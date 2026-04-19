"""Receptor de video vía GStreamer.

La Jetson envía H.264 sobre UDP al puerto 5000 (codificado por hardware con
`nvv4l2h264enc` y paquetizado con `rtph264pay`). Aquí montamos la pipeline
simétrica de recepción y usamos un `appsink` para tomar frames crudos como
QImage que se re-emiten por el bus.

Si GStreamer no está disponible en el sistema, el módulo emite un estado de
error y no crashea: el resto del dashboard sigue funcionando.

Pipeline típica de recepción:
    udpsrc port=5000 caps="application/x-rtp,media=video,encoding-name=H264,payload=96"
      ! rtpjitterbuffer latency=50
      ! rtph264depay
      ! avdec_h264
      ! videoconvert
      ! video/x-raw,format=RGB
      ! appsink name=sink emit-signals=true max-buffers=2 drop=true sync=false
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QObject, QThread
from PyQt6.QtGui import QImage

from config import NETWORK, VIDEO
from core.signals import bus
from core.state import state

try:
    import gi
    gi.require_version("Gst", "1.0")
    from gi.repository import Gst, GLib
    _GST_AVAILABLE = True
except (ImportError, ValueError):  # pragma: no cover
    Gst = GLib = None
    _GST_AVAILABLE = False


def _build_pipeline_str() -> str:
    return (
        f"udpsrc port={NETWORK.video_port} "
        f'caps="application/x-rtp,media=video,encoding-name=H264,payload=96" '
        f"! rtpjitterbuffer latency=50 "
        f"! rtph264depay "
        f"! avdec_h264 "
        f"! videoconvert "
        f"! video/x-raw,format=RGB,width={VIDEO.width},height={VIDEO.height} "
        f"! appsink name=sink emit-signals=true max-buffers=2 drop=true sync=false"
    )


class VideoReceiver(QObject):
    """Administra la pipeline GStreamer y re-emite QImage por el bus."""

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._pipeline = None
        self._appsink = None
        self._loop: Optional[GLib.MainLoop] = None
        self._thread: Optional[QThread] = None

    def start(self) -> None:
        if not _GST_AVAILABLE:
            state.video_state = "error"
            bus.video_state_changed.emit("error", "GStreamer no disponible en este sistema")
            return

        if self._pipeline is not None:
            return

        Gst.init(None)
        try:
            self._pipeline = Gst.parse_launch(_build_pipeline_str())
        except GLib.Error as exc:
            state.video_state = "error"
            bus.video_state_changed.emit("error", f"parse_launch: {exc}")
            return

        self._appsink = self._pipeline.get_by_name("sink")
        self._appsink.connect("new-sample", self._on_new_sample)

        bus_gst = self._pipeline.get_bus()
        bus_gst.add_signal_watch()
        bus_gst.connect("message::error", self._on_bus_error)
        bus_gst.connect("message::eos", self._on_bus_eos)

        self._pipeline.set_state(Gst.State.PLAYING)

        # GLib main loop en thread dedicado para recibir mensajes del bus GStreamer
        self._thread = _GLibLoopThread()
        self._thread.start()

        state.video_state = "connected"
        bus.video_state_changed.emit("connected", f"udp:{NETWORK.video_port}")

    def stop(self) -> None:
        if self._pipeline:
            self._pipeline.set_state(Gst.State.NULL)
            self._pipeline = None
            self._appsink = None
        if self._thread:
            self._thread.quit_loop()
            self._thread.wait(1000)
            self._thread = None
        state.video_state = "disconnected"
        bus.video_state_changed.emit("disconnected", "")

    # ---- GStreamer callbacks ----
    def _on_new_sample(self, appsink):
        sample = appsink.emit("pull-sample")
        if sample is None:
            return Gst.FlowReturn.ERROR
        buf = sample.get_buffer()
        caps = sample.get_caps().get_structure(0)
        width = caps.get_value("width")
        height = caps.get_value("height")

        ok, mapinfo = buf.map(Gst.MapFlags.READ)
        if not ok:
            return Gst.FlowReturn.ERROR
        try:
            # Copiamos los bytes: QImage sin copia es peligroso cuando el buffer
            # se libera. A 30fps 720p el coste es asumible.
            image = QImage(
                bytes(mapinfo.data), width, height, width * 3, QImage.Format.Format_RGB888
            ).copy()
            bus.video_frame_ready.emit(image)
        finally:
            buf.unmap(mapinfo)
        return Gst.FlowReturn.OK

    def _on_bus_error(self, _bus, message):
        err, dbg = message.parse_error()
        state.video_state = "error"
        bus.video_state_changed.emit("error", f"{err.message} ({dbg})")

    def _on_bus_eos(self, _bus, _message):
        state.video_state = "disconnected"
        bus.video_state_changed.emit("disconnected", "EOS")


class _GLibLoopThread(QThread):
    def __init__(self):
        super().__init__()
        self._loop: Optional[GLib.MainLoop] = None

    def run(self) -> None:
        self._loop = GLib.MainLoop()
        try:
            self._loop.run()
        except Exception:  # pragma: no cover
            pass

    def quit_loop(self) -> None:
        if self._loop and self._loop.is_running():
            self._loop.quit()