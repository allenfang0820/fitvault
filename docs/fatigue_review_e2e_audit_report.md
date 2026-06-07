# 复盘功能 E2E 联调分析报告

> 生成时间：V4.0 防腐层治理完成后
> 范围：复盘覆盖层（V6.3 / V7.x / V8.x）后端 → 前端全链路
> 测试文件：`tests/test_fatigue_review_e2e_contract.py`（32 tests）
> 结论：**32/32 联调测试通过；发现 2 个真实后端 bug 需修复**

---

## 一、复盘功能数据流总览

```
前端 openFatigueReview
    ↓
window.pywebview.api.get_fatigue_review(activity_id)
    ↓
main.py: get_fatigue_review  (envelope: {code, msg, data})
    ↓
_build_fatigue_review_snapshot(row)
    ↓
_build_resolved_payload_v81(hr_curve, speed_curve, sport_type)
    ↓
MetricsResolver.resolve() → {gap_curve, efficiency_curve, insight_events, fatigue_zones, ...}
    ↓
回填 metrics 8 字段 (hr_drift / decoupling / bonk_risk / events / efficiency / durability / cadence_stability / training_load)
    ↓
data = {sport_type, metrics, collapse_events, fatigue_zones, curves, context_tags, ai_insight, advice, disclaimer}
    ↓
前端 _renderFatigueReviewMetrics / _renderFatigueReviewDimensions / _renderFatigueReviewEvents
    + renderProfileAnalysisChart (ECharts 三层图)
```

---

## 二、后端输出清单（V8.x 当前实现）

### 2.1 顶级 9 段白名单

| 字段 | 类型 | 来源 | 备注 |
|---|---|---|---|
| `sport_type` | str | `row.sport_type` | running / cycling / swimming |
| `metrics` | dict | V4 治理 + V7.x 累计 | 8 维指标子字段 |
| `collapse_events` | list[dict] | Resolver `insight_events` | 异常事件图钉 |
| `fatigue_zones` | list[dict] | Resolver `fatigue_zones` | Layer 2 疲劳背景带 |
| `curves` | dict | Resolver + row | 5 条曲线 + total_distance_m |
| `context_tags` | dict | Resolver `context_tags` | 上下文标签 |
| `ai_insight` | None\|dict | call_llm 注入 | 走独立 sentinel `__FATIGUE_REVIEW_INSIGHT__` |
| `advice` | str | 后端兜底 | "暂未生成" / AI 填充 |
| `disclaimer` | str | 后端兜底 | "AI 生成仅供参考..." |

### 2.2 metrics 8 维指标子字段

| 指标 | 字段 | 来源 | 必填子键 |
|---|---|---|---|
| **hr_drift** (V7.10) | `pct`, `level`, `confidence`, `trend` | `MetricsResolver._compute_hr_drift` | 4 项 |
| **decoupling** (V7.6) | `pct`, `level`, `trend` | efficiency_curve 前后半 | 3 项 |
| **bonk_risk** | `is_at_risk`, `confidence`, `trend` | bonk_events + total_calories | 3 项 |
| **events** | `count`, `trend` | len(collapse_events) | 2 项 |
| **efficiency** (V7.9) | `score`, `level`, `confidence`, `delta_pct`, `sample_size`, `trend` | `MetricsResolver.evaluate_efficiency` | 6 项 |
| **durability** (V7.11) | `score`, `level`, `confidence`, `head_speed`, `tail_speed`, `trend` | `MetricsResolver._compute_durability_index` | 6 项 |
| **cadence_stability** (V7.12) | `score`, `level`, `confidence`, `cv`, `decay_pct`, `is_intermittent`, `trend` | `MetricsResolver._compute_cadence_stability` | 7 项 |
| **training_load** (V7.13) | `load`, `level`, `zone_used`, `confidence`, `load_ratio`, `trend` | `MetricsResolver._compute_training_load` | 6 项 |

### 2.3 curves 子字段

| 字段 | 类型 | 来源 | 用途 |
|---|---|---|---|
| `efficiency` | list[float] | Resolver | 解耦率曲线 |
| `gap` | list[float] | Resolver | 等效配速 |
| `grade` | list[float] | Resolver | 坡度 |
| `hr` | list[float] | row.hr_curve | 心率 |
| `speed` | list[float] | row.speed_curve | 速度 |
| `total_distance_m` | float | row.distance | ECharts xAxis 上限 |

