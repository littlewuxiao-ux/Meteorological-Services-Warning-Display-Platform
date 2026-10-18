"""TAF 最小单元要素 JSON（入库 taf_elements，供明语翻译）。不改动宽表旧列。"""

from __future__ import annotations

import re
from typing import Any, Optional

def _weather_alert(code: str) -> str:
    from parsers.taf_parser import get_weather_alert_level
    return get_weather_alert_level(code)


def _cloud_alert(height: int, airport_info: dict) -> Optional[str]:
    from parsers.taf_parser import ALERT_NONE, get_cloud_alert_level
    try:
        return get_cloud_alert_level(int(height), airport_info)
    except Exception:
        return ALERT_NONE


def _wind_sub_alerts(speed_mps, gust_mps, airport_info: dict) -> tuple:
    """平均风与阵风各自的告警等级；风组整体等级仍是两者取高。"""
    from parsers.taf_parser import get_gust_alert_level, get_wind_alert_level

    speed_alert = None
    gust_alert = None
    if speed_mps not in (None, ''):
        try:
            speed_alert = get_wind_alert_level(float(speed_mps), airport_info)
        except (TypeError, ValueError):
            speed_alert = None
    if gust_mps not in (None, ''):
        try:
            gust_alert = get_gust_alert_level(float(gust_mps), airport_info)
        except (TypeError, ValueError):
            gust_alert = None
    return _alert(speed_alert), _alert(gust_alert)

_CLOUD_TOKEN = re.compile(
    r'(VV|FEW|SCT|BKN|OVC|NSC|SKC|CLR|NCD)(\d{3})?(CB|TCU)?',
    re.IGNORECASE,
)
_WIND_TOKEN = re.compile(
    r'(VRB|\d{2,3})(\d{2})(?:G(\d+))?(KT|MPS|KMH)?',
    re.IGNORECASE,
)


def _ddhh(ts) -> Optional[str]:
    dt = getattr(ts, 'dt', None) if ts is not None else None
    if dt is None:
        return None
    return dt.strftime('%d%H')


def _num(obj) -> Optional[float]:
    if obj is None:
        return None
    value = getattr(obj, 'value', obj)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _repr(obj) -> Optional[str]:
    if obj is None:
        return None
    text = getattr(obj, 'repr', None)
    if text:
        return str(text)
    return str(obj) if obj != '' else None


def _alert(value) -> Optional[str]:
    if value is None or value == '':
        return None
    return str(value)


def _other_tokens(line) -> list:
    if line is None:
        return []
    return [str(item).upper() for item in (getattr(line, 'other', None) or [])]


def build_taf_elements(parser) -> dict[str, Any]:
    """从解析器内存状态生成 taf_elements。"""
    cancelled = (getattr(parser, 'abnormal_label', '') or '') in ('CNL', 'AMD_CNL')
    issue_z = None
    taf_obj = getattr(parser, 'taf_obj', None)
    data = getattr(taf_obj, 'data', None) if taf_obj is not None else None
    time_obj = getattr(data, 'time', None) if data is not None else None
    if time_obj is not None and getattr(time_obj, 'dt', None) is not None:
        issue_z = time_obj.dt.strftime('%d%H%MZ')
    payload = {
        'airport': parser.airport_4code or None,
        'issue_time': parser.observation_time,
        'issue_time_z': issue_z,
        'amended': parser.amd_or_cor == 'AMD',
        'corrected': parser.amd_or_cor == 'COR',
        'cancelled': cancelled,
        'whole_validity': parser.whole_validity_period or None,
        'subject_period': {
            'start': parser.subject_validity_period_start or None,
            'end': parser.subject_validity_period_end or None,
        },
        'temperatures': _temperatures(parser),
        'subject': None,
        'changes': [],
    }
    if cancelled:
        return payload

    own_flags = getattr(parser, '_own_elements', {}) or {}
    airport_info = parser.get_airport_info()
    subject_line = getattr(parser, '_subject_line', None)
    payload['subject'] = _build_period(
        parser,
        line=subject_line,
        group=None,
        inherited_flags={},
        airport_info=airport_info,
        warning=_alert(parser.subject_warning),
        always_own=True,
    )

    for index in sorted(parser.change_groups):
        group = parser.change_groups[index]
        payload['changes'].append(
            _build_change(
                parser,
                group,
                own_flags.get(index, {}),
                airport_info,
            )
        )
    return payload


def _temperatures(parser) -> list:
    items = []
    for kind, prefix in (('max', 'subject_max_temp'), ('min', 'subject_min_temp')):
        for slot in (1, 2):
            value = getattr(parser, f'{prefix}{slot}', '') or ''
            if not str(value).strip():
                continue
            items.append({
                'kind': kind,
                'value': str(value).strip(),
                'time': getattr(parser, f'{prefix}{slot}_time', '') or None,
                'alert': _alert(getattr(parser, f'{prefix}{slot}_warning', None)),
            })
    return items


