---
title: 运动生涯记录中心（PB 功能）开发任务清单
aliases:
  - 记录中心开发任务清单
  - Records Center PB Task List
version: v1.0.0
status: Planning Freeze
type: Ordered Implementation Task List
scope: ACS 记录中心 V1，跑步 5K、10K、半程马拉松、马拉松整次活动 PB
source:
  - docs/运动生涯记录中心（PB功能）开发交付手册.md
updated: 2026-07-13
---

# 运动生涯记录中心（PB 功能）开发任务清单

## 0. 使用说明

本文档是记录中心 V1 后续所有开发任务的唯一顺序依据。任务目标、依赖关系和验收门槛来自 `docs/运动生涯记录中心（PB功能）开发交付手册.md`。

执行规则：

1. 默认严格按编号执行，不得跳过未完成依赖。
2. 每次只启动一个主任务；确需并行时，任务之间必须不存在代码、数据或契约依赖。
3. 每个任务开始前必须读取交付手册、本任务条目和上一任务完成报告。
4. 每个任务结束时必须更新本清单状态，并新增独立完成报告或执行记录。
5. 自动化测试通过不等于发布完成；真实数据、macOS、Windows 和打包验证按各自门禁单独验收。
6. 若实现需要改变已冻结的产品语义，必须先修改交付手册和本清单，不能在代码中静默改变规则。
7. 工作区可能已有其他改动；每个任务必须先确认自己的文件边界，不得覆盖或回退无关修改。

状态标记：

- `Pending`：尚未开始。
- `In Progress`：正在执行，最多一个主任务处于此状态。
- `Blocked`：存在需要用户决策或外部环境的阻塞。
- `Done`：交付物、测试和本任务验收标准均已满足。
- `Verified`：在后续真实数据或发布门禁中再次验证通过。

## 0.1 全局硬约束

所有任务必须遵守：

- `Activity` 是唯一事实源。
- PB Resolver 是正式纪录唯一写入口。
- 前端只渲染后端 ViewModel，不计算 PB、提升量或置信度。
- AI 只消费 Records Snapshot，不读取原始 FIT、轨迹点、SQLite schema 或本地路径。
- 每条当前、历史、候选纪录都必须绑定有效 `activity_id`。
- V1 只交付跑步 5K、10K、半程马拉松、马拉松的整次活动 PB。
- 标准距离统一采用包含边界的 `±3%` 公式。
- 正式比较使用整数秒 elapsed time；口径不确定的旧数据不得自动成为正式纪录。
- 置信度 `>0.90` 才能自动确认；`0.70-0.90` 进入候选；`<0.70` 不进入正式纪录。
- 不新建与 `career_pb_records` 含义重叠的平行事实表。
- 不因页面改名而废弃现有 `get_career_pb()` 或改变 `detail_link.source = "career"`。
- 不在 V1 实现最佳分段、骑行功率曲线、路线纪录、环境纪录或公开排行榜。

---

# 1. 任务总览

