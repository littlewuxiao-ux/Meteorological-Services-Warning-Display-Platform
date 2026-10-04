"""
数值预报产品（NWP）解析器
从 open-meteo API 获取各有航班机场的温度预报数据，
截取当前时刻起 48 小时内符合极端温度阈值的数据并缓存。

机场坐标来源：airport_info。本次解析用到、而表中没有坐标的机场，才请求跑道接口并写回。
"""

import logging
import math
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

import requests

logger = logging.getLogger('mtws.parsers')

# ── 模块级缓存 ──────────────────────────────────────────────────────────────
_nwp_cache: Dict[str, List[Dict]] = {}
_nwp_last_updated: Optional[datetime] = None

# ── 常量 ────────────────────────────────────────────────────────────────────
NWP_API_URL = "https://api.open-meteo.com/v1/forecast"

TEMP_HIGH = 33.0   # °C，≥ 此值时保留
TEMP_LOW = -38.0   # °C，≤ 此值时保留


# ── 缓存访问接口 ──────────────────────────────────────────────────────────────

def get_nwp_cache() -> Dict[str, List[Dict]]:
    """返回当前 NWP 缓存数据的浅拷贝"""
    return dict(_nwp_cache)


def get_nwp_last_updated() -> Optional[str]:
    """返回最后一次成功更新的 UTC 时间（ISO 字符串），未更新时返回 None"""
    return _nwp_last_updated.isoformat() if _nwp_last_updated else None


# ── 解析器主类 ────────────────────────────────────────────────────────────────

