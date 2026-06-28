# P5b 骑行复盘功率效率与功率保持指标卡对齐提示词

> 任务类型：P5b-cycling 前端复盘指标卡 P3b 语义对齐
> 前置条件：P3b-cycling 已完成后端 `metrics.efficiency.basis="power_hr"` 与 `metrics.durability.basis="power_retention"`，P5-cycling 已完成骑行指标卡 profile
> 核心目标：让骑行复盘指标卡用户可见文案和证据展示对齐 P3b 的功率口径，展示“功率效率 / 后程功率保持”，不再把 `durability` 描述为旧的速度保持辅助参考
> 不包含：后端算法、ECharts 主图、AI prompt/schema、DB schema、真实 LLM 联调、FTP/IF/TSS/W/kg/功率区间模型

---

## 零、执行前重新思考

执行本任务前，先重新确认任务顺序和边界是否合理：

- P5 已经让骑行指标卡与跑步不同，突出 `power_variability / pedaling_stability`。
- P5 当时刻意把 `durability` 写成“后程保持参考”，因为 P3b 尚未完成，不能暗示它已经是功率耐力。
- P3b 现在已经把后端骑行 `efficiency / durability` 改成 `power_hr / power_retention` 功率口径。
- 因此下一步不是继续改后端，也不是改主图，而是把前端骑行指标卡的展示语义对齐 P3b。
- 这一步必须只读后端 `metrics`，不能在前端从 `summary / curves.power / curves.cadence / ECharts / DOM` 计算任何功率指标。

如果执行前发现后端没有返回：

```text
metrics.efficiency.basis === "power_hr"
metrics.durability.basis === "power_retention"
```

则前端只能展示“数据不足 / 后端未返回功率口径”，不能自行计算 `power_per_hr` 或 `power_retention_pct`。

---

## 一、架构契约核对

执行本任务前必须先阅读并遵守：

- `docs/p3b_cycling_power_efficiency_durability_prompt.md`
- `docs/p3b_cycling_power_efficiency_durability_completion_report.md`
- `docs/p5_cycling_fatigue_review_metric_cards_prompt.md`
- `docs/p5_cycling_fatigue_review_metric_cards_completion_report.md`
- `docs/p4_cycling_fatigue_review_chart_completion_report.md`
- `docs/js_api_contract.json` 中 `get_fatigue_review`
- `docs/fatigue_review_realignment_plan_v1.md`
- `docs/脉图运动复盘系统_开发团队交付手册_v1.md`
- 全局架构契约 `fit-arch-contrac`

硬性约束：

- 复盘 Tab 唯一数据源仍是 `get_fatigue_review(activity_id)`。
- 前端指标卡只能读取 `data.metrics` 和 `data.sport_type`。
- 前端不得从 `summary.avg_power / summary.avg_hr` 计算 `power_per_hr`。
- 前端不得从 `curves.power` 计算 `head_power / tail_power / power_retention_pct`。
- 前端不得从 `curves.power`、`curves.cadence`、速度曲线、DOM、ECharts series、`_lastFatigueReviewChartPayload`、points 推导任何骑行指标。
- 前端不得计算 VI、CV、decay、score、FTP、IF、TSS、W/kg、功率区间。
- 不改 `main.py`、不改 `metrics_resolver.py`、不改 `llm_backend.py`。
- 不改 DB schema / migrations。
- 不改 AI prompt / AI 输出 schema / 真实 LLM 调用。
- 不改 P4 ECharts 主图 laneDefs。
- 不写 DB，不写 localStorage/sessionStorage。
- `shadow_diff / shadow_diff_json / diff / records / points / raw_records / track_points` 不得进入复盘主展示。

---

## 二、任务背景

当前骑行 profile 的 8 张卡大致为：

```text
关键证据：
功率变异              metrics.power_variability
心率漂移              metrics.hr_drift
踏频稳定性            metrics.pedaling_stability
能量断档风险          metrics.bonk_risk

补充证据：
状态下滑点            metrics.events
训练负荷              metrics.training_load
后程效率变化          metrics.decoupling
后程保持参考          metrics.durability
```

