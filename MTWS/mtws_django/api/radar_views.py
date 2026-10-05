"""雷达告警 API：配置、状态、结果、触发。"""

from __future__ import annotations

import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from utils.radar.config_defaults import merge_config
from utils.radar import get_radar_job_status, trigger_radar_job

logger = logging.getLogger('mtws.radar.api')


def _deny(request, module, action, error):
    from utils.access_control import has_perm, resolve_access_identity
    if has_perm(resolve_access_identity(request), module, action):
        return None
    return JsonResponse({'success': False, 'error': error, 'written': False}, status=403)


def _json_body(request):
    import json
    try:
        return json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        return {}


@require_http_methods(['GET', 'PUT'])
@csrf_exempt
def radar_alert_config(request, time_mode='current'):
    from core.models import RadarAlertConfig
    from api.settings_views import _deny_settings_write
    from utils.user_settings import json_config_row, save_json_config, scope_meta, settings_subject

    user, _editing = settings_subject(request, time_mode)
    row = json_config_row(RadarAlertConfig, user)
    if request.method == 'GET':
        denied = _deny(request, 'settings_radar_alert', 'display', '无雷达告警设置权限')
        if denied:
            return denied
        cfg = merge_config(row.config if row else None)
        return JsonResponse({'success': True, 'config': cfg, **scope_meta(request, time_mode)})

    denied = _deny_settings_write(request, 'settings_radar_alert')
    if denied:
        return denied
    data = _json_body(request)
    cfg_in = data.get('config')
    if not isinstance(cfg_in, dict):
        return JsonResponse({'success': False, 'error': 'config must be object'}, status=400)
    cfg = merge_config(cfg_in)
    save_json_config(RadarAlertConfig, user, cfg)
    try:
        from parsers.scheduler import reload_scheduler_jobs
        reload_scheduler_jobs()
    except Exception:
        logger.exception('雷达配置保存后重载调度失败')
    # 配置变更后清瓦片索引指纹，下次任务重建
    from core.models import RadarTileIndex
    RadarTileIndex.objects.all().delete()
    return JsonResponse({'success': True, 'config': cfg})


@require_http_methods(['GET'])
def radar_alert_status(request, time_mode='current'):
    return JsonResponse({'success': True, 'status': get_radar_job_status()})


@require_http_methods(['POST'])
@csrf_exempt
def radar_alert_run(request, time_mode='current'):
    from utils.airport_scope import airport_codes_for_scope, clamp_future_hours

    denied = _deny(request, 'map_radar', 'activate', '无雷达告警激活权限')
    if denied:
        return denied
    data = _json_body(request)
    force = bool(data.get('force'))
    scope = (data.get('scope') or '').strip()
    if scope in ('has_flight', 'recent2h'):
        hours = clamp_future_hours(data.get('future_hours'))
        codes = airport_codes_for_scope(scope, hours)
        hide_stale = bool(data.get('hide_stale'))
        st = trigger_radar_job(force=force, codes=codes, hide_stale=hide_stale)
    else:
        st = trigger_radar_job(force=force)
    return JsonResponse({'success': True, 'status': st})


@require_http_methods(['POST'])
@csrf_exempt
def radar_rebuild_tile_index(request, time_mode='current'):
    from core.models import RadarTileIndex, RadarAlertConfig
    from parsers.models import Flight
    from utils.radar.tiles import build_airport_tile_index
    from api.settings_views import _deny_settings_write

    denied = _deny_settings_write(request, 'settings_radar_alert')
    if denied:
        return denied
    from utils.user_settings import active_job_user, json_config_row
    row = json_config_row(RadarAlertConfig, active_job_user())
    cfg = merge_config(row.config if row else None)

    from utils.airport_coords import resolve_airport_coords
    codes = list(Flight.objects.filter(has_flight=True).values_list('airport_4code', flat=True))
    found, coord_errors = resolve_airport_coords(codes)
    airports = [
        {'code': c, 'lat': lat, 'lon': lon}
        for c, (lat, lon) in found.items()
    ]
    zooms = [int(cfg['overview_z']), int(cfg['mid_z']), int(cfg['final_z'])]
    index = build_airport_tile_index(airports, float(cfg['radius_km']), zooms)
    fingerprint = {
        'radius_km': float(cfg['radius_km']),
        'zooms': zooms,
        'codes': sorted(a['code'] for a in airports),
    }
    RadarTileIndex.objects.all().delete()
    RadarTileIndex.objects.create(index_data=index, fingerprint=fingerprint)
    payload = {
        'success': True,
        'airport_count': len(airports),
        'unions': {k: len(v) for k, v in (index.get('unions') or {}).items()},
    }
    if coord_errors:
        payload['error'] = '；'.join(coord_errors)
    return JsonResponse(payload)


