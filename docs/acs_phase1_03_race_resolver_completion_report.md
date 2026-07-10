# ACS-Phase1-03 Race Resolver 完成报告

## 任务范围

本任务实现 Race Resolver 与赛事候选置信度模型，只做后端派生能力：

- 从 Activity 安全摘要字段识别赛事语义。
- 将 high / medium 置信度写入 `career_race_events`。
- 将 low 置信度写入 `career_event_candidates`。
- 保证所有正式赛事与候选都携带 `activity_id`。

本任务未实现：

- `get_career_races` API
- 前端 UI
- PB / Achievement / Memory Engine
- Timeline 节点渲染
- AI Snapshot 或 AI 洞察

## 修改文件

- `career_backend.py`
- `tests/test_career_race_resolver.py`
- `docs/acs_phase1_03_race_resolver_completion_report.md`

## 实现摘要

### Resolver 入口

新增：

```python
resolve_race_events(conn: sqlite3.Connection | None = None) -> dict[str, Any]
```

返回：

```json
{
  "ok": true,
  "processed": 0,
  "race_events_upserted": 0,
  "candidates_upserted": 0,
  "skipped": 0,
  "status": {
    "schema_ready": true,
    "resolver": "race",
    "message": "赛事解析完成"
  }
}
```

### 安全读取字段

Resolver 只读取 `RACE_RESOLVER_ACTIVITY_COLUMNS` 中的安全摘要字段，包括：

- `id`
- `title`
- `title_source`
- `sport_type`
- `sub_sport_type`
- `start_time`
- `start_time_utc`
- `dist_km`
- `distance`
- `duration`
- `duration_sec`
- `avg_pace`
- `region_city`
- `region`
- `region_display`
- `is_race`
- `race_source`
- `race_confidence`
- `race_override`
- `race_confirmed_at`
- `deleted_at`

禁止读取 / 存储：

- `points`
- `points_json`
- `track_json`
- `raw_records`
- `fit_records`
- `file_path`
- `advanced_metrics`
- `shadow_diff_json`

旧库缺列时使用 `NULL AS column` 兼容，不依赖平台路径或特定 SQLite 文件位置。

## Race Resolver 规则

### high

满足任一条件即进入 `career_race_events`：

- `race_source == 'user'` 且 `is_race == 1`
- `race_override == 1` 且 `is_race == 1`
- `race_source == 'fit_sport_event'` 且 `is_race == 1`
- `is_race == 1` 且 `race_confidence == 'high'`

写入：

- `confidence = 1.0`
- `source = user / fit_sport_event / resolver`
- `status = active`

### medium

标题强赛事关键词 + 标准距离区间同时满足时进入 `career_race_events`。

标准距离：

- 5K：4.8-5.3 km
- 10K：9.5-10.8 km
- 半马：20.5-21.7 km
- 全马：41.0-43.0 km

写入：

- `confidence = 0.75`
- `source = resolver`
- `status = active`

### low

只有标准距离匹配，或只有弱标题线索时，只进入 `career_event_candidates`：

- `candidate_type = race`
- `confidence = 0.35` 或 `0.25`
- `status = candidate`

## low 候选不污染正式赛事

`_build_race_decision()` 对 low 返回 `decision = candidate`。

`resolve_race_events()` 仅在 `decision == race_event` 时调用 `_upsert_race_event()`；low 只调用 `_upsert_race_candidate()`。

测试 `test_standard_distance_only_writes_low_candidate_not_race_event` 已覆盖：标准距离但无强赛事标题时，`career_race_events` 为空，`career_event_candidates` 有候选。

## 用户取消优先级

若 `race_source == 'user'` 且 `is_race == 0`：

- 不进入正式赛事。
- 不进入候选。
- 已存在的 `career_race_events` 会标记为 `inactive`。
- 已存在的 `career_event_candidates` 会标记为 `dismissed`。

测试 `test_user_cancelled_race_closes_existing_event_and_candidate` 已覆盖。

## 幂等策略

稳定 ID：

- 正式赛事：`race:{activity_id}`
- 候选赛事：`race_candidate:{activity_id}`

使用 SQLite `ON CONFLICT(id) DO UPDATE`，重复执行不会产生重复记录。

测试 `test_resolver_is_idempotent` 已覆盖。

## macOS / Windows 兼容性

- 默认连接继续使用 `profile_backend.DB_PATH`，不硬编码系统路径。
- 测试使用 `tempfile.TemporaryDirectory()` 与 `Path` 构造临时库。
- SQLite migration 与 resolver 写入均为幂等操作。
- 中文标题、城市名通过 `json.dumps(..., ensure_ascii=False)` 保留。
- 不向 ACS 或 AI 暴露本地绝对路径。

## 验证结果

已通过：

```bash
python3 -m pytest tests/test_career_race_resolver.py
# 9 passed

python3 -m pytest tests/test_career_backend_schema.py tests/test_career_api_skeleton.py
# 12 passed

python3 -m pytest tests/test_fit_sport_event_race.py tests/test_activity_race_flag_api.py
# 14 passed

python3 -m py_compile career_backend.py main.py profile_backend.py
# passed

python3 -m pytest tests/test_fit_sync.py
# 111 passed
```

说明：pytest 期间存在 urllib3 / LibreSSL warning，为当前 macOS Python 环境提示，不影响本任务结果。

## 下一任务建议

原计划下一个任务是：

`ACS-Phase1-04：实现 get_career_races API`

建议边界：

- 只读取 `career_race_events` 与必要 Activity 展示摘要。
- 返回统一 pywebview envelope。
- 支持基础筛选 / 排序。
- 所有赛事卡片必须带 `activity_id`，可回跳 Activity Detail。
- 不接前端 UI，不做 PB / 成就 / 记忆。
