# 疲劳复盘外部影响契约摘要

## 1. 目标与非目标

本次优化目标是冻结疲劳复盘外部影响字段边界，避免 `21°C` 左右高湿场景被写成“温度偏高”，并为 Task 2-6 提供可复用契约入口。普通 `get_fatigue_review(activity_id)` snapshot 与 `__FATIGUE_REVIEW_INSIGHT__` compact snapshot 都必须允许 `environment_factors`，且该字段只能由后端生成，前端与 AI 只能消费。

非目标：不新增数据库字段或表，不重构天气服务，不重构 `environment_challenge` 或 `classify_heat_stress()`，不实现 WBGT、Heat Index 或伪精确热风险指数，不引入 AI 知识库，不处理泳池游泳，不触碰同步、导入、去重、生涯记录、Records Center、天气回填等无关链路。

## 2. 三层字段边界

- `environment_context`：中性事实层。表达天气和环境事实，例如是否有天气、温度、湿度、风速、观测时间、事实摘要；不直接代表压力或用户可见影响结论。
- `context_tags`：压力/宽容标签层。只表达确有压力时给 AI 解释使用的宽容标签，例如明显热应激、高海拔、极高心肺负荷；不承载中性天气事实，不作为前端首选文案来源。
- `environment_factors`：用户可见解释层。表达后端已经识别、可直接展示给用户和传给 AI 的外部影响解释；UI 和 AI 优先消费它，不补算、不改写 canonical 环境事实。

`environment_factors` 推荐为数组。每项只允许稳定解释字段：`key`、`category`、`severity`、`label`、`comment`、`basis`、`confidence`。`basis` 只放标量事实，禁止放 points、records、curves、DOM 文本、截图信息或调试差异字段。

## 3. Snapshot 白名单

普通 fatigue review snapshot 顶层白名单包含：`sport_type`、`summary`、`metrics`、`collapse_events`、`fatigue_zones`、`curves`、`context_tags`、`environment_context`、`environment_factors`、`cycling_explanation_signals`、`ai_insight`、`advice`、`disclaimer`。

AI compact snapshot 白名单包含：`activity_id`、`sport_type`、`review_mode`、`capabilities`、`summary`、`metrics`、`fatigue_zones`、`collapse_events`、`curves_summary`、`context_tags`、`environment_context`、`environment_factors`、`cycling_explanation_signals`、`advice`、`disclaimer`。

所有 snapshot 和 prompt 输入递归禁止：`points`、`records`、`raw_records`、`track_points`、`fit_records`、`gpx_points`、`shadow_diff`、`shadow_diff_json`、`diff`、全量曲线、DOM/ECharts/截图/活动标题/设备/天气卡派生字段。

## 4. 前端、后端与 AI 边界

后端允许：从后端已持有的 `environment_context`、运动类型和安全标量事实生成 `environment_factors`；将它加入普通 snapshot 和 AI compact snapshot；过滤 forbidden keys；保持无天气或数据不足时的空数组或低置信度降级。

后端禁止：新增 DB 字段或表；重构 `environment_challenge`；修改同步、导入、去重、生涯记录链路；把原始 points、records、全量 curves 或 debug diff 放进 `environment_factors.basis`。

前端允许：优先渲染后端 `environment_factors.label/comment`；旧数据缺失时仅对后端 `context_tags` 做温和 fallback 展示；空态不推断环境事实。

前端禁止：从 DOM、ECharts、截图、活动标题、设备、天气卡、points、records、curves、summary、metrics 推导 `environment_factors`；禁止用关键词把 `热应激 / temperature / 散热` 粗暴映射成“温度偏高，心率更容易上浮”。

AI prompt 允许：消费 compact snapshot 中的 `environment_context`、`context_tags` 和 `environment_factors`，优先引用后端给出的 `environment_factors` 解释。

AI prompt 禁止：自行判断 canonical 环境事实；从温度、湿度或中性天气事实补算环境压力；把 `<25°C` 写成“温度偏高”；在户外游泳无水温时推断水温压力。

## 5. `environment_challenge` 边界

