"""
统一服务启动器 (Unified Launcher)
深色简洁风格 · CustomTkinter · 左侧服务管理 + 右侧合并/分项日志

一个入口同时启动并监控四个服务：
  ① FMSA 基于航班计划的气象监视告警系统   (Django, 内部端口 8001)
  ② OMICS 预报评定/发布工具 (Flask+Waitress, 内部端口 8002)
  ③ IWBP 气象智能业务工作台 (Node, 内部端口 8787)
  ④ Nginx 统一入口          (对外端口 8000，/fmsa/ /omics/ /iwbp/，局域网可访问)

设计要点：
  - 业务服务对称处理：subprocess.Popen + CREATE_NO_WINDOW（无黑框）+ 读 stdout
  - 界面显示 FMSA / OMICS / IWBP；Nginx 作为后台统一入口由启动器静默管理
  - 默认一个合并运行日志，可按级别勾选过滤；点左侧标签查看该子项目全部日志
  - 路径可配置：通过 launcher_config.json 记录各项目路径，不必放同一文件夹

注意：本文件不改动 server_gui.py / main.py，作为独立启动器存在。
"""

import customtkinter as ctk
import base64
import io
import subprocess
import threading
import webbrowser
import sys
import os
import json
import queue
import re
import socket
import time
import tkinter.font as tkfont
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

try:
    from PIL import Image, ImageDraw, ImageFont, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    Image = ImageDraw = ImageFont = ImageTk = None
    PIL_AVAILABLE = False

try:
    import pystray
    TRAY_AVAILABLE = PIL_AVAILABLE
except ImportError:
    pystray = None
    TRAY_AVAILABLE = False

# ── 路径常量 ──────────────────────────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "launcher_config.json"
IPC_PORT    = 19528          # 单实例 IPC（与 MTWS 的 19527 错开）
AUTH_BROKER_PORT = 19529     # Nginx 统一登录态接口后端（仅 127.0.0.1，由 Nginx /auth/ 反代）
# SF 平台航班计划接口，用于轻量校验 token 是否仍然有效（与 MTWS validate-token 同源）。
SF_FLIGHT_VALIDATE_URL = "http://sfa-wgw-inn.sf-airlines.com:1080/flight/flightSchedule/getByFlightDate"
AUTH_VALIDATE_INTERVAL_MS = 60000   # 控制台后台校验 token 的间隔（毫秒）

DEFAULT_MTWS_DIR = SCRIPT_DIR / "FMSA"
DEFAULT_OMICS_DIR = SCRIPT_DIR / "OMICS"
DEFAULT_IWBP_DIR = SCRIPT_DIR / "IWBP"
# 桌面/窗口图标（窗口标题栏、任务栏、桌面快捷方式）
DESKTOP_ICON_CANDIDATES = [
    SCRIPT_DIR / "桌面图标.ico",
    SCRIPT_DIR / "桌面图标.png",
    SCRIPT_DIR / "系统图标.ico",
    SCRIPT_DIR.parent / "桌面图标.ico",
]
# 系统托盘图标
TRAY_ICON_CANDIDATES = [
    SCRIPT_DIR / "托盘图标.ico",
    SCRIPT_DIR / "托盘图标.png",
    SCRIPT_DIR / "系统图标.ico",
    SCRIPT_DIR.parent / "托盘图标.ico",
]
ICON_PATH = next((path for path in DESKTOP_ICON_CANDIDATES if path.exists()), DESKTOP_ICON_CANDIDATES[0])
TRAY_ICON_PATH = next((path for path in TRAY_ICON_CANDIDATES if path.exists()), TRAY_ICON_CANDIDATES[0])
NGINX_DIR = DEFAULT_OMICS_DIR / "tools" / "nginx"
# Windows 版 Nginx 对中文路径支持很差；运行前缀必须放到纯英文路径。
NGINX_RUNTIME_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "MTWS_OMICS_Nginx"
NGINX_CONF_DIR = NGINX_RUNTIME_DIR / "conf"
NGINX_LOG_DIR = NGINX_RUNTIME_DIR / "logs"
# 旧版可能写过 token 缓存；现在仅写无 token 占位，避免中控台脱离前端默认登录。
AUTH_STATE_FILE = NGINX_RUNTIME_DIR / "auth_state.json"
_PLACEHOLDER_AUTH_VALUES = {"", "--", "-", "OFFLINE", "UNKNOWN", "UNDEFINED", "NULL", "NONE"}


def is_real_user_code(user_code):
    """真实工号才算登录身份；`--` / OFFLINE 等占位符不能当成已登录。"""
    code = str(user_code or "").strip()
    return bool(code) and code.upper() not in _PLACEHOLDER_AUTH_VALUES


def is_usable_auth_token(token):
    value = str(token or "").strip()
    return bool(value) and value.upper() not in _PLACEHOLDER_AUTH_VALUES


# ── macOS 深色系统配色（沿用 server_gui.py 同款）────────────────────────────────
BG_PRIMARY        = "#1c1c1e"
BG_SECONDARY      = "#2c2c2e"
BG_TERTIARY       = "#3a3a3c"
BG_GROUPED        = "#48484a"
COLOR_BLUE        = "#0a84ff"
COLOR_GREEN       = "#30d158"
COLOR_RED         = "#ff453a"
COLOR_ORANGE      = "#ff9f0a"
COLOR_LABEL       = "#ffffff"
COLOR_LABEL2      = "#ebebf5"
COLOR_SEPARATOR   = "#38383a"
COLOR_MUTED       = "#8e8e93"
COLOR_APRICOT     = "#e8b86d"
SIDEBAR_WIDTH     = 148
USER_WIN_SIZE     = (920, 430)
DEV_WIN_SIZE      = (1280, 760)
USER_WIN_MIN      = (840, 380)
DEV_WIN_MIN       = (1080, 620)
MAX_LOG_ENTRIES   = 3000
BADGE_W           = 58
BADGE_H           = 16
BADGE_RADIUS      = 5
SERVICE_LABELS = {
    "mtws":  ("基于航班计划的气象监视告警", "FMSA"),
    "omics": ("预报发布/质量评定", "OMICS"),
    "iwbp":  ("气象智能业务工作台", "IWBP"),
}
BADGE_STYLE = {
    "mtws":  {"text": "FMSA",  "bg": "#c44742", "fg": "#ffffff"},
    "omics": {"text": "OMICS", "bg": "#c4a035", "fg": "#1c1c1e"},
    "iwbp":  {"text": "IWBP",  "bg": "#3b6fd4", "fg": "#ffffff"},
}
LOG_FILTER_GROUPS = {
    "error": {"error"},
    "warn":  {"warn"},
    "debug": {"debug"},
    "info":  {"info", "success", "normal", "dim"},
}
COLOR_DEBUG       = "#7aa2c4"


def _hex_rgb(value):
    raw = value.lstrip("#")
    return tuple(int(raw[i:i + 2], 16) for i in (0, 2, 4))


