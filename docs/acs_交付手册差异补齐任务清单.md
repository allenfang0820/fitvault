# ACS 交付手册差异补齐任务清单

版本：v0.1.0  
状态：Product Gap Remediation Baseline  
创建时间：2026-07-08  
来源：
- `docs/脉图运动生涯系统（ACS）开发团队交付手册.md`
- `docs/脉图运动生涯系统（ACS）开发任务清单.md`
- 用户截图反馈：ACS 当前像叠加在「个人运动数据」上的半透明开发态页面，不像独立一级功能

## 0. 当前判断

当前 ACS 不能视为已进入最终验收。

已有实现更接近“工程骨架 + 数据链路 + 测试护栏”的 MVP：

- 已有一级导航入口、基础 API、resolver、Snapshot、Memory 轻量闭环和较多自动化测试。
- 但页面独立性、产品完成度、交付手册定义的长期运动生涯体验仍明显不足。
- 继续编写人工验收清单或进入打包验证前，必须先完成本补齐任务清单中的关键项。

## 1. 总原则

1. `Activity` 仍是唯一事实源。
2. `Resolver` 负责赛事、PB、成就、候选事件等语义识别。
3. `ACS` 负责组织运动生涯结构，不复制 Activity 原始事实。
4. 前端只消费后端 view model，不计算赛事、PB、成就、时间线事实。
5. AI 只消费 Career Snapshot，不读取 raw FIT、points、track_json、SQLite schema、本地绝对路径或 storage_ref。
6. 所有赛事、PB、成就、记忆、地图节点必须可回跳 Activity Detail。
7. Windows 真机、Windows 打包、macOS 打包产物验证仍后置，不得提前勾选完成。

## 2. 优先级定义

| 优先级 | 含义 |
| --- | --- |
| P0 | 阻塞产品形态，必须立即修复 |
| P1 | 交付手册核心功能缺失，必须在验收前补齐 |
| P2 | 产品体验增强，可在核心闭环后推进 |
| P3 | 后置增强或真实 AI / 打包验证相关 |

---

# P0：页面独立性与产品形态修复

## `ACS-GAP-P0-01`：修复「运动生涯」一级页面隔离失败

### 问题

截图显示 ACS 页面像半透明浮层叠在「个人运动数据」页面上，背后运动记录表格、雷达图、个人资料仍可见。

### 目标

切换到「运动生涯」后，必须是完全独立页面：

- `#panel-profile` 不得继续显示在背后。
- `#panel-career` 必须拥有不透底的页面背景。
- `career-shell` 不得依赖半透明遮罩来压暗背后内容。
- 左侧一级导航仍保持当前 App 框架一致。

### 建议实现

- 修复 `.tab-panel` 与 `#panel-profile` CSS 优先级冲突。
- 明确 `#panel-career` 的背景、层级、布局与 overflow。
- 补测试：切换到 career 时 profile panel 不应保持 active / visible。

### 验收

- 肉眼看不到背后的个人运动数据。
- ACS 像一个独立一级功能，而不是 overlay。
- 现有 profile / trace / settings / help / about 切换不受影响。

## `ACS-GAP-P0-02`：将 ACS 页面从“开发态面板”提升为正式功能页面

### 问题

当前区域大量使用“等待数据 / 暂无 / 本地洞察准备中”，叠加半透明视觉后，像早期开发调试面板。

### 目标

建立正式产品态页面骨架：

- 首屏有明确身份感和运动生涯主题。
- 空状态是产品文案，不是调试文案。
- Overview、Timeline、Archive、Memory、Insight 的层级清楚。
- 页面信息密度适合长期浏览，不像临时 dashboard。

### 建议实现

- 重写 Career header、空态、区块标题与状态文案。
- 将“等待数据”类文案改成“尚未形成该类生涯事件”的正式说明。
- 不增加营销 hero，不做落地页；直接呈现可用的生涯工作台。

### 验收

- 即使没有赛事 / PB，也像正式功能的空状态。
- 用户能理解“这是运动生涯系统”，不是一个未完成面板。

---

# P1：交付手册核心功能补齐

## `ACS-GAP-P1-01`：重新审计交付手册 vs 当前实现差异

### 目标

逐项对照交付手册，形成代码现状差异表。

### 必须覆盖

- Career Overview
- Timeline Engine
- Race Archive
- PB Engine
- Achievement Engine
- Memory Gallery
- Race Map
- AI Career Insight
- Season / 年度 / 月度组织
- Resolver 低置信度候选机制
- 性能目标：5000+ Activity、500+ 赛事、10000+ 照片

### 输出

- 新增文档：`docs/acs_delivery_manual_gap_audit.md`
- 每项标记：
  - 已完成
  - 骨架完成
  - 部分完成
  - 未开始
  - 明确后置

## `ACS-GAP-P1-02`：补齐 Career Overview 的“我是谁 / 我走了多久 / 我经历过什么”

### 当前不足

Overview 目前是指标网格，缺少交付手册定义的身份感和生涯叙事。

### 目标

Overview 应回答：

1. 我是谁？
2. 我走了多久？
3. 我经历过什么？

