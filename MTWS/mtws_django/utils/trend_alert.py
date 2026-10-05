"""实况趋势告警：规则校验与按实况序列计分。

常规要素的下降与时段内最高值比较，上升与时段内最低值比较。
云量、云高、天气现象的「由 / 过去出现」看时段内是否有一份满足，含特殊报。
"""

from __future__ import annotations

import math
import re
import time
import uuid
from typing import Any, Optional

ELEMENTS = (
    'temperature', 'dewpoint', 'rh', 'pressure', 'wind', 'visibility',
)
ELEMENT_LABELS = {
    'temperature': '气温',
    'dewpoint': '露点温度',
    'rh': '相对湿度',
    'pressure': '气压',
    'wind': '风速',
    'visibility': '能见度',
}
ELEMENT_UNITS = {
    'temperature': '℃',
    'dewpoint': '℃',
    'rh': '%',
    'pressure': 'hPa',
    'wind': 'm/s',
    'visibility': 'm',
}
COVERS = ('NSC', 'FEW', 'SCT', 'BKN', 'OVC')
COVER_RANK = {'FEW': 1, 'SCT': 2, 'BKN': 3, 'OVC': 4}
CLEAR_SKY = {'NSC', 'SKC', 'CLR', 'NCD'}
ROW_ORDER = (
    'temperature', 'dewpoint', 'rh', 'pressure', 'wind', 'visibility',
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
    return {'groups': []}


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
        return {'cover': cover, 'base': base, 'nsc': False}
    base = _num(min_height)
    if base is not None:
        return {'cover': 'NSC', 'base': base, 'nsc': False}
    return {'cover': 'NSC', 'base': None, 'nsc': True}


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
        'base': cloud['base'],
        'nsc': cloud['nsc'],
    }


def _element_value(obs: dict, name: str):
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


def _condition_match(cond: dict, obs: list, now_ms: int) -> bool:
    if len(obs) < 1:
        return False
    current = obs[-1]
    use_change = bool(cond.get('use_change'))
    use_current = bool(cond.get('use_current'))
    hours = _num(cond.get('hours')) or 0
    begin = int(now_ms - hours * HOUR_MS)
    kind = cond.get('kind')
    if not use_change and not use_current:
        return False

    if kind == 'element':
        direction = cond.get('direction')
        ok = True
        if use_change:
            amount = _num(cond.get('change_amount'))
            element = cond.get('change_element')
            if amount is None:
                return False
            values = []
            for item in _in_past_window(obs, begin, now_ms):
                value = _element_value(item, element)
                if value is not None:
                    values.append(value)
            after = _element_value(current, element)
            if not values or after is None:
                return False
            if direction == 'down':
                ok = (max(values) - after) >= amount
            else:
                ok = (after - min(values)) >= amount
        if ok and use_current:
            element = cond.get('current_element')
            limit = _num(cond.get('current_value'))
            value = _element_value(current, element)
            if value is None or limit is None:
                return False
            ok = value <= limit if direction == 'down' else value >= limit
        return ok

    if kind == 'weather':
        ok = True
        if use_change:
            codes = cond.get('past_codes') or []
            samples = _in_past_window(obs, begin, now_ms)
            if not samples:
                return False
            if codes:
                wanted = set(codes)
                ok = any(wanted.intersection(item['weather']) for item in samples)
            else:
                ok = any(not item['weather'] for item in samples)
        if ok and use_current:
            if cond.get('current_match') == 'none' or not (cond.get('current_codes') or []):
                ok = not current['weather']
            else:
                ok = bool(set(cond.get('current_codes') or []).intersection(current['weather']))
        return ok

    if kind == 'cover':
        ok = True
        if use_change:
            samples = _in_past_window(obs, begin, now_ms)
            if not samples:
                return False
            wanted_from = set(cond.get('cover_from') or [])
            wanted_to = set(cond.get('cover_to') or [])
            ok = any(item['cover'] in wanted_from for item in samples) and current['cover'] in wanted_to
        if ok and use_current:
            ok = current['cover'] in set(cond.get('cover_now') or [])
        return ok

    if kind == 'height':
        ok = True
        if use_change:
            samples = _in_past_window(obs, begin, now_ms)
            if not samples:
                return False
            ok = any(
                _height_side(item, _num(cond.get('from_height')), cond.get('from_cmp'), cond.get('from_nsc'))
                for item in samples
            )
            if ok:
                ok = _height_side(current, _num(cond.get('to_height')), cond.get('to_cmp'), cond.get('to_nsc'))
        if ok and use_current:
            ok = _height_side(current, _num(cond.get('now_height')), cond.get('now_cmp'), cond.get('now_nsc'))
        return ok
    return False


