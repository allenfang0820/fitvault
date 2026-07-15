---
title: ACS 年度 AI 总结切换性能修复任务清单与工程提示词
version: v0.1.0
status: Completed
type: Ordered Performance Fix Task List
updated: 2026-07-15
source:
  - docs/acs_next_annual_ai_summary_delivery_manual.md
  - docs/acs_next_annual_ai_summary_execution_log.md
  - 2026-07-15 真实库性能剖析
---

# ACS 年度 AI 总结切换性能修复任务清单与工程提示词

> 2026-07-15 后续产品决策：独立“生涯总结”模式及其公开 API 已退役。本文中关于生涯模式懒加载、跨模式切换和 `generate_career_insight` 的内容仅作为当时性能修复记录，不再是现行产品契约。

## 0. 真实基线

真实数据库：`/Users/fanglei/.fitvault/user_profile.db`。

- 数据库约 1.4 GB。
- `activities` 表约 1.482 GB，共 981 条活动。
- 单条 Activity 的 `points_json + track_json` 平均约 1.5 MB。
- 可用年份 9 个，已有 ready 年度报告 6 个。
- 单次 `get_career_year_insight(year)` 约 4.0-5.6 秒。
- `_career_year_update_badges()` 约 3.3 秒。
- 单个 `build_career_year_snapshot(year)` 约 0.5-0.7 秒。
- 单次年度读取约执行 2822 条 SQL：1451 SELECT、832 PRAGMA、473 CREATE、44 UPDATE。
- 已复现 `sqlite3.OperationalError: database is locked`。
- `career_snapshots` 真实库当前为 0 行，全生涯 Snapshot 未形成有效持久化命中。

## 1. 滚动项目契约摘要

- `Activity` 是唯一事实源；Race、PB、Achievement、Milestone 语义只来自 Resolver。
- 年度报告状态与刷新资格只由白名单 Year Snapshot 和 `source_fingerprint` 决定。
- 性能优化不得改变 Snapshot 字段、fingerprint 语义、年度报告状态、AI Prompt、模型来源或 evidence 校验规则。
- 年度 NEW 徽标必须保持准确，但不得在每次单年份读取时重复扫描宽 Activity 表。
- 前端不得自行推断年度事实或报告是否 stale。
- 旧报告、AI 缓存和 canonical 事实表不得因性能优化被删除、覆盖或重建。
- 当前工作区有大量未提交改动；不得回退、覆盖或格式化无关文件。
- 每个任务开始前刷新本摘要；只有改动文件、失败测试或 review 风险需要时才回读原始交付手册。

---

## 任务 1：年度只读热路径与全表扫描收敛

状态：`Completed`

完成证据：

- `get_career_year_insight(2026)` 复用同一份请求级 Activity 安全行。
- 确定性测试锁定单次 API 调用 `_overview_activity_rows()` 恰好调用 1 次。
- `_overview_activity_rows()` 的 `PRAGMA table_info(activities)` 收敛为 1 次。
- 34 个定向测试通过；`py_compile` 与 `git diff --check` 通过。
- 真实库只读热读约 0.38-0.47 秒，单次 1 个 Activity read、97 条 SQL、1 条 PRAGMA。
- 冷读约 4.6 秒，残余成本来自 1.4 GB 宽表的一次冷扫描，未在本任务引入跨请求缓存掩盖数据更新。

### 工程级执行提示词

#### Goal

把年度年份切换的后端读取从“为所有 ready 年份重复构建 Snapshot 并多次扫描宽 Activity 表”改为“单请求只读取一次 Activity 安全字段并复用”，保持所有年度 NEW 徽标、Snapshot、fingerprint、同期比较和报告状态语义不变。

#### Scope

