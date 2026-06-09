# P3 运动复盘前端最小可用回正完成报告

## 1. 本次目标

- 正式执行 P3 前端最小可用回正。
- 让复盘前端只消费 `get_fatigue_review(activity_id)` 返回的后端权威 snapshot。
- 删除前端基于 `speed / time / total_distance_m` 重建事实距离轴的职责。
- 保持 P3 边界：不改后端算法、不改 Resolver、不接 AI 洞察、不做草图完整视觉还原。

## 2. 修改文件

- `track.html`
- `tests/test_v9_0_detail_tab_review.py`
- `tests/test_fatigue_review_e2e_contract.py`
- `docs/detail_tab_review_manual_test_checklist.md`
- `docs/p3_fatigue_review_frontend_realignment_completion_report.md`

## 3. 前端链路变更

- `openFatigueReview(activityId)` 的 `chartPayload.distance_curve` 改为直接读取 `data.curves.distance`。
- 删除 `_distanceFromSpeedTime(curves)`。
- 前端不再使用 `speed`、`gap/hr` 长度、`total_distance_m` 或 `speed * 1s` 推导距离轴。
- `fatigue_zones` 继续只来自 `data.fatigue_zones`。
- `insight_events` 继续只来自 `data.collapse_events`。
- 指标卡、维度解释、事件列表继续只展示后端 `metrics / collapse_events / context_tags`。

## 4. 图表空态策略

- `renderProfileAnalysisChart()` 在 `distance_curve` 缺失或长度小于 2 时直接展示空态。
- 空态标题：`复盘曲线数据不足`。
- 空态原因：`后端未返回权威距离轴`。
- 空态 tag：`curves.distance = []`。
- 缺距离轴时不绘制 fatigue zones、event markers 或任何事实曲线。

## 5. 状态清理策略

- 本阶段保留既有 `_cleanupFatigueReviewPanel()`、`_clearFatigueReviewInsight()`、`_clearFatigueAiInsight()` 行为。
- 切活动时继续清空复盘 AI 状态与旧活动缓存。
- 关闭详情时继续清理 ECharts 实例与 lazy load 标志。
- AI 洞察 sentinel 保留，但 P3 不修复、不接入。

## 6. 测试变更

- `tests/test_v9_0_detail_tab_review.py` 新增 P3 静态契约测试：
  - `openFatigueReview()` 必须直接读取 `curvesObj.distance`。
  - 前端不得保留 `_distanceFromSpeedTime()`。
  - 前端不得按 speed 比例或 speed * 1s 重建距离轴。
  - `renderProfileAnalysisChart()` 缺权威距离轴时必须空态。
- `tests/test_fatigue_review_e2e_contract.py` 的图表 payload 模拟改为直接消费 `curves.distance`。
- `docs/detail_tab_review_manual_test_checklist.md` 新增 P3 前端零推断手工验收项。

## 7. 验证结果

验证命令：

```bash
python3 -m pytest tests/test_v9_0_detail_tab_review.py tests/test_fatigue_review_e2e_contract.py tests/test_fatigue_review_snapshot_realignment.py tests/test_fatigue_review_resolver_realignment.py tests/test_fatigue_review_contract_realignment.py tests/test_fatigue_review_envelope.py
```

验证结果：

```text
85 passed, 1 warning
```

说明：

- warning 来自本机 urllib3 / LibreSSL 版本提示，与本次 P3 修改无关。
- 本机无 `python` 命令，继续使用 `python3` 完成验证。

## 8. 未处理事项

- P4：按 `docs/design/运动复盘系统_页面设计草图_v1.png` 升级 UI 信息结构和视觉层级。
- P5：继续扩展前端/后端门禁与手工验收。
- P6：复盘 AI 洞察最后接入，修复 `__FATIGUE_REVIEW_INSIGHT__` 分支。

## 9. 下一步建议

- 进入 P4 UI 草图还原。
- P4 应只改变布局、状态和视觉层级，不改变 P0-P3 已固化的数据契约。
