"""地图样式默认可配置项（存 DB JSONField）。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict


# 边界线宽（非设置项，代码写死）
BORDER_WIDTH = {
    'country': 1.1,
    'province': 0.7,
    'admin1': 0.55,
}

# 3 套配色：两深一浅。国界实线 / 省州界虚线由前端线型控制。
# 深色靠填色区分海陆（无海岸线描边）；河流细、暗，让国界更醒目。
# 浅色海陆拉开明度，文字用深色字加浅色描边。
COLOR_SCHEMES = {
    'deep_navy': {
        'id': 'deep_navy',
        'scheme_label': '深海军蓝',
        'background': '#2a3038',
        'land': '#0c1016',
        'sea': '#2a3038',
        'country_border': '#9aa4b0',
        'province_border': '#5c6670',
        'admin1_border': '#6a7480',
        'label_color': '#d5dde6',
        'country_label': '#c5ced8',
        'label_halo': 'rgba(8,12,18,0.88)',
        'river': '#5d7380',
        'river_width': 0.75,
        'river_opacity': 0.5,
        'lake': 'rgba(28, 40, 52, 0.85)',
        'lake_border': '#3a4858',
    },
    'slate_gray': {
        'id': 'slate_gray',
        'scheme_label': '冷灰岩板',
        'background': '#1a1f26',
        'land': '#2a3340',
        'sea': '#1a1f26',
        'country_border': '#d0dce8',
        'province_border': '#8f9eae',
        'admin1_border': '#9aabba',
        'label_color': '#eef3f8',
        'country_label': '#d5dee8',
        'label_halo': 'rgba(12,16,22,0.88)',
        'river': '#6d8292',
        'river_width': 0.75,
        'river_opacity': 0.48,
        'lake': 'rgba(48, 64, 80, 0.55)',
        'lake_border': '#6a8094',
    },
    'warm_dim': {
        'id': 'warm_dim',
        'scheme_label': '浅暖纸',
        'background': '#4d7ea6',
        'land': '#f7f4ec',
        'sea': '#4d7ea6',
        'country_border': '#2a261f',
        'province_border': '#6a6258',
        'admin1_border': '#7a7268',
        'label_color': '#1a140e',
        'country_label': '#1a140e',
        'label_halo': 'rgba(255,251,244,0.96)',
        'river': '#2a6496',
        'river_width': 0.9,
        'river_opacity': 0.72,
        'lake': 'rgba(90, 140, 175, 0.55)',
        'lake_border': '#3d6d90',
    },
}


def default_map_style_config() -> Dict[str, Any]:
    return {
        'color_scheme': 'deep_navy',
        'marker_inner_size': 6,
        'marker_outer_size': 10,
        'show_airport_labels': False,
        'china': {
            'province_borders': True,
            'province_labels': False,
        },
        'world': {
            'admin1_borders': False,
            'admin1_labels': False,
        },
        'global': {
            'country_borders': True,
            'country_labels': False,
            'rivers': False,
            'lakes': False,
        },
    }


def merge_map_style(stored: Dict[str, Any] | None) -> Dict[str, Any]:
    cfg = default_map_style_config()
    if not stored:
        out = cfg
    else:
        out = deepcopy(cfg)
        for key, val in stored.items():
            if key == 'metar_flash_mode':
                continue
            if key in ('china', 'world', 'global') and isinstance(val, dict):
                out[key] = {**cfg.get(key, {}), **val}
            else:
                out[key] = val
    if out.get('color_scheme') not in COLOR_SCHEMES:
        out['color_scheme'] = 'deep_navy'
    try:
        inner = int(out.get('marker_inner_size') or 6)
        outer = int(out.get('marker_outer_size') or 10)
        if outer < inner + 4:
            outer = inner + 4
        out['marker_inner_size'] = max(4, inner)
        out['marker_outer_size'] = outer
    except (TypeError, ValueError):
        out['marker_inner_size'] = 6
        out['marker_outer_size'] = 10
    out['show_airport_labels'] = bool(out.get('show_airport_labels'))
    return out


def resolve_palette(cfg: Dict[str, Any] | None) -> Dict[str, Any]:
    merged = merge_map_style(cfg)
    return COLOR_SCHEMES[merged['color_scheme']]
