---
title: Task 06 Prompt - 疲劳复盘外部影响回归与最终验证
version: v1.0.0
status: Ready
type: Engineering Execution Prompt
updated: 2026-07-27
source:
  - docs/fatigue_review_environment_factors_contract_summary.md
  - docs/fatigue_review_environment_factors_task_list.md
  - docs/fatigue_review_environment_factors_delivery_manual.md
  - docs/js_api_contract.json
---

# Task 06 Prompt - 疲劳复盘外部影响回归与最终验证

## 1. 工作区约束

当前工作区已有大量其他任务的未提交改动。不得新建分支，不得新建 worktree，不得清理、回滚或覆盖既有改动。

本任务是“疲劳复盘外部影响语义优化”的最终回归任务，只验证并补齐本任务组的测试合同和执行记录。不得顺手修改业务实现、同步、导入、去重、生涯记录、Records Center、天气回填、DB schema 或无关测试。

开始前必须运行 `git status --short`，记录已有脏工作区。特别注意 `main.py`、`metrics_resolver.py`、`llm_backend.py`、`track.html` 可能带有其他任务的未提交改动；除非出现合同冲突且得到明确授权，不得修改这些业务文件。

## 2. 启动阅读与摘要刷新

开始 Task 6 时，默认只阅读：

1. `docs/fatigue_review_environment_factors_contract_summary.md` 全文。
2. `docs/fatigue_review_environment_factors_task_list.md` 的 Task 6 段落。
3. `docs/fatigue_review_environment_factors_task_06_prompt.md`。
4. 下列直接相关测试全文：
   - `tests/test_fatigue_review_environment_factors_contract.py`
   - `tests/test_fatigue_review_snapshot_realignment.py`
   - `tests/test_fatigue_review_prompts.py`
   - `tests/test_fatigue_review_ai_preflight_p8.py`
   - `tests/test_fatigue_review_quality_gate.py`
   - `tests/test_v9_0_detail_tab_review.py`
   - `tests/test_response_envelope_contract.py`
   - `tests/test_fatigue_review_e2e_contract.py`
   - `tests/test_resolver_sport_isolation.py`
5. 仅在测试无法定位问题时，阅读对应的最小生产代码片段。

在运行或修改测试前，刷新 contract summary 的“最近刷新记录”，写明 Task 6、本轮阅读文件、是否发现偏离、是否需要回读原始契约，以及执行边界是否变化。

## 3. 目标

证明合同、后端 snapshot、前端展示和 AI prompt 已围绕同一条语义链路对齐：

- `environment_context` 只表示中性环境事实；
- `context_tags` 只表示压力/宽容标签；
- `environment_factors` 只由后端生成，是前端和 AI 优先消费的用户可见解释；
- 普通 fatigue review snapshot 与 `__FATIGUE_REVIEW_INSIGHT__` compact snapshot 都允许 `environment_factors`；
- 所有 snapshot / prompt 输入都不包含 forbidden keys；
- 21.7°C / 89% 跑步与骑行使用“湿度偏高 / 体感偏闷”语义，不产生“温度偏高”；
- 徒步、登山、户外游泳的语义与边界不被跑步热应激规则污染；
- 泳池游泳不进入户外游泳环境因素分支。

## 4. 允许修改的文件

- `tests/test_fatigue_review_environment_factors_contract.py`
- `tests/test_fatigue_review_snapshot_realignment.py`
- `tests/test_fatigue_review_prompts.py`
- `tests/test_fatigue_review_ai_preflight_p8.py`
- `tests/test_fatigue_review_quality_gate.py`
- `tests/test_v9_0_detail_tab_review.py`
- `tests/test_response_envelope_contract.py`
- `tests/test_fatigue_review_e2e_contract.py`
- `tests/test_resolver_sport_isolation.py`
- 必要时一个专门的 fatigue review environment factors 回归测试文件
- `docs/fatigue_review_environment_factors_contract_summary.md`
- `docs/fatigue_review_environment_factors_task_list.md`
- 本提示词文件

## 5. 明确禁止

