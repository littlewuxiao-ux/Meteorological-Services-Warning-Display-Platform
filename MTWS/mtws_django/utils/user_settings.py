"""按登录用户读取配置。没有个人行时用 default；test 单独一套，不回退。"""

import contextvars

TEMPLATE = 'default'
TEST = 'test'
_SKIP = {'', '--', '-', 'system', 'scheduler'}

_settings_user = contextvars.ContextVar('mtws_settings_user', default=None)

TIMER_KEYS = ('metar', 'taf', 'flight', 'aircraft_parking')
TIMER_NAMES = {
    'metar': '实况',
    'taf': '预报',
    'flight': '航班',
    'aircraft_parking': '飞机停场信息',
}


class _SettingsUser:
    def __init__(self, user_code):
        self.user_code = user_code
        self.token = None

    def __enter__(self):
        self.token = _settings_user.set(self.user_code)
        return self.user_code

    def __exit__(self, exc_type, exc, tb):
        _settings_user.reset(self.token)
        return False


def use_settings_user(user_code):
    return _SettingsUser(user_code)


def normalize_settings_user(code, time_mode='current'):
    if time_mode == 'test':
        return TEST
    text = str(code or '').strip()
    if text in _SKIP or text == TEST:
        return active_job_user()
    return text


def current_settings_user():
    bound = _settings_user.get()
    if bound:
        return bound
    return active_job_user()


def bound_or(explicit, time_mode='current'):
    """有请求或任务绑定时用绑定值，否则用解析器自己的用户。"""
    bound = _settings_user.get()
    if bound:
        return bound
    return normalize_settings_user(explicit, time_mode)


def active_job_user():
    """当前本机登录用户。没有人登录时用 default。"""
    try:
        from parsers.scheduler import get_scheduler_user_code
        code = str(get_scheduler_user_code() or '').strip()
    except Exception:
        code = ''
    if code in _SKIP or code == TEST:
        return TEMPLATE
    return code


def request_settings_user(request, time_mode='current'):
    """这次页面请求该用谁的配置。非本机固定用 default。"""
    if time_mode == 'test':
        return TEST
    if request is not None:
        from utils.access_control import is_local_request
        if not is_local_request(request):
            return TEMPLATE
        code = str(request.headers.get('X-User-Code') or '').strip()
        if code and code not in _SKIP and code != TEST:
            return code
    return active_job_user()


def editing_template(request):
    if request is None:
        return False
    scope = str(request.headers.get('X-Settings-Scope') or request.GET.get('settings_scope') or '').strip()
    if scope != TEMPLATE:
        return False
    from utils.access_control import is_admin_unlocked, is_local_request
    return is_local_request(request) and is_admin_unlocked(request, touch=True)


def settings_subject(request, time_mode='current'):
    """返回 (要读写的用户, 是否正在改模板)。"""
    if time_mode == 'test':
        return TEST, False
    if editing_template(request):
        return TEMPLATE, True
    return request_settings_user(request, time_mode), False


def can_edit_template(request):
    if request is None:
        return False
    from utils.access_control import is_admin_unlocked, is_local_request
    return is_local_request(request) and is_admin_unlocked(request, touch=False)


def allow_restore(request, time_mode='current'):
    user, editing = settings_subject(request, time_mode)
    return (not editing) and user not in (TEMPLATE, TEST)


def scope_meta(request, time_mode='current'):
    return {
        'can_edit_default': can_edit_template(request),
        'editing_default': editing_template(request) and time_mode != 'test',
        'allow_restore': allow_restore(request, time_mode),
    }


def _fallback(user_code):
    return user_code not in (TEMPLATE, TEST)


def get_threshold_row(user_code, airport_4code):
    from core.models import AirportAlertThresholds

    code = str(airport_4code or '').strip().upper()
    if not code:
        code = 'default'
    own = AirportAlertThresholds.objects.filter(user_code=user_code, airport_4code=code).first()
    if own:
        return own
    if code != 'default':
        generic = AirportAlertThresholds.objects.filter(
            user_code=user_code, airport_4code='default'
        ).first()
        if generic:
            return generic
    if not _fallback(user_code):
        return None
    templ_specific = AirportAlertThresholds.objects.filter(
        user_code=TEMPLATE, airport_4code=code
    ).first()
    if templ_specific:
        return templ_specific
    return AirportAlertThresholds.objects.filter(
        user_code=TEMPLATE, airport_4code='default'
    ).first()


