# 精细化气象信息处理与客观评价平台（OMICS）· 项目说明

## 第五版正式版

当前版本：第五版正式版（2026-09-21）。第五版已完成核心业务流程稳定化，后续功能和界面改造统一进入第六版开发线。

### 第五版已完成内容

- 预报发布支持运行机场、机场分组、文字导入预报、表格导入四类机场来源，并显示机场性质、分组补充说明和导入统计。
- 机场分组支持置顶、全选和每次打开导入窗口重新选择，不持久化本次临时勾选状态。
- 未来24小时预报支持从 XLSX/XLSM 表格导入，并识别文件名、表格日期、起报时间和预报时效；兼容根目录两类 24 小时预报模板。
- 未来8/12/4小时及自定义时段继续使用原有目标机场实况下载逻辑；24小时扫描失败时自动回退到目标机场实况下载。
- 预报发布表格支持手动插入机场、强制显示被过滤机场、右键插入定位、拖动排序和顺序持久化。
- 刷新预报时，非自定义参数预报会自动更新到最新日期和对应时段；自定义参数不被覆盖。
- 修复机场重复判断、机场顺序恢复、保存后检查目录、评定结果 Excel 导出及保存目录打开功能。
- 评定结果保存后提供“检查保存文件”入口，直接打开席位预报或机场预报的实际保存目录。

### 第六版开发方向

第六版重点进行 OMICS 深度 UI 更新，建议围绕以下方向实施：

- 统一导航和页面层级，减少长页面滚动，明确“实时监控、预报发布、质量评定、历史查询、系统设置”五个一级工作区。
- 重做预报发布工作台，采用固定顶部工具栏、可折叠来源面板、清晰的表格状态栏和更稳定的窄屏布局。
- 强化状态反馈：统一加载、成功、失败、回退、未登录和未保存修改等状态样式，避免只通过弹窗提示。
- 统一按钮、颜色、间距、表格、弹窗和表单控件规范，降低现有页面中多套样式并存造成的视觉噪音。
- 提升可读性和可访问性：增加键盘操作、焦点状态、悬停说明、错误定位和长文本处理。
- 保持第五版业务逻辑和数据兼容，第六版优先改造界面结构与交互，不改变已有保存格式和评定规则。

## 最近更新 · 2026-08-02

### 2026-10-09 · 强降水与编发条件监控

- 编发前在机场天气行下方增加航班起降行，与逐小时列对齐：绿色向下表示落地、橙色向上表示起飞，数字为航班数，悬停查看北京时准确时刻、航班号和航线。开始前1小时内及结束后3小时内的航班分别用行首、行尾红方块提示。
- 航班展示与运行机场筛选共用 OMICS 航班接口结果，不读取 MTWS 数据库。借鉴 MTWS 时刻优先级：起飞按实际/预计/计划/公布，落地按实际/预计/计划/公布；Web Worker 后台分解并按承运人筛选、去重，页面可见时每分钟更新。接口失败显示不可用，不误报无航班。现有接口覆盖当前时刻前24小时至后48小时。
- 发布页天气翻译保留复合 RA 代码的降水量级，兼容大小写和连续空白。
- 每次确认编发及已编发内容编辑后异步检查地面结冰/极寒条件：编发温度优先，缺失时使用同小时 EC 温度，结合编发降水、雾、能见度及 EC 温露差、历史降水判断。新增候选在底部文字右侧显示红点，悬停显示机场名单，点击按条件选择新增或放弃；接受后保留人工汇总文字。
- 所选机场组在航班查询成功后按预报有效时段检查，无航班机场备注显示“无航班”；查询失败不作无航班判断。
- 文本导出将备注中的轻雾、冻雾、高温作为前置说明，随后补充逐小时能见度或温度；备注风统一为“西北风1-3米/秒”形式，不附时间。终端区及伴短时雷暴备注仅关联所在天气行，轻雾、冻雾在逐小时天气中保留完整名称。
- 前置说明与逐小时预报使用逗号连接，例如“有轻雾，3日01-06时能见度1600米”；不同预报段之间保留分号。

### 2026-09-27 · Publish workflow fixes

- Publish Excel export now uses the filename pattern `未来24小时天气预报YYYYMMDD.xlsx`.
- Excel import supports both the `.xlsx` and `.xlsm` 24-hour forecast templates in the project parent directory. It reads forecast date, start time, validity, airport rows, notes, airport nature, and the footer's ground-icing/extreme-cold airport summary.
- Imported footer conditions are restored in the publish view and persisted with the local publish snapshot. Airports with the same condition are grouped into one statement, for example `哈尔滨、长春（地面结冰）；锡林浩特（极寒）`.
- Import progress is cleared after a successful parse, including workbooks whose imported rows do not yet contain NWP data.
- Publish text export reflects edited notes immediately. Wind notes are placed first, high-temperature notes precede temperature text, and visibility values such as `5000+` and `4000+` export as `能见度大于5000米` and `能见度大于4000米`.
- The publish view can fetch the latest METAR independently of future TAF data and shows TAF/METAR on airport hover. Parallel loading status reports flight, TAF, METAR, EC, parsing, and layout stages.
- Running-flight filtering supports a configurable carrier-code list (default: `O3`, `8K`, `YG`) and includes only flights within one hour before through three hours after the selected forecast period.

- 修复 TAF/EC 连续双击失效：不再依赖浏览器原生 `dblclick` 对长点击序列的分组，自行将连续点击两两配对，连续多次双击可稳定逐次展开/收起。数据视图首行按 TAF、EC、编发和视图操作重新分组，来源开关、明细展开和一键采纳放在各自数据源内。
- 区域显示改为纯前端显隐：国内、国际区域内容左对齐，切换区域不再重新请求 TAF/EC/NWP；关闭区域只隐藏机场，完整数据、置顶顺序和缓存均保留，重新开启后原位恢复。运行机场导入会先加载全部区域，再按当前区域选择显示。
- 发布表右键菜单统一提供增加天气行、删除当前天气行、新增机场和撤销编发；多行预报可删除第一行，附加行备注可直接编辑，撤销编发会保留内容回到草稿。新增机场遇到已加载机场时明确提示。
- 导入机场的默认顺序、导入顺序、运行机场筛选/全部及各来源说明移入导入窗口；发布工具栏按钮统一左对齐并移除外部说明。
- 中雨、大雨、中阵雨和大阵雨统一归入强降水；修复 TAF/EC 一键采纳按钮恢复状态后白底白字，并将单机场 TAF/EC 双击展开改为局部行高更新以减少卡顿。
- 预报发布：TAF/EC 的批量操作调整为“`一键采纳`”，只生成可继续编辑的草稿；“`一键编发`”只确认当前编辑结果，不再隐式采纳来源数据。三个批量操作均支持再次点击撤回，且撤回 TAF 或 EC 不会覆盖另一来源的草稿。
- 高温：保留在 EC 行，不会自动进入编辑行或自动编发。导出文本会将连续高温合并为完整时段及温度范围，例如 `阿布扎比：1日07-16Z温度35-42℃。`。
- 文本导出：默认按机场自动选择时区，中国内地使用北京时间，国际机场和港澳台使用世界时。
- 发布表：已编发机场支持增加空白天气行、删除附加天气行；未知天气统一使用“其他”的浅蓝色。区域筛选改为国内、国际两条对齐的独立行，并各自提供“全部”。
- 发布设置：基础过滤、高温、地面结冰、极寒条件拆分；结冰可配置温露差，极寒仅按温度阈值判断。
- 账户显示：工号优先映射为人员管理中的姓名；导入机场和导出文本按钮下方增加用途说明。

