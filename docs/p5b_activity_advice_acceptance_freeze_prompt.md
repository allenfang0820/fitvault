# P5B 活动建议验收冻结与发布说明提示词

> 任务类型：P5B 验收冻结 / 发布说明 / 人工验收闭环
> 适用范围：轨迹报告「活动建议」功能在 P0-P5A 完成后的最终验收、冻结记录与发布说明
> 前置条件：P0-P4 已完成；P5A 已修复当前展示轨迹 route facts 进入 OpenClaw / LLM 的链路
> 核心目标：不再扩大功能范围，在既有实现基础上完成桌面端人工验收、自动化回归复核、发布说明与冻结结论

---

## 零、架构契约核对

执行本任务前必须阅读并遵守：

- `docs/activity_advice_feature_design_v2.md`
- `docs/p1_activity_advice_backend_prompt.md`
- `docs/p2_activity_advice_frontend_prompt.md`
- `docs/p3_activity_advice_cleanup_prompt.md`
- `docs/p4_activity_advice_manual_acceptance_prompt.md`
- `docs/p5a_activity_advice_snapshot_fix_prompt.md`
- `docs/activity_advice_manual_test_checklist.md`
- `docs/js_api_contract.json`
- 当前实现：`main.py` / `llm_backend.py` / `track.html`
- 当前测试：`tests/test_activity_advice_prompts.py` / `tests/test_activity_advice_integration.py` / `tests/test_activity_advice_frontend.py` / `tests/test_activity_advice_cleanup.py`

本任务必须遵守以下强制契约：

- 活动建议只通过 `__REPORT_ACTIVITY_ADVICE__ -> { ok, activity_advice }`。
- 前端点击「生成建议」只能传用户显式 planning context：`user_activity_type` 与 `planned_start_time`。
- 前端不得把 `points[]`、`placemarks[]`、DOM 文本、UI 统计值、图表数据、`activityMetrics`、`currentWeather` 或前端 fallback 拼进 `call_llm` 参数。
- 后端活动建议只能消费 `_activity_advice_snapshot` 中的路线事实白名单 + 用户显式 planning context。
- `_activity_advice_snapshot` 不得包含全量 `points[]`、`placemarks[]`、历史天气、`_track_weather`、`weather_json`、`shadow_diff`、`diff`、历史 `start_time`、轨迹点 `time/timestamp`。
- `planned_start_time` 只能来自用户显式输入，不得从 FIT/GPX 历史时间、轨迹点时间或活动详情时间提取。
- 活动类型只能来自用户选择，不得从文件名、标题、设备、历史记录自动推断。
- 活动建议结果不持久化，不写 DB、不写 `localStorage` / `sessionStorage`、不进入 `ai_snapshots`、不进入普通 AI 教练 `_chat_messages`。
- 切换轨迹、导入新文件、切 Tab、离开 report 侧栏、重新生成建议时继续丢弃旧活动建议。
- KML 不作为本次版本目标，不计入 P5B 通过/阻塞条件。
- 旧「风险预警」生产链路不得回潮，不得恢复 `__REPORT_RISK_ASSESSMENT__`、`risk_assessment` 输出或旧 UI 文案。
- P5B 是验收冻结任务，不是功能增强任务；除非发现阻塞级缺陷，否则不要修改生产代码。

---

## 一、任务背景

P5A 已修复活动建议后端 route facts 来源缺失问题：

```text
用户点击生成建议
→ 前端只传 planning context
→ 后端使用当前轨迹对应的 _activity_advice_snapshot
→ DB 活动来自 Resolver truth 白名单
→ 无 activity_id 的当前 GPX/FIT 展示轨迹来自后端聚合临时 route facts
→ LLM 返回四类活动建议
→ 前端渲染活动建议
```

P5B 的目标不是继续改模型、改 UI 或增强路线事实，而是确认当前功能是否达到可冻结标准，并产出发布说明。

---

## 二、任务目标

完成以下事项：

1. 复核 P0-P5A 契约，确认无旧「风险预警」回潮。
2. 复跑活动建议相关自动化回归与必要关联回归。
3. 在桌面端执行真实点击验收，至少覆盖当前用户截图中的 19.19 km / 1118 m 爬升轨迹。
4. 覆盖纯 GPX、DB/FIT 活动、无活动类型/无计划时间、有活动类型/有计划时间等关键路径。
5. 验证真实 OpenClaw / LLM 输出是否引用路线事实，且不伪造天气、不引用历史时间。
6. 验证活动建议结果的阅后即焚生命周期。
7. 更新 `docs/activity_advice_manual_test_checklist.md` 的执行结果与冻结结论。
8. 新增发布说明文档，建议命名为 `docs/activity_advice_release_notes_p5b.md`。
9. 如果发现阻塞级缺陷，记录为 P5B blocker，并停止冻结，给出下一步修复任务建议。
10. 如果无阻塞级缺陷，给出 P5B 冻结通过结论。

---

## 三、本任务改动范围

默认只允许改文档：

