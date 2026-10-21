"""清掉配置库里已不用的表：旧权限备份、Django admin/auth。"""

from django.db import connections

UNUSED_TABLES = {
    'auth_group',
    'auth_group_permissions',
    'auth_permission',
    'auth_user',
    'auth_user_groups',
    'auth_user_user_permissions',
    'django_admin_log',
    'django_content_type',
}

DROPPED_MIGRATION_APPS = ('admin', 'auth', 'contenttypes')


def drop_unused_config_tables():
    conn = connections['default']
    names = conn.introspection.table_names()
    to_drop = [
        name for name in names
        if name in UNUSED_TABLES or '_bak_' in name
    ]
    if not to_drop and 'django_migrations' not in names:
        return to_drop
    with conn.cursor() as cursor:
        cursor.execute('PRAGMA foreign_keys=OFF')
        for name in to_drop:
            cursor.execute(f'DROP TABLE IF EXISTS "{name}"')
        if 'django_migrations' in names:
            cursor.execute(
                'DELETE FROM django_migrations WHERE app IN (%s, %s, %s)',
                DROPPED_MIGRATION_APPS,
            )
        cursor.execute('PRAGMA foreign_keys=ON')
    return to_drop
