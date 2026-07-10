---
title: ACS-Next-06B Timeline 工程级提示词与执行记录
version: v0.1
status: In Progress
created: 2026-07-10
source:
  - docs/acs_next_06b_timeline_task_list.md
  - docs/acs_next_06b_timeline_design_guidance.md
---

# ACS-Next-06B Timeline 工程级提示词与执行记录

本文记录每个 06B 子任务可以直接交付给 Codex 的工程级提示词，以及执行后的验证结果和下一个建议任务。任务执行顺序以 `docs/acs_next_06b_timeline_task_list.md` 为准。

## 通用任务前置要求

每个任务开始前，必须刷新项目契约意识。默认使用首次阅读后形成的项目契约摘要；只有在当前任务、改动文件、测试失败或 review 风险提示需要时，才回到项目契约原文重新阅读。

必须持续遵守：

1. `Activity` 是唯一事实源。
2. `Resolver` 负责赛事、PB、成就、累计、首次等语义判断。
3. `ACS` 只组织派生展示和安全媒体引用，不复制 raw FIT 事实。
4. 前端只消费后端 ViewModel，不自行判断赛事、PB、成就、首次、累计或训练事实。
5. 低置信度候选不进入正式 Timeline 主轴。
6. 所有正式节点必须能回跳 Activity Detail。
7. 不向前端、AI、Snapshot 或 API 返回 raw FIT、points、track_json、file_path、storage_ref、本地绝对路径或 SQLite schema。
8. Windows 真机、Windows 打包、macOS 打包产物未验证前，不得标记打包级完成。

---

## ACS-Next-06B-00：冻结 Timeline 06B 契约与偏差基线

### 工程级提示词

```markdown
# ACS-Next-06B-00：冻结 Timeline 06B 契约与偏差基线

## 任务开始前

每个任务开始前，必须刷新项目契约意识。默认使用首次阅读后形成的项目契约摘要；只有在当前任务、改动文件、测试失败或 review 风险提示需要时，才回到项目契约原文重新阅读。

必须确认本任务只做 06B 契约与偏差基线收口，不提前实现 06B-01 的运行时代码迁移。

## Goal

把 `docs/acs_next_06b_timeline_design_guidance.md` 与 `docs/acs_next_06b_timeline_task_list.md` 中的 06B 目标转化为后续 Codex 可执行的基线：明确旧 Phase5 与 06B 的差异，写清 API、前端和测试迁移方向，并为下一个任务 `ACS-Next-06B-01` 提供可直接执行的建议。

## Scope

允许修改：

- `docs/acs_next_06b_timeline_engineering_prompts.md`
- 必要时补充 `docs/acs_next_06b_timeline_task_list.md`

原则上不修改：

- `career_backend.py`
- `track.html`
- `docs/js_api_contract.json`
- 任何测试文件

原因：本任务是冻结契约与偏差基线，运行时 API 和测试迁移放到 `06B-01` 执行，避免在没有实现的情况下先提交失败测试。

## Constraints

- 不删除旧 Phase5 代码。
- 不改变 `get_career_timeline` 当前运行时行为。
- 不改变 pywebview API envelope。
- 不引入新的 Resolver 规则。
- 不为了文档任务修改 unrelated dirty files。
- 文档必须明确：PB 不再作为 06B 正式 Timeline 独立节点；PB 只通过赛事卡皇冠表达。
- 文档必须明确：Timeline 页面不再展示 `years[].season`、年度卡片或“高光年”。
- 文档必须明确：记忆类暂不进入主时间轴。

## Expected Files or Areas

- `docs/acs_next_06b_timeline_engineering_prompts.md`
- `docs/acs_next_06b_timeline_task_list.md`

## Validation Commands or Acceptance Checks

执行：

```bash
test -s docs/acs_next_06b_timeline_engineering_prompts.md
rg -n "ACS-Next-06B-00|每个任务开始前，必须刷新项目契约意识|PB 不再作为|years\\[\\]\\.season|ACS-Next-06B-01" docs/acs_next_06b_timeline_engineering_prompts.md
```

如果修改了 JSON，再执行：

```bash
.venv312/bin/python -m json.tool docs/js_api_contract.json >/dev/null
```

## Completion Definition

- 工程级提示词文档存在。
- `06B-00` 提示词包含 Goal、Scope、Constraints、Expected Files or Areas、Validation Commands or Acceptance Checks、Completion Definition。
- 提示词包含用户要求的项目契约刷新原文。
- 执行记录给出下一个建议任务：`ACS-Next-06B-01：Timeline API ViewModel 结构迁移`。
- 不产生运行时代码改动。
```

