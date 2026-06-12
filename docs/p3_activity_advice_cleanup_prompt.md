# P3 旧风险预警 Cleanup 与端到端回归提示词

> 任务类型：P3 旧链路清理 / 契约收口 / 回归验证
> 适用范围：旧「风险预警」后端兼容链路、旧 schema / prompt / normalizer、契约文档、静态测试与关键回归
> 前置条件：P0 活动建议契约已固化，P1 后端 `__REPORT_ACTIVITY_ADVICE__` 已实现，P2 前端「活动建议」UI 已接入
> 核心目标：删除旧 `__REPORT_RISK_ASSESSMENT__` 生产链路和残留垃圾代码，确保系统只保留「活动建议」作为当前轨迹报告建议功能

---

## 零、架构契约核对

执行本任务前必须阅读并遵守：

- `docs/activity_advice_feature_design_v2.md`
- `docs/p0_activity_advice_contract_prompt.md`
- `docs/p1_activity_advice_backend_prompt.md`
- `docs/p2_activity_advice_frontend_prompt.md`
- `docs/js_api_contract.json`
- 当前生产实现：`main.py` / `llm_backend.py` / `track.html`
- 当前活动建议测试：`tests/test_activity_advice_prompts.py` / `tests/test_activity_advice_integration.py` / `tests/test_activity_advice_frontend.py`

本任务必须遵守以下强制契约：

- 当前功能名称只能是「活动建议」，旧「风险预警」不得作为生产功能继续存在。
- 生产代码不得继续暴露或处理 `__REPORT_RISK_ASSESSMENT__`。
- 生产代码不得继续返回 `risk_assessment` 作为轨迹报告建议结果。
- 新活动建议链路必须继续使用 `__REPORT_ACTIVITY_ADVICE__ -> { ok, activity_advice }`。
- 活动建议结果不持久化，不写 DB，不进入 `ai_snapshots`，不进入普通 AI 教练 `_chat_messages`。
- 活动建议输入仍只能来自后端路线事实白名单 + 用户显式 planning context。
- `planned_start_time` 仍只能来自用户显式输入，不得从 FIT/GPX 历史 `start_time`、`start_time_utc`、轨迹点时间或活动详情时间提取。
- 未填写计划活动时间时，天气相关输出必须表达信息不足或检查清单，不得使用历史天气伪造判断。
- 本任务是 cleanup，不重写活动建议产品形态，不新增天气 API，不新增 DB 字段，不做大规模视觉重构。

---

## 一、任务背景

P0/P1/P2 已完成「风险预警」到「活动建议」的主要迁移：

```text
旧链路：__REPORT_RISK_ASSESSMENT__ -> { ok, risk_assessment }
新链路：__REPORT_ACTIVITY_ADVICE__ -> { ok, activity_advice }
```

P2 完成后，前端生产 UI 已不再调用旧 risk 链路。但后端仍保留旧兼容分支和旧 prompt/normalizer，契约文档里也仍有 deprecated 说明。

P3 的目标是把旧兼容链路正式退场，避免未来出现三类问题：

1. 新旧 sentinel 并存，导致调用方误用旧 `__REPORT_RISK_ASSESSMENT__`。
2. 旧 `risk_assessment` schema 与新 `activity_advice` schema 混杂，污染测试和契约。
3. 旧「风险预警」语义继续暗示系统有确定性安全预警能力，超出当前数据资产边界。

---

## 二、任务目标

完成 P3 cleanup：

1. 删除 `main.py` 中旧 `REPORT_RISK_ASSESSMENT` 常量。
2. 删除 `Api.call_llm` 中旧 `__REPORT_RISK_ASSESSMENT__` 分支。
3. 删除 `main.py` 中旧 `_build_risk_assessment_messages(...)`。
4. 删除 `llm_backend.py` 中旧风险预警 schema / payload / prompt / empty / normalizer。
5. 更新 `docs/js_api_contract.json`，移除旧 `__REPORT_RISK_ASSESSMENT__` 作为可调用能力的描述。
6. 更新或新增静态测试，确保生产代码无旧风险命名。
7. 调整现有测试中对旧 risk sentinel 的引用，只允许在历史文档或“已删除断言”中出现。
8. 跑活动建议 P1/P2 测试和关键 AI sentinel 回归测试。

