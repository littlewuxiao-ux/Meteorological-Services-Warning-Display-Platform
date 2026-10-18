"""
三段式航班时段统计。

按机场把航班整理成若干个整点时段。每个时段是字符串
「在飞落地数-全部落地数-起飞数」，例如 ``1-2-3``。
三种计数都是 0 时，该时段为空字符串。

统计窗口由调用时传入的两个时间点决定，只计入落在二者之间的航班。
区间为左闭右开：``start <= 航班时刻 < end``。
第 0 格是 ``start`` 所在的整点，之后每格 1 小时，直到覆盖 ``end`` 之前的最后一个整点。
结果长度随这两个时间变化，不再固定为 48。

用法::

    from three_segment_flight import build_three_segment_slots

    slots = build_three_segment_slots(
        flights,
        "ZBAA",
        start,
        end,
    )

``flights`` 是航班行的序列，每一行支持 ``字段 in row`` 和 ``row[字段]``
（字典或 pandas Series 都可以）。``start`` 和 ``end`` 按无时区的北京时间理解，
且 ``end`` 必须晚于 ``start``。

每行用到的字段：

- ``arrivalAirport`` / ``departureAirport``：机场四字码
- ``ata``：有值的到达航班不计入
- ``atd``：到达航班有值时计入「在飞」；出发航班有值时不计入起飞
- 到达时刻，按 ``eta``、``sta``、``pta`` 的顺序取第一个有值的字段
- 起飞时刻，按 ``etd``、``std``、``ptd`` 的顺序取第一个有值的字段

时间字段是毫秒时间戳。换算时先当作 UTC，再加 8 小时，得到北京时间。
"""

import math
from datetime import datetime, timedelta
from typing import Iterable, List, Mapping, Optional, Sequence, Tuple

# 毫秒时间戳换算成北京时间时加上的小时数。
BEIJING_OFFSET_HOURS = 8

# 到达时刻优先级：预计 > 计划 > 公布。
ARRIVAL_TIME_FIELDS: Sequence[str] = ("eta", "sta", "pta")

# 起飞时刻优先级：预计 > 计划 > 公布。已起飞的出发航班不进入本统计。
DEPARTURE_TIME_FIELDS: Sequence[str] = ("etd", "std", "ptd")


def build_three_segment_slots(
    flights: Iterable[Mapping],
    airport: str,
    start: datetime,
    end: datetime,
) -> List[str]:
    """统计一个机场在两个时间点之间的三段式时段。

    Args:
        flights: 航班行。字段见模块说明。
        airport: 机场四字码。到达机场或起飞机场等于它的航班才会计入。
        start: 窗口起点（北京时间，可不带时区）。该时刻本身计入。
        end: 窗口终点（北京时间，可不带时区）。该时刻本身不计入。

    Returns:
        每个整点一时段一项。有航班的时段形如 ``在飞-落地-起飞``，
        没有航班的时段是空字符串。
    """
    start_hour, slot_count = _window_slots(start, end)
    landing_inflight = [0] * slot_count
    landing_all = [0] * slot_count
    takeoff_all = [0] * slot_count

    for row in flights:
        if _airport_of(row, "arrivalAirport") == airport and not _has_field(row, "ata"):
            arrival_time = _pick_beijing_time(row, ARRIVAL_TIME_FIELDS)
            slot = _slot_index(arrival_time, start, end, start_hour, slot_count)
            if slot is not None:
                landing_all[slot] += 1
                if _has_field(row, "atd"):
                    landing_inflight[slot] += 1

        if _airport_of(row, "departureAirport") == airport and not _has_field(row, "atd"):
            departure_time = _pick_beijing_time(row, DEPARTURE_TIME_FIELDS)
            slot = _slot_index(departure_time, start, end, start_hour, slot_count)
            if slot is not None:
                takeoff_all[slot] += 1

    return _format_slots(landing_inflight, landing_all, takeoff_all)


def _window_slots(start: datetime, end: datetime) -> Tuple[datetime, int]:
    """返回窗口起点所在整点，以及需要的时段个数。"""
    if end <= start:
        raise ValueError("end 必须晚于 start")
    start_hour = _floor_hour(start)
    end_hour = _floor_hour(end)
    # end 落在整点上时，该整点不占用时段；否则要带上 end 所在的那一小时。
    if end == end_hour:
        slot_count = int((end_hour - start_hour).total_seconds() // 3600)
    else:
        slot_count = int((end_hour - start_hour).total_seconds() // 3600) + 1
    return start_hour, slot_count


def _format_slots(
    landing_inflight: Sequence[int],
    landing_all: Sequence[int],
    takeoff_all: Sequence[int],
) -> List[str]:
    """把三组计数拼成时段字符串。"""
    slots = []
    for inflight, landing, takeoff in zip(landing_inflight, landing_all, takeoff_all):
        if inflight == 0 and landing == 0 and takeoff == 0:
            slots.append("")
        else:
            slots.append(f"{inflight}-{landing}-{takeoff}")
    return slots


def _slot_index(
    flight_time: Optional[datetime],
    start: datetime,
    end: datetime,
    start_hour: datetime,
    slot_count: int,
) -> Optional[int]:
    """航班落在窗口内时，返回它相对起点整点的小时序号。"""
    if flight_time is None or flight_time < start or flight_time >= end:
        return None
    hours = int((_floor_hour(flight_time) - start_hour).total_seconds() // 3600)
    if 0 <= hours < slot_count:
        return hours
    return None


def _floor_hour(moment: datetime) -> datetime:
    return moment.replace(minute=0, second=0, microsecond=0)


def _pick_beijing_time(row: Mapping, fields: Sequence[str]) -> Optional[datetime]:
    """按字段顺序取第一个有效毫秒时间戳，并换成北京时间。"""
    for field in fields:
        if not _has_field(row, field):
            continue
        parsed = _beijing_from_millis(row[field])
        if parsed is not None:
            return parsed
    return None


def _beijing_from_millis(raw) -> Optional[datetime]:
    """毫秒时间戳转北京时间。无法解析时返回 None。"""
    try:
        millis = float(str(raw).strip())
        utc_time = datetime.utcfromtimestamp(millis / 1000)
    except (TypeError, ValueError, OSError, OverflowError):
        return None
    return utc_time + timedelta(hours=BEIJING_OFFSET_HOURS)


def _airport_of(row: Mapping, field: str) -> str:
    if not _has_field(row, field):
        return ""
    return str(row[field]).strip()


def _has_field(row: Mapping, field: str) -> bool:
    """字段存在，且不是空值。"""
    try:
        if field not in row:
            return False
        value = row[field]
    except (KeyError, TypeError, ValueError):
        return False
    if value is None:
        return False
    if isinstance(value, float) and math.isnan(value):
        return False
    if type(value).__name__ in ("NAType", "NaTType"):
        return False
    return bool(str(value).strip())
