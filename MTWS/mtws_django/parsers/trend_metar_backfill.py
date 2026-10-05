"""趋势重算前：按最长回看窗口补齐整点例行报历史。"""

from __future__ import annotations

import logging
import threading
import time
from typing import Iterable, Optional

logger = logging.getLogger('mtws.trend')

HOUR_MS = 3600 * 1000
SLOT_WINDOW_MS = 10 * 60 * 1000


def hourly_slots(since_ms: int, now_ms: int) -> list[int]:
    """回看窗口内需要具备 SA 的整点时刻列表。"""
    since_ms = int(since_ms)
    now_ms = int(now_ms)
    if now_ms < since_ms:
        return []
    first = (since_ms // HOUR_MS) * HOUR_MS
    if first < since_ms:
        first += HOUR_MS
    last = (now_ms // HOUR_MS) * HOUR_MS
    slots = []
    slot = first
    while slot <= last:
        slots.append(int(slot))
        slot += HOUR_MS
    return slots


def hour_for_sa(obs_ms: int, slots: Iterable[int]) -> Optional[int]:
    """例行报观测时刻落到哪个整点窗口；对不上则返回 None。"""
    obs_ms = int(obs_ms)
    for slot in slots:
        if abs(obs_ms - slot) <= SLOT_WINDOW_MS:
            return int(slot)
    return None


def normalize_content(content: str) -> str:
    return ' '.join(str(content or '').strip().split())


def missing_hourly_slots(sa_obs_times: Iterable[int], since_ms: int, now_ms: int) -> list[int]:
    slots = hourly_slots(since_ms, now_ms)
    covered = set()
    for obs in sa_obs_times or []:
        if obs is None:
            continue
        hit = hour_for_sa(int(obs), slots)
        if hit is not None:
            covered.add(hit)
    return [slot for slot in slots if slot not in covered]


def _resolve_token(time_mode: str, token: Optional[str]) -> Optional[str]:
    if token:
        return token
    if time_mode != 'current':
        return None
    try:
        from parsers.scheduler import get_scheduler_token
        return get_scheduler_token()
    except Exception:
        return None


def _dewpoint_text(value) -> Optional[str]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return f'M{abs(int(round(number))):02d}' if abs(number - int(number)) < 1e-9 else f'M{abs(number):.1f}'
    if abs(number - int(number)) < 1e-9:
        return f'{int(number):02d}'
    return f'{number:.1f}'


def _cloud_text(data) -> Optional[str]:
    clouds = getattr(data, 'clouds', None) or []
    parts = []
    for cloud in clouds:
        raw = str(getattr(cloud, 'repr', '') or '').strip()
        if raw:
            parts.append(raw)
    return ' '.join(parts) if parts else None


def _parse_row_for_store(
    content: str,
    airport_code: str,
    wtype: str,
    now_ms: int,
    parser,
    min_cloud_amt: Optional[str] = None,
) -> Optional[dict]:
    from parsers.metar_elements import build_metar_elements
    from parsers.metar_history import _extract_obs_timestamp_ms, _visibility_to_m, _wind_to_mps
    from parsers.report_text_highlight import _parse_avwx_metar

    content = (content or '').strip()
    if not content:
        return None
    obs_ts = _extract_obs_timestamp_ms(content, now_ms)
    if obs_ts is None:
        return None
    try:
        data, units, _is_na = _parse_avwx_metar(content, airport_code)
    except Exception:
        return None
    if data is None or units is None:
        return None

    wind_speed = _wind_to_mps(
        data.wind_speed.value if data.wind_speed else None,
        units.wind_speed,
    )
    gust = _wind_to_mps(
        data.wind_gust.value if data.wind_gust else None,
        units.wind_speed,
    )
    vis_val = None
    if data.visibility:
        vis_repr = data.visibility.repr or ''
        if vis_repr in ('CAVOK',) or vis_repr.startswith('P6'):
            vis_val = 10000
        else:
            vis_val = _visibility_to_m(data.visibility.value, units.visibility)
    from parsers.cloud_amount import lowest_base_from_cloud_objects, resolve_min_cloud_amt
    if min_cloud_amt is None:
        min_cloud_amt = resolve_min_cloud_amt(airport_code)
    min_cloud_height = lowest_base_from_cloud_objects(data.clouds, min_cloud_amt)
    temp_val = None
    if data.temperature and data.temperature.value is not None:
        temp_val = float(data.temperature.value)
    dew_val = None
    if data.dewpoint and data.dewpoint.value is not None:
        dew_val = float(data.dewpoint.value)
    weather = None
    if data.wx_codes:
        codes = [c.repr for c in data.wx_codes if c.repr]
        if codes:
            weather = ','.join(codes)
    kind = str(wtype or '').strip().upper()
    if kind not in ('SA', 'SP'):
        kind = 'SP' if 'SPECI' in content[:40].upper() else 'SA'

    elements = None
    try:
        elements = build_metar_elements(content, airport_code, parser, observation_ms=obs_ts)
    except Exception as exc:
        logger.debug('趋势补数构建 metar_elements 失败 [%s]: %s', airport_code, exc)

    return {
        'airport_4code': airport_code,
        'metar_content': content,
        'metar_observation_time': obs_ts,
        'metar_type': kind,
        'metar_temp_val': temp_val,
        'metar_temperature': None if temp_val is None else str(temp_val),
        'metar_dew_point': _dewpoint_text(dew_val),
        'metar_wind_speed_val': wind_speed,
        'metar_gust_val': gust,
        'metar_visibility_val': vis_val,
        'metar_weather': weather,
        'metar_cloud': _cloud_text(data),
        'metar_min_cloud_height': min_cloud_height,
        'metar_elements': elements,
        'metar_warning': 'N',
        'data_status': 'H',
        'operation_popup': 'N',
        'parking_popup': 'N',
    }


def _existing_sa_times(airport: str, since_ms: int, now_ms: int) -> list[int]:
    from parsers.models import Metar

    rows = Metar.objects.filter(
        airport_4code=airport,
        metar_type='SA',
        metar_observation_time__gte=since_ms - SLOT_WINDOW_MS,
        metar_observation_time__lte=now_ms + SLOT_WINDOW_MS,
    ).values_list('metar_observation_time', flat=True)
    return [int(value) for value in rows if value is not None]


def _content_key(obs_ms: int, content: str) -> tuple:
    return (int(obs_ms), normalize_content(content))


def _backfill_airport(
    airport: str,
    missing: list[int],
    now_ms: int,
    time_mode: str,
    token: Optional[str],
    parser,
) -> int:
    from parsers.metar_history import fetch_raw_met_list
    from parsers.models import Metar

    if not missing:
        return 0
    from django.db import connection
    connection.close()
    start_ms = min(missing) - SLOT_WINDOW_MS
    end_ms = max(missing) + SLOT_WINDOW_MS
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
        logger.warning('趋势历史报文请求失败 [%s]: %s', airport, exc)
        return 0
    if not items:
        logger.info('趋势历史报文为空 [%s] %s-%s', airport, start_ms, end_ms)
        return 0

    missing_set = set(missing)
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
    from parsers.cloud_amount import resolve_min_cloud_amt
    min_cloud_amt = resolve_min_cloud_amt(airport)

    for item in sorted(items, key=lambda row: (row.get('sort_time') or 0, row.get('content') or '')):
        content = item.get('content') or ''
        parsed = _parse_row_for_store(
            content, airport, item.get('wtype') or '', now_ms, parser, min_cloud_amt,
        )
        if not parsed:
            continue
        obs_ms = parsed['metar_observation_time']
        slot = hour_for_sa(obs_ms, missing_set)
        if slot is None:
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
        except Exception as exc:
            logger.warning('趋势历史实况入库失败 [%s] %s: %s', airport, sqc, exc)
            continue
        existing_keys.add(key)
        existing_sqcs.add(sqc)
        inserted += 1
    if inserted:
        logger.info('趋势历史实况补数 [%s]: 写入 %s 条，缺失整点 %s', airport, inserted, len(missing))
    return inserted


def ensure_hourly_sa_history(
    airports: Iterable[str],
    lookback_ms: int,
    now_ms: Optional[int] = None,
    time_mode: str = 'current',
    token: Optional[str] = None,
) -> None:
    """
    最长回看窗口内每个整点至少一份 SA；不够则按缺失时段补拉 airportMetList。
    补数失败只记日志，不抛出，由调用方继续用现有本地数据重算。
    """
    codes = sorted({str(code).upper() for code in airports or [] if code})
    if not codes or lookback_ms <= 0:
        return
    now_ms = int(now_ms if now_ms is not None else time.time() * 1000)
    since_ms = now_ms - int(lookback_ms)
    token = _resolve_token(time_mode, token)
    try:
        from parsers.metar_parser import MetarParser
        parser = MetarParser(time_mode=time_mode, token=token)
    except Exception as exc:
        logger.warning('趋势历史补数初始化解析器失败: %s', exc)
        return

    for airport in codes:
        try:
            missing = missing_hourly_slots(_existing_sa_times(airport, since_ms, now_ms), since_ms, now_ms)
            if not missing:
                continue
            _backfill_airport(airport, missing, now_ms, time_mode, token, parser)
        except Exception:
            logger.exception('趋势历史实况补数失败: %s', airport)


_backfill_lock = threading.Lock()
_backfill_pending: dict[str, tuple[int, int]] = {}
_backfill_event = threading.Event()
_backfill_worker_started = False


def queue_hourly_sa_history(airports: Iterable[str], lookback_ms: int, now_ms: int) -> None:
    """补数放到单独线程，不跟本次实况/航班写入挤在同一段执行里。"""
    global _backfill_worker_started
    codes = sorted({str(code).upper() for code in airports or [] if code})
    if not codes or lookback_ms <= 0:
        return
    with _backfill_lock:
        for code in codes:
            prev = _backfill_pending.get(code)
            if prev is None or int(lookback_ms) > prev[0] or int(now_ms) > prev[1]:
                _backfill_pending[code] = (int(lookback_ms), int(now_ms))
        if not _backfill_worker_started:
            _backfill_worker_started = True
            threading.Thread(
                target=_backfill_worker,
                name='trend-sa-backfill',
                daemon=True,
            ).start()
        _backfill_event.set()


def _backfill_worker() -> None:
    from django.db import close_old_connections

    while True:
        _backfill_event.wait()
        with _backfill_lock:
            batch = dict(_backfill_pending)
            _backfill_pending.clear()
            _backfill_event.clear()
        if not batch:
            continue
        close_old_connections()
        try:
            codes = sorted(batch)
            lookback = max(item[0] for item in batch.values())
            now_ms = max(item[1] for item in batch.values())
            ensure_hourly_sa_history(codes, lookback, now_ms)
            from utils.trend_alert import refresh_airports
            refresh_airports(codes, now_ms, backfill=False)
        except Exception:
            logger.exception('趋势历史实况补数线程失败: %s', sorted(batch))
        finally:
            close_old_connections()
            with _backfill_lock:
                if _backfill_pending:
                    _backfill_event.set()
