"""TLS fingerprint-verified client: list, upload, and download."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import socket
import ssl
import threading
from pathlib import Path
from typing import Callable

from .protocol import (TransferError, measure, receive_items, recv_json, require_ok,
                       send_items, send_json)
from .security import SecurityError, fingerprint_of_der, normalize_fingerprint, relative_parts


class FileClient:
    def __init__(self, host: str, port: int, secret: str, fingerprint: str,
                 timeout: float = 30.0):
        self.host, self.port = host.strip(), int(port)
        self.secret = secret
        self.fingerprint = normalize_fingerprint(fingerprint)
        self.timeout = timeout
        if not self.host or not self.secret:
            raise SecurityError("Enter a server address and a shared access key.")

    def _connect(self) -> ssl.SSLSocket:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        # Certificate authenticity is checked explicitly with the pinned SHA-256.
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        raw = socket.create_connection((self.host, self.port), timeout=self.timeout)
        tls = None
        try:
            tls = context.wrap_socket(raw, server_hostname=self.host)
            tls.settimeout(120)
            actual = fingerprint_of_der(tls.getpeercert(binary_form=True))
            if not secrets.compare_digest(actual, self.fingerprint):
                tls.close()
                raise SecurityError("The TLS fingerprint does not match. Authentication was not sent. Verify the server identity.")
            challenge = recv_json(tls)
            if challenge.get("type") != "challenge" or challenge.get("version") != 1:
                raise TransferError("Incompatible protocol version.")
            try:
                nonce = bytes.fromhex(challenge["nonce"])
            except (KeyError, ValueError, TypeError) as exc:
                raise TransferError("Invalid authentication challenge.") from exc
            if len(nonce) != 32:
                raise TransferError("Invalid challenge.")
            proof = hmac.new(self.secret.encode("utf-8"), nonce, hashlib.sha256).hexdigest()
            send_json(tls, {"type": "auth", "proof": proof})
            require_ok(recv_json(tls))
            return tls
        except Exception:
            if tls is not None:
                tls.close()
            else:
                raw.close()
            raise

    def list_remote(self, path: str = "") -> dict:
        relative_parts(path, allow_root=True)
        with self._connect() as tls:
            send_json(tls, {"op": "list", "path": path})
            return require_ok(recv_json(tls))

    def upload(self, source: str | Path, remote_folder: str = "",
               progress: Callable[[int, int], None] | None = None,
               cancel: threading.Event | None = None) -> dict:
        source = Path(source).expanduser().absolute()
        if source.is_symlink() or not source.exists():
            raise TransferError("The selected source does not exist or is a symbolic link.")
        relative_parts(source.name)
        relative_parts(remote_folder, allow_root=True)
        _, total = measure(source)
        sent = 0

        def update(delta: int):
            nonlocal sent
            sent += delta
            if progress:
                progress(sent, total)

        if progress:
            progress(0, total)
        with self._connect() as tls:
            send_json(tls, {"op": "upload", "target": remote_folder})
            require_ok(recv_json(tls))
            send_items(tls, source, progress=update, cancel=cancel)
            return require_ok(recv_json(tls))

    def download(self, remote_path: str, local_folder: str | Path,
                 progress: Callable[[int, int], None] | None = None,
                 cancel: threading.Event | None = None) -> dict:
        relative_parts(remote_path)
        folder = Path(local_folder).expanduser().absolute()
        if not folder.is_dir():
            raise TransferError("The download destination folder does not exist.")
        with self._connect() as tls:
            send_json(tls, {"op": "download", "path": remote_path})
            info = require_ok(recv_json(tls))
            total = info.get("total_bytes", 0)
            received = 0

            def update(delta: int):
                nonlocal received
                received += delta
                if progress:
                    progress(received, total)

            if progress:
                progress(0, total)
            files, size = receive_items(tls, folder, progress=update, cancel=cancel)
            return {"ok": True, "files": files, "bytes": size}
