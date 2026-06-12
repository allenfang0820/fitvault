# P7.10 分层 ECharts 主图实现完成报告

## 1. 本阶段目标

P7.10 的目标是把复盘主图从当前心率 / 速度 / GAP 叠加图，回正为设计稿方向的多维分层时间轴。

本阶段不开放 AI，不改后端 API，不改算法链路，不改 DB schema。

## 2. 设计稿差距回正说明

P7.9 已确认当前叠加图不是设计稿完成态。P7.10 已将 `fatigue-review-chart` 改为分层 ECharts 主图：

- 多个指标独立泳道显示，避免互相遮挡。
- 所有泳道共用后端 `curves.distance` 距离轴。
- 疲劳带作为背景区间进入各泳道。
- 事件以竖向参考线按公里位置跨泳道对齐。

## 3. 实际修改文件

- `track.html`
- `tests/test_v9_0_detail_tab_review.py`
- `tests/test_fatigue_review_quality_gate.py`
- `docs/fatigue_review_realignment_plan_v1.md`
- `docs/detail_tab_review_manual_test_checklist.md`
- `docs/p7_10_fatigue_review_layered_echarts_completion_report.md`

## 4. ECharts 实现说明

是否多 grid：是。

- `_renderFatigueReviewLayeredEcharts(...)` 中按可用曲线动态生成 `grid[]`。

是否多 yAxis：是。

- 每个泳道生成独立 `yAxis[]`。
- 每条曲线绑定对应 `xAxisIndex / yAxisIndex`。

已实现泳道：

- 心率：`hr_curve`
- 速度：`speed_curve`
- 海拔：`altitude_curve`
- 效率：`efficiency_curve`
- GAP：`gap_curve`
- 坡度：`grade_curve`

X 轴来源：

- `data.curves.distance` 经 `chartPayload.distance_curve` 传入。
- 缺距离轴时继续显示空态。

疲劳带来源：

- `data.fatigue_zones`
- 使用 `start_km / end_km / level`
- 作为 `markArea` 背景区间进入分层主图。

事件标记来源：

- `data.collapse_events`
- 使用 `trigger_km / type / description`
- 作为 `markLine` 竖向参考线对齐距离轴。

## 5. 数据契约核对

保持：

- `get_fatigue_review(activity_id)` 仍是复盘 Tab 唯一数据源。
- 分层主图只读取后端白名单曲线、`fatigue_zones` 和 `collapse_events`。
- 不从 `speed/time/total_distance_m/points/DOM` 推导事实字段。
- 不新增 HR Drift / Decoupling / Terrain Load 曲线；这些若后端未提供，顺延到 P7.11 标记待接入。

## 6. AI 冻结核对

保持：

- `fr-ai-generate-btn` 继续 disabled。
- 保留 `aria-disabled="true"`。
- 不新增 onclick。
- 不触发 `call_llm`。
- 不写 DB。

## 7. UI 边界核对

保持：

- 不改活动详情顶部。
- 不改现有 Tab 系统。
- 不实现设计稿左侧全局导航。
- 不新增分享、导出、更多菜单。
- 不把复盘 Tab 改成独立页面。

## 8. 新增 / 调整测试

新增或调整静态门禁：

- `fatigue-review-chart` 使用 `_renderFatigueReviewLayeredEcharts(...)` 专用分支。
- 分层主图存在多个 `grid / xAxis / yAxis`。
- 分层主图使用 `axisPointer.link` 联动所有距离轴。
- 分层主图读取 `hr_curve / speed_curve / altitude_curve / efficiency_curve / gap_curve / grade_curve`。
- 疲劳带使用 `_frLayeredMarkArea(fatigueZones)`。
- 事件使用 `_frLayeredEventMarkLine(insightEvents)` 和 `markLine`。
- 禁止 `_distanceFromSpeedTime / total_distance_m / points / DOM / call_llm` 出现在分层主图 helper 中。

## 9. 自动测试结果

```text
python3 -m pytest tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py
75 passed, 1 warning in 1.24s
```

warning 为本地 Python 环境的 `urllib3` / LibreSSL 提示，不是 P7.10 失败。

## 10. 视觉检查结果

已尝试启动本地应用：

```text
python3 main.py
```

启动失败于本地 Watchdog/FSEvents 环境：

```text
SystemError: Cannot start fsevents stream. Use a kqueue or polling observer instead.
```

该问题与 P7.7/P7.8/P7.9 的视觉检查阻塞一致，不是 P7.10 自动测试失败。本阶段以静态测试和代码检查兜底，不声称完成真实截图验收。

## 11. 剩余风险

- P7.10 只完成主图分层，不处理状态阶段概览横条。
- HR Drift / Decoupling / Terrain Load 曲线若后端未提供，本阶段不前端伪造。
- 事件卡片与分层图的精细联动后续可在 P7.14 随事件图钉模块一起增强。
- 真正截图验收顺延到 P7.18。

## 12. 下一步建议

进入 P7.11「状态阶段与派生指标模块回正」，补齐设计稿中的状态阶段横条和派生指标横向指标条。
