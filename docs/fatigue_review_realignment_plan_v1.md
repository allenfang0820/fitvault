# 运动复盘功能回正实施清单 v1

> 目标：把当前“已有曲线临时拼接的复盘面板”回正为符合交付手册、设计草图与 `fit-arch-contrac` 的可信运动复盘系统。
> 范围：先跑通复盘数据、算法、后端快照、前端展示；AI 洞察放到最后。
> 配套文档：`docs/脉图运动复盘系统_开发团队交付手册_v1.md`、`docs/design/运动复盘系统_页面设计草图_v1.png`。

---

## 状态总览

| 阶段 | 状态 | 完成摘要 |
|---|---|---|
| P0 数据契约回正 | 已完成 | `get_fatigue_review` 契约补齐 `metrics / curves.distance / fatigue_zones / collapse_events` 等白名单字段。 |
| P1 算法链路回正 | 已完成 | 废弃伪 records，改用真实 `track_json / points_json / merged_track_json` 和后端 Resolver / GapCalculator 链路。 |
| P2 后端快照回正 | 已完成 | 新增曲线快照标准化、距离轴清洗、曲线长度对齐和 forbidden 字段递归隔离。 |
| P3 前端最小可用回正 | 已完成 | 删除 `_distanceFromSpeedTime()`，前端直接消费 `data.curves.distance`，缺距离轴时展示空态。 |
| P4 按草图升级 UI | 已完成 | 复盘 Tab 重组为摘要、核心状态、能力负荷、主图、上下文/事件/建议侧栏。 |
| P5 测试与文档固化 | 已完成 | 新增质量门禁，覆盖前端零推断、后端 snapshot 白名单、曲线同源、P4 UI 和 AI 边界。 |
| P6 AI 洞察最后接入 | 已完成，入口冻结 | 修复 `__FATIGUE_REVIEW_INSIGHT__`，AI 只消费后端权威 compact insight snapshot，不写 DB；UI 定稿前前端按钮置灰。 |
| P6.1 AI 入口冻结 | 已完成 | 保留后端 P6 能力和测试，前端按钮禁用且不绑定 `onFatigueReviewAiInsight()`。 |
| P7 复盘分析驾驶舱 | 已完成，UI 基线冻结 | 保持现有活动详情顶部与 Tab 系统，仅在复盘 Tab 内按草图的“分析”页完成主图、泳道、事件图钉、状态阶段、右侧摘要和底部控制收口；AI 入口复核进入 P8。 |
| P0-cycling 骑行专项契约 | 已完成 | 为 `cycling / road_cycling / mountain_biking` 固化 `curves.power/cadence`、`summary`、数据质量与降级边界；不实现算法、不改 UI、不改 LLM 输出。 |
| P0-science 骑行解释信号契约 | 已完成 | 新增 `cycling_explanation_signals` 后端占位契约，锁定前端/AI 零推断；本阶段不计算 FTP/IF/TSS/Pw:Hr。 |
| P8 个人强度算法补齐 | 已完成 | 仅推进 `intensity_signal`：有 FTP、可用功率且样本足够时输出个人化强度分级；缺 FTP/缺功率/样本不足时明确降级。 |
| P2 有氧漂移解释信号 | 已完成，后续由 P9 升级 | 初版仅把 `hr_drift/decoupling` 作为参考 evidence；不输出确定性漂移结论。 |
| P9 心率反应/有氧漂移算法补齐 | 已完成 | 仅推进 `aerobic_drift_signal`：基于有效功率 + 心率段计算前后半功率/心率关系，输出 `stable/mild_drift/significant_drift`；缺心率、缺功率、样本不足或曲线不对齐时明确降级。 |
| P3 有效踩踏段后程保持 | 已完成 | 仅推进 `power_retention_signal`：过滤滑行、停顿、零功率、异常片段后评估有效踩踏段前后半功率保持；不改 UI/DB/AI。 |
| P4 骑行 pacing / 功率波动解释 | 已完成 | 仅推进 `pacing_signal`：结合 VI 与后端功率曲线摘要判断 `steady/variable/front_loaded/late_fade`；不改 UI/DB/AI。 |
| P10 踏频节奏解释信号 | 已完成 | 仅推进 `cadence_signal`：过滤无效踏频、零踏频、停顿、滑行和时间断裂后判断 `steady/variable/low_cadence_bias/cadence_drop/interrupted`；不诊断齿比、扭矩、左右平衡或真实踩踏技术。 |
| P11 关键证据标签产品化 | 已完成 | 仅收口 `cycling_explanation_signals.*.evidence` 的 `label/display_value/description/visibility/source`，前端优先只读后端展示字段；不新增训练负荷模型、不改 UI 布局/DB/AI。 |
| P6 AI 复盘输入升级 | 已完成 | AI compact snapshot 只透传后端 `cycling_explanation_signals`，prompt 明确只能解释后端 signals，不从曲线/DOM/points 自行推导。 |
| P5 现有复盘 UI 最小接入 | 已完成 | 骑行复盘现有卡片只读后端 `cycling_explanation_signals`，优先展示 signal.summary 和保守依据；不改主图、不新增模块、不计算新指标。 |
| P7 验收与真实样本复核 | 已完成 | 新增解释信号验收测试与手工清单，覆盖有 FTP/无 FTP/无功率/无心率/滑行多/样本不足/非骑行回归；真实样本人工复核仍需按清单执行。 |
| P0-visibility 复盘解释可见性闸门 | 已完成 | 在保持现有 UI 设计的前提下，固化 `available/partial/unavailable` 的用户可见规则；`partial` 只能作为参考，工程状态和占位语义不得进入用户文案。 |
| P1-card-semantics 现有骑行复盘卡片语义回正 | 已完成 | 在不改 UI 布局、不补算法的前提下，约束现有骑行卡片主结论来源：强度/有氧漂移只有 `available` signal 才能主导标题，`partial/unavailable` 只能温和降级。 |
| P2-real-sample-audit 真实样本解释质量复核 | 已完成 snapshot 审计；视觉人工验收待执行 | 用本地真实骑行 activity 复核 `cycling_explanation_signals`，修正后端 summary 中的工程态/占位态文案；不新增算法、不改 UI、不改 AI。 |
| P3-real-ui-card-audit 真实 UI 逐卡片验收 | 已完成 | 在 pywebview 真实 UI 中逐卡片检查骑行复盘文案，修正无功率骑行概览仍显示“整体稳定”的口径问题；只读后端 signals，不改布局/算法。 |
| P4-trustworthy-acceptance 骑行可信解释验收闭环 | 已完成 | 将有 FTP/无 FTP/无功率/无心率/滑行多/样本不足/非骑行回归整理为可重复验收矩阵，并新增门禁锁定“可说/不可说”和半成品文案黑名单。 |
| P5-real-ui-screenshot-audit 真实 UI 截图/视觉回归 | 已完成 | 复核 304/298/246/279/293 等真实骑行样本，记录有功率、无功率、下坡比例高和坡度极端场景的 UI/可信解释结论；不补算法、不改主图。 |
| P6-downhill-coasting-guard 滑行/下坡误判防线 | 已完成 | 筛选 279/248/283/252/246/257/262 等真实样本，确认可用功率样本的回落/保持结论均带有效踩踏过滤 evidence，功率不可用样本全部降级。 |
| P7-cycling-trust-freeze 骑行可信解释最终冻结 | 已完成 | 收口 P0-P6 骑行解释信号链路，冻结可说/不可说/只能参考规则；不新增算法、不改 UI/DB/AI，发布前只保留人工体感与跨浏览器截图复核风险。 |
| P12-real-evidence-polish 真实样本证据展示收口 | 已完成 | 复核 304/303/251/299/298/297/294/279/246/252 等真实骑行 snapshot，修正功率不可用时仍展示“本次功率”关键证据的问题；不新增算法、不改 UI/DB/AI。 |
| P13-cycling-events-zones-contract 骑行事件与疲劳带契约回正 | 已完成 | 固化骑行 `fatigue_zones / collapse_events` 为参考区间和后端显式事件语义，普通区间不再自动压缩成强事件；前端文案降级为“参考区间”。 |
| P14-cycling-zone-generation-calibration 骑行疲劳带生成逻辑校准 | 已完成 | 在 UI 暴露前增加后端骑行 fatigue zone 校准层，过滤下坡/滑行/停顿主导误报，并按 `cycling_explanation_signals` 可用性降级为参考区间。 |

---

## 0. 架构核对

### 必须遵守

- FIT / GPX → fit_engine → resolver → SQLite canonical DB → API snapshot → UI。
- Resolver 是唯一语义翻译层，复盘算法优先收敛到 Resolver 或专用算法层。
- 前端只做展示、格式化、交互和图表渲染，不生成事实指标。
- AI 洞察只消费后端权威 snapshot，不参与指标计算，不写 DB。
- `shadow_diff`、`shadow_diff_json`、`diff` 禁止进入复盘快照、前端主展示和 AI 输入。

### 历史偏离与当前处理状态

- `call_llm('__FATIGUE_REVIEW_INSIGHT__')` 无参调用 `_build_fatigue_review_snapshot(row)`：P6 已修复，P6.1 期间前端入口冻结。
- `_build_resolved_payload_v81()` 使用伪 records：P1 已改为真实 FIT / DB canonical 数据链路。
- 前端 `_distanceFromSpeedTime()` 推导距离轴：P3 已删除，前端只消费 `data.curves.distance`。
- `docs/js_api_contract.json` 中 `get_fatigue_review` 契约滞后：P0/P2/P6 已更新。

---

## P0 数据契约回正

### 目标

先固定 `get_fatigue_review(activity_id)` 的权威输出结构，所有后续算法、前端和 AI 都只消费这个契约。

### 必改文件

- `docs/js_api_contract.json`
- `docs/fatigue_review_realignment_plan_v1.md`
- 后续可补 `tests/test_fatigue_review_contract_realignment.py`

### 输出契约

```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "sport_type": "running",
    "metrics": {
      "hr_drift": {},
      "decoupling": {},
      "efficiency": {},
      "durability": {},
      "cadence_stability": {},
      "training_load": {},
      "bonk_risk": {},
      "events": {}
    },
    "fatigue_zones": [],
    "collapse_events": [],
    "curves": {
      "distance": [],
      "time": [],
      "hr": [],
      "speed": [],
      "altitude": [],
      "grade": [],
      "gap": [],
      "efficiency": [],
      "total_distance_m": 0
    },
    "context_tags": {},
    "ai_insight": null,
    "advice": "",
    "disclaimer": "AI 生成仅供参考 · 数据来源：FIT 解析 + 后端算法"
  },
  "traceId": "hex12"
}
```

### 验收标准

- `data` 不包含 `shadow_diff`、`shadow_diff_json`、`diff`、`records`、全量原始点。
- `curves.distance` 由后端权威输出，前端不得重建。
- `fatigue_zones.start_km/end_km` 与 `curves.distance` 使用同一距离来源。
- 缺少关键曲线时后端返回空数组，前端展示空态，不补算事实字段。

---

## P0-cycling 骑行复盘专项化契约

### 目标

在不改算法、不改前端、不改 LLM 输出的前提下，先把骑行复盘的专项字段和降级规则写入 `get_fatigue_review(activity_id)` 契约，避免后续继续把骑行塞进跑步复盘语义。

### 覆盖运动类型

- `cycling`
- `road_cycling`
- `mountain_biking`

后续扩展类型包括 `indoor_cycling`、`gravel_cycling`、`track_cycling`、`hand_cycling`、`e_biking`、`e_mountain_biking`，扩展时应统一走 cycling mode。

### 契约增量

`data.curves` 预留：

```json
{
  "power": [],
  "cadence": []
}
```

要求：

- `curves.power` 为后端权威功率曲线，单位 W，必须与 `curves.distance` 同轴。
- `curves.cadence` 为后端权威踏频曲线，单位 rpm 或设备原始踏频单位，必须与 `curves.distance` 同轴。
- 前端不得补算、推断、拉伸或从 DOM/ECharts/points 重建功率和踏频曲线。

`data.summary` 预留：

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

`data.metrics` 预留：

```json
{
  "power_variability": {
    "vi": null,
    "level": "unknown",
    "confidence": "unavailable",
    "avg_power": null,
    "normalized_power": null,
    "power_points_count": 0,
    "power_data_quality": "missing",
    "reasons": []
  },
  "pedaling_stability": {
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
}
```

### 降级规则

- 有功率：后续骑行专项指标可以使用 `power / normalized_power / cadence` 作为核心事实来源。
- 无功率：复盘只能降级为 HR / speed / altitude / grade 辅助解释，必须通过 `power_data_quality` 标记数据不足。
- 功率样本不足：不得推导整场输出稳定性，不得让 AI 做 FTP 或长期能力推断。
- 踏频缺失：不得展示踏频稳定结论，不得让 AI 编造踏频组织或踏频衰减。

### P3-cycling 后续状态

P3 已实现两项后端事实指标：

- `power_variability.vi`：仅由 `summary.normalized_power / summary.avg_power` 计算，禁止从曲线重算 NP，禁止计算 FTP / IF / TSS / W/kg。
- `pedaling_stability`：仅由同轴 `curves.cadence` 计算 `cv / decay_pct / score`。
- `power_data_quality / cadence_data_quality` 非 `available` 时必须降级为 `confidence="unavailable"`，并在 `reasons` 中说明原因。
- 非骑行活动保留结构完整的 unavailable 占位，不改变跑步复盘行为。

P3b 已实现两项骑行功率口径覆盖：

