# ACS-Phase7-03 Career Insight 后端生成 API 骨架完成报告

## 任务范围

本任务新增 Career Insight 后端 API 骨架，但仍不接真实 LLM。

已完成：

- 新增 `generate_career_insight(payload=None, conn=None)`
- 新增 fallback insight 构建逻辑
- 新增 pywebview API `generate_career_insight`
- 更新 `docs/js_api_contract.json`
- 新增 API 骨架测试

未实现：

- 不调用 LLM
- 不调用 `llm_backend`
- 不新增前端按钮
- 不新增正式 Career Insight 页面
- 不写 canonical 事实表

## 修改文件

- `career_backend.py`
  - 新增 `_career_insight_highlights`
  - 新增 `_build_fallback_career_insight`
  - 新增 `generate_career_insight`
- `main.py`
  - 新增 `Api.generate_career_insight`
- `docs/js_api_contract.json`
  - 新增 `generate_career_insight` 契约
- `tests/test_career_insight_api_skeleton.py`
  - 新增 Insight API 骨架测试
- `docs/acs_phase7_03_career_insight_api_skeleton_completion_report.md`

## 新 API

### 后端函数

```python
generate_career_insight(payload=None, conn=None) -> dict
```

当前 payload 仅支持：

```json
{
  "refresh_snapshot": false
}
```

未知字段会返回参数校验错误。

### pywebview API

```python
Api.generate_career_insight(payload=None)
```

返回统一 envelope：

```json
{
  "ok": true,
  "code": 0,
  "msg": "ok",
  "data": {
    "insight": {},
    "snapshot_status": {},
    "status": {}
  },
  "traceId": "..."
}
```

## fallback insight 结构

当前返回本地降级洞察：

```json
{
  "insight": {
    "mode": "fallback",
    "title": "运动生涯洞察准备中",
    "summary": "已生成安全的运动生涯快照，AI 洞察将在后续版本开启。",
    "highlights": [
      "累计活动 1 次",
      "已记录赛事 1 场",
      "已沉淀 PB 1 项"
    ],
    "next_steps": [
      "继续完善赛事、PB、成就与记忆数据",
      "后续版本将基于 Career Snapshot 生成长期总结"
    ],
    "disclaimer": "当前为本地降级洞察，不调用 AI。"
  },
  "snapshot_status": {
    "available": true,
    "source": "generated",
    "snapshot_version": "acs.v1"
  },
  "status": {
    "schema_ready": true,
    "data_ready": true,
    "message": "Career Insight 降级结果已生成"
  }
}
```

`highlights` 只来自 Snapshot `summary` 安全聚合字段：

- `activity_count`
- `race_count`
- `pb_count`
- `achievement_count`
- `memory_count`
- `covered_city_count`
- `total_distance_km`

不使用 story 文本、媒体引用、轨迹点或原始活动数据。

## Snapshot 使用策略

- `refresh_snapshot=true`
  - 调用 `save_career_snapshot(conn=db)`
  - 刷新并保存 latest Snapshot
  - `snapshot_status.source = "refreshed"`
- `refresh_snapshot=false`
  - 优先调用 `get_latest_career_snapshot(conn=db)`
  - 若没有已保存 Snapshot，再调用 `save_career_snapshot(conn=db)`
  - 已存在时 `source = "saved"`
  - 自动生成时 `source = "generated"`

写入仅限 `career_snapshots`，且只保存白名单 Snapshot。

## 不调用 LLM 确认

- `generate_career_insight` 不调用 `call_llm`。
- `generate_career_insight` 不调用 `llm_backend`。
- `Api.generate_career_insight` 只调用 `career_backend.generate_career_insight`。
- 本任务未新增前端 AI 按钮。
- 当前 insight 结果为本地 fallback，不是 AI 生成内容。

## forbidden 字段确认

Insight 输出不包含：

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
- 本地绝对路径

## canonical 表不写入确认

`generate_career_insight` 不写入：

- `career_race_events`
- `career_pb_records`
- `career_achievement_events`
- `career_memory_items`

可能写入：

- `career_snapshots`

写入原因：无 Snapshot 或显式刷新时，受控生成并保存白名单 Snapshot。

## macOS / Windows 兼容性

- 未新增平台路径逻辑。
- 未读写本地媒体文件。
- 未返回本地绝对路径。
- SQLite 写入仍通过 Snapshot 持久化函数完成。
- 中文 fallback 文案保持 UTF-8。
- pywebview API envelope 保持 `{ok, code, msg, data, traceId}`。

## 验证结果

已通过：

```bash
python3 -m pytest tests/test_career_insight_api_skeleton.py
python3 -m pytest tests/test_career_insight_api_skeleton.py tests/test_career_snapshot_persistence.py tests/test_career_snapshot_builder.py tests/test_career_memory_phase6_closure_docs.py tests/test_career_overview_api_closure.py tests/test_career_timeline_engine_closure.py
python3 -m py_compile career_backend.py main.py profile_backend.py
python3 -m json.tool docs/js_api_contract.json >/dev/null
```

结果：

- 新增 API 骨架测试：11 passed。
- 相关 ACS 回归：40 passed。
- Python 编译：通过。
- JS API 契约 JSON：合法。

说明：当前 macOS Python 环境仍有 urllib3 / LibreSSL warning，不影响测试结果。

## 下一个任务建议

建议进入 `ACS-Phase7-04：Career Insight 前端只读占位渲染`。

建议边界：

- 前端可以调用 `generate_career_insight` 并展示 fallback 结果。
- 不新增真实 AI 调用。
- 不新增 prompt 拼接。
- 不把前端数据传入 AI。
- 不展示 Snapshot 原文或调试 JSON。
