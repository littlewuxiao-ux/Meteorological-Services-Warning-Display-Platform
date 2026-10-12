"""
FMSA 服务端图形化控制台
深色 macOS 风格 · CustomTkinter
"""

import customtkinter as ctk
import subprocess
import threading
import webbrowser
import sys
import os
import queue
import socket
from datetime import datetime
from pathlib import Path

try:
    import pystray
    from PIL import Image, ImageDraw, ImageFont, ImageTk
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False

# ── 路径常量 ──────────────────────────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).parent
DJANGO_DIR  = SCRIPT_DIR / "mtws_django"
MANAGE_PY   = DJANGO_DIR / "manage.py"
DB_TOOL     = SCRIPT_DIR / "data" / "sqlite_database" / "database_manage_allinone.py"
HOME_URL    = "http://127.0.0.1:8000/current/"

DJANGO_PORT  = 8000          # Django 服务端口
IPC_PORT     = 19527         # GUI 单实例 IPC 端口（内部通信）
ICON_HEADER  = SCRIPT_DIR / "assets" / "icon_header.png"  # UI 标题栏图标
ICON_BOTTOM  = SCRIPT_DIR / "assets" / "icon_bottom.png"  # 任务栏图标

# ── macOS 深色系统配色 ─────────────────────────────────────────────────────────
BG_PRIMARY        = "#1c1c1e"   # systemBackground (dark)
BG_SECONDARY      = "#2c2c2e"   # secondarySystemBackground
BG_TERTIARY       = "#3a3a3c"   # tertiarySystemBackground
BG_GROUPED        = "#48484a"
COLOR_BLUE        = "#0a84ff"
COLOR_GREEN       = "#30d158"
COLOR_RED         = "#ff453a"
COLOR_ORANGE      = "#ff9f0a"
COLOR_LABEL       = "#ffffff"
COLOR_LABEL2      = "#ebebf5"   # ~60% opacity equivalent
COLOR_LABEL3      = "#ebebf599"
COLOR_SEPARATOR   = "#38383a"
COLOR_FILL_BLUE   = "#0a84ff26"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")


# ══════════════════════════════════════════════════════════════════════════════
#  单实例 & 端口检测
# ══════════════════════════════════════════════════════════════════════════════

def is_port_in_use(port: int) -> bool:
    """检查本地 TCP 端口是否已被占用（有服务在监听）"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def acquire_single_instance() -> "socket.socket | None":
    """
    尝试绑定 IPC 端口以声明"我是第一个实例"。
    - 成功：返回已绑定的 socket（调用方需保持引用）。
    - 失败（端口已占用）：向已有实例发送 SHOW 信号，然后返回 None。
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    try:
        sock.bind(("127.0.0.1", IPC_PORT))
        sock.listen(5)
        return sock          # 第一个实例
    except OSError:
        sock.close()
        # 向已有实例发送唤醒信号
        try:
            c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            c.settimeout(1)
            c.connect(("127.0.0.1", IPC_PORT))
            c.sendall(b"SHOW")
            c.close()
        except Exception:
            pass
        return None          # 已有实例正在运行


