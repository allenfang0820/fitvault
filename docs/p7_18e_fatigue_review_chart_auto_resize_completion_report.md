# P7.18E 复盘分层图窗口自适应完成报告

## 任务目标

用户反馈调整窗口大小后，复盘分层折线图不能随窗口变化自适应，出现图表区域与右侧面板重叠或宽度不正确的问题。

## 问题判断

这不是后端数据问题，而是前端图表布局生命周期问题：

- ECharts 在首次渲染、切 Tab、切图层时会 resize。
- 但窗口尺寸变化、容器宽度变化、右侧布局挤压后，没有持续监听容器尺寸。
- 因此 canvas / grid 可能保持旧宽度，造成视觉错位。

## 契约约束

- 不启用 AI 洞察，不新增 `call_llm`，不修改 AI prompt。
- 不写 DB，不新增持久化字段。
- 不从 DOM、截图、ECharts 像素、活动标题、设备、路线或 `points` 推导运动事实。
- 新增逻辑只监听容器尺寸并调用 ECharts `resize()`，属于布局修正，不改变后端 snapshot。

## 实现内容

- 新增复盘分层图自适应状态：
  - `_fatigueReviewChartResizeObserver`
  - `_fatigueReviewChartResizeBound`
- 新增绑定函数：
  - `_bindFatigueReviewChartAutoResize()`
  - 监听 `window.resize`
  - 使用 `ResizeObserver` 监听 `fr-chart-body` 和 `fatigue-review-chart`
- 新增解绑函数：
  - `_unbindFatigueReviewChartAutoResize()`
  - 关闭/清理复盘时移除窗口监听
  - 断开 `ResizeObserver`
- 在复盘图表成功渲染后绑定自适应监听。
- 在空态、关闭详情、销毁 `fatigue-review-chart` 时解绑。

## 验收结果

- 调整窗口大小时，复盘分层图会随容器重新 resize。
- 关闭复盘或销毁图表时不会留下重复监听。
- 不影响其他使用 `renderProfileAnalysisChart()` 的页面。
