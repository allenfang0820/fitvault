# P7.16B Terrain Load 柱间距与离散柱视觉回正完成报告

## 任务目标

对照设计图 `/Users/fanglei/Downloads/5486EA08-F07D-48FC-A8BF-D997700D1B66 2.PNG`，继续纠正复盘主图 Terrain Load 泳道视觉。

P7.16A 已完成 `curves.terrain_load` 后端事实字段与柱形泳道接入；P7.16B 只做视觉回正：把过密后端点形成的粘连色带，调整为一根根有间距的离散柱，并为柱体增加上深下浅的纵向渐变。

## 契约约束

- Terrain Load 仍只来自后端 `get_fatigue_review.data.curves.terrain_load`。
- X 轴仍只来自后端 `data.curves.distance`。
- 前端允许做显示层降采样 / 分桶，但不改变 Terrain Load 指标事实。
- 显示层聚合不回写 `activityData`，不写全局状态，不写 DB。
- 不从 DOM、截图、ECharts 当前像素、活动标题、设备信息、前端 payload、`points` 或其它曲线走势推导 Terrain Load。
- 不把 `metrics.training_load` 误作 Terrain Load。
- 不改 AI prompt，不开放 AI 洞察。

## 实现内容

- `track.html`
  - 新增 `_frDownsampleTerrainLoadBars(distanceCurve, terrainLoadCurve)`。
  - Terrain Load bar series 使用 `terrainBarData`，不再直接渲染密集 `lane.data`。
  - 显示层聚合改为等距距离桶，动态生成约 96-128 根柱，桶内取峰值，柱体间隔更均匀且更致密。
  - Terrain Load 柱宽调整为 `barWidth: 4`，并设置 `barGap / barCategoryGap`。
  - 柱体颜色改为 ECharts `LinearGradient(0, 0, 0, 1)`，顶部深青绿、底部浅青绿，并提高不透明度以强化上深下浅。
  - 保留 `fatigue_zones` 背景带和 `collapse_events.trigger_km` 事件参考线。

- 测试与文档
  - 更新 `tests/test_fatigue_review_quality_gate.py`，新增 P7.16B 门禁。
  - 更新 `docs/fatigue_review_realignment_plan_v1.md`。
  - 更新 `docs/detail_tab_review_manual_test_checklist.md`。

## 验证结果

已运行：

```bash
python3 -m pytest tests/test_fatigue_review_quality_gate.py tests/test_fatigue_review_snapshot_realignment.py tests/test_fatigue_review_contract_realignment.py tests/test_fatigue_review_e2e_contract.py
```

结果：

- 79 passed
- 1 warning：urllib3 / LibreSSL 环境提示，与本次改动无关。

## 完成结论

P7.16B 已完成。Terrain Load 视觉从粘连色带回正为离散柱形波浪，并带有上深下浅渐变；数据契约、后端事实源、事件线、疲劳带和 AI 冻结规则保持不变。