- `efficiency.basis = "power_hr"`：仅由 `summary.avg_power / avg_hr` 计算 `power_per_hr`，不使用速度/配速，不计算 FTP / IF / TSS / W/kg。
- `durability.basis = "power_retention"`：仅由同轴 `curves.power` 计算 `head_power / tail_power / power_retention_pct`，不得用速度后程保持冒充功率耐力。
- 缺功率、缺心率或样本不足时必须按 `power_data_quality` 降级，前端和 AI 均不得计算或补齐。

P5b 已完成前端指标卡 P3b 语义对齐：

- 骑行 profile 用户可见 `功率效率`，只读 `metrics.efficiency.power_per_hr / avg_power / avg_hr / basis`。
- 骑行 profile 用户可见 `后程功率保持`，只读 `metrics.durability.power_retention_pct / head_power / tail_power / basis`。
- 前端不从 `summary / curves / DOM / ECharts / points` 推导 P3b 指标。

P5c 已完成端到端验收与降级场景固化：

- 新增等价场景测试覆盖有功率、无功率、功率样本不足和非骑行回归。
- 固化骑行主图/指标卡与跑步不同的静态验收。
- 新增手工验收清单，方便后续用真实活动 ID 验证。

### P0-science 骑行解释信号契约

当前状态：已完成。

目标不是增加专业指标面板，而是为“像找教练复盘这一次骑行”预留后端解释依据。`get_fatigue_review(activity_id)` 新增 `data.cycling_explanation_signals`，前端和 AI 只能消费这个后端字段，不得从 `summary / metrics / curves / DOM / ECharts / points` 自行推导。

字段形态：

```json
{
  "status": "available | partial | unavailable",
  "intensity_signal": {"status": "unavailable", "level": "unknown", "summary": "", "evidence": [], "reasons": []},
  "aerobic_drift_signal": {"status": "unavailable", "level": "unknown", "summary": "", "evidence": [], "reasons": []},
  "power_retention_signal": {"status": "partial", "level": "unknown", "summary": "", "evidence": [], "reasons": []},
  "pacing_signal": {"status": "partial", "level": "unknown", "summary": "", "evidence": [], "reasons": []},
  "cadence_signal": {"status": "partial", "level": "unknown", "summary": "", "evidence": [], "reasons": []},
  "evidence": [],
  "unavailable_reasons": []
}
```

边界：

- 本阶段只返回后端保守占位结构，不实现 FTP、IF、TSS、W/kg、Pw:Hr、CTL/ATL/TSB、CP/W′。
- 无 FTP 时，不输出“阈值/高强度”等个人化强度判断。
- 无功率时，不输出功率强度、功率保持、功率波动的确定性结论。
- 无心率时，不输出有氧漂移的确定性结论。
- 专业指标未来只允许作为 `evidence`，默认 UI 主结论仍保持教练复盘口吻。
- 非骑行活动只能返回 `status="unavailable"` 或空安全结构，不获得完整骑行解释。
- AI compact snapshot 如包含 `cycling_explanation_signals`，只能来自 `review_snapshot.get("cycling_explanation_signals")`。

### P8 个人强度算法补齐

当前状态：已完成。

本任务严格继承原始任务清单，只处理 `cycling_explanation_signals.intensity_signal`，不推进 `aerobic_drift_signal / power_retention_signal / pacing_signal / cadence_signal`。

后端事实来源：

- `profile_backend.get_profile().ftp_watts`，缺失时兜底 `profile.ftp`。
- `summary.avg_power / max_power / normalized_power`。
- `summary.power_available / power_data_quality / power_points_count / duration_sec`。
- `profile.weight` 只作为 evidence，不作为默认 UI 主结论。

输出规则：

- 非骑行活动：`intensity_signal.status = "unavailable"`，原因包含 `not_cycling_activity`。
- 无可用功率：`intensity_signal.status = "unavailable"`，原因包含 `power_data_unavailable:*`，不得输出功率强度结论。
- 有功率但无个人 FTP：`intensity_signal.status = "unavailable"`，原因包含 `missing_ftp`，只允许在 `evidence` 中保留本次功率摘要和数据质量，不判断相对强度。
- 有功率、有个人 FTP、功率质量为 `available` 且样本足够：`intensity_signal.status = "available"`，`level` 可为 `recovery / endurance / tempo / threshold / high_intensity`。
- 功率质量不足或样本不足：`intensity_signal.status = "unavailable"`，原因包含 `power_data_unavailable:*` 或 `insufficient_power_points`，不得输出确定性强度结论。
- 优先使用 `normalized_power / FTP` 作为相对强度参考；NP 缺失时可保守使用 `avg_power / FTP`。

边界：

- 本任务不计算 IF / TSS / W/kg / Pw:Hr / CTL / ATL / TSB / CP/W′。
- `avg_power_to_ftp / normalized_power_to_ftp / intensity_ratio / weight_kg` 只作为后端 evidence，不作为默认 UI 主结论。
- 无 FTP 时不得输出“阈值/高强度”等个人化判断；有 FTP 且功率可用时，允许输出教练式个人强度结论。
- 前端和 AI 继续只读后端 snapshot，不从 `summary / metrics / curves / DOM / ECharts / points` 构造个人强度解释。

### P2 有氧漂移解释信号

当前状态：已完成。

本任务严格继承原始任务清单，只处理 `cycling_explanation_signals.aerobic_drift_signal`，不推进 `power_retention_signal / pacing_signal / cadence_signal`。P2 初版只建立降级边界和参考 evidence；P9 已在同一 signal 上补齐后端可用算法。

后端事实来源：

- `metrics.hr_drift`：通用心率漂移参考。
- `metrics.decoupling`：复盘 decoupling 参考。
- `summary.power_available / power_data_quality`。
- `curves.hr` 只用于后端判断心率数据是否存在，不进入 `evidence`。

输出规则：

- 非骑行活动：`aerobic_drift_signal.status = "unavailable"`，原因包含 `not_cycling_activity`。
- 缺心率：`aerobic_drift_signal.status = "unavailable"`，原因包含 `missing_hr`。
- 缺功率：`aerobic_drift_signal.status = "unavailable"`，原因包含 `power_data_unavailable:*`。
- P2 初版中，有心率且有功率但未启用专门算法时只能 `partial`；该限制已由 P9 替换为有效样本算法。
- `metrics.hr_drift / metrics.decoupling` 只能作为 `hr_drift_reference / review_decoupling_reference` evidence，不得绕过 P9 算法单独称为骑行功率-心率漂移结论。

边界：

- 本任务不实现完整 Pw:Hr 模型。
- 不把 `hr_drift / decoupling` 包装成骑行 power-HR decoupling。
- 不暴露完整 `curves / points / records / raw_records / shadow_diff / diff`。
- 前端和 AI 继续只读后端 snapshot，不构造有氧漂移解释。

### P9 心率反应/有氧漂移算法补齐

当前状态：已完成。

目标：

- 修复“心率反应/有氧漂移”卡片的半成品感，让有功率、有心率且样本足够的骑行可以给出可信教练解释。
- 仍保持现有 UI 设计，不新增专业指标面板，不复刻 TrainingPeaks/佳明。

后端事实来源：

- `summary.power_available / power_data_quality / power_points_count / avg_power`。
- 后端同轴 `curves.power / curves.hr / curves.speed / curves.time` 只用于内部过滤和计算，不进入 `evidence` 原始明细。
- `metrics.hr_drift / metrics.decoupling` 可继续作为参考 evidence，但不主导最终 `level`。

有效样本过滤：

- 过滤零功率、低功率滑行、异常功率、异常心率、低速停顿和明显时间断裂。
- 功率与心率曲线长度不一致、有效样本不足或前后半样本不足时必须 `unavailable`。

输出规则：

- `stable`：后半程功率/心率关系保持稳定，未看到明显有氧漂移。
- `mild_drift`：后半程同等心率下功率略有下降，出现轻微有氧漂移。
- `significant_drift`：后半程功率与心率关系明显分离，有氧漂移较明显。
- 缺心率：`aerobic_drift_signal.status = "unavailable"`，原因包含 `missing_hr`。
- 缺功率或功率质量不足：`aerobic_drift_signal.status = "unavailable"`，原因包含 `power_data_unavailable:*`。
- 样本不足：`aerobic_drift_signal.status = "unavailable"`，原因包含 `insufficient_power_hr_points`。

边界：

- 不输出 `Pw:Hr` 专业缩写，不计算 IF/TSS/W/kg/长期负荷。
- 不推断补给不足、脱水、天气、恢复差等未进入 snapshot 的原因。
- 不暴露 `curves / points / records / raw_records / shadow_diff / diff`。
- 前端和 AI 继续只读后端 `cycling_explanation_signals.aerobic_drift_signal`，不得自行从曲线补算。

### P3 有效踩踏段后程保持

当前状态：已完成。

本任务严格继承原始任务清单，只处理 `cycling_explanation_signals.power_retention_signal`，不推进 `pacing_signal / cadence_signal`，不改变既有 `metrics.durability` 指标卡计算结果。

目标：

- 升级后程功率保持解释，避免把下坡、滑行、停顿或零功率段误判成体能下降。
- 默认仍保持“教练复盘”口吻，专业数字只作为 `evidence`。

后端事实来源：

- `summary.power_available / power_data_quality / power_points_count / avg_power`。
- 后端同轴 `curves.power / curves.speed / curves.time` 仅用于内部过滤和计算，不进入 `evidence`。
- `metrics.durability` 可作为兼容 reference evidence，不作为有效踩踏段最终口径。

有效踩踏段过滤：

- 过滤零功率、低于动态阈值的滑行段、异常功率点。
- 过滤低速停顿点。
- 过滤时间倒退或明显时间断裂点。
- 前半程和后半程有效踩踏样本都足够时，才计算前后半有效功率保持。

输出规则：

- 非骑行活动：`power_retention_signal.status = "unavailable"`，原因包含 `not_cycling_activity`。
- 无功率或功率不可用：`status = "unavailable"`，`level = "unknown"`，原因包含 `power_data_unavailable:*`。
- 有功率但有效踩踏样本不足：`status = "unavailable"`，原因包含 `insufficient_effective_pedaling_points`，不得输出掉功率结论。
- 有效踩踏段足够：输出 `held / slight_drop / clear_drop`，并在 `evidence` 中给出 `effective_pedaling_power_retention` 摘要。

边界：

- 本任务不计算 FTP / IF / TSS / W/kg / Pw:Hr / CTL / ATL / TSB / CP/W′。
- 不新增 DB schema，不修改 `llm_backend.py`，不解冻 AI 入口。
- 不修改 `track.html` 或 ECharts。
- 不向前端或 AI 暴露 `points / records / raw_records / curves / shadow_diff / diff`。
- 不把速度后程保持包装成功率保持，不把下坡/滑行包装成体能下降。

### P4 骑行 pacing / 功率波动解释

当前状态：已完成。

本任务严格继承原始任务清单，只处理 `cycling_explanation_signals.pacing_signal`，不推进 `cadence_signal`，不改变既有 `metrics.power_variability / durability / efficiency / pedaling_stability` 计算结果。

目标：

- 解释“是不是前面骑太猛、输出太乱、后段是否回落”。
- 专业指标只作为后端 `evidence`，默认输出仍是教练复盘口吻。

后端事实来源：

- `metrics.power_variability.vi / level / confidence`。
- `metrics.durability.power_retention_pct` 作为后程保持参考。
- `summary.avg_power / normalized_power / power_available / power_data_quality / power_points_count`。
- 后端同轴 `curves.power` 仅用于内部计算前后段/早段/中段功率摘要，不进入 `evidence` 原始明细。

输出规则：

- 非骑行活动：`pacing_signal.status = "unavailable"`，原因包含 `not_cycling_activity`。
- 无功率或功率不可用：`status = "unavailable"`，`level = "unknown"`，原因包含 `power_data_unavailable:*`。
- 功率样本不足：`status = "unavailable"`，原因包含 `insufficient_power_points`，不得输出 pacing 结论。
- VI 或功率 CV 明显高：`level = "variable"`。
- 前段明显过冲且后段回落：`level = "front_loaded"`。
- 后段明显回落但前段不过冲：`level = "late_fade"`。
- 输出平稳且前后段接近：`level = "steady"`。

边界：

- 本任务不计算 FTP / IF / TSS / W/kg / Pw:Hr / CTL / ATL / TSB / CP/W′。
- 不新增 DB schema，不修改 `llm_backend.py`，不解冻 AI 入口。
- 不修改 `track.html` 或 ECharts。
- 不向前端或 AI 暴露 `points / records / raw_records / curves / shadow_diff / diff`。
- 不把跑步配速策略包装成骑行功率 pacing。

### P10 踏频节奏 / 踩踏组织解释信号补齐

当前状态：已完成。

本任务严格继承修复后的骑行解释信号清单，只处理 `cycling_explanation_signals.cadence_signal`，不推进新的 UI、AI、DB 或 FIT 字段解析能力。

目标：

- 让“踏频节奏”用户可见卡片不再呈现半成品口吻。
- 只解释“这次踩踏节奏是否连续、是否波动大、后段是否掉踏频、是否明显低踏频偏力量输出”。
- 专业指标只作为后端 `evidence`，用户主文案保持教练复盘口吻。

后端事实来源：

- `summary.avg_cadence / cadence_available / cadence_points_count / cadence_data_quality`。
- 后端同轴 `curves.cadence`，可结合 `curves.speed / curves.power / curves.time` 过滤停顿、滑行和时间断裂。
- `metrics.pedaling_stability` 只能作为 `pedaling_stability_metric_reference` 参考 evidence，不作为前端或 AI 重新推导来源。

