"""
报文原文告警着色（实况弹窗 / 机场详情共用）。
数据来自 airportMetList 原始报文，avwx 解析 + 入库同款阈值；不影响图表与入库解析。
"""

from __future__ import annotations

import html
import logging
import re
from typing import Optional

from parsers.metar_history import (
    _rvr_to_m,
    _visibility_to_m,
    _wind_to_mps,
    fetch_latest_raw_metars,
    fetch_raw_met_list,
)
from parsers.metar_parser import MetarParser

logger = logging.getLogger('fmsa.parsers')

_WS_RE = re.compile(
    r'\bWS(?:\s+ALL)?(?:\s+RWY\d*[LCR]?)?(?:\s+R?\d{2}[LCR]?)?',
    re.IGNORECASE,
)
_TAF_WS_RE = re.compile(r'\bWS\d{3}/\d+(?:KT|MPS)?\b', re.IGNORECASE)
_TREND_RE = re.compile(
    r'\b(?:TEMPO|BECMG|INTER)\b.*?(?=\sRMK\b|$)',
    re.IGNORECASE | re.DOTALL,
)
_TX_TN_RE = re.compile(r'\bT[XN](M?\d{2})/\d{4}Z\b', re.IGNORECASE)


def build_popup_metar_reports(
    airport_code: str,
    time_mode: str = 'current',
    token: Optional[str] = None,
) -> list:
    reports = fetch_latest_raw_metars(
        airport_code, time_mode=time_mode, token=token, limit=3
    )
    parser = MetarParser(time_mode=time_mode, token=token)
    thresholds = parser._get_airport_thresholds(airport_code)
    result = []
    for item in reports:
        content = item['content']
        result.append({
            'content': content,
            'html': highlight_metar_content(content, airport_code, thresholds, parser),
        })
    return result


def select_taf_reports(items: list) -> list:
    """同时有 FC/FT：各取最新 1 份；仅 FC：最新 1 份 FC；仅 FT：最新 1 份 FT。"""
    fc = [i for i in items if i.get('wtype') == 'FC']
    ft = [i for i in items if i.get('wtype') == 'FT']
    fc.sort(key=lambda x: x.get('sort_time') or -1, reverse=True)
    ft.sort(key=lambda x: x.get('sort_time') or -1, reverse=True)
    if fc and ft:
        selected = fc[:1] + ft[:1]
    elif fc:
        selected = fc[:1]
    else:
        selected = ft[:1]
    selected.sort(key=lambda x: x.get('sort_time') or -1, reverse=True)
    return selected


def build_airport_detail_reports(
    airport_code: str,
    time_mode: str = 'current',
    token: Optional[str] = None,
) -> dict:
    items = fetch_raw_met_list(
        airport_code,
        time_mode=time_mode,
        token=token,
        ws_types=['SA', 'SP', 'FC', 'FT'],
    )
    parser = MetarParser(time_mode=time_mode, token=token)
    thresholds = parser._get_airport_thresholds(airport_code)

    metars = [i for i in items if i.get('wtype') in ('SA', 'SP')]
    metars.sort(key=lambda x: x.get('sort_time') or -1, reverse=True)
    metars = metars[:5]
    tafs = select_taf_reports(items)

    return {
        'metar_reports': [
            {
                'content': item['content'],
                'wtype': item.get('wtype'),
                'html': highlight_metar_content(
                    item['content'], airport_code, thresholds, parser
                ),
            }
            for item in metars
        ],
        'taf_reports': [
            {
                'content': item['content'],
                'wtype': item.get('wtype'),
                'html': highlight_taf_content(
                    item['content'], airport_code, thresholds, parser
                ),
            }
            for item in tafs
        ],
    }


