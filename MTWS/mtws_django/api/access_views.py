"""
访问控制 / 超级用户管理 API
"""

from __future__ import annotations

import json
import logging
import re
import uuid

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from core.models import (
    AccessGroup,
    AccessGroupPermission,
    NonLocalQrBlacklist,
)
from utils.access_control import (
    ACCESS_MODULES,
    ADMIN_COOKIE,
    ADMIN_TTL_SECONDS,
    LOCAL_GROUP_CODE,
    MODULE_CATEGORIES,
    SEAT_COOKIE,
    clear_admin_session,
    clear_seat_session,
    create_admin_session,
    create_seat_session,
    ensure_bootstrap_data,
    get_local_group,
    has_perm,
    is_admin_unlocked,
    is_local_request,
    is_user_blacklisted,
    permissions_dict_from_group,
    resolve_access_identity,
    seat_sid_from_request,
    set_superuser_password,
    validate_group_permission_payload,
    verify_superuser_password,
)

logger = logging.getLogger('mtws.access')


def _json_body(request):
    try:
        return json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return {}


def _set_cookie(resp, key, value, max_age):
    resp.set_cookie(
        key,
        value,
        max_age=max_age,
        httponly=True,
        samesite='Lax',
        path='/',
    )
    return resp


def _clear_cookie(resp, key):
    resp.delete_cookie(key, path='/')
    return resp


@csrf_exempt
@require_http_methods(['GET'])
def access_bootstrap(request, time_mode='current'):
    """页面启动：身份、权限、可选非本机角色列表。"""
    ensure_bootstrap_data()
    identity = resolve_access_identity(request)
    groups = []
    if not identity.get('is_local'):
        for g in AccessGroup.objects.filter(is_local=False).order_by('sort_order', 'id'):
            groups.append({
                'id': g.id,
                'code': g.code,
                'name': g.name,
                'require_qr': g.require_qr,
            })
    return JsonResponse({
        'success': True,
        'data': {
            'identity': identity,
            'modules': ACCESS_MODULES,
            'categories': MODULE_CATEGORIES,
            'non_local_groups': groups,
            'admin_unlocked': is_admin_unlocked(request),
        },
    })


@csrf_exempt
@require_http_methods(['GET'])
def access_session_status(request, time_mode='current'):
    identity = resolve_access_identity(request)
    return JsonResponse({
        'success': True,
        'data': {'identity': identity, 'admin_unlocked': is_admin_unlocked(request, touch=False)},
    })


@csrf_exempt
@require_http_methods(['POST'])
def access_select_role(request, time_mode='current'):
    """非本机选择角色；免扫码直接建会话，需扫码则返回 pending。"""
    if is_local_request(request):
        return JsonResponse({'success': False, 'error': '本机无需选择角色'}, status=400)

    # 选角前先清掉旧席位，避免登出后残留 cookie 直接进主页
    old_sid = seat_sid_from_request(request)
    clear_seat_session(old_sid)
    request.session.pop('qr_id', None)
    request.session.pop('routing', None)
    request.session.pop('seat_scanned_user_id', None)
    request.session['seat_qr_round'] = uuid.uuid4().hex

    data = _json_body(request)
    group_id = data.get('group_id')
    try:
        group = AccessGroup.objects.get(id=group_id, is_local=False)
    except AccessGroup.DoesNotExist:
        return JsonResponse({'success': False, 'error': '用户组不存在'}, status=404)

    if group.require_qr:
        request.session['seat_pending_group_id'] = group.id
        resp = JsonResponse({
            'success': True,
            'data': {
                'require_qr': True,
                'group_id': group.id,
                'group_name': group.name,
            },
        })
        return _clear_cookie(resp, SEAT_COOKIE)

    request.session.pop('seat_pending_group_id', None)
    perms = permissions_dict_from_group(group)
    # 免扫码组不得带写入
    for code, p in perms.items():
        if p.get('write'):
            p['write'] = False

    sid = create_seat_session(
        group_id=group.id,
        group_code=group.code,
        group_name=group.name,
        is_local=False,
        require_qr=False,
        user_id=None,
        permissions=perms,
    )
    identity = resolve_access_identity(request)  # still guest until cookie set
    # build identity manually for response
    from utils.access_control import build_identity_from_session, get_seat_session
    sess = get_seat_session(sid)
    identity = build_identity_from_session(sess)
    resp = JsonResponse({'success': True, 'data': {'identity': identity, 'require_qr': False}})
    return _set_cookie(resp, SEAT_COOKIE, sid, 12 * 3600)


