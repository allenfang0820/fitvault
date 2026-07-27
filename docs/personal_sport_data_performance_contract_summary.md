---
title: 个人运动数据性能优化契约摘要
version: v0.1.0
status: Active
type: Contract Summary
updated: 2026-07-24
source:
  - docs/personal_sport_data_performance_optimization_plan.md
  - docs/personal_sport_data_performance_task_list.md
  - docs/js_api_contract.json
  - docs/field_contract_matrix.md
  - docs/脉图运动复盘系统_开发团队交付手册_v1.md
  - docs/运动详情页多运动升级开发交付手册.md
  - docs/fatigue_review_environment_factors_contract_summary.md
---

# 个人运动数据性能优化契约摘要

## 1. 本轮阅读

- 阅读时间：2026-07-27 CST。
- 当前任务：Task 10，复盘 cache miss 后端构建剖析与优化。
- 已阅读：Task 10 提示词、Task 09 完成报告、优化方案中的真实 pywebview 样本、任务清单 Task 09/Task 10 段落、本文既有 API/snapshot/隐私/dirty worktree 边界。后续实现前继续阅读 `get_fatigue_review()`、`_build_fatigue_review_snapshot()`、趋势查询、曲线构建、`docs/js_api_contract.json` 和复盘相关测试。

## 2. 总边界

本轮性能优化只覆盖“个人运动数据”的三条用户路径：活动列表、活动概览、运动复盘。Task 09 曾建立最小、受控、进程内的真实 pywebview 性能诊断桥，并根据真实分段数据定位瓶颈；真实样本采集后，临时 `耗时` 按钮、前端上报桥和 pywebview 诊断 API 已移除。不得在没有证据时直接修改复盘计算或图表策略。

明确非目标：Garmin/COROS 导入和远程同步、AI 质量、LLM prompt、embedding、Records Center 新功能、UI 大改、活动事实字段语义、轨迹原始数据、训练指标含义、真实数据库清理或迁移、打包流程。

## 3. API Envelope 契约

pywebview API 默认遵守统一 envelope：

```json
{ "ok": true, "code": 0, "msg": "ok", "data": {}, "traceId": "<hex12>" }
```

错误响应保留过渡期顶层 `error`，但业务 payload 必须在 `data` 内。性能字段只能作为 `data.api_elapsed_ms`、`data.startup_trace.api_elapsed_ms` 或等价诊断字段加入，不得污染顶层 envelope。

## 4. 活动列表契约

- 入口：`track.html::loadSportHubActivityList()` 调用 `get_activity_list()` 或兼容 `get_activity_list_snapshot()`。
- 后端：`main.py::get_activity_list()` / `get_sport_hub_activity_page()` 通过 `profile_backend.get_activity_list_filtered()` 取数。
- 列表字段必须保留分页、过滤、排序、`activity_types`、`page_sizes`、`records` 等既有语义。
- Task 02 允许将列表改为 SQL 层轻字段分页，要求保持排序、过滤、分页 total 和去重语义稳定。
- 列表查询不得读取 `track_json` / `points_json` 大字段；`has_track` 只能来自 `file_path`、经纬度、处理状态等轻量来源或保守 fallback。

## 5. 活动概览契约

- 入口：`track.html::openActivityDetailModal()` -> `fetchSportHubActivityDetail()` -> `get_activity_detail(activity_id)`。
- `get_activity_detail()` 返回 `data.record`，旧契约继续可用。
- UI 字段必须满足 `UI -> DB -> Resolver -> FIT SDK` 可追溯。
- Task 04 新增 `get_activity_detail_summary(activity_id)`，旧 `get_activity_detail(activity_id)` 保持可用。
- summary API 不读取 `track_json` / `points_json` / `laps_json` / 曲线大字段；首屏只返回必要指标、地区、设备、天气和轻量能力占位。
- summary 记录必须带 `detail_pending=true` 或等价标记，前端不得把 summary 缓存当作完整详情。

## 6. 运动复盘契约

