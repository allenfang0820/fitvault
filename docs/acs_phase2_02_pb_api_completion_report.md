# ACS-Phase2-02 get_career_pb API 完成报告

## 任务范围

本任务基于 `ACS-Phase2-01` 已生成的 `career_pb_records`，实现 PB 记录只读 API。

已完成：

- 新增 `career_backend.get_career_pb(filters=None, conn=None)`
- 新增 `main.Api.get_career_pb(filters=None)`
- 更新 `docs/js_api_contract.json`
- 新增 `tests/test_career_pb_api.py`
- 为 ACS public metadata 出口增加 forbidden key 递归清洗

未实现：

- 前端 PB 页面或卡片
- 骑行 PB Resolver 扩展
- Achievement Engine
- Timeline PB 节点
- AI Snapshot / AI 洞察
- 用户手填无 Activity 的 PB

## API 返回结构

`get_career_pb` 返回统一 envelope 中的 `data`：

```json
{
  "pb_records": [],
  "summary": {
    "total": 0,
    "by_pb_type": {},
    "by_sport": {},
    "by_year": {}
  },
  "filters": {
    "sport": "all",
    "year": null,
    "pb_type": "all",
    "source": "all"
  },
  "status": {
    "schema_ready": true,
    "data_ready": false,
    "message": "PB 记录将在 PB Resolver 识别后展示"
  }
}
```

每条 PB 记录包含：

- `id`
- `activity_id`
- `sport`
- `pb_type`
- `value`
- `value_unit`
- `improvement_sec`
- `event_date`
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

## 读取边界

API 只读取：

```sql
career_pb_records WHERE status = 'active'
```

支持筛选：

- `sport`
- `year`
- `pb_type`
- `source`

禁止返回：

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

- 默认数据库连接继续使用 `profile_backend.DB_PATH`
- 测试使用 `tempfile.TemporaryDirectory()` 和 `Path`
- 不硬编码平台路径
- 不暴露本地绝对路径
- API 保持 pywebview 统一 envelope

## 验证结果

已通过：

```bash
python3 -m pytest tests/test_career_pb_api.py
# 7 passed

python3 -m pytest tests/test_career_pb_resolver.py
# 8 passed

python3 -m pytest tests/test_career_races_api.py tests/test_career_race_resolver.py
# 15 passed

python3 -m pytest tests/test_career_overview_timeline_races.py tests/test_career_backend_schema.py tests/test_career_api_skeleton.py
# 21 passed

python3 -m py_compile career_backend.py main.py profile_backend.py
# passed

python3 -m json.tool docs/js_api_contract.json
# passed
```

说明：pytest 期间存在 urllib3 / LibreSSL warning，为当前 macOS Python 环境提示，不影响本任务结果。

## 下一任务建议

建议进入：

`ACS-Phase2-03：PB Timeline 节点只读接入`

建议边界：

- 只把 active PB 组织为 timeline node
- 不重新计算 PB
- 不做前端 UI
- 不扩展骑行 PB Resolver
- 不生成 AI Snapshot
