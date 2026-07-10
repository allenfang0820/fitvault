# ACS-Phase3-02 get_career_achievements API 完成报告

## 任务范围

本任务基于 `career_achievement_events` 中由 Achievement Resolver 生成的 active 成就，实现 ACS 成就档案只读 API。

已完成：

- 新增 `career_backend.get_career_achievements(filters=None, conn=None)`
- 新增 `main.Api.get_career_achievements(filters=None)`
- 更新 `docs/js_api_contract.json`
- 新增 `tests/test_career_achievements_api.py`

未实现：

- 前端 UI
- Timeline 成就节点
- Overview 代表成就接入
- Achievement Resolver 写入规则调整
- AI Snapshot / AI 洞察

## 数据来源

API 只读取：

```text
career_achievement_events WHERE status = 'active'
```

不重新计算 Achievement，不读取 Activity、raw FIT、points、track_json、file_path 或 SQLite schema。

## API 返回结构

`get_career_achievements` 返回统一 envelope 中的 `data`：

```json
{
  "achievements": [],
  "summary": {
    "total": 0,
    "by_type": {},
    "by_year": {},
    "by_source": {},
    "max_score": null
  },
  "filters": {
    "achievement_type": "all",
    "year": null,
    "source": "all",
    "min_score": null
  },
  "status": {
    "schema_ready": true,
    "data_ready": false,
    "message": "成就档案将在 Achievement Resolver 识别后展示"
  }
}
```

每条 achievement 包含：

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

## 筛选规则

支持：

- `achievement_type` / `type`
- `year`
- `source`
- `min_score`

归一化：

- `achievement_type = all` 时不过滤类型
- `source = all` 时不过滤来源
- 非法 `year` 归一化为 `null`
- 非法 `min_score` 归一化为 `null`

## 排序规则

```text
score DESC
event_date DESC
id DESC
```

## 边界约束

返回结果会清洗 forbidden keys：

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

## macOS / Windows 兼容性

- 测试使用 `sqlite3.connect(":memory:")` 与 `tempfile.TemporaryDirectory()`
- 不硬编码系统路径
- 不依赖大小写敏感文件系统
- 中文 title / description / metadata 通过测试
- pywebview API envelope 保持 `{ok, code, msg, data, traceId}`

## 验证结果

已通过：

```bash
python3 -m pytest tests/test_career_achievements_api.py
# 9 passed

python3 -m pytest tests/test_career_achievement_resolver.py
# 9 passed

python3 -m pytest tests/test_career_races_api.py tests/test_career_pb_api.py
# 13 passed

python3 -m pytest tests/test_career_api_skeleton.py tests/test_career_backend_schema.py
# 12 passed

python3 -m pytest tests/test_career_overview_pb_summary.py tests/test_career_timeline_pb_nodes.py tests/test_career_overview_timeline_races.py
# 21 passed

python3 -m py_compile career_backend.py main.py profile_backend.py
# passed

python3 -m json.tool docs/js_api_contract.json
# passed
```

说明：pytest 期间存在 urllib3 / LibreSSL warning，为当前 macOS Python 环境提示，不影响本任务结果。

## 下一任务建议

建议进入：

`ACS-Phase3-03：Achievement Timeline 节点只读接入`

建议边界：

- 只把 active achievements 组织为 timeline node
- 不重新计算 Achievement
- 不做前端 UI
- 不接入 Overview
- 不生成 AI Snapshot
