from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from retrotransfer.client import FileClient
from retrotransfer.protocol import TransferError, recv_json, send_json
from retrotransfer.security import SecurityError, safe_path
from retrotransfer.server import FileServer

SECRET = "development-testing-secret-123"


@pytest.fixture
def setup_server(tmp_path):
    shared = tmp_path / "Shared"
    shared.mkdir()
    server = FileServer(shared, SECRET, host="127.0.0.1", port=0,
                        cert_folder=tmp_path / "Config")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.ready.wait(10), "server did not start"
    assert server.failure is None, str(server.failure)
    client = FileClient("127.0.0.1", server.port, SECRET, server.fingerprint)
    yield server, client, shared, tmp_path
    server.stop()
    thread.join(timeout=5)
    assert not thread.is_alive()


def test_upload_and_download_binary_file(setup_server):
    _, client, shared, temp = setup_server
    payload = os.urandom(735_117) + b"\x00\xff\x0a"
    src = temp / "sample picture.bin"
    src.write_bytes(payload)
    events = []
    result = client.upload(src, progress=lambda done, total: events.append((done, total)))
    assert result["files"] == 1
    assert (shared / src.name).read_bytes() == payload
    assert events[-1] == (len(payload), len(payload))
    assert client.list_remote()["entries"][0]["name"] == src.name

    dest = temp / "download"
    dest.mkdir()
    downloaded = client.download(src.name, dest)
    assert downloaded["files"] == 1
    assert (dest / src.name).read_bytes() == payload


def test_folder_recursive_and_empty_subfolders(setup_server):
    _, client, shared, tmp = setup_server
    folder = tmp / "3d_models"
    (folder / "parts" / "empty").mkdir(parents=True)
    (folder / "parts" / "mesh.obj").write_text("v 0 0 0\nv 1 0 0\n", encoding="utf-8")
    (folder / "README").write_text("No extension", encoding="utf-8")
    uploaded = client.upload(folder, remote_folder="projects/2026")
    assert uploaded["files"] == 2
    remote = shared / "projects" / "2026" / "3d_models"
    assert (remote / "parts" / "empty").is_dir()
    assert (remote / "README").read_text() == "No extension"
    assert (remote / "parts" / "mesh.obj").read_bytes() == (folder / "parts" / "mesh.obj").read_bytes()
    dest = tmp / "received"
    dest.mkdir()
    client.download("projects/2026/3d_models", dest)
    assert (dest / "3d_models" / "parts" / "empty").is_dir()
    assert (dest / "3d_models" / "README").read_text() == "No extension"


def test_empty_file_and_overwrite(setup_server):
    _, client, shared, tmp = setup_server
    source = tmp / "zero.txt"
    source.write_bytes(b"")
    client.upload(source)
    assert (shared / "zero.txt").read_bytes() == b""
    source.write_bytes(b"now updated")
    client.upload(source)
    assert (shared / "zero.txt").read_bytes() == b"now updated"
    assert not list(shared.glob(".rt98-*.part"))


def test_wrong_secret_rejected(setup_server):
    server, _, _, _ = setup_server
    fake = FileClient("127.0.0.1", server.port, "incorrect-password", server.fingerprint)
    with pytest.raises(TransferError, match="Authentication"):
        fake.list_remote()


def test_wrong_fingerprint_rejected_before_auth(setup_server):
    server, _, _, _ = setup_server
    fake = FileClient("127.0.0.1", server.port, SECRET, "0" * 64)
    with pytest.raises(SecurityError, match="fingerprint"):
        fake.list_remote()


def test_traversal_rejected(setup_server):
    server, client, shared, tmp = setup_server
    for name in ("../bad", "/etc/passwd", "C:\\Windows", "ok/../../bad", "ok//bad"):
        with pytest.raises(SecurityError):
            safe_path(shared, name)
    with client._connect() as tls:
        send_json(tls, {"op": "upload", "target": "../bad"})
        assert recv_json(tls)["ok"] is False
    assert not (tmp / "bad").exists()


def test_symlink_escape_rejected(setup_server):
    _, client, shared, tmp = setup_server
    other = tmp / "private"
    other.mkdir()
    (other / "secret.txt").write_text("confidential")
    (shared / "link").symlink_to(other, target_is_directory=True)
    listing = client.list_remote()
    assert not any(e["name"] == "link" for e in listing["entries"])
    with pytest.raises(TransferError, match="Symbolic links"):
        client.download("link/secret.txt", tmp)


def test_certificate_directory_blocked_when_root_contains_config(tmp_path):
    root = tmp_path / "share"
    root.mkdir()
    keys = root / ".certs"
    srv = FileServer(root, SECRET, host="127.0.0.1", port=0, cert_folder=keys)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    assert srv.ready.wait(10) and srv.failure is None
    client = FileClient("127.0.0.1", srv.port, SECRET, srv.fingerprint)
    assert not any(e["name"] == ".certs" for e in client.list_remote()["entries"])
    with pytest.raises(TransferError):
        client.download(".certs/identity.key", tmp_path)
    srv.stop()
    thread.join(timeout=5)


def test_concurrent_uploads(setup_server):
    _, client, shared, tmp = setup_server
    files = []
    for i in range(4):
        path = tmp / f"file-{i}.dat"
        path.write_bytes(os.urandom(125_000 + i))
        files.append(path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        result = list(pool.map(client.upload, files))
    assert len(result) == 4
    for path in files:
        assert (shared / path.name).read_bytes() == path.read_bytes()


def test_corrupted_checksum_never_overwrites_file(setup_server):
    _, client, shared, _ = setup_server
    old = shared / "protect.txt"
    old.write_text("keep this original")
    with client._connect() as tls:
        send_json(tls, {"op": "upload", "target": ""})
        assert recv_json(tls)["ok"] is True
        send_json(tls, {"type": "file", "path": "protect.txt", "size": 4})
        tls.sendall(b"evil")
        send_json(tls, {"type": "checksum", "sha256": "deadbeef"})
        err = recv_json(tls)
        assert err["ok"] is False
        assert "SHA-256" in err["error"]
    assert old.read_text() == "keep this original"
    assert not list(shared.glob(".rt98-*.part"))


def test_upload_to_subdirectory_then_browse_it(setup_server):
    _, client, shared, tmp = setup_server
    source = tmp / "windows selected file.txt"
    source.write_text("Windows to Linux", encoding="utf-8")
    result = client.upload(source, remote_folder="Uploads/From Windows")
    assert result["files"] == 1
    assert (shared / "Uploads" / "From Windows" / source.name).read_text() == "Windows to Linux"
    entries = client.list_remote("Uploads/From Windows")["entries"]
    assert [entry["name"] for entry in entries] == [source.name]


def test_unicode_and_nested_windows_local_source(setup_server):
    _, client, shared, tmp = setup_server
    src = tmp / "Foot measurement project"
    (src / "designs").mkdir(parents=True)
    (src / "designs" / "shoe_👟_01.obj").write_bytes(b"3D\0data")
    result = client.upload(src)
    assert result["files"] == 1
    assert (shared / src.name / "designs" / "shoe_👟_01.obj").read_bytes() == b"3D\0data"
    back = tmp / "windows_download"
    back.mkdir()
    client.download(src.name, back)
    assert (back / src.name / "designs" / "shoe_👟_01.obj").read_bytes() == b"3D\0data"