- 优化 `get_career_year_insight()`、年度 update badges、Year Snapshot Activity 读取和列元数据检查。
- 允许增加内部 request-scoped read context、预加载 Activity rows、按年份分桶或等价局部抽象。
- 允许给内部函数增加可选预加载参数，但不得改变公开 API payload 或返回结构。
- 增加确定性的调用次数 / SQL 元数据检查回归测试和真实库只读 benchmark 脚本或测试辅助。

#### Constraints

- 开始前刷新滚动项目契约摘要。
- 不修改 AI Prompt、报告 schema、LLM 调用、报告缓存写入和状态语义。
- 不用简单删除 `year_update_badges` 换取速度；徽标结果必须继续准确。
- 不把 raw FIT、points、track_json 或媒体字段读入新的缓存结构。
- 不引入跨请求长期缓存，避免活动更新后返回陈旧 fingerprint；本任务优先使用请求级复用。
- 不依赖脆弱的毫秒断言作为唯一测试，必须锁住全量 Activity 读取次数和结果等价性。

#### Expected Files Or Areas

- `career_backend.py`
- `tests/test_career_year_insight_service.py`
- `tests/test_career_year_snapshot_activity_aggregation.py`
- `tests/test_career_year_snapshot_period_comparison.py`
- 新增年度性能契约测试文件（如确有必要）
- 本任务清单与独立完成报告

#### Validation

```bash
.venv312/bin/python -m pytest tests/test_career_year_insight_service.py tests/test_career_year_snapshot_activity_aggregation.py tests/test_career_year_snapshot_period_comparison.py tests/test_career_year_snapshot_fingerprint.py tests/test_career_seasons_api.py -q
.venv312/bin/python -m py_compile career_backend.py
git diff --check -- career_backend.py tests/test_career_year*.py tests/test_career_seasons_api.py docs/acs_year_ai_performance_fix_task_list.md
```

真实库只读验收：

- 单次 `get_career_year_insight(2026)` 的 `_overview_activity_rows` 调用次数应从约 15 次降到 1 次。
- 单次年度读取 SQL 数量必须显著下降，不再出现数百次重复 `PRAGMA table_info(activities)`。
- 在应用运行时使用只读连接复测，不调用 LLM、不修改真实报告。

#### Completion Definition

- 年度读取、NEW 徽标、fingerprint、同期比较结果与优化前一致。
- 单请求 Activity 安全行只读取一次并被所有年份计算复用。
- 列存在性检查不再对每个字段单独重复执行 `PRAGMA table_info`。
- 定向测试全绿，真实库年度读取达到可交互量级，adaptive diff review 无阻塞问题。

---

## 任务 2：Schema Ensure、事务提交与 SQLite 锁竞争修复

状态：`Completed`

完成证据：

- 当前 schema 版本且 11 张必需 ACS 表完整时，`ensure_career_schema()` 只执行只读完整性检查。
- 缺表、旧版本和 migration 失败回滚路径继续执行完整迁移。
- `generate_career_insight()` 自有连接会提交内部 Snapshot 写入，外部连接仍由调用方管理事务。
- 59 个测试和 3 个子测试通过；`py_compile` 与 `git diff --check` 通过。
- 真实库 query-only 年度读取共 119 条 SQL，CREATE / ALTER / INSERT / UPDATE / DELETE / SAVEPOINT 均为 0。

### 工程级执行提示词

#### Goal

让 Career 只读 API 在 schema 已是当前版本时保持真正只读，避免嵌套仓储函数反复执行 DDL、backfill 和 UPDATE；修复全生涯 Snapshot 在外层连接中写入后未提交的问题，降低并发加载时的 SQLite 锁竞争。

#### Scope

- 优化 `ensure_career_schema()` 当前版本快速返回路径。
- 保证实际迁移、缺表或版本变化时仍完整执行 migration。
- 修复 `generate_career_insight()` / `save_career_snapshot()` 的事务所有权和提交边界。
- 检查年度只读和缓存仓储调用中的嵌套 schema ensure，避免重复迁移。
- 增加 schema 幂等、只读无 UPDATE、外层连接持久化和锁竞争回归测试。

