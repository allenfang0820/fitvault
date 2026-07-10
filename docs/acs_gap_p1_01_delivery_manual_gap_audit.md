# ACS-GAP-P1-01 交付手册与当前实现差异审计

生成日期：2026-07-09

## 1. 审计结论摘要

当前 ACS 已经具备较完整的工程底座：一级入口、独立页面壳、Schema migration、只读 API、Race/PB/Achievement Resolver、Career Snapshot、本地 fallback Insight、轻量 Memory、Activity Detail 回跳和较密集的自动化测试都已建立。

但从交付手册定义看，当前 ACS 仍不能视为完整产品交付。它更接近“安全数据链路 + 产品骨架 + 轻量只读 MVP”，主要缺口集中在：

- 生涯总览尚未充分回答“我是谁 / 我走了多久 / 我经历过什么”。
- 时间轴已有年/月节点，但还没有成为 ACS 的核心浏览体验。
- 赛事档案、PB、荣誉已能返回列表，但仍像摘要分区，不像正式档案系统。
- 候选事件已有表和计数，但缺用户确认 / 拒绝 / 晋级工作流。
- 足迹地图与 Memory Gallery 仍是轻量容器，离交付手册的“记忆与城市足迹”体验还有距离。
- 真实 AI Career Insight、Windows 真机和打包验证仍应后置。

## 2. 当前 ACS 总体成熟度判断

总体成熟度：`部分完成`

判断依据：

- 后端能力：`部分完成`。核心表、resolver、只读 API、Snapshot 和 fallback Insight 已建立，但 Season、候选工作流、足迹聚合、完整档案体验仍不足。
- 前端能力：`骨架完成 -> 部分完成`。P0 后已具备独立一级页面与顶部二级导航，但多数二级页仍复用轻量列表或空状态。
- 数据边界：`已完成`。测试和实现持续约束 raw FIT、points、track_json、file_path、storage_ref、SQLite schema、本地绝对路径不得进入 API/Snapshot/AI/前端静态 ACS 面板。
- 测试覆盖：`部分完成`。自动化测试覆盖非常密，但多为契约、resolver、列表渲染、边界安全；手册定义的完整产品体验仍缺人工与视觉验收。
- 跨平台：`部分完成`。macOS 代码层和路径兼容审计较充分，Windows 真机、Windows 打包和 macOS 打包产物验收未完成。

## 3. 模块差异矩阵

