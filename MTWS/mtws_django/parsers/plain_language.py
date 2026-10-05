"""明语（中文）翻译：气象要素 → 中文文本 + 告警着色。

只做翻译与着色，不解析报文、不写库。两条输入路径共用同一套渲染：

1. 入库列 ``taf.taf_elements``（中文模式列表、详情页甘特条带）
2. avwx 现场解析结果（详情页实况/预报原文区，逐份报文逐时段）

天气现象中文名取自 ``weather_alert_levels.description``；其余句式与码表写在本文件。
告警只作用在要素值本身（``plain-val plain-val-R/Y/G`` 字体色），时段整体告警
以圆点（``plain-dot-*``）显示在时段左侧。
"""

from __future__ import annotations

import html
import logging
import re
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import timedelta
from typing import Any, Optional

logger = logging.getLogger('mtws.parsers')

ALERT_LEVELS = ('R', 'Y', 'G')

# 报文时刻为世界时。CST 时把显示时刻加 8 小时，与主页时区开关一致。
_plain_display_tz: ContextVar[str] = ContextVar('plain_display_tz', default='CST')


@contextmanager
def plain_display_timezone(tz: Optional[str]):
    name = 'UTC' if str(tz or '').strip().upper() == 'UTC' else 'CST'
    token = _plain_display_tz.set(name)
    try:
        yield
    finally:
        _plain_display_tz.reset(token)


def _tz_offset_hours() -> int:
    return 0 if _plain_display_tz.get() == 'UTC' else 8

# ── 码表（很少变动，写在代码里） ────────────────────────────────────

_CLOUD_COVER_ZH = {
    'FEW': '少云',
    'SCT': '疏云',
    'BKN': '多云',
    'OVC': '阴天',
    'VV': '垂直能见度',
}

_CLOUD_TYPE_ZH = {
    'CB': '积雨云',
    'TCU': '塔状积云',
}

_SKY_ZH = {
    'NSC': '无重要云',
    'SKC': '碧空',
    'CLR': '晴空',
    'NCD': '未探测到云',
}

# 变化组：label 与时段分列显示，如「11日12时    转为」
_CHANGE_ZH = {
    'FROM': '转为',
    'FM': '转为',
    'BECMG': '逐渐转为',
    'TEMPO': '短时波动',
    'INTER': '间歇出现',
}

_SPEED_UNIT_ZH = {
    'MPS': '米/秒',
    'KT': '节',
    'KMH': '公里/小时',
}

_WX_INTENSITY_ZH = {
    '-': '小',
    '+': '强',
    'VC': '附近',
}

# weather_alert_levels 里查不到时的兜底码表
_WX_FALLBACK_ZH = {
    'MI': '浅', 'BC': '散片', 'PR': '部分', 'DR': '低吹', 'BL': '高吹',
    'SH': '阵性', 'TS': '雷暴', 'FZ': '冻',
    'DZ': '毛毛雨', 'RA': '雨', 'SN': '雪', 'SG': '米雪', 'IC': '冰晶',
    'PL': '冰粒', 'GR': '冰雹', 'GS': '小冰雹', 'UP': '未知降水',
    'BR': '轻雾', 'FG': '雾', 'FU': '烟', 'VA': '火山灰', 'DU': '浮尘',
    'SA': '沙', 'HZ': '霾', 'PY': '飞沫',
    'PO': '尘卷风', 'SQ': '飑', 'FC': '漏斗云', 'SS': '沙暴', 'DS': '尘暴',
    'NSW': '重要天气现象结束',
}

_WX_CACHE_TTL = 300
_wx_cache: dict = {}

_TX_TN_RE = re.compile(r'\bT(X|N)(M?\d{2})/(\d{4})Z\b', re.IGNORECASE)
_TREND_RE = re.compile(r'\b(?:TEMPO|BECMG|INTER)\b.*?(?=\sRMK\b|$)', re.IGNORECASE | re.DOTALL)
_METAR_WS_RE = re.compile(
    r'\bWS(?:\s+ALL)?(?:\s+RWY\d*[LCR]?)?(?:\s+R?\d{2}[LCR]?)?',
    re.IGNORECASE,
)


# ── 天气现象中文名 ──────────────────────────────────────────────

def _weather_zh_map() -> dict[str, str]:
    """当前用户改过的描述优先，其余用模板。"""
    from utils.user_settings import current_settings_user, weather_rows_for

    user = current_settings_user()
    now = time.time()
    cached = _wx_cache.get(user)
    if cached and now - cached[0] < _WX_CACHE_TTL:
        return cached[1]
    mapping: dict[str, str] = {}
    try:
        for row in weather_rows_for(user):
            key = str(row.weather or '').strip().upper()
            text = str(row.description or '').strip()
            if key and text:
                mapping.setdefault(key, text)
    except Exception as exc:
        logger.warning(f'读取天气现象中文名失败: {exc}')
        return cached[1] if cached else {}
    _wx_cache[user] = (now, mapping)
    return mapping


