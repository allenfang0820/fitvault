# 轨迹报告「风险预警」功能调研与设计方案 v1

> **废弃声明(2026-06-10)**: 本方案已被 [activity_advice_feature_design_v2.md](./activity_advice_feature_design_v2.md) 替代。功能语义从「风险预警」调整为「活动建议」,计划活动时间只允许来自用户显式输入,不得从 FIT/GPX 历史 `start_time` 或历史天气推断。

> **状态**: 已废弃,仅作历史调研记录
> **Workspace**: /Users/fanglei/应用开发/AI track
> **契约基线**: fit-arch-contrac §5.5 轨迹报告 v3 边界 / §5.6 AI 洞察功能开发标准流程
> **调研日期**: 2026-06-09
> **版本**: v1.1(2026-06-09 新增 §11 维度与数据源评审)
> **调研范围**: 已实现 sentinel `__REPORT_RISK_ASSESSMENT__` / prompt builder / normalizer / 前端面板 / **数据源覆盖度**

---

## 0. 调研结论一句话

风险预警的 **sentinel、后端 prompt、normalizer、前端面板均已落地**,但**与 `fit-arch-contrac` §5.6 的 7 条铁律存在 4 处契约偏离**,且**没有任何针对性测试**。建议按本文 P0-N / P1-N / P2-N 任务清单做一轮回正即可,不需要推倒重来。

---

## 1. 现状盘点(对照代码)

### 1.1 现有实现总览

