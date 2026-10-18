"""
访问控制：用户组权限、席位会话、超管口令、黑名单。
"""

from __future__ import annotations

import re
import secrets
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone

from utils.popup_utils import get_client_ip, is_loopback_ip

# 模块定义。category 对应管理页四大类；parent 为视图下的子项，须父项显示才可显示。
# 显示即具备该模块的后台解析/接口调用权限；local_write_only 的写入仅本机组可授。
ACCESS_MODULES: List[Dict[str, Any]] = [
    {'code': 'login_user', 'name': '登录的用户/登出按钮', 'category': 'function', 'has_write': False,
     'hint_display': '显示右上角用户与登出按钮，可点击登出'},
    {'code': 'nwp', 'name': '温度辅助', 'category': 'function', 'has_write': False,
     'hint_display': '显示温度辅助按钮并可触发解析'},
    {'code': 'refresh_btn', 'name': '刷新按钮', 'category': 'function', 'has_write': False,
     'hint_display': '显示刷新按钮并可触发后台解析'},
    {'code': 'search', 'name': '搜索框和搜索按钮', 'category': 'function', 'has_write': False,
     'hint_display': '显示搜索框和搜索按钮，搜索时可触发解析'},
    {'code': 'settings_btn', 'name': '设置按钮', 'category': 'function', 'has_write': False,
     'hint_display': '显示主页设置按钮'},
    {'code': 'metar_popup', 'name': '实况弹窗', 'category': 'function', 'has_write': True,
     'hint_display': '显示标题、运行类、停场类、恢复弹窗、处理记录及弹窗，所有按钮均可点击',
     'hint_write': '将处理记录写入报文（按用户）'},
    {'code': 'view_home', 'name': '主页', 'category': 'views', 'has_write': False,
     'hint_display': '导航栏显示并可进入列表主页'},
    {'code': 'view_map', 'name': '地图', 'category': 'views', 'has_write': False,
     'hint_display': '导航栏显示并可进入地图模式'},
    {'code': 'map_radar', 'name': '雷达回波与强对流预警', 'category': 'views', 'parent': 'view_map',
     'has_write': True,
     'hint_display': '地图中显示雷达回波和强对流预警',
     'hint_write': '可将雷达告警标为已处理并写库'},
    {'code': 'map_radar_nav', 'name': '导航栏告警数量', 'category': 'views', 'parent': 'view_map',
     'has_write': False,
     'hint_display': '地图导航图标显示未处理雷达告警数量'},
    {'code': 'map_satellite', 'name': '卫星云图', 'category': 'views', 'parent': 'view_map',
     'has_write': False,
     'hint_display': '地图中显示红外、水汽、可见光卫星云图'},
    {'code': 'view_plain', 'name': '翻译', 'category': 'views', 'has_write': False,
     'hint_display': '导航栏显示并可进入中文模式'},
    {'code': 'view_trend', 'name': '实况趋势', 'category': 'views', 'has_write': True,
     'hint_display': '导航栏显示并可进入实况趋势告警',
     'hint_write': '可将趋势告警标为已处理并写库'},
    {'code': 'view_trend_nav', 'name': '导航栏告警数量', 'category': 'views', 'parent': 'view_trend',
     'has_write': False,
     'hint_display': '趋势导航图标显示未处理告警数量'},
    {'code': 'import_alert', 'name': '报文入库告警', 'category': 'views', 'has_write': True,
     'hint_display': '导航栏显示并可进入报文入库告警',
     'hint_write': '可将告警标为已处理并写库'},
    {'code': 'detail_contact_home', 'name': '详情页·主页·联系方式', 'category': 'shared', 'has_write': False,
     'hint_display': '主页模式下详情页显示联系方式'},
    {'code': 'detail_contact_plain', 'name': '详情页·中文·联系方式', 'category': 'shared', 'has_write': False,
     'hint_display': '中文模式下详情页显示联系方式'},
    {'code': 'search_contact_home', 'name': '搜索结果·主页·联系方式', 'category': 'shared', 'has_write': False,
     'hint_display': '主页模式下搜索结果展示联系方式'},
    {'code': 'search_contact_plain', 'name': '搜索结果·中文·联系方式', 'category': 'shared', 'has_write': False,
     'hint_display': '中文模式下搜索结果展示联系方式'},
    {'code': 'detail_metar_trend', 'name': '机场详情页实况趋势', 'category': 'shared', 'has_write': False,
     'hint_display': '详情页显示实况趋势，展开时可触发解析'},
    {'code': 'settings_airport_info', 'name': '机场信息设置', 'category': 'settings', 'has_write': True, 'local_write_only': True,
     'hint_display': '设置中显示机场信息', 'hint_write': '可改机场信息'},
    {'code': 'settings_prefix_area', 'name': '机场区域', 'category': 'settings', 'has_write': True, 'local_write_only': True,
     'hint_display': '设置中显示机场区域', 'hint_write': '可改机场区域'},
    {'code': 'settings_taf_import', 'name': '预报入库告警', 'category': 'settings', 'has_write': True, 'local_write_only': True,
     'hint_display': '设置中显示预报入库告警', 'hint_write': '可改预报入库告警'},
    {'code': 'settings_data_refresh', 'name': '数据更新设置', 'category': 'settings', 'has_write': True, 'local_write_only': True,
     'hint_display': '设置中显示数据更新', 'hint_write': '可改刷新定时'},
    {'code': 'settings_popup', 'name': '弹窗设置', 'category': 'settings', 'has_write': True, 'local_write_only': True,
     'hint_display': '设置中显示弹窗规则', 'hint_write': '可改等级、余量、追溯时间以及运行类、停场类、降级免打扰'},
    {'code': 'settings_alert_thresholds', 'name': '告警阈值', 'category': 'settings', 'has_write': True, 'local_write_only': True,
     'hint_display': '设置中显示告警阈值', 'hint_write': '可改机场告警阈值'},
    {'code': 'settings_weather_type', 'name': '天气类型', 'category': 'settings', 'has_write': True, 'local_write_only': True,
     'hint_display': '设置中显示天气类型', 'hint_write': '可改天气类型'},
    {'code': 'settings_weather_alert', 'name': '天气告警等级', 'category': 'settings', 'has_write': True, 'local_write_only': True,
     'hint_display': '设置中显示天气告警等级', 'hint_write': '可改天气告警等级'},
    {'code': 'settings_radar_alert', 'name': '雷达告警', 'category': 'settings', 'has_write': True, 'local_write_only': True,
     'hint_display': '设置中显示雷达告警', 'hint_write': '可改雷达告警规则'},
    {'code': 'settings_trend_alert', 'name': '实况趋势告警', 'category': 'settings', 'has_write': True, 'local_write_only': True,
     'hint_display': '设置中显示实况趋势告警', 'hint_write': '可改实况趋势告警规则'},
    {'code': 'settings_map_style', 'name': '地图样式', 'category': 'settings', 'has_write': True, 'local_write_only': True,
     'hint_display': '设置中显示地图样式', 'hint_write': '可改地图样式'},
]

