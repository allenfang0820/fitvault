# P8.0 复盘 AI 洞察开放前契约复核完成报告

## 1. 审查结论

P8.0 复盘 AI 洞察开放前契约复核通过，允许进入 P8.1 最小闭环打开按钮。

P8.0 未解除 `fr-ai-generate-btn` 冻结，未新增实际 LLM 调用路径，未修改 AI prompt，未写 DB。

## 2. 后端 Sentinel 审查结果

通过。

- 复盘 AI 洞察继续使用唯一 sentinel：`__FATIGUE_REVIEW_INSIGHT__`。
- 未新增第二个复盘 AI sentinel。
- 未复用 `__RADAR_INSIGHT__`、`__REPORT_INSIGHT__` 或 `__REPORT_ACTIVITY_ADVICE__`。
- `Api.call_llm()` 的 FATIGUE 分支先清空普通聊天 session 并刷新 session id，保持功能区 AI 与普通聊天隔离。

## 3. Compact Snapshot 白名单审查结果

通过。

`_build_fatigue_review_insight_snapshot(activity_id, sport_type)` 只输出：

- `activity_id`
- `sport_type`
- `metrics`
- `fatigue_zones`
- `collapse_events`
- `curves_summary`
- `context_tags`
- `advice`
- `disclaimer`

AI 输入不包含全量 `curves`，只包含 `curves_summary`。

## 4. Forbidden 字段审查结果

通过，并补强。

本轮将 `_FATIGUE_REVIEW_FORBIDDEN_KEYS` 扩展为同时剥离：

- `records`
- `points`
- `raw_records`
- `track_points`
- `fit_records`
- `gpx_points`
- `shadow_diff`
- `shadow_diff_json`
- `diff`

新增 P8.0 测试验证 compact snapshot 会递归剥离这些字段。

## 5. 前端入口冻结审查结果

通过。

P8.0 后仍保持：

- `fr-ai-generate-btn disabled`
- `aria-disabled="true"`
- 按钮文案为待开放状态
- 按钮无 `onclick`

P8.0 未打开按钮。

## 6. 前端调用链审查结果

通过。

`onFatigueReviewAiInsight()` 保留为 P8.1 的预备调用链，但当前按钮未绑定。

静态门禁确认未来打开时只传：

```js
call_llm('__FATIGUE_REVIEW_INSIGHT__', sportType)
```

不传：

- `activityData`
- `curves`
- `metrics`
- `fatigue_zones`
- `collapse_events`
- `points`
- DOM 文本
- ECharts option / chart payload

## 7. AI Modal 状态审查结果

通过。

已有状态函数覆盖：

- loading：`_renderFatigueReviewAiLoading()`
- success：`_renderFatigueReviewAiSuccess(insight)`
- error：`_renderFatigueReviewAiError(msg)`
- empty：`_renderFatigueReviewAiEmpty(insight)`
- clear：`_clearFatigueReviewInsight()` / `_clearFatigueAiInsight()`

P8.0 未进行真实 LLM 联调；真实点击链路留到 P8.1。

## 8. 清空态 / 阅后即焚审查结果

通过，并补强。

已有清空触发包括：

- 关闭 AI Modal。
- 关闭活动详情。
- 切换活动。
- 切换详情 Tab。
- 重新点击生成前清空。
- sport type / 数据切换相关清空路径。

本轮发现并修复一个开放前隐患：

- 旧路径会在 AI 成功态将结果写入 `sessionStorage` 的 `fatigue_review_ai:*` 5 分钟缓存。
- P8.0 将该缓存路径改为 no-op 兼容层：保留函数名，避免旧调用异常，但不读写 `sessionStorage` / `localStorage`，也不展示“上次解读”缓存。

## 9. P7 冻结 UI 保护审查结果

通过。

P8.0 没有重构 P7 已冻结 UI：

- 不改分层主图结构。
- 不改左侧泳道。
- 不改图层控制。
- 不改右侧摘要。
- 不改状态阶段概览。
- 不改主图自适应 resize。

AI 结果仍位于独立 Modal，不嵌入主图或右侧栏，不挤压 P7 冻结布局。

## 10. 修改文件

- `main.py`
- `track.html`
- `docs/js_api_contract.json`
- `docs/fatigue_review_realignment_plan_v1.md`
- `docs/detail_tab_review_manual_test_checklist.md`
- `tests/test_fatigue_review_ai_insight_p6.py`
- `tests/test_fatigue_review_ai_preflight_p8.py`
- `docs/p8_0_fatigue_review_ai_preflight_contract_review_completion_report.md`

## 11. 测试结果

```bash
python3 -m pytest tests/test_fatigue_review_ai_preflight_p8.py tests/test_fatigue_review_ai_insight_p6.py
# 13 passed, 1 warning

python3 -m pytest tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py
# 97 passed, 1 warning

python3 -m pytest tests/test_fatigue_review_snapshot_realignment.py tests/test_fatigue_review_contract_realignment.py tests/test_fatigue_review_e2e_contract.py
# 45 passed, 1 warning

python3 -m json.tool docs/js_api_contract.json
# passed
```

warning 为本地 Python `urllib3` / LibreSSL 环境提示，不是 P8.0 回归失败。

## 12. Must-Fix 项

无剩余 must-fix。

本轮发现的 sessionStorage AI 结果缓存隐患已在 P8.0 内修复并固化测试。

## 13. Deferrable 项

- P8.0 未做真实 LLM 点击联调，因为按钮仍按契约冻结。
- AI Modal 在真实长文本、真实错误、真实空结果下的视觉细节留到 P8.1 / P8.2 验收。

## 14. 下一步建议

进入 P8.1「复盘 AI 洞察最小闭环打开按钮」。

P8.1 才允许考虑：

- 解除 `fr-ai-generate-btn disabled`。
- 移除 `aria-disabled="true"`。
- 绑定按钮点击入口。
- 真实调用 `call_llm('__FATIGUE_REVIEW_INSIGHT__', sportType)`。

P8.1 仍必须禁止：

- 前端拼 prompt。
- 传入前端事实 payload。
- 写 DB。
- 写 `localStorage` / `sessionStorage` 持久化 AI 事实。
- 让 AI 输出参与指标、曲线、事件或疲劳区间计算。
