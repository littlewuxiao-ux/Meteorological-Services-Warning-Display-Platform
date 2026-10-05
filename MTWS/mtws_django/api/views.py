"""
API视图
提供默认加载数据API和搜索API
严格按照项目规划.md的要求实现
"""

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.db.models import Q
from datetime import datetime, timedelta, timezone
import json
import logging

from core.models import (
    AirportInfo, AirportAlertThresholds, AirportTafImportConfig,
    WeatherAlertLevels, AreaOptions, DataRefreshTimer,
)
from parsers.models import Flight, Metar, Taf, ParseLog
from parsers.taf_parser import calc_taf_expected_issue_ms
from parsers.parsing_manager import ParsingManager
from utils.time_manager import TimeManager
from utils.flight_selection import (
    distinct_flight_carriers,
    apply_carrier_change,
    selected_carrier_codes,
    selected_events,
    sort_carrier_codes,
)
from utils.marks_alert_calculator import computed_alerts_from_flight
from utils.popup_utils import PopupManager, get_seat_identity, get_popup_trace_hours
from data_adapters.adapter_factory import AdapterFactory
from utils.cas_api_log import cas_user_context, log_cas_api_request

logger = logging.getLogger('mtws.api')

def check_token_invalid_response(result, time_mode):
    """
    检查解析结果是否因token失效导致失败，如果是则返回401响应
    
    Args:
        result: 解析器返回的结果
        time_mode: 时间模式
        
    Returns:
        JsonResponse with 401 status if token invalid, None otherwise
    """
    if not result.get('success', False) and time_mode == 'current':
        # 检查错误信息中是否包含API请求失败的标识
        message = result.get('message', '')
        if 'API请求失败' in message or '未获取到' in message:
            logger.warning("数据更新失败，可能是token失效")
            return JsonResponse({
                'success': False,
                'error': '认证失效，请重新登录'
            }, status=401)
    return None


def get_overview_auth_status(time_mode):
    """overview 附带的统一登录态摘要；AuthBroker 不可达时 expired 为 False。"""
    if time_mode != 'current':
        return {'reachable': False, 'logged_in': False, 'expired': False}
    try:
        from utils.auth_broker_client import get_auth_status_from_broker
        return get_auth_status_from_broker()
    except Exception:
        return {'reachable': False, 'logged_in': False, 'expired': False}


def get_cached_area_options():
    """获取区域选项数据"""
    try:
        return {
            'domestic': list(AreaOptions.objects.filter(classification='国内').order_by('sequence').values('area', 'sequence')),
            'international': list(AreaOptions.objects.filter(classification='国际').order_by('sequence').values('area', 'sequence'))
        }
        
    except Exception as e:
        logger.error(f"获取区域选项数据失败: {str(e)}")
        # 返回空的区域选项
        return {
            'domestic': [],
            'international': []
        }


