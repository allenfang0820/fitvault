# ACS-Year-AI-05B AI 总结页模式、年份选择与年度 ViewModel 完成报告

## 状态

Done。

## 交付内容

- AI 总结页新增 `年度总结 / 生涯总结` 分段控制。
- 新增后端驱动年份胶囊容器 `career-year-selector`。
- 新增年度与生涯独立状态：
  - `insightMode`
  - `insight / insightLoading / insightError`
  - `yearInsight / yearInsightLoading / yearInsightError`
  - `yearInsightSelectedYear`
  - `yearInsightRequestId`（预留给 05D 请求隔离）
- 顶部导航进入 AI 总结页时默认年度模式，并调用 `loadCareerYearInsight({})` 让后端选择最近有效年份。
- 年度卡片进入时通过 `suppressInsightAutoLoad` 避免默认加载覆盖卡片年份。
- 年份胶囊只消费后端返回的 `available_years`。
- 生涯模式继续调用 `generate_career_insight` fallback。

## 契约边界

- 前端不从 Overview 卡片、Activity 列表或当前日期推断年份。
- 年度模式只调用 `get_career_year_insight`。
- 生涯模式仍调用 `generate_career_insight`。
- 未调用 `generate_career_year_insight` 或 `call_llm`。
- 切换模式时优先复用各自已加载 ViewModel，不覆盖另一模式缓存。

## 验证

```text
.venv312/bin/python -m pytest tests/test_career_year_insight_mode_frontend.py tests/test_career_year_card_navigation_frontend.py tests/test_career_insight_frontend_render.py -q
17 passed in 0.05s

.venv312/bin/python -m pytest tests/test_career_year_insight_read_api.py tests/test_career_phase9_pywebview_envelope.py -q
9 passed in 0.12s
```

## Review 结论

通过。05B diff 只触达 AI 总结页模式控制、年份胶囊、状态隔离、静态测试和任务文档；未发现前端扫描 Activity 或复用 Overview 年份，未引入生成 API 或 LLM 调用。
