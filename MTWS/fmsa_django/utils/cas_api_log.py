"""
记录每一次请求顺丰 CAS / 内网业务 API 时的用户工号。

工号与 token 是分开的：token 负责鉴权，工号只是展示/落库身份。
占位工号（如 --）时仍可能带着有效 token 把外部接口调通。
"""

from contextlib import contextmanager
from contextvars import ContextVar
import logging

logger = logging.getLogger('fmsa.cas_api')

_current_user_id = ContextVar('fmsa_cas_user_id', default=None)
_current_client_ip = ContextVar('fmsa_cas_client_ip', default=None)
_omit_user_fallback = ContextVar('fmsa_cas_omit_user_fallback', default=False)


def resolve_cas_user_id(explicit=None):
    if explicit not in (None, ''):
        return str(explicit).strip()
    bound = _current_user_id.get()
    if bound:
        return str(bound).strip()
    if _omit_user_fallback.get():
        return None
    try:
        from parsers.scheduler import get_scheduler_user_code
        code = get_scheduler_user_code()
        if code:
            return str(code).strip()
    except Exception:
        pass
    return None


@contextmanager
def cas_user_context(user_id, client_ip=None, omit_user_fallback=False):
    uid_token = _current_user_id.set(str(user_id).strip() if user_id else None)
    ip_token = _current_client_ip.set(client_ip or None)
    omit_token = _omit_user_fallback.set(bool(omit_user_fallback))
    try:
        yield
    finally:
        _current_user_id.reset(uid_token)
        _current_client_ip.reset(ip_token)
        _omit_user_fallback.reset(omit_token)


def log_cas_api_request(endpoint, user_id=None, has_token=None):
    """NWP 等非 CAS 接口不要调用本函数。"""
    uid = resolve_cas_user_id(user_id)
    ip = _current_client_ip.get()
    token_flag = '有' if has_token else ('无' if has_token is False else '未标明')
    parts = ['CAS外部API请求']
    if ip:
        parts.append(f'IP={ip}')
    if uid:
        parts.append(f'user_id={uid}')
    elif not ip:
        parts.append('user_id=(未知)')
    parts.append(f'has_token={token_flag}')
    parts.append(f'endpoint={endpoint}')
    logger.info(' '.join(parts))
