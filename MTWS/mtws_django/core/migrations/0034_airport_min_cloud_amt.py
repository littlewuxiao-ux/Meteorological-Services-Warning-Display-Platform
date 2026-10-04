"""机场告警阈值增加计入云底高的最低云量，default 行为 SCT。"""

from django.db import migrations, models


def set_default_row_sct(apps, schema_editor):
    AirportAlertThresholds = apps.get_model('core', 'AirportAlertThresholds')
    AirportAlertThresholds.objects.filter(airport_4code='default').update(min_cloud_amt='SCT')


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0033_remove_settings_carrier'),
    ]

    operations = [
        migrations.AddField(
            model_name='airportalertthresholds',
            name='min_cloud_amt',
            field=models.CharField(
                choices=[('FEW', 'FEW'), ('SCT', 'SCT'), ('BKN', 'BKN'), ('OVC', 'OVC')],
                default='SCT',
                max_length=3,
                verbose_name='计入云底高的最低云量',
            ),
        ),
        migrations.RunPython(set_default_row_sct, migrations.RunPython.noop),
    ]