def _radar_overlay_meta():
    """最近一次任务的 RainViewer 帧信息，供地图 z3 铺图。"""
    from core.models import RadarJobRun, RadarAlertConfig

    row = RadarJobRun.objects.order_by('-id').first()
    from utils.user_settings import active_job_user, json_config_row
    cfg_row = json_config_row(RadarAlertConfig, active_job_user())
    cfg = merge_config(cfg_row.config if cfg_row else None)
    if not row or not row.host or not row.path:
        return None
    return {
        'host': row.host.rstrip('/'),
        'path': row.path,
        'frame_time': row.frame_time,
        'z': int(cfg.get('overview_z', 3)),
        'tile_size': int(cfg.get('tile_size', 256)),
        'color': int(cfg.get('color_scheme', 2)),
        'smooth': int(cfg.get('smooth', 0)),
        'snow': int(cfg.get('snow', 0)),
    }


@require_http_methods(['POST'])
@csrf_exempt
def radar_alert_handle(request, time_mode='current'):
    """把当前雷达告警标为已处理。告警等级变化后会重新变为未处理。"""
    from core.models import AirportRadarAlert

    denied = _deny(request, 'map_radar', 'write', '无雷达告警写入权限')
    if denied:
        return denied
    data = _json_body(request)
    code = str(data.get('airport_4code') or '').strip().upper()
    if len(code) != 4:
        return JsonResponse({'success': False, 'error': '无效的四字代码'}, status=400)
    row = AirportRadarAlert.objects.filter(airport_4code=code).first()
    if not row:
        return JsonResponse({'success': False, 'error': '未找到该机场告警'}, status=404)
    row.handled = True
    row.handled_signature = row.alert_signature()
    row.save(update_fields=['handled', 'handled_signature'])
    return JsonResponse({'success': True, 'airport_4code': code, 'handled': True})


@require_http_methods(['GET'])
def radar_alerts(request, time_mode='current'):
    """返回当前雷达告警列表，供地图悬浮层使用。只含当前清单内的机场。"""
    from core.models import AirportRadarAlert, RadarAlertConfig
    from utils.access_control import has_perm, resolve_access_identity

    identity = resolve_access_identity(request)
    if not (
        has_perm(identity, 'map_radar', 'activate')
        or has_perm(identity, 'map_radar_nav', 'display')
    ):
        return JsonResponse({'success': False, 'error': '无雷达告警查看权限'}, status=403)
    from utils.airport_scope import airport_codes_for_scope, clamp_future_hours
    from utils.radar.pipeline import job_stale_filter

    show_g = request.GET.get('include_g') == '1'
    scope = (request.GET.get('scope') or 'has_flight').strip()
    if scope not in ('has_flight', 'recent2h'):
        scope = 'has_flight'
    future_hours = clamp_future_hours(request.GET.get('future_hours'))
    universe = set(airport_codes_for_scope(scope, future_hours))
    hide_stale, stale_codes, stale_started = job_stale_filter()
    from utils.user_settings import active_job_user, json_config_row
    cfg_row = json_config_row(RadarAlertConfig, active_job_user())
    alarm_colors = set(merge_config(cfg_row.config if cfg_row else None).get('alarm_colors') or ['R', 'Y'])
    qs = AirportRadarAlert.objects.all()
    rows = []
    observe = []
    watch = []
    for r in qs:
        code = r.airport_4code
        if code not in universe:
            continue
        if hide_stale and code in stale_codes and stale_started is not None:
            if r.updated_at is None or r.updated_at < stale_started:
                continue
        a33, a41 = r.alert_33 or 'N', r.alert_41 or 'N'
        # 两档回波都达到所选颜色才是告警；只达到一档为观察项
        hit33 = a33 in alarm_colors
        hit41 = a41 in alarm_colors
        item = {
            'airport_4code': r.airport_4code,
            'alert_33': a33,
            'alert_41': a41,
            'alert_highest': r.alert_highest or 'N',
            'frame_time': r.frame_time,
            'updated_at': r.updated_at.isoformat() if r.updated_at else None,
            'handled': r.is_handled_current(),
        }
        if hit33 and hit41:
            item['kind'] = 'alarm'
            rows.append(item)
        elif hit33 or hit41:
            item['kind'] = 'observe'
            observe.append(item)
        elif show_g and (a33 == 'G' or a41 == 'G'):
            item['kind'] = 'watch'
            watch.append(item)

    def sort_key(it):
        rank = {'R': 3, 'Y': 2, 'G': 1, 'N': 0}
        return (-rank.get(it['alert_highest'], 0), it['airport_4code'])

    rows.sort(key=sort_key)
    observe.sort(key=sort_key)
    watch.sort(key=sort_key)
    return JsonResponse({
        'success': True,
        'alerts': rows,
        'observe': observe,
        'watch': watch,
        'status': get_radar_job_status(),
        'overlay': _radar_overlay_meta(),
        'scope': scope,
        'future_hours': future_hours,
        'universe_count': len(universe),
    })


