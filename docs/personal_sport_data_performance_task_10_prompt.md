---
title: Task 10 Prompt - 复盘 cache miss 后端构建剖析与优化
version: v0.1.0
status: Ready
type: Engineering Execution Prompt
updated: 2026-07-27
source:
  - docs/personal_sport_data_performance_task_09_completion_report.md
  - docs/personal_sport_data_performance_optimization_plan.md
  - docs/personal_sport_data_performance_task_list.md
  - docs/personal_sport_data_performance_contract_summary.md
---

# Task 10 Prompt - 复盘 cache miss 后端构建剖析与优化

## 1. 问题与目标

Task 09 已通过真实 pywebview `耗时` 弹窗确认：

| 样本 | cache | 总计 | API 往返 | 后端 | 面板渲染 | 图表 setOption | 曲线 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 2026-07-27 10:34 | hit | 96ms | 28ms | 15.1ms | 5ms | 60ms | 1206 / 3576 |
| 2026-07-27 11:12，雅安市骑行，疑似 `activities.id=1094` | miss | 4783ms | 4748ms | 3745.12ms | 4ms | 29ms | 990 / 2916 |

结论：3-5 秒体感主要来自复盘 `cache: miss` 后端构建，以及后端 `api_elapsed_ms` 之外约 1 秒的 pywebview/API 往返或调度开销；不是复盘面板 DOM 或 ECharts 同步首绘主导。

Task 10 的目标是用工程级阶段剖析定位 `cache: miss` 后端构建慢点，并在不改变复盘事实、公式、曲线轴、AI 输入和 sampled/full 语义的前提下做最小可验证优化。目标验收建议：

- `cache: miss` 后端 `api_elapsed_ms` 从约 3745ms 降到 < 1500ms，理想 < 1000ms。
- `cache: miss` pywebview 总计从约 4783ms 降到 < 2000ms，理想 < 1500ms。
- `cache: hit` 保持 < 150ms 级别，不因优化退化。
- 面板渲染和 ECharts 首绘不回归。

## 2. 启动要求

开始前必须完成以下动作：

1. 执行 `git status --short`，确认 dirty worktree；禁止清理、revert、覆盖或格式化无关改动。
2. 阅读：
   - `docs/personal_sport_data_performance_optimization_plan.md`
   - `docs/personal_sport_data_performance_task_list.md` 中 Task 09 和 Task 10 段落
   - `docs/personal_sport_data_performance_contract_summary.md`
   - `docs/personal_sport_data_performance_task_09_completion_report.md`
   - `docs/personal_sport_data_performance_task_10_prompt.md`
3. 刷新 `docs/personal_sport_data_performance_contract_summary.md` 的“最近刷新记录”，将当前任务更新为 Task 10，并摘要本轮必须遵守的 API、snapshot、隐私、dirty worktree 边界。
4. 全文阅读真实复盘后端路径：
   - `main.py::get_fatigue_review()`
   - `main.py::_build_fatigue_review_snapshot()`
   - `main.py::_prepare_fatigue_review_snapshot_for_response()`
   - `main.py::_store_fatigue_review_snapshot_cache()`
   - `main.py::_fetch_historical_metrics_avg()`
   - `main.py::_fetch_efficiency_trend()`
   - `main.py::_fetch_durability_trend()`
   - `main.py::_fetch_cadence_stability_trend()`
   - `main.py::_review_historical_curve_cached()`
   - 曲线 bundle / display curves / cadence curve 相关 helper
5. 阅读相关契约和测试：
   - `docs/js_api_contract.json` 中 `get_fatigue_review`
   - `docs/field_contract_matrix.md`
   - `docs/脉图运动复盘系统_开发团队交付手册_v1.md`
   - `docs/运动详情页多运动升级开发交付手册.md`
   - `tests/test_personal_sport_data_performance_contract.py`
   - `tests/test_response_envelope_contract.py`
   - 复盘 snapshot / E2E / quality 相关聚焦测试

若执行中发现需要改变返回 shape、复盘字段语义、曲线轴、疲劳带/事件位置、AI 输入边界、API envelope、sampled/full 默认语义，必须暂停实现，重新全文阅读相关原始契约后再继续，并把偏离原因写入契约摘要。

## 3. 允许改动文件

优先允许：

- `main.py`
- `tests/test_personal_sport_data_performance_contract.py`
- 必要时新增聚焦后端性能测试
- `docs/personal_sport_data_performance_contract_summary.md`
- `docs/personal_sport_data_performance_task_list.md`
- `docs/personal_sport_data_performance_optimization_plan.md`
- 可新增 `docs/personal_sport_data_performance_task_10_completion_report.md`

仅在确有契约同步需要时允许：

- `docs/js_api_contract.json`
- `scripts/benchmark_personal_sport_data.py`

默认不修改：

- `track.html`，除非只补不含敏感数据的后端阶段耗时展示字段。
- `metrics_resolver.py`，除非剖析证明瓶颈来自纯函数计算且改动不改变语义。

禁止修改：

- Garmin/COROS 同步与导入链路。
- AI/LLM prompt、AI 质量或 AI 输入字段语义。
- Records Center。
- schema 大迁移或新建长期性能日志表。
- 复盘指标公式、历史窗口、Resolver 口径、曲线轴、疲劳带/事件位置。
- sampled/full 默认语义和 full 数据真实性。

## 4. 契约与隐私约束

