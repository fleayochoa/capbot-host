"""Dock de video: muestra el stream de la cámara de la Jetson con las
detecciones de la DNN superpuestas (caja, clase, confianza y distancia).

Las cajas llegan por `bus.detections_received` (WS de navegación, mensaje
{"type":"detections"}) normalizadas 0..1 sobre el frame de análisis de la
Jetson; como la rama de análisis y el video comparten aspecto (16:9), basta
escalarlas al pixmap mostrado. Si dejan de llegar (percepción detenida) el
overlay se limpia solo a los ~2 s.
"""
from __future__ import annotations

import time

from PyQt6.QtCore import Qt, QRectF, QTimer, pyqtSlot
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QDockWidget, QLabel, QVBoxLayout, QWidget

from core.signals import bus

# Nombres de clase del engine activo (bottles_fp16.engine: una sola clase).
# Si el id no está aquí se muestra "cls N".
_CLASS_NAMES = {0: "botella"}

_DET_COLOR = QColor(46, 204, 64)          # verde (caja + texto)
_DET_TEXT_BG = QColor(0, 0, 0, 160)       # fondo del rótulo
# Sin detecciones nuevas tras este tiempo, el overlay se borra.
_DET_STALE_S = 2.0


class _VideoCanvas(QLabel):
    """QLabel que mantiene aspect ratio del último frame y pinta detecciones."""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(320, 180)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background:#111; color:#888;")
        self.setText("Sin señal de video")
        self._last_pix: QPixmap | None = None
        self._dets: list = []

    def set_image(self, img: QImage) -> None:
        self._last_pix = QPixmap.fromImage(img)
        self._redraw()

    def set_detections(self, dets: list) -> None:
        self._dets = dets
        self._redraw()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._redraw()

    def _redraw(self) -> None:
        if self._last_pix is None:
            return
        scaled = self._last_pix.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        if self._dets:
            self._paint_detections(scaled)
        self.setPixmap(scaled)

    def _paint_detections(self, pix: QPixmap) -> None:
        w, h = pix.width(), pix.height()
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(_DET_COLOR, 2)
        font = painter.font()
        font.setPointSizeF(max(8.0, h / 40.0))
        painter.setFont(font)
        metrics = painter.fontMetrics()

        for d in self._dets:
            box = d.get("box")
            if not isinstance(box, (list, tuple)) or len(box) != 4:
                continue
            try:
                x1, y1, x2, y2 = (float(v) for v in box)
            except (TypeError, ValueError):
                continue
            rect = QRectF(x1 * w, y1 * h, (x2 - x1) * w, (y2 - y1) * h)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)

            # Rótulo: clase, confianza y distancia ("<" = caja recortada por
            # el borde inferior: el objeto está más cerca que lo estimado).
            cls_id = d.get("cls")
            name = _CLASS_NAMES.get(cls_id, f"cls {cls_id}")
            try:
                label = f"{name} {float(d.get('conf', 0.0)):.2f}"
            except (TypeError, ValueError):
                label = name
            dist = d.get("dist_m")
            if dist is not None:
                prefix = "<" if d.get("clipped") else ""
                label += f"  {prefix}{float(dist):.2f} m"

            text_w = metrics.horizontalAdvance(label) + 8
            text_h = metrics.height() + 2
            # Rótulo encima de la caja; si no cabe, adentro.
            ty = rect.top() - text_h
            if ty < 0:
                ty = rect.top()
            bg = QRectF(rect.left(), ty, text_w, text_h)
            painter.fillRect(bg, _DET_TEXT_BG)
            painter.drawText(bg.adjusted(4, 0, 0, 0),
                             Qt.AlignmentFlag.AlignVCenter, label)
        painter.end()


class VideoDock(QDockWidget):
    def __init__(self, parent=None):
        super().__init__("Cámara", parent)
        self.setObjectName("dock_video")
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)

        self._canvas = _VideoCanvas()
        self._status = QLabel("—")
        self._status.setStyleSheet("color:#aaa; padding:2px 6px;")

        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._canvas, 1)
        lay.addWidget(self._status)
        self.setWidget(container)

        self._video_state = "—"
        self._video_detail = ""
        self._det_stamp = 0.0   # llegada local de la última tanda de cajas
        self._det_fps = 0.0
        self._det_count = -1    # -1 = nunca llegó nada (no mostrar en status)

        bus.video_frame_ready.connect(self._on_frame)
        bus.video_state_changed.connect(self._on_state)
        bus.detections_received.connect(self._on_detections)

        # Limpia el overlay si la percepción deja de mandar cajas.
        self._stale_timer = QTimer(self)
        self._stale_timer.setInterval(500)
        self._stale_timer.timeout.connect(self._check_stale)
        self._stale_timer.start()

    @pyqtSlot(object)
    def _on_frame(self, img: QImage) -> None:
        self._canvas.set_image(img)

    @pyqtSlot(str, str)
    def _on_state(self, state: str, detail: str) -> None:
        self._video_state = state
        self._video_detail = detail
        self._refresh_status()
        if state != "connected":
            self._canvas.setText(f"Video {state}")

    @pyqtSlot(dict)
    def _on_detections(self, data: dict) -> None:
        boxes = data.get("boxes")
        boxes = boxes if isinstance(boxes, list) else []
        self._det_stamp = time.time()
        self._det_count = len(boxes)
        try:
            self._det_fps = float(data.get("fps") or 0.0)
        except (TypeError, ValueError):
            self._det_fps = 0.0
        self._canvas.set_detections(boxes)
        self._refresh_status()

    def _check_stale(self) -> None:
        if self._det_count < 0:
            return
        if time.time() - self._det_stamp > _DET_STALE_S:
            self._det_count = -1
            self._canvas.set_detections([])
            self._refresh_status()

    def _refresh_status(self) -> None:
        text = (f"Video: {self._video_state} — {self._video_detail}"
                if self._video_detail else f"Video: {self._video_state}")
        if self._det_count >= 0:
            text += f"   |   DNN: {self._det_count} obj @ {self._det_fps:.1f} fps"
        self._status.setText(text)
