# RCV2-37 工程级执行提示词：Records Snapshot、AI 与 Trends 联动

## 任务目标

安全压缩 Records Center V2 的正式纪录、候选状态和曲线可用性摘要，供 Career Snapshot、AI fallback insight 与 Trends 消费，同时严格区分事实、分析曲线和模型估计。

## 输入摘要

- 当前任务：`RCV2-37 Records Snapshot、AI 与 Trends 联动`。
- 前置任务：`RCV2-14` 通用 Records API、`RCV2-33` 前端曲线视图、`RCV2-36` Overview/Timeline/Race/Achievement 集成已完成。
- 当前 `build_career_snapshot()` 已包含 V1 PB 当前纪录、最近刷新、候选数量、演进摘要和基础 `trend_inputs`。
- 当前 curve cache 是派生缓存，不是正式纪录事实源。

## 冻结契约

- Activity 是唯一事实源；正式纪录只能由 Resolver/状态迁移服务写入。
- Snapshot 只能包含安全白名单摘要，不暴露 raw FIT、raw streams、points、track、route signature、path、schema、设备标识、体重详情或候选 evidence。
- AI 可以解释来源和变化，但不得重算纪录、确认候选或写 canonical 表。
- Trends 可以消费 PDC/Pace/GAP 的可用性摘要，但必须标注来源、算法版本、分析属性和降级状态。
- GAP/NGP/eFTP/CP/W′/MAP/PMax 等分析或模型估计不得被表述为“刷新正式纪录”。
- 不打包，不写真实库；本任务只改 builder、contract、测试和报告。

## 文件范围

- `career_backend.py`
- `docs/js_api_contract.json`
- `tests/test_career_snapshot_builder.py`
- 新增 `tests/test_career_records_v2_snapshot_ai_trends.py`
- 新增 `docs/records_center_v2_rcv2_37_completion_report.md`
- 更新 `docs/运动生涯记录中心V2（多运动纪录）开发任务清单.md`
- 更新 `docs/records_center_v2_rolling_contract_summary.md`

## 非目标

- 不新增真实数据 apply/rebuild。
- 不改变 Records Resolver 的正式纪录结果。
- 不改变前端页面结构。
- 不把 curve cache payload、candidate evidence 或模型估计暴露给 AI/Trends。
- 不执行打包、签名、公证或发布包替换。

## 实施步骤

1. 为 Records Snapshot 增加 V2 formal records 安全摘要。
2. 增加 curve availability 安全摘要，只统计 `curve_type/sport/source_mode/algorithm_version/sample_count/latest_generated_at/state` 等元数据。
3. 扩展 `trend_inputs`，声明 facts/analysis/model 边界，提供 PDC/Pace/GAP 可用性输入，且所有 curve 输入标记 `creates_formal_record=false`。
4. 扩展 saved snapshot sanitizer，保证旧脏内容会被裁剪成安全 schema。
5. 调整 AI fallback record highlights，仅解释正式纪录、候选数量和分析曲线可用性，不输出强结论或“模型刷新纪录”。
6. 更新 JS API contract 的 Snapshot 返回契约描述。
7. 增加定向测试覆盖：安全字段、curve payload 不泄露、candidate evidence 不泄露、AI wording 边界、dirty snapshot sanitizer、正式纪录/模型/analysis 分离。

## 验证命令

```bash
.venv312/bin/python -m pytest tests/test_career_records_v2_snapshot_ai_trends.py tests/test_career_snapshot_builder.py -q
.venv312/bin/python -m pytest tests/test_career_records_v2_api.py tests/test_career_records_v2_downstream_integration.py tests/test_career_insight_api_skeleton.py -q
.venv312/bin/python -m py_compile career_backend.py main.py
```

## 差异复核

- 检查 diff 是否只触碰本任务范围。
- 检查 Snapshot、AI、Trends 输出没有 raw/points/track/path/schema/体重详情/candidate evidence。
- 检查 curve/model 只作为 analysis/model 边界，不会进入 formal refresh。
- 检查旧 Snapshot sanitizer 仍兼容历史脏内容。

## 完成定义

- 定向测试和 py_compile 通过。
- 完成报告写入。
- 任务清单标记 `RCV2-37 Done`、`RCV2-38 In Progress`。
- 滚动摘要刷新到 RCV2-38。
