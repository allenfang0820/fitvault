# P3b 骑行复盘功率效率与耐力专项化提示词

> 任务类型：P3b-cycling 后端骑行专项指标语义增强
> 前置条件：P0-cycling 契约、P1-cycling 快照入源、P2-cycling AI prompt、P3-cycling 专项指标、P4-cycling 主图模式、P5-cycling 指标卡专项化均已完成
> 核心目标：让骑行活动的 `metrics.efficiency` 与 `metrics.durability` 从跑步/速度口径升级为功率口径，并保持跑步/general 行为不变
> 不包含：前端 ECharts 改造、指标卡布局改造、AI prompt/schema 变更、DB schema 迁移、FTP/TSS/IF/W/kg/功率区间模型、真实 LLM 联调

---

## 零、执行前重新思考

执行本任务前，先重新确认方案是否合理：

- P3 已实现 `metrics.power_variability` 与 `metrics.pedaling_stability`，解决了骑行专项事实指标缺位问题。
- P4 已让骑行主图与跑步不同，默认突出功率、心率、海拔，并支持踏频图层。
- P5 已让骑行指标卡突出 VI 与踏频稳定性，但 `后程效率变化 / 后程保持参考` 仍是辅助口吻，因为后端 `efficiency / durability` 尚未功率化。
- 因此下一步做 P3b 是合理的：先把后端事实口径补齐，再考虑前端是否进一步改名、重排或强化展示。
- 本任务不应命名为 P6，因为 P6 已用于 AI 洞察；继续使用 P3b 可以避免任务编号和职责冲突。

关键判断：

- 骑行 `efficiency` 不应继续用跑步配速/速度效率语义；有功率和心率时，应表达“单位心率输出功率”的功率心肺效率。
- 骑行 `durability` 不应继续只看速度后程保持；有同轴功率曲线时，应表达“后程功率保持能力”。
- 无功率、无心率或功率曲线不足时，必须诚实降级；不得用速度、配速、AI 或前端推断补齐功率结论。

如果执行前发现 P1/P3 的 power 入源或数据质量判断不稳定，先修快照入源缺陷，不要在 P3b 中用 mock、records、points、前端曲线或 AI 绕过。

---

## 一、架构契约核对

执行本任务前必须先阅读并遵守：

- `docs/p0_cycling_fatigue_review_contract_prompt.md`
- `docs/p0_cycling_fatigue_review_contract_completion_report.md`
- `docs/p1_cycling_fatigue_review_snapshot_prompt.md`
- `docs/p1_cycling_fatigue_review_snapshot_completion_report.md`
- `docs/p2_cycling_fatigue_review_ai_prompt.md`
- `docs/p2_cycling_fatigue_review_ai_prompt_completion_report.md`
- `docs/p3_cycling_fatigue_review_metrics_prompt.md`
- `docs/p3_cycling_fatigue_review_metrics_completion_report.md`
- `docs/p4_cycling_fatigue_review_chart_completion_report.md`
- `docs/p5_cycling_fatigue_review_metric_cards_completion_report.md`
- `docs/js_api_contract.json` 中 `get_fatigue_review`
- `docs/fatigue_review_realignment_plan_v1.md`
- 全局架构契约 `fit-arch-contrac`

硬性约束：

- `get_fatigue_review(activity_id)` 仍是复盘页面唯一权威数据源。
- 后端 metrics 是事实来源；前端和 AI 均不得计算、补齐、推断 `efficiency / durability`。
- 本任务只允许改变骑行活动的 `metrics.efficiency / metrics.durability` 语义；跑步/general 行为必须保持。
- 指标只能来自后端 canonical snapshot、resolver 结果、DB canonical 字段和同轴曲线。
- 不写 DB，不新增 DB 字段，不改 migration。
- 不改 `llm_backend.py`，不改 AI prompt，不改 AI 输出 schema。
- 禁止引入 FTP、IF、TSS、W/kg、功率区间、长期能力模型。
- 禁止从 power curve 重算 NP；NP 仍只作为 P3 `power_variability` 的既有输入。
- 禁止使用 shadow_diff、debug-only 字段、records、points、原始 FIT 消息作为 API 返回。
- 所有指标必须有可解释降级路径；数据不足时返回 `confidence="unavailable"` 或 `confidence="low"`，不得输出完整功率复盘口吻。

