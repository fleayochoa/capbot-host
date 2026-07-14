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

    # ---------- Modo de conducción ----------
    # 0 = manual, 1 = autónomo — se dispara al presionar botón del mando
    mode_switch_requested = pyqtSignal(int)

    # ---------- Navegación / Mapa ----------
    # Estado de la conexión con gui_bridge_node (ROS): mismos valores que ws/udp
    nav_state_changed = pyqtSignal(str, str)  # (state, detail)
    # Pose real del robot en frame map: {x, y, yaw, valid, stamp}
    robot_pose_updated = pyqtSignal(dict)
    # Estado de navegación NAV2: {state, distance_remaining?}
    nav_status_changed = pyqtSignal(dict)
    # Objetivo solicitado desde la UI (mapa o campos): {x, y, yaw}
    nav_goal_requested = pyqtSignal(dict)
    # Cancelación del goal activo solicitada desde la UI
    nav_cancel_requested = pyqtSignal()
    # Nombre del mapa recibido desde el robot (gui_bridge_node) al conectar
    map_name_received = pyqtSignal(str)

    # ---------- Edición de paredes del maze ----------
    # Estado completo de paredes desde el robot: {map, walls, connected, unreachable}
    walls_received = pyqtSignal(dict)
    # Resultado de una edición: {ok, action, reason?}
    wall_result_received = pyqtSignal(dict)
    # Edición solicitada desde la UI: {action: "add"|"remove"|"reset", o?, i?, j?}
    wall_edit_requested = pyqtSignal(dict)

    # ---------- Obstáculos detectados por la DNN ----------
    # Celdas de 30 cm bloqueadas por objetos (desde el robot): {map, cells:[[i,j],..]}
    obstacles_received = pyqtSignal(dict)
    # Detecciones crudas de la DNN para dibujar sobre el video:
    # {stamp, fps, boxes:[{box:[x1,y1,x2,y2] normalizado 0..1, cls, conf,
    #  clipped, dist_m|None}, ...]}
    detections_received = pyqtSignal(dict)


# Singleton
bus = SignalBus()