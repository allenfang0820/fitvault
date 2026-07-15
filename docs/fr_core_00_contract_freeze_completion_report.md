# FR-Core-00 复盘权威数据、时间语义与可用性契约冻结完成报告

日期：2026-07-13  
任务源：`docs/fatigue_review_core_audit_fix_task_list.md`  
状态：已完成红色基线冻结；未修改业务算法结果

## 1. 交付手册摘要

- FIT / Activity 是单次活动事实源，Resolver / 复盘后端是算法结论唯一事实源。
- `get_fatigue_review(activity_id)` 是复盘页唯一权威数据源。
- 前端只做展示、格式化和交互，不从 `curves / DOM / ECharts / points` 补算指标、事件、疲劳带或结论。
- AI 只消费后端 compact snapshot，不读原始 records、SQLite schema、前端 payload、DOM、ECharts 或全量曲线。
- `shadow_diff / shadow_diff_json / diff / records / raw_records / points / track_points` 不得进入复盘主展示或 AI 输入。
- 新增 §4.6：历史窗口必须以活动 `as_of_time` 为锚点；可用性状态与置信度分离；不可用主值为 `null`；不可用趋势不得进入 AI。

## 2. FR-Core-00 任务契约摘要

- 历史窗口：7d / 21d / 42d 以当前活动 `start_time / start_time_utc` 归一化后的 `as_of_time` 截止，只读取活动发生前数据，排除当前活动。
- 状态机：`available / partial / unavailable / not_applicable` 是可用性状态；`confidence` 只表达置信度，不替代状态。
- 缺失语义：`unavailable / not_applicable` 主值必须为 `null`，不得用 `0` 表示缺失。
- 趋势门控：当前指标不可用时，`trend.delta_pct / trend.is_improving / direction` 必须为 `null / unknown`。
- 同口径比较：current 与 baseline 必须同 `basis/version`、同公式、同方向、同单位、同过滤规则、同曲线来源。
- 专项边界：跑步 durability 使用速度/配速；骑行 power retention 使用有效踩踏功率；跑步功率不得自动进入骑行语义。
- AI 边界：AI 不接收不可用强趋势，不补算事实，不生成缺失运动指标。

## 3. 工程级提示词

目标：完成 FR-Core-00，不修业务算法，只冻结复盘核心审计契约和失败基线。

范围：
- 允许修改 `docs/js_api_contract.json`、`docs/脉图运动复盘系统_开发团队交付手册_v1.md`、`docs/fatigue_review_core_audit_fix_task_list.md`。
- 允许新增 `tests/test_fatigue_review_core_audit_regression.py` 和本完成报告。
- 禁止修改 `main.py`、`metrics_resolver.py`、`track.html`、`llm_backend.py` 的业务行为。

必须固化的红色基线：
- 历史 baseline 不得读取当前活动之后的数据。
- 后程效率改善不得被 `abs()` 算法标记为下降或风险。
- unavailable 主值不得用 `0` 表示缺失。
- unavailable current metric 不得生成强 `delta_pct / is_improving`。
- 跑步 durability 必须读取权威 `curves_snapshot.speed`，不得因 `row.speed_curve` 为空而误判样本不足。
- AI compact snapshot 不得携带 unavailable 指标的强趋势。
- 跑步 durability 缺失文案不得出现功率曲线。

验证：
- 使用 `.venv312/bin/python -m unittest discover -s tests -p 'test_fatigue_review_core_audit_regression.py'`。
- 本任务验收为“预期红色基线稳定失败”，不是绿灯。
- 文档契约测试应通过；程序测试应保持失败并分别指向后续 FR-Core-01 至 FR-Core-07。

偏差处理：
- 如果需要改业务代码才能让 FR-Core-00 通过，停止并确认，因为 FR-Core-00 的边界是不改业务结果。
- 如果测试失败原因不是上述已知缺陷，而是语法、依赖、fixture 本身错误，先修测试。
- 如果文档契约与本次审计冲突，以 2026-07-13 审计清单和 `docs/js_api_contract.json` 新冻结契约为准。

## 4. 验证结果

命令：

```bash
.venv312/bin/python -m unittest discover -s tests -p 'test_fatigue_review_core_audit_regression.py'
```

结果：
- 8 个测试执行。
- 文档契约测试已通过。
- 其余 7 个程序/算法/UI/AI 门控测试预期失败，分别锚定：
  - FR-Core-01：历史窗口使用电脑当前时间或未来数据。
  - FR-Core-02：后程效率改善被绝对值解耦标记为风险。
  - FR-Core-03：不可用指标仍生成强趋势，AI compact snapshot 携带不可用趋势。
  - FR-Core-04：跑步 durability 仍使用空 `row.speed_curve`，没有读取权威 snapshot speed。
  - FR-Core-05：unavailable decoupling 仍以 `pct=0.0` 表示缺失。
  - FR-Core-07：跑步 durability 样本不足文案仍出现“功率曲线”。

## 5. Diff 自审

- 本任务只新增测试和文档契约，不触碰业务算法。
- 新增测试使用匿名化等价 fixture，不写入真实活动路径、原始轨迹或用户隐私数据。
- 新增契约没有扩大到 ACS、OpenClaw、同步、标题、打包或无关 UI。

## 6. 下一任务建议

按清单顺序，下一任务是 `FR-Core-01：历史窗口与活动时点修复`。

建议执行边界：
- 只修 `as_of_time` 解析、21d/7d/42d 窗口、历史 SQL 排除未来数据和当前活动。
- 不同时修解耦方向、不可用趋势、durability 数据源或前端文案。
- 完成后应让 FR-Core-00 中的历史窗口测试转绿，并补充 `tests/test_v8_5_trend.py`、`tests/test_fatigue_review_trends.py` 的聚焦验证。