def highlight_metar_content(
    content: str,
    airport_code: str,
    thresholds: dict,
    parser: MetarParser,
) -> str:
    if not content:
        return ''
    try:
        data, units, is_na = _parse_avwx_metar(content, airport_code)
    except Exception as exc:
        logger.debug(f'实况原文 avwx 解析失败 [{airport_code}]: {exc}')
        return html.escape(content)

    spans = []
    if data is not None and units is not None:
        spans.extend(_wind_spans(content, data, units, thresholds, parser))
        spans.extend(_visibility_spans(content, data, units, thresholds, parser))
        spans.extend(_weather_spans(content, data, parser))
        spans.extend(_cloud_spans(content, data, thresholds, parser))
        spans.extend(_rvr_spans(content, data, is_na, thresholds, parser))
        spans.extend(_temperature_spans(content, data, thresholds))
        spans.extend(_ws_spans(content))
        spans.extend(_trend_spans(content))
    return _render_spans(content, spans)


def highlight_taf_content(
    content: str,
    airport_code: str,
    thresholds: dict,
    parser: MetarParser,
) -> str:
    if not content:
        return ''
    try:
        from avwx_custom import Taf as AvwxTaf
        from avwx_custom.station.meta import uses_na_format
        from avwx_custom.exceptions import BadStation

        station = airport_code
        try:
            taf = AvwxTaf(station)
        except BadStation:
            words = content.split()
            station = next(
                (w.upper() for w in words if len(w) == 4 and w.isalpha() and w.upper() not in ('TAF', 'AMD', 'COR')),
                airport_code,
            )
            taf = AvwxTaf(station)
        parsed = taf.parse(content)
        if not parsed or not taf.data or not taf.units:
            return _taf_split_escaped(content)
        data, units = taf.data, taf.units
        try:
            is_na = uses_na_format(airport_code[:2])
        except Exception:
            is_na = False
    except Exception as exc:
        logger.debug(f'预报原文 avwx 解析失败 [{airport_code}]: {exc}')
        return _taf_split_escaped(content)

    periods = _taf_display_periods(content)
    forecast = data.forecast or []
    html_lines = ['<span class="taf-report-grid">']
    for i, raw in enumerate(periods):
        line = forecast[i] if i < len(forecast) else None
        html_lines.append(_render_taf_period_row(raw, line, units, thresholds, parser, is_na, i == 0))
    html_lines.append('</span>')
    return ''.join(html_lines)


def _taf_display_periods(content: str) -> list:
    """avwx split_taf 会在长效有效时间处断开，将第一变化组之前的片段合并回主预报行。"""
    from avwx_custom.current.taf import split_taf, starts_new_line

    pieces = split_taf(content.strip())
    if not pieces:
        return [content] if content else []
    merged = []
    for piece in pieces:
        tokens = piece.split()
        first = tokens[0] if tokens else ''
        if merged and not starts_new_line(first):
            merged[-1] = f'{merged[-1]} {piece}'.strip()
        else:
            merged.append(piece)
    return merged


def _split_taf_header_and_rest(raw: str, is_first: bool) -> tuple[str, str]:
    """主预报行在发报时间（DDHHMMZ）处切开；变化组整行放在发报时间这一列。"""
    if not is_first:
        return '', raw
    tokens = raw.split()
    time_idx = None
    for i, token in enumerate(tokens):
        if len(token) == 7 and token.endswith('Z') and token[:6].isdigit():
            time_idx = i
            break
    if time_idx is None:
        return '', raw
    return ' '.join(tokens[:time_idx]), ' '.join(tokens[time_idx:])


def _render_taf_period_row(raw, line, units, thresholds, parser, is_na, is_first) -> str:
    header, rest = _split_taf_header_and_rest(raw, is_first)
    rest_html = _highlight_taf_period(rest or raw, line, units, thresholds, parser, is_na)
    header_html = html.escape(header) if header else ''
    return (
        f'<span class="taf-period-line">'
        f'<span class="taf-period-prefix">{header_html}</span>'
        f'<span class="taf-period-body">{rest_html}</span>'
        f'</span>'
    )


