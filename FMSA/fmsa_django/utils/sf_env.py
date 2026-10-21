"""
读取 FMSA 根目录 .env，供内网地址使用。
不依赖 Django，启动任意脚本时都可以先 load_fmsa_env()。
"""
from pathlib import Path
import os

_LOADED = False
_FMSA_ROOT = Path(__file__).resolve().parents[2]


def load_fmsa_env():
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    path = _FMSA_ROOT / '.env'
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding='utf-8')
    except OSError:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        os.environ.setdefault(key, value)


def env(name, default=''):
    load_fmsa_env()
    return (os.environ.get(name, default) or default).strip()


def require(name):
    value = env(name)
    if not value:
        raise RuntimeError(
            f'缺少 {name}。请复制 FMSA/.env.example 为 FMSA/.env 并填写本机内网地址。'
        )
    return value


def intranet_base_url():
    return require('SF_INTRANET_BASE_URL').rstrip('/')


def intranet_url(path):
    suffix = path if str(path).startswith('/') else f'/{path}'
    return f'{intranet_base_url()}{suffix}'
