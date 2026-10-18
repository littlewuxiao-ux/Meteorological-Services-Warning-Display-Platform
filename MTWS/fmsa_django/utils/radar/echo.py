"""机场周边雷达回波拼图（Z7，固定半径）。"""

from __future__ import annotations

import base64
import io
import math
import threading
from typing import Dict, List, Optional, Tuple

from PIL import Image

from .tiles import lat_to_y, lon_to_x

_EARTH_M = 2 * math.pi * 6378137.0
_CACHE_MAX = 24
_cache: Dict[tuple, dict] = {}
_cache_lock = threading.Lock()


class EchoWaiting(Exception):
    def __init__(self, retry_after: float):
        super().__init__('radar echo waiting')
        self.retry_after = max(0.5, float(retry_after))


class EchoError(Exception):
    def __init__(self, message: str, not_found: bool = False):
        super().__init__(message)
        self.not_found = not_found


def meters_per_pixel(lat: float, z: int, tile_size: int) -> float:
    return _EARTH_M * math.cos(math.radians(lat)) / (float(tile_size) * (2 ** int(z)))


def tiles_for_pixel_box(
    z: int,
    tile_size: int,
    left: float,
    top: float,
    right: float,
    bottom: float,
) -> List[Tuple[int, int]]:
    n = 2 ** int(z)
    x0 = int(math.floor(left / tile_size))
    x1 = int(math.floor((right - 1e-6) / tile_size))
    y0 = int(math.floor(top / tile_size))
    y1 = int(math.floor((bottom - 1e-6) / tile_size))
    x0 = max(0, min(n - 1, x0))
    x1 = max(0, min(n - 1, x1))
    y0 = max(0, min(n - 1, y0))
    y1 = max(0, min(n - 1, y1))
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    tiles: List[Tuple[int, int]] = []
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            tiles.append((x, y))
    return tiles


def compose_echo(
    tile_png: Dict[Tuple[int, int, int], bytes],
    z: int,
    tile_size: int,
    lat: float,
    lon: float,
    radius_km: float,
    rings_km: List[int],
) -> dict:
    """把已下载的 Z 级瓦片裁成以机场为中心、半径 radius_km 的正方形图。"""
    mpp = meters_per_pixel(lat, z, tile_size)
    if mpp <= 0:
        raise EchoError('无法计算雷达比例')
    radius_px = radius_km * 1000.0 / mpp
    full_side = max(2, int(round(radius_px * 2)))
    cx = lon_to_x(lon, z) * tile_size
    cy = lat_to_y(lat, z) * tile_size
    left = cx - full_side / 2.0
    top = cy - full_side / 2.0
    tiles = tiles_for_pixel_box(z, tile_size, left, top, left + full_side, top + full_side)
    if not tiles:
        raise EchoError('机场位置超出雷达图范围')

    xs = [t[0] for t in tiles]
    ys = [t[1] for t in tiles]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    mosaic_w = (max_x - min_x + 1) * tile_size
    mosaic_h = (max_y - min_y + 1) * tile_size
    mosaic = Image.new('RGBA', (mosaic_w, mosaic_h), (0, 0, 0, 0))
    for x, y in tiles:
        raw = tile_png.get((int(z), int(x), int(y)))
        if not raw:
            continue
        tile = Image.open(io.BytesIO(raw)).convert('RGBA')
        mosaic.paste(tile, ((x - min_x) * tile_size, (y - min_y) * tile_size), tile)

    out = Image.new('RGBA', (full_side, full_side), (0, 0, 0, 0))
    dest_x = int(round(min_x * tile_size - left))
    dest_y = int(round(min_y * tile_size - top))
    out.paste(mosaic, (dest_x, dest_y), mosaic)

    side = full_side
    px_per_km = 1000.0 / mpp
    if side > 1400:
        scaled = 1400
        px_per_km *= scaled / float(side)
        out = out.resize((scaled, scaled), Image.Resampling.LANCZOS)
        side = scaled

    buf = io.BytesIO()
    out.save(buf, format='PNG')
    encoded = base64.b64encode(buf.getvalue()).decode('ascii')
    return {
        'radius_km': int(radius_km),
        'rings_km': list(rings_km),
        'z': int(z),
        'width': side,
        'height': side,
        'center_x': side / 2.0,
        'center_y': side / 2.0,
        'px_per_km': px_per_km,
        'image': f'data:image/png;base64,{encoded}',
    }


def cache_get(key: tuple) -> Optional[dict]:
    with _cache_lock:
        hit = _cache.get(key)
        return dict(hit) if hit else None


def cache_put(key: tuple, payload: dict) -> None:
    with _cache_lock:
        if key in _cache:
            _cache.pop(key, None)
        _cache[key] = dict(payload)
        while len(_cache) > _CACHE_MAX:
            _cache.pop(next(iter(_cache)))