> 本文件供跨机器 AI 协作时快速了解项目全貌，每次功能变更同步更新第一部分。

---

## 一、程序概览与架构

### 定位
航空气象报文综合监控告警系统 + 预报质量自动化评定平台。  
双轨架构：**事中监控**（轮询航班+气象报文，红黄绿告警）；**事后评定**（TAF/手工双模式评分、Excel导出）。

### 运行方式
- 统一启动器（推荐）：从交付根目录 `MTWS+OMICS` 双击 `MTWS+OMICS.bat`，或双击同目录的 `MTWS+OMICS.bat.lnk`。启动器同时管理 MTWS、OMICS 与后台 Nginx：MTWS 内部监听 `127.0.0.1:8001`，OMICS 内部监听 `127.0.0.1:8002`，Nginx 对外提供统一入口 `127.0.0.1:8000`。
- 访问地址：MTWS 使用 `http://127.0.0.1:8000/mtws/`，OMICS 使用 `http://127.0.0.1:8000/omics/`。两个前端同源；扫码仍从各软件页面发起，但登录成功后的 token 统一交由 Nginx 管理，任一软件登录后其他软件可复用同一 token，减少不同 IP/入口重复登录导致的掉线。
- 启动器界面只显示两个业务面板：左侧 MTWS / 右侧 OMICS，各自状态灯 + 独立日志。Nginx 是基础设施服务，已隐藏单独监控面板，但仍会随「全部启动」「退出服务」和托盘右键退出一起启动/停止。
- 中控台不再提供扫码登录功能；原登录入口改为说明框，只展示当前统一登录状态（目前谁登录、用户标识、登录来源/时间等）。
- portable Nginx 随 OMICS 携带在 `OMICS/tools/nginx/nginx.exe`，目标电脑不需要额外安装 Nginx；运行时配置生成到 `%LOCALAPPDATA%/MTWS_OMICS_Nginx`，避免 Windows Nginx 中文路径问题。
- 开发调试（会出黑框）：`python main.py`（旧单 OMICS 开发入口，端口 56789；不经过统一 Nginx 入口）
- 生产发布：PyInstaller 打包为 `ForecastTool.exe`（console=False），托盘常驻

### 目录结构
```
├── main.py                  # 入口：启动 Flask+Waitress，CustomTkinter 控制台，pystray 托盘
├── ../launcher.py            # 交付根目录统一启动器：两栏监控 MTWS + OMICS，后台静默管理 Nginx 统一入口
├── ../launcher_config.json   # 【运行时】统一启动器配置：MTWS/OMICS/Nginx 路径与端口
├── ../MTWS+OMICS.bat          # 交付根目录 bat：pythonw 启动 ../launcher.py（无黑框）
├── ../MTWS+OMICS.bat.lnk      # 桌面图标快捷方式，指向 MTWS+OMICS.bat，可复制到桌面
├── tools/nginx/nginx.exe     # portable Nginx，随 OMICS 携带，目标电脑无需额外安装 Nginx
├── assets/weather.ico        # OMICS/打包图标资源
├── assets/weather.png        # OMICS 图标资源
├── server_gui.py            # MTWS 原始托盘控制台（未改动，launcher.py 参考其设计）
├── config.json              # 运行时路径/端口配置（自动生成）
├── backend/
│   ├── app.py               # Flask 应用主体，所有 API 路由（~82KB）
│   └── logic/
│       ├── avwx_standalone_parser.py  # 国际报文解析（avwx，英制→公制）
│       ├── taf_parser.py              # TAF 解析与要素提取
│       ├── metar_parser.py            # METAR 解析（7要素）
│       ├── sf_client.py               # 数字填图/SF平台 HTTP 客户端（扫码登录）
│       └── exporter.py                # 评定结果→Excel 导出（openpyxl）
├── frontend/
│   ├── index.html           # 单页应用入口
│   ├── script.js            # 评分主逻辑（评定计算、数据管理、JSON库读写）
│   ├── publish.js           # 预报发布模块（独立，initPublishModule）
│   ├── export_publish.js    # 发布预览、图片/Excel导出、文字与表格导入
│   ├── airports.js          # 机场基础数据（ICAO、坐标等）
│   └── style.css            # 样式（含 .spinner/.loader 动画）
├── runtime/
│   ├── omics_config.js      # 统一持久配置源（前后端共同读写）
│   └── settings_config.example.json # 首次运行默认配置模板
├── logs/
│   └── runtime.log          # 滚动日志（2MB×5，RotatingFileHandler）
└── backup/                  # 自动备份（auto_YYYYMMDD_HHMMSS/）
```

### 主要功能模块

| 模块 | 说明 |
|------|------|
| 评定计算器 | TAF 自动解析 + 手工录入双模式；7要素逐项打分；AMD溯源 |
| 评分公式 | 总分 = 准确率×50% + 完美率×30% + 优秀率×20% − 空报率×10% − 漏报率×10%；未参评项目不计入总评 |
| JSON 数据库 | 层级化 JSON 持久化评定结果，SQLite 辅助 |
| Excel 导出/逆向同步 | openpyxl 生成格式化 Excel；winreg 穿透 OneDrive 写入物理桌面 `SF预报评定导出` 文件夹；支持 Excel→系统双向同步。预报发布导出不依赖外部模板文件，按原版式直接生成「24小时天气预报」xlsx + PNG |
| 预报发布 | publish.js 独立模块；拉取 NWP 数值预报（open-meteo ECMWF IFS）；管理发布字典表 |
| 发布机场导入 | 运行机场（筛选/全部）、机场分组（可置顶）、文字预报、指定 XLSX/XLSM 可多选组合导入；表格保留机场性质、备注和附加天气行 |
| 事中监控 | 轮询航班数据 + METAR/TAF 实时解析；7要素红黄绿弹窗告警 |
| SF平台登录 | 各软件端口/页面发起扫码登录；登录成功 token 统一由 Nginx 管理并供 MTWS/OMICS 复用，OMICS 前端保存登录信息用于页面状态和请求携带，后端不再作为统一登录态来源。 |
| 运行日志 | 后端 RotatingFileHandler + 前端 PBLOG() 批量上报 `/api/log`；一键复制 copyPublishLog() |

