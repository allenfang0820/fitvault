# RCV2-00 完成报告：V2 基线审计与滚动摘要初始化

完成时间：2026-07-14

## 任务目标

建立记录中心 V2 的可信起点，确认 V1 继承基线、V2 冻结目标、当前代码/API/前端状态、真实库决策和打包边界，并为后续任务创建滚动摘要。

## 交付物

- `docs/records_center_v2_rcv2_00_execution_prompt.md`
- `docs/records_center_v2_rolling_contract_summary.md`
- `docs/records_center_v2_rcv2_00_baseline_audit_completion_report.md`
- `docs/运动生涯记录中心V2（多运动纪录）开发任务清单.md` 状态更新

## 审计结论

- V2 任务清单共 45 项，`RCV2-00` 已完成，下一任务为 `RCV2-01 多运动 Activity 事实源与真实数据审计`。
- V1 记录中心已完成 RC-00 至 RC-27；旧 RC-28 至 RC-30 不再代表最终发布完成。
- 当前业务代码仍是 V1 Records/PB 基线：四项跑步 Registry、PB 状态机、事件、候选、增量、rebuild 和 `get_career_pb*` API。
- 当前 V2 通用 Catalog/Records API 尚未代码化；`docs/js_api_contract.json` 仍只登记 PB API 和事件/候选维护 API。
- 当前前端仍保留 V1 `career-pb-*` 结构和未交付骑行 PB 筛选项，这些是 V2 视觉重构时应清理的遗留硬编码。
- 真实库仍遵守“候选保留、不写入”；打包仍暂停。

## 验证结果

```bash
.venv312/bin/python -m pytest tests/test_career_record_registry.py tests/test_career_pb_resolver.py tests/test_career_pb_api.py tests/test_career_timeline_pb_nodes.py -q
```

结果：`41 passed, 13 subtests passed in 0.18s`

```bash
.venv312/bin/python -m py_compile career_backend.py main.py
```

结果：通过

```bash
.venv312/bin/python -m json.tool docs/js_api_contract.json
```

结果：通过

## Diff 复核

- 本任务只新增/更新文档和任务清单状态。
- 未修改业务代码、数据库、测试、打包脚本或发布产物。
- 未执行真实库写入、staging apply、打包、签名或公证。
- 工作区原有大量未提交改动未被回退或整理。

## 下一任务边界

`RCV2-01` 应执行只读多运动事实源审计，复核骑行、徒步、游泳、越野跑所需 canonical 输入和真实数据覆盖。该任务仍不得写真实库，也不得把标题/文件名直接提升为高置信运动类型。
