"""
ui/main_window.py
─────────────────
Application shell:  sidebar navigation  +  stacked panel area.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMainWindow, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget,
)

from ui.backup_panel   import BackupPanel
from ui.cloud_panel    import CloudPanel
from ui.restore_panel  import RestorePanel
from ui.settings_panel import SettingsPanel
from ui.widgets        import make_divider


# ──────────────────────────────────────────────────────────────
#  Nav item  (sidebar button)
# ──────────────────────────────────────────────────────────────

class _NavButton(QPushButton):
    def __init__(self, icon: str, label: str):
        super().__init__(f"  {icon}  {label}")
        self.setObjectName("nav_btn")
        self._set_active(False)

    def _set_active(self, on: bool):
        self.setProperty("active", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)


# ──────────────────────────────────────────────────────────────
#  Main window
# ──────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):

    _PAGES = [
        ("💾", "Backup",       BackupPanel),
        ("⏪", "Restore",      RestorePanel),
        ("☁",  "Cloud Upload", CloudPanel),
        ("⚙",  "Settings",    SettingsPanel),
    ]

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PGSafe — PostgreSQL Backup Manager")
        self.setMinimumSize(900, 660)
        self.resize(1080, 720)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)

        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── sidebar ──────────────────────────────────────────
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sb = QVBoxLayout(sidebar)
        sb.setContentsMargins(0, 28, 0, 20)
        sb.setSpacing(0)

        # logo
        logo_wrap = QWidget()
        lw = QVBoxLayout(logo_wrap)
        lw.setContentsMargins(20, 0, 20, 26)
        lw.setSpacing(3)

        app_title = QLabel("PGSafe")
        app_title.setObjectName("app_title")
        app_sub   = QLabel("POSTGRESQL BACKUP")
        app_sub.setObjectName("app_subtitle")

        lw.addWidget(app_title)
        lw.addWidget(app_sub)
        sb.addWidget(logo_wrap)
        sb.addWidget(make_divider())
        sb.addSpacing(12)

        # nav buttons
        self._nav_buttons: list[_NavButton] = []
        self._stack = QStackedWidget()

        for icon, label, PanelClass in self._PAGES:
            panel = PanelClass()
            self._stack.addWidget(panel)

            btn = _NavButton(icon, label)
            idx = self._stack.count() - 1
            btn.clicked.connect(lambda _, i=idx: self._switch(i))
            sb.addWidget(btn)
            self._nav_buttons.append(btn)

        sb.addStretch()

        ver = QLabel("v2.0.0")
        ver.setContentsMargins(20, 0, 0, 0)
        ver.setStyleSheet("color: #202840; font-size: 10px;")
        sb.addWidget(ver)

        root_layout.addWidget(sidebar)
        root_layout.addWidget(self._stack, 1)

        self._switch(0)

    def _switch(self, idx: int):
        self._stack.setCurrentIndex(idx)
        for i, btn in enumerate(self._nav_buttons):
            btn._set_active(i == idx)