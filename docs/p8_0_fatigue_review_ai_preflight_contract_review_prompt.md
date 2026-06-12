# P8.0 复盘 AI 洞察开放前契约复核提示词

> 任务类型：P8.0 开放前契约复核
> 适用范围：复盘 Tab AI 洞察入口、`__FATIGUE_REVIEW_INSIGHT__` 后端链路、前端 AI Modal 状态、契约测试与手工验收清单
> 前置条件：P7.19 已冻结复盘 UI，并确认允许进入 P8 复盘 AI 洞察接入/开放前复核
> 核心目标：在不解除 `fr-ai-generate-btn` 冻结的前提下，审查复盘 AI 洞察是否具备安全开放条件

---

## 零、执行前必须先读

执行本任务前必须阅读并遵守：

- `docs/p7_19_fatigue_review_ui_final_acceptance_freeze_report.md`
- `docs/p6_fatigue_review_ai_insight_completion_report.md`
- `docs/p6_1_fatigue_review_ai_entry_freeze_completion_report.md`
- `docs/fatigue_review_realignment_plan_v1.md`
- `docs/js_api_contract.json`
- `track.html`
- `main.py`
- `llm_backend.py`
- `tests/test_fatigue_review_ai_insight_p6.py`
- `tests/test_fatigue_review_quality_gate.py`
- `tests/test_v9_0_detail_tab_review.py`

P8.0 开始前必须重新确认：

- P7 UI 已冻结，P8.0 不做视觉重构。
- P8.0 只做开放前审查，不打开 AI 按钮。
- `fr-ai-generate-btn` 必须继续 `disabled` 且 `aria-disabled="true"`。
- 前端按钮仍不得绑定 `onclick`。

---

## 一、任务背景

P6 已完成复盘 AI 洞察后端能力：

```text
call_llm("__FATIGUE_REVIEW_INSIGHT__", sport_type)
```

P6.1 到 P7.19 期间，为了先完成复盘 UI 设计稿回正，前端入口保持冻结：

```html
id="fr-ai-generate-btn"
disabled
aria-disabled="true"
AI 洞察待开放
```

P7.19 已确认：

- P7 复盘 UI 可以冻结。
- 允许进入 P8 复盘 AI 洞察接入 / 开放前复核。
- P8 必须继续以 `get_fatigue_review(activity_id)` 后端 snapshot 为事实源。
- P8 不得让 AI 输出参与指标、事件、疲劳区间或曲线计算。
- 是否解除 `fr-ai-generate-btn` 冻结必须单独审查后执行。

因此 P8.0 的目标不是开放入口，而是判断是否具备开放条件，并补齐必要的契约门禁。

---

## 二、P8.0 核心目标

完成复盘 AI 洞察开放前契约复核：

1. 审查 `__FATIGUE_REVIEW_INSIGHT__` 后端链路是否只消费后端 compact snapshot。
2. 审查前端是否只通过 sentinel + `sportType` 触发复盘 AI 洞察。
3. 审查 AI 输入是否禁止携带 DOM、ECharts、截图、活动标题、设备、路线、`points`、`raw_records`、前端曲线 payload。
4. 审查 AI 输出是否只作为解释层展示，不回写 DB，不修改 `metrics / curves / fatigue_zones / collapse_events`。
5. 审查 loading / success / error / empty / clear 状态是否已有可开放基础。
6. 审查切换活动、切换 Tab、关闭详情、关闭 AI Modal、重新点击时是否清空旧 AI 结果。
7. 审查 AI 结果插入后是否可能破坏 P7 冻结 UI 布局。
8. 更新契约测试和手工验收清单，固化“P8.0 只审查，不开放”的结论。
9. 输出 P8.0 完成报告，并明确是否允许进入 P8.1。

---

## 三、本任务允许修改

允许修改：

