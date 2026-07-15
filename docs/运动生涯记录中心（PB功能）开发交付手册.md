---
title: 运动生涯记录中心（PB 功能）开发交付手册
aliases:
  - 记录中心开发交付手册
  - Records Center PB Handbook
version: v1.0.0
status: Design Freeze
type: Product and Engineering Delivery Handbook
module: ACS Records Center
updated: 2026-07-13
---

# 运动生涯记录中心（PB 功能）开发交付手册

> 本手册是“运动生涯”中 PB 功能的产品、数据、后端、前端、AI 与测试统一依据。
> 它吸收 Records Center 调研方案，但以脉图现有 ACS 架构和当前代码契约为落地基线。
> 若实现与本文冲突，应先更新契约和本文，再修改代码，禁止由前端或单个 Resolver 自行改变产品语义。

后续实施顺序统一以 `docs/运动生涯记录中心（PB功能）开发任务清单.md` 为准；不得绕过任务依赖直接进入后端或前端编码。

## 0. 文档结论

### 0.1 产品名称

用户可见名称冻结为：

```text
记录中心
```

英文名称：

```text
Records Center
```

“PB”保留为纪录类型和用户熟悉的成绩标签，不再作为整个页面的唯一名称。

用词约定：产品模块统一写“记录中心”，表示保存和管理；单项最佳成绩、历史最好成绩统一写“纪录”，表示被创造或刷新的成绩。

### 0.2 产品位置

V1 中，记录中心是“运动生涯”内部的二级页面，与时间轴、赛事档案、荣誉里程碑、记忆、足迹并列。

本期不将记录中心提升为应用全局一级导航。是否升级为与“活动”“趋势分析”“AI 教练”并列的一级模块，在完成 V1 使用验证后另行决策。

### 0.3 V1 一句话定义

记录中心用于自动识别、保存和解释用户由 Activity 产生的个人最佳纪录，并完整展示“当前纪录从哪里来、替代了什么、如何演进”。

### 0.4 V1 核心交付

V1 必须闭环：

1. 跑步 5K、10K、半程马拉松、马拉松的整次活动 PB。
2. 当前纪录、历史纪录和候选纪录三种状态。
3. 新纪录识别、提升幅度计算、旧纪录归档和删除后回退。
4. 每条纪录可回跳来源 Activity Detail。
5. 置信度不足的结果不得直接污染正式纪录。
6. Resolver 可增量运行，也可安全全量重建。
7. 前端只渲染后端 ViewModel，不自行判断 PB。
8. AI 只消费 Records Snapshot，不读取原始 FIT、轨迹点或数据库结构。

### 0.5 V1 明确不做

- 用户手动创建或修改纪录值。
- 用户之间排行榜。
- 路线排行榜或公开挑战。
- 任意活动内的最佳分段成绩。
- 骑行功率持续时间曲线。
- 游泳分段 PB、铁三综合 PB、FTP 自动预测、VO2Max PB。
- 天气、逆风、暴雨等“故事纪录”进入正式 PB。
- 因改名而新建一套与 `career_pb_records` 并行的 `records` 事实表。

---

# 1. 背景与设计目标

## 1.1 为什么使用“记录中心”

PB 只表达“个人最佳”，而长期运动档案还可以容纳：

- 最快：标准距离用时、路线用时、爬坡用时。
- 最长：距离、时长、连续运动。
- 最高：海拔、爬升、功率、速度。
- 最大：训练量、累计量、单次负荷。
- 演进：纪录刷新过程和长期成长。

因此页面采用可扩展的“记录中心”，首期以 PB 为核心，后续再逐步增加其他纪录族。

## 1.2 用户问题

记录中心优先回答四个问题：

1. 我目前最好的成绩是什么？
2. 这项纪录是哪次活动创造的？
3. 相比上一项纪录提升了多少？
4. 我的纪录是如何一步步变化的？

## 1.3 设计目标

- 自动：导入或更新 Activity 后自动评估。
- 真实：每条纪录都必须有可追溯的 Activity 证据。
- 公平：同一种纪录使用固定口径比较。
- 可解释：用户能看到匹配距离、计时口径、置信度和提升量。
- 可恢复：活动删除、纠正或 Resolver 升级后能重新计算。
- 可扩展：新增纪录类型不重写核心比较流程。
- 本地优先：默认在本地计算和保存，不依赖网络服务。

## 1.4 非目标

记录中心不是：

- 社交排名系统。
- 训练负荷或趋势分析替代品。
- 赛事识别系统。
- 成就徽章系统。
- AI 自动编造成绩的入口。

模块关系：

| 模块 | 回答的问题 | 事实责任 |
| --- | --- | --- |
| Records | 我创造过什么最好成绩 | PB Resolver |
| Trends | 我的能力在上升还是下降 | Trend Resolver |
| Race Archive | 哪些 Activity 是正式赛事 | Race Resolver |
| Achievement | 哪些事件值得纪念 | Achievement Resolver |
| AI Coach | 为什么变化、下一步怎么做 | 只读 Snapshot 后解释 |

---

# 2. 架构契约

## 2.1 Activity 是唯一事实源

所有纪录必须来源于已有 Activity：

```text
FIT RAW
  -> fit_engine
  -> Metrics / Performance Resolver
  -> Activity
  -> PB Resolver
  -> Records ViewModel
```

禁止：

- 前端根据标题、距离或配速自行生成 PB。
- AI 直接生成、修改或确认 PB。
- 用户脱离 Activity 手填一项纪录。
- Records Center 复制完整 Activity 或原始轨迹形成第二事实源。

## 2.2 Resolver 职责边界

