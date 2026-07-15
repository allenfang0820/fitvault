# RC-16 删除回退、幂等、并发与事务闭环完成报告

完成日期：2026-07-13

## 本轮目标

补齐 Records 数据生命周期一致性：来源 Activity 删除、失效或关键成绩变化后，active 纪录可被 invalidated，并从有效历史中安全回退。

## 实现范围

- `career_backend.py`
  - 新增 `_current_record_decision_for_activity()`。
  - 新增 `_active_record_invalid_reason()`。
  - 新增 `_valid_fallback_record()`。
  - 新增 `repair_record_lifecycle(conn, record_key=None)`。
- `tests/test_career_record_lifecycle.py`
  - 覆盖 active 来源 Activity 删除后 invalidated，并提升最佳有效 superseded。
  - 覆盖 Activity evidence 改变后 invalidated，且不误报为新纪录。
  - 覆盖重复 repair 不重复 invalidated event。
  - 覆盖 repair 失败 savepoint rollback，active 状态保持。

## 行为契约

- records-v1 active 行失效条件：
  - Activity 不存在或软删除。
  - 当前 Activity 重新计算后不再命中 record。
  - 当前 record_key 改变。
  - 当前 evidence_key 改变。
- legacy 行为：
  - 仅按 Activity 缺失/删除判断失效，避免误伤旧数据。
- fallback：
  - 在同 `pb_type/source_mode/sport_scope` 内选择有效 superseded 中最快记录。
  - 回退事件为 `activated_from_rebuild`，不作为新纪录庆祝事件。
- repair 全程使用 savepoint，失败回滚本次状态变化。

## 验证

```bash
.venv312/bin/python -m pytest tests/test_career_record_lifecycle.py -q
# 4 passed

.venv312/bin/python -m pytest tests/test_career_record_lifecycle.py tests/test_career_record_rebuild.py tests/test_career_record_incremental_evaluation.py tests/test_career_record_state_migration.py tests/test_career_record_schema_migration.py tests/test_career_record_registry.py tests/test_career_pb_resolver.py tests/test_career_pb_api.py tests/test_career_timeline_pb_nodes.py -q
# 61 passed, 13 subtests passed

.venv312/bin/python -m py_compile career_backend.py main.py
# passed
```

## 复核结论

RC-16 已完成 Milestone B 的核心数据闭环：候选、active、superseded、invalidated、fallback 与 rebuild 均有后端测试覆盖。后续 RC-17 进入只读 API 层。

