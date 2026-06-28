# P5 骑行复盘指标卡专项化提示词

> 任务类型：P5-cycling 前端复盘指标卡骑行模式
> 前置条件：P0-cycling 契约、P1-cycling 快照入源、P2-cycling AI prompt、P3-cycling 专项指标、P4-cycling 主图模式均已完成
> 核心目标：让骑行活动的复盘指标卡与跑步不同，突出 `power_variability / pedaling_stability`，并弱化跑步语义较强的效率/耐久卡；所有事实只来自 `get_fatigue_review(activity_id)`
> 不包含：后端指标算法、AI prompt/schema、DB schema、真实 LLM 联调、骑行评分重算、主图区 ECharts 再改造

---

## 零、执行前重新思考

执行本任务前，先重新确认任务顺序是否合理：

- P1 已保证骑行 `summary / curves.power / curves.cadence` 进入 `get_fatigue_review(activity_id)`。
- P3 已把 `metrics.power_variability / metrics.pedaling_stability` 从占位升级为后端事实指标。
- P4 已让骑行主图默认显示功率、心率、海拔，并支持踏频图层。
- 现在做 P5 是合理的：主图已经骑行化，指标卡也应同步从跑步语义切到骑行语义。
- 本任务只改变“指标卡怎么展示、怎么命名、怎么降级”，不改变“指标怎么算”。

如果发现后端没有返回 `metrics.power_variability / metrics.pedaling_stability`，只能展示数据不足或后端未返回，不能前端补算 VI、CV、decay 或 score。

---

## 一、架构契约核对

执行本任务前必须先阅读并遵守：

- `docs/p0_cycling_fatigue_review_contract_prompt.md`
- `docs/p1_cycling_fatigue_review_snapshot_completion_report.md`
- `docs/p2_cycling_fatigue_review_ai_prompt_completion_report.md`
- `docs/p3_cycling_fatigue_review_metrics_completion_report.md`
- `docs/p4_cycling_fatigue_review_chart_completion_report.md`
- `docs/js_api_contract.json` 中 `get_fatigue_review`
- `docs/fatigue_review_realignment_plan_v1.md`
- `docs/脉图运动复盘系统_开发团队交付手册_v1.md`
- 全局架构契约 `fit-arch-contrac`

硬性约束：

- 复盘 Tab 唯一数据源仍是 `get_fatigue_review(activity_id)`。
- 指标卡只能展示后端返回的 `data.metrics`，必要时只读取 `data.sport_type` 选择展示文案/卡片配置。
- 前端不得计算、补齐、拉伸、推断 `power_variability / pedaling_stability`。
- 前端不得从 `summary`、`curves.power`、`curves.cadence`、速度曲线、配速曲线、DOM、ECharts series、points 推导 VI、CV、decay、score 或结论。
- 不改 `main.py`、不改 `llm_backend.py`、不改 `metrics_resolver.py`、不改 DB、不改 AI prompt、不改 AI 输出 schema。
- `shadow_diff / shadow_diff_json / diff / records / points / raw_records / track_points` 仍不得进入复盘主展示。
- 指标卡展示不写 DB、不写 localStorage/sessionStorage、不调用 AI、不改变 `_lastFatigueReviewChartPayload`。

---

## 二、任务背景

当前复盘指标卡为 8 张静态卡，偏跑步语义：

```text
关键证据：
心率漂移
后程效率变化
能量断档风险
状态下滑点

补充证据：
运动效率
耐久指数
步频稳定性
训练负荷
```

骑行活动中，这套展示存在问题：

- `metrics.power_variability` 已经是骑行核心事实，但没有用户可见的一等入口。
- `metrics.pedaling_stability` 已经是骑行专项踏频指标，但当前卡片仍叫“步频稳定性”，容易混淆跑步步频。
- `运动效率 / 耐久指数` 当前仍带跑步或速度保持语义，P3 尚未实现 power-based efficiency / durability，不应在骑行中作为核心判断。
- P4 主图已经突出功率/心率/海拔，指标卡如果仍以跑步卡片为主，会造成视觉重点和事实指标不一致。

P5 的目标是让骑行指标卡进入专项模式：

```text
核心：功率变异 VI + 踏频稳定性 + 心率/能量/事件
辅助：训练负荷、后程效率变化、耐久指数等
弱化：跑步语义的运动效率、步频稳定性
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

指标卡应进入 cycling profile。

推荐 8 卡展示顺序：

```text
关键证据：
功率变异 / VI              metrics.power_variability
心率漂移                   metrics.hr_drift
踏频稳定性                 metrics.pedaling_stability
能量断档风险               metrics.bonk_risk