@csrf_exempt
@require_http_methods(['POST'])
def access_complete_qr_login(request, time_mode='current'):
    """扫码成功后完成非本机席位登录（不替换本机调度 token）。"""
    if is_local_request(request):
        return JsonResponse({'success': False, 'error': '本机无需扫码选角'}, status=400)

    data = _json_body(request)
    group_id = data.get('group_id')
    user_id = str(data.get('user_id') or '').strip()
    if not user_id:
        return JsonResponse({'success': False, 'error': '缺少 user_id'}, status=400)
    if is_user_blacklisted(user_id):
        return JsonResponse({'success': False, 'error': '该用户已在扫码黑名单中，禁止非本机登录'}, status=403)

    try:
        group = AccessGroup.objects.get(id=group_id, is_local=False)
    except AccessGroup.DoesNotExist:
        return JsonResponse({'success': False, 'error': '用户组不存在'}, status=404)
    if not group.require_qr:
        return JsonResponse({'success': False, 'error': '该角色无需扫码'}, status=400)

    pending_gid = request.session.get('seat_pending_group_id')
    if pending_gid and int(pending_gid) != int(group.id):
        return JsonResponse({'success': False, 'error': '请重新选择角色后再扫码'}, status=400)
    scanned_uid = str(request.session.get('seat_scanned_user_id') or '').strip()
    if not scanned_uid or scanned_uid != user_id:
        return JsonResponse({'success': False, 'error': '请先完成当前二维码扫码'}, status=400)
    request.session.pop('seat_scanned_user_id', None)
    request.session.pop('seat_pending_group_id', None)

    logger.info(
        '非本机扫码登录成功 user_id=%s 角色=%s group_id=%s',
        user_id, group.name, group.id,
    )
    perms = permissions_dict_from_group(group)
    sid = create_seat_session(
        group_id=group.id,
        group_code=group.code,
        group_name=group.name,
        is_local=False,
        require_qr=True,
        user_id=user_id,
        permissions=perms,
    )
    from utils.access_control import build_identity_from_session, get_seat_session
    identity = build_identity_from_session(get_seat_session(sid))
    resp = JsonResponse({'success': True, 'data': {'identity': identity}})
    return _set_cookie(resp, SEAT_COOKIE, sid, 12 * 3600)


@csrf_exempt
@require_http_methods(['POST'])
def access_seat_logout(request, time_mode='current'):
    """非本机席位登出（回到角色选择）。本机勿用此接口清 CAS。"""
    sid = seat_sid_from_request(request)
    clear_seat_session(sid)
    request.session.pop('qr_id', None)
    request.session.pop('routing', None)
    request.session.pop('seat_pending_group_id', None)
    request.session.pop('seat_scanned_user_id', None)
    request.session['seat_qr_round'] = uuid.uuid4().hex
    try:
        from .cas_login import reset_cas_http_session
        reset_cas_http_session()
    except Exception:
        pass
    resp = JsonResponse({'success': True})
    return _clear_cookie(resp, SEAT_COOKIE)


@csrf_exempt
@require_http_methods(['POST'])
def access_admin_unlock(request, time_mode='current'):
    if not is_local_request(request):
        return JsonResponse({'success': False, 'error': '仅本机可解锁超级用户'}, status=403)
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
    """设置页切换选项时顺延超级用户会话，不改变当前查看的配置。"""
    unlocked = is_admin_unlocked(request, touch=True)
    return JsonResponse({'success': True, 'admin_unlocked': unlocked})


@csrf_exempt
@require_http_methods(['POST'])
def access_admin_lock(request, time_mode='current'):
    sid = request.COOKIES.get(ADMIN_COOKIE)
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


def _require_admin(request):
    if not is_admin_unlocked(request, touch=True):
        return JsonResponse({'success': False, 'error': '请先解锁超级用户'}, status=403)
    return None


