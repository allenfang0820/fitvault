# P7.16A Terrain Load 柱形泳道接入完成报告

## 任务目标

对照设计图 `/Users/fanglei/Downloads/5486EA08-F07D-48FC-A8BF-D997700D1B66 2.PNG`，补齐复盘主图中缺失的 Terrain Load 柱形波浪泳道。

本任务只处理 Terrain Load 曲线来源、契约和主图泳道，不重做 P7.15 状态阶段条，不重构 P7.16 右侧摘要，不开放 AI 洞察。

## 契约约束

- Terrain Load 必须来自后端 `get_fatigue_review.data.curves.terrain_load`。
- 后端使用 `grade × speed × duration` 构建 Terrain Load 曲线。
- Terrain Load 与 `curves.distance` 使用同一后端距离轴并保持长度对齐。
- 前端只读取 `data.curves.terrain_load`，不得从 DOM、截图、ECharts、活动标题、前端 payload 或曲线走势推导。
- 不将 `metrics.training_load` 误作 Terrain Load。
- 不写 DB，不改 AI prompt，不开放 AI 洞察。

## 实现内容

- `main.py`
  - 新增 `_build_fatigue_review_terrain_load_curve()`。
  - `curves` 白名单新增 `terrain_load`。
  - 正常路径和 `_empty_fatigue_review_snapshot()` 均返回 `curves.terrain_load`。

- `track.html`
  - 图例新增 `Terrain Load · curves.terrain_load`。
  - `openFatigueReview()` 的 chart payload 新增 `terrain_load_curve`。
  - `_renderFatigueReviewLayeredEcharts()` 新增独立 Terrain Load 泳道。
  - Terrain Load 使用 ECharts `bar` series 呈现柱形波浪视觉。
  - 空态文案同步包含 `terrain_load`。

- 测试与文档
  - 更新 `docs/js_api_contract.json`。
  - 更新 `docs/fatigue_review_realignment_plan_v1.md`。
  - 更新 `docs/detail_tab_review_manual_test_checklist.md`。
  - 更新后端 snapshot、API 契约、E2E 和 P7 质量门禁测试。

## 验证结果

已运行：

```bash
python3 -m pytest tests/test_fatigue_review_snapshot_realignment.py tests/test_fatigue_review_contract_realignment.py tests/test_fatigue_review_quality_gate.py tests/test_fatigue_review_e2e_contract.py
```

结果：

- 78 passed
- 1 warning：urllib3 / LibreSSL 环境提示，与本次改动无关。

## 完成结论

P7.16A 已完成。复盘主图现在具备独立 Terrain Load 柱形泳道，字段来源已纳入后端权威快照和契约门禁；AI 入口仍保持冻结。
