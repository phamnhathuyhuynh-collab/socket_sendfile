"""Multi-client TLS file server with HMAC authentication and restricted sharing root."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import socket
import ssl
import threading
import time
from pathlib import Path
from typing import Callable

from .protocol import (MAX_FILES, TransferError, iter_items, measure, receive_items,
                       recv_json, require_ok, send_items, send_json)
from .security import SecurityError, config_dir, ensure_certificates, safe_path


class FileServer:
    def __init__(self, root: str | Path, secret: str, host: str = "0.0.0.0", port: int = 8000,
                 cert_folder: str | Path | None = None, log: Callable[[str], None] | None = None,
                 started: Callable[[str, int], None] | None = None):
        self.root = Path(root).expanduser().resolve()
        self.secret = secret
        self.host, self.port = host, port
        self.cert_folder = Path(cert_folder) if cert_folder else config_dir()
        self.log = log or (lambda _: None)
        self.started = started
        self.fingerprint = ""
        self.ready = threading.Event()
        self.failure: Exception | None = None
        self._stop = threading.Event()
        self._listener: socket.socket | None = None
        self._limit = threading.BoundedSemaphore(6)
        self._lock = threading.Lock()
        self._sessions: set[socket.socket] = set()

    def serve_forever(self) -> None:
        try:
            if len(self.secret) < 12:
                raise SecurityError("The shared access key must contain at least 12 characters (a generated key is recommended).")
            if not self.root.is_dir():
                raise TransferError("The shared directory does not exist.")
            forbidden = self.cert_folder.expanduser().resolve()
            if self.root == forbidden or self.root.is_relative_to(forbidden):
                raise SecurityError("The TLS key directory cannot be shared.")
            cert_file, key_file, fingerprint = ensure_certificates(self.cert_folder)
            self.fingerprint = fingerprint
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(str(cert_file), str(key_file))
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                listener.bind((self.host, self.port))
                listener.listen(16)
                listener.settimeout(0.4)
                self._listener = listener
                self.port = listener.getsockname()[1]
                self.log(f"Server listening on {self.host}:{self.port}")
                self.ready.set()
                if self.started:
                    self.started(fingerprint, self.port)
                while not self._stop.is_set():
                    try:
                        conn, address = listener.accept()
                    except socket.timeout:
                        continue
                    except OSError:
                        if self._stop.is_set():
                            break
                        raise
                    if not self._limit.acquire(blocking=False):
                        conn.close()
                        self.log("The six-connection limit has been reached.")
                        continue
                    thread = threading.Thread(target=self._handle_connection,
                                              args=(conn, address, context), daemon=True)
                    thread.start()
        except Exception as exc:
            self.failure = exc
            self.log("Server error: " + str(exc))
        finally:
            self._listener = None
            self.ready.set()
            self.log("Server stopped.")

    def stop(self) -> None:
        self._stop.set()
        listener = self._listener
        if listener:
            try:
                listener.close()
            except OSError:
                pass
        with self._lock:
            for sock in list(self._sessions):
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def _handle_connection(self, conn: socket.socket, address: tuple, context: ssl.SSLContext):
        tls = None
        try:
            conn.settimeout(120)
            tls = context.wrap_socket(conn, server_side=True)
            with self._lock:
                self._sessions.add(tls)
            nonce = secrets.token_bytes(32)
            send_json(tls, {"type": "challenge", "version": 1, "nonce": nonce.hex()})
            response = recv_json(tls)
            expected = hmac.new(self.secret.encode("utf-8"), nonce, hashlib.sha256).hexdigest()
            actual = response.get("proof", "")
            if response.get("type") != "auth" or not isinstance(actual, str) or not hmac.compare_digest(expected, actual):
                time.sleep(0.3)
                send_json(tls, {"ok": False, "error": "Authentication failed."})
                self.log(f"Rejected authentication attempt from {address[0]}")
                return
            send_json(tls, {"ok": True})
            message = recv_json(tls)
            operation = message.get("op")
            if operation == "list":
                self._list(tls, message.get("path", ""))
            elif operation == "upload":
                self._upload(tls, message.get("target", ""))
            elif operation == "download":
                self._download(tls, message.get("path", ""))
            else:
                raise TransferError("Unsupported operation.")
            self.log(f"{address[0]} — {operation}: completed")
        except (OSError, ssl.SSLError, ValueError, SecurityError, TransferError) as exc:
            self.log(f"{address[0]} — {type(exc).__name__}: {exc}")
            if tls is not None:
                try:
                    send_json(tls, {"ok": False, "error": str(exc)})
                except (OSError, ssl.SSLError, TransferError):
                    pass
        finally:
            if tls is not None:
                with self._lock:
                    self._sessions.discard(tls)
                try:
                    tls.close()
                except OSError:
                    pass
            else:
                conn.close()
            self._limit.release()

    def _list(self, tls: ssl.SSLSocket, relative: str):
        directory = safe_path(self.root, relative, allow_root=True, forbidden_dir=self.cert_folder)
        if not directory.is_dir():
            raise TransferError("The remote directory does not exist.")
        entries = []
        estimated_json_size = 256
        truncated = False
        with os.scandir(directory) as it:
            for entry in it:
                path = directory / entry.name
                try:
                    safe_path(self.root, path.relative_to(self.root).as_posix(), forbidden_dir=self.cert_folder)
                    if entry.is_symlink():
                        continue
                    typ = "dir" if entry.is_dir(follow_symlinks=False) else "file"
                    if typ == "file" and not entry.is_file(follow_symlinks=False):
                        continue
                    item = {"name": entry.name, "type": typ,
                            "size": entry.stat(follow_symlinks=False).st_size if typ == "file" else 0}
                    item_bytes = len(json.dumps(item, ensure_ascii=False).encode("utf-8")) + 2
                    if len(entries) >= 1000 or estimated_json_size + item_bytes > 58 * 1024:
                        truncated = True
                        break
                    entries.append(item)
                    estimated_json_size += item_bytes
                except (SecurityError, OSError):
                    continue
        entries.sort(key=lambda item: (item["type"] != "dir", item["name"].lower()))
        send_json(tls, {"ok": True, "path": relative, "entries": entries,
                        "truncated": truncated})

    def _upload(self, tls: ssl.SSLSocket, prefix: str):
        # Server alone decides where uploads may be written.
        destination = safe_path(self.root, prefix, allow_root=True, forbidden_dir=self.cert_folder)
        if destination.exists() and not destination.is_dir():
            raise TransferError("The upload destination is not a directory.")
        destination.mkdir(parents=True, exist_ok=True)
        send_json(tls, {"ok": True})
        files, total = receive_items(tls, self.root, prefix=prefix,
                                     forbidden_dir=self.cert_folder)
        send_json(tls, {"ok": True, "files": files, "bytes": total})

    def _download(self, tls: ssl.SSLSocket, relative: str):
        source = safe_path(self.root, relative, allow_root=True, forbidden_dir=self.cert_folder)
        if not source.is_file() and not source.is_dir():
            raise TransferError("The remote file or directory does not exist.")
        files, total = measure(source, forbidden_dir=self.cert_folder)
        send_json(tls, {"ok": True, "files": files, "total_bytes": total})
        send_items(tls, source, forbidden_dir=self.cert_folder)
