# RC-24 Records Snapshot、AI 与 Trends 联动完成报告

日期：2026-07-14

## 执行提示词摘要

目标：在不新增平行事实表的前提下，把记录中心事实安全压缩进 `career_snapshots`，并为 AI 与 Trends 提供有限、可解释、不可重算 PB 的 Records 摘要。

边界：

- 复用 `career_snapshots`，不新增 Records 专用 snapshot 表。
- Records Snapshot 只暴露当前纪录、正式刷新事件、候选数量、演进摘要和频率型趋势输入。
- 候选只暴露计数，不输出候选成绩、候选证据或强结论。
- AI fallback 只解释 snapshot 白名单事实，不调用 LLM，不重算 PB，不写 canonical 事实表。
- Trends 输入只表达刷新频率和演进事件数量，固定 `interpretation = "frequency_only"`，不得把一次 PB 等同为整体能力提升。
- Snapshot 不返回 `detail_link`、raw FIT、轨迹、路径、schema、storage_ref、thumbnail_url 或事件 payload。

## 变更内容

- `career_backend.py`
  - 新增 `records_summary` snapshot 分区：
    - `current_records`
    - `recent_refreshes`
    - `candidate_count`
    - `evolution_summary`
    - `trend_inputs`
  - `recent_refreshes` 仅包含正式刷新类事件：`activated`、`activated_from_rebuild`、`user_confirmed`、`recalculated`。
  - 旧脏 snapshot 读取时通过 `_sanitize_snapshot_records_summary()` 重新白名单清洗。
  - `trend_inputs.interpretation` 固定收敛为 `frequency_only`。
  - AI fallback 增加 Records 摘要高亮，但不读取候选证据、不输出候选成绩、不调用 LLM。

- `docs/js_api_contract.json`
  - 更新 `get_latest_career_snapshot` 返回结构，补充 `records_summary`。
  - 更新 `generate_career_insight` 描述，明确 AI 只解释当前纪录、候选数量、刷新频率和演进事件数量，不重算 PB。

- 测试
  - 补充 Records Snapshot 白名单、候选边界、历史脏 snapshot 清洗、AI fallback 摘要边界测试。
  - 调整 snapshot 批量测试数据，符合 active 纪录唯一约束。

## 验证

已通过：

```bash
.venv312/bin/python -m pytest \
  tests/test_career_snapshot_builder.py \
  tests/test_career_snapshot_persistence.py \
  tests/test_career_insight_api_skeleton.py \
  tests/test_career_phase9_data_boundary_audit.py \
  tests/test_career_phase9_pywebview_envelope.py \
  tests/test_career_overview_pb_summary.py \
  tests/test_career_overview_api_closure.py \
  tests/test_career_timeline_pb_nodes.py \
  tests/test_career_timeline_frontend_render.py \
  tests/test_career_record_maintenance_api.py \
  tests/test_career_record_lifecycle.py \
  tests/test_career_record_rebuild.py \
  tests/test_career_record_incremental_evaluation.py \
  tests/test_career_record_state_migration.py \
  tests/test_career_record_schema_migration.py \
  tests/test_career_record_registry.py \
  tests/test_career_pb_resolver.py \
  tests/test_career_pb_api.py \
  -q
```

结果：`126 passed, 13 subtests passed`

已通过：

```bash
.venv312/bin/python -m py_compile career_backend.py main.py
.venv312/bin/python -m json.tool docs/js_api_contract.json >/dev/null
```

## 复核结论

- 未新增 Records Snapshot 平行表。
- Snapshot 与 AI 输出均不包含禁止字段。
- 候选纪录没有进入 AI 强结论或趋势结论，只保留数量。
- Trends 输入只保留频率型事实，不表达能力提升判断。
- 未发现阻断性问题。

