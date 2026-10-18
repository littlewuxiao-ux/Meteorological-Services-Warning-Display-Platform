"""
数据源适配器基类
定义统一的数据源接口
"""

from abc import ABC, abstractmethod
import pandas as pd
from typing import Optional, Dict, Any, List


class BaseDataAdapter(ABC):
    """数据源适配器基类"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化数据适配器
        
        Args:
            config: 配置参数
        """
        self.config = config
        self._connection = None
    
    @abstractmethod
    def get_flight_data(self) -> pd.DataFrame:
        """
        获取航班数据
        
        Returns:
            DataFrame: 航班数据
        """
        pass
    
    @abstractmethod
    def get_metar_data(self, airport_codes: List[str] = None) -> pd.DataFrame:
        """
        获取METAR数据
        
        Args:
            airport_codes: 机场四字代码列表（可选，某些适配器可能需要）
        
        Returns:
            DataFrame: METAR数据
        """
        pass
    
    @abstractmethod
    def get_taf_data(self, airport_codes: List[str] = None) -> pd.DataFrame:
        """
        获取TAF数据
        
        Args:
            airport_codes: 机场四字代码列表（可选，某些适配器可能需要）
        
        Returns:
            DataFrame: TAF数据
        """
        pass
    
    @abstractmethod
    def test_connection(self) -> bool:
        """
        测试数据源连接
        
        Returns:
            bool: 连接是否成功
        """
        pass
    
    def connect(self) -> None:
        """建立数据源连接"""
        pass
    
    def disconnect(self) -> None:
        """断开数据源连接"""
        pass
    
    def get_data_info(self) -> Dict[str, Any]:
        """
        获取数据源信息
        
        Returns:
            Dict: 数据源信息
        """
        return {
            'type': self.__class__.__name__,
            'config': self.config,
            'connected': self._connection is not None,
        }
    
    def __enter__(self):
        """上下文管理器入口"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.disconnect() 