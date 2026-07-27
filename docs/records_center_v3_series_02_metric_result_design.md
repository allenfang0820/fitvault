# Records Center V3 SERIES-02 Metric Result Design

更新时间：2026-07-18

## 1. 任务边界

本文件交付 RCV3-SERIES-02：activity-level metric result 数据模型与只读 ViewModel 设计。

本阶段只定义 V3 正式实现边界，不做前端接入，不调用 AI / LLM，不写 `career_ai_insights`，不写真实业务数据，不把 `career_pb_records` 的 active/superseded 状态链作为记录中心主事实。

V3 正确链路固定为：

```text
Activity -> Record Metric Result -> Metric Series -> Current Best -> Chart
```

PB / 破纪录事件只是从 metric series 派生出的 marker 或 timeline event，不是右侧主折线图的数据源。

## 2. 当前代码基线

现有 schema 已有：

- `career_pb_records`：当前 PB / 旧 Records V2 active/superseded 状态表。
- `career_record_events`：旧记录事件表，当前主要围绕 record_id、pb_type、record_key、event_type。
- `career_record_curve_cache`：曲线缓存表，按单活动或曲线类型缓存 payload。
- `career_event_candidates`：候选事件 / 候选纪录状态表。

现有 schema 尚未定义：

- `career_record_metric_results`
- `career_record_indexes`

可复用代码基础：

- Catalog / Registry：`RecordDefinition`、`RECORD_DEFINITIONS`、`get_record_definition()`、`get_career_record_catalog()`。
- Activity facts：`normalize_activity_record_sport()`、`build_activity_record_facts()`、`_activity_stream_list()`。
- 安全 evidence / 展示工具：`RecordEvidence`、`build_record_evidence()`、`canonicalize_record_range()`、`canonicalize_record_quality()`、`_record_metric_display()`。
- Running best effort：`normalize_distance_time_points()`、`best_effort_distance_window()`、`best_effort_distance_or_fallback()`。
- Cycling / activity-total resolvers：`build_cycling_power_record_evidences()`、`build_cycling_activity_total_record_evidences()` 等可在后续多运动扩展中复用。

必须冻结或降级为兼容层的旧路径：

- `career_pb_records` active/superseded 不能继续作为记录中心主图事实源。
- `get_career_record_history()` 不能继续作为右侧主折线图 API。
- candidate -> active 写入状态机不能作为 V3 metric result 生成链路。
- `preview_career_records()` 只能作为只读诊断 / 迁移辅助，不能被前端主图调用。

## 3. 数据模型

### 3.1 `career_record_metric_results`

该表是 V3 记录中心事实层。每一行表示“一条 Activity 在一个 record_key 下计算出的一个成绩点”。

推荐 schema：

```sql
CREATE TABLE IF NOT EXISTS career_record_metric_results (
    id TEXT PRIMARY KEY,
    activity_id TEXT NOT NULL,
    record_key TEXT NOT NULL,
    sport TEXT NOT NULL,
    event_date TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value_num REAL NOT NULL,
    metric_unit TEXT NOT NULL,
    display_value TEXT NOT NULL DEFAULT '',
    source_mode TEXT NOT NULL,
    record_family TEXT NOT NULL DEFAULT '',
    comparison TEXT NOT NULL,
    scope_json TEXT NOT NULL DEFAULT '{}',
    scope_hash TEXT NOT NULL DEFAULT 'scope:default',
    range_json TEXT NOT NULL DEFAULT '{}',
    quality_json TEXT NOT NULL DEFAULT '{}',
    eligibility_json TEXT NOT NULL DEFAULT '{}',
    resolver_version TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    input_fingerprint TEXT NOT NULL,
    result_fingerprint TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'available',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(activity_id, record_key, scope_hash, resolver_version)
);
```

字段语义：

- `activity_id`：必须绑定真实 Activity。
- `record_key`：来自 Catalog，例如 `running_5k`。
- `event_date`：活动日期，用于 series 时间轴排序。
- `metric_value_num`：用于比较和绘图的标准数值。
- `display_value`：后端格式化后的展示值，前端不得自行格式化关键口径。
- `range_json`：窗口范围，例如 5K 的起止秒、起止距离。
- `quality_json`：质量状态、reason_codes、fallback 标记、是否可进入 current best。
- `eligibility_json`：是否参与 current best / progression / chart，及原因。
- `input_fingerprint`：Activity 安全输入摘要指纹，用于增量重算。
- `result_fingerprint`：result 事实指纹，用于幂等写入和变更检测。
- `status`：建议枚举 `available`、`partial`、`validation_required`、`sample_missing`、`unsupported`、`invalidated`。

