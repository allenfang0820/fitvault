---
title: ACS-Next-06B Timeline 核心浏览体验任务清单
version: v0.1
status: Task Breakdown Draft
created: 2026-07-10
source:
  - docs/acs_next_06b_timeline_design_guidance.md
  - codex://threads/019f45c7-5f42-7941-9ccf-5b89ca2d1cc2
  - docs/acs_phase5_01_timeline_engine_closure_completion_report.md
  - docs/acs_phase5_02_timeline_frontend_light_render_completion_report.md
  - docs/acs_phase5_04_timeline_frontend_filters_completion_report.md
---

# ACS-Next-06B Timeline 核心浏览体验任务清单

本文档用于把 `docs/acs_next_06b_timeline_design_guidance.md` 和时间轴讨论会话沉淀为可执行开发任务。后续实现以指导文件为最终依据；若本文与指导文件、项目契约或 API 契约冲突，以指导文件和项目契约为准。

## 0. 结论摘要

当前 Timeline Phase5 雏形已经具备后端分组、前端轻量渲染、筛选、候选计数和 Activity Detail 回跳，但产品形态偏离 06B 目标：

- 当前仍是按 `year -> month -> node list` 的纵向列表。
- 当前仍返回并渲染 `years[].season` 年度摘要。
- 当前仍把 PB 作为独立 timeline node 和独立筛选项。
- 当前年份筛选是原生 `select`，不是顶部年份胶囊。
- 当前月份内部不是横向日期轴，也没有赛事 / 里程碑双轨。
- 当前里程碑范围仍混杂旧 Achievement V1，例如 PB、首次城市、个人纪录等可能与 06B 取舍不一致。

06B 的目标不是在现有列表上补样式，而是把 Timeline 改成用户按时间回看运动生涯的核心浏览方式：

- 顶部年份胶囊：`全部 / 2026 / 2025 / ...`
- 顶部内容胶囊：`全部 / 赛事 / 里程碑`
- 主体按月份组织。
- 每个月右侧是横向日期轴，日期从左到右落位。
- 月份内固定轨道：第一行赛事，第二行里程碑。
- PB 不再作为独立节点，赛事如果是 PB，只在赛事卡右上角展示皇冠。
- 低置信度候选、普通活动流水、记忆类、年度卡片和高光年不进入主时间轴。

## 1. 必须保留的契约

1. `Activity` 是唯一事实源。
2. `Resolver` 负责赛事、PB、成就、累计、首次等语义判断。
3. `ACS` 只组织派生展示和安全媒体引用，不复制 raw FIT 事实。
4. 前端只渲染后端 Timeline ViewModel，不判断赛事、PB、成就、首次、累计节点。
5. Timeline 只展示后端已确认正式节点，低置信度候选不进入主轴。
6. 每个可点击节点必须能回跳 Activity Detail。
7. 不向前端、AI、Snapshot 或 API 返回 raw FIT、points、track_json、file_path、storage_ref、本地绝对路径或 SQLite schema。
8. Windows 真机、Windows 打包、macOS 打包产物未验证前，不标记打包级完成。

## 2. 会话讨论中已确定的信息

- 参考图方向：按月份组织，顶部保留年份胶囊，默认显示全部，也能切换具体年份。
- 内容筛选：从 `赛事 / 里程碑` 扩展为 `全部 / 赛事 / 里程碑`。
- 同一个月份内使用二维时间轴：横向是当月 1 日到月底，卡片按发生日期落位。
- 同一个月份内第一行是赛事，第二行是里程碑。
- 页面宽度要被充分利用，不能继续把事件堆成普通列表。
- 年度卡片和“高光年”只属于 Overview，不属于 Timeline。
- PB 里程碑不需要了，PB 已经在赛事里表达。
- 赛事 PB 视觉：人生 PB 用较大的金色皇冠，当年 PB 用较大的银色皇冠，皇冠压在赛事卡右上角。
- 皇冠判断必须来自后端字段，例如 `pb_badge_scope: career | season | none`。
- 里程碑只保留三类：成就类、累计节点类、首次类。
- 记忆类暂时不进入 Timeline，避免活动列表和活动详情增加新的规则判断。
- 高海拔 3000m+ / 5000m+ 属于成就类的“高海拔探索成就”，不放进普通首次类。

