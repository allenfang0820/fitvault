# RC-12 PB schema migration 与 Record Event 表完成报告

完成日期：2026-07-13

## 本轮目标

实现 RC-05 冻结的数据结构，使 `career_pb_records` 能表达 evidence、source mode、历史链、决策状态与 resolver version，并新增 append-only `career_record_events` 事件表。

## 实现范围

- `career_backend.py`
  - `career_pb_records` 新建表结构加入：
    - `evidence_key`
    - `source_mode`
    - `sport_scope`
    - `previous_record_id`
    - `resolver_version`
    - `confirmed_at`
    - `rejected_at`
    - `invalidated_at`
    - `decision_source`
    - `decided_at`
  - 新增 `_ensure_career_pb_record_columns()`，为旧表幂等补列并回填 legacy `evidence_key`。
  - 新增 `career_record_events` append-only 表。
  - 新增 PB active scope、evidence version 与 record events 相关索引。
  - `ensure_career_schema()` 使用 savepoint 包裹迁移，失败时只回滚本轮 schema 变更。
  - 调整 legacy `_upsert_active_pb_record()` 顺序：先 supersede 旧 active，再插入新 active，以兼容 active scope 唯一索引。
- `tests/test_career_record_schema_migration.py`
  - 覆盖空库建表/索引。
  - 覆盖重复 migration 幂等。
  - 覆盖旧 `career_pb_records` 升级后仍可被 `get_career_pb()` 读取。
  - 覆盖部分旧 schema 只补缺失列。
  - 覆盖 migration 失败 rollback 且 legacy PB 行不丢失。

## 决策契约

- legacy 行默认：
  - `source_mode = 'activity_total'`
  - `sport_scope = 'default'`
  - `resolver_version = 'legacy'`
  - `decision_source = 'resolver'`
  - `evidence_key = 'activity_total:' || activity_id || ':' || pb_type || ':' || value`
- active 唯一性索引：`pb_type, source_mode, sport_scope WHERE status='active'`。
- evidence 幂等索引：`pb_type, activity_id, evidence_key, resolver_version`。

## 特别约束

- 本轮只做 schema/migration 与必要的旧 Resolver 兼容顺序调整。
- 未接入 RC-11 candidate decision 到写入链路。
- 未新增 UI 或 API 返回字段。
- 未写真实数据库。

## 验证

```bash
.venv312/bin/python -m pytest tests/test_career_record_schema_migration.py tests/test_career_pb_resolver.py tests/test_career_pb_api.py -q
# 23 passed

.venv312/bin/python -m pytest tests/test_career_record_schema_migration.py tests/test_career_record_registry.py tests/test_career_pb_resolver.py tests/test_career_pb_api.py tests/test_career_timeline_pb_nodes.py -q
# 44 passed, 13 subtests passed

.venv312/bin/python -m py_compile career_backend.py
# passed
```

## 复核结论

RC-12 diff 符合数据层任务边界：新增字段、事件表、索引和失败回滚测试均已覆盖；旧 active PB 读取保持兼容。