推荐索引：

```sql
CREATE INDEX IF NOT EXISTS idx_career_record_metric_results_key_date
ON career_record_metric_results(record_key, scope_hash, event_date, activity_id);

CREATE INDEX IF NOT EXISTS idx_career_record_metric_results_sport_key
ON career_record_metric_results(sport, record_key, status, event_date);

CREATE INDEX IF NOT EXISTS idx_career_record_metric_results_activity
ON career_record_metric_results(activity_id, record_key);

CREATE INDEX IF NOT EXISTS idx_career_record_metric_results_fingerprint
ON career_record_metric_results(record_key, input_fingerprint, result_fingerprint);
```

### 3.2 `career_record_events`

`career_record_events` 在 V3 中可以继续存在，但语义要转为派生事件层。

V3 建议新增或兼容以下字段：

- `metric_result_id`
- `record_key`
- `scope_hash`
- `event_type`
- `event_at`
- `activity_id`
- `payload_json`
- `resolver_version`

V3 event_type 建议：

- `record_breaking`：按时间扫描 series 后发现刷新历史最佳。
- `current_best_changed`：索引 current best 变化。
- `metric_result_invalidated`：Activity 或 resolver 变化导致 result 失效。
- `milestone`：后续 timeline 可用的重要节点。

注意：Record Event 不保存主成绩事实，只保存从 metric results 派生出的事件标记。缺失或删除 event 时，必须能从 metric results 重建。

### 3.3 `career_record_indexes`

索引表是缓存，不是事实。

推荐 schema：

```sql
CREATE TABLE IF NOT EXISTS career_record_indexes (
    id TEXT PRIMARY KEY,
    record_key TEXT NOT NULL,
    sport TEXT NOT NULL,
    scope_hash TEXT NOT NULL DEFAULT 'scope:default',
    index_type TEXT NOT NULL,
    period_key TEXT NOT NULL DEFAULT 'career',
    metric_result_id TEXT NOT NULL,
    activity_id TEXT NOT NULL,
    event_date TEXT NOT NULL,
    metric_value_num REAL NOT NULL,
    metric_unit TEXT NOT NULL,
    display_value TEXT NOT NULL DEFAULT '',
    comparison TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    source_fingerprint TEXT NOT NULL,
    resolver_version TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(record_key, scope_hash, index_type, period_key)
);
```

`index_type` 建议：

- `current_best`
- `yearly_best`
- `monthly_best`
- `weekly_best`
- `trend_summary`

所有 index 必须能从 `career_record_metric_results` 重建。V3 首个实现可不落表，直接查询派生 current best；等性能需要明确后再 materialize。

## 4. ViewModel Contract

新增只读 API：

```text
get_career_record_metric_series(record_key, filters)
```

输入 filters：

```json
{
  "sport": "running",
  "scope_hash": "all",
  "year": null,
  "status": "available",
  "limit": 1000
}
```

返回 ViewModel：

```json
{
  "record_key": "running_5k",
  "sport": "running",
  "display_name": "5K",
  "comparison": "lower_is_better",
  "axis_direction": "lower",
  "points": [],
  "current_best": null,
  "record_progression": [],
  "summary": {},
  "filters": {},
  "status": {},
  "metrics": {}
}
```

`points[]` 每个点代表一条历史活动的指标成绩：

```json
{
  "id": "metric_result:running_5k:activity-id:scope",
  "activity_id": "activity-id",
  "record_key": "running_5k",
  "sport": "running",
  "event_date": "2025-05-03",
  "metric": {
    "name": "elapsed_time_sec",
    "value": 1212,
    "unit": "seconds",
    "display": "20:12"
  },
  "range": {
    "start_sec": 1234.0,
    "end_sec": 2446.0,
    "start_distance_m": 5020.0,
    "end_distance_m": 10020.0,
    "distance_m": 5000.0
  },
  "quality": {
    "state": "high_confidence",
    "confidence": 0.92,
    "source": "best_effort_distance",
    "reason_codes": ["best_effort_distance_window"],
    "fallback": false,
    "eligible_for_current_best": true
  },
  "scope": {
    "scope_hash": "scope:default",
    "labels": [],
    "dimensions": {}
  },
  "detail_link": {
    "activity_id": "activity-id",
    "source": "career"
  },
  "is_current_best": true,
  "is_record_breaking": true
}
```

`current_best`：

- 从 `points[]` 中按 `comparison` 派生。
- `lower_is_better` 取最小 `metric.value`。
- `higher_is_better` 取最大 `metric.value`。
- 只允许后端计算，前端只渲染。

`record_progression`：

