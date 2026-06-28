# P1 骑行复盘快照入源与数据质量提示词

> 任务类型：P1 骑行复盘快照入源
> 前置条件：P0-cycling 契约已完成，`get_fatigue_review(activity_id)` 已声明 `curves.power / curves.cadence / summary / data_quality`
> 核心目标：让骑行活动的功率与踏频从真实 FIT / DB canonical 数据进入复盘后端快照，并给出可测试的数据质量判定
> 不包含：骑行专项评分算法、前端 ECharts 主图改造、LLM 输出逻辑改造、DB schema 迁移

---

## 零、架构契约核对

执行本任务前必须先阅读并遵守：

- `docs/p0_cycling_fatigue_review_contract_prompt.md`
- `docs/p0_cycling_fatigue_review_contract_completion_report.md`
- `docs/js_api_contract.json` 中 `get_fatigue_review` 与 `fatigue_review_ai_contract`
- `docs/fatigue_review_realignment_plan_v1.md` 的 `P0-cycling` 章节
- `docs/脉图运动复盘系统_开发团队交付手册_v1.md`
- 全局架构契约 `fit-arch-contrac`

硬性约束：

- `get_fatigue_review(activity_id)` 仍是复盘页面唯一权威数据源。
- 数据流必须遵循 FIT / GPX → fit_engine → resolver → SQLite canonical DB → API snapshot → UI。
- 后端负责曲线同轴、字段白名单、空态和数据质量判定；前端只展示。
- 本任务只做 power/cadence 入快照和数据质量判定，不实现 `power_variability`、`pedaling_stability`、骑行效率或骑行耐久评分。
- 本任务不修改 `track.html` 主图 ECharts；骑行主图展示专项化留到后续阶段。
- 本任务不修改 `llm_backend.py` 的 LLM 输出规则；AI 提示词专项化留到后续阶段。
- `shadow_diff`、`shadow_diff_json`、`diff`、原始 records、全量 points、FIT 原始消息禁止进入 API data 与 AI compact snapshot。
- canonical DB 只读，不写入 synthetic / mock / AI 生成指标。

---

## 一、任务背景

P0-cycling 已完成契约预留：

- `data.curves.power`
- `data.curves.cadence`
- `data.summary.avg_power`
- `data.summary.max_power`
- `data.summary.normalized_power`
- `data.summary.avg_cadence`
- `data.summary.power_available`
- `data.summary.cadence_available`
- `data.summary.power_points_count`
- `data.summary.cadence_points_count`
- `data.summary.power_data_quality`
- `data.summary.cadence_data_quality`
- `metrics.power_variability`
- `metrics.pedaling_stability`

但 P0 只是契约与保守占位。P1-cycling 的任务是让这些字段真正从已有活动数据中稳定、可追溯地输出，尤其要处理：

- FIT 点中有 `power`，但曲线长度可能与距离轴不一致。
- DB 中有 `cadence_curve`，但可能是 JSON 字符串、空数组或与距离轴不同轴。
- `avg_power / max_power / normalized_power / avg_cadence` 可能在 activities 表中已有，也可能缺失。
- 骑行无功率时必须明确降级，不能让后续 UI 或 AI 误以为可以做完整功率复盘。

---

## 二、任务目标

完成 P1 骑行复盘快照入源：

1. 静态调查当前 power/cadence 数据来源、单位、字段名和缺失策略。
2. 确认 `_build_fatigue_review_curve_bundle(row)` 是否已经提取 `power_curve / cadence_curve`。
3. 确认 `_build_fatigue_review_curves_snapshot(bundle, resolved)` 是否按 `curves.distance` 主轴输出 `power / cadence`。
4. 实现或完善 power/cadence 曲线长度校验与同轴策略。
5. 实现或完善 `summary` 中 power/cadence 标量与数据质量字段。
6. 确保 AI compact snapshot 只拿 summary 与 curves_summary，不拿全量 power/cadence 曲线。
7. 新增或更新测试，覆盖有功率、有踏频、无功率、样本不足、长度不匹配等场景。

