---
title: ACS-Year-AI-01A Year Snapshot 契约完成报告
task: ACS-Year-AI-01A
status: Done
updated: 2026-07-14
---

# ACS-Year-AI-01A Year Snapshot 契约完成报告

## 工程级提示词摘要

目标：冻结 `acs.year.v1` 的 Year Snapshot schema、安全白名单、禁止字段、合法年份和无数据年份行为。

范围：`career_backend.py`、`tests/test_career_year_snapshot_contract.py`、任务清单、执行日志和本完成报告。

约束：不实现真实 LLM，不持久化 Snapshot，不接前端，不做年度聚合、Resolver evidence、同期比较或 fingerprint 计算。

## 交付内容

- 后端新增 Year Snapshot 版本、scope、顶层字段顺序和字段 schema 描述。
- 后端新增 Activity 安全字段白名单和 Resolver evidence 字段白名单。
- 后端新增递归禁止字段检测，覆盖 raw FIT、points、track、路径、媒体、SQL、token、Provider 配置和已退役记忆字段。
- 后端新增 no-data 年度 Snapshot shell，稳定返回 12 个月摘要、零值 summary、空 evidence、不可用 comparison 和空 fingerprint。
- 测试新增丰富年度、轻量年度、无数据年度、当前部分年度 fixture。

## 验证

已执行：

```bash
.venv312/bin/python -m pytest tests/test_career_year_snapshot_contract.py tests/test_career_snapshot_builder.py -q
.venv312/bin/python -m py_compile career_backend.py
```

结果：

- `13 passed in 0.13s`
- `career_backend.py` 编译通过。

## Review 结论

通过。本任务未新增持久化、未调用 LLM、未改前端、未改全生涯 fallback。`conn` 参数仅作为后续 01B 聚合扩展点保留，当前显式丢弃，避免 01A 越界读取数据库。

## 下一任务

`ACS-Year-AI-01B`：年度 Activity 聚合、运动分布与月度摘要。