## 3. 当前实现偏差清单

| 偏差 | 当前位置 | 06B 目标 |
| --- | --- | --- |
| PB 独立节点仍进入 `type=all` | `career_backend.get_career_timeline()` 汇入 `_build_timeline_pb_node()` | PB 不作为独立 Timeline 节点 |
| 筛选仍有 `PB` 按钮 | `track.html` Timeline 筛选区 | 内容筛选只有 `全部 / 赛事 / 里程碑` |
| 年份筛选使用 select | `career-timeline-year-filter` | 年份胶囊按钮，默认 `全部` |
| 运动类型筛选仍在 Timeline 顶部 | `career-timeline-sport-filter` | 06B 核心浏览不需要运动类型筛选；如保留应降级为后置增强 |
| 年度摘要仍附着在 Timeline | `years[].season`、`careerTimelineSeasonSummaryHtml()` | Timeline 不展示年度卡片、高光年或 Season 摘要 |
| 月份内部是纵向节点列表 | `careerTimelineMonthHtml()` + `.career-timeline-node-list` | 月份横向日期轴 + 赛事 / 里程碑双轨 |
| 节点缺少布局字段 | 当前 node 无 `day / track / priority / pb_badge_scope` | 后端 ViewModel 提供安全布局字段 |
| 里程碑来源过宽 | `career_achievement_events` V1 含首次城市、个人纪录等 | 06B 只保留成就类、累计节点类、首次类，并排除 PB / 记忆类 |

---

# 任务清单

## `ACS-Next-06B-00`：冻结 Timeline 06B 契约与偏差基线

优先级：P0  
性质：文档 / 测试基线  
目标文件：

- `docs/acs_next_06b_timeline_design_guidance.md`
- `docs/acs_next_06b_timeline_task_list.md`
- `docs/js_api_contract.json`
- `tests/test_career_timeline_engine_closure.py`
- `tests/test_career_timeline_frontend_render.py`

### 目标

在进入代码迁移前，先把 06B 与旧 Phase5 的差异写成测试和 API 契约约束，防止后续实现继续沿用旧列表形态。

### 必做

- 明确 `get_career_timeline` 的 06B 返回结构草案。
- 标记 `type=pb` 和 PB timeline node 为待移除 / 待兼容项。
- 明确 `years[].season` 不再作为 Timeline 页面展示数据。
- 明确候选事件仍只进入候选提示，不进入正式 `nodes`。
- 明确 Timeline 不接 Memory 节点。

### 验收

- 文档中能直接看到 06B 和 Phase5 的差异。
- 测试文件中新增或更新断言，锁住“PB 不作为主时间轴独立节点”的目标。
- API 契约准备好进入 06B-01 结构迁移。

---

## `ACS-Next-06B-01`：Timeline API ViewModel 结构迁移

优先级：P0  
性质：后端 API / 契约  
目标文件：

- `career_backend.py`
- `docs/js_api_contract.json`
- `tests/test_career_timeline_engine_closure.py`
- `tests/test_career_overview_timeline_races.py`
- `tests/test_career_timeline_pb_nodes.py`
- `tests/test_career_timeline_achievement_nodes.py`

### 目标

把 Timeline 后端返回从旧的 `race / pb / achievement + season` 结构迁移为 06B 的正式浏览 ViewModel。

### 建议 ViewModel

```json
{
  "filters": {
    "year": null,
    "type": "all"
  },
  "available_years": [2026, 2025],
  "years": [
    {
      "year": 2026,
      "months": [
        {
          "year": 2026,
          "month": 6,
          "days_in_month": 30,
          "nodes": []
        }
      ]
    }
  ],
  "candidates_count": 0,
  "status": {
    "schema_ready": true,
    "data_ready": true,
    "message": "运动生涯时间轴已生成"
  }
}
```

