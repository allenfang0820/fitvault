# P0 活动建议功能契约回正提示词

> 任务类型：P0 产品语义与数据契约回正
> 适用范围：轨迹报告侧栏「风险预警」重构为「活动建议」
> 核心目标：先固化活动建议的名称、输入边界、输出结构、生命周期和旧风险预警退场规则
> 前置背景：`docs/risk_warning_feature_design_v1.md` 已确认旧风险预警链路存在命名、天气上下文、阅后即焚和测试缺口

---

## 零、架构契约核对

执行本任务前必须阅读并遵守：

- `docs/risk_warning_feature_design_v1.md`
- `docs/js_api_contract.json`
- 全局架构契约 `fit-arch-contrac`
- 现有实现位置：`main.py` / `llm_backend.py` / `track.html`

本任务必须遵守以下契约：

- 轨迹事实只来自后端 canonical / Resolver / 当前轨迹上下文，前端不得拼接事实字段进入 AI。
- 活动建议是一次性 AI 解释结果，不写 DB、不进入 `ai_snapshots`、不进入 canonical activity、不进入普通 AI 教练历史消息。
- 活动建议内容只存在前端内存，切换轨迹文件、导入新 GPX/FIT、重新加载轨迹、切主 Tab、离开报告侧栏、重新点击生成时必须丢弃旧结果。
- `计划活动时间` 只能来自用户在活动建议卡片中的显式输入，不得从 FIT/GPX 的 `start_time`、`start_time_utc` 或轨迹点时间自动提取。
- `活动类型` 只能来自用户显式选择或当前 UI 控制参数，不得把文件名、标题、设备名、历史 sport_type 当作不可质疑事实。
- 天气建议不得消费历史天气快照；没有用户填写的计划活动时间时，只能输出天气检查清单或信息不足说明。
- 旧「风险预警」不是本功能的新名字，必须作为待退场链路处理，不能继续用旧 schema 包装新语义。
- 本任务只固化契约和提示后续任务，不实现完整后端/前端功能。

---

## 一、任务背景

当前轨迹报告中已有 `__REPORT_RISK_ASSESSMENT__` 风险预警链路，但它的问题不是简单的 UI 文案：

1. 「风险预警」暗示系统具备确定性安全预警能力，超过当前数据能力。
2. 天气因素与计划活动时间强相关，但旧实现消费的是历史轨迹天气/时间。
3. GPX 文件经常只有路线几何，缺少运动类型和计划时间，需要用户在活动建议卡片补充上下文。
4. 旧 schema 使用 `supply_risk/weather_risk/equipment_risk/physical_risk` 和 `低/中/高`，容易诱导模型做伪确定判断。
5. 旧风险链路代码需要明确退场，避免「风险预警」和「活动建议」两套语义混杂。

因此，本轮改造的第一任务是先建立「活动建议」契约，再进入后端 payload、prompt、前端 UI 和测试实现。

---

## 二、任务目标

完成 P0 活动建议契约回正：

1. 明确功能名称从「风险预警」改为「活动建议」。
2. 固化用户可选输入：`活动类型` 与 `计划活动时间`。
3. 固化活动建议专用 payload 边界，明确允许字段和禁止字段。
4. 固化目标输出 schema，不再使用旧 risk schema。
5. 固化生命周期：不持久化、阅后即焚、切换轨迹即丢弃。
6. 固化旧风险预警退场清单。
7. 更新或新增文档，为 P1 后端实现提供唯一依据。

---

## 三、本任务改动范围

建议改动文件：

- 新建：`docs/activity_advice_feature_design_v2.md`
- 更新：`docs/js_api_contract.json`
- 可选更新：`docs/risk_warning_feature_design_v1.md` 顶部加「已废弃，被活动建议 v2 替代」说明

本任务禁止改动：

- 不改 `main.py` 的 `call_llm` 生产逻辑。
- 不改 `llm_backend.py` 的 prompt / normalizer 生产逻辑。
- 不改 `track.html` UI。
- 不新增 DB 字段。
- 不接入天气预报 API。
- 不做旧风险代码删除，删除动作留到后续 cleanup 实施任务。

---

## 四、目标功能契约

### 4.1 功能名称

生产 UI 和文档中的新名称为：

```text
活动建议
```

推荐四个维度：

```text
补给建议
天气检查
装备建议
体力安排
```

禁止继续把该能力描述为：

```text
风险预警
安全预警
危险判断
天气预报
医学建议
```

### 4.2 用户可选输入契约

活动建议卡片应支持两个可选输入：

```json
{
  "user_activity_type": "hiking|mountaineering|trail_running|running|cycling|mountain_biking|other|",
  "planned_start_time": "用户显式选择的本地日期时间，允许为空"
}
```