- 不修改 `main.py`、`metrics_resolver.py`、`llm_backend.py`、`track.html`、`fit_engine.py`、`profile_backend.py`、`garmin_sync.py`、`coros_sync.py`、`career_backend.py`。
- 不新增 DB 字段或表，不改同步、导入、去重、生涯记录、Records Center、天气回填。
- 不重构、不迁移、不替代 `environment_challenge`，不修改 `classify_heat_stress()`。
- 不让前端从 DOM、ECharts、截图、活动标题、设备、天气卡、points、records、curves、summary 或 metrics 推导 `environment_factors`。
- 不让 AI 自行判断 canonical 环境事实，或从温度、湿度等中性事实补算环境压力。
- 不放宽 forbidden keys：`points`、`records`、`raw_records`、`track_points`、`fit_records`、`gpx_points`、`shadow_diff`、`shadow_diff_json`、`diff`、全量 curves 仍不得进入 compact snapshot / prompt。

## 6. 必须覆盖的回归矩阵

审计现有测试；仅在缺口存在时补测。最终至少覆盖：

1. 跑步：17°C / 77% 不产生环境压力因子；21.7°C / 89% 只表达“湿度偏高 / 体感偏闷”，不表达“温度偏高”或热应激。
2. 骑行：21.7°C / 89% 使用保守高湿语义；不从温湿度推断顺逆风；前端不再出现旧的“温度偏高，心率更容易上浮”文案。
3. 徒步：高湿可以表达体感闷、补水需求或长时间暴露，不套用跑步式热应激。
4. 登山：低温、风寒、海拔 / 缺氧优先，不套用跑步热应激。
5. 户外游泳：只覆盖开放水域；无 `water_temperature_c` 时只说明水温信息缺失 / 判断有限，不推断水温压力。
6. 泳池游泳：不生成户外游泳 `environment_factors`。
7. 三层字段：`environment_context`、`context_tags`、`environment_factors` 互不混用；前端与 AI 都只消费后端结果。
8. snapshot / prompt：普通与 compact snapshot 都包含 `environment_factors`，且递归无 forbidden keys。

## 7. 偏离与失败处理

遇到以下任一情况必须暂停当前修改，全文回读相关原始契约后再继续：

- 测试期望与 contract summary、任务清单、交付手册或 `docs/js_api_contract.json` 不一致；
- 现有 snapshot 字段、白名单、prompt 输入或前端消费路径与摘要不一致；
- 为让测试通过而需要修改业务实现、`environment_challenge`、`classify_heat_stress()`、DB 或无关链路；
- 户外游泳与泳池游泳边界不清；
- 测试失败表现为合同冲突，而不是漏测、测试断言过期或实现的确定性回归。

回读至少包括相关的 `docs/fatigue_review_environment_factors_delivery_manual.md` 与 `docs/js_api_contract.json`。若仍需要改业务实现，停止 Task 6，并在任务清单和最终报告中说明阻塞原因；不要把 Task 6 标记完成。

## 8. 验证命令

```bash
PYTHONPATH=. .venv312/bin/python -m pytest \
  tests/test_fatigue_review_environment_factors_contract.py \
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

若新增专用测试文件，将其加入同一条 pytest 命令。若聚焦集失败，先隔离到最小失败集，判断是本任务合同回归、已有脏工作区影响，还是无关失败；不要用扩大修改范围掩盖失败。

## 9. 完成与回写

只有所有聚焦测试通过且 `git diff --check` 通过，才能将 Task 6 执行项和最终验收项从 `[ ]` 更新为 `[x]`。

在 `docs/fatigue_review_environment_factors_task_list.md` 的 Task 6 段落追加执行记录，至少包含：

- 完成时间；
- 修改文件；
- 测试命令与结果；
- 是否发现偏离；
- 是否触发全文阅读原始契约；
- 未触碰的无关链路；
- 若失败，未完成项、失败原因与阻塞信息。

最终报告必须区分本轮实际修改与工作区已有脏改动，并说明 Task 1-6 是否已经完成完整闭环。