单个节点建议：

```json
{
  "id": "timeline-node-xxx",
  "type": "race",
  "subtype": "half_marathon",
  "date": "2026-06-15",
  "year": 2026,
  "month": 6,
  "day": 15,
  "track": "race",
  "title": "青岛半程马拉松",
  "badge": "公路赛",
  "value": "01:22:05",
  "meta": "半程马拉松",
  "pb_badge_scope": "season",
  "priority": 90,
  "detail_link": {
    "activity_id": "123",
    "source": "career_timeline"
  }
}
```

### 必做

- `type` 只支持核心三类：`all / race / milestone`。
- 兼容旧输入 `achievement / achievements` 映射到 `milestone`。
- 旧输入 `pb` 返回稳定空结果，或作为兼容期 deprecated type 明确记录，不进入正式 UI。
- 后端返回 `available_years`，前端不得扫描原始活动推断年份。
- 每个节点补齐 `year / month / day / track / priority`。
- 每个月补齐 `days_in_month`，闰年 2 月要正确。
- 移除 Timeline 对 `years[].season` 的展示依赖；Overview 仍可保留年度结构。
- `detail_link.source` 可继续为 `career`，也可迁移为 `career_timeline`，但必须在 API 契约和测试中一致。

### 禁止

- 禁止返回 PB 独立节点作为正式主时间轴节点。
- 禁止返回 raw FIT、points、track_json、file_path、storage_ref、本地路径或 SQLite schema。
- 禁止把低置信度候选塞进 `years[].months[].nodes`。

### 验收

- `type=all` 返回 `race + milestone`，不返回 `pb`。
- `type=race` 只返回赛事轨道节点。
- `type=milestone` 只返回里程碑轨道节点。
- 每个正式节点都有 `activity_id` 回跳。
- 每个节点都有 `day`，且 `1 <= day <= days_in_month`。
- `available_years` 倒序稳定。
- 旧 Phase5 的 PB node 测试被替换为“PB 折叠为赛事皇冠”的新测试。

---

## `ACS-Next-06B-02`：赛事轨道与 PB 皇冠字段

优先级：P0  
性质：后端 ViewModel / 前端视觉  
目标文件：

- `career_backend.py`
- `track.html`
- `docs/js_api_contract.json`
- `tests/test_career_overview_timeline_races.py`
- `tests/test_career_timeline_frontend_render.py`
- `tests/test_career_timeline_frontend_visual_contract.py`

### 目标

赛事节点成为 Timeline 第一轨道，PB 只以皇冠字段挂在赛事卡片上展示。

### 后端必做

- 为 race node 返回 `pb_badge_scope`：
  - `career`：人生 PB。
  - `season`：当年 PB。
  - `none`：非 PB。
- 同一赛事同时满足人生 PB 和当年 PB 时，优先返回 `career`。
- PB 判断必须来自 PB Resolver / PB 记录 / 后端安全聚合结果，不由前端根据成绩、距离、日期推断。
- race node 需要返回赛事卡片安全展示字段：
  - `title`
  - `date / year / month / day`
  - `badge`
  - `value`
  - `meta`
  - `sport` 或 `sport_label`
  - `detail_link.activity_id`

### 前端必做

- 赛事卡片右上角渲染皇冠：
  - `pb_badge_scope=career`：较大金色皇冠。
  - `pb_badge_scope=season`：较大银色皇冠。
  - `none` 或空：不渲染。
- 皇冠允许轻微压住卡片右上角。
- 皇冠不能只靠颜色表达，必须有 `title` / `aria-label` 或可访问文本标注 `人生 PB` / `当年 PB`。
- 赛事卡片仍能点击回跳 Activity Detail。

### 验收

- 前端代码不读取 PB 记录原始字段来判断皇冠。
- 静态测试能确认 `pb_badge_scope` 是白名单字段。
- 视觉测试能确认存在 career / season 两种皇冠样式。
- `PB` 筛选按钮从 Timeline 顶部消失。

