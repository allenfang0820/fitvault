---
title: 脉图运动生涯系统（ACS）开发团队交付手册
aliases:
  - ACS 开发交付手册
  - Athlete Career System 开发团队交付手册
version: v1.1.0
status: Architecture Freeze
type: System Design Document
scope: 脉图本地 AI 运动生涯系统
source:
  - [[我的文档/项目/脉图/荣誉墙产品设计/脉图运动生涯系统（ACS）产品设计规范]]
updated: 2026-07-09
---

# 脉图运动生涯系统（ACS）开发团队交付手册

> 说明：本文档由 [[我的文档/项目/脉图/荣誉墙产品设计/脉图运动生涯系统（ACS）产品设计规范]] 提炼而来，面向前端、后端、AI 与测试团队。  
> 若本文与原产品设计规范冲突，以原规范和数据契约为准。

## 阅读顺序

建议按以下顺序阅读：

1. 系统摘要
2. 架构契约
3. 模块设计
4. 数据模型
5. API 设计
6. 前端实现
7. 异常与边界
8. 测试与验收
9. 开发拆解

---

# 1. 系统摘要

## 1.1 ACS 是什么

Athlete Career System（ACS，运动生涯系统）是脉图的长期运动档案层，用来把离散的 Activity 组织成可回顾、可沉淀、可叙事的个人运动生涯。

ACS 不负责生成新的运动事实，而负责把已有数据转化为以下内容：

- 运动生涯总览
- 年度 / 月度时间轴
- 赛事档案
- PB 记录
- 荣誉里程碑
- 记忆相册
- AI 运动生涯总结

## 1.2 核心对象

ACS 的核心对象关系如下：

```text
Athlete
  ↓
Career
  ↓
Season
  ↓
RaceEvent
  ↓
Activity
  ↓
Achievement / PB / Memory
```

## 1.3 核心价值

| 维度 | 价值 |
| --- | --- |
| 数据层 | 沉淀长期运动资产 |
| 产品层 | 形成运动人生档案 |
| AI 层 | 提供长期成长洞察 |
| 用户层 | 增强情感连接 |

## 1.4 非目标

ACS 不是以下系统：

- 社交系统
- 在线排行榜
- 训练计划系统
- 传统 KPI Dashboard
- 奖牌收藏系统

奖牌、图片、故事都可以进入 ACS，但它们只是故事载体，不是系统主目标。

---

# 2. 架构契约

> 以下约束是硬性要求，开发实现不得绕过。

## 2.1 Activity 是唯一事实源

所有 ACS 数据必须可追溯到 Activity。

```text
FIT RAW
  ↓
fit_engine
  ↓
resolver
  ↓
Activity Database
  ↓
ACS
```

禁止：

- 前端自行计算事实
- AI 自行生成成绩
- ACS 复制 Activity 原始字段作为二次事实层

## 2.2 Resolver 负责语义，ACS 负责组织

- `fit_engine`：只负责解析原始 FIT
- `resolver`：只负责把 Activity 变成业务语义
- `ACS`：负责把语义组织成生涯结构
- `AI Snapshot`：只负责给 AI 消费，不修改事实

## 2.3 AI 只能消费 Snapshot

AI 不得直接读取：

- 原始 FIT
- 原始记录数组
- 数据库 schema
- 本地文件路径

AI 只读 `ai_snapshot.json` 或等价结构。

## 2.4 不重复存储 Activity

ACS 保存的是派生数据与索引，不保存完整运动事实。

正确：

```json
{
  "activity_id": "xxx",
  "event_type": "marathon",
  "achievement_ids": ["..."],
  "display_metadata": {}
}
```

错误：

```json
{
  "distance": 42195,
  "heart_rate": 168,
  "gps": []
}
```

## 2.5 入口必须可回跳 Activity Detail

所有赛事、PB、荣誉、记忆都必须能回跳到原始 Activity Detail。

跳转时必须携带：

```json
{
  "activity_id": "xxx",
  "source": "career"
}
```

## 2.6 置信度低的事件不能直接污染主时间轴

Resolver 输出若置信度不足，应保留为候选事件，不直接进入正式 Timeline。

---

# 3. 模块设计

## 3.1 模块总览