输出规则：

- 非骑行活动：`cadence_signal.status = "unavailable"`，原因包含 `not_cycling_activity`。
- 无踏频或踏频质量不可用：`status = "unavailable"`，原因包含 `cadence_data_unavailable:*`。
- 踏频样本不足、曲线长度不对齐或过滤后有效样本不足：`status = "unavailable"`，原因包含 `insufficient_cadence_points` 或 `curve_length_mismatch`。
- 有足够有效踏频样本时输出 `steady / variable / low_cadence_bias / cadence_drop / interrupted`。
- `evidence` 仅允许输出 `cycling_cadence_rhythm` 摘要字段：`avg_cadence / head_cadence / tail_cadence / cadence_cv / cadence_std / cadence_drop_pct / low_cadence_ratio / zero_cadence_ratio / effective_cadence_points_count / filter_reasons / confidence`。

边界：

- 不新增 DB schema，不修改 `llm_backend.py`，不解冻 AI 入口。
- 不修改 `track.html` 或 ECharts，不新增卡片或图表。
- 不向前端或 AI 暴露 `points / records / raw_records / curves / shadow_diff / diff`。
- 不诊断齿比、扭矩、左右平衡、踩踏平滑度、踏板效率或真实踩踏技术细节。
- 不把跑步步频/配速口径包装成骑行踏频解释。

### P11 关键证据标签产品化

当前状态：已完成。

本任务只收口骑行解释信号的证据展示口径，不新增科学模型、不改变卡片布局、不修改 ECharts、不改 DB 或 AI 生成逻辑。

目标：

- 让用户看到的是“教练复盘依据”，不是 `avg_cadence / decoupling_pct / intensity_ratio` 这类内部字段名。
- 保留后端机器证据字段用于测试和后续算法，但用户可见层只读后端提供的展示字段。
- 负荷相关内容只作为“相对个人阈值 / 本次刺激参考”，不包装成 TrainingPeaks、佳明或高驰式训练负荷体系。

契约增量：

- `cycling_explanation_signals.*.evidence[]` 继续保留 `type` 与算法摘要字段。
- 每条 evidence 由后端补充：
  - `label`
  - `display_value`
  - `unit`
  - `description`
  - `visibility`
  - `source`
- `visibility = "visible"` 的 evidence 可进入关键证据展示。
- `visibility = "hidden"` 的 evidence 只作为机器证据，不进入用户可见关键证据。

前端规则：

- 前端优先展示后端 `label + display_value`。
- 前端不得从 `summary / metrics / curves / DOM / ECharts / points` 生成证据标签或补算关键证据。
- 前端保留旧 evidence 类型映射只作为兼容兜底，不作为新事实来源。

负荷边界：

- `intensity_signal` 可展示 `相对个人阈值`、`本次功率` 等依据。
- `training_load` 相关内容只能作为温和参考，不得输出 `TSS / IF / CTL / ATL / TSB / W/kg / 长期训练负荷模型`。
- 缺 FTP、缺功率或样本不足时，仍按 P8 降级，不显示确定性个人强度结论。

测试固化：

- `tests/test_cycling_explanation_evidence_labels.py` 锁定后端 display 字段、前端只读展示字段、隐藏机器证据、负荷边界和内部字段名隔离。

### P6 AI 复盘输入升级

当前状态：已完成。

本任务严格继承原始任务清单，只升级复盘 AI 输入契约与 prompt 边界，不进入 P5 UI 接入，不解冻或新增 AI 入口。

目标：

- AI 使用后端 `cycling_explanation_signals`，而不是从曲线、DOM、ECharts 或 points 自己猜。
- 输出仍保持“发生了什么 / 可能原因 / 下次建议”的复盘口吻。

输入白名单：

- `activity_id / sport_type / summary / metrics / fatigue_zones / collapse_events / curves_summary / context_tags / environment_context / cycling_explanation_signals / advice / disclaimer`。
- `cycling_explanation_signals` 只能来自 `review_snapshot.get("cycling_explanation_signals")`。
- `curves_summary` 只作为紧凑摘要，不允许 AI 据此补算新的骑行科学信号。

Prompt 约束：

- AI 只能解释后端已有 `intensity_signal / aerobic_drift_signal / power_retention_signal / pacing_signal / cadence_signal`。
- 对 `status=unavailable/partial` 的 signal 必须温和降级。
- 无 FTP 不得编造 FTP、IF、TSS、训练负荷或阈值强度。
- 无功率不得输出功率强度、后程功率保持或 pacing 确定性结论。
- 无心率不得输出有氧漂移结论。
- 不得编造补给、天气、设备、路况等 snapshot 未提供事实。
- 不得把跑步配速/速度耐力口径包装成骑行功率解释。

边界：

- 不修改 `track.html`，不改 ECharts。
- 不新增 DB schema，不写 DB，不写 `localStorage/sessionStorage`。
- 不修改后端 `cycling_explanation_signals` 计算结果。
- 不允许 `points / records / raw_records / track_points / fit_records / gpx_points / shadow_diff / diff` 进入 prompt。
- 不开放或解冻复盘 AI 入口。

仍未实现：

- 如需更强视觉层级，可单独做骑行复盘指标卡视觉重排；当前 P5b 保持 8 卡布局稳定。

### P5 现有复盘 UI 最小接入

当前状态：已完成。

本任务严格继承原始任务清单，只做骑行复盘 UI 最小接入；目标是让已有卡片更像“教练复盘”，不是新增专业指标面板。

完成内容：

- `openFatigueReview(activityId)` 继续以 `get_fatigue_review(activity_id)` 为唯一权威数据源，并把 `data.cycling_explanation_signals` 传给现有指标卡渲染。
- 骑行模式下，现有卡片优先读取后端 signal：
  - `pacing_signal` → 输出节奏卡；
  - `aerobic_drift_signal` → 心率漂移卡；
  - `cadence_signal` → 踏频稳定性卡；
  - `intensity_signal` → 训练负荷卡；
  - `power_retention_signal` → 后程功率保持卡。
- UI 副文案优先使用 `signal.summary`，`signal.evidence` 只作为“依据”辅助展示，`signal.reasons` 用于 partial/unavailable 温和降级。
- 前端 helper 只读取后端 signal 字段，不从 `summary / metrics / curves / DOM / ECharts / points` 构造解释信号。

边界：

- 不新增 UI 大模块，不重构 `track.html` 布局，不改 ECharts 主图。
- 不修改 DB、后端算法、`cycling_explanation_signals` 计算结果或 AI 生成逻辑。
- 不进入 P7 真实样本复核。

测试固化：

- `tests/test_cycling_explanation_signals_contract.py` 将旧的“前端完全不出现字段”升级为“前端只读后端字段，不构造信号”。
- `tests/test_fatigue_review_quality_gate.py` 固化 P5 UI 只消费 `data.cycling_explanation_signals`，并检查 helper 不读曲线、DOM、ECharts 或 metrics 来推导 signal。

### P0-visibility 复盘解释可见性闸门

当前状态：已完成。

本任务是对骑行解释信号 UI 接入的边界收口，不补算法、不重构现有复盘 UI、不改变 AI 能力。目标是让现有卡片只展示可信复盘解释，不把契约占位、工程状态或开发阶段说明暴露给用户。

可见性规则：

- `available`：可作为卡片主结论，可进入主标题和评价文案。
- `partial`：只能作为参考线索或副文案，不得抢主标题，不得形成确定判断。
- `unavailable`：只能显示温和空态或不可判断，不得输出确定性结论。
- `pending_algorithm / *_not_enabled / backend / 后端证据 / 本阶段 / 专项算法尚未完成 / 占位` 等工程或占位语义不得进入用户可见文案。
- 前端只能做可见性闸门和产品化中文映射，不得从 `summary / metrics / curves / DOM / ECharts / points` 构造新的解释信号。

保持不变：

- 现有复盘 Tab 布局、卡片数量、分组、主图和右侧摘要结构不变。
- 后端 `cycling_explanation_signals` 契约不变。
- `metrics.power_variability / pedaling_stability / efficiency / durability` 计算结果不变。
- AI compact snapshot 仍只透传后端字段，不开放 AI 生成新事实。

测试固化：

- `tests/test_fatigue_review_quality_gate.py` 锁定可见性闸门 helper、`available` 才能拥有主标题、`partial` 只能参考。
- `tests/test_cycling_explanation_signals_contract.py` 和 `tests/test_cycling_explanation_signals_acceptance.py` 锁定前端只读后端 signal、禁止半成品文案和内部字段名进入 UI helper。

### P1-card-semantics 现有骑行复盘卡片语义回正

当前状态：已完成。

本任务只修正现有骑行复盘卡片的评价语义，不改变页面布局、卡片数量、分组、主图、后端算法、DB 或 AI 行为。目标是避免 `partial/unavailable` 的解释信号被前端 fallback 包装成确定性教练结论。

主标题来源规则：

- `intensity_signal`：只有 `available` 可拥有主标题；`partial/unavailable` 显示“强度暂不分级”，不得回退到 `training_load` 的“负荷高/低”等确定评价。
- `aerobic_drift_signal`：只有 `available` 可输出“漂移不明显/有轻微漂移/漂移较明显”；`partial/unavailable` 显示“暂不单独判断”，不得回退到旧 `hr_drift` 确定结论。
- `cadence_signal`：P10 后有足够有效踏频样本时可输出 `steady / variable / low_cadence_bias / cadence_drop / interrupted`；非 `available` 时只做温和降级，不从前端或 `metrics.pedaling_stability` 反推出新的踩踏节奏结论。
- `pacing_signal`：`available` 可拥有输出节奏主标题；非 `available` 仍可回退到既有 `metrics.power_variability` 事实卡片。
- `power_retention_signal`：`available` 可拥有后程保持主标题；非 `available` 仍可回退到既有 `metrics.durability` 事实卡片，但缺样本时必须降级。

测试固化：

- `tests/test_fatigue_review_quality_gate.py` 新增 P1 卡片主标题策略门禁，锁定强度/有氧漂移不得从 partial signal 回退成确定判断。

### P7 验收与真实样本复核

当前状态：已完成自动化验收与清单落档；真实样本人工复核需按清单继续执行。

本任务严格继承原始任务清单，只做验收与复核，不新增算法、不重构 UI、不改变 AI 行为。

自动化覆盖：

- 有功率 + 有心率 + 有 FTP：确认 `intensity_signal` 可输出个人化强度分级，但不生成 IF/TSS/Pw:Hr/W/kg 或长期训练负荷结论；`power_retention_signal / pacing_signal` 可在有效样本上给出解释。
- 无 FTP：确认 `intensity_signal.status = unavailable` 且原因包含 `missing_ftp`，不输出阈值/高强度/训练负荷结论。
- 无功率：确认强度、后程功率保持、pacing 均 unavailable，不输出功率确定性结论。
- 无心率：确认 `aerobic_drift_signal.status = unavailable`，不输出有氧漂移或 Pw:Hr 结论。
- 滑行很多：确认后半程 0W 滑行不会被误判为体能下降，样本不足时降级。
- 样本不足：确认 `power_retention_signal / pacing_signal` 均 unavailable。
- 非骑行：确认只返回 unavailable 的骑行解释结构，不展示完整骑行解释口吻。
- evidence 隔离：确认不暴露 `points / records / raw_records / track_points / fit_records / gpx_points / shadow_diff / diff`。
- UI/AI 边界：确认前端只读后端 signal，AI compact snapshot 只透传 `review_snapshot.get("cycling_explanation_signals")`。

文档：

- `docs/cycling_fatigue_review_acceptance_checklist.md` 已更新为 P7 验收清单，包含真实样本记录表、解释信号矩阵、UI/AI 边界和剩余风险。

剩余风险：

- 当前自动化样本是构造样本，不能替代真实骑行样本体感验收。
- 真实有 FTP、功率、心率的骑行样本仍需在用户本地数据中检查 UI 文案是否像教练复盘。
- 真实滑行很多、下坡很多的户外骑行样本仍需人工复核；本阶段不新增滑行/下坡复杂识别算法。
- 有氧漂移已由 P9 补齐后端有效样本算法；阈值仍需结合真实样本和用户体感继续校准。

### P2-real-sample-audit 真实样本解释质量复核

当前状态：已完成后端 snapshot 审计；浏览器视觉人工验收待执行。

本任务使用用户本地真实骑行样本检查 `get_fatigue_review(activity_id)` 返回的 `cycling_explanation_signals` 是否符合“可信教练复盘”语义，不补算法、不重构 UI、不改变 AI 行为。

已审计样本：

- `304`：有功率 + 有心率 + 有 FTP。P8 后 `intensity_signal` 可用；P9 后 `aerobic_drift_signal` 在有效样本足够时可用；`power_retention_signal / pacing_signal` 可用；P10 后 `cadence_signal` 在有效踏频样本足够时可用，样本不足或曲线不对齐时降级。
- `303 / 251 / 297 / 294`：功率质量为 `invalid_values`，强度、后程保持、pacing、有氧漂移均降级，不输出功率确定性结论。
- `298`：无可用功率、无可用踏频，功率相关与踏频解释均降级。

修正内容：

- 后端 signal `summary` 不再出现 `本阶段 / 后端证据 / 尚未启用专用算法 / 后端参考证据 / 占位` 等工程态或半成品文案。
- `intensity_signal.status = available` 时可输出 `recovery / endurance / tempo / threshold / high_intensity` 的个人化强度结论；缺 FTP、缺功率或样本不足时必须降级。
- `aerobic_drift_signal.status = available` 时可输出稳定/轻微漂移/明显漂移；`unavailable` 时只温和说明缺心率、缺功率、样本不足或曲线无法对齐。
- `cadence_signal.status = available` 时可输出稳定、波动较大、低踏频偏力量、后段掉踏频或踩踏中断较多；缺踏频、样本不足或曲线无法对齐时只温和降级，不暴露占位语义。

