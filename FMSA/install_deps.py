# -*- coding: utf-8 -*-
"""Install FMSA dependencies. Double-click 安装依赖.bat to run this."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REQ = ROOT / "requirements_production.txt"
LOG = ROOT / "logs" / "install.log"
SPEC = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*\s*(==|>=|<=|~=|!=)\s*\S+\s*$")
MODULES = (
    "django",
    "rest_framework",
    "pandas",
    "numpy",
    "requests",
    "PIL",
    "suntime",
    "apscheduler",
    "tzlocal",
    "customtkinter",
    "darkdetect",
    "pystray",
    "win32api",
    "httpx",
    "geopy",
    "xmltodict",
    "shapely",
    "scipy",
    "rapidfuzz",
)


def log_line(text: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8", errors="replace") as handle:
        handle.write(text + "\n")


def run(args: list[str]) -> int:
    shown = " ".join(args)
    print("+ " + shown)
    log_line("$ " + shown)
    proc = subprocess.Popen(
        args,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    assert proc.stdout is not None
    for raw in proc.stdout:
        line = raw.decode("utf-8", errors="replace")
        if "\ufffd" in line:
            line = raw.decode("gbk", errors="replace")
        sys.stdout.write(line)
        with LOG.open("a", encoding="utf-8", errors="replace") as handle:
            handle.write(line)
    return proc.wait()


def requirements_ok() -> bool:
    if not REQ.is_file():
        print("找不到 requirements_production.txt")
        return False
    data = REQ.read_bytes()
    if data.startswith(b"\xef\xbb\xbf") or any(byte > 127 for byte in data):
        print("requirements_production.txt 含有中文或异常字符，文件可能已损坏。")
        print("请换回仓库里的纯 ASCII 版本，不要往这个文件里写中文。")
        return False
    bad: list[str] = []
    for number, line in enumerate(data.decode("ascii").splitlines(), 1):
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        if SPEC.fullmatch(text) is None:
            bad.append(f"第 {number} 行：{text}")
    if bad:
        print("requirements_production.txt 有无法识别的行：")
        print("\n".join(bad))
        return False
    return True


def imports_ok() -> bool:
    failed: list[str] = []
    for name in MODULES:
        try:
            __import__(name)
        except Exception as exc:
            failed.append(f"{name}: {exc}")
    if failed:
        print("以下模块导入失败：")
        print("\n".join(failed))
        return False
    print("关键模块导入成功。")
    return True


def main() -> int:
    print("FMSA 依赖安装")
    print(f"Python {sys.version.split()[0]}")
    print(sys.executable)
    print(f"依赖清单：{REQ}")
    if sys.version_info < (3, 12):
        print("需要 Python 3.12 或更高版本。")
        return 1
    if not requirements_ok():
        return 1
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text("", encoding="utf-8")
    log_line(f"Python {sys.version}")
    log_line(sys.executable)
    print("正在升级 pip / setuptools / wheel ...")
    if run([sys.executable, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"]) != 0:
        print("pip 升级失败，继续安装依赖。")
    print("正在安装 requirements_production.txt ...")
    if run([sys.executable, "-m", "pip", "install", "-r", str(REQ)]) != 0:
        print("安装失败。详情见 logs\\install.log")
        return 1
    if not imports_ok():
        print("安装结束，但有模块无法导入。详情见 logs\\install.log")
        return 1
    print("全部依赖安装完成。")
    print("可用这些文件启动：")
    for path in sorted(ROOT.glob("*.vbs")) + sorted(ROOT.glob("*.bat")):
        print(" ", path.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