| 层 | 职责 |
| --- | --- |
| `fit_engine` | 解析 FIT，不做 PB 业务判断 |
| Metrics / Performance Resolver | 产出可比较的规范化成绩和质量信息 |
| PB Resolver | 匹配纪录类型、计算置信度、历史比较、状态迁移 |
| ACS / Records Center | 组织当前纪录、历史、候选和页面 ViewModel |
| Frontend | 展示、筛选、确认候选、打开 Activity Detail |
| AI | 只读 Records Snapshot，生成解释性文本 |

PB Resolver 不应直接读取或向外返回：

- `points` / `points_json`
- `track_json`
- `raw_records` / `fit_records`
- `file_path` / `storage_ref`
- SQLite schema
- 本地绝对路径

未来需要“活动内最佳 5K”时，轨迹扫描由 Performance Resolver 完成，并只向 PB Resolver 提交安全的分段摘要。

## 2.3 单一写入口

正式纪录只能由 PB Resolver 写入。

允许的用户操作只有：

- 确认候选纪录。
- 拒绝候选纪录。
- 打开来源 Activity。

用户确认只改变候选的决策状态，不得修改成绩值、距离、时间或来源 Activity。

## 2.4 可追溯性

每条当前纪录、历史纪录、候选纪录必须包含：

```json
{
  "activity_id": "123",
  "detail_link": {
    "activity_id": "123",
    "source": "career"
  }
}
```

若 `activity_id` 不存在、对应 Activity 已永久删除或无法读取，则该条纪录不得保持 `active`。

## 2.5 与赛事的关系

- PB 不要求 Activity 必须是正式赛事，训练也可能创造 PB。
- `is_race` 可以作为展示信息和辅助证据，但不能替代成绩有效性判断。
- 赛事名称、城市和日期不得单独触发 PB。
- 同一 Activity 可以同时产生 Race Event、PB 和 Achievement，但三者仍由各自 Resolver 负责。

## 2.6 与 Achievement 的关系

PB 与 Achievement 是不同对象：

- PB 保存可比较的成绩事实。
- Achievement 表达“刷新 PB”这一生涯事件。

只有正式激活的新纪录才允许触发 Achievement。候选、拒绝、重算后未变化的纪录不得重复生成 Achievement。

---

# 3. 范围与演进路线

## 3.1 当前代码基线

截至 2026-07-13，仓库已有：

- `career_pb_records` 数据表。
- `resolve_pb_records()`。
- `get_career_pb()` JS Bridge API。
- 运动生涯中的 PB 页面、筛选器和卡片。
- 跑步 5K、10K、半马、全马的整次活动识别。
- `active` / `superseded` 状态和 Activity Detail 回跳。
- API 数据边界与自动化测试。

当前尚未闭环：

- 统一的 `±3%` 标准距离公式。
- 候选确认和拒绝。
- 不可变的纪录事件历史。
- 活动删除或修正后的自动回退。
- PB 详情页与演进图。
- 骑行、越野、路线、功率曲线和环境纪录。
- PB 进入主 Timeline 的最终产品策略。

## 3.2 Release 1：PB 核心闭环

支持运动：跑步。

支持纪录：

| record_key | 显示名 | 标准距离 | 比较方向 | 来源模式 |
| --- | --- | ---: | --- | --- |
| `running_5k` | 5K | 5,000 m | 越小越好 | activity total |
| `running_10k` | 10K | 10,000 m | 越小越好 | activity total |
| `running_half_marathon` | 半程马拉松 | 21,097.5 m | 越小越好 | activity total |
| `running_marathon` | 马拉松 | 42,195 m | 越小越好 | activity total |

## 3.3 Release 1.1：跑步扩展

在 Performance Resolver 能稳定生成分段摘要后增加：

- 400m、800m、1K、3K、15K。
- 50K、100K。
- 活动内最佳分段成绩。
- 公路跑与越野跑分组，避免不公平混比。

## 3.4 Release 2：骑行与越野纪录

骑行：

- 最长距离。
- 最大累计爬升。
- 最佳平均速度。
- 最佳平均功率，仅在可靠功率数据可用时启用。

越野：

- 最长距离。
- 最大累计爬升。
- 指定距离最佳成绩，必须按路线类型和成绩口径分组。

## 3.5 Release 3：专业与故事纪录

- 骑行 Power Duration Curve。
- 路线纪录、爬坡纪录、同一赛事历年纪录。
- 游泳标准距离纪录。
- 环境故事纪录。
- 分享卡片、纪录地图、赛季纪录、年龄组纪录、纪录预测。

故事纪录不得与竞技 PB 混排，也不得使用“最好”暗示健康或风险价值判断。

---

# 4. 术语与状态模型

## 4.1 核心术语

| 术语 | 定义 |
| --- | --- |
| Record Definition | 一项纪录的固定规则，如跑步 10K 最快用时 |
| Record Candidate | 由 Activity 推导但尚未达到自动确认条件的候选 |
| PB Record | 一次曾经或当前成立的个人最佳成绩 |
| Current Record | 某个 `record_key` 当前生效的唯一纪录 |
| Historical Record | 曾经生效、后来被刷新或失效的纪录 |
| Record Event | 纪录检测、确认、激活、替代、拒绝、失效的审计事件 |
| Source Mode | 成绩来源口径，如整次活动或最佳分段 |
| Resolver Version | 生成纪录的规则版本 |

## 4.2 纪录生命周期

```text
detected
  -> candidate
      -> active
      -> rejected
  -> active
      -> superseded
      -> invalidated
```

状态定义：

| status | 含义 | 是否展示在当前纪录 |
| --- | --- | --- |
| `candidate` | 需要用户确认 | 否 |
| `active` | 当前正式纪录 | 是 |
| `superseded` | 被更好成绩替代 | 否，进入历史 |
| `rejected` | 用户明确拒绝 | 否 |
| `invalidated` | 来源 Activity 删除、损坏或规则重算失效 | 否 |

每个 `record_key + source_mode + sport_scope` 同一时刻只能有一条 `active` 纪录。

## 4.3 状态迁移要求

