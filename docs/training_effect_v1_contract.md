# 训练收益 (Training Effect) 实施契约 — v1

> **本文档是「可执行的实施契约」,不是设计草案。**
> 用户设计原文(8 运动 × 双维度 × 6 TE 范围)逐字保留;本文档只在架构层面加:数据源定位、契约约束、验收测试项、范围外说明。
>
> **核心原则**(用户原文):
> - TE 数值负责:训练刺激强度
> - 运动类型负责:训练意义翻译
> - 3.5 永远代表「有效训练刺激」;但跑步→提升耐力,骑行→提升持续输出,徒步→增强长距离体能
>
> **架构原则**(fit-arch-contrac):
> - Resolver 是真理源(§2.1 全链路可追溯)
> - 前端只消费,严禁 UI 推导(§11.2 审查门禁)
> - AI 不写回 canonical(§5.4 AI 边界)
> - 数据源:canonical FIT 字段 → Resolver 派生 → `record.detail.training_effect` → Frontend

---

## §0 元信息

| 字段 | 值 |
|---|---|
| 文档版本 | v1.2 |
| 状态 | V9.4.2 已锁定,旧设备兜底已删除 |
| 适用模块 | 活动详情 Modal → 右侧栏「训练收益」卡 |
| 后端落地 | `metrics_resolver.py` `build_training_effect` + `main.py` `_build_record_from_row` 透传 |
| 前端落地 | `track.html` `_buildTrainingBenefitCard` 消费 `record.detail.training_effect` |
| 数据流 | FIT → `fitparse` 读 219/218 → DB → `MetricsResolver` 查表 → `record.detail.training_effect` → `get_activity_detail` API → Frontend render |
| 关联契约 | `fit-arch-contrac` §2.1 / §五 / §5.4 / §5.5 / §11.2 |

---

## §1 数据源契约 — Resolver 输入

`training_effect` 是**派生字段**(类似 `difficulty_score` / `calories` / `training_load`),不由 FIT SDK 直接给出,而由 Resolver 从 canonical 字段派生。

### 1.1 派生所需 canonical 字段(后端 Resolver 必须消费)

| 字段 | 类型 | 来源 | 用途(语义) |
|---|---|---|---|
| `avg_hr` | number | `record.avg_hr` | 主刺激(有氧)强度计算 |
| `max_hr` | number | `record.max_hr` | 冲刺 / 极限强度参考 |
| `duration_sec` | number | `record.duration_sec` | 持续时间影响 TE 累计 |
| `sport_type` | string | `record.sport_type` | 选维度(跑步/骑行/...) |
| `display_sport_type` | string | `record.display_sport_type` | 选维度(规范化后) |
| `avg_pace_sec` | number | `record.avg_pace_sec` | 跑步/越野配速 → 速度刺激 |
| `avg_power` | number | `record.avg_power`(若存) | 骑行/室内骑行 → 功率 |
| `avg_cadence` | number | `record.avg_cadence` | 步频 / 踏频 |
| `gain_m` | number | `record.gain_m` | 越野/徒步 → 坡度刺激 |
| `hr_zones` | object | `record.detail.hr_zones`(若存) | HR 区间分布 → 训练刺激等级 |

### 1.2 数据可信分层(§五)

- `training_effect` = **derived/frontend_fallback** 层级
- **不**属于 `fit_sdk` 真值(不是 FIT SDK 直接给出)
- **不**属于 `shadow_diff`(要展示给用户,不是 audit-only)
- 派生计算必须发生在 Resolver 层;**前端不计算**

---

## §2 Resolver 输出契约 — JSON 结构(用户原文 §五,逐字保留)

```json
{
  "training_effect": {
    "sport_type": "running",

    "primary": {
      "title": "有氧收益",
      "score": 3.6,
      "level": "improvement",
      "label": "提升有氧耐力",
      "summary": "有效增强基础耐力"
    },

    "secondary": {
      "title": "速度刺激",
      "score": 2.4,
      "level": "maintenance",
      "label": "轻度提升",
      "summary": "包含少量高强度刺激"
    },

    "global_level": "improvement",

    "overall_summary":
      "本次训练主要强化基础耐力,并包含少量速度刺激。"
  }
}
```

### 2.1 字段定义