| 模块 | 交付手册要求 | 当前实现状态 | 证据 | 缺失点 | 风险 | 后续任务 |
|---|---|---|---|---|---|---|
| ACS 一级入口与导航 | ACS 是独立一级功能，荣誉墙只是二级能力 | 部分完成 | `track.html` 的 `panel-career`、`data-acs-product-shell="v1"`、顶部 `data-career-page-target`；`tests/test_career_p0_product_shell.py` | 视觉仍需继续产品化，各二级页内容深度不足 | P1 | 继续各二级页产品化 |
| 生涯总览 | 回答“我是谁 / 我走了多久 / 我经历过什么”，展示活动、赛事、PB、成就、城市、距离、代表事件 | 部分完成 | `career_backend.get_career_overview`；`track.html` 的 `career-overview-grid`、spotlight；`tests/test_career_overview_*` | 缺生涯身份叙事、阶段/赛季结构、年度目标、长期趋势入口 | P1 | `ACS-GAP-P1-02` |
| 年度 / 月度时间轴 | 年份 x 月份 x 事件，时间轴优先于列表，节点区分赛事/PB/首次/里程碑/记忆 | 部分完成 | `career_backend.get_career_timeline`、`_group_timeline_nodes`；`track.html` 的 `career-timeline-years`；`tests/test_career_timeline_*` | 记忆节点未充分进入主轴，时间轴体验仍偏紧凑列表，缺更强年/月浏览与事件故事化 | P1 | `ACS-GAP-P1-04` |
| 赛事识别与赛事档案 | 正式赛事识别、分类、置信度、档案浏览、详情回跳 | 部分完成 | `resolve_race_events`、`get_career_races`；`career_event_candidates`；`tests/test_career_race_resolver.py`、`tests/test_career_races_api.py` | 档案页缺搜索/筛选/卡片视觉/关联 PB 与成就；低置信候选缺用户流程 | P1 | `ACS-GAP-P1-05`、`ACS-GAP-P1-08` |
| PB Engine 与 PB 档案 | 跑步与骑行 PB，来源必须是 Activity，含提升幅度和回跳 | 部分完成 | `resolve_pb_records`、`get_career_pb`；`RUNNING_PB_DISTANCE_RANGES`；`tests/test_career_pb_resolver.py`、`tests/test_career_pb_api.py` | 当前主要覆盖跑步距离型 PB；骑行 PB、功率/速度类 PB、PB 趋势档案体验不足 | P1 | `ACS-GAP-P1-06` |
| 荣誉 / 成就 / 里程碑 | 首次、突破、连续、探索等 V1 分类，代表性评分，不只按时间 | 部分完成 | `resolve_achievement_events`、`ACHIEVEMENT_FIRST_DISTANCE_RULES`、`_record_achievement_candidates`、`_first_city_achievement_candidates`；`tests/test_career_achievement_*` | 分类仍不完整，连续性/探索类体验不足，荣誉墙视觉仍是列表而非勋章系统 | P1 | `ACS-GAP-P1-07` |
| 候选事件机制 | 低置信事件不能进入主时间轴，用户可确认/拒绝/晋级 | 骨架完成 | `career_event_candidates`、`_upsert_race_candidate`、timeline `candidates_count` | 无候选列表 API、无确认/拒绝 API、无前端候选管理界面 | P1 | `ACS-GAP-P1-08` |
| 记忆相册 / 生涯叙事 | 图像、故事、轨迹等记忆资产，按赛事/年份/类型浏览，与 Activity 回跳 | 部分完成 | `career_memory_items`、`get_career_memory`、`save_career_memory_story`、`save_career_memory_media`、`update_career_memory_story`、`deactivate_career_memory_item`；`tests/test_career_memory_*` | 当前是轻量文本/媒体引用闭环，缺相册式浏览、缩略图策略、年份/赛事浏览和 10000+ 照片懒加载 | P1/P2 | `ACS-GAP-P1-10`、`ACS-GAP-P2-04` |
| AI 生涯总结 / Career Snapshot | AI 只消费 Snapshot，生成生涯总结，不污染事实 | 部分完成 | `build_career_snapshot`、`save_career_snapshot`、`get_latest_career_snapshot`、`generate_career_insight` fallback；`tests/test_career_snapshot_*`、`tests/test_career_insight_*` | 当前不接真实 AI，页面是本地 fallback/准备态；真实 AI prompt、缓存、超时、安全审查未做 | P2 | `ACS-GAP-P2-01`、`ACS-GAP-P2-02` |
| 赛事足迹 / 城市地图 | 赛事城市分布、代表城市、PB 诞生地、城市足迹 | 骨架完成 | `covered_city_count`、`region_city` 聚合、P0 后 `footprint` 二级页容器 | 缺城市足迹 ViewModel/API，缺地图或城市分布卡片，缺 PB/赛事地点关系 | P1 | `ACS-GAP-P1-11` |
| Activity Detail 回跳 | 所有赛事、PB、成就、记忆、地图节点必须能回跳 Activity Detail | 部分完成 | `detail_link: {activity_id, source:'career'}`；`openCareerActivityDetailFromElement`；`tests/test_career_overview_activity_detail_link.py` | 足迹节点未实现，候选事件确认流未实现；回跳链路需随二级页补齐继续验收 | P1 | 并入各二级页任务 |
| macOS / Windows 兼容 | 路径、SQLite、pywebview、中文文件名、打包后权限与滚动性能 | 部分完成 | `tests/test_career_phase9_*`、受控目录/中文文件名/禁绝对路径测试 | Windows 真机、Windows 打包、macOS 打包产物验收未执行 | P3 | `ACS-GAP-P3-*` |
| 数据边界与安全契约 | 前端不算事实，AI 只吃 Snapshot，禁止 raw/local/schema 泄露 | 已完成 | `ACS_FORBIDDEN_RESPONSE_KEYS`、`CAREER_SNAPSHOT_FORBIDDEN_KEYS`、`_sanitize_public_metadata`；多组 tests 中 forbidden 字段检查 | 后续每个新 API/页面仍需继续加测试锁住 | P0/P1 持续 | 每个后续任务必带边界测试 |
| 测试覆盖与验收缺口 | 功能、数据、UI、AI 输出、系统验收 | 部分完成 | 46 个 `tests/test_career*.py`，主回归曾达 328 tests | 产品级人工验收、真实 AI 验收、打包验收、超大数据性能验收未完成 | P2/P3 | 后置验收矩阵继续执行 |

## 4. 逐模块详细审计

### 4.1 ACS 一级入口与导航

交付手册要求：ACS 是长期运动生涯组织能力，不是“个人运动数据 > 荣誉墙”的附属页面。

当前实现状态：`部分完成`

已完成证据：