- 首条高置信度成绩直接成为 `active`。
- 新成绩严格优于当前纪录时，新记录变为 `active`，旧记录变为 `superseded`。
- 新成绩与当前成绩相同，不创建新 PB，不替换当前纪录。
- 候选经用户确认后才能参与正式历史比较。
- 候选被拒绝后，同一 `activity_id + record_key + evidence_key` 不得再次提示，除非 Resolver 版本改变且证据发生实质变化。
- 当前纪录失效时，必须从剩余有效记录中重新选出下一条 `active`。

---

# 5. Record Registry

## 5.1 目的

纪录类型必须通过注册表配置，不允许在 UI、SQL 和多个 Resolver 中分别硬编码不同口径。

建议代码结构：

```text
RecordDefinition {
  key
  sport
  category
  display_name
  metric
  canonical_unit
  comparison
  source_mode
  standard_distance_m
  tolerance_ratio
  minimum_data_requirements
  enabled_release
  rule_version
}
```

## 5.2 V1 注册定义

示例：

```json
{
  "key": "running_10k",
  "sport": "running",
  "category": "distance_time",
  "display_name": "10K",
  "metric": "elapsed_time_sec",
  "canonical_unit": "seconds",
  "comparison": "lower_is_better",
  "source_mode": "activity_total",
  "standard_distance_m": 10000,
  "tolerance_ratio": 0.03,
  "rule_version": "records-v1"
}
```

## 5.3 注册表约束

- `key` 发布后不可改变语义。
- 显示名称可以调整，但不能改变比较口径。
- 单位必须使用规范化单位存储，格式化只在 ViewModel 层完成。
- 新增类型必须同时补齐 Resolver、API、UI 和测试。
- 禁用类型不删除历史数据，只停止新纪录评估并在 UI 中隐藏。

---

# 6. 跑步 PB 判定规则

## 6.1 运动类型

只有经过 Sport Resolver 归一为 `running` 的 Activity 才参与 V1 跑步 PB。

`trail_running`、`treadmill_running` 是否进入公路跑 PB 必须明确：

- `trail_running` 默认不与公路跑混比，Release 2 单独建纪录族。
- `treadmill_running` 可生成候选，但无可靠距离校准时不得自动确认。

## 6.2 标准距离匹配

统一使用：

```text
distance_error_ratio = abs(actual_distance_m - standard_distance_m) / standard_distance_m

matched = distance_error_ratio <= 0.03
```

边界为包含关系，即误差恰好等于 3% 时允许匹配。

不得继续为不同距离维护互相不一致的手写区间。

## 6.3 V1 成绩来源

V1 只支持 `activity_total`：

- Activity 总距离匹配标准距离。
- 使用 Performance Resolver 给出的规范化总用时。
- 不从一场 10K 活动中截取最快 5K。
- 不从马拉松中截取半马、10K 或 5K。

界面必须明确标注“整次活动成绩”，避免用户误认为系统已支持最佳分段。

## 6.4 计时口径

跑步标准距离 PB 使用：

```text
elapsed_time_sec
```

即从活动开始到结束的实际经过时间，不能因为自动暂停而排除停留时间。

若历史 Activity 只有含义不明确的 `duration`：

1. Performance Resolver 先统一字段语义。
2. 无法确认是 elapsed time 时，结果最高只能进入候选。
3. 前端不得自行在 moving time 与 elapsed time 之间选择。

## 6.5 比较规则

```text
new_record = candidate.elapsed_time_sec < current.elapsed_time_sec
```

补充规则：

- 精度统一到整数秒。
- 相同秒数视为追平，不刷新纪录。
- 当前纪录不存在时，第一条有效成绩成为首条纪录，`improvement` 为 `null`。
- 提升量：`previous_value - current_value`。
- 不允许用平均配速作为比较主值；平均配速只用于展示。
- 日期不参与成绩优劣，只在完全相同值的内部稳定排序中使用。

## 6.6 有效性要求

候选至少满足：

- Activity 未删除。
- `activity_id` 非空且可读取。
- 运动类型有效。
- 距离大于 0。
- 用时大于 0。
- 标准距离误差不超过 3%。
- 没有被标记为损坏、测试数据或解析失败。

以下情况直接忽略：

- 用时为 0 或负数。
- 距离为 0、负数、NaN 或无穷值。
- 明显不可能的成绩且没有可信设备证据。
- Activity 已软删除。
- 相同证据已经处理。

## 6.7 异常成绩保护

V1 应建立可配置的合理性边界。超出边界不直接删除数据，而是：

```text
confidence 降级
  -> candidate 或 ignored
  -> 保留 reason_code
```

合理性边界只用于数据质量保护，不用于评价用户能力。具体阈值必须来自独立配置并有测试，不能散落在前端文案或 SQL 中。

---

# 7. 置信度与候选机制

## 7.1 处理区间

| confidence | 处理 |
| ---: | --- |
| `> 0.90` | 自动确认，可参与正式纪录比较 |
| `0.70 - 0.90` | 进入候选区，不替换当前纪录 |
| `< 0.70` | 忽略正式 PB，写审计原因 |

`0.70` 和 `0.90` 均属于候选区。

## 7.2 评分维度

置信度必须由可解释信号组成，至少包括：

- 运动类型可靠性。
- 距离与标准距离的接近程度。
- 计时字段完整性和口径确定性。
- Activity 完整性。
- GPS 或设备距离质量；室内活动使用对应设备质量信号。
- 异常值检查结果。

API 应返回：

```json
{
  "confidence": 0.86,
  "confidence_level": "candidate",
  "reason_codes": [
    "distance_within_3_percent",
    "duration_semantics_uncertain"
  ]
}
```

禁止只返回一个无法解释的分数。

## 7.3 用户确认

候选页允许“确认”和“不是有效纪录”两种操作。

确认后：

