"""合并机场坐标到 airport_info，拆出预报入库配置和前缀区域，华东不再拆分。"""

from django.db import migrations, models


def _match_prefix(code, seed):
    airport = (code or '').upper()
    for prefix, classification, area, _remark in sorted(seed, key=lambda item: len(item[0]), reverse=True):
        if prefix and airport.startswith(prefix):
            return classification, area
    return None, None


def forwards(apps, schema_editor):
    AirportInfo = apps.get_model('core', 'AirportInfo')
    AirportLocation = apps.get_model('core', 'AirportLocation')
    AreaOptions = apps.get_model('core', 'AreaOptions')
    TafConfig = apps.get_model('core', 'AirportTafImportConfig')
    PrefixArea = apps.get_model('core', 'AirportPrefixArea')
    AccessGroupPermission = apps.get_model('core', 'AccessGroupPermission')

    AirportInfo.objects.filter(area__in=['沪浙闽', '苏皖鲁']).update(area='华东')
    removed, _details = AreaOptions.objects.filter(
        classification='国内', area__in=['沪浙闽', '苏皖鲁']
    ).delete()
    if removed and not AreaOptions.objects.filter(classification='国内', area='华东').exists():
        AreaOptions.objects.create(classification='国内', sequence=3, area='华东')
    if removed:
        for row in AreaOptions.objects.filter(classification='国内', sequence__gte=5).order_by('sequence'):
            row.sequence = row.sequence - 1
            row.save(update_fields=['sequence'])

    for info in AirportInfo.objects.exclude(airport_4code='default'):
        TafConfig.objects.update_or_create(
            airport_4code=info.airport_4code,
            defaults={
                'taf_init_time': info.taf_init_time,
                'import_check_interval': info.import_check_interval,
                'taf_max_delay': info.taf_max_delay,
            },
        )
        info.taf_infer_attempted = True
        info.save(update_fields=['taf_infer_attempted'])

    from core.prefix_areas import PREFIX_SEED

    existing = set(AirportInfo.objects.values_list('airport_4code', flat=True))
    pending = []
    for loc in AirportLocation.objects.all().iterator():
        code = loc.airport_4code
        if code == 'default':
            continue
        if code in existing:
            AirportInfo.objects.filter(airport_4code=code).update(
                latitude=loc.latitude,
                longitude=loc.longitude,
            )
            continue
        classification, area = _match_prefix(code, PREFIX_SEED)
        pending.append(AirportInfo(
            airport_4code=code,
            airport_name=loc.airport_name,
            latitude=loc.latitude,
            longitude=loc.longitude,
            classification=classification,
            area=area,
            catalog_only=True,
            taf_infer_attempted=False,
        ))
        if len(pending) >= 500:
            AirportInfo.objects.bulk_create(pending, batch_size=500)
            pending.clear()
    if pending:
        AirportInfo.objects.bulk_create(pending, batch_size=500)

    AirportInfo.objects.filter(airport_4code='default').delete()

    for info in AirportInfo.objects.all().iterator():
        if (info.classification or '').strip() and (info.area or '').strip():
            continue
        classification, area = _match_prefix(info.airport_4code, PREFIX_SEED)
        changed = []
        if classification and not (info.classification or '').strip():
            info.classification = classification
            changed.append('classification')
        if area and not (info.area or '').strip():
            info.area = area
            changed.append('area')
        if changed:
            info.save(update_fields=changed)

    for prefix, classification, area, remark in PREFIX_SEED:
        PrefixArea.objects.update_or_create(
            prefix=prefix,
            defaults={'classification': classification, 'area': area, 'remark': remark},
        )

    for module in ('settings_prefix_area', 'settings_taf_import'):
        for src in AccessGroupPermission.objects.filter(module_code='settings_airport_info'):
            AccessGroupPermission.objects.update_or_create(
                group_id=src.group_id,
                module_code=module,
                defaults={
                    'can_display': src.can_display,
                    'can_activate': src.can_activate,
                    'can_write': src.can_write,
                },
            )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0034_airport_min_cloud_amt'),
    ]

    operations = [
        migrations.CreateModel(
            name='AirportPrefixArea',
            fields=[
                ('prefix', models.CharField(max_length=4, primary_key=True, serialize=False, verbose_name='前缀')),
                ('classification', models.CharField(max_length=10, verbose_name='性质')),
                ('area', models.CharField(max_length=20, verbose_name='区域')),
                ('remark', models.TextField(blank=True, default='', verbose_name='备注')),
            ],
            options={
                'verbose_name': '前缀区域',
                'verbose_name_plural': '前缀区域',
                'db_table': 'airport_prefix_area',
                'ordering': ['prefix'],
            },
        ),
        migrations.CreateModel(
            name='AirportTafImportConfig',
            fields=[
                ('airport_4code', models.CharField(max_length=4, primary_key=True, serialize=False, verbose_name='机场四字代码')),
                ('taf_init_time', models.SmallIntegerField(blank=True, null=True, verbose_name='首份预报发布整点')),
                ('import_check_interval', models.SmallIntegerField(blank=True, null=True, verbose_name='发布间隔小时')),
                ('taf_max_delay', models.SmallIntegerField(blank=True, null=True, verbose_name='接收延迟分钟')),
            ],
            options={
                'verbose_name': '预报入库配置',
                'verbose_name_plural': '预报入库配置',
                'db_table': 'airport_taf_import_config',
            },
        ),
        migrations.AddField(
            model_name='airportinfo',
            name='latitude',
            field=models.FloatField(blank=True, null=True, verbose_name='纬度（十进制度）'),
        ),
        migrations.AddField(
            model_name='airportinfo',
            name='longitude',
            field=models.FloatField(blank=True, null=True, verbose_name='经度（十进制度）'),
        ),
        migrations.AddField(
            model_name='airportinfo',
            name='catalog_only',
            field=models.BooleanField(default=False, verbose_name='仅坐标目录'),
        ),
        migrations.AddField(
            model_name='airportinfo',
            name='taf_infer_attempted',
            field=models.BooleanField(default=False, verbose_name='已尝试推断预报入库配置'),
        ),
        migrations.RunPython(forwards, migrations.RunPython.noop),
        migrations.RemoveField(model_name='airportinfo', name='taf_init_time'),
        migrations.RemoveField(model_name='airportinfo', name='import_check_interval'),
        migrations.RemoveField(model_name='airportinfo', name='taf_max_delay'),
        migrations.DeleteModel(name='AirportLocation'),
    ]
