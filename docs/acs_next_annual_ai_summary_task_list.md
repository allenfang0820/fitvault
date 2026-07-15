---
title: ACS 年度 AI 总结开发任务清单
aliases:
  - 运动生涯年度 AI 总结任务清单
  - Annual Career AI Summary Task List
version: v0.3.0
status: Narrative V3 In Progress
type: Ordered Implementation Task List
scope: ACS Overview 年度卡片、Year Snapshot、年度报告状态机、年度 AI 缓存、AI 总结页与真实 LLM
source:
  - docs/acs_next_annual_ai_summary_delivery_manual.md
  - docs/脉图运动生涯系统（ACS）开发团队交付手册.md
  - docs/脉图运动生涯系统（ACS）开发任务清单.md
  - docs/js_api_contract.json
updated: 2026-07-14
---

# ACS 年度 AI 总结开发任务清单

## 0. 文档定位

本文档把 `docs/acs_next_annual_ai_summary_delivery_manual.md` 冻结的产品、数据、AI、缓存、交互和验收规则，拆成可按顺序执行、可独立验证、可逐项 review 的工程任务。

本文档是年度 AI 总结后续开发的任务顺序依据。交付手册仍是功能语义和产品边界的最终依据；若本清单与交付手册冲突，必须先修订本清单，不得在实现中静默改变交付手册。

总目标：

```text
Activity / Resolver canonical facts
  -> Year Snapshot
  -> stable source_fingerprint
  -> annual report state
  -> read API / local fallback
  -> controlled LLM generation
  -> validated evidence-backed report cache
  -> annual AI summary UI
```

最终用户规则：

```text
年度卡片永远可以查看。
没有报告时可以生成。
年度事实变化时可以更新。
事实没有变化时只读取沉淀结果。
AI 只写叙事，不写事实。
```

## 0.1 执行规则

1. 默认严格按本文编号执行，不得跳过未完成依赖。
2. 每次只启动一个可执行任务；确需并行时，任务之间必须没有代码、数据、迁移或契约依赖。
3. 每个任务开始前必须刷新项目契约意识：默认使用首次阅读形成的项目契约摘要；只有当前任务、改动文件、测试失败或 review 风险需要时，才回到项目契约原文重新阅读。
4. 每个任务开始前必须把本任务改写成工程级执行提示词，至少包含目标、范围、约束、预期文件、验证命令和完成定义。
5. 每个任务完成后必须执行定向测试和 adaptive diff review；测试或 review 未通过不得进入下一任务。
6. 每个任务完成后必须更新本清单状态，并新增独立完成报告或在年度 AI 执行日志中记录证据。
7. 若实现需要改变已冻结的产品语义，必须先更新交付手册和本清单，再修改代码。
8. 自动化测试通过只代表对应代码门禁通过，不代表真实 AI、真实用户数据、视觉、打包或跨平台验收完成。
9. 当前工作区可能已有其他未提交改动；不得覆盖、回退或重写无关用户变更。
10. 不得为了让旧测试通过而恢复已退役的通用 MemoryItem、`representative_memories` 或 `memory_count` 产品语义。

状态标记：

- `Pending`：尚未开始。
- `In Progress`：正在执行；最多一个任务处于此状态。
- `Blocked`：存在必须由用户决策或外部环境解除的阻塞。
- `Done`：交付物、定向测试和本任务 review 均已通过。
- `Verified`：后续真实数据、真实 AI、视觉或打包门禁再次验证通过。

## 0.2 全局硬约束

所有任务必须遵守：

- `Activity` 是唯一事实源。
- Race、PB、Achievement、Milestone 等语义只由对应 Resolver 产生。
- `Year Snapshot` 是年度 AI 唯一允许消费的上下文。
- 前端不得扫描 Activity、DOM 或本地缓存拼装 Year Snapshot。
- AI 不得读取 SQLite、raw FIT、`points`、`points_json`、`track_json`、文件路径、媒体引用、token 或 Provider 授权信息。
- AI 不得判断或写入赛事、PB、成就、里程碑等 canonical 事实。
- 年度事实、统计数字、日期、成绩和 `detail_link` 必须由后端回填，前端不得直接信任 LLM 事实文本。
- 年度模式与全生涯模式可以共用页面框架，但 Snapshot、ViewModel、缓存键和生成 API 必须分离。
- 保留现有全生涯 `generate_career_insight` fallback，直到全生涯真实 AI 另行迁移。
- 报告是否可更新只由年度事实指纹变化决定，不由“当前年份 / 历史年份”决定。
- 系统日期、`generated_at`、`as_of_date`、traceId、Prompt 版本和 UI 状态不得单独改变年度事实指纹。
- 相同 `year + fingerprint` 不得重复调用 LLM。
- 更新失败、超时、非 JSON 或证据校验失败不得覆盖旧报告。
- 未完成真实 LLM 验证不得标记“真实 AI 完成”。
- 未完成 macOS / Windows 打包产物验证不得标记“打包级完成”。
- 未完成 Windows 真机验证不得标记“跨平台完成”。

## 0.3 明确不做

本轮不实现：

- 用户编辑年度报告正文。
- 用户可见的报告历史版本管理。
- 社交分享海报或 PDF 导出。
- 自动生成详细训练计划。
- 医疗、伤病或健康诊断。
- 年度 AI 对话追问。
- AI 记忆系统。
- 照片理解或多模态年度总结。
- 在年度卡片内直接展示 AI 结论或生成状态。
- 因 Prompt 或模型升级批量重写历史报告。
- 无事实变化时的“换一种说法”或强制重新生成。

---

# 1. 任务总览

## 1.1 主阶段映射

| 手册阶段 | 目标 | 可执行任务 |
| --- | --- | --- |
| `ACS-Year-AI-00` | 契约与基线冻结 | `00` |
| `ACS-Year-AI-01` | Year Snapshot 白名单与同期比较 | `01A` 至 `01D` |
| `ACS-Year-AI-02` | 稳定 fingerprint 与报告状态机 | `02A` 至 `02B` |
| `ACS-Year-AI-03` | Snapshot 与 AI 输出持久化 | `03A` 至 `03B` |
| `ACS-Year-AI-04` | 年度只读 API 与本地 fallback | `04A` 至 `04B` |
| `ACS-Year-AI-05` | 年度卡片导航与年度页面状态 | `05A` 至 `05D` |
| `ACS-Year-AI-06` | 真实 LLM、schema 与 evidence 回填 | `06A` 至 `06C` |
| `ACS-Year-AI-07` | 更新、缓存、单飞与失败保留 | `07A` 至 `07C` |
| `ACS-Year-AI-08` | 宽回归、真实数据、视觉与发布门禁 | `08A` 至 `08C` |

## 1.2 可执行任务顺序