- 按 `event_date ASC, activity_id ASC` 扫描 `points[]`。
- 当某个点优于此前 best，标记为 record breaking。
- 它用于 chart marker / timeline，不是 chart 数据源。

`summary` 建议字段：

```json
{
  "point_count": 26,
  "eligible_count": 24,
  "record_breaking_count": 3,
  "current_best_activity_id": "activity-id",
  "first_point_date": "2023-01-01",
  "last_point_date": "2026-07-17",
  "status_counts": {
    "available": 24,
    "validation_required": 2
  }
}
```

`status` 建议字段：

```json
{
  "schema_ready": true,
  "data_ready": true,
  "state": "ready",
  "message": "",
  "resolver_version": "records-v3-series-v1"
}
```

安全边界：

- 不返回 raw FIT。
- 不返回 `points_json` / `track_json` / `power_stream` 原始流。
- 不返回本地路径、SQLite schema、设备标识、体重历史。
- 不返回 prompt、AI 文案或 AI insight。

## 5. 派生算法

### 5.1 Current Best

输入：过滤后的 eligible points。

排序：

- `lower_is_better`：`metric_value_num ASC, event_date ASC, activity_id ASC`
- `higher_is_better`：`metric_value_num DESC, event_date ASC, activity_id ASC`

输出：

- `current_best` 指向完整 point ViewModel。
- 对应 point 标记 `is_current_best = true`。

### 5.2 Record Progression

输入：按时间升序排列的 eligible points。

过程：

1. 初始化 `best = null`。
2. 逐点扫描。
3. 若当前点优于 `best`，生成 progression item，并更新 `best`。
4. 首个 eligible point 可以标记为 `first_record`。

输出 item：

```json
{
  "metric_result_id": "metric_result:...",
  "activity_id": "activity-id",
  "event_date": "2025-05-03",
  "metric": {},
  "previous_best_metric": {},
  "improvement": {},
  "event_type": "record_breaking"
}
```

`record_progression` 只用于 marker；chart 主序列始终使用 `points[]`。

## 6. Running 5K 首阶段只读落地方案

目标：实现 `running_5k` metric series 只读路径，先不写真实库。

可复用现有能力：

- 活动读取：复用 `_preview_career_record_activity_rows()` 的安全列选择，但后续应改名为 series 专用 reader，避免 preview 语义泄漏。
- sport normalize：复用 `build_activity_record_facts()`。
- 距离流读取：复用 `_activity_stream_list(activity, "points_json", "track_json")`。
- 窗口计算：复用 `best_effort_distance_or_fallback()`，目标距离来自 Catalog `running_5k.standard_distance_m`。
- range / quality 清洗：复用 `canonicalize_record_range()`、`canonicalize_record_quality()`。
- metric 展示：复用 `_record_metric_display()`。

只读函数建议：

```text
build_running_5k_metric_result_from_activity(activity) -> dict | None
get_career_record_metric_series(record_key, filters, conn=None) -> dict
```

`build_running_5k_metric_result_from_activity()`：

1. 读取 Activity safe summary 和 distance/time stream。
2. 校验 sport 为 running。
3. 调用 `best_effort_distance_or_fallback(stream, 5000, activity=activity, fallback_tolerance_ratio=None 或 Catalog 口径)`。
4. 成功时生成一个 point。
5. 若 fallback 或质量不足，仍可返回 `validation_required` point，但 `eligible_for_current_best=false`，除非产品明确允许。
6. 每个 Activity 对 `running_5k` 最多生成一个 point。

注意：当前 `RUNNING_RECORD_DEFINITIONS` 仍是 V1 `activity_total` 口径。RCV3-SERIES-03 实现时必须显式覆盖 running 5K 为 `best_effort_distance`，不能沿用整次活动 3% tolerance 作为主结果。

## 7. 后续代码改造清单

RCV3-SERIES-03：

- 新增只读 running 5K series builder。
- 新增 `get_career_record_metric_series()` 后端函数。
- 新增 `main.py` pywebview 只读桥。
- 暂不写 `career_record_metric_results` 真实表，可直接从 activities 动态构造 ViewModel，作为只读 MVP。

RCV3-SERIES-04：

- 扩展 running 10K / 半马 / 全马。
- 将 running standard distance definitions 迁移到 `best_effort_distance` 口径或增加 V3 catalog overlay。

RCV3-SERIES-05：

- 固化 ViewModel contract 和 js_api_contract。
- 增加 status、summary、progression、current_best 完整字段。

RCV3-SERIES-06：

- `get_career_records()` 左侧摘要从 metric series 派生 current best。
- 不再依赖 `career_pb_records` active 作为 Records Center 当前最佳。

