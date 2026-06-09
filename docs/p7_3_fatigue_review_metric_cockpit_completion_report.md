# P7.3 核心指标驾驶舱完成报告

## 1. 任务目标

在 P7.0 设计边界、P7.1 信息架构和 P7.2 顶部分析摘要带基础上，升级复盘 Tab 内部“核心状态区 + 能力与负荷区”的 8 张指标卡，使每张卡具备主值、状态标签和解释/空态文案。

本阶段不改活动详情 Modal 顶部，不改 Tab 系统，不改后端、算法、AI 后端、契约 JSON 或数据库。

## 2. 修改文件

- `track.html`
- `tests/test_v9_0_detail_tab_review.py`
- `tests/test_fatigue_review_quality_gate.py`
- `docs/fatigue_review_realignment_plan_v1.md`
- `docs/detail_tab_review_manual_test_checklist.md`
- `docs/p7_3_fatigue_review_metric_cockpit_completion_report.md`

## 3. UI 变化摘要

- 8 张指标卡均新增状态标签。
- 8 张指标卡均保持主值、状态标签、解释/空态文案三层结构。
- 保留所有既有主值 DOM id，避免破坏现有渲染和测试。
- 新增 `fr-events-sub`，让崩溃事件卡也拥有稳定解释容器。
- 优化指标卡 CSS，增加稳定高度、换行和状态标签样式。

## 4. 8 个指标卡字段来源说明

| 指标卡 | 后端字段 |
|---|---|
| 心率漂移 | `data.metrics.hr_drift` |
| 解耦率 | `data.metrics.decoupling` |
| Bonk 风险 | `data.metrics.bonk_risk` |
| 崩溃事件 | `data.metrics.events` |
| 运动效率 | `data.metrics.efficiency` |
| 耐久指数 | `data.metrics.durability` |
| 步频稳定性 | `data.metrics.cadence_stability` |
| 训练负荷 | `data.metrics.training_load` |

## 5. 空态与错误态说明

- 心率漂移缺失：显示数据不足。
- 解耦率缺失：显示数据不足。
- Bonk 风险缺失：显示待接入。
- 崩溃事件为空：显示暂无事件。
- 运动效率缺失：显示数据不足。
- 耐久指数缺失：显示数据不足。
- 步频稳定性缺失：显示设备未记录。
- 训练负荷缺失：显示待接入。

## 6. 契约约束确认

- `get_fatigue_review(activity_id)` 仍是复盘 Tab 唯一数据源。
- 指标卡只读取 `data.metrics` 对应字段。
- 前端没有从 speed/time/total_distance_m/points/DOM/curves 推导指标。
- 字段缺失时展示空态、弱化态或“待接入”，不补算。
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

结果：51 passed, 1 warning。

说明：warning 为本地 Python `urllib3` / LibreSSL 环境提示，与 P7.3 UI 改造无关。

## 9. 未实现内容

- 未改主图容器与图例，留给 P7.4。
- 未改事件与疲劳区间解释区，留给 P7.5。
- 未改上下文与建议侧栏，留给 P7.6。
- 未开放 AI 洞察入口。

## 10. 下一步建议

进入 P7.4 主图容器与图例，强化疲劳带、事件、曲线的视觉层级，仍只使用后端 `curves.distance` 作为 X 轴。
