# P0 运动复盘数据契约回正提示词构建完成报告

## 1. 本次目标

- 根据 `docs/fatigue_review_realignment_plan_v1.md` 的第一任务 P0，构建一份可交给后续开发执行的提示词。
- 提示词必须遵循全局架构契约 `fit-arch-contrac` 与运动复盘功能设计文档。
- 提示词必须明确本阶段只做数据契约回正，不做算法实现、不做前端草图还原、不接 AI 洞察。

## 2. 新增文件

- `docs/p0_fatigue_review_contract_prompt.md`
- `docs/p0_fatigue_review_contract_prompt_completion_report.md`

## 3. 提示词覆盖范围

- 架构契约核对：FIT 为事实源、Resolver 为语义层、前端零推断、AI 最后接入、shadow_diff 隔离。
- P0 任务边界：更新 `get_fatigue_review(activity_id)` API 契约与相关契约测试。
- 目标响应结构：明确 `metrics`、`fatigue_zones`、`collapse_events`、`curves.distance/time/hr/speed/altitude/grade/gap/efficiency/total_distance_m`、`context_tags`、`ai_insight`、`advice`、`disclaimer`。
- 禁止事项：禁止前端重建距离轴、禁止暴露 shadow_diff、禁止原始 records / 全量 points 进入 API data、禁止 AI 参与本阶段。
- 验收标准：契约文档更新、测试覆盖、空态字段完整、完成报告要求。

## 4. 设计文档对齐

- 对齐 `docs/脉图运动复盘系统_开发团队交付手册_v1.md` 的 Part II 架构契约。
- 对齐 `docs/fatigue_review_realignment_plan_v1.md` 的 P0 数据契约回正任务。
- 保留 `docs/design/运动复盘系统_页面设计草图_v1.png` 作为后续 P4 UI 参考，但 P0 不实现 UI。

## 5. 未处理事项

- P1 算法链路回正：留到下一任务。
- P2 后端快照实际算法封装：留到后续任务。
- P3/P4 前端最小展示与草图还原：留到数据链路稳定后。
- P6 AI 洞察：等复盘功能跑通后再处理。

## 6. 下一步建议

- 使用 `docs/p0_fatigue_review_contract_prompt.md` 执行 P0 数据契约回正。
- P0 完成后再进入 P1，重点梳理真实 `distance_curve / altitude_curve / time / calories / sport_type` 来源。
