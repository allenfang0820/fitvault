# 疲劳复盘外部影响语义优化任务清单

## 总原则

- 只修复疲劳复盘外部影响语义链路。
- 不新增数据库字段。
- 不重构 `environment_challenge`。
- 前端只渲染后端字段，不从 DOM、ECharts、截图、标题、设备或天气卡推导外部影响。
- 游泳只覆盖户外游泳，不处理泳池游泳。
- 当前工作区已有较多无关改动，执行时必须避免混入同步、导入、生涯记录等任务。

## Task 1：合同冻结

目标：冻结字段边界，防止 `environment_context`、`environment_factors`、`context_tags` 再次混用。

涉及文件：

- `docs/js_api_contract.json`
- `tests/test_response_envelope_contract.py`
- `tests/test_fatigue_review_ai_preflight_p8.py`
- `tests/test_fatigue_review_e2e_contract.py`

执行项：

- [x] 在合同中增加 `environment_factors` 字段说明。
- [x] 明确 `environment_context` 只表达中性事实。
- [x] 明确 `environment_factors` 表达用户可见外部影响解释。
- [x] 明确 `context_tags` 只表达压力/宽容标签。
- [x] 更新 snapshot / compact snapshot 白名单测试。
- [x] 确认 forbidden keys 仍禁止 `points`、`records`、`curves` 全量、`shadow_diff`、DOM 派生事实进入 AI 输入。

验收：

- [x] 合同测试能证明新增字段被允许。
- [x] 合同测试能证明前端/AI 不允许自行补算外部影响。

执行记录：

- 完成时间：2026-07-23 00:49:07 CST
- 修改文件：`docs/js_api_contract.json`、`docs/fatigue_review_environment_factors_contract_summary.md`、`docs/fatigue_review_environment_factors_task_list.md`、`tests/test_response_envelope_contract.py`、`tests/test_fatigue_review_ai_preflight_p8.py`、`tests/test_fatigue_review_e2e_contract.py`、`tests/test_fatigue_review_environment_factors_contract.py`
- 测试命令：`PYTHONPATH=. .venv312/bin/python -m pytest tests/test_fatigue_review_environment_factors_contract.py tests/test_response_envelope_contract.py tests/test_fatigue_review_ai_preflight_p8.py tests/test_fatigue_review_e2e_contract.py -q`
- 测试结果：`74 passed in 0.25s`
- 是否发现偏离：未发现需要改变 Task 1 范围的重要偏离；测试中发现 `test_fatigue_review_ai_preflight_p8.py` 的 compact snapshot 白名单滞后于当前 `review_mode/capabilities` 合同，已在允许测试文件内对齐。
- 是否触发全文阅读原始契约：Task 1 按要求已全文阅读指定原始契约；未额外触发新的全文回读。
- 遗留问题或下一任务注意事项：Task 1 只冻结合同，不实现 `environment_factors` 业务生成；Task 2 进入前先读 `docs/fatigue_review_environment_factors_contract_summary.md`、本清单 Task 2 段落和直接相关代码/测试，并刷新摘要“最近刷新记录”。

## Task 2：后端环境因素生成

目标：在后端新增 `environment_factors`，由后端统一生成用户可见外部影响解释。

涉及文件：

- `main.py`
- `tests/test_fatigue_review_snapshot_realignment.py`

执行项：

- [x] 新增 `_build_fatigue_review_environment_factors(...)`。
- [x] `_empty_fatigue_review_snapshot(...)` 返回 `environment_factors: []`。
- [x] `_build_fatigue_review_snapshot(...)` 返回 `environment_factors`。
- [x] `_build_fatigue_review_insight_snapshot(...)` compact snapshot 返回 `environment_factors`。
- [x] 支持跑步、骑行、徒步、登山、户外游泳分支。
- [x] 对无天气数据场景安全降级为空数组或低置信度数据不足因素。
- [x] 对异常温度、湿度、风速做边界过滤，避免脏数据生成压力。

