---
title: 个人运动数据性能优化方案
version: v0.1.0
status: Planning
type: Engineering Optimization Plan
updated: 2026-07-23
scope: 个人运动数据活动列表、活动概览、运动复盘首屏性能
source:
  - 2026-07-23 本机只读测量与 cProfile 结果
  - track.html 当前个人运动数据前端调用路径
  - main.py 当前 pywebview API 实现
  - profile_backend.py 当前活动列表与 schema ensure 实现
---

# 个人运动数据性能优化方案

## 0. 文档用途

本文冻结“个人运动数据”性能优化的真实问题、已观测证据、优化边界、分阶段方案、风险和验收标准。

在任何业务代码修改开始前，实施者必须先阅读本文和对应任务清单：

- `docs/personal_sport_data_performance_task_list.md`
- 当前工作区 `git status --short`
- 待修改文件的现有 diff

当前工作区已有大量未提交修改。本优化不得回退、覆盖或格式化无关改动，不得新开分支，不得新建 worktree。

## 1. 用户可感知问题

用户进入“个人运动数据”后，当前体验存在三段明显等待：

- 加载运动活动列表约 5 秒。
- 进入单个运动概览页约 3 秒。
- 进入运动复盘页约 7 秒。

这些等待都发生在高频交互路径上，且与本机数据量增长强相关。优化目标不是降低数据真实性，而是把重查询、大 JSON、大计算和大图表绘制移出首屏阻塞路径。

## 2. 当前证据与测量数据

### 2.1 数据体量

- 数据库：`/Users/fanglei/.fitvault/user_profile.db` 约 1.4GB。
- active activities 约 989 条。
- `track_json` / `points_json` 各约 747MB。
- `/Users/fanglei/.fitvault/logs/duplicate_check.log` 约 107MB。

### 2.2 活动列表

当前路径：

```text
track.html::loadSportHubActivityList()
  -> window.pywebview.api.get_activity_list(page, pageSize, filterType, titleKeyword)
  -> main.py::get_activity_list()
  -> profile_backend.get_activity_list_filtered()
```

相关实现：

- `track.html::loadSportHubActivityList()` 约 17040 行。
- `main.py::get_activity_list()` 约 13917 行。
- `main.py::get_sport_hub_activity_page()` 约 14000 行。
- `profile_backend.py::get_activity_list_filtered()` 约 2193 行。

已观测瓶颈：

- `get_activity_list_filtered()` 名义上分页，但 SQL 先 SELECT 全部匹配活动，再 Python `_dedupe_activity_list_rows()` 后切片。
- SELECT 字段中使用 `CASE WHEN TRIM(COALESCE(NULLIF(track_json,''), NULLIF(points_json,''), '')) ... THEN 1` 计算 `has_track`，会触碰大轨迹 JSON。
- 只读微基准：当前全量列表 SQL 首次约 3681ms，热态约 350-400ms。
- 去掉 `track_json/points_json` 的 `has_track` 判断后，全量约 230-250ms。
- 真正 `LIMIT 10` 的轻字段查询约 3-4ms。
- 直接调用 API：`get_sport_hub_activity_page(1,10,'all','')` 首次约 2937-4394ms，热态约 405ms。
- 直接调用 API：`get_activity_list(1,20,'all','')` 热态约 386-432ms。
- cProfile 显示列表首调 4.394s 中约 3.79s 花在 `profile_backend._ensure_schema_initialized()` / `_init_schema()` / `ensure_device_product_mapping_seed()`。

### 2.3 活动概览

当前路径：

```text
track.html::openActivityDetailModal()
  -> fetchSportHubActivityDetail()
  -> window.pywebview.api.get_activity_detail(activityId)
  -> main.py::_fetch_activity_row()
  -> main.py::_build_record_from_row()
```

相关实现：

