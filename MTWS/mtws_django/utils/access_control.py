"""
访问控制：用户组权限、席位会话、超管口令、黑名单。
"""

from __future__ import annotations

import secrets
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone

from utils.popup_utils import get_client_ip, is_loopback_ip

# 模块定义。category 对应管理页四大类；parent 为视图下的子项；
# activate_locked 表示「激活后台」与「显示」同步，管理页不可单独改。
ACCESS_MODULES: List[Dict[str, Any]] = [
    {'code': 'login_user', 'name': '登录的用户/登出按钮', 'category': 'function', 'has_activate': True, 'has_write': False,
     'hint_display': '显示右上角用户与登出', 'hint_activate': '允许点击登出'},
    {'code': 'nwp', 'name': '温度辅助', 'category': 'function', 'has_activate': True, 'has_write': False,
     'hint_display': '显示温度辅助按钮', 'hint_activate': '允许触发温度辅助解析'},
    {'code': 'refresh_btn', 'name': '刷新按钮', 'category': 'function', 'has_activate': True, 'has_write': False,
     'hint_display': '显示刷新按钮', 'hint_activate': '允许触发后台解析刷新'},
    {'code': 'search', 'name': '搜索框和搜索按钮', 'category': 'function', 'has_activate': True, 'has_write': False,
     'hint_display': '显示搜索框和搜索按钮', 'hint_activate': '搜索时可触发解析'},
    {'code': 'settings_btn', 'name': '设置按钮', 'category': 'function', 'has_activate': False, 'has_write': False,
     'hint_display': '显示主页设置按钮'},
    {'code': 'view_home', 'name': '主页', 'category': 'views', 'has_activate': False, 'has_write': False,
     'hint_display': '导航栏显示并可进入列表主页'},
    {'code': 'view_map', 'name': '地图', 'category': 'views', 'has_activate': False, 'has_write': False,
     'hint_display': '导航栏显示并可进入地图模式'},
    {'code': 'map_radar', 'name': '雷达回波与强对流预警', 'category': 'views', 'parent': 'view_map',
     'has_activate': True, 'has_write': True, 'activate_locked': True,
     'hint_display': '地图中显示雷达回波和强对流预警',
     'hint_activate': '与显示同步，不可单独修改',
     'hint_write': '可将雷达告警标为已处理并写库'},
    {'code': 'map_radar_nav', 'name': '导航栏告警数量', 'category': 'views', 'parent': 'view_map',
     'has_activate': False, 'has_write': False,
     'hint_display': '地图导航图标显示未处理雷达告警数量'},
    {'code': 'map_satellite', 'name': '卫星云图', 'category': 'views', 'parent': 'view_map',
     'has_activate': False, 'has_write': False,
     'hint_display': '地图中显示红外、水汽、可见光卫星云图'},
    {'code': 'view_plain', 'name': '翻译', 'category': 'views', 'has_activate': True, 'has_write': False,
     'hint_display': '导航栏显示并可进入中文模式', 'hint_activate': '允许中文模式触发后台解析'},
    {'code': 'view_trend', 'name': '实况趋势', 'category': 'views',
     'has_activate': True, 'has_write': True, 'activate_locked': True,
     'hint_display': '导航栏显示并可进入实况趋势告警',
     'hint_activate': '与显示同步，不可单独修改',
     'hint_write': '可将趋势告警标为已处理并写库'},
    {'code': 'view_trend_nav', 'name': '导航栏告警数量', 'category': 'views', 'parent': 'view_trend',
     'has_activate': False, 'has_write': False,
     'hint_display': '趋势导航图标显示未处理告警数量'},
    {'code': 'import_alert', 'name': '报文入库告警', 'category': 'views',
     'has_activate': True, 'has_write': True, 'activate_locked': True,
     'hint_display': '导航栏显示并可进入报文入库告警',
     'hint_activate': '与显示同步，不可单独修改',
     'hint_write': '可将告警标为已处理并写库'},
    {'code': 'detail_sun_home', 'name': '详情页·主页·日出日落', 'category': 'shared', 'has_activate': False, 'has_write': False,
     'hint_display': '主页模式下详情页显示日出日落'},
    {'code': 'detail_sun_plain', 'name': '详情页·中文·日出日落', 'category': 'shared', 'has_activate': False, 'has_write': False,
     'hint_display': '中文模式下详情页显示日出日落'},
    {'code': 'detail_runway_home', 'name': '详情页·主页·跑道', 'category': 'shared', 'has_activate': False, 'has_write': False,
     'hint_display': '主页模式下详情页显示跑道'},
    {'code': 'detail_runway_plain', 'name': '详情页·中文·跑道', 'category': 'shared', 'has_activate': False, 'has_write': False,
     'hint_display': '中文模式下详情页显示跑道'},
    {'code': 'detail_contact_home', 'name': '详情页·主页·联系方式', 'category': 'shared', 'has_activate': False, 'has_write': False,
     'hint_display': '主页模式下详情页显示联系方式'},
    {'code': 'detail_contact_plain', 'name': '详情页·中文·联系方式', 'category': 'shared', 'has_activate': False, 'has_write': False,
     'hint_display': '中文模式下详情页显示联系方式'},
    {'code': 'detail_metar_trend', 'name': '机场详情页实况趋势', 'category': 'shared', 'has_activate': True, 'has_write': False,
     'hint_display': '详情页显示实况趋势', 'hint_activate': '展开趋势时可触发解析'},
    {'code': 'metar_popup', 'name': '实况弹窗标题及选项', 'category': 'shared', 'has_activate': True, 'has_write': True,
     'hint_display': '显示弹窗及运行/停场等开关', 'hint_activate': '可点忽略/收到/稍后/详情', 'hint_write': '将处理记录写入报文（按用户）'},
    {'code': 'search_sun_home', 'name': '搜索结果·主页·日出日落', 'category': 'shared', 'has_activate': False, 'has_write': False,
     'hint_display': '主页模式下搜索结果展示日出日落'},
    {'code': 'search_sun_plain', 'name': '搜索结果·中文·日出日落', 'category': 'shared', 'has_activate': False, 'has_write': False,
     'hint_display': '中文模式下搜索结果展示日出日落'},
    {'code': 'search_runway_home', 'name': '搜索结果·主页·跑道', 'category': 'shared', 'has_activate': False, 'has_write': False,
     'hint_display': '主页模式下搜索结果展示跑道'},
    {'code': 'search_runway_plain', 'name': '搜索结果·中文·跑道', 'category': 'shared', 'has_activate': False, 'has_write': False,
     'hint_display': '中文模式下搜索结果展示跑道'},
    {'code': 'search_contact_home', 'name': '搜索结果·主页·联系方式', 'category': 'shared', 'has_activate': False, 'has_write': False,
     'hint_display': '主页模式下搜索结果展示联系方式'},
    {'code': 'search_contact_plain', 'name': '搜索结果·中文·联系方式', 'category': 'shared', 'has_activate': False, 'has_write': False,
     'hint_display': '中文模式下搜索结果展示联系方式'},
    {'code': 'settings_airport_info', 'name': '机场信息设置', 'category': 'settings', 'has_activate': False, 'has_write': True, 'settings_write_exclusive': True,
     'hint_display': '设置中显示机场信息', 'hint_write': '可改机场信息（全站仅一组）'},
    {'code': 'settings_area_options', 'name': '区域信息设置', 'category': 'settings', 'has_activate': False, 'has_write': True, 'settings_write_exclusive': True,
     'hint_display': '设置中显示区域信息', 'hint_write': '可改区域选项（全站仅一组）'},
    {'code': 'settings_data_refresh', 'name': '数据更新设置', 'category': 'settings', 'has_activate': False, 'has_write': True, 'settings_write_exclusive': True,
     'hint_display': '设置中显示数据更新', 'hint_write': '可改刷新定时（全站仅一组）'},
    {'code': 'settings_popup', 'name': '弹窗设置', 'category': 'settings', 'has_activate': False, 'has_write': True, 'settings_write_exclusive': True,
     'hint_display': '设置中显示弹窗规则', 'hint_write': '可改等级/余量/追溯时间（全站仅一组）'},
    {'code': 'settings_alert_thresholds', 'name': '告警阈值', 'category': 'settings', 'has_activate': False, 'has_write': True, 'settings_write_exclusive': True,
     'hint_display': '设置中显示告警阈值', 'hint_write': '可改机场告警阈值（全站仅一组）'},
    {'code': 'settings_weather_type', 'name': '天气类型', 'category': 'settings', 'has_activate': False, 'has_write': True, 'settings_write_exclusive': True,
     'hint_display': '设置中显示天气类型', 'hint_write': '可改天气类型（全站仅一组）'},
    {'code': 'settings_weather_alert', 'name': '天气告警等级', 'category': 'settings', 'has_activate': False, 'has_write': True, 'settings_write_exclusive': True,
     'hint_display': '设置中显示天气告警等级', 'hint_write': '可改天气告警等级（全站仅一组）'},
    {'code': 'settings_airport_location', 'name': '机场坐标', 'category': 'settings', 'has_activate': False, 'has_write': True, 'settings_write_exclusive': True,
     'hint_display': '设置中显示机场坐标', 'hint_write': '可改机场坐标（全站仅一组）'},
    {'code': 'settings_radar_alert', 'name': '雷达告警', 'category': 'settings', 'has_activate': False, 'has_write': True, 'settings_write_exclusive': True,
     'hint_display': '设置中显示雷达告警', 'hint_write': '可改雷达告警规则（全站仅一组）'},
    {'code': 'settings_trend_alert', 'name': '实况趋势告警', 'category': 'settings', 'has_activate': False, 'has_write': True, 'settings_write_exclusive': True,
     'hint_display': '设置中显示实况趋势告警', 'hint_write': '可改实况趋势告警规则（全站仅一组）'},
    {'code': 'settings_map_style', 'name': '地图样式', 'category': 'settings', 'has_activate': False, 'has_write': True, 'settings_write_exclusive': True,
     'hint_display': '设置中显示地图样式', 'hint_write': '可改地图样式（全站仅一组）'},
]

