# RCV2-36 完成报告：Overview、Timeline、Race 与 Achievement 联动

## 完成内容

- `career_backend.py` 新增 Records 下游集成守卫：
  - `get_career_records_downstream_integration()`
  - `_records_downstream_formal_records()`
  - `_records_downstream_formal_events()`
- Overview 集成摘要：
  - 只统计 `career_pb_records` 中 `active/superseded` 的正式纪录。
  - 输出 `by_sport` 与 `by_family`，供下游展示/验收使用。
  - 排除 `analysis_only/model_only/unavailable` 与 `analysis_curve/model_estimate`。
- Timeline 集成摘要：
  - 只消费正式 record events：`activated`、`activated_from_rebuild`、`user_confirmed`。
  - 使用 `career_record_events.id` 作为幂等键。
  - 排除 `candidate_created`、`detected`、`ignored`、`recalculated`、`user_rejected`。
- Race Archive 边界：
  - 明确 `consumes_records=false`。
  - 明确 `record_derived_race_count=0`。
  - 赛事事实仍由 Race Resolver 维护，不从纪录反推赛事。
- Achievement 边界：
  - 只允许正式 record event 作为触发来源。
  - candidate、curve/cache、model 均不触发。
- 新增 `tests/test_career_records_v2_downstream_integration.py`。

## 契约复核

- 候选纪录仍只在 `career_event_candidates`，不会进入 Overview formal record、Timeline formal event 或 Achievement trigger。
- Curve cache 只作为分析缓存，不触发正式下游效果。
- model/analysis 纪录按 family/catalog_state 排除。
- rebuild no-change / recalculated 事件不进入 Timeline/Achievement。
- Race Archive 不从 Records 反推赛事。
- helper 不返回 raw evidence payload、raw FIT、track、power stream、GPS、路径、schema、设备或体重历史。

## 验证

```bash
.venv312/bin/python -m pytest tests/test_career_records_v2_downstream_integration.py tests/test_career_overview_pb_summary.py tests/test_career_timeline_engine_closure.py tests/test_career_achievements_api.py -q
# 27 passed

.venv312/bin/python -m pytest tests/test_career_records_v2_api.py -q
# 6 passed

.venv312/bin/python -m py_compile career_backend.py main.py
# passed
```

## 自审结论

- 新增逻辑为 summary/guard surface，不改变现有 Race Resolver、Timeline node、Achievement Resolver 正式语义。
- 没有把 PB 独立节点重新加入 Timeline。
- 无阻塞项。
