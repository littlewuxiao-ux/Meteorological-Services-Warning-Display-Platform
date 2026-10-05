"""
数据库管理工具类
提供数据清理、去重、批量操作等功能
"""

from django.db import transaction
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from typing import List, Dict, Any, Optional, Type
import logging

from core.models import AirportInfo, AirportAlertThresholds, WeatherAlertLevels, Carrier, SystemConfig
from parsers.models import Flight, Metar, Taf, ParseLog

logger = logging.getLogger('mtws.database')


class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self):
        self.config = settings.MTWS_CONFIG
        self.retention_config = self.config['DATA_RETENTION']
    
    def cleanup_old_data(self, model_class: Type, max_records: int = None, 
                        field_name: str = 'created_at') -> int:
        """
        清理旧数据
        
        Args:
            model_class: 模型类
            max_records: 最大保留记录数
            field_name: 排序字段名
            
        Returns:
            int: 删除的记录数
        """
        try:
            if max_records is None:
                # 从配置获取最大记录数
                if model_class == Metar:
                    max_records = self.retention_config['metar_max_records']
                elif model_class == Taf:
                    max_records = self.retention_config['taf_max_records']
                elif model_class == Flight:
                    max_records = self.retention_config['flight_max_records']
                else:
                    max_records = 5000  # 默认值
            
            # 获取当前记录数
            total_count = model_class.objects.count()
            
            if total_count <= max_records:
                logger.info(f"{model_class.__name__}: 当前记录数 {total_count}，无需清理")
                return 0
            
            # 计算需要删除的记录数
            delete_count = total_count - max_records
            
            # 优先删除异常记录
            deleted_abnormal = self._delete_abnormal_records(model_class, delete_count)
            
            # 如果还需要删除更多记录，按时间删除最旧的
            remaining_delete = delete_count - deleted_abnormal
            if remaining_delete > 0:
                deleted_old = self._delete_old_records(model_class, remaining_delete, field_name)
            else:
                deleted_old = 0
            
            total_deleted = deleted_abnormal + deleted_old
            logger.info(f"{model_class.__name__}: 清理完成，删除 {total_deleted} 条记录")
            
            return total_deleted
            
        except Exception as e:
            logger.error(f"清理 {model_class.__name__} 数据失败: {e}")
            return 0
    
    def _delete_abnormal_records(self, model_class: Type, max_delete: int) -> int:
        """
        删除异常记录
        
        Args:
            model_class: 模型类
            max_delete: 最大删除数量
            
        Returns:
            int: 删除的记录数
        """
        try:
            # 查找异常记录
            abnormal_records = model_class.objects.filter(
                abnormal_label='FAIL'
            ).order_by('created_at')[:max_delete]
            
            if not abnormal_records:
                return 0
            
            # 批量删除
            deleted_count = 0
            batch_size = self.retention_config.get('cleanup_batch_size', 1000)
            
            for i in range(0, len(abnormal_records), batch_size):
                batch = abnormal_records[i:i + batch_size]
                ids_to_delete = [record.id for record in batch]
                
                with transaction.atomic():
                    deleted = model_class.objects.filter(id__in=ids_to_delete).delete()
                    deleted_count += deleted[0]
            
            logger.info(f"{model_class.__name__}: 删除异常记录 {deleted_count} 条")
            return deleted_count
            
        except Exception as e:
            logger.error(f"删除异常记录失败: {e}")
            return 0
    
    def _delete_old_records(self, model_class: Type, delete_count: int, field_name: str) -> int:
        """
        删除最旧的记录
        
        Args:
            model_class: 模型类
            delete_count: 删除数量
            field_name: 排序字段名
            
        Returns:
            int: 删除的记录数
        """
        try:
            # 查找最旧的记录
            old_records = model_class.objects.order_by(field_name)[:delete_count]
            
            if not old_records:
                return 0
            
            # 批量删除
            deleted_count = 0
            batch_size = self.retention_config.get('cleanup_batch_size', 1000)
            
            for i in range(0, len(old_records), batch_size):
                batch = old_records[i:i + batch_size]
                ids_to_delete = [record.id for record in batch]
                
                with transaction.atomic():
                    deleted = model_class.objects.filter(id__in=ids_to_delete).delete()
                    deleted_count += deleted[0]
            
            logger.info(f"{model_class.__name__}: 删除旧记录 {deleted_count} 条")
            return deleted_count
            
        except Exception as e:
            logger.error(f"删除旧记录失败: {e}")
            return 0
    
    def bulk_create_or_update(self, model_class: Type, data_list: List[Dict[str, Any]], 
                             unique_fields: List[str] = None) -> Dict[str, int]:
        """
        批量创建或更新记录
        
        Args:
            model_class: 模型类
            data_list: 数据列表
            unique_fields: 唯一字段列表
            
        Returns:
            Dict: 操作结果统计
        """
        try:
            created_count = 0
            updated_count = 0
            error_count = 0
            
            batch_size = self.retention_config.get('cleanup_batch_size', 1000)
            
            for i in range(0, len(data_list), batch_size):
                batch = data_list[i:i + batch_size]
                
                with transaction.atomic():
                    for data in batch:
                        try:
                            if unique_fields:
                                # 构建查询条件
                                query_dict = {field: data.get(field) for field in unique_fields}
                                
                                # 尝试获取现有记录
                                try:
                                    instance = model_class.objects.get(**query_dict)
                                    # 更新现有记录
                                    for key, value in data.items():
                                        setattr(instance, key, value)
                                    instance.save()
                                    updated_count += 1
                                except ObjectDoesNotExist:
                                    # 创建新记录
                                    model_class.objects.create(**data)
                                    created_count += 1
                            else:
                                # 直接创建新记录
                                model_class.objects.create(**data)
                                created_count += 1
                                
                        except Exception as e:
                            logger.error(f"处理记录失败: {data}, 错误: {e}")
                            error_count += 1
            
            result = {
                'created': created_count,
                'updated': updated_count,
                'errors': error_count,
                'total': len(data_list)
            }
            
            logger.info(f"{model_class.__name__}: 批量操作完成 - {result}")
            return result
            
        except Exception as e:
            logger.error(f"批量操作失败: {e}")
            return {'created': 0, 'updated': 0, 'errors': len(data_list), 'total': len(data_list)}
    
    def get_airport_thresholds(self, airport_4code: str) -> Optional[AirportAlertThresholds]:
        """
        获取机场告警阈值
        
        Args:
            airport_4code: 机场四字代码
            
        Returns:
            AirportAlertThresholds: 机场告警阈值对象
        """
        try:
            # 优先查找具体机场的阈值
            try:
                return AirportAlertThresholds.objects.get(airport_4code=airport_4code)
            except ObjectDoesNotExist:
                # 如果没有找到，使用默认阈值
                try:
                    from copy import deepcopy
                    default_thresholds = AirportAlertThresholds.objects.get(airport_4code='default')
                    
                    # 创建一个新对象，复制所有阈值数据但使用实际机场代码
                    modified_thresholds = deepcopy(default_thresholds)
                    modified_thresholds.airport_4code = airport_4code  # 使用实际机场代码
                    
                    return modified_thresholds
                    
                except ObjectDoesNotExist:
                    logger.warning(f"未找到机场 {airport_4code} 和默认阈值配置")
                    return None
                    
        except Exception as e:
            logger.error(f"获取机场阈值失败: {e}")
            return None
    
    def get_airport_info(self, airport_4code: str) -> Optional[AirportInfo]:
        """
        获取机场信息
        
        Args:
            airport_4code: 机场四字代码
            
        Returns:
            AirportInfo: 机场信息对象
        """
        try:
            return AirportInfo.objects.get(airport_4code=airport_4code)
        except ObjectDoesNotExist:
            logger.warning(f"未找到机场 {airport_4code} 的信息")
            return None
        except Exception as e:
            logger.error(f"获取机场信息失败: {e}")
            return None
    
    def get_weather_alert_level(self, weather_code: str) -> Optional[str]:
        """
        获取天气现象告警等级
        
        Args:
            weather_code: 天气现象代码
            
        Returns:
            str: 告警等级 ('R', 'Y', 'G')
        """
        try:
            alert_record = WeatherAlertLevels.objects.filter(weather=weather_code).first()
            return alert_record.alert_level if alert_record else None
        except Exception as e:
            logger.error(f"获取天气告警等级失败: {e}")
            return None
    
    def is_valid_carrier(self, carrier_code: str) -> bool:
        """
        检查航空公司代码是否有效
        
        Args:
            carrier_code: 航空公司代码
            
        Returns:
            bool: 是否有效
        """
        try:
            return Carrier.objects.filter(carrier_code=carrier_code).exists()
        except Exception as e:
            logger.error(f"检查航空公司代码失败: {e}")
            return False 