MODULE_CATEGORIES = [
    {'code': 'function', 'name': '通用功能区'},
    {'code': 'views', 'name': '视图设置'},
    {'code': 'shared', 'name': '其它功能'},
    {'code': 'settings', 'name': '设置选项'},
]

MODULE_BY_CODE = {m['code']: m for m in ACCESS_MODULES}

# 导航视图，顺序即无权限回落的优先级（导航栏顺序另见 views_nav.js）
VIEW_MODULE_CODES = ('view_home', 'view_map', 'view_plain', 'view_trend', 'import_alert')
_VIEW_REQUIRED_MSG = '主页、地图、翻译、实况趋势、报文入库告警至少需要保留一个显示权限'

LOCAL_GROUP_CODE = 'local'
# 旧版存于配置库 system_config(config_type, config_key)，现存于用户组库 access_setting(key)
SUPERUSER_CONFIG_TYPE = 'access_control'
SUPERUSER_CONFIG_KEY = 'superuser_password_hash'
DEFAULT_SUPERUSER_PASSWORD = 'admin2026'

SEAT_COOKIE = 'fmsa_seat_sid'
ADMIN_COOKIE = 'fmsa_admin_sid'
# 已打开页面里的旧 cookie 继续认，避免改名后席位立刻掉线
LEGACY_SEAT_COOKIE = 'mtws_seat_sid'
LEGACY_ADMIN_COOKIE = 'mtws_admin_sid'
SEAT_TTL_SECONDS = 12 * 3600
ADMIN_TTL_SECONDS = 5 * 60

