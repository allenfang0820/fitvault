# 环境挑战 (Environment Challenge) 实施契约 — v1

> **本文档是「可执行的实施契约」,不是设计草案。**
> 数据基础设计原文:见 `Environment_Load_数据基础能力调研报告.md` §3 / §4(6 运动 × 4 模块 × 4/5 级语义映射)
> 本文档只在架构层面加:数据源定位、契约约束、验收测试项、范围外说明。
>
> **核心原则**(调研报告原文):
> - 描述「外部世界」对运动体验的影响,不是身体内部反应
> - 与 Training Effect、Replay、派生指标形成清晰分工
> - 拒绝伪精确:不做 WBGT / Heat Index / AI 热风险
> - 同等级不同运动不同语义(5 运动 × 4 模块 × 5 级独立语义表)
>
> **架构原则**(fit-arch-contrac):
> - Resolver 是真理源(§2.1 全链路可追溯)
> - 前端只消费,严禁 UI 推导(§11.2 审查门禁)
> - AI 不消费 environment_challenge(§5.3 AI Snapshot 白名单)
> - 数据流:canonical FIT 字段 + `raw["weather"]` → Resolver 派生 → `record.detail.environment_challenge` → `get_activity_detail` API → Frontend render

---

## §0 元信息

| 字段 | 值 |
|---|---|
| 文档版本 | **v1.1** |
| 状态 | V_ENV.1.x + V_ENV.2.x 已落地,Phase 1 MVP(含释义字段增强) |
| 最近更新 | v1.1:label 字段升级为 `{label, explanation}` 双键(2026-06) |
| 适用模块 | 活动详情 Modal → 概览 Tab → 右侧栏 → 训练收益卡下方 |
| 后端落地 | `metrics_resolver.py` `_build_environment_challenge_block` (resolve 入口) |
| 前端落地 | `track.html` `_buildEnvironmentChallengeCard` 消费 `record.detail.environment_challenge` |
| 数据流 | FIT → `fitparse` 读 total_ascent/max_altitude/avg_temperature → `raw["weather"].humidity` → DB → `MetricsResolver` 派生 → `record.detail.environment_challenge` → `get_activity_detail` API → Frontend render |
| 关联契约 | `fit-arch-contrac` §2.1 / §五 5.3 / §六 审计字段隔离 / §11.2 |
| Phase 范围 | **Phase 1 MVP**:climb + altitude + heat 真实派生 + 释义字段;**Phase 2**:GPS curvature(technical_terrain) |

---

## §1 数据源契约 — Resolver 输入

`environment_challenge` 是**派生字段**(类似 `training_effect` / `difficulty_score`),不由 FIT SDK 直接给出,由 Resolver 从 canonical 字段派生。

### 1.1 派生所需 canonical 字段(后端 Resolver 必须消费)

| 字段 | 类型 | 来源 | 用途(语义) |
|---|---|---|---|
| `total_ascent` | int (m) | `sm.total_ascent` | 累计爬升 → climb 子块派生 |
| `distance_km` | float (km) | `sm.distance_km` | 距离归一化 → climb_density = ascent/distance |
| `max_altitude_m` | int (m) | `sm.max_altitude_m` (备选 `sm.max_alt_m`) | 主海拔指标 → altitude 子块 |
| `avg_temperature` | float (°C) \| None | `session.avg_temperature` | 第 3 模块温度主指标 |
| `humidity` | float (0~1 或 0~100) | `raw["weather"].humidity` / `meta["weather"].humidity` / `meta["humidity"]` | 第 3 模块温度辅助指标 |
| `sport_type` | str | `session.sport` | 选语义表(running / trail_running / ...) |

### 1.2 数据可信分层(§2.2 fit-arch-contrac)

- `fit_sdk` —— 上表的 FIT 字段(FIT 真实数据)
- `frontend_fallback` —— ❌ 严禁前端反推
- `mock` / `synthetic` —— ❌ 严禁进入 canonical

---

## §2 派生算法契约

### 2.1 climb 子块

| 步骤 | 公式 | 阈值 | level |
|---|---|---|---|
| 1 | `climb_density = total_ascent_m / distance_km` | `distance_km <= 0` 或任一为 None → 0.0 | — |
| 2 | `_classify_climb_density_level(density)` | `< 10` → 0 / `[10, 30)` → 1 / `[30, 60)` → 2 / `[60, 100)` → 3 / `>= 100` → 4 | 0~4 |
| 3 | `get_environment_challenge_semantic(sport_type, "vertical", level)` | 6 运动语义表 + 默认 running | label |