### 功能要求

- 主运动类型 / primary sport。
- 生涯起点。
- 累计活动、赛事、PB、成就、城市、距离。
- 最近赛事。
- 代表成就。
- 关键生涯摘要文案。

### 边界

- 摘要文案可由后端规则生成，不调用真实 AI。
- 前端不根据原始 activity 计算事实。

## `ACS-GAP-P1-03`：补齐 Season / 年度生涯结构

### 当前不足

交付手册核心对象包含 `Season`，当前实现基本没有年度 Season 概念。

### 目标

建立年度生涯结构：

- 年度摘要。
- 年度赛事。
- 年度 PB。
- 年度成就。
- 年度记忆。

### 建议 API

- `get_career_seasons`
- 或在 `get_career_overview` / `get_career_timeline` 中返回年度摘要 view model。

### 验收

- 用户可以按年份理解自己的运动生涯。
- Timeline 不只是节点列表，而是年度组织入口。

## `ACS-GAP-P1-04`：升级 Timeline 为“年份 × 月份 × 生涯事件”的核心浏览方式

### 当前不足

当前 Timeline 更像紧凑节点列表，未充分体现“时间轴优先于列表”的核心体验。

### 目标

- 纵向年份。
- 横向 / 分组月份。
- 节点区分赛事、PB、首次、里程碑、记忆。
- 节点不能只靠颜色区分，必须有图标与标签。
- 低置信度候选不进入主轴。

### 验收

- 时间轴成为 ACS 主浏览方式，而不是附属列表。
- 节点点击可回跳 Activity Detail。

## `ACS-GAP-P1-05`：补齐 Race Archive 的正式赛事档案体验

### 当前不足

当前有轻量只读赛事列表，但未形成“赛事档案”体验。

### 目标

赛事档案至少包含：

- 赛事名称。
- 类型：5K / 10K / 半马 / 全马 / 越野 / 骑行赛事等。
- 日期。
- 城市 / 国家。
- 运动类型。
- 置信度来源。
- 成绩摘要。
- 关联 PB / 成就。
- Activity Detail 回跳。

### 命名优先级

1. FIT Event Name
2. User Metadata
3. Resolver Database
4. Generic Name：年份 + 城市 + 类型

## `ACS-GAP-P1-06`：补齐 PB Engine 范围与 PB 档案体验

### 当前不足

跑步 PB 已有基础能力，骑行 PB 与 PB 档案体验仍不足。

### 目标

跑步：

- 5K
- 10K
- 半马
- 全马

骑行：

- 最大距离
- 最大爬升
- 最快均速
- 功率类 PB 仅在数据质量足够时启用。

### 必须包含

- improvement：首次 PB / 比上一次提升多少。
- PB 来源 activity_id。
- PB 卡片点击回跳 Activity Detail。

## `ACS-GAP-P1-07`：补齐 Achievement Engine 的 V1 分类

### 当前不足

已实现部分首次/代表成就，但交付手册要求的分类更完整。

### 目标分类

- 首次里程碑。
- 性能突破。
- 距离挑战。
- 连续性成就。
- 探索成就。
- 特殊事件。

### V1 具体规则

- 首次 5K / 10K / 半马 / 全马。
- 首次骑行 50K / 100K。
- 最长跑步。
- 最长骑行。
- 最大爬升。
- 首次城市。
- 年度里程碑。

### 验收

- 成就不只按时间排序，也考虑代表性分值。
- 每个成就都有 activity_id、type、title、date、score、confidence。

## `ACS-GAP-P1-08`：补齐低置信度候选事件工作流

### 当前不足

已有 candidate 概念，但用户可见的候选确认 / 拒绝 / 晋级流程不足。

### 目标

- 低置信度赛事 / 成就进入候选区。
- 候选不进入正式主时间轴。
- 用户可确认为赛事 / 非赛事。
- 用户确认后优先级高于后续 resolver 自动判断。

### 边界

- 用户确认写入 Activity 或 ACS 派生表的确认元数据。
- 不修改 FIT 原始文件。

---

# P1：核心页面与交互补齐

## `ACS-GAP-P1-09`：将 Race / PB / Achievement 从右侧小分区升级为可浏览档案区

### 当前不足

赛事、PB、里程碑现在像右侧摘要列表，不像可浏览档案。

### 目标

在 ACS 一级页面内提供清晰档案浏览：

- 可筛选。
- 可排序。
- 可展开。
- 可回跳 Activity。
- 有正式空态。

### 实现方式

可先在同一页面使用 tabs / segmented control，不必立刻拆独立路由。

## `ACS-GAP-P1-10`：补齐 Memory Gallery 的产品体验

### 当前不足

当前 Memory 是轻量文本卡片 + 安全引用，离“记忆相册”还有距离。

### 目标

- 无图也可展示故事。
- 有图时展示缩略图。
- 支持故事、照片、轨迹三类卡片。
- 支持按赛事 / 年份 / 类型浏览。
- 支持回跳 Activity Detail。

### 后置能力

- 真实上传器。
- 文件复制 / 删除生命周期。
- 轨迹截图自动生成。
- 批量管理。

