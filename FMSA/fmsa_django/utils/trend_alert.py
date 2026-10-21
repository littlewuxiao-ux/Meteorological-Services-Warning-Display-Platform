"""实况趋势告警：规则校验与按实况序列计分。

常规要素的下降与时段内最高值比较，上升与时段内最低值比较。
云量、云高、天气现象的「由 / 过去出现」看时段内是否有一份满足，含特殊报。
时序里天气现象和云量在条件命中后单独成行，格子取该窗口内最早一份自身符合条件的报文。
"""

from __future__ import annotations

import math
import re
import time
import uuid
from typing import Any, Optional

ELEMENTS = (
    'temperature', 'dewpoint', 'rh', 'pressure', 'wind', 'visibility', 'spread',
)
ELEMENT_LABELS = {
    'temperature': '气温',
    'dewpoint': '露点温度',
    'rh': '相对湿度',
    'pressure': '气压',
    'wind': '风速',
    'visibility': '能见度',
    'spread': '温度露点差',
}
ELEMENT_UNITS = {
    'temperature': '℃',
    'dewpoint': '℃',
    'rh': '%',
    'pressure': 'hPa',
    'wind': 'm/s',
    'visibility': 'm',
    'spread': '℃',
}
COVERS = ('NSC', 'FEW', 'SCT', 'BKN', 'OVC')
COVER_RANK = {'FEW': 1, 'SCT': 2, 'BKN': 3, 'OVC': 4}
CLEAR_SKY = {'NSC', 'SKC', 'CLR', 'NCD'}
ROW_ORDER = (
    'temperature', 'dewpoint', 'rh', 'pressure', 'wind', 'visibility', 'spread',
    'weather', 'cover', 'height',
)
ROW_LABELS = {
    **{k: f'{v}({ELEMENT_UNITS[k]})' for k, v in ELEMENT_LABELS.items()},
    'weather': '天气现象',
    'cover': '云量',
    'height': '云高(百英尺)',
}
COLOR_RANK = {'G': 1, 'Y': 2, 'R': 3}
HOUR_MS = 3600 * 1000
DAY_MS = 24 * HOUR_MS
MAX_HOURS = 72
EXTRA_SCORE_CAP = 3
SLOT_WINDOW_MS = 10 * 60 * 1000
_CLOUD_RE = re.compile(r'\b(VV|FEW|SCT|BKN|OVC|NSC|SKC|CLR|NCD)(\d{3})?\b', re.I)
_QNH_RE = re.compile(r'\bQ(\d{4})\b')
_ALTIMETER_RE = re.compile(r'\bA(\d{4})\b')


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def default_config() -> dict:
    return {'groups': [], 'alarm_colors': ['R', 'Y', 'G']}


def alarm_colors_of(raw) -> list:
    """导航计入的颜色。没配过时红黄绿都计入。勾绿含黄和红，勾黄含红。"""
    if not isinstance(raw, dict) or 'alarm_colors' not in raw:
        return ['R', 'Y', 'G']
    picked = [color for color in ('R', 'Y', 'G') if color in set(raw.get('alarm_colors') or [])]
    if 'G' in picked:
        return ['R', 'Y', 'G']
    if 'Y' in picked:
        return ['R', 'Y']
    if 'R' in picked:
        return ['R']
    return []


