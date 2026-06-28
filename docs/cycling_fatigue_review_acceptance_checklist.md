# 骑行复盘验收清单

> 适用范围：`cycling / road_cycling / mountain_biking`
> 数据源：`get_fatigue_review(activity_id)`
> 边界：前端只展示后端 snapshot，不从 `summary / metrics / curves / DOM / ECharts / points` 推导指标或解释信号。
> P7 状态：自动化构造样本已覆盖；真实样本验收按本清单逐项记录，未执行的人工项不得标为通过。

---

## 1. 基本信息

| 项目 | 记录 |
| --- | --- |
| 活动 ID / 文件名 |  |
| sport_type |  |
| 是否有功率 |  |
| 是否有心率 |  |
| 是否有踏频 |  |
| 是否有 FTP |  |
| power_data_quality |  |
| cadence_data_quality |  |
| `cycling_explanation_signals.status` |  |
| 验收人 / 日期 |  |

---

## 2. 有功率 + 有踏频骑行

期望输入：

- `summary.power_data_quality = available`
- `summary.cadence_data_quality = available`
- `metrics.power_variability.vi != null`
- `metrics.pedaling_stability.score != null`
- `metrics.efficiency.basis = power_hr`
- `metrics.efficiency.power_per_hr != null`
- `metrics.durability.basis = power_retention`
- `metrics.durability.power_retention_pct != null`
- `curves.power` 非空
- `curves.cadence` 非空

验收项：

- [ ] 主图默认展示骑行模式。
- [ ] 主图包含功率、心率、海拔、踏频相关图层。
- [ ] 主图不以跑步配速 / GAP / 效率作为核心泳道。
- [ ] 指标卡包含“功率变异”。
- [ ] 指标卡包含“踏频稳定性”。
- [ ] 指标卡包含“功率效率”。
- [ ] 指标卡包含“后程功率保持”。
- [ ] 功率效率卡证据来自 `metrics.efficiency.power_per_hr / avg_power / avg_hr`。
- [ ] 后程功率保持卡证据来自 `metrics.durability.power_retention_pct / head_power / tail_power`。
- [ ] 骑行核心指标区不出现“步频稳定性”。
- [ ] 不出现“后程保持参考”旧文案。
- [ ] 不出现“当前不等同于 power-based durability”旧文案。

---

## 3. P7 解释信号验收矩阵

### 3.1 有功率 + 有心率 + 有 FTP

期望：

- `intensity_signal.status = partial`，只输出个人 FTP 与功率摘要 evidence。
- `power_retention_signal` 可根据有效踩踏段输出 `held / slight_drop / clear_drop / unavailable`。
- `pacing_signal` 可输出 `steady / variable / front_loaded / late_fade / unavailable`。
- `aerobic_drift_signal` 在专门 Pw:Hr 算法未启用时仍保持 `partial` 或 `unavailable`，不输出确定性 Pw:Hr 结论。

验收项：

- [ ] 文案像教练复盘，不把 FTP/IF/TSS/Pw:Hr/W/kg 作为主结论。
- [ ] 不出现“阈值 / 高强度 / 低强度 / 训练负荷确定性结论”。
- [ ] evidence 只作为依据或副文本。
- [ ] `evidence` 不暴露 `points / records / raw_records / curves / shadow_diff / diff`。

### 3.2 无 FTP

期望：

- `intensity_signal.status = unavailable`
- `intensity_signal.reasons` 包含 `missing_ftp`

验收项：

- [ ] 不判断相对强度。
- [ ] 不出现“阈值 / 高强度 / 低强度 / IF / TSS / 训练负荷”结论。
- [ ] UI 温和提示缺少个人阈值或 FTP。

### 3.3 无功率

期望：

- `intensity_signal / power_retention_signal / pacing_signal.status = unavailable`
- `reasons` 包含 `power_data_unavailable:*`

验收项：

- [ ] 不输出功率强度结论。
- [ ] 不输出后程功率保持确定性结论。
- [ ] 不输出 pacing 确定性结论。
- [ ] 主图不补算功率曲线。

