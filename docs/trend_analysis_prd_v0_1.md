# 趋势分析 PRD v0.1

> **状态**: 初稿,待评审  
> **日期**: 2026-06-20  
> **适用模块**: 新功能模块「趋势分析」  
> **数据源**: 用户画像 + FIT 文件解析结果 + Resolver 派生指标  
> **核心原则**: 时间序列分析必须服务训练决策,不得把单日波动包装成长期趋势

---

## 0. 一句话结论

「趋势分析」不是指标折线图集合,而是基于时间轴分析用户训练负荷、能力表现、恢复状态和运动效率变化,并用可解释的运动科学模型回答:

```text
最近训练是否在让用户变强?
当前表现变化更像能力变化,还是疲劳/恢复变化?
训练负荷增长是否合理?
哪些趋势可信,哪些趋势数据不足?
```

---

## 1. 功能定位

### 1.1 产品目标

为用户提供一个长期训练状态面板,把分散在用户画像和 FIT 活动记录中的指标转化为可理解的趋势判断。

核心目标:

- 识别能力提升、停滞、下降。
- 识别短期疲劳、长期负荷、恢复压力。
- 解释同一指标变化背后的可能原因。
- 用数据可信度限制结论边界。
- 为后续 AI 训练建议、周期化训练计划、比赛准备建议提供稳定数据层。

### 1.2 非目标

本模块 v0.1 不做以下事情:

- 不输出医学诊断。
- 不预测伤病概率。
- 不根据单次训练直接判断长期能力变化。
- 不替代教练制定完整训练计划。
- 不把 Garmin / COROS 等平台的私有评分原样复刻为黑盒分数。
- 不在前端直接计算核心运动生理指标。

### 1.3 命名约束

推荐中文模块名:

```text
趋势分析
```

可选英文内部名:

```text
Trend Analysis
```

禁止命名:

```text
伤病预测
健康诊断
能力评级
风险预警
训练处方
```

---

## 2. 用户场景

### 2.1 核心用户

| 用户类型 | 需求 | 典型问题 |
|---|---|---|
| 跑步用户 | 判断有氧基础、阈值、疲劳 | 最近跑得慢是退步了吗? |
| 骑行用户 | 判断 FTP / 功率效率 / 负荷 | 最近功率提升是否真实? |
| 越野/徒步用户 | 判断爬升耐力和长距离能力 | 最近山地能力有没有提升? |
| 泛耐力用户 | 看训练一致性和恢复 | 最近训练是否过量? |

### 2.2 使用场景

- 每周复盘:查看过去 7 / 28 / 42 天训练状态。
- 月度复盘:查看能力趋势、训练一致性、效率变化。
- 赛前准备:判断疲劳是否过高,能力是否处于上升期。
- 训练停滞排查:区分负荷不足、恢复不足、强度结构不合理。

---

## 3. 信息架构

v0.1 建议拆成 4 个一级区块:

```text
趋势总览
训练负荷
能力表现
恢复与效率
```

### 3.1 趋势总览

展示 4 张核心结论卡:

| 卡片 | 回答的问题 | 主要输入 |
|---|---|---|
| 能力趋势 | 最近是否变强 | VO2max、阈值、最佳努力、同心率配速/功率 |
| 负荷趋势 | 训练是否持续且合理 | 周训练量、ATL、CTL、TSB、强度分布 |
| 恢复趋势 | 当前是否疲劳 | HRV、静息心率、睡眠、TSB |
| 效率趋势 | 同等输入下输出是否更好 | 心率-配速、功率-速度、心率漂移 |

每张卡必须包含:

- 当前状态。
- 相比上一周期的变化。
- 趋势方向。
- 可信度。
- 一句解释。
- 一个建议动作。

### 3.2 训练负荷

展示长期训练投入与疲劳平衡:

- 周训练时长。
- 周训练距离。
- 周累计爬升。
- 心率/功率区间时间。
- ATL / CTL / TSB。
- 负荷突增提示。
- 训练单调性。

### 3.3 能力表现

展示用户的运动能力变化:

- VO2max 趋势。
- 阈值心率 / 阈值配速 / FTP 趋势。
- 最佳努力曲线。
- 同心率下配速趋势。
- 同功率下速度趋势。
- 跑步 / 骑行 / 徒步等运动类型筛选。

### 3.4 恢复与效率

展示恢复状态和运动经济性:

- HRV 趋势。
- 静息心率趋势。
- 睡眠趋势。
- 心率漂移。
- 有氧效率。
- 功率效率。
- 同路线对比。

