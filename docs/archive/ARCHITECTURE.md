# 脉图（FitVault）架构总纲

> Version: 2026-Q2 Canonical Architecture
>
> 项目定位：本地 AI 运动外挂（Local AI Sports Copilot）
>
> 核心原则：轻量、本地优先、可解释、可演进、拒绝平台化膨胀

---

# 1. 项目愿景（Vision）

脉图不是一个传统意义上的运动平台。

它的目标不是：

- 社交平台
- SaaS 数据中台
- 企业级数据仓库
- Garmin 替代品
- 云端 AI Agent 平台

脉图真正的定位是：

> 一个运行在用户本地的 AI 运动外挂。

核心价值：

- 导入运动数据
- 建立可信运动档案
- 提供结构化 AI 解读
- 形成长期运动画像
- 为 AI 提供稳定语义上下文

因此：

脉图不是“数据库产品”。
而是：

> AI 的运动上下文引擎（AI Context Engine for Sports Data）

---

# 2. 总体架构哲学

## 2.1 核心原则

项目长期坚持以下原则：

### 原则 1：本地优先（Local First）

所有核心能力必须：

- 可离线运行
- 不依赖云端服务
- 不依赖第三方 API 存活
- 用户可完全掌控数据

因此：

- SQLite 是核心数据库
- FIT 文件是核心事实源
- AI 仅消费 snapshot
- 不做重型在线服务依赖

---

### 原则 2：FIT 为唯一事实源（FIT as Source of Truth）

所有活动数据最终必须能够回溯到：

- 原始 FIT 文件
- Garmin FIT SDK
- 原始 record/session/lap/message

禁止：

- 前端生成虚假指标
- AI 生成伪运动数据
- UI fallback 长期污染数据层
- synthetic 数据进入 canonical layer

因此：

系统内必须严格区分：

| 类型 | 定义 |
|---|---|
| fit_sdk | Garmin SDK 解析真实数据 |
| frontend_fallback | UI 临时推导数据 |
| mock | 测试数据 |
| synthetic | AI 生成数据 |

其中：

- canonical 层只接受可信数据
- resolver 可以存在降级逻辑
- UI 可以做展示 fallback
- AI 不允许写回 canonical 数据

---

### 原则 3：AI 只消费，不污染

AI 的职责：

- 解读
- 总结
- 分析
- 生成 narrative
- 生成 insight

AI 不负责：

- 修改原始数据
- 回写 metrics
- 生成结构化 canonical 字段
- 作为事实来源

因此：

AI 永远运行在：

> snapshot layer

而不是：

> canonical persistence layer

---

### 原则 4：拒绝平台化膨胀

明确不引入：

- Data Warehouse
- Kafka
- Event Bus
- Feature Store
- Runtime Orchestrator
- 微服务体系
- 云端计算节点
- SaaS 多租户架构
- GraphQL Federation
- 企业级权限系统

脉图是：

> 单用户、本地 AI 工具。

不是企业 BI 平台。

---

### 原则 5：一切新增能力必须回答一个问题

> OpenClaw 会真实使用它吗？

如果答案是否定：

不进入核心架构。

---

# 3. 当前标准架构（Canonical Architecture）

当前标准架构收敛为：

```text
FIT FILES
    ↓
fit_engine
    ↓
resolver
    ↓
SQLite Canonical DB
    ↓
ai_snapshot
    ↓
OpenClaw / AI Layer
    ↓
Narrative / Insight / Radar / Trend
```

这是长期主架构。

禁止再横向扩展大型 subsystem。

---

# 4. 分层架构定义

# 4.1 Ingestion Layer（数据摄取层）

职责：

- 导入 FIT / GPX
- 文件扫描
- 文件同步
- 文件 hash
- 去重
- 原始 metadata 建立

核心原则：

- 不做复杂业务逻辑
- 不做 AI 分析
- 不做训练指标计算
- 不做 UI fallback

输入：

- FIT 文件
- GPX 文件

输出：

- raw parsed payload

核心模块：

```text
sync_local_fit_files
_parse_fit_activity_for_sync
fit file watcher
```

---

# 4.2 fit_engine（FIT解析引擎）

这是脉图最核心的基础设施之一。

职责：

- Garmin FIT SDK 解码
- record/session/lap/event 解析
- 保留 Garmin 原始语义
- 建立 canonical raw metrics

核心原则：

- 不做业务推断
- 不做 AI 解读
- 不做 UI 兼容
- 尽可能完整保留字段

