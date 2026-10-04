"""已选承运人：入库保留全部航班，派生结果只认 carrier 表里启用的代码。"""

import json
import logging

from django.db import transaction

logger = logging.getLogger('mtws.flight_selection')


def normalize_carrier(value) -> str:
    if value is None:
        return ''
    return str(value).strip().upper()


def sort_carrier_codes(codes) -> list:
    """O3 固定第一，其余按字母顺序。"""
    uniq = sorted({normalize_carrier(code) for code in codes or [] if normalize_carrier(code)})
    if 'O3' in uniq:
        uniq.remove('O3')
        uniq.insert(0, 'O3')
    return uniq


def selected_carrier_codes() -> set:
    from core.models import Carrier

    return {
        code
        for code in (
            normalize_carrier(raw)
            for raw in Carrier.objects.filter(is_active=True).values_list('carrier_code', flat=True)
        )
        if code
    }


def event_is_selected(event, selected) -> bool:
    if not selected or not isinstance(event, dict):
        return False
    return normalize_carrier(event.get('carrier')) in selected


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


def selected_events(events, selected=None) -> list:
    chosen = selected_carrier_codes() if selected is None else selected
    return [ev for ev in _as_event_list(events) if event_is_selected(ev, chosen)]


def airport_flags_from_events(events: list) -> dict:
    """由事件汇总 has_flight、在途和三个特殊时刻。调用方先筛好承运人。"""
    idle = {'off', 'lnd', 'dst'}
    has_flight = False
    en_route = 0
    closest_arr_link = None
    closest_lnd_at = None
    closest_dep_at = None
    for ev in events or []:
        if not isinstance(ev, dict):
            continue
        kind = ev.get('kind')
        if kind not in idle:
            has_flight = True
        if kind in ('enr', 'oen'):
            en_route = 1
        if kind in ('arr', 'oar'):
            link = ev.get('link')
            if link is not None and (closest_arr_link is None or link < closest_arr_link):
                closest_arr_link = link
        if kind in ('enr', 'arr', 'oen', 'oar'):
            at = ev.get('at')
            if at is not None and (closest_lnd_at is None or at < closest_lnd_at):
                closest_lnd_at = at
        if kind in ('dep', 'odp'):
            at = ev.get('at')
            if at is not None and (closest_dep_at is None or at < closest_dep_at):
                closest_dep_at = at
    return {
        'has_flight': has_flight,
        'en_route': en_route,
        'closest_arr_link': closest_arr_link,
        'closest_lnd_at': closest_lnd_at,
        'closest_dep_at': closest_dep_at,
    }


def distinct_flight_carriers() -> list:
    """flight.events 里出现过的二字代码。"""
    from parsers.models import Flight

    found = set()
    for raw in Flight.objects.values_list('events', flat=True):
        for ev in _as_event_list(raw):
            code = normalize_carrier(ev.get('carrier') if isinstance(ev, dict) else '')
            if len(code) == 2:
                found.add(code)
    return sort_carrier_codes(found)


def _two_letter_codes(codes) -> list:
    return sort_carrier_codes(
        code for code in (normalize_carrier(raw) for raw in (codes or []))
        if len(code) == 2
    )


def save_selected_carriers(codes, visible=None, time_mode='current') -> list:
    """勾选结果写回 carrier 表，并重算已选承运人的航班派生数据。

    只改本次矩阵里出现的代码。航班里暂时没有的已选承运人保持原状。
    """
    from core.models import Carrier

    cleaned = _two_letter_codes(codes)
    shown = set(_two_letter_codes(visible if visible is not None else distinct_flight_carriers()))
    chosen = set(cleaned)
    with transaction.atomic():
        for code in shown:
            if code in chosen:
                continue
            Carrier.objects.filter(carrier_code__iexact=code).update(is_active=False)
        for code in cleaned:
            row = Carrier.objects.filter(carrier_code__iexact=code).first()
            if row:
                row.carrier_code = code
                row.is_active = True
                row.save(update_fields=['carrier_code', 'is_active', 'updated_at'])
            else:
                Carrier.objects.create(carrier_code=code, is_active=True)
    recompute_selected_flight_state(time_mode)
    return sort_carrier_codes(selected_carrier_codes())


def recompute_selected_flight_state(time_mode='current') -> None:
    """按当前已选承运人重写有航班、在途、三个特殊时刻和航班告警。"""
    from parsers.models import Flight

    selected = selected_carrier_codes()
    changed = []
    airports = []
    rows = Flight.objects.all().only(
        'id', 'airport_4code', 'events', 'has_flight', 'en_route',
        'closest_departure_time_of_arriving_flight',
        'closest_departure_time_at_this_airport',
        'closest_landing_time_of_arriving_flight',
    )
    for row in rows:
        airports.append(row.airport_4code)
        flags = airport_flags_from_events(selected_events(row.as_events(), selected))
        new_vals = {
            'has_flight': flags['has_flight'],
            'en_route': flags['en_route'],
            'closest_departure_time_of_arriving_flight': flags['closest_arr_link'],
            'closest_departure_time_at_this_airport': flags['closest_dep_at'],
            'closest_landing_time_of_arriving_flight': flags['closest_lnd_at'],
        }
        if any(getattr(row, key) != value for key, value in new_vals.items()):
            Flight.objects.filter(pk=row.pk).update(**new_vals)
            changed.append(row.airport_4code)
    if airports:
        from utils.marks_alert_calculator import MarksAlertCalculator
        MarksAlertCalculator(time_mode).apply(full_airports=airports)
    if changed:
        try:
            from utils.trend_alert import refresh_airports
            refresh_airports(changed)
        except Exception:
            logger.exception('承运人变更后刷新实况趋势失败')
