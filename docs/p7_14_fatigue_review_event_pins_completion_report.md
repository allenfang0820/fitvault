# P7.14 关键事件图钉与竖向参考线完成报告

## 任务目标

对照设计图 `/Users/fanglei/Downloads/5486EA08-F07D-48FC-A8BF-D997700D1B66 2.PNG`，回正复盘主图中的关键事件层：事件应以主图上方气泡 / 图钉呈现，并用竖向虚线贯穿多条指标泳道，而不是只作为普通图例或难以识别的单线标记。

## 设计图关系

本任务对应设计图“多维时间轴分析”区域上方的事件标注，如“漂移开始 / 效率下降 / 撞墙点”一类气泡，以及从这些事件位置向下贯穿心率、配速、效率、HR Drift、Decoupling、Terrain Load 等泳道的竖向参考线。

P7.14 只处理关键事件标记层，不重做 P7.13 左侧指标轨道，不重做状态阶段条，不重构右侧摘要，也不开放 AI 洞察。

## 实现内容

- 根据用户截图反馈修正后端事件为空的问题：新增 `_build_fatigue_review_collapse_events(...)`，由后端 Bonk 事件和 `fatigue_zones` 关键转折压缩生成 `collapse_events`。
- `track.html` 中将事件层拆分为跨泳道参考线和顶部图钉气泡两层。
- 新增 `_frLayeredEventTitle(event)`，标题只读取 `title / label / type / event_id`。
- 新增 `_frLayeredEventKmLabel(triggerKm)`，距离标签只读取 `trigger_km`。
- 新增 `_frLayeredEventPinMarkLine(insightEvents)`，强化 `pin` 图钉、气泡标题、公里数和 tooltip。
- 保留 `_frLayeredEventMarkLine(insightEvents)` 作为参考线构建器，各泳道继续绘制虚线。
- `_renderFatigueReviewEvents(events)` 右侧事件卡优先展示 `title / label`，与顶部气泡保持一致。
- 主图顶部预留事件气泡空间，避免气泡挤压泳道曲线。

## 契约约束

- 事件数组只读 `data.collapse_events`。
- `collapse_events` 由后端 Bonk 检测或后端 `fatigue_zones` 关键转折生成。
- 事件定位只读 `collapse_events[].trigger_km`。
- 事件标题只读 `title / label / type / event_id`。
- 事件说明只读 `description` 或后端空态文案。
- 前端不从 DOM、截图、曲线走势、`curves`、`speed`、`time`、`points`、`total_distance_m` 推导事件。
- 不写 DB。
- AI 洞察入口继续冻结，不触发 `call_llm`。

## 测试与文档

- 更新 `tests/test_fatigue_review_quality_gate.py`，新增 P7.14 静态门禁。
- 更新 `tests/test_fatigue_review_quality_gate.py`，新增 `fatigue_zones` 生成后端事件锚点的契约测试。
- 更新 `tests/test_v9_0_detail_tab_review.py`，新增详情 Tab P7.14 回归门禁。
- 更新 `docs/fatigue_review_realignment_plan_v1.md`，记录 P7.14 完成状态与边界。
- 更新 `docs/detail_tab_review_manual_test_checklist.md`，补充 P7.14 手工验收清单。
- 更新 `docs/js_api_contract.json`，补充 `collapse_events.title / label` 字段和 P7.14 事件锚点契约。

## 完成结论

P7.14 已完成。当前复盘主图事件层更接近设计图：用户第一眼可以看到主图上方事件气泡，事件位置用竖向虚线贯穿分层泳道，并且所有事件事实仍保持后端权威数据边界。
