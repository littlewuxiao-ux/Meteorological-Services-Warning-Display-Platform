"""
数据源适配器包
提供统一的数据源接口，支持API数据源
"""

from .base_adapter import BaseDataAdapter
from .api_adapter import APIDataAdapter
from .adapter_factory import AdapterFactory

__all__ = [
    'BaseDataAdapter',
    'APIDataAdapter',
    'AdapterFactory',
] 