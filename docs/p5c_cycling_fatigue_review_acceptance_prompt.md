# P5c 骑行复盘端到端验收与降级场景固化提示词

> 任务类型：P5c-cycling 骑行复盘端到端验收 / 质量门禁补强
> 前置条件：P0/P1/P2/P3/P3b/P4/P5/P5b-cycling 均已完成
> 核心目标：用真实或等价场景化样本验收骑行复盘页面，确认主图、指标卡、功率效率、后程功率保持和降级文案都符合骑行契约
> 不包含：新增算法、重排 UI、改 AI prompt/schema、DB schema 迁移、真实 LLM 联调、FTP/IF/TSS/W/kg/功率区间模型

---

## 零、执行前重新思考

执行本任务前，先重新确认任务顺序是否合理：

- P3 已实现 `power_variability / pedaling_stability` 后端事实指标。
- P3b 已实现骑行 `efficiency.basis="power_hr"` 与 `durability.basis="power_retention"`。
- P4 已让骑行主图区 ECharts 与跑步不同，突出功率、心率、海拔、踏频。
- P5 已让骑行指标卡突出功率变异与踏频稳定性。
- P5b 已让骑行指标卡展示“功率效率 / 后程功率保持”。
- 因此下一步不应急着继续加功能，而应做端到端验收和场景固化，确认页面在真实数据、缺功率、样本不足时都诚实表达。

本任务的价值不是“再做一个新指标”，而是回答：

```text
骑行复盘现在是否真的不像跑步复盘？
有功率时是否突出功率事实？
无功率时是否没有装作有完整功率复盘？
功率样本不足时是否不会输出过度结论？
```

如果验收发现重大契约违背，允许做最小修复；如果只是视觉偏好或信息层级取舍，先记录为后续视觉重排任务，不在 P5c 中扩大范围。

---

## 一、架构契约核对

执行本任务前必须先阅读并遵守：

- `docs/p0_cycling_fatigue_review_contract_completion_report.md`
- `docs/p1_cycling_fatigue_review_snapshot_completion_report.md`
- `docs/p3_cycling_fatigue_review_metrics_completion_report.md`
- `docs/p3b_cycling_power_efficiency_durability_completion_report.md`
- `docs/p4_cycling_fatigue_review_chart_completion_report.md`
- `docs/p5_cycling_fatigue_review_metric_cards_completion_report.md`
- `docs/p5b_cycling_power_efficiency_durability_cards_completion_report.md`
- `docs/js_api_contract.json` 中 `get_fatigue_review`
- `docs/fatigue_review_realignment_plan_v1.md`
- 全局架构契约 `fit-arch-contrac`

硬性约束：

- `get_fatigue_review(activity_id)` 仍是复盘页面唯一权威数据源。
- 前端不得从 `summary / curves / DOM / ECharts / points` 推导指标。
- AI 不参与指标计算，不参与验收结论生成。
- 不调用真实 LLM。
- 不写 DB，不改 DB schema，不改 migrations。
- 不新增 FTP / IF / TSS / W/kg / 功率区间。
- 不从 power curve 重算 NP。
- 不用速度后程保持冒充功率耐力。
- `shadow_diff / shadow_diff_json / diff / records / points / raw_records / track_points` 不得进入复盘主展示或测试 fixture 预期。

---

## 二、任务背景

当前骑行复盘链路已经具备以下能力：

```text
summary.avg_power / normalized_power / avg_cadence / power_data_quality / cadence_data_quality
curves.power / curves.cadence
metrics.power_variability
metrics.pedaling_stability
metrics.efficiency.basis = power_hr
metrics.durability.basis = power_retention
骑行主图：power + hr + altitude + cadence
骑行指标卡：功率变异 / 心率漂移 / 踏频稳定性 / 能量断档风险 / 功率效率 / 训练负荷 / 后程功率保持 / 状态下滑点
```

但这些任务大多是单点实现和静态契约测试。P5c 需要从用户视角做一次场景验收：

- 有功率和踏频的骑行活动。
- 无功率但有心率/速度/海拔的骑行活动。
- 功率或踏频样本不足的骑行活动。
- 非骑行活动回归。

---

## 三、验收场景

