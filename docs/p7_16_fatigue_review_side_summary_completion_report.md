# P7.16 右侧关键摘要面板纠偏完成报告

## 任务目标

对照设计图 `/Users/fanglei/Downloads/5486EA08-F07D-48FC-A8BF-D997700D1B66 2.PNG`，回正复盘 Tab 右侧分析摘要栏。

P7.16 只处理右侧关键摘要、崩溃触发因素、生理冲击点和建议结构；不重做主图、不重做事件图钉、不重做状态阶段条、不重做 Terrain Load，也不开放 AI 洞察。

## 契约约束

- 右侧摘要只消费 `get_fatigue_review(activity_id)` 后端 snapshot。
- 可用字段限于 `metrics / collapse_events / fatigue_zones / context_tags / advice / disclaimer`。
- 不读取 `curves`，不从 DOM、截图、ECharts、曲线走势、前端 payload、活动标题、设备信息或 `points` 推导结论。
- 不新增 AI 调用，不改 AI prompt，不解除 `fr-ai-generate-btn` 冻结。
- 不写 DB，不改后端 `curves` 契约。

## 实现内容

- `track.html`
  - 右侧栏新增 `fr-side-summary-panel`，展示关键摘要。
  - 右侧栏新增 `fr-phys-impact-panel`，展示生理冲击点。
  - `fr-events-panel` 语义调整为“崩溃触发因素”，仍复用后端 `collapse_events` 渲染。
  - `fr-fatigue-zones-panel` 保留为状态区间，仍复用后端 `fatigue_zones` 渲染。
  - 新增 `_renderFatigueReviewSideSummary(data)`，只读白名单字段。
  - loading / error 状态清空右侧摘要，避免旧活动内容残留。

- 测试与文档
  - 更新 `tests/test_fatigue_review_quality_gate.py`，新增 P7.16 右侧摘要门禁。
  - 更新 `docs/fatigue_review_realignment_plan_v1.md`。
  - 更新 `docs/detail_tab_review_manual_test_checklist.md`。

## 验证结果

已运行：

```bash
python3 -m pytest tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py
python3 -m pytest tests/test_fatigue_review_snapshot_realignment.py tests/test_fatigue_review_contract_realignment.py tests/test_fatigue_review_e2e_contract.py
```

结果：

- P7 UI / 详情 Tab：91 passed
- 后端 snapshot / 契约 / E2E：44 passed
- 1 warning：urllib3 / LibreSSL 环境提示，与本次改动无关。

## 完成结论

P7.16 已完成。右侧栏从普通列表进一步回正为关键摘要、崩溃触发因素、生理冲击点、状态区间和建议组合；事实来源仍保持后端白名单，AI 入口继续冻结。
