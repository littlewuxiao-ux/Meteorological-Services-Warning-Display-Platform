"""
机场额外信息API
"""

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from datetime import datetime, timedelta
import logging
import requests
from suntime import Sun
from utils.cas_api_log import cas_user_context

logger = logging.getLogger('mtws.api')


def _cas_user_from_request(request):
    return request.headers.get('X-User-Code')


def _resolve_cas_token(request, time_mode='current'):
    """
    解析 CAS token：优先请求头；非本机无自有 token 时回退本机调度缓存。
    报文原文等只读外呼依赖此 token，与权限矩阵无关。
    """
    if time_mode != 'current':
        return None, None
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return auth_header[7:], None
    try:
        from parsers.scheduler import get_scheduler_token
        cached = get_scheduler_token()
        if cached:
            return cached, None
    except Exception:
        pass
    return None, JsonResponse(
        {'success': False, 'error': '未找到认证 token，请先在本机登录'},
        status=401,
    )


@require_http_methods(["GET"])
def airport_metar_history(request, airport_code, time_mode='current'):
    """
    获取机场历史 METAR 图表数据（供详情页 ECharts 图表使用）。
    返回最近 72 小时内的解析数据点列表。
    """
    try:
        token, err = _resolve_cas_token(request, time_mode)
        if err:
            return err

        from parsers.metar_history import fetch_and_parse_metar_history
        with cas_user_context(_cas_user_from_request(request)):
            chart_data = fetch_and_parse_metar_history(
                airport_code, time_mode=time_mode, token=token
            )
        return JsonResponse({'success': True, 'data': chart_data})

    except Exception as exc:
        logger.error(f'获取历史 METAR 数据失败 [{airport_code}]: {exc}')
        return JsonResponse(
            {'success': False, 'error': str(exc)}, status=500
        )


@require_http_methods(["GET"])
def airport_popup_metar_text(request, airport_code, time_mode='current'):
    """
    实况弹窗报文原文：同源原始历史实况接口取最新 3 份，avwx 解析后按告警着色。
    不复用图表数值，也不改详情报文原文接口。
    """
    try:
        token, err = _resolve_cas_token(request, time_mode)
        if err:
            return err

        from parsers.report_text_highlight import build_popup_metar_reports
        with cas_user_context(_cas_user_from_request(request)):
            reports = build_popup_metar_reports(
                airport_code, time_mode=time_mode, token=token
            )
        return JsonResponse({'success': True, 'data': reports})
    except Exception as exc:
        logger.error(f'获取弹窗实况原文失败 [{airport_code}]: {exc}')
        return JsonResponse(
            {'success': False, 'error': str(exc)}, status=500
        )


@require_http_methods(["GET"])
def airport_report_text(request, airport_code, time_mode='current'):
    """
    机场详情报文原文：一次拉取 SA/SP/FC/FT，实况最新 5 份，预报按 FC/FT 规则筛选并着色。
    """
    try:
        token, err = _resolve_cas_token(request, time_mode)
        if err:
            return err

        from parsers.report_text_highlight import build_airport_detail_reports
        with cas_user_context(_cas_user_from_request(request)):
            data = build_airport_detail_reports(
                airport_code, time_mode=time_mode, token=token
            )
        return JsonResponse({'success': True, 'data': data})
    except Exception as exc:
        logger.error(f'获取机场详情报文原文失败 [{airport_code}]: {exc}')
        return JsonResponse(
            {'success': False, 'error': str(exc)}, status=500
        )