| 编号 | 任务 | 阶段 | 优先级 | 依赖 | 状态 |
| --- | --- | --- | --- | --- | --- |
| RC-00 | 当前实现与工作区基线审计 | 审计 | P0 | 无 | Done |
| RC-01 | Activity 距离与计时事实源审计 | 审计 | P0 | RC-00 | Done |
| RC-02 | 真实数据库与 `±3%` 迁移影响审计 | 审计 | P0 | RC-01 | Done |
| RC-03 | Record Registry 与比较规则冻结 | 契约 | P0 | RC-01, RC-02 | Done |
| RC-04 | 置信度、候选与状态机冻结 | 契约 | P0 | RC-01, RC-03 | Done |
| RC-05 | 数据模型、审计事件与迁移回滚冻结 | 契约 | P0 | RC-04 | Done |
| RC-06 | API、ViewModel 与错误状态契约冻结 | 契约 | P0 | RC-05 | Done |
| RC-07 | 记录中心前端设计与交互冻结 | 设计 | P0 | RC-06 | Done |
| RC-08 | Record Registry 代码化 | Resolver | P0 | RC-03 | Done |
| RC-09 | 规范化 Performance Summary | Resolver | P0 | RC-01, RC-08 | Done |
| RC-10 | 标准距离匹配与成绩比较 Resolver | Resolver | P0 | RC-08, RC-09 | Done |
| RC-11 | 置信度、原因码与候选生成 | Resolver | P0 | RC-04, RC-10 | Done |
| RC-12 | PB schema migration 与 Record Event 表 | 数据层 | P0 | RC-05 | Done |
| RC-13 | 当前纪录、历史链与状态迁移 | 数据层 | P0 | RC-10, RC-11, RC-12 | Done |
| RC-14 | Activity 导入后的增量评估 | 数据层 | P0 | RC-13 | Done |
| RC-15 | 全量 dry-run、重建与 Resolver 版本化 | 数据层 | P0 | RC-13 | Done |
| RC-16 | 删除回退、幂等、并发与事务闭环 | 数据层 | P0 | RC-14, RC-15 | Done |
| RC-17 | 当前纪录、详情与历史只读 API | API | P0 | RC-06, RC-16 | Done |
| RC-18 | 候选决策、重建与新纪录事件 API | API | P0 | RC-17 | Done |
| RC-19 | “记录”导航与当前纪录页面 | 前端 | P1 | RC-07, RC-17 | Done |
| RC-20 | 纪录详情与演进视图 | 前端 | P1 | RC-07, RC-17, RC-19 | Done |
| RC-21 | 候选纪录确认与拒绝视图 | 前端 | P1 | RC-07, RC-18, RC-19 | Done |
| RC-22 | 页面状态、响应式、无障碍与刷新反馈 | 前端 | P1 | RC-19, RC-20, RC-21 | Done |
| RC-23 | Overview、Timeline、Race、Achievement 联动 | 集成 | P1 | RC-18, RC-22 | Done |
| RC-24 | Records Snapshot、AI 与 Trends 联动 | 集成 | P1 | RC-18, RC-23 | Done |
| RC-25 | 安全、性能、日志与可观测性闭环 | 质量 | P0 | RC-16, RC-18, RC-24 | Done |
| RC-26 | 自动化测试矩阵与宽回归 | 质量 | P0 | RC-22, RC-23, RC-24, RC-25 | Done |
| RC-27 | 真实数据 dry-run、迁移与人工复核 | 发布 | P0 | RC-26 | Done |
| RC-28 | macOS 当前环境与打包产物验收 | 发布 | P1 | RC-27 | In Progress |
| RC-29 | Windows 真机与打包产物验收 | 发布 | P1 | RC-27 | Pending |
| RC-30 | 最终文档同步与发布门禁 | 发布 | P0 | RC-28, RC-29 | Pending |

当前下一任务：`RC-28`。

---

# 2. 里程碑与门禁

## Milestone A：审计、契约与设计冻结

包含：`RC-00` 至 `RC-07`。

通过条件：

- 已用代码、真实数据库和测试回答交付手册附录 B 的全部问题。
- Record Registry、计时口径、状态机、数据模型和 API ViewModel 已冻结。
- 当前纪录、演进、候选三条前端路径已有可评审设计。
- 未开始业务实现，或只增加不改变行为的审计测试和工具。

未通过 Milestone A，不得进入 Resolver、schema 或正式前端开发。

## Milestone B：Resolver 与数据闭环

包含：`RC-08` 至 `RC-16`。

通过条件：

- Registry、计时、距离、置信度和状态迁移均由后端实现。
- 增量评估和安全全量重建可用。
- 删除、修改、重复导入和并发不会产生多个 active 或丢失当前纪录。
- 数据 migration 可重复执行并有回滚/失败保护。

## Milestone C：API 与前端闭环

包含：`RC-17` 至 `RC-22`。

通过条件：

- 当前、详情、历史、候选和决策 API 完整。
- 页面名称为“记录中心”，内部仍兼容现有 PB API。
- 当前纪录、演进、候选和所有状态在桌面与移动端可用。
- 前端无 PB 事实推断。

## Milestone D：跨模块与质量闭环

包含：`RC-23` 至 `RC-26`。

通过条件：

- Overview、Timeline、Race、Achievement、Snapshot、AI、Trends 边界清楚。
- 新纪录事件幂等，不重复节点、通知或 Achievement。
- 安全、性能、日志和自动化宽回归通过。

## Milestone E：真实数据与发布闭环

包含：`RC-27` 至 `RC-30`。

通过条件：

- 真实数据迁移差异经过人工复核。
- macOS 与 Windows 的当前环境和打包产物完成验收。
- 文档、API contract、任务状态、发布说明和回滚说明同步完成。

---

# 3. 详细任务

## RC-00：当前实现与工作区基线审计

任务目标：

建立记录中心开发的可信起点，确认现有 PB Resolver、schema、API、前端、Timeline、Achievement 和测试的真实状态，并划定当前脏工作区的任务边界。

前置条件：无。

实施范围：

- `career_backend.py`
- `main.py`
- `track.html`
- `docs/js_api_contract.json`
- `tests/test_career_pb_*.py`
- `tests/test_career_timeline_pb_nodes.py`
- PB 与 Achievement、Overview、刷新管线相关测试

必须完成：

- 列出现有 PB 类型、距离区间、计时字段、状态值和 ID 规则。
- 列出现有 `career_pb_records` schema、索引和 migration 入口。
- 记录现有 `get_career_pb()` 返回字段和前端使用位置。
- 解释当前 Timeline 是否以及为什么排除 PB 节点。
- 记录当前相关文件中已有未提交修改，区分本项目可编辑范围和用户无关改动。
- 运行当前 PB 定向测试，形成基线结果。