# ─────────────────────────────────────────────────────────────────────────────
class MTWSServerGUI(ctk.CTk):

    def __init__(self, ipc_sock: "socket.socket"):
        super().__init__()

        self.title("FMSA 服务端控制台")
        self.geometry("920x660")
        self.minsize(740, 560)
        self.configure(fg_color=BG_PRIMARY)

        # ── 内部状态 ──────────────────────────────────────────────────────
        self.server_process: subprocess.Popen | None = None
        self.server_running  = False
        self._attached       = False   # True = 接管了外部已有服务（非本进程启动）
        self.log_queue       = queue.Queue()
        self.tray_icon       = None
        self._tray_running   = False
        self._quitting       = False
        self._ipc_sock       = ipc_sock

        self._build_ui()
        self._configure_log_tags()
        self._setup_tray()
        # 延迟到事件循环启动后再设图标，确保窗口句柄已就绪
        self.after(300, self._setup_window_icon)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._poll_logs)
        self.after(300, self._start_server)   # 稍延迟，待 UI 完全渲染后启动

        # IPC 监听：接收其他实例发来的 SHOW 信号
        threading.Thread(target=self._ipc_listener, daemon=True).start()

        # 程序启动后立即挂载托盘图标（不必等关闭窗口）
        if TRAY_AVAILABLE and self.tray_icon:
            self._tray_running = True
            threading.Thread(target=self.tray_icon.run, daemon=True).start()

    # ══════════════════════════════════════════════════════════════════════════
    #  UI 构建
    # ══════════════════════════════════════════════════════════════════════════

    def _build_ui(self):
        self._build_titlebar()
        self._build_body()

    # ── 顶部标题栏 ────────────────────────────────────────────────────────────
    def _build_titlebar(self):
        bar = ctk.CTkFrame(self, fg_color=BG_SECONDARY, corner_radius=0, height=52)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        # 左侧：图标 + 标题
        left = ctk.CTkFrame(bar, fg_color="transparent")
        left.pack(side="left", padx=18, pady=8)

        # 标题栏图标：优先使用 PNG，降级为文字
        if TRAY_AVAILABLE and ICON_HEADER.exists():
            _raw = Image.open(ICON_HEADER).convert("RGBA")
            _ctk_icon = ctk.CTkImage(light_image=_raw, dark_image=_raw, size=(28, 28))
            icon_lbl = ctk.CTkLabel(left, text="", image=_ctk_icon, width=32)
        else:
            icon_lbl = ctk.CTkLabel(
                left, text="✈",
                font=ctk.CTkFont(size=22),
                text_color=COLOR_BLUE,
                width=32
            )
        icon_lbl.pack(side="left")

        ctk.CTkLabel(
            left,
            text="FMSA  基于航班计划的气象监视告警系统",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=COLOR_LABEL
        ).pack(side="left", padx=(6, 0))

        ctk.CTkLabel(
            left,
            text="服务端控制台",
            font=ctk.CTkFont(size=11),
            text_color="#636366"
        ).pack(side="left", padx=(8, 0), pady=(2, 0))

        # 右侧：运行状态
        right = ctk.CTkFrame(bar, fg_color="transparent")
        right.pack(side="right", padx=18)

        self.status_dot = ctk.CTkLabel(
            right, text="●",
            font=ctk.CTkFont(size=13),
            text_color=COLOR_RED
        )
        self.status_dot.pack(side="right", padx=(4, 0))

        self.status_label = ctk.CTkLabel(
            right, text="未启动",
            font=ctk.CTkFont(size=12),
            text_color="#636366"
        )
        self.status_label.pack(side="right")

        # 分割线
        ctk.CTkFrame(self, fg_color=COLOR_SEPARATOR, height=1, corner_radius=0).pack(fill="x")

    # ── 主体：侧边栏 + 日志 ───────────────────────────────────────────────────
    def _build_body(self):
        body = ctk.CTkFrame(self, fg_color=BG_PRIMARY, corner_radius=0)
        body.pack(fill="both", expand=True, padx=16, pady=16)

        self._build_sidebar(body)
        self._build_log_panel(body)

    def _build_sidebar(self, parent):
        sidebar = ctk.CTkFrame(parent, fg_color=BG_SECONDARY, corner_radius=12, width=210)
        sidebar.pack(side="left", fill="y", padx=(0, 12))
        sidebar.pack_propagate(False)

        # ── 服务器信息卡片 ──
        self._section_title(sidebar, "服务器信息")

        info_card = ctk.CTkFrame(sidebar, fg_color=BG_TERTIARY, corner_radius=10)
        info_card.pack(fill="x", padx=12, pady=(0, 4))

        self._info_row(info_card, "地址",  "127.0.0.1")
        self._divider(info_card)
        self._info_row(info_card, "端口",  "8000")
        self._divider(info_card)
        self._info_row(info_card, "协议",  "HTTP")

        # ── 操作按钮 ──
        self._section_title(sidebar, "操作")

        self.open_btn = ctk.CTkButton(
            sidebar,
            text="  打开主页",
            image=None,
            command=self._open_homepage,
            font=ctk.CTkFont(size=13),
            fg_color=COLOR_BLUE,
            hover_color="#007aff",
            text_color="#ffffff",
            corner_radius=8,
            height=38,
            anchor="center"
        )
        self.open_btn.pack(fill="x", padx=12, pady=(0, 8))

        self.db_btn = ctk.CTkButton(
            sidebar,
            text="  数据库管理工具",
            command=self._open_db_tool,
            font=ctk.CTkFont(size=13),
            fg_color=BG_TERTIARY,
            hover_color=BG_GROUPED,
            text_color=COLOR_LABEL2,
            corner_radius=8,
            height=38
        )
        self.db_btn.pack(fill="x", padx=12, pady=(0, 4))

        # ── 分割线 ──
        ctk.CTkFrame(sidebar, fg_color=COLOR_SEPARATOR, height=1).pack(
            fill="x", padx=12, pady=12
        )

        # ── 服务器控制 ──
        self._section_title(sidebar, "服务器")

        self.toggle_btn = ctk.CTkButton(
            sidebar,
            text="停止服务器",
            command=self._toggle_server,
            font=ctk.CTkFont(size=13),
            fg_color=COLOR_RED,
            hover_color="#e0362d",
            text_color="#ffffff",
            corner_radius=8,
            height=38
        )
        self.toggle_btn.pack(fill="x", padx=12, pady=(0, 8))

        ctk.CTkButton(
            sidebar,
            text="清空日志",
            command=self._clear_log,
            font=ctk.CTkFont(size=12),
            fg_color=BG_TERTIARY,
            hover_color=BG_GROUPED,
            text_color="#636366",
            corner_radius=8,
            height=32
        ).pack(fill="x", padx=12)

        # ── 分割线 ──
        ctk.CTkFrame(sidebar, fg_color=COLOR_SEPARATOR, height=1).pack(
            fill="x", padx=12, pady=12
        )

        # ── 退出服务 ──
        ctk.CTkButton(
            sidebar,
            text="退出服务",
            command=self._confirm_quit,
            font=ctk.CTkFont(size=12),
            fg_color="#3a1f1f",
            hover_color="#5a2a2a",
            text_color="#ff6b6b",
            corner_radius=8,
            height=34,
            border_width=1,
            border_color="#7a3030",
        ).pack(fill="x", padx=12)

        # ── 版本号 ──
        ctk.CTkLabel(
            sidebar,
            text="FMSA  ·  v1.0",
            font=ctk.CTkFont(size=10),
            text_color="#48484a"
        ).pack(pady=(8, 10))

    def _build_log_panel(self, parent):
        panel = ctk.CTkFrame(parent, fg_color=BG_SECONDARY, corner_radius=12)
        panel.pack(side="right", fill="both", expand=True)

        # 标题行
        header = ctk.CTkFrame(panel, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(14, 6))

        ctk.CTkLabel(
            header,
            text="运行日志",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLOR_LABEL
        ).pack(side="left")

        self.log_time_label = ctk.CTkLabel(
            header,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="#48484a"
        )
        self.log_time_label.pack(side="right")

        # 日志文本框
        self.log_text = ctk.CTkTextbox(
            panel,
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color="#141416",
            text_color="#d1d1d6",
            corner_radius=8,
            wrap="word",
            state="disabled",
            scrollbar_button_color=BG_TERTIARY,
            scrollbar_button_hover_color=BG_GROUPED,
        )
        self.log_text.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    # ── 辅助小部件 ───────────────────────────────────────────────────────────

    def _section_title(self, parent, text: str):
        ctk.CTkLabel(
            parent,
            text=text.upper(),
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#636366"
        ).pack(anchor="w", padx=16, pady=(14, 6))

    def _info_row(self, parent, label: str, value: str):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=6)
        ctk.CTkLabel(
            row, text=label,
            font=ctk.CTkFont(size=11),
            text_color="#8e8e93",
            width=40
        ).pack(side="left")
        ctk.CTkLabel(
            row, text=value,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLOR_BLUE
        ).pack(side="right")

    def _divider(self, parent):
        ctk.CTkFrame(parent, fg_color=BG_GROUPED, height=1, corner_radius=0).pack(
            fill="x", padx=8
        )

    # ══════════════════════════════════════════════════════════════════════════
    #  日志着色标签（访问底层 tk.Text）
    # ══════════════════════════════════════════════════════════════════════════

    def _configure_log_tags(self):
        tb = self.log_text._textbox
        tb.tag_configure("info",    foreground=COLOR_BLUE)
        tb.tag_configure("success", foreground=COLOR_GREEN)
        tb.tag_configure("warn",    foreground=COLOR_ORANGE)
        tb.tag_configure("error",   foreground=COLOR_RED)
        tb.tag_configure("normal",  foreground="#d1d1d6")
        tb.tag_configure("dim",     foreground="#636366")
        tb.tag_configure("url",     foreground=COLOR_BLUE)

    # ══════════════════════════════════════════════════════════════════════════
    #  窗口图标（任务栏 + 标题栏左上角）
    # ══════════════════════════════════════════════════════════════════════════

    def _setup_window_icon(self):
        """
        Win32 API 分别设置：
          ICON_SMALL (标题栏左上角) → 圆形 M
          ICON_BIG   (任务栏)       → icon_bottom.png
        """
        if not TRAY_AVAILABLE:
            return
        try:
            if sys.platform == "win32":
                self._apply_win32_icons()
            else:
                # 非 Windows 降级：iconphoto 统一使用 icon_bottom
                img = Image.open(ICON_BOTTOM).convert("RGBA") if ICON_BOTTOM.exists() \
                      else self._make_tray_icon()
                self._win_photo = ImageTk.PhotoImage(img.resize((64, 64), Image.LANCZOS))
                self.iconphoto(True, self._win_photo)
        except Exception:
            pass

    def _apply_win32_icons(self):
        """
        两步设置 Windows 图标：
          ① iconbitmap(.ico) → 最可靠地写入标题栏左上角（ICON_SMALL，圆形 M）
          ② WM_SETICON ICON_BIG → 覆盖任务栏图标（icon_bottom.png）
        """
        import ctypes
        import tempfile

        WM_SETICON = 0x0080
        ICON_BIG   = 1

        def save_ico(img: "Image.Image", sizes: list[int]) -> str:
            """将 PIL Image 保存为多尺寸 .ico 临时文件，返回路径"""
            tmp = tempfile.NamedTemporaryFile(suffix=".ico", delete=False)
            path = tmp.name
            tmp.close()
            img.save(path, format="ICO",
                     sizes=[(s, s) for s in sizes])
            return path

        def load_hicon(path: str, size: int) -> int:
            hicon = ctypes.windll.user32.LoadImageW(
                None, path, 1, size, size, 0x00000010  # IMAGE_ICON | LR_LOADFROMFILE
            )
            try:
                os.unlink(path)
            except OSError:
                pass
            return hicon

        # ── ① 标题栏：iconbitmap 写入圆形 M ──────────────────────────────
        m_img   = self._make_tray_icon()
        m_path  = save_ico(m_img, [16, 32, 48])
        try:
            self.iconbitmap(m_path)
        finally:
            try:
                os.unlink(m_path)
            except OSError:
                pass

        # ── ② 任务栏：WM_SETICON ICON_BIG 覆盖为 icon_bottom.png ────────
        bottom_src = (Image.open(ICON_BOTTOM).convert("RGBA")
                      if ICON_BOTTOM.exists() else m_img)
        big_path  = save_ico(bottom_src, [48, 256])
        big_hicon = load_hicon(big_path, 48)

        if big_hicon:
            # FindWindowW 按标题找句柄，最可靠
            hwnd = ctypes.windll.user32.FindWindowW(None, self.title())
            if not hwnd:
                hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            if not hwnd:
                hwnd = self.winfo_id()
            if hwnd:
                ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, big_hicon)

    # ══════════════════════════════════════════════════════════════════════════
    #  系统托盘
    # ══════════════════════════════════════════════════════════════════════════

    def _setup_tray(self):
        if not TRAY_AVAILABLE:
            return

        icon_img = self._make_tray_icon()

        menu = pystray.Menu(
            pystray.MenuItem(
                "显示窗口",
                lambda icon, item: self._show_window(),
                default=True       # 双击触发此项
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "进入主页",
                lambda icon, item: self._open_homepage()
            ),
            pystray.MenuItem(
                "启动数据库管理工具",
                lambda icon, item: self._open_db_tool()
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "退出服务",
                lambda icon, item: self._quit_app()
            ),
        )

        self.tray_icon = pystray.Icon(
            "FMSA",
            icon_img,
            "FMSA 基于航班计划的气象监视告警系统",
            menu
        )

    def _make_tray_icon(self) -> "Image.Image":
        """生成托盘图标（蓝色圆底 + 白色 M 字）"""
        size = 64
        img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d    = ImageDraw.Draw(img)

        # 深色圆形背景
        d.ellipse([1, 1, size - 1, size - 1], fill=(28, 28, 30, 255))
        # 蓝色内圆
        d.ellipse([6, 6, size - 6, size - 6], fill=(10, 132, 255, 255))

        # 白色 "M"（三条矩形拼合）
        lx, rx, top, bot = 14, 50, 16, 48
        mid_y = top + (bot - top) // 2
        d.rectangle([lx,      top, lx + 7,  bot],  fill=(255, 255, 255, 255))
        d.rectangle([rx - 7,  top, rx,      bot],  fill=(255, 255, 255, 255))
        d.polygon(
            [(lx, top), (size // 2, mid_y), (rx, top),
             (rx, top + 8), (size // 2, mid_y + 8), (lx, top + 8)],
            fill=(255, 255, 255, 255)
        )
        return img

    # ══════════════════════════════════════════════════════════════════════════
    #  服务器管理
    # ══════════════════════════════════════════════════════════════════════════

    def _start_server(self):
        if self.server_running:
            return

        # ── 检测 8000 端口是否已有服务在运行 ──────────────────────────────
        if is_port_in_use(DJANGO_PORT):
            self._log(f"检测到端口 {DJANGO_PORT} 已有服务在运行，直接接管。", "warn")
            self._log(f"服务已就绪 → {HOME_URL}", "success")
            self.server_running = True
            self._attached = True
            self.after(0, self._on_server_attached)
            return

        self._log("正在启动 Django 服务器…", "info")

        def _run():
            try:
                flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                env = os.environ.copy()
                # 强制子进程（Django）使用 UTF-8 I/O，避免 Windows 中文系统 GBK 乱码
                env["PYTHONUTF8"]      = "1"
                env["PYTHONIOENCODING"] = "utf-8"
                self.server_process = subprocess.Popen(
                    [sys.executable, str(MANAGE_PY), "runserver", "127.0.0.1:8000"],
                    cwd=str(DJANGO_DIR),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=env,
                    creationflags=flags,
                )
                self.server_running = True
                self.after(0, self._on_server_started)

                for line in self.server_process.stdout:
                    stripped = line.rstrip()
                    if stripped:
                        self.log_queue.put(("raw", stripped))

                self.server_process.wait()
                self.server_running = False
                if not self._quitting:
                    self.after(0, self._on_server_stopped)

            except Exception as exc:
                self.log_queue.put(("styled", f"启动失败：{exc}", "error"))
                self.server_running = False
                self.after(0, self._on_server_stopped)

        threading.Thread(target=_run, daemon=True).start()

    def _stop_server(self):
        if self.server_process and self.server_running:
            self._log("正在停止服务器…", "warn")
            pid = self.server_process.pid
            try:
                if sys.platform == "win32":
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(pid)],
                        creationflags=subprocess.CREATE_NO_WINDOW,
                        capture_output=True,
                    )
                else:
                    import signal as _sig
                    os.killpg(os.getpgid(pid), _sig.SIGTERM)
            except Exception as exc:
                self._log(f"强制终止时出错：{exc}", "warn")
            finally:
                try:
                    self.server_process.wait(timeout=3)
                except Exception:
                    pass
            self.server_process = None
            self.server_running = False
            self._on_server_stopped()

    def _kill_port_listeners(self) -> int:
        """
        扫描并强制终止所有正在监听 DJANGO_PORT 的进程（含外部启动的 Django）。
        返回被终止的进程数。
        """
        if sys.platform != "win32":
            return 0
        try:
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True, text=True, encoding="gbk", errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            pids: set[str] = set()
            for line in result.stdout.splitlines():
                # 匹配形如 "  TCP  0.0.0.0:8000  ...  LISTENING  1234"
                if f":{DJANGO_PORT}" in line and "LISTENING" in line:
                    parts = line.split()
                    if parts:
                        pids.add(parts[-1])

            for pid in pids:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", pid],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    capture_output=True,
                )
            return len(pids)
        except Exception:
            return 0

    def _toggle_server(self):
        if self.server_running:
            if self._attached:
                # 接管模式下"停止"无意义，给用户提示
                self._log("当前为接管外部服务，无法通过此控制台停止。", "warn")
            else:
                self._stop_server()
        else:
            self._start_server()

    def _on_server_attached(self):
        """接管外部已有服务时的 UI 状态"""
        self.status_dot.configure(text_color=COLOR_ORANGE)
        self.status_label.configure(text="已接管", text_color=COLOR_ORANGE)
        self.toggle_btn.configure(
            text="外部服务（接管）",
            fg_color=BG_TERTIARY,
            hover_color=BG_GROUPED,
            text_color=COLOR_ORANGE,
        )

    def _on_server_started(self):
        self.status_dot.configure(text_color=COLOR_GREEN)
        self.status_label.configure(text="运行中", text_color=COLOR_GREEN)
        self.toggle_btn.configure(
            text="停止服务器",
            fg_color=COLOR_RED,
            hover_color="#e0362d"
        )
        self._log(f"服务器已启动 → {HOME_URL}", "success")

    def _on_server_stopped(self):
        self.status_dot.configure(text_color=COLOR_RED)
        self.status_label.configure(text="已停止", text_color="#636366")
        self.toggle_btn.configure(
            text="启动服务器",
            fg_color=COLOR_GREEN,
            hover_color="#27a846"
        )
        self._log("服务器已停止", "warn")

    # ══════════════════════════════════════════════════════════════════════════
    #  操作回调
    # ══════════════════════════════════════════════════════════════════════════

    def _open_homepage(self):
        webbrowser.open(HOME_URL)
        self._log(f"已在浏览器打开主页：{HOME_URL}", "info")

    def _open_db_tool(self):
        if not DB_TOOL.exists():
            self._log(f"找不到数据库管理工具：{DB_TOOL}", "error")
            return
        try:
            # 数据库工具是 Tkinter GUI，不需要 CREATE_NO_WINDOW
            subprocess.Popen(
                [sys.executable, str(DB_TOOL)],
                cwd=str(DB_TOOL.parent),
            )
            self._log("数据库管理工具已启动", "info")
        except Exception as exc:
            self._log(f"启动数据库管理工具失败：{exc}", "error")

    # ══════════════════════════════════════════════════════════════════════════
    #  日志系统
    # ══════════════════════════════════════════════════════════════════════════

    def _log(self, msg: str, level: str = "normal"):
        """主线程或子线程均可调用"""
        self.log_queue.put(("styled", msg, level))

    def _poll_logs(self):
        try:
            while True:
                item = self.log_queue.get_nowait()
                self._write_log(item)
        except queue.Empty:
            pass
        self.after(80, self._poll_logs)

    def _write_log(self, item):
        tb = self.log_text._textbox
        tb.configure(state="normal")

        now = datetime.now().strftime("%H:%M:%S")

        if item[0] == "styled":
            _, msg, level = item
            prefix_map = {
                "info":    "ℹ",
                "success": "✓",
                "warn":    "⚠",
                "error":   "✕",
                "normal":  "·",
            }
            prefix = prefix_map.get(level, "·")
            tb.insert("end", f"{now}  ", "dim")
            tb.insert("end", f"{prefix} ", level)
            tb.insert("end", msg + "\n", level)

        else:  # "raw" — Django stdout
            _, text = item
            # 高亮关键词
            if "Error" in text or "error" in text or "Exception" in text:
                tb.insert("end", f"{now}  ", "dim")
                tb.insert("end", text + "\n", "error")
            elif "WARNING" in text or "Warning" in text:
                tb.insert("end", f"{now}  ", "dim")
                tb.insert("end", text + "\n", "warn")
            elif "Starting" in text or "Quit" in text or "Watching" in text:
                tb.insert("end", f"{now}  ", "dim")
                tb.insert("end", text + "\n", "success")
            else:
                tb.insert("end", f"{now}  ", "dim")
                tb.insert("end", text + "\n", "normal")

        tb.configure(state="disabled")
        tb.see("end")

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_time_label.configure(text=f"最后更新 {ts}")

    def _clear_log(self):
        tb = self.log_text._textbox
        tb.configure(state="normal")
        tb.delete("1.0", "end")
        tb.configure(state="disabled")
        self._log("日志已清空", "dim")

    # ══════════════════════════════════════════════════════════════════════════
    #  窗口 / 托盘 / 退出
    # ══════════════════════════════════════════════════════════════════════════

    def _on_close(self):
        """点击关闭按钮 → 最小化到托盘（托盘图标已常驻，直接隐藏窗口即可）"""
        if TRAY_AVAILABLE and self.tray_icon:
            self.withdraw()
        else:
            self._quit_app()

    def _show_window(self):
        """从托盘恢复窗口（可在非主线程调用）"""
        self.after(0, self._do_show_window)

    def _do_show_window(self):
        self.deiconify()
        self.state("normal")
        self.lift()
        self.focus_force()

    def _confirm_quit(self):
        """弹出深色确认弹窗，确认后才退出"""
        ConfirmDialog(
            parent=self,
            title="退出确认",
            message="确定要退出 FMSA 服务端吗？\n\n退出后 Django 服务器将同时停止，\n前端页面将无法访问。",
            on_confirm=self._quit_app,
        )

    def _quit_app(self):
        self._quitting = True
        # 先停我们自己启动的进程
        if not self._attached:
            self._stop_server()
        # 再扫描端口，清理一切残留（含接管模式的外部 Django、重载后 PID 变化的子进程）
        killed = self._kill_port_listeners()
        if killed:
            self._log(f"已清理 {killed} 个残留 Django 进程", "warn")
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        try:
            self._ipc_sock.close()
        except Exception:
            pass
        try:
            self.quit()
            self.destroy()
        except Exception:
            pass
        sys.exit(0)

    # ══════════════════════════════════════════════════════════════════════════
    #  IPC 监听（接收其他实例的 SHOW 信号）
    # ══════════════════════════════════════════════════════════════════════════

    def _ipc_listener(self):
        while not self._quitting:
            try:
                self._ipc_sock.settimeout(1.0)
                conn, _ = self._ipc_sock.accept()
                try:
                    data = conn.recv(16)
                    if data == b"SHOW":
                        self._show_window()
                finally:
                    conn.close()
            except socket.timeout:
                continue
            except Exception:
                break


