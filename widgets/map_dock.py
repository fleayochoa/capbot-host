"""Dock de Mapa: muestra el mapa de ocupación, la pose real del robot y permite
fijar un objetivo de navegación al estilo "2D Goal Pose" de rviz2.

Dos formas de fijar el goal (ambas emiten `bus.nav_goal_requested`):
  * Clic-arrastrar sobre el mapa: el clic fija la posición y el arrastre la
    orientación (igual que rviz2).
  * Campos numéricos x / y / θ(grados) + botón "Enviar objetivo".

La pose llega por `bus.robot_pose_updated`; el estado de navegación por
`bus.nav_status_changed`; el estado de conexión por `bus.nav_state_changed`.
"""
from __future__ import annotations

import math
import time

from PyQt6.QtCore import Qt, QTimer, QPointF, pyqtSignal, pyqtSlot
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
)
from PyQt6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import config
from config import AVAILABLE_MAPS, NAV, ROBOT
from core.occupancy_map import OccupancyMap, load_map
from core.signals import bus
from core.state import state
from widgets._common import color_for_state, format_state

_BTN_STYLE = (
    "QPushButton { background:#1f6feb; color:white; font-weight:bold;"
    "  padding:5px; border-radius:4px; }"
    "QPushButton:hover { background:#388bfd; }"
    "QPushButton:pressed { background:#1158c7; }"
    "QPushButton:disabled { background:#444; color:#777; }"
)
_CANCEL_STYLE = _BTN_STYLE.replace("#1f6feb", "#b3261e").replace(
    "#388bfd", "#d93f33").replace("#1158c7", "#8c1d18")

_ROBOT_COLOR = QColor(46, 160, 67)       # verde
_GOAL_COLOR = QColor(227, 160, 8)        # ámbar
_STALE_COLOR = QColor(130, 130, 130)     # gris (pose obsoleta)

# Flecha de orientación como múltiplo del radio real del robot (proporción
# visual fija, sea cual sea la resolución del mapa activo).
_ARROW_LEN_FACTOR = 2.75