`environment_challenge` 是活动详情旧模块，数据流是 Resolver 派生到 `record.detail.environment_challenge` 后由活动详情 UI 消费；既有契约明确它不进入 AI snapshot。本次 `environment_factors` 只服务疲劳复盘外部影响解释，不重构、不迁移、不替代 `environment_challenge`，也不修改 `classify_heat_stress()`。

## 6. 运动类型语义边界

- 跑步/越野跑：关注温度、湿度、风、爬升、海拔。`<25°C` 不得说“温度偏高”；`20-25°C + 湿度 >= 80%` 只能表达“湿度偏高 / 体感偏闷”。
- 骑行/公路骑行/山地车：同温下热压力判断比跑步保守。`21-24°C + 高湿` 只表达“湿度偏高 / 体感偏闷”，不得表达“温度偏高”；不做顺逆风判断。
- 徒步：不是“跑得慢的跑步”。高湿可解释为体感闷、补水需求和长时间暴露更吃状态；爬升和海拔优先级高于跑步式热应激。
- 登山：关注海拔、爬升、低温、风寒、天气变化；不套用跑步热应激；高海拔优先解释为缺氧压力。
- 户外游泳：只覆盖开放水域/户外游泳，不处理泳池游泳。水温优先于气温；无 `water_temperature_c` 不得推断水温压力，可低置信度提示缺少水温导致环境判断有限。

## 7. Task 1 修改边界

Task 1 允许修改：`docs/js_api_contract.json`、`docs/fatigue_review_environment_factors_contract_summary.md`、`docs/fatigue_review_environment_factors_task_list.md`、`tests/test_response_envelope_contract.py`、`tests/test_fatigue_review_ai_preflight_p8.py`、`tests/test_fatigue_review_e2e_contract.py`、`tests/test_fatigue_review_environment_factors_contract.py`。

Task 1 不允许修改：`main.py`、`metrics_resolver.py`、`track.html`、`llm_backend.py`、`fit_engine.py`、`profile_backend.py`、`garmin_sync.py`、`coros_sync.py`、`career_backend.py`，以及任何同步、导入、去重、生涯记录相关文件。

## 8. 后续 Task 2-6 摘要刷新规则

后续每个任务开始前，不必默认全文阅读所有原始合同文档。只需阅读本摘要、`docs/fatigue_review_environment_factors_task_list.md` 中当前任务段落，以及当前任务直接相关的代码、测试或合同文件。

每个任务开始时必须刷新本文件“最近刷新记录”，记录：刷新时间、当前任务编号、本轮阅读的摘要/任务段落/相关文件、是否发现偏离、是否需要回读原始契约、当前任务执行边界是否变化。

只有出现重要偏离时，才需要暂停当前修改，重新全文阅读相关原始契约文件，再继续。

## 9. 重要偏离触发条件

遇到以下任一情况必须回读相关原始契约：`docs/js_api_contract.json` 与交付手册/任务清单/本摘要不一致；测试期望与交付手册/任务清单/本摘要不一致；现有代码字段名、白名单或 snapshot 结构与摘要不一致；需要修改 `environment_challenge` 或 `classify_heat_stress()`；需要新增 DB 字段或表；需要让前端推导 `environment_factors`；需要让 AI 自行判断 canonical 环境事实；户外游泳与泳池游泳边界不清；需要触碰活动同步、导入、去重、生涯记录等无关链路；测试失败显示合同与实现边界冲突而不是单纯断言未更新。

## 10. 最近刷新记录