#### Constraints

- 开始前刷新滚动项目契约摘要，并回读 schema / persistence 相关原文与测试。
- 不跳过真实 schema migration；只能在确认 `career_schema_meta.schema_version` 为当前版本时走快速路径。
- 不使用全局连接 id 缓存等可能受连接复用影响的不安全方案。
- 不改变 canonical 表字段、年度 AI 缓存唯一约束或 Snapshot 内容。
- 所有写事务必须明确 commit/rollback 所有权；只读路径不得隐式 UPDATE。
- 不大规模替换整个项目数据库连接层，除非测试证明局部修复无法成立。

#### Expected Files Or Areas

- `career_backend.py`
- `tests/test_career_snapshot_persistence.py`
- `tests/test_career_year_snapshot_persistence.py`
- `tests/test_career_ai_insights_repository.py`
- 新增 schema 热路径 / 事务测试文件（如确有必要）
- 本任务清单与独立完成报告

#### Validation

```bash
.venv312/bin/python -m pytest tests/test_career_snapshot_persistence.py tests/test_career_year_snapshot_persistence.py tests/test_career_ai_insights_repository.py tests/test_career_year_insight_service.py tests/test_career_phase9_pywebview_envelope.py -q
.venv312/bin/python -m py_compile career_backend.py main.py
git diff --check -- career_backend.py main.py tests/test_career_snapshot_persistence.py tests/test_career_year_snapshot_persistence.py tests/test_career_ai_insights_repository.py
```

附加门禁：

- 当前 schema 版本下重复 ensure 不执行 migration backfill UPDATE。
- `main.Api().generate_career_insight()` 在临时真实文件 DB 中调用后，重新连接仍能读到 `career_snapshot:latest`。
- 并发只读年度请求不因 schema ensure 产生 `database is locked`。

#### Completion Definition

- schema 当前版本走轻量只读快速路径。
- 缺表、旧版本和迁移失败 rollback 测试继续通过。
- 全生涯 Snapshot 能跨连接持久化读取。
- 年度只读请求不再包含数百条 CREATE / UPDATE。
- 定向测试与 full diff review 通过，无数据迁移或事务回归。

---

## 任务 3：前端按年份缓存与 AI 页面按需加载

状态：`Completed`

完成证据：

- 增加 `yearInsightByYear` 与 `yearInsightNeedsRefresh`，有效年份缓存可即时回切。
- 后端 NEW / stale 信号和活动事实更新均会标记对应缓存需要刷新。
- 增加单调 `careerSourceVersion`，防止进行中的旧请求覆盖事实更新失效信号。
- `loadCareerData()` 增加 loaded / loadingPromise / needsRefresh 门禁，不再预加载全生涯 Snapshot。
- Overview 与 Seasons 改为错峰加载，避免同时触发年度报告更新计算。
- 活动同步、导入、删除、标题更新、赛事标记和新活动检测均接入缓存失效。
- 50 个前端契约测试通过；3 个内联脚本通过 Node 语法解析；`git diff --check` 通过。

### 工程级执行提示词

#### Goal

让已经读取过且未被标记更新的年份在前端即时切换；避免进入运动生涯时无条件预加载全生涯 Snapshot，并阻止 Overview、Seasons、年度报告在同一时刻重复触发重型年度计算。

#### Scope

- 增加按年份的年度 ViewModel 缓存，例如 `yearInsightByYear`。
- 年份回切时：缓存有效且没有后端 NEW / stale 信号则直接渲染；有更新信号或显式 force 时重新请求。
- 数据同步、赛事标记、活动编辑/删除等已知事实变化路径必须使相关缓存失效或标记需刷新。
- 从 `loadCareerData()` 移除无条件全生涯 Insight 预加载；只在 AI 总结页切到生涯模式时加载。
- 避免重复进入 Career 主 Tab 时无条件执行同一批加载；使用明确的 loaded / needsRefresh 状态，不屏蔽真实数据更新。
- 保留 request token、晚到响应隔离和生成中的旧报告保护。

