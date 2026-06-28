# P3 骑行复盘专项指标实现提示词

> 任务类型：P3-cycling 后端骑行专项指标实现
> 前置条件：P0-cycling 契约已完成，P1-cycling 已让 power/cadence 入快照，P2-cycling 已完成 AI prompt 专项化
> 核心目标：把 `metrics.power_variability` 与 `metrics.pedaling_stability` 从 unavailable 占位升级为可测试、可降级、可解释的骑行专项指标
> 不包含：前端 ECharts 主图改造、AI 输出 schema 变更、DB schema 迁移、真实 LLM 联调、FTP/TSS/IF 等训练负荷高级模型

---

## 零、执行前重新思考

执行本任务前，先重新确认任务边界是否合理：

- P0 已经预留 `metrics.power_variability / metrics.pedaling_stability`，但当前仍是 pending implementation。
- P1 已经保证 `curves.power / curves.cadence` 与 `curves.distance` 同轴，且 `summary.power_data_quality / cadence_data_quality` 可用于降级。
- P2 已经让 AI 知道：有功率时才能解释功率，缺功率时必须降级。
- 因此前端主图不是下一个最稳任务；先补后端指标事实更合理。
- 本任务只实现两项已预留指标，不顺手重写 `metrics.efficiency / metrics.durability`，避免一次变更多层语义。

如果发现 P1 的 power/cadence 入源仍不稳定，先修 P1 缺陷，不要在 P3 中用 mock、前端曲线或 AI 推断绕过。

---

## 一、架构契约核对

执行本任务前必须先阅读并遵守：

- `docs/p0_cycling_fatigue_review_contract_prompt.md`
- `docs/p0_cycling_fatigue_review_contract_completion_report.md`
- `docs/p1_cycling_fatigue_review_snapshot_prompt.md`
- `docs/p1_cycling_fatigue_review_snapshot_completion_report.md`
- `docs/p2_cycling_fatigue_review_ai_prompt.md`
- `docs/p2_cycling_fatigue_review_ai_prompt_completion_report.md`
- `docs/js_api_contract.json` 中 `get_fatigue_review`
- `docs/fatigue_review_realignment_plan_v1.md`
- 全局架构契约 `fit-arch-contrac`

硬性约束：

- `get_fatigue_review(activity_id)` 仍是复盘页面唯一权威数据源。
- 指标只能来自后端 canonical snapshot、resolver 结果、DB canonical 字段和同轴曲线。
- 前端不得计算、补齐、拉伸、推断 `power_variability / pedaling_stability`。
- AI 不参与指标计算。
- 不写 DB，不新增 DB 字段，不改 migration。
- 禁止使用 shadow_diff、debug-only 字段、records、points、原始 FIT 消息作为 API 返回。
- 所有指标必须有可解释降级路径；数据不足时返回 unavailable/unknown，而不是用速度或心率硬凑。

---

## 二、任务背景

当前 `main.py` 中复盘 metrics 已经有占位：

```json
{
  "power_variability": {
    "vi": null,
    "level": "unknown",
    "confidence": "unavailable",
    "reasons": ["cycling power metric pending implementation"]
  },
  "pedaling_stability": {
    "score": null,
    "level": "unknown",
    "confidence": "unavailable",
    "cv": null,
    "decay_pct": null,
    "reasons": ["cycling cadence metric pending implementation"]
  }
}
```

P1 已经补齐：

- `curves.power`
- `curves.cadence`
- `summary.avg_power`
- `summary.normalized_power`
- `summary.power_data_quality`
- `summary.cadence_data_quality`

