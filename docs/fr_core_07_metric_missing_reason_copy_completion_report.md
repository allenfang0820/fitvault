# FR-Core-07 指标卡、缺失原因与运动专项文案分流完成报告

日期：2026-07-13  
任务源：`docs/fatigue_review_core_audit_fix_task_list.md`  
状态：已完成

## 1. 交付手册摘要刷新

- 指标缺失原因必须由后端 `basis/status/reason_code/reasons` 驱动。
- 跑步耐久缺失只使用速度/配速/时长文案。
- 骑行功率保持缺失只使用功率/有效踩踏文案。
- 用户界面不得出现“后端未返回功率口径指标”等开发者式文案。

## 2. FR-Core-07 任务契约摘要

- `_fatigueReviewMetricMissingReason()` 不得只用模糊正则把 `points<20` 一律解释成功率缺失。
- `durability.basis=power_retention` 才能进入功率保持文案。
- 普通 running durability 的样本不足必须说明速度样本不足或活动时长不足。
- 前端只翻译后端状态和原因，不从曲线或 DOM 补算生理结论。

## 3. 工程级提示词

目标：修复复盘指标卡缺失原因的运动专项文案分流，防止跑步耐久卡片出现骑行功率曲线文案，同时保留骑行功率保持的正确降级文案。

范围：
- 允许修改 `track.html` 的 `_fatigueReviewMetricMissingReason()`。
- 允许更新前端文案测试和核心红线测试。
- 允许同步契约文档与任务清单。

边界：
- 不修改后端 durability / power_retention 算法。
- 不从前端曲线重新计算指标。
- 不修改运动类型 registry。
- 不修改 HR 传感器来源、步频低置信度状态或 baseline 迁移策略。

验收：
- JS 语义测试实际执行 `_fatigueReviewMetricMissingReason('durability', {confidence:'unavailable', reasons:['points<20']})`，结果包含“速度”且不包含“功率”。
- JS 语义测试实际执行 `durability.basis='power_retention'`，结果保留“功率”且不包含“速度”。
- `track.html` 不再包含“后端未返回功率口径指标”。

## 4. 实现摘要

- `_fatigueReviewMetricMissingReason()` 增加 `reason_code/reason_codes` 输入兼容。
- 新增 `basis` 判断：`power_retention` 与普通 `durability` 分开处理。
- running durability 样本不足返回“有效速度样本不足 20 个”。
- cycling power retention 样本不足继续返回“功率曲线样本不足”。
- 移除开发者式功率口径错误文案。

## 5. 验证结果

通过：

```bash
.venv312/bin/python -m unittest discover -s tests -p 'test_fatigue_review_core_audit_regression.py'
.venv312/bin/python -m pytest -q tests/test_fatigue_review_quality_gate.py::TestP5P4UiStructureGate::test_metric_card_user_facing_copy_and_tooltips tests/test_v9_0_detail_tab_review.py::TestV9AiInsightModalHtml::test_p7_3_metric_render_uses_metrics_only tests/test_v9_0_detail_tab_review.py::TestV9AiInsightModalHtml::test_p5_cycling_metric_cards_use_power_and_pedaling_profile
```

结果：

- 核心红线回归：9/9 通过。
- 前端文案/渲染窄测：3/3 通过。

## 6. 下一任务建议

按清单顺序，下一任务是 `FR-Core-08：步频低置信度与间歇活动状态修复`。
