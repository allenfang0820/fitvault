# P7.18 复盘 UI 定稿验收与主线回归收口完成报告

## 1. 本阶段目标

P7.18 的目标是对复盘 UI 纠偏成果做主线回归收口，确认当前复盘 Tab 已经可以作为后续 P8 AI 洞察复核的稳定 UI 基线。

本阶段不继续大幅改 UI，不开放 AI 洞察，不修改后端算法，不修改 DB schema。

## 2. 对照设计稿的验收结论

已覆盖设计稿“分析页”的核心内容：

- 顶部活动详情和 Tab 系统继续沿用项目现有设计，复盘 Tab 等价于设计稿“分析”页。
- 运动摘要 / 派生指标区域已通过分析摘要带、核心状态、能力与负荷模块承载。
- 状态阶段概览已进入主图容器内部，作为主图前的状态带，不再单独抢占首屏中心。
- 多维时间轴分析已成为视觉中心，主图为多泳道分层结构。
- 左侧指标轨道已承载指标识别职责，包含泳道名称、颜色和单位。
- 关键事件已通过图钉 / 竖向参考线表达，锚点来自后端事件。
- 右侧辅助栏已包含关键摘要、上下文、崩溃触发因素、生理冲击点、状态区间和建议。
- 底部控制已收敛为图层状态和图层开关，不再保留重复事件时间线。

明确不属于本项目 P7 范围：

- 设计稿最右侧的首页、活动、日历、统计、训练、设备、设置等全局导航。
- 设计稿顶部分享、导出、更多等全局动作。
- 将复盘 Tab 改造成独立页面。

仍未完全覆盖或顺延项：

- 设计稿底部的负荷与能量分析、状态解释引擎、对比分析等大模块未按原样完整复刻；当前版本以右侧摘要和底部图层控制承载核心读图任务。
- W' Balance 等后端未稳定提供的专项指标未由前端伪造。

## 3. 主图验收结论

主图已具备可冻结基线：

- `fr-chart-section` 是复盘 Tab 的主视觉中心。
- `fr-stage-overview-section` 位于主图容器内，处于标题和画布之间，视觉权重已降级。
- `fr-chart-body / fr-lane-rail / fatigue-review-chart` 同属主图结构。
- ECharts 分层图使用多泳道，泳道包括心率、配速、GAP、效率、海拔、坡度、地形负荷。
- 左侧轨道承担主要指标识别，避免所有指标挤在 yAxis 文字里。
- 关键事件图钉与竖向参考线来自 `collapse_events[].trigger_km`。
- 疲劳带背景来自 `fatigue_zones`。
- 地形负荷使用独立柱形泳道，位置来自 `curves.distance`，数据来自 `curves.terrain_load`。

## 4. 模块验收结论

状态阶段：

- 只读取 `data.fatigue_zones`。
- 使用 `start_km / end_km / level / reason / description`。
- 空数组显示空态，不从曲线补算稳定 / 漂移 / 疲劳 / 崩溃阶段。

左侧轨道：

- 由实际可绘制 `lanes` 渲染。
- 空曲线时清空轨道，避免旧活动残留。
- 720px 以下具备响应式降级策略。

事件图钉：

- 只读取 `data.collapse_events`。
- 只用 `trigger_km` 定位。
- 标题读取 `title / label / type / event_id`，说明读取 `description` 或后端空态文案。

右侧栏：

- `关键摘要` 来自 `metrics / collapse_events / fatigue_zones`。
- `崩溃触发因素` 只读 `collapse_events`。
- `生理冲击点` 只读 `metrics.hr_drift / decoupling / training_load / bonk_risk / events`。
- `建议` 只读 `data.advice`，免责声明只读 `data.disclaimer`。

底部控制：

- `fr-chart-footer` 保留图层状态和图层开关。
- 图层开关只影响当前 ECharts 视图，不请求后端、不写 DB、不触发 AI。
- 底部重复事件时间线已删除，事件职责回归主图图钉和右侧摘要。

## 5. 数据契约核对

通过。

- `get_fatigue_review(activity_id)` 仍是复盘 Tab 唯一事实数据源。
- 主图曲线只来自 `data.curves`。
- X 轴只来自 `data.curves.distance`。
- 疲劳区间只来自 `data.fatigue_zones`。
- 关键事件只来自 `data.collapse_events`。
- 右侧摘要、建议和状态说明只读取后端白名单字段。
- 前端没有从 DOM、截图、ECharts 像素、活动标题、设备、points 或曲线走势生成事实结论。
- `shadow_diff / shadow_diff_json / diff` 进入前端主展示时仍会触发契约错误。

## 6. AI 冻结核对

通过。

- `fr-ai-generate-btn` 仍为 `disabled`。
- 保留 `aria-disabled="true"`。
- 按钮文案仍为“AI 洞察待开放”。
- 按钮 DOM 未绑定 `onclick="onFatigueReviewAiInsight()"`。
- 当前 P7.18 不新增前端 `call_llm` 触发路径。
- `onFatigueReviewAiInsight()` 保留为 P8 预备调用链，但 P7.18 不开放入口。

## 7. 自动测试结果

```bash
python3 -m pytest tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py
# 97 passed, 1 warning in 1.40s

python3 -m pytest tests/test_fatigue_review_e2e_contract.py tests/test_fatigue_review_snapshot_realignment.py tests/test_fatigue_review_ai_insight_p6.py
# 46 passed, 1 warning in 0.80s
```

warning 均为本地 Python `urllib3` / LibreSSL 环境提示，不是 P7.18 回归失败。

## 8. 手工检查清单

本轮已完成静态手工核对：

- 对照设计稿确认 P7 只吸收“分析页”，不实现全局导航和顶部分享 / 导出。
- 核对主图 DOM、左侧轨道、事件图钉、状态阶段、地形负荷、右侧栏和底部控制均存在。
- 核对 P7.9-P7.18F 纠偏报告链条完整。
- 核对 P7.19 冻结报告已给出进入 P8 的冻结判断。
- 核对 P8.0 报告已存在，且 P8.0 仍未解除 AI 按钮冻结。

本轮未执行真实浏览器截图回归，也未启动 pywebview 桌面应用做人工截图验收。因此本报告不声称完成新的截图对比，只基于已有纠偏报告、设计稿复核、代码结构和自动测试做主线收口。

## 9. 是否允许进入 P8

允许进入 P8。

判断依据：

- P7 UI 主线已形成稳定基线。
- 主图、泳道、图钉、状态带、右侧摘要、底部控制均已落位。
- 自动测试通过。
- AI 入口仍冻结，没有被 P7 UI 纠偏提前打开。
- 已有 P8.0 开放前契约复核报告，且 P8.0 结论为允许进入 P8.1 最小闭环打开按钮。

## 10. 剩余风险和下一步建议

剩余风险：

- 真实截图验收需在用户实际运行环境继续观察，尤其是长活动、多事件、窄屏和窗口缩放场景。
- 当前 UI 未原样复刻设计稿底部全部分析卡片，而是按项目契约收敛为右侧摘要和底部图层控制。
- P8 打开 AI 后，需要重点确认 AI Modal 不挤压 P7 冻结 UI，也不写入本地持久化缓存。

下一步建议：

- 若需要先备份，先提交并 push 当前 P7/P8.0 收口成果。
- 正式进入 P8.1「复盘 AI 洞察最小闭环打开按钮」。
- P8.1 只允许解除按钮冻结和接入最小调用闭环，不允许前端拼 prompt、传事实 payload、写 DB 或让 AI 输出参与指标计算。