测试固化：

- `tests/test_cycling_explanation_signals_acceptance.py` 新增产品化文案门禁，只检查用户可见 `summary`，保留 `reasons` 机器码作为契约降级依据。

剩余风险：

- 本阶段完成的是后端 snapshot 与静态前端门禁复核；仍未执行浏览器截图或逐卡片视觉验收。
- 滑行很多、下坡很多的真实户外样本仍需结合用户体感做人工判断；本阶段不新增下坡/滑行复杂识别算法。

### 明确不做

- P0 阶段不实现 `power_variability` 和 `pedaling_stability` 算法；P3 已补齐两项后端事实指标。
- 不替换现有跑步 `cadence_stability`。
- 不改 `track.html` 展示。
- 不改 `llm_backend.py` 输出逻辑。
- 不改 DB schema。

---

## P1 算法链路回正

### 目标

让复盘算法消费真实 FIT / DB canonical 数据，而不是用 `hr_curve/speed_curve` 拼出伪 records。

### 必改文件

- `main.py`
- `metrics_resolver.py`
- `gap_calculator.py` 如需补齐曲线输出
- `tests/test_fatigue_review_resolver_realignment.py`

### 实施任务

- 梳理 DB 中已有曲线字段：`hr_curve`、`speed_curve`、`cadence_curve`、`altitude_curve`、`distance_curve`、`track_json`、`duration`、`calories`。
- 优先从 canonical DB 或 Resolver 已有输出拿真实 `distance / altitude / time / calories / sport_type`。
- 废弃 `_build_resolved_payload_v81()` 中的伪造 altitude、固定 dt、空 session 方案。
- 将 GAP、grade、efficiency、fatigue_zones、bonk_events 的输入统一到真实 records 或等价 canonical curve bundle。
- `_detect_bonk_event()` 必须接收真实 calories，并显式传入 `sport_type` 走运动类型阈值。
- 疲劳带只基于 Resolver 内部真实 `distance_curve + efficiency_curve` 计算。

### 验收标准

- grade 不再因为固定 `altitude=100.0` 退化为全 0。
- bonk 不再因为 session calories 缺失而系统性漏判。
- fatigue_zones 的公里位置与后端返回的 `curves.distance` 同源。
- main.py 不再承担复盘核心算法，只做 API 编排、快照白名单和错误降级。

---

## P2 后端快照回正

### 目标

让 `get_fatigue_review(activity_id)` 成为前端复盘页面唯一数据源。

### 必改文件

- `main.py`
- `docs/js_api_contract.json`
- `tests/test_fatigue_review_e2e_contract.py`
- `tests/test_fatigue_review_envelope.py`

### 实施任务

- `_build_fatigue_review_snapshot(row)` 返回 P0 定义的完整白名单字段。
- `curves` 增加后端权威 `distance` 和必要时的 `time`。
- 后端负责统一曲线长度、降采样策略和空态表达。
- 统一错误返回：参数错误 `1001`，未找到 `1004`，DB/构建失败 `5001` 或 `9001`。
- 空态使用 `_empty_fatigue_review_snapshot()`，并保持字段完整。
- `docs/js_api_contract.json` 更新 `line`、`returns`、`contract`、`description`。

### 验收标准

- 前端不需要任何业务推导即可画图。
- API 响应始终是 `{code,msg,data,traceId}`。
- 降级返回也包含完整 `metrics / curves / fatigue_zones / collapse_events / context_tags / advice / disclaimer`。
- 单测覆盖 `shadow_diff` 隔离和 `curves.distance` 必传逻辑。

---

## P3 前端最小可用回正

### 目标

先让复盘页面用后端权威数据跑通，不追求最终视觉效果。

### 必改文件

- `track.html`
- `tests/test_v9_0_detail_tab_review.py`

### 实施任务

- 删除或停用 `_distanceFromSpeedTime()` 的事实推导职责。
- `openFatigueReview()` 直接读取 `data.curves.distance`。
- `renderProfileAnalysisChart()` 缺少 `distance_curve` 时展示空态，不自行补齐。
- 指标卡只展示 `data.metrics`，不得通过 DOM、points、curves 自算指标。
- 事件列表只展示 `data.collapse_events`。
- 疲劳带只展示 `data.fatigue_zones`。

### 验收标准

- 全文 grep 确认复盘链路不再调用 `_distanceFromSpeedTime()` 生成事实坐标。
- 前端切 Tab、切活动、重新加载均不会复用旧活动复盘数据。
- 曲线为空时页面显示空态，而不是画错误图。
- 图表 X 轴、疲劳带、事件标记使用同一后端距离来源。

---

## P4 按草图升级 UI

### 目标

在数据链路稳定后，根据草图完善复盘页面的信息结构、布局和视觉层次。

### 参考文件

- `docs/design/运动复盘系统_页面设计草图_v1.png`
- `docs/脉图运动复盘系统_开发团队交付手册_v1.md`
- `track.html`

### 实施任务

- 按草图组织顶部总结、核心指标、主图、多维解释、事件列表和建议区。
- 主图突出 Layer 1 疲劳带、Layer 2 事件标记、Layer 3 派生指标曲线。
- 保留“AI 洞察”入口但置灰或隐藏，直到 P6。
- 所有字段显示都从 `get_fatigue_review` 返回值读取。
- UI 文案区分“数据不足”“设备未记录”“算法不适用”“当前运动类型暂不支持”。

### 验收标准

- 页面结构符合草图的信息层级。
- 空态、错误态、加载态完整。
- 前端无新增业务计算。
- 视觉还原不改变数据契约。

---

## P5 测试与文档固化

### 目标

把这次回正变成长期门禁，防止后续继续偏离。

### 当前状态

已完成。新增 `tests/test_fatigue_review_quality_gate.py`，集中固化 P0-P4 的长期门禁。

### 必改文件

- `tests/test_fatigue_review_e2e_contract.py`
- `tests/test_fatigue_review_envelope.py`
- `tests/test_v9_0_detail_tab_review.py`
- `docs/js_api_contract.json`
- `docs/detail_tab_review_manual_test_checklist.md`

### 测试重点

- 后端返回 `curves.distance`，且不含 forbidden 字段。
- 前端不调用 `_distanceFromSpeedTime()` 作为事实字段来源。
- `fatigue_zones` 与 `curves.distance` 同源对齐。
- 空曲线不会触发前端补算。
- `get_fatigue_review` 成功、参数错误、活动不存在、后端降级均返回统一 envelope。
- 复盘功能不写 DB、不写 `ai_snapshots`。

### 已固化门禁

- 前端零推断：禁止 `_distanceFromSpeedTime`、`speed / sum(speed)`、`speed * 1s`、`total_distance_m` 均分距离轴。
- 后端白名单：snapshot 顶层和 `curves` 字段必须严格等于 P0/P2 契约。
- forbidden 隔离：任意层级禁止 `shadow_diff / shadow_diff_json / diff / records / points / raw_records / track_points`。
- 曲线同源：非空可绘图曲线长度必须与 `curves.distance` 一致。
- P4 UI：摘要、核心状态、能力负荷、上下文、事件、建议等结构必须保留。
- AI 边界：前端 AI 调用只传 sentinel + sportType，不传 metrics / curves / points，不拼 prompt。

### 手工验证

- 跑步、越野跑、骑行、徒步各选 1 条真实 FIT。
- 检查距离轴终点是否等于活动总距离。
- 检查有爬升活动的 grade/GAP 是否不再全 0。
- 检查长距离高消耗活动是否能触发或合理不触发 bonk 风险。
- 切换详情 Tab、切换活动、关闭弹窗后复盘状态清空。

---

## P6 AI 洞察最后接入

### 目标

等 P0-P5 跑通后，再恢复复盘 AI 洞察。

### 当前状态

已完成。复盘 AI 洞察通过独立 sentinel 接入，入口先清空普通聊天 session 并刷新 session id；AI snapshot 由 `_ai_snapshot` 定位活动，再从 DB row + `_build_fatigue_review_snapshot(row)` 构建 compact snapshot。

### 必改文件

- `main.py`
- `llm_backend.py`
- `track.html`
- `tests/test_fatigue_review_prompts.py`
- `tests/test_e2e_fatigue_review.py`

### 实施任务

- 修复 `FATIGUE_REVIEW_INSIGHT` 分支无参调用问题。
- 新增或改造 `_build_fatigue_review_insight_snapshot()`，只从后端权威快照 / `_ai_snapshot` / DB truth 构建。
- sentinel 入口必须先 `self._chat_messages = []` 并刷新 session。
- compact AI snapshot 只包含 `metrics / fatigue_zones / collapse_events / curves_summary / context_tags / advice / disclaimer`，不包含全量 curves / records / points / shadow_diff。
- 任意缺上下文、DB 无记录、LLM 异常均返回 `empty_fatigue_review_insight(...)` envelope，不抛异常给前端。

---

## P6.1 AI 入口冻结

### 目标

保留 P6 后端 AI 洞察能力和测试，但在复盘 UI 设计定稿前冻结前端入口，避免误触发 LLM。

### 当前状态

已完成。复盘 Tab 中 `fr-ai-generate-btn` 保留但禁用，文案为“AI 洞察待开放”，并移除 `onclick="onFatigueReviewAiInsight()"`。

### 验收标准

- 后端 `__FATIGUE_REVIEW_INSIGHT__` sentinel 仍存在。
- 前端 `onFatigueReviewAiInsight()` 函数仍保留，便于后续开放。
- `fr-ai-generate-btn` 必须 `disabled` 且 `aria-disabled="true"`。
- 按钮不绑定 onclick，不触发 `call_llm`。
- `_clearFatigueReviewInsight()` 和 `_clearFatigueAiInsight()` 会保持按钮冻结。
- 前端 `onFatigueReviewAiInsight()` 只传 sentinel 和控制参数，不传 metrics、points、DOM 推导值。
- LLM 异常、数据缺失、JSON 解析失败统一返回 `empty_fatigue_review_insight(error_msg)`。
- AI 输出只存在前端内存，不写 DB，不进入 canonical，不进入 `ai_snapshots`。

### 验收标准

- AI 洞察不参与任何指标计算。
- AI prompt 不含 `shadow_diff`、全量 records、前端 points。
- happy path、LLM 异常、数据不足、JSON 解析失败都有测试。
- 切 Tab、切活动、重新点击会清空旧 AI 洞察。

---

## P7 复盘分析驾驶舱

### 目标

在 P0-P6.1 的数据、算法、前端零推断、测试门禁和 AI 入口冻结基础上，把复盘 Tab 打磨为草图所表达的“分析驾驶舱”。本阶段只吸收草图的复盘内容结构、信息密度、层级和局部视觉语言，不改现有活动详情 Modal 顶部、活动标题、时间/设备/路线信息和详情 Tab 系统。

### P7 后续任务纠偏提示

从 P7.9 起，后续所有 P7.x / P8 任务必须先执行源头校正，不得把当前 UI 当作完成态。

必须同时对照：

- `docs/脉图运动复盘系统_开发团队交付手册_v1.md`
- `docs/design/运动复盘系统_页面设计草图_v1.png`
- 用户设计稿截图 `/Users/fanglei/Downloads/5486EA08-F07D-48FC-A8BF-D997700D1B66 2.PNG`
- 当前程序截图 `/Users/fanglei/Desktop/截屏2026-06-10 00.14.07.png`

每个后续任务必须回答四个复盘问题：

1. 身体状态如何变化。
2. 为什么失衡。
3. 在哪里开始崩。
4. 什么因素导致崩溃。

每个后续任务必须核对三层核心输出：

1. Layer 1 疲劳带 `fatigue_zones`。
2. Layer 2 事件标记 `collapse_events`。
3. Layer 3 派生指标曲线 `curves / metrics`。

如果当前 UI 与交付手册或设计稿冲突，以交付手册和设计稿为准；当前 UI 只作为已实现状态参考。AI 入口继续冻结，直到设计稿视觉回正、分层主图、分析模块补齐和截图验收完成。

### P7.0 设计边界确认

当前状态：已完成。

设计边界：

- 现有活动详情顶部信息保持现状：活动标题、时间、设备、路线等信息继续由既有详情 Modal 承担。
- 现有顶部 Tab 保持现状：概览 / 复盘等 Tab 系统不改名、不新增草图中的全局导航。
- 项目里的“复盘 Tab”等价于草图里的“分析”页；P7 只实现这个 Tab 内部的分析驾驶舱。
- 草图最右侧的首页、活动、日历等全局功能按钮不进入本阶段范围。
- 草图顶部的分享、导出、全局动作区不进入本阶段范围，除非后续另起任务并补充契约。
- AI 洞察入口继续沿用 P6.1 冻结状态：按钮保留置灰，不绑定 `onFatigueReviewAiInsight()`，不触发 `call_llm`。

数据与架构契约：

- 复盘 Tab 的唯一数据源仍是 `get_fatigue_review(activity_id)`。
- 前端不得新增事实推导；禁止从 speed/time/total_distance_m/points/DOM 计算距离、指标、事件、疲劳带或结论。
- `curves.distance` 仍是图表 X 轴、疲劳带和事件定位的唯一后端权威距离来源。
- `metrics / fatigue_zones / collapse_events / context_tags / advice / disclaimer` 只能从后端 snapshot 白名单读取。
- 字段缺失、数组为空或运动类型不适用时展示空态、弱化态或“待接入”，不得前端补算。
- P7 UI 改造不得写 DB，不得改 canonical 数据，不得让 AI 输出参与指标计算。
- `shadow_diff / shadow_diff_json / diff / records / points / raw_records / track_points` 禁止进入复盘主展示和 AI 输入。

