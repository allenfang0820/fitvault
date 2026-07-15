---
title: ACS-Year-AI-01D 年度 Period 与同期比较完成报告
task: ACS-Year-AI-01D
status: Done
updated: 2026-07-14
---

# ACS-Year-AI-01D 年度 Period 与同期比较完成报告

## 工程级提示词摘要

目标：完成 Year Snapshot 的 period、data_quality 和同期比较，让 AI 只解释后端给出的差值。

范围：`career_backend.py`、`tests/test_career_year_snapshot_period_comparison.py`、既有年度 Snapshot 测试、任务清单、执行日志和本完成报告。

约束：不实现 fingerprint、持久化、API、前端或 LLM；缺失比较数据时 delta 必须为 null。

## 契约刷新

`comparison` 新增 `reason` 字段，用于稳定表达 unavailable 原因，例如 `no_current_year_data` 和 `previous_year_no_data`。

## 交付内容

- `period.data_through` / `latest_activity_date` 使用进入 Snapshot 的最新事实日期。
- 当前部分年度按 `data_through` 对比上一年同月同日范围。
- 历史年度按完整自然年对比完整自然年。
- comparison 由后端输出活动、距离、时长、赛事和 PB 差值。
- data_quality 输出 `no_data`、`limited`、`ready` 与 warnings。
- 闰年、1 月初、上一年无数据和跨年边界有测试覆盖。

## 验证

已执行：

```bash
.venv312/bin/python -m pytest tests/test_career_year_snapshot_period_comparison.py tests/test_career_year_snapshot_evidence.py tests/test_career_year_snapshot_activity_aggregation.py tests/test_career_year_snapshot_contract.py tests/test_career_snapshot_builder.py tests/test_career_snapshot_persistence.py tests/test_career_insight_api_skeleton.py -q
.venv312/bin/python -m py_compile career_backend.py
```

结果：

- `48 passed in 0.36s`
- `career_backend.py` 编译通过。

## Review 结论

通过。`as_of_date` 只影响 period 展示，不作为比较截止；不可用比较保持 null delta；未新增持久化、API、前端或 LLM 调用。review 中清理了 01B 遗留的无用变量。

## 下一任务

`ACS-Year-AI-02A`：canonical JSON 与稳定 source fingerprint。
