# P1 活动建议后端链路实现提示词

> 任务类型：P1 后端 AI 链路实现
> 适用范围：轨迹报告「活动建议」后端 sentinel / payload / prompt / normalizer / call_llm 分支
> 前置条件：P0 活动建议契约已固化，见 `docs/activity_advice_feature_design_v2.md`
> 核心目标：新增 `__REPORT_ACTIVITY_ADVICE__` 后端链路，替代旧 `__REPORT_RISK_ASSESSMENT__` 的模型语义

---

## 零、架构契约核对

执行本任务前必须阅读并遵守：

- `docs/activity_advice_feature_design_v2.md`
- `docs/p0_activity_advice_contract_prompt.md`
- `docs/js_api_contract.json`
- 全局架构契约 `fit-arch-contrac`
- 当前实现：`main.py` / `llm_backend.py`

本任务必须遵守以下强制契约：

- 活动建议结果不持久化，不写 DB，不进入 `ai_snapshots`，不修改 canonical activity。
- 活动建议不进入普通 AI 教练 `_chat_messages`。
- 活动建议后端分支入口必须立即清空 `_chat_messages` 并刷新 session。
- 计划活动时间只来自用户显式传入的 `planned_start_time`，不得从 FIT/GPX `start_time`、`start_time_utc` 或轨迹点时间提取。
- 活动类型只来自用户显式传入的 `user_activity_type`，不得从文件名、标题、设备名推断。
- 活动建议 payload 禁止包含历史天气、`_track_weather`、`start_time`、`start_time_utc`、`points[]`、`placemarks[]`、`shadow_diff`、`shadow_diff_json`、`diff`。
- 后端可以从 `_ai_snapshot` 读取 DB 活动路线事实，但必须经过活动建议专用白名单过滤。
- 临时 GPX 无 `activity_id` / `_ai_snapshot` 时不得前端拼 prompt；后端应返回明确 empty fallback，或使用已存在的后端路线事实上下文能力构建降级 payload。
- 本任务不做前端 UI 表单，不删除旧风险预警生产代码；旧代码 cleanup 留到 P3。

---

## 一、任务背景

P0 已确认旧「风险预警」语义不适合当前产品边界。新功能「活动建议」需要后端提供独立 AI 链路：

```text
前端用户显式计划输入
    +
后端路线事实白名单
    ->
__REPORT_ACTIVITY_ADVICE__
    ->
activity_advice JSON
```

旧实现问题：

- `__REPORT_RISK_ASSESSMENT__` 使用 risk schema，输出 `risk_assessment`。
- `_risk_snapshot_payload` 包含 `start_time`，且可消费历史天气上下文。
- 风险等级 `低/中/高` 容易诱导模型做安全预警式判断。
- `REPORT_RISK_ASSESSMENT` 分支没有在入口立即隔离普通 AI 教练会话。

本任务目标是新增一条干净的后端活动建议链路，为 P2 前端接入做准备。

---

## 二、任务目标

完成 P1 后端活动建议链路：

1. 在 `main.py` 新增 `REPORT_ACTIVITY_ADVICE = "__REPORT_ACTIVITY_ADVICE__"`。
2. 在 `llm_backend.py` 新增活动建议 output schema。
3. 在 `llm_backend.py` 新增 `_activity_advice_payload(snapshot, planning_context)`。
4. 在 `llm_backend.py` 新增 `build_activity_advice_system_prompt(...)`。
5. 在 `llm_backend.py` 新增 `build_activity_advice_user_prompt()`。
6. 在 `llm_backend.py` 新增 `empty_activity_advice(error="")`。
7. 在 `llm_backend.py` 新增 `normalize_activity_advice_json(raw_text)`。
8. 在 `main.py` 新增 `_build_activity_advice_messages(...)`。
9. 在 `Api.call_llm` 新增 `__REPORT_ACTIVITY_ADVICE__` 分支。
10. 新增后端契约测试，覆盖 forbidden 字段、normalizer、call_llm happy/fallback。