验收矩阵：

- [x] 跑步 17°C / 77%：无明显外部压力。
- [x] 跑步 21.7°C / 89%：湿度偏高，不说温度偏高。
- [x] 骑行 21.7°C / 89%：湿度偏高，不说温度偏高。
- [x] 徒步 24°C / 90%：体感偏闷 / 长时间暴露语义。
- [x] 登山 5°C / 大风：低温 / 风寒语义。
- [x] 户外游泳 21°C / 高湿 / 无水温：提示水温缺失，不推断温度压力。
- [x] 户外游泳低水温：水温偏低 / 冷刺激语义。

执行记录：

- 完成时间：2026-07-23 01:29:08 CST
- 修改文件：`main.py`、`tests/test_fatigue_review_environment_factors_contract.py`、`tests/test_fatigue_review_snapshot_realignment.py`、`tests/test_fatigue_review_ai_preflight_p8.py`、`tests/test_fatigue_review_e2e_contract.py`、`docs/fatigue_review_environment_factors_contract_summary.md`、`docs/fatigue_review_environment_factors_task_list.md`
- 测试命令：`PYTHONPATH=. .venv312/bin/python -m pytest tests/test_fatigue_review_environment_factors_contract.py tests/test_fatigue_review_snapshot_realignment.py tests/test_fatigue_review_ai_preflight_p8.py tests/test_fatigue_review_e2e_contract.py -q`
- 测试结果：`92 passed in 1.55s`
- 是否发现偏离：未发现需要改变 Task 2 范围的重要偏离；compact snapshot 白名单按 Task 2 新字段更新。
- 是否触发全文阅读原始契约：否。
- 遗留问题或下一任务注意事项：Task 3 负责收紧 `context_tags` 热应激注入阈值；进入 Task 3 前先读 contract summary、本清单 Task 3 段落和 `metrics_resolver.py` / 相关测试，仍不得重构 `environment_challenge` 或混入前端/AI prompt 工作。

纠偏执行记录（Task 6 后）：

- 完成时间：2026-07-27 14:43:13 CST。
- 修改文件：`main.py`、`tests/test_fatigue_review_environment_factors_contract.py`、`docs/fatigue_review_environment_factors_contract_summary.md`、`docs/fatigue_review_environment_factors_task_list.md`。
- 测试命令：`PYTHONPATH=. .venv312/bin/python - <<'PY' ... PY` 最小开放水域复现；`PYTHONPATH=. .venv312/bin/python -m pytest tests/test_fatigue_review_environment_factors_contract.py -q`；`PYTHONPATH=. .venv312/bin/python -m pytest tests/test_fatigue_review_environment_factors_contract.py tests/test_fatigue_review_snapshot_realignment.py tests/test_fatigue_review_ai_preflight_p8.py tests/test_fatigue_review_e2e_contract.py -q`；`git diff --check`。
- 测试结果：最小复现通过；单文件合同测试 `20 passed in 0.10s`；聚焦测试 `94 passed in 1.73s`；`git diff --check` 通过。
- 是否发现偏离：是；开放水域分支在读取水温前因缺少普通天气事实提前返回，令“低水温 / 冷刺激”验收场景失效。
- 是否触发全文阅读原始契约：是；已按重要偏离规则回读户外游泳相关交付契约与 API/旧模块边界。
- 遗留问题或下一任务注意事项：此为 Task 2 已冻结语义的最小纠偏。必须保持无水温时仅输出低置信度缺失提示，泳池游泳始终返回空数组，且 `basis` 只含标量。

## Task 3：热应激标签收紧

目标：修正 `context_tags` 热应激注入过宽问题，避免普通温度被当成热压力。

涉及文件：

- `metrics_resolver.py`
- `tests/test_resolver_sport_isolation.py`
- `tests/test_fatigue_review_snapshot_realignment.py`

执行项：