### P7.x 任务拆分

每个 P7.x 任务都必须重复本节数据与架构契约，并提交独立完成报告。

| 阶段 | 任务 | 范围 |
|---|---|---|
| P7.1 | 复盘 Tab 信息架构稿 | 固定页面区块顺序、命名、空态和响应式骨架，不改数据逻辑。 |
| P7.2 | 顶部分析摘要带 | 优化复盘 Tab 内部摘要、数据来源和状态说明，不改详情 Modal 顶部。 |
| P7.3 | 核心指标驾驶舱 | 重排核心指标与能力负荷卡片，只读取后端 `metrics`。 |
| P7.4 | 主图容器与图例 | 强化疲劳带、事件、曲线的视觉层级，X 轴只用 `curves.distance`。 |
| P7.5 | 事件与疲劳区间说明 | 重构事件列表、疲劳带解释和空态，只展示后端 `collapse_events / fatigue_zones`。 |
| P7.6 | 建议与上下文侧栏 | 历史阶段：优化 `context_tags / advice / disclaimer` 的呈现和缺失态；P8.1 后 `context_tags` 不再作为独立卡片展示。 |
| P7.7 | 响应式与可读性检查 | 覆盖窄屏、长文本、空数据、异常数据，不新增业务推导。 |
| P7.8 | 视觉回归测试与手工清单 | 固化 P7 UI 结构、冻结 AI 入口、前端零推断和草图边界。 |
| P7.9 | 复盘 UI 设计稿视觉回正与源头纠偏 | 回到交付手册和设计稿，记录遗漏、重排后续阶段，AI 复核顺延。 |
| P7.10 | 分层 ECharts 主图实现 | 将当前叠加图回正为多 grid / 多 yAxis 分层时间轴，共用 `curves.distance`。 |
| P7.11 | 状态阶段与派生指标模块回正 | 补齐状态阶段概览横条和派生指标横向条，只读后端白名单字段。 |
| P7.12 | 主图信息架构纠偏 | 对照设计图回正状态阶段与主图的视觉主次，放大主图主体，降低状态区压制感。 |
| P7.13 | 左侧指标轨道与分层泳道回正 | 对照设计图补齐左侧编号、颜色、指标名和更清晰的泳道阅读结构。 |
| P7.14 | 关键事件图钉与竖向参考线 | 对照设计图补齐事件图钉、气泡和跨泳道竖向参考线，只读 `collapse_events.trigger_km`。 |
| P7.15 | 状态阶段条视觉回正 | 对照设计图把阶段条进一步收敛为连续分段视觉，只读 `fatigue_zones`。 |
| P7.16A | Terrain Load 柱形泳道接入 | 对照设计图补齐 Terrain Load 柱形波浪泳道，只读后端 `curves.terrain_load`。 |
| P7.16B | Terrain Load 柱间距与离散柱视觉回正 | 对照设计图把 Terrain Load 从粘连色带回正为有间距的离散渐变柱。 |
| P7.16 | 右侧关键摘要面板纠偏 | 对照设计图重组关键摘要、事件摘要、生理冲击点和建议，不前端伪造归因。 |
| P7.17 | 底部图例与交互控件回正 | 对照设计图补齐底部图例、开关和轻交互控制感。 |
| P7.18 | 视觉回归与草图对照验收 | 用截图和手工清单验收设计稿差距，不通过则不得进入 AI 入口复核。 |
| P8 | UI 定稿后 AI 入口复核 | 总阶段：先 P8.0 开放前契约复核，再视结论进入 P8.1 最小闭环打开按钮。 |
| P8.0 | 复盘 AI 洞察开放前契约复核 | 只审查不开放按钮，确认 sentinel、compact snapshot、前端调用参数、清空态和不持久化边界。 |
| P8.1 | 复盘上下文标签降噪与 AI 输入保留 | 独立上下文卡片消失；有 `context_tags` 时并入关键摘要“影响因素”；AI compact snapshot 继续保留 `context_tags`。 |

### P7.1 复盘 Tab 信息架构稿

当前状态：已完成。

详见 `docs/p7_fatigue_review_analysis_cockpit_information_architecture.md`。

信息架构固定为：

1. Tab 内部标题与状态行
2. 分析摘要带
3. 核心状态区
4. 能力与负荷区
5. 主图分析区
6. 事件与疲劳区间解释区
7. 上下文与建议区
8. disclaimer / 数据边界说明

P7.1 已明确每个区块的用户可见内容、判断目的、后端字段来源、缺失态、交互边界、字段来源矩阵、空态策略和响应式骨架。后续 P7.2-P7.9 必须以该信息架构为基线，并继续遵守 P7.0 数据与架构契约。

### P7.2 顶部分析摘要带

当前状态：已完成。

已在复盘 Tab 内部 `fr-status-strip` 升级顶部分析摘要带，不改活动详情 Modal 顶部和 Tab 系统。

实现内容：

- 新增 `fr-summary-desc`，展示运动类型、建议接入状态和后端 disclaimer。
- 新增 `fr-curve-status-pill`，展示后端可用曲线组数或曲线不足。
- 新增 `fr-risk-pill`，只依据后端 `metrics.bonk_risk` 展示 Bonk 风险状态。
- 新增 `fr-ai-status-pill`，明确 AI 入口仍为待开放冻结态。
- 保留 `fr-data-source-pill / fr-distance-axis-pill / fr-event-pill`，并统一 loading、error、success 三态。

字段来源：

- `data.curves.distance`：距离轴状态。
- `data.curves.hr/speed/altitude/grade/gap/efficiency`：曲线接入状态，仅统计后端数组存在性。
- `data.metrics.bonk_risk / data.metrics.hr_drift`：摘要与风险提示。
- `data.collapse_events / data.fatigue_zones`：事件与疲劳区间数量。
- `data.sport_type / data.advice / data.disclaimer`：摘要描述。

P7.2 不从 speed/time/total_distance_m/points/DOM 推导事实字段，不新增分享、导出、首页、活动、日历等草图全局动作。

### P7.3 核心指标驾驶舱

当前状态：已完成。

已升级复盘 Tab 内部“核心状态”和“能力与负荷”两组指标卡，不改活动详情 Modal 顶部和 Tab 系统。

实现内容：

- 8 张指标卡均保留原有主值 DOM id。
- 8 张指标卡新增状态标签 DOM id。
- 8 张指标卡均有主值、状态标签和解释/空态文案三层结构。
- `_renderFatigueReviewMetrics(metrics)` 改为 8 卡显式映射，只消费 `metrics`。
- 能力与负荷区不再依赖 efficiency 分支成功后才渲染其他指标。

字段来源：

- `metrics.hr_drift`：心率漂移。
- `metrics.decoupling`：解耦率。
- `metrics.bonk_risk`：Bonk 风险。
- `metrics.events`：崩溃事件摘要。
- `metrics.efficiency`：运动效率。
- `metrics.durability`：耐久指数。
- `metrics.cadence_stability`：步频稳定性。
- `metrics.training_load`：训练负荷。

P7.3 不从 speed/time/total_distance_m/points/DOM/curves 推导指标，不新增草图全局导航、分享或导出动作，AI 入口继续冻结。

### P7.4 主图容器与图例

当前状态：已完成。

已升级复盘 Tab 内部主图分析区，不改活动详情 Modal 顶部和 Tab 系统。

实现内容：

- 主图容器新增 `fr-chart-section`。
- 主图标题新增 `fr-chart-title / fr-chart-subtitle / fr-chart-boundary`。
- 图例新增 `fr-chart-legend`，明确心率、速度、GAP、疲劳带和事件的后端来源。
- 新增 `fr-chart-axis-note`，明确 `distance_curve = data.curves.distance`。
- 保留 `fatigue-review-chart`，作为 ECharts 渲染目标。
- loading/error/success 三态会更新 X 轴说明。

字段来源：

- X 轴：`data.curves.distance`。
- 心率曲线：`data.curves.hr`。
- 速度曲线：`data.curves.speed`。
- GAP 曲线：`data.curves.gap`。
- 疲劳带：`data.fatigue_zones`。
- 事件标记：`data.collapse_events`。

P7.4 不恢复 `_distanceFromSpeedTime()`，不使用 speed/time/total_distance_m 重建距离轴，不新增草图全局导航、分享或导出动作，AI 入口继续冻结。

### P7.5 事件与疲劳区间说明

当前状态：已完成。

已升级复盘 Tab 右侧说明区，不改活动详情 Modal 顶部和 Tab 系统。

实现内容：

- 关键事件面板新增 `fr-events-boundary`，明确来自 `data.collapse_events`，位置使用 `trigger_km`。
- 新增疲劳区间面板 `fr-fatigue-zones-panel`。
- 新增 `fr-fatigue-zones-boundary`，明确来自 `data.fatigue_zones`，区间使用 `start_km / end_km`。
- 新增 `fr-fatigue-zone-list` 和 `_renderFatigueReviewZones(zones)`。
- `_renderFatigueReviewEvents(events)` 优化为空态与字段说明，只消费后端事件数组。

字段来源：

- 关键事件：`data.collapse_events`。
- 事件位置：`collapse_events[].trigger_km`。
- 事件类型：`collapse_events[].type`。
- 事件说明：`collapse_events[].description`。
- 疲劳区间：`data.fatigue_zones`。
- 区间位置：`fatigue_zones[].start_km / end_km`。
- 区间等级：`fatigue_zones[].level`。

P7.5 不从 speed/time/total_distance_m/points/DOM/curves 推导事件或区间，不新增草图全局导航、分享或导出动作，AI 入口继续冻结。

### P7.6 建议与上下文侧栏

当前状态：已完成；P8.1 已对 `context_tags` 展示方式做降噪调整。

历史 P7.6 曾升级复盘 Tab 右侧上下文与建议侧栏；P8.1 后，独立上下文卡片取消，`context_tags` 只在有值时进入右侧“关键摘要”的“影响因素”，无值时不展示空态。

实现内容：

- `context_tags` 仍明确来自 `data.context_tags`，不从活动标题、设备或 DOM 推导。
- 独立 `fr-context-panel` 已移除，避免无价值空态噪音。
- 关键摘要通过 `_renderFatigueReviewContextFactors(contextTags)` 将有值标签转为用户语言的“影响因素”。
- 建议面板新增 `fr-advice-boundary`，明确建议来自 `data.advice`，免责声明来自 `data.disclaimer`。
- 建议面板新增 `fr-advice-status`，展示建议已接入/建议待接入。
- 新增 `_renderFatigueReviewAdvice(advice, disclaimer)`，统一建议和免责声明渲染。
- `openFatigueReview` 调用 `_renderFatigueReviewSideSummary(data)` 和 `_renderFatigueReviewAdvice(data.advice, data.disclaimer)`；上下文影响因素由关键摘要内部消费 `data.context_tags`。

字段来源：

- 影响因素：`data.context_tags`。
- 建议：`data.advice`。
- 免责声明：`data.disclaimer`。

P7.6 不从 metrics/curves/collapse_events/fatigue_zones/points/DOM 生成建议，不新增草图全局导航、分享或导出动作，AI 入口继续冻结。

### P7.7 响应式与可读性检查

当前状态：已完成。

已对复盘 Tab 内部驾驶舱进行响应式和长文本可读性加固，不改活动详情 Modal 顶部和 Tab 系统。

实现内容：

- 指标卡栅格改为 `repeat(4, minmax(0, 1fr))`，避免窄列撑破。
- 中宽 `max-width: 1100px` 下主图标题和图例改为纵向排列，侧栏下移。
- 窄屏 `max-width: 720px` 下指标卡改为 2 列，轴说明可换行。
- 小屏 `max-width: 480px` 下指标卡改为单列，AI 冻结按钮铺满宽度，状态标签可换行。
- 事件卡、疲劳区间卡、侧栏面板、上下文标签和建议块补充长文本换行/截断策略。
- 新增静态门禁，禁止 viewport 字体缩放和负 letter-spacing。

P7.7 不改变任何数据字段来源，不从前端推导事实字段，不新增草图全局导航、分享或导出动作，AI 入口继续冻结。

### P7.8 视觉回归测试与手工清单

当前状态：已完成。

已对 P7 复盘分析驾驶舱建立视觉回归静态门禁和人工验收清单，不改生产 UI、不改活动详情 Modal 顶部和 Tab 系统。

实现内容：

- 新增 P7.8 静态测试，锁定复盘 Tab 内部视觉区块顺序，防止偏离 P7.1 信息架构。
- 新增草图边界回归测试，确认复盘 Tab 不引入首页、活动、日历、分享、导出等非本阶段动作。
- 新增 AI 入口冻结回归测试，确认 `fr-ai-generate-btn` 继续 disabled、`aria-disabled="true"`、无 onclick。
- 在手工测试清单中新增 P7.8 视觉回归章节，覆盖桌面、中宽、窄屏、小屏、长文本、空数据、AI 冻结和前端零推断。

P7.8 不改变字段来源，不新增前端事实推导，不开放 AI 洞察，不写 DB，不修改后端 API、算法链路或 `docs/js_api_contract.json`。

### P7.9 复盘 UI 设计稿视觉回正与源头纠偏

当前状态：已完成。