P3 的目标是让上述占位变成真实后端指标，并保持无功率/无踏频时的诚实降级。

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
hiking
swimming
```

要求：

- 非骑行活动必须保留结构完整的 unavailable 占位，不改变现有跑步复盘行为。
- `indoor_cycling` 可自然输出 power/cadence summary，但本任务不要求纳入专项验收。
- 电助力活动暂不进入普通骑行能力评价，避免电助力污染“输出稳定性”语义。

---

## 四、目标输出契约

### 1. `metrics.power_variability`

目标结构：

```json
{
  "vi": null,
  "level": "unknown",
  "confidence": "unavailable",
  "avg_power": null,
  "normalized_power": null,
  "power_points_count": 0,
  "power_data_quality": "missing",
  "reasons": []
}
```

字段语义：

- `vi`：Variability Index，计算方式仅允许 `normalized_power / avg_power`。
- `avg_power`：透传 `summary.avg_power`，单位 W。
- `normalized_power`：透传 `summary.normalized_power`，单位 W。
- `power_points_count`：透传 `summary.power_points_count` 或有效功率样本数。
- `power_data_quality`：透传 `summary.power_data_quality`。
- `level`：功率波动水平。
- `confidence`：指标可信度。
- `reasons`：用户不可见或开发解释用的简短原因数组，不能包含 raw points。

计算规则：

- 只有 `summary.power_data_quality == "available"` 且 `avg_power > 0` 且 `normalized_power > 0` 时才计算 `vi`。
- `vi = normalized_power / avg_power`，建议保留 2 位小数。
- 禁止从 power curve 自行计算 NP。
- 禁止计算 FTP、IF、TSS、W/kg、功率区间。
- 如果 `normalized_power` 缺失，即使 power curve 可用，也必须降级为 `confidence="low"` 或 `unavailable`，并说明缺少 NP。

建议分级：

```text
vi < 1.05       -> level="good"
1.05 <= vi < 1.15 -> level="moderate"
1.15 <= vi < 1.30 -> level="variable"
vi >= 1.30      -> level="surging"
```

可信度建议：

```text
power_data_quality != available -> confidence="unavailable"
power_points_count < 20         -> confidence="low"
20 <= points < 120              -> confidence="medium"
points >= 120                   -> confidence="high"
```

注意：

- 如果当前项目已有统一 level 枚举规范，可映射为 `good / warn / bad / unknown`，但必须在完成报告说明映射。
- 用户可见文案由 AI/前端再转译；本指标层只提供事实与枚举。

### 2. `metrics.pedaling_stability`

目标结构：

```json
{
  "score": null,
  "level": "unknown",
  "confidence": "unavailable",
  "cv": null,
  "decay_pct": null,
  "avg_cadence": null,
  "cadence_points_count": 0,
  "cadence_data_quality": "missing",
  "reasons": []
}
```

字段语义：

- `cv`：踏频变异系数，`std(cadence) / mean(cadence)`。
- `decay_pct`：后半程平均踏频相对前半程的变化百分比，`(tail_avg - head_avg) / head_avg * 100`。
- `score`：踏频稳定性粗评分，0-100。
- `avg_cadence`：透传 `summary.avg_cadence`。
- `cadence_points_count`：透传 `summary.cadence_points_count` 或有效踏频样本数。
- `cadence_data_quality`：透传 `summary.cadence_data_quality`。

计算规则：

- 只有 `summary.cadence_data_quality == "available"` 且有效踏频样本足够时才计算。
- 有效踏频范围沿用 P1：`0 < cadence <= 250`。
- `cv` 建议保留 3 位小数。
- `decay_pct` 建议保留 1 位小数。
- `score` 可用简单保守公式：

```text
base = 100
cv_penalty = min(45, cv * 300)
decay_penalty = min(35, abs(decay_pct) * 1.5)
score = clamp(base - cv_penalty - decay_penalty, 0, 100)
```

建议分级：

```text
score >= 80 -> level="good"
60 <= score < 80 -> level="moderate"
40 <= score < 60 -> level="unstable"
score < 40 -> level="poor"
```

可信度建议：

```text
cadence_data_quality != available -> confidence="unavailable"
cadence_points_count < 20         -> confidence="low"
20 <= points < 120                -> confidence="medium"
points >= 120                     -> confidence="high"
```

注意：

- 不得推断左右平衡、扭矩、齿比、低踏高扭矩。
- 踏频为 0 的点在 P1 已视为无效样本；P3 不重新定义这个规则。

---

## 五、降级契约

### 功率不可用

当 `power_data_quality` 为以下任意值：

```text
missing
insufficient_points
invalid_values
length_mismatch
unavailable
```

必须返回：

```json
{
  "vi": null,
  "level": "unknown",
  "confidence": "unavailable",
  "reasons": ["power data unavailable: <quality>"]
}
```

不得：

- 用速度替代功率。
- 用心率推断功率波动。
- 用曲线少量点推断整场功率稳定性。

### NP 或 AvgPower 缺失

当功率曲线可用但 `normalized_power` 或 `avg_power` 缺失：

- 不得计算 `vi`。
- 可返回 `confidence="low"` 或 `unavailable`。
- `reasons` 必须说明缺少 `normalized_power` 或 `avg_power`。

### 踏频不可用

当 `cadence_data_quality` 为以下任意值：

```text
missing
insufficient_points
invalid_values
length_mismatch
unavailable
```

必须返回：

```json
{
  "score": null,
  "level": "unknown",
  "confidence": "unavailable",
  "cv": null,
  "decay_pct": null,
  "reasons": ["cadence data unavailable: <quality>"]
}
```

不得：

- 编造踏频稳定性。
- 用速度或心率推断踩踏组织。
- 输出低踏高扭矩、踏频衰减等未被后端事实支撑的判断。

---

## 六、允许修改的文件

优先修改：

- `main.py`
- `tests/test_cycling_fatigue_review_snapshot.py`

建议新增：

- `tests/test_cycling_fatigue_review_metrics.py`
- `docs/p3_cycling_fatigue_review_metrics_completion_report.md`

必要时修改：

- `docs/js_api_contract.json`
- `docs/fatigue_review_realignment_plan_v1.md`
- `docs/脉图运动复盘系统_开发团队交付手册_v1.md`

禁止或暂缓修改：

- `track.html`
- `llm_backend.py`
- `metrics_resolver.py` 中雷达能力评分逻辑
- `fit_engine.py`
- DB schema / migration
- AI 输出 schema

说明：

- 如果实现 helper 放在 `main.py` 会让文件继续变胖，可在已有后端工具层中抽纯函数；但不得引入新服务或异步链路。
- 若发现已有安全统计 helper，可复用，不要复制一套复杂统计框架。

---

## 七、实施步骤

### Step 1：现状调查

先确认：

- `_build_fatigue_review_summary(...)` 当前输出字段。
- `_build_fatigue_review_snapshot(...)` 当前 metrics 构建位置。
- `_empty_fatigue_review_snapshot(...)` 中占位结构。
- 现有测试如何断言 `power_variability / pedaling_stability`。

输出调查结论到完成报告：

```text
power_variability 当前来源：
pedaling_stability 当前来源：
summary 字段可用性：
curves.power/cadence 同轴保障：
```

### Step 2：新增纯函数

建议新增后端纯函数：

```python
def _build_cycling_power_variability_metric(summary: dict[str, Any]) -> dict[str, Any]:
    ...

