# ACS-Year-AI-05A 年度卡片导航与键盘可访问性完成报告

## 状态

Done。

## 交付内容

- Overview 年度卡片由静态 `div` 改为原生 `button`。
- 卡片增加 `aria-label="查看 {year} 年度总结"`。
- 原生 button 支持 Enter / Space 键盘触发。
- 悬停/焦点提示从“点击我试试”改为“查看年度总结”。
- 保留 DIN 年份、统计胶囊、克制样式和轻微上浮动效。
- 新增 `openCareerYearInsight(year)`：切换到 AI 总结页，设置年度模式与选中年份。
- 新增 `loadCareerYearInsight(options)`：只调用 `get_career_year_insight` 只读 API。
- `loadCareerInsight()` 明确设置生涯模式，为后续 05B 分段模式打基础。

## 契约边界

- 年度卡片点击不调用 `generate_career_year_insight`。
- 年度卡片点击不调用 `generate_career_insight`。
- 年度卡片点击不调用 `call_llm`。
- 年度卡片不渲染 `not_generated / stale / ready` 状态胶囊。
- 本任务只完成入口和只读加载钩子；年度页完整模式与渲染由 05B/05C 完成。

## 验证

```text
.venv312/bin/python -m pytest tests/test_career_year_card_navigation_frontend.py tests/test_career_overview_frontend_render.py tests/test_career_insight_frontend_render.py -q
23 passed in 0.06s

.venv312/bin/python -m pytest tests/test_career_year_insight_read_api.py tests/test_career_phase9_pywebview_envelope.py -q
9 passed in 0.12s
```

## Review 结论

通过。05A diff 只触达 Overview 年度卡片、年度只读加载钩子、前端静态测试和任务文档；点击路径只调用 `window.pywebview.api.get_career_year_insight`，未发现生成 API 或 LLM 调用。
