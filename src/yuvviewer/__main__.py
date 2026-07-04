"""Entry point: `python -m yuvviewer`."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # clean, consistent flat look across Windows/Linux/macOS
    app.setApplicationName("YUView-lite")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
