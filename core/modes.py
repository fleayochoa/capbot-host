"""Constantes y helper compartido para el modo de conducción.

Centraliza lo que antes vivía duplicado en JoystickMapper, para que el
teclado y el mando usen la misma vía de cambio de modo.
"""
from __future__ import annotations

from core.signals import bus
from core.state import state

MODE_MANUAL = 0
MODE_AUTONOMOUS = 1
MODE_NAV2 = 2

MODE_NAME = {
    MODE_MANUAL: "manual",
    MODE_AUTONOMOUS: "autonomous",
    MODE_NAV2: "nav2",
}


def set_drive_mode(mode: int) -> None:
    """Actualiza el estado compartido y notifica al bus (UDP, UI, etc.)."""
    state.drive_mode = MODE_NAME[mode]
    bus.mode_switch_requested.emit(mode)
