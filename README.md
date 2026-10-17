# RetroTransfer 98

**RetroTransfer 98** is a Windows 95/98-inspired desktop application for transferring files and folders between computers over a local network. It supports **Windows and Linux** in either client or server role. This project evolved from a simple `sendFile.py` / `recvFile.py` TCP experiment.

All application labels, dialogs, error messages, console output, code comments, tests, and documentation are in **English**.

## Features

- **Bidirectional transfers:** upload or download individual files and complete directory trees, including empty folders.
- **Two file explorers:** browse local files and drives on the left, and the server's shared folder on the right.
- **Classic desktop interface:** PySide6 interface with Windows 95/98-inspired gray panels, navy highlights, and beveled controls.
- **Streaming transport:** sends raw bytes in 256 KiB chunks without Base64 encoding or loading entire files into memory.
- **TLS 1.2+:** encrypts network traffic and requires the client to verify the server's SHA-256 certificate fingerprint.
- **HMAC-SHA256 authentication:** the server challenges the client; the shared access key is not sent in plaintext.
- **File integrity:** each file is checked with SHA-256 before its temporary `.part` file replaces the destination.
- **Restricted sharing:** blocks path traversal, absolute remote paths, symbolic links, and access to the TLS key directory.
- **Basic limits:** a maximum of six concurrent connections, 50 GiB per file, and 100,000 files per transfer.
- **Command-line mode:** start a headless server or send, download, and list files without launching the GUI.

## System requirements

- Python **3.10 or later** (Python 3.11+ recommended)
- Windows 10/11 or a desktop Linux distribution (including Arch Linux)
- Two computers on the same reachable LAN, or connected over a VPN

Python packages in `requirements.txt`:

- `PySide6` for the desktop interface
- `cryptography` for TLS identity generation

For the automated tests, install `pytest` separately.

## Installation

### Linux (Arch Linux and other distributions)

Open a terminal in the extracted `RetroTransfer98` folder:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python main.py
```

After installing the dependencies, you can also launch the application with:

```bash
./run_linux.sh
```

If Python virtual environments are unavailable on Arch Linux, install the required distribution packages using `pacman` first. Do not install the application's packages globally if you can use a virtual environment.

### Windows (PowerShell)

Open PowerShell in the extracted `RetroTransfer98` folder:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

After installing the dependencies, you may also launch the application with `run_windows.bat`.

**Use the same project version on both computers.** The client and server use a custom application protocol, not FTP, SFTP, or the original three-socket protocol.

## Quick start: Linux server and Windows client

### 1. Set up the server on Linux

1. Launch the application and open **SERVER / SHARE**.
2. Choose **Shared folder**, for example `/home/your-user/RetroTransfer_Shared`. The application creates the directory if it does not exist.
3. Set **Bind IP** to `0.0.0.0` to listen on all local IPv4 interfaces; keep **Port** at `8000`.
4. Keep the automatically generated **Share key**, or use your own key with at least 12 characters.
5. Click **Start server** and verify that the status shows **ONLINE**.
6. Copy the **TLS SHA-256 fingerprint**, and securely transfer both the fingerprint and share key to the Windows computer.
7. Find the Linux computer's Wi-Fi IP address using `hostname -I` or `ip -4 addr`.

Do not share the TLS private key. **Bind IP `0.0.0.0` is not the address that the client should connect to.**

### 2. Connect from Windows

1. Launch the same version of RetroTransfer 98 and open **CLIENT / EXPLORER**.
2. Enter the **Linux server IP** into **Server IP**, for example `192.168.1.129`.
3. Set **Port** to `8000`.
4. Enter the Linux server's **Share key** and its exact **TLS fingerprint**.
5. Click **Refresh**. The right-hand pane displays the content of the Linux shared folder.

If both machines use Wi-Fi, they can still connect normally, provided the router allows communication between devices. Guest Wi-Fi networks or client isolation settings may block device-to-device traffic.

### 3. Upload from Windows to Linux

1. In **LOCAL FILE EXPLORER** on the left, use **Drives** to navigate to a Windows drive if necessary.
2. Click a local file or folder. This fills the **Local source** field. Alternatively, use **Choose file** or **Choose folder**.
3. To upload to the shared folder root, leave **Upload into** empty. For a subfolder, enter a relative path such as `Uploads/2026`.
4. Click **Upload (local → server)**.
5. When the transfer finishes, the remote explorer navigates to the upload destination and refreshes its contents.

Example: uploading `projects` with **Upload into** set to `Uploads/2026` creates `Uploads/2026/projects/...` on the server.

### 4. Download from Linux to Windows

1. In **REMOTE FILE EXPLORER** on the right, click **Refresh** if needed.
2. Select the file or folder to download. Double-click a folder to browse inside it.
3. Under **Save to**, choose an existing local Windows folder, such as `C:\Users\YourUser\Downloads`.
4. Click **Download (server → local)**.

The **Parent** buttons only navigate to parent directories. They do not upload files. Remote browsing cannot go above the server's **Shared folder**.

### 5. Testing on one computer

To test without a second computer, start the server and click **Connect local client** on the Server tab. The application will fill in the client settings and open the Client tab. The client connects to `127.0.0.1`.

## Command-line interface

Run the following commands from the project directory:

```bash
# On the server computer:
python cli.py server --root ./Shared --host 0.0.0.0 --port 8000

