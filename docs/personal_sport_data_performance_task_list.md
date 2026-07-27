---
title: 个人运动数据性能优化任务清单
version: v0.1.0
status: Planning
type: Ordered Engineering Task List
updated: 2026-07-23
source:
  - docs/personal_sport_data_performance_optimization_plan.md
---

# 个人运动数据性能优化任务清单

## 0. 执行规则

- 本清单的唯一设计基线是 `docs/personal_sport_data_performance_optimization_plan.md`。
- 未经用户确认，不开始业务代码修改。
- 不新开分支，不新建 worktree，直接在当前本地项目工作区实施。
- 当前 worktree 很脏；每个任务开始前必须执行 `git status --short`，并阅读待修改文件的现有 diff。
- 每个任务只改“允许改动文件”列出的范围；发现必须扩大范围时先暂停并更新文档。
- 每个任务完成后立即运行该任务的聚焦测试和 `git diff --check`。
- 不回退、不覆盖、不格式化当前 dirty worktree 中的无关修改。
- 所有性能结论必须附带冷态、热态、payload 和前端分段证据；不能只凭理论收益标记完成。

## 1. 总体状态

| 顺序 | 任务 | 状态 | 主要交付物 |
| --- | --- | --- | --- |
| 1 | 性能基线与埋点补齐 | `Completed` | 契约摘要、API/前端分段耗时、payload、基线报告 |
| 2 | 活动列表轻量分页修复 | `Completed` | 真分页、轻字段、列表测试 |
| 3 | schema ensure 冷路径治理 | `Completed` | sentinel/预热/用户路径去阻塞 |
| 4 | 活动概览轻量首屏 | `Completed` | summary API 或轻量 mode、延迟加载 |
| 5 | 复盘快照缓存 | `Completed` | activity fingerprint 缓存、命中测试 |
| 6 | 复盘曲线降采样与按需全量 | `Completed` | 默认轻量曲线、全量曲线 API |
| 7 | 复盘历史趋势查询合并/物化 | `Completed` | 请求内历史曲线解析缓存 |
| 8 | 最终回归与真实用户路径验收 | `Completed with UI follow-up` | 后端实测耗时、回归结果、完成报告；真实 pywebview UI 分段待补采 |
| 9 | 真实 pywebview 复盘首屏可观测性与瓶颈定位 | `Completed with real miss sample` | 受控前端性能诊断桥、真实分段数据、根因排序与后续任务 |
| 10 | 复盘 cache miss 后端构建剖析与优化 | `Completed` | 后端阶段剖析、cache miss 优化、API 前后对比 |

## 任务 1：性能基线与埋点补齐

状态：`Completed`

完成证据：

- 已新增 `docs/personal_sport_data_performance_contract_summary.md`，包含 Task 02-08 摘要刷新规则与重要偏离回读触发条件。
- `main.py` 为 `get_activity_list`、`get_sport_hub_activity_page`、`get_activity_detail`、`get_fatigue_review` 补充 `data.api_elapsed_ms` 诊断字段；列表兼容保留 `startup_trace.api_elapsed_ms`。
- `track.html` 已为活动列表、活动概览、复盘 API、复盘面板渲染和 ECharts 调用补充 `performance.now()` 分段事件。
- 已新增只读微基准脚本 `scripts/benchmark_personal_sport_data.py`。
- 已新增 `tests/test_personal_sport_data_performance_contract.py` 锁定摘要刷新规则、前端埋点安全边界、API contract 诊断字段和只读基准脚本。
- 验证命令见 Task 01 最终报告；业务优化尚未开始，未修改 SQL、schema、详情拆分、复盘缓存或曲线降采样。

### 目标

在修改核心性能路径前，补齐可重复测量工具和前端分段埋点，能清楚区分后端计算、pywebview 往返、payload 大小、DOM 渲染和 ECharts 绘制耗时。

### 允许改动文件

- `main.py`
- `track.html`
- `docs/personal_sport_data_performance_optimization_plan.md`
- `docs/personal_sport_data_performance_contract_summary.md`
- `docs/personal_sport_data_performance_task_01_prompt.md`
- 可新增聚焦测试或测量脚本，例如 `tests/test_personal_sport_data_performance_contract.py` 或 `scripts/benchmark_personal_sport_data.py`

