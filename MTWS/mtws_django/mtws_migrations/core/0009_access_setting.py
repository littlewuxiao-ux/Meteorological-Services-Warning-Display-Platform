# 超管口令哈希从配置库 system_config 移到用户组库（搬迁见 utils.access_control.ensure_access_database）。

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0008_access_drop_activate'),
    ]

    operations = [
        migrations.CreateModel(
            name='AccessSetting',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(max_length=64, unique=True, verbose_name='键')),
                ('value', models.TextField(verbose_name='值')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
            ],
            options={
                'verbose_name': '用户组库配置',
                'verbose_name_plural': '用户组库配置',
                'db_table': 'access_setting',
            },
        ),
    ]
