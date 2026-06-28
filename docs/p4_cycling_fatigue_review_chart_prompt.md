# P4 骑行复盘主图模式提示词

> 任务类型：P4-cycling 前端复盘主图骑行模式
> 前置条件：P0-cycling 契约、P1-cycling 快照入源、P2-cycling AI prompt、P3-cycling 专项指标均已完成
> 核心目标：让骑行活动的复盘主图区 ECharts 与跑步不同，默认突出 `power + hr + altitude`，并支持踏频图层；所有事实只来自 `get_fatigue_review(activity_id)`
> 不包含：后端指标算法、AI prompt/schema、DB schema、真实 LLM 联调、骑行评分重算

---

## 零、执行前重新思考

执行本任务前，先重新确认任务顺序是否合理：

- P1 已保证 `data.curves.power / data.curves.cadence` 与 `curves.distance` 同轴。
- P3 已把 `metrics.power_variability / pedaling_stability` 变成后端事实指标。
- 现在可以做前端主图专项化，因为前端已有可信 power/cadence 数据源。
- 本任务只改变“怎么展示”，不改变“事实怎么计算”。
- 骑行主图必须和跑步不同：跑步主图仍以配速/GAP/心率为核心；骑行主图应以功率/心率/海拔为核心，踏频作为可选或次级图层。

如果发现后端没有返回 `curves.power / curves.cadence`，只能展示空态或缺失图层，不能前端补算。

---

## 一、架构契约核对

执行本任务前必须先阅读并遵守：

- `docs/p0_cycling_fatigue_review_contract_prompt.md`
- `docs/p1_cycling_fatigue_review_snapshot_completion_report.md`
- `docs/p2_cycling_fatigue_review_ai_prompt_completion_report.md`
- `docs/p3_cycling_fatigue_review_metrics_completion_report.md`
- `docs/js_api_contract.json` 中 `get_fatigue_review`
- `docs/fatigue_review_realignment_plan_v1.md`
- `docs/脉图运动复盘系统_开发团队交付手册_v1.md`
- 全局架构契约 `fit-arch-contrac`

硬性约束：

- 复盘 Tab 唯一数据源仍是 `get_fatigue_review(activity_id)`。
- 前端只能展示后端返回的 `data.curves.power / cadence / hr / altitude / grade / terrain_load / distance`。
- 前端不得计算、补齐、拉伸、推断 power/cadence。
- 前端不得从 `points`、DOM、ECharts 现有 series、速度曲线或 UI fallback 生成功率/踏频。
- 不改 `main.py`、不改 DB、不改 AI prompt、不改 AI 输出 schema。
- `shadow_diff / shadow_diff_json / diff / records / points / raw_records / track_points` 仍不得进入复盘主展示。
- 图层开关只影响视图，不改变 `_lastFatigueReviewData`、不写 DB、不写缓存。

---

## 二、任务背景

当前复盘主图已经有分层 ECharts：

- `renderProfileAnalysisChart(...)`
- `_renderFatigueReviewLayeredEcharts(...)`
- `_applyFatigueReviewLayerVisibility(...)`
- `fr-layer-toggle-row`
- `fr-lane-rail`

但当前主图 lane 定义仍偏跑步：

```text
心率
配速
坡度修正配速（GAP）
效率
海拔
坡度
地形负荷
```

对于骑行活动，这会导致：

- 主图默认仍把配速/GAP/效率放到核心位置。
- 即使后端已有 `curves.power / curves.cadence`，前端也没有稳定展示。
- 用户打开骑行复盘时，视觉重点和 AI 解释重点不一致。

P4 的目标是让骑行主图进入专项模式：

```text
默认核心：功率 + 心率 + 海拔
可选辅助：踏频 + 坡度 + 地形负荷
弱化或隐藏：配速/GAP/跑步效率
```

---

## 三、目标行为

### 1. 骑行主图默认图层

当 `data.sport_type` 属于：

```text
cycling
road_cycling
mountain_biking
```

主图默认应优先展示：

```text
power_curve      功率 W
hr_curve         心率 bpm
altitude_curve   海拔 m
```

并支持可选展示：

```text
cadence_curve      踏频 rpm
grade_curve        坡度 %
terrain_load_curve 地形负荷
```

要求：

- `power_curve` 来自 `data.curves.power`。
- `cadence_curve` 来自 `data.curves.cadence`。
- `hr_curve` 来自 `data.curves.hr`。
- `altitude_curve` 来自 `data.curves.altitude`。
- 距离轴仍只来自 `data.curves.distance`。

### 2. 跑步主图保持现状

当 `sport_type` 为 running / trail_running / treadmill_running 或其他非骑行类型：

- 继续保留当前跑步图层：
  - 心率
  - 配速
  - GAP
  - 效率
  - 海拔
  - 坡度
  - 地形负荷