---

## 4. 数据源契约

### 4.1 用户画像字段

| 字段 | 当前来源 | 用途 |
|---|---|---|
| `age` | profile | 年龄相关提示、最大心率兜底 |
| `gender` | profile | 个体背景,不直接做能力评价 |
| `weight` | profile | 功率体重比、能耗、负荷解释 |
| `resting_hr` | profile | HRR 区间、恢复趋势 |
| `max_hr` | profile | HR 区间、HRR 区间、训练负荷 |
| `hrv_baseline` | profile | 恢复基线 |
| `vo2max` | profile / Garmin / COROS | 能力趋势 |
| `avg_sleep_hours` | profile / 平台同步 | 恢复背景 |
| `lactate_threshold_hr` | profile / 平台同步 | 阈值区间、能力趋势 |
| `lactate_threshold_pace` | profile / 平台同步 | 跑步阈值趋势 |
| `ftp` / `ftp_watts` | profile / 平台同步 | 骑行功率趋势 |

约束:

- 用户画像是长期背景,不是每次活动的真值。
- 用户画像字段过期时必须降级可信度。
- 无 `resting_hr` 或 `max_hr` 时,不得计算 HRR 区间。

### 4.2 FIT 活动级字段

| 字段 | FIT / canonical 来源 | 用途 |
|---|---|---|
| `start_time` | session | 时间轴 X 轴 |
| `sport_type` | session sport/sub_sport | 运动类型筛选 |
| `duration_sec` | total_timer_time | 训练量、负荷 |
| `distance_m` | total_distance | 训练量、配速 |
| `calories` | total_calories | 能耗参考 |
| `gain_m` | total_ascent | 爬升负荷 |
| `descent_m` | total_descent | 山地负荷 |
| `avg_hr` | avg_heart_rate | 强度、负荷、效率 |
| `max_hr` | max_heart_rate | 强度上限 |
| `avg_speed` | avg_speed | 配速/速度趋势 |
| `avg_cadence` | avg_cadence | 步频/踏频趋势 |
| `avg_power` | avg_power | 骑行功率趋势 |

### 4.3 FIT record 级字段

| 字段 | 用途 |
|---|---|
| `timestamp` | 构造时序曲线 |
| `heart_rate` | HR 曲线、TRIMP、漂移 |
| `speed` | 配速/速度曲线、最佳努力 |
| `distance` | 分段、最佳努力、长距离衰减 |
| `altitude` | 爬升、坡度修正 |
| `cadence` | 步频/踏频 |
| `power` | 功率曲线、FTP/CP、TSS 类指标 |
| `temperature` | 热环境修正 |

### 4.4 数据流原则

```text
FIT / profile
  -> canonical storage
  -> MetricsResolver / TrendResolver 派生
  -> API 输出 trend_analysis
  -> Frontend 只渲染
```

强制约束:

- 前端不得计算 ATL / CTL / TSB / TRIMP / 有氧效率 / 心率漂移等核心指标。
- AI 不写回 canonical。
- AI 可以消费趋势摘要,但不得重新计算趋势指标。
- 所有趋势结论必须带 `confidence` 和 `basis`。

---

## 5. 指标体系

### 5.1 指标分层

| 层级 | 含义 | 示例 |
|---|---|---|
| 原始指标 | FIT 或 profile 直接字段 | 心率、配速、功率、VO2max |
| 派生指标 | 可复算的工程指标 | TRIMP、ATL、CTL、心率漂移 |
| 复合指标 | 多指标解释性聚合 | 有氧基础指数、疲劳压力指数 |
| 解释结论 | 面向用户的自然语言 | 当前疲劳偏高,能力趋势稳定 |

### 5.2 v0.1 必做指标

| 指标 | 类型 | 适用 sport | 最小数据 |
|---|---|---|---|
| 周训练时长 | 原始聚合 | all | 2 周活动 |
| 周训练距离 | 原始聚合 | running/cycling/hiking 等 | 2 周活动 |
| 周累计爬升 | 原始聚合 | trail/hiking/mountain_biking | 2 周活动 |
| 强度区间分布 | 派生 | 有 HR 或 power 的活动 | 4 次有效活动 |
| ATL | 派生 | all endurance | 14 天数据 |
| CTL | 派生 | all endurance | 42 天数据,不足时降级 |
| TSB | 派生 | all endurance | ATL + CTL |
| 有氧效率 | 派生 | running/cycling | 6 次同类活动 |
| 心率漂移 | 派生 | running/cycling/hiking | 单次 45 分钟以上且 HR 有效 |
| VO2max 趋势 | 原始/画像 | 有 profile vo2max | 至少 2 个时间点,否则只显示当前 |
| 阈值趋势 | 原始/画像/派生 | running/cycling | 至少 2 个时间点 |
| HRV 趋势 | 原始/画像 | 有 hrv_baseline 或日更 HRV | 7 天以上 |
| 静息心率趋势 | 原始/画像 | all | 7 天以上 |