def weather_zh(code: str) -> str:
    """天气现象码 → 中文。库里查不到时按强度前缀 + 两字母切分兜底。"""
    token = (code or '').strip().upper()
    if not token:
        return ''
    mapping = _weather_zh_map()
    if token in mapping:
        return mapping[token]
    if token in _WX_FALLBACK_ZH:
        return _WX_FALLBACK_ZH[token]

    prefix = ''
    body = token
    for mark in ('-', '+', 'VC'):
        if body.startswith(mark):
            prefix = _WX_INTENSITY_ZH[mark]
            body = body[len(mark):]
            break
    if body in mapping:
        return prefix + mapping[body]
    if body in _WX_FALLBACK_ZH:
        return prefix + _WX_FALLBACK_ZH[body]

    parts = [body[i:i + 2] for i in range(0, len(body), 2)]
    if len(body) % 2 == 0 and all(p in mapping or p in _WX_FALLBACK_ZH for p in parts):
        return prefix + ''.join(mapping.get(p) or _WX_FALLBACK_ZH[p] for p in parts)
    return token


# ── 片段（若干小段文本，只有告警值那一小段着色） ──────────────────

def _part(text: str, alert: Any = None) -> Optional[dict]:
    """片段里的一小段。alert 命中 R/Y/G 时，只有这一小段用告警色字体。"""
    if text is None or text == '':
        return None
    level = str(alert).upper() if alert else ''
    return {'text': str(text), 'alert': level if level in ALERT_LEVELS else None}


def _seg(*parts) -> Optional[dict]:
    """一个要素片段 = 若干小段；直接传字符串等价于无告警小段。"""
    items = []
    for item in parts:
        if item is None:
            continue
        piece = _part(item) if isinstance(item, str) else item
        if piece:
            items.append(piece)
    return {'parts': items} if items else None


def _join_parts(chunks: list, sep: str = '，') -> list:
    """把若干「小段列表」用分隔符串成一个小段列表。"""
    parts = []
    for chunk in chunks:
        chunk = [p for p in chunk if p]
        if not chunk:
            continue
        if parts:
            parts.append(_part(sep))
        parts.extend(chunk)
    return parts


def _seg_alert(seg: Optional[dict]) -> Optional[str]:
    if not seg:
        return None
    return _max_alert(*[p['alert'] for p in seg['parts'] if p['alert']])


def _segs_alert(segs: list) -> Optional[str]:
    return _max_alert(*[_seg_alert(s) for s in segs if s])


def _segs_text(segs: list, sep: str = '，') -> str:
    return sep.join(''.join(p['text'] for p in s['parts']) for s in segs if s)


def _segs_html(segs: list, sep: str = '，') -> str:
    chunks = []
    for s in segs:
        if not s:
            continue
        body = ''
        for p in s['parts']:
            text = html.escape(p['text'])
            body += (
                f'<span class="plain-val plain-val-{p["alert"]}">{text}</span>'
                if p['alert'] else text
            )
        chunks.append(body)
    return sep.join(chunks)


def _max_alert(*levels) -> Optional[str]:
    for level in ALERT_LEVELS:
        if level in levels:
            return level
    return None


# ── 数值/时间格式 ───────────────────────────────────────────────

def _fmt_num(value) -> str:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(num)) if num == int(num) else f'{num:g}'


def _shift_clock(day: int, hour: int, minute: int = 0) -> tuple[int, int, int]:
    """世界时日/时/分 → 当前显示时区的日/时/分（跨日按 31 日循环）。"""
    total = hour * 60 + minute + _tz_offset_hours() * 60
    extra, total = divmod(total, 24 * 60)
    hour, minute = divmod(total, 60)
    day = ((day - 1 + extra) % 31) + 1
    return day, hour, minute


def _ddhh_zh(ddhh) -> str:
    """``1006`` → ``10日06时``（UTC）或换算后的北京时；``100630`` 带分。"""
    text = str(ddhh or '').strip().upper().rstrip('Z')
    if len(text) == 4 and text.isdigit():
        day, hour, _ = _shift_clock(int(text[:2]), int(text[2:4]))
        return f'{day}日{hour:02d}时'
    if len(text) == 6 and text.isdigit():
        day, hour, minute = _shift_clock(int(text[:2]), int(text[2:4]), int(text[4:6]))
        return f'{day}日{hour:02d}时{minute:02d}分'
    return text


def _zulu_clock_zh(value, suffix: str) -> str:
    """``100630Z`` → ``10日06时30分观测/发布``，随显示时区换算。"""
    text = str(value or '').strip().upper()
    if text.endswith('Z'):
        text = text[:-1]
    if len(text) == 6 and text.isdigit():
        day, hour, minute = _shift_clock(int(text[:2]), int(text[2:4]), int(text[4:6]))
        return f'{day}日{hour:02d}时{minute:02d}分{suffix}'
    if len(text) == 4 and text.isdigit():
        return f'{_ddhh_zh(text)}{suffix}'
    return suffix


def _validity_zh(period: str) -> str:
    """``1106/1212`` → ``11日06时-12日12时``。"""
    text = str(period or '').strip()
    if '/' in text:
        start, _, end = text.partition('/')
        return f'{_ddhh_zh(start)}-{_ddhh_zh(end)}'
    return text


