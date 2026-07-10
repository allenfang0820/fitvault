# ACS-Phase4-01 Career Overview API 完整总览收口完成报告

## 任务范围

本任务对 `get_career_overview` 做后端 API 收口，确认其可作为 ACS 一级页首屏总览数据源。

已完成：

- 收口 Activity summary 聚合语义
- 收口 Overview `status.data_ready` 语义
- 更新 `docs/js_api_contract.json`
- 新增 `tests/test_career_overview_api_closure.py`

未实现：

- Frontend UI
- 一级导航
- Memory Gallery
- AI Snapshot / AI 洞察
- Race / PB / Achievement Resolver 规则调整

## Overview 数据来源

`get_career_overview` 聚合以下安全来源：

- `activities` 表的基础摘要
- `career_race_events WHERE status = 'active'`
- `career_pb_records WHERE status = 'active'`
- `career_achievement_events WHERE status = 'active'`
- `career_memory_items`

其中：

- `latest_race` 复用 `get_career_races`
- `latest_pb` 复用 `get_career_pb`
- `representative_pb_records` 复用 PB safe records
- `representative_achievements` 复用 `get_career_achievements`

不读取或返回 raw FIT、points、track_json、file_path 或 SQLite schema。

## Summary 字段语义

`summary` 字段保持：

- `career_start_year`：未删除 Activity 中最早 `start_time` / `start_time_utc` 年份
- `activity_count`：未删除 Activity 数
- `race_count`：active RaceEvent 数
- `pb_count`：active PB 数
- `achievement_count`：active Achievement 数
- `memory_count`：MemoryItem 数
- `covered_city_count`：未删除 Activity 中非空城市去重数
- `total_distance_km`：未删除 Activity 距离汇总，兼容 `dist_km` 与 `distance`

## data_ready 语义

`status.data_ready` 在以下任一条件满足时为 `true`：

- `activity_count > 0`
- `race_count > 0`
- `pb_count > 0`
- `achievement_count > 0`
- `memory_count > 0`

因此，即使尚未生成 Race / PB / Achievement，只要存在普通 Activity，Overview 也可展示基础生涯。

## 安全边界

返回结果递归检查不得包含：

- `points`
- `points_json`
- `track_json`
- `raw_records`
- `fit_records`
- `file_path`
- `advanced_metrics`
- `shadow_diff_json`
- `sqlite_schema`
- `schema`

所有 Race / PB / Achievement 对象继续保留：

```json
{
  "detail_link": {
    "activity_id": "<activity_id>",
    "source": "career"
  }
}
```

## macOS / Windows 兼容性

- 测试使用 `sqlite3.connect(":memory:")`
- 默认连接测试使用 `tempfile.TemporaryDirectory()` 临时替换 `profile_backend.DB_PATH`
- 不硬编码系统路径
- 不依赖大小写敏感文件系统
- pywebview API envelope 契约不变

## 验证结果

已通过：

```bash
python3 -m pytest tests/test_career_overview_api_closure.py
# 4 passed

python3 -m pytest tests/test_career_api_skeleton.py tests/test_career_overview_timeline_races.py tests/test_career_overview_pb_summary.py tests/test_career_overview_representative_achievements.py
# 25 passed

python3 -m pytest tests/test_career_achievement_phase3_integration.py tests/test_career_backend_schema.py
# 11 passed

python3 -m py_compile career_backend.py main.py profile_backend.py
# passed

python3 -m json.tool docs/js_api_contract.json
# passed
```

说明：pytest 期间存在 urllib3 / LibreSSL warning，为当前 macOS Python 环境提示，不影响本任务结果。

## 下一任务建议

建议进入：

`ACS-Phase4-02：Career Overview 前端首屏数据接入准备`

如继续后端优先，也可进入：

`ACS-Phase5-01：Timeline Engine 年月结构与筛选收口`
