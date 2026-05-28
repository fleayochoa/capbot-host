"""Dock de ajuste de PID: 12 constantes (3x4) y setpoint, envío por UDP."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDockWidget,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from network.udp_client import UdpClient
from protocol.udp_frame import (
    CTRL_ANG_POS,
    CTRL_ANG_VEL,
    CTRL_LINEAR_POS,
    CTRL_LINEAR_VEL,
    PARAM_KD,
    PARAM_KI,
    PARAM_KP,
)

_CONTROLLERS = [
    (CTRL_LINEAR_POS, "linearPos"),
    (CTRL_LINEAR_VEL, "linearVel"),
    (CTRL_ANG_POS,    "angPos"),
    (CTRL_ANG_VEL,    "angVel"),
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

        # ── PID constants grid (4 rows × 3 cols) ──────────────────────
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

        # ── Setpoint ──────────────────────────────────────────────────
        sp_group = QGroupBox("Setpoint")
        sp_lay = QVBoxLayout(sp_group)
        sp_lay.setContentsMargins(6, 6, 6, 6)
        hint = QLabel("xPos, yPos, angPos")
        hint.setStyleSheet("color:#888; font-size:10px;")
        self._sp_edit = QLineEdit()
        self._sp_edit.setPlaceholderText("0.0, 0.0, 0.0")
        sp_lay.addWidget(hint)
        sp_lay.addWidget(self._sp_edit)

        # ── Buttons + status ──────────────────────────────────────────
        self._send_pid_btn = QPushButton("Enviar PID")
        self._send_pid_btn.setStyleSheet(_BTN_STYLE)
        self._send_pid_btn.clicked.connect(self._on_send_pid)

        self._send_sp_btn = QPushButton("Enviar Setpoint")
        self._send_sp_btn.setStyleSheet(_BTN_STYLE)
        self._send_sp_btn.clicked.connect(self._on_send_setpoint)

        self._status = QLabel("")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setStyleSheet("color:#aaa; font-size:10px; padding:2px;")

        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addWidget(pid_group)
        lay.addWidget(self._send_pid_btn)
        lay.addWidget(sp_group)
        lay.addWidget(self._send_sp_btn)
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

    def _on_send_setpoint(self) -> None:
        sp_text = self._sp_edit.text().strip() or "0,0,0"
        try:
            parts = [float(x.strip()) for x in sp_text.split(",")]
            if len(parts) != 3:
                raise ValueError(f"se esperan 3 valores, recibidos {len(parts)}")
        except ValueError as exc:
            self._status.setStyleSheet("color:#d93f33; font-size:10px; padding:2px;")
            self._status.setText(f"Setpoint inválido: {exc}")
            return
        self._udp.send_setpoint(parts)
        self._status.setStyleSheet("color:#2ea043; font-size:10px; padding:2px;")
        self._status.setText("Setpoint enviado")
