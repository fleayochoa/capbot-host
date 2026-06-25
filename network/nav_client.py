"""Cliente WebSocket de navegación hacia gui_bridge_node (ROS).

Espejo de `network/ws_client.py`: asyncio dentro de un QThread con reconexión
automática. A diferencia del cliente de telemetría, este canal es bidireccional:
  * Entrada  (ROS -> host): pose del robot y estado de navegación → bus.
  * Salida   (host -> ROS): goals y cancelaciones, encolados desde la UI.

Se conecta a ws://{NETWORK.jetson_host}:{NAV.gui_bridge_port} (mismo Jetson que
la telemetría; el nodo gui_bridge_node corre dentro de la pila ROS).
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

from config import NAV, NETWORK
from core.signals import bus
from core.state import state


class NavClient(QThread):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop_event: Optional[asyncio.Event] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._ws = None  # conexión activa (solo se toca dentro del loop)

        # La UI emite estas señales; las convertimos en envíos por el socket.
        bus.nav_goal_requested.connect(self.send_goal)
        bus.nav_cancel_requested.connect(self.cancel)

    # -------------------------------------------------------------
    # API pública (thread-safe: agenda el envío en el loop asyncio)
    # -------------------------------------------------------------
    def send_goal(self, goal: dict) -> None:
        payload = json.dumps({
            "type": "goal",
            "x": float(goal.get("x", 0.0)),
            "y": float(goal.get("y", 0.0)),
            "yaw": float(goal.get("yaw", 0.0)),
        })
        self._send_threadsafe(payload)

    def cancel(self) -> None:
        self._send_threadsafe(json.dumps({"type": "cancel"}))

    def _send_threadsafe(self, payload: str) -> None:
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(
            lambda: asyncio.ensure_future(self._do_send(payload), loop=self._loop)
        )

    async def _do_send(self, payload: str) -> None:
        if self._ws is None:
            return
        try:
            await self._ws.send(payload)
        except (WebSocketException, ConnectionClosed, OSError):
            pass

    # -------------------------------------------------------------
    # Lifecycle (idéntico a WsClient)
    # -------------------------------------------------------------
    def stop(self) -> None:
        if self._loop and self._stop_event:
            self._loop.call_soon_threadsafe(self._stop_event.set)
        self.wait(2000)

    def run(self) -> None:  # QThread entrypoint
        if websockets is None:
            bus.nav_state_changed.emit("error", "websockets package not installed")
            return
        try:
            asyncio.run(self._main())
        except Exception as exc:  # pragma: no cover
            bus.nav_state_changed.emit("error", f"loop crashed: {exc}")

    async def _main(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()

        url = f"ws://{NETWORK.jetson_host}:{NAV.gui_bridge_port}"
        backoff = NAV.nav_reconnect_ms / 1000.0

        while not self._stop_event.is_set():
            state.nav_state = "connecting"
            bus.nav_state_changed.emit("connecting", url)
            try:
                async with websockets.connect(url, ping_interval=5, ping_timeout=5) as ws:
                    self._ws = ws
                    state.nav_state = "connected"
                    bus.nav_state_changed.emit("connected", url)
                    await self._consume(ws)
            except (OSError, WebSocketException, ConnectionClosed) as exc:
                state.nav_state = "disconnected"
                bus.nav_state_changed.emit("disconnected", f"{type(exc).__name__}: {exc}")
            finally:
                self._ws = None

            if self._stop_event.is_set():
                break

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
                self._handle_message(recv_task.result())
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
        mtype = data.get("type")
        if mtype == "pose":
            state.mark_pose(data)
            bus.robot_pose_updated.emit(data)
        elif mtype == "nav_status":
            state.last_nav_status = data
            bus.nav_status_changed.emit(data)
        elif mtype == "map_name":
            name = str(data.get("name", "")).strip()
            if name:
                bus.map_name_received.emit(name)