### 场景 A：有功率 + 有踏频的骑行

输入特征：

```text
sport_type = cycling / road_cycling / mountain_biking
summary.power_data_quality = available
summary.cadence_data_quality = available
metrics.power_variability.vi != null
metrics.pedaling_stability.score != null
metrics.efficiency.basis = power_hr
metrics.efficiency.power_per_hr != null
metrics.durability.basis = power_retention
metrics.durability.power_retention_pct != null
curves.power 非空
curves.cadence 非空
```

必须验收：

- 主图默认骑行模式，不展示跑步配速/GAP/效率作为核心泳道。
- 主图包含功率、心率、海拔、踏频相关图层。
- 指标卡包含“功率变异 / 踏频稳定性 / 功率效率 / 后程功率保持”。
- `功率效率` 展示来自 `metrics.efficiency.power_per_hr` 的证据。
- `后程功率保持` 展示来自 `metrics.durability.power_retention_pct / head_power / tail_power` 的证据。
- 不出现“步频稳定性”作为骑行核心指标。
- 不出现“后程保持参考 / 不等同于 power-based durability”的旧文案。

### 场景 B：无功率骑行

输入特征：

```text
sport_type = cycling / road_cycling / mountain_biking
summary.power_data_quality = missing
curves.power = []
metrics.power_variability.confidence = unavailable
metrics.efficiency.confidence = unavailable 或 power_per_hr = null
metrics.durability.confidence = unavailable 或 power_retention_pct = null
```

必须验收：

- 页面可以展示骑行复盘，但必须明确功率数据不足。
- 功率变异卡不能展示 VI。
- 功率效率卡不能展示完整结论。
- 后程功率保持卡不能展示完整结论。
- AI/文案不得使用“功率保持良好”“输出很稳”等完整功率复盘口吻。
- 主图不应前端补算功率曲线。

### 场景 C：功率样本不足或长度不匹配

输入特征：

```text
summary.power_data_quality = insufficient_points / length_mismatch / invalid_values
metrics.durability.power_retention_pct = null
metrics.power_variability.vi = null 或 confidence 低可信/不可用
```

必须验收：

- 指标卡显示“功率数据不足 / 功率曲线样本不足 / 不适合判断”。
- 不用速度曲线替代功率耐力。
- 不把 `durability.score` 单独当成功率保持事实展示。
- 不从 ECharts 当前 series 或 DOM 文案推导。

### 场景 D：非骑行回归

输入特征：

```text
sport_type = running / trail_running / treadmill_running / hiking / walking
```

必须验收：

- 跑步/general 指标卡仍显示“运动效率 / 耐久指数 / 步频稳定性”。
- 跑步/general 不展示“功率效率 / 后程功率保持”。
- 跑步/general 不展示 `power_variability / pedaling_stability` 作为主卡。
- 跑步主图不被切换成骑行功率主图。

---

## 四、建议实现方式

优先顺序：

1. 如果本地已有可用真实骑行活动数据，选取 1 条有功率骑行和 1 条无功率或功率不足骑行做手工验收记录。
2. 如果真实数据不可稳定复现，则使用测试 fixture 或构造等价 `get_fatigue_review` payload 做静态/单元验收。
3. 如果发现生产代码只缺少测试覆盖，优先补测试，不改业务代码。
4. 如果发现生产代码确实违反 P5c 验收标准，做最小修复并在报告中说明。

建议新增或更新：

- `tests/test_cycling_fatigue_review_acceptance.py`
- `docs/cycling_fatigue_review_acceptance_checklist.md`
- `docs/p5c_cycling_fatigue_review_acceptance_completion_report.md`

如已有等价测试文件，也可以扩展现有：

- `tests/test_cycling_fatigue_review_metrics.py`
- `tests/test_cycling_fatigue_review_snapshot.py`
- `tests/test_fatigue_review_quality_gate.py`
- `tests/test_v9_0_detail_tab_review.py`

---

## 五、实现边界

允许修改：

