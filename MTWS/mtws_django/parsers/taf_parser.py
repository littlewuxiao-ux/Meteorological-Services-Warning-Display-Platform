#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TAF报文解析程序
完整移植自原始的mtws_03_taf解析.py，适配Django项目
"""

from avwx_custom.current.taf import parse as parse_taf_report
#  直接解析报文原文，不构造 Taf(机场代码)，因此不读取 stations.json
import math
import re
import logging
import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

from django.conf import settings
from parsers.models import Taf, ParseLog
from core.models import AirportAlertThresholds, AirportTafImportConfig, WeatherAlertLevels
from parsers.cloud_amount import (
    cloud_amount_qualifies,
    cloud_object_amount,
    format_cloud_min,
    lowest_height_in_text,
    normalize_cloud_amt,
)
from data_adapters.adapter_factory import AdapterFactory

logger = logging.getLogger('mtws.parsers')


class _ParsedTaf:
    """只保留入库所需的解析结果，避免构造 avwx 的 Taf 对象。"""

    def __init__(self, data):
        self.data = data

def calc_taf_expected_issue_ms(now_ms, taf_init_time, taf_max_delay, import_check_interval, leeway_minutes):
    """
    按入库告警同一公式计算预报应发时间（UTC 毫秒）。
    起点为参考时刻当天 UTC 0 点 + 首份发布整点，步长为发布间隔。
    未到第一个检查窗口，或步长无效时返回 None。
    """
    try:
        now_ms = int(now_ms)
        taf_init_time = int(taf_init_time or 0)
        taf_max_delay = int(taf_max_delay or 0)
        import_check_interval = int(import_check_interval or 1)
        leeway_minutes = int(30 if leeway_minutes is None else leeway_minutes)
    except (TypeError, ValueError):
        return None

    now_dt = datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc)
    ms_0 = int(now_dt.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
    delay_ms = leeway_minutes * 60_000 + taf_max_delay * 60_000
    origin = ms_0 + taf_init_time * 3_600_000
    step = import_check_interval * 3_600_000
    if step <= 0:
        return None
    n_val = math.floor((now_ms - origin - delay_ms) / step)
    if n_val < 0:
        return None
    return origin + step * n_val

# 告警级别常量定义
ALERT_RED = 'R'         # 红色告警
ALERT_YELLOW = 'Y'      # 黄色告警
ALERT_GREEN = 'G'       # 绿色告警
ALERT_NONE = 'N'        # 无告警

def get_weather_alert_level(weather_phenomenon: str) -> str:
    """根据天气现象获取告警级别 - 从WeatherAlertLevels表读取"""
    if not weather_phenomenon or weather_phenomenon.upper() in ['NSW', '']:
        return ALERT_NONE
    
    weather = weather_phenomenon.upper().strip()
    
    try:
        alert_level = WeatherAlertLevels.objects.filter(
            weather=weather
        ).first()
        return alert_level.alert_level if alert_level else ALERT_NONE
    except Exception as e:
        logger.error(f"获取天气现象告警级别失败: {e}")
        return ALERT_NONE


def get_visibility_alert_level(visibility_m: int, airport_info: dict) -> str:
    """根据能见度获取告警级别"""
    red_threshold = airport_info.get('visibility_m_red')
    yellow_threshold = airport_info.get('visibility_m_yellow')
    green_threshold = airport_info.get('visibility_m_green')
    
    # 如果没有配置阈值，返回无告警
    if red_threshold is None or yellow_threshold is None or green_threshold is None:
        return ALERT_NONE
    
    if visibility_m <= red_threshold:
        return ALERT_RED
    elif visibility_m <= yellow_threshold:
        return ALERT_YELLOW
    elif visibility_m <= green_threshold:
        return ALERT_GREEN
    else:
        return ALERT_NONE


def get_cloud_alert_level(cloud_min: int, airport_info: dict) -> str:
    """根据最低云高获取告警级别"""
    red_threshold = airport_info.get('cloud_min_red')
    yellow_threshold = airport_info.get('cloud_min_yellow')
    green_threshold = airport_info.get('cloud_min_green')
    
    # 如果没有配置阈值，返回无告警
    if red_threshold is None or yellow_threshold is None or green_threshold is None:
        return ALERT_NONE
    
    if cloud_min <= red_threshold:
        return ALERT_RED
    elif cloud_min <= yellow_threshold:
        return ALERT_YELLOW
    elif cloud_min <= green_threshold:
        return ALERT_GREEN
    else:
        return ALERT_NONE


def get_wind_alert_level(wind_speed_mps: float, airport_info: dict) -> str:
    """根据平均风速获取告警级别"""
    red_threshold = airport_info.get('average_wind_speed_mps_red')
    yellow_threshold = airport_info.get('average_wind_speed_mps_yellow')
    green_threshold = airport_info.get('average_wind_speed_mps_green')
    
    # 如果没有配置阈值，返回无告警
    if red_threshold is None or yellow_threshold is None or green_threshold is None:
        return ALERT_NONE
    
    if wind_speed_mps >= red_threshold:
        return ALERT_RED
    elif wind_speed_mps >= yellow_threshold:
        return ALERT_YELLOW
    elif wind_speed_mps >= green_threshold:
        return ALERT_GREEN
    else:
        return ALERT_NONE


def get_gust_alert_level(gust_mps: float, airport_info: dict) -> str:
    """根据阵风风速获取告警级别"""
    red_threshold = airport_info.get('gust_mps_red')
    yellow_threshold = airport_info.get('gust_mps_yellow')
    green_threshold = airport_info.get('gust_mps_green')
    
    # 如果没有配置阈值，返回无告警
    if red_threshold is None or yellow_threshold is None or green_threshold is None:
        return ALERT_NONE
    
    if gust_mps >= red_threshold:
        return ALERT_RED
    elif gust_mps >= yellow_threshold:
        return ALERT_YELLOW
    elif gust_mps >= green_threshold:
        return ALERT_GREEN
    else:
        return ALERT_NONE


def get_temperature_alert_level(temperature: float, airport_info: dict) -> str:
    """根据气温获取告警级别"""
    cold_red = airport_info.get('temperature_cold_red')
    cold_yellow = airport_info.get('temperature_cold_yellow')
    cold_green = airport_info.get('temperature_cold_green')
    hot_red = airport_info.get('temperature_hot_red')
    hot_yellow = airport_info.get('temperature_hot_yellow')
    hot_green = airport_info.get('temperature_hot_green')
    
    # 如果没有配置阈值，返回无告警
    if (cold_red is None or cold_yellow is None or cold_green is None or
        hot_red is None or hot_yellow is None or hot_green is None):
        return ALERT_NONE
    
    # 检查低温告警
    if temperature <= cold_red:
        return ALERT_RED
    elif temperature <= cold_yellow:
        return ALERT_YELLOW
    elif temperature <= cold_green:
        return ALERT_GREEN
    # 检查高温告警
    elif temperature >= hot_red:
        return ALERT_RED
    elif temperature >= hot_yellow:
        return ALERT_YELLOW
    elif temperature >= hot_green:
        return ALERT_GREEN
    else:
        return ALERT_NONE


class TafParser:
    """TAF解析器 - 完整移植自原始版本"""
    
    def __init__(self, time_mode='current', token=None):
        """初始化解析器"""
        self.time_mode = time_mode
        self.token = token
        self.taf_obj = None
        self.change_groups = {}
        
        # 初始化变量
        self.reset_variables()
    
    def reset_variables(self):
        """重置所有变量"""
        # 基础信息
        self.airport_4code = ""
        self.observation_time = None
        self.content = ""
        self.whole_validity_period = ""
        self.subject_validity_period_start = ""
        self.subject_validity_period_end = ""
        self.abnormal_label = ""
        self.error_report = ""
        self.amd_or_cor = "N"
        
        # 主预报字段
        self.subject_content = ""
        self.subject_wind = ""
        self.subject_wind_direction = ""
        self.subject_wind_speed = ""
        self.subject_wind_speed_mps = ""
        self.subject_gust = ""
        self.subject_gust_mps = ""
        self.subject_visibility = ""
        self.subject_visibility_m = ""
        self.subject_weather = ""
        self.subject_weather1 = ""
        self.subject_weather2 = ""
        self.subject_weather3 = ""
        self.subject_weather4 = ""
        self.subject_weather5 = ""
        self.subject_cloud = ""
        self.subject_cloud_min = ""
        
        # 主预报温度字段
        self.subject_max_temp1 = ""
        self.subject_max_temp1_time = ""
        self.subject_max_temp2 = ""
        self.subject_max_temp2_time = ""
        self.subject_min_temp1 = ""
        self.subject_min_temp1_time = ""
        self.subject_min_temp2 = ""
        self.subject_min_temp2_time = ""
        
        # 告警字段
        self.subject_warning = ""
        self.subject_max_temp1_warning = ""
        self.subject_max_temp2_warning = ""
        self.subject_min_temp1_warning = ""
        self.subject_min_temp2_warning = ""
        
        # 变化组字段
        self.change_groups = {}
        self._subject_line = None
        self._own_elements = {}
    
    def kt_to_mps(self, speed_kt: float) -> float:
        """节转米/秒"""
        return speed_kt * 0.514444
    
    def extract_wind_info(self, forecast_line_data) -> Dict[str, str]:
        """提取风信息 - 适配AVWX的TafLineData结构"""
        if not forecast_line_data:
            return {
                'wind': '', 'direction': '', 'speed': '', 'speed_mps': '', 'gust': '', 'gust_mps': ''
            }
        
        # 处理风向，确保数字风向保持3位格式
        direction_value = ''
        if hasattr(forecast_line_data, 'wind_direction') and forecast_line_data.wind_direction:
            if forecast_line_data.wind_direction.value is not None:
                if str(forecast_line_data.wind_direction.value).isdigit():
                    direction_value = str(forecast_line_data.wind_direction.value).zfill(3)
                else:
                    direction_value = str(forecast_line_data.wind_direction.value)
            else:
                direction_value = 'VRB'
        else:
            direction_value = 'VRB'
        
        wind_info = {
            'wind': '',
            'direction': direction_value,
            'speed': str(forecast_line_data.wind_speed.value) if forecast_line_data.wind_speed and forecast_line_data.wind_speed.value is not None else '',
            'speed_mps': '',
            'gust': str(forecast_line_data.wind_gust.value) if forecast_line_data.wind_gust and forecast_line_data.wind_gust.value is not None else '',
            'gust_mps': ''
        }
        
        # 构建风组字符串
        if wind_info['direction'] and wind_info['speed']:
            wind_str = f"{wind_info['direction']}{wind_info['speed'].zfill(2)}"
            if wind_info['gust']:
                wind_str += f"G{wind_info['gust']}"
            # 检查单位
            if hasattr(forecast_line_data.wind_speed, 'units') and forecast_line_data.wind_speed.units == 'kt':
                wind_str += "KT"
                # 转换为MPS
                wind_info['speed_mps'] = str(self.kt_to_mps(float(wind_info['speed'])))
                if wind_info['gust']:
                    wind_info['gust_mps'] = str(self.kt_to_mps(float(wind_info['gust'])))
            else:
                wind_str += "MPS"
                wind_info['speed_mps'] = wind_info['speed']
                wind_info['gust_mps'] = wind_info['gust']
            
            wind_info['wind'] = wind_str
        
        return wind_info
    
    def extract_visibility_info(self, visibility_data) -> Dict[str, str]:
        """提取能见度信息 - 完全按照原始程序逻辑"""
        if not visibility_data:
            return {'visibility': '', 'visibility_m': ''}
        
        vis_str = str(visibility_data.repr) if hasattr(visibility_data, 'repr') else str(visibility_data)
        vis_value = visibility_data.value if hasattr(visibility_data, 'value') else None
        
        # 检查单位信息 - 从原始报文推断单位
        units_info = ''
        if hasattr(visibility_data, 'units') and visibility_data.units and visibility_data.units != 'N/A':
            if visibility_data.units == 'sm':
                units_info = 'SM'
            elif visibility_data.units == 'm':
                units_info = 'm'
        else:
            # 单位信息缺失，从vis_str和机场代码推断
            # 根据机场代码判断地区和单位制
            station_code = ''
            if hasattr(self, 'taf_obj') and self.taf_obj and hasattr(self.taf_obj, 'data') and self.taf_obj.data:
                station_code = self.taf_obj.data.station or ''
            else:
                station_code = getattr(self, 'airport_4code', '')
            
            # 使用更准确的单位制判断方法
            uses_na_format = False
            try:
                # 尝试使用AVWX的准确判断
                from avwx.station import uses_na_format as avwx_uses_na_format
                uses_na_format = avwx_uses_na_format(station_code)
            except ImportError:
                # 如果AVWX不可用，使用改进的判断
                # 北美地区机场代码：K(美国本土), P(美国太平洋), C(加拿大), T(部分加勒比海)
                na_prefixes = ['K', 'P', 'C']
                uses_na_format = any(station_code.startswith(prefix) for prefix in na_prefixes)
            
            if vis_str in ['P6', 'CAVOK']:
                units_info = 'SM'  # 这些特殊值通常是英里制
            elif '/' in vis_str:  # 分数形式一般是英里
                units_info = 'SM'
            elif vis_str.isdigit():
                vis_num = int(vis_str)
                if uses_na_format or vis_num <= 6:
                    # 北美机场或小数值，很可能是英里
                    units_info = 'SM'
                elif not uses_na_format or vis_num >= 100:
                    # 非北美机场或大数值，很可能是米
                    units_info = 'm'
                else:
                    # 默认根据数值大小判断
                    units_info = 'm' if vis_num > 10 else 'SM'
            else:
                # 其他情况，根据机场地区默认
                units_info = 'SM' if uses_na_format else 'm'
        
        # 构建带单位的能见度字符串
        if vis_str in ['CAVOK']:
            vis_with_units = 'CAVOK'
            vis_m = "9999"
        elif vis_str == 'P6' or vis_str == 'P6SM':
            vis_with_units = 'P6SM'
            vis_m = "9999"
        else:
            # 根据单位类型决定是否显示单位
            if units_info == 'm':
                # 米制单位：省略单位，直接显示数值
                vis_with_units = vis_str
            elif units_info == 'SM':
                # 英里单位：保留单位
                # 处理分数形式的显示 - 将5/4转换回1 1/4格式
                if '/' in vis_str:
                    try:
                        numerator, denominator = vis_str.split('/')
                        num_val = float(numerator)
                        den_val = float(denominator)
                        decimal_val = num_val / den_val
                        
                        # 如果大于1，转换为带分数形式
                        if decimal_val > 1:
                            whole_part = int(decimal_val)
                            remainder = decimal_val - whole_part
                            if remainder > 0:
                                # 寻找最简分数表示
                                for denom in [2, 4, 8, 16]:
                                    frac_num = remainder * denom
                                    if abs(frac_num - round(frac_num)) < 0.01:
                                        vis_with_units = f"{whole_part} {int(round(frac_num))}/{denom}SM"
                                        break
                                else:
                                    vis_with_units = f"{vis_str}SM"
                            else:
                                vis_with_units = f"{whole_part}SM"
                        else:
                            vis_with_units = f"{vis_str}SM"
                    except:
                        vis_with_units = f"{vis_str}SM"
                else:
                    # 对于其他情况，添加SM单位
                    if not vis_str.endswith('SM'):
                        vis_with_units = f"{vis_str}SM"
                    else:
                        vis_with_units = vis_str
            else:
                # 未知单位情况，保持原样
                vis_with_units = vis_str
            
            # 计算米制能见度
            if vis_value is not None:
                if units_info == 'SM':
                    # 英里转米 (1英里 = 1600米)
                    vis_m = str(int(vis_value * 1600))
                else:
                    vis_m = str(int(vis_value))
            else:
                # 如果AVWX没有正确解析值，尝试手动解析
                vis_m = str(self._convert_visibility_to_meters(vis_with_units))
        
        return {'visibility': vis_with_units, 'visibility_m': vis_m}
    
    def _convert_visibility_to_meters(self, vis_value: str) -> int:
        """将能见度转换为米"""
        if not vis_value:
            return 0
        
        try:
            # 处理CAVOK
            if vis_value.upper() == 'CAVOK':
                return 10000
            
            # 处理数字能见度
            if vis_value.isdigit():
                return int(vis_value)
            
            # 处理分数能见度
            if '/' in vis_value:
                parts = vis_value.split('/')
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    return int((float(parts[0]) / float(parts[1])) * 1609)  # 英里转米
            
            return 0
        except:
            return 0
    
    def extract_weather_info(self, wx_codes) -> Dict[str, str]:
        """提取天气现象信息 - 完全按照原始程序逻辑"""
        weather_info = {
            'weather': '',
            'weather1': '', 'weather2': '', 'weather3': '', 'weather4': '', 'weather5': ''
        }
        
        if not wx_codes:
            return weather_info
        
        # 提取天气现象 - 使用repr获取原始TAF代码
        weather_list = []
        for wx in wx_codes:
            if hasattr(wx, 'repr'):
                weather_repr = wx.repr
                weather_list.append(weather_repr)
            else:
                weather_list.append(str(wx))
        
        if weather_list:
            weather_info['weather'] = ' '.join(weather_list[:5])
            # 分配到individual weather slots
            for i, weather in enumerate(weather_list[:5], 1):
                weather_info[f'weather{i}'] = weather
        
        return weather_info
    
    def extract_cloud_info(self, clouds, visibility_str="") -> Dict[str, str]:
        """提取云组信息 - 完全按照原始程序逻辑"""
        cloud_info = {'cloud': '', 'cloud_min': ''}
        
        # CAVOK时云组为空
        if visibility_str == 'CAVOK':
            return cloud_info
        
        if not clouds:
            return cloud_info
        
        cloud_parts = []
        min_height = None
        min_cloud_amt = self._min_cloud_amt()
        
        for cloud in clouds:
            if hasattr(cloud, 'type') and hasattr(cloud, 'base'):
                cloud_type = cloud.type
                # 云高用base属性，单位是百英尺
                altitude = cloud.base if cloud.base is not None else 0
                altitude_str = f"{altitude:03d}"
                
                # 构建完整的云组字符串，包含CB/TCU标识
                cloud_str = f"{cloud_type}{altitude_str}"
                
                # 检查是否有云类型修饰符（CB/TCU等）
                if hasattr(cloud, 'modifier') and cloud.modifier:
                    cloud_str += cloud.modifier
                elif hasattr(cloud, 'repr') and cloud.repr:
                    # 如果有完整的repr，尝试从中提取CB/TCU
                    repr_str = cloud.repr
                    if 'CB' in repr_str:
                        cloud_str += 'CB'
                    elif 'TCU' in repr_str:
                        cloud_str += 'TCU'
                
                cloud_parts.append(cloud_str)
                
                # 只在达到云量下限的云组中找最低云底高
                if cloud_amount_qualifies(cloud_object_amount(cloud), min_cloud_amt):
                    if min_height is None or altitude < min_height:
                        min_height = altitude
        
        if cloud_parts:
            cloud_info['cloud'] = ' '.join(cloud_parts)
            if min_height is not None:
                cloud_info['cloud_min'] = f"{min_height:03d}"
        
        return cloud_info
    
    def parse_taf(self, taf_text: str, station_code: Optional[str] = None):
        """解析TAF报文"""
        self.reset_variables()
        
        try:
            # 存储原始报文
            self.content = taf_text.strip()
            
            # 直接解析原文。单位按四字码前缀判断，不查 stations.json。
            if not station_code:
                words = taf_text.split()
                for word in words:
                    if len(word) == 4 and word.isalpha() and word.upper() not in ['TAF', 'AMD', 'COR']:
                        station_code = word.upper()
                        break

            self.taf_obj = None
            parsed = False
            if station_code:
                data, _units, _sanitization = parse_taf_report(station_code, self.content)
                if data is not None:
                    self.taf_obj = _ParsedTaf(data)
                    parsed = True
            
            if not parsed or not self.taf_obj or not self.taf_obj.data:
                self.abnormal_label = 'FAIL'
                return False
            
            data = self.taf_obj.data
            
            # 解析修订报/更正报标识
            if data.is_amended:
                self.amd_or_cor = 'AMD'
            elif data.is_correction:
                self.amd_or_cor = 'COR'
            else:
                self.amd_or_cor = 'N'
            
            # 检查是否为取消报
            if data.remarks == "CNL" and not data.forecast:
                self.abnormal_label = 'AMD_CNL' if data.is_amended else 'CNL'
                self.airport_4code = data.station
                self.observation_time = None
                return True  # CNL报文解析成功
            
            # 基础信息
            self.airport_4code = data.station
            self.observation_time = None
            
            # 整体有效期
            if data.start_time and data.end_time:
                start_str = data.start_time.dt.strftime('%d%H') if data.start_time.dt else ''
                end_str = data.end_time.dt.strftime('%d%H') if data.end_time.dt else ''
                self.whole_validity_period = f"{start_str}/{end_str}"
                self.subject_validity_period_start = start_str
                
                # 主预报结束时间：取最早的FROM或BECMG变化开始时间
                earliest_change_time = self.get_earliest_change_time()
                if earliest_change_time:
                    self.subject_validity_period_end = earliest_change_time
                else:
                    self.subject_validity_period_end = end_str
            
            # 解析主预报
            if data.forecast:
                main_forecast = data.forecast[0]
                self._subject_line = main_forecast
                self.parse_forecast_line(main_forecast, is_subject=True)
            
            # 解析变化组
            for i, forecast_line in enumerate(data.forecast[1:], 1):
                self.parse_forecast_line(forecast_line, change_index=i)
            
            # 处理温度信息
            self.parse_temperature_info(data)

            self._snapshot_own_elements()
            
            # 处理BECMG继承逻辑（同时处理CAVOK逻辑）
            self.process_becmg_inheritance()
            
            # 生成BECMG变化组的完整content_all
            self.generate_becmg_content_all()
            
            # 计算告警级别
            self.calculate_alert_levels()
            
            return True
            
        except Exception as e:
            self.abnormal_label = 'FAIL'
            self.error_report = f"TAF解析异常: {str(e)}"
            logger.error(f"TAF解析异常: {e}")
            return False
    
    def parse_forecast_line(self, forecast_line, is_subject=False, change_index=None):
        """解析预报行 - 完全移植原始程序逻辑"""
        # 提取风信息 - 直接内联处理，不使用extract_wind_info
        wind_info = {}
        if hasattr(forecast_line, 'wind_speed') and forecast_line.wind_speed:
            # 处理风向，确保数字风向保持3位格式
            direction_value = ''
            if forecast_line.wind_direction and forecast_line.wind_direction.value:
                if str(forecast_line.wind_direction.value).isdigit():
                    direction_value = str(forecast_line.wind_direction.value).zfill(3)
                else:
                    direction_value = str(forecast_line.wind_direction.value)
            else:
                direction_value = 'VRB'
            
            # 重新构建风信息
            wind_info = {
                'direction': direction_value,
                'speed': str(forecast_line.wind_speed.value) if forecast_line.wind_speed and forecast_line.wind_speed.value else '',
                'gust': str(forecast_line.wind_gust.value) if forecast_line.wind_gust and forecast_line.wind_gust.value else '',
            }
            
            # 构建风组字符串和转换单位
            if wind_info['direction'] and wind_info['speed']:
                wind_str = f"{wind_info['direction']}{wind_info['speed'].zfill(2)}"
                if wind_info['gust']:
                    wind_str += f"G{wind_info['gust']}"
                
                # 判断原始报文中的风速单位
                # 通过检查原始报文来确定真实单位
                original_units = 'kt'  # 默认为kt
                if hasattr(forecast_line, 'raw') and forecast_line.raw:
                    if 'MPS' in forecast_line.raw.upper():
                        original_units = 'mps'
                    elif 'KT' in forecast_line.raw.upper() or 'KMH' in forecast_line.raw.upper():
                        original_units = 'kt'
                elif hasattr(forecast_line.wind_speed, 'units'):
                    # AVWX解析的单位
                    original_units = forecast_line.wind_speed.units.lower()
                
                # 根据真实单位构建风组和转换
                if original_units in ['mps', 'm/s']:
                    wind_str += "MPS"
                    wind_info['speed_mps'] = wind_info['speed']
                    wind_info['gust_mps'] = wind_info['gust']
                else:
                    wind_str += "KT"
                    wind_info['speed_mps'] = str(self.kt_to_mps(float(wind_info['speed']))) if wind_info['speed'] else ''
                    wind_info['gust_mps'] = str(self.kt_to_mps(float(wind_info['gust']))) if wind_info['gust'] else ''
                
                wind_info['wind'] = wind_str
            else:
                wind_info.update({'wind': '', 'speed_mps': '', 'gust_mps': ''})
        
        # 提取能见度信息
        visibility_info = self.extract_visibility_info(forecast_line.visibility)
        
        # 提取天气现象信息
        weather_info = self.extract_weather_info(forecast_line.wx_codes)
        
        
        # 检查other字段中是否有NSW（No Significant Weather）
        if hasattr(forecast_line, 'other') and forecast_line.other:
            for item in forecast_line.other:
                if str(item).upper() == 'NSW':
                    weather_info['weather'] = 'NSW'
                    weather_info['weather1'] = 'NSW'
                    # 清空其他天气现象
                    for i in range(2, 6):
                        weather_info[f'weather{i}'] = ''
                    break
        
        # 提取云组信息
        cloud_info = self.extract_cloud_info(forecast_line.clouds, visibility_info['visibility'])
        
        # 检查other字段中是否有NSC（No Significant Cloud）或SKC（Sky Clear）
        if hasattr(forecast_line, 'other') and forecast_line.other:
            for item in forecast_line.other:
                item_upper = str(item).upper()
                if item_upper in ['NSC', 'SKC']:
                    # NSC/SKC表示无重要云组，清空云组信息
                    cloud_info['cloud'] = ''
                    cloud_info['cloud_min'] = ''
                    break
        
        if is_subject:
            # 主预报
            self.subject_wind = wind_info.get('wind', '')
            self.subject_wind_direction = wind_info.get('direction', '')
            self.subject_wind_speed = wind_info.get('speed', '')
            self.subject_wind_speed_mps = wind_info.get('speed_mps', '')
            self.subject_gust = wind_info.get('gust', '')
            self.subject_gust_mps = wind_info.get('gust_mps', '')
            self.subject_visibility = visibility_info['visibility']
            self.subject_visibility_m = visibility_info['visibility_m']
            self.subject_weather = weather_info['weather']
            self.subject_weather1 = weather_info['weather1']
            self.subject_weather2 = weather_info['weather2']
            self.subject_weather3 = weather_info['weather3']
            self.subject_weather4 = weather_info['weather4']
            self.subject_weather5 = weather_info['weather5']
            self.subject_cloud = cloud_info['cloud']
            self.subject_cloud_min = cloud_info['cloud_min']
            
            # 构建主预报内容
            content_parts = []
            if self.subject_wind:
                content_parts.append(self.subject_wind)
            if self.subject_visibility:
                content_parts.append(self.subject_visibility)
            if self.subject_weather:
                content_parts.append(self.subject_weather)
            if self.subject_cloud:
                content_parts.append(self.subject_cloud)
            self.subject_content = ' '.join(content_parts)
        
        else:
            # 变化组
            actual_type = forecast_line.type
            if hasattr(forecast_line, 'raw') and forecast_line.raw:
                raw_line = forecast_line.raw.strip()
                if raw_line.startswith('PROB30'):
                    actual_type = 'PROB30'
                elif raw_line.startswith('PROB40'):
                    actual_type = 'PROB40'
                elif raw_line.startswith('PROB'):
                    prob_match = re.match(r'^(PROB\d+)', raw_line)
                    if prob_match:
                        actual_type = prob_match.group(1)
            
            group_info = {
                'type': actual_type,
                '_line': forecast_line,
                'content': '',
                'validity_period_start': '',
                'validity_period_end': '',
                'wind': wind_info.get('wind', ''),
                'wind_direction': wind_info.get('direction', ''),
                'wind_speed': wind_info.get('speed', ''),
                'wind_speed_mps': wind_info.get('speed_mps', ''),
                'gust': wind_info.get('gust', ''),
                'gust_mps': wind_info.get('gust_mps', ''),
                'visibility': visibility_info['visibility'],
                'visibility_m': visibility_info['visibility_m'],
                'weather': weather_info['weather'],
                'weather1': weather_info['weather1'],
                'weather2': weather_info['weather2'],
                'weather3': weather_info['weather3'],
                'weather4': weather_info['weather4'],
                'weather5': weather_info['weather5'],
                'cloud': cloud_info['cloud'],
                'cloud_min': cloud_info['cloud_min']
            }
            
            # 时间信息
            if forecast_line.start_time and forecast_line.start_time.dt:
                group_info['validity_period_start'] = forecast_line.start_time.dt.strftime('%d%H')
            if forecast_line.end_time and forecast_line.end_time.dt:
                group_info['validity_period_end'] = forecast_line.end_time.dt.strftime('%d%H')
            
            # 构建变化组内容（完全移植原版逻辑）
            content_parts = []
            if group_info['type'] not in ['FROM']:
                content_parts.append(group_info['type'])
            
            # 添加时间
            if group_info['validity_period_start'] and group_info['validity_period_end']:
                if group_info['type'] == 'FROM':
                    content_parts.append(f"FM{group_info['validity_period_start']}")
                else:
                    content_parts.append(f"{group_info['validity_period_start']}/{group_info['validity_period_end']}")
            
            # 添加气象要素
            if group_info['wind']:
                content_parts.append(group_info['wind'])
            if group_info['visibility']:
                content_parts.append(group_info['visibility'])
            if group_info['weather']:
                content_parts.append(group_info['weather'])
            if group_info['cloud']:
                content_parts.append(group_info['cloud'])
            
            group_info['content'] = ' '.join(content_parts)
            
            # 初始化content_all，对于非BECMG变化组，只包含气象要素（去掉类型和时间）
            content_all_parts = []
            if group_info['wind']:
                content_all_parts.append(group_info['wind'])
            if group_info['visibility']:
                content_all_parts.append(group_info['visibility'])
            if group_info['weather']:
                content_all_parts.append(group_info['weather'])
            if group_info['cloud']:
                content_all_parts.append(group_info['cloud'])
            group_info['content_all'] = ' '.join(content_all_parts)
            
            self.change_groups[change_index] = group_info

    def _snapshot_own_elements(self) -> None:
        """BECMG 继承前记录各组自身写出的要素，供 taf_elements 打 inherited。"""
        self._own_elements = {}
        for index, group in self.change_groups.items():
            vis = (group.get('visibility') or '').strip()
            weather = (group.get('weather') or '').strip()
            cloud = (group.get('cloud') or '').strip()
            line = group.get('_line')
            others = []
            if line is not None:
                others = [str(item).upper() for item in (getattr(line, 'other', None) or [])]
            self._own_elements[index] = {
                'wind': bool(group.get('wind')),
                'visibility': bool(vis),
                'weather': bool(weather),
                'cloud': bool(cloud) or any(token in others for token in ('NSC', 'SKC', 'CLR')),
                'cavok': vis.upper() == 'CAVOK',
                'vis_raw': vis,
            }
    
    def inherit_element(self, element_name: str, change_index: int) -> str:
        """为BECMG变化组继承要素"""
        # 向前查找最近的一个FROM或BECMG变化组（不管是否包含该要素）
        for i in range(change_index - 1, -1, -1):
            if i in self.change_groups:
                group = self.change_groups[i]
                if group['type'] in ['BECMG', 'FROM']:
                    # 特殊处理天气现象：如果最近的变化组包含NSW，则天气现象继承空值
                    if element_name in ['weather', 'weather1', 'weather2', 'weather3', 'weather4', 'weather5']:
                        group_weather = group.get('weather', '').strip('()')
                        if group_weather == 'NSW':
                            return ''  # NSW表示无重要天气现象，继承空值
                    
                    # 特殊处理云组：如果最近的变化组包含NSC/SKC，则云组继承空值
                    if element_name in ['cloud', 'cloud_min']:
                        group_cloud = group.get('cloud', '').strip('()')
                        if group_cloud in ['NSC', 'SKC'] or not group_cloud:
                            return ''  # NSC/SKC或空值表示无云组，继承空值
                    
                    # 继承该变化组的对应要素（包括空值）
                    inherited_value = group.get(element_name, '')
                    # 如果已经有括号包裹，去掉括号后返回（避免多重继承时重复包裹）
                    return inherited_value.strip('()')
        
        # 如果没找到任何FROM或BECMG变化组，从主预报继承
        subject_element = getattr(self, f'subject_{element_name}', '')
        return subject_element

    def process_becmg_inheritance(self):
        """处理BECMG变化组的继承逻辑"""
        elements_to_inherit = ['wind', 'visibility', 'weather', 'cloud']
        
        for i, group in self.change_groups.items():
            if group['type'] == 'BECMG':
                # 检查是否有SKC/NSC标识，如果有则跳过云组继承
                has_skc_nsc = False
                if hasattr(self, 'taf_obj') and self.taf_obj and self.taf_obj.data:
                    forecast_line = self.taf_obj.data.forecast[i] if i < len(self.taf_obj.data.forecast) else None
                    if forecast_line and hasattr(forecast_line, 'other') and forecast_line.other:
                        for item in forecast_line.other:
                            if str(item).upper() in ['SKC', 'NSC']:
                                has_skc_nsc = True
                                break
                    # 也检查原始报文中的NSC
                    if forecast_line and hasattr(forecast_line, 'raw') and forecast_line.raw:
                        if 'NSC' in forecast_line.raw.upper():
                            has_skc_nsc = True
                
                for element in elements_to_inherit:
                    # 如果有SKC/NSC标识，跳过云组继承
                    if has_skc_nsc and element in ['cloud', 'cloud_min']:
                        continue
                    
                    if not group.get(element):
                        inherited_value = self.inherit_element(element, i)
                        # 总是继承，包括空值，但只有非空值才加括号
                        if inherited_value:
                            group[element] = f"({inherited_value})"
                            
                            # 同时处理相关的衍生字段
                            if element == 'wind' and inherited_value:
                                # 解析继承的风信息，支持数字风向和VRB风向，如"33007KT"、"VRB05G12KT"
                                wind_match = re.match(r'(VRB|\d{2,3})(\d{2})(?:G(\d+))?(KT|MPS)?', inherited_value.replace(' ', ''))
                                if wind_match:
                                    # 确保数字风向保持3位格式
                                    direction = wind_match.group(1)
                                    if direction.isdigit():
                                        direction = direction.zfill(3)
                                    group['wind_direction'] = direction
                                    group['wind_speed'] = wind_match.group(2)
                                    group['gust'] = wind_match.group(3) or ''
                                    unit = wind_match.group(4) or 'KT'  # 默认为KT而不是MPS
                                    
                                    # 根据继承的风组单位进行正确转换
                                    if unit.upper() == 'MPS':
                                        group['wind_speed_mps'] = group['wind_speed']
                                        group['gust_mps'] = group['gust']
                                    else:  # KT或其他
                                        group['wind_speed_mps'] = str(self.kt_to_mps(float(group['wind_speed']))) if group['wind_speed'] else ''
                                        group['gust_mps'] = str(self.kt_to_mps(float(group['gust']))) if group['gust'] else ''
                            
                            elif element == 'visibility' and inherited_value:
                                # 对继承的能见度值进行正确的单位转换
                                vis_m = self._convert_visibility_to_meters(inherited_value)
                                if vis_m:
                                    group['visibility_m'] = vis_m
                            
                            elif element == 'weather' and inherited_value:
                                # 分解天气现象
                                weather_list = inherited_value.split()
                                for j, weather in enumerate(weather_list[:5], 1):
                                    group[f'weather{j}'] = weather
                            
                            elif element == 'cloud' and inherited_value:
                                # 在达到云量下限的云组中提取最低云高
                                group['cloud_min'] = format_cloud_min(
                                    lowest_height_in_text(inherited_value, self._min_cloud_amt())
                                )
                        else:
                            # 继承空值，不加括号，但也需要处理相关字段
                            group[element] = inherited_value  # 空字符串
                            
                            # 清空相关的衍生字段
                            if element == 'wind':
                                group['wind_direction'] = ''
                                group['wind_speed'] = ''
                                group['wind_speed_mps'] = ''
                                group['gust'] = ''
                                group['gust_mps'] = ''
                            elif element == 'visibility':
                                group['visibility_m'] = ''
                            elif element == 'weather':
                                for j in range(1, 6):
                                    group[f'weather{j}'] = ''
                            elif element == 'cloud':
                                group['cloud_min'] = ''
                
                # 每个BECMG完成继承后，立即检查并应用CAVOK逻辑
                self.apply_cavok_to_group(group)
                
                # 检查并转换继承的CAVOK（如果变化组有天气现象或云组）
                self.convert_inherited_cavok_if_needed(group)

    def apply_cavok_to_group(self, group):
        """对单个变化组应用CAVOK逻辑"""
        # 检查能见度是否为CAVOK，但要区分是自身的还是继承的
        visibility = group.get('visibility', '')
        
        # 只有当变化组自身的能见度是CAVOK时才清除天气现象和云组
        # 如果是继承的CAVOK（带括号），不清除自身明确指定的天气现象或云组
        if visibility.upper() == 'CAVOK':  # 自身能见度为CAVOK（不带括号）
            # 清空天气现象相关字段
            group['weather'] = ''
            group['weather1'] = ''
            group['weather2'] = ''
            group['weather3'] = ''
            group['weather4'] = ''
            group['weather5'] = ''
            
            # 清空云组相关字段
            group['cloud'] = ''
            group['cloud_min'] = ''
            return True
        return False

    def convert_inherited_cavok_if_needed(self, group):
        """如果BECMG变化组继承CAVOK但有天气现象或云组，则转换CAVOK为具体数值"""
        visibility = group.get('visibility', '')
        
        # 检查是否为继承的CAVOK
        if visibility.strip('()').upper() == 'CAVOK' and visibility.startswith('('):
            # 检查是否有天气现象或云组
            has_weather = any(group.get(f'weather{i}', '') for i in range(1, 6)) or group.get('weather', '')
            has_cloud = group.get('cloud', '') or group.get('cloud_min', '')
            
            if has_weather or has_cloud:
                # 判断机场类型（米制还是英里制）
                station_code = getattr(self, 'airport_4code', '')
                
                # 使用更准确的单位制判断方法
                # 北美格式机场（美国、加拿大等）使用英里制，其他使用米制
                uses_na_format = False
                try:
                    # 尝试使用AVWX的准确判断
                    from avwx.station import uses_na_format as avwx_uses_na_format
                    uses_na_format = avwx_uses_na_format(station_code)
                except ImportError:
                    # 如果AVWX不可用，使用简化判断
                    # 北美地区机场代码：K(美国本土), P(美国太平洋), C(加拿大), T(部分加勒比海)
                    na_prefixes = ['K', 'P', 'C']
                    uses_na_format = any(station_code.startswith(prefix) for prefix in na_prefixes)
                
                # 根据机场类型转换CAVOK
                if uses_na_format:  # 英里制机场
                    new_visibility = '(P6SM)'
                    new_visibility_m = '9999'  # 内部统一用米表示
                else:  # 米制机场
                    new_visibility = '(9999)'
                    new_visibility_m = '9999'
                
                # 更新能见度字段
                group['visibility'] = new_visibility
                group['visibility_m'] = new_visibility_m
                group['_vis_from_cavok'] = True

    def generate_becmg_content_all(self):
        """为BECMG变化组生成完整的content_all"""
        for i, group in self.change_groups.items():
            if group['type'] == 'BECMG':
                # 构建完整的content_all，只包含气象要素（去掉类型和时间），按照要求的顺序：风组 + 能见度组 + 天气现象组 + 云组
                content_all_parts = []
                
                # 按顺序添加四类要素（不包括类型和时间）
                if group['wind']:
                    content_all_parts.append(group['wind'])
                if group['visibility']:
                    content_all_parts.append(group['visibility'])
                if group['weather']:
                    content_all_parts.append(group['weather'])
                if group['cloud']:
                    content_all_parts.append(group['cloud'])
                
                group['content_all'] = ' '.join(content_all_parts)

    def get_earliest_change_time(self) -> str:
        """从原始报文中按文本顺序获取第一个FROM或BECMG变化开始时间"""
        if not hasattr(self, 'content') or not self.content:
            return ''
        
        # 按文本顺序从前到后查找第一个BECMG或FM
        # 查找BECMG DDHH/ddhh格式，提取DDHH
        becmg_match = re.search(r'BECMG\s+(\d{4})/\d{4}', self.content)
        
        # 查找FM DDHHMM格式，提取DDHH（前4位）
        fm_match = re.search(r'FM(\d{4})\d{2}', self.content)
        
        # 比较两者在文本中的位置，返回最先出现的
        if becmg_match and fm_match:
            # 两者都存在，返回位置靠前的
            if becmg_match.start() < fm_match.start():
                return becmg_match.group(1)  # BECMG的DDHH
            else:
                return fm_match.group(1)     # FM的DDHH
        elif becmg_match:
            return becmg_match.group(1)      # 只有BECMG
        elif fm_match:
            return fm_match.group(1)         # 只有FM
        else:
            return ''                        # 都没有找到
    
    def parse_temperature_info(self, data):
        """解析温度信息 - 完全移植原始程序逻辑"""
        # 从原始报文中解析所有温度组，支持多个温度
        if hasattr(self, 'content') and self.content:
            # 查找所有最高温度 TX
            max_temps = re.findall(r'TX(\d+|M\d+)/(\d{4})Z', self.content)
            if max_temps:
                # 第一个最高温度
                self.subject_max_temp1 = max_temps[0][0].replace('M', '-')
                self.subject_max_temp1_time = max_temps[0][1]
                
                # 第二个最高温度（如果存在）
                if len(max_temps) > 1:
                    self.subject_max_temp2 = max_temps[1][0].replace('M', '-')
                    self.subject_max_temp2_time = max_temps[1][1]
            
            # 查找所有最低温度 TN
            min_temps = re.findall(r'TN(\d+|M\d+)/(\d{4})Z', self.content)
            if min_temps:
                # 第一个最低温度
                self.subject_min_temp1 = min_temps[0][0].replace('M', '-')
                self.subject_min_temp1_time = min_temps[0][1]
                
                # 第二个最低温度（如果存在）
                if len(min_temps) > 1:
                    self.subject_min_temp2 = min_temps[1][0].replace('M', '-')
                    self.subject_min_temp2_time = min_temps[1][1]
        
        # 如果原始解析失败，回退到AVWX解析（兼容性处理）
        if not self.subject_max_temp1:
            if hasattr(data, 'max_temp') and data.max_temp:
                temp_match = re.match(r'TX(\d+|M\d+)/(\d{4})Z', data.max_temp)
                if temp_match:
                    self.subject_max_temp1 = temp_match.group(1).replace('M', '-')
                    self.subject_max_temp1_time = temp_match.group(2)
        
        if not self.subject_min_temp1:
            if hasattr(data, 'min_temp') and data.min_temp:
                temp_match = re.match(r'TN(\d+|M\d+)/(\d{4})Z', data.min_temp)
                if temp_match:
                    self.subject_min_temp1 = temp_match.group(1).replace('M', '-')
                    self.subject_min_temp1_time = temp_match.group(2)
    
    def _min_cloud_amt(self) -> str:
        """当前机场计入最低云底高的最低云量。"""
        code = self.airport_4code or ''
        cache = getattr(self, '_min_cloud_amt_cache', None)
        if isinstance(cache, tuple) and cache[0] == code:
            return cache[1]
        info = self.get_airport_info()
        amount = normalize_cloud_amt((info or {}).get('min_cloud_amt'))
        self._min_cloud_amt_cache = (code, amount)
        return amount

    def get_airport_info(self):
        """获取机场告警阈值信息"""
        try:
            airport_info = AirportAlertThresholds.objects.filter(
                airport_4code=self.airport_4code
            ).first()
            
            if not airport_info:
                # 使用默认配置
                default_airport_info = AirportAlertThresholds.objects.filter(
                    airport_4code='default'
                ).first()
                
                if default_airport_info:
                    from copy import deepcopy
                    airport_info = deepcopy(default_airport_info)
                    airport_info.airport_4code = self.airport_4code  # 使用实际机场代码
                    airport_info.airport_name = f'未配置机场 ({self.airport_4code})'  # 合理的名称
            
            if airport_info:
                return {
                    'visibility_m_red': airport_info.visibility_m_red,
                    'visibility_m_yellow': airport_info.visibility_m_yellow,
                    'visibility_m_green': airport_info.visibility_m_green,
                    'cloud_min_red': airport_info.cloud_min_red,
                    'cloud_min_yellow': airport_info.cloud_min_yellow,
                    'cloud_min_green': airport_info.cloud_min_green,
                    'min_cloud_amt': normalize_cloud_amt(getattr(airport_info, 'min_cloud_amt', None)),
                    'average_wind_speed_mps_red': airport_info.average_wind_speed_mps_red,
                    'average_wind_speed_mps_yellow': airport_info.average_wind_speed_mps_yellow,
                    'average_wind_speed_mps_green': airport_info.average_wind_speed_mps_green,
                    'gust_mps_red': airport_info.gust_mps_red,
                    'gust_mps_yellow': airport_info.gust_mps_yellow,
                    'gust_mps_green': airport_info.gust_mps_green,
                    'temperature_cold_red': airport_info.temperature_cold_red,
                    'temperature_cold_yellow': airport_info.temperature_cold_yellow,
                    'temperature_cold_green': airport_info.temperature_cold_green,
                    'temperature_hot_red': airport_info.temperature_hot_red,
                    'temperature_hot_yellow': airport_info.temperature_hot_yellow,
                    'temperature_hot_green': airport_info.temperature_hot_green,
                }
            else:
                return {}
        except Exception as e:
            logger.error(f"获取机场信息失败: {e}")
            return {}
    
    def calculate_alert_levels(self):
        """计算告警级别 - 按照原始程序的分级告警逻辑"""
        airport_info = self.get_airport_info()
        
        # 主预报各要素告警计算
        # 1. 风组告警 - 只有在有风组内容时才设置告警
        if self.has_wind_content(self.subject_wind_speed_mps, self.subject_gust_mps):
            self.subject_wind_warning = self.get_wind_max_alert(
                self.subject_wind_speed_mps, 
                self.subject_gust_mps, 
                airport_info
            )
        else:
            self.subject_wind_warning = None  # 空字段无需处理
        
        # 2. 能见度告警
        if self.subject_visibility_m is not None:
            try:
                visibility = int(self.subject_visibility_m)
                self.subject_visibility_warning = get_visibility_alert_level(visibility, airport_info)
            except:
                self.subject_visibility_warning = None
        else:
            self.subject_visibility_warning = None  # 空字段无需处理
        
        # 3. 天气现象告警 - 只有在有天气现象内容时才设置告警
        if self.has_weather_content(
            self.subject_weather1 or '',
            self.subject_weather2 or '',
            self.subject_weather3 or '',
            self.subject_weather4 or '',
            self.subject_weather5 or ''
        ):
            self.subject_weather_warning = self.get_weather_max_alert(
                self.subject_weather1 or '',
                self.subject_weather2 or '',
                self.subject_weather3 or '',
                self.subject_weather4 or '',
                self.subject_weather5 or ''
            )
        else:
            self.subject_weather_warning = None  # 空字段无需处理
        
        # 4. 云高告警
        if self.subject_cloud_min is not None:
            try:
                cloud_min = int(self.subject_cloud_min)
                self.subject_cloud_warning = get_cloud_alert_level(cloud_min, airport_info)
            except:
                self.subject_cloud_warning = None
        else:
            self.subject_cloud_warning = None  # 空字段无需处理
        
        # 5. 主预报综合告警 - 使用get_max_alert_level_nullable正确处理空值
        self.subject_warning = self.get_max_alert_level_nullable(
            self.subject_wind_warning,
            self.subject_visibility_warning,
            self.subject_weather_warning,
            self.subject_cloud_warning
        )
        
        # 6. 温度告警
        for temp_field in ['subject_max_temp1', 'subject_max_temp2', 'subject_min_temp1', 'subject_min_temp2']:
            temp_value = getattr(self, temp_field, '')
            if temp_value and str(temp_value).strip():
                try:
                    temp_float = float(str(temp_value))
                    temp_alert = get_temperature_alert_level(temp_float, airport_info)
                    setattr(self, f'{temp_field}_warning', temp_alert)
                except:
                    setattr(self, f'{temp_field}_warning', None)  # 转换失败时不设置告警
            else:
                setattr(self, f'{temp_field}_warning', None)  # 空字段无需处理
        
        # 7. 变化组告警计算
        for i, group in self.change_groups.items():
            # 变化组风组告警 - 只有在有风组内容时才设置告警
            if self.has_wind_content(group.get('wind_speed_mps'), group.get('gust_mps')):
                group['wind_warning'] = self.get_wind_max_alert(
                    group.get('wind_speed_mps'),
                    group.get('gust_mps'),
                    airport_info
                )
            else:
                group['wind_warning'] = None  # 空字段无需处理
            
            # 变化组能见度告警
            if group.get('visibility_m') is not None:
                try:
                    visibility = int(group['visibility_m'])
                    group['visibility_warning'] = get_visibility_alert_level(visibility, airport_info)
                except:
                    group['visibility_warning'] = None
            else:
                group['visibility_warning'] = None  # 空字段无需处理
            
            # 变化组天气现象告警 - 只有在有天气现象内容时才设置告警
            if self.has_weather_content(
                group.get('weather1', ''),
                group.get('weather2', ''),
                group.get('weather3', ''),
                group.get('weather4', ''),
                group.get('weather5', '')
            ):
                group['weather_warning'] = self.get_weather_max_alert(
                    group.get('weather1', ''),
                    group.get('weather2', ''),
                    group.get('weather3', ''),
                    group.get('weather4', ''),
                    group.get('weather5', '')
                )
            else:
                group['weather_warning'] = None  # 空字段无需处理
            
            # 变化组云高告警
            if group.get('cloud_min') is not None:
                try:
                    cloud_min = int(group['cloud_min'])
                    group['cloud_warning'] = get_cloud_alert_level(cloud_min, airport_info)
                except:
                    group['cloud_warning'] = None
            else:
                group['cloud_warning'] = None  # 空字段无需处理
            
            # 变化组综合告警 - 使用get_max_alert_level_nullable正确处理空值
            group['warning'] = self.get_max_alert_level_nullable(
                group['wind_warning'],
                group['visibility_warning'],
                group['weather_warning'],
                group['cloud_warning']
            )
    
    def get_max_alert_level(self, levels: List[str]) -> str:
        """获取最高告警级别"""
        alert_priority = {
            ALERT_NONE: 0,
            ALERT_GREEN: 1,
            ALERT_YELLOW: 2,
            ALERT_RED: 3
        }
        
        valid_levels = [level for level in levels if level in alert_priority]
        if not valid_levels:
            return ALERT_NONE
        
        return max(valid_levels, key=lambda x: alert_priority[x])
    
    def has_weather_content(self, weather1: str, weather2: str, weather3: str, weather4: str, weather5: str) -> bool:
        """检查是否有天气现象内容"""
        return any(w and w.strip() for w in [weather1, weather2, weather3, weather4, weather5])
    
    def has_wind_content(self, wind_speed_mps, gust_mps) -> bool:
        """检查是否有风组内容"""
        return (wind_speed_mps is not None and str(wind_speed_mps).strip()) or \
               (gust_mps is not None and str(gust_mps).strip())
    
    def get_weather_max_alert(self, weather1: str, weather2: str, weather3: str, 
                            weather4: str, weather5: str) -> str:
        """获取天气现象的最高告警级别"""
        levels = []
        for weather in [weather1, weather2, weather3, weather4, weather5]:
            if weather and weather.strip():
                level = get_weather_alert_level(weather.strip())
                levels.append(level)
        
        return self.get_max_alert_level(levels)
    
    def get_wind_max_alert(self, wind_speed_mps, gust_mps, airport_info: dict) -> str:
        """获取风组的最高告警级别"""
        levels = []
        
        if wind_speed_mps is not None and str(wind_speed_mps).strip():
            try:
                wind_level = get_wind_alert_level(float(wind_speed_mps), airport_info)
                levels.append(wind_level)
            except:
                pass
        
        if gust_mps is not None and str(gust_mps).strip():
            try:
                gust_level = get_gust_alert_level(float(gust_mps), airport_info)
                levels.append(gust_level)
            except:
                pass
        
        return self.get_max_alert_level(levels)
    
    def get_max_alert_level_nullable(self, *levels) -> str:
        """获取多个告警级别中的最高级别，正确处理空值情况"""
        if not levels:
            return ALERT_NONE
        
        # 过滤掉None值，但保留有效的告警级别字符串
        valid_levels = [level for level in levels if level is not None and level in [ALERT_RED, ALERT_YELLOW, ALERT_GREEN, ALERT_NONE]]
        if not valid_levels:
            return ALERT_NONE
        
        # 返回优先级最高的级别
        return self.get_max_alert_level(valid_levels)
    
    def to_database_dict(self) -> Dict[str, Any]:
        """将解析结果转换为数据库字典格式"""
        data_dict = {}
        
        # 基础字段
        data_dict['taf_observation_time'] = self.observation_time
        data_dict['taf_content'] = self.content
        data_dict['whole_validity_period'] = self.whole_validity_period
        data_dict['subject_validity_period_start'] = self.subject_validity_period_start
        data_dict['subject_validity_period_end'] = self.subject_validity_period_end
        data_dict['subject_content'] = self.subject_content
        data_dict['subject_warning'] = self.subject_warning
        
        # 主预报详细字段
        try:
            data_dict['subject_wind_speed_mps'] = int(float(self.subject_wind_speed_mps)) if self.subject_wind_speed_mps else None
        except (ValueError, TypeError):
            data_dict['subject_wind_speed_mps'] = None
            
        try:
            data_dict['subject_gust_mps'] = int(float(self.subject_gust_mps)) if self.subject_gust_mps else None
        except (ValueError, TypeError):
            data_dict['subject_gust_mps'] = None
            
        data_dict['subject_wind_warning'] = self.subject_wind_warning or 'N'
        
        try:
            data_dict['subject_visibility_m'] = int(float(self.subject_visibility_m)) if self.subject_visibility_m else None
        except (ValueError, TypeError):
            data_dict['subject_visibility_m'] = None
            
        data_dict['subject_visibility_warning'] = self.subject_visibility_warning or 'N'
        data_dict['subject_weather1'] = self.subject_weather1 or ''
        data_dict['subject_weather2'] = self.subject_weather2 or ''
        data_dict['subject_weather3'] = self.subject_weather3 or ''
        data_dict['subject_weather4'] = self.subject_weather4 or ''
        data_dict['subject_weather5'] = self.subject_weather5 or ''
        data_dict['subject_weather_warning'] = self.subject_weather_warning or 'N'
        
        try:
            data_dict['subject_cloud_min'] = int(float(self.subject_cloud_min)) if self.subject_cloud_min else None
        except (ValueError, TypeError):
            data_dict['subject_cloud_min'] = None
            
        data_dict['subject_cloud_warning'] = self.subject_cloud_warning or 'N'
        
        # 温度信息
        data_dict['subject_max_temp1'] = self.subject_max_temp1
        data_dict['subject_max_temp1_time'] = self.subject_max_temp1_time
        data_dict['subject_max_temp1_warning'] = self.subject_max_temp1_warning
        data_dict['subject_max_temp2'] = self.subject_max_temp2
        data_dict['subject_max_temp2_time'] = self.subject_max_temp2_time
        data_dict['subject_max_temp2_warning'] = self.subject_max_temp2_warning
        data_dict['subject_min_temp1'] = self.subject_min_temp1
        data_dict['subject_min_temp1_time'] = self.subject_min_temp1_time
        data_dict['subject_min_temp1_warning'] = self.subject_min_temp1_warning
        data_dict['subject_min_temp2'] = self.subject_min_temp2
        data_dict['subject_min_temp2_time'] = self.subject_min_temp2_time
        data_dict['subject_min_temp2_warning'] = self.subject_min_temp2_warning
        
        # 变化组字段
        for i in range(1, 9):
            if i in self.change_groups:
                group = self.change_groups[i]
                prefix = f'change_{i}_'
                
                # 基础字段
                data_dict[f'{prefix}type'] = group.get('type', '')
                data_dict[f'{prefix}content_all'] = group.get('content_all', '')
                data_dict[f'{prefix}warning'] = group.get('warning', '')
                data_dict[f'{prefix}validity_period_start'] = group.get('validity_period_start', '')
                data_dict[f'{prefix}validity_period_end'] = group.get('validity_period_end', '')
                
                # 详细字段
                wind_speed_mps = group.get('wind_speed_mps', '')
                try:
                    data_dict[f'{prefix}wind_speed_mps'] = int(float(wind_speed_mps)) if wind_speed_mps else None
                except (ValueError, TypeError):
                    data_dict[f'{prefix}wind_speed_mps'] = None
                    
                gust_mps = group.get('gust_mps', '')
                try:
                    data_dict[f'{prefix}gust_mps'] = int(float(gust_mps)) if gust_mps else None
                except (ValueError, TypeError):
                    data_dict[f'{prefix}gust_mps'] = None
                    
                data_dict[f'{prefix}wind_warning'] = group.get('wind_warning', 'N')
                
                visibility_m = group.get('visibility_m', '')
                try:
                    data_dict[f'{prefix}visibility_m'] = int(float(visibility_m)) if visibility_m else None
                except (ValueError, TypeError):
                    data_dict[f'{prefix}visibility_m'] = None
                    
                data_dict[f'{prefix}visibility_warning'] = group.get('visibility_warning', 'N')
                
                data_dict[f'{prefix}weather1'] = group.get('weather1', '')
                data_dict[f'{prefix}weather2'] = group.get('weather2', '')
                data_dict[f'{prefix}weather3'] = group.get('weather3', '')
                data_dict[f'{prefix}weather4'] = group.get('weather4', '')
                data_dict[f'{prefix}weather5'] = group.get('weather5', '')
                data_dict[f'{prefix}weather_warning'] = group.get('weather_warning', 'N')
                
                cloud_min = group.get('cloud_min', '')
                try:
                    data_dict[f'{prefix}cloud_min'] = int(float(cloud_min)) if cloud_min else None
                except (ValueError, TypeError):
                    data_dict[f'{prefix}cloud_min'] = None
                    
                data_dict[f'{prefix}cloud_warning'] = group.get('cloud_warning', 'N')
            else:
                prefix = f'change_{i}_'
                # 基础字段
                data_dict[f'{prefix}type'] = ''
                data_dict[f'{prefix}content_all'] = ''
                data_dict[f'{prefix}warning'] = ''
                data_dict[f'{prefix}validity_period_start'] = ''
                data_dict[f'{prefix}validity_period_end'] = ''
                
                # 详细字段
                data_dict[f'{prefix}wind_speed_mps'] = None
                data_dict[f'{prefix}gust_mps'] = None
                data_dict[f'{prefix}wind_warning'] = 'N'
                data_dict[f'{prefix}visibility_m'] = None
                data_dict[f'{prefix}visibility_warning'] = 'N'
                data_dict[f'{prefix}weather1'] = ''
                data_dict[f'{prefix}weather2'] = ''
                data_dict[f'{prefix}weather3'] = ''
                data_dict[f'{prefix}weather4'] = ''
                data_dict[f'{prefix}weather5'] = ''
                data_dict[f'{prefix}weather_warning'] = 'N'
                data_dict[f'{prefix}cloud_min'] = None
                data_dict[f'{prefix}cloud_warning'] = 'N'
        
        # 异常标签和错误报告
        data_dict['abnormal_label'] = self.abnormal_label
        data_dict['error_report'] = self.error_report
        
        # 修订报/更正报标识
        data_dict['amd_or_cor'] = self.amd_or_cor

        from parsers.taf_elements import build_taf_elements
        try:
            data_dict['taf_elements'] = build_taf_elements(self)
        except Exception as exc:
            logger.error(f'构建 taf_elements 失败: {exc}')
            data_dict['taf_elements'] = None
        
        return data_dict
    
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
    
    def parse_and_save(self) -> Dict[str, Any]:
        """解析并保存TAF数据"""
        result = {
            'status': 'error',
            'total_processed': 0,
            'success_count': 0,
            'error_count': 0,
            'errors': [],
            'updated_airports': [],
        }
        
        try:
            # 1. 获取有航班或停场的机场列表
            from utils.airport_scope import get_monitored_airport_codes
            active_airports = get_monitored_airport_codes()
            
            if not active_airports:
                result['errors'].append("未找到有航班或停场的机场，跳过TAF数据解析")
                return result
            
            # 2. 获取数据适配器并读取数据
            adapter = AdapterFactory.get_adapter('taf')
            taf_data = adapter.get_taf_data(active_airports)
            
            # 2. 识别API中缺失的机场并删除其数据库记录
            api_airports = set(taf_data['airport4Code'].astype(str).str.strip().unique()) if taf_data is not None and not taf_data.empty else set()
            missing_airports = set(active_airports) - api_airports
            deleted_missing_count = self._delete_missing_airports_data(missing_airports)
            
            if taf_data is None or taf_data.empty:
                result['errors'].append("没有获取到TAF数据")
                result['deleted_missing_count'] = deleted_missing_count
                return result
            
            for index, row in taf_data.iterrows():
                result['total_processed'] += 1
                
                try:
                    airport_code = str(row.get('airport4Code', '')).strip()
                    taf_content = str(row.get('content', '')).strip()
                    sqc = str(row.get('sqc', '')).strip()
                    
                    raw_observation_time = row.get('observationTime', '')
                    try:
                        observation_time = int(raw_observation_time) if raw_observation_time not in ('', None) else None
                    except (ValueError, TypeError):
                        observation_time = None

                    raw_receive_time = row.get('receiveTime', '')
                    receive_time = self._convert_timestamp_to_utc_string(raw_receive_time)
                    
                    if not airport_code or not taf_content or not sqc:
                        result['error_count'] += 1
                        result['errors'].append(f"行 {index}: 缺少必要字段")
                        continue
                    
                    # 使用SQC字段检查是否已存在（去重）
                    if Taf.objects.filter(sqc=sqc).exists():
                        continue
                    
                    # 将该机场所有旧记录标记为历史报文
                    Taf.objects.filter(airport_4code=airport_code).update(data_status='H')
                    
                    # 解析TAF
                    if self.parse_taf(taf_content, airport_code):
                        # 使用API原始时间戳覆盖解析得到的时间
                        self.observation_time = observation_time
                        # 转换为数据库格式
                        data_dict = self.to_database_dict()
                        
                        # 创建TAF记录（data_status='N'，created_at为毫秒时间戳）
                        taf_record = Taf(
                            airport_4code=airport_code,
                            sqc=sqc,
                            data_status='N',
                            created_at=int(time.time() * 1000),
                            **data_dict
                        )
                        taf_record.save()
                        result.setdefault('updated_airports', []).append(airport_code)
                        
                        result['success_count'] += 1
                    else:
                        result['error_count'] += 1
                        result['errors'].append(f"机场 {airport_code}: 解析失败 - {self.error_report}")
                
                except Exception as e:
                    result['error_count'] += 1
                    result['errors'].append(f"行 {index}: 处理异常 - {str(e)}")
                    logger.error(f"TAF数据处理异常: {e}")
            
            # 记录解析日志
            self._log_parse_result(result)
            
            # 解析完成后执行水位线清理
            self._clean_old_data()
            
            # 设置成功状态
            result['status'] = 'success'
            
        except Exception as e:
            result['errors'].append(f"TAF解析程序异常: {str(e)}")
            logger.error(f"TAF解析程序异常: {e}")
        
        return result
    


    def parse_taf_data_for_airports(self, airport_codes: List[str]) -> Dict[str, Any]:
        """
        为指定机场解析TAF数据
        
        Args:
            airport_codes: 机场代码列表
            
        Returns:
            Dict: 解析结果统计
        """
        
        result = {
            'success': False,  # 添加success字段
            'status': 'error',
            'total_processed': 0,
            'success_count': 0,
            'error_count': 0,
            'record_count': 0,  # 添加record_count字段
            'errors': [],
            'filtered_airports': airport_codes,
            'updated_airports': [],
        }
        
        try:
            # 清理滞留告警：航班运行已结束但告警尚未处置的记录
            self._clear_stale_taf_import_alerts(int(time.time() * 1000))

            adapter = AdapterFactory.create_adapter(time_mode=self.time_mode, token=self.token)
            taf_data = adapter.get_taf_data(airport_codes)
            
            # 识别API中缺失的机场（保留现有记录，后续由入库检查统一处理）
            api_airports = set(taf_data['airport4Code'].astype(str).str.strip().unique()) if taf_data is not None and not taf_data.empty and 'airport4Code' in taf_data.columns else set()
            missing_airports = set(airport_codes) - api_airports
            if missing_airports:
                logger.info(f"API中缺失的机场（保留现有记录）: {sorted(missing_airports)}")
            result['missing_airports_count'] = len(missing_airports)
            
            if taf_data is None or taf_data.empty:
                result['errors'].append("没有获取到TAF数据")
                return result
            
            # 过滤指定机场的数据
            if 'airport4Code' in taf_data.columns:
                taf_data_filtered = taf_data[taf_data['airport4Code'].isin(airport_codes)]
                logger.info(f"过滤后获取到 {len(taf_data_filtered)} 条指定机场的TAF数据")
            else:
                result['errors'].append("TAF数据中未找到airport4Code字段")
                return result
            
            if taf_data_filtered.empty:
                logger.warning(f"指定机场 {airport_codes} 没有TAF数据")
                result['success'] = True  # 没有数据也算成功
                result['status'] = 'success'
                result['message'] = "指定机场没有TAF数据"
                result['record_count'] = 0
                return result
            
            # 统计信息
            stats = {
                'planned_count': len(taf_data_filtered),    # 计划解析数量
                'sqc_filtered_count': 0,                   # SQC重复过滤数量
                'parsed_count': 0,                         # 实际解析数量
                'deleted_updated_count': 0,                # 删除更新的机场数量
                'new_added_count': 0,                      # 新增数量
                'error_count': 0,                          # 解析失败数量
                'sqc_skipped_airports': [],                # SQC重复跳过的机场列表
                'parsed_airports': [],                     # 实际解析的机场列表
                'deleted_updated_airports': [],            # 删除更新的机场列表
                'new_added_airports': [],                  # 新增的机场列表
                'error_airports': []                       # 解析失败的机场列表
            }
            
            deleted_airports = set()  # 记录已删除的机场，避免重复统计
            
            # 批量SQC查询优化：一次性查询所有SQC
            all_sqcs = [str(row.get('sqc', '')).strip() for _, row in taf_data_filtered.iterrows()]
            existing_sqcs = set(Taf.objects.filter(sqc__in=all_sqcs).values_list('sqc', flat=True))
            logger.info(f"批量SQC查询完成，发现 {len(existing_sqcs)} 个重复SQC")
            
            for index, row in taf_data_filtered.iterrows():
                result['total_processed'] += 1
                
                try:
                    airport_code = str(row.get('airport4Code', '')).strip()
                    taf_content = str(row.get('content', '')).strip()
                    sqc = str(row.get('sqc', '')).strip()
                    
                    if not airport_code or not taf_content or not sqc:
                        stats['error_count'] += 1
                        result['error_count'] += 1
                        result['errors'].append(f"行 {index}: 缺少必要字段")
                        continue
                    
                    # SQC查重前置：使用批量查询结果检查
                    if sqc in existing_sqcs:
                        # SQC已存在，跳过处理（避免不必要的解析）
                        stats['sqc_filtered_count'] += 1
                        stats['sqc_skipped_airports'].append(airport_code)
                        continue
                    
                    raw_observation_time = row.get('observationTime', '')
                    try:
                        # API 返回的时间戳比真实 UTC 早 8 小时，加偏移量转为真实 UTC
                        observation_time = int(raw_observation_time) + 28_800_000 if raw_observation_time not in ('', None) else None
                    except (ValueError, TypeError):
                        observation_time = None

                    raw_receive_time = row.get('receiveTime', '')
                    receive_time = self._convert_timestamp_to_utc_string(raw_receive_time)
                    
                    # SQC不存在，检查该机场是否有旧记录
                    existing_count = Taf.objects.filter(airport_4code=airport_code).count()
                    
                    # 将该机场所有旧记录标记为历史报文
                    Taf.objects.filter(airport_4code=airport_code).update(data_status='H')
                    
                    # 统计标记历史的机场（每个机场只统计一次）
                    if existing_count > 0 and airport_code not in deleted_airports:
                        stats['deleted_updated_count'] += 1
                        stats['deleted_updated_airports'].append(airport_code)
                        deleted_airports.add(airport_code)
                    
                    # 开始解析TAF（统计实际解析数量）
                    stats['parsed_count'] += 1
                    stats['parsed_airports'].append(airport_code)
                    if self.parse_taf(taf_content, airport_code):
                        # 使用API原始时间戳覆盖解析得到的时间
                        self.observation_time = observation_time
                        # 转换为数据库格式
                        data_dict = self.to_database_dict()
                        
                        # 创建TAF记录（data_status='N'，created_at为毫秒时间戳）
                        taf_record = Taf(
                            airport_4code=airport_code,
                            sqc=sqc,
                            data_status='N',
                            created_at=int(time.time() * 1000),
                            **data_dict
                        )
                        taf_record.save()
                        result.setdefault('updated_airports', []).append(airport_code)
                        
                        # 检查全表总量，超限时批量删除最旧500行
                        self._clean_old_data()
                        
                        # 统计新增（如果是新机场或者原来没有数据的机场）
                        if existing_count == 0:
                            stats['new_added_count'] += 1
                            stats['new_added_airports'].append(airport_code)
                        
                        result['success_count'] += 1
                    else:
                        stats['error_count'] += 1
                        stats['error_airports'].append(airport_code)
                        result['error_count'] += 1
                        result['errors'].append(f"机场 {airport_code}: 解析失败 - {self.error_report}")
                
                except Exception as e:
                    stats['error_count'] += 1
                    stats['error_airports'].append(airport_code if 'airport_code' in locals() else 'Unknown')
                    result['error_count'] += 1
                    result['errors'].append(f"行 {index}: 处理异常 - {str(e)}")
                    logger.error(f"TAF数据处理异常: {e}")
            
            # 添加统计信息到结果
            result['stats'] = stats
            
            # 记录解析日志
            self._log_parse_result(result)
            
            # 设置成功状态和记录数
            result['success'] = True
            result['status'] = 'success'
            result['record_count'] = stats['new_added_count']  # 使用新增数量作为记录数
            
            # 输出简化的统计日志
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            logger.info(f"预报数据更新完成 - {current_time}")
            logger.info(f"计划解析: {stats['planned_count']} 条，"
                       f"SQC重复跳过: {stats['sqc_filtered_count']} 条，"
                       f"实际解析: {stats['parsed_count']} 条，"
                       f"删除和更新: {stats['deleted_updated_count']} 条，"
                       f"新增: {stats['new_added_count']} 条，"
                       f"解析失败: {stats['error_count']} 条")
            
            # 输出各类机场清单
            if stats['sqc_skipped_airports']:
                logger.info(f"SQC重复跳过机场: {stats['sqc_skipped_airports']}")
            if stats['parsed_airports']:
                logger.info(f"实际解析机场: {stats['parsed_airports']}")
            if stats['deleted_updated_airports']:
                logger.info(f"删除和更新机场: {stats['deleted_updated_airports']}")
            if stats['new_added_airports']:
                logger.info(f"新增机场: {stats['new_added_airports']}")
            if stats['error_airports']:
                logger.info(f"解析失败机场: {stats['error_airports']}")

            # 主循环结束后，为无 N 行的机场创建占位行（直接标记 import_alert=Y）
            airports_with_n_after = set(
                Taf.objects.filter(
                    airport_4code__in=airport_codes,
                    data_status='N',
                ).values_list('airport_4code', flat=True)
            )
            placeholder_airports = []
            for airport_code in airport_codes:
                if airport_code not in airports_with_n_after:
                    self._create_taf_placeholder(airport_code, int(time.time() * 1000))
                    placeholder_airports.append(airport_code)
            if placeholder_airports:
                logger.info(f"[TAF入库告警] 创建占位行 {len(placeholder_airports)} 条，机场: {placeholder_airports}")

            # 统一执行入库告警检查（仅对 data_status=N 且 import_alert≠Y 的行）
            self._check_taf_import_alert(airport_codes, int(time.time() * 1000))

        except Exception as e:
            result['errors'].append(f"指定机场TAF解析程序异常: {str(e)}")
            logger.error(f"指定机场TAF解析程序异常: {e}")
        
        return result
    
    def _skip_import_alert(self) -> bool:
        """
        test 模式取的是固定历史快照，用真实时钟判定会把全部报文判成过期，
        故整套入库告警（占位行、过期标记、滞留清理）在该模式下不执行。
        """
        return self.time_mode == 'test'

    def _clear_stale_taf_import_alerts(self, now_ms: int):
        """
        清理滞留的TAF入库告警：
        若某机场的 import_alert=Y 且 import_alert_handle_time 为空，
        且既无航班也无停场飞机，则视为滞留告警，自动结案。
        """
        if self._skip_import_alert():
            return

        try:
            from utils.airport_scope import get_import_alert_keep_airport_codes
            keep_airports = get_import_alert_keep_airport_codes()
            updated = Taf.objects.filter(
                import_alert='Y',
                import_alert_handle_time__isnull=True,
            ).exclude(
                airport_4code__in=keep_airports
            ).update(
                import_alert_handle_time=now_ms,
                handle_status='航班运行结束且无停场飞机',
            )
            if updated:
                logger.info(f"[TAF入库告警] 清理滞留告警 {updated} 条（航班运行结束且无停场飞机）")
        except Exception as e:
            logger.error(f"[TAF入库告警] 清理滞留告警失败: {e}")

    def _check_taf_import_alert(self, airport_codes: List[str], now_ms: int):
        """
        主循环结束后，对所有受监控机场做统一入库告警检查：
        有 data_status=N 且 import_alert≠Y 的行 → 按公式判断是否过期，过期则批量标记 Y。
        占位行（data_status=C）已由主循环创建，此处不再处理。
        """
        if not airport_codes or self._skip_import_alert():
            return
        try:
            m = settings.MTWS_CONFIG['TAF_IMPORT_ALERT']['TAF_ISSUE_LEEWAY_MINUTES']
        except (KeyError, TypeError):
            m = 30

        # 批量查询所有受监控机场中 data_status=N 且尚未告警的行
        rows_to_check = list(
            Taf.objects.filter(
                airport_4code__in=airport_codes,
                data_status='N',
            ).exclude(import_alert='Y').values('airport_4code', 'sqc', 'taf_observation_time')
        )

        # 批量查询所有相关机场的 airport_info 配置
        airport_configs = {
            a.airport_4code: a
            for a in AirportTafImportConfig.objects.filter(airport_4code__in=airport_codes)
        }

        # --- 步骤1：对有 N 行且未告警的机场做入库检查 ---
        alert_sqcs = []
        alerted_airports = []

        for row in rows_to_check:
            airport_code = row['airport_4code']
            cfg = airport_configs.get(airport_code)
            if (
                not cfg
                or cfg.taf_init_time is None
                or cfg.taf_max_delay is None
                or cfg.import_check_interval is None
            ):
                continue

            check_obs_time = calc_taf_expected_issue_ms(
                now_ms, cfg.taf_init_time, cfg.taf_max_delay, cfg.import_check_interval, m
            )
            if check_obs_time is None:
                continue

            taf_obs_time   = row['taf_observation_time']

            if taf_obs_time is not None and taf_obs_time < check_obs_time:
                alert_sqcs.append(row['sqc'])
                alerted_airports.append(airport_code)

        if alert_sqcs:
            Taf.objects.filter(sqc__in=alert_sqcs).update(
                import_alert='Y',
                import_alert_time=now_ms,
            )
            logger.info(f"[TAF入库告警] 标记过期报文 {len(alert_sqcs)} 条，机场: {alerted_airports}")

        # --- 步骤1.5：自动覆盖 — 对"不需要告警"的机场，关闭其未处理的历史告警 ---
        alerted_set = set(alerted_airports)
        no_alert_sqc_map = {
            row['airport_4code']: row['sqc']
            for row in rows_to_check
            if row['airport_4code'] not in alerted_set
        }
        if no_alert_sqc_map:
            auto_cover_airports = []
            for airport_code, new_sqc in no_alert_sqc_map.items():
                updated = Taf.objects.filter(
                    airport_4code=airport_code,
                    import_alert='Y',
                    import_alert_handle_time__isnull=True,
                ).update(
                    import_alert_handle_time=now_ms,
                    handle_status=f'新报文已入库，sqc={new_sqc}',
                )
                if updated:
                    auto_cover_airports.append(airport_code)
            if auto_cover_airports:
                logger.info(f"[TAF入库告警] 自动覆盖历史告警，机场: {auto_cover_airports}")

    def _create_taf_placeholder(self, airport_code: str, now_ms: int):
        """
        为无任何有效数据的机场创建 data_status=C 的占位行，并直接标记 import_alert=Y。
        SQC 格式与 METAR 占位行保持一致：C_{airport_4code}_{now_ms}
        """
        if self._skip_import_alert():
            return

        try:
            sqc = f"C_{airport_code}_{now_ms}"
            Taf.objects.create(
                airport_4code=airport_code,
                sqc=sqc,
                data_status='C',
                import_alert='Y',
                import_alert_time=now_ms,
                created_at=now_ms,
            )
        except Exception as e:
            logger.error(f"[TAF入库告警] 创建占位行失败 {airport_code}: {e}")

    def _clean_old_data(self):
        """清理TAF记录（水位线模式）：超过上限时一次性削减至上限的90%，按created_at升序删除最旧记录。"""
        try:
            max_records = settings.MTWS_CONFIG['DATA_RETENTION']['taf_max_records']
            current_count = Taf.objects.count()

            if current_count <= max_records:
                return

            target_count = int(max_records * 0.9)
            delete_count = current_count - target_count
            old_ids = list(
                Taf.objects.order_by('created_at').values_list('id', flat=True)[:delete_count]
            )
            if old_ids:
                Taf.objects.filter(id__in=old_ids).delete()
                logger.info(f"TAF表水位线清理：{current_count} 条 → 删除 {delete_count} 条，目标保留 {target_count} 条")

        except Exception as e:
            logger.error(f"清理TAF旧数据失败: {e}")
    
    def _delete_missing_airports_data(self, missing_airports: set) -> int:
        """删除API中缺失机场的TAF数据"""
        total_deleted = 0
        deleted_airports_list = []
        
        for airport_code in missing_airports:
            deleted_count = Taf.objects.filter(airport_4code=airport_code).delete()[0]
            if deleted_count > 0:
                deleted_airports_list.append(airport_code)
                total_deleted += deleted_count
        
        if missing_airports:
            logger.info(f"API中缺失的机场: {sorted(missing_airports)}，共删除 {total_deleted} 条TAF记录")
            if deleted_airports_list:
                logger.info(f"删除缺失机场记录: {sorted(deleted_airports_list)}")
        
        return total_deleted
    
    def _log_parse_result(self, result: Dict[str, Any]):
        """记录解析结果"""
        try:
            status = 'success' if result['error_count'] == 0 else 'warning' if result['success_count'] > 0 else 'error'
            
            message_parts = [
                f"处理 {result['total_processed']} 条记录",
                f"成功 {result['success_count']} 条",
                f"失败 {result['error_count']} 条"
            ]
            
            if result['errors']:
                message_parts.append(f"错误详情: {'; '.join(result['errors'][:5])}")
                if len(result['errors']) > 5:
                    message_parts.append(f"等 {len(result['errors'])} 个错误")
            
            ParseLog.objects.create(
                parse_type='taf',
                status=status,
                message='; '.join(message_parts),
                record_count=result['success_count'],
                error_count=result['error_count']
            )
            
        except Exception as e:
            logger.error(f"记录TAF解析日志失败: {e}") 