#### Constraints

- 开始前刷新滚动项目契约摘要，并回读前端状态隔离测试。
- 前端缓存只缓存后端 ViewModel，不计算 Snapshot、fingerprint 或 stale 状态。
- 年度卡片仍只导航，不调用 LLM。
- 不破坏当前 v1/v2/v3 年度报告兼容渲染。
- 不用无限期缓存掩盖活动更新；`needsRefresh` 必须有消费和清理规则。
- 不修改无关页面布局或视觉主题。

#### Expected Files Or Areas

- `track.html`
- `tests/test_career_year_insight_mode_frontend.py`
- `tests/test_career_year_request_isolation_frontend.py`
- `tests/test_career_year_card_navigation_frontend.py`
- `tests/test_career_gap_p1_11_frontend_data_linkage.py`
- `tests/test_track_html_sync_logic.py`
- 本任务清单与独立完成报告

#### Validation

```bash
.venv312/bin/python -m pytest tests/test_career_year_insight_mode_frontend.py tests/test_career_year_request_isolation_frontend.py tests/test_career_year_card_navigation_frontend.py tests/test_career_gap_p1_11_frontend_data_linkage.py tests/test_track_html_sync_logic.py -q
git diff --check -- track.html tests/test_career_year*.py tests/test_career_gap_p1_11_frontend_data_linkage.py
```

前端行为验收：

- `2026 -> 2025 -> 2026` 第二次进入 2026 不再调用后端，除非 2026 被标记 NEW / stale 或缓存已失效。
- `年度总结 -> 生涯总结 -> 年度总结` 在两侧均已加载时只切换渲染。
- 首次进入运动生涯不再无条件构建全生涯 Snapshot。
- 已知事实更新后重新进入年度页会请求最新后端状态。

#### Completion Definition

- 年份和模式回切使用有效缓存即时渲染。
- 数据更新后缓存能够正确失效。
- AI 相关 API 改为页面按需加载。
- 晚到响应、生成状态和错误态测试继续通过。
- 定向测试、静态契约和 adaptive diff review 通过。

---

## 4. 最终累计门禁

三个任务完成后执行：

```bash
.venv312/bin/python -m pytest $(rg --files tests | rg 'career_year|career_snapshot|career_insight|career_seasons|track_html_sync') -q
.venv312/bin/python -m pytest $(rg --files tests | rg '^tests/test_.*career.*\.py$') -q
.venv312/bin/python -m py_compile career_backend.py main.py llm_backend.py
.venv312/bin/python -m json.tool docs/js_api_contract.json >/dev/null
git diff --check
```

最终 review 必须检查：

- 未改变年度 Snapshot、fingerprint 和报告状态语义。
- 未恢复旧 MemoryItem 或敏感字段。
- 未让前端承担事实判断。
- 未丢失历史报告。
- 未引入新的 SQLite 写锁或未提交事务。
- 真实库年度读取性能有前后对比证据。

## 5. 最终结果

- 年度/快照/生涯洞察/Seasons/同步矩阵：195 passed，10 subtests passed。
- 全部 Career 测试：751 passed，57 subtests passed。
- `career_backend.py`、`main.py`、`llm_backend.py` 编译通过。
- `docs/js_api_contract.json` JSON 校验通过。
- `track.html` 3 个内联脚本通过 Node 语法解析。
- 全工作区 `git diff --check` 通过。
- 真实库年度读取：每次 1 个 Activity read、119 条只读 SQL、0 条写 SQL；热读约 0.29-0.40 秒。
- 真实库冷读仍约 5.0 秒，来自 1.4 GB 宽 Activity 表首次磁盘扫描。实际进入 Career 后 Overview 已预热 Activity 数据页，随后年度切换由后端热读和前端年份缓存共同收敛。