- `track.html::openActivityDetailModal()` 约 19519 行。
- `track.html::fetchSportHubActivityDetail()` 约 18047 行。
- `main.py::get_activity_detail()` 约 14049 行。
- `main.py::_fetch_activity_row()` 约 12045 行。
- `DETAIL_API_REQUIRED_COLUMNS` 约 849 行，包含 `track_json`、`points_json`。
- `main.py::_build_record_from_row()` 约 16051 行会立即 `json.loads(track_json/points_json)` 并生成缩略图、laps、capabilities 等。

已观测瓶颈：

- `_fetch_activity_row()` 会调用 `ensure_activity_sync_schema()`，冷路径可能阻塞详情首屏。
- 当前详情查询取 `DETAIL_API_REQUIRED_COLUMNS` + `COALESCE(track_json, points_json) AS merged_track_json`。
- 最近活动单条轨迹约 0.65-1.3MB，最大活动约 9.3MB。
- 直接调用 API：最近活动 `get_activity_detail` 首次约 1247ms，热态约 9-17ms。
- 长轨迹活动热态约 40-50ms，但首次触发 schema ensure 可到 1.6-2.7s。
- 详情 payload 约 48KB，不是主要传输瓶颈。
- 用户侧 3 秒更可能来自 schema ensure 冷路径、pywebview 往返、前端渲染、照片请求和轨迹缩略图组合。

### 2.4 运动复盘

当前路径：

```text
track.html::switchDetailTab('review')
  -> openFatigueReview()
  -> window.pywebview.api.get_fatigue_review(activityId)
  -> main.py::_fetch_activity_row()
  -> main.py::_build_fatigue_review_snapshot()
  -> 前端同步渲染多个面板和 ECharts
```

相关实现：

- `track.html::switchDetailTab('review')` 约 19591 行。
- `track.html::openFatigueReview()` 约 24387 行。
- `main.py::get_fatigue_review()` 约 14194 行。
- `main.py::_build_fatigue_review_snapshot()` 约 15030 行。

已观测瓶颈：

- 复盘热态 cProfile：`get_fatigue_review` 约 1.355s，其中 `_build_fatigue_review_snapshot` 约 1.352s。
- 19 次 SQLite 查询约 0.847s。
- `_fetch_cadence_stability_trend` 约 0.721s。
- `_fetch_durability_trend` 约 0.359s。
- 历史曲线 JSON 解析约 0.11s。
- 复盘冷态 cProfile：`get_fatigue_review` 约 6.5s。
- 冷态 `_fetch_activity_row` / `ensure_activity_sync_schema` 约 3.85s。
- 冷态 `_build_fatigue_review_snapshot` 约 2.675s。
- gap_calculator/numpy/scipy 首次 import/计算约 1s。
- 长活动复盘 payload 约 3.1-3.25MB。
- 曲线点数约 24,000-26,000，返回 distance/time/hr/speed/gap/grade/terrain_load/altitude/power/cadence 等多条曲线，以及多条等长 `display_curves`。
- pywebview 序列化和 ECharts 绘制会继续放大用户侧等待。

## 3. 瓶颈分类

### 3.1 冷启动 schema ensure

`profile_backend._conn()` 每次会先 `_ensure_schema_initialized()`；首次 `_init_schema()` 包含 `ensure_device_product_mapping_seed()`。

`main.py::ensure_activity_sync_schema()` 约 4582 行挂在列表、详情、复盘路径上，内部包含多条兼容性迁移与修复，例如：

- `UPDATE activities SET track_json = COALESCE(NULLIF(track_json,''), points_json) WHERE track_json IS NULL OR track_json=''`
- 标题修复。
- region 修复。
- processing/weather 兼容修复。
- indexes 创建或补齐。

这些迁移不应同步挂在用户首次点击列表、详情、复盘的首屏路径上。

### 3.2 SQL 全量扫描与 Python 分页

活动列表当前先 SELECT 全量匹配记录，再由 Python 去重和分页。随着活动数、轨迹 JSON 和派生字段增长，首屏列表成本会被全量数据拖累。

### 3.3 大 JSON 字段触碰