明确非目标：

- 不修改 PB 判定规则。
- 不调整 UI。
- 不执行 schema migration。

交付物：

- `docs/records_center_rc_00_baseline_audit.md`
- 基线测试结果。

完成标准：

- 交付手册“当前代码基线”中的每条结论都有代码或测试证据。
- 下一任务不需要重新猜测现有实现。

建议验证：

```bash
.venv312/bin/python -m pytest tests/test_career_pb_resolver.py tests/test_career_pb_api.py tests/test_career_timeline_pb_nodes.py -q
```

## RC-01：Activity 距离与计时事实源审计

任务目标：

确认跑步 PB 应读取的 canonical 距离与 elapsed time 字段，回答 `duration`、`duration_sec`、moving time、elapsed time 的真实语义和历史数据可用性。

前置条件：`RC-00`。

实施范围：

- FIT 解析到 Activity 的距离、时长字段写入链路。
- `metrics_resolver.py`、`fit_engine.py`、Activity schema 和真实 SQLite 样本。
- 跑步机、自动暂停和字段缺失样本。

必须完成：

- 画出 FIT 字段到 Activity 字段的来源链。
- 明确哪个字段可作为 V1 `elapsed_time_sec`。
- 分类统计真实库中“可靠 elapsed / 仅 moving / 语义未知 / 缺失”的 Activity 数量。
- 明确距离使用米还是公里字段，以及单位转换位置。
- 明确跑步机活动的距离来源和可信度上限。
- 给出口径未知旧数据进入候选或忽略的确定规则。

明确非目标：

- 不实现新的成绩比较。
- 不扫描原始轨迹计算最佳分段。

交付物：

- `docs/records_center_rc_01_activity_metric_source_audit.md`
- canonical 字段建议和数据质量分类样例。

完成标准：

- `elapsed_time_sec` 和距离事实源不再依赖字段名猜测。
- RC-03 可以基于确定事实冻结 Registry。

## RC-02：真实数据库与 `±3%` 迁移影响审计

任务目标：

用只读方式评估从当前硬编码距离区间切换到统一 `±3%` 后，真实用户 PB 会新增、移除或替换哪些结果。

前置条件：`RC-01`。

必须完成：

- 对当前硬编码范围和新 `±3%` 公式分别计算候选集合。
- 输出每个 `pb_type` 的共同项、新增项、移除项和 active 变化。
- 重点审计 5K 的 4.8-5.3K、10K 的 9.5-10.8K 边界数据。
- 列出受计时口径不确定影响的历史 Activity。
- 保存 Activity ID、日期、距离、用时和变化原因；不得保存 raw FIT 或路径。
- 本任务只输出差异，不写正式 PB 表。

明确非目标：

- 不让 dry-run 结果覆盖现有 active。
- 不要求用户在本任务确认迁移。

交付物：

- `docs/records_center_rc_02_real_db_rule_diff.md`
- 可重复运行的只读审计测试或脚本。

完成标准：

- 规则迁移的真实影响可量化、可追溯、可复跑。

## RC-03：Record Registry 与比较规则冻结

任务目标：

冻结 V1 四项跑步纪录的唯一规则来源，消除代码、SQL、API 和前端各自硬编码口径的风险。

前置条件：`RC-01`、`RC-02`。

必须完成：

- 冻结 `running_5k`、`running_10k`、`running_half_marathon`、`running_marathon`。
- 为每项定义 sport、display name、metric、unit、comparison、source mode、标准距离、容差和版本。
- 冻结 `abs(actual-standard)/standard <= 0.03`，包含边界。
- 冻结 V1 只使用 `activity_total`，不截取活动内分段。
- 冻结用时整数秒、相同秒数不刷新、首条 improvement 为 `null`。
- 定义多个标准距离区间冲突时的检测与失败策略。

明确非目标：

- 不加入骑行、越野、游泳或故事纪录。
- 不实现 UI。

交付物：

- Registry 契约章节或独立 JSON/Python 结构草案。
- Registry 测试用例表。

完成标准：

- 后续任何模块只引用 Registry key，不重复定义距离范围和比较方向。

## RC-04：置信度、候选与状态机冻结

任务目标：

冻结纪录从检测到候选、激活、替代、拒绝和失效的完整生命周期，以及每种状态的用户可见行为。

前置条件：`RC-01`、`RC-03`。

必须完成：

- 冻结 `candidate`、`active`、`superseded`、`rejected`、`invalidated`。
- 冻结置信度区间：`>0.90` 自动确认、`0.70-0.90` 候选、`<0.70` 忽略。
- 定义 sport、距离、计时、Activity 完整性、设备/GPS 质量和异常值的评分维度。
- 每个分数必须有 `reason_codes`，禁止只有不可解释分数。
- 定义候选确认和拒绝后的状态迁移、来源标记与幂等规则。
- 定义用户拒绝后在何种 Resolver 版本变化下允许重新提示。
- 定义当前纪录失效后的回退流程。

