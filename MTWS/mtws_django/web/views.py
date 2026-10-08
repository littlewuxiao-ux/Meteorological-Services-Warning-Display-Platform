"""
Web应用视图
提供前端页面渲染
"""

from pathlib import Path

from django.shortcuts import render
from django.http import FileResponse, Http404, HttpResponse
import json
from utils.flight_selection import selected_carrier_codes, sort_carrier_codes
from utils.time_manager import TimeManager
from django.conf import settings as django_settings


def index(request, time_mode='current'):
    """主页"""
    # 获取时间模式（从URL参数或默认为current）
    time_mode = request.GET.get('time_mode', time_mode)
    
    # 已选承运人，打开页面时从 carrier 表读取
    carriers = sort_carrier_codes(selected_carrier_codes())
    
    # 获取测试时间（如果是测试模式）
    test_time_iso = None
    if time_mode == 'test':
        test_time_iso = TimeManager.get_test_time_iso_string()
    
    # 获取弹窗图表配置
    popup_config = django_settings.MTWS_CONFIG.get('POPUP_CONFIG', {})
    chart_default_hours = popup_config.get('CHART_DEFAULT_HOURS', 3)
    
    context = {
        'time_mode': time_mode,
        'carriers': json.dumps(carriers),  # 转换为JSON字符串传递给前端
        'carrier_label': ' '.join(carriers),
        'test_time_iso': test_time_iso,  # 传递测试时间给前端
        'chart_default_hours': chart_default_hours,  # 传递图表默认小时数给前端
    }
    
    return render(request, 'web/index.html', context)


def airports(request, time_mode='current'):
    """机场监控页面"""
    # 目前重定向到主页
    return index(request, time_mode)


def airport_detail(request, airport_code):
    """机场详情页面"""
    time_mode = request.GET.get('time_mode', 'current')
    
    context = {
        'airport_code': airport_code,
        'time_mode': time_mode,
    }
    
    return render(request, 'web/airport_detail.html', context)


def search(request):
    """搜索页面"""
    time_mode = request.GET.get('time_mode', 'current')
    
    context = {
        'time_mode': time_mode,
    }
    
    return render(request, 'web/search.html', context)


def history(request):
    """历史数据页面"""
    time_mode = request.GET.get('time_mode', 'current')
    
    context = {
        'time_mode': time_mode,
    }
    
    return render(request, 'web/history.html', context)


def statistics(request):
    """统计分析页面"""
    time_mode = request.GET.get('time_mode', 'current')
    
    context = {
        'time_mode': time_mode,
    }
    
    return render(request, 'web/statistics.html', context)


def admin_panel(request):
    """管理面板"""
    return render(request, 'web/admin_panel.html')


def admin_config(request):
    """管理配置"""
    return render(request, 'web/admin_config.html')


def admin_logs(request):
    """管理日志"""
    return render(request, 'web/admin_logs.html')


def settings(request):
    """设置页面"""
    return render(request, 'web/settings.html')


def test_time_mode(request):
    """测试时间模式页面"""
    return index(request, time_mode='test')


def parsing_status(request, time_mode='current'):
    """解析状态检查页面"""
    return render(request, 'web/parsing_status.html', {
        'time_mode': time_mode,
        'page_title': '解析状态检查 - MTWS'
    })


def access_admin(request, time_mode='current'):
    """超级用户管理独立页"""
    return render(request, 'web/access_admin.html', {'time_mode': time_mode})


def system_reference_pdf(request):
    """在浏览器新标签中打开 docs/MTWS-System-Reference.pdf。"""
    docs_dir = Path(django_settings.BASE_DIR).parent / 'docs'
    for name in ('MTWS-System-Reference.pdf', 'MTWS System Reference.pdf'):
        pdf_path = docs_dir / name
        if pdf_path.is_file():
            break
    else:
        raise Http404('未找到说明文档：docs/MTWS-System-Reference.pdf')
    return FileResponse(
        pdf_path.open('rb'),
        content_type='application/pdf',
        as_attachment=False,
        filename='MTWS-System-Reference.pdf',
    )