- `track.html` 已有一级 `bookmark-tab data-panel="career"`。
- P0 后 `panel-career` 已有 `data-acs-product-shell="v1"`。
- P0 后有顶部二级导航：总览、时间轴、赛事档案、PB、荣誉、AI 总结、足迹。
- `tests/test_career_p0_product_shell.py` 锁定页面独立性、顶部二级导航和敏感字段不直出。

缺失点：

- 二级页内容仍不完整，部分页面只是列表复用或空状态。
- 视觉仍只是“正式骨架”，还未达到参考设计中的完整产品密度。

建议：不再单独做 P0 修壳，后续按二级页逐个产品化。

### 4.2 生涯总览

交付手册要求：首页总览回答“我是谁 / 我走了多久 / 我经历过什么”，有身份感、长期累计、代表事件。

当前实现状态：`部分完成`

已完成证据：

- `career_backend.get_career_overview` 返回 `summary`、`latest_race`、`latest_pb`、`representative_pb_records`、`representative_achievements`。
- `track.html` 渲染 `career-overview-grid` 和 spotlight。
- `tests/test_career_overview_frontend_render.py`、`tests/test_career_overview_pb_summary.py`、`tests/test_career_overview_representative_achievements.py` 覆盖了主要数据。

缺失点：

- 缺少生涯身份文案、赛季/年度进度、长期演化叙事。
- 缺“我是谁”的运动画像表达，例如主运动、运动年限、主要赛事类型、代表城市。
- 当前更像统计总览，不像 ACS 首页。

建议任务：`ACS-GAP-P1-02`，优先做。

### 4.3 年度 / 月度时间轴

交付手册要求：时间轴优先于列表，按年份 x 月份 x 赛事组织，是 ACS 核心浏览方式。

当前实现状态：`部分完成`

已完成证据：

- `career_backend.get_career_timeline` 聚合 Race/PB/Achievement。
- `career_event_candidates` 只通过 `candidates_count` 出现，低置信候选不进入正式 `years`。
- `track.html` 有 `career-timeline-year/month/node` 渲染、类型/年份/运动筛选。
- `tests/test_career_timeline_*` 覆盖筛选、PB 节点、Achievement 节点、大列表渐进展开。

缺失点：

- 时间轴视觉仍偏节点列表，缺年度/月份浏览主体验。
- 记忆节点尚未充分进入时间轴。
- 缺用户对候选事件的处理入口。

建议任务：`ACS-GAP-P1-04`，但应在 Overview 产品化后做。

### 4.4 赛事识别与赛事档案

交付手册要求：识别正式赛事，输出置信度，形成可浏览赛事档案。

当前实现状态：`部分完成`

已完成证据：

- `resolve_race_events` 使用 `sport_event/is_race`、标题关键词、标准距离等安全字段决策。
- `get_career_races` 返回 active `career_race_events`，含 `detail_link`。
- `tests/test_fit_sport_event_race.py`、`tests/test_activity_race_flag_api.py`、`tests/test_career_race_resolver.py`、`tests/test_career_races_api.py` 覆盖赛事入口。

缺失点：

- 赛事档案页面缺搜索、筛选、分组、卡片化视觉和详情结构。
- 赛事与 PB、荣誉、记忆之间的关联展示不足。
- 低置信候选没有用户确认流。

建议任务：`ACS-GAP-P1-05`，在 Timeline 产品化前后均可；若用户更关注赛事体验，可提前。

### 4.5 PB Engine 与 PB 档案

交付手册要求：跑步 PB、骑行 PB、提升幅度、来源 Activity、回跳 Activity Detail。

当前实现状态：`部分完成`

已完成证据：

- `resolve_pb_records` 已处理跑步距离 PB。
- `get_career_pb` 有只读 API 与白名单输出。
- `tests/test_career_pb_resolver.py`、`tests/test_career_pb_api.py`、`tests/test_career_timeline_pb_nodes.py` 覆盖 PB 解析、API、时间轴。

缺失点：

- 骑行 PB 仍不足。
- 功率/速度类 PB 未形成可用策略。
- 前端 PB 页仍是列表，不是 PB 档案与历史趋势。

建议任务：`ACS-GAP-P1-06`。

### 4.6 荣誉 / 成就 / 里程碑

交付手册要求：建立 Achievement V1 分类，包含首次、突破、连续、探索等；排序要考虑代表性。

当前实现状态：`部分完成`

已完成证据：

- `resolve_achievement_events` 已有首次距离、最长距离/爬升、首次城市等候选。
- `get_career_achievements` 返回 active 成就。
- `tests/test_career_achievement_resolver.py`、`tests/test_career_achievement_phase3_integration.py`、`tests/test_career_achievements_api.py` 覆盖基础成就链路。