| 字段 | 类型 | 必现 | 说明 |
|---|---|---|---|
| `sport_type` | string | ✓ | 选用的运动类型(与 `record.display_sport_type` 对齐) |
| `primary` | object | ✓ | 主维度(用户原 §四 "Primary Title") |
| `primary.title` | string | ✓ | 主维度标题(例:"有氧收益" / "肌肉刺激") |
| `primary.score` | number | ✓ | 主刺激 TE 数值(0.0~5.0) |
| `primary.level` | string | ✓ | 全局 6 等级 ID(见 §3 表) |
| `primary.label` | string | ✓ | 当前 TE 范围对应的 UI 语义(用户原 §二 表) |
| `primary.summary` | string | ✓ | 当前 TE 范围对应的 Summary(用户原 §二 表) |
| `secondary` | object | ✓ | 次维度(用户原 §四 "Secondary Title") |
| `secondary.*` | 同 primary | ✓ | — |
| `global_level` | string | ✓ | 取 `max(primary.level, secondary.level)` 的全局等级 |
| `overall_summary` | string | ✓ | 自然语言总结(由 Resolver 拼接,前端不拼接) |

### 2.2 路径约定(本契约强制)

- 完整路径:`record.detail.training_effect`
- **不**放在 `record` 顶层(避免污染 canonical 字段,保持 §5.4 AI 边界)
- 命名空间:与 V4.0 已有的 `detail.display_metrics` / `detail.layout` 平级

---

## §3 全局 TE 标尺(用户原 §一,逐字保留)

> 适用于所有运动、所有维度的 6 等级统一标尺

| TE | Level ID | 全局等级 | 全局意义 | UI 颜色 |
|---|---|---|---|---|
| 0.0~0.9 | `recovery` | 恢复 | 几乎未形成训练刺激 | Gray |
| 1.0~1.9 | `activation` | 激活 | 轻度训练刺激 | Blue |
| 2.0~2.9 | `maintenance` | 维持 | 维持当前能力 | Cyan |
| 3.0~3.9 | `improvement` | 提升 | 有效训练刺激 | Green |
| 4.0~4.5 | `overload` | 高负荷 | 强烈训练刺激 | Orange |
| 4.5~5.0 | `extreme` | 极限 | 接近极限训练 | Red |

> 注:本契约只引用 Level ID,UI 颜色由前端按 ID 查表渲染(避免 Resolver 输出颜色字段污染)。

---

## §4 运动 × 维度 × 标题 映射表(用户原 §四,逐字保留)

| 运动 | Primary Title | Secondary Title |
|---|---|---|
| 跑步 | 有氧收益 | 速度刺激 |
| 越野跑 | 耐力收益 | 高强度刺激 |
| 徒步 | 耐力收益 | 高强度刺激 |
| 骑行 | 耐力输出 | 冲刺刺激 |
| 室内骑行 | 有氧输出 | 功率刺激 |
| 游泳 | 耐力收益 | 速度刺激 |
| 力量训练 | 肌肉刺激 | 爆发负荷 |
| HIIT | 心肺刺激 | 爆发刺激 |

> 注:本表 8 运动。当前 V9.3.1 `HERO_FIELD_REGISTRY`(track.html:6170)有 7 运动(无 HIIT),M0 是否扩到 8 运动由用户决定(见 §11 范围外)。

---

## §5 运动 × 维度 × TE 范围 完整映射(用户原 §二,逐字保留)

> 每个运动 2 张表(主维度 primary + 次维度 secondary),每张表 6 行(6 个 TE 范围)。
> `label` = UI 语义,`summary` = 描述。

### 5.1 跑步(Running)

#### 有氧收益(主)
| TE | label | summary |
|---|---|---|
| 0~1 | 恢复跑 | 以恢复与轻松活动为主 |
| 1~2 | 轻度耐力激活 | 对心肺形成轻微刺激 |
| 2~3 | 维持有氧耐力 | 保持当前耐力水平 |
| 3~4 | 提升有氧耐力 | 有效增强基础耐力 |
| 4~4.5 | 强化心肺能力 | 形成较强有氧刺激 |
| 4.5~5 | 极限耐力负荷 | 接近极限耐力训练 |

#### 速度刺激(次)
| TE | label | summary |
|---|---|---|
| 0~1 | 无明显速度刺激 | 基本为纯有氧训练 |
| 1~2 | 少量变速刺激 | 包含轻度变速 |
| 2~3 | 提升速度能力 | 形成一定爆发刺激 |
| 3~4 | 强化爆发能力 | 高强度配速刺激明显 |
| 4~4.5 | 高强度间歇刺激 | 对无氧系统形成较强负荷 |
| 4.5~5 | 极限速度训练 | 接近极限冲刺负荷 |

### 5.2 越野跑(Trail Running)

