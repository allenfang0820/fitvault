# RCV2-03 完成报告：V2 Record Registry、纪录族与 Scope 冻结

完成时间：2026-07-14

## 任务目标

把 V2 手册、真实数据审计和 golden fixtures 中的多运动规则转成无歧义 Registry 契约，供后续 `RCV2-09` 代码化。

## 交付物

- `docs/records_center_v2_rcv2_03_execution_prompt.md`
- `docs/records_center_v2_rcv2_03_registry_scope_contract.md`
- `docs/records_center_v2_rcv2_03_completion_report.md`
- `docs/records_center_v2_rolling_contract_summary.md`
- `docs/运动生涯记录中心V2（多运动纪录）开发任务清单.md`

## 冻结结论

- V2 `RecordDefinition` 字段已冻结，包括 `family`、`scope_dimensions`、`quality_policy`、`availability_state`、`standard_duration_sec`、`dynamic_scope` 等扩展字段。
- 跑步四项完全继承 V1：`running_5k`、`running_10k`、`running_half_marathon`、`running_marathon`。
- 骑行固定功率锚点冻结为 5s、30s、1m、5m、20m、60m，默认可进入 Catalog；W/kg 不注册为 active。
- 骑行整次活动纪录冻结为距离、爬升、历时和机械功，其中机械功为 `validation_required`。
- 徒步正式纪录冻结为距离、累计爬升、历时、最高海拔和最大连续爬升；最大连续爬升为 `candidate_only`。
- 泳池标准距离冻结为 50m、100m、200m、400m、800m、1500m，但因无真实泳池样本和 pool length schema 缺失，默认 `validation_required`。
- 公开水域标准距离和整次活动纪录冻结，但默认 `candidate_only`。
- 越野整次活动、路线 PR、赛段 PR 均冻结为 `candidate_only`；路线/赛段使用 `record_key + scope_key`，不拼接新 record type。
- 分析曲线和模型估计明确排除在正式纪录之外。

## 验证结果

```bash
.venv312/bin/python - <<'PY'
# 检查 record key 唯一性、关键白名单和必要边界术语
PY
```

结果：`contract_check_ok record_keys=45`

```bash
.venv312/bin/python -m pytest tests/test_records_center_v2_golden_fixtures.py -q
```

结果：`4 passed in 0.02s`

## Diff 复核

- 本任务只新增/更新 RCV2 文档、滚动摘要和任务状态。
- 未修改业务代码、schema migration、API contract、前端、真实库或打包产物。
- Contract 明确保留 V1 跑步兼容、候选状态机、真实数据 dry-run 和“不打包”边界。
- Golden fixtures 仍仅作为算法输入，不作为真实数据 Verified 证据。

## 下一任务

`RCV2-04 质量评分、置信度与原因码冻结`。

下一任务应在本文 Registry 状态基础上冻结质量评分矩阵、confidence 阈值、reason codes 和各运动的 candidate/ignored 判定边界。
