"""
marks 航班告警：按 event.at 写 events.warning；并写入机场级五档色。
"""

import logging
from calendar import monthrange
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from django.utils import timezone

from parsers.models import Flight, Metar, Taf
from utils.time_manager import TimeManager

logger = logging.getLogger('mtws.marks_alert')

HOUR_MS = 3600 * 1000
RANK = {'R': 4, 'Y': 3, 'G': 2, 'N': 1}
EMPTY_WARNING = ['N', 'N', 'N', 'N', 'N']


def default_warning() -> List[str]:
    return list(EMPTY_WARNING)


def normalize_warning(value) -> List[str]:
    if isinstance(value, list) and len(value) >= 5:
        out = []
        for i in range(5):
            lv = value[i] if value[i] in RANK else 'N'
            out.append(lv)
        return out
    if isinstance(value, str) and value in RANK:
        return [value] * 5
    return default_warning()


def warning_is_ready(value) -> bool:
    return isinstance(value, list) and len(value) >= 5


IDLE_KINDS = frozenset({'off', 'lnd', 'dst'})


def computed_alerts_from_flight(flight) -> Dict[str, Dict[str, str]]:
    """概览/地图用：由 Flight 三色字段组装原 computed_alerts 形状。"""
    empty = default_warning()
    if flight is None:
        metar, taf, airport = empty, empty, empty
    else:
        metar = flight.as_alert_levels('metar_highest_alert')
        taf = flight.as_alert_levels('taf_highest_alert')
        airport = flight.as_alert_levels('airport_highest_alert')
    out = {}
    for m in range(5):
        out[f'margin_{m}'] = {
            'highest_alert': airport[m],
            'taf_highest_alert': taf[m],
            'metar_highest_alert': metar[m],
        }
    return out


def _window_parts(win) -> tuple:
    start_ms, end_ms, alert, inclusive_end = win[0], win[1], win[2], win[3]
    source = win[4] if len(win) > 4 else 'all'
    return start_ms, end_ms, alert, inclusive_end, source


def _at_in_window(at: int, start_ms, end_ms, inclusive_end: bool) -> bool:
    if inclusive_end:
        return start_ms <= at <= end_ms
    return start_ms <= at < end_ms


def event_identity(event: Dict) -> str:
    fid = event.get('flightId')
    if fid:
        return f"id:{fid}"
    other = event.get('other') or {}
    fn = other.get('flightNo') or ''
    return f"fb:{fn}|{event.get('at')}|{event.get('kind')}"


def _max_alert(a: Optional[str], b: Optional[str]) -> str:
    aa = a if a in RANK else 'N'
    bb = b if b in RANK else 'N'
    return aa if RANK[aa] >= RANK[bb] else bb


