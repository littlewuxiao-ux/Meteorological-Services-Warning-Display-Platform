"""按用户保存每个机场最新一条实况、预报告警。原始报文仍只存一份。"""

from parsers.taf_parser import (
    ALERT_GREEN, ALERT_NONE, ALERT_RED, ALERT_YELLOW,
    get_cloud_alert_level, get_gust_alert_level, get_temperature_alert_level,
    get_visibility_alert_level, get_weather_alert_level, get_wind_alert_level,
)
from utils.user_settings import get_threshold_row, threshold_dict, use_settings_user

_RANK = {ALERT_NONE: 0, ALERT_GREEN: 1, ALERT_YELLOW: 2, ALERT_RED: 3, 'N': 0, 'G': 1, 'Y': 2, 'R': 3}


def _max_level(*levels):
    valid = [level for level in levels if level in _RANK]
    if not valid:
        return 'N'
    return max(valid, key=lambda level: _RANK[level])


def _num(value):
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _wind_level(speed, gust, info):
    levels = []
    if speed is not None:
        levels.append(get_wind_alert_level(speed, info))
    if gust is not None:
        levels.append(get_gust_alert_level(gust, info))
    if not levels:
        return None
    return _max_level(*levels)


def _weather_level(*codes):
    levels = []
    for code in codes:
        text = str(code or '').strip()
        if text:
            levels.append(get_weather_alert_level(text))
    if not levels:
        return None
    return _max_level(*levels)


def _save(user_code, airport, kind, source_key, warnings):
    from parsers.models import UserAirportAlert

    UserAirportAlert.objects.update_or_create(
        user_code=user_code,
        airport_4code=airport,
        kind=kind,
        defaults={'source_key': str(source_key or ''), 'warnings': warnings},
    )


def _load(user_code, airport, kind, source_key):
    from parsers.models import UserAirportAlert

    row = UserAirportAlert.objects.filter(
        user_code=user_code, airport_4code=airport, kind=kind
    ).first()
    if row and row.source_key == str(source_key or '') and isinstance(row.warnings, dict):
        return row.warnings
    return None


def recompute_metar_warnings(metar, user_code):
    info = threshold_dict(get_threshold_row(user_code, metar.airport_4code))
    with use_settings_user(user_code):
        wind = _wind_level(_num(metar.metar_wind_speed_val), _num(metar.metar_gust_val), info)
        visibility = None
        if metar.metar_visibility_val is not None:
            visibility = get_visibility_alert_level(int(metar.metar_visibility_val), info)
        cloud = None
        if metar.metar_min_cloud_height is not None:
            cloud = get_cloud_alert_level(int(metar.metar_min_cloud_height), info)
        temp = None
        if metar.metar_temp_val is not None:
            temp = get_temperature_alert_level(float(metar.metar_temp_val), info)
        rvr = None
        if metar.rvr_min_val is not None:
            red = info.get('rvr_m_red')
            yellow = info.get('rvr_m_yellow')
            green = info.get('rvr_m_green')
            value = int(metar.rvr_min_val)
            if None not in (red, yellow, green):
                if value <= red:
                    rvr = 'R'
                elif value <= yellow:
                    rvr = 'Y'
                elif value <= green:
                    rvr = 'G'
                else:
                    rvr = 'N'
        parts = str(metar.metar_weather or '').replace('+', ' ').split()
        weather = _weather_level(*parts)
        # 风切变、变化组不看个人阈值，沿用报文上已有结果。
        warnings = {
            'metar_wind_warning': wind or 'N',
            'metar_visibility_warning': visibility or 'N',
            'metar_weather_warning': weather or 'N',
            'metar_cloud_warning': cloud or 'N',
            'metar_temperature_warning': temp or 'N',
            'metar_rvr_warning': rvr or metar.metar_rvr_warning or 'N',
            'metar_ws_warning': metar.metar_ws_warning or 'N',
            'metar_change_trend_warning': metar.metar_change_trend_warning or 'N',
        }
        warnings['metar_warning'] = _max_level(
            warnings['metar_wind_warning'],
            warnings['metar_visibility_warning'],
            warnings['metar_weather_warning'],
            warnings['metar_cloud_warning'],
            warnings['metar_temperature_warning'],
            warnings['metar_rvr_warning'],
            warnings['metar_change_trend_warning'],
        )
        return warnings


