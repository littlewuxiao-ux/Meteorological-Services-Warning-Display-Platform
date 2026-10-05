# 配置按用户分开。已有数据归到 default；承运人模板固定为 O3。

from django.db import migrations, models


def _collapse_carrier(apps, schema_editor):
    Carrier = apps.get_model('core', 'Carrier')
    Carrier.objects.all().delete()
    Carrier.objects.create(user_code='default', codes=['O3'], carrier_code='O3')


def _collapse_timer(apps, schema_editor):
    Timer = apps.get_model('core', 'DataRefreshTimer')
    config = {}
    rows = list(Timer.objects.all())
    for row in rows:
        config[row.data] = {'init_time': row.init_time, 'interval': row.interval}
    if rows:
        keep = rows[0]
        keep.user_code = 'default'
        keep.config = config
        keep.save(update_fields=['user_code', 'config'])
        Timer.objects.exclude(pk=keep.pk).delete()
    else:
        Timer.objects.create(
            user_code='default', config={}, data='metar', init_time=0, interval=5,
        )


def _keep_first_user(apps, model_name):
    Model = apps.get_model('core', model_name)
    rows = list(Model.objects.order_by('id'))
    if not rows:
        return
    first = rows[0]
    first.user_code = 'default'
    first.save(update_fields=['user_code'])
    Model.objects.exclude(pk=first.pk).delete()


def _mark_radar(apps, schema_editor):
    _keep_first_user(apps, 'RadarAlertConfig')


def _mark_trend(apps, schema_editor):
    _keep_first_user(apps, 'TrendAlertConfig')


def _rebuild_thresholds(apps, schema_editor):
    quoted = schema_editor.quote_name
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        cursor.execute('PRAGMA table_info(airport_alert_thresholds)')
        info = [row for row in cursor.fetchall() if row[1] != 'id']
        pieces = []
        for row in info:
            name, col_type, notnull = row[1], row[2] or 'TEXT', row[3]
            if name == 'user_code':
                col_type, notnull = 'varchar(12)', 1
            pieces.append(f'{quoted(name)} {col_type} {"NOT NULL" if notnull else "NULL"}')
        cursor.execute(
            'CREATE TABLE airport_alert_thresholds_new ('
            'id integer NOT NULL PRIMARY KEY AUTOINCREMENT, '
            + ', '.join(pieces)
            + ', UNIQUE (user_code, airport_4code))'
        )
        names = ', '.join(quoted(row[1]) for row in info)
        cursor.execute(
            f'INSERT INTO airport_alert_thresholds_new ({names}) '
            f'SELECT {names} FROM airport_alert_thresholds'
        )
        cursor.execute('DROP TABLE airport_alert_thresholds')
        cursor.execute('ALTER TABLE airport_alert_thresholds_new RENAME TO airport_alert_thresholds')


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_drop_parse_log_and_login_record'),
    ]

    operations = [
        migrations.AddField(
            model_name='airportalertthresholds',
            name='user_code',
            field=models.CharField(default='default', max_length=12, verbose_name='用户代码'),
            preserve_default=False,
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='airportalertthresholds',
                    name='id',
                    field=models.AutoField(primary_key=True, serialize=False),
                ),
                migrations.AlterField(
                    model_name='airportalertthresholds',
                    name='airport_4code',
                    field=models.CharField(max_length=4, verbose_name='机场四字代码'),
                ),
                migrations.AlterUniqueTogether(
                    name='airportalertthresholds',
                    unique_together={('user_code', 'airport_4code')},
                ),
            ],
            database_operations=[
                migrations.RunPython(_rebuild_thresholds, migrations.RunPython.noop),
            ],
        ),
        migrations.AddField(
            model_name='weatheralertlevels',
            name='user_code',
            field=models.CharField(default='default', max_length=12, verbose_name='用户代码'),
            preserve_default=False,
        ),
        migrations.AlterUniqueTogether(
            name='weatheralertlevels',
            unique_together={('user_code', 'weather', 'alert_level')},
        ),
        migrations.AddField(
            model_name='carrier',
            name='user_code',
            field=models.CharField(max_length=12, null=True, verbose_name='用户代码'),
        ),
        migrations.AddField(
            model_name='carrier',
            name='codes',
            field=models.JSONField(null=True, verbose_name='二字代码列表'),
        ),
        migrations.RunPython(_collapse_carrier, migrations.RunPython.noop),
        migrations.RemoveField(model_name='carrier', name='carrier_code'),
        migrations.RemoveField(model_name='carrier', name='carrier_name'),
        migrations.AlterField(
            model_name='carrier',
            name='user_code',
            field=models.CharField(max_length=12, unique=True, verbose_name='用户代码'),
        ),
        migrations.AlterField(
            model_name='carrier',
            name='codes',
            field=models.JSONField(default=list, verbose_name='二字代码列表'),
        ),
        migrations.AddField(
            model_name='datarefreshtimer',
            name='user_code',
            field=models.CharField(max_length=12, null=True, verbose_name='用户代码'),
        ),
        migrations.AddField(
            model_name='datarefreshtimer',
            name='config',
            field=models.JSONField(null=True, verbose_name='刷新配置'),
        ),
        migrations.RunPython(_collapse_timer, migrations.RunPython.noop),
        migrations.RemoveField(model_name='datarefreshtimer', name='data'),
        migrations.RemoveField(model_name='datarefreshtimer', name='init_time'),
        migrations.RemoveField(model_name='datarefreshtimer', name='interval'),
        migrations.AlterField(
            model_name='datarefreshtimer',
            name='user_code',
            field=models.CharField(max_length=12, unique=True, verbose_name='用户代码'),
        ),
        migrations.AlterField(
            model_name='datarefreshtimer',
            name='config',
            field=models.JSONField(default=dict, verbose_name='刷新配置'),
        ),
        migrations.AddField(
            model_name='radaralertconfig',
            name='user_code',
            field=models.CharField(default='default', max_length=12, verbose_name='用户代码'),
            preserve_default=False,
        ),
        migrations.RunPython(_mark_radar, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='radaralertconfig',
            name='user_code',
            field=models.CharField(max_length=12, unique=True, verbose_name='用户代码'),
        ),
        migrations.AddField(
            model_name='trendalertconfig',
            name='user_code',
            field=models.CharField(default='default', max_length=12, verbose_name='用户代码'),
            preserve_default=False,
        ),
        migrations.RunPython(_mark_trend, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='trendalertconfig',
            name='user_code',
            field=models.CharField(max_length=12, unique=True, verbose_name='用户代码'),
        ),
    ]