ACS V1 建议拆分为以下模块：

```text
ACS
├── Career Overview
├── Timeline Engine
├── Race Archive
├── PB Engine
├── Achievement Engine
├── Memory Gallery
├── Race Map
└── AI Career Insight
```

## 3.2 Career Overview

### 职责

首页总览是 ACS 的运动生涯封面页。

它不再以解释型问答卡片作为首屏主形态，而是优先展示用户最有记忆点的运动瞬间，以及长期累计下来的运动成果。

一句话定义：

```text
先展示值得记住的一场运动，再展示长期积累出的运动资产。
```

### 展示内容

Overview V2 的首屏结构如下：

1. 赛事记忆 Banner
   - 优先展示已绑定照片的赛事记忆。
   - 若没有赛事照片，使用代表活动或赛事标题生成艺术字 Banner。
   - 若没有正式赛事但已有普通 Activity，展示“运动记忆”而不是伪装成赛事。
   - 若完全没有 Activity，展示稳定空态。
   - Banner 必须能回跳 Activity Detail。

2. 全量运动统计
   - 总跑步距离
   - 总骑行距离
   - 总徒步 / 步行距离
   - 总游泳距离
   - 力量训练总重量
   - 总活动数
   - 总运动时长
   - 覆盖城市数
   - 覆盖国家数
   - 完赛赛事数
   - 最高海拔
   - 最长单次距离
   - 最大爬升
   - 活跃年份

3. 年度结构
   - 年度里程
   - 年度赛事
   - 年度 PB
   - 年度城市足迹
   - 年度代表活动
   - 年度卡片仅作为 Overview 中的年度统计摘要，覆盖全部已有运动年份并按年份倒序排列；标题使用“{year} 年度”，不展示“高光年 / 赛事年 / 记录年 / 空白年”等阶段评价

4. 下钻入口
   - 时间轴
   - 赛事档案
   - PB
   - 荣誉里程碑
   - 记忆
   - 赛事足迹
   - AI 生涯总结

### 明确禁止

- 不再恢复三问卡片作为总览首屏 UI。
- 不用营销式大 hero 解释 ACS 是什么。
- 前端不得根据标题、距离、配速自行推断赛事、PB、荣誉或力量训练总重量。
- 无赛事照片时不得返回本地文件路径；只能使用标题艺术字 fallback 或安全逻辑图片引用。

## 3.3 Timeline Engine

### 职责

按“年份 × 月份 × 赛事”生成时间轴，是 ACS 的核心浏览方式。

### 关键规则

- 纵向年份
- 横向月份
- 节点按赛事 / PB / 首次 / 里程碑区分
- 时间轴优先于列表

## 3.4 Race Archive

### 职责

整理正式赛事记录，形成可浏览的赛事档案。

### 赛事识别与用户覆盖规则

赛事事实必须由后端写入和解析，前端不得根据标题、距离、城市或日期自行推断。

识别优先级：

1. 用户手动确认 / 取消：最高优先级。
   - 活动列表在「时间」与「标题」之间展示赛事奖牌列。
   - 点亮 `🏅` 表示赛事；灰阶未点亮 `🏅` 表示非赛事。
   - 用户点击奖牌后即时写入 `activities.is_race` 与用户覆盖状态，不弹窗。
   - 用户取消赛事后，后续 Resolver / FIT / 标题 / 距离不得自动覆盖该取消结果。
2. FIT `session.sport_event == race`：高置信度赛事来源。
3. 活动标题强赛事关键词 + 标准距离区间：中置信度正式赛事。
4. 仅标准距离匹配：低置信度候选事件，不进入正式赛事时间轴。
5. 城市 / 时间：仅可作为展示信息或弱辅助证据，不得单独触发正式赛事或候选赛事。

V1 不依赖网络开放赛事库。若未来引入外部赛事信息源，必须先新增数据来源契约、置信度降级规则、失败降级策略与用户纠错机制。

### 赛事命名优先级

1. FIT Event Name
2. User Metadata
3. Resolver Database
4. Generic Name

若都没有，则使用：

```text
年份 + 城市 + 类型
```

例如：

```text
2026 北京马拉松
```

## 3.5 PB Engine

### 职责

识别并维护个人最佳成绩。

