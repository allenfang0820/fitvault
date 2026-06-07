# 脉图运动生理参考 (Physiology Reference)

> 知识层权威源 · V7.8.0 → Q2-1 扩展
> 适用范围：所有进入 MetricsResolver / LLM prompt / UI 展示的运动生理指标
> 更新策略：每个新指标必须先填本文件 7 项标注，审查通过后才能进入代码

---

## 一、本文件使用规则

### 1.1 7 项必填标注模板

每个进入"可发布指标库"的指标，必须填全以下 7 项：

| 项目 | 必填 | 说明 |
|---|---|---|
| 1. 生理意义 | YES | 该指标在运动生理学中的具体含义，严禁"提升训练质量"等空话 |
| 2. 数据来源 | YES | 文献/标准名 + 页码/DOI，无来源=禁止进入 |
| 3. 是否行业标准 | YES | YES / NO / 部分 — 严禁模糊 |
| 4. 参考体系 | YES | Coggan / ACSM / Friel / Burke / 自创 等 |
| 5. 适用 sport | YES | 白名单 sport_type 列表，严禁"全部 sport 适用" |
| 6. 风险说明 | YES | 边界条件、降级路径、已知误用场景 |
| 7. confidence 条件 | YES | HIGH / MEDIUM / LOW / UNAVAILABLE 分级与对应条件 |

### 1.2 拒绝入源的场景

- 无文献来源
- 行业术语误用（如把 SWOLF 当心肺负荷）
- 自造无统一定义的指标（如 "power_smoothness"）
- 自建误差大且有标准替代的公式（如自定义 swim MET）

### 1.3 版本化

- 文档版本：跟随 fit-arch-contrac 的 Q-季度号
- 当前版本：2026-Q2-1（GIS 扩展）
- 修订记录：见文末"变更日志"

---

## 二、可发布指标库 (Active Indicators)

---

### 指标 1: Glycogen Depletion Risk

> 替代原 `_detect_bonk_event` 硬编码 1600 kcal 阈值

#### 1. 生理意义

糖原耗竭风险（Glycogen Depletion Risk）：在长时间耐力运动中，糖原耗竭是导致"撞墙"（hitting the wall / bonking）的核心生理机制。耗竭风险与以下因素强相关：

- 总耗能（由体重、强度、持续时间决定）
- 训练状态（训练有素者糖原储备更高）
- 碳水化合物摄入（比赛/训练中补给）

固定 kcal 阈值只是 heuristic；更科学的做法是**区间模型 + risk_level**。

#### 2. 数据来源

- Burke, L. (2007). *Practical Sports Nutrition*. Human Kinetics. Chapter 5: "Carbohydrate requirements for exercise"。
- Friel, J. (2009). *The Triathlete's Training Bible* (4th ed.). VeloPress. Chapter 12: "Training for the Long Run"。
- 行业基准：跑步全马（42.195 km）平均消耗 2500-3000 kcal；糖原储备约 1500-1800 kcal；故 2 小时以上中强度跑步进入糖原耗竭区。

#### 3. 是否行业标准

**部分**。Bonk 检测本身是行业共识，但具体 kcal 阈值因体重/训练/补给出入较大，**精确量化无统一标准**。区间模型是工程上的合理折中。

#### 4. 参考体系

- Burke 碳水化合物指南（营养层）
- Friel 训练圣经（应用层）

#### 5. 适用 sport

| sport_type | 区间 (kcal) | 备注 |
|---|---|---|
| running | 1400-1800 | 公路跑 |
| trail_running | 1600-2200 | 越野含爬升耗能高 |
| cycling | 1800-2400 | 功率主导，总耗能更大 |
| mountain_biking | 1800-2400 | 同上 |
| hiking | 1400-1800 | 徒步耗能接近慢跑 |
| swimming | 1200-1600 | 水阻散热好，1-2h 长游触发 |
| open_water | 1200-1600 | 公开水域水温低耗能略高 |
| skiing | 1600-2200 | 滑雪冷应激+技术动作 |
| default | 1400-1800 | 未知 sport |

**输出格式**：

- `risk_level`：`"low"`（kcal < 区间下界） / `"moderate"`（区间内） / `"high"`（kcal > 区间上界）
- **不输出** `bonk: true/false` 二元值（过于绝对化）

#### 6. 风险说明