class NwpParser:
    """NWP 数值预报解析器"""

    def fetch_and_filter(self) -> Dict[str, Any]:
        """
        主入口：获取 → 裁剪 → 筛选 → 缓存。

        流程：
          1. 查询有航班（has_flight=True）的机场四字代码
          2. 从 airport_info 批量获取机场坐标（十进制度数，无需转换）
          3. 调用 open-meteo API（一次请求涵盖所有机场）
          4. 截取当前 UTC 时刻起向后 48 小时的数据
          5. 仅保留 temperature_2m >= 33 或 <= -38 的时刻
          6. 将结果存入模块级缓存并返回摘要

        Returns:
            {
              'success': bool,
              'airport_count': int,
              'record_count': int,
              'data': { 'ZBAA': [{'time': unix_ts, 'temperature': float}, ...], ... }
            }
        """
        global _nwp_cache, _nwp_last_updated

        # ── Step 1: 获取有航班机场代码 ──
        try:
            from parsers.models import Flight
            airport_codes = list(
                Flight.objects.filter(has_flight=True)
                .values_list('airport_4code', flat=True)
                .distinct()
            )
        except Exception as e:
            logger.error(f"NWP解析: 获取机场代码失败: {e}")
            return {'success': False, 'message': f'获取机场代码失败: {e}',
                    'airport_count': 0, 'record_count': 0, 'data': {}}

        if not airport_codes:
            logger.warning("NWP解析: 未找到有航班的机场，跳过解析")
            _nwp_cache = {}
            _nwp_last_updated = datetime.now(timezone.utc)
            return {'success': True, 'airport_count': 0, 'record_count': 0, 'data': {}}

        # ── Step 2: 按需获取机场坐标（本地表优先，缺失时写回接口结果）──
        try:
            from utils.airport_coords import resolve_airport_coords
            found, coord_errors = resolve_airport_coords(airport_codes)
        except Exception as e:
            logger.error(f"NWP解析: 查询机场坐标失败: {e}")
            return {'success': False, 'message': f'查询机场坐标失败: {e}',
                    'airport_count': 0, 'record_count': 0, 'data': {}}

        if coord_errors:
            logger.error("NWP解析: " + "；".join(coord_errors))
        if not found:
            message = "；".join(coord_errors) or "未能获取机场坐标"
            return {'success': False, 'message': message,
                    'airport_count': 0, 'record_count': 0, 'data': {}}

        locations = {
            code: {'latitude': lat, 'longitude': lon}
            for code, (lat, lon) in found.items()
        }

        logger.info(
            f"NWP解析: 找到 {len(locations)} 个机场坐标"
            f"（共请求 {len(airport_codes)} 个）"
        )

        # ── Step 3: 构建坐标列表与反查映射 ──
        lats: List[str] = []
        lons: List[str] = []
        coord_to_code: Dict[tuple, str] = {}

        for code, row in locations.items():
            lats.append(str(row['latitude']))
            lons.append(str(row['longitude']))
            coord_to_code[(row['latitude'], row['longitude'])] = code

        # ── Step 4: 计算日期参数（UTC） ──
        now_utc = datetime.now(timezone.utc)
        start_date = now_utc.strftime('%Y-%m-%d')
        end_date = (now_utc + timedelta(days=2)).strftime('%Y-%m-%d')

        # ── Step 5: 调用 open-meteo API ──
        params = {
            'latitude': ','.join(lats),
            'longitude': ','.join(lons),
            'hourly': 'temperature_2m',
            'models': 'ecmwf_ifs',
            'timeformat': 'unixtime',
            'wind_speed_unit': 'ms',
            'start_date': start_date,
            'end_date': end_date,
        }

        try:
            resp = requests.get(NWP_API_URL, params=params, timeout=30)
            resp.raise_for_status()
            raw = resp.json()
        except requests.Timeout:
            logger.error("NWP解析: API 请求超时")
            return {'success': False, 'message': 'API请求超时',
                    'airport_count': 0, 'record_count': 0, 'data': {}}
        except requests.RequestException as e:
            logger.error(f"NWP解析: API 请求失败: {e}")
            return {'success': False, 'message': f'API请求失败: {e}',
                    'airport_count': 0, 'record_count': 0, 'data': {}}
        except Exception as e:
            logger.error(f"NWP解析: 解析 API 响应失败: {e}")
            return {'success': False, 'message': f'解析响应失败: {e}',
                    'airport_count': 0, 'record_count': 0, 'data': {}}

        # API 返回单坐标时为 dict，多坐标时为 list
        if isinstance(raw, dict):
            raw = [raw]

        # ── Step 6: 裁剪 48h 并按阈值筛选 ──
        now_unix = now_utc.timestamp()
        cutoff_unix = now_unix + 48 * 3600
        result_data: Dict[str, List[Dict]] = {}

        for entry in raw:
            # 用返回坐标与输入坐标进行最近邻匹配
            ret_lat = entry.get('latitude', 0)
            ret_lon = entry.get('longitude', 0)
            matched_code: Optional[str] = None
            min_dist = float('inf')

            for (lat, lon), code in coord_to_code.items():
                dist = math.sqrt((lat - ret_lat) ** 2 + (lon - ret_lon) ** 2)
                if dist < min_dist:
                    min_dist = dist
                    matched_code = code

            if not matched_code or min_dist > 1.0:
                logger.warning(
                    f"NWP解析: 无法匹配坐标 ({ret_lat}, {ret_lon})，跳过"
                )
                continue

            times = entry.get('hourly', {}).get('time', [])
            temps = entry.get('hourly', {}).get('temperature_2m', [])

            filtered: List[Dict] = []
            for t, temp in zip(times, temps):
                if temp is None:
                    continue
                if t < now_unix or t > cutoff_unix:
                    continue
                if temp >= TEMP_HIGH or temp <= TEMP_LOW:
                    filtered.append({'time': int(t), 'temperature': float(temp)})

            result_data[matched_code] = filtered

        _nwp_cache = result_data
        _nwp_last_updated = datetime.now(timezone.utc)

        total_records = sum(len(v) for v in result_data.values())
        logger.info(
            f"NWP解析完成: {len(result_data)} 个机场，"
            f"共 {total_records} 条极端温度数据"
            f"（>= {TEMP_HIGH}°C 或 <= {TEMP_LOW}°C）"
        )
        return {
            'success': True,
            'airport_count': len(result_data),
            'record_count': total_records,
            'data': result_data,
        }
