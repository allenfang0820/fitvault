# FR-Core-10 历史派生曲线与 baseline 版本化完成报告

日期：2026-07-13  
任务源：`docs/fatigue_review_core_audit_fix_task_list.md`  
状态：已完成

## 1. 交付手册摘要刷新

- 历史 speed/cadence baseline 优先从 canonical `track_json / points_json` 只读重建。
- 老库没有 canonical 轨迹时才 fallback 到 legacy 派生列。
- trend 必须携带 `basis/version/source_quality`。
- 普通页面读取不得批量写库或改变 canonical FIT 事实。

## 2. FR-Core-10 任务契约摘要

- 新旧活动使用相同公式和曲线选择规则。
- baseline 不得随机依赖旧 `speed_curve/cadence_curve` 是否存在。
- 不同来源质量必须显式标记，不得默默混为同口径强结论。
- 本任务不做破坏性迁移。

## 3. 工程级提示词

目标：修复历史 baseline 对旧派生曲线列的依赖，优先从 canonical track_json 只读重建 speed/cadence 曲线，并为趋势输出补齐版本与来源质量。

范围：
- 允许修改 `main.py` 历史 trend 查询和只读 helper。
- 允许更新趋势/时间窗口测试。
- 允许同步契约文档和任务清单。

边界：
- 不修改 durability/cadence 公式。
- 不在普通复盘页面读取时写库。
- 不改变 canonical FIT 事实。
- 不修改运动类型 registry、HR 来源或前端 UI 样式。

验收：
- 历史活动 `speed_curve/cadence_curve` 为空但 `track_json` 有数据时，baseline 仍能计算。
- trend 返回 `basis/version/source_quality`。
- 老库缺少 `track_json/points_json` 时仍能兼容 legacy 派生列。

## 4. 实现摘要

- 新增 `_activity_optional_column_sql()` 兼容不同 activities schema。
- 新增 `_review_curve_from_track_points()` 与 `_review_historical_curve()`。
- `_fetch_durability_trend()` 查询 canonical `track_json/points_json` 并从中重建 speed baseline。
- `_fetch_cadence_stability_trend()` 查询 canonical `track_json/points_json` 并从中重建 cadence CV baseline。
- durability/cadence trend 注入透传 `basis/version/source_quality`。

## 5. 验证结果

通过：

```bash
.venv312/bin/python -m unittest discover -s tests -p 'test_fatigue_review_time_window_contract.py'
.venv312/bin/python -m pytest -q tests/test_v8_5_trend.py tests/test_fatigue_review_trends.py tests/test_fatigue_review_core_audit_regression.py
.venv312/bin/python -m pytest -q tests/test_fatigue_review_e2e_contract.py tests/test_fatigue_review_snapshot_realignment.py tests/test_resolver_sport_isolation.py
```

结果：

- 时间窗口与 canonical baseline：4/4 通过。
- 趋势/核心回归：31/31 通过。
- 复盘契约 broader：154/154 通过。

## 6. 下一任务建议

按清单顺序，下一任务是 `FR-Core-11：真实活动回放矩阵与发布门禁`。
