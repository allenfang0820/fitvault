---
title: ACS 足迹与 Memory Gallery 实施任务清单
aliases:
  - 足迹实施任务清单
  - Footprint and Memory Gallery Task List
version: v0.1.0
status: Planning Freeze
type: Task List
scope: ACS 足迹页、生涯足迹地图、赛事相册 Memory Gallery
source:
  - docs/acs_next_footprint_memory_gallery_delivery_manual.md
updated: 2026-07-13
---

# ACS 足迹与 Memory Gallery 实施任务清单

## 0. 使用说明

本文档以 `docs/acs_next_footprint_memory_gallery_delivery_manual.md` 为目标依据，把足迹页后续开发拆成可逐项执行、可独立验收的工程任务。

后续每个任务执行前，必须先读取交付手册和本任务清单，确认当前任务边界。

总目标：

```text
足迹页
├── 生涯足迹：暗黑地图，按省份 / 州 / 行政区域点亮
└── Memory Gallery：按赛事组织相册，支持相册展开与单图大图
```

## 1. 全局硬约束

所有任务必须遵守：

- Activity 是唯一事实源。
- 后端输出安全 ViewModel，前端只负责渲染。
- 前端不得根据标题、城市、日期或 DOM 文本推断地理区域。
- 前端不得读取 raw FIT、`points_json`、`track_json`、本地路径、`storage_ref` 或 SQLite schema。
- 生涯足迹覆盖所有有可靠地理信息的 Activity，不只限赛事。
- Memory Gallery 必须按 Race Event / 赛事 Activity 组织相册。
- Memory Gallery 必须复用 Activity Detail 已有赛事照片、排序与安全预览。
- 相册封面必须复用第一张图逻辑，并与 Overview Banner 保持一致。
- 中国-only 足迹必须显示中国地区地图，并包含台湾区域。
- 存在海外足迹必须显示世界地图。

## 2. 任务总览

| 编号 | 任务 | 模块 | 优先级 | 依赖 | 交付物 |
| --- | --- | --- | --- | --- | --- |
| FM-00 | 现状审计与基线冻结 | 全局 | P0 | 无 | 审计记录、风险清单 |
| FM-01 | 生涯足迹数据契约冻结 | 生涯足迹 | P0 | FM-00 | API 契约、测试样例 |
| FM-02 | 地理区域归一 Resolver | 生涯足迹 | P0 | FM-01 | 区域归一函数、后端单测 |
| FM-03 | `get_career_footprint` 只读 API | 生涯足迹 | P0 | FM-02 | 后端 API、pywebview envelope、契约测试 |
| FM-04 | 地图资源与区域 key 对齐 | 生涯足迹 | P0 | FM-01 | 中国/世界地图 key 映射、静态契约测试 |
| FM-05 | 暗黑地图前端骨架 | 生涯足迹 | P1 | FM-03, FM-04 | 地图 UI、区域点亮、空态 |
| FM-06 | 地图交互与详情回跳 | 生涯足迹 | P1 | FM-05 | hover/click 摘要、Activity Detail 回跳 |
| FM-07 | Memory Gallery 相册 ViewModel | Memory Gallery | P0 | FM-00 | 相册 API 数据、后端单测 |
| FM-08 | Memory Gallery 相册墙前端 | Memory Gallery | P1 | FM-07 | 4:3 赛事相册卡片墙 |
| FM-09 | 单场赛事相册展开 | Memory Gallery | P1 | FM-08 | 照片网格、返回相册墙 |
| FM-10 | 单张照片大图预览 | Memory Gallery | P1 | FM-09 | 大图 modal、关闭、上一张/下一张 |
| FM-11 | 安全边界与前端零推断验收 | 全局 | P0 | FM-03, FM-07, FM-10 | 自动化边界测试 |
| FM-12 | 真实数据与视觉验收 | 全局 | P1 | FM-06, FM-10, FM-11 | 验收记录、截图或手工清单 |
| FM-13 | 本地行政区形状点亮地图 | 生涯足迹 | P1 | FM-12 | SVG path 区域资源、shape 填色渲染 |
| FM-15 | ECharts GeoJSON Choropleth 足迹地图 | 生涯足迹 | P1 | FM-14 | 本地 GeoJSON 地图资源、registerMap 渲染、CN 下钻 |

