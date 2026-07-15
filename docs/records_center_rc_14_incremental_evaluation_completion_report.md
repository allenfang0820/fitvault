# RC-14 Activity 导入后的增量评估完成报告

完成日期：2026-07-13

## 本轮目标

在 Activity 新增或关键字段更新后提供 PB 记录中心增量评估入口，使新 Activity 不必等待用户进入运动生涯页面才进入 Records Resolver。

## 实现范围

- `career_backend.py`
  - 新增 `_fetch_pb_resolver_activity_row(conn, activity_id)`，只读取单个 Activity 的 PB 白名单字段。
  - 新增 `evaluate_activity_record_increment(conn, activity_id)`，执行单 Activity 的 Performance Summary、Registry 匹配、置信度决策和 RC-13 状态迁移。
  - 新增 `evaluate_activity_record_increments(conn, activity_ids)`，支持多个 Activity id 去重后增量评估。
  - `refresh_career_derived_events(..., include_pb=True)` 增加兼容参数；默认保持旧行为，导入增量路径可跳过 legacy PB 全量。
- `main.py`
  - `_refresh_career_derived_events_safe(reason, activity_id=None)` 在有 activity_id 时先调用 PB 增量评估。
  - 单 FIT 同步写入成功后传入 `activity_id`。
  - 有 PB 增量结果时，后续全量 ACS refresh 跳过旧 PB 全量，避免 candidate 被 legacy PB Resolver 重新写成 active。
- `tests/test_career_record_incremental_evaluation.py`
  - 覆盖单 Activity 增量候选幂等。
  - 覆盖缺失/删除 Activity ignored。
  - 覆盖导入安全刷新调用增量入口并跳过 legacy PB 全量。

## 行为契约

- 增量入口只读取受影响 Activity。
- 增量入口复用 RC-09/10/11/13 的 summary、Registry、confidence 和状态迁移服务。
- 重复导入同一 evidence 不重复 PB、candidate 或 candidate_created event。
- 导入后的 ACS refresh 仍保留 Race/Achievement 全量兼容刷新；PB 由增量入口负责。
- 增量 Resolver 失败由 `_refresh_career_derived_events_safe()` 捕获，不阻塞 Activity 基础事实保存。

## 验证

```bash
.venv312/bin/python -m pytest tests/test_career_record_incremental_evaluation.py -q
# 3 passed

.venv312/bin/python -m pytest tests/test_career_record_incremental_evaluation.py tests/test_career_record_state_migration.py tests/test_career_record_schema_migration.py tests/test_career_record_registry.py tests/test_career_pb_resolver.py tests/test_career_pb_api.py tests/test_career_timeline_pb_nodes.py -q
# 53 passed, 13 subtests passed

.venv312/bin/python -m py_compile career_backend.py main.py
# passed
```

## 复核结论

RC-14 已完成 Activity 写入后的 PB 增量入口与导入触发点接入。后续 RC-15 可基于同一状态迁移服务实现全量 dry-run、重建和 resolver version 管理。

