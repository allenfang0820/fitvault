# P7.12 主图信息架构纠偏完成报告

## 1. 本阶段目标

P7.12 的目标是对复盘 Tab 的主图信息架构做源头纠偏，让“多维时间轴分析”重新成为复盘页的视觉中心。

本阶段不开放 AI，不改后端 API，不改算法链路，不改 DB schema。

## 2. 设计图对应关系与纠偏结果

执行前已回看设计图：

- `/Users/fanglei/Downloads/5486EA08-F07D-48FC-A8BF-D997700D1B66 2.PNG`

本任务对应设计图中的三个区域：

- “状态阶段概览”
- “多维时间轴分析”
- “右侧关键摘要”

当前实现与设计图的主要差距：

- 状态阶段区视觉权重过高，像独立重卡片，压住了主图。
- 主图外层高度和 ECharts 内部网格比例不足，多条曲线仍挤在中下部。
- 右侧栏宽度偏强，和主图争夺视觉焦点。

本次纠偏结果：

- 主图容器 `fr-chart-section` 提升为复盘主体视觉焦点。
- 状态阶段模块已移入主图容器，位于“多维时间轴分析”标题之后、画布之前，成为主图内的轻量上下文条。
- 分层 ECharts 内部网格降低顶部/底部留白，让泳道获得主要垂直空间。
- 右侧栏收窄为辅助解释区。

本次未处理的相邻模块：

- 不实现 P7.13 左侧指标编号 / 颜色 / 指标名轨道。
- 不深化 P7.14 事件图钉、气泡和竖向参考线。
- 不重构 P7.16 右侧关键摘要深层内容。
- 不实现 P7.17 底部图例与交互控件。

## 3. 当前实现问题复盘

截图反馈显示，P7.10/P7.11 虽然已具备分层主图和状态阶段横条，但仍存在三个视觉问题：

- 状态阶段跑到主图上方后体量过大。
- ECharts 泳道实际高度太窄，线条仍显得拥挤。
- 主图和右侧栏的主次关系不够像设计稿。

P7.12 因此优先处理结构权重，而不是继续微调颜色或文字。

## 4. 本次结构纠偏内容

`track.html`：

- `fr-layout` 右侧栏从 `300px` 收敛为 `260px`。
- `chart-container` 最小高度提升到 `640px`。
- `fatigue-review-chart` 画布最小高度提升到 `560px`。
- 720px 以下保留 `min-height: 280px`，避免小屏被大图撑破。
- `fr-stage-overview` 从主图前独立区块移入 `fr-chart-section`，放在标题之后、画布之前。
- `fr-stage-overview` 改为横向轻量摘要条：左侧为小标题，右侧为阶段轨道。
- `fr-stage-track` 空态改为横向轻量空态。
- 分层 ECharts 内部参数从 `topStart = 28 / bottomPad = 32` 回正为 `topStart = 5 / bottomPad = 8`。
- 分层 ECharts 网格左右边距微调为 `left: 72 / right: 56`，为后续左侧指标轨道预留基础。

## 5. 契约约束核对

保持：

- 复盘页面唯一数据源仍为 `get_fatigue_review(activity_id)`。
- 主图曲线只读 `data.curves`。
- 距离轴只读 `data.curves.distance`。
- 状态阶段只读 `data.fatigue_zones`。
- 事件参考只读 `data.collapse_events`。
- AI 入口继续 disabled，不触发 `call_llm`。
- 不改 `main.py` / `llm_backend.py`。
- 不写 DB。

## 6. 修改文件列表

- `track.html`
- `tests/test_fatigue_review_quality_gate.py`
- `tests/test_v9_0_detail_tab_review.py`
- `docs/fatigue_review_realignment_plan_v1.md`
- `docs/p7_fatigue_review_analysis_cockpit_information_architecture.md`
- `docs/detail_tab_review_manual_test_checklist.md`
- `docs/p7_9_fatigue_review_design_alignment_correction_completion_report.md`
- `docs/p7_10_fatigue_review_layered_echarts_completion_report.md`
- `docs/p7_11_fatigue_review_stage_metrics_completion_report.md`
- `docs/p7_12_fatigue_review_chart_architecture_correction_completion_report.md`

## 7. 自动测试结果

```text
python3 -m pytest tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py

80 passed, 1 warning in 1.36s
```

说明：warning 来自本机 Python SSL / urllib3 环境提示，与 P7.12 前端契约和静态门禁无关。

## 8. 手工视觉检查结论

本阶段完成代码级视觉结构检查：

- 主图区域高度和视觉权重已提升。
- 状态阶段模块已进入主图内部，并降权为标题下方的轻量摘要条。
- ECharts 内部泳道占比已扩大。
- 右侧栏已收敛为辅助宽度。

未执行真实浏览器截图回归。本阶段不声称完成截图验收，截图验收顺延到 P7.18。

## 9. 尚未解决的问题

- 左侧指标编号、颜色、名称轨道仍未实现，留给 P7.13。
- 关键事件图钉、气泡和竖向参考线仍需按设计图继续增强，留给 P7.14。
- 状态阶段条还不是最终设计稿连续分段视觉，留给 P7.15。
- 右侧关键摘要、生理冲击点和建议面板仍需重组，留给 P7.16。
- 底部图例、开关和轻交互控制感仍未实现，留给 P7.17。

## 10. 下一步建议

进入 P7.13「左侧指标轨道与分层泳道回正」。

P7.13 执行前必须再次查看设计图与本次子任务的关系，重点对照设计图主图左侧的编号、颜色、指标名称、勾选状态和每条泳道的阅读高度。
