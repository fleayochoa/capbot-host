"""Cliente UDP para comandos y ACKs.

Hilos:
  * _SenderThread:  procesa la cola de comandos pendientes. Cada comando se
                    retransmite hasta recibir su ACK o agotar reintentos.
  * _ReceiverThread: escucha ACKs en el puerto 5006 y los inyecta en un
                     diccionario de pending.

El paro de emergencia tiene su propia política (20 ms x 50) y se gestiona con
un flag dedicado para que tenga prioridad sobre cualquier otro comando.

Todo evento relevante se emite por `bus` (nunca se habla directo con la UI).
"""
from __future__ import annotations

import socket
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from PyQt6.QtCore import QObject

from config import NETWORK
from core.signals import bus
from core.state import state
from protocol.udp_frame import (
    Frame,
    MsgType,
    build_emergency,
    build_heartbeat,
    build_motor_cmd,
    parse_ack,
)


@dataclass
class _PendingCmd:
    seq: int
    data: bytes
    retries_left: int
    interval_s: float
    next_send_ts: float = 0.0
    sent_at: float = field(default_factory=time.time)
    is_emergency: bool = False


class UdpClient(QObject):
    """Cliente UDP orientado a comandos con acuse de recibo."""

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._sock: Optional[socket.socket] = None
        self._recv_sock: Optional[socket.socket] = None

        self._seq = 1
        self._seq_lock = threading.Lock()

        # Pendientes por seq → _PendingCmd
        self._pending: dict[int, _PendingCmd] = {}
        self._pending_lock = threading.Lock()

        self._running = False
        self._sender: Optional[threading.Thread] = None
        self._receiver: Optional[threading.Thread] = None

        # Conectar señal de emergencia del bus a nuestra acción
        bus.emergency_requested.connect(self.send_emergency)

    # -------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------
    def start(self) -> None:
        if self._running:
            return
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)

            self._recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._recv_sock.bind(("0.0.0.0", NETWORK.udp_ack_port))
            self._recv_sock.settimeout(0.2)

            self._running = True
            self._sender = threading.Thread(target=self._sender_loop, daemon=True, name="udp-sender")
            self._receiver = threading.Thread(target=self._receiver_loop, daemon=True, name="udp-receiver")
            self._sender.start()
            self._receiver.start()

            state.udp_state = "connected"
            bus.udp_state_changed.emit("connected", f"{NETWORK.jetson_host}:{NETWORK.udp_cmd_port}")
        except OSError as exc:
            state.udp_state = "error"
            bus.udp_state_changed.emit("error", str(exc))

    def stop(self) -> None:
        self._running = False
        if self._sender:
            self._sender.join(timeout=1.0)
        if self._receiver:
            self._receiver.join(timeout=1.0)
        for s in (self._sock, self._recv_sock):
            if s:
                try:
                    s.close()
                except OSError:
                    pass
        self._sock = self._recv_sock = None
        state.udp_state = "disconnected"
        bus.udp_state_changed.emit("disconnected", "")

    # -------------------------------------------------------------
    # API pública
    # -------------------------------------------------------------
    def send_motor(self, left: int, right: int, aux: int = 0) -> None:
        seq = self._next_seq()
        data = build_motor_cmd(seq, left, right, aux)
        self._enqueue(_PendingCmd(
            seq=seq,
            data=data,
            retries_left=NETWORK.cmd_max_retries,
            interval_s=NETWORK.cmd_ack_timeout_ms / 1000.0,
        ))

    def send_heartbeat(self) -> None:
        # Heartbeat no reintenta: si se pierde, el siguiente cubre.
        seq = self._next_seq()
        data = build_heartbeat(seq)
        self._send_raw(data)

    def send_emergency(self) -> None:
        """Paro de emergencia: 20 ms x 50 intentos máx."""
        seq = self._next_seq()
        data = build_emergency(seq)
        self._enqueue(_PendingCmd(
            seq=seq,
            data=data,
            retries_left=NETWORK.emergency_max_retries,
            interval_s=NETWORK.emergency_retry_ms / 1000.0,
            is_emergency=True,
        ))
        state.emergency_active = True

    # -------------------------------------------------------------
    # Internals
    # -------------------------------------------------------------
    def _next_seq(self) -> int:
        with self._seq_lock:
            s = self._seq
            self._seq = (self._seq + 1) & 0xFFFFFFFF
            if self._seq == 0:
                self._seq = 1
            return s

    def _enqueue(self, cmd: _PendingCmd) -> None:
        cmd.next_send_ts = time.time()
        with self._pending_lock:
            self._pending[cmd.seq] = cmd

    def _send_raw(self, data: bytes) -> None:
        if not self._sock:
            return
        try:
            self._sock.sendto(data, (NETWORK.jetson_host, NETWORK.udp_cmd_port))
        except OSError as exc:
            bus.udp_state_changed.emit("error", f"sendto: {exc}")

    def _sender_loop(self) -> None:
        while self._running:
            now = time.time()
            due: list[_PendingCmd] = []
            with self._pending_lock:
                for cmd in list(self._pending.values()):
                    if cmd.next_send_ts <= now:
                        due.append(cmd)

            for cmd in due:
                self._send_raw(cmd.data)
                cmd.retries_left -= 1
                cmd.next_send_ts = now + cmd.interval_s
                if cmd.retries_left <= 0:
                    # Agotado
                    with self._pending_lock:
                        self._pending.pop(cmd.seq, None)
                    if cmd.is_emergency:
                        state.emergency_active = False
                        bus.emergency_acknowledged.emit(False, NETWORK.emergency_max_retries)

            # Dormir hasta el próximo evento (mínimo 5 ms para no spin-lockear)
            time.sleep(0.005)

    def _receiver_loop(self) -> None:
        while self._running:
            try:
                data, _ = self._recv_sock.recvfrom(64)
            except socket.timeout:
                continue
            except OSError:
                break

            try:
                frame = Frame.unpack(data)
            except ValueError:
                continue  # frame corrupto, se ignora

            if frame.msg_type != MsgType.ACK:
                continue

            acked = parse_ack(frame)
            now = time.time()
            with self._pending_lock:
                cmd = self._pending.pop(acked, None)

            if cmd is None:
                continue

            rtt_ms = (now - cmd.sent_at) * 1000.0
            state.last_rtt_ms = rtt_ms
            bus.rtt_updated.emit(rtt_ms)

            if cmd.is_emergency:
                used = NETWORK.emergency_max_retries - cmd.retries_left
                state.emergency_active = False
                bus.emergency_acknowledged.emit(True, used)