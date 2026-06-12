# P2 活动建议前端 UI 接入提示词

> 任务类型：P2 前端 UI 与交互接入
> 适用范围：轨迹报告侧栏「活动建议」卡片、用户可选输入、前端状态、AI 调用、阅后即焚清理
> 前置条件：P0 活动建议契约已固化，P1 后端 `__REPORT_ACTIVITY_ADVICE__` 链路已实现
> 核心目标：把旧「风险预警」卡片前端替换为「活动建议」卡片，并接入新后端 sentinel

---

## 零、架构契约核对

执行本任务前必须阅读并遵守：

- `docs/activity_advice_feature_design_v2.md`
- `docs/p1_activity_advice_backend_prompt.md`
- `docs/js_api_contract.json`
- 当前后端实现：`main.py` / `llm_backend.py`
- 当前前端实现：`track.html`

本任务必须遵守以下强制契约：

- 活动建议结果只存在前端内存。
- 不写 DB、不写 `localStorage` / `sessionStorage`、不进入 `ai_snapshots`、不进入 ordinary AI coach 历史消息。
- 前端只能传用户显式 planning context：`user_activity_type` 与 `planned_start_time`。
- 前端不得传 `points[]`、`placemarks[]`、`activityMetrics`、`metrics`、`curves`、DOM 文本、UI fallback 或任何前端推导事实字段。
- `planned_start_time` 默认空，不得从 FIT/GPX 历史 `start_time`、轨迹点时间或活动详情时间自动填充。
- `user_activity_type` 默认空或用户选择值，不得从文件名、标题、设备名推断。
- 天气检查在未填写计划活动时间时必须由后端/LLM 展示信息不足或检查清单，前端不得伪造天气判断。
- 本任务不删除旧风险预警后端代码；旧代码 cleanup 留到 P3。

---

## 一、任务背景

P1 已新增后端链路：

```text
__REPORT_ACTIVITY_ADVICE__ -> { ok, activity_advice }
```

当前前端仍是旧「风险预警」入口：

```text
PY_REPORT_RISK_ASSESSMENT
currentRiskAssessment
riskAssessmentLoading
buildRiskAssessmentHTML
resetRiskAssessmentState
requestRiskAssessment
risk-assessment-*
```

P2 的目标是把前端体验切换为「活动建议」，并接入 P1 后端链路。此阶段不做大规模视觉重构，只做语义、输入和数据边界回正。

---

## 二、任务目标

完成 P2 前端接入：

1. 将轨迹报告卡片标题从「风险预警」改为「活动建议」。
2. 在卡片内增加两个可选输入：活动类型、计划活动时间。
3. 新增前端 sentinel 常量 `PY_REPORT_ACTIVITY_ADVICE = "__REPORT_ACTIVITY_ADVICE__"`。
4. 将前端状态从 risk 命名迁移到 activity advice 命名。
5. 新增 `buildActivityAdviceHTML(activityAdvice)`。
6. 新增 `resetActivityAdviceState()`。
7. 新增 `requestActivityAdvice()`，调用 P1 后端 sentinel。
8. 确保导入新 GPX/FIT、切换轨迹、切主 Tab、离开 report 侧栏、重新点击生成建议时清空旧结果。
9. 更新相关契约测试或静态测试。

---

## 三、本任务改动范围

建议改动文件：

- `track.html`
- `tests/test_activity_advice_frontend.py` 或复用现有前端静态契约测试文件
- `docs/js_api_contract.json` 如发现前端契约描述还需微调

本任务禁止改动：

- 不改 `main.py` 后端业务逻辑。
- 不改 `llm_backend.py` prompt/normalizer。
- 不新增 DB 字段。
- 不接入天气预报 API。
- 不删除旧后端 `REPORT_RISK_ASSESSMENT` 链路。
- 不让前端从 `points[]` 或 `activityMetrics` 拼 prompt。

---

## 四、目标 UI 契约

### 4.1 卡片标题

旧：

```text
风险预警
```

新：

```text
活动建议
```

按钮文案推荐：

```text
生成建议
```

空态文案推荐：

```text
可选填写活动类型和计划时间后，生成补给、天气检查、装备和体力安排建议
```

### 4.2 输入控件

活动建议卡片内新增两个可选输入：