---

## 二、任务背景

P3 完成后，骑行已有两项专项事实指标：

```text
metrics.power_variability     -> VI = normalized_power / avg_power
metrics.pedaling_stability    -> cadence cv / decay_pct / score
```

P5 完成后，骑行指标卡已经突出：

```text
功率变异
踏频稳定性
```

但两个旧指标仍存在语义债：

```text
metrics.efficiency    当前主要来自跑步 avg_hr + avg_pace / 速度效率口径
metrics.durability    当前主要来自 speed_stream 后程保持口径
```

这对骑行不够恰当：

- 骑行外部速度高度受坡度、风、路况、跟骑、刹停影响，不应作为核心输出能力代理。
- 骑行功率是更直接的机械输出事实；有功率时应优先进入效率与耐力判断。
- 心率仍重要，但在骑行中更适合与功率组合，表达“输出相对心肺成本”。

P3b 的目标是让骑行活动下：

```text
efficiency -> power-based efficiency
durability -> power-based durability
```

同时不破坏跑步和 general 复盘。

---

## 三、适用范围

本任务正式覆盖：

```text
cycling
road_cycling
mountain_biking
```

暂缓但不得破坏：

```text
indoor_cycling
gravel_cycling
track_cycling
hand_cycling
e_biking
e_mountain_biking
running
trail_running
treadmill_running
hiking
swimming
```

要求：

- `cycling / road_cycling / mountain_biking` 使用 P3b 功率口径。
- 跑步和其他非骑行活动继续使用既有 `efficiency / durability` 逻辑。
- 电助力活动暂不进入普通骑行功率能力评价，避免电助力污染“输出效率/后程保持”语义。
- `indoor_cycling` 是否纳入 P3b 不在本任务验收范围；如自然进入，必须在完成报告说明原因和风险。

---

## 四、目标输出契约

### 1. `metrics.efficiency` 骑行功率口径

目标结构应兼容现有前端读取方式，保留通用字段：

```json
{
  "score": null,
  "level": "unknown",
  "confidence": "unavailable",
  "delta_pct": null,
  "sample_size": 0,
  "basis": "power_hr",
  "power_per_hr": null,
  "avg_power": null,
  "avg_hr": null,
  "power_data_quality": "missing",
  "reasons": []
}
```

字段语义：

- `basis`：骑行活动必须为 `"power_hr"`，用于标记本指标是功率心率口径。
- `power_per_hr`：`avg_power / avg_hr`，单位可理解为 W/bpm，只作为同一用户活动内参考。
- `score`：功率心肺效率粗评分，0-100。
- `level`：`good / moderate / low / unknown` 或项目已有等价枚举。
- `confidence`：`high / medium / low / unavailable`。
- `delta_pct`：相对个人历史 baseline 的变化百分比；如果没有可靠 baseline，返回 `null`，不要伪造。
- `sample_size`：baseline 样本量；如未接入 baseline，返回 0。
- `avg_power`：透传 `summary.avg_power`。
- `avg_hr`：使用活动平均心率。
- `power_data_quality`：透传 `summary.power_data_quality`。
- `reasons`：降级原因数组，不包含 raw points。

最低实现策略：

- 当 `summary.power_data_quality == "available"` 且 `avg_power > 0` 且 `avg_hr > 0` 时，计算 `power_per_hr = avg_power / avg_hr`。
- 如果可复用既有 baseline 查询且 baseline 语义清楚，可以计算 `delta_pct`；否则先不接 baseline，保持 `delta_pct=null / sample_size=0`。
- `score` 可以使用保守映射，不要宣称为标准运动科学模型。

建议评分：

```text
power_per_hr <= 0       -> unavailable
power_per_hr < 1.2      -> score 45, level="low"
1.2 <= value < 1.8      -> score 65, level="moderate"
1.8 <= value < 2.5      -> score 80, level="good"
value >= 2.5            -> score 90, level="good"
```

注意：

- 该评分只是单次活动内的保守可解释启发式，不是跨人群能力排名。
- 不得用体重计算 W/kg。
- 不得用 FTP 或功率区间归一化。
- 不得用速度/配速作为骑行 efficiency 的核心输入。

### 2. `metrics.durability` 骑行功率口径

目标结构应兼容现有前端读取方式，保留通用字段：