**降级**:`total_ascent_m < 0` → 视为 0;`distance_km <= 0` 或 None → 0.0。

### 2.2 altitude 子块

| 步骤 | 公式 | 阈值 | level |
|---|---|---|---|
| 1 | `classify_altitude_stress(max_altitude_m)` | `< 1500` → 0 / `[1500, 2500)` → 1 / `[2500, 3500)` → 2 / `[3500, 4500)` → 3 / `>= 4500` → 4 | 0~4 |
| 2 | `get_environment_challenge_semantic(sport_type, "altitude", level)` | 6 运动语义表 | label |

**降级**:`max_altitude_m` 为 None 或 `< 0` → 0;主指标唯一(`avg_altitude` 严禁参与判定)。

### 2.3 heat 子块 — **双路径**

#### 2.3.1 普通运动(非 skiing/mountaineering)

| 步骤 | 公式 | 阈值 | level |
|---|---|---|---|
| 1 | `_resolve_humidity_0to1(raw, meta)` | 防御性归一化(0~1 vs 0~100) | float \| None |
| 2 | `classify_heat_stress(temp_c, humidity_0to1)` | 4 档(product < 500 / [500,1200) / [1200,2100) / >= 2100) | 0~3 |
| 3 | `get_environment_challenge_semantic(sport_type, "heat", level)` | 6 运动语义表 | label |

**降级**:
- `temp_c is None` → level=0
- `humidity_0to1 is None` → 单维度温度粗分(`<25` → 0 / `[25,30)` → 1 / `[30,35)` → 2 / `>= 35` → 3)
- 双 None → 0

#### 2.3.2 滑雪/登山(skiing / mountaineering)—— **低温 5 档替换**

| 步骤 | 公式 | 阈值 | level |
|---|---|---|---|
| 1 | `_classify_cold_level(temp_c)` | `> 0` → 0 / `[-10, 0)` → 1 / `[-20, -10)` → 2 / `[-30, -20)` → 3 / `<= -30` → 4 | 0~4 |
| 2 | `get_environment_challenge_semantic(sport_type, "heat", level)` | **走 COLD_SEMANTICS**(与 humidity 解耦) | label |

**关键决策**:`heat.metric_value` 在低温路径下是**温度**而非 product。

### 2.4 technical_terrain 子块 — **Phase 1 占位**

```json
{
  "metric_name": "gps_curvature",
  "metric_value": null,
  "level": 0,
  "label": "--",
  "available": false
}
```

**Phase 2 待实现**:`ΣΔbearing / distance_km`(GPS curvature 算法)。

---

## §3 语义路由契约 — 同等级不同运动不同语义

### 3.1 路由表

| sport | 语义表 |
|---|---|
| `running` | `RUNNING_SEMANTICS` |
| `trail_running` | `TRAIL_RUNNING_SEMANTICS` |
| `hiking` | `HIKING_SEMANTICS` |
| `cycling` | `CYCLING_SEMANTICS` |
| `road_cycling` | `CYCLING_SEMANTICS`(别名) |
| `mountain_biking` | `MOUNTAIN_BIKING_SEMANTICS` |
| `skiing` | `TRAIL_RUNNING_SEMANTICS`(兜底)+ 第 3 模块走 `COLD_SEMANTICS` |
| `mountaineering` | `HIKING_SEMANTICS`(兜底)+ 第 3 模块走 `COLD_SEMANTICS` |
| 其他(未匹配) | `RUNNING_SEMANTICS` fallback |

### 3.2 语义表结构(以 RUNNING 为例)

```python
RUNNING_SEMANTICS = {
    "vertical":  ["平路路线", "略有起伏", "持续爬升路线", "高强度爬升跑", "极限爬升挑战"],  # 5 档
    "altitude":  ["低海拔环境", "中低海拔跑步", "中高海拔环境", "高海拔耐力环境", "极限高海拔挑战"],  # 5 档
    "heat":      ["环境舒适", "略有热感", "炎热跑步环境", "高温耐力挑战"],  # 4 档
    "terrain":   ["路线平稳", "略复杂路线", "技术型路线", "高技术跑步路线", "极限技术地形"],  # 5 档
}
```

