# P0 骑行复盘专项化契约与边界提示词

> 任务类型：P0 契约与边界确认
> 适用范围：运动复盘功能中骑行活动的 `get_fatigue_review(activity_id)` API 契约、AI 输入契约、测试契约与文档边界
> 核心目标：先把骑行复盘的专项字段、降级规则和禁止事项写清楚，为后续 P1/P2 实现提供稳定边界
> 不包含：算法实现、前端展示改造、AI 生成逻辑改造、DB schema 迁移

---

## 零、架构契约核对

执行本任务前必须先阅读并遵守：

- `docs/js_api_contract.json` 中 `get_fatigue_review` 与 `fatigue_review_ai_contract` 现有契约
- `docs/fatigue_review_realignment_plan_v1.md`
- `docs/脉图运动复盘系统_开发团队交付手册_v1.md`
- `docs/p0_fatigue_review_contract_prompt.md`
- `docs/p1_fatigue_review_algorithm_realignment_prompt.md`
- 全局架构契约 `fit-arch-contrac`

硬性约束：

- 脉图是本地 AI 运动外挂，不引入 SaaS、微服务、消息队列、Feature Store、云计算节点。
- 数据流必须遵循 FIT / GPX → fit_engine → resolver → SQLite canonical DB → API snapshot → UI。
- `get_fatigue_review(activity_id)` 仍是复盘页面唯一权威数据源。
- Resolver / 后端算法层是唯一事实指标来源，前端只展示，不生成事实指标。
- 本任务只固化骑行专项契约与边界，不实现 power/cadence 算法，不改前端图表，不改 AI 调用链。
- `shadow_diff`、`shadow_diff_json`、`diff`、原始 records、全量 points、FIT 原始消息禁止进入复盘 API data 与 AI compact snapshot。
- 所有新增或变更 API 契约必须更新 `docs/js_api_contract.json`。
- 所有 API 响应必须继续使用统一 envelope：`{code,msg,data,traceId}`。

---

## 一、任务背景

当前运动复盘功能已经具备跑步复盘的基础链路，也已在底层解析中保留部分骑行字段：

- `track_json` / records 中可能含 `power`。
- activities 表中已有 `avg_power`、`max_power`、`normalized_power`。
- activities 表中已有 `avg_cadence`、`cadence_curve`。
- Bonk / energy gap 事件检测链路已经可以接收 `power_curve` 作为内部证据。

但单次复盘的对外契约仍然偏跑步：

- `curves` 白名单没有 `power` / `cadence`。
- AI compact snapshot 只有 `has_hr`、`has_speed`、`has_altitude`、`has_grade`、`has_gap`、`has_efficiency`，没有功率/踏频摘要。
- `metrics.cadence_stability` 目前只适用于 running / trail_running，骑行直接 unavailable。
- `metrics.efficiency` 当前基础算法是 `speed / hr`，对骑行不应作为有功率场景下的主效率指标。
- `metrics.durability` 当前基于前后段速度保持度，骑行中容易被坡度、风、滑行、路口干扰。
- AI 提示词虽然要求 cycling 依赖 NP，但上游 snapshot 没有把 NP / power curve / cadence 摘要作为稳定输入。

本任务是骑行复盘专项化的 P0：只把边界、字段契约、降级规则和测试约束先写清楚，为后续实现拆任务。

---

## 二、任务目标

完成 P0 骑行复盘专项化契约定义：

1. 明确骑行复盘第一阶段覆盖的运动类型。
2. 明确 `get_fatigue_review` 对骑行活动必须暴露哪些新增字段。
3. 明确 AI compact snapshot 对骑行必须包含哪些功率/踏频摘要。
4. 明确有功率、无功率、功率样本不足时的降级规则。
5. 明确哪些现有跑步指标可以复用，哪些必须在后续 P 阶段分支改造。
6. 明确 P0 不实现算法、不改 UI、不改 LLM 生成逻辑。
7. 新增或更新契约测试，保证文档契约不再遗漏 power/cadence。

---

## 三、骑行适用范围

P0 先覆盖以下运动类型：

```text
cycling
road_cycling
mountain_biking
```

暂缓但需要在文档中注明的类型：