- 保留原始 Resolver 分数。
- `source` 标记为 `user_confirmed`。
- 写入确认时间和 Record Event。
- 重新与当前纪录比较。

拒绝后：

- 状态改为 `rejected`。
- 保存用户决策，不因普通刷新再次出现。
- 不删除来源 Activity。

用户确认不是手动创建，也不是修改成绩。

---

# 8. 数据模型

## 8.1 兼容策略

V1 继续使用现有 `career_pb_records`，不新建含义重叠的 `records` 表。

现有字段继续保留：

```text
id
activity_id
sport
pb_type
value
value_unit
improvement
event_date
confidence
source
status
display_metadata_json
created_at
updated_at
```

## 8.2 `career_pb_records` 语义冻结

| 字段 | 规则 |
| --- | --- |
| `id` | 稳定纪录实例 ID，不因状态变化改变 |
| `activity_id` | 必填，指向 Activity |
| `sport` | 规范化运动类型 |
| `pb_type` | Record Registry 的 `record_key` |
| `value` | 规范化比较值；跑步 PB 为整数秒 |
| `value_unit` | 规范化单位，如 `seconds` |
| `improvement` | 相对前一条正式纪录的提升量，首条为 `null` |
| `event_date` | 来源 Activity 的本地运动日期 |
| `confidence` | 0 到 1 的 Resolver 置信度 |
| `source` | `resolver` / `user_confirmed` / `migration` |
| `status` | `candidate` / `active` / `superseded` / `rejected` / `invalidated` |
| `display_metadata_json` | 白名单解释字段，不保存原始轨迹和路径 |

`value` 当前为 TEXT 字段，Resolver 必须按 `value_unit` 转为正确数值比较，禁止字符串排序。后续如迁移为 NUMERIC，必须提供兼容迁移和回滚验证。

## 8.3 建议新增的结构化字段

若继续扩展纪录类型，建议通过幂等 migration 增加：

| 字段 | 用途 |
| --- | --- |
| `evidence_key` | 同一 Activity 内证据去重 |
| `source_mode` | `activity_total` / `best_effort_segment` |
| `previous_record_id` | 关联上一条正式纪录 |
| `resolver_version` | 支持规则升级和重算 |
| `confirmed_at` | 用户确认时间 |
| `invalidated_at` | 失效时间 |

在字段尚未迁移前，可暂存于白名单 metadata，但发布 Release 1.1 前必须结构化 `evidence_key`、`source_mode` 和 `resolver_version`。

## 8.4 Record Event 审计表

新增 append-only 表：

```text
career_record_events
```

建议字段：

```text
id
pb_record_id
pb_type
activity_id
event_type
old_status
new_status
previous_record_id
resolver_version
reason_json
created_at
```

`event_type` 支持：

- `detected`
- `candidate_created`
- `user_confirmed`
- `user_rejected`
- `activated`
- `superseded`
- `invalidated`
- `recalculated`

Record Event 只追加，不覆盖历史。

## 8.5 唯一性与索引

必须保证：

- 同一纪录证据幂等：`pb_type + activity_id + evidence_key` 唯一。
- 同一 `pb_type + source_mode + sport_scope` 最多一条 `active`。
- 查询索引至少覆盖 `status`、`sport`、`pb_type`、`event_date`、`activity_id`。

SQLite 若无法直接通过局部约束表达全部规则，由事务内检查和自动化测试共同保证。

## 8.6 AI Snapshot

继续复用 `career_snapshots`，不新建平行的 `records_snapshot` 表。

Records Snapshot 只包含白名单摘要：

```json
{
  "records": {
    "active_count": 4,
    "candidate_count": 1,
    "new_records_last_30d": 2,
    "items": [
      {
        "record_key": "running_10k",
        "value_sec": 2870,
        "event_date": "2026-07-01",
        "improvement_sec": 35
      }
    ]
  }
}
```

Snapshot 不包含轨迹、文件路径、数据库字段说明或用户未确认的推断性结论。

---

# 9. Resolver 处理流程

## 9.1 增量流程

每次 Activity 导入或更新：

```text
Activity changed
  -> Performance summary ready
  -> 找到受影响的 Record Definitions
  -> 生成候选证据
  -> 有效性与置信度评估
  -> 与当前纪录比较
  -> 在单一事务中写 Record + Event
  -> 刷新 Records Snapshot
  -> 返回 new_record_events
```

只重算受影响的纪录类型，禁止每次导入都扫描全部历史。

## 9.2 全量重建

以下情况触发全量重建：

- 首次升级到 Records V1。
- Record Registry 规则版本变化。
- 计时或距离字段语义修复。
- 用户主动执行“重新计算记录”。

重建要求：

1. 建立本次 `resolver_version` 和运行 ID。
2. 在临时结果集中完成计算。
3. 对比现有正式纪录，生成变更计划。
4. 在事务中应用状态迁移和事件。
5. 失败时保留旧的可用结果，不得先清空正式纪录。
6. 重建成功后刷新 Snapshot。

## 9.3 Activity 删除或修正

当来源 Activity 被删除、替换或关键成绩字段改变：

1. 将关联纪录标记为 `invalidated`。
2. 写 `invalidated` Record Event。
3. 对受影响的 `pb_type` 重新评估剩余历史。
4. 将下一条最优有效纪录提升为 `active`。
5. 不把“回退到旧纪录”误报为新 PB。

## 9.4 幂等性

同一输入重复运行必须满足：

- 不产生重复 PB 记录。
- 不重复产生 Achievement。
- 不重复发送新纪录通知。
- 不重复追加语义相同的 Record Event。

## 9.5 并发与事务

- 同一 Activity 的导入和 PB 评估必须串行或使用运行锁。
- 当前纪录替换必须在单一数据库事务中完成。
- 先激活新纪录再使旧纪录失效会产生双 active 窗口，必须避免。
- 事务失败后不得留下没有当前纪录或多个当前纪录的中间状态。

---

