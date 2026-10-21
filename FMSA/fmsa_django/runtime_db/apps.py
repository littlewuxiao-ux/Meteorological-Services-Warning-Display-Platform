from django.apps import AppConfig


class RuntimeDbConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'runtime_db'
    verbose_name = '生产库'