约束：

- 两个字段均为可选。
- 默认不自动填充 FIT/GPX 历史时间。
- `planned_start_time` 为空时，天气检查必须降级为信息不足/检查清单。
- 用户输入只作为本次 AI 建议上下文，不写 DB。

### 4.3 活动建议 payload 契约

目标 payload 由两部分组成：

```json
{
  "route_facts": {
    "activity_id": "可选，仅 DB 活动存在",
    "distance_km": 0,
    "distance_display": "",
    "duration_sec": 0,
    "elevation_gain_m": 0,
    "total_descent_m": 0,
    "max_alt_m": 0,
    "min_alt_m": 0,
    "avg_grade_pct": null,
    "max_slope_pct": null,
    "min_slope_pct": null,
    "uphill_pct": null,
    "downhill_pct": null,
    "up_count": 0,
    "down_count": 0,
    "max_single_climb_m": 0,
    "difficulty_score": 0,
    "region": "",
    "start_lat": null,
    "start_lon": null,
    "source": "DB canonical / Resolver truth / current route context"
  },
  "planning_context": {
    "user_activity_type": "",
    "planned_start_time": "",
    "activity_type_source": "user_input|missing",
    "planned_time_source": "user_input|missing"
  }
}
```

明确禁止进入 `route_facts` 或 prompt 的字段：

```text
start_time
start_time_utc
历史 weather_json
_track_weather
points[]
placemarks[]
shadow_diff
shadow_diff_json
diff
DOM 文本
前端自行推断的事实字段
```

说明：

- DB 活动可从 `_ai_snapshot` 或 activity canonical 中提取路线事实，但必须使用活动建议专用白名单过滤。
- 临时 GPX 没有 `activity_id` 时，也必须支持基于当前轨迹上下文生成路线事实；该路线事实不得写 DB。
- 如果当前系统暂时无法为临时 GPX 构建完整后端路线事实，本契约文档必须把它列为 P1/P2 任务，而不能偷偷让前端拼 prompt。

### 4.4 输出 schema 契约

目标输出不再使用 `risk_assessment`，新结构为：

```json
{
  "supply_advice": {
    "status": "提示|注意|重点关注",
    "basis": "依据哪些路线事实或用户输入",
    "advice": "补给建议"
  },
  "weather_check": {
    "status": "信息不足|提示|注意|重点关注",
    "basis": "是否有计划活动时间；没有则明确说明信息不足",
    "advice": "天气检查建议"
  },
  "equipment_advice": {
    "status": "提示|注意|重点关注",
    "basis": "依据海拔、爬升、坡度、路线环境等",
    "advice": "装备建议"
  },
  "physical_plan": {
    "status": "提示|注意|重点关注",
    "basis": "依据距离、爬升、坡度、预计耗时等",
    "advice": "体力安排建议"
  },
  "disclaimer": "以上建议由 AI 基于当前轨迹和用户填写的计划信息生成，仅供出行准备参考。",
  "error": ""
}
```

约束：

- `status` 不得使用旧 `低/中/高风险` 表达。
- 每个维度必须包含 `basis`，用于说明建议依据。
- `weather_check` 在缺少 `planned_start_time` 时必须返回 `status = "信息不足"` 或明确表达同等含义。
- 不能输出医学诊断、安全保证或确定性天气预报。

### 4.5 Sentinel / API 契约

正式新 sentinel：

```python
REPORT_ACTIVITY_ADVICE = "__REPORT_ACTIVITY_ADVICE__"
```

推荐响应：

```json
{
  "ok": true,
  "activity_advice": {}
}
```

旧 sentinel 退场策略：

- `__REPORT_RISK_ASSESSMENT__` 标记为 deprecated。
- 后续 cleanup 任务删除旧常量、旧 prompt builder、旧 normalizer、旧前端状态和旧 CSS。
- 过渡期如必须兼容，应在文档中明确兼容窗口，不得继续新增旧风险链路能力。

### 4.6 生命周期契约

活动建议结果只存在前端内存，必须在以下触发点清空：

```text
1. 导入新 GPX/FIT
2. 切换轨迹文件
3. 从活动列表加载另一条轨迹
4. applyDataAndRender(...)
5. switchTab(...)
6. switchSidebarTab(tab) 且 tab !== "report"
7. requestActivityAdvice() 重新点击生成前
```

禁止：

- 禁止写 DB。
- 禁止写 `localStorage` / `sessionStorage`。
- 禁止进入 `ai_snapshots`。
- 禁止进入普通 AI 教练 `_chat_messages`。

---

## 五、旧风险预警退场清单

后续 cleanup 任务必须清理以下生产代码命名：

