"""雷达告警默认可配置项（【】内参数均可在设置页修改）。"""

from __future__ import annotations

import math
from copy import deepcopy
from typing import Any, Dict, List


# 综合告警等级排序：数字越大越严重
ALERT_RANK = {'N': 0, 'G': 1, 'Y': 2, 'R': 3}


def _default_rings_km() -> List[List[float]]:
    return [
        [0, 8],
        [8, 16],
        [16, 30],
        [30, 50],
        [50, 100],
        [100, 150],
        [150, 200],
        [200, 250],
    ]


def _default_count_bins() -> List[dict]:
    return [
        {'id': 'N0', 'lo': 1, 'hi': 5, 'lo_open': False},
        {'id': 'N1', 'lo': 6, 'hi': 10, 'lo_open': False},
        {'id': 'N2', 'lo': 11, 'hi': 15, 'lo_open': False},
        {'id': 'N3', 'lo': 16, 'hi': 20, 'lo_open': False},
        {'id': 'N4', 'lo': 21, 'hi': None, 'lo_open': False},
    ]


def _default_color_matrix() -> List[List[str]]:
    return [
        ['R', 'Y', 'Y', 'Y', 'G', 'G', 'G', 'G'],  # N0
        ['R', 'R', 'Y', 'Y', 'Y', 'G', 'G', 'G'],  # N1
        ['R', 'R', 'R', 'Y', 'Y', 'Y', 'G', 'G'],  # N2
        ['R', 'R', 'R', 'R', 'Y', 'Y', 'Y', 'G'],  # N3
        ['R', 'R', 'R', 'R', 'R', 'Y', 'Y', 'Y'],  # N4
    ]


def _default_z7_levels() -> List[Dict[str, Any]]:
    """z7 两个阈值档：各自独立的 dBZ / 斑块最少像素 / 数量档 / 颜色矩阵。"""
    return [
        {
            'label': '阈值档A',
            'dbz': 33,
            'min_blob_pixels': 5,
            'count_bins': deepcopy(_default_count_bins()),
            'color_matrix': deepcopy(_default_color_matrix()),
        },
        {
            'label': '阈值档B',
            'dbz': 41,
            'min_blob_pixels': 5,
            'count_bins': deepcopy(_default_count_bins()),
            'color_matrix': deepcopy(_default_color_matrix()),
        },
    ]


def default_radar_config() -> Dict[str, Any]:
    """返回一份可写入数据库的默认配置。"""
    rings_km = _default_rings_km()
    z7_levels = _default_z7_levels()
    return {
        'enabled': True,
        'interval_minutes': 15,
        'radius_km': 250,
        'overview_z': 3,
        'mid_z': 5,
        'final_z': 7,
        'tile_size': 256,
        'rate_limit_per_minute': 80,
        # 兼容旧字段：由 z7_levels 同步
        'dbz_thresholds': [int(z7_levels[0]['dbz']), int(z7_levels[1]['dbz'])],
        'min_blob_pixels': int(z7_levels[0]['min_blob_pixels']),
        'count_bins': deepcopy(z7_levels[0]['count_bins']),
        'color_matrix': deepcopy(z7_levels[0]['color_matrix']),
        # z3 初筛
        'screen_dbz': 25,
        'z3_min_pixels': 1,
        # z3 强回波捷径：满足则跳过 z5，直进 z7
        'z3_skip_dbz': 41,
        'z3_skip_min_pixels': 3,
        # z5 复核
        'z5_screen_dbz': 25,
        'z5_min_pixels': 8,
        'azimuth_bins': 36,
        'rings_km': rings_km,
        'z7_levels': z7_levels,
        'smooth': 0,
        'snow': 0,
        'color_scheme': 2,
        # 计入告警的颜色：默认红、黄（Y 及以上）
        'alarm_colors': ['R', 'Y'],
    }


def ring_area_ratios(rings_km: List[List[float]]) -> List[float]:
    """M_n = S_n / S_0，S = π(r_out² - r_in²)。"""
    if not rings_km:
        return []
    areas = []
    for r_in, r_out in rings_km:
        areas.append(math.pi * (float(r_out) ** 2 - float(r_in) ** 2))
    s0 = areas[0] if areas[0] > 0 else 1.0
    return [a / s0 for a in areas]