P3b 完成后，两个事实已经变化：

```text
metrics.efficiency.basis = "power_hr"
metrics.efficiency.power_per_hr = avg_power / avg_hr

metrics.durability.basis = "power_retention"
metrics.durability.power_retention_pct = tail_power / head_power * 100
```

因此旧展示存在两个问题：

- `metrics.efficiency` 在骑行 profile 中没有用户可见入口，被 `events` 占用了原本的 efficiency slot。
- `metrics.durability` 虽然被展示，但仍叫“后程保持参考”，tooltip 还写着“不等同于 power-based durability”，这已经与 P3b 后端事实不一致。

P5b 的目标是：

```text
骑行卡片直接展示 P3b 的功率效率和后程功率保持。
```

---

## 三、目标行为

### 1. 骑行活动指标卡

当 `data.sport_type` 属于：

```text
cycling
road_cycling
mountain_biking
```

指标卡进入 cycling profile。

推荐 8 卡展示顺序：

```text
关键证据：
功率变异 / VI              metrics.power_variability
心率漂移                   metrics.hr_drift
踏频稳定性                 metrics.pedaling_stability
能量断档风险               metrics.bonk_risk

补充证据：
功率效率                   metrics.efficiency
训练负荷                   metrics.training_load
后程功率保持               metrics.durability
状态下滑点                 metrics.events
```

要求：

- `功率效率` 必须读取 `metrics.efficiency.basis / power_per_hr / score / level / confidence / avg_power / avg_hr / power_data_quality / reasons`。
- `后程功率保持` 必须读取 `metrics.durability.basis / head_power / tail_power / power_retention_pct / score / level / confidence / power_points_count / power_data_quality / reasons`。
- `功率效率` 只有在 `basis === "power_hr"` 且 `power_per_hr != null` 且 `confidence !== "unavailable"` 时展示有效结论。
- `后程功率保持` 只有在 `basis === "power_retention"` 且 `power_retention_pct != null` 且 `confidence !== "unavailable"` 时展示有效结论。
- 如果后端缺少 basis 或 basis 不匹配，必须按数据不足处理，不能用 score 强行展示功率口径。
- `decoupling` 可以不再出现在 cycling 8 卡中；如果保留，必须明确它不是 P3b 的 power retention。
- `events` 可以移到最后一张或其他补充位置，但不能消失到页面外不可见，除非有明确替代入口。

### 2. 跑步和其他非骑行活动保持现状

非骑行活动必须保持 P5 前的既有语义：

- `efficiency -> 运动效率`
- `durability -> 耐久指数`
- `cadence_stability -> 步频稳定性`
- 不展示 `power_variability / pedaling_stability`。
- 不展示 `功率效率 / 后程功率保持`。
- 不要求 `basis` 字段存在。

### 3. 空态与降级

骑行功率效率不可用：

- 展示“功率效率不足 / 数据不足 / 不适合判断”之一。
- sub 文案说明缺少功率、心率或后端未返回 `power_hr`。
- 不得用 `summary.avg_power / avg_hr` 补算。

骑行后程功率保持不可用：

- 展示“功率保持不足 / 数据不足 / 不适合判断”之一。
- sub 文案说明缺少功率曲线、样本不足或后端未返回 `power_retention`。
- 不得用速度曲线、配速、主图、ECharts 或 DOM 补算。

---

## 四、前端展示契约

### 1. card defs 调整

建议调整 `_fatigueReviewMetricCardDefs(sportType)` 的 cycling profile：

```js
withSlot('efficiency', 'efficiency', '功率效率', ... 'power_per_hr', 'W/bpm')
withSlot('cadence_stability', 'durability', '后程功率保持', ... 'power_retention_pct', '%')
withSlot('training_load', 'events', '状态下滑点', ... 'count', '')
```

也可以选择其他 slot 顺序，但必须满足：

- `metrics.efficiency` 在 cycling profile 中有用户可见卡片。
- `metrics.durability` 在 cycling profile 中命名为功率保持或后程功率保持。
- 不再把 `durability` tooltip 写成“不等同于 power-based durability”。
- 不新增第 9、第 10 张卡，除非同步更新布局和测试；优先保持 8 卡布局稳定。