已回到交付手册、设计草图、用户设计稿截图和当前程序截图进行源头复核。结论是：当前 UI 已覆盖复盘数据骨架和基础展示，但仍偏工程契约面板，不能视为设计稿完成态，也不能进入 AI 入口复核。

当前已覆盖：

- 活动详情顶部和复盘 Tab 容器。
- 后端快照摘要带。
- 8 个基础指标卡。
- 当前叠加式 ECharts 主图。
- 上下文、关键事件、疲劳区间、建议和 disclaimer。
- AI 冻结入口。

当前遗漏或弱化：

- 交付手册要求回答“身体状态如何变化 / 为什么失衡 / 在哪里开始崩 / 什么因素导致崩溃”，当前 UI 尚未形成完整分析叙事。
- Layer 1 疲劳带、Layer 2 事件标记、Layer 3 派生指标曲线尚未按设计稿形成清晰主视觉层级。
- 主图仍是心率、速度、GAP 叠加图，不是设计稿的多维分层时间轴。
- 缺少独立状态阶段概览横条。
- 派生指标仍以较大卡片展示，缺少设计稿中的紧凑横向指标条和小趋势视觉。
- 右侧侧栏尚未回正为关键摘要、崩溃触发因素、基准核心因素、生理冲击点。
- 底部事件时间线、负荷与能量分析、状态解释 / 建议、对比分析尚未完整覆盖。
- 配色、信息密度和深色玻璃运动仪表盘质感与设计稿仍有差距。

P7.9 已将原“UI 定稿后 AI 入口复核”顺延到 P8。P7.10-P7.18 先完成设计稿视觉回正、分层主图、主图信息架构纠偏、左侧指标轨道、事件图钉、右侧摘要、底部图例和截图验收。P7.9 不修改后端、不修改 API、不修改 DB、不开放 AI 洞察。

### P7.10 分层 ECharts 主图实现

当前状态：已完成。

已将复盘主图从心率 / 速度 / GAP 叠加图回正为分层 ECharts 主图。`fatigue-review-chart` 容器使用专用 `_renderFatigueReviewLayeredEcharts(...)` 分支，其他复用 `renderProfileAnalysisChart(...)` 的页面保留原双 Y 轴叠加逻辑。

实现内容：

- 主图标题改为“多维时间轴分析”。
- 主图副标题改为“分层泳道共用后端 curves.distance”。
- `openFatigueReview` 的 chart payload 补充后端已有曲线：
  - `altitude_curve = data.curves.altitude`
  - `efficiency_curve = data.curves.efficiency`
  - `grade_curve = data.curves.grade`
- 分层主图按后端可用曲线动态生成泳道：
  - 心率 `hr_curve`
  - 速度 `speed_curve`
  - 海拔 `altitude_curve`
  - 效率 `efficiency_curve`
  - GAP `gap_curve`
  - 坡度 `grade_curve`
- 每个泳道使用独立 `grid / xAxis / yAxis`，通过 `axisPointer.link` 共享距离轴联动。
- 疲劳带 `fatigue_zones` 作为 `markArea` 背景区间进入每个泳道。
- 事件 `collapse_events` 作为 `markLine` 竖向参考线按 `trigger_km` 跨泳道对齐。
- 缺 `curves.distance` 时继续展示空态，不补算距离轴。

字段来源：

- X 轴：`data.curves.distance`。
- 心率：`data.curves.hr`。
- 速度：`data.curves.speed`。
- 海拔：`data.curves.altitude`。
- 效率：`data.curves.efficiency`。
- GAP：`data.curves.gap`。
- 坡度：`data.curves.grade`。
- 疲劳带：`data.fatigue_zones`。
- 事件标记：`data.collapse_events`。

P7.10 不从 speed/time/total_distance_m/points/DOM 推导任何事实字段，不新增草图全局导航、分享或导出动作，AI 入口继续冻结。

### P7.11 状态阶段与派生指标模块回正

当前状态：已完成。

已新增复盘 Tab 内部“状态阶段概览”模块，并将既有核心状态 / 能力与负荷指标区向设计稿的紧凑横向 Derived Metrics 条收敛。P7.11 不修改后端、不修改 API、不修改 DB，不开放 AI 洞察。

实现内容：

- 新增 `fr-stage-overview-section`，位于派生指标区之后、分层主图之前。
- 新增 `fr-stage-boundary`，明确状态阶段只来自 `data.fatigue_zones`。
- 新增 `fr-stage-track`，作为横向彩色阶段条容器。
- 新增 `_renderFatigueReviewStageOverview(zones)`。
- `openFatigueReview` 调用 `_renderFatigueReviewStageOverview(data.fatigue_zones || [])`。
- loading / error 态会清空状态阶段，避免旧活动残留。
- 派生指标区增加 `fr-derived-metrics-strip` 类名，并压缩指标卡高度、间距和字号，向设计稿横向指标条收敛。
- 保留 8 个既有指标主值 DOM id，避免破坏渲染目标和测试门禁。

字段来源：

- 状态阶段：`data.fatigue_zones`。
- 阶段位置：`fatigue_zones[].start_km / end_km`。
- 阶段等级：`fatigue_zones[].level`。
- 阶段说明：`fatigue_zones[].reason / description`。
- 派生指标：继续只消费 `data.metrics`。

P7.11 不从 curves/speed/time/total_distance_m/points/DOM 推导状态阶段，不前端生成 HR Drift / Decoupling / Terrain Load 曲线。设计稿中后端尚未提供的曲线或指标只作为后续待接入事项。

### P7.12 主图信息架构纠偏

当前状态：已完成。

设计图关联约束：P7.12 开始前已回看 `/Users/fanglei/Downloads/5486EA08-F07D-48FC-A8BF-D997700D1B66 2.PNG`。本阶段对应设计图中的“状态阶段概览 / 多维时间轴分析 / 右侧关键摘要”组合区，只纠正主图与状态区的上下关系、主图高度、容器比例和右侧辅助栏权重，不实现 P7.13 左侧指标轨道、不实现 P7.14 事件图钉细节、不重构 P7.16 右侧深层摘要。

实现内容：

- 主图容器 `fr-chart-section` 从普通卡片提升为复盘主体视觉焦点，`min-height` 提升到 640px。
- `fatigue-review-chart` 画布最小高度提升，避免 ECharts 被压在中下部。
- 分层 ECharts 内部网格从 `topStart = 28 / bottomPad = 32` 回正为 `topStart = 5 / bottomPad = 8`，让各泳道获得主要垂直空间。
- 状态阶段模块已移入 `fr-chart-section`，位于“多维时间轴分析”标题之后、画布之前，通过横向轻量摘要条降低压制感。
- 右侧栏宽度从 300px 收敛到 260px，明确作为主图辅助解释区。

字段来源保持不变：

- 主图曲线：`data.curves`。
- 距离轴：`data.curves.distance`。
- 状态阶段：`data.fatigue_zones`。
- 事件参考：`data.collapse_events`。

P7.12 不改后端、不改 API、不改 DB、不开放 AI 洞察，不从 DOM、曲线走势或截图视觉生成新的业务事实。

### 验收标准

- 复盘 Tab 明确对应草图“分析”页，且不影响现有活动详情顶部和 Tab 结构。
- 草图全局导航、首页/活动/日历等按钮、分享导出区未被实现到本阶段。
- AI 入口仍冻结，点击无响应，不触发 Network / pywebview `call_llm`。
- 前端无新增事实推导，图表、指标、事件和疲劳带均消费后端白名单字段。
- 所有 P7.x 子任务都有契约约束和完成报告。
- P7.1 信息架构已覆盖字段来源矩阵、空态策略和桌面/中等宽度/窄屏响应式骨架。
- P7.2 摘要带在 loading/error/success 三态下均展示后端数据状态、风险状态、事件/疲劳区间状态和 AI 冻结状态。
- P7.3 8 张指标卡均保留主值 id，并具备状态标签、解释文案和空态策略。
- P7.4 主图容器明确 `curves.distance`、`data.curves`、`fatigue_zones`、`collapse_events` 的边界，缺距离轴时展示空态。
- P7.5 关键事件和疲劳区间说明只消费后端数组，空数组时展示空态，不补算。
- P7.6 上下文、建议和免责声明只消费 `context_tags / advice / disclaimer`，空 advice 时展示空态，不生成建议。
- P7.7 桌面、中宽、窄屏和小屏均有响应式守卫，长文本不撑破容器，不使用 viewport 字体或负 letter-spacing。
- P7.8 已固化视觉回归静态门禁和手工验收清单，覆盖区块顺序、草图边界、AI 冻结、响应式可读性和前端零推断。
- P7.9 已完成源头纠偏：当前叠加图不得被误判为设计稿分层主图完成态；AI 入口复核已顺延到 P8。
- P7.10 已将复盘主图回正为多 grid / 多 yAxis 分层 ECharts，疲劳带和事件标记与 `curves.distance` 对齐。
- P7.11 已新增状态阶段概览横条，并将派生指标区向设计稿横向指标条收敛，字段来源仍保持后端白名单。
- P7.12 已完成主图信息架构纠偏：主图成为视觉中心，状态阶段区降权，右侧栏回到辅助位。
- P7.13 已完成左侧指标轨道与分层泳道回正：轨道由实际可绘制 lanes 生成，空曲线不生成假轨道。
- P7.14 已完成关键事件图钉与竖向参考线回正：事件以顶部气泡 / 图钉呈现，竖向虚线跨泳道对齐。
- P7.15 已完成状态阶段条视觉回正：阶段条按后端 `fatigue_zones` 区间长度形成连续分段带。
- 后续 P7.16-P7.18 必须继续完成右侧摘要、底部图例和截图验收。

### P7.13 左侧指标轨道与分层泳道回正

当前状态：已完成。

设计图关联约束：P7.13 开始前已回看 `/Users/fanglei/Downloads/5486EA08-F07D-48FC-A8BF-D997700D1B66 2.PNG`。本阶段对应设计图中的“多维时间轴分析”主图区、主图左侧指标列表和每条曲线对应的分层泳道。P7.13 只纠正左侧指标轨道、泳道识别和图例主次，不实现 P7.14 关键事件图钉，不重做 P7.15 状态阶段条，不重构 P7.16 右侧摘要，不开放 AI 洞察。

实现内容：

- 新增 `fr-chart-body`，将主图内部结构调整为左侧轨道 + ECharts 画布。
- 新增 `fr-lane-rail`，作为分层主图左侧指标轨道容器。
- 新增 `_renderFatigueReviewLaneRail(lanes)`，只根据 `_renderFatigueReviewLayeredEcharts(...)` 实际筛选出的可绘制 `lanes` 渲染轨道。
- 每个轨道项包含编号、颜色、指标名、单位，顺序与 ECharts lanes 顺序一致。
- 空 `lanes` 或缺距离轴时调用 `_renderFatigueReviewLaneRail([])`，不残留上一次活动轨道。
- ECharts `yAxis.name` 弱化为空，指标识别主职责交给左侧轨道，避免左侧文字堆叠。
- 顶部图例降低字号、宽度和不透明度，退居辅助说明。
- 720px 以下左侧轨道转为横向滚动条，不挤压图表。

字段来源保持不变：

- 轨道来源：实际可绘制 `lanes`。
- 曲线来源：`data.curves.hr / speed / altitude / efficiency / gap / grade`。
- 距离轴：`data.curves.distance`。

P7.13 不从 DOM、截图、曲线走势、`points` 或 `total_distance_m` 生成业务事实，不改后端、不改 API、不改 DB、不开放 AI 洞察。

### P7.14 关键事件图钉与竖向参考线

当前状态：已完成。

设计图关联约束：P7.14 开始前已回看 `/Users/fanglei/Downloads/5486EA08-F07D-48FC-A8BF-D997700D1B66 2.PNG`。本阶段对应设计图“多维时间轴分析”主图上方的事件气泡 / 图钉，以及从事件点向下贯穿各指标泳道的竖向虚线。P7.14 只纠正关键事件标记层，不重做左侧指标轨道、不重做状态阶段条、不重构右侧摘要、不开放 AI 洞察。

实现内容：

- 将事件层拆成两类数据：`eventReferenceLineData` 用于各泳道竖向参考线，`eventPinLineData` 用于顶部事件气泡 / 图钉。
- 新增后端 `_build_fatigue_review_collapse_events(...)`，将 Bonk 事件和 `fatigue_zones` 关键转折压缩为 `collapse_events`，避免有疲劳带但事件层长期为空。
- 新增 `_frLayeredEventTitle(event)`，事件标题只读取 `event.title / event.label / event.type / event.event_id`。
- 新增 `_frLayeredEventKmLabel(triggerKm)`，事件距离展示只来自 `collapse_events[].trigger_km`。
- 新增 `_frLayeredEventPinMarkLine(insightEvents)`，保留 `symbol: ['none', 'pin']`，并增强气泡样式、标题、公里数。
- `_renderFatigueReviewEvents(events)` 右侧事件卡优先展示 `title / label`，与主图气泡一致。
- 空 `collapse_events` 或非数字 `trigger_km` 不绘制事件层，不从曲线走势补算事件。
- P7.13 左侧轨道保留，顶部事件气泡通过主图上方空间展示，不压住左侧轨道。

字段来源保持不变：

- 事件数组：`data.collapse_events`。
- 事件生成：后端 Bonk 检测或后端 `fatigue_zones` 关键转折压缩。
- 事件位置：`collapse_events[].trigger_km`。
- 事件标题：`title / label / type / event_id`。
- 事件说明：`description`。

P7.14 不从前端 DOM、截图、曲线走势、`curves`、`speed`、`time`、`points` 或 `total_distance_m` 推导事件；后端事件锚点只来自已计算出的 `bonk_events / fatigue_zones` 白名单结果；不写 DB、不开放 AI 洞察。

