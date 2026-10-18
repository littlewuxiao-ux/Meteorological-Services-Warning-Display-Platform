# 用户组权限去掉「激活后台」列，日出日落、跑道改为随所在页面显示；设置项写入仅本机组。

from django.db import migrations

_REMOVED_MODULES = [
    'detail_sun_home', 'detail_sun_plain', 'detail_runway_home', 'detail_runway_plain',
    'search_sun_home', 'search_sun_plain', 'search_runway_home', 'search_runway_plain',
]

_SETTINGS_MODULES = [
    'settings_airport_info', 'settings_prefix_area', 'settings_taf_import',
    'settings_data_refresh', 'settings_popup', 'settings_alert_thresholds',
    'settings_weather_type', 'settings_weather_alert', 'settings_radar_alert',
    'settings_trend_alert', 'settings_map_style',
]


def _cleanup_permissions(apps, schema_editor):
    conn = schema_editor.connection
    if 'access_group_permission' not in conn.introspection.table_names():
        return
    Perm = apps.get_model('core', 'AccessGroupPermission')
    Perm.objects.using(conn.alias).filter(module_code__in=_REMOVED_MODULES).delete()
    Perm.objects.using(conn.alias).filter(
        module_code__in=_SETTINGS_MODULES, group__is_local=False, can_write=True,
    ).update(can_write=False)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_popup_display_switches'),
    ]

    operations = [
        migrations.RunPython(_cleanup_permissions, migrations.RunPython.noop),
        migrations.RemoveField(model_name='accessgrouppermission', name='can_activate'),
    ]
