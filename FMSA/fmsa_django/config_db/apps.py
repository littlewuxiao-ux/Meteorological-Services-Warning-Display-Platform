from django.apps import AppConfig


class ConfigDbConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'config_db'
    verbose_name = '配置库'