### 主要依赖库

**后端（Python）**
- `flask` + `waitress` — Web 服务器
- `pandas` — 数据处理
- `openpyxl` — Excel 读写
- `customtkinter` / `pystray` / `Pillow` — 桌面 GUI / 托盘
- `winreg`（标准库）— OneDrive 路径穿透
- `avwx`（内嵌 avwx_standalone_parser.py）— 国际报文解析

**前端（原生）**
- `ECharts 5` — 图表
- `Flatpickr` — 日期选择器
- 无其他第三方框架（纯 HTML/CSS/ES6）

---

## 二、更新日志

### v5.8-dev · 2026-08-01（预报发布时段、多来源机场与编发流程整合）
- **调整** 删除系统设置中的“自定义时间基准”，要素过滤和 EC 自动采纳阈值改为铺满面板的双列布局，消除原时间卡片移除后的空白。
- **调整** 发布页日期改为紧凑入口，默认只显示北京时基准日期；点击后才展示基准日期、UTC 开始时次和预报总时长，关闭后不占用头部空间。
- **增强** 应用日期弹层中的任一自定义时段后，标题自动进入自定义模式并按总时长显示“XX小时天气预报”；北京时基准日期与 UTC 起报日期支持跨日正确换算，时间轴和 Excel 导入同步更新。
- **增强** 机场导入可选默认顺序或导入顺序，文字导入按原行序展示；发布页增加国内/国际区域筛选和按运行、机场分组、文字、表格、手动来源清空，区域默认全选并从设置页移除旧入口。
- **优化** 机场分组改为“置顶”语义：置顶组按组顺序及组内机场顺序排列，普通机场按国内/国际和区域排列；新增分组、删除分组及机场重排时保留未保存的组编辑和发布草稿。
- **优化** 高温达到配置阈值时使用“其他”浅蓝色，自动加入 EC 预报及“高温”备注；备注输入可直接删除并在跨机场操作、重绘和确认后持续保存。
- **新增** 地面结冰/极寒配置：仅检查运行机场，结冰按低温且温露点相等、配置回看时段内有降水或低能见度判定，极寒单独判定；结果只写入底部“地面结冰/极寒机场”，不写入逐小时表格。数值请求按回看时长补足历史降水，刷新已确认机场仍更新 TAF 标题。
- **增强** TAF、EC 一键编发均覆盖适航机场并支持再次点击独立撤回；新增“一键全编发”，TAF/EC 同时保留，重合天气使用附加行，不覆盖手工或另一来源的数据。
- **增强** 导出文本可切换北京时和 UTC，同一连续天气沿用跨日/跨月合并规则；表格内风向统一为 16 方位字母代码，文字导出转换为中文风向。
- **调整** EC 雷暴按降水量匹配弱/中/强雷雨，无降水默认弱雷雨，编发备注增加“终端区/本场”；导出文字在雷雨前增加“短时”，不修改原备注。
- **调整** EC 气压改取 Open-Meteo `pressure_msl` 海平面气压并默认展示；配置 schema 升级会为旧配置一次性启用气压显示。
- **优化** 发布头部在窄屏下缩小标题、重排风险统计和日期/预报员信息，日期弹层自动限制在视口内，避免裁切与控件重叠。
- **验证** `backend/app.py` 通过 `py_compile`；前端脚本通过 `node --check`；Edge Playwright 实测桌面及 390px 窄屏，并覆盖自定义 30 小时时段、北京时/UTC 导出、91/92/95/96/99 雷暴量级、海平面气压、双来源编发/独立撤回、无天气适航、导入顺序和来源清空。

### v5.8-dev · 2026-07-27（发布机场多来源导入、双行评估与配置持久化加固）
- **修复** 天气量级配置在并发保存其他设置时被旧快照覆盖的问题：统一配置写入增加进程内锁与原子替换，前端保存成功后立即刷新内存配置；同一天气代码加入新分类时自动从旧分类移除。`SHRA` 已归入「强降水(无雷)类」。
- **修复** 预报发布机场含主行和附加行时只处理主行的问题：机场风险计数、激活状态、确认数据、文本导出及 Excel 结构化导出均遍历同一 ICAO 的全部行；Excel 附加行和逐行备注可再次完整导入，风险机场数按 ICAO 去重。
- **调整** 发布工具栏拆为两行：TAF/EC 数据视图至刷新为第一行，导入机场、导出文本、图片和 Excel 为第二行；原「文表互导」拆为独立的「导入机场」和「导出文本」。
- **新增** 「导入机场」支持多选组合：运行机场可选默认「筛选」或「全部」，常驻机场按已启用组逐项选择，保留原文字导入预报，并支持上传 XLSX/XLSM 或读取 OMICS 根目录 `未来24小时天气预报20260725.xlsm`。表格导入识别日期、起报时间、机场性质、备注、逐小时天气及机场附加行。
- **调整** 发布页首次进入及切换预报时长时不再自动请求/刷新机场表，只有选择机场来源并导入或手动刷新后才加载；未选择的常驻组不参与显示和机场性质判定。
- **增强** 导出文本覆盖全部附加行和备注：风描述放在时段前，「间歇性/短时」等描述放在天气前，不同天气行以分号分隔。
- **修复** 48 小时等长时段表格被容器压缩导致时间列过密、备注消失：长时段按固定小时列宽设置表格最小宽度并使用横向滚动，备注列保持固定宽度。
- **新增** 预报发布「启用要素」即时写入统一配置并在下次打开时恢复，无需重复选择。
- **修复** 席位预报表格为同一机场增加附加行后，提交评定时后行覆盖前行的问题：现按机场和小时合并全部非空行，空白、`NSW` 和重复内容均不会冲掉已有预报。
- **调整** 预报发布大风要素改用中文风向和单位显示，例如 `N17` 显示为「偏北风17米/秒」、`NW20` 显示为「西北风20米/秒」；TAF、EC、手工编辑、粘贴和表格导入统一转换，评定解析继续兼容代码与中文格式。
- **验证** `backend/app.py` 通过 `py_compile`；`script.js`、`publish.js`、`export_publish.js`、`airports.js` 通过 `node --check`；根目录模板和上传分支均实测导入 28 个机场并识别 4 个双行机场；双行及逐行备注的 Excel 导出回读通过；Edge 无头实测 48 小时双行表格、备注及文本导出。