| 编号 | 任务 | 模块 | 优先级 | 依赖 | 状态 |
| --- | --- | --- | --- | --- | --- |
| `ACS-Year-AI-00` | 当前基线审计与契约同步 | 契约 / 审计 | P0 | 无 | Done |
| `ACS-Year-AI-01A` | Year Snapshot schema 与安全白名单冻结 | Snapshot | P0 | `00` | Done |
| `ACS-Year-AI-01B` | 年度 Activity 聚合、运动分布与月度摘要 | Snapshot | P0 | `01A` | Done |
| `ACS-Year-AI-01C` | 年度 Resolver evidence catalog | Snapshot / Resolver | P0 | `01A`, `01B` | Done |
| `ACS-Year-AI-01D` | 年度 period、data quality 与同期比较 | Snapshot | P0 | `01B`, `01C` | Done |
| `ACS-Year-AI-02A` | canonical JSON 与稳定 source fingerprint | Fingerprint | P0 | `01D` | Done |
| `ACS-Year-AI-02B` | 年度报告状态解析器 | State Machine | P0 | `02A` | Done |
| `ACS-Year-AI-03A` | 年度 Snapshot 持久化与读取 | Persistence | P0 | `02A` | Done |
| `ACS-Year-AI-03B` | `career_ai_insights` schema 与缓存仓储 | Persistence | P0 | `02B`, `03A` | Done |
| `ACS-Year-AI-04A` | 年度报告只读服务与本地 fallback | Backend Service | P0 | `02B`, `03B` | Done |
| `ACS-Year-AI-04B` | `get_career_year_insight` API 与契约 | API | P0 | `04A` | Done |
| `ACS-Year-AI-05A` | 年度卡片导航与键盘可访问性 | Frontend | P1 | `04B` | Done |
| `ACS-Year-AI-05B` | AI 总结页模式、年份选择与年度 ViewModel | Frontend | P1 | `04B`, `05A` | Done |
| `ACS-Year-AI-05C` | 年度页面状态、报告结构与本地降级渲染 | Frontend | P1 | `05B` | Done |
| `ACS-Year-AI-05D` | 年份切换、请求 token 与晚到响应隔离 | Frontend | P0 | `05C` | Done |
| `ACS-Year-AI-06A` | 年度 Prompt、模型调用与严格 JSON 输出 | LLM | P0 | `04B`, `05D` | Done |
| `ACS-Year-AI-06B` | AI schema 校验、evidence 验证与事实回填 | LLM Safety | P0 | `06A` | Done |
| `ACS-Year-AI-06C` | `generate_career_year_insight` 生成 API | API / LLM | P0 | `06B` | Done |
| `ACS-Year-AI-07A` | 缓存命中、幂等与 ready 禁止重复生成 | Cache | P0 | `06C` | Done |
| `ACS-Year-AI-07B` | 单飞控制、并发与原子切换 | Concurrency | P0 | `07A` | Done |
| `ACS-Year-AI-07C` | 失败保留、受控重试、日志与隐私收口 | Reliability / Security | P0 | `07B` | Done |
| `ACS-Year-AI-08A` | 自动化测试矩阵与 ACS 宽回归 | Quality | P0 | `07C` | Done |
| `ACS-Year-AI-08B` | 真实用户数据与桌面 / 移动视觉验收 | Acceptance | P1 | `08A` | Done |
| `ACS-Year-AI-08C` | 跨平台代码检查、打包门禁与文档收口 | Release | P0 | `08B` | Done |
| `ACS-Year-AI-09A` | 完整长文、语气、迁移与生成态契约冻结 | Product / Contract | P0 | `08C` | Done |
| `ACS-Year-AI-09B` | v2 Prompt、schema 校验与后端文章 ViewModel | LLM / Backend | P0 | `09A` | Done |
| `ACS-Year-AI-09C` | v1 缓存兼容与一次性格式升级 | Backend / Cache | P0 | `09B` | Done |
| `ACS-Year-AI-09D` | 文章式报告渲染与明确生成过渡 | Frontend | P0 | `09C` | Done |
| `ACS-Year-AI-09E` | 叙事 v2 回归、真实链路验收与文档收口 | Quality | P0 | `09D` | Done |
| `ACS-Year-AI-FIX-01` | 年度报告生成时间按设备当地时区展示 | Time / Display | P0 | `09E` | Done |
| `ACS-Year-AI-10A` | v3 分层叙事、高光与城市足迹契约冻结 | Product / Contract | P0 | `FIX-01` | Done |
| `ACS-Year-AI-10B` | v3 Snapshot 线索、Prompt 与报告校验实现 | Snapshot / LLM / Backend | P0 | `10A` | Done |
| `ACS-Year-AI-10C` | v3 回归、真实链路验收与文档收口 | Quality | P0 | `10B` | Done |
| `ACS-Year-AI-11A` | v4 分享欲与成就感语气升级 | Prompt / Quality | P0 | `10C` | Done |

当前下一任务：无。完整年度故事 v4 已完成分享欲与成就感语气升级、年度定向测试和文档收口；本轮仍未打包 DMG。

---

# 2. 里程碑与门禁

## Milestone A：契约与 Snapshot 闭环

包含：`ACS-Year-AI-00` 至 `ACS-Year-AI-02B`。

通过条件：

- 旧 Phase7 的通用记忆契约已修正。
- Year Snapshot schema、白名单、稳定排序、同期比较和数据质量语义已冻结。
- 相同事实稳定产生相同 fingerprint。
- `no_data / not_generated / ready / stale` 状态由后端稳定解析。
- 本阶段不调用真实 LLM。

未通过 Milestone A，不得建立年度 AI 输出缓存或年度生成 API。

## Milestone B：持久化与只读体验闭环

包含：`ACS-Year-AI-03A` 至 `ACS-Year-AI-05D`。

通过条件：

- 每个年份可独立保存和读取 Snapshot。
- 每个年度报告拥有独立缓存键和当前展示版本。
- `get_career_year_insight` 只读且绝不调用 LLM。
- 未生成时仍能展示年度事实和本地 fallback。
- 年度卡片只导航，不生成。
- 年份切换不会串写响应。

未通过 Milestone B，不得把真实 LLM 接入用户可见页面。

## Milestone C：真实 AI 与可靠性闭环

包含：`ACS-Year-AI-06A` 至 `ACS-Year-AI-07C`。

通过条件：

- Prompt 只消费 Year Snapshot。
- AI 输出严格经过 schema 和 evidence 校验。
- 事实字段全部由后端回填。
- 相同指纹命中缓存，`ready` 不重复调用 AI。
- 同一 `year + fingerprint` 只有一个生成任务。
- 更新失败保留旧报告。
- 日志和错误不泄露 Prompt、Snapshot、token 或底层请求体。

## Milestone D：验收与发布闭环

包含：`ACS-Year-AI-08A` 至 `ACS-Year-AI-08C`。

通过条件：

- 自动化定向测试与 ACS 宽回归通过。
- 真实用户数据覆盖当前年、历史补录、丰富年度和轻量年度。
- 桌面和移动视口无溢出、重叠或状态覆盖。
- macOS / Windows 代码级检查完成。
- 打包与真机验证按实际结果标记，不虚报完成等级。
- 手册、任务清单、API 契约和完成报告一致。

## Milestone E：完整年度故事闭环

包含：`ACS-Year-AI-09A` 至 `ACS-Year-AI-09E`。

通过条件：

- 用户看到的是一篇连续可读的年度故事，而不是字段卡片集合。
- 报告明确覆盖年度努力、比赛、进步、节奏、比较和写给下一年的话；无对应事实时自然降级。
- AI 采用温暖、克制、真诚的语气，不夸张、不鸡血、不制造焦虑。
- 精确事实仍由后端导语和 evidence 节点提供，AI 不自行计算或创造数字。
- v1 缓存继续可读，并能在不改变事实指纹的前提下一次性升级为 v2。
- 生成过程有明确过渡提示、加载骨架、禁用操作和晚到响应隔离。
- 定向测试、ACS 年度宽回归与可行的真实模型验证通过；不执行 DMG 打包。

## Milestone F：叙事节奏与高光足迹闭环

包含：`ACS-Year-AI-10A` 至 `ACS-Year-AI-10C`。

通过条件：

