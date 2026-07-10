# ACS-Phase2-04 PB Overview 摘要接入完成报告

## 任务范围

本任务将 PB Resolver 已生成的 active PB 记录接入 `get_career_overview`。

已完成：

- `get_career_overview(conn=None)` 返回 `latest_pb`
- `get_career_overview(conn=None)` 返回 `representative_pb_records`
- `summary.pb_count` 继续统计 active PB 数量
- representative PB 采用标准跑步 PB 类型优先级
- 更新 `docs/js_api_contract.json`
- 新增 `tests/test_career_overview_pb_summary.py`

未实现：

- 前端 UI
- 骑行 PB Resolver 扩展
- Achievement Engine
- AI Snapshot / AI 洞察
- 用户手填无 Activity 的 PB

## 数据来源

PB Overview 摘要来自：

```text
career_pb_records WHERE status = 'active'
```

读取路径：

```text
get_career_overview
  -> get_career_pb
  -> career_pb_records active records
  -> latest_pb / representative_pb_records
```

本任务不重新计算 PB，也不修改 PB 写入规则。

## 返回字段

新增：

```json
{
  "latest_pb": null,
  "representative_pb_records": []
}
```

无 PB 时：

- `latest_pb = null`
- `representative_pb_records = []`
- `summary.pb_count = 0`

## latest_pb 规则

`latest_pb` 取 active PB 中 `event_date` 最新的一条。

## representative_pb_records 规则

第一版最多返回 4 条 active PB。

排序优先级：

1. `running_5k`
2. `running_10k`
3. `running_half_marathon`
4. `running_marathon`
5. 其他 PB 类型

同类型按 `event_date DESC` 排序。

## 边界约束

禁止读取或返回：

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

所有 PB 摘要继续携带：

```json
{
  "detail_link": {
    "activity_id": "<activity_id>",
    "source": "career"
  }
}
```

AI Snapshot 未参与本任务。

## macOS / Windows 兼容性

- 测试使用 `sqlite3.connect(":memory:")`
- 不硬编码系统路径
- 不依赖大小写敏感文件系统
- 中文状态文案与 JSON 契约校验通过
- pywebview API envelope 保持不变

## 验证结果

已通过：

```bash
python3 -m pytest tests/test_career_overview_pb_summary.py
# 6 passed

python3 -m pytest tests/test_career_pb_api.py tests/test_career_timeline_pb_nodes.py
# 13 passed

python3 -m pytest tests/test_career_overview_timeline_races.py tests/test_career_races_api.py
# 15 passed

python3 -m pytest tests/test_career_api_skeleton.py tests/test_career_backend_schema.py
# 12 passed

python3 -m py_compile career_backend.py main.py profile_backend.py
# passed

python3 -m json.tool docs/js_api_contract.json
# passed
```

说明：pytest 期间存在 urllib3 / LibreSSL warning，为当前 macOS Python 环境提示，不影响本任务结果。

## 下一任务建议

建议进入：

`ACS-Phase3-01：Achievement Resolver 后端骨架`

建议边界：

- 先实现 Activity-backed 成就 Resolver
- 只支持 V1 基础成就类型
- 不做前端 UI
- 不生成 AI Snapshot
- 不读取 raw FIT、points、track_json 或本地路径
