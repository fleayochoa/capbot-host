"""Ventana principal del dashboard.

Ensambla todos los docks y orquesta el ciclo de vida de los subsistemas de red.
Expone un menú Ver para mostrar/ocultar docks y guardar layout.
"""
from __future__ import annotations

from PyQt6.QtCore import QSettings, Qt, pyqtSlot
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QMainWindow, QMessageBox

import config
from controllers.joystick import JoystickController
from controllers.joystick_mapper import JoystickMapper
from network.udp_client import UdpClient
from network.video_receiver import VideoReceiver
from network.ws_client import WsClient
from widgets.connection_dock import ConnectionDock
from widgets.emergency_dock import EmergencyDock
from widgets.joystick_dock import JoystickDock
from widgets.telemetry_dock import TelemetryDock
from widgets.video_dock import VideoDock


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Jetson Nano — Dashboard")
        self.resize(1400, 900)

        # ---------------- Subsistemas ----------------
        self.udp = UdpClient(self)
        self.ws = WsClient(self)
        self.video = VideoReceiver(self)
        self.joystick = JoystickController(self)
        self.mapper = JoystickMapper(self.udp, self)

        # ---------------- Docks ----------------
        self.video_dock = VideoDock(self)
        self.telemetry_dock = TelemetryDock(self)
        self.joystick_dock = JoystickDock(self)
        self.connection_dock = ConnectionDock(self)
        self.emergency_dock = EmergencyDock(self)

        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.video_dock)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.telemetry_dock)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.joystick_dock)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.connection_dock)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.emergency_dock)

        # Splits más sensatos: telemetría arriba, joystick abajo en la col derecha
        self.splitDockWidget(self.telemetry_dock, self.joystick_dock, Qt.Orientation.Vertical)
        # Video arriba y conexión abajo en la col izquierda
        self.splitDockWidget(self.video_dock, self.connection_dock, Qt.Orientation.Vertical)

        # ---------------- Menú ----------------
        self._build_menu()

        # ---------------- Señales de UI ----------------
        self.connection_dock.reconnect_requested.connect(self._on_reconnect)
        self.connection_dock.host_changed.connect(self._on_host_changed)

        # ---------------- Arranque ----------------
        self._start_all()

        # Restaurar layout guardado
        self._settings = QSettings("JetsonDash", "HostDashboard")
        geom = self._settings.value("geometry")
        if geom:
            self.restoreGeometry(geom)
        st = self._settings.value("windowState")
        if st:
            self.restoreState(st)

    # -------------------------------------------------------------
    def _build_menu(self) -> None:
        bar = self.menuBar()
        view_menu = bar.addMenu("&Ver")
        for dock in (
            self.video_dock,
            self.telemetry_dock,
            self.joystick_dock,
            self.connection_dock,
            self.emergency_dock,
        ):
            view_menu.addAction(dock.toggleViewAction())

        view_menu.addSeparator()
        reset_act = QAction("Restablecer layout", self)
        reset_act.triggered.connect(self._reset_layout)
        view_menu.addAction(reset_act)

        sys_menu = bar.addMenu("&Sistema")
        reconnect_all = QAction("Reconectar todo", self)
        reconnect_all.setShortcut(QKeySequence("Ctrl+R"))
        reconnect_all.triggered.connect(lambda: self._on_reconnect("all"))
        sys_menu.addAction(reconnect_all)

        quit_act = QAction("Salir", self)
        quit_act.setShortcut(QKeySequence.StandardKey.Quit)
        quit_act.triggered.connect(self.close)
        sys_menu.addAction(quit_act)

    # -------------------------------------------------------------
    def _start_all(self) -> None:
        self.udp.start()
        self.ws.start()
        self.video.start()
        self.joystick.start()

    def _stop_all(self) -> None:
        self.joystick.stop()
        self.video.stop()
        self.ws.stop()
        self.udp.stop()

    @pyqtSlot(str)
    def _on_reconnect(self, what: str) -> None:
        if what in ("udp", "all"):
            self.udp.stop()
            self.udp.start()
        if what in ("ws", "all"):
            self.ws.stop()
            self.ws.start()
        if what in ("video", "all"):
            self.video.stop()
            self.video.start()

    @pyqtSlot(str)
    def _on_host_changed(self, host: str) -> None:
        # Mutamos el dataclass (frozen=True nos obliga a object.__setattr__)
        object.__setattr__(config.NETWORK, "jetson_host", host)
        self._on_reconnect("all")
        QMessageBox.information(
            self,
            "Host actualizado",
            f"Reintentando con host {host}",
        )

    def _reset_layout(self) -> None:
        self.resize(1400, 900)
        # Recrear layout básico
        for dock in (
            self.video_dock,
            self.telemetry_dock,
            self.joystick_dock,
            self.connection_dock,
            self.emergency_dock,
        ):
            dock.setFloating(False)
            dock.show()
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.video_dock)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.telemetry_dock)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.joystick_dock)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.connection_dock)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.emergency_dock)
        self.splitDockWidget(self.telemetry_dock, self.joystick_dock, Qt.Orientation.Vertical)
        self.splitDockWidget(self.video_dock, self.connection_dock, Qt.Orientation.Vertical)

    # -------------------------------------------------------------
    def closeEvent(self, ev) -> None:
        self._settings.setValue("geometry", self.saveGeometry())
        self._settings.setValue("windowState", self.saveState())
        self._stop_all()
        super().closeEvent(ev)