from django.db import migrations


def _drop_area_permission(apps, schema_editor):
    Perm = apps.get_model('core', 'AccessGroupPermission')
    Perm.objects.filter(module_code='settings_area_options').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_prefix_sequence'),
    ]

    operations = [
        migrations.RunPython(_drop_area_permission, migrations.RunPython.noop),
        migrations.DeleteModel(name='AreaOptions'),
    ]
