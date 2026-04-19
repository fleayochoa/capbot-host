"""Controlador de joystick con pygame.

Corre en un QThread propio. Cuando no hay mando, reintenta cada `reconnect_ms`.
Cuando hay mando, polea a `poll_hz` y emite snapshots por el bus.

El mapeo final (qué eje = velocidad lineal, qué botón = emergencia, etc.)
ocurre fuera de este módulo; aquí sólo publicamos la lectura cruda.
"""
from __future__ import annotations

import time
from typing import Optional

from PyQt6.QtCore import QThread

try:
    import pygame
except ImportError:  # pragma: no cover
    pygame = None

from config import JOYSTICK
from core.signals import bus
from core.state import state


class JoystickController(QThread):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._joystick: Optional["pygame.joystick.Joystick"] = None

    def stop(self) -> None:
        self._running = False
        self.wait(1500)

    def run(self) -> None:
        if pygame is None:
            bus.joystick_state_changed.emit("error", "pygame no instalado")
            return

        # pygame exige display/video para algunos backends. En Windows lo evitamos:
        pygame.display.init()  # necesario en algunos drivers para eventos HID
        pygame.joystick.init()

        self._running = True
        poll_period = 1.0 / JOYSTICK.poll_hz
        reconnect_period = JOYSTICK.reconnect_ms / 1000.0
        last_reconnect_attempt = 0.0

        while self._running:
            # --- Intentar conectar si no hay mando ---
            if self._joystick is None:
                now = time.time()
                if now - last_reconnect_attempt >= reconnect_period:
                    last_reconnect_attempt = now
                    self._try_connect()
                if self._joystick is None:
                    time.sleep(0.1)
                    continue

            # --- Polling ---
            try:
                pygame.event.pump()
                snapshot = self._read_snapshot()
                bus.joystick_update.emit(snapshot)
                time.sleep(poll_period)
            except pygame.error as exc:
                # Desconexión del mando
                self._on_disconnect(str(exc))

        # Cleanup
        if self._joystick is not None:
            try:
                self._joystick.quit()
            except Exception:
                pass
        pygame.joystick.quit()
        pygame.display.quit()

    # ---------------------------------------------------
    def _try_connect(self) -> None:
        # Re-inicializar subsistema para detectar nuevos dispositivos
        pygame.joystick.quit()
        pygame.joystick.init()

        count = pygame.joystick.get_count()
        if count == 0:
            if state.joystick_state != "disconnected":
                state.joystick_state = "disconnected"
                state.joystick_name = ""
                bus.joystick_state_changed.emit("disconnected", "")
            return

        try:
            js = pygame.joystick.Joystick(0)
            js.init()
            self._joystick = js
            state.joystick_state = "connected"
            state.joystick_name = js.get_name()
            bus.joystick_state_changed.emit("connected", js.get_name())
        except pygame.error as exc:
            bus.joystick_state_changed.emit("error", str(exc))

    def _on_disconnect(self, reason: str) -> None:
        self._joystick = None
        state.joystick_state = "disconnected"
        state.joystick_name = ""
        bus.joystick_state_changed.emit("disconnected", reason)

    def _read_snapshot(self) -> dict:
        js = self._joystick
        assert js is not None
        dz = JOYSTICK.deadzone

        def axis(i: int) -> float:
            v = js.get_axis(i)
            return 0.0 if abs(v) < dz else v

        axes = [axis(i) for i in range(js.get_numaxes())]
        buttons = [bool(js.get_button(i)) for i in range(js.get_numbuttons())]
        hats = [js.get_hat(i) for i in range(js.get_numhats())]
        return {
            "name": js.get_name(),
            "axes": axes,
            "buttons": buttons,
            "hats": hats,
            "ts": time.time(),
        }