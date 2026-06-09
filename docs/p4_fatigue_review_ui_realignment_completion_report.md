# P4 运动复盘 UI 草图还原完成报告

## 1. 本次目标

- 正式执行 P4 运动复盘 UI / 信息结构升级。
- 在 P0-P3 数据链路已回正的基础上，按草图方向重组复盘 Tab 的信息层级。
- 保持前端只消费 `get_fatigue_review(activity_id)` 后端权威 snapshot。
- 不修改后端算法、不修改 Resolver、不接 AI 洞察。

## 2. 修改文件

- `track.html`
- `tests/test_v9_0_detail_tab_review.py`
- `docs/detail_tab_review_manual_test_checklist.md`
- `docs/p4_fatigue_review_ui_realignment_completion_report.md`

## 3. 草图对齐说明

- 新增复盘主布局 `fr-review-layout`，形成主列 + 侧列的信息结构。
- 顶部新增 `fr-status-strip` 摘要带，展示后端权威快照、数据来源、距离轴状态、事件和疲劳带数量。
- 指标区拆成两组：
  - `fr-core-metrics-section`：心率漂移、解耦率、Bonk 风险、崩溃事件。
  - `fr-capacity-metrics-section`：运动效率、耐久指数、步频稳定性、训练负荷。
- 主图标题调整为“疲劳带 · 事件 · 曲线”，图例突出心率、速度、GAP、疲劳带和事件。
- 右侧新增上下文标签、关键事件、建议和 disclaimer 信息列。

## 4. 状态展示策略

- Loading / Error 继续使用现有 `fr-subtitle` 与 `fr-summary` 状态。
- Success 时新增 `_renderFatigueReviewSummary(data)`，只基于后端 snapshot 做展示文案。
- 缺 `context_tags` 时，右侧上下文面板展示空态。
- 缺权威距离轴时，继续沿用 P3 的图表空态：`复盘曲线数据不足`。
- AI 洞察 Modal 使用独立 `fr-ai-*` id，避免和 P4 复盘主页面 id 冲突。

## 5. 数据边界说明

- `chartPayload.distance_curve` 仍直接来自 `data.curves.distance`。
- `fatigue_zones` 仍直接来自 `data.fatigue_zones`。
- `insight_events` 仍直接来自 `data.collapse_events`。
- 指标卡仍只展示 `data.metrics`。
- P4 未恢复 `_distanceFromSpeedTime()`，未新增 speed/time/total_distance_m 距离推导。
- P4 未修改 `main.py`、`metrics_resolver.py`、`llm_backend.py`。

## 6. 测试变更

- `tests/test_v9_0_detail_tab_review.py` 新增 P4 结构测试，覆盖：
  - `fr-review-layout`
  - `fr-status-strip`
  - `fr-core-metrics-section`
  - `fr-capacity-metrics-section`
  - `fr-context-panel`
  - `fr-events-panel`
  - `fr-advice-panel`
- 同步将 AI Modal 内部元素断言更新为 `fr-ai-*` 独立 id。
- `docs/detail_tab_review_manual_test_checklist.md` 新增 P4 复盘页面结构手工验收项。

## 7. 验证结果

验证命令：

```bash
python3 -m pytest tests/test_v9_0_detail_tab_review.py tests/test_fatigue_review_e2e_contract.py tests/test_fatigue_review_snapshot_realignment.py tests/test_fatigue_review_resolver_realignment.py tests/test_fatigue_review_contract_realignment.py tests/test_fatigue_review_envelope.py
```

验证结果：

```text
86 passed, 1 warning
```

说明：

- warning 来自本机 urllib3 / LibreSSL 版本提示，与本次 P4 修改无关。
- 本机无 `python` 命令，继续使用 `python3` 完成验证。

## 8. 未处理事项

- P5：继续扩展测试门禁、手工验收和文档固化。
- P6：复盘 AI 洞察最后接入，修复 `__FATIGUE_REVIEW_INSIGHT__` 分支。

## 9. 下一步建议

- 进入 P5 测试与文档固化。
- P5 应重点把 P0-P4 的前端零推断、后端 snapshot 白名单、空态和 UI 结构变成长期门禁。