- 不改变跑步复盘主图默认语义。
- 不让骑行新增图层破坏既有 P7/P8 测试。

### 3. 空态与降级

骑行活动无功率：

- `power_curve` 为空时，不显示功率 lane。
- 主图仍可展示心率、海拔、坡度、地形负荷等后端已有曲线。
- 空态文案不得说“未记录配速/GAP”作为主要原因；应说明“后端未返回可绘制的功率、心率、海拔、踏频或地形曲线”。

骑行活动无踏频：

- `cadence_curve` 为空时，不显示踏频 lane。
- 不用速度推断踏频。

所有骑行主图曲线都为空：

- 展示空态，不初始化 ECharts 或清理旧实例。
- 空态必须说明后端未返回可绘制的骑行曲线。

---

## 四、前端数据映射契约

### 1. `chartPayload`

`_renderFatigueReview` 构造 `chartPayload` 时必须包含：

```js
{
  sport_type: data.sport_type,
  distance_curve: data.curves.distance,
  hr_curve: data.curves.hr,
  power_curve: data.curves.power,
  cadence_curve: data.curves.cadence,
  altitude_curve: data.curves.altitude,
  grade_curve: data.curves.grade,
  terrain_load_curve: data.curves.terrain_load,
  ...
}
```

跑步现有字段继续保留：

```js
pace_curve
pace_raw_curve
pace_capped_curve
gap_pace_curve
gap_pace_raw_curve
gap_pace_capped_curve
efficiency_curve
```

要求：

- `sport_type` 必须进入 chartPayload，供 `_renderFatigueReviewLayeredEcharts` 选择 laneDefs。
- `power_curve / cadence_curve` 只从 `data.curves` 读取。
- 不得使用 `speed_curve` 计算 power、cadence 或 pace。

### 2. 图层开关

需要新增或调整开关：

```text
power
cadence
```

要求：

- `data-fr-layer-toggle="power"` 对应 `power_curve`。
- `data-fr-layer-toggle="cadence"` 对应 `cadence_curve`。
- 图层 toggle 仅清空 payload 中对应曲线数组，不改变原始 `_lastFatigueReviewChartPayload`。
- 非骑行场景下 power/cadence toggle 可以隐藏、禁用或保留为无数据状态；必须在完成报告说明选择。
- 既有开关 `hr / speed / gap / efficiency / altitude / grade / terrainLoad / zones / events` 不得回归。

---

## 五、ECharts lane 契约

### 1. 建议新增 sport mode helper

建议新增：

```js
function _fatigueReviewChartSportMode(sportType) {
  ...
}
```

返回：

```text
cycling
running
general
```

### 2. 建议新增 laneDefs builder

建议将 laneDefs 抽成 helper：

```js
function _fatigueReviewChartLaneDefs(activityData) {
  ...
}
```

骑行 laneDefs 建议：

```js
[
  { key: 'power_curve', name: '功率', unit: 'W', color: '#f59e0b', ... },
  { key: 'hr_curve', name: '心率', unit: 'bpm', color: '#ef4444', ... },
  { key: 'altitude_curve', name: '海拔', unit: 'm', color: '#94a3b8', ... },
  { key: 'cadence_curve', name: '踏频', unit: 'rpm', color: '#38bdf8', ... },
  { key: 'grade_curve', name: '坡度', unit: '%', color: '#f97316', ... },
  { key: 'terrain_load_curve', name: '地形负荷', unit: 'grade×speed×s', color: '#14b8a6', seriesType: 'bar', ... }
]
```

跑步 laneDefs 保持当前：

```js
心率 / 配速 / GAP / 效率 / 海拔 / 坡度 / 地形负荷
```

要求：

- 骑行 laneDefs 不默认包含 `pace_curve / gap_pace_curve / efficiency_curve`。
- 如果后续产品想保留速度辅助层，必须单独作为后续任务，不在 P4 偷偷加入。
- 每条 lane 都必须使用 `_frPairDistanceCurve(distanceCurve, curve)` 或现有安全 pair helper。
- 不得根据曲线长度不一致做前端插值；长度不同只按现有 pair 逻辑展示同下标已有点，事实同轴由后端保证。

---

## 六、允许修改的文件

优先修改：

- `track.html`
- `tests/test_fatigue_review_quality_gate.py`
- `tests/test_v9_0_detail_tab_review.py`

建议新增：

- `docs/p4_cycling_fatigue_review_chart_completion_report.md`

必要时修改：

- `docs/fatigue_review_realignment_plan_v1.md`
- `docs/js_api_contract.json`

禁止或暂缓修改：

- `main.py`
- `llm_backend.py`
- `metrics_resolver.py`
- DB schema / migration
- AI 输出 schema

---

## 七、实施步骤

### Step 1：现状调查

先确认并记录：