def _build_change(parser, group: dict, flags: dict, airport_info: dict) -> dict:
    change_type = (group.get('type') or '').strip()
    line = group.get('_line')
    normalized = change_type.upper().replace(' ', '')
    period = {
        'type': change_type or None,
        'probability': _probability(line, normalized),
        'transition_start': None,
        'start': group.get('validity_period_start') or None,
        'end': group.get('validity_period_end') or None,
        'warning': _alert(group.get('warning')),
    }
    if normalized == 'FROM' or normalized.startswith('FM'):
        period['start'] = _ddhh(getattr(line, 'start_time', None)) or period['start']
        period['end'] = None
    elif normalized == 'BECMG':
        period['transition_start'] = _ddhh(getattr(line, 'transition_start', None))
        period['start'] = _ddhh(getattr(line, 'start_time', None)) or period['start']
        period['end'] = None
    inherited_flags = flags if normalized == 'BECMG' else {
        'wind': True,
        'visibility': True,
        'weather': True,
        'cloud': True,
    }
    period.update(_build_period(
        parser,
        line=line,
        group=group,
        inherited_flags=inherited_flags,
        airport_info=airport_info,
        warning=period['warning'],
        always_own=False,
    ))
    return period


def _probability(line, normalized: str) -> Optional[int]:
    if line is not None:
        value = _num(getattr(line, 'probability', None))
        if value is not None:
            return int(value)
    match = re.match(r'PROB(\d+)', normalized or '')
    if match:
        return int(match.group(1))
    return None


def _build_period(
    parser,
    *,
    line,
    group: Optional[dict],
    inherited_flags: dict,
    airport_info: dict,
    warning: Optional[str],
    always_own: bool,
) -> dict:
    vis_inherited = (not always_own) and not inherited_flags.get('visibility', True)
    wx_inherited = (not always_own) and not inherited_flags.get('weather', True)
    cloud_inherited = (not always_own) and not inherited_flags.get('cloud', True)
    wind_inherited = (not always_own) and not inherited_flags.get('wind', True)

    return {
        'warning': warning,
        'wind': _wind(parser, line, group, wind_inherited, always_own, airport_info),
        'visibility': _visibility(parser, line, group, vis_inherited, always_own, inherited_flags),
        'weather': _weather(parser, line, group, wx_inherited, always_own),
        'clouds': _clouds(parser, line, group, cloud_inherited, always_own, airport_info),
        'wind_shear': _wind_shear(line),
    }


def _wind(parser, line, group, inherited: bool, always_own: bool, airport_info: dict) -> Optional[dict]:
    if always_own:
        direction, speed, gust, unit, variable = _wind_from_line(line)
        if direction is None and speed is None:
            return None
        alert = _alert(parser.subject_wind_warning)
        subs = _wind_sub_alerts(parser.subject_wind_speed_mps, parser.subject_gust_mps, airport_info)
        return _wind_dict(direction, speed, gust, unit, variable, alert, False, subs)

    # 变化组的风速已由解析器换算成 m/s 存在组里，子告警按换算值判
    subs = _wind_sub_alerts(
        (group or {}).get('wind_speed_mps'), (group or {}).get('gust_mps'), airport_info
    )
    alert = _alert(group.get('wind_warning') if group else None)

    if inherited:
        direction, speed, gust, unit = _wind_from_group(group)
        if direction is None and speed is None:
            return None
        return _wind_dict(direction, speed, gust, unit, None, alert, True, subs)

    direction, speed, gust, unit, variable = _wind_from_line(line)
    if direction is None and speed is None:
        return None
    return _wind_dict(direction, speed, gust, unit, variable, alert, False, subs)


def _wind_from_line(line) -> tuple:
    if line is None:
        return None, None, None, None, None
    direction = None
    wind_dir = getattr(line, 'wind_direction', None)
    if wind_dir is not None:
        if getattr(wind_dir, 'value', None) is not None:
            try:
                direction = str(int(float(wind_dir.value))).zfill(3)
            except (TypeError, ValueError):
                direction = _repr(wind_dir)
        else:
            direction = _repr(wind_dir)
    speed = _num(getattr(line, 'wind_speed', None))
    gust = _num(getattr(line, 'wind_gust', None))
    unit = None
    speed_obj = getattr(line, 'wind_speed', None)
    if speed_obj is not None:
        unit = getattr(speed_obj, 'units', None) or None
        if not unit:
            repr_s = (_repr(speed_obj) or '').upper()
            for token in ('MPS', 'KMH', 'KT'):
                if token in repr_s:
                    unit = token
                    break
    if unit == 'kt':
        unit = 'KT'
    elif unit in ('m/s', 'mps'):
        unit = 'MPS'
    if not unit and line is not None:
        raw_line = (getattr(line, 'raw', '') or '').upper()
        for token in ('MPS', 'KMH', 'KT'):
            if re.search(rf'\b\d{{2,3}}\d{{2}}(?:G\d+)?{token}\b', raw_line) or token in raw_line:
                if token in raw_line:
                    unit = token
                    break
    variable = None
    vardir = getattr(line, 'wind_variable_direction', None) or []
    if len(vardir) >= 2:
        variable = {'from': _num(vardir[0]), 'to': _num(vardir[1])}
    return direction, speed, gust, unit, variable


