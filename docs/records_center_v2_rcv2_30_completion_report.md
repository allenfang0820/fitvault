# RCV2-30 完成报告：越野 Pace/GAP Curve 分析边界

## 结果

已完成越野 Pace Curve / GAP Curve 的 analysis-only resolver、ViewModel 和缓存能力。该能力只服务分析展示和对比，不注册正式 RecordDefinition，不生成 RecordEvidence，不进入 active record、Timeline 或 Achievement。

## 实现内容

- 新增 `TRAIL_PACE_GAP_ANCHOR_DISTANCES_M`：
  - `1K / 3K / 5K / 10K / 20K / 30K / 50K`
- 新增 `resolve_trail_pace_gap_activity_curve()`：
  - 单 Activity 计算 pace/GAP anchors。
  - 不足距离输出 `activity_shorter_than_window`。
  - 每个可用 anchor 仅输出安全来源：`activity_id + range`。
- 新增 `build_trail_pace_gap_curve_viewmodel()`：
  - 支持 `all`、`season`、`last_42_days` 时间范围。
  - 聚合多个 Activity，按距离锚点选择 pace 最优的分析 anchor。
- 新增 `save_trail_pace_gap_curve_cache()`：
  - 同时写入 `trail_pace_curve` 与 `trail_gap_curve` cache。
  - curve payload 只包含 `anchors/summary/gap_algorithm/quality`，不保存 raw track、GPS 点或 polyline。
- GAP ViewModel 明确包含：
  - `algorithm_version`
  - `elevation_input`
  - `limitations`: `analysis_only_not_record`、`does_not_model_technical_terrain`、`grade_adjustment_is_approximate`
- 新增测试 `tests/test_career_record_trail_pace_gap_curve.py`：
  - 锚点可用/不可用解释。
  - all/season/last_42_days 范围过滤。
  - cache 隐私安全。
  - `trail_pace_curve` / `trail_gap_curve` 不能作为 record evidence。

## 契约确认

- 不文案化为“刷新越野 10K 正式纪录”。
- 不宣称考虑技术路况。
- 不写真实库；测试使用内存 SQLite。
- 未打包。

## 验证

```bash
.venv312/bin/python -m pytest tests/test_career_record_trail_pace_gap_curve.py tests/test_career_record_schema_migration.py tests/test_career_record_registry.py -q
# 36 passed, 16 subtests passed

.venv312/bin/python -m pytest tests/test_career_records_v2_api.py tests/test_career_record_v2_rebuild.py tests/test_career_pb_api.py -q
# 21 passed

.venv312/bin/python -m py_compile career_backend.py
# passed
```

## 后续

RCV2-31 可整合越野 Catalog、API、fixture 与测试闭环：正式整次纪录 candidate-only，route/segment candidate-only，Pace/GAP curve analysis-only。
