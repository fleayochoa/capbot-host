"""Configuración centralizada del dashboard.

Todos los parámetros de red, timeouts y protocolo viven aquí para que cualquier
cambio se propague sin tocar módulos de negocio.
"""
import os
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


_ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


@dataclass(frozen=True)
class NavConfig:
    # Puerto del WebSocket de navegación expuesto por gui_bridge_node (ROS).
    # Corre en la misma Jetson que la telemetría → reusa NETWORK.jetson_host.
    gui_bridge_port: int = 8766

    # Reconexión del cliente de navegación (ms)
    nav_reconnect_ms: int = 1500
    # Si no llega pose en este tiempo, se marca la pose como obsoleta (ms)
    pose_stale_ms: int = 1000

    # Assets del mapa para renderizar la GUI de forma autónoma (copia de
    # capbot-ros/src/test_bot/maps/). Coinciden con el mapa que carga NAV2.
    map_pgm: str = os.path.join(_ASSETS_DIR, "map.pgm")
    map_yaml: str = os.path.join(_ASSETS_DIR, "map.yaml")


NETWORK = NetworkConfig()
PROTOCOL = ProtocolConfig()
JOYSTICK = JoystickConfig()
VIDEO = VideoConfig()
NAV = NavConfig()