def max_ring_radius_km(rings_km: List[List[float]] | None) -> float:
    """取各环外半径最大值，作为计算半径。"""
    if not rings_km:
        return float(default_radar_config()['radius_km'])
    outs = []
    for pair in rings_km:
        if not pair or len(pair) < 2:
            continue
        try:
            outs.append(float(pair[1]))
        except (TypeError, ValueError):
            continue
    return max(outs) if outs else float(default_radar_config()['radius_km'])


def _normalize_z7_levels(cfg: Dict[str, Any], defaults: Dict[str, Any]) -> List[Dict[str, Any]]:
    """保证始终有两个阈值档；旧配置（单一矩阵）自动拆成两档。"""
    raw = cfg.get('z7_levels')
    base_bins = cfg.get('count_bins') or defaults['count_bins']
    base_matrix = cfg.get('color_matrix') or defaults['color_matrix']
    blob = cfg.get('min_blob_pixels', defaults['min_blob_pixels'])
    ths = cfg.get('dbz_thresholds') or defaults['dbz_thresholds']

    def _one(src: dict | None, idx: int) -> Dict[str, Any]:
        d = defaults['z7_levels'][min(idx, 1)]
        src = src or {}
        dbz = src.get('dbz', ths[idx] if idx < len(ths) else d['dbz'])
        return {
            'label': src.get('label') or d['label'],
            'dbz': float(dbz),
            'min_blob_pixels': int(src.get('min_blob_pixels', blob)),
            'count_bins': deepcopy(src.get('count_bins') or base_bins),
            'color_matrix': deepcopy(src.get('color_matrix') or base_matrix),
        }

    if isinstance(raw, list) and raw:
        levels = [_one(raw[i] if i < len(raw) else None, i) for i in range(2)]
    else:
        levels = [_one(None, 0), _one(None, 1)]
    return levels


def _normalize_alarm_colors(raw, present: bool) -> List[str]:
    """勾选集始终是从红往下的一段：仅红、红黄、或红黄绿。未保存过则默认红黄。"""
    if not present or not isinstance(raw, (list, tuple)):
        return ['R', 'Y']
    picked = {c for c in raw if c in ('R', 'Y', 'G')}
    if 'G' in picked:
        return ['R', 'Y', 'G']
    if 'Y' in picked:
        return ['R', 'Y']
    if 'R' in picked:
        return ['R']
    return []


def merge_config(stored: Dict[str, Any] | None) -> Dict[str, Any]:
    """用默认值补齐缺失键；radius_km 始终等于最大环外半径。"""
    cfg = default_radar_config()
    if not stored:
        out = cfg
    else:
        out = deepcopy(cfg)
        out.update(stored)
        for key in ('rings_km', 'count_bins', 'color_matrix', 'dbz_thresholds'):
            if key not in out or out[key] is None:
                out[key] = cfg[key]
        # 仅当库中已有 z7_levels 时沿用；否则由扁平字段迁移生成，避免默认档盖住旧阈值
        if not stored.get('z7_levels'):
            out['z7_levels'] = None
    out['z7_levels'] = _normalize_z7_levels(out, cfg)
    # 同步兼容字段（列表页 / 旧逻辑）
    out['dbz_thresholds'] = [int(out['z7_levels'][0]['dbz']), int(out['z7_levels'][1]['dbz'])]
    out['min_blob_pixels'] = int(out['z7_levels'][0]['min_blob_pixels'])
    out['count_bins'] = deepcopy(out['z7_levels'][0]['count_bins'])
    out['color_matrix'] = deepcopy(out['z7_levels'][0]['color_matrix'])
    out['radius_km'] = max_ring_radius_km(out.get('rings_km'))
    stored_has_colors = isinstance(stored, dict) and 'alarm_colors' in stored
    out['alarm_colors'] = _normalize_alarm_colors(out.get('alarm_colors'), stored_has_colors)
    return out
