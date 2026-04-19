"""Dock de paro de emergencia.

Un botón grande que dispara `bus.emergency_requested`. El UdpClient se encarga
de reenviar el paquete cada 20 ms hasta recibir ACK o agotar 50 intentos.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QDockWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.signals import bus


STYLE_IDLE = """
QPushButton {
    background: #c13434;
    color: white;
    font-size: 24px;
    font-weight: bold;
    border-radius: 10px;
    padding: 24px;
}
QPushButton:hover { background: #d33f3f; }
QPushButton:pressed { background: #a02828; }
"""
STYLE_ACTIVE = """
QPushButton {
    background: #7a1a1a;
    color: #ffcccc;
    font-size: 24px;
    font-weight: bold;
    border-radius: 10px;
    padding: 24px;
}
"""


class EmergencyDock(QDockWidget):
    def __init__(self, parent=None):
        super().__init__("Paro de emergencia", parent)
        self.setObjectName("dock_emergency")
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)

        self._btn = QPushButton("⛔  STOP")
        self._btn.setStyleSheet(STYLE_IDLE)
        self._btn.setMinimumHeight(100)
        self._btn.clicked.connect(self._trigger)

        self._status = QLabel("Listo")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setStyleSheet("color:#aaa; padding:4px;")

        hint = QLabel("Atajo: Barra espaciadora")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color:#666; font-size:10px;")

        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(self._btn, 1)
        lay.addWidget(self._status)
        lay.addWidget(hint)
        self.setWidget(container)

        # Atajo global (se crea sobre el widget principal desde main_window)
        self._shortcut = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        self._shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._shortcut.activated.connect(self._trigger)

        bus.emergency_acknowledged.connect(self._on_ack)

    def _trigger(self) -> None:
        self._btn.setStyleSheet(STYLE_ACTIVE)
        self._btn.setText("⛔  ENVIANDO…")
        self._status.setText("Enviando paro de emergencia…")
        bus.emergency_requested.emit()

    @pyqtSlot(bool, int)
    def _on_ack(self, ok: bool, retries: int) -> None:
        self._btn.setStyleSheet(STYLE_IDLE)
        self._btn.setText("⛔  STOP")
        if ok:
            self._status.setText(f"✔ Confirmado por Jetson ({retries} intentos)")
        else:
            self._status.setText(f"✘ Sin respuesta tras {retries} intentos")