### V1 支持范围

跑步：

- 5K
- 10K
- 半马
- 全马

骑行：

- 最大距离
- 最大爬升
- 最快速度 / 功率类 PB（按实际数据可用性决定）

## 3.6 Achievement Engine

### 职责

识别运动里程碑，表达“发生了什么重要事情”。

### V1 分类

- 首次里程碑
- 性能突破
- 距离挑战
- 连续性成就
- 探索成就
- 特殊事件

### 与 PB 的区别

| 模块 | 回答的问题 |
| --- | --- |
| PB | 我跑得更快了吗？ |
| Achievement | 我的运动生涯发生过哪些重要事情？ |

## 3.7 Memory Gallery

### 职责

把照片、轨迹和 AI 文本组织成可回忆的记忆卡片。

### 数据来源

- User Media
- Activity Metadata
- AI Snapshot

## 3.8 Race Map

### 职责

展示赛事地理分布，回答“我跑过 / 骑过哪些城市”。

### 数据来源

- Race Event
- GPS Start Location
- City Metadata

## 3.9 AI Career Insight

### 职责

把长周期运动数据压缩成可读的年度总结、生涯总结和成长叙事。

### 输入要求

AI 只读：

- `ai_snapshot`
- 结构化摘要
- 少量代表性记忆

禁止读取原始 FIT 与数据库。

---

# 4. 数据模型

> 数据模型采用“派生数据存储”思路，只保存语义结果与引用，不复制原始 Activity。

## 4.1 RaceEvent

### 结构

```json
{
  "id": "race_001",
  "activity_id": "activity_001",
  "name": "北京马拉松",
  "date": "2026-10-15",
  "sport": "running",
  "type": "marathon",
  "location": {
    "city": "北京",
    "country": "China"
  },
  "performance": {},
  "achievement": []
}
```

### 字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | string / UUID | 赛事 ID |
| activity_id | string / UUID | 关联 Activity |
| name | string | 赛事名称 |
| date | date | 日期 |
| sport | string | 运动类型 |
| type | string | 赛事类型 |
| location | object | 地点 |
| performance | object | 成绩摘要 |
| achievement | array | 关联成就 |
| confidence | float | 识别置信度 |

## 4.2 PBRecord

### 结构

```json
{
  "id": "pb_001",
  "activity_id": "activity_001",
  "sport": "running",
  "type": "marathon",
  "value": "3:28:10",
  "improvement": "-12min",
  "date": "2026-10-15"
}
```

### 字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | UUID | PB 记录 ID |
| activity_id | UUID | 关联 Activity |
| sport | TEXT | 运动类型 |
| type | TEXT | PB 类型 |
| value | TEXT | 结果值 |
| improvement | TEXT | 提升幅度 |
| date | DATE | 发生日期 |

## 4.3 AchievementEvent

### 结构

```json
{
  "id": "ach_001",
  "type": "FIRST_MARATHON",
  "title": "人生首马",
  "activity_id": "activity_001",
  "date": "2023-10-15",
  "score": 100,
  "icon": "star",
  "description": "完成第一次42.195公里挑战"
}
```

### 字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | UUID | 成就 ID |
| type | TEXT | 成就类型 |
| title | TEXT | 显示标题 |
| activity_id | UUID | 关联 Activity |
| date | DATE | 发生时间 |
| score | INTEGER | 排序分值 |
| icon | TEXT | 图标 |
| description | TEXT | 描述 |

## 4.4 MemoryItem

### 结构

```json
{
  "id": "mem_001",
  "race_id": "race_001",
  "activity_id": "activity_001",
  "type": "photo|story|track",
  "path": "storage/...",
  "metadata": {}
}
```

### 字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | UUID | 记忆项 ID |
| race_id | UUID | 关联赛事 |
| activity_id | UUID | 关联 Activity |
| type | TEXT | 类型 |
| path | TEXT | 文件路径 |
| metadata | JSON | 扩展信息 |

## 4.5 CareerSnapshot

### 用途

给 AI 消费的结构化上下文。

### 字段建议

| 字段 | 说明 |
| --- | --- |
| id | 快照 ID |
| generated_at | 生成时间 |
| content | JSON 内容 |

### 建议内容