class MiniSwitch(ctk.CTkFrame):
    """圆角开关：左关红底，右开绿底。labeled 时显示开启/关闭。"""

    def __init__(self, master, command=None, labeled=False, **kwargs):
        self.labeled = labeled
        if labeled:
            self.TRACK_W, self.TRACK_H = 58, 24
            self.THUMB_W, self.THUMB_H = 18, 18
            self.PAD = 3
            radius = 12
        else:
            self.TRACK_W, self.TRACK_H = 38, 16
            self.THUMB_W, self.THUMB_H = 12, 10
            self.PAD = 3
            radius = 5
        super().__init__(
            master,
            width=self.TRACK_W,
            height=self.TRACK_H,
            corner_radius=radius,
            fg_color=COLOR_RED,
            cursor="hand2",
        )
        self.pack_propagate(False)
        self.command = command
        self._on = False
        self.caption = None
        if labeled:
            self.caption = ctk.CTkLabel(
                self, text="关闭",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color="#ffffff", cursor="hand2",
            )
        self.thumb = ctk.CTkFrame(
            self,
            width=self.THUMB_W,
            height=self.THUMB_H,
            corner_radius=self.THUMB_W // 2 if labeled else 3,
            fg_color="#f2f2f7",
            cursor="hand2",
        )
        self._place_thumb()
        self.bind("<Button-1>", self._on_click)
        self.thumb.bind("<Button-1>", self._on_click)
        if self.caption:
            self.caption.bind("<Button-1>", self._on_click)

    def _place_thumb(self):
        y = max(0, (self.TRACK_H - self.THUMB_H) // 2)
        x = self.TRACK_W - self.THUMB_W - self.PAD if self._on else self.PAD
        self.thumb.place(x=x, y=y)
        self.thumb.lift()
        if self.caption:
            if self._on:
                self.caption.configure(text="开启")
                self.caption.place(x=7, rely=0.5, anchor="w")
            else:
                self.caption.configure(text="关闭")
                self.caption.place(x=self.TRACK_W - 7, rely=0.5, anchor="e")

    def _on_click(self, _event=None):
        self._apply(not self._on, notify=True)

    def _apply(self, on, notify=False):
        self._on = bool(on)
        self.configure(fg_color=COLOR_GREEN if self._on else COLOR_RED)
        self._place_thumb()
        if notify and self.command:
            self.command(self._on)

    def select(self):
        self._apply(True, notify=False)

    def deselect(self):
        self._apply(False, notify=False)

    def get(self):
        return 1 if self._on else 0


class FilterChip(ctk.CTkButton):
    """标题栏用的圆角筛选开关：按下为开，再按为关。"""

    def __init__(self, master, text, variable, command=None, accent="#3a3a3c"):
        self.variable = variable
        self._command = command
        self._accent = accent
        super().__init__(
            master,
            text=text,
            width=52,
            height=22,
            corner_radius=11,
            font=ctk.CTkFont(size=11),
            border_width=1,
            command=self._toggle,
        )
        self._refresh()

    def _toggle(self):
        self.variable.set(not bool(self.variable.get()))
        self._refresh()
        if self._command:
            self._command()

    def _refresh(self):
        if bool(self.variable.get()):
            self.configure(
                fg_color=self._accent,
                hover_color=self._accent,
                text_color=COLOR_LABEL,
                border_color=self._accent,
            )
        else:
            self.configure(
                fg_color="transparent",
                hover_color=BG_TERTIARY,
                text_color=COLOR_MUTED,
                border_color=BG_GROUPED,
            )

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")


OMICS_INLINE_CODE = 'import os, sys, argparse, logging\ntry:\n    sys.stdout.reconfigure(encoding=\'utf-8\', errors=\'replace\')\n    sys.stderr.reconfigure(encoding=\'utf-8\', errors=\'replace\')\nexcept Exception:\n    pass\nparser = argparse.ArgumentParser(description=\'OMICS inline server\')\nparser.add_argument(\'--host\', default=\'127.0.0.1\')\nparser.add_argument(\'--port\', type=int, default=56789)\nparser.add_argument(\'--work-dir\', required=True)\nargs = parser.parse_args()\nwork_dir = os.path.abspath(args.work_dir)\ndef out(msg):\n    print(msg, flush=True)\nout(f"[INFO] OMICS 服务启动中 | host={args.host} port={args.port}")\nout(f"[INFO] 工作目录: {work_dir}")\nif not os.path.isdir(os.path.join(work_dir, \'frontend\')) or not os.path.isdir(os.path.join(work_dir, \'backend\')):\n    out(f"[ERROR] 工作目录无效，需包含 frontend/backend: {work_dir}")\n    sys.exit(2)\nos.environ[\'FORECAST_WORK_DIR\'] = work_dir\nif work_dir not in sys.path:\n    sys.path.insert(0, work_dir)\nlogger = logging.getLogger(\'forecast\')\nlogger.setLevel(logging.INFO)\nhandler = logging.StreamHandler(sys.stdout)\nhandler.setFormatter(logging.Formatter(\'%(asctime)s [%(levelname)s] %(message)s\', datefmt=\'%H:%M:%S\'))\nlogger.handlers.clear()\nlogger.addHandler(handler)\nlogger.propagate = False\ntry:\n    from waitress import serve\n    from backend.app import app\nexcept Exception as e:\n    out(f"[ERROR] 导入后端失败: {e}")\n    sys.exit(3)\ntry:\n    out(f"[INFO] Waitress 正在监听 http://{args.host}:{args.port}")\n    serve(app, host=args.host, port=args.port, threads=6)\nexcept OSError as e:\n    out(f"[ERROR] 端口 {args.port} 被占用或无法绑定: {e}")\n    sys.exit(1)\nexcept Exception as e:\n    out(f"[ERROR] 服务运行异常: {e}")\n    sys.exit(4)'


# ══════════════════════════════════════════════════════════════════════════════
#  配置（两个服务的路径/端口）
# ══════════════════════════════════════════════════════════════════════════════
DEFAULT_CONFIG = {
    "mtws": {
        "name": "FMSA 监控系统",
        "work_dir": str(DEFAULT_MTWS_DIR) if DEFAULT_MTWS_DIR.exists() else "",
        "host": "127.0.0.1",
        "port": 8001,
        "home_path": "/current/",
        "public_home_url": "http://127.0.0.1:8000/fmsa/",
    },
    "omics": {
        "name": "OMICS 评定发布",
        "work_dir": str(DEFAULT_OMICS_DIR) if DEFAULT_OMICS_DIR.exists() else str(SCRIPT_DIR), # 指向 OMICS 项目根目录（包含 backend/frontend）
        "host": "127.0.0.1",
        "port": 8002,
        "home_path": "/",
        "public_home_url": "http://127.0.0.1:8000/omics/",
    },
    "iwbp": {
        "name": "IWBP 业务工作台",
        "work_dir": str(DEFAULT_IWBP_DIR) if DEFAULT_IWBP_DIR.exists() else "",
        "host": "127.0.0.1",
        "port": 8787,
        "home_path": "/index.html",
        "public_home_url": "http://127.0.0.1:8000/iwbp/",
    },
    "nginx": {
        "name": "Nginx 统一入口",
        "host": "0.0.0.0",
        "port": 8000,
        "home_path": "/",
        "public_home_url": "http://127.0.0.1:8000/fmsa/",
        "exe_path": "",
    },
}


def load_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    try:
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            for svc in ("mtws", "omics", "iwbp", "nginx"):
                if svc in saved and isinstance(saved[svc], dict):
                    cfg[svc].update(saved[svc])
    except Exception:
        pass
    # 统一入口改为对局域网开放；业务进程仍只绑 127.0.0.1。
    cfg.setdefault("nginx", {})
    if str(cfg["nginx"].get("host") or "").strip() in ("", "127.0.0.1", "localhost"):
        cfg["nginx"]["host"] = "0.0.0.0"
    cfg.setdefault("iwbp", json.loads(json.dumps(DEFAULT_CONFIG["iwbp"])))
    if not cfg["iwbp"].get("public_home_url"):
        cfg["iwbp"]["public_home_url"] = f"http://127.0.0.1:{int(cfg['nginx'].get('port', 8000))}/iwbp/"
    # 兼容旧配置：MTWS 旧版保存 manage_py，新版统一保存程序根目录/入口路径
    if cfg["mtws"].get("manage_py") and not cfg["mtws"].get("work_dir"):
        cfg["mtws"]["work_dir"] = cfg["mtws"].get("manage_py")
    cfg["mtws"].pop("manage_py", None)
    if cfg["mtws"].get("name") in ("MTWS 监控系统", "MTWS"):
        cfg["mtws"]["name"] = "FMSA 监控系统"
    nginx_port = int(cfg["nginx"].get("port", 8000) or 8000)
    fmsa_home = f"http://127.0.0.1:{nginx_port}/fmsa/"
    cfg["mtws"]["public_home_url"] = fmsa_home
    cfg["nginx"]["public_home_url"] = fmsa_home
    # 兼容旧配置：如果已有 run_server 路径，自动折算为项目根目录
    if cfg["omics"].get("run_server") and not cfg["omics"].get("work_dir"):
        cfg["omics"]["work_dir"] = str(Path(cfg["omics"]["run_server"]).parent)
    cfg["omics"].pop("run_server", None)
    # When IWMS is moved or cloned, a stale absolute path (or a duplicated
    # ``OMICS\\OMICS`` path) must not shadow the repository's bundled project.
    configured_omics = str(cfg["omics"].get("work_dir") or "").strip().strip('"')
    configured_omics_path = Path(configured_omics).expanduser() if configured_omics else None
    if configured_omics_path and not (
        (configured_omics_path / "frontend").is_dir()
        and (configured_omics_path / "backend").is_dir()
    ) and (DEFAULT_OMICS_DIR / "frontend").is_dir() and (DEFAULT_OMICS_DIR / "backend").is_dir():
        cfg["omics"]["work_dir"] = str(DEFAULT_OMICS_DIR.resolve())
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def local_lan_ipv4():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    return None


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def find_nginx_exe(configured_path=""):
    """定位 nginx.exe。优先使用配置，其次使用项目内 portable nginx，再尝试 PATH。"""
    candidates = []
    if configured_path:
        candidates.append(Path(configured_path))
    candidates.extend([
        NGINX_DIR / "nginx.exe",
        DEFAULT_OMICS_DIR / "tools" / "nginx" / "nginx.exe",
        SCRIPT_DIR / "nginx" / "nginx.exe",
        SCRIPT_DIR / "tools" / "nginx.exe",
        SCRIPT_DIR / "tools" / "nginx" / "nginx.exe",
    ])
    for c in candidates:
        if c and c.exists() and c.is_file():
            return c
    try:
        import shutil
        found = shutil.which("nginx.exe") or shutil.which("nginx")
        if found:
            return Path(found)
    except Exception:
        pass
    return None


def find_node_exe():
    candidates = []
    try:
        import shutil
        found = shutil.which("node.exe") or shutil.which("node")
        if found:
            candidates.append(Path(found))
    except Exception:
        pass
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local = os.environ.get("LOCALAPPDATA", "")
    candidates.extend([
        Path(pf) / "nodejs" / "node.exe",
        Path(pf86) / "nodejs" / "node.exe",
        Path(local) / "Programs" / "nodejs" / "node.exe" if local else None,
    ])
    for c in candidates:
        if c and c.exists() and c.is_file():
            return c
    return None


def _iwbp_has_proxy(root):
    try:
        if not root:
            return False
        tools = Path(root) / "tools"
        direct = tools / "dev-server-proxy.cjs"
        if direct.is_file() or os.path.isfile(str(direct)):
            return True
        if tools.is_dir():
            for item in tools.iterdir():
                if item.is_file() and item.name.lower() == "dev-server-proxy.cjs":
                    return True
    except Exception:
        return False
    return False


def _iwbp_search_nearby(root):
    """在配置目录及其一层子目录中查找完整 IWBP（跳过 node_modules/.git）。"""
    if _iwbp_has_proxy(root):
        return root
    if not root or not root.is_dir():
        return None
    skip = {".git", "node_modules", "__pycache__", ".venv", "venv"}
    try:
        children = list(root.iterdir())
    except Exception:
        return None
    preferred = ("拷贝", "copy", "workbench", "V2", "v2")
    ordered = []
    for name in preferred:
        p = root / name
        if p.is_dir():
            ordered.append(p)
    for child in children:
        if child.is_dir() and child.name not in skip and child not in ordered:
            ordered.append(child)
    for child in ordered:
        if _iwbp_has_proxy(child):
            return child
        nested = child / "IWBP"
        if _iwbp_has_proxy(nested):
            return nested
    return None


def resolve_iwbp_root(path):
    """定位 IWBP 根目录（含 tools/dev-server-proxy.cjs）。

    优先用启动器所在工程里的 IWBP（例如 D:\\Projects\\MTWS-OMICS\\IWBP），
    避免路径配置仍指向另一块盘上缺少脚本的旧副本（例如 E:\\MTWS-OMICS\\IWBP）。
    """
    raw = str(path or "").strip().strip('"')
    seeds = []

    def add(item):
        if item is None:
            return
        p = item if isinstance(item, Path) else Path(str(item))
        seeds.append(p)

    # 1) 启动器旁边的完整工程（Cursor 里打开的那份）
    add(SCRIPT_DIR / "IWBP")
    add(SCRIPT_DIR)
    add(Path(r"D:\Projects\MTWS-OMICS") / "IWBP")
    add(Path(r"D:\Projects\MTWS-OMICS"))
    # 2) 用户在路径配置里填的目录
    if raw:
        given = Path(raw)
        add(given)
        if not given.is_absolute():
            add(SCRIPT_DIR / given)
        add(given / "IWBP")
        add(given.parent)
        if given.name.lower() == "tools":
            add(given.parent)
        if given.name.lower() == "dev-server-proxy.cjs":
            add(given.parent.parent)
            add(given.parent)
    add(DEFAULT_IWBP_DIR)

    seen = set()
    for p in seeds:
        try:
            p = p.expanduser().resolve()
        except Exception:
            pass
        try:
            key = str(p).lower()
        except Exception:
            key = str(p)
        if key in seen:
            continue
        seen.add(key)
        if p.is_file() and p.name.lower() == "dev-server-proxy.cjs":
            p = p.parent.parent
        found = _iwbp_search_nearby(p)
        if found:
            return found
        nested = p / "IWBP"
        found = _iwbp_search_nearby(nested)
        if found:
            return found
    return None


def nginx_runtime_paths():
    prefix = NGINX_RUNTIME_DIR
    conf = NGINX_CONF_DIR / "nginx.conf"
    return prefix, conf


def ensure_nginx_conf(mtws_cfg, omics_cfg, iwbp_cfg, nginx_cfg):
    """生成统一入口配置：对外听 0.0.0.0:8000，反代到本机各业务端口。"""
    prefix, conf = nginx_runtime_paths()
    NGINX_CONF_DIR.mkdir(parents=True, exist_ok=True)
    NGINX_LOG_DIR.mkdir(parents=True, exist_ok=True)
    for d in ("client_body_temp", "proxy_temp", "fastcgi_temp", "uwsgi_temp", "scgi_temp"):
        (NGINX_RUNTIME_DIR / "temp" / d).mkdir(parents=True, exist_ok=True)
    mime_types = NGINX_CONF_DIR / "mime.types"
    if not mime_types.exists():
        mime_types.write_text("""types {
    text/html                             html htm shtml;
    text/css                              css;
    text/xml                              xml;
    image/gif                             gif;
    image/jpeg                            jpeg jpg;
    image/png                             png;
    image/svg+xml                         svg svgz;
    image/x-icon                          ico;
    application/javascript                js;
    application/json                      json;
    application/pdf                       pdf;
    font/woff                             woff;
    font/woff2                            woff2;
    application/vnd.ms-fontobject         eot;
    font/ttf                              ttf;
}
""", encoding="utf-8")
    mtws_host, mtws_port = mtws_cfg.get("host", "127.0.0.1"), int(mtws_cfg.get("port", 8001))
    omics_host, omics_port = omics_cfg.get("host", "127.0.0.1"), int(omics_cfg.get("port", 8002))
    iwbp_host, iwbp_port = iwbp_cfg.get("host", "127.0.0.1"), int(iwbp_cfg.get("port", 8787))
    nginx_port = int(nginx_cfg.get("port", 8000))
    text = f"""worker_processes  1;
error_log  logs/error.log;
pid        logs/nginx.pid;

events {{
    worker_connections  1024;
}}

http {{
    include       mime.types;
    default_type  application/octet-stream;
    access_log    logs/access.log;
    sendfile      on;
    keepalive_timeout  65;
    client_max_body_size 50m;
    client_body_buffer_size 8m;

    server {{
        listen 0.0.0.0:{nginx_port};
        server_name 127.0.0.1 localhost;

        location = / {{
            return 302 /fmsa/;
        }}

        location /fmsa/ {{
            proxy_pass http://{mtws_host}:{mtws_port}/;
            proxy_http_version 1.1;
            proxy_set_header Host $host:$server_port;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_redirect ~^(/.*)$ /fmsa$1;
            proxy_redirect http://{mtws_host}:{mtws_port}/ /fmsa/;
        }}

        # 静态 JS/CSS 禁止浏览器缓存，避免席位电脑服务端更新后仍运行旧脚本。
        location ~* ^/static/.*\\.(js|css)$ {{
            proxy_pass http://{mtws_host}:{mtws_port};
            proxy_http_version 1.1;
            proxy_set_header Host $host:$server_port;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            add_header Cache-Control "no-cache, no-store, must-revalidate" always;
            add_header Pragma "no-cache" always;
            expires -1;
        }}

        location ~ ^/(current|test|system|admin|static|media)(/.*)?$ {{
            proxy_pass http://{mtws_host}:{mtws_port};
            proxy_http_version 1.1;
            proxy_set_header Host $host:$server_port;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }}

        location /omics/ {{
            proxy_pass http://{omics_host}:{omics_port}/;
            proxy_http_version 1.1;
            proxy_set_header Host $host:$server_port;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_redirect ~^(/.*)$ /omics$1;
            proxy_redirect http://{omics_host}:{omics_port}/ /omics/;
        }}

        location = /iwbp {{
            return 302 /iwbp/;
        }}

        location /iwbp/ {{
            proxy_pass http://{iwbp_host}:{iwbp_port}/;
            proxy_http_version 1.1;
            proxy_set_header Host $host:$server_port;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header Authorization $http_authorization;
            proxy_set_header token $http_token;
            proxy_set_header X-User-Code $http_x_user_code;
            proxy_redirect ~^(/.*)$ /iwbp$1;
            proxy_redirect http://{iwbp_host}:{iwbp_port}/ /iwbp/;
        }}

        location /auth/ {{
            proxy_pass http://127.0.0.1:{AUTH_BROKER_PORT}/auth/;
            proxy_http_version 1.1;
            proxy_set_header Host $host:$server_port;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }}

        location /api/ {{
            proxy_pass http://{omics_host}:{omics_port}/api/;
            proxy_http_version 1.1;
            proxy_set_header Host $host:$server_port;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }}
        location /assets/ {{
            proxy_pass http://{omics_host}:{omics_port}/assets/;
        }}
    }}
}}
"""
    conf.write_text(text, encoding="utf-8")
    return prefix, conf


def resolve_mtws_manage_py(path):
    """配置既可指向 manage.py，也可指向 server_gui.py 所在的程序根目录。

    OMICS 与 FMSA 平级时，未手动配置也会尝试 ../FMSA/fmsa_django/manage.py。
    """
    raw = (path or "").strip()
    paths = []
    if raw:
        paths.append(Path(raw))
    paths.append(DEFAULT_MTWS_DIR)

    seen = set()
    for p in paths:
        try:
            key = str(p.resolve())
        except Exception:
            key = str(p)
        if key in seen:
            continue
        seen.add(key)

        if p.is_file() and p.name.lower() == "manage.py":
            return p
        if p.is_file() and p.name.lower() == "server_gui.py":
            p = p.parent
        if p.is_dir():
            candidates = [
                p / "fmsa_django" / "manage.py",
                p / "manage.py",
                p.parent / "FMSA" / "fmsa_django" / "manage.py",
            ]
            for c in candidates:
                if c.exists():
                    return c
    return None


def mtws_root_from_path(path):
    """由配置路径推导 MTWS 程序根目录，用于数据库管理工具等。"""
    if not path:
        return None
    p = Path(path)
    if p.is_file() and p.name.lower() == "manage.py":
        if p.parent.name.lower() == "fmsa_django":
            return p.parent.parent
        return p.parent
    if p.is_file() and p.name.lower() == "server_gui.py":
        return p.parent
    if p.is_dir():
        return p
    m = resolve_mtws_manage_py(path)
    return mtws_root_from_path(str(m)) if m else None

def acquire_single_instance():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    try:
        sock.bind(("127.0.0.1", IPC_PORT))
        sock.listen(5)
        return sock
    except OSError:
        sock.close()
        try:
            c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            c.settimeout(1)
            c.connect(("127.0.0.1", IPC_PORT))
            c.sendall(b"SHOW")
            c.close()
        except Exception:
            pass
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  单个服务的运行控制器（封装一个 subprocess + 日志队列 + 状态）
# ══════════════════════════════════════════════════════════════════════════════
class ServicePanel:
    """管理一个服务的进程、状态与日志面板 UI。"""

    def __init__(self, app, key, cfg):
        self.app = app
        self.key = key
        self.cfg = cfg
        self.process = None
        self.sidecar_process = None
        self.running = False
        self.attached = False     # 接管外部已存在的服务
        self.log_queue = queue.Queue()
        self._quitting = False

        # UI 句柄（由 build_ui 填充）
        self.status_dot = None
        self.status_label = None
        self.power_switch = None
        self.power_switches = []
        self.nav_card = None
        self.log_entries = []
        self._switch_syncing = False

    @property
    def host(self):
        return self.cfg.get("host", "127.0.0.1")

    @property
    def port(self):
        return int(self.cfg.get("port", 0))

    @property
    def home_url(self):
        return f"http://{self.host}:{self.port}{self.cfg.get('home_path', '/')}"

    @property
    def public_home_url(self):
        return self.cfg.get("public_home_url") or self.home_url

    def target_path(self):
        raw = str(self.cfg.get("work_dir") or "").strip().strip('"')
        if not raw:
            return raw
        # Resolve configured relative paths from the launcher directory, not
        # the process cwd (which may be changed by a batch file).
        p = Path(raw).expanduser()
        return str((SCRIPT_DIR / p).resolve()) if not p.is_absolute() else str(p.resolve())

    # ── 启动 ──────────────────────────────────────────────────────────────
    def start(self):
        if self.running:
            return

        # 端口已被占用 → 接管模式
        if is_port_in_use(self.port):
            self.log(f"检测到端口 {self.port} 已有服务，直接接管。", "warn")
            if self.key == "omics":
                configured_frontend = Path(self.target_path()) / "frontend" / "publish.js"
                self.log(
                    f"当前不会重新加载源码；请确认已停止旧 OMICS 服务后再启动。配置前端资源：{configured_frontend}",
                    "warn",
                )
            self.log(f"服务已就绪 → {self.home_url}", "success")
            self.running = True
            self.attached = True
            self.app.after(0, self._ui_attached)
            return

        path = self.target_path()
        if self.key == "nginx":
            valid_path = bool(find_nginx_exe(self.cfg.get("exe_path", "")))
        elif self.key == "mtws":
            valid_path = bool(resolve_mtws_manage_py(path))
        elif self.key == "iwbp":
            valid_path = bool(resolve_iwbp_root(path) and find_node_exe())
        else:
            valid_path = bool(path and os.path.isdir(os.path.join(path, "backend")) and os.path.isdir(os.path.join(path, "frontend")))
        # Older seat-local configs sometimes resolve OMICS as
        # ``...\\OMICS\\OMICS`` after the repository was moved.  IWMS is
        # launched from this repository, so recover to its bundled project
        # root when that configured path is invalid.
        if self.key == "omics" and not valid_path:
            fallback = str(DEFAULT_OMICS_DIR.resolve())
            fallback_valid = os.path.isdir(os.path.join(fallback, "backend")) and os.path.isdir(os.path.join(fallback, "frontend"))
            if fallback_valid:
                self.log(f"OMICS 配置目录无效，已回退到启动器目录：{fallback}", "warn")
                self.cfg["work_dir"] = fallback
                path = fallback
                valid_path = True
        if not valid_path:
            if self.key == "nginx":
                self.log("未找到 nginx.exe。请将 portable Nginx 放到 tools\\nginx\\nginx.exe，或在「路径配置」中指定。", "error")
            elif self.key == "iwbp":
                if not find_node_exe():
                    self.log("未找到 node.exe。请安装 Node.js LTS，或把 node 加入系统 PATH 后重启启动器。", "error")
                else:
                    checked = path or str(DEFAULT_IWBP_DIR)
                    missing = Path(checked) / "tools" / "dev-server-proxy.cjs"
                    self.log(
                        f"IWBP 目录「{checked}」下没有启动脚本：{missing}",
                        "error",
                    )
                    self.log(
                        "该目录多半是不完整副本。请把完整 IWBP（含 tools\\dev-server-proxy.cjs）同步过来，"
                        "或在路径配置中改选含该文件的目录（例如 IWBP\\拷贝）。",
                        "error",
                    )
            else:
                self.log(f"未配置有效启动路径，无法启动。请点「路径配置」。", "error")
            self.app.after(0, self._ui_unstarted)
            return

        self.log(f"正在启动 {self.cfg['name']} …", "info")
        threading.Thread(target=self._run, args=(path,), daemon=True).start()

    def _build_cmd(self, path):
        """根据服务类型组装启动命令。"""
        if self.key == "mtws":
            # Django: 可从程序根目录自动定位 fmsa_django/manage.py
            manage_py = resolve_mtws_manage_py(path)
            if not manage_py:
                raise FileNotFoundError(f"未找到 FMSA 启动入口 manage.py: {path}")
            return [sys.executable, str(manage_py), "runserver", f"{self.host}:{self.port}"], str(manage_py.parent)
        if self.key == "nginx":
            exe = find_nginx_exe(self.cfg.get("exe_path", ""))
            if not exe:
                raise FileNotFoundError("未找到 nginx.exe")
            prefix, conf = ensure_nginx_conf(
                self.app.mtws.cfg, self.app.omics.cfg, self.app.iwbp.cfg, self.cfg)
            return [str(exe), "-p", str(prefix) + os.sep, "-c", str(conf)], str(exe.parent)
        if self.key == "iwbp":
            node = find_node_exe()
            if not node:
                raise FileNotFoundError("未找到 node.exe")
            root = resolve_iwbp_root(path)
            if not root:
                raise FileNotFoundError(f"未找到 IWBP 启动入口: {path}")
            configured = str(Path(path).expanduser().resolve()) if path else ""
            actual = str(root)
            if configured and configured.lower().rstrip("\\/") != actual.lower().rstrip("\\/"):
                self.log(
                    f"配置目录「{path}」中没有 tools\\dev-server-proxy.cjs，已改用启动器旁的完整 IWBP：{actual}",
                    "warn",
                )
                self.cfg["work_dir"] = actual
            else:
                self.log(f"IWBP 工作目录：{actual}", "info")
            return [str(node), "tools/dev-server-proxy.cjs"], actual
        # OMICS: 内联启动 Flask+Waitress，不再依赖 run_server.py
        wd = str(Path(path))
        frontend_file = Path(wd) / "frontend" / "publish.js"
        if frontend_file.is_file():
            try:
                modified = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(frontend_file.stat().st_mtime))
                self.log(f"OMICS 前端资源：{frontend_file}（修改时间 {modified}）", "info")
            except OSError:
                self.log(f"OMICS 前端资源：{frontend_file}", "info")
        else:
            self.log(f"OMICS 前端资源缺失：{frontend_file}", "warn")
        return ([sys.executable, "-u", "-c", OMICS_INLINE_CODE, "--host", self.host,
                 "--port", str(self.port), "--work-dir", wd], wd)

    def _run(self, path):
        try:
            cmd, cwd = self._build_cmd(path)
            flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            env = os.environ.copy()
            env["PYTHONUTF8"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"
            if self.key == "iwbp":
                env["IWBP_BIND"] = "127.0.0.1"
            self.process = subprocess.Popen(
                cmd, cwd=cwd,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                env=env, creationflags=flags,
            )
            self.running = True
            self.app.after(0, self._ui_started)
            if self.key == "iwbp":
                self._start_iwbp_robot(cwd, env, flags)

            if self.key == "nginx":
                self.log(f"Nginx 配置已生成，本机入口 → {self.public_home_url}", "success")
                lan_ip = local_lan_ipv4()
                nginx_port = int(self.cfg.get("port", 8000))
                if lan_ip:
                    self.log(
                        f"局域网入口 → http://{lan_ip}:{nginx_port}/fmsa/  /omics/  /iwbp/（需放行 TCP {nginx_port}）",
                        "info",
                    )
                # Windows 版 nginx.exe 通常会拉起后台进程后立即返回；
                # 这里按监听端口维持运行状态，避免 UI 误报停止。
                time.sleep(0.8)
                while not self._quitting and is_port_in_use(self.port):
                    time.sleep(1.0)
                self.running = False
                if not self._quitting:
                    self.app.after(0, self._ui_stopped)
                return

            for line in self.process.stdout:
                s = line.rstrip()
                if s:
                    self.log_queue.put(("raw", s))

            self.process.wait()
            self.running = False
            if not self._quitting:
                self.app.after(0, self._ui_stopped)
        except Exception as exc:
            self.log_queue.put(("styled", f"启动失败：{exc}", "error"))
            self.running = False
            self.app.after(0, self._ui_stopped)

    def _start_iwbp_robot(self, cwd, env, flags):
        robot = Path(cwd) / "tools" / "robot-outbox-send.cjs"
        node = find_node_exe()
        if not robot.exists() or not node:
            return
        try:
            self.sidecar_process = subprocess.Popen(
                [str(node), str(robot), "--watch"],
                cwd=cwd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
                creationflags=flags,
            )
            self.log("工作台机器人发群进程已后台启动。", "info")
        except Exception as exc:
            self.log(f"工作台机器人未能启动：{exc}", "warn")

    def _stop_sidecar(self):
        proc = self.sidecar_process
        self.sidecar_process = None
        if not proc:
            return
        try:
            if sys.platform == "win32" and proc.pid:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                               creationflags=subprocess.CREATE_NO_WINDOW,
                               capture_output=True)
            else:
                proc.terminate()
        except Exception:
            pass

    # ── 停止 ──────────────────────────────────────────────────────────────
    def stop(self):
        if self.key == "nginx" and self.running and not self.attached:
            self.log("正在停止 Nginx…", "warn")
            try:
                exe = find_nginx_exe(self.cfg.get("exe_path", ""))
                prefix, conf = nginx_runtime_paths()
                if exe:
                    subprocess.run([str(exe), "-p", str(prefix) + os.sep, "-c", str(conf), "-s", "stop"],
                                   cwd=str(exe.parent), creationflags=subprocess.CREATE_NO_WINDOW,
                                   capture_output=True)
            except Exception as exc:
                self.log(f"停止 Nginx 时出错：{exc}", "warn")
            self.kill_port_listeners()
            self.process = None
            self.running = False
            self._ui_stopped()
            return
        if self.process and self.running and not self.attached:
            self.log("正在停止服务…", "warn")
            self._stop_sidecar()
            pid = self.process.pid
            try:
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                                   creationflags=subprocess.CREATE_NO_WINDOW,
                                   capture_output=True)
                else:
                    self.process.terminate()
            except Exception as exc:
                self.log(f"停止时出错：{exc}", "warn")
            finally:
                try:
                    self.process.wait(timeout=3)
                except Exception:
                    pass
            self.process = None
            self.running = False
            self._ui_stopped()
        elif self.attached:
            self.log("外部接管的服务无法在此停止。", "warn")

    def toggle(self):
        if self.running:
            self.stop()
        else:
            self.start()

    def check_external_health(self):
        """外部接管的服务被关闭后，恢复为可重新启动状态。"""
        if self.attached and self.running and not is_port_in_use(self.port):
            self.attached = False
            self.running = False
            self.log(f"检测到端口 {self.port} 的外部服务已退出，可重新启动。", "warn")
            self.app.after(0, self._ui_stopped)

    def kill_port_listeners(self):
        """退出时清理监听本服务端口的残留进程。"""
        if sys.platform != "win32":
            return
        try:
            result = subprocess.run(["netstat", "-ano"], capture_output=True,
                                    text=True, encoding="gbk", errors="replace",
                                    creationflags=subprocess.CREATE_NO_WINDOW)
            pids = set()
            for line in result.stdout.splitlines():
                if f":{self.port}" in line and "LISTENING" in line:
                    parts = line.split()
                    if parts:
                        pids.add(parts[-1])
            for pid in pids:
                subprocess.run(["taskkill", "/F", "/T", "/PID", pid],
                               creationflags=subprocess.CREATE_NO_WINDOW,
                               capture_output=True)
        except Exception:
            pass

    # ── 状态 UI 更新 ──────────────────────────────────────────────────────
    def _set_power_switch(self, on):
        switches = self.power_switches or ([self.power_switch] if self.power_switch else [])
        if not switches:
            return
        self._switch_syncing = True
        try:
            for sw in switches:
                if on:
                    sw.select()
                else:
                    sw.deselect()
        except Exception:
            pass
        self._switch_syncing = False

    def on_power_switch(self, want_on=None):
        if self._switch_syncing:
            return
        if want_on is None:
            if not self.power_switches:
                return
            want_on = bool(self.power_switches[0].get())
        want_on = bool(want_on)
        if want_on:
            if not self.running:
                self.start()
            else:
                self._set_power_switch(True)
            return
        if self.attached:
            self.log("外部接管的服务无法在此停止。", "warn")
            self._set_power_switch(True)
            return
        if self.running:
            self.stop()
        else:
            self._set_power_switch(False)

    def _ui_started(self):
        self._set_power_switch(True)
        self.log(f"服务已启动 → {self.public_home_url}", "success")

    def _ui_attached(self):
        self._set_power_switch(True)

    def _ui_stopped(self):
        self._set_power_switch(False)
        self.log("服务未启动", "warn")

    def _ui_unstarted(self):
        self._set_power_switch(False)

    # ── 日志 ──────────────────────────────────────────────────────────────
    def log(self, msg, level="normal"):
        self.log_queue.put(("styled", msg, level))

    def drain_logs(self):
        try:
            while True:
                item = self.log_queue.get_nowait()
                self._store_log(item)
        except queue.Empty:
            pass

    def _classify_raw(self, text):
        low = text.lower()
        if "error" in low or "exception" in low or "[error]" in low or "traceback" in low:
            return "error"
        if "warning" in low or "[warn]" in low or " warn" in low:
            return "warn"
        if "debug" in low or "[debug]" in low:
            return "debug"
        if "starting" in low or "watching" in low or "监听" in text or "已启动" in text or "running on" in low:
            return "success"
        return "normal"

    def _store_log(self, item):
        now = datetime.now().strftime("%H:%M:%S")
        if item[0] == "styled":
            _, msg, level = item
            prefix = {"info": "ℹ", "success": "✓", "warn": "⚠",
                      "error": "✕", "debug": "dbg", "normal": "·", "dim": "·"}.get(level, "·")
            entry = {
                "source": self.key,
                "ts": now,
                "level": level,
                "text": f"{prefix} {msg}",
            }
        else:
            _, text = item
            level = self._classify_raw(text)
            entry = {
                "source": self.key,
                "ts": now,
                "level": level,
                "text": text,
            }
        entry["seq"] = getattr(self.app, "_log_seq", 0)
        self.app._log_seq = entry["seq"] + 1
        self.log_entries.append(entry)
        if len(self.log_entries) > MAX_LOG_ENTRIES:
            self.log_entries = self.log_entries[-MAX_LOG_ENTRIES:]
        self.app._on_log_entry(entry)

    def clear_log(self):
        """仅清空启动器里该项目的显示缓冲，不中断进程 stdout 写入。"""
        self.app._request_clear_log(self)

    def open_home(self):
        webbrowser.open(self.public_home_url)

    @property
    def protocol_label(self):
        return "HTTP"

    @property
    def address_label(self):
        return self.host

    def open_db_tool(self):
        if self.key != "mtws":
            self.log("当前服务没有独立数据库管理工具入口。", "warn")
            return
        # 优先用配置推导的 MTWS 根目录；推导失败时回退到随包交付的 MTWS 目录。
        # 这样即使席位电脑的本地配置路径异常，只要仓库同步了工具文件就能找到。
        root = mtws_root_from_path(self.target_path())
        candidates = []
        if root:
            candidates.append(root / "data" / "sqlite_database" / "database_manage_allinone.py")
        candidates.append(DEFAULT_MTWS_DIR / "data" / "sqlite_database" / "database_manage_allinone.py")
        db_tool = next((c for c in candidates if c and c.exists()), None)
        if not db_tool:
            tried = "、".join(str(c) for c in candidates if c)
            self.log(f"找不到数据库管理工具（已尝试：{tried or '未配置 FMSA 根目录'}）", "error")
            return
        try:
            subprocess.Popen([sys.executable, str(db_tool)], cwd=str(db_tool.parent))
            self.log("数据库管理工具已启动", "info")
        except Exception as exc:
            self.log(f"启动数据库管理工具失败：{exc}", "error")