```text
indoor_cycling
gravel_cycling
track_cycling
hand_cycling
e_biking
e_mountain_biking
```

要求：

- P0 不需要实现这些暂缓类型的专项逻辑。
- 文档必须说明后续扩展时应统一走 cycling mode，而不是复制跑步逻辑。
- `road_cycling`、`mountain_biking` 必须明确归入骑行复盘契约。

---

## 四、目标 API 契约增量

在现有 `get_fatigue_review(activity_id)` 契约基础上，为骑行活动新增或预留以下字段。

### 1. `curves` 增量

目标结构：

```json
{
  "curves": {
    "distance": [],
    "time": [],
    "hr": [],
    "speed": [],
    "altitude": [],
    "grade": [],
    "gap": [],
    "efficiency": [],
    "terrain_load": [],
    "power": [],
    "cadence": [],
    "total_distance_m": 0
  }
}
```

字段要求：

- `curves.power`：骑行功率曲线，单位 W，必须与 `curves.distance` 同轴；无数据时为空数组。
- `curves.cadence`：骑行踏频曲线，单位 rpm 或设备原始踏频单位，契约中必须明确；无数据时为空数组。
- `curves.power` / `curves.cadence` 长度必须由后端统一校验。
- 曲线长度不匹配时，后端返回空数组或后端重采样后的同轴曲线，禁止前端补齐、推断或拉伸。
- P0 只定义契约；是否重采样、如何过滤异常值留到 P1/P2。

### 2. `summary` 增量

建议新增 `summary`，用于承载单次复盘的活动级摘要，避免把标量塞进 `metrics`：

```json
{
  "summary": {
    "avg_power": null,
    "max_power": null,
    "normalized_power": null,
    "avg_cadence": null,
    "power_available": false,
    "cadence_available": false,
    "power_points_count": 0,
    "cadence_points_count": 0,
    "power_data_quality": "missing",
    "cadence_data_quality": "missing"
  }
}
```

字段要求：

- `avg_power`：平均功率，单位 W。
- `max_power`：最大功率，单位 W。
- `normalized_power`：标准化功率 NP，单位 W。
- `avg_cadence`：平均踏频，单位 rpm 或设备原始踏频单位。
- `power_available`：只表示本次活动是否有可用功率数据，不代表质量一定高。
- `cadence_available`：只表示本次活动是否有可用踏频数据，不代表质量一定高。
- `power_points_count` / `cadence_points_count`：用于 AI 与 UI 判断数据覆盖度。
- `power_data_quality` 可取：`available | missing | insufficient_points | invalid_values | unavailable`。
- `cadence_data_quality` 可取：`available | missing | insufficient_points | invalid_values | unavailable`。

P0 允许后端暂时只输出保守值，但契约必须写清楚这些字段的目标含义。

### 3. `metrics` 增量预留

P0 只定义目标，不实现算法：

```json
{
  "metrics": {
    "power_variability": {},
    "pedaling_stability": {}
  }
}
```

字段定位：

- `power_variability`：后续用于 `VI = NP / AvgPower`、功率波动水平、输出稳定性。
- `pedaling_stability`：后续用于骑行踏频稳定，不复用跑步的 `cadence_stability` 语义。

兼容要求：

- 现有 `cadence_stability` 保留给跑步，不在 P0 删除。
- P0 不要求 `power_variability` / `pedaling_stability` 有有效分数。
- 空态必须结构完整，可返回 `{}` 或带 `confidence: "unavailable"` 的空对象，具体形态需在契约中固定。

---

## 五、AI compact snapshot 契约增量

`__FATIGUE_REVIEW_INSIGHT__` 后端 compact snapshot 必须预留骑行摘要字段。

目标增量：

```json
{
  "curves_summary": {
    "has_power": false,
    "has_cadence": false,
    "power_points_count": 0,
    "cadence_points_count": 0
  },
  "summary": {
    "avg_power": null,
    "max_power": null,
    "normalized_power": null,
    "avg_cadence": null,
    "power_available": false,
    "cadence_available": false,
    "power_data_quality": "missing",
    "cadence_data_quality": "missing"
  }
}
```

AI 输入约束：

