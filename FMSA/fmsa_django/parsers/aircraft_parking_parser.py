"""飞机停场：一机场一行，随航班同一批数据增量更新。"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd
from django.conf import settings

from data_adapters.adapter_factory import AdapterFactory
from runtime_db.models import AircraftParkingInfo
from utils.aircraft_parking import (
    latest_fetched_at,
    normalize_intervals,
    parking_ac_regs,
    parking_is_on,
    parking_payload,
)
from utils.time_manager import TimeManager

logger = logging.getLogger('fmsa.parsers')

HOUR_MS = 3600 * 1000
STALE_MS = 10 * 1000
MAX_RECORDS = 500


class AircraftParkingParser:
    def __init__(self, time_mode='current', token=None):
        self.time_mode = time_mode
        self.token = token
        self.current_time = TimeManager.get_current_time_local(time_mode)
        config = settings.FMSA_CONFIG.get('AIRCRAFT_PARKING_CONFIG', {})
        self.past_hours = int(config.get('PAST_HOURS', 72))
        self.carrier_code = str(config.get('CARRIER_CODE', 'O3') or 'O3').strip()
        self.max_records = int(config.get('MAX_RECORDS', MAX_RECORDS) or MAX_RECORDS)
        self._fingerprints = {}

    def parse_and_save(self):
        return self.parse_aircraft_parking_data()

    def parse_aircraft_parking_data(self, flight_df=None, fetched_at=None):
        if self.time_mode == 'test':
            logger.info('测试模式跳过停场解析')
            return {'success': True, 'message': '测试模式跳过停场解析', 'airport_count': 0, 'skipped': True}

        start_time = datetime.now()
        logger.info('开始解析飞机停场数据')
        try:
            now_ms = int(self.current_time.timestamp() * 1000)
            watermark = latest_fetched_at()
            df, used_at, mode = self._load_flights(flight_df, fetched_at, now_ms, watermark)
            if df is None or getattr(df, 'empty', True):
                return {'success': False, 'message': '未获取到停场航班数据', 'airport_count': 0}

            df = self._o3_rows(df)
            occupancy, intervals = self._load_state()
            if mode == 'bootstrap':
                occupancy, intervals = {}, {}
                self._rebuild_from_flights(df, occupancy, intervals, now_ms)
                self._fingerprints = self._all_fingerprints(df)
            else:
                self._apply_batch(df, occupancy, intervals, now_ms)

            touched = set(occupancy.values()) | set(intervals)
            self._save_state(occupancy, intervals, used_at, now_ms, touched)
            duration = (datetime.now() - start_time).total_seconds()
            parked = sorted({code for code in occupancy.values() if code})
            logger.info(f'停场解析完成 {mode}，{len(parked)} 个机场有停场，耗时 {duration:.2f}s: {parked}')
            return {
                'success': True,
                'message': '飞机停场数据解析成功',
                'airport_count': len(parked),
                'duration': duration,
                'mode': mode,
            }
        except Exception as exc:
            logger.exception('解析飞机停场数据失败')
            return {'success': False, 'message': f'解析失败: {exc}', 'airport_count': 0}

    def _load_flights(self, flight_df, fetched_at, now_ms: int, watermark: Optional[int]):
        if flight_df is not None and not getattr(flight_df, 'empty', True) and fetched_at:
            fetch_ms = int(fetched_at)
            if watermark and fetch_ms + STALE_MS < watermark:
                logger.info('传入航班数据早于停场水位，忽略并自行补拉')
            elif not watermark:
                logger.info('停场表为空，首次按过去 72 小时补数')
                return self._fetch_range(now_ms - self.past_hours * HOUR_MS, now_ms), now_ms, 'bootstrap'
            else:
                return flight_df, fetch_ms, 'incremental'

        if not watermark:
            start = now_ms - self.past_hours * HOUR_MS
            df = self._fetch_range(start, now_ms)
            return df, now_ms, 'bootstrap'

        flight_success = self._flight_success_ms()
        if flight_success is not None and watermark + STALE_MS >= flight_success:
            df = self._fetch_range(now_ms - 24 * HOUR_MS, now_ms + 48 * HOUR_MS)
            return df, now_ms, 'incremental'

        start = int(watermark)
        end = now_ms + 48 * HOUR_MS
        logger.info(f'停场水位落后，补拉 {start} -> {end}')
        df = self._fetch_range(start, end)
        return df, now_ms, 'catchup'

    def _fetch_range(self, start_ms: int, end_ms: int):
        adapter = AdapterFactory.create_adapter(time_mode=self.time_mode, token=self.token)
        return adapter.get_flight_data(start_ms=start_ms, end_ms=end_ms)

    def _flight_success_ms(self) -> Optional[int]:
        value = (settings.FMSA_CONFIG.get('FLIGHT_DATA_STATUS') or {}).get('last_success_time')
        if value is None:
            return None
        try:
            return int(value.timestamp() * 1000)
        except Exception:
            return None

    def _o3_rows(self, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty or 'carrier' not in df.columns or 'acReg' not in df.columns:
            return pd.DataFrame()
        carrier = df['carrier'].astype(str).str.strip()
        ac = df['acReg'].astype(str).str.strip()
        out = df[(carrier == self.carrier_code) & (ac != '') & (ac.str.lower() != 'nan')]
        return out.copy()

    def _load_state(self) -> Tuple[Dict[str, str], Dict[str, list]]:
        occupancy = {}
        intervals = {}
        for row in AircraftParkingInfo.objects.all():
            code = str(row.airport_4code or '').strip().upper()
            if not code:
                continue
            intervals[code] = normalize_intervals(row.aircraft_parked_status_records)
            for ac_reg in parking_ac_regs(row.parking):
                occupancy[ac_reg] = code
        return occupancy, intervals

    def _all_fingerprints(self, df: pd.DataFrame) -> dict:
        out = {}
        if df.empty or 'acReg' not in df.columns:
            return out
        for ac_reg, group in df.groupby('acReg'):
            key = str(ac_reg).strip()
            if key:
                out[key] = self._fingerprint(group)
        return out

    def _fingerprint(self, group: pd.DataFrame) -> tuple:
        rows = []
        for _, row in group.iterrows():
            rows.append((
                self._text(row, 'flightId'),
                self._airport(row, 'departureAirport'),
                self._airport(row, 'arrivalAirport'),
                self._ms(row, 'atd'),
                self._ms(row, 'ata'),
            ))
        rows.sort()
        return tuple(rows)

    def _apply_batch(self, df: pd.DataFrame, occupancy: dict, intervals: dict, now_ms: int):
        if df.empty or 'acReg' not in df.columns:
            return
        next_fp = {}
        for ac_reg, group in df.groupby('acReg'):
            key = str(ac_reg).strip()
            if not key:
                continue
            fp = self._fingerprint(group)
            next_fp[key] = fp
            if self._fingerprints.get(key) == fp:
                continue
            self._apply_aircraft(key, group, occupancy, intervals, now_ms)
        self._fingerprints = next_fp

    def _rebuild_from_flights(self, df: pd.DataFrame, occupancy: dict, intervals: dict, now_ms: int):
        if df.empty or 'acReg' not in df.columns:
            return
        for ac_reg, group in df.groupby('acReg'):
            key = str(ac_reg).strip()
            if key:
                self._apply_aircraft(key, group, occupancy, intervals, now_ms, replace=True)

    def _apply_aircraft(self, ac_reg: str, group: pd.DataFrame, occupancy: dict, intervals: dict, now_ms: int, replace=False):
        events = []
        in_air = False
        last_ata_ap = None
        last_ata_ms = None
        for _, row in group.iterrows():
            dep = self._airport(row, 'departureAirport')
            arr = self._airport(row, 'arrivalAirport')
            atd = self._ms(row, 'atd')
            ata = self._ms(row, 'ata')
            if atd:
                events.append((atd, 0, 'atd', dep))
            if ata:
                events.append((ata, 1, 'ata', arr))
                if last_ata_ms is None or ata >= last_ata_ms:
                    last_ata_ms = ata
                    last_ata_ap = arr
            if atd and (ata is None or ata > now_ms) and atd <= now_ms:
                in_air = True
        events.sort()
        current = None if replace else occupancy.get(ac_reg)
        if replace:
            occupancy.pop(ac_reg, None)
        for when, _order, kind, airport in events:
            if not airport:
                continue
            if kind == 'atd':
                parked = occupancy.get(ac_reg)
                if parked:
                    self._leave(ac_reg, parked, when, occupancy, intervals)
            elif kind == 'ata':
                parked = occupancy.get(ac_reg)
                if parked and parked != airport:
                    self._leave(ac_reg, parked, when, occupancy, intervals)
                if occupancy.get(ac_reg) != airport:
                    self._arrive(ac_reg, airport, when, occupancy, intervals)
                current = airport
        if in_air:
            parked = occupancy.get(ac_reg)
            if parked:
                leave_at = None
                for when, _order, kind, airport in events:
                    if kind == 'atd' and airport == parked:
                        leave_at = when
                self._leave(ac_reg, parked, leave_at or now_ms, occupancy, intervals)
            return
        if occupancy.get(ac_reg):
            return
        if last_ata_ap and last_ata_ms and (current == last_ata_ap or current is None):
            self._arrive(ac_reg, last_ata_ap, last_ata_ms, occupancy, intervals)

    def _arrive(self, ac_reg: str, airport: str, when: int, occupancy: dict, intervals: dict):
        occupancy[ac_reg] = airport
        items = list(intervals.get(airport) or [])
        open_row = next((item for item in items if item[1] is None), None)
        if open_row is None:
            items.append([int(when), None])
        intervals[airport] = normalize_intervals(items, when)

    def _leave(self, ac_reg: str, airport: str, when: int, occupancy: dict, intervals: dict):
        if occupancy.get(ac_reg) == airport:
            occupancy.pop(ac_reg, None)
        others = [code for code, place in occupancy.items() if place == airport]
        if others:
            return
        items = []
        for start, end in intervals.get(airport) or []:
            if end is None:
                items.append([start, int(when)])
            else:
                items.append([start, end])
        intervals[airport] = normalize_intervals(items, when)

    def _save_state(self, occupancy: dict, intervals: dict, fetched_at: int, now_ms: int, touched: set):
        by_airport = {}
        for ac_reg, airport in occupancy.items():
            by_airport.setdefault(airport, []).append(ac_reg)
        existing = {str(row.airport_4code).strip().upper(): row for row in AircraftParkingInfo.objects.all()}
        upsert_codes = set(by_airport) | set(touched) | set(existing)
        for code in sorted(upsert_codes):
            if not code or len(code) != 4:
                continue
            regs = by_airport.get(code) or []
            row = existing.get(code)
            raw_iv = intervals[code] if code in intervals else (row.aircraft_parked_status_records if row else [])
            records = normalize_intervals(raw_iv, now_ms)
            if row is None:
                self._trim_if_needed()
                if AircraftParkingInfo.objects.count() >= self.max_records:
                    logger.warning(f'停场表已满，跳过新机场 {code}')
                    continue
                AircraftParkingInfo.objects.create(
                    airport_4code=code,
                    parking=parking_payload(regs),
                    aircraft_parked_status_records=records,
                    fetched_at=int(fetched_at),
                )
                continue
            row.parking = parking_payload(regs)
            row.aircraft_parked_status_records = records
            row.fetched_at = int(fetched_at)
            row.save(update_fields=['parking', 'aircraft_parked_status_records', 'fetched_at'])
        AircraftParkingInfo.objects.update(fetched_at=int(fetched_at))
        self._trim_if_needed()

    def _trim_if_needed(self):
        total = AircraftParkingInfo.objects.count()
        if total < self.max_records:
            return
        delete_count = max(1, total // 10)
        old_ids = list(
            AircraftParkingInfo.objects.order_by('fetched_at', 'id').values_list('id', flat=True)[:delete_count]
        )
        if old_ids:
            AircraftParkingInfo.objects.filter(id__in=old_ids).delete()
            logger.info(f'停场表超过 {self.max_records}，删除最旧 {len(old_ids)} 行')

    def _airport(self, row, field) -> Optional[str]:
        text = self._text(row, field)
        if not text:
            return None
        code = text.strip().upper()
        return code if len(code) == 4 else None

    def _text(self, row, field) -> Optional[str]:
        if field not in row:
            return None
        val = row[field]
        if pd.isna(val):
            return None
        text = str(val).strip()
        return text or None

    def _ms(self, row, field) -> Optional[int]:
        text = self._text(row, field)
        if not text:
            return None
        try:
            return int(float(text))
        except (TypeError, ValueError):
            return None
