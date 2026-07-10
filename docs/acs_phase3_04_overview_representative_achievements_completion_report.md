# ACS-Phase3-04 Overview 代表成就接入完成报告

## 任务范围

本任务将 `get_career_achievements` 返回的 active 成就只读接入 `get_career_overview.representative_achievements`。

已完成：

- 新增 Overview 代表成就选择逻辑
- `get_career_overview` 返回 `representative_achievements`
- 更新 `docs/js_api_contract.json`
- 新增 `tests/test_career_overview_representative_achievements.py`

未实现：

- Frontend UI
- Timeline 额外改造
- Achievement Resolver 写入规则调整
- Memory Gallery
- AI Snapshot / AI 洞察

## 数据来源

Overview 代表成就只复用：

```python
get_career_achievements(conn=db)
```

实际数据来源仍为：

```text
career_achievement_events WHERE status = 'active'
```

不重新计算 Achievement，不读取 Activity、raw FIT、points、track_json、file_path 或 SQLite schema。

## 返回字段

`representative_achievements` 中每条记录包含：

- `id`
- `activity_id`
- `achievement_type`
- `title`
- `event_date`
- `score`
- `icon`
- `description`
- `confidence`
- `source`
- `display_metadata`
- `detail_link`

`detail_link` 固定为：

```json
{
  "activity_id": "<activity_id>",
  "source": "career"
}
```

## 排序规则

代表成就选择规则：

```text
score DESC
event_date DESC
id DESC
LIMIT 4
```

该规则与 `get_career_achievements` 的代表性排序保持一致。

## 边界约束

返回结果不得包含：

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

Overview summary 字段保持不变：

- `career_start_year`
- `activity_count`
- `race_count`
- `pb_count`
- `achievement_count`
- `memory_count`
- `covered_city_count`
- `total_distance_km`

## macOS / Windows 兼容性

- 测试使用 `sqlite3.connect(":memory:")`
- 不硬编码系统路径
- 不依赖大小写敏感文件系统
- 中文 title / description 正常通过测试
- pywebview API envelope 契约不变

## 验证结果

已通过：

```bash
python3 -m pytest tests/test_career_overview_representative_achievements.py
# 5 passed

python3 -m pytest tests/test_career_achievements_api.py tests/test_career_timeline_achievement_nodes.py tests/test_career_overview_pb_summary.py tests/test_career_overview_timeline_races.py tests/test_career_api_skeleton.py tests/test_career_backend_schema.py
# 43 passed

python3 -m py_compile career_backend.py main.py profile_backend.py
# passed

python3 -m json.tool docs/js_api_contract.json
# passed
```

说明：pytest 期间存在 urllib3 / LibreSSL warning，为当前 macOS Python 环境提示，不影响本任务结果。

## 下一任务建议

建议进入：

`ACS-Phase3-05：Achievement Engine Phase 3 收口与回归`

建议边界：

- 汇总 Phase 3 已完成能力
- 补齐必要的集成回归
- 不新增前端 UI
- 不生成 AI Snapshot