# ── 要素渲染 ────────────────────────────────────────────────────

def _wind_segs(wind: Optional[dict]) -> list:
    """``风向110°，平均风速12米/秒，阵风18米/秒``；风速与阵风各自按子告警着色。"""
    if not wind:
        return []
    direction = str(wind.get('direction') or '').strip().upper()
    speed = wind.get('speed')
    gust = wind.get('gust')
    unit = _SPEED_UNIT_ZH.get(str(wind.get('unit') or '').upper(), '米/秒')
    speed_alert = wind.get('speed_alert')
    gust_alert = wind.get('gust_alert')

    speed_text = _fmt_num(speed) if speed is not None else ''
    if speed_text == '0' and direction in ('000', '', 'VRB'):
        return [_seg(_part('静风', wind.get('alert')))]

    if direction == 'VRB':
        head = '风向不定'
    elif direction.isdigit():
        head = f'风向{int(direction):03d}°'
    elif direction:
        head = f'风向{direction}'
    else:
        head = ''

    chunks = [[_part(head)]]
    if speed_text:
        chunks.append([_part('平均风速'), _part(speed_text, speed_alert), _part(unit)])
    if gust is not None:
        chunks.append([_part('阵风'), _part(_fmt_num(gust), gust_alert), _part(unit)])
    parts = _join_parts(chunks)
    if not parts:
        return []

    variable = wind.get('variable') or None
    if variable and variable.get('from') is not None and variable.get('to') is not None:
        parts.append(_part(
            f'（风向{int(float(variable["from"])):03d}°至'
            f'{int(float(variable["to"])):03d}°变化）'
        ))
    return [_seg(*parts)]


def _visibility_segs(vis: Optional[dict]) -> list:
    if not vis:
        return []
    raw = str(vis.get('raw') or '').strip().upper()
    value = str(vis.get('value') if vis.get('value') is not None else raw).strip().upper()
    unit = str(vis.get('unit') or '').strip().upper()
    alert = vis.get('alert')

    if value == 'CAVOK':
        return [_seg(_part('天气良好（CAVOK）', alert))]
    if raw == 'CAVOK':
        # BECMG 继承来的 CAVOK 被本组天气/云顶替，生效值已转成 9999 / P6SM
        return [_seg('能见度', _part('10', alert), '公里以上（继承CAVOK）')]
    if value.startswith('P6'):
        return [_seg('能见度', _part('6', alert), '英里以上')]
    if value in ('9999', '10000'):
        return [_seg('能见度', _part('10', alert), '公里以上')]
    if value.replace('.', '', 1).isdigit():
        suffix = '英里' if unit == 'SM' else '米'
        return [_seg('能见度', _part(value, alert), suffix)]
    return [_seg('能见度', _part(value, alert))] if value else []


def _weather_segs(weather: Optional[dict]) -> list:
    """天气现象整词用自身告警色。"""
    items = (weather or {}).get('items') or []
    segs = []
    for item in items:
        code = str(item.get('code') or '').strip()
        if not code:
            continue
        segs.append(_seg(_part(weather_zh(code), item.get('alert'))))
    return [s for s in segs if s]


def _cloud_segs(clouds: Optional[dict]) -> list:
    if not clouds:
        return []
    segs = []
    sky = str(clouds.get('sky') or '').strip().upper()
    if sky in _SKY_ZH:
        segs.append(_seg(_SKY_ZH[sky]))
    for layer in clouds.get('layers') or []:
        cover = str(layer.get('cover') or '').strip().upper()
        cover_zh = _CLOUD_COVER_ZH.get(cover, cover)
        height = layer.get('height')
        try:
            feet = int(height) * 100 if height is not None else None
        except (TypeError, ValueError):
            feet = None
        cloud_type = str(layer.get('type') or '').strip().upper()
        tail = _CLOUD_TYPE_ZH.get(cloud_type, cloud_type) if cloud_type else ''
        if feet is not None:
            segs.append(_seg(
                cover_zh, _part(str(feet), layer.get('alert')), '英尺' + tail
            ))
        else:
            segs.append(_seg(_part(cover_zh + tail, layer.get('alert'))))
    return [s for s in segs if s]


def _wind_shear_segs(raw) -> list:
    text = str(raw or '').strip()
    if not text:
        return []
    return [_seg(_part(f'风切变（{text}）', 'R'))]


def _element_segs(block: Optional[dict]) -> list:
    """一个时段内的四类要素 + 风切变，按 风→能见度→天气→云 顺序。"""
    if not block:
        return []
    segs = []
    segs.extend(_wind_segs(block.get('wind')))
    segs.extend(_visibility_segs(block.get('visibility')))
    segs.extend(_weather_segs(block.get('weather')))
    segs.extend(_cloud_segs(block.get('clouds')))
    segs.extend(_wind_shear_segs(block.get('wind_shear')))
    return segs


def _temperature_segs(temperatures: Optional[list]) -> list:
    segs = []
    for item in temperatures or []:
        value = str(item.get('value') or '').strip()
        if not value:
            continue
        name = '最高气温' if item.get('kind') == 'max' else '最低气温'
        value_zh = value.replace('M', '-') if value.upper().startswith('M') else value
        moment = _ddhh_zh(item.get('time'))
        tail = f'℃（{moment}）' if moment else '℃'
        segs.append(_seg(name, _part(value_zh, item.get('alert')), tail))
    return [s for s in segs if s]


