---
title: ACS-Year-AI-01B 年度 Activity 聚合完成报告
task: ACS-Year-AI-01B
status: Done
updated: 2026-07-14
---

# ACS-Year-AI-01B 年度 Activity 聚合完成报告

## 工程级提示词摘要

目标：实现 Year Snapshot 的 Activity 事实层，按目标自然年聚合有效 Activity，输出年度 summary、sport_breakdown、12 个月 month_digest 和 available_years。

范围：`career_backend.py`、`tests/test_career_year_snapshot_activity_aggregation.py`、契约测试、任务清单、执行日志和本完成报告。

约束：不输出普通 Activity 明细；不从标题推断事实；不读取轨迹点补算年度距离；不实现 Resolver evidence、同期比较、fingerprint、持久化、API 或前端。

## 交付内容

- `build_career_year_snapshot` 已填充 Activity 聚合事实。
- 新增 `get_career_year_snapshot_available_years`，返回基于有效 Activity 的倒序年份。
- 月度摘要稳定输出 1 至 12 月，无活动月份为零值。
- sport_breakdown 按规范化 sport 稳定排序。
- 距离精度统一为 1 位小数，时长为整数秒。

## 验证

已执行：

```bash
.venv312/bin/python -m pytest tests/test_career_year_snapshot_activity_aggregation.py tests/test_career_year_snapshot_contract.py tests/test_career_snapshot_builder.py -q
.venv312/bin/python -m py_compile career_backend.py
```

结果：

- `18 passed in 0.11s`
- `career_backend.py` 编译通过。

## Review 结论

通过。Snapshot 输出不包含普通 Activity 明细、活动标题、points、track、本地路径、照片或媒体引用；未改全生涯 Career Snapshot fallback，未新增持久化和 LLM 调用。

## 下一任务

`ACS-Year-AI-01C`：年度 Resolver evidence catalog。