def threshold_dict(row):
    if row is None:
        return {}
    fields = (
        'visibility_m_red', 'visibility_m_yellow', 'visibility_m_green',
        'cloud_min_red', 'cloud_min_yellow', 'cloud_min_green', 'min_cloud_amt',
        'average_wind_speed_mps_red', 'average_wind_speed_mps_yellow', 'average_wind_speed_mps_green',
        'gust_mps_red', 'gust_mps_yellow', 'gust_mps_green',
        'temperature_cold_red', 'temperature_cold_yellow', 'temperature_cold_green',
        'temperature_hot_red', 'temperature_hot_yellow', 'temperature_hot_green',
        'rvr_m_red', 'rvr_m_yellow', 'rvr_m_green',
    )
    return {name: getattr(row, name) for name in fields}


def weather_row(user_code, weather_code):
    from core.models import WeatherAlertLevels

    weather = str(weather_code or '').strip().upper()
    if not weather:
        return None
    own = WeatherAlertLevels.objects.filter(user_code=user_code, weather=weather).first()
    if own:
        return own
    if not _fallback(user_code):
        return None
    return WeatherAlertLevels.objects.filter(user_code=TEMPLATE, weather=weather).first()


def weather_rows_for(user_code):
    """该用户改过的天气优先，其余用模板。"""
    from core.models import WeatherAlertLevels

    own = list(WeatherAlertLevels.objects.filter(user_code=user_code))
    if not _fallback(user_code):
        return own
    seen = {(row.weather, row.alert_level) for row in own}
    merged = list(own)
    for row in WeatherAlertLevels.objects.filter(user_code=TEMPLATE):
        if (row.weather, row.alert_level) not in seen:
            merged.append(row)
    return merged


def known_weather_codes(user_code=None):
    user = user_code or current_settings_user()
    return {str(row.weather).strip().upper() for row in weather_rows_for(user) if row.weather}


def _json_row(model, user_code):
    row = model.objects.filter(user_code=user_code).first()
    if row:
        return row
    if not _fallback(user_code):
        return None
    return model.objects.filter(user_code=TEMPLATE).first()


def carrier_codes(user_code=None):
    from core.models import Carrier
    from utils.flight_selection import carrier_code_or_blank, sort_carrier_codes

    user = user_code or current_settings_user()
    row = _json_row(Carrier, user)
    raw = row.codes if row and isinstance(row.codes, list) else ['O3']
    return sort_carrier_codes(carrier_code_or_blank(code) for code in raw)


def timer_config(user_code=None):
    from core.models import DataRefreshTimer

    user = user_code or active_job_user()
    row = _json_row(DataRefreshTimer, user)
    data = row.config if row and isinstance(row.config, dict) else {}
    return data


def active_timer_config():
    """入库和页面刷新共用当前这一份间隔。"""
    return timer_config(active_job_user())


def json_config_row(model, user_code=None):
    user = user_code or current_settings_user()
    return _json_row(model, user)


def save_json_config(model, user_code, config):
    row = model.objects.filter(user_code=user_code).first()
    if row:
        row.config = config
        row.save(update_fields=['config', 'updated_at'])
        return row
    return model.objects.create(user_code=user_code, config=config)


def restore_group(user_code, group):
    from core.models import (
        AirportAlertThresholds, Carrier, DataRefreshTimer, PopupSettings,
        RadarAlertConfig, TrendAlertConfig, WeatherAlertLevels,
    )

    if user_code in (TEMPLATE, TEST):
        raise ValueError('这一组不能恢复默认')
    if group == 'airport_alert_thresholds':
        AirportAlertThresholds.objects.filter(
            user_code=user_code, airport_4code='default'
        ).delete()
        return
    if group == 'weather_alert_levels':
        WeatherAlertLevels.objects.filter(user_code=user_code).delete()
        return
    if group == 'carrier':
        Carrier.objects.filter(user_code=user_code).delete()
        return
    if group == 'data_refresh_timer':
        DataRefreshTimer.objects.filter(user_code=user_code).delete()
        return
    if group == 'radar_alert_config':
        RadarAlertConfig.objects.filter(user_code=user_code).delete()
        return
    if group == 'trend_alert_config':
        TrendAlertConfig.objects.filter(user_code=user_code).delete()
        return
    if group == 'popup':
        PopupSettings.objects.filter(user_code=user_code).delete()
        return
    raise ValueError('未知设置组')
