"""Entry point del dashboard."""
from __future__ import annotations

import sys

from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtWidgets import QApplication

from main_window import MainWindow


def apply_dark_palette(app: QApplication) -> None:
    app.setStyle("Fusion")
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(32, 33, 36))
    p.setColor(QPalette.ColorRole.WindowText, QColor(220, 220, 220))
    p.setColor(QPalette.ColorRole.Base, QColor(24, 25, 28))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(40, 42, 46))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 255))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(0, 0, 0))
    p.setColor(QPalette.ColorRole.Text, QColor(220, 220, 220))
    p.setColor(QPalette.ColorRole.Button, QColor(45, 47, 52))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(220, 220, 220))
    p.setColor(QPalette.ColorRole.Highlight, QColor(38, 110, 213))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    app.setPalette(p)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Jetson Host Dashboard")
    apply_dark_palette(app)
    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())