```text
REPORT_RISK_ASSESSMENT
__REPORT_RISK_ASSESSMENT__
PY_REPORT_RISK_ASSESSMENT
RISK_ASSESSMENT_OUTPUT_SCHEMA
_risk_snapshot_payload
build_risk_assessment_system_prompt
build_risk_assessment_user_prompt
empty_risk_assessment
normalize_risk_assessment_json
_build_risk_assessment_messages
buildRiskAssessmentHTML
resetRiskAssessmentState
requestRiskAssessment
currentRiskAssessment
riskAssessmentLoading
risk-assessment-*
risk_assessment
风险预警
```

允许保留的位置：

- 历史调研文档。
- 迁移说明。
- 测试中用于断言旧命名已删除的静态检查。

生产代码中不应继续出现旧风险命名。

---

## 六、实施步骤

### Step 1：新建活动建议 v2 设计文档

新建：

```text
docs/activity_advice_feature_design_v2.md
```

文档必须包含：

- 功能定位。
- 数据资产盘点。
- 用户可选输入。
- payload 白名单。
- forbidden 字段。
- 输出 schema。
- 生命周期与阅后即焚触发点。
- 旧风险预警退场清单。
- P1/P2/P3 后续任务拆分。

### Step 2：更新 API 契约文档

更新：

```text
docs/js_api_contract.json
```

要求：

- 新增或更新 `call_llm` 返回说明，包含 `__REPORT_ACTIVITY_ADVICE__`。
- 新增 `activity_advice_contract`。
- 标注 `__REPORT_RISK_ASSESSMENT__` deprecated。
- 把 `ai_insight_pattern` 中固定 `sportType` 的表述改为「控制参数 / planning context」，避免与活动建议的用户输入冲突。

### Step 3：标注旧设计稿状态

在：

```text
docs/risk_warning_feature_design_v1.md
```

顶部增加说明：

```text
状态：已废弃 / 被 activity_advice_feature_design_v2 替代。
原因：功能语义从风险预警改为活动建议，计划活动时间只来自用户显式输入。
```

### Step 4：补契约静态检查说明

在 v2 设计文档中写入后续静态验收命令：

```bash
rg "风险预警|risk_assessment|REPORT_RISK_ASSESSMENT|RiskAssessment|risk-assessment" main.py llm_backend.py track.html docs/js_api_contract.json tests
```

预期：

- P0 只允许命中 deprecated 说明。
- P2 cleanup 完成后，生产代码应无旧风险命名。

---

## 七、验收标准

- [ ] `docs/activity_advice_feature_design_v2.md` 已创建。
- [ ] v2 文档明确「活动建议」替代「风险预警」。
- [ ] v2 文档明确用户输入 `活动类型` / `计划活动时间` 均为可选。
- [ ] v2 文档明确 `planned_start_time` 不得从 FIT/GPX 历史时间提取。
- [ ] v2 文档明确历史天气不得进入活动建议 prompt。
- [ ] v2 文档明确输出 schema 为 `activity_advice`，不再使用 `risk_assessment`。
- [ ] v2 文档明确活动建议不持久化，并列出所有清空触发点。
- [ ] v2 文档包含旧风险预警退场清单。
- [ ] `docs/js_api_contract.json` 已包含 `__REPORT_ACTIVITY_ADVICE__` 契约。
- [ ] `docs/risk_warning_feature_design_v1.md` 已标注废弃或替代关系。

---

## 八、完成报告要求

完成本任务后，请输出：

```text
P0 活动建议契约回正完成报告

1. 本次目标
2. 已更新文件
3. 契约变更
4. 明确禁止项
5. 旧风险预警退场范围
6. 验收结果
7. 未完成事项
8. 下一步建议
```

---

## 九、下一步建议

P0 完成后，进入下一任务：

```text
P1 后端活动建议链路实现
```

P1 建议目标：

- 新增 `REPORT_ACTIVITY_ADVICE = "__REPORT_ACTIVITY_ADVICE__"`。
- 新增 `_activity_advice_payload(...)`，只输出路线事实和用户显式 planning context。
- 新增 `ACTIVITY_ADVICE_OUTPUT_SCHEMA`。
- 新增 `empty_activity_advice(...)`。
- 新增 `normalize_activity_advice_json(...)`。
- 新增 `build_activity_advice_system_prompt(...)` / `build_activity_advice_user_prompt(...)`。
- 在 `Api.call_llm` 新增活动建议分支，入口立即清空 `_chat_messages` 并刷新 session。
- 不写 DB、不修改 `_ai_snapshot`、不消费历史天气、不传 `start_time`。
- 为 DB 活动和临时 GPX 路线分别设计可用降级路径。

P1 不建议做前端 UI 重构；前端表单和展示留到 P2。

