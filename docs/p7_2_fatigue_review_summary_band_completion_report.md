# P7.2 顶部分析摘要带完成报告

## 1. 任务目标

在 P7.0 设计边界和 P7.1 信息架构基础上，升级复盘 Tab 内部顶部分析摘要带，让用户进入复盘后第一眼看到数据状态、风险提示、事件/疲劳区间状态和 AI 入口冻结状态。

本阶段不改活动详情 Modal 顶部，不改 Tab 系统，不改后端、算法、AI 后端或数据库。

## 2. 修改文件

- `track.html`
- `tests/test_v9_0_detail_tab_review.py`
- `tests/test_fatigue_review_quality_gate.py`
- `docs/fatigue_review_realignment_plan_v1.md`
- `docs/detail_tab_review_manual_test_checklist.md`
- `docs/p7_2_fatigue_review_summary_band_completion_report.md`

## 3. UI 变化摘要

- 在现有 `fr-status-strip` 内升级分析摘要带。
- 新增 `fr-summary-desc`，展示运动类型、建议接入状态和后端 disclaimer。
- 新增 `fr-curve-status-pill`，展示后端可用曲线组数或曲线不足。
- 新增 `fr-risk-pill`，展示后端 Bonk 风险状态。
- 新增 `fr-ai-status-pill`，展示 AI 待开放状态。
- 保留 `fr-data-source-pill / fr-distance-axis-pill / fr-event-pill`，并统一 loading、error、success 三态。

## 4. 数据字段来源说明

- `data.curves.distance`：距离轴状态。
- `data.curves.hr/speed/altitude/grade/gap/efficiency`：曲线接入状态，仅统计后端数组存在性。
- `data.metrics.bonk_risk`：风险状态。
- `data.metrics.hr_drift`：摘要中的心率漂移状态。
- `data.collapse_events`：事件数量。
- `data.fatigue_zones`：疲劳区间数量。
- `data.sport_type`：运动类型描述。
- `data.advice`：建议是否接入。
- `data.disclaimer`：数据边界说明。

## 5. 空态与错误态说明

- loading：摘要带显示读取后端权威快照中，各状态标签为待加载。
- error：摘要带显示复盘数据不可用，距离轴缺失、曲线不足，且不补算事实字段。
- `curves.distance` 为空：显示距离轴缺失。
- 可绘曲线为空：显示曲线不足。
- `collapse_events / fatigue_zones` 为空：显示事件 0、疲劳带 0。
- `advice` 为空：显示建议待接入。

## 6. 契约约束确认

- `get_fatigue_review(activity_id)` 仍是复盘 Tab 唯一数据源。
- 前端没有从 speed/time/total_distance_m/points/DOM 推导事实字段。
- `curves.distance` 仍是图表 X 轴、疲劳带和事件定位的唯一后端权威距离来源。
- 摘要带只消费 `curves / metrics / fatigue_zones / collapse_events / sport_type / advice / disclaimer`。
- 字段缺失时展示空态、弱化态或“待接入”，不补算。
- 未写 DB，未改 canonical 数据，未让 AI 输出参与指标计算。
- 未实现草图右侧首页、活动、日历等全局导航，也未新增分享/导出区。

## 7. AI 入口冻结确认

- `fr-ai-generate-btn` 仍为 disabled。
- `fr-ai-generate-btn` 仍有 `aria-disabled="true"`。
- `fr-ai-generate-btn` 无 onclick。
- `fr-ai-status-pill` 显示 `AI 待开放`。
- 本阶段不触发 `call_llm`。

## 8. 测试结果

已执行：

```bash
python3 -m pytest tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py
```

结果：48 passed, 1 warning。

说明：warning 为本地 Python `urllib3` / LibreSSL 环境提示，与 P7.2 UI 改造无关。

## 9. 未实现内容

- 未重排核心指标驾驶舱，留给 P7.3。
- 未改主图容器与图例，留给 P7.4。
- 未改事件与疲劳区间解释区，留给 P7.5。
- 未开放 AI 洞察入口。

## 10. 下一步建议

进入 P7.3 核心指标驾驶舱，重排核心状态与能力负荷指标卡，但仍只读取后端 `metrics`。
