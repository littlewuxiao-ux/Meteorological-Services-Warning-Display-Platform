# 用户组、权限行、扫码黑名单不再使用。口令仍留在 access_setting。

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_access_setting'),
    ]

    operations = [
        migrations.DeleteModel(name='AccessGroupPermission'),
        migrations.DeleteModel(name='NonLocalQrBlacklist'),
        migrations.DeleteModel(name='AccessGroup'),
    ]
