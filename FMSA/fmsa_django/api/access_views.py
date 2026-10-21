"""
超级用户口令：解锁后才能编辑 default 模板。
"""

from __future__ import annotations

import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from utils.access_control import (
    ADMIN_COOKIE,
    ADMIN_TTL_SECONDS,
    LEGACY_ADMIN_COOKIE,
    clear_admin_session,
    create_admin_session,
    ensure_bootstrap_data,
    is_admin_unlocked,
    request_cookie,
    resolve_access_identity,
    set_superuser_password,
    verify_superuser_password,
)
from utils.module_profile import load_modules, load_options


def _json_body(request):
    try:
        return json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return {}


def _set_cookie(resp, key, value, max_age):
    resp.set_cookie(
        key, value, max_age=max_age, httponly=True, samesite='Lax', path='/',
    )
    return resp


def _clear_cookie(resp, key):
    resp.delete_cookie(key, path='/')
    if key == ADMIN_COOKIE:
        resp.delete_cookie(LEGACY_ADMIN_COOKIE, path='/')
    return resp


@csrf_exempt
@require_http_methods(['GET'])
def access_bootstrap(request, time_mode='current'):
    """页面启动：模块开关和超级用户是否已解锁。"""
    ensure_bootstrap_data()
    identity = resolve_access_identity(request)
    return JsonResponse({
        'success': True,
        'data': {
            'identity': identity,
            'modules': load_modules(),
            'options': load_options(),
            'admin_unlocked': is_admin_unlocked(request),
        },
    })


@csrf_exempt
@require_http_methods(['GET'])
def access_session_status(request, time_mode='current'):
    identity = resolve_access_identity(request)
    return JsonResponse({
        'success': True,
        'data': {
            'identity': identity,
            'admin_unlocked': is_admin_unlocked(request, touch=False),
        },
    })


@csrf_exempt
@require_http_methods(['POST'])
def access_admin_unlock(request, time_mode='current'):
    data = _json_body(request)
    password = data.get('password') or ''
    if not verify_superuser_password(password):
        return JsonResponse({'success': False, 'error': '口令错误'}, status=403)
    sid = create_admin_session(request)
    resp = JsonResponse({'success': True})
    return _set_cookie(resp, ADMIN_COOKIE, sid, ADMIN_TTL_SECONDS)


@csrf_exempt
@require_http_methods(['POST'])
def access_admin_touch(request, time_mode='current'):
    unlocked = is_admin_unlocked(request, touch=True)
    return JsonResponse({'success': True, 'admin_unlocked': unlocked})


@csrf_exempt
@require_http_methods(['POST'])
def access_admin_lock(request, time_mode='current'):
    sid = request_cookie(request, ADMIN_COOKIE, LEGACY_ADMIN_COOKIE)
    clear_admin_session(sid)
    resp = JsonResponse({'success': True})
    return _clear_cookie(resp, ADMIN_COOKIE)


@csrf_exempt
@require_http_methods(['POST'])
def access_admin_change_password(request, time_mode='current'):
    if not is_admin_unlocked(request, touch=True):
        return JsonResponse({'success': False, 'error': '请先解锁超级用户'}, status=403)
    data = _json_body(request)
    old_pw = data.get('old_password') or ''
    new_pw = data.get('new_password') or ''
    if len(new_pw) < 6:
        return JsonResponse({'success': False, 'error': '新口令至少 6 位'}, status=400)
    if not verify_superuser_password(old_pw):
        return JsonResponse({'success': False, 'error': '原口令错误'}, status=403)
    set_superuser_password(new_pw)
    return JsonResponse({'success': True})