- `tests/test_cycling_fatigue_review_acceptance.py`
- `tests/test_cycling_fatigue_review_metrics.py`
- `tests/test_cycling_fatigue_review_snapshot.py`
- `tests/test_fatigue_review_quality_gate.py`
- `tests/test_v9_0_detail_tab_review.py`
- `docs/cycling_fatigue_review_acceptance_checklist.md`
- `docs/fatigue_review_realignment_plan_v1.md`
- 新增 `docs/p5c_cycling_fatigue_review_acceptance_completion_report.md`

仅当验收失败且必须最小修复时允许修改：

- `track.html`
- `main.py`

禁止修改：

- `llm_backend.py`
- `metrics_resolver.py`，除非发现 P3b helper 明确 bug 且有测试证明
- DB schema / migrations
- AI prompt / AI schema / 真实 LLM 调用链路
- P4 ECharts 主图结构性重排
- 指标卡视觉重排或新增卡片数量

---

## 六、测试要求

### 1. 后端 payload 验收

至少覆盖：

- 有功率骑行 payload 含 `summary.power_data_quality="available"`。
- 有功率骑行 payload 含 `metrics.efficiency.basis="power_hr"`。
- 有功率骑行 payload 含 `metrics.durability.basis="power_retention"`。
- 无功率或样本不足时，相关 metrics `confidence` 降级且关键数值为 `null`。

### 2. 前端静态验收

至少覆盖：

- cycling profile 包含 `功率效率 / 后程功率保持`。
- cycling profile 不包含旧文案 `后程保持参考`。
- cycling profile 不包含 `当前不等同于 power-based durability`。
- running/general profile 不包含 `功率效率 / 后程功率保持`。
- `_renderFatigueReviewMetrics` 不含 `summary.`、`curves.`、`getOption`、`querySelector`、`innerText`。
- `_renderFatigueReviewMetrics` 不含 `avg_power / avg_hr`、`tail_power / head_power`、`normalized_power / avg_power`。

### 3. 手工验收清单

如果可以打开真实 UI，至少记录：

```text
活动 ID / 文件名
sport_type
是否有功率
是否有踏频
主图默认图层
8 张指标卡标题
功率效率卡主值与 sub 文案
后程功率保持卡主值与 sub 文案
无功率或样本不足时的降级文案
是否出现跑步语义误用
```

建议运行：

```bash
python3 -m pytest tests/test_cycling_fatigue_review_metrics.py tests/test_cycling_fatigue_review_snapshot.py
python3 -m pytest tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py
python3 -m pytest tests/test_fatigue_review_contract_realignment.py
```

---

## 七、验收标准

完成后必须满足：

- 有功率骑行能展示完整骑行功率复盘口径。
- 无功率骑行能诚实降级，不展示完整功率结论。
- 功率样本不足能诚实降级，不用速度替代功率。
- 骑行复盘主图与跑步不同。
- 骑行指标卡与跑步不同。
- 跑步/general 不回归。
- 前端零推断边界有测试覆盖。
- 完成报告记录真实或等价验收结果。

---

## 八、完成报告模板

任务完成后新增：

```text
docs/p5c_cycling_fatigue_review_acceptance_completion_report.md
```

报告至少包含：

```markdown
# P5c 骑行复盘端到端验收与降级场景固化完成报告

## 1. 本次目标

## 2. 执行前重新思考

## 3. 验收场景

## 4. 实现或测试内容

## 5. 验收结果

## 6. 前端零推断边界

## 7. 发现的问题与处理

## 8. 剩余风险

## 9. 下一步
```

报告必须说明：

- 是否使用真实活动样本；如果没有，使用了哪些等价 fixture。
- 有功率、无功率、样本不足、非骑行四类场景是否覆盖。
- 是否改业务代码；如果改了，为什么必须改。
- 是否仍保持不改 AI、不改 DB、不调用 LLM。
- 是否仍未实现 FTP / IF / TSS / W/kg / 功率区间。

---

## 九、明确不做

- 不新增骑行算法。
- 不重排骑行指标卡视觉层级。
- 不新增第 9、第 10 张指标卡。
- 不改 AI prompt/schema。
- 不调用真实 LLM。
- 不写 DB。
- 不改 DB schema。
- 不计算 FTP / IF / TSS / W/kg。
- 不计算功率区间。
- 不从 power curve 重算 NP。
- 不从 summary/curves/DOM/ECharts/points 推导指标。
