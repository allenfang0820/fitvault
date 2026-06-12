# P7.13 左侧指标轨道与分层泳道回正完成报告

## 1. 本阶段目标

P7.13 的目标是让复盘主图从“技术上分层”进一步回正为设计图中可扫读的多泳道分析图。

本阶段重点补齐左侧指标轨道，让用户不依赖顶部图例，也能直接从左侧识别每条泳道代表的指标。

本阶段不开放 AI，不改后端 API，不改算法链路，不改 DB schema。

## 2. 设计图对应关系与纠偏结果

执行前已回看设计图：

- `/Users/fanglei/Downloads/5486EA08-F07D-48FC-A8BF-D997700D1B66 2.PNG`

本任务对应设计图中的三个区域：

- “多维时间轴分析”主图区
- 主图左侧指标列表
- 每条曲线对应的分层泳道

当前实现与设计图的主要差距：

- P7.12 后主图已成为视觉中心，但每条泳道仍主要依赖 yAxis 名称和顶部图例识别。
- 顶部图例距离曲线较远，无法承担设计图中左侧指标列表的读图入口职责。
- yAxis 名称和曲线左侧数值混在一起，仍有文字拥挤风险。

本次纠偏结果：

- 新增左侧 `fr-lane-rail` 指标轨道。
- 每个轨道项包含编号、颜色、指标名和单位。
- 轨道项顺序与 ECharts 实际 lanes 顺序一致。
- 顶部图例降权为辅助说明。
- ECharts `yAxis.name` 弱化为空，指标身份交给左侧轨道。

本次未处理的相邻模块：

- 不实现 P7.14 关键事件图钉和气泡。
- 不重做 P7.15 状态阶段条最终视觉。
- 不重构 P7.16 右侧关键摘要。
- 不开放 AI 洞察。

## 3. 当前实现问题复盘

P7.10 已完成多 grid / 多 yAxis 分层，P7.12 已让主图成为视觉中心。但截图反馈中的“不同折线代表的指标应该在折线左侧，更直观”尚未解决。

P7.13 因此把识别体系从顶部图例迁移到左侧轨道，让主图阅读顺序更接近设计图。

## 4. 左侧指标轨道实现说明

`track.html`：

- 新增 `fr-chart-body`，作为左侧轨道和 ECharts 画布的并排容器。
- 新增 `fr-lane-rail`，作为左侧指标轨道。
- 新增 `_renderFatigueReviewLaneRail(lanes)`。

轨道渲染规则：

- 只接收 `_renderFatigueReviewLayeredEcharts(...)` 实际筛选出的 `lanes`。
- 不读取 DOM、截图、曲线走势或前端推导字段。
- 空 `lanes` 时显示“等待后端曲线”空态。
- 缺距离轴或全部曲线为空时调用 `_renderFatigueReviewLaneRail([])`，避免旧活动轨道残留。

每个轨道项展示：

- 编号：`index + 1`
- 颜色：`lane.color`
- 指标名：`lane.name`
- 单位：`lane.unit`

## 5. 分层泳道可读性调整

- `fr-chart-body` 使用 `132px + 1fr` 的桌面布局。
- 720px 以下左侧轨道改为横向滚动，避免挤压图表。
- ECharts `yAxis.name` 设置为空，避免与左侧轨道重复显示指标名称。
- 顶部图例字号、宽度和透明度降低，作为辅助说明存在。
- 图表左边距从 `72` 调整为 `46`，减少重复文字占位。

## 6. 契约约束核对

保持：

- 复盘页面唯一数据源仍为 `get_fatigue_review(activity_id)`。
- 主图曲线只读 `data.curves`。
- 距离轴只读 `data.curves.distance`。
- 左侧轨道只由实际可绘制 `lanes` 渲染。
- 不从 `speed/time/total_distance_m/points/DOM` 重建距离或补算指标。
- 不改 `main.py` / `llm_backend.py`。
- AI 入口继续 disabled，不触发 `call_llm`。
- 不写 DB。

## 7. 修改文件列表

- `track.html`
- `tests/test_fatigue_review_quality_gate.py`
- `tests/test_v9_0_detail_tab_review.py`
- `docs/fatigue_review_realignment_plan_v1.md`
- `docs/detail_tab_review_manual_test_checklist.md`
- `docs/p7_13_fatigue_review_lane_rail_completion_report.md`

## 8. 自动测试结果

```text
python3 -m pytest tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py

83 passed, 1 warning in 1.37s
```

说明：warning 来自本机 Python SSL / urllib3 环境提示，与 P7.13 前端契约和静态门禁无关。

## 9. 手工视觉检查结论

本阶段完成代码级视觉结构检查：

- 主图内部已有左侧指标轨道容器。
- 轨道与 ECharts 画布并排。
- 轨道信息由实际 lanes 生成，空曲线不生成假轨道。
- 顶部图例已降权。
- 窄屏下轨道转为横向滚动。

未执行真实浏览器截图回归。本阶段不声称完成截图验收，截图验收顺延到 P7.18。

## 10. 尚未解决的问题

- 关键事件图钉、气泡和竖向参考线留给 P7.14。
- 状态阶段条连续分段最终视觉留给 P7.15。
- 右侧关键摘要、生理冲击点和建议面板重组留给 P7.16。
- 底部图例、开关和轻交互控制感留给 P7.17。

## 11. 下一步建议

进入 P7.14「关键事件图钉与竖向参考线」。

P7.14 执行前必须再次查看设计图与本次子任务的关系，重点对照设计图主图内的事件图钉、气泡标签和跨泳道竖向参考线。
