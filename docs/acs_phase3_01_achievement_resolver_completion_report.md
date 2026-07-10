# ACS-Phase3-01 Achievement Resolver 后端骨架完成报告

## 任务范围

本任务建立 ACS Achievement Engine 的后端 Resolver 骨架，从 Activity 安全摘要字段识别 V1 基础成就，并写入 `career_achievement_events`。

已完成：

- 新增 `career_backend.resolve_achievement_events(conn=None)`
- 支持跑步首次 5K / 10K / 半马 / 全马
- 支持骑行首次 50K / 100K
- 支持最长跑步、最长骑行、最大累计爬升
- 支持首次点亮城市
- 纪录类新纪录出现时旧 active 成就标记为 `superseded`
- Resolver 幂等
- 新增 `tests/test_career_achievement_resolver.py`

未实现：

- `get_career_achievements` API
- Timeline 成就节点
- Overview 代表成就接入
- 前端 UI
- AI Snapshot / AI 洞察
- 复杂成就叙事或 AI 文案

## 数据来源

Achievement Resolver 只读取 `activities` 安全摘要字段：

- `id`
- `sport_type`
- `sub_sport_type`
- `start_time`
- `start_time_utc`
- `dist_km`
- `distance`
- `total_ascent`
- `ascent`
- `elev_gain`
- `gain_m`
- `region_city`
- `region`
- `region_display`
- `deleted_at`

禁止读取或存储：

- `points`
- `points_json`
- `track_json`
- `raw_records`
- `fit_records`
- `file_path`
- `advanced_metrics`
- `shadow_diff_json`

## V1 成就规则

首次跑步：

- `first_running_5k`：4.8-5.3 km
- `first_running_10k`：9.5-10.8 km
- `first_running_half_marathon`：20.5-21.7 km
- `first_running_marathon`：41.0-43.0 km

首次骑行：

- `first_cycling_50k`：49.0-55.0 km
- `first_cycling_100k`：98.0-110.0 km

纪录类：

- `longest_running`：跑步活动中 `dist_km` 最大的一条
- `longest_cycling`：骑行活动中 `dist_km` 最大的一条
- `max_ascent`：所有活动中爬升最大的一条

城市类：

- `first_city`：每个首次出现城市写入一条 active 成就
- 城市读取顺序：`region_city` -> `region_display` -> `region`
- 空城市跳过

## 写入策略

写入表：

```text
career_achievement_events
```

稳定 ID：

- 首次类：`achievement:{achievement_type}:{activity_id}`
- 纪录类：`achievement:{achievement_type}:{activity_id}`
- 城市类：`achievement:first_city:{city_key}:{activity_id}`

`display_metadata_json` 至少包含：

- `resolver = achievement`
- `achievement_type`
- `distance_km` 或 `ascent_m`
- `city`
- `previous_activity_id / previous_value`（纪录类新纪录适用）

## 幂等策略

重复执行：

- 不产生重复成就
- 当前 active 纪录保持 active
- 旧纪录不会重新变 active
- 新纪录出现时旧 active 同类型纪录标记为 `superseded`

## macOS / Windows 兼容性

- 默认连接继续使用 `profile_backend.DB_PATH`
- 测试使用 `sqlite3.connect(":memory:")` 与 `tempfile.TemporaryDirectory()`
- 不硬编码系统路径
- 不依赖大小写敏感文件系统
- 中文 title 与中文城市名通过测试

## 验证结果

已通过：

```bash
python3 -m pytest tests/test_career_achievement_resolver.py
# 9 passed

python3 -m pytest tests/test_career_backend_schema.py
# 7 passed

python3 -m pytest tests/test_career_overview_pb_summary.py tests/test_career_pb_api.py tests/test_career_timeline_pb_nodes.py
# 19 passed

python3 -m pytest tests/test_career_races_api.py tests/test_career_race_resolver.py
# 15 passed

python3 -m pytest tests/test_career_api_skeleton.py
# 5 passed

python3 -m pytest tests/test_career_overview_timeline_races.py
# 9 passed

python3 -m py_compile career_backend.py main.py profile_backend.py
# passed

python3 -m json.tool docs/js_api_contract.json
# passed
```

说明：pytest 期间存在 urllib3 / LibreSSL warning，为当前 macOS Python 环境提示，不影响本任务结果。

## 下一任务建议

建议进入：

`ACS-Phase3-02：实现 get_career_achievements API`

建议边界：

- 只读取 `career_achievement_events.status='active'`
- 返回 achievements、summary、filters 与 `detail_link`
- 不做前端 UI
- 不接入 Timeline
- 不生成 AI Snapshot
