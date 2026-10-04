"""
历史 METAR 数据获取与解析模块
专用于机场详情页图表的 72 小时历史气象要素数据。
"""

import re
import logging
import requests
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger('mtws.parsers')

_HISTORY_API_URL = (
    "http://sfa-wgw-inn.sf-airlines.com:1080"
    "/met/dispatchMetTelSummary/airportMetList"
)

# 单位换算常数
_KT_TO_MPS = 0.514444   # 节 → 米/秒
_SM_TO_M = 1609.34       # 英里 → 米
_FT_RVR_FACTOR = 1 / 3  # 英尺 RVR → 米（与现有 _parse_rvr_min_value 保持一致）


# ------------------------------------------------------------------
# 内部工具函数
# ------------------------------------------------------------------

def _build_headers(time_mode: str, token: Optional[str]) -> dict:
    """构造与 api_adapter.py 一致的请求头。"""
    if time_mode == 'current':
        return {'token': token or '', 'Content-Type': 'application/json'}
    return {
        'systemKey': '629dd582-f044-41ec-aebb-1f352e26ca92',
        'accessKey': 'api2_935b8fc3-a8dc-41d5-a6d0-1c91b1d3e209',
        'Content-Type': 'application/json',
    }


def _extract_obs_timestamp_ms(content: str, now_ms: int) -> Optional[int]:
    """
    从 METAR 报文中提取 DDHHMM Z 时间组，结合当前时间推断正确的年月，
    返回毫秒级 UTC 时间戳。支持跨月边界（72 小时窗口内最多跨一个月）。
    """
    match = re.search(r'\b(\d{2})(\d{2})(\d{2})Z\b', content)
    if not match:
        return None
    day = int(match.group(1))
    hour = int(match.group(2))
    minute = int(match.group(3))

    now_dt = datetime.utcfromtimestamp(now_ms / 1000).replace(tzinfo=timezone.utc)

    # 先尝试当月，再尝试上月（处理月底跨月）
    for month_offset in (0, -1):
        year = now_dt.year
        month = now_dt.month + month_offset
        if month <= 0:
            month += 12
            year -= 1
        try:
            candidate = datetime(year, month, day, hour, minute, 0, tzinfo=timezone.utc)
        except ValueError:
            continue
        diff_ms = now_ms - int(candidate.timestamp() * 1000)
        # 接受 0 ~ 73 小时内的时间戳（73 = 72h + 1h 宽限）
        if 0 <= diff_ms <= 73 * 3_600_000:
            return int(candidate.timestamp() * 1000)

    return None


def _wind_to_mps(value, unit: str) -> Optional[float]:
    """将风速换算为 m/s，保留 1 位小数。"""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if unit == 'kt':
        return round(v * _KT_TO_MPS, 1)
    if unit == 'm/s':
        return round(v, 1)
    if unit == 'km/h':
        return round(v / 3.6, 1)
    return round(v, 1)


def _visibility_to_m(value, unit: str) -> Optional[int]:
    """将能见度换算为整数米。"""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if unit == 'sm':
        return int(round(v * _SM_TO_M))
    return int(round(v))


def _rvr_to_m(value, is_na: bool) -> Optional[int]:
    """将 RVR 值换算为整数米（NA 格式单位为英尺，国际格式已为米）。"""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if is_na:
        return int(v * _FT_RVR_FACTOR)
    return int(v)


