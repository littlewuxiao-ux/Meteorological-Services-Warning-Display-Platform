"""飞机停场：按机号算段，再按机场并集；指纹未变则跳过。"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, Optional, Tuple

import pandas as pd
from django.conf import settings

from data_adapters.adapter_factory import AdapterFactory
from runtime_db.models import AircraftParkingInfo, AircraftParkingSync, AircraftParkingTail
from utils.aircraft_parking import (
    batch_fingerprint,
    latest_fetched_at,
    normalize_intervals,
    occupancy_airports,
    occupancy_from_tails,
    parking_payload,
    parking_segments_from_events,
    seed_from_segments,
    splice_tail_segments,
    tail_fingerprint,
    union_airport_intervals,
)
from utils.time_manager import TimeManager

logger = logging.getLogger('fmsa.parsers')

HOUR_MS = 3600 * 1000
STALE_MS = 10 * 1000
MAX_RECORDS = 500
SYNC_ID = 1


class AircraftParkingParser:
    def __init__(self, time_mode='current', token=None):
        self.time_mode = time_mode
        self.token = token
        self.current_time = TimeManager.get_current_time_local(time_mode)
        config = settings.FMSA_CONFIG.get('AIRCRAFT_PARKING_CONFIG', {})
        self.past_hours = int(config.get('PAST_HOURS', 72))
        self.carrier_code = str(config.get('CARRIER_CODE', 'O3') or 'O3').strip()
        self.max_records = int(config.get('MAX_RECORDS', MAX_RECORDS) or MAX_RECORDS)

    def parse_and_save(self):
        return self.parse_aircraft_parking_data()

    def parse_aircraft_parking_data(self, flight_df=None, fetched_at=None):
        if self.time_mode == 'test':
            logger.info('测试模式跳过停场解析')
            return {'success': True, 'message': '测试模式跳过停场解析', 'airport_count': 0, 'skipped': True}

        start_time = datetime.now()
        logger.info('开始解析飞机停场数据')
        try:
            self.current_time = TimeManager.get_current_time_local(self.time_mode)
            now_ms = int(self.current_time.timestamp() * 1000)
            if not AircraftParkingInfo.objects.exists():
                deleted_tails, _ = AircraftParkingTail.objects.all().delete()
                AircraftParkingSync.objects.filter(pk=SYNC_ID).delete()
                logger.info(
                    '停场机场表为空，已清除机号时段 %s 行和同步水位，将按过去 72 小时重建',
                    deleted_tails,
                )
            watermark = latest_fetched_at()
            df, used_at, mode = self._load_flights(flight_df, fetched_at, now_ms, watermark)
            if df is None or getattr(df, 'empty', True):
                return {'success': False, 'message': '未获取到停场航班数据', 'airport_count': 0}

            df = self._o3_rows(df)
            if mode != 'bootstrap' and not AircraftParkingTail.objects.exists():
                logger.info('机号停场表为空，按过去 72 小时重建')
                df = self._o3_rows(self._fetch_range(now_ms - self.past_hours * HOUR_MS, now_ms))
                used_at = now_ms
                mode = 'bootstrap'
            groups, tail_fps = self._tail_groups(df)
            batch_fp = batch_fingerprint(tail_fps)
            sync = self._sync_row()

            if (
                mode != 'bootstrap'
                and sync.batch_fingerprint
                and sync.batch_fingerprint == batch_fp
                and AircraftParkingInfo.objects.exists()
            ):
                self._touch_watermark(used_at)
                duration = (datetime.now() - start_time).total_seconds()
                logger.info(f'停场解析跳过，航班指纹未变，耗时 {duration:.2f}s')
                return {
                    'success': True,
                    'message': '航班未变化，跳过停场重算',
                    'airport_count': len(occupancy_airports()),
                    'duration': duration,
                    'mode': 'skipped',
                    'skipped': True,
                }

            stored = {} if mode == 'bootstrap' else self._load_tails()
            if mode == 'bootstrap':
                AircraftParkingTail.objects.all().delete()
                logger.info('停场首次重建：清空机号时段后按 72 小时航班回放')

            tail_segments = {}
            changed = 0
            for ac_reg, group in groups.items():
                fp = tail_fps[ac_reg]
                old = stored.get(ac_reg)
                if old and old.get('fingerprint') == fp:
                    tail_segments[ac_reg] = old.get('segments') or []
                    continue
                events, in_air, window_lo = self._events_from_group(group, now_ms)
                seed_airport, seed_start = (None, None)
                if old and window_lo is not None:
                    seed_airport, seed_start = seed_from_segments(old.get('segments') or [], window_lo)
                if window_lo is None and old:
                    tail_segments[ac_reg] = old.get('segments') or []
                    self._upsert_tail(ac_reg, fp, tail_segments[ac_reg])
                    continue
                fresh, _parked = parking_segments_from_events(
                    events, now_ms, seed_airport, seed_start, in_air=in_air,
                )
                segs = splice_tail_segments(
                    old.get('segments') if old else [], fresh, window_lo, now_ms,
                )
                tail_segments[ac_reg] = segs
                self._upsert_tail(ac_reg, fp, segs)
                changed += 1

            for ac_reg, row in stored.items():
                if ac_reg not in tail_segments:
                    tail_segments[ac_reg] = row.get('segments') or []

            occupancy = occupancy_from_tails(tail_segments)
            intervals = union_airport_intervals(tail_segments, now_ms)
            touched = set(occupancy.values()) | set(intervals)
            self._save_airports(occupancy, intervals, used_at, now_ms, touched)
            sync.batch_fingerprint = batch_fp
            sync.fetched_at = int(used_at)
            sync.save(update_fields=['batch_fingerprint', 'fetched_at'])

            duration = (datetime.now() - start_time).total_seconds()
            parked = sorted({code for code in occupancy.values() if code})
            logger.info(
                f'停场解析完成 {mode}，重算 {changed} 架，{len(parked)} 个机场有停场，'
                f'耗时 {duration:.2f}s: {parked}'
            )
            return {
                'success': True,
                'message': '飞机停场数据解析成功',
                'airport_count': len(parked),
                'duration': duration,
                'mode': mode,
                'recomputed': changed,
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

    def _tail_groups(self, df: pd.DataFrame) -> Tuple[Dict[str, pd.DataFrame], Dict[str, str]]:
        groups = {}
        fps = {}
        if df.empty or 'acReg' not in df.columns:
            return groups, fps
        for ac_reg, group in df.groupby('acReg'):
            key = str(ac_reg).strip()
            if not key:
                continue
            groups[key] = group
            fps[key] = tail_fingerprint(self._fingerprint_rows(group))
        return groups, fps

    def _iter_flight_rows(self, group: pd.DataFrame):
        cols = [name for name in (
            'flightId', 'acReg', 'departureAirport', 'arrivalAirport', 'atd', 'ata',
        ) if name in group.columns]
        if not cols:
            return
        for item in group.loc[:, cols].to_dict('records'):
            yield item

    def _fingerprint_rows(self, group: pd.DataFrame) -> list:
        rows = []
        for rec in self._iter_flight_rows(group):
            rows.append([
                self._cell_text(rec, 'flightId'),
                self._cell_airport(rec, 'departureAirport'),
                self._cell_airport(rec, 'arrivalAirport'),
                self._cell_ms(rec, 'atd'),
                self._cell_ms(rec, 'ata'),
            ])
        return rows

    def _events_from_group(self, group: pd.DataFrame, now_ms: int):
        events = []
        in_air = False
        window_lo = None
        for rec in self._iter_flight_rows(group):
            dep = self._cell_airport(rec, 'departureAirport')
            arr = self._cell_airport(rec, 'arrivalAirport')
            atd = self._cell_ms(rec, 'atd')
            ata = self._cell_ms(rec, 'ata')
            if atd:
                events.append((atd, 0, 'atd', dep))
                window_lo = atd if window_lo is None else min(window_lo, atd)
            if ata:
                events.append((ata, 1, 'ata', arr))
                window_lo = ata if window_lo is None else min(window_lo, ata)
            if atd and (ata is None or ata > now_ms) and atd <= now_ms:
                in_air = True
        events.sort()
        return events, in_air, window_lo

    def _sync_row(self) -> AircraftParkingSync:
        row = AircraftParkingSync.objects.filter(pk=SYNC_ID).first()
        if row:
            return row
        return AircraftParkingSync.objects.create(id=SYNC_ID)

    def _load_tails(self) -> dict:
        out = {}
        for row in AircraftParkingTail.objects.all():
            key = str(row.ac_reg or '').strip()
            if key:
                out[key] = {'fingerprint': row.fingerprint or '', 'segments': row.segments or []}
        return out

    def _upsert_tail(self, ac_reg: str, fingerprint: str, segments: list):
        AircraftParkingTail.objects.update_or_create(
            ac_reg=ac_reg,
            defaults={'fingerprint': fingerprint or '', 'segments': segments or []},
        )

    def _touch_watermark(self, fetched_at: int):
        used = int(fetched_at)
        sync = self._sync_row()
        sync.fetched_at = used
        sync.save(update_fields=['fetched_at'])
        AircraftParkingInfo.objects.update(fetched_at=used)

    def _save_airports(self, occupancy: dict, intervals: dict, fetched_at: int, now_ms: int, touched: set):
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

    def _cell_airport(self, rec, field) -> Optional[str]:
        text = self._cell_text(rec, field)
        if not text:
            return None
        code = text.strip().upper()
        return code if len(code) == 4 else None

    def _cell_text(self, rec, field) -> Optional[str]:
        if not isinstance(rec, dict) or field not in rec:
            return None
        val = rec.get(field)
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return None
        text = str(val).strip()
        if not text or text.lower() == 'nan' or text.lower() == 'none':
            return None
        return text

    def _cell_ms(self, rec, field) -> Optional[int]:
        text = self._cell_text(rec, field)
        if not text:
            return None
        try:
            return int(float(text))
        except (TypeError, ValueError):
            return None
