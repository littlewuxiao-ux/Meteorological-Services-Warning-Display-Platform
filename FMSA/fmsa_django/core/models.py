"""模型已按库拆到 config_db / runtime_db / access_db。这里只转接旧引用。"""

from access_db.models import AccessSetting
from config_db.models import (
    AirportAlertThresholds,
    AirportInfo,
    AirportPrefixArea,
    AirportTafImportConfig,
    Carrier,
    DataRefreshTimer,
    MapStyleConfig,
    PopupSettings,
    RadarAlertConfig,
    SystemConfig,
    TrendAlertConfig,
    WeatherAlertLevels,
    WeatherTypeInfo,
)
from runtime_db.models import (
    AircraftParkingInfo,
    AirportRadarAlert,
    AirportTrendAlert,
    RadarJobRun,
    RadarTileIndex,
    WxmsgImportAlert,
)

__all__ = [
    'AccessSetting',
    'AircraftParkingInfo',
    'AirportAlertThresholds',
    'AirportInfo',
    'AirportPrefixArea',
    'AirportRadarAlert',
    'AirportTafImportConfig',
    'AirportTrendAlert',
    'Carrier',
    'DataRefreshTimer',
    'MapStyleConfig',
    'PopupSettings',
    'RadarAlertConfig',
    'RadarJobRun',
    'RadarTileIndex',
    'SystemConfig',
    'TrendAlertConfig',
    'WeatherAlertLevels',
    'WeatherTypeInfo',
    'WxmsgImportAlert',
]