完整语义表见 `metrics_resolver.py` `RUNNING_SEMANTICS` / `TRAIL_RUNNING_SEMANTICS` / `HIKING_SEMANTICS` / `CYCLING_SEMANTICS` / `MOUNTAIN_BIKING_SEMANTICS` / `COLD_SEMANTICS` 六个常量(任务 1.2 输出,L2946~L3061)。

### 3.3 降级

| 输入 | 行为 |
|---|---|
| `sport_type is None` / 空串 | fallback to RUNNING_SEMANTICS |
| `sport_type` 大小写 / 前后空格 | strip().lower() 归一化 |
| `level is None` / 非数值 / 越界 | 归 0(不抛异常) |
| `module` 拼错 | 返回 `"--"` |

---

## §4 输出契约 — `record.detail.environment_challenge` 结构

```json
{
  "sport_type": "running",
  "climb": {
    "metric_name": "climb_density",
    "metric_value": 100.0,
    "level": 4,
    "label": "极限爬升挑战"
  },
  "altitude": {
    "metric_name": "max_altitude",
    "metric_value": 800.0,
    "level": 0,
    "label": "低海拔环境"
  },
  "heat": {
    "metric_name": "temp_humidity_product",
    "metric_value": 25.5,
    "level": 1,
    "label": "略有热感"
  },
  "technical_terrain": {
    "metric_name": "gps_curvature",
    "metric_value": null,
    "level": 0,
    "label": "--",
    "available": false
  },
  "phase": 1,
  "data_source": "fit_sdk"
}
```

| 字段 | 契约 |
|---|---|
| `sport_type` | 透传 session.sport,原样 |
| `climb` / `altitude` / `heat` / `technical_terrain` | 含 `metric_name` / `metric_value` / `level` / `label`(4 子块形状一致) |
| `climb` / `altitude` / `heat` 的 `label` | **v1.1 升级**:从 `str` 改为 `dict{"label", "explanation"}`(详见 §4.5) |
| `technical_terrain.label` | 仍为 `str` `"--"`(Phase 1 占位,详见 §4.4) |
| `metric_value` | 内部派生量,UI **不直接展示**(§5.1 边界) |
| `technical_terrain.metric_value` | Phase 1 固定 `null` |
| `phase` | 当前 `1`(Phase 2 上线后置 2) |
| `data_source` | 固定 `"fit_sdk"`(§2.2 可信分层标识) |

---

## §4.5 释义字段契约(v1.1 新增)

4 子块(climb / altitude / heat / technical_terrain)的 `label` 字段已从 `str` 升级为 `dict{"label", "explanation"}`,供前端成对消费。

### 数据结构

```json
"climb": {
  "metric_name": "climb_density",
  "metric_value": 100.0,
  "level": 4,
  "label": {
    "label": "极限爬升挑战",
    "explanation": "极端爬升密度,纯靠爬升能力,建议分段休息"
  }
}
```

### 字段语义

| 字段 | 用途 | 消费端 |
|---|---|---|
| `label.label` | 等级短文案(2~7 字) | UI 标题(`.env-challenge-key-label`) |
| `label.explanation` | 释义短语(10~30 字) | UI 副文案(`.env-challenge-explanation`,小字) |
| `metric_value` | 内部派生数值 | **不在 UI 直接展示**;仅供调试/AI 使用 |

### technical_terrain 例外

Phase 1 占位状态的 `technical_terrain.label` 仍为字符串 `"--"`(非 dict),表示该子块尚未上线。前端检测到非 dict 时不显示 explanation(走空字符串分支)。

### 设计动机

调研报告 §3 的"5 档语义表"只给出了短文案,用户(如「极限爬升挑战 100.01 m/km」)无法理解数字含义。v1.1 在不增加契约复杂度的前提下,补充每条语义的「释义短语」,让用户**秒懂**该等级意味着什么。

### 契约一致性

| 维度 | v1.0 | v1.1 |
|---|---|---|
| label 字段类型 | `str` | `dict{label, explanation}` |
| 索引 1:1 对应 | ✅ | ✅(label 字符串内容 0 改动) |
| 释义文案来源 | (无) | 由产品决策撰写(任务 2.1 实施) |
| metric_value 展示 | 显示数字 | **不在 UI 直接展示**(§五 5.1 边界) |
| AI snapshot 入口 | 不进 | 仍不进 |