### 2.4 trend 子字段（8 指标统一）

| 字段 | 类型 | 备注 |
|---|---|---|
| `delta_pct` | float\|None | 与 21d 中位数基线对比 |
| `level` | str | up / down / flat |
| `compared_count` | int | 对比样本数 |
| `is_improving` | bool\|None | 仅 decoupling/cadence_stability |
| `source` | str | historical_avg / v7_14_baseline / v8_5_21d_median_cadence_cv / v8_5_21d_median_daily_load |

### 2.5 collapse_events 子字段

| 字段 | 类型 | 备注 |
|---|---|---|
| `event_id` | str | "ce_NN" 格式 |
| `type` | str | BONK_WARNING / CADENCE_DROP / ... |
| `trigger_km` | float\|None | 触发距离 |
| `trigger_time_sec` | None | 预留 |
| `value_y` | float | 触发值 |
| `description` | str | 描述 |

### 2.6 fatigue_zones 子字段

| 字段 | 类型 | 备注 |
|---|---|---|
| `start_km` | float | 起始距离 |
| `end_km` | float | 结束距离 |
| `level` | str | high / medium / low |

---

## 三、前端消费依赖清单

### 3.1 DOM 元素 ID 映射

| 前端 ID | 后端字段路径 | 渲染函数 |
|---|---|---|
| `#fr-hr-drift` | `metrics.hr_drift.pct` | `_renderFatigueReviewMetrics` |
| `#fr-hr-drift-sub` | `metrics.hr_drift.level + trend` | 同上 |
| `#fr-decoupling` | `metrics.decoupling.pct` | 同上 |
| `#fr-decoupling-sub` | `metrics.decoupling.level + trend` | 同上 |
| `#fr-bonk` | `metrics.bonk_risk.is_at_risk` | 同上 |
| `#fr-bonk-sub` | `metrics.bonk_risk.confidence + trend` | 同上 |
| `#fr-events-count` | `metrics.events.count` | 同上 |
| `#fr-efficiency-score` | `metrics.efficiency.score` | 同上（V7.9） |
| `#fr-durability-score` | `metrics.durability.score` | 同上（V7.11） |
| `#fr-cadence-stability-score` | `metrics.cadence_stability.score` | 同上（V7.12） |
| `#fr-training-load-value` | `metrics.training_load.load` | 同上（V7.13） |
| `#fr-dimensions` | `metrics.{hr_drift,decoupling,bonk_risk}` | `_renderFatigueReviewDimensions` |
| `#fr-event-list` | `collapse_events` | `_renderFatigueReviewEvents` |
| `#fr-section-summary` | `ai_insight.summary` | `_renderFatigueReviewAiSuccess` |
| `#fr-advice` | `advice` / `ai_insight.training_advice` | 同上 |
| `#fr-disclaimer` | `disclaimer` / `ai_insight.disclaimer` | 同上 |
| `#fatigue-review-chart` | `curves.{efficiency,hr,speed,gap}` + `fatigue_zones` + `collapse_events` | `renderProfileAnalysisChart` |

### 3.2 AI 洞察返回结构（`call_llm('__FATIGUE_REVIEW_INSIGHT__')`）

```json
{
  "summary": "str",
  "sport_type": "str",
  "key_dimensions": [{"key": "str", "label": "str", "level": "str", "comment": "str"}],
  "event_interpretation": "str",
  "training_advice": "str",
  "disclaimer": "str",
  "error": "str (空态时)"
}
```

---

## 四、已验证可正常消费项 ✅

