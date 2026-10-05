"""实况趋势告警：规则读写与结果表。"""

from __future__ import annotations

import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from utils.access_control import has_perm, is_local_request, resolve_access_identity
from utils.trend_alert import build_results, known_weather_codes, read_config, save_config


def _body(request):
    try:
        return json.loads(request.body.decode('utf-8') or '{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


@require_http_methods(['GET', 'PUT'])
@csrf_exempt
def trend_alert_config(request, time_mode='current'):
    identity = resolve_access_identity(request)
    if request.method == 'GET':
        if not has_perm(identity, 'settings_trend_alert', 'display'):
            return JsonResponse({'success': False, 'error': '无实况趋势告警设置权限'}, status=403)
        from utils.user_settings import scope_meta, settings_subject
        user, _editing = settings_subject(request, time_mode)
        return JsonResponse({
            'success': True,
            'config': read_config(user),
            'weather_codes': sorted(known_weather_codes(user)),
            **scope_meta(request, time_mode),
        })
    if not has_perm(identity, 'settings_trend_alert', 'write'):
        return JsonResponse({'success': False, 'error': '无该设置项写入权限'}, status=403)
    if not is_local_request(request):
        return JsonResponse({'success': False, 'error': '设置项仅允许本机用户修改'}, status=403)
    data = _body(request)
    from utils.user_settings import settings_subject
    user, _editing = settings_subject(request, time_mode)
    payload = data.get('config') if isinstance(data.get('config'), dict) else data
    config, errors = save_config(payload, user)
    if errors:
        return JsonResponse({'success': False, 'error': '；'.join(errors), 'errors': errors}, status=400)
    return JsonResponse({'success': True, 'config': config})


@require_http_methods(['POST'])
@csrf_exempt
def trend_alert_handle(request, time_mode='current'):
    """把当前趋势告警标为已处理。告警颜色变化后会重新变为未处理。"""
    from core.models import AirportTrendAlert

    identity = resolve_access_identity(request)
    if not has_perm(identity, 'view_trend', 'write'):
        return JsonResponse({'success': False, 'error': '无实况趋势告警写入权限', 'written': False}, status=403)
    data = _body(request)
    code = str(data.get('airport') or data.get('airport_4code') or '').strip().upper()
    if len(code) != 4:
        return JsonResponse({'success': False, 'error': '无效的四字代码'}, status=400)
    row = AirportTrendAlert.objects.filter(airport_4code=code).first()
    if not row or row.color not in ('R', 'Y', 'G'):
        return JsonResponse({'success': False, 'error': '未找到该机场趋势告警'}, status=404)
    row.handled = True
    row.handled_signature = row.color
    row.save(update_fields=['handled', 'handled_signature'])
    return JsonResponse({'success': True, 'airport': code, 'handled': True})


@require_http_methods(['GET'])
def trend_alert_results(request, time_mode='current'):
    identity = resolve_access_identity(request)
    if not has_perm(identity, 'view_trend', 'activate'):
        return JsonResponse({'success': False, 'error': '无实况趋势告警查看权限'}, status=403)
    from utils.airport_scope import clamp_future_hours

    scope = (request.GET.get('scope') or 'has_flight').strip()
    if scope not in ('has_flight', 'recent2h'):
        return JsonResponse({'success': False, 'error': '机场范围无效'}, status=400)
    future_hours = clamp_future_hours(request.GET.get('future_hours'))
    result = build_results(scope, future_hours=future_hours)
    return JsonResponse({'success': True, **result})
