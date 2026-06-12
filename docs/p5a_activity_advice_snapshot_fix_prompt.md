# P5A 活动建议当前轨迹快照修复提示词

> 任务类型：P5A 缺陷修复 / 后端快照补齐 / 回归验证
> 适用范围：轨迹报告「活动建议」点击生成后，当前导入/展示轨迹的路线事实快照进入 OpenClaw / LLM 的链路
> 前置条件：P0-P4 已完成；P3 已删除旧「风险预警」生产链路；P4 暴露当前轨迹活动建议返回空态的问题
> 核心目标：修复 `__REPORT_ACTIVITY_ADVICE__` 只依赖 DB `_ai_snapshot` 的缺口，让当前展示的 FIT/GPX 轨迹也能通过后端白名单快照生成有效活动建议

---

## 零、架构契约核对

执行本任务前必须阅读并遵守：

- `docs/activity_advice_feature_design_v2.md`
- `docs/p1_activity_advice_backend_prompt.md`
- `docs/p2_activity_advice_frontend_prompt.md`
- `docs/p3_activity_advice_cleanup_prompt.md`
- `docs/activity_advice_manual_test_checklist.md`
- `docs/js_api_contract.json`
- 当前实现：`main.py` / `llm_backend.py` / `track.html`
- 当前测试：`tests/test_activity_advice_prompts.py` / `tests/test_activity_advice_integration.py` / `tests/test_activity_advice_frontend.py` / `tests/test_activity_advice_cleanup.py`

本任务必须遵守以下强制契约：

- 活动建议仍只通过 `__REPORT_ACTIVITY_ADVICE__ -> { ok, activity_advice }`。
- 前端点击「生成建议」仍只能传用户显式 planning context：`user_activity_type` 与 `planned_start_time`。
- 前端不得把 `points[]`、`placemarks[]`、DOM 文本、UI 统计值、图表数据或前端 fallback 拼进 `call_llm` 参数。
- 后端可以在 `sync_track_context(...)` 阶段接收前端已有的轨迹上下文用于 UI 同步，但 LLM 只能消费后端构建的活动建议专用白名单快照。
- 活动建议快照不得包含全量 `points[]`、`placemarks[]`、历史天气、`_track_weather`、`weather_json`、`shadow_diff`、`diff`。
- `planned_start_time` 只能来自用户显式输入，不得从 FIT/GPX 历史 `start_time`、`start_time_utc`、轨迹点 `time` 或活动详情时间提取。
- 活动类型只能来自用户选择，不得从文件名、标题、设备、历史记录自动推断。
- 活动建议结果不持久化，不写 DB、不写 `localStorage` / `sessionStorage`、不进入 `ai_snapshots`、不进入普通 AI 教练 `_chat_messages`。
- 切换轨迹、导入新文件、切 Tab、离开 report 侧栏、重新生成建议时继续丢弃旧活动建议。
- KML 不作为本次版本目标。
- 本任务修复的是“后端活动建议路线事实来源缺失”，不是接入天气 API、不是恢复旧风险预警、不是重做 UI。

---

## 一、问题背景

P4 人工观察发现：用户在轨迹报告侧栏点击「生成建议」后，前端显示的建议仍是空态：

```text
当前路线事实或用户计划信息不足
请先加载活动轨迹
```

但当前页面实际上已经有轨迹事实，例如：

```text
里程 19.19 km
耗时 7h 52m
爬升 1118 m
最高 1019 m
```

这说明当前链路没有把“正在展示的轨迹路线事实”送入活动建议 prompt。现有 P1 实现主要依赖：

```python
self._ai_snapshot
```

而 `_ai_snapshot` 主要从 DB `activity_id` 构建。对于当前导入/展示的 GPX 或无 `activity_id` 的轨迹，`sync_track_context(...)` 会把 `_ai_snapshot` 置空，导致 `call_llm(__REPORT_ACTIVITY_ADVICE__)` 直接返回 `empty_activity_advice("请先加载活动轨迹")`。

正确工作流应参考雷达图 AI 洞察的模式：

```text
用户点击生成建议
→ 前端只传 planning context
→ 后端读取当前轨迹的权威/同步路线事实快照
→ 后端构建活动建议专用 route snapshot
→ 后端把 route snapshot + planning context 发给 OpenClaw / LLM
→ LLM 返回四类活动建议
→ 前端渲染活动建议
```

---

## 二、任务目标

完成 P5A 修复：

1. 在 `Api` 内新增活动建议专用内存快照，例如：

```python
self._activity_advice_snapshot: dict[str, Any] | None = None
```