#### 耐力收益(主)
| TE | label |
|---|---|
| 0~1 | 轻松山地恢复 |
| 1~2 | 轻度耐力刺激 |
| 2~3 | 维持山地耐力 |
| 3~4 | 提升爬升耐力 |
| 4~4.5 | 强化长距离耐力 |
| 4.5~5 | 极限山地耐力 |

#### 高强度刺激(次)
| TE | label |
|---|---|
| 0~1 | 无明显高强度刺激 |
| 1~2 | 少量高强度配速 |
| 2~3 | 提升爆发输出 |
| 3~4 | 强化高强度能力 |
| 4~4.5 | 高负荷间歇刺激 |
| 4.5~5 | 极限山地输出 |

### 5.3 徒步(Hiking)

#### 耐力收益(主)
| TE | label |
|---|---|
| 0~1 | 轻松活动 |
| 1~2 | 轻度长距离活动 |
| 2~3 | 维持基础体能 |
| 3~4 | 提升长距离耐力 |
| 4~4.5 | 强化山地体能 |
| 4.5~5 | 极限长距离负荷 |

#### 高强度刺激(次)
| TE | label |
|---|---|
| 0~1 | 无明显高强度刺激 |
| 1~2 | 少量高强度活动 |
| 2~3 | 中等强度刺激 |
| 3~4 | 强化高强度能力 |
| 4~4.5 | 高负荷体能刺激 |
| 4.5~5 | 极限高强度负荷 |

### 5.4 公路骑行(Cycling)

#### 耐力输出(主)
| TE | label |
|---|---|
| 0~1 | 恢复骑行 |
| 1~2 | 轻度输出激活 |
| 2~3 | 维持持续输出 |
| 3~4 | 提升持续功率 |
| 4~4.5 | 强化耐力输出 |
| 4.5~5 | 极限耐力骑行 |

#### 冲刺刺激(次,推荐标题替代「无氧」)
| TE | label |
|---|---|
| 0~1 | 无明显冲刺刺激 |
| 1~2 | 少量变速刺激 |
| 2~3 | 提升冲刺能力 |
| 3~4 | 强化爆发输出 |
| 4~4.5 | 高强度间歇刺激 |
| 4.5~5 | 极限冲刺负荷 |

### 5.5 室内骑行(Indoor Cycling)

#### 有氧输出(主)
| TE | label |
|---|---|
| 0~1 | 轻松恢复骑行 |
| 1~2 | 轻度踩踏激活 |
| 2~3 | 维持有氧输出 |
| 3~4 | 提升持续踩踏能力 |
| 4~4.5 | 强化功率耐力 |
| 4.5~5 | 极限功率训练 |

#### 功率刺激(次)
| TE | label |
|---|---|
| 0~1 | 无明显高强度刺激 |
| 1~2 | 少量间歇刺激 |
| 2~3 | 提升爆发输出 |
| 3~4 | 强化高强度能力 |
| 4~4.5 | 高负荷功率间歇 |
| 4.5~5 | 极限功率训练 |

### 5.6 游泳(Swimming)

#### 耐力收益(主)
| TE | label |
|---|---|
| 0~1 | 轻松恢复游 |
| 1~2 | 轻度耐力激活 |
| 2~3 | 维持持续游动能力 |
| 3~4 | 提升游泳耐力 |
| 4~4.5 | 强化心肺能力 |
| 4.5~5 | 极限耐力训练 |

#### 速度刺激(次)
| TE | label |
|---|---|
| 0~1 | 无明显速度刺激 |
| 1~2 | 少量冲刺训练 |
| 2~3 | 提升爆发能力 |
| 3~4 | 强化高强度划水 |
| 4~4.5 | 高强度速度训练 |
| 4.5~5 | 极限速度负荷 |

### 5.7 力量训练(Strength)

> 用户原 §5.7 标注:「这里必须彻底换语言」— 不再用「有氧/无氧」,改用「肌肉刺激 / 爆发负荷」

#### 肌肉刺激(主,替代「有氧」)
| TE | label |
|---|---|
| 0~1 | 轻度肌肉激活 |
| 1~2 | 基础力量刺激 |
| 2~3 | 维持力量状态 |
| 3~4 | 提升肌肉负荷 |
| 4~4.5 | 强化力量刺激 |
| 4.5~5 | 极限力量负荷 |

#### 爆发负荷(次,替代「无氧」)
| TE | label |
|---|---|
| 0~1 | 无明显爆发训练 |
| 1~2 | 少量爆发刺激 |
| 2~3 | 提升爆发能力 |
| 3~4 | 强化高强度输出 |
| 4~4.5 | 高负荷力量刺激 |
| 4.5~5 | 极限爆发训练 |

