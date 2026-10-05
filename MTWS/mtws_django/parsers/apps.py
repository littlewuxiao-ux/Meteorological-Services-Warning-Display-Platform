import os
import sys

from django.apps import AppConfig


class ParsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'parsers'

    def ready(self):
        # Django 开发服务器（runserver）会启动两个进程：
        #   1. reloader 监视进程（父进程，RUN_MAIN 未设置）
        #   2. 主工作进程（子进程，Django 自动设置 RUN_MAIN=true）
        # ready() 在两个进程中都会被调用，若不加判断，APScheduler 会启动两份，
        # 导致两个并发 _run_import_alert_check 互相竞争，将所有机场错误标记为告警。
        #
        # 解决方案：仅在 runserver 模式且为 reloader 父进程时跳过。
        # 生产环境（gunicorn/uWSGI）不使用 runserver，RUN_MAIN 不存在，调度器照常启动。
        if os.environ.get('MTWS_SKIP_SCHEDULER') == '1':
            return
        is_runserver = len(sys.argv) > 1 and sys.argv[1] == 'runserver'
        is_reloader_process = os.environ.get('RUN_MAIN') != 'true'
        if is_runserver and is_reloader_process:
            return
        from parsers.scheduler import start_scheduler
        start_scheduler()