### 3.4 无心率

期望：

- `aerobic_drift_signal.status = unavailable`
- `aerobic_drift_signal.reasons` 包含 `missing_hr`

验收项：

- [ ] 不输出有氧漂移确定性结论。
- [ ] 不输出 Pw:Hr 或功率-心率漂移结论。
- [ ] UI 温和提示心率数据不足。

### 3.5 滑行很多 / 下坡很多

期望：

- 后端有效踩踏段过滤滑行、停顿、零功率、异常片段。
- 有效踩踏样本不足时 `power_retention_signal.status = unavailable`。

验收项：

- [ ] 不把滑行、下坡或零功率段误判成体能下降。
- [ ] 不出现“后程功率明显回落 / 持续输出能力下降”等强结论，除非有效踩踏样本足够。
- [ ] evidence 可出现过滤原因摘要，但不暴露原始明细。

### 3.6 样本不足

期望：

- `power_retention_signal / pacing_signal.status = unavailable`
- `reasons` 包含 `insufficient_effective_pedaling_points` 或 `insufficient_power_points`

验收项：

- [ ] UI 明确显示数据不足。
- [ ] 不伪装成完整复盘。
- [ ] 不出现 undefined/null。

---

## 4. 无功率骑行

期望输入：

- `summary.power_data_quality = missing`
- `curves.power = []`
- `metrics.power_variability.confidence = unavailable`
- `metrics.efficiency.power_per_hr = null`
- `metrics.durability.power_retention_pct = null`

验收项：

- [ ] 页面可以正常展示骑行复盘。
- [ ] 功率变异卡不展示 VI。
- [ ] 功率效率卡不展示完整有效结论。
- [ ] 后程功率保持卡不展示完整有效结论。
- [ ] 页面明确提示功率数据不足或功率曲线样本不足。
- [ ] 不出现“功率保持良好”“输出很稳”等完整功率复盘口吻。
- [ ] 主图不补算功率曲线。

---

## 5. 功率样本不足 / 长度不匹配

期望输入：

- `summary.power_data_quality = insufficient_points / length_mismatch / invalid_values`
- `metrics.durability.power_retention_pct = null`
- `metrics.power_variability.vi = null` 或低可信 / 不可用

验收项：

- [ ] 指标卡显示“功率数据不足 / 功率曲线样本不足 / 不适合判断”。
- [ ] 不用速度曲线替代功率耐力。
- [ ] 不把 `durability.score` 单独当成功率保持事实展示。
- [ ] 不从 ECharts series 或 DOM 文案推导指标。

---

## 6. UI 与 AI 边界验收

UI：

- [ ] `available` signal 才能作为骑行卡片主结论。
- [ ] `partial` signal 只能作为参考线索或副文本，不抢主标题。
- [ ] `unavailable` signal 只显示温和空态或不可判断，不输出确定性结论。
- [ ] 个人强度卡：`intensity_signal` 非 `available` 时只显示“强度暂不分级”，不得回退成训练负荷高低评价。
- [ ] 有氧漂移卡：`aerobic_drift_signal` 非 `available` 时只显示“暂不单独判断”，不得回退成心率漂移确定结论。
- [ ] 踏频卡：`cadence_signal` 为 `partial` 时不得覆盖成熟的 `metrics.pedaling_stability` 事实评价。
- [ ] 输出节奏卡：`pacing_signal` 为 `available` 时可作为主标题，非 `available` 时只回退到既有功率波动事实卡片。
- [ ] 后程保持卡：`power_retention_signal` 为 `available` 时可作为主标题，非 `available` 时只回退到既有后程保持事实卡片，样本不足必须降级。
- [ ] 骑行卡片只展示产品化中文文案，不出现 `pending_algorithm`、`*_not_enabled`、`后端证据`、`本阶段`、`专项算法尚未完成`、`占位` 等工程/占位语义。
- [ ] `signal.evidence` 只作为“依据”或副文本，且不得暴露内部字段名。
- [ ] `signal.reasons` 只用于 partial/unavailable 降级，必须经过用户可读文案映射。
- [ ] 前端不从 `summary / metrics / curves / DOM / ECharts / points` 构造解释信号。

