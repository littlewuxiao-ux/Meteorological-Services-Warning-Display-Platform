"""
API数据源适配器
用于从API接口获取数据，基于测试脚本的成功配置
"""

import requests
import pandas as pd
from typing import Dict, Any, Optional, List
import logging
from datetime import datetime, timedelta
import json

from .base_adapter import BaseDataAdapter

from utils.cas_api_log import log_cas_api_request

logger = logging.getLogger('fmsa.data_adapters')


class APIDataAdapter(BaseDataAdapter):
    """API数据源适配器"""
    
    def __init__(self, config: Dict[str, Any] = None, time_mode: str = 'current', token: str = None):
        """
        初始化API数据适配器
        
        Args:
            config: 配置参数（暂时使用硬编码配置）
            time_mode: 仅 current 使用本适配器
            token: current模式下的认证token
        """
        super().__init__(config or {})
        
        self.time_mode = time_mode
        self.token = token
        self.timeout = 30
        
        self.base_url = "http://sfa-wgw-inn.sf-airlines.com:1080"
        self.headers = {
            'token': token or '',
            'Content-Type': 'application/json'
        }
        
        # API端点
        self.endpoints = {
            'flight': '/flight/flightSchedule/getByFlightDate',
            'metar': '/met/dispatchMetarMetTel/queryMetarTelList',
            'taf': '/met/dispatchTafMetTel/queryTafTelList',
            'history': '/met/dispatchMetTelSummary/selectNewestTopMet'
        }
    
    def _make_post_request(self, endpoint: str, data: Optional[Dict] = None, params: Optional[Dict] = None) -> Optional[Dict]:
        """
        发送POST API请求
        
        Args:
            endpoint: API端点
            data: 请求体数据
            params: URL参数
            
        Returns:
            Dict: 响应数据
        """
        try:
            url = f"{self.base_url}{endpoint}"
            log_cas_api_request(
                endpoint,
                has_token=bool(self.token) if self.time_mode == 'current' else False,
            )

            if params:
                # 对于历史报文接口，参数在URL中
                response = requests.post(
                    url,
                    headers=self.headers,
                    params=params,
                    timeout=self.timeout
                )
            else:
                # 对于其他接口，数据在请求体中
                response = requests.post(
                    url,
                    headers=self.headers,
                    json=data,
                    timeout=self.timeout
                )
            
            logger.info(f"API请求: {url}, 状态码: {response.status_code}")
            
            if response.status_code == 200:
                response_data = response.json()
                if response_data.get('success'):
                    return response_data
                else:
                    logger.error(f"API返回失败: {response_data.get('errorMessage', '未知错误')}")
                    return None
            else:
                logger.error(f"API请求失败: {url}, 状态码: {response.status_code}")
                return None
                
        except requests.RequestException as e:
            logger.error(f"API请求异常: {endpoint}, 错误: {e}")
            return None
        except Exception as e:
            logger.error(f"处理API响应失败: {endpoint}, 错误: {e}")
            return None
    
    def update_token(self, token: str):
        """
        更新认证token（用于current模式）
        
        Args:
            token: 新的认证token
        """
        if self.time_mode == 'current':
            self.token = token
            self.headers['token'] = token
            logger.info("Token已更新")
    
    def get_flight_data(self) -> pd.DataFrame:
        """
        获取航班数据
        
        Returns:
            DataFrame: 航班数据
        """
        try:
            # 计算时间范围（当前时间前24小时到后48小时）
            now = datetime.now()
            start_time = now - timedelta(hours=24)
            end_time = now + timedelta(hours=48)
            
            # 转换为毫秒级时间戳
            start_timestamp = int(start_time.timestamp() * 1000)
            end_timestamp = int(end_time.timestamp() * 1000)
            
            # 准备请求数据（纳入 ATA 供 events）
            request_data = {
                "startTime": start_timestamp,
                "endTime": end_timestamp,
                "excludeCancel": True,
                "excludeHaveAta": False
            }
            
            logger.info(f"请求航班数据: {start_time} 到 {end_time}")
            
            # 发送请求
            response_data = self._make_post_request(self.endpoints['flight'], request_data)
            
            if not response_data or not response_data.get('obj'):
                logger.warning("获取航班数据失败或数据为空")
                return pd.DataFrame()
            
            # 转换为DataFrame
            flight_data = response_data['obj']
            df = pd.DataFrame(flight_data)
            
            logger.info(f"成功获取航班数据: {len(df)} 行")
            return df
            
        except Exception as e:
            logger.error(f"获取航班数据失败: {e}")
            return pd.DataFrame()
    
    def get_metar_data(self, airport_codes: List[str] = None) -> pd.DataFrame:
        """
        获取METAR数据
        
        Args:
            airport_codes: 机场四字代码列表
            
        Returns:
            DataFrame: METAR数据
        """
        try:
            if not airport_codes:
                logger.warning("未提供机场代码，无法获取METAR数据")
                return pd.DataFrame()
            
            # 计算观测时间（当前时间前2小时）
            observation_time = datetime.now() - timedelta(hours=2)
            observation_timestamp = int(observation_time.timestamp() * 1000)
            
            # 准备请求数据
            request_data = {
                "airport4Codes": airport_codes,
                "observationTime": observation_timestamp
            }
            
            logger.info(f"请求METAR数据: 机场{airport_codes}, 观测时间{observation_time}")
            
            # 发送请求
            response_data = self._make_post_request(self.endpoints['metar'], request_data)
            
            if not response_data or not response_data.get('obj'):
                logger.warning("获取METAR数据失败或数据为空")
                return pd.DataFrame()
            
            # 转换为DataFrame
            metar_data = response_data['obj']
            df = pd.DataFrame(metar_data)
            
            logger.info(f"成功获取METAR数据: {len(df)} 行")
            return df
            
        except Exception as e:
            logger.error(f"获取METAR数据失败: {e}")
            return pd.DataFrame()
    
    def get_taf_data(self, airport_codes: List[str] = None) -> pd.DataFrame:
        """
        获取TAF数据
        
        Args:
            airport_codes: 机场四字代码列表
            
        Returns:
            DataFrame: TAF数据
        """
        try:
            if not airport_codes:
                logger.warning("未提供机场代码，无法获取TAF数据")
                return pd.DataFrame()
            
            # 计算观测时间（当前时间前14小时）
            observation_time = datetime.now() - timedelta(hours=14)
            observation_timestamp = int(observation_time.timestamp() * 1000)
            
            # 准备请求数据
            request_data = {
                "airport4Codes": airport_codes,
                "observationTime": observation_timestamp
            }
            
            logger.info(f"请求TAF数据: 机场{airport_codes}, 观测时间{observation_time}")
            
            # 发送请求
            response_data = self._make_post_request(self.endpoints['taf'], request_data)
            
            if not response_data or not response_data.get('obj'):
                logger.warning("获取TAF数据失败或数据为空")
                return pd.DataFrame()
            
            # 转换为DataFrame
            taf_data = response_data['obj']
            df = pd.DataFrame(taf_data)
            
            logger.info(f"成功获取TAF数据: {len(df)} 行")
            return df
            
        except Exception as e:
            logger.error(f"获取TAF数据失败: {e}")
            return pd.DataFrame()
    
    def get_history_reports(self, airport_code: str, metar_taf_num: int = 3, ws_wa_num: int = 1) -> Dict[str, List[Dict]]:
        """
        获取历史报文（用于弹窗功能）
        
        Args:
            airport_code: 机场四字代码
            metar_taf_num: 实况/预报数量
            ws_wa_num: WS/WA报文数量
            
        Returns:
            Dict: 包含实况和预报报文的字典
        """
        try:
            # 准备URL参数
            params = {
                "code4": airport_code,
                "metarOrTafTopNum": metar_taf_num,
                "wsOrWaTopNum": ws_wa_num
            }
            
            logger.info(f"请求历史报文: 机场{airport_code}")
            
            # 发送请求
            response_data = self._make_post_request(self.endpoints['history'], params=params)
            
            if not response_data or not response_data.get('obj'):
                logger.warning(f"获取机场{airport_code}历史报文失败或数据为空")
                return {'metar_reports': [], 'taf_reports': []}
            
            # 分类处理报文
            all_reports = response_data['obj']
            metar_reports = []
            taf_reports = []
            
            for report in all_reports:
                wtype = report.get('wtype', '')
                if wtype in ['SA', 'SP']:
                    metar_reports.append(report)
                elif wtype in ['FC', 'FT']:
                    taf_reports.append(report)
            
            # 按时间排序（从新到旧）
            metar_reports.sort(key=lambda x: x.get('receiveTime', 0), reverse=True)
            taf_reports.sort(key=lambda x: x.get('receiveTime', 0), reverse=True)
            
            logger.info(f"成功获取历史报文: 实况{len(metar_reports)}条, 预报{len(taf_reports)}条")
            
            return {
                'metar_reports': metar_reports,
                'taf_reports': taf_reports
            }
            
        except Exception as e:
            logger.error(f"获取历史报文失败: {e}")
            return {'metar_reports': [], 'taf_reports': []}
    
    def test_connection(self) -> bool:
        """
        测试数据源连接
        
        Returns:
            bool: 连接是否成功
        """
        try:
            # 测试航班接口（最基础的接口）
            now = datetime.now()
            start_time = now - timedelta(hours=1)
            end_time = now + timedelta(hours=1)
            
            start_timestamp = int(start_time.timestamp() * 1000)
            end_timestamp = int(end_time.timestamp() * 1000)
            
            request_data = {
                "startTime": start_timestamp,
                "endTime": end_timestamp,
                "excludeCancel": True,
                "excludeHaveAta": True
            }
            
            response_data = self._make_post_request(self.endpoints['flight'], request_data)
            
            if response_data:
                logger.info("API数据源连接测试成功")
                return True
            else:
                logger.error("API数据源连接测试失败")
                return False
                
        except Exception as e:
            logger.error(f"测试API数据源连接失败: {e}")
            return False
    
    def get_data_info(self) -> Dict[str, Any]:
        """
        获取数据源信息
        
        Returns:
            Dict: 数据源信息
        """
        base_info = super().get_data_info()
        
        base_info.update({
            'type': 'API',
            'base_url': self.base_url,
            'endpoints': list(self.endpoints.keys()),
            'timeout': self.timeout,
            'auth_configured': True
        })
        
        return base_info
    
    def get_aircraft_parking_data(self, carrier_code: str = None, past_hours: int = 72) -> pd.DataFrame:
        """
        获取飞机停场数据
        
        Args:
            carrier_code: 承运人代码
            past_hours: 过去小时数
            
        Returns:
            DataFrame: 飞机停场数据
        """
        try:
            # 计算时间范围（过去N小时到当前时间）
            now = datetime.now()
            start_time = now - timedelta(hours=past_hours)
            end_time = now
            
            # 转换为毫秒级时间戳
            start_timestamp = int(start_time.timestamp() * 1000)
            end_timestamp = int(end_time.timestamp() * 1000)
            
            # 准备请求数据
            request_data = {
                "startTime": start_timestamp,
                "endTime": end_timestamp,
                "excludeCancel": True
            }
            
            # 添加承运人筛选（如果提供）
            if carrier_code:
                request_data["carrier"] = carrier_code
            
            logger.info(f"请求飞机停场数据: {start_time} 到 {end_time}, 承运人: {carrier_code}")
            
            # 发送请求
            response_data = self._make_post_request(self.endpoints['flight'], request_data)
            
            if not response_data or not response_data.get('obj'):
                logger.warning("获取飞机停场数据失败或数据为空")
                return pd.DataFrame()
            
            # 转换为DataFrame
            parking_data = response_data['obj']
            df = pd.DataFrame(parking_data)
            
            logger.info(f"成功获取飞机停场数据: {len(df)} 行")
            return df
            
        except Exception as e:
            logger.error(f"获取飞机停场数据失败: {e}")
            return pd.DataFrame()