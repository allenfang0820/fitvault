# P8.6 复盘 AI 洞察中文化完成报告

## 任务目标

修复复盘 AI 洞察中 `good`、`warn`、`declining`、`caution`、`Bonk`、`collapse_events` 等英文枚举、代码词和技术词直接暴露给用户的问题，让「本次复盘概览」四维卡片与 AI 洞察弹窗保持自然中文表达。

## 完成内容

- 后端 `normalize_fatigue_review_json` 增加用户可见文案中文化清洗，覆盖 summary、四维 comment、event_interpretation、training_advice、disclaimer。
- 后端 prompt 增加明确约束：用户可见文本不得直接输出英文枚举、原始字段名或代码词。
- 前端增加 `_fatigueReviewAiLevelLabel`，将内部等级枚举显示为「极佳 / 良好 / 需关注 / 风险较高 / 数据不足」。
- 前端增加 `_fatigueReviewLocalizeAiText` 作为展示兜底，避免外部 LLM 返回英文术语时再次穿透 UI。
- 「本次复盘概览」AI 四维卡片改为展示中文等级，不再显示 `good`、`warn` 等原始 level。

## 契约约束

- 保留内部机器枚举，不改变四维排序、tone 判断和后端数据结构。
- 保留前端 AI 调用契约：`call_llm('__FATIGUE_REVIEW_INSIGHT__', sportType)`。
- 前端不传 `activityId`、metrics、curves、fatigue_zones、collapse_events、DOM 文本或 ECharts payload。
- AI 洞察仍只解释后端权威 snapshot，不写 DB，不写 localStorage/sessionStorage，不修改复盘指标、曲线、事件或图表。

## 验证结果

- `python3 -m pytest tests/test_fatigue_review_prompts.py tests/test_v9_0_detail_tab_review.py tests/test_fatigue_review_ai_preflight_p8.py tests/test_fatigue_review_ai_insight_p6.py`
  - 121 passed, 1 warning
- `python3 -m pytest tests/test_fatigue_review_quality_gate.py tests/test_e2e_fatigue_review.py tests/test_fatigue_review_e2e_contract.py`
  - 130 passed, 1 warning
