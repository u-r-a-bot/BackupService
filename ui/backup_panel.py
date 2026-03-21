"""
ui/backup_panel.py
──────────────────
A single "Backup" screen for naive users.

The user picks a backup *mode* using two clearly-labelled buttons:

  ┌──────────────────────────────────────────────────┐
  │  📄 Back up a specific database                  │
  │     Saves only one database. Easy to restore     │
  │     into any server. Best for most people.       │
  └──────────────────────────────────────────────────┘
  ┌──────────────────────────────────────────────────┐
  │  🗄  Back up the entire PostgreSQL server        │
  │     Saves everything — all databases, settings,  │
  │     users. Used for full server migrations.      │
  └──────────────────────────────────────────────────┘

The panel then shows only the fields that are relevant for the chosen mode.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from ui.widgets import (
    BasePanel, CloudGroup, ConnectionGroup,
    hint_card, path_row, section_header,
)
from utils.logical_backup import LogicalBackup
from utils.physical_backup import PhysicalBackup


# ──────────────────────────────────────────────────────────────
#  Mode selector card
# ──────────────────────────────────────────────────────────────

class _ModeCard(QPushButton):
    def __init__(self, icon: str, title: str, description: str):
        super().__init__()
        self.setObjectName("mode_btn")
        self.setCheckable(False)
        self.setProperty("selected", "false")
        self.setMinimumHeight(72)

        inner = QVBoxLayout(self)
        inner.setContentsMargins(14, 10, 14, 10)
        inner.setSpacing(3)

        top = QHBoxLayout()
        top.setSpacing(8)
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("font-size: 18px;")
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            "color: #a0c0e8; font-size: 13px; font-weight: 700; letter-spacing: 0px;"
        )
        top.addWidget(icon_lbl)
        top.addWidget(title_lbl)
        top.addStretch()
        inner.addLayout(top)

        desc_lbl = QLabel(description)
        desc_lbl.setStyleSheet(
            "color: #4a6a94; font-size: 11px; letter-spacing: 0px;"
        )
        desc_lbl.setWordWrap(True)
        inner.addWidget(desc_lbl)

    def set_selected(self, on: bool):
        self.setProperty("selected", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)


# ──────────────────────────────────────────────────────────────
#  Backup Panel
# ──────────────────────────────────────────────────────────────

class BackupPanel(BasePanel):

    MODE_LOGICAL  = "logical"
    MODE_PHYSICAL = "physical"

    def __init__(self):
        super().__init__()

        # ── header ──
        self.header_layout.addWidget(
            section_header(
                "Backup",
                "Choose what you want to back up and where to save it.",
            )
        )

        cl = self.content_layout

        # ── mode chooser ──
        mode_group = QGroupBox("WHAT DO YOU WANT TO BACK UP?")
        mode_inner = QVBoxLayout(mode_group)
        mode_inner.setSpacing(8)

        self._card_logical = _ModeCard(
            "📄",
            "A single database",
            "Saves one database to a single file. Quick, portable, and easy to restore. "
            "Best for most people.",
        )
        self._card_physical = _ModeCard(
            "🗄",
            "The entire PostgreSQL server",
            "Takes a full snapshot of every database, user, and server setting. "
            "Needed when migrating a whole server or setting up a standby replica.",
        )

        mode_inner.addWidget(self._card_logical)
        mode_inner.addWidget(self._card_physical)
        cl.addWidget(mode_group)

        self._card_logical.clicked.connect(lambda: self._set_mode(self.MODE_LOGICAL))
        self._card_physical.clicked.connect(lambda: self._set_mode(self.MODE_PHYSICAL))

        # ── logical fields ──
        self._logical_widget = QWidget()
        lv = QVBoxLayout(self._logical_widget)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(10)

        self.conn = ConnectionGroup(show_db=True)
        lv.addWidget(self.conn)

        out_group = QGroupBox("WHERE TO SAVE THE BACKUP FILE")
        out_inner = QVBoxLayout(out_group)
        out_row, self.logical_out_edit = path_row(
            "Save to",
            "e.g.  /backups/mydb_2024.dump",
            is_save=True,
        )
        out_inner.addLayout(out_row)
        lv.addWidget(out_group)

        self.logical_cloud = CloudGroup()
        lv.addWidget(self.logical_cloud)
        cl.addWidget(self._logical_widget)

        # ── physical fields ──
        self._physical_widget = QWidget()
        pv = QVBoxLayout(self._physical_widget)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(10)

        pv.addWidget(
            hint_card(
                "ℹ  Full server backup",
                "This requires pg_basebackup and a replication-enabled PostgreSQL user. "
                "The output folder must be empty or not yet created. "
                "PostgreSQL must be running during the backup.",
            )
        )

        self.phys_conn = ConnectionGroup(show_db=False)
        pv.addWidget(self.phys_conn)

        phys_out_group = QGroupBox("WHERE TO SAVE THE BACKUP")
        phys_out_inner = QVBoxLayout(phys_out_group)
        phys_out_row, self.physical_out_edit = path_row(
            "Output folder",
            "e.g.  /backups/server_snapshot",
            is_dir=True,
        )
        phys_out_inner.addLayout(phys_out_row)
        pv.addWidget(phys_out_group)

        self.physical_cloud = CloudGroup()
        pv.addWidget(self.physical_cloud)
        cl.addWidget(self._physical_widget)

        # default mode
        self._mode: str = self.MODE_LOGICAL
        self._set_mode(self.MODE_LOGICAL)

        # workers
        self._logical_worker: Optional[LogicalBackup] = None
        self._physical_worker: Optional[PhysicalBackup] = None

        self.run_btn.setText("START BACKUP")

    # ── mode switching ───────────────────────────────────────

    def _set_mode(self, mode: str):
        self._mode = mode
        self._card_logical.set_selected(mode == self.MODE_LOGICAL)
        self._card_physical.set_selected(mode == self.MODE_PHYSICAL)
        self._logical_widget.setVisible(mode == self.MODE_LOGICAL)
        self._physical_widget.setVisible(mode == self.MODE_PHYSICAL)

    # ── run ──────────────────────────────────────────────────

    def _run(self):
        if self._mode == self.MODE_LOGICAL:
            self._run_logical()
        else:
            self._run_physical()

    def _run_logical(self):
        vals = self.conn.values()
        if not vals["db"]:
            self._set_status("Please enter the database name.", "error")
            return
        out = self.logical_out_edit.text().strip()
        if not out:
            self._set_status("Please choose a location to save the backup file.", "error")
            return

        self.log.clear_log()
        self.log.append_line(f"Starting backup of database  '{vals['db']}'  →  {out}")
        self._set_status("Backup in progress …", "running")
        self._set_busy(True)

        self._logical_worker = LogicalBackup(db_name=vals["db"], output_path=out)
        self._logical_worker.host = vals["host"]
        self._logical_worker.port = vals["port"]
        self._logical_worker.user = vals["user"]

        def _done(code: int):
            if code == 0:
                self._set_status("✓  Backup complete!", "ok")
                self._maybe_cloud_upload(out, self.logical_cloud)
            else:
                self._set_status(f"Backup failed (exit code {code}).", "error")

        self._connect_worker(self._logical_worker, on_finished=_done)
        self._logical_worker.backup()

    def _run_physical(self):
        out = self.physical_out_edit.text().strip()
        if not out:
            self._set_status("Please choose an output folder.", "error")
            return

        vals = self.phys_conn.values()
        self.log.clear_log()
        self.log.append_line(f"Starting full server backup  →  {out}")
        self._set_status("Full server backup in progress …", "running")
        self._set_busy(True)

        self._physical_worker = PhysicalBackup(
            output_path=out,
            host=vals["host"],
            port=vals["port"],
            user=vals["user"],
        )

        def _done(code: int):
            if code == 0:
                self._set_status("✓  Server backup complete!", "ok")
                self._maybe_cloud_upload(out, self.physical_cloud)
            else:
                self._set_status(f"Backup failed (exit code {code}).", "error")

        self._connect_worker(self._physical_worker, on_finished=_done)
        self._physical_worker.backup()

    # ── cancel ───────────────────────────────────────────────

    def _cancel(self):
        for w in (self._logical_worker, self._physical_worker):
            if w and hasattr(w, "process"):
                try:
                    w.process.kill()
                except Exception:
                    pass
        if self._cloud:
            self._cloud.cancel()
        self._set_status("Cancelled.", "error")
        self._set_busy(False)