### 2. 证据展示 helper

建议新增：

```js
function _fatigueReviewPowerEfficiencyEvidence(metric, missing) {
  ...
}

function _fatigueReviewPowerRetentionEvidence(metric, missing) {
  ...
}
```

`_fatigueReviewPowerEfficiencyEvidence` 只允许读取：

```text
metric.power_per_hr
metric.avg_power
metric.avg_hr
metric.basis
metric.power_data_quality
metric.reasons
```

建议展示：

```text
1.60 W/bpm / Avg 240W / HR 150
```

`_fatigueReviewPowerRetentionEvidence` 只允许读取：

```text
metric.power_retention_pct
metric.head_power
metric.tail_power
metric.basis
metric.power_points_count
metric.power_data_quality
metric.reasons
```

建议展示：

```text
保持 91.2% / 前半 220W / 后半 201W
```

禁止：

```text
metric.tail_power / metric.head_power
summary.avg_power / avg_hr
curves.power
normalized_power / avg_power
```

### 3. headline 与 copy 调整

建议扩展 `_fatigueReviewMetricHeadline(kind, ...)`：

```js
kind === 'power_efficiency'
kind === 'power_retention'
```

或在 cycling 分支直接传 `efficiency / durability`，但文案必须区分骑行：

```text
功率效率稳定
单位心率输出偏弱
后程功率保持良好
后程功率明显回落
```

建议更新 `FATIGUE_REVIEW_METRIC_COPY.efficiency.cycling`：

- normal：`单位心率输出较顺，功率和心肺成本匹配较好。`
- risk：`同样心率成本下输出偏弱，可能受疲劳、地形或补给影响。`
- missing：`功率或心率数据不足，暂时无法判断功率效率。`

建议更新 `FATIGUE_REVIEW_METRIC_COPY.durability.cycling`：

- normal：`后半程功率保持较好，持续输出没有明显掉下去。`
- risk：`后半程功率保持下降，持续输出能力开始回落。`
- missing：`功率曲线或样本不足，暂时无法判断后程功率保持。`

### 4. missing reason 调整

`_fatigueReviewMetricMissingReason(metricKey, metric)` 应能区分：

```text
efficiency + cycling power_hr
durability + cycling power_retention
```

建议规则：

- `metricKey === 'efficiency'` 且 reason 包含 `missing avg_hr`：返回 `心率数据不足`。
- `metricKey === 'efficiency'` 且 reason 包含 `power data unavailable` / `avg_power`：返回 `功率数据不足`。
- `metricKey === 'durability'` 且 reason 包含 `power data unavailable` / `insufficient_points`：返回 `功率曲线样本不足`。
- `basis` 不匹配：返回 `后端未返回功率口径指标`。

---

## 五、实现边界

允许修改：

- `track.html`
- `tests/test_fatigue_review_quality_gate.py`
- `tests/test_v9_0_detail_tab_review.py`
- `docs/fatigue_review_realignment_plan_v1.md`
- 新增 `docs/p5b_cycling_power_efficiency_durability_cards_completion_report.md`

谨慎修改，只有测试确实需要时：

- `docs/detail_tab_review_manual_test_checklist.md`

禁止修改：

- `main.py`
- `metrics_resolver.py`
- `llm_backend.py`
- DB schema / migrations
- `docs/js_api_contract.json`，除非发现 P3b 契约漏字段且必须补充
- P4 ECharts 主图逻辑
- AI prompt / AI schema / 真实 LLM 调用链路

---

## 六、建议实施步骤

1. 阅读 P3b 完成报告和当前 `track.html` cycling profile。
2. 找到 `_fatigueReviewMetricCardDefs(sportType)`。
3. 调整 cycling profile 的 8 卡映射，让 `efficiency` 和 `durability` 以功率口径用户可见。
4. 新增或扩展 evidence helper，只读后端 `metrics.efficiency / metrics.durability`。
5. 更新 `_renderFatigueReviewMetrics(metrics, sportType)` 的 cycling 分支。
6. 更新 `FATIGUE_REVIEW_METRIC_COPY` 和 headline/missing reason 文案。
7. 更新静态质量门禁测试，确保前端没有从 summary/curves/DOM/ECharts 推导 P3b 指标。
8. 新增完成报告。

