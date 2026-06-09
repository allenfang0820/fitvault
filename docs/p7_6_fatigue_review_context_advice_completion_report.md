# P7.6 建议与上下文侧栏完成报告

## 1. 任务目标

在 P7.0-P7.5 基础上，升级复盘 Tab 右侧“上下文标签”和“建议”侧栏，让用户能清楚看到上下文、建议、免责声明的后端字段来源和缺失态。

本阶段不改活动详情 Modal 顶部，不改 Tab 系统，不改后端、算法、AI 后端、契约 JSON 或数据库。

## 2. 修改文件

- `track.html`
- `tests/test_v9_0_detail_tab_review.py`
- `tests/test_fatigue_review_quality_gate.py`
- `docs/fatigue_review_realignment_plan_v1.md`
- `docs/detail_tab_review_manual_test_checklist.md`
- `docs/p7_6_fatigue_review_context_advice_completion_report.md`

## 3. UI 变化摘要

- 上下文面板新增 `fr-context-boundary`。
- 建议面板新增 `fr-advice-boundary`。
- 建议面板新增 `fr-advice-status`。
- 新增 `_renderFatigueReviewAdvice(advice, disclaimer)`。
- `openFatigueReview` 改为调用 `_renderFatigueReviewAdvice(data.advice, data.disclaimer)`。
- 建议空态文案改为后端 `advice` 为空，不从指标或曲线生成建议。

## 4. 字段来源说明

| 区块 | 后端字段 |
|---|---|
| 上下文标签 | `data.context_tags` |
| 建议 | `data.advice` |
| 免责声明 | `data.disclaimer` |

## 5. 空态与错误态说明

- `context_tags = {}`：显示上下文标签空态，不从活动标题、设备或 DOM 补标签。
- `advice = ""` 或 `--`：显示“建议待接入”，不从 metrics/curves 生成建议。
- `disclaimer` 缺失：使用固定兜底免责声明。

## 6. 契约约束确认

- `get_fatigue_review(activity_id)` 仍是复盘 Tab 唯一数据源。
- 上下文只读取 `data.context_tags`。
- 建议只读取 `data.advice`。
- 免责声明只读取 `data.disclaimer` 或固定兜底。
- 前端没有从 metrics/curves/collapse_events/fatigue_zones/points/DOM 生成建议。
- 未写 DB，未改 canonical 数据，未让 AI 输出参与指标计算。
- 未实现草图右侧首页、活动、日历等全局导航，也未新增分享/导出区。

## 7. AI 入口冻结确认

- `fr-ai-generate-btn` 仍为 disabled。
- `fr-ai-generate-btn` 仍有 `aria-disabled="true"`。
- `fr-ai-generate-btn` 无 onclick。
- 本阶段不触发 `call_llm`。

## 8. 测试结果

已执行：

```bash
python3 -m pytest tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py
```

结果：60 passed, 1 warning。

说明：warning 为本地 Python `urllib3` / LibreSSL 环境提示，与 P7.6 UI 改造无关。

## 9. 未实现内容

- 未做响应式专项视觉验收，留给 P7.7。
- 未做视觉回归清单固化，留给 P7.8。
- 未开放 AI 洞察入口。

## 10. 下一步建议

进入 P7.7 响应式与可读性检查，覆盖窄屏、长文本、空数据和异常数据。
