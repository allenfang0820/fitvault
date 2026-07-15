# RCV2-11 完成报告：通用 Record Evidence 与 source_mode 扩展

完成日期：2026-07-14

## 1. 任务目标

建立安全、可序列化、可 fingerprint 的 V2 Record Evidence 底座，使 `activity_total`、`best_effort_duration`、`best_effort_distance`、`route_total`、`segment` 五类 evidence 能进入后续质量评分和状态机。

## 2. 实施范围

已修改：

- `career_backend.py`
- `tests/test_career_record_evidence.py`
- `docs/records_center_v2_rcv2_11_execution_prompt.md`
- `docs/records_center_v2_rcv2_11_completion_report.md`
- `docs/records_center_v2_rolling_contract_summary.md`
- `docs/运动生涯记录中心V2（多运动纪录）开发任务清单.md`

未修改：

- 未写真实数据库。
- 未修改前端。
- 未修改 API contract JSON。
- 未生成打包产物。
- 未改变 V1 running PB resolver 的旧 evidence key 和写入行为。

## 3. 主要交付

- 新增 `RecordEvidence` 模型，提供只读 payload、`evidence_key`、`evidence_fingerprint`。
- 新增 `build_record_evidence()` 纯 helper。
- 新增 `canonicalize_record_range()` 与 `canonicalize_record_quality()`。
- 新增通用 `source_mode` 校验和 scope key 派生。
- Evidence key 按冻结格式生成：

```text
evidence:v2:{record_key}:{activity_id}:{source_mode}:{scope_hash}:{range_hash}:{metric_hash}:{rule_version}
```

- Evidence fingerprint 使用 canonical JSON 生成，输入顺序变化不影响 key。
- Evidence 严格绑定 Registry：
  - 未知 `record_key` 被拒绝。
  - `source_mode` 必须与 RecordDefinition 一致。
  - `sport`、`metric_name`、`metric_unit` 必须与 RecordDefinition 一致。
- `best_effort_duration`、`best_effort_distance`、`segment` 必须携带 Activity 内 range。
- `route_total` 必须携带 `scope.route_key`。
- `segment` 必须携带 `segment_key`。
- Evidence 安全校验拒绝 raw FIT、完整轨迹、原始功率流、本地路径、真实 GPS 点、未脱敏设备标识、账号/token、体重历史等敏感字段。

## 4. 验证结果

已执行：

```bash
.venv312/bin/python -m pytest tests/test_career_record_evidence.py tests/test_career_record_registry.py -q
```

结果：

```text
25 passed, 18 subtests passed
```

已执行：

```bash
.venv312/bin/python -m pytest tests/test_career_pb_resolver.py tests/test_career_pb_api.py tests/test_career_record_state_migration.py -q
```

结果：

```text
26 passed
```

已执行：

```bash
.venv312/bin/python -m py_compile career_backend.py
```

结果：通过。

已执行宽回归：

```bash
.venv312/bin/python -m pytest tests/test_career_record_evidence.py tests/test_career_record_schema_migration.py tests/test_career_record_registry.py tests/test_career_pb_resolver.py tests/test_career_pb_api.py tests/test_career_record_state_migration.py tests/test_records_center_v2_golden_fixtures.py -q
```

结果：

```text
67 passed, 21 subtests passed
```

## 5. Diff 复核结论

- Evidence helper 是纯构建器，不写库、不切换 active、不创建候选。
- V1 `record_evidence_key()` 兼容测试通过。
- 未发现 Evidence payload 放行 raw stream/path/GPS/device/body-weight 的路径。
- RCV2-11 满足完成标准，可进入 RCV2-12。

