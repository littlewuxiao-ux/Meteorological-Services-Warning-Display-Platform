"""
本机模块开关。配置程序写入 data/fmsa_modules.json，主程序启动后只读这一份。
与用户配置库、生产库、超级用户口令库分开。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Dict

# fmsa_django/utils/module_profile.py -> 项目根目录
_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = _ROOT / 'data' / 'fmsa_modules.json'

# 核心四类捆绑，不能关。
CORE_KEY = 'core'

# 可勾选模块。nwp 挂在主页下；雷达/卫星由地图视图带动，均不单独计入「至少勾选 1 个」。
OPTIONAL_KEYS = (
    'home',
    'map',
    'plain',
    'trend',
    'import_alert',
    'popup',
    'awc',
    'contact',
)

# 机场详情、搜索结果用原文还是中文。与视图勾选分开。
REPORT_LANG_ORIGINAL = 'original'  # 原文优先：仅翻译视图显示中文
REPORT_LANG_CHINESE = 'chinese'    # 中文优先：仅主页视图显示原文

MODULE_GROUPS = (
    ('base', '基础类'),
    ('view', '视图类'),
    ('general', '设置通用类'),
)

MODULE_META = [
    {
        'key': 'core',
        'group': 'base',
        'name': '核心数据组',
        'locked': True,
        'data': '获取实况、预报、航班、停场，四类捆绑入库。地图上的机场也来自这组。',
        'program': '入库',
        'human': '无',
        'config': '数据更新、机场信息、机场区域、天气类型、告警阈值、天气告警等级',
    },
    {
        'key': 'home',
        'group': 'view',
        'name': '主页视图',
        'locked': False,
        'data': '不另取数据，用核心数据做列表展示。',
        'program': '无',
        'human': '无',
        'config': '无',
    },
    {
        'key': 'nwp',
        'group': 'view',
        'name': 'NWP 温度',
        'locked': False,
        'parent': 'home',
        'data': '主页附加。取 open-meteo 温度，只留内存。主页未勾时不能单独勾。',
        'program': '缺坐标时可能写回机场坐标',
        'human': '无',
        'config': '无',
    },
    {
        'key': 'map',
        'group': 'view',
        'name': '地图视图',
        'locked': False,
        'data': '用地图展示核心机场。勾选后同时启用雷达回波、卫星云图图层，不再单独开关。',
        'program': '雷达告警',
        'human': '雷达告警标已处理',
        'config': '雷达告警、地图样式',
    },
    {
        'key': 'plain',
        'group': 'view',
        'name': '翻译视图',
        'locked': False,
        'data': '不另取数据，列表展示核心报文的中文。',
        'program': '无',
        'human': '无',
        'config': '无',
    },
    {
        'key': 'trend',
        'group': 'view',
        'name': '实况趋势',
        'locked': False,
        'data': '对实况再计算，导航进入趋势视图。',
        'program': '趋势结果',
        'human': '标已处理',
        'config': '实况趋势告警',
    },
    {
        'key': 'import_alert',
        'group': 'view',
        'name': '入库告警',
        'locked': False,
        'data': '检查实况、预报是否按时入库，导航进入入库视图。',
        'program': '告警标记',
        'human': '标已处理',
        'config': '预报入库告警',
    },
    {
        'key': 'popup',
        'group': 'general',
        'name': '实况弹窗',
        'locked': False,
        'data': '用核心实况、航班和停场规则计算运行类、停场类。',
        'program': '弹窗状态',
        'human': '用本次登录工号写处理记录',
        'config': '弹窗设置',
    },
    {
        'key': 'awc',
        'group': 'general',
        'name': 'AWC 机场资料',
        'locked': False,
        'data': '按需查询坐标、跑道、日出日落。',
        'program': '缺坐标时写回机场坐标',
        'human': '无',
        'config': '无（机场信息编辑仍在核心里）',
    },
    {
        'key': 'contact',
        'group': 'general',
        'name': '联系方式',
        'locked': False,
        'data': '控制联系方式是否在详情和搜索中展示。不勾时隐藏展示位置。',
        'program': '无',
        'human': '无',
        'config': '无（机场信息里的电话仍可编辑）',
    },
]


def default_modules() -> Dict[str, bool]:
    data = {CORE_KEY: True}
    for key in OPTIONAL_KEYS:
        data[key] = True
    data['nwp'] = True
    data['radar'] = True
    data['satellite'] = True
    return data


def default_options() -> Dict[str, str]:
    return {'report_lang': REPORT_LANG_ORIGINAL}


def _normalize(raw: dict) -> Dict[str, bool]:
    base = default_modules()
    src = {}
    if isinstance(raw, dict):
        src = raw.get('modules') if isinstance(raw.get('modules'), dict) else raw
        if not isinstance(src, dict):
            src = {}
        for key in list(base.keys()):
            if key in src:
                base[key] = bool(src[key])
        if 'map' not in src:
            base['map'] = bool(src.get('radar', True)) or bool(src.get('satellite', True))
    base[CORE_KEY] = True
    if not base.get('home'):
        base['nwp'] = False
    base['radar'] = bool(base.get('map'))
    base['satellite'] = bool(base.get('map'))
    return base


def _normalize_options(raw) -> Dict[str, str]:
    base = default_options()
    if not isinstance(raw, dict):
        return base
    lang = raw.get('report_lang')
    if lang in (REPORT_LANG_ORIGINAL, REPORT_LANG_CHINESE):
        base['report_lang'] = lang
    return base


_cache_mtime: float | None = None
_cache_profile: dict | None = None


def _default_profile() -> dict:
    return {'modules': default_modules(), 'options': default_options()}


def load_profile() -> dict:
    """文件不存在或损坏时按全部启用 + 原文优先。"""
    global _cache_mtime, _cache_profile
    try:
        mtime = PROFILE_PATH.stat().st_mtime
    except OSError:
        return _default_profile()
    if _cache_profile is not None and _cache_mtime == mtime:
        return {
            'modules': dict(_cache_profile['modules']),
            'options': dict(_cache_profile['options']),
        }
    try:
        payload = json.loads(PROFILE_PATH.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return _default_profile()
    if not isinstance(payload, dict):
        return _default_profile()
    data = _normalize(payload)
    options = _normalize_options(payload.get('options'))
    _cache_mtime = mtime
    _cache_profile = {'modules': data, 'options': options}
    return {'modules': dict(data), 'options': dict(options)}


def load_modules() -> Dict[str, bool]:
    return load_profile()['modules']


def load_options() -> Dict[str, str]:
    return load_profile()['options']


def report_lang() -> str:
    return load_options().get('report_lang') or REPORT_LANG_ORIGINAL


def module_enabled(key: str) -> bool:
    modules = load_modules()
    if key == 'nwp':
        return bool(modules.get('home')) and bool(modules.get('nwp'))
    if key in ('radar', 'satellite'):
        return bool(modules.get('map'))
    if key == CORE_KEY:
        return True
    return bool(modules.get(key))


def validate_selection(modules: Dict[str, bool]) -> str:
    """返回错误说明。空字符串表示可以保存。"""
    chosen = _normalize({'modules': modules})
    if not any(chosen.get(key) for key in OPTIONAL_KEYS):
        return '至少勾选 1 个模块'
    return ''


def save_profile(modules: Dict[str, bool], options=None) -> str:
    """校验后原子写入。成功返回空字符串。"""
    message = validate_selection(modules)
    if message:
        return message
    chosen = _normalize({'modules': modules})
    chosen_options = _normalize_options(options if options is not None else default_options())
    payload = {
        'version': 1,
        'modules': chosen,
        'options': chosen_options,
    }
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(PROFILE_PATH.parent), suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.write('\n')
        os.replace(tmp_name, PROFILE_PATH)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    global _cache_mtime, _cache_profile
    _cache_mtime = None
    _cache_profile = None
    return ''


def save_modules(modules: Dict[str, bool]) -> str:
    return save_profile(modules, load_options())


def permissions_for_runtime() -> Dict[str, dict]:
    """把模块开关翻成页面原来使用的显示/写入表。开了的模块两端权限相同。"""
    on = load_modules()

    def flag(enabled: bool) -> dict:
        return {'display': enabled, 'write': enabled}

    always = flag(True)
    home = flag(bool(on.get('home')))
    nwp = flag(bool(on.get('home')) and bool(on.get('nwp')))
    mapped = flag(bool(on.get('map')))
    plain = flag(bool(on.get('plain')))
    popup = flag(bool(on.get('popup')))
    imported = flag(bool(on.get('import_alert')))
    trend = flag(bool(on.get('trend')))
    contact = flag(bool(on.get('contact')))
    off = flag(False)

    return {
        'login_user': always,
        'nwp': nwp,
        'refresh_btn': always,
        'search': always,
        'settings_btn': always,
        'metar_popup': popup,
        'view_home': home,
        'view_map': mapped,
        'map_radar': mapped,
        'map_radar_nav': mapped,
        'map_satellite': mapped,
        'view_plain': plain,
        'view_trend': trend,
        'view_trend_nav': trend,
        'import_alert': imported,
        'detail_contact_home': contact,
        'detail_contact_plain': contact,
        'search_contact_home': contact,
        'search_contact_plain': contact,
        'detail_metar_trend': always,
        'settings_airport_info': always,
        'settings_prefix_area': always,
        'settings_taf_import': imported,
        'settings_data_refresh': always,
        'settings_popup': popup,
        'settings_alert_thresholds': always,
        'settings_weather_type': always,
        'settings_weather_alert': always,
        'settings_radar_alert': mapped,
        'settings_trend_alert': trend,
        'settings_map_style': mapped,
        'unused': off,
    }