@require_http_methods(["GET"])
def airports_overview(request, time_mode='current'):
    """
    获取机场概览数据API
    根据项目规划.md 4节要求：
    - 航班解析数据中has_flight=True的机场数据
    - 对应的最新3条METAR数据
    - 对应的最新3条有效TAF数据
    - 机场信息和告警阈值表相关字段
    - 航空公司代码
    """
    try:
        # 移除缓存机制，直接从数据库加载最新数据
        
        # 1. 获取有航班的机场
        active_airports = Flight.objects.filter(has_flight=True).values_list('airport_4code', flat=True)
        
        if not active_airports:
            return JsonResponse({
                'success': True,
                'data': {
                    'airports': [],
                    'carriers': sort_carrier_codes(selected_carrier_codes()),
                    'timestamp': datetime.now().isoformat(),
                    'auth_status': get_overview_auth_status(time_mode),
                    'seat_identity': get_seat_identity(request),
                }
            })
        
        # 2. 补齐缺失资料后读取机场信息。资料不全仍保留在列表中。
        from core.airport_directory import (
            airport_config_gaps, display_airport_name, ensure_flight_airports,
        )
        try:
            ensure_flight_airports(
                list(active_airports),
                time_mode=time_mode,
                token=_request_token(request, time_mode),
            )
        except Exception as exc:
            logger.error(f"补齐机场资料失败: {exc}")
        configured_airports = {
            info.airport_4code: info
            for info in AirportInfo.objects.filter(airport_4code__in=active_airports)
        }
        taf_configs = {
            cfg.airport_4code: cfg
            for cfg in AirportTafImportConfig.objects.filter(airport_4code__in=active_airports)
        }
        
        # 3. 构建机场数据
        airports_data = []
        chosen_carriers = selected_carrier_codes()
        for airport_code in active_airports:
            airport = configured_airports.get(airport_code)
            in_directory = airport is not None
            if airport is None:
                airport = AirportInfo(airport_4code=airport_code)
            gaps = airport_config_gaps(airport, taf_configs.get(airport_code))
            # 获取最新的航班数据
            flight_data = Flight.objects.filter(
                airport_4code=airport.airport_4code,
                has_flight=True
            ).order_by('-created_at').first()
            
            if not flight_data:
                continue
                
            # 获取最新1条METAR数据（data_status=N 为当前报文，data_status=C 为系统创建的占位行）
            metar_data = Metar.objects.filter(
                airport_4code=airport.airport_4code,
                data_status__in=['N', 'C'],
            ).order_by('-metar_observation_time')[:1]
            
            # 获取当前有效TAF（data_status='N' 或 'C'），取 created_at 最大的1条
            taf_record = Taf.objects.filter(
                airport_4code=airport.airport_4code,
                data_status__in=['N', 'C'],
            ).order_by('-created_at').first()
            taf_data = [taf_record] if taf_record else []
            
            # 构建机场数据
            airport_data = {
                'airport_4code': airport.airport_4code,
                'airport_name': display_airport_name(airport.airport_name),
                'is_configured': not gaps,
                'in_directory': in_directory,
                'config_gaps': gaps,
                'latitude': None if airport.latitude is None else float(airport.latitude),
                'longitude': None if airport.longitude is None else float(airport.longitude),
                'area': airport.area,
                'area_code': airport.area_code,
                'classification': airport.classification,
                # 添加联系方式信息
                'forecast_phone': airport.forecast_phone,
                'observation_phone': airport.observation_phone,
                'other_phone': airport.other_phone,
                'flight_data': {
                    'has_flight': flight_data.has_flight,
                    'time_slots': flight_data.as_time_slots(),
                    'events': selected_events(flight_data.as_events(), chosen_carriers),
                    'last_updated': flight_data.created_at.isoformat()
                },
                'metar_data': [
                    {
                        'metar_observation_time': metar.metar_observation_time,
                        'metar_type': metar.metar_type,
                        'metar_auto_flag': metar.metar_auto_flag,
                        'metar_wind_direction': metar.metar_wind_direction,
                        'metar_wind_speed_original': metar.metar_wind_speed_original,
                        'metar_wind_speed_val': metar.metar_wind_speed_val,
                        'metar_gust_val': metar.metar_gust_val,
                        'metar_wind_warning': metar.metar_wind_warning,
                        'metar_visibility_original': metar.metar_visibility_original,
                        'metar_visibility_val': metar.metar_visibility_val,
                        'metar_visibility_warning': metar.metar_visibility_warning,
                        'metar_weather': metar.metar_weather,
                        'metar_weather_warning': metar.metar_weather_warning,
                        'metar_weather_pre': metar.metar_weather_pre,
                        'metar_cloud': metar.metar_cloud,
                        'metar_min_cloud_height': metar.metar_min_cloud_height,
                        'metar_cloud_warning': metar.metar_cloud_warning,
                        'metar_temperature': metar.metar_temperature,
                        'metar_temp_val': metar.metar_temp_val,
                        'metar_temperature_warning': metar.metar_temperature_warning,
                        'metar_dew_point': metar.metar_dew_point,
                        'metar_ws_dsc': metar.metar_ws_dsc,
                        'metar_ws_warning': metar.metar_ws_warning,
                        'metar_change_trend': metar.metar_change_trend,
                        'metar_change_trend_warning': metar.metar_change_trend_warning,
                        'metar_rvr_dsc': metar.metar_rvr_dsc,
                        'rvr_min_org': metar.rvr_min_org,
                        'rvr_min_val': metar.rvr_min_val,
                        'metar_rvr_warning': metar.metar_rvr_warning,
                        'metar_ice_flag': metar.metar_ice_flag,
                        'metar_content': metar.metar_content,
                        'metar_warning': metar.metar_warning,
                        'metar_weather_type': metar.metar_weather_type,
                        'data_status': metar.data_status,
                        'created_at': metar.created_at,
                        'sqc': metar.sqc,
                        'operation_popup': metar.operation_popup,
                        'parking_popup': metar.parking_popup,
                        'import_alert': metar.import_alert,
                        'import_alert_time': metar.import_alert_time,
                        'handle_status': metar.handle_status,
                        'import_alert_handle_time': metar.import_alert_handle_time,
                    } for metar in metar_data
                ],
                'taf_data': [
                    {
                        'id': taf.id,
                        'airport_4code': taf.airport_4code,
                        'whole_validity_period': taf.whole_validity_period,
                        'taf_observation_time': taf.taf_observation_time,
                        'taf_type': taf.taf_type,
                        'taf_content': taf.taf_content,
                        'subject_validity_period_start': taf.subject_validity_period_start,
                        'subject_validity_period_end': taf.subject_validity_period_end,
                        'subject_content': taf.subject_content,
                        'subject_warning': taf.subject_warning,
                        'subject_max_temp1': taf.subject_max_temp1,
                        'subject_max_temp1_time': taf.subject_max_temp1_time,
                        'subject_max_temp1_warning': taf.subject_max_temp1_warning,
                        'subject_max_temp2': taf.subject_max_temp2,
                        'subject_max_temp2_time': taf.subject_max_temp2_time,
                        'subject_max_temp2_warning': taf.subject_max_temp2_warning,
                        'subject_min_temp1': taf.subject_min_temp1,
                        'subject_min_temp1_time': taf.subject_min_temp1_time,
                        'subject_min_temp1_warning': taf.subject_min_temp1_warning,
                        'subject_min_temp2': taf.subject_min_temp2,
                        'subject_min_temp2_time': taf.subject_min_temp2_time,
                        'subject_min_temp2_warning': taf.subject_min_temp2_warning,
                        'change_1_type': taf.change_1_type,
                        'change_1_content_all': taf.change_1_content_all,
                        'change_1_warning': taf.change_1_warning,
                        'change_1_validity_period_start': taf.change_1_validity_period_start,
                        'change_1_validity_period_end': taf.change_1_validity_period_end,
                        'change_2_type': taf.change_2_type,
                        'change_2_content_all': taf.change_2_content_all,
                        'change_2_warning': taf.change_2_warning,
                        'change_2_validity_period_start': taf.change_2_validity_period_start,
                        'change_2_validity_period_end': taf.change_2_validity_period_end,
                        'change_3_type': taf.change_3_type,
                        'change_3_content_all': taf.change_3_content_all,
                        'change_3_warning': taf.change_3_warning,
                        'change_3_validity_period_start': taf.change_3_validity_period_start,
                        'change_3_validity_period_end': taf.change_3_validity_period_end,
                        'change_4_type': taf.change_4_type,
                        'change_4_content_all': taf.change_4_content_all,
                        'change_4_warning': taf.change_4_warning,
                        'change_4_validity_period_start': taf.change_4_validity_period_start,
                        'change_4_validity_period_end': taf.change_4_validity_period_end,
                        'change_5_type': taf.change_5_type,
                        'change_5_content_all': taf.change_5_content_all,
                        'change_5_warning': taf.change_5_warning,
                        'change_5_validity_period_start': taf.change_5_validity_period_start,
                        'change_5_validity_period_end': taf.change_5_validity_period_end,
                        'change_6_type': taf.change_6_type,
                        'change_6_content_all': taf.change_6_content_all,
                        'change_6_warning': taf.change_6_warning,
                        'change_6_validity_period_start': taf.change_6_validity_period_start,
                        'change_6_validity_period_end': taf.change_6_validity_period_end,
                        'change_7_type': taf.change_7_type,
                        'change_7_content_all': taf.change_7_content_all,
                        'change_7_warning': taf.change_7_warning,
                        'change_7_validity_period_start': taf.change_7_validity_period_start,
                        'change_7_validity_period_end': taf.change_7_validity_period_end,
                        'change_8_type': taf.change_8_type,
                        'change_8_content_all': taf.change_8_content_all,
                        'change_8_warning': taf.change_8_warning,
                        'change_8_validity_period_start': taf.change_8_validity_period_start,
                        'change_8_validity_period_end': taf.change_8_validity_period_end,
                        'error_report': taf.error_report,
                        'abnormal_label': taf.abnormal_label,
                        'amd_or_cor': taf.amd_or_cor,
                        'data_status': taf.data_status,
                        'created_at': taf.created_at,
                        'sqc': taf.sqc,
                        'import_alert': taf.import_alert,
                        'import_alert_time': taf.import_alert_time,
                        'handle_status': taf.handle_status,
                        'import_alert_handle_time': taf.import_alert_handle_time,
                    } for taf in taf_data
                ]
            }
            
            airport_data['computed_alerts'] = computed_alerts_from_flight(flight_data)
            
            airports_data.append(airport_data)
        
        # 4. 获取航空公司数据
        carriers = sort_carrier_codes(chosen_carriers)
        
        # 5. 获取区域选项数据（带缓存）
        area_options = get_cached_area_options()
        
        # 获取航班数据状态
        flight_status = settings.MTWS_CONFIG.get('FLIGHT_DATA_STATUS', {
            'last_success_time': None,
            'last_attempt_time': None,
            'is_available': True
        })
        
        # 附带后端解析状态（调度器 + 手动刷新均会写入）
        try:
            from parsers.scheduler import get_parsing_status
            backend_parsing_status = get_parsing_status()
        except Exception:
            backend_parsing_status = {}

        response_data = {
            'success': True,
            'data': {
                'airports': airports_data,
                'carriers': carriers,
                'area_options': area_options,
                'timestamp': datetime.now().isoformat(),
                'flight_status': {
                    'is_available': flight_status.get('is_available', True),
                    'last_success_time': flight_status.get('last_success_time').isoformat() if flight_status.get('last_success_time') else None,
                    'last_attempt_time': flight_status.get('last_attempt_time').isoformat() if flight_status.get('last_attempt_time') else None
                },
                'parsing_status': backend_parsing_status,
                'auth_status': get_overview_auth_status(time_mode),
                'seat_identity': get_seat_identity(request),
            }
        }
        
        # 移除缓存机制，直接返回最新数据
        return JsonResponse(response_data)
        
    except Exception as e:
        logger.error(f"获取机场概览数据失败: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': '获取机场概览数据失败',
            'message': str(e)
        }, status=500)