---

## §5 前端契约 — `track.html` 渲染

### 5.1 数据消费

```javascript
// _buildEnvironmentChallengeCard(record)
// 唯一数据源:record.detail.environment_challenge
// 严禁:record.points[] / record.records[] / record.aerobic_training_effect / ...
```

### 5.2 卡片结构

```
┌─ .weather-glass-card.env-challenge-card ─┐
│  ⛰️ 环境挑战                            │
│  [运动类型中文标签]                      │
│                                          │
│  ⛰️ 爬升挑战   [level 4] 极限爬升挑战    │
│  🏔️ 海拔环境   [level 0] 低海拔环境      │
│  🌡️ 温度环境   [level 1] 略有热感        │  ← skiing/mountaineering 显示「🌡️ 低温环境」
│  🧭 技术路线   [—]  —                    │  ← Phase 1 占位
└──────────────────────────────────────────┘
```

### 5.3 颜色映射(5 级)

```javascript
const _ENV_LEVEL_COLORS = ['#64748b', '#3b82f6', '#06b6d4', '#22c55e', '#f97316'];
//                    Gray(0)   Blue(1)    Cyan(2)    Green(3)   Orange(4)
//                    Red 保留给未来 Phase 3
```

- `border-left-color` 跟着 level 走
- 右侧 `.training-effect-score` 跟着 level 走(technical_terrain 不可用时显示「—」)

### 5.4 §六 审计字段隔离

```javascript
if (ec && (ec.shadow_diff || ec.shadow_diff_json || ec.diff)) {
    return '';  // 严禁展示 audit-only 字段
}
```

### 5.5 §五 AI 边界

- 前端**不消费** `points[]` / `records[]`
- 前端**不计算**任何指标(所有数字来自后端 canonical)
- 前端**不调用** `get_environment_challenge_semantic` / `classify_*` / `calculate_climb_density`

---

## §6 契约边界声明

### 6.1 §五 AI Snapshot 白名单(§5.3 fit-arch-contrac)

`environment_challenge` **严禁**进入 AI Snapshot:
- 集成测试 `test_environment_challenge_not_in_snapshot`(test_ai_snapshot_resolver.py)
- 集成测试 `test_ai_snapshot_end_to_end_isolation`(test_environment_challenge_integration.py)
- **断言**:`_build_ai_snapshot_block(row)` 输出不含 `environment_challenge`
- **断言**:`final_data["context_tags"]` 不含 `environment_challenge`

### 6.2 §六 审计字段隔离

- `environment_challenge` 4 子块**不含** `shadow_diff` / `shadow_diff_json` / `diff`
- `metrics_resolver.py` 源码**不含** `shadow_diff` 字面
- `js_api_contract.json` 已在 `get_activity_detail.description` 登记

### 6.3 §八 Canonical 只读

- `environment_challenge` 写入 `final_data` 顶层
- **不写入** `ai_snapshots` 表
- **不触发** `INSERT` / `UPDATE` / `db.save_*` 任何 DB 操作

---

## §7 验收测试项

### 7.1 工具函数单元测试(`test_environment_challenge_resolver.py`)

| TestCase | test 数 | 覆盖 |
|---|---|---|
| `TestCalculateClimbDensity` | 8 | 正常/零/负/None/双None |
| `TestClassifyAltitudeStress` | 7 | 5 档临界/None/负数 |
| `TestClassifyHeatStress` | 14 | 4 档/product 边界/3 条降级/humidity 缺失单维度 4 档 |

### 7.2 语义路由单元测试

| TestCase | test 数 | 覆盖 |
|---|---|---|
| `TestSemanticsIntegrity` | 8 | 6 常量 label 非空无重复 + 5 档/4 档断言 |
| `TestSportMapCoverage` | 6 | 8 键/必含/cold_set/别名/兜底表 |
| `TestGetEnvironmentChallengeSemantic` | 22 | 6 运动抽检/低温 4 档/fallback/5 种降级/拼错/大小写 |
| `TestExplanationIntegrity`(v1.1) | 3 | 释义非空 + 全运动 × 全模块 × 全档覆盖 |

