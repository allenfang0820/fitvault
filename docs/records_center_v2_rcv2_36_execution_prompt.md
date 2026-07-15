# RCV2-36 工程级提示词：Overview、Timeline、Race 与 Achievement 联动

## 目标

建立 Records V2 与 ACS 下游模块的安全集成守卫：Overview、Timeline、Race Archive、Achievement 只能消费正式纪录与正式事件，候选、curve cache、analysis/model、rebuild no-change 不得进入正式下游效果。

## 范围

- 在 `career_backend.py` 新增 Records downstream integration summary/helper。
- helper 只读取：
  - `career_pb_records` 中 `status in ('active', 'superseded')` 的正式纪录；
  - `career_record_events` 中正式刷新事件；
  - 不读取 `career_event_candidates` 作为正式来源；
  - 不读取 `career_record_curve_cache`、route comparison、model estimate 作为正式来源。
- 明确输出：
  - Overview 可消费的正式 record count、by_sport、by_family；
  - Timeline 可消费的正式 record event，按 event id 去重；
  - Race Archive 不从 Records 反推赛事；
  - Achievement 只可由正式 record event 触发；
  - excluded_sources 说明候选、curve/cache、model/no-change 的排除。
- 新增跨模块集成测试。

## 约束

- 不改变 Race Resolver、Achievement Resolver 的正式语义。
- 不把 PB 独立节点重新塞回 Timeline；Timeline 仍可用正式 PB badge/record event 辅助，但候选不进入 years/months/nodes。
- 不直接查询 raw evidence、raw FIT、track、power stream、GPS、路径、schema、设备或体重历史。
- 不写真实库，不打包。

## 预期文件

- `career_backend.py`
- `tests/test_career_records_v2_downstream_integration.py`
- `docs/records_center_v2_rcv2_36_completion_report.md`
- `docs/运动生涯记录中心V2（多运动纪录）开发任务清单.md`
- `docs/records_center_v2_rolling_contract_summary.md`

## 验证命令

```bash
.venv312/bin/python -m pytest tests/test_career_records_v2_downstream_integration.py tests/test_career_overview_pb_summary.py tests/test_career_timeline_engine_closure.py tests/test_career_achievements_api.py -q
.venv312/bin/python -m pytest tests/test_career_records_v2_api.py -q
.venv312/bin/python -m py_compile career_backend.py main.py
```

## 完成定义

- 正式 active/superseded 纪录可进入 Overview summary。
- 正式 record events 可作为 Timeline/Achievement 触发来源，且幂等去重。
- Race Archive 不从纪录反推赛事。
- 候选、curve/cache、model、rebuild no-change 均被排除并有测试覆盖。
