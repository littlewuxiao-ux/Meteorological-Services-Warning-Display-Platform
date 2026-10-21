"""检查三个 SQLite 库是否完好。"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = '检查配置库、生产库、口令库的完整性'

    def handle(self, *args, **options):
        import sqlite3

        failed = []
        for alias, conf in settings.DATABASES.items():
            path = conf.get('NAME')
            self.stdout.write(f'[{alias}] {path}')
            if not path:
                continue
            from pathlib import Path
            p = Path(path)
            if not p.is_file():
                self.stdout.write(self.style.WARNING('  文件不存在'))
                failed.append(alias)
                continue
            wal = p.with_name(p.name + '-wal')
            shm = p.with_name(p.name + '-shm')
            self.stdout.write(
                f'  大小 {p.stat().st_size} 字节；'
                f'wal={"有" if wal.is_file() else "无"}；'
                f'shm={"有" if shm.is_file() else "无"}'
            )
            try:
                conn = sqlite3.connect(f'file:{p.as_posix()}?mode=ro', uri=True)
                result = conn.execute('PRAGMA integrity_check;').fetchone()[0]
                conn.close()
            except Exception as exc:
                result = str(exc)
            if result == 'ok':
                self.stdout.write(self.style.SUCCESS('  完好'))
            else:
                self.stdout.write(self.style.ERROR(f'  损坏：{result}'))
                failed.append(alias)
        if failed:
            raise CommandError(
                '损坏的库：' + '、'.join(failed)
                + '。先退出 FMSA，用完好备份覆盖对应 .db，并一并覆盖同名的 .db-wal、.db-shm；'
                '或从完好机器执行 snapshot_sqlite 后再拷贝。'
            )
        self.stdout.write(self.style.SUCCESS('全部完好'))