交付物：

- 状态迁移表。
- 置信度样例矩阵。
- 候选用户操作契约。

完成标准：

- 后端、API 和前端对每种状态的含义一致。

## RC-05：数据模型、审计事件与迁移回滚冻结

任务目标：

在兼容现有 `career_pb_records` 的前提下，冻结历史链、审计事件、唯一性、索引、migration 和失败回滚方案。

前置条件：`RC-04`。

必须完成：

- 冻结现有字段语义和新增字段：`evidence_key`、`source_mode`、`previous_record_id`、`resolver_version`、确认/失效时间。
- 冻结 `career_record_events` append-only schema。
- 定义 Record Event 类型和不可变约束。
- 定义同一证据幂等键和每个纪录范围唯一 active 约束。
- 明确 `value` TEXT 的数值比较和未来 NUMERIC 迁移策略。
- 设计幂等 migration、失败回滚和旧版本兼容。
- 定义数据删除、Activity 软删除和规则重算时的保留策略。

明确非目标：

- 不新建与 `career_pb_records` 重复的 `records` 表。

交付物：

- schema 设计。
- migration/rollback 设计。
- 索引和唯一性测试计划。

完成标准：

- RC-12 可直接按冻结 schema 实现，不再临时改表意图。

## RC-06：API、ViewModel 与错误状态契约冻结

任务目标：

冻结当前纪录、详情、历史、候选、候选决策和重建状态的前后端数据契约，为前端设计和后端实现提供共同接口。

前置条件：`RC-05`。

必须完成：

- 保留并扩展 `get_career_pb(filters)`。
- 冻结 `get_career_pb_detail`、`get_career_pb_history`、`get_career_pb_candidates`。
- 冻结 `decide_career_pb_candidate` 和 `rebuild_career_pb_records`。
- 定义统一 envelope、readonly、高风险属性和错误码。
- 定义 Loading、Empty、Partial、Rebuilding、Error 所需 status 字段。
- 冻结 `detail_link.source = "career"`。
- 定义 API 白名单，禁止 raw FIT、轨迹、路径、storage_ref 和 schema。
- 为每个接口提供正常、空、候选、重建和错误样例。

交付物：

- API/ViewModel 契约草案。
- 前端 mock fixtures。
- `docs/js_api_contract.json` 计划变更表。

完成标准：

- 前端设计无需假设额外字段。
- 后端实现无需从页面反推数据结构。

## RC-07：记录中心前端设计与交互冻结

任务目标：

基于冻结 ViewModel 完成可交付的记录中心前端设计，明确“当前纪录 / 演进 / 候选”三条路径和所有响应式、状态与交互细节。

前置条件：`RC-06`。

必须完成：

- 冻结运动生涯二级导航 `PB -> 记录` 和页面标题“记录中心”。
- 完成桌面端当前纪录列表加详情区域设计。
- 完成演进视图：单一纪录类型、成绩曲线/阶梯图、历史节点。
- 完成候选视图：原因、置信度、Activity 入口、确认和拒绝。
- 完成移动端单列下钻方式。
- 完成 Loading、Empty、Partial、Rebuilding、Error 设计。
- 完成新纪录轻量通知和首次纪录文案。
- 定义组件、间距、图标、文本溢出、键盘与读屏规则。
- 使用真实长度的中文标题、日期和成绩做视觉验证。

明确非目标：

- 不在设计中加入未交付的骑行、路线、功率曲线占位卡。
- 不让前端 mock 产生新的业务规则。

交付物：

- 高保真页面设计或可交互原型。
- 前端组件与状态规范。
- 桌面和移动端验收截图。

完成标准：

- 产品、设计、前端和后端可对同一交互逐项确认。
- Milestone A 完成。

## RC-08：Record Registry 代码化

任务目标：

将 RC-03 冻结的四项跑步纪录定义实现为后端单一注册表，替换分散硬编码。

前置条件：`RC-03`。

必须完成：

- 实现 Registry 数据结构和查询 helper。
- 加入 key 唯一、单位合法、比较方向合法和区间冲突校验。
- 现有 PB label、Timeline title、Overview priority 逐步从 Registry 派生。
- 保持现有公开 key 兼容。
- 添加 Registry 单元测试。

明确非目标：

- 本任务不改变现有 active PB 结果。

交付物：

- Registry 代码与测试。
- 硬编码迁移清单。

完成标准：

- 距离、单位、比较方向和显示名称不再存在多个事实源。

## RC-09：规范化 Performance Summary

任务目标：

为 PB Resolver 提供明确、最小、安全的距离、elapsed time、运动类型和质量摘要，消除直接猜测 Activity 字段语义。

