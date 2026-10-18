# TAF `taf_elements` 入库说明

供新对话核对用。本文只描述**已实现的写入**，不含明语翻译、不含主页改动。

## 位置与时机

- 表：`taf`
- 列：`taf_elements`（JSON，可空）
- 写入：`TafParser.parse_taf` 成功后，在 `to_database_dict` 里由 `parsers/taf_elements.py` 组装
- 迁移：`parsers/migrations/0009_taf_elements.py`
- 主页旧列（`subject_*`、`change_n_*` 等）**照旧写入，未删除**
- 占位行（`data_status=C`）、迁移前的历史行：该列为 `null`，需重新解析入库才有值
- 取消报 CNL：仍写 JSON，但 `cancelled=true`，`subject` 为 `null`，`changes` 为空

数据来源是**当次解析内存**（avwx 行 + 继承后的 `change_groups` + 已算好的告警），不是二次解原文。

---

## 顶层字段

| 键 | 含义 | 规则 |
|---|---|---|
| `airport` | 四字代码 | 列内再存一份 |
| `issue_time` | 发报时间戳 | 与 `taf_observation_time` 相同（毫秒）；解析测试未覆盖 API 时间时可能为 `null` |
| `issue_time_z` | 发报时次 | `ddHHMMZ`，来自 avwx `data.time` |
| `amended` | 是否 AMD | 布尔 |
| `corrected` | 是否 COR | 布尔 |
| `cancelled` | 是否 CNL | 布尔 |
| `whole_validity` | 整份有效期 | 如 `1106/1212`，≠ 主预报截断后的时段 |
| `subject_period.start` / `.end` | 主预报自身起止 | `end` 取最早 FROM/BECMG 的报文开始时次（现逻辑），否则为整份有效期结束 |
| `temperatures` | TX/TN 列表 | 见下；不属于某个 TEMPO |
| `subject` | 主预报生效要素 | 见下 |
| `changes` | 真实变化组数组 | 有几条写几条，不补满 8 个空组 |

`subject_warning` **只在** `subject.warning`，不在顶层。

---

## `temperatures[]`

每条：

| 键 | 含义 |
|---|---|
| `kind` | `"max"` 或 `"min"` |
| `value` | 气温数值（字符串，负值为 `-` 前缀） |
| `time` | `ddHH` |
| `alert` | 该条温度告警 |

最多两个最高、两个最低，有才写入。

---

## 要素块（`subject` 与每个 change 共用结构）

### `warning`

- 该时段风 / 能见度 / 天气 / 云四类告警取最高
- **不含**变化组（主预报）、**不含**温度
- 变化组各自有自己的 `warning`

### `wind`（无风组则为 `null`）

| 键 | 含义 |
|---|---|
| `direction` | 风向三位数或 `VRB` |
| `speed` | 平均风速 |
| `gust` | 阵风，无则 `null` |
| `unit` | `MPS` / `KT` / `KMH` 等 |
| `variable` | 变风 `{from, to}`，无则 `null` |
| `alert` | 风组告警（平均风与阵风取高） |
| `speed_alert` | **平均风**单独告警（`get_wind_alert_level`），无风速则 `null` |
| `gust_alert` | **阵风**单独告警（`get_gust_alert_level`），无阵风则 `null` |
| `inherited` | 主预报恒 `false`；BECMG 补上的为 `true` |

子告警按解析器换算后的 m/s 值判定（主预报取 `subject_wind_speed_mps` / `subject_gust_mps`，
变化组取组内 `wind_speed_mps` / `gust_mps`），供明语翻译只给数值本身着色。

### `visibility`（无能见度则为 `null`）

| 键 | 含义 |
|---|---|
| `raw` | 原始语义（继承 CAVOK 转 9999 时仍为 `"CAVOK"`） |
| `value` | 生效值（`8000` / `9999` / `CAVOK` / `P6SM` 等） |
| `unit` | `m` / `SM` 等 |
| `cavok` | 当前生效值是否仍是 CAVOK |
| `alert` | 能见度告警 |
| `inherited` | 同上 |