### v5.8-dev · 2026-07-03（Excel 逆向同步与机场预报月末归档修复）
- **修复** 高级管理员「从云盘 Excel 逆向同步」只跟随统计区当前类型同步单一路径的问题。现改为一次扫描已配置的「机场预报」与「席位预报」两个云盘路径，避免默认停在席位预报时机场 Excel 根本未被读取。
- **增强** Excel 逆向同步反馈：后端返回扫描 Excel 数、导入/更新记录数、覆盖月份数，并汇总跳过原因（如路径缺少 `YYYY年`、文件名不符合 `-MMDD.xlsx`、缺少工作表或缺少「机场」列），避免静默跳过导致误判为同步成功。
- **修复** 机场预报月末保存跳日：原保存逻辑从逐时明细第一条 `DDHH` 反推日期，月末跨月时会把 `0630/0100` 等有效期内时次误归为 7 月 1 日。现机场预报按页面评分日期 `-2 天` 归档，例如 7 月 2 日评分保存为 6 月 30 日，7 月 3 日评分保存为 7 月 1 日；席位预报仍按页面评定日期保存。
- **增强** 评分保存一致性：评分成功后锁定当次评分日期，保存时不再受页面日期控件后续变化影响。
- **调整** 机场预报日度统计与明细查询兼容评分日期映射：选择 7 月 2 日可查到实际归档到 6 月 30 日的数据；月度/年度统计仍按实际归档日期计入对应月份，保证月末最后一天不跑到次月。
- **验证** `backend/app.py`、`backend/logic/exporter.py` 通过 `py_compile`；`frontend/script.js` 通过 `node --check`。

### v5.8-dev · 2026-06-24（配置持久化根因修复、权限规则收敛与发布/导出对齐）
- **修复** 48 小时预报致命异常 `loadForecastData: Cannot read properties of undefined (reading 'bg')`。根因：已确认数据按旧时长（24h=25 格）保存，切到 48h（49 格）时附加行 `rowsToRender[r][i]` 尾部越界为 `undefined`。主行有兜底守卫但附加行漏了，现补上同样的兜底默认单元格。
- **调整** 预报发布默认不选中 EC（`defaultShowEc:false`），并改写筛选语义：EC/TAF 未勾选时不作为筛选依据。`hasAlert` 拆分为 `hasAlertEC`/`hasAlertTAF`，最终 `hasAlert =（选中EC && EC告警）||（选中TAF && TAF告警）`。两者都不选则只剩常驻/手动机场，只选 TAF 则忽略 EC。勾选框改为凭缓存实时重算重渲染，不再重新请求 API。
- **修复** 24 小时预报时间轴最右侧的多余“外框”：表头容器靠负 margin 撑满到可视全宽，内部表只到列宽之和，右侧露出深色背景。`syncTimelineHeader` 末尾改为内容窄时容器收紧到表宽、超宽时保持可视全宽走滚动，正文 wrapper 同步收紧，左右边界统一（无头实测 24h/48h/切回三态右边界差≤1px）。
- **修复** 导出图片时间轴对齐与紧贴：克隆头部 padding 改成 18px 但时间轴仍用 -20px 负 margin 导致左右差 2px，且底部 28px padding 与 -20px margin 净剩 8px 深色背景条。改为克隆头 `padding:14px 18px 0 18px`、时间轴容器 `margin:16px -18px 0 -18px` 并清除内联 width，时间轴与正文左右对齐且紧贴无背景条。
- **修复** 导出 Excel 弹窗残留分割图片专属内容：先点“分割图片”生成“单页机场数”控件后再切到 Excel 模式时，`refreshPreview` 的 excel 分支直接 return 未隐藏该控件。现在 excel 分支隐藏并清空 `#export-page-size-controls`。
- **调整** 48 小时预报横向滚动条常驻：将原隐藏的 `#top-scrollbar` 改为 `position:fixed;bottom:0`，仅在正文横向溢出（48h）且发布页可见时显示，跟随正文可视区左右对齐，切走自动隐藏。
- **修复（根因）** 系统设置“配置一段时间后还原成默认”：根因为后端 `save_settings_config` 用 `deep_merge(默认, 前端传入)` 且**不读磁盘已存值**，配合前端每次保存都用整份内存快照整体覆盖；任一加载时配置较旧/默认的会话触发保存（改路径/加人员/初始化），就把阈值、人员等冲回默认。修复：① 后端保存改为 默认→读盘已存→本次传入 三层叠加，传部分块不抹其余字段；② 前端所有保存点改为分块 PATCH（新增 `OMICS_patchSettingsConfig` 与各 block 构造函数），人员只提交 `personnel_dict`、阈值只提交 `thresholds`、路径只提交 `paths`、默认机场只提交 `default_airports`、天气现象只提交 `phenomena_config`、发布配置只提交 `publish`，互不覆盖。
- **修复** OMICS 系统设置权限失效：旧逻辑为“任意账号登录即免密进设置”，且管理员判断依赖会被配置同步污染的 `personnelDict[uid]==='吴霄'`，时灵时不灵。按需求收敛为只认吴霄工号常量 `ADMIN_ID(41060711)`——吴霄扫码登录免密进入并显示「高级管理员配置」；其他任何情况（未登录或非吴霄）必须输管理密码且只能进普通设置、不显示高级管理员配置。`updateDisplayUserName`、`getRealBackupPath` 中的管理员判断一并统一为只认工号。
- **修复（仅打包模式生效）** PyInstaller frozen 后配置路径用 `__file__` 指向 bundle 内部、非持久；`main.spec` 的 `datas` 也未打包 `runtime/`。新增 `_persistent_base_dir()`（frozen 用 `sys.executable` 同级目录）与 `_bundle_resource_dir()`（`_MEIPASS`），配置/人员映射写入持久目录、example 模板优先持久再回退 bundle；`main.spec` 增打 `runtime/settings_config.example.json`。源码模式路径不变（仍 `OMICS/runtime/settings_config.json`），现有配置不受影响。
- **验证** `backend/app.py` 通过 `ast.parse`；`frontend/script.js`、`frontend/publish.js` 通过 `node --check`；后端三层叠加合并语义经独立脚本验证（传空组/部分块不抹其余字段）；时间轴对齐经无头 Chrome 实测。

### v5.8-dev · 2026-06-20（文图互导纠错与世界时识别）
- **新增** 文图互导“文字导入预报”页签内的“纠错检查”按钮，导入前可先检查格式。
- **新增** 无法识别内容的红色错误提示面板：按行标出错误内容、问题片段和原因，并给出标准输入格式示例。
- **调整** 文字导入逻辑：若存在无法识别的行或片段，不再部分静默导入，需修正后再导入，避免漏报/错报。
- **新增** 世界时识别：时间后加 `Z` 按 UTC/世界时解析，例如 `5日00Z-03Z有雷雨`；不加 `Z` 默认按北京时解析。
- **验证** `frontend/export_publish.js`、`frontend/publish.js`、`frontend/script.js` 通过 `node --check`；`backend/app.py` 通过 `py_compile`。