class AuthBrokerServer:
    """Nginx 统一登录态后端：保存各业务页面扫码后的 token，只监听本机 127.0.0.1。"""

    def __init__(self, app, host="127.0.0.1", port=AUTH_BROKER_PORT):
        self.app = app
        self.host = host
        self.port = port
        self.httpd = None

    def start(self):
        broker = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                return

            def _send_json(self, payload, status=200):
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()
                self.wfile.write(body)

            def do_OPTIONS(self):
                self._send_json({"success": True})

            def do_POST(self):
                if self.client_address[0] not in ("127.0.0.1", "::1"):
                    self._send_json({"success": False, "error": "forbidden"}, 403); return
                path = urlparse(self.path).path
                try:
                    length = int(self.headers.get("Content-Length", "0") or 0)
                    raw = self.rfile.read(length).decode("utf-8") if length else "{}"
                    data = json.loads(raw or "{}")
                except Exception:
                    data = {}
                if path == "/auth/update":
                    token = data.get("token")
                    user_code = data.get("userCode") or data.get("user_code") or data.get("user")
                    display_name = data.get("displayName") or data.get("display_name")
                    source = data.get("source") or "unknown"
                    if not is_usable_auth_token(token):
                        self._send_json({"success": False, "error": "missing token"}, 400); return
                    if not is_real_user_code(user_code):
                        self._send_json({"success": False, "error": "missing userCode"}, 400); return
                    broker.app.set_auth_state(token, user_code, display_name, source=source)
                    self._send_json({"success": True, **broker.app.get_auth_state(include_token=False)}); return
                if path == "/auth/clear":
                    # expired=True 由后端定时任务在确认 token 失效时上报，用于让统一登录态面板立即显示过期提示
                    broker.app.clear_auth_state(source=data.get("source") or "unknown", expired=bool(data.get("expired", False)))
                    self._send_json({"success": True}); return
                self._send_json({"success": False, "error": "not found"}, 404)

            def do_GET(self):
                if self.client_address[0] not in ("127.0.0.1", "::1"):
                    self._send_json({"success": False, "error": "forbidden"}, 403); return
                path = urlparse(self.path).path
                if path == "/auth/status":
                    state = broker.app.get_auth_state(include_token=True)
                    self._send_json({"success": True, **state}); return
                self._send_json({"success": False, "error": "not found"}, 404)

        try:
            self.httpd = ThreadingHTTPServer((self.host, self.port), Handler)
            threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
            return True
        except OSError as exc:
            try:
                self.app.omics.log(f"Nginx统一登录态接口启动失败：{exc}", "warn")
            except Exception:
                pass
            return False

    def stop(self):
        if self.httpd:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════════════