- **降级路径**：若 FIT 数据无 `total_calories`，则基于 Keytel / power_eq 推演，标注 `risk_level_confidence: "low"`
- **边界条件**：
  - 训练有素者糖原储备可超出区间上界，**不宜在用户体脂率未知时下调阈值**
  - 比赛/训练中补给（胶/能量棒）显著延缓糖原耗竭，本指标**未考虑补给**；在 prompt 中需告知 AI "未追踪补给"
- **已知误用**：
  - 误用 1：短距离高强度间歇训练 (HIIT) 总 kcal 也会 > 1000，但**糖原耗竭风险低**（高强度 < 30 min 走磷酸原系统）
  - 误用 2：100m 冲刺 30 秒也会触发 bonk 检测，需要 `duration_sec > 1800` 二次校验

#### 7. confidence 条件

| confidence | 条件 |
|---|---|
| HIGH | total_calories 来自功率计（cycling）或胸带心率 + 精确体重 |
| MEDIUM | 光学心率推算的 total_calories |
| LOW | Keytel / power_eq 推演 或 无体重数据 |
| UNAVAILABLE | 无 calorie 数据且无推演数据源 |

---

### 指标 2: HR-based Cardio Load

> 替代原 `_classify_cardio_load` avg_hr/max_hr 单一比值；骑行优先 Power+HR

#### 1. 生理意义

心肺负荷（Cardio Load）：运动中循环系统承受的相对强度，通常用储备心率百分比（HRR%）或最大心率百分比（%HRmax）衡量。比值越高，心脏泵血负荷越大。

HR-based Cardio Load 用 `%HRmax = avg_hr / max_hr` 衡量（简化版，精度低于 HRR%）；对有功率数据的骑行/滑雪，优先用 **Power + HR 联合判定**（功率更直接反映外部负荷）。

#### 2. 数据来源

- ACSM (2021). *Guidelines for Exercise Testing and Prescription* (11th ed.). Wolters Kluwer. Chapter 4: "Cardiovascular Responses to Exercise"。
- Pollock, M.L. et al. (1998). "The recommended quantity and quality of exercise for developing and maintaining cardiorespiratory fitness..." *MSSE* 30(6): 975-991。
- Coggan, A. (2003). *Training and Racing with a Power Meter*. VeloPress. Chapter 2: "Power 101"。

#### 3. 是否行业标准

**部分**。HRR% / %HRmax 是行业金标准；Coggan 7 级功率分区（Active Recovery / Endurance / Tempo / Threshold / VO2max / Anaerobic / Neuromuscular）是骑行金标准。

#### 4. 参考体系

- ACSM 心肺分区标准
- Coggan 功率分区标准（仅骑行/滑雪）

#### 5. 适用 sport

| sport_type | 主导指标 | 降级路径 |
|---|---|---|
| running | HR | 必填 avg_hr / max_hr |
| trail_running | HR | 必填 avg_hr / max_hr |
| hiking | HR | 必填 avg_hr / max_hr |
| swimming | HR | 必填 avg_hr / max_hr（与跑步同公式） |
| cycling | Power + HR | 无功率数据时降级 HR only |
| mountain_biking | Power + HR | 无功率数据时降级 HR only |
| skiing | Power + HR | 无功率数据时降级 HR only |

**HR 5 级分类**：

| ratio (avg_hr/max_hr) | 等级 |
|---|---|
| < 0.55 | very_low |
| 0.55-0.70 | low |
| 0.70-0.80 | moderate |
| 0.80-0.90 | high |
| > 0.90 | extreme |

**Power + HR 联合判定**（仅 cycling / mountain_biking / skiing）：

- 优先：%FTP（无 FTP 上下文时降级为 power_zones 比例）
- 降级：HR 比例

#### 6. 风险说明

- **降级路径**：无 max_hr 时直接返回 "unknown"；无 avg_hr 时同样 "unknown"
- **边界条件**：
  - 设备心率漂移（光学心率在剧烈运动中误差 ±5%）— prompt 需告知 AI "心率存在 5% 设备误差"
  - 药物（β-阻滞剂）使用者的 HR 与强度解耦 — 本指标对该人群不适用
- **已知误用**：
  - 误用 1：把 SWOLF 当心肺负荷指标（SWOLF 是技术效率，与心率无直接关系）
  - 误用 2：在静息状态下（avg_hr=60）误判为 "very_low"，但对耐力运动员，静息 HR 50 是**正常适应**，不是"负荷低"