### v5.8-dev · 2026-06-20（预报发布导出与文图互导增强）
- **新增** 预报发布导出拆分为 `导出图片` 与 `导出 Excel` 两个独立入口，不再混在一个“导出图表/Excel”按钮中。
- **新增** 导出预览弹窗：图片导出支持预览；Excel 导出支持表格预览。
- **新增** 图片分页切割：可选择是否分页，可填写每页机场数；未填写时按默认平均分配；每一页均自动保留标题/统计/日期等头部和“地面结冰/颜色说明/发布说明”等尾部。
- **调整** Excel 导出后端不依赖外部 `.xlsm` 模板运行，改为按“未来24小时天气预报”模板观感直接生成可编辑 `.xlsx`：包含深灰标题栏、影响机场表头、风险颜色块、尾部结冰/颜色说明/发布说明等版式。
- **新增** 导出文本升级为“文图互导”：弹窗内增加“导出文本/文字导入预报”页签；可从文本行直接导入机场预报，导入后机场以已编发状态显示。
- **优化** 预报发布界面：隐藏日期与“影响机场”之间的白色横向滚动条占位；预报表头滚动时保持置顶。
- **新增** 前端独立模块 `frontend/export_publish.js`，负责导出预览、图片分页、导出提交和文本导入解析，降低对主发布逻辑的耦合。
- **验证** `backend/app.py` 通过 `py_compile`；`frontend/publish.js`、`frontend/export_publish.js`、`frontend/script.js` 通过 `node --check`。

### v5.8-dev · 2026-06-20（OMICS 系统设置持久化到 JSON）
- **新增** OMICS 统一系统设置配置文件 `runtime/settings_config.json`，用于持久化除机场字典外的系统设置，避免浏览器 `localStorage` 清理、换入口或换电脑后配置丢失。实际运行配置为本机私有文件，不随 Git pull 覆盖。
- **新增** 默认模板 `runtime/settings_config.example.json`，Git 只分发模板；首次运行时如果本机没有 `settings_config.json`，后端会从模板/内置默认值自动生成。
- **新增** 后端配置接口 `/api/settings_config`，支持读取/保存人员映射、云盘路径、默认机场、天气现象量级、天气要素阈值、单机场阈值、预报发布机场分组与极寒积冰/EC 自动配置。
- **调整** 前端设置加载优先级：启动时优先读取 `runtime/settings_config.json`，并回填 `localStorage` 兼容旧逻辑；若配置文件不可用则回退旧本地缓存。
- **调整** 系统设置保存逻辑：人员管理映射、云盘路径、默认机场、天气现象量级、全局/单机场阈值、预报发布分组和 EC 配置保存时同步写入统一 JSON。
- **保留** 机场字典配置继续通过 `/api/save_airports` 写入 `frontend/airports.js`；人员映射继续兼容旧 `personnel_mapping.json` 并与统一设置同步。
- **调整** `.gitignore` 对 `runtime/` 增加例外，允许提交默认模板 `OMICS/runtime/settings_config.example.json`；实际运行配置 `settings_config.json` 保持本机私有，避免下载/更新时覆盖各席位本地设置。
- **验证** `backend/app.py` 通过 `py_compile`；`frontend/script.js`、`frontend/publish.js` 通过 `node --check`；`runtime/settings_config.example.json` 通过 Python JSON 读取校验。

### v5.8-dev · 2026-06-15（登录弹窗恢复与 OMICS 设置权限修正）
- **修复** MTWS current 模式未登录时自动弹出丰声扫码二维码的行为：页面初始化会先判断统一登录态/前端 localStorage token；如无 token 或统一态已标记过期，立即弹出登录二维码；如存在本地 token，则先调用 `validate-token` 轻量校验，401 时清理本地态并弹二维码。
- **修复** OMICS 系统设置权限：未登录访问设置必须输入管理密码；已登录账号可进入普通设置；只有吴霄账号（`41060711` / 显示名“吴霄”）能显示「高级管理员配置」，未登录输密码也不会显示高级管理员配置。
- **调整** OMICS 设置侧栏「机场字典配置」按钮颜色为白色，并通过 CSS 覆盖 active 状态，避免选中后变蓝。
- **验证** `launcher.py` 通过 `py_compile`；`MTWS/main.js`、`OMICS/script.js` 通过 `node --check`。

### v5.8-dev · 2026-06-15（Token 过期实时监控与三端自动登出）
- **新增** 控制台 token 实时监控：`launcher.py` 后台每 60 秒调用 SF 航班接口（与 MTWS validate-token 同源）轻量校验当前统一 token；返回 401（过期/异地登录被挤下线）时自动清空统一登录态并标记 `expired`，控制台信息框变为橙色「登录已过期｜请重新扫码登录」。网络错误等异常不误判为过期，保留登录态。
- **调整** 统一登录态保存策略：token 仍由 MTWS/OMICS 前端 localStorage 持有，中控台**不再**从本机磁盘 token 自动恢复登录，避免“前端和中控台都关闭后，再单独打开中控台却默认登录”。`%LOCALAPPDATA%/MTWS_OMICS_Nginx/auth_state.json` 只写无 token 的安全占位，用于覆盖旧版可能留下的 token 缓存。
- **新增** 三端联动自动登出/回灌：MTWS 与 OMICS 前端登录后启动后台轮询（每 5 秒）`/auth/status`。区分两种统一态为空的场景：`expired:true`（真过期）则自动登出本页面（MTWS 显示「登录过期」错误页并停止自动刷新，OMICS 弹窗提示并回到未登录状态）；`expired:false`（控制台刚重启、状态丢失）则由仍打开的前端页面把本地 token 回灌给控制台，无需刷新页面。若前端也已关闭，中控台不会默认登录，需重新打开前端页面由 localStorage 回灌。
- **说明** 处理了“token 在别的电脑登录或长时间未请求数据后失效”的场景：以前本地仍保存 token、显示已登录，但业务请求报 API 失败；现在由控制台主动探测失效并驱动三端登出。
- **验证** `launcher.py` 通过 `py_compile`（无 SyntaxWarning）；`MTWS/main.js`、`OMICS/script.js` 通过 `node --check`；实测持久化：推送 token 后 kill 并重启启动器，**不动前端**的情况下 `/auth/status` 立即返回 `logged_in:true`；登出后重启保持未登录；在 SF 内网不可达的开发机上校验周期不会误登出。

