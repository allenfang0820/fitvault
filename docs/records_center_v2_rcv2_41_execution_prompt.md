# RCV2-41 工程级执行提示词：用户数据决策与 Catalog 可用性最终冻结

## 任务目标

基于 RCV2-40 真实数据备份与 staging dry-run 结果，记录用户对真实数据的 no-apply / keep-candidate 决策，并确认 Catalog 可用性与实际验收状态一致。

## 输入摘要

- 当前任务：`RCV2-41 用户数据决策与 Catalog 可用性最终冻结`。
- RCV2-40 结论：源库未变化；backup/staging 创建成功；staging dry-run processed 981；骑行/徒步/公开水域有样本，泳池/越野无样本。
- 用户已明确要求：“先全部保持候选，不写入真实库。”

## 冻结契约

- 没有新的明确授权不得执行真实库 apply。
- 用户的 no-apply 决策必须优先记录：真实库不变，所有新 V2 真实结果保持候选/不可用状态。
- 泳池/越野无真实样本不能标 Verified。
- 公开水域仍 candidate-only。
- 骑行/徒步有真实样本，但正式写入仍需质量门禁与后续授权。

## 文件范围

- 新增 `docs/records_center_v2_rcv2_41_user_decision_catalog_freeze.md`
- 新增 `docs/records_center_v2_rcv2_41_completion_report.md`
- 如当前 Registry/Catalog 与冻结状态不一致，最小范围修复 `career_backend.py` 并补测试；否则只写决策/报告。
- 更新任务清单与滚动摘要。

## 非目标

- 不执行真实库 apply。
- 不确认/拒绝候选。
- 不打包。
- 不改变无样本运动为 Verified。

## 实施步骤

1. 读取 RCV2-40 dry-run 摘要和当前 Catalog ViewModel。
2. 对比真实样本状态与 Catalog availability。
3. 记录用户 no-apply / keep-candidate 决策。
4. 形成 Catalog 最终冻结表：running、cycling、hiking、open_water_swimming、pool_swimming、trail_running。
5. 如需修复 Catalog 状态，执行最小代码变更和测试；否则仅完成文档。
6. 验证真实库不变证据沿用 RCV2-40，不做真实写入。

## 验证命令

```bash
.venv312/bin/python -m pytest tests/test_career_record_registry.py tests/test_career_records_v2_api.py tests/test_records_center_v2_golden_fixtures.py -q
.venv312/bin/python -m py_compile career_backend.py main.py
```

## 完成定义

- 用户决策记录与 Catalog 冻结表写入。
- 当前 Catalog 与真实验收状态一致，或已修复并测试。
- 完成报告写入。
- 任务清单标记 `RCV2-41 Done`、`RCV2-42 In Progress`。