#### 7. confidence 条件

| confidence | 条件 |
|---|---|
| HIGH | 胸带心率 + max_hr 已校准 |
| MEDIUM | 光学心率 / max_hr 为 age-predicted（220-age） |
| LOW | 设备心率异常 / β-阻滞剂使用者 |
| UNAVAILABLE | 无 avg_hr / 无 max_hr |

---

### 指标 3: Variability Index (VI)

> 替代原 `_classify_pace_stability` 自造 "power_smoothness" 指标

#### 1. 生理意义

变异指数（Variability Index, VI）：衡量运动中功率输出的波动性。**VI = NP (Normalized Power) / Avg Power**。VI 越接近 1，功率输出越稳定（匀速）；VI 越大，波动越剧烈（间歇/上坡/冲刺）。

VI 在 Coggan 体系内是**正式指标**，广泛用于 TrainingPeaks / WKO / Golden Cheetah 等行业软件。

#### 2. 数据来源

- Coggan, A. (2003). *Training and Racing with a Power Meter*. VeloPress. Chapter 8: "Normalization of Power Data"。
- Allen, H. & Coggan, A. (2010). *Training and Racing with a Power Meter* (2nd ed.). VeloPress. **具体页码: p.50-55（Normalized Power 计算）**。
- 行业实现：TrainingPeaks, WKO5, Golden Cheetah。

#### 3. 是否行业标准

**YES**。Coggan 体系的金标准，行业广泛使用。

#### 4. 参考体系

- Coggan / TrainingPeaks / WKO 功率训练体系

#### 5. 适用 sport

| sport_type | 是否计算 VI | 数据需求 |
|---|---|---|
| running | NO | 跑步无连续功率数据 |
| trail_running | NO | 同上 |
| cycling | YES | 必填逐秒 power 数组 |
| mountain_biking | YES | 必填逐秒 power 数组 |
| skiing | YES | 必填逐秒 power 数组 |
| swimming | NO | 游泳有功率计但非主流 |
| hiking | NO | 无功率数据 |
| default | NO | 未知 sport 不计算 |

**VI 分级**（基于 Allen & Coggan p.55 表）：

| VI | 含义 | 训练场景 |
|---|---|---|
| < 1.05 | stable | 匀速有氧 / LSD |
| 1.05-1.15 | moderate | 长距离起伏 / 间歇训练 |
| > 1.15 | high_variance | 短距离冲刺 / 激烈比赛 |

**计算公式**：

```text
NP = (1/T) * Σ( p(t)^4 )^(1/4)  for t in 1..T
VI = NP / AvgPower
```

#### 6. 风险说明

- **降级路径**：
  - 无逐秒 power 数据 → 返回 "unknown"
  - 有 power 但无连续 records → 返回 "low_confidence" 并要求 prompt 中告知 AI "VI 不可信"
- **边界条件**：
  - 零功率段（滑行/休息）必须从 records 中过滤，否则 VI 系统性偏高
  - 短时运动（< 5 min）NP 收敛到 AvgPower，VI 接近 1.0，失去区分度
- **已知误用**：
  - 误用 1："power_smoothness"（自造词，无统一定义）— **严禁使用，见 §三**
  - 误用 2：跑步活动的 "power_smoothness" = power_variance 是个常见误用，跑步 FIT 几乎不包含功率数据

#### 7. confidence 条件

| confidence | 条件 |
|---|---|
| HIGH | 逐秒 power 数组完整 + duration > 10min |
| MEDIUM | power 有缺帧 / 功率计校准不明 |
| LOW | 零功率段未过滤 / duration < 5min |
| UNAVAILABLE | 无 power 数据 |

---

### 指标 4: Capability Routing

> 设计模式：context_tags 注入与 Bonk 状态机的 sport 路由

#### 1. 生理意义

**非生理指标，是工程设计模式**。每个 sport 拥有不同的"能力维度"（如：uses_altitude / uses_heat / uses_power / uses_swolf），指标的启用与否由能力决定，而非硬 sport 字符串排除。

例如：游泳的泳池温度（26-28°C）是设施设定，非环境应激 → 不应注入"热应激"标签；但"开放水域 16°C"就应注入 → 由 `uses_heat` capability 决定。

#### 2. 数据来源

**非生理指标，无文献来源**。设计模式参考：