列表路径只需要轻字段，却为了 `has_track` 触碰 `track_json/points_json`。详情和复盘路径也在首屏直接读取并解析轨迹大 JSON。

### 3.4 复盘计算

复盘构建 Resolver 快照、曲线、趋势、环境、summary、collapse events。热态后端仍约 1.35s，说明即使绕过冷启动，复盘首屏仍需要计算缓存和查询收敛。

### 3.5 大 payload

长活动复盘一次返回约 3.1-3.25MB，且包含多条 24,000-26,000 点等长曲线。这个规模会放大 pywebview 序列化、JS 解析和 ECharts 绘制成本。

### 3.6 前端渲染

当前缺少足够细的 `performance.now()` 分段埋点，无法精确区分 API roundtrip、后端耗时、DOM 渲染、照片请求和 ECharts 绘制成本。

## 4. 优化原则

1. 先测量，再优化。每个阶段必须留下冷态、热态、payload 大小和 UI 分段耗时证据。
2. 分阶段收敛。先处理活动列表和冷路径这种确定性高的瓶颈，再处理详情拆分和复盘缓存。
3. 保持 API 契约。公开 envelope、字段含义和真实运动数据不得因性能优化缩水。
4. 首屏轻量，重数据延迟。列表、概览、复盘首屏只取完成首屏所需数据，曲线、laps、照片、全量轨迹按需加载。
5. 不降低数据真实性。降采样只用于展示首屏，不替代原始数据、导出数据或后续分析数据。
6. 缓存必须可失效。复盘快照缓存需要绑定 `activity_id + updated_at + resolver_version` 或等效 fingerprint。
7. 保护 dirty worktree。每个任务开始前检查 diff，只修改任务列出的文件。

## 5. 分阶段方案

### 5.1 阶段一：测量基线与列表轻量化

目标：

- 补齐 API 与前端分段埋点。
- 让活动列表首屏使用真正 SQL 分页和轻字段查询。
- 列表路径不再读取 `track_json/points_json`。

预期收益：

- 列表首屏从约 5 秒降到 800ms 以内。
- 热态列表从约 400ms 降到 150ms 以内。

### 5.2 阶段二：冷路径 schema ensure 治理

目标：

- 将昂贵 ensure 从用户动作路径移走。
- 引入 schema version/sentinel，只在版本变化时执行迁移。
- 启动后台预热，不阻塞列表、详情、复盘首屏。

预期收益：

- 消除列表、详情、复盘首次点击时 2-4 秒级迁移阻塞。
- 冷态耗时接近热态路径加真实业务计算。

### 5.3 阶段三：活动概览轻量首屏

目标：

- 拆出 `get_activity_detail_summary` 或在现有 API 中引入明确轻量 mode。
- 首屏只返回标题、时间、地点、关键指标、设备、运动类型、轻量能力标记和约 60 点缩略图。
- laps、照片、全量轨迹、重型 capabilities 延迟加载或复用缓存。

预期收益：

- 活动概览首屏从约 3 秒降到 800ms 以内。
- 热态概览保持 200ms 以内。

### 5.4 阶段四：复盘缓存与曲线瘦身

目标：

- 按 `activity_id + updated_at + resolver_version` 缓存复盘快照。
- 默认返回降采样曲线，例如 800-1500 点。
- 全量曲线只在放大、导出或精细分析时按需请求。
- 合并或缓存历史趋势查询，减少多次 SQLite 查询和历史 JSON 解析。

预期收益：

- 复盘首屏从约 7 秒降到 1.5 秒以内。
- 缓存命中时后端接近轻量读取和序列化成本。
- 完整曲线、AI 和高级分析改为渐进加载。

## 6. 非目标

本次优化第一轮明确不处理：

- Garmin/COROS 导入和远程同步逻辑。
- AI 质量、LLM prompt、embedding、向量索引。
- Records Center 新功能或记录中心语义变更。
- 大规模 UI 视觉改版。
- 活动事实字段、轨迹原始数据、训练指标含义变更。
- 历史数据库清理、轨迹 JSON 拆表迁移等高风险存储改造。
- Windows/macOS 打包流程。