- 报告开篇不再第一句话一次性公布活动、里程、时长、赛事、PB、成就等全部年度数字。
- 后端提供分层事实引导，数字按阅读节奏逐步展开。
- Year Snapshot 提供后端可信高光候选池，覆盖赛事、PB、成就、最长距离、最长时长、最高海拔、累计爬升阈值和代表城市。
- 城市内容只来自活动定位事实，并通过受控文化词典提供有限提示；AI 不得自由使用常识或暗示用户实际吃喝旅行。
- Prompt 明确要求 AI 围绕数据解释“为什么值得记住”，而不是只陈述统计。
- 无高光或无城市时自然省略，不把普通年份写成失败。
- 定向测试、年度宽回归与可行的真实模型验证通过；不执行 DMG 打包。

## Milestone G：分享欲与成就感语气闭环

包含：`ACS-Year-AI-11A`。

通过条件：

- Prompt 版本升级为 `acs.year.summary.zh-CN.v4`，内容 schema 升级为 `acs.year.report.v3`。
- 年度报告语气从平实陈述升级为“有光、有分量、愿意庆祝”，让用户产生分享欲和成就感。
- 标题、副标题、开篇、收束和分享文案允许更有年度感，但仍必须站在 Year Snapshot 事实之上。
- 禁止营销鸡血、夸张等级评价、生活事件和心理状态推断。
- v2 旧报告继续可读；v3 schema 作为受控格式升级触发条件，不改变事实 fingerprint。
- 年度定向测试、静态校验和文档收口通过；不执行 DMG 打包。

---

# 3. 详细任务

## `ACS-Year-AI-00`：当前基线审计与契约同步

任务目标：

建立年度 AI 总结开发的可信起点，修正与 2026-07-13 通用记忆退役决策冲突的现行文档和 API 契约，冻结后续任务使用的项目契约摘要。

前置条件：无。

实施范围：

- `docs/acs_next_annual_ai_summary_delivery_manual.md`
- `docs/脉图运动生涯系统（ACS）开发团队交付手册.md`
- `docs/脉图运动生涯系统（ACS）开发任务清单.md`
- `docs/js_api_contract.json`
- `career_backend.py`
- `main.py`
- `track.html`
- Career Snapshot / Career Insight / Overview 年度卡片相关测试

必须完成：

- 列出现有 Career Snapshot、`career_snapshots`、全生涯 fallback 和 AI 总结页真实代码入口。
- 列出现有年度卡片 ViewModel、DOM、悬停提示和点击行为。
- 确认当前没有 Year Snapshot、fingerprint、年度 AI 输出缓存和真实年度 LLM。
- 从现行文档移除 `representative_memories`、`memory_count` 和旧通用 MemoryItem 作为 AI 输入的描述。
- 明确底层 `career_memory_items` 仅可作为现有赛事照片内部存储实现，不进入年度 Snapshot。
- 明确全生涯 Snapshot 与年度 Snapshot 的作用域、ID、版本和 API 分离。
- 把手册核心契约整理成后续任务复用的项目契约摘要。

明确非目标：

- 不实现 Year Snapshot。
- 不改变运行时行为。
- 不删除历史完成报告；只允许标注其历史状态。

交付物：

- 契约同步后的现行文档。
- `docs/acs_next_annual_ai_summary_execution_log.md`，记录契约摘要、基线和每个后续任务结果。
- `docs/acs_year_ai_00_contract_freeze_completion_report.md`。

完成标准：

- 现行文档不再把通用记忆作为 AI Snapshot 白名单。
- 交付手册、主任务清单和 API 契约描述一致。
- 定向文档 / 静态契约测试通过。
- diff review 确认没有运行时代码行为变化。

建议验证：

```bash
.venv312/bin/python -m pytest tests/test_career_snapshot_builder.py tests/test_career_snapshot_persistence.py tests/test_career_insight_api_skeleton.py tests/test_career_memory_retirement.py -q
.venv312/bin/python -m json.tool docs/js_api_contract.json >/dev/null
! rg -n "representative_memories|memory_count" docs/脉图运动生涯系统（ACS）开发团队交付手册.md docs/脉图运动生涯系统（ACS）开发任务清单.md docs/js_api_contract.json
```

## `ACS-Year-AI-01A`：Year Snapshot schema 与安全白名单冻结

任务目标：

先用后端结构和测试冻结 `acs.year.v1`，确保后续聚合、指纹、缓存和 LLM 都消费同一个年度数据契约。

前置条件：`ACS-Year-AI-00`。

必须完成：

- 定义顶层字段：`snapshot_version`、`scope`、`year`、`period`、`summary`、`sport_breakdown`、`month_digest`、`evidence_catalog`、`comparison`、`data_quality`、`source_fingerprint`。
- 定义每个字段类型、空值语义、排序规则和数值精度。
- 定义允许进入 Snapshot 的 Activity 安全字段和 Resolver 派生字段。
- 定义递归禁止键集合，至少覆盖 raw FIT、points、track、路径、媒体、SQL、token、Provider 配置和已退役记忆字段。
- 定义合法年份范围和无数据年份行为。
- 建立丰富年度、轻量年度、无数据年度、当前部分年度的测试 fixture。

明确非目标：

- 不实现真实 LLM。
- 不持久化 Snapshot。
- 不让前端接触 Snapshot 原文。

建议目标文件：

- `career_backend.py`
- `tests/test_career_year_snapshot_contract.py`
- `docs/js_api_contract.json`，仅在需要登记调试或内部契约时更新

完成标准：

- schema 可以独立表达手册 7.2 的完整样例。
- 禁止字段递归检查可复用，不只检查顶层。
- 旧 Career Snapshot 测试保持通过。

建议验证：

```bash
.venv312/bin/python -m pytest tests/test_career_year_snapshot_contract.py tests/test_career_snapshot_builder.py -q
.venv312/bin/python -m py_compile career_backend.py
```

## `ACS-Year-AI-01B`：年度 Activity 聚合、运动分布与月度摘要

任务目标：

实现 Year Snapshot 的 Activity 事实层，只读取目标年份未删除 Activity，产出稳定年度统计、运动类型分布和 1 至 12 月摘要。

前置条件：`ACS-Year-AI-01A`。

必须完成：

- 按 canonical 活动日期筛选目标自然年。
- 排除已删除或不可用 Activity。
- 汇总活动次数、总距离、总时长和可靠城市覆盖数。
- 按规范化 sport 输出活动次数、距离和时长。
- 输出 12 个月稳定月度摘要；无活动月份使用明确零值或按冻结 schema 省略，不得前后摇摆。
- 每月 `primary_sport` 由后端稳定规则确定。
- 数字统一精度，避免浮点噪声。
- `available_years` 的底层查询只基于有效 Activity，并倒序稳定。

明确非目标：

- 不把普通 Activity 全量列表放入 Snapshot。
- 不从标题推断运动类型、城市、赛事或里程碑。
- 不读取轨迹点补算年度距离。

建议目标文件：

- `career_backend.py`
- `tests/test_career_year_snapshot_activity_aggregation.py`

完成标准：

- Snapshot 只包含目标年份数据。
- 单运动、多运动、空月份、删除 Activity 和跨年边界测试通过。
- 聚合结果与现有 canonical Activity 事实一致。

## `ACS-Year-AI-01C`：年度 Resolver evidence catalog

任务目标：

建立年度关键事件证据目录，为 AI 的 `key_moments` 提供唯一可引用集合和 Activity Detail 回跳锚点。

前置条件：`ACS-Year-AI-01A`、`ACS-Year-AI-01B`。