# 设置子页写入权限 → settings API 模块码
SETTINGS_MODULE_MAP = {
    'airport_info': 'settings_airport_info',
    'prefix_area': 'settings_prefix_area',
    'taf_import': 'settings_taf_import',
    'data_refresh': 'settings_data_refresh',
    'popup': 'settings_popup',
    'alert_thresholds': 'settings_alert_thresholds',
    'weather_type': 'settings_weather_type',
    'weather_alert': 'settings_weather_alert',
    'radar_alert': 'settings_radar_alert',
    'trend_alert': 'settings_trend_alert',
    'map_style': 'settings_map_style',
}

_lock = threading.Lock()
_seat_sessions: Dict[str, dict] = {}
_admin_sessions: Dict[str, dict] = {}


def _now() -> float:
    return time.time()


def is_local_request(request) -> bool:
    return is_loopback_ip(get_client_ip(request))


def empty_perm() -> dict:
    return {'display': False, 'write': False}


def full_perm(module_code: str) -> dict:
    meta = MODULE_BY_CODE.get(module_code, {})
    return {
        'display': True,
        'write': bool(meta.get('has_write', False)),
    }


def default_local_permissions() -> Dict[str, dict]:
    """本机组出厂：除超管外全部打开。"""
    return {m['code']: full_perm(m['code']) for m in ACCESS_MODULES}


def permissions_dict_from_group(group) -> Dict[str, dict]:
    result = {m['code']: empty_perm() for m in ACCESS_MODULES}
    if not group:
        return result
    for row in group.permissions.all():
        meta = MODULE_BY_CODE.get(row.module_code)
        if not meta:
            continue
        can_write = bool(row.can_write) and bool(meta.get('has_write'))
        if meta.get('local_write_only') and not group.is_local:
            can_write = False
        result[row.module_code] = {
            'display': bool(row.can_display),
            'write': can_write,
        }
    return result


_ACCESS_TABLES = ('access_group', 'access_group_permission', 'non_local_qr_blacklist')
_access_db_lock = threading.Lock()
_access_db_ready = False


def _table_columns(conn, table: str) -> List[str]:
    with conn.cursor() as cur:
        return [col.name for col in conn.introspection.get_table_description(cur, table)]


def _move_legacy_access_tables():
    """旧版用户组表在配置库里：复制到用户组库后改名留作备份，不再读取。"""
    from django.db import connections, transaction
    from fmsa_system.db_router import ACCESS_DB

    src = connections['default']
    dst = connections[ACCESS_DB]
    legacy = set(src.introspection.table_names())
    if 'access_group' not in legacy:
        return
    with transaction.atomic(using=ACCESS_DB):
        for table in _ACCESS_TABLES:
            if table not in legacy:
                continue
            src_cols = set(_table_columns(src, table))
            cols = [c for c in _table_columns(dst, table) if c in src_cols]
            col_sql = ', '.join(f'"{c}"' for c in cols)
            with src.cursor() as cur:
                cur.execute(f'SELECT {col_sql} FROM "{table}"')
                rows = cur.fetchall()
            if rows:
                marks = ', '.join(['%s'] * len(cols))
                with dst.cursor() as cur:
                    cur.executemany(f'INSERT INTO "{table}" ({col_sql}) VALUES ({marks})', rows)
    suffix = timezone.now().strftime('%Y%m%d%H%M%S')
    with src.cursor() as cur:
        for table in _ACCESS_TABLES:
            if table in legacy:
                cur.execute(f'ALTER TABLE "{table}" RENAME TO "{table}_bak_{suffix}"')


