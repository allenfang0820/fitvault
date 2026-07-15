# RCV2-01 完成报告：多运动 Activity 事实源与真实数据审计

完成时间：2026-07-14

## 任务目标

确认骑行、徒步、游泳和越野所需 canonical 字段、时间语义、采样完整度和真实数据覆盖。

## 交付物

- `docs/records_center_v2_rcv2_01_execution_prompt.md`
- `docs/records_center_v2_rcv2_01_activity_fact_source_audit.md`
- `docs/records_center_v2_rcv2_01_completion_report.md`
- 已刷新 `docs/records_center_v2_rolling_contract_summary.md`
- 已更新 `docs/运动生涯记录中心V2（多运动纪录）开发任务清单.md`

## 核心结论

- 普通骑行 94 条，电助力 2 条；普通骑行中 67 条有可用功率流，27 条不能生成持续时间功率纪录。
- 徒步 7 条、登山 5 条、步行 38 条，均有距离、时间、轨迹和海拔，但三者必须分离。
- 游泳 2 条，均为公开水域；无真实泳池样本。
- 越野跑真实样本为 0。
- 当前 `duration_sec/duration` 主要来自 FIT `total_timer_time`，不能无条件视为 elapsed time。
- 体重有同步快照，但不是正式活动日期级历史体重事实表，W/kg 仍需门禁。

## 验证结果

```bash
.venv312/bin/python -m pytest tests/test_fit_sync.py -k "normalized_power or laps_json or activity_list" -q
```

结果：`14 passed, 105 deselected in 2.22s`

```bash
.venv312/bin/python -m py_compile profile_backend.py fit_engine.py metrics_resolver.py main.py career_backend.py
```

结果：通过

只读库检查：

- 审计前 DB 修改时间：`1784001529`
- 审计后 DB 修改时间：`1784001529`
- 结论：未写真实库

## Diff 复核

- 本任务只新增/更新文档和任务清单状态。
- 未修改业务代码、测试、真实数据库或打包产物。
- 没有把未验证运动标为 available。
- 没有从标题或文件名提升运动类型置信度。

## 下一任务

`RCV2-02 Golden fixtures 与算法可行性样本冻结`。

重点输入：

- 泳池和越野必须用脱敏 fixture 补足真实样本缺口。
- 骑行 fixture 必须覆盖 0W、缺失、非 1Hz、暂停、断点和尖峰。
- 海拔 fixture 必须覆盖 GPS 尖峰和平滑/连续爬升。
