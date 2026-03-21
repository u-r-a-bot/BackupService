"""
ui/widgets.py
─────────────
Reusable building blocks shared by every panel:
  • helper functions  (make_divider, section_header, hint_card, labelled, path_row)
  • LogWidget         — coloured terminal-style output box
  • ConnectionGroup   — host / port / user / password / database inputs
  • CloudGroup        — optional Google Drive upload section
  • BasePanel         — abstract base for all operation panels
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QFrame, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QProgressBar, QPushButton, QScrollArea,
    QTextEdit, QVBoxLayout, QWidget,
)

from utils.google_auth import CloudBackup


# ──────────────────────────────────────────────────────────────
#  Layout / widget helpers
# ──────────────────────────────────────────────────────────────

def make_divider() -> QFrame:
    f = QFrame()
    f.setObjectName("divider")
    f.setFrameShape(QFrame.HLine)
    return f


def section_header(title: str, subtitle: str = "") -> QWidget:
    """Big title + optional muted subtitle row."""
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(3)

    t = QLabel(title)
    t.setObjectName("section_title")
    v.addWidget(t)

    if subtitle:
        s = QLabel(subtitle)
        s.setObjectName("section_subtitle")
        s.setWordWrap(True)
        v.addWidget(s)

    return w


def hint_card(title: str, body: str) -> QFrame:
    """Friendly blue info card shown to naive users."""
    card = QFrame()
    card.setObjectName("hint_card")
    lay = QVBoxLayout(card)
    lay.setContentsMargins(14, 12, 14, 12)
    lay.setSpacing(4)

    t = QLabel(title)
    t.setObjectName("hint_title")
    lay.addWidget(t)

    b = QLabel(body)
    b.setObjectName("hint_body")
    b.setWordWrap(True)
    lay.addWidget(b)

    return card


def labelled(label_text: str, widget: QWidget, label_width: int = 110) -> QHBoxLayout:
    lbl = QLabel(label_text.upper())
    lbl.setMinimumWidth(label_width)
    lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    row = QHBoxLayout()
    row.setSpacing(10)
    row.addWidget(lbl)
    row.addWidget(widget)
    return row


def path_row(
    label_text: str,
    placeholder: str,
    is_dir: bool = False,
    is_save: bool = False,
) -> tuple[QHBoxLayout, QLineEdit]:
    """A label + line-edit + browse button row for file/dir picking."""
    edit = QLineEdit()
    edit.setObjectName("path_input")
    edit.setPlaceholderText(placeholder)

    btn = QPushButton("…")
    btn.setObjectName("btn_browse")
    btn.setFixedWidth(40)
    btn.setToolTip(f"Browse for {label_text}")

    def _browse():
        if is_dir:
            chosen = QFileDialog.getExistingDirectory(None, label_text)
        elif is_save:
            chosen, _ = QFileDialog.getSaveFileName(None, label_text)
        else:
            chosen, _ = QFileDialog.getOpenFileName(None, label_text)
        if chosen:
            edit.setText(chosen)

    btn.clicked.connect(_browse)

    lbl = QLabel(label_text.upper())
    lbl.setMinimumWidth(110)
    lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

    row = QHBoxLayout()
    row.setSpacing(10)
    row.addWidget(lbl)
    row.addWidget(edit, 1)
    row.addWidget(btn)
    return row, edit


# ──────────────────────────────────────────────────────────────
#  LogWidget  –  coloured terminal output
# ──────────────────────────────────────────────────────────────

class LogWidget(QTextEdit):
    def __init__(self):
        super().__init__()
        self.setObjectName("log_output")
        self.setReadOnly(True)
        self.setMinimumHeight(160)

    def append_line(self, text: str):
        text = text.strip()
        if not text:
            return
        lower = text.lower()
        if lower.startswith("error") or "fatal" in lower or "failed" in lower or "could not" in lower:
            color = "#f05070"
        elif "complete" in lower or "success" in lower or "finished" in lower:
            color = "#4aaa70"
        elif "%" in text or "upload" in lower or "progress" in lower:
            color = "#5b9cf6"
        elif "compres" in lower or "extract" in lower or "writing" in lower:
            color = "#e0a84a"
        elif lower.startswith("warning") or "warn" in lower:
            color = "#d4aa40"
        else:
            color = "#c9d1e0"

        safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.append(f'<span style="color:{color};">{safe}</span>')
        self.moveCursor(QTextCursor.End)

    def clear_log(self):
        self.clear()


# ──────────────────────────────────────────────────────────────
#  ConnectionGroup  –  host / port / user / password / database
# ──────────────────────────────────────────────────────────────

class ConnectionGroup(QGroupBox):
    def __init__(self, show_db: bool = True):
        super().__init__("DATABASE CONNECTION")
        self._show_db = show_db
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ── Row 1: HOST + PORT ──
        self.host_edit = QLineEdit("localhost")
        self.host_edit.setToolTip("PostgreSQL server hostname or IP")
        self.port_edit = QLineEdit("5432")
        self.port_edit.setFixedWidth(80)
        self.port_edit.setToolTip("PostgreSQL port (default: 5432)")

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        for lbl_txt, w in [("HOST", self.host_edit), ("PORT", self.port_edit)]:
            lbl = QLabel(lbl_txt)
            lbl.setMinimumWidth(50)
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row1.addWidget(lbl)
            row1.addWidget(w)
            row1.addSpacing(8)
        row1.addStretch()
        layout.addLayout(row1)

        # ── Row 2: USER + DATABASE (if show_db) ──
        self.user_edit = QLineEdit("postgres")
        self.user_edit.setToolTip("PostgreSQL superuser name")
        self.db_edit = QLineEdit()
        self.db_edit.setPlaceholderText("e.g.  my_database")
        self.db_edit.setToolTip("The database to backup or restore into")

        if show_db:
            row2 = QHBoxLayout()
            row2.setSpacing(10)
            for lbl_txt, w in [("USER", self.user_edit), ("DATABASE", self.db_edit)]:
                lbl = QLabel(lbl_txt)
                lbl.setMinimumWidth(70)
                lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                row2.addWidget(lbl)
                row2.addWidget(w)
                row2.addSpacing(8)
            row2.addStretch()
            layout.addLayout(row2)
        else:
            layout.addLayout(labelled("USER", self.user_edit))

        # ── Row 3: PASSWORD ──
        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("Leave blank if no password is set")
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setToolTip("PostgreSQL user password (passed via PGPASSWORD)")

        pw_row = QHBoxLayout()
        pw_row.setSpacing(10)
        pw_lbl = QLabel("PASSWORD")
        pw_lbl.setMinimumWidth(70)
        pw_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # Eye toggle button to show/hide password
        self._pw_visible = False
        self._eye_btn = QPushButton("👁")
        self._eye_btn.setObjectName("btn_browse")
        self._eye_btn.setFixedWidth(40)
        self._eye_btn.setToolTip("Show / hide password")
        self._eye_btn.clicked.connect(self._toggle_password_visibility)

        pw_row.addWidget(pw_lbl)
        pw_row.addWidget(self.password_edit, 1)
        pw_row.addWidget(self._eye_btn)
        pw_row.addSpacing(8)
        pw_row.addStretch()
        layout.addLayout(pw_row)

    def _toggle_password_visibility(self):
        self._pw_visible = not self._pw_visible
        self.password_edit.setEchoMode(
            QLineEdit.Normal if self._pw_visible else QLineEdit.Password
        )
        self._eye_btn.setText("🙈" if self._pw_visible else "👁")

    def values(self) -> dict:
        return {
            "host":     self.host_edit.text().strip() or "localhost",
            "port":     int(self.port_edit.text().strip() or 5432),
            "user":     self.user_edit.text().strip() or "postgres",
            "password": self.password_edit.text(),          # raw; passed as PGPASSWORD
            "db":       self.db_edit.text().strip() if self._show_db else "",
        }


# ──────────────────────────────────────────────────────────────
#  CloudGroup  –  optional Google Drive upload
# ──────────────────────────────────────────────────────────────

class CloudGroup(QGroupBox):
    def __init__(self):
        super().__init__("SAVE TO GOOGLE DRIVE  (OPTIONAL)")
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        self.enable_cb = QCheckBox("Automatically upload the backup to Google Drive when done")
        layout.addWidget(self.enable_cb)

        cred_row, self.cred_edit = path_row(
            "Credentials file",
            "Path to your service_account.json",
        )
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("Google Drive folder ID  (leave blank to upload to root)")
        folder_row = labelled("Folder ID", self.folder_edit)

        layout.addLayout(cred_row)
        layout.addLayout(folder_row)

        self._sub = [self.cred_edit, self.folder_edit]
        for w in self._sub:
            w.setEnabled(False)
        self.enable_cb.toggled.connect(lambda on: [w.setEnabled(on) for w in self._sub])

    @property
    def enabled(self) -> bool:
        return self.enable_cb.isChecked()

    def credentials(self):
        p = self.cred_edit.text().strip()
        if not p:
            return None
        pp = Path(p)
        if pp.suffix == ".json":
            with open(pp) as f:
                return json.load(f)
        return str(pp)

    def folder_id(self) -> Optional[str]:
        return self.folder_edit.text().strip() or None


# ──────────────────────────────────────────────────────────────
#  BasePanel  –  abstract base for every operation panel
# ──────────────────────────────────────────────────────────────

class BasePanel(QWidget):
    """
    Provides:
      • scrollable content area  (self.content_layout)
      • progress bar + status label
      • coloured log widget
      • Run / Cancel buttons
      • _set_busy / _set_status helpers
      • _connect_worker / _maybe_cloud_upload helpers
    """

    def __init__(self):
        super().__init__()
        self.setObjectName("panel")
        self._cloud: Optional[CloudBackup] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 20)
        outer.setSpacing(14)

        # ── header area ──
        self.header_layout = QVBoxLayout()
        self.header_layout.setSpacing(4)
        outer.addLayout(self.header_layout)
        outer.addWidget(make_divider())

        # ── scrollable config area ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content_host = QWidget()
        self.content_layout = QVBoxLayout(content_host)
        self.content_layout.setSpacing(12)
        self.content_layout.setContentsMargins(0, 4, 0, 4)
        scroll.setWidget(content_host)
        outer.addWidget(scroll, 1)

        # ── status + progress ──
        self.status_lbl = QLabel("")
        outer.addWidget(self.status_lbl)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        outer.addWidget(self.progress_bar)

        # ── log ──
        log_group = QGroupBox("ACTIVITY LOG")
        log_inner = QVBoxLayout(log_group)
        log_inner.setContentsMargins(6, 6, 6, 6)
        log_inner.setSpacing(6)
        self.log = LogWidget()
        log_inner.addWidget(self.log)
        clr = QPushButton("CLEAR LOG")
        clr.setFixedWidth(100)
        clr.clicked.connect(self.log.clear_log)
        log_inner.addWidget(clr, alignment=Qt.AlignRight)
        outer.addWidget(log_group)

        # ── action buttons ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        self.run_btn = QPushButton("RUN")
        self.run_btn.setObjectName("btn_primary")
        self.cancel_btn = QPushButton("CANCEL")
        self.cancel_btn.setObjectName("btn_danger")
        self.cancel_btn.setEnabled(False)
        btn_row.addStretch()
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.run_btn)
        outer.addLayout(btn_row)

        self.run_btn.clicked.connect(self._run)
        self.cancel_btn.clicked.connect(self._cancel)

    # ── status helpers ───────────────────────────────────────

    def _set_status(self, text: str, kind: str = "running"):
        names = {"running": "status_running", "ok": "status_ok", "error": "status_error"}
        self.status_lbl.setObjectName(names.get(kind, ""))
        self.status_lbl.setText(text)
        self.status_lbl.style().unpolish(self.status_lbl)
        self.status_lbl.style().polish(self.status_lbl)

    def _set_busy(self, busy: bool):
        self.run_btn.setEnabled(not busy)
        self.cancel_btn.setEnabled(busy)
        if not busy:
            self.progress_bar.setValue(0)

    # ── subclass interface ───────────────────────────────────

    def _run(self):    ...
    def _cancel(self): ...

    # ── worker wiring helper ─────────────────────────────────

    def _connect_worker(self, worker, on_finished=None):
        worker.output_ready.connect(self.log.append_line)
        worker.finished.connect(lambda *_: self._set_busy(False))
        if on_finished:
            worker.finished.connect(on_finished)
        if hasattr(worker, "progress"):
            worker.progress.connect(self.progress_bar.setValue)
        if hasattr(worker, "error"):
            worker.error.connect(lambda msg: self._set_status(msg, "error"))

    # ── optional cloud upload ────────────────────────────────

    def _maybe_cloud_upload(self, path: str, cloud_group: CloudGroup):
        if not cloud_group.enabled:
            return
        creds = cloud_group.credentials()
        if not creds:
            self.log.append_line("ERROR: Cloud upload enabled but no credentials file provided.")
            return
        self.log.append_line("── Starting Google Drive upload ──")
        self._cloud = CloudBackup(
            source=path,
            credentials=creds,
            folder_id=cloud_group.folder_id(),
        )
        self._cloud.output_ready.connect(self.log.append_line)
        self._cloud.progress.connect(self.progress_bar.setValue)
        self._cloud.finished.connect(
            lambda fid: self._set_status(f"✓  Uploaded to Drive — file ID: {fid}", "ok")
        )
        self._cloud.error.connect(
            lambda msg: self._set_status(msg, "error")
        )
        self._cloud.upload()
