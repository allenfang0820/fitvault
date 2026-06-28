# P4 骑行复盘主图模式完成报告

## 1. 本次目标

- 执行 `docs/p4_cycling_fatigue_review_chart_prompt.md`。
- 让骑行活动复盘主图区 ECharts 与跑步不同。
- 骑行主图默认优先展示 `功率 + 心率 + 海拔`，并支持踏频图层。
- 保持复盘 Tab 唯一数据源为 `get_fatigue_review(activity_id)`。
- 不改后端算法、不改 AI prompt/schema、不改 DB。

## 2. 现状调查

- `chartPayload` 原先未包含 `sport_type / power_curve / cadence_curve`。
- `_applyFatigueReviewLayerVisibility(...)` 原先只支持 `hr / speed / gap / efficiency / altitude / grade / terrainLoad / zones / events`。
- `_renderFatigueReviewLayeredEcharts(...)` 原先 laneDefs 固定为跑步语义：心率、配速、GAP、效率、海拔、坡度、地形负荷。
- `fr-layer-toggle-row` 原先没有功率和踏频开关。
- 现有静态测试对跑步 laneDefs 和图层开关有强断言，需要在不破坏跑步契约的前提下扩展骑行模式。

## 3. 实现内容

- `chartPayload`：
  - 新增 `sport_type: data.sport_type`。
  - 新增 `power_curve: data.curves && data.curves.power`。
  - 新增 `cadence_curve: data.curves && data.curves.cadence`。
  - 距离轴继续只来自 `data.curves.distance`。
- 图层开关：
  - 新增 `data-fr-layer-toggle="power"`。
  - 新增 `data-fr-layer-toggle="cadence"`。
  - `_applyFatigueReviewLayerVisibility(...)` 仅在视图 payload 副本中清空 `power_curve / cadence_curve`，不改变 `_lastFatigueReviewChartPayload`。
- ECharts laneDefs：
  - 新增 `_fatigueReviewChartSportMode(sportType)`，将 `cycling / road_cycling / mountain_biking` 归为 `cycling`。
  - 新增 `_fatigueReviewChartLaneDefs(activityData)`。
  - cycling lane 默认顺序为：功率、心率、海拔、踏频、坡度、地形负荷。
  - running/general lane 保留原有：心率、配速、GAP、效率、海拔、坡度、地形负荷。
- 空态：
  - cycling 空态纳入 `power / hr / altitude / cadence / grade / terrain_load`。
  - cycling 空态文案改为“后端未返回可绘制的功率、心率、海拔、踏频、坡度或地形负荷曲线。”。

## 4. 契约保持不变

- 数据源：复盘主图仍只消费 `get_fatigue_review(activity_id)` 返回的 `data.curves` 与 `data.display_curves`。
- 前端零推断：未从速度、配速、心率、DOM、ECharts series 或 points 推导功率/踏频。
- AI 边界：未改 `__FATIGUE_REVIEW_INSIGHT__` prompt/schema，也未新增 AI 调用。
- 后端边界：未改 `main.py / llm_backend.py / metrics_resolver.py`，未改 DB schema。
- 图层开关：仍是 view-only，不写 DB、不写 localStorage/sessionStorage、不调用 AI。

## 5. 明确不做

- 未新增速度辅助 lane 到骑行主图。
- 未在前端补算 power/cadence。
- 未重算骑行评分、FTP、IF、TSS、W/kg。
- 未专项化指标卡展示。
- 未改后端曲线生成或指标算法。

## 6. 验证

运行命令：

```bash
python3 -m pytest tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py
python3 -m pytest tests/test_cycling_fatigue_review_snapshot.py tests/test_cycling_fatigue_review_metrics.py tests/test_fatigue_review_contract_realignment.py
```

结果：

- 前端/详情页静态契约：`140 passed, 1 warning`。
- 骑行后端契约回归：`26 passed, 1 warning`。
- warning 均为 urllib3 / LibreSSL 环境提示，与本次 P4 修改无关。

## 7. 剩余风险

- 非骑行场景仍保留页面上的功率/踏频开关；无对应曲线时不会渲染 lane。后续如需更精细体验，可按 sport mode 动态隐藏或禁用。
- 骑行主图现在不显示速度 lane；若产品后续希望加入速度辅助层，应作为独立 P4b 任务明确契约。
- 功率/踏频曲线质量完全依赖后端 P1/P3 契约，本任务不做前端修复或补齐。

## 8. 下一步

- P5：骑行复盘指标卡展示专项化。
- P4b 可选：骑行图层开关按运动类型动态显隐。
- P3b 可选：power-based efficiency / durability 语义改造。
