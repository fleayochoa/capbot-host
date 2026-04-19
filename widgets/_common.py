"""Utilidades compartidas por los widgets."""
from PyQt6.QtGui import QColor


STATE_COLORS = {
    "connected": QColor(46, 160, 67),      # verde
    "connecting": QColor(227, 160, 8),     # ámbar
    "disconnected": QColor(130, 130, 130), # gris
    "error": QColor(218, 54, 51),          # rojo
}


def color_for_state(state: str) -> QColor:
    return STATE_COLORS.get(state, STATE_COLORS["disconnected"])


def format_state(state: str) -> str:
    return {
        "connected": "Conectado",
        "connecting": "Conectando…",
        "disconnected": "Desconectado",
        "error": "Error",
    }.get(state, state)