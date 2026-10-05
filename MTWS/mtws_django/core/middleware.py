"""
时间模式中间件
处理当前时间模式和测试时间模式的切换
"""

from django.utils.deprecation import MiddlewareMixin


class TimeModelMiddleware(MiddlewareMixin):
    """时间模式中间件"""
    
    def process_request(self, request):
        """处理请求，提取时间模式"""
        # 从URL路径中提取时间模式
        path_parts = request.path.strip('/').split('/')
        
        if path_parts and path_parts[0] in ['current', 'test']:
            request.time_mode = path_parts[0]
        else:
            request.time_mode = 'current'  # 默认使用当前时间模式
        self._remember_local_duty_user(request)
        return None

    def _remember_local_duty_user(self, request):
        """本机当前登录用户就是入库用的那一个。测试页和没有工号的请求不覆盖。"""
        if getattr(request, 'time_mode', 'current') != 'current':
            return
        code = str(request.headers.get('X-User-Code') or '').strip()
        if not code or code in {'--', '-', 'system', 'scheduler', 'test', 'default'}:
            return
        try:
            from utils.access_control import is_local_request
            if not is_local_request(request):
                return
            from parsers.scheduler import set_scheduler_user_code
            set_scheduler_user_code(code)
        except Exception:
            return

    def process_response(self, request, response):
        """设置页和超级用户页上的操作把超级用户会话再顺延 5 分钟。"""
        path = request.path or ''
        touches = (
            '/api/settings/',
            '/api/radar/config',
            '/api/trend-alert/config',
            '/api/access/admin/',
        )
        if not any(part in path for part in touches):
            return response
        from utils.access_control import ADMIN_COOKIE, ADMIN_TTL_SECONDS, is_admin_unlocked
        if is_admin_unlocked(request, touch=True):
            sid = request.COOKIES.get(ADMIN_COOKIE)
            if sid:
                response.set_cookie(
                    ADMIN_COOKIE, sid, max_age=ADMIN_TTL_SECONDS,
                    httponly=True, samesite='Lax', path='/',
                )
        elif request.COOKIES.get(ADMIN_COOKIE):
            response.delete_cookie(ADMIN_COOKIE, path='/')
        return response
    
    def process_view(self, request, view_func, view_args, view_kwargs):
        """处理视图，将时间模式添加到view_kwargs中"""
        if hasattr(request, 'time_mode'):
            view_kwargs['time_mode'] = request.time_mode
        
        return None 