### `weather`

| 键 | 含义 |
|---|---|
| `items` | 现象数组；**无现象为 `[]`**，只有原文有 `NSW` 才出现 NSW 项 |
| `items[].code` | 现象码 |
| `items[].alert` | **该码**告警（`get_weather_alert_level`） |
| `items[].inherited` | 该项是否继承 |
| `warning` | **组级**天气告警 |
| `inherited` | 整组天气是否继承 |

### `clouds`

| 键 | 含义 |
|---|---|
| `sky` | `NSC` / `SKC` / `CLR` / `NCD`，无则 `null` |
| `layers` | 云层数组；无云且非 NSC/SKC 为 `[]`；VV 作为一层，`cover` 为 `VV` |
| `layers[].cover` | `FEW` / `SCT` / `BKN` / `OVC` / `VV` 等 |
| `layers[].height` | 云底高，单位百英尺（`FEW040` → `40`） |
| `layers[].height_unit` | 固定 `"hft"` |
| `layers[].type` | `CB` / `TCU` 等，无则 `null` |
| `layers[].alert` | 该层按最低云高同一套阈值 |
| `layers[].inherited` | 该层是否继承 |
| `warning` | **组级** `cloud_warning` |
| `inherited` | 整组云是否继承 |

### `wind_shear`

有则原文令牌（如 `WS020/030MPS`），无则 `null`。不继承。

---

## `changes[]`（仅真实组）

每条除上述要素块外还有：

| 键 | 含义 | 规则 |
|---|---|---|
| `type` | `FM` / `BECMG` / `TEMPO` / `INTER` / `PROB30` / `PROB40` 等 | 与现解析 `change_n_type` 一致 |
| `probability` | PROB 数字 | 无则 `null` |
| `transition_start` | BECMG 转变窗口开始 | 报文时间组**第一个**时次（avwx `transition_start`）；非 BECMG 为 `null` |
| `start` | 开始生效 | BECMG 为报文时间组**第二个**时次（现库 `validity_period_start`）；其它组为该组开始 |
| `end` | 结束 | **BECMG 恒为 `null`（不存 avwx 补出的生效结束）**；**FM 恒为 `null`**；TEMPO / INTER / PROB 为报文结束时次 |

---

## 继承与 CAVOK（只作用于 BECMG）

- TEMPO / INTER / PROB / FM：**不继承**；缺的要素为 `null` 或 `[]`，`inherited` 为 `false`
- BECMG：缺的风 / 能见度 / 天气 / 云，从更早的 FROM/BECMG（否则主预报）补全（沿用现 `process_becmg_inheritance`）
- 不加括号，用 `inherited: true|false` 识别
- NSW：天气继承为空（`items` 为 `[]`）
- NSC/SKC：不继承云
- 本组自身能见度为 CAVOK：清空天气和云
- 继承的 CAVOK 且本组已有天气或云：生效值改为 `9999` 或 `P6SM`；`raw` 仍为 `"CAVOK"`，`inherited` 为 `true`，`cavok` 为 `false`

---

## 告警取值

- 风 / 能见度 / 云 / 温度：与现 TAF 入库同一套机场阈值
- 风另写平均风、阵风两个子告警，便于逐值着色
- 天气每码：`weather_alert_levels`（`get_weather_alert_level`）
- 组综合：四类要素告警取最高（与现 `subject_warning` / `change_n_warning` 相同，不含温度）

---

## 明确不进本列

- `taf_content` 全文、`content_all`
- `sqc`、`data_status`、导入告警与处理留痕
- 主页甘特仍用旧列

---

## 核对入口

- 组装：`fmsa_django/parsers/taf_elements.py` → `build_taf_elements`
- 挂钩：`fmsa_django/parsers/taf_parser.py`（继承前 `_snapshot_own_elements`，`to_database_dict` 写入）
- 模型：`parsers.models.Taf.taf_elements`