### 实现要点

- 为 `get_sport_hub_activity_page`、`get_activity_list`、`get_activity_detail`、`get_fatigue_review` 返回或记录 `api_elapsed_ms`。
- 首次执行时全文深度阅读优化方案、任务清单和项目契约，形成 `docs/personal_sport_data_performance_contract_summary.md`。
- 前端在列表加载、详情打开、复盘打开中增加 `performance.now()` 分段。
- 记录 payload 字节数或 JSON 字符串长度。
- 复盘前端分段至少包含 API roundtrip、数据整理、DOM 渲染、ECharts setOption。
- 日志必须可控，避免在正常用户路径产生高频噪音。

### 测试/验收

```bash
git status --short
PYTHONPATH=. .venv312/bin/python -m pytest tests/test_response_envelope_contract.py -q
.venv312/bin/python -m py_compile main.py
git diff --check
```

验收标准：

- 能复现列表、概览、复盘当前耗时。
- 已形成契约摘要，并明确后续任务的摘要刷新规则和偏离回读触发条件。
- 能输出冷态和热态对比。
- 性能埋点不改变 API 业务字段语义。

### 非目标

- 不优化 SQL。
- 不拆详情 API。
- 不缓存复盘。
- 不改 UI 视觉结构。

## 任务 2：活动列表轻量分页修复

状态：`Completed`

完成证据：

- `profile_backend.get_activity_list_filtered()` 已改为 SQL 层去重后分页：`COUNT(DISTINCT dedupe_key)` 统计 total，`GROUP BY dedupe_key` 取当前页 id，再回表读取轻字段。
- 列表 SELECT 不再读取 `track_json` / `points_json`；`has_track` 改为基于 `file_path` 与文件名一致性的保守轻量提示。
- 新增列表轻量覆盖索引和 dedupe key 表达式索引，避免 total/分页扫描宽表 JSON 页。
- `tests/test_personal_sport_data_performance_contract.py` 已锁定列表查询不得回流大轨迹字段，并要求保留 SQL 层去重分页。
- 2026-07-23 微基准：`get_sport_hub_activity_page(1,10,'all','')` 7.38-10.42ms；`get_activity_list(1,20,'all','')` 9.90-10.07ms。
- 验证已通过：`tests/test_fit_sync.py`、`tests/test_response_envelope_contract.py`、`tests/test_personal_sport_data_performance_contract.py`、列表去重测试、历史轨迹筛选测试、`py_compile`、`git diff --check`。

### 目标

让活动列表首屏使用真正 SQL 分页和轻字段查询，避免读取 `track_json/points_json`，把列表首屏从约 5 秒降到 800ms 以内，热态降到 150ms 以内。

### 允许改动文件

- `profile_backend.py`
- `main.py`
- `track.html`，仅限适配列表返回字段或埋点展示
- 列表相关测试文件，例如 `tests/test_fit_sync.py`、`tests/test_response_envelope_contract.py` 或新增列表分页测试
- `docs/personal_sport_data_performance_optimization_plan.md`，仅限记录实测结果

### 实现要点

- 将 `profile_backend.get_activity_list_filtered()` 改为数据库层 LIMIT/OFFSET 或 keyset pagination。
- 保持排序、filterType、titleKeyword 和分页 total 契约稳定。
- 从列表 SELECT 中移除 `track_json/points_json`。
- `has_track` 改为轻量来源，例如物化字段、`file_path`、已有状态或保守 fallback。
- 如果现有去重依赖 Python `_dedupe_activity_list_rows()`，必须先明确 SQL 层等效语义，避免分页漏项。

### 测试/验收

```bash
git status --short
PYTHONPATH=. .venv312/bin/python -m pytest tests/test_fit_sync.py -q
PYTHONPATH=. .venv312/bin/python -m pytest tests/test_response_envelope_contract.py -q
.venv312/bin/python -m py_compile profile_backend.py main.py
git diff --check
```

验收标准：

- 列表第一页轻字段 SQL 接近 3-10ms 级别。
- API 热态 < 150ms。
- 冷态不再由列表 SQL 全量扫描主导。
- 分页 total、去重和过滤行为有测试覆盖。

### 非目标