补充证据：
状态下滑点                 metrics.events
训练负荷                   metrics.training_load
后程效率变化               metrics.decoupling
耐久指数                   metrics.durability
```

要求：

- `功率变异 / VI` 必须来自 `metrics.power_variability.vi / level / confidence / reasons`。
- `踏频稳定性` 必须来自 `metrics.pedaling_stability.score / level / confidence / cv / decay_pct / reasons`。
- 骑行模式不得把 `metrics.cadence_stability` 展示为“踏频稳定性”的事实来源。
- 骑行模式可以保留 `hr_drift / decoupling / bonk_risk / events / training_load / durability`，但文案必须明确其辅助属性。
- 如果继续展示 `durability`，必须避免暗示它已经是 power-based durability；可以用“辅助参考”或“后程保持参考”口吻。
- 如果继续展示 `decoupling`，不得把它描述为功率解耦，除非后端契约已经提供对应字段。

### 2. 跑步和其他非骑行活动保持现状

当 `sport_type` 为：

```text
running
trail_running
treadmill_running
```

或其他非骑行类型：

- 继续保留当前跑步/general 指标卡语义。
- `cadence_stability` 仍显示为“步频稳定性”。
- 不把 `power_variability / pedaling_stability` 展示到跑步卡片中。
- 不改变跑步复盘指标卡默认文案和降级语义。

### 3. 空态与降级

骑行无功率或功率样本不足：

- `metrics.power_variability.confidence === "unavailable"` 或 `vi == null` 时，功率变异卡展示数据不足。
- 文案必须说明后端未返回可用功率、NP/AvgPower 缺失或样本不足，不能前端计算 VI。
- 不得展示完整功率复盘口吻。

骑行无踏频或踏频样本不足：

- `metrics.pedaling_stability.confidence === "unavailable"` 或 `score == null` 时，踏频稳定性卡展示数据不足。
- 文案必须说明后端未返回可用踏频或样本不足。
- 不得从速度、配速、踏频摘要或 DOM 推断踏频稳定性。

非骑行：

- `power_variability / pedaling_stability` 可以存在于 metrics 结构中，但前端默认不展示。
- 不因后端返回 unavailable 占位而污染跑步卡片。

---

## 四、前端展示契约

### 1. 建议新增 sport mode helper

可以复用 P4 的 `_fatigueReviewChartSportMode(sportType)`，也可以新增指标卡专用 helper：

```js
function _fatigueReviewMetricSportMode(sportType) {
  ...
}
```

返回：

```text
cycling
running
general
```

### 2. 建议新增 card defs builder

建议将指标卡映射抽成 helper：

```js
function _fatigueReviewMetricCardDefs(sportType) {
  ...
}
```

cycling profile 的 card defs 必须包含：

```js
{
  metricKey: 'power_variability',
  label: '功率变异',
  valueSource: 'vi',
  unit: 'VI'
}
{
  metricKey: 'pedaling_stability',
  label: '踏频稳定性',
  valueSource: 'score'
}
```

running/general profile 必须保留：

```js
cadence_stability -> 步频稳定性
efficiency -> 运动效率
durability -> 耐久指数
```

要求：

- 不要求一定新增 DOM 卡片数量；可以保持 8 张卡片并动态替换 label、tooltip、data-fr-metric、value/status/sub。
- 如果为了兼容现有测试保留原 DOM id，也必须保证用户可见 label 和 `data-fr-metric` 在 cycling profile 下反映真实指标。
- 不建议增加第 9、第 10 张卡，除非同步更新布局和静态测试；优先保持 8 卡布局稳定。

### 3. 数值展示建议

`power_variability`：

- 主值：`VI 1.05` 或 `1.05 VI`。
- status：由 `level / confidence` 映射为 `ok / warn / bad / empty`。
- sub：可以展示 `NP xxxW / Avg xxxW`，但只能读取 `metrics.power_variability.normalized_power / avg_power`。
- 不得从 `summary.normalized_power / summary.avg_power` 自行计算 VI。

`pedaling_stability`：

- 主值：`score`，例如 `82`。
- status：由 `level / confidence` 映射。
- sub：可以展示 `CV x.x% / 后程变化 y.y%`，但只能读取 `metrics.pedaling_stability.cv / decay_pct`。
- 不得从 `curves.cadence` 计算 CV、decay 或 score。

---

## 五、建议实施步骤

### Step 1：现状调查

先确认并记录：

- 指标卡 HTML 当前 8 个卡片 DOM。
- `_renderFatigueReviewMetrics(metrics, sportType)` 当前如何写入 value/status/sub。
- `FATIGUE_REVIEW_METRIC_COPY` 当前有哪些 cycling 文案。
- `_fatigueReviewMetricMissingReason(...)` 当前如何处理 cadence/power 数据不足。
- 现有测试对指标卡数量、id、label、tooltip 的断言。

### Step 2：定义指标卡 sport profile

新增或复用 sport mode helper。

新增 card defs：

- cycling：包含 `power_variability / pedaling_stability`。
- running/general：保持现状。

要求：

- 以 `sportType` 选择 profile。
- 不从 DOM 当前内容反推运动类型。
- 不从 ECharts 当前 series 或 chartPayload 读取数据。

### Step 3：扩展渲染逻辑

更新 `_renderFatigueReviewMetrics(metrics, sportType)`：

- 对 cycling profile 渲染功率变异卡。
- 对 cycling profile 渲染踏频稳定性卡。
- 保持 running/general 分支原有渲染。
- 更新 label、tooltip、data-fr-metric 时必须同步清理旧态，避免从骑行切换到跑步后残留“功率变异”。

建议新增小 helper：

```js
function _renderFatigueReviewMetricCard(cardDef, metric, sportGroup) {
  ...
}
```

但不要为了抽象而大范围重写无关逻辑。

### Step 4：扩展文案与降级

新增或调整：

- `FATIGUE_REVIEW_METRIC_COPY.power_variability`
- `FATIGUE_REVIEW_METRIC_COPY.pedaling_stability`
- `_fatigueReviewMetricHeadline(...)` 对两项骑行指标的映射。
- `_fatigueReviewMetricMissingReason(...)` 对 `power_data_quality / cadence_data_quality / missing_power / missing_cadence / insufficient_points` 的文案。

要求：

- 中文文案必须避免“步频”描述骑行踏频。
- 功率不足时明确“功率数据不足”，不要说“配速数据不足”。
- 踏频不足时明确“踏频数据不足”，不要说“步频数据不足”。

### Step 5：补测试

至少覆盖：

- `track.html` 中存在 cycling metric profile helper 或等价分支。
- cycling profile 包含 `power_variability` 和 `pedaling_stability`。
- cycling 用户可见 label 包含“功率变异”或“功率稳定性”，以及“踏频稳定性”。
- cycling 渲染不使用 `metrics.cadence_stability` 作为踏频稳定性来源。
- running/general 仍保留 `cadence_stability -> 步频稳定性`。
- `_renderFatigueReviewMetrics(...)` 不读取 `curves / points / chartPayload / ECharts / DOM 当前文字` 来生成事实指标。
- 前端不存在 `normalized_power / avg_power` 或 `np / avg_power` 形式的 VI 计算。
- 前端不存在从 `curves.cadence` 计算 `cv / decay_pct / score` 的逻辑。
- `main.py / llm_backend.py / metrics_resolver.py` 未被本任务修改。

建议运行：

```bash
python3 -m pytest tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py
python3 -m pytest tests/test_cycling_fatigue_review_snapshot.py tests/test_cycling_fatigue_review_metrics.py tests/test_fatigue_review_contract_realignment.py
```

### Step 6：写完成报告

新增：

```text
docs/p5_cycling_fatigue_review_metric_cards_completion_report.md
```

报告必须包含：

- 本次目标。
- 现状调查。
- 前端实现内容。
- cycling profile 卡片顺序。
- running/general 保持不变的说明。
- 数据边界与禁止事项。
- 测试命令与结果。
- 剩余风险。
- 下一步。

---

## 六、允许修改的文件

优先修改：

- `track.html`
- `tests/test_fatigue_review_quality_gate.py`
- `tests/test_v9_0_detail_tab_review.py`

建议新增：

- `docs/p5_cycling_fatigue_review_metric_cards_completion_report.md`

必要时修改：

- `docs/fatigue_review_realignment_plan_v1.md`

禁止或暂缓修改：

- `main.py`
- `llm_backend.py`
- `metrics_resolver.py`
- `fit_engine.py`
- DB schema / migration
- AI 输出 schema
- P4 主图区 ECharts laneDefs，除非发现 P5 必须修复的明确回归

---

## 七、验收标准

完成后必须满足：

- 骑行活动复盘指标卡和跑步不同。
- 骑行指标卡突出 `power_variability` 与 `pedaling_stability`。
- 骑行踏频卡不复用跑步 `cadence_stability` 语义。
- 跑步指标卡不回归。
- 指标卡仍只使用后端 `get_fatigue_review.data.metrics`。
- 前端不计算、不补齐、不推断 VI、CV、decay、score。
- AI prompt/schema 不变。
- 后端算法不变。
- DB schema 不变。

---

## 八、完成报告模板

```text
# P5 骑行复盘指标卡专项化完成报告

## 1. 本次目标

- ...

## 2. 现状调查

- 指标卡 DOM：
- 渲染函数：
- 现有文案：
- 现有测试：

## 3. 实现内容

- sport profile：
- cycling card defs：
- running/general card defs：
- 降级文案：
- 测试：

## 4. 契约保持不变

- 数据源：
- 前端零推断：
- AI 边界：
- 后端边界：

## 5. 明确不做

- 未改后端算法。
- 未改 AI prompt/schema。
- 未改 DB。
- 未从 summary/curves 计算 VI 或踏频稳定性。

## 6. 验证

- 运行命令：
- 结果：

## 7. 剩余风险

- ...

## 8. 下一步

- P6/P3b：power-based efficiency / durability。
- P4b：骑行图层开关按运动类型动态显隐。
```

---

## 九、给执行 Agent 的最后提醒

P5-cycling 是指标卡展示层任务，不是算法任务。

请保持边界：

- 可以改 `track.html` 指标卡映射、标签、tooltip、降级文案。
- 可以补前端静态契约测试。
- 可以写完成报告。
- 不改后端计算。
- 不改 AI。
- 不从 `summary / curves / speed / cadence / power / DOM / ECharts` 推导 `power_variability / pedaling_stability`。