```json
{
  "score": null,
  "level": "unknown",
  "confidence": "unavailable",
  "head_speed": null,
  "tail_speed": null,
  "basis": "power_retention",
  "head_power": null,
  "tail_power": null,
  "power_retention_pct": null,
  "power_points_count": 0,
  "power_data_quality": "missing",
  "reasons": []
}
```

字段语义：

- `basis`：骑行活动必须为 `"power_retention"`，用于标记本指标是功率后程保持口径。
- `head_power`：前半程有效功率均值。
- `tail_power`：后半程有效功率均值。
- `power_retention_pct`：`tail_power / head_power * 100`。
- `score`：后程功率保持评分，0-100。
- `level`：`good / moderate / dropping / unknown` 或项目已有等价枚举。
- `confidence`：由功率曲线质量和样本数决定。
- `head_speed / tail_speed`：为兼容旧前端可保留为 `null`，不得在骑行功率口径下继续伪装成核心事实。
- `power_points_count`：透传 `summary.power_points_count` 或有效功率样本数。
- `power_data_quality`：透传 `summary.power_data_quality`。
- `reasons`：降级原因数组，不包含 raw points。

计算规则：

- 只有 `summary.power_data_quality == "available"` 且同轴 `curves.power` 为 list 且有效样本数足够时才计算。
- 有效功率范围建议：`power > 0` 且 `power <= 2500`。
- 有效样本少于 20 个时必须降级。
- 前后半程应基于同轴 power 曲线的有效样本顺序拆分；不要从速度、距离、DOM 或 ECharts 推断。
- `power_retention_pct = tail_power / head_power * 100`，建议保留 1 位小数。

建议评分：

```text
retention >= 95%        -> score 90, level="good"
90% <= retention < 95%  -> score 78, level="moderate"
80% <= retention < 90%  -> score 62, level="dropping"
retention < 80%         -> score 45, level="dropping"
```

可信度建议：

```text
power_data_quality != available -> confidence="unavailable"
valid_power_points < 20         -> confidence="low" 或 "unavailable"
20 <= points < 120              -> confidence="medium"
points >= 120                   -> confidence="high"
```

注意：

- 不要使用 `normalized_power` 替代后程功率曲线。
- 不要从 power curve 重算 NP。
- 不要用速度后程保持冒充功率 durability。
- 不要把短时间滑行、路口停顿、下坡低功率解释为能力下降；当前只能作为保守参考，完成报告需写明风险。

---

## 五、实现边界

允许修改：

- `main.py`
- `metrics_resolver.py`，仅当复用或抽出纯函数能降低重复逻辑时
- `tests/test_cycling_fatigue_review_metrics.py`
- `tests/test_cycling_fatigue_review_snapshot.py`
- `tests/test_fatigue_review_contract_realignment.py`
- `docs/js_api_contract.json`
- `docs/fatigue_review_realignment_plan_v1.md`
- 新增 `docs/p3b_cycling_power_efficiency_durability_completion_report.md`

谨慎修改，除非确有必要并在完成报告说明：

- `tests/test_fatigue_review_e2e_contract.py`
- `tests/test_fatigue_review_quality_gate.py`

禁止修改：

- `llm_backend.py`
- DB schema / migrations
- 前端 ECharts 主图实现
- 前端指标卡布局与渲染逻辑
- AI prompt / AI schema / 真实 LLM 调用链路
- 任何与本任务无关的 activity advice、startup、water、environment challenge 模块

---

## 六、实现建议

建议新增或扩展后端 helper：

```python
def _build_cycling_power_efficiency_metric(summary, row_or_bundle):
    ...

def _build_cycling_power_durability_metric(summary, power_curve):
    ...

def _build_cycling_review_metrics(sport_type, summary, curves_snapshot, ...):
    ...
```

也可以保持 `_build_cycling_review_metrics(...)` 只负责 P3 指标，另建 P3b 覆盖 helper；但需要保证调用点清晰。

接入位置建议：

- 在 `_build_fatigue_review_snapshot()` 已经生成 `summary` 和 `curves_snapshot` 后，对骑行 sport 覆盖 `metrics["efficiency"]` 与 `metrics["durability"]`。
- 不要在通用 `MetricsResolver._compute_efficiency_score()` 或 `_compute_durability_index()` 中直接改变所有 sport 行为，除非有明确 sport 分支并有跑步回归测试覆盖。

