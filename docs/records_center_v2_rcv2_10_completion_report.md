# RCV2-10 完成报告：Scope schema migration 与 Curve Cache 基础设施

完成日期：2026-07-14

## 1. 任务目标

实现 V2 结构化 Scope、active/evidence 唯一索引、Curve Cache/Route 派生表、只读 migration dry-run、失败回滚与安全边界测试，同时保持 V1 `career_pb_records`、`career_record_events`、候选和旧 PB API 兼容。

## 2. 实施范围

已修改：

- `career_backend.py`
- `tests/test_career_record_schema_migration.py`
- `docs/records_center_v2_rcv2_10_execution_prompt.md`
- `docs/records_center_v2_rcv2_10_completion_report.md`
- `docs/records_center_v2_rolling_contract_summary.md`
- `docs/运动生涯记录中心V2（多运动纪录）开发任务清单.md`

未修改：

- 未修改真实数据库。
- 未修改前端。
- 未修改 `docs/js_api_contract.json`。
- 未生成、签名、公证或替换任何打包产物。

## 3. 主要交付

### 3.1 Schema migration

- `CAREER_SCHEMA_VERSION` 提升到 `2026-07-14.records-v2.10`。
- `career_pb_records` 新增并补列：
  - `record_key`
  - `record_family`
  - `scope_json`
  - `scope_key`
  - `scope_hash`
  - `range_json`
  - `quality_json`
  - `metric_value_num`
  - `metric_name`
  - `catalog_state`
  - `rule_version`
- `career_record_events` 新增并补列：
  - `record_key`
  - `scope_hash`
  - `scope_key`
  - `run_id`
  - `decision`
  - `reason_codes_json`
- 新增派生表：
  - `career_record_curve_cache`
  - `career_route_signatures`
  - `career_route_matches`

### 3.2 Scope 与 legacy 回填

- 新增结构化 Scope canonicalization 与 `scope:v2:sha256:*` hash。
- legacy V1 PB rows 回填 `record_key/pb_type`、`record_family`、`scope_json`、`scope_key`、`scope_hash`、`metric_value_num`、`metric_name`、`catalog_state`、`rule_version`、`quality_json`。
- `pb_type` 和 V1 `sport_scope` 保留，旧 API 仍可读取。

### 3.3 索引与冲突审计

- 保留 V1 active/evidence 索引。
- 新增 V2 active 唯一索引：`record_key + source_mode + scope_hash WHERE status='active'`。
- 新增 V2 evidence 索引：`record_key + activity_id + evidence_key + resolver_version`。
- 新增事件、候选、curve cache、route signature、route match 索引。
- 新增 `plan_career_records_v2_schema_migration(conn)` 只读计划函数，输出缺失表/列/索引、legacy 回填数量与 active scope 冲突。

### 3.4 Curve Cache 基础设施

- 新增允许的 curve type：
  - `cycling_power_duration_curve`
  - `trail_pace_curve`
  - `trail_gap_curve`
  - `pool_swim_pace_curve`
- 新增 `compute_career_record_curve_input_fingerprint()`，只使用安全摘要生成 `sha256:*` fingerprint。
- 新增 `save_career_record_curve_cache()`、`get_career_record_curve_cache()`、`invalidate_career_record_curve_cache()`、`cleanup_career_record_curve_cache_versions()`。
- Cache 写入前拒绝 raw FIT、完整轨迹、原始功率流、本地路径、真实 GPS 点、体重历史等敏感字段。
- Curve Cache 仍是派生缓存，不参与正式纪录 active 状态迁移。

## 4. 验证结果

已执行：

```bash
.venv312/bin/python -m pytest tests/test_career_record_schema_migration.py tests/test_career_record_registry.py -q
```

结果：

```text
31 passed, 16 subtests passed
```

已执行：

```bash
.venv312/bin/python -m pytest tests/test_career_pb_api.py tests/test_records_center_v2_golden_fixtures.py -q
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
.venv312/bin/python -m pytest tests/test_career_record_schema_migration.py tests/test_career_record_registry.py tests/test_career_pb_resolver.py tests/test_career_pb_api.py tests/test_career_timeline_pb_nodes.py tests/test_records_center_v2_golden_fixtures.py -q
```

结果：

```text
61 passed, 16 subtests passed
```

## 5. Diff 复核结论

- 未发现真实库写入；所有验证均使用内存 SQLite 或测试 fixture。
- 未发现前端计算纪录事实、Scope、confidence 或 improvement 的新增路径。
- 未发现 Curve Cache 保存 raw stream/path/GPS/体重历史的字段或测试漏洞。
- V1 PB API 兼容测试通过。
- RCV2-10 满足完成标准，可进入 RCV2-11。