### 执行记录

- 状态：已完成
- 验收：`test -s docs/acs_next_06b_timeline_engineering_prompts.md` 通过；`rg` 关键约束检查通过。
- Review gate：仅新增工程提示词文档，未改运行时代码。
- 下一个建议任务：`ACS-Next-06B-01：Timeline API ViewModel 结构迁移`

---

## ACS-Next-06B-01：Timeline API ViewModel 结构迁移

### 工程级提示词

```markdown
# ACS-Next-06B-01：Timeline API ViewModel 结构迁移

## 任务开始前

每个任务开始前，必须刷新项目契约意识。默认使用首次阅读后形成的项目契约摘要；只有在当前任务、改动文件、测试失败或 review 风险提示需要时，才回到项目契约原文重新阅读。

本任务涉及后端公开 API ViewModel、API 契约文档和 Timeline 后端测试，属于共享接口变更。开始前必须确认：

- `Activity` 是唯一事实源。
- Timeline 只组织后端 Resolver 已确认的正式节点。
- PB 不再作为 06B Timeline 独立节点。
- Timeline 不再返回 `years[].season` 供页面展示。
- 低置信度候选只进入 `candidates_count`，不进入正式 `nodes`。
- 不返回 raw FIT、points、track_json、file_path、storage_ref、本地绝对路径或 SQLite schema。

## Goal

把 `get_career_timeline()` 从旧 Phase5 的 `race / pb / achievement + season` ViewModel 迁移为 06B 的正式浏览 ViewModel：

- `type` 核心支持 `all / race / milestone`。
- 旧输入 `achievement / achievements` 映射到 `milestone`。
- 旧输入 `pb` 稳定返回空主时间轴，不再返回 PB 节点。
- `type=all` 只返回 `race + milestone`。
- 每个节点补齐 `year / month / day / track / priority`。
- 每个月补齐 `year / month / days_in_month / nodes`。
- 顶层返回 `available_years`，按倒序展示已有正式节点年份。
- Timeline 年份对象不再包含 `season`。

## Scope

允许修改：

- `career_backend.py`
- `docs/js_api_contract.json`
- `tests/test_career_timeline_engine_closure.py`
- `tests/test_career_overview_timeline_races.py`
- `tests/test_career_timeline_pb_nodes.py`
- `tests/test_career_timeline_achievement_nodes.py`
- `docs/acs_next_06b_timeline_engineering_prompts.md`

不修改：

- `track.html`
- 前端 Timeline 渲染测试
- PB Resolver / Race Resolver / Achievement Resolver 的识别语义
- Overview 年度卡片和 PB 档案 API

## Constraints

- 不删除 `get_career_pb` 或 PB 档案能力。
- 不删除 Overview 中的 `representative_seasons`。
- 不改 pywebview response envelope。
- 不把低置信度 candidate 转成正式节点。
- 不增加 Memory Timeline 节点。
- 不做 06B-02 的 PB 皇冠视觉，只保留 `pb_badge_scope: "none"` 的字段占位，正式判断放到下个任务。
- `detail_link.activity_id` 必须保留。
- 旧 `type=pb` 可以保留在 filters 中作为 deprecated 输入回显，但 `years` 必须为空。

## Expected Files or Areas

- `career_backend.py`
  - `_normalize_timeline_filters`
  - `_build_timeline_race_node`
  - `_build_timeline_achievement_node`
  - `_group_timeline_nodes`
  - `get_career_timeline`
- `docs/js_api_contract.json` 中 `get_career_timeline`
- Timeline 后端相关测试

## Validation Commands or Acceptance Checks

执行：

```bash
.venv312/bin/python -m pytest tests/test_career_timeline_engine_closure.py tests/test_career_overview_timeline_races.py tests/test_career_timeline_achievement_nodes.py tests/test_career_timeline_pb_nodes.py -q
.venv312/bin/python -m py_compile career_backend.py main.py profile_backend.py
.venv312/bin/python -m json.tool docs/js_api_contract.json >/dev/null
```

## Completion Definition

- `type=all` 返回 race + milestone，不返回 pb。
- `type=race` 只返回 `track=race`。
- `type=milestone` 只返回 `track=milestone`。
- `type=achievement / achievements` 映射到 `milestone`。
- `type=pb` 稳定空结果。
- 节点包含 `year / month / day / track / priority / detail_link`。
- 月份包含 `year / month / days_in_month / nodes`。
- 顶层包含 `available_years`。
- Timeline 年份对象不再包含 `season`。
- 测试和 JSON 校验通过。
- 完成后根据任务清单建议进入 `ACS-Next-06B-02：赛事轨道与 PB 皇冠字段`。
```

