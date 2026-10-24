from django.db import migrations, models


def fill_metar_pressure(apps, schema_editor):
    Metar = apps.get_model('runtime_db', 'Metar')
    from parsers.metar_pressure import pressure_hpa_from_content, pressure_hpa_from_elements

    batch = []
    for row in Metar.objects.all().iterator():
        if row.metar_pressure_val is not None:
            continue
        value = pressure_hpa_from_content(row.metar_content or '')
        if value is None:
            value = pressure_hpa_from_elements(row.metar_elements)
        if value is None:
            continue
        row.metar_pressure_val = value
        batch.append(row)
        if len(batch) >= 200:
            Metar.objects.bulk_update(batch, ['metar_pressure_val'])
            batch = []
    if batch:
        Metar.objects.bulk_update(batch, ['metar_pressure_val'])


def noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):

    dependencies = [
        ('runtime_db', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='metar',
            name='metar_pressure_val',
            field=models.FloatField(blank=True, null=True, verbose_name='气压值'),
        ),
        migrations.RunPython(fill_metar_pressure, noop_reverse),
    ]
