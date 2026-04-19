"""Estado compartido global del dashboard.

Contiene el último snapshot de cada subsistema. Los widgets lo pueden consultar
para obtener su estado inicial al crearse (en vez de esperar la siguiente señal).
"""
from dataclasses import dataclass, field
from typing import Optional
import time


@dataclass
class SystemState:
    ws_state: str = "disconnected"
    udp_state: str = "disconnected"
    video_state: str = "disconnected"
    joystick_state: str = "disconnected"
    joystick_name: str = ""

    last_telemetry: dict = field(default_factory=dict)
    last_telemetry_ts: float = 0.0
    last_rtt_ms: Optional[float] = None

    emergency_active: bool = False

    def mark_telemetry(self, data: dict) -> None:
        self.last_telemetry = data
        self.last_telemetry_ts = time.time()


state = SystemState()