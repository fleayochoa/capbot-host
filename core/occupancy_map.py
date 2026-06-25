"""Carga de mapas de ocupación (.pgm + .yaml de ROS) y transformaciones de coordenadas.

Módulo puro (sin Qt) para poder testearlo aislado. Replica la convención de
nav2_map_server:
  * El .pgm (formato binario P5) contiene la rejilla de ocupación en escala de
    grises: 255 = libre, 0 = ocupado (con `negate:0`).
  * El .yaml aporta `resolution` (m/px) y `origin` [ox, oy, theta]: la esquina
    INFERIOR-IZQUIERDA de la imagen en coordenadas del mundo (frame map).

Transformaciones (y se invierte porque la fila 0 del PGM es la parte superior):
    px = (x - ox) / res
    py = H - (y - oy) / res
"""
from __future__ import annotations

from dataclasses import dataclass


def _read_pgm_tokens(raw: bytes, count: int) -> tuple[list[bytes], int]:
    """Lee `count` tokens ASCII de la cabecera PGM saltando comentarios (#...).

    Devuelve (tokens, offset) donde offset apunta al byte siguiente al último
    token leído (justo antes de los datos binarios).
    """
    tokens: list[bytes] = []
    i = 0
    n = len(raw)
    while len(tokens) < count:
        # Saltar espacios en blanco
        while i < n and raw[i:i + 1].isspace():
            i += 1
        # Saltar comentarios hasta fin de línea
        if i < n and raw[i:i + 1] == b"#":
            while i < n and raw[i:i + 1] not in (b"\n", b"\r"):
                i += 1
            continue
        start = i
        while i < n and not raw[i:i + 1].isspace():
            i += 1
        if start == i:
            break
        tokens.append(raw[start:i])
    return tokens, i


@dataclass
class OccupancyMap:
    width: int
    height: int
    resolution: float
    origin_x: float
    origin_y: float
    pixels: bytes  # width*height bytes, fila 0 = arriba; valor en [0,255]

    # ---- Transformaciones mundo <-> píxel ----
    def world_to_pixel(self, x: float, y: float) -> tuple[float, float]:
        px = (x - self.origin_x) / self.resolution
        py = self.height - (y - self.origin_y) / self.resolution
        return px, py

    def pixel_to_world(self, px: float, py: float) -> tuple[float, float]:
        x = self.origin_x + px * self.resolution
        y = self.origin_y + (self.height - py) * self.resolution
        return x, y

    # ---- Extensión del mapa en el mundo (m) ----
    @property
    def world_width(self) -> float:
        return self.width * self.resolution

    @property
    def world_height(self) -> float:
        return self.height * self.resolution


def _coerce(val: str):
    try:
        return float(val)
    except ValueError:
        return val


def _parse_yaml(path: str) -> dict:
    """Parser mínimo del map.yaml de ROS (sin PyYAML).

    Solo necesitamos `resolution` (float) y `origin` (lista de 3 floats). El
    resto de claves se ignoran. Soporta `clave: valor`, listas inline
    `[a, b, c]` y listas en bloque (ítems `- x` en líneas siguientes), que es
    como nav2_map_server escribe el `origin`.
    """
    out: dict = {}
    pending_key = None  # clave esperando ítems de una lista en bloque
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.split("#", 1)[0].rstrip()
            stripped = line.strip()
            if not stripped:
                continue
            # Ítem de lista en bloque: "- valor"
            if stripped.startswith("- ") or stripped == "-":
                if pending_key is not None:
                    out.setdefault(pending_key, []).append(
                        _coerce(stripped[1:].strip()))
                continue
            if ":" not in stripped:
                continue
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()
            if not val:
                # Posible lista en bloque a continuación
                pending_key = key
                out[key] = []
                continue
            pending_key = None
            if val.startswith("[") and val.endswith("]"):
                items = [v.strip() for v in val[1:-1].split(",") if v.strip()]
                out[key] = [_coerce(v) for v in items]
            else:
                out[key] = _coerce(val)
    return out


def load_markers_db(path: str) -> list:
    """Parse a markers_db.yaml. Returns list of dicts with keys id, x, y, yaw."""
    markers: list = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return markers
    current: dict | None = None
    for raw in lines:
        line = raw.split("#", 1)[0].rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- id:"):
            if current is not None:
                markers.append(current)
            try:
                current = {"id": int(stripped.split(":", 1)[1].strip())}
            except (ValueError, IndexError):
                current = None
        elif current is not None and ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()
            if key in ("x", "y", "z", "roll", "pitch", "yaw"):
                try:
                    current[key] = float(val)
                except ValueError:
                    pass
    if current is not None:
        markers.append(current)
    return markers


def load_map(pgm_path: str, yaml_path: str) -> OccupancyMap:
    """Carga un mapa de ocupación desde su .pgm (P5) y su .yaml asociado."""
    meta = _parse_yaml(yaml_path)
    resolution = float(meta.get("resolution", 0.05))
    origin = meta.get("origin", [0.0, 0.0, 0.0])
    origin_x = float(origin[0]) if len(origin) > 0 else 0.0
    origin_y = float(origin[1]) if len(origin) > 1 else 0.0

    with open(pgm_path, "rb") as f:
        raw = f.read()

    tokens, offset = _read_pgm_tokens(raw, 4)
    if len(tokens) < 4 or tokens[0] != b"P5":
        raise ValueError(f"PGM no soportado (se esperaba binario P5): {pgm_path}")
    width = int(tokens[1])
    height = int(tokens[2])
    # tokens[3] = maxval. Tras él hay UN byte de separación antes de los datos.
    data_start = offset + 1
    expected = width * height
    pixels = raw[data_start:data_start + expected]
    if len(pixels) < expected:
        raise ValueError(
            f"PGM truncado: {len(pixels)} bytes, se esperaban {expected}")

    return OccupancyMap(
        width=width,
        height=height,
        resolution=resolution,
        origin_x=origin_x,
        origin_y=origin_y,
        pixels=pixels,
    )