def _build_cycling_pedaling_stability_metric(summary: dict[str, Any], cadence_curve: list[Any]) -> dict[str, Any]:
    ...
```

要求：

- 纯函数不得访问 DB。
- 纯函数不得读取前端数据。
- 纯函数输入输出可直接单元测试。
- 所有数值必须经 `_safe_float` 等安全转换。

### Step 3：接入 snapshot metrics

在 `_build_fatigue_review_snapshot(...)` 中：

- 对 `cycling / road_cycling / mountain_biking` 接入真实 `power_variability / pedaling_stability`。
- 对非骑行活动保留 unavailable 占位。
- 对异常路径 `_empty_fatigue_review_snapshot(...)` 保留结构完整占位。

注意：

- P3 不改 `summary` 语义。
- P3 不改 `curves` 语义。
- P3 不改 `ai_insight` 结构。

### Step 4：补测试

至少覆盖：

- 有 `avg_power=200 / normalized_power=220 / power_data_quality=available` 时，`vi=1.10`。
- 不同 `vi` 区间能得到不同 `level`。
- 无功率或 `power_data_quality=missing` 时，`vi=null` 且 `confidence=unavailable`。
- `normalized_power` 缺失时不得计算 `vi`。
- cadence 稳定曲线能得到较高 `score` 与较低 `cv`。
- cadence 波动大或后半程明显变化时 `score` 下降。
- cadence 缺失或 `cadence_data_quality=missing` 时降级。
- 非骑行活动仍返回 unavailable 占位。
- `_empty_fatigue_review_snapshot(...)` 结构不缺字段。

### Step 5：更新契约文档

如果输出字段新增了 `avg_power / normalized_power / power_points_count / cadence_points_count / cadence_data_quality` 等子字段，必须更新：

- `docs/js_api_contract.json`
- `docs/fatigue_review_realignment_plan_v1.md`

文档必须说明：

- P3 已实现 `power_variability / pedaling_stability`。
- 仍未实现 power-based `efficiency / durability`。
- 前端仍不能自行计算。

### Step 6：写完成报告

新增：

```text
docs/p3_cycling_fatigue_review_metrics_completion_report.md
```

报告必须包含：

- 本次目标。
- 现状调查。
- 实现内容。
- 降级策略。
- 明确不做。
- 测试命令与结果。
- 剩余风险。
- 下一步。

---

## 八、验收标准

完成后必须满足：

- 骑行活动 `metrics.power_variability` 不再是 pending implementation 占位。
- 骑行活动有可用 `avg_power + normalized_power` 时能输出 `vi`。
- 无功率、NP 缺失、功率质量不足时能明确降级。
- 骑行活动 `metrics.pedaling_stability` 不再是 pending implementation 占位。
- 有可用踏频时能输出 `score / cv / decay_pct`。
- 无踏频或踏频质量不足时能明确降级。
- 非骑行活动不受影响。
- 前端无新增计算逻辑。
- AI prompt 和输出 schema 不变。
- DB schema 不变。

---

## 九、建议验证命令

优先运行：

```bash
python3 -m pytest tests/test_cycling_fatigue_review_metrics.py
python3 -m pytest tests/test_cycling_fatigue_review_snapshot.py
```

如修改契约测试，再运行：

```bash
python3 -m pytest tests/test_fatigue_review_contract_realignment.py tests/test_fatigue_review_e2e_contract.py
python3 -m json.tool docs/js_api_contract.json
```

如担心 AI 侧回归，再运行：

```bash
python3 -m pytest tests/test_fatigue_review_prompts.py tests/test_fatigue_review_ai_insight_p6.py
```

---

## 十、完成报告模板

```text
# P3 骑行复盘专项指标实现完成报告

