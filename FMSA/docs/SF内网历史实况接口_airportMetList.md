# SF 内网历史实况接口 `airportMetList`

机场详情页向 SF 内网拉取历史报文时，走的是本接口，不是最新实况 `queryMetarTelList`，也不是最近 N 条 `selectNewestTopMet`。

本文只描述该接口的请求/响应结构，以及详情页实际读取的字段。未在代码中读取的字段不作为契约。

实现位置：`fmsa_django/parsers/metar_history.py` 的 `_fetch_history_obj` / `fetch_raw_met_list`。

---

## 1. 调用关系（详情页）

详情页不把本接口原始 JSON 直接交给前端。后端先请求本接口，再按用途分流：

| 详情页用途 | FMSA 入口 | 请求本接口时的 `wsTypes` | 时间窗 |
|---|---|---|---|
| 报文原文（实况最新 5 份，预报按 FC/FT 规则） | `GET /{time_mode}/api/airport/{code}/report-text/` | `SA, SP, FC, FT` | 默认近 72 小时 |
| 72 小时整点 SA 缺口补数并入库 | `GET /{time_mode}/api/airport/{code}/metar-history-ensure/` | `SA, SP` | 缺失整点对应窗口 |
| 趋势图 / 趋势表 | 读本地 `metar` 表 | 补数阶段同上 | 图 72h / 表 24h |

`test` 模式不打本接口，改为从本地 `metar` / `taf` 表拼出与 `obj[]` 同形的列表（`content`、`wtype`、`receiveTime`、`airPressure`）。

生产网关由本机 `FMSA/.env` 的 `SF_INTRANET_BASE_URL` 决定，例如：

`{SF_INTRANET_BASE_URL}/met/dispatchMetTelSummary/airportMetList`

---

## 2. 请求

- **Method**：`POST`
- **Path**：`/met/dispatchMetTelSummary/airportMetList`
- **Body**：JSON

### 2.1 请求头

| 头 | 必填 | 说明 |
|---|---|---|
| `Content-Type` | 是 | `application/json` |
| `token` | current 模式是 | CAS 登录拿到的业务 token，原样放入请求头 `token`（不是 `Authorization`） |

详情页 current 模式：前端 `Authorization: Bearer {token}` → 后端再转成上述 `token` 头。无 token 时 401，不请求内网。

### 2.2 请求体

详情页实际发送：

```json
{
  "code4s": "ZBAA",
  "wsTypes": ["SA", "SP"],
  "historyFlag": "Y",
  "searchStartDate": 1761800000000,
  "searchEndDate": 1762059200000,
  "metarOrTafTopNum": 100000,
  "otherTopNum": 100000
}
```

| 字段 | 类型 | 详情页取值 | 说明 |
|---|---|---|---|
| `code4s` | string | 单个四字码，如 `ZBAA` | 机场过滤。同源其它系统可空格拼接多个四字码做批量 |
| `wsTypes` | string[] | 见上表 | 报文种类过滤，见 §2.3 |
| `historyFlag` | string | 固定 `"Y"` | 拉历史，不是最新一条 |
| `searchStartDate` | number | 毫秒时间戳 | 窗口起点。默认 `searchEndDate - 72h` |
| `searchEndDate` | number | 毫秒时间戳 | 窗口终点。默认当前 UTC（test 模式用测试时钟） |
| `metarOrTafTopNum` | number | `100000` | 实况/预报条数上限，大数表示窗口内尽量全取 |
| `otherTopNum` | number | `100000` | 其它类型条数上限 |

起点晚于终点时，调用方会把两者对调后再发出。

超时：30 秒。

### 2.3 `wsTypes`

| 值 | 含义 |
|---|---|
| `SA` | 例行实况 METAR |
| `SP` | 特殊实况 SPECI |
| `FC` | 短期预报 TAF |
| `FT` | 常规预报 TAF |

详情页历史**实况**只传 `SA`、`SP`。同接口带 `FC`、`FT` 时给详情页预报原文用。

---

## 3. 响应信封

HTTP 200 且 body 可 JSON 解析后，再看业务字段：

```json
{
  "requestId": null,
  "success": true,
  "business": null,
  "errorCode": null,
  "errorMessage": null,
  "params": null,
  "date": null,
  "version": null,
  "obj": []
}
```

| 字段 | 类型 | 调用方处理 |
|---|---|---|
| `success` | boolean | `false` 视为失败，读 `errorMessage`，`obj` 当空 |
| `errorMessage` | string / null | 失败原因 |
| `obj` | array / null | 报文列表。`null` 或缺失当 `[]` |
| `errorCode` 等 | 任意 | 详情页不读 |

HTTP 非 200、JSON 解析失败、网络异常：按失败处理，不入库、不展示。