- Capability-based security（Capsicum, CapsN）
- Strategy pattern（GoF）

#### 3. 是否行业标准

**NO**（自创设计模式）。但 capability-based routing 在分布式系统（SPIFFE, Istio）中是行业惯例。

#### 4. 参考体系

- 自创（脉图项目内部）
- 参考：Strategy pattern（GoF 1994）

#### 5. 适用 sport

**所有 sport，统一接口**。注册表结构：

```python
SPORT_CAPABILITY_REGISTRY = {
    "running": {
        "uses_altitude": True,
        "uses_heat": True,
        "uses_power": False,
        "uses_swolf": False,
    },
    "swimming": {
        "uses_altitude": False,
        "uses_heat": False,
        "uses_power": False,
        "uses_swolf": True,
    },
    "cycling": {
        "uses_altitude": False,
        "uses_heat": True,
        "uses_power": True,
    },
    # ...
}
```

**严禁硬 sport 字符串排除**：

```python
# 反例 —— 严禁
if sport == "swimming":
    return []  # 硬排除

# 正例 —— 必须
if not dimension["uses_heat"]:
    return []  # capability 排除
```

#### 6. 风险说明

- **降级路径**：未知 sport 走 "default" capability（全部 False，最保守）
- **边界条件**：
  - open_water 应该 `uses_heat=True`（水温低，应激大）
  - indoor_cycling 应该 `uses_altitude=False`（室内功率车，无海拔）
- **已知误用**：
  - 误用 1：`if sport_type in ["swimming", "open_water"]`（硬字符串）
  - 误用 2：复用 sport_type 字符串而非 capability

#### 7. confidence 条件

**非生理指标，不适用 confidence 系统。**

---

## ===== 以下为 GIS 扩展新增（2026-Q2-1） =====

---

### 指标 5: Efficiency Score

> Growth Intelligence System · Canonical Metric
> 继承复盘系统 gap_calculator.py，新增 baseline normalization

#### 1. 生理意义

运动效率（Efficiency Score）：衡量**单位生理负荷下的运动输出效率**。反映心肺输出效率、跑步经济性改善、单位心率输出速度。

长期效率提升意味着基础耐力增强、心脏泵血效率提高、肌肉摄氧能力改善。

```text
更低心率 → 更高速度 = 效率提升
```

#### 2. 数据来源

- Bassett, D.R. & Howley, E.T. (2000). "Limiting factors for maximum oxygen uptake and determinants of endurance performance." *MSSE* 32(1): 70-84。
- Noakes, T.D. (2003). *Lore of Running* (4th ed.). Human Kinetics. Chapter 2: "Oxygen Transport and Running Economy"。
- 标准化方法参考 GAP（Grade Adjusted Pace）：Strava GAP 算法白皮书 + TrainingPeaks Normalized Graded Pace。

#### 3. 是否行业标准

**部分**。Efficiency（效率比）概念在运动生理学中有共识（单位耗氧量的运动输出），但评分归一化（0~100）和 rolling baseline comparison（21d）是脉图自建标准。Running Economy（ml/kg/km）是 ACSM 金标准，但需要 VO2 数据——GIS 退而求其次用 pace / hr 比值。

#### 4. 参考体系

- ACSM 运动效率框架
- Strava GAP（坡度修正）
- 脉图自建 baseline normalization（21d median）

#### 5. 适用 sport

| sport_type | 是否计算 | 备注 |
|---|---|---|
| running | YES | 主场景 |
| trail_running | YES | 坡度修正生效 |
| cycling | YES（未来） | 需 power 数据，当前无功率计暂不计算 |
| hiking | YES | 速度较慢，效率偏低正常 |
| swimming | NO | 心率测量可靠性不足 |
| default | NO | 未知 sport 不计算 |

#### 6. 风险说明

- **降级路径**：无 avg_hr → 返回 "unknown"；GPS 信号异常 → 标注 LOW confidence
- **边界条件**：
  - 温度 > 28°C 时心率升高效率降低 → 需温度补偿（系数待 Phase 5G 校准）
  - 高海拔（> 2000m）效率偏低 → 非适应退化，是环境应激
  - 短时运动（< 15 min）样本不足 → 排除
- **已知误用**：
  - 误用 1：把 efficiency 当 Ready Score（不是整体健康分，是单项效率趋势）
  - 误用 2：同一天两次运动的 efficiency 差异归因于"训练效果"（可能是温度/补给/睡眠差异）