def _hit_rows(cond: dict) -> list:
    """时序表只列已经命中的常规要素和云高。天气现象、云量不占行。同一要素只保留一次。"""
    rows = []
    if cond.get('kind') == 'element':
        if cond.get('use_change'):
            rows.append(cond.get('change_element'))
        if cond.get('use_current'):
            rows.append(cond.get('current_element'))
    elif cond.get('kind') == 'height':
        rows.append('height')
    seen = []
    for row in rows:
        if row in (*ELEMENTS, 'height') and row not in seen:
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


def _series(obs: list, slots: list, keys: list, now_ms: Optional[int] = None) -> tuple:
    """各时刻格只放本格的整点或半点报。最新一份报文单独记在 latest，由页面放在最右列。"""
    cells = {key: [] for key in keys}
    for slot in slots:
        routine = _routine_for_slot(obs, slot)
        for key in keys:
            cells[key].append(_format_cell(key, routine, False))
    latest_obs = _latest_observation(obs, slots, now_ms)
    rows = []
    for key in ROW_ORDER:
        if key not in cells:
            continue
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
    for cond in enabled:
        if cond.get('role') == 'veto':
            continue
        if not _condition_match(cond, obs, now_ms):
            continue
        # 只收录整条条件已经命中的描述，未命中的不出现在四字代码下方
        label = cond.get('label') or ''
        role = cond.get('role')
        if role == 'deduct' and label:
            label = f'「{label}」'
        labels.append(label)
        rows.extend(_hit_rows(cond))
        score = _num(cond.get('score')) or 0
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
    }


def merge_hits(hits: list) -> Optional[dict]:
    alerting = [hit for hit in hits if hit]
    if not alerting:
        return None
    best_color = max(alerting, key=lambda hit: (COLOR_RANK.get(hit['color'], 0), hit.get('score') or 0))
    best_score = max(alerting, key=lambda hit: ((hit.get('score') or 0), COLOR_RANK.get(hit['color'], 0)))
    labels = []
    rows = []
    for hit in alerting:
        for label in hit['labels']:
            if label not in labels:
                labels.append(label)
        for row in hit['rows']:
            if row not in rows:
                rows.append(row)
    return {
        'color': best_color['color'],
        'score': best_score['score'],
        'bar_color': best_score['color'],
        'labels': labels,
        'rows': rows,
    }


def evaluate_airport(obs: list, groups: list, now_ms: int, slots: list) -> dict:
    """时序只保留命中的常规要素和云高。未达阈值的机场不铺全部要素。"""
    ordered = sorted(obs, key=lambda item: item['time'])
    hits = []
    for group in groups or []:
        if not group.get('enabled', True):
            continue
        hits.append(score_group(group, ordered, now_ms))
    merged = merge_hits(hits)
    keys = merged['rows'] if merged else []
    rows, _speci = _series(ordered, slots, keys, now_ms)
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
    cond = {
        'id': str(raw.get('id') or new_id()),
        'enabled': _bool(raw.get('enabled'), True),
        'role': role,
        'kind': kind,
        'score': score if score is not None else 0,
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
        current_match = 'none' if str(raw.get('current_match') or '') == 'none' else 'any'
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
    return {'groups': groups}, errors


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
            if not text:
                continue
            points.append({'t': int(slot), 'text': text, 'speci': bool(cell.get('speci'))})
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
                cells.append({'text': hit.get('text') or '', 'speci': bool(hit.get('speci'))})
            else:
                cells.append({'text': '', 'speci': False})
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

    logger = logging.getLogger('mtws.trend')
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
        for code in inside:
            try:
                groups = groups_for_airport(config, code, universe)
                result = evaluate_airport(by_airport.get(code) or [], groups, now_ms, slots)
                color = result['color']
                old = previous.get(code)
                handled = bool(
                    old and old.handled and old.handled_signature == color and color in ('R', 'Y', 'G')
                )
                AirportTrendAlert.objects.update_or_create(
                    airport_4code=code,
                    defaults={
                        'color': color,
                        'score': result['score'],
                        'bar_color': result.get('bar_color') or color,
                        'labels': result['labels'],
                        'series': _pack_series(result['rows'], slots),
                        'handled': handled,
                        'handled_signature': color if handled else '',
                    },
                )
            except Exception:
                logger.exception('实况趋势告警写入失败: %s', code)
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
    return {'slots': slots, 'airports': airports, 'scope': scope, 'universe_count': len(universe)}


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
    assert _hit_rows({'kind': 'weather', 'use_change': True}) == []
    assert _hit_rows({'kind': 'cover', 'use_change': True}) == []
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
    assert scored['rows'] == ['temperature', 'visibility']
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
