from django.db import migrations, models


def wipe_parking(apps, schema_editor):
    apps.get_model('runtime_db', 'AircraftParkingInfo').objects.all().delete()


def noop(apps, schema_editor):
    return


class Migration(migrations.Migration):

    dependencies = [
        ('runtime_db', '0002_metar_pressure_val'),
    ]

    operations = [
        migrations.RunPython(wipe_parking, noop),
        migrations.RemoveIndex(
            model_name='aircraftparkinginfo',
            name='aircraft_pa_parse_t_030956_idx',
        ),
        migrations.RemoveIndex(
            model_name='aircraftparkinginfo',
            name='aircraft_pa_airport_7ac2d6_idx',
        ),
        migrations.RemoveField(
            model_name='aircraftparkinginfo',
            name='parse_time',
        ),
        migrations.AddField(
            model_name='aircraftparkinginfo',
            name='parking',
            field=models.JSONField(default=list, help_text='[是否停场, ...飞机注册号]', verbose_name='当前停场'),
        ),
        migrations.AddField(
            model_name='aircraftparkinginfo',
            name='aircraft_parked_status_records',
            field=models.JSONField(blank=True, default=list, help_text='[[开始, 结束], ...]，进行中结束为 null', verbose_name='飞机停场状态记录'),
        ),
        migrations.AddField(
            model_name='aircraftparkinginfo',
            name='fetched_at',
            field=models.BigIntegerField(blank=True, null=True, verbose_name='航班数据获取时间'),
        ),
        migrations.AlterField(
            model_name='aircraftparkinginfo',
            name='airport_4code',
            field=models.CharField(max_length=4, unique=True, verbose_name='机场四字代码'),
        ),
        migrations.AlterModelOptions(
            name='aircraftparkinginfo',
            options={
                'ordering': ['-fetched_at'],
                'verbose_name': '飞机停场信息',
                'verbose_name_plural': '飞机停场信息',
            },
        ),
        migrations.AddIndex(
            model_name='aircraftparkinginfo',
            index=models.Index(fields=['fetched_at'], name='aircraft_pa_fetched_b2e9a1_idx'),
        ),
    ]