前置条件：`RC-01`、`RC-08`。

必须完成：

- 输出 canonical `distance_m`、`elapsed_time_sec`、`sport`、`event_date` 和质量字段。
- 对旧数据标记可靠、部分可靠或未知。
- 跑步机、自动暂停、字段缺失有确定 reason code。
- 不向 PB Resolver 暴露 raw points、track_json、file path。
- 不影响其他运动和现有 Activity Detail。

交付物：

- Performance Summary helper/Resolver。
- 字段来源和边界测试。

完成标准：

- PB Resolver 只依赖规范化摘要，不再直接选择含义不明的 duration 字段。

## RC-10：标准距离匹配与成绩比较 Resolver

任务目标：

实现统一 `±3%` 标准距离匹配、唯一纪录类型选择和整数秒成绩比较。

前置条件：`RC-08`、`RC-09`。

必须完成：

- 实现包含边界的标准距离公式。
- V1 只处理 `activity_total`。
- 多定义冲突时失败并记录，不静默选择错误类型。
- 更快刷新、更慢不刷新、相同秒数不刷新。
- 首条纪录 improvement 为 `null`。
- 单位和 NaN/无穷/非正数防护。
- 覆盖 4.8K、4.85K、5.0K、5.15K、5.16K 等边界测试。

交付物：

- 匹配与比较实现。
- 完整边界单测。

完成标准：

- 新规则在纯函数层可独立验证，尚不要求写正式表。

## RC-11：置信度、原因码与候选生成

任务目标：

实现可解释的置信度计算，并把中置信度结果稳定输出为候选，不污染当前纪录。

前置条件：`RC-04`、`RC-10`。

必须完成：

- 实现冻结的评分维度和阈值。
- 输出 `confidence`、`confidence_level`、`reason_codes` 和评分分解。
- 高置信度进入正式比较；中置信度生成 candidate；低置信度只写审计计数。
- 旧计时语义、跑步机和异常值样例行为明确。
- 同一证据重复运行不重复候选。

交付物：

- 置信度/候选实现。
- 评分解释测试。

完成标准：

- 每项候选都能在 UI 中解释为什么没有自动确认。

## RC-12：PB schema migration 与 Record Event 表

任务目标：

实现 RC-05 冻结的数据结构，保证 migration 幂等、旧数据可读、失败不破坏现有 PB。

前置条件：`RC-05`。

必须完成：

- 增加结构化字段或明确的过渡字段策略。
- 新建 `career_record_events`。
- 创建必要索引。
- migration 重复执行无副作用。
- 旧数据库、空数据库和部分旧 schema 均可升级。
- 失败回滚后原 `career_pb_records` 仍可读取。

交付物：

- SQLite migration。
- schema 与 migration 测试。

完成标准：

- 数据层能表达全部冻结状态和审计事件。

## RC-13：当前纪录、历史链与状态迁移

任务目标：

把候选成绩可靠地写成当前纪录或历史纪录，并在每次变化中维护前序关系和 append-only 事件。

前置条件：`RC-10`、`RC-11`、`RC-12`。

必须完成：

- 首条有效纪录激活。
- 新纪录激活、旧纪录 superseded。
- 相同或更慢成绩不改变 active。
- 候选确认后重新参与比较。
- rejected 不进入历史链。
- 所有迁移写 Record Event。
- 同一范围最多一个 active。
- `previous_record_id`、previous value、improvement 正确。

交付物：

- 状态迁移服务。
- 当前/历史链单元与集成测试。

完成标准：

- 任意 `pb_type` 都可完整还原纪录演进。

## RC-14：Activity 导入后的增量评估

任务目标：

在 Activity 新增或关键字段更新后，只重算受影响的纪录类型，并返回可幂等消费的新纪录事件。

前置条件：`RC-13`。

必须完成：

- 找到 Activity 导入/同步后的正式触发点。
- 仅评估对应 sport 和可能匹配的 Registry 定义。
- 事务内完成 Record 和 Event 写入。
- 返回 new record / candidate / unchanged 结果。
- 重复导入不重复 PB、事件、通知或 Achievement。
- Resolver 失败不阻塞 Activity 基础事实保存，错误需可恢复。

交付物：

- 增量处理管线。
- 导入集成测试。

完成标准：

- 新 Activity 不需要进入运动生涯页面才生成纪录。

## RC-15：全量 dry-run、重建与 Resolver 版本化

任务目标：

提供安全的规则升级和历史重算能力，先输出差异，再在事务中应用，不先清空旧纪录。

前置条件：`RC-13`。

必须完成：

- 生成运行 ID 和 `resolver_version`。
- dry-run 输出新增、替换、移除、候选和不变项。
- 临时结果完成后再生成应用计划。
- 正式应用失败时保留旧 active。
- 重建相同结果不发送庆祝通知。
- 并发重建防重入。
- 提供进度和最终统计。

