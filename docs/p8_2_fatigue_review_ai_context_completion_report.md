# P8.2 复盘 AI 洞察真实联调与活动上下文修复完成报告

## 1. 任务目标

P8.2 解决 P8.1 打开按钮后的真实联调阻塞：用户在复盘 Tab 点击 `生成 AI 洞察` 后，后端返回 `请先加载活动轨迹`。

本阶段只修复当前复盘活动上下文，不改 AI 四维语义，不改「本次复盘概览」布局，不修改复盘指标算法，不写 DB。

## 2. 问题原因

P8.1 打开按钮后，前端调用链是正确的：

```js
call_llm('__FATIGUE_REVIEW_INSIGHT__', sportType)
```

但后端 `Api.call_llm()` 的 `__FATIGUE_REVIEW_INSIGHT__` 分支只从 `_ai_snapshot` 提取 `activity_id`。

复盘 Tab 的数据加载走的是 `get_fatigue_review(activity_id)`，该 API 只返回复盘 snapshot，没有把当前复盘活动 ID 写入后端 AI 上下文。因此真实点击 AI 时，后端 sentinel 无法定位当前活动，提前降级为：

```text
请先加载活动轨迹
```

## 3. 修复方案

新增后端专用复盘活动上下文字段：

```python
self._fatigue_review_activity_id = 0
```

在 `get_fatigue_review(activity_id)` 成功取到活动 row 并构建复盘 snapshot 后记录：

```python
self._fatigue_review_activity_id = aid
```

在 `call_llm('__FATIGUE_REVIEW_INSIGHT__', sport_type)` 中优先使用该字段：

```python
activity_id = (
    _safe_int(getattr(self, "_fatigue_review_activity_id", 0))
    or self._extract_fatigue_review_activity_id(self._ai_snapshot)
)
```

这样复盘 AI 可以从当前已加载复盘活动进入 compact snapshot 构建，同时保留旧 `_ai_snapshot` fallback。

## 4. 前端调用契约

保持不变。

前端仍只传：

```js
call_llm('__FATIGUE_REVIEW_INSIGHT__', sportType)
```

未传：

- `activityId`
- `metrics`
- `curves`
- `fatigue_zones`
- `collapse_events`
- `points`
- `activityData`
- `chartPayload`
- DOM 文本
- ECharts option
- 前端推导结果

`activity_id` 只作为后端当前复盘上下文存在，不作为前端 AI payload。

## 5. 后端 Snapshot 契约

保持不变。

AI 输入仍由：

- DB activity row
- `_build_fatigue_review_snapshot(row)`
- `_build_fatigue_review_insight_snapshot(activity_id, sport_type)`

构建。

compact snapshot 白名单仍为：

- `activity_id`
- `sport_type`
- `metrics`
- `fatigue_zones`
- `collapse_events`
- `curves_summary`
- `context_tags`
- `advice`
- `disclaimer`

仍禁止进入 AI snapshot：

- 全量 `curves`
- `records`
- `points`
- `raw_records`
- `track_points`
- `fit_records`
- `gpx_points`
- `shadow_diff`
- `shadow_diff_json`
- `diff`
- debug-only 字段

## 6. Session 与持久化边界

通过。

- `__FATIGUE_REVIEW_INSIGHT__` sentinel 入口仍先清空 `_chat_messages`。
- sentinel 入口仍刷新 `_new_session_id()`。
- 不写 DB。
- 不写 `ai_snapshots`。
- 不写 `localStorage`。
- 不写 `sessionStorage`。
- 不修改 `metrics / curves / fatigue_zones / collapse_events`。
- AI 输出仍只进入前端内存和 Modal 展示。

## 7. 测试结果

```bash
python3 -m pytest tests/test_fatigue_review_ai_preflight_p8.py tests/test_fatigue_review_ai_insight_p6.py
# 15 passed, 1 warning

python3 -m pytest tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py
# 120 passed, 1 warning

python3 -m pytest tests/test_fatigue_review_e2e_contract.py tests/test_fatigue_review_snapshot_realignment.py
# 61 passed, 1 warning
```

warning 为本地 Python `urllib3` / LibreSSL 环境提示，不是 P8.2 回归失败。

## 8. 新增测试覆盖

已新增：

- `get_fatigue_review(activity_id)` 成功后记录当前复盘活动 ID。
- `_ai_snapshot` 为空但 `_fatigue_review_activity_id` 存在时，`call_llm('__FATIGUE_REVIEW_INSIGHT__', sportType)` 会继续构建 compact snapshot。
- 上下文修复后不再提前返回 `请先加载活动轨迹`。
- LLM 配置缺失时仍返回 `empty_fatigue_review_insight(error)` envelope。

## 9. 剩余风险

- 本轮验证了真实阻塞点的上下文修复，但未实际连接外部 LLM 网关生成成功内容。
- 若用户本地 LLM 配置缺失，点击后会进入配置缺失 empty/error 展示，这是合理降级。
- 后续真实长文本输出仍需检查 Modal 可读性和清空触发点。

## 10. 下一步建议

进入 P8.3「复盘 AI 洞察四维语义回正」。

建议将旧维度：

- `endurance`
- `stability`
- `bonk_risk`
- `environment`

回正为：

- `overall_stability` / 全程稳定性
- `fatigue_progression` / 疲劳阶段
- `risk_triggers` / 风险触发
- `context_impact` / 外部影响

P8.3 只改 schema / prompt / normalizer 测试 / 前端文案映射，不在同一阶段改「本次复盘概览」卡片布局。四维总览卡建议留到 P8.4。
