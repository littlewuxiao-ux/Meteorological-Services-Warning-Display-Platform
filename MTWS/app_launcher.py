"""MTWS App 单窗口启动器：同一框体内先显示加载页，就绪后直接切主页。"""
import socket, subprocess, sys, threading, time, os, traceback, urllib.request
from pathlib import Path

def _log_err(text):
    try:
        with (Path(__file__).parent / "app_launcher_error.log").open("a", encoding="utf-8") as f:
            f.write(text + "\n")
            f.flush()
    except Exception:
        pass

def _excepthook(t, v, tb):
    _log_err("UNCAUGHT:\n" + "".join(traceback.format_exception(t, v, tb)))

sys.excepthook = _excepthook
_log_err(f"START py={sys.version.split()[0]} exe={sys.executable}")

try:
    import webview
except Exception:
    _log_err(traceback.format_exc())
    try:
        import tkinter.messagebox as _mb
        import tkinter as _tk
        _r = _tk.Tk(); _r.withdraw()
        _mb.showerror("MTWS", "缺少 pywebview，请先运行 安装依赖.bat\n(app_launcher_error.log 已记录详情)")
    except Exception:
        pass
    raise

SCRIPT_DIR = Path(__file__).parent
DJANGO_DIR = SCRIPT_DIR / "mtws_django"
MANAGE_PY = DJANGO_DIR / "manage.py"
HOME_URL = "http://127.0.0.1:8000/current/"
PORT = 8000
IPC = 19529

LOADING_HTML = """<html><head><meta charset="utf-8"><style>
*{margin:0;box-sizing:border-box}body{background:#1c1c1e;color:#fff;font-family:"Microsoft YaHei",sans-serif;display:flex;align-items:center;justify-content:center;height:100vh}
.card{background:#2c2c2e;border-radius:20px;width:460px;padding:40px;text-align:center;box-shadow:0 20px 60px rgba(0,0,0,.5)}
.logo{width:84px;height:84px;background:linear-gradient(135deg,#0a84ff,#0055ff);border-radius:20px;margin:0 auto 16px;font-size:46px;line-height:84px;box-shadow:0 8px 24px rgba(10,132,255,.4)}
h1{font-size:19px;margin-bottom:6px}p.sub{color:#8e8e93;font-size:12px;margin-bottom:20px}
.bar{height:10px;background:#3a3a3c;border-radius:6px;overflow:hidden}.fill{height:100%;width:5%;background:linear-gradient(90deg,#0a84ff,#30d158);border-radius:6px;transition:width .3s}
.tip{margin-top:12px;font-size:13px;color:#ebebf5}.pct{color:#636366;font-size:11px;margin-top:4px}
.spin{margin:18px auto 0;width:26px;height:26px;border:3px solid #3a3a3c;border-top-color:#0a84ff;border-radius:50%;animation:sp 0.8s linear infinite}@keyframes sp{to{transform:rotate(360deg)}}
</style></head><body><div class="card"><div class="logo">&#9992;</div><h1>MTWS 航空气象监控系统</h1><p class="sub">App 模式启动中…</p><div class="bar"><div class="fill" id="f"></div></div><div class="tip" id="t">正在初始化…</div><div class="pct" id="p">5%</div><div class="spin"></div></div>
<script>function setP(v,t){document.getElementById('f').style.width=v+'%';document.getElementById('p').innerText=v+'%';document.getElementById('t').innerText=t;}</script></body></html>"""

def port_in_use():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", PORT)) == 0

proc, own = None, False

def _pids_on_port(port):
    """查占用指定端口 LISTENING 的 PID 列表（Windows）。"""
    found = set()
    try:
        import subprocess as _sp
        r = _sp.run(["netstat", "-ano"], capture_output=True, text=True,
                    encoding="gbk", errors="replace",
                    creationflags=getattr(_sp, "CREATE_NO_WINDOW", 0))
        for line in r.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                if parts and parts[-1].isdigit():
                    found.add(parts[-1])
    except Exception as e:
        _log_err(f"pids_on_port fail: {e}")
    return found

def _kill_pids(pids):
    import subprocess as _sp
    for pid in pids:
        try:
            _sp.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                    creationflags=getattr(_sp, "CREATE_NO_WINDOW", 0),
                    capture_output=True)
            _log_err(f"killed stale pid {pid}")
        except Exception as e:
            _log_err(f"kill {pid} fail: {e}")