---

## `ACS-Next-06B-03`：里程碑 Resolver MVP

优先级：P1  
性质：后端 Resolver / 数据口径  
目标文件：

- `career_backend.py`
- `tests/test_career_timeline_achievement_nodes.py`
- `tests/test_career_achievement_resolver.py`
- 可新增：`tests/test_career_timeline_milestone_nodes.py`

### 目标

建立 06B 里程碑节点口径，只生成三类正式里程碑：成就类、累计节点类、首次类。

### 里程碑类型

#### 成就类

MVP 启用：

- `regular_training_4_weeks`
- `regular_training_8_weeks`
- `regular_training_12_weeks`
- `high_frequency_training_month`
- `single_elevation_gain_1000m`
- `single_elevation_gain_2000m`
- `first_max_altitude_3000m`
- `first_max_altitude_5000m`
- `multi_sport_2_types`
- `multi_sport_3_types`
- `multi_sport_5_types`
- `year_activity_100`
- `year_running_distance_1000km`
- `year_cycling_distance_3000km`
- `year_elevation_gain_50000m`

#### 累计节点类

MVP 阈值：

- 总活动次数：100 / 200 / 300 / 500 / 1000 次。
- 总里程：500 / 1000 / 2000 / 5000 / 10000 km。
- 跑步累计里程：500 / 1000 / 2000 / 5000 km。
- 骑行累计里程：1000 / 3000 / 5000 / 10000 km。
- 累计爬升：10000 / 50000 / 100000 m。
- 累计运动时长：100 / 300 / 500 / 1000 小时。

#### 首次类

MVP 启用：

- `first_activity`
- `first_sport_activity`
- `first_race`
- `first_running_5k`
- `first_running_10k`
- `first_half_marathon`
- `first_marathon`
- `first_cycling_50k`
- `first_cycling_100k`
- `first_cycling_200k`

### 排除项

- PB 里程碑。
- 记忆类里程碑。
- 普通活动流水。
- 第一次城市。
- 第一次设备。
- 第一次上传照片。
- 第一次写故事。
- 与首次标准距离重复的耐力挑战成就。

### 去重规则

- 同一活动同时触发多个阈值时，默认展示最高优先级节点。
- 同一天多个稳定训练成就达成时，默认展示最高等级，其余可进入后续详情或更多入口。
- 首次 5000m+ 同时覆盖首次 3000m+ 时，Timeline 默认展示 5000m+。
- `first_race + first_half_marathon` 可合并为更强标题，例如 `首次半马赛事`。

### 验收

- `type=milestone` 只返回 `track=milestone`。
- 里程碑节点必须有 `subtype / badge / value / meta / priority / detail_link`。
- 没有 `activity_id` 的全局累计节点不得进入可点击主轴；若进入，后端必须提供达成阈值的 activity_id。
- 旧的 `first_city` 不进入 06B 主时间轴。
- PB 不进入里程碑节点。

---

## `ACS-Next-06B-04`：顶部胶囊筛选与月份横向双轨布局

优先级：P0  
性质：前端产品形态  
目标文件：

- `track.html`
- `tests/test_career_timeline_frontend_render.py`
- `tests/test_career_timeline_frontend_filters.py`
- `tests/test_career_timeline_frontend_visual_contract.py`

### 目标

把 Timeline 页面从纵向节点列表改成 06B 的核心浏览形态。

### 必做

- 顶部年份胶囊：
  - 默认 `全部`。
  - 年份按倒序展示。
  - 年份来源来自 `available_years` 或 Timeline ViewModel 安全字段。
  - 点击年份保留当前内容类型筛选。
- 顶部内容胶囊：
  - `全部`
  - `赛事`
  - `里程碑`
  - 移除 `PB` 胶囊。
- 月份容器：
  - 左侧固定月份标签，例如 `07 JUL`。
  - 右侧横向日期轴区域。
  - 按 `days_in_month` 计算比例，不固定假设 31 天。