---

## 三、适用范围

本任务优先覆盖：

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

- 非骑行活动也可以带 `curves.power / curves.cadence` 空数组和 `summary` 空态，但不得因此改变现有跑步复盘行为。
- `indoor_cycling` 如果已有功率和踏频，可允许字段自然输出；但本任务不要求室内骑行完整专项验收。
- `e_biking / e_mountain_biking` 暂不纳入专项判断，避免电助力活动污染普通骑行能力解释。

---

## 四、必须先调查的数据来源

正式改代码前，先完成数据来源调查，并写入完成报告。

### 1. activities 表字段

核对 `_fetch_activity_row()` 是否返回：

- `avg_power`
- `max_power`
- `normalized_power`
- `avg_cadence`
- `cadence_curve`
- `track_json`
- `points_json`
- `merged_track_json`
- `sport_type`
- `duration` / `duration_sec`
- `dist_km` / `distance`

### 2. track_json / points_json 点结构

确认点结构是否可能包含：

- `power`
- `watts`
- `enhanced_power`
- `cadence`
- `distance`
- `time` / `timestamp`
- `hr`
- `speed`
- `alt`

要求：

- 优先复用已有 `_convert_track_to_algorithm_records()` 与 `_record_power()` 风格，不新增平行解析体系。
- 点级 power/cadence 只在后端内部用于构建曲线，不得暴露原始 points。

### 3. 现有 bundle / snapshot 链路

确认以下函数当前行为：

- `_build_fatigue_review_curve_bundle(row)`
- `_build_resolved_payload_v81(bundle, sport_type)`
- `_build_fatigue_review_curves_snapshot(bundle, resolved)`
- `_summarize_fatigue_review_curves_for_ai(curves)`
- `_build_fatigue_review_insight_snapshot(activity_id, sport_type)`

重点回答：

- `power_curve` 来自 track records 还是 DB 字段？
- `cadence_curve` 来自 DB JSON 还是 track records？
- 曲线长度和 `distance_curve_m` 不一致时目前怎么处理？
- AI compact snapshot 是否只包含摘要，不包含全量曲线？

---

## 五、目标输出契约

### 1. API `curves`

`get_fatigue_review(activity_id).data.curves` 必须满足：

```json
{
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
```

要求：

- `curves.power` 单位 W。
- `curves.cadence` 单位 rpm 或设备原始踏频单位；若项目无法确认单位，必须在完成报告标注。
- `curves.power / curves.cadence` 必须与 `curves.distance` 同轴。
- 若无法同轴，返回空数组并通过 `summary.*_data_quality` 标记。
- 前端不得补齐、插值、拉伸、推断 power/cadence。

### 2. API `summary`

`get_fatigue_review(activity_id).data.summary` 必须满足：

```json
{
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
```

字段语义：

- `avg_power / max_power / normalized_power` 来自 DB canonical 或 FIT session 已持久化字段。
- `avg_cadence` 来自 DB canonical 字段。
- `power_available` 仅表示本次活动有足够可用功率样本，不等于评分可信。
- `cadence_available` 仅表示本次活动有足够可用踏频样本，不等于评分可信。
- `power_points_count / cadence_points_count` 统计有效正值样本数。
- `power_data_quality / cadence_data_quality` 必须是枚举：

```text
available
missing
insufficient_points
invalid_values
length_mismatch
unavailable
```

### 3. AI compact snapshot

`_build_fatigue_review_insight_snapshot()` 输出必须包含：

```json
{
  "summary": {},
  "curves_summary": {
    "has_power": false,
    "has_cadence": false,
    "power_points_count": 0,
    "cadence_points_count": 0
  }
}
```

要求：

- AI compact snapshot 不得包含全量 `curves.power`。
- AI compact snapshot 不得包含全量 `curves.cadence`。
- 无功率骑行必须能通过 `summary.power_data_quality` 被识别。

