# ACS-Phase2-03 PB Timeline 节点只读接入完成报告

## 任务范围

本任务将 PB Resolver 已生成的 active PB 记录接入 ACS Timeline Engine。

已完成：

- `get_career_timeline(filters=None, conn=None)` 支持 PB 节点
- `filters.type = "pb"` 时只返回 PB 节点
- `filters.type = "race"` 时只返回赛事节点
- `filters.type = "all"` 时合并赛事节点与 PB 节点
- 新增 PB timeline title 稳定映射
- 更新 `docs/js_api_contract.json`
- 新增 `tests/test_career_timeline_pb_nodes.py`

未实现：

- 前端 UI
- 骑行 PB Resolver 扩展
- Achievement Engine
- Timeline 成就 / 记忆节点
- AI Snapshot / AI 洞察

## 数据来源

PB Timeline 节点来自：

```text
career_pb_records WHERE status = 'active'
```

读取路径：

```text
get_career_timeline
  -> get_career_pb
  -> career_pb_records active records
  -> PB timeline nodes
```

本任务不重新计算 PB，也不修改 PB 写入规则。

## PB 节点结构

PB 节点包含：

- `id`
- `type = "pb"`
- `activity_id`
- `title`
- `pb_type`
- `sport`
- `date`
- `value`
- `value_unit`
- `improvement_sec`
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

## PB title 映射

- `running_5k` -> `5K PB`
- `running_10k` -> `10K PB`
- `running_half_marathon` -> `半马 PB`
- `running_marathon` -> `全马 PB`
- 未知类型 -> `PB`

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

AI Snapshot 未参与本任务。

## macOS / Windows 兼容性

- 测试使用 `sqlite3.connect(":memory:")`
- 不硬编码系统路径
- 不依赖大小写敏感文件系统
- 中文 title 映射通过测试
- API envelope 保持不变

## 验证结果

已通过：

```bash
python3 -m pytest tests/test_career_timeline_pb_nodes.py
# 6 passed

python3 -m pytest tests/test_career_pb_api.py tests/test_career_pb_resolver.py
# 15 passed

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

`ACS-Phase2-04：PB Overview 摘要接入`

建议边界：

- `get_career_overview` 增加 latest / representative PB 摘要
- 不重新计算 PB
- 不做前端 UI
- 不扩展骑行 PB Resolver
- 不生成 AI Snapshot
