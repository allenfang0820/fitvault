# RCV2-12 完成报告：Scope 感知的状态迁移、事件与候选闭环

完成日期：2026-07-14

## 1. 任务目标

扩展 Records Center V2 状态服务底座，使安全 V2 Evidence 可以按 `record_key + source_mode + scope_hash` 独立比较、候选、确认、拒绝、替代和事件留痕，同时保持 V1 跑步 PB 状态迁移结果不变。

## 2. 实施范围

已修改：

- `career_backend.py`
- `tests/test_career_record_v2_state.py`
- `docs/records_center_v2_rcv2_12_execution_prompt.md`
- `docs/records_center_v2_rcv2_12_completion_report.md`
- `docs/records_center_v2_rolling_contract_summary.md`
- `docs/运动生涯记录中心V2（多运动纪录）开发任务清单.md`

未修改：

- 未写真实数据库。
- 未接入真实 sport resolver 扫描。
- 未修改前端/API contract JSON。
- 未生成打包产物。
- 未迁移 V1 `apply_record_candidate_decision()` 默认路径。

## 3. 主要交付

- 新增 `compare_record_metric()`，支持 Registry 中 `lower_is_better` 与 `higher_is_better`。
- 新增 V2 active 查询：按 `record_key + source_mode + scope_hash` 查找当前 active。
- 新增 V2 event helper，写入 `record_key/scope_hash/scope_key/run_id/decision/reason_codes_json`。
- 新增 V2 candidate helper，候选 payload 只保存安全裁剪后的 Record Evidence。
- 新增 `apply_record_evidence_state()`：
  - `auto_confirm`：按同 Scope 比较并激活/替代。
  - `candidate`：创建或刷新候选。
  - `ignored`/非自动确认：只记录事件，不写 active。
- 新增 `decide_career_record_v2_candidate()`：
  - `confirm`：使用原始 Evidence 重新比较，不允许用户改值。
  - `reject`：候选置为 rejected，同证据后续不重复提示。
- V2 写 `career_pb_records` 时同步 legacy 兼容列和 V2 列，旧 V1 active index 通过 `sport_scope=scope_key` 规避不同 Scope 冲突。
- `validation_required`/`candidate_only` Registry 状态会把高置信 Evidence 降为候选，不自动写 active。
- analysis/model/unavailable 类型不进入状态机。

## 4. 验证结果

已执行：

```bash
.venv312/bin/python -m pytest tests/test_career_record_v2_state.py tests/test_career_record_state_migration.py -q
```

结果：

```text
13 passed
```

已执行：

```bash
.venv312/bin/python -m pytest tests/test_career_record_evidence.py tests/test_career_record_schema_migration.py tests/test_career_pb_resolver.py tests/test_career_pb_api.py -q
```

结果：

```text
38 passed, 8 subtests passed
```

已执行：

```bash
.venv312/bin/python -m py_compile career_backend.py
```

结果：通过。

已执行宽回归：

```bash
.venv312/bin/python -m pytest tests/test_career_record_v2_state.py tests/test_career_record_evidence.py tests/test_career_record_schema_migration.py tests/test_career_record_registry.py tests/test_career_pb_resolver.py tests/test_career_pb_api.py tests/test_career_record_state_migration.py tests/test_career_timeline_pb_nodes.py tests/test_records_center_v2_golden_fixtures.py -q
```

结果：

```text
80 passed, 21 subtests passed
```

## 5. Diff 复核结论

- 不同 Scope 不互相替代；同 Scope 最多一个 active。
- lower/higher/tie/未提升均有测试覆盖。
- candidate confirm/reject 闭环幂等；rejected 同证据不重复提示。
- validation_required 高置信 Evidence 不会自动 active。
- V1 running PB 状态迁移测试通过。
- RCV2-12 满足完成标准，可进入 RCV2-13。