必须完成：

- 只读取目标年份 active 的 Race、PB、Achievement / Milestone 结果。
- 每条 evidence 至少包含 `evidence_id`、`activity_id`、`type`、`title`、`date`、`value` 和后端 detail link 所需信息。
- `evidence_id` 必须稳定且带类型命名空间，例如 `race:{id}`、`pb:{id}`、`achievement:{id}`。
- 同一事实去重；每个 evidence 必须绑定有效 Activity。
- 稳定排序：`date + type + evidence_id`。
- 定义没有 Resolver 事件时，是否允许后端选择少量代表 Activity；若实现，选择规则必须确定性、可测试且不得由 AI 自由搜索。
- 赛事数量、PB 数量、成就数量必须与 evidence / Resolver 事实一致。

明确非目标：

- 不读取候选或 rejected / superseded 结果作为当前年度事实，除非某类 Resolver 契约明确要求历史证据且手册已更新。
- 不把照片、缩略图、媒体引用或故事放入 evidence。
- 不让 AI 生成 evidence ID。

建议目标文件：

- `career_backend.py`
- `tests/test_career_year_snapshot_evidence.py`
- Race / PB / Achievement 现有 resolver 测试

完成标准：

- 丰富年度和普通活动年度均有稳定行为。
- 跨年份 Resolver 事件不会进入目标年度。
- 所有 evidence 可以回跳 Activity Detail。

## `ACS-Year-AI-01D`：年度 period、data quality 与同期比较

任务目标：

完成 Year Snapshot 的年度范围、数据截止、部分年度和上一年同期比较，使 AI 不需要计算差值或猜测数据完整性。

前置条件：`ACS-Year-AI-01B`、`ACS-Year-AI-01C`。

必须完成：

- 定义 `start_date`、`end_date`、`as_of_date`、`data_through`、`latest_activity_date`、`is_partial_year`。
- 当前年份 `is_partial_year=true`；结束年份使用完整自然年范围。
- `data_through` 使用最新进入 Snapshot 的事实日期，不使用每天变化的系统日期。
- 当前年份比较上一年相同 `data_through` 月日范围。
- 已结束年份比较完整自然年。
- 比较结果由后端输出活动、距离、时长、赛事和 PB 差值。
- 上一年无可靠可比数据时返回 `comparison.status=unavailable` 和稳定原因码。
- 定义 `data_quality.status` 与 warnings；缺失不等于零。
- 闰年、1 月初、上一年无数据和跨时区日期边界必须测试。

明确非目标：

- AI 不计算百分比或差值。
- 不因查看日期推进改变比较截止范围。

完成标准：

- 当前年和历史年比较规则均被测试锁定。
- 没有新增事实时，次日重新构建 Snapshot 的报告事实内容保持一致。

---

## `ACS-Year-AI-02A`：canonical JSON 与稳定 source fingerprint

任务目标：

实现年度事实的规范化序列化和 SHA-256 指纹，准确表达“进入年度报告的事实是否发生变化”。

前置条件：`ACS-Year-AI-01D`。

必须完成：

- 单独定义 `report_source_fields`，不得直接对整个运行时 Snapshot 做 hash。
- 字典键稳定排序。
- evidence 按冻结规则稳定排序。
- sport 和 month 列表稳定排序。
- 数字统一精度和 JSON 表达。
- 排除 `source_fingerprint` 自身、`generated_at`、`as_of_date`、traceId、状态文案、日志字段和随机值。
- 排除照片、UI 设置和 Prompt / model 版本。
- 输出格式固定为 `sha256:{hex}`。
- 提供可复用 canonical JSON helper，避免缓存层、测试和生成层各自实现。

必须覆盖的变化矩阵：

- 新增、删除或修改允许字段 -> fingerprint 变化。
- Race / PB / Achievement / Milestone active 事实变化 -> fingerprint 变化。
- 照片增删排序 -> 不变化。
- 系统日期或构建时间变化 -> 不变化。
- JSON 字典插入顺序变化 -> 不变化。
- 相同数值的浮点表现差异 -> 不变化。

完成标准：

- 相同事实跨多次构建得到相同 fingerprint。
- 手册第 17 节触发矩阵全部有自动化测试。

建议测试：

```bash
.venv312/bin/python -m pytest tests/test_career_year_snapshot_fingerprint.py -q
```

## `ACS-Year-AI-02B`：年度报告状态解析器

任务目标：

建立纯后端状态解析器，根据当前 Snapshot、成功报告、AI 可用性和进行中任务返回唯一报告状态及允许操作。

前置条件：`ACS-Year-AI-02A`。

必须完成：

- 核心持久状态：`no_data`、`not_generated`、`ready`、`stale`。
- 运行时状态：`generating`、`failed`、`ai_unavailable`。
- 返回 `can_generate`、`can_refresh`、`has_source_changes`。
- 没有数据优先于没有报告。
- 有成功报告且 fingerprint 相同 -> `ready`。
- 有成功报告且 fingerprint 不同 -> `stale`。
- 更新失败后仍保留旧报告，同时表达本次失败，不把年度退化为无报告。
- AI 不可用且已有报告时继续返回报告。
- `ready` 状态不得通过前端参数变成可生成。
- 状态文案与状态码分离；前端只消费状态码决定操作。

明确非目标：

- 不在本任务调用 LLM。
- 不让前端用当前年份推断刷新能力。

完成标准：

- 状态转换表全部有参数化测试。
- 状态解析器不依赖 DOM、当前页面或前端缓存。

---

## `ACS-Year-AI-03A`：年度 Snapshot 持久化与读取

任务目标：

复用 `career_snapshots` 保存每年可重建的白名单 Snapshot，并提供后端内部构建、保存和读取能力。

前置条件：`ACS-Year-AI-02A`。

必须完成：

- 使用稳定 ID：`career_snapshot:year:{year}`。
- 使用 `snapshot_type=career_year` 和 `source_version=acs.year.v1`。
- 每年独立 upsert，不覆盖全生涯 `career_snapshot:latest`。
- 保存前执行禁止字段递归检查。
- 读取历史脏数据时再次裁剪和校验。
- 明确事务、commit / rollback 和连接所有权。
- 保存结果返回 fingerprint、版本和保存时间，但不向普通前端展示完整 Snapshot。
- 年度 Snapshot 仍是派生数据，可安全重建，不成为 canonical 事实源。

兼容要求：

- 现有 `save_career_snapshot()`、`get_latest_career_snapshot()` 和全生涯测试不得回归。
- 不暴露前端任意写 Snapshot 的 pywebview API。

完成标准：

- 多年份保存和读取互不覆盖。
- 全生涯与年度 Snapshot 共表但作用域隔离。
- 历史脏内容不会把禁止字段返回给调用方。

## `ACS-Year-AI-03B`：`career_ai_insights` schema 与缓存仓储

任务目标：

新增独立 AI 输出缓存表和仓储函数，使年度报告按年份、事实指纹、Prompt 和模型可审计地保存。

前置条件：`ACS-Year-AI-02B`、`ACS-Year-AI-03A`。

必须完成：

- 新增表 `career_ai_insights`。
- 至少包含 `id`、`scope`、`scope_key`、`snapshot_fingerprint`、`snapshot_version`、`prompt_version`、`model_id`、`content_json`、`generated_at`、`created_at`、`status`。
- 冻结唯一约束：`scope + scope_key + snapshot_fingerprint + prompt_version + model_id`。
- 建立按 scope / scope_key / status / generated_at 查询的索引。
- 只允许校验成功的输出进入 `ready` 缓存。
- 新报告成功后把旧当前版本标为 `superseded`，并在同一事务原子切换。
- 第一版保留历史记录用于审计，但不提供用户可见版本管理。
- 提供读取当前成功报告、按完整缓存键查找、插入新报告和切换当前版本的仓储函数。

