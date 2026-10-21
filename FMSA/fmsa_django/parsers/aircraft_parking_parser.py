"""
飞机停场解析器
专门处理飞机停场信息的独立解析器
"""

import pandas as pd
from datetime import datetime
from typing import List, Dict
import logging

from django.utils import timezone
from django.conf import settings
from runtime_db.models import AircraftParkingInfo
from data_adapters.adapter_factory import AdapterFactory
from utils.time_manager import TimeManager

logger = logging.getLogger('fmsa.parsers')


class AircraftParkingParser:
    """飞机停场解析器类"""
    
    def __init__(self, time_mode='current', token=None):
        """
        初始化飞机停场解析器
        
        Args:
            time_mode: 时间模式，'current' 或 'test'
            token: current模式下的认证token
        """
        self.time_mode = time_mode
        self.token = token
        
        # 从settings获取配置
        self.config = settings.FMSA_CONFIG.get('AIRCRAFT_PARKING_CONFIG', {})
        self.past_hours = self.config.get('PAST_HOURS', 72)
        self.carrier_code = self.config.get('CARRIER_CODE', 'O3')
        self.max_records = self.config.get('MAX_RECORDS', 800)
        
        # 设置当前时间
        self.current_time = TimeManager.get_current_time_local(time_mode)
            
        logger.info(f"飞机停场解析器初始化完成，时间模式: {time_mode}, 当前时间: {self.current_time}")
        logger.info(f"配置参数: 过去{self.past_hours}小时, 承运人: {self.carrier_code}, 最大记录: {self.max_records}")
    
    def parse_and_save(self):
        """
        解析并保存飞机停场数据（与解析管理器接口保持一致）
        
        Returns:
            Dict: 解析结果统计
        """
        return self.parse_aircraft_parking_data()
    
    def parse_aircraft_parking_data(self):
        """
        解析飞机停场数据的主入口方法
        
        Returns:
            Dict: 解析结果统计
        """
        logger.info("开始解析飞机停场数据")
        start_time = datetime.now()
        
        try:
            # 1. 获取数据适配器并读取数据
            adapter = AdapterFactory.create_adapter(time_mode=self.time_mode, token=self.token)
            df = adapter.get_aircraft_parking_data(
                carrier_code=self.carrier_code,
                past_hours=self.past_hours
            )
            
            if df.empty:
                logger.warning("未获取到飞机停场数据")
                return {'success': False, 'message': '未获取到飞机停场数据', 'airport_count': 0}
            
            logger.info(f"获取到飞机停场原始数据 {len(df)} 行")
            
            # 2. 分析飞机停场状态
            parking_airports = self._analyze_aircraft_parking(df)
            logger.info(f"分析得到 {len(parking_airports)} 个有飞机停场的机场")
            
            # 3. 保存停场数据
            self._save_parking_data(parking_airports)
            
            # 4. 清理历史数据
            self._cleanup_old_records()
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            logger.info(f"飞机停场数据解析完成，耗时: {duration:.2f}秒")
            
            return {
                'success': True,
                'message': '飞机停场数据解析成功',
                'airport_count': len(parking_airports),
                'duration': duration
            }
            
        except Exception as e:
            logger.error(f"解析飞机停场数据失败: {str(e)}")
            return {
                'success': False,
                'message': f'解析失败: {str(e)}',
                'airport_count': 0
            }
    
    def _analyze_aircraft_parking(self, df: pd.DataFrame) -> List[str]:
        """
        分析飞机停场状态
        
        Args:
            df: 航班数据
            
        Returns:
            List[str]: 有飞机停场的机场代码列表
        """
        try:
            parking_airports = set()
            
            # 按飞机注册号分组处理
            for acReg, group in df.groupby('acReg'):
                try:
                    # 检查必需字段是否存在
                    if 'atd' not in group.columns or 'ata' not in group.columns or 'arrivalAirport' not in group.columns:
                        continue
                    
                    # 检查是否有"已起飞但未到达"的航班
                    in_flight = group[
                        (group['atd'].notna()) &  # 有实际起飞时间
                        (group['ata'].isna())     # 没有实际到达时间
                    ]
                    
                    # 如果有飞行中的航班，跳过该飞机
                    if not in_flight.empty:
                        continue
                    
                    # 找到最新的到达记录
                    ata_records = group[group['ata'].notna()]
                    if not ata_records.empty:
                        # 找到ata时间戳最大的记录
                        latest_arrival = ata_records.loc[ata_records['ata'].idxmax()]
                        arrival_airport = latest_arrival['arrivalAirport']
                        
                        if arrival_airport and str(arrival_airport).strip():
                            parking_airports.add(str(arrival_airport).strip())
                            
                except Exception as e:
                    logger.warning(f"处理飞机 {acReg} 时发生错误: {e}")
                    continue
            
            # 转换为排序后的列表
            result = sorted(list(parking_airports))
            logger.info(f"停场机场: {result}")
            
            return result
            
        except Exception as e:
            logger.error(f"分析飞机停场状态时发生错误: {e}")
            return []
    
    def _save_parking_data(self, parking_airports: List[str]):
        """
        保存停场数据到数据库
        
        Args:
            parking_airports: 有飞机停场的机场代码列表
        """
        try:
            # 创建新记录，存储毫秒级时间戳
            current_time_ms = int(timezone.now().timestamp() * 1000)
            AircraftParkingInfo.objects.create(
                airport_4code=parking_airports,  # 存储机场列表
                parse_time=current_time_ms
            )
            
            logger.info(f"成功保存停场数据: {len(parking_airports)} 个机场")
            
        except Exception as e:
            logger.error(f"保存停场数据失败: {e}")
            raise
    
    def _cleanup_old_records(self):
        """
        清理旧的停场记录，只保留最新的N条
        """
        try:
            # 获取当前记录总数
            total_count = AircraftParkingInfo.objects.count()
            
            if total_count > self.max_records:
                # 计算需要删除的记录数
                delete_count = total_count - self.max_records
                
                # 获取最旧的记录ID列表
                old_records = AircraftParkingInfo.objects.order_by('parse_time')[:delete_count]
                old_ids = list(old_records.values_list('id', flat=True))
                
                # 删除旧记录
                AircraftParkingInfo.objects.filter(id__in=old_ids).delete()
                
                logger.info(f"清理了 {delete_count} 条旧记录，当前保留 {self.max_records} 条记录")
            
        except Exception as e:
            logger.error(f"清理旧记录失败: {e}")