@require_http_methods(["GET"])
def airport_coords(request, time_mode=None):
    """
    按机场代码列表返回经纬度。先读 airport_info，本次请求中缺失的机场再访问跑道接口并写回。
    参数：codes=ZBAA,ZSSS,ZGGG,...（逗号分隔，必填）
    响应：{ success: true, coords: { "ZBAA": { lat, lon }, ... } }
    """
    try:
        codes_param = request.GET.get('codes', '').strip()
        if not codes_param:
            return JsonResponse({'success': True, 'coords': {}})

        codes = [c.strip().upper() for c in codes_param.split(',') if c.strip()]
        if not codes:
            return JsonResponse({'success': True, 'coords': {}})

        from utils.airport_coords import resolve_airport_coords
        found, errors = resolve_airport_coords(codes)
        coords = {
            code: {'lat': lat, 'lon': lon}
            for code, (lat, lon) in found.items()
        }
        if errors and not coords:
            return JsonResponse({'success': False, 'error': '；'.join(errors)}, status=404)
        payload = {'success': True, 'coords': coords}
        if errors:
            payload['error'] = '；'.join(errors)
        return JsonResponse(payload)
    except Exception as e:
        logger.error(f'获取机场坐标失败: {e}')
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def _get_coords_from_api(airport_code: str) -> tuple[float | None, float | None, list]:
    """
    从 aviationweather.gov API 获取机场坐标及跑道信息。
    返回 (lat, lon, runways)；请求失败时抛出 requests.RequestException。
    """
    from utils.airport_coords import fetch_aviationweather_airport
    info = fetch_aviationweather_airport(airport_code)
    return info['lat'], info['lon'], info['runways']


def _calc_sun_times(lat: float, lon: float, airport_code: str) -> dict:
    """根据坐标计算日出日落时间，返回含四个字段的字典。"""
    try:
        sun = Sun(lat, lon)
        current_datetime = datetime.now()
        sunrise_utc_dt = sun.get_sunrise_time(current_datetime)
        sunset_utc_dt = sun.get_sunset_time(current_datetime)
        sunrise_beijing = sunrise_utc_dt + timedelta(hours=8)
        sunset_beijing = sunset_utc_dt + timedelta(hours=8)
        result = {
            'sunrise':     sunrise_beijing.strftime('%H:%M'),
            'sunset':      sunset_beijing.strftime('%H:%M'),
            'sunrise_utc': sunrise_utc_dt.strftime('%H:%M'),
            'sunset_utc':  sunset_utc_dt.strftime('%H:%M'),
        }
        logger.info(f"机场{airport_code} 日出日落计算成功: 日出{result['sunrise']}, 日落{result['sunset']}")
        return result
    except Exception as e:
        logger.error(f"计算日出日落时间失败 (机场:{airport_code}, 坐标:{lat},{lon}): {str(e)}", exc_info=True)
        return {'sunrise': None, 'sunset': None, 'sunrise_utc': None, 'sunset_utc': None}


@require_http_methods(["GET"])
def airport_extra_info(request, airport_code, time_mode='current'):
    """
    获取机场额外信息API（日出日落时间、跑道信息）。

    坐标获取策略：
      1. 优先查询 airport_info 中的坐标；
      2. 本次调用发现表中没有或读取失败时，用跑道接口的坐标补写后再使用。
    跑道信息始终来自 aviationweather.gov API。不做坐标巡检。
    """
    try:
        from utils.airport_coords import read_local_coord, store_airport_coord

        code = airport_code.upper()
        local = read_local_coord(code)
        lat, lon = local if local else (None, None)
        coord_source = 'db' if local else None

        # 跑道每次都向该接口取。本地没有坐标时，用同一次响应补写，避免再请求一次。
        runway_ids = []
        try:
            api_lat, api_lon, runways = _get_coords_from_api(code)
            runway_ids = [r.get('id', '') for r in runways if r.get('id')]
            if local is None and api_lat is not None and api_lon is not None:
                store_airport_coord(code, api_lat, api_lon)
                lat, lon = float(api_lat), float(api_lon)
                coord_source = 'api'
        except requests.RequestException as e:
            logger.error(f"请求aviationweather.gov API失败: {str(e)}")
            if lat is None:
                return JsonResponse({
                    'success': False,
                    'error': f'未能获取机场 {code} 的坐标：{e}',
                })

        if lat is None or lon is None:
            return JsonResponse({
                'success': False,
                'error': f'未能获取机场 {code} 的坐标：接口未返回坐标',
            })

        # ── Step 3: 计算日出日落 ───────────────────────────────────────
        sun_times = {'sunrise': None, 'sunset': None, 'sunrise_utc': None, 'sunset_utc': None}
        if lat is not None and lon is not None:
            sun_times = _calc_sun_times(lat, lon, airport_code)

        return JsonResponse({
            'success': True,
            'data': {
                **sun_times,
                'runways':      runway_ids,
                'coord_source': coord_source,
            }
        })

    except Exception as e:
        logger.error(f"获取机场额外信息失败: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': '获取机场信息失败',
            'message': str(e)
        }, status=500)
