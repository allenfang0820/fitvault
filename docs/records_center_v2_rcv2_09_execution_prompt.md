# RCV2-09 工程级执行提示词

任务：V2 Registry 与动态 Catalog 代码化

目标：实现 V2 Registry/Catalog 单一真理源，代码化多运动 record definitions、Scope、availability 和 Catalog 派生，同时保持 V1 跑步纪录与旧 PB API 兼容。

输入摘要：

- `RCV2-03` 已冻结 V2 `RecordDefinition` 字段、family、source_mode、scope_dimensions、record keys 和 availability。
- `RCV2-06` 已冻结 Catalog API/ViewModel：sport tabs、groups、records、axis_direction、availability_state 等必须由后端 Registry 派生。
- 当前 `career_backend.py` 只有 V1 `RecordDefinition` 与四条 running 定义；`match_record_definition()` 是 V1 跑步整次距离 Resolver 路径。

前置依赖：`RCV2-03`、`RCV2-06`。

文件范围：

- 可写：`career_backend.py`、Registry/Catalog 测试、本文、完成报告、滚动摘要、任务清单。
- 禁止：schema migration、真实库、前端、`docs/js_api_contract.json`、打包产物。

冻结契约：

- 不运行新运动 Resolver，不写 V2 active/candidate。
- V1 `match_record_definition()` 仍只匹配跑步四项 `RUNNING_RECORD_DEFINITIONS`，不因 V2 多运动定义改变 V1 active 结果。
- `get_career_pb*` 兼容字段不破坏；`detail_link.source="career"` 保持。
- 未实现/未验收定义必须保留 `candidate_only` 或 `validation_required`，不得因代码化自动开放 active。
- model/analysis 项不得进入 active record definitions。

实施步骤：

1. 扩展 `RecordDefinition` dataclass，兼容 V1 字段并补齐 V2 字段。
2. 扩展白名单和 `validate_record_registry()`。
3. 代码化 V2 多运动 definitions。
4. 新增 Catalog 派生 helper：sport/group/record ViewModel。
5. 保持 V1 PB label、priority、source mode label 兼容。
6. 新增/扩展测试：唯一 key、白名单、V1 不变、Catalog 状态、dynamic scope、analysis/model 不 active。
7. 运行定向测试和 py_compile。
8. 更新滚动摘要和任务状态。

非目标：

- 不新增 V2 API bridge。
- 不实现 schema migration。
- 不实现新运动 Resolver。
- 不修改前端。
- 不写真实库。

验证：

- `.venv312/bin/python -m pytest tests/test_career_record_registry.py tests/test_records_center_v2_golden_fixtures.py -q`
- `.venv312/bin/python -m pytest tests/test_career_pb_resolver.py tests/test_career_pb_api.py -q`
- `.venv312/bin/python -m py_compile career_backend.py`

完成定义：

- Catalog 与 RCV2-03/06 契约一致；前端后续无需硬编码骑行/游泳/越野占位；V1 跑步 PB 回归通过。
