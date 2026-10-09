"""FMSA 托盘常驻管家：单实例，接管已有后端，多余杀到只剩一个。
托盘菜单: 显示窗口 / 打开主页 / 重启后端 / 完全退出(含杀后端)。
前端 X 只关窗口不杀后端；完全退出才清 8000+splash。
"""
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
TOOLS = BASE / "tools"
DJANGO_DIR = BASE / "mtws_django"
HOME = "http://127.0.0.1:8000/current/"
HEALTH = "http://127.0.0.1:8000/static/js/echarts.min.js"
SPLASH = TOOLS / "fmsa_splash_server.py"
SPLASH_URL = "http://127.0.0.1:18001/"
SPLASH_HEALTH = "http://127.0.0.1:18001/healthz"
DJANGO_PORT = 8000
SPLASH_PORT = 18001
IPC = 19531

try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_OK = True
except ImportError:
    TRAY_OK = False


LOG_DIR = BASE / "logs"
LOG_FILE = LOG_DIR / "fmsa_tray.log"
LOG_MAX = 512 * 1024  # 512KB 轮转

def _rotate():
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > LOG_MAX:
            bak = LOG_DIR / "fmsa_tray.log.1"
            try:
                if bak.exists():
                    bak.unlink()
            except Exception:
                pass
            LOG_FILE.rename(bak)
    except Exception:
        pass

def log(msg):
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        _rotate()
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except Exception:
        pass


def http_ok(url, timeout=2):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status in (200, 302)
    except Exception:
        return False


def django_alive():
    # /current/ 要登录态，未登录会 302 到登录页，同样算活；只判 HTTP 可达
    try:
        with urllib.request.urlopen(HOME, timeout=2) as r:
            home_ok = r.status in (200, 302)
    except Exception:
        return False
    return home_ok and http_ok(HEALTH)


def pids_on_port(port):
    found = set()
    try:
        r = subprocess.run(["netstat", "-ano"], capture_output=True, text=True,
                           encoding="gbk", errors="replace",
                           creationflags=subprocess.CREATE_NO_WINDOW)
        for line in r.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                p = line.split()
                if p and p[-1].isdigit() and p[-1] != "0":
                    found.add(p[-1])
    except Exception as e:
        log(f"pids_on_port fail {e}")
    return found


def proc_name(pid):
    try:
        r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                           capture_output=True, text=True,
                           encoding="gbk", errors="replace",
                           creationflags=subprocess.CREATE_NO_WINDOW)
        for line in r.stdout.splitlines():
            if line.startswith('"'):
                return line.split('","')[0].strip('"').lower()
    except Exception:
        pass
    return ""


def kill_pids(pids):
    for pid in pids:
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                           creationflags=subprocess.CREATE_NO_WINDOW,
                           capture_output=True)
            log(f"killed {pid}")
        except Exception as e:
            log(f"kill {pid} fail {e}")


def dedup_port(port, keep_one=True):
    """同一端口多个 LISTENING 只留一个，其余杀掉。返回剩余 PID。"""
    pids = sorted(pids_on_port(port))
    if len(pids) <= 1:
        return pids
    log(f"port {port} holders {pids}, dedup")
    kill = pids[:-1] if keep_one else pids
    kill_pids(kill)
    time.sleep(1.5)
    return sorted(pids_on_port(port))


def find_browser():
    import shutil
    for name in ("chrome.exe", "msedge.exe"):
        p = shutil.which(name)
        if p:
            return p
    for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
        if os.path.exists(p):
            return p
    return None


