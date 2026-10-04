"""
API应用URL配置
提供REST API接口，支持不同时间模式
"""

from django.urls import path
from . import views
from .airport_extra_views import (
    airport_extra_info, airport_coords, airport_metar_history,
    airport_popup_metar_text, airport_report_text,
)
from .settings_views import (
    settings_airport_info, settings_airport_info_detail,
    settings_area_options, settings_area_options_detail,
    settings_data_refresh_timer, settings_data_refresh_timer_detail,
    settings_popup,
    settings_alert_thresholds, settings_alert_thresholds_detail,
    settings_weather_type, settings_weather_type_detail,
    settings_weather_alert, settings_weather_alert_detail,
    settings_airport_location, settings_airport_location_detail,
)
from .plain_views import plain_taf_batch, plain_metar_batch, plain_report_text
from .access_views import (
    access_bootstrap, access_session_status, access_select_role,
    access_complete_qr_login, access_seat_logout,
    access_admin_unlock, access_admin_lock, access_admin_change_password,
    access_admin_groups, access_admin_group_detail,
    access_admin_blacklist, access_admin_blacklist_detail,
)
from .radar_views import (
    radar_alert_config, radar_alert_status, radar_alert_run,
    radar_rebuild_tile_index, radar_alerts, radar_alert_handle, radar_echo,
)
from .map_style_views import map_style_config
from .trend_views import trend_alert_config, trend_alert_results, trend_alert_handle

app_name = 'api'