### 5.3 v0.1 推荐复合指标

#### 5.3.1 有氧基础指数

用途:衡量用户低强度有氧基础是否改善。

组成:

- Zone 1/2 时长占比。
- 低强度训练频次。
- 同心率配速/功率变化。
- 长训练心率漂移。

输出:

```json
{
  "aerobic_base_index": {
    "score": 72,
    "trend": "up",
    "confidence": "medium",
    "contributors": [
      "zone2_time_increased",
      "hr_pace_efficiency_improved",
      "decoupling_stable"
    ]
  }
}
```

#### 5.3.2 阈值能力指数

用途:衡量接近阈值区间的持续输出能力。

组成:

- 20 分钟 / 40 分钟 / 60 分钟最佳努力。
- 阈值配速或 FTP。
- 阈值心率附近的稳定输出时长。

注意:

- 无功率时,骑行阈值能力可信度降低。
- 越野跑不应直接用原始配速比较,需坡度修正或降级。

#### 5.3.3 疲劳压力指数

用途:识别当前是否处于短期疲劳累积状态。

组成:

- ATL 相对 CTL 的偏离。
- TSB。
- HRV 是否低于个人基线。
- 静息心率是否高于个人基线。
- 睡眠是否低于个人基线。

注意:

- 只能输出「恢复压力较高」,不得输出「过度训练」诊断。

#### 5.3.4 训练一致性指数

用途:衡量训练是否稳定、可持续。

组成:

- 周训练频次。
- 周训练时长波动。
- 连续训练周数。
- 休息日分布。
- 低强度基础训练占比。

---

## 6. 计算规则

### 6.1 时间窗口

默认窗口:

| 窗口 | 用途 |
|---|---|
| 7 天 | 短期负荷、恢复变化 |
| 28 天 | 个人基线、近期趋势 |
| 42 天 | 长期训练负荷 |
| 90 天 | 能力趋势、最佳努力 |
| 180 天 | 历史对比 |

### 6.2 趋势方向

趋势方向枚举:

```text
up
down
stable
mixed
insufficient_data
```

判断建议:

- 使用最近 4-8 周斜率判断趋势。
- 变化幅度小于最小有意义变化时标记为 `stable`。
- 多个子指标方向冲突时标记为 `mixed`。
- 数据不足时必须标记 `insufficient_data`。

### 6.3 ATL / CTL / TSB

建议定义:

```text
daily_load = 每日训练负荷
ATL = daily_load 的 7 天 EWMA
CTL = daily_load 的 42 天 EWMA
TSB = CTL - ATL
```

daily_load 优先级:

1. power-based load,骑行有功率时优先。
2. HR-based TRIMP,有心率和 profile HR 时使用。
3. duration-based load,无心率/功率时降级。

输出约束:

- 不得把 TSB 直接解释为绝对好坏。
- TSB 低只能说明短期疲劳较高。
- CTL 上升说明长期训练负荷上升,不等于能力必然提升。

### 6.4 TRIMP

使用场景:

- 没有功率数据,但有心率数据。
- 需要跨跑步、徒步、骑行做统一训练负荷估计。

输入:

- duration。
- heart_rate。
- resting_hr。
- max_hr。

降级:

- 无 `resting_hr` 时可用 `%HRmax` 粗略估计,confidence 降为 LOW。
- 无 `max_hr` 时不可计算 HR-based TRIMP。

### 6.5 强度区间

优先级:

1. 功率区间:有 FTP / 功率曲线时。
2. HRR 区间:有 resting_hr + max_hr 时。
3. %HRmax 区间:仅有 max_hr 时。
4. RPE 或时长降级:v0.1 不做。

输出:

```json
{
  "intensity_distribution": {
    "low_pct": 78.2,
    "moderate_pct": 14.5,
    "high_pct": 7.3,
    "basis": "hrr_zones",
    "confidence": "high"
  }
}
```

### 6.6 有氧效率

跑步:

```text
aerobic_efficiency = speed / heart_rate
```

骑行:

```text
power_hr_efficiency = power / heart_rate
speed_power_efficiency = speed / power
```

要求:

- 只在低强度或稳定段比较。
- 排除暂停、极短活动、异常心率。
- 越野跑、山地骑行必须考虑爬升或降低可信度。

### 6.7 心率漂移

建议定义:

```text
decoupling = 后半程效率 / 前半程效率 - 1
```

可用效率:

- 跑步:配速/心率或速度/心率。
- 骑行:功率/心率。

最小条件:

- 活动时长 >= 45 分钟。
- 心率覆盖率 >= 80%。
- 前后半程强度相对稳定。

解释:

- 漂移下降:长时间稳定输出能力改善。
- 漂移上升:可能是疲劳、热环境、补给不足、爬升变化或配速不稳。

### 6.8 最佳努力曲线

v0.1 时间段:

```text
1 min
5 min
10 min
20 min
40 min
60 min
```

跑步:

- 输出最佳平均配速 / 速度。
- 越野跑使用 GAP 或标记低可信。

骑行:

- 输出最佳平均功率。
- 若有体重,可输出 W/kg。

约束:

- 必须保留最佳努力来源活动 ID 和日期。
- 不得把短间歇中的 20 分钟片段直接等同于正式测试。

---

## 7. 可信度规则

### 7.1 confidence 枚举

```text
HIGH
MEDIUM
LOW
UNAVAILABLE
```

### 7.2 通用规则

| confidence | 条件 |
|---|---|
| HIGH | 数据量充足,关键传感器齐全,运动类型一致,异常少 |
| MEDIUM | 数据量可用,但缺少部分关键字段或运动类型混杂 |
| LOW | 数据少、传感器缺失、环境差异大、仅用兜底模型 |
| UNAVAILABLE | 不满足最小计算条件 |

### 7.3 数据量门槛

| 分析类型 | HIGH | MEDIUM | LOW |
|---|---|---|---|
| 训练负荷 | >= 42 天活动记录 | 14-41 天 | 7-13 天 |
| 能力趋势 | 8 周内 >= 12 次同类活动 | 6-11 次 | 2-5 次 |
| 恢复趋势 | >= 14 天 HRV/RHR | 7-13 天 | 3-6 天 |
| 效率趋势 | >= 8 次可比活动 | 4-7 次 | 2-3 次 |

### 7.4 可信度降级原因

降级原因枚举:

```text
missing_heart_rate
missing_power
missing_resting_hr
missing_max_hr
insufficient_history
mixed_sport_types
high_environment_variance
short_activity_duration
low_sensor_coverage
profile_stale
route_not_comparable
```

---

## 8. 输出契约

### 8.1 API 顶层结构

建议路径:

```text
record.detail.trend_analysis
```

或长期趋势接口:

```text
GET /api/trend-analysis?range=90d&sport=running
```

响应示例:

```json
{
  "ok": true,
  "trend_analysis": {
    "range_days": 90,
    "sport_filter": "running",
    "generated_at": "2026-06-20T12:00:00+08:00",
    "summary": {
      "ability": {
        "status": "improving",
        "trend": "up",
        "confidence": "medium",
        "basis": ["hr_pace_efficiency", "best_effort_20m"],
        "message": "过去 8 周低强度同心率配速改善,20 分钟最佳努力小幅提升。"
      },
      "load": {
        "status": "productive",
        "trend": "up",
        "confidence": "high",
        "basis": ["ctl", "weekly_duration"],
        "message": "长期训练负荷持续上升,短期负荷未明显超出长期基线。"
      },
      "recovery": {
        "status": "watch",
        "trend": "mixed",
        "confidence": "medium",
        "basis": ["tsb", "hrv_baseline"],
        "message": "短期疲劳偏高,但 HRV 未明显低于个人基线。"
      },
      "efficiency": {
        "status": "improving",
        "trend": "up",
        "confidence": "medium",
        "basis": ["aerobic_efficiency", "decoupling"],
        "message": "稳定低强度活动中的心率-配速效率有所改善。"
      }
    },
    "metrics": {},
    "composite_indices": {},
    "data_quality": {}
  }
}
```

### 8.2 状态枚举

能力:

```text
improving
stable
declining
mixed
insufficient_data
```

负荷:

```text
building
productive
spiking
reduced
insufficient_data
```

恢复:

```text
fresh
balanced
watch
strained
insufficient_data
```

效率:

```text
improving
stable
declining
mixed
insufficient_data
```

### 8.3 指标对象标准

每个指标必须符合以下结构:

```json
{
  "key": "aerobic_efficiency",
  "label": "有氧效率",
  "unit": "m_per_sec_per_bpm",
  "current": 0.043,
  "previous": 0.041,
  "delta_pct": 4.9,
  "trend": "up",
  "confidence": "medium",
  "basis": {
    "window_days": 56,
    "activity_count": 11,
    "sport": "running"
  },
  "degradation_reasons": [],
  "source_activity_ids": [123, 127, 135]
}
```

---

## 9. UI 设计要求

### 9.1 总览卡片

每张卡片展示:

- 标题:能力趋势 / 训练负荷 / 恢复状态 / 运动效率。
- 状态标签。
- 关键变化值。
- 迷你趋势图。
- 可信度标签。
- 简短解释。

示例:

```text
有氧效率
+4.9% / 8 周
可信度: 中
在 140-150 bpm 区间内,你的平均配速有所提升,说明低强度输出效率改善。
```

### 9.2 趋势图

建议图表:

- 折线图:指标随时间变化。
- 区域图:ATL / CTL / TSB。
- 堆叠柱状图:强度区间分布。
- 最佳努力曲线:时长-表现曲线。
- 散点图:心率-配速 / 功率-心率。

图表要求:

- X 轴必须是时间。
- 必须支持运动类型筛选。
- 必须显示有效样本数。
- 数据不足时显示空状态,不得伪造趋势。
- 异常点可标记,但不默认删除。

### 9.3 文案规则

允许:

```text
短期疲劳偏高
恢复压力较大
训练负荷增长较快
有氧效率有所改善
当前数据不足以判断趋势
```

禁止:

```text
你已经过度训练
你将会受伤
你的心肺有问题
你的能力确定下降
这是医学风险
```

---

## 10. MVP 范围

### 10.1 M0:只读趋势总览

目标:先把数据结构和基础趋势跑通。

包含:

- 90 天运动筛选。
- 周训练时长 / 距离 / 爬升。
- ATL / CTL / TSB。
- 强度区间分布。
- 有氧效率。
- HRV / 静息心率展示。
- 4 张总览卡。
- confidence 和 degradation reasons。

不包含:

- AI 长文本建议。
- 周期化训练计划。
- 伤病风险。
- 复杂预测模型。

### 10.2 M1:能力表现页

包含:

- 最佳努力曲线。
- VO2max 趋势。
- 阈值趋势。
- 同心率配速 / 同功率速度。
- 同路线对比。

### 10.3 M2:恢复与效率增强

包含:

- HRV / RHR 日级趋势。
- 睡眠趋势。
- 心率漂移。
- 热环境影响提示。
- 长距离后半程衰减。

### 10.4 M3:AI 解释层

包含:

- 消费 `trend_analysis` 输出。
- 给出简短解释和下一步建议。
- 不重新计算指标。
- 不写回 canonical。

---

## 11. 数据质量与异常处理

### 11.1 传感器覆盖率

每次活动需计算:

```text
hr_coverage_pct
power_coverage_pct
speed_coverage_pct
cadence_coverage_pct
temperature_coverage_pct
```

覆盖率低于 80% 时,相关指标降级。

### 11.2 异常值处理

异常类型:

- 心率为 0 或超过生理合理范围。
- GPS 漂移导致速度尖峰。
- 功率长时间为 0 但活动未暂停。
- 海拔跳变。
- 活动时长过短。

处理原则:

- v0.1 可标记异常,不强制删除。
- 指标计算可排除明显无效点,但必须记录排除比例。
- UI 不展示过度技术细节,但 API 保留数据质量信息。

### 11.3 可比性判断

效率趋势必须判断活动是否可比:

- 同 sport。
- 相近强度。
- 相近活动类型。
- 路线/坡度/温度差异不过大。

不可比时:

```text
trend = mixed 或 insufficient_data
confidence = LOW
degradation_reasons 包含 route_not_comparable / high_environment_variance
```

---

## 12. 运动科学依据边界

### 12.1 可采用的成熟模型

| 模型 | 用途 | 备注 |
|---|---|---|
| HRR / %HRmax 分区 | 心率强度 | ACSM 体系常见 |
| Coggan 功率分区 | 骑行强度 | 有 FTP 和功率时优先 |
| TRIMP | 心率训练负荷 | 无功率时可用 |
| ATL / CTL / TSB | 负荷与疲劳平衡 | 解释为训练状态,不做绝对判断 |
| 心率漂移 | 有氧耐力稳定性 | 需稳定长训练 |
| 最佳努力曲线 | 能力表现 | 需标注来源和上下文 |
| HRV / RHR 基线偏离 | 恢复状态 | 只看个人趋势,不看单日绝对值 |

