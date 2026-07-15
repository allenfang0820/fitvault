# RC-09 完成报告

## 任务目标

为 PB Resolver 提供明确、最小、安全的距离、elapsed time、运动类型和质量摘要，消除直接猜测 Activity 字段语义。

## 实际改动

- 在 `career_backend.py` 新增 `_record_performance_summary(row)`。
- PB candidate 构建改为从 Performance Summary 读取 `sport`、`distance_m/distance_km`、`elapsed_time_sec`、`timer_time_sec`、`event_date`、质量字段和 reason codes。
- PB metadata 增加白名单 `performance_summary`，不包含 raw points、track_json 或 file path。
- 扩展 `tests/test_career_pb_resolver.py`，覆盖 summary 规范化和 metadata 安全边界。

## 契约决定

- 当前 Activity 表尚无独立可靠 `elapsed_time_sec`，因此 helper 以 legacy `duration/duration_sec` 生成兼容 `elapsed_time_sec`，并标记 `time_quality = semantics_unknown`。
- `timer_time_sec` 保留当前时长值，供 RC-11 置信度和候选机制使用。
- 距离优先 `dist_km`，转为整数 `distance_m`；`distance` 只作为兜底。
- RC-09 不改变当前 active PB 结果，不引入 candidate 状态。

## 测试与结果

```bash
.venv312/bin/python -m pytest tests/test_career_pb_resolver.py -q
```

结果：

```text
10 passed
```

```bash
.venv312/bin/python -m pytest tests/test_career_record_registry.py tests/test_career_pb_resolver.py tests/test_career_pb_api.py tests/test_career_timeline_pb_nodes.py -q
```

结果：

```text
29 passed
```

```bash
.venv312/bin/python -m py_compile career_backend.py tests/test_career_pb_resolver.py
```

结果：通过。

## 真实数据或人工验证

未写真实库。RC-01 的真实库审计结论已体现在 `time_quality = semantics_unknown` 的兼容策略中。

## 未完成项与残余风险

- 当前 helper 尚未从 FIT `total_elapsed_time` 或轨迹首尾时间生成可靠 elapsed；后续需要在更底层 Performance Resolver/导入链路中补白名单摘要。
- RC-11 需要使用 `time_quality/reason_codes` 决定 candidate，不应继续把 legacy timer time 全部自动确认。

## 下一任务

进入 `RC-10：标准距离匹配与成绩比较 Resolver`。
