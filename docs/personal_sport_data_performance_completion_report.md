---
title: 个人运动数据性能优化完成报告
version: v0.1.0
status: Completed With UI Follow-up
type: Performance Completion Report
updated: 2026-07-24
source:
  - docs/personal_sport_data_performance_optimization_plan.md
  - docs/personal_sport_data_performance_task_list.md
  - docs/personal_sport_data_performance_contract_summary.md
  - scripts/benchmark_personal_sport_data.py
---

# 个人运动数据性能优化完成报告

## 1. 背景与范围

本轮优化覆盖“个人运动数据”的三条用户可感知路径：

- 活动列表首屏。
- 活动概览首屏。
- 运动复盘 tab 首屏，以及 full 曲线按需路径。

非目标保持不变：不处理 Garmin/COROS 同步性能、AI 质量、Records Center 新功能、打包流程、schema 大迁移或 UI 大改；不改变活动事实字段、复盘公式、分页/去重语义或 API envelope。

## 2. 任务实施摘要

| 任务 | 结果 |
| --- | --- |
| Task 01 性能基线与埋点补齐 | 已补 API/前端分段耗时、payload 统计和只读微基准脚本。 |
| Task 02 活动列表轻量分页修复 | 已改为 SQL 层分页与轻字段查询，列表路径不读取 `track_json` / `points_json`。 |
| Task 03 schema ensure 冷路径治理 | 已用 sentinel/预热治理用户首屏路径上的重复 schema ensure 阻塞。 |
| Task 04 活动概览轻量首屏 | 已新增 `get_activity_detail_summary()`，summary 首屏不读取轨迹、点、laps 或曲线大字段。 |
| Task 05 复盘快照缓存 | 已按 activity `updated_at` 与 cache/resolver version 缓存 full snapshot，命中跳过构建。 |
| Task 06 复盘曲线降采样与按需 full | 默认 sampled 首屏，显式 `full` 保留全量曲线。 |
| Task 07 复盘历史趋势解析缓存 | 已增加请求内历史 raw JSON 解析复用，不改变趋势窗口、公式或 basis/version。 |
| Task 08 最终回归与验收 | 后端契约、编译、diff 和微基准已通过；真实 pywebview UI 分段本环境未能自动采集，列为残余风险。 |

## 3. 优化前后对比

| 路径 | Task 01 基线 | Task 08 实测 | 结论 |
| --- | ---: | ---: | --- |
| 活动列表 `get_sport_hub_activity_page(1,10)` | 443.72ms / 391.12ms / 389.82ms，payload 约 15.99KB | 12.77ms / 8.34ms / 8.10ms，payload 约 15.99KB | 达到首屏 < 800ms、热态 < 150ms 后端目标。 |
| 活动列表 `get_activity_list(1,20)` | 382.03ms / 388.22ms / 387.18ms，payload 约 32.23KB | 11.84ms / 11.06ms / 10.83ms，payload 约 32.23KB | 达到热态目标，分页与轻字段收益明确。 |
| 活动概览 full `get_activity_detail(1096)` | 1246.13ms / 19.35ms / 16.52ms，payload 约 45.36KB | 16.25ms / 16.13ms / 15.28ms，payload 约 45.38KB | schema 冷路径已消除；完整详情仍可用。 |
| 活动概览 summary `get_activity_detail_summary(1096)` | Task 01 无 summary | 20.45ms / 1.46ms / 1.10ms，payload 约 3.16KB | 达到首屏 < 800ms、热态 < 200ms 后端目标。 |
| 复盘默认 `get_fatigue_review(127)` | 963.07ms / 403.40ms / 383.13ms，payload 约 2.67MB | 78.09ms / 68.65ms / 66.71ms，payload 约 130.93KB | 达到首屏 < 1.5s 后端目标，payload 显著下降。 |
| 复盘 explicit `full` | Task 01 默认 full payload 约 2.67MB | 26.60ms / 29.18ms / 27.09ms，payload 约 3.12MB，26,052 点 | full 曲线仍可按需返回，不替代默认 sampled。 |

## 4. 后端微基准明细

命令：

```bash
.venv312/bin/python scripts/benchmark_personal_sport_data.py --warm-runs 3
```

结果：

| API | Run 1 | Run 2 | Run 3 | Payload |
| --- | ---: | ---: | ---: | ---: |
| `get_sport_hub_activity_page(1,10,'all','')` | 12.77ms | 8.34ms | 8.10ms | 15,988-15,990 bytes |
| `get_activity_list(1,20,'all','')` | 11.84ms | 11.06ms | 10.83ms | 32,225 bytes |
| `get_activity_detail(1096)` | 16.25ms | 16.13ms | 15.28ms | 45,382 bytes |
| `get_fatigue_review(127)` 默认 sampled | 78.09ms | 68.65ms | 66.71ms | 130,932 bytes |