# 10. API 契约

## 10.1 现有 API 保留

主查询接口继续使用当前 JS Bridge：

```text
get_career_pb(filters)
```

页面名称可以改为记录中心，内部 API 不因 UI 改名立即重命名。

## 10.2 当前纪录列表

请求：

```json
{
  "sport": "running",
  "year": "all",
  "pb_type": "all",
  "source": "all"
}
```

V1 返回结构：

```json
{
  "pb_records": [
    {
      "id": "pb:running_10k:123",
      "activity_id": "123",
      "sport": "running",
      "sport_label": "跑步",
      "pb_type": "running_10k",
      "pb_type_label": "10K",
      "pb_title": "10K PB",
      "value": 2870,
      "value_unit": "seconds",
      "value_display": "47:50",
      "improvement": 35,
      "improvement_display": "提升 0:35",
      "event_date": "2026-07-01",
      "confidence": 0.96,
      "source": "resolver",
      "source_mode": "activity_total",
      "detail_link": {
        "activity_id": "123",
        "source": "career"
      }
    }
  ],
  "summary": {
    "total": 1,
    "by_pb_type": {"running_10k": 1},
    "by_sport": {"running": 1},
    "by_year": {"2026": 1}
  },
  "status": {
    "schema_ready": true,
    "data_ready": true,
    "rebuilding": false,
    "resolver_version": "records-v1",
    "message": "记录已生成"
  }
}
```

## 10.3 建议新增 API

```text
get_career_pb_detail({ record_id })
get_career_pb_history({ pb_type, source_mode })
get_career_pb_candidates(filters)
decide_career_pb_candidate({ record_id, decision })
rebuild_career_pb_records({ reason })
```

`decision` 只允许：

```text
confirm
reject
```

接口属性：

| API | readonly | 说明 |
| --- | --- | --- |
| `get_career_pb` | 是 | 查询当前正式纪录 |
| `get_career_pb_detail` | 是 | 查询单条纪录详情 |
| `get_career_pb_history` | 是 | 查询单项纪录演进 |
| `get_career_pb_candidates` | 是 | 查询待确认候选 |
| `decide_career_pb_candidate` | 否 | 写入用户确认或拒绝决定 |
| `rebuild_career_pb_records` | 否 | 维护操作；必须防重入并返回运行状态 |

## 10.4 历史 API

历史按发生日期升序返回，必须包含状态和前序关系：

```json
{
  "record_key": "running_10k",
  "current_record_id": "pb:running_10k:123",
  "history": [
    {
      "record_id": "pb:running_10k:21",
      "value": 3250,
      "value_display": "54:10",
      "event_date": "2023-04-02",
      "status": "superseded",
      "activity_id": "21"
    },
    {
      "record_id": "pb:running_10k:123",
      "value": 2870,
      "value_display": "47:50",
      "event_date": "2026-07-01",
      "status": "active",
      "activity_id": "123"
    }
  ]
}
```

## 10.5 API 安全边界

所有 Records API 禁止返回：

- 原始 FIT 数据。
- 完整轨迹点。
- 本地文件路径或 `file://` URL。
- `storage_ref`。
- SQLite schema。
- 未经过白名单处理的 metadata。

## 10.6 错误码建议

| code | 含义 |
| --- | --- |
| `RECORD_NOT_FOUND` | 纪录不存在 |
| `ACTIVITY_NOT_FOUND` | 来源活动不存在 |
| `INVALID_DECISION` | 候选操作非法 |
| `RECORD_ALREADY_DECIDED` | 候选已处理 |
| `REBUILD_IN_PROGRESS` | 正在重建 |
| `RECORDS_UNAVAILABLE` | 数据暂不可用 |

---

# 11. 前端产品与交互

## 11.1 页面信息架构

运动生涯二级导航将“PB”改为“记录”。

记录中心页面使用三个视图：

```text
当前纪录 | 演进 | 候选
```

使用标签页或分段控件，不用三个并列大卡片作为页面导航。

## 11.2 当前纪录视图

页面顺序：

1. 运动类型筛选。
2. 纪录摘要：当前纪录数、最近 30 天刷新数、待确认数。
3. 按运动类型分组的纪录列表。
4. 空态、部分数据提示或重建状态。

V1 纪录卡展示：

- 纪录名称。
- 当前值。
- 相比上一纪录的提升量；首条显示“首次记录”。
- 发生日期。
- 来源活动标题或“查看活动”。
- “整次活动”口径标签。
- 必要时显示候选或数据质量状态。

高置信度正式纪录不默认展示技术分数，避免信息噪声；详情中可查看判定依据。

## 11.3 演进视图

用户先选择纪录类型，再展示：

- 当前纪录。
- 纪录变化折线或阶梯图。
- 按时间排列的纪录节点。
- 每次提升量。
- 对应 Activity 入口。

图表纵轴必须按指标方向处理。跑步用时越低越好，视觉上不能让更快成绩看起来像“下降变差”。可使用反向时间轴或明确的“提升”标识。

## 11.4 候选视图

每条候选展示：

- 可能匹配的纪录类型。
- 成绩和实际距离。
- 未自动确认的原因。
- 置信度等级。
- 来源 Activity。
- 确认按钮。
- “不是有效纪录”按钮。

确认和拒绝都必须有即时反馈，并防止重复提交。

## 11.5 详情视图

点击纪录打开详情抽屉或独立页面，至少包含：

- 纪录名称和当前值。
- 提升量和前一纪录。
- 来源模式与计时口径。
- 实际距离、标准距离和误差。
- 日期、活动标题、运动类型。
- 判定依据。
- 历史变化。
- 打开 Activity Detail 的主操作。

地图、天气、装备只作为 Activity 摘要展示，不复制完整详情页，也不阻塞 V1。

## 11.6 新纪录反馈

导入完成且正式激活新纪录时，可展示一次轻量通知：