fit_engine 是：

> 原始运动世界的翻译器。

不是分析器。

---

## fit_engine 输出层级

### Session Level

例如：

- total_distance
- total_timer_time
- total_elapsed_time
- total_calories
- avg_heart_rate
- max_heart_rate
- avg_speed
- avg_power
- total_ascent
- normalized_power
- training_effect

---

### Record Level

逐秒记录：

- timestamp
- position_lat
- position_long
- altitude
- heart_rate
- cadence
- power
- speed
- temperature

---

### Lap Level

用于：

- 圈分析
- 分段分析
- 配速变化
- AI 分段 narrative

---

## fit_engine 长期原则

### 必须保留：

- 原始 Garmin 字段
- 原始单位
- 原始时间语义
- 原始坐标

### 禁止：

- UI 推导字段混入
- AI 修正指标
- synthetic metrics
- 自动补全缺失值

---

# 4.3 Resolver Layer（语义解析层）

Resolver 是：

> 轻量语义转换层。

职责：

- 统一不同运动类型语义
- 生成展示友好字段
- 建立 AI 可读结构
- 补充轻量 metadata

Resolver 不负责：

- AI 推理
- 深度统计建模
- 数据仓库聚合
- 长链路推导

---

## Resolver 的典型职责

### 活动类型标准化

例如：

```text
trail_running
road_running
hiking
cycling
pool_swimming
open_water_swimming
```

---

### 区域解析

例如：

```text
中国 / 上海 / 浦东新区
日本 / 大阪 / 心斋桥
美国 / California / Irvine
```

基于：

```text
resolve_activity_region()
```

原则：

- 使用 session 起点坐标
- 中文优先
- fallback 英文
- 必须限流
- 必须随机请求间隔

---

### 标题解析

标题来源优先级：

```text
FIT 文件名
    ↓
FIT 原始 title
    ↓
activity type fallback
```

禁止 AI 自动命名污染 canonical title。

---

### 运动画像字段

例如：

- running_profile
- hiking_profile
- body_composition
- physiology
- training_focus

这些属于：

> resolver semantic layer

不是 AI narrative。

---

# 4.4 Canonical Persistence Layer

这是：

> 系统唯一可信数据层。

技术选型：

- SQLite

长期不升级：

- PostgreSQL
- ClickHouse
- ElasticSearch
- BigQuery

除非项目定位发生根本变化。

---

## Canonical DB 原则

### 只存可信数据

canonical database 内：

- 不允许 synthetic metrics
- 不允许 AI 结果回写
- 不允许 mock 污染生产数据

必须具备：

```text
source_type
is_mock
```

数据可信标记。

---

## 当前核心表

### activities

主活动表。

> **V9.4.4 字段审计**: 早期 §4.4 仅列 12 字段,与 V8.x~V9.4.4 实际 schema 严重脱节,违反 §六 "FIT → Resolver → DB → UI 字段契约必须长期维护" 原则。
> 本节已根据 DB 实际 schema 重写(28 + V9.4.4 新增 5 + laps/region/debug 5 = 38 字段)。
> 完整字段契约矩阵(UI → DB → Resolver → FIT SDK)见 [docs/field_contract_matrix.md](./docs/field_contract_matrix.md)。

#### 4.4.1 主活动字段(28 列,主表必需)

```text
id                  INTEGER   主键
filename            TEXT      文件名(原始)
file_name           TEXT      文件名(同 filename 兼容列)
file_path           TEXT      完整路径
file_mtime          REAL      文件 mtime(用于同步跳过)
file_size           INTEGER   文件大小(用于同步跳过)
title               TEXT      显示标题(_resolveDisplayTitle 真理源)
title_source        TEXT      'filename' / 'sport_name' / 'session_label' / 'file_name'
sport_type          TEXT      标准运动类型('running' / 'cycling' ...)
sub_sport_type      TEXT      FIT sub_sport 原始值
start_time          TEXT      起始时间(local)
start_time_utc      TEXT      起始时间(UTC ISO 8601)
start_lat           REAL      起点纬度
start_lon           REAL      起点经度
distance            REAL      距离(米,V8.x 统一单位,严禁改 km)
dist_km             REAL      距离(公里,_formatHeroValue 真理源)
duration            INTEGER   时长(秒,DB 端)
duration_sec        INTEGER   时长(秒,API 端同义字段)
avg_pace            REAL      平均配速(秒/公里)
calories            INTEGER   卡路里
gain_m              REAL      累计爬升(米)
total_descent_m     REAL      累计下降(米,V8.x 之后,设备原始值)
min_alt_m           REAL      最低海拔
max_alt_m           REAL      最高海拔
avg_hr              INTEGER   平均心率
max_hr              INTEGER   最高心率
avg_cadence         REAL      平均步频
avg_power           REAL      平均功率
normalized_power    REAL      标准化功率(NP)
swolf               INTEGER   SWOLF 游泳效率
source_type         TEXT      'fit_sdk' / 'frontend_fallback' / 'mock' / 'synthetic'(§2.2 分层)
is_mock             INTEGER   0/1 调试标记
deleted_at          TEXT      软删时间(§V4.0 +)
updated_at          TEXT      最后更新时间
device_name         TEXT      设备名(如 'Garmin Fenix 7')
is_race             INTEGER   0/1 是否比赛
is_event            INTEGER   0/1 是否事件活动
```

