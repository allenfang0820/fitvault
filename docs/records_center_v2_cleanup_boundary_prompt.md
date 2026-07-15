# 运动生涯记录中心 V2 冗余代码清理边界与工程提示词

更新时间：2026-07-15

## 1. 清理目标

本轮清理的目标不是重新设计记录中心，而是在当前已确认的 V2 产品边界下，移除或隔离已经不属于当前记录中心的路线/赛段/Pace-GAP 遗留实现，避免后续开发继续被旧方案误导。

本轮清理必须保护年度报告、Records V2 通用状态机、骑行功率曲线、多运动整次活动纪录等仍在当前范围内的能力。

## 2. 当前产品边界

当前记录中心 V2 不包含以下能力：

- 同赛道最好成绩
- Route PR
- Segment PR
- 越野路线对比
- 越野 Pace/GAP 分析曲线

这些能力需要赛道/路线管理、赛段定义、同路线匹配和更完整的轨迹治理能力。当前产品设计暂不支持赛道管理，因此不得在记录中心 Catalog、API contract、前端展示、候选记录或正式记录状态机中继续暴露它们。

当前记录中心 V2 保留以下能力：

- 跑步标准距离记录
- 骑行标准距离候选、功率时长记录、整次活动记录、PDC 曲线
- 徒步整次活动、海拔、连续爬升候选记录
- 泳池游泳标准距离候选
- 公开水域标准距离与整次活动候选记录
- 越野跑整次活动记录：最长距离、最大累计爬升、最长历时、最高海拔、最大连续爬升
- 通用 `RecordEvidence`、Catalog、Records list/detail/history/candidate、rebuild/status API
- 年度报告/年度 AI 总结所有 `CAREER_YEAR_*` 逻辑

## 3. 不可跨越的保护边界

清理时不得删除、恢复或重写以下范围：

- 年度报告和年度 AI 总结：
  - `CAREER_YEAR_*`
  - Year Snapshot
  - annual insight/report state machine
  - `get_career_year_insight`
  - `generate_career_year_insight`
  - 年度前端页面与年份卡片
- Records V2 通用核心：
  - `RecordDefinition`
  - `RecordEvidence`
  - `build_record_evidence`
  - `apply_record_evidence_state`
  - `get_career_record_catalog`
  - `get_career_records`
  - `get_career_record_detail`
  - `get_career_record_history`
  - `get_career_record_candidates`
  - `decide_career_record_candidate`
  - `rebuild_career_records`
  - `get_career_record_curve`
- 骑行功率曲线和 `career_record_curve_cache`，因为 PDC 仍属于当前记录中心。

严禁使用整文件 `git restore career_backend.py` 进行清理。该文件同时承载年度报告和记录中心核心实现，整文件恢复会误伤近期有效开发成果。

## 4. 可以清理的候选范围

在测试和 contract 对齐后，可以清理以下遗留实现：

- 越野路线签名和匹配：
  - `build_trail_route_signature`
  - `match_trail_route_signatures`
  - `build_trail_route_candidate_plan`
  - 仅服务 route matching 的 helper / version constant / safe-json helper
- route/segment 记录候选：
  - `build_trail_route_record_evidences`
  - `build_trail_segment_record_evidences`
  - `build_trail_route_segment_record_evidences`
  - `apply_trail_route_segment_records`
- 越野 Pace/GAP：
  - `TRAIL_PACE_GAP_CURVE_ALGORITHM_VERSION`
  - `TRAIL_PACE_GAP_ANCHOR_DISTANCES_M`
  - `resolve_trail_pace_gap_activity_curve`
  - `build_trail_pace_gap_curve_viewmodel`
  - `save_trail_pace_gap_curve_cache`
- route comparison read model:
  - `get_trail_route_comparison_viewmodel`
- route-specific observability:
  - `route_cache_count`
  - `route_match_count`
  - `route_candidates`
- route/Pace-GAP 相关测试和 golden fixture。

## 5. Schema 策略

本轮清理不做真实库破坏性动作。

允许：

- 停止当前代码继续依赖 route/segment/Pace-GAP 表。
- 在内存库/新 schema 测试中移除 route 表作为 Records Center V2 必需表。
- 将观测指标收口到仍有效的 `career_record_curve_cache`。

不允许：

- 对用户真实库执行 `DROP TABLE career_route_signatures`。
- 对用户真实库执行 `DROP TABLE career_route_matches`。
- 写迁移脚本自动删除历史 route cache 数据。

