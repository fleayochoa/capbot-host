# capbot-host
Repositorio destinado a guardar el programa a correr en PC host


# Host Dashboard — Jetson Nano Teleoperation

Dashboard de teleoperación en PyQt6 con widgets acoplables para controlar una Jetson Nano
vía red mixta (UDP para comandos de baja latencia + WebSocket para telemetría + GStreamer
para video).

## Arquitectura

```
host_dashboard/
├── main.py                 # Entry point
├── config.py               # Puertos, timeouts, IPs
├── core/
│   ├── signals.py          # Bus de señales Qt global
│   └── state.py            # Estado compartido (conexión, last-seen, etc.)
├── protocol/
│   └── udp_frame.py        # Empaquetado binario 16 bytes [magic|ver|type|seq|payload|crc16]
├── network/
│   ├── udp_client.py       # UDP con ACK + reintento (emergencia: 20ms x 50)
│   ├── ws_client.py        # WebSocket cliente telemetría
│   └── video_receiver.py   # GStreamer pipeline appsink → QImage
├── controllers/
│   └── joystick.py         # pygame en QThread con reconexión periódica
├── widgets/
│   ├── video_dock.py       # Stream de cámara
│   ├── telemetry_dock.py   # Sensores numéricos + gráficos
│   ├── joystick_dock.py    # Estado del mando y mapeo
│   ├── connection_dock.py  # Estado de red + reintentos manuales
│   └── emergency_dock.py   # Botón de paro de emergencia
└── main_window.py          # QMainWindow + ensamblaje de docks
```

## Principios de diseño

1. **Señales Qt como único pegamento entre capas.** Ningún widget importa clientes de red;
   todos consumen señales del `SignalBus` global. Esto permite mockear la red en tests.
2. **Cada cliente de red vive en su propio QThread.** El hilo UI nunca se bloquea.
3. **Reconexión automática en todas las capas** (joystick, WebSocket, video) con backoff.
4. **Reintentos de emergencia gestionados por el cliente UDP**, no por la UI.

## Requisitos

```
PyQt6>=6.6
pygame>=2.5
websockets>=12.0
# Para video: GStreamer con bindings Python (PyGObject) y plugins gst-plugins-{base,good,bad}
```

En Windows, GStreamer se instala desde https://gstreamer.freedesktop.org/download/
(runtime + development) y se añade `<gst>/bin` al PATH.

## Ejecución

```
python main.py
```