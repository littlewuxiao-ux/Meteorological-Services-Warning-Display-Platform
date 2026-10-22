"""外观样式 API（雷达地图样式 + 机场详细信息主题，同存 style_config JSON）。"""

from __future__ import annotations

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from utils.map_style_defaults import (
    BORDER_WIDTH,
    COLOR_SCHEMES,
    resolve_user_appearance,
    save_user_appearance,
)


def _json_body(request):
    import json
    try:
        return json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        return {}


def _payload(map_cfg, airport_cfg, extra=None):
    body = {
        'success': True,
        'config': map_cfg,
        'airport_detail': airport_cfg,
        'border_widths': BORDER_WIDTH,
        'color_schemes': [
            {'id': k, 'label': v['scheme_label']} for k, v in COLOR_SCHEMES.items()
        ],
        'palette': COLOR_SCHEMES[map_cfg['color_scheme']],
        'airport_detail_themes': [
            {'id': 'dark', 'label': '深色'},
            {'id': 'light', 'label': '浅色'},
        ],
    }
    if extra:
        body.update(extra)
    return body


def _can_read_appearance(identity):
    from utils.access_control import has_perm
    return any(
        has_perm(identity, module, 'display')
        for module in (
            'view_map',
            'view_home',
            'view_plain',
            'search',
            'settings_map_style',
        )
    )


@require_http_methods(['GET', 'PUT'])
@csrf_exempt
def map_style_config(request, time_mode='current'):
    from config_db.models import StyleConfig
    from api.settings_views import _deny_settings_write
    from utils.access_control import resolve_access_identity
    from utils.user_settings import scope_meta, settings_subject

    user, editing = settings_subject(request, time_mode)
    row = StyleConfig.objects.order_by('id').first()
    stored = row.config if row else None

    if request.method == 'GET':
        identity = resolve_access_identity(request)
        if not _can_read_appearance(identity):
            return JsonResponse({'success': False, 'error': '无外观样式查看权限'}, status=403)
        map_cfg, airport_cfg = resolve_user_appearance(stored, user, editing)
        return JsonResponse(_payload(map_cfg, airport_cfg, scope_meta(request, time_mode)))

    denied = _deny_settings_write(request, 'settings_map_style')
    if denied:
        return denied
    data = _json_body(request)
    cfg_in = data.get('config')
    if cfg_in is not None and not isinstance(cfg_in, dict):
        return JsonResponse({'success': False, 'error': 'config must be object'}, status=400)
    airport_in = data.get('airport_detail')
    if airport_in is not None and not isinstance(airport_in, dict):
        return JsonResponse({'success': False, 'error': 'airport_detail must be object'}, status=400)
    if cfg_in is None and airport_in is None:
        return JsonResponse({'success': False, 'error': 'config or airport_detail required'}, status=400)

    next_cfg = save_user_appearance(stored, user, cfg_in, airport_in, editing)
    if row:
        row.config = next_cfg
        row.save(update_fields=['config', 'updated_at'])
    else:
        StyleConfig.objects.create(config=next_cfg)
    map_cfg, airport_cfg = resolve_user_appearance(next_cfg, user, editing)
    return JsonResponse(_payload(map_cfg, airport_cfg, scope_meta(request, time_mode)))
