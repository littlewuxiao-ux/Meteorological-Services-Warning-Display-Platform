# 运行类、停场类、降级免打扰改为按用户保存。

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_prefix_area_ordering'),
    ]

    operations = [
        migrations.AddField(
            model_name='popupsettings',
            name='operation_enabled',
            field=models.BooleanField(default=True, verbose_name='运行类弹窗'),
        ),
        migrations.AddField(
            model_name='popupsettings',
            name='parking_enabled',
            field=models.BooleanField(default=True, verbose_name='停场类弹窗'),
        ),
        migrations.AddField(
            model_name='popupsettings',
            name='intercept_enabled',
            field=models.BooleanField(default=True, verbose_name='降级免打扰'),
        ),
    ]