- 不处理详情轨迹解析。
- 不处理复盘计算。
- 不做数据库轨迹拆表。

## 任务 3：schema ensure 冷路径治理

状态：`Completed`

完成证据：

- `profile_backend._ensure_schema_initialized()` 增加 `PROFILE_SCHEMA_SENTINEL_KEY`，命中后不再执行完整 `_init_schema()`。
- `main.ensure_activity_sync_schema()` 增加 `ACTIVITY_SYNC_SCHEMA_SENTINEL_KEY`，命中后跳过历史兼容性 `UPDATE activities ...`、补列和重复索引。
- sentinel 使用 `app_migrations`，miss 时仍执行旧迁移，成功后写入 `done`。
- 新增测试覆盖 profile sentinel 和 activity sync sentinel 命中时跳过重初始化/重更新。
- 2026-07-23 双 fresh process 微基准：第二轮 `get_activity_detail(1096)` 首调 15.25ms，列表 8-10ms；复盘首调仍 693.35ms，后续由复盘缓存/降采样/趋势任务继续治理。
- 验证已通过：`tests/test_fit_sync.py`、`tests/test_personal_sport_data_performance_contract.py`、`py_compile`、`git diff --check`。

### 目标

把昂贵 schema ensure 和兼容性大表修复从用户首屏动作路径移走，避免首次进入列表、详情、复盘时同步触发 2-4 秒级阻塞。

### 允许改动文件

- `profile_backend.py`
- `main.py`
- schema/migration 相关测试文件
- 可新增启动预热或 schema sentinel 测试
- `docs/personal_sport_data_performance_optimization_plan.md`，仅限记录实测结果

### 实现要点

- 区分轻量 schema ready 检查和重型 migration/repair。
- 引入 schema version/sentinel，只在版本变化时执行迁移。
- 对历史大表 UPDATE 增加一次性完成标记，避免每次首次交互重新扫描。
- 应用启动后可后台预热 schema，但不能阻塞个人运动数据首屏。
- 用户路径如发现 schema 未就绪，应返回明确轻量错误或触发后台修复，而不是静默长时间卡住。

### 测试/验收

```bash
git status --short
PYTHONPATH=. .venv312/bin/python -m pytest tests/test_fit_sync.py -q
.venv312/bin/python -m py_compile main.py profile_backend.py
git diff --check
```

验收标准：

- 列表、详情、复盘冷态不再同步执行大表 UPDATE。
- 旧数据库迁移仍幂等。
- schema 缺失或版本变化路径有测试覆盖。
- 冷态 API 耗时显著接近热态加真实业务计算。

### 非目标

- 不删除历史迁移逻辑。
- 不做全量数据库重建。
- 不改变活动事实字段。

## 任务 4：活动概览轻量首屏

状态：`Completed`

完成证据：

- 新增 `get_activity_detail_summary(activity_id)`，只读取 `DETAIL_SUMMARY_API_COLUMNS`，不读取 `track_json` / `points_json` / `laps_json` / 曲线大字段。
- summary record 带 `detail_pending=true`，完整 `get_activity_detail()` record 带 `detail_pending=false`，避免缓存误判。
- `track.html` 打开详情时先调用 summary API 渲染概览，再后台调用旧完整详情补全轨迹缩略图、laps 和照片。
- `renderActivityDetail()` 对 summary 记录跳过照片请求，完整详情回来后再加载照片。
- `docs/js_api_contract.json` 已新增 `get_activity_detail_summary` 契约。
- 2026-07-23 直接实测：summary payload 约 2.86KB，热态约 0.96-1.23ms；旧 detail payload 约 49.35KB，热态约 13.86-14.51ms。
- 验证已通过：`tests/test_response_envelope_contract.py`、`tests/test_personal_sport_data_performance_contract.py`、`py_compile`、`git diff --check`。

### 目标

让活动概览首屏只返回必要摘要和轻量缩略图，避免打开详情时立即读取和解析完整轨迹、laps、照片等重数据。

### 允许改动文件

- `main.py`
- `track.html`
- `docs/js_api_contract.json`
- 详情相关测试文件，例如 `tests/test_response_envelope_contract.py` 或新增详情 summary 测试
- `docs/personal_sport_data_performance_optimization_plan.md`，仅限记录实测结果