def _wind_from_group(group: Optional[dict]) -> tuple:
    if not group:
        return None, None, None, None
    direction = group.get('wind_direction') or None
    speed = group.get('wind_speed')
    gust = group.get('gust')
    unit = None
    raw = (group.get('wind') or '').replace('(', '').replace(')', '')
    match = _WIND_TOKEN.search(raw.replace(' ', ''))
    if match:
        direction = direction or match.group(1)
        speed = speed or match.group(2)
        gust = gust or match.group(3)
        unit = match.group(4)
    try:
        speed_n = float(speed) if speed not in (None, '') else None
    except (TypeError, ValueError):
        speed_n = None
    try:
        gust_n = float(gust) if gust not in (None, '') else None
    except (TypeError, ValueError):
        gust_n = None
    return direction, speed_n, gust_n, unit


def _wind_dict(direction, speed, gust, unit, variable, alert, inherited: bool,
               sub_alerts: tuple = (None, None)) -> dict:
    return {
        'direction': direction,
        'speed': speed,
        'gust': gust,
        'unit': unit,
        'variable': variable,
        'alert': alert,
        'speed_alert': sub_alerts[0],
        'gust_alert': sub_alerts[1],
        'inherited': inherited,
    }


def _visibility(parser, line, group, inherited: bool, always_own: bool, flags: dict) -> Optional[dict]:
    if always_own:
        raw, unit, cavok = _vis_from_line(line)
        if raw is None:
            return None
        return {
            'raw': raw,
            'value': raw,
            'unit': unit,
            'cavok': cavok,
            'alert': _alert(parser.subject_visibility_warning),
            'inherited': False,
        }

    own_cavok = bool(flags.get('cavok'))
    if inherited:
        current = ((group or {}).get('visibility') or '').strip('()')
        if not current:
            return None
        from_cavok = bool((group or {}).get('_vis_from_cavok') or own_cavok)
        value = current
        raw = 'CAVOK' if from_cavok else current
        unit = 'SM' if value.upper() in ('P6', 'P6SM') else None
        if value.isdigit():
            unit = unit or 'm'
        if value.upper() == 'CAVOK':
            from_cavok = True
        return {
            'raw': raw,
            'value': value,
            'unit': unit,
            'cavok': from_cavok and value.upper() == 'CAVOK',
            'alert': _alert((group or {}).get('visibility_warning')),
            'inherited': True,
        }

    raw, unit, cavok = _vis_from_line(line)
    if raw is None:
        current = ((group or {}).get('visibility') or '').strip()
        if not current:
            return None
        raw, cavok = current, current.upper() == 'CAVOK'
    return {
        'raw': raw,
        'value': raw,
        'unit': unit,
        'cavok': cavok,
        'alert': _alert((group or {}).get('visibility_warning')),
        'inherited': False,
    }


def _vis_from_line(line) -> tuple:
    if line is None or not getattr(line, 'visibility', None):
        return None, None, False
    vis = line.visibility
    raw = _repr(vis)
    cavok = (raw or '').upper() == 'CAVOK'
    unit = getattr(vis, 'units', None)
    if unit in ('N/A', '', None):
        unit = None
    elif unit == 'sm':
        unit = 'SM'
    elif unit == 'm':
        unit = 'm'
    if unit is None and raw and str(raw).isdigit() and int(raw) >= 100:
        unit = 'm'
    return raw, unit, cavok


def _weather(parser, line, group, inherited: bool, always_own: bool) -> dict:
    items = []
    if always_own or not inherited:
        codes = _weather_codes_from_line(line)
        if not codes and group and not always_own:
            codes = _weather_codes_from_group(group)
        if always_own and not codes:
            codes = _weather_codes_from_subject(parser)
        for code in codes:
            items.append({
                'code': code,
                'alert': _weather_alert(code),
                'inherited': False,
            })
        warning = parser.subject_weather_warning if always_own else (group or {}).get('weather_warning')
        return {
            'items': items,
            'warning': _alert(warning),
            'inherited': False,
        }

    codes = _weather_codes_from_group(group)
    for code in codes:
        items.append({
            'code': code,
            'alert': _weather_alert(code),
            'inherited': True,
        })
    return {
        'items': items,
        'warning': _alert((group or {}).get('weather_warning')),
        'inherited': True,
    }


