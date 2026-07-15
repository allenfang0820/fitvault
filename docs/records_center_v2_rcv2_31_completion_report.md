# RCV2-31 完成报告：越野 Catalog、API、fixture 与测试闭环

## 结果

已完成越野记录中心 API surface 闭环：Catalog 能区分越野整次纪录 candidate-only、route/segment PR candidate-only、Pace/GAP analysis-only；新增安全路线对比 ViewModel/API；候选、曲线、路线对比均通过隐私安全测试。

## 实现内容

- 增强 `trail_running` Catalog capabilities：
  - `activity_total_records.state = candidate_only`
  - `route_segment_pr.state = candidate_only`
  - `route_segment_pr.uses_elapsed_time = true`
  - `route_segment_pr.uses_moving_time = false`
  - `pace_gap_curve.state = analysis_only`
  - `pace_gap_curve.creates_record = false`
- 新增 `get_trail_route_comparison_viewmodel()`：
  - 只读取 `career_route_matches` 派生匹配摘要。
  - 返回 direction、score、coverage、overlap、length error、decision、reason codes 和安全 source refs。
  - 不返回 route signature 原文、完整轨迹或可还原路线。
  - `summary.verified_real_data = false`，避免 fixture 通过被误读为真实验收。
- 新增 pywebview API wrapper：`get_trail_route_comparison()`。
- 更新 `docs/js_api_contract.json`：
  - Catalog 描述补充越野 capabilities。
  - 新增 `get_trail_route_comparison` 契约。
- 新增测试 `tests/test_career_records_trail_api_surface.py`：
  - Catalog 状态。
  - 当前 records 空态与 candidates。
  - Trail curve API。
  - Route comparison API。
  - Contract 文案和安全字段。

## 契约确认

- 没有新增 route/segment active 写入路径。
- 没有新增 Pace/GAP record definition。
- 不因 fixture 全绿宣称真实数据 verified。
- 不写真实库；测试使用内存 SQLite。
- 未打包。

## 验证

```bash
.venv312/bin/python -m pytest tests/test_career_records_trail_api_surface.py tests/test_career_record_trail_route_segment_resolver.py tests/test_career_record_trail_pace_gap_curve.py -q
# 14 passed

.venv312/bin/python -m pytest tests/test_career_records_v2_api.py tests/test_career_record_registry.py tests/test_records_center_v2_golden_fixtures.py tests/test_career_pb_api.py -q
# 39 passed, 13 subtests passed

.venv312/bin/python -m py_compile career_backend.py main.py
# passed
```

## 后续

RCV2-32 可进入前端多运动页面外壳、Catalog 页签和当前纪录视图。前端必须消费本任务后端 Catalog/API，不得硬编码越野状态或自行推断 candidate/analysis 可见性。