## 7. 风险与回滚策略

### 7.1 主要风险

- SQL 分页与去重顺序不一致，导致列表重复、漏项或分页总数不准。
- `has_track` 轻量化后，少数历史活动的轨迹可用性判断与旧逻辑不一致。
- schema ensure 异步化后，旧数据库首次打开时可能出现字段未就绪。
- 详情 summary 拆分后，前端依赖旧 detail payload 的隐性字段。
- 复盘缓存失效不完整，可能展示过期复盘。
- 曲线降采样影响可视分析精度或 tooltip 体验。

### 7.2 回滚策略

- 每个阶段独立提交或至少保持独立 diff，失败时只回滚该阶段文件。
- 列表分页保留旧查询 fallback 开关，便于紧急切回。
- schema ensure 治理先增加 sentinel 和日志，不一次性删除旧迁移。
- 详情 summary 先新增 API 或 mode，保留旧 `get_activity_detail`。
- 复盘缓存先以只读命中方式接入，缓存 miss 继续走旧构建路径。
- 曲线降采样保留全量按需 API，导出和精细分析仍使用原始数据。

## 8. 验收指标

### 8.1 用户路径指标

| 路径 | 当前观测 | 阶段目标 |
| --- | ---: | ---: |
| 活动列表首屏 | 约 5s | < 800ms |
| 活动列表热态 | 约 400ms | < 150ms |
| 活动概览首屏 | 约 3s | < 800ms |
| 活动概览热态 | 约 9-50ms 后端，用户侧约秒级 | < 200ms 用户侧 API + 渲染主段 |
| 复盘首屏 | 约 7s | < 1.5s |
| 复盘完整曲线/AI | 阻塞首屏 | 渐进加载 |

### 8.2 技术指标

- 列表 SQL 首屏不读取 `track_json/points_json`。
- 列表 SQL 使用 LIMIT/OFFSET 或 keyset pagination，不再 Python 全量切片。
- 用户动作路径不触发大表 UPDATE 或全量 schema 修复。
- 复盘缓存命中时不重复执行历史趋势重查询。
- 默认复盘曲线 payload 控制在可交互范围内，长活动不再一次返回 3MB 以上曲线。
- 前端日志能分辨 API roundtrip、后端 `api_elapsed_ms`、DOM 渲染、ECharts 绘制。

## 9. 建议测试与测量命令

规划阶段必须先运行：

```bash
git status --short
```

实施阶段建议按任务选择运行：

```bash
PYTHONPATH=. .venv312/bin/python -m pytest tests/test_fit_sync.py -q
PYTHONPATH=. .venv312/bin/python -m pytest tests/test_response_envelope_contract.py -q
.venv312/bin/python -m py_compile main.py profile_backend.py metrics_resolver.py
git diff --check
```

建议新增或临时执行 API 微基准，覆盖：

```text
get_sport_hub_activity_page(1, 10, 'all', '')
get_activity_list(1, 20, 'all', '')
get_activity_detail(activity_id)
get_fatigue_review(activity_id)
```

每次优化后至少记录：

- 冷态首次耗时。
- 热态连续 3 次耗时。
- 后端 `api_elapsed_ms`。
- pywebview roundtrip。
- payload 字节数。
- 前端渲染和 ECharts 耗时。

## 10. 当前状态

截至 Task 08 完成时，本轮已完成契约摘要、诊断埋点、活动列表轻量 SQL 分页、schema 冷路径治理、活动概览 summary 首屏、复盘快照缓存、复盘默认曲线降采样、按需 full 曲线、复盘历史曲线解析请求内缓存，以及最终后端回归验证和完成报告。

Task 08 自动验证结论：列表、概览 summary/full detail、复盘 sampled/full 的后端 API 耗时与 payload 均达到或明显优于本方案目标；聚焦测试、编译检查和 `git diff --check` 已通过。真实 pywebview UI 分段耗时在当前 Codex 环境未能自动采集，原因是 pywebview console 未暴露给终端，且 Codex in-app browser 的本地 `file://` 探针被安全策略拦截；该缺口已记录在完成报告中。

