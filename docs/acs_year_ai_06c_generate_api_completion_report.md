# ACS-Year-AI-06C 完成报告：`generate_career_year_insight` 生成 API

## 状态

Done。

## 实现摘要

- 新增年度生成服务 `generate_career_year_insight(year)`。
- `not_generated` 与 `stale` 允许生成；`ready`、`no_data` 和非允许状态在 LLM 前返回。
- 生成前按 `scope + scope_key + source_fingerprint + prompt_version + model_id` 再查缓存；命中非 failed 缓存时复用，不调用 LLM。
- 成功生成后使用 06B 校验器校验 schema/evidence，并由后端回填事实，再通过 `save_ready_career_ai_insight` 原子切换 ready。
- AI 配置缺失或调用失败返回 `ai_unavailable` 业务状态，保留当前 facts 和旧报告。
- 新增 pywebview `generate_career_year_insight({ year })`，仅允许 `year`，拒绝 prompt、Snapshot、model、force 和事实字段。
- 更新 JS API contract，明确该接口是年度独立链路，不复用 `generate_career_insight`。

## 验证结果

```text
.venv312/bin/python -m pytest tests/test_career_year_generate_api.py tests/test_career_year_insight_service.py tests/test_career_year_insight_read_api.py -q
17 passed in 0.19s

.venv312/bin/python -m pytest tests/test_career_year_ai_report_validation.py tests/test_career_year_llm_prompt.py tests/test_career_ai_insights_repository.py -q
18 passed in 0.10s

.venv312/bin/python -m py_compile career_backend.py main.py llm_backend.py
passed
```

## Review 结论

通过。fake LLM 测试覆盖 `not_generated`、`stale`、`ready`、`no_data`、AI 配置缺失和非法 payload；成功生成后只读 API 可立即读到新 ready 报告；未改变 full-career `generate_career_insight`。