def recompute_taf_warnings(taf, user_code):
    info = threshold_dict(get_threshold_row(user_code, taf.airport_4code))

    def section(prefix):
        wind = _wind_level(
            _num(getattr(taf, f'{prefix}wind_speed_mps', None)),
            _num(getattr(taf, f'{prefix}gust_mps', None)),
            info,
        )
        vis_raw = getattr(taf, f'{prefix}visibility_m', None)
        visibility = get_visibility_alert_level(int(vis_raw), info) if vis_raw is not None else None
        cloud_raw = getattr(taf, f'{prefix}cloud_min', None)
        cloud = get_cloud_alert_level(int(cloud_raw), info) if cloud_raw is not None else None
        weather = _weather_level(
            getattr(taf, f'{prefix}weather1', None),
            getattr(taf, f'{prefix}weather2', None),
            getattr(taf, f'{prefix}weather3', None),
            getattr(taf, f'{prefix}weather4', None),
            getattr(taf, f'{prefix}weather5', None),
        )
        overall = _max_level(
            *[level for level in (wind, visibility, weather, cloud) if level is not None]
        )
        return {
            f'{prefix}wind_warning': wind,
            f'{prefix}visibility_warning': visibility,
            f'{prefix}weather_warning': weather,
            f'{prefix}cloud_warning': cloud,
            f'{prefix}warning': overall if any(level is not None for level in (wind, visibility, weather, cloud)) else None,
        }

    with use_settings_user(user_code):
        warnings = section('subject_')
        for index in range(1, 9):
            warnings.update(section(f'change_{index}_'))
        for name in ('subject_max_temp1', 'subject_max_temp2', 'subject_min_temp1', 'subject_min_temp2'):
            raw = getattr(taf, name, None)
            if raw is None or str(raw).strip() == '':
                warnings[f'{name}_warning'] = None
                continue
            try:
                warnings[f'{name}_warning'] = get_temperature_alert_level(float(str(raw)), info)
            except (TypeError, ValueError):
                warnings[f'{name}_warning'] = None
        return warnings


def _stored_metar_warnings(metar):
    return {
        'metar_wind_warning': metar.metar_wind_warning,
        'metar_visibility_warning': metar.metar_visibility_warning,
        'metar_weather_warning': metar.metar_weather_warning,
        'metar_cloud_warning': metar.metar_cloud_warning,
        'metar_temperature_warning': metar.metar_temperature_warning,
        'metar_rvr_warning': metar.metar_rvr_warning,
        'metar_ws_warning': metar.metar_ws_warning,
        'metar_change_trend_warning': metar.metar_change_trend_warning,
        'metar_warning': metar.metar_warning,
    }


def _stored_taf_warnings(taf):
    names = ['subject_warning', 'subject_wind_warning', 'subject_visibility_warning',
             'subject_weather_warning', 'subject_cloud_warning',
             'subject_max_temp1_warning', 'subject_max_temp2_warning',
             'subject_min_temp1_warning', 'subject_min_temp2_warning']
    for index in range(1, 9):
        names.extend([
            f'change_{index}_warning', f'change_{index}_wind_warning',
            f'change_{index}_visibility_warning', f'change_{index}_weather_warning',
            f'change_{index}_cloud_warning',
        ])
    return {name: getattr(taf, name, None) for name in names}


def apply_metar_warnings(payload, metar, user_code):
    if metar is None:
        return payload
    cached = _load(user_code, metar.airport_4code, 'metar', metar.sqc)
    if cached:
        payload.update(cached)
        return payload
    if (metar.user_code or '') == user_code:
        warnings = _stored_metar_warnings(metar)
    else:
        warnings = recompute_metar_warnings(metar, user_code)
    _save(user_code, metar.airport_4code, 'metar', metar.sqc, warnings)
    payload.update({key: value for key, value in warnings.items() if key in payload or True})
    return payload


def apply_taf_warnings(payload, taf, user_code):
    if taf is None:
        return payload
    cached = _load(user_code, taf.airport_4code, 'taf', taf.sqc)
    if cached:
        payload.update(cached)
        return payload
    warnings = recompute_taf_warnings(taf, user_code)
    _save(user_code, taf.airport_4code, 'taf', taf.sqc, warnings)
    payload.update(warnings)
    return payload


def remember_parsed_metar(metar, user_code):
    if metar is None or not user_code:
        return
    _save(user_code, metar.airport_4code, 'metar', metar.sqc, _stored_metar_warnings(metar))


def remember_parsed_taf(taf, user_code):
    if taf is None or not user_code:
        return
    _save(user_code, taf.airport_4code, 'taf', taf.sqc, _stored_taf_warnings(taf))
