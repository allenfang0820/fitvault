# 记录中心 V3 物化与增量计算设计审计

日期：2026-07-19

## 1. 审计结论

当前记录中心已经回到 V3 正确主链：

```text
Activity -> Record Metric Result -> Metric Series -> Current Best -> Chart
```

但当前实现仍是“请求时从 Activity 扫描并即时计算 point”的只读 MVP。它通过进程内 TTL cache 和前端 sourceVersion cache 缓解重复访问，但还没有稳定的 `career_record_metric_results` 事实表，也没有导入后按 Activity 增量计算的落点。因此：

- 现在不应继续扩 UI 或修饰 PB active/superseded 链路。
- 下一步应先实现 V3 metric result 的 schema 与 dry-run planner，确保未来落表不写错事实。
- `career_record_indexes` 可以作为 current best / period best 缓存，但必须保持“可从 metric results 重建”，不能成为事实源。
- AI 未来应读取 backend 事实层和派生 ViewModel，不读取前端缓存、不自行计算窗口/PB/best。

本轮未改业务代码、未改 UI、未写真实库、未删除 legacy 代码。

## 2. 当前代码基线

### 2.1 V3 metric series 已接入的指标族

`career_backend.py` 已定义 `RECORD_METRIC_SERIES_SUPPORTED_KEYS`，由以下集合组成：

- `RUNNING_STANDARD_DISTANCE_METRIC_SERIES_KEYS`：`running_5k`、`running_10k`、`running_half_marathon`、`running_marathon`
- `ACTIVITY_TOTAL_METRIC_SERIES_KEYS`：骑行、徒步、公开水域、越野等活动总量类记录
- `CYCLING_POWER_METRIC_SERIES_KEYS`：骑行功率时长记录
- `CYCLING_STANDARD_DISTANCE_METRIC_SERIES_KEYS`：骑行最快 10K / 20K / 40K / 50K / 100K / 180K
- `POOL_SWIM_METRIC_SERIES_KEYS`：泳池游泳标准距离记录

这些集合是 V3 物化任务的首批 Catalog 输入，应保留。

### 2.2 当前 point 生成路径

当前每个 Activity 的成绩点由以下函数即时生成：

- `_running_standard_distance_metric_result_from_activity()`
- `_running_standard_distance_metric_results_from_activity()`
- `_activity_total_metric_result_from_activity()`
- `_activity_total_metric_results_from_activity()`
- `_cycling_standard_distance_metric_result_from_activity()`
- `_cycling_standard_distance_metric_results_from_activity()`
- `_cycling_power_metric_results_from_activity()`
- `_pool_swim_metric_results_from_activity()`
- `_metric_series_point_from_resolver_result()`

这些函数已经返回接近事实层的结构：`id`、`activity_id`、`record_key`、`sport`、`event_date`、`metric`、`range`、`quality`、`scope`、`source_mode`、`resolver_version`、`rule_version`、`status`、`eligible_for_current_best`、`result_fingerprint`。

下一步应复用这些 resolver，不应重写窗口算法，也不应把算法挪到前端。

### 2.3 当前 ViewModel 派生路径

`get_career_record_metric_series()` 当前流程是：

1. 校验 `record_key` 是否在 `RECORD_METRIC_SERIES_SUPPORTED_KEYS`。
2. 通过 `_record_metric_series_activity_rows()` 从 `activities` 读取活动行。
3. 对每条 Activity 调用对应 resolver 生成 point。
4. 通过 `_record_metric_series_response_from_points()` 派生：
   - `points`
   - `current_best`
   - `record_progression`
   - `summary`
   - `axis_direction`
5. 返回 pywebview ViewModel。

`_records_v3_series_current_best_views()` 已经让左侧列表的 current best 从 metric series 派生，并通过 `_records_v3_merge_series_current_best_views()` 合并到 `get_career_records()` 的返回里。

这个方向应保留：current best 是完整成绩序列的派生结果，不是 PB active 行的反推。

### 2.4 当前缓存路径

后端：

- `_RECORD_METRIC_SERIES_CACHE`
- `RECORD_METRIC_SERIES_CACHE_TTL_SEC = 300`
- cache key 包含连接身份、activity fingerprint、record key、sport、scope、status、year、limit、resolver version。

前端：

- `track.html` 中 `careerSourceVersion`
- `loadCareerRecordsCenter()` 对 `loadedSport + loadedSourceVersion` 命中缓存
- `invalidateCareerDataCaches()` 在导入、刷新、删除等数据变化后递增 source version

