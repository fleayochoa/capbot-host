"""Dock de telemetría: muestra sensores recibidos por WebSocket."""
from __future__ import annotations

import time

from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtWidgets import (
    QDockWidget,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.signals import bus
from core.state import state


class TelemetryDock(QDockWidget):
    def __init__(self, parent=None):
        super().__init__("Telemetría", parent)
        self.setObjectName("dock_telemetry")
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)

        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["Sensor", "Valor"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self._summary = QLabel("Esperando telemetría…")
        self._summary.setStyleSheet("color:#aaa; padding:4px;")

        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self._summary)
        lay.addWidget(self._table, 1)
        self.setWidget(container)

        self._rows: dict[str, int] = {}

        bus.telemetry_received.connect(self._on_telemetry)
        bus.rtt_updated.connect(self._on_rtt)

        # Indicador de staleness: si no llegan datos en 1s, avisamos
        self._stale_timer = QTimer(self)
        self._stale_timer.setInterval(500)
        self._stale_timer.timeout.connect(self._check_stale)
        self._stale_timer.start()

    @pyqtSlot(dict)
    def _on_telemetry(self, data: dict) -> None:
        self._render_dict("", data)

    def _render_dict(self, prefix: str, data: dict) -> None:
        for key, value in data.items():
            full_key = f"{prefix}{key}"
            if isinstance(value, dict):
                self._render_dict(f"{full_key}.", value)
            elif isinstance(value, list):
                self._set_row(full_key, ", ".join(str(v) for v in value))
            else:
                self._set_row(full_key, str(value))

    def _set_row(self, key: str, value: str) -> None:
        if key in self._rows:
            self._table.item(self._rows[key], 1).setText(value)
        else:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(key))
            self._table.setItem(row, 1, QTableWidgetItem(value))
            self._rows[key] = row

    @pyqtSlot(float)
    def _on_rtt(self, rtt_ms: float) -> None:
        self._summary.setText(f"RTT último comando: {rtt_ms:.1f} ms")

    def _check_stale(self) -> None:
        if state.last_telemetry_ts == 0:
            return
        age = time.time() - state.last_telemetry_ts
        if age > 1.0:
            self._summary.setText(f"⚠ Telemetría obsoleta ({age:.1f}s sin datos)")