| 层 | 文件 | 行号 | 状态 |
|---|---|---|---|
| 后端 sentinel 常量 | [main.py](file:///Users/fanglei/应用开发/AI%20track/main.py) | L3565 | ✅ `REPORT_RISK_ASSESSMENT = "__REPORT_RISK_ASSESSMENT__"` |
| 后端 call_llm 分支 | [main.py](file:///Users/fanglei/应用开发/AI%20track/main.py) | L4063-L4078 | ⚠️ 已实现,但 §5.6 规则 4 入口清空缺失 |
| 后端 messages 构建器 | [main.py](file:///Users/fanglei/应用开发/AI%20track/main.py) | L3497-L3507 | ✅ 已实现 |
| 后端 output schema | [llm_backend.py](file:///Users/fanglei/应用开发/AI%20track/llm_backend.py) | L419-L425 | ✅ 4 维度 + disclaimer |
| 后端 snapshot 白名单 | [llm_backend.py](file:///Users/fanglei/应用开发/AI%20track/llm_backend.py) | L428-L446 | ✅ `_risk_snapshot_payload` 白名单过滤 |
| 后端 system prompt | [llm_backend.py](file:///Users/fanglei/应用开发/AI%20track/llm_backend.py) | L449-L484 | ✅ DATA BOUNDARY + MUST NOT |
| 后端 user prompt | [llm_backend.py](file:///Users/fanglei/应用开发/AI%20track/llm_backend.py) | L487-L488 | ✅ |
| 后端 empty_risk_assessment | [llm_backend.py](file:///Users/fanglei/应用开发/AI%20track/llm_backend.py) | L491-L500 | ✅ 4 维度默认值 + error |
| 后端 normalizer | [llm_backend.py](file:///Users/fanglei/应用开发/AI%20track/llm_backend.py) | L518-L544 | ✅ 永不抛异常 |
| 前端 panel 入口 HTML | [track.html](file:///Users/fanglei/应用开发/AI%20track/track.html) | L9929-L9932 | ✅ `buildAIReportHTML` 内 |
| 前端渲染函数 | [track.html](file:///Users/fanglei/应用开发/AI%20track/track.html) | L9858-L9881 | ✅ `buildRiskAssessmentHTML` |
| 前端 async 入口 | [track.html](file:///Users/fanglei/应用开发/AI%20track/track.html) | L9995-L10043 | ⚠️ 已实现,但 §5.6 规则 5 阅后即焚缺位 |
| 前端 reset 函数 | [track.html](file:///Users/fanglei/应用开发/AI%20track/track.html) | L9883-L9891 | ⚠️ 已实现,但只在 `applyDataAndRender` 中调用 |
| 前端 sentinel 常量 | [track.html](file:///Users/fanglei/应用开发/AI%20track/track.html) | L4816 | ✅ `PY_REPORT_RISK_ASSESSMENT` |
| API 契约登记 | [js_api_contract.json](file:///Users/fanglei/应用开发/AI%20track/docs/js_api_contract.json) | L190, L710 | ✅ |
| 测试 | — | — | ❌ 无 |

### 1.2 4 维度领域知识(已沉淀)

风险预警输出为固定 4 维度,每维度返回 `{level, advice}`:

| 维度 | 含义 | 关键判据 |
|---|---|---|
| 🎒 补给风险 | 水、能量、盐丸、电解质、低血糖、脱水 | 时长、距离、强度、天气 |
| 🌦️ 天气风险 | 温度、湿度、风、雨、低温、暴晒 | `weather_context.temperature_c / humidity / wind_speed_kmh / weather_label` |
| 🎽 装备风险 | 防雨、防晒、头灯、急救包、保暖、防滑、路线装备 | 时长、海拔跨度、天气、夜间 |
| 💪 体力风险 | 爬升压力、运动时长、心率压力、节奏控制、后程衰减 | `gain_m / duration_sec / avg_hr / max_hr / difficulty_score` |

等级仅 3 档:`低 / 中 / 高` (见 [llm_backend.py L503-L505](file:///Users/fanglei/应用开发/AI%20track/llm_backend.py#L503-L505))。

---

## 2. §5.6 7 条铁律审计

| # | 铁律 | 现状 | 是否偏离 |
|---|---|---|---|
| 1 | 独立 sentinel | `__REPORT_RISK_ASSESSMENT__` 与雷达/复盘 sentinel 不复用 | ✅ 合规 |
| 2 | 前端只传控制参数 | 前端传 `appState.sportType \|\| 'general'`,但后端实际忽略此参数(直接读 `self._ai_snapshot`) | ⚠️ **轻微偏离**:控制参数语义不清,后端实际不消费。建议改成传 `activity_id` 或固定 `'report'` 让意图显式 |
| 3 | 后端从 `_ai_snapshot` 构建 | 使用 `self._ai_snapshot` + `self._track_weather`,经 `_risk_snapshot_payload` 白名单过滤 | ✅ 合规 |
| 4 | sentinel 入口清空 + 刷新 | `_chat_messages = []` 与 `_new_session_id()` 在 LLM 调用 **之后** 执行;`_ai_snapshot` 缺失早返回路径未清空;LLM 异常路径未清空 | ❌ **偏离** |
| 5 | 阅后即焚 3 触发点 | `resetRiskAssessmentState()` 仅在 `applyDataAndRender` 中调用;**`switchTab` / `switchSidebarTab` / 切 sport 都不调用** | ❌ **偏离** |
| 6 | 严禁写 DB | 全流程只读 `_ai_snapshot` + `_track_weather`;normalizer 不写 DB | ✅ 合规 |
| 7 | 错误用 `empty_xxx_insight` | `empty_risk_assessment(error)` 全覆盖;`normalize_risk_assessment_json` 永不抛异常 | ✅ 合规 |

**总结**:7 条铁律中,2 条严重偏离(规则 4、5),1 条轻微偏离(规则 2),需回正;其余 4 条已合规。

---

## 3. 核心偏离的具体修复方案

### 3.1 §5.6 规则 4 — sentinel 入口清空(必修)

**问题代码**([main.py L4063-L4078](file:///Users/fanglei/应用开发/AI%20track/main.py#L4063-L4078)):

```python
if prompt == self.REPORT_RISK_ASSESSMENT:
    if not self._ai_snapshot:
        return {"ok": True, "risk_assessment": llm_backend.empty_risk_assessment("请先加载活动轨迹")}
    messages = _build_risk_assessment_messages(self._ai_snapshot, self._track_weather)
    text = llm_backend.chat_completions(...)
    self._chat_messages = []   # ← 错误:放在 LLM 调用之后
    self._new_session_id()
    risk_assessment = llm_backend.normalize_risk_assessment_json(text)
    return {"ok": True, "risk_assessment": risk_assessment}
```

**偏离后果**:
- `_ai_snapshot` 缺失时早返回 → AI 教练会话不被清空 → 用户后续问 AI 教练时,旧 session 残留。
- LLM 网关异常(超时/401/500)时 `chat_completions` 抛异常 → 走外层 `except` → 会话未清空 → 同上。

**参考实现**([main.py L4080-L4110](file:///Users/fanglei/应用开发/AI%20track/main.py#L4080-L4110),`RADAR_INSIGHT` 分支):

```python
if prompt == self.RADAR_INSIGHT:
    # §5.4 规则 5:洞察调用后清空 + 刷新 session,避免污染 AI 教练会话
    # 必须在所有分支(happy / 降级)前执行,否则降级路径会留下旧 session
    self._chat_messages = []
    self._new_session_id()

    if not sport_type:
        return {"ok": True, "radar_insight": llm_backend.empty_radar_insight("请先选择运动类型")}
    ...
```

**修复目标代码**(P0-N-1 产物):

```python
if prompt == self.REPORT_RISK_ASSESSMENT:
    # §5.6 规则 4:入口清空 + 刷新,必须在所有分支(happy / 降级)前执行
    self._chat_messages = []
    self._new_session_id()

    if not self._ai_snapshot:
        return {"ok": True, "risk_assessment": llm_backend.empty_risk_assessment("请先加载活动轨迹")}
    messages = _build_risk_assessment_messages(self._ai_snapshot, self._track_weather)
    try:
        text = llm_backend.chat_completions(
            url=url, api_key=api_key, model=model,
            messages=messages, session_id=sid, agent_id=agent_id,
        )
    except Exception as exc:
        # §5.6 规则 7:任何失败用 empty_risk_assessment,不抛到前端
        return {"ok": True, "risk_assessment": llm_backend.empty_risk_assessment(f"LLM 调用失败: {exc}")}
    risk_assessment = llm_backend.normalize_risk_assessment_json(text)
    return {"ok": True, "risk_assessment": risk_assessment}
```

### 3.2 §5.6 规则 5 — 阅后即焚 3 触发点(必修)

**问题盘点**:
| 触发点 | 是否清空 | 代码位置 |
|---|---|---|
| ① 切 Tab | ❌ | [switchTab L5736-L5741](file:///Users/fanglei/应用开发/AI%20track/track.html#L5736-L5741) 只调 `_clearRadarInsight` / `_clearFatigueReviewInsight`,未调 `resetRiskAssessmentState` |
| ② 切 sport/state(报告本身) | ❌ | `applyDataAndRender` L10283 已调,但仅在重新加载轨迹时触发;用户在已加载报告上切换运动类型/sidebar tab 不会触发 |
| ③ 重新点击 | ⚠️ 部分 | `requestRiskAssessment` L9995 的 spinner 覆盖会替换 DOM,但 `appState.currentRiskAssessment` 在请求发起瞬间仍是旧值,会闪烁 |

**修复目标**(P1-N-5 / P1-N-6 产物):

```javascript
// 1. switchTab 末尾追加(参照 _clearFatigueReviewInsight 写法)
function switchTab(tabBtn) {
    ...
    _clearRadarInsight();
    _clearFatigueReviewInsight();
    resetRiskAssessmentState();   // ← 新增
}

// 2. switchSidebarTab 末尾追加
function switchSidebarTab(tab, btn) {
    ...
    if (tab !== 'report') resetRiskAssessmentState();   // ← 新增:离开报告 tab 时清
}

// 3. requestRiskAssessment 入口立即清,避免闪烁
async function requestRiskAssessment() {
    if (appState.riskAssessmentLoading) return;
    if (!window.pywebview || ...) { showToast(...); return; }
    if (!currentLLMConfig.url) { showToast(...); return; }

    // §5.6 规则 5 触发点 ③:重新点击立即清空旧结果
    appState.currentRiskAssessment = null;
    appState.riskAssessmentLoading = true;
    ...
}
```

### 3.3 §5.6 规则 2 — 控制参数语义(建议修)

**问题**:前端传 `appState.sportType || 'general'`,但后端 main.py 与 llm_backend.py 都不消费第二参数(都依赖 `self._ai_snapshot`)。语义上违反"前端只传控制参数"的精神。

**修复方向**(二选一):
- **A 路线**:前端改为传固定字符串 `'report'`,语义显式,后端加 guard(若第二参数不为 `'report'` 返回 empty_risk_assessment("非法调用"))。
- **B 路线**:前端传 `appState.activityId`(若已加载),后端用 `activity_id` 校验是否与 `self._ai_snapshot` 中的 activity_id 一致,不匹配则拒绝并返回 empty。

**推荐 A 路线**:改动最小,语义最清晰,符合"前端只传触发意图"。

---

## 4. 数据流契约(回正后)

```text
[用户在轨迹报告面板点击 "AI分析"]
        │
        ▼
track.html requestRiskAssessment()
    ├─ 控制参数: 'report'(原 sportType 不再传)
    ├─ sentinel: __REPORT_RISK_ASSESSMENT__
    └─ 入参: 仅这两个字符串
        │
        ▼
window.pywebview.api.call_llm('__REPORT_RISK_ASSESSMENT__', 'report')
        │
        ▼
main.py Api.call_llm
    │
    ├─ §5.6 规则 4:分支入口立即 self._chat_messages = []; self._new_session_id()
    │
    ├─ 读 self._ai_snapshot(DB canonical) + self._track_weather(权威天气)
    │      └─ _build_risk_assessment_messages(snapshot, weather_context)
    │           ├─ build_risk_assessment_system_prompt → 含 4 维度 DATA BOUNDARY
    │           └─ build_risk_assessment_user_prompt
    │
    ├─ try: llm_backend.chat_completions(...)
    │
    ├─ except: empty_risk_assessment(f"LLM 调用失败: {exc}")  # §5.6 规则 7
    │
    └─ normalize_risk_assessment_json(text) → empty_risk_assessment on any failure
        │
        ▼
return {"ok": True, "risk_assessment": {...4 维度 + disclaimer + error}}
        │
        ▼
track.html _render → buildRiskAssessmentHTML → DOM 注入 #risk-assessment-result
```

---

## 5. P0-N 后端任务清单(5 子任务)

> **执行前提**: §3.1 / §3.2 修复已确定。本节给出实施步骤。

### P0-N-1:回正 sentinel 入口清空 + 异常捕获

**必改文件**:[main.py](file:///Users/fanglei/应用开发/AI%20track/main.py)

```python
# call_llm 中替换 L4063-L4078 整段
if prompt == self.REPORT_RISK_ASSESSMENT:
    # §5.6 规则 4:入口清空 + 刷新(必须在所有分支前)
    self._chat_messages = []
    self._new_session_id()

    if not self._ai_snapshot:
        return {"ok": True, "risk_assessment": llm_backend.empty_risk_assessment("请先加载活动轨迹")}
    messages = _build_risk_assessment_messages(self._ai_snapshot, self._track_weather)
    try:
        text = llm_backend.chat_completions(
            url=url, api_key=api_key, model=model,
            messages=messages, session_id=sid, agent_id=agent_id,
        )
    except Exception as exc:
        return {"ok": True, "risk_assessment": llm_backend.empty_risk_assessment(f"LLM 调用失败: {exc}")}
    risk_assessment = llm_backend.normalize_risk_assessment_json(text)
    return {"ok": True, "risk_assessment": risk_assessment}
```

**AC**:
- `grep -n "_chat_messages = \[\]" main.py | grep -B1 "REPORT_RISK_ASSESSMENT"` 显示清空在 if 分支顶部
- `grep -n "REPORT_RISK_ASSESSMENT" main.py` ≥ 3 命中(常量 + 入口清空 + 早返回 + LLM + 标准化)

### P0-N-2:新增控制参数 guard(配合 §3.3 A 路线)

**必改文件**:[main.py](file:///Users/fanglei/应用开发/AI%20track/main.py)

```python
# call_llm 签名不变,sport_type 已存在,改为参数语义
# 在 P0-N-1 块首行新增
if prompt == self.REPORT_RISK_ASSESSMENT:
    # §3.3 A 路线:控制参数必须为 'report',其它直接拒绝
    if sport_type != "report":
        return {"ok": True, "risk_assessment": llm_backend.empty_risk_assessment("非法调用:控制参数必须为 'report'")}

    self._chat_messages = []
    self._new_session_id()
    ...
```

**AC**:`grep "sport_type != \"report\"" main.py` ≥ 1 命中

### P0-N-3:snapshot 构建器白名单已合规,不动

**说明**:`_risk_snapshot_payload`([llm_backend.py L428-L446](file:///Users/fanglei/应用开发/AI%20track/llm_backend.py#L428-L446))已实现白名单,且显式排除 `shadow_diff`(allowed_keys 列表中无此字段),符合契约 §六。**保持现状**。

**AC**:`grep "shadow_diff" llm_backend.py` 在 `_risk_snapshot_payload` 函数体内 = 0

### P0-N-4:messages 构建器已合规,不动

**说明**:`_build_risk_assessment_messages`([main.py L3497-L3507](file:///Users/fanglei/应用开发/AI%20track/main.py#L3497-L3507))符合契约。

### P0-N-5:API 契约登记已合规,补一句 §5.6 规则 4 注释

**必改文件**:[docs/js_api_contract.json](file:///Users/fanglei/应用开发/AI%20track/docs/js_api_contract.json) L190

**修改**:

```diff
- "returns": "普通聊天返回 { ok, content }；__REPORT_INSIGHT__ 返回 { ok, insight, history, snapshot }；__REPORT_RISK_ASSESSMENT__ 返回 { ok, risk_assessment }；__RADAR_INSIGHT__ 返回 { ok, radar_insight, sport_type }；__FATIGUE_REVIEW_INSIGHT__ 返回 { code, msg, data: {fatigue_review_insight, sport_type}, traceId }",
+ "returns": "普通聊天返回 { ok, content }；__REPORT_RISK_ASSESSMENT__ 返回 { ok, risk_assessment }(4 维度 + disclaimer + error,控制参数固定为 'report',分支入口立即清空 _chat_messages 并刷新 session,失败走 empty_risk_assessment);..."
```

**AC**:JSON 解析合法,字段存在。

---

## 6. P1-N 前端任务清单(7 子任务)

### P1-N-1:按钮 + 面板 HTML — 已合规,不动

[track.html L9929-L9932](file:///Users/fanglei/应用开发/AI%20track/track.html#L9929-L9932) 已实现,符合模板。

### P1-N-2:CSS — 已合规,不动

`.risk-assessment-section / .risk-category / .risk-level-badge / .risk-advice / .risk-disclaimer / .risk-error` 在 track.html 中已存在;`.ai-empty` 复用雷达图样式。

### P1-N-3:状态层 — 已合规,不动

`appState.currentRiskAssessment / riskAssessmentLoading` 已在 [track.html L4752-L4753](file:///Users/fanglei/应用开发/AI%20track/track.html#L4752-L4753)。

### P1-N-4:async 入口函数 — 小幅回正(配合 §3.2 触发点 ③)

**必改文件**:[track.html](file:///Users/fanglei/应用开发/AI%20track/track.html) L9995-L10043

```javascript
async function requestRiskAssessment() {
    if (appState.riskAssessmentLoading) return;
    if (!window.pywebview || !window.pywebview.api || !window.pywebview.api.call_llm) {
        showToast('⚠️ AI 风险预警仅在桌面应用中可用');
        return;
    }
    if (!currentLLMConfig.url) { showToast('⚠️ 请先在配置中填写 API 地址'); return; }

    // §5.6 规则 5 触发点 ③:重新点击立即清空旧结果,避免闪烁
    appState.currentRiskAssessment = null;
    appState.riskAssessmentLoading = true;
    // ...后续原逻辑
    try {
        // §3.3 A 路线:控制参数固定 'report'
        const res = await withTimeout(
            window.pywebview.api.call_llm(PY_REPORT_RISK_ASSESSMENT, 'report'),
            60000
        );
        if (!res || !res.ok || !res.risk_assessment) {
            throw new Error((res && res.error) ? String(res.error) : '无风险预警结果');
        }
        appState.currentRiskAssessment = res.risk_assessment;
        if (resultEl) {
            resultEl.className = '';
            resultEl.innerHTML = buildRiskAssessmentHTML(res.risk_assessment);
        }
    } catch (e) {
        // §5.6 规则 7:错误用 empty_risk_assessment 的 error 字段展示
        var errorMsg = e && e.message ? e.message : String(e);
        var fallback = {
            supply_risk: {level:'中', advice:'暂无足够数据,建议结合实际路线和个人状态谨慎判断。'},
            weather_risk: {level:'中', advice:'暂无足够数据,建议结合实际路线和个人状态谨慎判断。'},
            equipment_risk: {level:'中', advice:'暂无足够数据,建议结合实际路线和个人状态谨慎判断。'},
            physical_risk: {level:'中', advice:'暂无足够数据,建议结合实际路线和个人状态谨慎判断。'},
            disclaimer:'以上建议由 AI 生成,仅供参考,请结合自身经验和实际情况判断。',
            error: errorMsg,
        };
        appState.currentRiskAssessment = fallback;
        if (resultEl) {
            resultEl.className = 'ai-empty';
            resultEl.innerHTML = buildRiskAssessmentHTML(fallback) + '<button type="button" class="ai-insight-btn" onclick="requestRiskAssessment()">重试</button>';
        }
        showToast('⚠️ 风险预警请求超时或失败');
    } finally {
        ...
    }
}
```

**AC**:控制参数传 `'report'`,不是 sportType;错误走 empty-style fallback。

### P1-N-5:`switchTab` 末尾追加 `resetRiskAssessmentState()`

**必改文件**:[track.html](file:///Users/fanglei/应用开发/AI%20track/track.html) L5736-L5741

```javascript
// §5.4 规则 6:切换 Tab 时清空 AI 洞察(阅后即焚)
_clearRadarInsight();
_clearFatigueReviewInsight();
resetRiskAssessmentState();   // ← 新增,触发点 ①
```

**AC**:`grep -n "_clearXxxInsight\|resetRiskAssessmentState" track.html` 显示 3 处 reset 函数都被调用 ≥ 1 次

### P1-N-6:`switchSidebarTab` 末尾追加条件清空

**必改文件**:[track.html](file:///Users/fanglei/应用开发/AI%20track/track.html) L9254-L9264

```javascript
function switchSidebarTab(tab, btn) {
    document.querySelectorAll('.sidebar-tab').forEach(function(el) { el.classList.remove('active'); });
    if (btn) btn.classList.add('active');
    document.querySelectorAll('.sidebar-panel').forEach(function(panel) { panel.style.display = 'none'; });
    const panel = document.getElementById('sidebar-panel-' + tab);
    if (panel) panel.style.display = 'flex';
    if (tab === 'cp') {
        updateCpTempNotice();
        renderCpList();
    }
    // §5.6 规则 5 触发点 ②:离开 report 侧栏时清空风险预警(风险预警只在 report 侧栏内)
    if (tab !== 'report') resetRiskAssessmentState();
}
```

**AC**:`grep -n "resetRiskAssessmentState" track.html` 命中数 ≥ 4(定义 + applyDataAndRender + switchTab + switchSidebarTab + requestRiskAssessment 入口)

### P1-N-7:不动(本功能无 sport state 切换函数)

**说明**:风险预警没有独立的 sport type selector(它消费的是当前加载的轨迹的 sportType),因此 §5.6.3 P1-N-7「切状态函数末尾清空」对本功能不适用,跳过。

---

## 7. P2-N 测试任务清单(5 子任务)

> **执行前提**: P0 + P1 已合并到一次提交。
> **现状**: 项目目前**没有任何**针对风险预警的测试。

### P2-N-1:prompt 单元测试

**新建**:`tests/test_risk_assessment_prompts.py`

```python
"""风险预警 prompt 单元测试。覆盖 §5.6 规则 3 / DATA BOUNDARY / MUST NOT / 4 维度。"""
import unittest
from llm_backend import (
    build_risk_assessment_system_prompt,
    build_risk_assessment_user_prompt,
    RISK_ASSESSMENT_OUTPUT_SCHEMA,
    empty_risk_assessment,
)

class TestRiskAssessmentPromptStructure(unittest.TestCase):
    def test_system_prompt_contains_4_dimensions(self):
        sp = build_risk_assessment_system_prompt({"activity_id": "a1"}, None)
        self.assertIn("补给风险", sp)
        self.assertIn("天气风险", sp)
        self.assertIn("装备风险", sp)
        self.assertIn("体力风险", sp)

    def test_system_prompt_data_boundary_clause(self):
        sp = build_risk_assessment_system_prompt(None, None)
        self.assertIn("DATA BOUNDARY", sp)
        self.assertIn("禁止生成或修改事实字段", sp)

    def test_system_prompt_must_not_clause(self):
        sp = build_risk_assessment_system_prompt(None, None)
        self.assertIn("MUST NOT", sp)
        self.assertIn("shadow_diff", sp)
        self.assertIn("shadow_diff_json", sp)
        self.assertIn("重新计算距离", sp)

    def test_output_schema_has_4_dimensions_and_disclaimer(self):
        self.assertIn("supply_risk", RISK_ASSESSMENT_OUTPUT_SCHEMA)
        self.assertIn("weather_risk", RISK_ASSESSMENT_OUTPUT_SCHEMA)
        self.assertIn("equipment_risk", RISK_ASSESSMENT_OUTPUT_SCHEMA)
        self.assertIn("physical_risk", RISK_ASSESSMENT_OUTPUT_SCHEMA)
        self.assertIn("disclaimer", RISK_ASSESSMENT_OUTPUT_SCHEMA)

    def test_empty_risk_assessment_has_all_keys(self):
        empty = empty_risk_assessment()
        for k in ("supply_risk", "weather_risk", "equipment_risk", "physical_risk", "disclaimer", "error"):
            self.assertIn(k, empty)
        self.assertEqual(empty["error"], "")

    def test_user_prompt_does_not_inject_metrics(self):
        self.assertIn("JSON", build_risk_assessment_user_prompt())
        # 用户 prompt 不应包含具体 metric 数值
        self.assertNotIn("distance", build_risk_assessment_user_prompt())
```

**AC**:覆盖 6 维度 / DATA BOUNDARY / MUST NOT / 输出 schema / empty 结构

### P2-N-2:normalizer 单元测试

**追加到**:`tests/test_risk_assessment_prompts.py`

```python
class TestNormalizeRiskAssessmentJson(unittest.TestCase):
    def test_none_returns_empty(self):
        from llm_backend import normalize_risk_assessment_json
        self.assertEqual(normalize_risk_assessment_json(None)["error"], "LLM 未返回内容")
        self.assertEqual(normalize_risk_assessment_json("")["error"], "LLM 未返回内容")

    def test_markdown_wrapped_json_stripped(self):
        from llm_backend import normalize_risk_assessment_json
        md = "```json\n{\"supply_risk\":{\"level\":\"低\",\"advice\":\"ok\"}}\n```"
        out = normalize_risk_assessment_json(md)
        self.assertEqual(out["supply_risk"]["level"], "低")

    def test_invalid_json_returns_empty_with_error(self):
        from llm_backend import normalize_risk_assessment_json
        out = normalize_risk_assessment_json("{not json")
        self.assertNotEqual(out["error"], "")

    def test_non_dict_returns_empty(self):
        from llm_backend import normalize_risk_assessment_json
        out = normalize_risk_assessment_json("[1,2,3]")
        self.assertNotEqual(out["error"], "")

    def test_invalid_level_clamped_to_moderate(self):
        from llm_backend import normalize_risk_assessment_json
        out = normalize_risk_assessment_json('{"supply_risk":{"level":"极高","advice":"x"}}')
        self.assertEqual(out["supply_risk"]["level"], "中")

    def test_missing_dim_defaulted_to_moderate(self):
        from llm_backend import normalize_risk_assessment_json
        out = normalize_risk_assessment_json('{}')
        self.assertEqual(out["supply_risk"]["level"], "中")
        self.assertEqual(out["weather_risk"]["level"], "中")
        self.assertEqual(out["equipment_risk"]["level"], "中")
        self.assertEqual(out["physical_risk"]["level"], "中")
```

### P2-N-3:snapshot 构建器 mock 测试

**追加到**:`tests/test_risk_assessment_prompts.py`

```python
class TestRiskSnapshotPayload(unittest.TestCase):
    def test_none_snapshot_yields_empty_payload(self):
        from llm_backend import _risk_snapshot_payload
        import json
        out = json.loads(_risk_snapshot_payload(None, None))
        self.assertEqual(out["activity_snapshot"], {})
        self.assertIsNone(out["weather_context"])

    def test_white_list_strips_shadow_diff(self):
        from llm_backend import _risk_snapshot_payload
        import json
        snap = {
            "activity_id": "a1", "distance_km": 10.5, "duration_sec": 3600,
            "shadow_diff": {"leak": True}, "shadow_diff_json": "leak",
            "diff": "leak",
        }
        out = json.loads(_risk_snapshot_payload(snap, None))
        self.assertNotIn("shadow_diff", out["activity_snapshot"])
        self.assertNotIn("shadow_diff_json", out["activity_snapshot"])
        self.assertNotIn("diff", out["activity_snapshot"])
        self.assertEqual(out["activity_snapshot"]["activity_id"], "a1")

    def test_weather_context_preserved_when_dict(self):
        from llm_backend import _risk_snapshot_payload
        import json
        w = {"temperature_c": 25.0, "humidity": 60, "weather_label": "晴"}
        out = json.loads(_risk_snapshot_payload({"activity_id":"a1"}, w))
        self.assertEqual(out["weather_context"]["temperature_c"], 25.0)

    def test_weather_context_rejected_when_not_dict(self):
        from llm_backend import _risk_snapshot_payload
        import json
        out = json.loads(_risk_snapshot_payload({"activity_id":"a1"}, "invalid"))
        self.assertIsNone(out["weather_context"])
```

### P2-N-4:集成测试(覆盖 §5.6 规则 4 全分支)

**新建**:`tests/test_risk_assessment_integration.py`

```python
"""风险预警 Api.call_llm 集成测试。覆盖 happy / 早返回 / LLM 异常 三路径。"""
import unittest
from unittest.mock import patch, MagicMock
from main import Api

class TestRiskAssessmentIntegration(unittest.TestCase):
    def setUp(self):
        self.api = Api()
        self.api._ai_snapshot = {"activity_id": "a1", "distance_km": 10.0}
        self.api._track_weather = {"temperature_c": 20, "humidity": 50}
        self.api._track_filename = "test.fit"

    def test_entry_clears_chat_messages_first(self):
        """§5.6 规则 4:进入分支前必须立即清空 _chat_messages"""
        self.api._chat_messages = [{"role":"user","content":"stale"}]
        with patch("llm_backend.chat_completions", return_value="{}") as m:
            with patch("llm_backend.normalize_risk_assessment_json", side_effect=lambda t: {"x":1}):
                self.api.call_llm(self.api.REPORT_RISK_ASSESSMENT, "report")
        self.assertEqual(self.api._chat_messages, [])

    def test_early_return_when_no_ai_snapshot(self):
        """降级路径 1:_ai_snapshot 为空时,清空必须已发生"""
        self.api._ai_snapshot = None
        self.api._chat_messages = [{"role":"user","content":"stale"}]
        res = self.api.call_llm(self.api.REPORT_RISK_ASSESSMENT, "report")
        self.assertEqual(self.api._chat_messages, [])
        self.assertIn("risk_assessment", res)
        self.assertNotEqual(res["risk_assessment"]["error"], "")

    def test_llm_exception_returns_empty_insight(self):
        """降级路径 2:LLM 网关异常时,_chat_messages 也必须已清空"""
        self.api._chat_messages = [{"role":"user","content":"stale"}]
        with patch("llm_backend.chat_completions", side_effect=Exception("gateway timeout")):
            res = self.api.call_llm(self.api.REPORT_RISK_ASSESSMENT, "report")
        self.assertEqual(self.api._chat_messages, [])
        self.assertIn("risk_assessment", res)
        self.assertIn("LLM 调用失败", res["risk_assessment"]["error"])

    def test_invalid_control_param_rejected(self):
        """§3.3 A 路线:控制参数必须为 'report'"""
        self.api._chat_messages = []
        res = self.api.call_llm(self.api.REPORT_RISK_ASSESSMENT, "running")
        self.assertIn("非法调用", res["risk_assessment"]["error"])

    def test_session_id_refreshed_after_call(self):
        """§5.6 规则 4:必须 _new_session_id()"""
        old_sid = self.api._session_id
        with patch("llm_backend.chat_completions", return_value="{}"):
            with patch("llm_backend.normalize_risk_assessment_json", side_effect=lambda t: {"x":1}):
                self.api.call_llm(self.api.REPORT_RISK_ASSESSMENT, "report")
        self.assertNotEqual(self.api._session_id, old_sid)
```

### P2-N-5:手工测试清单

**新建**:`docs/risk_warning_manual_test_checklist.md`

覆盖 5 个核心场景(每场景 3 列表格 + AC):
1. 加载有效 FIT → 点击 AI 分析 → 4 维度全部展示
2. 切 Tab → 风险预警面板清空
3. 切侧栏到 CP/POI → 风险预警面板清空
4. LLM 网关异常 → 显示 empty-style fallback + 重试按钮
5. 控制参数非 'report'(手动改前端)→ 后端拒绝并返回 empty_risk_assessment("非法调用")

---

## 8. 验证清单(任务完成后必跑)

```bash
# 1. 新测试 + 旧测试全过
python3 -m unittest test_risk_assessment_prompts test_risk_assessment_integration
python3 -m unittest test_radar_insight_prompts test_radar_insight_integration test_fatigue_review_prompts
# 预期:全过

# 2. §5.6 静态检查
grep -nB1 "if prompt == self.REPORT_RISK_ASSESSMENT" main.py
# 预期:入口 _chat_messages = [] 必须在 if 之前

grep -n "shadow_diff" llm_backend.py
# 预期:仅在 MUST NOT 提示文案中出现,在 _risk_snapshot_payload 内 = 0

grep -n "resetRiskAssessmentState" track.html
# 预期:命中 ≥ 4(定义 + applyDataAndRender + switchTab + switchSidebarTab + requestRiskAssessment 入口)

# 3. 契约文件
python3 -c "import json; json.load(open('docs/js_api_contract.json'))"
# 预期:无异常
```

---

## 9. 不在本方案范围内的事项

| 事项 | 理由 |
|---|---|
| 风险预警 prompt 增加更多维度(训练负荷、恢复、心率漂移) | 超出 §5.5 规定的 4 维度;若需扩展,先改契约 |
| 风险等级可视化(雷达图、热力图) | §5.5 当前允许行为仅"AI 解读 + 前端临时渲染",不做图表化 |
| 风险预警历史记录 | 违反 §5.4 规则 6(AI 洞察结果不持久化) |
| 风险预警与训练计划联动 | 不在轨迹报告 v3 边界;属于未来功能区 |
| 替换/合并 `__REPORT_INSIGHT__` | §5.6 规则 1 禁止 sentinel 复用,且当前代码无此 sentinel,无须处理 |

---

## 10. 评审 checklist

请评审者确认以下问题后,本方案进入实施态:

- [ ] §3.1 / §3.2 / §3.3 三个偏离修复方向是否同意?
- [ ] §5 P0-N / P1-N / P2-N 任务粒度是否合适?
- [ ] §7 P2-N-4 集成测试 5 个用例是否覆盖所有 §5.6 规则 4 分支?
- [ ] §9 不在本方案范围的事项是否需要扩入?
- [ ] 是否同意按 P0-N → P1-N → P2-N 顺序合并到一次提交?

---

## 11. 维度与数据源评审(v1.1 新增)

### 11.1 一句话结论

**4 维度划分本身合理,无须扩展;但数据源满足度从 50%~75% 不等,3 处显著缺口需补强(均为「后端已有但 risk 白名单未拉 / 未消费」类,不需新增外部依赖)。**

### 11.2 4 维度评估

| 维度 | 核心判据 | 与用户心智匹配 | 与运动类型耦合 | 边界互斥 | 评估 |
|---|---|---|---|---|---|
| 🎒 补给 | 吃喝、水、电解质 | ✅ 自然语言可直接表达 | 低(公式普适) | ✅ 与其他 3 维无重叠 | **保留** |
| 🌦️ 天气 | 温度、湿度、风、雨、雪、雷 | ✅ | 中(滑雪/登山有低温分支) | ✅ | **保留** |
| 🎽 装备 | 衣物、防晒、防雨、头灯、急救 | ✅ | 中(越野跑 vs 公路跑) | ✅ | **保留** |
| 💪 体力 | 爬升、心率、节奏、衰减 | ✅ | 中(骑行看 NP,游泳看 SWOLF) | ✅ | **保留** |

**是否扩到 5/6 维度?**

| 候选维度 | 评估 | 结论 |
|---|---|---|
| 🧭 路线/导航风险 | 长距离越野、夜间迷路 | ❌ **不扩**——`region / start_lat / start_lon` 可在 advice 文案中带过,不必单列维度;且当前 `environment_challenge.technical_terrain` 还在 Phase 2 占位,字段基础不足 |
| 🩺 健康/医学风险 | 心脏异常、热射病 | ❌ **不扩**——超出 AI 解读边界,属于医生诊断范畴,AI 不应给医学建议 |
| 🌡️ 环境挑战(单独列) | 高反、严寒、酷热 | ❌ **不扩**——已在 `environment_challenge` 模块独立处理,但按契约 §5.3 **不进 AI snapshot**;风险预警中以 narrative 形式带过即可 |

**结论:4 维度维持不变。**

### 11.3 数据源盘点

#### 11.3.1 `_risk_snapshot_payload` 当前白名单([llm_backend.py L428-L446](file:///Users/fanglei/应用开发/AI%20track/llm_backend.py#L428-L446))

```
activity_id, sport_type, sub_sport_type,
distance_km, distance_display, duration_sec,
avg_pace, avg_pace_display, pace_unit,
avg_hr, max_hr, calories,
elevation_gain_m, max_alt_m, min_alt_m, total_descent_m,
avg_cadence, normalized_power, swolf, tss,
start_time, region,
hr_decoupling, device_name,
up_count, down_count, max_single_climb_m,
difficulty_score, report_metrics_version, source
```

#### 11.3.2 AI snapshot 大白名单(39 项, [_AI_SNAPSHOT_FIELD_WHITELIST](file:///Users/fanglei/应用开发/AI%20track/metrics_resolver.py#L611-L646))中 risk_payload **未拉但相关**的字段

| 字段 | AI snapshot 已有 | risk 白名单已拉 | 对哪个维度有用 | 是否补 |
|---|---|---|---|---|
| `start_time_utc` | ✅ | ❌ | 装备(夜间判定) | **建议补** |
| `start_lat` / `start_lon` | ✅ | ❌ | narrative 增强 | 可选 |
| `weight` | ✅ | ❌ | 补给(水分/能量需求) | **建议补** |
| `height_cm` | ✅ | ❌ | 补给 | 可选 |
| `lactate_threshold_hr` | ✅ | ❌ | 体力(心率压力比) | **建议补** |
| `resting_hr` | ✅ | ❌ | 体力 | **建议补** |
| `vo2max` | ✅ | ❌ | 体力 | 可选 |
| `ftp_watts` | ✅ | ❌ | 体力(骑行) | 可选 |
| `avg_sleep_hours` | ✅ | ❌ | 体力(恢复状态) | **建议补** |
| `avg_grade_pct` / `max_slope_pct` | ✅ | ❌ | 装备(技术地形)+ 体力 | **建议补** |
| `uphill_pct` / `downhill_pct` | ✅ | ❌ | 装备 + 体力 | **建议补** |
| `hr_curve` / `speed_curve` | ✅ | ❌ | 体力(后程衰减) | **不补**(曲线数据量大,风险预警用 avg/max 已足够;若需要再做专用 snapshot 变体) |
| `pb_*` / `race_predict_*` | ✅ | ❌ | 体力(强度合理性) | 可选 |
| `longest_*` | ✅ | ❌ | 体力(经验) | 可选 |

#### 11.3.3 `_track_weather` 实际字段([utils/weather_api.py](file:///Users/fanglei/应用开发/AI%20track/utils/weather_api.py))

当前实现通过 `fetch_historical_weather` 从 Open-Meteo archive API 取**单点(运动开始时刻)**的:
- `temperature_c` / `humidity` / `wind_speed_kmh` / `weather_code` / `weather_label` / `observed_hour` / `observed_date`

**关键缺口(数据浪费)**:Open-Meteo archive API 实际返回了完整 `hourly[]` 数组(24 个时刻的温度/湿度/风速),但当前代码只取了 `match_index` 一个时刻(见 [weather_api.py L88-L117](file:///Users/fanglei/应用开发/AI%20track/utils/weather_api.py#L88-L117))。**长时间运动(8h 徒步)后续时段天气完全丢失**,导致天气维度判断只能基于"运动开始那一刻"。

#### 11.3.4 周边可消费但未消费的后端能力

| 能力 | 位置 | 对风险维度的价值 | 当前是否消费 |
|---|---|---|---|
| `environment_challenge` 子块(climb/altitude/heat/cold) | [metrics_resolver.py _build_environment_challenge_block](file:///Users/fanglei/应用开发/AI%20track/metrics_resolver.py#L3382) | 天气(heat/cold)+ 装备(altitude)+ 体力(climb) | ❌ 但按 §5.3 **不进 AI snapshot** |
| `calculate_track_difficulty` 派生 | [main.py L6721-L6730](file:///Users/fanglei/应用开发/AI%20track/main.py#L6721-L6730) | 装备(技术地形) | ⚠️ 仅写入 `mtdi_score`,未进 risk payload |
| `start_time_utc` 已有 UTC 标准化 | [main.py L1072-L1076](file:///Users/fanglei/应用开发/AI%20track/main.py#L1072-L1076) | 装备(夜间标志) | ❌ |
| 用户 PB / race_predict | profile_backend | 体力(强度是否超 PB) | ❌ |

### 11.4 维度 × 数据源匹配矩阵(关键审计)

| 维度 | 应有判据 | 当前可用数据源 | 满足度 | 主要缺口 |
|---|---|---|---|---|
| **🎒 补给** | 时长、距离、强度、卡路里、温度、湿度、海拔 | `duration_sec / distance_km / avg_hr / max_hr / calories / temperature_c / humidity / max_alt_m` | **70%** | 缺:用户体重(水分需求)、LT 心率(强度区间判定) |
| **🌦️ 天气** | 温度、湿度、风、雨雪、雷电、体感 | `temperature_c / humidity / wind_speed_kmh / weather_label`(仅运动开始单点) | **50%** | 缺:**时间序列天气**(Open-Meteo hourly 数组已取回但未消费)、UV 指数、降雨概率 |
| **🎽 装备** | 时长、海拔跨度、天气、夜间、技术地形、运动类型 | `duration_sec / max_alt_m / total_descent_m / temperature_c / weather_label / difficulty_score / sub_sport_type` | **65%** | 缺:**夜间标志**(需从 `start_time` + `duration_sec` 推算太阳位置)、高反等级(`environment_challenge.altitude` 存在但不进 AI) |
| **💪 体力** | 爬升、心率、TSS、hr_decoupling、时长、配速、PB 对比 | `elevation_gain_m / max_single_climb_m / up_count / avg_hr / max_hr / tss / hr_decoupling / difficulty_score / duration_sec` | **75%** | 缺:用户 LT / resting_hr(心率压力比)、`hr_curve` 后程衰减(数据已取回但未进 risk 白名单) |

### 11.5 数据源补强方案

#### A. **零成本补强(只动白名单列表,不动 DB / API)** — P0-N-3 增量

把以下字段加入 `_risk_snapshot_payload.allowed_keys`:

```python
allowed_keys = (
    # 原 28 项不动
    ...,
    # 新增(均已在 AI snapshot 白名单内,无需修改 Resolver)
    "start_time_utc",      # 装备:夜间判定(LLM 用 start_time_utc + duration_sec 自推太阳位置)
    "weight",              # 补给:水分需求估算(kg × 30~50ml/h)
    "lactate_threshold_hr",# 体力:心率压力比
    "resting_hr",          # 体力:HRR / 心率储备
    "avg_sleep_hours",     # 体力:恢复状态提示
    "avg_grade_pct",       # 装备 + 体力:技术地形 / 爬升压力
    "max_slope_pct",       # 装备 + 体力
    "uphill_pct",          # 体力:上坡占比
)
```

**工时估计**:`llm_backend.py` 1 处白名单修改 + `test_risk_assessment_prompts.py` 1 个白名单字段存在性测试 ≈ 30 行。

**预期效果**:补给满足度 70%→85%;体力满足度 75%→90%;装备满足度 65%→75%(夜间判定仍需后端辅助)。

#### B. **轻量级后端派生(夜间标志)** — P0-N-3.5(可选)

新增 Resolver 字段 `_is_night_activity(start_time_utc, duration_sec, start_lat, start_lon) -> bool`,基于太阳高度角粗算(可简化用日出日落表或 Astral 库)。

**优点**:LLM 不用算太阳位置,降低 prompt 复杂度。
**缺点**:新增依赖 / 增加 Resolver 职责;**评估为「可选」**,可放在 P0-N 之后做。

#### C. **时间序列天气补强(显著缺口,但工作量大)** — 列入 §9 不在本方案范围

把 Open-Meteo hourly 数组全量消费,在 `_track_weather` 中额外存 `temperature_range_c / humidity_avg / wind_max_kmh / precipitation_mm` 等聚合字段。

**为什么暂不做**:
- 工作量大,涉及 DB 字段扩展、`fetch_historical_weather` 升级、weather_json schema 演进。
- 当前实现采用"运动开始单点天气"是 v1 简化策略,数据已写入 `weather_json`,未来扩展无破坏性。
- LLM 在 prompt 中能基于 `observed_hour + duration_sec` 自行推理"运动跨越午后温度峰值"等场景,准确度可接受。

### 11.6 §11 与 §5 P0-N 的关系

| 项 | 关联 | 处理 |
|---|---|---|
| §5 P0-N-3(snapshot 构建器白名单已合规,不动) | 与 §11.5 A 冲突 | **修正**——把 §5 P0-N-3 改为「扩展白名单,补 7 字段」 |
| §7 P2-N-1(prompt 单元测试) | 与 §11.4 匹配矩阵相关 | **追加**——新增 `test_snapshot_payload_includes_extended_fields`,覆盖 7 字段从空 snapshot → 有 snapshot → 缺字段 3 种场景 |
| §9 不在本方案范围 | §11.5 B/C 列入 | **已覆盖** |

### 11.7 维度评审小结

| 评审项 | 结论 |
|---|---|
| 4 维度划分 | ✅ 合理,不扩不缩 |
| 维度边界互斥性 | ✅ 良好(补给/天气/装备/体力无重叠) |
| 维度覆盖度 | ✅ 户外运动四大风险域基本覆盖;路线/医学不扩 |
| 数据源满足度 | ⚠️ 4 维度 50%~75% 不等,需补 7 字段(均为零成本) |
| 夜间标志 | ⚠️ P0-N 范围外(可选 Phase 2) |
| 时间序列天气 | ⚠️ 显著缺口,不在本方案范围(可作 v2 任务) |
| 体感/UV/降雨概率 | ⚠️ 后端未计算,需新增 Resolver 派生;不在本方案范围 |

---

## 12. 评审 checklist(v1.1 更新)

请评审者确认以下问题后,本方案进入实施态:

- [ ] §3.1 / §3.2 / §3.3 三个偏离修复方向是否同意?
- [ ] §5 P0-N / P1-N / P2-N 任务粒度是否合适?
- [ ] §7 P2-N-4 集成测试 5 个用例是否覆盖所有 §5.6 规则 4 分支?
- [ ] §9 不在本方案范围的事项是否需要扩入?
- [ ] §11.2 4 维度维持不扩是否同意?
- [ ] §11.5 A 白名单补 7 字段(零成本)是否同意进入 P0-N-3?
- [ ] §11.5 B 夜间标志派生(Phase 2 可选)是否同意延后?
- [ ] §11.5 C 时间序列天气(v2 任务)是否同意延后?
- [ ] 是否同意按 P0-N → P1-N → P2-N 顺序合并到一次提交?

---

> **结束**: 本方案基于现有实现回正,不引入新文件结构,所有改动收敛在 [main.py](file:///Users/fanglei/应用开发/AI%20track/main.py) / [track.html](file:///Users/fanglei/应用开发/AI%20track/track.html) / [docs/js_api_contract.json](file:///Users/fanglei/应用开发/AI%20track/docs/js_api_contract.json) / [llm_backend.py](file:///Users/fanglei/应用开发/AI%20track/llm_backend.py) / 新建 2 个测试文件,符合契约 §5.6 「P0 后端 → P1 前端 → P2 测试」顺序。
>
> **v1.1 增量**: §11 维度评审确认 4 维度划分合理、数据源 50%~75% 满足、补 7 字段即可提至 75%~90%;B/C 两类缺口(夜间派生、时间序列天气)列入 Phase 2 / v2。
