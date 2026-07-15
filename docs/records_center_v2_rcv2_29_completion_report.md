# RCV2-29 完成报告：越野赛段 PR 与 Scope 状态闭环

## 结果

已完成越野 route total、segment、climb segment 三类 PR evidence resolver，并接入既有 Scope 感知状态机。当前 registry 仍为 `candidate_only`，因此不会自动生成 active 纪录；后续真实越野样本验收后，可以沿用同一 evidence 与状态机比较逻辑开放正式状态。

## 实现内容

- 新增 `build_trail_route_record_evidences()`：
  - 只接受 RCV2-28 route match 中 `decision=candidate` 且方向为 `same/loop` 的匹配。
  - 生成 `trail_route_best_time` / `source_mode=route_total` evidence。
  - 使用 whole-activity elapsed time，暂停计入成绩；不使用 moving time。
  - Scope 固定为 `sport_scope=trail_running + route_key`。
- 新增 `build_trail_segment_record_evidences()`：
  - 普通 segment 生成 `trail_segment_best_time`。
  - climb/uphill segment 生成 `trail_climb_segment_best_time`。
  - 每条 evidence 都携带 Activity 内 `start_sec/end_sec/duration_sec/start_distance_m/end_distance_m/segment_key` range。
- 新增 `_dedupe_best_elapsed_record_evidences()`：
  - 同一批 resolver 输出中，按 `record_key + source_mode + scope_hash` 只保留 elapsed time 最小的 evidence。
- 新增 `build_trail_route_segment_record_evidences()` 与 `apply_trail_route_segment_records()`：
  - 默认 `dry_run=True`。
  - `dry_run=False` 只调用既有 `apply_record_evidence_state()`；由于 registry 是 `candidate_only`，结果进入候选，不写 active。
- 新增测试 `tests/test_career_record_trail_route_segment_resolver.py`：
  - 覆盖同向 route evidence、反向不产 evidence、同 Scope 批内最快唯一、segment/climb range、candidate-only apply 幂等、dry-run 不写库。

## 契约确认

- 不实现公开 CR/KOM/QOM。
- 不用 moving time、GAP 或分析曲线作为正式 PR。
- 不保存 raw track、GPS 点、polyline、路径、设备/账号/体重等敏感信息。
- 不写真实库；测试使用内存 SQLite。
- 未打包。

## 验证

```bash
.venv312/bin/python -m pytest tests/test_career_record_trail_route_segment_resolver.py tests/test_career_record_trail_route_signature.py tests/test_career_record_v2_state.py -q
# 23 passed

.venv312/bin/python -m pytest tests/test_career_record_v2_rebuild.py tests/test_career_records_v2_api.py tests/test_career_record_evidence.py tests/test_career_pb_api.py -q
# 27 passed, 5 subtests passed

.venv312/bin/python -m py_compile career_backend.py
# passed
```

## 后续

RCV2-30 可进入越野 Pace/GAP Curve 分析边界；该类 curve 只能作为 analysis，不得写入正式纪录或 route/segment PR。
