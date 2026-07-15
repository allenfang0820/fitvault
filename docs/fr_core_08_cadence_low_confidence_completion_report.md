# FR-Core-08 步频低置信度与间歇活动状态修复完成报告

日期：2026-07-13  
任务源：`docs/fatigue_review_core_audit_fix_task_list.md`  
状态：已完成

## 1. 交付手册摘要刷新

- 步频稳定性必须区分“缺少步频数据”和“有步频但节奏变化太大，不适合稳定性评分”。
- CV 超阈值或间歇活动返回 `status=partial`、`confidence=low`、`reasons=["intermittent_cadence_pattern"]`。
- 前端对 low/partial cadence 显示“节奏变化较大，不适合稳定性评分”，不得显示“设备未记录”。

## 2. FR-Core-08 任务契约摘要

- missing cadence、intermittent/variable cadence、available stable cadence 是不同状态。
- 低置信度 cadence 不生成强历史趋势。
- 间歇跑不能被评价为跑姿退化或能力退化。
- 真正无 cadence 曲线时仍显示数据/设备缺失。

## 3. 工程级提示词

目标：修复步频稳定性低置信度状态，使有真实步频但节奏变化过大的活动不再被展示为设备未记录。

范围：
- 允许修改 `metrics_resolver.py` 的 cadence stability 输出形状。
- 允许修改 `main.py` 复盘快照透传字段。
- 允许修改 `track.html` 的 cadence 缺失原因和状态文案。
- 允许更新测试、契约文档和任务清单。

边界：
- 不修改 cadence stability 评分公式。
- 不修改运动类型 registry。
- 不修改 HR 传感器来源。
- 不修改历史 baseline 迁移策略。

验收：
- Resolver 间歇步频返回 `status=partial`、`confidence=low`、`reasons` 包含 `intermittent_cadence_pattern`。
- 前端 JS 文案实际执行后包含“节奏变化较大”，不包含“设备未记录”。
- cadence low/partial 不被展示成 available 稳定状态。

## 4. 实现摘要

- `_compute_cadence_stability()` 为 unsupported、样本不足、短时长和间歇模式返回明确 `status/reasons`。
- `main.py` cadence stability 快照透传 Resolver 的 `status/reasons`。
- 空态 cadence stability 补齐 `status=unavailable`。
- `_fatigueReviewMetricMissingReason()` 支持 `intermittent_cadence_pattern` 文案。
- cadence 卡片对 `status=partial` 或 `confidence=low` 显示“不适合评分”。

## 5. 验证结果

通过：

```bash
.venv312/bin/python -m pytest -q tests/test_resolver_sport_isolation.py::TestCadenceStability::test_running_intermittent_low_confidence
.venv312/bin/python -m unittest discover -s tests -p 'test_fatigue_review_core_audit_regression.py'
.venv312/bin/python -m pytest -q tests/test_fatigue_review_quality_gate.py::TestP5P4UiStructureGate::test_metric_card_user_facing_copy_and_tooltips tests/test_fatigue_review_quality_gate.py::TestP5P4UiStructureGate::test_p5_running_metric_cards_keep_cadence_stability_semantics
.venv312/bin/python -m pytest -q tests/test_resolver_sport_isolation.py tests/test_fatigue_review_e2e_contract.py tests/test_fatigue_review_snapshot_realignment.py
```

结果：

- 间歇步频 resolver 窄测：1/1 通过。
- 核心红线回归：10/10 通过。
- 前端文案窄测：2/2 通过。
- 相关 broader 测试：152/152 通过。

## 6. 下一任务建议

按清单顺序，下一任务是 `FR-Core-09：HR 传感器来源与置信度契约`。