AI：

- [ ] compact snapshot 的 `cycling_explanation_signals` 只来自 `review_snapshot.get("cycling_explanation_signals")`。
- [ ] prompt 明确 AI 不得从曲线、DOM、ECharts、points 自行推导。
- [ ] AI 不得编造 FTP、IF、TSS、补给、天气、设备、路况等缺失事实。

---

## 7. 非骑行回归

适用：

- `running`
- `trail_running`
- `treadmill_running`
- `hiking`
- `walking`

验收项：

- [ ] 跑步 / general 指标卡仍显示“运动效率”。
- [ ] 跑步 / general 指标卡仍显示“耐久指数”。
- [ ] 跑步 / general 指标卡仍显示“步频稳定性”。
- [ ] 跑步 / general 不展示“功率效率”。
- [ ] 跑步 / general 不展示“后程功率保持”。
- [ ] 跑步 / general 不把 `power_variability / pedaling_stability` 作为主卡。
- [ ] 跑步主图不被切换成骑行功率主图。
- [ ] 非骑行 activity 不展示完整骑行解释口吻。

---

## 8. P7 自动化验收记录

| 场景 | 自动化覆盖 | 文件 |
| --- | --- | --- |
| 有功率 + 有心率 + 有 FTP | 已覆盖 | `tests/test_cycling_explanation_signals_acceptance.py` |
| 无 FTP | 已覆盖 | `tests/test_cycling_explanation_signals_acceptance.py` |
| 无功率 | 已覆盖 | `tests/test_cycling_explanation_signals_acceptance.py` |
| 无心率 | 已覆盖 | `tests/test_cycling_explanation_signals_acceptance.py` |
| 滑行很多 / 后半程 0W | 已覆盖 | `tests/test_cycling_explanation_signals_acceptance.py` |
| 样本不足 | 已覆盖 | `tests/test_cycling_explanation_signals_acceptance.py` |
| 非骑行回归 | 已覆盖 | `tests/test_cycling_explanation_signals_acceptance.py` |
| UI 只读后端 signal | 已覆盖 | `tests/test_cycling_explanation_signals_acceptance.py` |
| AI compact snapshot 只透传后端 signal | 已覆盖 | `tests/test_cycling_explanation_signals_acceptance.py` |

---

## 9. 验收结论

| 项目 | 结论 |
| --- | --- |
| 有功率骑行 | 通过 / 不通过 / 未测 |
| 有功率 + 有心率 + 有 FTP | 通过 / 不通过 / 未测 |
| 无 FTP 骑行 | 通过 / 不通过 / 未测 |
| 无功率骑行 | 通过 / 不通过 / 未测 |
| 无心率骑行 | 通过 / 不通过 / 未测 |
| 滑行很多 / 下坡很多 | 通过 / 不通过 / 未测 |
| 功率样本不足 | 通过 / 不通过 / 未测 |
| 非骑行回归 | 通过 / 不通过 / 未测 |
| UI 只读后端解释信号 | 通过 / 不通过 / 未测 |
| AI 输入边界 | 通过 / 不通过 / 未测 |
| 是否发现契约违背 |  |
| 是否需要生产代码修复 |  |
| 备注 |  |

## 9.1 P2 真实样本 snapshot 审计记录