### 5.8 HIIT / 功能训练

#### 心肺刺激(主)
| TE | label |
|---|---|
| 0~1 | 轻度活动 |
| 1~2 | 轻度心肺刺激 |
| 2~3 | 维持有氧能力 |
| 3~4 | 提升心肺能力 |
| 4~4.5 | 强化高强度耐力 |
| 4.5~5 | 极限心肺负荷 |

#### 爆发刺激(次)
| TE | label |
|---|---|
| 0~1 | 无明显爆发刺激 |
| 1~2 | 少量高强度动作 |
| 2~3 | 提升爆发能力 |
| 3~4 | 强化高强度输出 |
| 4~4.5 | 高负荷间歇刺激 |
| 4.5~5 | 极限爆发负荷 |

---

## §6 运动 × 维度 × level × label × summary 完整查找表(给后端 Resolver)

> 本节是 §3 + §4 + §5 的合并查找表,后端 Resolver 实现时直接消费。

```python
# 伪代码骨架(给后端 Python 工程师;前端不写此代码)
TE_LEVELS = {
    (0.0, 1.0):  ("recovery",     "Gray"),
    (1.0, 2.0):  ("activation",   "Blue"),
    (2.0, 3.0):  ("maintenance",  "Cyan"),
    (3.0, 4.0):  ("improvement",  "Green"),
    (4.0, 4.5):  ("overload",     "Orange"),
    (4.5, 5.0):  ("extreme",      "Red"),
}

SPORT_TITLE_MAP = {
    "running":         ("有氧收益", "速度刺激"),
    "trail_running":   ("耐力收益", "高强度刺激"),
    "hiking":          ("耐力收益", "高强度刺激"),
    "cycling":         ("耐力输出", "冲刺刺激"),
    "indoor_cycling":  ("有氧输出", "功率刺激"),
    "swimming":        ("耐力收益", "速度刺激"),
    "strength":        ("肌肉刺激", "爆发负荷"),
    "hiit":            ("心肺刺激", "爆发刺激"),
}

# 每个运动 × 维度 × 6 TE 范围,完整 6×6 矩阵
# 格式: SPORT_TE_MATRIX[sport_type][dimension] = [6 entries of (label, summary)]
# 留作 Resolver 实现时由 §5 表格逐字填入,本契约不写实现代码
SPORT_TE_MATRIX = {
    "running": {
        "primary":   [("恢复跑","以恢复与轻松活动为主"), ("轻度耐力激活","对心肺形成轻微刺激"),
                      ("维持有氧耐力","保持当前耐力水平"), ("提升有氧耐力","有效增强基础耐力"),
                      ("强化心肺能力","形成较强有氧刺激"), ("高强度耐力负荷","接近极限耐力训练")],
        "secondary": [("无明显速度刺激","基本为纯有氧训练"), ("少量速度刺激","包含轻度变速"),
                      ("提升速度能力","形成一定爆发刺激"), ("强化爆发能力","高强度配速刺激明显"),
                      ("高强度间歇刺激","对无氧系统形成较强负荷"), ("极限速度训练","接近极限冲刺负荷")],
    },
    # trail_running / hiking / cycling / indoor_cycling / swimming / strength / hiit
    # 同格式,从 §5 表格逐字填入(本契约只列 running 1 例作样本,其余 7 运动在实施时逐字填)
}
```

### 6.5 FIT SDK 字段映射(V9.4.4 已锁定,只读 Firstbeat 私有字段)

> V9.4.4 修正:正确的 Garmin Firstbeat 私有 TE 字段是 `total_training_effect` / `total_anaerobic_training_effect`,**不是** 219/218(V9.4.0 字段名错误,fitparse 静默返回 None)。
>
> 专家说明(2026-06-08):"Garmin TE 属于 Firstbeat proprietary model,非公开算法,涉及长期训练状态" — **不要重算,只消费**。

| FIT 字段 | FIT Profile Number | 类型 | 含义 | 角色 |
|---|---|---|---|---|
| `total_training_effect` | 7 (session) | uint8 (scale 0.1) | 0.0~5.0 有氧 TE (Firstbeat) | **primary_score** 的数据源 |
| `total_anaerobic_training_effect` | 13 (session) | uint8 (scale 0.1) | 0.0~5.0 无氧 TE (Firstbeat) | **secondary_score** 的数据源 |

**实施路径**:

