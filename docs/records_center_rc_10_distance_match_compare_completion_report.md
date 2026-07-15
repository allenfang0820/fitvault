# RC-10 完成报告

## 任务目标

实现统一 `±3%` 标准距离匹配、唯一纪录类型选择和整数秒成绩比较。

## 实际改动

- 在 `career_backend.py` 新增 `match_record_definition(summary, definitions=...)`。
- 在 `career_backend.py` 新增 `compare_record_performance(candidate_value, current_value)`。
- 新增 Registry 匹配边界、运行时冲突、成绩比较测试。
- 正式写表 Resolver 暂未切换到新匹配函数，避免提前改变 active PB；后续状态迁移/重建任务统一接入。

## 契约决定

- 标准距离匹配使用包含边界的 `abs(actual-standard)/standard <= 0.03`。
- 多定义运行时冲突抛出 `ValueError`，不静默选择。
- 成绩比较使用整数秒；更快刷新，相同秒不刷新，更慢不刷新。
- 首条纪录 improvement 为 `null`。
- 非正候选时间判为 invalid。

## 测试与结果

```bash
.venv312/bin/python -m pytest tests/test_career_record_registry.py -q
```

结果：

```text
10 passed, 11 subtests passed
```

```bash
.venv312/bin/python -m pytest tests/test_career_record_registry.py tests/test_career_pb_resolver.py tests/test_career_pb_api.py tests/test_career_timeline_pb_nodes.py -q
```

结果：

```text
34 passed, 11 subtests passed
```

```bash
.venv312/bin/python -m py_compile career_backend.py tests/test_career_record_registry.py
```

结果：通过。

## 真实数据或人工验证

未写真实库。RC-02 已证明正式切换到 `±3%` 会改变 10K active，因此本任务只提供纯函数层能力。

## 未完成项与残余风险

- Legacy `RUNNING_PB_DISTANCE_RANGES` 仍服务当前写表 Resolver。
- RC-13/RC-15/RC-16 需要在状态迁移和重建闭环中正式应用新匹配/比较函数。

## 下一任务

进入 `RC-11：置信度、原因码与候选生成`。