#### 7. confidence 条件

| confidence | 条件 |
|---|---|
| HIGH | avg_hr 有效 + pace 有效 + duration > 30min + GPS 信号良好 |
| MEDIUM | 有数据但 duration 15~30min 或 GPS 信号中等 |
| LOW | temperature > 28°C 未补偿 / 高海拔未补偿 / 光学心率设备 |
| UNAVAILABLE | 无 avg_hr 或 无 pace 或 duration < 15min |

---

### 指标 6: HR Drift（心率漂移）

> Growth Intelligence System · Canonical Metric
> 当前 V7.6 由 decoupling_pct 临时代理，V7.13 升级真实算法

#### 1. 生理意义

心率漂移（Cardiovascular Drift）：在稳态运动过程中，心率随时间逐渐升高而配速/功率不增加的现象。反映：

- 有氧系统稳定性（漂移越少，有氧基础越好）
- 热适应能力（高温环境漂移加剧）
- 糖原管理（糖原耗竭时漂移急剧上升）
- 耐力基础（训练有素者漂移 < 5%）

#### 2. 数据来源

- Coyle, E.F. & González-Alonso, J. (2001). "Cardiovascular drift during prolonged exercise: new perspectives." *Exercise and Sport Sciences Reviews* 29(2): 88-92。
- Wingo, J.E. et al. (2012). "Cardiovascular drift is related to reduced maximal oxygen uptake during heat stress." *MSSE* 44(7): 1351-1358。
- Friel, J. (2009). *The Triathlete's Training Bible* (4th ed.). VeloPress. Chapter 8: "Heart Rate Training Zones"。

#### 3. 是否行业标准

**YES**（概念层）。Cardiovascular Drift 是运动生理学中的正式术语。但量化方法（early vs late HR ratio / decoupling_pct）在行业中有多种变体，无单一金标准。本指标采用前后半程心率均值差百分比。

#### 4. 参考体系

- Coyle & González-Alonso 心血管漂移模型
- Friel 心率训练体系
- 行业实践中 TrainingPeaks 解耦率（Decoupling Rate）作为参考

#### 5. 适用 sport

| sport_type | 是否计算 | 备注 |
|---|---|---|
| running | YES | 稳态跑（需配速波动 < threshold） |
| trail_running | YES | 需过滤间歇、停顿 |
| cycling | YES（未来） | 需功率数据做配速类比 |
| hiking | YES | 低速稳态，适用 |
| swimming | NO | 心率数据可靠性不足 |
| default | NO | |

**前置条件**（必须全部满足才计算）：
- duration > 45min
- 配速变异度 < threshold（排除间歇/变速）
- 无长时间停顿（pause_duration < 10%）
- `is_steady_aerobic = True`

#### 6. 风险说明

- **降级路径**：
  - 配速波动剧烈 → 排除（不为间歇训练计算 hr_drift）
  - 停顿过多 → 排除
  - 当前 V7.6 由 decoupling_pct 临时代理（⚠️ 不是真实 hr_drift），置信度上限为 MEDIUM
- **边界条件**：
  - 高温环境（> 30°C）漂移加剧 → 非有氧退化，是热应激
  - 补给不足导致糖原耗竭 → 漂移急剧上升，属于 bonk 范畴
  - 海拔变化 → 需排除坡度段的心率数据
- **已知误用**：
  - 误用 1：对间歇训练计算 hr_drift（间歇训练的心率变化是训练设计，不是生理漂移）
  - 误用 2：把 4% 漂移当成"有氧退化"（4% 是正常范围，< 5% 为 excellent）

#### 7. confidence 条件

| confidence | 条件 |
|---|---|
| HIGH | steady_aerobic + duration > 60min + 真实 hr_drift 算法（V7.13 后） |
| MEDIUM | 当前 V7.6 代理算法（decoupling_pct）或 duration 45~60min |
| LOW | 温度 > 30°C 未补偿 / 光学心率设备 |
| UNAVAILABLE | 间歇训练 / 停顿过多 / 配速波动剧烈 / duration < 45min |

---

### 指标 7: Durability Index（耐力持久指数）

> Growth Intelligence System · Canonical Metric
> 继承复盘系统 decoupling_pct 内联算法（main.py#L4731-L4746）

