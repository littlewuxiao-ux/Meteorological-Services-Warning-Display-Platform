#!/usr/bin/env python3
"""
将标准 world.json (以 0°经线为中心) 转换为以 150°E 为中心、
截断线在 30°W (大西洋中部) 的 world_pacific.json。

转换规则:
  - 截断线: CUT_LON = -30°
  - 中心:   CENTER_LON = 150°E (= CUT_LON + 180°)
  - 对于 lon >= -30: new_lon = lon - 150
  - 对于 lon < -30:  new_lon = lon + 360 - 150 = lon + 210
  - 最终范围: [-180, 180]，0° 对应真实经度 150°E

需要 shapely 来正确切割跨越截断线的多边形 (主要是格陵兰)。
"""
import json, sys, pathlib, warnings

CUT_LON   = -30     # 截断线经度 (30°W)
CENTER_LON = 150    # 新中心经度 (150°E)
SHIFT      = CENTER_LON  # 减去这个值

ROOT = pathlib.Path(__file__).parent.parent
SRC  = ROOT / 'fmsa_django' / 'static' / 'geo' / 'world.json'
DST  = ROOT / 'fmsa_django' / 'static' / 'geo' / 'world_pacific.json'

# ── shapely ──────────────────────────────────────────────────────────────────
from shapely.geometry import shape, mapping, Polygon, MultiPolygon, LineString
from shapely.ops      import split, unary_union

# 截断线（垂直线，延伸至极点外）
CUT_LINE = LineString([(CUT_LON, -91), (CUT_LON, 91)])


def _shift_coords(geom, delta):
    """给 shapely 几何体的所有顶点经度加上 delta"""
    def shift_ring(coords):
        return [(x + delta, y) for x, y in coords]

    if geom.geom_type == 'Polygon':
        ext = shift_ring(geom.exterior.coords)
        holes = [shift_ring(r.coords) for r in geom.interiors]
        return Polygon(ext, holes)
    elif geom.geom_type == 'MultiPolygon':
        return MultiPolygon([_shift_coords(p, delta) for p in geom.geoms])
    return geom


def transform_geometry(geom_dict):
    """将单个 GeoJSON geometry 做截断线切割 + 经度偏移"""
    try:
        geom = shape(geom_dict)
        if not geom.is_valid:
            geom = geom.buffer(0)

        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            try:
                pieces = split(geom, CUT_LINE).geoms
            except Exception:
                pieces = [geom]

        transformed = []
        for piece in pieces:
            cx = piece.centroid.x
            # 西侧 (< 截断线) → +210；东侧 → -150
            delta = (360 - SHIFT) if cx < CUT_LON else -SHIFT
            transformed.append(_shift_coords(piece, delta))

        result = unary_union(transformed)
        return mapping(result)

    except Exception as exc:
        print(f'  警告：跳过处理，回退原始 geometry: {exc}', file=sys.stderr)
        return geom_dict


# ── 主处理 ────────────────────────────────────────────────────────────────────
print(f'读取: {SRC}')
with open(SRC, 'r', encoding='utf-8') as f:
    world = json.load(f)

total = len(world['features'])
print(f'共 {total} 个 feature，开始转换 ...')

for i, feature in enumerate(world['features']):
    feature['geometry'] = transform_geometry(feature['geometry'])
    if (i + 1) % 50 == 0:
        print(f'  {i + 1}/{total}')

print(f'写出: {DST}')
with open(DST, 'w', encoding='utf-8') as f:
    json.dump(world, f, ensure_ascii=False, separators=(',', ':'))

size_kb = DST.stat().st_size // 1024
print(f'完成！文件大小: {size_kb} KB')
