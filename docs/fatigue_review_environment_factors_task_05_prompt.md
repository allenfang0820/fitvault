---
title: Task 05 Prompt - 疲劳复盘 AI prompt 对齐
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

# Task 05 Prompt - 疲劳复盘 AI prompt 对齐

## 1. 工作区约束

当前工作区已有大量其他任务的未提交改动。不得新建分支，不得新建 worktree，不得清理、回滚或覆盖既有改动。

本任务只处理“疲劳复盘外部影响语义优化”的 Task 5：AI prompt 对齐。不得把同步、导入、去重、生涯记录、Records Center、天气回填、前端展示、后端 environment factor 生成或数据库改动混入本任务。

开始前必须运行 `git status --short`，记录既有脏工作区；不要把既有 `main.py`、`metrics_resolver.py`、`track.html` 或其他任务的改动误判为本任务产物。

## 2. 启动阅读与摘要刷新

开始 Task 5 时，默认只阅读：

1. `docs/fatigue_review_environment_factors_contract_summary.md` 全文。
2. `docs/fatigue_review_environment_factors_task_list.md` 的 Task 5 段落。
3. `llm_backend.py` 中 `__FATIGUE_REVIEW_INSIGHT__` compact snapshot 的组装、prompt 构建与解析路径。
4. `tests/test_fatigue_review_prompts.py`。
5. `tests/test_fatigue_review_ai_preflight_p8.py`。
6. 直接相关的 fatigue review snapshot / prompt 测试。

在修改前刷新 contract summary 的“最近刷新记录”，记录刷新时间、Task 5、本轮阅读文件、是否发现偏离、是否需要回读原始契约，以及执行边界是否变化。

只有出现重要偏离时，才暂停并全文回读相关原始契约。重要偏离包括：

- compact snapshot、prompt 输入字段或白名单与摘要不一致；
- 测试期望与摘要、任务清单或 API 合同不一致；
- 需要修改 `main.py`、`metrics_resolver.py`、`track.html`、`environment_challenge` 或 `classify_heat_stress()`；
- 需要让 AI 自行判断 canonical 环境事实，或让前端补算 `environment_factors`；
- 户外游泳与泳池游泳边界不清；
- 需要新增 DB 字段/表，或触碰同步、导入、去重、生涯记录链路；
- 测试失败显示合同边界冲突，而不是单纯断言未更新。

发生重要偏离后，全文回读至少相关的 `docs/fatigue_review_environment_factors_delivery_manual.md` 与 `docs/js_api_contract.json`，再继续执行。

## 3. 目标

让 fatigue review AI 只消费后端已经冻结的 compact snapshot，并在 prompt 中正确区分：

- `environment_context` 是中性环境事实；
- `context_tags` 是确有压力时的压力/宽容标签；
- `environment_factors` 是后端已经识别、可直接向用户解释的外部影响。

AI 必须优先使用 `environment_factors` 的解释，不得把中性温湿度事实补算为压力，也不得自行产生新的 canonical 环境结论。

## 4. 允许修改的文件

- `llm_backend.py`，仅限 fatigue review compact snapshot / prompt 文案和消费逻辑。
- `tests/test_fatigue_review_prompts.py`。
- `tests/test_fatigue_review_ai_preflight_p8.py`。
- 必要时 `tests/test_fatigue_review_environment_factors_contract.py` 或 `tests/test_fatigue_review_snapshot_realignment.py`，且仅为 prompt/compact snapshot 合同回归。
- `docs/fatigue_review_environment_factors_contract_summary.md`。
- `docs/fatigue_review_environment_factors_task_list.md`。
- 本提示词文件。

## 5. 明确禁止

- 不修改 `main.py`、`metrics_resolver.py`、`track.html`、`fit_engine.py`、`profile_backend.py`、`garmin_sync.py`、`coros_sync.py`、`career_backend.py`。
- 不修改 DB schema、同步、导入、去重、生涯记录、Records Center 或天气回填。
- 不重构、不迁移、不替代 `environment_challenge`，不修改 `classify_heat_stress()`。
- 不让 AI 从 DOM、ECharts、截图、活动标题、设备、天气卡、points、records、curves、summary 或 metrics 推导 `environment_factors`。
- 不把 `points`、`records`、`raw_records`、`track_points`、`fit_records`、`gpx_points`、`shadow_diff`、`shadow_diff_json`、`diff` 或全量曲线带入 compact snapshot / prompt。
- 不重新实现 Task 2 的后端生成或 snapshot 传播；若 `environment_factors` 在 compact snapshot 中缺失，先按“重要偏离”规则暂停并回读契约。

## 6. 必须实现的 prompt 语义

1. compact snapshot 必须允许并传入已有的 `environment_factors`；AI 仅消费，不补算。
2. prompt 必须明确：`environment_factors` 是后端已识别的用户可见外部影响解释，应优先引用其 `label` / `comment`，并尊重 `confidence` 与缺失信息。
3. prompt 必须明确：`environment_context` 仅为中性事实，天气存在不等于存在压力；`context_tags` 仅是压力/宽容标签，不得替代事实层或用户可见解释层。
4. 对跑步、骑行和高湿场景：`<25°C` 不得写成“温度偏高”；`20-25°C` 且高湿时只能表达“湿度偏高 / 体感偏闷”等后端已给出的语义。
5. 对骑行：不得因温度或高湿自行推断顺逆风、额外热应激或其他未在 `environment_factors` / `context_tags` 中出现的环境结论。
6. 对徒步和登山：不得套用跑步式热应激叙述；只能遵从后端给出的爬升、海拔、低温、风寒或长时间暴露解释。
7. 对户外游泳：仅讨论开放水域/户外游泳；无 `water_temperature_c` 时不得推断水温压力，只能按后端低置信度/信息不足说明环境判断有限；不得把泳池游泳纳入此规则。
8. 无 `environment_factors` 且无 `context_tags` 时，不得从 `environment_context` 扩写压力结论；可如实说明环境影响线索有限。

## 7. 测试与验证

优先运行：

```bash
PYTHONPATH=. .venv312/bin/python -m pytest \
  tests/test_fatigue_review_prompts.py \
  tests/test_fatigue_review_ai_preflight_p8.py \
  tests/test_fatigue_review_environment_factors_contract.py \
  tests/test_fatigue_review_snapshot_realignment.py \
  -q

.venv312/bin/python -m py_compile llm_backend.py
git diff --check
```

测试至少应约束：

- prompt / compact snapshot 包含 `environment_factors`；
- `environment_context`、`context_tags`、`environment_factors` 的职责不混用；
- `<25°C` 不产生“温度偏高”表述；
- 高湿场景只使用“湿度偏高 / 体感偏闷”语义；
- 户外游泳缺水温时不推断水温压力；
- forbidden keys 不进入 prompt snapshot。

## 8. 完成与回写

完成后才可将 Task 5 的执行项和验收项从 `[ ]` 更新为 `[x]`。在 `docs/fatigue_review_environment_factors_task_list.md` 的 Task 5 段落追加执行记录，至少写明：

- 完成时间；
- 修改文件；
- 测试命令与结果；
- 是否发现偏离；
- 是否触发全文阅读原始契约；
- Task 6 的进入条件、遗留问题或注意事项。

最终报告必须说明：本任务修改的 prompt / 测试文件、是否只消费后端字段、测试结果、是否发生契约偏离、是否触发原始契约回读，以及没有触碰的非目标链路。
