---
title: Task 09 Prompt - 真实 pywebview 复盘首屏可观测性与瓶颈定位
version: v0.1.0
status: Ready
type: Engineering Execution Prompt
updated: 2026-07-27
source:
  - docs/personal_sport_data_performance_completion_report.md
  - docs/personal_sport_data_performance_optimization_plan.md
  - docs/personal_sport_data_performance_task_list.md
  - docs/personal_sport_data_performance_contract_summary.md
---

# Task 09 Prompt - 真实 pywebview 复盘首屏可观测性与瓶颈定位

## 1. 问题与目标

用户在 2026-07-27 的真实 pywebview 应用窗口中反馈：进入复盘仍需等待约 3-5 秒。

Task 08 的后端微基准已证明默认 sampled API、缓存命中和 payload 已明显收敛，但未成功采集真实 pywebview 的 API 往返、DOM 面板渲染和 ECharts 绘制分段。因此 Task 09 的目标不是直接“继续提速”，而是建立真实窗口可读取、可复现、最小隐私暴露的性能证据，明确等待主要来自：

- backend cache miss / hit 和 pywebview 序列化往返；
- 前端复盘面板同步渲染；
- ECharts 初始化、`setOption`、动画、resize 或可见性重试；
- 图片、轨迹缩略图或其他同屏异步工作；
- 首次 import / Resolver / 历史趋势构建。

完成后必须给出按真实数据排序的下一步优化任务；没有实测证据不得直接把 ECharts、后端或 pywebview 任一层认定为根因。

## 2. 启动要求

开始前必须完成以下动作：

1. 执行 `git status --short`，确认 dirty worktree；禁止清理、revert、覆盖或格式化无关改动。
2. 阅读：
   - `docs/personal_sport_data_performance_optimization_plan.md`
   - `docs/personal_sport_data_performance_completion_report.md`
   - `docs/personal_sport_data_performance_task_list.md` 中 Task 09 段落
   - `docs/personal_sport_data_performance_contract_summary.md`
   - `docs/personal_sport_data_performance_task_09_prompt.md`
3. 阅读并刷新契约摘要的“最近刷新记录”，将当前任务更新为 Task 09。
4. 全文阅读真实路径入口和既有埋点：
   - `track.html::switchDetailTab()`
   - `track.html::openFatigueReview()`
   - `track.html::markStartupPhase()`
   - `track.html::reportStartupTimeline()`
   - `track.html::renderProfileAnalysisChart()`
   - `main.py::get_fatigue_review()`
   - `main.py::get_startup_timeline()`
5. 阅读 `docs/js_api_contract.json`、复盘 snapshot/envelope 契约和相关测试。

若发现返回 shape、复盘字段语义、曲线轴、疲劳带/事件位置、AI 输入边界、API envelope 或前端零推断规则需要变更，必须暂停实现，重新全文阅读相关原始契约后再继续。

## 3. 允许改动文件

- `track.html`
- `main.py`
- `docs/js_api_contract.json`
- `tests/test_personal_sport_data_performance_contract.py`
- 必要时新增聚焦性能诊断测试
- `docs/personal_sport_data_performance_contract_summary.md`
- `docs/personal_sport_data_performance_task_list.md`
- `docs/personal_sport_data_performance_optimization_plan.md`
- 可新增 `docs/personal_sport_data_performance_task_09_completion_report.md`

除非验证暴露明确的本任务范围内 bug，否则不修改：

- `profile_backend.py` 的列表/导入语义或 schema 迁移；
- Garmin/COROS 同步；
- AI/LLM prompt、AI 质量；
- Records Center；
- 复盘指标公式、历史窗口、Resolver 口径；
- sampled/full 曲线真实性和 API 默认语义；
- UI 信息架构或视觉大改。

## 4. 契约与隐私约束

- 继续保持 pywebview 统一 envelope：`{ok, code, msg, data, traceId}`。
- 前端只上报最小性能诊断：阶段名、时间戳/相对耗时、`activity_id`、roundtrip/backend/render/chart ms、cache status、curve point count、payload byte count。
- 禁止上报或持久化 raw points、full curves、records、活动标题、照片、文件路径、API key、用户隐私配置和 AI 内容。
- 性能诊断不得改变、补算或覆盖后端事实；前端不得从 DOM/ECharts 推导运动事实或复盘结论。
- 诊断通道默认仅保留进程内有限条目，允许显式读取最近一次/有限历史；不得写入用户数据库的大表或无限增长日志。
- `reportStartupTimeline()` 现有 console 输出可保留，但 Task 09 必须提供真实 pywebview 中可读取的等价受控通道，不能仅依赖不可见 console。

## 5. 实现要点

1. 建立最小诊断桥：
   - 设计一个受控 pywebview API，用于接收已白名单化的前端性能事件，并提供读取最近一次诊断快照的 API。
   - 在后端验证字段类型、阶段白名单、条数上限、数值范围和敏感字段拒绝规则。
   - 保持诊断数据仅进程内短生命周期；活动切换和应用重启不要求持久保留。
2. 复盘路径至少采集：
   - `fatigue_review_open_start`
   - `fatigue_review_api_done`
   - `fatigue_review_panels_done`
   - `fatigue_review_chart_done`
   - 必要时补 `fatigue_review_visible_resize_done`、`fatigue_review_intro_animation_done`，但必须先说明定义。
3. 后端事件至少关联：
   - `cache_status`
   - `api_elapsed_ms`
   - `curve_resolution`
   - `curve_points_original`
   - `curve_points_returned`
4. 用真实 pywebview 窗口复现：
   - 最近活动至少 1 条；
   - 长活动至少 1 条；
   - 每条分别记录首次进入、同一活动再次进入和显式 full 曲线路径（若 UI 尚无入口，则保持后端只读验证并单独标注）。
5. 在完成报告中按阶段给出实际耗时表和根因排序；若 API 未超标而 chart/panels 超标，再拆下一任务做最小图表渲染优化。

## 6. 验收

必须运行：

```bash
PYTHONPATH=. .venv312/bin/python -m pytest tests/test_response_envelope_contract.py tests/test_personal_sport_data_performance_contract.py -q
.venv312/bin/python -m py_compile main.py
git diff --check
```

人工验收必须能在真实 pywebview 窗口中读取本次复盘的阶段诊断，并确认：

- 3-5 秒等待被拆分为可解释的 API / panels / chart / resize 或其他阶段；
- sampled 默认仍是默认首屏，full 仍按需；
- 复盘事实字段、事件、疲劳带、环境因素和 AI 输入边界未变化；
- 诊断信息不含敏感原始数据；
- 不把一次 cache miss 的耗时误报为 cache hit，或反之。

## 7. 非目标

- 不在没有真实分段数据时直接关闭动画、砍掉图表层、缩减复盘字段或降低数据真实性。
- 不新增数据库物化表、大迁移或长期日志表。
- 不以“更快”为由修改复盘公式、曲线轴、事件/疲劳带位置或 AI 事实输入。

## 8. 后续分流

- 若 `fatigue_review_api_done.roundtrip_ms` 主导：新任务治理 pywebview 序列化、cache miss 或后端构建。
- 若 `fatigue_review_panels_done.panels_ms` 主导：新任务拆分/延迟非首屏面板。
- 若 `fatigue_review_chart_done.chart_ms`、可见性重试或动画主导：新任务优化 ECharts 首次绘制和渐进渲染。
- 若三段均不高但仍体感慢：检查同屏照片、缩略图、主线程长任务和窗口渲染，另立任务处理。