- `docs/activity_advice_manual_test_checklist.md`
- `docs/activity_advice_release_notes_p5b.md`
- 如需要，可补充 `docs/js_api_contract.json` 中明显过时的说明文字，但不得改变接口契约

原则上不改：

- `main.py`
- `llm_backend.py`
- `track.html`
- 测试代码
- DB schema
- LLM prompt 主体

如发现必须修改生产代码：

- 先判断是否为阻塞级缺陷。
- 若是阻塞级缺陷，应停止 P5B 冻结，记录 blocker，并建议进入 `P5B-FIX` 或 `P5A-2`。
- 不要在 P5B 中顺手做功能增强、UI 优化、天气 API 接入、KML 支持或路线事实算法增强。

---

## 四、验收准备

### 4.1 自动化回归

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

### 4.2 旧风险预警回潮扫描

必须运行：

```bash
rg "REPORT_RISK_ASSESSMENT|__REPORT_RISK_ASSESSMENT__|build_risk_assessment|empty_risk_assessment|normalize_risk_assessment|_build_risk_assessment_messages|PY_REPORT_RISK_ASSESSMENT|requestRiskAssessment|buildRiskAssessmentHTML|resetRiskAssessmentState|currentRiskAssessment|risk-assessment|风险预警" main.py llm_backend.py track.html
rg "__REPORT_RISK_ASSESSMENT__|risk_assessment_contract|旧风险预警兼容名|待 cleanup 删除" docs/js_api_contract.json
```

预期：

- 两条命令均无匹配。
- `rg` 退出码 1 表示无匹配，视为通过。

### 4.3 活动建议链路扫描

必须运行：

```bash
rg "REPORT_ACTIVITY_ADVICE|_activity_advice_snapshot|activity_advice|build_activity_advice|normalize_activity_advice|empty_activity_advice|requestActivityAdvice" main.py llm_backend.py track.html tests docs/js_api_contract.json
```

预期：

- 活动建议链路存在。
- `requestActivityAdvice()` 仍只传 planning context。
- 后端活动建议分支使用 `_activity_advice_snapshot`。

---

## 五、桌面端人工验收矩阵

人工验收必须记录到 `docs/activity_advice_manual_test_checklist.md`。

### 5.1 路线样例

至少覆盖：

| 用例 ID | 路线类型 | 推荐样例 | 必须验证 |
|---|---|---|---|
| P5B-RT-01 | 当前截图路线 | 当前 19.19 km / 1118 m 爬升 / 1019 m 最高海拔轨迹 | 点击生成后不再空态，输出能引用路线事实 |
| P5B-RT-02 | 纯 GPX 路线 | `local_tracks/COURSE_443798.gpx` 或其他 GPX | 无 DB `activity_id` 时仍可生成路线准备建议 |
| P5B-RT-03 | DB/FIT 活动 | `local_tracks/240827212_ACTIVITY_1.fit` 或运动中心活动 | 使用 DB / Resolver truth 白名单 |
| P5B-RT-04 | 短路线 | `local_tracks/test_naive.gpx` | 不夸大补给、装备和体力压力 |
| P5B-RT-05 | 高爬升路线 | 从现有 FIT/GPX 中人工确认 | 装备和体力安排体现爬升/海拔压力 |

KML 不验收、不阻塞本版本。

### 5.2 输入组合

至少覆盖：

| 用例 ID | 活动类型 | 计划活动时间 | 必须验证 |
|---|---|---|---|
| P5B-IN-01 | 空 | 空 | 不推断活动类型；天气检查为信息不足或检查清单 |
| P5B-IN-02 | 徒步 / hiking | 空 | 可按徒步语境建议；天气仍不伪造具体天气 |
| P5B-IN-03 | 空 | 用户显式未来时间 | 可引用用户填写计划时间；不推断活动类型 |
| P5B-IN-04 | 越野跑 / trail_running | 用户显式未来时间 | 可结合活动类型和计划时间组织建议 |

### 5.3 输出质量判断

每次真实 LLM 输出都要检查：

- 是否包含四个维度：补给建议、天气检查、装备建议、体力安排。
- 是否引用路线事实，例如距离、爬升、海拔、起点区域或路线压力。
- 未填写计划活动时间时，是否没有确定性天气判断。
- 是否没有引用 FIT / GPX 历史开始时间。
- 是否没有出现「风险预警」「高风险」「危险等级」等旧语义。
- 是否没有医学诊断、安全保证或确定性天气预报。
- 是否没有把建议结果写入普通 AI 教练聊天。

### 5.4 生命周期检查

至少覆盖：

- 生成活动建议后切换主 Tab，旧建议清空。
- 生成活动建议后离开 report 侧栏，旧建议清空。
- 生成活动建议后导入新 GPX/FIT，旧建议清空。
- 生成活动建议后切换另一条轨迹，旧建议清空。
- 同一轨迹重新点击生成，旧建议先清空，再显示新结果。
- 刷新页面或重启应用后，不保留旧建议。
- `localStorage` / `sessionStorage` 不出现活动建议结果。

---

## 六、冻结通过标准

全部满足才可给出 P5B 冻结通过：

