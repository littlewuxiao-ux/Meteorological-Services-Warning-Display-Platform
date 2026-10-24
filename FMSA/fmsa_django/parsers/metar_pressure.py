"""从报文原文 / 要素 JSON / 接口字段得到气压（hPa）。"""

from __future__ import annotations

import re
from typing import Any, Optional

_QNH_RE = re.compile(r'\bQ(\d{3,4})\b')
_ALTHG_RE = re.compile(r'\bA(\d{4})\b')
_INHG_TO_HPA = 33.8638866667


def _to_hpa(value, unit: str = '') -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    kind = str(unit or '').lower()
    if kind in ('inhg', 'in') or (kind != 'hpa' and number < 50):
        return round(number * _INHG_TO_HPA, 1)
    return round(number, 1)


def pressure_hpa_from_content(content: str) -> Optional[float]:
    body = str(content or '').split(' RMK')[0]
    match = _QNH_RE.search(body)
    if match:
        return float(match.group(1))
    match = _ALTHG_RE.search(body)
    if match:
        raw = match.group(1)
        return _to_hpa(f'{raw[:2]}.{raw[2:]}', 'inhg')
    return None


def pressure_hpa_from_elements(elements: Any) -> Optional[float]:
    if not isinstance(elements, dict):
        return None
    alt = elements.get('altimeter')
    if not isinstance(alt, dict):
        return None
    return _to_hpa(alt.get('value'), alt.get('unit') or '')


def pressure_hpa_from_api(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    if hasattr(raw, 'get'):
        value = raw.get('airPressure')
        if value is None:
            value = raw.get('air_pressure')
    else:
        value = raw
    try:
        if value is None or str(value).strip() in ('', 'nan', 'NaN', 'None'):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def resolve_pressure_hpa(
    content: str = '',
    elements: Any = None,
    raw_item: Any = None,
    avwx_data=None,
    avwx_units=None,
) -> Optional[float]:
    found = pressure_hpa_from_api(raw_item)
    if found is not None:
        return found
    found = pressure_hpa_from_elements(elements)
    if found is not None:
        return found
    if avwx_data is not None:
        alt = getattr(avwx_data, 'altimeter', None)
        if alt is not None and getattr(alt, 'value', None) is not None:
            unit = ''
            if avwx_units is not None:
                unit = str(getattr(avwx_units, 'altimeter', '') or '')
            found = _to_hpa(alt.value, unit)
            if found is not None:
                return found
    return pressure_hpa_from_content(content)
