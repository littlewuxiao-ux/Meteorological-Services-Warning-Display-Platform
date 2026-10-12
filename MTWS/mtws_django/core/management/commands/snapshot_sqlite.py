"""把正在用的 SQLite 导出成可安全拷贝的干净文件（VACUUM INTO，不含 WAL）。"""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connections


class Command(BaseCommand):
    help = '导出干净的 SQLite 快照，复制该文件即可，不必再带 .db-wal / .db-shm'

    def add_arguments(self, parser):
        parser.add_argument(
            'alias',
            nargs='?',
            default='access',
            choices=sorted(settings.DATABASES.keys()),
            help='要导出的库：access=用户组库，default=配置库，runtime=生产库',
        )
        parser.add_argument(
            '-o', '--output',
            help='输出路径；默认写到原库同目录，文件名加 .portable.db',
        )

    def handle(self, *args, **options):
        alias = options['alias']
        src = Path(settings.DATABASES[alias]['NAME'])
        dest = Path(options['output']) if options.get('output') else src.with_name(f'{src.stem}.portable.db')
        dest = dest.resolve()
        if dest.exists():
            dest.unlink()
        dest.parent.mkdir(parents=True, exist_ok=True)

        conn = connections[alias]
        conn.ensure_connection()
        raw = conn.connection
        raw.execute('PRAGMA wal_checkpoint(TRUNCATE);')
        raw.execute('VACUUM INTO ?', (str(dest),))

        self.stdout.write(self.style.SUCCESS(
            f'已导出 {alias} → {dest}\n'
            '复制这个文件时先停掉目标机上的 MTWS，再覆盖对应的 .db，并删掉同名的 .db-wal、.db-shm。'
        ))
        return str(dest)