### v5.8-dev · 2026-06-15（图标样式更新、标题栏优化与登录态缓存修复）
- **调整** 重新生成托盘/桌面图标：按最新样式将 `托盘图标.png` 重新转为 `托盘图标.ico`（多尺寸 16~256）并删除 png；`桌面图标.ico` 采用最新样式；重建 `MTWS+OMICS.bat.lnk` 快捷方式并指向 `桌面图标.ico`。
- **调整** 标题栏：删除「航空气象统一服务启动器」前的小飞机 emoji。
- **修复** 窗口缩小时的遇遮顺序：将「全部启动/路径配置/退出服务」三个按钮直接钉在标题栏右边缘，登录状态标签紧贴按钮左侧；窗口缩小时从登录状态标签的右侧开始被逐渐遮挡，按钮始终可见可点击。
- **修复** 席位电脑登录态识别根因：Nginx 静态 JS/CSS 原来无 Cache-Control 头，服务端更新 `main.js` 后浏览器仍运行旧脚本（不含回灌登录态的修复）；在生成的 nginx 配置中为 `/static/*.js|css` 加上 `no-cache, no-store, must-revalidate`，确保各机总是拉取最新脚本。说明：登录态后端与路径配置无关（`/auth/` 代理到本机 19529 的 broker，跳过 Django），UNC 路径（如 `//MTWS-OMICS/MTWS`）不影响 token 回灌，问题为浏览器缓存旧 JS。
- **验证** `launcher.py` 通过 `py_compile`（无 SyntaxWarning）；重启启动器后实测：生成的 nginx 配置含 `\.(js|css)$` 静态缓存规则，`http://127.0.0.1:8000/static/js/main.js` 返回 `Cache-Control: no-cache, no-store, must-revalidate`；token 推送（:19529 /auth/update）与 `:8000 /auth/status` 闭环正常。

### v5.8-dev · 2026-06-14（目录/图标/BAT 重命名、登录态识别与数据库工具同步）
- **调整** 交付图标拆分：启动器窗口/任务栏/桌面快捷方式使用 `桌面图标.ico`，系统托盘使用 `托盘图标.ico`；原 `桌面图标.png`/`托盘图标.png` 已转为 ico 并删除 png，两个 ico 均纳入 Git 版本管理。
- **调整** 统一服务器 bat 名称：`统一服务器启动器.bat/.lnk` 重命名为 `MTWS+OMICS.bat/.lnk`，快捷方式图标指向 `桌面图标.ico`。
- **调整** OMICS 业务目录名：`OMICS 5.8` 重命名为 `OMICS`；同步更新 `launcher.py`、`launcher_config.json`、`.gitignore` 中的路径引用。
- **修复** 席位电脑找不到数据库管理工具：强制将 `MTWS/data/sqlite_database/database_manage_allinone.py` 纳入 Git（原本已 tracked，本次再次确认）；`launcher.py` 的数据库工具入口增加回退：配置推导的 MTWS 根目录找不到时，回退到随包交付的 `MTWS/data/sqlite_database/` 下的工具，避免本地配置路径异常导致无法启动。
- **修复** MTWS 重启后登录态识别：退出所有服务再打开后，Nginx/启动器的统一登录态（仅存内存）会清空；修改 MTWS 前端 `initCurrentModeAuth`，在统一登录态为空但浏览器本地仍有可用 token 时，主动回灌 `/auth/update`，让控制台信息框立即识别为已登录（与 OMICS 前端行为一致）。
- **验证** `launcher.py` 通过 `py_compile`；`launcher_config.json` JSON 解析通过；`database_manage_allinone.py` 通过 `py_compile`。

### v5.8-dev · 2026-06-12（启动器登录态识别、托盘图标、无模板导出与路径浏览）
- **增强** 启动器登录态识别：OMICS 前端打开后，会把浏览器缓存里已存在的 token（`sf_weather_token`/`mtws_token`）主动回灌到 Nginx 统一登录态（`/auth/update`），启动器信息框据此正确显示「已登录」及用户标识，无需重新扫码。
- **调整** 系统托盘/窗口图标：启动器优先使用项目根目录 `系统图标.ico`（依次回退 `图标.png`），窗口标题栏与托盘图标统一，该图标已纳入 Git 版本管理。
- **重做** 预报发布导出：图表 PNG 与 Excel 不再依赖外部 `.xlsm` 模板文件，后端用 openpyxl 按原模板版式直接生成 `.xlsx`（标题区、计数区、起报时间、机场行、24 小时天气列、颜色图例、发布说明），导出文件名统一为「24小时天气预报_时间戳」，内容与预报发布界面一致。
- **新增** 系统设置路径浏览：「JSON 备份」和「图表导出云盘配置」改为只读输入框 + 「浏览」按钮，通过 `/api/select_folder` 选择目录并持久化到 LocalStorage。
- **验证** `script.js` 通过 `node --check`；`app.py`、`launcher.py` 通过 `py_compile`。

### v5.8-dev · 2026-06-11（扫码登录调整为 Nginx 统一 Token 管理）
- **调整** 扫码登录入口：登录动作仍在各业务软件自己的页面/端口触发，MTWS 和 OMICS 均可独立发起扫码。
- **调整** token 归属：扫码成功后的 token 统一由 Nginx 管理，不再由统一中控台或 OMICS 后端作为跨系统唯一持有方。
- **增强** token 复用：不管从 MTWS 还是 OMICS 登录，其他软件都应复用 Nginx 当前 token，避免不同 IP、不同入口或重复扫码导致账号互相挤下线。
- **取消** 中控台扫码登录功能：统一启动器/中控台原登录区域改为说明框，只显示当前谁已登录、用户标识、登录来源和登录时间等状态信息。
- **调整** OMICS 登录态：OMICS 的登录信息不再放在后端作为统一状态来源，改为由前端保存；业务请求需要 token 时通过前端携带或通过 Nginx 统一登录态获取。
- **说明** LocalStorage 仍可用于前端页面展示、兼容旧 key 和刷新后恢复 UI，但跨 MTWS/OMICS 的 token 权威来源是 Nginx。

