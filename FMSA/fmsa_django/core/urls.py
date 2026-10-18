"""
核心应用URL配置
包括系统管理、配置管理等接口
"""

from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # 系统状态和配置
    path('status/', views.system_status, name='system_status'),
    path('config/', views.system_config, name='system_config'),
    
    # 数据管理
    path('data/import/', views.import_data, name='import_data'),
    path('data/export/', views.export_data, name='export_data'),
    path('data/cleanup/', views.cleanup_data, name='cleanup_data'),
    
    # 解析任务管理
    path('parse/run/', views.run_parse, name='run_parse'),
    path('parse/status/', views.parse_status, name='parse_status'),
    path('parse/logs/', views.parse_logs, name='parse_logs'),
] 