- 入口：`track.html::switchDetailTab('review')` lazy load `openFatigueReview()`。
- `get_fatigue_review(activity_id)` 是复盘页面唯一权威数据源。
- snapshot 顶层白名单包含 `sport_type`、`summary`、`metrics`、`collapse_events`、`fatigue_zones`、`curves`、`context_tags`、`environment_context`、`environment_factors`、`cycling_explanation_signals`、`ai_insight`、`advice`、`disclaimer` 等。
- `curves.distance` 是后端权威距离轴；前端不得从 speed/time/points 重建事实轴。
- 骑行解释信号、疲劳带、事件文案和环境解释均只能消费后端事实，不得从 DOM、ECharts、points、records 或标题补算。
- Task 01 只记录 API roundtrip、后端耗时、payload 字节数、面板渲染和 ECharts 调用耗时，不缓存、不降采样、不改变结论。
- Task 05 允许缓存 `get_fatigue_review(activity_id)` 的后端 snapshot，但缓存 key 必须包含 activity `updated_at` 和 cache/resolver version；缓存不得包含 AI 生成内容，不得改变复盘结论语义。当前实现命中时只补充诊断字段和 `cache_status`，不重新执行 `_build_fatigue_review_snapshot()`。
- Task 06 允许默认返回 sampled 展示曲线并支持显式 full 请求；缓存仍保存完整后端 snapshot，响应层派生 sampled/full。降采样必须保持后端权威距离轴、同轴长度、首尾点、关键极值和事件/疲劳带附近点。
- Task 07 允许增加请求内历史曲线解析缓存；不得改变 7d/21d/42d 历史窗口、趋势公式、basis/version、缺失数据降级或低置信度规则。历史趋势不得读取 sampled 响应曲线。
- Task 08 不改变接口语义，只验收列表、概览、复盘 sampled/full 路径；真实 UI 耗时必须与后端微基准分开记录，无法采集的 UI 项必须作为残余风险说明。
- Task 09 的只读诊断 API 和最小前端事件上报 API 是历史临时通道；诊断只包含阶段名、相对耗时、`activity_id`、roundtrip/backend/render/chart ms、cache 状态、曲线点数和 payload 字节数，且只在进程内有限保留。诊断不得进入复盘 snapshot、AI 输入、用户数据库或长期日志。当前代码已移除该临时前端桥，后端 `review_backend_profile` 响应诊断保留用于 Task 10 级别后端剖析。
- Task 10 只允许剖析和优化 `get_fatigue_review()` 的 `cache: miss` 后端构建与诊断元数据；不得改变复盘事实字段、指标公式、历史窗口、Resolver 口径、曲线轴、疲劳带/事件位置、AI 输入、sampled/full 默认语义或 full 数据真实性。

## 7. 前端零推断与数据真实性

前端允许：渲染后端字段、记录既有启动/控制台性能事件、展示已有空态。

前端禁止：从 DOM、ECharts、截图、活动标题、设备、天气卡、points、records、raw_records、curves 推导新的活动事实、复盘结论、环境压力或骑行事件语义。

降采样、缓存、summary API 等后续任务必须保持原始数据和导出数据真实性；展示优化不得替代 canonical 数据。

## 8. 埋点与日志安全

允许记录：

- `activity_id`
- roundtrip ms
- backend `api_elapsed_ms`
- payload byte count
- records count
- curve point count
- thumbnail point count
- render/ECharts elapsed ms

禁止记录：

- 完整 `points`
- raw records / FIT records
- 全量 curves 内容
- shadow_diff / shadow_diff_json / diff
- API key、Authorization、用户隐私配置
- 真实本地文件内容

## 9. Dirty Worktree 保护

当前 worktree 已有大量未提交修改。每个任务开始前必须运行 `git status --short` 并阅读待修改文件 diff。只能叠加当前任务允许范围内的最小改动，不得 revert、覆盖、格式化或清理无关修改。

## 10. Task 01 边界

允许修改：

- `main.py`
- `track.html`
- `docs/personal_sport_data_performance_optimization_plan.md`
- `docs/personal_sport_data_performance_task_list.md`
- `docs/personal_sport_data_performance_contract_summary.md`
- `scripts/benchmark_personal_sport_data.py`
- 必要时同步 `docs/js_api_contract.json` 和 envelope 测试