# ── 时段标题 ────────────────────────────────────────────────────

def _change_label(block: dict) -> tuple[str, str]:
    """返回 (时段, 变化组说法)。"""
    raw_type = str(block.get('type') or '').strip().upper().replace(' ', '')
    start = _ddhh_zh(block.get('start'))
    end = _ddhh_zh(block.get('end'))
    transition = _ddhh_zh(block.get('transition_start'))

    if raw_type.startswith('PROB'):
        digits = re.sub(r'\D', '', raw_type) or str(block.get('probability') or '')
        word = f'{digits}%概率出现' if digits else '概率出现'
    else:
        word = _CHANGE_ZH.get(raw_type, raw_type or '')

    if raw_type in ('FROM', 'FM') or raw_type.startswith('FM'):
        return start, word
    if raw_type == 'BECMG':
        span = f'{transition}-{start}' if transition and start else (start or transition)
        return span, word
    span = f'{start}-{end}' if start and end else (start or end)
    return span, word


def _period_line(span: str, word: str, segs: list) -> dict:
    body_text = _segs_text(segs)
    head = f'{span}{word}' if span else word
    return {
        'span': span,
        'word': word,
        'alert': _segs_alert(segs),
        'text': f'{head}：{body_text}' if body_text else f'{head}：无要素',
        'body_html': _segs_html(segs) or '无要素',
    }


def _period_cells(line: dict) -> str:
    """四列网格的一行：告警圆点 / 时段 / 变化性质 / 要素内容。"""
    level = line.get('alert') or 'N'
    return (
        f'<span class="plain-dot plain-dot-{level}"></span>'
        f'<span class="plain-span">{html.escape(line.get("span") or "")}</span>'
        f'<span class="plain-word">{html.escape(line.get("word") or "")}</span>'
        f'<span class="plain-elements">{line.get("body_html") or ""}</span>'
    )


# ── 入口一：入库列 taf_elements ─────────────────────────────────

def translate_taf_elements(elements: Optional[dict]) -> Optional[dict]:
    """``taf.taf_elements`` → 中文明语结构。

    返回 ``None`` 表示该列为空（占位行或迁移前的历史行）。
    """
    if not elements:
        return None

    airport = elements.get('airport') or ''
    header_bits = [f'预报 {airport}'.strip()]
    issue = str(elements.get('issue_time_z') or '').strip()
    if len(issue) == 7 and issue.endswith('Z'):
        header_bits.append(_zulu_clock_zh(issue, '发布'))
    validity = _validity_zh(elements.get('whole_validity'))
    if validity:
        header_bits.append(f'有效期{validity}')
    if elements.get('amended'):
        header_bits.append('修订报')
    if elements.get('corrected'):
        header_bits.append('更正报')

    result = {
        'airport': airport,
        'header': '，'.join(bit for bit in header_bits if bit),
        'cancelled': bool(elements.get('cancelled')),
        'periods': [],
        'temperatures': [],
        'bars': {},
        'html': '',
        'text': '',
    }

    if elements.get('cancelled'):
        result['periods'] = [{
            'span': validity,
            'word': '取消',
            'alert': None,
            'text': '该份预报已取消（CNL）',
            'body_html': '该份预报已取消（CNL）',
        }]
        result['bars']['SUBJECT'] = result['periods'][0]
    else:
        subject = elements.get('subject')
        if subject:
            period = elements.get('subject_period') or {}
            span = ''
            if period.get('start'):
                span = _ddhh_zh(period.get('start'))
                if period.get('end'):
                    span += f'-{_ddhh_zh(period.get("end"))}'
            line = _period_line(span, '主预报', _element_segs(subject))
            line['alert'] = _max_alert(line['alert'], subject.get('warning'))
            result['periods'].append(line)
            result['bars']['SUBJECT'] = line

        for block in elements.get('changes') or []:
            span, word = _change_label(block)
            line = _period_line(span, word, _element_segs(block))
            line['alert'] = _max_alert(line['alert'], block.get('warning'))
            result['periods'].append(line)
            key = _bar_key(block)
            if key:
                result['bars'].setdefault(key, line)

    temp_segs = _temperature_segs(elements.get('temperatures'))
    result['temperatures'] = [
        {'text': _segs_text([s]), 'alert': _seg_alert(s)} for s in temp_segs
    ]
    cells = ''.join(_period_cells(line) for line in result['periods'])
    if temp_segs:
        cells += f'<span class="plain-temps">{_segs_html(temp_segs, sep="　")}</span>'
    result['html'] = f'<span class="plain-periods">{cells}</span>'
    result['text'] = '；'.join(line['text'] for line in result['periods'])
    return result


def _bar_key(block: dict) -> str:
    """甘特条带查表键：与前端 ``change_i_type`` + ``validity_period_start`` 对应。"""
    raw_type = str(block.get('type') or '').strip().upper().replace(' ', '')
    start = str(block.get('start') or '').strip()
    if not raw_type or not start:
        return ''
    return f'{raw_type}|{start}'


