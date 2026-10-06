"""Portable settings archives; airport dictionaries and login tokens are excluded."""
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

BLOCKS = {'paths', 'default_airports', 'personnel_dict', 'phenomena_config', 'thresholds', 'publish'}


def validate_settings(value):
    if not isinstance(value, dict) or not value:
        raise ValueError('配置必须是非空对象')
    if set(value) - BLOCKS - {'schema_version'}:
        raise ValueError('包含未知配置字段')
    if not any(key in value for key in BLOCKS):
        raise ValueError('文件不包含系统配置')
    for key in BLOCKS & set(value):
        if not isinstance(value[key], dict):
            raise ValueError(f'{key} 必须为对象')
    def check(node, depth=0):
        if depth > 20:
            raise ValueError('配置嵌套过深')
        if isinstance(node, dict):
            for key, child in node.items():
                if key in {'__proto__', 'prototype', 'constructor'}:
                    raise ValueError('非法配置字段')
                check(child, depth + 1)
        elif isinstance(node, list):
            for child in node:
                check(child, depth + 1)
        elif not isinstance(node, (str, int, float, bool, type(None))):
            raise ValueError('不支持的配置类型')
    check(value)
    return value


class SettingsArchive:
    def __init__(self, directory):
        self.directory = Path(directory)

    def create(self, settings):
        self.directory.mkdir(parents=True, exist_ok=True)
        name = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json'
        fd, temporary = tempfile.mkstemp(dir=self.directory, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                json.dump(settings, handle, ensure_ascii=False, indent=2, allow_nan=False)
            os.replace(temporary, self.directory / name)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return name

    def list(self):
        if not self.directory.exists():
            return []
        return [{'name': path.name, 'size': path.stat().st_size} for path in sorted(self.directory.glob('*.json'), reverse=True)[:50]]

    def read(self, name):
        if not isinstance(name, str) or Path(name).name != name or not name.endswith('.json'):
            raise ValueError('无效备份名称')
        with (self.directory / name).open(encoding='utf-8') as handle:
            return validate_settings(json.load(handle))
