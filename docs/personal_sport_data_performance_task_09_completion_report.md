---
title: Task 09 Completion Report - 真实 pywebview 复盘首屏可观测性与瓶颈定位
version: v0.1.0
status: Completed with real pywebview miss sample
updated: 2026-07-27
---

# Task 09 Completion Report - 真实 pywebview 复盘首屏可观测性与瓶颈定位

## 1. 背景

用户在真实 pywebview 应用窗口中反馈：进入单次活动复盘仍需等待约 3-5 秒。

Task 08 已证明后端默认 sampled 复盘接口、缓存和 payload 明显收敛，但当时未能自动采集真实 pywebview 窗口中的 API 往返、面板渲染和 ECharts 绘制耗时。因此 Task 09 只补可读取的真实窗口诊断通道，不直接改复盘公式、曲线语义或渲染策略。

## 2. 本次交付

- 曾临时新增受控 pywebview 诊断 API，用于采集真实窗口样本：
  - `record_frontend_performance_events(events)`
  - `get_frontend_performance_trace(activity_id=None)`
- 曾在前端复盘路径新增白名单性能事件上报：
  - `fatigue_review_tab_first_open`
  - `fatigue_review_open_start`
  - `fatigue_review_api_done`
  - `fatigue_review_panels_done`
  - `fatigue_review_chart_done`
- 曾在复盘头部新增 `耗时` 按钮，用于在真实窗口内读取最近一次复盘的阶段耗时。
- 诊断字段仅限阶段名、`activity_id`、相对耗时、API roundtrip、后端 `api_elapsed_ms`、payload bytes、面板/图表耗时、cache status、curve resolution 和曲线点数。
- 后端仅在当前进程内保留最近 64 条诊断事件，单次上报最多 12 条，不写用户数据库，不写长期日志，不进入复盘 snapshot 或 AI 输入。
- 后续清理：真实样本已采集完毕，临时 `耗时` 按钮、前端上报桥和上述两个 pywebview 诊断 API 已移除；Task 10 保留的 `review_backend_profile` 响应诊断字段继续用于后端阶段剖析。

## 3. 隐私与契约

已禁止诊断事件携带未知字段。以下内容不得上报或返回：

- raw points
- full curves
- records / raw records
- 活动标题
- 照片
- 文件路径
- API key / token / Authorization
- 用户隐私配置
- AI 内容

本任务不改变：

- `get_fatigue_review` 的业务返回语义。
- sampled 默认首屏和 full 按需语义。
- 复盘公式、曲线轴、疲劳带、collapse events、环境因素或 AI 输入边界。
- Garmin/COROS 同步、Records Center、schema 大迁移或导入链路。

## 4. 历史采集方式

以下步骤为 Task 09 临时诊断按钮存在时的历史采集方式，当前代码中该按钮和前端桥已移除。

1. 重启 pywebview 应用，确保加载本次代码。
2. 打开“个人运动数据”。
3. 进入任意活动详情。
4. 切换到“复盘”。
5. 等待复盘出现后点击复盘头部的 `耗时` 按钮。
6. 记录弹窗中的：
   - 总计
   - API 往返
   - 后端
   - 面板渲染
   - 图表 setOption
   - 缓存
   - 曲线点数

建议至少采集：

- 最近活动首次进入复盘。
- 同一活动再次进入复盘。
- 长活动首次进入复盘。
- 长活动再次进入复盘。

## 5. 当前结论

代码和契约验证已完成，并已补采真实 pywebview 样本。用户反馈的 3-5 秒等待主要出现在 `cache: miss` 的复盘后端构建和 pywebview/API 往返阶段，不是面板渲染或 ECharts 首次 `setOption` 主导。

真实 pywebview 样本：

| 时间 | 活动 | cache | 总计 | API 往返 | 后端 | 面板渲染 | 图表 setOption | 曲线 |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 2026-07-27 10:34 | 未记录 | hit | 96ms | 28ms | 15.1ms | 5ms | 60ms | 1206 / 3576 |
| 2026-07-27 11:12 | 雅安市 骑行，疑似 `activities.id=1094` | miss | 4783ms | 4748ms | 3745.12ms | 4ms | 29ms | 990 / 2916 |

解释：

- `cache: hit` 时，复盘首屏链路已低于 150ms。
- `cache: miss` 时，后端构建约 3.7s，是主瓶颈。
- `cache: miss` 下 API 往返比后端多约 1.0s，可能来自 pywebview 序列化、线程调度、主线程等待或响应封装传输。
- 面板渲染和 ECharts 同步 `setOption` 均在几十毫秒内，不是当前 3-5 秒体感的主因。

疑似活动 ID 依据：本机只读查询 `activities` 中 2026-07-20 的“雅安市 骑行”候选，`id=1094` 的 `duration_sec=2918`、`dist_km=23.77559`，与截图中 `曲线: 990 / 2916` 和标题时间最接近。该 ID 仅用于后续本机复现基线，不进入用户可见业务语义。

下一步分流规则：

- 若 `API 往返` 主导：优先检查 pywebview 序列化、cache miss、后端构建或同进程竞争。
- 若 `面板渲染` 主导：拆分复盘非首屏面板或延迟低优先级 DOM。
- 若 `图表 setOption` 主导：优化 ECharts 首次绘制、动画、resize 和渐进渲染。
- 若三段都不高但体感仍慢：继续排查同屏照片、缩略图、主线程长任务和窗口渲染。

基于当前真实样本，下一任务应聚焦 `cache: miss` 后端构建剖析和优化，优先拆解：

- `_build_fatigue_review_snapshot(row)` 的阶段耗时。
- 21 天历史趋势查询：`_fetch_efficiency_trend`、`_fetch_durability_trend`、`_fetch_cadence_stability_trend`。
- 历史轨迹 JSON 解析与 request-scoped cache 命中情况。
- `_store_fatigue_review_snapshot_cache` 写入耗时。
- pywebview/API 往返中除后端 `api_elapsed_ms` 之外的约 1 秒开销。

## 6. 验证

已通过：

```bash
PYTHONPATH=. .venv312/bin/python -m pytest tests/test_response_envelope_contract.py tests/test_personal_sport_data_performance_contract.py -q
```

结果：`41 passed in 0.30s`

已通过：

```bash
.venv312/bin/python -m py_compile main.py
jq empty docs/js_api_contract.json
git diff --check
```
