"""
超级用户口令与会话。模块开关在 data/fmsa_modules.json，不在这里。
"""

from __future__ import annotations

import secrets
import threading
import time
from typing import Optional

from django.contrib.auth.hashers import check_password, make_password

from utils.popup_utils import get_client_ip

SUPERUSER_CONFIG_TYPE = 'access_control'
SUPERUSER_CONFIG_KEY = 'superuser_password_hash'
DEFAULT_SUPERUSER_PASSWORD = 'admin2026'

ADMIN_COOKIE = 'fmsa_admin_sid'
LEGACY_ADMIN_COOKIE = 'mtws_admin_sid'
ADMIN_TTL_SECONDS = 5 * 60

_lock = threading.Lock()
_admin_sessions: dict = {}
_access_db_lock = threading.Lock()
_access_db_ready = False


def _now() -> float:
    return time.time()


def ensure_access_database():
    """口令库迁移到当前版本，并把旧配置库里的口令哈希搬过来。"""
    global _access_db_ready
    if _access_db_ready:
        return
    with _access_db_lock:
        if _access_db_ready:
            return
        from django.core.management import call_command
        from fmsa_system.db_router import ACCESS_DB

        call_command('migrate', 'access_db', database=ACCESS_DB, verbosity=0, interactive=False)
        _move_legacy_superuser_hash()
        _access_db_ready = True


def _move_legacy_superuser_hash():
    """旧版口令哈希在配置库 system_config：口令库没有时搬入，配置库里的旧记录删除。"""
    from access_db.models import AccessSetting
    from config_db.models import SystemConfig

    legacy = SystemConfig.objects.filter(
        config_type=SUPERUSER_CONFIG_TYPE, config_key=SUPERUSER_CONFIG_KEY
    ).first()
    if not legacy:
        return
    if not AccessSetting.objects.filter(key=SUPERUSER_CONFIG_KEY).exists():
        AccessSetting.objects.create(key=SUPERUSER_CONFIG_KEY, value=legacy.config_value)
    legacy.delete()


def ensure_bootstrap_data():
    """确保超级用户口令哈希存在。"""
    from access_db.models import AccessSetting
    from config_db.cleanup import drop_unused_config_tables

    ensure_access_database()
    drop_unused_config_tables()
    AccessSetting.objects.get_or_create(
        key=SUPERUSER_CONFIG_KEY,
        defaults={'value': make_password(DEFAULT_SUPERUSER_PASSWORD)},
    )


def get_superuser_hash() -> str:
    from access_db.models import AccessSetting
    ensure_bootstrap_data()
    row = AccessSetting.objects.filter(key=SUPERUSER_CONFIG_KEY).first()
    return row.value if row else ''


def set_superuser_password(raw_password: str) -> None:
    from access_db.models import AccessSetting
    ensure_access_database()
    AccessSetting.objects.update_or_create(
        key=SUPERUSER_CONFIG_KEY,
        defaults={'value': make_password(raw_password)},
    )


def verify_superuser_password(raw_password: str) -> bool:
    hashed = get_superuser_hash()
    if not hashed:
        return False
    return check_password(raw_password, hashed)


def create_admin_session(request) -> str:
    sid = secrets.token_urlsafe(24)
    with _lock:
        _admin_sessions[sid] = {
            'ip': get_client_ip(request),
            'user_code': str(request.headers.get('X-User-Code') or '').strip(),
            'expires': _now() + ADMIN_TTL_SECONDS,
        }
    return sid


def touch_admin_session(sid: str, user_code: str | None = None) -> bool:
    with _lock:
        sess = _admin_sessions.get(sid)
        if not sess:
            return False
        if sess['expires'] < _now():
            _admin_sessions.pop(sid, None)
            return False
        bound = str(sess.get('user_code') or '')
        incoming = str(user_code or '').strip()
        if bound and incoming and incoming != bound:
            _admin_sessions.pop(sid, None)
            return False
        sess['expires'] = _now() + ADMIN_TTL_SECONDS
        return True


def clear_admin_session(sid: Optional[str]) -> None:
    if not sid:
        return
    with _lock:
        _admin_sessions.pop(sid, None)


def request_cookie(request, name: str, legacy: str = ''):
    value = request.COOKIES.get(name)
    if value:
        return value
    if legacy:
        return request.COOKIES.get(legacy)
    return None


def is_admin_unlocked(request, *, touch: bool = False) -> bool:
    sid = request_cookie(request, ADMIN_COOKIE, LEGACY_ADMIN_COOKIE) or request.headers.get('X-Admin-Session')
    if not sid:
        return False
    user_code = str(request.headers.get('X-User-Code') or '').strip()
    if touch:
        return touch_admin_session(sid, user_code)
    with _lock:
        sess = _admin_sessions.get(sid)
        if not sess or sess['expires'] < _now():
            if sess:
                _admin_sessions.pop(sid, None)
            return False
        bound = str(sess.get('user_code') or '')
        if bound and user_code and user_code != bound:
            return False
        return True


def resolve_access_identity(request) -> dict:
    """当前登录工号。能看能写什么由模块开关决定。"""
    from utils.module_profile import permissions_for_runtime

    ensure_bootstrap_data()
    code = str(request.headers.get('X-User-Code') or '').strip()
    if code in {'', '--', '-', 'system', 'scheduler', 'test', 'default'}:
        code = ''
    perms = permissions_for_runtime()
    return {
        'role': 'user',
        'show_logout': bool((perms.get('login_user') or {}).get('display')),
        'label': code,
        'user_id': code or None,
        'permissions': perms,
    }


def has_perm(identity: dict, module_code: str, action: str) -> bool:
    """action: display | write。模块开着则显示和写入都允许。"""
    perms = (identity or {}).get('permissions') or {}
    mod = perms.get(module_code) or {}
    visible = bool(mod.get('display') or mod.get('write'))
    if action == 'display':
        return visible
    if action == 'write':
        return visible and bool(mod.get('write'))
    return False
