"""机场资料补齐：外部接口提供坐标和名称，前缀表提供国内/国际和区域。"""

import logging

import requests

from core.models import AirportInfo, AirportPrefixArea, AirportTafImportConfig

logger = logging.getLogger('mtws.core')

MISSING_AIRPORT_NAME = '机场名称未配置'


def display_airport_name(name) -> str:
    text = str(name or '').strip()
    return text or MISSING_AIRPORT_NAME


def prefix_rules():
    rows = list(AirportPrefixArea.objects.all())
    rows.sort(key=lambda row: len(row.prefix or ''), reverse=True)
    return rows


def match_prefix(code: str, rules=None):
    airport = str(code or '').strip().upper()
    if len(airport) < 1:
        return None
    for rule in rules if rules is not None else prefix_rules():
        prefix = str(rule.prefix or '').strip().upper()
        if prefix and airport.startswith(prefix):
            return rule
    return None


def apply_prefix_if_blank(airport: AirportInfo, rules=None) -> bool:
    if (airport.classification or '').strip() and (airport.area or '').strip():
        return False
    rule = match_prefix(airport.airport_4code, rules)
    if rule is None:
        return False
    changed = False
    if not (airport.classification or '').strip():
        airport.classification = rule.classification
        changed = True
    if not (airport.area or '').strip():
        airport.area = rule.area
        changed = True
    return changed


def airport_config_gaps(airport: AirportInfo, taf_config) -> list:
    gaps = []
    if airport.latitude is None or airport.longitude is None:
        gaps.append('坐标未获取，请手动配置')
    if not str(airport.airport_name or '').strip():
        gaps.append(MISSING_AIRPORT_NAME)
    if not (airport.classification or '').strip() or not (airport.area or '').strip():
        gaps.append('区域未识别，请手动配置')
    if (
        taf_config is None
        or taf_config.taf_init_time is None
        or taf_config.import_check_interval is None
        or taf_config.taf_max_delay is None
    ):
        gaps.append('预报入库配置未完成，请手动配置')
    return gaps


def _create_stub(code: str, rules) -> AirportInfo:
    airport = AirportInfo(airport_4code=code, catalog_only=False)
    try:
        from utils.airport_coords import fetch_aviationweather_airport
        info = fetch_aviationweather_airport(code)
        lat, lon = info.get('lat'), info.get('lon')
        if lat is not None and lon is not None:
            airport.latitude = float(lat)
            airport.longitude = float(lon)
        name = info.get('name')
        if name:
            airport.airport_name = name
    except (requests.RequestException, ValueError, TypeError) as exc:
        logger.warning('获取机场 %s 坐标或名称失败: %s', code, exc)
    apply_prefix_if_blank(airport, rules)
    airport.save()
    return airport


def _infer_taf_config(airport: AirportInfo, time_mode: str, token):
    if airport.taf_infer_attempted:
        return
    if not token and time_mode == 'current':
        return
    from parsers.metar_history import _fetch_history_obj
    from parsers.taf_schedule import default_delay_minutes, infer_schedule

    try:
        from datetime import datetime, timezone
        from parsers.metar_history import _item_wtype
        now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
        obj, now_ms, ok = _fetch_history_obj(
            airport.airport_4code,
            time_mode,
            token,
            ws_types=['FC', 'FT'],
            start_ms=now_ms - 7 * 24 * 3_600_000,
            end_ms=now_ms,
        )
    except Exception as exc:
        logger.warning('读取机场 %s 历史预报失败: %s', airport.airport_4code, exc)
        return
    if not ok:
        return
    reports = []
    for item in obj or []:
        content = (item.get('content') or '').strip()
        if not content:
            continue
        reports.append({'wtype': _item_wtype(item, content), 'content': content})
    schedule = infer_schedule(reports)
    delay = default_delay_minutes(airport.classification)
    airport.taf_infer_attempted = True
    airport.save(update_fields=['taf_infer_attempted'])
    if schedule is None and delay is None:
        return
    AirportTafImportConfig.objects.update_or_create(
        airport_4code=airport.airport_4code,
        defaults={
            'taf_init_time': None if schedule is None else schedule['taf_init_time'],
            'import_check_interval': None if schedule is None else schedule['import_check_interval'],
            'taf_max_delay': delay,
        },
    )


def ensure_flight_airports(codes, time_mode='current', token=None):
    """有航班但资料不全的机场：补坐标、名称、区域，并在首次尝试推断预报入库配置。"""
    wanted = []
    seen = set()
    for raw in codes or []:
        code = str(raw or '').strip().upper()
        if len(code) == 4 and code.isalpha() and code not in seen and code != 'DEFAULT':
            seen.add(code)
            wanted.append(code)
    if not wanted:
        return
    rules = prefix_rules()
    existing = {
        row.airport_4code: row
        for row in AirportInfo.objects.filter(airport_4code__in=wanted)
    }
    has_taf = set(
        AirportTafImportConfig.objects.filter(airport_4code__in=wanted)
        .values_list('airport_4code', flat=True)
    )
    for code in wanted:
        airport = existing.get(code)
        if airport is None:
            airport = _create_stub(code, rules)
            existing[code] = airport
        else:
            updates = []
            if airport.catalog_only:
                airport.catalog_only = False
                updates.append('catalog_only')
            if apply_prefix_if_blank(airport, rules):
                updates.extend(['classification', 'area'])
            if updates:
                airport.save(update_fields=list(dict.fromkeys(updates)))
        if code not in has_taf:
            _infer_taf_config(airport, time_mode, token)