---

## 六、数据质量判定规则

### 1. 通用规则

建议使用后端 helper 统一判断：

```python
def _fatigue_review_data_quality(values, axis_len=None, min_points=20):
    ...
```

要求：

- 非 list 或空 list → `missing`
- 全部为 `None / 0 / 负数` → `missing`
- 有明显异常值且异常占比过高 → `invalid_values`
- 有效点数小于阈值 → `insufficient_points`
- 传入 `axis_len` 且长度不一致 → `length_mismatch`
- 有效点数足够且长度匹配 → `available`

### 2. 功率过滤建议

P1 只做保守过滤，不做复杂算法：

- 有效功率：`0 < power <= 2500`
- `power <= 0` 不计入有效样本。
- `power > 2500` 视为异常值。
- 若异常值占比过高，标记 `invalid_values`。
- 不在 P1 区分真实滑行 0W 与缺失 0W，只在完成报告记录为后续风险。

### 3. 踏频过滤建议

P1 只做保守过滤：

- 有效踏频：`0 < cadence <= 250`
- `cadence <= 0` 不计入有效样本。
- `cadence > 250` 视为异常值。
- 若异常值占比过高，标记 `invalid_values`。

### 4. 长度与同轴

规则：

- 如果 source curve 长度等于 `distance_curve_m` 长度，直接规范化输出。
- 如果已有后端安全重采样函数，可使用后端重采样对齐到距离轴。
- 如果没有可靠距离轴或无法重采样，返回空数组并标记 `length_mismatch` 或 `unavailable`。
- 禁止让前端处理长度不一致。

---

## 七、允许修改的文件

优先修改：

- `main.py`
- `tests/test_fatigue_review_contract_realignment.py`
- `tests/test_fatigue_review_e2e_contract.py`
- `tests/test_fatigue_review_ai_insight_p6.py`

建议新增：

- `tests/test_cycling_fatigue_review_snapshot.py`
- `docs/p1_cycling_fatigue_review_snapshot_completion_report.md`

必要时修改：

- `docs/js_api_contract.json`
- `docs/fatigue_review_realignment_plan_v1.md`
- `docs/脉图运动复盘系统_开发团队交付手册_v1.md`

禁止或暂缓修改：

- `track.html`
- `llm_backend.py`
- `metrics_resolver.py` 中真实专项评分算法
- `gap_calculator.py`
- DB schema / migration

说明：

- 如果发现 `metrics_resolver.py` 已有 power/cadence 解析 helper，可只读复用，不在本任务中扩展评分语义。
- 如必须修改 `metrics_resolver.py` 才能复用安全解析函数，修改必须局限在解析/工具函数，不得新增骑行评分算法。

---

## 八、实施步骤

### Step 1：现状调查

输出字段矩阵：

| 字段 | 来源 | 单位 | 当前是否可用 | 缺失策略 |
|---|---|---|---|---|
| avg_power | activities | W | ? | null |
| max_power | activities | W | ? | null |
| normalized_power | activities | W | ? | null |
| avg_cadence | activities | rpm/unknown | ? | null |
| power_curve | track records | W | ? | [] |
| cadence_curve | DB JSON / track records | rpm/unknown | ? | [] |

### Step 2：完善 bundle

检查或完善 `_build_fatigue_review_curve_bundle(row)`：

- 输出 `power_curve`。
- 输出 `cadence_curve`。
- 输出标量 `avg_power / max_power / normalized_power / avg_cadence` 所需来源。
- 保持 records 仅后端内部使用，不进入 API data。

### Step 3：完善 curves snapshot

检查或完善 `_build_fatigue_review_curves_snapshot(bundle, resolved)`：

- `curves.power` 与距离轴同轴。
- `curves.cadence` 与距离轴同轴。
- 长度不匹配时返回空数组或后端可信重采样结果。
- 不改变其他曲线原有行为。

### Step 4：完善 summary