MODULE_CATEGORIES = [
    {'code': 'function', 'name': '通用功能区'},
    {'code': 'views', 'name': '视图设置'},
    {'code': 'shared', 'name': '通用功能'},
    {'code': 'settings', 'name': '设置选项'},
]

MODULE_BY_CODE = {m['code']: m for m in ACCESS_MODULES}
SETTINGS_WRITE_EXCLUSIVE = {m['code'] for m in ACCESS_MODULES if m.get('settings_write_exclusive')}

# 导航视图，顺序即无权限回落的优先级（导航栏顺序另见 views_nav.js）
VIEW_MODULE_CODES = ('view_home', 'view_map', 'view_plain', 'view_trend', 'import_alert')
_VIEW_REQUIRED_MSG = '主页、地图、翻译、实况趋势、报文入库告警至少需要保留一个显示权限'

LOCAL_GROUP_CODE = 'local'
SUPERUSER_CONFIG_TYPE = 'access_control'
SUPERUSER_CONFIG_KEY = 'superuser_password_hash'
DEFAULT_SUPERUSER_PASSWORD = 'admin2026'

SEAT_COOKIE = 'mtws_seat_sid'
ADMIN_COOKIE = 'mtws_admin_sid'
SEAT_TTL_SECONDS = 12 * 3600
ADMIN_TTL_SECONDS = 30 * 60

