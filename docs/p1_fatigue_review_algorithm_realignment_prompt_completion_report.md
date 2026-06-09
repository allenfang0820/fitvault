# P1 运动复盘算法链路回正提示词构建完成报告

## 1. 本次目标

- 编写“P1：算法链路回正，废弃伪 records，改用真实 FIT / DB canonical 数据”的执行提示词。
- 提示词必须遵循 `fit-arch-contrac`、运动复盘功能设计文档、P0 数据契约回正结果。
- 提示词必须明确 P1 只处理算法输入链路，不做前端草图还原，不接 AI 洞察。

## 2. 新增文件

- `docs/p1_fatigue_review_algorithm_realignment_prompt.md`
- `docs/p1_fatigue_review_algorithm_realignment_prompt_completion_report.md`

## 3. 提示词覆盖范围

- 架构契约核对：FIT / DB canonical 为事实源、Resolver 为语义层、main.py 只编排、前端零推断、AI 留到 P6。
- 当前偏离说明：固定 `altitude=100.0`、固定 `dt=1s`、空 session、伪距离、bonk calories 漏传。
- 数据来源调查：activities 表字段、track_json 点结构、Resolver / GapCalculator 现有输出。
- canonical curve bundle 设计：`distance_curve_m`、`time_curve_sec`、`hr_curve`、`speed_curve_mps`、`altitude_curve_m`、`cadence_curve`、`calories`、`duration_sec`、`total_distance_m`、`sport_type`、`source`。
- 实施步骤：调查 → bundle 构建 → 替换伪 records → sport-aware bonk → 输出权威曲线 → 新增测试。
- 验收标准：不再固定 altitude/dt，不再空 session 漏 calories，fatigue_zones 与 curves.distance 同源。

## 4. 对齐依据

- `docs/fatigue_review_realignment_plan_v1.md` 的 P1 任务定义。
- `docs/p0_fatigue_review_contract_completion_report.md` 的 P0 契约结果。
- `docs/脉图运动复盘系统_开发团队交付手册_v1.md` 中数据输入契约、Gradient、GAP、Efficiency、HR Drift 等算法规格。
- `main.py` 当前 `_build_resolved_payload_v81()` 的伪 records 实现位置。

## 5. 未处理事项

- P1 的实际代码实现尚未执行。
- P2 后端快照封装留到 P1 输出稳定后。
- P3/P4 前端展示和草图还原留到数据链路稳定后。
- P6 AI 洞察留到复盘功能跑通后。

## 6. 下一步建议

- 使用 `docs/p1_fatigue_review_algorithm_realignment_prompt.md` 正式执行 P1。
- 执行 P1 时先做数据来源调查矩阵，再动代码废弃伪 records。
