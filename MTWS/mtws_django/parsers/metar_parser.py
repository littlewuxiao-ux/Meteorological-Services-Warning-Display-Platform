"""
METAR解析器
基于原始mtws_02_metar解析.py的核心逻辑，适配Django框架
"""

import json
import pandas as pd
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging

from django.utils import timezone
from django.conf import settings
from django.db import connection
from core.models import AirportAlertThresholds, WeatherAlertLevels
from parsers.cloud_amount import lowest_height_in_cloud_strings, normalize_cloud_amt
from parsers.models import Metar
from data_adapters.adapter_factory import AdapterFactory
from utils.time_manager import TimeManager

logger = logging.getLogger('mtws.parsers')


class MetarParser:
    """METAR解析器类"""
    
    def __init__(self, time_mode='current', token=None, user_code=None):
        """
        初始化METAR解析器
        
        Args:
            time_mode: 时间模式，'current' 或 'test'
            token: current模式下的认证token
            user_code: 用户代码
        """
        self.time_mode = time_mode
        self.token = token
        self.user_code = user_code
        self.airport_thresholds = {}  # 缓存机场阈值信息
        
        # 设置当前时间
        self.current_time = TimeManager.get_current_time_utc(time_mode)
            
        logger.info(f"METAR解析器初始化完成，时间模式: {time_mode}, 当前时间: {self.current_time}")
    
    def parse_and_save(self):
        """
        解析并保存METAR数据（与解析管理器接口保持一致）
        
        Returns:
            Dict: 解析结果统计
        """
        return self.parse_metar_data()
    
    def parse_metar_data(self):
        """
        解析METAR数据的主入口方法
        
        Returns:
            Dict: 解析结果统计
        """
        logger.info("开始解析METAR数据")
        start_time = datetime.now()
        
        try:
            from utils.airport_scope import get_monitored_airport_codes
            active_airports = get_monitored_airport_codes()
            
            if not active_airports:
                logger.warning("未找到有航班或停场的机场，跳过METAR数据解析")
                return {'success': False, 'message': '未找到有航班或停场的机场', 'record_count': 0}
            
            logger.info(f"获取到有航班或停场的机场: {active_airports}")
            
            adapter = AdapterFactory.create_adapter(time_mode=self.time_mode, token=self.token)
            df = adapter.get_metar_data(active_airports)
            
            success_count, error_count, updated_airports = self._process_all_airports(active_airports, df)
            
            self._cleanup_old_records()
            
            execution_time = (datetime.now() - start_time).total_seconds()
            logger.info(f"METAR数据解析完成，成功: {success_count} 条，失败: {error_count} 条，耗时 {execution_time:.2f} 秒")
            
            return {
                'success': True,
                'message': 'METAR数据解析完成',
                'record_count': success_count,
                'error_count': error_count,
                'execution_time': execution_time,
                'updated_airports': updated_airports,
            }
            
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"METAR数据解析失败: {str(e)}")
            return {
                'success': False,
                'message': f'METAR数据解析失败: {str(e)}',
                'record_count': 0,
                'execution_time': execution_time,
            }
    
    def _cleanup_old_records(self):
        """清理METAR记录（水位线模式）：超过上限时一次性削减至上限的90%，按created_at升序删除最旧记录。"""
        max_records = settings.MTWS_CONFIG['DATA_RETENTION']['metar_max_records']

        current_count = Metar.objects.count()
        if current_count <= max_records:
            return

        target_count = int(max_records * 0.9)
        delete_count = current_count - target_count
        old_pks = list(
            Metar.objects.order_by('created_at').values_list('pk', flat=True)[:delete_count]
        )
        Metar.objects.filter(pk__in=old_pks).delete()

        logger.info(f"METAR表水位线清理：{current_count} 条 → 删除 {delete_count} 条，目标保留 {target_count} 条")
    
    def parse_metar_data_for_airports(self, airport_codes: List[str]):
        """
        为指定机场解析METAR数据
        
        Args:
            airport_codes: 机场代码列表
            
        Returns:
            Dict: 解析结果统计
        """
        logger.info(f"开始为指定机场解析METAR数据: {airport_codes}")
        start_time = datetime.now()
        
        try:
            # 清理滞留告警：航班运行已结束但告警尚未处置的记录
            now_ms = int(timezone.now().timestamp() * 1000)
            self._clear_stale_metar_import_alerts(now_ms)

            adapter = AdapterFactory.create_adapter(time_mode=self.time_mode, token=self.token)
            df = adapter.get_metar_data(airport_codes)
            
            success_count, error_count, updated_airports = self._process_all_airports(airport_codes, df)
            
            self._cleanup_old_records()
            
            execution_time = (datetime.now() - start_time).total_seconds()
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            logger.info(f"实况数据更新完成 - {current_time}, 成功: {success_count} 条, 失败: {error_count} 条")
            
            return {
                'success': True,
                'message': '指定机场METAR数据解析完成',
                'record_count': success_count,
                'error_count': error_count,
                'execution_time': execution_time,
                'filtered_airports': airport_codes,
                'updated_airports': updated_airports,
            }
            
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"指定机场METAR数据解析失败: {str(e)}")
            return {
                'success': False,
                'message': f'指定机场METAR数据解析失败: {str(e)}',
                'record_count': 0,
                'execution_time': execution_time,
            }
    
    def _update_data_status_fields(self, airport_4code: str):
        """
        将该机场 data_status=N 或 C 的行全部改为 H（历史）。
        返回 (last_sqc, auto_cover_pks)：
          - last_sqc: 上一份当前报文的 sqc，用于拦截判断
          - auto_cover_pks: 需要自动覆盖告警的行主键列表（import_alert=Y 且 import_alert_handle_time 为空的行）
        """
        active_rows = list(
            Metar.objects.filter(
                airport_4code=airport_4code,
                data_status__in=['N', 'C'],
            ).values('pk', 'sqc', 'import_alert', 'import_alert_handle_time', 'data_status')
        )

        if len(active_rows) > 1:
            logger.warning(f"[METAR解析] {airport_4code}: 发现 {len(active_rows)} 条活跃行（并发异常？）")

        last_sqc = active_rows[0]['sqc'] if active_rows else None

        # 找出需要自动覆盖的告警行
        auto_cover_pks = [
            r['pk'] for r in active_rows
            if r.get('import_alert') == 'Y' and not r.get('import_alert_handle_time')
        ]

        # 将所有活跃行改为历史
        Metar.objects.filter(
            airport_4code=airport_4code,
            data_status__in=['N', 'C'],
        ).update(data_status='H')

        return last_sqc, auto_cover_pks

    def _process_all_airports(self, airport_codes: list, df: pd.DataFrame):
        """
        按机场逐个处理METAR数据，入库完成后统一执行入库告警判断。

        情况1（API返回了该机场数据）：SQC去重 → 入库(data_status=N)
        情况2（API未返回该机场数据 且 无N行）：创建 data_status=C 占位行（含 import_alert=Y）
        情况3（API未返回该机场数据 且 已有N行）：保留N行，由 _check_metar_import_alert 判断

        Returns:
            Tuple[int, int]: (成功插入条数, 失败条数)
        """
        config = settings.MTWS_CONFIG.get('METAR_IMPORT_ALERT', {})
        now_ms = int(timezone.now().timestamp() * 1000)

        if not df.empty and 'airport4Code' in df.columns:
            api_airports = set(df['airport4Code'].astype(str).str.strip().unique())
            all_sqcs = [str(row.get('sqc', '')).strip() for _, row in df.iterrows()]
            existing_sqcs = set(Metar.objects.filter(sqc__in=all_sqcs).values_list('sqc', flat=True))
            logger.info(
                f"[METAR解析] 批量SQC查询: API返回{len(all_sqcs)}条, "
                f"DB已存在{len(existing_sqcs)}条, 待处理{len(all_sqcs)-len(existing_sqcs)}条"
            )
        else:
            api_airports = set()
            existing_sqcs = set()

        # 批量预查已有 N 行的机场，用于在主循环中判断是否需要创建占位行
        airports_with_n = set(
            Metar.objects.filter(
                airport_4code__in=airport_codes,
                data_status='N',
            ).values_list('airport_4code', flat=True)
        )

        success_count = 0
        error_count = 0
        updated_airports = []

        for airport_code in airport_codes:
            try:
                if airport_code in api_airports:
                    airport_df = df[df['airport4Code'].astype(str).str.strip() == airport_code]
                    inserted = self._insert_airport_rows(airport_code, airport_df, existing_sqcs)
                    success_count += inserted
                    if inserted:
                        updated_airports.append(airport_code)
                elif airport_code not in airports_with_n:
                    # API 无数据且 DB 无 N 行 → 创建占位行（直接标记 import_alert=Y）
                    self._create_placeholder_and_alert(airport_code, now_ms)
            except Exception as e:
                error_count += 1
                logger.error(f"[METAR解析] {airport_code} 处理失败: {e}", exc_info=True)

        # 主循环结束后，统一执行入库告警检查
        self._check_metar_import_alert(airport_codes, now_ms, config)
        if updated_airports:
            try:
                from utils.trend_alert import refresh_airports
                refresh_airports(updated_airports)
            except Exception as trend_error:
                logger.error(f"实况趋势告警跟随实况入库失败: {trend_error}")

        return success_count, error_count, updated_airports

    def _skip_import_alert(self) -> bool:
        """
        test 模式取的是固定历史快照，用真实时钟判定会把全部报文判成过期，
        故整套入库告警（占位行、超时标记、滞留清理）在该模式下不执行。
        """
        return self.time_mode == 'test'

    def _clear_stale_metar_import_alerts(self, now_ms: int):
        """
        清理滞留的METAR入库告警：
        若某机场的 import_alert=Y 且 import_alert_handle_time 为空，
        且既无航班也无停场飞机，则视为滞留告警，自动结案。
        """
        if self._skip_import_alert():
            return

        try:
            from utils.airport_scope import get_import_alert_keep_airport_codes
            keep_airports = get_import_alert_keep_airport_codes()
            updated = Metar.objects.filter(
                import_alert='Y',
                import_alert_handle_time__isnull=True,
            ).exclude(
                airport_4code__in=keep_airports
            ).update(
                import_alert_handle_time=now_ms,
                handle_status='航班运行结束且无停场飞机',
            )
            if updated:
                logger.info(f"[METAR入库告警] 清理滞留告警 {updated} 条（航班运行结束且无停场飞机）")
        except Exception as e:
            logger.error(f"[METAR入库告警] 清理滞留告警失败: {e}")

    def _check_metar_import_alert(self, airport_codes: list, now_ms: int, config: dict):
        """
        主循环结束后，对所有受监控机场的 data_status=N 且未告警行做统一入库告警检查：
        满足时间条件（created_at 和 metar_observation_time 均超时）则批量标记 import_alert=Y。
        占位行（data_status=C）已由主循环创建，此处不再处理。
        """
        if not airport_codes or self._skip_import_alert():
            return

        from collections import Counter

        created_at_minutes = config.get('CREATED_AT_MINUTES', 70)
        observation_minutes = config.get('OBSERVATION_TIME_MINUTES', 90)
        created_at_threshold = now_ms - created_at_minutes * 60 * 1000
        observation_threshold = now_ms - observation_minutes * 60 * 1000

        # 批量查询所有受监控机场中 data_status=N 且尚未告警的行，按 created_at 降序（取最新）
        rows_to_check = list(
            Metar.objects.filter(
                airport_4code__in=airport_codes,
                data_status='N',
            ).exclude(import_alert='Y').order_by('-created_at').values(
                'airport_4code', 'sqc', 'created_at', 'metar_observation_time'
            )
        )

        airport_n_count = Counter(row['airport_4code'] for row in rows_to_check)
        alert_sqcs = []
        new_alert_airports = []
        seen_airports = set()

        for row in rows_to_check:
            airport_code = row['airport_4code']
            if airport_code in seen_airports:
                continue
            seen_airports.add(airport_code)

            if airport_n_count[airport_code] > 1:
                logger.warning(f"[入库告警] {airport_code}: 异常，存在{airport_n_count[airport_code]}条未告警N行")

            c = row['created_at']
            o = row['metar_observation_time']

            if (c is not None and c <= created_at_threshold
                    and o is not None and o <= observation_threshold):
                alert_sqcs.append(row['sqc'])
                new_alert_airports.append(airport_code)

        if alert_sqcs:
            Metar.objects.filter(sqc__in=alert_sqcs).update(
                import_alert='Y',
                import_alert_time=now_ms,
            )

        logger.warning(f"[入库告警] 本次新增告警机场: {sorted(new_alert_airports)}")

    def _insert_airport_rows(self, airport_code: str, airport_df: pd.DataFrame, existing_sqcs: set) -> int:
        """
        为单个机场插入API返回的METAR数据行，返回成功插入条数。
        existing_sqcs 会在插入成功后同步更新，防止同机场多行重复插入。
        """
        inserted = 0
        for _, row in airport_df.iterrows():
            try:
                sqc = str(row.get('sqc', '')).strip()
                metar_content = str(row.get('content', '')).strip()

                if not sqc or not metar_content:
                    continue

                if sqc in existing_sqcs:
                    continue

                last_metar_sqc, auto_cover_pks = self._update_data_status_fields(airport_code)

                parsed_data = self._parse_metar_content(row)
                for _k in list(parsed_data.keys()):
                    if parsed_data[_k] in ('None', 'nan'):
                        parsed_data[_k] = None

                parsed_data['sqc'] = sqc
                parsed_data['last_metar_sqc'] = last_metar_sqc
                self._add_popup_fields(parsed_data)
                parsed_data['data_status'] = 'N'

                Metar.objects.create(**parsed_data)

                if auto_cover_pks:
                    Metar.objects.filter(pk__in=auto_cover_pks).update(
                        import_alert_handle_time=parsed_data['created_at'],
                        handle_status=f'新报文已入库，sqc={sqc}',
                    )

                existing_sqcs.add(sqc)
                inserted += 1

            except Exception as e:
                logger.error(f"[METAR解析] {airport_code} 行插入失败: {e}", exc_info=True)

        return inserted

    def _check_and_set_import_alert(self, airport_code: str, now_ms: int, config: dict,
                                    new_alert_airports: list, existing_alert_airports: list):
        """
        对该机场当前 data_status=N 的行进行告警条件判断，满足则标记 import_alert=Y。
        若已标记Y，则跳过（保留最早告警时间）。
        """
        created_at_minutes = config.get('CREATED_AT_MINUTES', 70)
        observation_minutes = config.get('OBSERVATION_TIME_MINUTES', 90)
        created_at_threshold = now_ms - created_at_minutes * 60 * 1000
        observation_threshold = now_ms - observation_minutes * 60 * 1000

        all_n_rows = list(Metar.objects.filter(
            airport_4code=airport_code,
            data_status='N',
        ).order_by('created_at').values('sqc', 'created_at', 'metar_observation_time', 'import_alert', 'import_alert_time'))

        if not all_n_rows:
            return

        if len(all_n_rows) > 1:
            logger.warning(f"[入库告警] {airport_code}: 异常，存在{len(all_n_rows)}条N行")

        target = all_n_rows[0]
        target_sqc = target['sqc']

        if target['import_alert'] == 'Y':
            existing_alert_airports.append(airport_code)
            return

        c = target['created_at']
        o = target['metar_observation_time']

        if (c is not None and c <= created_at_threshold
                and o is not None and o <= observation_threshold):
            Metar.objects.filter(sqc=target_sqc).update(
                import_alert='Y',
                import_alert_time=now_ms,
            )
            new_alert_airports.append(airport_code)

    def _create_placeholder_and_alert(self, airport_code: str, now_ms: int):
        """
        情况2子分支：API无数据且DB无N行时，创建 data_status=C 占位行并直接标记 import_alert=Y。
        """
        if self._skip_import_alert():
            return

        sqc = f"C_{airport_code}_{now_ms}"
        user_code = self.user_code or 'system'

        Metar.objects.create(
            airport_4code=airport_code,
            sqc=sqc,
            created_at=now_ms,
            data_status='C',
            import_alert='Y',
            import_alert_time=now_ms,
            user_code=user_code,
            operation_popup='N',
            parking_popup='N',
        )
    
    def _parse_metar_content(self, row: pd.Series) -> Dict:
        """
        解析METAR报文内容
        注意：按照原始程序逻辑，直接从CSV列读取已解析的字段，而不是解析CONTENT字段
        
        Args:
            row: METAR数据行
            
        Returns:
            Dict: 解析后的数据
        """
        # 基础信息
        airport_4code = row.get('airport4Code', '').strip()
        metar_content = row.get('content', '').strip()
        observation_time = row.get('observationTime', '')
        
        # API返回的是北京时间戳，需要转换为UTC时间戳（加8小时）
        observation_timestamp = None
        if observation_time:
            try:
                # 尝试转换为整数（支持int、float、字符串格式）
                beijing_timestamp = int(float(observation_time))
                # 转换为UTC时间戳：北京时间戳 + 8小时
                observation_timestamp = beijing_timestamp + 28800000
            except (ValueError, TypeError):
                logger.warning(f"无法转换观测时间: {observation_time}")
        
        # 初始化解析结果
        parsed_data = {
            'airport_4code': airport_4code,
            'metar_content': metar_content,
            'metar_observation_time': observation_timestamp,
        }
        
        try:
            # 报文类型和自动报标签 - 从API数据字段获取
            metar_type = str(row.get('type', '')) if pd.notna(row.get('type')) else None
            auto_flag = str(row.get('autoFlag', '')) if pd.notna(row.get('autoFlag')) else None
            parsed_data['metar_type'] = metar_type
            parsed_data['metar_auto_flag'] = auto_flag
            
            # 风向风速 - 基于windDirection、windSpeed1和flurry1字段构建显示字符串
            wind_direction = str(row.get('windDirection', '')) if pd.notna(row.get('windDirection')) and str(row.get('windDirection', '')).strip() else None
            wind_speed1 = str(row.get('windSpeed1', '')) if pd.notna(row.get('windSpeed1')) and str(row.get('windSpeed1', '')).strip() else None
            flurry1 = str(row.get('flurry1', '')) if pd.notna(row.get('flurry1')) and str(row.get('flurry1', '')).strip() else None
            
            # 构建风速显示字符串
            wind_speed_original = None
            if wind_direction and wind_speed1:
                if flurry1:
                    # 如果flurry1不为空：windSpeed1前2位 + G + flurry1
                    wind_speed_digits = re.match(r'(\d{2})', wind_speed1)
                    if wind_speed_digits:
                        wind_speed_original = wind_speed_digits.group(1) + 'G' + flurry1
                else:
                    # 如果flurry1为空：windSpeed1完整内容
                    wind_speed_original = wind_speed1
            
            parsed_data['metar_wind_direction'] = wind_direction
            parsed_data['metar_wind_speed_original'] = wind_speed_original
            
            # 提取风速中间变量值
            wind_speed_val = None
            gust_val = None
            if pd.notna(row.get('windSpeed')):
                try:
                    wind_speed_val = float(row.get('windSpeed'))
                except (ValueError, TypeError):
                    wind_speed_val = None
            if pd.notna(row.get('flurry')):
                try:
                    gust_val = float(row.get('flurry'))
                except (ValueError, TypeError):
                    gust_val = None
            parsed_data['metar_wind_speed_val'] = wind_speed_val
            parsed_data['metar_gust_val'] = gust_val
            
            # 风速告警处理
            wind_warning = self._get_wind_alert_level(row, airport_4code)
            parsed_data['metar_wind_warning'] = wind_warning
            
            # 能见度 - 从API数据字段获取（用于前端显示）
            visibility_original = str(row.get('visibility1', '')) if pd.notna(row.get('visibility1')) and str(row.get('visibility1', '')).strip() else None
            parsed_data['metar_visibility_original'] = visibility_original
            
            # 提取能见度中间变量值
            visibility_val = None
            if pd.notna(row.get('visibility')):
                try:
                    visibility_val = int(row.get('visibility'))
                except (ValueError, TypeError):
                    visibility_val = None
            parsed_data['metar_visibility_val'] = visibility_val
            
            # 能见度告警处理
            visibility_warning = self._get_visibility_alert_level(row, airport_4code)
            parsed_data['metar_visibility_warning'] = visibility_warning
            
            # 天气现象 - 从API数据字段组合
            weather1 = str(row.get('weather1', '')) if pd.notna(row.get('weather1')) else None
            weather2 = str(row.get('weather2', '')) if pd.notna(row.get('weather2')) else None
            weather3 = str(row.get('weather3', '')) if pd.notna(row.get('weather3')) else None
            
            weather = self._combine_weather_info(weather1, weather2, weather3)
            parsed_data['metar_weather'] = weather
            
            # 天气现象告警处理
            weather_warning, weather_type_dict = self._get_weather_alert_level_from_fields(weather1, weather2, weather3, row)
            parsed_data['metar_weather_warning'] = weather_warning
            parsed_data['weather_type_dict'] = weather_type_dict  # 保存字典供后续使用
            
            # 近时天气
            weather_pre = str(row.get('proWeather', '')) if pd.notna(row.get('proWeather')) else None
            parsed_data['metar_weather_pre'] = weather_pre
            
            # 云组 - 从API数据字段组合
            cloud1 = str(row.get('cloud1', '')) if pd.notna(row.get('cloud1')) else None
            cloud2 = str(row.get('cloud2', '')) if pd.notna(row.get('cloud2')) else None
            cloud3 = str(row.get('cloud3', '')) if pd.notna(row.get('cloud3')) else None
            
            cloud = self._combine_cloud_info(cloud1, cloud2, cloud3)
            parsed_data['metar_cloud'] = cloud
            
            # 提取最低云层高度中间变量值
            min_cloud_height = self._get_min_cloud_height(cloud1, cloud2, cloud3, airport_4code)
            parsed_data['metar_min_cloud_height'] = min_cloud_height
            
            # 云组告警处理
            cloud_warning = self._get_cloud_alert_level(cloud1, cloud2, cloud3, airport_4code)
            parsed_data['metar_cloud_warning'] = cloud_warning
            
            # 温度露点 - 从API数据字段获取
            temperature = str(row.get('temperature', '')) if pd.notna(row.get('temperature')) else None
            dew_point = str(row.get('dewPoint', '')) if pd.notna(row.get('dewPoint')) else None
            parsed_data['metar_temperature'] = temperature
            parsed_data['metar_dew_point'] = dew_point
            
            # 提取温度中间变量值
            temp_val = None
            if pd.notna(row.get('temperature')):
                try:
                    temp_val = float(row.get('temperature'))
                except (ValueError, TypeError):
                    temp_val = None
            parsed_data['metar_temp_val'] = temp_val
            
            # 温度告警处理
            temp_warning = self._get_temperature_alert_level(row, airport_4code)
            parsed_data['metar_temperature_warning'] = temp_warning
            
            # 风切变
            ws_dsc = str(row.get('wsDsc', '')) if pd.notna(row.get('wsDsc')) else None
            parsed_data['metar_ws_dsc'] = ws_dsc
            
            # 风切变告警处理
            ws_warning = self._get_ws_alert_level(row, airport_4code)
            parsed_data['metar_ws_warning'] = ws_warning
            
            # 变化组
            change_trend = str(row.get('changeTrend', '')) if pd.notna(row.get('changeTrend')) else None
            parsed_data['metar_change_trend'] = change_trend
            
            # 变化组告警处理
            change_trend_warning = self._get_change_trend_alert_level(row, airport_4code)
            parsed_data['metar_change_trend_warning'] = change_trend_warning
            
            # 跑道视程
            rvr_dsc = str(row.get('rvrDsc', '')) if pd.notna(row.get('rvrDsc')) else None
            parsed_data['metar_rvr_dsc'] = rvr_dsc
            
            # 解析RVR最小值
            rvr_min_org, rvr_min_val = self._parse_rvr_min_value(rvr_dsc)
            parsed_data['rvr_min_org'] = rvr_min_org
            parsed_data['rvr_min_val'] = rvr_min_val
            
            # 跑道视程告警处理
            rvr_warning = self._get_rvr_alert_level(rvr_min_val, airport_4code)
            parsed_data['metar_rvr_warning'] = rvr_warning
            
            # 积冰条件
            ice_flag = str(row.get('iceFlag', '')) if pd.notna(row.get('iceFlag')) else None
            parsed_data['metar_ice_flag'] = ice_flag
            
            # 计算实况综合告警级别
            metar_warning = self._calculate_metar_overall_warning(parsed_data)
            parsed_data['metar_warning'] = metar_warning

            try:
                from parsers.metar_elements import build_metar_elements
                parsed_data['metar_elements'] = build_metar_elements(
                    metar_content,
                    airport_4code,
                    self,
                    observation_ms=parsed_data.get('metar_observation_time'),
                )
            except Exception as exc:
                logger.error(f'构建 metar_elements 失败 [{airport_4code}]: {exc}')
                parsed_data['metar_elements'] = None
            
        except Exception as e:
            logger.warning(f"解析METAR内容失败: {str(e)}")
            # 标记为异常
            parsed_data['abnormal_label'] = 'FAIL'
            # 异常情况下设置默认告警级别
            parsed_data['metar_warning'] = 'N'
        
        return parsed_data
    
    def _get_airport_thresholds(self, airport_4code: str) -> Dict:
        """获取机场告警阈值"""
        if airport_4code in self.airport_thresholds:
            return self.airport_thresholds[airport_4code]
        
        try:
            from utils.user_settings import bound_or, get_threshold_row
            airport_info = get_threshold_row(bound_or(self.user_code, self.time_mode), airport_4code)
            
            if airport_info:
                thresholds = {
                    'visibility_red': airport_info.visibility_m_red,
                    'visibility_yellow': airport_info.visibility_m_yellow,
                    'visibility_green': airport_info.visibility_m_green,
                    'cloud_red': airport_info.cloud_min_red,
                    'cloud_yellow': airport_info.cloud_min_yellow,
                    'cloud_green': airport_info.cloud_min_green,
                    'min_cloud_amt': normalize_cloud_amt(getattr(airport_info, 'min_cloud_amt', None)),
                    'wind_red': airport_info.average_wind_speed_mps_red,
                    'wind_yellow': airport_info.average_wind_speed_mps_yellow,
                    'wind_green': airport_info.average_wind_speed_mps_green,
                    'gust_red': airport_info.gust_mps_red,
                    'gust_yellow': airport_info.gust_mps_yellow,
                    'gust_green': airport_info.gust_mps_green,
                    'temp_cold_red': airport_info.temperature_cold_red,
                    'temp_cold_yellow': airport_info.temperature_cold_yellow,
                    'temp_cold_green': airport_info.temperature_cold_green,
                    'temp_hot_red': airport_info.temperature_hot_red,
                    'temp_hot_yellow': airport_info.temperature_hot_yellow,
                    'temp_hot_green': airport_info.temperature_hot_green,
                    'rvr_red': airport_info.rvr_m_red,
                    'rvr_yellow': airport_info.rvr_m_yellow,
                    'rvr_green': airport_info.rvr_m_green,
                }
            else:
                # 没有配置时返回空字典
                thresholds = {}
            
            self.airport_thresholds[airport_4code] = thresholds
            return thresholds
            
        except Exception as e:
            logger.error(f"获取机场阈值失败: {str(e)}")
            # 异常时返回空字典
            return {}
    
    def _get_alert_level(self, value, red_threshold, yellow_threshold, green_threshold, reverse=False):
        """根据阈值判断告警等级"""
        if value is None or red_threshold is None or yellow_threshold is None or green_threshold is None:
            return 'N'
        
        if reverse:
            # 对于能见度、云高等，值越小告警等级越高
            if value <= red_threshold:
                return 'R'
            elif value <= yellow_threshold:
                return 'Y'
            elif value <= green_threshold:
                return 'G'
        else:
            # 对于风速、温度等，值越大告警等级越高
            if value >= red_threshold:
                return 'R'
            elif value >= yellow_threshold:
                return 'Y'
            elif value >= green_threshold:
                return 'G'
        
        return 'N'
    
    def _get_weather_alert_level(self, weather_code: str) -> str:
        """获取天气现象告警等级"""
        try:
            from utils.user_settings import bound_or, weather_row
            weather_alert = weather_row(bound_or(self.user_code, self.time_mode), weather_code)
            if weather_alert:
                return weather_alert.alert_level
        except Exception as e:
            logger.warning(f"查询天气告警等级失败: {str(e)}")
        
        return 'N' 

    def _get_wind_alert_level(self, row, airport_4code: str) -> str:
        """获取风速告警等级（基于原始程序逻辑）"""
        thresholds = self._get_airport_thresholds(airport_4code)
        if not thresholds:
            return 'N'
        
        wind_speed_alert = None
        gust_alert = None
        
        # 处理平均风速告警
        if pd.notna(row.get('windSpeed')):
            try:
                wind_speed_val = float(row.get('windSpeed'))
                wind_speed_alert = self._get_alert_level(
                    wind_speed_val,
                    thresholds['wind_red'],
                    thresholds['wind_yellow'],
                    thresholds['wind_green']
                )
            except (ValueError, TypeError):
                wind_speed_alert = None
        
        # 处理阵风告警
        if pd.notna(row.get('flurry')):
            try:
                gust_val = float(row.get('flurry'))
                gust_alert = self._get_alert_level(
                    gust_val,
                    thresholds['gust_red'],
                    thresholds['gust_yellow'],
                    thresholds['gust_green']
                )
            except (ValueError, TypeError):
                gust_alert = None
        
        # 取最高告警等级
        alert_levels = ['R', 'Y', 'G']
        wind_alerts = [wind_speed_alert, gust_alert]
        
        for level in alert_levels:
            if level in wind_alerts:
                return level
        
        return 'N'
    
    def _get_visibility_alert_level(self, row, airport_4code: str) -> str:
        """获取能见度告警等级（基于原始程序逻辑）"""
        thresholds = self._get_airport_thresholds(airport_4code)
        if not thresholds:
            return 'N'
        
        if pd.notna(row.get('visibility')):
            try:
                visibility_val = int(row.get('visibility'))
                return self._get_alert_level(
                    visibility_val,
                    thresholds['visibility_red'],
                    thresholds['visibility_yellow'],
                    thresholds['visibility_green'],
                    reverse=True  # 能见度越小告警等级越高
                )
            except (ValueError, TypeError):
                return 'N'
        
        return 'N'
    
    def _get_weather_alert_level_from_fields(self, weather1, weather2, weather3, row) -> tuple:
        """
        获取天气现象告警等级（基于原始程序逻辑）
        
        Returns:
            tuple: (综合告警等级, weather_type_dict字典)
        """
        weather_alerts = []
        weather_type_dict = {}  # 新增：存储 {type: alert_level} 的字典
        
        # 处理各个天气现象字段
        weather_fields = [weather1, weather2, weather3, 
                          str(row.get('proWeather', '')) if pd.notna(row.get('proWeather')) else None]
        
        for weather_field in weather_fields:
            if weather_field and weather_field.strip():
                alert_level, weather_types = self._get_weather_alert_level_single(weather_field.strip())
                
                # 保持原有逻辑：收集告警等级到列表
                if alert_level and alert_level != 'N':
                    weather_alerts.append(alert_level)
                
                # 新增逻辑：构建type和告警等级的字典
                if weather_types:  # 如果有type列表
                    # 对每个type应用相同的去重和取高值逻辑
                    for weather_type in weather_types:
                        if weather_type:  # 确保type非空
                            # 如果该type已存在，比较告警等级，保留最高的
                            if weather_type in weather_type_dict:
                                current_level = weather_type_dict[weather_type]
                                # 优先级: R > Y > G > N
                                level_priority = {'R': 4, 'Y': 3, 'G': 2, 'N': 1}
                                if level_priority.get(alert_level, 0) > level_priority.get(current_level, 0):
                                    weather_type_dict[weather_type] = alert_level
                            else:
                                weather_type_dict[weather_type] = alert_level
        
        # 取最高告警等级
        综合告警等级 = 'N'
        if weather_alerts:
            alert_levels = ['R', 'Y', 'G']
            for level in alert_levels:
                if level in weather_alerts:
                    综合告警等级 = level
                    break
        
        return (综合告警等级, weather_type_dict)
    
    def _get_weather_alert_level_single(self, weather_code: str) -> tuple:
        """
        获取单个天气现象告警等级和类型
        
        Returns:
            tuple: (alert_level, [type1, type2, type3]) 或 ('N', [])
        """
        try:
            from core.models import WeatherAlertLevels
            
            from utils.user_settings import bound_or, weather_row
            weather_alert = weather_row(bound_or(self.user_code, self.time_mode), weather_code)
            if weather_alert:
                # 收集非空的type字段
                types = []
                if weather_alert.type1 and str(weather_alert.type1).strip() and str(weather_alert.type1).strip() != 'None':
                    types.append(weather_alert.type1)
                if weather_alert.type2 and str(weather_alert.type2).strip() and str(weather_alert.type2).strip() != 'None':
                    types.append(weather_alert.type2)
                if weather_alert.type3 and str(weather_alert.type3).strip() and str(weather_alert.type3).strip() != 'None':
                    types.append(weather_alert.type3)
                return (weather_alert.alert_level, types)
            return ('N', [])
        except Exception as e:
            logger.warning(f"查询天气告警等级失败: {str(e)}")
        
        return ('N', [])
    
    def _get_cloud_alert_level(self, cloud1, cloud2, cloud3, airport_4code: str) -> str:
        """获取云组告警等级（基于原始程序逻辑）"""
        thresholds = self._get_airport_thresholds(airport_4code)
        if not thresholds:
            return 'N'
        
        # 获取最低云层高度（已按云量下限筛选）
        min_cloud_height = self._get_min_cloud_height(cloud1, cloud2, cloud3, airport_4code)
        
        if min_cloud_height is not None:
            return self._get_alert_level(
                min_cloud_height,
                thresholds['cloud_red'],
                thresholds['cloud_yellow'],
                thresholds['cloud_green'],
                reverse=True  # 云高越小告警等级越高
            )
        
        return 'N'
    
    def _get_temperature_alert_level(self, row, airport_4code: str) -> str:
        """获取温度告警等级（基于原始程序逻辑）"""
        thresholds = self._get_airport_thresholds(airport_4code)
        if not thresholds:
            return 'N'
        
        if pd.notna(row.get('temperature')):
            try:
                temp_val = float(row.get('temperature'))
                
                # 低温告警判断
                if temp_val <= thresholds['temp_cold_red']:
                    return 'R'
                elif temp_val <= thresholds['temp_cold_yellow']:
                    return 'Y'
                elif temp_val <= thresholds['temp_cold_green']:
                    return 'G'
                # 高温告警判断
                elif temp_val >= thresholds['temp_hot_red']:
                    return 'R'
                elif temp_val >= thresholds['temp_hot_yellow']:
                    return 'Y'
                elif temp_val >= thresholds['temp_hot_green']:
                    return 'G'
                
            except (ValueError, TypeError):
                return 'N'
        
        return 'N'
    
    def _parse_rvr_min_value(self, rvr_dsc: str) -> tuple:
        """
        解析RVR最小值
        
        Args:
            rvr_dsc: RVR描述字符串
            
        Returns:
            tuple: (rvr_min_org, rvr_min_val)
        """
        if not rvr_dsc or not isinstance(rvr_dsc, str):
            return None, None
        
        import re
        
        # 查找所有符合格式的RVR数据组
        # 格式：/P(可选)+DDDD(4位数字)+FT(可选)
        pattern = r'/P?(\d{4})(?:FT)?(?=[^\d]|$)'
        matches = re.finditer(pattern, rvr_dsc)
        
        candidates = []
        for match in matches:
            full_match = match.group(0)  # 完整匹配的字符串
            digits = match.group(1)  # 四位数字
            has_p = full_match.startswith('/P')
            has_ft = full_match.endswith('FT')
            value = int(digits)
            
            candidates.append({
                'value': value,
                'has_p': has_p,
                'has_ft': has_ft,
                'full_match': full_match
            })
        
        if not candidates:
            return None, None
        
        # 找到数值最小的
        min_value = min(c['value'] for c in candidates)
        min_candidates = [c for c in candidates if c['value'] == min_value]
        
        # 如果有多个，优先选择没有P的
        no_p_candidates = [c for c in min_candidates if not c['has_p']]
        if no_p_candidates:
            selected = no_p_candidates[0]
        else:
            selected = min_candidates[0]
        
        # 计算rvr_min_org
        if selected['has_p']:
            rvr_min_org = selected['value'] + 30
        else:
            rvr_min_org = selected['value']
        
        # 计算rvr_min_val
        if selected['has_ft']:
            rvr_min_val = int(rvr_min_org / 3)
        else:
            rvr_min_val = rvr_min_org
        
        return rvr_min_org, rvr_min_val
    
    def _get_rvr_alert_level(self, rvr_min_val: int, airport_4code: str) -> str:
        """获取跑道视程告警等级"""
        if rvr_min_val is None:
            return 'N'
        
        thresholds = self._get_airport_thresholds(airport_4code)
        if not thresholds:
            return 'N'
        
        # 使用RVR阈值判断告警等级
        rvr_red = thresholds.get('rvr_red')
        rvr_yellow = thresholds.get('rvr_yellow')
        rvr_green = thresholds.get('rvr_green')
        
        if rvr_red is None or rvr_yellow is None or rvr_green is None:
            return 'N'
        
        return self._get_alert_level(
            rvr_min_val,
            rvr_red,
            rvr_yellow,
            rvr_green,
            reverse=True  # RVR越小告警等级越高
        )
    
    def _get_ws_alert_level(self, row, airport_4code: str) -> str:
        """获取风切变告警等级"""
        # 检查是否有风切变数据
        ws_dsc = row.get('wsDsc', None)
        
        # 有风切变数据即红色告警
        if ws_dsc and pd.notna(ws_dsc) and str(ws_dsc).strip():
            return 'R'
        else:
            return 'N'
    
    def _get_change_trend_alert_level(self, row, airport_4code: str) -> str:
        """获取变化组告警等级（改：NOSIG不告警）"""
        change_trend = row.get('changeTrend', None)
        # 判断非空、非None、非全空，并且排除等于'NOSIG'（忽略前后空格和大小写）
        if (
            change_trend
            and pd.notna(change_trend)
            and str(change_trend).strip()
            and str(change_trend).strip().upper() != 'NOSIG'
        ):
            return 'R'
        else:
            return 'N'

    def _convert_timestamp_to_utc_string(self, timestamp_value) -> str:
        """
        将时间戳转换为UTC标准时间格式字符串
        
        Args:
            timestamp_value: 时间戳值（毫秒级）或时间字符串
            
        Returns:
            str: UTC时间字符串，格式为 'YYYY-MM-DD HH:MM:SS'
        """
        if not timestamp_value:
            return ''
        
        timestamp_str = str(timestamp_value).strip()
        
        # 检查是否为时间戳（纯数字）
        if timestamp_str.isdigit():
            try:
                # 将毫秒级时间戳转换为UTC时间
                timestamp_ms = float(timestamp_str)
                timestamp_s = timestamp_ms / 1000
                utc_datetime = datetime.utcfromtimestamp(timestamp_s)
                return utc_datetime.strftime('%Y-%m-%d %H:%M:%S')
            except (ValueError, OSError) as e:
                logger.warning(f"时间戳转换失败: {timestamp_str}, 错误: {e}")
                return timestamp_str
        else:
            # 如果不是时间戳，直接返回原值
            return timestamp_str
    
    def _combine_weather_info(self, weather1, weather2, weather3):
        """组合天气信息（基于原始程序逻辑）"""
        weather_parts = []
        for weather in [weather1, weather2, weather3]:
            if weather and weather.strip():
                weather_parts.append(weather.strip())
        
        return ' '.join(weather_parts) if weather_parts else None
    
    def _combine_cloud_info(self, cloud1, cloud2, cloud3):
        """组合云层信息（基于原始程序逻辑）"""
        cloud_parts = []
        for cloud in [cloud1, cloud2, cloud3]:
            if cloud and cloud.strip():
                cloud_parts.append(cloud.strip())
        
        return ' '.join(cloud_parts) if cloud_parts else None
    
    def _min_cloud_amt_for(self, airport_4code: str) -> str:
        """该机场计入最低云底高的最低云量；无配置时按 SCT。"""
        if not airport_4code:
            return normalize_cloud_amt(None)
        thresholds = self._get_airport_thresholds(airport_4code)
        if not thresholds:
            return normalize_cloud_amt(None)
        return normalize_cloud_amt(thresholds.get('min_cloud_amt'))

    def _get_min_cloud_height(self, cloud1, cloud2, cloud3, airport_4code=None):
        """在达到云量下限的云组中取最低云底高。低于下限的云组不参与。"""
        return lowest_height_in_cloud_strings(
            [cloud1, cloud2, cloud3],
            self._min_cloud_amt_for(airport_4code),
        )
    
    def _calculate_metar_overall_warning(self, parsed_data: Dict) -> str:
        """
        计算METAR实况综合告警级别
        与前端createWeatherInfo函数中的逻辑完全一致
        
        Args:
            parsed_data: 解析后的METAR数据字典
            
        Returns:
            str: 综合告警级别 ('R', 'Y', 'G', 'N')
        """
        alert_levels = []
        
        # 收集各天气要素的告警级别
        # 风向风速告警
        if parsed_data.get('metar_wind_warning') and parsed_data['metar_wind_warning'] != 'N':
            alert_levels.append(parsed_data['metar_wind_warning'])
        
        # 能见度告警
        if parsed_data.get('metar_visibility_warning') and parsed_data['metar_visibility_warning'] != 'N':
            alert_levels.append(parsed_data['metar_visibility_warning'])
        
        # 天气现象告警
        if parsed_data.get('metar_weather_warning') and parsed_data['metar_weather_warning'] != 'N':
            alert_levels.append(parsed_data['metar_weather_warning'])
        
        # 云组告警
        if parsed_data.get('metar_cloud_warning') and parsed_data['metar_cloud_warning'] != 'N':
            alert_levels.append(parsed_data['metar_cloud_warning'])
        
        # 温度告警
        if parsed_data.get('metar_temperature_warning') and parsed_data['metar_temperature_warning'] != 'N':
            alert_levels.append(parsed_data['metar_temperature_warning'])
        
        # 跑道视程告警
        if parsed_data.get('metar_rvr_warning') and parsed_data['metar_rvr_warning'] != 'N':
            alert_levels.append(parsed_data['metar_rvr_warning'])
        
        # 变化组告警
        if parsed_data.get('metar_change_trend_warning') and parsed_data['metar_change_trend_warning'] != 'N':
            alert_levels.append(parsed_data['metar_change_trend_warning'])
        
        # 按优先级取最高告警等级：R > Y > G > N
        if 'R' in alert_levels:
            return 'R'
        elif 'Y' in alert_levels:
            return 'Y'
        elif 'G' in alert_levels:
            return 'G'
        else:
            return 'N'
    
    def _add_popup_fields(self, parsed_data: Dict):
        """
        为parsed_data添加弹窗相关字段，并进行弹窗判断
        
        Args:
            parsed_data: 解析后的METAR数据字典（会被修改）
        """
        import json
        from django.utils import timezone
        
        # 确定user_code值
        if self.time_mode == 'test':
            user_code = 'test'
        elif self.user_code:
            user_code = self.user_code
        else:
            user_code = 'system'
        
        # 提取weather_type_dict并转换为JSON字符串
        weather_type_dict = parsed_data.pop('weather_type_dict', {})
        
        # 获取当前时间（用于created_at和updated_at）
        current_time = timezone.now()
        current_time_ms = int(current_time.timestamp() * 1000)
        
        # 添加基础字段
        parsed_data['user_code'] = user_code
        parsed_data['popup_handle_records'] = {}
        parsed_data['metar_weather_type'] = json.dumps(weather_type_dict) if weather_type_dict else None
        parsed_data['created_at'] = current_time_ms
        parsed_data['updated_at'] = current_time
        
        popup_settings = self._get_popup_settings()
        op_level = (popup_settings.operation_metar_popup_level if popup_settings else None) or 'Y'
        park_level = (popup_settings.parking_metar_popup_level if popup_settings else None) or 'Y'
        op_leeway = popup_settings.operation_metar_popup_leeway if popup_settings else None

        operation_met = self._check_operation_popup(
            parsed_data, weather_type_dict, op_level, op_leeway
        )
        parking_met = self._check_parking_popup(
            parsed_data, weather_type_dict, park_level
        )

        if operation_met:
            parsed_data['operation_popup'] = (
                'I' if self._check_type_intercept(
                    parsed_data, weather_type_dict, 'operation', popup_settings
                ) else 'Y'
            )
        else:
            parsed_data['operation_popup'] = 'N'

        if parking_met:
            parsed_data['parking_popup'] = (
                'I' if self._check_type_intercept(
                    parsed_data, weather_type_dict, 'parking', popup_settings
                ) else 'Y'
            )
        else:
            parsed_data['parking_popup'] = 'N'

        if parsed_data['operation_popup'] in ('Y', 'I') or parsed_data['parking_popup'] in ('Y', 'I'):
            parsed_data['popup_time'] = current_time_ms
        else:
            parsed_data['popup_time'] = None

        parsed_data['operation_metar_popup_leeway'] = op_leeway
        parsed_data['operation_metar_popup_level'] = op_level
        parsed_data['parking_metar_popup_level'] = park_level
    
    def _get_popup_settings(self):
        """获取弹窗配置"""
        try:
            from core.models import PopupSettings
            
            # 确定查找的user_code
            if self.time_mode == 'test':
                lookup_user_code = 'test'
            elif self.user_code:
                lookup_user_code = self.user_code
            else:
                lookup_user_code = 'default'
            
            # 查找配置
            popup_settings = PopupSettings.objects.filter(user_code=lookup_user_code).first()
            
            # 如果没找到，使用default
            if not popup_settings:
                popup_settings = PopupSettings.objects.filter(user_code='default').first()
            
            return popup_settings
            
        except Exception as e:
            logger.error(f"获取弹窗配置失败: {e}")
            return None
    
    def _check_alert_level(self, actual_level: str, threshold_level: str) -> bool:
        """检查告警等级是否达到阈值"""
        if not actual_level or not threshold_level:
            return False
        
        ALERT_PRIORITY = {'R': 4, 'Y': 3, 'G': 2, 'N': 1}
        actual_priority = ALERT_PRIORITY.get(actual_level, 0)
        threshold_priority = ALERT_PRIORITY.get(threshold_level, 0)
        
        return actual_priority >= threshold_priority
    
    def _check_operation_popup(self, parsed_data: Dict, weather_type_dict: Dict, 
                                threshold_level: str, threshold_hours: int) -> bool:
        """
        检查运行类弹窗条件
        
        Args:
            parsed_data: 解析后的数据
            weather_type_dict: 天气类型字典
            threshold_level: 告警等级阈值
            threshold_hours: 时间阈值（小时）
            
        Returns:
            是否满足运行类弹窗条件
        """
        try:
            from parsers.models import Flight
            
            # 1. 检查告警等级
            alert_met = False
            
            # 检查各告警字段
            alert_fields = [
                parsed_data.get('metar_wind_warning'),
                parsed_data.get('metar_visibility_warning'),
                parsed_data.get('metar_cloud_warning'),
                parsed_data.get('metar_temperature_warning'),
                parsed_data.get('metar_change_trend_warning'),
                parsed_data.get('metar_rvr_warning'),
                parsed_data.get('metar_ws_warning'),
            ]
            
            for alert_level in alert_fields:
                if self._check_alert_level(alert_level, threshold_level):
                    alert_met = True
                    break
            
            # 检查天气类型告警
            if not alert_met and weather_type_dict:
                for weather_type, alert_level in weather_type_dict.items():
                    if self._check_alert_level(alert_level, threshold_level):
                        alert_met = True
                        break
            
            if not alert_met:
                return False
            
            # 2. 获取flight数据
            airport_4code = parsed_data.get('airport_4code')
            flight = Flight.objects.filter(airport_4code=airport_4code).first()
            
            if not flight:
                return False
            
            # 3. 检查时间条件
            time_condition_met = False
            metar_obs_time = parsed_data.get('metar_observation_time')
            if metar_obs_time and threshold_hours:
                times = []
                if flight.closest_departure_time_of_arriving_flight:
                    times.append(flight.closest_departure_time_of_arriving_flight)
                if flight.closest_departure_time_at_this_airport:
                    times.append(flight.closest_departure_time_at_this_airport)
                
                if times:
                    min_time = min(times)
                    # 起飞 − 观测：过去时刻为负，恒 ≤ 裕度，时间条件成立
                    time_diff = min_time - metar_obs_time
                    threshold_ms = threshold_hours * 3600000
                    time_condition_met = (time_diff <= threshold_ms)
            
            # 4. 检查en_route条件
            en_route_condition_met = bool(flight.en_route)
            
            # 5. 满足条件：告警 AND (时间 OR en_route)
            return time_condition_met or en_route_condition_met
            
        except Exception as e:
            logger.error(f"检查运行类弹窗条件失败: {e}")
            return False
    
    def _check_parking_popup(self, parsed_data: Dict, weather_type_dict: Dict, 
                              threshold_level: str) -> bool:
        """
        检查停场类弹窗条件
        
        Args:
            parsed_data: 解析后的数据
            weather_type_dict: 天气类型字典
            threshold_level: 告警等级阈值
            
        Returns:
            是否满足停场类弹窗条件
        """
        try:
            from core.models import AircraftParkingInfo
            from django.conf import settings
            import json
            
            # 1. 检查告警等级
            alert_met = False
            
            # 检查风速告警
            if self._check_alert_level(parsed_data.get('metar_wind_warning'), threshold_level):
                alert_met = True
            
            # 检查温度告警（仅当温度<-20时）
            if not alert_met:
                metar_temp = parsed_data.get('metar_temperature')
                if metar_temp:
                    try:
                        temp_str = str(metar_temp)
                        if temp_str.startswith('M'):
                            temp_value = -int(temp_str[1:])
                        else:
                            temp_value = int(temp_str)
                        
                        if temp_value < -20:
                            if self._check_alert_level(parsed_data.get('metar_temperature_warning'), threshold_level):
                                alert_met = True
                    except (ValueError, TypeError):
                        pass
            
            # 检查特定天气类型的告警
            if not alert_met and weather_type_dict:
                parking_weather_types = settings.MTWS_CONFIG['POPUP_CONFIG']['PARKING_WEATHER_TYPES']
                for weather_type, alert_level in weather_type_dict.items():
                    if weather_type in parking_weather_types:
                        if self._check_alert_level(alert_level, threshold_level):
                            alert_met = True
                            break
            
            if not alert_met:
                return False
            
            airport_4code = parsed_data.get('airport_4code')
            
            # 2. 检查停场条件
            parking_condition_met = False
            latest_parking = AircraftParkingInfo.objects.order_by('-parse_time').first()
            
            if latest_parking and latest_parking.airport_4code:
                parking_list = latest_parking.airport_4code
                if isinstance(parking_list, str):
                    parking_list = json.loads(parking_list)
                parking_condition_met = (airport_4code in parking_list)
            
            # 3. 检查en_route条件
            from parsers.models import Flight
            en_route_condition_met = False
            flight = Flight.objects.filter(airport_4code=airport_4code).first()
            if flight:
                en_route_condition_met = bool(flight.en_route)
            
            # 4. 满足条件：告警 AND (停场 OR en_route)
            return parking_condition_met or en_route_condition_met
            
        except Exception as e:
            logger.error(f"检查停场类弹窗条件失败: {e}")
            return False
    
    def _check_type_intercept(self, parsed_data: Dict, weather_type_dict: Dict, popup_type: str, popup_settings) -> bool:
        """
        数值降级时标记 I。始终按规则判断，不读库开关。
        """
        try:
            last_metar_sqc = parsed_data.get('last_metar_sqc')
            if not last_metar_sqc:
                return False

            previous_metar = Metar.objects.filter(sqc=str(last_metar_sqc)).first()
            if not previous_metar:
                return False

            prev_flag = (
                previous_metar.operation_popup if popup_type == 'operation'
                else previous_metar.parking_popup
            )
            if prev_flag not in ('Y', 'I'):
                return False

            current_time = parsed_data.get('metar_observation_time')
            previous_time = previous_metar.metar_observation_time
            if not current_time or not previous_time:
                return False
            time_diff = current_time - previous_time
            if time_diff <= 0 or time_diff > 4200000:
                return False

            if parsed_data.get('user_code') != previous_metar.user_code:
                return False

            previous_weather_type_dict = {}
            if previous_metar.metar_weather_type:
                try:
                    previous_weather_type_dict = json.loads(previous_metar.metar_weather_type)
                except Exception:
                    previous_weather_type_dict = {}

            if not popup_settings:
                return False

            if popup_type == 'operation':
                return self._check_operation_intercept(
                    parsed_data, weather_type_dict, previous_metar,
                    previous_weather_type_dict, popup_settings
                )
            if popup_type == 'parking':
                return self._check_parking_intercept(
                    parsed_data, weather_type_dict, previous_metar,
                    previous_weather_type_dict, popup_settings
                )
            return False

        except Exception as e:
            logger.error(f"弹窗拦截判断失败: {e}")
            return False
    
    def _check_operation_intercept(self, current_data: Dict, current_weather_dict: Dict,
                                   previous_metar, previous_weather_dict: Dict, popup_settings) -> bool:
        """
        检查运行类弹窗拦截条件（方案B：只对比触发告警的要素）

        前置快速判断：metar_change_trend_warning 或 metar_ws_warning >= 阈值 → 直接不拦截
        要素对比：只检查 warning >= operation_metar_popup_level 的项，全部通过才拦截
        """
        try:
            threshold_level = popup_settings.operation_metar_popup_level

            # 前置：change_trend 或 WS 告警达到阈值 → 直接不拦截
            if self._check_alert_level(current_data.get('metar_change_trend_warning'), threshold_level):
                return False
            if self._check_alert_level(current_data.get('metar_ws_warning'), threshold_level):
                return False

            # （1）风速/阵风
            if self._check_alert_level(current_data.get('metar_wind_warning'), threshold_level):
                if not self._is_value_same_or_smaller(current_data.get('metar_wind_speed_val'), previous_metar.metar_wind_speed_val):
                    return False
                if not self._is_value_same_or_smaller(current_data.get('metar_gust_val'), previous_metar.metar_gust_val, none_is_smaller=True):
                    return False

            # （2）能见度 + RVR（任一 warning 达到阈值则同时对比两项）
            vis_triggered = self._check_alert_level(current_data.get('metar_visibility_warning'), threshold_level)
            rvr_triggered = self._check_alert_level(current_data.get('metar_rvr_warning'), threshold_level)
            if vis_triggered or rvr_triggered:
                if not self._is_value_same_or_larger(current_data.get('metar_visibility_val'), previous_metar.metar_visibility_val, none_is_larger=True):
                    return False
                if not self._check_rvr_intercept_condition(current_data.get('rvr_min_val'), previous_metar.rvr_min_val):
                    return False

            # （3）天气现象（全部类型）
            if self._check_alert_level(current_data.get('metar_weather_warning'), threshold_level):
                if not self._check_weather_type_downgrade(current_weather_dict, previous_weather_dict):
                    return False

            # （4）云底高
            if self._check_alert_level(current_data.get('metar_cloud_warning'), threshold_level):
                if not self._is_value_same_or_larger(current_data.get('metar_min_cloud_height'), previous_metar.metar_min_cloud_height, none_is_larger=True):
                    return False

            # （5）温度（运行类专用逻辑）
            if self._check_alert_level(current_data.get('metar_temperature_warning'), threshold_level):
                if not self._check_operation_temperature_intercept(current_data.get('metar_temp_val'), previous_metar.metar_temp_val):
                    return False

            return True

        except Exception as e:
            logger.error(f"检查运行类拦截条件失败: {e}")
            return False
    
    def _check_parking_intercept(self, current_data: Dict, current_weather_dict: Dict,
                                 previous_metar, previous_weather_dict: Dict, popup_settings) -> bool:
        """
        检查停场类弹窗拦截条件（方案B：只对比触发告警的要素）

        要素对比：只检查 warning >= parking_metar_popup_level 的项，全部通过才拦截
        不涉及能见度、RVR、云底高
        """
        try:
            from django.conf import settings

            threshold_level = popup_settings.parking_metar_popup_level
            parking_weather_types = settings.MTWS_CONFIG['POPUP_CONFIG']['PARKING_WEATHER_TYPES']

            # （1）风速/阵风
            if self._check_alert_level(current_data.get('metar_wind_warning'), threshold_level):
                if not self._is_value_same_or_smaller(current_data.get('metar_wind_speed_val'), previous_metar.metar_wind_speed_val):
                    return False
                if not self._is_value_same_or_smaller(current_data.get('metar_gust_val'), previous_metar.metar_gust_val, none_is_smaller=True):
                    return False

            # （2）停场类天气类型（仅 S/F/I/G/H）
            if self._check_alert_level(current_data.get('metar_weather_warning'), threshold_level):
                if not self._check_weather_type_downgrade(current_weather_dict, previous_weather_dict, filter_types=parking_weather_types):
                    return False

            # （3）温度（停场类专用逻辑）
            if self._check_alert_level(current_data.get('metar_temperature_warning'), threshold_level):
                if not self._check_parking_temperature_intercept(current_data.get('metar_temp_val'), previous_metar.metar_temp_val):
                    return False

            return True

        except Exception as e:
            logger.error(f"检查停场类拦截条件失败: {e}")
            return False
    
    def _is_value_same_or_smaller(self, current_val, previous_val, none_is_smaller=False) -> bool:
        """
        检查当前值是否不变或更小
        
        Args:
            current_val: 当前值
            previous_val: 之前的值
            none_is_smaller: None是否认为更小（符合条件）
            
        Returns:
            是否满足条件
        """
        # 如果当前值为None
        if current_val is None:
            if none_is_smaller:
                return True
            else:
                # 如果之前值也是None，认为不变，符合条件
                return previous_val is None
        
        # 如果之前值为None，当前值不为None，认为更大，不符合条件
        if previous_val is None:
            return False
        
        # 都不为None，比较大小
        return current_val <= previous_val
    
    def _is_value_same_or_larger(self, current_val, previous_val, none_is_larger=False) -> bool:
        """
        检查当前值是否不变或更大
        
        Args:
            current_val: 当前值
            previous_val: 之前的值
            none_is_larger: None是否认为更大（符合条件）
            
        Returns:
            是否满足条件
        """
        # 如果当前值为None
        if current_val is None:
            if none_is_larger:
                return True
            else:
                # 如果之前值也是None，认为不变，符合条件
                return previous_val is None
        
        # 如果之前值为None，当前值不为None，认为更小，不符合条件
        if previous_val is None:
            return False
        
        # 都不为None，比较大小
        return current_val >= previous_val
    
    def _check_temperature_intercept_condition(self, current_temp, previous_temp) -> bool:
        """
        检查温度拦截条件
        
        条件：
        - 温度值更小且>20，或为空时符合条件
        - 温度值更大且<-20，或为空时符合条件
        
        Returns:
            是否满足条件
        """
        # 如果当前温度为空，符合条件
        if current_temp is None:
            return True
        
        # 如果之前温度为空，当前不为空
        if previous_temp is None:
            # 当前温度在-20到20之间，符合条件
            if -20 <= current_temp <= 20:
                return True
            else:
                return False
        
        # 都不为空，比较
        # 如果温度变小
        if current_temp < previous_temp:
            # 需要当前温度>20才符合条件
            return current_temp > 20
        # 如果温度变大
        elif current_temp > previous_temp:
            # 需要当前温度<-20才符合条件
            return current_temp < -20
        else:
            # 温度不变，符合条件
            return True
    
    def _check_rvr_intercept_condition(self, current_rvr, previous_rvr) -> bool:
        """
        RVR拦截条件：
        - 上一份有RVR，当前有RVR：当前 >= 上一份 → 通过
        - 上一份有RVR，当前无RVR → 通过
        - 上一份无RVR，当前有RVR → 不通过
        - 两者均无RVR → 通过
        """
        if previous_rvr is None and current_rvr is None:
            return True
        if previous_rvr is None and current_rvr is not None:
            return False
        if previous_rvr is not None and current_rvr is None:
            return True
        return current_rvr >= previous_rvr

    def _check_operation_temperature_intercept(self, current_temp, previous_temp) -> bool:
        """
        运行类温度拦截条件：
        - current_temp 为 None → 通过
        - current_temp 不为 None 而 previous_temp 为 None → 不通过
        - current_temp >= 0：当前 <= 上一份（降低或不变）→ 通过
        - current_temp < 0：当前 >= 上一份（升高或不变）→ 通过
        """
        if current_temp is None:
            return True
        if previous_temp is None:
            return False
        if current_temp >= 0:
            return current_temp <= previous_temp
        else:
            return current_temp >= previous_temp

    def _check_parking_temperature_intercept(self, current_temp, previous_temp) -> bool:
        """
        停场类温度拦截条件：
        - current_temp < 0 且 current_temp < previous_temp → 通过
        - 其他所有情况 → 不通过
        """
        if current_temp is None or previous_temp is None:
            return False
        return current_temp < 0 and current_temp < previous_temp

    def _check_weather_type_downgrade(self, current_dict: Dict, previous_dict: Dict,
                                      all_types=False, filter_types=None) -> bool:
        """
        检查天气类型告警等级是否不变或降级
        
        Args:
            current_dict: 当前天气类型字典
            previous_dict: 之前天气类型字典
            all_types: 是否检查所有类型
            filter_types: 要检查的特定类型列表（如停场类的['S', 'F', 'I', 'G', 'H']）
            
        Returns:
            是否满足条件（所有类型都不变或降级）
        """
        ALERT_PRIORITY = {'R': 4, 'Y': 3, 'G': 2, 'N': 1}
        
        # 如果需要过滤类型
        if filter_types:
            # 过滤当前和之前的字典
            current_dict = {k: v for k, v in current_dict.items() if k in filter_types}
            previous_dict = {k: v for k, v in previous_dict.items() if k in filter_types}
        
        # 检查之前存在的每个天气类型
        for weather_type, previous_level in previous_dict.items():
            if weather_type in current_dict:
                # 该类型仍然存在，检查是否降级或不变
                current_level = current_dict[weather_type]
                current_priority = ALERT_PRIORITY.get(current_level, 0)
                previous_priority = ALERT_PRIORITY.get(previous_level, 0)
                
                # 如果当前等级更高（告警升级），不符合条件
                if current_priority > previous_priority:
                    return False
            # 如果类型消失了，认为是降级，符合条件
        
        # 检查当前新出现的天气类型（之前没有的）
        for weather_type, current_level in current_dict.items():
            if weather_type not in previous_dict:
                # 新出现的天气类型，不符合降级条件
                return False
        
        return True
    