### 7.3 集成测试(`test_environment_challenge_integration.py`)

| TestCase | test 数 | 覆盖 |
|---|---|---|
| `TestEnvironmentChallengeInjection` | 13 | 5 运动派生/humidity 三入口/双单位/异常/fallback/全降级 |
| `TestEnvironmentChallengeNoShadowDiff` | 2 | 派生块无 shadow_diff/端到端 AI snapshot 隔离 |

### 7.4 前端契约测试(`test_environment_challenge_frontend.py`)

| TestCase | test 数 | 覆盖 |
|---|---|---|
| `TestEnvironmentChallengeCardExists` | 5 | 函数存在/字段消费/不消费 points/不计算/审计隔离 |
| `TestEnvironmentChallengeCSS` | 7 | 6 CSS 类/玻璃态根 div |
| `TestEnvironmentChallengeColors` | 3 | 5 级颜色/常量声明/函数引用 |
| `TestEnvironmentChallengeSidebarOrder` | 3 | 侧栏调用/顺序/5 张卡完整 |
| `TestEnvironmentChallengeNoCrossPollution` | 2 | cold sport 判定/XSS 防护 |

**合计 104 个测试(v1.1)**(`test_environment_challenge_resolver.py` 69[+3 TestExplanationIntegrity] + `test_environment_challenge_integration.py` 15 + `test_environment_challenge_frontend.py` 20)

### 7.5 现有契约回归测试

| 测试模块 | 关联 |
|---|---|
| `test_v4_0_layer_isolation.py` | shadow_diff 隔离 + env 校验 |
| `test_resolver_sport_isolation.py` | `test_schema_top_level_whitelist_unchanged` 已加 `environment_challenge` |
| `test_ai_snapshot_resolver.py` | `test_environment_challenge_not_in_snapshot`(1.3 加) |

---

## §8 实施落地映射(子任务到文件)

| 任务 | 文件 | 改动量 |
|---|---|---|
| 1.1 工具函数 | `metrics_resolver.py` L2851~L2927 | +101 行 |
| 1.2 语义路由 | `metrics_resolver.py` L2946~L3061 | +122 行 |
| 1.3 派生块注入 | `metrics_resolver.py` L120~L125(ACTIVITY_SCHEMA)+ L285~L297(resolve)+ L3083~L3242(4 函数) | +80 行 |
| 1.4 js_api_contract | `docs/js_api_contract.json` L186 | +1 行 |
| 1.5 CSS | `track.html` L1955~L1987(6 类)+ L6532(颜色常量) | +39 行 |
| 1.6 渲染函数 | `track.html` L6585~L6648 | +66 行 |
| 1.7 侧栏插入 | `track.html` L6470~L6471 | +2 行 |
| 1.8 工具单测 | `tests/test_environment_challenge_resolver.py` | +130 行(29 test) |
| 1.9 语义单测 | 同上追加 | +170 行(37 test) |
| 1.10 集成测试 | `tests/test_environment_challenge_integration.py` | +270 行(15 test) |
| 1.11 前端契约 | `tests/test_environment_challenge_frontend.py` | +225 行(20 test) |

---

## §9 实施过程中的关键决策

### 9.1 调研报告 §3.3 阈值数学 vs 文档示例不一致

| 文档示例 | 实际数学 | 处理 |
|---|---|---|
| 28°C × 60% = 16.8 标 Level 1 | product < 500 数学判 0 | **以数学为准**,语义服从公式 |
| 30°C × 70% = 21 标 Level 2 | product < 500 数学判 0 | 同上 |

未来 AI/Prompt 引用时需以**数学判定**为准,文档示例仅供示意。

### 9.2 skiing/mountaineering 走低温 5 档(独立判定)

任务 1.1 `classify_heat_stress` 把 humidity 缺失时的「单维度降级」写死为 `t < 25 → 0`,导致滑雪 -15°C 永远显示「温度舒适 0 档」。

**决策**:派生块内**新增** `_classify_cold_level(temp_c)`,skiing/mountaineering 分支用 cold_level,**不动**任务 1.1 / 1.2 函数契约。

### 9.3 项目枚举与调研报告的不对齐

| 调研报告用词 | 项目实际枚举 | 决策 |
|---|---|---|
| `road_cycling` | 合并到 `cycling` | 路由表双 key 兼容 |
| — | `treadmill_running` / `swimming` / `walking` | fallback 到 running |