### v5.8-dev · 2026-06-09（MTWS+OMICS 交付目录、Nginx 同源入口与启动器精简）
- **调整** 交付目录统一为 `MTWS+OMICS`：顶层放置 `launcher.py`、`launcher_config.json`、`统一服务器启动器.bat/.lnk`，业务目录为 `MTWS/` 与 `OMICS 5.8/`。
- **调整** 统一启动器架构：MTWS(Django) 内部 `127.0.0.1:8001`，OMICS(Flask+Waitress) 内部 `127.0.0.1:8002`，Nginx 对外统一入口 `127.0.0.1:8000`。
- **新增** OMICS 统一访问入口：`http://127.0.0.1:8000/omics/`；Nginx 同时保留 `/api/`、`/assets/` 等 OMICS 旧绝对路径兼容。
- **新增** portable Nginx：随 OMICS 放置于 `OMICS 5.8/tools/nginx/nginx.exe`，目标电脑无需额外安装 Nginx；运行配置生成到纯英文路径 `%LOCALAPPDATA%/MTWS_OMICS_Nginx`，规避 Windows Nginx 中文路径报错。
- **调整** 启动器 UI：界面只保留 MTWS / OMICS 两个业务监控面板，Nginx 监控栏隐藏为后台基础设施；「全部启动」「退出服务」和托盘右键退出仍会统一启动/停止 Nginx、MTWS、OMICS 及端口残留监听进程。
- **增强** 同源登录态：OMICS 前端在 LocalStorage 中同步 `sf_weather_token` 与 `mtws_token`、`sf_userId` 与 `mtws_userCode`，配合 MTWS 减少两个程序重复扫码互相挤下线。
- **修复** 迁移后的配置路径：`launcher_config.json` 改为 `MTWS+OMICS/MTWS` 与 `MTWS+OMICS/OMICS 5.8`，避免旧中文乱码路径影响跨机运行。
- **验证** `launcher.py`、`backend/app.py` 通过 `py_compile`；`frontend/script.js`、`frontend/publish.js` 通过 `node --check`；Nginx 配置 `-t` 成功。

### v5.6-dev · 2026-06-08（24小时模板导出、登录姓名映射与发布表细节修复）
- **调整** 发布表机场删除：机场名单元格右上角 `×` 点击后直接删除，不再二次确认。
- **调整** 非常驻机场确认适航逻辑：编辑内容为空并确认编发时，若该机场不是常驻机场，则直接从发布表移除；常驻机场仍保留为“适航”确认态。
- **重做** 预报发布 Excel 导出：导出 Excel 改为复制 `未来24小时天气预报20260507（模版）（如提示宏已被禁用，点击【启用内容】）.xlsm` 模板并保留宏，填写 `24小时天气预报` 工作表；起报时间写入 `C6`，机场从第 9 行开始写入，24 小时天气写入 `D:AA`。
- **修复** HTML 表格合并列导致 Excel 天气列偏移的问题：前端新增结构化 `publish_rows` 导出数据，后端优先使用结构化数据填模板。
- **新增** OMICS 后端人员映射缓存接口 `/api/personnel_mapping`，高级管理员“人员映射管理”的浏览器本地配置会同步到后端 `personnel_mapping.json`，供统一启动器读取。
- **调整** 统一启动器扫码登录显示：登录成功后不再直接显示工号，而是按人员映射显示姓名，例如 `吴霄 登录成功`。
- **新增** 统一启动器“退出登录”按钮：清空控制台登录态，并调用 OMICS `/api/auth/logout` 退出后端会话；中转接口随即返回未登录状态。
- **验证** `frontend/publish.js`、`frontend/script.js` 通过 `node --check`；`backend/app.py`、`launcher.py` 通过 `py_compile`；模板导出通过 Flask test client 生成 `.xlsm` 并验证 `C6/A9/B9/D9/E9` 写入正确。

### v5.6-dev · 2026-06-08（预报发布界面交互与导出优化）
- **优化** 预报发布导出文本：同一日期的时段只写一次日期，如 `5日04-07时有...`；不跨月时不写月份，跨天/跨月时自动补齐日期/月信息。
- **补强** 导出图表/Excel入口：前端导出前检查 `html2canvas` 是否加载，导出成功提示保存目录与文件名；后端 `/api/export_publish` 原有 PNG + Excel 保存逻辑保持可用。
- **修复** 确认编发后的右键撤销菜单：仅在备注列右键时出现，鼠标移出备注/菜单后自动消失，不再整行任意位置触发。
- **优化** 机场增删：去掉右键删除机场，改为机场名单元格右上角 hover 显示 `×` 删除；右键菜单移除红/黄/绿/删除标记与展开/收起机场入口，菜单文字去掉颜色和图标。
- **修复** 插入/添加机场后只出现空行的问题：新增机场加入强制显示集合后重新执行数据加载，确保自动获取最新 TAF 与 EC 数据。
- **修复** 附加行删除：行内有内容时删除会二次确认，避免误删后后续操作又复现异常空行。
- **优化** 表格编辑输入法体验：选中单元格后直接键入时不再把第一个字母强行写入输入框，优先让输入法接管输入。
- **修复** 展开后的 TAF/EC 明细复制：天气、风、能见度、温度、气压等明细单元格补齐选择坐标，支持选区复制和再次复制粘贴。
- **调整** 广州不再显示为“备选”分类，按普通机场处理。
- **修复** 编辑栏无天气点击确认后机场被自动删除的问题：空内容确认统一保存为“适航”确认态，不再依赖常驻机场豁免。
- **验证** `frontend/publish.js` 通过 `node --check`，`backend/app.py` 通过 `py_compile`。

### v5.6-dev · 2026-06-08（统一控制台登录态中转与启动器交互修复）
- **新增** 统一控制台本地登录态中转接口：`launcher.py` 启动仅监听 `127.0.0.1:19529` 的 `/auth/status`，控制台作为唯一 token 持有方；扫码成功后顶部按钮由「扫码登录」更新为「工号 登录成功」，避免多个业务程序重复扫码导致账号互相挤下线。
- **调整** OMICS 后端登录/取数流程：`backend/app.py` 的 `/api/auth/status`、`/api/fetch_data`、`/api/fetch_flights` 优先读取控制台中转 token；即使前端仍传旧 token，后端也优先使用控制台 token，降低 OMICS 与 MTWS 并行时的登录冲突。
- **增强** MTWS 路径与启动体验：默认识别与 OMICS 项目目录平级的 `../MTWS/mtws_django/manage.py`；路径配置保存后自动启动未运行服务；外部接管服务被误关后自动恢复为可点击「启动」状态。
- **调整** 统一启动器双栏布局：MTWS / OMICS 面板改为 grid uniform 等宽布局，避免 MTWS 因多一个「数据库管理工具」按钮导致框体比 OMICS 更宽。
- **说明** MTWS 本体未改动；后续如需接入统一登录，只需在 MTWS 业务请求前读取 `http://127.0.0.1:19529/auth/status` 获取 `token/userCode/login_time`，不要再独立扫码登录。
- **验证** `launcher.py` 与 `backend/app.py` 均通过 `py_compile`。