- `_renderFatigueReview` 如何构造 `chartPayload`。
- `_applyFatigueReviewLayerVisibility` 当前支持哪些图层。
- `_renderFatigueReviewLayeredEcharts` 当前 laneDefs。
- `fr-layer-toggle-row` 当前 HTML。
- 现有测试对 layer toggle 和 laneDefs 的断言。

### Step 2：扩展 chartPayload

在 `_renderFatigueReview` 的 chartPayload 中加入：

- `sport_type`
- `power_curve`
- `cadence_curve`

同时扩展 all-curves-empty 判断：

- 骑行场景必须把 `curves.power / curves.cadence` 纳入判断。
- 跑步场景保持现有判断。

### Step 3：扩展 layer visibility

更新 `_fatigueReviewLayerVisibility` 或相关初始化：

- 新增 `power`
- 新增 `cadence`

更新 `_applyFatigueReviewLayerVisibility(...)`：

- `!visible.power` 时清空 `power_curve`。
- `!visible.cadence` 时清空 `cadence_curve`。

更新 `fr-layer-toggle-row`：

- 增加功率/踏频开关。
- 保持旧开关不回归。

### Step 4：按运动类型构建 laneDefs

将 `_renderFatigueReviewLayeredEcharts` 中的 laneDefs 改为按 sport mode 选择：

- cycling：功率、心率、海拔、踏频、坡度、地形负荷。
- running/general：保留现有 laneDefs。

要求：

- 骑行模式下默认不渲染配速/GAP/效率 lane。
- lane rail 和 tooltip 也应展示骑行中文名：功率、踏频。
- 骑行 tooltip 数值单位正确：W / rpm / bpm / m / %。

### Step 5：补测试

至少覆盖：

- `chartPayload` 包含 `sport_type / power_curve / cadence_curve`。
- `_applyFatigueReviewLayerVisibility` 支持 `power / cadence`。
- HTML 中存在 `data-fr-layer-toggle="power"` 和 `data-fr-layer-toggle="cadence"`。
- `_renderFatigueReviewLayeredEcharts` 或 laneDefs helper 中包含骑行 `power_curve / cadence_curve`。
- 骑行 laneDefs 不默认包含 `pace_curve / gap_pace_curve / efficiency_curve`。
- 跑步 laneDefs 仍包含 `pace_curve / gap_pace_curve / efficiency_curve`。
- 前端没有出现从 speed/pace 计算 power/cadence 的代码。
- `main.py / llm_backend.py` 未被本任务修改。

### Step 6：写完成报告

新增：

```text
docs/p4_cycling_fatigue_review_chart_completion_report.md
```

报告必须包含：

- 本次目标。
- 现状调查。
- 前端实现内容。
- 跑步保持不变的说明。
- 数据边界与禁止事项。
- 测试命令与结果。
- 剩余风险。
- 下一步。

---

## 八、验收标准

完成后必须满足：

- 骑行活动复盘主图和跑步不同。
- 骑行主图默认优先显示功率、心率、海拔。
- 骑行主图支持踏频图层。
- 图层开关支持 power/cadence。
- 复盘主图仍只使用后端 `get_fatigue_review.data.curves`。
- 前端不计算、不补齐、不推断 power/cadence。
- 跑步主图不回归。
- AI prompt/schema 不变。
- 后端算法不变。
- DB schema 不变。

---

## 九、建议验证命令

优先运行：

```bash
python3 -m pytest tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py
```

如修改契约文档：

```bash
python3 -m json.tool docs/js_api_contract.json
```

如担心后端契约回归：

```bash
python3 -m pytest tests/test_cycling_fatigue_review_snapshot.py tests/test_cycling_fatigue_review_metrics.py tests/test_fatigue_review_contract_realignment.py
```

---

## 十、完成报告模板

```text
# P4 骑行复盘主图模式完成报告

## 1. 本次目标

- ...

## 2. 现状调查

- chartPayload：
- layer visibility：
- laneDefs：
- 现有测试：

## 3. 实现内容

- chartPayload：
- layer toggle：
- cycling laneDefs：
- running laneDefs：
- 空态：

## 4. 契约保持不变

- 数据源：
- 前端零推断：
- AI 边界：
- 后端边界：

## 5. 明确不做

- 未改后端算法。
- 未改 AI prompt/schema。
- 未改 DB。
- 未新增速度推导功率/踏频。

## 6. 验证

- 运行命令：
- 结果：

## 7. 剩余风险

- ...

## 8. 下一步

- P5/P4b：骑行指标卡展示专项化。
- P3b 可选：power-based efficiency / durability。
```

---

## 十一、给执行 Agent 的最后提醒

P4-cycling 是展示层任务，不是算法任务。

请保持边界：

- 可以改 `track.html` 主图映射。
- 可以补前端静态契约测试。
- 可以写完成报告。
- 不改后端计算。
- 不改 AI。
- 不从速度、配速、坡度或心率推导功率/踏频。
