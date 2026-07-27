---
title: Task 06 Prompt - 复盘曲线降采样与按需全量
version: v0.1.0
status: Ready
type: Engineering Execution Prompt
updated: 2026-07-24
source:
  - docs/personal_sport_data_performance_optimization_plan.md
  - docs/personal_sport_data_performance_task_list.md
  - docs/personal_sport_data_performance_contract_summary.md
---

# Task 06 Prompt - 复盘曲线降采样与按需全量

## 1. 启动要求

开始前必须执行 `git status --short`，阅读优化方案、任务清单 Task 06、契约摘要、`get_fatigue_review()`、复盘曲线构建与图表渲染代码、复盘 API 契约，并刷新契约摘要。

如果执行中发现需要改变 `curves` / `display_curves` / `collapse_events` / `fatigue_zones` 的字段语义，或需要让前端从 DOM、ECharts、points、records、标题、设备、天气卡补算事实，必须暂停当前修改，重新全文阅读相关原始契约文档，再继续。

## 2. 目标

复盘首屏默认返回展示用降采样曲线，把长活动默认 payload 从 3MB 级别降下来；全量曲线通过显式参数按需请求，供放大、导出或精细分析使用。

## 3. 允许改动文件

- `main.py`
- `track.html`
- `docs/js_api_contract.json`
- 复盘图表相关测试或 `tests/test_personal_sport_data_performance_contract.py`
- `docs/personal_sport_data_performance_optimization_plan.md`
- `docs/personal_sport_data_performance_contract_summary.md`
- `docs/personal_sport_data_performance_task_list.md`
- `docs/personal_sport_data_performance_task_06_prompt.md`

## 4. 硬性约束

- 不改变复盘算法语义。
- 不删除全量曲线；默认首屏降采样只影响展示 payload。
- 降采样后的 `curves.distance` 仍是后端权威距离轴，前端不得重建事实轴。
- `curves` 与 `display_curves` 必须保持同轴同长度；长度不匹配时不得让前端补齐。
- `collapse_events` 与 `fatigue_zones` 语义不变，事件定位必须落在保留的距离轴附近。
- 不改 Garmin/COROS 同步、AI、Records Center、schema 冷路径或复盘历史趋势算法。

## 5. 实现要点

- 为 `get_fatigue_review(activity_id, curve_resolution='sampled')` 增加可选分辨率参数；默认 `sampled`，显式 `full` 返回全量。
- Task 05 缓存应保存完整后端 snapshot；响应层根据 `curve_resolution` 派生 sampled/full，避免把 sampled 缓存误当 canonical。
- 默认 sampled 目标点数控制在 800-1500 点。
- 降采样索引必须包含首尾点、均匀采样点、各曲线关键极值点，以及 `collapse_events.trigger_km`、`fatigue_zones.start_km/end_km` 附近点。
- 返回诊断元信息，例如 `curve_resolution`、`curve_points_original`、`curve_points_returned`、`full_curves_available`。
- 前端首屏继续调用默认 sampled；需要全量曲线的后续交互显式调用 `get_fatigue_review(activityId, 'full')` 或等价参数。

## 6. 验证命令

```bash
git status --short
PYTHONPATH=. .venv312/bin/python -m pytest tests/test_response_envelope_contract.py tests/test_personal_sport_data_performance_contract.py -q
.venv312/bin/python -m py_compile main.py
git diff --check
.venv312/bin/python scripts/benchmark_personal_sport_data.py --warm-runs 3
```

## 7. 完成定义

- Task 06 提示词已落盘。
- 契约摘要已刷新到 Task 06。
- 默认复盘返回 sampled 曲线，长活动 payload 明显下降。
- 显式 full 请求可返回全量曲线。
- sampled 曲线保留首尾、关键极值和事件/疲劳带附近点。
- JS API 契约、测试、优化方案和任务清单已同步。

## 8. 下一任务建议

Task 07 进入复盘历史趋势查询合并/物化。开始前必须刷新契约摘要；如果 Task 06 引入的 sampled/full 参数影响缓存 fingerprint 或历史趋势字段，Task 07 必须先全文回读复盘缓存与曲线契约。
