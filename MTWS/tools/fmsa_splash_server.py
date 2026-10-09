"""FMSA Splash Server (Flight-Schedule-Based Meteorological Surveillance Alert System)
标准库 http.server，无第三方依赖。路由: / splash页, /healthz, /__ready 后端探针, /exit 自杀。
端口被占直接退出（天然单实例）。
"""
import json
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HOST = "127.0.0.1"
PORT = 18001
DJANGO_HOME = "http://127.0.0.1:8000/current/"
DJANGO_STATIC = "http://127.0.0.1:8000/static/js/echarts.min.js"
BASE = Path(__file__).parent
HTML_FILE = BASE / "fmsa_splash.html"

BRAND_EN = "Flight-Schedule-Based Meteorological Surveillance Alert System"
BRAND_SHORT = "FMSA"


def _probe(url, timeout=2):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status in (200, 302)
    except Exception:
        return False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/exit"):
            self._send(200, "bye", "text/plain")
            threading.Timer(0.1, lambda: sys.exit(0)).start()
            return
        if self.path.startswith("/healthz"):
            self._send(200, json.dumps({"ok": True}), "application/json")
            return
        if self.path.startswith("/__ready"):
            ok_home = _probe(DJANGO_HOME)
            ok_static = _probe(DJANGO_STATIC)
            self._send(200, json.dumps({"home": ok_home, "static": ok_static,
                                        "ready": ok_home and ok_static}),
                       "application/json")
            return
        try:
            html = HTML_FILE.read_text(encoding="utf-8")
        except Exception as e:
            self._send(500, f"splash html missing: {e}", "text/plain")
            return
        self._send(200, html)


if __name__ == "__main__":
    try:
        srv = HTTPServer((HOST, PORT), Handler)
    except OSError:
        sys.exit(0)
    print(f"FMSA splash on {HOST}:{PORT}", flush=True)
    srv.serve_forever()