#### 4.4.2 V9.4.4 新增字段(圈速 + 训练收益,5 列)

```text
total_ascent         REAL     累计爬升(FIT 原始,lap 级透传到 detail)
total_descent        REAL     累计下降(FIT 原始,lap 级)
aerobic_training_effect    REAL   Firstbeat 有氧 TE(0.0~5.0,fitparse scale 0.1)
anaerobic_training_effect  REAL   Firstbeat 无氧 TE(0.0~5.0)
```

#### 4.4.3 圈速 / 曲线 / 分段 JSON 字段(5 列)

```text
laps_json            TEXT      圈速列表 JSON(§4.3 Resolver _normalize_laps 输出,每圈 11 字段)
hr_curve             TEXT      心率曲线(LTTB 采样,V9.x §指标 7)
speed_curve          TEXT      速度曲线
cadence_curve        TEXT      步频曲线
hr_zone_distribution TEXT      心率区间分布 JSON
advanced_metrics     TEXT      高级指标(TRIMP/Decoupling/VAM 等)JSON
shadow_diff_json     TEXT      §六 debug-only 审计字段,严禁进入 UI/AI Snapshot
```

#### 4.4.4 报告派生指标(7 列,V9.x 复盘用,后端 compute_report_metrics())

```text
up_count             INTEGER   累计爬升次数
down_count           INTEGER   累计下降次数
max_single_climb_m   REAL      单段最大爬升
difficulty_score     INTEGER   难度评分
report_metrics_version INTEGER  派生指标 schema 版本(§11.3 字段版本化)
avg_grade_pct        REAL      平均坡度
max_slope_pct        REAL      最大坡度
min_slope_pct        REAL      最小坡度
uphill_pct           REAL      上坡占比
downhill_pct         REAL      下坡占比
```

#### 4.4.5 地区解析字段(8 列,profile_backend 异步写入)

```text
region               TEXT      地区全路径
region_city          TEXT      城市
region_country       TEXT      国家
region_display       TEXT      地区显示字符串
region_status        TEXT      'pending' / 'success' / 'failed'
region_error         TEXT      错误信息
region_updated_at    TEXT      解析时间
region_attempt_count INTEGER   重试次数
```

#### 4.4.6 轨迹 / 天气字段(2 列)

```text
points_json          TEXT      逐秒轨迹精简版(展示用)
track_json          TEXT      完整逐秒轨迹(分析用,V9.x 与 points_json 二选一)
weather_json         TEXT      天气数据 JSON(运行时 API 注入)
```

#### 4.4.7 已废弃/合并字段(说明,不实现)

```text
activity_id          ✗ 实际字段是 id,旧文档误用 activity_id
sub_sport            ✗ 实际是 sub_sport_type
ascent               ✗ 实际是 gain_m
```

> 字段版本化: 未来引入 `schema_version` 字段(§11.3 字段版本化),用于 schema 演进检测。

### Debug-only / Audit-only 字段

`activities.shadow_diff_json` 是 MetricsResolver Shadow Layer 的差异审计字段。

契约定义：

| 属性 | 契约 |
|---|---|
| DB 字段 | `activities.shadow_diff_json` |
| API 字段 | `shadow_diff` |
| 字段性质 | debug-only / audit-only |
| 数据来源 | MetricsResolver Shadow Layer |
| 数据用途 | 仅用于 Resolver 与 Legacy 指标差异审计、调试、回归验证 |
| 常规 UI 展示 | 禁止进入常规活动列表、详情主展示、指标卡片、图表和用户可见业务展示 |
| AI Snapshot | 禁止进入 AI Snapshot、AI prompt、AI 分析上下文 |
| Canonical 指标 | 禁止参与 canonical 指标计算、排序、筛选、运动画像、雷达图、训练负荷计算 |
| 持久化格式 | JSON 字符串，反序列化后仅作为审计对象读取 |