缺失点：

- 连续性成就不足。
- 探索类成就体系不足。
- 前端荣誉页未形成勋章墙、分类、解锁/未解锁状态、条件解释。

建议任务：`ACS-GAP-P1-07`。

### 4.7 候选事件机制

交付手册要求：低置信事件只能进入候选区，不能污染主时间轴；用户可确认/拒绝/晋级。

当前实现状态：`骨架完成`

已完成证据：

- Schema 有 `career_event_candidates`。
- `resolve_race_events` 有 `_upsert_race_candidate`。
- Timeline 返回 `candidates_count`，但不把候选写入正式 `years[].months[].nodes`。

缺失点：

- 没有候选列表 API。
- 没有 confirm/reject API。
- 没有候选区前端。
- 没有用户确认后如何影响 `activities.is_race` 或 ACS 派生表的明确实现。

建议任务：`ACS-GAP-P1-08`。这个任务与用户之前关心“如何判断一个活动是不是赛事 / 用户手动设置为赛事”直接相关。

### 4.8 记忆相册 / 生涯叙事

交付手册要求：图像、故事、轨迹、证书等记忆资产，形成 Memory Gallery，并可回跳 Activity Detail。

当前实现状态：`部分完成`

已完成证据：

- `get_career_memory`、`save_career_memory_story`、`save_career_memory_media`、`update_career_memory_story`、`deactivate_career_memory_item` 已存在。
- 媒体只保存受控引用，API 不返回 `storage_ref`。
- `tests/test_career_memory_*` 覆盖轻量闭环、编辑、媒体安全、前端渲染。

缺失点：

- 前端还不是 Gallery。
- 缺按赛事/年份/类型浏览。
- 缺缩略图策略、懒加载、10000+ 照片性能策略。

建议任务：`ACS-GAP-P1-10`；大规模照片性能归入 `ACS-GAP-P2-04`。

### 4.9 AI 生涯总结 / Career Snapshot

交付手册要求：AI 只消费 Career Snapshot，生成生涯总结，不读原始数据，不写事实表。

当前实现状态：`部分完成`

已完成证据：

- `build_career_snapshot`、`save_career_snapshot`、`get_latest_career_snapshot` 已存在。
- `generate_career_insight` 当前只返回本地 fallback。
- `CAREER_SNAPSHOT_FORBIDDEN_KEYS` 和相关测试阻止敏感字段进入 Snapshot/Insight。
- `docs/js_api_contract.json` 明确真实 AI 未接入且不返回禁用字段。

缺失点：

- 真实 AI 未接入。
- Prompt 契约、超时降级、缓存策略、独立 AI 会话污染隔离仍未做。
- 前端 AI 页仍是准备态，不是正式报告体验。

建议任务：先做 `ACS-GAP-P2-01` 准备态产品化；真实 AI 接入必须单独安全审查。

### 4.10 赛事足迹 / 城市地图

交付手册要求：赛事城市分布、PB 诞生地、参赛足迹、代表城市。

当前实现状态：`骨架完成`

已完成证据：

- Overview 统计 `covered_city_count`。
- 活动数据已有 `region_city/region/region_display` 基础。
- P0 后前端已有 `footprint` 二级页容器。

缺失点：

- 没有 `get_career_footprint` 或等价 ViewModel。
- 没有赛事城市聚合、PB 地点、城市分布卡片。
- 没有地图或城市足迹列表。

建议任务：`ACS-GAP-P1-11`。首版可不做复杂地图，先做城市足迹列表/分布卡。

### 4.11 Activity Detail 回跳

交付手册要求：所有赛事、PB、成就、记忆、地图节点必须能回跳 Activity Detail。

当前实现状态：`部分完成`

已完成证据：

- Race/PB/Achievement/Memory 返回 `detail_link`。
- 前端统一使用 `openCareerActivityDetailFromElement`。
- `tests/test_career_overview_activity_detail_link.py` 覆盖主要回跳。

缺失点：

- 足迹节点尚不存在，无法验收。
- 候选事件未实现，无法验收。
- 后续每个二级页产品化时都要补回跳测试。

## 5. 关键风险

1. 产品体验风险：当前数据链路比页面体验成熟，用户看到的仍可能觉得“功能没有做完”。
2. 候选事件风险：已有候选概念但无用户处理流，会影响“赛事识别可信度”和“手动设置为赛事”的闭环。
3. PB 范围风险：跑步 PB 已有基础，骑行 PB 和功率/速度 PB 不足，可能与交付手册预期不一致。
4. 荣誉系统风险：成就分类还不完整，荣誉页缺勋章墙体验。
5. AI 风险：真实 AI 尚未接入，不能提前宣称 AI Career Insight 完成。
6. 跨平台风险：Windows 真机、Windows 打包、macOS 打包产物验收未完成，不能进入最终发布验收。

