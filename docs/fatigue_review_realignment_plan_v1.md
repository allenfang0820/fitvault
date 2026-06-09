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
| P7 复盘分析驾驶舱 | 规划中，P7.8 已完成 | 保持现有活动详情顶部与 Tab 系统，仅在复盘 Tab 内按草图的“分析”页重构信息密度、层级和交互。 |

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
| P7.6 | 建议与上下文侧栏 | 优化 `context_tags / advice / disclaimer` 的呈现和缺失态。 |
| P7.7 | 响应式与可读性检查 | 覆盖窄屏、长文本、空数据、异常数据，不新增业务推导。 |
| P7.8 | 视觉回归测试与手工清单 | 固化 P7 UI 结构、冻结 AI 入口、前端零推断和草图边界。 |
| P7.9 | UI 定稿后 AI 入口复核 | 仅做开放前审查；是否解除 P6.1 冻结需用户单独确认。 |

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

当前状态：已完成。

已升级复盘 Tab 右侧上下文与建议侧栏，不改活动详情 Modal 顶部和 Tab 系统。

实现内容：

- 上下文面板新增 `fr-context-boundary`，明确来自 `data.context_tags`，不从活动标题、设备或 DOM 推导。
- 建议面板新增 `fr-advice-boundary`，明确建议来自 `data.advice`，免责声明来自 `data.disclaimer`。
- 建议面板新增 `fr-advice-status`，展示建议已接入/建议待接入。
- 新增 `_renderFatigueReviewAdvice(advice, disclaimer)`，统一建议和免责声明渲染。
- `openFatigueReview` 改为调用 `_renderFatigueReviewContextTags(data.context_tags || {})` 和 `_renderFatigueReviewAdvice(data.advice, data.disclaimer)`。

字段来源：

- 上下文标签：`data.context_tags`。
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