def _parse_single_metar(
    content: str,
    airport_code: str,
    now_ms: int,
    min_cloud_amt: Optional[str] = None,
) -> Optional[dict]:
    """
    使用 avwx_custom 解析单条 METAR/SPECI 报文。
    成功返回包含图表所需 7 个字段的字典，失败返回 None。
    """
    try:
        from avwx_custom.current.metar import parse_na, parse_in
        from avwx_custom.station.meta import uses_na_format
    except ImportError as exc:
        logger.error(f'导入 avwx_custom 失败: {exc}')
        return None

    try:
        is_na = uses_na_format(airport_code[:2])
    except Exception:
        is_na = False  # 无法识别前缀时默认国际格式

    try:
        data, units, _ = (parse_na if is_na else parse_in)(content)
    except Exception as exc:
        logger.debug(f'avwx 解析报文失败 [{airport_code}]: {exc}')
        return None

    if data is None or units is None:
        return None

    # 观测时间
    obs_ts = _extract_obs_timestamp_ms(content, now_ms)
    if obs_ts is None:
        return None

    # 风速 / 阵风 → m/s
    wind_speed_val = _wind_to_mps(
        data.wind_speed.value if data.wind_speed else None,
        units.wind_speed,
    )
    gust_val = _wind_to_mps(
        data.wind_gust.value if data.wind_gust else None,
        units.wind_speed,
    )

    # 能见度 → 整数米
    vis_val = None
    if data.visibility:
        vis_repr = data.visibility.repr or ''
        if vis_repr in ('CAVOK',) or vis_repr.startswith('P6'):
            # CAVOK / P6SM → 10000 m（能见度极好）
            vis_val = 10000
        else:
            vis_val = _visibility_to_m(data.visibility.value, units.visibility)

    # RVR 最小值 → 整数米
    rvr_min_val = None
    if data.runway_visibility:
        rvr_values = [
            _rvr_to_m(rvr.visibility.value, is_na)
            for rvr in data.runway_visibility
            if rvr.visibility and rvr.visibility.value is not None
        ]
        valid_rvr = [v for v in rvr_values if v is not None]
        if valid_rvr:
            rvr_min_val = min(valid_rvr)

    # 最低云底高：只取达到云量下限的云组，单位百英尺
    from parsers.cloud_amount import lowest_base_from_cloud_objects, resolve_min_cloud_amt
    if min_cloud_amt is None:
        min_cloud_amt = resolve_min_cloud_amt(airport_code)
    min_cloud_height = lowest_base_from_cloud_objects(data.clouds, min_cloud_amt)

    # 气温 (℃)
    temp_val = None
    if data.temperature and data.temperature.value is not None:
        temp_val = float(data.temperature.value)

    # 天气现象（原始 METAR 代码，如 +TSRA、BR，多个用逗号分隔）
    metar_weather = None
    if data.wx_codes:
        codes = [c.repr for c in data.wx_codes if c.repr]
        if codes:
            metar_weather = ','.join(codes)

    return {
        'metar_observation_time': obs_ts,
        'metar_wind_speed_val': wind_speed_val,
        'metar_gust_val': gust_val,
        'metar_visibility_val': vis_val,
        'rvr_min_val': rvr_min_val,
        'metar_min_cloud_height': min_cloud_height,
        'metar_temp_val': temp_val,
        'metar_weather': metar_weather,
    }


def _fetch_history_obj(
    airport_code: str,
    time_mode: str,
    token: Optional[str],
    ws_types=None,
    start_ms: Optional[int] = None,
    end_ms: Optional[int] = None,
):
    """
    调用与趋势图相同的原始历史报文接口（airportMetList），返回 (obj列表, now_ms, 是否成功)。
    失败时 obj 为空列表且成功标志为 False。可传入 start_ms/end_ms 覆盖默认的近 72 小时窗口。
    """
    now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    end = int(end_ms if end_ms is not None else now_ms)
    start = int(start_ms if start_ms is not None else end - 72 * 3_600_000)
    if start > end:
        start, end = end, start
    if not ws_types:
        ws_types = ['SA', 'SP']

    payload = {
        'code4s': airport_code,
        'wsTypes': list(ws_types),
        'historyFlag': 'Y',
        'searchStartDate': start,
        'searchEndDate': end,
        'metarOrTafTopNum': 100000,
        'otherTopNum': 100000,
    }

    headers = _build_headers(time_mode, token)

    try:
        from utils.cas_api_log import log_cas_api_request
        log_cas_api_request(
            '/met/dispatchMetTelSummary/airportMetList',
            has_token=bool(token) if time_mode == 'current' else False,
        )
        response = requests.post(
            _HISTORY_API_URL,
            headers=headers,
            json=payload,
            timeout=30,
        )
        logger.info(
            f'历史报文请求 [{airport_code}] {ws_types}: HTTP {response.status_code}'
        )
        if response.status_code != 200:
            logger.error(
                f'历史报文请求失败 [{airport_code}]: HTTP {response.status_code}'
            )
            return [], now_ms, False
        resp_data = response.json()
    except Exception as exc:
        logger.error(f'历史报文请求异常 [{airport_code}]: {exc}')
        return [], now_ms, False

    if not resp_data.get('success'):
        logger.error(
            f'历史报文接口返回失败 [{airport_code}]: '
            f'{resp_data.get("errorMessage", "未知错误")}'
        )
        return [], now_ms, False

    obj = resp_data.get('obj') or []
    if not obj:
        logger.info(f'历史报文无数据 [{airport_code}] {ws_types}')
        return [], now_ms, True
    return obj, now_ms, True


