# ACS-Year-AI-04B get_career_year_insight API 与契约完成报告

## 状态

Done。

## 交付内容

- 新增 `main.Api.get_career_year_insight(payload)` pywebview 只读 API。
- API 只接受 `payload.year`，未知字段返回 validation envelope。
- `year` 执行布尔、整数解析和范围校验。
- 成功响应使用统一 `{ok, code, msg, data, traceId}` envelope。
- 成功日志只记录 `year`、`traceId`、`report_state` 和耗时，不记录 Snapshot 原文。
- `docs/js_api_contract.json` 登记 `get_career_year_insight` 的参数、返回 ViewModel 和安全边界。
- 新增 API/契约测试 `tests/test_career_year_insight_read_api.py`。

## 契约边界

- API 只调用 `career_backend.get_career_year_insight()` 只读服务。
- 不调用 LLM。
- 不新增年度生成 API。
- 不写 `career_ai_insights` 或 canonical 事实表。
- 不改变全生涯 `generate_career_insight` payload 或返回结构。
- 无数据年份返回稳定业务状态，不泄露 SQL、栈、本地路径、raw FIT、points 或 track JSON。

## 验证

```text
.venv312/bin/python -m pytest tests/test_career_year_insight_read_api.py tests/test_career_phase9_pywebview_envelope.py -q
9 passed in 0.19s

.venv312/bin/python -m pytest tests/test_career_year_insight_service.py tests/test_career_ai_insights_repository.py tests/test_career_year_snapshot_persistence.py tests/test_career_year_report_state.py -q
25 passed, 4 subtests passed in 0.23s

.venv312/bin/python -m json.tool docs/js_api_contract.json >/dev/null
passed

.venv312/bin/python -m py_compile main.py career_backend.py
passed
```

## Review 结论

通过。04B diff 只触达 pywebview 只读 API、JS API 契约、测试和任务文档；未改 `generate_career_insight`，未新增年度生成入口，未调用 LLM，未把年度字段塞进全生涯 API。
