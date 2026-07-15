# RC-00 完成报告

## 任务目标

建立记录中心开发的可信起点，确认现有 PB Resolver、schema、API、前端、Timeline、Achievement 和测试的真实状态，并划定当前脏工作区边界。

## 实际改动

- 新增 `docs/records_center_rc_00_baseline_audit.md`。
- 新增 `docs/records_center_rolling_contract_summary.md`。
- 更新 `docs/运动生涯记录中心（PB功能）开发任务清单.md` 中 `RC-00` 状态和当前下一任务。
- 未修改业务代码。

## 契约决定

- 当前实现仍以 `career_pb_records` 和 `get_career_pb()` 为兼容基线。
- 当前 PB Resolver 的距离范围、计时字段和状态行为只作为基线记录，不作为记录中心 V1 最终规则。
- Timeline 当前明确排除 PB 独立节点；后续如要接入“纪录刷新事件”，必须由后端契约迁移，前端不得临时拼接。
- `RC-01` 必须先回答 `duration` / `duration_sec` 的 elapsed time 语义，之后才能冻结比较规则。

## 测试与结果

```bash
.venv312/bin/python -m pytest tests/test_career_pb_resolver.py tests/test_career_pb_api.py tests/test_career_timeline_pb_nodes.py -q
```

结果：

```text
22 passed in 0.16s
```

## 真实数据或人工验证

本任务未执行真实数据库扫描，符合 RC-00 范围。真实库中距离和计时字段覆盖率由 `RC-01`、`RC-02` 以只读方式审计。

## 未完成项与残余风险

- 工作区存在大量 RC-00 前已有未提交改动，后续任务必须持续隔离文件边界。
- 当前 `docs/js_api_contract.json` 中 `get_career_pb` 的 line 字段可能与当前 `main.py` 实际行号不一致；RC-06/RC-17 更新 API 契约时需要一并修正。
- 当前前端仍显示“PB 记录/PB 档案”，且暴露骑行 PB 筛选项；这是 RC-07/RC-19 的后续范围。

## 下一任务

进入 `RC-01：Activity 距离与计时事实源审计`。
