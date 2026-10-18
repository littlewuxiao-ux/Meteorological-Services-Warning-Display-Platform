from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('parsers', '0002_drop_parse_log_and_login_record'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserAirportAlert',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('user_code', models.CharField(max_length=12, verbose_name='用户代码')),
                ('airport_4code', models.CharField(max_length=4, verbose_name='机场四字代码')),
                ('kind', models.CharField(max_length=8, verbose_name='metar或taf')),
                ('source_key', models.CharField(max_length=50, verbose_name='来源报文标识')),
                ('warnings', models.JSONField(default=dict, verbose_name='告警字段')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
            ],
            options={
                'verbose_name': '用户机场告警',
                'db_table': 'user_airport_alert',
                'unique_together': {('user_code', 'airport_4code', 'kind')},
            },
        ),
    ]
