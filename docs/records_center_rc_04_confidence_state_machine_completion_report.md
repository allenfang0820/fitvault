# RC-04 完成报告

## 任务目标

冻结纪录从检测到候选、激活、替代、拒绝和失效的完整生命周期，以及每种状态的用户可见行为。

## 实际改动

- 新增 `docs/records_center_rc_04_confidence_state_machine_contract.md`。
- 更新 `docs/records_center_rolling_contract_summary.md`。
- 更新 `docs/运动生涯记录中心（PB功能）开发任务清单.md` 中 `RC-04` 状态和当前下一任务。
- 未修改业务代码、schema、API 或 UI。

## 契约决定

- 状态冻结为 `candidate`、`active`、`superseded`、`rejected`、`invalidated`。
- `confidence > 0.90` 才能自动确认；`0.70 <= confidence <= 0.90` 进入候选；`confidence < 0.70` 忽略正式 PB。
- 每个降级必须有稳定 `reason_codes`。
- 用户只能确认或拒绝候选；确认不是改成绩，拒绝不删除 Activity。
- rejected 同版本同 evidence 不再提示；Resolver 版本变化且 evidence 实质变化时才允许重新候选。
- active 失效后必须 invalidated 并回退下一有效纪录，回退不触发新纪录庆祝或 Achievement。

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

本任务为契约冻结，未新增真实库写入。候选矩阵使用 RC-01/RC-02 的真实案例校准。

## 未完成项与残余风险

- `confirmed_at`、`rejected_at`、候选确认后未激活的持久化形态需要 RC-05 数据模型冻结。
- 具体评分权重可在 RC-11 实现时微调，但不能删除评分维度和 reason codes。

## 下一任务

进入 `RC-05：数据模型、审计事件与迁移回滚冻结`。