### 执行记录

- 状态：已完成
- 验收：`.venv312/bin/python -m pytest tests/test_career_timeline_engine_closure.py tests/test_career_overview_timeline_races.py tests/test_career_timeline_achievement_nodes.py tests/test_career_timeline_pb_nodes.py -q` 通过，`28 passed`。
- 验收：`.venv312/bin/python -m py_compile career_backend.py main.py profile_backend.py` 通过。
- 验收：`.venv312/bin/python -m json.tool docs/js_api_contract.json >/dev/null` 通过。
- Review gate：公开 Timeline API 已迁移为 `race/milestone`，PB 不再进入主轴；未删除 PB 档案或 Overview 年度能力。
- 下一个建议任务：`ACS-Next-06B-02：赛事轨道与 PB 皇冠字段`

---

## ACS-Next-06B-02：赛事轨道与 PB 皇冠字段

### 工程级提示词

```markdown
# ACS-Next-06B-02：赛事轨道与 PB 皇冠字段

## 任务开始前

每个任务开始前，必须刷新项目契约意识。默认使用首次阅读后形成的项目契约摘要；只有在当前任务、改动文件、测试失败或 review 风险提示需要时，才回到项目契约原文重新阅读。

本任务涉及后端 Timeline race node 字段和前端可见渲染。必须确认：

- PB 不再作为 Timeline 独立节点。
- PB 皇冠只挂在赛事卡片上。
- 前端不得根据成绩、距离、日期、标题或 DOM 自行判断 PB。
- `pb_badge_scope` 必须来自后端 PB Resolver / PB 记录 / 后端安全聚合。
- 人生 PB 优先级高于当年 PB。

## Goal

为 Timeline 赛事节点补齐 `pb_badge_scope`，并在前端赛事卡片右上角展示大号皇冠：

- `career`：人生 PB，金色皇冠。
- `season`：当年 PB，银色皇冠。
- `none`：非 PB，不显示皇冠。

## Scope

允许修改：

- `career_backend.py`
- `track.html`
- `docs/js_api_contract.json`
- `tests/test_career_overview_timeline_races.py`
- `tests/test_career_timeline_frontend_render.py`
- `tests/test_career_timeline_frontend_visual_contract.py`
- `docs/acs_next_06b_timeline_engineering_prompts.md`

不修改：

- PB Resolver 的成绩判定规则。
- Race Resolver 的赛事判定规则。
- Timeline 横向月份双轨布局，留给 `06B-04`。
- 里程碑 Resolver MVP，留给 `06B-03`。

## Constraints

- 后端只基于 `career_pb_records` 这样的 ACS 派生安全表判断 `pb_badge_scope`。
- `status=active` 的 PB 记录绑定到同一 `activity_id` 时返回 `career`。
- `status=superseded` 的 PB 记录绑定到同一 `activity_id` 时可返回 `season`。
- 同一活动同时满足 career 和 season 时，返回 `career`。
- 前端只白名单消费 `pb_badge_scope`。
- 皇冠必须有 `title` / `aria-label` 或等价可访问文本，不能只靠颜色区分。
- Timeline 顶部不再出现 `PB` 筛选按钮。

## Expected Files or Areas

- `career_backend.py`
  - race node 构造。
  - PB scope 安全聚合 helper。
- `track.html`
  - Timeline normalizer。
  - node card HTML。
  - crown CSS。
  - Timeline filter buttons。
- Frontend / backend Timeline tests。

## Validation Commands or Acceptance Checks

执行：

```bash
.venv312/bin/python -m pytest tests/test_career_overview_timeline_races.py tests/test_career_timeline_frontend_render.py tests/test_career_timeline_frontend_visual_contract.py -q
.venv312/bin/python -m pytest tests/test_career_timeline_engine_closure.py tests/test_career_timeline_achievement_nodes.py tests/test_career_timeline_pb_nodes.py -q
.venv312/bin/python -m py_compile career_backend.py main.py profile_backend.py
.venv312/bin/python -m json.tool docs/js_api_contract.json >/dev/null
```

## Completion Definition

- race node 返回 `pb_badge_scope`。
- active PB 记录对应赛事返回 `career`。
- superseded PB 记录对应赛事返回 `season`。
- 非 PB 赛事返回 `none`。
- 前端渲染 career / season 两种皇冠样式。
- 皇冠有可访问标注。
- 前端不出现 PB 筛选按钮。
- 测试和 JSON 校验通过。
- 完成后根据任务清单建议进入 `ACS-Next-06B-03：里程碑 Resolver MVP`。
```

