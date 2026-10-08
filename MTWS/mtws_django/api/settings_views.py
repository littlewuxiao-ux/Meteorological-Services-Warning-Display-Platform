"""
设置管理API视图
提供机场信息、区域选项、数据刷新定时器、弹窗设置的增删改查接口
所有操作记录写入日志
"""

import json
import logging
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from core.models import (
    AirportInfo, AirportPrefixArea, AirportTafImportConfig, DataRefreshTimer, PopupSettings,
    AirportAlertThresholds, WeatherTypeInfo, WeatherAlertLevels,
)

logger = logging.getLogger('mtws.settings')

from utils.user_settings import (
    TEMPLATE, TIMER_KEYS, TIMER_NAMES, allow_restore, get_threshold_row,
    restore_group, scope_meta, settings_subject, timer_config,
)

DATA_NAMES = {
    'metar': '实况',
    'taf': '预报',
    'flight': '航班',
    'aircraft_parking': '飞机停场信息',
}


def _get_user_code(request, time_mode):
    if time_mode == 'test':
        return 'test'
    return request.headers.get('X-User-Code', 'default')


def _refresh_marks_alerts(airport_codes, time_mode='current'):
    """阈值变更后重算 marks 航班告警及机场三色。"""
    try:
        from utils.marks_alert_calculator import MarksAlertCalculator
        codes = [c for c in (airport_codes or []) if c]
        if not codes:
            return
        MarksAlertCalculator(time_mode).apply(full_airports=codes)
    except Exception as e:
        logger.error(f"阈值变更后更新 marks 告警失败: {e}", exc_info=True)


def _deny_settings_write(request, module_code: str):
    """设置写接口统一鉴权：需对应模块写入权，且仅本机可改库。"""
    from utils.access_control import resolve_access_identity, has_perm, is_local_request
    identity = resolve_access_identity(request)
    if not has_perm(identity, module_code, 'write'):
        return JsonResponse({'success': False, 'error': '无该设置项写入权限'}, status=403)
    if not is_local_request(request):
        return JsonResponse({'success': False, 'error': '设置项仅允许本机用户修改'}, status=403)
    return None


def _blank_to_none(value):
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _optional_float(value):
    if value is None or value == '':
        return None
    return float(value)


def _airport_info_fields(data, airport_3code):
    fields = {
        'airport_3code': airport_3code,
        'airport_name': _blank_to_none(data.get('airport_name')),
        'classification': _blank_to_none(data.get('classification')),
        'area': _blank_to_none(data.get('area')),
        'area_code': _blank_to_none(data.get('area_code')),
        'forecast_phone': _blank_to_none(data.get('forecast_phone')),
        'observation_phone': _blank_to_none(data.get('observation_phone')),
        'other_phone': _blank_to_none(data.get('other_phone')),
    }
    if 'latitude' in data:
        fields['latitude'] = _optional_float(data.get('latitude'))
    if 'longitude' in data:
        fields['longitude'] = _optional_float(data.get('longitude'))
    return fields


def _airport_info_payload(airport):
    return {
        'airport_4code': airport.airport_4code,
        'airport_3code': airport.airport_3code,
        'airport_name': airport.airport_name,
        'classification': airport.classification,
        'area': airport.area,
        'latitude': None if airport.latitude is None else float(airport.latitude),
        'longitude': None if airport.longitude is None else float(airport.longitude),
        'area_code': airport.area_code,
        'forecast_phone': airport.forecast_phone,
        'observation_phone': airport.observation_phone,
        'other_phone': airport.other_phone,
    }


# ===================== 机场信息 =====================

