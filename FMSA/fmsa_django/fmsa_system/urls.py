"""fmsa_system URL Configuration

项目主要URL配置，支持两种时间模式：
- current/ : 当前时间模式 
- test/ : 测试时间模式
"""

from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from web.views import system_reference_pdf

urlpatterns = [
    # 根路径重定向到当前时间模式
    path('', RedirectView.as_view(url='/current/', permanent=False)),
    path('docs/FMSA-System-Reference.pdf', system_reference_pdf, name='system_reference_pdf'),
    path('docs/MTWS-System-Reference.pdf', system_reference_pdf),
    
    # 当前时间模式路由
    path('current/', include([
        path('', include('web.urls')),  # 前端页面
        path('api/', include('api.urls')),  # API接口
    ]), kwargs={'time_mode': 'current'}),
    
    # 测试时间模式路由  
    path('test/', include([
        path('', include('web.urls')),  # 前端页面
        path('api/', include('api.urls')),  # API接口
    ]), kwargs={'time_mode': 'test'}),
    
    # 系统配置和管理接口（不区分时间模式）
    path('system/', include('core.urls')),
]

# 开发环境下服务静态文件和媒体文件
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