_ECHO_RADIUS_KM = 200
_ECHO_RINGS_KM = [50, 100, 150, 200]


def _echo_waiting(seconds: float):
    return JsonResponse({
        'success': True,
        'waiting': True,
        'retry_after': round(max(0.5, float(seconds)), 1),
    })


@require_http_methods(['GET'])
def radar_echo(request, time_mode='current'):
    """机场周边 200 公里、Z7 雷达回波。达到每分钟上限时返回等待秒数，不下载瓦片。"""
    denied = _deny(request, 'map_radar', 'activate', '无雷达回波查看权限')
    if denied:
        return denied
    from core.models import RadarAlertConfig
    from utils.radar.config_defaults import merge_config
    from utils.radar.echo import (
        EchoError, EchoWaiting, cache_get, cache_put, compose_echo, tiles_for_pixel_box,
        meters_per_pixel,
    )
    from utils.radar.rainviewer import RainViewerClient, RainViewerRateLimited
    from utils.radar.tiles import lat_to_y, lon_to_x

    code = (request.GET.get('code') or '').strip().upper()
    if len(code) != 4 or not code.isalnum():
        return JsonResponse({'success': False, 'error': '无效的四字代码'}, status=400)

    from utils.airport_coords import resolve_airport_coords
    found, coord_errors = resolve_airport_coords([code])
    if code not in found:
        detail = coord_errors[0] if coord_errors else '未找到该机场坐标'
        return JsonResponse({'success': False, 'error': detail}, status=404)
    lat, lon = found[code]

    from utils.user_settings import active_job_user, json_config_row
    cfg_row = json_config_row(RadarAlertConfig, active_job_user())
    cfg = merge_config(cfg_row.config if cfg_row else None)
    meta = _radar_overlay_meta() or {}
    z = int(cfg.get('final_z') or 7)
    tile_size = int(cfg.get('tile_size') or 256)
    color = int(meta.get('color') if meta.get('color') is not None else cfg.get('color_scheme', 2))
    smooth = int(meta.get('smooth') if meta.get('smooth') is not None else cfg.get('smooth', 0))
    snow = int(meta.get('snow') if meta.get('snow') is not None else cfg.get('snow', 0))
    client = RainViewerClient(rate_limit_per_minute=int(cfg.get('rate_limit_per_minute', 80)))
    limiter = client.limiter

    host = (meta.get('host') or '').rstrip('/')
    path = meta.get('path') or ''
    frame_time = meta.get('frame_time')
    try:
        if not host or not path:
            wait = limiter.seconds_until_slots(1)
            if wait > 0:
                return _echo_waiting(wait)
            if not limiter.try_reserve(1):
                return _echo_waiting(limiter.seconds_until_slots(1) or 1)
            host, path, frame_time = client.latest_frame_reserved()
            host = host.rstrip('/')

        mpp = meters_per_pixel(lat, z, tile_size)
        full_side = max(2, int(round(_ECHO_RADIUS_KM * 1000.0 / mpp * 2)))
        cx = lon_to_x(lon, z) * tile_size
        cy = lat_to_y(lat, z) * tile_size
        left = cx - full_side / 2.0
        top = cy - full_side / 2.0
        tile_list = tiles_for_pixel_box(z, tile_size, left, top, left + full_side, top + full_side)
        if not tile_list:
            raise EchoError('机场位置超出雷达图范围')

        cache_key = (path, z, tile_size, color, smooth, snow, code, _ECHO_RADIUS_KM)
        cached = cache_get(cache_key)
        if cached:
            cached['success'] = True
            cached['waiting'] = False
            cached['airport_4code'] = code
            return JsonResponse(cached)

        wait = limiter.seconds_until_slots(len(tile_list))
        if wait > 0:
            return _echo_waiting(wait)
        if not limiter.try_reserve(len(tile_list)):
            return _echo_waiting(limiter.seconds_until_slots(len(tile_list)) or 1)

        tiles = client.download_tiles_reserved(
            host, path, z, tile_list, tile_size, color, smooth, snow,
        )
        if not tiles:
            raise EchoError('未获取到雷达回波')
        payload = compose_echo(tiles, z, tile_size, lat, lon, _ECHO_RADIUS_KM, _ECHO_RINGS_KM)
        payload['frame_time'] = frame_time
        cache_put(cache_key, payload)
        payload = dict(payload)
        payload['success'] = True
        payload['waiting'] = False
        payload['airport_4code'] = code
        return JsonResponse(payload)
    except EchoWaiting as e:
        return _echo_waiting(e.retry_after)
    except RainViewerRateLimited as e:
        return _echo_waiting(e.retry_after)
    except EchoError as e:
        status = 404 if e.not_found else 502
        return JsonResponse({'success': False, 'error': str(e)}, status=status)
    except Exception as e:
        logger.exception('radar echo failed for %s', code)
        return JsonResponse({'success': False, 'error': f'获取雷达回波失败: {e}'}, status=502)
