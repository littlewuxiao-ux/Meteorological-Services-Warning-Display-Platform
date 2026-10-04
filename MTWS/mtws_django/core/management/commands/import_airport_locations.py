"""
管理命令：import_airport_locations
从 airport_loc.csv（GBK 编码）把机场坐标写入 airport_info。
已有机场只补经纬度，不覆盖名称。新机场记为坐标目录。

用法：
  python manage.py import_airport_locations
"""

import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.airport_directory import apply_prefix_if_blank
from core.models import AirportInfo


_CSV_PATH = (
    Path(__file__).resolve()
    .parent.parent.parent.parent.parent  # 工作区根目录
    / 'data' / 'sqlite_database' / 'airport_loc.csv'
)


def _dms_to_decimal(dms_str: str):
    """
    DMS 格式坐标 → 十进制度数，解析失败返回 None。

    格式：
      纬度  N/S + DDMMSSFF  （8 位数字，FF 为秒的百分之一）
      经度  E/W + DDDMMSSFF （9 位数字）
    """
    if not dms_str or len(dms_str) < 7:
        return None
    direction = dms_str[0].upper()
    digits = dms_str[1:]
    try:
        if direction in ('N', 'S'):
            d = int(digits[0:2])
            m = int(digits[2:4])
            s = int(digits[4:6])
            f = int(digits[6:8]) if len(digits) >= 8 else 0
        elif direction in ('E', 'W'):
            d = int(digits[0:3])
            m = int(digits[3:5])
            s = int(digits[5:7])
            f = int(digits[7:9]) if len(digits) >= 9 else 0
        else:
            return None
        decimal = d + m / 60.0 + (s + f / 100.0) / 3600.0
        if direction in ('S', 'W'):
            decimal = -decimal
        return round(decimal, 6)
    except (ValueError, IndexError):
        return None


class Command(BaseCommand):
    help = '从 airport_loc.csv 把机场坐标写入 airport_info'

    def add_arguments(self, parser):
        parser.add_argument(
            '--csv',
            type=str,
            default=str(_CSV_PATH),
            help=f'CSV 文件路径（默认：{_CSV_PATH}）',
        )

    def handle(self, *args, **options):
        csv_path = Path(options['csv'])
        if not csv_path.exists():
            raise CommandError(f'CSV 文件未找到：{csv_path}')

        seen_codes = set()
        skipped_invalid = 0
        skipped_dup = 0
        created = 0
        updated = 0

        with open(csv_path, newline='', encoding='gbk', errors='replace') as f:
            reader = csv.DictReader(f)
            for row in reader:
                code = row.get('CODE_ICAO', '').strip().upper()
                if not code or len(code) != 4:
                    skipped_invalid += 1
                    continue
                if code in seen_codes:
                    skipped_dup += 1
                    continue

                lat = _dms_to_decimal(row.get('GEO_LAT', '').strip())
                lon = _dms_to_decimal(row.get('GEO_LONG', '').strip())
                if lat is None or lon is None:
                    skipped_invalid += 1
                    continue

                seen_codes.add(code)
                name = row.get('TXT_NAME', '').strip() or None
                existing = AirportInfo.objects.filter(airport_4code=code).first()
                if existing:
                    existing.latitude = lat
                    existing.longitude = lon
                    existing.save(update_fields=['latitude', 'longitude'])
                    updated += 1
                    continue
                airport = AirportInfo(
                    airport_4code=code,
                    latitude=lat,
                    longitude=lon,
                    airport_name=name,
                    catalog_only=True,
                )
                apply_prefix_if_blank(airport)
                airport.save()
                created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'导入完成：新增 {created} 条，更新坐标 {updated} 条 | '
                f'无效/坐标缺失 {skipped_invalid} 条 | '
                f'文件内重复 {skipped_dup} 条'
            )
        )