# 设置子页写入权限 → settings API 模块码
SETTINGS_MODULE_MAP = {
    'airport_info': 'settings_airport_info',
    'area_options': 'settings_area_options',
    'data_refresh': 'settings_data_refresh',
    'popup': 'settings_popup',
    'alert_thresholds': 'settings_alert_thresholds',
    'weather_type': 'settings_weather_type',
    'weather_alert': 'settings_weather_alert',
    'airport_location': 'settings_airport_location',
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


def empty_perm(can_activate: bool = False, can_write: bool = False) -> dict:
    return {'display': False, 'activate': False, 'write': False}


def full_perm(module_code: str) -> dict:
    meta = MODULE_BY_CODE.get(module_code, {})
    return {
        'display': True,
        'activate': bool(meta.get('has_activate', False)),
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
        meta = MODULE_BY_CODE.get(row.module_code) or {}
        displayed = bool(row.can_display)
        if meta.get('activate_locked'):
            activated = displayed and bool(meta.get('has_activate'))
        else:
            activated = bool(row.can_activate) if meta.get('has_activate') else False
        result[row.module_code] = {
            'display': displayed,
            'activate': activated,
            'write': bool(row.can_write) if meta.get('has_write') else False,
        }
    return result


def ensure_bootstrap_data():
    """确保本机组、出厂权限、超管口令哈希存在。"""
    from core.models import AccessGroup, AccessGroupPermission, SystemConfig

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
                can_activate=bool(m.get('has_activate')),
                can_write=bool(m.get('has_write')),
            ))
        AccessGroupPermission.objects.bulk_create(bulk)
    else:
        # 本机组补齐后续新增模块，并同步锁定激活项
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
                    can_activate=bool(m.get('has_activate')),
                    can_write=bool(m.get('has_write')),
                ))
                continue
            if m.get('activate_locked') and row.can_activate != row.can_display:
                row.can_activate = bool(row.can_display)
                row.save(update_fields=['can_activate'])
            # 本机组对锁定激活且可写模块，显示开启时补齐写入
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
        AccessGroupPermission.objects.filter(
            group=group
        ).exclude(module_code__in=MODULE_BY_CODE.keys()).delete()

    exists = SystemConfig.objects.filter(
        config_type=SUPERUSER_CONFIG_TYPE, config_key=SUPERUSER_CONFIG_KEY
    ).exists()
    if not exists:
        SystemConfig.objects.create(
            config_type=SUPERUSER_CONFIG_TYPE,
            config_key=SUPERUSER_CONFIG_KEY,
            config_value=make_password(DEFAULT_SUPERUSER_PASSWORD),
            description='超级用户口令哈希',
        )