def _weather_codes_from_line(line) -> list:
    codes = []
    if line is None:
        return codes
    for wx in getattr(line, 'wx_codes', None) or []:
        token = getattr(wx, 'repr', None) or str(wx)
        if token:
            codes.append(str(token).strip())
    others = _other_tokens(line)
    if 'NSW' in others and 'NSW' not in [c.upper() for c in codes]:
        codes.append('NSW')
    return codes


def _weather_codes_from_group(group: Optional[dict]) -> list:
    if not group:
        return []
    codes = []
    for key in ('weather1', 'weather2', 'weather3', 'weather4', 'weather5'):
        token = (group.get(key) or '').strip().strip('()')
        if token:
            codes.append(token)
    if not codes:
        blob = (group.get('weather') or '').strip().strip('()')
        if blob:
            codes.extend(blob.split())
    return codes


def _weather_codes_from_subject(parser) -> list:
    codes = []
    for key in ('subject_weather1', 'subject_weather2', 'subject_weather3', 'subject_weather4', 'subject_weather5'):
        token = (getattr(parser, key, '') or '').strip()
        if token:
            codes.append(token)
    return codes


def _clouds(parser, line, group, inherited: bool, always_own: bool, airport_info: dict) -> dict:
    sky = _sky_condition(line, group, inherited)
    if always_own or not inherited:
        layers = _cloud_layers_from_line(line, airport_info)
        if not layers and group and not always_own:
            layers = _cloud_layers_from_text(group.get('cloud') or '', airport_info)
        warning = parser.subject_cloud_warning if always_own else (group or {}).get('cloud_warning')
        return {
            'sky': sky,
            'layers': layers,
            'warning': _alert(warning),
            'inherited': False,
        }
    layers = _cloud_layers_from_text((group or {}).get('cloud') or '', airport_info)
    return {
        'sky': sky,
        'layers': layers,
        'warning': _alert((group or {}).get('cloud_warning')),
        'inherited': True,
    }


def _sky_condition(line, group, inherited: bool) -> Optional[str]:
    others = _other_tokens(line)
    for token in ('NSC', 'SKC', 'CLR', 'NCD'):
        if token in others:
            return token
    if inherited and group:
        cloud = (group.get('cloud') or '').strip().strip('()').upper()
        if cloud in ('NSC', 'SKC', 'CLR', 'NCD'):
            return cloud
    if line is not None:
        raw = (getattr(line, 'raw', '') or '').upper()
        for token in ('NSC', 'SKC', 'CLR'):
            if re.search(rf'\b{token}\b', raw):
                return token
    return None


def _cloud_layers_from_line(line, airport_info: dict) -> list:
    layers = []
    if line is None:
        return layers
    vv = getattr(line, 'vertical_visibility', None)
    if vv is not None:
        height = int(_num(vv) or 0)
        layers.append(_cloud_layer('VV', height, None, airport_info, False))
    for cloud in getattr(line, 'clouds', None) or []:
        quantity = getattr(cloud, 'type', None)
        height = getattr(cloud, 'base', None)
        modifier = getattr(cloud, 'modifier', None)
        if quantity is None and not getattr(cloud, 'repr', None):
            continue
        if quantity is None:
            match = _CLOUD_TOKEN.search(getattr(cloud, 'repr', '') or '')
            if match:
                quantity, height_s, modifier = match.group(1).upper(), match.group(2), match.group(3)
                height = int(height_s) if height_s else None
        layers.append(_cloud_layer(quantity, height, modifier, airport_info, False))
    return layers


def _cloud_layers_from_text(text: str, airport_info: dict) -> list:
    layers = []
    for match in _CLOUD_TOKEN.finditer((text or '').replace('(', '').replace(')', '')):
        quantity = match.group(1).upper()
        if quantity in ('NSC', 'SKC', 'CLR', 'NCD'):
            continue
        height = int(match.group(2)) if match.group(2) else None
        modifier = match.group(3).upper() if match.group(3) else None
        layers.append(_cloud_layer(quantity, height, modifier, airport_info, True))
    return layers


def _cloud_layer(quantity, height, modifier, airport_info: dict, inherited: bool) -> dict:
    alert = _cloud_alert(height, airport_info) if height is not None else None
    return {
        'cover': quantity,
        'height': height,
        'height_unit': 'hft',
        'type': modifier,
        'alert': alert,
        'inherited': inherited,
    }


def _wind_shear(line) -> Optional[str]:
    if line is None:
        return None
    shear = getattr(line, 'wind_shear', None)
    if not shear:
        return None
    return str(shear)