@csrf_exempt
@require_http_methods(["GET", "POST"])
def settings_airport_info(request, time_mode='current'):
    user_code = _get_user_code(request, time_mode)

    if request.method == 'GET':
        # 合并后机场很多，列表不整表返回。设置页按四字代码查单条。
        return JsonResponse({'success': True, 'data': []})

    # POST: 新增
    denied = _deny_settings_write(request, 'settings_airport_info')
    if denied:
        return denied
    try:
        data = json.loads(request.body)
        code = (data.get('airport_4code') or '').strip().upper()
        if len(code) != 4 or not code.isalpha():
            return JsonResponse({'success': False, 'error': '机场四字代码必须为恰好4位英文大写字母'}, status=400)
        if code == 'DEFAULT':
            return JsonResponse({'success': False, 'error': '不可使用保留代码 DEFAULT'}, status=400)
        a3 = (data.get('airport_3code') or '').strip().upper() or None
        if a3 and (len(a3) != 3 or not a3.isalpha()):
            return JsonResponse({'success': False, 'error': '机场三字代码必须为恰好3位英文大写字母'}, status=400)

        fields = _airport_info_fields(data, a3)
        existing = AirportInfo.objects.filter(airport_4code=code).first()
        if existing and not existing.catalog_only:
            return JsonResponse({'success': False, 'error': f'机场代码 {code} 已存在'}, status=400)
        if existing:
            for key, value in fields.items():
                setattr(existing, key, value)
            existing.catalog_only = False
            existing.save()
        else:
            AirportInfo.objects.create(airport_4code=code, catalog_only=False, **fields)
        logger.info(f"[设置] 用户 {user_code} 新增机场: {code}")
        return JsonResponse({'success': True, 'message': f'机场 {code} 新增成功'})
    except (json.JSONDecodeError, ValueError) as e:
        return JsonResponse({'success': False, 'error': f'数据格式错误: {e}'}, status=400)
    except Exception as e:
        logger.error(f"新增机场信息失败: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
def settings_airport_info_detail(request, airport_4code, time_mode='current'):
    user_code = _get_user_code(request, time_mode)
    code = (airport_4code or '').strip().upper()

    try:
        airport = AirportInfo.objects.get(airport_4code=code)
    except AirportInfo.DoesNotExist:
        return JsonResponse({'success': False, 'error': f'未找到 {code} 的机场信息'}, status=404)

    if request.method == 'GET':
        return JsonResponse({'success': True, 'data': _airport_info_payload(airport)})

    denied = _deny_settings_write(request, 'settings_airport_info')
    if denied:
        return denied

    if request.method == 'PUT':
        try:
            data = json.loads(request.body)
            a3 = (data.get('airport_3code') or '').strip().upper() or None
            if a3 and (len(a3) != 3 or not a3.isalpha()):
                return JsonResponse({'success': False, 'error': '机场三字代码必须为恰好3位英文大写字母'}, status=400)

            fields = _airport_info_fields(data, a3)
            for key, value in fields.items():
                setattr(airport, key, value)
            airport.catalog_only = False
            airport.save()
            logger.info(f"[设置] 用户 {user_code} 修改机场: {airport_4code}")
            return JsonResponse({'success': True, 'message': '修改成功'})
        except (json.JSONDecodeError, ValueError) as e:
            return JsonResponse({'success': False, 'error': f'数据格式错误: {e}'}, status=400)
        except Exception as e:
            logger.error(f"修改机场信息失败: {e}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    # DELETE
    try:
        airport.delete()
        logger.info(f"[设置] 用户 {user_code} 删除机场: {airport_4code}")
        return JsonResponse({'success': True, 'message': f'机场 {airport_4code} 已删除'})
    except Exception as e:
        logger.error(f"删除机场信息失败: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ===================== 数据刷新定时器 =====================

def _timer_rows_for(user_code):
    config = timer_config(user_code)
    rows = []
    for key in TIMER_KEYS:
        item = config.get(key) if isinstance(config, dict) else None
        item = item if isinstance(item, dict) else {}
        rows.append({
            'id': key,
            'data': key,
            'data_name': TIMER_NAMES.get(key, DATA_NAMES.get(key, key)),
            'init_time': item.get('init_time'),
            'interval': item.get('interval'),
        })
    return rows


def _validate_timer_value(name, value, low, high):
    val = float(value)
    if val < low or val > high or round(val * 2) != val * 2:
        raise ValueError(f'{name} 超出范围或不是 0.5 的倍数')
    return val


@require_http_methods(["GET"])
def settings_data_refresh_timer(request, time_mode='current'):
    try:
        user, _editing = settings_subject(request, time_mode)
        return JsonResponse({
            'success': True,
            'data': _timer_rows_for(user),
            **scope_meta(request, time_mode),
        })
    except Exception as e:
        logger.error(f"获取定时器配置失败: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["PUT"])
def settings_data_refresh_timer_detail(request, timer_id, time_mode='current'):
    user_code, _editing = settings_subject(request, time_mode)
    denied = _deny_settings_write(request, 'settings_data_refresh')
    if denied:
        return denied
    if timer_id not in TIMER_KEYS:
        return JsonResponse({'success': False, 'error': '定时器不存在'}, status=404)

    try:
        data = json.loads(request.body)
        config = dict(timer_config(user_code) or {})
        current = dict(config.get(timer_id) or {})
        if 'init_time' in data:
            current['init_time'] = _validate_timer_value('init_time', data['init_time'], 0, 50)
        if 'interval' in data:
            current['interval'] = _validate_timer_value('interval', data['interval'], 0.5, 30)
        config[timer_id] = current
        from utils.user_settings import save_json_config
        save_json_config(DataRefreshTimer, user_code, config)
        from parsers.scheduler import reload_scheduler_jobs
        reload_scheduler_jobs()
        logger.info(f"[设置] 用户 {user_code} 修改定时器: {timer_id} {current}")
        return JsonResponse({'success': True, 'message': '修改成功'})
    except (json.JSONDecodeError, ValueError) as e:
        return JsonResponse({'success': False, 'error': f'数据格式错误: {e}'}, status=400)
    except Exception as e:
        logger.error(f"修改定时器配置失败: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def settings_restore(request, time_mode='current'):
    if not allow_restore(request, time_mode):
        return JsonResponse({'success': False, 'error': '当前不能恢复默认'}, status=403)
    user_code, _editing = settings_subject(request, time_mode)
    try:
        data = json.loads(request.body or '{}')
        group = data.get('group')
        restore_group(user_code, group)
        if group in ('data_refresh_timer', 'radar_alert_config'):
            from parsers.scheduler import reload_scheduler_jobs
            reload_scheduler_jobs()
        if group == 'carrier':
            from utils.flight_selection import recompute_selected_flight_state
            from utils.user_settings import active_job_user
            if user_code == active_job_user():
                recompute_selected_flight_state(time_mode, user_code)
        logger.info(f"[设置] 用户 {user_code} 恢复默认: {group}")
        return JsonResponse({'success': True, 'message': '已恢复默认'})
    except ValueError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    except Exception as exc:
        logger.error(f"恢复默认失败: {exc}")
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


# ===================== 弹窗设置 =====================

@csrf_exempt
@require_http_methods(["GET", "PUT"])
def settings_popup(request, time_mode='current'):
    user_code, editing = settings_subject(request, time_mode)

    if request.method == 'GET':
        try:
            ps = PopupSettings.objects.filter(user_code=user_code).first()
            if not ps and user_code != TEMPLATE:
                ps = PopupSettings.objects.filter(user_code=TEMPLATE).first()

            if not ps:
                return JsonResponse({'success': False, 'error': '未找到弹窗设置'}, status=404)

            return JsonResponse({
                'success': True,
                'data': {
                    'operation_metar_popup_leeway': ps.operation_metar_popup_leeway if ps and ps.operation_metar_popup_leeway is not None else 0,
                    'operation_metar_popup_level': (ps.operation_metar_popup_level if ps else None) or 'Y',
                    'parking_metar_popup_level': (ps.parking_metar_popup_level if ps else None) or 'Y',
                    'trace_time': int(ps.trace_time) if ps and ps.trace_time is not None else 6,
                },
                **scope_meta(request, time_mode),
            })
        except Exception as e:
            logger.error(f"获取弹窗设置失败: {e}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    # PUT: 修改
    denied = _deny_settings_write(request, 'settings_popup')
    if denied:
        return denied
    if user_code == TEMPLATE and not editing:
        return JsonResponse({'success': False, 'error': '不能修改默认模板'}, status=403)

    try:
        data = json.loads(request.body)

        valid_levels = ('R', 'Y', 'G')
        for level_field in ('operation_metar_popup_level', 'parking_metar_popup_level'):
            if level_field in data and data[level_field] not in valid_levels:
                return JsonResponse({'success': False, 'error': '告警等级只能为 R/Y/G'}, status=400)

        if 'trace_time' in data:
            try:
                tt = int(data['trace_time'])
            except (TypeError, ValueError):
                return JsonResponse({'success': False, 'error': '追溯时间需为0–9的整数'}, status=400)
            if tt < 0 or tt > 9:
                return JsonResponse({'success': False, 'error': '追溯时间需为0–9的整数'}, status=400)
            data['trace_time'] = tt

        update_dict = {}
        for field in ['operation_metar_popup_leeway', 'operation_metar_popup_level',
                      'parking_metar_popup_level', 'trace_time']:
            if field in data:
                update_dict[field] = data[field]

        updated = PopupSettings.objects.filter(user_code=user_code).update(**update_dict)
        if updated == 0:
            default_ps = PopupSettings.objects.filter(user_code=TEMPLATE).first()
            create_data = {'user_code': user_code}
            if default_ps and user_code != TEMPLATE:
                create_data.update({
                    'operation_metar_popup_leeway': default_ps.operation_metar_popup_leeway,
                    'operation_metar_popup_level': default_ps.operation_metar_popup_level,
                    'parking_metar_popup_level': default_ps.parking_metar_popup_level,
                    'trace_time': default_ps.trace_time if default_ps.trace_time is not None else 6,
                })
            create_data.update(update_dict)
            PopupSettings.objects.create(**create_data)

        logger.info(f"[设置] 用户 {user_code} 修改弹窗设置: {update_dict}")
        return JsonResponse({'success': True, 'message': '保存成功'})
    except (json.JSONDecodeError, ValueError) as e:
        return JsonResponse({'success': False, 'error': f'数据格式错误: {e}'}, status=400)
    except Exception as e:
        logger.error(f"修改弹窗设置失败: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ===================== 机场告警阈值 =====================

_THRESHOLD_FIELDS = [
    'visibility_m_red', 'visibility_m_yellow', 'visibility_m_green',
    'cloud_min_red', 'cloud_min_yellow', 'cloud_min_green',
    'average_wind_speed_mps_red', 'average_wind_speed_mps_yellow', 'average_wind_speed_mps_green',
    'gust_mps_red', 'gust_mps_yellow', 'gust_mps_green',
    'temperature_cold_red', 'temperature_cold_yellow', 'temperature_cold_green',
    'temperature_hot_red', 'temperature_hot_yellow', 'temperature_hot_green',
    'rvr_m_red', 'rvr_m_yellow', 'rvr_m_green',
]
_CLOUD_AMTS = ('FEW', 'SCT', 'BKN', 'OVC')


def _parse_min_cloud_amt(value):
    amount = str(value or '').strip().upper()
    if amount not in _CLOUD_AMTS:
        raise ValueError('min_cloud_amt 只能是 FEW、SCT、BKN、OVC')
    return amount


def _threshold_values(row, personalized, label=None):
    data = {
        'airport_4code': row.airport_4code,
        'min_cloud_amt': row.min_cloud_amt,
        'personalized': personalized,
    }
    if label:
        data['label'] = label
    for field in _THRESHOLD_FIELDS:
        data[field] = getattr(row, field)
    return data


@csrf_exempt
@require_http_methods(["GET", "POST"])
def settings_alert_thresholds(request, time_mode='current'):
    user_code, editing = settings_subject(request, time_mode)

    if request.method == 'GET':
        try:
            if editing:
                owned = list(
                    AirportAlertThresholds.objects.filter(user_code=user_code).order_by('airport_4code')
                )
                generic = [row for row in owned if row.airport_4code == 'default']
                specific = [row for row in owned if row.airport_4code != 'default']
                rows = [
                    _threshold_values(row, True, '通用' if row.airport_4code == 'default' else None)
                    for row in generic + specific
                ]
            else:
                rows = []
                generic = get_threshold_row(user_code, 'default')
                if generic:
                    own_generic = AirportAlertThresholds.objects.filter(
                        user_code=user_code, airport_4code='default'
                    ).exists()
                    item = _threshold_values(generic, own_generic, '通用')
                    item['airport_4code'] = 'default'
                    rows.append(item)
                rows.extend(
                    _threshold_values(row, True)
                    for row in AirportAlertThresholds.objects.filter(user_code=user_code)
                    .exclude(airport_4code='default').order_by('airport_4code')
                )
            return JsonResponse({'success': True, 'data': rows, **scope_meta(request, time_mode)})
        except Exception as e:
            logger.error(f"获取告警阈值失败: {e}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    denied = _deny_settings_write(request, 'settings_alert_thresholds')
    if denied:
        return denied
    try:
        data = json.loads(request.body)
        code = (data.get('airport_4code') or '').strip().upper()
        if len(code) != 4 or not code.isalpha():
            return JsonResponse({'success': False, 'error': '机场四字代码必须为4位英文大写字母'}, status=400)
        if code == 'DEFAULT':
            return JsonResponse({'success': False, 'error': '不可使用保留代码 DEFAULT'}, status=400)
        if AirportAlertThresholds.objects.filter(user_code=user_code, airport_4code=code).exists():
            return JsonResponse({'success': False, 'error': f'{code} 告警阈值记录已存在'}, status=400)

        kwargs = {'user_code': user_code, 'airport_4code': code}
        for f in _THRESHOLD_FIELDS:
            if f not in data or data[f] == '':
                return JsonResponse({'success': False, 'error': f'{f} 为必填项'}, status=400)
            kwargs[f] = int(data[f])
        if 'min_cloud_amt' not in data or data['min_cloud_amt'] == '':
            return JsonResponse({'success': False, 'error': 'min_cloud_amt 为必填项'}, status=400)
        kwargs['min_cloud_amt'] = _parse_min_cloud_amt(data['min_cloud_amt'])

        AirportAlertThresholds.objects.create(**kwargs)
        logger.info(f"[设置] 用户 {user_code} 新增机场告警阈值: {code}")
        _refresh_marks_alerts([code], time_mode)
        return JsonResponse({'success': True, 'message': f'{code} 告警阈值新增成功'})
    except (json.JSONDecodeError, ValueError) as e:
        return JsonResponse({'success': False, 'error': f'数据格式错误: {e}'}, status=400)
    except Exception as e:
        logger.error(f"新增告警阈值失败: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["PUT", "DELETE"])
def settings_alert_thresholds_detail(request, airport_4code, time_mode='current'):
    user_code, _editing = settings_subject(request, time_mode)
    denied = _deny_settings_write(request, 'settings_alert_thresholds')
    if denied:
        return denied

    code = airport_4code.strip()
    if code.lower() == 'default':
        if request.method == 'DELETE':
            return JsonResponse({'success': False, 'error': '通用行请使用恢复默认'}, status=403)
        obj = AirportAlertThresholds.objects.filter(user_code=user_code, airport_4code='default').first()
        if obj is None:
            source = get_threshold_row(TEMPLATE, 'default')
            obj = AirportAlertThresholds(user_code=user_code, airport_4code='default')
            if source is not None:
                for field in _THRESHOLD_FIELDS:
                    setattr(obj, field, getattr(source, field))
                obj.min_cloud_amt = source.min_cloud_amt
    else:
        try:
            obj = AirportAlertThresholds.objects.get(user_code=user_code, airport_4code=code)
        except AirportAlertThresholds.DoesNotExist:
            return JsonResponse({'success': False, 'error': '记录不存在'}, status=404)

    if request.method == 'PUT':
        try:
            data = json.loads(request.body)
            for f in _THRESHOLD_FIELDS:
                if f in data:
                    if data[f] == '':
                        return JsonResponse({'success': False, 'error': f'{f} 为必填项'}, status=400)
                    setattr(obj, f, int(data[f]))
            if 'min_cloud_amt' in data:
                if data['min_cloud_amt'] == '':
                    return JsonResponse({'success': False, 'error': 'min_cloud_amt 为必填项'}, status=400)
                obj.min_cloud_amt = _parse_min_cloud_amt(data['min_cloud_amt'])
            obj.save()
            logger.info(f"[设置] 用户 {user_code} 修改机场告警阈值: {airport_4code}")
            _refresh_marks_alerts([airport_4code], time_mode)
            return JsonResponse({'success': True, 'message': '修改成功'})
        except (json.JSONDecodeError, ValueError) as e:
            return JsonResponse({'success': False, 'error': f'数据格式错误: {e}'}, status=400)
        except Exception as e:
            logger.error(f"修改告警阈值失败: {e}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    try:
        obj.delete()
        logger.info(f"[设置] 用户 {user_code} 删除机场告警阈值: {airport_4code}")
        _refresh_marks_alerts([airport_4code], time_mode)
        return JsonResponse({'success': True, 'message': f'{airport_4code} 告警阈值已删除'})
    except Exception as e:
        logger.error(f"删除告警阈值失败: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ===================== 天气类型信息 =====================

@csrf_exempt
@require_http_methods(["GET", "POST"])
def settings_weather_type(request, time_mode='current'):
    user_code = _get_user_code(request, time_mode)

    if request.method == 'GET':
        try:
            rows = list(WeatherTypeInfo.objects.values(
                'id', 'weather_type_code', 'description_cn', 'description_en'
            ).order_by('weather_type_code'))
            return JsonResponse({'success': True, 'data': rows})
        except Exception as e:
            logger.error(f"获取天气类型失败: {e}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    denied = _deny_settings_write(request, 'settings_weather_type')
    if denied:
        return denied
    try:
        data = json.loads(request.body)
        code = (data.get('weather_type_code') or '').strip()
        cn = (data.get('description_cn') or '').strip()
        en = (data.get('description_en') or '').strip()
        if not code or len(code) != 1:
            return JsonResponse({'success': False, 'error': '天气类型代码必须为1位字符'}, status=400)
        if not cn:
            return JsonResponse({'success': False, 'error': '中文说明为必填项'}, status=400)
        if not en:
            return JsonResponse({'success': False, 'error': '英文说明为必填项'}, status=400)

        obj = WeatherTypeInfo.objects.create(
            weather_type_code=code,
            description_cn=cn,
            description_en=en,
        )
        logger.info(f"[设置] 用户 {user_code} 新增天气类型: {code}")
        return JsonResponse({'success': True, 'message': '新增成功', 'id': obj.id})
    except (json.JSONDecodeError, ValueError) as e:
        return JsonResponse({'success': False, 'error': f'数据格式错误: {e}'}, status=400)
    except Exception as e:
        logger.error(f"新增天气类型失败: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["PUT", "DELETE"])
def settings_weather_type_detail(request, type_id, time_mode='current'):
    user_code = _get_user_code(request, time_mode)
    denied = _deny_settings_write(request, 'settings_weather_type')
    if denied:
        return denied

    try:
        obj = WeatherTypeInfo.objects.get(id=type_id)
    except WeatherTypeInfo.DoesNotExist:
        return JsonResponse({'success': False, 'error': '天气类型不存在'}, status=404)

    if request.method == 'PUT':
        try:
            data = json.loads(request.body)
            code = (data.get('weather_type_code') or '').strip()
            cn = (data.get('description_cn') or '').strip()
            en = (data.get('description_en') or '').strip()
            if not code or len(code) != 1:
                return JsonResponse({'success': False, 'error': '天气类型代码必须为1位字符'}, status=400)
            if not cn:
                return JsonResponse({'success': False, 'error': '中文说明为必填项'}, status=400)
            if not en:
                return JsonResponse({'success': False, 'error': '英文说明为必填项'}, status=400)
            obj.weather_type_code = code
            obj.description_cn = cn
            obj.description_en = en
            obj.save()
            logger.info(f"[设置] 用户 {user_code} 修改天气类型: id={type_id}")
            return JsonResponse({'success': True, 'message': '修改成功'})
        except (json.JSONDecodeError, ValueError) as e:
            return JsonResponse({'success': False, 'error': f'数据格式错误: {e}'}, status=400)
        except Exception as e:
            logger.error(f"修改天气类型失败: {e}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    try:
        obj.delete()
        logger.info(f"[设置] 用户 {user_code} 删除天气类型: id={type_id}")
        return JsonResponse({'success': True, 'message': '删除成功'})
    except Exception as e:
        logger.error(f"删除天气类型失败: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ===================== 天气现象告警等级 =====================

@csrf_exempt
@require_http_methods(["GET", "POST"])
def settings_weather_alert(request, time_mode='current'):
    user_code, editing = settings_subject(request, time_mode)

    if request.method == 'GET':
        try:
            def _clean(row, personalized):
                data = {
                    'id': row.id,
                    'weather': row.weather,
                    'alert_level': row.alert_level,
                    'type1': None if row.type1 == 'None' else row.type1,
                    'type2': None if row.type2 == 'None' else row.type2,
                    'type3': None if row.type3 == 'None' else row.type3,
                    'description': row.description,
                    'personalized': personalized,
                    'from_template': not personalized,
                }
                return data

            if editing:
                rows = [
                    _clean(row, True)
                    for row in WeatherAlertLevels.objects.filter(user_code=user_code).order_by('weather', 'alert_level')
                ]
            else:
                own = {
                    (row.weather, row.alert_level): row
                    for row in WeatherAlertLevels.objects.filter(user_code=user_code)
                }
                rows = []
                seen = set()
                for row in WeatherAlertLevels.objects.filter(user_code=TEMPLATE).order_by('weather', 'alert_level'):
                    key = (row.weather, row.alert_level)
                    seen.add(key)
                    picked = own.get(key, row)
                    rows.append(_clean(picked, key in own))
                for key, row in own.items():
                    if key not in seen:
                        rows.append(_clean(row, True))
            type_codes = list(WeatherTypeInfo.objects.values_list('weather_type_code', 'description_cn').order_by('weather_type_code'))
            return JsonResponse({
                'success': True, 'data': rows, 'type_codes': type_codes, **scope_meta(request, time_mode),
            })
        except Exception as e:
            logger.error(f"获取天气告警等级失败: {e}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    denied = _deny_settings_write(request, 'settings_weather_alert')
    if denied:
        return denied
    try:
        data = json.loads(request.body)
        weather = (data.get('weather') or '').strip()
        level = (data.get('alert_level') or '').strip().upper()
        type1 = (data.get('type1') or '').strip() or None
        type2 = (data.get('type2') or '').strip() or None
        type3 = (data.get('type3') or '').strip() or None
        description = (data.get('description') or '').strip() or None

        if not weather:
            return JsonResponse({'success': False, 'error': '天气现象代码为必填项'}, status=400)
        if level not in ('R', 'Y', 'G'):
            return JsonResponse({'success': False, 'error': '告警等级只能为 R/Y/G'}, status=400)
        if not type1:
            return JsonResponse({'success': False, 'error': '类型1为必填项'}, status=400)
        if WeatherAlertLevels.objects.filter(user_code=user_code, weather=weather, alert_level=level).exists():
            return JsonResponse({'success': False, 'error': f'{weather}/{level} 组合已存在'}, status=400)

        obj = WeatherAlertLevels.objects.create(
            user_code=user_code,
            weather=weather, alert_level=level,
            type1=type1, type2=type2, type3=type3, description=description,
        )
        logger.info(f"[设置] 用户 {user_code} 新增天气告警等级: {weather}/{level}")
        return JsonResponse({'success': True, 'message': '新增成功', 'id': obj.id})
    except (json.JSONDecodeError, ValueError) as e:
        return JsonResponse({'success': False, 'error': f'数据格式错误: {e}'}, status=400)
    except Exception as e:
        logger.error(f"新增天气告警等级失败: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["PUT", "DELETE"])
def settings_weather_alert_detail(request, alert_id, time_mode='current'):
    user_code, _editing = settings_subject(request, time_mode)
    denied = _deny_settings_write(request, 'settings_weather_alert')
    if denied:
        return denied

    try:
        obj = WeatherAlertLevels.objects.get(id=alert_id)
    except WeatherAlertLevels.DoesNotExist:
        return JsonResponse({'success': False, 'error': '记录不存在'}, status=404)

    if request.method == 'PUT':
        try:
            data = json.loads(request.body)
            weather = (data.get('weather') or '').strip()
            level = (data.get('alert_level') or '').strip().upper()
            type1 = (data.get('type1') or '').strip() or None
            type2 = (data.get('type2') or '').strip() or None
            type3 = (data.get('type3') or '').strip() or None
            description = (data.get('description') or '').strip() or None

            if not weather:
                return JsonResponse({'success': False, 'error': '天气现象代码为必填项'}, status=400)
            if level not in ('R', 'Y', 'G'):
                return JsonResponse({'success': False, 'error': '告警等级只能为 R/Y/G'}, status=400)
            if not type1:
                return JsonResponse({'success': False, 'error': '类型1为必填项'}, status=400)
            if obj.user_code != user_code:
                if WeatherAlertLevels.objects.filter(
                    user_code=user_code, weather=weather, alert_level=level
                ).exists():
                    return JsonResponse({'success': False, 'error': f'{weather}/{level} 组合已存在'}, status=400)
                WeatherAlertLevels.objects.create(
                    user_code=user_code, weather=weather, alert_level=level,
                    type1=type1, type2=type2, type3=type3, description=description,
                )
                logger.info(f"[设置] 用户 {user_code} 自定义天气告警等级: {weather}/{level}")
                return JsonResponse({'success': True, 'message': '修改成功'})
            if WeatherAlertLevels.objects.filter(
                user_code=user_code, weather=weather, alert_level=level
            ).exclude(id=alert_id).exists():
                return JsonResponse({'success': False, 'error': f'{weather}/{level} 组合已存在'}, status=400)

            obj.weather = weather
            obj.alert_level = level
            obj.type1 = type1
            obj.type2 = type2
            obj.type3 = type3
            obj.description = description
            obj.save()
            logger.info(f"[设置] 用户 {user_code} 修改天气告警等级: id={alert_id}")
            return JsonResponse({'success': True, 'message': '修改成功'})
        except (json.JSONDecodeError, ValueError) as e:
            return JsonResponse({'success': False, 'error': f'数据格式错误: {e}'}, status=400)
        except Exception as e:
            logger.error(f"修改天气告警等级失败: {e}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    if obj.user_code != user_code:
        return JsonResponse({'success': False, 'error': '不能删除默认模板中的天气'}, status=403)
    try:
        obj.delete()
        logger.info(f"[设置] 用户 {user_code} 删除天气告警等级: id={alert_id}")
        return JsonResponse({'success': True, 'message': '删除成功'})
    except Exception as e:
        logger.error(f"删除天气告警等级失败: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def _backfill_prefix(rule: AirportPrefixArea):
    """只补分类或区域仍为空的机场，不改已经写过的区域。"""
    from core.airport_directory import match_prefix
    prefix = (rule.prefix or '').upper()
    if not prefix:
        return
    for airport in AirportInfo.objects.filter(airport_4code__startswith=prefix).iterator():
        if (airport.classification or '').strip() and (airport.area or '').strip():
            continue
        matched = match_prefix(airport.airport_4code)
        if matched is None or matched.prefix != prefix:
            continue
        changed = []
        if not (airport.classification or '').strip():
            airport.classification = rule.classification
            changed.append('classification')
        if not (airport.area or '').strip():
            airport.area = rule.area
            changed.append('area')
        if changed:
            airport.save(update_fields=changed)


def _prefix_payload(data):
    prefix = (data.get('prefix') or '').strip().upper()
    classification = (data.get('classification') or '').strip()
    area = (data.get('area') or '').strip()
    remark = data.get('remark') or ''
    if not prefix or len(prefix) > 4 or not prefix.isalpha():
        raise ValueError('前缀须为 1–4 位英文字母')
    if classification not in ('国内', '国际'):
        raise ValueError('性质只能是国内或国际')
    if not area:
        raise ValueError('请填写区域')
    try:
        sequence = int(data.get('sequence'))
    except (TypeError, ValueError):
        raise ValueError('序号须为正整数')
    if sequence < 1:
        raise ValueError('序号须为正整数')
    return prefix, classification, area, remark, sequence


def _sequence_taken(classification, sequence, area, keep_group=None):
    qs = AirportPrefixArea.objects.filter(
        classification=classification, sequence=sequence,
    ).exclude(area=area)
    if keep_group:
        qs = qs.exclude(sequence=keep_group[0], classification=keep_group[1], area=keep_group[2])
    return qs.exists()


def _prefix_sheet_rows(data):
    """整表保存。性质不能改道，只能在各自框架里增删区域。"""
    raw_rows = data.get('rows')
    if not isinstance(raw_rows, list) or not raw_rows:
        raise ValueError('请提交完整的区域配置')
    cleaned = []
    seen_prefix = set()
    seen_seq = {}
    areas_by_kind = {'国内': set(), '国际': set()}
    for raw in raw_rows:
        if not isinstance(raw, dict):
            raise ValueError('区域配置格式不正确')
        prefix, classification, area, remark, sequence = _prefix_payload(raw)
        if prefix in seen_prefix:
            raise ValueError(f'前缀 {prefix} 重复')
        seen_prefix.add(prefix)
        seq_key = (classification, sequence)
        other = seen_seq.get(seq_key)
        if other is not None and other != area:
            raise ValueError(f'{classification}下序号 {sequence} 重复')
        seen_seq[seq_key] = area
        areas_by_kind[classification].add((area, sequence))
        cleaned.append({
            'prefix': prefix,
            'classification': classification,
            'area': area,
            'remark': remark,
            'sequence': sequence,
        })
    area_seq = {}
    for item in cleaned:
        key = (item['classification'], item['area'])
        previous = area_seq.get(key)
        if previous is not None and previous != item['sequence']:
            raise ValueError(f'{item["classification"]}下区域「{item["area"]}」的序号不一致')
        area_seq[key] = item['sequence']
    for kind in ('国内', '国际'):
        if not areas_by_kind[kind]:
            raise ValueError(f'{kind}至少要有一个区域')
    return cleaned


def _replace_prefix_sheet(rows):
    keep = [row['prefix'] for row in rows]
    with transaction.atomic():
        AirportPrefixArea.objects.exclude(prefix__in=keep).delete()
        for row in rows:
            AirportPrefixArea.objects.update_or_create(
                prefix=row['prefix'],
                defaults={
                    'sequence': row['sequence'],
                    'classification': row['classification'],
                    'area': row['area'],
                    'remark': row['remark'],
                },
            )
        for rule in AirportPrefixArea.objects.filter(prefix__in=keep):
            _backfill_prefix(rule)


# ===================== 机场区域 =====================

@csrf_exempt
@require_http_methods(["GET", "POST", "PUT"])
def settings_prefix_area(request, time_mode='current'):
    user_code = _get_user_code(request, time_mode)
    if request.method == 'PUT':
        denied = _deny_settings_write(request, 'settings_prefix_area')
        if denied:
            return denied
        try:
            data = json.loads(request.body or '{}')
            rows = _prefix_sheet_rows(data)
            _replace_prefix_sheet(rows)
            logger.info(f"[设置] 用户 {user_code} 保存机场区域，共 {len(rows)} 条前缀")
            return JsonResponse({'success': True, 'message': '已保存'})
        except (json.JSONDecodeError, ValueError) as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
        except Exception as e:
            logger.error(f"保存机场区域失败: {e}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    if request.method == 'GET':
        rows = list(AirportPrefixArea.objects.values(
            'prefix', 'sequence', 'classification', 'area', 'remark'
        ))
        rows.sort(key=lambda row: (
            0 if row['classification'] == '国内' else 1,
            row['sequence'], row['area'], row['prefix'],
        ))
        return JsonResponse({'success': True, 'data': rows})

    denied = _deny_settings_write(request, 'settings_prefix_area')
    if denied:
        return denied
    try:
        data = json.loads(request.body)
        prefix, classification, area, remark, sequence = _prefix_payload(data)
        if AirportPrefixArea.objects.filter(prefix=prefix).exists():
            return JsonResponse({'success': False, 'error': f'前缀 {prefix} 已存在'}, status=400)
        if _sequence_taken(classification, sequence, area):
            return JsonResponse({'success': False, 'error': '同一性质下序号不能重复'}, status=400)
        rule = AirportPrefixArea.objects.create(
            prefix=prefix, sequence=sequence, classification=classification,
            area=area, remark=remark,
        )
        _backfill_prefix(rule)
        logger.info(f"[设置] 用户 {user_code} 新增前缀区域: {prefix}")
        return JsonResponse({'success': True, 'message': f'前缀 {prefix} 已保存'})
    except (json.JSONDecodeError, ValueError) as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    except Exception as e:
        logger.error(f"新增前缀区域失败: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["PUT", "DELETE"])
def settings_prefix_area_detail(request, prefix, time_mode='current'):
    user_code = _get_user_code(request, time_mode)
    denied = _deny_settings_write(request, 'settings_prefix_area')
    if denied:
        return denied
    try:
        rule = AirportPrefixArea.objects.get(prefix=prefix.upper())
    except AirportPrefixArea.DoesNotExist:
        return JsonResponse({'success': False, 'error': '前缀不存在'}, status=404)

    if request.method == 'DELETE':
        rule.delete()
        logger.info(f"[设置] 用户 {user_code} 删除前缀区域: {prefix}")
        return JsonResponse({'success': True, 'message': '已删除'})

    try:
        data = json.loads(request.body)
        new_prefix, classification, area, remark, sequence = _prefix_payload({
            **data, 'prefix': data.get('prefix') or rule.prefix,
        })
        keep = (rule.sequence, rule.classification, rule.area)
        if _sequence_taken(classification, sequence, area, keep):
            return JsonResponse({'success': False, 'error': '同一性质下序号不能重复'}, status=400)
        if data.get('apply_group'):
            AirportPrefixArea.objects.filter(
                sequence=rule.sequence, classification=rule.classification, area=rule.area,
            ).update(sequence=sequence, classification=classification, area=area)
            for item in AirportPrefixArea.objects.filter(
                sequence=sequence, classification=classification, area=area,
            ):
                _backfill_prefix(item)
            logger.info(f"[设置] 用户 {user_code} 修改区域组: {classification}-{area}")
            return JsonResponse({'success': True, 'message': '区域已更新'})
        if new_prefix != rule.prefix:
            if AirportPrefixArea.objects.filter(prefix=new_prefix).exists():
                return JsonResponse({'success': False, 'error': f'前缀 {new_prefix} 已存在'}, status=400)
            AirportPrefixArea.objects.create(
                prefix=new_prefix, sequence=rule.sequence, classification=rule.classification,
                area=rule.area, remark=remark,
            )
            rule.delete()
            rule = AirportPrefixArea.objects.get(prefix=new_prefix)
        else:
            rule.remark = remark
            rule.save(update_fields=['remark'])
        _backfill_prefix(rule)
        logger.info(f"[设置] 用户 {user_code} 修改前缀区域: {rule.prefix}")
        return JsonResponse({'success': True, 'message': '修改成功'})
    except (json.JSONDecodeError, ValueError) as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    except Exception as e:
        logger.error(f"修改前缀区域失败: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def _taf_payload(data):
    code = (data.get('airport_4code') or '').strip().upper()
    if len(code) != 4 or not code.isalpha():
        raise ValueError('机场四字代码必须为恰好4位英文大写字母')
    hour = int(data.get('taf_init_time'))
    interval = int(data.get('import_check_interval'))
    delay = int(data.get('taf_max_delay'))
    if hour < 0 or hour > 23:
        raise ValueError('首份预报发布时间须为 0–23 的整数')
    if interval not in (3, 6):
        raise ValueError('发布间隔只能是 3 或 6 小时')
    if delay < 0 or delay > 60:
        raise ValueError('接收延迟须为 0–60 的整数')
    return code, hour, interval, delay


# ===================== 预报入库告警 =====================

@csrf_exempt
@require_http_methods(["GET", "POST"])
def settings_taf_import(request, time_mode='current'):
    user_code = _get_user_code(request, time_mode)
    if request.method == 'GET':
        rows = list(AirportTafImportConfig.objects.values(
            'airport_4code', 'taf_init_time', 'import_check_interval', 'taf_max_delay'
        ).order_by('airport_4code'))
        return JsonResponse({'success': True, 'data': rows})

    denied = _deny_settings_write(request, 'settings_taf_import')
    if denied:
        return denied
    try:
        data = json.loads(request.body)
        code, hour, interval, delay = _taf_payload(data)
        if AirportTafImportConfig.objects.filter(airport_4code=code).exists():
            return JsonResponse({'success': False, 'error': f'{code} 的预报入库告警已存在'}, status=400)
        AirportTafImportConfig.objects.create(
            airport_4code=code,
            taf_init_time=hour,
            import_check_interval=interval,
            taf_max_delay=delay,
        )
        AirportInfo.objects.filter(airport_4code=code).update(taf_infer_attempted=True)
        logger.info(f"[设置] 用户 {user_code} 新增预报入库配置: {code}")
        return JsonResponse({'success': True, 'message': f'{code} 预报入库告警已保存'})
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    except Exception as e:
        logger.error(f"新增预报入库配置失败: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
def settings_taf_import_detail(request, airport_4code, time_mode='current'):
    user_code = _get_user_code(request, time_mode)
    code = airport_4code.upper()
    if request.method == 'GET':
        obj = AirportTafImportConfig.objects.filter(airport_4code=code).first()
        if not obj:
            return JsonResponse({'success': False, 'error': '尚未配置'}, status=404)
        return JsonResponse({'success': True, 'data': {
            'airport_4code': obj.airport_4code,
            'taf_init_time': obj.taf_init_time,
            'import_check_interval': obj.import_check_interval,
            'taf_max_delay': obj.taf_max_delay,
        }})

    denied = _deny_settings_write(request, 'settings_taf_import')
    if denied:
        return denied
    if request.method == 'DELETE':
        AirportTafImportConfig.objects.filter(airport_4code=code).delete()
        logger.info(f"[设置] 用户 {user_code} 删除预报入库配置: {code}")
        return JsonResponse({'success': True, 'message': '已删除'})

    try:
        data = json.loads(request.body)
        data['airport_4code'] = code
        _code, hour, interval, delay = _taf_payload(data)
        AirportTafImportConfig.objects.update_or_create(
            airport_4code=code,
            defaults={
                'taf_init_time': hour,
                'import_check_interval': interval,
                'taf_max_delay': delay,
            },
        )
        AirportInfo.objects.filter(airport_4code=code).update(taf_infer_attempted=True)
        logger.info(f"[设置] 用户 {user_code} 修改预报入库配置: {code}")
        return JsonResponse({'success': True, 'message': '修改成功'})
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    except Exception as e:
        logger.error(f"修改预报入库配置失败: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