def ensure_access_database():
    """每个进程首次访问时把用户组库迁移到当前版本（复制来的旧库也能用）；
    首次建表时从旧配置库搬入已有数据。"""
    global _access_db_ready
    if _access_db_ready:
        return
    with _access_db_lock:
        if _access_db_ready:
            return
        from django.core.management import call_command
        from django.db import connections
        from fmsa_system.db_router import ACCESS_DB

        fresh = 'access_group' not in connections[ACCESS_DB].introspection.table_names()
        call_command('migrate', 'core', database=ACCESS_DB, verbosity=0, interactive=False)
        if fresh:
            _move_legacy_access_tables()
        _move_legacy_superuser_hash()
        _access_db_ready = True


def _move_legacy_superuser_hash():
    """旧版口令哈希在配置库 system_config：用户组库没有时搬入；配置库里的旧记录一律删除。"""
    from core.models import AccessSetting, SystemConfig

    legacy = SystemConfig.objects.filter(
        config_type=SUPERUSER_CONFIG_TYPE, config_key=SUPERUSER_CONFIG_KEY
    ).first()
    if not legacy:
        return
    if not AccessSetting.objects.filter(key=SUPERUSER_CONFIG_KEY).exists():
        AccessSetting.objects.create(key=SUPERUSER_CONFIG_KEY, value=legacy.config_value)
    legacy.delete()


def ensure_bootstrap_data():
    """确保本机组、出厂权限、超管口令哈希存在。"""
    from core.models import AccessGroup, AccessGroupPermission, AccessSetting

    ensure_access_database()
    group, created = AccessGroup.objects.get_or_create(
        code=LOCAL_GROUP_CODE,
        defaults={
            'name': '本机用户',
            'is_local': True,
            'require_qr': False,
            'is_builtin': True,
            'sort_order': 0,
        },
    )
    if created or not group.permissions.exists():
        AccessGroupPermission.objects.filter(group=group).delete()
        bulk = []
        for m in ACCESS_MODULES:
            bulk.append(AccessGroupPermission(
                group=group,
                module_code=m['code'],
                can_display=True,
                can_write=bool(m.get('has_write')),
            ))
        AccessGroupPermission.objects.bulk_create(bulk)
    else:
        # 本机组补齐后续新增模块
        existing = {
            row.module_code: row
            for row in AccessGroupPermission.objects.filter(group=group)
        }
        missing = []
        for m in ACCESS_MODULES:
            row = existing.get(m['code'])
            if not row:
                missing.append(AccessGroupPermission(
                    group=group,
                    module_code=m['code'],
                    can_display=True,
                    can_write=bool(m.get('has_write')),
                ))
                continue
            # 本机组可写模块显示即写入
            if (
                group.is_local
                and m.get('has_write')
                and row.can_display
                and not row.can_write
            ):
                row.can_write = True
                row.save(update_fields=['can_write'])
        if missing:
            AccessGroupPermission.objects.bulk_create(missing)
    # 复制进来的库可能来自旧版本，清掉已不存在的模块
    AccessGroupPermission.objects.exclude(module_code__in=MODULE_BY_CODE.keys()).delete()

    AccessSetting.objects.get_or_create(
        key=SUPERUSER_CONFIG_KEY,
        defaults={'value': make_password(DEFAULT_SUPERUSER_PASSWORD)},
    )


def get_superuser_hash() -> str:
    from core.models import AccessSetting
    ensure_bootstrap_data()
    row = AccessSetting.objects.filter(key=SUPERUSER_CONFIG_KEY).first()
    return row.value if row else ''


def set_superuser_password(raw_password: str) -> None:
    from core.models import AccessSetting
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
    if not is_local_request(request):
        return False
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


