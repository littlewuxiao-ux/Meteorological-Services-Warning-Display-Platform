"""Web 墨卡托瓦片坐标与机场覆盖并集。"""

from __future__ import annotations

import math
from typing import Iterable, List, Set, Tuple

TileXY = Tuple[int, int]


def clamp_lat(lat: float) -> float:
    return max(min(lat, 85.05112878), -85.05112878)


def lon_to_x(lon: float, z: int) -> float:
    n = 2 ** z
    return (lon + 180.0) / 360.0 * n


def lat_to_y(lat: float, z: int) -> float:
    lat = clamp_lat(lat)
    n = 2 ** z
    lat_rad = math.radians(lat)
    return (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n


def tile_bounds(z: int, x: int, y: int) -> Tuple[float, float, float, float]:
    """返回 (west, south, east, north) 度。"""
    n = 2 ** z
    west = x / n * 360.0 - 180.0
    east = (x + 1) / n * 360.0 - 180.0
    north = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    south = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return west, south, east, north


def pixel_center_lonlat(z: int, x: int, y: int, px: int, py: int, tile_size: int) -> Tuple[float, float]:
    """瓦片内像素中心的经纬度。"""
    n = 2 ** z
    fx = (x + (px + 0.5) / tile_size) / n
    fy = (y + (py + 0.5) / tile_size) / n
    lon = fx * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * fy))))
    return lon, lat


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def tiles_covering_radius(lat: float, lon: float, radius_km: float, z: int) -> Set[TileXY]:
    """覆盖机场 radius_km 圆的 z 级瓦片集合（用 bbox 近似）。"""
    # 1° lat ≈ 111 km；经度按纬度缩放
    dlat = radius_km / 111.0
    cos_lat = max(0.2, abs(math.cos(math.radians(lat))))
    dlon = radius_km / (111.0 * cos_lat)
    lat1, lat2 = lat - dlat, lat + dlat
    lon1, lon2 = lon - dlon, lon + dlon
    return tiles_in_bbox(lon1, lat1, lon2, lat2, z)


def tiles_in_bbox(lon1: float, lat1: float, lon2: float, lat2: float, z: int) -> Set[TileXY]:
    n = 2 ** z
    x1 = int(math.floor(lon_to_x(min(lon1, lon2), z)))
    x2 = int(math.floor(lon_to_x(max(lon1, lon2), z)))
    y_a = lat_to_y(min(lat1, lat2), z)
    y_b = lat_to_y(max(lat1, lat2), z)
    y1 = int(math.floor(min(y_a, y_b)))
    y2 = int(math.floor(max(y_a, y_b)))
    x1 = max(0, min(n - 1, x1))
    x2 = max(0, min(n - 1, x2))
    y1 = max(0, min(n - 1, y1))
    y2 = max(0, min(n - 1, y2))
    out: Set[TileXY] = set()
    for x in range(x1, x2 + 1):
        for y in range(y1, y2 + 1):
            out.add((x, y))
    return out


def all_world_tiles(z: int) -> Set[TileXY]:
    n = 2 ** z
    return {(x, y) for x in range(n) for y in range(n)}


def union_tiles(sets: Iterable[Set[TileXY]]) -> Set[TileXY]:
    out: Set[TileXY] = set()
    for s in sets:
        out |= s
    return out


def build_airport_tile_index(
    airports: List[dict],
    radius_km: float,
    zooms: List[int],
) -> dict:
    """
    airports: [{'code','lat','lon'}, ...]
    返回 {
      'by_airport': {code: {str(z): [[x,y],...]}},
      'unions': {str(z): [[x,y],...]}
    }
    """
    by_airport = {}
    unions = {str(z): set() for z in zooms}
    for ap in airports:
        code = ap['code']
        lat, lon = float(ap['lat']), float(ap['lon'])
        entry = {}
        for z in zooms:
            tiles = tiles_covering_radius(lat, lon, radius_km, z)
            entry[str(z)] = sorted([list(t) for t in tiles])
            unions[str(z)] |= tiles
        by_airport[code] = entry
    return {
        'by_airport': by_airport,
        'unions': {z: sorted([list(t) for t in tiles]) for z, tiles in unions.items()},
        'radius_km': radius_km,
        'zooms': zooms,
    }