---

## 三、本任务改动范围

建议改动文件：

- `main.py`
- `llm_backend.py`
- `tests/test_activity_advice_prompts.py`
- `tests/test_activity_advice_integration.py`
- `docs/js_api_contract.json` 如 P0 文档仍需微调

本任务禁止改动：

- 不改 `track.html` UI。
- 不接入天气预报 API。
- 不新增 DB 字段。
- 不写 migration。
- 不删除旧 `REPORT_RISK_ASSESSMENT` 生产代码。
- 不修改普通 AI 教练聊天语义。
- 不让前端传 `points[]` / `metrics` / `curves` / DOM 文本。

---

## 四、目标后端契约

### 4.1 Sentinel

新增:

```python
REPORT_ACTIVITY_ADVICE = "__REPORT_ACTIVITY_ADVICE__"
```

### 4.2 请求控制参数

`call_llm(prompt, sport_type)` 签名保持不变。由于第二参数历史命名为 `sport_type`，本任务中将其作为 activity advice 的 `control_context` 使用。

推荐前端未来传入 JSON 字符串:

```json
{
  "user_activity_type": "hiking",
  "planned_start_time": "2026-06-12T08:30"
}
```

后端解析规则：

- 若第二参数是合法 JSON object 字符串，解析为 planning context。
- 若第二参数为空或非法 JSON，降级为空 planning context，不抛异常。
- P1 可兼容纯字符串活动类型，但必须标注为过渡兼容；正式 P2 应传 JSON。

### 4.3 Planning Context

标准结构：

```python
{
    "user_activity_type": "",
    "planned_start_time": "",
    "activity_type_source": "user_input" | "missing",
    "planned_time_source": "user_input" | "missing",
}
```

约束：

- `planned_start_time` 不得 fallback 到 `_ai_snapshot["start_time"]`。
- `planned_start_time` 不得 fallback 到 `_track_points[0]["time"]`。
- `user_activity_type` 不得 fallback 到文件名或活动标题。

### 4.4 Payload 白名单

新增 `_activity_advice_payload` 只允许输出：

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

禁止字段：

```text
start_time
start_time_utc
weather_json
weather_context
_track_weather
avg_hr
max_hr
calories
tss
hr_decoupling
hr_curve
speed_curve
device_name
points
placemarks
shadow_diff
shadow_diff_json
diff
```

说明：

- `avg_hr` / `max_hr` / `calories` 暂不进入 v1，因为活动建议面向路线计划，不是历史运动表现复盘。
- 若后续要做个人能力建议，另开 P4 评审，不在本任务扩大。

---

## 五、目标输出 Schema

新增:

```python
ACTIVITY_ADVICE_OUTPUT_SCHEMA = """{
  "supply_advice": {"status": "提示|注意|重点关注", "basis": "依据哪些路线事实或用户输入", "advice": "补给建议"},
  "weather_check": {"status": "信息不足|提示|注意|重点关注", "basis": "是否有计划活动时间；没有则明确说明信息不足", "advice": "天气检查建议"},
  "equipment_advice": {"status": "提示|注意|重点关注", "basis": "依据海拔、爬升、坡度、路线环境等", "advice": "装备建议"},
  "physical_plan": {"status": "提示|注意|重点关注", "basis": "依据距离、爬升、坡度、预计耗时等", "advice": "体力安排建议"},
  "disclaimer": "以上建议由 AI 基于当前轨迹和用户填写的计划信息生成，仅供出行准备参考。"
}"""
```

Normalizer 输出必须补齐:

```python
{
    "supply_advice": {"status": "提示", "basis": "...", "advice": "..."},
    "weather_check": {"status": "信息不足", "basis": "...", "advice": "..."},
    "equipment_advice": {"status": "提示", "basis": "...", "advice": "..."},
    "physical_plan": {"status": "提示", "basis": "...", "advice": "..."},
    "disclaimer": "...",
    "error": "",
}
```

