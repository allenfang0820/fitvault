---
title: 脉图运动生涯系统（ACS）开发任务清单
version: v0.2.0
status: Status Reconciled Baseline
source:
  - docs/脉图运动生涯系统（ACS）开发团队交付手册.md
  - docs/acs_*_completion_report.md
updated: 2026-07-09
---

# 脉图运动生涯系统（ACS）开发任务清单

本文档是 ACS 后续每个开发任务的参考基线。本轮已根据完成报告、现有代码、API 契约与测试状态完成回填，避免继续把已闭环基础能力误判为未开始。

每个任务开始前，必须刷新项目契约意识。默认使用首次阅读后形成的项目契约摘要；只有在当前任务、改动文件、测试失败或 review 风险提示需要时，才回到项目契约原文重新阅读。

## 0. 总原则

1. `Activity` 是唯一事实源。
2. `Resolver` 负责识别语义：赛事、PB、首次、里程碑。
3. `ACS` 只负责组织运动生涯结构。
4. 所有 ACS 卡片、赛事、PB、成就、记忆必须能回跳 Activity Detail。
5. 低置信度事件只能进入候选区，不能污染正式时间轴。
6. AI 只能消费 Career Snapshot，不得读取原始 FIT、points、track_json、SQLite schema 或本地文件路径。
7. macOS / Windows 双系统都必须兼容：路径、SQLite、pywebview、中文文件名、中文标题、打包后读写权限和滚动性能。
8. Windows 真机、Windows 打包、macOS 打包产物、真实数据人工验收未执行前，不得标记完成。

## 状态标记说明

- `[x] 代码闭环`：已有实现、契约与自动化测试。
- `[x] 轻量闭环`：满足当前阶段可用，但保留产品增强项。
- `[ ] 未完成`：尚未开发、尚未接真实能力，或仍需人工/真机/打包验证。

---

## Phase 0：架构准备

- [x] 代码闭环：新增一级导航「运动生涯」。
  - 证据：`track.html` 中 `bookmark-tab[data-panel="career"]` 与 `panel-career`。
- [x] 代码闭环：移除当前「个人运动数据 > 荣誉墙 / 运动生涯入口」重复入口。
  - 证据：运动生涯已作为一级导航存在，个人运动数据页不再保留 `data-hub-tab="honors"`、`data-legacy-honor-entry` 或 `switchToCareerFromHonorWall`。
- [x] 代码闭环：新建 ACS 后端模块 `career_backend.py`，避免继续膨胀 `main.py`。
  - 证据：`docs/acs_phase0_01_architecture_baseline_completion_report.md`。
- [x] 代码闭环：新增 ACS API 契约到 `docs/js_api_contract.json`。
- [x] 代码闭环：修复 AI snapshot DB 路径问题，统一使用 `profile_backend.DB_PATH`。
- [x] 代码闭环：建立 ACS 数据表幂等 migration：
  - `career_race_events`
  - `career_pb_records`
  - `career_achievement_events`
  - `career_memory_items`
  - `career_snapshots`
  - `career_event_candidates`
- [x] 代码闭环：确认 ACS 表只保存派生索引和展示元数据，禁止复制完整 Activity 原始事实。

## Phase 1：赛事识别与赛事档案

- [x] 代码闭环：读取 FIT `session.sport_event` 字段，识别 Garmin 原生 race 标记。
- [x] 代码闭环：将 `sport_event == race` 写入 `activities.is_race`。
- [x] 代码闭环：支持用户手动标记/取消赛事。
  - 用户确认优先级高于后续 FIT 自动同步。
  - 活动列表在「时间」与「标题」之间提供独立赛事奖牌列；点亮 `🏅` 表示赛事，灰阶未点亮 `🏅` 表示非赛事。
  - 活动列表奖牌展示以后端输出为准：`activities.is_race` 为真，或存在 active `career_race_events` 且用户未手动否决时，都应点亮 `🏅`。
  - 用户点击奖牌即时切换赛事标记，不弹窗；前端不根据标题 / 距离自行推断赛事，只消费后端判定后的字段。
  - 赛事档案中由 Race Resolver / 标题距离规则自动识别的赛事卡片，应提供「是赛事 / 不是赛事」内联判断按钮；已由用户手动点亮 `🏅` 的赛事卡片不再展示判断按钮。
