# 基于航班计划的气象监视告警系统 · 使用说明

---

## 一、实况弹窗拦截功能说明

### 1.1 功能概述

系统接收到新的 METAR 报文后，会自动判断是否需要弹窗通知。为避免天气状况持续但已在改善时重复打扰用户，系统设有**弹窗拦截机制**：当新报文满足弹窗条件，但与上一份报文相比天气要素并未恶化时，将弹窗标记为 `I`（拦截），而非 `Y`（弹出）。

---

### 1.2 弹窗状态说明

| popup 值 | 含义 |
|---|---|
| `N` | 不满足弹窗条件，无需弹窗 |
| `Y` | 满足弹窗条件，执行弹窗 |
| `I` | 满足弹窗条件，但被拦截（天气未恶化） |

---

### 1.3 弹窗类型

| 类型 | 触发依据 | 阈值配置 |
|---|---|---|
| 运行类（operation） | 风速、能见度、云底高、温度、天气现象等 | `operation_metar_popup_level` |
| 停场类（parking） | 风速、低温、停场类天气（S/F/I/G/H） | `parking_metar_popup_level` |
| 两者兼有（both） | 同时满足以上两类条件 | 各自阈值 |

---

### 1.4 相关配置开关

所有配置保存于 `PopupSettings` 表，按 `user_code` 区分：

| 字段 | 说明 |
|---|---|
| `operation_metar_popup` | 运行类弹窗总开关（1=开，0=关） |
| `parking_metar_popup` | 停场类弹窗总开关 |
| `intercept` | 拦截功能开关（0=关闭拦截，所有满足条件的报文均弹窗） |
| `operation_metar_popup_level` | 运行类弹窗告警等级阈值（N/G/Y/R） |
| `parking_metar_popup_level` | 停场类弹窗告警等级阈值 |
| `operation_metar_popup_leeway` | 运行类弹窗时间裕度（小时） |

---

### 1.5 总体处理流程

```
新 METAR 报文到达
        │
        ▼
  判断弹窗类型
  (operation / parking / both / 无)
        │
  无弹窗 ──────────────────────► popup = N
        │
  有弹窗
        │
        ▼
  intercept 开关是否开启？
        │
   否 ──────────────────────────► popup = Y
        │
   是
        │
        ▼
  执行拦截前提条件判断（见1.6节）
        │
  前提不满足 ───────────────────► popup = Y
        │
  前提全部满足
        │
        ▼
  执行要素对比（见1.7/1.8节）
        │
  要素对比通过 ─────────────────► popup = I（拦截）
        │
  要素对比不通过 ───────────────► popup = Y
```

---

### 1.6 拦截前提条件

以下条件按概率从高到低排列，任一不满足则直接 `popup=Y`：

| 顺序 | 判断内容 | 不满足时 |
|---|---|---|
| ① | `intercept` 开关已开启 | popup=Y |
| ② | `last_metar_sqc` 不为空（存在上一份报文） | popup=Y |
| ③ | 根据 `last_metar_sqc` 能查到上一份报文记录 | popup=Y |
| ④ | 上一份报文 `popup ≠ N`（上一份有过弹窗） | popup=Y |
| ⑤ | 两份报文时间戳差值在 **1～4200000ms（70分钟）**内 | popup=Y |
| ⑥ | 两份报文 `user_code` 相同 | popup=Y |

> **注**：`data_status=C` 的系统占位行在创建时写入 `popup='N'`，因此会被条件④自动拦截，无需单独判断。

---

### 1.7 运行类弹窗拦截要素对比

前提条件全部通过后，检查以下触发字段。**只对 warning 值 ≥ `operation_metar_popup_level` 的项进行数值对比，全部通过才拦截。**

#### 前置快速判断（优先执行）

| 字段 | 条件 | 结果 |
|---|---|---|
| `metar_change_trend_warning` | ≥ 阈值 | 直接 popup=Y，跳过所有对比 |
| `metar_ws_warning` | ≥ 阈值 | 直接 popup=Y，跳过所有对比 |

#### 要素对比规则

| 触发字段 | 对比要素 | 拦截条件（需全部满足） |
|---|---|---|
| `metar_wind_warning` | 风速（`metar_wind_speed_val`）+ 阵风（`metar_gust_val`） | 两值均 ≤ 上一份；阵风为 None 视为更小通过；上一份无阵风而当前有则不通过 |
| `metar_visibility_warning` 或 `metar_rvr_warning`（任一满足即同时对比两项） | 能见度（`metar_visibility_val`）+ RVR（`rvr_min_val`） | 能见度 ≥ 上一份；RVR 见下表 |
| `metar_weather_warning` | `metar_weather_type` 字典（全部类型） | 无新增天气类型，已有类型等级不变或降级 |
| `metar_cloud_warning` | 云底高（`metar_min_cloud_height`） | 当前 ≥ 上一份（None 视为更大，通过） |
| `metar_temperature_warning` | 温度（`metar_temp_val`） | 见温度规则 |

#### RVR 对比规则

| 当前 RVR | 上一份 RVR | 结果 |
|---|---|---|
| 有值 | 有值 | 当前 ≥ 上一份 → 通过 |
| 无（None） | 有值 | 通过（当前无 RVR 视为改善） |
| 有值 | 无（None） | **不通过** |
| 无（None） | 无（None） | 通过 |

#### 运行类温度规则

| 当前温度 | 上一份温度 | 拦截条件 |
|---|---|---|
| None | 任意 | 通过 |
| 有值 | None | **不通过** |
| ≥ 0°C | 有值 | 当前 ≤ 上一份（降低或不变）→ 通过 |
| < 0°C | 有值 | 当前 ≥ 上一份（升高或不变）→ 通过 |

---

### 1.8 停场类弹窗拦截要素对比

阈值使用 `parking_metar_popup_level`，**不涉及能见度、RVR、云底高**。

| 触发字段 | 对比要素 | 拦截条件 |
|---|---|---|
| `metar_wind_warning` | 风速 + 阵风 | 同运行类 |
| `metar_weather_warning` | `metar_weather_type` 中**仅 S/F/I/G/H 类型** | 无新增停场类型，已有类型等级不变或降级 |
| `metar_temperature_warning` | 温度 | 当前温度 < 0 且 当前 < 上一份 → 通过；其他情况不通过 |

---

### 1.9 告警等级说明

| 等级 | 优先级 | 含义 |
|---|---|---|
| `R` | 4（最高） | 红色告警 |
| `Y` | 3 | 黄色告警 |
| `G` | 2 | 绿色告警 |
| `N` | 1（最低） | 正常 |

"告警等级升级"指优先级数值增大；"降级"指数值减小或类型消失。

---

*本文档由系统自动维护，如需修改请编辑 `fmsa_django/static/docs/system_guide.md`*
