
import re
import pandas as pd
from flask import Flask, request, jsonify, send_from_directory
from datetime import datetime, timedelta, timezone
import traceback
import os
import sys
import time
import threading
import copy
import json
import logging
import requests

# Nginx 统一登录态由前端通过 /auth/status 管理；业务接口优先使用前端请求传入的 token，
# 前端未传时（例如未来新增无前端定时任务）回退查询 AuthBroker 统一登录态。


def resolve_auth_token(provided_token=None):
    """业务接口使用前端传入的 token；前端未传时回退查询统一登录态 AuthBroker。"""
    if provided_token:
        return provided_token
    try:
        from .logic.auth_broker_client import get_token_from_broker
    except ImportError:
        from logic.auth_broker_client import get_token_from_broker
    # 处于实时请求路径中，只查询一次，避免重试阻塞前端请求
    token, _user_code, _reachable = get_token_from_broker(retry_times=1)
    return token

def _persistent_base_dir():
    """运行时可写配置的持久目录。
    🌟 修复“配置一段时间后还原”：frozen 后不能用 __file__（指向 bundle 内部，
    onefile 是临时目录会被清理，onedir 是 _internal 重装/更新会被覆盖）。
    改为写在 exe 同级目录（持久）。源码模式保持原来的 backend 上级目录。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


def _bundle_resource_dir():
    """只读资源（打包进包的模板）目录。frozen 时为 _MEIPASS。"""
    if getattr(sys, 'frozen', False):
        return getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


_PERSIST_DIR = _persistent_base_dir()
_BUNDLE_DIR = _bundle_resource_dir()

PERSONNEL_MAP_PATH = os.path.join(_PERSIST_DIR, 'personnel_mapping.json')
SETTINGS_CONFIG_PATH = os.path.join(_PERSIST_DIR, 'runtime', 'settings_config.json')
# 模板优先找持久目录，再找打包进包的只读资源目录
_SETTINGS_EXAMPLE_PERSIST = os.path.join(_PERSIST_DIR, 'runtime', 'settings_config.example.json')
_SETTINGS_EXAMPLE_BUNDLE = os.path.join(_BUNDLE_DIR, 'runtime', 'settings_config.example.json')
SETTINGS_CONFIG_EXAMPLE_PATH = _SETTINGS_EXAMPLE_PERSIST if os.path.exists(_SETTINGS_EXAMPLE_PERSIST) else _SETTINGS_EXAMPLE_BUNDLE
# 🌟 配置持久化根治（方案A）：统一配置源迁移到 omics_config.js。
# 该文件同时被浏览器以 <script> 同步加载（window.OMICS_CONFIG）和后端读写，
# 成为唯一数据源，彻底摆脱对浏览器 localStorage 的依赖。
# 放在持久化 runtime 目录（frozen 后为 exe 同级），并通过显式路由 /omics_config.js 提供给前端，
# 保证打包模式下前端拿到的也是持久副本。
OMICS_CONFIG_JS_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'runtime', 'omics_config.js'))
if getattr(sys, 'frozen', False):
    OMICS_CONFIG_JS_PATH = os.path.join(_PERSIST_DIR, 'runtime', 'omics_config.js')
_SETTINGS_WRITE_LOCK = threading.RLock()
DEFAULT_PERSONNEL_MAP = {"41060711": "吴霄"}
CURRENT_SETTINGS_SCHEMA_VERSION = 4

DEFAULT_SETTINGS_CONFIG = {
    "schema_version": CURRENT_SETTINGS_SCHEMA_VERSION,
    "personnel_dict": dict(DEFAULT_PERSONNEL_MAP),
    "paths": {
        "taf_excel_path": "",
        "manual_excel_path": "",
        "manual_forecast_path": "",
        "backup_save_path": ""
    },
    "default_airports": {
        "manual": "ZBAA ZGSZ ZHEC ZSHC",
        "taf": "ZHEC"
    },
    "phenomena_config": {
        "雷雨类": ["TSRA"],
        "积冰类": ["FZDZ", "FZRA", "SN", "SG", "PL"],
        "强降水(无雷)类": ["RA", "SHRA"],
        "特殊类": ["GR", "GS", "FC", "SQ"]
    },
    "thresholds": {
        "global": {
            "vis_takeoff": 400,
            "vis_landing": 800,
            "vis_warning": 1000,
            "cld_takeoff": 60,
            "cld_landing": 60,
            "cld_warning": 90,
            "wind_warning": 17
        },
        "custom_airports": {}
    },
    "publish": {
        "airport_groups": [],
        "auto_ec_cfg": {
            "highTemp": 33,
            "groundIceTemp": 10,
            "groundIceDewPointDiff": 0,
            "groundIceVisibility": 1500,
            "precipHours": 12,
            "extremeColdTemp": -30
        },
        "display_elements": {
            "wind": True,
            "visibility": True,
            "weather": True,
            "temperature": True,
            "pressure": True
        }
    }
}


def deep_merge_dict(base, extra):
    """Return a recursive merge without mutating inputs."""
    merged = copy.deepcopy(base)
    if not isinstance(extra, dict):
        return merged
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def upgrade_settings_config(config):
    """Apply one-time defaults that cannot be expressed by a normal deep merge."""
    upgraded = copy.deepcopy(config) if isinstance(config, dict) else {}
    try:
        saved_version = int(upgraded.get("schema_version", 0) or 0)
    except (TypeError, ValueError):
        saved_version = 0
    if saved_version < 2:
        upgraded = deep_merge_dict(upgraded, {
            "publish": {"display_elements": {"pressure": True}}
        })
    if saved_version < 3:
        old_ec = upgraded.get("publish", {}).get("auto_ec_cfg", {})
        ec_defaults = copy.deepcopy(DEFAULT_SETTINGS_CONFIG["publish"]["auto_ec_cfg"])
        if isinstance(old_ec, dict):
            if "iceTemp" in old_ec:
                ec_defaults["groundIceTemp"] = old_ec["iceTemp"]
            if "iceVis" in old_ec:
                ec_defaults["groundIceVisibility"] = old_ec["iceVis"]
            if "iceDew" in old_ec:
                ec_defaults["groundIceDewPointDiff"] = old_ec["iceDew"]
            if "extCold" in old_ec:
                ec_defaults["extremeColdTemp"] = old_ec["extCold"]
            ec_defaults = deep_merge_dict(ec_defaults, old_ec)
        upgraded = deep_merge_dict(upgraded, {"publish": {"auto_ec_cfg": ec_defaults}})
    if saved_version < 4:
        old_ec = upgraded.get("publish", {}).get("auto_ec_cfg", {})
        ec_defaults = copy.deepcopy(DEFAULT_SETTINGS_CONFIG["publish"]["auto_ec_cfg"])
        if isinstance(old_ec, dict):
            if "iceDew" in old_ec and "groundIceDewPointDiff" not in old_ec:
                old_ec["groundIceDewPointDiff"] = old_ec["iceDew"]
            ec_defaults = deep_merge_dict(ec_defaults, old_ec)
        upgraded = deep_merge_dict(upgraded, {"publish": {"auto_ec_cfg": ec_defaults}})
    upgraded["schema_version"] = CURRENT_SETTINGS_SCHEMA_VERSION
    return upgraded


def _serialize_config_js(config):
    """把配置字典序列化成浏览器可同步加载的 JS 文件文本。"""
    payload = json.dumps(config, ensure_ascii=False, indent=2)
    return (
        "// 🌟 OMICS 统一配置文件（唯一数据源）——由系统自动读写，请勿手工编辑格式。\n"
        "// 浏览器以 <script> 同步加载 window.OMICS_CONFIG；后端 /api/settings_config 读写此文件。\n"
        "window.OMICS_CONFIG = " + payload + ";\n"
    )


def _parse_config_js(text):
    """从 omics_config.js 文本中提取 JSON 配置对象。"""
    if not text:
        return None
    # 截取 window.OMICS_CONFIG = {...}; 中的 JSON 主体。
    eq = text.find('=', text.find('OMICS_CONFIG'))
    if eq == -1:
        return None
    start = text.find('{', eq)
    end = text.rfind('}')
    if start == -1 or end == -1 or end < start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except Exception as exc:
        LOG.warning("解析 omics_config.js 失败: %s", exc)
        return None


def _write_config_js(config):
    os.makedirs(os.path.dirname(OMICS_CONFIG_JS_PATH), exist_ok=True)
    temp_path = OMICS_CONFIG_JS_PATH + '.tmp'
    with open(temp_path, 'w', encoding='utf-8') as f:
        f.write(_serialize_config_js(config))
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp_path, OMICS_CONFIG_JS_PATH)


def _read_legacy_json_config():
    """一次性迁移：读取旧的 settings_config.json / example 作为初始值。"""
    for path in (SETTINGS_CONFIG_PATH, SETTINGS_CONFIG_EXAMPLE_PATH):
        try:
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as exc:
            LOG.warning("读取旧配置 %s 失败: %s", path, exc)
    return None


def _read_config_js_raw():
    """读取 omics_config.js 中已存的配置字典（不叠加默认值）。"""
    try:
        if os.path.exists(OMICS_CONFIG_JS_PATH):
            with open(OMICS_CONFIG_JS_PATH, 'r', encoding='utf-8') as f:
                return _parse_config_js(f.read())
    except Exception as exc:
        LOG.warning("读取 omics_config.js 失败: %s", exc)
    return None


def load_settings_config():
    data = copy.deepcopy(DEFAULT_SETTINGS_CONFIG)
    # Keep backward compatibility with the older standalone personnel mapping file.
    data["personnel_dict"] = deep_merge_dict(data.get("personnel_dict", {}), load_personnel_mapping())
    saved = _read_config_js_raw()
    if saved is None:
        # 🌟 首次运行 / 旧版本升级：从旧 settings_config.json 迁移到 omics_config.js。
        legacy = _read_legacy_json_config()
        if legacy is not None:
            data = deep_merge_dict(data, upgrade_settings_config(legacy))
        try:
            _write_config_js(data)
        except Exception as exc:
            LOG.warning("初始化 omics_config.js 失败: %s", exc)
        return data
    upgraded_saved = upgrade_settings_config(saved)
    if upgraded_saved != saved:
        try:
            _write_config_js(upgraded_saved)
        except Exception as exc:
            LOG.warning("升级 omics_config.js 失败: %s", exc)
    saved = upgraded_saved
    data = deep_merge_dict(data, saved)
    return data


def save_settings_config(settings, replace=False):
    # 🌟 健壮性：以 默认 -> 磁盘已存 -> 本次传入 的顺序逐层叠加，
    # 避免某次只传部分字段的 sync 把磁盘上其他已保存配置抹掉。
    with _SETTINGS_WRITE_LOCK:
        data = copy.deepcopy(DEFAULT_SETTINGS_CONFIG)
        saved = _read_config_js_raw()
        if saved is None:
            # 尚未生成 JS 配置时，先把旧 JSON 迁移进来作为基底，避免覆盖历史配置。
            legacy = _read_legacy_json_config()
            if legacy is not None:
                data = deep_merge_dict(data, upgrade_settings_config(legacy))
        else:
            data = deep_merge_dict(data, upgrade_settings_config(saved))
        if replace:
            data = copy.deepcopy(DEFAULT_SETTINGS_CONFIG)
        data = deep_merge_dict(data, settings if isinstance(settings, dict) else {})
        data["schema_version"] = CURRENT_SETTINGS_SCHEMA_VERSION
        # Also keep personnel_mapping.json in sync for launcher/legacy readers.
        if isinstance(data.get("personnel_dict"), dict):
            save_personnel_mapping(data["personnel_dict"])
        _write_config_js(data)
        return data


def load_personnel_mapping():
    data = dict(DEFAULT_PERSONNEL_MAP)
    try:
        if os.path.exists(PERSONNEL_MAP_PATH):
            with open(PERSONNEL_MAP_PATH, 'r', encoding='utf-8') as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                data.update({str(k): str(v) for k, v in saved.items() if str(k).strip() and str(v).strip()})
    except Exception as exc:
        LOG.warning("读取人员映射失败: %s", exc)
    return data


def save_personnel_mapping(mapping):
    data = dict(DEFAULT_PERSONNEL_MAP)
    if isinstance(mapping, dict):
        data.update({str(k).strip(): str(v).strip() for k, v in mapping.items() if str(k).strip() and str(v).strip()})
    try:
        with open(PERSONNEL_MAP_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        LOG.warning("保存人员映射失败: %s", exc)
        raise
    return data


def resolve_person_name(user_code):
    if not user_code:
        return ""
    return load_personnel_mapping().get(str(user_code), str(user_code))

# ==========================================
# 🌟 运行日志：复用 main.py 建立的 'forecast' logger；若独立跑 app.py 则自建
# ==========================================
LOG = logging.getLogger('forecast')
if not LOG.handlers:
    # 被独立调用（如开发调试直接跑 app.py）时的兼容配置
    try:
        from logging.handlers import RotatingFileHandler
        _base = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        _logdir = os.path.join(_base, 'logs')
        os.makedirs(_logdir, exist_ok=True)
        _fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        _fh = RotatingFileHandler(os.path.join(_logdir, 'runtime.log'), maxBytes=2*1024*1024, backupCount=5, encoding='utf-8')
        _fh.setFormatter(_fmt)
        LOG.addHandler(_fh)
        LOG.setLevel(logging.INFO)
        LOG.propagate = False
    except Exception:
        pass

# ==========================================
# [系统保护] Mock 类与安全导入
# ==========================================
class MockSFClient:
    def get_qrcode(self): return {"success": False, "error": "后端模块缺失(Mock)"}
    def check_scan_status(self): return {"success": False, "error": "后端模块缺失(Mock)"}
    def validate_login_and_get_token(self, t, s): return {"success": False, "message": "后端模块缺失(Mock)"}
    def get_session_status(self): return {"logged_in": False, "userCode": "OFFLINE"}
    def logout(self): pass
    def fetch_weather_data(self, *args): return ""

sf_client_instance = MockSFClient()
METARParser = None
parse_tafs = None

try:
    from .logic.metar_parser import METARParser
    from .logic.taf_parser import parse_tafs 
    from .logic.sf_client import sf_client_instance
except ImportError:
    try:
        from metar_parser import METARParser
        from taf_parser import parse_tafs
        from sf_client import sf_client_instance
    except ImportError:
        if METARParser is None:
            class METARParser:
                def parse(self, text, for_scoring=False): return {}
                def get_weather_severity(self, w): return 0
        if parse_tafs is None:
            def parse_tafs(text): return []

def get_base_path():
    if getattr(sys, 'frozen', False): return sys._MEIPASS
    else: return os.path.dirname(os.path.abspath(__file__))

base_path = get_base_path()

# 🌟 优先使用 main.py 传入的 FORECAST_WORK_DIR（支持程序放在任意位置，通过路径配置启动）
_env_work_dir = os.environ.get('FORECAST_WORK_DIR', '').strip()
if _env_work_dir and os.path.isdir(os.path.join(_env_work_dir, 'frontend')):
    frontend_folder = os.path.join(_env_work_dir, 'frontend')
elif os.path.exists(os.path.join(base_path, 'frontend')):
    frontend_folder = os.path.join(base_path, 'frontend')
elif os.path.exists(os.path.join(os.path.dirname(base_path), 'frontend')):
    frontend_folder = os.path.join(os.path.dirname(base_path), 'frontend')
else:
    frontend_folder = base_path

app = Flask(__name__, static_folder=frontend_folder)

# --- 常量定义 ---
CHINESE_WEATHER_MAP = {
    "雷雨": "TSRA", "强雷雨": "+TSRA", "大雷雨": "+TSRA", "弱雷雨": "-TSRA", "小雷雨": "-TSRA", "雷暴": "TS",
    "小雨": "-RA", "弱雨": "-RA", "雨": "RA", "中雨": "RA", "大雨": "+RA", "强雨": "+RA", 
    "小雪": "-SN", "弱雪": "-SN", "雪": "SN", "中雪": "SN", "大雪": "+SN", "强雪": "+SN",
    "小雨夹雪": "-RASN", "弱雨夹雪": "-RASN", "雨夹雪": "RASN",
    "冻雨": "FZRA", "小阵雨": "-SHRA", "弱阵雨": "-SHRA", "阵雨": "SHRA", "大阵雨": "+SHRA", "强阵雨": "+SHRA",
    "小阵雪": "-SHSN", "弱阵雪": "-SHSN", "阵雪": "SHSN", "大阵雪": "+SHSN", "强阵雪": "+SHSN",
    "冰雹": "GR", "小冰雹": "GS", "雾": "FG", "轻雾": "BR", "冻雾": "FZFG", "霾": "HZ", "烟": "FU",
    "沙尘暴": "SS", "扬沙": "SA", "尘": "DU", "晴": "SKC", "晴空": "SKC", "无天气": "NSW",
    "小毛毛雨": "-DZ", "弱毛毛雨": "-DZ", "毛毛雨": "DZ",
    "米雪": "SG", "小米雪": "-SG", 
    "低吹": "DS", "高吹": "BL", "龙卷": "FC", "飑": "SQ",
    "低吹雪": "DRSN", "高吹雪": "BLSN" 
}
METAR_TO_CHINESE_MAP = {v: k for k, v in CHINESE_WEATHER_MAP.items()}
METAR_TO_CHINESE_MAP.update({
    "+RA": "大雨", "-RA": "小雨", "RA": "中雨",
    "+SN": "大雪", "-SN": "小雪", "SN": "中雪",
    "-SG": "小米雪", "SG": "米雪",
    "+TSRA": "强雷雨", "-TSRA": "弱雷雨", "TSRA": "中雷雨",
    "+SHRA": "大阵雨", "-SHRA": "小阵雨", "SHRA": "中阵雨",
    "TS": "雷暴", "-RASN": "小雨夹雪", "-DZ": "小毛毛雨"
})
AIRPORT_NAME_MAP = {"ZBAA": "首都机场", "ZBAD": "大兴机场", "ZBTJ": "天津机场", "ZBSJ": "石家庄机场", "ZGSZ": "深圳机场", "ZSHC": "杭州机场", "ZHEC": "鄂州机场", "ZWWW": "乌鲁木齐"}
WIND_DIRECTION_MAP = {'N': 0, 'NNE': 22.5, 'NE': 45, 'ENE': 67.5, 'E': 90, 'ESE': 112.5, 'SE': 135, 'SSE': 157.5, 'S': 180, 'SSW': 202.5, 'SW': 225, 'WSW': 247.5, 'W': 270, 'WNW': 292.5, 'NW': 315, 'NNW': 337.5, 'VRB': 'VRB'}
CHINESE_WIND_DIR_MAP = {'N': '偏北风', 'NNE': '东北偏北风', 'NE': '东北风', 'ENE': '东北偏东风', 'E': '偏东风', 'ESE': '东南偏东风', 'SE': '东南风', 'SSE': '东南偏南风', 'S': '偏南风', 'SSW': '西南偏南风', 'SW': '西南风', 'WSW': '西南偏西风', 'W': '偏西风', 'WNW': '西北偏西风', 'NW': '西北风', 'NNW': '西北偏北风', 'VRB': '风向不定'}

@app.route('/')
def serve_index(): return send_from_directory(frontend_folder, 'index.html')

# 🌟 统一配置文件：始终从持久化 runtime 目录提供（而非前端静态目录），
# 保证打包模式下浏览器同步加载到的 window.OMICS_CONFIG 是持久副本。
# 显式路由优先级高于下面的 /<path:path> 静态兜底。
@app.route('/omics_config.js')
def serve_omics_config_js():
    # 确保文件存在（含首次迁移），再回读其原始文本返回。
    load_settings_config()
    try:
        with open(OMICS_CONFIG_JS_PATH, 'r', encoding='utf-8') as f:
            body = f.read()
    except Exception as exc:
        LOG.warning("读取 omics_config.js 供前端失败: %s", exc)
        body = _serialize_config_js(load_settings_config())
    return app.response_class(body, mimetype='application/javascript')

@app.route('/<path:path>')
def serve_static(path): return send_from_directory(frontend_folder, path)

@app.before_request
def _log_request_start():
    if request.path.startswith('/api/'):
        request._start_ts = time.time()
        LOG.info("--> %s %s", request.method, request.path)

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    if request.path.startswith('/api/'):
        dur = (time.time() - getattr(request, '_start_ts', time.time())) * 1000
        LOG.info("<-- %s %s | %s | %.0fms", request.method, request.path, response.status_code, dur)
    return response

@app.route('/api/log', methods=['POST'])
def api_frontend_log():
    """接收前端运行日志，统一落盘到 runtime.log。"""
    try:
        data = request.get_json(silent=True) or {}
        entries = data.get('entries')
        if entries and isinstance(entries, list):
            for e in entries:
                lvl = str(e.get('level', 'INFO')).upper()
                msg = e.get('msg', '')
                logfn = LOG.error if lvl in ('ERROR', 'WARN', 'WARNING') else LOG.info
                logfn("[FE] %s", msg)
        else:
            lvl = str(data.get('level', 'INFO')).upper()
            msg = data.get('msg', '')
            logfn = LOG.error if lvl in ('ERROR', 'WARN', 'WARNING') else LOG.info
            logfn("[FE] %s", msg)
        return jsonify({"success": True})
    except Exception as ex:
        LOG.exception("前端日志写入失败: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

    
# --- 辅助函数 ---
def _format_hourly_forecast_to_chinese(hour_data):
    if not hour_data: return "晴好"
    data_to_read = hour_data.get('base', hour_data)
    if hour_data.get('rule') in ['TEMPO', 'BECMG_TRANSITION']: data_to_read = {**hour_data.get('base', {}), **hour_data.get('change', {})}
    if not data_to_read: return "晴好"
    parts = []
    wind_dir = data_to_read.get('wind_dir'); wind_speed = data_to_read.get('wind_speed')
    if wind_dir and wind_speed and wind_speed > 0: parts.append(f"{CHINESE_WIND_DIR_MAP.get(wind_dir, wind_dir)}{wind_speed}米/秒")
    elif wind_speed and wind_speed > 0: parts.append(f"风速{wind_speed}米/秒")
    vis = data_to_read.get('visibility')
    if vis and vis < 9999: parts.append(f"能见度{vis}米")
    cloud = data_to_read.get('cloud')
    if cloud and cloud.get('height') is not None:
        amt = cloud.get('amount'); amt_cn = { 'BKN/OVC': '5-8量', 'FEW/SCT': '1-4量' }.get(amt, amt)
        parts.append(f"云{amt_cn} {cloud.get('height')}米")
    weather = data_to_read.get('weather', 'NSW').upper()
    if weather and weather != 'NSW':
        parts.append(" ".join([METAR_TO_CHINESE_MAP.get(code, code) for code in weather.split()]))
    return " ".join(parts) if parts else "晴好"

def generate_forecast_summary(airport_code, hourly_forecasts, mode='manual'):
    if mode == 'taf' or not hourly_forecasts: return ""
    airport_name = AIRPORT_NAME_MAP.get(airport_code, airport_code)
    beijing_tz = timezone(timedelta(hours=8)); bjt_forecasts = []
    for utc_hour_str in sorted(hourly_forecasts.keys()):
        if utc_hour_str.startswith('__'): continue # 🌟 修复：过滤掉非时间字符串的隐藏属性
        try:
            now = datetime.now(); day = int(utc_hour_str[:2]); hour = int(utc_hour_str[2:])
            utc_dt = datetime(now.year, now.month, day, hour, tzinfo=timezone.utc)
            bjt_dt = utc_dt.astimezone(beijing_tz)
            summary = _format_hourly_forecast_to_chinese(hourly_forecasts.get(utc_hour_str, {}))
            bjt_forecasts.append({"day": bjt_dt.day, "hour": bjt_dt.hour, "summary": summary})
        except: continue
    if not bjt_forecasts: return ""
    parts = []; i = 0
    while i < len(bjt_forecasts):
        curr = bjt_forecasts[i]; txt = curr['summary']
        if txt == "晴好": i += 1; continue
        start_d = curr['day']; start_h = curr['hour']; end_h = start_h; j = i + 1
        while j < len(bjt_forecasts) and bjt_forecasts[j]['summary'] == txt and bjt_forecasts[j]['day'] == start_d: end_h = bjt_forecasts[j]['hour']; j += 1
        time_range = f"{start_h:02d}时" if start_h == end_h else f"{start_h:02d}-{end_h:02d}时"
        parts.append(f"{start_d}日{time_range}{txt}"); i = j
    return f"{airport_name}预报 (北京时): {', '.join(parts)}。" if parts else f"{airport_name}预报 (北京时): 预计天气适航。"

def parse_manual_forecast_text(text):
    if not text: return {}
    parsed = {'weather': 'NSW', 'visibility': 9999, 'wind_speed': 0, 'cloud': {}}
    text = text.upper(); temp = text
    
    # 1. 提取风向风速：兼容代码 N10 和中文“偏北风10米/秒”。
    chinese_wind_match = None
    for code, label in sorted(CHINESE_WIND_DIR_MAP.items(), key=lambda item: len(item[1]), reverse=True):
        match = re.search(rf'{re.escape(label)}\s*(\d+)(?:\s*米/秒)?', temp)
        if match:
            parsed['wind_speed'] = int(match.group(1))
            parsed['wind_dir'] = code
            temp = temp.replace(match.group(0), '', 1)
            chinese_wind_match = match
            break
    if chinese_wind_match is None:
        w_match = re.search(r'([A-Z]{1,3})(\d+)', text)
        if w_match and w_match.group(1) in WIND_DIRECTION_MAP:
            parsed['wind_speed'] = int(w_match.group(2)); parsed['wind_dir'] = w_match.group(1); temp = temp.replace(w_match.group(0), '', 1)
    
    # 🌟 新增核心功能：识别纯数字的快捷云高 (0, 30, 60, 90, 120)
    # \b 表示单词边界，确保不会误抓到 1300(能见度) 里的 30
    naked_cld = re.search(r'\b(0|30|60|90|120)\b', temp)
    if naked_cld:
        # 默认视为 BKN/OVC 的低云云高
        parsed['cloud'] = {'amount': 'BKN/OVC', 'height': int(naked_cld.group(1))}
        # 从文本中剔除这个数字，防止后续被误认为其他要素
        temp = re.sub(r'\b(0|30|60|90|120)\b', '', temp, count=1)
        
    # 2. 提取天气现象
    sorted_keys = sorted(CHINESE_WEATHER_MAP.keys(), key=len, reverse=True)
    wx_parts = []
    for cn in sorted_keys:
        if cn in temp:
            wx_parts.append(CHINESE_WEATHER_MAP[cn]); temp = temp.replace(cn, '')
    wx_parts.extend(re.findall(r'([+\-]?(?:VC|MI|PR|BC|BL|DR|SH|TS|FZ)?[A-Z]{2,6})', text))
    if wx_parts: parsed['weather'] = " ".join(filter(None, wx_parts))
    
    # 3. 提取能见度
    vis = re.search(r'(\d{3,4})M?', text)
    if vis: parsed['visibility'] = int(vis.group(1))
    
    # 4. 提取标准云高 (如 OVC001) - 如果有标准写法，将覆盖快捷数字写法
    cld = re.search(r'(FEW|SCT|BKN|OVC)(\d{3})', text)
    if cld: parsed['cloud'] = {'amount': 'BKN/OVC' if cld.group(1) in ['BKN','OVC'] else 'FEW/SCT', 'height': round(int(cld.group(2))*30.48)}
    
    # 5. 提取标准风速 (如 10MPS)
    spd = re.search(r'(\d{2,3})(?:G(\d{2,3}))?MPS', text)
    if spd: parsed['wind_speed'] = max(int(spd.group(1)), int(spd.group(2) or 0))
    
    return parsed

def _format_single_forecast_part(fcst_dict):
    if not fcst_dict: return []
    parts = []
    if fcst_dict.get('visibility') is not None: parts.append(f"能见度: {fcst_dict['visibility']}m")
    if fcst_dict.get('wind_speed') is not None: parts.append(f"风速: {fcst_dict['wind_speed']}mps")
    c = fcst_dict.get('cloud', {})
    if c: parts.append(f"云: {c.get('raw_amount') or c.get('amount')} at {c.get('height')}m")
    elif 'cloud' in fcst_dict: parts.append("云: NSC/CAVOK")
    weather = fcst_dict.get('weather', 'NSW')
    if weather and weather != 'NSW': parts.append(f"天气: {weather}")
    return parts

def format_forecast_for_display(fcst_dict):
    if not fcst_dict: return "无预报"
    rule = fcst_dict.get('rule', 'NORMAL')
    base_dict = fcst_dict.get('base', fcst_dict) 
    base_parts = _format_single_forecast_part(base_dict)
    base_str = "\n".join(base_parts) if base_parts else "CAVOK / NSW"
    if rule == 'NORMAL': return base_str
    change_parts = _format_single_forecast_part(fcst_dict.get('change', {}))
    change_str = "\n".join(change_parts)
    if not change_str: return base_str
    if rule == 'TEMPO': return f"主报:\n{base_str}\n\nTEMPO:\n{change_str}"
    if rule == 'BECMG_TRANSITION':
        merged_dict = {**base_dict, **fcst_dict.get('change', {})}
        merged_parts = _format_single_forecast_part(merged_dict)
        merged_str = "\n".join(merged_parts) if merged_parts else "CAVOK / NSW"
        return f"BECMG:\n{merged_str}"
    return base_str 

def _parse_ddhhmm_to_datetime(time_str, context_date, is_metar=False):
    # 此函数专用于处理 DDHHMM 格式
    try:
        if len(time_str) < 4: raise ValueError(f"Invalid time format: {time_str}")
        day = int(time_str[0:2]); hour = int(time_str[2:4]); minute = int(time_str[4:6]) if len(time_str) >= 6 else 0
        time_delta = timedelta(days=0)
        if hour == 24: hour = 0; time_delta = timedelta(days=1)
        
        # 锚点日期 (Context Date)
        naive_context = datetime(context_date.year, context_date.month, context_date.day)
        candidates = []
        
        # 尝试上个月、本月、下个月
        for month_offset in [-1, 0, 1]:
            year = naive_context.year
            month = naive_context.month + month_offset
            if month < 1: year -= 1; month = 12
            if month > 12: year += 1; month = 1
            try:
                candidate = datetime(year, month, day, hour, minute) + time_delta
                candidates.append(candidate.replace(tzinfo=timezone.utc))
            except ValueError: continue
        
        if not candidates: raise ValueError(f"无法为 {time_str} 创建有效日期")
        
        aware_context = context_date if context_date.tzinfo else context_date.replace(tzinfo=timezone.utc)
        # 找绝对距离最近的
        return min(candidates, key=lambda dt: abs(dt - aware_context))
            
    except Exception as e: raise ValueError(f"Time parsing error: {e}")

def _fill_forecast_gaps(hourly_forecasts):
    if not hourly_forecasts: return hourly_forecasts
    # 🌟 修复：只提取纯数字的时间键进行排序和补全，放过 '__' 开头的标记
    sorted_keys = sorted([k for k in hourly_forecasts.keys() if not k.startswith('__')])
    filled_forecasts = copy.deepcopy(hourly_forecasts)
    def next_ddhh(ddhh_str):
        d = int(ddhh_str[:2]); h = int(ddhh_str[2:])
        h += 1
        if h >= 24: h = 0; d += 1 
        return f"{d:02d}{h:02d}"
    for i in range(len(sorted_keys) - 1):
        curr_key = sorted_keys[i]; next_exist_key = sorted_keys[i+1]
        cursor = next_ddhh(curr_key)
        while cursor != next_exist_key:
            if len(cursor) != 4: break 
            base_data_to_copy = filled_forecasts.get(cursor, filled_forecasts[sorted_keys[i]])
            filled_forecasts[cursor] = copy.deepcopy(base_data_to_copy)
            cursor = next_ddhh(cursor)
            # 简单防止死循环
            if int(cursor[:2]) != int(curr_key[:2]) and abs(int(cursor[:2]) - int(curr_key[:2])) > 1 and int(curr_key[:2])!=31: break 
    return filled_forecasts

def parse_taf_string_robust(taf_text):
    clean_text = taf_text.strip().replace('=', '').replace('\n', ' ')
    clean_text = re.sub(r'\s+', ' ', clean_text)
    clean_text = clean_text.replace('TMEPO', 'TEMPO').replace('BEMCG', 'BECMG')
    validity_match = re.search(r'\b(\d{4}/\d{4})\b', clean_text)
    if not validity_match: return {}
    validity_str = validity_match.group(1)
    start_d = int(validity_str[:2]); start_h = int(validity_str[2:4]); end_d = int(validity_str[5:7]); end_h = int(validity_str[7:])
    tokens = clean_text.split()
    groups = []
    current_group = {'type': 'BASE', 'content': []}
    for token in tokens:
        if token in ['BECMG', 'TEMPO', 'FM']:
            groups.append(current_group); current_group = {'type': token, 'content': []}
        else: current_group['content'].append(token)
    groups.append(current_group)
    def parse_elements(tokens):
        data = {'wind_speed': None, 'visibility': None, 'weather': None, 'cloud': None}
        for t in tokens:
            if re.match(r'^\d{3}\d{2}(?:G\d{2})?MPS$', t): data['wind_speed'] = int(t[3:5])
            if re.match(r'^\d{3}\d{2}(?:G\d{2})?KT$', t): data['wind_speed'] = round(int(t[3:5]) * 0.51444)
            if re.match(r'^\d{4}$', t) and t != '9999': data['visibility'] = int(t)
            if t == '9999': data['visibility'] = 9999
            if re.search(r'(?:^|\+|-)(?:TS|SH|FZ|BL|DR|MI|BC|PR|RA|SN|SG|PL|GR|GS|DZ|FG|BR|HZ|FU|SA|DU|SS)(?:RA|SN|SG|PL|GR|GS|DZ)?$', t):
                if not re.search(r'\d', t): 
                    if data['weather']: data['weather'] += ' ' + t
                    else: data['weather'] = t
            if t == 'NSW': data['weather'] = 'NSW'
        return data
    base_group = groups[0]
    base_content_start_idx = 0
    for i, t in enumerate(base_group['content']):
        if re.match(r'\d{4}/\d{4}', t): base_content_start_idx = i + 1; break
    current_base = parse_elements(base_group['content'][base_content_start_idx:])
    hours = []
    curr_d, curr_h = start_d, start_h
    limit = 0
    while limit < 48:
        h_str = f"{curr_d:02d}{curr_h:02d}"
        hours.append(h_str)
        if curr_d == end_d and curr_h == end_h: break
        curr_h += 1
        if curr_h == 24: curr_h = 0; curr_d += 1
        limit += 1
    timeline = {h: {'base': copy.deepcopy(current_base), 'rule': 'NORMAL', 'change': {}} for h in hours}
    for grp in groups[1:]:
        g_type = grp['type']; content = grp['content']
        time_match = re.match(r'(\d{2})(\d{2})/(\d{2})(\d{2})', content[0]) if content else None
        if not time_match: continue
        changes = parse_elements(content[1:])
        sd, sh, ed, eh = int(time_match.group(1)), int(time_match.group(2)), int(time_match.group(3)), int(time_match.group(4))
        target_hours = []
        in_range = False
        for h_str in hours:
            hd, hh = int(h_str[:2]), int(h_str[2:])
            if hd == sd and hh == sh: in_range = True
            if hd == ed and hh == eh: in_range = False
            if in_range: target_hours.append(h_str)
        if g_type == 'BECMG':
            apply_from_idx = -1
            for idx, h in enumerate(hours):
                hd, hh = int(h[:2]), int(h[2:])
                if hd == ed and hh == eh: apply_from_idx = idx; break
            if apply_from_idx != -1:
                for i in range(apply_from_idx, len(hours)):
                    h_key = hours[i]; base_ref = timeline[h_key]['base']
                    if changes['wind_speed'] is not None: base_ref['wind_speed'] = changes['wind_speed']
                    if changes['visibility'] is not None: base_ref['visibility'] = changes['visibility']
                    if changes['weather'] is not None: base_ref['weather'] = changes['weather']
        elif g_type == 'TEMPO':
            for h_key in target_hours: timeline[h_key]['rule'] = 'TEMPO'; timeline[h_key]['change'] = changes
    return timeline

class QualityAssessor:
    def __init__(self, standards, custom_phenomena=None):
        self.standards = standards
        self.vis_map = { 'takeoff': standards.get('vis_takeoff', 400), 'landing': standards.get('vis_landing', 800), 'warning': standards.get('vis_warning', 1600) }
        self.cld_map = { 'takeoff': standards.get('cld_takeoff', 30), 'landing': standards.get('cld_landing', 60), 'warning': standards.get('cld_warning', 120) }
        if custom_phenomena: self.phen_categories = custom_phenomena
        else: self.phen_categories = { '雷雨类': ['TSRA'], '积冰类': ['FZDZ', 'FZRA', 'SN', 'SG', 'PL'], '强降水(无雷)类': ['RA', 'SH', 'SHRA'], '特殊类': ['GR', 'GS', 'FC', 'SQ'] }
        self.valid_codes_whitelist = set()
        for cats in self.phen_categories.values():
            for c in cats: self.valid_codes_whitelist.add(c)

    def _get_intensity(self, code):
        if not code or code == 'NSW': return '无'
        if '+' in code: return '强'
        if '-' in code: return '弱'
        return '中'

    def score_wind(self, fcst, obs):
        if fcst is None and obs is None: return '不评'
        f_spd = fcst or 0; o_spd = obs or 0
        if f_spd < 17 and o_spd < 17: return '不评' 
        if f_spd >= 17 and o_spd < 17: return '空报'
        if f_spd < 17 and o_spd >= 17: return '漏报'
        return '完美'

    def score_visibility(self, fcst, obs, obs_weather='NSW', fcst_weather='NSW'):
        f = fcst if fcst is not None else 9999
        o = obs if obs is not None else 9999
        def get_vis_level(v):
            if v <= self.vis_map['takeoff']: return 3
            if v <= self.vis_map['landing']: return 2
            if v <= self.vis_map['warning']: return 1
            return 0
        f_lvl = get_vis_level(f); o_lvl = get_vis_level(o)
        matrix = {
            3: {3: '完美', 2: '优秀', 1: '空报', 0: '空报'},
            2: {3: '优秀', 2: '完美', 1: '空报', 0: '空报'},
            1: {3: '漏报', 2: '漏报', 1: '完美', 0: '空报'},
            0: {3: '漏报', 2: '漏报', 1: '漏报', 0: '不评'} 
        }
        return matrix[f_lvl][o_lvl]

    def score_low_cloud(self, fcst_cloud, obs_cloud):
        f_h = fcst_cloud.get('height', 9999) if fcst_cloud else 9999
        f_amt_code = fcst_cloud.get('amount', '') if fcst_cloud else ''
        o_h = obs_cloud.get('height', 9999) if obs_cloud else 9999
        o_amt_code = obs_cloud.get('amount_code', '') if obs_cloud else ''
        def get_amt_level(code):
            if code in ['BKN', 'OVC', 'BKN/OVC']: return 2
            if code == 'SCT' or code == 'FEW/SCT': return 1
            return 0
        f_amt_lvl = get_amt_level(f_amt_code); o_amt_lvl = get_amt_level(o_amt_code); warn_h = self.cld_map['warning']
        if o_amt_lvl == 1 and o_h <= warn_h:
            if f_h <= warn_h: return '优秀'
            return '不评'
        if o_amt_lvl == 2 and o_h <= warn_h:
            if f_amt_lvl < 2: return '漏报'
            def get_h_level(h):
                if h <= self.cld_map['takeoff']: return 3
                if h <= self.cld_map['landing']: return 2
                if h <= self.cld_map['warning']: return 1
                return 0
            fh_lvl = get_h_level(f_h); oh_lvl = get_h_level(o_h)
            matrix = {
                3: {3: '完美', 2: '优秀', 1: '空报', 0: '空报'},
                2: {3: '优秀', 2: '完美', 1: '空报', 0: '空报'},
                1: {3: '漏报', 2: '漏报', 1: '完美', 0: '空报'},
                0: {3: '漏报', 2: '漏报', 1: '漏报', 0: '不评'}
            }
            return matrix[fh_lvl][oh_lvl]
        if (o_amt_lvl < 2 or o_h > warn_h):
            if f_amt_lvl == 2 and f_h <= warn_h: return '空报'
        return '不评'

    def score_single_weather_category(self, fcst_code, obs_code, category):
        has_fcst = fcst_code != 'NSW'; has_obs = obs_code != 'NSW'
        if not has_fcst and not has_obs: return '不评' 
        if has_fcst and not has_obs: return '空报'
        if not has_fcst and has_obs: return '漏报'
        f_int = self._get_intensity(fcst_code); o_int = self._get_intensity(obs_code)
        if f_int == o_int: return '完美'
        return '优秀' 

def run_evaluation(forecasts, final_obs, standards, obs_reports_raw, custom_phenomena=None, sorted_hours_list=None, ap_code="UNKNOWN", custom_thresholds=None):
    # 🌟 修复：取样本键时，跳过隐藏属性
    sample_key = next((k for k in forecasts.keys() if not k.startswith('__')), None) if forecasts else None
    if sample_key and 'base' not in forecasts[sample_key]: forecasts = _fill_forecast_gaps(forecasts)
    
    assessor = QualityAssessor(standards, custom_phenomena)
    score_results, obs_results = [], []
    
    # 🌟 修复：如果没传时间列表，自己提取时也要过滤掉隐藏属性
    hours_to_evaluate = sorted_hours_list if sorted_hours_list else sorted([k for k in forecasts.keys() if not k.startswith('__')])
    if not hours_to_evaluate: return pd.DataFrame(), pd.DataFrame(), ""
    
    tempo_blocks = {} 
    current_block_id = None; last_change_content = None; block_map = {} 
    
    def get_change_signature(c): return json.dumps(c, sort_keys=True)

    for hour in hours_to_evaluate:
        fcst = forecasts.get(hour, {}); rule = fcst.get('rule', 'NORMAL'); change = fcst.get('change', {})
        if rule == 'TEMPO':
            if not any(k in change for k in ['weather', 'visibility', 'wind_speed']): rule = 'NORMAL' 
            else:
                sig = get_change_signature(change)
                if sig != last_change_content:
                    current_block_id = hour; tempo_blocks[current_block_id] = {'hours': [], 'change': change}
                tempo_blocks[current_block_id]['hours'].append(hour); block_map[hour] = current_block_id; last_change_content = sig
        if rule != 'TEMPO': last_change_content = None 

    tempo_hits = {} 
    tempo_vis_hits = {} 

    def clean_weather_final(wx_str, current_category=None):
        if not wx_str or wx_str == 'NSW': return 'NSW'
        codes = wx_str.split(); cleaned = []
        for c in codes:
            if c.startswith('VC'): continue
            
            # 核心修改：如果是强降水类，且包含“-”(弱/小)，则忽略它
            if current_category == '强降水(无雷)类' and c.startswith('-'):
                continue 
                
            core_code = c.replace('+', '').replace('-', '')
            is_ts = 'TS' in core_code
            if core_code in assessor.valid_codes_whitelist or is_ts: cleaned.append(c)
        return " ".join(cleaned) if cleaned else 'NSW'

    def check_hit(change_dict, obs_dict, category=None):
        if category:
            codes = assessor.phen_categories.get(category, [])
            change_wx = change_dict.get('weather', 'NSW')
            obs_wx = obs_dict.get('weather', {}).get(category, 'NSW') 
            has_fcst_cat = any(c in change_wx for c in codes)
            if not has_fcst_cat: return False
            obs_clean = clean_weather_final(obs_wx, category); obs_codes = obs_clean.split()
            hit = any(any(oc.replace('+','').replace('-','') == c for c in codes) for oc in obs_codes)
            if 'TS' in codes and 'TS' in obs_clean: hit = True
            return hit
        return False 
    
    def check_vis_hit(change_vis, obs_vis_val):
        if change_vis is None: return False
        warn_std = standards.get('vis_warning', 1600)
        # 如果预测低能见度，且实况确实低
        if change_vis <= warn_std and obs_vis_val <= warn_std: return True
        return False

    for bid, bdata in tempo_blocks.items():
        tempo_hits[bid] = {}
        for cat in assessor.phen_categories.keys():
            is_hit = False
            for h in bdata['hours']:
                obs = final_obs.get(h, {})
                if check_hit(bdata['change'], obs, category=cat): is_hit = True; break
            tempo_hits[bid][cat] = is_hit
        
        is_vis_hit = False
        ch_vis = bdata['change'].get('visibility')
        if ch_vis is not None:
            for h in bdata['hours']:
                obs_v = final_obs.get(h, {}).get('visibility', 9999)
                if check_vis_hit(ch_vis, obs_v): is_vis_hit = True; break
        tempo_vis_hits[bid] = is_vis_hit

    for hour in hours_to_evaluate:
        obs = final_obs.get(hour, {}); fcst_data = forecasts.get(hour, {})
        score_row, obs_row = {'时次': hour}, {'时次': hour}
        rule = fcst_data.get('rule', 'NORMAL'); base_fcst = fcst_data.get('base', fcst_data); change_fcst = fcst_data.get('change', {})
        
        if rule == 'TEMPO' and hour not in block_map: rule = 'NORMAL'
        if rule != 'TEMPO': 
            rule = 'NORMAL' 
            if change_fcst: base_fcst = {**base_fcst, **change_fcst}

        # --- 1. 天气现象 ---
        for category, codes in assessor.phen_categories.items():
            obs_raw = obs.get('weather', {}).get(category, 'NSW'); obs_clean = clean_weather_final(obs_raw, category)
            obs_row[category] = obs_raw if obs_raw != 'NSW' else '/' 
            base_raw = base_fcst.get('weather', 'NSW'); base_clean = clean_weather_final(base_raw, category)
            base_phen = 'NSW'
            for p in base_clean.split():
                core_p = p.replace('+','').replace('-','')
                if core_p in codes or ('TS' in codes and 'TS' in core_p): base_phen = p; break
            has_base = base_phen != 'NSW'
            o_p = 'NSW'
            for p in obs_clean.split():
                core_p = p.replace('+','').replace('-','')
                if core_p in codes or ('TS' in codes and 'TS' in core_p): o_p = p; break
            has_obs = o_p != 'NSW'

            if rule == 'NORMAL':
                if not has_base and not has_obs: score_row[category] = '不评'
                elif has_base and not has_obs: score_row[category] = '空报'
                elif not has_base and has_obs: score_row[category] = '漏报'
                else: score_row[category] = assessor.score_single_weather_category(base_phen, o_p, category)
            elif rule == 'TEMPO':
                bid = block_map.get(hour); is_block_hit = tempo_hits.get(bid, {}).get(category, False)
                tempo_raw = change_fcst.get('weather', 'NSW'); tempo_clean = clean_weather_final(tempo_raw, category)
                tempo_phen = 'NSW'
                for p in tempo_clean.split():
                    core_p = p.replace('+','').replace('-','')
                    if core_p in codes or ('TS' in codes and 'TS' in core_p): tempo_phen = p; break
                has_tempo = tempo_phen != 'NSW'
                
                if not has_tempo:
                    if not has_base and not has_obs: score_row[category] = '不评'
                    elif has_base and not has_obs: score_row[category] = '空报' 
                    elif not has_base and has_obs: score_row[category] = '漏报' 
                    else: score_row[category] = assessor.score_single_weather_category(base_phen, o_p, category)
                    continue

                if is_block_hit:
                    if has_obs: score_row[category] = assessor.score_single_weather_category(tempo_phen, o_p, category)
                    else:
                        if not has_base: score_row[category] = '不评' 
                        else: score_row[category] = '空报' 
                else:
                    if has_obs: score_row[category] = '漏报' 
                    elif hour == tempo_blocks[bid]['hours'][0]: score_row[category] = '空报' 
                    else:
                        if not has_base and not has_obs: score_row[category] = '不评' 
                        elif has_base and not has_obs: score_row[category] = '空报'
                        elif not has_base and has_obs: score_row[category] = '漏报'
                        else: score_row[category] = assessor.score_single_weather_category(base_phen, o_p, category)

        # --- 2. 连续要素 (能见度) ---
        active_fcst_continuous = base_fcst
        
        # [诊断日志]
        current_vis_source = "Base"
        
        if rule == 'BECMG_TRANSITION' and change_fcst:
            active_fcst_continuous = {**base_fcst, **change_fcst}
            current_vis_source = "BECMG"
        
        elif rule == 'TEMPO':
            bid = block_map.get(hour)
            # 只有当 TEMPO 确实报了能见度变化时才判断
            if change_fcst.get('visibility') is not None:
                vis_hit = tempo_vis_hits.get(bid, False)
                if vis_hit:
                    # 命中：使用 TEMPO 值
                    active_fcst_continuous = {**base_fcst, **change_fcst}
                    current_vis_source = "TEMPO(Hit)"
                else:
                    # 未命中
                    if hour == tempo_blocks[bid]['hours'][0]:
                        # 首小时惩罚：强制用 TEMPO 值 (导致空报)
                        active_fcst_continuous = {**base_fcst, **change_fcst}
                        current_vis_source = "TEMPO(Miss-Penalty)"
                    else:
                        # 后续小时：回退 Base
                        active_fcst_continuous = base_fcst
                        current_vis_source = "TEMPO(Miss-Fallback)"
            else:
                # TEMPO 没报能见度，沿用 Base
                pass
        
        # 在黑框打印能见度取值过程
        vis_val_used = active_fcst_continuous.get('visibility', 9999)
        obs_val = obs.get('visibility', 9999)
        print(f"[DEBUG Vis] Time:{hour} | Rule:{rule} | Source:{current_vis_source} | Fcst:{vis_val_used} | Obs:{obs_val}")

        # === 🌟 全新大风打分逻辑 (对称 15% / 25%) ===
        # 1. 确定当前机场的大风阈值
        w_std = float(standards.get('wind_warning', 17))
        if custom_thresholds and ap_code in custom_thresholds:
            w_std = float(custom_thresholds[ap_code].get('ww', w_std))

        w_fcst_val = active_fcst_continuous.get('wind_speed')
        w_obs_val = obs.get('wind_speed')

        if w_fcst_val is None and w_obs_val is None:
            score_row['最大风速(MPS)'] = '不评'
        else:
            f_spd = float(w_fcst_val or 0)
            o_spd = float(w_obs_val or 0)

            if f_spd < w_std and o_spd < w_std:
                score_row['最大风速(MPS)'] = '不评'
            else:
                if o_spd == 0: # 防除零保护
                    if f_spd >= w_std: score_row['最大风速(MPS)'] = '空报'
                    else: score_row['最大风速(MPS)'] = '漏报'
                else:
                    # 核心公式
                    diff_ratio = (f_spd - o_spd) / o_spd
                    abs_ratio = abs(diff_ratio)

                    if abs_ratio < 0.15:
                        score_row['最大风速(MPS)'] = '完美'
                    elif abs_ratio < 0.25:
                        score_row['最大风速(MPS)'] = '优秀'
                    else:
                        if diff_ratio >= 0.25:
                            score_row['最大风速(MPS)'] = '空报'
                        else: # diff_ratio <= -0.25
                            score_row['最大风速(MPS)'] = '漏报'

        obs_row['最大风速(MPS)'] = w_obs_val
        
        vis_fcst = active_fcst_continuous.get('visibility'); vis_obs = obs.get('visibility')
        vis_wx_obs_raw = obs.get('weather', {})
        if isinstance(vis_wx_obs_raw, dict): vis_wx_obs = " ".join(vis_wx_obs_raw.values()) if vis_wx_obs_raw else 'NSW'
        else: vis_wx_obs = str(vis_wx_obs_raw)
        vis_wx_fcst = active_fcst_continuous.get('weather', 'NSW')
        
        score_row['最差能见度(m)'] = assessor.score_visibility(vis_fcst, vis_obs, vis_wx_obs, vis_wx_fcst)
        obs_row['最差能见度(m)'] = vis_obs

        cld_fcst = active_fcst_continuous.get('cloud'); cld_obs = obs.get('cloud')
        score_row['最低云高(m)'] = assessor.score_low_cloud(cld_fcst, cld_obs)
        obs_row['最低云高(m)'] = cld_obs.get('height') if cld_obs else '/'
        
        # 🌟 修复：使用本函数内的 forecasts 变量获取字典属性
        score_row['预报时效'] = forecasts.get('__validity', '24小时预报')
        score_row['预报全文'] = forecasts.get('__full_text', '-')
        score_row['预报内容'] = format_forecast_for_display(fcst_data).replace('\n', ' ')
        
        obs_row['预报时效'] = forecasts.get('__validity', '24小时预报')
        obs_row['预报全文'] = forecasts.get('__full_text', '-')
        obs_row['预报内容'] = '-'

        score_results.append(score_row); obs_results.append(obs_row)

    if not score_results: return pd.DataFrame(), pd.DataFrame(), ""
    df_scores = pd.DataFrame(score_results).set_index('时次'); df_obs = pd.DataFrame(obs_results).set_index('时次')
    
    # 🌟 修复核心1：在重置列名之前，先把“预报内容”单独保护起来！
    fcst_validity = df_scores['预报时效'] if '预报时效' in df_scores.columns else None
    fcst_full = df_scores['预报全文'] if '预报全文' in df_scores.columns else None
    fcst_content = df_scores['预报内容'] if '预报内容' in df_scores.columns else None

    obs_validity = df_obs['预报时效'] if '预报时效' in df_obs.columns else None
    obs_full = df_obs['预报全文'] if '预报全文' in df_obs.columns else None
    obs_content = df_obs['预报内容'] if '预报内容' in df_obs.columns else None

   # 🌟 恢复逻辑分组：基础要素一组，天气现象一组
    ordered_cols = ['最大风速(MPS)', '最差能见度(m)', '最低云高(m)', '雷雨类', '强降水(无雷)类', '积冰类', '特殊类']
    df_scores = df_scores.reindex(columns=ordered_cols).fillna('不评'); df_obs = df_obs.reindex(columns=ordered_cols).fillna('/')

    # 🌟 核心修复：按列（项目）独立统计，完美复刻你的专业计分逻辑！
    total_slots = len(df_scores)
    sum_perf = sum_exc = sum_fa = sum_miss = sum_eval = sum_acc = sum_tot = 0
    any_evaluated = False

    for col in ordered_cols:
        if col not in df_scores.columns:
            continue
        vals = df_scores[col].tolist()
        perf = vals.count('完美')
        exc = vals.count('优秀')
        fa = vals.count('空报')
        miss = vals.count('漏报')
        not_eval = vals.count('不评')
        
        eval_c = perf + exc + fa + miss
        # 只要该项目有任何参评记录，就把它全天时次拉入考核！
        if eval_c > 0:
            any_evaluated = True
            sum_perf += perf
            sum_exc += exc
            sum_fa += fa
            sum_miss += miss
            sum_eval += eval_c
            # 关键点：该项目下没犯错的“不评”时次，全部视为正确判断，算作“准确”！
            sum_acc += (perf + exc + not_eval) 
            sum_tot += total_slots

    # 兜底：如果一整天所有项目完全没有被激活（即全天适航无天气），总评和准确保底给满
    if not any_evaluated:
        sum_tot = total_slots
        sum_acc = total_slots
    
    stats_dict = {
        "完美": sum_perf,
        "优秀": sum_exc,
        "空报": sum_fa,
        "漏报": sum_miss,
        "准确": sum_acc,
        "参评": sum_eval,
        "总评": sum_tot
    }

    # 🌟 修复核心2：统计算完后，把“预报内容”插回第一列，传给前端和导出模块！
    if fcst_content is not None: df_scores.insert(0, '预报内容', fcst_content)
    if fcst_full is not None: df_scores.insert(0, '预报全文', fcst_full)
    if fcst_validity is not None: df_scores.insert(0, '预报时效', fcst_validity)
    
    if obs_content is not None: df_obs.insert(0, '预报内容', obs_content)
    if obs_full is not None: df_obs.insert(0, '预报全文', obs_full)
    if obs_validity is not None: df_obs.insert(0, '预报时效', obs_validity)

    return df_scores, df_obs, stats_dict    

# === 🌟 离线登录状态管理 ===
offline_session = {"logged_in": False, "userCode": "OFFLINE", "role": "user", "isOffline": True}

@app.route('/api/personnel_mapping', methods=['GET', 'POST'])
def personnel_mapping_api():
    if request.method == 'GET':
        return jsonify({"success": True, "data": load_personnel_mapping()})
    data = request.get_json() or {}
    mapping = data.get('mapping', data)
    try:
        saved = save_personnel_mapping(mapping)
        # Mirror legacy personnel mapping changes into the unified settings file when present.
        try:
            cfg = load_settings_config()
            cfg['personnel_dict'] = saved
            save_settings_config(cfg)
        except Exception as sync_exc:
            LOG.warning("同步人员映射到统一设置失败: %s", sync_exc)
        return jsonify({"success": True, "data": saved})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 200

try:
    from .logic.settings_archive import SettingsArchive, validate_settings
except ImportError:
    from logic.settings_archive import SettingsArchive, validate_settings
settings_archive = SettingsArchive(os.path.join(_PERSIST_DIR, 'runtime', 'settings_backups'))

@app.route('/api/settings_backups', methods=['GET', 'POST'])
def settings_backups_api():
    try:
        if request.method == 'GET':
            return jsonify(success=True, data=settings_archive.list())
        payload = request.get_json(silent=True) or {}
        if payload.get('restore'):
            settings = settings_archive.read(payload['restore'])
            settings_archive.create(load_settings_config())
            return jsonify(success=True, data=save_settings_config(settings, replace=True))
        return jsonify(success=True, data=settings_archive.create(load_settings_config()))
    except Exception as exc:
        return jsonify(success=False, error=str(exc)), 400

@app.route('/api/settings_config', methods=['GET', 'POST'])
def settings_config_api():
    """Persist system settings outside browser localStorage.

    Airport dictionary remains in frontend/airports.js via /api/save_airports.
    """
    if request.method == 'GET':
        return jsonify({"success": True, "data": load_settings_config()})
    payload = request.get_json(silent=True) or {}
    settings = payload.get('settings', payload)
    try:
        validate_settings(settings)
        if payload.get('replace'):
            settings_archive.create(load_settings_config())
        saved = save_settings_config(settings, replace=bool(payload.get('replace')))
        return jsonify({"success": True, "data": saved})
    except Exception as exc:
        LOG.warning("保存系统设置配置失败: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 200

@app.route('/api/auth/offline_login', methods=['POST'])
def offline_login_api():
    global offline_session
    data = request.json
    username = data.get('username', '').strip() # 此时前端传过来的是【工号】
    password = data.get('password', '')

    if not username: return jsonify({"success": False, "message": "请输入工号"})

    # 密码默认依然是 000 (只是前端不再自动填入了，需要你手打)
    if password == "000":
        # 🌟 核心修改：认准工号 41060711，给予吴霄最高权限标识！
        is_admin = (username == "41060711")
        display_name = resolve_person_name(username)
        offline_session = {
            "logged_in": True,
            "userCode": username,
            "displayName": display_name,
            "role": "admin" if is_admin else "user",
            "isOffline": True
        }
        return jsonify({"success": True, "message": f"登录成功！"})
    return jsonify({"success": False, "message": "密码错误"})

@app.route('/api/auth/qrcode', methods=['GET'])
def get_qrcode(): return jsonify(sf_client_instance.get_qrcode())

@app.route('/api/auth/check', methods=['GET'])
def check_qr_status(): return jsonify(sf_client_instance.check_scan_status())

@app.route('/api/auth/validate', methods=['POST'])
def validate_token():
    d = request.get_json()
    return jsonify(sf_client_instance.validate_login_and_get_token(d.get('ticket'), d.get('scan_id')))

@app.route('/api/auth/status', methods=['GET'])
def get_auth_status():
    # OMICS 后端不再作为统一登录态来源；统一 token 由前端 localStorage + Nginx /auth/status 管理。
    # 优先检查离线登录状态
    if offline_session["logged_in"]:
        return jsonify(offline_session)
    # 否则返回实际的扫码状态，加上 isOffline 标记为 false
    status = sf_client_instance.get_session_status()
    status["isOffline"] = False
    if status.get("userCode"):
        status["displayName"] = resolve_person_name(status.get("userCode"))
    # 如果扫码的是管理员账号，赋予 admin
    if status.get("userCode") == '41060711':
        status["role"] = "admin"
    return jsonify(status)

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    global offline_session
    offline_session = {"logged_in": False, "userCode": "OFFLINE", "role": "user", "isOffline": True}
    sf_client_instance.logout()
    return jsonify({"success": True})

@app.route('/api/fetch_data', methods=['POST'])
def fetch_weather_data():
    print(f"[DEBUG] 收到下载请求: {request.get_json()}")
    try:
        d = request.get_json()
        token = resolve_auth_token(d.get('token'))
        start = d.get('start_time'); end = d.get('end_time'); aps = d.get('airports', ""); wtypes = d.get('wtypes', ["SA","SP"])
        now = datetime.now(timezone.utc)
        try:
            if '-' in start: fmt = "%Y-%m-%d"
            elif len(start) == 8: fmt = "%Y%m%d"
            elif len(start) == 12: fmt = "%Y%m%d%H%M"
            else: fmt = "%Y%m%d"
            s_dt = datetime.strptime(start, fmt).replace(tzinfo=timezone.utc)
            e_dt = datetime.strptime(end, fmt).replace(tzinfo=timezone.utc)
            if e_dt < s_dt: e_dt += timedelta(days=1)
            print(f"[DEBUG] 解析后的时间范围: {s_dt} -> {e_dt}")
        except ValueError as e: return jsonify({"success": False, "error": f"时间格式错误: {e}"}), 400
        
        t_aps = ["ZHEC", "ZBAA", "ZGHA", "ZSHC"]
        if aps: t_aps = [x.upper() for x in aps.strip().split() if x.strip()]
        data = sf_client_instance.fetch_weather_data(token, s_dt, e_dt, t_aps, wtypes)
        
        # 🌟 核心升级：直接调用后台现成的质量评定 TAF 引擎，将完美解析的逐时数据发给前端！
        parsed_tafs_list = []
        if "FT" in wtypes or "FC" in wtypes:
            try:
                parsed_tafs_list = parse_tafs(data, issued_date=s_dt.date())
                # 转换 datetime，避免 JSON 序列化报错
                for t in parsed_tafs_list:
                    if 'start_dt' in t and hasattr(t['start_dt'], 'isoformat'): t['start_dt'] = t['start_dt'].isoformat()
                    if 'end_dt' in t and hasattr(t['end_dt'], 'isoformat'): t['end_dt'] = t['end_dt'].isoformat()
            except Exception as e:
                print(f"TAF 预解析异常: {e}")

        print(f"[DEBUG] 丰台接口返回数据长度: {len(data) if data else 0}")
        return jsonify({"success": True, "data": data, "parsed_tafs": parsed_tafs_list})
    except Exception as e: return jsonify({"success": False, "error": str(e)}), 500
# ==========================================
# 🌟 新增：处理前端获取航班数据的请求
# ==========================================
@app.route('/api/fetch_flights', methods=['POST'])
def api_fetch_flights():
    data = request.json
    token = resolve_auth_token(data.get('token'))
    flight_date = data.get('flight_date')
    
    if not token or not flight_date:
        return jsonify({"success": False, "error": "缺少 token 或 flight_date 参数"})
        
    try:
        # 直接调用你已经在 sf_client_instance 里写好的方法
        flights = sf_client_instance.fetch_flight_schedule(token, flight_date)
        return jsonify({"success": True, "data": flights})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)})

# ==========================================
# 🌟 新增：接收前端机场字典，并直接覆盖保存到 airports.js
# ==========================================
@app.route('/api/save_airports', methods=['POST'])
def api_save_airports():
    print("\n" + "="*40)
    print("[DEBUG] 收到前端请求：准备保存新的机场字典配置...")
    
    data = request.json
    coords = data.get('coords', {})
    names = data.get('names', {})
    
    # 将字典格式化为标准的 JS 代码字符串
    import json
    js_content = f"window.AIRPORT_COORDS = {json.dumps(coords, ensure_ascii=False, indent=4)};\n\n"
    js_content += f"window.GLOBAL_AIRPORT_NAME_MAP = {json.dumps(names, ensure_ascii=False, indent=4)};\n"
    
    try:
        # 🌟 核心修复：直接使用 app.py 顶部已经定义好的 frontend_folder 全局路径
        global frontend_folder
        file_path = os.path.join(frontend_folder, 'airports.js')
        
        print(f"[DEBUG] 计算出的目标物理路径为: {file_path}")
        
        if not os.path.exists(file_path):
            print("[WARN] 警告：目标路径下未找到原 airports.js，系统将自动创建新文件。")
        else:
            print("[DEBUG] 检测到原 airports.js，准备执行数据覆写。")
            
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(js_content)
            
        print("[DEBUG] ✅ 写入成功！新的机场配置已保存。")
        print("="*40 + "\n")
        
        return jsonify({"success": True, "message": "已成功保存到物理文件！"})
    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        print(f"[ERROR] ❌ 保存失败，详细报错信息如下:\n{error_msg}")
        return jsonify({"success": False, "error": str(e)})
        
@app.route('/api/shutdown', methods=['POST'])
def shutdown():
    def kill():
        time.sleep(1)
        os._exit(0)
    threading.Thread(target=kill).start()
    return jsonify({"status": "shutting down"})

@app.route('/api/score', methods=['POST', 'OPTIONS']) 
def handle_scoring():
    if request.method == 'OPTIONS': return jsonify({'status': 'ok'})
    try:
        print("[DEBUG] 开始评分...")
        parser = METARParser(); d = request.get_json()
        mode = d.get('forecast_mode'); obs_text = d.get('obs_text', '')
        standards = {k: int(v) for k, v in d.get('standards', {}).items()}
        custom_thresholds = d.get('custom_thresholds', {})
        phenomena_config = d.get('phenomena_config', None)
        
        # 🌟 修复 1：去 export_config 里把前端藏好的日期挖出来！
        export_cfg = d.get('export_config', {})
        base_date_str = d.get('base_date_str') or export_cfg.get('base_date_str')
        
        issued_date = None
        if base_date_str:
            try:
                if '-' in base_date_str: 
                    issued_date = datetime.strptime(base_date_str, "%Y-%m-%d").date()
                else: 
                    issued_date = datetime.strptime(base_date_str[:8], "%Y%m%d").date()
            except Exception as e: 
                print(f"日期解析失败: {e}")

        # 🌟 修复 2：去掉“仅限席位预报”的束缚，全局接管前后 3 天的超大时间边界！
        s_str = d.get('start_time'); e_str = d.get('end_time')
        start_eval_dt = None; end_eval_dt = None

        if s_str and e_str:
            try:
                fmt_s = "%Y%m%d%H%M%S" if len(s_str) == 14 else ("%Y%m%d%H%M" if len(s_str) == 12 else "%Y%m%d")
                start_eval_dt = datetime.strptime(s_str, fmt_s).replace(tzinfo=timezone.utc)
                fmt_e = "%Y%m%d%H%M%S" if len(e_str) == 14 else ("%Y%m%d%H%M" if len(e_str) == 12 else "%Y%m%d")
                end_eval_dt = datetime.strptime(e_str, fmt_e).replace(tzinfo=timezone.utc)
            except Exception as e: 
                print(f"边界时间解析失败: {e}")

        raw_obs_list = []
        for line in obs_text.strip().split('\n'):
            if not line.strip(): continue
            parsed = parser.parse(line, for_scoring=True)
            if parsed and parsed.get('time'):
                raw_obs_list.append(parsed)

        results = {}
        assessor_cats = QualityAssessor(standards, phenomena_config)

        def aggregate_obs(reports):
            if not reports: return {}
            worst = min(reports, key=lambda r: (r.get('visibility', 9999), r.get('cloud_height', 9999) if r.get('cloud_height') is not None else 9999))
            wind = max([r.get('wind_speed', 0) for r in reports] or [0])
            bkn = [r for r in reports if r.get('cloud_amount') in ['BKN','OVC']]
            sct = [r for r in reports if r.get('cloud_amount') == 'SCT']
            cld_rep = min(bkn, key=lambda x:x['cloud_height']) if bkn else (min(sct, key=lambda x:x['cloud_height']) if sct else {})
            wx_cats = {}
            all_wx = [p for r in reports for p in (r.get('weather') or 'NSW').split()]
            for cat, codes in assessor_cats.phen_categories.items():
                rels = []
                for p in all_wx:
                    core_p = p.replace('+','').replace('-','')
                    if core_p in codes or ('TS' in codes and 'TS' in core_p): rels.append(p)
                if rels: wx_cats[cat] = max(rels, key=parser.get_weather_severity)
            return {'wind_speed': wind, 'visibility': worst.get('visibility', 9999), 'cloud': {'height': cld_rep.get('cloud_height'), 'amount_code': cld_rep.get('cloud_amount')}, 'weather': wx_cats}

        forecasts_map = {}
        forecasts_map = {}
        if mode == 'manual':
            raw_fcst = d.get('manual_forecasts', {})
            # 🌟 修复：直接获取前端传来的准确时效文本 (如: 未来24小时)
            time_range_text = d.get('time_range_text', '席位综合预报')
            for ap, hours_data in raw_fcst.items():
                fcsts = {h: parse_manual_forecast_text(txt) for h, txt in hours_data.items()}
                fcsts['__validity'] = time_range_text
                fcsts['__full_text'] = generate_forecast_summary(ap, fcsts, 'manual')
                forecasts_map[ap] = fcsts
        else:
            raw_taf_text = d.get('taf_text', '')
            parsed_tafs = parse_tafs(raw_taf_text, issued_date=issued_date)
            taf_blocks = re.split(r'(?=TAF(?:\s|AMD|COR))', raw_taf_text)
            
            # 🌟 需求2：智能提取与 AMD 排序机制
            recognize_amd = d.get('recognize_amd', False)
            temp_groups = {}
            for t in parsed_tafs:
                g_key = f"{t['airport']}_{t['validity_str']}"
                if g_key not in temp_groups: temp_groups[g_key] = []
                temp_groups[g_key].append(t)

            for group_key, t_list in temp_groups.items():
                if not recognize_amd:
                    # 🔴 模式A（关闭开关）：只考核真正的原报
                    original_t = None
                    original_raw = ""
                    for t in t_list:
                        # 提取这段报文对应的真实原始文本
                        raw_txt = ""
                        for b in taf_blocks:
                            if t['airport'] in b and t['validity_str'].replace('-', '/') in b:
                                raw_txt = b.strip(); break
                        
                        # 🔍 核心修复：精准定位！只有文本里没有 AMD 且没有 COR，才是真正的原报
                        if " AMD " not in raw_txt and " COR " not in raw_txt and not raw_txt.startswith("TAF AMD") and not raw_txt.startswith("TAF COR"):
                            original_t = t
                            original_raw = raw_txt
                            break
                            
                    if not original_t:
                        # ⚠️ 如果粘贴的这段时间里全是 AMD，没有原报（说明原报在昨天的文件里没粘过来）
                        # 那么直接跳过这组报文！保证不把 AMD 误当成原报评分！
                        continue
                        
                    fcsts = original_t['forecasts']
                    fcsts['__validity'] = original_t['validity_str']
                    fcsts['__full_text'] = original_raw if original_raw else f"TAF {original_t['airport']} {original_t['validity_str']}"
                    forecasts_map[group_key] = fcsts
                    
                else:
                    # 🟢 模式B（打开开关）：分离模式并智能标注
                    amd_counter = 1
                    for idx, t in enumerate(t_list):
                        matching_blocks = [b.strip() for b in taf_blocks if t['airport'] in b and t['validity_str'].replace('-', '/') in b]
                        raw_txt = matching_blocks[idx] if idx < len(matching_blocks) else (matching_blocks[-1] if matching_blocks else f"TAF {t['airport']} {t['validity_str']}")
                        
                        # 🔍 核心修复：通过文本内容定位，而不是依靠先后顺序
                        is_amd = " AMD " in raw_txt or " COR " in raw_txt or raw_txt.startswith("TAF AMD") or raw_txt.startswith("TAF COR")
                        
                        if not is_amd:
                            suffix = "" # 真正的原报，不加后缀
                        else:
                            suffix = f" (AMD-{amd_counter})"
                            amd_counter += 1 # 只有遇到 AMD 计数器才 +1
                            
                        unique_key = f"{group_key}{suffix}"
                        fcsts = t['forecasts']
                        fcsts['__validity'] = f"{t['validity_str']}{suffix}"
                        fcsts['__full_text'] = raw_txt
                        forecasts_map[unique_key] = fcsts

        for key, hourly_forecasts in forecasts_map.items():
            ap_code = key.split('_')[0]

            ap_obs = [r for r in raw_obs_list if r['station'] == ap_code]
            grouped_obs = {}
            for o in ap_obs:
                time_str = o['time'] 
                if len(time_str) >= 4:
                    ddhh = time_str[:4]
                    grouped_obs.setdefault(ddhh, []).append(o)
            
            final_obs_agg = {h: aggregate_obs(reps) for h, reps in grouped_obs.items()}
            
            sorted_hours = []
            if start_eval_dt and end_eval_dt:
                temp_list = []
                for h_str in hourly_forecasts.keys():
                    if h_str.startswith('__'): continue # 🌟 修复：过滤掉隐藏属性
                    try:
                        dt_val = _parse_ddhhmm_to_datetime(h_str + "00", start_eval_dt)
                        if start_eval_dt <= dt_val <= end_eval_dt:
                            temp_list.append((dt_val, h_str))
                    except Exception as e: 
                        pass
                
                temp_list.sort(key=lambda x: x[0])
                sorted_hours = [x[1] for x in temp_list]
            else:
                sorted_hours = [k for k in sorted(list(hourly_forecasts.keys())) if not k.startswith('__')] # 🌟 修复：过滤

            df_s, df_o, stats = run_evaluation(hourly_forecasts, final_obs_agg, standards, ap_obs, phenomena_config, sorted_hours_list=sorted_hours, ap_code=ap_code, custom_thresholds=custom_thresholds)
            
            if df_s.empty: continue
            res_entry = {'scores': df_s.reset_index().to_dict('records'), 'observations': df_o.reset_index().to_dict('records'), 'statistics': stats}
            if mode == 'taf':
                # 🌟 修复：过滤掉隐藏属性，只拿真实的时次字典去格式化
                res_entry['recognized_forecasts'] = [{"hour": h, "text": format_forecast_for_display(hourly_forecasts[h])} for h in sorted(hourly_forecasts.keys()) if not h.startswith('__')]
                res_entry['forecast_summary_bjt'] = generate_forecast_summary(ap_code, hourly_forecasts, 'taf')
            else:
                res_entry['forecast_summary_bjt'] = generate_forecast_summary(ap_code, hourly_forecasts, 'manual')
            results[key] = res_entry

        return jsonify({"success": True, "data": results})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

# 需求3：使用 Tkinter 原生弹出目录选择器
@app.route('/api/select_folder', methods=['GET'])
def select_folder_api():
    try:
        import tkinter as tk
        from tkinter import filedialog
        
        # 创建一个隐藏的 tk 根窗口
        root = tk.Tk()
        root.withdraw()
        # 强制窗口在最顶层
        root.attributes('-topmost', True)
        
        folder_path = filedialog.askdirectory(title="选择保存评定文件的目录")
        root.destroy()
        
        return jsonify({"success": True, "path": folder_path})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

# 🌟 修复：获取当前电脑桌面绝对路径的接口（读取注册表穿透 D盘 / OneDrive）
@app.route('/api/get_desktop_path', methods=['GET'])
def get_desktop_path():
    import os
    import winreg
    desktop_dir = ""
    try:
        # 🌟 核心修复3：直接读取 Windows 注册表，无论桌面被移动到 D 盘还是哪里，都能精准定位！
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
        reg_path, _ = winreg.QueryValueEx(key, "Desktop")
        winreg.CloseKey(key)
        # 解析 %USERPROFILE% 等环境变量，得到最终真实绝对路径
        desktop_dir = os.path.expandvars(reg_path) 
    except Exception:
        # 备选方案：常规路径和 OneDrive 路径
        user_profile = os.path.expanduser("~")
        onedrive_desktop = os.path.join(user_profile, 'OneDrive', 'Desktop')
        if os.path.exists(onedrive_desktop):
            desktop_dir = onedrive_desktop
        else:
            desktop_dir = os.path.join(user_profile, 'Desktop')
    
    # 强制在桌面创建一个显眼的专属文件夹
    final_path = os.path.join(desktop_dir, 'SF预报评定导出')
    os.makedirs(final_path, exist_ok=True)
    return jsonify({"success": True, "path": final_path})


def _resolve_desktop_dir():
    """复用：winreg 穿透 OneDrive 定位真实物理桌面目录。"""
    import winreg
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
        reg_path, _ = winreg.QueryValueEx(key, "Desktop")
        winreg.CloseKey(key)
        return os.path.expandvars(reg_path)
    except Exception:
        user_profile = os.path.expanduser("~")
        onedrive_desktop = os.path.join(user_profile, 'OneDrive', 'Desktop')
        return onedrive_desktop if os.path.exists(onedrive_desktop) else os.path.join(user_profile, 'Desktop')


@app.route('/api/import_publish_excel', methods=['POST'])
def import_publish_excel_api():
    """Read the 24-hour publish worksheet without modifying the source workbook."""
    try:
        import openpyxl
        from datetime import date as date_type, time as time_type

        upload = request.files.get('file')
        # 席位预报可按评定日期自动读取前一天的 24 小时预报表。
        auto_root = (request.form.get('manual_forecast_path') or '').strip()
        evaluation_date = (request.form.get('evaluation_date') or '').strip()
        if upload and upload.filename:
            workbook_source = upload.stream
            source_name = os.path.basename(upload.filename)
        else:
            if auto_root and evaluation_date:
                try:
                    eval_day = datetime.strptime(evaluation_date, '%Y-%m-%d').date()
                    target_day = eval_day - timedelta(days=1)
                    folder = os.path.join(auto_root, f'{target_day.year}年', f'{target_day.month}月')
                    stem = f'未来24小时天气预报{target_day:%Y%m%d}'
                    candidates = [os.path.join(folder, stem + ext) for ext in ('.xlsm', '.xlsx', '.xls')]
                    workbook_source = next((p for p in candidates if os.path.isfile(p)), '')
                    if not workbook_source:
                        return jsonify({"success": False, "error": f"未找到席位预报表：{os.path.join(folder, stem + '.xlsm')}"}), 200
                    source_name = os.path.basename(workbook_source)
                except ValueError:
                    return jsonify({"success": False, "error": "评定日期格式无效，应为 YYYY-MM-DD"}), 200
            else:
                source_name = '未来24小时天气预报20260725.xlsm'
                workbook_source = os.path.join(_PERSIST_DIR, source_name)
            if not os.path.exists(workbook_source):
                return jsonify({"success": False, "error": f"未找到根目录模板：{source_name}"}), 200

        wb = openpyxl.load_workbook(workbook_source, data_only=True, read_only=False)
        try:
            ws = wb['24小时天气预报'] if '24小时天气预报' in wb.sheetnames else wb.active

            header_row = None
            for row_idx in range(1, min(ws.max_row, 80) + 1):
                if str(ws.cell(row_idx, 1).value or '').strip() == '名称' and str(ws.cell(row_idx, 2).value or '').strip() == '性质':
                    header_row = row_idx
                    break
            if header_row is None:
                for row_idx in range(1, min(ws.max_row, 100) + 1):
                    first = str(ws.cell(row_idx, 1).value or '').replace(' ', '').strip()
                    second = str(ws.cell(row_idx, 2).value or '').replace(' ', '').strip()
                    if '名称' in first and '性质' in second:
                        header_row = row_idx
                        break
            if header_row is None:
                raise ValueError('未找到“名称/性质”表头，无法识别预报数据区')

            if header_row is None:
                # 兼容第二份模板：标题文字可能不同，但结构仍是机场/性质/备注，
                # 下一行包含逐小时预报时段。
                for row_idx in range(1, min(ws.max_row, 100)):
                    first = str(ws.cell(row_idx, 1).value or '').strip()
                    second = str(ws.cell(row_idx, 2).value or '').strip()
                    third = str(ws.cell(row_idx, 3).value or '').strip()
                    next_values = [ws.cell(row_idx + 1, col).value for col in range(4, min(ws.max_column, 12) + 1)]
                    time_like = sum(isinstance(v, (datetime, date_type, time_type)) or isinstance(v, (int, float)) for v in next_values)
                    if first and second and third and time_like >= 2:
                        header_row = row_idx
                        break
            if header_row is None:
                raise ValueError('未找到有效的机场/性质/备注表头，无法识别预报表')

            data_start_col = 4
            duration_row = max(1, header_row - 1)
            hour_columns = []
            for col_idx in range(data_start_col, ws.max_column + 1):
                value = ws.cell(duration_row, col_idx).value
                if value is None or str(value).strip() == '':
                    if hour_columns:
                        break
                    continue
                hour_columns.append(col_idx)
            if not hour_columns:
                raise ValueError('未找到逐小时预报列')

            forecast_date = None
            start_hour_bjt = None

            def parse_date_value(value):
                if isinstance(value, (datetime, date_type)):
                    return value.strftime('%Y-%m-%d')
                text = str(value or '').strip()
                for pattern in (r'(20\d{2})[年\-/](\d{1,2})[月\-/](\d{1,2})', r'(20\d{2})(\d{2})(\d{2})'):
                    match = re.search(pattern, text)
                    if match:
                        try:
                            return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3))).strftime('%Y-%m-%d')
                        except ValueError:
                            pass
                return None

            def parse_hour_value(value):
                if isinstance(value, datetime):
                    return value.hour
                if isinstance(value, time_type):
                    return value.hour
                if isinstance(value, (int, float)):
                    number = float(value)
                    if 0 <= number < 1:
                        return int(round(number * 24)) % 24
                    if 0 <= number <= 23 and number.is_integer():
                        return int(number)
                text = str(value or '').strip()
                match = re.search(r'(\d{1,2})\s*(?:时|:|：)', text)
                if match:
                    return int(match.group(1)) % 24
                match = re.search(r'\b(\d{1,2})(?:00|时)?\b', text)
                if match and 0 <= int(match.group(1)) <= 23:
                    return int(match.group(1))
                return None
            eval_person = ''
            for row_idx in range(1, header_row + 1):
                label = str(ws.cell(row_idx, 1).value or '').strip()
                if label in ('评定对象', '预报员', '预报人员', '姓名', '制作人'):
                    for col_idx in range(2, min(ws.max_column, 8) + 1):
                        candidate = cell_text(ws.cell(row_idx, col_idx).value) if 'cell_text' in locals() else str(ws.cell(row_idx, col_idx).value or '').strip()
                        if candidate:
                            eval_person = candidate
                            break
                # 模板中“预报员”可能位于任意列，评定对象取其后一个单元格。
                if not eval_person:
                    labels = ('预报员', '评定对象', '预报人员', '姓名', '制作人')
                    ignored_values = labels + ('备注', '日期', '起报时间', '影响机场', '预报时段', '预报时刻')
                    for col_idx in range(1, ws.max_column):
                        label_text = str(ws.cell(row_idx, col_idx).value or '').strip().rstrip(':：')
                        if label_text not in labels:
                            continue
                        # 模板存在合并单元格，值可能不在紧邻单元格，向后找若干格并跳过其它字段标签。
                        for next_col in range(col_idx + 1, min(ws.max_column, col_idx + 6) + 1):
                            candidate = str(ws.cell(row_idx, next_col).value or '').strip()
                            if not candidate or candidate.rstrip(':：') in ignored_values:
                                continue
                            eval_person = candidate
                            break
                        if eval_person:
                            break
                if label.startswith('日期'):
                    for col_idx in range(2, min(ws.max_column, 8) + 1):
                        value = ws.cell(row_idx, col_idx).value
                        parsed = parse_date_value(value)
                        if parsed:
                            forecast_date = parsed
                            break
                elif label == '起报时间':
                    for col_idx in range(2, min(ws.max_column, 8) + 1):
                        value = ws.cell(row_idx, col_idx).value
                        parsed = parse_hour_value(value)
                        if parsed is not None:
                            start_hour_bjt = parsed
                            break

            def cell_text(value):
                if value is None:
                    return ''
                if isinstance(value, float) and value.is_integer():
                    return str(int(value))
                return str(value).strip()

            # Some exported workbooks preserve the values but not the exact
            # label text. Read the actual date/time cells in the header area
            # as a structural fallback (date row near the top, start time row
            # immediately before the airport header).
            if not forecast_date:
                for row_idx in range(1, min(header_row, 8) + 1):
                    for col_idx in range(1, min(ws.max_column, 8) + 1):
                        value = ws.cell(row_idx, col_idx).value
                        parsed = parse_date_value(value)
                        if parsed:
                            forecast_date = parsed
                            break
                    if forecast_date:
                        break
            if start_hour_bjt is None:
                for row_idx in range(max(1, header_row - 3), header_row):
                    for col_idx in range(1, min(ws.max_column, 8) + 1):
                        value = ws.cell(row_idx, col_idx).value
                        parsed = parse_hour_value(value)
                        if parsed is not None:
                            start_hour_bjt = parsed
                            break
                    if start_hour_bjt is not None:
                        break

            entries = []
            current = None
            special_condition_text = ''
            special_condition_markers = ('地面结冰', '地面积冰', '极寒条件', '极寒机场', '极寒')
            for r in range(1, ws.max_row + 1):
                row_values = [cell_text(ws.cell(r, c).value) for c in range(1, ws.max_column + 1)]
                joined = ' '.join(v for v in row_values if v)
                if any(marker in joined for marker in special_condition_markers):
                    label_pos = next((i for i, v in enumerate(row_values) if any(marker in v for marker in special_condition_markers)), 0)
                    tail = ' '.join(v for v in row_values[label_pos + 1:] if v)
                    # 兼容标签与内容写在同一个单元格、以及没有括号分类的人工编辑文本。
                    special_condition_text = tail or joined
                    break
            stop_labels = ('地面结冰', '地面积冰', '极寒条件', '极寒机场', '颜色说明', '发布说明')
            for row_idx in range(header_row + 1, ws.max_row + 1):
                airport_name = cell_text(ws.cell(row_idx, 1).value)
                nature = cell_text(ws.cell(row_idx, 2).value)
                note = cell_text(ws.cell(row_idx, 3).value)
                if airport_name and airport_name.startswith(stop_labels):
                    break
                cells = [cell_text(ws.cell(row_idx, col_idx).value) for col_idx in hour_columns]
                if not airport_name and not note and not any(cells):
                    continue
                if airport_name:
                    current = {"airport_name": airport_name, "nature": nature, "rows": [], "notes": []}
                    entries.append(current)
                elif current is None:
                    continue
                current["rows"].append(cells)
                current["notes"].append(note or '/')

            # 导出文件有时只在文件名中保留日期，起报时间则没有单独标签；
            # 这种文件按文件名日期读取，并以 00 时作为默认起报时刻。
            if not forecast_date:
                match = re.search(r'(20\d{6})', source_name)
                if match:
                    forecast_date = datetime.strptime(match.group(1), '%Y%m%d').strftime('%Y-%m-%d')
            # 两种模板都可能只在文件名中保留日期，或将起报时间写在“预报时刻”行。
            # 对整个表头区域再做一次结构化扫描，避免依赖固定标签/列位置。
            if start_hour_bjt is None:
                for row_idx in range(1, min(header_row + 1, 20)):
                    for col_idx in range(1, min(ws.max_column + 1, 12)):
                        parsed = parse_hour_value(ws.cell(row_idx, col_idx).value)
                        if parsed is not None and row_idx < header_row:
                            start_hour_bjt = parsed
                            break
                    if start_hour_bjt is not None:
                        break
            if start_hour_bjt is None:
                # 24 小时模板的标准起报时刻为表头前一行的第一个时间值；
                # 若模板确实没有该值，按文件名日期配合 15 时兜底，保证可导入并允许后续修改。
                start_hour_bjt = 15
            if not entries:
                raise ValueError('表格中没有可导入的机场预报')
            return jsonify({
                "success": True,
                "data": {
                    "source": source_name,
                    "publish_date": (target_day.isoformat() if auto_root and evaluation_date else forecast_date),
                    "sheet": ws.title,
                    "forecast_date": forecast_date,
                    "start_hour_bjt": start_hour_bjt,
                    "validity_hours": max(0, len(hour_columns) - 1),
                    "eval_person": eval_person,
                    "special_condition_text": special_condition_text,
                    "airports": entries
                }
            })
        finally:
            wb.close()
    except Exception as exc:
        LOG.exception('导入发布表格失败: %s', exc)
        return jsonify({"success": False, "error": str(exc)}), 200


@app.route('/api/export_publish', methods=['POST'])
def export_publish_api():
    """预报发布导出：图片/Excel 分离；Excel 不依赖外部模板，按模板观感直接生成。"""
    import base64
    try:
        data = request.json or {}
        mode = (data.get('mode') or 'both').lower()
        images_b64 = data.get('images') or []
        image_b64 = data.get('image', '')
        if image_b64 and not images_b64:
            images_b64 = [image_b64]
        rows = data.get('data', []) or []
        publish_rows = data.get('publish_rows', []) or []
        export_path = (data.get('export_path') or '').strip()
        start_date = (data.get('start_date') or '').strip()
        start_hour = data.get('start_hour')
        forecaster = data.get('forecaster') or ''
        icing_text = data.get('icing_text') or '无'
        validity_hours = int(data.get('validity_hours') or 24)
        hour_count = validity_hours + 1

        if export_path:
            target_dir = export_path
        else:
            target_dir = os.path.join(_resolve_desktop_dir(), 'SF预报发布导出')
        try:
            os.makedirs(target_dir, exist_ok=True)
        except Exception as e:
            LOG.error("导出目录创建失败 %s: %s", target_dir, e)
            return jsonify({"success": False, "error": f"导出目录无法创建: {target_dir} ({e})"}), 200

        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        saved = []

        # 图片导出：支持前端分页切割后的多张图片。
        if mode in ('image', 'both', '') and images_b64:
            for idx, img in enumerate(images_b64, start=1):
                try:
                    if ',' in img:
                        img = img.split(',', 1)[1]
                    suffix = f'_第{idx}页' if len(images_b64) > 1 else ''
                    png_path = os.path.join(target_dir, f'24小时天气预报_{ts}{suffix}.png')
                    with open(png_path, 'wb') as f:
                        f.write(base64.b64decode(img))
                    saved.append(png_path)
                except Exception as e:
                    LOG.exception("保存预报发布图片失败: %s", e)
                    return jsonify({"success": False, "error": f"预报发布图片写入失败: {e}"}), 200

        def normalize_publish_rows():
            data_rows = []
            if publish_rows:
                last_airport_key = ''
                for item in publish_rows:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get('name') or '').strip()
                    is_continuation = bool(item.get('continuation'))
                    airport_key = str(item.get('icao') or name or last_airport_key).strip()
                    if name:
                        last_airport_key = airport_key
                    elif not is_continuation or not airport_key:
                        continue
                    ap_type = str(item.get('type') or ('' if is_continuation else '普通')).strip()
                    note = str(item.get('note') or '').strip()
                    vals = [str(v or '').strip() for v in (item.get('values') or [])[:hour_count]]
                    if len(vals) < hour_count:
                        vals += [''] * (hour_count - len(vals))
                    data_rows.append({
                        'airport_key': airport_key,
                        'name': name,
                        'type': ap_type,
                        'note': note,
                        'values': vals,
                    })
            else:
                last_airport_key = ''
                for row in rows:
                    if not row or len(row) < 4:
                        continue
                    name = str(row[0] or '').strip()
                    ap_type = str(row[1] or '').strip()
                    marker = str(row[2] or '').strip()
                    if name in ('名称', '影响机场') or ap_type in ('性质', ''):
                        continue
                    if name in ('TAF', 'EC', '天气', '风', '能见度', '温度', '气压') or marker in ('TAF', 'EC'):
                        continue
                    vals = [str(v or '').strip() for v in row[4:4+hour_count]]
                    if len(vals) < hour_count:
                        vals += [''] * (hour_count - len(vals))
                    if not any(vals) and marker not in ('适航', '/'):
                        continue
                    last_airport_key = name or last_airport_key
                    data_rows.append({
                        'airport_key': last_airport_key,
                        'name': name,
                        'type': ap_type or ('普通' if name else ''),
                        'note': str(row[3] or '').strip(),
                        'values': vals,
                    })
            return data_rows

        # Excel 导出：按用户提供的 xlsm 模板观感复刻，不依赖模板文件。
        if mode in ('excel', 'both', '') and (rows or publish_rows):
            try:
                import openpyxl
                from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
                from openpyxl.utils import get_column_letter

                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = '24小时天气预报'

                # 模板观感：深灰标题、风险色块、细边框、24小时表格+尾部说明。
                dark = PatternFill('solid', fgColor='4B5563')
                white = PatternFill('solid', fgColor='FFFFFF')
                ts_fill = PatternFill('solid', fgColor='DC2626')
                wind_fill = PatternFill('solid', fgColor='2563EB')
                snow_fill = PatternFill('solid', fgColor='64748B')
                vis_fill = PatternFill('solid', fgColor='FDE047')
                rain_fill = PatternFill('solid', fgColor='16A34A')
                heavy_rain_fill = PatternFill('solid', fgColor='0F766E')
                cloud_fill = PatternFill('solid', fgColor='F59E0B')
                other_fill = PatternFill('solid', fgColor='BAE6FD')
                font_name = '\u5fae\u8f6f\u96c5\u9ed1'
                white_font = Font(name=font_name, color='FFFFFF', bold=True)
                black_font = Font(name=font_name, color='111827')
                title_font = Font(name=font_name, size=48, bold=True, color='FFFFFF')
                bold_font = Font(name=font_name, bold=True, color='111827')
                thin = Side(style='thin', color='95A5A6')
                med = Side(style='medium', color='34495E')
                thick = Side(style='medium', color='000000')
                border = Border(left=thin, right=thin, top=thin, bottom=thin)
                center = Alignment(horizontal='center', vertical='center', wrap_text=True)
                center_nowrap = Alignment(horizontal='center', vertical='center', wrap_text=False)

                bjt = None
                try:
                    if start_date and start_hour is not None:
                        bjt = datetime.strptime(f"{start_date} {int(start_hour):02d}", '%Y-%m-%d %H') + timedelta(hours=8)
                except Exception:
                    bjt = None
                if bjt is None:
                    bjt = datetime.now()

                max_hours = min(hour_count, 25)
                end_col = 3 + max_hours  # 24??+?????? AB
                data_rows = normalize_publish_rows()

                def fill_for(value):
                    v = value or ''
                    if not v or v in ('\u2014', '/', '\u9002\u822a'):
                        return None, black_font
                    if '\u96f7' in v or '\u96f9' in v:
                        return ts_fill, white_font
                    if any(k in v for k in ('\u5927\u96e8', '\u66b4\u96e8', '\u5f3a\u964d\u6c34')):
                        return heavy_rain_fill, white_font
                    if '\u96e8' in v:
                        return rain_fill, white_font
                    if '\u96ea' in v or '\u51bb\u96e8' in v or '\u51b0' in v:
                        return snow_fill, white_font
                    if '\u4f4e\u4e91' in v:
                        return cloud_fill, white_font
                    if v.startswith('W') or '\u5927\u98ce' in v or '\u98ce' in v:
                        return wind_fill, white_font
                    if v.isdigit() or '\u4f4e\u80fd\u89c1\u5ea6' in v or '\u96fe' in v or '\u973e' in v or '\u6c99' in v or '\u5c18' in v:
                        return vis_fill, black_font
                    return other_fill, black_font

                legend_defs = [
                    ('\u96f7\u66b4', ts_fill, white_font, lambda v: '\u96f7' in v or '\u96f9' in v),
                    ('\u5927\u98ce', wind_fill, white_font, lambda v: v.startswith('W') or '\u5927\u98ce' in v or '\u98ce' in v),
                    ('\u964d\u96ea', snow_fill, white_font, lambda v: '\u96ea' in v or '\u51bb\u96e8' in v or '\u51b0' in v),
                    ('\u5f3a\u964d\u6c34', heavy_rain_fill, white_font, lambda v: any(k in v for k in ('\u5927\u96e8', '\u66b4\u96e8', '\u5f3a\u964d\u6c34'))),
                    ('\u4f4e\u80fd\u89c1\u5ea6', vis_fill, black_font, lambda v: v.isdigit() or '\u4f4e\u80fd\u89c1\u5ea6' in v or '\u96fe' in v or '\u973e' in v or '\u6c99' in v or '\u5c18' in v),
                    ('\u4f4e\u4e91', cloud_fill, white_font, lambda v: '\u4f4e\u4e91' in v),
                    ('\u5176\u4ed6', other_fill, black_font, lambda v: bool(v) and fill_for(v)[0] == other_fill),
                ]
                count_map = {
                    label: len({
                        row['airport_key'] for row in data_rows
                        if row['airport_key'] and any(pred(v or '') for v in row['values'][:max_hours])
                    })
                    for label, _, _, pred in legend_defs
                }

                # 1-5????????/???????????????
                ws.merge_cells(start_row=1, start_column=1, end_row=2, end_column=end_col)
                ws['A1'] = '\u672a\u676524\u5c0f\u65f6\u5929\u6c14\u9884\u62a5' if validity_hours == 24 else f'\u672a\u6765{validity_hours}\u5c0f\u65f6\u5929\u6c14\u9884\u62a5'
                ws['A1'].font = title_font
                ws['A1'].alignment = center
                for r in range(1, 6):
                    for c in range(1, end_col + 1):
                        ws.cell(r, c).fill = dark
                        ws.cell(r, c).alignment = center

                # ?3-4??????????2???D?AB????????????????
                legend_cols = [4, 7, 10, 13, 16, 19, 22]
                for (label, fill, font, _), c in zip(legend_defs, legend_cols):
                    if c + 1 > end_col:
                        break
                    ws.merge_cells(start_row=3, start_column=c, end_row=4, end_column=c+1)
                    cell = ws.cell(3, c)
                    cell.value = f'{label}\n{count_map.get(label, 0)}'
                    cell.fill = fill
                    cell.font = font
                    cell.alignment = center

                ws.merge_cells(start_row=4, start_column=1, end_row=5, end_column=2)
                ws.merge_cells(start_row=4, start_column=3, end_row=5, end_column=3)
                ws['A4'] = '\u65e5\u671f\uff08\u5317\u4eac\u65f6\uff09'
                ws['C4'] = f'{bjt.year}\u5e74{bjt.month}\u6708{bjt.day}\u65e5'
                ws['A4'].font = white_font
                ws['C4'].font = white_font
                ws['C4'].alignment = center_nowrap
                forecaster_label_col = max(4, end_col - 3)
                ws.merge_cells(start_row=5, start_column=forecaster_label_col, end_row=5, end_column=forecaster_label_col + 1)
                ws.merge_cells(start_row=5, start_column=forecaster_label_col + 2, end_row=5, end_column=end_col)
                ws.cell(5, forecaster_label_col).value = '\u9884\u62a5\u5458\uff1a'
                ws.cell(5, forecaster_label_col + 2).value = forecaster
                ws.cell(5, forecaster_label_col).font = white_font
                ws.cell(5, forecaster_label_col + 2).font = white_font
                ws.cell(5, forecaster_label_col).alignment = center
                ws.cell(5, forecaster_label_col + 2).alignment = center

                # 6-8??????????????
                ws.merge_cells(start_row=6, start_column=1, end_row=6, end_column=2)
                ws['A6'] = '\u8d77\u62a5\u65f6\u95f4'
                ws['C6'] = f'{bjt.hour}\u65f6'
                ws.merge_cells(start_row=7, start_column=1, end_row=7, end_column=2)
                ws['A7'] = '\u5f71\u54cd\u673a\u573a'
                ws['A8'] = '\u540d\u79f0'
                ws['B8'] = '\u6027\u8d28'
                ws['C7'] = '\u9884\u62a5\u65f6\u957f\u2192'
                ws['C8'] = '\u9884\u62a5\u65f6\u523b\u2192'
                for i in range(max_hours):
                    c = 4 + i
                    ws.cell(7, c).value = i
                    ws.cell(8, c).value = f'{(bjt.hour + i) % 24}\u65f6'
                for r in range(6, 9):
                    for c in range(1, end_col + 1):
                        cell = ws.cell(r, c)
                        cell.fill = dark
                        cell.font = white_font
                        cell.alignment = center
                        cell.border = border

                # ???????????3?????????????????????????????
                max_text_len = max([len(str(v or '')) for row in data_rows for v in row['values'][:max_hours]] + [0])
                data_font_size = 11 if max_text_len <= 3 else (10 if max_text_len <= 4 else (9 if max_text_len <= 6 else 8))

                start_row = 9
                for idx, row in enumerate(data_rows, start=start_row):
                    name = row['name']
                    ap_type = row['type']
                    vals = row['values']
                    ws.cell(idx, 1).value = name
                    ws.cell(idx, 2).value = ap_type
                    ws.cell(idx, 3).value = row['note']
                    for c in (1, 2, 3):
                        ws.cell(idx, c).fill = white
                        ws.cell(idx, c).font = bold_font if c == 1 else black_font
                        ws.cell(idx, c).alignment = center
                        ws.cell(idx, c).border = border
                    for j in range(max_hours):
                        value = vals[j] if j < len(vals) else ''
                        value = '' if value in ('\u2014', '/') else value
                        cell = ws.cell(idx, 4 + j)
                        cell.value = value
                        fill, font = fill_for(value)
                        cell.fill = fill or white
                        cell.font = Font(name=font_name, size=data_font_size, bold=True, color=(font.color.rgb[-6:] if getattr(font.color, 'rgb', None) else '111827'))
                        cell.alignment = center_nowrap
                        cell.border = border

                tail_start = start_row + max(len(data_rows), 1) + 1
                ws.merge_cells(start_row=tail_start, start_column=1, end_row=tail_start, end_column=3)
                ws.cell(tail_start, 1).value = '\u5730\u9762\u7ed3\u51b0\u6761\u4ef6/\u6781\u5bd2\u6761\u4ef6'
                ws.cell(tail_start, 1).font = bold_font
                ws.cell(tail_start, 1).alignment = center
                ws.merge_cells(start_row=tail_start, start_column=4, end_row=tail_start, end_column=end_col)
                ws.cell(tail_start, 4).value = icing_text or '\u65e0'
                ws.cell(tail_start, 4).font = bold_font
                ws.cell(tail_start, 4).alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)

                color_row = tail_start + 1
                ws.merge_cells(start_row=color_row, start_column=1, end_row=color_row, end_column=3)
                ws.cell(color_row, 1).value = '\u989c\u8272\u8bf4\u660e'
                ws.cell(color_row, 1).font = bold_font
                ws.cell(color_row, 1).alignment = center
                col = 4
                for label, fill, font, _ in legend_defs:
                    if col > end_col:
                        break
                    ws.cell(color_row, col).fill = fill
                    ws.cell(color_row, col).border = Border(top=thin, bottom=thin)
                    desc_end = min(end_col, col + 2)
                    if col + 1 <= desc_end:
                        ws.merge_cells(start_row=color_row, start_column=col+1, end_row=color_row, end_column=desc_end)
                        ws.cell(color_row, col+1).value = label
                        ws.cell(color_row, col+1).alignment = center
                        ws.cell(color_row, col+1).font = black_font
                    col += 3
                for c in range(1, end_col + 1):
                    ws.cell(color_row, c).border = Border(top=thin, bottom=thin)

                notes = [
                    '1. \u672c\u8868\u7ed3\u8bba\u4f9d\u636e\u6570\u503c\u9884\u62a5\u548c\u8fd0\u884c\u673a\u573aTAF\u62a5\u6587\u7efc\u5408\u5206\u6790\uff0c\u5982\u6709\u7591\u95ee\u54a8\u8be2AOC\u6c14\u8c61\u670d\u52a1\u5e2d\u3002',
                    '2. \u80fd\u89c1\u5ea6\u548c\u4e91\u9ad8\u5355\u4f4d\u4e3a\u201c\u7c73\u201d\u3001\u98ce\u901f\u5355\u4f4d\u4e3a\u201c\u7c73/\u79d2\u201d\u3002',
                    '3. \u5927\u98ce\u8868\u793a\u8be5\u65f6\u6b21\u9884\u671f\u6700\u5927\u9635\u98ce\u503c\uff0c\u4f8b\u5982\u201c\u504f\u5317\u98ce17\u7c73/\u79d2\u201d\u6216\u201c\u897f\u5317\u98ce20\u7c73/\u79d2\u201d\u3002'
                ]
                note_start = color_row + 1
                ws.merge_cells(start_row=note_start, start_column=1, end_row=note_start + len(notes) - 1, end_column=3)
                ws.cell(note_start, 1).value = '\u53d1\u5e03\u8bf4\u660e'
                ws.cell(note_start, 1).font = bold_font
                ws.cell(note_start, 1).alignment = center
                for i, note in enumerate(notes):
                    r = note_start + i
                    ws.merge_cells(start_row=r, start_column=4, end_row=r, end_column=end_col)
                    ws.cell(r, 4).value = note
                    ws.cell(r, 4).alignment = Alignment(horizontal='left', vertical='center', wrap_text=False)
                    for c in range(1, end_col + 1):
                        ws.cell(r, c).border = border

                # ????????????/????????????
                for c in range(1, end_col + 1):
                    ws.cell(tail_start, c).border = border

                last_row = note_start + len(notes) - 1

                # ???????????????????????????
                for c in range(1, end_col + 1):
                    top_cell = ws.cell(1, c)
                    top_cell.border = Border(left=top_cell.border.left, right=top_cell.border.right, top=thick, bottom=top_cell.border.bottom)
                    bottom_cell = ws.cell(last_row, c)
                    bottom_cell.border = Border(left=bottom_cell.border.left, right=bottom_cell.border.right, top=bottom_cell.border.top, bottom=thick)
                for r in range(1, last_row + 1):
                    left_cell = ws.cell(r, 1)
                    right_cell = ws.cell(r, end_col)
                    left_cell.border = Border(left=thick, right=left_cell.border.right, top=left_cell.border.top, bottom=left_cell.border.bottom)
                    right_cell.border = Border(left=right_cell.border.left, right=thick, top=right_cell.border.top, bottom=right_cell.border.bottom)

                for r in range(1, 6):
                    c_cell = ws.cell(r, 3)
                    d_cell = ws.cell(r, 4)
                    c_cell.border = Border(left=c_cell.border.left, right=Side(style=None), top=c_cell.border.top, bottom=c_cell.border.bottom)
                    d_cell.border = Border(left=Side(style=None), right=d_cell.border.right, top=d_cell.border.top, bottom=d_cell.border.bottom)

                for c in range(1, end_col + 1):
                    if c == 1:
                        width = 15
                    elif c == 2:
                        width = 12
                    elif c == 3:
                        width = 19
                    else:
                        width = 6.2
                    ws.column_dimensions[get_column_letter(c)].width = width
                ws.row_dimensions[1].height = 58
                ws.row_dimensions[2].height = 18
                ws.row_dimensions[3].height = 26
                ws.row_dimensions[4].height = 26
                for r in range(5, last_row + 1):
                    ws.row_dimensions[r].height = 22
                ws.freeze_panes = 'A9'  # 取消 A/B/C 列左侧冻结，仅保留 1-8 行顶部冻结
                ws.sheet_view.showGridLines = False

                xlsx_path = os.path.join(target_dir, f'24小时天气预报_{ts}.xlsx')
                date_match = re.search(r'(20\d{2})[-/]?(\d{2})[-/]?(\d{2})', str(start_date or ''))
                file_date = ''.join(date_match.groups()) if date_match else datetime.now().strftime('%Y%m%d')
                desired_xlsx_path = os.path.join(target_dir, f'未来24小时天气预报{file_date}.xlsx')
                xlsx_path = desired_xlsx_path
                wb.save(xlsx_path)
                saved.append(xlsx_path)
            except Exception as e:
                LOG.exception("保存预报发布 Excel 失败: %s", e)
                return jsonify({"success": False, "error": f"预报发布 Excel 写入失败: {e}"}), 200

        if not saved:
            return jsonify({"success": False, "error": "没有可导出的图片或表格数据"}), 200

        LOG.info("预报发布导出成功: %s", target_dir)
        return jsonify({"success": True, "path": target_dir, "files": [os.path.basename(p) for p in saved]})
    except Exception as e:
        LOG.exception("export_publish 异常: %s", e)
        return jsonify({"success": False, "error": str(e)}), 200

# === 新增：手动保存接口 (替换 payload 为 data 解决报错) ===
@app.route('/api/save_score', methods=['POST'])
def save_score_api():
    try:
        data = request.json
        results = data.get('results')
        mode = data.get('forecast_mode')
        export_config = data.get('export_config', {})
        
        backup_path = export_config.get('backup_path', '')
        # 🌟 核心修复：如果前端传来的是空字符串(普通人员或未配置)，强行兜底到程序目录的 backup 文件夹！
        if not backup_path: 
            backup_path = os.path.join(os.getcwd(), 'backup')
            
        excel_root = export_config.get('excel_root', '')
        eval_person = export_config.get('eval_person', '未指定人员')
        base_date_str = export_config.get('base_date_str', '')
        rater = export_config.get('rater', '未知') # 🌟 提取评分人
        
        # === 🌟 修复关键：兼容性导入必须放在调用之前 ===
        try:
            from .logic.exporter import process_stats_and_save
        except ImportError:
            from backend.logic.exporter import process_stats_and_save

        # 🌟 并且只调用一次，带有完整的 rater 参数
        saved_file = process_stats_and_save(results, mode, backup_path, excel_root, eval_person, base_date_str, rater)
        
        return jsonify({
            "success": True,
            "message": "保存成功！",
            "file_path": saved_file,
            "folder_path": os.path.dirname(saved_file)
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/open_folder', methods=['POST'])
def open_folder_api():
    try:
        folder_path = os.path.abspath(os.path.normpath(str((request.json or {}).get('path', '')).strip()))
        if not os.path.isdir(folder_path):
            return jsonify({"success": False, "error": "保存文件夹不存在"}), 400
        if os.name != 'nt':
            return jsonify({"success": False, "error": "当前系统不支持资源管理器打开文件夹"}), 400
        os.startfile(folder_path)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# 🌟 找回失落的接口：日数据明细查询
@app.route('/api/query_raw_data', methods=['POST'])
def query_raw_data_api():
    try:
        data = request.json
        s_type = data.get('stats_type') 
        person = data.get('person')
        airport = data.get('airport', '').strip().upper()
        base_date = data.get('base_date')
        
        base_dates = [d.strip() for d in base_date.split(',')] if base_date else []
        if not base_dates: return jsonify({"success": False, "error": "请选择明细日期"})

        # 机场预报日查询兼容：页面评分日 = 实际 TAF 归档日 +2。
        # 因此选 7月2日时也要能查到实际归档到 6月30日的数据；
        # 同时保留原日期，避免直接按归档日查询时查不到。
        query_dates = set(base_dates)
        if s_type == 'taf':
            for d_str in base_dates:
                try:
                    query_dates.add((datetime.strptime(d_str, '%Y-%m-%d') - timedelta(days=2)).strftime('%Y-%m-%d'))
                except Exception:
                    pass
        
        backup_path = data.get('backup_path', 'backup')
        if not backup_path: backup_path = os.path.join(os.getcwd(), 'backup')
        
        files_to_read = set()
        for d_str in query_dates:
            try:
                dt = datetime.strptime(d_str, '%Y-%m-%d')
                files_to_read.add(f"backup_{dt.strftime('%Y%m')}.json")
            except: pass
            
        raw_list = []
        for fname in files_to_read:
            fpath = os.path.join(backup_path, fname)
            if not os.path.exists(fpath): continue
                
            with open(fpath, 'r', encoding='utf-8') as f: db = json.load(f)
            
            for rec_id, rec in db.get('records', {}).items():
                if rec['mode'] != s_type: continue
                if s_type == 'manual' and person != 'ALL' and rec['person'] != person: continue
                if airport and rec['airport'] != airport: continue
                if rec['date'] not in query_dates: continue
                
                ap_code = rec['airport']
                scores = rec.get('scores', [])
                obs_dict = {o['时次']: o for o in rec.get('observations', [])}
                
                # 🌟 修复需求1：强制锁定 JSON 提取的顺序（基础气象要素在前，天气现象在后）
                ordered_items = ['最大风速(MPS)', '最差能见度(m)', '最低云高(m)', '雷雨类', '强降水(无雷)类', '积冰类', '特殊类']
                items = [k for k in ordered_items if scores and k in scores[0].keys()]
                
                for s_row in scores:
                    t = s_row['时次']
                    o_row = obs_dict.get(t, {})
                    row_data = {
                        "评定对象": rec['person'], 
                        "机场": ap_code, 
                        "预报时效": s_row.get('预报时效', '/'),
                        "时次(UTC)": t, 
                        "预报全文": s_row.get('预报全文', '/')
                    }
                    for item in items:
                        row_data[f"{item}(实况)"] = o_row.get(item, '/')
                        row_data[f"{item}(评价)"] = s_row.get(item, '/')
                    raw_list.append(row_data)
                    
        if not raw_list: return jsonify({"success": False, "error": "所选日期未找到明细数据！"})
        return jsonify({"success": True, "data": raw_list})
    except Exception as e: return jsonify({"success": False, "error": str(e)})
    
@app.route('/api/query_stats', methods=['POST'])
def query_stats_api():
    try:
        data = request.json
        s_type = data.get('stats_type') 
        person = data.get('person')
        airport = data.get('airport', '').strip().upper()
        time_type = data.get('time_type') 
        base_date = data.get('base_date')
        
        # 接收逗号分隔的多日数据
        base_dates = [d.strip() for d in base_date.split(',')] if base_date else []
        if not base_dates: return jsonify({"success": False, "error": "请选择评定日期"})

        # 机场预报日查询兼容：页面评分日 = 实际 TAF 归档日 +2。
        # 只影响 day 查询；月/年统计仍按实际归档日归属，保证月末最后一天计入本月。
        query_dates = set(base_dates)
        if s_type == 'taf' and time_type == 'day':
            for d_str in base_dates:
                try:
                    query_dates.add((datetime.strptime(d_str, '%Y-%m-%d') - timedelta(days=2)).strftime('%Y-%m-%d'))
                except Exception:
                    pass
        
        backup_path = data.get('backup_path', 'backup')
        if not backup_path: backup_path = os.path.join(os.getcwd(), 'backup')

        files_to_read = set()
        if time_type == 'day':
            for d_str in query_dates:
                dt = datetime.strptime(d_str, '%Y-%m-%d')
                files_to_read.add(f"backup_{dt.strftime('%Y%m')}.json")
        elif time_type in ['month', 'year']:
            dt = datetime.strptime(base_dates[0], '%Y-%m-%d')
            if time_type == 'month': files_to_read.add(f"backup_{dt.strftime('%Y%m')}.json")
            else:
                for m in range(1, 13): files_to_read.add(f"backup_{dt.year}{m:02d}.json")

        aggregated_stats = {}
        for fname in files_to_read:
            fpath = os.path.join(backup_path, fname)
            if not os.path.exists(fpath): continue
            with open(fpath, 'r', encoding='utf-8') as f: db = json.load(f)
            
            for rec_id, rec in db.get('records', {}).items():
                # 🌟 核心拦截：绝对禁止机场预报和席位预报的数据互相串门污染！
                if rec.get('mode') != s_type: continue 
                
                if s_type == 'manual' and person != 'ALL' and rec['person'] != person: continue
                if airport and rec['airport'] != airport: continue
                
                try:
                    rec_dt = datetime.strptime(rec['date'], '%Y-%m-%d')
                except: continue

                # 🌟 按不同时间颗粒度精确放行
                if time_type == 'day' and rec['date'] not in query_dates: continue
                if time_type == 'month' and (rec_dt.year != dt.year or rec_dt.month != dt.month): continue
                if time_type == 'year' and rec_dt.year != dt.year: continue
                
                group_key = rec['airport'] if s_type == 'taf' else rec['person']
                if group_key not in aggregated_stats:
                    aggregated_stats[group_key] = {"总评":0, "参评":0, "准确":0, "空报":0, "漏报":0, "完美":0, "优秀":0, "适航天数":0}
                
                if rec.get('is_shihang'):
                    aggregated_stats[group_key]["适航天数"] += 1
                    slots = len(rec.get('scores', []))
                    if slots == 0: slots = 24 
                    aggregated_stats[group_key]["总评"] += slots
                    aggregated_stats[group_key]["准确"] += slots
                else:
                    for cat, st in rec['daily_stats'].items():
                        aggregated_stats[group_key]["总评"] += st.get('总评', 0)
                        aggregated_stats[group_key]["参评"] += st.get('参评', 0)
                        aggregated_stats[group_key]["准确"] += st.get('准确', 0)
                        aggregated_stats[group_key]["空报"] += st.get('空报', 0)
                        aggregated_stats[group_key]["漏报"] += st.get('漏报', 0)
                        aggregated_stats[group_key]["完美"] += st.get('完美', 0)
                        aggregated_stats[group_key]["优秀"] += st.get('优秀', 0)

        results = []
        for key, st in aggregated_stats.items():
            tot = st["总评"]; eval_c = st["参评"]; acc_c = st["准确"]; perf = st["完美"]; exc = st["优秀"]
            results.append({
                "统计对象": key, "总评项次": tot, "准确项次": acc_c, "参评项次": eval_c,
                "完美项次": perf, "优秀项次": exc, "空报项次": st["空报"], "漏报项次": st["漏报"],
                "准确率": f"{(acc_c/tot*100):.2f}%" if tot > 0 else "/",
                "完美率": f"{(perf/eval_c*100):.2f}%" if eval_c > 0 else "/",
                "优秀率": f"{(exc/eval_c*100):.2f}%" if eval_c > 0 else "/",
                "空报率": f"{(st['空报']/tot*100):.2f}%" if tot > 0 else "/",
                "漏报率": f"{(st['漏报']/tot*100):.2f}%" if tot > 0 else "/"
            })

        if not results: return jsonify({"success": False, "error": "未找到历史数据！"})
        return jsonify({"success": True, "data": results, "time_type": time_type, "base_date": base_date})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

# 🌟 从云端 Excel 逆向扫描重建 JSON 微型数据库的核心引擎 (智能识别路径与表头修复版)
@app.route('/api/sync_excel', methods=['POST'])
def sync_excel_api():
    try:
        data = request.json
        excel_root = data.get('excel_root')
        backup_path = data.get('backup_path')
        filter_year = int(data.get('year')) if str(data.get('year') or '').isdigit() else None
        filter_month = int(data.get('month')) if str(data.get('month') or '').isdigit() else None
        if not backup_path: backup_path = os.path.join(os.getcwd(), 'backup')
        
        if not excel_root or not os.path.exists(excel_root):
            return jsonify({"success": False, "error": "Excel 云盘目录不存在或未配置，无法同步！"})
            
        os.makedirs(backup_path, exist_ok=True)
        db_cache = {}
        scanned_files = 0
        imported_records = 0
        skipped_reasons = {}
        
        def mark_skip(reason):
            skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
        
        for root, dirs, files in os.walk(excel_root):
            for file in files:
                if not file.endswith('.xlsx') or file.startswith('~'): continue
                scanned_files += 1
                filepath = os.path.join(root, file)
                
                # 🌟 修复核心 1：不依赖表格内部文字，直接从文件路径和名称中“侦探式”提取精准的年月日！
                try:
                    # 1. 从路径提取年份 (例如 ".../2026年/...")
                    year_match = re.search(r'(\d{4})年', root)
                    if not year_match:
                        mark_skip('路径中没有“YYYY年”')
                        continue
                    year = int(year_match.group(1))
                    if filter_year and year != filter_year: continue
                    
                    # 2. 从文件名提取月日 (例如 席位预报质量评价表-曹骏-0415.xlsx -> 0415)
                    md_match = re.search(r'-(\d{4})\.xlsx$', file)
                    if not md_match:
                        mark_skip('文件名末尾不是“-MMDD.xlsx”')
                        continue
                    mmdd = md_match.group(1)
                    month = int(mmdd[:2])
                    day = int(mmdd[2:])
                    if filter_month and month != filter_month: continue
                    
                    base_date_str = f"{year}-{month:02d}-{day:02d}"
                    dt = datetime(year, month, day)
                    month_key = dt.strftime('%Y%m')
                except Exception as e:
                    mark_skip('文件日期解析失败')
                    continue # 命名不规范的废弃文件直接跳过
                    
                try:
                    # 🌟 修复核心 2：用 header=None 读取，避免 Pandas 把带有“评分人”的合并单元格当成错误表头
                    df_s1_raw = pd.read_excel(filepath, sheet_name='日统计', header=None)
                    df_s2 = pd.read_excel(filepath, sheet_name='要素分解与汇总')
                except Exception:
                    mark_skip('缺少“日统计/要素分解与汇总”工作表')
                    continue
                
                if df_s2.empty or df_s1_raw.empty:
                    mark_skip('工作表为空')
                    continue
                
                # 🌟 修复核心 3：智能往下寻找真实的表头行
                header_idx = 0
                for idx, row in df_s1_raw.iterrows():
                    if '天气分类' in [str(x) for x in row.values]:
                        header_idx = idx
                        break
                        
                # 重新定位表头，完美截取有效数据
                df_s1 = df_s1_raw.iloc[header_idx+1:].copy()
                df_s1.columns = df_s1_raw.iloc[header_idx]
                
                # 🌟 修复核心1：向下填充合并单元格，防止读取多个机场时名字变成 NaN
                if '机场' in df_s1.columns:
                    df_s1['机场'] = df_s1['机场'].ffill()
                
                if month_key not in db_cache: db_cache[month_key] = {"month": month_key, "records": {}}
                    
                mode = 'taf'
                person = 'ALL'
                if '席位' in file:
                    mode = 'manual'
                    p_match = re.search(r'-(.*?)-\d{4}\.xlsx', file)
                    if p_match: person = p_match.group(1).strip()
                
                # 🌟 修复核心2：按机场分组循环，完美保护每个机场的空报漏报不被后续机场覆盖！
                if '机场' not in df_s1.columns:
                    mark_skip('日统计表缺少“机场”列')
                    continue
                for ap_code, ap_df in df_s1.groupby('机场'):
                    if str(ap_code).startswith('评分人') or str(ap_code) == 'nan': continue
                    ap_code = str(ap_code).strip()
                    
                    rec_id = f"{base_date_str}_{mode}_{person}_{ap_code}"
                    daily_stats = {}
                    is_shihang = False
                    
                    # 录入每日统计 (Sheet 1)
                    for idx, row in ap_df.iterrows():
                        cat = row.get('天气分类'); stat_type = row.get('统计')
                        if pd.isna(cat): continue
                        if cat == '适航' and stat_type == '次数': is_shihang = True
                        if cat and cat not in ['总计', '适航'] and not str(cat).startswith('机场:'):
                            if stat_type == '次数':
                                daily_stats[cat] = {
                                    "完美": int(row.get('完美',0) if not pd.isna(row.get('完美',0)) else 0), 
                                    "优秀": int(row.get('优秀',0) if not pd.isna(row.get('优秀',0)) else 0), 
                                    "空报": int(row.get('空报',0) if not pd.isna(row.get('空报',0)) else 0), 
                                    "漏报": int(row.get('漏报',0) if not pd.isna(row.get('漏报',0)) else 0),
                                    "准确": int(row.get('准确',0) if not pd.isna(row.get('准确',0)) else 0), 
                                    "参评": int(row.get('参评',0) if not pd.isna(row.get('参评',0)) else 0), 
                                    "总评": int(row.get('总评',0) if not pd.isna(row.get('总评',0)) else 0)
                                }
                    
                    # 录入逐时详情 (Sheet 2)
                    ap_s2 = df_s2[df_s2['机场'] == ap_code] if '机场' in df_s2.columns else df_s2
                    scores, observations = [], []
                    for _, s2_row in ap_s2.iterrows():
                        time_str = str(s2_row.get('时次') or s2_row.get('时次(UTC)'))
                        if time_str == 'nan': continue
                        score_obj, obs_obj = {'时次': time_str}, {'时次': time_str}
                        
                        if '预报时效' in ap_s2.columns: score_obj['预报时效'] = str(s2_row['预报时效'])
                        if '预报全文' in ap_s2.columns: score_obj['预报全文'] = str(s2_row['预报全文'])
                        
                        for col in ap_s2.columns:
                            if '(实况)' in col: obs_obj[col.replace('(实况)', '').strip()] = s2_row[col]
                            elif '(评分)' in col or '(评价)' in col: score_obj[re.sub(r'\(评分\)|\(评价\)', '', col).strip()] = s2_row[col]
                        
                        scores.append(score_obj); observations.append(obs_obj)
                        
                    db_cache[month_key]["records"][rec_id] = {
                        "date": base_date_str, "mode": mode, "person": person,
                        "airport": ap_code, "is_shihang": is_shihang,
                        "daily_stats": daily_stats, "scores": scores, "observations": observations
                    }
                    imported_records += 1
                
        # 批量写回底层 JSON 数据库
        for m_key, db_data in db_cache.items():
            db_file = os.path.join(backup_path, f"backup_{m_key}.json")
            if os.path.exists(db_file):
                try:
                    with open(db_file, 'r', encoding='utf-8') as f:
                        existing = json.load(f)
                        existing['records'].update(db_data['records'])
                        db_data = existing
                except: pass
            with open(db_file, 'w', encoding='utf-8') as f:
                json.dump(db_data, f, ensure_ascii=False, indent=2)
                
        detail = f"扫描 {scanned_files} 个 Excel，导入/更新 {imported_records} 条记录，覆盖 {len(db_cache)} 个月份。"
        if skipped_reasons:
            detail += " 跳过原因：" + "；".join([f"{k}{v}个" for k, v in skipped_reasons.items()])
        return jsonify({"success": True, "message": f"✅ 同步完成！{detail}"})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/export_stats', methods=['POST'])
def export_stats_api():
    try:
        data = request.json
        excel_root = data.get('excel_root')
        table_data = data.get('table_data')
        title = data.get('title')
        time_type = data.get('time_type', 'day')
        base_date = data.get('base_date', '2026-01-01')
        
        if not excel_root: return jsonify({"success": False, "error": "请先配置 Excel 导出目录！"})
        
        import openpyxl
        from openpyxl.styles import Font, Alignment, Border, Side
        
        # 🌟 1. 智能分配文件夹 (年份 \ 月份)
        try:
            # 兼容多日期逗号分隔，取第一个日期作为归属
            base_dt = datetime.strptime(base_date.split(',')[0].strip(), '%Y-%m-%d')
        except:
            base_dt = datetime.now()
            
        y_str = f"{base_dt.year}年"
        m_str = f"{base_dt.month}月"
        
        # 年统计放年份里，月统计/日统计放月份里
        if time_type == 'year':
            folder = os.path.join(excel_root, y_str)
        else:
            folder = os.path.join(excel_root, y_str, m_str)
            
        os.makedirs(folder, exist_ok=True)
        file_path = os.path.join(folder, f"{title}.xlsx")
        
        # 🌟 2. 完美复刻前端双行复杂表格
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "统计汇总"
        
        font_bold = Font(name='仿宋_GB2312', size=12, bold=True)
        font_normal = Font(name='仿宋_GB2312', size=11)
        align_center = Alignment(horizontal='center', vertical='center')
        border_thin = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))

        first_col_name = "机场" if "机场预报" in title else "评定对象"
        headers = [first_col_name, "", "完美", "优秀", "空报", "漏报", "准确", "参评", "总评", "总分"]
        ws.append(headers)
        for i, h in enumerate(headers, 1):
            cell = ws.cell(1, i)
            cell.font = font_bold; cell.alignment = align_center; cell.border = border_thin

        row_idx = 2
        merges = []
        
        for row in table_data:
            obj_name = row.get("统计对象", "")
            
            # 计算复杂的总分逻辑
            acc_rate = (row.get("准确项次",0)/row.get("总评项次",1)) * 100 if row.get("总评项次",0)>0 else 0
            perf_rate = (row.get("完美项次",0)/row.get("参评项次",1)) * 100 if row.get("参评项次",0)>0 else 0
            exc_rate = (row.get("优秀项次",0)/row.get("参评项次",1)) * 100 if row.get("参评项次",0)>0 else 0
            fa_rate = (row.get("空报项次",0)/row.get("总评项次",1)) * 100 if row.get("总评项次",0)>0 else 0
            miss_rate = (row.get("漏报项次",0)/row.get("总评项次",1)) * 100 if row.get("总评项次",0)>0 else 0
            score = (acc_rate*0.5) + (perf_rate*0.3) + (exc_rate*0.2) - (fa_rate*0.1) - (miss_rate*0.1)
            
            row1 = [obj_name, "次数", row.get("完美项次",0), row.get("优秀项次",0), row.get("空报项次",0), row.get("漏报项次",0), row.get("准确项次",0), row.get("参评项次",0), row.get("总评项次",0), f"{score:.2f}"]
            row2 = ["", "概率", row.get("完美率","/"), row.get("优秀率","/"), row.get("空报率","/"), row.get("漏报率","/"), row.get("准确率","/"), "", "", ""]
            
            ws.append(row1)
            ws.append(row2)
            
            # 首列与尾列的上下合并
            merges.append((row_idx, 1, row_idx+1, 1))
            merges.append((row_idx, 10, row_idx+1, 10))
            
            for r in range(row_idx, row_idx+2):
                for c in range(1, 11):
                    cell = ws.cell(r, c)
                    cell.font = font_normal; cell.alignment = align_center; cell.border = border_thin
            row_idx += 2
            
        # 表尾规则说明合并
        desc_row = ["评定逻辑：总分=(准确率*50% + 完美率*30% + 优秀率*20% - 空报率*10% - 漏报率*10%)"] + [""]*9
        ws.append(desc_row)
        merges.append((row_idx, 1, row_idx, 10))
        desc_cell = ws.cell(row_idx, 1)
        desc_cell.font = font_bold; desc_cell.alignment = Alignment(horizontal='left', vertical='center'); desc_cell.border = border_thin
        for c in range(2, 11): ws.cell(row_idx, c).border = border_thin
            
        # 统一执行合并单元格
        for m in merges:
            ws.merge_cells(start_row=m[0], start_column=m[1], end_row=m[2], end_column=m[3])
            
        # 优化列宽
        ws.column_dimensions['A'].width = 15
        for col_letter in ['B','C','D','E','F','G','H','I','J']: ws.column_dimensions[col_letter].width = 12
        
        wb.save(file_path)
        return jsonify({"success": True, "message": f"成功导出至 {file_path}"})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500
