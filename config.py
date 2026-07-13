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
class KeyboardConfig:
    # Velocidad aplicada por rueda al mantener una tecla (fraccion de MAX_SPEED)
    speed: float = 0.6
    # Periodo de reenvio del comando mientras se mantiene una tecla (ms)
    resend_ms: int = 100


@dataclass(frozen=True)
class VideoConfig:
    width: int = 1280
    height: int = 720
    fps: int = 30


@dataclass(frozen=True)
class RobotConfig:
    # Footprint real del chasis: una caja de ~22x22 cm (no un circulo), medida
    # a ojo. Usado para dibujar el robot a escala real en el mapa
    # (widgets/map_dock.py). capbot-jetson no tiene hoy un equivalente (solo
    # wheel_radius/wheel_separation, que son geometria de rueda, no el
    # footprint completo del chasis).
    length_m: float = 0.22   # adelante-atras (eje de avance)
    width_m: float = 0.22    # izquierda-derecha


_ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

# Mapas disponibles localmente (nombre -> (pgm, yaml)).
# El nombre debe coincidir con el argumento map_name:=<name> del launch file.
# Values: (pgm_path, yaml_path)
AVAILABLE_MAPS: dict[str, tuple] = {
    "small": (
        os.path.join(_ASSETS_DIR, "test_map_small.pgm"),
        os.path.join(_ASSETS_DIR, "test_map_small.yaml"),
    ),
    "maze": (
        os.path.join(_ASSETS_DIR, "test_map_maze.pgm"),
        os.path.join(_ASSETS_DIR, "test_map_maze.yaml"),
    ),
}


@dataclass(frozen=True)
class NavConfig:
    # Puerto del WebSocket de navegación expuesto por gui_bridge_node (ROS).
    # Corre en la misma Jetson que la telemetría → reusa NETWORK.jetson_host.
    gui_bridge_port: int = 8766

    # Reconexión del cliente de navegación (ms)
    nav_reconnect_ms: int = 1500
    # Si no llega pose en este tiempo, se marca la pose como obsoleta (ms)
    pose_stale_ms: int = 1000

    # Mapa activo por defecto. Debe coincidir con map_name:=<name> del launch
    # file. La UI permite cambiarlo en runtime; el robot lo anuncia al conectar.
    default_map_name: str = "small"


NETWORK = NetworkConfig()
PROTOCOL = ProtocolConfig()
JOYSTICK = JoystickConfig()
KEYBOARD = KeyboardConfig()
VIDEO = VideoConfig()
NAV = NavConfig()
ROBOT = RobotConfig()