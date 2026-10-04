"""
创建默认数据管理命令
用于创建默认机场阈值等必要数据
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import AirportAlertThresholds


class Command(BaseCommand):
    help = '创建默认数据'

    def handle(self, *args, **options):
        """命令执行入口"""
        
        self.create_default_airport_thresholds()
        
        self.stdout.write(
            self.style.SUCCESS('默认数据创建完成')
        )

    def create_default_airport_thresholds(self):
        """创建默认机场阈值"""
        
        try:
            with transaction.atomic():
                # 创建默认告警阈值
                default_thresholds, created = AirportAlertThresholds.objects.update_or_create(
                    airport_4code='default',
                    defaults={
                        'visibility_m_red': 800,
                        'visibility_m_yellow': 1600,
                        'visibility_m_green': 2000,
                        'cloud_min_red': 2,
                        'cloud_min_yellow': 5,
                        'cloud_min_green': 10,
                        'min_cloud_amt': 'SCT',
                        'average_wind_speed_mps_red': 12,
                        'average_wind_speed_mps_yellow': 8,
                        'average_wind_speed_mps_green': 5,
                        'gust_mps_red': 17,
                        'gust_mps_yellow': 13,
                        'gust_mps_green': 10,
                        'temperature_cold_red': -30,
                        'temperature_cold_yellow': -27,
                        'temperature_cold_green': -25,
                        'temperature_hot_red': 40,
                        'temperature_hot_yellow': 37,
                        'temperature_hot_green': 35,
                        'revision_history': '',
                    }
                )
                
                if created:
                    self.stdout.write(
                        self.style.SUCCESS('已创建默认机场阈值配置')
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING('默认机场阈值配置已存在，已更新')
                    )
                    
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'创建默认机场阈值失败: {str(e)}')
            )