```
FIT session message
  ↓
fitparse msg.get_value("total_training_effect")             → 0.0~5.0 float (fitparse 自动 scale)
fitparse msg.get_value("total_anaerobic_training_effect")  → 0.0~5.0 float
  ↓
fit_engine 直接读,统一存到 aerobic_training_effect / anaerobic_training_effect(契约命名)
  ↓
DB 字段:activities.aerobic_training_effect REAL
        activities.anaerobic_training_effect REAL
  ↓
_build_record_from_row 读 → MetricsResolver.build_training_effect(record) → record.detail.training_effect
  ↓
前端 _buildTrainingBenefitCard 直接消费
```

**V9.4.4 重要说明**:

- **正确字段名**:`total_training_effect` / `total_anaerobic_training_effect`(**不是** 219/218)
- **不重算 Garmin TE**:Firstbeat 私有算法,涉及长期训练状态,无法仅凭单次活动重算
- **不读 213/218/219**:V9.4.0 用的字段名错,fitparse 静默返回 None 触发启发式估算
- **字段可能为 None**:老 Garmin 设备、Edge 部分记录、Zwift 导出 FIT、Apple 转 FIT、第三方转换
- **双字段都 None → 前端占位**(不重算)

**力量训练特例**:用户原 §5.7 标注「这里必须彻底换语言」,但 FIT 字段不变 — `training_effect_aerobic` / `anaerobic_training_effect` 是 Garmin 标准字段,所有运动都用这两个。**只有 label/summary/title 因运动不同**(由 SPORT_TITLE_MAP + SPORT_TE_MATRIX 决定)。

**HIIT 同理**:HIIT 设备的 FIT 文件也用标准 aerobic/anaerobic 字段,只是 label/title 走 §5.8 HIIT 表。

### 6.6 后端 Resolver 极简实现(因为 TE 数值直接读 FIT)

```python
def build_training_effect(record: dict, sport_type: str) -> dict | None:
    """V9.4.4:消费 FIT Firstbeat TE 字段,查表得 title/label/summary,返回 contract §2.1 JSON"""
    aerobic = record.get("aerobic_training_effect")
    anaerobic = record.get("anaerobic_training_effect")
    if aerobic is None and anaerobic is None:
        return None  # 双字段都 None → 占位卡(不重算 Firstbeat)

    primary_score = aerobic if aerobic is not None else 0.0
    secondary_score = anaerobic if anaerobic is not None else 0.0
    primary_title, secondary_title = SPORT_TITLE_MAP.get(sport_type, SPORT_TITLE_MAP["running"])

    primary_idx = _te_to_index(primary_score)        # 0~5 → 0~5
    secondary_idx = _te_to_index(secondary_score)
    primary_label, primary_summary = SPORT_TE_MATRIX[sport_type]["primary"][primary_idx]
    secondary_label, secondary_summary = SPORT_TE_MATRIX[sport_type]["secondary"][secondary_idx]

    primary_level, _ = TE_LEVELS_BY_INDEX[primary_idx]
    secondary_level, _ = TE_LEVELS_BY_INDEX[secondary_idx]
    global_level = max([primary_level, secondary_level], key=lambda l: LEVEL_ORDER[l])

    overall_summary = f"本次训练{primary_summary},并包含{secondary_summary}。"
    return {
        "sport_type": sport_type,
        "primary": {"title": primary_title, "score": primary_score, "level": primary_level,
                    "label": primary_label, "summary": primary_summary},
        "secondary": {"title": secondary_title, "score": secondary_score, "level": secondary_level,
                      "label": secondary_label, "summary": secondary_summary},
        "global_level": global_level,
        "overall_summary": overall_summary,
        "data_source": "fit_sdk",
    }
```

> **不再需要计算 TE score** — 直接读 FIT Firstbeat 字段。Resolver 唯一做的事是「查表 + 字符串拼接」。
> **V9.4.4 修正**:删除 V9.4.3 启发式估算函数(不再重算 Firstbeat 私有算法)。
> **V9.4.4 修正**:删除 V9.4.2 字段名 219/218 错误,改读正确的 `total_training_effect` / `total_anaerobic_training_effect`。

### 6.7 实施决策(M0 已锁定)

| # | 决策 | 状态 |
|---|---|---|
| 1 | 数据路径 `record.detail.training_effect` | ✅ 按用户建议 |
| 2 | 8 运动扩到前端 `_resolveHeroItems` | ✅ 实施中 |
| 3 | FIT 字段 `total_training_effect` / `total_anaerobic_training_effect`(Firstbeat)直读 | ✅ V9.4.4 已修正 |
| 4 | UI 6 等级颜色(Gray/Blue/Cyan/Green/Orange/Red)渲染 | ✅ 实施中 |
| 5 | V9.4.4 删除 V9.4.3 启发式估算函数(不再重算 Firstbeat 私有算法) | ✅ 已删除 |
| 6 | V9.4.4 删除 V9.4.2 字段名 219/218 错误 | ✅ 已删除 |

