---
title: Task 08 Prompt - 最终回归与真实用户路径验收
version: v0.1.0
status: Ready
type: Engineering Execution Prompt
updated: 2026-07-24
source:
  - docs/personal_sport_data_performance_optimization_plan.md
  - docs/personal_sport_data_performance_task_list.md
  - docs/personal_sport_data_performance_contract_summary.md
---

# Task 08 Prompt - 最终回归与真实用户路径验收

## 1. 启动要求

开始前必须完成以下动作：

1. 执行 `git status --short`，确认 dirty worktree，禁止清理、revert、覆盖无关改动。
2. 阅读 `docs/personal_sport_data_performance_optimization_plan.md`。
3. 阅读 `docs/personal_sport_data_performance_task_list.md` 中 Task 08 段落。
4. 阅读并刷新 `docs/personal_sport_data_performance_contract_summary.md` 的“最近刷新记录”，将当前任务更新为 Task 08。
5. 阅读 Task 01-07 完成证据，尤其是列表分页、schema sentinel、detail summary、review cache、sampled/full 曲线和历史曲线解析缓存的实测记录。
6. 阅读真实用户路径相关入口：
   - `track.html::loadSportHubActivityList()`
   - `track.html::openActivityDetailModal()`
   - `track.html::fetchSportHubActivityDetail()`
   - `track.html::openFatigueReview()`
   - `main.py::get_sport_hub_activity_page()`
   - `main.py::get_activity_list()`
   - `main.py::get_activity_detail_summary()`
   - `main.py::get_activity_detail()`
   - `main.py::get_fatigue_review()`

如果验收中发现返回 shape、字段语义、分页/去重、复盘结论、曲线轴、事件/疲劳带、AI 输入边界、前端零推断或 API envelope 存在重要偏离，必须暂停修复，重新全文阅读相关原始契约文档，再继续。

## 2. 目标

完成“个人运动数据”三条真实用户路径的最终回归验收：

- 活动列表首屏。
- 活动概览首屏。
- 复盘 tab 首屏与 full 曲线按需路径。

输出一个可审计的完成报告，记录优化前后对比、真实 UI 分段耗时、后端微基准、payload、验证命令、残余风险和后续建议。

## 3. 允许改动文件

- `docs/personal_sport_data_performance_optimization_plan.md`
- `docs/personal_sport_data_performance_task_list.md`
- `docs/personal_sport_data_performance_contract_summary.md`
- `docs/personal_sport_data_performance_task_08_prompt.md`
- 可新增 `docs/personal_sport_data_performance_completion_report.md`
- 仅限修复验收中发现的本任务范围内小问题：
  - `main.py`
  - `track.html`
  - `docs/js_api_contract.json`
  - 聚焦测试文件

发现需要修改 Garmin/COROS 同步、AI 质量、Records Center、打包流程、schema 大迁移或 UI 大改时，必须停止并记录为后续任务，不在 Task 08 内扩展。

## 4. 硬性约束

- 不新建分支，不新建 worktree。
- 不清理、不 revert、不格式化无关 dirty 文件。
- 不改变活动事实字段、复盘指标公式、AI 输入边界、分页/去重语义或 API envelope。
- 不把 sampled 曲线当作 canonical 数据源；full 曲线必须仍可按需请求。
- 不通过前端 DOM、ECharts、截图、标题、设备或天气卡补算事实。
- 只允许记录最小性能诊断，不记录 raw points、records、full curves 内容、本地文件内容、API key 或用户隐私配置。

## 5. 验收步骤

### 5.1 后端与契约验证

运行：

```bash
git status --short
PYTHONPATH=. .venv312/bin/python -m pytest tests/test_fit_sync.py tests/test_response_envelope_contract.py tests/test_personal_sport_data_performance_contract.py -q
.venv312/bin/python -m py_compile main.py profile_backend.py metrics_resolver.py
git diff --check
.venv312/bin/python scripts/benchmark_personal_sport_data.py --warm-runs 3
```

记录：

- 活动列表 API cold-ish / warm 耗时、payload。
- 活动概览 summary 与 full detail 耗时、payload。
- 复盘 sampled hit/miss 耗时、payload、`curve_points_original`、`curve_points_returned`。
- `get_fatigue_review(activity_id, "full")` 耗时、payload、点数。

### 5.2 真实 UI 路径验收

启动本地应用并手动进入：

1. 个人运动数据列表页。
2. 最近活动概览弹窗。
3. 同一活动复盘 tab。
4. 长活动复盘 tab。
5. full 曲线按需路径，如当前 UI 尚未提供按钮，则用 pywebview 控制台或后端直接调用确认。

采集 `markStartupPhase` 或等效日志，至少记录：

- `activity_list_api_done`
- `activity_list_render_done`
- `activity_detail_summary_api_done`
- `activity_detail_summary_render_done`
- `activity_detail_api_done`
- `activity_detail_render_done`
- `fatigue_review_api_done`
- `fatigue_review_panels_done`
- `fatigue_review_chart_done`

### 5.3 人工回归检查

检查并记录：

- 列表分页 total 正确，无明显漏项或重复项。
- 列表排序、运动类型筛选、标题搜索仍可用。
- 概览首屏字段完整，summary 不被误当完整详情缓存。
- 完整详情渐进加载后轨迹缩略图、laps、照片能力不回退。
- 复盘 summary、metrics、collapse_events、fatigue_zones、environment_factors、cycling_explanation_signals 仍来自后端。
- sampled 曲线图可绘制，事件 pins 和疲劳带位置合理。
- full 曲线按需请求可用，不阻塞默认首屏。

## 6. 验收指标

- 活动列表首屏 < 800ms，热态 < 150ms。
- 活动概览首屏 < 800ms，热态 < 200ms。
- 复盘首屏 < 1.5s。
- 长活动默认复盘 payload 明显低于 Task 01 约 2.67-3.25MB 基线。
- full 曲线仍能返回全量点，且不替代默认 sampled 首屏。
- 无分页漏项、重复项、详情字段缺失、复盘结论漂移或前端事实补算。

## 7. 完成报告要求

新增或更新 `docs/personal_sport_data_performance_completion_report.md`，至少包含：

- 背景与优化范围。
- Task 01-07 实施摘要。
- 优化前后对比表。
- 后端微基准表。
- 真实 UI 分段耗时表。
- 验证命令与结果。
- 未处理残余风险。
- 回滚策略。
- 后续建议。

同时更新：

- `docs/personal_sport_data_performance_task_list.md`：将 Task 08 标为 completed 并记录完成证据。
- `docs/personal_sport_data_performance_optimization_plan.md`：补最终验收结论。
- `docs/personal_sport_data_performance_contract_summary.md`：刷新到 Task 08 完成状态。

## 8. 非目标

- 不扩展到 Garmin/COROS 同步性能。
- 不处理 AI 质量或 LLM prompt。
- 不追加 UI 大改。
- 不处理 Records Center 新功能。
- 不新增趋势物化表或数据库重构。

## 9. 下一步建议

Task 08 是本轮性能优化闭环任务。完成后，如真实 UI 仍未达到目标，应按报告中的残余风险拆新任务，优先级建议为：

1. 真实 UI ECharts setOption 仍慢：单独优化图表渲染和渐进绘制。
2. 复盘 cache miss 仍慢：在新契约下评估历史趋势 SQL 合并或物化表。
3. full 曲线交互不够顺：补 UI 按需加载入口，但不得改变默认 sampled 首屏。