### 执行记录

- 状态：已完成
- 验收：`.venv312/bin/python -m pytest tests/test_career_overview_timeline_races.py tests/test_career_timeline_frontend_render.py tests/test_career_timeline_frontend_visual_contract.py -q` 通过，`30 passed`。
- 验收：`.venv312/bin/python -m pytest tests/test_career_timeline_engine_closure.py tests/test_career_timeline_achievement_nodes.py tests/test_career_timeline_pb_nodes.py -q` 通过，`19 passed`。
- 验收：`.venv312/bin/python -m py_compile career_backend.py main.py profile_backend.py` 与 `docs/js_api_contract.json` JSON 校验通过。
- Review gate：`pb_badge_scope` 仅由后端 PB 记录聚合产生，前端只渲染 `career/season` 皇冠；PB 筛选入口已移除。
- 下一个建议任务：`ACS-Next-06B-03：里程碑 Resolver MVP`

---

## ACS-Next-06B-03：里程碑 Resolver MVP

### 工程级提示词

```markdown
# ACS-Next-06B-03：里程碑 Resolver MVP

## 任务开始前

每个任务开始前，必须刷新项目契约意识。默认使用首次阅读后形成的项目契约摘要；只有在当前任务、改动文件、测试失败或 review 风险提示需要时，才回到项目契约原文重新阅读。

本任务涉及 Timeline 里程碑语义边界。必须确认：

- Timeline 里程碑只保留成就类、累计节点类、首次类。
- PB 里程碑不进入主时间轴。
- 记忆类暂不进入主时间轴。
- 第一次城市、设备、上传照片、写故事不进入 06B Timeline。
- 前端不参与任何里程碑判断。
- 里程碑必须绑定达成节点的 `activity_id`。

## Goal

为 `get_career_timeline(type=milestone|all)` 建立 06B Timeline Milestone Resolver MVP：

- 过滤旧 Achievement V1 中不属于 06B 的节点。
- 保留或映射标准首次类节点。
- 派生 `first_activity`、`first_sport_activity`、`first_race`。
- 派生成就类中的爬升、高海拔、多运动、年度坚持基础节点。
- 派生生涯累计节点。
- 确保所有里程碑节点都是 `type=milestone`、`track=milestone`。

## Scope

允许修改：

- `career_backend.py`
- `tests/test_career_timeline_achievement_nodes.py`
- `tests/test_career_achievement_resolver.py`
- 新增 `tests/test_career_timeline_milestone_nodes.py`
- `docs/acs_next_06b_timeline_engineering_prompts.md`

原则上不修改：

- `track.html`
- PB Resolver 成绩规则。
- Race Resolver 赛事识别规则。
- Memory Gallery。

## Constraints

- 不从 raw FIT、points、track_json、file_path、storage_ref 或本地路径推导。
- 只读取 Activity 安全摘要列、Race/PB/Achievement 派生表。
- `first_city` 不进入 06B Timeline。
- `longest_running / longest_cycling / max_ascent / annual_milestone` 等旧 V1 节点不直接进入 06B Timeline，除非被映射到 06B 白名单节点。
- 同一活动同一类别跨多个阈值时，默认展示最高阈值。
- `first_max_altitude_5000m` 覆盖同活动的 `first_max_altitude_3000m`。
- 里程碑节点必须包含 `subtype / badge / value / meta / priority / detail_link`。

## Expected Files or Areas

- `career_backend.py`
  - Timeline milestone whitelist。
  - Timeline milestone derivation helper。
  - `_build_timeline_nodes_for_type()` milestone 分支。
- Timeline milestone tests。

## Validation Commands or Acceptance Checks

执行：

```bash
.venv312/bin/python -m pytest tests/test_career_timeline_milestone_nodes.py tests/test_career_timeline_achievement_nodes.py tests/test_career_timeline_engine_closure.py -q
.venv312/bin/python -m pytest tests/test_career_overview_timeline_races.py tests/test_career_timeline_pb_nodes.py -q
.venv312/bin/python -m py_compile career_backend.py main.py profile_backend.py
```

## Completion Definition

- `type=milestone` 只返回 `track=milestone`。
- `first_city` 不进入 06B Timeline。
- PB 不进入里程碑。
- `first_activity`、`first_sport_activity`、`first_race` 可生成。
- 高海拔 3000m/5000m 可生成，且同活动优先 5000m。
- 累计节点可生成，并绑定跨越阈值活动。
- 所有新增测试通过。
- 完成后根据任务清单建议进入 `ACS-Next-06B-04：顶部胶囊筛选与月份横向双轨布局`。
```