### 6.8 V9.4.4 关键决策:不重算 Firstbeat

> **专家说明(2026-06-08)**:Garmin TE 属于 Firstbeat proprietary model,非公开算法,涉及长期训练状态。
>
> **脉图正确定位**:消费 Garmin TE + 做语义解释,**不是**重建 Firstbeat。

**为什么不做启发式估算**:
- 即使有 hr_zone_distribution(HRR 法 5 区间),也**无法精确重算** Garmin Connect 数值
- 项目 zone 划分(Karvonen 50~100% HRR)与 Garmin(%max HR / 用户自定义)不在同一体系
- 同一段 HR 在两套 zone 下归入不同区间,TE 结果必偏差

**V9.4.4 行为**:
- FIT 有 `total_training_effect` / `total_anaerobic_training_effect` → 直接消费 + 查表(标 `data_source=fit_sdk`)
- FIT 缺这两个字段(老设备/Edge 部分记录/Zwift 导出/Apple 转 FIT/第三方转换)→ 返回 None + 前端占位卡

---

## §7 前端契约(消费侧,严禁计算)

### 7.1 数据源

- 唯一来源:`record.detail.training_effect`
- **严禁**前端拼接 / 推导 / 重新计算 `level` / `label` / `summary` / `overall_summary`
- **严禁**前端读 `record.avg_hr` 等再二次计算

### 7.2 UI 结构(用户原 §三,逐字保留)

```
🔥 训练收益
───────────────

主收益
xxx  ←  primary.label

次刺激
xxx  ←  secondary.label

─────────────
Summary  ←  overall_summary
```

### 7.3 前端 UI 渲染(契约)

```js
// 伪代码骨架(给前端;严禁二次计算)
function _buildTrainingBenefitCard(record) {
    var te = record && record.detail && record.detail.training_effect;
    if (!te) {
        // 降级:返回占位卡(同 V9.2.2 旧占位)
        return _buildPlaceholderSidebarCard('训练收益', '🔥',
            '有氧收益 / 无氧刺激将在「复盘」Tab 的 AI 洞察中呈现');
    }
    // §六 shadow_diff 隔离(本卡无 shadow_diff 风险,但保持一致)
    if (te.shadow_diff || te.shadow_diff_json || te.diff) return '';
    // 直接消费 Resolver 输出
    return '<div class="weather-glass-card">' +
        '<div class="weather-glass-head">' +
            '<div>' +
                '<div class="weather-glass-title">🔥 训练收益</div>' +
                '<div class="weather-glass-subtitle">' + esc(te.sport_type) + ' · ' +
                    esc(_levelLabel(te.global_level)) + '</div>' +
            '</div>' +
        '</div>' +
        '<div class="training-effect-grid">' +
            '<div class="training-effect-row">' +
                '<div class="key">主收益 — ' + esc(te.primary.title) + '</div>' +
                '<div class="val">' + esc(te.primary.label) + '</div>' +
                '<div class="score">' + esc(te.primary.score.toFixed(1)) + '</div>' +
            '</div>' +
            '<div class="training-effect-row">' +
                '<div class="key">次刺激 — ' + esc(te.secondary.title) + '</div>' +
                '<div class="val">' + esc(te.secondary.label) + '</div>' +
                '<div class="score">' + esc(te.secondary.score.toFixed(1)) + '</div>' +
            '</div>' +
        '</div>' +
        '<div class="weather-glass-empty">— ' + esc(te.overall_summary) + '</div>' +
    '</div>';
}

// 颜色查表(用户原 §一,前端可缓存)
var _TE_LEVEL_LABEL = {
    recovery:    '恢复',
    activation:  '激活',
    maintenance: '维持',
    improvement: '提升',
    overload:    '高负荷',
    extreme:     '极限',
};
function _levelLabel(id) { return _TE_LEVEL_LABEL[id] || id; }
```

### 7.4 颜色渲染(可选,M1)

- 前端按 `primary.level` / `secondary.level` 查表得 UI 颜色
- 不要把颜色写进 Resolver 输出(避免污染语义层)
- M0 暂不实现颜色(等用户验收后决定)

---

## §8 契约合规(§11.2 审查门禁逐条)

