"""
数据处理工具类
提供数据格式转换、验证等功能
"""

import pandas as pd
import re
from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timedelta
import logging

logger = logging.getLogger('fmsa.data_utils')


class DataProcessor:
    """数据处理器"""
    
    @staticmethod
    def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
        """
        规范化DataFrame
        
        Args:
            df: 原始DataFrame
            
        Returns:
            DataFrame: 规范化后的DataFrame
        """
        if df.empty:
            return df
        
        # 去除列名的空格
        df.columns = df.columns.str.strip()
        
        # 去除字符串列的前后空格
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str).str.strip()
                # 将空字符串转换为None
                df[col] = df[col].replace('', None)
        
        return df
    
    @staticmethod
    def validate_airport_code(code: str) -> bool:
        """
        验证机场代码格式
        
        Args:
            code: 机场代码
            
        Returns:
            bool: 是否有效
        """
        if not code or not isinstance(code, str):
            return False
        
        # 机场四字代码：4个字母
        if len(code) == 4 and code.isalpha():
            return True
        
        # 机场三字代码：3个字母
        if len(code) == 3 and code.isalpha():
            return True
        
        return False
    
    @staticmethod
    def validate_carrier_code(code: str) -> bool:
        """
        验证航空公司代码格式
        
        Args:
            code: 航空公司代码
            
        Returns:
            bool: 是否有效
        """
        if not code or not isinstance(code, str):
            return False
        
        # 航空公司二字代码：2个字符（字母或数字）
        if len(code) == 2 and code.isalnum():
            return True
        
        return False
    
    @staticmethod
    def extract_carrier_from_flight(flight_number: str) -> Optional[str]:
        """
        从航班号中提取航空公司代码
        
        Args:
            flight_number: 航班号
            
        Returns:
            str: 航空公司代码
        """
        if not flight_number or not isinstance(flight_number, str):
            return None
        
        # 匹配航班号格式：2字母+数字
        match = re.match(r'^([A-Z]{2})', flight_number.upper())
        if match:
            return match.group(1)
        
        return None
    
    @staticmethod
    def parse_weather_phenomena(weather_str: str) -> List[str]:
        """
        解析天气现象字符串
        
        Args:
            weather_str: 天气现象字符串
            
        Returns:
            List[str]: 天气现象列表
        """
        if not weather_str or not isinstance(weather_str, str):
            return []
        
        # 常见天气现象代码
        weather_codes = [
            'RA', 'SN', 'DZ', 'FG', 'BR', 'HZ', 'FU', 'SA', 'DU', 'SQ',
            'FC', 'SS', 'DS', 'SH', 'TS', 'FZRA', 'FZDZ', 'RASN', 'SHRASN',
            'SHRA', 'SHSN', 'TSRA', 'TSSN', 'TSRASN', 'VCSH', 'VCTS',
            'VCFG', 'MIFG', 'PRFG', 'BCFG', 'FZFG', 'BLSN', 'BLSA', 'BLDU'
        ]
        
        found_phenomena = []
        weather_upper = weather_str.upper()
        
        for code in weather_codes:
            if code in weather_upper:
                found_phenomena.append(code)
        
        return found_phenomena
    
    @staticmethod
    def convert_visibility_to_meters(visibility_str: str) -> Optional[float]:
        """
        将能见度字符串转换为米
        
        Args:
            visibility_str: 能见度字符串
            
        Returns:
            float: 能见度（米）
        """
        if not visibility_str or not isinstance(visibility_str, str):
            return None
        
        try:
            # 移除单位
            visibility_str = visibility_str.replace('m', '').replace('M', '').strip()
            
            # 处理分数形式
            if '/' in visibility_str:
                parts = visibility_str.split('/')
                if len(parts) == 2:
                    return float(parts[0]) / float(parts[1]) * 1000  # 转换为米
            
            # 处理数字形式
            visibility = float(visibility_str)
            
            # 如果小于10，可能是公里，转换为米
            if visibility < 10:
                return visibility * 1000
            
            return visibility
            
        except (ValueError, ZeroDivisionError):
            return None
    
    @staticmethod
    def convert_wind_speed_to_mps(wind_speed_str: str, unit: str = 'KT') -> Optional[float]:
        """
        将风速转换为米/秒
        
        Args:
            wind_speed_str: 风速字符串
            unit: 单位（KT=节，MPS=米/秒，KMH=公里/小时）
            
        Returns:
            float: 风速（米/秒）
        """
        if not wind_speed_str or not isinstance(wind_speed_str, str):
            return None
        
        try:
            # 提取数字
            wind_speed = float(re.sub(r'[^\d.]', '', wind_speed_str))
            
            # 转换单位
            if unit.upper() == 'KT':
                return wind_speed * 0.5144  # 节转米/秒
            elif unit.upper() == 'MPS':
                return wind_speed
            elif unit.upper() == 'KMH':
                return wind_speed / 3.6  # 公里/小时转米/秒
            else:
                return wind_speed
                
        except ValueError:
            return None
    
    @staticmethod
    def convert_cloud_height_to_hundred_feet(cloud_str: str) -> Optional[float]:
        """
        将云高转换为百英尺
        
        Args:
            cloud_str: 云高字符串
            
        Returns:
            float: 云高（百英尺）
        """
        if not cloud_str or not isinstance(cloud_str, str):
            return None
        
        try:
            # 提取数字
            cloud_height = float(re.sub(r'[^\d.]', '', cloud_str))
            
            # 如果是三位数字，可能已经是百英尺
            if cloud_height >= 100:
                return cloud_height / 100
            
            return cloud_height
            
        except ValueError:
            return None
    
    @staticmethod
    def parse_datetime_string(datetime_str: str, format_str: str = None) -> Optional[datetime]:
        """
        解析日期时间字符串
        
        Args:
            datetime_str: 日期时间字符串
            format_str: 格式字符串
            
        Returns:
            datetime: 解析后的日期时间
        """
        if not datetime_str or not isinstance(datetime_str, str):
            return None
        
        # 常见格式
        formats = [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M',
            '%Y-%m-%d',
            '%Y%m%d%H%M%S',
            '%Y%m%d%H%M',
            '%Y%m%d',
            '%d/%m/%Y %H:%M:%S',
            '%d/%m/%Y %H:%M',
            '%d/%m/%Y',
        ]
        
        if format_str:
            formats.insert(0, format_str)
        
        for fmt in formats:
            try:
                return datetime.strptime(datetime_str, fmt)
            except ValueError:
                continue
        
        logger.warning(f"无法解析日期时间: {datetime_str}")
        return None
    
    @staticmethod
    def filter_valid_flights(flights_data: List[Dict[str, Any]], 
                           valid_carriers: List[str]) -> List[Dict[str, Any]]:
        """
        过滤有效航班数据
        
        Args:
            flights_data: 航班数据列表
            valid_carriers: 有效航空公司列表
            
        Returns:
            List[Dict]: 过滤后的航班数据
        """
        if not flights_data or not valid_carriers:
            return []
        
        valid_flights = []
        
        for flight in flights_data:
            flight_number = flight.get('flight_number', '')
            carrier = DataProcessor.extract_carrier_from_flight(flight_number)
            
            if carrier and carrier in valid_carriers:
                valid_flights.append(flight)
        
        return valid_flights
    
    @staticmethod
    def validate_numeric_range(value: Any, min_val: float = None, 
                              max_val: float = None) -> bool:
        """
        验证数值范围
        
        Args:
            value: 要验证的值
            min_val: 最小值
            max_val: 最大值
            
        Returns:
            bool: 是否在范围内
        """
        try:
            num_value = float(value)
            
            if min_val is not None and num_value < min_val:
                return False
            
            if max_val is not None and num_value > max_val:
                return False
            
            return True
            
        except (ValueError, TypeError):
            return False 