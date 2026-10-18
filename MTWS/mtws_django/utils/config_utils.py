"""
配置管理工具类
提供系统配置的读取和管理功能
"""

from django.conf import settings
from typing import Dict, Any, Optional
import json
import logging

from core.models import SystemConfig

logger = logging.getLogger('mtws.config')


class ConfigManager:
    """配置管理器"""
    
    def __init__(self):
        self.cache_timeout = settings.MTWS_CONFIG['CACHE_TIMEOUT']['config_data']
    
    def get_config(self, config_type: str, config_key: str, default_value: Any = None) -> Any:
        """
        获取配置值
        
        Args:
            config_type: 配置类型
            config_key: 配置键
            default_value: 默认值
            
        Returns:
            Any: 配置值
        """
        try:
            # 从数据库获取
            config_record = SystemConfig.objects.get(
                config_type=config_type,
                config_key=config_key
            )
            
            # 尝试解析JSON
            try:
                return json.loads(config_record.config_value)
            except (json.JSONDecodeError, TypeError):
                return config_record.config_value
            
        except SystemConfig.DoesNotExist:
            logger.warning(f"配置不存在: {config_type}.{config_key}")
            return default_value
        except Exception as e:
            logger.error(f"获取配置失败: {e}")
            return default_value
    
    def set_config(self, config_type: str, config_key: str, config_value: Any,
                  description: str = None) -> bool:
        """
        设置配置值
        
        Args:
            config_type: 配置类型
            config_key: 配置键
            config_value: 配置值
            description: 描述
            
        Returns:
            bool: 是否成功
        """
        try:
            # 序列化值
            if isinstance(config_value, (dict, list)):
                value_str = json.dumps(config_value, ensure_ascii=False)
            else:
                value_str = str(config_value)
            
            # 创建或更新配置
            config_record, created = SystemConfig.objects.update_or_create(
                config_type=config_type,
                config_key=config_key,
                defaults={
                    'config_value': value_str,
                    'description': description
                }
            )
            
            # 清除缓存
            cache_key = f"config_{config_type}_{config_key}"
            cache.delete(cache_key)
            
            logger.info(f"配置保存成功: {config_type}.{config_key}")
            return True
            
        except Exception as e:
            logger.error(f"设置配置失败: {e}")
            return False
    
    def get_data_retention_config(self) -> Dict[str, int]:
        """
        获取数据保留配置
        
        Returns:
            Dict: 数据保留配置
        """
        return {
            'metar_max_records': self.get_config('data_retention', 'metar_max_records', 5000),
            'taf_max_records': self.get_config('data_retention', 'taf_max_records', 5000),
            'flight_max_records': self.get_config('data_retention', 'flight_max_records', 10000),
            'cleanup_batch_size': self.get_config('data_retention', 'cleanup_batch_size', 1000),
        }
    
    def get_auto_refresh_config(self) -> Dict[str, int]:
        """
        获取自动刷新配置
        
        Returns:
            Dict: 自动刷新配置
        """
        return {
            'enable_auto_refresh': self.get_config('auto_refresh', 'enable_auto_refresh', True),
            'refresh_interval': self.get_config('auto_refresh', 'refresh_interval', 30),
            'flight_interval': self.get_config('auto_refresh', 'flight_interval', 60),
            'metar_interval': self.get_config('auto_refresh', 'metar_interval', 30),
            'taf_interval': self.get_config('auto_refresh', 'taf_interval', 60),
        }
    
    def get_data_source_config(self) -> Dict[str, Any]:
        """
        获取数据源配置
        
        Returns:
            Dict: 数据源配置
        """
        return {
            'type': self.get_config('data_source', 'type', 'api'),
            'api_endpoints': self.get_config('data_source', 'api_endpoints', {}),
            'api_auth_token': self.get_config('data_source', 'api_auth_token', ''),
            'api_timeout': self.get_config('data_source', 'api_timeout', 30),
        }
    
    def update_data_retention_config(self, config: Dict[str, int]) -> bool:
        """
        更新数据保留配置
        
        Args:
            config: 配置字典
            
        Returns:
            bool: 是否成功
        """
        try:
            for key, value in config.items():
                self.set_config('data_retention', key, value)
            logger.info("数据保留配置更新成功")
            return True
        except Exception as e:
            logger.error(f"更新数据保留配置失败: {e}")
            return False
    
    def update_auto_refresh_config(self, config: Dict[str, Any]) -> bool:
        """
        更新自动刷新配置
        
        Args:
            config: 配置字典
            
        Returns:
            bool: 是否成功
        """
        try:
            for key, value in config.items():
                self.set_config('auto_refresh', key, value)
            logger.info("自动刷新配置更新成功")
            return True
        except Exception as e:
            logger.error(f"更新自动刷新配置失败: {e}")
            return False
    
    def update_data_source_config(self, config: Dict[str, Any]) -> bool:
        """
        更新数据源配置
        
        Args:
            config: 配置字典
            
        Returns:
            bool: 是否成功
        """
        try:
            for key, value in config.items():
                self.set_config('data_source', key, value)
            logger.info("数据源配置更新成功")
            return True
        except Exception as e:
            logger.error(f"更新数据源配置失败: {e}")
            return False
    
    def clear_config_cache(self) -> None:
        """清除配置缓存"""
        try:
            # 清除所有配置相关的缓存
            cache.delete_many([
                key for key in cache._cache.keys() 
                if key.startswith('config_')
            ])
            logger.info("配置缓存清除成功")
        except Exception as e:
            logger.error(f"清除配置缓存失败: {e}")
    
    def get_all_configs(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有配置
        
        Returns:
            Dict: 所有配置
        """
        try:
            configs = {}
            
            # 按类型分组获取配置
            for config_type in ['data_retention', 'auto_refresh', 'data_source']:
                configs[config_type] = {}
                
                config_records = SystemConfig.objects.filter(config_type=config_type)
                
                for record in config_records:
                    try:
                        value = json.loads(record.config_value)
                    except (json.JSONDecodeError, TypeError):
                        value = record.config_value
                    
                    configs[config_type][record.config_key] = {
                        'value': value,
                        'description': record.description,
                        'updated_at': record.updated_at
                    }
            
            return configs
            
        except Exception as e:
            logger.error(f"获取所有配置失败: {e}")
            return {} 