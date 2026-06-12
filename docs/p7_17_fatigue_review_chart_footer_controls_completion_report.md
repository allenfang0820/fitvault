# P7.17 底部图例与交互控件回正完成报告

## 任务目标

对照设计图 `/Users/fanglei/Downloads/5486EA08-F07D-48FC-A8BF-D997700D1B66 2.PNG`，回正复盘 Tab 主图下方 / 底部辅助区域。

P7.17 只处理底部图例、图层状态、轻交互控件和底部辅助分析模块；不重做主图、不重做右侧摘要、不重做状态阶段、不重做 Terrain Load，也不开放 AI 洞察。

## 契约约束

- 只能消费 `get_fatigue_review(activity_id)` 后端 snapshot。
- Footer 允许读取 `curves` 的字段存在性和长度，但不得根据曲线值推导结论。
- 事件时间线只读 `collapse_events`。
- 负荷与能量只读 `metrics.training_load / metrics.bonk_risk`。
- 状态解释只读 `fatigue_zones / metrics.hr_drift / metrics.decoupling`。
- 建议状态只读 `data.advice / data.disclaimer`。
- 图层开关只影响当前前端 ECharts 视图，不写 DB、不写 localStorage、不请求后端、不触发 AI。

## 实现内容

- `track.html`
  - 新增 `fr-chart-footer`。
  - 新增图层状态 chip：曲线字段、距离轴、疲劳带、事件数量。
  - 新增展示层图层开关：曲线、疲劳带、事件、Terrain。
  - 新增底部辅助卡：事件时间线、负荷与能量、状态解释、建议状态。
  - 新增 `_renderFatigueReviewChartFooter(data)`。
  - 新增 `_applyFatigueReviewLayerVisibility(chartPayload)` 和 `onFatigueReviewLayerToggle(inputEl)`。
  - loading / error 状态清空 footer 与最近 chart payload。

- 测试与文档
  - 更新 `tests/test_fatigue_review_quality_gate.py`，新增 P7.17 footer / toggle 门禁。
  - 更新 `docs/fatigue_review_realignment_plan_v1.md`。
  - 更新 `docs/detail_tab_review_manual_test_checklist.md`。

## 验证结果

已运行：

```bash
python3 -m pytest tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py
python3 -m pytest tests/test_fatigue_review_snapshot_realignment.py tests/test_fatigue_review_contract_realignment.py tests/test_fatigue_review_e2e_contract.py
```

结果：

- P7 UI / 详情 Tab：94 passed
- 后端 snapshot / 契约 / E2E：44 passed
- 1 warning：urllib3 / LibreSSL 环境提示，与本次改动无关。

## 完成结论

P7.17 已完成。主图下方不再只有单薄轴说明，而是具备图层状态、展示层开关和底部辅助分析模块；数据事实仍来自后端白名单，AI 入口继续冻结。
