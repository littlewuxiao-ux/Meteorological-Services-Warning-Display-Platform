"""把现有三库接到按应用拆分后的初始迁移。配置和口令数据保留，生产库重建。"""

from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connections


OLD_APPS = ('core', 'parsers')


class Command(BaseCommand):
    help = '保留配置库、口令库数据；清空生产库；按新的初始迁移记账'

    def handle(self, *args, **options):
        connections.close_all()
        self._delete_runtime_files()
        self._drop_old_migration_rows('default')
        self._drop_old_migration_rows('access')
        self.stdout.write('配置库：按现有表记账')
        call_command(
            'migrate', 'config_db',
            database='default', fake_initial=True,
            verbosity=1, interactive=False,
        )
        self.stdout.write('口令库：按现有表记账')
        call_command(
            'migrate', 'access_db',
            database='access', fake_initial=True,
            verbosity=1, interactive=False,
        )
        self.stdout.write('生产库：新建表')
        call_command(
            'migrate', 'runtime_db',
            database='runtime',
            verbosity=1, interactive=False,
        )
        self.stdout.write(self.style.SUCCESS('已按库接上新的初始迁移。'))

    def _delete_runtime_files(self):
        path = Path(settings.DATABASES['runtime']['NAME'])
        connections.close_all()
        for item in (path, Path(str(path) + '-wal'), Path(str(path) + '-shm')):
            if item.exists():
                item.unlink()
                self.stdout.write(f'已删除 {item.name}')

    def _drop_old_migration_rows(self, alias):
        conn = connections[alias]
        with conn.cursor() as cursor:
            if 'django_migrations' not in conn.introspection.table_names():
                return
            cursor.execute(
                'DELETE FROM django_migrations WHERE app IN (%s, %s)',
                OLD_APPS,
            )
            self.stdout.write(f'{alias}: 已去掉 core/parsers 迁移记录')
        connections.close_all()
