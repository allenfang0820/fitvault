# RC-17 当前纪录、详情与历史只读 API 完成报告

完成日期：2026-07-13

## 本轮目标

提供记录中心当前纪录、详情、历史只读能力，并保持现有 `get_career_pb()` 兼容。

## 实现范围

- `career_backend.py`
  - 扩展 `_build_pb_record()` 与 `get_career_pb()`，新增 `source_mode/source_mode_label/sport_scope/resolver_version/status/evidence_key/previous_record_id/detail_link.record_id`。
  - 新增 `get_career_pb_detail(record_id, conn=None)`。
  - 新增 `get_career_pb_history(pb_type, filters=None, conn=None)`。
- `main.py`
  - 新增 `Api.get_career_pb_detail(record_id)`。
  - 新增 `Api.get_career_pb_history(pb_type, filters=None)`。
- `docs/js_api_contract.json`
  - 更新 `get_career_pb` returns。
  - 新增 `get_career_pb_detail` 与 `get_career_pb_history`。
- `tests/test_career_pb_api.py`
  - 覆盖 current 扩展字段、detail/history、pywebview wrapper 和 contract 注册。

## 验证

```bash
.venv312/bin/python -m pytest tests/test_career_pb_api.py -q
# 10 passed

.venv312/bin/python -m pytest tests/test_career_pb_api.py tests/test_career_record_lifecycle.py tests/test_career_record_rebuild.py tests/test_career_record_incremental_evaluation.py tests/test_career_record_state_migration.py tests/test_career_record_schema_migration.py tests/test_career_record_registry.py tests/test_career_pb_resolver.py tests/test_career_timeline_pb_nodes.py -q
# 63 passed, 13 subtests passed

.venv312/bin/python -m py_compile career_backend.py main.py
.venv312/bin/python -m json.tool docs/js_api_contract.json
# passed
```

## 复核结论

RC-17 已完成前端记录中心所需的 current/detail/history 只读数据基础。后续 RC-18 进入候选决策、重建与新纪录事件 API。