这些缓存可以保留，但它们不是事实层，不能作为 AI 知识库或跨进程稳定数据源。

## 3. 当前瓶颈和风险

### 3.1 进入记录中心慢的根因

当前慢点不在 UI 绘图本身，而在 `get_career_records()` 为左侧 current best 扫描多个 sport/record definitions 时会触发 `_records_v3_series_current_best_views()`。冷缓存下，它需要读取活动行并解析：

- `points_json` / `track_json`：跑步、骑行标准距离窗口。
- `power_points` / `points_json` / `track_json`：骑行功率曲线。
- `lengths_json` / `laps_json`：泳池游泳。

右侧切换单个指标时，`get_career_record_metric_series()` 也会按该指标再次扫描 Activity。进程内缓存命中后会明显改善，但首次进入、进程重启、resolver version 变化、activity fingerprint 变化后仍会重新计算。

### 3.2 V2/PB 链路仍存在但不应作为主链

以下路径仍在代码中服务 legacy/ACS/诊断场景，应冻结，不应删除或作为 V3 chart source：

- `career_pb_records` active/superseded 主链
- `career_event_candidates`
- candidate -> active 写入状态机
- `preview_career_records()`
- V2 rebuild/materializer
- `get_career_record_history()` 两点式 PB history

风险是：如果下一步把物化结果写回 `career_pb_records` active，再由 active 反推 chart，会重新回到 V2 跑偏方向。

### 3.3 当前 schema 缺口

`ensure_career_schema()` 当前创建的业务表包括 `career_pb_records`、`career_event_candidates`、`career_record_events`、`career_record_curve_cache`、`career_ai_insights` 等，但代码中尚未创建：

- `career_record_metric_results`
- `career_record_indexes`

`docs/records_center_v3_series_02_metric_result_design.md` 已经给出这两张表的推荐 schema。下一步实现应沿用并收敛，而不是另起一套表名或字段名。

### 3.4 invalidation 缺口

`invalidate_career_record_state_for_activity()` 当前会处理：

- active PB invalidation
- fallback promote
- `career_record_curve_cache` invalidation

但尚未处理 `career_record_metric_results`。导入路径 `_sync_single_fit_file()`、批量导入 `batch_import_tracks()`、远程同步 `sync_remote_fit_activities()` 目前只会刷新已有 career derived events，不会对 metric results 做按 Activity 的增量 upsert/invalidate。

## 4. 应保留、改造、冻结、删除的边界

### 4.1 保留并复用

- Record Definition / Catalog：继续作为 `record_key`、sport、comparison、unit、scope 的源头。
- Best effort/window resolver：继续由后端生成 `range`、`quality`、`metric`。
- `build_activity_record_facts()` 和活动事实读取：继续作为 Activity -> Result 的输入边界。
- `_record_metric_series_response_from_points()`：继续集中派生 current best、progression、summary。
- 前端左右布局：左侧指标项，右侧所选指标历史成绩折线图。
- 前端 cache 与后端 TTL cache：保留为体验优化，但不作为事实源。

### 4.2 需要改造

- `ensure_career_schema()`：新增 metric results / indexes 表，但需保持幂等和 schema-ready 快速返回。
- point generator：抽出统一的 `compute_record_metric_results_for_activity()`，让 API 即时计算和落表 planner 共用同一套逻辑。
- `get_career_record_metric_series()`：优先读 materialized rows，缺失或 stale 时 fallback 到现有 resolver。
- `_records_v3_series_current_best_views()`：优先从 materialized rows 派生左侧 current best，避免冷启动扫全量活动。
- `invalidate_career_record_state_for_activity()`：增加 metric results dry-run 和真实 invalidation 分支。
- 导入/同步 hook：在 Activity insert/update 后规划 metric results 增量计算，但要先在测试库验证。

### 4.3 冻结

- `career_pb_records` active/superseded：冻结为 legacy PB archive / ACS 兼容，不参与 V3 主图。
- `career_event_candidates`：冻结为候选事件/旧流程，不参与 metric series。
- `career_record_events`：仅作为从 metric results 派生的事件标记层。
- `career_ai_insights`：当前阶段不写入、不调用 LLM。

### 4.4 暂不删除

本阶段不建议删除任何 legacy 代码。原因：

- 多个 ACS 页面、Timeline、Overview、Season、PB archive 仍可能读旧表。
- 删除前需要完成 metric results 落表、读路径切换、测试覆盖和人工验收。
- V3 主链稳定后，才能做 legacy 删除清单和迁移保护。

