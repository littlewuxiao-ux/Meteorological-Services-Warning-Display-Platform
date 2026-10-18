from django.apps import AppConfig
from django.db.backends.signals import connection_created
from django.db.utils import DatabaseError


def _configure_sqlite(sender, connection, **kwargs):
    """WAL 下读者不必等写者结束。busy_timeout 与连接 timeout 同为 30 秒。"""
    if connection.vendor != 'sqlite':
        return
    db_path = connection.settings_dict.get('NAME')
    alias = getattr(connection, 'alias', '')
    try:
        with connection.cursor() as cursor:
            cursor.execute('PRAGMA journal_mode=WAL;')
            cursor.execute('PRAGMA synchronous=NORMAL;')
            cursor.execute('PRAGMA busy_timeout=30000;')
    except DatabaseError as exc:
        raise DatabaseError(
            f'SQLite 无法打开「{alias}」：{db_path}\n'
            f'原错误：{exc}\n'
            '请先完全退出本机和目标机上的 FMSA。复制库文件时须同时带上同名的 .db-wal、.db-shm；'
            '更稳妥的做法是停服务后执行 python manage.py snapshot_sqlite，再拷生成的干净文件。'
        ) from exc


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        connection_created.connect(_configure_sqlite, dispatch_uid='mtws_sqlite_wal')