强制边界：

- `shadow_diff_json` 可以在 DB 中持久化，用于可追溯审计。
- API 可以返回解析后的 `shadow_diff`，但调用方必须将其视为 debug-only 数据。
- 前端如需使用 `shadow_diff`，只能放入显式调试入口或开发者审计面板，不得默认展示给普通用户。
- AI Snapshot 白名单不得加入 `shadow_diff`、`shadow_diff_json`、`diff` 或任何等价字段。
- 任何新增消费点必须在本架构契约中登记，并明确标记 debug-only。

验收规则：

- 查询活动列表或活动详情时，`shadow_diff` 的存在不得影响任何业务字段展示。
- 构建 AI Snapshot 时，出现 `shadow_diff`、`shadow_diff_json`、`diff` 应视为契约违规。
- 修改 Resolver、入库或 API 返回逻辑时，必须验证 `shadow_diff_json` 仍不参与 canonical 数据路径。

---

### activity_records

逐秒轨迹记录。

---

### activity_laps

圈信息。

---

### ai_snapshots

AI 输入 snapshot。

注意：

不是 AI canonical database。

---

# 4.5 ai_snapshot Layer

这是整个 AI 架构最关键的一层。

其目标是：

> 将复杂运动数据压缩为 AI 可消费上下文。

AI 不应该直接读取：

- 原始 FIT
- 原始 records
- SQLite schema

AI 只应该读取：

> snapshot。

---

## snapshot 内容

包括：

### 基础摘要

例如：

```json
{
  "sport": "trail_running",
  "distance_km": 18.5,
  "duration": "2:14:22",
  "avg_hr": 152,
  "elevation_gain": 1260
}
```

---

### 结构化洞察

例如：

```json
{
  "pace_distribution": "front_fast_back_slow",
  "climb_efficiency": "high",
  "fatigue_pattern": "late_stage_drop"
}
```

---

### AI Narrative Context

例如：

- 最近训练趋势
- PB 变化
- 恢复状态
- 睡眠背景
- 训练负荷

---

## snapshot 原则

### 必须：

- 小
- 稳定
- 可解释
- token 可控

### 禁止：

- 全量 records 注入
- 巨型 JSON
- 无边界上下文
- AI 无限上下文堆积
- `shadow_diff`
- `shadow_diff_json`
- `diff`
- 任何 debug-only / audit-only 字段

---

# 4.6 AI Layer（OpenClaw）

AI 层的职责：

- narrative
- insight
- radar explanation
- trend summary
- achievement story
- training suggestion

AI 不是：

- 规则引擎
- 数据库
- canonical generator

---

## AI 输出类型

### Narrative

例如：

- “本次爬升能力明显强于近30日平均”
- “后半程心率漂移明显”
- “这是一次典型的高负荷越野跑”

---

### Trend

例如：

- VO2Max 长期变化
- HRV 恢复趋势
- 月跑量变化

---

### Achievement

例如：

- PB
- 首次百公里
- 比赛成绩
- 荣誉墙

---

## AI 长期原则

### AI 输出不可回写 canonical

AI 永远是：

> interpretation layer

不是事实层。

---

# 5. 前端架构

# 5.1 UI Philosophy

脉图 UI 原则：

- 信息密度高
- 专业运动风格
- AI insight 驱动
- 本地桌面工具感
- 不做社交 App 风格

---

# 5.2 当前主要页面

## 个人运动数据

核心入口。

包含：

- 活动列表
- 分页
- 筛选
- 基础统计

---

## 活动详情页

核心页面之一。

包含：

- 地图
- 轨迹
- 圈数据
- 心率
- 功率
- AI 解读
- 训练指标

---

## 轨迹分析工具

偏专业工具页。

用于：

- 轨迹回放
- 海拔分析
- GPS 检查
- 分段分析

---

## 雷达图系统

当前原则：

雷达图分析逻辑不能长期放在：

```text
main.py
```

未来应收敛为：

```text
radar_engine/
```

但仍然属于：

> lightweight analytics layer

不能演化为独立 analytics platform。

---

## 趋势指标页面（规划）

目标：

展示长期单指标变化。