## 5. 推荐的最小物化模型

### 5.1 `career_record_metric_results`

事实层。每行表示一条 Activity 在一个 `record_key + scope_hash + resolver_version` 下计算出的成绩点。

建议沿用已在 `records_center_v3_series_02_metric_result_design.md` 冻结的字段：

- identity：`id`、`activity_id`、`record_key`、`sport`
- axis：`event_date`、`comparison`
- metric：`metric_name`、`metric_value_num`、`metric_unit`、`display_value`
- evidence metadata：`source_mode`、`record_family`、`scope_json`、`scope_hash`、`range_json`、`quality_json`、`eligibility_json`
- version/fingerprint：`resolver_version`、`rule_version`、`input_fingerprint`、`result_fingerprint`
- lifecycle：`status`、`created_at`、`updated_at`

唯一约束：

```sql
UNIQUE(activity_id, record_key, scope_hash, resolver_version)
```

首批 status 建议只写：

- `available`
- `invalidated`

`sample_missing` / `unsupported` 不建议首批落事实行，避免把“没算出点”的诊断状态混进 chart facts。可以在 dry-run summary 或 logs 中暴露。

### 5.2 `career_record_indexes`

缓存层。用于 current best、yearly best、monthly best、weekly best、trend summary 等可重建索引。

首个实现可先不落 `career_record_indexes`，直接从 `career_record_metric_results` 查询派生 current best。等性能瓶颈真实出现后再落 index 表。

如果实现 index 表，必须满足：

- 每行持有 `metric_result_id`。
- `source_fingerprint` 来自参与计算的 metric result 集合。
- 删除 index 不影响事实。
- index 可全量重建。

### 5.3 `career_record_events`

派生事件层。建议后续新增兼容字段：

- `metric_result_id`
- `event_type`
- `payload_json`

事件用于标记 `record_breaking`、`current_best_changed`、`metric_result_invalidated`，不能作为 chart 数据源。

## 6. 增量计算设计

### 6.1 推荐函数边界

下一步实现时建议先加以下函数，但先保持 dry-run/test DB：

```text
_ensure_career_record_metric_result_tables(conn, migrated)
compute_record_metric_results_for_activity(activity, record_keys=None, conn=None) -> dict
upsert_career_record_metric_results(conn, results, run_id="", dry_run=True) -> dict
invalidate_career_record_metric_results_for_activity(conn, activity_id, reason, dry_run=True) -> dict
_metric_result_row_to_point(row) -> dict
_metric_result_point_to_row(point, input_fingerprint) -> dict
```

`compute_record_metric_results_for_activity()` 必须只调用现有 resolver，不写 DB。这样它既能服务 dry-run，也能服务真实 import hook。

### 6.2 input fingerprint

`input_fingerprint` 应只包含安全、稳定、足够判断重算的 Activity 输入摘要，例如：

- `activity_id`
- sport / normalized sport
- event date / start time
- distance / elapsed / ascent / altitude / pool length 等 summary facts
- 相关流的 hash 和长度摘要
- resolver version / rule version

不应存 raw FIT、raw path、完整 `points_json`、`track_json`、`power_points`、`lengths_json`。

### 6.3 upsert 策略

真实写入时建议：

1. 查询同一 `activity_id + record_key + scope_hash + resolver_version` 现有行。
2. 若 `input_fingerprint` 与 `result_fingerprint` 均不变：跳过。
3. 若变化：更新 metric/range/quality/result/status。
4. 若某 Activity 之前有行、现在 resolver 不再产生该 key：标记 `invalidated`，不硬删。
5. upsert 后清理进程内 `_RECORD_METRIC_SERIES_CACHE`，并让前端通过已有 sourceVersion 机制刷新。

## 7. 导入与同步 hook

后续接入顺序建议：

1. `_sync_single_fit_file()`：在 `write_res.op in {"inserted", "updated"}` 且活动行可读取后，调用 metric result planner/upsert。
2. `batch_import_tracks()`：继续对单文件 `refresh_career=False`，但可以累计 activity_id，批量 upsert metric results，最后统一刷新 derived events。
3. `sync_remote_fit_activities()`：下载后走本地导入路径，不另开一套 metric result 计算。
4. activity 删除/更新：接入 `invalidate_career_record_metric_results_for_activity()`。

在真实库接入前，应先完成测试库验证，避免把现有用户数据库写入不可逆脏数据。

