"""carrier 表去掉 is_active。原先未启用的行删除，表中剩余代码都生效。"""

from django.db import migrations


def drop_inactive(apps, schema_editor):
    Carrier = apps.get_model('core', 'Carrier')
    Carrier.objects.filter(is_active=False).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0035_merge_airport_directory'),
    ]

    operations = [
        migrations.RunPython(drop_inactive, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='carrier',
            name='is_active',
        ),
    ]
