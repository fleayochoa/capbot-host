"""Cliente WebSocket para telemetría JSON desde la Jetson.

Usa asyncio dentro de un QThread dedicado para no bloquear la UI. Reconecta
automáticamente con backoff si la conexión cae.
"""
from __future__ import annotations

import asyncio
import json
from typing import Optional

from PyQt6.QtCore import QThread

try:
    import websockets
    from websockets.exceptions import ConnectionClosed, WebSocketException
except ImportError:  # pragma: no cover
    websockets = None
    ConnectionClosed = WebSocketException = Exception

from config import NETWORK
from core.signals import bus
from core.state import state


class WsClient(QThread):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop_event: Optional[asyncio.Event] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def stop(self) -> None:
        if self._loop and self._stop_event:
            self._loop.call_soon_threadsafe(self._stop_event.set)
        self.wait(2000)

    def run(self) -> None:  # QThread entrypoint
        if websockets is None:
            bus.ws_state_changed.emit("error", "websockets package not installed")
            return
        try:
            asyncio.run(self._main())
        except Exception as exc:  # pragma: no cover
            bus.ws_state_changed.emit("error", f"loop crashed: {exc}")

    async def _main(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()

        url = f"ws://{NETWORK.jetson_host}:{NETWORK.ws_telemetry_port}"
        backoff = NETWORK.ws_reconnect_ms / 1000.0

        while not self._stop_event.is_set():
            state.ws_state = "connecting"
            bus.ws_state_changed.emit("connecting", url)
            try:
                async with websockets.connect(url, ping_interval=5, ping_timeout=5) as ws:
                    state.ws_state = "connected"
                    bus.ws_state_changed.emit("connected", url)
                    await self._consume(ws)
            except (OSError, WebSocketException, ConnectionClosed) as exc:
                state.ws_state = "disconnected"
                bus.ws_state_changed.emit("disconnected", f"{type(exc).__name__}: {exc}")

            if self._stop_event.is_set():
                break

            # Espera con opción de cancelación
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=backoff)
            except asyncio.TimeoutError:
                pass

    async def _consume(self, ws) -> None:
        stop_task = asyncio.create_task(self._stop_event.wait())
        try:
            while not self._stop_event.is_set():
                recv_task = asyncio.create_task(ws.recv())
                done, pending = await asyncio.wait(
                    {recv_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
                )
                if stop_task in done:
                    recv_task.cancel()
                    return
                msg = recv_task.result()
                self._handle_message(msg)
        finally:
            if not stop_task.done():
                stop_task.cancel()

    def _handle_message(self, msg: str | bytes) -> None:
        try:
            if isinstance(msg, bytes):
                msg = msg.decode("utf-8")
            data = json.loads(msg)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        if not isinstance(data, dict):
            return
        state.mark_telemetry(data)
        bus.telemetry_received.emit(data)