def create_seat_session(
    *,
    group_id: int,
    group_code: str,
    group_name: str,
    is_local: bool,
    require_qr: bool,
    user_id: Optional[str],
    permissions: Dict[str, dict],
) -> str:
    sid = secrets.token_urlsafe(24)
    with _lock:
        _seat_sessions[sid] = {
            'group_id': group_id,
            'group_code': group_code,
            'group_name': group_name,
            'is_local': is_local,
            'require_qr': require_qr,
            'user_id': user_id,
            'permissions': permissions,
            'expires': _now() + SEAT_TTL_SECONDS,
            'created_at': timezone.now().isoformat(),
        }
    return sid


def get_seat_session(sid: Optional[str]) -> Optional[dict]:
    if not sid:
        return None
    with _lock:
        sess = _seat_sessions.get(sid)
        if not sess:
            return None
        if sess['expires'] < _now():
            _seat_sessions.pop(sid, None)
            return None
        sess['expires'] = _now() + SEAT_TTL_SECONDS
        return dict(sess)


def clear_seat_session(sid: Optional[str]) -> None:
    if not sid:
        return
    with _lock:
        _seat_sessions.pop(sid, None)


def seat_sid_from_request(request) -> Optional[str]:
    return request_cookie(request, SEAT_COOKIE, LEGACY_SEAT_COOKIE) or request.headers.get('X-Seat-Session')


def get_local_group():
    from core.models import AccessGroup
    ensure_bootstrap_data()
    return AccessGroup.objects.filter(code=LOCAL_GROUP_CODE, is_local=True).first()


def build_local_identity(request) -> dict:
    group = get_local_group()
    perms = permissions_dict_from_group(group) if group else default_local_permissions()
    return {
        'role': 'local',
        'is_local': True,
        'show_logout': bool((perms.get('login_user') or {}).get('display')),
        'label': '',
        'group_id': group.id if group else None,
        'group_code': LOCAL_GROUP_CODE,
        'group_name': group.name if group else '本机用户',
        'user_id': None,
        'require_qr': False,
        'permissions': perms,
        'needs_role_select': False,
        'host_login_ok': True,
    }


def build_identity_from_session(sess: dict, host_login_ok: bool = True) -> dict:
    display_label = sess['group_name']
    if sess.get('require_qr') and sess.get('user_id'):
        display_label = f"{sess['group_name']} {sess['user_id']}"
    perms = sess.get('permissions') or {}
    return {
        'role': 'non_local',
        'is_local': False,
        'show_logout': bool((perms.get('login_user') or {}).get('display')),
        'label': display_label,
        'group_id': sess['group_id'],
        'group_code': sess['group_code'],
        'group_name': sess['group_name'],
        'user_id': sess.get('user_id'),
        'require_qr': sess.get('require_qr', False),
        'permissions': perms,
        'needs_role_select': False,
        'host_login_ok': host_login_ok,
    }


def check_host_login_ok() -> bool:
    """本机调度 token 是否可用：有缓存 token 视为本机已登录过。"""
    try:
        from parsers.scheduler import get_scheduler_token
        return bool(get_scheduler_token())
    except Exception:
        return True


def resolve_access_identity(request) -> dict:
    """统一解析当前访问身份。"""
    ensure_bootstrap_data()
    if is_local_request(request):
        return build_local_identity(request)

    sid = seat_sid_from_request(request)
    sess = get_seat_session(sid)
    host_ok = check_host_login_ok()
    if sess and not sess.get('is_local'):
        from core.models import AccessGroup
        group = AccessGroup.objects.filter(id=sess.get('group_id')).first()
        if group:
            with _lock:
                live = _seat_sessions.get(sid)
                if live:
                    live['permissions'] = permissions_dict_from_group(group)
                    live['require_qr'] = bool(group.require_qr)
                    live['group_name'] = group.name
                    live['group_code'] = group.code
                    sess = dict(live)
        identity = build_identity_from_session(sess, host_login_ok=host_ok)
        return identity

    return {
        'role': 'guest',
        'is_local': False,
        'show_logout': False,
        'label': '',
        'group_id': None,
        'group_code': None,
        'group_name': None,
        'user_id': None,
        'require_qr': False,
        'permissions': {m['code']: empty_perm() for m in ACCESS_MODULES},
        'needs_role_select': True,
        'host_login_ok': host_ok,
    }