- [x] 代码闭环：建立 Race Resolver，证据来源包括：
  - FIT `sport_event`
  - 用户确认状态
  - 活动标题
  - 活动距离区间
  - 城市 / 时间仅作展示与弱辅助，不单独触发正式赛事或候选赛事。
- [x] 代码闭环：输出赛事置信度：
  - `high`：FIT 明确 race 或用户确认
  - `medium`：标题强关键词 + 标准距离
  - `low`：只有距离匹配
- [x] 代码闭环：实现赛事候选机制，低置信度不进入正式主时间轴。
- [x] 代码闭环：实现 `get_career_races` API。
- [x] 代码闭环：确保所有 RaceEvent 必须带 `activity_id`。
- [x] 代码闭环：进入 ACS 页面前刷新派生事件，解决历史 Activity 不进入 ACS 派生表的问题。

## Phase 2：PB Engine

- [x] 代码闭环：支持跑步 PB：
  - 5K
  - 10K
  - 半马
  - 全马
- [x] 代码闭环：支持骑行 PB 的基础能力：
  - 最大距离
  - 最大爬升
  - 最快均速视数据质量进入 resolver 输出
- [x] 代码闭环：PB 来源必须是 Activity，不允许用户手填无 Activity 的 PB。
- [x] 代码闭环：记录 improvement：
  - 首次 PB
  - 比上一次提升多少
- [x] 代码闭环：实现 `get_career_pb` API。
- [x] 代码闭环：PB 卡片点击回跳 Activity Detail。

## Phase 3：Achievement Engine

- [x] 代码闭环：建立 V1 成就类型：
  - 首次 5K / 10K / 半马 / 全马
  - 首次骑行 50K / 100K
  - 最长跑步
  - 最长骑行
  - 最大爬升
  - 首次城市
  - 年度里程碑
- [x] 代码闭环：每个成就包含：
  - `activity_id`
  - `achievement_type`
  - `title`
  - `event_date`
  - `score`
  - `confidence`
- [x] 代码闭环：实现 `get_career_achievements` API。
- [x] 代码闭环：成就排序同时考虑代表性分值与时间。

## Phase 4：Career Overview

- [x] 代码闭环：新增「运动生涯」一级页面首屏。
- [x] 代码闭环：实现 `get_career_overview` API。
- [x] 代码闭环：空状态可用；没有赛事也能展示基础生涯。
- [x] 代码闭环：Overview V1 接入基础摘要、最近赛事、最新 PB、代表成就。
- [x] 代码闭环：Overview V2 已完成首屏结构重构：
  - 顶部赛事记忆 Banner。
  - 无赛事照片时使用活动标题艺术字 fallback。
  - 有赛事照片时使用应用受控安全图片引用进入真实照片 Banner 模式。
  - 无赛事但有普通活动时展示「运动记忆」，不伪装成赛事。
  - 无活动时展示稳定空态 Banner。
  - Banner 可回跳 Activity Detail。
  - 跑步 / 骑行 / 徒步步行 / 游泳距离统计。
  - 力量训练总重量仅在 Activity 存在可靠总重量字段时聚合，否则稳定显示待生成。
  - 城市 / 国家足迹、最高海拔、最长单次、最大爬升、活跃年份等统计接入；`best_pb` 数据继续保留供 PB 档案与其他下钻入口使用。
  - 年度结构保留在 Banner 与统计区之后；年度卡片仅在 Overview 展示，覆盖后端返回的全部已有运动年份并按年份倒序排列，标题统一为“{year} 年度”，不展示“高光年 / 赛事年 / 记录年 / 空白年”等阶段评价。
  - 不返回 raw FIT、points、track_json、file_path、storage_ref、本地媒体路径或 SQLite schema。

## Phase 5：Timeline Engine

- [x] 代码闭环：实现年份 × 月份时间轴。
- [x] 代码闭环：支持节点类型：
  - 普通赛事
  - PB
  - 首次 / 里程碑
  - 成就