```html
<select id="activity-advice-type">
  <option value="">活动类型（可选）</option>
  <option value="hiking">徒步</option>
  <option value="mountaineering">登山</option>
  <option value="trail_running">越野跑</option>
  <option value="running">跑步</option>
  <option value="cycling">骑行</option>
  <option value="mountain_biking">山地车</option>
  <option value="other">其他</option>
</select>

<input id="activity-advice-planned-time" type="datetime-local" />
```

约束：

- `datetime-local` 默认空。
- 不自动填入 FIT/GPX 历史时间。
- 不从轨迹点首点时间填入。
- 不从活动记录 `start_time` 填入。
- 活动类型可以保留用户选择，但导入/切换新轨迹时建议清空。

---

## 五、前端状态契约

新增或替换为：

```javascript
appState.currentActivityAdvice = null;
appState.activityAdviceLoading = false;
```

旧状态退场：

```text
currentRiskAssessment
riskAssessmentLoading
```

P2 可保留旧函数壳用于过渡，但生产 UI 不应继续调用旧 risk 函数。

---

## 六、请求契约

新增：

```javascript
const PY_REPORT_ACTIVITY_ADVICE = "__REPORT_ACTIVITY_ADVICE__";
```

请求函数目标：

```javascript
async function requestActivityAdvice() {
    if (appState.activityAdviceLoading) return;
    if (!window.pywebview || !window.pywebview.api || !window.pywebview.api.call_llm) {
        showToast('AI 活动建议仅在桌面应用中可用');
        return;
    }
    if (!currentLLMConfig.url) {
        showToast('请先在配置中填写 API 地址');
        return;
    }

    appState.currentActivityAdvice = null;
    appState.activityAdviceLoading = true;

    const planningContext = {
        user_activity_type: getActivityAdviceTypeInput(),
        planned_start_time: getActivityAdvicePlannedTimeInput()
    };

    const res = await withTimeout(
        window.pywebview.api.call_llm(PY_REPORT_ACTIVITY_ADVICE, JSON.stringify(planningContext)),
        60000
    );
}
```

强制禁止：

- 禁止把 `appState.points` 传给后端。
- 禁止把 `appState.activityMetrics` 传给后端。
- 禁止把 DOM 渲染文本传给后端。
- 禁止传历史天气 `appState.currentWeather`。
- 禁止传 FIT/GPX `start_time`。

---

## 七、渲染契约

新增：

```javascript
function buildActivityAdviceHTML(advice) { ... }
```

必须渲染四个维度：

```text
补给建议 -> supply_advice
天气检查 -> weather_check
装备建议 -> equipment_advice
体力安排 -> physical_plan
```

每个维度展示：

- `status`
- `basis`
- `advice`

错误态：

- 如果 `activity_advice.error` 非空，在卡片底部展示错误提示。
- 错误态不应使用“风险预警生成失败”文案。
- fallback 文案应使用“活动建议生成失败”。

---

## 八、阅后即焚契约

新增：

```javascript
function resetActivityAdviceState() {
    appState.currentActivityAdvice = null;
    appState.activityAdviceLoading = false;
    ...
}
```

必须接入以下触发点：

```text
1. applyDataAndRender(...)
   导入新 GPX/FIT 或加载新轨迹时清空

2. switchTab(...)
   切换主 Tab 时清空

3. switchSidebarTab(tab, ...)
   tab !== "report" 时清空

4. requestActivityAdvice()
   重新点击生成建议前立即清空旧结果

5. 所有绕过 applyDataAndRender 的活动轨迹加载成功路径
   如存在,必须补 resetActivityAdviceState()
```

约束：

- 不写 `localStorage`。
- 不写 `sessionStorage`。
- 不在前端缓存跨轨迹建议。

---

## 九、CSS / 命名契约

推荐新 CSS 命名：

```text
activity-advice-section
activity-advice-controls
activity-advice-select
activity-advice-time
activity-advice-container
activity-advice-card
activity-advice-status
activity-advice-basis
activity-advice-text
activity-advice-error
```

旧 CSS 命名退场：

```text
risk-assessment-*
```

P2 允许保留旧 CSS 到 P3 cleanup，但新 UI 不应继续依赖旧风险命名。

---

## 十、测试要求