## 2.1 执行状态

| 编号 | 状态 | 最近记录 | 下一步 |
| --- | --- | --- | --- |
| FM-00 | Done | 已完成现状审计、首个工程级提示词与执行日志；验证 `tests/test_career_race_map_api.py tests/test_career_race_map_frontend.py` 通过 | 已进入 FM-01 |
| FM-01 | Done | 已冻结 `get_career_footprint` ViewModel 契约；验证 `tests/test_career_footprint_contract.py` 通过 | 已进入 FM-02 |
| FM-02 | Done | 已实现地理区域归一 Resolver；验证 `tests/test_career_footprint_api.py tests/test_career_footprint_contract.py` 通过 | 已进入 FM-03 |
| FM-03 | Done | 已新增 `get_career_footprint` 只读 API、pywebview envelope 与 JS API 契约；验证目标测试通过 | 已进入 FM-04 |
| FM-04 | Done | 已新增本地地图区域资源并验证后端 key 对齐；目标测试通过 | 已进入 FM-05 |
| FM-05 | Done | 已实现暗黑地图前端骨架，接入 `get_career_footprint`、本地区域资源、区域点亮与空态；目标测试通过 | 已进入 FM-06 |
| FM-06 | Done | 已实现地图 hover/focus 摘要、click 详情面板、代表 Activity 回跳；目标测试通过 | 已进入 FM-07 |
| FM-07 | Done | 已实现 `get_career_memory_gallery` 赛事相册 ViewModel、pywebview wrapper、JS API 契约与后端测试；目标测试通过 | 已进入 FM-08 |
| FM-08 | Done | 已实现 Memory Gallery 4:3 赛事相册墙前端，接入 `get_career_memory_gallery`；目标测试通过 | 已进入 FM-09 |
| FM-09 | Done | 已实现单场赛事相册展开、照片网格、空相册状态与返回相册墙；目标测试通过 | 已进入 FM-10 |
| FM-10 | Done | 已实现单张照片大图预览、关闭、上一张/下一张和键盘 ESC/左右键；目标测试通过 | 已进入 FM-11 |
| FM-11 | Done | 已新增足迹 + Memory Gallery 组合安全测试，并通过前端零透传/后端零泄露边界验证 | 已进入 FM-12 |
| FM-12 | Done | 已完成真实库 API 验收、静态视觉契约验收、验收报告与最终相关回归；未执行 Windows/打包/截图验收并已记录 | 已进入 FM-13 |
| FM-13 | Done | 已将足迹地图从锚点点亮升级为本地 SVG path 行政区 shape 填色；定向测试通过 | 后续可替换更精确行政区 path 资源 |
| FM-14 | Done | 已将中国地图替换为本地真实省级边界 path，世界地图使用随包 Natural Earth 本地底图；空相册封面 fallback 对齐 Overview Banner 标题艺术字 | 已完成定向回归 |
| FM-15 | Done | 已按最佳实践将足迹地图升级为本地 GeoJSON + ECharts registerMap 静态 Choropleth；世界图完整轮廓国家级点亮，中国 / 日本可下钻并可返回世界图；首次进入足迹页会重绘地图，台湾基础边界保持可见；地图视窗与 ECharts 填充比例已调大 | 已完成定向回归 |

## 3. 里程碑划分

### Milestone 1：契约与后端闭环

目标：

- 冻结生涯足迹和 Memory Gallery 的 ViewModel。
- 后端能稳定返回地图区域数据和赛事相册数据。
- 自动化测试覆盖核心事实边界。

包含任务：

- FM-00
- FM-01
- FM-02
- FM-03
- FM-07
- FM-11 的后端部分

### Milestone 2：生涯足迹地图前端