- 刷新时间：2026-07-27 14:41:08 CST
- 当前任务编号：Task 2 corrective follow-up（Task 6 后开放水域回归修复）
- 本轮阅读：本摘要全文、`docs/fatigue_review_environment_factors_task_list.md` Task 2 / Task 6 段落、`main.py` 的 `_build_fatigue_review_environment_factors(...)`、`tests/test_fatigue_review_environment_factors_contract.py`、`docs/fatigue_review_environment_factors_delivery_manual.md` 的户外游泳语义与验收矩阵、`docs/js_api_contract.json` 的 fatigue review 外部影响契约、`docs/environment_challenge_v1_contract.md` 的非目标边界。
- 是否发现偏离：是。开放水域分支在读取 `water_temperature_c` 前被“无普通天气”早返回，导致无气温/湿度/风速但有低水温时错误返回空数组，违反“水温优先于气温”和“户外游泳，有低水温：生成水温偏低 / 冷刺激解释”的既有契约。
- 是否需要回读原始契约：是；代码字段与已冻结的户外游泳验收矩阵不一致，已回读相关原始契约后继续。
- 当前任务执行边界是否变化：不变化。仅调整 `main.py` 中开放水域分支与普通天气早返回的顺序，补充直接合同回归；不修改 `environment_challenge`、`classify_heat_stress()`、前端、AI prompt、DB、同步/导入/去重/生涯记录链路。

- 刷新时间：2026-07-27 11:54:26 CST
- 当前任务编号：Task 6
- 本轮阅读：本摘要全文、`docs/fatigue_review_environment_factors_task_list.md` Task 6 段落、`docs/fatigue_review_environment_factors_task_06_prompt.md`、`tests/test_fatigue_review_environment_factors_contract.py`、`tests/test_fatigue_review_snapshot_realignment.py`、`tests/test_fatigue_review_prompts.py`、`tests/test_fatigue_review_ai_preflight_p8.py`、`tests/test_fatigue_review_quality_gate.py`、`tests/test_v9_0_detail_tab_review.py`、`tests/test_response_envelope_contract.py`、`tests/test_fatigue_review_e2e_contract.py`、`tests/test_resolver_sport_isolation.py` 的外部影响、snapshot、prompt、前端零推导与 forbidden keys 回归断言。
- 是否发现偏离：未发现需要改变 Task 6 边界的重要偏离；现有测试已覆盖跑步、骑行、徒步、登山、户外游泳和泳池游泳边界，以及普通/compact snapshot、前端与 AI prompt 的三层字段契约，无需新增业务实现或重复测试。
- 是否需要回读原始契约：否；本轮未触发重要偏离条件。
- 当前任务执行边界是否变化：不变化。Task 6 只运行聚焦回归、补齐必要测试（本轮审计未发现缺口）并回写文档；不修改业务实现、DB、`environment_challenge`、同步/导入/生涯记录链路。

- 刷新时间：2026-07-27 11:21:20 CST
- 当前任务编号：Task 5
- 本轮阅读：本摘要全文、`docs/fatigue_review_environment_factors_task_list.md` Task 5 段落、`docs/fatigue_review_environment_factors_task_05_prompt.md`、`llm_backend.py` 的 `build_fatigue_review_messages(...)` / fatigue review output schema / normalizer 相邻代码、`tests/test_fatigue_review_prompts.py`、`tests/test_fatigue_review_ai_preflight_p8.py`、`tests/test_fatigue_review_environment_factors_contract.py`、`tests/test_fatigue_review_snapshot_realignment.py`。
- 是否发现偏离：未发现需要改变 Task 5 边界的重要偏离；compact snapshot 已包含并过滤 `environment_factors`，现有 prompt 仍主要以 `environment_context` / `context_tags` 表达外部影响边界，属于 Task 5 需要对齐的范围。
- 是否需要回读原始契约：否；本轮未触发重要偏离条件。
- 当前任务执行边界是否变化：不变化。Task 5 仅改造 `llm_backend.py` 的疲劳复盘 prompt 文案与直接测试；不修改前端、后端生成逻辑、DB、`environment_challenge` 或同步/导入/生涯记录链路。

历史刷新记录：