### 执行记录

- 状态：已完成
- 验收：`.venv312/bin/python -m pytest tests/test_career_timeline_milestone_nodes.py tests/test_career_timeline_achievement_nodes.py tests/test_career_timeline_engine_closure.py -q` 通过，`17 passed`。
- 验收：`.venv312/bin/python -m pytest tests/test_career_overview_timeline_races.py tests/test_career_timeline_pb_nodes.py -q` 通过，`16 passed`。
- 验收：`.venv312/bin/python -m py_compile career_backend.py main.py profile_backend.py` 通过。
- Review gate：Timeline milestone 已切换为 06B 白名单与 Timeline 专用派生层；旧 `first_city`、PB、Memory、普通流水不进入主轴；新增节点均绑定 `activity_id` 回跳。
- 下一个建议任务：`ACS-Next-06B-04：顶部胶囊筛选与月份横向双轨布局`

---

## ACS-Next-06B-04：顶部胶囊筛选与月份横向双轨布局

### 工程级提示词

```markdown
# ACS-Next-06B-04：顶部胶囊筛选与月份横向双轨布局

## 任务开始前

每个任务开始前，必须刷新项目契约意识。默认使用首次阅读后形成的项目契约摘要；只有在当前任务、改动文件、测试失败或 review 风险提示需要时，才回到项目契约原文重新阅读。

本任务涉及 Timeline 前端产品形态重构。必须确认：

- 前端只渲染后端 Timeline ViewModel，不判断赛事、PB、成就、首次或累计节点。
- 年份来源必须来自 `available_years` 或 ViewModel 安全字段。
- 内容筛选只有 `全部 / 赛事 / 里程碑`，不出现 PB。
- Timeline 不展示年度摘要、高光年或 Season 卡片。
- 月份内横向定位只能使用后端提供的 `day / days_in_month`。
- Activity Detail 回跳必须保留。

## Goal

把 Timeline 页面从旧纵向节点列表改成 06B 核心浏览形态：

- 顶部年份胶囊：`全部 / 2026 / 2025 / ...`
- 顶部内容胶囊：`全部 / 赛事 / 里程碑`
- 月份横向日期轴。
- 月份内双轨：第一行赛事，第二行里程碑。
- 卡片按日期横向落位。

## Scope

允许修改：

- `track.html`
- `tests/test_career_timeline_frontend_render.py`
- `tests/test_career_timeline_frontend_filters.py`
- `tests/test_career_timeline_frontend_visual_contract.py`
- `docs/acs_next_06b_timeline_engineering_prompts.md`

不修改：

- 后端 Race / PB / Milestone Resolver 语义。
- `career_backend.py`，除非前端测试暴露 ViewModel 字段缺口且能严格证明需要补齐。
- 大数据量拥挤和“更多”入口，留给 `06B-05`。
- 打包、pywebview 真机验收，留给 `06B-06`。

## Constraints

- 不扫描原始活动推断年份、赛事、PB 或里程碑。
- 不读取 raw FIT、points、track_json、file_path、storage_ref、本地绝对路径或 SQLite schema。
- 年份胶囊默认 `全部`。
- 点击年份时保留当前内容类型筛选。
- 内容胶囊默认 `全部`。
- `type=race` 只显示赛事轨道；`type=milestone` 只显示里程碑轨道。
- 空轨道默认隐藏。
- 月份定位公式：`left_percent = (day - 1) / max(days_in_month - 1, 1) * 100`。
- 窄屏可退化为纵向月份列表，但不能丢失类型标签、皇冠、日期和回跳。

## Expected Files or Areas

- `track.html`
  - Timeline panel header / filter render。
  - Timeline state: year + type。
  - `careerTimelineYearCapsuleHtml()` 或同等函数。
  - `careerTimelineContentFilterHtml()` 或同等函数。
  - `careerTimelineMonthHtml()` 从 node list 迁移为 month band。
  - `careerTimelineTrackHtml(month, track)`。
  - `careerTimelineNodePositionStyle(node, month)`。
  - CSS: capsule、month band、track、positioned card、mobile fallback。
- Frontend static tests。

## Validation Commands or Acceptance Checks

执行：

```bash
.venv312/bin/python -m pytest tests/test_career_timeline_frontend_render.py tests/test_career_timeline_frontend_filters.py tests/test_career_timeline_frontend_visual_contract.py -q
.venv312/bin/python -m pytest tests/test_career_timeline_engine_closure.py tests/test_career_timeline_milestone_nodes.py tests/test_career_timeline_pb_nodes.py -q
.venv312/bin/python -m py_compile career_backend.py main.py profile_backend.py
```

## Completion Definition

- Timeline 页面默认展示全部年份 + 全部内容。
- 年份筛选是胶囊按钮，不是原生 `select`。
- 内容筛选只有 `全部 / 赛事 / 里程碑`。
- PB 筛选按钮不存在。
- 运动类型筛选不再出现在 Timeline 顶部。
- 月份内存在横向日期轴容器。
- 同一个月份内赛事和里程碑分轨道展示。
- 卡片按 `day / days_in_month` 横向定位。
- 年度摘要 / 高光年 / Season 卡片不出现在 Timeline 页面。
- 赛事 PB 皇冠仍可渲染，且 Activity Detail 回跳保留。
- 测试通过。
- 完成后根据任务清单建议进入 `ACS-Next-06B-05：卡片避让、更多入口与大数据量渲染`。
```

