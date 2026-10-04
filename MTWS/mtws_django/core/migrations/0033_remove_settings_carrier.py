"""承运人改由主页勾选，去掉设置页权限。"""

from django.db import migrations


def forwards(apps, schema_editor):
    Perm = apps.get_model('core', 'AccessGroupPermission')
    Perm.objects.filter(module_code='settings_carrier').delete()


def backwards(apps, schema_editor):
    AccessGroup = apps.get_model('core', 'AccessGroup')
    Perm = apps.get_model('core', 'AccessGroupPermission')
    for group in AccessGroup.objects.all():
        if Perm.objects.filter(group=group, module_code='settings_carrier').exists():
            continue
        Perm.objects.create(
            group=group,
            module_code='settings_carrier',
            can_display=bool(group.is_local),
            can_activate=False,
            can_write=bool(group.is_local),
        )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0032_access_layout'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