Task 09 曾补齐真实 pywebview 窗口可读取的最小性能诊断通道：前端复盘路径上报白名单阶段事件，后端仅进程内保存最近 64 条，复盘头部 `耗时` 按钮可展示总计、API 往返、后端、面板渲染、图表 setOption、缓存状态和曲线点数。真实样本采集完成后，该临时按钮、前端上报桥和 pywebview 诊断 API 已移除；后续复测优先使用后端 `review_backend_profile`、API 微基准或新的受控验证方式。

Task 09 真实 pywebview 补采结果：

- `cache: hit` 样本：总计 96ms，API 往返 28ms，后端 15.1ms，面板 5ms，图表 setOption 60ms，曲线 1206 / 3576。
- `cache: miss` 样本：总计 4783ms，API 往返 4748ms，后端 3745.12ms，面板 4ms，图表 setOption 29ms，曲线 990 / 2916。

据此，3-5 秒体感主要来自复盘 `cache: miss` 后端构建和 pywebview/API 往返，而不是复盘面板 DOM 或 ECharts 同步首绘。下一阶段应先剖析并治理 `_build_fatigue_review_snapshot(row)`、21 天历史趋势查询、历史曲线 JSON 解析、snapshot cache 写入，以及后端 `api_elapsed_ms` 之外约 1 秒的桥接/调度开销。

Task 10 已完成复盘 `cache: miss` 后端构建剖析与优化：

- 新增 `review_backend_profile` 响应诊断字段，仅包含阶段耗时和计数，不进入 snapshot cache 或 AI 输入。
- 历史趋势查询从“先读大范围历史大 JSON 再过滤”调整为“先读时间/派生轻字段并做 Python 权威窗口过滤，再只为窗口内候选批量读取 canonical JSON”。
- `efficiency` / `training_load` / `load_ratio` 等轻字段历史查询增加粗 SQL 时间窗，最终语义仍由 Python 时间解析决定。
- pywebview 前端 ready 后后台预热 GAP 的 numpy/scipy 数值依赖，降低首次复盘点击路径的 import 成本。
- 1094 miss API 后端从 Task 09 真实样本约 3745ms、本地 API 基线约 3550ms，降到 654-1154ms；1094 hit 对照约 5.32ms。

后续真实 pywebview 仍需复测用户体感，确认 API 往返总计是否同步降到 <2s；若仍有约 1 秒差值，再单独治理 pywebview 序列化/线程调度。当前不要恢复临时 `耗时` 按钮，除非先落盘新的受控验证任务。

Task 01 微基准命令：

```bash
.venv312/bin/python scripts/benchmark_personal_sport_data.py --warm-runs 3
```

本机实测样本：

| API | 样本 | Run 1 | Run 2 | Run 3 | Payload |
| --- | --- | ---: | ---: | ---: | ---: |
| `get_sport_hub_activity_page(1,10,'all','')` | page 1 / 10 | 443.72ms | 391.12ms | 389.82ms | 15,991-15,992 bytes |
| `get_activity_list(1,20,'all','')` | page 1 / 20 | 382.03ms | 388.22ms | 387.18ms | 32,227-32,229 bytes |
| `get_activity_detail(1096)` | recent activity | 1246.13ms | 19.35ms | 16.52ms | 45,359-45,361 bytes |
| `get_fatigue_review(127)` | long activity | 963.07ms | 403.40ms | 383.13ms | 2,671,801-2,671,802 bytes |

备注：本次微基准在同一 Python 进程中连续调用，属于 Task 01 基线，不代表 UI 端 pywebview、DOM 和 ECharts 完整用户体感。前端分段埋点已补齐，后续需要在真实 UI 路径中采集 roundtrip、面板渲染和 ECharts 耗时。

Task 02 完成后实测样本：

