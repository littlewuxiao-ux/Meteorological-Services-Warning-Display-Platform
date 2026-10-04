"""按需解析机场坐标：先读 airport_info，没有坐标时再请求跑道接口并写回。"""

import logging

import requests
from django.db import DatabaseError

logger = logging.getLogger('mtws.api')

AVIATIONWEATHER_AIRPORT_URL = (
    "https://aviationweather.gov/api/data/airport?ids={code}&format=json"
)


class AirportCoordUnavailable(Exception):
    """本地表和跑道接口都没有给出该机场坐标。"""


def _normalize_codes(codes):
    seen = []
    for raw in codes:
        code = str(raw or '').strip().upper()
        if code and code not in seen:
            seen.append(code)
    return seen


def _read_local_coords(codes):
    """返回 {code: (lat, lon)}。查询失败时抛出 DatabaseError。"""
    from core.models import AirportInfo

    rows = AirportInfo.objects.filter(airport_4code__in=codes).values(
        'airport_4code', 'latitude', 'longitude'
    )
    found = {}
    for row in rows:
        lat, lon = row['latitude'], row['longitude']
        if lat is None or lon is None:
            continue
        found[row['airport_4code']] = (float(lat), float(lon))
    return found


def read_local_coord(code):
    """本地表中的 (lat, lon)。没有、坐标为空或读取失败时返回 None。"""
    code = str(code or '').strip().upper()
    if not code:
        return None
    try:
        return _read_local_coords([code]).get(code)
    except DatabaseError as exc:
        logger.warning(f"读取机场 {code} 坐标失败: {exc}")
        return None


def fetch_aviationweather_airport(code):
    """
    请求现有跑道接口。
    成功返回 {'lat', 'lon', 'name', 'runways'}，lat/lon 可能为 None。
    网络或响应失败时抛出 requests.RequestException 或 ValueError。
    """
    response = requests.get(
        AVIATIONWEATHER_AIRPORT_URL.format(code=code),
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload:
        return {'lat': None, 'lon': None, 'name': None, 'runways': []}
    info = payload[0]
    name = info.get('name') or info.get('site') or None
    if isinstance(name, str):
        name = name[:100]
    return {
        'lat': info.get('lat'),
        'lon': info.get('lon'),
        'name': name,
        'runways': info.get('runways') or [],
    }


def store_airport_coord(code, lat, lon, name=None):
    """没有坐标时写入 airport_info。已有中文名称不被接口英文名覆盖。"""
    from core.airport_directory import apply_prefix_if_blank
    from core.models import AirportInfo

    obj = AirportInfo.objects.filter(airport_4code=code).first()
    created = obj is None
    if created:
        obj = AirportInfo(
            airport_4code=code,
            catalog_only=True,
            latitude=float(lat),
            longitude=float(lon),
            airport_name=name or None,
        )
        apply_prefix_if_blank(obj)
        obj.save()
        logger.info(f"机场{code} 坐标已写入 airport_info: lat={lat}, lon={lon}")
        return
    updates = []
    if obj.latitude is None or obj.longitude is None:
        obj.latitude = float(lat)
        obj.longitude = float(lon)
        updates.extend(['latitude', 'longitude'])
    if name and not (obj.airport_name or '').strip():
        obj.airport_name = name
        updates.append('airport_name')
    if apply_prefix_if_blank(obj):
        updates.extend(['classification', 'area'])
    if updates:
        obj.save(update_fields=list(dict.fromkeys(updates)))
        logger.info(f"机场{code} 空坐标或空名称已补写: lat={lat}, lon={lon}")


def resolve_airport_coords(codes):
    """
    按调用方给出的机场代码取坐标。
    返回 (coords, errors)：
      coords: {code: (lat, lon)}
      errors: 未能取得坐标的说明，每条对应一个机场
    只对本次请求里本地没有的机场访问接口，不巡检其他机场。
    """
    codes = _normalize_codes(codes)
    if not codes:
        return {}, []

    try:
        found = _read_local_coords(codes)
    except DatabaseError as exc:
        logger.warning(f"读取 airport_info 坐标失败，改为按需请求接口: {exc}")
        found = {}

    errors = []
    for code in codes:
        if code in found:
            continue
        try:
            info = fetch_aviationweather_airport(code)
            lat, lon = info['lat'], info['lon']
            if lat is None or lon is None:
                raise AirportCoordUnavailable(f"机场 {code} 的接口响应没有坐标")
            store_airport_coord(code, lat, lon, info.get('name'))
            found[code] = (float(lat), float(lon))
        except (requests.RequestException, ValueError, AirportCoordUnavailable, DatabaseError) as exc:
            message = f"未能获取机场 {code} 的坐标：{exc}"
            logger.error(message)
            errors.append(message)
    return found, errors