def _taf_split_escaped(content: str) -> str:
    try:
        periods = _taf_display_periods(content) or [content]
    except Exception:
        periods = [content]
    html_lines = ['<span class="taf-report-grid">']
    for i, raw in enumerate(periods):
        if not raw:
            continue
        header, rest = _split_taf_header_and_rest(raw, i == 0)
        html_lines.append(
            f'<span class="taf-period-line">'
            f'<span class="taf-period-prefix">{html.escape(header)}</span>'
            f'<span class="taf-period-body">{html.escape(rest or raw)}</span>'
            f'</span>'
        )
    html_lines.append('</span>')
    return ''.join(html_lines)


def _highlight_taf_period(raw, line, units, thresholds, parser, is_na) -> str:
    if not raw:
        return ''
    if line is None:
        return html.escape(raw)
    spans = []
    if line.wind_speed or line.wind_gust:
        level = _wind_alert_level(line.wind_speed, line.wind_gust, units, thresholds, parser)
        if level != 'N':
            spans.extend(_wind_token_spans(raw, [level]))
    if line.visibility:
        spans.extend(_visibility_list_spans(raw, [line.visibility], units, thresholds, parser))
    spans.extend(_weather_code_spans(raw, line.wx_codes or [], parser))
    spans.extend(_cloud_list_spans(raw, line.clouds or [], thresholds, parser))
    if getattr(line, 'runway_visibility', None):
        class _RvrHolder:
            runway_visibility = line.runway_visibility
        spans.extend(_rvr_spans(raw, _RvrHolder(), is_na, thresholds, parser))
    spans.extend(_taf_temp_spans(raw, thresholds))
    spans.extend(_ws_spans(raw))
    spans.extend(_taf_ws_spans(raw))
    return _render_spans(raw, spans)


def _parse_avwx_metar(content: str, airport_code: str):
    from avwx_custom.current.metar import parse_na, parse_in
    from avwx_custom.station.meta import uses_na_format

    try:
        is_na = uses_na_format(airport_code[:2])
    except Exception:
        is_na = False
    data, units, _ = (parse_na if is_na else parse_in)(content)
    return data, units, is_na


def _iter_tokens(content: str):
    for match in re.finditer(r'\S+', content):
        yield match.start(), match.end(), match.group()


def _find_token(content: str, token: str, used: list) -> tuple[int, int] | None:
    if not token:
        return None
    start = 0
    while True:
        idx = content.find(token, start)
        if idx < 0:
            return None
        end = idx + len(token)
        if not _overlaps(idx, end, used) and _token_boundary(content, idx, end):
            return idx, end
        start = idx + 1


def _token_boundary(content: str, start: int, end: int) -> bool:
    left_ok = start == 0 or content[start - 1].isspace()
    right_ok = end >= len(content) or content[end].isspace()
    return left_ok and right_ok


def _overlaps(start: int, end: int, used: list) -> bool:
    return any(start < u_end and end > u_start for u_start, u_end in used)


def _add_span(spans: list, start: int, end: int, level: str):
    if level in ('R', 'Y', 'G') and start < end:
        spans.append((start, end, level))


def _max_level(*levels) -> str:
    for level in ('R', 'Y', 'G'):
        if level in levels:
            return level
    return 'N'


def _wind_alert_level(speed_obj, gust_obj, units, thresholds, parser: MetarParser) -> str:
    if not thresholds:
        return 'N'
    wind_mps = _wind_to_mps(speed_obj.value if speed_obj else None, units.wind_speed)
    gust_mps = _wind_to_mps(gust_obj.value if gust_obj else None, units.wind_speed)
    wind_alert = parser._get_alert_level(
        wind_mps, thresholds.get('wind_red'), thresholds.get('wind_yellow'), thresholds.get('wind_green')
    ) if wind_mps is not None else 'N'
    gust_alert = parser._get_alert_level(
        gust_mps, thresholds.get('gust_red'), thresholds.get('gust_yellow'), thresholds.get('gust_green')
    ) if gust_mps is not None else 'N'
    return _max_level(wind_alert, gust_alert)


