# ACS-Year-AI-06B 完成报告：AI schema 校验、evidence 验证与事实回填

## 状态

Done。

## 实现摘要

- 新增年度 AI 报告 schema 版本 `acs.year.report.v1` 与未知 evidence 失败阈值。
- 新增 `validate_career_year_ai_report`，把 LLM 输出视为不可信草稿，校验 schema/year 后输出可缓存、可展示报告。
- 所有关键时刻只接受当前 Year Snapshot 中存在的 `evidence_id`，重复 evidence 去重，未知 evidence 低于阈值丢弃，达到阈值整份失败。
- 关键时刻标题、日期、成绩、`activity_id` 和 `detail_link` 全部由后端 evidence 回填，不采用 AI 自带事实。
- 清洗 headline、annual thread、rhythm/comparison/directions/commentary/caveats，移除 HTML、script、Markdown code fence 和异常控制字符，并限制数量与长度。
- 当 Snapshot comparison 不可用时，后端强制降级比较文案，避免保留确定性同比结论。
- 同步年度 LLM 输出 schema，要求模型返回 `schema_version/year/headline/annual_thread/key_moments/rhythm_summary/comparison_summary/directions/commentary/caveats`。

## 验证结果

```text
.venv312/bin/python -m pytest tests/test_career_year_ai_report_validation.py tests/test_career_year_llm_prompt.py -q
12 passed in 0.13s

.venv312/bin/python -m pytest tests/test_career_year_insight_service.py tests/test_career_ai_insights_repository.py -q
11 passed in 0.12s

.venv312/bin/python -m py_compile career_backend.py llm_backend.py
passed
```

## Review 结论

通过。校验器不调用 LLM，不输出 Prompt、Snapshot 或 raw response；输出 year、事实摘要和关键事件事实均来自当前 Snapshot；未知 evidence、重复 evidence、超长文本、脚本内容和 comparison 不可用均有测试覆盖。