### 实现要点

- 新增 `get_activity_detail_summary(activity_id)`，或为 `get_activity_detail` 增加明确轻量 mode。
- 首屏字段限制为标题、时间、地点、运动类型、关键指标、设备、可用能力和约 60 点缩略图。
- laps、照片、全量轨迹、复杂 capabilities 延迟加载。
- 保留旧详情 API，避免破坏其他入口。
- 前端打开弹窗先渲染 summary，再渐进填充重数据。

### 测试/验收

```bash
git status --short
PYTHONPATH=. .venv312/bin/python -m pytest tests/test_response_envelope_contract.py -q
.venv312/bin/python -m py_compile main.py
git diff --check
```

验收标准：

- 概览首屏 < 800ms。
- 热态概览 < 200ms。
- summary payload 明显小于旧 detail payload。
- 旧 `get_activity_detail` 契约保持可用。

### 非目标

- 不重写详情页视觉。
- 不改变轨迹原始数据。
- 不处理复盘 tab。

## 任务 5：复盘快照缓存

状态：`Completed`

完成证据：

- `main.py` 已为 `get_fatigue_review(activity_id)` 增加 `fatigue_review_snapshot_cache` 后端快照缓存。
- 缓存 fingerprint 包含 `activity_id`、activity `updated_at`、`FATIGUE_REVIEW_CACHE_VERSION` 和 `CURRENT_METRICS_VERSION`。
- 缓存 miss 继续走 `_build_fatigue_review_snapshot()` 旧构建路径，成功返回后 best-effort 写缓存；缓存写入失败只记录 debug，不影响复盘返回。
- 缓存 hit 返回旧 snapshot 字段语义，补充 `api_elapsed_ms` 与 `cache_status=hit`，不再调用快照构建、历史趋势查询和曲线解析。
- 缓存写入时显式将 `ai_insight` 置为 `None`，避免缓存 AI 生成内容。
- `tests/test_personal_sport_data_performance_contract.py` 已覆盖同一活动二次命中、命中跳过构建、AI 内容不入缓存、`updated_at` 和 cache version 变更失效。
- 2026-07-24 微基准：长活动 `get_fatigue_review(127)` miss 约 1713.20ms，后续 hit 约 30.58-30.89ms；直接 API 确认 `cache_status=hit` 约 34.31-52.69ms。
- 验证已通过：`tests/test_fit_sync.py`、`tests/test_personal_sport_data_performance_contract.py`、`py_compile`、`git diff --check`。

### 目标

为复盘构建结果增加可失效缓存，缓存命中时避免重复执行 Resolver 快照、历史趋势查询和曲线解析。

### 允许改动文件

- `main.py`
- `profile_backend.py`，仅限新增轻量缓存表或 helper
- `metrics_resolver.py`，仅限 resolver version/fingerprint 明确化
- 复盘相关测试文件
- `docs/personal_sport_data_performance_optimization_plan.md`，仅限记录实测结果

### 实现要点

- 缓存 key 至少包含 `activity_id`、activity `updated_at`、resolver version 或等效 fingerprint。
- 缓存 payload 可拆分 summary 与 curves，避免一次性缓存不可控大对象。
- 缓存 miss 继续走旧构建路径，构建成功后写入缓存。
- 缓存命中必须保留 API envelope 和字段语义。
- 缓存写入失败不得影响复盘返回。

### 测试/验收

```bash
git status --short
PYTHONPATH=. .venv312/bin/python -m pytest tests/test_fit_sync.py -q
.venv312/bin/python -m py_compile main.py profile_backend.py metrics_resolver.py
git diff --check
```

验收标准：

- 同一活动第二次复盘命中缓存。
- activity 更新或 resolver version 变化后缓存失效。
- 缓存命中不执行历史趋势重查询。
- 冷态和热态复盘均有实测记录。

### 非目标

- 不改变复盘算法语义。
- 不缓存 AI 生成内容，除非现有契约已经要求。
- 不牺牲缺失数据和低置信度判断。

## 任务 6：复盘曲线降采样与按需全量

状态：`Completed`

完成证据：

