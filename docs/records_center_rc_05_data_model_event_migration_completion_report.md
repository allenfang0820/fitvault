# RC-05 完成报告

## 任务目标

在兼容现有 `career_pb_records` 的前提下，冻结历史链、审计事件、唯一性、索引、migration 和失败回滚方案。

## 实际改动

- 新增 `docs/records_center_rc_05_data_model_event_migration_contract.md`。
- 更新 `docs/records_center_rolling_contract_summary.md`。
- 更新 `docs/运动生涯记录中心（PB功能）开发任务清单.md` 中 `RC-05` 状态和当前下一任务。
- 未修改业务代码或真实数据库。

## 契约决定

- 继续使用 `career_pb_records`，不新建同义 records 表。
- 新增结构化字段：`evidence_key`、`source_mode`、`sport_scope`、`previous_record_id`、`resolver_version`、`confirmed_at`、`rejected_at`、`invalidated_at`、`decision_source`、`decided_at`。
- 新增 append-only `career_record_events`。
- 使用 active scope partial unique index；Windows/SQLite 不支持时必须事务检查 fallback。
- `value` 保持 TEXT 兼容，但所有比较必须按 `value_unit` 转数值。
- migration 必须事务化、幂等、失败 rollback 后旧 active 可读。

## 测试与结果

回归验证：

```bash
.venv312/bin/python -m pytest tests/test_career_pb_resolver.py tests/test_career_pb_api.py tests/test_career_timeline_pb_nodes.py -q
```

结果：

```text
22 passed
```

## 真实数据或人工验证

本任务只冻结数据模型，不对真实库执行 migration。

## 未完成项与残余风险

- active partial unique index 需要在 RC-12 实现时验证当前 SQLite 版本和 Windows 打包环境。
- 若旧库已经存在多个 active 冲突，migration 必须输出冲突报告并停止，不得静默修复。

## 下一任务

进入 `RC-06：API、ViewModel 与错误状态契约冻结`。