## 1. 本次目标

- ...

## 2. 现状调查

- power_variability 当前状态：
- pedaling_stability 当前状态：
- summary / curves 输入：

## 3. 实现内容

- power_variability：
- pedaling_stability：
- snapshot metrics 接入：
- empty snapshot：

## 4. 降级策略

- 无功率：
- NP/AvgPower 缺失：
- 无踏频：
- 非骑行：

## 5. 明确不做

- 未改前端 ECharts。
- 未改 AI prompt / 输出 schema。
- 未实现 FTP / IF / TSS / W/kg。
- 未重写 efficiency / durability。
- 未改 DB schema。

## 6. 验证

- 运行命令：
- 结果：

## 7. 剩余风险

- ...

## 8. 下一步

- P4：前端主图骑行模式。
- P3b 可选：power-based efficiency / durability 语义改造。
```

---

## 十一、给执行 Agent 的最后提醒

P3-cycling 的目标不是“把骑行能力评价做完整”，而是先把两块已经承诺给 API 和 AI 的事实指标补上。

请保持边界：

- 可以实现 `power_variability`。
- 可以实现 `pedaling_stability`。
- 可以补测试和文档。
- 不做 FTP / TSS / IF / W/kg。
- 不改前端主图。
- 不让 AI 或前端参与指标计算。