状态约束：

```text
信息不足
提示
注意
重点关注
```

其中 `信息不足` 只建议用于 `weather_check` 或整体 empty fallback 场景。

---

## 六、Prompt 契约

### 6.1 System Prompt 必须包含

- DATA BOUNDARY。
- 当前 route facts JSON。
- 当前 planning context JSON。
- 四个建议维度。
- 明确禁止使用历史 `start_time` / `start_time_utc` / 历史天气。
- 明确没有 `planned_start_time` 时，天气只能给检查清单，不能判断具体天气。
- 明确不得输出 markdown。
- 明确不得给医学诊断、安全保证或确定性天气预报。

### 6.2 User Prompt

保持简单，不注入任何事实字段：

```text
请基于系统指令中的路线事实和用户计划上下文生成活动建议 JSON。只输出纯 JSON。
```

---

## 七、main.py 实现要求

### 7.1 messages 构建器

新增:

```python
def _build_activity_advice_messages(
    snapshot: dict[str, Any] | None,
    planning_context: dict[str, Any] | None,
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": llm_backend.build_activity_advice_system_prompt(snapshot, planning_context),
        },
        {
            "role": "user",
            "content": llm_backend.build_activity_advice_user_prompt(),
        },
    ]
```

### 7.2 call_llm 分支

新增分支必须在普通聊天逻辑前处理：

```python
if prompt == self.REPORT_ACTIVITY_ADVICE:
    self._chat_messages = []
    self._new_session_id()
    sid = self._session_id

    planning_context = _parse_activity_advice_context(sport_type)
    if not self._ai_snapshot:
        return {"ok": True, "activity_advice": llm_backend.empty_activity_advice("请先加载活动轨迹")}

    messages = _build_activity_advice_messages(self._ai_snapshot, planning_context)
    try:
        text = llm_backend.chat_completions(
            url=url,
            api_key=api_key,
            model=model,
            messages=messages,
            session_id=sid,
            agent_id=agent_id,
        )
    except Exception as exc:
        return {"ok": True, "activity_advice": llm_backend.empty_activity_advice(f"LLM 调用失败: {exc}")}

    return {"ok": True, "activity_advice": llm_backend.normalize_activity_advice_json(text)}
```

注意：

- `sid` 必须在 `_new_session_id()` 之后重新读取。
- 不得复用旧 `risk_assessment` 返回字段。
- 不得把 `_track_weather` 传入 messages。
- 不得在异常路径抛给前端。

### 7.3 临时 GPX 降级

P1 如果暂时无法为无 `_ai_snapshot` 的临时 GPX 构建后端路线事实，则必须返回:

```python
empty_activity_advice("请先加载活动轨迹")
```

并在完成报告中标注:

```text
临时 GPX 后端 route facts 构建留到 P1.5 或 P2 前置任务。
```

不得为了支持临时 GPX 而让前端拼 prompt。

---

## 八、测试要求

### 8.1 Prompt / Payload 单测

新建:

```text
tests/test_activity_advice_prompts.py
```

覆盖：

- schema 包含 `supply_advice/weather_check/equipment_advice/physical_plan/disclaimer`。
- `_activity_advice_payload` 不包含 `start_time` / `start_time_utc` / `weather_context` / `shadow_diff`。
- planning context 中用户显式 `planned_start_time` 会进入 payload。
- 缺少 `planned_start_time` 时 planning context 标注 `planned_time_source = "missing"`。
- system prompt 包含 DATA BOUNDARY。
- system prompt 包含禁止历史时间和历史天气条款。
- user prompt 不包含 distance / start_time 等具体事实字段。

### 8.2 Normalizer 单测

覆盖：

