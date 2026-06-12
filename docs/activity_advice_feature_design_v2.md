# 轨迹报告「活动建议」功能设计方案 v2

> **状态**: P0 契约回正完成,待 P1 后端实现
> **替代**: `docs/risk_warning_feature_design_v1.md`
> **核心变化**: 功能语义从「风险预警」改为「活动建议」
> **日期**: 2026-06-10
> **范围**: 产品语义、数据边界、输入契约、输出契约、生命周期、旧风险预警退场规则

---

## 0. 一句话结论

「活动建议」不是安全预警、天气预报或医学判断,而是基于当前轨迹路线事实和用户显式填写的计划信息,生成一次性的补给、天气检查、装备和体力安排建议。

---

## 1. 功能定位

旧「风险预警」命名会暗示系统具备确定性的危险判断能力,但当前数据资产更适合做路线准备建议。尤其 GPX 文件可能只有纯轨迹信息,缺少运动类型、计划活动时间、心率、功率等上下文。

新功能命名为:

```text
活动建议
```

四个建议维度为:

```text
补给建议
天气检查
装备建议
体力安排
```

禁止使用以下定位:

```text
风险预警
安全预警
危险判断
天气预报
医学建议
```

---

## 2. 数据资产盘点

### 2.1 已可支撑 v1 的数据

现有系统已经具备活动建议 v1 所需的大部分路线事实:

| 数据 | 当前来源 | 用途 |
|---|---|---|
| 距离 | DB canonical / Resolver / 当前轨迹上下文 | 补给、体力安排 |
| 时长或估算时长 | DB canonical / 轨迹报告解释层 | 补给、体力安排 |
| 累计爬升 | DB canonical / Resolver | 装备、体力安排 |
| 累计下降 | report metrics | 装备、体力安排 |
| 最高/最低海拔 | report metrics | 装备、体力安排 |
| 最大连续爬升 | report metrics | 体力安排 |
| 坡度/上坡比例 | report metrics v2 | 装备、体力安排 |
| MTDI 难度分 | report metrics | 体力安排 |
| 地区/经纬度 | DB canonical / Resolver | 天气检查、装备建议 |

### 2.2 不直接用于活动建议 v1 的数据

以下数据虽然存在,但不应进入活动建议 prompt:

| 数据 | 不使用原因 |
|---|---|
| FIT / GPX `start_time` | 它是历史记录时间,不是用户未来计划活动时间 |
| `start_time_utc` | 同上 |
| 历史 `weather_json` | 它描述历史活动时段,不能代表用户计划出发时段 |
| `_track_weather` | 当前语义是历史天气上下文,不适合计划建议 |
| 心率/功率/训练负荷 | v1 聚焦路线准备,个人能力建议后续单独评审 |
| 全量 `points[]` | 禁止前端拼 prompt 或把 per-point 数据送入 AI |
| `shadow_diff` / `shadow_diff_json` / `diff` | 审计字段隔离 |

---

## 3. 用户可选输入

活动建议卡片增加两个可选输入:

| 字段 | 控件 | 默认值 | 说明 |
|---|---|---|---|
| 活动类型 | 下拉选择 | 空 | 用户显式选择,用于解释路线准备语境 |
| 计划活动时间 | datetime-local | 空 | 用户显式选择,用于天气检查语境 |

推荐活动类型选项:

```text
hiking
mountaineering
trail_running
running
cycling
mountain_biking
other
```

约束:

- 两个字段均为可选。
- 不从 FIT / GPX 的历史时间自动填充计划活动时间。
- 不从文件名、标题、设备名推断活动类型。
- 用户输入只用于本次活动建议,不写 DB、不改 canonical。
- 未填写计划活动时间时,天气检查只能输出信息不足或检查清单。

---

## 4. Payload 契约

目标 payload 只包含路线事实和用户显式计划上下文:

```json
{
  "route_facts": {
    "activity_id": null,
    "distance_km": null,
    "distance_display": "",
    "duration_sec": null,
    "elevation_gain_m": null,
    "total_descent_m": null,
    "max_alt_m": null,
    "min_alt_m": null,
    "avg_grade_pct": null,
    "max_slope_pct": null,
    "min_slope_pct": null,
    "uphill_pct": null,
    "downhill_pct": null,
    "up_count": null,
    "down_count": null,
    "max_single_climb_m": null,
    "difficulty_score": null,
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

### 4.1 白名单字段

活动建议专用 route facts 白名单:

```text
activity_id
distance_km
distance_display
duration_sec
elevation_gain_m
total_descent_m
max_alt_m
min_alt_m
avg_grade_pct
max_slope_pct
min_slope_pct
uphill_pct
downhill_pct
up_count
down_count
max_single_climb_m
difficulty_score
region
start_lat
start_lon
source
```

### 4.2 Forbidden 字段

以下字段不得进入活动建议 payload 或 prompt:

```text
start_time
start_time_utc
历史 weather_json
_track_weather
points[]
placemarks[]
hr_curve
speed_curve
shadow_diff
shadow_diff_json
diff
DOM 文本
前端自行推断的事实字段
```

---

## 5. 输出 Schema

正式响应字段:

```json
{
  "ok": true,
  "activity_advice": {
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
}
```

约束:

- 不再返回 `risk_assessment`。
- 不再使用 `低/中/高风险` 作为主表达。
- 每个维度必须有 `basis`。
- 缺少计划活动时间时,`weather_check` 必须说明信息不足。
- 不输出安全保证、医学诊断或确定性天气预报。

---

## 6. Sentinel / API 契约

正式新 sentinel:

```python
REPORT_ACTIVITY_ADVICE = "__REPORT_ACTIVITY_ADVICE__"
```

前端调用目标:

```javascript
window.pywebview.api.call_llm("__REPORT_ACTIVITY_ADVICE__", planningContext)
```

其中 `planningContext` 是 JSON 字符串或后端可解析的控制参数,只允许携带:

```json
{
  "user_activity_type": "",
  "planned_start_time": ""
}
```

旧 sentinel:

```python
REPORT_RISK_ASSESSMENT = "__REPORT_RISK_ASSESSMENT__"
```

状态:

```text
deprecated, 后续 cleanup 任务删除
```

---

## 7. 生命周期与持久化边界

活动建议结果只存在前端内存。

禁止:

- 写 DB。
- 写 `localStorage` / `sessionStorage`。
- 写 `ai_snapshots`。
- 修改 `_ai_snapshot`。
- 进入普通 AI 教练 `_chat_messages`。
- 作为活动详情或轨迹报告的永久属性保存。

必须清空旧活动建议的触发点:

```text
1. 导入新 GPX/FIT
2. 切换轨迹文件
3. 从活动列表加载另一条轨迹
4. applyDataAndRender(...)
5. switchTab(...)
6. switchSidebarTab(tab) 且 tab !== "report"
7. requestActivityAdvice() 重新点击生成前
```

后端 `__REPORT_ACTIVITY_ADVICE__` 分支要求:

- 入口立即 `self._chat_messages = []`。
- 入口立即 `self._new_session_id()`。
- 异常返回 `empty_activity_advice(error)`。
- 不写 DB。
- 不消费历史天气。
- 不传 `start_time` / `start_time_utc`。

---

## 8. 旧风险预警退场清单

后续 cleanup 任务必须清理以下生产代码命名:

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

允许保留:

- 历史调研文档。
- 迁移说明。
- 测试中用于断言旧命名已删除的静态检查。

生产代码中不应继续出现旧风险命名。

---

## 9. 实施任务拆分

### P1 后端活动建议链路实现

- 新增 `REPORT_ACTIVITY_ADVICE = "__REPORT_ACTIVITY_ADVICE__"`。
- 新增 `_activity_advice_payload(...)`。
- 新增 `ACTIVITY_ADVICE_OUTPUT_SCHEMA`。
- 新增 `empty_activity_advice(...)`。
- 新增 `normalize_activity_advice_json(...)`。
- 新增 `build_activity_advice_system_prompt(...)` / `build_activity_advice_user_prompt(...)`。
- 在 `Api.call_llm` 新增活动建议分支。
- 覆盖 DB 活动和临时 GPX 路线的降级路径。

### P2 前端活动建议 UI 实现

- 卡片标题改为「活动建议」。
- 增加活动类型下拉和计划活动时间输入。
- 新增 `requestActivityAdvice()`。
- 新增 `resetActivityAdviceState()`。
- 新增 `buildActivityAdviceHTML()`。
- 所有清空触发点接入。

### P3 Cleanup 与测试

- 删除旧风险预警生产代码。
- 更新 `docs/js_api_contract.json`。
- 新增 prompt / normalizer / payload / integration 测试。
- 增加静态检查,确保生产代码无旧风险命名。

---

## 10. 验收清单

- [ ] 功能名称已固定为「活动建议」。
- [ ] 文档明确用户可选输入:活动类型、计划活动时间。
- [ ] 文档明确计划活动时间只来自用户显式输入。
- [ ] 文档明确历史天气和历史 `start_time` 不进入活动建议。
- [ ] 文档明确输出字段为 `activity_advice`。
- [ ] 文档明确活动建议不持久化。
- [ ] 文档列出所有清空触发点。
- [ ] 文档包含旧风险预警退场清单。
- [ ] `docs/js_api_contract.json` 已登记 `__REPORT_ACTIVITY_ADVICE__`。

---

## 11. 静态验收建议

P3 cleanup 完成后运行:

```bash
rg "风险预警|risk_assessment|REPORT_RISK_ASSESSMENT|RiskAssessment|risk-assessment" main.py llm_backend.py track.html docs/js_api_contract.json tests
```

预期:

- 生产代码无旧风险命名。
- 只允许历史文档或迁移说明命中。