def _wind_token_spans(content, levels: list) -> list:
    from avwx_custom.parsing.core import is_wind

    spans = []
    idx = 0
    for start, end, token in _iter_tokens(content):
        if idx >= len(levels):
            break
        if is_wind(token):
            _add_span(spans, start, end, levels[idx])
            idx += 1
    return spans


def _wind_spans(content, data, units, thresholds, parser: MetarParser) -> list:
    level = _wind_alert_level(data.wind_speed, data.wind_gust, units, thresholds, parser)
    if level == 'N':
        return []
    return _wind_token_spans(content, [level])


def _visibility_spans(content, data, units, thresholds, parser: MetarParser) -> list:
    if not data.visibility:
        return []
    return _visibility_list_spans(content, [data.visibility], units, thresholds, parser)


def _visibility_list_spans(content, vis_list, units, thresholds, parser: MetarParser) -> list:
    if not vis_list or not thresholds:
        return []
    spans = []
    used = []
    for vis in vis_list:
        vis_repr = vis.repr or ''
        if vis_repr in ('CAVOK',) or vis_repr.startswith('P6'):
            vis_val = 10000
        else:
            vis_val = _visibility_to_m(vis.value, units.visibility)
        level = parser._get_alert_level(
            vis_val,
            thresholds.get('visibility_red'),
            thresholds.get('visibility_yellow'),
            thresholds.get('visibility_green'),
            reverse=True,
        )
        if level == 'N':
            used_skip = _find_token(content, vis_repr, used)
            if used_skip:
                used.append(used_skip)
            continue
        candidates = [vis_repr]
        if vis_repr and not vis_repr.endswith('SM') and units.visibility == 'sm':
            candidates.append(vis_repr + 'SM')
        if vis_repr == 'CAVOK':
            candidates = ['CAVOK']
        for token in candidates:
            found = _find_token(content, token, used)
            if found:
                used.append(found)
                _add_span(spans, found[0], found[1], level)
                break
    return spans


def _weather_spans(content, data, parser: MetarParser) -> list:
    return _weather_code_spans(content, data.wx_codes or [], parser)


def _weather_code_spans(content, wx_codes, parser: MetarParser) -> list:
    spans = []
    used = []
    for code in wx_codes:
        token = code.repr if code else None
        if not token:
            continue
        level, _types = parser._get_weather_alert_level_single(token)
        if level == 'N':
            found_skip = _find_token(content, token, used)
            if found_skip:
                used.append(found_skip)
            continue
        found = _find_token(content, token, used)
        if found:
            used.append(found)
            _add_span(spans, found[0], found[1], level)
    return spans


def _cloud_spans(content, data, thresholds, parser: MetarParser) -> list:
    return _cloud_list_spans(content, data.clouds or [], thresholds, parser)


def _cloud_list_spans(content, clouds, thresholds, parser: MetarParser) -> list:
    if not clouds or not thresholds:
        return []
    spans = []
    used = []
    for cloud in clouds:
        token = cloud.repr if cloud else None
        if not token or cloud.base is None:
            continue
        level = parser._get_alert_level(
            cloud.base,
            thresholds.get('cloud_red'),
            thresholds.get('cloud_yellow'),
            thresholds.get('cloud_green'),
            reverse=True,
        )
        found = _find_token(content, token, used)
        if not found:
            continue
        used.append(found)
        if level != 'N':
            _add_span(spans, found[0], found[1], level)
    return spans


def _rvr_numeric(number, is_na: bool):
    if number is None:
        return None
    if number.value is not None:
        return _rvr_to_m(number.value, is_na)
    if number.repr:
        digits = re.search(r'\d+', str(number.repr))
        if digits:
            return _rvr_to_m(int(digits.group()), is_na)
    return None