### 12.2 谨慎采用的模型

| 模型 | 风险 | v0.1 策略 |
|---|---|---|
| ACWR | 伤病预测争议较大 | 只用于负荷突增提示,不输出伤病风险 |
| VO2max 设备估算 | 受算法和设备影响 | 作为参考趋势,不作为唯一能力指标 |
| 单次最佳努力推 FTP/阈值 | 受训练结构影响 | 标注来源和低/中可信度 |
| AI 总结 | 容易过度解释 | 只能基于结构化指标输出 |

---

## 13. 验收标准

### 13.1 产品验收

- 用户能在 30 秒内理解最近训练状态是上升、稳定、疲劳还是数据不足。
- 每个趋势结论都有可信度。
- 数据不足时明确说明原因。
- 没有医学化、伤病预测化文案。
- 复合指标可以展开看到主要贡献因子。

### 13.2 数据验收

- 同一批 FIT 文件重复导入,趋势结果稳定。
- 缺少 HR 时,HR-based 指标不可用或降级。
- 缺少 power 时,骑行功率指标不可用或降级。
- 缺少 profile `resting_hr` / `max_hr` 时,HRR 不计算。
- 少于最小样本数时,不输出强趋势判断。

### 13.3 工程验收

- 核心指标由 Resolver 层输出。
- 前端只消费 `trend_analysis`。
- API 输出包含 `confidence`、`basis`、`degradation_reasons`。
- 单元测试覆盖数据不足、传感器缺失、运动类型混杂、异常点。
- 文案测试覆盖禁止用语。

---

## 14. 待决策问题

| 问题 | 选项 | 建议 |
|---|---|---|
| v0.1 是否新建 `TrendResolver` | 新建 / 放入 `MetricsResolver` | 新建,避免 `MetricsResolver` 继续膨胀 |
| 长期趋势是否单独 API | 单独接口 / 活动详情内嵌 | 单独接口,趋势是跨活动数据 |
| 是否支持多平台画像时间序列 | 只当前值 / 历史快照 | M0 当前值,M1 引入画像快照 |
| 是否做 AI 总结 | M0 做 / M3 做 | M3 做,先稳定结构化输出 |
| 是否展示复合分数 | 展示 / 只展示子指标 | 展示,但必须可解释展开 |

---

## 15. 建议开发拆分

### P0:数据与契约

- 定义 `trend_analysis` schema。
- 新建 `TrendResolver`。
- 聚合活动历史数据。
- 计算基础数据质量。
- 输出 confidence / degradation reasons。

### P1:负荷与总览

- 周训练量。
- 强度区间分布。
- ATL / CTL / TSB。
- 4 张总览卡。

### P2:能力与效率

- 有氧效率。
- 心率漂移。
- 最佳努力曲线。
- VO2max / 阈值趋势。

### P3:恢复与 AI

- HRV / 静息心率趋势。
- 睡眠趋势。
- AI 消费结构化趋势摘要。
- 用户可读建议文案。

---

## 16. 参考实现输出样例

```json
{
  "trend_analysis": {
    "range_days": 90,
    "sport_filter": "running",
    "summary": {
      "ability": {
        "status": "improving",
        "trend": "up",
        "confidence": "medium",
        "message": "低强度同心率配速改善,但阈值数据不足,能力提升判断为中等可信。"
      },
      "load": {
        "status": "productive",
        "trend": "up",
        "confidence": "high",
        "message": "长期训练负荷连续 5 周上升,短期负荷未出现明显突增。"
      },
      "recovery": {
        "status": "watch",
        "trend": "mixed",
        "confidence": "medium",
        "message": "TSB 偏低提示短期疲劳上升,但 HRV 未明显低于个人基线。"
      },
      "efficiency": {
        "status": "improving",
        "trend": "up",
        "confidence": "medium",
        "message": "稳定有氧活动中的心率-配速效率有所改善。"
      }
    },
    "data_quality": {
      "activity_count": 24,
      "valid_hr_activity_count": 21,
      "valid_power_activity_count": 0,
      "degradation_reasons": ["missing_power"]
    }
  }
}
```

---

## 17. 版本记录

| 版本 | 日期 | 说明 |
|---|---|---|
| v0.1 | 2026-06-20 | 初稿,定义产品定位、指标体系、计算规则、输出契约和 MVP 范围 |