- `docs/fatigue_review_realignment_plan_v1.md`
- `docs/detail_tab_review_manual_test_checklist.md`
- `docs/js_api_contract.json` 中复盘 AI 洞察契约描述
- `tests/test_fatigue_review_quality_gate.py`
- `tests/test_v9_0_detail_tab_review.py`
- `tests/test_fatigue_review_ai_insight_p6.py`
- 必要时新增 `tests/test_fatigue_review_ai_preflight_p8.py`
- 必要时新增完成报告：
  - `docs/p8_0_fatigue_review_ai_preflight_contract_review_completion_report.md`

只有在发现契约描述与现有实现明显不一致、且不改变开放状态的情况下，才允许小幅修改：

- `track.html` 的注释、状态文案、清空态兜底
- `main.py` 的注释或测试友好兜底
- `llm_backend.py` 的注释或 normalizer 空态测试修正

---

## 四、本任务禁止修改

P8.0 严禁：

- 不解除 `fr-ai-generate-btn` 的 `disabled`。
- 不移除 `aria-disabled="true"`。
- 不给按钮新增 `onclick`。
- 不在 UI 中展示可点击的“生成 AI 洞察”入口。
- 不新增任何实际 LLM 调用路径。
- 不修改 AI prompt 正文，除非只是文档审查结论指出后续 P8.1/P8.2 需要改。
- 不新增 DB 字段。
- 不写 DB。
- 不写 `localStorage` / `sessionStorage` 持久化 AI 事实。
- 不让 AI 输出参与 `metrics / curves / fatigue_zones / collapse_events` 计算。
- 不让前端从 DOM、截图、ECharts 像素、活动标题、设备、路线、`points` 或曲线走势推导 AI 输入事实。
- 不重构 P7 已冻结 UI。

---

## 五、必须审查的后端契约

### 5.1 Sentinel 唯一性

确认：

- `__FATIGUE_REVIEW_INSIGHT__` 是复盘 AI 洞察唯一 sentinel。
- 不复用 `__RADAR_INSIGHT__`、`__REPORT_INSIGHT__`、`__REPORT_ACTIVITY_ADVICE__`。
- 不新增第二个复盘 AI sentinel。

### 5.2 后端输入源

确认 `Api.call_llm("__FATIGUE_REVIEW_INSIGHT__", sport_type)`：

- 不消费前端传入的曲线 payload。
- 不消费前端 DOM 文本。
- 不消费 ECharts 当前状态。
- 不消费活动标题、设备、路线作为事实归因。
- 只通过后端活动 ID 回查并构建复盘 AI compact snapshot。
- compact snapshot 只能来自 `get_fatigue_review(activity_id)` 同源后端事实。

### 5.3 Compact Snapshot 白名单

复核 AI compact snapshot 只允许包含：

- `activity_id`
- `sport_type`
- `metrics`
- `fatigue_zones`
- `collapse_events`
- `curves_summary`
- `context_tags`
- `advice`
- `disclaimer`

禁止出现：

- `points`
- `records`
- `raw_records`
- `track_points`
- `shadow_diff`
- `shadow_diff_json`
- `diff`
- `fit_records`
- `gpx_points`
- 前端 DOM / ECharts / screenshot 派生字段

### 5.4 AI 输出边界

确认 AI 输出：

- 只进入 `fatigue_review_insight` 展示结构。
- 不写入 canonical DB。
- 不更新活动记录。
- 不修改后端 metrics。
- 不生成新的 `fatigue_zones`。
- 不生成新的 `collapse_events`。
- 不改 `curves`。
- 错误时使用统一 empty / error insight 结构，不抛出破坏 UI 的异常。

---

## 六、必须审查的前端契约

### 6.1 入口冻结

P8.0 完成后仍必须满足：

```html
fr-ai-generate-btn disabled
aria-disabled="true"
无 onclick
文案仍表达待开放
```

### 6.2 调用链预备状态

可以审查但不得启用：

```js
onFatigueReviewAiInsight()
window.pywebview.api.call_llm('__FATIGUE_REVIEW_INSIGHT__', sportType)
```