def _num(value) -> Optional[float]:
    if value is None or value == '':
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _bool(value, default=False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def _split_commas(text: str) -> list:
    parts = re.split(r'[,，]+', str(text or ''))
    return [p.strip() for p in parts if p.strip()]


def _split_codes(value) -> list:
    """逗号分隔的文字，或已经存成列表的云量、天气现象代码。"""
    if isinstance(value, (list, tuple)):
        codes = []
        for item in value:
            for code in _split_codes(item):
                if code not in codes:
                    codes.append(code)
        return codes
    text = str(value or '').replace('[', ',').replace(']', ',').replace("'", '').replace('"', '')
    codes = []
    for part in _split_commas(text):
        code = part.strip().upper()
        if code and code not in codes:
            codes.append(code)
    return codes


def relative_humidity(temp_c: Optional[float], dew_c: Optional[float]) -> Optional[float]:
    if temp_c is None or dew_c is None:
        return None
    if temp_c <= -243 or dew_c <= -243:
        return None

    def saturation(temp):
        return math.exp((17.625 * temp) / (temp + 243.04))

    rh = 100.0 * saturation(dew_c) / saturation(temp_c)
    return max(0.0, min(100.0, rh))


def _parse_dewpoint(raw) -> Optional[float]:
    if raw is None:
        return None
    text = str(raw).strip().upper()
    if not text or text in ('NONE', 'NULL', '//', 'M//'):
        return None
    sign = 1
    if text.startswith('M'):
        sign = -1
        text = text[1:]
    elif text.startswith('-'):
        sign = -1
        text = text[1:]
    try:
        return sign * float(text)
    except ValueError:
        return None


def _pressure_hpa(elements: Optional[dict], content: str) -> Optional[float]:
    alt = (elements or {}).get('altimeter') if isinstance(elements, dict) else None
    if isinstance(alt, dict) and alt.get('value') is not None:
        value = _num(alt.get('value'))
        unit = str(alt.get('unit') or '').lower()
        if value is None:
            return None
        if unit in ('inhg', 'in'):
            return value * 33.8638866667
        if unit == 'hpa':
            return value
        if value < 50:
            return value * 33.8638866667
        return value
    text = content or ''
    qnh = _QNH_RE.search(text)
    if qnh:
        return float(qnh.group(1))
    inches = _ALTIMETER_RE.search(text)
    if inches:
        return int(inches.group(1)) / 100.0 * 33.8638866667
    return None


def _weather_codes(elements: Optional[dict], raw: Optional[str]) -> list:
    codes = []
    weather = (elements or {}).get('weather') if isinstance(elements, dict) else None
    items = weather.get('items') if isinstance(weather, dict) else None
    if isinstance(items, list):
        for item in items:
            token = str((item or {}).get('code') or '').strip().upper()
            if token and token != 'NSW':
                codes.append(token)
    if codes:
        return codes
    for token in re.split(r'\s+', str(raw or '').strip().upper()):
        if token and token != 'NSW':
            codes.append(token)
    return codes


def _cover_marks(layers) -> list:
    marks = []
    for layer in layers:
        cover = str((layer or {}).get('cover') or '').strip().upper()
        if cover in ('FEW', 'SCT', 'BKN', 'OVC') and cover not in marks:
            marks.append(cover)
    return marks


def _cloud_state(elements: Optional[dict], cloud_text: Optional[str], min_height) -> dict:
    layers = []
    sky = None
    clouds = (elements or {}).get('clouds') if isinstance(elements, dict) else None
    if isinstance(clouds, dict):
        sky = str(clouds.get('sky') or '').strip().upper() or None
        raw_layers = clouds.get('layers')
        if isinstance(raw_layers, list):
            for layer in raw_layers:
                if not isinstance(layer, dict):
                    continue
                layers.append({
                    'cover': str(layer.get('cover') or '').strip().upper(),
                    'height': _num(layer.get('height')),
                })
    if not layers and not sky:
        for match in _CLOUD_RE.finditer(str(cloud_text or '')):
            cover = match.group(1).upper()
            height = int(match.group(2)) if match.group(2) else None
            if cover in CLEAR_SKY:
                sky = cover
            else:
                layers.append({'cover': cover, 'height': height})
    ranked = [COVER_RANK[layer['cover']] for layer in layers if layer['cover'] in COVER_RANK]
    heights = [layer['height'] for layer in layers if layer['height'] is not None and layer['cover'] in COVER_RANK]
    if not heights:
        vv_heights = [layer['height'] for layer in layers if layer['cover'] == 'VV' and layer['height'] is not None]
        heights = vv_heights
    if ranked:
        best = max(ranked)
        cover = next(name for name, rank in COVER_RANK.items() if rank == best)
        base = min(heights) if heights else _num(min_height)
        return {'cover': cover, 'base': base, 'nsc': False, 'covers': _cover_marks(layers)}
    base = _num(min_height)
    marks = _cover_marks(layers) or ['NSC']
    if base is not None:
        return {'cover': 'NSC', 'base': base, 'nsc': False, 'covers': marks}
    return {'cover': 'NSC', 'base': None, 'nsc': True, 'covers': marks}


def snapshot_from_row(row: dict) -> Optional[dict]:
    observed = row.get('metar_observation_time')
    if observed is None:
        return None
    elements = row.get('metar_elements')
    if isinstance(elements, str):
        elements = None
    content = row.get('metar_content') or ''
    kind = str(row.get('metar_type') or '').strip().upper()
    if not kind and str(content).lstrip().upper().startswith('SPECI'):
        kind = 'SPECI'
    temp = _num(row.get('metar_temp_val'))
    if temp is None and isinstance(elements, dict):
        temp = _num((elements.get('temperature') or {}).get('value'))
    dew = None
    if isinstance(elements, dict):
        dew = _num((elements.get('dewpoint') or {}).get('value'))
    if dew is None:
        dew = _parse_dewpoint(row.get('metar_dew_point'))
    wind = _num(row.get('metar_wind_speed_val'))
    visibility = _num(row.get('metar_visibility_val'))
    if isinstance(elements, dict) and (wind is None or visibility is None):
        from parsers.metar_history import _visibility_to_m, _wind_to_mps
        if wind is None:
            wind_el = elements.get('wind') or {}
            unit = str(wind_el.get('unit') or '').upper()
            mapped = {'KT': 'kt', 'MPS': 'm/s', 'M/S': 'm/s', 'KMH': 'km/h'}.get(unit, 'm/s')
            wind = _wind_to_mps(wind_el.get('speed'), mapped)
        if visibility is None:
            vis = elements.get('visibility') or {}
            unit = str(vis.get('unit') or 'm').lower()
            visibility = _visibility_to_m(vis.get('value'), 'sm' if unit == 'sm' else 'm')
    cloud = _cloud_state(elements, row.get('metar_cloud'), row.get('metar_min_cloud_height'))
    return {
        'time': int(observed),
        'sa': kind == 'SA',
        'speci': 'SPECI' in kind or kind == 'SP',
        'temperature': temp,
        'dewpoint': dew,
        'rh': relative_humidity(temp, dew),
        'pressure': _pressure_hpa(elements if isinstance(elements, dict) else None, content),
        'wind': wind,
        'visibility': visibility,
        'weather': _weather_codes(elements if isinstance(elements, dict) else None, row.get('metar_weather')),
        'cover': cloud['cover'],
        'covers': cloud.get('covers') or [],
        'base': cloud['base'],
        'nsc': cloud['nsc'],
    }


def _element_value(obs: dict, name: str):
    if name == 'spread':
        temp = obs.get('temperature')
        dew = obs.get('dewpoint')
        if temp is None or dew is None:
            return None
        return temp - dew
    return obs.get(name)


def _window_start(obs: list, boundary: int) -> Optional[dict]:
    found = None
    for item in obs:
        if item['time'] <= boundary:
            found = item
        else:
            break
    return found


def _in_past_window(obs: list, begin: int, end: int) -> list:
    return [item for item in obs if begin <= item['time'] <= end]


def _height_side(obs: Optional[dict], threshold, cmp: str, allow_nsc: bool) -> bool:
    """没填数字且勾选可为空或 NSC 时，只接受没有云。填了数字再勾选，则数字条件或无云都通过。"""
    if obs is None:
        return False
    clear = bool(obs.get('nsc') or obs.get('base') is None)
    numbered = threshold is not None and cmp in ('below', 'above')
    if not numbered:
        return bool(allow_nsc and clear)
    if clear:
        return bool(allow_nsc)
    if cmp == 'below':
        return obs['base'] <= threshold
    return obs['base'] >= threshold


def _condition_sides(cond: dict, obs: list, now_ms: int):
    """返回 (过去是否成立, 当前是否成立)。没勾的一侧是 None。"""
    if len(obs) < 1:
        return None, None
    current = obs[-1]
    use_change = bool(cond.get('use_change'))
    use_current = bool(cond.get('use_current'))
    hours = _num(cond.get('hours')) or 0
    begin = int(now_ms - hours * HOUR_MS)
    kind = cond.get('kind')
    change_ok = None
    current_ok = None

    if kind == 'element':
        direction = cond.get('direction')
        if use_change:
            amount = _num(cond.get('change_amount'))
            element = cond.get('change_element')
            change_ok = False
            if amount is not None:
                values = []
                for item in _in_past_window(obs, begin, now_ms):
                    value = _element_value(item, element)
                    if value is not None:
                        values.append(value)
                after = _element_value(current, element)
                if values and after is not None:
                    change_op = cond.get('change_op') or '>='
                    if direction == 'down':
                        diff = max(values) - after
                    else:
                        diff = after - min(values)
                    change_ok = diff >= amount if change_op != '<=' else diff <= amount
        if use_current:
            element = cond.get('current_element')
            limit = _num(cond.get('current_value'))
            value = _element_value(current, element)
            current_ok = False
            if value is not None and limit is not None:
                current_op = cond.get('current_op') or ('<=' if direction != 'up' else '>=')
                current_ok = value <= limit if current_op == '<=' else value >= limit
        return change_ok, current_ok

    if kind == 'weather':
        if use_change:
            codes = cond.get('past_codes') or []
            samples = _in_past_window(obs, begin, now_ms)
            change_ok = False
            if samples:
                if codes:
                    wanted = set(codes)
                    if cond.get('past_match') == 'all':
                        seen = set()
                        for item in samples:
                            seen.update(wanted.intersection(item['weather']))
                        change_ok = wanted.issubset(seen)
                    else:
                        change_ok = any(wanted.intersection(item['weather']) for item in samples)
                else:
                    change_ok = any(not item['weather'] for item in samples)
        if use_current:
            cm = cond.get('current_match') or 'any'
            if not (cond.get('current_codes') or []):
                current_ok = not current['weather']
            elif cm == 'all':
                current_ok = set(cond.get('current_codes') or []).issubset(set(current['weather']))
            else:
                current_ok = bool(set(cond.get('current_codes') or []).intersection(current['weather']))
        return change_ok, current_ok

    if kind == 'cover':
        if use_change:
            samples = _in_past_window(obs, begin, now_ms)
            wanted_from = set(cond.get('cover_from') or [])
            wanted_to = set(cond.get('cover_to') or [])
            change_ok = bool(samples) and any(item['cover'] in wanted_from for item in samples) and current['cover'] in wanted_to
        if use_current:
            current_ok = current['cover'] in set(cond.get('cover_now') or [])
        return change_ok, current_ok

    if kind == 'height':
        if use_change:
            samples = _in_past_window(obs, begin, now_ms)
            change_ok = bool(samples) and any(
                _height_side(item, _num(cond.get('from_height')), cond.get('from_cmp'), cond.get('from_nsc'))
                for item in samples
            ) and _height_side(current, _num(cond.get('to_height')), cond.get('to_cmp'), cond.get('to_nsc'))
        if use_current:
            current_ok = _height_side(current, _num(cond.get('now_height')), cond.get('now_cmp'), cond.get('now_nsc'))
        return change_ok, current_ok
    return None, None


def _picked_score(cond: dict, key: str) -> float:
    value = _num(cond.get(key))
    if value is None:
        value = _num(cond.get('score'))
    return value or 0


def _condition_points(cond: dict, obs: list, now_ms: int) -> Optional[dict]:
    """未命中返回 None。命中时带上采用的分值，以及过去、当前各自是否成立。"""
    change_ok, current_ok = _condition_sides(cond, obs, now_ms)
    use_change = change_ok is not None
    use_current = current_ok is not None
    if not use_change and not use_current:
        return None
    both = use_change and use_current
    mode = 'any' if cond.get('match_mode') == 'any' else 'all'
    if both and mode != 'any':
        if not (change_ok and current_ok):
            return None
        score = _num(cond.get('score')) or 0
    elif both:
        if change_ok and current_ok:
            score = _num(cond.get('score')) or 0
        elif change_ok:
            score = _picked_score(cond, 'change_score')
        elif current_ok:
            score = _picked_score(cond, 'current_score')
        else:
            return None
    else:
        ok = change_ok if use_change else current_ok
        if not ok:
            return None
        score = _picked_score(cond, 'change_score' if use_change else 'current_score')
    return {'score': score, 'change': bool(change_ok), 'current': bool(current_ok)}


def _condition_match(cond: dict, obs: list, now_ms: int) -> bool:
    return _condition_points(cond, obs, now_ms) is not None


def _hit_rows(cond: dict, change: bool = True, current: bool = True) -> list:
    """时序表只列已经命中的要素。分别满足时，没命中的那一段不占行。"""
    rows = []
    if cond.get('kind') == 'element':
        if cond.get('use_change') and change:
            rows.append(cond.get('change_element'))
        if cond.get('use_current') and current:
            rows.append(cond.get('current_element'))
    elif cond.get('kind') == 'height' and (change or current):
        rows.append('height')
    elif cond.get('kind') == 'weather' and (change or current):
        rows.append('weather')
    elif cond.get('kind') == 'cover' and (change or current):
        rows.append('cover')
    seen = []
    for row in rows:
        if row in (*ELEMENTS, 'height', 'weather', 'cover') and row not in seen:
            seen.append(row)
    return seen


def _format_cell(key: str, obs: Optional[dict], speci: bool) -> dict:
    if obs is None:
        return {'text': '', 'speci': False}
    if key == 'weather':
        text = ' '.join(obs['weather']) if obs['weather'] else '无'
    elif key == 'cover':
        text = obs['cover'] or ''
    elif key == 'height':
        if obs.get('nsc') or obs.get('base') is None:
            text = 'NSC'
        else:
            text = str(int(round(obs['base'])))
    elif key == 'rh' or key == 'visibility':
        value = obs.get(key)
        text = '' if value is None else str(int(round(value)))
    else:
        value = obs.get(key)
        if value is None:
            text = ''
        else:
            rounded = round(float(value), 1)
            text = str(int(rounded)) if abs(rounded - int(rounded)) < 1e-9 else f'{rounded:.1f}'
    return {'text': text, 'speci': speci}


def build_slots(now_ms: int) -> list:
    """过去 24 小时内、不晚于当前时刻的整点与半点。"""
    begin = now_ms - DAY_MS
    slot = (begin // (30 * 60 * 1000)) * (30 * 60 * 1000)
    if slot < begin:
        slot += 30 * 60 * 1000
    slots = []
    while slot <= now_ms:
        slots.append(int(slot))
        slot += 30 * 60 * 1000
    return slots


def _routine_for_slot(obs: list, slot: int) -> Optional[dict]:
    """整点或半点前后 10 分钟内的例行报（SA）。多份时取发布时间更早的一份。"""
    begin = slot - SLOT_WINDOW_MS
    end = slot + SLOT_WINDOW_MS
    found = None
    for item in obs:
        if not item.get('sa'):
            continue
        if item['time'] < begin or item['time'] > end:
            continue
        if found is None or item['time'] < found['time']:
            found = item
    return found


def _latest_observation(obs: list, slots: list, now_ms: Optional[int]) -> Optional[dict]:
    """窗口内时间最晚的一份实况，整点、半点、特殊报都算。"""
    if not obs:
        return None
    end = now_ms if now_ms is not None else (slots[-1] if slots else 0)
    start = (slots[0] - 20 * 60 * 1000) if slots else end - DAY_MS
    pool = [item for item in obs if start <= item['time'] <= end + 60 * 1000]
    if not pool:
        return None
    return max(pool, key=lambda item: item['time'])


def _weather_text(obs: dict) -> str:
    codes = []
    for code in obs.get('weather') or []:
        token = str(code).strip().upper()
        if token and token not in codes:
            codes.append(token)
    return ','.join(codes)


def _cover_text(obs: dict) -> str:
    marks = []
    for code in obs.get('covers') or []:
        token = str(code).strip().upper()
        if token in ('FEW', 'SCT', 'BKN', 'OVC', 'NSC') and token not in marks:
            marks.append(token)
    if not marks:
        token = str(obs.get('cover') or '').strip().upper()
        if token in ('FEW', 'SCT', 'BKN', 'OVC', 'NSC'):
            marks.append(token)
    return ','.join(marks)


def _codes_hit(present: set, codes, mode: str) -> bool:
    wanted = {str(code).strip().upper() for code in (codes or []) if str(code).strip()}
    if not wanted:
        return not present
    if mode == 'all':
        return wanted.issubset(present)
    return bool(wanted.intersection(present))


def _report_meets_weather(item: dict, cond: dict) -> bool:
    """格子里要的是带有告警现象的那份报文。当前条件留空表示无天气，不拿它挡住后面的降水。"""
    present = set(item.get('weather') or [])
    hit = False
    coded = False
    if cond.get('use_current') and (cond.get('current_codes') or []):
        coded = True
        hit = hit or _codes_hit(present, cond.get('current_codes'), cond.get('current_match') or 'any')
    if cond.get('use_change') and (cond.get('past_codes') or []):
        coded = True
        hit = hit or _codes_hit(present, cond.get('past_codes'), cond.get('past_match') or 'any')
    if coded:
        return hit
    if cond.get('use_current') or cond.get('use_change'):
        return not present
    return False


def _report_meets_cover(item: dict, cond: dict) -> bool:
    marks = {str(code).strip().upper() for code in (item.get('covers') or [])}
    cover = str(item.get('cover') or '').strip().upper()
    if cover:
        marks.add(cover)
    targets = set()
    if cond.get('use_current'):
        targets.update(cond.get('cover_now') or [])
    if cond.get('use_change'):
        targets.update(cond.get('cover_to') or [])
    if not targets:
        return False
    return bool(marks.intersection(targets))


def _phenom_ranges(slot: int, hour_only: bool) -> dict:
    """天气现象、云量的取值窗口。半点格只有一套；整点格按是否勾选半点报分成两套。"""
    ten = 10 * 60 * 1000
    if slot % HOUR_MS != 0:
        return {
            'sa': [(slot - ten, slot + ten)],
            'sp': [(slot, slot + 29 * 60 * 1000 + 59 * 1000)],
        }
    if hour_only:
        return {
            'sa': [(slot - ten, slot + 40 * 60 * 1000)],
            'sp': [(slot, slot + 59 * 60 * 1000 + 59 * 1000)],
        }
    return {
        'sa': [(slot - ten, slot + ten)],
        'sp': [(slot, slot + 29 * 60 * 1000 + 50 * 1000)],
    }


def _in_ranges(moment: int, ranges) -> bool:
    return any(begin <= moment <= end for begin, end in ranges)


def _first_phenom(obs: list, slot: int, hour_only: bool, predicate) -> Optional[dict]:
    ranges = _phenom_ranges(slot, hour_only)
    found = None
    for item in obs:
        if item.get('sa'):
            ok = _in_ranges(item['time'], ranges['sa'])
        elif item.get('speci'):
            ok = _in_ranges(item['time'], ranges['sp'])
        else:
            continue
        if not ok or not predicate(item):
            continue
        if found is None or item['time'] < found['time']:
            found = item
    return found


def _phenom_cell(key: str, item: Optional[dict]) -> dict:
    if item is None:
        return {'text': '', 'speci': False}
    text = _weather_text(item) if key == 'weather' else _cover_text(item)
    return {'text': text, 'speci': bool(item.get('speci'))}


def _series(obs: list, slots: list, keys: list, now_ms: Optional[int] = None, matched: Optional[list] = None) -> tuple:
    """常规要素和云高仍取该格前后 10 分钟内的例行报。天气现象、云量取窗口内最早一份符合条件的报文。"""
    weather_conds = [cond for cond in (matched or []) if cond.get('kind') == 'weather']
    cover_conds = [cond for cond in (matched or []) if cond.get('kind') == 'cover']
    cells = {key: [] for key in keys}
    for slot in slots:
        routine = _routine_for_slot(obs, slot)
        for key in keys:
            if key not in ('weather', 'cover'):
                cells[key].append(_format_cell(key, routine, False))
                continue
            conds = weather_conds if key == 'weather' else cover_conds
            predicate = (
                (lambda item, group=conds: any(_report_meets_weather(item, cond) for cond in group))
                if key == 'weather'
                else (lambda item, group=conds: any(_report_meets_cover(item, cond) for cond in group))
            )
            picked = _phenom_cell(key, _first_phenom(obs, slot, False, predicate))
            if slot % HOUR_MS == 0:
                hour_only = _phenom_cell(key, _first_phenom(obs, slot, True, predicate))
                picked['text_hour'] = hour_only['text']
                picked['speci_hour'] = hour_only['speci']
            cells[key].append(picked)
    latest_obs = _latest_observation(obs, slots, now_ms)
    rows = []
    for key in ROW_ORDER:
        if key not in cells:
            continue
        if key in ('weather', 'cover'):
            latest_cell = {'text': '', 'speci': False}
        else:
            latest_cell = (
                _format_cell(key, latest_obs, bool(latest_obs.get('speci')))
                if latest_obs else {'text': '', 'speci': False}
            )
        rows.append({
            'key': key,
            'name': ROW_LABELS.get(key, key),
            'cells': cells[key],
            'latest': latest_cell,
        })
    return rows, None


def score_group(group: dict, obs: list, now_ms: int) -> Optional[dict]:
    enabled = [cond for cond in (group.get('conditions') or []) if cond.get('enabled', True)]
    for cond in enabled:
        if cond.get('role') == 'veto' and _condition_match(cond, obs, now_ms):
            return None
    required_scores = []
    extra_score = 0.0
    deduct_score = 0.0
    labels = []
    rows = []
    matched = []
    for cond in enabled:
        if cond.get('role') == 'veto':
            continue
        hit = _condition_points(cond, obs, now_ms)
        if hit is None:
            continue
        # 只收录整条条件已经命中的描述，未命中的不出现在四字代码下方
        label = cond.get('label') or ''
        role = cond.get('role')
        if role == 'deduct' and label:
            label = f'「{label}」'
        labels.append(label)
        rows.extend(_hit_rows(cond, hit['change'], hit['current']))
        matched.append(cond)
        score = hit['score']
        if role == 'extra':
            extra_score += min(score, EXTRA_SCORE_CAP)
        elif role == 'deduct':
            deduct_score += score
        else:
            required_scores.append(score)
    if required_scores:
        if group.get('required_agg') == 'avg':
            required = sum(required_scores) / len(required_scores)
        else:
            required = max(required_scores)
    else:
        required = 0.0
    total = max(0.0, required + extra_score - deduct_score)
    red = _num(group.get('threshold_r'))
    yellow = _num(group.get('threshold_y'))
    green = _num(group.get('threshold_g'))
    if red is not None and total >= red:
        color = 'R'
    elif yellow is not None and total >= yellow:
        color = 'Y'
    elif green is not None and total >= green:
        color = 'G'
    else:
        return None
    if not labels and not rows:
        return None
    return {
        'color': color,
        'score': round(total, 4),
        'labels': [label for label in labels if label],
        'rows': rows,
        'matched': matched,
    }


def merge_hits(hits: list) -> Optional[dict]:
    alerting = [hit for hit in hits if hit]
    if not alerting:
        return None
    best_color = max(alerting, key=lambda hit: (COLOR_RANK.get(hit['color'], 0), hit.get('score') or 0))
    best_score = max(alerting, key=lambda hit: ((hit.get('score') or 0), COLOR_RANK.get(hit['color'], 0)))
    labels = []
    rows = []
    matched = []
    for hit in alerting:
        for label in hit['labels']:
            if label not in labels:
                labels.append(label)
        for row in hit['rows']:
            if row not in rows:
                rows.append(row)
        for cond in hit.get('matched') or []:
            if cond not in matched:
                matched.append(cond)
    return {
        'color': best_color['color'],
        'score': best_score['score'],
        'bar_color': best_score['color'],
        'labels': labels,
        'rows': rows,
        'matched': matched,
    }


def evaluate_airport(obs: list, groups: list, now_ms: int, slots: list) -> dict:
    """时序保留命中的常规要素、云高，以及命中的天气现象和云量。未达阈值的机场不铺全部要素。"""
    ordered = sorted(obs, key=lambda item: item['time'])
    hits = []
    for group in groups or []:
        if not group.get('enabled', True):
            continue
        hits.append(score_group(group, ordered, now_ms))
    merged = merge_hits(hits)
    keys = merged['rows'] if merged else []
    rows, _speci = _series(ordered, slots, keys, now_ms, (merged or {}).get('matched'))
    if not merged:
        return {
            'color': 'N',
            'score': 0,
            'bar_color': '',
            'labels': [],
            'rows': rows,
        }
    return {
        'color': merged['color'],
        'score': merged['score'],
        'bar_color': merged.get('bar_color') or merged['color'],
        'labels': merged['labels'],
        'rows': rows,
    }


def _clean_condition(raw: dict, index: int, known_weather: set, errors: list) -> Optional[dict]:
    prefix = f'条件{index}'
    kind = str(raw.get('kind') or '').strip()
    if kind not in ('element', 'weather', 'cover', 'height'):
        errors.append(f'{prefix}类型无效')
        return None
    label = str(raw.get('label') or '').strip()
    score = _num(raw.get('score'))
    role = str(raw.get('role') or '')
    if role not in ('extra', 'veto', 'deduct'):
        role = 'required'
    if not label:
        errors.append(f'{prefix}需要描述词')
    if role == 'required':
        if score is None or score < 1 or score > 5:
            errors.append(f'{prefix}基础条件分值需在 1 到 5 之间')
            if score is None:
                score = 1
    elif role == 'veto':
        score = 0
    else:
        role_name = {'extra': '附加条件', 'deduct': '减分条件'}[role]
        if score is None or score < 0.1 or score > EXTRA_SCORE_CAP:
            errors.append(f'{prefix}{role_name}分值需在 0.1 到 {EXTRA_SCORE_CAP} 之间')
            if score is None:
                score = 0.1
    use_change = _bool(raw.get('use_change'))
    use_current = _bool(raw.get('use_current'))
    if not use_change and not use_current:
        errors.append(f'{prefix}至少填写一段条件')
    hours = _num(raw.get('hours'))
    if use_change and (hours is None or hours <= 0 or hours > MAX_HOURS):
        errors.append(f'{prefix}过去小时数需大于 0 且不超过 {MAX_HOURS}')
    match_mode = 'any' if str(raw.get('match_mode') or '') == 'any' else 'all'

    def side_score(key: str, enabled: bool) -> float:
        if role == 'veto':
            return 0
        value = _num(raw.get(key))
        if value is None:
            value = score
        if enabled:
            if role == 'required':
                if value is None or value < 1 or value > 5:
                    errors.append(f'{prefix}分段分值需在 1 到 5 之间')
                    if value is None:
                        value = 1
            elif value is None or value < 0.1 or value > EXTRA_SCORE_CAP:
                errors.append(f'{prefix}分段分值需在 0.1 到 {EXTRA_SCORE_CAP} 之间')
                if value is None:
                    value = 0.1
        return value if value is not None else 0

    cond = {
        'id': str(raw.get('id') or new_id()),
        'enabled': _bool(raw.get('enabled'), True),
        'role': role,
        'kind': kind,
        'score': score if score is not None else 0,
        'change_score': side_score('change_score', use_change),
        'current_score': side_score('current_score', use_current),
        'match_mode': match_mode,
        'label': label,
        'hours': hours if hours is not None else None,
        'use_change': use_change,
        'use_current': use_current,
    }
    if kind == 'element':
        direction = str(raw.get('direction') or '').strip()
        if direction not in ('down', 'up'):
            errors.append(f'{prefix}需要选择下降或上升')
            direction = 'down'
        cond['direction'] = direction
        change_op = str(raw.get('change_op') or '').strip()
        cond['change_op'] = change_op if change_op in ('>=', '<=') else '>='
        current_op = str(raw.get('current_op') or '').strip()
        cond['current_op'] = current_op if current_op in ('>=', '<=') else ('<=' if direction != 'up' else '>=')
        if use_change:
            element = str(raw.get('change_element') or '').strip()
            amount = _num(raw.get('change_amount'))
            if element not in ELEMENTS:
                errors.append(f'{prefix}变化要素无效')
            if amount is None:
                errors.append(f'{prefix}需要填写变化量')
            cond['change_element'] = element
            cond['change_amount'] = amount
        if use_current:
            element = str(raw.get('current_element') or '').strip()
            limit = _num(raw.get('current_value'))
            if element not in ELEMENTS:
                errors.append(f'{prefix}当前要素无效')
            if limit is None:
                errors.append(f'{prefix}需要填写当前阈值')
            cond['current_element'] = element
            cond['current_value'] = limit
    elif kind == 'weather':
        past_codes = _split_codes(raw.get('past_weather') or '')
        current_codes = _split_codes(raw.get('current_weather') or '')
        past_match = str(raw.get('past_match') or '').strip()
        cond['past_match'] = 'all' if past_match == 'all' else 'any'
        current_match = str(raw.get('current_match') or '').strip()
        current_match = 'all' if current_match == 'all' else 'any'
        if use_change:
            unknown = [code for code in past_codes if code not in known_weather]
            if unknown:
                errors.append(f'{prefix}天气现象未登记：{",".join(unknown)}')
        if use_current and current_match == 'any':
            unknown = [code for code in current_codes if code not in known_weather]
            if unknown:
                errors.append(f'{prefix}当前天气现象未登记：{",".join(unknown)}')
        cond['past_codes'] = past_codes
        cond['past_weather'] = ','.join(past_codes)
        cond['current_codes'] = current_codes
        cond['current_weather'] = ','.join(current_codes)
        cond['current_match'] = current_match
    elif kind == 'cover':
        cover_from = [c for c in _split_codes(raw.get('cover_from') or '')]
        cover_to = [c for c in _split_codes(raw.get('cover_to') or '')]
        cover_now = [c for c in _split_codes(raw.get('cover_now') or '')]
        if use_change:
            if not cover_from or not cover_to:
                errors.append(f'{prefix}需要填写变化前后的云量')
            bad = [c for c in cover_from + cover_to if c not in COVERS]
            if bad:
                errors.append(f'{prefix}云量只能是 NSC、FEW、SCT、BKN、OVC')
        if use_current:
            if not cover_now:
                errors.append(f'{prefix}需要填写当前云量')
            bad = [c for c in cover_now if c not in COVERS]
            if bad:
                errors.append(f'{prefix}云量只能是 NSC、FEW、SCT、BKN、OVC')
        cond['cover_from'] = cover_from
        cond['cover_to'] = cover_to
        cond['cover_now'] = cover_now
    elif kind == 'height':
        def clean_height_side(side_name, key_h, key_c, key_n):
            height = _num(raw.get(key_h))
            cmp = str(raw.get(key_c) or '')
            nsc = _bool(raw.get(key_n))
            if height is None and not nsc:
                errors.append(f'{prefix}{side_name}需要填写云高，或只勾选可为空或NSC')
            if height is not None and cmp not in ('below', 'above'):
                errors.append(f'{prefix}{side_name}云高需要选择低于或高于')
            cond[key_h] = height
            cond[key_c] = cmp if cmp in ('below', 'above') else ''
            cond[key_n] = nsc

        if use_change:
            clean_height_side('起点', 'from_height', 'from_cmp', 'from_nsc')
            clean_height_side('终点', 'to_height', 'to_cmp', 'to_nsc')
        if use_current:
            clean_height_side('当前', 'now_height', 'now_cmp', 'now_nsc')
    return cond


def _clean_airports(text: str) -> list:
    codes = []
    for part in _split_commas(text):
        code = part.strip().upper()
        if re.fullmatch(r'[A-Z]{4}', code) and code not in codes:
            codes.append(code)
    return codes


def normalize_config(payload: Any, known_weather: Optional[set] = None) -> tuple:
    known = {str(code).strip().upper() for code in (known_weather or set()) if str(code).strip()}
    errors = []
    if not isinstance(payload, dict):
        return default_config(), ['配置格式无效']
    groups_in = payload.get('groups')
    if groups_in is None:
        groups_in = []
    if not isinstance(groups_in, list):
        return default_config(), ['规则列表格式无效']
    groups = []
    for g_index, raw in enumerate(groups_in, start=1):
        if not isinstance(raw, dict):
            errors.append(f'规则{g_index}格式无效')
            continue
        prefix = f'规则{g_index}'
        mode = 'specific' if str(raw.get('airport_mode') or '') == 'specific' else 'all'
        airports = _clean_airports(raw.get('airports') or '')
        invalid = []
        for part in _split_commas(raw.get('airports') or ''):
            code = part.strip().upper()
            if code and not re.fullmatch(r'[A-Z]{4}', code):
                invalid.append(part.strip())
        if invalid:
            errors.append(f'{prefix}机场代码无效：{",".join(invalid)}')
        if mode == 'specific' and not airports:
            errors.append(f'{prefix}选择特定时需要填写四字码')
        agg = 'avg' if str(raw.get('required_agg') or '') == 'avg' else 'max'
        thresholds = {}
        for key, title in (('threshold_g', '绿'), ('threshold_y', '黄'), ('threshold_r', '红')):
            value = _num(raw.get(key))
            if value is None:
                errors.append(f'{prefix}需要{title}阈值')
            thresholds[key] = value
        conditions = []
        raw_conditions = raw.get('conditions') if isinstance(raw.get('conditions'), list) else []
        for c_index, cond in enumerate(raw_conditions, start=1):
            if not isinstance(cond, dict):
                errors.append(f'{prefix}条件{c_index}格式无效')
                continue
            cleaned = _clean_condition(cond, c_index, known, errors)
            if cleaned:
                conditions.append(cleaned)
        groups.append({
            'id': str(raw.get('id') or new_id()),
            'name': str(raw.get('name') or '').strip() or f'规则{g_index}',
            'enabled': _bool(raw.get('enabled'), True),
            'airport_mode': mode,
            'airports': airports,
            'airports_text': ','.join(airports),
            'required_agg': agg,
            'threshold_g': thresholds['threshold_g'],
            'threshold_y': thresholds['threshold_y'],
            'threshold_r': thresholds['threshold_r'],
            'conditions': conditions,
        })
    return {'groups': groups, 'alarm_colors': alarm_colors_of(payload if isinstance(payload, dict) else {})}, errors


def groups_for_airport(config: dict, airport: str, universe: set) -> list:
    code = (airport or '').upper()
    if code not in universe:
        return []
    selected = []
    for group in config.get('groups') or []:
        if not group.get('enabled', True):
            continue
        if group.get('airport_mode') == 'specific':
            if code not in set(group.get('airports') or []):
                continue
        selected.append(group)
    return selected


def airport_universe(scope: str, now_ms: Optional[int] = None, future_hours: int = 2) -> list:
    """与雷达共用 airport_scope。后台保留未来 9 小时，避免较宽的本机设置被清掉。"""
    from utils.airport_scope import airport_codes_for_scope

    return airport_codes_for_scope(scope, future_hours, now_ms)


def max_lookback_ms(groups: list) -> int:
    hours = [24.0]
    for group in groups:
        for cond in group.get('conditions') or []:
            if cond.get('enabled', True) and cond.get('use_change'):
                value = _num(cond.get('hours'))
                if value:
                    hours.append(value)
    return int(max(hours) * HOUR_MS) + 3 * HOUR_MS


def load_config_row(user_code=None):
    from core.models import TrendAlertConfig
    from utils.user_settings import active_job_user, json_config_row
    return json_config_row(TrendAlertConfig, user_code or active_job_user())


def known_weather_codes(user_code=None) -> set:
    from utils.user_settings import known_weather_codes as codes_for
    return codes_for(user_code)


def read_config(user_code=None) -> dict:
    from utils.user_settings import active_job_user
    user = user_code or active_job_user()
    row = load_config_row(user)
    payload = row.config if row and isinstance(row.config, dict) else default_config()
    config, _errors = normalize_config(payload, known_weather_codes(user))
    return config


def save_config(payload: dict, user_code=None) -> tuple:
    from core.models import TrendAlertConfig
    from utils.user_settings import active_job_user, save_json_config
    user = user_code or active_job_user()
    before = read_config(user)
    config, errors = normalize_config(payload, known_weather_codes(user))
    if errors:
        return None, errors
    save_json_config(TrendAlertConfig, user, config)
    now_ms = int(time.time() * 1000)
    universe = _active_universe(now_ms)
    changed = _changed_airports(before.get('groups') or [], config.get('groups') or [], universe)
    if changed:
        refresh_airports(sorted(changed), now_ms)
    return config, []


def _group_airports(group, universe: set) -> set:
    if not group or not group.get('enabled', True):
        return set()
    if str(group.get('airport_mode') or '') == 'specific':
        return {str(code).upper() for code in (group.get('airports') or []) if str(code).upper() in universe}
    return set(universe)


def _changed_airports(before: list, after: list, universe: set) -> set:
    old_map = {str(group.get('id')): group for group in before or [] if isinstance(group, dict)}
    new_map = {str(group.get('id')): group for group in after or [] if isinstance(group, dict)}
    codes = set()
    for gid in set(old_map) | set(new_map):
        old = old_map.get(gid)
        new = new_map.get(gid)
        if old == new:
            continue
        codes |= _group_airports(old, universe)
        codes |= _group_airports(new, universe)
    return codes


def _pack_series(rows: list, slots: list) -> list:
    packed = []
    for row in rows:
        points = []
        for slot, cell in zip(slots, row.get('cells') or []):
            text = cell.get('text') or ''
            text_hour = cell.get('text_hour') or ''
            if not text and not text_hour:
                continue
            point = {'t': int(slot), 'text': text, 'speci': bool(cell.get('speci'))}
            if text_hour:
                point['text_hour'] = text_hour
                point['speci_hour'] = bool(cell.get('speci_hour'))
            points.append(point)
        latest = row.get('latest') or {}
        packed.append({
            'key': row.get('key'),
            'name': row.get('name'),
            'points': points,
            'latest': {'text': latest.get('text') or '', 'speci': bool(latest.get('speci'))},
        })
    return packed


def _unpack_series(packed: list, slots: list) -> list:
    rows = []
    for row in packed or []:
        points = row.get('points') or []
        cells = []
        for slot in slots:
            hit = next((point for point in points if abs(int(point.get('t') or 0) - slot) <= 60 * 1000), None)
            if hit:
                cells.append({
                    'text': hit.get('text') or '',
                    'speci': bool(hit.get('speci')),
                    'text_hour': hit.get('text_hour') or '',
                    'speci_hour': bool(hit.get('speci_hour')),
                })
            else:
                cells.append({'text': '', 'speci': False, 'text_hour': '', 'speci_hour': False})
        latest = row.get('latest') or {}
        rows.append({
            'key': row.get('key'),
            'name': row.get('name'),
            'cells': cells,
            'latest': {'text': latest.get('text') or '', 'speci': bool(latest.get('speci'))},
        })
    return rows


def _active_universe(now_ms: int) -> set:
    from utils.airport_scope import FUTURE_HOURS_MAX

    return set(airport_universe('has_flight', now_ms)) | set(
        airport_universe('recent2h', now_ms, FUTURE_HOURS_MAX)
    )


def clear_airports(codes) -> None:
    from core.models import AirportTrendAlert
    wanted = sorted({str(code).upper() for code in codes or [] if code})
    if wanted:
        AirportTrendAlert.objects.filter(airport_4code__in=wanted).delete()


def refresh_airports(codes, now_ms: Optional[int] = None, *, backfill: bool = True) -> None:
    """只重算给定机场。不在有航班或起降窗口全集里的机场直接清掉结果。"""
    import logging
    from core.models import AirportTrendAlert
    from parsers.models import Metar

    logger = logging.getLogger('fmsa.trend')
    wanted = sorted({str(code).upper() for code in codes or [] if code})
    if not wanted:
        return
    try:
        now_ms = int(now_ms if now_ms is not None else time.time() * 1000)
        config = read_config()
        universe = _active_universe(now_ms)
        outside = [code for code in wanted if code not in universe]
        clear_airports(outside)
        inside = [code for code in wanted if code in universe]
        active_groups = [group for group in config.get('groups') or [] if group.get('enabled', True)]
        if not inside or not active_groups:
            clear_airports(inside)
            return
        lookback = max_lookback_ms(active_groups)
        if backfill:
            try:
                from parsers.trend_metar_backfill import queue_hourly_sa_history
                queue_hourly_sa_history(inside, lookback, now_ms)
            except Exception:
                logger.exception('实况趋势告警历史补数排队失败: %s', inside)
        slots = build_slots(now_ms)
        since = now_ms - lookback
        rows = Metar.objects.filter(
            airport_4code__in=inside,
            metar_observation_time__gte=since,
            metar_observation_time__lte=now_ms,
        ).values(
            'airport_4code', 'metar_type', 'metar_observation_time',
            'metar_wind_speed_val', 'metar_visibility_val', 'metar_temp_val',
            'metar_dew_point', 'metar_weather', 'metar_cloud', 'metar_min_cloud_height',
            'metar_elements', 'metar_content',
        )
        by_airport = {code: [] for code in inside}
        for row in rows:
            code = str(row.get('airport_4code') or '').upper()
            snap = snapshot_from_row(row)
            if code in by_airport and snap is not None:
                by_airport[code].append(snap)
        previous = {
            row.airport_4code: row
            for row in AirportTrendAlert.objects.filter(airport_4code__in=inside)
        }
        pending = []
        for code in inside:
            groups = groups_for_airport(config, code, universe)
            result = evaluate_airport(by_airport.get(code) or [], groups, now_ms, slots)
            color = result['color']
            old = previous.get(code)
            handled = bool(
                old and old.handled and old.handled_signature == color and color in ('R', 'Y', 'G')
            )
            pending.append((code, {
                'color': color,
                'score': result['score'],
                'bar_color': result.get('bar_color') or color,
                'labels': result['labels'],
                'series': _pack_series(result['rows'], slots),
                'handled': handled,
                'handled_signature': color if handled else '',
            }))

        from utils.sqlite_retry import retry_if_locked

        def _write():
            for code, defaults in pending:
                AirportTrendAlert.objects.update_or_create(
                    airport_4code=code,
                    defaults=defaults,
                )

        retry_if_locked(_write)
    except Exception:
        logger.exception('实况趋势告警重算失败: %s', wanted)


def refresh_active_airports(now_ms: Optional[int] = None) -> None:
    """规则保存后，按当前两个机场全集重算一次。"""
    now_ms = int(now_ms if now_ms is not None else time.time() * 1000)
    refresh_airports(sorted(_active_universe(now_ms)), now_ms)


def build_results(scope: str, now_ms: Optional[int] = None, future_hours: int = 2) -> dict:
    """只返回当前选中集合里的机场。已离开该集合的，不论是否已处理，都不进入表格和导航数字。"""
    from core.models import AirportTrendAlert

    now_ms = int(now_ms if now_ms is not None else time.time() * 1000)
    universe = airport_universe(scope, now_ms, future_hours)
    slots = build_slots(now_ms)
    stored = AirportTrendAlert.objects.filter(airport_4code__in=universe)
    airports = []
    for row in stored:
        airports.append({
            'airport': row.airport_4code,
            'color': row.color,
            'score': row.score,
            'bar_color': row.bar_color or row.color,
            'labels': row.labels or [],
            'handled': row.is_handled_current(),
            'rows': _unpack_series(row.series or [], slots),
        })
    airports.sort(key=lambda item: (-COLOR_RANK.get(item['color'], 0), item['airport']))
    return {
        'slots': slots,
        'airports': airports,
        'scope': scope,
        'universe_count': len(universe),
        'alarm_colors': read_config().get('alarm_colors') or ['R', 'Y', 'G'],
    }


def _self_check() -> None:
    now = 1_700_000_000_000
    hour = HOUR_MS

    def obs(offset_h, **values):
        base = {
            'time': now - int(offset_h * hour),
            'speci': False,
            'temperature': 20,
            'dewpoint': 10,
            'rh': relative_humidity(20, 10),
            'pressure': 1013,
            'wind': 3,
            'visibility': 9999,
            'weather': [],
            'cover': 'NSC',
            'base': None,
            'nsc': True,
        }
        base.update(values)
        if 'sa' not in values:
            base['sa'] = not base.get('speci')
        return base

    series = [
        obs(6, temperature=20, visibility=8000, cover='FEW', base=30, nsc=False, weather=[]),
        obs(1, temperature=12, visibility=900, cover='BKN', base=8, nsc=False, weather=['RA'], speci=True),
    ]
    element = {
        'enabled': True, 'role': 'required', 'kind': 'element', 'direction': 'down',
        'use_change': True, 'use_current': True, 'hours': 6,
        'change_element': 'temperature', 'change_amount': 8,
        'current_element': 'visibility', 'current_value': 1000,
        'score': 4, 'label': '气温下降且能见度低',
    }
    assert _condition_match(element, series, now)
    only_past = dict(element, match_mode='any', change_score=2, current_score=3, current_value=100)
    past_hit = _condition_points(only_past, series, now)
    assert past_hit and past_hit['score'] == 2 and past_hit['change'] and not past_hit['current']
    only_now = dict(element, match_mode='any', change_amount=20, change_score=2, current_score=3)
    now_hit = _condition_points(only_now, series, now)
    assert now_hit and now_hit['score'] == 3 and not now_hit['change'] and now_hit['current']
    both_hit = _condition_points(dict(element, match_mode='any', change_score=2, current_score=3), series, now)
    assert both_hit and both_hit['score'] == 4 and both_hit['change'] and both_hit['current']
    assert not _condition_points(dict(element, match_mode='all', current_value=100), series, now)
    one_side = _condition_points(dict(element, use_current=False, change_score=2), series, now)
    assert one_side and one_side['score'] == 2
    assert _hit_rows(only_past, past_hit['change'], past_hit['current']) == ['temperature']
    element_short = dict(element, change_amount=9)
    assert not _condition_match(element_short, series, now)
    # 下降对比时段内最高值，上升对比时段内最低值
    peaked = [obs(6, temperature=20), obs(3, temperature=5), obs(0, temperature=16)]
    peaked_rule = dict(element, use_current=False, change_amount=8, current_element=None)
    assert not _condition_match(peaked_rule, peaked, now)
    assert _condition_match(dict(peaked_rule, change_amount=4), peaked, now)
    interior = [obs(6, temperature=10), obs(3, temperature=20), obs(0, temperature=12)]
    assert _condition_match(dict(peaked_rule, change_amount=8), interior, now)
    assert not _condition_match(dict(peaked_rule, direction='up', change_amount=8), interior, now)
    assert _condition_match(dict(peaked_rule, direction='up', change_amount=2), interior, now)
    no_start = [obs(1, temperature=10)]
    assert not _condition_match(dict(peaked_rule, hours=6), no_start, now)

    weather = {
        'enabled': True, 'role': 'extra', 'kind': 'weather', 'use_change': True, 'use_current': True,
        'hours': 6, 'past_codes': ['RA'], 'current_match': 'any', 'current_codes': ['RA'],
        'score': 4.5, 'label': '出现降雨',
    }
    assert _condition_match(weather, series, now)
    assert _condition_match(dict(weather, past_codes=[], use_current=False), [obs(1, weather=[])], now)
    wet = [obs(6, weather=['RA']), obs(1, weather=['RA'], speci=True)]
    assert not _condition_match(dict(weather, past_codes=[], use_current=False), wet, now)

    cover = {
        'enabled': True, 'kind': 'cover', 'use_change': True, 'use_current': False, 'hours': 6,
        'cover_from': ['FEW', 'SCT'], 'cover_to': ['BKN', 'OVC'], 'score': 2, 'label': '云量增加', 'role': 'required',
    }
    assert _condition_match(cover, series, now)
    mid_cover = [obs(6, cover='OVC', base=10, nsc=False), obs(3, cover='FEW', base=30, nsc=False), obs(0, cover='BKN', base=8, nsc=False)]
    assert _condition_match(cover, mid_cover, now)
    assert not _condition_match(cover, [obs(6, cover='OVC', base=10, nsc=False), obs(0, cover='BKN', base=8, nsc=False)], now)
    empty_cloud = [obs(6), obs(0)]
    assert _condition_match(dict(cover, cover_from=['NSC'], cover_to=['NSC']), empty_cloud, now)
    # 实况没有云组时按 NSC，当前云量选 NSC 即命中
    assert _cloud_state(None, '', None)['cover'] == 'NSC'
    assert _cloud_state({}, None, None)['cover'] == 'NSC'
    no_cloud = [obs(0, cover='NSC', base=None, nsc=True)]
    assert _condition_match({
        'enabled': True, 'kind': 'cover', 'role': 'required', 'use_change': False, 'use_current': True,
        'cover_now': ['NSC'], 'score': 1, 'label': '无云',
    }, no_cloud, now)
    assert _split_codes(['NSC', 'FEW']) == ['NSC', 'FEW']
    assert _split_codes("['NSC', 'FEW', 'OVC']") == ['NSC', 'FEW', 'OVC']
    assert _split_codes(["['NSC", "'FEW'", "'OVC']"]) == ['NSC', 'FEW', 'OVC']

    height = {
        'enabled': True, 'kind': 'height', 'role': 'required', 'use_change': False, 'use_current': True,
        'now_height': 10, 'now_cmp': 'below', 'now_nsc': False, 'score': 3, 'label': '云高低',
    }
    assert _condition_match(height, series, now)
    assert _condition_match(dict(height, now_nsc=True), empty_cloud, now)
    assert not _condition_match(height, empty_cloud, now)
    became_clear = [
        obs(6, cover='FEW', base=20, nsc=False),
        obs(3, cover='BKN', base=45, nsc=False),
        obs(0, cover='NSC', base=None, nsc=True),
    ]
    to_clear = {
        'enabled': True, 'kind': 'height', 'role': 'required', 'use_change': True, 'use_current': False,
        'hours': 6, 'from_height': 40, 'from_cmp': 'above', 'from_nsc': False,
        'to_height': None, 'to_cmp': '', 'to_nsc': True, 'score': 1, 'label': '由高云转无云',
    }
    assert _condition_match(to_clear, became_clear, now)
    assert not _condition_match(to_clear, [obs(6, cover='FEW', base=20, nsc=False), obs(0, cover='NSC', base=None, nsc=True)], now)
    assert _hit_rows(to_clear) == ['height']
    assert _hit_rows({'kind': 'weather', 'use_change': True}) == ['weather']
    assert _hit_rows({'kind': 'cover', 'use_change': True}) == ['cover']
    only_nsc, height_errs = normalize_config({'groups': [{
        'name': '云', 'airport_mode': 'all', 'threshold_g': 1, 'threshold_y': 2, 'threshold_r': 3,
        'conditions': [{
            'kind': 'height', 'role': 'required', 'label': '转无云', 'score': 1,
            'use_change': True, 'use_current': False, 'hours': 6,
            'from_height': 30, 'from_cmp': 'above', 'from_nsc': False,
            'to_height': '', 'to_cmp': '', 'to_nsc': True,
        }],
    }]})
    assert not height_errs and only_nsc['groups'][0]['conditions'][0]['to_height'] is None
    def score_payload(score, role):
        return {'groups': [{
            'name': '计分', 'airport_mode': 'all', 'threshold_g': 1, 'threshold_y': 2, 'threshold_r': 3,
            'conditions': [{
                'kind': 'element', 'role': role, 'label': '风力', 'score': score,
                'use_current': True, 'use_change': False, 'direction': 'down',
                'current_element': 'wind', 'current_value': 2,
            }],
        }]}
    _, low_extra = normalize_config(score_payload(0.05, 'extra'))
    _, ok_extra = normalize_config(score_payload(0.1, 'extra'))
    _, low_base = normalize_config(score_payload(0.5, 'required'))
    _, ok_base = normalize_config(score_payload(1, 'required'))
    _, low_deduct = normalize_config(score_payload(0.05, 'deduct'))
    _, ok_deduct = normalize_config(score_payload(3, 'deduct'))
    _, high_deduct = normalize_config(score_payload(3.1, 'deduct'))
    assert low_extra and not ok_extra and low_base and not ok_base
    assert low_deduct and not ok_deduct and high_deduct

    group = {
        'enabled': True, 'required_agg': 'max',
        'threshold_g': 1, 'threshold_y': 3, 'threshold_r': 5,
        'conditions': [element, weather],
    }
    scored = score_group(group, series, now)
    assert scored and scored['color'] == 'R' and abs(scored['score'] - (4 + EXTRA_SCORE_CAP)) < 1e-9
    assert scored['rows'] == ['temperature', 'visibility', 'weather']
    assert scored['labels'] == ['气温下降且能见度低', '出现降雨']
    missed = dict(element, label='风速上升', use_current=False, change_element='wind', direction='up', change_amount=20)
    partial = score_group(dict(group, conditions=[element, weather, missed]), series, now)
    assert partial and partial['labels'] == ['气温下降且能见度低', '出现降雨']
    second_extra = dict(weather, score=2, label='另一次降雨')
    summed = score_group(dict(group, conditions=[element, weather, second_extra]), series, now)
    assert summed and abs(summed['score'] - (4 + EXTRA_SCORE_CAP + 2)) < 1e-9
    averaged = score_group(dict(group, required_agg='avg', conditions=[
        dict(element, score=4), dict(element, score=4.5, label='更深', change_amount=8),
    ]), series, now)
    assert averaged and averaged['score'] == 4.25
    only_extra = score_group(dict(group, conditions=[dict(weather, role='extra')], threshold_g=2, threshold_y=9, threshold_r=9), series, now)
    assert only_extra and only_extra['color'] == 'G' and only_extra['score'] == EXTRA_SCORE_CAP
    vetoed = score_group(dict(group, conditions=[element, dict(element, role='veto', label='否决', score=0.5)]), series, now)
    assert vetoed is None
    deducted = score_group(dict(group, conditions=[
        element, weather, dict(weather, role='deduct', score=2, label='回升'),
    ]), series, now)
    assert deducted and deducted['color'] == 'R' and abs(deducted['score'] - 5) < 1e-9
    assert '「回升」' in deducted['labels']
    floored = score_group(dict(group, conditions=[
        element,
        dict(element, role='deduct', score=3, label='扣一'),
        dict(element, role='deduct', score=3, label='扣二'),
    ]), series, now)
    assert floored is None
    isolated = evaluate_airport(series, [
        dict(group, conditions=[element, dict(element, role='veto', label='否决', score=1)]),
        dict(group, conditions=[element]),
    ], now, build_slots(now))
    assert isolated['color'] == 'Y' and '否决' not in isolated['labels']

    slots = build_slots(now)
    assert slots
    assert all(slot <= now for slot in slots)
    assert slots[-1] % (30 * 60 * 1000) == 0
    hour_slot = slots[0]
    half_slot = hour_slot + 30 * 60 * 1000
    only_hour = [obs(0)]
    only_hour[0]['time'] = hour_slot
    only_hour[0]['temperature'] = 7
    packed_rows, _idx = _series(only_hour, [hour_slot, half_slot], ['temperature'], now)
    assert packed_rows[0]['cells'][0]['text'] == '7'
    assert packed_rows[0]['cells'][1]['text'] == ''
    assert packed_rows[0]['latest']['text'] == '7'
    speci = obs(0, temperature=9, speci=True)
    speci['time'] = hour_slot + 10 * 60 * 1000
    with_speci, _idx = _series(only_hour + [speci], [hour_slot, half_slot], ['temperature'], half_slot + 20 * 60 * 1000)
    assert with_speci[0]['cells'][0]['text'] == '7'
    assert with_speci[0]['cells'][1]['text'] == ''
    assert with_speci[0]['latest']['text'] == '9' and with_speci[0]['latest']['speci']
    early = obs(0, temperature=1)
    early['time'] = hour_slot - 8 * 60 * 1000
    late = obs(0, temperature=2)
    late['time'] = hour_slot - 2 * 60 * 1000
    far = obs(0, temperature=8)
    far['time'] = hour_slot - 11 * 60 * 1000
    picked, _idx = _series([late, far, early], [hour_slot], ['temperature'], hour_slot)
    assert picked[0]['cells'][0]['text'] == '1'
    half_obs = obs(0, temperature=3)
    half_obs['time'] = half_slot + 9 * 60 * 1000
    half_rows, _idx = _series([half_obs], [hour_slot, half_slot], ['temperature'], half_slot)
    assert half_rows[0]['cells'][0]['text'] == '' and half_rows[0]['cells'][1]['text'] == '3'
    special = obs(0, temperature=6, speci=True)
    special['time'] = hour_slot - 3 * 60 * 1000
    special_rows, _idx = _series([special], [hour_slot], ['temperature'], hour_slot)
    assert special_rows[0]['cells'][0]['text'] == ''
    slot = (now // HOUR_MS) * HOUR_MS
    if slot > now:
        slot -= HOUR_MS
    half = slot + 30 * 60 * 1000
    rain = {
        'kind': 'weather', 'use_current': True, 'use_change': False,
        'current_codes': ['RA'], 'current_match': 'any',
    }
    sa_clear = obs(0, weather=[], sa=True, speci=False)
    sa_clear['time'] = slot
    sa_rain = obs(0, weather=['RA'], sa=True, speci=False)
    sa_rain['time'] = slot - 5 * 60 * 1000
    sp_rain = obs(0, weather=['RA', 'BR'], speci=True, sa=False)
    sp_rain['time'] = slot + 15 * 60 * 1000
    sp_late = obs(0, weather=['RA'], speci=True, sa=False)
    sp_late['time'] = slot + 40 * 60 * 1000
    phenom, _idx = _series([sa_clear, sp_rain, sa_rain, sp_late], [slot, half], ['weather'], slot + 50 * 60 * 1000, [rain])
    assert phenom[0]['cells'][0]['text'] == 'RA' and phenom[0]['cells'][0]['speci'] is False
    assert phenom[0]['cells'][0]['text_hour'] == 'RA'
    assert phenom[0]['cells'][1]['text'] == 'RA' and phenom[0]['cells'][1]['speci'] is True
    only_later, _idx = _series([sa_clear, sp_rain], [slot], ['weather'], slot, [rain])
    assert only_later[0]['cells'][0]['text'] == 'RA,BR' and only_later[0]['cells'][0]['speci'] is True
    assert only_later[0]['cells'][0]['text_hour'] == 'RA,BR'
    stopped = {
        'kind': 'weather', 'use_current': True, 'use_change': True,
        'current_codes': [], 'current_match': 'any', 'past_codes': ['RA'], 'past_match': 'any',
    }
    after_rain, _idx = _series([sa_clear, sp_rain], [slot], ['weather'], slot, [stopped])
    assert after_rain[0]['cells'][0]['text'] == 'RA,BR'
    sa_gap = obs(0, weather=['RA'], sa=True, speci=False)
    sa_gap['time'] = slot + 15 * 60 * 1000
    gap_rows, _idx = _series([sa_gap], [slot], ['weather'], slot, [rain])
    assert gap_rows[0]['cells'][0]['text'] == ''
    assert gap_rows[0]['cells'][0]['text_hour'] == 'RA'
    sa_half = obs(0, weather=['RA'], sa=True, speci=False)
    sa_half['time'] = slot + 25 * 60 * 1000
    hour_only_sa, _idx = _series([sa_half], [slot], ['weather'], slot, [rain])
    assert hour_only_sa[0]['cells'][0]['text'] == ''
    assert hour_only_sa[0]['cells'][0]['text_hour'] == 'RA'
    cloud_rule = {
        'kind': 'cover', 'use_current': True, 'use_change': False, 'cover_now': ['BKN', 'OVC'],
    }
    sa_few = obs(0, cover='FEW', covers=['FEW'], sa=True, speci=False)
    sa_few['time'] = slot
    sp_cloud = obs(0, cover='BKN', covers=['FEW', 'BKN'], speci=True, sa=False)
    sp_cloud['time'] = slot + 20 * 60 * 1000
    clouds, _idx = _series([sa_few, sp_cloud], [slot], ['cover'], slot, [cloud_rule])
    assert clouds[0]['cells'][0]['text'] == 'FEW,BKN'
    assert clouds[0]['cells'][0]['text_hour'] == 'FEW,BKN'
    packed = _pack_series(clouds, [slot])
    unpacked = _unpack_series(packed, [slot])
    assert unpacked[0]['cells'][0]['text'] == 'FEW,BKN'
    assert unpacked[0]['cells'][0]['text_hour'] == 'FEW,BKN'
    quiet = evaluate_airport(only_hour, [], now, [hour_slot, half_slot])
    assert quiet['color'] == 'N' and quiet['rows'] == []
    merged = merge_hits([
        {'color': 'Y', 'score': 9, 'labels': ['甲'], 'rows': ['temperature']},
        {'color': 'R', 'score': 4, 'labels': ['乙'], 'rows': ['wind']},
    ])
    assert merged['color'] == 'R' and merged['score'] == 9 and merged['bar_color'] == 'Y'
    print('trend_alert self-check ok', len(slots))


if __name__ == '__main__':
    _self_check()
