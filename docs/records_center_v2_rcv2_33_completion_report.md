# RCV2-33 完成报告：多运动演进图、功率/Pace Curve 与路线对比

## 结果

已在 Records Center V2 shell 中加入统一分析面板，支持从后端 ViewModel 读取纪录演进、派生曲线与越野路线对比。ECharts 可用时渲染图表；不可用时保留可访问列表 fallback。

## 实现内容

- 新增分析面板 DOM/CSS：
  - `career-record-analysis-panel`
  - `career-record-analysis-grid`
  - `career-record-chart-box`
  - `career-record-node-list`
- 新增通用 chart engine：
  - `careerRecordChartInstances`
  - `renderCareerRecordChart()`
  - `resizeCareerRecordCharts()`
  - `disposeCareerRecordCharts()`
  - 绑定 window resize。
- 当前纪录卡支持选中：
  - `selectCareerRecordForAnalysis()`
  - `onCareerRecordAnalysisKeydown()`
- 新增分析加载：
  - `loadCareerRecordAnalysis()`
  - 调用 `get_career_record_history`
  - 调用 `get_career_record_curve`
  - 越野调用 `get_trail_route_comparison`
- 新增可访问 fallback：
  - `careerRecordHistoryListHtml()`
  - `careerRecordCurveListHtml()`
  - `careerRecordRouteComparisonHtml()`

## 契约确认

- 前端只消费后端 History/Curve/Route Comparison ViewModel。
- 前端不解析 raw stream、raw track、points_json、track_json、fit_records 或 raw_records。
- Pace/GAP 曲线文案固定为“仅分析”，不标为 PB，不文案化为“刷新越野 10K 正式纪录”。
- 图表 y 轴方向读取后端 `axis_direction`。
- ECharts 实例在切换运动时 dispose，窗口 resize 时 resize。
- 未打包。

## 验证

```bash
.venv312/bin/python -m pytest tests/test_career_records_v2_chart_frontend.py tests/test_career_records_v2_frontend_shell.py -q
# 10 passed

.venv312/bin/python -m pytest tests/test_career_records_trail_api_surface.py tests/test_career_records_v2_api.py -q
# 9 passed

.venv312/bin/python -m py_compile career_backend.py main.py
# passed
```

## 后续

RCV2-34 可进入候选队列、确认/拒绝交互与解释文案。必须继续保持候选由后端状态机控制，前端不得改值。
