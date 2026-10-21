"""
Web应用URL配置
提供前端页面访问，支持不同时间模式
"""

from django.urls import path
from . import views

app_name = 'web'

urlpatterns = [
    # 主页
    path('', views.index, name='index'),
    
    # 时间模式
    path('test/', views.test_time_mode, name='test_time_mode'),
    
    # 机场监控页面
    path('airports/', views.airports, name='airports'),
    path('airports/<str:airport_code>/', views.airport_detail, name='airport_detail'),
    
    # 搜索页面
    path('search/', views.search, name='search'),
    
    # 历史数据页面
    path('history/', views.history, name='history'),
    
    # 统计分析页面
    path('statistics/', views.statistics, name='statistics'),
    
    # 设置页面
    path('settings/', views.settings, name='settings'),
    
    # 系统管理页面
    path('admin/', views.admin_panel, name='admin_panel'),
    path('admin/config/', views.admin_config, name='admin_config'),
    path('admin/logs/', views.admin_logs, name='admin_logs'),
    
    # 解析状态检查页面
    path('parsing-status/', views.parsing_status, name='parsing_status'),
] 