目标：

- 足迹页显示暗黑地图。
- 中国-only 显示中国地图。
- 海外足迹触发世界地图。
- 区域能点亮、能查看摘要、能回跳代表 Activity。

包含任务：

- FM-04
- FM-05
- FM-06

### Milestone 3：Memory Gallery 前端

目标：

- Gallery 按赛事显示 4:3 相册卡片。
- 点击相册展示所有照片。
- 点击照片打开大图。
- 封面与 Overview Banner 第一张图逻辑一致。

包含任务：

- FM-08
- FM-09
- FM-10

### Milestone 4：真实数据与跨端验收

目标：

- 当前真实库可正确展示。
- 构造海外样例可触发世界地图。
- macOS 当前工作区视觉与交互可用。
- 后续 Windows / 打包验证有清单可执行。

包含任务：

- FM-11
- FM-12

## 4. 详细任务

### FM-00：现状审计与基线冻结

目标：

确认当前 `Race Map / 赛事足迹`、Activity Detail 赛事照片、Overview Banner、Memory Gallery 轻量实现的真实状态，作为后续改造基线。

范围：

- `career_backend.py`
- `main.py`
- `track.html`
- `docs/js_api_contract.json`
- `tests/test_career_race_map_api.py`
- `tests/test_career_race_map_frontend.py`
- Activity Detail 赛事照片相关测试

必须产出：

- 当前 API 与前端入口列表。
- 当前真实 SQLite 数据中可用于足迹和相册的字段清单。
- 已有照片排序 / Banner 选择逻辑的代码位置。
- 不应复用或需要替换的旧 Race Map 点位逻辑。

验收标准：

- 明确哪些代码可复用。
- 明确哪些旧能力只是历史基础。
- 不修改业务逻辑，除非发现文档明显错误需要补充说明。

建议验证：

```bash
python3 -m pytest tests/test_career_race_map_api.py tests/test_career_race_map_frontend.py -q
```

### FM-01：生涯足迹数据契约冻结

目标：

冻结 `get_career_footprint(filters?)` 的 ViewModel，不先做 UI。

范围：

- API 返回字段
- 地图模式字段
- 区域列表字段
- summary/status 字段
- 缺地理信息 Activity 的表达方式

建议契约：

```json
{
  "map_mode": "china",
  "regions": [],
  "without_region": [],
  "summary": {},
  "filters": {},
  "status": {}
}
```

关键规则：

- `map_mode` 只能由后端返回。
- `map_mode = china` 表示只渲染中国地区地图。
- `map_mode = world` 表示渲染世界地图。
- `regions[].region_key` 必须能与前端地图资源匹配。
- `without_region` 只能说明缺失，不得猜测区域。

验收标准：

- 文档和测试中明确中国-only、海外、缺地理信息三类样例。
- 契约禁止 raw FIT、points、本地路径、SQLite schema。
- 契约允许普通 Activity 进入生涯足迹。

建议测试文件：

- `tests/test_career_footprint_api.py`
- `tests/test_career_footprint_contract.py`

### FM-02：地理区域归一 Resolver

目标：

实现后端地理区域归一逻辑，把 Activity 地理字段转成稳定的 `footprint_region_key`。

输入字段候选：

- `region_country`
- `country`
- `countryName`
- `region`
- `region_display`
- `region_city`
- `city`
- `cityName`
- `start_lat`
- `start_lon`

实现要求：

- 优先使用已有结构化国家 / 省州 / 城市字段。
- 中国城市缺省份时，可使用受控城市到省份映射补齐。
- 台湾必须归入中国地区地图的可渲染区域。
- 海外缺州/省但有国家时，先归一到国家级区域。
- 无可靠地理信息时返回 `without_region`，不得强行点亮。

非目标：

- 不调用在线地理编码。
- 不从标题解析城市。
- 不从轨迹 points 计算区域。

验收标准：

- 中国城市可映射到省级区域。
- 台湾区域可独立点亮。
- 海外国家可触发 `map_mode = world`。
- 缺失地理信息不会被误点亮。

