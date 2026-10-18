"""配置库 default，生产库 runtime，用户组库 access。"""

CONFIG_MODELS = {
    'airportinfo',
    'airportalertthresholds',
    'areaoptions',
    'weatheralertlevels',
    'carrier',
    'systemconfig',
    'datarefreshtimer',
    'popupsettings',
    'weathertypeinfo',
    'airporttafimportconfig',
    'airportprefixarea',
    'radaralertconfig',
    'mapstyleconfig',
    'trendalertconfig',
}

RUNTIME_CORE_MODELS = {
    'aircraftparkinginfo',
    'wxmsgimportalert',
    'nonlocalqrauthloginrecord',
    'radartileindex',
    'airportradaralert',
    'radarjobrun',
    'airporttrendalert',
}

ACCESS_MODELS = {
    'accessgroup',
    'accessgrouppermission',
    'accesssetting',
    'nonlocalqrblacklist',
}

ACCESS_DB = 'access'

DJANGO_APPS = {'admin', 'auth', 'contenttypes', 'sessions'}


def database_for(app_label: str, model_name: str | None) -> str | None:
    """返回模型所在库。model_name 为空时，无法从单个模型判断。"""
    if app_label in DJANGO_APPS or app_label not in ('core', 'parsers'):
        return 'default'
    if app_label == 'parsers':
        return 'runtime'
    name = (model_name or '').lower()
    if name in CONFIG_MODELS:
        return 'default'
    if name in RUNTIME_CORE_MODELS:
        return 'runtime'
    if name in ACCESS_MODELS:
        return ACCESS_DB
    return None


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
        if db == ACCESS_DB:
            # 用户组库只建 ACCESS_MODELS 的表；历史迁移里的数据脚本（无模型名）不在此库执行
            return app_label == 'core' and (model_name or '').lower() in ACCESS_MODELS
        if app_label in DJANGO_APPS:
            return db == 'default'
        if app_label == 'parsers':
            return db == 'runtime'
        if app_label == 'core':
            if not model_name:
                return True
            target = database_for('core', model_name)
            return target == db
        return db == 'default'
