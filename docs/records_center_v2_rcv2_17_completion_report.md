# RCV2-17 骑行固定功率锚点正式纪录 Resolver 完成报告

日期：2026-07-15

## 任务目标

从活动功率曲线生成 5s、30s、1m、5m、20m、60m 固定功率锚点 `RecordEvidence`，并通过 V2 状态机完成正式纪录、候选、忽略、替代、tie 和回退闭环。

## 本次完成内容

- 新增 `CYCLING_POWER_RECORD_KEY_BY_DURATION`，冻结六个 duration 到 record key 的映射。
- 新增 `build_cycling_power_record_evidences()`，从 RCV2-16 curve anchors 生成安全 `RecordEvidence`。
- 新增 `apply_cycling_power_duration_records()`，默认 `dry_run=True`；显式 `dry_run=False` 时通过 `apply_record_evidence_state()` 写入 V2 状态机。
- Evidence 固定：
  - `source_mode=best_effort_duration`
  - `metric_name=power_w`
  - `metric_unit=watts`
  - `range_data=start_sec/end_sec/duration_sec`
  - `scope=sport_scope/indoor_scope/power_metric_scope`
- 修正 `_records_api_safe()`：
  - 继续禁止 `power_stream` 等 raw 字段键。
  - 允许 `power_stream_gap`、`missing_power_stream_sample` 等冻结 reason code 出现在安全质量原因中。

## 契约保持

- 不实现 1s 正式纪录。
- 不把 eFTP、CP、W′、MAP、PMax 或 W/kg 写成 PB。
- 默认不写库。
- 不修改前端。
- 不打包。
- 不触碰真实库。

## 触碰文件

- `career_backend.py`
- `tests/test_career_record_cycling_power_resolver.py`
- `docs/records_center_v2_rcv2_17_execution_prompt.md`

## 验证结果

### RCV2-17 定向

```bash
.venv312/bin/python -m pytest tests/test_career_record_cycling_power_resolver.py tests/test_career_record_cycling_power_curve.py tests/test_career_record_cycling_power_stream.py -q
```

结果：

```text
13 passed in 0.21s
```

### 状态机/API/PB 兼容

```bash
.venv312/bin/python -m pytest tests/test_career_record_v2_state.py tests/test_career_record_v2_rebuild.py tests/test_career_record_evidence.py tests/test_career_records_v2_api.py tests/test_career_pb_api.py -q
.venv312/bin/python -m py_compile career_backend.py
```

结果：

```text
34 passed, 5 subtests passed in 0.23s
```

### 加宽回归

```bash
.venv312/bin/python -m pytest tests/test_career_record_cycling_power_resolver.py tests/test_career_record_cycling_power_curve.py tests/test_career_record_cycling_power_stream.py tests/test_career_record_registry.py tests/test_career_record_schema_migration.py tests/test_career_record_evidence.py tests/test_career_record_v2_state.py tests/test_career_record_v2_rebuild.py tests/test_career_records_v2_api.py tests/test_records_center_v2_golden_fixtures.py tests/test_career_pb_api.py -q
```

结果：

```text
82 passed, 21 subtests passed in 0.38s
```

## 自适应差异复核

- 范围符合 RCV2-17：固定功率锚点 Evidence、状态机接入和测试。
- 写入仅发生在内存测试库，默认入口仍为 dry-run。
- 未写真实库。
- 未打包。
- 未发现阻塞问题。

## 后续任务提示

下一任务为 `RCV2-18 骑行 W/kg 门禁与整次活动纪录`。注意：W/kg 只有活动日期附近可靠历史体重时才能进入独立 Scope；无可靠历史体重时不得创建 W/kg fact 或候选。整次活动纪录可以实现距离、爬升、历时和机械功，但不得实现最快均速核心纪录。
