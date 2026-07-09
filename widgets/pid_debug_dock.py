"""Dock de ajuste de PID: 6 constantes (3x2, solo velocidad), envío por UDP."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDockWidget,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from network.udp_client import UdpClient
from protocol.udp_frame import (
    CTRL_LEFT_WHEEL_VEL,
    CTRL_RIGHT_WHEEL_VEL,
    PARAM_KD,
    PARAM_KI,
    PARAM_KP,
)

_CONTROLLERS = [
    (CTRL_LEFT_WHEEL_VEL,  "leftWheel"),
    (CTRL_RIGHT_WHEEL_VEL, "rightWheel"),
]
_PARAMS = [
    (PARAM_KP, "Kp"),
    (PARAM_KI, "Ki"),
    (PARAM_KD, "Kd"),
]

_BTN_STYLE = (
    "QPushButton { background:#2ea043; color:white; font-weight:bold;"
    "  padding:6px; border-radius:4px; }"
    "QPushButton:hover { background:#3caf52; }"
    "QPushButton:pressed { background:#237c34; }"
)


class PidDebugDock(QDockWidget):
    def __init__(self, udp: UdpClient, parent=None):
        super().__init__("PID Debug", parent)
        self.setObjectName("dock_pid_debug")
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self._udp = udp

        # ── PID constants grid (2 rows × 3 cols) ──────────────────────
        pid_group = QGroupBox("Constantes PID")
        pid_lay = QGridLayout(pid_group)
        pid_lay.setContentsMargins(6, 6, 6, 6)
        pid_lay.setSpacing(4)

        pid_lay.addWidget(QLabel(""), 0, 0)
        for col, (_, pname) in enumerate(_PARAMS, start=1):
            hdr = QLabel(pname)
            hdr.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hdr.setStyleSheet("font-weight:bold;")
            pid_lay.addWidget(hdr, 0, col)

        self._inputs: dict[tuple[int, int], QDoubleSpinBox] = {}
        for row, (ctrl_id, ctrl_name) in enumerate(_CONTROLLERS, start=1):
            pid_lay.addWidget(QLabel(ctrl_name), row, 0)
            for col, (param_id, _) in enumerate(_PARAMS, start=1):
                spin = QDoubleSpinBox()
                spin.setRange(0.0, 999999.0)
                spin.setDecimals(6)
                spin.setSingleStep(0.01)
                spin.setValue(0.0)
                pid_lay.addWidget(spin, row, col)
                self._inputs[(ctrl_id, param_id)] = spin

        # ── Buttons + status ──────────────────────────────────────────
        self._send_pid_btn = QPushButton("Enviar PID")
        self._send_pid_btn.setStyleSheet(_BTN_STYLE)
        self._send_pid_btn.clicked.connect(self._on_send_pid)

        self._status = QLabel("")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setStyleSheet("color:#aaa; font-size:10px; padding:2px;")

        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addWidget(pid_group)
        lay.addWidget(self._send_pid_btn)
        lay.addWidget(self._status)
        lay.addStretch(1)
        self.setWidget(container)

    # ──────────────────────────────────────────────────────────────────
    def _on_send_pid(self) -> None:
        pid_params = [
            (ctrl_id, param_id, spin.value())
            for (ctrl_id, param_id), spin in self._inputs.items()
        ]
        self._udp.send_pid_params(pid_params)
        self._status.setStyleSheet("color:#2ea043; font-size:10px; padding:2px;")
        self._status.setText("Constantes PID enviadas")