| 维度 | 验证项 | 测试 |
|---|---|---|
| 顶级 9 段白名单 | 完整覆盖 | `TestFatigueReviewBackendOutputContract` |
| metrics 8 维子字段 | hr_drift / decoupling / bonk_risk / events / efficiency / durability / cadence_stability / training_load | `test_metrics_whitelist` |
| curves 6 字段 | efficiency / gap / grade / hr / speed / total_distance_m | `test_curves_whitelist` |
| hr_drift 子字段 | pct/level/confidence/trend | `test_hr_drift_subfields` |
| efficiency 子字段 | score/level/confidence/delta_pct/sample_size/trend | `test_efficiency_subfields` |
| durability 子字段 | score/level/confidence/head_speed/tail_speed/trend | `test_durability_subfields` |
| cadence_stability 子字段 | score/level/confidence/cv/decay_pct/is_intermittent/trend | `test_cadence_subfields` |
| training_load 子字段 | load/level/zone_used/confidence/load_ratio/trend | `test_training_load_subfields` |
| 前端 pctVal() 渲染 | hr_drift.pct 数值类型 + 精度 | `test_frontend_hr_drift_pct_consumable` |
| 前端 lvl() 翻译映射 | 5 档 known level 全部覆盖 | `test_frontend_hr_drift_level_consumable` |
| 前端 trendText() 渲染 | 4 字段全 | `test_frontend_hr_drift_trend_consumable` |
| bonk_risk 布尔值 | is_at_risk: bool | `test_frontend_bonk_risk_consumable` |
| efficiency 4 档 confidence | high/medium/low/unavailable | `test_frontend_efficiency_consumable` |
| durability 头尾速度 | head_speed/tail_speed 数值或 None | `test_frontend_durability_consumable` |
| cadence 间歇训练 | is_intermittent: bool | `test_frontend_cadence_consumable` |
| training_load 6 档 level | very_high..very_low | `test_frontend_training_load_consumable` |
| ECharts distance_curve | 累计递增 km | `test_distance_curve_populated` |
| ECharts fatigue_zones schema | start_km/end_km/level | `test_fatigue_zones_schema` |
| ECharts insight_events schema | trigger_km/value_y/type/description | `test_insight_events_schema` |
| AI normalizer | 4 路径全部返回 valid dict | `test_ai_insight_normalizer` |
| 真实后端完整数据 | 完整 7+ 段 + 8 metrics | `test_snapshot_with_full_data` |
| event_id 格式 | "ce_NN" 格式校验 | `test_insight_event_id_format` |
| §三 envelope | {code, msg, data} 响应结构 | `test_envelope_response_code` |
| §六 shadow_diff 隔离 | 严禁 shadow_diff 字段 | `test_shadow_diff_not_in_fatigue_snapshot` |
| §五 AI 边界 | Resolver 不 import profile_backend | `test_metrics_resolver_no_profile_backend` |

---

## 五、发现的真实问题 ⚠️

### 🔴 Bug #1：降级分支缺失 `fatigue_zones` 字段

**位置**：`main.py:5635-5649`（`_build_fatigue_review_snapshot` 的外层 except 兜底）

**现象**：当 `hr_curve`/`speed_curve` 为空时（小型活动/无 GPS），触发 `UnboundLocalError: local variable 'fatigue_zones' referenced before assignment`，兜底 dict 缺失 `fatigue_zones` 字段。

**影响**：
- 前端 `data.fatigue_zones || []` 取不到 `data.fatigue_zones === undefined`
- `renderProfileAnalysisChart` 中 `fatigueZones = activityData.fatigue_zones || []` 临时保护，但 `chartPayload` 仍传 `fatigue_zones: data.fatigue_zones || []`（line 9895），实际为 `[]` 没问题
- 但前端契约 `data.fatigue_zones` 应当**始终存在**（即使空数组）

**修复**：

```python
# main.py:5635-5649 修复方案:补充 fatigue_zones + 4 个新 metrics 字段
return {
    "sport_type": "running",
    "metrics": {
        "hr_drift": {"pct": 0.0, "level": "unknown", "confidence": "unavailable", "trend": {...}},
        "decoupling": {...},
        "bonk_risk": {...},
        "events": {...},
        # 【修复】补齐 4 个新指标(V7.9 - V7.13)
        "efficiency": {"score": None, "level": "unknown", "confidence": "unavailable", ...},
        "durability": {"score": None, "level": "unknown", "confidence": "unavailable", ...},
        "cadence_stability": {"score": None, "level": "unknown", "confidence": "unavailable", ...},
        "training_load": {"load": None, "level": "unknown", "confidence": "unavailable", ...},
    },
    "collapse_events": [],
    "fatigue_zones": [],  # 【修复】补齐顶级字段
    "curves": {
        "efficiency": [], "gap": [], "grade": [], "hr": [], "speed": [],
        "total_distance_m": 0.0,  # 【修复】补齐
    },
    "context_tags": {},
    "ai_insight": None,
    "advice": "复盘快照构建失败,数据不足",
    "disclaimer": "AI 生成仅供参考 · 数据来源：FIT 解析 + 后端算法",
}
```