def _item_wtype(item: dict, content: str) -> str:
    wtype = str(item.get('wtype') or item.get('wsType') or item.get('type') or '').upper().strip()
    if wtype in ('SA', 'SP', 'FC', 'FT'):
        return wtype
    head = content[:40].upper()
    if head.startswith('TAF') or ' TAF' in head:
        match = re.search(r'\b(\d{2})(\d{2})/(\d{2})(\d{2})\b', content)
        if match:
            d1, h1, d2, h2 = (int(g) for g in match.groups())
            hours = ((d2 - d1) % 31) * 24 + (h2 - h1)
            return 'FC' if 0 < hours <= 12 else 'FT'
        return 'FT'
    if 'SPECI' in head or head.startswith('SP'):
        return 'SP'
    return 'SA'


def fetch_raw_met_list(
    airport_code: str,
    time_mode: str = 'current',
    token: Optional[str] = None,
    ws_types=None,
    start_ms: Optional[int] = None,
    end_ms: Optional[int] = None,
) -> list:
    """
    从同源原始接口取报文列表。
    每项: {content, wtype, sort_time}
    可传入 start_ms/end_ms 限定时间范围；默认近 72 小时。
    """
    obj, now_ms, _ok = _fetch_history_obj(
        airport_code,
        time_mode,
        token,
        ws_types=ws_types,
        start_ms=start_ms,
        end_ms=end_ms,
    )
    items = []
    for item in obj:
        content = (item.get('content') or '').strip()
        if not content:
            continue
        obs_ts = _extract_obs_timestamp_ms(content, now_ms)
        receive = item.get('receiveTime') or item.get('observationTime') or 0
        try:
            receive = int(receive)
        except (TypeError, ValueError):
            receive = 0
        sort_time = obs_ts if obs_ts is not None else receive
        items.append({
            'content': content,
            'wtype': _item_wtype(item, content),
            'sort_time': sort_time if sort_time is not None else -1,
        })
    items.sort(key=lambda x: x['sort_time'], reverse=True)
    return items


def fetch_latest_raw_metars(
    airport_code: str,
    time_mode: str = 'current',
    token: Optional[str] = None,
    limit: int = 3,
) -> list:
    """
    从趋势图同源原始接口取报文，按观测时间从新到旧返回最多 limit 条原文。
    每项: {content, metar_observation_time}
    """
    items = fetch_raw_met_list(
        airport_code, time_mode=time_mode, token=token, ws_types=['SA', 'SP']
    )
    result = []
    for item in items[:limit]:
        result.append({
            'content': item['content'],
            'metar_observation_time': item['sort_time'],
        })
    return result


# ------------------------------------------------------------------
# 公开接口
# ------------------------------------------------------------------

def fetch_and_parse_metar_history(
    airport_code: str,
    time_mode: str = 'current',
    token: Optional[str] = None,
) -> list:
    """
    获取并解析指定机场最近 72 小时的历史 METAR/SPECI 数据。

    Returns:
        按观测时间升序排列的图表数据点列表，每项包含：
        metar_observation_time, metar_wind_speed_val, metar_gust_val,
        metar_visibility_val, rvr_min_val, metar_min_cloud_height, metar_temp_val
    """
    obj, now_ms, _ok = _fetch_history_obj(airport_code, time_mode, token)
    if not obj:
        return []

    from parsers.cloud_amount import resolve_min_cloud_amt
    min_cloud_amt = resolve_min_cloud_amt(airport_code)

    results = []
    for item in obj:
        content = (item.get('content') or '').strip()
        if not content:
            continue
        parsed = _parse_single_metar(content, airport_code, now_ms, min_cloud_amt)
        if parsed:
            results.append(parsed)

    # 按观测时间去重：同一分钟可能同时存在 SA 和 SP，保留先出现的一条
    seen_times: set = set()
    deduped = []
    for r in results:
        t = r['metar_observation_time']
        if t not in seen_times:
            seen_times.add(t)
            deduped.append(r)

    deduped.sort(key=lambda x: x['metar_observation_time'])
    logger.info(
        f'历史 METAR 解析完成 [{airport_code}]: {len(deduped)} 条有效数据点'
    )
    return deduped