建议测试：

```bash
python3 -m pytest tests/test_career_footprint_api.py -q
```

### FM-03：`get_career_footprint` 只读 API

目标：

新增后端只读 API，并通过 `main.Api` 暴露给前端。

改动范围：

- `career_backend.py`
- `main.py`
- `docs/js_api_contract.json`
- tests

实现要求：

- 读取未删除 Activity。
- 汇总普通 Activity 和赛事 Activity。
- 输出 `regions`、`without_region`、`summary`、`status`。
- 支持基础筛选：`sport/year`。
- 使用统一 `{ok, code, msg, data, traceId}` envelope。
- 不返回 raw FIT、points、完整路线、本地路径、SQLite schema。

验收标准：

- 无 `activities` 表时返回稳定空态。
- 中国-only 数据返回 `map_mode = china`。
- 海外数据返回 `map_mode = world`。
- 普通 Activity 参与区域统计。
- 删除 Activity 不参与统计。
- pywebview envelope 通过测试。

建议测试：

```bash
python3 -m pytest tests/test_career_footprint_api.py tests/test_career_phase9_pywebview_envelope.py -q
```

### FM-04：地图资源与区域 key 对齐

目标：

确定前端用于渲染中国地图和世界地图的资源方案，并与后端 `region_key` 对齐。

可选方案：

- 内置简化 GeoJSON / TopoJSON。
- 使用 ECharts map 注册地图。
- 使用已有可离线加载的地图资源。

要求：

- 中国地图必须包含台湾区域。
- 中国地图资源必须能按省级 key 点亮。
- 世界地图资源必须能按国家或一级区域 key 点亮。
- 地图资源应本地可用，不依赖在线 CDN。
- key 映射必须有测试保护。

验收标准：

- 后端返回的中国区域 key 能在中国地图资源中找到。
- 台湾区域 key 能在中国地图资源中找到。
- 世界地图国家 key 能在世界地图资源中找到。
- 前端没有在线地图依赖。

建议测试：

- `tests/test_career_footprint_map_assets.py`
- `tests/test_career_footprint_frontend.py`

### FM-05：暗黑地图前端骨架

目标：

在足迹页实现“生涯足迹”暗黑地图区域渲染骨架。

改动范围：

- `track.html`
- 可能新增本地地图资源文件
- 前端静态测试

实现要求：

- 调用 `api.get_career_footprint(filters)`。
- 使用后端 `map_mode` 决定中国地图或世界地图。
- 按 `regions` 点亮区域。
- 渲染 summary。
- 渲染稳定空态和局部错误态。
- 不再把生涯足迹表现为赛事点位散点图。

视觉要求：

- 暗黑底图。
- 已点亮区域高对比但克制。
- 未点亮区域低对比。
- 文本不遮挡地图主体。
- 移动端不横向溢出。

验收标准：

- 中国-only 数据显示中国地图。
- world 数据显示世界地图。
- 空数据不显示假点亮区域。
- 前端源码不读取 forbidden 字段。

建议测试：

```bash
python3 -m pytest tests/test_career_footprint_frontend.py -q
```

### FM-06：地图交互与详情回跳

目标：

完善地图区域交互，使用户能查看区域摘要并回跳代表 Activity。

实现要求：

- hover 或 focus 展示区域名称和摘要。
- click 展示区域详情面板。
- 区域详情包含活动数、赛事数、首次活动、最近活动。
- 有 `representative_activity_id` 时可回跳 Activity Detail。
- 键盘可达。
- 局部错误不影响其他 Career 模块。

验收标准：

- 鼠标和键盘都能访问区域摘要。
- 点击代表活动复用既有 Activity Detail 打开链路。
- 前端不基于区域名称反查 Activity。

建议测试：

- `tests/test_career_footprint_frontend.py`
- `tests/test_career_overview_activity_detail_link.py`

### FM-07：Memory Gallery 相册 ViewModel

目标：

