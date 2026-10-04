"""按云量下限筛选云组后，取最低云底高。"""

import re

CLOUD_AMT_ORDER = ('FEW', 'SCT', 'BKN', 'OVC')
CLOUD_AMT_RANK = {name: index for index, name in enumerate(CLOUD_AMT_ORDER)}
DEFAULT_MIN_CLOUD_AMT = 'SCT'

_CLOUD_TOKEN = re.compile(r'(FEW|SCT|BKN|OVC)\s*(\d+)', re.IGNORECASE)


def normalize_cloud_amt(value, default=DEFAULT_MIN_CLOUD_AMT) -> str:
    amount = str(value or '').strip().upper()
    if amount in CLOUD_AMT_RANK:
        return amount
    return default


def cloud_amount_qualifies(amount, min_cloud_amt) -> bool:
    """云量达到下限（含）时返回 True。FEW < SCT < BKN < OVC。"""
    rank = CLOUD_AMT_RANK.get(str(amount or '').strip().upper())
    if rank is None:
        return False
    floor = normalize_cloud_amt(min_cloud_amt)
    return rank >= CLOUD_AMT_RANK[floor]


def lowest_height_in_text(text, min_cloud_amt):
    """在文本里的合格云组中取最低云底高；没有合格云组时返回 None。"""
    heights = []
    for match in _CLOUD_TOKEN.finditer(str(text or '')):
        if cloud_amount_qualifies(match.group(1), min_cloud_amt):
            heights.append(int(match.group(2)))
    return min(heights) if heights else None


def lowest_height_in_cloud_strings(clouds, min_cloud_amt):
    parts = [str(cloud) for cloud in clouds if cloud]
    return lowest_height_in_text(' '.join(parts), min_cloud_amt)


def _amount_and_base(cloud):
    amount = str(getattr(cloud, 'type', '') or '').strip().upper()
    base = getattr(cloud, 'base', None)
    if amount not in CLOUD_AMT_RANK or base is None:
        match = _CLOUD_TOKEN.search(str(getattr(cloud, 'repr', '') or ''))
        if match:
            if amount not in CLOUD_AMT_RANK:
                amount = match.group(1).upper()
            if base is None:
                base = int(match.group(2))
    return amount, base


def cloud_object_amount(cloud) -> str:
    amount, _base = _amount_and_base(cloud)
    return amount


def lowest_base_from_cloud_objects(clouds, min_cloud_amt):
    """在云对象列表的合格云组中取最低云底高。"""
    heights = []
    for cloud in clouds or []:
        amount, base = _amount_and_base(cloud)
        if base is None or not cloud_amount_qualifies(amount, min_cloud_amt):
            continue
        heights.append(int(base))
    return min(heights) if heights else None


def format_cloud_min(height) -> str:
    if height is None:
        return ''
    return f'{int(height):03d}'


def resolve_min_cloud_amt(airport_4code: str) -> str:
    """机场自身有配置时用该行，否则用 default 行，再否则用 SCT。"""
    from core.models import AirportAlertThresholds

    code = (airport_4code or '').strip()
    row = None
    if code:
        row = (
            AirportAlertThresholds.objects.filter(airport_4code=code)
            .only('min_cloud_amt')
            .first()
        )
    if row is None:
        row = (
            AirportAlertThresholds.objects.filter(airport_4code='default')
            .only('min_cloud_amt')
            .first()
        )
    return normalize_cloud_amt(getattr(row, 'min_cloud_amt', None))
