# ACS-Year-AI-04A 年度报告只读服务与本地 fallback 完成报告

## 状态

Done。

## 交付内容

- 新增后端只读服务 `get_career_year_insight()`。
- 默认年份使用最近一个有有效 Activity 的年份；无数据时不伪造当前年份。
- 返回稳定年度 ViewModel：
  - `available_years`
  - `year`
  - `report_state`
  - `can_generate`
  - `can_refresh`
  - `has_source_changes`
  - `facts`
  - `report`
  - `local_fallback`
  - `generated_at`
  - `data_through`
  - `status`
- 新增安全 facts 投影 `_career_year_facts_view()`，不返回完整 Snapshot、debug JSON 或 `source_fingerprint`。
- 新增本地 fallback `_career_year_local_fallback()`，明确 `mode=local_fallback`，不伪装为 AI 报告。
- 新增缓存报告视图 `_career_year_report_view()`，有历史成功报告时返回 AI report；无成功报告时 `report=None`。

## 契约边界

- 本服务不调用 LLM。
- 本服务不写 AI 成功缓存。
- 本服务不新增 pywebview API，不改前端。
- `facts` 只来自后端年度安全聚合。
- AI 不可用但有历史成功报告时继续返回该报告。
- 无成功报告时只返回本地 fallback，不生成固定 AI 叙事。

## 验证

```text
.venv312/bin/python -m pytest tests/test_career_year_insight_service.py tests/test_career_ai_insights_repository.py tests/test_career_year_snapshot_persistence.py tests/test_career_year_report_state.py -q
25 passed, 4 subtests passed in 0.30s

.venv312/bin/python -m pytest tests/test_career_snapshot_persistence.py tests/test_career_snapshot_builder.py -q
16 passed in 0.23s

.venv312/bin/python -m py_compile career_backend.py
passed
```

## Review 结论

通过。04A diff 只新增后端只读 ViewModel、测试和文档；服务路径不引用 `llm_backend`，不调用 `save_ready_career_ai_insight`，不写 AI 缓存；返回 `facts` 安全投影和明确 `local_fallback`，未返回完整 Year Snapshot。
