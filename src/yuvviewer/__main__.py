"""Entry point: `python -m yuvviewer`."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .ui.main_window import MainWindow


def _icon_path() -> Path:
    """Locate resources/icon.ico both running from source and PyInstaller-frozen."""
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)  # PyInstaller onefile extraction dir
    else:
        base = Path(__file__).resolve().parent.parent.parent  # project root
    return base / "resources" / "icon.ico"


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # clean, consistent flat look across Windows/Linux/macOS
    app.setApplicationName("YUView-lite")

    icon_path = _icon_path()
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