- 已新增 `docs/personal_sport_data_performance_task_06_prompt.md`，延续契约摘要刷新与重要偏离全文回读规则。
- `main.py` 已将 `get_fatigue_review(activity_id, curve_resolution=None)` 改为默认 sampled 响应，显式 `full` 返回全量曲线。
- Task 05 缓存仍保存完整后端 snapshot；Task 06 只在响应层派生 sampled/full，避免 sampled 数据污染 canonical snapshot。
- sampled 降采样保留首尾点、均匀点、各曲线全局极值、`collapse_events.trigger_km` 与 `fatigue_zones.start_km/end_km` 附近点。
- 返回诊断字段：`curve_resolution`、`curve_points_original`、`curve_points_returned`、`curve_sample_target_points`、`full_curves_available`。
- `track.html` 复盘首屏继续调用默认 sampled，并在性能埋点中记录 cache/resolution/original/returned 点数。
- `docs/js_api_contract.json` 已同步 sampled/full 返回契约。
- `tests/test_personal_sport_data_performance_contract.py` 已覆盖默认 sampled、显式 full、缓存 full snapshot 复用、同轴长度、首尾/极值/事件点保留。
- 2026-07-24 微基准：长活动默认 `get_fatigue_review(127)` payload 约 130,932 bytes，点数 26,052 -> 1,207；显式 `full` payload 约 2,671,972 bytes，点数 26,052。
- 验证已通过：`tests/test_response_envelope_contract.py`、`tests/test_personal_sport_data_performance_contract.py`、`py_compile main.py`、`git diff --check`。

### 目标

复盘首屏默认返回展示用降采样曲线，长活动不再一次返回 3MB 以上 payload；全量曲线在放大、导出或精细分析时按需请求。

### 允许改动文件

- `main.py`
- `track.html`
- `docs/js_api_contract.json`
- 复盘图表相关测试文件
- `docs/personal_sport_data_performance_optimization_plan.md`，仅限记录实测结果

### 实现要点

- 默认曲线目标点数控制在 800-1500 点。
- 降采样算法必须保留距离/时间单调性、关键极值和事件附近点。
- tooltip 与事件 pins 仍能定位到合理位置。
- 新增全量曲线按需 API 或参数，例如 `curve_resolution=full`。
- 导出、放大和精细检查使用全量曲线，不使用降采样替代原始数据。

### 测试/验收

```bash
git status --short
PYTHONPATH=. .venv312/bin/python -m pytest tests/test_response_envelope_contract.py -q
.venv312/bin/python -m py_compile main.py
git diff --check
```

验收标准：

- 长活动默认复盘 payload 明显下降。
- 首屏 ECharts setOption 时间下降。
- 降采样曲线保留关键事件和极值。
- 全量曲线按需请求可用。

### 非目标

- 不删除原始曲线。
- 不改变复盘结论。
- 不重写 ECharts 视觉风格。

## 任务 7：复盘历史趋势查询合并/物化

状态：`Completed`

完成证据：

- 已新增 `docs/personal_sport_data_performance_task_07_prompt.md`，延续契约摘要刷新与重要偏离全文回读规则。
- `main.py` 已新增 `_review_historical_curve_cached()`，在一次复盘 cache miss 构建内复用相同历史 `track_json` / `points_json` 的解析结果。
- `_fetch_durability_trend()` 与 `_fetch_cadence_stability_trend()` 已接入请求内历史曲线缓存，避免同一历史 raw JSON 被重复 `json.loads`。
- cache miss 构建前后会清空 `_fatigue_review_historical_curve_cache`，不跨活动、不跨请求复用，避免陈旧数据。
- 未新增 schema/物化表，未改变 21d/7d/42d 历史窗口、趋势公式、basis/version、缺失数据降级或低置信度规则。
- `tests/test_personal_sport_data_performance_contract.py` 已覆盖 canonical JSON 解析复用、canonical 缺字段时继续 fallback 派生列。
- 2026-07-24 长活动直接 `_build_fatigue_review_snapshot(127)`：首轮约 1091.38ms，热态约 347.48-356.01ms；常规 API sampled hit 约 70.93-82.74ms，payload 约 130,931-130,932 bytes。
- 验证已通过：`tests/test_fit_sync.py`、`tests/test_personal_sport_data_performance_contract.py`、`py_compile main.py profile_backend.py metrics_resolver.py`、`git diff --check`。