交付物：

- dry-run/rebuild 服务。
- 失败恢复和版本化测试。

完成标准：

- 规则迁移可审计、可预览、可失败恢复。

## RC-16：删除回退、幂等、并发与事务闭环

任务目标：

补齐数据生命周期和一致性保护，确保 Activity 删除、修改、重复运行和并发场景不会破坏当前纪录。

前置条件：`RC-14`、`RC-15`。

必须完成：

- active 来源 Activity 删除或失效后标记 invalidated。
- 从剩余有效历史中提升下一条 active。
- 回退不误报为新纪录。
- Activity 关键成绩修改触发受影响类型重算。
- 同一证据、事件、Achievement 和通知幂等。
- 当前纪录替换处于单一事务。
- 并发时不会出现零 active 中间状态或多个 active。

交付物：

- 生命周期一致性实现。
- 删除、修改、并发和幂等测试。

完成标准：

- Milestone B 完成。

## RC-17：当前纪录、详情与历史只读 API

任务目标：

提供前端需要的正式纪录查询能力，并保持现有 `get_career_pb()` 兼容。

前置条件：`RC-06`、`RC-16`。

必须完成：

- 扩展 `get_career_pb()` 的 status、source mode 和安全展示字段。
- 实现纪录详情 API。
- 实现单项历史 API，按发生日期升序。
- 支持 sport、year、pb_type、source 筛选。
- 返回统一 envelope、稳定空态和 resolver/rebuild 状态。
- 所有记录包含 `detail_link.activity_id` 和 `source = "career"`。
- 递归清除禁止字段和本地路径。

交付物：

- 后端只读 API。
- pywebview wrapper。
- `docs/js_api_contract.json` 更新。
- API 测试。

完成标准：

- RC-07 前端设计所需正式数据均可由只读 API 提供。

## RC-18：候选决策、重建与新纪录事件 API

任务目标：

提供候选查询与确认/拒绝、重建触发/状态查询、新纪录事件消费所需的受控写接口。

前置条件：`RC-17`。

必须完成：

- 实现候选列表 API。
- 实现 confirm/reject，拒绝非法 decision。
- 防止候选重复提交和已决定记录再次修改。
- 实现 rebuild 启动、运行中和结果查询。
- 定义新纪录事件一次性或幂等消费方式。
- 写接口校验 payload、返回明确错误码并记录审计事件。
- 更新 JS API contract 的 readonly/high-risk 属性。

交付物：

- 候选与维护 API。
- 决策/重建/事件 API 测试。

完成标准：

- 前端不需要直接操作 SQLite 或猜测状态迁移。

## RC-19：“记录”导航与当前纪录页面

任务目标：

将现有 PB 页面升级为记录中心的当前纪录视图，保持紧凑、可扫描并完全消费后端 ViewModel。

前置条件：`RC-07`、`RC-17`。

必须完成：

- 二级导航 `PB -> 记录`，页面标题“记录中心”。
- 当前纪录、最近 30 天刷新、待确认数量摘要。
- 运动类型、年份和纪录类型筛选。
- V1 四项跑步纪录卡。
- 展示成绩、提升、日期、来源模式和必要状态。
- 空态不展示未交付的骑行或其他运动占位。
- 现有 Activity Detail 跳转不回归。

明确非目标：

- 前端不计算 PB、improvement 或 confidence label。

交付物：

- 当前纪录页面。
- 前端渲染和契约测试。

完成标准：

- 当前纪录能在真实和 mock ViewModel 下稳定展示。

## RC-20：纪录详情与演进视图

任务目标：

让用户理解纪录的来源、判定口径和长期变化，而不是只看到一个最好成绩。

前置条件：`RC-07`、`RC-17`、`RC-19`。

必须完成：

- 详情展示成绩、提升、前一纪录、实际/标准距离、误差、计时口径和判定依据。
- 打开来源 Activity Detail。
- 演进视图一次只展示一种纪录类型。
- 图表或阶梯图正确表达“时间越低越好”。
- 历史节点展示日期、成绩、提升和 Activity 入口。
- 历史为空或只有首条时有稳定表达。

交付物：

- 详情与演进 UI。
- 图表、历史和跳转测试。

完成标准：

- 用户可从当前纪录追溯完整历史和来源 Activity。

## RC-21：候选纪录确认与拒绝视图

任务目标：

让用户安全处理中置信度纪录，并明确确认前不会影响正式 PB。

前置条件：`RC-07`、`RC-18`、`RC-19`。

必须完成：

- 候选列表展示纪录类型、成绩、实际距离、日期、原因码解释和置信度等级。
- 提供“确认纪录”和“不是有效纪录”。
- 提交期间禁用重复操作。
- 确认后重新比较并刷新当前/历史。
- 拒绝后从候选列表移除且普通刷新不再出现。
- API 失败时保留候选并显示局部错误。