#  主窗口
# ══════════════════════════════════════════════════════════════════════════════
class LauncherApp(ctk.CTk):

    def __init__(self, ipc_sock):
        super().__init__()
        self.cfg = load_config()
        self._ipc_sock = ipc_sock
        self._quitting = False
        self._log_seq = 0
        self.tray_icon = None
        self.auth_state = {"logged_in": False, "token": None, "userCode": None, "displayName": None, "login_time": None, "source": None, "expired": False}
        self.auth_broker = None
        self._auth_validating = False
        self._load_auth_state()  # 清理旧版磁盘 token 缓存；登录态由前端 localStorage 回灌

        self.mtws = ServicePanel(self, "mtws", self.cfg["mtws"])
        self.omics = ServicePanel(self, "omics", self.cfg["omics"])
        self.iwbp = ServicePanel(self, "iwbp", self.cfg["iwbp"])
        self.nginx = ServicePanel(self, "nginx", self.cfg["nginx"])

        self.title("统一服务启动器 · FMSA/OMICS/IWBP")
        self.geometry(f"{USER_WIN_SIZE[0]}x{USER_WIN_SIZE[1]}")
        self.minsize(*USER_WIN_MIN)
        self.configure(fg_color=BG_PRIMARY)
        self._log_view = "all"
        self.filter_error = ctk.BooleanVar(value=True)
        self.filter_warn = ctk.BooleanVar(value=True)
        self.filter_info = ctk.BooleanVar(value=True)
        self.filter_debug = ctk.BooleanVar(value=True)
        self.nav_all_btn = None
        self.log_text = None
        self.log_title_label = None
        self.log_time_label = None
        self.filter_bar = None
        self._badge_photos = {}
        self._log_body_indent = 120
        self._ui_mode = "user"
        self._dev_body = None
        self._user_body = None

        self._build_ui()
        self._refresh_auth_info_label()
        if ICON_PATH.exists():
            try:
                self.iconbitmap(str(ICON_PATH))
            except Exception:
                pass
        self._configure_log_tags()
        self.auth_broker = AuthBrokerServer(self)
        self.auth_broker.start()
        self._setup_tray()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._poll_logs)
        self.after(1500, self._monitor_services)
        self.after(AUTH_VALIDATE_INTERVAL_MS, self._monitor_auth)
        self.after(300, self._autostart)

        threading.Thread(target=self._ipc_listener, daemon=True).start()
        if TRAY_AVAILABLE and self.tray_icon:
            threading.Thread(target=self.tray_icon.run, daemon=True).start()

    # ── UI ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        self._build_titlebar()
        self._dev_body = ctk.CTkFrame(self, fg_color=BG_PRIMARY, corner_radius=0)
        self._build_sidebar(self._dev_body)
        self._build_log_pane(self._dev_body)
        self._user_body = ctk.CTkFrame(self, fg_color=BG_PRIMARY, corner_radius=0)
        self._build_user_mode(self._user_body)
        self._set_ui_mode("user")
        self._refresh_nav_styles()

    def _build_titlebar(self):
        bar = ctk.CTkFrame(self, fg_color=BG_SECONDARY, corner_radius=0, height=44)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        left = ctk.CTkFrame(bar, fg_color="transparent")
        self._port_box = left
        left.pack(side="left", padx=16, pady=6)
        ctk.CTkLabel(
            left, text="统一入口 8000  ·  FMSA 8001  ·  OMICS 8002  ·  IWBP 8787",
            font=ctk.CTkFont(size=12),
            text_color="#636366",
        ).pack(side="left")

        def bind_text_hover(btn, rest="#ffffff", lit="#fff4c2"):
            btn.bind("<Enter>", lambda _e, b=btn: b.configure(text_color=lit))
            btn.bind("<Leave>", lambda _e, b=btn: b.configure(text_color=rest))

        self._quit_btn = ctk.CTkButton(
            bar, text="退出服务", width=96, command=self._quit_app,
            font=ctk.CTkFont(size=13), fg_color=COLOR_RED, hover_color="#e03a32",
            text_color="#ffffff", corner_radius=6, height=30,
        )
        bind_text_hover(self._quit_btn)

        self._path_btn = ctk.CTkButton(
            bar, text="路径配置", width=96, command=self._open_path_config,
            font=ctk.CTkFont(size=13), fg_color=COLOR_BLUE, hover_color="#007aff",
            text_color="#ffffff", corner_radius=6, height=30,
        )
        bind_text_hover(self._path_btn)

        self.auth_info_label = ctk.CTkLabel(
            bar,
            text="登录状态：未登录｜请在 FMSA / OMICS / IWBP 页面扫码",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLOR_MUTED,
            anchor="center",
        )
        ctk.CTkFrame(self, fg_color=COLOR_SEPARATOR, height=1, corner_radius=0).pack(fill="x")

    def _build_sidebar(self, parent):
        side = ctk.CTkFrame(parent, fg_color=BG_SECONDARY, corner_radius=10, width=SIDEBAR_WIDTH)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)

        self.nav_all_btn = ctk.CTkButton(
            side, text="全部", height=28, corner_radius=6,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=BG_TERTIARY, hover_color=BG_GROUPED, text_color=COLOR_LABEL,
            command=lambda: self._select_log_view("all"),
        )
        self.nav_all_btn.pack(fill="x", padx=6, pady=(8, 6))

        for svc in (self.mtws, self.omics, self.iwbp):
            self._build_service_nav(side, svc)

        ctk.CTkButton(
            side, text="切换为用户模式", height=28, corner_radius=6,
            font=ctk.CTkFont(size=12),
            fg_color=BG_TERTIARY, hover_color=BG_GROUPED, text_color=COLOR_LABEL2,
            command=lambda: self._set_ui_mode("user"),
        ).pack(side="bottom", fill="x", padx=6, pady=8)

    def _build_service_nav(self, parent, svc):
        card = ctk.CTkFrame(parent, fg_color=BG_TERTIARY, corner_radius=8)
        card.pack(fill="x", padx=6, pady=(0, 6))
        svc.nav_card = card

        blurb, abbr = SERVICE_LABELS.get(svc.key, ("", svc.key.upper()))
        ctk.CTkLabel(
            card, text=blurb,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLOR_LABEL,
            anchor="center",
            wraplength=0,
        ).pack(fill="x", padx=6, pady=(6, 0))

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=6, pady=(2, 4))
        ctk.CTkLabel(
            head, text=abbr, font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLOR_LABEL,
        ).pack(side="left")
        sw = MiniSwitch(head, command=svc.on_power_switch)
        sw.pack(side="right")
        svc.power_switch = sw
        svc.power_switches.append(sw)

        def muted_btn(text, command, extra_pady=(0, 3)):
            btn = ctk.CTkButton(
                card, text=text, height=24, corner_radius=5,
                font=ctk.CTkFont(size=11),
                fg_color=BG_SECONDARY, hover_color=BG_GROUPED,
                text_color=COLOR_LABEL2, command=command,
            )
            btn.pack(fill="x", padx=6, pady=extra_pady)
            return btn

        muted_btn("打开主页", svc.open_home)
        muted_btn("详细日志", lambda key=svc.key: self._select_log_view(key))
        muted_btn("清空", svc.clear_log, extra_pady=(0, 6 if svc.key != "mtws" else 3))
        if svc.key == "mtws":
            muted_btn("D.B.M.S", svc.open_db_tool, extra_pady=(0, 6))

    def _build_log_pane(self, parent):
        pane = ctk.CTkFrame(parent, fg_color=BG_SECONDARY, corner_radius=10)
        pane.pack(side="left", fill="both", expand=True, padx=(12, 0))

        head = ctk.CTkFrame(pane, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(10, 6))
        self.log_head = head
        self.log_title_label = ctk.CTkLabel(
            head, text="运行日志", font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLOR_LABEL,
        )
        self.log_title_label.pack(side="left")
        self.log_time_label = ctk.CTkLabel(
            head, text="", font=ctk.CTkFont(size=11), text_color="#636366",
        )
        self.log_time_label.pack(side="right")

        self.filter_bar = ctk.CTkFrame(head, fg_color="transparent")
        self.filter_bar.pack(side="left", padx=(14, 8))
        for text, var, accent in (
            ("错误", self.filter_error, "#6b3030"),
            ("告警", self.filter_warn, "#6b5420"),
            ("信息", self.filter_info, "#2d4a6b"),
            ("调试", self.filter_debug, "#3a4a58"),
        ):
            FilterChip(
                self.filter_bar, text=text, variable=var,
                command=self._rebuild_log_view, accent=accent,
            ).pack(side="left", padx=(0, 6))

        self.log_text = ctk.CTkTextbox(
            pane, font=ctk.CTkFont(family="Consolas", size=12),
            fg_color="#141416", text_color="#d1d1d6", corner_radius=8,
            wrap="word", state="disabled",
            scrollbar_button_color=BG_TERTIARY,
            scrollbar_button_hover_color=BG_GROUPED,
        )
        self.log_text.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def _build_user_mode(self, parent):
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.pack(expand=True)
        row = ctk.CTkFrame(wrap, fg_color="transparent")
        row.pack()
        for index, svc in enumerate((self.mtws, self.omics, self.iwbp)):
            self._build_user_card(row, svc, index)
        ctk.CTkButton(
            wrap, text="切换为开发者模式", height=32, corner_radius=6,
            font=ctk.CTkFont(size=13),
            fg_color=BG_SECONDARY, hover_color=BG_GROUPED, text_color=COLOR_LABEL,
            command=lambda: self._set_ui_mode("dev"),
        ).pack(fill="x", pady=(8, 0))

    def _build_user_card(self, parent, svc, index):
        card = ctk.CTkFrame(parent, fg_color=BG_SECONDARY, corner_radius=10, width=250, height=232)
        card.pack(side="left", padx=(0, 10) if index < 2 else (0, 0), pady=4)
        card.pack_propagate(False)
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=14, pady=16)
        blurb, abbr = SERVICE_LABELS.get(svc.key, ("", svc.key.upper()))
        ctk.CTkLabel(
            inner, text=blurb,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLOR_LABEL, anchor="center", wraplength=0,
        ).pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(
            inner, text=abbr, font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLOR_LABEL, anchor="center",
        ).pack(fill="x", pady=(0, 8))
        sw = MiniSwitch(inner, command=svc.on_power_switch, labeled=True)
        sw.pack(anchor="center", pady=(0, 12))
        svc.power_switches.append(sw)
        ctk.CTkButton(
            inner, text="打开主页", height=28, corner_radius=6,
            font=ctk.CTkFont(size=12),
            fg_color=COLOR_BLUE, hover_color="#007aff", text_color="#ffffff",
            command=svc.open_home,
        ).pack(fill="x", pady=(0, 6))
        url_row = ctk.CTkFrame(inner, fg_color="transparent")
        url_row.pack(fill="x")
        url = svc.public_home_url
        ctk.CTkLabel(
            url_row, text=url, font=ctk.CTkFont(size=10),
            text_color=COLOR_MUTED, anchor="w",
        ).pack(side="left", fill="x", expand=True, padx=(0, 4))
        copy_btn = ctk.CTkButton(
            url_row, text="复制", width=44, height=22, corner_radius=5,
            font=ctk.CTkFont(size=11),
            fg_color=BG_TERTIARY, hover_color=BG_GROUPED, text_color=COLOR_LABEL2,
        )
        copy_btn.configure(command=lambda u=url, b=copy_btn: self._copy_home_url(u, b))
        copy_btn.pack(side="right")

    def _copy_home_url(self, url, btn):
        try:
            self.clipboard_clear()
            self.clipboard_append(url)
            self.update()
        except Exception:
            return
        if btn:
            btn.configure(text="已复制")
            self.after(1200, lambda: btn.configure(text="复制"))

    def _apply_window_size(self, mode):
        if mode == "user":
            w, h = USER_WIN_SIZE
            self.minsize(*USER_WIN_MIN)
        else:
            w, h = DEV_WIN_SIZE
            self.minsize(*DEV_WIN_MIN)
        self.update_idletasks()
        old_w = self.winfo_width()
        old_h = self.winfo_height()
        if old_w <= 1 or old_h <= 1:
            self.geometry(f"{w}x{h}")
            return
        match = re.match(r"\d+x\d+([+-]\d+)([+-]\d+)", self.geometry())
        if match:
            old_x = int(match.group(1))
            old_y = int(match.group(2))
        else:
            old_x, old_y = self.winfo_x(), self.winfo_y()
        new_x = old_x + (old_w - w) // 2
        new_y = old_y + (old_h - h) // 2
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        new_x = max(0, min(new_x, max(0, screen_w - w)))
        new_y = max(0, min(new_y, max(0, screen_h - h)))
        self.geometry(f"{w}x{h}+{new_x}+{new_y}")

    def _sync_titlebar_mode(self, mode):
        for w in (
            getattr(self, "_port_box", None),
            getattr(self, "_path_btn", None),
            getattr(self, "_quit_btn", None),
            getattr(self, "auth_info_label", None),
        ):
            if w:
                w.pack_forget()
        if mode == "user":
            if self.auth_info_label:
                self.auth_info_label.configure(anchor="center")
                self.auth_info_label.pack(side="left", fill="x", expand=True, padx=(16, 10))
            if getattr(self, "_quit_btn", None):
                self._quit_btn.pack(side="right", padx=(8, 16), pady=7)
            return
        if getattr(self, "_port_box", None):
            self._port_box.pack(side="left", padx=16, pady=6)
        if getattr(self, "_quit_btn", None):
            self._quit_btn.pack(side="right", padx=(8, 16), pady=7)
        if getattr(self, "_path_btn", None):
            self._path_btn.pack(side="right", padx=(8, 0), pady=7)
        if self.auth_info_label:
            self.auth_info_label.configure(anchor="center")
            self.auth_info_label.pack(side="left", fill="x", expand=True, padx=(10, 10))

    def _set_ui_mode(self, mode):
        self._ui_mode = mode
        self._sync_titlebar_mode(mode)
        if mode == "user":
            if self._dev_body:
                self._dev_body.pack_forget()
            if self._user_body:
                self._user_body.pack(fill="both", expand=True, padx=16, pady=16)
        else:
            if self._user_body:
                self._user_body.pack_forget()
            if self._dev_body:
                self._dev_body.pack(fill="both", expand=True, padx=16, pady=16)
            self._refresh_nav_styles()
            self._rebuild_log_view()
        self._apply_window_size(mode)

    def _select_log_view(self, key):
        if self._log_view == key:
            return
        self._log_view = key
        titles = {
            "all": "运行日志",
            "mtws": "FMSA 详细日志",
            "omics": "OMICS 详细日志",
            "iwbp": "IWBP 详细日志",
        }
        if self.log_title_label:
            self.log_title_label.configure(text=titles.get(key, "运行日志"))
        if self.filter_bar:
            if key == "all":
                self.filter_bar.pack(side="left", padx=(14, 8), after=self.log_title_label)
            else:
                self.filter_bar.pack_forget()
        self._refresh_nav_styles()
        self._rebuild_log_view()

    def _request_clear_log(self, svc):
        names = {"mtws": "FMSA", "omics": "OMICS", "iwbp": "IWBP"}
        name = names.get(svc.key, svc.key.upper())
        self._select_log_view(svc.key)
        ClearLogConfirmDialog(self, name, on_confirm=lambda: self._clear_log_display(svc))

    def _clear_log_display(self, svc):
        svc.log_entries.clear()
        self._rebuild_log_view()

    def _refresh_nav_styles(self):
        if self.nav_all_btn:
            if self._log_view == "all":
                self.nav_all_btn.configure(fg_color=BG_GROUPED, text_color=COLOR_LABEL)
            else:
                self.nav_all_btn.configure(fg_color=BG_TERTIARY, text_color=COLOR_LABEL2)
        for svc in (self.mtws, self.omics, self.iwbp):
            if not svc.nav_card:
                continue
            if self._log_view == svc.key:
                svc.nav_card.configure(fg_color="#3f3f42")
            else:
                svc.nav_card.configure(fg_color=BG_TERTIARY)

    def _passes_filter(self, entry):
        if self._log_view != "all":
            return True
        level = entry.get("level") or "normal"
        if level in LOG_FILTER_GROUPS["error"]:
            return bool(self.filter_error.get())
        if level in LOG_FILTER_GROUPS["warn"]:
            return bool(self.filter_warn.get())
        if level in LOG_FILTER_GROUPS["debug"]:
            return bool(self.filter_debug.get())
        return bool(self.filter_info.get())

    def _visible_entries(self):
        sources = ("mtws", "omics", "iwbp")
        if self._log_view == "all":
            merged = []
            for key in sources:
                merged.extend(getattr(self, key).log_entries)
            merged.sort(key=lambda e: e.get("seq", 0))
            return [e for e in merged if self._passes_filter(e)]
        svc = getattr(self, self._log_view, None)
        return list(svc.log_entries) if svc else []

    def _on_log_entry(self, entry):
        if getattr(self, "_ui_mode", "dev") != "dev":
            return
        source = entry.get("source")
        if source not in ("mtws", "omics", "iwbp"):
            return
        if self._log_view not in ("all", source):
            return
        if not self._passes_filter(entry):
            return
        self._insert_log_line(entry)
        if self.log_time_label:
            self.log_time_label.configure(text="更新 " + entry.get("ts", ""))

    def _rebuild_log_view(self):
        if not self.log_text or getattr(self, "_ui_mode", "dev") != "dev":
            return
        tb = self.log_text._textbox
        tb.configure(state="normal")
        tb.delete("1.0", "end")
        last_ts = ""
        for entry in self._visible_entries():
            self._insert_log_line(entry, already_enabled=True)
            last_ts = entry.get("ts") or last_ts
        tb.configure(state="disabled")
        tb.see("end")
        if self.log_time_label:
            self.log_time_label.configure(text=("更新 " + last_ts) if last_ts else "")

    def _insert_log_line(self, entry, already_enabled=False):
        if not self.log_text:
            return
        tb = self.log_text._textbox
        if not already_enabled:
            tb.configure(state="normal")
        start = tb.index("end-1c")
        source = entry.get("source")
        photo = self._badge_photos.get(source)
        if photo:
            tb.image_create("end", image=photo, pady=1)
            tb.insert("end", " ")
        elif source in BADGE_STYLE:
            tb.insert("end", f" {BADGE_STYLE[source]['text']:^5} ", f"badge_{source}")
            tb.insert("end", " ")
        tb.insert("end", f"{entry.get('ts', '')}  ", "dim")
        level = entry.get("level") or "normal"
        tb.insert("end", entry.get("text", "") + "\n", level)
        tb.tag_add("logline", start, "end-1c")
        if not already_enabled:
            self._trim_log_widget(tb)
            tb.configure(state="disabled")
            tb.see("end")

    def _trim_log_widget(self, tb):
        cap = MAX_LOG_ENTRIES if self._log_view != "all" else MAX_LOG_ENTRIES * 3
        last_line = int(tb.index("end-1c").split(".")[0])
        extra = last_line - cap
        if extra > 200:
            tb.delete("1.0", f"{extra + 1}.0")

    def _make_badge_photo(self, text, bg, fg):
        if not PIL_AVAILABLE:
            return None
        scale = 3
        w, h, r = BADGE_W * scale, BADGE_H * scale, BADGE_RADIUS * scale
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=_hex_rgb(bg) + (255,))
        font_path = next((
            p for p in (
                "C:/Windows/Fonts/consolab.ttf",
                "C:/Windows/Fonts/consola.ttf",
                "C:/Windows/Fonts/arialbd.ttf",
                "C:/Windows/Fonts/msyhbd.ttc",
            ) if Path(p).exists()
        ), None)
        pad_x, pad_y = 3 * scale, 1 * scale
        font = ImageFont.load_default()
        if font_path:
            for size in range(h - pad_y * 2, 10, -1):
                try:
                    trial = ImageFont.truetype(font_path, size)
                except Exception:
                    continue
                bbox = draw.textbbox((0, 0), text, font=trial)
                if bbox[2] - bbox[0] <= w - pad_x * 2 and bbox[3] - bbox[1] <= h - pad_y * 2:
                    font = trial
                    break
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(
            ((w - tw) / 2 - bbox[0], (h - th) / 2 - bbox[1] - scale),
            text,
            font=font,
            fill=_hex_rgb(fg) + (255,),
        )
        img = img.resize((BADGE_W, BADGE_H), Image.LANCZOS)
        return ImageTk.PhotoImage(img, master=self)

    def _configure_log_tags(self):
        if not self.log_text:
            return
        tb = self.log_text._textbox
        body_font = tkfont.Font(font=tb.cget("font"))
        self._log_body_indent = BADGE_W + 6 + body_font.measure("88:88:88  ")
        tb.configure(spacing1=3, spacing3=5)
        tb.tag_configure("info", foreground=COLOR_BLUE)
        tb.tag_configure("success", foreground=COLOR_GREEN)
        tb.tag_configure("warn", foreground=COLOR_ORANGE)
        tb.tag_configure("error", foreground=COLOR_RED)
        tb.tag_configure("debug", foreground=COLOR_DEBUG)
        tb.tag_configure("normal", foreground="#d1d1d6")
        tb.tag_configure("dim", foreground="#636366")
        tb.tag_configure(
            "logline",
            lmargin2=self._log_body_indent,
            spacing1=3,
            spacing3=5,
        )
        self._badge_photos = {}
        for key, style in BADGE_STYLE.items():
            photo = self._make_badge_photo(style["text"], style["bg"], style["fg"])
            if photo:
                self._badge_photos[key] = photo
            tb.tag_configure(
                f"badge_{key}",
                background=style["bg"],
                foreground=style["fg"],
                font=("Consolas", 11, "bold"),
            )

    # ── 日志轮询 ──────────────────────────────────────────────────────────
    def _poll_logs(self):
        self.mtws.drain_logs()
        self.omics.drain_logs()
        self.iwbp.drain_logs()
        self.nginx.drain_logs()
        self.after(80, self._poll_logs)

    def _monitor_services(self):
        if not self._quitting:
            self.mtws.check_external_health()
            self.omics.check_external_health()
            self.iwbp.check_external_health()
            self.nginx.check_external_health()
            self.after(1500, self._monitor_services)

    # ── 启动控制 ──────────────────────────────────────────────────────────
    def _autostart(self):
        # 初始各服务显示未启动状态提示
        for svc in (self.mtws, self.omics, self.iwbp, self.nginx):
            path = svc.target_path()
            if svc.key == "mtws":
                ok = bool(resolve_mtws_manage_py(path))
            elif svc.key == "omics":
                ok = bool(path and os.path.isdir(path))
            elif svc.key == "iwbp":
                ok = bool(resolve_iwbp_root(path) and find_node_exe())
            else:
                ok = bool(find_nginx_exe(svc.cfg.get("exe_path", "")))
            if not ok:
                if svc.key == "nginx":
                    svc.log("未找到 nginx.exe。后端会启动，但 8000 统一入口需安装/放置 Nginx 后才能工作。", "warn")
                elif svc.key == "iwbp" and not find_node_exe():
                    svc.log("未找到 node.exe，IWBP 无法启动。请安装 Node.js LTS。", "warn")
                elif svc.key == "iwbp":
                    svc.log("IWBP 启动脚本未就绪，将在启动时再检查 tools\\dev-server-proxy.cjs。", "warn")
                else:
                    svc.log(f"未配置启动路径，请点右上「路径配置」。", "warn")
        self._start_all()

    def _start_all(self):
        for svc in (self.mtws, self.omics, self.iwbp):
            try:
                svc.start()
            except Exception as exc:
                svc.log(f"启动失败：{exc}", "error")
        # Nginx 需要后端端口已开始启动后再接入
        self.after(1200, self.nginx.start)

    # ── 路径配置 ──────────────────────────────────────────────────────────
    def _open_path_config(self):
        PathConfigDialog(self)


    def resolve_display_name(self, user_code):
        if not user_code or user_code == "--" or requests is None or not self.omics.running:
            return user_code or "账号"
        try:
            res = requests.get(f"{self.omics.home_url.rstrip('/')}/api/personnel_mapping", timeout=2)
            data = res.json()
            if data.get("success") and isinstance(data.get("data"), dict):
                return data["data"].get(str(user_code), str(user_code))
        except Exception:
            pass
        return str(user_code)

    def _save_auth_state(self):
        """将当前登录态落盘，供 launcher 重启后恢复，使后端定时任务无需等待前端重新推送。"""
        try:
            AUTH_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(AUTH_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.auth_state, f, ensure_ascii=False)
            try:
                os.chmod(AUTH_STATE_FILE, 0o600)
            except Exception:
                pass
        except Exception:
            pass

    def _load_auth_state(self):
        """启动时从磁盘恢复登录态，避免 launcher 重启后需要重新扫码才能供定时任务使用。"""
        try:
            if AUTH_STATE_FILE.exists():
                with open(AUTH_STATE_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                if isinstance(saved, dict) and set(saved.keys()) >= set(self.auth_state.keys()):
                    if is_usable_auth_token(saved.get("token")) and is_real_user_code(saved.get("userCode")):
                        self.auth_state = saved
                    else:
                        self.auth_state = {
                            "logged_in": False, "token": None, "userCode": None,
                            "displayName": None, "login_time": None, "source": "invalid_saved_state",
                            "expired": False,
                        }
                        self._save_auth_state()
                        self._refresh_auth_info_label()
        except Exception:
            pass

    def set_auth_state(self, token, user_code=None, display_name=None, source=None):
        if not is_usable_auth_token(token) or not is_real_user_code(user_code):
            return
        name = display_name or self.resolve_display_name(user_code)
        self.auth_state = {
            "logged_in": True,
            "token": token,
            "userCode": str(user_code).strip(),
            "displayName": name,
            "login_time": datetime.now().isoformat(timespec="seconds"),
            "source": source or "unknown",
            "expired": False,
        }
        self._save_auth_state()
        self._refresh_auth_info_label()
        self.omics.log(f"统一登录态已更新：{name}（来源：{source or 'unknown'}）。Token 由 Nginx 统一入口复用。", "success")

    def clear_auth_state(self, source=None, expired=False):
        self.auth_state = {"logged_in": False, "token": None, "userCode": None, "displayName": None, "login_time": None, "source": source, "expired": bool(expired)}
        self._save_auth_state()
        self._refresh_auth_info_label()
        if expired:
            self.omics.log(f"登录已过期（来源：{source or 'token校验'}），FMSA / OMICS / IWBP 页面将自动登出，请重新扫码登录。", "warn")
        else:
            self.omics.log(f"统一登录态已清空（来源：{source or 'unknown'}）。", "info")

    def _refresh_auth_info_label(self):
        if not hasattr(self, "auth_info_label") or not self.auth_info_label:
            return
        state = self.get_auth_state(include_token=False)
        if state.get("logged_in"):
            name = state.get("displayName") or state.get("userCode") or "未知用户"
            source = state.get("source") or "业务页面"
            login_time = state.get("login_time") or ""
            self.auth_info_label.configure(
                text=f"当前登录：{name}｜来源：{source}｜{login_time}",
                text_color=COLOR_GREEN,
                fg_color="transparent",
                font=ctk.CTkFont(size=12, weight="bold"),
            )
        elif state.get("expired"):
            self.auth_info_label.configure(
                text="登录已过期｜请在 FMSA / OMICS / IWBP 页面重新扫码登录",
                text_color="#5c3a14",
                fg_color=COLOR_APRICOT,
                corner_radius=8,
                font=ctk.CTkFont(size=12, weight="bold"),
            )
        else:
            self.auth_info_label.configure(
                text="登录状态：未登录｜请在 FMSA / OMICS / IWBP 页面扫码",
                text_color=COLOR_MUTED,
                fg_color="transparent",
                font=ctk.CTkFont(size=12, weight="bold"),
            )

    def _monitor_auth(self):
        """控制台后台定期校验统一 token 是否仍有效；过期则自动登出并通知前端。"""
        if not self._quitting:
            try:
                if self.auth_state.get("logged_in") and self.auth_state.get("token") and not self._auth_validating:
                    self._auth_validating = True
                    threading.Thread(target=self._validate_token_worker,
                                     args=(self.auth_state.get("token"),), daemon=True).start()
            except Exception:
                pass
            self.after(AUTH_VALIDATE_INTERVAL_MS, self._monitor_auth)

    def _validate_token_worker(self, token):
        """后台线程：调用 SF 航班接口轻量校验 token。401 视为过期；网络错误视为仍有效，不误护登出。"""
        try:
            if requests is None:
                return
            now_ms = int(time.time() * 1000)
            headers = {"token": token, "Content-Type": "application/json"}
            payload = {
                "startTime": now_ms - 3600 * 1000,
                "endTime": now_ms + 3600 * 1000,
                "excludeCancel": True,
                "excludeHaveAta": True,
            }
            resp = requests.post(SF_FLIGHT_VALIDATE_URL, headers=headers, json=payload, timeout=10)
            if resp.status_code == 401:
                # token 已过期/异地登录被挤下线，仅在仍是同一个 token 时才清理，避免覆盖期间新登录。
                if self.auth_state.get("token") == token:
                    self.after(0, lambda: self.clear_auth_state(source="token过期", expired=True))
        except Exception:
            # 网络异常等不当作过期处理，保守起见保留登录态。
            pass
        finally:
            self._auth_validating = False

    def get_auth_state(self, include_token=False):
        state = dict(self.auth_state)
        if not include_token:
            state.pop("token", None)
        return state

    def apply_config(self, new_cfg, autostart=False):
        self.cfg = new_cfg
        self.cfg.setdefault("iwbp", json.loads(json.dumps(DEFAULT_CONFIG["iwbp"])))
        self.mtws.cfg = new_cfg["mtws"]
        self.omics.cfg = new_cfg["omics"]
        self.iwbp.cfg = new_cfg["iwbp"]
        self.nginx.cfg = new_cfg["nginx"]
        save_config(new_cfg)
        if autostart:
            self.after(100, self._start_all)

    # ── 托盘 ──────────────────────────────────────────────────────────────
    def _setup_tray(self):
        if not TRAY_AVAILABLE:
            return
        icon_img = self._make_tray_icon()
        menu = pystray.Menu(
            pystray.MenuItem("显示窗口", lambda i, it: self._show_window(), default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("全部启动", lambda i, it: self.after(0, self._start_all)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出服务", lambda i, it: self.after(0, self._quit_app)),
        )
        self.tray_icon = pystray.Icon("Launcher", icon_img, "航空气象统一启动器", menu)

    def _make_tray_icon(self):
        if TRAY_ICON_PATH.exists():
            try:
                return Image.open(TRAY_ICON_PATH).convert("RGBA").resize((64, 64), Image.LANCZOS)
            except Exception:
                pass
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse([1, 1, size - 1, size - 1], fill=(28, 28, 30, 255))
        d.ellipse([6, 6, size - 6, size - 6], fill=(10, 132, 255, 255))
        d.rectangle([26, 16, 38, 48], fill=(255, 255, 255, 255))
        d.polygon([(14, 28), (50, 28), (32, 14)], fill=(255, 255, 255, 255))
        return img

    # ── 窗口/退出 ─────────────────────────────────────────────────────────
    def _on_close(self):
        if TRAY_AVAILABLE and self.tray_icon:
            self.withdraw()
            return
        # pystray/Pillow 未安装时无法挂托盘，关闭窗口会真正退出服务。
        try:
            self.mtws.log("未安装 pystray/Pillow，关闭窗口将退出服务。请执行: python -m pip install pystray pillow", "warn")
        except Exception:
            pass
        self._quit_app()

    def _show_window(self):
        self.after(0, self._do_show_window)

    def _do_show_window(self):
        self.deiconify(); self.state("normal"); self.lift(); self.focus_force()

    def _quit_app(self):
        self._quitting = True
        self.mtws._quitting = True
        self.omics._quitting = True
        self.iwbp._quitting = True
        self.nginx._quitting = True
        for svc in (self.nginx, self.mtws, self.omics, self.iwbp):
            try:
                if not svc.attached:
                    svc.stop()
                svc.kill_port_listeners()
            except Exception:
                pass
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        if self.auth_broker:
            self.auth_broker.stop()
        try:
            self._ipc_sock.close()
        except Exception:
            pass
        try:
            self.quit(); self.destroy()
        except Exception:
            pass
        os._exit(0)

    def _ipc_listener(self):
        while not self._quitting:
            try:
                self._ipc_sock.settimeout(1.0)
                conn, _ = self._ipc_sock.accept()
                try:
                    if conn.recv(16) == b"SHOW":
                        self._show_window()
                finally:
                    conn.close()
            except socket.timeout:
                continue
            except Exception:
                break


# ══════════════════════════════════════════════════════════════════════════════
#  清空显示日志确认
# ══════════════════════════════════════════════════════════════════════════════
class ClearLogConfirmDialog(ctk.CTkToplevel):
    def __init__(self, app, project_name, on_confirm):
        super().__init__(app)
        self._on_confirm = on_confirm
        self.title("清空日志")
        self.resizable(False, False)
        self.configure(fg_color=BG_SECONDARY)
        self.transient(app)
        self.withdraw()

        ctk.CTkLabel(
            self, text=f"是否确认清除{project_name}的全部日志信息？",
            font=ctk.CTkFont(size=14), text_color=COLOR_LABEL, anchor="w",
        ).pack(fill="x", padx=24, pady=(22, 6))
        ctk.CTkLabel(
            self, text="（清空日志信息不影响本地运行日志写入）",
            font=ctk.CTkFont(size=11), text_color=COLOR_MUTED, anchor="w",
        ).pack(fill="x", padx=24, pady=(0, 16))

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=24, pady=(0, 20))
        ctk.CTkButton(
            btn_row, text="取消", command=self.destroy,
            fg_color=BG_TERTIARY, hover_color=BG_GROUPED,
            text_color=COLOR_LABEL2, corner_radius=8, height=32, width=110,
        ).pack(side="left")
        ctk.CTkButton(
            btn_row, text="确认清空", command=self._confirm,
            fg_color=COLOR_RED, hover_color="#e03a32",
            text_color="#ffffff", corner_radius=8, height=32, width=110,
        ).pack(side="right")

        self.update_idletasks()
        width, height = 420, 168
        px = app.winfo_rootx()
        py = app.winfo_rooty()
        pw = max(app.winfo_width(), 1)
        ph = max(app.winfo_height(), 1)
        x = px + (pw - width) // 2
        y = py + (ph - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.deiconify()
        self.grab_set()
        self.lift()
        self.focus_force()

    def _confirm(self):
        callback = self._on_confirm
        self.destroy()
        if callback:
            callback()


# ══════════════════════════════════════════════════════════════════════════════
#  路径配置弹窗
# ══════════════════════════════════════════════════════════════════════════════
class PathConfigDialog(ctk.CTkToplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.cfg = json.loads(json.dumps(app.cfg))  # 编辑副本

        self.title("路径配置")
        self.geometry("720x640")
        self.resizable(False, False)
        self.configure(fg_color=BG_SECONDARY)
        self.grab_set(); self.lift(); self.focus_force()

        ctk.CTkLabel(self, text="服务路径配置", font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=COLOR_LABEL).pack(anchor="w", padx=24, pady=(20, 2))
        ctk.CTkLabel(self, text="各程序可放在不同文件夹；选择对应项目根目录。",
                     font=ctk.CTkFont(size=11), text_color="#8e8e93").pack(anchor="w", padx=24)

        # MTWS
        self.mtws_entry = self._dir_row(
            "FMSA 程序根目录（server_gui.py 所在目录）",
            self.cfg["mtws"].get("work_dir", ""),
            "选择 FMSA 程序根目录")
        self.mtws_port = self._port_row("FMSA 内部端口", self.cfg["mtws"].get("port", 8001))

        ctk.CTkFrame(self, fg_color=COLOR_SEPARATOR, height=1).pack(fill="x", padx=24, pady=10)

        # OMICS
        self.omics_entry = self._dir_row(
            "OMICS 项目根目录（包含 backend/frontend）",
            self.cfg["omics"].get("work_dir", str(SCRIPT_DIR)),
            "选择 OMICS 项目根目录")
        self.omics_port = self._port_row("OMICS 内部端口", self.cfg["omics"].get("port", 8002))

        ctk.CTkFrame(self, fg_color=COLOR_SEPARATOR, height=1).pack(fill="x", padx=24, pady=10)

        self.iwbp_entry = self._dir_row(
            "IWBP 项目根目录（含 tools/dev-server-proxy.cjs）",
            self.cfg.get("iwbp", {}).get("work_dir")
            or (str(DEFAULT_IWBP_DIR) if DEFAULT_IWBP_DIR.exists() else ""),
            "选择 IWBP 项目根目录")
        self.iwbp_port = self._port_row("IWBP 内部端口", self.cfg.get("iwbp", {}).get("port", 8787))

        ctk.CTkFrame(self, fg_color=COLOR_SEPARATOR, height=1).pack(fill="x", padx=24, pady=10)

        self.nginx_entry = self._path_row(
            "Nginx.exe 路径（可空；默认查找 tools/nginx/nginx.exe 或 PATH）",
            self.cfg.get("nginx", {}).get("exe_path", ""),
            "选择 nginx.exe",
            [("nginx.exe", "nginx.exe"), ("可执行文件", "*.exe"), ("所有文件", "*.*")])
        self.nginx_port = self._port_row("Nginx 对外端口", self.cfg.get("nginx", {}).get("port", 8000))

        self.hint = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=11), text_color=COLOR_ORANGE)
        self.hint.pack(anchor="w", padx=24, pady=(8, 0))

        btn_row = ctk.CTkFrame(self, fg_color="transparent"); btn_row.pack(fill="x", padx=24, pady=(14, 18))
        ctk.CTkButton(btn_row, text="取消", command=self.destroy, fg_color=BG_TERTIARY,
                      hover_color=BG_GROUPED, text_color=COLOR_LABEL2, corner_radius=8,
                      height=34, width=120).pack(side="left", expand=True, padx=(0, 6))
        ctk.CTkButton(btn_row, text="保存", command=self._save, fg_color=COLOR_GREEN,
                      hover_color="#27a846", text_color="#fff", corner_radius=8,
                      height=34, width=120).pack(side="right", expand=True, padx=(6, 0))

    def _path_row(self, label, value, dlg_title, filetypes):
        ctk.CTkLabel(self, text=label, font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=COLOR_LABEL2).pack(anchor="w", padx=24, pady=(12, 2))
        row = ctk.CTkFrame(self, fg_color="transparent"); row.pack(fill="x", padx=24)
        entry = ctk.CTkEntry(row, font=ctk.CTkFont(size=11), fg_color=BG_TERTIARY,
                             border_color=BG_GROUPED, text_color=COLOR_LABEL)
        entry.pack(side="left", fill="x", expand=True)
        entry.insert(0, value or "")

        def browse():
            from tkinter import filedialog
            f = filedialog.askopenfilename(title=dlg_title, filetypes=filetypes)
            if f:
                entry.delete(0, "end"); entry.insert(0, f)
        ctk.CTkButton(row, text="浏览", width=60, command=browse, fg_color=COLOR_BLUE,
                      hover_color="#007aff", text_color="#fff", corner_radius=8).pack(side="right", padx=(8, 0))
        return entry

    def _dir_row(self, label, value, dlg_title):
        ctk.CTkLabel(self, text=label, font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=COLOR_LABEL2).pack(anchor="w", padx=24, pady=(12, 2))
        row = ctk.CTkFrame(self, fg_color="transparent"); row.pack(fill="x", padx=24)
        entry = ctk.CTkEntry(row, font=ctk.CTkFont(size=11), fg_color=BG_TERTIARY,
                             border_color=BG_GROUPED, text_color=COLOR_LABEL)
        entry.pack(side="left", fill="x", expand=True)
        entry.insert(0, value or "")
        def browse():
            from tkinter import filedialog
            d = filedialog.askdirectory(title=dlg_title)
            if d:
                entry.delete(0, "end"); entry.insert(0, d)
        ctk.CTkButton(row, text="浏览", width=60, command=browse, fg_color=COLOR_BLUE,
                      hover_color="#007aff", text_color="#fff", corner_radius=8).pack(side="right", padx=(8, 0))
        return entry

    def _port_row(self, label, value):
        row = ctk.CTkFrame(self, fg_color="transparent"); row.pack(fill="x", padx=24, pady=(6, 0))
        ctk.CTkLabel(row, text=label, font=ctk.CTkFont(size=11), text_color="#8e8e93").pack(side="left")
        entry = ctk.CTkEntry(row, width=100, font=ctk.CTkFont(size=11), fg_color=BG_TERTIARY,
                             border_color=BG_GROUPED, text_color=COLOR_LABEL)
        entry.pack(side="left", padx=(8, 0))
        entry.insert(0, str(value))
        return entry

    def _save(self):
        mtws_path = self.mtws_entry.get().strip()
        omics_path = self.omics_entry.get().strip()
        iwbp_path = self.iwbp_entry.get().strip()
        if mtws_path and not resolve_mtws_manage_py(mtws_path):
            self.hint.configure(text="⚠ 程序根目录无效，需能定位到 fmsa_django/manage.py。"); return
        if omics_path and (not os.path.isdir(os.path.join(omics_path, "backend")) or not os.path.isdir(os.path.join(omics_path, "frontend"))):
            self.hint.configure(text="⚠ OMICS 项目根目录无效，需包含 backend/frontend。"); return
        resolved_iwbp = resolve_iwbp_root(iwbp_path) if iwbp_path else resolve_iwbp_root(DEFAULT_IWBP_DIR)
        if iwbp_path and not resolved_iwbp:
            self.hint.configure(text="⚠ IWBP 根目录无效，需能定位到 tools/dev-server-proxy.cjs。"); return
        try:
            self.cfg["mtws"]["port"] = int(self.mtws_port.get().strip() or 8001)
            self.cfg["omics"]["port"] = int(self.omics_port.get().strip() or 8002)
            self.cfg.setdefault("iwbp", {})["port"] = int(self.iwbp_port.get().strip() or 8787)
            self.cfg.setdefault("nginx", {})["port"] = int(self.nginx_port.get().strip() or 8000)
        except ValueError:
            self.hint.configure(text="⚠ 端口必须是数字。"); return
        nginx_port = self.cfg["nginx"]["port"]
        self.cfg["mtws"]["work_dir"] = mtws_path
        self.cfg["mtws"]["public_home_url"] = f"http://127.0.0.1:{nginx_port}/fmsa/"
        self.cfg["mtws"].pop("manage_py", None)
        self.cfg["omics"]["work_dir"] = omics_path or str(SCRIPT_DIR)
        self.cfg["omics"]["public_home_url"] = f"http://127.0.0.1:{nginx_port}/omics/"
        self.cfg["omics"].pop("run_server", None)
        self.cfg.setdefault("iwbp", {})
        self.cfg["iwbp"]["name"] = self.cfg["iwbp"].get("name") or "IWBP 业务工作台"
        self.cfg["iwbp"]["host"] = "127.0.0.1"
        self.cfg["iwbp"]["home_path"] = "/index.html"
        self.cfg["iwbp"]["work_dir"] = str(resolved_iwbp) if resolved_iwbp else (iwbp_path or "")
        self.cfg["iwbp"]["public_home_url"] = f"http://127.0.0.1:{nginx_port}/iwbp/"
        self.cfg["nginx"].setdefault("name", "Nginx 统一入口")
        self.cfg["nginx"]["host"] = "0.0.0.0"
        self.cfg["nginx"]["public_home_url"] = f"http://127.0.0.1:{nginx_port}/fmsa/"
        self.cfg["nginx"]["exe_path"] = self.nginx_entry.get().strip()
        self.app.apply_config(self.cfg, autostart=True)
        self.hint.configure(text="✓ 已保存，正在启动未运行的服务。", text_color=COLOR_GREEN)
        self.after(900, self.destroy)


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    ipc_sock = acquire_single_instance()
    if ipc_sock is None:
        sys.exit(0)
    app = LauncherApp(ipc_sock)
    app.mainloop()
