"""Length-prefixed JSON control messages + streamed raw TCP file contents."""
from __future__ import annotations

import hashlib
import json
import os
import socket
import struct
import tempfile
import threading
from pathlib import Path
from typing import Callable

from .security import SecurityError, safe_path

CHUNK = 256 * 1024
MAX_JSON = 64 * 1024
MAX_FILE_SIZE = 50 * 1024 ** 3  # 50 GiB per file
MAX_FILES = 100_000
Progress = Callable[[int], None] | None


class TransferError(Exception):
    pass


def recv_exact(sock: socket.socket, n: int) -> bytes:
    result = bytearray()
    while len(result) < n:
        data = sock.recv(n - len(result))
        if not data:
            raise TransferError("The connection closed while receiving data.")
        result.extend(data)
    return bytes(result)


def send_json(sock: socket.socket, payload: dict) -> None:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_JSON:
        raise TransferError("The control message exceeds 64 KiB.")
    sock.sendall(struct.pack("!I", len(raw)) + raw)


def recv_json(sock: socket.socket) -> dict:
    (length,) = struct.unpack("!I", recv_exact(sock, 4))
    if length < 2 or length > MAX_JSON:
        raise TransferError("Invalid control message length.")
    try:
        result = json.loads(recv_exact(sock, length).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TransferError("Invalid JSON payload.") from exc
    if not isinstance(result, dict):
        raise TransferError("A control message must be a JSON object.")
    return result


def require_ok(message: dict) -> dict:
    if not message.get("ok"):
        raise TransferError(str(message.get("error", "The remote peer rejected the request.")))
    return message


def send_file(sock: socket.socket, file_path: Path, relative_name: str,
              progress: Progress = None, cancel: threading.Event | None = None) -> int:
    size = file_path.stat().st_size
    if size > MAX_FILE_SIZE:
        raise TransferError("The file exceeds the 50 GiB limit.")
    send_json(sock, {"type": "file", "path": relative_name, "size": size})
    digest = hashlib.sha256()
    with file_path.open("rb") as file:
        remaining = size
        while remaining:
            if cancel is not None and cancel.is_set():
                raise TransferError("File transfer was canceled.")
            chunk = file.read(min(CHUNK, remaining))
            if not chunk:
                raise TransferError("The source file changed during the transfer.")
            sock.sendall(chunk)
            digest.update(chunk)
            remaining -= len(chunk)
            if progress:
                progress(len(chunk))
    send_json(sock, {"type": "checksum", "sha256": digest.hexdigest()})
    require_ok(recv_json(sock))
    return size


def receive_file(sock: socket.socket, root: Path, relative_name: str, size: int,
                 progress: Progress = None, cancel: threading.Event | None = None,
                 forbidden_dir: Path | None = None) -> int:
    if type(size) is not int or size < 0 or size > MAX_FILE_SIZE:
        raise TransferError("Invalid file size or file exceeds the 50 GiB limit.")
    target = safe_path(root, relative_name, forbidden_dir=forbidden_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Re-check after creating parents (and before creating temporary output).
    target = safe_path(root, relative_name, forbidden_dir=forbidden_dir)
    if target.exists() and not target.is_file():
        raise TransferError("The destination already exists and is not a file.")
    fd, temporary = tempfile.mkstemp(prefix=".rt98-", suffix=".part", dir=target.parent)
    try:
        digest = hashlib.sha256()
        with os.fdopen(fd, "wb") as output:
            remaining = size
            while remaining:
                if cancel is not None and cancel.is_set():
                    raise TransferError("File transfer was canceled.")
                chunk = sock.recv(min(CHUNK, remaining))
                if not chunk:
                    raise TransferError("Connection lost while receiving the file.")
                output.write(chunk)
                digest.update(chunk)
                remaining -= len(chunk)
                if progress:
                    progress(len(chunk))
        checksum = recv_json(sock)
        if checksum.get("type") != "checksum" or checksum.get("sha256") != digest.hexdigest():
            raise TransferError("SHA-256 mismatch: the file is corrupted or incomplete.")
        target = safe_path(root, relative_name, forbidden_dir=forbidden_dir)
        os.replace(temporary, target)
        send_json(sock, {"ok": True, "type": "file_ack"})
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return size


def iter_items(source: Path, *, forbidden_dir: Path | None = None):
    """Yield ('dir'|'file', source_path, relative_posix_path), without links."""
    source = source.resolve(strict=True)
    if source.is_file():
        yield "file", source, source.name
        return
    if not source.is_dir():
        raise TransferError("The source is not a file or directory.")
    yield "dir", source, source.name
    for directory, directories, files in os.walk(source, followlinks=False):
        base = Path(directory)
        directories[:] = sorted(d for d in directories if not (base / d).is_symlink()
                                and not is_forbidden(base / d, forbidden_dir))
        for name in directories:
            path = base / name
            yield "dir", path, path.relative_to(source.parent).as_posix()
        for name in sorted(files):
            path = base / name
            if path.is_file() and not path.is_symlink() and not is_forbidden(path, forbidden_dir):
                yield "file", path, path.relative_to(source.parent).as_posix()


def is_forbidden(path: Path, forbidden: Path | None) -> bool:
    if forbidden is None:
        return False
    resolved = path.resolve(strict=False)
    return resolved == forbidden or resolved.is_relative_to(forbidden)


def measure(source: Path, *, forbidden_dir: Path | None = None) -> tuple[int, int]:
    files, total = 0, 0
    for kind, path, _ in iter_items(source, forbidden_dir=forbidden_dir):
        if kind == "file":
            files += 1
            if files > MAX_FILES:
                raise TransferError("Too many files (limit: 100,000).")
            total += path.stat().st_size
    return files, total


def send_items(sock: socket.socket, source: Path, progress: Progress = None,
               cancel: threading.Event | None = None,
               forbidden_dir: Path | None = None) -> tuple[int, int]:
    count, total = 0, 0
    for kind, path, rel in iter_items(source, forbidden_dir=forbidden_dir):
        if cancel is not None and cancel.is_set():
            raise TransferError("File transfer was canceled.")
        if kind == "dir":
            send_json(sock, {"type": "dir", "path": rel})
        else:
            count += 1
            if count > MAX_FILES:
                raise TransferError("Too many files.")
            total += send_file(sock, path, rel, progress, cancel)
    send_json(sock, {"type": "done"})
    return count, total


def receive_items(sock: socket.socket, target_root: Path, *, prefix: str = "",
                  progress: Progress = None, cancel: threading.Event | None = None,
                  forbidden_dir: Path | None = None) -> tuple[int, int]:
    from .security import safe_remote_join

    count, total = 0, 0
    while True:
        if cancel is not None and cancel.is_set():
            raise TransferError("File transfer was canceled.")
        frame = recv_json(sock)
        if frame.get("type") == "done":
            return count, total
        kind, name = frame.get("type"), frame.get("path")
        if kind not in ("dir", "file") or not isinstance(name, str):
            raise TransferError("Invalid item type or name.")
        relative = safe_remote_join(prefix, name)
        if kind == "dir":
            folder = safe_path(target_root, relative, forbidden_dir=forbidden_dir)
            folder.mkdir(parents=True, exist_ok=True)
            safe_path(target_root, relative, forbidden_dir=forbidden_dir)
        else:
            count += 1
            if count > MAX_FILES:
                raise TransferError("Too many files.")
            total += receive_file(sock, target_root, relative, frame.get("size"),
                                  progress, cancel, forbidden_dir)