交付物：

- 候选 UI 与交互测试。

完成标准：

- 候选不会在确认前显示为正式纪录或触发通知。

## RC-22：页面状态、响应式、无障碍与刷新反馈

任务目标：

完成记录中心所有非理想状态和跨尺寸体验，并实现不重复的新纪录反馈。

前置条件：`RC-19`、`RC-20`、`RC-21`。

必须完成：

- Loading、Empty、Partial、Rebuilding、Error。
- 重建期间保留上次可用数据。
- 桌面端列表加详情，移动端单列下钻。
- 长中文标题、长成绩、窄窗口不溢出或重叠。
- 状态不只靠颜色，图标按钮有名称和 tooltip。
- 键盘可切换视图、进入纪录、处理候选和打开 Activity。
- 首条纪录与刷新纪录文案区分。
- 通知只在正式新纪录时出现一次，点击进入详情。

交付物：

- 完整状态和响应式实现。
- 桌面/移动截图与无障碍测试。

完成标准：

- Milestone C 完成。

## RC-23：Overview、Timeline、Race、Achievement 联动

任务目标：

将正式纪录事件接入运动生涯其他模块，同时保持各 Resolver 的事实责任和幂等边界。

前置条件：`RC-18`、`RC-22`。

必须完成：

- Overview 展示一个代表性正式纪录摘要。
- Timeline 只展示正式刷新事件，不展示静态 current 或候选。
- 同一 Activity 的 Race、PB、Achievement 合并为一个节点的多个徽标。
- Race Archive 卡显示 PB 徽标但仍打开 Activity Detail。
- Achievement 使用 `achievement:pb:{pb_record_id}` 幂等键。
- 重建无变化、候选、拒绝和回退不重复生成节点或 Achievement。
- 记录失效后的 Achievement 展示策略按冻结契约实现。

交付物：

- 跨模块实现与回归测试。

完成标准：

- 各模块不重复事实、不重复事件、不互相越权计算。

## RC-24：Records Snapshot、AI 与 Trends 联动

任务目标：

将纪录事实安全压缩为 Snapshot，并为 AI 和 Trends 提供有限、可解释的长期摘要。

前置条件：`RC-18`、`RC-23`。

必须完成：

- 复用 `career_snapshots`，不新建平行 snapshot 表。
- Snapshot 只包含当前纪录、最近刷新、候选数量和演进摘要白名单。
- AI 不读取候选的强结论，不重新计算 PB。
- AI 不可用时使用确定性文案。
- Trends 只消费刷新频率和演进事实，不把一次 PB 等同于整体能力提升。
- Snapshot 不包含 raw FIT、轨迹、路径、schema 或 detail link。

交付物：

- Records Snapshot 构建与白名单测试。
- AI/Trends 降级和边界测试。

完成标准：

- AI 与 Trends 能解释纪录，但不能改变或重算纪录。

## RC-25：安全、性能、日志与可观测性闭环

任务目标：

补齐记录中心的非功能性要求，使问题可定位、数据不泄露、性能可接受。

前置条件：`RC-16`、`RC-18`、`RC-24`。

必须完成：

- API 和 metadata 递归禁止 raw FIT、points、track_json、storage_ref、file path、SQLite schema 和本地绝对路径。
- 增量评估、查询和重建有耗时统计。
- 日志记录运行 ID、Resolver 版本、处理/激活/候选/拒绝/失效/跳过数量和原因计数。
- 日志不记录原始轨迹、FIT 内容或不必要位置明细。
- 建立交付手册要求的 records 指标。
- 使用约 10,000 条 Activity 的合成或脱敏数据做性能测试。

交付物：

- 安全边界测试。
- 性能报告。
- 日志和指标实现。

完成标准：

- 性能达到手册目标或有经确认的偏差说明。
- 无敏感字段泄露。

## RC-26：自动化测试矩阵与宽回归

任务目标：

建立从 Registry 到前端和跨模块的完整自动化防回归网，证明记录中心不会破坏现有 ACS 与活动流程。

前置条件：`RC-22`、`RC-23`、`RC-24`、`RC-25`。

必须完成：

- Registry、边界距离、计时、比较、状态和置信度单测。
- migration、历史链、候选、删除回退、幂等、并发集成测试。
- API envelope、筛选、错误码和安全边界测试。
- 当前、详情、演进、候选、状态、响应式和无障碍前端测试。
- Overview、Timeline、Race、Achievement、Snapshot、AI、Trends 联动测试。
- PB 定向测试、全部 Career 测试和相关活动导入回归。
- JSON contract 和 Python 编译检查。

交付物：

- 测试矩阵文档。
- 全部测试结果和已知残余风险。

完成标准：