| API | 样本 | Run 1 | Run 2 | Run 3 | Payload |
| --- | --- | ---: | ---: | ---: | ---: |
| `get_sport_hub_activity_page(1,10,'all','')` | page 1 / 10 | 10.42ms | 7.38ms | 7.97ms | 15,988-15,990 bytes |
| `get_activity_list(1,20,'all','')` | page 1 / 20 | 10.07ms | 9.95ms | 9.90ms | 32,223 bytes |
| `get_activity_detail(1096)` | recent activity | 1006.71ms | 15.10ms | 14.38ms | 45,359-45,361 bytes |
| `get_fatigue_review(127)` | long activity | 831.89ms | 349.23ms | 348.73ms | 2,671,802 bytes |

Task 02 备注：列表 profile 层查询热态约 4-5ms；应用 API 热态约 7-10ms。列表 SQL 已不读取 `track_json` / `points_json`。后续冷态 schema ensure 仍按 Task 03 单独治理。

Task 03 完成后双 fresh process 实测样本：

第一轮用于写入/确认 sentinel：

| API | Run 1 | Run 2 | Run 3 | Payload |
| --- | ---: | ---: | ---: | ---: |
| `get_sport_hub_activity_page(1,10,'all','')` | 11.30ms | 7.49ms | 8.51ms | 15,988-15,990 bytes |
| `get_activity_list(1,20,'all','')` | 10.20ms | 10.01ms | 10.11ms | 32,223-32,225 bytes |
| `get_activity_detail(1096)` | 1009.56ms | 14.66ms | 14.01ms | 45,359-45,361 bytes |
| `get_fatigue_review(127)` | 926.45ms | 352.37ms | 339.17ms | 2,671,801-2,671,802 bytes |

第二轮代表 sentinel 命中后的跨进程冷路径：

| API | Run 1 | Run 2 | Run 3 | Payload |
| --- | ---: | ---: | ---: | ---: |
| `get_sport_hub_activity_page(1,10,'all','')` | 8.83ms | 7.61ms | 7.87ms | 15,987 bytes |
| `get_activity_list(1,20,'all','')` | 10.30ms | 10.21ms | 10.32ms | 32,224 bytes |
| `get_activity_detail(1096)` | 15.25ms | 14.57ms | 15.38ms | 45,359 bytes |
| `get_fatigue_review(127)` | 693.35ms | 343.06ms | 338.81ms | 2,671,802 bytes |

Task 03 备注：schema ensure 冷路径已从列表和详情首调中移除；复盘首调仍有 resolver/import/计算侧成本，不再主要表现为 schema ensure 阻塞，后续由 Task 05-07 继续治理。

Task 04 完成后活动概览 summary 实测样本：

| API | Run 1 | Run 2 | Run 3 | Payload | 标记 |
| --- | ---: | ---: | ---: | ---: | --- |
| `get_activity_detail_summary(1096)` | 16.54ms | 1.23ms | 0.97ms | 2,859-2,860 bytes | `detail_pending=true` |
| `get_activity_detail(1096)` | 14.54ms | 13.88ms | 13.97ms | 49,347 bytes | `detail_pending=false` |

Task 04 备注：summary API 首屏不读取轨迹、点、圈速或曲线大字段；前端先渲染 summary，再渐进加载旧完整详情补全轨迹缩略图、laps 和照片。完整详情 API 契约保留。

Task 05 完成后复盘缓存实测样本：

| API | Run 1 | Run 2 | Run 3 | Payload | 标记 |
| --- | ---: | ---: | ---: | ---: | --- |
| `get_fatigue_review(127)` | 1713.20ms | 30.58ms | 30.89ms | 2,671,822-2,671,825 bytes | Run 1 miss, Run 2-3 hit |

直接 API 命中确认：

| API | Run 1 | Run 2 | Payload | 标记 |
| --- | ---: | ---: | ---: | --- |
| `get_fatigue_review(127)` | 52.94ms | 36.81ms | 2,671,822 bytes | `cache_status=hit` |

