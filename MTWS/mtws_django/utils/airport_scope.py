"""机场范围：有航班、起降窗口，以及入库告警用的有航班 ∪ 停场。"""

from __future__ import annotations

import json
import logging
import time

logger = logging.getLogger('mtws.utils')

HOUR_MS = 3600 * 1000
PAST_WINDOW_MS = 2 * HOUR_MS
FUTURE_HOURS_MAX = 9
FUTURE_HOURS_DEFAULT = 2

# 起飞：未起、超时未起。已起飞的 off/dst 不收。
_DEPARTURE_KINDS = frozenset({'dep', 'odp'})
# 落地：未起未到、已起未到、超时未落。已落地的 lnd 不收。
_ARRIVAL_KINDS = frozenset({'arr', 'enr', 'oar', 'oen'})


def clamp_future_hours(value, default: int = FUTURE_HOURS_DEFAULT) -> int:
    """未来侧小时数，限制在 0–9。无法解析时用默认值。"""
    if value is None or value == '':
        return default
    try:
        hours = int(value)
    except (TypeError, ValueError):
        return default
    if hours < 0:
        return 0
    if hours > FUTURE_HOURS_MAX:
        return FUTURE_HOURS_MAX
    return hours


def _as_event_list(raw) -> list:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _in_window(ts, begin: int, end: int) -> bool:
    if ts is None:
        return False
    try:
        value = int(ts)
    except (TypeError, ValueError):
        return False
    return begin <= value <= end


def event_in_operation_window(events, now_ms: int, future_hours: int, carriers=None) -> bool:
    """过去固定 2 小时，未来 future_hours 小时。有一条命中即真。

    起飞看 dep/odp 的 at。落地看 arr/enr/oar/oen 的 at 或 link。
    只统计已选承运人。
    """
    from utils.flight_selection import event_is_selected, selected_carrier_codes

    chosen = selected_carrier_codes() if carriers is None else carriers
    begin = int(now_ms) - PAST_WINDOW_MS
    end = int(now_ms) + clamp_future_hours(future_hours) * HOUR_MS
    for event in _as_event_list(events):
        if not isinstance(event, dict):
            continue
        if not event_is_selected(event, chosen):
            continue
        kind = event.get('kind')
        if kind in _DEPARTURE_KINDS and _in_window(event.get('at'), begin, end):
            return True
        if kind in _ARRIVAL_KINDS and (
            _in_window(event.get('at'), begin, end) or _in_window(event.get('link'), begin, end)
        ):
            return True
    return False


def get_parking_airport_codes() -> set:
    from core.models import AircraftParkingInfo

    latest = AircraftParkingInfo.objects.order_by('-parse_time').first()
    if not latest or not latest.airport_4code:
        return set()
    parking_list = latest.airport_4code
    if isinstance(parking_list, str):
        try:
            parking_list = json.loads(parking_list)
        except (TypeError, json.JSONDecodeError):
            logger.warning('停场名单 JSON 解析失败')
            return set()
    if not parking_list:
        return set()
    return {str(code).strip() for code in parking_list if str(code).strip()}


def get_flight_airport_codes() -> set:
    from parsers.models import Flight

    return set(
        Flight.objects.filter(has_flight=True).values_list('airport_4code', flat=True)
    )


def get_monitored_airport_codes() -> list:
    """有航班机场 ∪ 停场名单，去重；有航班顺序在前，停场-only 按代码排序补在后面。"""
    from parsers.models import Flight

    flight_list = list(
        Flight.objects.filter(has_flight=True)
        .values_list('airport_4code', flat=True)
        .distinct()
    )
    extras = sorted(get_parking_airport_codes() - set(flight_list))
    return flight_list + extras


def get_import_alert_keep_airport_codes() -> set:
    """入库告警自动结案时仍保留的机场：有航班或在停场名单中。"""
    return get_flight_airport_codes() | get_parking_airport_codes()


def airport_codes_for_scope(scope: str, future_hours=FUTURE_HOURS_DEFAULT, now_ms: int = None) -> list:
    """雷达和趋势共用的机场清单。

    has_flight：has_flight 为真（至少一条不是已起飞 off/dst 或已落地 lnd）。
    recent2h：起降窗口，过去 2 小时到未来 future_hours 小时。
    """
    from parsers.models import Flight

    chosen = (scope or 'has_flight').strip()
    if chosen != 'recent2h':
        return sorted(get_flight_airport_codes())
    from utils.flight_selection import selected_carrier_codes

    now_ms = int(now_ms if now_ms is not None else time.time() * 1000)
    hours = clamp_future_hours(future_hours)
    carriers = selected_carrier_codes()
    found = []
    rows = Flight.objects.values('airport_4code', 'events')
    for row in rows:
        code = str(row.get('airport_4code') or '').strip().upper()
        if not code:
            continue
        if event_in_operation_window(row.get('events'), now_ms, hours, carriers):
            found.append(code)
    return sorted(set(found))
