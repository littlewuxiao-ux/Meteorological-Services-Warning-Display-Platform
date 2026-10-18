"""METAR 最小单元要素 JSON（入库 metar_elements，供明语翻译）。不改动宽表旧列。"""

from __future__ import annotations

import re
from typing import Any, Optional

_METAR_WS_RE = re.compile(
    r'\bWS(?:\s+ALL)?(?:\s+RWY\d*[LCR]?)?(?:\s+R?\d{2}[LCR]?)?',
    re.IGNORECASE,
)


def build_metar_elements(
    content: str,
    airport_code: str,
    parser,
    observation_ms: Optional[int] = None,
) -> Optional[dict[str, Any]]:
    """用当次原文走 avwx 拆最小单元，告警用同一套机场阈值。"""
    if not content or not airport_code:
        return None

    from parsers.plain_language import (
        _avwx_clouds,
        _avwx_visibility,
        _avwx_weather,
        _avwx_wind,
        _max_alert,
    )
    from parsers.report_text_highlight import _parse_avwx_metar, _temp_value_level

    try:
        data, units, is_na = _parse_avwx_metar(content, airport_code)
    except Exception:
        return None
    if data is None or units is None:
        return None

    thresholds = parser._get_airport_thresholds(airport_code) or {}
    wind = _avwx_wind(data, units, thresholds, parser)
    vis = _avwx_visibility(getattr(data, 'visibility', None), units, thresholds, parser)
    weather = _avwx_weather(getattr(data, 'wx_codes', None), parser)
    clouds = _avwx_clouds(getattr(data, 'clouds', None), data, thresholds, parser)
    rvr = _rvr_items(data, is_na, thresholds, parser)
    body = content.split(' RMK')[0]
    shear = str(getattr(data, 'wind_shear', '') or '') or None
    if not shear:
        match = _METAR_WS_RE.search(body)
        shear = match.group().strip() if match else None

    issue_z = None
    time_obj = getattr(data, 'time', None)
    dt = getattr(time_obj, 'dt', None) if time_obj is not None else None
    if dt is not None:
        issue_z = dt.strftime('%d%H%MZ')

    rvr_alert = _max_alert(*[item.get('alert') for item in rvr])
    warning = _max_alert(
        (wind or {}).get('alert'),
        (vis or {}).get('alert'),
        (weather or {}).get('warning'),
        (clouds or {}).get('warning'),
        rvr_alert,
        'R' if shear else None,
    )

    temp_obj = getattr(data, 'temperature', None)
    temp_val = getattr(temp_obj, 'value', None) if temp_obj is not None else None
    dew_obj = getattr(data, 'dewpoint', None)
    dew_val = getattr(dew_obj, 'value', None) if dew_obj is not None else None
    alt = getattr(data, 'altimeter', None)
    alt_val = getattr(alt, 'value', None) if alt is not None else None
    alt_unit = str(getattr(units, 'altimeter', '') or '').lower()

    return {
        'airport': airport_code,
        'observation_time': observation_ms,
        'observation_time_z': issue_z,
        'warning': warning,
        'wind': wind,
        'visibility': vis,
        'weather': weather,
        'clouds': clouds,
        'rvr': rvr,
        'wind_shear': shear,
        'temperature': (
            {'value': temp_val, 'alert': _temp_value_level(float(temp_val), thresholds)}
            if temp_val is not None else None
        ),
        'dewpoint': {'value': dew_val} if dew_val is not None else None,
        'altimeter': (
            {'value': alt_val, 'unit': 'inHg' if alt_unit in ('inhg', 'in') else 'hPa'}
            if alt_val is not None else None
        ),
        'nosig': bool(re.search(r'\bNOSIG\b', body, re.IGNORECASE)),
    }


def _rvr_items(data, is_na: bool, thresholds: dict, parser) -> list:
    from parsers.report_text_highlight import _rvr_numeric

    items = []
    for rvr in getattr(data, 'runway_visibility', None) or []:
        raw = str(getattr(rvr, 'repr', '') or '').strip()
        if not raw:
            continue
        values = [_rvr_numeric(getattr(rvr, 'visibility', None), is_na)]
        for var in getattr(rvr, 'variable_visibility', None) or []:
            values.append(_rvr_numeric(var, is_na))
        valid = [v for v in values if v is not None]
        if not valid:
            continue
        level = parser._get_alert_level(
            min(valid), thresholds.get('rvr_red'), thresholds.get('rvr_yellow'),
            thresholds.get('rvr_green'), reverse=True,
        )
        runway = str(getattr(getattr(rvr, 'runway', None), 'repr', '') or '').strip()
        items.append({
            'runway': runway or None,
            'value': min(valid),
            'alert': level,
            'raw': raw,
        })
    return items