实现赛事相册 ViewModel，按赛事聚合照片，并复用 Activity Detail 赛事照片排序。

建议 API：

```text
get_career_memory_gallery(filters?)
```

改动范围：

- `career_backend.py`
- `main.py`
- `docs/js_api_contract.json`
- tests

实现要求：

- 以 active Race Event / 赛事 Activity 为相册单位。
- 每个相册关联 `race_id` 和 `activity_id`。
- 返回赛事标题、时间、地点。
- 返回 `photos`，按现有排序排列。
- 第一张启用照片作为 `cover`。
- `cover` 逻辑与 Overview Banner 一致。
- 只返回安全预览或安全媒体引用。
- 不返回 `storage_ref`、本地路径、`file://`。

空相册策略：

- 已有赛事但无照片时，可返回空相册卡片。
- 空相册卡片不得使用假照片。
- summary 中统计 `empty_album_count`。

验收标准：

- 有照片赛事返回封面和照片列表。
- 第一张照片改变排序后，Gallery 封面与 Banner 逻辑一致。
- 软删除照片不出现在相册中。
- 无照片赛事稳定显示为空相册。
- API 安全边界通过测试。

建议测试：

```bash
python3 -m pytest tests/test_career_memory_gallery_api.py tests/test_career_media_safe_preview_api.py -q
```

### FM-08：Memory Gallery 相册墙前端

目标：

在足迹页 Memory Gallery 区域渲染 4:3 赛事相册卡片墙。

实现要求：

- 调用 `api.get_career_memory_gallery(filters)`。
- 使用 `albums` 渲染相册卡片。
- 卡片比例固定 4:3。
- 卡片显示封面、赛事标题、时间、地点。
- 无封面时显示稳定空态，不展示假照片。
- 网格布局适配桌面和移动端。
- 点击卡片进入单场赛事相册展开。

验收标准：

- 卡片不变形。
- 文字不压住主体照片。
- 长标题不溢出容器。
- 空相册状态克制可读。
- 前端只使用白名单字段。

建议测试：

```bash
python3 -m pytest tests/test_career_memory_gallery_frontend.py -q
```

### FM-09：单场赛事相册展开

目标：

点击相册后，展示该赛事上传的所有照片。

实现方式可选：

- 页面内展开面板
- modal
- drawer

必须满足：

- 展示该赛事所有已启用照片。
- 保持后端返回排序。
- 显示赛事标题、时间、地点。
- 支持返回相册墙。
- 支持键盘可达。
- 图片加载失败只影响单图，不影响相册关闭。

验收标准：

- 点击相册能看到全部照片。
- 照片顺序与后端一致。
- 无照片赛事展开后有稳定空态。
- 关闭后回到相册墙原位置或可理解状态。

建议测试：

- `tests/test_career_memory_gallery_frontend.py`

### FM-10：单张照片大图预览

目标：

点击相册中的单张照片后，打开大图预览。

实现要求：

- 大图使用安全预览或应用受控媒体读取结果。
- 支持关闭。
- 支持上一张 / 下一张。
- 显示当前序号。
- 支持键盘 ESC 关闭。
- 支持键盘左右切换。
- 不拼接本地路径。

验收标准：

- 点击任意照片能打开大图。
- 上一张 / 下一张按相册排序切换。
- 第一张和最后一张边界稳定。
- 关闭后回到相册展开态。
- 大图加载失败时展示局部错误态。

建议测试：

- `tests/test_career_memory_gallery_frontend.py`

### FM-11：安全边界与前端零推断验收

目标：

对生涯足迹和 Memory Gallery 做统一安全边界验收。

必须覆盖：

- API 不返回 forbidden 字段。
- 前端 normalizer 不使用 `Object.assign` 或 `...item` 透传原始对象。
- 前端不出现 `points_json`、`track_json`、`storage_ref`、`file_path`、`file://`、`/Users/`。
- 前端不从标题、城市、日期推断地图模式或区域 key。
- Memory Gallery 不绕过后端直接读取媒体路径。

