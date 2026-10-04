"""从过去 7 天的预报报文推断首份发布整点和发布间隔。"""

import re
from collections import Counter

_AMD_COR = re.compile(r'\b(?:AMD|COR)\b', re.I)
_ISSUE = re.compile(r'\b(\d{2})(\d{2})(\d{2})Z\b', re.I)
_VALID = re.compile(r'\b(\d{2})(\d{2})/(\d{2})(\d{2})\b')

DOMESTIC_DELAY_MINUTES = 10
INTERNATIONAL_DELAY_MINUTES = 30


def issue_hour_if_validity_starts(content: str, start_hour: int):
    """排除修订报、更正报。有效期起始小时匹配时，返回发布整点。"""
    text = str(content or '').upper()
    if not text or _AMD_COR.search(text):
        return None
    valid = _VALID.search(text)
    issue = _ISSUE.search(text)
    if not valid or not issue or issue.start() > valid.start():
        return None
    if int(valid.group(2)) != int(start_hour):
        return None
    return int(issue.group(2))


def pick_most_common_hour(hours):
    """次数最多的整点。并列时取较早的那个。"""
    usable = [int(hour) for hour in hours if hour is not None]
    if not usable:
        return None
    counts = Counter(usable)
    best = max(counts.values())
    tied = [hour for hour, count in counts.items() if count == best]
    return min(tied)


def infer_schedule(reports):
    """
    reports: [{'wtype': 'FT'|'FC', 'content': '...'}, ...]
    有 FT 时间隔 6 小时，取有效期 06UTC 开始的发布整点。
    只有 FC 时间隔 3 小时，取有效期 03UTC 开始的发布整点。
    """
    items = list(reports or [])
    has_ft = any(str(item.get('wtype') or '').upper() == 'FT' for item in items)
    has_fc = any(str(item.get('wtype') or '').upper() == 'FC' for item in items)
    if has_ft:
        interval = 6
        start_hour = 6
        typed = [item for item in items if str(item.get('wtype') or '').upper() == 'FT']
    elif has_fc:
        interval = 3
        start_hour = 3
        typed = items
    else:
        return None
    hours = [
        issue_hour_if_validity_starts(item.get('content') or '', start_hour)
        for item in typed
    ]
    hour = pick_most_common_hour(hours)
    if hour is None:
        return None
    return {'taf_init_time': hour, 'import_check_interval': interval}


def default_delay_minutes(classification: str):
    kind = (classification or '').strip()
    if kind == '国内':
        return DOMESTIC_DELAY_MINUTES
    if kind == '国际':
        return INTERNATIONAL_DELAY_MINUTES
    return None