- 继续保持 pywebview 统一 envelope：`{ok, code, msg, data, traceId}`。
- `get_fatigue_review(activity_id)` 默认仍返回 sampled 首屏；`full` 仍只能通过显式参数按需返回。
- 优化不得删除、改名、补算或篡改复盘事实字段。
- 不得把前端 DOM、ECharts、截图、活动标题、设备、天气卡、points、records、raw records、curves 作为新的事实来源。
- 性能剖析只允许记录阶段名、耗时、计数、cache hit/miss、曲线点数、SQLite 查询次数等元数据。
- 禁止记录 raw points、full curves、records、活动标题、照片、文件路径、API key、用户隐私配置和 AI 内容。
- 若新增诊断字段，必须只进入诊断元数据，不进入复盘 snapshot、AI compact snapshot 或用户数据库大表。

## 5. 实现步骤

### 5.1 先做阶段剖析

在 `get_fatigue_review()` 的 `cache: miss` 路径补最小后端阶段计时，至少拆出：

- `_fetch_activity_row`
- `_fatigue_review_cache_fingerprint`
- `_load_fatigue_review_snapshot_cache`
- `_build_fatigue_review_snapshot`
- `_prepare_fatigue_review_snapshot_for_response`
- `_store_fatigue_review_snapshot_cache`

在 `_build_fatigue_review_snapshot()` 内部继续拆：

- curve bundle / Resolver / curves snapshot
- display curves
- HR drift
- historical avg
- efficiency score / efficiency trend
- durability trend
- cadence stability trend
- environment factors
- summary / advice / snapshot assembly

阶段耗时可以通过后端 `_record_startup_event()` 或响应内受控诊断字段返回，但不得改变业务字段语义。若返回新诊断字段，必须同步 `docs/js_api_contract.json` 和测试。

### 5.2 用真实活动复现

优先复现疑似活动：

- `activities.id=1094`
- 标题：雅安市 骑行
- 时间：2026-07-20 18:50:51
- `duration_sec=2918`
- `dist_km=23.77559`
- 截图曲线约 `990 / 2916`

先在只读/可控方式下清理或绕过该活动的复盘 snapshot cache，使 `get_fatigue_review(1094)` 确认走 `cache: miss`。不要清理无关 cache；如需删除单条 cache，必须只针对该 `activity_id` 的 `fatigue_review_snapshot_cache` 记录，并在完成报告中说明。

### 5.3 再做最小优化

根据剖析结果选择最小优化，不预设根因。优先考虑：

- 合并 21 天历史趋势查询，避免 `_fetch_efficiency_trend`、`_fetch_durability_trend`、`_fetch_cadence_stability_trend` 分别扫描和解析同一批历史活动。
- 缓存同一请求内历史活动的 canonical points/derived curves 解析结果，避免重复 JSON loads。
- 对历史趋势只取 21 天窗口和必要字段，不读取更大范围或无关 JSON。
- 将 snapshot cache 写入从首屏响应关键路径中移出或缩短，但必须保证 cache miss 后下一次命中语义稳定；若异步写入，必须有失败兜底且不得吞掉业务响应。
- 避免在 `cache: miss` 响应路径里构建 full 曲线 payload；默认首屏只做 sampled 响应准备，full 保持按需。

不得为了速度直接跳过低置信度判断、删除趋势字段、改变历史窗口、改指标公式或降低曲线真实性。

## 6. 测试与验收

必须运行：

```bash
git status --short
PYTHONPATH=. .venv312/bin/python -m pytest tests/test_response_envelope_contract.py tests/test_personal_sport_data_performance_contract.py -q
.venv312/bin/python -m py_compile main.py
jq empty docs/js_api_contract.json
git diff --check
```

建议按需运行复盘相关聚焦测试：

```bash
PYTHONPATH=. .venv312/bin/python -m pytest tests/test_fatigue_review_snapshot_realignment.py tests/test_fatigue_review_e2e_contract.py tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py -q
```

建议补真实 API 微基准：

```bash
.venv312/bin/python - <<'PY'
import time
import main

api = main.Api()
activity_id = 1094
for i in range(3):
    started = time.perf_counter()
    res = api.get_fatigue_review(activity_id)
    elapsed = (time.perf_counter() - started) * 1000
    data = res.get("data") or {}
    print({
        "run": i + 1,
        "ok": res.get("ok"),
        "elapsed_ms": round(elapsed, 2),
        "api_elapsed_ms": data.get("api_elapsed_ms"),
        "cache_status": data.get("cache_status"),
        "curve_resolution": data.get("curve_resolution"),
        "curve_points_returned": data.get("curve_points_returned"),
        "curve_points_original": data.get("curve_points_original"),
    })
PY
```

验收必须记录：

- 优化前 `cache: miss` 阶段耗时表。
- 优化后 `cache: miss` 阶段耗时表。
- `cache: hit` 对照耗时。
- payload 大小和曲线点数。
- 是否仍能在真实 pywebview `耗时` 弹窗看到改善。
- 任何未优化的残余瓶颈和下一步建议。

## 7. 完成定义

完成时必须：

- 新增或更新 Task 10 完成报告。
- 更新任务清单 Task 10 状态。
- 更新优化方案当前状态。
- 刷新契约摘要最近记录，说明是否发生偏离和是否回读原始契约。
- 给出真实样本的前后对比，不用“应该更快”替代实测。
- 明确说明 dirty worktree 未被清理、未创建分支、未创建 worktree。

## 8. 非目标

- 不做 UI 大改。
- 不做复盘图表视觉优化。
- 不处理 AI 生成速度或 AI 质量。
- 不处理 Garmin/COROS 同步、导入或重复活动逻辑。
- 不新增 Records Center 能力。
- 不新建大表或长期性能日志。
- 不在没有证据时把 1 秒 pywebview/API 往返归因到某一层。