验收标准：

- 新增或扩展自动化测试覆盖以上红线。
- 现有 ACS Phase9 数据边界测试仍通过。

建议测试：

```bash
python3 -m pytest tests/test_career_phase9_data_boundary_audit.py tests/test_career_footprint_frontend.py tests/test_career_memory_gallery_frontend.py -q
```

### FM-12：真实数据与视觉验收

目标：

用当前真实库和构造样例完成端到端体验验收。

验收场景：

- 当前真实库展示生涯足迹。
- 中国-only 数据只显示中国地图。
- 台湾样例能点亮台湾区域。
- 海外样例触发世界地图。
- 普通 Activity 可进入生涯足迹。
- 无地理信息 Activity 进入缺失统计。
- 有照片赛事显示 4:3 相册卡片。
- 无照片赛事显示空相册状态。
- 点击相册展开全部照片。
- 点击单张照片打开大图。
- Gallery 封面与 Overview Banner 第一张图逻辑一致。

视觉验收：

- 桌面宽屏。
- 窄窗口。
- 移动端宽度。
- 深色 UI 对比度。
- 长标题。
- 图片缺失 / 加载失败。

非本轮完成但要记录：

- Windows 真机。
- Windows 打包产物。
- macOS 打包产物。

建议记录：

- 验收日期。
- 数据库样例说明。
- 截图或手工验收记录。
- 未解决问题清单。

## 5. 推荐执行顺序

第一组：

1. FM-00：现状审计与基线冻结
2. FM-01：生涯足迹数据契约冻结
3. FM-07：Memory Gallery 相册 ViewModel

第二组：

1. FM-02：地理区域归一 Resolver
2. FM-03：`get_career_footprint` 只读 API
3. FM-11：安全边界与前端零推断验收的后端部分

第三组：

1. FM-04：地图资源与区域 key 对齐
2. FM-05：暗黑地图前端骨架
3. FM-06：地图交互与详情回跳

第四组：

1. FM-08：Memory Gallery 相册墙前端
2. FM-09：单场赛事相册展开
3. FM-10：单张照片大图预览

最后：

1. FM-11：安全边界与前端零推断验收完整收口
2. FM-12：真实数据与视觉验收

## 6. 每轮任务完成定义

每个任务完成时必须满足：

- 代码实现完成。
- 相关测试新增或更新。
- 针对当前任务运行最小必要测试。
- 若改动 API，更新 `docs/js_api_contract.json`。
- 若改动产品边界，更新本任务清单或交付手册。
- 最终说明清楚本轮完成、未完成、验证命令和风险。

## 7. 不得误标完成

以下事项不得在未实际完成前标记为完成：

- 生涯足迹地图已完成，但实际仍是赛事经纬度散点图。
- 中国-only 地图已完成，但中国地图不包含台湾。
- 世界地图已完成，但海外样例无法触发。
- Memory Gallery 已完成，但仍按零散 MemoryItem 展示。
- 相册封面已完成，但没有复用第一张图 / Banner 逻辑。
- 相册展开已完成，但不能看到所有照片。
- 大图预览已完成，但只能打开封面。
- 安全验收已完成，但 API 或前端仍暴露本地路径。

## 8. 美国下钻最小增量

2026-07-14 追加：

- 只新增 `US -> us` 美国州级下钻，不同时扩展欧美 / 亚洲其他国家。
- 美国州界资源使用独立懒加载脚本 `assets/career_footprint_us.js`，不嵌入首屏 `assets/career_footprint_maps.js`。
- 后端仅在结构化国家字段为 `US / USA / United States / 美国` 且州或城市字段可明确解析时返回 `US-xx` 与 `map_mode = us`。
- 只有国家字段、缺少州 / 城市线索的美国足迹继续返回 `US` 与 `map_mode = world`，不从标题、文件名或轨迹点推断州。
- 点击世界图中的美国或点击美国相册时，前端进入美国州级地图；未进入美国下钻前不加载美国州界脚本。