降级 helper 建议：

```python
def _cycling_power_efficiency_unavailable(summary, reason):
    ...

def _cycling_power_durability_unavailable(summary, reason):
    ...
```

输出必须结构稳定，即使 unavailable 也要保留字段。

---

## 七、测试要求

至少新增或更新以下测试：

### 1. 骑行效率功率化

覆盖：

- `cycling` 且 `avg_power / avg_hr / power_data_quality` 可用时，`metrics.efficiency.basis == "power_hr"`。
- 输出 `power_per_hr / avg_power / avg_hr / power_data_quality`。
- 不再依赖跑步配速字段。
- 缺少 power 或 HR 时，`confidence` 降级且 `reasons` 明确。

### 2. 骑行耐力功率化

覆盖：

- `cycling` 且 `curves.power` 可用时，`metrics.durability.basis == "power_retention"`。
- 输出 `head_power / tail_power / power_retention_pct / power_points_count`。
- 后半程功率低于前半程时，score/level 反映下降。
- 功率曲线样本不足或质量不可用时，`confidence` 降级且不使用速度曲线冒充。

### 3. 非骑行不回归

覆盖：

- `running` 或 general sport 不出现 `basis="power_hr"`。
- 跑步 `efficiency / durability` 仍保留原有语义和字段。
- `power_variability / pedaling_stability` 的 P3 行为不被破坏。

### 4. 契约文档

覆盖：

- `docs/js_api_contract.json` 可通过 JSON 校验。
- 契约描述补充 P3b：骑行 `efficiency / durability` 为功率口径，前端和 AI 不得计算或补齐。

建议运行：

```bash
python3 -m pytest tests/test_cycling_fatigue_review_metrics.py
python3 -m pytest tests/test_cycling_fatigue_review_snapshot.py tests/test_fatigue_review_contract_realignment.py
python3 -m json.tool docs/js_api_contract.json
```

如修改了 resolver 或通用指标逻辑，还需运行：

```bash
python3 -m pytest tests/test_fatigue_review_resolver_realignment.py tests/test_fatigue_review_p1_regression.py
```

---

## 八、验收标准

完成后必须满足：

- 骑行活动 `metrics.efficiency.basis == "power_hr"`。
- 骑行活动 `metrics.durability.basis == "power_retention"`。
- 有功率和心率时，`efficiency` 输出可解释的 `power_per_hr`。
- 有同轴功率曲线时，`durability` 输出可解释的 `head_power / tail_power / power_retention_pct`。
- 无功率、无心率或样本不足时明确降级，不输出完整功率结论。
- 跑步/general `efficiency / durability` 行为不变。
- P3 `power_variability / pedaling_stability` 行为不变。
- 不改前端、不改 AI、不改 DB。
- 契约文档和完成报告同步更新。

---

## 九、完成报告模板

任务完成后新增：

```text
docs/p3b_cycling_power_efficiency_durability_completion_report.md
```

报告至少包含：

```markdown
# P3b 骑行复盘功率效率与耐力专项化完成报告

## 1. 本次目标

## 2. 执行前重新思考

## 3. 现状调查

## 4. 实现内容

## 5. 降级策略

## 6. 契约保持与边界

## 7. 验证

## 8. 剩余风险

## 9. 下一步
```

报告必须明确说明：

- 是否接入 baseline；如果没有，为什么先保持 `delta_pct=null / sample_size=0`。
- `efficiency` 的 `power_per_hr` 只是保守启发式，不是跨人群能力评价。
- `durability` 的功率后程保持可能受路况、下坡、滑行、停顿影响，当前不做复杂场景识别。
- 未实现 FTP / IF / TSS / W/kg / 功率区间。
- 未改 AI、前端、DB。

---

## 十、明确不做

- 不做 P4/P5 前端再设计。
- 不改 ECharts 主图。
- 不改指标卡布局。
- 不改 AI prompt/schema。
- 不调用真实 LLM。
- 不写 DB。
- 不新增 DB 字段。
- 不计算 FTP。
- 不计算 IF。
- 不计算 TSS。
- 不计算 W/kg。
- 不计算功率区间。
- 不从功率曲线重算 NP。
- 不把速度后程保持包装成功率耐力。
- 不把跑步 `efficiency / durability` 一并重写。
