"""详情页图/表：72 小时 SA 完整性补数，以及读库聚合。"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Iterable, Optional

logger = logging.getLogger('fmsa.detail_metar')

HOUR_MS = 3600 * 1000
SA_LEAD_MS = 10 * 60 * 1000
SA_TAIL_MS = 50 * 60 * 1000
CHART_HOURS = 72
TABLE_HOURS = 24
_WEATHER_SPLIT_RE = re.compile(r'[,\s]+')
_DEW_RE = re.compile(r'^M?(\d+(?:\.\d+)?)$', re.IGNORECASE)


def _now_ms(time_mode: str = 'current') -> int:
    if time_mode == 'test':
        try:
            from utils.time_manager import TimeManager
            return int(TimeManager.get_current_time_utc('test').timestamp() * 1000)
        except Exception:
            pass
    return int(time.time() * 1000)


def hourly_slots(now_ms: int, count: int) -> list[int]:
    last = (int(now_ms) // HOUR_MS) * HOUR_MS
    return [last - (count - 1 - index) * HOUR_MS for index in range(count)]


def sa_window(hour_ms: int) -> tuple[int, int]:
    return int(hour_ms) - SA_LEAD_MS, int(hour_ms) + SA_TAIL_MS


def in_sa_window(obs_ms: int, hour_ms: int) -> bool:
    start, end = sa_window(hour_ms)
    return start <= int(obs_ms) < end


def in_sp_window(obs_ms: int, hour_ms: int) -> bool:
    hour_ms = int(hour_ms)
    return hour_ms <= int(obs_ms) < hour_ms + HOUR_MS


def _metar_kind(row) -> str:
    kind = str(getattr(row, 'metar_type', None) or '').strip().upper()
    if kind in ('SA', 'SP'):
        return kind
    content = str(getattr(row, 'metar_content', '') or '')[:40].upper()
    return 'SP' if 'SPECI' in content else 'SA'


def missing_sa_hours(rows: Iterable, hours: list[int]) -> list[int]:
    covered = set()
    for row in rows:
        if _metar_kind(row) != 'SA':
            continue
        obs = getattr(row, 'metar_observation_time', None)
        if obs is None:
            continue
        for hour in hours:
            if in_sa_window(int(obs), hour):
                covered.add(hour)
                break
    return [hour for hour in hours if hour not in covered]


def _query_window(airport: str, hours: list[int]):
    from runtime_db.models import Metar

    if not hours:
        return Metar.objects.none()
    start, _ = sa_window(hours[0])
    end = hours[-1] + HOUR_MS
    return Metar.objects.filter(
        airport_4code=airport,
        metar_observation_time__gte=start,
        metar_observation_time__lt=end + SA_LEAD_MS,
    ).order_by('metar_observation_time', 'created_at')


def _insert_history_items(airport: str, items: list, now_ms: int, parser) -> int:
    from parsers.cloud_amount import resolve_min_cloud_amt
    from parsers.trend_metar_backfill import _content_key, _parse_row_for_store
    from runtime_db.models import Metar
    from utils.sqlite_retry import retry_if_locked

    if not items:
        return 0
    start_ms = min(item.get('sort_time') or now_ms for item in items) - SA_LEAD_MS
    end_ms = max(item.get('sort_time') or now_ms for item in items) + HOUR_MS
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
    seq_by_obs: dict[int, int] = {}
    inserted = 0
    created_at = int(time.time() * 1000)
    min_cloud_amt = resolve_min_cloud_amt(airport)

    for item in sorted(items, key=lambda row: (row.get('sort_time') or 0, row.get('content') or '')):
        content = item.get('content') or ''
        parsed = _parse_row_for_store(
            content, airport, item.get('wtype') or '', now_ms, parser, min_cloud_amt,
            raw_item=item,
        )
        if not parsed:
            continue
        obs_ms = parsed['metar_observation_time']
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

        def _create(payload=parsed):
            Metar.objects.create(**payload)

        try:
            retry_if_locked(_create)
        except Exception as exc:
            logger.warning('详情历史实况入库失败 [%s] %s: %s', airport, sqc, exc)
            continue
        existing_keys.add(key)
        existing_sqcs.add(sqc)
        inserted += 1
    return inserted


def ensure_sa_history(
    airport_code: str,
    time_mode: str = 'current',
    token: Optional[str] = None,
    hours: int = CHART_HOURS,
) -> dict:
    airport = str(airport_code or '').strip().upper()
    now_ms = _now_ms(time_mode)
    slots = hourly_slots(now_ms, hours)
    if not airport or not slots:
        return {'complete': True, 'missing': 0, 'inserted': 0}

    rows = list(_query_window(airport, slots))
    missing = missing_sa_hours(rows, slots)
    if not missing:
        return {'complete': True, 'missing': 0, 'inserted': 0}

    from parsers.metar_history import fetch_raw_met_list
    from parsers.metar_parser import MetarParser

    start_ms, _ = sa_window(min(missing))
    end_ms = max(missing) + HOUR_MS
    try:
        items = fetch_raw_met_list(
            airport,
            time_mode=time_mode,
            token=token,
            ws_types=['SA', 'SP'],
            start_ms=start_ms,
            end_ms=end_ms,
        )
    except Exception as exc:
        logger.warning('详情历史报文请求失败 [%s]: %s', airport, exc)
        items = []

    inserted = 0
    if items:
        parser = MetarParser(time_mode=time_mode, token=token)
        inserted = _insert_history_items(airport, items, now_ms, parser)
        rows = list(_query_window(airport, slots))
        missing = missing_sa_hours(rows, slots)

    logger.info(
        '详情历史补数 [%s]: 写入 %s 条，仍缺 SA 整点 %s',
        airport, inserted, len(missing),
    )
    return {
        'complete': not missing,
        'missing': len(missing),
        'inserted': inserted,
    }


def chart_points_from_db(airport_code: str, time_mode: str = 'current') -> list[dict]:
    airport = str(airport_code or '').strip().upper()
    now_ms = _now_ms(time_mode)
    slots = hourly_slots(now_ms, CHART_HOURS)
    if not airport:
        return []
    points = []
    for row in _query_window(airport, slots):
        obs = row.metar_observation_time
        if obs is None:
            continue
        points.append({
            'metar_observation_time': int(obs),
            'metar_wind_speed_val': row.metar_wind_speed_val,
            'metar_gust_val': row.metar_gust_val,
            'metar_visibility_val': row.metar_visibility_val,
            'rvr_min_val': row.rvr_min_val,
            'metar_min_cloud_height': row.metar_min_cloud_height,
            'metar_temp_val': row.metar_temp_val,
            'dewPoint': _dew_to_float(row.metar_dew_point),
            'metar_weather': row.metar_weather,
            'airPressure': row.metar_pressure_val,
        })
    points.sort(key=lambda item: item['metar_observation_time'])
    return points


def _hour_weather_codes(rows, hour_ms: int) -> list[str]:
    seen = []
    seen_set = set()
    for item in _union_reports(rows, hour_ms):
        for code in _split_weather(item.metar_weather):
            if code not in seen_set:
                seen_set.add(code)
                seen.append(code)
    return seen


def hourly_weather_from_db(airport_code: str, time_mode: str = 'current') -> list[dict]:
    airport = str(airport_code or '').strip().upper()
    now_ms = _now_ms(time_mode)
    hours = hourly_slots(now_ms, CHART_HOURS)
    rows = list(_query_window(airport, hours)) if airport else []
    result = []
    for hour in hours:
        codes = _hour_weather_codes(rows, hour)
        if codes:
            result.append({'hour': int(hour), 'weather': codes})
    return result


def _dew_to_float(value) -> Optional[float]:
    if value is None or value == '':
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().upper().replace('−', '-')
    if not text:
        return None
    if text.startswith('M') and not text.startswith('M-'):
        text = '-' + text[1:]
    try:
        return float(text)
    except ValueError:
        match = _DEW_RE.match(str(value).strip())
        if not match:
            return None
        number = float(match.group(1))
        return -number if str(value).strip().upper().startswith('M') else number


def _split_weather(text) -> list[str]:
    if not text:
        return []
    parts = []
    for item in _WEATHER_SPLIT_RE.split(str(text).strip()):
        code = item.strip()
        if code:
            parts.append(code)
    return parts


def _union_reports(rows, hour_ms: int) -> list:
    picked = []
    for row in rows:
        obs = row.metar_observation_time
        if obs is None:
            continue
        kind = _metar_kind(row)
        if kind == 'SA' and in_sa_window(obs, hour_ms):
            picked.append(row)
        elif kind == 'SP' and in_sp_window(obs, hour_ms):
            picked.append(row)
    picked.sort(key=lambda item: (item.metar_observation_time or 0, item.created_at or 0))
    return picked


def _hourly_value(rows, hour_ms: int):
    sa_rows = [row for row in rows if _metar_kind(row) == 'SA' and in_sa_window(row.metar_observation_time, hour_ms)]
    sa_rows.sort(key=lambda item: (item.metar_observation_time or 0, item.created_at or 0))
    if sa_rows:
        return sa_rows[0]
    sp_rows = [row for row in rows if _metar_kind(row) == 'SP' and in_sp_window(row.metar_observation_time, hour_ms)]
    sp_rows.sort(key=lambda item: (item.metar_observation_time or 0, item.created_at or 0))
    return sp_rows[0] if sp_rows else None


def _min_num(values):
    numbers = [value for value in values if value is not None]
    return min(numbers) if numbers else None


def _max_num(values):
    numbers = [value for value in values if value is not None]
    return max(numbers) if numbers else None


def _wind_pick(rows) -> Optional[str]:
    best = None
    best_speed = None
    best_obs = None
    for row in rows:
        speed = row.metar_wind_speed_val
        if speed is None:
            continue
        obs = row.metar_observation_time or 0
        if (
            best is None
            or float(speed) > float(best_speed)
            or (float(speed) == float(best_speed) and obs > best_obs)
        ):
            best = row
            best_speed = speed
            best_obs = obs
    if best is None:
        return None
    direction = str(best.metar_wind_direction or '').strip().upper()
    return direction or None


def table_from_db(airport_code: str, time_mode: str = 'current') -> dict:
    airport = str(airport_code or '').strip().upper()
    now_ms = _now_ms(time_mode)
    hours = hourly_slots(now_ms, TABLE_HOURS)
    rows = list(_query_window(airport, hours)) if airport else []
    visibility, rvr, temp, dewpoint = [], [], [], []
    wind_dir, wind_speed, gust, pressure, weather = [], [], [], [], []
    for hour in hours:
        union = _union_reports(rows, hour)
        hourly = _hourly_value(rows, hour)
        visibility.append(_min_num(item.metar_visibility_val for item in union))
        rvr.append(_min_num(item.rvr_min_val for item in union))
        temp.append(None if hourly is None else hourly.metar_temp_val)
        dewpoint.append(None if hourly is None else _dew_to_float(hourly.metar_dew_point))
        wind_dir.append(_wind_pick(union))
        wind_speed.append(_max_num(item.metar_wind_speed_val for item in union))
        gust.append(_max_num(item.metar_gust_val for item in union))
        pressure.append(None if hourly is None else hourly.metar_pressure_val)
        weather.append(_hour_weather_codes(rows, hour))
    return {
        'hours': hours,
        'now': now_ms,
        'rows': {
            'visibility': visibility,
            'rvr': rvr,
            'temp': temp,
            'dewpoint': dewpoint,
            'wind_dir': wind_dir,
            'wind_speed': wind_speed,
            'gust': gust,
            'pressure': pressure,
            'weather': weather,
        },
    }
