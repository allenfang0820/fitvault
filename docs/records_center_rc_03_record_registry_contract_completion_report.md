# RC-03 完成报告

## 任务目标

冻结 V1 四项跑步纪录的唯一规则来源，消除代码、SQL、API 和前端各自硬编码口径的风险。

## 实际改动

- 新增 `docs/records_center_rc_03_record_registry_contract.md`。
- 更新 `docs/records_center_rolling_contract_summary.md`。
- 更新 `docs/运动生涯记录中心（PB功能）开发任务清单.md` 中 `RC-03` 状态和当前下一任务。
- 未修改业务代码、schema 或 UI。

## 契约决定

- V1 Registry 只包含 `running_5k`、`running_10k`、`running_half_marathon`、`running_marathon`。
- 标准距离统一使用包含边界的 `abs(actual-standard)/standard <= 0.03`。
- V1 `source_mode` 固定为 `activity_total`。
- 比较主值固定为整数秒 `elapsed_time_sec`，相同秒数不刷新。
- 首条纪录 `improvement = null`。
- Registry 初始化必须检测区间冲突；冲突配置直接失败，不静默选择定义。
- `duration_sec` 不是 Registry metric，后续必须由 Performance Summary 规范化为 `elapsed_time_sec`。

## 测试与结果

文档契约完成；业务代码未变。

回归验证：

```bash
.venv312/bin/python -m pytest tests/test_career_pb_resolver.py tests/test_career_pb_api.py tests/test_career_timeline_pb_nodes.py -q
```

结果：

```text
22 passed
```

## 真实数据或人工验证

RC-03 复用 RC-02 dry-run 结论作为迁移注意事项，不新增真实库写入。

## 未完成项与残余风险

- 区间冲突策略采用“配置失败”硬约束，优先级高于早期手册中的运行时兜底；若产品希望支持重叠定义，需要先回到手册修改契约。
- 半马 `event_date` 与 Activity 本地日期差异尚未冻结，需 RC-06 或数据层任务继续处理。

## 下一任务

进入 `RC-04：置信度、候选与状态机冻结`。