**优先级**：🔴 P0（数据契约违规，违反 §3 响应结构）

### 🟡 Bug #2：降级分支缺失 4 个新指标字段

**位置**：`main.py:5635-5649`（同上 except 兜底）

**现象**：兜底 dict 中 `metrics` 只含老 4 项（hr_drift / decoupling / bonk_risk / events），缺 V7.9-V7.13 的 4 个新指标。

**影响**：
- 前端 `_renderFatigueReviewMetrics` 走 `eff = metrics.efficiency || {}`，保护性默认空对象
- `eff.confidence === 'unavailable' || eff.score == null` 命中，显示 `--`
- **不会白屏，但违反了 §3 数据契约 9 段白名单完整性**

**修复**：与 Bug #1 一并修复。

**优先级**：🟡 P1（前端显示无影响，但违反契约）

### 🟢 风险点：降级触发路径宽泛

**观察**：`_build_fatigue_review_snapshot` 中大量 try/except 兜底，导致实际生产中可能频繁进入降级分支。

**改进建议**：
- 增加结构化日志统计降级频率
- 评估是否需将"无曲线"识别为正常状态（而非异常），走更早的提前 return

**优先级**：🟢 P2（性能/可观测性优化）

---

## 六、字段类型 & 精度对照

| 字段 | 后端类型 | 前端期望 | 匹配 |
|---|---|---|---|
| `hr_drift.pct` | float (0.0~100.0) | number → toFixed(1) | ✅ |
| `hr_drift.level` | str (excellent/good/warn/bad/unknown) | str | ✅ |
| `hr_drift.confidence` | str (high/medium/low/unavailable) | str | ✅ |
| `decoupling.pct` | float (0.0~100.0) | number → toFixed(1) | ✅ |
| `bonk_risk.is_at_risk` | bool | bool | ✅ |
| `efficiency.score` | float\|None (0~100) | number | ✅ |
| `efficiency.level` | str (improving/declining/stable/unknown) | str | ✅ |
| `efficiency.delta_pct` | float\|None | number | ✅ |
| `efficiency.trend.level` | str (up/down/flat) | str | ✅ |
| `durability.score` | float\|None (0~100) | number | ✅ |
| `durability.head_speed` / `tail_speed` | float\|None (m/s) | number → toFixed(2) | ✅ |
| `cadence_stability.cv` | float\|None (CV%) | number | ✅ |
| `cadence_stability.decay_pct` | float\|None (%) | number | ✅ |
| `training_load.load` | float\|None | number | ✅ |
| `training_load.zone_used` | str\|list\|None | str\|list | ✅（前端 Array.isArray 判断）|
| `curves.efficiency` | list[float] | list[float] | ✅ |
| `fatigue_zones[].start_km` / `end_km` | float | float | ✅ |
| `collapse_events[].event_id` | str "ce_NN" | str | ✅ |
| `context_tags` | dict[str, str] | dict | ✅（前端 Object.keys 遍历）|

**类型兼容性**：100% 匹配，无需类型转换。

---

## 七、异常场景覆盖

| 场景 | 后端行为 | 前端处理 | 验证状态 |
|---|---|---|---|
| 无 hr_curve/speed_curve | 走降级 except → 缺字段 | `eff.confidence === 'unavailable'` 显示 `--` | ⚠️ 部分通过（Bug #1 #2）|
| activity_id 不存在 | 返回 `{code: 1004, msg: "未找到..."}` | `_renderFatigueReviewError` | ✅ |
| LLM 返回空 | `empty_fatigue_review_insight("LLM 未返回内容")` | `_renderFatigueReviewAiError` | ✅ |
| LLM 返回无效 JSON | `empty_fatigue_review_insight("JSON 解析失败...")` | 同上 | ✅ |
| LLM 返回非 dict | `empty_fatigue_review_insight("洞察结果格式错误")` | 同上 | ✅ |
| `data.shadow_diff` 误入 | 前端 `console.warn + 渲染错误` | `code !== 0` 渲染 | ✅ |
| 21d baseline 不足 | `trend.compared_count < 3` | "数据不足" | ✅ |
| `eff.score == null` | `confidence: 'unavailable'` | 显示 `--` | ✅ |
| `durability.score == null` | 同上 | 显示 `--` | ✅ |
| cadence 间歇训练 | `is_intermittent: True` | "间歇训练不计算" | ✅ |
| `window._lastFatigueReviewCurves` 残留 | 阅后即焚清空 | `closeFatigueReview` 清空 | ✅ |

