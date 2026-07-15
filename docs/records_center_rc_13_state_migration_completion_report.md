# RC-13 当前纪录、历史链与状态迁移完成报告

完成日期：2026-07-13

## 本轮目标

将 RC-10 的标准距离/成绩比较、RC-11 的置信度候选决策、RC-12 的 PB schema/event 表串成数据层状态迁移能力。

## 实现范围

- `career_backend.py` 新增 Records 状态迁移服务 `apply_record_candidate_decision(conn, decision)`。
- `career_backend.py` 新增 PB candidate 用户决策函数 `decide_career_pb_candidate(candidate_id, decision, conn=None)`。
- `tests/test_career_record_state_migration.py` 覆盖首条激活、更快替换、相同/更慢不刷新、候选幂等、确认、拒绝。

## 状态迁移契约

- `auto_confirm`：无 active 时激活；更快时旧 active superseded，新纪录 active；相同或更慢只写 `recalculated`。
- `candidate`：写入 `career_event_candidates(candidate_type='pb_record')`，不写入 current/history，同一 evidence key 幂等。
- `ignored`：不写入 PB current/history，只写审计事件。
- `confirm`：candidate 重新参与比较。
- `reject`：candidate 标为 rejected，不进入历史链。

## 验证

```bash
.venv312/bin/python -m pytest tests/test_career_record_state_migration.py -q
# 6 passed

.venv312/bin/python -m pytest tests/test_career_record_state_migration.py tests/test_career_record_schema_migration.py tests/test_career_record_registry.py tests/test_career_pb_resolver.py tests/test_career_pb_api.py tests/test_career_timeline_pb_nodes.py -q
# 50 passed, 13 subtests passed

.venv312/bin/python -m py_compile career_backend.py
# passed
```

## 复核结论

RC-13 已形成可还原 record evolution 的数据层闭环。后续 RC-14 可在 Activity 导入/更新后按受影响范围调用该服务。