urlpatterns = [
    # 默认数据API（用于页面初始化）
    path('airports/overview/', views.airports_overview, name='airports_overview'),
    
    # 单个机场数据API
    path('airport/<str:airport_code>/history-reports/', views.airport_history_reports, name='airport_history_reports'),
    path('airport/<str:airport_code>/extra-info/', airport_extra_info, name='airport_extra_info'),
    path('airport/<str:airport_code>/metar-history/', airport_metar_history, name='airport_metar_history'),
    path('airport/<str:airport_code>/popup-metar-text/', airport_popup_metar_text, name='airport_popup_metar_text'),
    path('airport/<str:airport_code>/report-text/', airport_report_text, name='airport_report_text'),
    
    # 解析控制API
    path('trigger-parsing/', views.trigger_parsing, name='trigger_parsing'),
    path('parsing-status/', views.get_parsing_status, name='get_parsing_status'),
    path('running-parsers/', views.get_running_parsers, name='get_running_parsers'),
    
    # 鉴权相关API（仅用于current模式）
    path('auth/get-qrcode/', views.get_qrcode, name='get_qrcode'),
    path('auth/check-login/', views.check_login_status, name='check_login_status'),
    path('auth/logout/', views.logout, name='logout'),
    path('seat-identity/', views.seat_identity, name='seat_identity'),
    
    
    # Token验证API
    path('validate-token/', views.validate_token_status, name='validate_token_status'),
    
    # 定时器配置API
    path('timer-configs/', views.get_timer_configs, name='get_timer_configs'),
    
    # 弹窗API
    path('metar-popups/', views.get_metar_popups, name='get_metar_popups'),
    path('popup-received/', views.handle_popup_received, name='handle_popup_received'),
    path('popup-batch-ignore/', views.handle_popup_batch_ignore, name='handle_popup_batch_ignore'),
    path('popup-batch-received/', views.handle_popup_batch_received, name='handle_popup_batch_received'),

    # 实况入库告警API
    path('import-alerts/', views.get_import_alerts, name='get_import_alerts'),
    path('import-alerts/handle/', views.handle_import_alert, name='handle_import_alert'),

    # 预报入库告警API
    path('taf-import-alerts/', views.get_taf_import_alerts, name='get_taf_import_alerts'),
    path('taf-import-alerts/handle/', views.handle_taf_import_alert, name='handle_taf_import_alert'),

    # NWP 数值预报温度数据
    path('nwp-data/', views.get_nwp_data, name='get_nwp_data'),

    # 地图告警：机场坐标批量接口
    path('airport-coords/', airport_coords, name='airport_coords'),

    # 机场搜索接口（支持系统内/系统外机场）
    path('airport-search/', views.airport_search, name='airport_search'),

    # 地图告警：机场实况状态批量接口（Tooltip用）
    path('airport-flight-status/', views.get_airport_flight_status, name='airport_flight_status'),
    path('flight-carriers/', views.flight_carriers, name='flight_carriers'),

    # ===== 设置管理API =====
    path('settings/airport-info/', settings_airport_info, name='settings_airport_info'),
    path('settings/airport-info/<str:airport_4code>/', settings_airport_info_detail, name='settings_airport_info_detail'),
    path('settings/area-options/', settings_area_options, name='settings_area_options'),
    path('settings/area-options/<int:option_id>/', settings_area_options_detail, name='settings_area_options_detail'),
    path('settings/data-refresh-timer/', settings_data_refresh_timer, name='settings_data_refresh_timer'),
    path('settings/data-refresh-timer/<int:timer_id>/', settings_data_refresh_timer_detail, name='settings_data_refresh_timer_detail'),
    path('settings/popup/', settings_popup, name='settings_popup'),
    path('settings/alert-thresholds/', settings_alert_thresholds, name='settings_alert_thresholds'),
    path('settings/alert-thresholds/<str:airport_4code>/', settings_alert_thresholds_detail, name='settings_alert_thresholds_detail'),
    path('settings/weather-type/', settings_weather_type, name='settings_weather_type'),
    path('settings/weather-type/<int:type_id>/', settings_weather_type_detail, name='settings_weather_type_detail'),
    path('settings/weather-alert/', settings_weather_alert, name='settings_weather_alert'),
    path('settings/weather-alert/<int:alert_id>/', settings_weather_alert_detail, name='settings_weather_alert_detail'),
    path('settings/airport-location/', settings_airport_location, name='settings_airport_location'),
    path('settings/airport-location/<str:airport_4code>/', settings_airport_location_detail, name='settings_airport_location_detail'),

    # 中文（明语）模式
    path('plain/taf-batch/', plain_taf_batch, name='plain_taf_batch'),
    path('plain/metar-batch/', plain_metar_batch, name='plain_metar_batch'),
    path('plain/airport/<str:airport_code>/report-text/', plain_report_text, name='plain_report_text'),

    # 访问控制 / 超级用户
    path('access/bootstrap/', access_bootstrap, name='access_bootstrap'),
    path('access/session/', access_session_status, name='access_session_status'),
    path('access/select-role/', access_select_role, name='access_select_role'),
    path('access/complete-qr-login/', access_complete_qr_login, name='access_complete_qr_login'),
    path('access/seat-logout/', access_seat_logout, name='access_seat_logout'),
    path('access/admin/unlock/', access_admin_unlock, name='access_admin_unlock'),
    path('access/admin/lock/', access_admin_lock, name='access_admin_lock'),
    path('access/admin/change-password/', access_admin_change_password, name='access_admin_change_password'),
    path('access/admin/groups/', access_admin_groups, name='access_admin_groups'),
    path('access/admin/groups/<int:group_id>/', access_admin_group_detail, name='access_admin_group_detail'),
    path('access/admin/blacklist/', access_admin_blacklist, name='access_admin_blacklist'),
    path('access/admin/blacklist/<int:item_id>/', access_admin_blacklist_detail, name='access_admin_blacklist_detail'),

    # 雷达告警
    path('radar/config/', radar_alert_config, name='radar_alert_config'),
    path('radar/status/', radar_alert_status, name='radar_alert_status'),
    path('radar/run/', radar_alert_run, name='radar_alert_run'),
    path('radar/rebuild-index/', radar_rebuild_tile_index, name='radar_rebuild_tile_index'),
    path('radar/alerts/', radar_alerts, name='radar_alerts'),
    path('radar/alerts/handle/', radar_alert_handle, name='radar_alert_handle'),
    path('radar/echo/', radar_echo, name='radar_echo'),
    path('map-style/config/', map_style_config, name='map_style_config'),

    # 实况趋势告警
    path('trend-alert/config/', trend_alert_config, name='trend_alert_config'),
    path('trend-alert/results/', trend_alert_results, name='trend_alert_results'),
    path('trend-alert/handle/', trend_alert_handle, name='trend_alert_handle'),
] 