- AI compact snapshot 只能来自后端权威 `get_fatigue_review` 快照或同源 DB row。
- 禁止 AI 消费前端 DOM、ECharts、截图、活动标题、设备名、路线名、前端曲线 payload。
- 禁止把全量 `curves.power` / `curves.cadence` 直接塞进 AI prompt；AI 只需要摘要和后端已计算指标。
- 无功率骑行必须在 compact snapshot 中体现 `power_available=false` 或 `power_data_quality=missing`。
- P0 不修改 LLM 生成逻辑，只更新契约描述和测试约束。

---

## 六、骑行降级规则

P0 必须把以下降级规则写入契约或文档：

### 有功率

- 骑行复盘应以功率为核心事实之一。
- `normalized_power`、`avg_power`、`power_curve` 可用于后续 P 阶段计算输出稳定性、功率耐久、功率效率。
- AI 解读不得忽略功率摘要。

### 无功率

- 骑行复盘降级为 HR / speed / altitude / grade 辅助复盘。
- 必须标记功率数据不足，不能输出完整功率复盘口吻。
- 速度相关结论必须低可信度，因为速度受坡度、风、停顿、滑行影响大。

### 功率样本不足

- `power_available` 可以为 false，或 `power_data_quality=insufficient_points`。
- 不得用少量功率点推导整场输出稳定性。
- AI 不得基于少量功率点做长期能力或 FTP 推断。

### 踏频缺失

- `cadence_available=false` 或 `cadence_data_quality=missing`。
- 不展示踏频稳定结论。
- AI 不得编造踏频组织、踏频衰减、低踏高扭矩等判断。

---

## 七、明确禁止

本任务中禁止：

- 禁止实现 `power_variability`、`pedaling_stability` 的真实算法。
- 禁止修改 `track.html` 做骑行前端展示。
- 禁止修改 `llm_backend.py` 的 LLM 输出逻辑。
- 禁止修改 DB schema 或写迁移脚本。
- 禁止把 `power_curve`、`cadence_curve` 全量数据塞进 AI prompt。
- 禁止前端补算功率、踏频、距离轴或复盘指标。
- 禁止把 `shadow_diff`、`shadow_diff_json`、`diff`、records、全量 points 暴露到 API data。
- 禁止让无功率骑行显示为完整功率复盘。
- 禁止把跑步的“配速/步频稳定”文案声明为骑行核心契约。
- 禁止为了测试通过写入 mock / synthetic 指标到 canonical DB。

---

## 八、允许修改的文件

优先修改：

- `docs/js_api_contract.json`
- `docs/fatigue_review_realignment_plan_v1.md`
- `docs/脉图运动复盘系统_开发团队交付手册_v1.md`

建议新增：

- `docs/p0_cycling_fatigue_review_contract_completion_report.md`

建议新增或更新测试：

- `tests/test_fatigue_review_contract_realignment.py`
- `tests/test_fatigue_review_e2e_contract.py`
- `tests/test_fatigue_review_ai_insight_p6.py`
- `tests/test_fatigue_review_prompts.py`

只有在测试需要空态字段占位时，才允许轻微修改：

- `main.py`

禁止在本任务中大规模改动：

- `track.html`
- `metrics_resolver.py`
- `gap_calculator.py`
- `llm_backend.py`
- `profile_backend.py`

---

## 九、实施步骤

### Step 1：现状核对

先静态核对并在完成报告中记录：

- `get_fatigue_review` 当前 `curves` 白名单字段。
- `_empty_fatigue_review_snapshot()` 当前空态字段。
- `_build_fatigue_review_insight_snapshot()` 当前 compact snapshot 字段。
- `docs/js_api_contract.json` 中 `get_fatigue_review` 当前 returns/contract。
- `fatigue_review_ai_contract` 当前 compact snapshot 描述。

### Step 2：更新 API 契约

修改 `docs/js_api_contract.json`：

