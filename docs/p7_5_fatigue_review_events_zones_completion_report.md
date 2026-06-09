# P7.5 事件与疲劳区间说明完成报告

## 1. 任务目标

在 P7.0-P7.4 基础上，升级复盘 Tab 右侧“关键事件”和“疲劳区间”说明区，让用户能清楚看到事件、疲劳区间的后端字段来源、位置字段和空态。

本阶段不改活动详情 Modal 顶部，不改 Tab 系统，不改后端、算法、AI 后端、契约 JSON 或数据库。

## 2. 修改文件

- `track.html`
- `tests/test_v9_0_detail_tab_review.py`
- `tests/test_fatigue_review_quality_gate.py`
- `docs/fatigue_review_realignment_plan_v1.md`
- `docs/detail_tab_review_manual_test_checklist.md`
- `docs/p7_5_fatigue_review_events_zones_completion_report.md`

## 3. UI 变化摘要

- 关键事件面板新增 `fr-events-boundary`。
- 新增疲劳区间面板 `fr-fatigue-zones-panel`。
- 新增 `fr-fatigue-zones-boundary`。
- 新增 `fr-fatigue-zone-list`。
- 新增 `_renderFatigueReviewZones(zones)`。
- `_renderFatigueReviewEvents(events)` 的空态和事件卡说明更明确。

## 4. 字段来源说明

| 区块 | 后端字段 |
|---|---|
| 关键事件列表 | `data.collapse_events` |
| 事件位置 | `collapse_events[].trigger_km` |
| 事件类型 | `collapse_events[].type` |
| 事件说明 | `collapse_events[].description` |
| 疲劳区间列表 | `data.fatigue_zones` |
| 区间位置 | `fatigue_zones[].start_km / end_km` |
| 区间等级 | `fatigue_zones[].level` |
| 区间说明 | `fatigue_zones[].reason / description` |

## 5. 空态与错误态说明

- `collapse_events = []`：显示“暂无关键事件”，主图不绘制事件标记。
- `fatigue_zones = []`：显示“暂无疲劳区间”，主图不绘制疲劳背景带。
- 事件缺少描述：显示“后端未返回事件描述”。
- 区间缺少说明：显示“后端未返回区间说明”。
- 位置字段缺失：显示 `?`，不从曲线或距离轴推导。

## 6. 契约约束确认

- `get_fatigue_review(activity_id)` 仍是复盘 Tab 唯一数据源。
- 关键事件只读取 `data.collapse_events`。
- 疲劳区间只读取 `data.fatigue_zones`。
- 前端没有从 speed/time/total_distance_m/points/DOM/curves 推导事件或区间。
- 侧栏事件/区间与主图事件/疲劳带使用同一后端数组。
- 字段缺失时展示空态或 `?`，不补算。
- 未写 DB，未改 canonical 数据，未让 AI 输出参与指标计算。
- 未实现草图右侧首页、活动、日历等全局导航，也未新增分享/导出区。

## 7. AI 入口冻结确认

- `fr-ai-generate-btn` 仍为 disabled。
- `fr-ai-generate-btn` 仍有 `aria-disabled="true"`。
- `fr-ai-generate-btn` 无 onclick。
- 本阶段不触发 `call_llm`。

## 8. 测试结果

已执行：

```bash
python3 -m pytest tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py
```

结果：57 passed, 1 warning。

说明：warning 为本地 Python `urllib3` / LibreSSL 环境提示，与 P7.5 UI 改造无关。

## 9. 未实现内容

- 未改上下文与建议侧栏，留给 P7.6。
- 未做响应式专项视觉验收，留给 P7.7。
- 未开放 AI 洞察入口。

## 10. 下一步建议

进入 P7.6 建议与上下文侧栏，优化 `context_tags / advice / disclaimer` 的呈现和缺失态。
