# P5b 骑行复盘功率效率与功率保持指标卡对齐完成报告

## 1. 本次目标

- 按 `docs/p5b_cycling_power_efficiency_durability_cards_prompt.md` 执行 P5b-cycling。
- 让骑行复盘指标卡用户可见 P3b 后端功率口径。
- 将骑行 `metrics.efficiency` 展示为“功率效率”。
- 将骑行 `metrics.durability` 展示为“后程功率保持”。
- 保持跑步/general 指标卡语义不变。
- 不改后端、不改 AI、不改 DB、不改 ECharts 主图。

## 2. 执行前重新思考

- P5 已让骑行指标卡突出 `power_variability / pedaling_stability`。
- P3b 已将骑行 `efficiency / durability` 后端事实升级为 `power_hr / power_retention`。
- 因此本次不需要继续改算法，只需要让前端展示语义从旧的“辅助参考”对齐到功率口径。
- 前端必须只读后端 metrics，不能从 `summary / curves / DOM / ECharts / points` 推导。

## 3. 现状调查

- 当前 cycling profile 保持 8 张卡。
- `metrics.efficiency` 原先在骑行 profile 中没有用户可见入口，原 slot 被 `events` 占用。
- `metrics.durability` 原先显示为“后程保持参考”，tooltip 仍提示“不等同于 power-based durability”。
- 渲染分支已读取 `metrics.durability`，但只展示 score，没有展示 P3b 的 `power_retention_pct / head_power / tail_power`。

## 4. 实现内容

- 保持 8 卡布局不变。
- cycling profile 调整为：
  - 功率变异：`metrics.power_variability`
  - 心率漂移：`metrics.hr_drift`
  - 踏频稳定性：`metrics.pedaling_stability`
  - 能量断档风险：`metrics.bonk_risk`
  - 功率效率：`metrics.efficiency`
  - 训练负荷：`metrics.training_load`
  - 后程功率保持：`metrics.durability`
  - 状态下滑点：`metrics.events`
- 新增 `_fatigueReviewPowerEfficiencyEvidence(metric, missing)`。
  - 只读 `metric.power_per_hr / avg_power / avg_hr / reasons`。
- 新增 `_fatigueReviewPowerRetentionEvidence(metric, missing)`。
  - 只读 `metric.power_retention_pct / head_power / tail_power / reasons`。
- 更新 cycling 文案：
  - `efficiency.cycling` 改为单位心率功率输出语义。
  - `durability.cycling` 改为后程功率保持语义。
- 更新 headline 和 missing reason：
  - 新增 `power_efficiency` 与 `power_retention` headline。
  - basis 不匹配时展示“后端未返回功率口径指标”。
  - 功率曲线样本不足时展示“功率曲线样本不足”。

## 5. 前端零推断边界

- `功率效率` 只读 `metrics.efficiency.power_per_hr`。
- `后程功率保持` 只读 `metrics.durability.power_retention_pct/head_power/tail_power`。
- 未从 `summary.avg_power / summary.avg_hr` 计算 `power_per_hr`。
- 未从 `curves.power` 计算 `power_retention_pct`。
- 未从 DOM、ECharts、`_lastFatigueReviewChartPayload`、points 推导任何 P3b 指标。
- 未计算 FTP / IF / TSS / W/kg / 功率区间。

## 6. 验证

运行命令：

```bash
python3 -m pytest tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py
```

结果：

- `143 passed, 1 warning`。
- warning 为 urllib3 / LibreSSL 环境提示，与本次修改无关。

## 7. 剩余风险

- P5b 仅做文案和指标卡证据对齐，没有重新设计骑行卡片视觉层级。
- P3b 的 `power_per_hr` 和 `power_retention_pct` 仍是保守启发式指标，用户文案避免表达为 FTP 或长期能力。
- 后程功率保持仍可能受下坡、滑行、路口停顿、跟骑和路况影响；本任务不做复杂场景识别。

## 8. 下一步

- 可选：基于真实骑行样本做一次 UI 手动验收，确认 `功率效率 / 后程功率保持` 在有功率、无功率、样本不足三种场景下都能诚实降级。
- 可选：如需要更强视觉重点，单独做骑行指标卡视觉重排任务。