确认该调用链一旦 P8.1 打开，只传：

- sentinel
- `sportType`

不得传：

- `activityData`
- `curves`
- `metrics`
- `fatigue_zones`
- `collapse_events`
- `points`
- DOM 文本
- 图表当前 option

### 6.3 AI Modal 状态

审查已有 AI Modal 是否具备以下状态：

- 初始 empty
- loading
- success
- error
- close / clear
- reopen after clear

如缺失，只允许补契约测试或报告记录为 P8.1 前置项；不要在 P8.0 打开入口。

### 6.4 阅后即焚 / 清空态

审查以下动作是否清空复盘 AI 洞察状态：

- 关闭 AI Modal。
- 关闭活动详情。
- 切换活动。
- 切换详情 Tab。
- 重新点击生成。
- 新活动数据加载。
- sport type 变化。

### 6.5 P7 UI 冻结保护

审查 AI 结果区域是否会影响：

- 分层主图高度与自适应 resize。
- 左侧泳道标题。
- 图层控制。
- 右侧关键摘要。
- 状态阶段概览。
- 移动端宽度。
- 长文本换行。

P8.0 不修视觉问题，只记录 must-fix / deferrable；若存在 must-fix，不得进入 P8.1。

---

## 七、测试要求

至少运行：

```bash
python3 -m pytest tests/test_fatigue_review_ai_insight_p6.py
python3 -m pytest tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py
python3 -m pytest tests/test_fatigue_review_snapshot_realignment.py tests/test_fatigue_review_contract_realignment.py tests/test_fatigue_review_e2e_contract.py
```

如新增 P8.0 测试，则一并运行：

```bash
python3 -m pytest tests/test_fatigue_review_ai_preflight_p8.py
```

测试至少覆盖：

- `fr-ai-generate-btn` 仍冻结。
- `__FATIGUE_REVIEW_INSIGHT__` sentinel 保留且唯一。
- 前端复盘 AI 调用链只允许 sentinel + `sportType`。
- 后端 compact snapshot 不含 forbidden 字段。
- AI 输出不写 DB、不改 metrics / curves / fatigue_zones / collapse_events。
- 错误态返回 empty / error insight，而不是异常破坏 UI。
- P7 图层、泳道、图例、ResizeObserver、疲劳区间合并门禁不回退。

---

## 八、完成报告要求

新增：

```text
docs/p8_0_fatigue_review_ai_preflight_contract_review_completion_report.md
```

完成报告必须包含：

1. 审查结论：允许进入 P8.1 / 不允许进入 P8.1。
2. 后端 sentinel 审查结果。
3. compact snapshot 白名单审查结果。
4. forbidden 字段审查结果。
5. 前端入口冻结审查结果。
6. 前端调用链审查结果。
7. AI Modal 状态审查结果。
8. 清空态 / 阅后即焚审查结果。
9. P7 冻结 UI 保护审查结果。
10. 测试结果。
11. must-fix 项。
12. deferrable 项。
13. 下一步建议。

如果允许进入 P8.1，报告必须明确写：

```text
P8.0 复盘 AI 洞察开放前契约复核通过，允许进入 P8.1 最小闭环打开按钮。
```

如果不允许进入 P8.1，报告必须明确写：

```text
P8.0 复盘 AI 洞察开放前契约复核未通过，禁止解除 fr-ai-generate-btn 冻结。
```

---

## 九、下一步建议

P8.0 通过后，进入：

```text
P8.1 复盘 AI 洞察最小闭环打开按钮
```

P8.1 才允许考虑：

- 解除 `fr-ai-generate-btn disabled`。
- 移除 `aria-disabled="true"`。
- 绑定按钮点击入口。
- 真实调用 `call_llm('__FATIGUE_REVIEW_INSIGHT__', sportType)`。

P8.1 仍必须禁止：

- 前端拼 prompt。
- 传入前端事实 payload。
- 写 DB。
- 让 AI 输出参与指标或事件计算。
