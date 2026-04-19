"""Configuración centralizada del dashboard.

Todos los parámetros de red, timeouts y protocolo viven aquí para que cualquier
cambio se propague sin tocar módulos de negocio.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class NetworkConfig:
    # IP del Jetson Nano. Se puede sobrescribir en runtime desde la UI.
    jetson_host: str = "192.168.1.120"

    # Puertos según especificación
    video_port: int = 5000
    udp_cmd_port: int = 5005       # host -> jetson: comandos
    udp_ack_port: int = 5006       # jetson -> host: ACKs
    ws_telemetry_port: int = 8765  # jetson -> host: WebSocket telemetría

    # Timeouts / heartbeats (milisegundos)
    ws_reconnect_ms: int = 1500
    video_reconnect_ms: int = 2000
    heartbeat_interval_ms: int = 100   # comando vacío/keepalive periódico

    # Emergencia: 20 ms x 50 intentos = 1s máximo
    emergency_retry_ms: int = 20
    emergency_max_retries: int = 50

    # Reintento de comandos normales ante pérdida de ACK
    cmd_ack_timeout_ms: int = 100
    cmd_max_retries: int = 3


@dataclass(frozen=True)
class ProtocolConfig:
    magic: int = 0xABCD
    version: int = 1
    frame_size: int = 16  # bytes fijos


@dataclass(frozen=True)
class JoystickConfig:
    # Periodo de polling del mando cuando está conectado
    poll_hz: int = 50
    # Periodo entre intentos de reconexión cuando no hay mando
    reconnect_ms: int = 1000
    # Deadzone de ejes (-1..1)
    deadzone: float = 0.08


@dataclass(frozen=True)
class VideoConfig:
    width: int = 1280
    height: int = 720
    fps: int = 30


NETWORK = NetworkConfig()
PROTOCOL = ProtocolConfig()
JOYSTICK = JoystickConfig()
VIDEO = VideoConfig()