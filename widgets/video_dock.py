"""Dock de video: muestra el stream de la cámara de la Jetson."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QImage, QPainter, QPixmap
from PyQt6.QtWidgets import QDockWidget, QLabel, QVBoxLayout, QWidget

from core.signals import bus


class _VideoCanvas(QLabel):
    """QLabel que mantiene aspect ratio del último frame."""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(320, 180)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background:#111; color:#888;")
        self.setText("Sin señal de video")
        self._last_pix: QPixmap | None = None

    def set_image(self, img: QImage) -> None:
        self._last_pix = QPixmap.fromImage(img)
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
        self.setPixmap(scaled)


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

        bus.video_frame_ready.connect(self._on_frame)
        bus.video_state_changed.connect(self._on_state)

    @pyqtSlot(object)
    def _on_frame(self, img: QImage) -> None:
        self._canvas.set_image(img)

    @pyqtSlot(str, str)
    def _on_state(self, state: str, detail: str) -> None:
        self._status.setText(f"Video: {state} — {detail}" if detail else f"Video: {state}")
        if state != "connected":
            self._canvas.setText(f"Video {state}")