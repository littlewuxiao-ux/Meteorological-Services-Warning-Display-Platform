from django.db import migrations, models


def _copy_sequence(apps, schema_editor):
    Prefix = apps.get_model('core', 'AirportPrefixArea')
    Area = apps.get_model('core', 'AreaOptions')
    lookup = {}
    for row in Area.objects.all():
        lookup[(row.classification, row.area)] = row.sequence
    for rule in Prefix.objects.all():
        sequence = lookup.get((rule.classification, rule.area))
        if sequence:
            rule.sequence = sequence
            rule.save(update_fields=['sequence'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_user_settings'),
    ]

    operations = [
        migrations.AddField(
            model_name='airportprefixarea',
            name='sequence',
            field=models.PositiveIntegerField(default=1, verbose_name='序号'),
        ),
        migrations.RunPython(_copy_sequence, migrations.RunPython.noop),
    ]
