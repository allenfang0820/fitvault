---
title: ACS-Year-AI-02A 稳定 Source Fingerprint 完成报告
task: ACS-Year-AI-02A
status: Done
updated: 2026-07-14
---

# ACS-Year-AI-02A 稳定 Source Fingerprint 完成报告

## 工程级提示词摘要

目标：实现 Year Snapshot canonical JSON 和稳定 `source_fingerprint`。

范围：`career_backend.py`、`tests/test_career_year_snapshot_fingerprint.py`、年度 Snapshot 契约测试、任务清单、执行日志和本完成报告。

约束：不直接 hash 整个运行时 Snapshot；排除运行时字段、`as_of_date`、状态文案、UI、Prompt 和模型版本；不实现状态机、持久化、API、前端或 LLM。

## 交付内容

- 新增 `career_year_snapshot_report_source_fields`。
- 新增 `career_year_snapshot_canonical_json`。
- 新增 `compute_career_year_source_fingerprint`。
- `build_career_year_snapshot` 现在返回 `sha256:{hex}` 格式 fingerprint。
- 测试覆盖事实变化、Resolver evidence 变化、日期推进、运行时字段、UI/Prompt/model 字段、排序差异和浮点等价表达。

## 验证

已执行：

```bash
.venv312/bin/python -m pytest tests/test_career_year_snapshot_fingerprint.py tests/test_career_year_snapshot_period_comparison.py tests/test_career_year_snapshot_contract.py -q
.venv312/bin/python -m pytest tests/test_career_snapshot_builder.py tests/test_career_snapshot_persistence.py tests/test_career_insight_api_skeleton.py -q
.venv312/bin/python -m py_compile career_backend.py
```

结果：

- `18 passed in 0.12s`
- `27 passed in 0.30s`
- `career_backend.py` 编译通过。

## Review 结论

通过。fingerprint 不直接 hash 整个 Snapshot，运行时字段和 `as_of_date` 被排除；未新增状态机、持久化、API、前端或 LLM 调用。review 中同步修正了 `source_fingerprint` schema 描述。

## 下一任务

`ACS-Year-AI-02B`：年度报告状态解析器。
