# ACS-Phase2-01 PB Resolver 完成报告

## 任务范围

本任务建立 PB Engine 后端 Resolver 骨架，从 Activity 安全摘要字段识别跑步 PB，并写入 `career_pb_records`。

已完成：

- 新增 `career_backend.resolve_pb_records(conn=None)`
- 支持跑步 5K / 10K / 半马 / 全马 PB
- 写入 `career_pb_records`
- 保持每个 PB 类型只有一条 active PB
- 新 PB 出现时旧 PB 标记为 `superseded`
- 新增 `tests/test_career_pb_resolver.py`

未实现：

- `get_career_pb` API
- 前端 UI
- 骑行 PB
- Achievement Engine
- AI Snapshot / AI 洞察
- 用户手填无 Activity 的 PB

## 修改文件

- `career_backend.py`
- `tests/test_career_pb_resolver.py`
- `docs/acs_phase2_01_pb_resolver_completion_report.md`

## PB 识别规则

第一版仅识别跑步 PB。

跑步类型：

- `running`
- `run`
- `trail_running`
- `track_running`
- `road_running`

标准距离区间：

- `running_5k`：4.8-5.3 km
- `running_10k`：9.5-10.8 km
- `running_half_marathon`：20.5-21.7 km
- `running_marathon`：41.0-43.0 km

完成时间：

- 优先读取 `duration`
- 其次读取 `duration_sec`
- 缺少有效时长则跳过

## 写入规则

写入表：

```text
career_pb_records
```

记录字段：

- `id = pb:{pb_type}:{activity_id}`
- `activity_id`
- `sport = running`
- `pb_type`
- `value = duration_sec`
- `value_unit = seconds`
- `confidence = 1.0`
- `source = resolver`
- `status = active / superseded`
- `display_metadata_json`

`display_metadata_json` 包含：

- `resolver = pb`
- `pb_type`
- `distance_km`
- `matched_range_km`
- `previous_activity_id`
- `previous_value`
- `improvement_sec`

## active / superseded 规则

- 同一 `pb_type` 只保留最快活动为 `active`。
- 新增更快活动后：
  - 新活动写为 `active`
  - 旧 active PB 标记为 `superseded`
  - 新 PB 的 metadata 记录旧活动与提升秒数
- 新活动不快于当前 active 时，不切换 active PB。

## 幂等策略

稳定 ID 使用：

```text
pb:{pb_type}:{activity_id}
```

写入使用 SQLite `ON CONFLICT(id) DO UPDATE`。

重复执行 resolver：

- 不产生重复 PB。
- 当前最快活动保持 active。
- 旧记录不重新变成 active。

## forbidden fields 验证

PB Resolver 只读取：

- `id`
- `sport_type`
- `sub_sport_type`
- `start_time`
- `start_time_utc`
- `dist_km`
- `distance`
- `duration`
- `duration_sec`
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

测试 `test_resolver_does_not_select_or_store_forbidden_raw_fields` 已覆盖 SQL SELECT 与 `display_metadata_json`。

## Overview 联动

`get_career_overview()` 已统计：

```sql
career_pb_records WHERE status = 'active'
```

执行 PB Resolver 后，`summary.pb_count` 会自然反映 active PB 数量。

## macOS / Windows 兼容性

- 默认连接继续使用 `profile_backend.DB_PATH`。
- 测试使用 `tempfile.TemporaryDirectory()` 与 `Path` 创建临时 SQLite 文件。
- 不硬编码系统路径。
- SQLite 写入和 resolver 均幂等。
- 不暴露本地绝对路径。

## 验证结果

已通过：

```bash
python3 -m pytest tests/test_career_pb_resolver.py
# 8 passed

python3 -m pytest tests/test_career_overview_timeline_races.py
# 9 passed

python3 -m pytest tests/test_career_races_api.py tests/test_career_race_resolver.py
# 15 passed

python3 -m pytest tests/test_career_backend_schema.py tests/test_career_api_skeleton.py
# 12 passed

python3 -m py_compile career_backend.py main.py profile_backend.py
# passed

python3 -m json.tool docs/js_api_contract.json
# passed

python3 -m pytest tests/test_fit_sport_event_race.py tests/test_activity_race_flag_api.py
# 14 passed
```

说明：pytest 期间存在 urllib3 / LibreSSL warning，为当前 macOS Python 环境提示，不影响本任务结果。

## 下一任务建议

建议进入：

`ACS-Phase2-02：实现 get_career_pb API`

建议边界：

- 只读取 `career_pb_records.status='active'`
- 返回 PB 列表、summary 与 `detail_link`
- 不接前端 UI
- 不扩展骑行 PB
- 不生成 AI Snapshot