| activity_id | 场景 | 审计结论 |
| --- | --- | --- |
| `304` | 有功率 + 有心率 + 有 FTP | 通过。后程保持与 pacing 可输出可用结论；强度只作相对强度参考，有氧漂移不单独判断，踏频只作节奏参考。 |
| `303` | 功率质量 `invalid_values` | 通过。强度、有氧漂移、后程保持、pacing 均降级；踏频只作节奏参考。 |
| `251` | 功率质量 `invalid_values` | 通过。功率相关解释不输出确定性结论。 |
| `298` | 无可用功率、无可用踏频 | 通过。功率相关和踏频解释均降级。 |
| `297` | 低功率质量 `invalid_values` | 通过。没有把低质量功率包装成功率强度或后程保持结论。 |
| `294` | 低功率质量 `invalid_values` | 通过。功率相关解释降级，踏频只作参考。 |

P2 修正记录：

- 后端 signal `summary` 已改为产品化中文，不再出现 `本阶段 / 后端证据 / 尚未启用专用算法 / 后端参考证据 / 占位` 等半成品文案。
- 新增自动化门禁：用户可见 `summary` 不得泄露工程态或占位态表达；`reasons` 仍保留机器码用于契约降级。

## 9.2 P3 真实 UI 逐卡片视觉验收记录

| activity / 场景 | UI 验收结论 |
| --- | --- |
| `2026-06-26` 雅安市骑行，有功率 + 有心率 + FTP | 通过。关键证据卡显示“输出有起伏 / 暂不单独判断 / 踏频波动明显 / 风险较低”，补充证据卡显示“功率效率尚可 / 强度可参考 / 后程功率保持良好”。未出现 `pending_algorithm / 后端证据 / 本阶段 / 占位 / 算法未完成` 等半成品文案。 |
| `2026-06-21` 雅安市骑行，无可用功率 | 指标卡通过。功率节奏、踏频稳定性、功率效率、后程功率保持均显示“不适合判断”，训练负荷显示“暂不判断强度”，未输出功率保持或强度确定性结论。 |
| `2026-06-21` 雅安市骑行，无可用功率 | 发现并修正。复盘概览“全程稳定性”曾沿用通用稳定性口径显示“整体稳定”；现改为只读 `cycling_explanation_signals` 状态，缺功率时显示“暂不判断”。 |

P3 自动化补充：

- `tests/test_fatigue_review_quality_gate.py::test_p3_cycling_overview_downgrades_from_backend_signals_when_power_missing`

## 9.3 P4 真实样本验收闭环记录

P4 目标不是继续补科学模型，而是把“可信解释”变成可重复验收的闭环：

- 有数据时说得具体。
- 缺数据时明确降级。
- 不用跑步口径解释骑行。
- 不把专业指标当 UI 主角。
- 前端和 AI 不自行推导后端没有给出的结论。

| 场景 | 必须允许的表达 | 禁止输出或展示 |
| --- | --- | --- |
| 有功率 + 有心率 + 有 FTP | 可说明本次功率、个人 FTP 参考、有效踩踏后程保持、pacing 线索。 | 不把 FTP/IF/TSS/Pw:Hr/W/kg 作为主结论；不直接给“阈值 / 高强度 / 训练负荷”确定性判断。 |
| 无 FTP | 可提示缺少个人 FTP 或阈值，强度暂不分级。 | 不输出阈值、高强度、低强度、IF、TSS、个人化训练负荷结论。 |
| 无可用功率 | 可提示功率数据不足，改看心率、爬升、环境等辅助线索。 | 不输出功率强度、功率保持、功率波动、pacing 的确定性结论。 |
| 无心率 | 可提示心率数据不足，暂不判断有氧漂移。 | 不输出 Pw:Hr、功率-心率漂移、漂移稳定或显著漂移结论。 |
| 滑行 / 下坡较多 | 可说明有效踩踏样本不足或已过滤滑行停顿后再评估。 | 不把滑行、下坡、零功率直接说成体能下降或后程功率明显回落。 |
| 样本不足 | 可显示“不适合判断 / 数据不足 / 谨慎参考”。 | 不伪装成完整复盘，不出现 undefined/null，不输出强结论。 |
| 非骑行回归 | 可保留跑步/general 原有复盘口径。 | 不展示完整骑行解释，不把跑步步频/配速口径包装成功率解释。 |

用户可见文案黑名单：