### P7.15 状态阶段条视觉回正

当前状态：已完成。

设计图关联约束：P7.15 开始前已回看 `/Users/fanglei/Downloads/5486EA08-F07D-48FC-A8BF-D997700D1B66 2.PNG`。本阶段对应设计图中的“状态阶段概览”横向连续分段条。P7.15 只纠正阶段条视觉、分段占比和窄段可读性，不重做 P7.13 左侧指标轨道、不重做 P7.14 事件图钉、不重构 P7.16 右侧摘要、不开放 AI 洞察。

实现内容：

- `fr-stage-track` 调整为更接近设计图的连续阶段带，提高高度、居中文本、使用虚线分隔。
- `_renderFatigueReviewStageOverview(zones)` 先校验 `start_km / end_km`，仅渲染有效后端区间。
- 阶段条按 `end_km - start_km` 计算 `--fr-stage-grow / --fr-stage-basis`，用区间长度表达相对占比。
- 每段展示阶段名、距离范围、占比和后端说明。
- 过窄区间进入 `compact` 样式，隐藏长说明，避免文字挤压主图。
- 空 `fatigue_zones` 或无有效区间时展示空态，不前端补算阶段。

字段来源保持不变：

- 状态阶段：`data.fatigue_zones`。
- 阶段位置：`fatigue_zones[].start_km / end_km`。
- 阶段等级：`fatigue_zones[].level`。
- 阶段说明：`fatigue_zones[].reason / description`。

P7.15 不从 DOM、截图、ECharts、曲线走势、`curves`、`speed`、`time`、`points` 或 `total_distance_m` 推导阶段，不改后端、不改 API、不写 DB、不开放 AI 洞察。

---

### P7.16A Terrain Load 柱形泳道接入

当前状态：已完成。

设计图关联约束：P7.16A 开始前已回看 `/Users/fanglei/Downloads/5486EA08-F07D-48FC-A8BF-D997700D1B66 2.PNG`。本阶段对应设计图中“多维时间轴分析”主图内的 Terrain Load 柱形波浪泳道。P7.16A 只补齐 Terrain Load 后端曲线、图例、左侧指标轨道和柱形泳道，不重做 P7.15 状态阶段条、不重构 P7.16 右侧摘要、不开放 AI 洞察。

实现内容：

- `get_fatigue_review` 的 `curves` 白名单新增 `terrain_load`。
- 后端用 `grade × speed × duration` 构建 Terrain Load 曲线，输入只来自后端 `grade / speed / time` 曲线，并与 `curves.distance` 长度对齐。
- 空态和 `_empty_fatigue_review_snapshot()` 均包含 `curves.terrain_load: []`。
- 前端复盘主图新增 `地形负荷 · curves.terrain_load` 图例。
- `_renderFatigueReviewLayeredEcharts()` 新增 Terrain Load 独立泳道，使用 ECharts `bar` series 呈现柱形波浪视觉。

P7.16A 不从 DOM、截图、ECharts、曲线走势、`points`、活动标题或前端 payload 推导 Terrain Load，不把 `training_load` 误作 Terrain Load，不写 DB，不改 AI prompt，不开放 AI 洞察。

---

### P7.16B Terrain Load 柱间距与离散柱视觉回正

当前状态：已完成。

设计图关联约束：P7.16B 开始前已回看 `/Users/fanglei/Downloads/5486EA08-F07D-48FC-A8BF-D997700D1B66 2.PNG`。本阶段对应设计图中“多维时间轴分析”主图内 Terrain Load 一根根独立柱子并排形成波浪的视觉。P7.16B 只纠正 Terrain Load 柱间距、显示密度和柱体渐变，不重做 P7.16A 后端事实字段，不重构 P7.16 右侧摘要，不开放 AI 洞察。

实现内容：

- 新增 `_frDownsampleTerrainLoadBars(distanceCurve, terrainLoadCurve)`，只用于显示层聚合密集后端样本。
- Terrain Load bar series 不再直接使用密集 `lane.data`，而是使用 `terrainBarData`。
- 显示层聚合改为等距距离桶，动态生成约 96-128 根柱，保留距离覆盖和桶内峰值，避免柱体疏密不均或粘成连续色带。
- Terrain Load 柱体使用 ECharts 纵向渐变：上方深青绿，中段青绿，下方浅青绿，提高不透明度以强化上深下浅。
- 保留 `fatigue_zones` 背景区间与 `collapse_events.trigger_km` 事件参考线。

P7.16B 不从 DOM、截图、ECharts 当前像素、活动标题、设备信息、前端 payload、`points` 或其它曲线走势推导 Terrain Load；显示层聚合不改变后端 `curves.terrain_load` 事实，不写 DB，不改 AI prompt，不开放 AI 洞察。

---

### P7.16 右侧关键摘要面板纠偏

当前状态：已完成。

设计图关联约束：P7.16 开始前已回看 `/Users/fanglei/Downloads/5486EA08-F07D-48FC-A8BF-D997700D1B66 2.PNG`。本阶段对应设计图右侧分析摘要区域。P7.16 只纠正右侧关键摘要、崩溃触发因素、生理冲击点和建议结构，不重做 P7.13 左侧轨道、不重做 P7.14 事件图钉、不重做 P7.15 状态阶段条、不重做 P7.16A/B Terrain Load、不开放 AI 洞察。

实现内容：

- 右侧栏新增 `fr-side-summary-panel`，展示关键摘要。
- 右侧栏新增 `fr-phys-impact-panel`，展示生理冲击点。
- 原 `fr-events-panel` 语义调整为“崩溃触发因素”，仍只读 `collapse_events`。
- 原 `fr-fatigue-zones-panel` 保留为状态区间，仍只读 `fatigue_zones`。
- 新增 `_renderFatigueReviewSideSummary(data)`，输入完整后端 snapshot，但内部只读 `metrics / collapse_events / fatigue_zones / context_tags / advice / disclaimer`。
- loading / error 状态会清空右侧摘要，避免旧活动内容残留。

P7.16 不从 DOM、截图、ECharts、曲线走势、前端 payload、活动标题、设备信息、`points` 推导事实结论；不新增 AI 调用，不解除 `fr-ai-generate-btn` 冻结，不写 DB，不改 AI prompt，不改 `curves` 后端契约。

---

### P7.17 底部图例与交互控件回正

当前状态：已完成。

设计图关联约束：P7.17 开始前已回看 `/Users/fanglei/Downloads/5486EA08-F07D-48FC-A8BF-D997700D1B66 2.PNG`。本阶段对应设计图主图下方 / 底部辅助区域。P7.17 只纠正底部图例、图层状态、轻交互控件和底部辅助分析模块，不重做主图、不重做右侧摘要、不重做状态阶段、不重做 Terrain Load、不开放 AI 洞察。

实现内容：

- 主图下方新增 `fr-chart-footer`。
- 新增图层 chip，显示 `curves` 各字段存在性和长度、距离轴、疲劳带、事件数量。
- 新增展示层图层开关：曲线、疲劳带、事件、Terrain。
- 新增底部辅助模块：事件时间线、负荷与能量、状态解释、建议状态。
- 新增 `_renderFatigueReviewChartFooter(data)`，只读 `metrics / collapse_events / fatigue_zones / context_tags / advice / disclaimer / curves` 的存在性与长度。
- 新增 `_applyFatigueReviewLayerVisibility(chartPayload)` 和 `onFatigueReviewLayerToggle(inputEl)`，只影响当前前端 ECharts 视图。
- loading / error 状态清空 footer 和最近 chart payload，避免旧活动残留。

P7.17 不从 DOM、截图、ECharts 当前像素、曲线走势、前端 payload、活动标题、设备信息或 `points` 推导事实结论；`curves` 只用于字段存在性和长度状态，不根据曲线值生成结论；图层开关不写 DB、不写 localStorage、不调用 AI、不改后端契约。

---

## 推荐执行顺序

```text
P0 数据契约
  ↓
P1 算法 / Resolver 输出
  ↓
P2 后端 get_fatigue_review 快照
  ↓
P3 前端最小展示
  ↓
P4 草图视觉还原
  ↓
P5 测试 / 契约文档
  ↓
P6 AI 洞察
  ↓
P6.1 UI 定稿前冻结 AI 入口
  ↓
P7 复盘分析驾驶舱
```

---

## 第一批建议动手项（已完成）

1. 在后端快照中补齐权威 `curves.distance`。
2. 删除前端 `_distanceFromSpeedTime()` 的事实推导调用。
3. 改造 `_build_resolved_payload_v81()`，不再伪造 altitude / session / dt。
4. 让 fatigue_zones、collapse_events、curves 使用同一 Resolver 输出来源。
5. 更新 `docs/js_api_contract.json` 与契约测试。
6. 在复盘跑通后，处理 `__FATIGUE_REVIEW_INSIGHT__`，并于 P6.1 冻结前端入口。

## P8.0 复盘 AI 洞察开放前契约复核

当前状态：已完成。

P8.0 是 P7.19 冻结后的开放前审查，不解除 `fr-ai-generate-btn` 冻结，不绑定 onclick，不新增 LLM 调用路径。

审查结论：

- `__FATIGUE_REVIEW_INSIGHT__` 保持复盘 AI 洞察唯一 sentinel。
- 前端预备调用链只允许 `call_llm('__FATIGUE_REVIEW_INSIGHT__', sportType)`。
- 后端 AI 输入只来自 `_build_fatigue_review_insight_snapshot(activity_id, sport_type)` compact snapshot。
- compact snapshot 只包含 `activity_id / sport_type / metrics / fatigue_zones / collapse_events / curves_summary / context_tags / environment_context / cycling_explanation_signals / advice / disclaimer`。
- compact snapshot 任意层级禁止 `points / records / raw_records / track_points / fit_records / gpx_points / shadow_diff / shadow_diff_json / diff`。
- 复盘 AI 输出只进入 `fatigue_review_insight` 展示结构，不写 DB，不改 `metrics / curves / fatigue_zones / collapse_events`。
- 复盘 AI 结果只保留在前端内存，不写 `localStorage` / `sessionStorage`；旧 5 分钟 sessionStorage 缓存路径已关闭为 no-op 兼容层。

P8.0 通过后，允许进入 P8.1「复盘 AI 洞察最小闭环打开按钮」。

---

## P3 骑行真实 UI 逐卡片视觉验收与最小文案收口

当前状态：已完成。

本阶段只验收真实 UI 文案和最小前端映射，不新增算法、不改 ECharts、不改卡片布局、不改 DB、不改 AI。

验收与修正：

- 真实有功率骑行样本显示为产品化卡片文案：输出节奏、有氧漂移、踏频、功率效率、个人强度、后程保持均未出现工程占位词。
- 真实无功率骑行样本的指标卡已正确降级为“不适合判断 / 暂不判断强度 / 后程保持不适合判断”。
- 发现复盘概览“全程稳定性”在无功率骑行时仍可能沿用通用/跑步口径显示“整体稳定”。
- 前端新增骑行概览降级覆盖，只读后端 `cycling_explanation_signals` 的 signal 状态；缺少功率依据时显示“暂不判断”，不从 `curves / DOM / ECharts / points` 推导。
- 新增静态门禁，固化骑行概览只能消费后端解释信号做降级。

P3 不计算 FTP、IF、TSS、Pw:Hr，不改变既有骑行专项主图和指标算法，只把真实 UI 中不可信的确定性口吻收回。

## P4 骑行可信解释验收闭环

当前状态：已完成。

本阶段只做真实样本验收闭环和可信解释回归，不新增算法、不改 DB、不改 AI、不重构 `track.html`，也不把专业指标升级成 UI 主角。

完成内容：

- 在 `docs/cycling_fatigue_review_acceptance_checklist.md` 增加 P4 验收矩阵，覆盖有功率 + 有心率 + 有 FTP、无 FTP、无可用功率、无心率、滑行 / 下坡较多、样本不足、非骑行回归。
- 每类样本明确“必须允许的表达”和“禁止输出或展示”，用于后续真实活动人工复核。
- 固化用户可见文案黑名单：`pending_algorithm / *_not_enabled / 后端证据 / 本阶段 / 专项算法尚未完成 / 占位 / 算法未完成` 等工程态和半成品语义不得进入卡片或 summary。
- 新增自动化验收矩阵，集中验证缺 FTP、缺功率、缺心率、滑行多、样本不足、非骑行时必须降级，且不输出强结论。
- 新增清单门禁，防止后续任务把真实样本验收标准删散或弱化。

边界：

- 不实现 FTP、IF、TSS、Pw:Hr、W/kg、CTL/ATL/TSB、CP/W′。
- 不改变 `metrics.power_variability / pedaling_stability / efficiency / durability` 计算结果。
- 不让前端或 AI 从 `summary / metrics / curves / DOM / ECharts / points` 推导解释信号。
- 不改变既有复盘 UI 设计，只把可信解释的验收标准固定下来。

## P5 真实 UI 截图/视觉回归与滑行/下坡样本复核

当前状态：已完成。

本阶段只做真实 UI / 真实样本复核和验收记录，不新增科学算法、不改 DB、不改 AI、不重构页面、不修改 ECharts 主图。

复核样本：

