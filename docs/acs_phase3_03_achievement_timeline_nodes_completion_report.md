# ACS-Phase3-03 Achievement Timeline 节点只读接入完成报告

## 任务范围

本任务将 `get_career_achievements` 返回的 active 成就只读接入 `get_career_timeline`。

已完成：

- 新增 Achievement Timeline 节点构造逻辑
- `get_career_timeline(type=all)` 返回 race / pb / achievement 节点
- `get_career_timeline(type=achievement|achievements|milestone)` 只返回 achievement 节点
- 更新 `docs/js_api_contract.json`
- 新增 `tests/test_career_timeline_achievement_nodes.py`

未实现：

- Frontend Timeline UI
- Overview 代表成就接入
- Achievement Resolver 写入规则调整
- Memory Gallery
- AI Snapshot / AI 洞察

## 数据来源

Timeline 成就节点只读取：

```text
career_achievement_events WHERE status = 'active'
```

实际入口复用：

```python
get_career_achievements(
    {
        "achievement_type": "all",
        "year": normalized_filters["year"],
        "source": "all",
        "min_score": None,
    },
    conn=db,
)
```

不重新计算 Achievement，不读取 Activity、raw FIT、points、track_json、file_path 或 SQLite schema。

## Timeline 节点结构

Achievement 节点包含：

- `id`
- `type = achievement`
- `activity_id`
- `title`
- `achievement_type`
- `date`
- `score`
- `icon`
- `description`
- `confidence`
- `source`
- `detail_link`

`detail_link` 固定为：

```json
{
  "activity_id": "<activity_id>",
  "source": "career"
}
```

## 筛选规则

`get_career_timeline(filters)` 支持：

- `type = all`：聚合 race / pb / achievement
- `type = race`：仅赛事
- `type = pb`：仅 PB
- `type = achievement | achievements | milestone`：仅成就
- `year`：应用于 race / pb / achievement
- `sport`：只应用于 race / pb，不过滤 achievement

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

低置信度候选事件仍只统计在 `candidates_count`，不会进入正式 Timeline。

## macOS / Windows 兼容性

- 测试使用 `sqlite3.connect(":memory:")`
- 不硬编码系统路径
- 不依赖大小写敏感文件系统
- 中文 title / description 正常通过测试
- pywebview API envelope 契约不变

## 验证结果

已通过：

```bash
python3 -m pytest tests/test_career_timeline_achievement_nodes.py
# 7 passed

python3 -m pytest tests/test_career_achievements_api.py tests/test_career_achievement_resolver.py tests/test_career_timeline_pb_nodes.py tests/test_career_overview_timeline_races.py tests/test_career_races_api.py tests/test_career_pb_api.py tests/test_career_api_skeleton.py tests/test_career_backend_schema.py
# 58 passed

python3 -m py_compile career_backend.py main.py profile_backend.py
# passed

python3 -m json.tool docs/js_api_contract.json
# passed
```

说明：pytest 期间存在 urllib3 / LibreSSL warning，为当前 macOS Python 环境提示，不影响本任务结果。

## 下一任务建议

建议进入：

`ACS-Phase3-04：Overview 代表成就接入`

建议边界：

- 复用 `get_career_achievements`
- 只把代表性成就接入 `get_career_overview.representative_achievements`
- 不重新计算 Achievement
- 不做前端 UI
- 不生成 AI Snapshot
