# P7.15 状态阶段条视觉回正完成报告

## 任务目标

对照设计图 `/Users/fanglei/Downloads/5486EA08-F07D-48FC-A8BF-D997700D1B66 2.PNG`，将复盘页「状态阶段概览」回正为更接近设计稿的连续横向分段条。阶段条作为“多维时间轴分析”主图前的辅助摘要，不抢主图层级。

## 设计图关系

本任务对应设计图中的“状态阶段概览”区域：稳定、漂移、疲劳、崩溃等阶段以连续横向状态带呈现，并通过颜色和分段比例帮助用户快速理解活动状态变化。

P7.15 只处理状态阶段条，不重做 P7.13 左侧指标轨道，不重做 P7.14 事件图钉与竖向参考线，不重构 P7.16 右侧摘要，也不开放 AI 洞察。

## 实现内容

- `fr-stage-track` 调整为连续横向阶段带，增加高度、居中排版和虚线分隔。
- `_renderFatigueReviewStageOverview(zones)` 只渲染有效 `start_km / end_km` 的后端区间。
- 每段按 `end_km - start_km` 计算 `--fr-stage-grow / --fr-stage-basis`，形成相对长度占比。
- 每段显示阶段名、距离范围、占比和后端说明。
- 过窄区间自动使用 `compact` 样式，隐藏长说明，避免文字重叠。
- 空 `fatigue_zones` 或无有效区间继续显示空态，不补算阶段。

## 契约约束

- 阶段条只读取 `data.fatigue_zones`。
- 阶段位置只读取 `start_km / end_km`。
- 阶段等级只读取 `level`。
- 阶段说明只读取 `reason / description`。
- 不从 DOM、截图、ECharts、曲线走势、`curves`、`speed`、`time`、`points`、`total_distance_m` 推导阶段。
- 不改后端、不改 API、不写 DB。
- AI 洞察入口继续冻结，不触发 `call_llm`。

## 测试与文档

- 更新 `tests/test_fatigue_review_quality_gate.py`，新增 P7.15 阶段条视觉回正门禁。
- 更新 `tests/test_v9_0_detail_tab_review.py`，新增详情 Tab P7.15 回归门禁。
- 更新 `docs/fatigue_review_realignment_plan_v1.md`，记录 P7.15 完成状态与边界。
- 更新 `docs/detail_tab_review_manual_test_checklist.md`，补充 P7.15 手工验收清单。

## 完成结论

P7.15 已完成。当前状态阶段概览更接近设计稿中的连续阶段带：分段按后端区间长度表达占比，窄段有 compact 兜底，阶段事实仍全部来自后端 `fatigue_zones`。
