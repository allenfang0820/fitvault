# RC-15 全量 dry-run、重建与 Resolver 版本化完成报告

完成日期：2026-07-13

## 本轮目标

提供安全的 Records 全量 dry-run 与 rebuild 服务，让规则升级和历史重算可以先预览、再事务化应用，并保留失败恢复能力。

## 实现范围

- `career_backend.py`
  - 新增 `plan_records_rebuild(conn, resolver_version=...)`。
  - 新增 `rebuild_records(conn, dry_run=True, resolver_version=...)`。
  - 新增 `_plan_record_rebuild_item()`，复用 Performance Summary、Registry、confidence 和当前 active 比较。
  - 新增 `_RECORDS_REBUILD_IN_PROGRESS` 进程内防重入 guard。
- `tests/test_career_record_rebuild.py`
  - 覆盖 dry-run 版本化计划且不写 PB/candidate。
  - 覆盖 apply 同 evidence 幂等，不重复 candidate_created event。
  - 覆盖 apply 失败 rollback，旧 active 保持不变。
  - 覆盖重入拒绝。

## 行为契约

- dry-run 返回：
  - `run_id`
  - `resolver_version`
  - `processed`
  - `progress`
  - `summary`
  - `items`
- action 分类包含：`new/replace/candidate/unchanged/ignored`。
- apply 不清空旧纪录；逐项调用 RC-13 状态迁移服务。
- apply 使用 savepoint；失败时回滚本次应用，旧 active 保持。
- 同一 evidence 的重复 rebuild 不重复 candidate 或 candidate_created event。

## 验证

```bash
.venv312/bin/python -m pytest tests/test_career_record_rebuild.py -q
# 4 passed

.venv312/bin/python -m pytest tests/test_career_record_rebuild.py tests/test_career_record_incremental_evaluation.py tests/test_career_record_state_migration.py tests/test_career_record_schema_migration.py tests/test_career_record_registry.py tests/test_career_pb_resolver.py tests/test_career_pb_api.py tests/test_career_timeline_pb_nodes.py -q
# 57 passed, 13 subtests passed

.venv312/bin/python -m py_compile career_backend.py main.py
# passed
```

## 复核结论

RC-15 已提供可审计、可预览、可失败恢复的全量 rebuild 服务。后续 RC-16 需要补齐 Activity 删除/修改、invalidated 回退、并发一致性等生命周期闭环。