- [x] 删除 `>=20°C` 注入 `Moderate 热应激` 的逻辑。
- [x] 明确 `<25°C` 不注入热应激。
- [x] 明确明显高温才进入 `context_tags`。
- [x] 保持 swimming / lap_swimming 不注入热应激的既有隔离。
- [x] 确认户外游泳不通过气温注入热应激。
- [x] 不修改 `classify_heat_stress()` 和 `environment_challenge`，除非后续另立任务。

验收：

- [x] 21.7°C 场景 `context_tags` 不包含热应激。
- [x] 28°C 或更高的跑步场景仍能生成合理热压力。
- [x] 游泳类运动不会因气温生成热应激。

执行记录：

- 完成时间：2026-07-27 09:23:17 CST
- 修改文件：`metrics_resolver.py`、`tests/test_resolver_sport_isolation.py`、`docs/js_api_contract.json`、`docs/fatigue_review_environment_factors_contract_summary.md`、`docs/fatigue_review_environment_factors_task_list.md`
- 测试命令：`PYTHONPATH=. .venv312/bin/python -m pytest tests/test_resolver_sport_isolation.py tests/test_fatigue_review_snapshot_realignment.py tests/test_fatigue_review_environment_factors_contract.py -q`；`git diff --check`。
- 测试结果：`145 passed in 1.71s`；`git diff --check` 通过。
- 是否发现偏离：发现 `docs/js_api_contract.json` 缺少合同测试冻结的精确三层语义与普通/compact snapshot 说明；已以独立契约块补齐，未改变 Task 3 业务边界。
- 是否触发全文阅读原始契约：是；已全文回读 `docs/fatigue_review_environment_factors_delivery_manual.md` 与 `docs/js_api_contract.json`。
- 遗留问题或下一任务注意事项：Task 4 开始前读取 contract summary、Task 4 段落及 `track.html` / 相关前端测试；前端只能消费后端 `environment_factors`，不得从 DOM、ECharts、天气卡、标题、设备或 records 推导环境事实。

## Task 4：前端展示改造

目标：前端优先展示后端 `environment_factors`，不再通过关键词硬猜环境影响文案。

涉及文件：

- `track.html`
- `tests/test_fatigue_review_quality_gate.py`
- `tests/test_v9_0_detail_tab_review.py`

执行项：

- [x] `_buildFatigueReviewOverviewDimensions(data)` 读取 `data.environment_factors`。
- [x] `context_impact` 卡片优先使用 `environment_factors` 的 `label/comment`。
- [x] `_renderFatigueReviewContextFactors(...)` 支持渲染 `environment_factors`。
- [x] `context_tags` 仅作为旧 snapshot fallback。
- [x] 删除或降级“温度关键词 => 温度偏高，心率更容易上浮”的硬编码。
- [x] 保留空态：无 `environment_factors` 且无 `context_tags` 时，不额外推断天气、地形或设备影响。

验收：

- [x] 21.7°C / 89% 骑行 UI 显示“湿度偏高”语义。
- [x] UI 不出现“温度偏高，心率更容易上浮”。
- [x] 旧 `context_tags` snapshot 仍能温和 fallback。

执行记录：

- 完成时间：2026-07-27 09:51:39 CST
- 修改文件：`track.html`、`tests/test_fatigue_review_quality_gate.py`、`tests/test_v9_0_detail_tab_review.py`、`docs/fatigue_review_environment_factors_contract_summary.md`、`docs/fatigue_review_environment_factors_task_list.md`
- 测试命令：`PYTHONPATH=. .venv312/bin/python -m pytest tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py tests/test_fatigue_review_snapshot_realignment.py tests/test_fatigue_review_environment_factors_contract.py -q`；`git diff --check`
- 测试结果：聚焦测试 `204 passed in 2.43s`；`git diff --check` 通过
- 是否发现偏离：是；`tests/test_fatigue_review_quality_gate.py` 的普通 snapshot 顶层白名单遗漏已冻结的 `environment_factors`，与合同边界不一致，已补齐测试白名单。
- 是否触发全文阅读原始契约：是；已全文回读 `docs/fatigue_review_environment_factors_delivery_manual.md` 与 `docs/js_api_contract.json`。
- 遗留问题或下一任务注意事项：Task 5 进入前读取 contract summary、Task 5 段落及 `llm_backend.py` / prompt 相关测试；AI prompt 只能消费后端 `environment_factors`，不得让 AI 自行判断 canonical 环境事实，也不得修改前端、后端生成逻辑、DB 或同步/导入/生涯记录链路。

