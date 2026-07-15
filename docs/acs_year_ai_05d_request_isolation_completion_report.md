# ACS-Year-AI-05D 年份切换、请求 token 与晚到响应隔离完成报告

## 状态

Done。

## 交付内容

- `loadCareerYearInsight` 每次请求递增 `yearInsightRequestId`。
- 请求发起时冻结 `requestedYear`。
- 响应写入前校验：
  - 当前 request id 仍匹配；
  - 当前仍在年度模式；
  - 响应年份仍匹配发起年份，或发起时由后端默认年份决定。
- 过期响应返回 `ignored=true`，不覆盖当前页面。
- 过期错误同样不覆盖当前页面错误提示。

## 验证

```text
.venv312/bin/python -m pytest tests/test_career_year_request_isolation_frontend.py tests/test_career_year_insight_render_frontend.py tests/test_career_year_insight_mode_frontend.py -q
14 passed in 0.05s
```

## Review 结论

通过。05D diff 只触达年度读取请求隔离、测试和任务文档；写入前 guard 位于 `appState.career.yearInsight = data` 之前，切到生涯模式或年份变化后晚到响应不会污染当前页面。
