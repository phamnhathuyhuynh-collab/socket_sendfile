"""PySide6 classic Windows 95/98 inspired desktop application."""
from __future__ import annotations

import secrets
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QDir, QModelIndex, QStandardPaths
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QSpinBox, QStyle, QTabWidget,
    QTextEdit, QVBoxLayout, QWidget, QGridLayout, QSplitter, QTreeView, QFileSystemModel,
)

from .client import FileClient
from .server import FileServer


RETRO_STYLE = """
QWidget { background: #C0C0C0; color: #151515; font-family: Tahoma, 'DejaVu Sans', sans-serif; font-size: 11px; }
QMainWindow { background: #C0C0C0; }
QLabel#titleBar { background: #000080; color: white; padding: 11px 13px; font-weight: bold; font-size: 17px; }
QLabel#bannerSub { color: #1D1D1D; font-size: 10px; padding: 3px; }
QLabel#online { color: #006018; font-weight: bold; }
QLabel#offline { color: #830000; font-weight: bold; }
QGroupBox { border: 2px solid; border-color: #FFFFFF #606060 #606060 #FFFFFF;
            margin-top: 15px; padding: 13px 11px 10px 11px; font-weight: bold; background: #C0C0C0; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 1px 7px; background: #C0C0C0; }
QLineEdit, QSpinBox, QTextEdit, QListWidget, QTreeView {
    background: #FFFFFF; color: #101010; selection-background-color: #000080;
    selection-color: #FFFFFF; border: 2px solid;
    border-color: #686868 #FFFFFF #FFFFFF #686868; padding: 5px; }
QLineEdit:read-only { background: #EEEEEE; }
QPushButton {
    background: #C0C0C0; color: #111; min-height: 27px; padding: 3px 10px;
    border: 2px solid; border-color: #FFFFFF #565656 #565656 #FFFFFF; font-weight: bold;
}
QPushButton:pressed { border-color: #565656 #FFFFFF #FFFFFF #565656; padding-left: 12px; padding-top: 5px; }
QPushButton:disabled { color: #888; }
QPushButton#primary { background: #D8D8D8; border-bottom: 3px solid #333; }
QTreeView::item:selected { background: #000080; color: white; }
QTabWidget::pane { border: 2px solid; border-color: #FFFFFF #606060 #606060 #FFFFFF; }
QTabBar::tab { background: #AEAEAE; padding: 7px 18px; margin-right: 2px; border: 1px solid #5E5E5E; }
QTabBar::tab:selected { background: #C0C0C0; border-top: 3px solid #000080; font-weight: bold; }
QProgressBar { background: #FFFFFF; color: #111; text-align: center; height: 21px;
               border: 2px solid; border-color: #656565 #FFFFFF #FFFFFF #656565; }
QProgressBar::chunk { background: #000080; margin: 2px; }
QMenuBar, QMenu { background: #C0C0C0; }
QMenuBar::item:selected, QMenu::item:selected { background: #000080; color: white; }
QStatusBar { border-top: 2px solid #FFFFFF; }
QCheckBox { spacing: 6px; }
"""


class Worker(QThread):
    result = Signal(object)
    error = Signal(str)
    progress = Signal(object, object)

    def __init__(self, connection: dict, action: str, **kwargs):
        super().__init__()
        self.connection, self.action, self.kwargs = connection, action, kwargs
        import threading
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        try:
            client = FileClient(**self.connection)
            if self.action == "list":
                result = client.list_remote(self.kwargs["path"])
            elif self.action == "upload":
                result = client.upload(self.kwargs["source"], self.kwargs["remote_folder"],
                                       progress=self.progress.emit, cancel=self.cancel_event)
            elif self.action == "download":
                result = client.download(self.kwargs["remote_path"], self.kwargs["local_folder"],
                                         progress=self.progress.emit, cancel=self.cancel_event)
            else:
                raise RuntimeError("Unknown action")
            self.result.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class ServerWorker(QThread):
    server_started = Signal(str, int)
    server_log = Signal(str)

    def __init__(self, root: str, secret: str, host: str, port: int):
        super().__init__()
        self.server = FileServer(root, secret, host, port,
                                 log=self.server_log.emit,
                                 started=self.server_started.emit)

    def run(self):
        self.server.serve_forever()

    def stop(self):
        self.server.stop()