Task 05 备注：缓存 key 包含 activity `updated_at` 与 cache/metrics version，命中后不执行 `_build_fatigue_review_snapshot()`，因此避开 Resolver 快照、历史趋势查询和曲线解析。缓存 payload 仍保留当前完整 curves；payload 与 ECharts 绘制压力由 Task 06 单独治理。

Task 06 完成后复盘 sampled/full 实测样本：

| API | Run 1 | Run 2 | Run 3 | Payload | 曲线点数 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `get_fatigue_review(127)` 默认 sampled | 89.71ms | 72.74ms | 71.29ms | 130,932 bytes | 26,052 -> 1,207 |

显式分辨率对比：

| API | Elapsed | Backend | Payload | cache_status | curve_resolution | 曲线点数 |
| --- | ---: | ---: | ---: | --- | --- | ---: |
| `get_fatigue_review(127, 'sampled')` | 76.77ms | 35.27ms | 130,932 bytes | hit | sampled | 26,052 -> 1,207 |
| `get_fatigue_review(127, 'full')` | 31.44ms | 30.73ms | 2,671,972 bytes | hit | full | 26,052 -> 26,052 |

Task 06 备注：默认首屏 payload 从约 2.67MB 降到约 131KB，缓存仍存 full snapshot；`full` 通过显式参数按需返回，供放大、导出或精细分析使用。ECharts setOption 的真实 UI 耗时仍需 Task 08 在应用内采集。

Task 07 完成后历史趋势解析缓存实测样本：

直接构建 full snapshot，不走 API snapshot cache：

| Target | Run 1 | Run 2 | Run 3 | 曲线点数 |
| --- | ---: | ---: | ---: | ---: |
| `_build_fatigue_review_snapshot(row=127)` | 1091.38ms | 347.48ms | 356.01ms | 26,052 |

常规 sampled API：

| API | Run 1 | Run 2 | Run 3 | Payload |
| --- | ---: | ---: | ---: | ---: |
| `get_fatigue_review(127)` 默认 sampled | 82.74ms | 72.15ms | 70.93ms | 130,931-130,932 bytes |

Task 07 备注：本阶段未新增物化表，避免 schema/失效规则风险；仅在 cache miss 的单次构建内复用历史 raw JSON 解析结果。若后续仍需压低 miss 构建时间，可在新的契约冻结后评估合并 SQL 或趋势物化表。

Task 08 完成后实测样本：

| API | Run 1 | Run 2 | Run 3 | Payload | 备注 |
| --- | ---: | ---: | ---: | ---: | --- |
| `get_sport_hub_activity_page(1,10,'all','')` | 12.77ms | 8.34ms | 8.10ms | 15,988-15,990 bytes | 列表首屏后端路径 |
| `get_activity_list(1,20,'all','')` | 11.84ms | 11.06ms | 10.83ms | 32,225 bytes | 列表兼容 API |
| `get_activity_detail_summary(1096)` | 20.45ms | 1.46ms | 1.10ms | 3,160-3,161 bytes | `detail_pending=true` |
| `get_activity_detail(1096)` | 16.25ms | 16.13ms | 15.28ms | 45,382 bytes | 旧完整详情契约保留 |
| `get_fatigue_review(127)` 默认 sampled | 78.09ms | 68.65ms | 66.71ms | 130,932 bytes | 默认首屏曲线 |
| `get_fatigue_review(127,'full')` | 26.60ms | 29.18ms | 27.09ms | 3,115,408 bytes | full 按需，26,052 点 |

Task 08 验证已通过：

```bash
PYTHONPATH=. .venv312/bin/python -m pytest tests/test_fit_sync.py tests/test_response_envelope_contract.py tests/test_personal_sport_data_performance_contract.py -q
.venv312/bin/python -m py_compile main.py profile_backend.py metrics_resolver.py
git diff --check
.venv312/bin/python scripts/benchmark_personal_sport_data.py --warm-runs 3
```

完成报告见 `docs/personal_sport_data_performance_completion_report.md`。
