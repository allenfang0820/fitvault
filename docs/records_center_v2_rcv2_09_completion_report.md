# RCV2-09 完成报告：V2 Registry 与动态 Catalog 代码化

完成时间：2026-07-14

## 任务目标

实现 V2 Registry/Catalog 单一真理源，代码化多运动 record definitions、Scope、availability 和 Catalog 派生，同时保持 V1 跑步纪录与旧 PB API 兼容。

## 交付物

- `docs/records_center_v2_rcv2_09_execution_prompt.md`
- `docs/records_center_v2_rcv2_09_completion_report.md`
- `career_backend.py`
- `tests/test_career_record_registry.py`
- `docs/records_center_v2_rolling_contract_summary.md`
- `docs/运动生涯记录中心V2（多运动纪录）开发任务清单.md`

## 实现内容

- 扩展 `RecordDefinition`，补齐 V2 字段：`family`、`scope_dimensions`、`quality_policy`、`availability_state`、`availability_reason`、`standard_duration_sec`、`dynamic_scope`、`legacy_category`。
- 扩展 Registry 白名单：sport、family、unit、comparison、source_mode、scope_dimensions、availability。
- 代码化 V2 多运动 definitions：跑步、骑行功率、骑行整次活动、徒步、泳池、公开水域、越野整次、越野 route/segment。
- 新增 `get_career_record_catalog()`，从 Registry 派生 sport tabs、groups、records、axis_direction、availability、scope_dimensions 和 curve/history/candidate 能力。
- 保持 V1 `match_record_definition()` 默认只匹配 `RUNNING_RECORD_DEFINITIONS`，避免新运动定义被旧 Resolver 误触发。
- 扩展 source mode label，同时保持旧 PB API 字段兼容。
- 新增测试覆盖 V2 definitions、Catalog 派生、dynamic scope、analysis/model 不进入 active definitions、V1 跑步匹配不受 V2 定义影响。

## 验证结果

```bash
.venv312/bin/python -m pytest tests/test_career_record_registry.py tests/test_records_center_v2_golden_fixtures.py -q
```

结果：`23 passed, 13 subtests passed in 0.16s`

```bash
.venv312/bin/python -m pytest tests/test_career_pb_resolver.py tests/test_career_pb_api.py -q
```

结果：`20 passed in 0.11s`

```bash
.venv312/bin/python -m py_compile career_backend.py
```

结果：通过

```bash
.venv312/bin/python -m pytest tests/test_career_record_registry.py tests/test_career_pb_resolver.py tests/test_career_pb_api.py tests/test_career_timeline_pb_nodes.py tests/test_records_center_v2_golden_fixtures.py -q
```

结果：`49 passed, 13 subtests passed in 0.17s`

## Diff 复核

- 本任务修改 Registry/Catalog 代码和 Registry 测试，新增 RCV2-09 文档。
- 未修改 schema migration、真实库、前端、`docs/js_api_contract.json` 或打包产物。
- 工作树中 `career_backend.py` 已存在其他未提交改动；本任务复核聚焦 Registry/Catalog 区段，未回退或整理无关改动。
- V1 跑步 match path 默认仍只使用 `RUNNING_RECORD_DEFINITIONS`，降低新运动误触发旧 Resolver 的风险。
- 新运动 definitions 只进入 Catalog，不运行 Resolver，不写 active/candidate。

## 下一任务

`RCV2-10 Scope schema migration 与 Curve Cache 基础设施`。

下一任务应按 `RCV2-05` schema/cache/route 契约，实现结构化 Scope 字段、V2 active/evidence 索引、Curve Cache 表和 dry-run/rollback 测试；仍不得写真实库。
