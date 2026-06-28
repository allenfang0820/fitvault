# P2 骑行复盘 AI 提示词专项化提示词

> 任务类型：P2 骑行复盘 AI prompt 专项化
> 前置条件：P0-cycling 契约已完成，P1-cycling 已让 `summary` 与 `curves_summary` 稳定进入 AI compact snapshot
> 核心目标：让骑行活动的 AI 复盘基于功率、踏频、心率与地形关系解释；无功率时明确降级，不再套用跑步复盘语言
> 不包含：骑行评分算法、前端 ECharts 主图改造、DB schema 迁移、真实 LLM 联调、AI 输出 schema 变更

---

## 零、执行前重新思考

执行本任务前，先重新确认以下判断是否仍然成立：

- P0 已经把骑行复盘的 API 契约、AI compact snapshot 契约和降级边界写清楚。
- P1 已经让 `summary.avg_power / normalized_power / avg_cadence / power_data_quality / cadence_data_quality` 进入后端快照。
- P1 已经让 `curves_summary.has_power / has_cadence / power_points_count / cadence_points_count` 进入 AI compact snapshot。
- 当前问题不是“缺少功率数据入口”，而是“AI prompt 仍然偏跑步语言，无法稳定按骑行数据质量降级”。
- 本任务应保持很薄：只改 AI prompt 契约和 prompt 测试，不实现新的骑行指标。

如果上述任意条件不成立，先补齐对应前置任务，不要在 P2 中绕过契约直接让 AI 猜。

---

## 一、架构契约核对

执行本任务前必须先阅读并遵守：

- `docs/p0_cycling_fatigue_review_contract_prompt.md`
- `docs/p0_cycling_fatigue_review_contract_completion_report.md`
- `docs/p1_cycling_fatigue_review_snapshot_prompt.md`
- `docs/p1_cycling_fatigue_review_snapshot_completion_report.md`
- `docs/js_api_contract.json` 中 `get_fatigue_review` 与 `fatigue_review_ai_contract`
- `docs/fatigue_review_realignment_plan_v1.md`
- `docs/脉图运动复盘系统_开发团队交付手册_v1.md`
- 全局架构契约 `fit-arch-contrac`

硬性约束：

- `get_fatigue_review(activity_id)` 仍是复盘页面唯一权威数据源。
- AI 只消费后端 `_build_fatigue_review_insight_snapshot(activity_id, sport_type)` 生成的 compact snapshot。
- 前端不得构建 prompt，不得把 ECharts payload、DOM、截图、全量曲线或 UI fallback 值传给 AI。
- LLM 只能解释后端已提供的字段，禁止重新计算、估算、推断或生成 canonical 指标。
- `shadow_diff`、`shadow_diff_json`、`diff`、records、points、track_points、原始 FIT 消息禁止进入 prompt payload。
- 本任务不得修改 AI 输出 JSON schema；仍输出 `summary / key_dimensions / event_interpretation / training_advice / disclaimer`。
- `key_dimensions` 仍严格包含 `overall_stability / fatigue_progression / risk_triggers / context_impact` 四维。

---

## 二、任务背景