## 6. 推荐后续任务顺序

建议按以下顺序推进：

1. `ACS-GAP-P1-02`：补齐 Career Overview 的“我是谁 / 我走了多久 / 我经历过什么”。
2. `ACS-GAP-P1-03`：补齐 Season / 年度生涯结构。
3. `ACS-GAP-P1-04`：升级 Timeline 为核心浏览体验。
4. `ACS-GAP-P1-05`：补齐 Race Archive 的正式赛事档案体验。
5. `ACS-GAP-P1-06`：补齐 PB Engine 范围与 PB 档案体验。
6. `ACS-GAP-P1-07`：补齐 Achievement Engine V1 分类与荣誉墙体验。
7. `ACS-GAP-P1-08`：补齐低置信度候选事件工作流。
8. `ACS-GAP-P1-09`：将 Race/PB/Achievement 从摘要列表升级为可浏览档案区。
9. `ACS-GAP-P1-10`：补齐 Memory Gallery 产品体验。
10. `ACS-GAP-P1-11`：新增 Race Map / 城市足迹。
11. `ACS-GAP-P2-01`：AI 生涯洞察准备态产品化。
12. `ACS-GAP-P2-02`：真实 AI 接入前安全设计。
13. `ACS-GAP-P2-03/P2-04`：Timeline 与 Memory 性能策略。
14. `ACS-GAP-P3-*`：macOS/Windows 打包与人工验收。

下一编码任务推荐：`ACS-GAP-P1-02`。

原因：Overview 是用户进入 ACS 的第一屏，它决定 ACS 是否像一个完整产品。先把首页做成“运动生涯身份页”，后续时间轴、赛事档案、PB、荣誉才能自然承接。

## 7. 暂缓任务

以下任务暂缓，不应混入 P1 当前补齐阶段：

- 真实 AI Career Insight 接入。
- Windows 真机验证。
- Windows 打包验证。
- macOS 打包产物验收。
- 10000+ 照片真实压力验证。
- 复杂地图引擎或外部地图服务接入。

## 8. 验收建议

后续每个编码任务至少应验收：

- 前端只消费后端 ViewModel，不计算赛事、PB、成就事实。
- API envelope 继续为 `{ok, code, msg, data, traceId}`。
- 返回数据不包含 raw FIT、points、track_json、file_path、storage_ref、SQLite schema、本地绝对路径。
- 所有卡片、节点、记忆、档案项只要有关联 Activity，就必须能回跳 Activity Detail。
- 空状态必须是正式产品空状态，而不是开发占位。
- Windows/打包验收不得提前勾选。

## 9. 附录：检查过的文件与测试

检查过的主要文件：

- `docs/脉图运动生涯系统（ACS）开发团队交付手册.md`
- `docs/脉图运动生涯系统（ACS）开发任务清单.md`
- `docs/acs_交付手册差异补齐任务清单.md`
- `.trae/rules/fit-arch-contrac.md`
- `career_backend.py`
- `main.py`
- `track.html`
- `docs/js_api_contract.json`
- `tests/test_career*.py`

关键证据函数/API：

- `career_backend.ensure_career_schema`
- `career_backend.resolve_race_events`
- `career_backend.resolve_pb_records`
- `career_backend.resolve_achievement_events`
- `career_backend.get_career_overview`
- `career_backend.get_career_timeline`
- `career_backend.get_career_races`
- `career_backend.get_career_pb`
- `career_backend.get_career_achievements`
- `career_backend.get_career_memory`
- `career_backend.build_career_snapshot`
- `career_backend.generate_career_insight`
- `main.Api.get_career_overview`
- `main.Api.get_career_timeline`
- `main.Api.get_career_races`
- `main.Api.get_career_pb`
- `main.Api.get_career_achievements`
- `main.Api.get_career_memory`
- `main.Api.get_latest_career_snapshot`
- `main.Api.generate_career_insight`

自动化测试现状：

- `tests/test_career*.py` 覆盖 schema、resolver、API、Snapshot、Insight、Memory、前端静态契约、跨平台代码层约束。
- `tests/test_career_p0_product_shell.py` 覆盖 P0 页面独立性与二级导航。
- `tests/test_career_phase8_frontend_readiness.py` 覆盖 ACS 前端基础可用性。

