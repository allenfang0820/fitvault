# P2 运动复盘后端快照回正提示词构建完成报告

## 1. 本次目标

- 编写“P2：后端快照回正，让 `get_fatigue_review` 成为前端唯一数据源”的执行提示词。
- 提示词必须承接 P0 数据契约和 P1 算法链路回正结果。
- 提示词必须遵循 `fit-arch-contrac` 和运动复盘功能设计文档。

## 2. 新增文件

- `docs/p2_fatigue_review_snapshot_realignment_prompt.md`
- `docs/p2_fatigue_review_snapshot_realignment_prompt_completion_report.md`

## 3. 提示词覆盖范围

- 架构边界：后端快照是前端唯一数据源，前端不得补算事实字段，AI 留到 P6。
- 快照结构：完整覆盖 `metrics / collapse_events / fatigue_zones / curves / context_tags / ai_insight / advice / disclaimer`。
- 曲线策略：后端统一 distance/time/hr/speed/altitude/grade/gap/efficiency 的单位、长度和空态。
- 数据形态：覆盖有 GPS、有海拔、缺 calories、室内短轨迹、轨迹点不完整、活动不存在、参数错误等场景。
- 测试要求：新增 `tests/test_fatigue_review_snapshot_realignment.py`，并运行 P0/P1/P2 相关测试。
- 文档要求：更新 `docs/js_api_contract.json`，将状态从 P0/P1 过渡到 P2 后端快照回正。

## 4. 对齐依据

- `docs/fatigue_review_realignment_plan_v1.md` 的 P2 任务定义。
- `docs/p0_fatigue_review_contract_completion_report.md` 的 API 契约结果。
- `docs/p1_fatigue_review_algorithm_realignment_completion_report.md` 的真实算法链路结果。
- `docs/js_api_contract.json` 中当前 `get_fatigue_review` 契约。
- `fit-arch-contrac` 中的数据流、AI 边界、shadow_diff 隔离和统一响应结构。

## 5. 未处理事项

- P2 的实际代码实现尚未执行。
- P3/P4 前端展示与草图还原留到后端快照稳定后。
- P6 AI 洞察留到复盘功能跑通后。

## 6. 下一步建议

- 使用 `docs/p2_fatigue_review_snapshot_realignment_prompt.md` 正式执行 P2。
- 执行 P2 时先审查 `get_fatigue_review` 全返回路径，再抽取快照标准化层。