## Task 5：AI prompt 对齐

目标：让复盘 AI 与后端结构化字段对齐，避免 AI 再把中性天气事实写成环境压力。

涉及文件：

- `llm_backend.py`
- `tests/test_fatigue_review_prompts.py`
- `tests/test_fatigue_review_ai_preflight_p8.py`

执行项：

- [x] AI compact snapshot 加入 `environment_factors`。
- [x] prompt 说明 `environment_factors` 是后端已识别的外部影响解释。
- [x] prompt 说明 `environment_context` 是事实，不等同于压力。
- [x] prompt 说明 `context_tags` 是压力/宽容标签。
- [x] prompt 明确 `<25°C` 不得写“温度偏高”。
- [x] prompt 明确高湿应写“湿度偏高 / 体感偏闷”。
- [x] prompt 明确户外游泳无水温时不得推断水温压力。

验收：

- [x] prompt 测试包含 `environment_factors`。
- [x] prompt 测试包含 `<25°C` 禁止高温表达规则。
- [x] prompt 测试覆盖户外游泳无水温降级。

执行记录：

- 完成时间：2026-07-27 11:23:39 CST
- 修改文件：`llm_backend.py`、`tests/test_fatigue_review_prompts.py`、`docs/fatigue_review_environment_factors_contract_summary.md`、`docs/fatigue_review_environment_factors_task_list.md`
- 测试命令：`PYTHONPATH=. .venv312/bin/python -m pytest tests/test_fatigue_review_prompts.py tests/test_fatigue_review_ai_preflight_p8.py tests/test_fatigue_review_environment_factors_contract.py tests/test_fatigue_review_snapshot_realignment.py -q`；`.venv312/bin/python -m py_compile llm_backend.py`；`git diff --check`
- 测试结果：聚焦测试 `104 passed in 1.93s`；`py_compile` 通过；`git diff --check` 通过
- 是否发现偏离：未发现需要改变 Task 5 边界的重要偏离；compact snapshot 的 `environment_factors` 已由前序任务接入，本轮测试确认其存在与 forbidden keys 过滤。
- 是否触发全文阅读原始契约：否；本轮未触发重要偏离条件。
- 遗留问题或下一任务注意事项：Task 6 进入前读取 contract summary、Task 6 段落和直接相关回归测试；以聚焦回归证明整组外部影响语义链路，不引入新的前端/后端/AI 业务改动，除非测试暴露合同边界冲突并按摘要规则回读原始契约。

## Task 6：回归测试与最终验证

目标：用聚焦测试证明本次修复覆盖整类问题，且未破坏既有疲劳复盘合同。

涉及文件：

- `tests/test_fatigue_review_snapshot_realignment.py`
- `tests/test_fatigue_review_prompts.py`
- `tests/test_fatigue_review_ai_preflight_p8.py`
- `tests/test_fatigue_review_quality_gate.py`
- `tests/test_v9_0_detail_tab_review.py`
- `tests/test_response_envelope_contract.py`
- `tests/test_fatigue_review_e2e_contract.py`
- `tests/test_resolver_sport_isolation.py`

执行项：

- [x] 补齐运动类型矩阵测试。
- [x] 补齐前端禁止硬编码温度偏高测试。
- [x] 补齐 AI prompt 边界测试。
- [x] 运行聚焦测试集合。
- [x] 检查 `git diff --check`。
- [x] 汇总改动文件、测试命令和结果。

推荐命令：