| 门禁项 | V1.0 合规 |
|---|---|
| 前端 UI 推断值写回 canonical | ✅ 前端只读 `detail.training_effect`,不写 |
| AI 输出进入 canonical | ✅ TE 由 Resolver 派生(非 AI 输出),不写回 |
| `shadow_diff` 进入 AI Snapshot / UI | ✅ TE 路径无 shadow_diff |
| 新增文件放入错误目录 | ✅ Resolver 改 `metrics_resolver.py` / Frontend 改 `track.html` |
| 硬编码绝对路径 | ✅ 无 |
| 未更新 requirements.txt 引入新依赖 | ✅ 无新依赖 |
| 敏感字段未脱敏 | ✅ TE 字段非敏感 |

---

## §9 数据流(全链路可追溯 §2.1)

```
FIT 文件
  ↓
fit_engine 解析 (fitparse)
  ↓
DB 写入 (activities 表: avg_hr, max_hr, duration_sec, sport_type, avg_pace_sec, gain_m, ...)
  ↓
MetricsResolver.build_training_effect(record)  ← 新增
  - 读 canonical 字段(avg_hr / max_hr / avg_pace_sec / gain_m / ...)
  - 计算 primary_score / secondary_score(0~5)
  - 查 SPORT_TITLE_MAP + SPORT_TE_MATRIX 得 title / level / label / summary
  - 拼接 overall_summary
  ↓
_build_record_from_row() 在 main.py:6065 透传:
  "training_effect": resolver.build_training_effect(...)
  存到 record.detail.training_effect
  ↓
get_activity_detail API 返回:
  { code, msg, data: { record: { detail: { training_effect: {...} } } }, traceId }
  ↓
Frontend renderActivityDetailSidebar
  - 读 record.detail.training_effect
  - _buildTrainingBenefitCard(record) 直接消费
  - 不计算、不拼接
```

---

## §10 实施任务清单(P0/P1/P2)

### P0-TE 后端

| # | 任务 | 文件 | 行数 |
|---|---|---|---|
| 1 | 新增 `MetricsResolver.build_training_effect(record, sport_type)` | `metrics_resolver.py` | ~30 |
| 2 | 新增 `TE_LEVELS` / `SPORT_TITLE_MAP` / `SPORT_TE_MATRIX` 静态字典 | `metrics_resolver.py` | ~150 |
| 3 | 填全 8 运动 × 2 维度 × 6 TE 范围 = 96 单元(从 §5 表格逐字) | `metrics_resolver.py` | — |
| 4 | `_build_record_from_row` 在 line 6065 附近透传 `training_effect` | `main.py` | +3 |
| 5 | `docs/js_api_contract.json` 登记新字段(若需) | `docs/js_api_contract.json` | +10 |

### P1-TE 前端

| # | 任务 | 文件 | 行数 |
|---|---|---|---|
| 1 | 新增 `_buildTrainingBenefitCard(record)` 函数 | `track.html` | ~30 |
| 2 | 新增 `_TE_LEVEL_LABEL` 颜色查表 | `track.html` | ~5 |
| 3 | 替换 `renderActivityDetailSidebar` 内 `_buildPlaceholderSidebarCard('训练收益', ...)` | `track.html` | +3 -3 |
| 4 | 新增 `.training-effect-grid` / `.training-effect-row` CSS | `track.html` | ~30 |
| 5 | 复用 `.weather-glass-card` / `.weather-glass-title` 玻璃态样式(0 新增 CSS) | — | 0 |

### P2-TE 测试

| # | 任务 | 文件 | 行数 |
|---|---|---|---|
| 1 | `test_training_effect_resolver.py` — 8 运动 × 2 维度 × 6 范围 单元测试 | `tests/test_training_effect_resolver.py` | ~150 |
| 2 | `test_training_effect_frontend.py` — 静态 grep 验证 | `tests/test_training_effect_frontend.py` | ~80 |
| 3 | `test_training_effect_contract.py` — §2.2 路径、§3 等级、§5 范围、§7 禁做 集成 | `tests/test_training_effect_contract.py` | ~80 |

---

## §11 范围外(本契约**不**包含)

> 以下事项**用户未在原文中要求**,本契约**不**做,等用户后续指示:

1. **HIIT 运动前端落地**:用户原 §四 / §二 含 HIIT 8 个运动,但 V9.3.1 `HERO_FIELD_REGISTRY` 只有 7(无 HIIT)。M0 是否扩到 8 运动由用户决定(影响 `_resolveHeroItems` 注册表 + V9.3.4 字段映射)。本契约保留 HIIT 8 运动 Resolver 设计,前端是否消费等用户验收时拍板。
2. **UI 颜色渲染**:§3 表的 UI 颜色(Gray/Blue/Cyan/Green/Orange/Red)M0 暂不实现,等用户验收后决定。
3. **历史 TE 趋势**(跨活动 TE 折线图)— 用户未要求。
4. **AI 洞察联动**:`training_effect` 不进入 `_ai_snapshot`(它是 Resolver 派生,不是 AI 输出;§5.4 AI 边界);复盘 Tab 的 AI 洞察可独立消费 TE 字段,具体联动等用户要求。
5. **TE 计算公式**(具体怎么从 avg_hr/duration_sec 算出 0~5 的 TE score):本契约不规定 Resolver 的**计算逻辑**(留给后端工程师实现,需参考 Garmin TE 算法或类似)。本契约只规定**输入字段**和**输出结构**。
6. **`shadow_diff` 联动**:V4.0 §六 已有 `shadow_diff_json` 字段,本契约不与之联动(TE 派生路径独立)。

---

## §12 验收清单(M0)

> 用户在 DevTools 打开任一跑步活动详情,确认:

- [ ] 右侧栏「🔥 训练收益」卡显示 4 块:
  - [ ] 标题:🔥 训练收益 + 副标题(运动类型 + 全局等级)
  - [ ] 主收益行:标题(如"有氧收益")+ label(如"提升有氧耐力")+ score(数值)
  - [ ] 次刺激行:标题(如"速度刺激")+ label(如"轻度提升")+ score(数值)
  - [ ] Summary:`overall_summary` 一句自然语言
- [ ] 字段值与后端 `_build_record_from_row` 输出的 `record.detail.training_effect` **完全一致**(无前端拼接)
- [ ] 7 运动(跑/越野/徒/骑/室骑/游/力)显示正常;HIIT 走降级(若 M0 不扩)
- [ ] 跑/越野/徒/骑/室骑/游/力 切换时,主/次标题(label / summary)随运动切换
- [ ] TE 等级(recovery/.../extreme)与 §3 表一致
- [ ] `record.detail.training_effect` 缺数据时,降级为 V9.2.2 占位卡(等用户验收)
- [ ] shadow_diff / shadow_diff_json 出现时,卡返回空字符串(§六 隔离)

---

## §13 变更日志

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.0 | 2026-06-07 | 初稿,从用户原 8 运动 × 双维度 × 6 TE 范围设计整理为可执行契约 |
| v1.1 | 2026-06-08 | V9.4.0 实施:`build_training_effect` Resolver + 8 运动 × 2 维 × 6 范围 矩阵 + `_estimate_training_effect_from_hr` 启发式兜底(V9.4.1) |
| v1.2 | 2026-06-08 | V9.4.2 简化:删除 `total_training_effect`(field 213)兜底分支,`fit_engine.py` 只读 219/218,旧设备走占位卡降级 |
| v1.3 | 2026-06-08 | V9.4.3 启发式估算升级:优先消费 `hr_zone_distribution` + logistic 压缩公式 + §6.8 已知局限声明(后来证实是错误方向) |
| v1.4 | 2026-06-08 | V9.4.4 **关键修正**:Garmin 正确字段名是 `total_training_effect` / `total_anaerobic_training_effect`(V9.4.0 用的 219/218 错误,fitparse 静默返回 None)。删除 V9.4.3 启发式估算函数,采用"消费 Firstbeat 私有字段 + 缺则占位"策略,4.2/2.1 和 5.0/0.1 完美对齐 Garmin Connect。 |

---

> **契约审阅要点**(给用户):
>
> 1. **数据路径**:本契约把 `training_effect` 放在 `record.detail.training_effect`(与 V4.0 `detail.display_metrics` / `detail.layout` 平级);若你想放顶层 `record.training_effect`,改 §2.2 即可。
> 2. **8 运动 vs 7 运动**:本契约含 HIIT(8 运动),但 V9.3.1 `HERO_FIELD_REGISTRY` 只有 7 运动(无 HIIT);M0 是否扩 8 运动到前端由你拍板(详见 §11.1)。
> 3. **TE 计算公式**:本契约不规定具体公式(留给后端实现);若你有 Garmin 原始算法参考,告诉我,我加进 §6 伪代码骨架。
> 4. **§11 范围外**:M0 暂不实现的 6 项(颜色、HIIT 前端、历史趋势、AI 联动、计算公式、shadow_diff 联动);如有遗漏请补。
>
> 验收通过后,我按 §10 任务清单分 P0/P1/P2 实施。
</content>