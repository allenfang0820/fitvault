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
- compact snapshot 只包含 `activity_id / sport_type / metrics / fatigue_zones / collapse_events / curves_summary / context_tags / advice / disclaimer`。
- compact snapshot 任意层级禁止 `points / records / raw_records / track_points / fit_records / gpx_points / shadow_diff / shadow_diff_json / diff`。
- 复盘 AI 输出只进入 `fatigue_review_insight` 展示结构，不写 DB，不改 `metrics / curves / fatigue_zones / collapse_events`。
- 复盘 AI 结果只保留在前端内存，不写 `localStorage` / `sessionStorage`；旧 5 分钟 sessionStorage 缓存路径已关闭为 no-op 兼容层。

P8.0 通过后，允许进入 P8.1「复盘 AI 洞察最小闭环打开按钮」。