---

## 七、测试要求

至少更新或新增以下测试：

### 1. cycling profile 展示 P3b 指标

覆盖：

- cycling block 包含 `withSlot(..., 'efficiency', '功率效率', ...)`。
- cycling block 包含 `withSlot(..., 'durability', '后程功率保持', ...)`。
- cycling block 不再含有 `后程保持参考`。
- cycling block 不再说 `当前不等同于 power-based durability`。

### 2. 渲染只读后端 P3b metrics

覆盖：

- render body 中读取 `metrics.efficiency || {}`。
- render body 中读取 `eff.power_per_hr`。
- render body 中检查或使用 `eff.basis`。
- render body 中读取 `metrics.durability || {}`。
- render body 中读取 `durCycling.power_retention_pct`。
- render body 中检查或使用 `durCycling.basis`。

### 3. 禁止前端推导

render body 或新增 helper 中不得出现：

```text
summary.
curves.
chartPayload
getOption
querySelector
innerText
tail_power / head_power
avg_power / avg_hr
normalized_power / avg_power
power_per_hr =
power_retention_pct =
```

说明：

- 字符串匹配时要避免误伤普通文案；可聚焦 `_renderFatigueReviewMetrics` 和新增 evidence helper。
- 如果 helper 中只是读取 `metric.power_per_hr`，不应算作违规。

### 4. 非骑行不回归

覆盖：

- running/general profile 仍包含 `运动效率 / 耐久指数 / 步频稳定性`。
- running/general profile 不包含 `功率效率 / 后程功率保持`。
- running/general profile 不展示 `power_variability / pedaling_stability`。

建议运行：

```bash
python3 -m pytest tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py
```

如修改了文档或契约，也运行：

```bash
python3 -m pytest tests/test_fatigue_review_contract_realignment.py
```

---

## 八、验收标准

完成后必须满足：

- 骑行复盘指标卡用户可见“功率效率”。
- 骑行复盘指标卡用户可见“后程功率保持”。
- 两张卡只读取 `metrics.efficiency` 与 `metrics.durability` 的 P3b 字段。
- basis 不匹配或数据不足时诚实降级。
- 跑步/general 指标卡不变。
- 不改后端、不改 AI、不改 DB、不改 ECharts 主图。
- 测试覆盖前端零推断边界。
- 完成报告记录剩余风险。

---

## 九、完成报告模板

任务完成后新增：

```text
docs/p5b_cycling_power_efficiency_durability_cards_completion_report.md
```

报告至少包含：

```markdown
# P5b 骑行复盘功率效率与功率保持指标卡对齐完成报告

## 1. 本次目标

## 2. 执行前重新思考

## 3. 现状调查

## 4. 实现内容

## 5. 前端零推断边界

## 6. 验证

## 7. 剩余风险

## 8. 下一步
```

报告必须说明：

- 是否保留 8 卡布局。
- `功率效率` 只读 `metrics.efficiency.power_per_hr`。
- `后程功率保持` 只读 `metrics.durability.power_retention_pct/head_power/tail_power`。
- 未从 summary/curves/ECharts/DOM 推导。
- 未改后端、AI、DB。
- 未实现 FTP / IF / TSS / W/kg / 功率区间。

---

## 十、明确不做

- 不改后端 P3b 算法。
- 不改 `main.py`。
- 不改 `metrics_resolver.py`。
- 不改 `llm_backend.py`。
- 不改 DB。
- 不改 AI prompt/schema。
- 不改 ECharts 主图。
- 不新增指标卡数量。
- 不从 summary 计算 `power_per_hr`。
- 不从 curves 计算 `power_retention_pct`。
- 不从 DOM/ECharts/points 推导任何指标。
- 不计算 FTP / IF / TSS / W/kg / 功率区间。
