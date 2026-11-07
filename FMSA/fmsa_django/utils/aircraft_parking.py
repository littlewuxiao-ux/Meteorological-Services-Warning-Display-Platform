"""停场表读写：一机场一行，parking 为 [是否停场, ...机号]。"""

from __future__ import annotations

import hashlib
import json
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
    from runtime_db.models import AircraftParkingInfo, AircraftParkingSync

    row = AircraftParkingSync.objects.filter(pk=1).first()
    if row is not None and row.fetched_at is not None:
        try:
            return int(row.fetched_at)
        except (TypeError, ValueError):
            pass
    value = AircraftParkingInfo.objects.aggregate(Max('fetched_at')).get('fetched_at__max')
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def fingerprint_hash(payload) -> str:
    raw = json.dumps(payload, separators=(',', ':'), ensure_ascii=True)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def tail_fingerprint(rows) -> str:
    items = [list(row) for row in (rows or [])]
    items.sort(key=lambda row: (str(row[0] or ''), str(row[1] or ''), str(row[2] or ''), row[3] or 0, row[4] or 0))
    return fingerprint_hash(items)


def batch_fingerprint(tail_fps: dict) -> str:
    return fingerprint_hash([[key, tail_fps[key]] for key in sorted(tail_fps or {})])


def _as_airport(value) -> Optional[str]:
    text = str(value or '').strip().upper()
    return text if len(text) == 4 else None


def parking_segments_from_events(
    events,
    now_ms: int,
    seed_airport=None,
    seed_start=None,
    in_air=False,
):
    """按一架飞机的 ATA/ATD 回放停场段。events: (when, order, kind, airport)。"""
    now = int(now_ms)
    airport = _as_airport(seed_airport)
    start = int(seed_start) if airport and seed_start is not None else None
    if airport and start is None:
        airport = None
    segments = []

    def close(when):
        nonlocal airport, start
        if not airport or start is None:
            airport = None
            start = None
            return
        end = int(when)
        lo, hi = (start, end) if start <= end else (end, start)
        if hi > lo:
            segments.append([airport, int(lo), int(hi)])
        airport = None
        start = None

    def open_at(place, when):
        nonlocal airport, start
        code = _as_airport(place)
        if not code:
            return
        if airport == code:
            return
        if airport:
            close(when)
        airport = code
        start = int(when)

    for when, _order, kind, place in sorted(events or []):
        if int(when) > now:
            continue
        if kind == 'ata':
            open_at(place, when)
        elif kind == 'atd':
            if airport:
                close(when)

    if in_air:
        if airport:
            leave_at = None
            for when, _order, kind, place in sorted(events or []):
                if kind == 'atd' and _as_airport(place) == airport and int(when) <= now:
                    leave_at = int(when)
            close(leave_at if leave_at is not None else now)
        return segments, None

    if airport and start is not None:
        segments.append([airport, int(start), None])
        return segments, airport
    return segments, None


def normalize_tail_segments(raw, now_ms: Optional[int] = None) -> list:
    by_airport = {}
    for item in raw or []:
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue
        airport = _as_airport(item[0])
        if not airport:
            continue
        by_airport.setdefault(airport, []).append([item[1], item[2]])
    out = []
    for airport, items in by_airport.items():
        for start, end in normalize_intervals(items, now_ms):
            out.append([airport, start, end])
    out.sort(key=lambda row: (row[1], row[0], row[2] is not None, row[2] or 0))
    return out


def splice_tail_segments(stored, fresh, window_lo, now_ms: Optional[int] = None) -> list:
    if window_lo is None:
        return normalize_tail_segments(fresh if fresh else stored, now_ms)
    kept = []
    lo = int(window_lo)
    for item in stored or []:
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue
        end = item[2]
        if end is None:
            continue
        try:
            if int(end) < lo:
                kept.append(list(item))
        except (TypeError, ValueError):
            continue
    return normalize_tail_segments(kept + list(fresh or []), now_ms)


def union_airport_intervals(tail_segments, now_ms: Optional[int] = None) -> dict:
    by_airport = {}
    for segments in (tail_segments or {}).values():
        for item in segments or []:
            if not isinstance(item, (list, tuple)) or len(item) < 3:
                continue
            airport = _as_airport(item[0])
            if not airport:
                continue
            by_airport.setdefault(airport, []).append([item[1], item[2]])
    return {code: normalize_intervals(items, now_ms) for code, items in by_airport.items()}


def occupancy_from_tails(tail_segments) -> dict:
    occupancy = {}
    for ac_reg, segments in (tail_segments or {}).items():
        key = str(ac_reg or '').strip()
        if not key:
            continue
        open_row = None
        for item in segments or []:
            if isinstance(item, (list, tuple)) and len(item) >= 3 and item[2] is None:
                open_row = item
        if open_row:
            airport = _as_airport(open_row[0])
            if airport:
                occupancy[key] = airport
    return occupancy


def seed_from_segments(segments, window_lo):
    if window_lo is None:
        return None, None
    lo = int(window_lo)
    seed_airport = None
    seed_start = None
    for item in segments or []:
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue
        if item[2] is not None:
            continue
        airport = _as_airport(item[0])
        try:
            start = int(item[1])
        except (TypeError, ValueError):
            continue
        if airport and start < lo:
            seed_airport = airport
            seed_start = start
    return seed_airport, seed_start
