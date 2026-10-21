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

# 可勾选模块。nwp 挂在主页下，不单独计入「至少勾选 1 个」。
OPTIONAL_KEYS = (
    'home',
    'plain',
    'popup',
    'import_alert',
    'trend',
    'radar',
    'satellite',
    'awc',
    'contact',
)

MODULE_META = [
    {
        'key': 'core',
        'name': '核心数据组',
        'locked': True,
        'data': '获取实况、预报、航班、停场，四类捆绑入库，不能取消。地图上的机场也来自这组数据。',
        'writes': '程序入库。人的处置无。配置：数据更新、机场信息、机场区域、天气类型、告警阈值、天气告警等级。',
    },
    {
        'key': 'home',
        'name': '主页视图',
        'locked': False,
        'data': '不另取数据，展示核心数据。',
        'writes': '写入无。',
    },
    {
        'key': 'nwp',
        'name': 'NWP 温度',
        'locked': False,
        'parent': 'home',
        'data': '主页附加。获取 open-meteo 温度，只留在内存。主页未勾时不能单独勾。',
        'writes': '人不写入。缺坐标时可能写回机场坐标。配置无。',
    },
    {
        'key': 'plain',
        'name': '翻译视图',
        'locked': False,
        'data': '不另取数据，展示核心报文的中文。',
        'writes': '写入无，配置无。',
    },
    {
        'key': 'popup',
        'name': '实况弹窗',
        'locked': False,
        'data': '用核心实况、航班和停场规则计算运行类、停场类。',
        'writes': '程序写入弹窗状态。人用本次登录的工号写处理记录。配置：弹窗设置。',
    },
    {
        'key': 'import_alert',
        'name': '入库告警',
        'locked': False,
        'data': '检查实况、预报是否按时入库。',
        'writes': '程序打告警标记。人标已处理。配置：预报入库告警。',
    },
    {
        'key': 'trend',
        'name': '实况趋势',
        'locked': False,
        'data': '对实况再计算。',
        'writes': '程序写入趋势结果。人标已处理。配置：实况趋势告警。',
    },
    {
        'key': 'radar',
        'name': '雷达',
        'locked': False,
        'data': '获取雷达回波并做反演。',
        'writes': '程序写入告警。人标已处理。配置：雷达告警。显示在地图图层和导航数量。',
    },
    {
        'key': 'satellite',
        'name': '卫星云图',
        'locked': False,
        'data': '浏览器直接取葵花红外、水汽、可见光。服务器不入库。',
        'writes': '写入无，配置无。显示在地图图层。',
    },
    {
        'key': 'awc',
        'name': 'AWC 机场资料',
        'locked': False,
        'data': '按需查询坐标、跑道、日出日落。',
        'writes': '缺坐标时写回机场坐标。配置无，机场信息编辑仍在核心里。',
    },
    {
        'key': 'contact',
        'name': '其他',
        'locked': False,
        'data': '只控制联系方式是否在详情和搜索中展示。',
        'writes': '写入无。不勾时展示位置隐藏。机场信息设置里的电话字段仍可编辑。',
    },
]


def default_modules() -> Dict[str, bool]:
    data = {CORE_KEY: True}
    for key in OPTIONAL_KEYS:
        data[key] = True
    data['nwp'] = True
    return data


def _normalize(raw: dict) -> Dict[str, bool]:
    base = default_modules()
    if isinstance(raw, dict):
        src = raw.get('modules') if isinstance(raw.get('modules'), dict) else raw
        if isinstance(src, dict):
            for key in list(base.keys()):
                if key in src:
                    base[key] = bool(src[key])
    base[CORE_KEY] = True
    if not base.get('home'):
        base['nwp'] = False
    return base


_cache_mtime: float | None = None
_cache_data: Dict[str, bool] | None = None


def load_modules() -> Dict[str, bool]:
    """文件不存在或损坏时按全部启用，避免主程序空转却没有界面。"""
    global _cache_mtime, _cache_data
    try:
        mtime = PROFILE_PATH.stat().st_mtime
    except OSError:
        return default_modules()
    if _cache_data is not None and _cache_mtime == mtime:
        return dict(_cache_data)
    try:
        payload = json.loads(PROFILE_PATH.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return default_modules()
    if not isinstance(payload, dict):
        return default_modules()
    data = _normalize(payload)
    _cache_mtime = mtime
    _cache_data = data
    return dict(data)


def module_enabled(key: str) -> bool:
    modules = load_modules()
    if key == 'nwp':
        return bool(modules.get('home')) and bool(modules.get('nwp'))
    if key == CORE_KEY:
        return True
    return bool(modules.get(key))


def validate_selection(modules: Dict[str, bool]) -> str:
    """返回错误说明。空字符串表示可以保存。"""
    chosen = _normalize({'modules': modules})
    if not any(chosen.get(key) for key in OPTIONAL_KEYS):
        return '至少勾选 1 个模块'
    return ''


def save_modules(modules: Dict[str, bool]) -> str:
    """校验后原子写入。成功返回空字符串。"""
    message = validate_selection(modules)
    if message:
        return message
    chosen = _normalize({'modules': modules})
    payload = {
        'version': 1,
        'modules': chosen,
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
    global _cache_mtime, _cache_data
    _cache_mtime = None
    _cache_data = None
    return ''


def permissions_for_runtime() -> Dict[str, dict]:
    """把模块开关翻成页面原来使用的显示/写入表。开了的模块两端权限相同。"""
    on = load_modules()

    def flag(enabled: bool) -> dict:
        return {'display': enabled, 'write': enabled}

    always = flag(True)
    home = flag(bool(on.get('home')))
    nwp = flag(bool(on.get('home')) and bool(on.get('nwp')))
    plain = flag(bool(on.get('plain')))
    popup = flag(bool(on.get('popup')))
    imported = flag(bool(on.get('import_alert')))
    trend = flag(bool(on.get('trend')))
    radar = flag(bool(on.get('radar')))
    satellite = flag(bool(on.get('satellite')))
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
        'view_map': always,
        'map_radar': radar,
        'map_radar_nav': radar,
        'map_satellite': satellite,
        'view_plain': plain,
        'view_trend': trend,
        'view_trend_nav': trend,
        'import_alert': imported,
        'detail_contact_home': contact,
        'detail_contact_plain': contact,
        'search_contact_home': contact,
        'search_contact_plain': contact,
        'detail_metar_trend': trend,
        'settings_airport_info': always,
        'settings_prefix_area': always,
        'settings_taf_import': imported,
        'settings_data_refresh': always,
        'settings_popup': popup,
        'settings_alert_thresholds': always,
        'settings_weather_type': always,
        'settings_weather_alert': always,
        'settings_radar_alert': radar,
        'settings_trend_alert': trend,
        'settings_map_style': always,
        'unused': off,
    }
