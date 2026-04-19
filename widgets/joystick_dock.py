"""Dock de joystick: muestra estado, ejes y botones."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QColor, QPainter, QPaintEvent
from PyQt6.QtWidgets import (
    QDockWidget,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from core.signals import bus
from widgets._common import color_for_state, format_state


class _AxisBar(QWidget):
    """Barra horizontal bidireccional (-1..1)."""
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(12)
        self._value = 0.0

    def set_value(self, v: float) -> None:
        self._value = max(-1.0, min(1.0, v))
        self.update()

    def paintEvent(self, _ev: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        mid = w // 2
        # Fondo
        p.fillRect(0, 0, w, h, QColor(40, 40, 40))
        # Línea central
        p.setPen(QColor(90, 90, 90))
        p.drawLine(mid, 0, mid, h)
        # Valor
        if self._value >= 0:
            p.fillRect(mid, 2, int((w / 2) * self._value), h - 4, QColor(46, 160, 67))
        else:
            bar_w = int((w / 2) * (-self._value))
            p.fillRect(mid - bar_w, 2, bar_w, h - 4, QColor(218, 54, 51))


class JoystickDock(QDockWidget):
    MAX_AXES = 8
    MAX_BTNS = 16

    def __init__(self, parent=None):
        super().__init__("Joystick", parent)
        self.setObjectName("dock_joystick")
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)

        self._status = QLabel("Sin mando")
        self._status.setStyleSheet("font-weight:bold; padding:4px;")

        # Ejes
        axes_box = QWidget()
        axes_lay = QGridLayout(axes_box)
        axes_lay.setContentsMargins(4, 4, 4, 4)
        self._axis_bars: list[_AxisBar] = []
        self._axis_labels: list[QLabel] = []
        for i in range(self.MAX_AXES):
            lbl = QLabel(f"Eje {i}")
            lbl.setFixedWidth(50)
            bar = _AxisBar()
            val = QLabel("0.00")
            val.setFixedWidth(44)
            val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            axes_lay.addWidget(lbl, i, 0)
            axes_lay.addWidget(bar, i, 1)
            axes_lay.addWidget(val, i, 2)
            self._axis_bars.append(bar)
            self._axis_labels.append(val)

        # Botones
        btn_box = QWidget()
        btn_lay = QGridLayout(btn_box)
        btn_lay.setContentsMargins(4, 4, 4, 4)
        btn_lay.setSpacing(4)
        self._btn_labels: list[QLabel] = []
        for i in range(self.MAX_BTNS):
            b = QLabel(str(i))
            b.setFixedSize(28, 22)
            b.setAlignment(Qt.AlignmentFlag.AlignCenter)
            b.setStyleSheet(self._btn_style(False))
            btn_lay.addWidget(b, i // 8, i % 8)
            self._btn_labels.append(b)

        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self._status)
        lay.addWidget(QLabel("Ejes"))
        lay.addWidget(axes_box)
        lay.addWidget(QLabel("Botones"))
        lay.addWidget(btn_box)
        lay.addStretch(1)
        self.setWidget(container)

        bus.joystick_state_changed.connect(self._on_state)
        bus.joystick_update.connect(self._on_update)

    @staticmethod
    def _btn_style(pressed: bool) -> str:
        if pressed:
            return "background:#2ea043; color:white; border-radius:4px;"
        return "background:#2b2b2b; color:#888; border-radius:4px;"

    @pyqtSlot(str, str)
    def _on_state(self, st: str, name: str) -> None:
        color = color_for_state(st).name()
        text = f"<span style='color:{color}'>●</span> {format_state(st)}"
        if name:
            text += f" — {name}"
        self._status.setText(text)

    @pyqtSlot(dict)
    def _on_update(self, snap: dict) -> None:
        axes = snap.get("axes", [])
        for i, bar in enumerate(self._axis_bars):
            if i < len(axes):
                bar.set_value(axes[i])
                self._axis_labels[i].setText(f"{axes[i]:+.2f}")
                bar.setEnabled(True)
            else:
                bar.set_value(0.0)
                self._axis_labels[i].setText("—")
                bar.setEnabled(False)

        buttons = snap.get("buttons", [])
        for i, lbl in enumerate(self._btn_labels):
            pressed = i < len(buttons) and buttons[i]
            lbl.setStyleSheet(self._btn_style(pressed))