2. 在 `sync_track_context(...)` 中同步当前轨迹时，同时构建或刷新 `_activity_advice_snapshot`。
3. 当存在 DB `activity_id` 且 `_ai_snapshot` 构建成功时，活动建议快照优先来自 DB truth `_ai_snapshot` 的白名单字段。
4. 当不存在 DB `activity_id` 或 `_ai_snapshot` 为空时，后端基于当前同步轨迹上下文构建“临时路线事实快照”。
5. `call_llm(__REPORT_ACTIVITY_ADVICE__)` 使用 `_activity_advice_snapshot`，而不是只检查 `_ai_snapshot`。
6. 临时路线事实快照必须只包含聚合后的白名单字段，不包含全量点。
7. 增加测试覆盖 DB 活动、临时 GPX/导入轨迹、无轨迹三类路径。
8. 保持 P1-P4 既有契约和测试全部通过。

---

## 三、本任务改动范围

建议改动：

- `main.py`
- `tests/test_activity_advice_integration.py`
- 如需覆盖 payload 白名单：`tests/test_activity_advice_prompts.py`
- 如需契约说明微调：`docs/js_api_contract.json`
- 如需记录修复结果：`docs/activity_advice_manual_test_checklist.md`

原则上不改：

- `track.html` 的 `requestActivityAdvice()` 参数结构。
- `llm_backend.py` 的活动建议 prompt 主体。
- DB schema。
- 旧风险预警相关代码。
- KML 支持。

如果确实需要轻微更新 `track.html`：

- 只能为了补充 `sync_track_context` 的后端同步字段。
- `requestActivityAdvice()` 仍不得传 `points[]`、`activityMetrics`、`currentWeather`、DOM 文本或前端拼 prompt。

---

## 四、设计方案

### 4.1 新增活动建议专用快照

在 `Api.__init__` 中新增：

```python
self._activity_advice_snapshot: dict[str, Any] | None = None
```

语义：

- 仅用于 `__REPORT_ACTIVITY_ADVICE__`。
- 只保留路线事实白名单字段。
- 生命周期跟随当前轨迹上下文。
- 切换/导入新轨迹时由 `sync_track_context(...)` 覆盖。
- 不写 DB，不进入 `ai_snapshots`。

### 4.2 DB 活动路径

当 `sync_track_context(...)` 收到 `activity_id` 且 `_build_ai_snapshot(activity_id)` 成功：

```python
self._ai_snapshot = _build_ai_snapshot(int(activity_id))
self._activity_advice_snapshot = _build_activity_advice_snapshot_from_ai_snapshot(self._ai_snapshot)
```

要求：

- 不改变 `_ai_snapshot` 对其他 AI 功能的语义。
- `_activity_advice_snapshot` 必须经过活动建议白名单过滤。
- 不包含 `start_time` / `start_time_utc`。
- 不包含历史天气。

### 4.3 临时 GPX/FIT 路径

当无 `activity_id` 或 `_ai_snapshot` 构建失败时：

```python
self._activity_advice_snapshot = _build_activity_advice_snapshot_from_track_context(obj)
```

这个函数可以读取 `sync_track_context(...)` 收到的当前轨迹上下文，但输出必须是聚合字段，例如：

```text
distance_km
distance_display
duration_sec
elevation_gain_m
total_descent_m
max_alt_m
min_alt_m
start_lat
start_lon
region
source
```

如果当前可用数据不足，字段可以缺省或为 `None`，但不能伪造。

注意：

- 可以在后端基于当前点列做路线事实聚合，但最终 prompt 只能收到聚合后的快照。
- 不得把 `points[]` 直接传给 `llm_backend.build_activity_advice_system_prompt(...)`。
- 不得把轨迹点 `time` 用作 `planned_start_time`。
- 不得把 `weather` / `_track_weather` 写入活动建议快照。
- 如果 `track.html` 没有同步足够的聚合事实，可以先使用后端从点列计算的基础路线事实；后续再考虑后端解析阶段产出 report metrics。

### 4.4 活动建议调用路径

修改：

```python
if not self._ai_snapshot:
    return _activity_advice_empty("请先加载活动轨迹")

messages = _build_activity_advice_messages(self._ai_snapshot, planning_context)
```

为：

```python
snapshot = self._activity_advice_snapshot
if not snapshot:
    return _activity_advice_empty("请先加载活动轨迹")

messages = _build_activity_advice_messages(snapshot, planning_context)
```

要求：

- 仍在分支入口清空 `_chat_messages` 并刷新 session。
- 仍不传 `_track_weather`。
- LLM 异常仍返回 `empty_activity_advice(error)`。
- 返回字段仍是 `{ok: True, activity_advice: ...}`。

---

## 五、快照构建白名单

`_activity_advice_snapshot` 允许字段与 `llm_backend._activity_advice_payload(...)` 保持一致：

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