class _MapView(QGraphicsView):
    """Vista del mapa con overlays (robot/goal) y captura de goal por arrastre."""

    goal_drawn = pyqtSignal(float, float, float)  # x, y, yaw(rad) en frame map

    def __init__(self, occ: OccupancyMap, parent=None):
        super().__init__(parent)
        self._occ = occ
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setMouseTracking(True)
        self.setBackgroundBrush(QBrush(QColor(30, 30, 30)))

        # Escena: 1 unidad = 1 píxel del mapa.
        self._scene = QGraphicsScene(0, 0, occ.width, occ.height, self)
        self.setScene(self._scene)
        self._scene.addPixmap(self._build_pixmap(occ))

        # Estado de overlays
        self._robot = None   # (x, y, yaw) o None
        self._robot_stale = False
        self._goal = None    # (x, y, yaw) o None

        # Estado de arrastre del goal
        self._drag_start = None  # QPointF en escena
        self._drag_cur = None

        self.fit()

    # ---- Construcción del pixmap en escala de grises ----
    @staticmethod
    def _build_pixmap(occ: OccupancyMap) -> QPixmap:
        img = QImage(bytes(occ.pixels), occ.width, occ.height,
                     occ.width, QImage.Format.Format_Grayscale8)
        return QPixmap.fromImage(img)

    def fit(self) -> None:
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def wheelEvent(self, ev) -> None:
        factor = 1.15 if ev.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    # ---- Overlays ----
    def set_robot(self, x: float, y: float, yaw: float, stale: bool) -> None:
        self._robot = (x, y, yaw)
        self._robot_stale = stale
        self.viewport().update()

    def clear_robot(self) -> None:
        self._robot = None
        self.viewport().update()

    def set_goal(self, x: float, y: float, yaw: float) -> None:
        self._goal = (x, y, yaw)
        self.viewport().update()

    def clear_goal(self) -> None:
        self._goal = None
        self.viewport().update()

    # ---- Captura del goal (estilo rviz2) ----
    def mousePressEvent(self, ev) -> None:
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drag_start = self.mapToScene(ev.pos())
            self._drag_cur = self._drag_start
            self.viewport().update()
        else:
            super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev) -> None:
        if self._drag_start is not None:
            self._drag_cur = self.mapToScene(ev.pos())
            self.viewport().update()
        else:
            super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev) -> None:
        if ev.button() == Qt.MouseButton.LeftButton and self._drag_start is not None:
            start, cur = self._drag_start, self.mapToScene(ev.pos())
            self._drag_start = self._drag_cur = None
            x, y = self._occ.pixel_to_world(start.x(), start.y())
            xc, yc = self._occ.pixel_to_world(cur.x(), cur.y())
            yaw = math.atan2(yc - y, xc - x)
            self.set_goal(x, y, yaw)
            self.goal_drawn.emit(x, y, yaw)
        else:
            super().mouseReleaseEvent(ev)

    # ---- Dibujo de overlays sobre el mapa ----
    def drawForeground(self, painter: QPainter, rect) -> None:
        if self._robot is not None:
            color = _STALE_COLOR if self._robot_stale else _ROBOT_COLOR
            self._draw_pose(painter, self._robot, color, filled=True)
        if self._goal is not None:
            self._draw_pose(painter, self._goal, _GOAL_COLOR, filled=False)
        # Flecha provisional mientras se arrastra
        if self._drag_start is not None and self._drag_cur is not None:
            pen = QPen(_GOAL_COLOR, 2)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawLine(self._drag_start, self._drag_cur)

    def _draw_pose(self, painter: QPainter, pose, color: QColor, filled: bool) -> None:
        x, y, yaw = pose
        px, py = self._occ.world_to_pixel(x, y)
        center = QPointF(px, py)

        # Footprint a escala real: caja orientada (no un círculo). Medio-largo
        # (eje de avance) y medio-ancho en unidades de escena (px del mapa),
        # a partir de las dimensiones físicas del chasis y la resolución
        # (m/px) del mapa activo, así se ve del tamaño correcto en cualquier mapa.
        res = self._occ.resolution
        half_len = (ROBOT.length_m / 2.0) / res
        half_wid = (ROBOT.width_m / 2.0) / res
        cos_y, sin_y = math.cos(yaw), math.sin(yaw)

        def _corner(fwd, left):
            # (fwd, left) offset en el frame local del robot (metros ya
            # convertidos a px) -> rotado por yaw al frame del mundo -> px
            # de escena (+y mundo es -py en escena).
            dx = fwd * cos_y - left * sin_y
            dy = fwd * sin_y + left * cos_y
            return QPointF(px + dx, py - dy)

        box = QPolygonF([
            _corner(half_len, half_wid),
            _corner(half_len, -half_wid),
            _corner(-half_len, -half_wid),
            _corner(-half_len, half_wid),
        ])

        pen = QPen(color, 2)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(QBrush(color) if filled else QBrush(Qt.BrushStyle.NoBrush))
        painter.drawPolygon(box)

        # Flecha de orientación (la caja sola no distingue frente/atrás si es
        # cuadrada). En escena, +x mundo apunta a +px; +y mundo apunta a -py.
        arrow_len = half_len * _ARROW_LEN_FACTOR
        tip = QPointF(px + arrow_len * math.cos(yaw),
                      py - arrow_len * math.sin(yaw))
        painter.drawLine(center, tip)
        # Cabeza de flecha
        ang = math.atan2(-(tip.y() - py), tip.x() - px)
        head = half_len
        head_left = QPointF(tip.x() - head * math.cos(ang - 0.5),
                            tip.y() + head * math.sin(ang - 0.5))
        head_right = QPointF(tip.x() - head * math.cos(ang + 0.5),
                             tip.y() + head * math.sin(ang + 0.5))
        painter.setBrush(QBrush(color))
        painter.drawPolygon(QPolygonF([tip, head_left, head_right]))


