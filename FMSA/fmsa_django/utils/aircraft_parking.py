"""停场表读写：一机场一行，parking 为 [是否停场, ...机号]。"""

from __future__ import annotations

import time
from typing import Optional


def default_parking_list() -> list:
    return [False]


def parking_is_on(payload) -> bool:
    if isinstance(payload, (list, tuple)) and payload:
        return bool(payload[0])
    return False


def parking_ac_regs(payload) -> list:
    if not isinstance(payload, (list, tuple)) or len(payload) < 2:
        return []
    out = []
    seen = set()
    for item in payload[1:]:
        code = str(item or '').strip()
        if not code or code in seen:
            continue
        seen.add(code)
        out.append(code)
    return out


def parking_payload(regs) -> list:
    codes = []
    seen = set()
    for item in regs or []:
        code = str(item or '').strip()
        if not code or code in seen:
            continue
        seen.add(code)
        codes.append(code)
    codes.sort()
    if not codes:
        return [False]
    return [True] + codes


def normalize_intervals(raw, now_ms: Optional[int] = None) -> list:
    now = int(now_ms if now_ms is not None else time.time() * 1000)
    week_ago = now - 7 * 24 * 3600 * 1000
    items = []
    for row in raw or []:
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            start, end = row[0], row[1]
        else:
            continue
        try:
            start = int(start)
        except (TypeError, ValueError):
            continue
        if end is None:
            items.append([start, None])
            continue
        try:
            end = int(end)
        except (TypeError, ValueError):
            continue
        if end < start:
            start, end = end, start
        if end < week_ago:
            continue
        items.append([start, end])
    items.sort(key=lambda item: (item[0], item[1] is not None, item[1] or 0))
    merged = []
    for start, end in items:
        if not merged:
            merged.append([start, end])
            continue
        prev_s, prev_e = merged[-1]
        if prev_e is None:
            if end is None:
                merged[-1][0] = min(prev_s, start)
            continue
        if end is None:
            if start <= prev_e:
                merged[-1] = [min(prev_s, start), None]
            else:
                merged.append([start, None])
            continue
        if start <= prev_e:
            merged[-1][1] = max(prev_e, end)
        else:
            merged.append([start, end])
    return merged


def interval_contains(start, end, obs_ms: int, now_ms: Optional[int] = None) -> bool:
    try:
        obs = int(obs_ms)
        lo = int(start)
    except (TypeError, ValueError):
        return False
    if end is None:
        hi = int(now_ms if now_ms is not None else time.time() * 1000)
    else:
        try:
            hi = int(end)
        except (TypeError, ValueError):
            return False
    return lo <= obs <= hi


def intervals_overlap_range(intervals, start_ms: int, end_ms: int, now_ms: Optional[int] = None) -> bool:
    for start, end in intervals or []:
        hi = int(now_ms if now_ms is not None else time.time() * 1000) if end is None else end
        try:
            lo = int(start)
            hi = int(hi)
        except (TypeError, ValueError):
            continue
        if max(lo, int(start_ms)) <= min(hi, int(end_ms)):
            return True
    return False


def occupancy_airports():
    from runtime_db.models import AircraftParkingInfo

    codes = set()
    for row in AircraftParkingInfo.objects.all().only('airport_4code', 'parking'):
        if parking_is_on(row.parking) and row.airport_4code:
            codes.add(str(row.airport_4code).strip().upper())
    return codes


def latest_fetched_at() -> Optional[int]:
    from django.db.models import Max
    from runtime_db.models import AircraftParkingInfo

    value = AircraftParkingInfo.objects.aggregate(Max('fetched_at')).get('fetched_at__max')
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
