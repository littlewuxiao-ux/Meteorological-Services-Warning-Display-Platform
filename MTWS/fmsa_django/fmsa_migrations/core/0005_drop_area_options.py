from django.db import migrations


def _drop_area_permission(apps, schema_editor):
    conn = schema_editor.connection
    if 'access_group_permission' not in conn.introspection.table_names():
        return
    Perm = apps.get_model('core', 'AccessGroupPermission')
    Perm.objects.using(conn.alias).filter(module_code='settings_area_options').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_prefix_sequence'),
    ]

    operations = [
        migrations.RunPython(_drop_area_permission, migrations.RunPython.noop),
        migrations.DeleteModel(name='AreaOptions'),
    ]