建议新增：

```text
tests/test_activity_advice_frontend.py
```

静态测试覆盖：

- `track.html` 包含 `PY_REPORT_ACTIVITY_ADVICE`。
- `track.html` 包含 `requestActivityAdvice`。
- `track.html` 包含 `buildActivityAdviceHTML`。
- `track.html` 包含 `resetActivityAdviceState`。
- `requestActivityAdvice` 调用 `call_llm(PY_REPORT_ACTIVITY_ADVICE, JSON.stringify(planningContext))`。
- `planningContext` 只包含 `user_activity_type` 和 `planned_start_time`。
- `requestActivityAdvice` 不传 `appState.points`。
- `requestActivityAdvice` 不传 `appState.activityMetrics`。
- `requestActivityAdvice` 不传 `appState.currentWeather`。
- `datetime-local` 输入没有自动 value 绑定历史时间。
- `switchTab` / `switchSidebarTab` / `applyDataAndRender` 调用 `resetActivityAdviceState`。

可选手工测试：

- 未填活动类型和计划时间，仍可点击生成建议。
- 未填计划时间时，天气检查显示信息不足或检查清单。
- 填写计划时间后，请求 payload 包含该时间。
- 切换轨迹后，旧建议消失。
- 离开 report 侧栏后，旧建议消失。

---

## 十一、验收命令

建议运行：

```bash
python3 -m unittest discover -s tests -p 'test_activity_advice_*.py'
python3 -m unittest discover -s tests -p 'test_response_envelope_contract.py'
python3 -m json.tool docs/js_api_contract.json >/tmp/js_api_contract_check.json
```

静态检查：

```bash
rg "PY_REPORT_ACTIVITY_ADVICE|requestActivityAdvice|buildActivityAdviceHTML|resetActivityAdviceState|activity-advice" track.html tests docs
rg "PY_REPORT_RISK_ASSESSMENT|requestRiskAssessment|buildRiskAssessmentHTML|resetRiskAssessmentState|risk-assessment" track.html
```

预期：

- 新活动建议 UI 链路存在。
- 生产 UI 不再展示「风险预警」作为当前功能。
- 旧风险命名若仍存在,必须标注为 P3 cleanup 遗留，不得被当前 UI 调用。

---

## 十二、验收标准

- [ ] 轨迹报告侧栏显示「活动建议」。
- [ ] 卡片包含活动类型可选下拉。
- [ ] 卡片包含计划活动时间可选输入，默认空。
- [ ] 前端新增 `PY_REPORT_ACTIVITY_ADVICE`。
- [ ] 前端新增 `requestActivityAdvice()`。
- [ ] 前端新增 `buildActivityAdviceHTML()`。
- [ ] 前端新增 `resetActivityAdviceState()`。
- [ ] 请求只传 `JSON.stringify({user_activity_type, planned_start_time})`。
- [ ] 请求不传 `points[]`、`activityMetrics`、`currentWeather`、DOM 文本。
- [ ] 切换轨迹/导入新 GPX/FIT 时清空旧建议。
- [ ] 切主 Tab 和离开 report 侧栏时清空旧建议。
- [ ] 重新点击生成建议前清空旧结果。
- [ ] 新增或更新测试通过。

---

## 十三、完成报告要求

完成本任务后，请输出：

```text
P2 活动建议前端 UI 接入完成报告

1. 本次目标
2. 已更新文件
3. 新增前端能力
4. 契约约束落实情况
5. 测试结果
6. 已知限制
7. 未完成事项
8. 下一步建议
```

---

## 十四、下一步建议

P2 完成后进入：

```text
P3 旧风险预警 Cleanup 与端到端回归
```

P3 建议目标：

- 删除旧 `REPORT_RISK_ASSESSMENT` / `__REPORT_RISK_ASSESSMENT__` 生产链路。
- 删除旧 `risk_assessment` schema / prompt / normalizer / empty fallback。
- 删除旧前端 `RiskAssessment` 状态、函数和 CSS。
- 更新 `docs/js_api_contract.json`，去掉 deprecated 兼容说明或标记为历史。
- 增加静态测试，确保生产代码无旧「风险预警」命名。
- 跑 P1/P2 活动建议测试和关键旧 AI 洞察回归测试。

