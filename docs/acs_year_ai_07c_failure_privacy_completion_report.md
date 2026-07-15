# ACS-Year-AI-07C 完成报告：失败保留、受控重试、日志与隐私收口

## 状态

Done。

## 实现摘要

- 年度生成失败按阶段和错误类型返回稳定业务状态：
  - `network_failed`
  - `timeout`
  - `format_failed`
  - `schema_failed`
  - `evidence_failed`
  - `persistence_failed`
  - `ai_unavailable`
- 首次失败保留 facts 并返回 `failed` 页面状态。
- 更新失败保留旧报告、旧 `generated_at` 和旧 fingerprint。
- 持久化失败不会污染当前 ready 报告。
- 错误返回不回显 token、URL 密钥、Prompt、Snapshot、底层请求体或 raw AI response。
- 失败日志只输出安全摘要，不使用 traceback/异常正文作为常规日志内容。

## 验证结果

```text
.venv312/bin/python -m pytest tests/test_career_year_generate_api.py tests/test_career_year_ai_report_validation.py -q
23 passed, 6 subtests passed in 0.53s

.venv312/bin/python -m pytest tests/test_career_year_llm_prompt.py tests/test_career_year_insight_read_api.py -q
11 passed in 0.11s

.venv312/bin/python -m py_compile career_backend.py llm_backend.py main.py
passed
```

## Review 结论

通过。失败矩阵、日志隐私和 canonical 表不污染均有测试覆盖；纯格式修复仍由 06A LLM 调用层保持最多一次，不在服务层新增无限重试。