- `get_fatigue_review.returns` 中加入 `curves.power`、`curves.cadence`。
- `get_fatigue_review.returns` 中加入 `summary` 或明确等价字段承载位置。
- `get_fatigue_review.returns` 中预留 `metrics.power_variability`、`metrics.pedaling_stability`。
- `get_fatigue_review.contract` 中写明骑行 power/cadence 后端权威、同轴、前端零推断。
- `get_fatigue_review.description` 中写明 P0 只固化骑行专项契约，不实现算法。
- `fatigue_review_ai_contract` 中加入 AI compact snapshot 的骑行摘要字段。

### Step 3：更新设计/开发文档

修改 `docs/fatigue_review_realignment_plan_v1.md` 或开发手册：

- 增加“骑行复盘专项化 P0”章节。
- 写明本阶段覆盖运动类型。
- 写明有功率、无功率、功率样本不足、踏频缺失的降级规则。
- 写明后续 P 阶段才实现算法和 UI。

### Step 4：补充契约测试

新增或更新测试，至少覆盖：

- `docs/js_api_contract.json` 的 `get_fatigue_review.returns` 包含 `curves.power`。
- `docs/js_api_contract.json` 的 `get_fatigue_review.returns` 包含 `curves.cadence`。
- `docs/js_api_contract.json` 的 `get_fatigue_review.returns` 包含 `summary` 或等价骑行摘要字段。
- `docs/js_api_contract.json` 的 contract 包含“前端不得推断 power/cadence”。
- `fatigue_review_ai_contract` 包含 `has_power` / `has_cadence` / `power_data_quality`。
- forbidden 字段仍包含 `shadow_diff`、`shadow_diff_json`、`diff`、`records`、`points`。

### Step 5：必要时补后端空态占位

如果新增测试要求 API 空态字段完整，允许最小修改 `_empty_fatigue_review_snapshot()`：

- `curves.power: []`
- `curves.cadence: []`
- `summary.power_available: false`
- `summary.cadence_available: false`
- `summary.power_data_quality: "missing"`
- `summary.cadence_data_quality: "missing"`

要求：

- 不实现真实算法。
- 不改 Resolver。
- 不改前端。
- 不改 AI 输出逻辑。

### Step 6：运行验证

运行最小契约测试：

```bash
python -m pytest tests/test_fatigue_review_contract_realignment.py tests/test_fatigue_review_e2e_contract.py
```

如修改 AI contract 测试，一并运行：

```bash
python -m pytest tests/test_fatigue_review_ai_insight_p6.py tests/test_fatigue_review_prompts.py
```

---

## 十、验收标准

完成后必须满足：

- `docs/js_api_contract.json` 已明确骑行 `curves.power` / `curves.cadence` 契约。
- `get_fatigue_review` 契约已明确骑行 summary / data quality 字段。
- AI compact snapshot 契约已明确 `has_power`、`has_cadence`、`power_data_quality`。
- 文档明确覆盖 `cycling`、`road_cycling`、`mountain_biking`。
- 文档明确无功率骑行必须降级，不得完整功率复盘。
- 文档明确 P0 不实现算法、不改 UI、不改 LLM 输出逻辑。
- forbidden 字段隔离规则没有放松。
- 契约测试通过，或完成报告中说明失败原因与下一步。

---

## 十一、完成报告模板

完成后输出报告，必须包含：

```text
P0 骑行复盘专项化契约与边界完成报告

1. 本次目标
- ...

2. 现状核对
- get_fatigue_review 当前 curves 字段：
- AI compact snapshot 当前字段：
- 现有禁用字段隔离结果：

3. 契约变更
- API returns：
- API contract：
- AI compact snapshot：
- 文档补充：

4. 明确不做
- 未实现算法：
- 未改前端：
- 未改 AI 输出：
- 未改 DB：

5. 验证
- 运行命令：
- 结果：

6. 剩余风险
- ...

7. 下一步
- P1：复盘快照补齐 power/cadence
- P2：AI compact snapshot 接入骑行摘要
- P3：骑行专项指标实现
```

---

## 十二、给执行 Agent 的最后提醒

本任务的价值不是“把骑行复盘做完”，而是防止后续实现继续在跑步契约里塞骑行逻辑。

请保持 P0 的克制：

- 只确认契约。
- 只补文档和测试约束。
- 只在必要时补空态占位。
- 不做真实算法。
- 不做 UI。
- 不让 AI 先行解释尚未进入权威快照的字段。
