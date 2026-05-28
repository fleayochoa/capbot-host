"""Dock de telemetría: muestra sensores recibidos por WebSocket."""
from __future__ import annotations

import csv
import time
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
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

        self._btn_record = QPushButton("Iniciar grabación CSV")
        self._btn_record.setCheckable(True)
        self._btn_record.toggled.connect(self._toggle_recording)

        self._rec_label = QLabel("")
        self._rec_label.setStyleSheet("color:#aaa; font-size:10px; padding:2px;")

        btn_row = QHBoxLayout()
        btn_row.addWidget(self._btn_record)
        btn_row.addWidget(self._rec_label, 1)

        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self._summary)
        lay.addWidget(self._table, 1)
        lay.addLayout(btn_row)
        self.setWidget(container)

        self._rows: dict[str, int] = {}
        self._csv_file = None
        self._csv_writer = None
        self._csv_header_written = False

        bus.telemetry_received.connect(self._on_telemetry)
        bus.rtt_updated.connect(self._on_rtt)

        # Indicador de staleness: si no llegan datos en 1s, avisamos
        self._stale_timer = QTimer(self)
        self._stale_timer.setInterval(500)
        self._stale_timer.timeout.connect(self._check_stale)
        self._stale_timer.start()

    # ------------------------------------------------------------------
    # CSV recording
    # ------------------------------------------------------------------

    def _toggle_recording(self, checked: bool) -> None:
        if checked:
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Guardar telemetría CSV",
                str(Path.home() / f"telemetry_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"),
                "CSV (*.csv)",
            )
            if not path:
                self._btn_record.setChecked(False)
                return
            self._csv_file = open(path, "w", newline="", encoding="utf-8")
            self._csv_writer = csv.writer(self._csv_file)
            self._csv_header_written = False
            self._btn_record.setText("Detener grabación")
            self._btn_record.setStyleSheet("color: red;")
            self._rec_label.setText(Path(path).name)
        else:
            self._stop_recording()

    def _stop_recording(self) -> None:
        if self._csv_file:
            self._csv_file.close()
            self._csv_file = None
            self._csv_writer = None
            self._csv_header_written = False
        self._btn_record.setText("Iniciar grabación CSV")
        self._btn_record.setStyleSheet("")
        self._rec_label.setText("")

    def _record_row(self, flat: dict[str, str]) -> None:
        if self._csv_writer is None:
            return
        if not self._csv_header_written:
            self._csv_writer.writerow(["timestamp"] + list(flat.keys()))
            self._csv_header_written = True
        self._csv_writer.writerow(
            [datetime.now().isoformat(timespec="milliseconds")] + list(flat.values())
        )
        self._csv_file.flush()

    @pyqtSlot(dict)
    def _on_telemetry(self, data: dict) -> None:
        flat: dict[str, str] = {}
        self._render_dict("", data, flat)
        if self._csv_writer is not None:
            self._record_row(flat)

    def _render_dict(self, prefix: str, data: dict, flat: dict | None = None) -> None:
        for key, value in data.items():
            full_key = f"{prefix}{key}"
            if isinstance(value, dict):
                self._render_dict(f"{full_key}.", value, flat)
            elif isinstance(value, list):
                text = ", ".join(str(v) for v in value)
                self._set_row(full_key, text)
                if flat is not None:
                    flat[full_key] = text
            else:
                self._set_row(full_key, str(value))
                if flat is not None:
                    flat[full_key] = str(value)

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