# ACS-Phase7-01 Career Snapshot 生成器白名单骨架完成报告

## 任务范围

本任务进入 ACS Phase 7，但只建立 Career Snapshot 后端白名单骨架。

已完成：

- 新增 `build_career_snapshot(conn=None)`
- 新增 Snapshot 白名单 sanitizer
- 新增 `primary_sport` 安全聚合
- 新增 Snapshot Builder 单元测试

未实现：

- 不新增 pywebview API
- 不新增前端入口
- 不调用 LLM
- 不生成最终 AI 总结
- 不写入 `career_snapshots` 表

## 修改文件

- `career_backend.py`
  - 新增 `_build_primary_sport_summary`
  - 新增 `_sanitize_snapshot_pb`
  - 新增 `_sanitize_snapshot_achievement`
  - 新增 `_sanitize_snapshot_timeline_node`
  - 新增 `_sanitize_snapshot_memory`
  - 新增 `_flatten_timeline_digest`
  - 新增 `build_career_snapshot`
- `tests/test_career_snapshot_builder.py`
  - 新增 Snapshot 白名单、限量、降级和不持久化测试
- `docs/acs_phase7_01_career_snapshot_builder_completion_report.md`

## Snapshot 结构

`build_career_snapshot(conn=None)` 返回：

```json
{
  "snapshot_version": "acs.v1",
  "generated_at": "ISO time",
  "summary": {
    "career_start_year": 2023,
    "activity_count": 3,
    "race_count": 1,
    "pb_count": 1,
    "achievement_count": 1,
    "memory_count": 1,
    "covered_city_count": 2,
    "total_distance_km": 45.0
  },
  "primary_sport": {
    "sport": "running",
    "activity_count": 2,
    "confidence": "derived"
  },
  "pb_summary": [],
  "major_achievements": [],
  "timeline_digest": [],
  "representative_memories": [],
  "status": {
    "schema_ready": true,
    "data_ready": true,
    "message": "Career Snapshot 已生成"
  }
}
```

## 字段白名单

### summary

- `career_start_year`
- `activity_count`
- `race_count`
- `pb_count`
- `achievement_count`
- `memory_count`
- `covered_city_count`
- `total_distance_km`

### primary_sport

- `sport`
- `activity_count`
- `confidence`

### pb_summary

最多 6 条，每条仅包含：

- `id`
- `activity_id`
- `sport`
- `pb_type`
- `value`
- `value_unit`
- `event_date`

### major_achievements

最多 8 条，每条仅包含：

- `id`
- `activity_id`
- `achievement_type`
- `title`
- `event_date`
- `score`

### timeline_digest

最多 12 个节点，每条仅包含：

- `id`
- `activity_id`
- `type`
- `title`
- `date`

### representative_memories

最多 6 条，每条仅包含：

- `id`
- `activity_id`
- `race_id`
- `type`
- `title`
- `story`
- `date`
- `has_media`

## forbidden 字段确认

Snapshot 不读取或返回：

- raw FIT
- points / points_json
- track_json
- raw_records / fit_records
- file_path
- advanced_metrics
- shadow_diff_json
- sqlite_schema / schema
- storage_ref
- path
- thumbnail_url
- detail_link

## representative_memories 安全策略

`representative_memories` 只从 `get_career_memory` 的安全 view model 取值，并再次裁剪字段。

明确不进入 Snapshot：

- `storage_ref`
- `thumbnail_url`
- `detail_link`
- 本地路径
- 媒体引用

`has_media` 只作为布尔状态进入 Snapshot。

## primary_sport 降级策略

- 若 `activities` 表不存在，返回：
  - `sport=""`
  - `activity_count=0`
  - `confidence="none"`
- 若没有可用运动类型列，返回同样空结构。
- 若有 `sport_type` / `sport` / `activity_type`，按 active 活动聚合计数，取数量最多的运动类型。
- 若 `deleted_at` 存在，已删除活动不参与聚合。

## 不写 DB / 不调用 LLM 确认

- 本任务没有新增 `main.py` API。
- 本任务没有新增前端入口。
- `build_career_snapshot` 不调用 `call_llm`。
- `build_career_snapshot` 不导入或调用 `main.py`。
- `build_career_snapshot` 不向 `career_snapshots` 表写入记录。

说明：函数会复用既有 ACS 安全查询函数；这些查询会确保 ACS schema 存在，但不会持久化 Snapshot 内容。

## macOS / Windows 兼容性

- 未新增平台路径逻辑。
- 未读写本地媒体文件。
- 未返回本地绝对路径。
- SQLite 查询使用显式列名和参数化调用。
- 中文状态文案保持 UTF-8。

## 验证结果

已通过：

```bash
python3 -m pytest tests/test_career_snapshot_builder.py
python3 -m pytest tests/test_career_snapshot_builder.py tests/test_career_memory_phase6_closure_docs.py tests/test_career_memory_media_api.py tests/test_career_memory_story_edit_api.py tests/test_career_memory_api.py tests/test_career_timeline_engine_closure.py tests/test_career_overview_api_closure.py
python3 -m py_compile career_backend.py main.py profile_backend.py
python3 -m json.tool docs/js_api_contract.json >/dev/null
```

结果：

- Snapshot Builder 新增测试：5 passed。
- 相关 ACS 回归：41 passed。
- Python 编译：通过。
- JS API 契约 JSON：合法。

说明：当前 macOS Python 环境仍有 urllib3 / LibreSSL warning，不影响测试结果。

## 下一个任务建议

建议进入 `ACS-Phase7-02：Career Snapshot 持久化与只读调试 API`。

建议边界：

- 可以考虑将 Snapshot 写入 `career_snapshots` 表，但必须仍保持白名单。
- 可新增只读调试 API，用于本地检查 Snapshot 内容。
- 仍不调用 LLM，不生成 AI 总结。
- 仍不新增正式前端 AI 入口。