迁移要求：

- schema migration 可重复执行。
- 老数据库升级不丢失现有 Career Snapshot 或 canonical 表数据。
- migration 失败必须 rollback 或返回明确失败，不留下半建表状态。

完成标准：

- 多年份、多 fingerprint 缓存互不覆盖。
- AI 输出不会写入 Activity、Race、PB、Achievement 或照片表。

---

## `ACS-Year-AI-04A`：年度报告只读服务与本地 fallback

任务目标：

实现不调用 LLM 的年度报告页后端服务，统一返回年份列表、当前事实、缓存报告、报告状态和本地可用内容。

前置条件：`ACS-Year-AI-02B`、`ACS-Year-AI-03B`。

必须完成：

- 构建或读取当前 Year Snapshot。
- 后端返回 `available_years`，前端不得扫描 Activity。
- 返回 `year`、`report_state`、`can_generate`、`can_refresh`、`has_source_changes`、`facts`、`report`、`generated_at`、`data_through` 和 `status`。
- `facts` 直接来自后端年度安全聚合。
- 本地 fallback 可返回关键事件列表、月度节奏摘要和比较差值，但不得伪装为 AI 报告。
- 无任何成功报告时，`report` 必须为空或明确为非 AI fallback，不生成固定 AI 叙事。
- AI 不可用但有历史成功报告时继续返回该报告。
- 默认年份为最近一个有有效 Activity 的年份。

明确非目标：

- 本服务绝不调用 LLM。
- 不写 AI 成功缓存。
- 不把 Snapshot 原文或 debug JSON返回前端。

完成标准：

- `no_data`、`not_generated`、`ready`、`stale`、AI 不可用且有旧报告均有稳定返回。

## `ACS-Year-AI-04B`：`get_career_year_insight` API 与契约

任务目标：

通过 `main.Api` 暴露年度报告只读能力，并同步 pywebview envelope 和 JS API 契约。

前置条件：`ACS-Year-AI-04A`。

必须完成：

- 新增 `get_career_year_insight({ year })`。
- 只接受冻结字段；未知字段拒绝。
- 对 year 执行类型、范围和存在性校验。
- 使用统一 `{ok, code, msg, data, traceId}` envelope。
- 无数据年份返回稳定业务状态，不泄露 SQL 或栈信息。
- `docs/js_api_contract.json` 登记完整 ViewModel 和只读属性。
- 日志只记录 year、traceId、结果状态和耗时，不记录 Snapshot 原文。

兼容要求：

- 不改变现有 `generate_career_insight` payload 和返回结构。
- 不把年度字段塞进全生涯 API。

完成标准：

- pywebview wrapper、参数校验、错误 envelope 和 API 文档测试通过。

建议验证：

```bash
.venv312/bin/python -m pytest tests/test_career_year_insight_read_api.py tests/test_career_phase9_pywebview_envelope.py -q
.venv312/bin/python -m json.tool docs/js_api_contract.json >/dev/null
```

---

## `ACS-Year-AI-05A`：年度卡片导航与键盘可访问性

任务目标：

把 Overview 年度卡片改造成稳定的年度档案入口，点击只进入对应年份年度总结，不调用 AI。

前置条件：`ACS-Year-AI-04B`。

必须完成：

- 年度卡片使用原生 `button` 或等价可键盘操作语义。
- `aria-label="查看 {year} 年度总结"`。
- Enter / Space 可触发。
- 悬停提示从“点击我试试”改为“查看年度总结”。
- 保留 DIN 年份、统计胶囊、现有轻微上浮和克制布局。
- 点击执行：切换到 AI 总结页、进入年度模式、选中卡片年份、发起只读加载。
- 点击不得调用 `generate_career_year_insight` 或任何 LLM。
- 年度卡片不增加 `not_generated / stale / ready` 状态胶囊。

完成标准：

- 静态和行为测试证明点击只导航与读取。
- 鼠标和键盘均可用。
- 原 Overview 年度统计无回归。

## `ACS-Year-AI-05B`：AI 总结页模式、年份选择与年度 ViewModel

任务目标：

在现有 AI 总结页框架中增加 `年度总结 / 生涯总结` 模式和后端驱动的年份选择，同时保留全生涯 fallback。

前置条件：`ACS-Year-AI-04B`、`ACS-Year-AI-05A`。

必须完成：

- 顶部使用分段控制：`年度总结 | 生涯总结`。
- 年度模式显示年份胶囊，来源仅为 `available_years`。
- 顶部导航进入时默认最近有数据年份。
- 年度卡片进入时选中卡片年份。
- 没有年度数据时不伪造当前年份。
- 年度与生涯分别维护 ViewModel、loading、error 和 request state。
- 切换模式不覆盖另一模式已加载内容。
- 生涯模式继续使用现有 `generate_career_insight` fallback 行为。

视觉约束：

- 年份是明确视觉信号，但不使用营销式 Hero。
- 不把页面所有段落做成嵌套卡片。
- 移动端年份胶囊可换行或横向安全滚动，不溢出。

完成标准：

- 年度 / 生涯模式可稳定切换。
- 不存在前端推断年份或复用错误缓存键。

## `ACS-Year-AI-05C`：年度页面状态、报告结构与本地降级渲染

任务目标：

完成年度页面的事实概览、报告章节和全状态渲染，不依赖真实 LLM 即可形成可用页面闭环。

前置条件：`ACS-Year-AI-05B`。

必须完成：

- 渲染年份标题、生成时间、`data_through` 和部分年度说明。
- 年度事实概览直接渲染后端 facts：活动、里程、时长、赛事、PB、成就 / 里程碑、可靠城市数。
- 报告章节顺序：主线、关键时刻、运动节奏、上一年比较、下一年方向、免责声明。
- 关键时刻使用后端回填事实并可回跳 Activity Detail。
- `not_generated`：显示事实、待生成文案和生成按钮。
- `ready`：显示报告，不显示生成按钮。
- `stale`：保留旧报告，显示“有新的运动数据”和更新按钮。
- `generating`：保留事实；更新时保留旧报告，禁用重复操作。
- `failed`：保留旧报告或事实，提供本次重试。
- `ai_unavailable`：显示事实和已有报告，不显示虚假生成按钮。
- `no_data`：稳定空态，无生成按钮。

完成标准：

- 所有状态有独立静态测试。
- loading、旧报告和错误提示不会互相覆盖。
- 长中文、窄屏和无关键事件年度不溢出。

## `ACS-Year-AI-05D`：年份切换、请求 token 与晚到响应隔离

任务目标：

防止年度页面在快速切换年份、切换模式或销毁页面后发生 A 年响应写入 B 年的竞态。

前置条件：`ACS-Year-AI-05C`。

必须完成：

- 每次年度只读请求保存 `requestYear` 和递增 request token。
- 响应写入前同时校验当前模式、年份和 token。
- 切换年份不清空已缓存的其他年份 ViewModel。
- 相同年份重复只读加载可以复用页面缓存，但必须允许显式刷新状态。
- 页面离开或切到生涯模式后，晚到年度响应不得覆盖当前页面。
- 生成请求与只读请求使用可区分 token。

完成标准：

- 使用可控 Promise 或 mock API 测试逆序响应。
- A 年响应不能污染 B 年页面或 B 年缓存。