### 执行记录

- 状态：已完成
- 验收：`.venv312/bin/python -m pytest tests/test_career_timeline_frontend_render.py tests/test_career_timeline_frontend_filters.py tests/test_career_timeline_frontend_visual_contract.py -q` 通过，`26 passed`。
- 验收：`.venv312/bin/python -m pytest tests/test_career_timeline_engine_closure.py tests/test_career_timeline_milestone_nodes.py tests/test_career_timeline_pb_nodes.py -q` 通过，`16 passed`。
- 验收：`.venv312/bin/python -m py_compile career_backend.py main.py profile_backend.py` 通过。
- Review gate：Timeline 前端已切换为年份胶囊、内容胶囊、月份横向日期轴和赛事/里程碑双轨；旧年份 select、运动类型筛选和 Season Summary 调用已移除。
- 下一个建议任务：`ACS-Next-06B-05：卡片避让、更多入口与大数据量渲染`

---

## ACS-Next-06B-05：卡片避让、更多入口与大数据量渲染

### 工程级提示词

```markdown
# ACS-Next-06B-05：卡片避让、更多入口与大数据量渲染

## 任务开始前

每个任务开始前，必须刷新项目契约意识。默认使用首次阅读后形成的项目契约摘要；只有在当前任务、改动文件、测试失败或 review 风险提示需要时，才回到项目契约原文重新阅读。

本任务涉及 Timeline 前端布局稳定性和大数据量渲染。必须确认：

- 前端仍只消费后端 `priority / day / track / days_in_month` 等 ViewModel 字段。
- 前端不得根据活动原始字段判断赛事、PB、里程碑或累计事实。
- “更多”入口只是同月同轨展示策略，不改变正式节点事实。
- Activity Detail 回跳必须保留。
- 06B-04 的年份胶囊、内容胶囊、月份横向双轨不得回退。

## Goal

为 06B Timeline 增加同月同轨卡片拥挤处理：

- 同一月份同一轨道最多直接展示有限数量的高优先级节点。
- 同一天或近日期节点可以错层显示。
- 低优先级或超量节点进入“更多”入口。
- 500+ 节点静态渲染仍稳定。

## Scope

允许修改：

- `track.html`
- `tests/test_career_timeline_frontend_large_render.py`
- `tests/test_career_timeline_frontend_visual_contract.py`
- 必要时补充 `tests/test_career_timeline_frontend_render.py`
- `docs/acs_next_06b_timeline_engineering_prompts.md`

不修改：

- 后端 Resolver 语义。
- Timeline API ViewModel 字段，除非前端拥挤策略严格需要且已有后端安全字段不足。
- Windows/macOS 打包验收。

## Constraints

- 排序只能使用 `priority / day / id / type / track` 等安全 ViewModel 字段。
- 不读取 raw FIT、points、track_json、file_path、storage_ref、本地绝对路径或 SQLite schema。
- 直接展示节点应优先保留赛事和高优先级里程碑。
- 同一天多个节点不能完全重叠。
- “更多”入口必须可访问，带 `aria-label` 或清晰文本。
- 展开更多后仍复用原 Activity Detail 回跳。
- 长标题不能撑破月份容器。

## Expected Files or Areas

- `track.html`
  - `careerTimelineTrackVisibleNodes()` 或同等 helper。
  - `careerTimelineTrackHiddenNodes()` 或同等 helper。
  - `careerTimelineNodePositionStyle()` 增加错层/垂直偏移。
  - `careerTimelineTrackHtml()` 增加更多入口和展开状态。
  - CSS: 稳定卡片宽高、错层高度、更多按钮。
- Frontend large render / visual contract tests。

## Validation Commands or Acceptance Checks

执行：

```bash
.venv312/bin/python -m pytest tests/test_career_timeline_frontend_large_render.py tests/test_career_timeline_frontend_visual_contract.py -q
.venv312/bin/python -m pytest tests/test_career_timeline_frontend_render.py tests/test_career_timeline_frontend_filters.py -q
.venv312/bin/python -m py_compile career_backend.py main.py profile_backend.py
```

## Completion Definition

- 同一轨道默认直接展示数量有限，超量进入“更多”。
- 展开后可显示该轨道更多节点。
- 同一天多个节点有稳定错层，不完全重叠。
- 卡片尺寸有 min/max 或固定约束，长标题不会撑破月份容器。
- 大数据量静态测试通过。
- 06B-04 的胶囊筛选和横向双轨测试仍通过。
- 完成后根据任务清单建议进入 `ACS-Next-06B-06：视觉验收与跨平台收口`。
```

