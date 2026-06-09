# P7.4 主图容器与图例完成报告

## 1. 任务目标

在 P7.0 设计边界、P7.1 信息架构、P7.2 顶部分析摘要带和 P7.3 核心指标驾驶舱基础上，升级复盘 Tab 内部主图分析区，强化“疲劳带 · 事件 · 曲线”的标题、图例和数据边界说明。

本阶段不改活动详情 Modal 顶部，不改 Tab 系统，不改后端、算法、AI 后端、契约 JSON 或数据库。

## 2. 修改文件

- `track.html`
- `tests/test_v9_0_detail_tab_review.py`
- `tests/test_fatigue_review_quality_gate.py`
- `docs/fatigue_review_realignment_plan_v1.md`
- `docs/detail_tab_review_manual_test_checklist.md`
- `docs/p7_4_fatigue_review_chart_container_completion_report.md`

## 3. UI 变化摘要

- 主图容器新增 `fr-chart-section`。
- 主图标题新增 `fr-chart-title / fr-chart-subtitle / fr-chart-boundary`。
- 图例新增 `fr-chart-legend`，明确心率、速度、GAP、疲劳带和事件来源。
- 新增 `fr-chart-axis-note`，展示 `distance_curve = data.curves.distance`。
- 保留 `fatigue-review-chart` 作为 ECharts 渲染目标。
- loading / error / success 三态会更新 X 轴说明。

## 4. 主图字段来源说明

| 主图元素 | 后端字段 |
|---|---|
| X 轴 | `data.curves.distance` |
| 心率曲线 | `data.curves.hr` |
| 速度曲线 | `data.curves.speed` |
| GAP 曲线 | `data.curves.gap` |
| 疲劳带 | `data.fatigue_zones` |
| 事件标记 | `data.collapse_events` |

## 5. 空态与错误态说明

- loading：轴说明显示 `distance_curve = data.curves.distance`。
- error：轴说明显示后端未返回权威距离轴。
- `curves.distance` 为空：`renderProfileAnalysisChart` 展示“复盘曲线数据不足 / 后端未返回权威距离轴”。
- 曲线部分字段为空：对应曲线不绘制或保持弱化状态，不补算。
- `fatigue_zones` 为空：不画疲劳背景带。
- `collapse_events` 为空：不画事件标记。

## 6. 图表渲染边界确认

- `openFatigueReview` 直接读取 `data.curves.distance` 构造 `chartPayload.distance_curve`。
- `fatigue_zones` 直接使用 `data.fatigue_zones || []`。
- `insight_events` 直接使用 `data.collapse_events || []`。
- `renderProfileAnalysisChart` 缺少 `distance_curve` 时展示空态。
- 未恢复 `_distanceFromSpeedTime()`。
- 未用 speed/time/total_distance_m 重建距离轴。

## 7. 契约约束确认

- `get_fatigue_review(activity_id)` 仍是复盘 Tab 唯一数据源。
- 前端没有从 speed/time/total_distance_m/points/DOM 推导事实字段。
- `curves.distance` 仍是主图 X 轴、疲劳带和事件定位的唯一后端权威距离来源。
- 主图只消费 `curves / fatigue_zones / collapse_events`。
- 字段缺失时展示空态、弱化态或隐藏对应图例，不补算。
- 未写 DB，未改 canonical 数据，未让 AI 输出参与指标计算。
- 未实现草图右侧首页、活动、日历等全局导航，也未新增分享/导出区。

## 8. AI 入口冻结确认

- `fr-ai-generate-btn` 仍为 disabled。
- `fr-ai-generate-btn` 仍有 `aria-disabled="true"`。
- `fr-ai-generate-btn` 无 onclick。
- 本阶段不触发 `call_llm`。

## 9. 测试结果

已执行：

```bash
python3 -m pytest tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py
```

结果：54 passed, 1 warning。

说明：warning 为本地 Python `urllib3` / LibreSSL 环境提示，与 P7.4 UI 改造无关。

## 10. 未实现内容

- 未改事件与疲劳区间解释区，留给 P7.5。
- 未改上下文与建议侧栏，留给 P7.6。
- 未开放 AI 洞察入口。

## 11. 下一步建议

进入 P7.5 事件与疲劳区间说明，重构关键事件列表、疲劳区间解释和空态。