例如：

- 跑量
- HRV
- 睡眠
- 训练负荷
- 配速
- 功率

原则：

- 轻量 trend engine
- 不做 data warehouse
- 不做 OLAP

---

## 荣誉墙（规划）

自动识别：

- 比赛
- PB
- 首次达成
- 长距离里程碑

形成：

> AI 体育生涯时间线

---

# 6. 数据契约（Data Contract）

脉图长期必须维护：

> FIT → Resolver → DB → UI 的字段契约。

这是系统稳定性的关键。

---

## 数据流

```text
FIT SDK Field
    ↓
fit_engine canonical field
    ↓
resolver semantic field
    ↓
database schema
    ↓
frontend ui model
    ↓
ai snapshot
```

---

## 数据契约原则

### 一切字段必须可追踪

任何 UI 字段都必须能追溯：

```text
UI → DB → Resolver → FIT SDK
```

---

### 严禁隐式推导

禁止：

- 前端偷偷计算
- AI 偷偷生成
- resolver 无来源推断

---

### 字段版本化

未来建议：

```text
field_contract_version
```

用于 schema evolution。

---

# 7. 性能原则

# 7.1 当前规模定位

脉图当前规模假设：

- 单用户
- 数千活动
- 本地 SQLite
- 本地 AI

因此：

不需要：

- 分布式系统
- 云端扩容
- 横向分片
- 流处理平台

---

# 7.2 优化优先级

优先：

1. FIT 导入稳定性
2. SQLite 查询效率
3. Snapshot token 控制
4. 前端渲染性能
5. 地图加载速度

而不是：

- 企业级高并发
- 微服务治理
- 大数据计算

---

# 8. 技术债治理

当前已识别技术债：

---

## 8.1 main.py 过大

问题：

- UI
- parser
- analytics
- radar
- persistence

存在耦合。

目标：

逐步拆分：

```text
fit_engine/
resolver/
radar_engine/
persistence/
ai_snapshot/
```

但：

必须保持轻量。

禁止 Java 企业化目录膨胀。

---

## 8.2 雷达图逻辑耦合

未来应形成：

```text
radar_engine/
```

负责：

- score normalize
- percentile
- dimension weighting
- sport profile

但不负责：

- AI narrative
- 大数据分析

---

## 8.3 UI fallback 污染风险

必须严格限制：

```text
frontend fallback
```

仅用于展示。

禁止写回 canonical。

---

# 9. 长期演进路线（Roadmap）

# Phase 1：可信数据层（进行中）

目标：

- FIT SDK 稳定化
- canonical schema
- source_type
- resolver 稳定
- 数据契约建立

---

# Phase 2：AI Snapshot 架构

目标：

- snapshot pipeline
- token 控制
- AI context engineering
- OpenClaw integration

---

# Phase 3：专业分析层

目标：

- radar engine
- trend engine
- fatigue analysis
- training structure analysis
- achievement engine

---

# Phase 4：AI 运动生涯系统

目标：

- 荣誉墙
- AI 生涯 narrative
- 长期训练画像
- AI 总结系统

---

# 10. 明确不做的事情（Non-Goals）

以下内容长期不进入脉图核心：

---

## 不做 SaaS 平台

不做：

- 多租户
- 企业团队
- 云账号系统
- 订阅系统

---

## 不做社交平台

不做：

- 关注
- 点赞
- 评论
- 动态流

---

## 不做企业 BI

不做：

- Data Lake
- Cube
- ETL 平台
- 企业报表系统

---

## 不做 AI Agent Runtime

不做：

- agent orchestration
- tool runtime
- workflow engine
- autonomous agent network

OpenClaw 是：

> 消费 snapshot 的 AI。

不是系统 runtime。

---

# 11. 最终架构收敛

脉图最终长期稳定架构：

```text
FIT / GPX
    ↓
fit_engine
    ↓
resolver
    ↓
SQLite canonical DB
    ↓
ai_snapshot
    ↓
OpenClaw
    ↓
Narrative / Radar / Trend / Achievement
```

系统长期只围绕：

- 可信运动数据
- AI 可读上下文
- 轻量专业分析
- 本地 AI 运动外挂

持续演进。

禁止架构失控。

---

# 12. 一句话定义脉图

> 脉图是一个基于 FIT 可信数据层的本地 AI 运动外挂，通过轻量语义解析与 AI Snapshot 机制，为 OpenClaw 提供稳定、可解释、长期可演进的运动上下文系统。
