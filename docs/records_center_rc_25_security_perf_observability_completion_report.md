# RC-25 安全、性能、日志与可观测性闭环完成报告

日期：2026-07-14

## 执行提示词摘要

目标：补齐记录中心非功能性要求，使 Records/PB 关键路径可观测、可诊断、性能可验证，同时避免 raw FIT、轨迹、路径、schema、payload 等敏感信息泄露。

边界：

- 只处理记录中心 PB/Records 相关增量评估、重建、候选决策、事件查询和 Snapshot 清洗边界。
- 不改 UI、不改非 Records 模块业务语义。
- 新增返回字段保持兼容：只追加 `metrics`，不删除现有字段。

## 变更内容

- 安全清洗
  - `_sanitize_public_metadata()` 增强：递归移除禁止 key，并清空疑似本地路径字符串值，如 `/Users/...`、`\Users\...`、`/tmp/...`、`file://...`、`.fit` 路径。
  - `get_career_record_events()` 的 `payload` 继续走递归清洗，测试覆盖嵌套 `track_json/detail_link/file_path` 与路径字符串。
  - 安全日志 helper `_safe_record_log()` 禁止输出 `items/results/decision/payload/evidence_json` 等高风险原文。

- 耗时与指标
  - `evaluate_activity_record_increment()` / `evaluate_activity_record_increments()` 返回 `metrics.elapsed_ms`。
  - `plan_records_rebuild()` / `rebuild_records()` 返回 `metrics.elapsed_ms`、`processed`、`reason_counts`，apply 模式额外返回 `applied_summary`。
  - `decide_career_pb_candidate()` 返回 `metrics.elapsed_ms`，main API 包装层保留该指标。
  - `get_career_pb()`、`get_career_pb_detail()`、`get_career_pb_history()`、`get_career_record_events()` 返回查询耗时和返回数量。

- 日志与可观测性
  - 重建 dry-run/apply、增量评估、候选决策写入安全结构化日志。
  - 日志字段限定为 run_id、resolver_version、processed、summary、applied_summary、reason_counts、elapsed_ms、action 等安全摘要。
  - 日志不记录 raw FIT、轨迹点、payload、证据原文、本地路径或 SQLite schema。

- 性能测试
  - 新增约 10,000 条合成 Activity 的 `rebuild_records(dry_run=True)` 性能测试。
  - 自动化门限：函数内 `metrics.elapsed_ms < 8000ms`，外部 wall time `< 10000ms`。

- 契约
  - `docs/js_api_contract.json` 更新候选决策、重建、事件查询的 `metrics` 返回说明和安全日志边界。

## 验证

已通过 RC-25 定向验证：

```bash
.venv312/bin/python -m pytest \
  tests/test_career_record_rebuild.py \
  tests/test_career_record_incremental_evaluation.py \
  tests/test_career_record_maintenance_api.py \
  tests/test_career_record_lifecycle.py \
  tests/test_career_record_state_migration.py \
  tests/test_career_record_schema_migration.py \
  tests/test_career_record_registry.py \
  tests/test_career_pb_resolver.py \
  tests/test_career_pb_api.py \
  -q
```

结果：`63 passed, 13 subtests passed`

已通过组合回归：

```bash
.venv312/bin/python -m pytest \
  tests/test_career_record_rebuild.py \
  tests/test_career_record_incremental_evaluation.py \
  tests/test_career_record_maintenance_api.py \
  tests/test_career_record_lifecycle.py \
  tests/test_career_record_state_migration.py \
  tests/test_career_record_schema_migration.py \
  tests/test_career_record_registry.py \
  tests/test_career_pb_resolver.py \
  tests/test_career_pb_api.py \
  tests/test_career_snapshot_builder.py \
  tests/test_career_snapshot_persistence.py \
  tests/test_career_insight_api_skeleton.py \
  tests/test_career_phase9_data_boundary_audit.py \
  tests/test_career_phase9_pywebview_envelope.py \
  tests/test_career_overview_pb_summary.py \
  tests/test_career_overview_api_closure.py \
  tests/test_career_timeline_pb_nodes.py \
  tests/test_career_timeline_frontend_render.py \
  tests/test_career_archives_frontend_render.py \
  tests/test_career_phase8_frontend_readiness.py \
  -q
```

结果：`150 passed, 13 subtests passed`

已通过：

```bash
.venv312/bin/python -m py_compile career_backend.py main.py
.venv312/bin/python -m json.tool docs/js_api_contract.json >/dev/null
```

## 复核结论

- API 和 metadata 禁止字段递归清洗已覆盖。
- 关键 Records 路径有耗时和计数指标。
- 日志只输出安全摘要，不输出 payload 或本地路径。
- 10k 合成 Activity dry-run 性能门已纳入自动化测试。
- 未发现阻断性问题。

