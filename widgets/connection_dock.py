"""Dock de conexión: estado por subsistema y acciones de reintento."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QPainter, QPaintEvent
from PyQt6.QtWidgets import (
    QDockWidget,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from config import NETWORK
from core.signals import bus
from widgets._common import color_for_state, format_state


class _Led(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(14, 14)
        self._color = color_for_state("disconnected")

    def set_state(self, state: str) -> None:
        self._color = color_for_state(state)
        self.update()

    def paintEvent(self, _ev: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(self._color)
        p.setPen(QColor(0, 0, 0, 60))
        p.drawEllipse(1, 1, self.width() - 2, self.height() - 2)


class ConnectionDock(QDockWidget):
    # Emitida cuando el usuario pulsa "Reintentar"
    reconnect_requested = pyqtSignal(str)  # "udp" | "ws" | "video" | "all"
    host_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__("Conexión", parent)
        self.setObjectName("dock_connection")
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)

        # Campo host editable
        host_row = QHBoxLayout()
        host_row.addWidget(QLabel("Jetson host:"))
        self._host_edit = QLineEdit(NETWORK.jetson_host)
        self._host_edit.setMaximumWidth(180)
        host_row.addWidget(self._host_edit)
        apply_btn = QPushButton("Aplicar")
        apply_btn.clicked.connect(self._on_host_apply)
        host_row.addWidget(apply_btn)
        host_row.addStretch(1)

        # Grid de estados
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        self._rows: dict[str, tuple[_Led, QLabel, QLabel, QPushButton]] = {}
        subsystems = [
            ("udp", "UDP comandos"),
            ("ws", "WebSocket telemetría"),
            ("video", "Video"),
            ("joystick", "Joystick"),
        ]
        for row, (key, label) in enumerate(subsystems):
            led = _Led()
            name_lbl = QLabel(label)
            state_lbl = QLabel("Desconectado")
            state_lbl.setStyleSheet("color:#aaa;")
            retry_btn = QPushButton("Reintentar")
            if key == "joystick":
                # Joystick reconecta sólo; botón inhabilitado
                retry_btn.setEnabled(False)
                retry_btn.setToolTip("El joystick reintenta automáticamente")
            else:
                retry_btn.clicked.connect(lambda _=False, k=key: self.reconnect_requested.emit(k))
            grid.addWidget(led, row, 0)
            grid.addWidget(name_lbl, row, 1)
            grid.addWidget(state_lbl, row, 2)
            grid.addWidget(retry_btn, row, 3)
            self._rows[key] = (led, name_lbl, state_lbl, retry_btn)

        # Botón reintento global
        all_btn = QPushButton("Reintentar todo")
        all_btn.clicked.connect(lambda: self.reconnect_requested.emit("all"))

        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addLayout(host_row)
        lay.addLayout(grid)
        lay.addWidget(all_btn)
        lay.addStretch(1)
        self.setWidget(container)

        bus.udp_state_changed.connect(lambda s, d: self._update("udp", s, d))
        bus.ws_state_changed.connect(lambda s, d: self._update("ws", s, d))
        bus.video_state_changed.connect(lambda s, d: self._update("video", s, d))
        bus.joystick_state_changed.connect(lambda s, d: self._update("joystick", s, d))

    @pyqtSlot(str, str, str)
    def _update(self, key: str, st: str, detail: str) -> None:
        if key not in self._rows:
            return
        led, _, state_lbl, _ = self._rows[key]
        led.set_state(st)
        txt = format_state(st)
        if detail:
            txt += f" — {detail}"
        state_lbl.setText(txt)

    def _on_host_apply(self) -> None:
        host = self._host_edit.text().strip()
        if host:
            self.host_changed.emit(host)