如未来需要真实库 drop，必须另立迁移任务，包含备份、兼容读取、回滚方案和显式用户确认。

## 6. 执行顺序

### Task 1：固化清理边界

目标：写入本文件，作为本轮清理唯一工程护栏。

验收：

- 文档明确当前记录中心不含同赛道、Route PR、Segment PR、Pace-GAP。
- 文档明确保护年度报告和 Records V2 通用核心。
- 文档明确 schema 不做真实库破坏性动作。

### Task 2：清理 tests 和 contract 不一致

目标：让测试与最新产品边界一致。

范围：

- 保留/新增断言：Catalog/API/frontend 不暴露 route/segment/Pace-GAP。
- 删除或改写旧测试中对 route table、route comparison、route metrics、`route_total` fixture 的期待。
- `docs/js_api_contract.json` 不再描述 route comparison API 或 route rebuild metrics。

验收：

- `rg "get_trail_route_comparison|route_segment_pr|pace_gap_curve|trail_route_segment" docs/js_api_contract.json track.html tests` 仅允许出现在“不得出现/不包含”的测试断言中。
- 与 schema/rebuild/observability 相关测试不再要求 route table 或 route metrics。

### Task 3：清理 backend 死代码

目标：移除当前记录中心不再使用的 route/segment/Pace-GAP backend 实现。

范围：

- 删除 route signature/matching、route/segment evidence、Pace-GAP viewmodel/cache、route comparison viewmodel。
- 删除 route-only source mode/scope/range 支持，前提是不影响仍有效的 Records V2 evidence。
- 保留 cycling PDC 曲线和通用 curve cache。

验收：

- `career_backend.py` 中不再存在当前记录中心不使用的 route/segment/Pace-GAP public/helper 函数。
- `get_career_record_curve` 仍可服务骑行 PDC。
- `py_compile` 通过。

### Task 4：schema 非破坏性收口

目标：Records V2 schema 不再把 route tables 视为当前必需资源，同时不 drop 真实库。

范围：

- 从当前必需表/索引集合中移除 route table/index。
- 停止新 schema 测试要求 route table/index 存在。
- `ensure_career_schema` 不执行任何 drop。

验收：

- schema migration 测试通过。
- 代码中没有 `DROP TABLE career_route_signatures` 或 `DROP TABLE career_route_matches`。

### Task 5：聚焦验证和最终 review

目标：确认清理没有误伤年度报告、记录中心核心、骑行 PDC 和前端展示。

建议验证命令：

```bash
PYTHONPATH=. .venv312/bin/python -m py_compile career_backend.py main.py llm_backend.py
PYTHONPATH=. .venv312/bin/python -m unittest tests.test_career_record_registry
PYTHONPATH=. .venv312/bin/python -m unittest tests.test_career_record_schema_migration
PYTHONPATH=. .venv312/bin/python -m unittest tests.test_career_record_evidence
PYTHONPATH=. .venv312/bin/python -m unittest tests.test_career_record_v2_rebuild
PYTHONPATH=. .venv312/bin/python -m unittest tests.test_career_records_trail_api_surface
PYTHONPATH=. .venv312/bin/python -m unittest tests.test_career_records_v2_security_perf_observability
PYTHONPATH=. .venv312/bin/python -m unittest tests.test_career_records_v2_chart_frontend
PYTHONPATH=. .venv312/bin/python -m unittest tests.test_career_records_v2_cycling_frontend_semantics
PYTHONPATH=. .venv312/bin/python -m unittest tests.test_career_year_insight_read_api tests.test_career_year_generate_api
```

## 7. 本轮清理工程提示词

请按以下约束执行记录中心 V2 冗余代码清理：

> 你正在清理脉图运动生涯记录中心 V2。当前产品边界已经冻结：记录中心不包含同赛道最好成绩、Route PR、Segment PR、越野路线对比、越野 Pace/GAP 分析曲线。请先对齐 tests 和 API contract，再移除 backend 中已经不属于当前记录中心的 route/segment/Pace-GAP 遗留实现。清理时必须保护年度报告 `CAREER_YEAR_*`、Records V2 通用 `RecordEvidence`/Catalog/Records API、骑行 PDC 和多运动整次活动记录。schema 只能做非破坏性收口，不得 drop 真实库 route tables。每一步都要运行聚焦测试，失败最多做三次集中修复；不要做打包，不写真实库。