def translate_taf_row(row: Any) -> Optional[dict]:
    """接受 Taf 实例或含 ``taf_elements`` 的 dict。"""
    if row is None:
        return None
    elements = row.get('taf_elements') if isinstance(row, dict) else getattr(row, 'taf_elements', None)
    if isinstance(elements, str):
        import json
        try:
            elements = json.loads(elements)
        except (TypeError, ValueError):
            return None
    return translate_taf_elements(elements)


def translate_metar_row(row: Any) -> Optional[dict]:
    """接受 Metar 实例或含 ``metar_elements`` 的 dict。"""
    if row is None:
        return None
    elements = row.get('metar_elements') if isinstance(row, dict) else getattr(row, 'metar_elements', None)
    if isinstance(elements, str):
        import json
        try:
            elements = json.loads(elements)
        except (TypeError, ValueError):
            return None
    return translate_metar_elements(elements)


def _obs_head_zh(elements: dict) -> str:
    issue = str(elements.get('observation_time_z') or '').strip()
    if len(issue) == 7 and issue.endswith('Z'):
        return _zulu_clock_zh(issue, '观测')
    return '观测'


def _wind_compact_segs(wind: Optional[dict]) -> list:
    """详情甘特左侧短句：风向110°，风速12，阵风18米/秒。"""
    if not wind:
        return []
    direction = str(wind.get('direction') or '').strip().upper()
    speed = wind.get('speed')
    gust = wind.get('gust')
    unit = _SPEED_UNIT_ZH.get(str(wind.get('unit') or '').upper(), '米/秒')
    speed_alert = wind.get('speed_alert')
    gust_alert = wind.get('gust_alert')
    speed_text = _fmt_num(speed) if speed is not None else ''
    if speed_text == '0' and direction in ('000', '', 'VRB'):
        return [_seg(_part('静风', wind.get('alert')))]

    if direction == 'VRB':
        head = '风向不定'
    elif direction.isdigit():
        head = f'风向{int(direction):03d}°'
    elif direction:
        head = f'风向{direction}'
    else:
        head = ''

    chunks = [[_part(head)]] if head else []
    if speed_text and gust is not None:
        chunks.append([_part('风速'), _part(speed_text, speed_alert)])
        chunks.append([_part('阵风'), _part(_fmt_num(gust), gust_alert), _part(unit)])
    elif speed_text:
        chunks.append([_part('风速'), _part(speed_text, speed_alert), _part(unit)])
    elif gust is not None:
        chunks.append([_part('阵风'), _part(_fmt_num(gust), gust_alert), _part(unit)])
    parts = _join_parts(chunks)
    return [_seg(*parts)] if parts else []


def _rvr_element_segs(items: Optional[list]) -> list:
    segs = []
    for item in items or []:
        value = item.get('value')
        if value is None:
            continue
        runway = str(item.get('runway') or '').strip()
        head = f'{runway}跑道视程' if runway else '跑道视程'
        segs.append(_seg(head, _part(_fmt_num(value), item.get('alert')), '米'))
    return segs


def translate_metar_elements(elements: Optional[dict]) -> Optional[dict]:
    """``metar.metar_elements`` → 列表行全文 + 详情甘特左侧短句。"""
    if not elements:
        return None

    segs = []
    segs.extend(_wind_segs(elements.get('wind')))
    segs.extend(_visibility_segs(elements.get('visibility')))
    segs.extend(_weather_segs(elements.get('weather')))
    segs.extend(_cloud_segs(elements.get('clouds')))
    segs.extend(_rvr_element_segs(elements.get('rvr')))
    temp = elements.get('temperature') or {}
    if temp.get('value') is not None:
        segs.append(_seg('气温', _part(_fmt_num(temp['value']), temp.get('alert')), '℃'))
    dew = elements.get('dewpoint') or {}
    if dew.get('value') is not None:
        segs.append(_seg(f'露点{_fmt_num(dew["value"])}℃'))
    alt = elements.get('altimeter') or {}
    if alt.get('value') is not None:
        suffix = '英寸汞柱' if str(alt.get('unit') or '') in ('inHg', 'inhg', 'in') else '百帕'
        segs.append(_seg(f'修正海压{_fmt_num(alt["value"])}{suffix}'))
    segs.extend(_wind_shear_segs(elements.get('wind_shear')))
    if elements.get('nosig'):
        segs.append(_seg('未来2小时无重要变化'))

    head = _obs_head_zh(elements)
    body = _segs_html(segs) or '无可翻译要素'
    html_line = (
        '<span class="plain-metar-line">'
        f'<span class="plain-metar-head">{html.escape(head)}</span>'
        f'<span class="plain-elements">{body}</span>'
        '</span>'
    )

    compact_parts = []
    compact_parts.extend(_wind_compact_segs(elements.get('wind')))
    compact_parts.extend(_visibility_segs(elements.get('visibility')))
    compact_parts.extend(_rvr_element_segs(elements.get('rvr')))
    wx_segs = _weather_segs(elements.get('weather'))
    compact_parts.extend(wx_segs or [_seg('无重要天气现象')])
    clouds = elements.get('clouds') or {}
    layers_only = dict(clouds)
    layers_only['sky'] = None
    layer_segs = _cloud_segs(layers_only)[:3]
    if layer_segs:
        compact_parts.extend(layer_segs)
    else:
        compact_parts.extend(_cloud_segs(clouds)[:1])
    compact_html = '<br>'.join(
        _segs_html([s]) for s in compact_parts if s
    )

    return {
        'airport': elements.get('airport'),
        'alert': elements.get('warning'),
        'html': html_line,
        'compact_html': compact_html,
        'text': f'{head}：{_segs_text(segs)}',
    }