检查或完善 `_build_fatigue_review_summary(...)`：

- 输出 DB 标量。
- 统计有效功率点数。
- 统计有效踏频点数。
- 输出 `available / missing / insufficient_points / invalid_values / length_mismatch / unavailable`。
- 对非骑行活动保持保守空态，不影响跑步复盘。

### Step 5：完善 AI compact snapshot

检查或完善 `_summarize_fatigue_review_curves_for_ai()` 与 `_build_fatigue_review_insight_snapshot()`：

- 输出 `has_power / has_cadence`。
- 输出 `power_points_count / cadence_points_count`。
- 输出 `summary`。
- 确保不包含全量 power/cadence 曲线。

### Step 6：新增测试

至少覆盖：

- 有功率、有踏频、长度匹配 → `curves.power / curves.cadence` 非空，`summary.*_available=true`。
- 无功率 → `curves.power=[]`，`power_available=false`，`power_data_quality=missing`。
- 功率点数不足 → `power_data_quality=insufficient_points`。
- 功率异常值过多 → `power_data_quality=invalid_values`。
- 功率长度不匹配且无法重采样 → `curves.power=[]`，`power_data_quality=length_mismatch` 或 `unavailable`。
- AI compact snapshot 含摘要，不含全量 power/cadence 曲线。
- 跑步活动现有复盘字段不回归。

---

## 九、验收标准

完成后必须满足：

- `get_fatigue_review` 对骑行活动输出真实可追溯的 `curves.power / curves.cadence`。
- `curves.power / curves.cadence` 与 `curves.distance` 同轴，或明确空态降级。
- `summary.power_data_quality / cadence_data_quality` 能区分 missing、insufficient_points、invalid_values、length_mismatch。
- AI compact snapshot 只包含摘要，不包含全量 power/cadence 曲线。
- 跑步、徒步、游泳现有复盘契约不回归。
- `shadow_diff / diff / records / points` 仍不得进入 API data。
- 没有修改 `track.html`。
- 没有实现骑行专项评分算法。

---

## 十、验证命令

建议运行：

```bash
python3 -m pytest tests/test_fatigue_review_contract_realignment.py tests/test_fatigue_review_e2e_contract.py
python3 -m pytest tests/test_fatigue_review_ai_insight_p6.py tests/test_fatigue_review_prompts.py
```

如果新增 `tests/test_cycling_fatigue_review_snapshot.py`：

```bash
python3 -m pytest tests/test_cycling_fatigue_review_snapshot.py
```

如修改契约文档：

```bash
python3 -m json.tool docs/js_api_contract.json
```

---

## 十一、完成报告模板

完成后新增：

```text
docs/p1_cycling_fatigue_review_snapshot_completion_report.md
```

报告必须包含：

```text
P1 骑行复盘快照入源与数据质量完成报告

1. 本次目标
- ...

2. 数据来源调查
- activities 字段：
- track_json 点结构：
- bundle 当前行为：

3. 实现内容
- curves.power：
- curves.cadence：
- summary：
- AI compact snapshot：

4. 明确不做
- 未改前端：
- 未改 LLM 输出：
- 未实现专项评分：
- 未改 DB：

5. 验证
- 运行命令：
- 结果：

6. 剩余风险
- 0W 滑行与缺失 0W 的区分：
- 踏频单位确认：
- 室内骑行扩展：

7. 下一步
- P2：AI 骑行提示词专项化
- P3：骑行专项指标实现
- P4：前端主图骑行模式
```

---

## 十二、给执行 Agent 的最后提醒

P1-cycling 的目标不是“评估骑得好不好”，而是让后端快照可信地说清楚“有没有功率、有没有踏频、这些数据能不能用”。

请保持任务边界：

- 可以接入真实 power/cadence 曲线。
- 可以做数据质量判定。
- 可以补测试和完成报告。
- 不做骑行评分。
- 不改主图 ECharts。
- 不让 AI 开始解释尚未计算的骑行专项指标。