@require_http_methods(["GET"])
def airport_history_reports(request, airport_code, time_mode='current'):
    """
    获取机场历史报文API（用于弹窗功能）
    """
    try:
        # 移除缓存机制，直接从API获取最新历史报文数据
        
        # 获取token（仅在current模式下需要）；非本机回退本机调度缓存
        token = None
        if time_mode == 'current':
            auth_header = request.headers.get('Authorization')
            if auth_header and auth_header.startswith('Bearer '):
                token = auth_header[7:]  # 去掉 'Bearer ' 前缀
            else:
                try:
                    from parsers.scheduler import get_scheduler_token
                    token = get_scheduler_token()
                except Exception:
                    token = None
                if not token:
                    return JsonResponse({
                        'success': False,
                        'error': '未找到认证token，请先在本机登录'
                    }, status=401)
        
        # 获取API适配器
        user_code = request.headers.get('X-User-Code')
        with cas_user_context(user_code):
            adapter = AdapterFactory.create_adapter(time_mode=time_mode, token=token)

            # 调用历史报文接口，增加重试机制
            history_data = None
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    history_data = adapter.get_history_reports(airport_code)
                    if history_data and (history_data.get('metar_reports') or history_data.get('taf_reports')):
                        break  # 成功获取到数据，退出重试
                    elif attempt < max_retries - 1:
                        logger.warning(f"第{attempt + 1}次尝试获取历史报文数据为空，将重试")
                        import time
                        time.sleep(0.5)  # 等待0.5秒后重试
                except Exception as e:
                    logger.error(f"第{attempt + 1}次尝试获取历史报文失败: {e}")
                    if attempt < max_retries - 1:
                        import time
                        time.sleep(0.5)  # 等待0.5秒后重试
                    else:
                        history_data = {'metar_reports': [], 'taf_reports': []}

        if not history_data:
            history_data = {'metar_reports': [], 'taf_reports': []}
        
        # 格式化时间戳为可读格式
        def format_timestamp(timestamp):
            if timestamp:
                try:
                    dt = datetime.fromtimestamp(timestamp / 1000)
                    return dt.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    return str(timestamp)
            return ''
        
        # 处理实况报文
        metar_reports = []
        for report in history_data.get('metar_reports', []):
            metar_reports.append({
                'content': report.get('content', ''),
                'receive_time': report.get('receiveTime', 0),
                'receive_time_formatted': format_timestamp(report.get('receiveTime')),
                'wtype': report.get('wtype', '')
            })
        
        # 处理预报报文
        taf_reports = []
        for report in history_data.get('taf_reports', []):
            taf_reports.append({
                'content': report.get('content', ''),
                'receive_time': report.get('receiveTime', 0),
                'receive_time_formatted': format_timestamp(report.get('receiveTime')),
                'wtype': report.get('wtype', '')
            })
        
        response_data = {
            'success': True,
            'data': {
                'airport_code': airport_code,
                'metar_reports': metar_reports,
                'taf_reports': taf_reports,
                'timestamp': datetime.now().isoformat()
            }
        }
        
        # 移除缓存机制，直接返回最新数据
        return JsonResponse(response_data)
        
    except Exception as e:
        logger.error(f"获取机场历史报文失败: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': '获取机场历史报文失败',
            'message': str(e)
        }, status=500)


@require_http_methods(["POST"])
@csrf_exempt
def trigger_parsing(request, time_mode='current'):
    """
    触发解析API - 使用新的顺序解析模式
    先执行航班解析，再根据有航班的机场执行METAR和TAF解析
    """
    try:
        # 解析请求数据
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            data = {}

        from utils.access_control import resolve_access_identity, has_perm
        identity = resolve_access_identity(request)
        update_types = data.get('updateTypes', None)
        only_nwp = isinstance(update_types, list) and set(update_types) == {'nwp'}
        if only_nwp:
            if not has_perm(identity, 'nwp', 'activate'):
                return JsonResponse({'success': False, 'error': '无温度辅助激活权限'}, status=403)
        else:
            # 刷新/综合解析：需要刷新激活；搜索触发的解析也走此接口
            if not (
                has_perm(identity, 'refresh_btn', 'activate')
                or has_perm(identity, 'search', 'activate')
                or has_perm(identity, 'detail_metar_trend', 'activate')
            ):
                return JsonResponse({'success': False, 'error': '无激活解析权限'}, status=403)
        
        # 获取要更新的数据类型
        # update_types already parsed

        # 同步 NWP 开关状态到调度器缓存
        nwp_enabled = data.get('nwpEnabled', None)
        if nwp_enabled is not None:
            try:
                from parsers.scheduler import set_nwp_enabled
                set_nwp_enabled(bool(nwp_enabled))
            except Exception:
                pass
        
        # 获取token（仅在current模式下需要）
        token = None
        if time_mode == 'current':
            auth_header = request.headers.get('Authorization')
            if auth_header and auth_header.startswith('Bearer '):
                token = auth_header[7:]  # 去掉 'Bearer ' 前缀
                # 缓存 token 供后端调度器复用
                try:
                    from parsers.scheduler import set_scheduler_token
                    set_scheduler_token(token)
                except Exception:
                    pass
            else:
                # 非本机可用调度器缓存的本机 token
                try:
                    from parsers.scheduler import get_scheduler_token
                    token = get_scheduler_token()
                except Exception:
                    token = None
                if not token:
                    return JsonResponse({
                        'success': False,
                        'error': '未找到认证token，请先在本机登录'
                    }, status=401)
        
        # 激活日志：需扫码的席位记 IP + user_id；免扫码只记 IP，避免落到本机值班工号
        raw_user = request.headers.get('X-User-Code') or identity.get('user_id')
        from utils.popup_utils import get_client_ip
        activator_ip = get_client_ip(request)
        log_user = raw_user if identity.get('require_qr') else None
        if log_user:
            logger.info(
                '手动激活解析: types=%s IP=%s user_id=%s group=%s is_local=%s',
                update_types, activator_ip, log_user,
                identity.get('group_name'), identity.get('is_local'),
            )
        else:
            logger.info(
                '手动激活解析: types=%s IP=%s group=%s is_local=%s',
                update_types, activator_ip,
                identity.get('group_name'), identity.get('is_local'),
            )

        # 仅扫码席位把激活人工号写入调度缓存；免扫码不覆盖本机值班工号
        if log_user and time_mode == 'current':
            try:
                from parsers.scheduler import set_scheduler_user_code
                set_scheduler_user_code(log_user)
            except Exception:
                pass

        manager = ParsingManager(time_mode, token, log_user, activator_ip=activator_ip)
        
        # 根据是否有updateTypes参数决定调用哪个方法
        if update_types is None:
            # 没有updateTypes参数，使用原始的顺序解析（兼容备份版本行为）
            result = manager.run_sequential_parsing(time_mode=time_mode)
        else:
            # 有updateTypes参数，使用选择性解析
            result = manager.run_selective_parsing(update_types, time_mode=time_mode)

        # 将本次解析结果同步写入内存状态，供轮询接口附带返回
        try:
            from parsers.scheduler import update_parsing_status
            for dt, pr in result.get('parsers', {}).items():
                update_parsing_status(
                    dt,
                    success=pr.get('success', False),
                    message=pr.get('message', '') or ('' if pr.get('success') else '解析失败'),
                )
        except Exception:
            pass

        if result['success']:
            # 检查是否所有解析器都失败且可能是token问题
            parsers = result.get('parsers', {})
            all_failed = all(not parser.get('success', False) for parser in parsers.values())
            total_records = result.get('total_records', 0)
            
            # 如果在current模式下所有解析器都失败且没有获取到任何数据，可能是token失效
            if all_failed and total_records == 0 and time_mode == 'current':
                logger.warning("所有解析器失败且无数据，可能是token失效")
                return JsonResponse({
                    'success': False,
                    'error': '认证失效，请重新登录'
                }, status=401)
            
            return JsonResponse({
                'success': True,
                'message': '解析任务已完成',
                'data': result
            })
        else:
            return JsonResponse({
                'success': False,
                'error': '解析任务执行失败',
                'message': result.get('message', '未知错误'),
                'data': result
            }, status=500)
            
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': '请求数据格式错误'
        }, status=400)
    except Exception as e:
        logger.error(f"触发解析失败: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': '触发解析失败',
            'message': str(e)
        }, status=500)


@require_http_methods(["GET"])
def get_running_parsers(request, time_mode='current'):
    """
    实时查询当前正在执行或排队中的解析器列表。
    前端在点击刷新前调用此接口判断是否可以触发新一轮解析。
    """
    try:
        from parsers.scheduler import get_running_parsers as _get
        data = _get()
        return JsonResponse({'success': True, 'data': data})
    except Exception as e:
        logger.error(f"查询解析器运行状态失败: {str(e)}")
        return JsonResponse({'success': True, 'data': {'running': [], 'queued': []}})


@require_http_methods(["GET"])
def get_parsing_status(request, time_mode='current'):
    """
    获取解析状态API
    """
    try:
        # 获取最近的解析日志
        latest_logs = ParseLog.objects.order_by('-created_at')[:10]
        
        logs_data = []
        for log in latest_logs:
            logs_data.append({
                'id': log.id,
                'parser_name': log.parser_name,
                'status': log.status,
                'message': log.message,
                'created_at': log.created_at.isoformat()
            })
        
        return JsonResponse({
            'success': True,
            'data': {
                'logs': logs_data,
                'timestamp': datetime.now().isoformat()
            }
        })
        
    except Exception as e:
        logger.error(f"获取解析状态失败: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': '获取解析状态失败',
            'message': str(e)
        }, status=500)


