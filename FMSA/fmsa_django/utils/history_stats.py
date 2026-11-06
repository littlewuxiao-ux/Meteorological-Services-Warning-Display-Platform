"""历史天气统计：规则组、时段、航班命中、实况分段。"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Optional

from utils.user_settings import json_config_row, save_json_config

logger = logging.getLogger('fmsa.history')

HOUR_MS = 3600 * 1000
MAX_RANGE_MS = 24 * HOUR_MS
BJ = dt_timezone(timedelta(hours=8))
ALERT_RANK = {'N': 1, 'G': 2, 'Y': 3, 'R': 4}
ALERT_LEVELS = ('R', 'Y', 'G')
TYPE_LAND = '落地'
TYPE_DEP = '起飞'
TYPE_ENR = '飞行中'
TYPE_SOON = '即将起飞'
TYPE_PARK = '停场'
ELEMENT_FILTER_BASE = ('风速', '能见度', 'RVR', '云底高', '高温', '低温', '风切变')
ELEMENT_FILTER_TREND = '趋势'
PARKING_WX_CODES = ('S', 'F', 'I', 'G', 'H')
TYPE_ORDER = (TYPE_LAND, TYPE_DEP, TYPE_ENR, TYPE_SOON, TYPE_PARK)
AIRPORT_RE = re.compile(r'^[A-Z]{4}$')


def default_params() -> dict:
    return {
        'done_hours': 2,
        'open_hours': 4,
        'alert_level': 'Y',
        'gap_hours': 2,
    }


def default_parking_elements() -> list:
    names = ['风速', '低温']
    seen = set(names)
    try:
        mapping = _weather_type_cn_map()
    except Exception:
        mapping = {}
    for code in PARKING_WX_CODES:
        label = str((mapping or {}).get(code) or (mapping or {}).get(str(code).upper()) or '').strip() or str(code)
        if label not in seen:
            seen.add(label)
            names.append(label)
    return names


def default_config() -> dict:
    return {
        'general': default_params(),
        'special': [],
        'parking_elements': default_parking_elements(),
    }


def _num(value, default, lo=0, hi=24):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    if number < lo:
        number = lo
    if number > hi:
        number = hi
    if abs(number - int(number)) < 1e-9:
        return int(number)
    return round(number, 1)


def _level(value, default='Y') -> str:
    text = str(value or '').strip().upper()
    return text if text in ALERT_LEVELS else default


def parse_airports(text) -> list:
    raw = str(text or '').upper().replace('，', ',').replace(';', ',').replace(' ', ',')
    codes = []
    seen = set()
    for part in raw.split(','):
        code = part.strip()
        if not code:
            continue
        if not AIRPORT_RE.match(code):
            raise ValueError(f'机场四字代码无效：{code}')
        if code in seen:
            continue
        seen.add(code)
        codes.append(code)
    return codes


def _params_from(raw: dict) -> dict:
    base = default_params()
    src = raw if isinstance(raw, dict) else {}
    return {
        'done_hours': _num(src.get('done_hours'), base['done_hours'], 0, 24),
        'open_hours': _num(src.get('open_hours'), base['open_hours'], 0, 24),
        'alert_level': _level(src.get('alert_level'), base['alert_level']),
        'gap_hours': _num(src.get('gap_hours'), base['gap_hours'], 0, 24),
    }


def normalize_config(payload: dict) -> tuple[dict, list]:
    errors = []
    src = payload if isinstance(payload, dict) else {}
    general = _params_from(src.get('general') if isinstance(src.get('general'), dict) else src)
    special = []
    used = {}
    rows = src.get('special') if isinstance(src.get('special'), list) else []
    if len(rows) > 3:
        errors.append('特殊组最多 3 个')
        rows = rows[:3]
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        text = str(row.get('airports_text') or '').strip()
        if not text and not row.get('airports'):
            continue
        try:
            codes = parse_airports(text or ','.join(row.get('airports') or []))
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not codes:
            errors.append(f'特殊组{index}未填写机场')
            continue
        clash = [code for code in codes if code in used]
        if clash:
            errors.append(f'机场 {",".join(clash)} 同时出现在特殊组{used[clash[0]]}和特殊组{index}')
            continue
        for code in codes:
            used[code] = index
        item = _params_from(row)
        item['name'] = str(row.get('name') or f'特殊组{index}').strip() or f'特殊组{index}'
        item['airports'] = codes
        item['airports_text'] = ','.join(codes)
        special.append(item)
    parking_elements = _parking_elements_from(src.get('parking_elements'))
    config = {'general': general, 'special': special, 'parking_elements': parking_elements}
    return config, errors


def _parking_elements_from(raw) -> list:
    allowed = element_filter_options()
    allow = set(allowed)
    if raw is None:
        wanted = set(default_parking_elements())
    else:
        wanted = set()
        if isinstance(raw, list):
            for name in raw:
                text = str(name or '').strip()
                if text in allow:
                    wanted.add(text)
    return [name for name in allowed if name in wanted]


def read_config(user_code=None) -> dict:
    from config_db.models import HistoryStatsConfig

    row = json_config_row(HistoryStatsConfig, user_code)
    payload = row.config if row and isinstance(row.config, dict) else default_config()
    config, _errors = normalize_config(payload)
    return config


def save_config(payload: dict, user_code=None) -> tuple[dict, list]:
    from config_db.models import HistoryStatsConfig
    from utils.user_settings import current_settings_user

    user = user_code or current_settings_user()
    config, errors = normalize_config(payload)
    if errors:
        return config, errors
    save_json_config(HistoryStatsConfig, user, config)
    return config, []


def params_for(config: dict, airport: str) -> dict:
    code = str(airport or '').upper()
    for group in config.get('special') or []:
        if code in set(group.get('airports') or []):
            return _params_from(group)
    return _params_from((config or {}).get('general') or {})


def meets_level(actual, threshold) -> bool:
    return ALERT_RANK.get(str(actual or '').upper(), 0) >= ALERT_RANK.get(str(threshold or '').upper(), 0)


def _bj_now(time_mode='current') -> datetime:
    from utils.time_manager import TimeManager
    return TimeManager.get_current_time_beijing(time_mode)


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=BJ)
    return dt.astimezone(BJ)


def dt_to_ms(dt: datetime) -> int:
    return int(_aware(dt).timestamp() * 1000)


def ms_to_bj(ms: int) -> datetime:
    return datetime.fromtimestamp(int(ms) / 1000.0, tz=BJ)


def clip_end(start: datetime, end: datetime, now: datetime) -> tuple[datetime, datetime]:
    if start <= now <= end:
        end = now
    return start, end


def resolve_range(preset: str, start_ms=None, end_ms=None, time_mode='current') -> tuple[int, int, str]:
    now = _bj_now(time_mode)
    today_0830 = now.replace(hour=8, minute=30, second=0, microsecond=0)
    today_1730 = now.replace(hour=17, minute=30, second=0, microsecond=0)
    y_0830 = today_0830 - timedelta(days=1)
    y_1730 = today_1730 - timedelta(days=1)
    kind = str(preset or 'day').strip().lower()

    if kind == 'custom':
        if start_ms is None or end_ms is None:
            raise ValueError('自定义时段需要起止时间')
        start = ms_to_bj(int(start_ms)).replace(tzinfo=None)
        end = ms_to_bj(int(end_ms)).replace(tzinfo=None)
    elif kind == 'night':
        if now >= today_1730:
            start, end = today_1730, today_0830 + timedelta(days=1)
        else:
            start, end = y_1730, today_0830
    elif kind == 'daynight':
        start, end = y_0830, today_0830
    else:
        kind = 'day'
        if now < today_0830:
            start, end = y_0830, y_1730
        else:
            start, end = today_0830, today_1730

    if start >= end:
        raise ValueError('开始时间必须早于结束时间')
    start, end = clip_end(start, end, now)
    if start >= end:
        raise ValueError('所选时段没有可查询的已发生时间')
    span = dt_to_ms(end) - dt_to_ms(start)
    if span > MAX_RANGE_MS:
        raise ValueError('查询时段最长 24 小时')
    return dt_to_ms(start), dt_to_ms(end), kind


def _field_ms(row: dict, *keys):
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if not text or text.lower() in ('nan', 'none', 'nat'):
            continue
        try:
            number = int(float(text))
        except (TypeError, ValueError):
            continue
        if number > 0:
            return number
    return None


def _has_time(row: dict, key: str) -> bool:
    return _field_ms(row, key) is not None


def _airport(value) -> Optional[str]:
    code = str(value or '').strip().upper()
    return code if AIRPORT_RE.match(code) else None


def _intersect(lo: int, hi: int, start: int, end: int) -> Optional[tuple[int, int]]:
    a = max(int(lo), int(start))
    b = min(int(hi), int(end))
    if a > b:
        return None
    return a, b


def _row_dict(row) -> dict:
    if isinstance(row, dict):
        return row
    try:
        return row.to_dict()
    except Exception:
        return dict(row)


def load_flights(time_mode: str, token: Optional[str], start_ms: int, end_ms: int, carriers: set) -> list:
    chosen = {str(code).strip() for code in (carriers or set()) if str(code).strip()}
    if time_mode == 'test':
        rows = _flights_from_local()
    else:
        rows = _flights_from_api(token, start_ms, end_ms)
    out = []
    for row in rows:
        carrier = str(row.get('carrier') or '').strip()
        if chosen and carrier not in chosen:
            continue
        out.append(row)
    return out


def _flights_from_api(token, start_ms, end_ms) -> list:
    from data_adapters.adapter_factory import AdapterFactory

    try:
        adapter = AdapterFactory.create_adapter(time_mode='current', token=token)
        df = adapter.get_flight_data(start_ms=start_ms, end_ms=end_ms)
    except Exception:
        logger.exception('历史统计拉取航班失败')
        return []
    if df is None or getattr(df, 'empty', True):
        return []
    return [_row_dict(row) for _, row in df.iterrows()]


def _flights_from_local() -> list:
    from runtime_db.models import Flight

    seen = set()
    rows = []
    for events in Flight.objects.values_list('events', flat=True):
        if not isinstance(events, list):
            continue
        for event in events:
            if not isinstance(event, dict):
                continue
            other = event.get('other') if isinstance(event.get('other'), dict) else {}
            key = (
                other.get('flightId') or event.get('flightId'),
                other.get('flightNo'),
                other.get('atd'),
                other.get('ata'),
                other.get('departureAirport'),
                other.get('arrivalAirport'),
            )
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                'flightId': other.get('flightId') or event.get('flightId'),
                'flightNo': other.get('flightNo'),
                'carrier': event.get('carrier') or other.get('carrier'),
                'departureAirport': other.get('departureAirport'),
                'arrivalAirport': other.get('arrivalAirport'),
                'ptd': other.get('ptd'),
                'pta': other.get('pta'),
                'std': other.get('std'),
                'sta': other.get('sta'),
                'etd': other.get('etd'),
                'eta': other.get('eta'),
                'atd': other.get('atd'),
                'ata': other.get('ata'),
            })
    return rows


def _collect_hits(flights: list, config: dict, query_start: int, query_end: int) -> dict:
    """airport -> {window: (lo,hi) merged by type tagging later at report level}"""
    hits = {}

    def add(airport, kind, lo, hi):
        code = _airport(airport)
        if not code:
            return
        window = _intersect(lo, hi, query_start, query_end)
        if not window:
            return
        bucket = hits.setdefault(code, [])
        bucket.append({'type': kind, 'start': window[0], 'end': window[1]})

    for raw in flights:
        row = _row_dict(raw)
        dep = _airport(row.get('departureAirport'))
        arr = _airport(row.get('arrivalAirport'))
        ata = _field_ms(row, 'ata')
        atd = _field_ms(row, 'atd')
        planned = _field_ms(row, 'etd', 'std', 'ptd')
        dest_p = params_for(config, arr) if arr else default_params()
        orig_p = params_for(config, dep) if dep else default_params()

        if ata and query_start <= ata <= query_end and arr:
            pad = int(float(dest_p['done_hours']) * HOUR_MS)
            add(arr, TYPE_LAND, ata - pad, ata + pad)
        if atd and query_start <= atd <= query_end and dep:
            pad = int(float(orig_p['done_hours']) * HOUR_MS)
            add(dep, TYPE_DEP, atd - pad, atd + pad)

        airborne = atd and atd <= query_end and (ata is None or ata > query_end)
        if airborne and arr:
            look = int(float(dest_p['open_hours']) * HOUR_MS)
            add(arr, TYPE_ENR, query_end - look, query_end)

        not_departed = (atd is None or atd > query_end) and dep and planned
        if not_departed:
            look = int(float(orig_p['open_hours']) * HOUR_MS)
            upcoming = query_end < planned <= query_end + look
            overdue = planned <= query_end
            if upcoming or overdue:
                add(dep, TYPE_SOON, query_end - look, query_end)
    return hits


def actual_badges(metar, threshold: str) -> list:
    from utils.popup_utils import (
        _alert_badge, _as_dict, _clean_text, _element_badges,
    )

    badges = _element_badges(metar)
    elements = _as_dict(metar.metar_elements)

    def take(items):
        found = []
        for item in items or []:
            if not item:
                continue
            if meets_level(item.get('level'), threshold):
                found.append({'text': item.get('text') or '', 'level': item.get('level')})
        return found

    out = []
    wind = take(badges.get('wsp'))
    if not wind:
        info = elements.get('wind') if isinstance(elements.get('wind'), dict) else {}
        direction = _clean_text(metar.metar_wind_direction)
        speed = _clean_text(metar.metar_wind_speed_original)
        text = f'{direction}{speed}' if direction or speed else ''
        badge = _alert_badge(info.get('alert'), text)
        wind = take([badge] if badge else [])
    out.extend(wind)

    vis = take(badges.get('vis'))
    if not vis:
        info = elements.get('visibility') if isinstance(elements.get('visibility'), dict) else {}
        badge = _alert_badge(info.get('alert'), _clean_text(metar.metar_visibility_original))
        vis = take([badge] if badge else [])
    out.extend(vis)
    out.extend(take(badges.get('rvr')))
    out.extend(take(badges.get('ww')))
    out.extend(take(badges.get('cld')))

    temp = take(badges.get('t'))
    if not temp:
        info = elements.get('temperature') if isinstance(elements.get('temperature'), dict) else {}
        text = _clean_text(metar.metar_temperature)
        if text and '°' not in text and not text.endswith('C'):
            text = f'{text}°C'
        badge = _alert_badge(info.get('alert'), text)
        temp = take([badge] if badge else [])
    out.extend(temp)

    shear = take(badges.get('ws'))
    if not shear:
        badge = _alert_badge(metar.metar_ws_warning, _clean_text(metar.metar_ws_dsc))
        shear = take([badge] if badge else [])
    out.extend(shear)

    trend = take(badges.get('tr'))
    if not trend:
        badge = _alert_badge(metar.metar_change_trend_warning, '趋势')
        trend = take([badge] if badge else [])
    else:
        trend = [{'text': '趋势', 'level': item.get('level')} for item in trend]
    out.extend(trend)
    return [item for item in out if item.get('text')]


def _better_level(current, candidate) -> str:
    cand = str(candidate or '').upper()
    if cand not in ALERT_LEVELS:
        return current
    if current is None or ALERT_RANK.get(cand, 0) > ALERT_RANK.get(str(current).upper(), 0):
        return cand
    return current


def _field_warning(metar, field: str, element_path=None):
    level = getattr(metar, field, None)
    if str(level or '').upper() in ALERT_RANK:
        return str(level).upper()
    if not element_path:
        return None
    from utils.popup_utils import _as_dict
    cursor = _as_dict(metar.metar_elements)
    for key in element_path:
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(key)
    if isinstance(cursor, dict):
        alert = cursor.get('alert') or cursor.get('warning')
        return str(alert).upper() if alert else None
    return None


def _airport_names(codes: list) -> dict:
    from config_db.models import AirportInfo
    from core.airport_directory import display_airport_name

    mapping = {}
    if codes:
        for row in AirportInfo.objects.filter(airport_4code__in=codes).values('airport_4code', 'airport_name'):
            mapping[row['airport_4code']] = display_airport_name(row.get('airport_name'))
    for code in codes or []:
        mapping.setdefault(code, display_airport_name(''))
    return mapping


def element_filter_options() -> list:
    names = list(ELEMENT_FILTER_BASE)
    seen = set(names)
    for name in _weather_type_cn_map().values():
        text = str(name or '').strip()
        if text and text not in seen:
            seen.add(text)
            names.append(text)
    names.append(ELEMENT_FILTER_TREND)
    return names


def _weather_type_cn_map() -> dict:
    from config_db.models import WeatherTypeInfo

    mapping = {}
    for row in WeatherTypeInfo.objects.all():
        code = str(row.weather_type_code or '').strip()
        name = str(row.description_cn or '').strip()
        if code and name:
            mapping[code] = name
            mapping[code.upper()] = name
    return mapping


def _weather_type_label(code: str, given_name=None, type_map=None) -> str:
    from utils.popup_utils import weather_type_display_name

    text = str(given_name or '').strip()
    if text and text not in ALERT_LEVELS and text != 'N':
        return text
    key = str(code or '').strip()
    mapped = (type_map or {}).get(key) or (type_map or {}).get(key.upper())
    if mapped:
        return mapped
    return weather_type_display_name(key, mapped)


def _weather_type_entries(metar, type_map=None) -> list:
    import json

    raw = metar.metar_weather_type
    if isinstance(raw, str):
        try:
            raw = json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            raw = {}
    if not isinstance(raw, dict):
        raw = {}
    if type_map is None:
        type_map = _weather_type_cn_map()
    entries = []
    for code, info in raw.items():
        if isinstance(info, dict):
            level = info.get('alert_level')
            name = _weather_type_label(code, info.get('cn_name'), type_map)
        else:
            level = info
            name = _weather_type_label(code, None, type_map)
        entries.append({'code': str(code), 'name': name, 'level': str(level or '').upper()})
    if entries:
        return entries
    from parsers.plain_language import weather_zh
    warning = str(metar.metar_weather_warning or '').upper()
    for token in _wx_tokens(metar):
        entries.append({
            'code': token,
            'name': weather_zh(token) or token,
            'level': warning,
        })
    return entries


def _temp_kind(metar) -> Optional[str]:
    value = getattr(metar, 'metar_temp_val', None)
    if value is None:
        return None
    try:
        return '高温' if float(value) >= 0 else '低温'
    except (TypeError, ValueError):
        return None


def popup_badges_for_metars(metars: list, threshold: str) -> dict:
    """实况弹窗同款徽章：要素中文名 + 天气类型中文名 + 趋势。实心色块为该段最高等级。"""
    element_specs = (
        ('风速', 'metar_wind_warning', ('wind',)),
        ('能见度', 'metar_visibility_warning', ('visibility',)),
        ('RVR', 'metar_rvr_warning', None),
        ('云底高', 'metar_cloud_warning', ('clouds',)),
        ('风切变', 'metar_ws_warning', None),
        ('趋势', 'metar_change_trend_warning', None),
    )
    elements = []
    for label, field, path in element_specs:
        best = None
        for metar in metars:
            level = _field_warning(metar, field, path)
            if field == 'metar_rvr_warning':
                from utils.popup_utils import _as_dict
                for item in _as_dict(metar.metar_elements).get('rvr') or []:
                    if isinstance(item, dict):
                        level = _better_level(level, item.get('alert'))
            best = _better_level(best, level)
        if meets_level(best, threshold):
            elements.append({'text': label, 'level': best})
    hot_best = None
    cold_best = None
    for metar in metars:
        kind = _temp_kind(metar)
        if not kind:
            continue
        level = _field_warning(metar, 'metar_temperature_warning', ('temperature',))
        if kind == '高温':
            hot_best = _better_level(hot_best, level)
        else:
            cold_best = _better_level(cold_best, level)
    temp_badges = []
    if meets_level(hot_best, threshold):
        temp_badges.append({'text': '高温', 'level': hot_best})
    if meets_level(cold_best, threshold):
        temp_badges.append({'text': '低温', 'level': cold_best})
    if temp_badges:
        cloud_at = next((i for i, item in enumerate(elements) if item.get('text') == '云底高'), None)
        insert_at = cloud_at + 1 if cloud_at is not None else max(0, len(elements) - 2)
        for offset, badge in enumerate(temp_badges):
            elements.insert(insert_at + offset, badge)

    weather = []
    best_wx = {}
    type_map = _weather_type_cn_map()
    for metar in metars:
        for item in _weather_type_entries(metar, type_map):
            if not meets_level(item['level'], threshold):
                continue
            prev = best_wx.get(item['code'])
            if prev is None or ALERT_RANK.get(item['level'], 0) > ALERT_RANK.get(prev['level'], 0):
                best_wx[item['code']] = {'text': item['name'], 'level': item['level']}
    weather.extend(best_wx.values())
    return {
        'elements': elements,
        'weather': weather,
        'all': elements + weather,
    }


def _wx_tokens(metar) -> list:
    text = str(metar.metar_weather or '').strip()
    if not text or text.lower() == 'none':
        return []
    return [part.strip() for part in re.split(r'[\s,]+', text) if part.strip()]


def _phenomenon_plain_names(metars: list, threshold: str) -> list:
    from parsers.plain_language import weather_zh
    from utils.popup_utils import _as_dict, _clean_text
    from utils.user_settings import current_settings_user, weather_row

    names = []
    seen = set()
    user = current_settings_user()

    def add(code):
        token = str(code or '').strip()
        if not token or token.lower() == 'none':
            return
        name = weather_zh(token) or token
        if name and name not in seen:
            seen.add(name)
            names.append(name)

    def token_level(token):
        row = weather_row(user, token)
        if row is None:
            body = token.lstrip('+-')
            if body.startswith('VC'):
                body = body[2:]
            if body != token:
                row = weather_row(user, body)
        return getattr(row, 'alert_level', None) if row else None

    for metar in metars:
        weather = _as_dict(_as_dict(metar.metar_elements).get('weather'))
        items = [item for item in (weather.get('items') or []) if isinstance(item, dict)]
        if items:
            for item in items:
                if not meets_level(item.get('alert'), threshold):
                    continue
                code = _clean_text(item.get('code')) or _clean_text(item.get('raw'))
                for token in re.split(r'[\s,]+', code) if code else []:
                    add(token)
            continue
        for token in _wx_tokens(metar):
            level = token_level(token)
            if level:
                if meets_level(level, threshold):
                    add(token)
            elif meets_level(metar.metar_weather_warning, threshold):
                add(token)
    return names


def _format_rvr_display(meters) -> str:
    """Pxxxx 入库时写成 原值+30；展示还原为 Pxxxx，其余仍写米。"""
    try:
        number = int(round(float(meters)))
    except (TypeError, ValueError):
        return str(meters)
    base = number - 30
    if base > 0 and number % 100 == 30 and base % 50 == 0:
        return f'P{base:04d}'
    return f'{number} 米'


def _format_rvr_from_metars(metars: list) -> Optional[str]:
    chosen = None
    for metar in metars:
        value = metar.rvr_min_val
        if value is None:
            continue
        if chosen is None or value < chosen.rvr_min_val:
            chosen = metar
    if chosen is None:
        return None
    stored = chosen.rvr_min_org if chosen.rvr_min_org is not None else chosen.rvr_min_val
    return _format_rvr_display(stored)


def build_plain_parts(metars: list, threshold: str, popup: dict = None) -> list:
    popup = popup or popup_badges_for_metars(metars, threshold)
    labels = {item.get('text') for item in (popup.get('elements') or [])}

    speeds = [m.metar_wind_speed_val for m in metars if m.metar_wind_speed_val is not None]
    gusts = [m.metar_gust_val for m in metars if m.metar_gust_val is not None]
    vis = [m.metar_visibility_val for m in metars if m.metar_visibility_val is not None]
    clouds = [m.metar_min_cloud_height for m in metars if m.metar_min_cloud_height is not None]
    temps = [m.metar_temp_val for m in metars if m.metar_temp_val is not None]
    parts = []

    def add(label, text):
        text = str(text or '').strip()
        if not label or not text:
            return
        parts.append({'labels': [label], 'text': text})

    if '风速' in labels:
        wind_bits = []
        if speeds:
            wind_bits.append(f'平均风速最大 {int(round(max(speeds)))} 米/秒')
        if gusts:
            wind_bits.append(f'阵风最大 {int(round(max(gusts)))} 米/秒')
        add('风速', '，'.join(wind_bits) if wind_bits else '风速')
    if '能见度' in labels:
        add('能见度', f'能见度最低 {int(min(vis))} 米' if vis else '能见度')
    if 'RVR' in labels:
        rvr_text = _format_rvr_from_metars(metars)
        add('RVR', f'RVR最低 {rvr_text}' if rvr_text else 'RVR')
    wx_seen = set()
    for item in popup.get('weather') or []:
        name = str(item.get('text') or '').strip()
        if name and name not in wx_seen:
            wx_seen.add(name)
            add(name, name)
    for name in _phenomenon_plain_names(metars, threshold):
        if name not in wx_seen:
            wx_seen.add(name)
            add(name, name)
    if '云底高' in labels:
        add('云底高', f'云底高最低 {int(min(clouds)) * 100} 英尺' if clouds else '云底高')
    hot = [t for t in temps if t >= 0]
    cold = [t for t in temps if t < 0]
    if '高温' in labels:
        add('高温', f'最高温度 {int(round(max(hot)))}℃' if hot else '高温')
    if '低温' in labels:
        add('低温', f'最低温度 {int(round(min(cold)))}℃' if cold else '低温')
    if '风切变' in labels:
        add('风切变', '风切变')
    if '趋势' in labels:
        add('趋势', '趋势')
    return parts


def build_plain(metars: list, threshold: str, popup: dict = None) -> str:
    return '；'.join(item['text'] for item in build_plain_parts(metars, threshold, popup) if item.get('text'))


def _load_metars(airports: list, start_ms: int, end_ms: int) -> dict:
    from runtime_db.models import Metar

    if not airports:
        return {}
    rows = Metar.objects.filter(
        airport_4code__in=airports,
        metar_observation_time__gte=start_ms,
        metar_observation_time__lte=end_ms,
    ).order_by('airport_4code', 'metar_observation_time', 'sqc')
    grouped = {code: [] for code in airports}
    for row in rows:
        grouped.setdefault(row.airport_4code, []).append(row)
    return grouped


def _backfill_empty(airports: list, start_ms: int, end_ms: int, time_mode: str, token: Optional[str]) -> None:
    from parsers.metar_history import fetch_raw_met_list
    from parsers.metar_parser import MetarParser
    from parsers.trend_metar_backfill import _content_key, _parse_row_for_store
    from runtime_db.models import Metar

    if time_mode == 'test' or not airports:
        return
    try:
        parser = MetarParser(time_mode=time_mode, token=token)
    except Exception:
        logger.exception('历史统计补数初始化解析器失败')
        return
    now_ms = int(time.time() * 1000)
    created_at = now_ms
    for airport in airports:
        try:
            items = fetch_raw_met_list(
                airport,
                time_mode=time_mode,
                token=token,
                ws_types=['SA', 'SP'],
                start_ms=start_ms,
                end_ms=end_ms,
            )
        except Exception:
            logger.exception('历史统计请求历史报文失败: %s', airport)
            continue
        if not items:
            continue
        existing_keys = {
            _content_key(obs, content)
            for obs, content in Metar.objects.filter(
                airport_4code=airport,
                metar_observation_time__gte=start_ms,
                metar_observation_time__lte=end_ms,
            ).values_list('metar_observation_time', 'metar_content')
            if obs is not None and content
        }
        existing_sqcs = set(
            Metar.objects.filter(sqc__startswith=f'H_{airport}_').values_list('sqc', flat=True)
        )
        seq_by_obs = {}
        for item in items:
            content = item.get('content') or ''
            parsed = _parse_row_for_store(
                content, airport, item.get('wtype') or '', now_ms, parser, raw_item=item,
            )
            if not parsed:
                continue
            obs_ms = parsed['metar_observation_time']
            if obs_ms is None or obs_ms < start_ms or obs_ms > end_ms:
                continue
            key = _content_key(obs_ms, parsed['metar_content'])
            if key in existing_keys:
                continue
            seq = seq_by_obs.get(obs_ms, 0) + 1
            while True:
                sqc = f'H_{airport}_{obs_ms}_{seq}'
                if sqc not in existing_sqcs:
                    break
                seq += 1
            seq_by_obs[obs_ms] = seq
            parsed['sqc'] = sqc
            parsed['created_at'] = created_at
            try:
                Metar.objects.create(**parsed)
            except Exception:
                logger.warning('历史统计写入补数失败 [%s] %s', airport, sqc, exc_info=True)
                continue
            existing_keys.add(key)
            existing_sqcs.add(sqc)


def _segment_reports(reports: list, gap_ms: int) -> list:
    if not reports:
        return []
    ordered = sorted(reports, key=lambda item: (item['obs'], item['metar'].sqc))
    segments = [[ordered[0]]]
    for item in ordered[1:]:
        prev = segments[-1][-1]
        if item['obs'] - prev['obs'] >= gap_ms:
            segments.append([item])
        else:
            segments[-1].append(item)
    return segments


def _is_later_metar(row, last_obs: int, last_sqc: str) -> bool:
    obs = row.metar_observation_time
    if obs is None:
        return False
    if obs > last_obs:
        return True
    return obs == last_obs and (row.sqc or '') > (last_sqc or '')


def _metar_after(airport: str, last_obs: int, last_sqc: str, known: list):
    from runtime_db.models import Metar

    later = [row for row in (known or []) if _is_later_metar(row, last_obs, last_sqc)]
    if later:
        later.sort(key=lambda row: (row.metar_observation_time, row.sqc or ''))
        return later[0]
    nxt = (
        Metar.objects.filter(airport_4code=airport, metar_observation_time__gt=last_obs)
        .order_by('metar_observation_time', 'sqc')
        .first()
    )
    if nxt:
        return nxt
    for row in Metar.objects.filter(
        airport_4code=airport, metar_observation_time=last_obs,
    ).order_by('sqc'):
        if _is_later_metar(row, last_obs, last_sqc):
            return row
    return None


def _parking_interval_map() -> dict:
    from runtime_db.models import AircraftParkingInfo
    from utils.aircraft_parking import normalize_intervals

    out = {}
    for row in AircraftParkingInfo.objects.all().only('airport_4code', 'aircraft_parked_status_records'):
        code = str(row.airport_4code or '').strip().upper()
        if not code:
            continue
        out[code] = normalize_intervals(row.aircraft_parked_status_records)
    return out


def _obs_in_parking(intervals: list, obs_ms: int) -> bool:
    from utils.aircraft_parking import interval_contains

    for start, end in intervals or []:
        if interval_contains(start, end, obs_ms):
            return True
    return False


def query_history(preset: str, start_ms=None, end_ms=None, time_mode='current', token=None, user_code=None, config=None) -> dict:
    from utils.aircraft_parking import intervals_overlap_range
    from utils.flight_selection import selected_carrier_codes

    range_start, range_end, kind = resolve_range(preset, start_ms, end_ms, time_mode)
    if config is None:
        cfg = read_config(user_code)
    else:
        cfg, errors = normalize_config(config)
        if errors:
            raise ValueError('；'.join(errors))
    carriers = selected_carrier_codes(user_code)
    max_pad_h = 0.0
    groups = [cfg.get('general') or {}] + list(cfg.get('special') or [])
    for group in groups:
        max_pad_h = max(
            max_pad_h,
            float(group.get('open_hours') or 0),
            float(group.get('done_hours') or 0),
        )
    pad = int(max_pad_h * HOUR_MS)
    flights = load_flights(time_mode, token, range_start - pad, range_end + pad, carriers)
    hits = _collect_hits(flights, cfg, range_start, range_end)

    parking_map = _parking_interval_map()
    parking_elements = set(cfg.get('parking_elements') or default_parking_elements())
    now_ms = int(time.time() * 1000)
    park_airports = {
        code for code, items in parking_map.items()
        if intervals_overlap_range(items, range_start, range_end, now_ms)
    }
    airports = sorted(set(hits) | park_airports)
    grouped = _load_metars(airports, range_start, range_end)
    missing = [code for code in airports if not grouped.get(code)]
    if missing:
        _backfill_empty(missing, range_start, range_end, time_mode, token)
        grouped = _load_metars(airports, range_start, range_end)

    tagged = {}
    all_airports = sorted(set(hits) | park_airports)
    for airport in all_airports:
        params = params_for(cfg, airport)
        level = params['alert_level']
        windows = hits.get(airport) or []
        park_ivs = parking_map.get(airport) or []
        for metar in grouped.get(airport) or []:
            obs = metar.metar_observation_time
            if obs is None:
                continue
            types = []
            for window in windows:
                if window['start'] <= obs <= window['end']:
                    types.append(window['type'])
            parked = _obs_in_parking(park_ivs, obs)
            if not types and not parked:
                continue
            badges = actual_badges(metar, level)
            if not badges:
                continue
            if parked:
                popup_one = popup_badges_for_metars([metar], level)
                labels = {item.get('text') for item in popup_one.get('all') or []}
                if labels & parking_elements:
                    types.append(TYPE_PARK)
            if not types:
                continue
            bucket = tagged.setdefault(airport, {})
            rec = bucket.get(metar.sqc)
            if rec is None:
                rec = {'metar': metar, 'obs': obs, 'types': set(), 'badges': badges}
                bucket[metar.sqc] = rec
            rec['types'].update(types)

    rows = []
    names = _airport_names(sorted(tagged))
    for airport in sorted(tagged):
        params = params_for(cfg, airport)
        gap_ms = int(float(params['gap_hours']) * HOUR_MS)
        segments = _segment_reports(list(tagged[airport].values()), gap_ms)
        for segment in segments:
            types = []
            for name in TYPE_ORDER:
                if any(name in item['types'] for item in segment):
                    types.append(name)
            metars = [item['metar'] for item in segment]
            last = segment[-1]
            start_ms = segment[0]['obs']
            end_ms = last['obs']
            nxt = _metar_after(
                airport, last['obs'], last['metar'].sqc, grouped.get(airport) or [],
            )
            if nxt and nxt.metar_observation_time:
                end_ms = nxt.metar_observation_time
            popup = popup_badges_for_metars(metars, params['alert_level'])
            plain_parts = build_plain_parts(metars, params['alert_level'], popup)
            reports = []
            seen = set()
            for metar in list(grouped.get(airport) or []) + ([nxt] if nxt else []):
                obs = metar.metar_observation_time
                if obs is None or obs < start_ms or obs > end_ms:
                    continue
                key = (obs, metar.sqc or metar.metar_content or '')
                if key in seen:
                    continue
                seen.add(key)
                reports.append({
                    'obs_ms': obs,
                    'content': metar.metar_content or '',
                })
            reports.sort(key=lambda item: item['obs_ms'])
            rows.append({
                'airport': airport,
                'airport_name': names.get(airport) or '',
                'start_ms': start_ms,
                'end_ms': end_ms,
                'badges': popup['all'],
                'element_badges': popup['elements'],
                'weather_badges': popup['weather'],
                'types': types,
                'plain': '；'.join(item['text'] for item in plain_parts if item.get('text')),
                'plain_parts': plain_parts,
                'reports': reports,
            })

    return {
        'preset': kind,
        'start_ms': range_start,
        'end_ms': range_end,
        'config': cfg,
        'rows': rows,
        'flight_count': len(flights),
        'airport_count': len(airports),
        'element_options': element_filter_options(),
        'airport_names': names,
    }