强制禁止字段：

```text
start_time
start_time_utc
time
timestamp
weather
weather_json
weather_context
_track_weather
points
points[]
placemarks
placemarks[]
shadow_diff
shadow_diff_json
diff
hr_curve
speed_curve
records
raw_records
track_points
fit_records
gpx_points
DOM
```

---

## 六、临时轨迹聚合建议

如果需要从当前点列构建临时 route facts，可实现小型后端聚合函数，例如：

```python
def _build_activity_advice_snapshot_from_track_context(obj: dict[str, Any]) -> dict[str, Any] | None:
    points = obj.get("points") if isinstance(obj.get("points"), list) else []
    if not points:
        return None
    # 只在函数内部遍历 points，输出聚合事实，不保存全量 points 到活动建议快照
```

可聚合字段：

- `distance_km`：优先使用后端/同步上下文中已有权威距离；若没有，可用点列 haversine 聚合。
- `distance_display`：由 `distance_km` 格式化。
- `duration_sec`：仅当点列时间能明确表示轨迹持续时间时可用于“路线参考耗时”，但不得当作计划出发时间。
- `elevation_gain_m`：可用海拔正向累计的保守估算；缺失则 `None`。
- `total_descent_m`：可用海拔负向累计的保守估算；缺失则 `None`。
- `max_alt_m` / `min_alt_m`：来自点列海拔；缺失则 `None`。
- `start_lat` / `start_lon`：来自首个有效坐标。
- `source`：建议使用 `"track_context"` 或 `"temporary_track_context"`。

谨慎项：

- 坡度、最大连续爬升、难度分如果没有后端成熟算法，不要在 P5A 中硬算。
- 如计算爬升，必须在测试中注明它是临时路线事实估算，用于活动建议，不写 canonical。
- 不得把该临时估算污染 DB 或其他系统指标。

---

## 七、测试要求

### 7.1 集成测试

更新或新增 `tests/test_activity_advice_integration.py`：

1. DB `_ai_snapshot` 路径：
   - 设置 `api._ai_snapshot` 后调用 `REPORT_ACTIVITY_ADVICE`。
   - 验证 builder 收到的是活动建议快照。
   - 验证不包含 `start_time` / `_track_weather`。

2. 临时轨迹路径：
   - 调用 `api.sync_track_context(...)`，payload 含 `points`、`filename`，不含 `activityId`。
   - 然后调用 `api.call_llm(api.REPORT_ACTIVITY_ADVICE, planning_context)`。
   - mock `_build_activity_advice_messages` 捕获 snapshot。
   - 断言 snapshot 包含 `distance_km` / `elevation_gain_m` / `max_alt_m` 或至少基础路线事实。
   - 断言 snapshot 不包含 `points`、`placemarks`、`weather`、`start_time`。
   - 断言不是 empty fallback。

3. 无轨迹路径：
   - 不调用 `sync_track_context`，且 `_activity_advice_snapshot` 为空。
   - 调用活动建议返回 `empty_activity_advice("请先加载活动轨迹")`。

4. 切换轨迹路径：
   - 连续调用两次 `sync_track_context(...)`，第二条轨迹距离不同。
   - 验证 `_activity_advice_snapshot` 被覆盖，不残留第一条路线事实。

### 7.2 前端静态测试

保持 `tests/test_activity_advice_frontend.py`：

- `requestActivityAdvice()` 仍只发送 planning context。
- 不允许新增 `appState.points`、`activityMetrics`、`currentWeather` 到 `call_llm` 参数。

如果需要前端在 `sync_track_context` 中补充当前轨迹聚合事实，必须新增测试确保这些字段只进入 `sync_track_context`，不进入 `requestActivityAdvice`。

### 7.3 Payload 测试

保持或增强 `tests/test_activity_advice_prompts.py`：

- `_activity_advice_payload(...)` 仍过滤 forbidden 字段。
- 临时 snapshot 中的 `source` 可进入 payload。
- `planned_start_time` 不从 snapshot 时间字段 fallback。

---

## 八、静态验收命令

旧风险预警不得回潮：

```bash
rg "REPORT_RISK_ASSESSMENT|__REPORT_RISK_ASSESSMENT__|build_risk_assessment|empty_risk_assessment|normalize_risk_assessment|_build_risk_assessment_messages|PY_REPORT_RISK_ASSESSMENT|requestRiskAssessment|buildRiskAssessmentHTML|resetRiskAssessmentState|currentRiskAssessment|risk-assessment|风险预警" main.py llm_backend.py track.html
rg "__REPORT_RISK_ASSESSMENT__|risk_assessment_contract|旧风险预警兼容名|待 cleanup 删除" docs/js_api_contract.json
```

