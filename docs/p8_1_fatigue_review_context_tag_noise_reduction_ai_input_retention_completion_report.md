# P8.1 复盘上下文标签降噪与 AI 输入保留完成报告

## 1. 修改文件清单

- `main.py`
- `metrics_resolver.py`
- `track.html`
- `docs/detail_tab_review_manual_test_checklist.md`
- `docs/fatigue_review_realignment_plan_v1.md`
- `docs/js_api_contract.json`
- `tests/test_fatigue_review_quality_gate.py`
- `tests/test_v9_0_detail_tab_review.py`
- `tests/test_e2e_fatigue_review.py`
- `tests/test_fatigue_review_snapshot_realignment.py`

## 2. UI 降噪结果

已移除复盘右侧独立 `fr-context-panel` 上下文卡片。

用户可见空态已删除：

- `本次活动未携带上下文标签`
- `暂无上下文`

`context_tags` 非空时，前端仅在右侧“关键摘要”中渲染“影响因素”；`context_tags = {}` 时不展示任何上下文区域或空态占位。

## 3. `context_tags` 后端契约保留说明

`get_fatigue_review(activity_id)` 继续返回 `context_tags`。

本轮补强 `_build_resolved_payload_v81()` 的 Resolver session 输入，新增或保留以下背景字段：

- `avg_heart_rate`
- `max_heart_rate`
- `total_ascent`
- `max_altitude`
- `avg_power`
- `normalized_power`
- `avg_temperature`

`avg_temperature` 支持从 `weather_json.temperature_c` 兜底读取。无 records 或 records 不足时，`_build_resolved_payload_v81()` 返回安全 fallback，不再引用未定义变量。

## 4. AI Compact Snapshot 白名单保留说明

`__FATIGUE_REVIEW_INSIGHT__` compact snapshot 继续包含：

- `activity_id`
- `sport_type`
- `metrics`
- `fatigue_zones`
- `collapse_events`
- `curves_summary`
- `context_tags`
- `advice`
- `disclaimer`

禁入字段仍递归剥离：`points / records / raw_records / track_points / fit_records / gpx_points / shadow_diff / shadow_diff_json / diff`。

## 5. 禁止前端推导说明

前端“影响因素”只消费 `data.context_tags`。

本轮未从 `metrics / curves / collapse_events / fatigue_zones / DOM / ECharts / 截图 / 活动标题 / 设备 / 路线 / points` 推导上下文标签。

## 6. 测试命令与结果

```bash
python3 -m pytest tests/test_fatigue_review_snapshot_realignment.py tests/test_fatigue_review_ai_preflight_p8.py
# 31 passed, 1 warning

python3 -m pytest tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py
# 115 passed, 1 warning

python3 -m pytest tests/test_e2e_fatigue_review.py tests/test_fatigue_review_e2e_contract.py
# 74 passed, 1 warning

python3 -m json.tool docs/js_api_contract.json
# passed
```

warning 为本地 Python `urllib3` / LibreSSL 环境提示，不是 P8.1 回归失败。

## 7. 未覆盖风险

- 本轮为静态测试与后端单元测试验证；尝试用 in-app Browser 打开本地 `file://` 页面时被浏览器安全策略阻止，未做真实浏览器截图。
- 未开放 AI 洞察按钮，真实 LLM 点击链路仍沿用 P8.0 冻结结论。