#### 1. 生理意义

耐力持久指数（Durability Index）：**长时间运动中后程输出保持能力**。衡量疲劳抵抗、肌耐力、神经肌肉稳定性。

后程掉速是"疲劳累积→运动表现下降"的直接证据。耐久指数 = 后半程速度 / 前半程速度，越接近 1 越稳定。

#### 2. 数据来源

- Joyner, M.J. & Coyle, E.F. (2008). "Endurance exercise performance: the physiology of champions." *The Journal of Physiology* 586(1): 35-44。
- Noakes, T.D. (2012). "Fatigue is a brain-derived emotion that regulates the exercise behavior to ensure the protection of whole body homeostasis." *Frontiers in Physiology* 3: 82。
- Skorski, S. et al. (2019). "The relationship between the variability of pacing and performance in elite marathon runners." *IJSPP* 14(3): 310-315。

#### 3. 是否行业标准

**部分**。后程掉速分析在运动科学中是标准方法（half-split comparison），但"durability_index"作为单一 0~100 评分是脉图自建。行业实践中更常见的是按分段报告掉速率（如每 10km pace 变化），而非归一化单值。

#### 4. 参考体系

- Joyner & Coyle 耐力表现生理模型
- Noakes 中枢疲劳理论
- 脉图自建 durability_index 聚合（前 30% vs 后 30% 速度比）

#### 5. 适用 sport

| sport_type | 是否计算 | 备注 |
|---|---|---|
| running | YES | 主场景 |
| trail_running | YES | 需排除爬升段的 pace 失真 |
| cycling | YES（未来） | 需 power 分段数据 |
| hiking | YES | 低速同样适用 |
| swimming | NO | 池内配速分段与路面逻辑不同 |
| default | NO | |

**前置条件**：
- duration > 45min
- 有 speed_stream 数据
- 配速非间歇模式

#### 6. 风险说明

- **降级路径**：
  - 无可分段 speed_stream → 返回 "unknown"
  - 坡度变化大的 trail → 排除爬升段后再分段（GAP 修正）
- **边界条件**：
  - 比赛场景（负配速策略）≠ 训练场景（疲劳掉速）→ 需标记是否为比赛
  - 短时高强度（< 45min）的后半程掉速是"无氧疲劳"而非"耐力不足"
- **已知误用**：
  - 误用 1：加速后程（negative split）判定为 "durability > 100"（durability index 应 cap 在 100）
  - 误用 2：把 5km 比赛的掉速当耐力不足（5km 是短距离，不应使用 durability）

#### 7. confidence 条件

| confidence | 条件 |
|---|---|
| HIGH | speed_stream 逐秒可用 + duration > 60min + 稳态配速 |
| MEDIUM | speed_stream 有缺帧 / duration 45~60min / trail 坡度修正中 |
| LOW | 比赛配速策略 / 有明显间歇 |
| UNAVAILABLE | 无 speed_stream / duration < 45min / 配速完全不可分段 |

---

### 指标 8: Cadence Stability（步频稳定性）

> Growth Intelligence System · Canonical Metric
> 新增指标，当前复盘系统未实现

#### 1. 生理意义

步频稳定性（Cadence Stability）：运动中步频的离散度。反映**跑姿稳定性 + 疲劳控制 + 神经肌肉协调**。

- 步频越稳定 → 跑姿经济性越好 → 能量浪费越少
- 后程步频坍塌 → 疲劳信号 → 神经肌肉协调能力不足

步频是个体化参数（受身高、腿长影响），所以 stability 比 absolute cadence 更有趋势价值。

#### 2. 数据来源

- Cavanagh, P.R. & Williams, K.R. (1982). "The effect of stride length variation on oxygen uptake during distance running." *MSSE* 14(1): 30-35。
- Heiderscheit, B.C. et al. (2011). "Effects of step rate manipulation on joint mechanics during running." *MSSE* 43(2): 296-302。
- Burns, G.T. et al. (2021). "Running cadence and the influence on running economy: a review." *Sports Medicine* 51(8): 1635-1653。

#### 3. 是否行业标准

**部分**。步频分析在运动科学中常见，但"cadence_stability"作为单独 trend 指标非行业标准。行业更多关注 optimal cadence（最佳步频），stability 视角是脉图差异化方向。

#### 4. 参考体系