# ── 入口二：avwx 现场解析（详情页原文中文化） ───────────────────

def build_airport_detail_plain_reports(
    airport_code: str,
    time_mode: str = 'current',
    token: Optional[str] = None,
) -> dict:
    """与 ``build_airport_detail_reports`` 同一批原文，输出中文明语。"""
    from parsers.metar_history import fetch_raw_met_list
    from parsers.metar_parser import MetarParser
    from parsers.report_text_highlight import select_taf_reports

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
                'html': metar_plain_html(item['content'], airport_code, thresholds, parser),
            }
            for item in metars
        ],
        'taf_reports': [
            {
                'content': item['content'],
                'wtype': item.get('wtype'),
                'html': taf_plain_html(item['content'], airport_code, thresholds, parser),
            }
            for item in tafs
        ],
    }


def metar_plain_html(content: str, airport_code: str, thresholds: dict, parser) -> str:
    if not content:
        return ''
    from parsers.report_text_highlight import _parse_avwx_metar

    try:
        data, units, is_na = _parse_avwx_metar(content, airport_code)
    except Exception as exc:
        logger.debug(f'实况明语 avwx 解析失败 [{airport_code}]: {exc}')
        return html.escape(content)
    if data is None or units is None:
        return html.escape(content)

    segs = []
    segs.extend(_wind_segs(_avwx_wind(data, units, thresholds, parser)))
    segs.extend(_visibility_segs(_avwx_visibility(data.visibility, units, thresholds, parser)))
    segs.extend(_weather_segs(_avwx_weather(getattr(data, 'wx_codes', None), parser)))
    segs.extend(_cloud_segs(_avwx_clouds(getattr(data, 'clouds', None), data, thresholds, parser)))
    segs.extend(_avwx_rvr_segs(data, is_na, thresholds, parser))
    segs.extend(_avwx_temp_segs(data, thresholds))
    segs.extend(_avwx_altimeter_segs(data, units))
    segs.extend(_metar_trend_segs(content))

    head = _metar_head(airport_code, data)
    body = _segs_html(segs) or '无可翻译要素'
    return (
        '<span class="plain-metar-line">'
        f'<span class="plain-metar-head">{html.escape(head)}</span>'
        f'<span class="plain-elements">{body}</span>'
        '</span>'
    )


def taf_plain_html(content: str, airport_code: str, thresholds: dict, parser) -> str:
    """按 avwx 拆出的时段逐行输出中文，与原文着色排版保持一致的两列网格。"""
    if not content:
        return ''
    from parsers.report_text_highlight import _taf_display_periods

    try:
        from avwx_custom import Taf as AvwxTaf
        from avwx_custom.exceptions import BadStation

        station = airport_code
        try:
            taf = AvwxTaf(station)
        except BadStation:
            words = content.split()
            station = next(
                (
                    w.upper() for w in words
                    if len(w) == 4 and w.isalpha() and w.upper() not in ('TAF', 'AMD', 'COR')
                ),
                airport_code,
            )
            taf = AvwxTaf(station)
        parsed = taf.parse(content)
        forecast = list(taf.data.forecast) if (parsed and taf.data) else []
        units = taf.units if parsed else None
    except Exception as exc:
        logger.debug(f'预报明语 avwx 解析失败 [{airport_code}]: {exc}')
        forecast, units = [], None

    try:
        periods = _taf_display_periods(content) or [content]
    except Exception:
        periods = [content]

    rows = ['<span class="plain-periods">']
    for index, raw in enumerate(periods):
        line = forecast[index] if index < len(forecast) else None
        if line is None or units is None:
            rows.append(_period_cells({
                'span': '',
                'word': '预报' if index == 0 else '变化组',
                'alert': None,
                'body_html': html.escape(raw or ''),
            }))
            continue
        block = _avwx_taf_block(line, units, thresholds, parser, is_first=index == 0)
        segs = _element_segs(block)
        segs.extend(_taf_temp_segs(raw or '', thresholds))
        if index == 0:
            span, word = _validity_zh(_avwx_line_span(line)), '主预报'
        else:
            span, word = _change_label(block)
        rows.append(_period_cells({
            'span': span,
            'word': word,
            'alert': _segs_alert(segs),
            'body_html': _segs_html(segs) or '无要素',
        }))
    rows.append('</span>')
    return ''.join(rows)


# ── avwx → 统一要素块 ──────────────────────────────────────────