def _acquire_ipc():
    """返回 socket；已唤出存量实例则返回 None（调用方直接退出）。"""
    import socket as _sk, time as _t
    s = _sk.socket(_sk.AF_INET, _sk.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", IPC))
        s.listen(5)
        return s
    except OSError:
        pass
    # 先尝试唤出存量实例
    try:
        c = _sk.socket(_sk.AF_INET, _sk.SOCK_STREAM)
        c.settimeout(2)
        c.connect(("127.0.0.1", IPC))
        c.sendall(b"SHOW")
        c.close()
        _log_err("SHOW sent, exit")
        return None
    except Exception as e:
        _log_err(f"SHOW send fail (stale?): {e}")
    # 发不过去 = 僵尸占用，自动清理后重试一次
    pids = _pids_on_port(IPC)
    if pids:
        _log_err(f"stale holder pids={pids}, killing")
        _kill_pids(pids)
        _t.sleep(2)
        s2 = _sk.socket(_sk.AF_INET, _sk.SOCK_STREAM)
        try:
            s2.bind(("127.0.0.1", IPC))
            s2.listen(5)
            _log_err("rebind ok after cleanup")
            return s2
        except OSError as e2:
            _log_err(f"rebind fail: {e2}")
    try:
        import tkinter.messagebox as _mb2
        import tkinter as _tk2
        _r2 = _tk2.Tk(); _r2.withdraw()
        _mb2.showerror("MTWS", "检测到残留进程并已尝试清理，但端口仍被占用。\n请重启电脑后重试。")
    except Exception:
        pass
    return None


def ensure_backend(window):
    global proc, own
    def js(v, t):
        try: window.evaluate_js(f"setP({int(v)},'{t}')")
        except Exception: pass
    js(10, "正在检查端口")
    if port_in_use():
        js(60, "发现已有服务，直接进入")
    else:
        js(30, "正在拉起 Django 服务")
        env = os.environ.copy(); env["PYTHONUTF8"] = "1"; env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.Popen([sys.executable, str(MANAGE_PY), "runserver", f"127.0.0.1:{PORT}"],
            cwd=str(DJANGO_DIR), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        own = True
    ok = 0
    for i in range(120):
        try:
            with urllib.request.urlopen(HOME_URL, timeout=2) as r:
                if r.status in (200, 302):
                    ok += 1
                    if ok >= 2:
                        js(100, "启动完成"); time.sleep(0.4)
                        window.load_url(HOME_URL); return
                else: ok = 0
        except Exception: ok = 0
        js(min(30 + i * 0.55, 97), "正在等待主页就绪")
        time.sleep(0.5)
    js(100, "主页响应超时，请检查后端日志")

def on_closed():
    if own and proc and proc.poll() is None:
        try: subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            creationflags=subprocess.CREATE_NO_WINDOW, capture_output=True)
        except Exception: pass

_tray = {"icon": None}

def _tray_image():
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse([1, 1, 63, 63], fill=(28, 28, 30, 255))
        d.ellipse([6, 6, 58, 58], fill=(10, 132, 255, 255))
        d.text((22, 14), "M", fill=(255, 255, 255, 255))
        return img
    except Exception:
        return None

def _ensure_tray(window):
    try:
        import pystray
        if _tray["icon"] is not None:
            return
        img = _tray_image()
        if img is None:
            return
        menu = pystray.Menu(
            pystray.MenuItem("显示窗口", lambda i, x: _show_window(window), default=True),
            pystray.MenuItem("打开主页", lambda i, x: window.load_url(HOME_URL)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", lambda i, x: _quit_all(window)),
        )
        icon = pystray.Icon("MTWS-App", img, "MTWS", menu)
        _tray["icon"] = icon
        threading.Thread(target=icon.run, daemon=True).start()
    except Exception as e:
        _log_err(f"tray fail: {e}")

def _show_window(window):
    try:
        window.show()
        try: window.restore()
        except Exception: pass
        try: window.bring_to_front()
        except Exception: pass
    except Exception as e:
        _log_err(f"show fail: {e}")

def _quit_all(window):
    try:
        ic = _tray["icon"]
        if ic:
            try: ic.stop()
            except Exception: pass
        _tray["icon"] = None
    except Exception:
        pass
    on_closed()
    try: window.destroy()
    except Exception: pass
    os._exit(0)

def _on_closing(window):
    # 点 X 进入托盘而非退出
    try:
        window.hide()
    except Exception:
        pass
    _ensure_tray(window)
    return False

def _ipc_listener(sock, window):
    _ensure_tray(window)
    while True:
        try:
            sock.settimeout(1.0)
            conn, _ = sock.accept()
            try:
                data = conn.recv(16)
                if data == b"SHOW":
                    _log_err("IPC SHOW -> bring to front")
                    _show_window(window)
            finally:
                conn.close()
        except socket.timeout:
            continue
        except Exception as e:
            _log_err(f"ipc listen err: {e}")
            break

if __name__ == "__main__":
    try:
        _log_err("MAIN enter")
        import webview as _wv_check
        _log_err(f"webview import ok: {_wv_check.__file__ if hasattr(_wv_check, '__file__') else 'ok'}")
        s = _acquire_ipc()
        if s is None:
            sys.exit(0)
        win = webview.create_window("MTWS", html=LOADING_HTML, width=1600, height=900)
        win.events.closed += on_closed
        win.events.closing += lambda: _on_closing(win)
        threading.Thread(target=_ipc_listener, args=(s, win), daemon=True).start()
        threading.Thread(target=ensure_backend, args=(win,), daemon=True).start()
        _log_err("webview.start enter")
        webview.start()
        _log_err("webview.start exit")
    except BaseException:
        _log_err(traceback.format_exc())
        raise
