# ACS-Year-AI-05C 年度页面状态、报告结构与本地降级渲染完成报告

## 状态

Done。

## 交付内容

- 年度模式渲染年度标题、生成时间、`data_through` 和部分年度说明。
- 新增年度 facts 概览：活动、里程、时长、赛事、PB、成就 / 城市。
- 新增年度状态文案：`no_data`、`not_generated`、`ready`、`stale`、`generating`、`failed`、`ai_unavailable`。
- 新增固定章节顺序：主线、关键时刻、运动节奏、上一年比较、下一年方向、免责声明。
- 有 AI report 时优先展示 report content；无 report 时使用明确非 AI 的 `local_fallback`。
- `not_generated/stale/failed/generating` 显示生成/更新/重试占位按钮，但不绑定生成 API。

## 契约边界

- 年度事实概览只读后端 `facts`。
- 本地 fallback 明确为非 AI。
- 本阶段不调用 `generate_career_year_insight`。
- 本阶段不调用 `generate_career_insight` 或 `call_llm` 生成年度内容。
- 生成动作仅作为后续任务接线占位。

## 验证

```text
.venv312/bin/python -m pytest tests/test_career_year_insight_render_frontend.py tests/test_career_year_insight_mode_frontend.py tests/test_career_year_card_navigation_frontend.py -q
13 passed in 0.04s

.venv312/bin/python -m pytest tests/test_career_year_insight_read_api.py tests/test_career_phase9_pywebview_envelope.py -q
9 passed in 0.09s
```

## Review 结论

通过。05C diff 只触达年度页面渲染、状态文案、静态测试和任务文档；未发现生成 API 或 LLM 调用，旧报告和本地 fallback 的展示边界清晰。
