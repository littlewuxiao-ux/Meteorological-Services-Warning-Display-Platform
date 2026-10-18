"""
立即跑一轮雷达告警（调试用）:
  python manage.py run_radar_alert
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Run one RainViewer radar alert pipeline cycle'

    def add_arguments(self, parser):
        parser.add_argument('--sync', action='store_true', help='Run in foreground')

    def handle(self, *args, **options):
        from utils.radar import trigger_radar_job, get_radar_job_status
        from utils.radar.pipeline import RadarAlertPipeline

        if options.get('sync'):
            self.stdout.write('Running radar pipeline synchronously...')
            result = RadarAlertPipeline().run()
            self.stdout.write(self.style.SUCCESS(str(result)))
            return

        st = trigger_radar_job(force=False)
        self.stdout.write(self.style.SUCCESS(f'Triggered: {st}'))
        self.stdout.write('Poll status via /api/radar/status/')
