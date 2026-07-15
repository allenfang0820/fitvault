# RCV2-30 工程级提示词：越野 Pace/GAP Curve 分析边界

## 目标

提供越野跑 Pace Curve 与 GAP Curve 的安全分析 ViewModel 和缓存能力，同时明确它们永远是 `analysis-only`，不得进入正式 PB/纪录状态机、Timeline 或 Achievement。

## 范围

- 在 `career_backend.py` 中新增 Trail Pace/GAP Curve resolver。
- 计算 1K、3K、5K、10K、20K、30K、50K 锚点；不足距离输出明确 unavailable reason。
- 支持 `all`、`season`、`last_42_days` 时间范围过滤。
- 输出来源 Activity/range 的安全引用。
- 将 GAP 算法版本、海拔输入状态、局限性写入 ViewModel。
- 可写入 `career_record_curve_cache`，但只保存 anchors/summary/quality，不保存 raw track/points/polyline。
- 新增测试覆盖 analysis-only 边界。

## 约束

- 不新增 `RecordDefinition`，不允许 `trail_pace_curve` / `trail_gap_curve` 作为 record evidence。
- 不文案化为“刷新越野 10K 正式纪录”。
- 不宣称考虑技术路况；GAP 仅为基于坡度/海拔输入的近似分析。
- 不保存完整轨迹、真实 GPS 点、可还原 polyline、本地路径、设备/账号/体重等敏感字段。
- 不写真实库；测试使用内存 SQLite。
- 不打包。

## 预期实现契约

- `resolve_trail_pace_gap_activity_curve(...)`：单 Activity 生成 pace/gap anchors。
- `build_trail_pace_gap_curve_viewmodel(...)`：按时间范围聚合多个 Activity，返回 best anchors 和 unavailable anchors。
- `save_trail_pace_gap_curve_cache(...)`：写入 `trail_pace_curve` / `trail_gap_curve` 派生缓存。
- ViewModel 中每个 available anchor 只包含 `activity_id`、`range`、`pace_sec_per_km/gap_sec_per_km`、`elapsed_time_sec`、`distance_m`、`reason_codes` 等安全字段。

## 验证命令

```bash
.venv312/bin/python -m pytest tests/test_career_record_trail_pace_gap_curve.py tests/test_career_record_schema_migration.py tests/test_career_record_registry.py -q
.venv312/bin/python -m pytest tests/test_career_records_v2_api.py tests/test_career_record_v2_rebuild.py tests/test_career_pb_api.py -q
.venv312/bin/python -m py_compile career_backend.py
```

## 完成定义

- 1K/3K/5K/10K/20K/30K/50K 锚点可用/不可用解释稳定。
- `all/season/last_42_days` 范围过滤有效。
- curve cache 隐私安全。
- 无路径可将 Pace/GAP Curve 写入 active record。