def has_perm(identity: dict, module_code: str, action: str) -> bool:
    """action: display | write。显示即可触发该模块的后台解析。"""
    perms = (identity or {}).get('permissions') or {}
    mod = perms.get(module_code) or {}
    visible = bool(mod.get('display') or mod.get('write'))
    if action == 'display':
        return visible
    if action == 'write':
        return visible and bool(mod.get('write'))
    return False


def is_user_blacklisted(user_id: str) -> bool:
    from core.models import NonLocalQrBlacklist
    if not user_id:
        return False
    ensure_access_database()
    return NonLocalQrBlacklist.objects.filter(user_id=str(user_id).strip()).exists()


def validate_group_permission_payload(
    group, perms_payload: dict, is_local_group: bool, require_view: bool = True,
) -> Tuple[bool, str, List[dict]]:
    """校验并规范化权限保存载荷。导入时 require_view=False：新建未配置的组本就没有视图。"""
    rows = []
    displayed = {}
    for m in ACCESS_MODULES:
        code = m['code']
        raw = (perms_payload or {}).get(code) or {}
        can_write = bool(raw.get('write')) and bool(m.get('has_write'))
        if m.get('local_write_only') and not is_local_group:
            can_write = False
        # 勾了写入视为需要显示
        can_display = bool(raw.get('display')) or can_write
        if m.get('parent') and not displayed.get(m['parent']):
            can_display = False
        if not can_display:
            can_write = False
        displayed[code] = can_display
        rows.append({
            'module_code': code,
            'can_display': can_display,
            'can_write': can_write,
        })

    # 视图不得全部关闭，否则该组登录后无处可去
    if require_view and not any(r['can_display'] for r in rows if r['module_code'] in VIEW_MODULE_CODES):
        return False, _VIEW_REQUIRED_MSG, []

    require_qr = bool(getattr(group, 'require_qr', False)) if group else False
    # 写入强制扫码（非本机）
    if not is_local_group:
        any_write = any(r['can_write'] for r in rows)
        if any_write and not require_qr:
            return False, '勾选写入权限时必须同时勾选扫码认证', []

    return True, '', rows


EXPORT_FORMAT = 'fmsa-access-config'
LEGACY_EXPORT_FORMAT = 'mtws-access-config'
EXPORT_VERSION = 1


def new_group_code(name: str) -> str:
    return 'nl_' + re.sub(r'[^a-zA-Z0-9_]', '_', name)[:40] + '_' + uuid.uuid4().hex[:6]


def export_access_config() -> dict:
    """用户组、权限、扫码黑名单导出为可移植的 JSON（不含超管口令）。"""
    from core.models import AccessGroup, NonLocalQrBlacklist

    ensure_bootstrap_data()
    groups = []
    for g in AccessGroup.objects.prefetch_related('permissions').order_by('sort_order', 'id'):
        groups.append({
            'code': g.code,
            'name': g.name,
            'is_local': g.is_local,
            'require_qr': g.require_qr,
            'sort_order': g.sort_order,
            'permissions': permissions_dict_from_group(g),
        })
    blacklist = [
        {'user_id': row.user_id, 'remark': row.remark or ''}
        for row in NonLocalQrBlacklist.objects.order_by('id')
    ]
    return {
        'format': EXPORT_FORMAT,
        'version': EXPORT_VERSION,
        'exported_at': timezone.localtime().isoformat(),
        'groups': groups,
        'blacklist': blacklist,
    }