def get_superuser_hash() -> str:
    from core.models import SystemConfig
    ensure_bootstrap_data()
    row = SystemConfig.objects.filter(
        config_type=SUPERUSER_CONFIG_TYPE, config_key=SUPERUSER_CONFIG_KEY
    ).first()
    return row.config_value if row else ''


def set_superuser_password(raw_password: str) -> None:
    from core.models import SystemConfig
    SystemConfig.objects.update_or_create(
        config_type=SUPERUSER_CONFIG_TYPE,
        config_key=SUPERUSER_CONFIG_KEY,
        defaults={
            'config_value': make_password(raw_password),
            'description': '超级用户口令哈希',
        },
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
            'expires': _now() + ADMIN_TTL_SECONDS,
        }
    return sid


def touch_admin_session(sid: str) -> bool:
    with _lock:
        sess = _admin_sessions.get(sid)
        if not sess:
            return False
        if sess['expires'] < _now():
            _admin_sessions.pop(sid, None)
            return False
        sess['expires'] = _now() + ADMIN_TTL_SECONDS
        return True


def clear_admin_session(sid: Optional[str]) -> None:
    if not sid:
        return
    with _lock:
        _admin_sessions.pop(sid, None)


def is_admin_unlocked(request) -> bool:
    if not is_local_request(request):
        return False
    sid = request.COOKIES.get(ADMIN_COOKIE) or request.headers.get('X-Admin-Session')
    if not sid:
        return False
    return touch_admin_session(sid)


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
    return request.COOKIES.get(SEAT_COOKIE) or request.headers.get('X-Seat-Session')


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
        'show_logout': True,
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
    return {
        'role': 'non_local',
        'is_local': False,
        'show_logout': True,
        'label': display_label,
        'group_id': sess['group_id'],
        'group_code': sess['group_code'],
        'group_name': sess['group_name'],
        'user_id': sess.get('user_id'),
        'require_qr': sess.get('require_qr', False),
        'permissions': sess.get('permissions') or {},
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
    """action: display | activate | write"""
    perms = (identity or {}).get('permissions') or {}
    mod = perms.get(module_code) or {}
    visible = bool(mod.get('display') or mod.get('activate') or mod.get('write'))
    if action == 'display':
        return visible
    if action == 'activate':
        return visible and bool(mod.get('activate'))
    if action == 'write':
        return visible and bool(mod.get('write'))
    return False


def is_user_blacklisted(user_id: str) -> bool:
    from core.models import NonLocalQrBlacklist
    if not user_id:
        return False
    return NonLocalQrBlacklist.objects.filter(user_id=str(user_id).strip()).exists()


def validate_group_permission_payload(group, perms_payload: dict, is_local_group: bool) -> Tuple[bool, str, List[dict]]:
    """校验并规范化权限保存载荷。"""
    rows = []
    for m in ACCESS_MODULES:
        code = m['code']
        raw = (perms_payload or {}).get(code) or {}
        can_display = bool(raw.get('display'))
        can_activate = bool(raw.get('activate')) if m.get('has_activate') else False
        can_write = bool(raw.get('write')) if m.get('has_write') else False
        # 勾了激活/写入视为需要显示对应模块。锁定项的激活由显示决定，不反向打开显示。
        if m.get('activate_locked'):
            can_activate = False
        if can_activate or can_write:
            can_display = True
        if not can_display:
            can_activate = False
            can_write = False
        if m.get('activate_locked'):
            can_activate = can_display and bool(m.get('has_activate'))
        elif can_activate and not m.get('has_activate'):
            can_activate = False
        if can_write and not m.get('has_write'):
            can_write = False
        rows.append({
            'module_code': code,
            'can_display': can_display,
            'can_activate': can_activate,
            'can_write': can_write,
        })

    # 三个显示视图不得全部关闭，否则该组登录后无处可去
    if not any(r['can_display'] for r in rows if r['module_code'] in VIEW_MODULE_CODES):
        return False, _VIEW_REQUIRED_MSG, []

    require_qr = bool(getattr(group, 'require_qr', False)) if group else False
    # 写入强制扫码（非本机）
    if not is_local_group:
        any_write = any(r['can_write'] for r in rows)
        if any_write and not require_qr:
            return False, '勾选写入权限时必须同时勾选扫码认证', []

    # 设置项写入互斥
    from core.models import AccessGroupPermission
    for r in rows:
        if not r['can_write']:
            continue
        if r['module_code'] not in SETTINGS_WRITE_EXCLUSIVE:
            continue
        qs = AccessGroupPermission.objects.filter(
            module_code=r['module_code'], can_write=True
        )
        if group and group.id:
            qs = qs.exclude(group_id=group.id)
        other = qs.select_related('group').first()
        if other:
            name = MODULE_BY_CODE[r['module_code']]['name']
            return False, (
                f'模块「{name}」的写入权限已授予用户组「{other.group.name}」，请先取消后再授权'
            ), []

    return True, '', rows
