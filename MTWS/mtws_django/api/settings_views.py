"""
设置管理API视图
提供机场信息、区域选项、数据刷新定时器、弹窗设置的增删改查接口
所有操作记录写入日志
"""

import json
import logging
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from core.models import (
    AirportInfo, AreaOptions, DataRefreshTimer, PopupSettings,
    AirportAlertThresholds, WeatherTypeInfo, WeatherAlertLevels, AirportLocation,
)

logger = logging.getLogger('mtws.settings')

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


# ===================== 机场信息 =====================

@csrf_exempt
@require_http_methods(["GET", "POST"])
def settings_airport_info(request, time_mode='current'):
    user_code = _get_user_code(request, time_mode)

    if request.method == 'GET':
        try:
            airports = list(
                AirportInfo.objects.values(
                    'airport_4code', 'airport_3code', 'airport_name', 'classification',
                    'area', 'taf_init_time', 'import_check_interval', 'taf_max_delay',
                    'area_code', 'forecast_phone', 'observation_phone', 'other_phone'
                ).order_by('classification', 'area', 'airport_4code')
            )
            return JsonResponse({'success': True, 'data': airports})
        except Exception as e:
            logger.error(f"获取机场信息失败: {e}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

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
        if AirportInfo.objects.filter(airport_4code=code).exists():
            return JsonResponse({'success': False, 'error': f'机场代码 {code} 已存在'}, status=400)

        a3 = (data.get('airport_3code') or '').strip().upper() or None
        if a3 and (len(a3) != 3 or not a3.isalpha()):
            return JsonResponse({'success': False, 'error': '机场三字代码必须为恰好3位英文大写字母'}, status=400)

        AirportInfo.objects.create(
            airport_4code=code,
            airport_3code=a3,
            airport_name=data.get('airport_name', ''),
            classification=data.get('classification', ''),
            area=data.get('area', ''),
            taf_init_time=int(data.get('taf_init_time', 0)),
            import_check_interval=int(data.get('import_check_interval', 6)),
            taf_max_delay=int(data.get('taf_max_delay', 30)),
            area_code=data.get('area_code') or None,
            forecast_phone=data.get('forecast_phone') or None,
            observation_phone=data.get('observation_phone') or None,
            other_phone=data.get('other_phone') or None,
        )
        logger.info(f"[设置] 用户 {user_code} 新增机场: {code}")
        return JsonResponse({'success': True, 'message': f'机场 {code} 新增成功'})
    except (json.JSONDecodeError, ValueError) as e:
        return JsonResponse({'success': False, 'error': f'数据格式错误: {e}'}, status=400)
    except Exception as e:
        logger.error(f"新增机场信息失败: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["PUT", "DELETE"])
def settings_airport_info_detail(request, airport_4code, time_mode='current'):
    user_code = _get_user_code(request, time_mode)
    denied = _deny_settings_write(request, 'settings_airport_info')
    if denied:
        return denied

    if airport_4code.upper() == 'DEFAULT':
        return JsonResponse({'success': False, 'error': 'default 行不可修改或删除'}, status=403)

    try:
        airport = AirportInfo.objects.get(airport_4code=airport_4code)
    except AirportInfo.DoesNotExist:
        return JsonResponse({'success': False, 'error': '机场不存在'}, status=404)

    if request.method == 'PUT':
        try:
            data = json.loads(request.body)
            a3 = (data.get('airport_3code') or '').strip().upper() or None
            if a3 and (len(a3) != 3 or not a3.isalpha()):
                return JsonResponse({'success': False, 'error': '机场三字代码必须为恰好3位英文大写字母'}, status=400)

            for field in ['airport_name', 'classification', 'area',
                          'taf_init_time', 'import_check_interval', 'taf_max_delay',
                          'area_code', 'forecast_phone', 'observation_phone', 'other_phone']:
                if field in data:
                    val = data[field]
                    if val == '':
                        val = None
                    setattr(airport, field, val)
            if 'airport_3code' in data:
                airport.airport_3code = a3
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


# ===================== 区域选项 =====================

@csrf_exempt
@require_http_methods(["GET", "POST"])
def settings_area_options(request, time_mode='current'):
    user_code = _get_user_code(request, time_mode)

    if request.method == 'GET':
        try:
            options = list(
                AreaOptions.objects.values('id', 'classification', 'area', 'sequence')
                .order_by('classification', 'sequence')
            )
            return JsonResponse({'success': True, 'data': options})
        except Exception as e:
            logger.error(f"获取区域选项失败: {e}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    # POST: 新增
    denied = _deny_settings_write(request, 'settings_area_options')
    if denied:
        return denied
    try:
        data = json.loads(request.body)
        classification = (data.get('classification') or '').strip()
        area = (data.get('area') or '').strip()
        sequence = data.get('sequence')

        if not classification or not area or sequence is None:
            return JsonResponse({'success': False, 'error': '分类、区域名称、排序均为必填项'}, status=400)

        sequence = int(sequence)
        if AreaOptions.objects.filter(classification=classification, sequence=sequence).exists():
            return JsonResponse({
                'success': False,
                'error': '区域内排序数字为唯一值，请确保同一类别下的顺序数值唯一，不得有重复'
            }, status=400)

        option = AreaOptions.objects.create(classification=classification, area=area, sequence=sequence)
        logger.info(f"[设置] 用户 {user_code} 新增区域选项: {classification}-{area}(seq={sequence})")
        return JsonResponse({'success': True, 'message': '新增成功', 'id': option.id})
    except (json.JSONDecodeError, ValueError) as e:
        return JsonResponse({'success': False, 'error': f'数据格式错误: {e}'}, status=400)
    except Exception as e:
        logger.error(f"新增区域选项失败: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["PUT", "DELETE"])
def settings_area_options_detail(request, option_id, time_mode='current'):
    user_code = _get_user_code(request, time_mode)
    denied = _deny_settings_write(request, 'settings_area_options')
    if denied:
        return denied

    try:
        option = AreaOptions.objects.get(id=option_id)
    except AreaOptions.DoesNotExist:
        return JsonResponse({'success': False, 'error': '区域选项不存在'}, status=404)

    if request.method == 'PUT':
        try:
            data = json.loads(request.body)
            classification = (data.get('classification') or option.classification).strip()
            area = (data.get('area') or option.area).strip()
            sequence = int(data.get('sequence', option.sequence))

            if AreaOptions.objects.filter(
                classification=classification, sequence=sequence
            ).exclude(id=option_id).exists():
                return JsonResponse({
                    'success': False,
                    'error': '区域内排序数字为唯一值，请确保同一类别下的顺序数值唯一，不得有重复'
                }, status=400)

            option.classification = classification
            option.area = area
            option.sequence = sequence
            option.save()
            logger.info(f"[设置] 用户 {user_code} 修改区域选项: id={option_id}")
            return JsonResponse({'success': True, 'message': '修改成功'})
        except (json.JSONDecodeError, ValueError) as e:
            return JsonResponse({'success': False, 'error': f'数据格式错误: {e}'}, status=400)
        except Exception as e:
            logger.error(f"修改区域选项失败: {e}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    # DELETE
    try:
        label = f"{option.classification}-{option.area}"
        option.delete()
        logger.info(f"[设置] 用户 {user_code} 删除区域选项: id={option_id} ({label})")
        return JsonResponse({'success': True, 'message': '删除成功'})
    except Exception as e:
        logger.error(f"删除区域选项失败: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ===================== 数据刷新定时器 =====================

@require_http_methods(["GET"])
def settings_data_refresh_timer(request, time_mode='current'):
    try:
        timers = []
        for t in DataRefreshTimer.objects.all().order_by('id'):
            timers.append({
                'id': t.id,
                'data': t.data,
                'data_name': DATA_NAMES.get(t.data, t.data),
                'init_time': t.init_time,
                'interval': t.interval,
            })
        return JsonResponse({'success': True, 'data': timers})
    except Exception as e:
        logger.error(f"获取定时器配置失败: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["PUT"])
def settings_data_refresh_timer_detail(request, timer_id, time_mode='current'):
    user_code = _get_user_code(request, time_mode)
    denied = _deny_settings_write(request, 'settings_data_refresh')
    if denied:
        return denied

    try:
        timer = DataRefreshTimer.objects.get(id=timer_id)
    except DataRefreshTimer.DoesNotExist:
        return JsonResponse({'success': False, 'error': '定时器不存在'}, status=404)

    try:
        data = json.loads(request.body)

        if 'init_time' in data:
            val = float(data['init_time'])
            if val < 0 or val > 50:
                return JsonResponse({'success': False, 'error': 'init_time 范围为 0–50'}, status=400)
            if round(val * 2) != val * 2:
                return JsonResponse({'success': False, 'error': 'init_time 必须为 0.5 的倍数'}, status=400)
            timer.init_time = val

        if 'interval' in data:
            val = float(data['interval'])
            if val < 0.5 or val > 30:
                return JsonResponse({'success': False, 'error': 'interval 范围为 0.5–30'}, status=400)
            if round(val * 2) != val * 2:
                return JsonResponse({'success': False, 'error': 'interval 必须为 0.5 的倍数'}, status=400)
            timer.interval = val

        timer.save()
        logger.info(
            f"[设置] 用户 {user_code} 修改定时器: id={timer_id} data={timer.data} "
            f"init_time={timer.init_time} interval={timer.interval}"
        )
        return JsonResponse({'success': True, 'message': '修改成功'})
    except (json.JSONDecodeError, ValueError) as e:
        return JsonResponse({'success': False, 'error': f'数据格式错误: {e}'}, status=400)
    except Exception as e:
        logger.error(f"修改定时器配置失败: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ===================== 弹窗设置 =====================

@csrf_exempt
@require_http_methods(["GET", "PUT"])
def settings_popup(request, time_mode='current'):
    user_code = _get_user_code(request, time_mode)

    if request.method == 'GET':
        try:
            ps = PopupSettings.objects.filter(user_code=user_code).first()
            if not ps:
                ps = PopupSettings.objects.filter(user_code='default').first()

            if not ps:
                return JsonResponse({'success': False, 'error': '未找到弹窗设置'}, status=404)

            return JsonResponse({
                'success': True,
                'data': {
                    'operation_metar_popup_leeway': ps.operation_metar_popup_leeway if ps.operation_metar_popup_leeway is not None else 0,
                    'operation_metar_popup_level': ps.operation_metar_popup_level or 'Y',
                    'parking_metar_popup_level': ps.parking_metar_popup_level or 'Y',
                    'trace_time': int(ps.trace_time) if ps.trace_time is not None else 6,
                }
            })
        except Exception as e:
            logger.error(f"获取弹窗设置失败: {e}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    # PUT: 修改
    denied = _deny_settings_write(request, 'settings_popup')
    if denied:
        return denied
    if user_code in ('default', 'test'):
        return JsonResponse({'success': False, 'error': 'default/test 账号设置不可修改'}, status=403)

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
            default_ps = PopupSettings.objects.filter(user_code='default').first()
            create_data = {'user_code': user_code}
            if default_ps:
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


@csrf_exempt
@require_http_methods(["GET", "POST"])
def settings_alert_thresholds(request, time_mode='current'):
    user_code = _get_user_code(request, time_mode)

    if request.method == 'GET':
        try:
            rows = list(AirportAlertThresholds.objects.values(
                'airport_4code', *_THRESHOLD_FIELDS
            ).order_by('airport_4code'))
            return JsonResponse({'success': True, 'data': rows})
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
        if AirportAlertThresholds.objects.filter(airport_4code=code).exists():
            return JsonResponse({'success': False, 'error': f'{code} 告警阈值记录已存在'}, status=400)

        kwargs = {'airport_4code': code}
        for f in _THRESHOLD_FIELDS:
            if f not in data or data[f] == '':
                return JsonResponse({'success': False, 'error': f'{f} 为必填项'}, status=400)
            kwargs[f] = int(data[f])

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
    user_code = _get_user_code(request, time_mode)
    denied = _deny_settings_write(request, 'settings_alert_thresholds')
    if denied:
        return denied

    if airport_4code.upper() == 'DEFAULT':
        return JsonResponse({'success': False, 'error': 'default 行不可修改或删除'}, status=403)

    try:
        obj = AirportAlertThresholds.objects.get(airport_4code=airport_4code)
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
    user_code = _get_user_code(request, time_mode)

    if request.method == 'GET':
        try:
            rows = list(WeatherAlertLevels.objects.values(
                'id', 'weather', 'alert_level', 'type1', 'type2', 'type3', 'description'
            ).order_by('weather', 'alert_level'))
            # normalise 'None' strings
            for r in rows:
                for f in ('type1', 'type2', 'type3'):
                    if r[f] == 'None':
                        r[f] = None
            type_codes = list(WeatherTypeInfo.objects.values_list('weather_type_code', 'description_cn').order_by('weather_type_code'))
            return JsonResponse({'success': True, 'data': rows, 'type_codes': type_codes})
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
        if WeatherAlertLevels.objects.filter(weather=weather, alert_level=level).exists():
            return JsonResponse({'success': False, 'error': f'{weather}/{level} 组合已存在'}, status=400)

        obj = WeatherAlertLevels.objects.create(
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
    user_code = _get_user_code(request, time_mode)
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
            if WeatherAlertLevels.objects.filter(weather=weather, alert_level=level).exclude(id=alert_id).exists():
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

    try:
        obj.delete()
        logger.info(f"[设置] 用户 {user_code} 删除天气告警等级: id={alert_id}")
        return JsonResponse({'success': True, 'message': '删除成功'})
    except Exception as e:
        logger.error(f"删除天气告警等级失败: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ===================== 机场坐标 =====================

@csrf_exempt
@require_http_methods(["GET", "POST"])
def settings_airport_location(request, time_mode='current'):
    user_code = _get_user_code(request, time_mode)

    if request.method == 'GET':
        try:
            rows = list(AirportLocation.objects.values(
                'airport_4code', 'latitude', 'longitude', 'airport_name'
            ).order_by('airport_4code'))
            return JsonResponse({'success': True, 'data': rows})
        except Exception as e:
            logger.error(f"获取机场坐标失败: {e}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    denied = _deny_settings_write(request, 'settings_airport_location')
    if denied:
        return denied
    try:
        data = json.loads(request.body)
        code = (data.get('airport_4code') or '').strip().upper()
        if len(code) != 4 or not code.isalpha():
            return JsonResponse({'success': False, 'error': '机场四字代码必须为4位英文大写字母'}, status=400)
        if AirportLocation.objects.filter(airport_4code=code).exists():
            return JsonResponse({'success': False, 'error': f'{code} 坐标记录已存在'}, status=400)

        lat = data.get('latitude')
        lon = data.get('longitude')
        if lat is None or lon is None or lat == '' or lon == '':
            return JsonResponse({'success': False, 'error': '纬度和经度为必填项'}, status=400)

        AirportLocation.objects.create(
            airport_4code=code,
            latitude=float(lat),
            longitude=float(lon),
            airport_name=data.get('airport_name') or None,
        )
        logger.info(f"[设置] 用户 {user_code} 新增机场坐标: {code}")
        return JsonResponse({'success': True, 'message': f'{code} 坐标新增成功'})
    except (json.JSONDecodeError, ValueError) as e:
        return JsonResponse({'success': False, 'error': f'数据格式错误: {e}'}, status=400)
    except Exception as e:
        logger.error(f"新增机场坐标失败: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
def settings_airport_location_detail(request, airport_4code, time_mode='current'):
    user_code = _get_user_code(request, time_mode)

    try:
        obj = AirportLocation.objects.get(airport_4code=airport_4code.upper())
    except AirportLocation.DoesNotExist:
        return JsonResponse({'success': False, 'error': f'未找到 {airport_4code.upper()} 的坐标记录'}, status=404)

    if request.method == 'GET':
        return JsonResponse({'success': True, 'data': {
            'airport_4code': obj.airport_4code,
            'latitude': float(obj.latitude),
            'longitude': float(obj.longitude),
            'airport_name': obj.airport_name,
        }})

    denied = _deny_settings_write(request, 'settings_airport_location')
    if denied:
        return denied

    if request.method == 'PUT':
        try:
            data = json.loads(request.body)
            if 'latitude' in data:
                if data['latitude'] == '':
                    return JsonResponse({'success': False, 'error': '纬度为必填项'}, status=400)
                obj.latitude = float(data['latitude'])
            if 'longitude' in data:
                if data['longitude'] == '':
                    return JsonResponse({'success': False, 'error': '经度为必填项'}, status=400)
                obj.longitude = float(data['longitude'])
            if 'airport_name' in data:
                obj.airport_name = data['airport_name'] or None
            obj.save()
            logger.info(f"[设置] 用户 {user_code} 修改机场坐标: {airport_4code}")
            return JsonResponse({'success': True, 'message': '修改成功'})
        except (json.JSONDecodeError, ValueError) as e:
            return JsonResponse({'success': False, 'error': f'数据格式错误: {e}'}, status=400)
        except Exception as e:
            logger.error(f"修改机场坐标失败: {e}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    try:
        obj.delete()
        logger.info(f"[设置] 用户 {user_code} 删除机场坐标: {airport_4code}")
        return JsonResponse({'success': True, 'message': f'{airport_4code} 坐标已删除'})
    except Exception as e:
        logger.error(f"删除机场坐标失败: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