def _rvr_spans(content, data, is_na: bool, thresholds, parser: MetarParser) -> list:
    if not data.runway_visibility or not thresholds:
        return []
    spans = []
    used = []
    for rvr in data.runway_visibility:
        token = rvr.repr if rvr else None
        if not token:
            continue
        values = [_rvr_numeric(rvr.visibility, is_na)]
        for var in (rvr.variable_visibility or []):
            values.append(_rvr_numeric(var, is_na))
        valid = [v for v in values if v is not None]
        if not valid:
            continue
        level = parser._get_alert_level(
            min(valid),
            thresholds.get('rvr_red'),
            thresholds.get('rvr_yellow'),
            thresholds.get('rvr_green'),
            reverse=True,
        )
        if level == 'N':
            continue
        found = _find_token(content, token, used)
        if found:
            used.append(found)
            _add_span(spans, found[0], found[1], level)
    return spans


def _temperature_spans(content, data, thresholds) -> list:
    if not data.temperature or data.temperature.value is None or not thresholds:
        return []
    level = _temp_value_level(float(data.temperature.value), thresholds)
    if level == 'N':
        return []
    temp_repr = data.temperature.repr
    dew_repr = data.dewpoint.repr if data.dewpoint else None
    if temp_repr and dew_repr:
        combo = f'{temp_repr}/{dew_repr}'
        idx = content.find(combo)
        if idx >= 0:
            return [(idx, idx + len(temp_repr), level)]
    found = _find_token(content, temp_repr, [])
    if found:
        return [(found[0], found[1], level)]
    return []


def _temp_value_level(temp_val: float, thresholds: dict) -> str:
    cold_r = thresholds.get('temp_cold_red')
    cold_y = thresholds.get('temp_cold_yellow')
    cold_g = thresholds.get('temp_cold_green')
    hot_r = thresholds.get('temp_hot_red')
    hot_y = thresholds.get('temp_hot_yellow')
    hot_g = thresholds.get('temp_hot_green')
    try:
        if cold_r is not None and temp_val <= cold_r:
            return 'R'
        if cold_y is not None and temp_val <= cold_y:
            return 'Y'
        if cold_g is not None and temp_val <= cold_g:
            return 'G'
        if hot_r is not None and temp_val >= hot_r:
            return 'R'
        if hot_y is not None and temp_val >= hot_y:
            return 'Y'
        if hot_g is not None and temp_val >= hot_g:
            return 'G'
    except TypeError:
        return 'N'
    return 'N'


def _taf_temp_spans(content: str, thresholds: dict) -> list:
    if not thresholds:
        return []
    spans = []
    for match in _TX_TN_RE.finditer(content):
        raw = match.group(1).upper()
        try:
            temp_val = -int(raw[1:]) if raw.startswith('M') else int(raw)
        except ValueError:
            continue
        level = _temp_value_level(float(temp_val), thresholds)
        _add_span(spans, match.start(), match.end(), level)
    return spans


def _ws_spans(content: str) -> list:
    body = content
    rmk = re.search(r'\bRMK\b', content)
    if rmk:
        body = content[:rmk.start()]
    spans = []
    for match in _WS_RE.finditer(body):
        _add_span(spans, match.start(), match.end(), 'R')
    return spans


def _taf_ws_spans(content: str) -> list:
    spans = []
    for match in _TAF_WS_RE.finditer(content):
        _add_span(spans, match.start(), match.end(), 'R')
    return spans


def _trend_spans(content: str) -> list:
    match = _TREND_RE.search(content)
    if match:
        return [(match.start(), match.end(), 'R')]
    return []


def _render_spans(content: str, spans: list) -> str:
    cleaned = []
    for start, end, level in spans:
        if level in ('R', 'Y', 'G') and 0 <= start < end <= len(content):
            cleaned.append((start, end, level))
    cleaned.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    picked = []
    for start, end, level in cleaned:
        if any(start < pe and end > ps for ps, pe, _ in picked):
            continue
        picked.append((start, end, level))
    picked.sort(key=lambda x: x[0])
    parts = []
    last = 0
    for start, end, level in picked:
        parts.append(html.escape(content[last:start]))
        parts.append(
            f'<span class="report-alert report-alert-{level}">'
            f'{html.escape(content[start:end])}</span>'
        )
        last = end
    parts.append(html.escape(content[last:]))
    return ''.join(parts)
