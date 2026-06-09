# P7.8 视觉回归测试与手工清单完成报告

## 1. 本阶段目标

P7.8 的目标是在 P7.1-P7.7 已完成复盘分析驾驶舱信息架构、视觉区块和响应式加固后，固化视觉回归测试与人工验收清单。

本阶段不继续大改 UI，不开放 AI 洞察，不改后端、算法、DB schema 或 API 契约。

## 2. 实际修改文件

- `tests/test_v9_0_detail_tab_review.py`
- `tests/test_fatigue_review_quality_gate.py`
- `docs/detail_tab_review_manual_test_checklist.md`
- `docs/fatigue_review_realignment_plan_v1.md`
- `docs/p7_8_fatigue_review_visual_regression_completion_report.md`

## 3. 新增或调整的测试项

新增 P7.8 静态视觉回归测试：

- 锁定复盘 Tab 视觉区块顺序：
  - `fr-ai-generate-btn`
  - `fr-review-layout`
  - `fr-status-strip`
  - `fr-core-metrics-section`
  - `fr-capacity-metrics-section`
  - `fr-chart-section`
  - `fr-context-panel`
  - `fr-events-panel`
  - `fr-fatigue-zones-panel`
  - `fr-advice-panel`
- 锁定草图范围边界：
  - 不新增首页、活动、日历等全局导航。
  - 不新增分享、导出等全局动作。
  - 活动详情顶部和现有 Tab 系统继续存在。
- 锁定 AI 冻结：
  - `fr-ai-generate-btn` 保持 disabled。
  - 保持 `aria-disabled="true"`。
  - 不出现 onclick。
  - 按钮片段中不触发 `call_llm`。

## 4. 手工验收清单变更

已在 `docs/detail_tab_review_manual_test_checklist.md` 中新增：

- `1.1.10 P7.8 视觉回归测试与手工清单`
- `6.10 P7.8 视觉回归测试与手工清单门禁`

新增手工验收覆盖：

- P7.1 信息架构顺序。
- 设计草图边界。
- 现有活动详情顶部和 Tab 保持。
- 桌面、中宽、窄屏、小屏布局。
- 长 advice、disclaimer、context tag、事件说明。
- 空 metrics、空 distance、空事件、空疲劳区间。
- AI 洞察入口冻结。
- 前端零事实推导。

## 5. 契约约束核对

数据源契约：保持。

- `get_fatigue_review(activity_id)` 仍是复盘 Tab 唯一数据源。
- P7.8 未新增任何前端事实推导。
- `curves.distance` 仍是主图 X 轴、疲劳带、事件定位的唯一权威距离来源。
- `metrics / fatigue_zones / collapse_events / context_tags / advice / disclaimer` 继续只读后端白名单字段。

AI 冻结：保持。

- `fr-ai-generate-btn` 继续 disabled。
- 保留 `aria-disabled="true"`。
- 不新增 onclick。
- 不触发 `call_llm`。
- 不新增实际 `__FATIGUE_REVIEW_INSIGHT__` 前端调用链。
- 不写 DB。

UI 边界：保持。

- 保持现有活动详情顶部信息。
- 保持现有详情 Tab 系统。
- 复盘 Tab 继续对应草图“分析”页。
- 未新增草图右侧首页、活动、日历等全局导航。
- 未新增分享、导出动作。

后端 / DB / API：未改。

- 未修改 `main.py`。
- 未修改算法链路。
- 未修改 DB schema。
- 未修改 `docs/js_api_contract.json`。

响应式与可读性门禁：保持。

- P7.7 的三档响应式 CSS 守卫继续存在。
- 长文本可读性守卫继续存在。
- 不使用 viewport 字体缩放。
- 不使用负 `letter-spacing`。

## 6. 自动测试结果

```text
python3 -m pytest tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py
69 passed, 1 warning in 0.73s
```

warning 为本地 Python 环境的 `urllib3` / LibreSSL 提示，不是 P7.8 回归失败。

## 7. 视觉检查结果

已尝试启动本地应用：

```text
python3 main.py
```

启动失败于本地 Watchdog/FSEvents 环境：

```text
SystemError: Cannot start fsevents stream. Use a kqueue or polling observer instead.
```

该问题与 P7.7 视觉检查阻塞一致，不是 P7.8 自动测试失败。P7.8 已用静态 DOM/CSS 门禁和手工验收清单兜底固化视觉回归范围。

## 8. 剩余风险

- 当前 P7.8 未引入真实截图 diff 框架，视觉回归以静态 DOM/CSS 门禁和手工清单为主。
- 本地浏览器视觉检查依赖 dev server 是否能正常启动；若 Watchdog/FSEvents 失败，需要后续用可启动环境补做截图验收。
- AI 入口仍冻结，P7.9 若要解除冻结，需要单独做开放前审查。

## 9. 下一步建议

进入 P7.9「UI 定稿后 AI 入口复核」，先审查是否满足解除 P6.1 冻结的条件，再决定是否开放前端 AI 洞察入口。