## `ACS-GAP-P1-11`：新增 Race Map / 城市足迹

### 当前不足

交付手册包含 Race Map，当前实现缺失。

### 目标

回答“我跑过 / 骑过哪些城市”：

- 赛事城市分布。
- 运动城市覆盖。
- 城市列表或地图轻量视图。
- 不要求首版做复杂地图，可先做城市足迹列表 / 分布卡片。

### 数据来源

- Race Event。
- Activity 起点城市 / region。
- City Metadata。

---

# P2：AI Career Insight 产品化补齐

## `ACS-GAP-P2-01`：将本地 fallback Insight 升级为正式“生涯洞察准备态”

### 当前不足

当前 Insight 是安全 fallback，但观感接近占位。

### 目标

在不接真实 AI 的前提下，形成正式准备态：

- 已生成哪些安全摘要。
- 后续 AI 将如何使用这些摘要。
- 当前为什么不调用 AI。
- 给用户明确下一步。

## `ACS-GAP-P2-02`：真实 AI Career Insight 接入前安全设计

### 后置原因

真实 AI 需要单独审查，不应混在当前补齐任务中。

### 必须先完成

- Career Snapshot 白名单最终确认。
- Prompt 契约。
- 超时 / 失败 / 离线降级。
- 输出不写 canonical。
- 不污染普通 AI 教练会话。

---

# P2：性能与大数据量

## `ACS-GAP-P2-03`：Timeline 500+ 赛事性能策略

### 目标

- 分段渲染或虚拟列表。
- 月份折叠。
- 大节点数量不卡顿。

## `ACS-GAP-P2-04`：Memory 10000+ 照片懒加载策略

### 目标

- 图片缩略图优先。
- 懒加载。
- 无图状态不阻塞。
- 不读取或暴露本地绝对路径。

---

# P3：验收与打包后置任务

## `ACS-GAP-P3-01`：macOS 打包产物验收

- 应用受控目录可读写。
- 中文标题、中文文件名、图标渲染正常。
- 深色 UI 对比度正常。
- 离线可用。

## `ACS-GAP-P3-02`：Windows 打包产物验收

- SQLite 可读写。
- FIT 导入后 ACS 可刷新。
- 中文文件名正常。
- 中文标题编辑正常。
- 时间轴滚动不卡。
- pywebview 初始化慢时局部错误态正常。

## `ACS-GAP-P3-03`：完整人工验收

- 使用真实数据导入。
- 确认赛事、PB、成就、记忆、时间轴、回跳链路。
- 记录问题与复测结果。

---

# 3. 建议执行顺序

1. `ACS-GAP-P0-01`：修复一级页面隔离失败。
2. `ACS-GAP-P0-02`：把 ACS 页面提升为正式功能页。
3. `ACS-GAP-P1-01`：交付手册 vs 当前实现差异审计。
4. `ACS-GAP-P1-02`：补齐 Overview 生涯叙事。
5. `ACS-GAP-P1-03`：补齐 Season / 年度结构。
6. `ACS-GAP-P1-04`：升级 Timeline 核心浏览体验。
7. `ACS-GAP-P1-05`：补齐 Race Archive。
8. `ACS-GAP-P1-06`：补齐 PB Engine 与档案。
9. `ACS-GAP-P1-07`：补齐 Achievement 分类。
10. `ACS-GAP-P1-08`：补齐候选事件工作流。
11. `ACS-GAP-P1-09`：档案区浏览体验。
12. `ACS-GAP-P1-10`：Memory Gallery 产品体验。
13. `ACS-GAP-P1-11`：Race Map / 城市足迹。
14. `ACS-GAP-P2-01`：Insight 准备态产品化。
15. `ACS-GAP-P2-02`：真实 AI 安全设计。
16. `ACS-GAP-P2-03` / `ACS-GAP-P2-04`：性能策略。
17. `ACS-GAP-P3-*`：打包与人工验收。

## 4. 暂停事项

在完成 P0 与 P1 核心补齐前，暂停以下任务：

- `ACS-Phase10-03` 人工验收清单。
- Windows 真机验证。
- Windows 打包验证。
- macOS 打包产物验收。
- 真实 AI Career Insight 接入。

## 5. 每个后续任务提示词必须包含

1. 任务开始前刷新项目契约意识。
2. 默认使用首次阅读后形成的项目契约摘要；只有当前任务、改动文件、测试失败或 review 风险提示需要时，才回到契约原文阅读。
3. 必须参考：
   - `docs/脉图运动生涯系统（ACS）开发团队交付手册.md`
   - `docs/脉图运动生涯系统（ACS）开发任务清单.md`
   - `docs/acs_交付手册差异补齐任务清单.md`
   - `.trae/rules/fit-arch-contrac.md` 的已形成契约摘要
4. 明确任务边界：
   - 不引入真实 AI，除非任务明确要求。
   - 不执行 Windows / 打包验证，除非进入 P3。
   - 不让前端计算事实。
   - 不暴露 raw FIT、points、track_json、file_path、storage_ref、SQLite schema 或本地绝对路径。