- summary
- latest
- primary_sport
- major_achievements
- trend
- representative_memories

---

# 5. API 设计

## 5.1 设计原则

- 一个接口对应一个业务能力
- 返回值以结构化 JSON 为主
- 前端不得自行补齐核心事实
- 所有详情跳转依赖 `activity_id`

## 5.2 Overview API

```http
GET /api/career/overview
```

### 返回示例

```json
{
  "summary": {
    "career_start_year": 2018,
    "activity_count": 236,
    "race_count": 12,
    "pb_count": 4,
    "achievement_count": 18,
    "memory_count": 3,
    "covered_city_count": 18,
    "total_distance_km": 1706.4
  },
  "hero_banner": {
    "mode": "photo",
    "activity_id": "123",
    "race_id": "race:123",
    "title": "都江堰马拉松",
    "subtitle": "2026-03-22 · 成都 · 跑步",
    "sport": "running",
    "sport_label": "跑步",
    "event_date": "2026-03-22",
    "city": "成都",
    "country": "中国",
    "distance_display": "42.20 km",
    "duration_display": "03:28:16",
    "badges": ["马拉松", "PB"],
    "media": {
      "has_photo": true,
      "image_ref": "asset:memory:photo:race-123"
    },
    "art": {
      "text": "都江堰马拉松",
      "tone": "steel_blue",
      "style": "metallic_gradient"
    },
    "detail_link": {
      "activity_id": "123",
      "source": "career"
    }
  },
  "sport_totals": {
    "running_distance_km": 1200.5,
    "cycling_distance_km": 430.0,
    "walking_distance_km": 30.0,
    "hiking_distance_km": 45.9,
    "walking_hiking_distance_km": 75.9,
    "swimming_distance_km": 12.4,
    "strength_total_weight_kg": null,
    "strength_total_weight_status": "unavailable"
  },
  "career_stats": {
    "activity_count": 236,
    "race_count": 12,
    "pb_count": 4,
    "achievement_count": 18,
    "total_duration_seconds": 1260000,
    "covered_city_count": 18,
    "covered_country_count": 2,
    "active_year_count": 6,
    "longest_activity_distance_km": 42.2,
    "max_elevation_gain_m": 1650,
    "max_altitude_m": 3840
  },
  "best_pb": {
    "title": "半程马拉松 PB",
    "value_display": "1:42:30",
    "event_date": "2026-03-22",
    "detail_link": {
      "activity_id": "123",
      "source": "career"
    }
  }
}
```

### 字段规则

- `hero_banner.mode` 支持 `photo`、`title_art`、`empty`。
- 有安全照片引用时使用 `photo`；没有照片时使用 `title_art`。
- `image_ref` 只能是应用受控的逻辑引用，不得是本地绝对路径、`file://`、`storage_ref` 或原始文件路径。
- `strength_total_weight_kg` 只能在 Activity 存在可靠总重量字段时聚合；没有可靠来源时必须返回 `null`，并通过 `strength_total_weight_status` 表达 `unavailable` 或 `partial`。
- `max_altitude_m` 只能聚合未删除 Activity 的 canonical `max_alt_m`；前端不得从轨迹点自行计算最高海拔。
- Overview 统计卡展示最高海拔；`best_pb` 继续保留在 ViewModel 中供 PB 档案与其他下钻入口使用，并允许为 `null`。
- 所有可点击入口必须通过 `detail_link.activity_id` 回跳 Activity Detail。
- Overview API 不返回 raw FIT、points、track_json、file_path、SQLite schema 或本地路径。

## 5.3 Timeline API

```http
GET /api/career/timeline
```

### 参数示例

```json
{
  "sport": "all",
  "year": 2026
}
```

### 返回建议

按年份分组，节点包含：

- activity_id
- date
- title
- type
- sport
- achievement tags

## 5.4 Races API

```http
GET /api/career/races
```

### 参数示例

```json
{
  "sport": "running",
  "year": 2026
}
```

### 返回建议

```json
{
  "races": [
    {
      "id": "",
      "name": "",
      "type": "",
      "activity_id": ""
    }
  ]
}
```

## 5.5 PB API

草稿中出现了两种写法：

- `GET /api/career/personal-best`
- `GET /api/career/pb`