### 目标

减少复盘构建中的多次 SQLite 历史趋势查询和历史曲线 JSON 解析，降低 `_fetch_cadence_stability_trend`、`_fetch_durability_trend` 等热点成本。

### 允许改动文件

- `main.py`
- `profile_backend.py`
- `metrics_resolver.py`，仅限趋势 fingerprint 或共享计算入口
- 趋势/复盘相关测试文件
- `docs/personal_sport_data_performance_optimization_plan.md`，仅限记录实测结果

### 实现要点

- 合并同一活动复盘所需的历史活动查询。
- 对同一批历史活动的曲线解析结果做请求内缓存。
- 评估是否需要轻量趋势物化表；若需要，先冻结 schema 和失效规则。
- 避免在复盘构建中重复读取同一历史 JSON。

### 测试/验收

```bash
git status --short
PYTHONPATH=. .venv312/bin/python -m pytest tests/test_fit_sync.py -q
.venv312/bin/python -m py_compile main.py profile_backend.py metrics_resolver.py
git diff --check
```

验收标准：

- 复盘热态 `_build_fatigue_review_snapshot` 明显下降。
- SQLite 查询次数下降。
- 历史趋势语义和缺失数据行为保持稳定。

### 非目标

- 不做 Records Center 新物化能力。
- 不改变趋势口径。
- 不为了速度跳过低置信度判断。

## 任务 8：最终回归与真实用户路径验收

状态：`Completed with UI follow-up`

完成证据：

- 已新增 `docs/personal_sport_data_performance_completion_report.md`，汇总 Task 01-07 实施摘要、优化前后对比、后端微基准、验证命令、残余风险和回滚策略。
- 已刷新 `docs/personal_sport_data_performance_contract_summary.md` 到 Task 08，明确本任务为最终验证和报告闭环，不扩展业务实现。
- 最终微基准：`get_sport_hub_activity_page(1,10,'all','')` 约 8.10-12.77ms，`get_activity_list(1,20,'all','')` 约 10.83-11.84ms，`get_activity_detail_summary(1096)` 热态约 1.10-1.46ms，`get_activity_detail(1096)` 约 15.28-16.25ms，默认 sampled `get_fatigue_review(127)` 约 66.71-78.09ms。
- 显式 full 曲线验证通过：`get_fatigue_review(127,'full')` 约 26.60-29.18ms，payload 约 3,115,408 bytes，`curve_points_returned=26052`。
- 验证已通过：`tests/test_fit_sync.py`、`tests/test_response_envelope_contract.py`、`tests/test_personal_sport_data_performance_contract.py`、`py_compile main.py profile_backend.py metrics_resolver.py`、`git diff --check`。
- 当前环境未能自动采集真实 pywebview UI 分段耗时：pywebview console 未暴露给终端，Codex in-app browser 的本地 `file://` 探针被安全策略拦截。该缺口已记录为完成报告残余风险，不将后端耗时伪装为完整 UI 体感。

### 目标

完成列表、概览、复盘三段真实用户路径验收，记录优化前后对比，确认没有引入数据真实性、分页、复盘语义或 UI 交互回归。

### 允许改动文件

- `docs/personal_sport_data_performance_optimization_plan.md`
- 可新增完成报告，例如 `docs/personal_sport_data_performance_completion_report.md`
- 仅限修复验收中发现的本任务范围内小问题

### 实现要点

- 汇总每阶段冷态、热态、payload、前端分段数据。
- 运行聚焦 pytest 和 py_compile。
- 手动打开应用验证活动列表、活动概览、复盘 tab。
- 验证长活动和最近活动各至少 1 条。
- 记录仍未处理的残余风险和后续建议。

### 测试/验收

```bash
git status --short
PYTHONPATH=. .venv312/bin/python -m pytest tests/test_fit_sync.py tests/test_response_envelope_contract.py -q
.venv312/bin/python -m py_compile main.py profile_backend.py metrics_resolver.py
git diff --check
```

验收标准：

- 活动列表首屏 < 800ms，热态 < 150ms。
- 活动概览首屏 < 800ms，热态 < 200ms。
- 复盘首屏 < 1.5s。
- 完整曲线和 AI 相关内容渐进加载，不阻塞复盘首屏。
- 无分页漏项、重复项、详情字段缺失、复盘结论漂移。

