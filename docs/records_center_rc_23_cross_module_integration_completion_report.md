# RC-23 Overview、Timeline、Race、Achievement 联动完成报告

日期：2026-07-14

## 执行提示词摘要

目标：验证并收敛记录中心与 Overview、Timeline、Race、Achievement 的集成边界，确保正式纪录能被其他模块消费，但候选、拒绝、回退和无变化重建不会污染正式概览、时间线节点或成就事实。

边界：

- Activity 仍是唯一事实源，正式纪录事实由 Records/PB Resolver 写入。
- Overview、Timeline、Race、Achievement 只能消费后端事实或 ViewModel，不重新计算 PB。
- `detail_link.source = "career"` 保留；PB 详情入口额外保留 `detail_link.record_id`。
- Timeline 候选禁入规则只约束 Timeline 渲染区，不禁止记录中心自身调用候选 API。

## 变更内容

- 刷新 Overview PB 契约测试：`latest_pb.detail_link` 与代表纪录 `detail_link` 包含 `record_id`，支持记录详情/演进入口。
- 增加 Overview 边界测试：`career_event_candidates(candidate_type="pb_record")` 不进入 `pb_count`、`latest_pb` 或 `representative_pb_records`。
- 调整代表纪录测试数据：同一 `pb_type/source_mode/sport_scope` 的旧纪录使用 `superseded`，符合 active 唯一约束。
- 收紧 Timeline 前端测试范围：候选 API 不应出现在 Timeline 面板/流程中；记录中心页面自身允许候选 API。
- 同步 Overview closure 旧断言：PB detail link 包含 `record_id`，Race/Achievement 仍使用 Activity 回跳契约。

## 验证

已通过：

```bash
.venv312/bin/python -m pytest \
  tests/test_career_overview_pb_summary.py \
  tests/test_career_overview_timeline_races.py \
  tests/test_career_timeline_pb_nodes.py \
  tests/test_career_timeline_frontend_render.py \
  tests/test_career_archives_frontend_render.py \
  tests/test_career_phase8_frontend_readiness.py \
  tests/test_career_record_maintenance_api.py \
  tests/test_career_pb_api.py \
  tests/test_career_record_lifecycle.py \
  tests/test_career_record_rebuild.py \
  tests/test_career_record_incremental_evaluation.py \
  tests/test_career_record_state_migration.py \
  tests/test_career_record_schema_migration.py \
  tests/test_career_record_registry.py \
  tests/test_career_pb_resolver.py \
  tests/test_career_overview_api_closure.py \
  -q
```

结果：`125 passed, 13 subtests passed`

已通过：

```bash
.venv312/bin/python -m py_compile career_backend.py main.py
```

## 复核结论

- 本任务未新增跨模块事实写入口。
- 候选纪录不会进入正式 Overview 摘要或 Timeline 渲染流程。
- PB 详情入口需要的 `record_id` 已在 Overview 相关契约中保留。
- Timeline 候选禁入断言已限定到 Timeline 面板，避免误伤记录中心候选视图。
- 未发现阻断性问题。