---

## 三、本任务改动范围

建议改动文件：

- `main.py`
- `llm_backend.py`
- `docs/js_api_contract.json`
- `tests/test_activity_advice_prompts.py`
- `tests/test_activity_advice_integration.py`
- `tests/test_activity_advice_frontend.py`
- 可新增：`tests/test_activity_advice_cleanup.py`
- 如有必要：`tests/test_e2e_fatigue_review.py`
- 如有必要：`tests/test_response_envelope_contract.py`

允许保留旧词的位置：

- `docs/risk_warning_feature_design_v1.md`
- `docs/p0_activity_advice_contract_prompt.md`
- `docs/p1_activity_advice_backend_prompt.md`
- `docs/p2_activity_advice_frontend_prompt.md`
- `docs/activity_advice_feature_design_v2.md` 中的历史背景、退场清单和迁移说明
- 新增 cleanup 测试中用于断言旧命名不存在的字符串

本任务禁止改动：

- 不删除 `__REPORT_ACTIVITY_ADVICE__`。
- 不改变活动建议输出 schema。
- 不把旧 risk 逻辑包一层重命名为 activity advice。
- 不把活动建议结果写入 DB、`localStorage`、`sessionStorage` 或 `ai_snapshots`。
- 不让活动建议消费 `_track_weather`、历史天气、历史 `start_time`、`points[]`、`placemarks[]`、`shadow_diff`。
- 不把普通聊天、雷达洞察、复盘洞察的 sentinel 合并或复用。

---

## 四、生产代码清理清单

### 4.1 `main.py`

删除以下旧风险预警生产代码：

```text
REPORT_RISK_ASSESSMENT = "__REPORT_RISK_ASSESSMENT__"
_build_risk_assessment_messages(...)
if prompt == self.REPORT_RISK_ASSESSMENT:
    ...
```

删除后必须确认：

- `Api.call_llm` 仍正常处理普通聊天。
- `Api.call_llm` 仍正常处理 `REPORT_ACTIVITY_ADVICE`。
- `Api.call_llm` 仍正常处理 `REPORT_INSIGHT`、`RADAR_INSIGHT`、`FATIGUE_REVIEW_INSIGHT`。
- 删除旧分支不会破坏 `_chat_messages` 隔离策略。
- 未知 prompt 仍按原普通聊天逻辑处理，除非现有架构已有更严格的 sentinel guard。

### 4.2 `llm_backend.py`

删除以下旧风险预警生产代码：

```text
RISK_ASSESSMENT_OUTPUT_SCHEMA
_risk_snapshot_payload
build_risk_assessment_system_prompt
build_risk_assessment_user_prompt
empty_risk_assessment
normalize_risk_assessment_json
```

如果当前文件没有 `RISK_ASSESSMENT_OUTPUT_SCHEMA` 或 `_risk_snapshot_payload`，静态检查应确认它们不存在即可，不要为了删除而新增。

删除后必须确认：

- `ACTIVITY_ADVICE_OUTPUT_SCHEMA` 仍存在。
- `_activity_advice_payload(...)` 仍只输出活动建议白名单字段。
- `build_activity_advice_system_prompt(...)` 仍明确禁止历史时间、历史天气和前端推导事实。
- `empty_activity_advice(...)` / `normalize_activity_advice_json(...)` 仍正常工作。

### 4.3 `track.html`

P2 已完成前端清理，本任务只做复核：

```bash
rg "PY_REPORT_RISK_ASSESSMENT|requestRiskAssessment|buildRiskAssessmentHTML|resetRiskAssessmentState|currentRiskAssessment|risk-assessment|风险预警" track.html
```

预期：无匹配。

如发现旧前端残留，删除它们；但不要借 P3 做新的 UI 重构。

---

## 五、契约文档更新

### 5.1 `docs/js_api_contract.json`

更新 `call_llm` 返回说明：

旧描述中类似：

```text
__REPORT_RISK_ASSESSMENT__ 已废弃(旧风险预警兼容名,待 cleanup 删除)
```