### v5.6-dev · 2026-06-08（统一启动器修复与 MTWS 根目录适配）
- **修复** `统一服务器启动器.bat` 通过 `cmd start` 启动时在中文/特殊字符路径下会把 `launcher.py` 截断为 0 字节的问题；改为 PowerShell `Start-Process` 数组参数启动，规避批处理路径解析坑，并实测启动后 `launcher.py` 不再被清空。
- **调整** 扫码登录窗口：删除 token 文本框与「复制Token」按钮，不再展示/复制一次性 token；扫码后只完成控制台服务登录态写入，避免多个程序重复登录导致账号互相下线。
- **补齐** 统一控制台从 `server_gui.py` 继承的能力：服务信息卡显示地址/端口/协议，MTWS 面板增加「数据库管理工具」入口，顶部增加「退出服务」。
- **增强** MTWS 路径配置：可直接选择 `server_gui.py` 所在程序根目录，launcher 自动定位 `mtws_django/manage.py` 并按 `server_gui.py` 的方式执行 `runserver host:port`；也兼容旧配置中直接选择 `manage.py` 或 `server_gui.py`。
- **验证** `launcher.py` 通过 `py_compile`；用临时 MTWS 标准目录验证根目录、`server_gui.py`、`manage.py` 三种配置均可解析到启动入口。

### v5.6-dev · 2026-06-08（启动器单文件化与根目录清理）
- **合并** `run_server.py` 逻辑到 `launcher.py`：OMICS 服务由 launcher 内联 subprocess 启动 Flask+Waitress，不再需要单独的 `run_server.py`。交付统一控制台时，核心只需 `launcher.py` + `统一服务器启动器.bat` + `assets/weather.*`（如需图标快捷方式再带 `统一服务器启动器.lnk`）。
- **清理** 根目录重复启动器：删除 `run_server.py`、`启动(无黑框).bat`、`统一启动器(无黑框).bat`，根目录只保留 `统一服务器启动器.bat` 一个 bat。
- **调整** 路径配置：OMICS 侧从选择 `run_server.py` 改为选择项目根目录（需包含 backend/frontend），兼容旧配置中的 run_server 字段并自动折算为项目根目录。
- **保留** 通用「扫码登录/Token」窗口：界面不绑定 OMICS，只输出 token 并提供复制按钮；当前调用右侧服务接口，后续 MTWS 可由其他人对接复用。
- **验证** `launcher.py` 通过 `py_compile`；无 `run_server.py` 情况下实测可启动 OMICS 内联服务并监听 56789。

### v5.6-dev · 2026-06-08（扫码登录文案与启动路径说明）
- **调整** `launcher.py` 顶部扫码入口文案：由面向 OMICS 的登录入口改为通用「扫码登录/Token」窗口。窗口标题与说明不再写 OMICS，只负责通过当前右侧服务接口获取并显示 token，提供复制按钮；MTWS 或其它程序后续可由其他人对接复用该 token。
- **说明** 当前 `统一启动器(无黑框).bat` / `统一服务器启动器.bat` 与 `launcher.py` 需要放在同一文件夹，因为 bat 使用 `%~dp0launcher.py` 定位脚本。若要放桌面或其它目录，应移动 `.lnk` 快捷方式，不要移动 bat；若必须移动 bat，需要把 launcher.py 绝对路径写入 bat。
- **验证** `launcher.py` 与 `run_server.py` 均通过 `py_compile` 语法检查。

### v5.6-dev · 2026-06-08（误删恢复）
- **恢复** 误删的 `run_server.py`：该文件仍是当前 `launcher.py` 启动 OMICS 无界面服务的必要入口，不能删除。
- **恢复/重建** 启动脚本：从备份恢复 `统一启动器(无黑框).bat`，重建 `启动(无黑框).bat`；保留 `统一服务器启动器.bat/.lnk` 作为带天气图标的统一入口别名。
- **清理** 删除临时探测文件 `_omics_inline.py`、`_probe_launcher.py`。
- **验证** `launcher.py` 与 `run_server.py` 均通过 `py_compile` 语法检查；测试进程已清理，56789/8000 端口未被占用。

### v5.6-dev · 2026-06-08（统一服务器启动器修订）
- **注意** 本节为一次未完全落地的设计记录：曾计划将 OMICS 服务内联进 `launcher.py` 并删除 `run_server.py`，但当前实际版本已恢复为 `launcher.py` + `run_server.py` 的稳定方案。
- **新增** 天气图标：`assets/weather.ico` / `assets/weather.png`；保留 `统一服务器启动器.bat` 与带天气图标的 `统一服务器启动器.lnk` 作为可选启动入口。

### v5.6-dev · 2026-06-07（统一启动器）
- **新增** `launcher.py` 统一服务启动器：一个入口双屏并行启动/监控 MTWS(Django,8000) 与 OMICS(Flask,56789)。两服务对称处理：subprocess + CREATE_NO_WINDOW（无黑框）+ 读 stdout 实时显示。左 MTWS / 右 OMICS 独立日志面板 + 状态灯；任一未启动显示「服务未启动」。设计沉淀自 server_gui.py（原文件未动，MTWS 显示效果不变）。
- **新增** `launcher_config.json` 启动器配置（两服务路径/端口可配，不必同文件夹）。

### v5.6-dev · 2026-06-07

### v5.6-dev · 2026-06-06
- **修复** 预报发布「导出文本」时间格式缺少日期，改为「X月X日HH时」，跨日时日期自动推算

### v5.6-dev · 2026-06-03
- **修复** `publish.js` 3处模板字符串损坏（反引号/`${}`被吃掉），根因：整个文件解析失败导致 `initPublishModule` 未定义，引发"时间不加载/无动画/无数据"三症状
- **修复** `style.css` 缺少 `.spinner` 类定义（代码用 `.spinner`，只有 `.loader` 有动画），补充 spin 动画
- **修复** `publish.js` NWP 抓取 `.catch(()=>[])` 静默吞错，改为记录 HTTP 状态/异常原因
- **新增** 运行日志系统：`main.py`+`app.py` 接入 `logging`，写 `logs/runtime.log`（滚动 2MB×5）；新增 `/api/log` 接口收集前端日志；前端加 `PBLOG()` 日志器 + `copyPublishLog()` 一键复制

## 2026-09-19 功能更新

- 预报发布 Excel 文件名统一为 `未来24小时预报YYYYMMDD.xlsx`。
- 未来 24 小时席位预报支持扫描 Excel 日期和起报时间；扫描失败会自动按目标机场下载实况。
- 未来 8/12/4 小时及自定义时段继续使用原有目标机场实况下载流程。
- 机场导入界面分为“运行机场与机场分组”“文字导入预报”“表格导入”三个区域。
- 机场分组支持置顶、补充说明、全选，导入时显示分组说明。

## 项目简介

OMICS 用于航空气象报文监控、机场预报发布、席位预报评定和评定结果归档，访问入口为 `http://127.0.0.1:8000/omics/`。
