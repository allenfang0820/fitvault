# RCV2-18 骑行 W/kg 门禁与整次活动纪录完成报告

日期：2026-07-15

## 任务目标

实现骑行整次活动纪录 resolver：最长距离、最大爬升、最长 elapsed time、最大机械功；同时冻结 W/kg 门禁，确保无可靠历史体重时不创建 W/kg fact、candidate 或 active record。

## 本次完成内容

- 新增 `resolve_cycling_wkg_gate()`：
  - 无 activity date 或无可靠历史体重时返回 `historical_weight_missing`。
  - 只在活动日期附近存在 25-250kg 的历史体重时返回 available。
  - 即使 available，也只返回 gate，不创建 W/kg evidence，因为当前 Registry 未开放 W/kg active record。
- 新增 `build_cycling_activity_total_record_evidences()`：
  - 构造 `cycling_longest_distance`、`cycling_max_ascent`、`cycling_longest_elapsed_time`、`cycling_max_work` evidence。
  - 室内无距离/爬升时 skipped 为 `not_applicable_indoor_metric_missing`，不填 0。
  - e-bike skipped 为 `ebike_scope_excluded`。
  - 机械功优先从 RCV2-15 功率流积分；无功率流时可读可信汇总并降级。
- 新增 `apply_cycling_activity_total_records()`：
  - 默认 `dry_run=True`。
  - 显式 `dry_run=False` 时通过 V2 状态机 apply。
  - `cycling_max_work` 因 Registry `validation_required` 被状态机降为候选，不进入 active。
- 新增 `tests/test_career_record_cycling_activity_total.py`：
  - dry-run evidence。
  - active 替代。
  - work candidate。
  - 室内 not applicable。
  - W/kg missing/available gate。
  - e-bike 排除。

## 契约保持

- 不实现最快均速核心纪录。
- 不使用当前体重回填历史。
- 无可靠历史体重时不创建 W/kg fact、candidate 或 active。
- 不修改前端。
- 不打包。
- 不触碰真实库。

## 触碰文件

- `career_backend.py`
- `tests/test_career_record_cycling_activity_total.py`
- `docs/records_center_v2_rcv2_18_execution_prompt.md`

## 验证结果

### RCV2-18 定向

```bash
.venv312/bin/python -m pytest tests/test_career_record_cycling_activity_total.py tests/test_career_record_cycling_power_resolver.py -q
```

结果：

```text
10 passed in 0.22s
```

### 状态机/API/PB 兼容

```bash
.venv312/bin/python -m pytest tests/test_career_record_v2_state.py tests/test_career_records_v2_api.py tests/test_career_pb_api.py -q
.venv312/bin/python -m py_compile career_backend.py
```

结果：

```text
23 passed in 0.16s
```

### 加宽回归

```bash
.venv312/bin/python -m pytest tests/test_career_record_cycling_activity_total.py tests/test_career_record_cycling_power_resolver.py tests/test_career_record_cycling_power_curve.py tests/test_career_record_cycling_power_stream.py tests/test_career_record_registry.py tests/test_career_record_schema_migration.py tests/test_career_record_evidence.py tests/test_career_record_v2_state.py tests/test_career_record_v2_rebuild.py tests/test_career_records_v2_api.py tests/test_records_center_v2_golden_fixtures.py tests/test_career_pb_api.py -q
```

结果：

```text
87 passed, 21 subtests passed in 0.41s
```

## 自适应差异复核

- 范围符合 RCV2-18：W/kg gate 与骑行整次活动纪录。
- 默认 dry-run。
- 未写真实库。
- 未改前端。
- 未打包。
- 未发现阻塞问题。

## 后续任务提示

下一任务为 `RCV2-19 骑行 Catalog、API、Curve ViewModel 与测试闭环`。重点是只读表面：Catalog 分组、当前/历史/详情、PDC ViewModel、无功率/部分功率/W/kg 不可用状态和安全测试；前端仍不得读取 Activity raw data。