class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RetroTransfer 98 — Secure LAN File Manager")
        self.resize(1120, 735)
        self.setMinimumSize(860, 620)
        self.server_worker: ServerWorker | None = None
        self.worker: Worker | None = None
        self._needs_refresh = False
        self.remote_entries: list[dict] = []
        self._build()

    def _button(self, text, slot, primary=False):
        button = QPushButton(text)
        button.clicked.connect(slot)
        if primary:
            button.setObjectName("primary")
        return button

    def _build(self):
        menu = self.menuBar().addMenu("&File")
        quit_action = QAction("Exit", self)
        quit_action.triggered.connect(self.close)
        menu.addAction(quit_action)
        help_menu = self.menuBar().addMenu("&Help")
        about = QAction("About", self)
        about.triggered.connect(self.show_about)
        help_menu.addAction(about)

        container = QWidget()
        self.setCentralWidget(container)
        root_layout = QVBoxLayout(container)
        root_layout.setContentsMargins(13, 11, 13, 9)
        root_layout.setSpacing(7)
        top = QLabel("▣  RETROTRANSFER 98    //    SECURE FILE MANAGER")
        top.setObjectName("titleBar")
        root_layout.addWidget(top)
        subtitle = QLabel("Classic desktop, modern transport  •  TCP + TLS  •  HMAC  •  SHA-256")
        subtitle.setObjectName("bannerSub")
        root_layout.addWidget(subtitle)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._make_client(), "▸  CLIENT / EXPLORER")
        self.tabs.addTab(self._make_server(), "▸  SERVER / SHARE")
        root_layout.addWidget(self.tabs, stretch=1)
        self.statusBar().showMessage("READY  |  Secure LAN transfer  |  Verify the server fingerprint before connecting.")

    def _make_client(self):
        tab = QWidget()
        main = QVBoxLayout(tab)
        main.setContentsMargins(12, 11, 12, 10)
        main.setSpacing(8)

        connection = QGroupBox("01 / SERVER CONNECTION")
        grid = QGridLayout(connection)
        self.remote_host = QLineEdit("127.0.0.1")
        self.remote_port = QSpinBox()
        self.remote_port.setRange(1, 65535)
        self.remote_port.setValue(8000)
        self.remote_secret = QLineEdit()
        self.remote_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.remote_fingerprint = QLineEdit()
        self.remote_fingerprint.setPlaceholderText("Required: SHA-256 fingerprint from the server")
        grid.addWidget(QLabel("Server IP:"), 0, 0)
        grid.addWidget(self.remote_host, 0, 1)
        grid.addWidget(QLabel("Port:"), 0, 2)
        grid.addWidget(self.remote_port, 0, 3)
        grid.addWidget(QLabel("Share key:"), 1, 0)
        grid.addWidget(self.remote_secret, 1, 1)
        grid.addWidget(QLabel("Fingerprint:"), 2, 0)
        grid.addWidget(self.remote_fingerprint, 2, 1, 1, 3)
        self.show_client_password = QCheckBox("Show key")
        self.show_client_password.toggled.connect(lambda checked: self.remote_secret.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password))
        grid.addWidget(self.show_client_password, 1, 2, 1, 2)
        grid.setColumnStretch(1, 4)
        grid.setColumnStretch(3, 1)
        main.addWidget(connection)

        # Two real file explorers: this computer (Windows/Linux) and the remote server.
        # The earlier version only displayed the server, which made the Windows
        # machine appear to have no accessible local files.
        browser_split = QSplitter(Qt.Orientation.Horizontal)

        local_explorer = QGroupBox("02 / LOCAL FILE EXPLORER — THIS COMPUTER")
        local_layout = QVBoxLayout(local_explorer)
        local_address = QHBoxLayout()
        local_address.addWidget(QLabel("Local:"))
        self.local_current = QLineEdit(str(Path.home()))
        self.local_current.returnPressed.connect(self.local_go_path)
        local_address.addWidget(self.local_current, stretch=1)
        local_address.addWidget(self._button("↑ Parent", self.local_up))
        local_address.addWidget(self._button("Drives", self.local_drives))
        local_layout.addLayout(local_address)

        self.local_model = QFileSystemModel(self)
        self.local_model.setFilter(QDir.Filter.AllEntries | QDir.Filter.NoDotAndDotDot
                                   | QDir.Filter.AllDirs | QDir.Filter.Drives)
        self.local_model.setRootPath(str(Path.home()))
        self.local_tree = QTreeView()
        self.local_tree.setModel(self.local_model)
        self.local_tree.setRootIndex(self.local_model.index(str(Path.home())))
        self.local_tree.setSelectionMode(QTreeView.SelectionMode.SingleSelection)
        self.local_tree.setSelectionBehavior(QTreeView.SelectionBehavior.SelectRows)
        self.local_tree.setAlternatingRowColors(True)
        self.local_tree.setColumnWidth(0, 220)
        self.local_tree.hideColumn(2)  # Type column: leave name, size and date.
        self.local_tree.clicked.connect(self.local_clicked)
        self.local_tree.doubleClicked.connect(self.local_double_clicked)
        local_layout.addWidget(self.local_tree, stretch=1)
        local_layout.addWidget(QLabel("Click to select an upload source  •  Double-click to open a folder"))
        browser_split.addWidget(local_explorer)

        explorer = QGroupBox("03 / REMOTE FILE EXPLORER — SERVER")
        explorer_layout = QVBoxLayout(explorer)
        address = QHBoxLayout()
        address.addWidget(QLabel("Remote:"))
        self.current_remote = QLineEdit("")
        self.current_remote.setPlaceholderText("Leave blank to browse the shared folder root")
        self.current_remote.returnPressed.connect(self.refresh_remote)
        address.addWidget(self.current_remote, 1)
        self.go_up = self._button("↑ Parent", self.up_remote)
        self.go_up.setEnabled(False)
        self.refresh_button = self._button("Refresh", self.refresh_remote, True)
        address.addWidget(self.go_up)
        address.addWidget(self.refresh_button)
        explorer_layout.addLayout(address)
        self.file_list = QListWidget()
        self.file_list.itemDoubleClicked.connect(self.open_remote_item)
        explorer_layout.addWidget(self.file_list, stretch=1)
        self.remote_hint = QLabel("Click Refresh to browse the server files.")
        explorer_layout.addWidget(self.remote_hint)
        browser_split.addWidget(explorer)
        browser_split.setSizes([470, 470])
        main.addWidget(browser_split, stretch=3)

        transfer = QGroupBox("04 / FILE TRANSFER — LOCAL ↔ REMOTE")
        form = QGridLayout(transfer)
        self.source_edit = QLineEdit()
        self.source_edit.setPlaceholderText("Select a file in Local Explorer or use Choose file/folder")
        form.addWidget(QLabel("Local source:"), 0, 0)
        form.addWidget(self.source_edit, 0, 1, 1, 2)
        form.addWidget(self._button("Choose file", self.pick_file), 0, 3)
        form.addWidget(self._button("Choose folder", self.pick_folder), 0, 4)
        self.remote_folder = QLineEdit()
        self.remote_folder.setPlaceholderText("Destination inside the shared folder, e.g. docs (blank = root)")
        form.addWidget(QLabel("Upload into:"), 1, 0)
        form.addWidget(self.remote_folder, 1, 1, 1, 4)
        downloads = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
        # Downloads can be redirected by Windows/OneDrive or missing altogether.
        if not downloads or not Path(downloads).is_dir():
            downloads = str(Path.home())
        self.download_folder = QLineEdit(downloads)
        form.addWidget(QLabel("Save to:"), 2, 0)
        form.addWidget(self.download_folder, 2, 1, 1, 3)
        form.addWidget(self._button("Browse...", self.pick_download_folder), 2, 4)
        self.upload_button = self._button("→ Upload (local → server)", self.upload, True)
        self.download_button = self._button("← Download (server → local)", self.download, True)
        self.cancel_button = self._button("Cancel", self.cancel_operation)
        self.cancel_button.setEnabled(False)
        actions = QHBoxLayout()
        actions.addWidget(self.upload_button)
        actions.addWidget(self.download_button)
        actions.addStretch()
        actions.addWidget(self.cancel_button)
        form.addLayout(actions, 3, 0, 1, 5)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        form.addWidget(self.bar, 4, 0, 1, 5)
        main.addWidget(transfer)
        self.client_message = QLabel("Not connected to the server.")
        main.addWidget(self.client_message)
        return tab

    def _make_server(self):
        tab = QWidget()
        main = QVBoxLayout(tab)
        main.setContentsMargins(12, 11, 12, 10)
        main.setSpacing(10)
        settings = QGroupBox("01 / SERVER CONFIGURATION")
        grid = QGridLayout(settings)
        default_root = Path.home() / "RetroTransfer_Shared"
        self.share_root = QLineEdit(str(default_root))
        grid.addWidget(QLabel("Shared folder:"), 0, 0)
        grid.addWidget(self.share_root, 0, 1, 1, 3)
        grid.addWidget(self._button("Browse...", self.pick_share_root), 0, 4)
        self.bind_host = QLineEdit("0.0.0.0")
        self.bind_host.setToolTip("0.0.0.0 = all IPv4 interfaces; 127.0.0.1 = this computer only")
        self.bind_port = QSpinBox()
        self.bind_port.setRange(1, 65535)
        self.bind_port.setValue(8000)
        grid.addWidget(QLabel("Bind IP:"), 1, 0)
        grid.addWidget(self.bind_host, 1, 1)
        grid.addWidget(QLabel("Port:"), 1, 2)
        grid.addWidget(self.bind_port, 1, 3)
        self.server_secret = QLineEdit(secrets.token_urlsafe(24))
        self.server_secret.setEchoMode(QLineEdit.EchoMode.Password)
        grid.addWidget(QLabel("Share key:"), 2, 0)
        grid.addWidget(self.server_secret, 2, 1, 1, 3)
        self.new_key_button = self._button("New key", self.random_key)
        grid.addWidget(self.new_key_button, 2, 4)
        self.show_server_password = QCheckBox("Show key")
        self.show_server_password.toggled.connect(lambda checked: self.server_secret.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password))
        grid.addWidget(self.show_server_password, 3, 1)
        main.addWidget(settings)

        identity = QGroupBox("02 / TLS SERVER IDENTITY")
        id_layout = QGridLayout(identity)
        self.server_fingerprint = QLineEdit()
        self.server_fingerprint.setReadOnly(True)
        self.server_fingerprint.setPlaceholderText("Generated when you start the server")
        id_layout.addWidget(QLabel("SHA-256:"), 0, 0)
        id_layout.addWidget(self.server_fingerprint, 0, 1)
        id_layout.addWidget(self._button("Copy", self.copy_fingerprint), 0, 2)
        info = QLabel("Verify the fingerprint through a trusted channel before the first connection. Never share the private key.")
        info.setWordWrap(True)
        id_layout.addWidget(info, 1, 0, 1, 3)
        main.addWidget(identity)

        controls = QHBoxLayout()
        self.start_button = self._button("▶  Start server", self.start_server, True)
        self.stop_button = self._button("■  Stop server", self.stop_server)
        self.stop_button.setEnabled(False)
        self.local_connect_button = self._button("Connect local client", self.use_local_server)
        self.local_connect_button.setEnabled(False)
        self.server_status = QLabel("● OFFLINE")
        self.server_status.setObjectName("offline")
        controls.addWidget(self.start_button)
        controls.addWidget(self.stop_button)
        controls.addWidget(self.local_connect_button)
        controls.addStretch(1)
        controls.addWidget(self.server_status)
        main.addLayout(controls)

        logs = QGroupBox("03 / EVENT LOG")
        log_layout = QVBoxLayout(logs)
        self.server_log = QTextEdit()
        self.server_log.setReadOnly(True)
        self.server_log.setFont(QFont("DejaVu Sans Mono", 10))
        self.server_log.setPlainText("[READY] Configure the server and click Start server.\n")
        log_layout.addWidget(self.server_log)
        main.addWidget(logs, stretch=1)
        warning = QLabel("Security: Share only the necessary folder. Do not expose port 8000 to the public Internet; use LAN or VPN.")
        warning.setWordWrap(True)
        main.addWidget(warning)
        return tab

    def show_about(self):
        QMessageBox.information(self, "About RetroTransfer 98",
                                "RetroTransfer 98 — Python TCP/TLS file manager\n"
                                "Encrypted transport • HMAC authentication • SHA-256 integrity\n"
                                "Interface inspired by Windows 95/98.")

    def local_go_path(self):
        """Navigate to a local folder; works with both Windows drive paths and Linux paths."""
        raw = self.local_current.text().strip().strip('"')
        target = Path(raw).expanduser()
        if target.is_file():
            self.source_edit.setText(str(target))
            target = target.parent
        if not target.is_dir():
            QMessageBox.warning(self, "Invalid folder", "The local folder could not be found: " + raw)
            return
        self.local_current.setText(str(target))
        self.local_tree.setRootIndex(self.local_model.index(str(target)))

    def local_drives(self):
        """Display the filesystem roots (C:, D:, USB drives on Windows)."""
        self.local_tree.setRootIndex(QModelIndex())
        self.local_current.setText("Computer / Drives")

    def local_up(self):
        index = self.local_tree.rootIndex()
        if not index.isValid():
            return
        folder = Path(self.local_model.filePath(index))
        parent = folder.parent
        if parent == folder:
            self.local_drives()
        else:
            self.local_current.setText(str(parent))
            self.local_tree.setRootIndex(self.local_model.index(str(parent)))

    def local_clicked(self, index: QModelIndex):
        path = self.local_model.filePath(index)
        if path:
            self.source_edit.setText(path)
            self.client_message.setText("Selected upload source: " + path)

    def local_double_clicked(self, index: QModelIndex):
        path = self.local_model.filePath(index)
        if path and self.local_model.isDir(index):
            self.local_current.setText(path)
            self.local_tree.setRootIndex(index)
        elif path:
            self.source_edit.setText(path)

    def pick_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose a file")
        if path:
            self.source_edit.setText(path)

    def pick_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Choose a folder to upload")
        if path:
            self.source_edit.setText(path)

    def pick_download_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Choose a download folder", self.download_folder.text())
        if path:
            self.download_folder.setText(path)

    def pick_share_root(self):
        path = QFileDialog.getExistingDirectory(self, "Choose a shared folder", self.share_root.text())
        if path:
            self.share_root.setText(path)

    def random_key(self):
        self.server_secret.setText(secrets.token_urlsafe(24))

    def use_local_server(self):
        """Fill the client tab with safe localhost connection settings."""
        if not self.server_worker or not self.server_fingerprint.text():
            return
        self.remote_host.setText("127.0.0.1")
        self.remote_port.setValue(self.server_worker.server.port)
        self.remote_secret.setText(self.server_secret.text())
        self.remote_fingerprint.setText(self.server_fingerprint.text())
        self.tabs.setCurrentIndex(0)
        self.refresh_remote()

    def copy_fingerprint(self):
        if self.server_fingerprint.text():
            QApplication.clipboard().setText(self.server_fingerprint.text())
            self.statusBar().showMessage("Fingerprint copied. Verify it and paste it into the client.")

    def start_server(self):
        if self.server_worker and self.server_worker.isRunning():
            return
        path = Path(self.share_root.text()).expanduser()
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "Directory error", str(exc))
            return
        if len(self.server_secret.text()) < 12:
            QMessageBox.warning(self, "Weak key", "The shared access key must contain at least 12 characters.")
            return
        self.server_worker = ServerWorker(str(path), self.server_secret.text(),
                                          self.bind_host.text().strip(), self.bind_port.value())
        self.server_worker.server_started.connect(self.server_online)
        self.server_worker.server_log.connect(self.server_log.append)
        self.server_worker.finished.connect(self.server_finished)
        self.server_fingerprint.clear()
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.server_status.setText("● STARTING")
        self.server_worker.start()

    def server_online(self, fingerprint: str, port: int):
        self.server_fingerprint.setText(fingerprint)
        self.server_secret.setReadOnly(True)
        self.new_key_button.setEnabled(False)
        self.share_root.setReadOnly(True)
        self.bind_host.setReadOnly(True)
        self.bind_port.setEnabled(False)
        self.local_connect_button.setEnabled(True)
        self.server_status.setText("● ONLINE / PORT " + str(port))
        self.server_status.setObjectName("online")
        self.server_status.style().unpolish(self.server_status)
        self.server_status.style().polish(self.server_status)
        self.statusBar().showMessage("SERVER ONLINE  |  Enter the server fingerprint and shared key on the client.")

    def stop_server(self):
        if self.server_worker:
            self.server_worker.stop()
            self.stop_button.setEnabled(False)
            self.server_status.setText("● STOPPING")

    def server_finished(self):
        self.start_button.setEnabled(True)
        self.server_secret.setReadOnly(False)
        self.new_key_button.setEnabled(True)
        self.share_root.setReadOnly(False)
        self.bind_host.setReadOnly(False)
        self.bind_port.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.local_connect_button.setEnabled(False)
        self.server_status.setText("● OFFLINE")
        self.server_status.setObjectName("offline")
        self.server_status.style().unpolish(self.server_status)
        self.server_status.style().polish(self.server_status)
        if self.server_worker and self.server_worker.server.failure:
            QMessageBox.warning(self, "Server error", str(self.server_worker.server.failure))

    def connection(self):
        return {"host": self.remote_host.text(), "port": self.remote_port.value(),
                "secret": self.remote_secret.text(), "fingerprint": self.remote_fingerprint.text()}

    def start_task(self, action: str, **kwargs):
        if self.worker and self.worker.isRunning():
            return
        self.worker = Worker(self.connection(), action, **kwargs)
        self.worker.result.connect(lambda value: self.task_success(action, value))
        self.worker.error.connect(self.task_error)
        self.worker.progress.connect(self.progress_update)
        self.worker.finished.connect(self.task_finished)
        for button in (self.upload_button, self.download_button, self.refresh_button, self.go_up):
            button.setEnabled(False)
        self.cancel_button.setEnabled(action != "list")
        self.client_message.setText("Running: " + action + " ...")
        self.worker.start()

    def task_finished(self):
        for button in (self.upload_button, self.download_button, self.refresh_button):
            button.setEnabled(True)
        self.go_up.setEnabled(bool(self.current_remote.text().strip().strip("/")))
        self.cancel_button.setEnabled(False)
        if self._needs_refresh:
            self._needs_refresh = False
            self.refresh_remote()

    def task_success(self, action: str, result: dict):
        if action == "list":
            self.file_list.clear()
            self.remote_entries = result.get("entries", [])
            style = self.style()
            for entry in self.remote_entries:
                label = ("[DIR]   " if entry["type"] == "dir" else "[FILE]  ") + entry["name"]
                item = QListWidgetItem(label)
                kind = (QStyle.StandardPixmap.SP_DirIcon if entry["type"] == "dir"
                        else QStyle.StandardPixmap.SP_FileIcon)
                item.setIcon(style.standardIcon(kind))
                item.setData(Qt.ItemDataRole.UserRole, entry)
                self.file_list.addItem(item)
            self.remote_folder.setText(self.current_remote.text())
            self.remote_hint.setText("This server folder is empty." if not self.remote_entries else "Double-click a folder to open it; click an item to select it for download.")
            self.go_up.setEnabled(bool(self.current_remote.text().strip().strip("/")))
            suffix = " (showing up to 1,000 items)" if result.get("truncated") else ""
            self.client_message.setText(f"Connected / {len(self.remote_entries)} items{suffix}")
        else:
            self.bar.setValue(100)
            self.client_message.setText(f"Completed {action}: {result.get('files', 0)} file(s), "
                                        f"{result.get('bytes', 0):,} bytes")
            self.statusBar().showMessage("TRANSFER COMPLETED  |  SHA-256 OK")
            if action == "upload":
                # Display where the file actually landed; previously uploading into
                # another folder could look like nothing had been sent.
                self.current_remote.setText(self.remote_folder.text().strip())
                self._needs_refresh = True

    def task_error(self, message: str):
        self.client_message.setText("Error: " + message)
        self.statusBar().showMessage("TRANSFER ERROR")
        QMessageBox.warning(self, "Transfer error", message)

    def progress_update(self, current: int, total: int):
        if total:
            self.bar.setValue(min(100, int(current * 100 / total)))
            self.client_message.setText(f"Transferred {current:,} / {total:,} bytes")
        else:
            self.bar.setValue(0)
            self.client_message.setText("Transferring an empty file or folder...")

    def refresh_remote(self):
        self.start_task("list", path=self.current_remote.text().strip())

    def up_remote(self):
        current = self.current_remote.text().strip().strip("/")
        parent = current.rsplit("/", 1)[0] if "/" in current else ""
        self.current_remote.setText(parent)
        self.refresh_remote()

    def open_remote_item(self, item: QListWidgetItem):
        entry = item.data(Qt.ItemDataRole.UserRole)
        if entry["type"] == "dir":
            base = self.current_remote.text().strip().strip("/")
            self.current_remote.setText((base + "/" if base else "") + entry["name"])
            self.refresh_remote()

    def upload(self):
        path = self.source_edit.text().strip()
        if not path or not Path(path).expanduser().exists():
            QMessageBox.warning(self, "No file", "Select a file or folder in Local Explorer, or click Choose file/folder.\n\nIf the path does not exist, check the local drives or connected USB storage.")
            return
        if not (Path(path).expanduser().is_file() or Path(path).expanduser().is_dir()):
            QMessageBox.warning(self, "Invalid source", "The selected source is not a file or directory.")
            return
        self.bar.setValue(0)
        remote_folder = self.remote_folder.text().strip()
        if ":" in remote_folder or "\\" in remote_folder or remote_folder.startswith("/"):
            QMessageBox.warning(self, "Remote path", "Upload into must be a RELATIVE path inside the server shared folder.\nFor example: docs/2026 or leave it blank. Do not use C:\\ or /home/.")
            return
        self.start_task("upload", source=str(Path(path).expanduser()), remote_folder=remote_folder)

    def download(self):
        item = self.file_list.currentItem()
        if item is None:
            QMessageBox.information(self, "Select item", "Select a file or folder from the remote file list.")
            return
        entry = item.data(Qt.ItemDataRole.UserRole)
        base = self.current_remote.text().strip().strip("/")
        remote_path = (base + "/" if base else "") + entry["name"]
        self.bar.setValue(0)
        self.start_task("download", remote_path=remote_path,
                        local_folder=self.download_folder.text().strip())

    def cancel_operation(self):
        if self.worker:
            self.worker.cancel()
            self.cancel_button.setEnabled(False)
            self.client_message.setText("Canceling the current transfer...")

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "Transfer running", "Cancel the active transfer or let it finish before exiting.")
            event.ignore()
            return
        if self.server_worker and self.server_worker.isRunning():
            self.server_worker.stop()
            self.server_worker.wait(3000)
        super().closeEvent(event)


def run():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(RETRO_STYLE)
    window = App()
    window.show()
    return app.exec()
