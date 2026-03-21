"""
ui/settings_panel.py
─────────────────────
Settings screen that shows auto-detected PostgreSQL binary paths and lets
the user override them by browsing manually.

Layout:

  ┌─────────────────────────────────────────────────────────────┐
  │  PostgreSQL Binaries                                        │
  │                                                             │
  │  pg_dump        [ /usr/bin/pg_dump              ] [Browse]  │
  │  pg_restore     [ /usr/bin/pg_restore           ] [Browse]  │
  │  pg_basebackup  [ Not found — browse manually   ] [Browse]  │
  │                                                             │
  │  [ 🔍 Re-scan ]                              [ ✓ Apply ]    │
  └─────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from ui.widgets import BasePanel, hint_card, section_header
from utils import pg_finder


# ── one row per binary ────────────────────────────────────────

class _BinaryRow(QWidget):
    """Label  +  path edit  +  browse button  +  status dot."""

    _DOT_OK  = "●"
    _DOT_ERR = "●"

    def __init__(self, binary: str):
        super().__init__()
        self.binary = binary

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        # name label
        name_lbl = QLabel(binary)
        name_lbl.setFixedWidth(130)
        name_lbl.setStyleSheet(
            "color: #a0c0e8; font-size: 12px; font-weight: 700; letter-spacing: 1px;"
        )
        row.addWidget(name_lbl)

        # editable path
        self.edit = QLineEdit()
        self.edit.setObjectName("path_input")
        self.edit.setPlaceholderText("Not found — browse to set manually")
        self.edit.textChanged.connect(self._on_text_changed)
        row.addWidget(self.edit, 1)

        # browse button
        browse_btn = QPushButton("Browse …")
        browse_btn.setObjectName("btn_browse")
        browse_btn.setFixedWidth(90)
        browse_btn.clicked.connect(self._browse)
        row.addWidget(browse_btn)

        # status indicator
        self._dot = QLabel(self._DOT_ERR)
        self._dot.setFixedWidth(18)
        self._dot.setAlignment(Qt.AlignCenter)
        row.addWidget(self._dot)

        self.refresh()

    # ── helpers ──────────────────────────────────────────────

    def refresh(self):
        """Pull the current cached value from pg_finder and update UI."""
        p = pg_finder.find(self.binary)
        if p:
            self.edit.setText(str(p))
        else:
            self.edit.clear()
        self._update_dot(bool(p))

    def _update_dot(self, ok: bool):
        if ok:
            self._dot.setText(self._DOT_OK)
            self._dot.setStyleSheet("color: #4aaa70; font-size: 14px;")
            self._dot.setToolTip("Binary found ✓")
        else:
            self._dot.setText(self._DOT_ERR)
            self._dot.setStyleSheet("color: #f05070; font-size: 14px;")
            self._dot.setToolTip("Binary not found")

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Locate {self.binary}",
            "",
            "Executables (*)" if True else "All files (*)",
        )
        if path:
            self.edit.setText(path)

    def _on_text_changed(self, text: str):
        exists = Path(text.strip()).is_file() if text.strip() else False
        self._update_dot(exists)

    def apply(self):
        """Push the current edit value into pg_finder's cache."""
        text = self.edit.text().strip()
        pg_finder.set_override(self.binary, text if text else None)


# ── Settings Panel ───────────────────────────────────────────

class SettingsPanel(BasePanel):

    def __init__(self):
        super().__init__()

        # hide the run/cancel buttons — we have our own footer
        self.run_btn.hide()
        self.cancel_btn.hide()
        self.progress_bar.hide()
        self.status_lbl.hide()
        self.log.parent().hide()          # hide log group

        # ── header ──
        self.header_layout.addWidget(
            section_header(
                "Settings",
                "Configure the paths to PostgreSQL command-line tools.",
            )
        )

        cl = self.content_layout

        cl.addWidget(
            hint_card(
                "ℹ  Why this matters",
                "PGSafe calls pg_dump, pg_restore, and pg_basebackup to do its work. "
                "On Windows these are not usually on your PATH. "
                "If a binary shows a red dot below, click Browse to locate it inside "
                "your PostgreSQL installation folder (usually under C:\\Program Files\\PostgreSQL\\<version>\\bin).",
            )
        )

        # ── binary rows ──
        bin_group = QGroupBox("POSTGRESQL BINARY PATHS")
        bg_inner = QVBoxLayout(bin_group)
        bg_inner.setSpacing(10)

        self._rows: list[_BinaryRow] = []
        for binary in pg_finder.BINARIES:
            row_widget = _BinaryRow(binary)
            bg_inner.addWidget(row_widget)
            self._rows.append(row_widget)

        cl.addWidget(bin_group)
        cl.addStretch()

        # ── footer buttons ──
        footer = QHBoxLayout()
        footer.setSpacing(12)

        rescan_btn = QPushButton("🔍  RE-SCAN")
        rescan_btn.setToolTip("Search common install paths again")
        rescan_btn.clicked.connect(self._rescan)

        apply_btn = QPushButton("✓  APPLY")
        apply_btn.setObjectName("btn_primary")
        apply_btn.clicked.connect(self._apply)

        footer.addStretch()
        footer.addWidget(rescan_btn)
        footer.addWidget(apply_btn)
        self.content_layout.addLayout(footer)

    # ── actions ──────────────────────────────────────────────

    def _rescan(self):
        pg_finder.clear_cache()
        for row in self._rows:
            row.refresh()

    def _apply(self):
        for row in self._rows:
            row.apply()

    # BasePanel abstract stubs (not used here)
    def _run(self):    pass
    def _cancel(self): pass