class Manager:
    def __init__(self):
        self.tray = None
        self.profile = os.path.expandvars(r"%LOCALAPPDATA%\fmsa-app")
        os.makedirs(self.profile, exist_ok=True)

    def start_splash(self):
        if http_ok(SPLASH_HEALTH):
            return True
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        pyw = sys.executable
        if pyw.lower().endswith("python.exe"):
            cand = pyw[:-len("python.exe")] + "pythonw.exe"
            if os.path.exists(cand):
                pyw = cand
        log(f"start splash with {pyw}")
        try:
            subprocess.Popen(
                [pyw, str(SPLASH)],
                cwd=str(BASE), env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception as e:
            log(f"splash popen fail {e}")
            return False
        for _ in range(17):
            if http_ok(SPLASH_HEALTH):
                log("splash up")
                return True
            time.sleep(0.3)
        log("splash start timeout")
        return False

    def ensure_backend(self):
        """有就接管并去重；没有或接管失败就杀干净重建。返回 True=可用。"""
        if django_alive():
            left = dedup_port(DJANGO_PORT)
            log(f"reuse backend, holders={left}")
            if django_alive():
                return True
            log("reuse probe failed after dedup, rebuild")
        # 重建：清 8000 python 残留再起
        for pid in pids_on_port(DJANGO_PORT):
            if proc_name(pid) in ("python.exe", "pythonw.exe"):
                kill_pids([pid])
        time.sleep(1.5)
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        pyw = sys.executable
        if pyw.lower().endswith("python.exe"):
            cand = pyw[:-len("python.exe")] + "pythonw.exe"
            if os.path.exists(cand):
                pyw = cand
        log(f"start django with {pyw}")
        try:
            subprocess.Popen(
                [pyw, "manage.py", "runserver", f"127.0.0.1:{DJANGO_PORT}"],
                cwd=str(DJANGO_DIR), env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception as e:
            log(f"django popen fail {e}")
            return False
        ok = 0
        for _ in range(120):
            if django_alive():
                ok += 1
                if ok >= 2:
                    log("backend rebuilt ok")
                    return True
            else:
                ok = 0
            time.sleep(0.5)
        log("backend rebuild timeout")
        return False

    def open_window(self, url, small=False):
        self._focus_or_open(url, small)

    def _focus_or_open(self, url, small=False):
        """已有同 URL 的 --app 窗口则顶到最前，否则新开。"""
        import ctypes
        user32 = ctypes.windll.user32
        found = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def _cb(hwnd, _):
            try:
                if not user32.IsWindowVisible(hwnd):
                    return True
                length = user32.GetWindowTextLengthW(hwnd)
                if length <= 0 or length > 256:
                    return True
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value or ""
                if ("FMSA" in title) or ("18001" in title) or ("8000" in title) or ("current" in title):
                    pid = ctypes.c_ulong(0)
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    name = proc_name(str(pid.value)).lower()
                    if "chrome" in name or "msedge" in name or "edge" in name:
                        found.append(int(hwnd))
            except Exception:
                pass
            return True

        try:
            user32.EnumWindows(_cb, 0)
        except Exception as e:
            log(f"enum windows fail {e}")
        for hwnd in found:
            try:
                SW_RESTORE, SW_SHOW = 9, 5
                HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
                SWP_NOMOVE, SWP_NOSIZE, SWP_SHOW = 0x2, 0x1, 0x40
                kernel32 = ctypes.windll.kernel32
                try:
                    fg = user32.GetForegroundWindow()
                    cur_tid = kernel32.GetCurrentThreadId()
                    fg_tid = user32.GetWindowThreadProcessId(fg, None)
                    user32.AttachThreadInput(cur_tid, fg_tid, True)
                    attached = True
                except Exception:
                    attached = False
                try:
                    if user32.IsIconic(hwnd):
                        user32.ShowWindow(hwnd, SW_RESTORE)
                    else:
                        user32.ShowWindow(hwnd, SW_SHOW)
                    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                                        SWP_NOMOVE | SWP_NOSIZE | SWP_SHOW)
                    user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0,
                                        SWP_NOMOVE | SWP_NOSIZE | SWP_SHOW)
                    user32.SetForegroundWindow(hwnd)
                    user32.BringWindowToTop(hwnd)
                    user32.SetActiveWindow(hwnd)
                finally:
                    try:
                        if attached:
                            user32.AttachThreadInput(cur_tid, fg_tid, False)
                    except Exception:
                        pass
                log(f"focused existing window {hwnd}")
                return
            except Exception as e:
                log(f"focus {hwnd} fail {e}")
        b = find_browser()
        if not b:
            import webbrowser
            webbrowser.open(url)
            return
        args = [b, f"--app={url}", f"--user-data-dir={self.profile}",
                "--no-default-browser-check", "--no-first-run"]
        args.append("--window-size=680,600" if small else "--start-maximized")
        subprocess.Popen(args)
        log(f"opened new window {url}")

    def flow(self):
        # splash 去重：多个只留一个
        try:
            left = dedup_port(SPLASH_PORT)
            if not left or not http_ok(SPLASH_HEALTH):
                for pid in pids_on_port(SPLASH_PORT):
                    kill_pids([pid])
                time.sleep(1)
                ok = self.start_splash()
                log(f"splash start -> {ok}")
        except Exception as e:
            log(f"flow splash fail {e}")
        try:
            self.open_window(SPLASH_URL, small=True)
            log("splash window opened (single window, splash will redirect to HOME itself)")
        except Exception as e:
            log(f"open splash fail {e}")
        try:
            ok = self.ensure_backend()
            log(f"backend ensure -> {ok}")
            # 不再另开第二个主页窗口：由 splash 页 finish() 同窗跳转，避免双页
            if not ok:
                log("backend failed, splash stays for manual entry")
        except Exception as e:
            log(f"flow backend fail {e}")
        self.ensure_tray()

    # ---- tray ----
    def _img(self):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse([1, 1, 63, 63], fill=(16, 24, 40, 255))
        d.ellipse([6, 6, 58, 58], fill=(14, 74, 138, 255))
        d.text((22, 14), "F", fill=(255, 255, 255, 255))
        return img

    def ensure_tray(self):
        if not TRAY_OK or self.tray is not None:
            return
        menu = pystray.Menu(
            pystray.MenuItem("显示窗口", lambda i, x: self.open_window(HOME), default=True),
            pystray.MenuItem("打开主页", lambda i, x: self.open_window(HOME)),
            pystray.MenuItem("重启后端", lambda i, x: threading.Thread(
                target=self.ensure_backend, daemon=True).start()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("完全退出(含杀后端)", lambda i, x: self.quit_all()),
        )
        self.tray = pystray.Icon("FMSA", self._img(), "FMSA", menu)
        threading.Thread(target=self.tray.run, daemon=True).start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass

    def quit_all(self):
        kill_pids(pids_on_port(DJANGO_PORT))
        kill_pids(pids_on_port(SPLASH_PORT))
        try:
            if self.tray:
                self.tray.stop()
        except Exception:
            pass
        os._exit(0)


def acquire():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", IPC))
        s.listen(5)
        return s
    except OSError:
        pass
    try:
        c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        c.settimeout(2)
        c.connect(("127.0.0.1", IPC))
        c.sendall(b"SHOW")
        c.close()
        log("SHOW sent to running manager")
    except Exception as e:
        log(f"SHOW fail {e}, cleanup stale IPC holder")
        for pid in pids_on_port(IPC):
            kill_pids([pid])
        time.sleep(2)
        s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s2.bind(("127.0.0.1", IPC))
            s2.listen(5)
            return s2
        except OSError:
            return None
    return None


if __name__ == "__main__":
    log("=== manager start ===")
    s = acquire()
    if s is None:
        sys.exit(0)
    m = Manager()
    threading.Thread(target=m.flow, daemon=True).start()

    def ipc_loop():
        while True:
            try:
                s.settimeout(1.0)
                conn, _ = s.accept()
                try:
                    if conn.recv(16) == b"SHOW":
                        m.open_window(HOME)
                finally:
                    conn.close()
            except socket.timeout:
                continue
            except Exception:
                break
    threading.Thread(target=ipc_loop, daemon=True).start()
    m.ensure_tray()
