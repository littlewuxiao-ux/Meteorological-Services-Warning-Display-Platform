"""PNG 色标 → dBZ 反演与连通斑块。"""

from __future__ import annotations

import io
import json
import logging
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

from .tiles import haversine_km, pixel_center_lonlat

logger = logging.getLogger('fmsa.radar.inversion')

_LUT_PATH = Path(__file__).with_name('universal_blue_lut.json')
_COLOR_TO_DBZ: Optional[Dict[Tuple[int, int, int], float]] = None
_LUT_RGB: Optional[np.ndarray] = None
_LUT_DBZ: Optional[np.ndarray] = None


def _load_lut() -> None:
    global _COLOR_TO_DBZ, _LUT_RGB, _LUT_DBZ
    if _COLOR_TO_DBZ is not None:
        return
    with open(_LUT_PATH, encoding='utf-8') as f:
        rows = json.load(f)
    mapping: Dict[Tuple[int, int, int], float] = {}
    rgbs = []
    dbzs = []
    for row in rows:
        r, g, b, a = row['rgba']
        dbz = float(row['dbz'])
        if a == 0 or dbz <= -32:
            continue
        key = (r, g, b)
        # 同色取较大 dbz（表尾有重复）
        if key not in mapping or dbz > mapping[key]:
            mapping[key] = dbz
        rgbs.append([r, g, b])
        dbzs.append(dbz)
    _COLOR_TO_DBZ = mapping
    _LUT_RGB = np.asarray(rgbs, dtype=np.int16)
    _LUT_DBZ = np.asarray(dbzs, dtype=np.float32)


def png_to_dbz(png_bytes: bytes) -> np.ndarray:
    """返回 float32 阵列，无回波为 nan。"""
    _load_lut()
    assert _COLOR_TO_DBZ is not None and _LUT_RGB is not None and _LUT_DBZ is not None
    img = Image.open(io.BytesIO(png_bytes)).convert('RGBA')
    arr = np.asarray(img)
    h, w, _ = arr.shape
    rgb = arr[:, :, :3].astype(np.int16)
    alpha = arr[:, :, 3]
    flat = rgb.reshape(-1, 3)
    # 先 unique 再映射，避免千万次最近邻
    uniq, inv = np.unique(flat, axis=0, return_inverse=True)
    mapped = np.full(len(uniq), np.nan, dtype=np.float32)
    for i, (r, g, b) in enumerate(uniq):
        key = (int(r), int(g), int(b))
        if key in _COLOR_TO_DBZ:
            mapped[i] = _COLOR_TO_DBZ[key]
            continue
        # 最近邻（容 JPEG/平滑误差）
        diff = _LUT_RGB.astype(np.int32) - np.array([r, g, b], dtype=np.int32)
        d2 = np.sum(diff * diff, axis=1)
        j = int(np.argmin(d2))
        if d2[j] <= 3 * 12 * 12:  # 每通道约 ±12
            mapped[i] = _LUT_DBZ[j]
    out = mapped[inv].reshape(h, w)
    out[alpha < 10] = np.nan
    return out


def label_connected_8(mask: np.ndarray) -> Tuple[np.ndarray, int]:
    """8 连通标注，返回 (labels, count)。labels 从 1 起。"""
    h, w = mask.shape
    labels = np.zeros((h, w), dtype=np.int32)
    current = 0
    neighbors = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    for i in range(h):
        for j in range(w):
            if not mask[i, j] or labels[i, j]:
                continue
            current += 1
            stack = [(i, j)]
            labels[i, j] = current
            while stack:
                y, x = stack.pop()
                for dy, dx in neighbors:
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and labels[ny, nx] == 0:
                        labels[ny, nx] = current
                        stack.append((ny, nx))
    return labels, current


def keep_blobs(mask: np.ndarray, min_pixels: int) -> np.ndarray:
    """保留 8 连通且像素数 >= min_pixels 的斑块。"""
    if not mask.any():
        return mask
    labels, n = label_connected_8(mask)
    if n == 0:
        return np.zeros_like(mask, dtype=bool)
    counts = np.bincount(labels.ravel())
    keep = counts >= int(min_pixels)
    keep[0] = False
    return keep[labels]


def count_ge_dbz_in_radius(
    dbz_grid: np.ndarray,
    z: int,
    tile_x: int,
    tile_y: int,
    airport_lat: float,
    airport_lon: float,
    radius_km: float,
    threshold: float,
    tile_size: int,
) -> int:
    """单瓦片内：机场 radius 内 >= threshold 的像素数。"""
    ys, xs = np.where(np.isfinite(dbz_grid) & (dbz_grid >= threshold))
    if len(xs) == 0:
        return 0
    count = 0
    for py, px in zip(ys, xs):
        lon, lat = pixel_center_lonlat(z, tile_x, tile_y, int(px), int(py), tile_size)
        if haversine_km(airport_lat, airport_lon, lat, lon) <= radius_km:
            count += 1
    return count


def max_dbz_in_radius(
    dbz_grid: np.ndarray,
    z: int,
    tile_x: int,
    tile_y: int,
    airport_lat: float,
    airport_lon: float,
    radius_km: float,
    tile_size: int,
) -> float:
    ys, xs = np.where(np.isfinite(dbz_grid))
    if len(xs) == 0:
        return float('nan')
    best = float('nan')
    for py, px in zip(ys, xs):
        lon, lat = pixel_center_lonlat(z, tile_x, tile_y, int(px), int(py), tile_size)
        if haversine_km(airport_lat, airport_lon, lat, lon) <= radius_km:
            v = float(dbz_grid[py, px])
            if not np.isfinite(best) or v > best:
                best = v
    return best


def collect_blob_pixels(
    dbz_grid: np.ndarray,
    z: int,
    tile_x: int,
    tile_y: int,
    airport_lat: float,
    airport_lon: float,
    radius_km: float,
    threshold: float,
    min_blob_pixels: int,
    tile_size: int,
) -> List[dict]:
    """
    返回半径内有效斑块像素列表：
    [{dbz, dist_km, az_deg, lat, lon}, ...]
    斑块在整瓦上做连通，再过滤半径。
    """
    mask = np.isfinite(dbz_grid) & (dbz_grid >= threshold)
    if not mask.any():
        return []
    kept = keep_blobs(mask, min_blob_pixels)
    ys, xs = np.where(kept)
    pixels = []
    for py, px in zip(ys, xs):
        lon, lat = pixel_center_lonlat(z, tile_x, tile_y, int(px), int(py), tile_size)
        dist = haversine_km(airport_lat, airport_lon, lat, lon)
        if dist > radius_km:
            continue
        # 方位：0=北，顺时针
        dlon = math_radians_delta(airport_lon, lon)
        y = math.sin(dlon) * math.cos(math.radians(lat))
        x = math.cos(math.radians(airport_lat)) * math.sin(math.radians(lat)) - (
            math.sin(math.radians(airport_lat)) * math.cos(math.radians(lat)) * math.cos(dlon)
        )
        az = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0
        pixels.append({
            'dbz': float(dbz_grid[py, px]),
            'dist_km': float(dist),
            'az_deg': float(az),
            'lat': float(lat),
            'lon': float(lon),
        })
    return pixels


def math_radians_delta(lon1: float, lon2: float) -> float:
    return math.radians(lon2 - lon1)