P1-cycling 完成后，骑行复盘 AI compact snapshot 已经具备：

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
  },
  "curves_summary": {
    "has_power": false,
    "has_cadence": false,
    "power_points_count": 0,
    "cadence_points_count": 0
  }
}
```

但当前 `llm_backend.build_fatigue_review_messages()` 对骑行只有粗粒度约束：

```text
cycling:必须依赖功率(NP)评估;若缺功率,声明数据质量不足
```

这会带来几个风险：

- 有功率时，AI 仍可能把“配速、步频、节奏稳定”作为核心解释。
- 无功率时，AI 可能用速度和心率写出过度确定的骑行功率复盘。
- 踏频数据存在时，AI 不知道它是辅助解释项。
- 踏频缺失时，AI 可能编造踏频组织或低踏高扭矩判断。
- `overall_stability` 维度说明仍偏跑步，骑行场景下语义不够准确。

P2 的目标是让 prompt 明确告诉 AI：骑行复盘要优先解释功率、踏频、心率和地形关系；当功率质量不足时必须降级，并声明结论置信度受限。

---

## 三、任务目标

完成 P2 骑行复盘 AI 提示词专项化：

1. 调整 `llm_backend.build_fatigue_review_messages()` 中 cycling mode 的专项约束。
2. 明确骑行有功率、无功率、功率样本不足、功率长度不匹配、踏频缺失时的 AI 解读边界。
3. 调整四维说明中 `overall_stability` 的骑行语义，避免跑步化表达。
4. 保持跑步、徒步、游泳现有 prompt 行为不回归。
5. 保持 AI 输出 schema、normalizer、sentinel 调用链不变。
6. 新增或更新 prompt 契约测试，确保骑行规则可长期守住。
7. 新增完成报告，记录本次改动、未做事项和验证结果。

---

## 四、允许修改的文件

优先修改：

- `llm_backend.py`
- `tests/test_fatigue_review_prompts.py`

建议新增：

- `docs/p2_cycling_fatigue_review_ai_prompt_completion_report.md`

必要时修改：

- `docs/fatigue_review_realignment_plan_v1.md`
- `docs/js_api_contract.json`

禁止或暂缓修改：

- `main.py` 中 power/cadence 入源逻辑，除非发现 P1 明确缺陷且必须修复才能完成 prompt 测试。
- `track.html`
- `metrics_resolver.py` 中真实骑行专项评分算法。
- `fit_engine.py`
- DB schema / migration。
- AI 输出 schema 和 `normalize_fatigue_review_json()` 的结构契约。

---

## 五、骑行 prompt 必须表达的规则

### 1. 骑行核心解释顺序

当 `sport_mode == "cycling"` 时，prompt 必须要求 AI 优先参考：

1. `summary.power_data_quality`
2. `summary.normalized_power`
3. `summary.avg_power`
4. `summary.power_points_count` 或 `curves_summary.power_points_count`
5. `summary.cadence_data_quality`
6. `summary.avg_cadence`
7. `curves_summary.has_power / has_cadence`
8. 心率、爬升、坡度、速度等辅助事实

要求：

- 功率可用时，骑行稳定性优先解释功率输出与心率反应，而不是速度快慢。
- 踏频可用时，踏频只作为踩踏组织和输出稳定性的辅助证据。
- 速度可以作为外部结果参考，但不能替代功率判断训练输出，因为速度受坡度、风、滑行、停顿和路况影响很大。

### 2. 有功率时

如果 `power_data_quality == "available"` 或 `power_available == true`：

- 可以解释 `normalized_power` 与 `avg_power` 共同反映的输出强度和波动倾向。
- 可以结合心率描述“功率输出与心率反应是否一致”。
- 可以结合坡度、爬升、地形描述功率波动的外部背景。
- 不得推断 FTP、功率区间、TSS、IF、VI 或 W/kg，除非这些字段已经由 snapshot 明确提供。
- 不得从 `normalized_power / avg_power` 自行计算 VI。

### 3. 无功率或功率质量不足时

如果 `power_data_quality` 为以下任意值：

```text
missing
insufficient_points
invalid_values
length_mismatch
unavailable
```

AI 必须降级：

- 明确说明本次缺少足够可用功率数据，功率相关判断置信度受限。
- 只能基于心率、速度、爬升、坡度、疲劳区间、风险事件和环境背景做辅助复盘。
- 不能输出完整功率复盘。
- 不能说“功率稳定”“后段功率下降”“输出过猛”“功率耐久不足”等没有后端指标支撑的结论。
- 速度相关结论必须表达为低置信或辅助观察。

### 4. 踏频可用时

如果 `cadence_data_quality == "available"` 或 `cadence_available == true`：

- 可以把 `avg_cadence` 作为踩踏组织的辅助背景。
- 可以表达踏频是否可作为解释疲劳或输出稳定性的辅助线索。
- 不得推断左右平衡、扭矩、齿比、低踏高扭矩、踏频衰减，除非 snapshot 明确提供。

### 5. 踏频缺失或质量不足时

如果 `cadence_data_quality` 为以下任意值：

```text
missing
insufficient_points
invalid_values
length_mismatch
unavailable
```

AI 必须：

- 避免给出踏频稳定性结论。
- 不得编造踏频组织、踏频衰减、低踏高扭矩、踩踏效率等判断。
- 可以简短说明踏频数据不足，无法评估踩踏组织。

### 6. 禁止跑步化表达

骑行 prompt 必须明确禁止把以下跑步核心词作为骑行的主要解释框架：

```text
配速
步频
跑姿
触地
步幅
跑步节奏
恢复跑
跑步赛道
```

说明：

- 如果 snapshot 中已有 `speed`，AI 可以说“速度”或“车速”，但不能把“配速”作为核心指标。
- 如果通用四维里需要表达稳定性，骑行应写为“功率输出、心率反应、踏频组织、爬升/坡度背景下的节奏”，而不是“配速、步频和跑步节奏”。

---

## 六、四维输出契约

输出结构不变：

```json
{
  "summary": "",
  "key_dimensions": [
    {"key": "overall_stability", "label": "全程稳定性", "level": "good|warn|bad|unknown", "comment": ""},
    {"key": "fatigue_progression", "label": "疲劳阶段", "level": "good|warn|bad|unknown", "comment": ""},
    {"key": "risk_triggers", "label": "风险触发", "level": "good|warn|bad|unknown", "comment": ""},
    {"key": "context_impact", "label": "外部影响", "level": "good|warn|bad|unknown", "comment": ""}
  ],
  "event_interpretation": "",
  "training_advice": "",
  "disclaimer": ""
}
```

骑行语义要求：

- `overall_stability`：解释功率输出、心率反应、踏频组织、坡度/爬升背景下的整体稳定性；无功率时必须标记稳定性判断受限。
- `fatigue_progression`：解释后端 `fatigue_zones` 中疲劳是否出现、从哪里出现、是否持续或加重；不得从速度下降自行推断疲劳。
- `risk_triggers`：解释 `bonk_risk`、`collapse_events`、训练负荷或后端已识别事件；不得编造爆缸、抽筋、FTP 崩盘等事件。
- `context_impact`：解释天气、温度、湿度、风、爬升、坡度、地形和 context_tags 对本次表现的影响；不得把地形变化误写成跑步赛道变化。

---

## 七、禁止事项

执行 P2 时必须保证：

- 不新增或修改骑行评分算法。
- 不计算 VI、FTP、IF、TSS、W/kg、功率区间、左右平衡、扭矩、齿比。
- 不让 AI 从 full curves 还原 per-point 趋势。
- 不把 `curves.power` 或 `curves.cadence` 全量数组塞入 prompt。
- 不修改 `get_fatigue_review` API envelope。
- 不修改前端复盘页面。
- 不修改 ECharts 主图。
- 不新增 DB 字段。
- 不改变跑步 prompt 的核心语义，除非是为了抽象出通用文案并保持测试通过。

---

## 八、实施步骤

### Step 1：阅读现状

先查看：

- `llm_backend.py::build_fatigue_review_messages()`
- `tests/test_fatigue_review_prompts.py`
- `main.py::_build_fatigue_review_insight_snapshot()`
- `main.py::_summarize_fatigue_review_curves_for_ai()`

确认：

- AI prompt payload 是否来自 compact snapshot。
- compact snapshot 是否有 `summary` 和 `curves_summary`。
- 当前 cycling prompt 具体有哪些跑步化描述。

### Step 2：改造 cycling prompt

在 `build_fatigue_review_messages()` 中做最小改造：

- 保留 DATA BOUNDARY、MUST NOT、输出 JSON schema 等已有硬约束。
- 将 `cycling` 专项约束从一句话扩展为可执行规则。
- 增加骑行数据质量降级规则。
- 增加禁止跑步化表达规则。
- 调整四维说明，让 `overall_stability` 对不同 sport mode 的语义更准确。

建议优先通过清晰的文本约束完成，不要引入复杂代码分支。

### Step 3：补充测试

在 `tests/test_fatigue_review_prompts.py` 中新增或增强测试，至少覆盖：

- cycling prompt 包含 `summary.power_data_quality`、`normalized_power`、`avg_power`、`avg_cadence`、`curves_summary.has_power` 等字段引用或等价说明。
- cycling prompt 包含 `missing / insufficient_points / invalid_values / length_mismatch / unavailable` 降级枚举。
- cycling prompt 明确说明无功率时不能做完整功率复盘。
- cycling prompt 明确禁止“配速 / 步频 / 跑姿”等跑步化表达作为核心解释框架。
- cycling prompt 明确禁止计算 FTP、VI、IF、TSS、W/kg。
- running prompt 仍包含有氧解耦、心率漂移、Bonk 等跑步专项规则。
- prompt payload 不泄漏全量 `curves.power / curves.cadence`，前提是输入 compact snapshot 本身不含全量曲线。

### Step 4：更新文档

如执行中修改了计划或契约，更新：

- `docs/fatigue_review_realignment_plan_v1.md`
- `docs/js_api_contract.json`

如果只是实现 prompt 和测试，文档可只新增完成报告。

### Step 5：写完成报告

新增：

```text
docs/p2_cycling_fatigue_review_ai_prompt_completion_report.md
```

完成报告必须记录：

- 本次目标。
- 修改文件。
- prompt 新增的骑行专项规则。
- 无功率/踏频缺失降级规则。
- 明确未做事项。
- 测试命令与结果。
- 剩余风险和下一步。

---

## 九、验收标准

完成后必须满足：

- 骑行 AI prompt 明确以功率、踏频、心率和地形关系为核心解释框架。
- 有功率时，prompt 要求优先参考 `normalized_power / avg_power / power_data_quality`。
- 无功率或功率质量不足时，prompt 要求明确降级且禁止完整功率复盘。
- 踏频缺失时，prompt 禁止踏频稳定性或踩踏效率臆测。
- 骑行 prompt 不再把“配速、步频、跑步节奏”作为核心说明。
- AI 输出 JSON schema 不变。
- `key_dimensions` 四维不变。
- AI compact snapshot 仍不包含全量 power/cadence 曲线。
- 跑步 prompt 测试不回归。
- 没有修改前端主图和骑行评分算法。

---

## 十、建议验证命令

优先运行：

```bash
python3 -m pytest tests/test_fatigue_review_prompts.py
```

如修改了 AI compact snapshot 或契约测试，再运行：

```bash
python3 -m pytest tests/test_fatigue_review_ai_insight_p6.py tests/test_cycling_fatigue_review_snapshot.py
```

如修改了文档契约或 API 契约，再运行：

```bash
python3 -m pytest tests/test_fatigue_review_contract_realignment.py tests/test_fatigue_review_e2e_contract.py
python3 -m json.tool docs/js_api_contract.json
```

---

## 十一、完成报告模板

```text
# P2 骑行复盘 AI 提示词专项化完成报告

## 1. 本次目标

- ...

## 2. 修改文件

- ...

## 3. Prompt 规则变更

- 有功率：
- 无功率：
- 踏频可用：
- 踏频缺失：
- 禁止跑步化表达：

## 4. 契约保持不变

- AI 输出 schema：
- key_dimensions 四维：
- compact snapshot 白名单：
- 前端边界：

## 5. 明确不做

- 未实现骑行评分算法。
- 未改前端 ECharts。
- 未改 DB schema。
- 未做真实 LLM 联调。

## 6. 验证

- 运行命令：
- 结果：

## 7. 剩余风险

- ...

## 8. 下一步

- P3：骑行专项指标实现。
- P4：前端主图骑行模式。
```

---

## 十二、给执行 Agent 的最后提醒

P2-cycling 的关键不是让 AI “更会夸骑行”，而是让它在数据不足时诚实、在数据充足时抓住骑行真正重要的证据。

请保持边界：

- 可以改 prompt。
- 可以补 prompt 测试。
- 可以写完成报告。
- 不做评分。
- 不改图表。
- 不让 AI 推断没有后端提供的功率、踏频或训练学指标。
