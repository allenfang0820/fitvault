# P5c 骑行复盘端到端验收与降级场景固化完成报告

## 1. 本次目标

- 按 `docs/p5c_cycling_fatigue_review_acceptance_prompt.md` 执行 P5c-cycling。
- 固化骑行复盘有功率、无功率、功率样本不足、非骑行回归四类验收场景。
- 确认骑行主图和指标卡已经与跑步不同。
- 确认无功率或样本不足时不会展示完整功率复盘口吻。
- 不新增算法，不改 AI，不改 DB，不调用 LLM。

## 2. 执行前重新思考

- P3/P3b/P4/P5/P5b 已完成骑行专项指标、主图和指标卡对齐。
- 当前更需要验收闭环，而不是继续增加新功能。
- 本任务默认补测试和验收清单；只有发现契约违背才做最小生产修复。
- 本次验收未发现必须修改生产代码的问题。

## 3. 验收场景

- 场景 A：有功率 + 有踏频骑行。
- 场景 B：无功率骑行。
- 场景 C：功率样本不足。
- 场景 D：非骑行回归。

## 4. 实现或测试内容

- 新增 `tests/test_cycling_fatigue_review_acceptance.py`。
  - 后端等价 payload 验收有功率骑行：`power_variability / pedaling_stability / power_hr / power_retention` 均可用。
  - 后端等价 payload 验收无功率骑行：`vi / power_per_hr / power_retention_pct` 均降级为空。
  - 后端等价 payload 验收功率样本不足：不回退到速度耐力，`head_speed / tail_speed` 仍为空。
  - 后端等价 payload 验收非骑行：不注入 `efficiency / durability` 的骑行功率口径。
  - 前端静态验收 cycling profile：包含“功率变异 / 踏频稳定性 / 功率效率 / 后程功率保持”。
  - 前端静态验收 cycling 主图：功率、心率、海拔、踏频，不以跑步配速/GAP/效率作为核心泳道。
  - 前端静态验收零推断：`_renderFatigueReviewMetrics` 不读取 `summary / curves / DOM / ECharts` 推导指标。
  - 前端静态验收非骑行回归：保留“运动效率 / 耐久指数 / 步频稳定性”。
- 新增 `docs/cycling_fatigue_review_acceptance_checklist.md`。
  - 供后续用真实活动 ID 做手工验收。
- 更新 `docs/fatigue_review_realignment_plan_v1.md`。
  - 标记 P5c 已完成端到端验收与降级场景固化。

## 5. 验收结果

- 使用等价 fixture / helper 构造场景，未依赖真实 DB 活动。
- 有功率骑行：已覆盖，通过。
- 无功率骑行：已覆盖，通过。
- 功率样本不足：已覆盖，通过。
- 非骑行回归：已覆盖，通过。
- 未发现需要修改生产代码的契约违背。

## 6. 前端零推断边界

- 前端仍只展示后端 `metrics`。
- 未从 `summary.avg_power / summary.avg_hr` 计算 `power_per_hr`。
- 未从 `curves.power` 计算 `power_retention_pct`。
- 未从 DOM、ECharts、`_lastFatigueReviewChartPayload`、points 推导指标。
- 未重算 NP。
- 未计算 FTP / IF / TSS / W/kg / 功率区间。

## 7. 发现的问题与处理

- 未发现生产代码契约违背。
- 未修改 `track.html`。
- 未修改 `main.py`。
- 未修改 `metrics_resolver.py`。
- 未修改 `llm_backend.py`。
- 未修改 DB schema 或 migrations。
- 未修改 AI prompt/schema。

## 8. 验证

运行命令：

```bash
python3 -m pytest tests/test_cycling_fatigue_review_acceptance.py
python3 -m pytest tests/test_cycling_fatigue_review_acceptance.py tests/test_cycling_fatigue_review_metrics.py tests/test_cycling_fatigue_review_snapshot.py tests/test_fatigue_review_contract_realignment.py
python3 -m pytest tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py
```

结果：

- `7 passed, 1 warning`。
- 骑行验收/metrics/snapshot/契约回归：`40 passed, 1 warning`。
- 前端质量门禁与详情页静态回归：`143 passed, 1 warning`。
- warning 为 urllib3 / LibreSSL 环境提示，与本次修改无关。

## 9. 剩余风险

- 本次使用等价 fixture / helper 场景，没有直接打开真实 UI 逐条活动截图验收。
- 后程功率保持仍可能受下坡、滑行、路口停顿、跟骑和路况影响；P5c 只验证降级和展示边界，不新增复杂场景识别。
- 如需进一步提升信息层级，可单独做骑行指标卡视觉重排。

## 10. 下一步

- 可选：用 `docs/cycling_fatigue_review_acceptance_checklist.md` 选取真实活动 ID 做人工验收。
- 可选：如果真实样本暴露视觉层级问题，再单独开骑行指标卡视觉重排任务。
