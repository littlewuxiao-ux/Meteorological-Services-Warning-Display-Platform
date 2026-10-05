"""
解析管理器
统一调度航班、METAR、TAF解析任务
"""

import logging
from datetime import datetime
from typing import Dict, Any

from django.conf import settings
from parsers.flight_parser import FlightParser
from parsers.metar_parser import MetarParser
from parsers.taf_parser import TafParser  # 已实现
from parsers.aircraft_parking_parser import AircraftParkingParser
from utils.cas_api_log import cas_user_context

logger = logging.getLogger('mtws.parsers')


class ParsingManager:
    """解析管理器"""
    
    def __init__(self, time_mode='current', token=None, user_code=None, activator_ip=None):
        """
        初始化解析管理器
        
        Args:
            time_mode: 时间模式，'current' 或 'test'
            token: current模式下的认证token
            user_code: 用户代码
            activator_ip: 手动激活时的客户端 IP
        """
        self.time_mode = time_mode
        self.token = token
        self.user_code = user_code
        self.activator_ip = activator_ip
        self.flight_parser = FlightParser(time_mode, token)
        self.metar_parser = MetarParser(time_mode, token, user_code)
        self.taf_parser = TafParser(time_mode, token)  # 已实现
        self.aircraft_parking_parser = AircraftParkingParser(time_mode, token)
        
        if activator_ip and user_code:
            logger.info(f"解析管理器初始化完成，时间模式: {time_mode} user_id={user_code} IP={activator_ip}")
        elif activator_ip:
            logger.info(f"解析管理器初始化完成，时间模式: {time_mode} IP={activator_ip}")
        else:
            logger.info(f"解析管理器初始化完成，时间模式: {time_mode} user_id={user_code or '-'}")

    def _cas_log_context(self):
        omit = bool(self.activator_ip) and not self.user_code
        return cas_user_context(
            self.user_code,
            client_ip=self.activator_ip,
            omit_user_fallback=omit,
        )

    def _settings_context(self):
        from utils.user_settings import bound_or, use_settings_user
        return use_settings_user(bound_or(self.user_code, self.time_mode))

    def run_all_parsers(self, time_mode=None) -> Dict[str, Any]:
        with self._cas_log_context(), self._settings_context():
            return self._run_all_parsers_impl(time_mode)

    def _run_all_parsers_impl(self, time_mode=None) -> Dict[str, Any]:
        """
        运行所有解析器 - 保留原有接口兼容性
        
        Args:
            time_mode: 时间模式（保留原有参数）
            
        Returns:
            Dict: 总体解析结果
        """
        # 输出整体更新开始日志
        logger.info("")  # 增加空白行
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        logger.info(f"{'='*20} 整体更新  时间：{current_time} {'='*20}")
        
        start_time = datetime.now()
        
        results = {
            'success': True,
            'start_time': start_time,
            'parsers': {}
        }
        
        # 1. 运行停场解析器（最先执行，为其他解析器提供基础数据）
        try:
            logger.info("开始停场解析")
            parking_result = self.aircraft_parking_parser.parse_aircraft_parking_data()
            results['parsers']['aircraft_parking'] = parking_result
            self._log_parse_result('aircraft_parking', parking_result)
        except Exception as e:
            logger.error(f"停场解析失败: {str(e)}")
            results['parsers']['aircraft_parking'] = {
                'success': False,
                'message': f'停场解析失败: {str(e)}',
                'airport_count': 0
            }
            # 停场解析失败不影响整体结果
        
        # 2. 运行航班解析器
        try:
            logger.info("开始航班解析")
            flight_result = self.flight_parser.parse_flight_data()
            results['parsers']['flight'] = flight_result
            self._log_parse_result('flight', flight_result)
        except Exception as e:
            logger.error(f"航班解析失败: {str(e)}")
            results['parsers']['flight'] = {
                'success': False,
                'message': f'航班解析失败: {str(e)}',
                'record_count': 0
            }
            results['success'] = False
        
        # 3. 运行METAR解析器（实况）
        try:
            logger.info("开始METAR解析")
            metar_result = self.metar_parser.parse_metar_data()
            results['parsers']['metar'] = metar_result
            self._log_parse_result('metar', metar_result)
        except Exception as e:
            logger.error(f"METAR解析失败: {str(e)}")
            results['parsers']['metar'] = {
                'success': False,
                'message': f'METAR解析失败: {str(e)}',
                'record_count': 0
            }
            results['success'] = False
        
        # 4. 运行TAF解析器（预报）
        logger.info("开始TAF解析")
        taf_result = self.taf_parser.parse_and_save()
        results['parsers']['taf'] = taf_result
        
        if not taf_result.get('success', True):
            results['success'] = False
            logger.error(f"TAF解析失败: {taf_result.get('errors', [])}")
        else:
            logger.info(f"TAF解析成功: 处理{taf_result.get('processed_count', 0)}条，保存{taf_result.get('saved_count', 0)}条")
        
        # 计算总体执行时间
        end_time = datetime.now()
        total_execution_time = (end_time - start_time).total_seconds()
        
        results.update({
            'end_time': end_time,
            'total_execution_time': total_execution_time,
            'total_records': sum(
                result.get('record_count', 0) 
                for result in results['parsers'].values()
            )
        })
        
        logger.info(f"所有解析器运行完成，总耗时: {total_execution_time:.2f} 秒")
        self._apply_marks_flight_alerts(results)
        return results
    
    def run_sequential_parsing(self, time_mode=None) -> Dict[str, Any]:
        with self._cas_log_context(), self._settings_context():
            return self._run_sequential_parsing_impl(time_mode)

    def _run_sequential_parsing_impl(self, time_mode=None) -> Dict[str, Any]:
        """
        按照新需求的顺序执行解析器：
        1. 先执行航班解析器
        2. 获取有航班的机场代码
        3. 基于机场代码执行METAR和TAF解析器
        
        Args:
            time_mode: 时间模式
            
        Returns:
            Dict: 总体解析结果
        """
        # 输出更新开始日志
        logger.info("")  # 增加空白行
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        logger.info(f"{'='*20} 更新时间：{current_time} 更新内容：【停场解析】【航班】【实况】【预报】 {'='*20}")
        
        start_time = datetime.now()
        
        results = {
            'success': True,
            'start_time': start_time,
            'parsers': {},
            'mode': 'sequential'
        }
        
        # 本批次开始前，将所有解析器标记为 queued
        try:
            from parsers.scheduler import set_parser_exec_status
            for _ut in ['aircraft_parking', 'flight', 'metar', 'taf']:
                set_parser_exec_status(_ut, 'queued')
        except Exception:
            pass

        # 第一步：运行停场解析器（最先执行）
        try:
            from parsers.scheduler import set_parser_exec_status as _s
            _s('aircraft_parking', 'running')
        except Exception:
            pass
        try:
            logger.info("【停场解析】")
            parking_result = self.aircraft_parking_parser.parse_aircraft_parking_data()
            results['parsers']['aircraft_parking'] = parking_result
            self._log_parse_result('aircraft_parking', parking_result)
        except Exception as e:
            logger.error(f"停场解析失败: {str(e)}")
            results['parsers']['aircraft_parking'] = {
                'success': False,
                'message': f'停场解析失败: {str(e)}',
                'airport_count': 0
            }
            # 停场解析失败不影响整体结果
        finally:
            try:
                from parsers.scheduler import set_parser_exec_status as _s
                _s('aircraft_parking', 'done')
            except Exception:
                pass
        
        # 第二步：运行航班解析器
        try:
            from parsers.scheduler import set_parser_exec_status as _s
            _s('flight', 'running')
        except Exception:
            pass
        _flight_done = False
        try:
            logger.info("【航班解析】")
            flight_result = self.flight_parser.parse_flight_data()
            results['parsers']['flight'] = flight_result
            self._log_parse_result('flight', flight_result)
            
            if not flight_result.get('success', False):
                if flight_result.get('data_preserved', False):
                    logger.warning("航班数据获取失败但保留原有数据，继续后续解析")
                else:
                    logger.error("航班解析失败，停止后续解析")
                    results['success'] = False
                    _flight_done = True
                    try:
                        from parsers.scheduler import set_parser_exec_status as _s
                        _s('flight', 'done')
                    except Exception:
                        pass
                    return self._finalize_results(results, start_time)
                
        except Exception as e:
            logger.error(f"航班解析失败: {str(e)}")
            results['parsers']['flight'] = {
                'success': False,
                'message': f'航班解析失败: {str(e)}',
                'record_count': 0
            }
            results['success'] = False
            _flight_done = True
            try:
                from parsers.scheduler import set_parser_exec_status as _s
                _s('flight', 'done')
            except Exception:
                pass
            return self._finalize_results(results, start_time)
        finally:
            if not _flight_done:
                try:
                    from parsers.scheduler import set_parser_exec_status as _s
                    _s('flight', 'done')
                except Exception:
                    pass
        
        # 第三步：获取有航班或停场的机场代码（首页仍只展示有航班机场）
        try:
            from utils.airport_scope import get_monitored_airport_codes
            active_airport_codes = get_monitored_airport_codes()
            
            if not active_airport_codes:
                logger.warning("未找到有航班或停场的机场，跳过气象数据解析")
                results['message'] = '未找到有航班或停场的机场，仅完成航班解析'
                return self._finalize_results(results, start_time)
                
            logger.info(f"找到 {len(active_airport_codes)} 个有航班或停场的机场: {active_airport_codes}")
            results['active_airports'] = active_airport_codes
            
        except Exception as e:
            logger.error(f"获取有航班或停场机场代码失败: {str(e)}")
            results['success'] = False
            results['message'] = f'获取机场代码失败: {str(e)}'
            return self._finalize_results(results, start_time)
        
        # 第四步：顺序执行METAR和TAF解析器（有航班 ∪ 停场）
        # 运行METAR解析器
        try:
            from parsers.scheduler import set_parser_exec_status as _s
            _s('metar', 'running')
        except Exception:
            pass
        try:
            logger.info(f"【实况解析】（解析 {len(active_airport_codes)} 个机场）")
            metar_result = self.metar_parser.parse_metar_data_for_airports(active_airport_codes)
            results['parsers']['metar'] = metar_result
            self._log_parse_result('metar', metar_result)
        except Exception as e:
            logger.error(f"METAR解析失败: {str(e)}")
            results['parsers']['metar'] = {
                'success': False,
                'message': f'METAR解析失败: {str(e)}',
                'record_count': 0
            }
            results['success'] = False
        finally:
            try:
                from parsers.scheduler import set_parser_exec_status as _s
                _s('metar', 'done')
            except Exception:
                pass
        
        # 运行TAF解析器
        try:
            from parsers.scheduler import set_parser_exec_status as _s
            _s('taf', 'running')
        except Exception:
            pass
        try:
            logger.info(f"【预报解析】（解析 {len(active_airport_codes)} 个机场）")
            taf_result = self.taf_parser.parse_taf_data_for_airports(active_airport_codes)
            
            # 标准化TAF结果格式，确保与其他解析器一致
            if 'success_count' in taf_result and 'record_count' not in taf_result:
                taf_result['record_count'] = taf_result['success_count']
            
            results['parsers']['taf'] = taf_result
            self._log_parse_result('taf', taf_result)
        except Exception as e:
            logger.error(f"TAF解析失败: {str(e)}")
            results['parsers']['taf'] = {
                'success': False,
                'message': f'TAF解析失败: {str(e)}',
                'record_count': 0
            }
            results['success'] = False
        finally:
            try:
                from parsers.scheduler import set_parser_exec_status as _s
                _s('taf', 'done')
            except Exception:
                pass
        
        return self._finalize_results(results, start_time)

    def _apply_marks_flight_alerts(self, results: Dict[str, Any]) -> None:
        """按本轮入库变化更新 marks 的 events.warning 与机场三色。"""
        try:
            from utils.marks_alert_calculator import MarksAlertCalculator
            parsers = results.get('parsers') or {}
            flight = parsers.get('flight') or {}
            metar = parsers.get('metar') or {}
            taf = parsers.get('taf') or {}
            full = set(metar.get('updated_airports') or [])
            full.update(taf.get('updated_airports') or [])
            full.update(flight.get('marks_full_airports') or [])
            partial = dict(flight.get('marks_changed_keys') or {})
            MarksAlertCalculator(self.time_mode).apply(
                full_airports=full,
                changed_keys_by_airport=partial,
            )
        except Exception as e:
            logger.error(f"marks 航班告警更新失败: {e}", exc_info=True)

    def _finalize_results(self, results: Dict[str, Any], start_time: datetime) -> Dict[str, Any]:
        """
        完成解析结果的最终处理
        
        Args:
            results: 解析结果字典
            start_time: 开始时间
            
        Returns:
            Dict: 最终结果
        """
        self._apply_marks_flight_alerts(results)
        end_time = datetime.now()
        total_execution_time = (end_time - start_time).total_seconds()
        
        results.update({
            'end_time': end_time,
            'total_execution_time': total_execution_time,
            'total_records': sum(
                result.get('record_count', 0) 
                for result in results['parsers'].values()
            )
        })
        
        logger.info(f"解析器运行完成，总耗时: {total_execution_time:.2f} 秒")
        return results
    
    def run_single_parser(self, parser_type: str) -> Dict[str, Any]:
        with self._cas_log_context(), self._settings_context():
            return self._run_single_parser_impl(parser_type)

    def _run_single_parser_impl(self, parser_type: str) -> Dict[str, Any]:
        """
        运行单个解析器
        
        Args:
            parser_type: 解析器类型，'flight' 或 'metar' 或 'taf'
            
        Returns:
            Dict: 解析结果
        """
        logger.info(f"开始运行{parser_type}解析器")
        
        try:
            if parser_type == 'flight':
                result = self.flight_parser.parse_and_save()
            elif parser_type == 'metar':
                result = self.metar_parser.parse_and_save()
            elif parser_type == 'taf':
                result = self.taf_parser.parse_and_save()
            else:
                raise ValueError(f"未知的解析器类型: {parser_type}")
            self._apply_marks_flight_alerts({'parsers': {parser_type: result}})
            return result
                
        except Exception as e:
            logger.error(f"{parser_type}解析器运行异常: {e}")
            return {
                'success': False,
                'errors': [f"{parser_type}解析器运行异常: {str(e)}"]
            }
    
    def _log_parse_result(self, parser_type: str, result: Dict[str, Any]):
        """把一次解析的结果写入日志文件。"""
        try:
            status = 'success' if result.get('success', False) else 'error'
            
            extra = ''
            if self.activator_ip and self.user_code:
                extra = f" [激活 IP={self.activator_ip} user_id={self.user_code}]"
            elif self.activator_ip:
                extra = f" [激活 IP={self.activator_ip}]"
            logger.info(
                '解析 %s %s：%s 记录=%s 错误=%s 耗时=%s秒',
                parser_type,
                status,
                (result.get('message', '') or '') + extra,
                result.get('record_count', 0),
                result.get('error_count', 0),
                result.get('execution_time', 0),
            )
        except Exception as e:
            logger.error(f"记录解析日志失败: {str(e)}")

    def run_selective_parsing(self, update_types: list, time_mode=None) -> Dict[str, Any]:
        with self._cas_log_context(), self._settings_context():
            return self._run_selective_parsing_impl(update_types, time_mode)

    def _run_selective_parsing_impl(self, update_types: list, time_mode=None) -> Dict[str, Any]:
        """
        根据指定的数据类型执行选择性解析
        
        Args:
            update_types: 要更新的数据类型列表，如 ['flight', 'metar', 'taf']
            time_mode: 时间模式
            
        Returns:
            Dict: 总体解析结果
        """
        # 生成更新内容描述
        update_content_map = {
            'flight': '【航班】',
            'metar': '【实况】', 
            'taf': '【预报】',
            'aircraft_parking': '【停场解析】'
        }
        update_content = ''.join([update_content_map.get(t, f'【{t}】') for t in update_types])
        
        # 输出更新开始日志
        logger.info("")  # 增加空白行
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        logger.info(f"{'='*20} 更新时间：{current_time} 更新内容：{update_content} {'='*20}")
        
        start_time = datetime.now()
        
        results = {
            'success': True,
            'start_time': start_time,
            'parsers': {},
            'mode': 'selective',
            'update_types': update_types
        }
        
        # 本批次开始前，将所有待执行的解析器标记为 queued
        try:
            from parsers.scheduler import set_parser_exec_status
            _known = {'flight', 'metar', 'taf', 'aircraft_parking', 'nwp'}
            for ut in update_types:
                if ut in _known:
                    set_parser_exec_status(ut, 'queued')
        except Exception:
            pass

        # 按优先级执行解析器：航班 > 实况 = 预报
        if 'flight' in update_types:
            results = self._execute_flight_parser(results)
            if not results['success']:
                return self._finalize_results(results, start_time)
        
        # 获取有航班或停场的机场（如果需要执行实况或预报解析）
        active_airport_codes = []
        if 'metar' in update_types or 'taf' in update_types:
            active_airport_codes = self._get_active_airports()
            if not active_airport_codes:
                logger.warning("未找到有航班或停场的机场，跳过气象数据解析")
                if 'flight' not in update_types:
                    results['success'] = False
                    results['message'] = '未找到有航班或停场的机场'
                return self._finalize_results(results, start_time)
            
            results['active_airports'] = active_airport_codes
        
        # 执行实况解析
        if 'metar' in update_types:
            results = self._execute_metar_parser(results, active_airport_codes)
        
        # 执行预报解析
        if 'taf' in update_types:
            results = self._execute_taf_parser(results, active_airport_codes)
        
        # 执行停场解析（独立于其他解析器）
        if 'aircraft_parking' in update_types:
            results = self._execute_aircraft_parking_parser(results)

        # 执行 NWP 解析（独立于其他解析器）
        if 'nwp' in update_types:
            results = self._execute_nwp_parser(results)

        return self._finalize_results(results, start_time)
    
    def _execute_flight_parser(self, results):
        """执行航班解析器"""
        try:
            from parsers.scheduler import set_parser_exec_status
            set_parser_exec_status('flight', 'running')
        except Exception:
            pass
        try:
            logger.info("【航班解析】")
            flight_result = self.flight_parser.parse_flight_data()
            results['parsers']['flight'] = flight_result
            self._log_parse_result('flight', flight_result)
            
            if not flight_result.get('success', False):
                if flight_result.get('data_preserved', False):
                    logger.warning("航班数据获取失败但保留原有数据，继续后续解析")
                else:
                    logger.error("航班解析失败，停止后续解析")
                    results['success'] = False
                    
        except Exception as e:
            logger.error(f"航班解析失败: {str(e)}")
            results['parsers']['flight'] = {
                'success': False,
                'message': f'航班解析失败: {str(e)}',
                'record_count': 0
            }
            results['success'] = False
        finally:
            try:
                from parsers.scheduler import set_parser_exec_status
                set_parser_exec_status('flight', 'done')
            except Exception:
                pass
            
        return results
    
    def _execute_metar_parser(self, results, active_airport_codes):
        """执行实况解析器"""
        try:
            from parsers.scheduler import set_parser_exec_status
            set_parser_exec_status('metar', 'running')
        except Exception:
            pass
        try:
            logger.info(f"【实况解析】（解析 {len(active_airport_codes)} 个机场）")
            metar_result = self.metar_parser.parse_metar_data_for_airports(active_airport_codes)
            results['parsers']['metar'] = metar_result
            self._log_parse_result('metar', metar_result)
        except Exception as e:
            logger.error(f"实况解析失败: {str(e)}")
            results['parsers']['metar'] = {
                'success': False,
                'message': f'实况解析失败: {str(e)}',
                'record_count': 0
            }
            results['success'] = False
        finally:
            try:
                from parsers.scheduler import set_parser_exec_status
                set_parser_exec_status('metar', 'done')
            except Exception:
                pass
            
        return results
    
    def _execute_taf_parser(self, results, active_airport_codes):
        """执行预报解析器"""
        try:
            from parsers.scheduler import set_parser_exec_status
            set_parser_exec_status('taf', 'running')
        except Exception:
            pass
        try:
            logger.info(f"【预报解析】（解析 {len(active_airport_codes)} 个机场）")
            taf_result = self.taf_parser.parse_taf_data_for_airports(active_airport_codes)
            
            # 标准化TAF结果格式
            if 'success_count' in taf_result and 'record_count' not in taf_result:
                taf_result['record_count'] = taf_result['success_count']
            
            results['parsers']['taf'] = taf_result
            self._log_parse_result('taf', taf_result)
        except Exception as e:
            logger.error(f"预报解析失败: {str(e)}")
            results['parsers']['taf'] = {
                'success': False,
                'message': f'预报解析失败: {str(e)}',
                'record_count': 0
            }
            results['success'] = False
        finally:
            try:
                from parsers.scheduler import set_parser_exec_status
                set_parser_exec_status('taf', 'done')
            except Exception:
                pass
            
        return results
    
    def _execute_nwp_parser(self, results):
        """执行 NWP 数值预报解析器"""
        try:
            from parsers.scheduler import set_parser_exec_status
            set_parser_exec_status('nwp', 'running')
        except Exception:
            pass
        try:
            logger.info("【NWP解析】")
            from parsers.NWP import NwpParser
            nwp_result = NwpParser().fetch_and_filter()
            if 'record_count' not in nwp_result:
                nwp_result['record_count'] = nwp_result.get('airport_count', 0)
            results['parsers']['nwp'] = nwp_result
            self._log_parse_result('nwp', nwp_result)
        except Exception as e:
            logger.error(f"NWP解析失败: {str(e)}")
            results['parsers']['nwp'] = {
                'success': False,
                'message': f'NWP解析失败: {str(e)}',
                'record_count': 0,
            }
        finally:
            try:
                from parsers.scheduler import set_parser_exec_status
                set_parser_exec_status('nwp', 'done')
            except Exception:
                pass
        return results

    def _execute_aircraft_parking_parser(self, results):
        """执行停场解析器"""
        try:
            from parsers.scheduler import set_parser_exec_status
            set_parser_exec_status('aircraft_parking', 'running')
        except Exception:
            pass
        try:
            logger.info("【停场解析】")
            parking_result = self.aircraft_parking_parser.parse_aircraft_parking_data()
            results['parsers']['aircraft_parking'] = parking_result
            self._log_parse_result('aircraft_parking', parking_result)
        except Exception as e:
            logger.error(f"停场解析失败: {str(e)}")
            results['parsers']['aircraft_parking'] = {
                'success': False,
                'message': f'停场解析失败: {str(e)}',
                'airport_count': 0
            }
            # 停场解析失败不影响整体结果
        finally:
            try:
                from parsers.scheduler import set_parser_exec_status
                set_parser_exec_status('aircraft_parking', 'done')
            except Exception:
                pass
            
        return results
    
    def _get_active_airports(self):
        """获取 METAR/TAF 解析覆盖的机场：有航班 ∪ 停场名单。"""
        try:
            from utils.airport_scope import get_monitored_airport_codes
            active_airport_codes = get_monitored_airport_codes()
            
            if active_airport_codes:
                logger.info(f"找到 {len(active_airport_codes)} 个有航班或停场的机场: {active_airport_codes}")
            
            return active_airport_codes
            
        except Exception as e:
            logger.error(f"获取有航班或停场机场代码失败: {str(e)}")
            return [] 