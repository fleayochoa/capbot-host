"""Empaquetado/desempaquetado de frames UDP binarios de 16 bytes.

Layout (little-endian):
    [magic:2][version:1][type:1][seq:4][payload:6][crc16:2]
    = 16 bytes fijos

CRC16-CCITT (poly 0x1021, init 0xFFFF) calculado sobre los primeros 14 bytes.

Tipos de mensaje (convención propuesta, ajustable):
    0x01  CMD_MOTOR     payload = int16 left, int16 right, int16 aux (velocidades)
    0x02  CMD_HEARTBEAT payload = zeros
    0x03  CMD_EMERGENCY payload = zeros (paro de emergencia)
    0x81  ACK           payload[0..3] = seq que acusa, resto reservado
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum

from config import PROTOCOL


class MsgType(IntEnum):
    CMD_MOTOR = 0x01
    CMD_HEARTBEAT = 0x02
    CMD_EMERGENCY = 0x03
    ACK = 0x81


# ------------------------------------------------------------
# CRC16-CCITT
# ------------------------------------------------------------
def crc16_ccitt(data: bytes, init: int = 0xFFFF) -> int:
    crc = init
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


# ------------------------------------------------------------
# Frame
# ------------------------------------------------------------
@dataclass
class Frame:
    msg_type: int
    seq: int
    payload: bytes  # exactamente 6 bytes

    def pack(self) -> bytes:
        if len(self.payload) != 6:
            raise ValueError(f"payload debe ser 6 bytes, recibió {len(self.payload)}")
        # <H B B I 6s  -> 2+1+1+4+6 = 14 bytes
        header = struct.pack(
            "<HBBI6s",
            PROTOCOL.magic,
            PROTOCOL.version,
            self.msg_type & 0xFF,
            self.seq & 0xFFFFFFFF,
            self.payload,
        )
        crc = crc16_ccitt(header)
        return header + struct.pack("<H", crc)

    @classmethod
    def unpack(cls, data: bytes) -> "Frame":
        if len(data) != PROTOCOL.frame_size:
            raise ValueError(f"frame debe ser {PROTOCOL.frame_size} bytes")
        magic, version, msg_type, seq, payload, crc = struct.unpack("<HBBI6sH", data)
        if magic != PROTOCOL.magic:
            raise ValueError(f"magic inválido: 0x{magic:04X}")
        if version != PROTOCOL.version:
            raise ValueError(f"versión no soportada: {version}")
        expected = crc16_ccitt(data[:14])
        if crc != expected:
            raise ValueError(f"CRC inválido: 0x{crc:04X} != 0x{expected:04X}")
        return cls(msg_type=msg_type, seq=seq, payload=payload)


# ------------------------------------------------------------
# Helpers de alto nivel
# ------------------------------------------------------------
def build_motor_cmd(seq: int, left: int, right: int, aux: int = 0) -> bytes:
    """left, right, aux ∈ [-32768, 32767]."""
    payload = struct.pack("<hhh", left, right, aux)
    return Frame(MsgType.CMD_MOTOR, seq, payload).pack()


def build_heartbeat(seq: int) -> bytes:
    return Frame(MsgType.CMD_HEARTBEAT, seq, b"\x00" * 6).pack()


def build_emergency(seq: int) -> bytes:
    return Frame(MsgType.CMD_EMERGENCY, seq, b"\x00" * 6).pack()


def parse_ack(frame: Frame) -> int:
    """Extrae el seq acusado del payload del ACK."""
    (acked_seq,) = struct.unpack("<I", frame.payload[:4])
    return acked_seq