应改为：

```text
旧 __REPORT_RISK_ASSESSMENT__ 生产链路已删除；轨迹报告建议功能只支持 __REPORT_ACTIVITY_ADVICE__ -> { ok, activity_advice }
```

同时更新 `architectural_constraints`：

- 保留 `activity_advice_contract`。
- 删除 `risk_assessment_contract`，或改为 `removed_legacy_contracts` 之类的历史说明。
- 不再把 `__REPORT_RISK_ASSESSMENT__` 描述为可调用兼容名。

### 5.2 历史文档

历史设计文档允许保留旧命名，但必须语义清晰：

- `docs/risk_warning_feature_design_v1.md` 保持废弃声明。
- P0/P1/P2 prompt 中的旧命名是历史迁移上下文，可以保留。
- 不需要为了让全仓 `rg` 零命中而改写历史文档。

---

## 六、测试任务

### 6.1 新增 cleanup 静态测试

建议新增：

```text
tests/test_activity_advice_cleanup.py
```

测试目标：

- `main.py` 不包含 `REPORT_RISK_ASSESSMENT`。
- `main.py` 不包含 `__REPORT_RISK_ASSESSMENT__`。
- `main.py` 不包含 `_build_risk_assessment_messages`。
- `main.py` 不包含 `risk_assessment` 作为旧分支返回字段。
- `llm_backend.py` 不包含 `build_risk_assessment_system_prompt`。
- `llm_backend.py` 不包含 `build_risk_assessment_user_prompt`。
- `llm_backend.py` 不包含 `empty_risk_assessment`。
- `llm_backend.py` 不包含 `normalize_risk_assessment_json`。
- `track.html` 不包含旧 risk 前端符号。
- `docs/js_api_contract.json` 不把 `__REPORT_RISK_ASSESSMENT__` 描述为仍可调用的兼容 sentinel。
- `__REPORT_ACTIVITY_ADVICE__`、`activity_advice`、`build_activity_advice_system_prompt`、`requestActivityAdvice` 仍存在。

注意：cleanup 测试自身会包含旧字符串用于断言，因此静态扫描生产文件和契约文件时要限定路径，不要误扫测试文件本身。

### 6.2 调整旧测试引用

检查并处理：

```bash
rg "REPORT_RISK_ASSESSMENT|__REPORT_RISK_ASSESSMENT__|risk_assessment|empty_risk_assessment|normalize_risk_assessment" tests
```

处理原则：

- 如果测试是在验证旧风险分支还能工作，应删除或改为验证旧分支已不存在。
- 如果测试是响应 envelope 对任意旧字段的兼容示例，优先改成非业务字段或新 `activity_advice` 示例。
- 如果 E2E / preflight 测试只是枚举 sentinel，删除旧 sentinel，保留新活动建议 sentinel 与其他有效 sentinel。

### 6.3 保留活动建议测试

必须继续通过：

```bash
python3 -m unittest discover -s tests -p 'test_activity_advice_*.py'
```

覆盖内容应继续包括：

- payload 禁止历史 `start_time` / `start_time_utc`。
- payload 禁止历史天气 / `_track_weather`。
- payload 禁止 `points[]` / `placemarks[]` / `shadow_diff`。
- happy path 返回 `{ ok: True, activity_advice: ... }`。
- 无 `_ai_snapshot` 返回 `empty_activity_advice("请先加载活动轨迹")`。
- LLM 异常返回 `empty_activity_advice(error)`。
- 前端只传 `user_activity_type` 和 `planned_start_time`。
- 前端活动建议状态为阅后即焚。

---

## 七、静态验收命令

### 7.1 生产代码旧风险命名扫描

```bash
rg "REPORT_RISK_ASSESSMENT|__REPORT_RISK_ASSESSMENT__|build_risk_assessment|empty_risk_assessment|normalize_risk_assessment|_build_risk_assessment_messages|PY_REPORT_RISK_ASSESSMENT|requestRiskAssessment|buildRiskAssessmentHTML|resetRiskAssessmentState|currentRiskAssessment|risk-assessment|风险预警" main.py llm_backend.py track.html
```

预期：无匹配。

### 7.2 契约文件扫描

