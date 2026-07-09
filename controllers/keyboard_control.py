"""Control manual por teclado: respaldo cuando no hay joystick conectado.

    Q: rueda izquierda adelante   A: rueda izquierda atrás
    E: rueda derecha adelante     D: rueda derecha atrás

Mientras el joystick esté conectado, el JoystickMapper tiene la autoridad y
el teclado se ignora (evita pelear comandos entre las dos fuentes). Mantener
una tecla mueve la rueda a velocidad fija (KEYBOARD.speed); soltarla la
detiene. Se reenvía el comando periódicamente mientras haya alguna tecla
presionada (keepalive, igual que el polling del joystick).
"""
from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, QTimer, Qt
from PyQt6.QtGui import QKeyEvent

from config import KEYBOARD
from core.signals import bus
from core.state import state
from network.udp_client import UdpClient

MAX_SPEED = 32767

_LEFT_FWD = Qt.Key.Key_Q
_LEFT_BACK = Qt.Key.Key_A
_RIGHT_FWD = Qt.Key.Key_E
_RIGHT_BACK = Qt.Key.Key_D
_TRACKED_KEYS = {_LEFT_FWD, _LEFT_BACK, _RIGHT_FWD, _RIGHT_BACK}


class KeyboardController(QObject):
    """Event filter de aplicación: traduce Q/A/E/R a comandos de motor."""

    def __init__(self, udp: UdpClient, parent=None):
        super().__init__(parent)
        self._udp = udp
        self._pressed: set[int] = set()
        self._last_l = 0
        self._last_r = 0

        bus.joystick_state_changed.connect(self._on_joystick_state)

        self._resend_timer = QTimer(self)
        self._resend_timer.setInterval(KEYBOARD.resend_ms)
        self._resend_timer.timeout.connect(self._resend)
        self._resend_timer.start()

    def stop(self) -> None:
        self._resend_timer.stop()

    # ------------------------------------------------------------------
    def eventFilter(self, obj, ev) -> bool:  # noqa: N802 (override de Qt)
        if ev.type() in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            key_ev: QKeyEvent = ev
            if not key_ev.isAutoRepeat() and key_ev.key() in _TRACKED_KEYS:
                if state.joystick_state == "connected":
                    # El joystick manda; no pelear comandos con el teclado.
                    return False
                if ev.type() == QEvent.Type.KeyPress:
                    self._pressed.add(key_ev.key())
                else:
                    self._pressed.discard(key_ev.key())
                self._send_current()
        return False

    # ------------------------------------------------------------------
    def _on_joystick_state(self, st: str, _name: str) -> None:
        if st == "connected" and self._pressed:
            # El joystick tomó el control: soltamos teclas que hubieran
            # quedado "pegadas" y dejamos de mandar por teclado.
            self._pressed.clear()
            self._udp.send_motor(0, 0, 0)
            self._last_l = self._last_r = 0

    def _compute_lr(self) -> tuple[int, int]:
        speed = max(0.0, min(1.0, KEYBOARD.speed))
        left = 0.0
        if _LEFT_FWD in self._pressed and _LEFT_BACK not in self._pressed:
            left = speed
        elif _LEFT_BACK in self._pressed and _LEFT_FWD not in self._pressed:
            left = -speed
        right = 0.0
        if _RIGHT_FWD in self._pressed and _RIGHT_BACK not in self._pressed:
            right = speed
        elif _RIGHT_BACK in self._pressed and _RIGHT_FWD not in self._pressed:
            right = -speed
        return int(left * MAX_SPEED), int(right * MAX_SPEED)

    def _send_current(self) -> None:
        l_int, r_int = self._compute_lr()
        self._udp.send_motor(l_int, r_int, 0)
        self._last_l, self._last_r = l_int, r_int

    def _resend(self) -> None:
        if self._pressed and state.joystick_state != "connected":
            self._udp.send_motor(self._last_l, self._last_r, 0)
