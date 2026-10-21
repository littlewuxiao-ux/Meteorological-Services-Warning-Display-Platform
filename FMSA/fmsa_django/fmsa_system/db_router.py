"""配置库 default，生产库 runtime，口令库 access。按应用整库路由。"""

ACCESS_DB = 'access'

# 扫码登录还用 Django session。admin/auth/contenttypes 已从项目卸掉，禁止再迁进配置库。
DJANGO_APPS = {'sessions'}
DROPPED_DJANGO_APPS = {'admin', 'auth', 'contenttypes'}

APP_DATABASE = {
    'config_db': 'default',
    'runtime_db': 'runtime',
    'access_db': ACCESS_DB,
}


def database_for(app_label: str, model_name: str | None) -> str | None:
    if app_label in DJANGO_APPS:
        return 'default'
    return APP_DATABASE.get(app_label)


class FmsaRouter:
    def db_for_read(self, model, **hints):
        return database_for(model._meta.app_label, model._meta.model_name)

    def db_for_write(self, model, **hints):
        return database_for(model._meta.app_label, model._meta.model_name)

    def allow_relation(self, obj1, obj2, **hints):
        return database_for(obj1._meta.app_label, obj1._meta.model_name) == database_for(
            obj2._meta.app_label, obj2._meta.model_name
        )

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label in DROPPED_DJANGO_APPS:
            return False
        if app_label in DJANGO_APPS:
            return db == 'default'
        target = APP_DATABASE.get(app_label)
        if target:
            return db == target
        return False