### 执行记录

- 状态：已完成
- 验收：`.venv312/bin/python -m pytest tests/test_career_timeline_frontend_large_render.py tests/test_career_timeline_frontend_visual_contract.py -q` 通过，`17 passed`。
- 验收：`.venv312/bin/python -m pytest tests/test_career_timeline_frontend_render.py tests/test_career_timeline_frontend_filters.py -q` 通过，`17 passed`。
- 验收：`.venv312/bin/python -m py_compile career_backend.py main.py profile_backend.py` 通过。
- Review gate：拥挤策略已收敛为同月同轨按 `priority/day/id` 直显 3 个节点，其余进入轨道级“更多”；卡片按 lane 错层，展开仍复用 Activity Detail 回跳。
- 下一个建议任务：`ACS-Next-06B-06：视觉验收与跨平台收口`

---

## ACS-Next-06B-06：视觉验收与跨平台收口

### 工程级提示词

```markdown
# ACS-Next-06B-06：视觉验收与跨平台收口

## 任务开始前

每个任务开始前，必须刷新项目契约意识。默认使用首次阅读后形成的项目契约摘要；只有在当前任务、改动文件、测试失败或 review 风险提示需要时，才回到项目契约原文重新阅读。

本任务是 06B 代码级闭环验收。必须确认：

- 只能标记代码级完成，不能标记 Windows/macOS 打包级完成。
- Timeline 不暴露 raw FIT、points、track_json、file_path、storage_ref、本地绝对路径或 SQLite schema。
- 前端不自行推断赛事、PB、里程碑、首次或累计事实。
- 06B 的年份胶囊、内容胶囊、月份横向双轨、PB 皇冠、更多入口均有测试锁定。
- 真实用户数据人工浏览、Windows 真机、Windows 打包、macOS 打包仍属于未验证项。

## Goal

做 06B Timeline 的最终代码级验收和文档收口：

- 补齐视觉/安全契约测试缺口。
- 更新测试验收矩阵。
- 新增 06B 完成报告。
- 跑一组覆盖后端、前端、视觉和安全边界的实用回归。

## Scope

允许修改：

- `tests/test_career_timeline_frontend_visual_contract.py`
- `tests/test_career_phase8_cross_platform_visual_contract.py`
- `tests/test_career_phase9_data_boundary_audit.py`
- `docs/acs_phase10_test_acceptance_matrix.md`
- 新增 `docs/acs_next_06b_timeline_completion_report.md`
- `docs/acs_next_06b_timeline_engineering_prompts.md`

原则上不修改：

- 业务语义代码。
- 前端布局代码，除非验收测试发现明确缺口。
- 打包脚本或安装产物。

## Constraints

- 完成报告必须明确：代码级完成，不代表打包级完成。
- 验收矩阵必须保留未验证项：Windows 真机、Windows 打包、macOS 打包、真实用户数据人工浏览。
- 不新增需要外部服务或真实设备的自动化门槛。
- 若只做静态视觉契约测试，应在报告中明确人工验收待执行。

## Expected Files or Areas

- Visual contract tests:
  - 年份胶囊存在。
  - 内容胶囊只有 `全部 / 赛事 / 里程碑`。
  - 没有 PB 筛选按钮。
  - 没有 Season Summary 调用。
  - 有横向月份 band / track / card positioning。
  - 有 PB 皇冠样式和可访问标注。
  - 有更多入口与错层。
- Data boundary tests:
  - forbidden keys 不进入 Timeline ViewModel / 前端渲染路径。
- Docs:
  - acceptance matrix。
  - 06B completion report。

## Validation Commands or Acceptance Checks

执行：

```bash
.venv312/bin/python -m pytest tests/test_career_timeline_engine_closure.py tests/test_career_timeline_milestone_nodes.py tests/test_career_overview_timeline_races.py tests/test_career_timeline_pb_nodes.py -q
.venv312/bin/python -m pytest tests/test_career_timeline_frontend_render.py tests/test_career_timeline_frontend_filters.py tests/test_career_timeline_frontend_visual_contract.py tests/test_career_timeline_frontend_large_render.py -q
.venv312/bin/python -m pytest tests/test_career_phase8_cross_platform_visual_contract.py tests/test_career_phase9_data_boundary_audit.py -q
.venv312/bin/python -m py_compile career_backend.py main.py profile_backend.py
```

## Completion Definition

- 所有 06B 自动化验收通过。
- 完成报告存在并写明代码级完成 / 打包级未验证。
- 验收矩阵记录 06B Timeline 核心浏览体验。
- 不声称 Windows 真机、Windows 打包、macOS 打包或真实用户数据人工浏览已完成。
- 完成后根据任务清单建议：06B 队列已完成，下一步进入人工视觉验收或真实数据浏览。
```

