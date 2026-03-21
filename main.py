"""
main.py
───────
Entry point for PGSafe.

Loads the QSS stylesheet from  ui/styles.qss  and launches the window.
"""

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


def _load_stylesheet() -> str:
    qss_path = Path(__file__).parent / "ui" / "styles.qss"
    try:
        return qss_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"Warning: stylesheet not found at {qss_path}")
        return ""


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(_load_stylesheet())

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()