- 轨道：
  - 第一行 `race`。
  - 第二行 `milestone`。
  - `type=race` 只显示赛事轨道。
  - `type=milestone` 只显示里程碑轨道。
  - 空轨道默认隐藏。
- 卡片定位：
  - 使用 `left_percent = (day - 1) / max(days_in_month - 1, 1) * 100`。
  - 前端只做布局计算，不做事实判断。
- 窄屏：
  - 可退化为纵向月份列表。
  - 不丢失类型标签、皇冠、日期和 Activity Detail 回跳。

### 建议实现步骤

1. 新增或替换 `careerTimelineYearCapsuleHtml()`。
2. 新增 `careerTimelineContentFilterHtml()` 或复用现有 chip 渲染逻辑。
3. 替换 `careerTimelineMonthHtml()`，从 `node-list` 改为 `month-band + tracks`。
4. 新增 `careerTimelineTrackHtml(month, track)`。
5. 新增 `careerTimelineNodePositionStyle(node, month)`。
6. 删除或停用 `careerTimelineSeasonSummaryHtml()` 在 Timeline 中的调用。
7. 删除或降级 `career-timeline-sport-filter`。

### 验收

- 页面默认展示全部年份 + 全部内容。
- 点击具体年份只展示对应年份月份。
- 点击 `赛事` 只展示赛事轨道。
- 点击 `里程碑` 只展示里程碑轨道。
- 同一个月份内，赛事和里程碑分轨道展示。
- 卡片按日期横向落位。
- 年度摘要 / 高光年 / Season 卡片不出现在 Timeline 页面。

---

## `ACS-Next-06B-05`：卡片避让、更多入口与大数据量渲染

优先级：P1  
性质：前端布局 / 性能  
目标文件：

- `track.html`
- `tests/test_career_timeline_frontend_large_render.py`
- `tests/test_career_timeline_frontend_visual_contract.py`

### 目标

处理同月、同轨、同日或近日期卡片拥挤问题，并保持 500+ 节点下的渲染可用性。

### MVP 策略

- 同一月份同一轨道最多直接展示前若干高优先级节点。
- 低优先级节点进入“更多”入口。
- 同一天事件可聚合成组卡片，点击展开可后置。
- 卡片设置稳定最小 / 最大宽度，不因 hover 或长标题改变轨道高度过多。
- 赛事和高优先级里程碑优先保证可读。

### 必做

- 后端 `priority` 字段参与前端拥挤展示策略。
- 同一轨道近距离卡片至少能错层或进入更多入口。
- 月份展开状态继续保留，但从“展开更多节点列表”改成“显示该月份更多事件”。
- 不为了性能引入原始 activity 扫描或本地事实重算。

### 验收

- 500+ 节点静态渲染测试通过。
- 同一天多个节点不会互相完全遮挡。
- 长标题不会撑破月份容器。
- 更多入口可访问且不会破坏 Activity Detail 回跳。

---

## `ACS-Next-06B-06`：视觉验收与跨平台收口

优先级：P1  
性质：验收 / 回归  
目标文件：

- `tests/test_career_timeline_frontend_visual_contract.py`
- `tests/test_career_phase8_cross_platform_visual_contract.py`
- `docs/acs_phase10_test_acceptance_matrix.md`
- 可新增完成报告：`docs/acs_next_06b_timeline_completion_report.md`

### 目标

确认 Timeline 新形态在桌面宽屏、窄屏、真实 pywebview 环境和静态契约测试中都没有明显破坏。

### 自动化验收

- 后端 Timeline API 单测。
- 前端 Timeline 渲染静态测试。
- 视觉契约测试：
  - 年份胶囊存在。
  - 内容胶囊只有 `全部 / 赛事 / 里程碑`。
  - 没有 PB 筛选按钮。
  - 没有 Season Summary 调用。
  - 有横向月份 band / track / card 定位样式。
  - 有 PB 皇冠样式和可访问标注。