`success=true` 且 `obj=[]`：该窗口无数据，算成功。

失败样例：

```json
{
  "success": false,
  "errorCode": "1010",
  "errorMessage": "系统错误",
  "obj": null
}
```

---

## 4. `obj[]` 元素

列表无保证顺序。详情页先逐条取字段，再按观测时间从新到旧排序。

### 4.1 详情页实际读取

同一语义可能有多个键名，按表中顺序取第一个非空。

| 语义 | 键（优先级从左到右） | 类型 | 说明 |
|---|---|---|---|
| 报文字符串 | `content` | string | 必用。空或仅空白则丢弃该条 |
| 报文种类 | `wtype` → `wsType` → `type` | string | 规范化为大写后须为 `SA` / `SP` / `FC` / `FT`。都不合法时用 `content` 开头推断：含 `TAF` 则按有效时段判 `FC`（≤12h）或 `FT`；含 `SPECI` 或 `SP` 为 `SP`；否则 `SA` |
| 接收/观测时间 | `receiveTime` → `observationTime` | number | 毫秒时间戳。解析失败当 `0`。排序时优先用 `content` 里 `DDHHMMZ` 推出的观测时刻，没有才用本字段 |
| 气压 | `airPressure` → `air_pressure` | number / string / null | 优先当 hPa 数值用；无效则回退报文气压组（`Qxxxx` / `Axxxx`） |

入库补数时，`airPressure` 会随 `raw_item` 传给解析器，写入 `metar.metar_pressure_val`。

### 4.2 同源系统还出现过的键

不作为详情页契约，联调时可能随条出现：

| 键 | 说明 |
|---|---|
| `airport4Code` | 四字码。批量 `code4s` 时可用于二次过滤 |
| `handInput` | 是否手工录入 |
| `observationTime` | 观测时刻（毫秒）。详情页仅作 `receiveTime` 的后备 |

最新实况 `queryMetarTelList` 的结构化要素（`windSpeed`、`visibility`、`dewPoint`、`ryg` 等）**详情页历史链路不读**。图表风速、能见度、气温、天气等均由 `content` 经 avwx 解析得到。

### 4.3 实况条目样例

字段以详情页实际读取为准，其余键可能存在：

```json
{
  "content": "METAR ZBAA 160630Z 20002MPS 120V260 9999 FEW030 28/22 Q1009 NOSIG=",
  "wtype": "SA",
  "receiveTime": 1755297143000,
  "observationTime": 1755297000000,
  "airport4Code": "ZBAA",
  "airPressure": 1009
}
```

SPECI：

```json
{
  "content": "SPECI ZBAA 160645Z 28012G18MPS 3000 -TSRA BKN008 24/22 Q1007=",
  "wtype": "SP",
  "receiveTime": 1755297900000,
  "airPressure": 1007
}
```

---

## 5. 详情页对 `obj[]` 的规范化结果

`fetch_raw_met_list` 输出（不是 SF 原始 JSON）：

```json
{
  "content": "METAR ZBAA 160630Z 20002MPS 120V260 9999 FEW030 28/22 Q1009 NOSIG=",
  "wtype": "SA",
  "sort_time": 1755297000000,
  "airPressure": 1009
}
```

| 字段 | 说明 |
|---|---|
| `content` | 去首尾空白后的原文 |
| `wtype` | 已归一为 `SA` / `SP` / `FC` / `FT` |
| `sort_time` | 观测时刻毫秒；推不出则用 `receiveTime`/`observationTime`；再没有为 `-1` |
| `airPressure` | 接口气压，没有则为 `null` |

列表按 `sort_time` 降序。

报文原文：实况取前 5 条；预报 `FC`/`FT` 同时存在时各取最新 1 条，只有一种则取该种最新 1 条。

图表：对 `content` 解析后按 `metar_observation_time` 去重（同一分钟 SA/SP 留先出现的一条），再升序给趋势图。

---

## 6. 与相邻 SF 接口的区别

| 接口 | 路径 | 详情页是否使用 |
|---|---|---|
| 本接口（历史列表） | `POST /met/dispatchMetTelSummary/airportMetList` JSON body | **是**（历史实况/预报原文、72h 补数） |
| 最近 N 条摘要 | `POST /met/dispatchMetTelSummary/selectNewestTopMet` URL 参数 `code4` | 否（旧弹窗/适配器 `get_history_reports`） |
| 最新结构化实况 | `POST /met/dispatchMetarMetTel/queryMetarTelList` | 否（主页/调度入库最新报） |

不要把 `selectNewestTopMet` 的 `code4` 或 `queryMetarTelList` 的 `airport4Codes` + `observationTime` 套到本接口上。