### 建议

实现时统一一个主路由，并保留另一个作为兼容别名，避免前后端对不齐。

### 返回示例

```json
{
  "running": {
    "marathon": {
      "value": "3:28:10",
      "activity_id": "xxx"
    }
  }
}
```

## 5.6 Achievement API

```http
GET /api/career/achievement
```

### 返回示例

```json
{
  "achievements": [
    {
      "type": "",
      "title": "",
      "date": ""
    }
  ]
}
```

## 5.7 Memory API

```http
GET /api/career/memory
POST /api/career/memory
```

### 说明

- GET：获取记忆列表
- POST：新增 / 绑定记忆项

## 5.8 AI Insight API

```http
POST /api/career/insight
```

### 请求示例

```json
{
  "type": "career_summary"
}
```

### 返回示例

```json
{
  "title": "",
  "summary": "",
  "highlights": []
}
```

---

# 6. 前端实现

## 6.1 页面结构

建议最少包含以下页面或等价路由：

```text
pages/career/
├── index.html
├── timeline.html
├── achievement.html
└── memory.html
```

## 6.2 组件清单

```text
components/career/
├── HeroBanner
├── OverviewStatsGrid
├── SeasonStructure
├── Timeline
├── RaceCard
├── PBCard
├── AchievementCard
├── MemoryGallery
└── AIInsightCard
```

## 6.3 首屏数据加载

建议优先加载：

1. Overview
2. Seasons / 年度结构
3. Timeline

随后按需加载：

- PB
- Achievement
- Memory
- AI Insight

## 6.4 状态管理

推荐单独建立 `Career Store`，统一维护：

```javascript
careerState = {
  summary: {},
  heroBanner: {},
  sportTotals: {},
  careerStats: {},
  bestPb: null,
  timeline: {},
  events: [],
  pb: [],
  achievement: [],
  memory: [],
  insight: {}
}
```

## 6.5 页面布局原则

- 首页以赛事记忆 Banner 为第一视觉
- 无照片时使用活动标题艺术字 fallback，不显示空图片框
- Banner 下方展示全量运动统计，不把赛事数 / PB 数 / 成就数作为唯一重点
- 年度结构放在统计区之后，作为继续浏览的组织入口
- 年度卡片只在 Overview 展示，覆盖后端返回的全部已有年份，使用中性年度标题和后端统计摘要，不对整个年份进行高光等级判断
- 赛事、PB、荣誉、记忆、足迹作为下钻页面或二级入口
- 移动端采用单列流式布局
- 长中文标题必须不溢出，不遮挡 Banner 信息
- 前端只渲染后端 ViewModel，不从标题、距离、配速或 FIT 字段推断事实
- 时间轴节点不能只靠颜色区分

## 6.6 视觉与交互

### Overview Banner

- `photo` 模式：使用安全逻辑图片引用作为背景，叠加暗角和渐变遮罩。
- `title_art` 模式：使用活动或赛事标题生成金属 / 冷光渐变艺术字。
- `empty` 模式：展示稳定空态，不出现 `undefined`、`NaN` 或空对象。
- Banner 上可叠加赛事名称、日期、城市/国家、运动类型、距离、成绩、PB/荣誉标签。
- Banner 点击回跳 Activity Detail。
- 不允许通过 CSS 背景引用本地绝对路径。

### 节点样式

- 普通赛事：圆点
- PB：奖杯
- 首次：星标
- 里程碑：火焰 / 强标识

### 跳转规则

点击任意赛事、成就、记忆项：

```text
career item
  ↓
Activity Detail
```

不得生成新的重复详情页。

---

# 7. 异常与边界

## 7.1 无 Activity 数据

Overview 展示稳定空态：

- Banner 使用 `empty` 模式。
- 统计卡显示 0、待生成或暂无可靠数据。
- 不报错，不显示 `undefined`、`NaN` 或空 JSON。

## 7.2 无赛事数据

可以展示基础生涯，不报错。

建议文案：

> 还没有识别到正式赛事，继续同步运动记录后，你的运动生涯将在这里生成。

Overview Banner 不得伪装成赛事；应以普通 Activity 展示“运动记忆”。

## 7.3 无赛事照片

不阻塞 Overview。

