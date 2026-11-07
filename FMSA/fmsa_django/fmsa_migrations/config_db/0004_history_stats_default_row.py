from django.db import migrations


def seed_history_stats_default(apps, schema_editor):
    HistoryStatsConfig = apps.get_model('config_db', 'HistoryStatsConfig')
    if HistoryStatsConfig.objects.filter(user_code='default').exists():
        return
    from utils.history_stats import default_config, normalize_config

    config, _errors = normalize_config(default_config(), default_config())
    HistoryStatsConfig.objects.create(user_code='default', config=config)


def unseed_history_stats_default(apps, schema_editor):
    HistoryStatsConfig = apps.get_model('config_db', 'HistoryStatsConfig')
    HistoryStatsConfig.objects.filter(user_code='default').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('config_db', '0003_history_stats_config'),
    ]

    operations = [
        migrations.RunPython(seed_history_stats_default, unseed_history_stats_default),
    ]
