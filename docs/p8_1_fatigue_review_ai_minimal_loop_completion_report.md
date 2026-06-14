# P8.1 复盘 AI 洞察最小闭环完成报告

## 1. 任务目标

P8.1 的目标是在 P7 UI 定稿和 P8.0 开放前审查通过后，打开复盘 Tab 的 AI 洞察入口，并接通现有 `__FATIGUE_REVIEW_INSIGHT__` 最小调用闭环。

本阶段只开放入口和前端状态流，不修改复盘指标算法、不修改主图、不写 DB、不让 AI 输出参与 `metrics / curves / fatigue_zones / collapse_events` 计算。

## 2. 已完成内容

前端入口：

- `fr-ai-generate-btn` 从冻结态改为可点击态。
- 按钮文案调整为 `生成 AI 洞察`。
- 按钮绑定 `onclick="onFatigueReviewAiInsight()"`。
- 按钮本身不内联 `call_llm`，不携带任何事实 payload。
- 摘要带 AI 状态从 `AI 待开放` 调整为 `AI 可用`。

前端调用：

- `onFatigueReviewAiInsight()` 继续只调用：

```js
call_llm('__FATIGUE_REVIEW_INSIGHT__', sportType)
```

- 不传 `metrics`、`curves`、`fatigue_zones`、`collapse_events`、`points`、DOM 文本、ECharts option 或 chart payload。
- 重新点击前继续清空旧洞察。
- loading / success / error / empty 继续走现有 Modal 四态。

入口状态：

- 新增 `_setFatigueReviewAiEntryBusy(isBusy)`。
- loading 时按钮临时禁用并显示 `AI 分析中`。
- success / error / empty / close / clear 后恢复 `生成 AI 洞察`。
- 保留 `_freezeFatigueReviewAiEntry()` 作为兼容函数名，但当前行为已改为恢复可点击入口，避免旧调用链断裂。

## 3. 后端契约保持

后端未改变核心边界：

- 复盘 AI 仍只使用 sentinel `__FATIGUE_REVIEW_INSIGHT__`。
- `Api.call_llm()` sentinel 入口仍先清空普通聊天 session 并刷新 session id。
- AI 输入仍由 `_build_fatigue_review_insight_snapshot(activity_id, sport_type)` 构建。
- compact snapshot 仍只包含 `activity_id / sport_type / metrics / fatigue_zones / collapse_events / curves_summary / context_tags / advice / disclaimer`。
- 仍递归剥离 `records / points / raw_records / track_points / fit_records / gpx_points / shadow_diff / shadow_diff_json / diff`。
- LLM 异常、缺配置、缺活动、缺数据均返回 `empty_fatigue_review_insight(error)` envelope。

## 4. 持久化边界

通过。

- 不写 DB。
- 不写 `ai_snapshots`。
- 不写 `localStorage` / `sessionStorage`。
- AI 结果只保留在当前前端内存和 Modal 展示态。
- 关闭、切换、重新点击仍会清空旧洞察。

## 5. 修改文件

- `track.html`
- `tests/test_v9_0_detail_tab_review.py`
- `tests/test_fatigue_review_quality_gate.py`
- `tests/test_fatigue_review_ai_preflight_p8.py`
- `docs/p8_1_fatigue_review_ai_minimal_loop_completion_report.md`

## 6. 测试结果

```bash
python3 -m pytest tests/test_fatigue_review_ai_preflight_p8.py tests/test_fatigue_review_ai_insight_p6.py
# 13 passed, 1 warning

python3 -m pytest tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py
# 120 passed, 1 warning
```

warning 为本地 Python `urllib3` / LibreSSL 环境提示，不是 P8.1 回归失败。

## 7. 剩余风险

- 本轮未执行真实 LLM 网关联调；已通过 mock / 静态门禁确认调用边界。
- 若用户本地 LLM 配置缺失，点击后会进入 empty/error 展示，不会抛异常。
- 真实长文本输出的 Modal 可读性仍需 P8.2 做人工验收。

## 8. 下一步建议

进入 P8.2「复盘 AI 洞察真实联调与展示验收」。

P8.2 建议只做：

- 使用真实活动点击 `生成 AI 洞察`。
- 验证 loading / success / error / empty 四态。
- 验证 AI 内容不撑破 Modal。
- 验证切 Tab、切活动、重新点击、关闭 Modal 后旧结果清空。
- 验证 DevTools / 日志中前端仍只传 sentinel + sportType。