禁止修改：`profile_backend.py` SQL、schema/migration 行为、详情 summary API、复盘缓存、曲线降采样、Garmin/COROS 同步、AI prompt、Records Center、打包流程、真实用户数据库迁移。

## 10a. Task 03 schema 迁移契约

- 历史迁移逻辑保留，sentinel miss 时仍可完整执行。
- sentinel 命中只跳过当前版本已完成的建表、补列、seed、兼容性大表 UPDATE 和重复索引。
- sentinel 必须版本化；未来 schema 变化必须通过新 key/version 重新触发迁移。
- 用户首屏路径不得因为重复 schema ensure 同步扫描 `activities` 大表。

## 11. 后续摘要刷新规则

从 Task 02 开始，每个任务开始前必须先阅读本文、任务清单中的当前任务段落，以及当前任务直接相关的代码、测试和契约文件，并更新“最近刷新记录”。

如果执行中遇到重要偏离，必须暂停当前修改，重新全文阅读相关原始契约文档，再继续。

## 12. 重要偏离触发条件

遇到以下任一情况必须回读相关原始契约：

- `docs/js_api_contract.json` 与优化方案、任务清单或本文不一致。
- 当前代码字段名、返回 shape、snapshot 白名单或测试期望与本文不一致。
- 需要新增、删除或重命名 pywebview API。
- 需要改变 `get_activity_list`、`get_activity_detail`、`get_fatigue_review` 的业务字段语义。
- 前端需要从 DOM、ECharts、points、raw records、curves 或标题/设备/天气卡补算事实。
- 埋点需要记录大轨迹、原始 points、raw records、敏感配置或用户隐私数据。
- 为了埋点必须触碰 Garmin/COROS 导入、AI 质量、Records Center、打包或其他非目标链路。
- 测试失败显示合同与实现边界冲突，而不是单纯断言未同步。

## 13. 最近刷新记录

- 刷新时间：2026-07-27 CST
- 当前任务编号：Task 10
- 本轮阅读：Task 10 提示词、Task 09 完成报告、优化方案当前状态、任务清单 Task 09/Task 10 段落、`docs/js_api_contract.json` 的 `get_fatigue_review` 契约、复盘字段/AI/零推断边界、`main.py` 的 `get_fatigue_review()`、`_build_fatigue_review_snapshot()`、cache 读写、历史趋势查询、曲线构建 helpers、`metrics_resolver.py::_fetch_efficiency_baseline()`、性能/envelope/复盘相关测试。
- 是否发现偏离：新增 `review_backend_profile` 响应诊断字段属于 API 返回契约扩展，已同步 `docs/js_api_contract.json` 和聚焦测试。该字段只含阶段耗时和计数，不进入 snapshot cache、AI compact snapshot 或用户数据库大表。
- 是否需要回读原始契约：已完成本任务所需回读；执行中未改变复盘事实字段、指标公式、历史窗口、Resolver 口径、曲线轴、事件/疲劳带、AI 输入或 sampled/full 语义。
- 当前任务执行边界是否变化：不变化。Task 10 仅优化 cache miss 后端构建、历史查询读取范围和后台数值依赖预热；不扩展到 sync/import、AI 质量、Records Center、UI 大改、schema 大迁移或长期性能日志。
- 完成记录：Task 10 已完成。1094 miss API 后端从 Task 09 真实样本约 3745ms、本地 API 基线约 3550ms，降到 654-1154ms；1094 hit 对照约 5.32ms。验证通过 `43` 个性能/envelope 测试、`219` 个复盘相关测试、`py_compile main.py metrics_resolver.py` 和 `jq empty docs/js_api_contract.json`。
- 后续注意：临时 `耗时` 按钮和前端诊断桥已移除；需要重启真实 pywebview 后用新的受控验证方式复测 API 往返总计。若后端已低于 1.5s 但 pywebview 总计仍高，再单独治理序列化/线程调度差值。