- 有赛事但无照片：使用赛事标题生成 `title_art` Banner。
- 无赛事但有普通 Activity：使用代表活动标题生成 `title_art` Banner。
- 不返回本地图片路径。
- 不渲染空照片卡或破图。

## 7.4 数据冲突

如果同一 Activity 同时命中多个规则：

- 优先保留置信度高的结果
- 其余保留为候选，不进入主时间轴

## 7.5 重复导入

按 `activity_id` 去重。

## 7.6 Resolver 失败

Resolver 失败时：

- 保留 Activity
- 不影响运动记录主流程
- 允许后续重新解析

## 7.7 图片缺失

Memory Gallery 必须允许无图状态。

可仅展示故事与轨迹，不因图片缺失阻塞页面。

Overview Banner 缺图时走标题艺术字 fallback。

## 7.8 AI 不可用

AI 失败时，页面降级为基础统计与历史事件展示。

---

# 8. 缓存、性能与安全

## 8.1 缓存策略

- 一级缓存：内存，用于页面切换
- 二级缓存：本地数据库，如 SQLite
- AI 缓存：单独的 `career_ai_cache`

## 8.2 性能目标

文档目标支持：

- 20 年运动年限
- 5000+ Activity
- 500+ 赛事
- 10000+ 照片

## 8.3 渲染策略

- Timeline 使用虚拟列表
- Memory 使用懒加载
- 图片优先缩略图

## 8.4 安全原则

- 本地优先
- 不默认上传云端
- 不默认分享
- AI 只接收 snapshot

---

# 9. 测试与验收

## 9.1 测试范围

### 功能测试

- 赛事识别
- 时间轴展示
- PB 识别
- Achievement 识别
- Memory 展示
- AI Insight 生成

### 数据测试

- Activity 追溯性
- 去重逻辑
- 置信度处理
- 重复导入处理

### UI 测试

- Desktop / Mobile 布局
- Empty / Partial / Error State
- 节点交互与跳转

### AI 输出测试

- 不编造成绩
- 不直接读原始数据
- JSON 可解析

## 9.2 系统级验收标准

| 编号 | 标准 |
| --- | --- |
| AC-001 | 不影响现有运动记录 |
| AC-002 | 所有数据可追溯 Activity |
| AC-003 | AI 无法修改事实数据 |
| AC-004 | 支持离线运行 |
| AC-005 | 模块可独立关闭 |

---

# 10. 开发拆解

## 10.1 Phase 0：架构准备

周期：3-5 天

任务：

- 创建 `career` 模块
- 建立基础数据模型
- 建立 Resolver 框架
- 建立 Career 页面入口

## 10.2 Phase 1：赛事档案

周期：1-2 周

任务：

- 实现 Race Resolver
- 实现赛事分类
- 实现 `GET /api/career/races`
- 完成 Timeline 基础卡片

## 10.3 Phase 2：首页与时间轴

周期：2 周

任务：

- Career Overview
- Timeline
- Race Card

## 10.4 Phase 3：荣誉与记忆

周期：2 周

任务：

- Achievement Wall
- Memory Gallery

## 10.5 Phase 4：AI 能力

周期：1-2 周

任务：

- `ai_snapshot`
- `POST /api/career/insight`
- OpenClaw / AI 接入

---

# 11. 术语表

| 术语 | 说明 |
| --- | --- |
| Activity | 原始运动记录，唯一事实源 |
| RaceEvent | 赛事语义事件 |
| PB | Personal Best，个人最佳成绩 |
| Achievement | 运动里程碑 |
| Memory | 图像、故事、轨迹等记忆资产 |
| Snapshot | 给 AI 消费的结构化摘要 |
| Resolver | 语义识别与转换层 |

---

# 12. 交付结论

ACS 的开发实现目标不是“再做一个运动列表”，而是建立一层长期稳定的运动生涯组织能力。

开发团队需要始终遵守三条主线：

1. **Activity 单一事实源**
2. **Resolver 负责语义**
3. **AI 只消费 Snapshot**

只要这三条不变，ACS 后续可以持续扩展到：

- 更完整的年度总结
- 更丰富的记忆组织
- 更强的 AI 生涯叙事
- 更稳定的本地运动知识资产
