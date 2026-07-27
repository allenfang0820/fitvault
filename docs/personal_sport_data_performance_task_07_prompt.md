---
title: Task 07 Prompt - 复盘历史趋势查询合并与解析缓存
version: v0.1.0
status: Ready
type: Engineering Execution Prompt
updated: 2026-07-24
source:
  - docs/personal_sport_data_performance_optimization_plan.md
  - docs/personal_sport_data_performance_task_list.md
  - docs/personal_sport_data_performance_contract_summary.md
---

# Task 07 Prompt - 复盘历史趋势查询合并与解析缓存

## 1. 启动要求

开始前必须执行 `git status --short`，阅读优化方案、任务清单 Task 07、契约摘要、复盘历史趋势函数、历史曲线解析函数和相关测试，并刷新契约摘要。

如果执行中需要改变趋势指标公式、历史窗口、baseline basis/version、缺失数据降级规则、`curves` 字段语义，或引入新的物化表/schema 迁移，必须暂停当前修改，重新全文阅读相关原始契约文档，再继续。

## 2. 目标

减少复盘 cache miss 构建中的重复历史 SQLite 查询和重复历史曲线 JSON 解析，优先降低 `_fetch_durability_trend()` 与 `_fetch_cadence_stability_trend()` 的重复解析成本。

## 3. 允许改动文件

- `main.py`
- `profile_backend.py`，仅限必要 helper
- `metrics_resolver.py`，仅限趋势 fingerprint 或共享计算入口
- 趋势/复盘相关测试或 `tests/test_personal_sport_data_performance_contract.py`
- `docs/personal_sport_data_performance_optimization_plan.md`
- `docs/personal_sport_data_performance_contract_summary.md`
- `docs/personal_sport_data_performance_task_list.md`
- `docs/personal_sport_data_performance_task_07_prompt.md`

## 4. 硬性约束

- 不改变趋势公式和历史窗口。
- 不改变缺失数据、低置信度和 basis/version 语义。
- 不读取 sampled 曲线作为历史趋势事实源。
- 不把前端、ECharts、DOM 或标题/设备/天气卡纳入趋势计算。
- 不新增 schema/物化表，除非先冻结失效规则并更新文档。

## 5. 实现要点

- 优先引入请求内历史曲线解析缓存，缓存 raw history JSON 的解析结果和按字段提取结果。
- 同一个复盘 cache miss 内，相同历史 `track_json` / `points_json` 不应被 durability/cadence 趋势重复 `json.loads`。
- 缓存生命周期只覆盖当前复盘构建，构建结束后清空，避免跨活动陈旧数据。
- 若合并 SQL 查询会扩大语义风险，可先不做物化表，记录为后续可选项。

## 6. 验证命令

```bash
git status --short
PYTHONPATH=. .venv312/bin/python -m pytest tests/test_fit_sync.py tests/test_personal_sport_data_performance_contract.py -q
.venv312/bin/python -m py_compile main.py profile_backend.py metrics_resolver.py
git diff --check
.venv312/bin/python scripts/benchmark_personal_sport_data.py --warm-runs 3
```

## 7. 完成定义

- Task 07 提示词已落盘。
- 契约摘要已刷新到 Task 07。
- 历史曲线解析有请求内缓存覆盖。
- 相同历史 raw JSON 在同一复盘构建中可复用解析结果。
- 复盘趋势语义、缺失数据降级、basis/version 不变。
- 实测记录写入优化方案和任务清单。

## 8. 下一任务建议

Task 08 进入最终回归与真实用户路径验收。开始前必须刷新契约摘要，并使用真实 UI 分段埋点检查列表、概览、复盘首屏和 full 曲线按需路径。
