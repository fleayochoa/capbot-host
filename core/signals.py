"""Bus de señales Qt global.

Este módulo expone un singleton `bus` que re-emite todos los eventos del sistema.
Los widgets se conectan a las señales relevantes sin conocer a los productores;
los productores (clientes de red, controllers) emiten sin conocer a los consumidores.

Esto desacopla totalmente la UI de la red y permite:
  - Sustituir clientes reales por mocks en tests
  - Añadir nuevos widgets sin tocar la capa de red
  - Reutilizar el mismo bus para logging/grabación
"""
from PyQt6.QtCore import QObject, pyqtSignal


class SignalBus(QObject):
    # ---------- Conexión ----------
    # Estado general: "disconnected" | "connecting" | "connected" | "error"
    ws_state_changed = pyqtSignal(str, str)     # (state, detail)
    udp_state_changed = pyqtSignal(str, str)
    video_state_changed = pyqtSignal(str, str)

    # ---------- Telemetría ----------
    # dict con sensores decodificados desde JSON del WS
    telemetry_received = pyqtSignal(dict)
    # RTT estimado en ms (ACK - envío)
    rtt_updated = pyqtSignal(float)

    # ---------- Video ----------
    # QImage listo para pintar
    video_frame_ready = pyqtSignal(object)  # QImage

    # ---------- Joystick ----------
    # "connected" | "disconnected"
    joystick_state_changed = pyqtSignal(str, str)  # (state, device_name)
    # Snapshot del mando: {axes: [...], buttons: [...], hats: [...]}
    joystick_update = pyqtSignal(dict)

    # ---------- Emergencia ----------
    # Se dispara desde cualquier parte (UI, joystick botón, etc.)
    emergency_requested = pyqtSignal()
    # Resultado del handshake de emergencia: True si recibió ACK, False si agotó reintentos
    emergency_acknowledged = pyqtSignal(bool, int)  # (ok, retries_used)


# Singleton
bus = SignalBus()