- Cavanagh / Heiderscheit 步频与跑步经济性研究
- Burns et al. (2021) 系统综述
- 脉图自建 stability 框架（std + late-run decay）

#### 5. 适用 sport

| sport_type | 是否计算 | 备注 |
|---|---|---|
| running | YES | 主场景 |
| trail_running | YES | 地形变化影响步频，需分段 |
| hiking | NO | 步频非关键指标 |
| cycling | NO | 使用 cadence（踏频），另有节奏稳定性 |
| swimming | NO | 划频是不同维度（stroke rate） |
| default | NO | |

#### 6. 风险说明

- **降级路径**：无 cadence_stream → 返回 "unknown"
- **边界条件**：
  - 上下坡对步频影响大 → trail 需去趋势化后计算 std
  - 部分跑表无逐秒 cadence → Garmin 智能 recording 模式下 cadence 降采样，影响 std 精度
- **已知误用**：
  - 误用 1：把高步频等同于"好跑姿"（步频有个体最优值，不是越高越好）
  - 误用 2：在公路跑和越野跑之间比较 stability（地形差异大，不可比）

#### 7. confidence 条件

| confidence | 条件 |
|---|---|
| HIGH | cadence_stream 逐秒可用 + road running + duration > 30min |
| MEDIUM | trail running 或 cadence 降采样 |
| LOW | 间歇训练（步频波动是训练设计） |
| UNAVAILABLE | 无 cadence_stream / duration < 20min |

---

### 指标 9: Training Load（训练负荷）

> Growth Intelligence System · Canonical Metric
> 新增指标，当前复盘系统未实现

#### 1. 生理意义

训练负荷（Training Load）：**单次训练造成的总体生理压力**。综合考虑运动时长和强度分布，而不是简单的"时间 × 平均心率"。

长期视角：acute (7d) 与 chronic (42d) 的比值（load ratio）反映疲劳风险。

#### 2. 数据来源

- Banister, E.W. (1991). "Modeling elite performance." In: *Physiological Testing of the High-Performance Athlete* (2nd ed.). Human Kinetics. pp. 403-425。原版 TRIMP 公式。
- Foster, C. et al. (2001). "A new approach to monitoring exercise training." *Journal of Strength and Conditioning Research* 15(1): 109-115。Session RPE 方法。
- ACSM (2021). *Guidelines for Exercise Testing and Prescription* (11th ed.). Chapter 5: "General Principles of Exercise Prescription"。

#### 3. 是否行业标准

**部分**。TRIMP（Training Impulse）概念在运动科学中有共识（Banister 1991），但具体权重系数有多种方案。本指标采用 HR zone weighted duration（简化 TRIMP），不使用 Session RPE（脉图当前无主观 RPE 采集）。

#### 4. 参考体系

- Banister TRIMP 模型
- Foster Session RPE（未来可补充）
- 脉图简化 HR-zone-weighted duration

#### 5. 适用 sport

| sport_type | 是否计算 | 备注 |
|---|---|---|
| running | YES | HR zone 分布权重 |
| trail_running | YES | 同上 |
| cycling | YES | 有功率时优先 power-based TRIMP |
| hiking | YES | 同上 |
| swimming | YES | HR 可靠性标 LOW confidence |
| default | YES | 所有有 avg_hr 的活动均可计算 |

**HR zone 权重**：

| Zone | 权重 |
|------|------|
| Z1（< 55% max） | 1 |
| Z2（55-70%） | 2 |
| Z3（70-80%） | 3 |
| Z4（80-90%） | 5 |
| Z5（> 90%） | 8 |

```text
training_load = duration_min × Σ(zone_weight × zone_time_pct)
```

#### 6. 风险说明

- **降级路径**：无 avg_hr / hr_zone_distribution → 返回 "unknown"
- **边界条件**：
  - 光学心率设备在 Z4/Z5 区误差大（±5-10%）→ load 可能被高估
  - 升坡/越野跑 HR 偏高 → load 可能被高估（心率和运动强度解耦）
- **已知误用**：
  - 误用 1：把 training_load 当 calorie 替代（load 是生理压力，非能耗）
  - 误用 2：跨运动类型比较 load（跑步 HR 权重 ≠ 游泳 HR 权重）

#### 7. confidence 条件

