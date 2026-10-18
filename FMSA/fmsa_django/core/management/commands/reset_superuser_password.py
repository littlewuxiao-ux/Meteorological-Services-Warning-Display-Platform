"""
重置超级用户口令：
  python manage.py reset_superuser_password
  python manage.py reset_superuser_password --password newpass
"""

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = '重置超级用户管理口令（仅本机部署应急使用）'

    def add_arguments(self, parser):
        parser.add_argument('--password', type=str, help='新口令（不传则交互输入）')

    def handle(self, *args, **options):
        from utils.access_control import set_superuser_password, ensure_bootstrap_data

        ensure_bootstrap_data()
        pw = options.get('password')
        if not pw:
            pw = input('请输入新的超级用户口令: ').strip()
            confirm = input('请再输入一次: ').strip()
            if pw != confirm:
                raise CommandError('两次输入不一致')
        if len(pw) < 6:
            raise CommandError('口令至少 6 位')
        set_superuser_password(pw)
        self.stdout.write(self.style.SUCCESS('超级用户口令已重置'))