```text
刷新 10K 纪录
47:50，比上次快 35 秒
```

要求：

- 首条纪录显示“建立首条 10K 记录”，不写“提升 0 秒”。
- 候选不显示“刷新纪录”。
- 重建产生的相同结果不重复通知。
- 点击通知进入纪录详情。

## 11.7 页面状态

必须实现：

| 状态 | 表现 |
| --- | --- |
| Loading | 固定尺寸骨架，不引起布局跳动 |
| Empty | 说明尚无符合规则的记录，并提供返回活动入口 |
| Partial | 明确哪些运动或指标暂不可用 |
| Candidate | 显示待确认数量和原因 |
| Rebuilding | 保留旧结果可读，显示正在重新计算 |
| Error | 保留上次可用数据并显示重试操作 |

禁止出现 `undefined`、`NaN`、空 JSON 或本地路径。

## 11.8 无障碍与响应式

- 状态不能只靠颜色区分。
- 图标按钮必须有可访问名称和 tooltip。
- 键盘可进入卡片、切换视图、确认候选和打开 Activity。
- 移动端使用单列，筛选控件可换行但不得溢出。
- 长中文活动标题必须截断或换行，不遮挡成绩。
- 数值区域使用稳定宽度，加载和刷新不能改变卡片高度。

---

# 12. Timeline、Overview 与其他模块联动

## 12.1 Overview

Overview 只展示一个代表性纪录摘要：

- 优先最近正式刷新且有显著提升的纪录。
- 若最近没有刷新，展示当前优先级最高的跑步纪录。
- 必须可进入记录中心或来源 Activity。

Overview 不重复渲染全部纪录列表。

## 12.2 主 Timeline

产品策略冻结为：

- 主 Timeline 只展示“纪录被正式刷新”的事件，不展示静态当前纪录。
- 首次建立纪录可作为里程碑，但需与 Achievement 去重。
- 候选、拒绝、重算无变化不进入主 Timeline。
- 同一 Activity 同时产生赛事和 PB 时，合并为一个节点的多个徽标，避免重复节点。

当前代码中 PB 节点仍被排除在 Timeline 外，开发时应作为显式迁移项，不得在前端临时拼接。

## 12.3 Race Archive

同一 Activity 是赛事且产生 PB 时：

- Race Archive 卡片显示 PB 徽标。
- 点击仍进入现有 Activity Detail。
- 赛事历年成绩比较属于后续“赛事纪录”，不替代通用 PB 历史。

## 12.4 Achievement

正式刷新纪录可生成 Achievement Event，但必须使用稳定幂等键：

```text
achievement:pb:{pb_record_id}
```

记录失效时，Achievement 不应静默删除；应标记来源纪录已失效，具体展示策略由 Achievement 契约决定。

## 12.5 Trends

Records 与 Trends 的联动只传递事实摘要：

- 最近刷新频率。
- 某纪录的长期变化。
- 距离类型覆盖。

Records 不根据一次 PB 直接得出“整体能力一定提升”的结论。

---

# 13. AI 解释契约

## 13.1 输入边界

AI 只接收 Records Snapshot，不读取：

- 原始 FIT。
- 原始轨迹数组。
- 数据库表结构。
- 本地文件路径。
- 未确认候选的强结论。

## 13.2 可生成内容

- 本次刷新了什么纪录。
- 相比前一纪录提升多少。
- 某项纪录的长期演进摘要。
- Records 与 Trends 共同支持时的谨慎解释。

## 13.3 禁止内容

- 编造不存在的成绩、天气、装备或路线。
- 将候选说成已确认 PB。
- 仅凭一次 PB 给出伤病、疾病或恢复诊断。
- 修改纪录状态。
- 绕过 Resolver 重新计算成绩。

## 13.4 降级

AI 不可用时：

- 记录识别、保存、历史和通知仍正常工作。
- 使用确定性文案展示成绩与提升量。
- 不显示空白 AI 卡片或阻塞错误。

---

# 14. 异常与边界处理

## 14.1 无 Activity

展示稳定空态：

```text
还没有可生成记录的运动数据
同步或导入活动后，系统会自动识别个人记录。
```

## 14.2 有 Activity 但无匹配纪录

说明标准距离和当前支持范围，不暗示数据丢失。

## 14.3 重复导入

- 先依赖 Activity 导入层去重。
- PB 层再按 `activity_id + pb_type + evidence_key` 幂等。
- 不重复生成历史事件、通知或 Achievement。

## 14.4 同一 Activity 匹配多个标准距离

V1 `activity_total` 模式下，使用相对误差最小的唯一标准距离。

若误差完全相同，按 Record Registry 中更长距离优先，并写入决策原因。正常标准距离配置不应产生此类重叠，测试必须覆盖注册表区间冲突。

## 14.5 日期和时区

- 比较成绩不依赖日期。
- 展示日期使用 Activity 本地开始日期。
- 数据库存储应保留 UTC 时间和本地日期来源。
- 跨时区不得把同一次活动显示到错误年份。

## 14.6 单位

- 距离统一以米计算。
- 用时统一以秒计算。
- 功率统一以瓦计算。
- 爬升和海拔统一以米计算。
- 速度统一以 m/s 或明确的 canonical 单位存储，ViewModel 再格式化。

## 14.7 旧数据语义不确定

无法确认距离或计时口径的历史 Activity：

- 不静默当成高置信度正式纪录。
- 进入候选或忽略。
- API 返回可解释的 `reason_code`。

## 14.8 Resolver 升级导致纪录变化

- 显示“记录已按新规则重新计算”，不伪装成当天刷新。
- 写 `recalculated` 事件。
- 不发送新纪录庆祝通知。
- 保留旧结果审计信息。

---

# 15. 性能、安全与可观测性

## 15.1 性能目标

建议本地数据量基线：10,000 条 Activity。

