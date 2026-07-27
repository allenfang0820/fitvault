---
title: Task 10 Completion Report - 复盘 cache miss 后端构建剖析与优化
version: v0.1.0
status: Completed
updated: 2026-07-27
---

# Task 10 Completion Report - 复盘 cache miss 后端构建剖析与优化

## 1. 背景

Task 09 真实 pywebview 样本显示，复盘 `cache: miss` 时总计 4783ms，API 往返 4748ms，后端 `api_elapsed_ms` 3745.12ms，面板渲染 4ms，ECharts `setOption` 29ms。瓶颈明确在后端 miss 构建和 pywebview/API 往返，不在前端面板或图表首绘。

本任务聚焦 `get_fatigue_review()` 的 miss 后端路径，不改变复盘事实、指标公式、曲线轴、疲劳带/事件、AI 输入、sampled/full 语义或 full 数据真实性。

## 2. 本次交付

- 新增 `review_backend_profile` 响应诊断字段，只包含阶段名、耗时、计数、cache 状态、曲线分辨率和曲线点数。
- `review_backend_profile` 只存在于 API 响应诊断中，不写入 `fatigue_review_snapshot_cache`，不进入 AI compact snapshot。
- `get_fatigue_review()` miss/hit 路径增加阶段剖析：
  - `fetch_activity_row`
  - `cache_fingerprint`
  - `load_snapshot_cache`
  - `build_snapshot`
  - `store_snapshot_cache`
  - `prepare_response`
- `_build_fatigue_review_snapshot()` 内增加受控阶段剖析：
  - curve bundle
  - Resolver/GAP
  - curves snapshot
  - display curves
  - historical metrics avg
  - efficiency/durability/cadence/training load trends
  - summary/signals
  - events/metric gate
- 优化 durability/cadence 历史趋势查询：
  - 先按粗 SQL 时间窗读取轻字段和派生曲线。
  - Python 继续做权威 21 天窗口判断。
  - 只对窗口内候选活动批量读取 `track_json/points_json`，保留 canonical 优先级。
- 优化轻字段历史查询：
  - `_fetch_efficiency_trend`
  - `_fetch_training_load_trend`
  - `_fetch_load_ratio_7d_42d`
  - `metrics_resolver.MetricsResolver._fetch_efficiency_baseline`
- 新增 pywebview 前端 ready 后的后台 GAP 数值依赖预热，降低首次复盘时 numpy/scipy import 进入用户点击路径的概率。

## 3. 实测结果

目标活动：疑似截图活动 `activities.id=1094`，雅安市骑行，`duration_sec=2918`，`dist_km=23.77559`。

为复现 miss，验证过程中只删除过该活动的单条缓存：

```sql
DELETE FROM fatigue_review_snapshot_cache WHERE activity_id=1094;
```

未清理其他活动缓存，未修改 activities 业务数据。

### 优化前基线

| 场景 | elapsed | api_elapsed_ms | cache | 曲线 |
| --- | ---: | ---: | --- | --- |
| Task 09 真实 pywebview | 4783ms | 3745.12ms | miss | 990 / 2916 |
| Task 10 本地 API 基线 | 3553.18ms | 3550.05ms | miss | 990 / 2916 |
| Task 10 cProfile 基线 | 1908.87ms | 1899.85ms | miss | 990 / 2916 |

cProfile 基线主要耗时：

- `_build_fatigue_review_snapshot()`：约 1.89s。
- Resolver/GAP：约 0.73-0.94s，包含 scipy/numpy 首次依赖加载。
- SQLite execute/fetch：约 1.0s，主要来自历史趋势查询读取过宽历史和大 JSON。
- `_fetch_cadence_stability_trend()`：约 0.65s。
- `_fetch_durability_trend()`：约 0.29s。

### 优化后

| 场景 | elapsed | api_elapsed_ms | cache | 曲线 |
| --- | ---: | ---: | --- | --- |
| 1094 miss，GAP 依赖已预热 | 1157.71ms | 1154.18ms | miss | 990 / 2916 |
| 1094 miss，顺序冷测 | 657.42ms | 654.18ms | miss | 990 / 2916 |
| 1094 hit 对照 | 8.71ms | 5.32ms | hit | 990 / 2916 |

优化后典型阶段：

- `resolver_payload`：约 413ms，仍是最大单项计算。
- `historical_metrics_avg`：约 2.31ms。
- `efficiency_trend`：约 23.98ms。
- `durability_trend`：约 49.64ms。
- `cadence_stability_trend`：约 55.35ms。
- `load_ratio_7d_42d`：约 25.02ms。
- `training_load_trend`：约 24.78ms。
- `store_snapshot_cache`：约 6.79ms。
- `prepare_response`：约 3.05ms。

## 4. 当前结论

Task 10 后，目标活动的 API miss 后端耗时已从约 3.55-3.75s 降到约 0.65-1.15s，达到并优于 <1500ms 的验收目标。cache hit 维持在 5-9ms 级别。

剩余主要瓶颈：

- Resolver/GAP 计算约 0.4s，属于真实计算成本。
- pywebview 端仍需重启应用后用 `耗时` 按钮复测，确认 API 往返总计是否同步降到 <2s。

## 5. 验证

已通过：

```bash
PYTHONPATH=. .venv312/bin/python -m pytest tests/test_response_envelope_contract.py tests/test_personal_sport_data_performance_contract.py -q
```

结果：`43 passed in 0.36s`

已通过：

```bash
PYTHONPATH=. .venv312/bin/python -m pytest tests/test_fatigue_review_snapshot_realignment.py tests/test_fatigue_review_e2e_contract.py tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py -q
```

结果：`219 passed in 1.40s`

已通过：

```bash
.venv312/bin/python -m py_compile main.py metrics_resolver.py
jq empty docs/js_api_contract.json
```

`git diff --check` 将在最终文档更新后重新执行。
