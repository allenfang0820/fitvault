# ACS-Phase7-02 Career Snapshot 持久化与只读调试 API 完成报告

## 任务范围

本任务在 Phase7-01 的 `build_career_snapshot(conn=None)` 白名单骨架基础上，新增 Career Snapshot 的后端受控持久化与 pywebview 只读调试 API。

已完成：

- 新增 `save_career_snapshot(conn=None)`
- 新增 `get_latest_career_snapshot(conn=None)`
- 新增 pywebview 只读 API `get_latest_career_snapshot`
- 更新 `docs/js_api_contract.json`
- 新增 Snapshot 持久化测试

未实现：

- 不暴露 `save_career_snapshot` pywebview API
- 不新增前端按钮
- 不调用 LLM
- 不生成 AI 总结

## 修改文件

- `career_backend.py`
  - 新增 `CAREER_SNAPSHOT_FORBIDDEN_KEYS`
  - 新增 `_snapshot_has_forbidden_key`
  - 新增 `_sanitize_saved_career_snapshot`
  - 新增 `save_career_snapshot`
  - 新增 `get_latest_career_snapshot`
- `main.py`
  - 新增 `Api.get_latest_career_snapshot`
- `docs/js_api_contract.json`
  - 新增只读 API `get_latest_career_snapshot`
- `tests/test_career_snapshot_persistence.py`
  - 新增持久化、读取、脏数据防护、API 契约测试
- `docs/acs_phase7_02_career_snapshot_persistence_completion_report.md`

## 新增后端函数

### save_career_snapshot

```python
save_career_snapshot(conn=None) -> dict
```

行为：

- 调用 `build_career_snapshot(conn=db)` 生成白名单 Snapshot。
- 写入 `career_snapshots` 表。
- 使用固定 id：`career_snapshot:latest`。
- 使用 `snapshot_type='career'`。
- `source_version` 使用 Snapshot 的 `snapshot_version`。
- 使用 upsert，重复保存只更新 latest，不新增多条。
- 返回 `{snapshot, saved, saved_at, source_version, status}`。

### get_latest_career_snapshot

```python
get_latest_career_snapshot(conn=None) -> dict
```

行为：

- 只读取 `career_snapshot:latest`。
- 不自动生成 Snapshot。
- 不调用 LLM。
- 空状态返回：

```json
{
  "snapshot": null,
  "status": {
    "schema_ready": true,
    "data_ready": false,
    "message": "暂无 Career Snapshot"
  }
}
```

存在已保存 Snapshot 时返回：

```json
{
  "snapshot": {},
  "saved_at": "...",
  "source_version": "acs.v1",
  "status": {
    "schema_ready": true,
    "data_ready": true,
    "message": "Career Snapshot 已保存"
  }
}
```

## 新增 pywebview 只读 API

```python
Api.get_latest_career_snapshot()
```

说明：

- 只读调试 API。
- 返回 `_api_success(career_backend.get_latest_career_snapshot())`。
- 不自动生成 Snapshot。
- 不调用 LLM。
- 不暴露保存接口。

## 为什么不暴露保存 API

`save_career_snapshot` 是后端受控缓存动作，不应由前端任意触发。

原因：

- Snapshot 是 AI 上下文缓存，不是普通用户编辑数据。
- 保存动作未来应由明确的后端流程控制，例如生成洞察前的受控刷新。
- 只读 API 足够用于本地调试与后续开发验收。
- 避免前端在页面刷新、切 tab 或调试误点时反复写 DB。

## 持久化策略

- 表：`career_snapshots`
- id：`career_snapshot:latest`
- snapshot_type：`career`
- content_json：完整白名单 Snapshot JSON
- source_version：`acs.v1`
- generated_at：Snapshot 生成时间
- created_at：本次保存时间，upsert 时同步更新

重复保存只保留一条 latest 记录。

## 脏数据防护策略

读取已保存 Snapshot 时，不直接透出 `content_json`。

`get_latest_career_snapshot` 会调用 `_sanitize_saved_career_snapshot` 重新按 Snapshot 白名单组装结构。

即使历史脏数据包含：

- `storage_ref`
- `path`
- `thumbnail_url`
- `detail_link`
- points / points_json
- track_json
- file_path
- SQLite schema

也不会原样返回。

## forbidden 字段确认

持久化与读取结果不包含：

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

## 不调用 LLM 确认

- `save_career_snapshot` 不调用 `call_llm`。
- `get_latest_career_snapshot` 不调用 `call_llm`。
- `Api.get_latest_career_snapshot` 不调用 LLM。
- 本任务没有新增 AI 前端按钮。
- 本任务没有新增 `generate_career_insight`。

## macOS / Windows 兼容性

- 未新增平台路径逻辑。
- 未读写本地媒体文件。
- 未返回本地绝对路径。
- SQLite 写入使用参数化 SQL。
- Snapshot JSON 使用 UTF-8 / `ensure_ascii=False`。
- pywebview API envelope 保持 `{ok, code, msg, data, traceId}`。

## 验证结果

已通过：

```bash
python3 -m pytest tests/test_career_snapshot_persistence.py
python3 -m pytest tests/test_career_snapshot_persistence.py tests/test_career_snapshot_builder.py tests/test_career_memory_phase6_closure_docs.py tests/test_career_overview_api_closure.py tests/test_career_timeline_engine_closure.py
python3 -m py_compile career_backend.py main.py profile_backend.py
python3 -m json.tool docs/js_api_contract.json >/dev/null
```

结果：

- 新增持久化测试：9 passed。
- 相关 ACS 回归：29 passed。
- Python 编译：通过。
- JS API 契约 JSON：合法。

说明：当前 macOS Python 环境仍有 urllib3 / LibreSSL warning，不影响测试结果。

## 下一个任务建议

建议进入 `ACS-Phase7-03：Career Insight 后端生成 API 骨架（无 LLM 或可降级空实现）`。

建议边界：

- 可以新增 `generate_career_insight` 后端 API 骨架，但先不接真实 LLM。
- 只读取已保存 Snapshot 或受控生成 Snapshot。
- 输出稳定空 insight / status，用于前端和测试接线。
- 继续禁止 raw FIT、points、track_json、file_path、storage_ref、SQLite schema 进入 AI。