- 单次 Activity 增量 PB 评估 P95 小于 300ms，不含 FIT 解析。
- 当前纪录列表查询 P95 小于 150ms。
- 单项历史查询 P95 小于 200ms。
- 全量重建可后台运行，UI 仍可读取上次正式结果。

## 15.2 日志

记录：

- 运行 ID。
- Resolver 版本。
- 处理 Activity 数。
- 生成候选数。
- 激活、替代、拒绝、失效数量。
- 跳过原因计数。
- 运行耗时。

不记录：

- 原始轨迹。
- 完整 FIT 内容。
- 本地绝对路径。
- 不必要的个人位置明细。

## 15.3 指标

- `records_resolver_duration_ms`
- `records_candidates_total`
- `records_activated_total`
- `records_rejected_total`
- `records_invalidated_total`
- `records_rebuild_failures_total`
- `records_duplicate_prevented_total`

## 15.4 本地隐私

- 默认不上传 Records Snapshot。
- 分享能力另行授权。
- AI 调用必须遵守现有本地/远端配置和脱敏边界。
- API 不暴露本地文件路径或数据库内部实现。

---

# 16. 迁移方案

## 16.1 命名迁移

前端：

- 二级导航 `PB` -> `记录`。
- 页面标题 `PB 记录` -> `记录中心`。
- 卡片仍可显示 `5K PB`、`10K PB`。

后端：

- 保留 `career_pb_records`。
- 保留 `get_career_pb()`。
- 新能力优先扩展现有契约，不创建同义 API。

## 16.2 距离规则迁移

当前代码使用多个硬编码范围，和统一 `±3%` 规则不完全一致。迁移时：

1. 将范围改为标准距离与容差公式。
2. 使用新 Resolver 版本全量 dry-run。
3. 输出将新增、删除、替换的纪录清单。
4. 对真实数据抽样核对，尤其是 4.8-5.0K、9.5-10.0K 边界活动。
5. 用户确认后再正式应用重算。

## 16.3 计时口径迁移

当前 `duration` / `duration_sec` 需要先确认语义。不得仅改字段名即视为完成。

迁移必须输出：

- 哪些 Activity 有可靠 elapsed time。
- 哪些只能确定 moving time。
- 哪些口径未知并进入候选。

## 16.4 历史迁移

现有 `active` / `superseded` 记录可迁移为历史链：

- 按 `pb_type` 和发生日期排序。
- 重新验证每条记录在当时是否严格优于此前最好值。
- 非纪录活动不进入 PB 历史。
- 为有效状态迁移补写 `migration` Record Event。
- 不伪造当年未保存的通知或 AI 文案。

---

# 17. 测试策略

## 17.1 单元测试

Record Registry：

- key 唯一。
- 单位合法。
- 标准距离区间不冲突。
- comparison 与 unit 匹配。

距离匹配：

- 恰好 -3%、+3% 可匹配。
- 超出边界最小精度不可匹配。
- 不同标准距离只命中一个定义。

比较：

- 更快刷新。
- 更慢不刷新。
- 相同秒数不刷新。
- 首条纪录 improvement 为 `null`。
- 提升量计算正确。

状态：

- candidate 确认后参与比较。
- rejected 不再次提示。
- active 被删除后正确回退。
- 重建失败保留旧 active。
- 同一类型不会出现两个 active。

## 17.2 集成测试

- FIT 导入后触发增量 Resolver。
- 重复导入不重复记录。
- Activity 修改后受影响类型被重算。
- Activity 删除后纪录失效并回退。
- Record Event 完整记录状态迁移。
- Snapshot 只含白名单字段。
- API 统一 envelope 和错误码稳定。

## 17.3 API 边界测试

递归断言响应不含：

- points / track_json。
- raw FIT。
- file_path / storage_ref。
- SQLite schema。
- `/Users/`、`\\Users\\`、`/tmp/` 等本地路径。

## 17.4 前端测试

- 当前纪录、演进、候选三视图。
- Loading / Empty / Partial / Rebuilding / Error。
- 年份、运动、纪录类型筛选。
- 长中文标题和极长成绩文本。
- 桌面和移动端不溢出、不重叠。
- 键盘与读屏标签。
- 点击纪录和通知能打开正确 Activity。
- 低置信度候选不会显示为正式 PB。

## 17.5 真实数据回放

至少准备：

- 同一距离多次逐步提升。
- 4.8K、4.85K、5.0K、5.15K、5.16K 边界活动。
- 自动暂停明显的活动。
- GPS 漂移活动。
- 跑步机活动。
- 被删除的当前纪录。
- 重复导入 Activity。
- 同一天多个成绩。
- 跨时区 Activity。

## 17.6 回归测试

不得破坏：

- Activity 列表和详情。
- Race Resolver 和用户赛事覆盖。
- ACS Overview。
- Timeline 现有赛事与里程碑。
- Achievement 幂等性。
- macOS / Windows pywebview API。
- 现有 JS API contract。

---

# 18. 验收标准

## 18.1 产品验收

| 编号 | 标准 |
| --- | --- |
| RC-001 | 用户入口名称为“记录”，页面名称为“记录中心” |
| RC-002 | V1 明确展示只支持跑步 5K、10K、半马、全马整次活动 PB |
| RC-003 | 用户可查看当前纪录、历史演进和候选纪录 |
| RC-004 | 每条纪录可打开正确的 Activity Detail |
| RC-005 | 新纪录通知只在正式刷新时出现一次 |
| RC-006 | 无数据、部分数据、重建和错误状态均有稳定 UI |

## 18.2 规则验收

| 编号 | 标准 |
| --- | --- |
| RC-101 | 跑步标准距离统一使用包含边界的 `±3%` 公式 |
| RC-102 | 跑步比较主值为整数秒 elapsed time |
| RC-103 | 相同秒数不刷新纪录 |
| RC-104 | 首条纪录不产生虚假提升量 |
| RC-105 | 置信度 `>0.90` 才可自动确认 |
| RC-106 | `0.70-0.90` 只进入候选，不替换当前纪录 |
| RC-107 | 用户只能确认或拒绝候选，不能修改成绩 |

