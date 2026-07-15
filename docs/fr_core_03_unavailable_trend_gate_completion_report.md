# FR-Core-03 不可用指标趋势门控与 AI 快照净化完成报告

日期：2026-07-13  
任务源：`docs/fatigue_review_core_audit_fix_task_list.md`  
状态：已完成

## 1. 交付手册摘要刷新

- 可用性状态与置信度分离；`unavailable / not_applicable` 不是低置信度，而是不能计算。
- 不可用指标不得用 `0` 代替缺失主值，也不得生成强趋势。
- AI 只能消费已通过可用性门控的 compact snapshot，不自行判断哪些 trend 可用。
- 骑行专项解释继续只以 `cycling_explanation_signals` 为后端权威输入。

## 2. FR-Core-03 任务契约摘要

- 当前主值缺失、`status=unavailable/not_applicable`、`confidence=unavailable/missing` 时，trend 必须为 unknown。
- unknown trend 的 `delta_pct` 和 `is_improving` 必须为 `null`。
- low/partial 指标在 AI compact snapshot 中默认不带强趋势，只可作为 reference。
- prompt 文案不能掩盖后端错误字段；必须先净化数据再进入 AI。

## 3. 工程级提示词

目标：修复不可用指标仍生成强趋势、并进入 AI compact snapshot 的问题。

范围：
- 允许修改 `main.py` 中 trend gate、AI compact snapshot 构建和 HR drift trend 注入。
- 允许更新 FR-Core-03 相关测试和任务清单。

边界：
- 不修改 running durability 当前曲线源。
- 不修改空快照 `pct=0` 主值契约。
- 不修改前端跑步/骑行缺失文案。
- 不修改解耦方向算法之外的其他算法口径。
- 不让 AI 自行补算或自行筛选趋势。

验收：
- `hr_drift.pct=null` 时 trend 的 `delta_pct/is_improving` 为 `null`。
- 不再出现“数据不足但改善 100%”。
- AI compact snapshot 不携带 unavailable 指标的强趋势字段。
- AI preflight / insight 契约测试通过。

## 4. 实现摘要

- 新增 `_gate_fatigue_review_metric_trends()` 与 `_fatigue_review_unknown_trend()`。
- 后端复盘 snapshot 返回前统一门控不可用指标 trend。
- AI compact snapshot 构建时再次门控，并对 low/partial 指标使用 unknown reference trend。
- HR drift trend 不再把 `_drift_pct=None` 转成 `0.0`。

## 5. 验证结果

通过：

```bash
.venv312/bin/python -m pytest -q tests/test_fatigue_review_ai_preflight_p8.py tests/test_fatigue_review_ai_insight_p6.py tests/test_fatigue_review_e2e_contract.py
```

结果：51 passed。

红线回归：

```bash
.venv312/bin/python -m unittest discover -s tests -p 'test_fatigue_review_core_audit_regression.py'
```

结果：FR-Core-03 对应用例已转绿；剩余 3 个预期失败继续锚定 FR-Core-04、FR-Core-05、FR-Core-07。

## 6. 下一任务建议

按清单顺序，下一任务是 `FR-Core-04：当前指标曲线权威源统一`。

建议执行边界：
- 只修当前复盘 snapshot 中 running durability 使用的速度曲线来源。
- 不同时修空快照主值、前端文案、专项路由或 AI prompt。
