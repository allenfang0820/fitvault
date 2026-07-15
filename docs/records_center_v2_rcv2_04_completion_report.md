# RCV2-04 完成报告：质量评分、置信度与原因码冻结

完成时间：2026-07-14

## 任务目标

统一 Records Center V2 的自动确认、候选和忽略边界，并冻结多运动质量维度、reason codes、用户文案 key 和日志安全边界。

## 交付物

- `docs/records_center_v2_rcv2_04_execution_prompt.md`
- `docs/records_center_v2_rcv2_04_quality_confidence_contract.md`
- `docs/records_center_v2_rcv2_04_completion_report.md`
- `docs/records_center_v2_rolling_contract_summary.md`
- `docs/运动生涯记录中心V2（多运动纪录）开发任务清单.md`

## 冻结结论

- 继续继承阈值：`>0.90` 自动确认，`0.70-0.90` 候选，`<0.70` 忽略；`0.70/0.90` 均为候选。
- 决策优先级冻结：`analysis/model` 短路、hard-block 短路、`validation_required` 不得 active、`candidate_only` 最高只能候选、最后才看 confidence。
- 冻结 `QualityDecision` 输出字段：decision、confidence、band、reason_codes、user_message_key、log_safety、can_user_confirm、blocks_active、evidence_fingerprint。
- 冻结通用、跑步、骑行、徒步、游泳、越野 reason code 表。
- 明确用户可确认/不可确认边界：用户确认不能修改事实值，也不能解除 hard-block、validation_required 或 candidate-only 发布门禁。
- 冻结日志安全要求：不返回 raw FIT、完整轨迹、真实 GPS 点、路径、设备序列号、账号、token、schema 或体重历史。

## 验证结果

```bash
.venv312/bin/python - <<'PY'
# 检查 reason code 白名单覆盖 fixtures、阈值边界和关键门禁术语
PY
```

结果：`quality_contract_check_ok reason_codes=78 fixture_codes=11`

```bash
.venv312/bin/python -m pytest tests/test_records_center_v2_golden_fixtures.py -q
```

结果：`4 passed in 0.03s`

## Diff 复核

- 本任务只新增/更新 RCV2 文档、滚动摘要和任务状态。
- 未修改业务 Resolver、状态机、schema migration、API contract、前端、真实库或打包产物。
- Contract 明确 `candidate_only` 和 `validation_required` 优先于单条 evidence 高分，防止未验收运动被自动写 active。
- Reason code 文档覆盖当前 golden manifest 中全部 reason codes。

## 下一任务

`RCV2-05 Schema、Curve Cache、Route 数据与回滚冻结`。

下一任务应在 Registry 与质量契约基础上冻结新增 schema、唯一性、curve cache、route signature 派生数据、migration dry-run 和回滚方案。