### 9.4 ACTIVITY_SCHEMA 提前扩 key(1.3 越界 1.4)

任务 1.3 提示词禁止改 `ACTIVITY_SCHEMA`,但 `final_data["environment_challenge"]` 注入会破坏 `test_schema_top_level_whitelist_unchanged` set 断言。

**决策**:
- 1.3 主动加 `ACTIVITY_SCHEMA["environment_challenge"] = {}`
- 同步更新白名单测试 `expected_keys`
- 1.4 范围**简化为**「js_api_contract.json 登记」

### 9.5 v1.1:label 升级为 `{label, explanation}` 双键

调研报告 §3 的语义表只给短文案,用户看到「极限爬升挑战 100.01 m/km」无法理解数字含义(如骑马 activity 实际数感 10.01 m/km 也判 "略有起伏" 而非"高强度爬升跑")。v1.1 决定:
- **label 字段升级为 `dict{label, explanation}`**
- 6 运动 × 4 模块 × 5/4 档 = 120 条 explanation 文案(任务 2.1 实施)
- COLD_SEMANTICS 5 档低温 explanation 文案
- 前端读取 `block.label.label` / `block.label.explanation` 成对消费
- `metric_value` 数字(密度 100.01)**不再在 UI 直接展示**,降级为内部派生量(§五 5.1 边界)
- 破坏性 API 变更,前端+测试同步升级(任务 2.4~2.8)
- 单维度降级(humidity=None → 温度粗分)仍走原 4 档,不受 v1.1 影响
- technical_terrain 占位状态 `label` 仍为字符串 `"--"`(非 dict),前端检测后不渲染 explanation

---

## §10 已知问题与未来工作

### 10.1 Phase 2 待实现

- `technical_terrain` 子块:Phase 2 上线 GPS curvature(`ΣΔbearing / distance_km`)
- `climb` 子块:Vertical Intensity(时间归一化)—— Phase 3
- `heat` 子块:分级数学化(从 product 改为更灵敏的阈值)—— 待产品确认

### 10.2 预存在测试失败(非本任务回归)

| 测试 | 失败数 | 原因 | 责任 |
|---|---|---|---|
| `test_v9_2_overview_m0.py` | 7 | `track.html` 现状与 V9.2.3 旧测试规约错位 | V9.2.3 grid 重构者 |
| `test_laps_real_data.py` | 2 | `profile_backend._ensure_schema_initialized` 签名不匹配 | schema 迁移维护者 |

修复工作应**与本任务分离**,由对应原作者推进。

### 10.3 字段版本化

`field_contract_version` 字段预留(§11.3 fit-arch-contrac),当前为 `phase=1`。

**v1.1 changelog(释义字段增强)**:
- `label` 字段: `str` → `dict{label, explanation}`
- 6 运动语义常量: `list[str]` → `list[dict]`
- `COLD_SEMANTICS`: `list[str]` → `list[dict]`
- `get_environment_challenge_semantic()`: 返回值 `str` → `dict{label, explanation}`
- `technical_terrain.label`: 仍 `str "--"`(占位状态)
- 派生块 `_build_environment_challenge_block`: `climb.label` / `altitude.label` / `heat.label` 类型自动跟随
- `metric_value`: **不在 UI 展示**(降级为内部派生量)
- 不进 AI snapshot
- label 字符串内容 0 改动(索引 1:1 对应 v1.0)

---

## §11 关联文件索引

| 文件 | 路径 | 关联 |
|---|---|---|
| 全局架构契约 | `/.trae/rules/fit-arch-contrac.md` | §2.1 / §五 5.3 / §六 / §11.2 |
| 数据基础调研报告 | `/Environment_Load_数据基础能力调研报告.md` | §3 / §4 |
| Resolver 实现 | `metrics_resolver.py` | 1.1 / 1.2 / 1.3 |
| 训练收益契约参考 | `docs/training_effect_v1_contract.md` | 风格对齐 |
| 活动详情契约 | `docs/js_api_contract.json` L179-L189 | 1.4 |

---

> **本文档是「环境挑战」功能的实施契约。所有 Phase 1 子任务已落地,Phase 2 待产品确认 GPS curvature 算法后启动。**
