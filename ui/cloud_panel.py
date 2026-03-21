"""
ui/cloud_panel.py
─────────────────
Standalone panel for uploading any file or directory to Google Drive.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import QGroupBox, QLineEdit, QVBoxLayout

from ui.widgets import (
    BasePanel, CloudGroup, hint_card, labelled,
    path_row, section_header,
)
from utils.google_auth import CloudBackup


class CloudPanel(BasePanel):

    def __init__(self):
        super().__init__()

        # ── header ──
        self.header_layout.addWidget(
            section_header(
                "Cloud Upload",
                "Upload any backup file or folder to Google Drive.",
            )
        )

        cl = self.content_layout

        cl.addWidget(
            hint_card(
                "ℹ  Google Service Account required",
                "You need a Google Cloud service account JSON key with access to Google Drive. "
                "Ask your administrator or follow Google's guide to create one.",
            )
        )

        # source
        src_group = QGroupBox("WHAT TO UPLOAD")
        sv = QVBoxLayout(src_group)
        src_row, self.src_edit = path_row(
            "File or folder",
            "Select the backup file or directory to upload",
        )
        sv.addLayout(src_row)
        cl.addWidget(src_group)

        # credentials
        cred_group = QGroupBox("GOOGLE DRIVE CREDENTIALS")
        cv = QVBoxLayout(cred_group)
        cred_row, self.cred_edit = path_row(
            "Service account key",
            "Path to service_account.json",
        )
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText(
            "Google Drive folder ID  (leave blank to upload to My Drive root)"
        )
        folder_row = labelled("Destination folder", self.folder_edit)
        cv.addLayout(cred_row)
        cv.addLayout(folder_row)
        cl.addWidget(cred_group)
        cl.addStretch()

        self._uploader: Optional[CloudBackup] = None
        self.run_btn.setText("UPLOAD TO DRIVE")

    def _run(self):
        src  = self.src_edit.text().strip()
        cred = self.cred_edit.text().strip()

        if not src:
            self._set_status("Please select a file or folder to upload.", "error")
            return
        if not Path(src).exists():
            self._set_status("The selected path does not exist.", "error")
            return
        if not cred:
            self._set_status("Please provide the service account credentials file.", "error")
            return

        creds_path = Path(cred)
        if creds_path.suffix == ".json":
            with open(creds_path) as f:
                credentials = json.load(f)
        else:
            credentials = str(creds_path)

        self.log.clear_log()
        self.log.append_line(f"Uploading  '{src}'  to Google Drive …")
        self._set_status("Upload in progress …", "running")
        self._set_busy(True)
        self.progress_bar.setValue(0)

        self._uploader = CloudBackup(
            source=src,
            credentials=credentials,
            folder_id=self.folder_edit.text().strip() or None,
        )
        self._uploader.output_ready.connect(self.log.append_line)
        self._uploader.progress.connect(self.progress_bar.setValue)
        self._uploader.finished.connect(self._on_upload_done)
        self._uploader.error.connect(self._on_upload_error)
        self._uploader.upload()

    def _on_upload_done(self, file_id: str):
        self._set_status(f"✓  Upload complete — Drive file ID: {file_id}", "ok")
        self._set_busy(False)

    def _on_upload_error(self, msg: str):
        self._set_status(msg, "error")
        self._set_busy(False)

    def _cancel(self):
        if self._uploader:
            self._uploader.cancel()
        self._set_status("Cancelled.", "error")
        self._set_busy(False)