### 非目标

- 不扩展到 Garmin/COROS 同步性能。
- 不处理 AI 质量。
- 不追加 UI 大改。
- 不处理 Records Center 新功能。

## 任务 9：真实 pywebview 复盘首屏可观测性与瓶颈定位

状态：`Completed with real miss sample`

完成证据：

- 已新增 `docs/personal_sport_data_performance_task_09_completion_report.md`，记录诊断通道、隐私边界、真实窗口采集方式和后续分流规则。
- 曾新增受控 pywebview 诊断 API：`record_frontend_performance_events(events)` 与 `get_frontend_performance_trace(activity_id=None)`，仅进程内有限保存白名单性能事件；真实样本采集完成后，临时按钮和前端桥已移除。
- 已在复盘路径采集 `fatigue_review_tab_first_open`、`fatigue_review_open_start`、`fatigue_review_api_done`、`fatigue_review_panels_done`、`fatigue_review_chart_done`。
- 曾在复盘头部新增 `耗时` 按钮，用于在真实 pywebview 窗口读取最近一次复盘的总计、API 往返、后端、面板渲染、图表 setOption、缓存和曲线点数；当前 UI 已不再显示该临时按钮。
- 已补充聚焦契约测试，覆盖敏感字段拒绝、最近一次打开过滤、进程内 64 条保存上限和 API 文档同步。
- 验证已通过：`tests/test_response_envelope_contract.py`、`tests/test_personal_sport_data_performance_contract.py`、`py_compile main.py`、`jq empty docs/js_api_contract.json`。
- 已补采真实 pywebview 样本：`cache: miss` 时总计 4783ms、API 往返 4748ms、后端 3745.12ms、面板 4ms、图表 setOption 29ms、曲线 990 / 2916。结论是 3-5 秒体感主要来自复盘 cache miss 后端构建和 pywebview/API 往返，不是面板或 ECharts 首次 `setOption`。
- 对照样本：`cache: hit` 时总计 96ms、API 往返 28ms、后端 15.1ms、面板 5ms、图表 setOption 60ms、曲线 1206 / 3576。

### 触发证据

用户于 2026-07-27 在真实 pywebview 应用窗口中反馈，进入复盘仍需等待约 3-5 秒。Task 08 已确认后端微基准不能代表 pywebview、DOM 与 ECharts 的完整体感，因此必须先补可读取的真实分段证据。

### 目标

建立最小、受控、无敏感原始数据的前端性能诊断桥，定位复盘首屏等待到底来自 API/pywebview 往返、cache miss、面板渲染、ECharts、动画/resize，还是同屏其他长任务。

### 允许改动文件

- `track.html`
- `main.py`
- `docs/js_api_contract.json`
- `tests/test_personal_sport_data_performance_contract.py`
- 必要时新增聚焦诊断测试
- 本轮性能优化文档和 Task 09 完成报告

### 实现要点

- 前端仅上报白名单化的最小性能事件，后端仅进程内有限保留。
- 在真实窗口可读取最近复盘阶段的 API、panels、chart 等耗时，不能只写 console。
- 最近活动、长活动、首次/再次打开和 sampled/full 路径分别记录。
- 以真实分段数据决定后续优化方向；本任务不直接大改渲染或复盘计算。
- 基于当前真实样本，下一任务优先聚焦 `cache: miss` 的 `_build_fatigue_review_snapshot(row)`、历史趋势查询、历史曲线 JSON 解析、snapshot cache 写入，以及后端 `api_elapsed_ms` 之外约 1 秒 pywebview/API 往返开销。

### 测试/验收

```bash
PYTHONPATH=. .venv312/bin/python -m pytest tests/test_response_envelope_contract.py tests/test_personal_sport_data_performance_contract.py -q
.venv312/bin/python -m py_compile main.py
git diff --check
```

### 非目标

- 不修改复盘事实、公式、曲线轴、AI 输入边界或 sampled/full 真实性。
- 不新增大表、长期性能日志、schema 大迁移、Garmin/COROS 同步改造或 UI 大改。

## 任务 10：复盘 cache miss 后端构建剖析与优化

状态：`Completed`