def _serialize_group(group: AccessGroup) -> dict:
    perms = permissions_dict_from_group(group)
    return {
        'id': group.id,
        'code': group.code,
        'name': group.name,
        'is_local': group.is_local,
        'require_qr': group.require_qr,
        'is_builtin': group.is_builtin,
        'sort_order': group.sort_order,
        'permissions': perms,
    }


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def access_admin_groups(request, time_mode='current'):
    err = _require_admin(request)
    if err:
        return err
    ensure_bootstrap_data()

    if request.method == 'GET':
        groups = [_serialize_group(g) for g in AccessGroup.objects.all().order_by('sort_order', 'id')]
        return JsonResponse({
            'success': True,
            'data': {'groups': groups, 'modules': ACCESS_MODULES, 'categories': MODULE_CATEGORIES},
        })

    data = _json_body(request)
    name = (data.get('name') or '').strip()
    if not name:
        return JsonResponse({'success': False, 'error': '名称不能为空'}, status=400)
    code = (data.get('code') or '').strip()
    if not code:
        code = 'nl_' + re.sub(r'[^a-zA-Z0-9_]', '_', name)[:40] + '_' + uuid.uuid4().hex[:6]
    if AccessGroup.objects.filter(code=code).exists():
        return JsonResponse({'success': False, 'error': '组代码已存在'}, status=400)
    require_qr = bool(data.get('require_qr'))
    group = AccessGroup.objects.create(
        code=code,
        name=name,
        is_local=False,
        require_qr=require_qr,
        is_builtin=False,
        sort_order=int(data.get('sort_order') or 100),
    )
    # 空权限起步
    AccessGroupPermission.objects.bulk_create([
        AccessGroupPermission(
            group=group,
            module_code=m['code'],
            can_display=False,
            can_activate=False,
            can_write=False,
        )
        for m in ACCESS_MODULES
    ])
    return JsonResponse({'success': True, 'data': _serialize_group(group)})


@csrf_exempt
@require_http_methods(['GET', 'PUT', 'DELETE'])
def access_admin_group_detail(request, group_id, time_mode='current'):
    err = _require_admin(request)
    if err:
        return err
    try:
        group = AccessGroup.objects.get(id=group_id)
    except AccessGroup.DoesNotExist:
        return JsonResponse({'success': False, 'error': '用户组不存在'}, status=404)

    if request.method == 'GET':
        return JsonResponse({'success': True, 'data': _serialize_group(group)})

    if request.method == 'DELETE':
        if group.is_local or group.is_builtin:
            return JsonResponse({'success': False, 'error': '本机/内置组不可删除'}, status=400)
        group.delete()
        return JsonResponse({'success': True})

    # PUT
    data = _json_body(request)
    if 'name' in data and not group.is_local:
        name = (data.get('name') or '').strip()
        if name:
            group.name = name
    if 'require_qr' in data:
        if group.is_local:
            group.require_qr = False
        else:
            group.require_qr = bool(data.get('require_qr'))
    if 'sort_order' in data:
        group.sort_order = int(data.get('sort_order') or group.sort_order)

    perms_payload = data.get('permissions')
    if perms_payload is not None:
        if not group.is_local:
            group.require_qr = bool(data.get('require_qr', group.require_qr))
        else:
            group.require_qr = False
        ok, msg, rows = validate_group_permission_payload(
            group, perms_payload, is_local_group=group.is_local
        )
        if not ok:
            return JsonResponse({'success': False, 'error': msg}, status=400)
        group.save()
        AccessGroupPermission.objects.filter(group=group).delete()
        AccessGroupPermission.objects.bulk_create([
            AccessGroupPermission(group=group, **row) for row in rows
        ])
    else:
        if 'require_qr' in data and not group.is_local:
            group.require_qr = bool(data.get('require_qr'))
        group.save()

    group.refresh_from_db()
    return JsonResponse({'success': True, 'data': _serialize_group(group)})


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def access_admin_blacklist(request, time_mode='current'):
    err = _require_admin(request)
    if err:
        return err
    if request.method == 'GET':
        rows = list(NonLocalQrBlacklist.objects.all().values('id', 'user_id', 'remark', 'created_at'))
        for r in rows:
            if r.get('created_at'):
                r['created_at'] = r['created_at'].isoformat()
        return JsonResponse({'success': True, 'data': rows})

    data = _json_body(request)
    user_id = str(data.get('user_id') or '').strip()
    if not user_id:
        return JsonResponse({'success': False, 'error': 'user_id 不能为空'}, status=400)
    if NonLocalQrBlacklist.objects.filter(user_id=user_id).exists():
        return JsonResponse({'success': False, 'error': '该 user_id 已在黑名单'}, status=400)
    row = NonLocalQrBlacklist.objects.create(
        user_id=user_id,
        remark=(data.get('remark') or '')[:200] or None,
    )
    return JsonResponse({
        'success': True,
        'data': {'id': row.id, 'user_id': row.user_id, 'remark': row.remark},
    })


@csrf_exempt
@require_http_methods(['DELETE'])
def access_admin_blacklist_detail(request, item_id, time_mode='current'):
    err = _require_admin(request)
    if err:
        return err
    deleted, _ = NonLocalQrBlacklist.objects.filter(id=item_id).delete()
    if not deleted:
        return JsonResponse({'success': False, 'error': '记录不存在'}, status=404)
    return JsonResponse({'success': True})