- `pending_algorithm`
- `*_not_enabled`
- `后端证据`
- `后端参考证据`
- `本阶段`
- `专项算法尚未完成`
- `尚未启用专用算法`
- `占位`
- `算法未完成`

P4 自动化补充：

- `tests/test_cycling_explanation_signals_acceptance.py::test_p4_trustworthy_acceptance_matrix_keeps_degradation_boundaries`
- `tests/test_cycling_explanation_signals_acceptance.py::test_p4_acceptance_checklist_defines_repeatable_real_sample_closure`

## 9.4 P5 真实 UI 截图/视觉验收记录

P5 执行口径：保持既有 UI 设计，只复核真实样本在后端 snapshot 与当前卡片映射中的用户可见结论；发现问题才做最小文案修正。本轮未做算法新增，未改 ECharts，未改 AI。

| activity / 场景 | 视觉/可信解释验收结论 |
| --- | --- |
| `304` 雅安市骑行，有功率 + 有心率 + 有 FTP | 通过。后端提供 `power_retention_signal=held`、`pacing_signal=variable`、`intensity_signal=partial`、`aerobic_drift_signal=partial`；UI 可展示“输出有起伏 / 强度可参考 / 后程功率保持良好”等产品化文案，但强度和有氧漂移仍保持谨慎参考，不输出 IF/TSS/Pw:Hr 或训练负荷确定性结论。 |
| `298` 雅安市骑行，无可用功率 | 通过。功率质量为 `invalid_values`，强度、后程功率保持、pacing、有氧漂移均降级；UI 应显示“不适合判断 / 暂不判断强度 / 缺少可用功率依据”，不显示“输出较平稳”“功率保持良好”“整体稳定”等完整功率复盘口吻。 |
| `246` 成都市骑行，下坡比例高，功率质量 `invalid_values` | 通过。该样本下坡比例高但功率不可用，后端没有把下坡或滑行误判成体能下降；功率强度、后程保持、pacing 均降级，只允许踏频作为参考线索。 |
| `279` 雅安市骑行，坡度极端且有可用功率 | 通过但需人工解读。该样本有效踩踏证据充足，过滤 `coasting / time_gap` 后仍显示后半程功率回落，因此可以输出“后程功率明显回落”；验收重点是结论来自有效踩踏 evidence，而不是直接把下坡或滑行说成体能下降。 |
| `293` 雅安市骑行，无可用功率 | 通过。功率相关解释降级，非完整功率复盘口吻。 |

P5 自动化补充：

- `tests/test_cycling_explanation_signals_acceptance.py::test_p5_real_ui_visual_audit_records_power_and_downhill_boundaries`

## 9.5 P6 真实滑行/下坡可用功率样本复核

P6 执行口径：专门处理 P5 剩余风险，查找真实“下坡/滑行明显且功率质量可用”的骑行样本，确认后程功率保持结论是否来自有效踩踏段 evidence，而不是把下坡、滑行、停顿或零功率直接归因成体能下降。本轮未新增算法，未改 UI。

筛选方式：

- 从本地 `activities` 只读筛选 `cycling` 样本。
- 优先按 `downhill_pct`、`min_slope_pct`、`total_descent_m`、`avg_power / normalized_power` 选出候选。
- 再以 `get_fatigue_review(activity_id)` 后端 snapshot 的 `summary.power_data_quality` 和 `power_retention_signal.evidence` 判定是否可解释。