## 18.3 数据验收

| 编号 | 标准 |
| --- | --- |
| RC-201 | 所有纪录都有有效 `activity_id` |
| RC-202 | 同一纪录范围最多一条 `active` |
| RC-203 | 重复运行 Resolver 不增加重复数据 |
| RC-204 | 当前纪录来源 Activity 删除后能回退到下一有效纪录 |
| RC-205 | 所有状态变化写入 append-only Record Event |
| RC-206 | 全量重建失败时保留旧结果 |
| RC-207 | API 不返回原始轨迹、本地路径或数据库结构 |

## 18.4 工程验收

| 编号 | 标准 |
| --- | --- |
| RC-301 | Record Registry 是纪录定义单一来源 |
| RC-302 | PB Resolver 是正式纪录唯一写入口 |
| RC-303 | 前端不计算 PB、不计算提升量、不判断置信度 |
| RC-304 | AI 不参与事实计算和状态修改 |
| RC-305 | 增量评估和全量重建都有自动化测试 |
| RC-306 | macOS 与 Windows 的 API、SQLite migration 和中文 UI 均通过验证 |

---

# 19. 开发拆解

## Phase RC-00：契约冻结

- 冻结 Record Registry。
- 冻结 elapsed time 口径。
- 冻结统一 `±3%` 公式。
- 冻结状态机、API 和 Record Event 模型。
- 对当前真实数据库执行只读差异审计。

交付物：契约文档、差异报告、测试样例。

## Phase RC-01：Resolver 与迁移

- 重构硬编码距离范围为 Registry。
- 增加置信度和 reason codes。
- 增加 candidate / rejected / invalidated 状态。
- 增加 `career_record_events`。
- 实现删除回退、幂等和全量安全重建。

交付物：migration、Resolver、单元与集成测试。

## Phase RC-02：API 与 ViewModel

- 扩展 `get_career_pb()` 状态信息。
- 新增详情、历史、候选、候选决策 API。
- 更新 `docs/js_api_contract.json`。
- 完成响应白名单与错误码测试。

交付物：API 契约、后端测试、兼容说明。

## Phase RC-03：记录中心 UI

- PB 导航改为“记录”。
- 实现当前纪录、演进、候选视图。
- 实现详情、Activity 跳转和状态页。
- 完成桌面、移动端和无障碍验证。

交付物：前端实现、截图验收、交互测试。

## Phase RC-04：跨模块联动

- Overview 代表纪录。
- Timeline 纪录刷新事件。
- Race Card PB 徽标。
- Achievement 幂等联动。
- Records Snapshot 和 AI 降级文案。

交付物：跨模块回归报告。

## Phase RC-05：真实数据发布门禁

- 真实 Activity 全量 dry-run。
- 边界样本人工复核。
- macOS / Windows 真机验证。
- 打包产物数据库 migration 验证。
- 性能、日志和回滚演练。

交付物：真实数据回放报告、发布检查表、回滚说明。

---

# 20. Definition of Done

只有同时满足以下条件，Records Center V1 才能标记完成：

1. 产品名称、范围、判定口径和状态机已冻结。
2. 当前硬编码距离范围已迁移为统一 Registry 和 `±3%` 公式。
3. elapsed time 语义已验证，未知旧数据不会被静默当成正式 PB。
4. 当前、历史、候选三条用户路径均可用。
5. Activity 删除、修改、重复导入和 Resolver 重建均能正确恢复。
6. 每条纪录都能回跳 Activity Detail。
7. 前端、AI 和 API 均未越过事实边界。
8. 自动化测试、真实数据回放、双平台真机和打包 migration 均通过。
9. `docs/js_api_contract.json`、ACS 总交付手册和开发任务清单已同步。
10. 发布说明明确 V1 只支持整次活动 PB，不宣传尚未交付的最佳分段、路线或功率曲线。

---

# 附录 A：调研建议的采纳结论

| 调研建议 | 本手册结论 |
| --- | --- |
| 使用“记录中心”而非“PB 中心” | 采纳 |
| 作为应用全局一级模块 | V1 暂不采纳，先作为运动生涯二级模块 |
| Records Resolver 是唯一计算入口 | 采纳，并沿用现有 PB Resolver 边界 |
| 自动生成、不可手填 | 采纳；允许确认/拒绝候选，不允许改值 |
| 保存当前纪录和历史 | 采纳 |
| Record Registry | 采纳 |
| 每次导入增量更新 | 采纳，同时要求安全全量重建 |
| Running / Cycling / Swimming / Hiking 全量首发 | 不采纳，按数据可靠性分期 |
| 路线、环境、赛事纪录首发 | 延后，避免与核心 PB 混淆 |
| AI 自动解读 | 采纳为可降级能力，AI 不参与事实计算 |
| 新建 records / records_history / records_snapshot | 不直接照搬；兼容现有 `career_pb_records`、新增事件表、复用 `career_snapshots` |

# 附录 B：开发前必须回答的问题

以下问题未有证据前不得直接进入实现：

1. 当前 `duration` 和 `duration_sec` 分别表示 elapsed time 还是 moving time？
2. 历史 Activity 是否保存可靠的 elapsed time canonical 字段？
3. 软删除、重新导入和 Activity ID 去重的实际契约是什么？
4. 跑步机距离的设备来源和质量字段是什么？
5. 当前 Timeline 为什么显式排除 PB 节点，是否存在尚未记录的产品决定？
6. Achievement 在来源 PB 失效后的展示策略是什么？
7. Windows 打包环境下 SQLite migration 和后台重建如何表现？

以上问题应在 RC-00 通过代码、真实数据库和测试证据回答，不允许凭假设补齐。