---

## `ACS-Year-AI-06A`：年度 Prompt、模型调用与严格 JSON 输出

任务目标：

建立年度报告专用 Prompt assembler 和受控 LLM 调用，只把白名单 Year Snapshot 交给现有 LLM 配置链路。

前置条件：`ACS-Year-AI-04B`、`ACS-Year-AI-05D`。

必须完成：

- Prompt 版本固定为独立值，例如 `acs.year.summary.zh-CN.v1`。
- system / developer prompt 明确 AI 只能使用给定 Snapshot。
- 当前部分年度必须使用“截至当前数据周期”语气。
- 禁止伤病、心理、生活事件、训练动机、年度等级、详细训练计划和医疗建议。
- 数据不足时要求降级表达，不补全故事。
- 输出严格 JSON，不允许 Markdown code fence 或附加解释。
- 模型、URL、token 和 Provider 从现有受控 LLM 配置链路读取；前端不得提交。
- 调用层设置受控超时和最多一次格式修复机会。
- 测试使用 fake client，不依赖真实网络。

隐私要求：

- 不在日志输出完整 Prompt、Snapshot 或原始 AI 响应。
- 只记录 year、fingerprint 前缀、prompt version、model id、耗时和结果状态。

完成标准：

- 测试能证明禁止字段和前端 payload 不进入 Prompt。
- fake LLM 可返回符合 schema 的示例结果。

## `ACS-Year-AI-06B`：AI schema 校验、evidence 验证与事实回填

任务目标：

把 LLM 输出视为不可信叙事草稿，经过严格校验后转换成可缓存、可展示的年度报告。

前置条件：`ACS-Year-AI-06A`。

必须完成：

- 校验 `schema_version` 和请求 year。
- 限制 headline、annual_thread、rhythm_summary、comparison_summary、directions、commentary 和 caveats 的数量与长度。
- 所有 `key_moments[].evidence_id` 必须存在于当前 Snapshot。
- 去除重复和未知 evidence；未知证据达到失败阈值时整份输出失败。
- 关键时刻限制 3 至 5 个；证据不足时允许少于 3 个，不要求 AI 编造。
- 使用后端 evidence 回填标题、日期、成绩、activity_id 和 detail link。
- 清洗 HTML、脚本、Markdown code fence 和异常控制字符。
- 比较不可用时，AI 不得输出确定性同比结论；必要时后端置空或降级。
- 输出 year、事实摘要和关键事件事实不得采用 AI 自己提供的值。

完成标准：

- 非 JSON、错 year、未知 evidence、重复 evidence、超长输出和脚本内容均有测试。
- 通过校验的报告中所有事实可追溯到当前 Snapshot。

## `ACS-Year-AI-06C`：`generate_career_year_insight` 生成 API

任务目标：

新增年度生成 / 更新 API，严格按照后端状态决定是否允许调用 LLM。

前置条件：`ACS-Year-AI-06B`。

必须完成：

- 新增 `generate_career_year_insight({ year })`。
- 前端只能提交 year；拒绝 prompt、Snapshot、model、force 和任意事实字段。
- `not_generated` 允许首次生成。
- `stale` 允许更新。
- `ready` 返回缓存或“已是最新”，不得调用 LLM。
- `no_data` 返回不可生成业务状态。
- AI 配置缺失返回 `ai_unavailable`，保留 facts 和旧报告。
- 成功流程：构建当前 Snapshot -> 再查缓存 -> 调用 LLM -> 校验 -> 后端回填 -> 原子写缓存 -> 返回新报告。
- 使用统一 pywebview envelope。

完成标准：

- 使用 fake LLM 验证各状态调用次数。
- `ready`、`no_data` 和非法 payload 的 LLM 调用次数为零。
- 生成成功后只读 API 可立即读到新报告。

---

## `ACS-Year-AI-07A`：缓存命中、幂等与 ready 禁止重复生成

任务目标：

确保相同年度事实只产生一次有效 AI 调用和一个可复用缓存结果。

前置条件：`ACS-Year-AI-06C`。

必须完成：

- 生成前按完整缓存键再次查询。
- 命中缓存直接返回，不调用 LLM。
- 相同请求重复提交返回一致报告和状态。
- `ready` 状态即使前端构造额外参数也不能绕过。
- Prompt / model 版本变化不自动把用户可见状态改为 stale。
- 若内部明确使用新 Prompt / model，必须遵守本期产品规则，不向用户暴露无事实变化的重新生成入口。
- 缓存读取和状态解析使用同一当前报告选择规则。

完成标准：

- fake LLM 调用计数锁定缓存命中行为。
- 数据库唯一约束和服务层幂等同时测试。

## `ACS-Year-AI-07B`：单飞控制、并发与原子切换

任务目标：

实现同一 `year + fingerprint` 单飞控制，避免重复点击、多窗口或并发请求产生重复 LLM 调用和版本竞争。

前置条件：`ACS-Year-AI-07A`。

必须完成：

- 同一进程内按 `year + fingerprint` 建立单飞锁或任务注册表。
- 第二个相同请求复用进行中状态或等待同一结果，不发第二次 LLM。
- 不同年份允许并行，前提是数据库连接和缓存事务安全。
- 锁定后再次检查缓存，覆盖两个窗口同时到达的情况。
- 新报告写入与旧报告 supersede 在一个事务中完成。
- 生成期间若年度事实再次变化，旧 fingerprint 结果不得被标记为当前 `ready`；返回后应重新解析为 stale 或按冻结策略丢弃为非当前结果。
- 异常、取消和超时必须释放单飞状态。

完成标准：

- 并发测试证明同一键只调用一次 LLM。
- 不同年份不会共用锁或串写报告。
- 事务失败后旧报告仍为当前版本。

## `ACS-Year-AI-07C`：失败保留、受控重试、日志与隐私收口

任务目标：

完成年度生成链路的失败策略、安全日志和用户可恢复行为。

前置条件：`ACS-Year-AI-07B`。

必须完成：

- 覆盖网络失败、超时、非 JSON、schema 失败、错 year、未知 evidence、空输出和超长输出。
- 允许对纯格式错误进行最多一次受控修复或重试；不得无限重试。
- 首次生成失败保留 facts 和 failed 状态。
- 更新失败保留旧报告、原 generated_at 和旧 fingerprint 记录。
- 错误 envelope 不回显 token、URL 密钥、Prompt、Snapshot、底层请求体或原始 AI 响应。
- 日志只保留 request / trace id、year、fingerprint 前缀、prompt version、model id、耗时、缓存命中和结果状态。
- 明确错误码：参数错误、无数据、AI 未配置、生成中、超时、格式失败、证据失败和内部持久化失败。
- 前端 retry 只重试本次失败，不提供无事实变化的任意重新生成。

完成标准：

- 失败矩阵测试全部通过。
- 日志捕获测试确认没有敏感内容。
- 任意失败均不污染 canonical 表。

---

## `ACS-Year-AI-08A`：自动化测试矩阵与 ACS 宽回归

任务目标：

汇总并补齐 Snapshot、fingerprint、状态机、缓存、API、前端、并发、安全和兼容测试，执行最宽实际可行的 ACS 回归。

前置条件：`ACS-Year-AI-07C`。

必须完成：