- Milestone D 完成。
- 无未解释的相关测试失败。

## RC-27：真实数据 dry-run、迁移与人工复核

任务目标：

在不直接污染正式结果的前提下，用当前真实库验证新规则、历史迁移、候选和回退结果。

前置条件：`RC-26`。

必须完成：

- 备份真实数据库并记录校验信息。
- 执行只读或 staging dry-run。
- 输出新增、替换、移除、候选、不变和跳过清单。
- 人工复核边界距离、自动暂停、GPS 漂移、跑步机、重复导入、删除纪录、同日多成绩和跨时区样本。
- 确认差异后执行 migration/rebuild。
- 验证 Activity Detail 回跳和历史演进。
- 准备恢复旧数据库或旧 Resolver 结果的方案。

明确非目标：

- 未完成人工复核前不得将 dry-run 结果直接视为发布数据。

交付物：

- 真实数据回放与迁移报告。
- 差异清单、人工复核结论和恢复说明。

完成标准：

- 真实结果与冻结规则一致，异常项有明确处理。

## RC-28：macOS 当前环境与打包产物验收

任务目标：

验证记录中心在 macOS 开发环境和正式打包应用中的数据、交互、视觉、migration 与性能。

前置条件：`RC-27`。

必须完成：

- 当前 macOS 环境完整功能验收。
- 桌面与窄窗口截图验收。
- pywebview API、中文标题、图标、字体、滚动和键盘交互。
- 打包产物首次启动 migration、重复启动幂等和数据库可写。
- Activity 导入后增量纪录、候选处理、历史、重建和回跳。
- 深色 UI 对比度和长文本不重叠。
- 打包环境下无本地路径泄露。

交付物：

- macOS 验收报告和截图。
- 打包 migration 结果。

完成标准：

- macOS 开发和打包两种环境均通过。

## RC-29：Windows 真机与打包产物验收

任务目标：

验证记录中心在 Windows 真机和正式打包产物中的 SQLite、pywebview、字体、路径和交互兼容性。

前置条件：`RC-27`。

必须完成：

- Windows 真机启动和首次 migration。
- FIT 导入后增量评估、候选、历史、重建和回跳。
- 中文文件名、中文标题、字体与 icon 混排。
- 窄窗口无横向溢出，滚动和图表可用。
- pywebview 初始化慢或接口失败时只显示局部错误态。
- 打包目录和数据库读写权限正常。
- Windows 路径不进入 API、Snapshot 或 UI。

交付物：

- Windows 真机与打包验收报告。
- 截图和已知平台差异。

完成标准：

- Windows 真机与打包产物通过；无法执行时任务保持 Pending/Blocked，不得标记 Done。

## RC-30：最终文档同步与发布门禁

任务目标：

汇总全部实施和验证结果，确保代码、契约、手册、任务状态和用户可见说明一致后再发布。

前置条件：`RC-28`、`RC-29`。

必须完成：

- 更新本任务清单全部状态和证据链接。
- 更新 `docs/运动生涯记录中心（PB功能）开发交付手册.md` 的最终实现差异。
- 更新 `docs/js_api_contract.json`。
- 同步 `docs/脉图运动生涯系统（ACS）开发团队交付手册.md`。
- 同步 `docs/脉图运动生涯系统（ACS）开发任务清单.md`。
- 形成发布说明、已知限制和回滚说明。
- 明确 V1 只支持四项跑步整次活动 PB。
- 确认不宣传最佳分段、骑行、路线、功率曲线或环境纪录。
- 汇总自动化、真实数据、macOS、Windows 和打包验收证据。

交付物：

- 最终完成报告。
- 发布检查表和回滚说明。
- 同步后的文档与契约。

完成标准：

- Milestone E 完成。
- 交付手册 Definition of Done 全部满足。
- 记录中心 V1 才可标记发布完成。

---

# 4. 任务完成报告模板

每个任务完成后建议新增：

```text
docs/records_center_rc_XX_<short_name>_completion_report.md
```

报告至少包含：

```markdown
# RC-XX 完成报告

## 任务目标

## 实际改动

## 契约决定

## 测试与结果

## 真实数据或人工验证

## 未完成项与残余风险

## 下一任务
```

完成报告不能只写“测试通过”，必须说明实际行为、边界和未验证内容。

---

# 5. 最终完成定义

以下条件全部满足后，记录中心 V1 才能完成：

- `RC-00` 至 `RC-30` 全部为 `Done` 或发布后复验为 `Verified`。
- Milestone A-E 全部门禁通过。
- 每条纪录可追溯 Activity。
- 当前、历史、候选、删除回退和重建完整可用。
- 前端、AI、Timeline、Race、Achievement 和 Trends 没有越过事实边界。
- 自动化测试、真实数据、macOS、Windows 和打包产物均有证据。
- 发布文档没有宣传 V1 未交付能力。