# 鉴权相关API视图（仅用于current模式）
@require_http_methods(["POST"])
@csrf_exempt
def get_qrcode(request, time_mode='current'):
    """
    获取二维码API（仅用于current模式）
    """
    if time_mode != 'current':
        return JsonResponse({
            'success': False,
            'error': '此接口仅用于current模式'
        }, status=400)
    
    try:
        from .cas_login import get_config, get_qrcode
        
        # 获取配置并生成二维码
        config = get_config()
        qr_data = get_qrcode(config)
        
        # 将二维码信息存储到session中
        request.session['qr_id'] = qr_data['qr_id']
        request.session['routing'] = qr_data['routing']
        
        return JsonResponse({
            'success': True,
            'data': {
                'qr_img_base64': qr_data['qr_img_base64'],
                'qr_id': qr_data['qr_id']
            }
        })
        
    except Exception as e:
        logger.error(f"获取二维码失败: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': '获取二维码失败',
            'message': str(e)
        }, status=500)


@require_http_methods(["POST"])
@csrf_exempt 
def check_login_status(request, time_mode='current'):
    """
    检查登录状态API（仅用于current模式）
    """
    if time_mode != 'current':
        return JsonResponse({
            'success': False,
            'error': '此接口仅用于current模式'
        }, status=400)
    
    try:
        from .cas_login import check_scan_status, validate_login, get_config
        
        # 从session中获取二维码信息
        qr_id = request.session.get('qr_id')
        routing = request.session.get('routing')
        
        if not qr_id or not routing:
            return JsonResponse({
                'success': False,
                'error': '请先获取二维码'
            }, status=400)
        
        # 检查扫码状态
        scan_result = check_scan_status(qr_id, routing)
        
        if scan_result.get('success'):
            # 扫码成功，进行登录验证
            config = get_config()
            token = validate_login(config, scan_result)
            
            # 清除二维码信息
            del request.session['qr_id']
            del request.session['routing']
            if request.session.get('seat_pending_group_id'):
                request.session['seat_scanned_user_id'] = scan_result.get('userCode')
            
            return JsonResponse({
                'success': True,
                'data': {
                    'token': token,
                    'userCode': scan_result.get('userCode')
                }
            })
        else:
            return JsonResponse({
                'success': False,
                'message': '等待扫码'
            })
            
    except Exception as e:
        logger.error(f"检查登录状态失败: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': '检查登录状态失败',
            'message': str(e)
        }, status=500)


@require_http_methods(["GET"])
def seat_identity(request, time_mode='current'):
    return JsonResponse({'success': True, 'data': get_seat_identity(request)})


@require_http_methods(["POST"])
@csrf_exempt
def logout(request, time_mode='current'):
    """
    登出API（仅用于current模式）
    """
    if time_mode != 'current':
        return JsonResponse({
            'success': False,
            'error': '此接口仅用于current模式'
        }, status=400)
    
    try:
        from .cas_login import logout as cas_logout
        
        # 从请求头获取token
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header[7:]  # 去掉 'Bearer ' 前缀
        else:
            return JsonResponse({
                'success': False,
                'error': '未找到有效token'
            }, status=400)
        
        # 调用登出API
        logout_success = cas_logout(token)
        
        return JsonResponse({
            'success': logout_success,
            'message': '登出成功' if logout_success else '登出失败'
        })
        
    except Exception as e:
        logger.error(f"登出失败: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': '登出失败',
            'message': str(e)
        }, status=500)








@require_http_methods(["GET"])
def validate_token_status(request, time_mode='current'):
    """
    验证token状态的轻量级接口
    直接调用外部API验证token有效性
    """
    if time_mode != 'current':
        return JsonResponse({'success': True})  # test模式直接返回成功
    
    # 获取token
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return JsonResponse({
            'success': False,
            'error': '未找到认证token'
        }, status=401)
    
    token = auth_header[7:]
    user_code = request.headers.get('X-User-Code')
    
    try:
        # 使用一个轻量的API调用验证token
        import requests
        headers = {'token': token, 'Content-Type': 'application/json'}
        
        # 调用航班数据接口验证token（使用最小的时间范围）
        from datetime import datetime, timedelta
        now = datetime.now()
        start_time = now - timedelta(hours=1)
        end_time = now + timedelta(hours=1)
        
        request_data = {
            "startTime": int(start_time.timestamp() * 1000),
            "endTime": int(end_time.timestamp() * 1000),
            "excludeCancel": True,
            "excludeHaveAta": True
        }
        
        log_cas_api_request(
            '/flight/flightSchedule/getByFlightDate',
            user_id=user_code,
            has_token=True,
        )
        response = requests.post(
            'http://sfa-wgw-inn.sf-airlines.com:1080/flight/flightSchedule/getByFlightDate',
            headers=headers,
            json=request_data,
            timeout=10
        )
        
        if response.status_code == 401:
            return JsonResponse({
                'success': False,
                'error': 'Token已失效'
            }, status=401)
        else:
            return JsonResponse({'success': True})
            
    except Exception as e:
        logger.error(f"Token验证失败: {str(e)}")
        # 网络错误等，当作token有效处理
        return JsonResponse({'success': True})


@require_http_methods(["GET"])
def get_timer_configs(request, time_mode='current'):
    """获取定时器配置的API接口"""
    try:
        configs = {}
        for timer in DataRefreshTimer.objects.all():
            configs[timer.data] = {
                'init_time': timer.init_time,
                'interval': timer.interval
            }
        
        # 添加弹窗稍后处理配置
        from django.conf import settings
        popup_snooze_duration = settings.MTWS_CONFIG.get('POPUP_CONFIG', {}).get('SNOOZE_DURATION_MINUTES', 10)
        configs['popup_snooze_duration'] = popup_snooze_duration
        
        return JsonResponse({
            'success': True,
            'data': configs
        })
        
    except Exception as e:
        logger.error(f"获取定时器配置失败: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': '获取定时器配置失败',
            'message': str(e)
        }, status=500)


@require_http_methods(["GET"])
@csrf_exempt
def get_metar_popups(request, time_mode='current'):
    """
    获取实况弹窗数据
    
    URL参数:
        - time_mode: 时间模式（从URL路径获取）
    
    GET参数:
        - user_code: 用户代码
    """
    try:
        from utils.time_manager import TimeManager
        
        user_code = request.GET.get('user_code', 'default')
        
        # 创建弹窗管理器
        popup_manager = PopupManager(user_code=user_code, time_mode=time_mode)
        
        # 获取未处理的弹窗
        popup_list = popup_manager.get_pending_popups()
        
        # 获取当前时间（毫秒级时间戳）
        current_time_utc = TimeManager.get_current_time_utc(time_mode)
        current_time_ms = int(current_time_utc.timestamp() * 1000)
        
        return JsonResponse({
            'success': True,
            'data': popup_list,
            'current_time': current_time_ms,
            'trace_time': get_popup_trace_hours(),
        })
        
    except Exception as e:
        logger.error(f"获取实况弹窗数据失败: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': '获取实况弹窗数据失败',
            'message': str(e)
        }, status=500)


@require_http_methods(["POST"])
@csrf_exempt
def handle_popup_received(request, time_mode='current'):
    """
    处理弹窗收到操作
    
    URL参数:
        - time_mode: 时间模式（从URL路径获取）
    
    Headers:
        - X-User-Code: 用户代码（current模式需要）
    
    POST参数:
        - sqc: METAR的SQC值
    """
    try:
        data = json.loads(request.body)
        sqc = data.get('sqc')
        
        if not sqc:
            return JsonResponse({
                'success': False,
                'error': '缺少SQC参数'
            }, status=400)
        
        user_code = 'test' if time_mode == 'test' else request.headers.get('X-User-Code')
        result = PopupManager.write_handle_records([sqc], user_code, 'handle', request)
        return JsonResponse({
            'success': True,
            'written': result['written'],
            'updated': result['updated'],
            'message': '操作成功'
        })
        
    except Exception as e:
        logger.error(f"处理弹窗收到操作失败: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': '处理弹窗收到操作失败',
            'message': str(e)
        }, status=500)


