# RC-01 完成报告

## 任务目标

确认跑步 PB 应读取的 canonical 距离与 elapsed time 字段，回答 `duration`、`duration_sec`、moving time、elapsed time 的真实语义和历史数据可用性。

## 实际改动

- 新增 `docs/records_center_rc_01_activity_metric_source_audit.md`。
- 更新 `docs/records_center_rolling_contract_summary.md`。
- 更新 `docs/运动生涯记录中心（PB功能）开发任务清单.md` 中 `RC-01` 状态和当前下一任务。
- 未修改业务代码，未写入 SQLite。

## 契约决定

- 距离 canonical 建议：优先 `dist_km * 1000` 得到 `distance_m`；`distance` 仅作为确认单位后的兜底。
- 计时 canonical 必须是 `elapsed_time_sec`；当前 `duration/duration_sec` 同源且来自 `total_timer_time`，不能直接作为正式 elapsed 口径。
- 旧数据需要由 Performance Summary 输出 `time_quality` 和 `reason_codes`；仅有 `duration_sec` 且无 elapsed 证据时，最高进入候选。
- 当前真实库无明确跑步机样本，跑步机规则后续应按候选策略冻结。

## 测试与结果

只读真实库审计完成：

- DB：`/Users/fanglei/.fitvault/user_profile.db`
- active Activity：253
- active running Activity：95
- running `duration == duration_sec`：95
- running `dist_km > 0`：95
- running 轨迹 elapsed 与 duration 基本一致：84
- running 轨迹 elapsed 明显大于 duration：8

回归验证：

```bash
.venv312/bin/python -m pytest tests/test_career_pb_resolver.py tests/test_career_pb_api.py tests/test_career_timeline_pb_nodes.py -q
```

结果：

```text
22 passed
```

## 真实数据或人工验证

本任务以只读方式审计真实 SQLite。没有执行 migration、Resolver 写入或正式 PB 重算。

## 未完成项与残余风险

- 当前数据库未存储单独的 `elapsed_time_sec`；RC-09 需要实现 Performance Summary 规范化输出。
- 真实库暂无跑步机样本，后续只能先以契约和测试夹具覆盖。
- `duration_sec` 在标准距离样本中目前看起来安全，但非标准样本已出现 timer time 小于 elapsed 的证据，后续不能将字段名当作口径保证。

## 下一任务

进入 `RC-02：真实数据库与 ±3% 迁移影响审计`。