- 刷新时间：2026-07-27 09:46:08 CST
- 当前任务编号：Task 4
- 本轮阅读：本摘要全文、`docs/fatigue_review_environment_factors_task_list.md` Task 4 段落、`track.html` 的 `_buildFatigueReviewOverviewDimensions(...)`、`_fatigueReviewContextOverviewComment(...)`、`_fatigueReviewContextFactorCopy(...)`、`_renderFatigueReviewContextFactors(...)`、`_renderFatigueReviewSideSummary(...)`、`tests/test_fatigue_review_quality_gate.py`、`tests/test_v9_0_detail_tab_review.py`、`tests/test_fatigue_review_snapshot_realignment.py`、`docs/fatigue_review_environment_factors_delivery_manual.md`、`docs/js_api_contract.json`。
- 是否发现偏离：发现 `tests/test_fatigue_review_quality_gate.py` 的普通 snapshot 顶层白名单遗漏已冻结的 `environment_factors`，与交付手册、API 合同和本摘要不一致；已按契约补齐测试白名单。前端现有 `context_tags` 关键词映射仍属于 Task 4 要替换为后端 `environment_factors` 优先消费的范围。
- 是否需要回读原始契约：是；聚焦测试暴露白名单与合同边界冲突，已全文回读 `docs/fatigue_review_environment_factors_delivery_manual.md` 与 `docs/js_api_contract.json` 后继续。
- 当前任务执行边界是否变化：不变化。Task 4 仅改造 `track.html` 的疲劳复盘展示与直接测试；不修改后端、AI prompt、DB、`environment_challenge` 或同步/导入/生涯记录链路。

- 刷新时间：2026-07-27 09:22:13 CST
- 当前任务编号：Task 3
- 本轮阅读：本摘要全文、`docs/fatigue_review_environment_factors_task_list.md` Task 3 段落、`metrics_resolver.py` 的 capability 路由 / `context_tags` 热应激注入 / `classify_heat_stress()` / `environment_challenge` 相邻代码、`tests/test_resolver_sport_isolation.py`、`tests/test_fatigue_review_snapshot_realignment.py`、`tests/test_fatigue_review_environment_factors_contract.py`。
- 是否发现偏离：发现 `docs/js_api_contract.json` 虽已列出 `environment_factors`，但缺少合同测试冻结的三层字段和普通/compact snapshot 的精确说明；已补充独立契约块。Task 3 的 `<25°C` 禁止热应激标签、游泳不按气温注入热应激，与现有 capability 路由和 snapshot 契约一致。
- 是否需要回读原始契约：是；因合同测试与 API 合同文本不一致，已全文回读 `docs/fatigue_review_environment_factors_delivery_manual.md` 与 `docs/js_api_contract.json` 后继续。
- 当前任务执行边界是否变化：不变化。Task 3 仅收紧 `metrics_resolver.py` 的 `context_tags` 热应激注入阈值，并补充直接回归测试；不修改 `classify_heat_stress()`、`environment_challenge`、前端、AI prompt、DB 或同步/导入/生涯记录链路。

- 刷新时间：2026-07-23 01:29:08 CST
- 当前任务编号：Task 2
- 本轮阅读：本摘要全文、`docs/fatigue_review_environment_factors_task_list.md` Task 2 段落、`main.py` 中疲劳复盘 environment context / empty snapshot / compact snapshot / normal snapshot 相关函数、`tests/test_fatigue_review_environment_factors_contract.py`、`tests/test_fatigue_review_snapshot_realignment.py`、`tests/test_fatigue_review_ai_preflight_p8.py`、`tests/test_fatigue_review_e2e_contract.py`。
- 是否发现偏离：未发现需要改变 Task 2 范围的重要偏离；`tests/test_fatigue_review_ai_preflight_p8.py` 的 compact snapshot 白名单随 Task 2 新字段同步更新。
- 是否需要回读原始契约：否；本轮未触发重要偏离条件。
- 当前任务执行边界是否变化：不变化。Task 2 仅实现后端 `environment_factors` 生成和 snapshot 接入，不修改 `environment_challenge`、`classify_heat_stress()`、前端、AI prompt、DB 或同步/导入/生涯记录链路。

- Task 1 / 2026-07-23 00:42:16 CST：已全文阅读交付手册、任务清单、`docs/js_api_contract.json`、`environment_challenge` 契约、复盘回正计划、P8.1/P8.2 完成报告、指定合同测试文件；未发现需要改变 Task 1 范围的重要偏离；Task 1 仅修改合同文档和合同测试，不实现业务逻辑。
