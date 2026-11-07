from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('runtime_db', '0003_aircraft_parking_per_airport'),
    ]

    operations = [
        migrations.CreateModel(
            name='AircraftParkingSync',
            fields=[
                ('id', models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
                ('batch_fingerprint', models.CharField(blank=True, default='', max_length=64, verbose_name='整批指纹')),
                ('fetched_at', models.BigIntegerField(blank=True, null=True, verbose_name='航班数据获取时间')),
            ],
            options={
                'verbose_name': '飞机停场同步状态',
                'verbose_name_plural': '飞机停场同步状态',
                'db_table': 'aircraft_parking_sync',
            },
        ),
        migrations.CreateModel(
            name='AircraftParkingTail',
            fields=[
                ('ac_reg', models.CharField(max_length=16, primary_key=True, serialize=False, verbose_name='飞机注册号')),
                ('fingerprint', models.CharField(blank=True, default='', max_length=64, verbose_name='航班指纹')),
                ('segments', models.JSONField(blank=True, default=list, help_text='[[机场, 开始, 结束], ...]，进行中结束为 null', verbose_name='停场时段')),
            ],
            options={
                'verbose_name': '飞机停场机号记录',
                'verbose_name_plural': '飞机停场机号记录',
                'db_table': 'aircraft_parking_tail',
            },
        ),
    ]
