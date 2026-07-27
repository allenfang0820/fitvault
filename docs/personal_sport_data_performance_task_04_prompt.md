---
title: Task 04 Prompt - 活动概览轻量首屏
version: v0.1.0
status: Ready
type: Engineering Execution Prompt
updated: 2026-07-23
source:
  - docs/personal_sport_data_performance_optimization_plan.md
  - docs/personal_sport_data_performance_task_list.md
  - docs/personal_sport_data_performance_contract_summary.md
---

# Task 04 Prompt - 活动概览轻量首屏

## 1. 启动要求

开始前必须执行 `git status --short`，阅读优化方案、任务清单 Task 04、契约摘要、`docs/js_api_contract.json` 详情 API 段落，以及 `main.py` / `track.html` 的详情打开路径，并刷新契约摘要。

如果执行中需要改变旧 `get_activity_detail` 返回语义、复盘 tab 数据源、前端事实推断规则、轨迹原始数据或照片存储契约，必须暂停并全文回读相关原始契约。

## 2. 目标

新增活动概览 summary 首屏路径：打开活动详情时先用轻量 API 渲染标题、时间、地点、运动类型、关键指标、设备、天气和能力占位，再后台加载旧完整详情，补全轨迹缩略图、laps、训练收益、环境挑战、照片等重内容。

## 3. 允许改动文件

- `main.py`
- `track.html`
- `docs/js_api_contract.json`
- 详情相关测试，例如 `tests/test_response_envelope_contract.py` 或 `tests/test_personal_sport_data_performance_contract.py`
- `docs/personal_sport_data_performance_optimization_plan.md`
- `docs/personal_sport_data_performance_contract_summary.md`
- `docs/personal_sport_data_performance_task_list.md`
- `docs/personal_sport_data_performance_task_04_prompt.md`

## 4. 硬性约束

- 保留旧 `get_activity_detail(activity_id)` 契约。
- summary API 不读取 `track_json` / `points_json` / `laps_json` / 曲线大字段。
- summary 记录必须带 `detail_pending=true` 或等价标记，避免被当作完整详情缓存。
- 前端只渲染后端字段，不从 DOM、ECharts、points、curves、标题或设备推导事实。
- 不处理复盘 tab，不改变复盘 API。

## 5. 验证命令

```bash
git status --short
PYTHONPATH=. .venv312/bin/python -m pytest tests/test_response_envelope_contract.py tests/test_personal_sport_data_performance_contract.py -q
.venv312/bin/python -m py_compile main.py
git diff --check
.venv312/bin/python scripts/benchmark_personal_sport_data.py --warm-runs 3
```

## 6. 完成定义

- Task 04 提示词已落盘。
- 契约摘要已刷新到 Task 04。
- `get_activity_detail_summary(activity_id)` 可用并写入 API 契约。
- 前端先渲染 summary，再渐进加载完整 detail。
- summary payload 明显小于旧 detail payload。
- 旧详情 API 仍可用。

## 7. 下一任务建议

Task 05 进入复盘快照缓存。开始前必须刷新契约摘要；如果要缓存复盘 snapshot，必须先明确 activity fingerprint 与 resolver version。
