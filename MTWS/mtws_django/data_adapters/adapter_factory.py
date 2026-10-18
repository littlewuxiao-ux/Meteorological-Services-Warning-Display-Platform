"""
数据适配器工厂
根据配置创建相应的数据适配器实例
"""

from typing import Dict, Any
import logging
from django.conf import settings

from .base_adapter import BaseDataAdapter
from .api_adapter import APIDataAdapter

logger = logging.getLogger('mtws.data_adapters')


class AdapterFactory:
    """数据适配器工厂"""
    
    # 支持的适配器类型
    ADAPTER_TYPES = {
        'api': APIDataAdapter,
    }
    
    @classmethod
    def create_adapter(cls, adapter_type: str = None, config: Dict[str, Any] = None, time_mode: str = 'current', token: str = None) -> BaseDataAdapter:
        """
        创建数据适配器实例
        
        Args:
            adapter_type: 适配器类型 ('api')
            config: 配置参数
            time_mode: 时间模式 ('current' 或 'test')
            token: current模式下的认证token
            
        Returns:
            BaseDataAdapter: 数据适配器实例
            
        Raises:
            ValueError: 不支持的适配器类型
        """
        # 如果没有指定类型，默认使用API
        if adapter_type is None:
            adapter_type = 'api'
        
        # 如果没有指定配置，从Django配置读取
        if config is None:
            try:
                config = cls._get_config_from_settings(adapter_type)
            except:
                # 如果配置读取失败，使用空配置（API适配器会使用硬编码配置）
                config = {}
        
        # 验证适配器类型
        if adapter_type not in cls.ADAPTER_TYPES:
            raise ValueError(f"不支持的适配器类型: {adapter_type}")
        
        if time_mode == 'test':
            raise ValueError('test 模式只读本地数据库，不创建外部数据适配器')

        adapter_class = cls.ADAPTER_TYPES[adapter_type]
        adapter = adapter_class(config, time_mode, token)
        logger.info(f"创建数据适配器成功: {adapter_type}, 时间模式: {time_mode}")
        return adapter
    
    @classmethod
    def _get_config_from_settings(cls, adapter_type: str) -> Dict[str, Any]:
        """
        从Django配置获取适配器配置
        
        Args:
            adapter_type: 适配器类型
            
        Returns:
            Dict: 配置参数
        """
        data_source_config = settings.MTWS_CONFIG['DATA_SOURCE']
        
        if adapter_type == 'api':
            return data_source_config.get('api_config', {})
        else:
            return {}
    
    @classmethod
    def get_supported_types(cls) -> list:
        """
        获取支持的适配器类型列表
        
        Returns:
            list: 支持的适配器类型
        """
        return list(cls.ADAPTER_TYPES.keys())
    
    @classmethod
    def test_adapter(cls, adapter_type: str = None, config: Dict[str, Any] = None) -> bool:
        """
        测试数据适配器连接
        
        Args:
            adapter_type: 适配器类型
            config: 配置参数
            
        Returns:
            bool: 测试是否成功
        """
        try:
            adapter = cls.create_adapter(adapter_type, config)
            return adapter.test_connection()
        except Exception as e:
            logger.error(f"测试数据适配器失败: {e}")
            return False
    
    @classmethod
    def get_adapter_info(cls, adapter_type: str = None, config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        获取适配器信息
        
        Args:
            adapter_type: 适配器类型
            config: 配置参数
            
        Returns:
            Dict: 适配器信息
        """
        try:
            adapter = cls.create_adapter(adapter_type, config)
            return adapter.get_data_info()
        except Exception as e:
            logger.error(f"获取适配器信息失败: {e}")
            return {'error': str(e)}
    
    @classmethod
    def get_adapter(cls, data_type: str = None) -> BaseDataAdapter:
        """
        根据数据类型获取适配器
        
        Args:
            data_type: 数据类型 ('flight', 'metar', 'taf')
            
        Returns:
            BaseDataAdapter: 数据适配器实例
        """
        # 不管数据类型如何，都使用同一个适配器实例
        return cls.create_adapter()


# 便捷函数
def get_default_adapter() -> BaseDataAdapter:
    """
    获取默认的数据适配器
    
    Returns:
        BaseDataAdapter: 默认数据适配器
    """
    return AdapterFactory.create_adapter()


def switch_data_source(adapter_type: str, config: Dict[str, Any] = None) -> BaseDataAdapter:
    """
    切换数据源
    
    Args:
        adapter_type: 目标适配器类型
        config: 配置参数
        
    Returns:
        BaseDataAdapter: 新的数据适配器
    """
    logger.info(f"切换数据源至: {adapter_type}")
    return AdapterFactory.create_adapter(adapter_type, config) 