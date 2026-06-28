# P5 骑行复盘指标卡专项化完成报告

## 1. 本次目标

- 按 `docs/p5_cycling_fatigue_review_metric_cards_prompt.md` 执行 P5-cycling。
- 让骑行活动的复盘指标卡与跑步不同。
- 骑行指标卡突出 `metrics.power_variability` 与 `metrics.pedaling_stability`。
- 保持跑步/general 指标卡现有语义不回归。
- 不改后端算法、不改 AI prompt/schema、不改 DB。

## 2. 现状调查

- 指标卡 DOM：复盘页已有 8 张固定 `metric-card fr-metric-card`，主值/status/sub id 已稳定。
- 渲染函数：`_renderFatigueReviewMetrics(metrics, sportType)` 原先按固定 id 写入 8 张跑步/general 卡片。
- 现有文案：`FATIGUE_REVIEW_METRIC_COPY` 已有 cycling 文案，但没有 `power_variability / pedaling_stability` 用户可见卡片文案。
- 现有测试：质量门禁和 V9 详情页测试均断言 8 卡结构、指标卡文案、metrics-only 渲染边界。

## 3. 实现内容

- sport profile：
  - 新增 `_fatigueReviewMetricSportMode(sportType)`。
  - `cycling / road_cycling / mountain_biking` 进入 cycling profile。
  - running/general 继续走原指标卡 profile。
- card defs：
  - 新增 `_fatigueReviewMetricCardDefs(sportType)` 与 `_fatigueReviewMetricCardSlots()`。
  - 保持 8 张卡片 DOM 不变，通过 profile 动态切换 label、tooltip、`data-fr-metric` 与渲染数据源。
- cycling profile 顺序：
  - 关键证据：功率变异、心率漂移、踏频稳定性、能量断档风险。
  - 补充证据：状态下滑点、训练负荷、后程效率变化、后程保持参考。
- 渲染：
  - `功率变异` 只读 `metrics.power_variability.vi / level / confidence / avg_power / normalized_power / reasons`。
  - `踏频稳定性` 只读 `metrics.pedaling_stability.score / level / confidence / cv / decay_pct / reasons`。
  - cycling 分支不使用 `metrics.cadence_stability` 作为踏频稳定性来源。
- 降级文案：
  - 新增 `FATIGUE_REVIEW_METRIC_COPY.power_variability`。
  - 新增 `FATIGUE_REVIEW_METRIC_COPY.pedaling_stability`。
  - `_fatigueReviewMetricMissingReason(...)` 增加功率不足、踏频不足文案。
  - `_fatigueReviewMetricHeadline(...)` 增加功率变异和踏频稳定性的 headline 映射。
- 测试：
  - 新增 P5 质量门禁，验证 cycling profile 和 running/general profile 分离。
  - 新增 V9 静态契约测试，验证指标卡只读 metrics，不从 summary/curves/DOM/ECharts 推导。

## 4. 契约保持不变

- 数据源：指标卡仍只消费 `get_fatigue_review(activity_id)` 返回的 `data.metrics`，并用 `data.sport_type` 选择展示 profile。
- 前端零推断：未从 `summary / curves / speed / cadence / power / DOM / ECharts` 计算 VI、CV、decay 或 score。
- AI 边界：未改 `__FATIGUE_REVIEW_INSIGHT__` prompt/schema，未新增 AI 调用。
- 后端边界：未改 `main.py / llm_backend.py / metrics_resolver.py / fit_engine.py`，未改 DB schema。
- 主图边界：未改 P4 ECharts laneDefs。

## 5. 明确不做

- 未改后端算法。
- 未改 AI prompt/schema。
- 未改 DB。
- 未新增第 9、第 10 张指标卡。
- 未从 `summary.normalized_power / summary.avg_power` 计算 VI。
- 未从 `curves.cadence` 计算 CV、decay 或 score。
- 未实现 power-based efficiency / durability。

## 6. 验证

运行命令：

```bash
python3 -m pytest tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py
python3 -m pytest tests/test_cycling_fatigue_review_snapshot.py tests/test_cycling_fatigue_review_metrics.py tests/test_fatigue_review_contract_realignment.py
```

结果：

- 前端/详情页静态契约：`143 passed, 1 warning`。
- 骑行后端契约回归：`26 passed, 1 warning`。
- warning 均为 urllib3 / LibreSSL 环境提示，与本次 P5 修改无关。

## 7. 剩余风险

- 当前为了保持布局稳定，P5 复用 8 张既有卡片 DOM；如果后续需要完全不同的信息架构，可以单独做 P5b 视觉重排。
- `后程效率变化 / 后程保持参考` 在 cycling profile 中仍是辅助参考，尚未升级为 power-based efficiency / durability。
- 指标卡的 cycling profile 依赖 P3 后端事实指标；如果后端返回 unavailable，占位和降级文案会展示数据不足。

## 8. 下一步

- P6/P3b：power-based efficiency / durability。
- P4b：骑行图层开关按运动类型动态显隐。
- P5b 可选：骑行指标卡视觉布局专项设计。
