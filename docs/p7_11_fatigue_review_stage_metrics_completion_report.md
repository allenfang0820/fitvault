# P7.11 状态阶段与派生指标模块回正完成报告

## 1. 本阶段目标

P7.11 的目标是补齐设计稿中的状态阶段概览横条，并将现有派生指标区从较大的工程卡片进一步向设计稿的紧凑横向 Derived Metrics 条收敛。

本阶段不开放 AI，不改后端 API，不改算法链路，不改 DB schema。

## 2. 设计稿差距回正说明

P7.10 已完成分层 ECharts 主图，但设计稿中主图上方还有一个清晰的状态阶段概览横条，用绿色、黄色、橙色、红色表达稳定、漂移、疲劳、崩溃等阶段。P7.11 已新增该模块。

同时，设计稿中的 Derived Metrics 是紧凑横向指标条。P7.11 保留现有 8 个指标 DOM id，同时压缩指标卡高度、间距和视觉密度，使其更接近横向指标条。

## 3. 实际修改文件

- `track.html`
- `tests/test_v9_0_detail_tab_review.py`
- `tests/test_fatigue_review_quality_gate.py`
- `docs/fatigue_review_realignment_plan_v1.md`
- `docs/detail_tab_review_manual_test_checklist.md`
- `docs/p7_11_fatigue_review_stage_metrics_completion_report.md`

## 4. 状态阶段模块说明

DOM 位置：

- 新增 `fr-stage-overview-section`
- 位于核心状态 / 能力负荷指标区之后，P7.10 分层主图之前。

数据来源：

- 只读取 `data.fatigue_zones`。

字段使用：

- `start_km`
- `end_km`
- `level`
- `reason`
- `description`

渲染函数：

- `_renderFatigueReviewStageOverview(data.fatigue_zones || [])`

空态策略：

- 当 `fatigue_zones = []` 时显示“暂无后端疲劳阶段”。
- 明确不从曲线前端推导阶段。
- loading / error 态会清空状态阶段，避免旧活动残留。

## 5. 派生指标模块说明

原 DOM id：保留。

- `fr-hr-drift`
- `fr-decoupling`
- `fr-bonk`
- `fr-events-count`
- `fr-efficiency-score`
- `fr-durability-score`
- `fr-cadence-stability-score`
- `fr-training-load-value`

视觉收敛：

- 两组指标区新增 `fr-derived-metrics-strip`。
- 指标卡高度、间距、主值字号小幅压缩。
- 保持现有渲染函数 `_renderFatigueReviewMetrics(metrics)`，继续只消费后端 `metrics`。

暂未实现：

- HR Drift 曲线。
- Decoupling 曲线。
- Terrain Load 曲线。
- W' Balance 曲线。

这些字段若后端未提供，P7.11 不在前端伪造。

## 6. 数据契约核对

保持：

- `get_fatigue_review(activity_id)` 仍是复盘 Tab 唯一数据源。
- 状态阶段只读取 `data.fatigue_zones`。
- 派生指标只读取 `data.metrics`。
- 不从 `curves/speed/time/total_distance_m/points/DOM` 推导状态阶段。
- 不前端生成后端未提供的派生指标曲线。

## 7. AI 冻结核对

保持：

- `fr-ai-generate-btn` 继续 disabled。
- 保留 `aria-disabled="true"`。
- 不新增 onclick。
- 不触发 `call_llm`。
- 不写 DB。

## 8. UI 边界核对

保持：

- 不改活动详情顶部。
- 不改现有 Tab 系统。
- 不实现设计稿左侧全局导航。
- 不新增分享、导出、更多菜单。
- 不把复盘 Tab 改成独立页面。

## 9. 新增 / 调整测试

新增或调整静态门禁：

- 状态阶段 DOM 存在。
- 状态阶段只调用 `_renderFatigueReviewStageOverview(data.fatigue_zones || [])`。
- 状态阶段渲染使用 `start_km / end_km / level / reason / description`。
- 空 `fatigue_zones` 显示空态。
- 状态阶段函数不读取 `curves/speed/time/total_distance_m/points/DOM/call_llm`。
- 派生指标区具备 `fr-derived-metrics-strip`。
- 8 个既有指标主值 DOM id 保留。

## 10. 自动测试结果

```text
python3 -m pytest tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py

78 passed, 1 warning in 1.20s
```

说明：warning 来自本机 Python SSL / urllib3 环境提示，与 P7.11 前端契约和静态门禁无关。

## 11. 视觉检查结果

本阶段完成静态视觉结构检查：

- 状态阶段概览横条已位于分层 ECharts 主图之前。
- 状态阶段使用绿色 / 黄色 / 橙色 / 红色 / 灰色分段，对齐设计稿“阶段条”表达。
- 核心状态与能力负荷两组指标已收敛为更紧凑的横向 Derived Metrics 条。
- 720px 以下阶段条允许横向滚动，480px 以下指标卡单列，避免文字挤压。

未执行真实浏览器截图回归。本阶段不声称完成真实截图验收，截图验收顺延到后续 UI 定稿/视觉回归任务。

## 12. 剩余风险

- P7.11 只完成状态阶段横条和指标条密度收敛，不处理右侧关键摘要 / 触发因素 / 生理冲击点。
- 设计稿中的 W' Balance、Terrain Load 等若后端未提供字段，本阶段未前端伪造。
- 真实截图验收顺延到 P7.18。

## 13. 下一步建议

进入 P7.12「主图信息架构纠偏」，先回正主图视觉中心、状态阶段降权和右侧辅助栏比例；右侧关键摘要与底部模块顺延到 P7.16/P7.17。