- `None` / 空字符串返回 empty。
- markdown wrapped JSON 可剥离。
- invalid JSON 返回 empty + error。
- 非 dict 返回 empty + error。
- invalid status fallback 到 `提示` 或 `信息不足`。
- 缺字段补齐四维度。
- 超长 `basis/advice/disclaimer` 截断。

### 8.3 Integration 测试

新建:

```text
tests/test_activity_advice_integration.py
```

覆盖：

- happy path 返回 `{ok: True, activity_advice: ...}`。
- 入口清空 `_chat_messages`。
- 入口刷新 session，且本次 LLM 调用使用刷新后的 `sid`。
- 无 `_ai_snapshot` 时返回 empty fallback，且已清空会话。
- LLM 异常返回 empty fallback，且不抛异常。
- 不向 `_build_activity_advice_messages` 传 `_track_weather`。
- 旧 `risk_assessment` 字段不会出现在新分支响应中。

---

## 九、验收命令

建议运行：

```bash
python3 -m unittest tests.test_activity_advice_prompts tests.test_activity_advice_integration
python3 -m unittest tests.test_response_envelope_contract
python3 -m json.tool docs/js_api_contract.json >/tmp/js_api_contract_check.json
```

静态检查：

```bash
rg "REPORT_ACTIVITY_ADVICE|activity_advice|build_activity_advice|normalize_activity_advice|empty_activity_advice" main.py llm_backend.py tests docs/js_api_contract.json
rg "start_time|start_time_utc|weather_context|_track_weather" llm_backend.py tests/test_activity_advice_prompts.py
```

预期：

- 新活动建议链路存在。
- 活动建议 payload / prompt 测试明确禁止历史时间和历史天气。
- `docs/js_api_contract.json` 合法。

---

## 十、验收标准

- [ ] `main.py` 新增 `REPORT_ACTIVITY_ADVICE`。
- [ ] `main.py` 新增 `_build_activity_advice_messages`。
- [ ] `Api.call_llm` 新增 `__REPORT_ACTIVITY_ADVICE__` 分支。
- [ ] 新分支入口立即清空 `_chat_messages` 并刷新 session。
- [ ] 新分支本次 LLM 调用使用刷新后的 `session_id`。
- [ ] 新分支返回 `{ok, activity_advice}`。
- [ ] 新分支不传 `_track_weather`。
- [ ] `llm_backend.py` 新增活动建议 schema / payload / prompt / empty / normalizer。
- [ ] `_activity_advice_payload` 不包含 forbidden 字段。
- [ ] 单测和集成测试覆盖 happy / fallback / exception。
- [ ] 旧 `__REPORT_RISK_ASSESSMENT__` 仍可保留但不得被新功能复用。

---

## 十一、完成报告要求

完成本任务后，请输出：

```text
P1 活动建议后端链路实现完成报告

1. 本次目标
2. 已更新文件
3. 新增后端能力
4. 契约约束落实情况
5. 测试结果
6. 已知限制
7. 未完成事项
8. 下一步建议
```

---

## 十二、下一步建议

P1 完成后进入：

```text
P2 前端活动建议 UI 接入
```

P2 建议目标：

- 将轨迹报告卡片标题从「风险预警」改为「活动建议」。
- 增加活动类型下拉框。
- 增加计划活动时间输入框，默认空，不自动填 FIT/GPX 历史时间。
- 新增 `requestActivityAdvice()`，调用 `__REPORT_ACTIVITY_ADVICE__`。
- 新增 `buildActivityAdviceHTML()`，渲染四个建议维度和 `basis`。
- 新增 `resetActivityAdviceState()`。
- 在导入新 GPX/FIT、切换轨迹、切主 Tab、离开 report 侧栏、重新点击生成建议时清空旧结果。
- 前端不得传 `points[]`、DOM 文本或自行推导事实字段。

P2 不建议删除旧风险预警生产代码；旧代码集中清理留到 P3 Cleanup。