def import_access_config(payload: dict, mode: str) -> Tuple[bool, str, dict]:
    """导入导出文件。mode=merge 只新增/更新文件里的组和黑名单；
    mode=replace 另外删除文件里没有的非本机组，黑名单整表替换。
    按模块代码匹配，本版本没有的模块忽略，文件里缺的模块视为关闭。"""
    from types import SimpleNamespace

    from django.db import transaction
    from core.models import AccessGroup, AccessGroupPermission, NonLocalQrBlacklist
    from fmsa_system.db_router import ACCESS_DB

    if not isinstance(payload, dict) or payload.get('format') not in (EXPORT_FORMAT, LEGACY_EXPORT_FORMAT):
        return False, '不是用户组配置导出文件', {}
    if mode not in ('merge', 'replace'):
        return False, '导入方式无效', {}
    ensure_bootstrap_data()

    plans = []
    local_done = False
    seen_names = set()
    for item in payload.get('groups') or []:
        if not isinstance(item, dict):
            continue
        is_local = bool(item.get('is_local'))
        name = str(item.get('name') or '').strip()[:100]
        code = str(item.get('code') or '').strip()[:64]
        if is_local:
            if local_done:
                continue
            local_done = True
            group = get_local_group()
        else:
            if not name:
                return False, '文件中有未命名的非本机组', {}
            if name in seen_names:
                return False, f'文件中非本机组「{name}」重名', {}
            seen_names.add(name)
            group = None
            if code:
                group = AccessGroup.objects.filter(code=code, is_local=False).first()
            if not group:
                group = AccessGroup.objects.filter(name=name, is_local=False).first()
        require_qr = False if is_local else bool(item.get('require_qr'))
        ok, msg, rows = validate_group_permission_payload(
            SimpleNamespace(require_qr=require_qr), item.get('permissions') or {},
            is_local_group=is_local, require_view=is_local,
        )
        if not ok:
            return False, f'用户组「{name or "本机用户"}」：{msg}', {}
        try:
            sort_order = int(item.get('sort_order'))
        except (TypeError, ValueError):
            sort_order = 0 if is_local else 100
        plans.append({
            'group': group, 'is_local': is_local, 'name': name, 'code': code,
            'require_qr': require_qr, 'sort_order': sort_order, 'rows': rows,
        })

    blacklist = []
    for item in payload.get('blacklist') or []:
        if not isinstance(item, dict):
            continue
        uid = str(item.get('user_id') or '').strip()[:32]
        if uid and uid not in {b['user_id'] for b in blacklist}:
            blacklist.append({'user_id': uid, 'remark': (str(item.get('remark') or '').strip()[:200]) or None})

    summary = {'created': 0, 'updated': 0, 'deleted': 0, 'blacklist_added': 0}
    with transaction.atomic(using=ACCESS_DB):
        kept_ids = set()
        for plan in plans:
            group = plan['group']
            if group is None:
                code = plan['code']
                if not code or code == LOCAL_GROUP_CODE or AccessGroup.objects.filter(code=code).exists():
                    code = new_group_code(plan['name'])
                group = AccessGroup.objects.create(
                    code=code, name=plan['name'], is_local=False, require_qr=plan['require_qr'],
                    is_builtin=False, sort_order=plan['sort_order'],
                )
                summary['created'] += 1
            else:
                if not plan['is_local']:
                    group.name = plan['name']
                group.require_qr = plan['require_qr']
                group.sort_order = plan['sort_order']
                group.save()
                summary['updated'] += 1
            kept_ids.add(group.id)
            AccessGroupPermission.objects.filter(group=group).delete()
            AccessGroupPermission.objects.bulk_create([
                AccessGroupPermission(group=group, **row) for row in plan['rows']
            ])

        if mode == 'replace':
            stale = AccessGroup.objects.filter(is_local=False, is_builtin=False).exclude(id__in=kept_ids)
            summary['deleted'] = stale.count()
            stale.delete()
            NonLocalQrBlacklist.objects.all().delete()
        existing = set(NonLocalQrBlacklist.objects.values_list('user_id', flat=True))
        new_rows = [NonLocalQrBlacklist(**b) for b in blacklist if b['user_id'] not in existing]
        NonLocalQrBlacklist.objects.bulk_create(new_rows)
        summary['blacklist_added'] = len(new_rows)

    ensure_bootstrap_data()
    return True, '', summary
