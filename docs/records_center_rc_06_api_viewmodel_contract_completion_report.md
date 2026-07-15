# RC-06 完成报告

## 任务目标

冻结当前纪录、详情、历史、候选、候选决策和重建状态的前后端数据契约，为前端设计和后端实现提供共同接口。

## 实际改动

- 新增 `docs/records_center_rc_06_api_viewmodel_contract.md`。
- 更新 `docs/records_center_rolling_contract_summary.md`。
- 更新 `docs/运动生涯记录中心（PB功能）开发任务清单.md` 中 `RC-06` 状态和当前下一任务。
- 未实现 API，未更新 `docs/js_api_contract.json`。

## 契约决定

- 保留并扩展 `get_career_pb(filters)`。
- 新增 `get_career_pb_detail`、`get_career_pb_history`、`get_career_pb_candidates`、`decide_career_pb_candidate`、`rebuild_career_pb_records`。
- 统一 `status.state`：`loading/ready/empty/partial/rebuilding/error`。
- `decide_career_pb_candidate` 与 `rebuild_career_pb_records` 为 `readonly=false`、`high_risk=true`。
- 所有 Records API 递归禁止 raw FIT、轨迹、路径、storage_ref 和 SQLite schema。
- RC-07 前端设计可使用本契约 mock fixtures。

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

本任务不访问真实库写路径。接口样例使用 RC-02 dry-run 中的活动 `108` 和 `150` 作为 mock 场景。

## 未完成项与残余风险

- `docs/js_api_contract.json` 尚未更新，按任务顺序应在 RC-17/RC-18 实现 API 时同步。
- `apply` 重建是否需要额外用户确认由 RC-15/RC-27 的 dry-run/真实数据门禁继续约束。

## 下一任务

进入 `RC-07：记录中心前端设计与交互冻结`。