---

## 八、ECharts 三层图数据契约

| 输入 | 来源字段 | 类型 | 必需 |
|---|---|---|---|
| `distance_curve` | `_distanceFromSpeedTime(curves)` | list[float]，累计 km | ✅ |
| `hr_curve` | `curves.hr` | list[float] bpm | ✅ |
| `speed_curve` | `curves.speed` | list[float] m/s | ✅ |
| `gap_curve` | `curves.gap` | list[float] m/s | ✅ |
| `fatigue_zones[].start_km` | `fatigue_zones` | float | ⚠️ Bug（降级时缺）|
| `fatigue_zones[].end_km` | `fatigue_zones` | float | ⚠️ Bug |
| `fatigue_zones[].level` | `fatigue_zones` | str | ⚠️ Bug |
| `insight_events[].trigger_km` | `collapse_events` | float | ✅ |
| `insight_events[].value_y` | `collapse_events` | float | ✅ |
| `insight_events[].type` | `collapse_events` | str | ✅ |
| `insight_events[].description` | `collapse_events` | str | ✅ |

**前端 ECharts 防护**：
- `var distanceCurve = (activityData && activityData.distance_curve) || []` 临时保护
- `var allCurvesEmpty = (...)` 检测 4 曲线全空 → 渲染空态占位
- `chartContainer.innerHTML = _frEmptyStateHtml(...)` 占位卡

**结论**：前端 ECharts 渲染有充分防护，能优雅降级。

---

## 九、修复建议（落地要求）

### P0 优先级（必修）

1. **修复 `_build_fatigue_review_snapshot` 外层 except 兜底**（main.py:5635-5649）：
   - 补齐 `fatigue_zones: []`
   - 补齐 `curves.total_distance_m: 0.0`
   - 补齐 4 个新指标（efficiency / durability / cadence_stability / training_load）
   - 全部 `confidence: 'unavailable'`

2. **修复 `fatigue_zones` UnboundLocalError**（main.py:5619）：
   - 在 try 块开头初始化 `fatigue_zones: list = []` 防止内层 try 失败时引用未定义

### P1 优先级（建议修）

3. **统一兜底 dict 模式**：
   - 提取 `_empty_fatigue_review_snapshot()` 公共方法
   - 正常路径与降级路径都返回相同结构
   - 测试断言能 100% 覆盖降级场景

### P2 优先级（增强）

4. **结构化日志统计降级频率**：
   - 区分"无数据"(正常) vs "Resolver 异常"(异常)
   - 上报 metrics：降级次数、降级原因分布

---

## 十、最终结论

| 维度 | 结论 |
|---|---|
| 顶级 9 段白名单 | ✅ 完整 |
| metrics 8 维字段 | ✅ 完整（前端可消费）|
| curves 6 字段 | ⚠️ 降级时缺 `total_distance_m` |
| trend 子字段 | ✅ 完整 |
| AI 洞察 normalizer | ✅ 4 路径全部安全降级 |
| ECharts 三层图 | ✅ 前端防护充分，优雅降级 |
| shadow_diff 隔离 | ✅ 严格 |
| envelope 响应结构 | ✅ {code, msg, data} |
| 异常场景覆盖 | ⚠️ 降级分支缺 2 项字段（Bug #1 #2）|
| 跨字段类型兼容 | ✅ 100% |

**整体评估**：
- ✅ 8/10 维度完全可用
- ⚠️ 2 个 bug 待修复（均不阻塞主流程，前端有防护）
- 🟢 联调测试 32/32 通过

**落地要求**：
- 修复 P0 Bug #1（`fatigue_zones` 缺失）后，100% 前端契约对齐
- 修复 P0 Bug #2（`total_distance_m` + 4 个 metrics 缺失）后，降级场景契约完整