@require_http_methods(["POST"])
@csrf_exempt
def handle_popup_batch_ignore(request, time_mode='current'):
    """
    批量忽略弹窗
    
    URL参数:
        - time_mode: 时间模式（从URL路径获取）
    
    Headers:
        - X-User-Code: 用户代码（current模式需要）
    
    POST参数:
        - sqc_list: METAR的SQC列表
    """
    try:
        data = json.loads(request.body)
        sqc_list = data.get('sqc_list', [])
        
        if not sqc_list:
            return JsonResponse({
                'success': False,
                'error': '缺少sqc_list参数'
            }, status=400)
        
        user_code = 'test' if time_mode == 'test' else request.headers.get('X-User-Code')
        result = PopupManager.write_handle_records(sqc_list, user_code, 'ignore', request)
        return JsonResponse({
            'success': True,
            'written': result['written'],
            'updated': result['updated'],
            'message': '批量忽略成功'
        })
        
    except Exception as e:
        logger.error(f"批量忽略弹窗失败: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': '批量忽略弹窗失败',
            'message': str(e)
        }, status=500)


@require_http_methods(["POST"])
@csrf_exempt
def handle_popup_batch_received(request, time_mode='current'):
    """
    批量处理弹窗（收到/去处理）
    
    URL参数:
        - time_mode: 时间模式（从URL路径获取）
    
    Headers:
        - X-User-Code: 用户代码（current模式需要）
    
    POST参数:
        - sqc_list: METAR的SQC列表
    """
    try:
        data = json.loads(request.body)
        sqc_list = data.get('sqc_list', [])
        
        if not sqc_list:
            return JsonResponse({
                'success': False,
                'error': '缺少sqc_list参数'
            }, status=400)
        
        user_code = 'test' if time_mode == 'test' else request.headers.get('X-User-Code')
        result = PopupManager.write_handle_records(sqc_list, user_code, 'handle', request)
        return JsonResponse({
            'success': True,
            'written': result['written'],
            'updated': result['updated'],
            'message': '批量处理成功'
        })
        
    except Exception as e:
        logger.error(f"批量处理弹窗失败: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': '批量处理弹窗失败',
            'message': str(e)
        }, status=500)


@require_http_methods(["GET"])
def airport_extra_info(request, airport_code, time_mode='current'):
    """
    获取机场额外信息API（日出日落时间、跑道信息）
    """
    try:
        import requests
        from suntime import Sun
        
        # 调用aviationweather.gov API获取机场信息
        api_url = f"https://aviationweather.gov/api/data/airport?ids={airport_code}&format=json"
        
        try:
            response = requests.get(api_url, timeout=10)
            response.raise_for_status()
            airport_data = response.json()
            
            if not airport_data or len(airport_data) == 0:
                return JsonResponse({
                    'success': False,
                    'error': '未找到机场信息'
                })
            
            airport_info = airport_data[0]
            lat = airport_info.get('lat')
            lon = airport_info.get('lon')
            runways = airport_info.get('runways', [])
            
            # 计算日出日落时间
            sunrise_time = None
            sunset_time = None
            
            if lat is not None and lon is not None:
                try:
                    sun = Sun(lat, lon)
                    current_date = datetime.now().date()
                    sunrise = sun.get_sunrise_time(current_date)
                    sunset = sun.get_sunset_time(current_date)
                    
                    # 转换为北京时间并格式化为HH:MM
                    sunrise_time = sunrise.strftime('%H:%M')
                    sunset_time = sunset.strftime('%H:%M')
                except Exception as e:
                    logger.warning(f"计算日出日落时间失败: {str(e)}")
            
            # 提取跑道信息
            runway_ids = [runway.get('id', '') for runway in runways if runway.get('id')]
            
            return JsonResponse({
                'success': True,
                'data': {
                    'sunrise': sunrise_time,
                    'sunset': sunset_time,
                    'runways': runway_ids
                }
            })
            
        except requests.RequestException as e:
            logger.error(f"请求aviationweather.gov API失败: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': 'API请求失败'
            })
    
    except Exception as e:
        logger.error(f"获取机场额外信息失败: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': '获取机场信息失败',
            'message': str(e)
        }, status=500)


# ==============================================================================
# 实况入库异常告警 API
# ==============================================================================