- `304`：有功率 + 有心率 + 有 FTP。确认可展示具体骑行解释，但强度和有氧漂移仍保持谨慎参考，不输出 IF/TSS/Pw:Hr 或训练负荷确定性结论。
- `298`：无可用功率。确认功率强度、后程功率保持、pacing 和有氧漂移均降级，UI 不应显示完整功率复盘口吻。
- `246`：下坡比例高，功率质量 `invalid_values`。确认没有把下坡或滑行误判成体能下降，功率相关解释降级。
- `279`：坡度极端且有可用功率。确认后程回落结论来自有效踩踏 evidence，并且已过滤 `coasting / time_gap`，不是直接把下坡或滑行说成体能下降。
- `293`：无可用功率。确认功率相关解释降级。

文档与门禁：

- `docs/cycling_fatigue_review_acceptance_checklist.md` 新增 P5 真实 UI 截图/视觉验收记录。
- `tests/test_cycling_explanation_signals_acceptance.py` 新增 P5 清单门禁，防止后续删除真实样本视觉复核结论。

剩余风险：

- 本轮复核使用本地 pywebview 真实 UI 记录和后端 snapshot 交叉验证，未做跨浏览器截图回归。
- 真实滑行很多且功率质量可用的样本仍需继续结合用户体感人工复核。

## P6 真实滑行/下坡可用功率样本复核与误判防线

当前状态：已完成。

本阶段专门处理 P5 剩余风险：真实“滑行/下坡明显且功率质量可用”的样本是否会被误判成体能下降。范围仍然是复核和门禁，不新增 FTP/IF/TSS/Pw:Hr 等科学模型，不改 DB，不改 AI，不重构 UI。

真实样本结论：

- `279`：`min_slope_pct=-44.8`，功率质量 `available`。`power_retention_signal=available/clear_drop`，但 evidence 显示已过滤 `coasting / time_gap`，且前后半有效踩踏样本充足；结论可保留，但必须理解为有效踩踏段回落。
- `248`：长距离骑行，`min_slope_pct=-20.3`，功率质量 `available`。过滤 `coasting` 后仍有大量有效踩踏样本，结论为 `held`，未误判下坡或滑行为掉功率。
- `283`：长距离爬升骑行，`total_descent_m=633.2`，功率质量 `available`。过滤 `coasting / time_gap / stopped` 后仍有大量有效踩踏样本，结论为 `held`。
- `252`：长距离骑行，`total_descent_m=1597.2`，功率质量 `available`。`clear_drop` 结论带有效踩踏 evidence，后续真实体感复核时应重点确认。
- `246 / 257 / 262 / 261 / 287`：下坡或负坡明显，但 snapshot 判定功率质量 `invalid_values`，功率强度、后程保持和 pacing 均降级。

测试固化：

- 新增“下坡多但功率质量 invalid 必须 unavailable”。
- 新增“下坡/滑行多且可用功率输出回落时，必须包含过滤 evidence 和有效踩踏样本数”。
- 新增“后半程滑行为主且有效踩踏不足时，后程保持必须 unavailable”。

剩余风险：

- 本轮未发现需要修改生产算法的误判。
- `252 / 279` 这类真实可用功率且 `clear_drop` 的样本，仍建议结合用户体感和路线实际情况做人工复核。

## P7 骑行复盘可信解释最终验收与冻结

当前状态：已完成。

本阶段只做最终验收与冻结，不新增 FTP/IF/TSS/W/kg/Pw:Hr/CTL/ATL/TSB/CP/W′ 等科学模型，不改 DB，不改 AI，不重构 `track.html`，不修改 ECharts 主图。

冻结结论：

- `get_fatigue_review(activity_id)` 仍是复盘页唯一权威数据源。
- 用户可见强结论只允许来自后端 `cycling_explanation_signals` 中 `status=available` 的 signal。
- `partial` 只能作为参考线索，`unavailable` 只能温和降级；缺 FTP、缺功率、缺心率、功率质量无效、样本不足、滑行/下坡多时不得过度断言。
- 前端只做读取、可见性闸门和产品化中文映射，不从 `summary / metrics / curves / DOM / ECharts / points` 构造骑行解释信号。
- AI compact snapshot 只透传 `review_snapshot.get("cycling_explanation_signals")`，prompt 约束 AI 不从曲线、DOM、ECharts、points 或 compact 摘要补算新事实。
- 专业指标只保留为 evidence 或辅助依据，不成为默认 UI 主结论。

最终验收覆盖：

- 有功率 + 有心率 + 有 FTP。
- 无 FTP。
- 无可用功率。
- 无心率。
- 功率质量 `invalid_values`。
- 滑行 / 下坡很多。
- 样本不足。
- 非骑行回归。
- 用户可见文案黑名单。
- UI 与 AI 零推断边界。

剩余风险：

- 已完成本地 pywebview 真实 UI 与后端 snapshot 交叉复核，但未做跨浏览器截图回归。
- `252 / 279` 这类真实可用功率且 `clear_drop` 的样本，仍建议结合路线实际情况与用户体感做人工复核。
- 有氧漂移已按 P9 输出 `stable/mild_drift/significant_drift/unavailable`；仍不输出 `Pw:Hr` 专业缩写或补给/天气等未提供事实。

## P12 真实样本证据展示收口

当前状态：已完成。

本阶段只处理真实样本审计中暴露的用户可见证据问题，不新增算法、不改 DB、不改 AI、不重构 `track.html`，不修改 ECharts 主图。

真实样本审计：

- `304 / 299 / 279 / 252`：功率质量可用且有 FTP，可展示个人强度、功率心率关系、有效踩踏后程、功率节奏与踏频节奏；证据以产品化中文展示，不暴露内部字段名。
- `303 / 251 / 297 / 294 / 246`：功率质量为 `invalid_values` 或不可用，功率强度、后程保持、pacing、有氧漂移必须降级；踏频信号可在有效踏频样本足够时单独输出。
- `298`：无可用功率、无可用踏频，功率相关、踏频相关解释均降级。

修正内容：

- 当 `power_available=false` 或 `power_data_quality != available` 时，`ride_power_summary` 仍保留机器字段，但 `visibility=hidden`，不得作为“关键证据”显示给用户。
- 避免出现“暂不判断个人强度”同时又展示 `平均功率 0W` 或低质量功率摘要的矛盾体验。

测试固化：

- `tests/test_cycling_explanation_evidence_labels.py` 新增 P12 门禁，锁定不可用功率摘要不能成为可见关键证据。

剩余风险：

- 本轮是后端 snapshot 与用户可见 evidence 文案审计；未新增训练模型，也未重新设计卡片布局。
- 真实路线体感仍可能影响对 `252 / 279` 等可用功率 clear_drop 样本的解释强度，发布前建议继续结合用户主观反馈微调文案阈值。

## P13 骑行事件与疲劳带契约回正

当前状态：已完成。

本阶段只固化骑行 `fatigue_zones / collapse_events` 的语义边界，不新增复杂疲劳带算法，不改 DB，不改 AI 生成逻辑，不修改 ECharts 主图结构。

契约边界：

- 骑行 `fatigue_zones` 在当前阶段定义为“压力/状态变化参考区间”，不默认等于体能崩了、输出下降或后程保持变差。
- 骑行 `collapse_events` 必须由后端字段明确区分功率回落、踏频中断、心率-功率关系变化、滑行/停顿/下坡导致的非体能事件、数据不足；普通 `fatigue_zones` 不再自动压缩成骑行强事件。
- 当前无法可靠区分时，必须降级为“参考区间/数据不足”，不得强行输出功率回落、有氧漂移、心率压力或输出崩掉等确定性文案。
- 与 `cycling_explanation_signals` 一致：`available` 才能强结论，`partial` 只能作为参考，`unavailable` 必须温和降级。
- 前端只展示后端 `fatigue_zones / collapse_events` 字段，不从 `curves / DOM / ECharts / points` 构造新的骑行事件或疲劳带语义。

修正内容：

- 后端对骑行 `fatigue_zones` 补充 `semantic=state_change_reference / interpretation=reference_only / confidence=partial` 的参考语义。
- 后端阻止普通骑行 `fatigue_zones` 自动生成“状态压力开始 / 效率下降 / 疲劳加深”等强事件；只有后端显式给出 `event_semantic` 时才生成骑行专项事件。
- 前端右侧区间详情和阶段条的骑行默认文案改为“参考区间 / 状态变化参考”，避免“中后段开始吃力 / 输出压力持续 / 掉功率风险”等无依据强结论。
- `docs/js_api_contract.json` 新增 P13 契约，锁定无功率、无心率、功率质量非 available 时的降级规则。

测试固化：

- 新增 `tests/test_cycling_fatigue_events_contract.py`，覆盖骑行普通 fatigue zone 不生成强事件、显式 `event_semantic` 才生成骑行事件、无功率/无心率/invalid power 不出现确定性事件文案、前端事件/区间只读后端字段。

剩余风险：

- 本阶段没有进入 P14 的疲劳带生成逻辑校准，因此 `fatigue_zones` 的位置与分段算法仍沿用当前 Resolver 输出；本轮只保证解释语义不越界。
- 真实可用功率样本中的 `clear_drop` 仍应继续依赖 `cycling_explanation_signals.power_retention_signal` 的有效踩踏 evidence，而不是由 fatigue zone 直接推断。

## P14 骑行疲劳带生成逻辑校准

当前状态：已完成。

本阶段只校准骑行 `fatigue_zones` 进入 UI 前的后端生成/过滤规则，不重构 Resolver 通用 EI 滑窗，不改 DB，不改 AI，不改 ECharts 主图结构，也不进入 P15 事件文案完整重写。

校准规则：

- 骑行 `fatigue_zones` 在进入 UI 前经过 `_calibrate_cycling_fatigue_zones_for_review(...)`。
- 下坡、滑行、停顿、零功率主导的片段会被过滤，不再默认展示为疲劳或体能下降区间。
- `power_retention_signal.status != available` 时，区间不得表达确定性功率保持下降。
- `aerobic_drift_signal.status != available` 时，区间不得表达确定性有氧漂移或心率压力。
- `cadence_signal.status != available` 时，区间不得表达确定性踏频组织问题。
- 无功率、无心率、无踏频或 `power_data_quality != available` 时，只能保留 `reference_only` 参考区间，并在 `description` 中说明数据不足。
- 即使专项解释信号可用，`fatigue_zones` 仍保持 `semantic=state_change_reference / interpretation=reference_only / confidence=partial`，强结论继续由对应 `cycling_explanation_signals.*` 承担。

测试固化：

- `tests/test_cycling_fatigue_events_contract.py` 新增 P14 门禁：
  - 下坡滑行主导区间会被过滤。
  - `invalid_values` 功率或缺心率时，区间只保留参考语义，不出现功率回落、有氧漂移、心率压力等确定性文案。
  - 专项信号可用时，区间仍保持参考区间语义，并把强解释交给可用 signal。

剩余风险：

- Resolver 原始 `fatigue_zones` 仍由通用 `distance_curve + efficiency_curve` 滑窗产生；本阶段是在复盘快照出 UI 前做骑行校准和降噪，没有重写底层区间发现算法。
- 真实可用功率、复杂坡度与间歇混合样本仍可能需要后续 P15 或真实样本验收继续打磨用户可见事件文案。

## P15 事件文案产品化

当前状态：已完成。

本阶段只产品化骑行 `collapse_events / fatigue_zones` 的用户可见文案，不新增事件算法，不修改 DB、AI 生成逻辑或 ECharts 主图结构。

文案边界：

- 前端只把后端事件字段翻译成用户可读文案，优先识别 `type / semantic / event_semantic / reason_code`，不从 `curves / DOM / ECharts / points` 重新判断事件语义。
- 骑行事件按白名单展示为 `power_drop / cadence_interruption / hr_power_decoupling / non_fitness_event / data_insufficient` 等产品语义。
- `power_drop` 只能表达“有效踩踏输出回落参考”，并提示对照后程功率保持卡片；不得独立宣称后程功率保持下降或输出崩掉。
- `cadence_interruption` 只能表达踩踏节奏连续性被打断，提示结合坡度、滑行或停顿；不得诊断齿比、扭矩、左右平衡或真实踩踏技术。
- `hr_power_decoupling` 只能表达功率和心率关系变化，提示对照心率反应卡片；不得输出 `Pw:Hr` 等训练平台术语。
- `non_fitness_event` 与 `data_insufficient` 必须温和降级为路线/停顿影响或数据不足参考点，不得解释成体能下降。
- 骑行区间说明不直接透出后端 `description / reason` 的强口吻，而是根据后端 reference/data/unavailable/route 类字段转译为教练式参考文案。

修正内容：

- `track.html` 扩展 `FATIGUE_REVIEW_EVENT_COPY`，补齐骑行专项事件类型标题和说明。
- `_fatigueReviewEventKind(...)` 改为先读后端事件语义字段，再做兼容 regex fallback。
- 新增 `_fatigueReviewCyclingZoneSummaryDesc(...)`，将骑行状态区间统一解释为参考区间、数据不足区间或路线/停顿影响参考。
- 骑行长区间标题从“整体偏吃力”收敛为“整体参考区间”。

测试固化：

- `tests/test_cycling_fatigue_events_contract.py` 新增 P15 门禁：
  - 锁定五类骑行专项事件文案。
  - 禁止事件文案出现“撞墙已经发生 / 输出崩掉 / 体能崩掉 / 后程功率保持下降”及训练平台模型术语。
  - 锁定事件类型识别优先使用后端语义字段。
  - 锁定事件和区间渲染 helper 不读取 `curves / DOM / ECharts / points` 推导语义。

剩余风险：

- P15 仍然不改底层区间发现和事件生成算法；真实复杂路线样本中的事件准确性继续依赖 P13/P14 后端字段和后续真实样本验收。
- 当前只做文案产品化映射，没有新增新的 UI 结构或更多事件解释层级。