- [x] 代码闭环：节点通过图标、标签、类型文案区分，不只靠颜色。
- [x] 代码闭环：时间轴支持筛选：
  - 全部
  - 赛事
  - PB
  - 里程碑 / 成就
- [x] 代码闭环：实现 `get_career_timeline` API。
- [x] 轻量闭环：500+ 节点采用按月份分段渲染与渐进展开。
  - 后续真实用户数据达到更高规模时，再评估真正虚拟列表或后端分页。
- [x] 已取消：通用记忆节点不进入主时间轴。

## Phase 6：Memory Gallery

> 2026-07-13 产品决策更新：通用“记忆”写入、故事编辑与停用能力已退役，不再作为现行产品契约。仅保留从赛事 Activity Detail 管理照片、按赛事只读浏览相册，以及 Overview Banner 复用赛事首图的链路；底层 `career_memory_items` 只作为现有赛事照片的内部存储实现。

### 已完成：轻量闭环

- [x] 先做轻量版，不急着做复杂相册。
- [x] 历史轻量记忆能力已退役为内部实现说明：现行产品只保留赛事照片 `photo` 类型安全媒体引用；故事文本、轨迹截图和通用记忆写入不再作为现行产品契约。
- [x] 图片缺失时不能空成一堆占位图；当前只展示文本卡片和 `has_media` 状态。
- [x] 每个 MemoryItem 必须绑定 `activity_id` 或 `race_id`。
- [x] macOS / Windows 路径走应用受控逻辑引用，不把绝对本地路径暴露给 AI；当前 API 不返回 `storage_ref` 或本地路径。

### 后续增强：暂不阻塞 Phase 7

- [x] 代码闭环：单张赛事 Banner 图片选择器与受控复制已完成。
- [x] 代码闭环：Memory Gallery 保持集中只读展示；照片添加入口已回收到赛事 Activity Detail。
- [x] 代码闭环：赛事 Activity Detail 多图相册、最多 5 张、拖拽排序、首图 Banner 规则已完成。
- [x] 代码闭环：赛事照片删除采用软删除，媒体文件物理删除仍不执行。
- [x] 代码闭环：真实缩略图与安全预览渲染已完成；后端仅从应用受控媒体目录转换 `data:image` 预览，前端只消费安全预览字段。
- [ ] 未完成：复杂相册布局和媒体文件物理删除生命周期。
- [ ] 未完成：轨迹截图自动生成。

## Phase 7：AI Career Insight

### 已完成：本地 fallback 闭环

- [x] 轻量闭环：新建 `career_snapshot` 生成器。
- [x] 轻量闭环：Snapshot 只能包含：
  - summary
  - primary_sport
  - PB 摘要
  - major_achievements
  - timeline digest
- [x] 契约同步：旧通用记忆、赛事照片内部存储、媒体引用和本地路径不得进入 Career Snapshot；年度 Year Snapshot 后续使用独立 scope、年份、版本、指纹和 API。
- [x] 轻量闭环：禁止进入 AI / Career Insight 前端展示：
  - 原始 FIT
  - points
  - track_json
  - 本地文件路径
  - SQLite schema
- [x] 轻量闭环：实现 `save_career_snapshot` 后端受控持久化。
- [x] 轻量闭环：实现 `get_latest_career_snapshot` 只读调试 API。
- [x] 轻量闭环：实现 `generate_career_insight` API。
- [x] 轻量闭环：`generate_career_insight` 当前阶段只返回本地 fallback 洞察，不调用 LLM，不调用 `llm_backend`。
- [x] 轻量闭环：Career Insight 前端只读占位渲染已接入「运动生涯」页面。
- [x] 轻量闭环：AI 不可用时页面降级为本地基础统计 / fallback 洞察。
- [x] 轻量闭环：前端不展示 Snapshot 原文、Snapshot JSON 或 debug JSON。

### 后续增强：未完成

- [ ] 未完成：接入真实 AI Career Insight 前，必须新增独立任务与安全审查。
- [ ] 未完成：真实 AI 输入仍必须只来自 Career Snapshot 白名单，不得读取 raw FIT、points、track_json、本地路径或 SQLite schema。
- [ ] 未完成：真实 AI 输出需要独立缓存 / 展示策略，不能污染 canonical 事实表。
- [ ] 未完成：补充真实 AI 的 prompt 契约、失败降级、超时降级与跨平台验证。