```bash
PYTHONPATH=. .venv312/bin/python -m pytest \
  tests/test_fatigue_review_snapshot_realignment.py \
  tests/test_fatigue_review_prompts.py \
  tests/test_fatigue_review_ai_preflight_p8.py \
  tests/test_fatigue_review_quality_gate.py \
  tests/test_v9_0_detail_tab_review.py \
  tests/test_response_envelope_contract.py \
  tests/test_fatigue_review_e2e_contract.py \
  tests/test_resolver_sport_isolation.py \
  -q

git diff --check
```

最终验收：

- [x] 聚焦测试通过。
- [x] 21.7°C / 89% 骑行不再显示“温度偏高”。
- [x] 跑步、骑行、徒步、登山、户外游泳均有回归覆盖。
- [x] 合同、后端、前端、AI prompt 四层一致。
- [x] 未触碰无关业务链路。

执行记录：

- 完成时间：2026-07-27 11:55:02 CST
- 修改文件：`docs/fatigue_review_environment_factors_contract_summary.md`、`docs/fatigue_review_environment_factors_task_list.md`
- 测试命令：`PYTHONPATH=. .venv312/bin/python -m pytest tests/test_fatigue_review_environment_factors_contract.py tests/test_fatigue_review_snapshot_realignment.py tests/test_fatigue_review_prompts.py tests/test_fatigue_review_ai_preflight_p8.py tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py tests/test_response_envelope_contract.py tests/test_fatigue_review_e2e_contract.py tests/test_resolver_sport_isolation.py -q`；`git diff --check`
- 测试结果：聚焦测试 `407 passed in 2.20s`；`git diff --check` 通过
- 是否发现偏离：未发现需要改变 Task 6 边界的重要偏离。既有测试已覆盖跑步、骑行、徒步、登山、户外游泳、泳池游泳、三层字段、普通/compact snapshot、前端禁止硬编码与 AI prompt 边界，因此无需新增测试或业务改动。
- 是否触发全文阅读原始契约：否；本轮未触发重要偏离条件。
- 未触碰的无关链路：未修改 `main.py`、`metrics_resolver.py`、`llm_backend.py`、`track.html`、DB、`environment_challenge`、`classify_heat_stress()`、同步、导入、去重、生涯记录或 Records Center。
- 闭环结论：Task 1-6 已完成合同冻结、后端生成、标签阈值收紧、前端消费、AI prompt 对齐与最终聚焦回归验证。

纠偏执行记录（Task 6 后）：

- 完成时间：2026-07-27 14:43:13 CST。
- 修改文件：`main.py`、`tests/test_fatigue_review_environment_factors_contract.py`、`docs/fatigue_review_environment_factors_contract_summary.md`、`docs/fatigue_review_environment_factors_task_list.md`。
- 测试命令：`PYTHONPATH=. .venv312/bin/python - <<'PY' ... PY` 最小开放水域复现；`PYTHONPATH=. .venv312/bin/python -m pytest tests/test_fatigue_review_environment_factors_contract.py -q`；`PYTHONPATH=. .venv312/bin/python -m pytest tests/test_fatigue_review_environment_factors_contract.py tests/test_fatigue_review_snapshot_realignment.py tests/test_fatigue_review_ai_preflight_p8.py tests/test_fatigue_review_e2e_contract.py -q`；`git diff --check`。
- 测试结果：最小复现通过；单文件合同测试 `20 passed in 0.10s`；聚焦测试 `94 passed in 1.73s`；`git diff --check` 通过。
- 是否发现偏离：是；Task 6 的覆盖未包含“无普通天气但有低水温”的开放水域输入，因此没有发现 Task 2 生成函数的早返回违约。
- 是否触发全文阅读原始契约：是；按代码实现与验收矩阵冲突的触发条件回读。
- 遗留问题或下一任务注意事项：后续若调整环境因素生成顺序，必须保留开放水域水温优先、无水温低置信度降级和泳池空数组三个回归场景。