| activity_id | 入选原因 | P6 复核结论 |
| --- | --- | --- |
| `279` | `min_slope_pct=-44.8`，功率质量 `available`，坡度极端。 | 通过。`power_retention_signal=available/clear_drop`，但 evidence 显示 `effective_power_points_count=1638`、前后半有效踩踏样本均充足，并过滤 `coasting / time_gap`；后程回落结论来自有效踩踏段，不是直接把下坡/滑行说成体能下降。 |
| `248` | 长距离骑行，`min_slope_pct=-20.3`，功率质量 `available`。 | 通过。`power_retention_signal=available/held`，过滤 `coasting` 后仍有 `5903` 个有效踩踏点，没有把下坡或滑行误判成后程掉功率。 |
| `283` | 长距离爬升骑行，`total_descent_m=633.2`，功率质量 `available`。 | 通过。过滤 `coasting / time_gap / stopped` 后仍有 `9361` 个有效踩踏点，结论为 `held`，未把大量下坡或停顿包装成体能下降。 |
| `252` | 长距离骑行，`total_descent_m=1597.2`，功率质量 `available`。 | 通过但需人工结合体感。`power_retention_signal=available/clear_drop`，evidence 显示 `effective_power_points_count=12550`，过滤 `coasting / time_gap` 后前后半有效踩踏样本充足；可输出回落，但解释必须保留“有效踩踏段”口径。 |
| `246` | `downhill_pct=58.4`，下坡比例极高，但功率质量 `invalid_values`。 | 通过。强度、后程保持和 pacing 均 `unavailable`，没有输出后程功率回落或体能下降结论。 |
| `257 / 262 / 261 / 287` | 下坡或负坡明显，但 snapshot 判定功率质量 `invalid_values`。 | 通过。均降级为缺少可用功率曲线，不输出功率保持或 pacing 确定性结论。 |

P6 自动化补充：

- `tests/test_cycling_explanation_signals_contract.py::test_p6_downhill_invalid_power_stays_unavailable`
- `tests/test_cycling_explanation_signals_contract.py::test_p6_downhill_available_power_requires_filter_evidence_for_drop`
- `tests/test_cycling_explanation_signals_contract.py::test_p6_downhill_coasting_with_insufficient_effective_tail_degrades`

## 10. 剩余风险

- 已完成本地 pywebview 真实 UI 逐卡片文案验收与后端 snapshot 复核；未做跨浏览器截图回归。
- 已覆盖下坡比例高但功率不可用样本、坡度极端且有效踩踏证据充足样本、长距离大量下降且功率质量可用样本；仍建议后续结合用户体感复核 `252 / 279` 这类可输出 clear_drop 的真实活动。
- 当前 P7 不新增算法；有氧漂移仍按 P2 边界保持 partial/unavailable，不输出完整 Pw:Hr 结论。

## 11. P7 最终冻结结论

P7 执行口径：最终验收与冻结，不新增科学算法、不改 UI 布局、不改 ECharts、不改 DB、不解冻 AI 入口。

冻结规则：

- `get_fatigue_review(activity_id)` 仍是骑行复盘唯一权威数据源。
- 前端只能读取 `data.cycling_explanation_signals`，不得从 `summary / metrics / curves / DOM / ECharts / points` 构造解释信号。
- AI compact snapshot 的 `cycling_explanation_signals` 只能来自 `review_snapshot.get("cycling_explanation_signals")`。
- `available` 可以作为用户可见主结论；`partial` 只能作为参考线索；`unavailable` 只能温和降级。
- 无 FTP 不判断个人化强度；无功率不判断功率强度、后程功率保持或 pacing；无心率不判断有氧漂移。
- 功率质量无效、样本不足、滑行/下坡很多时，不把缺失或零功率片段包装成体能下降。
- 专业指标只作为 evidence 或副文本，不作为默认 UI 主角。

最终自动化覆盖：

- 构造样本矩阵已覆盖有功率 + 有心率 + 有 FTP、无 FTP、无可用功率、无心率、滑行很多、样本不足和非骑行回归。
- 静态门禁已覆盖 UI 只读后端 signal、AI 只透传后端 signal、用户可见文案黑名单、raw detail 字段隔离。

发布前人工检查项：

- 用真实骑行样本复看 `252 / 279` 的 `clear_drop` 是否符合路线和体感。
- 做一次跨浏览器或打包环境截图回归，确认文案无溢出、卡片无错位。
- 确认跑步复盘仍保持原有口径，不展示完整骑行解释。