补充只读 API 对比：

| API | Run 1 | Run 2 | Run 3 | Payload | 标记 |
| --- | ---: | ---: | ---: | ---: | --- |
| `get_activity_detail_summary(1096)` | 20.45ms | 1.46ms | 1.10ms | 3,160-3,161 bytes | `detail_pending=true` |
| `get_activity_detail(1096)` | 16.09ms | 16.61ms | 15.57ms | 49,742 bytes | `detail_pending=false`, `thumbnail_points=60` |
| `get_fatigue_review(127,'sampled')` | 134.84ms | 68.53ms | 68.18ms | 152,002-152,003 bytes | `cache_status=hit`, `26052 -> 1207` |
| `get_fatigue_review(127,'full')` | 26.60ms | 29.18ms | 27.09ms | 3,115,408 bytes | `cache_status=hit`, `26052 -> 26052` |

## 5. 真实 UI 分段验收

本轮未能在当前 Codex 环境自动采集真实 pywebview UI 分段耗时：

- pywebview 应用内页面的 `console.debug('[STARTUP]')` 没有从当前终端暴露出可读通道。
- 尝试使用 Codex in-app browser 访问本地 `file://` 页面运行前端探针时，被浏览器 URL 安全策略拦截；已停止，未绕过策略。
- 因此本报告不把后端 API 耗时等同为完整 UI 体感。

前端埋点入口已存在，真实窗口中建议补采以下事件：

| 用户路径 | 必采事件 |
| --- | --- |
| 活动列表首屏 | `activity_list_api_done`, `activity_list_data_done`, `activity_list_render_done` |
| 活动概览首屏 | `activity_detail_summary_api_done`, `activity_detail_summary_render_done`, `activity_detail_api_done`, `activity_detail_render_done` |
| 复盘 tab 首屏 | `fatigue_review_api_done`, `fatigue_review_panels_done`, `fatigue_review_chart_done` |

真实 UI 验收标准仍按原目标执行：列表首屏 < 800ms、概览首屏 < 800ms、复盘首屏 < 1.5s；如 `fatigue_review_chart_done.chart_ms` 仍显著偏高，应拆新任务单独优化 ECharts 渲染与渐进绘制。

## 6. 验证命令与结果

| 命令 | 结果 |
| --- | --- |
| `git status --short` | 已运行；worktree 很脏，未清理、未 revert、未创建分支或 worktree。 |
| `PYTHONPATH=. .venv312/bin/python -m pytest tests/test_fit_sync.py tests/test_response_envelope_contract.py tests/test_personal_sport_data_performance_contract.py -q` | 通过，198 passed, 4 subtests passed。 |
| `.venv312/bin/python -m py_compile main.py profile_backend.py metrics_resolver.py` | 通过，无输出。 |
| `git diff --check` | 通过，无输出。 |
| `.venv312/bin/python scripts/benchmark_personal_sport_data.py --warm-runs 3` | 通过，结果见后端微基准表。 |
| 补充 summary/sampled/full API 对比脚本 | 通过，结果见补充只读 API 对比表。 |

## 7. 残余风险

- 真实 pywebview 窗口中的 DOM 渲染、图片能力、地图/缩略图组合、ECharts `setOption` 仍需手工或可读控制台环境补采。
- 复盘 cache miss 仍可能受 Resolver、历史趋势查询和首次 import/计算影响；Task 07 已降低请求内重复解析，但未新增物化表。
- full 曲线 payload 仍为 MB 级，这是按需路径的真实性成本；默认首屏不得切回 full。
- 当前 worktree 存在大量无关 dirty 文件，本报告只说明本任务验证结果，不代表其他改动可发布。

## 8. 回滚策略

- 活动列表回滚：恢复 `profile_backend.get_activity_list_filtered()` 的旧查询/分页实现，并保留测试用于确认行为差异。
- schema 冷路径回滚：禁用 sentinel 快路径，恢复首次交互同步 ensure；需接受冷启动等待回退。
- 活动概览回滚：前端停止调用 `get_activity_detail_summary()`，回到旧 `get_activity_detail()` 单路径。
- 复盘回滚：禁用 snapshot cache 与 sampled 响应派生，默认返回 full snapshot；需接受 payload 和 ECharts 压力回退。
- 任一回滚都必须重新跑聚焦测试、`py_compile`、`git diff --check` 和微基准。

## 9. 后续建议

1. 在真实 pywebview 应用窗口补采 `reportStartupTimeline('manual')` 输出，记录列表、概览、复盘三段完整用户体感。
2. 若 `fatigue_review_chart_done.chart_ms` 超标，单开任务优化 ECharts 分层渲染、动画策略和渐进绘制。
3. 若复盘 cache miss 仍影响长活动首开，单开任务评估历史趋势 SQL 合并或物化，但需先冻结新 schema/失效契约。
