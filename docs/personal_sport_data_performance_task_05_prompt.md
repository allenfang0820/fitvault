---
title: Task 05 Prompt - 复盘快照缓存
version: v0.1.0
status: Ready
type: Engineering Execution Prompt
updated: 2026-07-23
source:
  - docs/personal_sport_data_performance_optimization_plan.md
  - docs/personal_sport_data_performance_task_list.md
  - docs/personal_sport_data_performance_contract_summary.md
---

# Task 05 Prompt - 复盘快照缓存

## 1. 启动要求

开始前必须执行 `git status --short`，阅读优化方案、任务清单 Task 05、契约摘要、`get_fatigue_review()`、`_build_fatigue_review_snapshot()`、历史趋势查询函数和复盘 API 契约，并刷新契约摘要。

重要偏离时必须回读原始契约：改变复盘指标语义、改变 curves/collapse_events/fatigue_zones/environment_factors shape、缓存 AI 生成内容、跳过低置信度判断或从前端补算事实。

## 2. 目标

为 `get_fatigue_review(activity_id)` 增加可失效后端快照缓存。缓存命中时不再重复执行 Resolver 快照、历史趋势查询和曲线解析；缓存 miss 保持旧路径并写入缓存。

## 3. 允许改动文件

- `main.py`
- `profile_backend.py`，仅限缓存表/helper
- `metrics_resolver.py`，仅限 resolver version/fingerprint
- 复盘相关测试或 `tests/test_personal_sport_data_performance_contract.py`
- `docs/personal_sport_data_performance_optimization_plan.md`
- `docs/personal_sport_data_performance_contract_summary.md`
- `docs/personal_sport_data_performance_task_list.md`
- `docs/personal_sport_data_performance_task_05_prompt.md`

## 4. 硬性约束

- 不改变复盘算法语义。
- 不缓存 AI 生成内容。
- 不牺牲缺失数据、低置信度、骑行/环境/事件文案契约。
- 缓存 key 至少包含 `activity_id`、activity `updated_at`、resolver/cache version。
- 缓存写入失败不得影响复盘返回。

## 5. 验证命令

```bash
git status --short
PYTHONPATH=. .venv312/bin/python -m pytest tests/test_fit_sync.py tests/test_personal_sport_data_performance_contract.py -q
.venv312/bin/python -m py_compile main.py profile_backend.py metrics_resolver.py
git diff --check
.venv312/bin/python scripts/benchmark_personal_sport_data.py --warm-runs 3
```

## 6. 完成定义

- Task 05 提示词已落盘。
- 契约摘要已刷新到 Task 05。
- 同一活动第二次复盘命中缓存，且构建函数不再执行。
- activity `updated_at` 或 cache/resolver version 变化后缓存失效。
- 实测记录写入优化方案和任务清单。

## 7. 下一任务建议

Task 06 进入复盘曲线降采样与按需全量。开始前必须刷新契约摘要，并确认缓存 payload 与降采样/full resolution 参数的交互。