# On the client computer (use the server's actual LAN IP and fingerprint):
python cli.py list --host 192.168.1.129 --port 8000 --fingerprint "<64-hex-fingerprint>"
python cli.py send ./example.txt --host 192.168.1.129 --port 8000 --fingerprint "<64-hex-fingerprint>"
python cli.py get example.txt --into ./Downloads --host 192.168.1.129 --port 8000 --fingerprint "<64-hex-fingerprint>"
```

The CLI prompts for the share key without placing it in shell history. The server prints its TLS fingerprint when it starts. The `--root` directory for CLI server mode and the download `--into` directory must already exist.

## Network troubleshooting

**Windows cannot reach the Linux server:**

```powershell
Test-NetConnection 192.168.1.129 -Port 8000
```

Replace the example IP with the Linux computer's actual IP. `TcpTestSucceeded : True` confirms that Windows can reach that TCP port; it does not confirm authentication. If the test fails, check the Linux IP address, server status, firewall rules, and router client isolation.

**The remote explorer is empty:** Confirm that the server's selected **Shared folder** contains files. The application does not expose the entire Linux filesystem. If you uploaded into a subfolder, navigate to that subfolder.

**No files appear on the Windows side:** The left pane is the **LOCAL FILE EXPLORER**. Click **Drives** to browse Windows drives or use the file/folder picker.

**Upload fails:** Check that **Local source** points to an existing file or folder. **Upload into** must be relative to the server's shared directory: `Uploads/2026` is valid; `C:\...` and `/home/...` are not. Look for details under **SERVER / SHARE → EVENT LOG**.

**Download fails:** Make sure **Save to** points to an existing, writable folder on the client.

**Fingerprint mismatch:** Do not bypass verification. Check the fingerprint directly on the intended server. A regenerated server certificate changes its fingerprint.

## Security considerations and limitations

- This is an **LAN/VPN-oriented tool**, not a hardened public file-hosting service. Do not expose the server port directly to the public Internet. Use a VPN for remote connections.
- Verify the TLS fingerprint through a trusted channel before the first connection. An attacker who supplies a false fingerprint can impersonate a server.
- Anyone who knows the share key has **read and write** access inside the shared folder. There are no per-user permissions or upload-only accounts.
- A file with the same path can be **overwritten** after the new file passes its SHA-256 check. Concurrent uploads to the same destination can still overwrite one another.
- Symbolic links are rejected, but path checks alone do not eliminate local filesystem race attacks from malicious processes running on the server. For untrusted hosts, stronger OS-level isolation or descriptor-based traversal would be required.
- There is no interrupted-transfer resume, bandwidth quota, storage quota, durable audit logging, or encryption of files at rest.
- Cancellation takes effect between transfer chunks; already completed files may remain at the destination.
- By default, TLS identity files are created under `~/.config/retrotransfer98` (or `XDG_CONFIG_HOME` on supported Linux systems), and must not be stored in the shared data folder.
- The GUI creates a new random share key at startup. If you restart the server GUI, enter its current key again on the client.

## Run the tests

The backend integration tests do not require PySide6:

```bash
python -m pip install pytest
python -m pytest -q
```

The integration suite covers binary files, directories, empty files, authentication failure, TLS identity verification, unsafe paths, symbolic links, concurrent uploads, checksum failure, nested upload destinations, and Unicode filenames.

**GUI testing must be performed on a machine with PySide6 installed.** The backend tests alone do not establish that every GUI control works on both operating systems.

## Project structure

```text
RetroTransfer98/
├── main.py                    # Desktop entry point
├── cli.py                     # Command-line entry point
├── retrotransfer/
│   ├── __init__.py
│   ├── gui.py                 # Windows 95/98-inspired interface
│   ├── client.py              # Secure file-transfer client
│   ├── server.py              # Multiclient TLS server
│   ├── protocol.py            # Control-message framing and file streaming
│   └── security.py            # TLS certificates, fingerprints, and safe paths
├── tests/
│   └── test_transfer.py       # Integration tests
├── requirements.txt
├── run_linux.sh
├── run_windows.bat
├── CHANGELOG.md
└── README.md
```
