"""Dock de telemetría: muestra sensores recibidos por WebSocket."""
from __future__ import annotations

import csv
import datetime
import os
import time
from collections import deque

_TELEMETRY_HZ = 50
_HISTORY_SECONDS = 5 * 60
_HISTORY_MAXLEN = _TELEMETRY_HZ * _HISTORY_SECONDS

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

_SAVE_BTN_STYLE = (
    "QPushButton { background:#1f6feb; color:white; font-weight:bold;"
    "  padding:5px; border-radius:4px; }"
    "QPushButton:hover { background:#388bfd; }"
    "QPushButton:pressed { background:#1158c7; }"
    "QPushButton:disabled { background:#444; color:#777; }"
)


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

        self._save_btn = QPushButton("Guardar CSV")
        self._save_btn.setStyleSheet(_SAVE_BTN_STYLE)
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._on_save_csv)

        self._save_status = QLabel("")
        self._save_status.setStyleSheet("color:#aaa; font-size:10px; padding:2px;")

        btn_row = QHBoxLayout()
        btn_row.addWidget(self._save_btn)
        btn_row.addWidget(self._save_status, 1)

        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self._summary)
        lay.addWidget(self._table, 1)
        lay.addLayout(btn_row)
        self.setWidget(container)

        self._rows: dict[str, int] = {}
        self._history: deque[dict] = deque(maxlen=_HISTORY_MAXLEN)  # ultimos 5 min @ 50 Hz
        self._stale_active = False       # si el aviso de "obsoleta" esta mostrado

        bus.telemetry_received.connect(self._on_telemetry)
        bus.rtt_updated.connect(self._on_rtt)

        # Indicador de staleness: si no llegan datos en 1s, avisamos
        self._stale_timer = QTimer(self)
        self._stale_timer.setInterval(500)
        self._stale_timer.timeout.connect(self._check_stale)
        self._stale_timer.start()

    @pyqtSlot(dict)
    def _on_telemetry(self, data: dict) -> None:
        flat: dict[str, str] = {}
        self._flatten("", data, flat)
        record = {"timestamp": datetime.datetime.now().isoformat(timespec="milliseconds")}
        record.update(flat)
        self._history.append(record)
        self._save_btn.setEnabled(True)
        self._render_dict("", data)

    def _flatten(self, prefix: str, data: dict, out: dict[str, str]) -> None:
        for key, value in data.items():
            full_key = f"{prefix}{key}"
            if isinstance(value, dict):
                self._flatten(f"{full_key}.", value, out)
            elif isinstance(value, list):
                out[full_key] = ", ".join(str(v) for v in value)
            else:
                out[full_key] = str(value)

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

    def _on_save_csv(self) -> None:
        if not self._history:
            return
        default_name = datetime.datetime.now().strftime("telemetry_%Y%m%d_%H%M%S.csv")
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar telemetría", default_name, "CSV (*.csv)"
        )
        if not path:
            return
        all_keys: list[str] = list(
            dict.fromkeys(k for rec in self._history for k in rec)
        )
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(self._history)
            self._save_status.setStyleSheet("color:#2ea043; font-size:10px; padding:2px;")
            self._save_status.setText(f"Guardado: {os.path.basename(path)}")
        except OSError as exc:
            self._save_status.setStyleSheet("color:#d93f33; font-size:10px; padding:2px;")
            self._save_status.setText(f"Error: {exc}")

    def _check_stale(self) -> None:
        if state.last_telemetry_ts == 0:
            return
        age = time.time() - state.last_telemetry_ts
        if age > 1.0:
            self._stale_active = True
            self._summary.setText(f"⚠ Telemetría obsoleta ({age:.1f}s sin datos)")
        elif self._stale_active:
            # Sin esto, el aviso de "obsoleta" queda pegado en pantalla para
            # siempre despues de un unico hueco (arranque, hiccup de red),
            # aunque la telemetria se haya normalizado.
            self._stale_active = False
            self._summary.setText("Telemetría OK")