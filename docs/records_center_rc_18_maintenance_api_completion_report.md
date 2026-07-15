# RC-18 候选决策、重建与新纪录事件 API 完成报告

完成日期：2026-07-13

## 本轮目标

提供记录中心候选确认/拒绝、全量 rebuild、record events 查询 API，使前端无需直接操作 SQLite 或猜测状态迁移。

## 实现范围

- `career_backend.py`
  - `pb_record` candidate 类型增加中文标签“纪录候选”。
  - 新增 `get_career_record_events(filters=None, conn=None)`。
- `main.py`
  - 新增 `Api.decide_career_pb_candidate(payload)`。
  - 新增 `Api.rebuild_career_pb_records(payload=None)`。
  - 新增 `Api.get_career_record_events(filters=None)`。
- `docs/js_api_contract.json`
  - 新增 `decide_career_pb_candidate`，`readonly=false`，`high_risk=true`。
  - 新增 `rebuild_career_pb_records`，`readonly=false`，`high_risk=true`。
  - 新增 `get_career_record_events`，`readonly=true`，`high_risk=false`。
- `tests/test_career_record_maintenance_api.py`
  - 覆盖 candidate confirm/reject wrapper。
  - 覆盖 rejected 后非法再次 confirm 返回 validation。
  - 覆盖 rebuild dry-run/apply wrapper。
  - 覆盖 record events 查询。
  - 覆盖 JS API contract readonly/high_risk 属性。

## 行为契约

- PB candidate decision 只接受 `confirm/reject`。
- 非法 decision、缺 candidate id、已拒绝后再次确认均返回 validation error。
- rebuild 默认 `dry_run=true`；`dry_run=false` 时事务化应用并提交，失败 rollback。
- record events 只读查询支持 `record_id/pb_type/record_key/event_type` 筛选。
- 所有接口继续禁止 raw FIT、points、track_json、file_path、本地路径和 SQLite schema。

## 验证

```bash
.venv312/bin/python -m pytest tests/test_career_record_maintenance_api.py -q
# 3 passed

.venv312/bin/python -m pytest tests/test_career_record_maintenance_api.py tests/test_career_pb_api.py tests/test_career_record_lifecycle.py tests/test_career_record_rebuild.py tests/test_career_record_incremental_evaluation.py tests/test_career_record_state_migration.py tests/test_career_record_schema_migration.py tests/test_career_record_registry.py tests/test_career_pb_resolver.py tests/test_career_timeline_pb_nodes.py -q
# 66 passed, 13 subtests passed

.venv312/bin/python -m py_compile career_backend.py main.py
.venv312/bin/python -m json.tool docs/js_api_contract.json
# passed
```

## 复核结论

RC-18 已完成候选与维护 API。后续 RC-19 进入前端“记录”导航与当前纪录页面。