RCV3-SERIES-07：

- 前端右侧折线图改用 `get_career_record_metric_series()`。
- 保留左侧/右侧布局，替换点位语义和底部列表。

RCV3-SERIES-09：

- 决定是否 materialize `career_record_metric_results`。
- 建立导入/刷新活动时的增量计算和 invalidation 策略。

## 8. 测试清单

新增测试：

- `tests/test_career_record_metric_series_schema_contract.py`
  - 若实现 schema，验证 `career_record_metric_results` 和 index 存在。
  - 验证不创建或写入 `career_ai_insights`。
- `tests/test_career_record_metric_series_running_5k.py`
  - 多条跑步活动各生成一个 5K point。
  - 当前最佳从完整 points 派生。
  - progression 只包含刷新历史最佳点。
  - chart points 数量等于可计算活动数，不等于 PB 刷新次数。
- `tests/test_career_record_metric_series_api_contract.py`
  - API 返回 `points`、`current_best`、`record_progression`、`summary`、`status`。
  - 不返回 raw FIT、`points_json`、`track_json`、本地路径、SQLite schema。
- `tests/test_career_records_v3_frontend_boundary.py`
  - 前端不调用 `preview_career_records()`。
  - 前端不计算窗口、current best、record progression。
  - 右侧图表消费 `get_career_record_metric_series()`。

需要冻结或改写的旧测试：

- 保护 active/superseded 主链的记录中心测试应迁入 legacy 或改写为 PB archive 测试。
- 保护 candidate -> active 写入链的测试不应作为 V3 Records Center 验收。
- 当前 `test_career_records_v2_chart_frontend.py` 断言 `get_career_record_history()`，后续 RCV3-SERIES-07 必须改为断言 `get_career_record_metric_series()`。

## 9. 风险和冻结项

风险：

- 直接删除旧 `career_pb_records` 路径会影响 ACS PB archive、Overview、Season、Timeline 等现有功能。
- 直接让前端消费 preview/materializer 会造成切换指标时全量扫描历史活动。
- 若 current best 先写成 active PB，再反推 series，会再次回到 V2 跑偏路径。
- 若运行 5K 继续使用 V1 `activity_total` 3% tolerance，会无法表达活动内最佳 5K 窗口。

冻结项：

- 本阶段不删除 `career_pb_records`。
- 本阶段不删除 candidate/active 写入代码。
- 本阶段不改 UI。
- 本阶段不写真实 metric result 表数据。
- 本阶段不接入 AI，不调用 LLM，不写 `career_ai_insights`。

## 10. 验收定义

RCV3-SERIES-02 完成标准：

- 已定义 `career_record_metric_results` 事实模型。
- 已定义 Record Event / Record Index 作为可重建派生层。
- 已定义 `get_career_record_metric_series()` ViewModel。
- 已明确 running 5K 只读落地方案。
- 已明确后续代码改造和测试清单。
- 已明确旧 PB active/superseded、candidate/active、preview/rebuild、AI 路径的冻结边界。

## 11. 当前实现状态（截至 RCV3-SERIES-18）

已实现的只读 V3 主链：

```text
Activity -> Record Metric Result -> Metric Series -> Current Best -> Chart
```

当前代码状态：

- `get_career_record_metric_series()` 已支持 running 标准距离首批四项：`running_5k`、`running_10k`、`running_half_marathon`、`running_marathon`。
- `points[]` 从历史跑步 Activity 的距离-时间流计算，每个点代表一条活动的对应标准距离 Best Effort 成绩。
- `current_best` 与 `record_progression` 均由后端从完整 `points[]` 派生。
- 右侧图表已消费 `get_career_record_metric_series().points/current_best/record_progression`，不再以 `get_career_record_history()` 作为主折线图数据源。
- `get_career_records()` 对 running 标准距离左侧摘要已从 metric series `current_best` 派生，并保持左侧/右侧通过同一 `record_key + scope_hash` 串联。
- 前端仍只渲染后端 ViewModel，不计算窗口、current best、record progression、scope、confidence、quality 或 axis direction。

仍然冻结的兼容路径：

- `career_pb_records` active/superseded 仅作为旧 PB / ACS / 兼容维护路径，不能作为 V3 主图或 running 标准距离左侧 Current Best 的主数据源。
- `career_event_candidates` 与 candidate -> active 写入状态机不参与 V3 metric series 生成链路。
- `preview_career_records()` 与 rebuild/materializer 不得被记录中心主图区前端调用。
- 当前阶段仍不写真实 `career_record_metric_results` 表，不写 `career_ai_insights`，不调用 AI / LLM。