def _avwx_line_span(line) -> str:
    start = _avwx_ddhh(getattr(line, 'start_time', None))
    end = _avwx_ddhh(getattr(line, 'end_time', None))
    if start and end:
        return f'{start}/{end}'
    return start or end or ''


def _avwx_ddhh(value) -> str:
    dt = getattr(value, 'dt', None) if value is not None else None
    return dt.strftime('%d%H') if dt is not None else ''


def _avwx_taf_block(line, units, thresholds, parser, is_first: bool) -> dict:
    raw_type = str(getattr(line, 'type', '') or '').strip().upper().replace(' ', '')
    probability = getattr(getattr(line, 'probability', None), 'value', None)
    return {
        'type': raw_type,
        'probability': probability,
        'transition_start': _avwx_ddhh(getattr(line, 'transition_start', None)),
        'start': _avwx_ddhh(getattr(line, 'start_time', None)),
        'end': '' if is_first else _avwx_ddhh(getattr(line, 'end_time', None)),
        'wind': _avwx_wind(line, units, thresholds, parser),
        'visibility': _avwx_visibility(getattr(line, 'visibility', None), units, thresholds, parser),
        'weather': _avwx_weather(getattr(line, 'wx_codes', None), parser),
        'clouds': _avwx_clouds(getattr(line, 'clouds', None), line, thresholds, parser),
        'wind_shear': str(getattr(line, 'wind_shear', '') or '') or None,
    }


def _avwx_wind(holder, units, thresholds, parser) -> Optional[dict]:
    from parsers.report_text_highlight import _wind_alert_level, _wind_to_mps

    speed_obj = getattr(holder, 'wind_speed', None)
    gust_obj = getattr(holder, 'wind_gust', None)
    dir_obj = getattr(holder, 'wind_direction', None)
    if speed_obj is None and dir_obj is None:
        return None
    speed = getattr(speed_obj, 'value', None)
    gust = getattr(gust_obj, 'value', None)
    if speed is None and gust is None and getattr(dir_obj, 'repr', None) is None:
        return None

    direction = getattr(dir_obj, 'value', None)
    if direction is not None:
        try:
            direction = str(int(float(direction))).zfill(3)
        except (TypeError, ValueError):
            direction = getattr(dir_obj, 'repr', None)
    else:
        direction = getattr(dir_obj, 'repr', None)

    unit = str(getattr(units, 'wind_speed', '') or '').upper()
    unit = {'KT': 'KT', 'M/S': 'MPS', 'MPS': 'MPS', 'KMH': 'KMH'}.get(unit, unit)

    variable = None
    vardir = getattr(holder, 'wind_variable_direction', None) or []
    if len(vardir) >= 2:
        variable = {
            'from': getattr(vardir[0], 'value', None),
            'to': getattr(vardir[1], 'value', None),
        }
    # 平均风与阵风各判一次，翻译时只给数值本身着色
    speed_mps = _wind_to_mps(speed, getattr(units, 'wind_speed', None))
    gust_mps = _wind_to_mps(gust, getattr(units, 'wind_speed', None))
    speed_alert = parser._get_alert_level(
        speed_mps, thresholds.get('wind_red'), thresholds.get('wind_yellow'),
        thresholds.get('wind_green'),
    ) if speed_mps is not None else None
    gust_alert = parser._get_alert_level(
        gust_mps, thresholds.get('gust_red'), thresholds.get('gust_yellow'),
        thresholds.get('gust_green'),
    ) if gust_mps is not None else None
    return {
        'direction': direction,
        'speed': speed,
        'gust': gust,
        'unit': unit,
        'variable': variable,
        'alert': _wind_alert_level(speed_obj, gust_obj, units, thresholds, parser),
        'speed_alert': speed_alert,
        'gust_alert': gust_alert,
    }


def _avwx_visibility(vis, units, thresholds, parser) -> Optional[dict]:
    if vis is None:
        return None
    from parsers.metar_history import _visibility_to_m

    raw = str(getattr(vis, 'repr', '') or '').strip()
    if not raw:
        return None
    if raw == 'CAVOK' or raw.startswith('P6'):
        meters = 10000
    else:
        meters = _visibility_to_m(getattr(vis, 'value', None), getattr(units, 'visibility', None))
    alert = parser._get_alert_level(
        meters,
        thresholds.get('visibility_red'),
        thresholds.get('visibility_yellow'),
        thresholds.get('visibility_green'),
        reverse=True,
    )
    unit = str(getattr(units, 'visibility', '') or '').upper()
    return {
        'raw': raw,
        'value': raw,
        'unit': 'SM' if unit == 'SM' else 'm',
        'cavok': raw == 'CAVOK',
        'alert': alert,
    }


def _avwx_weather(wx_codes, parser) -> dict:
    items = []
    warning = None
    for code in wx_codes or []:
        token = str(getattr(code, 'repr', '') or '').strip()
        if not token:
            continue
        level, _types = parser._get_weather_alert_level_single(token)
        items.append({'code': token, 'alert': level})
        warning = _max_alert(warning, level)
    return {'items': items, 'warning': warning}