## Phase 8：前端页面

- [x] 代码闭环：新增一级导航「运动生涯」。
- [x] 代码闭环：页面基础结构已建立：
  - 总览
  - 时间轴
  - 赛事档案
  - PB
  - AI 总结
  - 足迹入口
- [x] 代码闭环：移除运动生涯二级导航中的「荣誉」标签页。
  - 说明：赛事成绩、PB、里程碑分别在赛事档案、记录中心、时间轴 / 总览中体现；Achievement Engine 与后端 API 保留为底层语义能力，不作为独立二级页直接展示。
- [x] 代码闭环：不再使用当前“照片卡片墙 + coming soon 遮罩”作为 ACS 主形态。
- [x] 代码闭环：卡片保持紧凑、可扫描，不做营销式 landing page。
- [x] 代码闭环：移动端单列布局。
- [x] 代码闭环：PB / 赛事 / 里程碑分区从结构预留升级为只读列表。
- [x] 代码闭环：跨平台视觉代码层约束已补充，包括中文字体 fallback、横向溢出约束、局部错误态。
- [ ] 未完成：Windows 下字体、滚动条、窗口尺寸和 pywebview 渲染差异仍需真机验收。
- [ ] 未完成：完整应用人工视觉验收与截图级验收未执行。

## Phase 9：macOS / Windows 兼容性

- [x] 代码闭环：ACS SQLite migration 与路径兼容性代码层审计。
- [x] 代码闭环：应用受控目录与中文文件名兼容性代码层审计。
- [x] 代码闭环：开发完成前的 ACS 数据边界与前端零推断总审计。
- [x] 代码闭环：macOS 当前工作区代码层轻量验收与开发收口检查。
- [x] 代码闭环：SQLite migration 幂等代码层测试。
- [x] 代码闭环：路径处理使用 `Path` / `os.path` 代码层审计。
- [x] 代码闭环：不暴露本地绝对路径给前端 AI 或 Snapshot 的自动化测试。
- [x] 代码闭环：pywebview API 返回结构保持 `{ok, code, msg, data, traceId}` 的契约测试。
- [ ] Windows 打包后验证：
  - SQLite 可读写
  - FIT 导入后 ACS 可刷新
  - 中文文件名正常
  - 中文标题编辑正常
  - 时间轴滚动不卡
- [ ] Windows 真机验证运动生涯页面：
  - 中文字体与 icon 混排正常
  - 窄窗口无横向溢出
  - pywebview 初始化慢或接口暂不可用时，各 Career 区块只显示局部错误态
  - Overview / Timeline / Archives / Memory / Insight 滚动体验正常
  - 说明：Windows 真机与打包验证已后置，仍未完成。
- [ ] macOS 打包产物验证：
  - 应用受控目录可读写
  - 中文标题、图标渲染正常
  - 深色 UI 对比度正常
  - 打包后 pywebview API 可用

## Phase 10：测试与验收

- [x] 代码闭环：ACS 测试与验收矩阵整理。
  - 证据：`docs/acs_phase10_test_acceptance_matrix.md`。
- [x] 代码闭环：ACS 主回归与契约测试收口。
  - 最近 ACS 主回归：`tests/test_career*.py tests/test_activity_race_flag_api.py tests/test_fit_sport_event_race.py tests/test_fit_sync.py tests/test_track_html_sync_logic.py` 通过。
- [x] 代码闭环：后端单测覆盖：
  - schema migration
  - Race Resolver
  - PB Resolver
  - Achievement Resolver
  - Timeline grouping
  - Snapshot 白名单
- [x] 代码闭环：前端静态测试覆盖：
  - 一级导航存在
  - API 调用存在
  - 卡片回跳 Activity Detail
  - 不从前端计算 PB / 赛事事实
- [x] 代码闭环：集成测试覆盖：
  - FIT `sport_event` 导入到赛事标记
  - 手动赛事标记刷新 ACS 派生数据
  - 主要 ACS API 与前端渲染契约
