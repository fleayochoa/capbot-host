"""Traduce snapshots de joystick a comandos de motor y los envía al UdpClient.

Convención por defecto (ajustable):
    - Eje 1 (stick izq vertical)  -> throttle (invertido: arriba = +)
    - Eje 0 (stick izq horizontal) -> giro diferencial
    - Botón 0 (A/Cross)            -> emergencia
Se aplica mezcla diferencial sencilla: L = throttle + turn, R = throttle - turn,
clamp a int16.
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, QTimer, pyqtSlot

from config import NETWORK
from core.signals import bus
from core.state import state
from network.udp_client import UdpClient


MAX_SPEED = 32768  # algo menos que int16 para margen


class JoystickMapper(QObject):
    """Escucha joystick_update y despacha comandos de motor.

    Envío:
      - Al cambiar el snapshot: inmediato.
      - Si no hay cambios: heartbeat periódico (keepalive) para que la Jetson
        sepa que el host sigue vivo.
    """

    def __init__(self, udp: UdpClient, parent=None):
        super().__init__(parent)
        self._udp = udp
        self._last_l = 0
        self._last_r = 0
        self._last_emergency_btn = False

        bus.joystick_update.connect(self._on_joy)
        bus.joystick_state_changed.connect(self._on_joy_state)

        # Heartbeat periódico (se usa incluso si no hay mando)
        self._hb_timer = QTimer(self)
        self._hb_timer.setInterval(NETWORK.heartbeat_interval_ms)
        self._hb_timer.timeout.connect(self._tick_heartbeat)
        self._hb_timer.start()

    @pyqtSlot(dict)
    def _on_joy(self, snap: dict) -> None:
        axes = snap.get("axes", [])
        buttons = snap.get("buttons", [])

        throttleLeft = -axes[1] if len(axes) > 1 else 0.0
        throttleRight = -axes[3] if len(axes) > 3 else 0.0
        
        left = throttleLeft
        right = throttleRight
        left = max(-1.0, min(1.0, left))
        right = max(-1.0, min(1.0, right))

        l_int = int(left * MAX_SPEED)
        r_int = int(right * MAX_SPEED)

        self._udp.send_motor(l_int, r_int, 0)
        self._last_l, self._last_r = l_int, r_int

        # Detección de flanco en botón 0 → emergencia
        btn0 = buttons[0] if buttons else False
        if btn0 and not self._last_emergency_btn:
            bus.emergency_requested.emit()
        self._last_emergency_btn = btn0

    @pyqtSlot(str, str)
    def _on_joy_state(self, st: str, _name: str) -> None:
        # Si se desconecta el mando, enviar STOP inmediato (seguro por defecto)
        if st != "connected":
            self._udp.send_motor(0, 0, 0)
            self._last_l = self._last_r = 0

    def _tick_heartbeat(self) -> None:
        # Si el joystick está desconectado y emergencia no activa, mandamos
        # heartbeat. Si está conectado, los propios comandos de motor sirven
        # de heartbeat para la Jetson.
        if state.joystick_state != "connected":
            self._udp.send_heartbeat()