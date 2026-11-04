from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('config_db', '0002_rename_style_config'),
    ]

    operations = [
        migrations.CreateModel(
            name='HistoryStatsConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('user_code', models.CharField(max_length=12, unique=True, verbose_name='用户代码')),
                ('config', models.JSONField(default=dict, verbose_name='配置JSON')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
            ],
            options={
                'verbose_name': '历史天气统计配置',
                'verbose_name_plural': '历史天气统计配置',
                'db_table': 'history_stats_config',
            },
        ),
    ]