- [ ] 未完成：真实数据端到端人工验收：
  - 导入真实 FIT 后生成 ACS 派生数据
  - 删除 Activity 后 ACS 不显示孤儿事件
  - 修改活动标题后赛事命名更新
  - Overview / Timeline / Archives / Memory / Insight 真实窗口体验
- [ ] 未完成：模块可关闭或降级的产品级开关尚未独立验收。

---

## 尚未完成的产品闭环

- [x] 代码闭环：`ACS-Next-01` 真实赛事照片上传与 Banner 真实照片模式。
  - 说明：已支持为已确认赛事活动选择一张图片、复制到应用受控目录、保存安全逻辑引用，并让 Overview Banner 在有照片时进入 `mode=photo`。
  - 边界：仅完成单张 Banner 照片闭环；复杂相册、批量管理、缩略图生成、删除生命周期仍未完成。
- [x] 代码闭环：`ACS-Next-02` Memory Gallery 媒体生命周期闭环。
  - 说明：已支持为活动记忆选择单张照片、复制到应用受控目录、保存安全逻辑引用、在记忆列表展示白名单图片，并通过既有停用 API 软停用记忆。
  - 边界：仅完成单张照片新增与软停用闭环；复杂相册、批量管理、真实缩略图生成、媒体文件物理删除、轨迹截图自动生成仍未完成。
- [x] 代码闭环：`ACS-Next-02R` 赛事活动详情页轻量相册重构。
  - 说明：照片添加入口已从 Memory Gallery 移到赛事 Activity Detail 概览页圈速统计下方；当前活动上下文自动绑定 `activity_id`，支持最多 5 张、多选添加、拖拽排序、删除照片，排序第一张作为 Banner。
  - 边界：Memory Gallery 仅集中展示；删除采用软删除，不做媒体物理删除、复杂相册详情页、真实缩略图生成或云同步。
- [x] 代码闭环：`ACS-Next-03`：Race Map / 赛事足迹完整能力。
  - 说明：已新增 `get_career_race_map` 只读 API，从 Race Resolver 生成的 active 赛事与 Activity 安全起点坐标生成赛事足迹；前端足迹页展示筛选、摘要、点位和缺坐标赛事列表，并可点击返回 Activity Detail。
  - 边界：不接入复杂地图引擎，不返回完整路线 points / raw FIT / `points_json` / `track_json` / `file_path` / `storage_ref` / 本地路径；前端不从标题、城市或日期推断坐标。
- [x] 代码闭环：`ACS-Next-04`：媒体缩略图与安全预览闭环。
  - 说明：已统一 Activity Detail 赛事照片、Overview Banner、Memory Gallery 的安全预览生成；后端仅从应用受控媒体目录读取图片并返回 `data:image` 或空字符串，前端只使用白名单预览字段渲染图片。
  - 边界：Memory Gallery 仍只读展示，不恢复上传/手填活动 ID 入口；不做复杂相册、媒体物理删除、云同步、轨迹截图自动生成或 AI 接入。
- [ ] 未完成：真实 AI Career Insight 安全接入。
- [ ] 未完成：macOS 打包产物验证。
- [ ] 未完成：Windows 打包与真机验证。
- [ ] 未完成：真实数据端到端人工验收。

## 后续任务建议顺序

1. `ACS-Next-05`：真实数据端到端人工验收准备与验收清单。
2. `ACS-Next-06`：macOS 打包产物验证。
3. `ACS-Next-07`：Windows 打包与真机验证。
4. `ACS-Next-08`：真实 AI Career Insight 安全接入设计。

## 不得误标完成的事项

- [x] 代码闭环：单张赛事 Banner 图片选择器已完成。
- [x] 真实缩略图与安全预览代码闭环已完成。
- [x] Race Map / 赛事足迹完整能力代码闭环已完成。
- [ ] 真实 AI Career Insight 未完成。
- [ ] Windows 打包后验证未完成。
- [ ] Windows 真机验证运动生涯页面未完成。
- [ ] macOS 打包产物验证未完成。
- [ ] 真实数据端到端人工验收未完成。
