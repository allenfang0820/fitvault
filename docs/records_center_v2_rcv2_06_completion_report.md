# RCV2-06 完成报告：通用 Records API、Catalog 与 ViewModel 冻结

完成时间：2026-07-14

## 任务目标

冻结 Records Center V2 的通用 API、Catalog、Records、Detail、History、Curve、Candidate ViewModel、错误状态和 V1 PB API 兼容关系。

## 交付物

- `docs/records_center_v2_rcv2_06_execution_prompt.md`
- `docs/records_center_v2_rcv2_06_api_viewmodel_contract.md`
- `docs/records_center_v2_rcv2_06_completion_report.md`
- `docs/records_center_v2_rolling_contract_summary.md`
- `docs/运动生涯记录中心V2（多运动纪录）开发任务清单.md`

## 冻结结论

- 新增通用 API 契约：Catalog、Records、Detail、History、Curve、Candidates、Candidate Decision、Rebuild、Rebuild Status。
- Catalog 是运动页签、左侧分组和可用性灰态的唯一来源。
- Records ViewModel 冻结 `metric/improvement/scope/range/quality/status/detail_link`，前端不得自行计算 improvement、scope label、confidence 或轴方向。
- History ViewModel 冻结 `history_summary` 和 `chart`，后端提供 `axis_direction` 与 `total_improvement`。
- Curve ViewModel 只返回安全绘图点和 anchors，不返回 raw stream。
- V1 `get_career_pb*` 保持兼容，作为 V2 通用 API 包装器；`detail_link.source="career"` 不变。
- 列出 `docs/js_api_contract.json` 后续计划新增/更新项，但本任务未实际修改 JSON。
- 冻结错误码和安全黑名单。

## 验证结果

```bash
.venv312/bin/python - <<'PY'
# 检查新 API 名称、V1 包装关系、安全黑名单、Catalog 状态和 detail_link.source
PY
```

结果：`api_contract_check_ok`

```bash
.venv312/bin/python -m pytest tests/test_records_center_v2_golden_fixtures.py -q
```

结果：`4 passed in 0.02s`

## Diff 复核

- 本任务只新增/更新 RCV2 文档、滚动摘要和任务状态。
- 未修改业务代码、`docs/js_api_contract.json`、前端、真实库或打包产物。
- Contract 明确前端零推断：不计算纪录事实、Scope、置信度、improvement、history summary 或轴方向。
- Contract 明确禁止 raw points、轨迹、功率流、路径、schema、传感器序列号和体重详情。

## 下一任务

`RCV2-07 V2 高保真视觉、交互与响应式冻结`。

下一任务应在 API/ViewModel 契约基础上冻结多运动记录中心的视觉结构、页面状态、响应式断点和可截图验收基线。