### 执行记录

- 状态：已完成
- 验收：`.venv312/bin/python -m pytest tests/test_career_timeline_engine_closure.py tests/test_career_timeline_milestone_nodes.py tests/test_career_overview_timeline_races.py tests/test_career_timeline_pb_nodes.py -q` 通过，`26 passed`。
- 验收：`.venv312/bin/python -m pytest tests/test_career_timeline_frontend_render.py tests/test_career_timeline_frontend_filters.py tests/test_career_timeline_frontend_visual_contract.py tests/test_career_timeline_frontend_large_render.py -q` 通过，`34 passed`。
- 验收：`.venv312/bin/python -m pytest tests/test_career_phase8_cross_platform_visual_contract.py tests/test_career_phase9_data_boundary_audit.py -q` 通过，`10 passed`。
- 补充验收：`.venv312/bin/python -m pytest tests/test_career_phase8_frontend_readiness.py tests/test_career_phase10_acceptance_matrix_docs.py -q` 通过，`8 passed`。
- 最终宽回归：`.venv312/bin/python -m pytest tests/test_career*.py -q` 通过，`406 passed, 14 subtests passed`。
- 验收：`.venv312/bin/python -m py_compile career_backend.py main.py profile_backend.py` 与 `docs/js_api_contract.json` JSON 校验通过。
- Review gate：06B 完成报告和验收矩阵已明确代码级完成；Windows 真机、Windows 打包、macOS 打包产物和真实用户数据人工浏览仍标记为未验证。
- 下一个建议任务：06B 队列已完成；建议进入人工视觉验收 / 真实数据浏览
