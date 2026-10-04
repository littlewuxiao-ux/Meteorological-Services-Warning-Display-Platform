"""
航班解析器
完全移植原始mtws_01_flight解析.py的核心逻辑，适配Django框架
"""

import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging

from django.utils import timezone
from django.conf import settings
from parsers.models import Flight
from data_adapters.adapter_factory import AdapterFactory
from utils.flight_selection import airport_flags_from_events, selected_carrier_codes, selected_events
from utils.time_manager import TimeManager
from utils.marks_alert_calculator import (
    default_warning,
    event_identity,
    normalize_warning,
    warning_is_ready,
)

logger = logging.getLogger('mtws.parsers')


class FlightParser:
    """航班解析器类 - 完全移植原始程序逻辑"""
    
    def __init__(self, time_mode='current', token=None):
        """
        初始化航班解析器
        
        Args:
            time_mode: 时间模式，'current' 或 'test'
            token: current模式下的认证token
        """
        self.time_mode = time_mode
        self.token = token
        
        # 设置当前时间
        self.current_time = TimeManager.get_current_time_local(time_mode)
            
        logger.info(f"航班解析器初始化完成，时间模式: {time_mode}, 当前时间: {self.current_time}")
    
    def parse_and_save(self):
        """
        解析并保存航班数据（与解析管理器接口保持一致）
        
        Returns:
            Dict: 解析结果统计
        """
        return self.parse_flight_data()
    
    def parse_flight_data(self):
        """
        解析航班数据的主入口方法
        
        Returns:
            Dict: 解析结果统计
        """
        logger.info("开始解析航班数据")
        start_time = datetime.now()
        
        try:
            # 1. 获取数据适配器并读取数据
            adapter = AdapterFactory.create_adapter(time_mode=self.time_mode, token=self.token)
            df = adapter.get_flight_data()
            
            if df.empty:
                logger.warning("未获取到航班数据，保留原有数据")
                # 更新状态：数据不可用，但保留原有数据
                self._update_flight_status(success=False)
                return {'success': False, 'message': '未获取到航班数据', 'record_count': 0, 'data_preserved': True}
            
            logger.info(f"获取到航班原始数据 {len(df)} 行，全量入库")
            selected = selected_carrier_codes()
            logger.info(f"已选承运人 {sorted(selected) or '无'}，派生字段只统计这些承运人")

            old_by_airport = {}
            for row in Flight.objects.all().order_by('created_at'):
                old_by_airport[row.airport_4code] = row

            airports = self._get_airports(df)
            logger.info(f"发现 {len(airports)} 个机场")

            processed_count = 0
            has_flight_true = []
            has_flight_false = []
            marks_full_airports = []
            marks_changed_keys = {}
            new_airports = set()
            trend_changed = []

            for airport in airports:
                try:
                    events = self._build_airport_events(df, airport)
                    flags = airport_flags_from_events(selected_events(events, selected))
                    has_flight = flags['has_flight']
                    old = old_by_airport.get(airport)
                    en_route = flags['en_route']
                    closest_arr = flags['closest_arr_link']
                    closest_dep = flags['closest_dep_at']
                    closest_lnd = flags['closest_lnd_at']
                    old_events = old.as_events() if old else []
                    events, full_recalc, changed_keys = self._merge_event_warnings(old_events, events)
                    stats_changed = (
                        old is None
                        or old.has_flight != has_flight
                        or old.en_route != en_route
                        or old.closest_departure_time_of_arriving_flight != closest_arr
                        or old.closest_departure_time_at_this_airport != closest_dep
                        or old.closest_landing_time_of_arriving_flight != closest_lnd
                    )
                    if stats_changed or events != old_events:
                        if self._upsert_airport_data(
                            old, airport, has_flight, events, en_route,
                            closest_arr, closest_dep, closest_lnd,
                        ):
                            processed_count += 1
                            trend_changed.append(airport)
                    else:
                        processed_count += 1

                    new_airports.add(airport)
                    if full_recalc:
                        marks_full_airports.append(airport)
                    elif changed_keys:
                        marks_changed_keys[airport] = changed_keys

                    if has_flight:
                        has_flight_true.append(airport)
                    else:
                        has_flight_false.append(airport)
                except Exception as e:
                    logger.error(f"处理机场 {airport} 数据失败: {str(e)}")

            stale = set(old_by_airport.keys()) - new_airports
            if stale:
                Flight.objects.filter(airport_4code__in=stale).delete()
                logger.info(f"已删除无数据机场航班行: {sorted(stale)}")
            try:
                from utils.trend_alert import clear_airports, refresh_airports
                if stale:
                    clear_airports(stale)
                if trend_changed:
                    refresh_airports(trend_changed)
            except Exception as trend_error:
                logger.error(f"实况趋势告警跟随航班更新失败: {trend_error}")
            
            # 输出简化的日志
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            logger.info(f"航班数据更新完成 - {current_time}")
            if has_flight_true:
                logger.info(f"has_flight: True - {has_flight_true}")
            if has_flight_false:
                logger.info(f"has_flight: False - {has_flight_false}")
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            # 更新状态：数据获取成功
            self._update_flight_status(success=True)
            
            result = {
                'success': True,
                'message': f'航班数据解析完成',
                'record_count': processed_count,
                'execution_time': execution_time,
                'marks_full_airports': marks_full_airports,
                'marks_changed_keys': marks_changed_keys,
            }
            
            logger.info(f"航班数据解析完成，处理 {processed_count} 个机场，耗时 {execution_time:.2f} 秒")
            return result
            
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"航班数据解析失败: {str(e)}")
            return {
                'success': False,
                'message': f'航班数据解析失败: {str(e)}',
                'record_count': 0,
                'execution_time': execution_time
            }
    
    def _get_airports(self, df: pd.DataFrame) -> List[str]:
        """
        从航班数据中提取机场列表
        
        Args:
            df: 航班数据
            
        Returns:
            List[str]: 机场四字代码列表
        """
        # 获取所有起飞机场和到达机场
        departure_airports = set(df['departureAirport'].dropna().tolist())
        arrival_airports = set(df['arrivalAirport'].dropna().tolist())
        
        # 合并并去重
        all_airports = list(departure_airports | arrival_airports)
        all_airports = [airport for airport in all_airports if airport and str(airport).strip()]
        
        logger.info(f"统计到的机场数量: {len(all_airports)}")
        logger.info(f"机场列表: {all_airports}")
        
        return all_airports
    
    def _has_field(self, row: pd.Series, field: str) -> bool:
        """字段是否有有效值。"""
        if field not in row:
            return False
        val = row[field]
        if pd.isna(val):
            return False
        return bool(str(val).strip())

    def _field_ms(self, row: pd.Series, field: str) -> Optional[int]:
        """读取单个毫秒时间戳字段。"""
        if not self._has_field(row, field):
            return None
        try:
            return int(float(str(row[field]).strip()))
        except (ValueError, OSError, TypeError):
            return None

    def _pick_ms(self, row: pd.Series, fields: List[str]) -> Optional[int]:
        """按优先级取第一个有效毫秒时间戳。"""
        for field in fields:
            ms = self._field_ms(row, field)
            if ms is not None:
                return ms
        return None

    def _other_payload(self, row: pd.Series) -> Dict:
        """悬停用明细字段。"""
        keys = [
            'flightId', 'flightDate', 'flightNo', 'acType', 'acReg',
            'departureAirport', 'arrivalAirport',
            'ptd', 'pta', 'std', 'sta', 'etd', 'eta', 'atd', 'ata',
            'blockOut', 'closeDoorTime',
        ]
        other = {}
        for key in keys:
            if key not in row:
                other[key] = None
                continue
            val = row[key]
            if pd.isna(val) or str(val).strip() == '':
                other[key] = None
            else:
                if key in ('ptd', 'pta', 'std', 'sta', 'etd', 'eta', 'atd', 'ata',
                           'blockOut', 'closeDoorTime', 'flightDate'):
                    try:
                        other[key] = int(float(str(val).strip()))
                    except (ValueError, TypeError):
                        other[key] = str(val).strip()
                else:
                    other[key] = str(val).strip()
        return other

    def _event_window_ms(self) -> tuple:
        """events 写入窗口：[now-2h, now+48h]，分钟精度。"""
        now = self.current_time.replace(second=0, microsecond=0)
        start = now - timedelta(hours=2)
        end = now + timedelta(hours=48)
        return int(start.timestamp() * 1000), int(end.timestamp() * 1000)

    def _build_airport_events(self, df: pd.DataFrame, airport: str) -> list:
        """构建本机场 marks 用 events 列表（按 at 升序）。"""
        events = []
        win_start, win_end = self._event_window_ms()
        now_ms = int(self.current_time.replace(second=0, microsecond=0).timestamp() * 1000)

        def append_event(kind: str, at_ms: Optional[int], link_ms: Optional[int], row: pd.Series):
            if at_ms is None:
                return
            if at_ms < win_start or at_ms > win_end:
                return
            carrier = None
            if self._has_field(row, 'carrier'):
                carrier = str(row['carrier']).strip()
            flight_id = None
            if self._has_field(row, 'flightId'):
                flight_id = str(row['flightId']).strip()
            events.append({
                'at': at_ms,
                'link': link_ms,
                'kind': kind,
                'carrier': carrier,
                'flightId': flight_id,
                'warning': default_warning(),
                'other': self._other_payload(row),
            })

        arrival_flights = df[df['arrivalAirport'] == airport]
        for _, row in arrival_flights.iterrows():
            has_atd = self._has_field(row, 'atd')
            has_ata = self._has_field(row, 'ata')
            link_ms = self._pick_ms(row, ['atd', 'etd', 'std', 'ptd'])
            if has_ata:
                append_event('lnd', self._field_ms(row, 'ata'), link_ms, row)
            else:
                land_ms = self._pick_ms(row, ['eta', 'sta', 'pta'])
                if land_ms is not None and land_ms < now_ms:
                    # oen=已起飞超时未落；oar=对方未起且落地时刻已过
                    append_event('oen' if has_atd else 'oar', land_ms, link_ms, row)
                elif has_atd:
                    append_event('enr', land_ms, link_ms, row)
                else:
                    append_event('arr', land_ms, link_ms, row)

        departure_flights = df[df['departureAirport'] == airport]
        for _, row in departure_flights.iterrows():
            at_ms = self._pick_ms(row, ['atd', 'etd', 'std', 'ptd'])
            # 目的地到达：实际到达优先，其后预计、计划
            link_ms = self._pick_ms(row, ['ata', 'eta', 'sta', 'pta'])
            has_atd = self._has_field(row, 'atd')
            has_ata = self._has_field(row, 'ata')
            if has_atd and has_ata:
                kind = 'dst'
            elif has_atd:
                kind = 'off'
            elif at_ms is not None and at_ms < now_ms:
                kind = 'odp'  # 本场超时未起（原 no_dep）
            else:
                kind = 'dep'
            append_event(kind, at_ms, link_ms, row)

        events.sort(key=lambda e: (e['at'], e['kind']))
        return events

    def _merge_event_warnings(self, old_events: list, new_events: list):
        """沿用未变航班的 warning；返回 (events, 是否全场重算, 变化键列表)。"""
        old_map = {}
        for ev in old_events or []:
            if isinstance(ev, dict):
                old_map[event_identity(ev)] = ev
        changed_keys = []
        if not old_map:
            return new_events, True, []
        for ev in new_events:
            key = event_identity(ev)
            old = old_map.get(key)
            if (
                old
                and old.get('at') == ev.get('at')
                and old.get('kind') == ev.get('kind')
                and warning_is_ready(old.get('warning'))
            ):
                ev['warning'] = normalize_warning(old.get('warning'))
            else:
                ev['warning'] = default_warning()
                changed_keys.append(key)
        return new_events, False, changed_keys

    def _upsert_airport_data(
        self, old, airport, has_flight, events, en_route,
        closest_arr, closest_dep, closest_lnd,
    ) -> bool:
        try:
            fields = {
                'has_flight': has_flight,
                'events': events or [],
                'en_route': en_route,
                'closest_departure_time_of_arriving_flight': closest_arr,
                'closest_departure_time_at_this_airport': closest_dep,
                'closest_landing_time_of_arriving_flight': closest_lnd,
            }
            if old and old.pk is not None:
                for k, v in fields.items():
                    setattr(old, k, v)
                old.save()
                extras = Flight.objects.filter(airport_4code=airport).exclude(pk=old.pk)
                if extras.exists():
                    extras.delete()
            elif old:
                Flight.objects.filter(airport_4code=airport).update(**fields)
            else:
                Flight.objects.create(airport_4code=airport, **fields)
            return True
        except Exception as e:
            logger.error(f'保存机场{airport}数据时发生错误: {e}')
            return False

    def _update_flight_status(self, success: bool):
        """更新航班数据状态。"""
        try:
            from django.utils import timezone
            current_time = timezone.now()
            settings.MTWS_CONFIG['FLIGHT_DATA_STATUS']['last_attempt_time'] = current_time
            settings.MTWS_CONFIG['FLIGHT_DATA_STATUS']['is_available'] = success
            if success:
                settings.MTWS_CONFIG['FLIGHT_DATA_STATUS']['last_success_time'] = current_time
                logger.info(f'航班数据状态更新：成功获取，时间 {current_time}')
            else:
                logger.warning(f'航班数据状态更新：获取失败，时间 {current_time}')
        except Exception as e:
            logger.error(f'更新航班数据状态失败: {e}')