- 自动化回归通过。
- 旧风险预警扫描无匹配。
- 活动建议链路扫描符合契约。
- 当前 19.19 km / 1118 m 爬升轨迹真实点击不再返回空态。
- 纯 GPX 与 DB/FIT 活动均能生成活动建议。
- 未填写计划时间时，天气检查不伪造具体天气。
- 不从历史时间推断计划活动时间。
- 不从文件名、标题、设备、历史记录推断活动类型。
- 活动建议结果不持久化。
- 切换轨迹、导入新文件、切 Tab、离开 report 侧栏、重新生成建议时旧建议被丢弃。
- 不出现旧「风险预警」UI、字段、sentinel 或文案。
- 发布说明已落档。

---

## 七、阻塞级缺陷定义

出现以下任一情况，不得冻结：

- 点击「生成建议」仍返回“请先加载活动轨迹”，但页面已有有效轨迹事实。
- 纯 GPX 路线无法生成活动建议，且不是 LLM 配置缺失或网络问题。
- `requestActivityAdvice()` 向 `call_llm` 传入 `points[]`、`activityMetrics`、`currentWeather`、DOM 文本或前端拼 prompt。
- LLM prompt 或 payload 中出现历史 `start_time`、`weather_json`、`points[]`、`placemarks[]`。
- 活动建议结果写入 DB、`localStorage`、`sessionStorage`、`ai_snapshots` 或普通 AI 教练 `_chat_messages`。
- 旧 `__REPORT_RISK_ASSESSMENT__` 或 `risk_assessment` 生产链路回潮。
- 旧 UI 文案「风险预警」回潮。
- 无计划活动时间时，系统稳定输出确定性天气判断且无法通过 prompt/normalizer 约束解释。

阻塞处理：

```text
停止 P5B 冻结
记录 blocker 到 docs/activity_advice_manual_test_checklist.md
给出下一修复任务建议
不要发布“冻结通过”
```

---

## 八、发布说明文档要求

新增 `docs/activity_advice_release_notes_p5b.md`，建议包含：

```text
# 活动建议 P5B 发布说明

## 发布范围
## 用户可见变化
## 数据与 AI 输入边界
## 已移除 / 不再支持
## 非目标范围
## 验收结果
## 已知限制
## 回滚 / 降级策略
## 后续建议
```

发布说明必须明确：

- 「活动建议」替代旧「风险预警」。
- 活动建议只做路线准备建议，不做安全保证、天气预报或医学判断。
- 活动类型和计划时间为可选，且只来自用户显式输入。
- 未填写计划时间时，天气部分只做检查清单，不判断具体天气。
- GPX 纯路线可基于路线事实生成建议。
- 活动建议结果不持久化。
- KML 不作为本次版本目标。
- 旧风险预警生产链路已删除。

---

## 九、验收记录更新要求

更新 `docs/activity_advice_manual_test_checklist.md`：

- 将状态改为以下二选一：

```text
状态：P5B 冻结通过
```

或：

```text
状态：P5B 冻结阻塞
```

- 补充桌面端真实点击结果。
- 补充真实 LLM 输出质量判断。
- 补充自动化回归最新结果。
- 补充旧风险预警扫描结果。
- 补充未覆盖项与残余风险。
- 给出是否允许进入发布冻结的结论。

如果无法执行真实桌面端点击：

- 不得标记冻结通过。
- 必须标记为“冻结阻塞 / 待人工点击”。
- 说明阻塞原因，例如未启动桌面端、LLM 配置缺失、网络不可达、用户未提供样例等。

---

## 十、完成报告格式

完成本任务后，请输出：

```text
P5B 活动建议验收冻结与发布说明完成报告

1. 本次目标
2. 执行范围
3. 自动化回归结果
4. 人工验收结果
5. 发布说明文件
6. 契约约束落实情况
7. 冻结结论
8. 未覆盖项 / 风险
9. 下一步建议
```

---

## 十一、下一任务建议

如果 P5B 冻结通过，下一任务建议：

```text
P6 活动建议发布后观察与反馈收集
```

目标：

- 收集真实用户路线建议质量反馈。
- 记录 GPX / FIT / 不同活动类型的输出质量。
- 不立即扩大功能范围，先观察建议是否稳定、是否有越界表达。

如果 P5B 因 route facts 质量不足而阻塞，下一任务建议：

```text
P5A-2 活动建议路线事实增强
```

适用场景：

- 临时 GPX 能生成建议，但距离、爬升、海拔或区域事实质量不足。
- 需要补充更准确的爬升、下降、坡度、最大连续爬升或地区信息。

如果 P5B 因真实 LLM 输出越界而阻塞，下一任务建议：

```text
P5C 活动建议 Prompt 与 Normalizer 质量闸门
```

适用场景：

- LLM 引用历史时间、伪造具体天气、输出旧风险语义或医学/安全保证。
- 需要增强 prompt 约束、normalizer 降级策略或输出质量门禁。

所有后续任务仍必须遵守：

- 不恢复旧风险预警。
- 不把 points[] 送进 LLM。
- 不从历史时间推断计划时间。
- 不把活动建议结果持久化。
- KML 不作为当前版本目标。