```bash
rg "__REPORT_RISK_ASSESSMENT__|risk_assessment_contract|旧风险预警兼容名|待 cleanup 删除" docs/js_api_contract.json
```

预期：不再出现“仍可调用兼容名”或“待 cleanup 删除”的描述。

允许出现“已删除”类历史说明，但建议尽量让 `docs/js_api_contract.json` 不再包含旧 sentinel 字符串，避免误导调用方。

### 7.3 新活动建议链路扫描

```bash
rg "REPORT_ACTIVITY_ADVICE|__REPORT_ACTIVITY_ADVICE__|activity_advice|build_activity_advice|normalize_activity_advice|empty_activity_advice|requestActivityAdvice" main.py llm_backend.py track.html tests docs/js_api_contract.json
```

预期：

- 新活动建议后端、前端、测试、契约均存在。
- 旧 risk 生产链路删除后，新链路不受影响。

---

## 八、回归验证命令

必须运行：

```bash
python3 -m unittest discover -s tests -p 'test_activity_advice_*.py'
python3 -m unittest discover -s tests -p 'test_response_envelope_contract.py'
python3 -m json.tool docs/js_api_contract.json >/tmp/js_api_contract_check.json
PYTHONPYCACHEPREFIX=/private/tmp python3 -m py_compile main.py llm_backend.py
```

建议运行：

```bash
python3 -m unittest discover -s tests -p 'test_e2e_fatigue_review.py'
python3 -m unittest discover -s tests -p 'test_fatigue_review_ai_preflight_p8.py'
```

如果本机 `node` 可用，建议检查 `track.html` 内联脚本语法：

```bash
node -e "const fs=require('fs'); const html=fs.readFileSync('track.html','utf8'); const scripts=[...html.matchAll(/<script[^>]*>([\\s\\S]*?)<\\/script>/gi)].map(m=>m[1]); for (const [i,script] of scripts.entries()) new Function(script); console.log('parsed scripts:', scripts.length);"
```

如果 `node` 不在 PATH，可使用项目 bundled Node，路径以当前环境为准。

---

## 九、验收清单

- [ ] `main.py` 已删除 `REPORT_RISK_ASSESSMENT`。
- [ ] `main.py` 已删除旧 `__REPORT_RISK_ASSESSMENT__` 分支。
- [ ] `main.py` 已删除 `_build_risk_assessment_messages(...)`。
- [ ] `llm_backend.py` 已删除旧风险预警 prompt / empty / normalizer / schema。
- [ ] `track.html` 无旧风险预警前端符号。
- [ ] `docs/js_api_contract.json` 不再把旧 sentinel 描述为兼容可调用能力。
- [ ] 测试不再要求旧风险链路可用。
- [ ] 新增或更新 cleanup 静态测试。
- [ ] 活动建议 P1/P2 测试全部通过。
- [ ] 响应 envelope 回归通过。
- [ ] `main.py` / `llm_backend.py` 编译通过。
- [ ] 活动建议仍满足：不持久化、不使用历史 start time、不使用历史天气、不进入普通聊天会话。

---

## 十、完成报告格式

完成本任务后，请输出：

```text
P3 旧风险预警 Cleanup 与端到端回归完成报告

1. 本次目标
2. 已删除旧链路
3. 已更新文件
4. 契约约束落实情况
5. 静态扫描结果
6. 测试结果
7. 已知限制或保留的历史文档命中
8. 下一步建议
```

---

## 十一、下一任务建议

P3 完成后建议进入：

```text
P4 活动建议人工验收与边界样例回归
```

P4 目标：

- 使用真实 FIT / GPX / KML 样例做桌面端人工验收。
- 覆盖无计划时间、有计划时间、无活动类型、有活动类型四类输入组合。
- 覆盖纯 GPX 路线、DB 活动路线、高爬升路线、短距离路线、无海拔路线。
- 验证天气建议在无计划时间时不伪造天气判断。
- 验证切换轨迹、导入新文件、切 Tab、离开 report 侧栏、重新生成时活动建议立即丢弃。
- 记录最终人工验收清单到 `docs/activity_advice_manual_test_checklist.md`。