| confidence | 条件 |
|---|---|
| HIGH | 胸带心率 + hr_zone_distribution 完整 + duration > 30min |
| MEDIUM | 光学心率 / 游泳 / 无 zone distribution（基于 avg_hr 推算） |
| LOW | 无 avg_hr / 设备心率异常 |
| UNAVAILABLE | 无 avg_hr 且无可推算的心率数据 |

---

## 三、已废弃指标博物馆 (Deprecated Indicators)

> 任何被 Architect Review 拒绝的指标，必须记录在此节，写明拒绝原因和替代方案，防止后续误用复活。

### 废弃 1: SWOLF → Cardio Load

- **拒绝原因**：生理边界错误。SWOLF = 单趟泳池长度耗时 + 划水次数，衡量**技术效率**（游泳经济性），**不是心肺负荷**。SWOLF 高反而代表划水效率差，与心率无直接关系。
- **替代方案**：
  - cardio_load 仍用 HR 比例（见指标 2）
  - SWOLF 单独归入 "technique_efficiency" 维度（未来功能，不在 V7.8 范围）
- **历史决定**：2026-Q2 Architect Review §10

### 废弃 2: Power Smoothness

- **拒绝原因**：非标准术语，无统一定义。Coggan / TrainingPeaks / WKO 体系内**没有** "power_smoothness" 这个指标。
- **替代方案**：用 **VI = NP / AvgPower**（见指标 3，行业标准）
- **历史决定**：2026-Q2 Architect Review §10

### 废弃 3: 自定义 Swim MET 公式

- **拒绝原因**：误差巨大。同样速度下，新手与专业选手耗能差异可达 2 倍；自建公式（如 `MET = 2.0 + 8.0 * (mps/0.4)`）系统高估 80%。
- **替代方案**：
  - 第一阶段（V7.8）：游泳 calorie 走 **ACSM MET 查找表**（MET = 6/8/10 按 pace zone 映射）
  - 第二阶段（未来）：引入水温校正（10°C vs 25°C 差 30-40%）
- **历史决定**：2026-Q2 Architect Review §10

---

## 四、未来指标入源流程

### 4.1 入源审查表

| 审查项 | 必须满足 |
|---|---|
| 文献来源 | 至少 1 篇同行评审论文 / 1 本行业权威书籍 / 1 个公认标准（ACSM/Coggan/Burke 等）|
| 7 项标注 | 全部填写完整，无空字段 |
| 适用 sport 白名单 | 明确，未列入白名单的 sport 一律不应用 |
| 风险说明 | 至少 1 条边界条件 + 1 条降级路径 |
| confidence 条件 | 全部 4 级（HIGH/MEDIUM/LOW/UNAVAILABLE）均有对应条件 |
| Architect Review | 至少 1 次正式 review 决议记录 |

### 4.2 禁止入源的场景

| 场景 | 理由 |
|---|---|
| 无来源的"AI 推断指标" | 黑盒，无法审计 |
| 行业术语误用（如 SWOLF cardio）| 生理边界错误 |
| 自造无定义指标（如 power_smoothness）| 沟通成本极高 |
| 自建误差大且有标准替代的公式（如 swim MET）| 风险大于收益 |
| 单一自测样本验证的指标 | n=1 无统计意义 |

### 4.3 退出机制

- 已发布指标如发现新证据支持废弃 → 移入 §三 已废弃指标博物馆
- 退出后代码层（metrics_resolver.py）必须同步删除该指标，严禁留 zombie 代码

---

## 五、变更日志

| 日期 | 版本 | 变更 | Architect |
|---|---|---|---|
| 2026-06-05 | 2026-Q2 | 初始奠基，含 4 个可发布指标 + 3 个废弃指标 | Review §9 §10 |
| 2026-06-05 | 2026-Q2-1 | GIS 扩展：新增 5 条 canonical metric（efficiency_score / hr_drift / durability_index / cadence_stability / training_load）；模板从 6 项扩为 7 项（含 confidence 条件）；补充已有 4 条指标的 confidence 条件 | Final Architecture Review |
| TBD | TBD | 待补：Keytel 2005 / ACSM MET 表 / Friel 训练圣经 完整引用 | TBD |
| TBD | TBD | 待补：WBGT 热指数（指标 10 候选）| TBD |

---

> 本文件是脉图运动生理模型的**唯一权威源**。任何代码 / prompt / UI 涉及运动生理指标，必须能在此文件找到出处。
> 违反本文件入源规则的代码，Architect Review 门禁拒绝合入。
