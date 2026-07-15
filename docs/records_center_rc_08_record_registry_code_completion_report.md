# RC-08 完成报告

## 任务目标

将 RC-03 冻结的四项跑步纪录定义实现为后端单一 Registry，替换分散硬编码的显示名称、比较方向、单位和优先级来源。

## 实际改动

- 在 `career_backend.py` 新增不可变 `RecordDefinition`。
- 新增 `RUNNING_RECORD_DEFINITIONS`、`RECORD_DEFINITIONS`、`get_record_definition()`、`iter_record_definitions()`、`validate_record_registry()`。
- Registry 覆盖四项 V1 跑步纪录：5K、10K、半程马拉松、马拉松。
- PB display label、Timeline title、Overview priority 改为从 Registry 派生。
- 保留 legacy `RUNNING_PB_DISTANCE_RANGES`，本任务不切换 Resolver 匹配规则，避免提前改变 active PB。
- 新增 `tests/test_career_record_registry.py`。

## 契约决定

- Registry rule version 为 `records-v1`。
- Registry metric 为 `elapsed_time_sec`，但正式 Performance Summary 尚未实现；当前 Resolver 仍使用 legacy 字段。
- `±3%` 定义已进入 Registry，但 Resolver 切换留给 RC-10。
- RC-08 不改变当前真实库 active PB 结果。

## 测试与结果

```bash
.venv312/bin/python -m pytest tests/test_career_record_registry.py -q
```

结果：

```text
5 passed
```

```bash
.venv312/bin/python -m pytest tests/test_career_pb_resolver.py tests/test_career_pb_api.py tests/test_career_timeline_pb_nodes.py -q
```

结果：

```text
22 passed
```

```bash
.venv312/bin/python -m py_compile career_backend.py tests/test_career_record_registry.py
```

结果：通过。

## 真实数据或人工验证

未执行真实库写入或 Resolver 重算。RC-02 已证明切换到 `±3%` 会改变 10K active，因此本任务刻意不切换匹配逻辑。

## 未完成项与残余风险

- `RUNNING_PB_DISTANCE_RANGES` 仍作为 legacy Resolver 范围保留，需 RC-10 替换。
- 当前 git diff 中 `career_backend.py` 包含 RC-08 前已有 Footprint/Memory 相关未提交改动；本任务未回退或修改这些无关内容。

## 下一任务

进入 `RC-09：规范化 Performance Summary`。