- 建立年度 AI 测试矩阵，映射交付手册第 19、20 节每条验收标准。
- 运行所有新增 `test_career_year_*` 测试。
- 联跑现有 Career Snapshot、Career Insight、Overview、Timeline、Race、PB、Achievement 和 pywebview envelope 测试。
- 静态检查禁止字段、前端零推断、年度 / 生涯 API 分离。
- 运行 Python 编译和 `docs/js_api_contract.json` 解析。
- 对当前任务累计 diff 做全量 review，重点检查迁移、并发、缓存、公共 API、安全和跨模块回归。
- 失败测试不得通过删除断言、降低语义或恢复旧记忆能力规避。

建议最终验证：

```bash
.venv312/bin/python -m pytest tests/test_career_year_*.py -q
.venv312/bin/python -m pytest tests/test_career*.py -q
.venv312/bin/python -m py_compile career_backend.py main.py llm_backend.py profile_backend.py
.venv312/bin/python -m json.tool docs/js_api_contract.json >/dev/null
```

完成标准：

- 定向测试全绿。
- ACS 宽回归全绿，或仅剩有证据且与本功能无关的既有失败，并在报告中准确记录。
- review 无阻塞问题。

## `ACS-Year-AI-08B`：真实用户数据与桌面 / 移动视觉验收

任务目标：

使用当前真实数据库和受控样例验证年度事实、状态变化、报告沉淀及页面视觉，不只依赖构造单测。

前置条件：`ACS-Year-AI-08A`。

必须覆盖：

- 当前年份持续新增活动。
- 历史年份补导入活动后由 ready 进入 stale。
- 历史年份无事实变化时保持 ready。
- 有赛事、PB、成就的丰富年度。
- 只有普通 Activity 的轻量年度。
- 单运动类型和多运动类型年度。
- 上一年无可靠比较数据。
- AI 配置缺失、超时和格式错误。
- 更新失败后旧报告仍可读。

视觉验收：

- 宽屏桌面、常规笔记本、窄屏 / 移动视口。
- 年份胶囊、事实概览、主操作和长中文不溢出。
- loading、旧报告、状态提示和错误不会重叠。
- 当前部分年度表达清楚。
- 关键时刻回跳 Activity Detail 正确。
- 年度卡片悬停和键盘焦点清楚。

交付物：

- `docs/acs_year_ai_08_real_data_visual_acceptance_report.md`。
- 必要的截图或逐项人工验收记录。
- 真实 AI 验证使用的模型、Prompt 版本、年份和结果状态；不得记录完整 Prompt、Snapshot 或 token。

完成标准：

- 真实数据状态与自动化状态机一致。
- 真实 AI 至少完成一次首次生成和一次事实变化后的更新验证，才能标记真实 AI 完成。
- 视觉无阻塞缺陷。

## `ACS-Year-AI-08C`：跨平台代码检查、打包门禁与文档收口

任务目标：

完成跨平台代码级检查、实际可执行的打包验证和最终文档同步，明确交付等级。

前置条件：`ACS-Year-AI-08B`。

必须完成：

- 检查 SQLite migration、线程 / 锁、时间与时区、JSON、日志和 pywebview 在 macOS / Windows 的兼容性。
- 检查 LLM 网络调用的证书、超时、编码和打包依赖。
- 按当前环境实际执行可行的 macOS 打包产物验证。
- Windows 代码级检查与测试必须执行；Windows 真机和打包产物只能按实际结果标记。
- 同步：年度交付手册、本任务清单、主 ACS 任务清单、API 契约、执行日志和最终完成报告。
- 记录未完成边界、已知风险、回滚方式和下一步建议。
- 不把代码级检查写成真机验证，不把单元测试写成打包验证。

交付物：

- `docs/acs_year_ai_summary_completion_report.md`。
- 更新后的任务状态与发布门禁表。

完成标准：

- 文档、代码、API 和测试契约一致。
- 完成等级准确：代码级 / 真实 AI / 产品验收 / macOS 打包 / Windows 真机分别标记。
- 没有未说明的阻塞项或已知数据风险。

## `ACS-Year-AI-09A`：完整长文、语气、迁移与生成态契约冻结

任务目标：把已确认的年度运动平台式长文形态固化为工程契约，避免 Prompt、后端和前端分别解释产品语义。

实施范围：年度 AI 交付手册、本任务清单、执行日志；不得修改运行时代码。

完成定义：冻结 v2 schema、章节顺序、动态省略规则、AI 语气、事实/叙事边界、v1 兼容升级、生成中提示和分享文案预留；文档静态检查与 diff review 通过。

## `ACS-Year-AI-09B`：v2 Prompt、schema 校验与后端文章 ViewModel

任务目标：让任意已配置可用模型按统一语气生成 `acs.year.report.v2` 母稿，并由后端校验、清洗、回填证据和组装文章 ViewModel。

实施范围：`llm_backend.py`、`career_backend.py`、年度 Prompt/校验/服务测试；不得改变 Year Snapshot、事实 fingerprint、模型配置链路或前端请求 payload。

完成定义：Prompt 版本升级为 v2；章节 type、顺序、文本长度、evidence 和动态省略均受校验；后端生成事实导语；精确事实不依赖 AI 文本；所有相关测试通过并完成 diff review。

## `ACS-Year-AI-09C`：v1 缓存兼容与一次性格式升级

任务目标：保持旧报告可读，同时允许同一事实指纹从 v1 一次性升级到 v2，且失败不覆盖旧报告。

实施范围：年度报告 read/generate service、缓存选择逻辑、API ViewModel 与测试；不得删除历史缓存、改变 `source_fingerprint` 或允许无边界重复生成。

完成定义：只有 v1 时返回 `format_upgrade_available=true` 和受控升级动作；v2 成功后成为当前版本；v2 已存在时禁止重复；失败继续展示 v1；并发与缓存测试通过。

## `ACS-Year-AI-09D`：文章式报告渲染与明确生成过渡

任务目标：把年度报告渲染为连续长文，并让用户点击后立即明确知道系统正在工作。

实施范围：`track.html`、年度前端契约测试；不得修改 Overview 年卡片的只导航边界，不得让前端拼 Snapshot、模型参数或 canonical 事实。

完成定义：呈现标题、副标题、事实导语、连续章节、证据节点、收束和写给下一年的话；v1 有兼容视图；生成时显示年度故事主提示、轮换步骤、skeleton/shimmer、禁用按钮并尊重 reduced motion；切年响应隔离保持有效；测试和 diff review 通过。

## `ACS-Year-AI-09E`：叙事 v2 回归、真实链路验收与文档收口

任务目标：验证 v2 在丰富年度、普通年度、无比赛/PB、部分年度、旧缓存和生成失败场景下都可信可读，并收口文档状态。

实施范围：年度测试矩阵、可行的真实已配置模型生成、执行日志、完成报告、任务状态与必要契约同步；不得打包 DMG。

完成定义：年度定向测试与 ACS 相关宽回归全绿；真实模型验证不依赖写死模型；页面无阻塞视觉/交互问题；累计 diff review 通过；任务清单标记完成并明确 DMG 未执行。

## `ACS-Year-AI-10A`：v3 分层叙事、高光与城市足迹契约冻结

任务目标：冻结分层叙事节奏、高光候选池和城市足迹边界，避免年度报告继续像一次性统计播报。

实施范围：年度 AI 交付手册、任务清单和执行日志；不修改运行时代码。

完成定义：文档明确开篇不得一次性公布所有年度数据；高光候选、城市文化词典、动态省略和 AI 禁止推断规则冻结；后续 10B/10C 任务边界清晰。

## `ACS-Year-AI-10B`：v3 Snapshot 线索、Prompt 与报告校验实现

任务目标：让 Year Snapshot、Prompt 和校验器支持高光时刻、城市足迹和分层事实引导。

