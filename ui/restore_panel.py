"""
ui/restore_panel.py
───────────────────
A single "Restore" screen that auto-detects the backup type when the user
picks a file, then shows only the fields that are relevant.

Flow:
  1. User picks a backup file via the browse button.
  2. backup_detector.detect() inspects the file bytes.
  3. A badge ("Logical backup" / "Physical backup" / "Unknown") appears.
  4. The matching field section slides into view:
       • Logical  →  connection + database name
       • Physical →  connection + data directory  (auto-filled via pg_finder)
       • Unknown  →  manual type selector + both sets of fields
  5. User hits "Restore" — the correct restore class is invoked.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThread, QObject, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QFileDialog, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QRadioButton,
    QVBoxLayout, QWidget,
)

from ui.widgets import (
    BasePanel, ConnectionGroup, hint_card,
    labelled, path_row, section_header,
)
from utils.backup_detector import BackupInfo, BackupKind, detect
from utils.logical_restore import LogicalRestore
from utils.physical_restore import PhysicalRestore
from utils import pg_finder


# ──────────────────────────────────────────────────────────────
#  Background worker — data dir detection (non-blocking)
# ──────────────────────────────────────────────────────────────

class _DataDirWorker(QObject):
    """Runs pg_finder.find_data_directory() in a thread so the UI stays responsive."""
    found = Signal(str)   # emits the path string, or "" if not found

    def run(self):
        result = pg_finder.find_data_directory()
        self.found.emit(str(result) if result else "")


# ──────────────────────────────────────────────────────────────
#  Restore Panel
# ──────────────────────────────────────────────────────────────

class RestorePanel(BasePanel):

    def __init__(self):
        super().__init__()

        self._data_dir_thread: Optional[QThread] = None
        self._data_dir_worker: Optional[_DataDirWorker] = None

        # ── header ──
        self.header_layout.addWidget(
            section_header(
                "Restore",
                "Select a backup file — the app will figure out the rest automatically.",
            )
        )

        cl = self.content_layout

        # ── file picker (always visible) ──
        file_group = QGroupBox("SELECT YOUR BACKUP FILE")
        fg_inner = QVBoxLayout(file_group)
        fg_inner.setSpacing(10)

        pick_row = QHBoxLayout()
        pick_row.setSpacing(10)
        self.file_edit = QLineEdit()
        self.file_edit.setObjectName("path_input")
        self.file_edit.setPlaceholderText(
            "Browse for your backup file  (.dump / .backup / .tar.gz / …)"
        )
        self.file_edit.setReadOnly(False)

        browse_btn = QPushButton("Browse …")
        browse_btn.setObjectName("btn_browse")
        browse_btn.setFixedWidth(90)
        browse_btn.clicked.connect(self._browse_file)
        self.file_edit.textChanged.connect(self._on_file_changed)

        pick_row.addWidget(self.file_edit, 1)
        pick_row.addWidget(browse_btn)
        fg_inner.addLayout(pick_row)

        # detection badge row
        badge_row = QHBoxLayout()
        badge_row.setSpacing(10)
        badge_lbl = QLabel("Detected type:")
        badge_lbl.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self._badge = QLabel("—")
        self._badge.setObjectName("badge_unknown")
        badge_row.addWidget(badge_lbl)
        badge_row.addWidget(self._badge)
        badge_row.addStretch()
        fg_inner.addLayout(badge_row)

        self._detect_desc = QLabel("")
        self._detect_desc.setObjectName("hint_body")
        self._detect_desc.setWordWrap(True)
        self._detect_desc.setVisible(False)
        fg_inner.addWidget(self._detect_desc)

        cl.addWidget(file_group)

        # ── manual override (shown only when type is UNKNOWN) ──
        self._override_group = QGroupBox("SELECT RESTORE TYPE MANUALLY")
        ov_inner = QVBoxLayout(self._override_group)
        self._radio_logical  = QRadioButton("Restore a single database  (pg_restore)")
        self._radio_physical = QRadioButton("Restore the full server  (extract tar archive)")
        self._radio_logical.setChecked(True)
        self._radio_logical.toggled.connect(self._refresh_fields)
        ov_inner.addWidget(self._radio_logical)
        ov_inner.addWidget(self._radio_physical)
        self._override_group.setVisible(False)
        cl.addWidget(self._override_group)

        # ── logical fields ──
        self._logical_group = QGroupBox("RESTORE INTO WHICH DATABASE?")
        lg_inner = QVBoxLayout(self._logical_group)
        lg_inner.setSpacing(10)

        self.conn_logical = ConnectionGroup(show_db=True)
        lg_inner.addWidget(self.conn_logical)
        lg_inner.addWidget(
            hint_card(
                "ℹ  What happens",
                "The backup data will be loaded into the database you specify. "
                "The database must already exist on the server. "
                "Existing data in that database will be replaced.",
            )
        )
        self._logical_group.setVisible(False)
        cl.addWidget(self._logical_group)

        # ── physical fields ──
        self._physical_group = QGroupBox("RESTORE TO SERVER DATA DIRECTORY")
        pg_inner = QVBoxLayout(self._physical_group)
        pg_inner.setSpacing(10)

        self.conn_physical = ConnectionGroup(show_db=False)
        pg_inner.addWidget(self.conn_physical)

        # Data directory header row with live status label
        data_dir_label_row = QHBoxLayout()
        data_dir_title = QLabel("DATA DIRECTORY")
        data_dir_title.setStyleSheet(
            "color: #a0c0e8; font-weight: 700; font-size: 11px; letter-spacing: 1px;"
        )
        self._data_dir_status_lbl = QLabel("  Detecting…")
        self._data_dir_status_lbl.setObjectName("hint_body")
        data_dir_label_row.addWidget(data_dir_title)
        data_dir_label_row.addWidget(self._data_dir_status_lbl)
        data_dir_label_row.addStretch()
        pg_inner.addLayout(data_dir_label_row)

        # Path edit + browse + rescan
        data_path_row = QHBoxLayout()
        data_path_row.setSpacing(10)
        self.data_dir_edit = QLineEdit()
        self.data_dir_edit.setObjectName("path_input")
        self.data_dir_edit.setPlaceholderText(
            "e.g.  C:\\Program Files\\PostgreSQL\\16\\data"
        )
        self.data_dir_edit.textChanged.connect(self._on_data_dir_changed)

        data_browse_btn = QPushButton("…")
        data_browse_btn.setObjectName("btn_browse")
        data_browse_btn.setFixedWidth(40)
        data_browse_btn.setToolTip("Browse for data directory")
        data_browse_btn.clicked.connect(self._browse_data_dir)

        rescan_btn = QPushButton("↺ Re-scan")
        rescan_btn.setObjectName("btn_browse")
        rescan_btn.setFixedWidth(80)
        rescan_btn.setToolTip("Try to auto-detect the data directory again")
        rescan_btn.clicked.connect(self._start_data_dir_detection)

        data_path_row.addWidget(self.data_dir_edit, 1)
        data_path_row.addWidget(data_browse_btn)
        data_path_row.addWidget(rescan_btn)
        pg_inner.addLayout(data_path_row)

        pg_inner.addWidget(
            hint_card(
                "⚠  Stop PostgreSQL first",
                "PostgreSQL must NOT be running when you perform a full server restore. "
                "Stop the service (services.msc → postgresql-x64-16) before clicking Restore. "
                "The data directory must be empty.",
            )
        )
        self._physical_group.setVisible(False)
        cl.addWidget(self._physical_group)

        # internal state
        self._detected: Optional[BackupInfo] = None
        self._logical_worker: Optional[LogicalRestore]  = None
        self._physical_worker: Optional[PhysicalRestore] = None

        self.run_btn.setText("RESTORE")

        # Kick off data dir detection immediately in the background
        self._start_data_dir_detection()

    # ── data directory detection ─────────────────────────────

    def _is_thread_running(self) -> bool:
        """
        Safely check whether the detection thread is still alive.
        Qt deletes the C++ object when the thread finishes and
        deleteLater() fires, so we must guard against the stale reference.
        """
        if self._data_dir_thread is None:
            return False
        try:
            return self._data_dir_thread.isRunning()
        except RuntimeError:
            # C++ object already deleted — treat as not running and clear ref
            self._data_dir_thread = None
            self._data_dir_worker = None
            return False

    def _start_data_dir_detection(self):
        """Launch a background thread to find the PostgreSQL data directory."""
        if self._is_thread_running():
            return

        self._data_dir_status_lbl.setText("  Detecting…")
        self._data_dir_status_lbl.setStyleSheet("color: #5a7aaa; font-size: 11px;")

        self._data_dir_thread = QThread()
        self._data_dir_worker = _DataDirWorker()
        self._data_dir_worker.moveToThread(self._data_dir_thread)

        self._data_dir_thread.started.connect(self._data_dir_worker.run)
        self._data_dir_worker.found.connect(self._on_data_dir_detected)
        self._data_dir_worker.found.connect(self._data_dir_thread.quit)

        # deleteLater cleans up the C++ object; we clear our Python refs in the
        # slot so _is_thread_running() never sees a dangling pointer again.
        self._data_dir_thread.finished.connect(self._data_dir_thread.deleteLater)
        self._data_dir_thread.finished.connect(self._on_thread_done)

        self._data_dir_thread.start()

    def _on_thread_done(self):
        """Clear Python references after Qt has deleted the C++ thread object."""
        self._data_dir_thread = None
        self._data_dir_worker = None

    def _on_data_dir_detected(self, path: str):
        if path:
            # Only auto-fill if the user hasn't already typed something
            if not self.data_dir_edit.text().strip():
                self.data_dir_edit.setText(path)
            self._data_dir_status_lbl.setText("  ✓ Auto-detected")
            self._data_dir_status_lbl.setStyleSheet("color: #4aaa70; font-size: 11px;")
        else:
            self._data_dir_status_lbl.setText("  Not found — browse manually")
            self._data_dir_status_lbl.setStyleSheet("color: #d4aa40; font-size: 11px;")

    def _on_data_dir_changed(self, text: str):
        """Validate the path live as the user types."""
        p = Path(text.strip()) if text.strip() else None
        if p and (p / "PG_VERSION").exists():
            self._data_dir_status_lbl.setText("  ✓ Valid data directory")
            self._data_dir_status_lbl.setStyleSheet("color: #4aaa70; font-size: 11px;")
        elif p and p.exists():
            self._data_dir_status_lbl.setText("  ⚠ Exists but PG_VERSION not found")
            self._data_dir_status_lbl.setStyleSheet("color: #d4aa40; font-size: 11px;")
        elif text.strip():
            self._data_dir_status_lbl.setText("  ✗ Path does not exist")
            self._data_dir_status_lbl.setStyleSheet("color: #f05070; font-size: 11px;")
        else:
            self._data_dir_status_lbl.setText("")

    def _browse_data_dir(self):
        chosen = QFileDialog.getExistingDirectory(self, "Select PostgreSQL data directory")
        if chosen:
            self.data_dir_edit.setText(chosen)

    # ── file browsing & detection ────────────────────────────

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select backup file",
            "",
            "Backup files (*.dump *.backup *.pgdump *.tar *.gz *.tgz *.sql);;All files (*)",
        )
        if path:
            self.file_edit.setText(path)

    def _on_file_changed(self, text: str):
        p = text.strip()
        if not p or not Path(p).exists():
            self._clear_detection()
            return
        info = detect(p)
        self._apply_detection(info)

    def _clear_detection(self):
        self._detected = None
        self._badge.setText("—")
        self._badge.setObjectName("badge_unknown")
        self._badge.style().unpolish(self._badge)
        self._badge.style().polish(self._badge)
        self._detect_desc.setVisible(False)
        self._override_group.setVisible(False)
        self._logical_group.setVisible(False)
        self._physical_group.setVisible(False)

    def _apply_detection(self, info: BackupInfo):
        self._detected = info

        if info.kind == BackupKind.LOGICAL:
            self._badge.setText("  LOGICAL BACKUP  ")
            self._badge.setObjectName("badge_logical")
        elif info.kind == BackupKind.PHYSICAL:
            self._badge.setText("  PHYSICAL BACKUP  ")
            self._badge.setObjectName("badge_physical")
        else:
            self._badge.setText("  UNKNOWN — CHOOSE BELOW  ")
            self._badge.setObjectName("badge_unknown")
        self._badge.style().unpolish(self._badge)
        self._badge.style().polish(self._badge)

        self._detect_desc.setText(info.description)
        self._detect_desc.setVisible(True)
        self._override_group.setVisible(info.kind == BackupKind.UNKNOWN)
        self._refresh_fields()

    def _refresh_fields(self):
        if self._detected is None:
            return
        if self._detected.kind == BackupKind.LOGICAL:
            show_logical, show_physical = True, False
        elif self._detected.kind == BackupKind.PHYSICAL:
            show_logical, show_physical = False, True
        else:
            show_logical  = self._radio_logical.isChecked()
            show_physical = not show_logical
        self._logical_group.setVisible(show_logical)
        self._physical_group.setVisible(show_physical)

    # ── effective restore type ───────────────────────────────

    def _effective_kind(self) -> BackupKind:
        if self._detected is None:
            return BackupKind.UNKNOWN
        if self._detected.kind != BackupKind.UNKNOWN:
            return self._detected.kind
        return BackupKind.LOGICAL if self._radio_logical.isChecked() else BackupKind.PHYSICAL

    # ── run ──────────────────────────────────────────────────

    def _run(self):
        src = self.file_edit.text().strip()
        if not src:
            self._set_status("Please select a backup file first.", "error")
            return
        if not Path(src).exists():
            self._set_status("The selected file was not found.", "error")
            return
        if self._detected is None:
            self._set_status("Please wait — detecting backup type …", "running")
            return

        kind = self._effective_kind()
        if kind == BackupKind.LOGICAL:
            self._run_logical(src)
        elif kind == BackupKind.PHYSICAL:
            self._run_physical(src)
        else:
            self._set_status("Cannot determine backup type. Please select manually.", "error")

    def _run_logical(self, src: str):
        vals = self.conn_logical.values()
        if not vals["db"]:
            self._set_status("Please enter the target database name.", "error")
            return

        self.log.clear_log()
        self.log.append_line(f"Restoring  '{src}'  →  database '{vals['db']}'")
        self._set_status("Restore in progress …", "running")
        self._set_busy(True)

        self._logical_worker = LogicalRestore(db_name=vals["db"], input_path=src)
        self._logical_worker.host     = vals["host"]
        self._logical_worker.port     = vals["port"]
        self._logical_worker.user     = vals["user"]
        self._logical_worker.password = vals["password"]

        self._connect_worker(
            self._logical_worker,
            on_finished=lambda code: self._set_status(
                "✓  Restore complete!" if code == 0
                else f"Restore failed (exit code {code}).",
                "ok" if code == 0 else "error",
            ),
        )
        self._logical_worker.restore()

    def _run_physical(self, src: str):
        data_dir = self.data_dir_edit.text().strip()
        if not data_dir:
            self._set_status("Please enter the PostgreSQL data directory path.", "error")
            return

        vals = self.conn_physical.values()
        self.log.clear_log()
        self.log.append_line(f"Restoring server backup  '{src}'  →  '{data_dir}'")
        self._set_status("Full server restore in progress …", "running")
        self._set_busy(True)

        self._physical_worker = PhysicalRestore(
            backup_path=src,
            data_dir=data_dir,
            host=vals["host"],
            port=vals["port"],
            user=vals["user"],
        )

        self._connect_worker(
            self._physical_worker,
            on_finished=lambda code: self._set_status(
                "✓  Restore complete! Start PostgreSQL to bring the server back online."
                if code == 0
                else f"Restore failed (exit code {code}).",
                "ok" if code == 0 else "error",
            ),
        )
        self._physical_worker.restore()

    # ── cancel ───────────────────────────────────────────────

    def _cancel(self):
        for w in (self._logical_worker, self._physical_worker):
            if w and hasattr(w, "process"):
                try:
                    w.process.kill()
                except Exception:
                    pass
            if w and hasattr(w, "cancel"):
                try:
                    w.cancel()
                except Exception:
                    pass
        self._set_status("Cancelled.", "error")
        self._set_busy(False)