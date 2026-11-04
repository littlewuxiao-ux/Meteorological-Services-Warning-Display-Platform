"""历史天气统计：规则读写与查询。"""

from __future__ import annotations

import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from utils.access_control import has_perm, resolve_access_identity
from utils.history_stats import query_history, read_config, resolve_range, save_config


def _body(request):
    try:
        return json.loads(request.body.decode('utf-8') or '{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _ms(value):
    if value in (None, ''):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@require_http_methods(['GET', 'PUT'])
@csrf_exempt
def history_stats_config(request, time_mode='current'):
    identity = resolve_access_identity(request)
    if not has_perm(identity, 'view_history', 'display'):
        return JsonResponse({'success': False, 'error': '无历史视图权限'}, status=403)
    from utils.user_settings import settings_subject

    user, _editing = settings_subject(request, time_mode)
    if request.method == 'GET':
        return JsonResponse({'success': True, 'config': read_config(user)})
    if not has_perm(identity, 'view_history', 'write'):
        return JsonResponse({'success': False, 'error': '无历史视图写入权限'}, status=403)
    data = _body(request)
    payload = data.get('config') if isinstance(data.get('config'), dict) else data
    config, errors = save_config(payload, user)
    if errors:
        return JsonResponse({'success': False, 'error': '；'.join(errors), 'errors': errors}, status=400)
    return JsonResponse({'success': True, 'config': config})


@require_http_methods(['GET'])
def history_stats_range(request, time_mode='current'):
    identity = resolve_access_identity(request)
    if not has_perm(identity, 'view_history', 'display'):
        return JsonResponse({'success': False, 'error': '无历史视图权限'}, status=403)
    preset = request.GET.get('preset') or 'day'
    try:
        start_ms, end_ms, kind = resolve_range(
            preset,
            _ms(request.GET.get('start_ms')),
            _ms(request.GET.get('end_ms')),
            time_mode,
        )
    except ValueError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    return JsonResponse({
        'success': True,
        'preset': kind,
        'start_ms': start_ms,
        'end_ms': end_ms,
    })


@require_http_methods(['POST'])
@csrf_exempt
def history_stats_query(request, time_mode='current'):
    identity = resolve_access_identity(request)
    if not has_perm(identity, 'view_history', 'display'):
        return JsonResponse({'success': False, 'error': '无历史视图权限'}, status=403)
    from api.views import _request_token
    from utils.user_settings import settings_subject

    user, _editing = settings_subject(request, time_mode)
    data = _body(request)
    payload = data.get('config') if isinstance(data.get('config'), dict) else None
    if payload is not None and has_perm(identity, 'view_history', 'write'):
        config, errors = save_config(payload, user)
        if errors:
            return JsonResponse({'success': False, 'error': '；'.join(errors), 'errors': errors}, status=400)
    else:
        config = None
    try:
        result = query_history(
            data.get('preset') or 'day',
            _ms(data.get('start_ms')),
            _ms(data.get('end_ms')),
            time_mode=time_mode,
            token=_request_token(request, time_mode),
            user_code=user,
            config=config,
        )
    except ValueError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    except Exception:
        import logging
        logging.getLogger('fmsa.history').exception('历史统计查询失败')
        return JsonResponse({'success': False, 'error': '查询失败'}, status=500)
    return JsonResponse({'success': True, **result})