活动建议链路存在：

```bash
rg "REPORT_ACTIVITY_ADVICE|_activity_advice_snapshot|activity_advice|build_activity_advice|normalize_activity_advice|empty_activity_advice|requestActivityAdvice" main.py llm_backend.py track.html tests docs/js_api_contract.json
```

前端生成建议不传事实 payload：

```bash
rg -n "function requestActivityAdvice|call_llm\\(PY_REPORT_ACTIVITY_ADVICE|appState\\.points|activityMetrics|currentWeather" track.html tests/test_activity_advice_frontend.py
```

---

## 九、回归命令

必须运行：

```bash
python3 -m unittest discover -s tests -p 'test_activity_advice_*.py'
python3 -m unittest discover -s tests -p 'test_response_envelope_contract.py'
python3 -m json.tool docs/js_api_contract.json >/tmp/js_api_contract_check.json
PYTHONPYCACHEPREFIX=/private/tmp python3 -m py_compile main.py llm_backend.py
```

建议运行：

```bash
python3 -m pytest tests/test_e2e_fatigue_review.py
python3 -m unittest discover -s tests -p 'test_fatigue_review_ai_preflight_p8.py'
```

如果本机 `node` 可用，检查 `track.html` 内联脚本：

```bash
node -e "const fs=require('fs'); const html=fs.readFileSync('track.html','utf8'); const scripts=[...html.matchAll(/<script[^>]*>([\\s\\S]*?)<\\/script>/gi)].map(m=>m[1]); for (const [i,script] of scripts.entries()) new Function(script); console.log('parsed scripts:', scripts.length);"
```

如果 `node` 不在 PATH，可使用项目 bundled Node。

---

## 十、人工验收步骤

完成代码修复后，按 `docs/activity_advice_manual_test_checklist.md` 补跑桌面端验收，至少覆盖：

1. 当前截图中的 19.19 km / 1118 m 爬升轨迹。
2. 一条 GPX 纯路线。
3. 一条 FIT / DB 活动路线。
4. 无活动类型 + 无计划活动时间。
5. 有活动类型 + 有计划活动时间。
6. 切换轨迹后旧建议清空。

通过标准：

- 生成建议不再显示“当前路线事实或用户计划信息不足”作为四个维度的主要内容。
- LLM 输出能引用路线事实，例如距离、爬升、海拔或位置。
- 无计划活动时间时，天气检查仍不伪造具体天气。
- 不出现旧「风险预警」。

---

## 十一、验收清单

- [ ] `Api` 新增活动建议专用内存快照。
- [ ] `sync_track_context(...)` 能为 DB 活动构建活动建议快照。
- [ ] `sync_track_context(...)` 能为无 `activity_id` 的当前轨迹构建临时路线快照。
- [ ] `call_llm(__REPORT_ACTIVITY_ADVICE__)` 使用活动建议快照，不再只依赖 `_ai_snapshot`。
- [ ] 临时快照不包含全量 `points[]` / `placemarks[]`。
- [ ] 临时快照不包含历史天气 / `_track_weather`。
- [ ] 临时快照不包含历史 `start_time` / `start_time_utc` / 点列 `time`。
- [ ] 前端 `requestActivityAdvice()` 仍只传 planning context。
- [ ] 无轨迹时仍返回 empty fallback。
- [ ] 切换轨迹时活动建议快照被覆盖。
- [ ] 活动建议结果仍不持久化。
- [ ] 旧风险预警无回潮。
- [ ] 自动化回归通过。
- [ ] 桌面端人工验收更新到 `docs/activity_advice_manual_test_checklist.md`。

---

## 十二、完成报告格式

完成本任务后，请输出：

```text
P5A 活动建议当前轨迹快照修复完成报告

1. 本次目标
2. 根因确认
3. 已更新文件
4. 修复方案
5. 契约约束落实情况
6. 测试结果
7. 人工验收结果
8. 未覆盖项 / 风险
9. 下一步建议
```

---

## 十三、下一任务建议

P5A 完成后，根据结果选择：

```text
P5B 活动建议验收冻结与发布说明
```

适用场景：

- 当前轨迹、GPX、FIT/DB 活动都能生成有效活动建议。
- 自动化回归全部通过。
- 人工验收无阻塞。

或：

```text
P5A-2 活动建议路线事实增强
```

适用场景：

- 临时轨迹可生成建议，但路线事实质量不足。
- 需要补充更准确的爬升、下降、坡度、最大连续爬升或地区信息。

P5A-2 仍必须遵守：

- 不写 canonical。
- 不把 points[] 送进 LLM。
- 不从历史时间推断计划时间。
- 不接入旧风险预警。