实施范围：`career_backend.py`、`llm_backend.py`、`track.html`、年度测试和 `docs/js_api_contract.json`。

完成定义：Snapshot 包含安全稳定的 `highlight_moments` 与 `city_moments`；Prompt 要求先主线后数据；校验器支持 `footprints` 与 `fact_leads`；前端可渲染 v3 文章；定向测试通过。

## `ACS-Year-AI-10C`：v3 回归、真实链路验收与文档收口

任务目标：完成 v3 的自动化回归、真实模型链路和文档一致性收口。

实施范围：年度测试矩阵、可行真实链路、执行日志、完成报告、任务状态与 API 契约；不得打包 DMG。

完成定义：年度相关测试、ACS 宽回归、Python 编译和 API JSON 校验通过；真实年度报告生成可用；文档准确记录未执行 DMG。

## `ACS-Year-AI-11A`：v4 分享欲与成就感语气升级

任务目标：在 v3 事实边界和高光机制不变的前提下，把年度报告语气升级为更有分享欲和成就感的年度运动故事。

实施范围：`llm_backend.py`、`career_backend.py`、`track.html`、年度 Prompt / 校验 / 服务 / 前端测试、交付手册、任务清单、执行日志和完成报告。

完成定义：Prompt 版本为 `acs.year.summary.zh-CN.v4`；报告 schema 为 `acs.year.report.v3`；同事实指纹的 v2 报告可受控升级；v2/v3 前端兼容；标题、收束和分享文案更适合截图分享；AI 仍不得编造事实、营销鸡血或生活心理推断；年度定向测试、编译和 JSON 校验通过。

---

# 4. 全局测试矩阵

| 测试域 | 最低覆盖 |
| --- | --- |
| Year Snapshot | 年份隔离、删除过滤、聚合、sport、month、evidence、禁止字段 |
| Period / Comparison | 当前部分年度、历史完整年度、同期截止、闰年、unavailable |
| Fingerprint | 稳定排序、精度、事实变化、照片不变化、日期自然推进不变化 |
| State Machine | `no_data`、`not_generated`、`ready`、`stale`、`generating`、`failed`、`ai_unavailable` |
| Persistence | 多年份 Snapshot、缓存键、唯一约束、迁移幂等、原子切换 |
| Read API | 年份校验、统一 envelope、只读零 LLM、fallback、旧报告读取 |
| Generate API | 允许状态、拒绝状态、未知 payload、AI 不可用、缓存命中 |
| LLM Safety | Prompt 白名单、严格 JSON、错 year、evidence、长度、清洗、事实回填 |
| Concurrency | 单飞、重复点击、多窗口、不同年份、事实中途变化、锁释放 |
| Frontend | 卡片导航、模式、年份、状态、旧报告保留、请求隔离、回跳 |
| Security | 路径 / FIT / points / SQL / token / Prompt / Snapshot 零泄露 |
| Compatibility | 全生涯 Snapshot / fallback、Overview、Timeline、Race、PB、Achievement 无回归 |
| Visual | 桌面、窄屏、长中文、空态、loading、错误、部分年度 |
| Release | 真实数据、真实 AI、macOS、Windows、打包产物分别验收 |

---

# 5. 状态更新与完成报告规范

## 5.1 每个任务开始时

必须：

- 把任务状态改为 `In Progress`。
- 在执行日志写入工程级提示词。
- 记录当前工作区状态和本任务允许修改的文件范围。
- 记录前置任务完成证据和本任务定向测试命令。

## 5.2 每个任务完成时

必须：

- 记录实际修改文件。
- 记录验证命令和结果。
- 记录 adaptive review 结论及修复循环。
- 记录未验证边界。
- 把状态改为 `Done`。
- 明确下一任务编号，不询问是否继续；测试和 review 通过后按顺序继续。

## 5.3 完成报告最低内容

```text
任务编号与目标
契约摘要
实现范围
关键设计决定
实际修改文件
测试命令与结果
Review 结论
未验证边界
下一任务
```

## 5.4 状态变更限制

- 只有代码、测试和 review 均通过才能标记 `Done`。
- 真实数据或真实 AI 后续复核可把任务标记为 `Verified`。
- 外部服务、凭证、真机或打包环境缺失时使用 `Blocked` 或保留 `Done` 并明确更高门禁未完成，不得伪造验证。

---

# 6. 交付等级

| 等级 | 必须满足 |
| --- | --- |
| 契约冻结 | `00` 完成，文档和过期 Phase7 契约已同步 |
| Snapshot 闭环 | `01A` 至 `02B` 完成，fingerprint 和状态机通过 |
| 本地页面闭环 | `03A` 至 `05D` 完成，无真实 LLM 也可查看 facts / fallback |
| 真实 AI 代码闭环 | `06A` 至 `07C` 完成，fake LLM、缓存、并发、安全测试通过 |
| 真实 AI 验证 | 使用真实配置完成至少一次生成和一次事实更新后的刷新 |
| 产品验收 | `08A`、`08B` 完成，真实数据和视觉验收通过 |
| macOS 打包级完成 | macOS 安装产物实际构建并验证 |
| Windows 打包级完成 | Windows 安装产物实际构建并验证 |
| 跨平台完成 | macOS 与 Windows 真机核心流程均通过 |

---

# 7. 变更控制

出现以下情况时，必须暂停当前任务并先更新交付手册与本清单：

- 希望无事实变化也允许重复生成。
- 希望 Prompt / model 升级自动使历史报告 stale。
- 希望 AI 直接决定赛事、PB、成就、里程碑或代表事件事实。
- 希望前端自行拼 Snapshot、计算同比或推断年份。
- 希望把照片、轨迹点、原始 FIT 或路径交给 AI。
- 希望年度报告写回 canonical 表。
- 希望删除或替换现有全生涯 fallback。
- 希望增加用户编辑、版本管理、分享、PDF、对话或训练计划。

不改变交付手册即可处理：

- 不改变语义的内部函数拆分。
- 测试文件组织调整。
- 不改变缓存键和状态行为的性能优化。
- 不改变字段含义的局部视觉修复。

---

# 8. 最终完成定义

只有同时满足以下条件，年度 AI 总结才能标记“代码闭环完成”：

- `ACS-Year-AI-00` 至 `ACS-Year-AI-09E` 及 `ACS-Year-AI-FIX-01` 全部 `Done`。
- Year Snapshot 白名单、禁止字段、同期比较和 fingerprint 测试通过。
- 报告按年份持久化并可再次读取。
- `not_generated / ready / stale` 状态与允许操作正确。
- v2 `ready` 不重复调用 AI；同指纹 v1 只允许一次格式升级；`no_data` 不调用 AI。
- 关键事件全部通过 evidence 回填并可回跳 Activity Detail。
- 更新失败不丢失旧报告。
- 年度卡片只导航，不直接生成。
- 年度与生涯模式互不覆盖。
- 全生涯 fallback 和既有 ACS 核心能力无回归。
- API、前端、测试和文档契约一致。
- v2 报告以完整文章呈现，精确事实来自后端导语和 evidence，v1 报告继续可读。
- 生成过程具备明确状态、轮换步骤、skeleton 和 reduced-motion 兼容。

更高等级必须继续满足：

- `ACS-Year-AI-08B` 完成后，才能标记产品验收完成。
- 真实 LLM 生成和更新都验证后，才能标记真实 AI 完成。
- 对应平台安装产物实际验证后，才能标记该平台打包完成。
- macOS 和 Windows 真机均验证后，才能标记跨平台完成。