- 安全边界递归测试：
  - 不含 forbidden keys。
  - 不含本地绝对路径。
  - 不含 raw FIT / points / track_json / SQLite schema。

### 人工验收

- 宽屏：月份横向日期轴可读，双轨清楚。
- 窄屏：布局退化后仍可读，不丢失类型与回跳。
- 年份切换：`全部` 与具体年份切换稳定。
- 类型切换：`全部 / 赛事 / 里程碑` 切换稳定。
- 赛事 PB 皇冠：人生 PB / 当年 PB 能区分且不只靠颜色。
- 空状态：无赛事、无里程碑、无数据时文案稳定。

### 完成标记限制

完成代码级闭环后，可以标记 06B 代码完成；但在以下验证未执行前，不得标记打包级完成：

- Windows 真机。
- Windows 打包产物。
- macOS 打包产物。
- 真实用户数据人工浏览。

---

# 推荐执行顺序

1. `ACS-Next-06B-00`：先冻结契约和偏差，避免继续按旧 Phase5 目标开发。
2. `ACS-Next-06B-01`：迁移后端 Timeline ViewModel，去掉正式 PB 节点和 Timeline Season 依赖。
3. `ACS-Next-06B-02`：完成赛事节点 PB 皇冠字段和赛事卡视觉。
4. `ACS-Next-06B-03`：补齐 06B 里程碑 Resolver MVP。
5. `ACS-Next-06B-04`：重做前端为年份胶囊 + 内容胶囊 + 月份横向双轨。
6. `ACS-Next-06B-05`：处理拥挤、更多入口和大数据量。
7. `ACS-Next-06B-06`：做视觉、契约、安全和跨平台收口。

# 第一轮建议最小切片

若需要尽快把页面从偏航拉回设计方向，第一轮建议只做：

1. `06B-01` 的 API 最小迁移：
   - `type=all/race/milestone`
   - PB 不再作为正式节点
   - 节点补 `day/track/priority/pb_badge_scope`
   - 移除 Timeline `season`
2. `06B-02` 的赛事皇冠字段与前端显示。
3. `06B-04` 的前端结构改造：
   - 年份胶囊
   - `全部 / 赛事 / 里程碑`
   - 月份横向双轨

里程碑 Resolver 的完整规则可以在第一轮先用现有 active achievement 经过白名单过滤实现，随后在 `06B-03` 扩展累计节点和首次类。

# 每个任务的通用验收命令

根据实际改动范围选择运行：

```bash
.venv312/bin/python -m pytest tests/test_career_timeline_engine_closure.py -q
.venv312/bin/python -m pytest tests/test_career_overview_timeline_races.py tests/test_career_timeline_achievement_nodes.py tests/test_career_timeline_pb_nodes.py -q
.venv312/bin/python -m pytest tests/test_career_timeline_frontend_render.py tests/test_career_timeline_frontend_filters.py tests/test_career_timeline_frontend_visual_contract.py tests/test_career_timeline_frontend_large_render.py -q
.venv312/bin/python -m pytest tests/test_career_phase8_cross_platform_visual_contract.py tests/test_career_phase9_data_boundary_audit.py -q
.venv312/bin/python -m py_compile career_backend.py main.py profile_backend.py
.venv312/bin/python -m json.tool docs/js_api_contract.json
```

# 结束判定

06B 完成时必须满足：

- Timeline 默认显示全部年份 + 全部内容。
- 年份筛选是胶囊按钮，不是原生 select。
- 内容筛选只有 `全部 / 赛事 / 里程碑`。
- 同月内赛事和里程碑分轨道展示。
- 卡片按日期横向落位。
- PB 只以赛事卡皇冠表达，不作为独立节点重复展示。
- 记忆类暂不进入主时间轴。
- 年度卡片和“高光年”不出现在 Timeline 页面。
- 所有正式节点可回跳 Activity Detail。
- 低置信度候选不进入正式主时间轴。
- 前端不暴露 raw FIT、points、track_json、file_path、storage_ref、本地绝对路径或 SQLite schema。