def _g(obj: Any, key: str, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


class MarksAlertCalculator:
    def __init__(self, time_mode='current'):
        self.time_mode = time_mode
        self.ref_time = TimeManager.get_current_time_utc(time_mode)

    def apply(
        self,
        full_airports: Optional[Iterable[str]] = None,
        changed_keys_by_airport: Optional[Dict[str, Sequence[str]]] = None,
    ) -> None:
        full = {c for c in (full_airports or []) if c}
        partial = {
            code: set(keys)
            for code, keys in (changed_keys_by_airport or {}).items()
            if code and code not in full and keys
        }
        if not full and not partial:
            return
        from utils.flight_selection import selected_carrier_codes
        self.selected_carriers = selected_carrier_codes()
        for code in full:
            try:
                self._recalc_airport(code, keys=None)
            except Exception as e:
                logger.error(f"marks 全场告警计算失败 {code}: {e}", exc_info=True)
        for code, keys in partial.items():
            try:
                self._recalc_airport(code, keys=keys)
            except Exception as e:
                logger.error(f"marks 航班告警计算失败 {code}: {e}", exc_info=True)

    def _recalc_airport(self, airport: str, keys: Optional[Set[str]]) -> None:
        row = (
            Flight.objects.filter(airport_4code=airport)
            .order_by('-created_at')
            .first()
        )
        if not row:
            return
        events = row.as_events()
        metar = (
            Metar.objects.filter(airport_4code=airport, data_status__in=['N', 'C'])
            .order_by('-metar_observation_time')
            .first()
        )
        taf = (
            Taf.objects.filter(airport_4code=airport, data_status__in=['N', 'C'])
            .order_by('-created_at')
            .first()
        )
        windows = self._build_windows(metar, taf)
        from utils.flight_selection import event_is_selected
        selected = getattr(self, 'selected_carriers', None)
        if selected is None:
            from utils.flight_selection import selected_carrier_codes
            selected = selected_carrier_codes()
        changed = False
        for ev in events:
            if not event_is_selected(ev, selected):
                continue
            if keys is not None and event_identity(ev) not in keys:
                continue
            new_w = self._warning_for_event(ev, windows)
            if new_w != normalize_warning(ev.get('warning')):
                ev['warning'] = new_w
                changed = True
            elif not warning_is_ready(ev.get('warning')):
                ev['warning'] = new_w
                changed = True
        scoped = [ev for ev in events if event_is_selected(ev, selected)]
        metar_h, taf_h, air_h = self._airport_alert_levels(scoped, windows)
        filters = {'airport_4code': airport}
        if row.pk is not None:
            filters['pk'] = row.pk
        payload = {
            'metar_highest_alert': metar_h,
            'taf_highest_alert': taf_h,
            'airport_highest_alert': air_h,
            'updated_at': timezone.now(),
        }
        if changed:
            payload['events'] = events
        Flight.objects.filter(**filters).update(**payload)

    def _warning_for_event(self, event: Dict, windows: Dict) -> List[str]:
        try:
            at = int(event.get('at'))
        except (TypeError, ValueError):
            return default_warning()
        result = default_warning()
        for m in range(5):
            lv = 'N'
            for win in windows[m]:
                start_ms, end_ms, alert, inclusive_end, _src = _window_parts(win)
                if alert not in RANK or alert == 'N':
                    continue
                if _at_in_window(at, start_ms, end_ms, inclusive_end):
                    lv = _max_alert(lv, alert)
            result[m] = lv
        return result

    def _airport_alert_levels(self, events: list, windows: Dict) -> tuple:
        """未排除航班上分别取 METAR / TAF 最高，再合成机场最高。"""
        metar_h = default_warning()
        taf_h = default_warning()
        for ev in events or []:
            if not isinstance(ev, dict) or ev.get('kind') in IDLE_KINDS:
                continue
            try:
                at = int(ev.get('at'))
            except (TypeError, ValueError):
                continue
            for m in range(5):
                for win in windows[m]:
                    start_ms, end_ms, alert, inclusive_end, source = _window_parts(win)
                    if alert not in RANK or alert == 'N':
                        continue
                    if not _at_in_window(at, start_ms, end_ms, inclusive_end):
                        continue
                    if source == 'metar':
                        metar_h[m] = _max_alert(metar_h[m], alert)
                    else:
                        taf_h[m] = _max_alert(taf_h[m], alert)
        air_h = [_max_alert(metar_h[i], taf_h[i]) for i in range(5)]
        return metar_h, taf_h, air_h

    def _build_windows(self, metar, taf) -> Dict[int, List[tuple]]:
        """margin -> list of (start_ms, end_ms, alert, inclusive_end)."""
        out = {m: [] for m in range(5)}
        obs = _g(metar, 'metar_observation_time') if metar else None
        metar_lv = _g(metar, 'metar_warning', 'N') if metar else 'N'
        if obs is not None and metar_lv and metar_lv != 'N':
            try:
                obs_ms = int(obs)
            except (TypeError, ValueError):
                obs_ms = None
            if obs_ms is not None:
                for m in range(5):
                    out[m].append((obs_ms, obs_ms + (m + 1) * HOUR_MS, metar_lv, False, 'metar'))

        if not taf:
            return out

        subject_start = _g(taf, 'subject_validity_period_start')
        subject_end = _g(taf, 'subject_validity_period_end')
        subject_lv = _g(taf, 'subject_warning', 'N')
        self._add_period_windows(out, subject_start, subject_end, subject_lv, expand=True)

        change_groups = []
        for i in range(1, 9):
            ctype = (_g(taf, f'change_{i}_type') or '').strip()
            cstart = _g(taf, f'change_{i}_validity_period_start')
            cend = _g(taf, f'change_{i}_validity_period_end')
            clv = _g(taf, f'change_{i}_warning')
            if not ctype:
                continue
            change_groups.append({
                'index': i,
                'type': ctype,
                'start': cstart,
                'end': cend,
                'warning': clv,
            })
            self._add_period_windows(out, cstart, cend, clv, expand=True)

        self._add_becmg_gaps(out, taf, change_groups)

        temp_fields = [
            ('subject_max_temp1_time', 'subject_max_temp1_warning'),
            ('subject_max_temp2_time', 'subject_max_temp2_warning'),
            ('subject_min_temp1_time', 'subject_min_temp1_warning'),
            ('subject_min_temp2_time', 'subject_min_temp2_warning'),
        ]
        for t_field, w_field in temp_fields:
            t_str = _g(taf, t_field)
            t_lv = _g(taf, w_field)
            t_ms = self._ddhh_to_ms(t_str)
            if t_ms is None or not t_lv or t_lv == 'N':
                continue
            for m in range(5):
                out[m].append((t_ms - m * HOUR_MS, t_ms + m * HOUR_MS, t_lv, True, 'taf'))
        return out

    def _add_period_windows(self, out, start_str, end_str, alert, expand: bool):
        if not alert or alert == 'N':
            return
        start_ms = self._ddhh_to_ms(start_str)
        end_ms = self._ddhh_to_ms(end_str)
        if start_ms is None or end_ms is None:
            return
        end_bound = end_ms + HOUR_MS
        for m in range(5):
            if expand:
                lo = start_ms - m * HOUR_MS
                hi = end_bound + m * HOUR_MS
            else:
                lo = start_ms
                hi = end_bound
            out[m].append((lo, hi, alert, False, 'taf'))

    def _add_becmg_gaps(self, out, taf, change_groups: List[Dict]):
        for becmg in change_groups:
            if becmg['type'] != 'BECMG' or not becmg['start']:
                continue
            preceding_end, preceding_lv = self._find_preceding(taf, becmg, change_groups)
            if not preceding_end:
                continue
            gap_lv = _max_alert(preceding_lv, becmg.get('warning'))
            if not gap_lv or gap_lv == 'N':
                continue
            lo = self._ddhh_to_ms(preceding_end)
            hi = self._ddhh_to_ms(becmg['start'])
            if lo is None or hi is None or lo >= hi:
                continue
            for m in range(5):
                out[m].append((lo, hi, gap_lv, False, 'taf'))

    def _find_preceding(self, taf, becmg: Dict, change_groups: List[Dict]):
        becmg_start = becmg['start']
        for g in reversed(change_groups):
            if g['index'] >= becmg['index']:
                continue
            if g['type'] not in ('FROM', 'BECMG') or not g.get('end'):
                continue
            if self._ddhh_before_or_equal(g['end'], becmg_start):
                return g['end'], g.get('warning') or 'N'
        return _g(taf, 'subject_validity_period_end'), _g(taf, 'subject_warning', 'N')

    def _ddhh_before_or_equal(self, t1, t2) -> bool:
        a = self._ddhh_to_ms(t1)
        b = self._ddhh_to_ms(t2)
        if a is None or b is None:
            return False
        return a <= b

    def _ddhh_to_ms(self, value) -> Optional[int]:
        if not value:
            return None
        s = str(value).strip()
        if len(s) == 4:
            day, hour, minute = int(s[:2]), int(s[2:4]), 0
        elif len(s) == 6:
            day, hour, minute = int(s[:2]), int(s[2:4]), int(s[4:6])
        else:
            return None
        add_day = False
        if hour == 24:
            hour = 0
            add_day = True
        if hour > 23 or minute > 59 or day < 1 or day > 31:
            return None
        ref = self.ref_time
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=dt_timezone.utc)
        candidates = []
        for month_delta in (-1, 0, 1):
            month = ref.month + month_delta
            year = ref.year
            if month < 1:
                month += 12
                year -= 1
            elif month > 12:
                month -= 12
                year += 1
            last = monthrange(year, month)[1]
            if day > last:
                continue
            try:
                dt = datetime(year, month, day, hour, minute, 0, tzinfo=dt_timezone.utc)
            except ValueError:
                continue
            if add_day:
                dt += timedelta(days=1)
            candidates.append(dt)
        if not candidates:
            return None
        best = min(candidates, key=lambda d: abs((d - ref).total_seconds()))
        return int(best.timestamp() * 1000)
