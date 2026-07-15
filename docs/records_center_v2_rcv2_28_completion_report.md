# RCV2-28 完成报告：Route Signature 与同路线匹配 candidate-only

## 结果

已完成隐私安全的越野 Route Resolver 前置能力：可从 Activity 轨迹事实构建 hashed route signature，并在不保存完整轨迹的前提下判断同路线、同方向、反向、低重合、部分覆盖、长缺口和 GPS 跳点。

## 实现内容

- 新增 `TRAIL_ROUTE_MATCH_DEFAULT_CONFIG`：
  - 起终点容差 `100m`
  - 长度误差阈值 `5%`
  - 最小轨迹覆盖率 `95%`
  - 最小 corridor overlap `85%`
- 新增 `build_trail_route_signature()`：
  - 只输出 `route_key`、`direction_key`、起终点 anchor hash、shape hash、sample/corridor hash、距离与质量摘要。
  - 不输出真实坐标、完整轨迹、polyline、文件路径或设备信息。
- 新增 `match_trail_route_signatures()`：
  - 支持 `same`、`reverse`、`loop`、`unknown` 方向判定。
  - 输出 `coverage_ratio`、`overlap_ratio`、`length_error_ratio`、`match_score`、`decision`、`reason_codes`。
  - 同向同路线只返回 `candidate`，并带 `real_data_sample_missing`；反向/端点不符/长度不符/低覆盖/低重合返回 `ignored`。
- 新增 `build_trail_route_candidate_plan()`：
  - 生成 candidate-only 匹配计划，不接入 active record 状态机。
- 新增 `save_career_route_signature()` / `get_career_route_signature()` / `save_career_route_match()`：
  - 写入既有 `career_route_signatures` 与 `career_route_matches` 派生表。
  - 保存前执行 route safe JSON 校验。
- 新增测试 `tests/test_career_record_trail_route_signature.py`：
  - 覆盖 golden manifest 的同向、反向、低重合样本。
  - 覆盖部分路线、折返/loop、长缺口、GPS 跳点、阈值配置化、candidate plan 和持久化隐私安全。

## 契约确认

- Activity 仍是唯一事实源。
- Route signature/match 是派生数据，不是正式纪录。
- 本任务没有自动确认 route PR，没有写 active record。
- 本任务没有真实库写入；测试使用内存 SQLite。
- 未打包。

## 验证

```bash
.venv312/bin/python -m pytest tests/test_career_record_trail_route_signature.py tests/test_career_record_trail_activity_total.py -q
# 13 passed, 3 subtests passed

.venv312/bin/python -m pytest tests/test_career_record_schema_migration.py tests/test_career_record_v2_rebuild.py tests/test_career_records_v2_api.py tests/test_career_pb_api.py -q
# 33 passed, 3 subtests passed

.venv312/bin/python -m py_compile career_backend.py
# passed
```

## 后续

RCV2-29 可以基于本任务的 `candidate` route match，将 `route_total`、`segment`、`climb_segment` 转成 `trail_route_best_time` / `trail_segment_best_time` / `trail_climb_segment_best_time` evidence，并保持 candidate-only。