@require_http_methods(["GET"])
def get_import_alerts(request, time_mode):
    """
    获取实况入库告警列表（分页）。
    未处理：data_status IN ('N','C') 且 import_alert='Y' 且 import_alert_handle_time IS NULL。
    已处理：import_alert='Y' 且 import_alert_handle_time IS NOT NULL（含已改为 H 的自动处理行）。
    排序：未处理在前，已处理在后，均按 import_alert_time 降序。
    """
    from utils.access_control import resolve_access_identity, has_perm
    if not has_perm(resolve_access_identity(request), 'import_alert', 'activate'):
        return JsonResponse({'success': False, 'error': '无报文入库告警权限'}, status=403)
    try:
        PAGE_SIZE = 10
        MAX_PAGES = 10

        try:
            page = max(1, int(request.GET.get('page', 1)))
        except (ValueError, TypeError):
            page = 1

        unhandled = list(
            Metar.objects.filter(
                data_status__in=['N', 'C'],
                import_alert='Y',
                import_alert_handle_time__isnull=True,
            ).order_by('-import_alert_time')
        )
        handled = list(
            Metar.objects.filter(
                import_alert='Y',
                import_alert_handle_time__isnull=False,
            ).order_by('-import_alert_time')
        )

        total_unhandled = len(unhandled)
        sorted_alerts = (unhandled + handled)[: MAX_PAGES * PAGE_SIZE]

        total_count = len(sorted_alerts)
        total_pages = max(1, (total_count + PAGE_SIZE - 1) // PAGE_SIZE)
        total_pages = min(total_pages, MAX_PAGES)
        page = min(page, total_pages)

        start = (page - 1) * PAGE_SIZE
        page_alerts = sorted_alerts[start: start + PAGE_SIZE]

        def _fmt(m):
            return {
                'sqc': m.sqc,
                'airport_4code': m.airport_4code,
                'metar_type': m.metar_type or 'METAR',
                'import_alert_time': m.import_alert_time,
                'metar_observation_time': m.metar_observation_time,
                'created_at': m.created_at,
                'handle_status': m.handle_status if m.handle_status is not None else '',
                'import_alert_handle_time': m.import_alert_handle_time,
            }

        return JsonResponse({
            'success': True,
            'alerts': [_fmt(m) for m in page_alerts],
            'total_unhandled': total_unhandled,
            'total_pages': total_pages,
            'current_page': page,
        })

    except Exception as e:
        logger.error(f"获取实况入库告警列表失败: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
            'alerts': [],
            'total_unhandled': 0,
            'total_pages': 1,
            'current_page': 1,
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def handle_import_alert(request, time_mode):
    """
    处理实况入库告警：通过 sqc 定位 metar 行，写入 import_alert_handle_time 和 handle_status。
    """
    try:
        from utils.access_control import resolve_access_identity, has_perm
        if not has_perm(resolve_access_identity(request), 'import_alert', 'write'):
            return JsonResponse({'success': False, 'error': '无入库告警写入权限', 'written': False}, status=403)
    except Exception:
        pass

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, Exception):
        return JsonResponse({'success': False, 'error': '请求数据格式错误'}, status=400)

    sqc = data.get('sqc')
    import_alert_handle_time = data.get('import_alert_handle_time')
    handle_status = data.get('handle_status', '')

    if not sqc:
        return JsonResponse({'success': False, 'error': '缺少 sqc 标识'}, status=400)

    try:
        metar = Metar.objects.get(sqc=sqc)
        metar.import_alert_handle_time = import_alert_handle_time
        metar.handle_status = handle_status
        metar.save(update_fields=['import_alert_handle_time', 'handle_status'])
        return JsonResponse({'success': True, 'written': True})
    except Metar.DoesNotExist:
        return JsonResponse({'success': False, 'error': '告警记录不存在'}, status=404)
    except Exception as e:
        logger.error(f"处理告警失败: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def get_taf_import_alerts(request, time_mode):
    """
    获取预报入库告警列表（分页）。
    未处理：data_status IN ('N','C') 且 import_alert='Y' 且 import_alert_handle_time IS NULL。
    已处理：import_alert='Y' 且 import_alert_handle_time IS NOT NULL（含 H 行自动处理记录）。
    排序：未处理在前，已处理在后，均按 created_at 降序。
    taf_type 由预报发布间隔决定：6→FT，3→FC，其他→TAF。配置不完整时不算应发时间。
    """
    from utils.access_control import resolve_access_identity, has_perm
    if not has_perm(resolve_access_identity(request), 'import_alert', 'activate'):
        return JsonResponse({'success': False, 'error': '无报文入库告警权限'}, status=403)
    try:
        PAGE_SIZE = 10
        MAX_PAGES = 10

        try:
            page = max(1, int(request.GET.get('page', 1)))
        except (ValueError, TypeError):
            page = 1

        unhandled = list(
            Taf.objects.filter(
                data_status__in=['N', 'C'],
                import_alert='Y',
                import_alert_handle_time__isnull=True,
            ).order_by('-created_at')
        )
        handled = list(
            Taf.objects.filter(
                import_alert='Y',
                import_alert_handle_time__isnull=False,
            ).order_by('-created_at')
        )

        total_unhandled = len(unhandled)
        sorted_alerts = (unhandled + handled)[: MAX_PAGES * PAGE_SIZE]

        # 机场发布时刻：taf_type，以及与入库告警相同公式的应发时间
        airport_codes = list({t.airport_4code for t in sorted_alerts})
        airport_cfg = {
            a.airport_4code: a
            for a in AirportTafImportConfig.objects.filter(airport_4code__in=airport_codes)
        }
        try:
            leeway_minutes = settings.MTWS_CONFIG['TAF_IMPORT_ALERT']['TAF_ISSUE_LEEWAY_MINUTES']
        except (KeyError, TypeError):
            leeway_minutes = 30

        def _taf_ready(cfg):
            return (
                cfg is not None
                and cfg.taf_init_time is not None
                and cfg.taf_max_delay is not None
                and cfg.import_check_interval is not None
            )

        def _taf_type(airport_code):
            cfg = airport_cfg.get(airport_code)
            interval = cfg.import_check_interval if cfg else None
            if interval == 6:
                return 'FT'
            if interval == 3:
                return 'FC'
            return 'TAF'

        def _expected_issue_time(t):
            cfg = airport_cfg.get(t.airport_4code)
            if not _taf_ready(cfg):
                return None
            # 未处理随当前时刻滚动；已处理停在告警发生时算出的那个应发点
            ref_ms = t.import_alert_time if t.import_alert_handle_time else int(datetime.now(timezone.utc).timestamp() * 1000)
            if not ref_ms:
                return None
            return calc_taf_expected_issue_ms(
                ref_ms, cfg.taf_init_time, cfg.taf_max_delay, cfg.import_check_interval, leeway_minutes
            )

        total_count = len(sorted_alerts)
        total_pages = max(1, (total_count + PAGE_SIZE - 1) // PAGE_SIZE)
        total_pages = min(total_pages, MAX_PAGES)
        page = min(page, total_pages)

        start = (page - 1) * PAGE_SIZE
        page_alerts = sorted_alerts[start: start + PAGE_SIZE]

        def _fmt(t):
            return {
                'sqc': t.sqc,
                'airport_4code': t.airport_4code,
                'taf_type': _taf_type(t.airport_4code),
                'import_alert_time': t.import_alert_time,
                'taf_observation_time': t.taf_observation_time,
                'expected_issue_time': _expected_issue_time(t),
                'created_at': t.created_at,
                'handle_status': t.handle_status if t.handle_status is not None else '',
                'import_alert_handle_time': t.import_alert_handle_time,
            }

        return JsonResponse({
            'success': True,
            'alerts': [_fmt(t) for t in page_alerts],
            'total_unhandled': total_unhandled,
            'total_pages': total_pages,
            'current_page': page,
        })

    except Exception as e:
        logger.error(f"获取预报入库告警列表失败: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
            'alerts': [],
            'total_unhandled': 0,
            'total_pages': 1,
            'current_page': 1,
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def handle_taf_import_alert(request, time_mode):
    """
    处理预报入库告警：通过 sqc 定位 taf 行，写入 import_alert_handle_time 和 handle_status。
    """
    try:
        from utils.access_control import resolve_access_identity, has_perm
        if not has_perm(resolve_access_identity(request), 'import_alert', 'write'):
            return JsonResponse({'success': False, 'error': '无入库告警写入权限', 'written': False}, status=403)
    except Exception:
        pass

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, Exception):
        return JsonResponse({'success': False, 'error': '请求数据格式错误'}, status=400)

    sqc = data.get('sqc')
    import_alert_handle_time = data.get('import_alert_handle_time')
    handle_status = data.get('handle_status', '')

    if not sqc:
        return JsonResponse({'success': False, 'error': '缺少 sqc 标识'}, status=400)

    try:
        taf = Taf.objects.get(sqc=sqc)
        taf.import_alert_handle_time = import_alert_handle_time
        taf.handle_status = handle_status
        taf.save(update_fields=['import_alert_handle_time', 'handle_status'])
        return JsonResponse({'success': True, 'written': True})
    except Taf.DoesNotExist:
        return JsonResponse({'success': False, 'error': '告警记录不存在'}, status=404)
    except Exception as e:
        logger.error(f"处理TAF告警失败: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def get_nwp_data(request, time_mode='current'):
    """
    返回当前模块级 NWP 缓存数据。
    数据由 NwpParser.fetch_and_filter() 在解析时写入，
    前端在 NWP 温度辅助功能开启时轮询此接口。
    """
    try:
        from parsers.NWP import get_nwp_cache, get_nwp_last_updated
        return JsonResponse({
            'success': True,
            'data': get_nwp_cache(),
            'last_updated': get_nwp_last_updated(),
        })
    except Exception as e:
        logger.error(f"获取NWP数据失败: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ==============================================================================
# 机场搜索 API（支持系统内/系统外机场，系统外机场实时获取 METAR/TAF 不写库）
# ==============================================================================

def _serialize_metar(metar):
    """将 Metar ORM 对象序列化为前端所需字典"""
    return {
        'metar_observation_time': metar.metar_observation_time,
        'metar_type': metar.metar_type,
        'metar_auto_flag': metar.metar_auto_flag,
        'metar_wind_direction': metar.metar_wind_direction,
        'metar_wind_speed_original': metar.metar_wind_speed_original,
        'metar_wind_speed_val': metar.metar_wind_speed_val,
        'metar_gust_val': metar.metar_gust_val,
        'metar_wind_warning': metar.metar_wind_warning,
        'metar_visibility_original': metar.metar_visibility_original,
        'metar_visibility_val': metar.metar_visibility_val,
        'metar_visibility_warning': metar.metar_visibility_warning,
        'metar_weather': metar.metar_weather,
        'metar_weather_warning': metar.metar_weather_warning,
        'metar_weather_pre': metar.metar_weather_pre,
        'metar_cloud': metar.metar_cloud,
        'metar_min_cloud_height': metar.metar_min_cloud_height,
        'metar_cloud_warning': metar.metar_cloud_warning,
        'metar_temperature': metar.metar_temperature,
        'metar_temp_val': metar.metar_temp_val,
        'metar_temperature_warning': metar.metar_temperature_warning,
        'metar_dew_point': metar.metar_dew_point,
        'metar_ws_dsc': metar.metar_ws_dsc,
        'metar_ws_warning': metar.metar_ws_warning,
        'metar_change_trend': metar.metar_change_trend,
        'metar_change_trend_warning': metar.metar_change_trend_warning,
        'metar_rvr_dsc': metar.metar_rvr_dsc,
        'rvr_min_org': metar.rvr_min_org,
        'rvr_min_val': metar.rvr_min_val,
        'metar_rvr_warning': metar.metar_rvr_warning,
        'metar_ice_flag': metar.metar_ice_flag,
        'metar_content': metar.metar_content,
        'metar_warning': metar.metar_warning,
        'metar_weather_type': metar.metar_weather_type,
        'data_status': metar.data_status,
        'created_at': metar.created_at,
        'sqc': metar.sqc,
        'operation_popup': metar.operation_popup,
        'parking_popup': metar.parking_popup,
        'import_alert': metar.import_alert,
        'import_alert_time': metar.import_alert_time,
        'handle_status': metar.handle_status,
        'import_alert_handle_time': metar.import_alert_handle_time,
    }


_TAF_CHANGE_DETAIL_FIELDS = [
    'type', 'content_all', 'warning',
    'validity_period_start', 'validity_period_end',
    'wind_speed_mps', 'gust_mps', 'wind_warning',
    'visibility_m', 'visibility_warning',
    'weather1', 'weather2', 'weather3', 'weather4', 'weather5', 'weather_warning',
    'cloud_min', 'cloud_warning',
]


def _serialize_taf(taf):
    """将 Taf ORM 对象序列化为前端所需字典"""
    result = {
        'id': taf.id,
        'airport_4code': taf.airport_4code,
        'whole_validity_period': taf.whole_validity_period,
        'taf_observation_time': taf.taf_observation_time,
        'taf_type': taf.taf_type,
        'taf_content': taf.taf_content,
        'subject_validity_period_start': taf.subject_validity_period_start,
        'subject_validity_period_end': taf.subject_validity_period_end,
        'subject_content': taf.subject_content,
        'subject_warning': taf.subject_warning,
        'subject_wind_speed_mps': taf.subject_wind_speed_mps,
        'subject_gust_mps': taf.subject_gust_mps,
        'subject_wind_warning': taf.subject_wind_warning,
        'subject_visibility_m': taf.subject_visibility_m,
        'subject_visibility_warning': taf.subject_visibility_warning,
        'subject_weather1': taf.subject_weather1,
        'subject_weather2': taf.subject_weather2,
        'subject_weather3': taf.subject_weather3,
        'subject_weather4': taf.subject_weather4,
        'subject_weather5': taf.subject_weather5,
        'subject_weather_warning': taf.subject_weather_warning,
        'subject_cloud_min': taf.subject_cloud_min,
        'subject_cloud_warning': taf.subject_cloud_warning,
        'subject_max_temp1': taf.subject_max_temp1,
        'subject_max_temp1_time': taf.subject_max_temp1_time,
        'subject_max_temp1_warning': taf.subject_max_temp1_warning,
        'subject_max_temp2': taf.subject_max_temp2,
        'subject_max_temp2_time': taf.subject_max_temp2_time,
        'subject_max_temp2_warning': taf.subject_max_temp2_warning,
        'subject_min_temp1': taf.subject_min_temp1,
        'subject_min_temp1_time': taf.subject_min_temp1_time,
        'subject_min_temp1_warning': taf.subject_min_temp1_warning,
        'subject_min_temp2': taf.subject_min_temp2,
        'subject_min_temp2_time': taf.subject_min_temp2_time,
        'subject_min_temp2_warning': taf.subject_min_temp2_warning,
        'error_report': taf.error_report,
        'abnormal_label': taf.abnormal_label,
        'amd_or_cor': taf.amd_or_cor,
        'data_status': taf.data_status,
        'created_at': taf.created_at,
        'sqc': taf.sqc,
        'import_alert': taf.import_alert,
        'import_alert_time': taf.import_alert_time,
        'handle_status': taf.handle_status,
        'import_alert_handle_time': taf.import_alert_handle_time,
    }
    for i in range(1, 9):
        for f in _TAF_CHANGE_DETAIL_FIELDS:
            result[f'change_{i}_{f}'] = getattr(taf, f'change_{i}_{f}', None)
    return result


def _request_token(request, time_mode):
    if time_mode != 'current':
        return None
    auth_header = request.headers.get('Authorization') or ''
    if auth_header.startswith('Bearer '):
        return auth_header[7:]
    try:
        from parsers.scheduler import get_scheduler_token
        return get_scheduler_token()
    except Exception:
        return None


def _get_system_airport_search_data(code, time_mode='current', token=None):
    """从数据库读取系统内机场（has_flight=True）的搜索数据"""
    from core.airport_directory import display_airport_name, ensure_flight_airports
    try:
        ensure_flight_airports([code], time_mode=time_mode, token=token)
    except Exception as exc:
        logger.error(f"补齐机场 {code} 资料失败: {exc}")
    airport = AirportInfo.objects.filter(airport_4code=code).first()

    flight_data = Flight.objects.filter(
        airport_4code=code, has_flight=True
    ).order_by('-created_at').first()

    metar_qs = Metar.objects.filter(
        airport_4code=code, data_status__in=['N', 'C']
    ).order_by('-metar_observation_time')[:1]

    taf_record = Taf.objects.filter(
        airport_4code=code, data_status__in=['N', 'C']
    ).order_by('-created_at').first()

    return {
        'airport_4code': code,
        'airport_name': display_airport_name(airport.airport_name) if airport else display_airport_name(''),
        'is_system_airport': True,
        'area': airport.area if airport else '',
        'area_code': airport.area_code if airport else '',
        'classification': airport.classification if airport else '',
        'forecast_phone': airport.forecast_phone if airport else '',
        'observation_phone': airport.observation_phone if airport else '',
        'other_phone': airport.other_phone if airport else '',
        'flight_data': {
            'has_flight': flight_data.has_flight if flight_data else False,
            'time_slots': flight_data.as_time_slots() if flight_data else [False] * 48,
            'events': selected_events(flight_data.as_events()) if flight_data else [],
        },
        'metar_data': [_serialize_metar(m) for m in metar_qs],
        'taf_data': [_serialize_taf(taf_record)] if taf_record else [],
        'computed_alerts': computed_alerts_from_flight(flight_data),
    }


def _get_external_airport_search_data(code, time_mode, token):
    """从外部 METAR/TAF API 实时获取系统外机场数据，不写入数据库"""
    import pandas as pd

    from core.airport_directory import display_airport_name
    loc = AirportInfo.objects.filter(airport_4code=code).values('airport_name').first()
    airport_name = display_airport_name(loc['airport_name']) if loc else code

    metar_result = []
    taf_result = []

    try:
        from parsers.metar_parser import MetarParser
        from parsers.taf_parser import TafParser

        adapter = AdapterFactory.create_adapter(time_mode=time_mode, token=token)

        # ── METAR ────────────────────────────────────────────────────────────
        metar_df = adapter.get_metar_data([code])
        if metar_df is not None and not metar_df.empty:
            metar_parser = MetarParser(time_mode=time_mode, token=token)
            airport_metar_df = metar_df[
                metar_df['airport4Code'].astype(str).str.strip().str.upper() == code
            ]
            for _, row in airport_metar_df.iterrows():
                try:
                    parsed = metar_parser._parse_metar_content(row)
                    now_ms = int(datetime.now().timestamp() * 1000)
                    metar_result.append({
                        'metar_observation_time': parsed.get('metar_observation_time'),
                        'metar_type': parsed.get('metar_type'),
                        'metar_auto_flag': parsed.get('metar_auto_flag'),
                        'metar_wind_direction': parsed.get('metar_wind_direction'),
                        'metar_wind_speed_original': parsed.get('metar_wind_speed_original'),
                        'metar_wind_speed_val': parsed.get('metar_wind_speed_val'),
                        'metar_gust_val': parsed.get('metar_gust_val'),
                        'metar_wind_warning': parsed.get('metar_wind_warning', 'N'),
                        'metar_visibility_original': parsed.get('metar_visibility_original'),
                        'metar_visibility_val': parsed.get('metar_visibility_val'),
                        'metar_visibility_warning': parsed.get('metar_visibility_warning', 'N'),
                        'metar_weather': parsed.get('metar_weather'),
                        'metar_weather_warning': parsed.get('metar_weather_warning', 'N'),
                        'metar_weather_pre': parsed.get('metar_weather_pre'),
                        'metar_cloud': parsed.get('metar_cloud'),
                        'metar_min_cloud_height': parsed.get('metar_min_cloud_height'),
                        'metar_cloud_warning': parsed.get('metar_cloud_warning', 'N'),
                        'metar_temperature': parsed.get('metar_temperature'),
                        'metar_temp_val': parsed.get('metar_temp_val'),
                        'metar_temperature_warning': parsed.get('metar_temperature_warning', 'N'),
                        'metar_dew_point': parsed.get('metar_dew_point'),
                        'metar_ws_dsc': parsed.get('metar_ws_dsc'),
                        'metar_ws_warning': parsed.get('metar_ws_warning', 'N'),
                        'metar_change_trend': parsed.get('metar_change_trend'),
                        'metar_change_trend_warning': parsed.get('metar_change_trend_warning', 'N'),
                        'metar_rvr_dsc': parsed.get('metar_rvr_dsc'),
                        'rvr_min_org': parsed.get('rvr_min_org'),
                        'rvr_min_val': parsed.get('rvr_min_val'),
                        'metar_rvr_warning': parsed.get('metar_rvr_warning', 'N'),
                        'metar_ice_flag': parsed.get('metar_ice_flag'),
                        'metar_content': parsed.get('metar_content', ''),
                        'metar_warning': parsed.get('metar_warning', 'N'),
                        'metar_weather_type': None,
                        'data_status': 'N',
                        'created_at': now_ms,
                        'sqc': str(row.get('sqc', '')).strip() or None,
                        'operation_popup': 'N',
                        'parking_popup': 'N',
                        'import_alert': 'N',
                        'import_alert_time': None,
                        'handle_status': None,
                        'import_alert_handle_time': None,
                    })
                except Exception as e:
                    logger.warning(f"[搜索] 解析机场 {code} METAR 行失败: {e}")

        # ── TAF ──────────────────────────────────────────────────────────────
        taf_df = adapter.get_taf_data([code])
        if taf_df is not None and not taf_df.empty:
            taf_parser = TafParser(time_mode=time_mode, token=token)
            airport_taf_df = taf_df[
                taf_df['airport4Code'].astype(str).str.strip().str.upper() == code
            ]
            if not airport_taf_df.empty:
                row = airport_taf_df.iloc[0]
                try:
                    taf_content = str(row.get('content', '')).strip()
                    sqc = str(row.get('sqc', '')).strip()
                    raw_obs_time = row.get('observationTime', '')
                    try:
                        obs_time = int(float(raw_obs_time)) if raw_obs_time not in ('', None) else None
                    except (ValueError, TypeError):
                        obs_time = None

                    if taf_content and taf_parser.parse_taf(taf_content, code):
                        taf_parser.observation_time = obs_time
                        data_dict = taf_parser.to_database_dict()
                        now_ms = int(datetime.now().timestamp() * 1000)
                        taf_entry = {
                            'id': None,
                            'airport_4code': code,
                            'sqc': sqc,
                            'taf_type': 'TAF',
                            'data_status': 'N',
                            'created_at': now_ms,
                            'import_alert': 'N',
                            'import_alert_time': None,
                            'handle_status': None,
                            'import_alert_handle_time': None,
                        }
                        taf_entry.update(data_dict)
                        taf_result.append(taf_entry)
                except Exception as e:
                    logger.warning(f"[搜索] 解析机场 {code} TAF 失败: {e}")

    except Exception as e:
        logger.error(f"[搜索] 获取机场 {code} 外部数据失败: {e}")

    return {
        'airport_4code': code,
        'airport_name': airport_name,
        'is_system_airport': False,
        'area': '',
        'area_code': '',
        'classification': '',
        'forecast_phone': '',
        'observation_phone': '',
        'other_phone': '',
        'flight_data': {
            'has_flight': False,
            'time_slots': [False] * 48,
            'events': [],
        },
        'metar_data': metar_result,
        'taf_data': taf_result,
        'computed_alerts': {},
    }


@require_http_methods(["GET"])
def airport_search(request, time_mode='current'):
    """
    机场搜索 API。
    GET 参数: codes=ZBAA,ZSSS  （逗号分隔的四字代码，已由前端校验并去重）
    对系统内机场（has_flight=True）直接读库；对系统外机场实时调 METAR/TAF API，不写库。
    停场实况弹窗「查看详情」在机场不在主页时也走本接口（无航班仅停场，场景很少，
    不另做读库详情；has_flight=False 会落到外部 API，与搜索系统外机场相同）。
    """
    try:
        codes_param = request.GET.get('codes', '').strip()
        if not codes_param:
            return JsonResponse({'success': False, 'error': '缺少 codes 参数'}, status=400)

        codes = [c.strip().upper() for c in codes_param.split(',') if len(c.strip()) == 4]
        if not codes:
            return JsonResponse({'success': False, 'error': '未找到有效的机场四字代码'}, status=400)

        token = None
        if time_mode == 'current':
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                token = auth_header[7:]
            else:
                try:
                    from parsers.scheduler import get_scheduler_token
                    token = get_scheduler_token()
                except Exception:
                    token = None

        user_code = request.headers.get('X-User-Code')
        result = []
        with cas_user_context(user_code):
            for code in codes:
                try:
                    is_system = Flight.objects.filter(airport_4code=code, has_flight=True).exists()
                    if is_system:
                        data = _get_system_airport_search_data(code, time_mode, token)
                    else:
                        data = _get_external_airport_search_data(code, time_mode, token)
                    result.append(data)
                except Exception as e:
                    logger.error(f"[搜索] 机场 {code} 数据获取失败: {e}")
                    result.append({
                        'airport_4code': code,
                        'airport_name': code,
                        'is_system_airport': False,
                    'area': '', 'area_code': '', 'classification': '',
                    'forecast_phone': '', 'observation_phone': '', 'other_phone': '',
                    'flight_data': {'has_flight': False, 'time_slots': [False] * 48, 'events': []},
                    'metar_data': [],
                    'taf_data': [],
                    'computed_alerts': {},
                })

        return JsonResponse({'success': True, 'data': result})

    except Exception as e:
        logger.error(f"[搜索] airport_search 失败: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def flight_carriers(request, time_mode='current'):
    """主页承运人矩阵：航班里出现的代码加上 carrier 表。勾选写入，取消勾选删除。"""
    try:
        if request.method == 'GET':
            return JsonResponse({
                'success': True,
                'flights': distinct_flight_carriers(),
                'selected': sort_carrier_codes(selected_carrier_codes()),
            })
        data = json.loads(request.body or '{}')
        action = data.get('action')
        if action not in ('add', 'remove'):
            return JsonResponse({'success': False, 'error': 'action 必须是 add 或 remove'}, status=400)
        try:
            selected = apply_carrier_change(action, data.get('code'), time_mode)
        except ValueError as exc:
            return JsonResponse({'success': False, 'error': str(exc)}, status=400)
        return JsonResponse({
            'success': True,
            'flights': distinct_flight_carriers(),
            'selected': selected,
        })
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': '数据格式错误'}, status=400)
    except Exception as e:
        logger.error(f"承运人勾选失败: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["GET"])
def get_airport_flight_status(request, time_mode='current'):
    """
    批量获取所有机场的5项实况状态（供地图模式Tooltip使用）
    返回: { airport_4code: { closest_departure_time_of_arriving_flight, closest_landing_time_of_arriving_flight,
                              closest_departure_time_at_this_airport, en_route, has_parking } }
    """
    try:
        from core.models import AircraftParkingInfo

        flights = Flight.objects.all()

        parking_airports = set()
        latest_parking = AircraftParkingInfo.objects.order_by('-parse_time').first()
        if latest_parking and latest_parking.airport_4code:
            parking_list = latest_parking.airport_4code
            if isinstance(parking_list, str):
                parking_list = json.loads(parking_list)
            if isinstance(parking_list, list):
                parking_airports = set(parking_list)

        result = {}
        for flight in flights:
            code = flight.airport_4code
            result[code] = {
                'closest_departure_time_of_arriving_flight': flight.closest_departure_time_of_arriving_flight,
                'closest_landing_time_of_arriving_flight': flight.closest_landing_time_of_arriving_flight,
                'closest_departure_time_at_this_airport': flight.closest_departure_time_at_this_airport,
                'en_route': bool(flight.en_route) if flight.en_route is not None else False,
                'has_parking': code in parking_airports,
            }

        return JsonResponse({'success': True, 'data': result})

    except Exception as e:
        logger.error(f"获取机场实况状态失败: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