class MapDock(QDockWidget):
    def __init__(self, parent=None):
        super().__init__("Mapa", parent)
        self.setObjectName("dock_map")
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)

        container = QWidget()
        self._lay = QVBoxLayout(container)
        self._lay.setContentsMargins(4, 4, 4, 4)

        # ---- Selector de mapa ----
        map_row = QHBoxLayout()
        map_row.addWidget(QLabel("Mapa:"))
        self._map_combo = QComboBox()
        for name in AVAILABLE_MAPS:
            self._map_combo.addItem(name)
        map_row.addWidget(self._map_combo, 1)
        self._lay.addLayout(map_row)

        # ---- Contenedor intercambiable de la vista del mapa ----
        self._view_container = QWidget()
        self._view_container_lay = QVBoxLayout(self._view_container)
        self._view_container_lay.setContentsMargins(0, 0, 0, 0)
        self._lay.addWidget(self._view_container, 1)

        # ---- Estado ----
        self._conn_lbl = QLabel("Navegación: —")
        self._conn_lbl.setStyleSheet("font-size:11px; padding:2px;")
        self._status_lbl = QLabel("Sin objetivo")
        self._status_lbl.setStyleSheet("color:#aaa; font-size:11px; padding:2px;")
        self._lay.addWidget(self._conn_lbl)
        self._lay.addWidget(self._status_lbl)

        # ---- Campos numéricos del goal ----
        coords = QHBoxLayout()
        self._x_spin = self._make_spin(-1000.0, 1000.0, " m")
        self._y_spin = self._make_spin(-1000.0, 1000.0, " m")
        self._th_spin = self._make_spin(-180.0, 180.0, " °")
        coords.addWidget(QLabel("x"))
        coords.addWidget(self._x_spin)
        coords.addWidget(QLabel("y"))
        coords.addWidget(self._y_spin)
        coords.addWidget(QLabel("θ"))
        coords.addWidget(self._th_spin)
        self._lay.addLayout(coords)

        # ---- Botones ----
        btns = QHBoxLayout()
        self._send_btn = QPushButton("Enviar objetivo")
        self._send_btn.setStyleSheet(_BTN_STYLE)
        self._send_btn.clicked.connect(self._on_send_clicked)
        self._cancel_btn = QPushButton("Cancelar")
        self._cancel_btn.setStyleSheet(_CANCEL_STYLE)
        self._cancel_btn.clicked.connect(self._on_cancel_clicked)
        self._fit_btn = QPushButton("Centrar")
        self._fit_btn.setStyleSheet(_BTN_STYLE)
        self._fit_btn.clicked.connect(lambda: self._view and self._view.fit())
        btns.addWidget(self._send_btn)
        btns.addWidget(self._cancel_btn)
        btns.addWidget(self._fit_btn)
        self._lay.addLayout(btns)

        self.setWidget(container)

        # Carga inicial del mapa
        self._view: _MapView | None = None
        self._load_map_view(NAV.default_map_name)
        idx = self._map_combo.findText(NAV.default_map_name)
        if idx >= 0:
            self._map_combo.setCurrentIndex(idx)

        # ---- Señales ----
        self._map_combo.currentTextChanged.connect(self._on_map_selected)
        bus.robot_pose_updated.connect(self._on_pose)
        bus.nav_status_changed.connect(self._on_nav_status)
        bus.nav_state_changed.connect(self._on_nav_state)
        bus.map_name_received.connect(self._on_map_name_received)
        self._on_nav_state(state.nav_state, "")

        # ---- Timer de obsolescencia de pose ----
        self._stale_timer = QTimer(self)
        self._stale_timer.setInterval(400)
        self._stale_timer.timeout.connect(self._check_stale)
        self._stale_timer.start()

    # -------------------------------------------------------------
    # Carga y recarga del mapa
    # -------------------------------------------------------------
    def _load_map_view(self, name: str) -> None:
        """Carga el mapa `name` en el contenedor (crea _MapView o label de error)."""
        entry = AVAILABLE_MAPS.get(name, (None, None))
        pgm, yaml = entry[0], entry[1]
        has_view = False
        if pgm and yaml:
            try:
                occ = load_map(pgm, yaml)
                new_view = _MapView(occ)
                new_view.goal_drawn.connect(self._on_goal_drawn)
                self._view_container_lay.addWidget(new_view)
                self._view = new_view
                has_view = True
            except (OSError, ValueError) as exc:
                self._view = None
                err = QLabel(f"No se pudo cargar '{name}':\n{exc}")
                err.setStyleSheet("color:#d93f33; padding:8px;")
                err.setWordWrap(True)
                self._view_container_lay.addWidget(err)
        else:
            self._view = None
            err = QLabel(f"Mapa '{name}' no disponible localmente.")
            err.setStyleSheet("color:#e3a008; padding:8px;")
            err.setWordWrap(True)
            self._view_container_lay.addWidget(err)

        for w in (self._x_spin, self._y_spin, self._th_spin,
                  self._send_btn, self._cancel_btn, self._fit_btn):
            w.setEnabled(has_view)

        # Persist the active selection in config so other modules can query it
        object.__setattr__(config.NAV, "default_map_name", name)

    def _reload_map(self, name: str) -> None:
        """Descarta la vista actual y carga el mapa `name`."""
        # Remove every widget inside the container
        while self._view_container_lay.count():
            item = self._view_container_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.deleteLater()
        self._view = None
        self._load_map_view(name)

    @pyqtSlot(str)
    def _on_map_selected(self, name: str) -> None:
        self._reload_map(name)

    @pyqtSlot(str)
    def _on_map_name_received(self, name: str) -> None:
        """Auto-selecciona el mapa anunciado por el robot al conectar."""
        if name not in AVAILABLE_MAPS:
            self._status_lbl.setStyleSheet("color:#e3a008; font-size:11px; padding:2px;")
            self._status_lbl.setText(f"Mapa del robot '{name}' no disponible localmente")
            return
        idx = self._map_combo.findText(name)
        if idx >= 0 and self._map_combo.currentIndex() != idx:
            # Block the signal to avoid double-reload; reload explicitly
            self._map_combo.blockSignals(True)
            self._map_combo.setCurrentIndex(idx)
            self._map_combo.blockSignals(False)
            self._reload_map(name)

    # -------------------------------------------------------------
    @staticmethod
    def _make_spin(lo: float, hi: float, suffix: str) -> QDoubleSpinBox:
        sp = QDoubleSpinBox()
        sp.setRange(lo, hi)
        sp.setDecimals(2)
        sp.setSingleStep(0.1)
        sp.setSuffix(suffix)
        return sp

    # ---- Goal desde el mapa (clic-arrastrar) ----
    @pyqtSlot(float, float, float)
    def _on_goal_drawn(self, x: float, y: float, yaw: float) -> None:
        self._x_spin.setValue(x)
        self._y_spin.setValue(y)
        self._th_spin.setValue(math.degrees(yaw))
        self._emit_goal(x, y, yaw)

    # ---- Goal desde los campos ----
    def _on_send_clicked(self) -> None:
        x = self._x_spin.value()
        y = self._y_spin.value()
        yaw = math.radians(self._th_spin.value())
        if self._view is not None:
            self._view.set_goal(x, y, yaw)
        self._emit_goal(x, y, yaw)

    def _emit_goal(self, x: float, y: float, yaw: float) -> None:
        bus.nav_goal_requested.emit({"x": x, "y": y, "yaw": yaw})
        self._status_lbl.setStyleSheet("color:#e3a008; font-size:11px; padding:2px;")
        self._status_lbl.setText(
            f"Objetivo enviado: x={x:.2f} y={y:.2f} θ={math.degrees(yaw):.0f}°")

    def _on_cancel_clicked(self) -> None:
        bus.nav_cancel_requested.emit()
        if self._view is not None:
            self._view.clear_goal()
        self._status_lbl.setStyleSheet("color:#aaa; font-size:11px; padding:2px;")
        self._status_lbl.setText("Objetivo cancelado")

    # ---- Pose entrante ----
    @pyqtSlot(dict)
    def _on_pose(self, pose: dict) -> None:
        if self._view is None:
            return
        if not pose.get("valid", False):
            self._view.clear_robot()
            return
        self._view.set_robot(
            float(pose.get("x", 0.0)),
            float(pose.get("y", 0.0)),
            float(pose.get("yaw", 0.0)),
            stale=False,
        )

    def _check_stale(self) -> None:
        if self._view is None or state.last_pose_ts == 0:
            return
        pose = state.last_pose
        if not pose.get("valid", False):
            return
        stale = (time.time() - state.last_pose_ts) * 1000.0 > NAV.pose_stale_ms
        self._view.set_robot(
            float(pose.get("x", 0.0)),
            float(pose.get("y", 0.0)),
            float(pose.get("yaw", 0.0)),
            stale=stale,
        )

    # ---- Estado de navegación NAV2 ----
    @pyqtSlot(dict)
    def _on_nav_status(self, data: dict) -> None:
        st = data.get("state", "")
        labels = {
            "accepted": ("Objetivo aceptado", "#e3a008"),
            "active": ("Navegando…", "#388bfd"),
            "succeeded": ("¡Objetivo alcanzado!", "#2ea043"),
            "aborted": ("Navegación abortada", "#d93f33"),
            "canceled": ("Navegación cancelada", "#aaa"),
            "rejected": ("Objetivo rechazado por NAV2", "#d93f33"),
        }
        text, color = labels.get(st, (st, "#aaa"))
        if st == "active" and "distance_remaining" in data:
            text = f"Navegando… {data['distance_remaining']:.2f} m restantes"
        self._status_lbl.setStyleSheet(f"color:{color}; font-size:11px; padding:2px;")
        self._status_lbl.setText(text)

    # ---- Estado de conexión ----
    @pyqtSlot(str, str)
    def _on_nav_state(self, st: str, detail: str) -> None:
        color = color_for_state(st)
        self._conn_lbl.setText(f"Navegación: {format_state(st)}")
        self._conn_lbl.setStyleSheet(
            f"color:{color.name()}; font-size:11px; padding:2px;")