# ══════════════════════════════════════════════════════════════════════════════
#  深色确认弹窗
# ══════════════════════════════════════════════════════════════════════════════

class ConfirmDialog(ctk.CTkToplevel):
    """深色 macOS 风格确认对话框"""

    def __init__(self, parent: ctk.CTk, title: str, message: str,
                 on_confirm, on_cancel=None):
        super().__init__(parent)
        self._on_confirm = on_confirm
        self._on_cancel  = on_cancel

        self.title(title)
        self.resizable(False, False)
        self.configure(fg_color=BG_SECONDARY)
        self.grab_set()          # 模态
        self.lift()
        self.focus_force()

        # 居中于父窗口
        self.after(10, lambda: self._center(parent))

        # ── 内容 ──
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(padx=28, pady=(24, 16))

        # 警告图标
        ctk.CTkLabel(
            content, text="⚠",
            font=ctk.CTkFont(size=36),
            text_color=COLOR_ORANGE
        ).pack()

        ctk.CTkLabel(
            content, text=title,
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=COLOR_LABEL
        ).pack(pady=(8, 0))

        ctk.CTkLabel(
            content, text=message,
            font=ctk.CTkFont(size=12),
            text_color="#8e8e93",
            justify="center",
            wraplength=280
        ).pack(pady=(8, 4))

        # ── 按钮行 ──
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=24, pady=(0, 20))

        ctk.CTkButton(
            btn_row, text="取消",
            command=self._cancel,
            font=ctk.CTkFont(size=13),
            fg_color=BG_TERTIARY,
            hover_color=BG_GROUPED,
            text_color=COLOR_LABEL2,
            corner_radius=8,
            height=36,
            width=120
        ).pack(side="left", expand=True, padx=(0, 6))

        ctk.CTkButton(
            btn_row, text="确认退出",
            command=self._confirm,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=COLOR_RED,
            hover_color="#e0362d",
            text_color="#ffffff",
            corner_radius=8,
            height=36,
            width=120
        ).pack(side="right", expand=True, padx=(6, 0))

        self.protocol("WM_DELETE_WINDOW", self._cancel)

    def _center(self, parent: ctk.CTk):
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        dw = self.winfo_width()
        dh = self.winfo_height()
        x  = px + (pw - dw) // 2
        y  = py + (ph - dh) // 2
        self.geometry(f"+{x}+{y}")

    def _confirm(self):
        self.destroy()
        if self._on_confirm:
            self._on_confirm()

    def _cancel(self):
        self.destroy()
        if self._on_cancel:
            self._on_cancel()


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ipc_sock = acquire_single_instance()
    if ipc_sock is None:
        # 已有实例在运行，SHOW 信号已发送，直接退出
        sys.exit(0)

    app = MTWSServerGUI(ipc_sock)
    app.mainloop()