def _avwx_clouds(clouds, holder, thresholds, parser) -> dict:
    layers = []
    warning = None
    vv = getattr(holder, 'vertical_visibility', None)
    vv_value = getattr(vv, 'value', None) if vv is not None else None
    if vv_value is not None:
        level = parser._get_alert_level(
            vv_value, thresholds.get('cloud_red'), thresholds.get('cloud_yellow'),
            thresholds.get('cloud_green'), reverse=True,
        )
        layers.append({'cover': 'VV', 'height': vv_value, 'type': None, 'alert': level})
        warning = _max_alert(warning, level)
    for cloud in clouds or []:
        cover = str(getattr(cloud, 'type', '') or '').strip().upper()
        base = getattr(cloud, 'base', None)
        level = None
        if base is not None:
            level = parser._get_alert_level(
                base, thresholds.get('cloud_red'), thresholds.get('cloud_yellow'),
                thresholds.get('cloud_green'), reverse=True,
            )
            warning = _max_alert(warning, level)
        if not cover and base is None:
            continue
        layers.append({
            'cover': cover,
            'height': base,
            'type': str(getattr(cloud, 'modifier', '') or '').strip().upper() or None,
            'alert': level,
        })
    sky = None
    for token in (str(item).upper() for item in (getattr(holder, 'other', None) or [])):
        if token in _SKY_ZH:
            sky = token
            break
    return {'sky': sky, 'layers': layers, 'warning': warning}


def _avwx_rvr_segs(data, is_na: bool, thresholds: dict, parser) -> list:
    from parsers.report_text_highlight import _rvr_numeric

    segs = []
    for rvr in getattr(data, 'runway_visibility', None) or []:
        raw = str(getattr(rvr, 'repr', '') or '').strip()
        if not raw:
            continue
        values = [_rvr_numeric(getattr(rvr, 'visibility', None), is_na)]
        for var in getattr(rvr, 'variable_visibility', None) or []:
            values.append(_rvr_numeric(var, is_na))
        valid = [v for v in values if v is not None]
        if not valid:
            continue
        level = parser._get_alert_level(
            min(valid), thresholds.get('rvr_red'), thresholds.get('rvr_yellow'),
            thresholds.get('rvr_green'), reverse=True,
        )
        runway = str(getattr(getattr(rvr, 'runway', None), 'repr', '') or '').strip()
        head = f'{runway}跑道视程' if runway else '跑道视程'
        segs.append(_seg(head, _part(str(min(valid)), level), '米'))
    return [s for s in segs if s]


def _avwx_temp_segs(data, thresholds: dict) -> list:
    from parsers.report_text_highlight import _temp_value_level

    segs = []
    temp = getattr(data, 'temperature', None)
    if temp is not None and getattr(temp, 'value', None) is not None:
        level = _temp_value_level(float(temp.value), thresholds)
        segs.append(_seg('气温', _part(_fmt_num(temp.value), level), '℃'))
    dew = getattr(data, 'dewpoint', None)
    if dew is not None and getattr(dew, 'value', None) is not None:
        segs.append(_seg(f'露点{_fmt_num(dew.value)}℃'))
    return [s for s in segs if s]


def _avwx_altimeter_segs(data, units) -> list:
    alt = getattr(data, 'altimeter', None)
    value = getattr(alt, 'value', None) if alt is not None else None
    if value is None:
        return []
    unit = str(getattr(units, 'altimeter', '') or '').lower()
    suffix = '英寸汞柱' if unit in ('inhg', 'in') else '百帕'
    return [_seg(f'修正海压{_fmt_num(value)}{suffix}')]


def _metar_trend_segs(content: str) -> list:
    body = content.split(' RMK')[0]
    segs = []
    if re.search(r'\bNOSIG\b', body, re.IGNORECASE):
        segs.append(_seg('未来2小时无重要变化'))
    for match in _METAR_WS_RE.finditer(body):
        segs.append(_seg(_part(f'风切变（{match.group().strip()}）', 'R')))
    trend = _TREND_RE.search(body)
    if trend:
        segs.append(_seg(_part(f'趋势：{trend.group().strip()}', 'R')))
    return [s for s in segs if s]


def _metar_head(airport_code: str, data) -> str:
    time_obj = getattr(data, 'time', None)
    dt = getattr(time_obj, 'dt', None) if time_obj is not None else None
    if dt is not None:
        offset = _tz_offset_hours()
        if offset:
            dt = dt + timedelta(hours=offset)
        return f'{dt.day}日{dt.strftime("%H时%M分")}观测'
    return '观测'


def _taf_temp_segs(raw: str, thresholds: dict) -> list:
    from parsers.report_text_highlight import _temp_value_level

    segs = []
    for match in _TX_TN_RE.finditer(raw or ''):
        kind, value, moment = match.group(1).upper(), match.group(2).upper(), match.group(3)
        try:
            temp_val = -int(value[1:]) if value.startswith('M') else int(value)
        except ValueError:
            continue
        name = '最高气温' if kind == 'X' else '最低气温'
        level = _temp_value_level(float(temp_val), thresholds)
        segs.append(_seg(name, _part(str(temp_val), level), f'℃（{_ddhh_zh(moment)}）'))
    return [s for s in segs if s]