## 8. AI 知识库边界

这个物化方案适合未来 AI 沿用，因为它提供的是长期、稳定、可解释的用户运动事实：

- 每条 Activity 在各 record key 下的成绩点。
- 每个成绩点的窗口范围、质量、scope、resolver version。
- current best / record breaking 是可重建派生结果。

但 AI 只能读取后端事实/派生 ViewModel，不应：

- 调 raw FIT 或 raw activity streams。
- 从前端缓存读取。
- 自己计算 best effort window。
- 自己判定 PB/current best。
- 写 `career_ai_insights` 以外的事实表。

当前阶段仍不实现 AI，不调用 LLM，不写 `career_ai_insights`。

## 9. 下一步任务顺序

建议后续按以下顺序推进：

1. `RCV3-MATERIALIZE-02`：schema + dry-run planner。只在测试库创建表和验证 planner，不 hook 真实导入。
2. `RCV3-MATERIALIZE-03`：Activity -> metric results 纯计算批处理，覆盖当前支持的 record keys。
3. `RCV3-MATERIALIZE-04`：测试库 safe upsert / invalidate，验证幂等、stale、resolver version 变化。
4. `RCV3-MATERIALIZE-05`：`get_career_record_metric_series()` 优先读 materialized，缺失 fallback resolver。
5. `RCV3-MATERIALIZE-06`：左侧 current best 读 materialized，降低进入记录中心冷启动成本。
6. `RCV3-MATERIALIZE-07`：导入/同步 hook 和 cache invalidation。
7. `RCV3-MATERIALIZE-08`：legacy 清理审计，只列删除清单，不直接删除。
8. `RCV3-AI-CONTEXT-01`：AI context 只读 ViewModel 设计，不调用 LLM。

## 10. 下一任务提示词

```text
请在当前项目本地 main 工作区继续，不要创建新分支、不要创建 worktree。

执行 RCV3-MATERIALIZE-02 / schema + dry-run planner。

背景边界：
- V3 正确主链是 Activity -> Record Metric Result -> Metric Series -> Current Best -> Chart。
- 本任务只建立 metric result 事实层的 schema 与 dry-run planner，不接入真实导入，不改 UI，不调用 AI，不写 career_ai_insights。
- PB active/superseded、candidate/active、preview/rebuild/history 只能作为 legacy/diagnostic，不得作为 V3 chart source。
- 前端永远只消费后端 ViewModel，不在前端计算窗口、PB、best、scope、confidence、quality。

执行要求：
1. 先阅读：
   - docs/records_center_v3_materialization_design_audit.md
   - docs/records_center_v3_series_02_metric_result_design.md
   - career_backend.py 中 ensure_career_schema、metric series resolver、get_career_record_metric_series、invalidate_career_record_state_for_activity
   - main.py 中 _sync_single_fit_file、batch_import_tracks、sync_remote_fit_activities
   - 记录中心相关 tests
2. 新增或调整 schema 代码：
   - 在 ensure_career_schema 路径中幂等创建 career_record_metric_results。
   - 如创建 career_record_indexes，只能作为可重建缓存；若本轮不需要，可先不建，并在文档/测试中明确。
   - 新增必要索引，字段尽量沿用设计文档。
   - 不对真实业务数据做 backfill。
3. 新增 dry-run planner：
   - compute_record_metric_results_for_activity(activity, record_keys=None, conn=None) 只返回待写 metric result 计划，不写库。
   - 复用现有 running/cycling/hiking/open_water/trail/pool resolver。
   - 返回结果必须包含 input_fingerprint、result_fingerprint、would_upsert、would_skip、would_invalidate 等摘要。
   - 不暴露 raw FIT、raw local path、完整 points_json/track_json/power_points/lengths_json。
4. 新增测试：
   - schema 幂等创建 career_record_metric_results 和索引。
   - dry-run planner 对一条支持的 Activity 生成 metric result 计划但不写库。
   - dry-run planner 不创建/写入 career_ai_insights。
   - 输出 payload 不包含 raw stream / 本地路径。
   - 不要求真实导入 hook 生效。
5. 运行相关测试，至少覆盖新增测试与现有 records metric series 关键测试。

验收：
- 代码只完成 schema + dry-run planner，不改变记录中心 UI。
- 真实库无 backfill、无导入 hook 写入、无 AI 写入。
- 测试通过。
- 最后给出完成说明和下一个任务提示词，但不要执行下一个任务。
```
