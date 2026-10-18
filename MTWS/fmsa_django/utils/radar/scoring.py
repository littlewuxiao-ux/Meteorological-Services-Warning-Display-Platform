"""按环面积比 M_n 与数量档查表得到 R/Y/G。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .config_defaults import ALERT_RANK, ring_area_ratios


def higher_alert(a: str, b: str) -> str:
    return a if ALERT_RANK.get(a, 0) >= ALERT_RANK.get(b, 0) else b


def find_bin_for_count(c_n: float, m_n: float, bins: List[dict]) -> Optional[int]:
    """像素数为 0 不入档。下限为 0 时按开区间，避免 0 个像素落入最低档。"""
    if c_n <= 0:
        return None
    for i, b in enumerate(bins):
        lo = float(b['lo']) * m_n
        hi = b['hi']
        lo_open = bool(b.get('lo_open'))
        if hi is None:
            # 正无穷档：C >= lo（N4 的 21*M）
            if c_n >= lo:
                return i
            continue
        hi_v = float(hi) * m_n
        if lo_open:
            if lo < c_n <= hi_v:
                return i
        else:
            if lo <= c_n <= hi_v:
                return i
    return None


def score_rings(
    pixel_counts_by_ring: List[int],
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """
    pixel_counts_by_ring: 各环斑块像素数 C_n。
    返回 {
      'alerts': [{'ring_index', 'bin_id', 'color', 'count', 'M'}...],
      'highest': 'R'|'Y'|'G'|'N'
    }
    """
    rings = config['rings_km']
    bins = config['count_bins']
    matrix = config['color_matrix']
    ratios = ring_area_ratios(rings)
    alerts = []
    highest = 'N'
    for n, c_n in enumerate(pixel_counts_by_ring):
        if n >= len(ratios):
            break
        m_n = ratios[n]
        bi = find_bin_for_count(float(c_n), m_n, bins)
        if bi is None:
            continue
        color = matrix[bi][n] if bi < len(matrix) and n < len(matrix[bi]) else 'N'
        if color not in ('R', 'Y', 'G'):
            continue
        alerts.append({
            'ring_index': n,
            'ring_km': rings[n],
            'bin_id': bins[bi].get('id', f'N{bi}'),
            'color': color,
            'count': int(c_n),
            'M': round(m_n, 4),
        })
        highest = higher_alert(highest, color)
    return {'alerts': alerts, 'highest': highest}


def bin_pixels_to_rings_and_azimuth(
    pixels: List[dict],
    rings_km: List[List[float]],
    azimuth_bins: int = 36,
) -> Tuple[List[int], List[dict]]:
    """
    返回 (C_n 列表, 方位扇区统计列表)。
    扇区统计：每个 ring × az_bin → count/mean/max（供入库，前端暂不展示）。
    """
    n_rings = len(rings_km)
    counts = [0] * n_rings
    # stats key (ring, az) -> list of dbz
    buckets: Dict[Tuple[int, int], List[float]] = {}
    az_w = 360.0 / max(1, azimuth_bins)

    for p in pixels:
        dist = float(p['dist_km'])
        dbz = float(p['dbz'])
        az = float(p['az_deg'])
        ring_i = None
        for i, (r_in, r_out) in enumerate(rings_km):
            if r_in <= dist < r_out or (i == n_rings - 1 and r_in <= dist <= r_out):
                ring_i = i
                break
        if ring_i is None:
            continue
        counts[ring_i] += 1
        az_i = int(az // az_w) % azimuth_bins
        buckets.setdefault((ring_i, az_i), []).append(dbz)

    sector_stats = []
    for (ring_i, az_i), vals in buckets.items():
        arr = np.asarray(vals, dtype=np.float32)
        sector_stats.append({
            'ring_index': ring_i,
            'azimuth_bin': az_i,
            'azimuth_deg': [az_i * az_w, (az_i + 1) * az_w],
            'count': int(arr.size),
            'mean_dbz': float(arr.mean()),
            'max_dbz': float(arr.max()),
        })
    return counts, sector_stats