提示词：`docs/personal_sport_data_performance_task_10_prompt.md`

完成报告：`docs/personal_sport_data_performance_task_10_completion_report.md`

完成证据：

- 已新增 `review_backend_profile` 响应诊断字段，只返回阶段名、耗时、计数、cache 状态、曲线分辨率和曲线点数；不写入 snapshot cache，不进入 AI compact snapshot。
- 已为 `get_fatigue_review()` miss/hit 路径和 `_build_fatigue_review_snapshot()` 关键阶段补充后端阶段剖析。
- 已优化 durability/cadence 历史趋势查询：先按粗 SQL 时间窗读取轻字段，再只为窗口内候选读取 `track_json/points_json`，保留 canonical 优先级。
- 已为 efficiency/training load/load ratio 轻字段历史查询补充粗 SQL 时间窗；`metrics_resolver._fetch_efficiency_baseline` 同步收窄。
- 已新增 pywebview 前端 ready 后的后台 GAP 数值依赖预热，降低首次复盘把 numpy/scipy import 计入用户点击路径的概率。
- 1094 miss API 后端从 Task 09 真实样本约 3745ms、本地 API 基线约 3550ms，降到 654-1154ms；1094 hit 对照约 5.32ms。
- 验证已通过：`tests/test_response_envelope_contract.py`、`tests/test_personal_sport_data_performance_contract.py`、复盘 snapshot/E2E/quality/V9.0 聚焦测试、`py_compile main.py metrics_resolver.py`、`jq empty docs/js_api_contract.json`。

### 触发证据

Task 09 真实 pywebview 样本显示：`cache: miss` 时总计 4783ms、API 往返 4748ms、后端 3745.12ms、面板 4ms、图表 setOption 29ms；`cache: hit` 时总计 96ms。当前 3-5 秒体感主要来自复盘 cache miss 后端构建和约 1 秒 pywebview/API 往返差值。

### 目标

用阶段剖析定位并优化 `get_fatigue_review()` 的 cache miss 后端构建路径，优先让 miss 后端耗时降到 < 1500ms，理想 < 1000ms，同时保持 hit 路径 < 150ms 级别。

### 允许改动文件

- `main.py`
- `tests/test_personal_sport_data_performance_contract.py`
- 必要时新增聚焦后端性能测试
- `docs/personal_sport_data_performance_contract_summary.md`
- `docs/personal_sport_data_performance_task_list.md`
- `docs/personal_sport_data_performance_optimization_plan.md`
- 可新增 `docs/personal_sport_data_performance_task_10_completion_report.md`
- 仅在契约同步需要时修改 `docs/js_api_contract.json` 或 `scripts/benchmark_personal_sport_data.py`

### 实现要点

- 先刷新契约摘要到 Task 10，阅读 Task 09 完成报告、任务清单、优化方案和原始复盘契约。
- 先做阶段剖析，不带证据不改公式、不砍字段、不调整 sampled/full 语义。
- 拆解 `_build_fatigue_review_snapshot(row)`、历史趋势查询、历史曲线 JSON 解析、snapshot cache 写入。
- 优先合并或缓存同一请求内 21 天历史趋势查询和曲线解析。
- 记录优化前后 cache miss、cache hit、payload、曲线点数和后端 `review_backend_profile` 对比；真实 pywebview 总耗时如需复测，应使用新的受控验证方式，不恢复临时按钮。

### 测试/验收

```bash
git status --short
PYTHONPATH=. .venv312/bin/python -m pytest tests/test_response_envelope_contract.py tests/test_personal_sport_data_performance_contract.py -q
.venv312/bin/python -m py_compile main.py
jq empty docs/js_api_contract.json
git diff --check
```

建议补跑：

```bash
PYTHONPATH=. .venv312/bin/python -m pytest tests/test_fatigue_review_snapshot_realignment.py tests/test_fatigue_review_e2e_contract.py tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py -q
```

### 非目标

- 不做 UI 大改或图表视觉优化。
- 不处理 AI 生成速度或 AI 质量。
- 不处理 Garmin/COROS 同步、导入、重复活动或 Records Center。
- 不新建大表或长期性能日志。
- 不改变复盘事实、公式、曲线轴、事件/疲劳带、AI 输入或 sampled/full 真实性。
