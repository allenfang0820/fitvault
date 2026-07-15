# RCV2-13 完成报告：增量分发、删除回退、重建与回滚闭环

完成日期：2026-07-14

## 1. 任务目标

建立 Records Center V2 通用增量/重建框架，让 Activity 变化能够按 sport 分发到可用 definitions，并提供 Activity 删除/修改导致的 record/cache/route 失效、同 Scope fallback 回退、rebuild dry-run/apply 摘要和事务回滚能力。

## 2. 实施范围

已修改：

- `career_backend.py`
- `tests/test_career_record_v2_rebuild.py`
- `docs/records_center_v2_rcv2_13_execution_prompt.md`
- `docs/records_center_v2_rcv2_13_completion_report.md`
- `docs/records_center_v2_rolling_contract_summary.md`
- `docs/运动生涯记录中心V2（多运动纪录）开发任务清单.md`

未修改：

- 未写真实数据库。
- 未实现具体骑行/徒步/游泳/越野算法。
- 未修改前端/API contract JSON。
- 未生成打包产物。
- 未改变 V1 rebuild/lifecycle/incremental 路径。

## 3. 主要交付

- 新增 Activity sport 归一与 V2 dispatch plan：
  - `plan_activity_record_v2_dispatch()`
  - `plan_career_records_v2_rebuild()`
  - `rebuild_career_records_v2()`
- 默认只分发 `available` definitions；`candidate_only/validation_required` 不自动 apply。
- 修复 dispatch 归一顺序：`trail_running` 不再被 `RUNNING_SPORT_TYPES` 误归为 `running`。
- 新增 Activity 失效闭环：
  - `invalidate_career_record_state_for_activity()`
  - 失效相关 active V2 record。
  - 失效同 Activity curve cache。
  - 失效 route signatures 和 route matches。
  - dry-run 预览会列出 records/cache/route/fallback。
  - apply 使用 savepoint，失败回滚。
- 新增同 Scope fallback：
  - active 失效后，从同 `record_key/source_mode/scope_hash` 的 superseded 历史中按比较方向选择有效 Activity fallback。
- V2 rebuild plan 输出：
  - `run_id`
  - `by_sport`
  - `by_family`
  - `by_reason`
  - `summary`
  - `items`
  - `cancelled`
- V2 rebuild apply 当前只提供事务壳；具体 sport evidence 生成留给 RCV2-15+。

## 4. 验证结果

已执行：

```bash
.venv312/bin/python -m pytest tests/test_career_record_v2_rebuild.py tests/test_career_record_v2_state.py -q
```

结果：

```text
12 passed
```

已执行：

```bash
.venv312/bin/python -m pytest tests/test_career_record_rebuild.py tests/test_career_record_lifecycle.py tests/test_career_record_incremental_evaluation.py -q
```

结果：

```text
14 passed
```

已执行：

```bash
.venv312/bin/python -m py_compile career_backend.py
```

结果：通过。

已执行宽回归：

```bash
.venv312/bin/python -m pytest tests/test_career_record_v2_rebuild.py tests/test_career_record_v2_state.py tests/test_career_record_evidence.py tests/test_career_record_schema_migration.py tests/test_career_record_registry.py tests/test_career_pb_resolver.py tests/test_career_pb_api.py tests/test_career_record_state_migration.py tests/test_career_record_rebuild.py tests/test_career_record_lifecycle.py tests/test_career_record_incremental_evaluation.py tests/test_career_timeline_pb_nodes.py tests/test_records_center_v2_golden_fixtures.py -q
```

结果：

```text
99 passed, 21 subtests passed
```

## 5. Diff 复核结论

- dry-run 不写库。
- apply 使用 savepoint，失败可回滚。
- Activity 失效会同时处理 record/cache/route。
- fallback 不跨 Scope。
- 越野不会误归为跑步。
- V1 rebuild/lifecycle/incremental 测试无回归。
- RCV2-13 满足完成标准，可进入 RCV2-14。

