#!/usr/bin/env python3
"""
将 china.json 中的省级边界合并进 world_pacific.json：
  1. 删除 world_pacific.json 中名为 "China" 的国界 feature
  2. 将 china.json 各省 feature 的坐标做 pacific 偏移（lon - 150）
     （中国所有经度均在 73°E~135°E，全部 >= -30°，直接减 150）
  3. 将转换后的省级 features 追加到 world_pacific.json
  4. 从 world.json（原始）提取中国国界轮廓，同样做 pacific 偏移后，
     以 name="China_outline" 追加，供前端加粗显示国界线

执行后直接覆盖 world_pacific.json，无需其他操作。
"""
import json, copy, pathlib

ROOT  = pathlib.Path(__file__).parent.parent
CHINA = ROOT / 'fmsa_django' / 'static' / 'geo' / 'china.json'
WORLD = ROOT / 'fmsa_django' / 'static' / 'geo' / 'world_pacific.json'
DST   = WORLD   # 直接覆盖

SHIFT = 150  # world_pacific 坐标系：原始经度 - 150


def shift_coords(obj):
    """递归遍历 GeoJSON geometry，将所有经度减去 SHIFT"""
    if isinstance(obj, list):
        if obj and isinstance(obj[0], (int, float)):
            # [lon, lat] 坐标点
            return [obj[0] - SHIFT, obj[1]]
        return [shift_coords(item) for item in obj]
    return obj


def transform_geometry(geom):
    """对整个 geometry 的 coordinates 做经度偏移"""
    result = copy.deepcopy(geom)
    result['coordinates'] = shift_coords(result['coordinates'])
    return result


# ── 加载数据 ──────────────────────────────────────────────────────────────────
print(f'读取: {WORLD}')
with open(WORLD, 'r', encoding='utf-8') as f:
    world = json.load(f)

print(f'读取: {CHINA}')
with open(CHINA, 'r', encoding='utf-8') as f:
    china = json.load(f)

# ── 移除 world 中已有的 China 整体国界及旧版 China_outline（防止重复运行叠加）────
before = len(world['features'])
world['features'] = [
    feat for feat in world['features']
    if feat.get('properties', {}).get('name') not in ('China', 'China_outline')
]

# ── 同时移除已有的省级 feature（防止重复，通过 parent adcode 识别）────────────
# 省级 feature 由本脚本写入，其 properties 只含 name 字段（无 adcode），
# 但 name 与 china.json 中省名一致；用 china 省名集合过滤
china_province_names = set()
for feat in china['features']:
    props = feat.get('properties', feat)
    name = props.get('name', '')
    adcode = props.get('adcode', '')
    if name and not str(adcode).endswith('_JD'):
        china_province_names.add(name)

world['features'] = [
    feat for feat in world['features']
    if feat.get('properties', {}).get('name') not in china_province_names
]

after = len(world['features'])
print(f'清理旧数据：{before} → {after} 个 feature')

# ── 将 china.json 省级 feature 经度变换后追加 ────────────────────────────────
skip_names = {''}   # 跳过南海九段线（name 为空字符串）
added_provinces = 0
for feat in china['features']:
    props = feat.get('properties', feat)
    name  = props.get('name', '')
    adcode = props.get('adcode', '')

    if name in skip_names or str(adcode).endswith('_JD'):
        print(f'  跳过南海 feature: name="{name}" adcode="{adcode}"')
        continue

    new_feat = copy.deepcopy(feat)
    new_feat['geometry'] = transform_geometry(feat['geometry'])
    new_feat['properties'] = {'name': name}
    world['features'].append(new_feat)
    added_provinces += 1

print(f'追加中国省级 feature：{added_provinces} 个')

print(f'合并后 world_pacific.json 共 {len(world["features"])} 个 feature')

# ── 写出 ──────────────────────────────────────────────────────────────────────
print(f'写出: {DST}')
with open(DST, 'w', encoding='utf-8') as f:
    json.dump(world, f, ensure_ascii=False, separators=(',', ':'))

size_kb = DST.stat().st_size // 1024
print(f'完成！文件大小: {size_kb} KB')
