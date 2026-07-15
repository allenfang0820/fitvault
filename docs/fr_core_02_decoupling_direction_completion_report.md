# FR-Core-02 后程效率变化方向与同口径趋势修复完成报告

日期：2026-07-13  
任务源：`docs/fatigue_review_core_audit_fix_task_list.md`  
状态：已完成

## 1. 交付手册摘要刷新

- Resolver / 复盘后端是算法结论唯一事实源；前端不得从曲线或 DOM 补算指标。
- 当前指标与历史 baseline 必须使用同一公式、方向、单位、过滤规则、basis 和 version。
- 后程效率变化必须保留方向；改善、稳定、下降不能被绝对值混成同一种“风险”。
- 前端只翻译后端状态和方向字段，不重新计算 early / late efficiency。

## 2. FR-Core-02 任务契约摘要

- `change_pct = (late_efficiency - early_efficiency) / early_efficiency * 100`。
- `decline_pct = max(0, -change_pct)`。
- `direction = improved | stable | declined | unknown`。
- `pct` 保留为前端兼容字段，但语义改为 `decline_pct`。
- trend baseline 缺少同口径 `efficiency_curve_signed_change` 时必须返回 unknown，不得用速度衰减替代。

## 3. 工程级提示词

目标：修复后程效率解耦方向，让后程改善不再被误判为下滑风险，并停止不同口径 trend 比较。

范围：
- 允许修改 `metrics_resolver.py` 的 `_build_review_decoupling()`。
- 允许修改 `main.py` 中 decoupling trend baseline 与 trend 元信息。
- 允许修改 `track.html` 的 decoupling 展示文案，但只消费后端字段。
- 允许更新相关测试和任务清单。

边界：
- 不修改 unavailable 状态机。
- 不修改 AI compact snapshot gate。
- 不修改 running durability 当前曲线源。
- 不修改功率/骑行专项算法。
- 不顺手修改 ACS、OpenClaw、同步、标题或打包。

验收：
- 后程效率 `[1.0...1.2]` 返回 `direction=improved`、`change_pct>0`、`decline_pct=0`，不得是 warn/bad。
- 后程效率 `[1.0...0.88]` 返回 `direction=declined`，并保留风险等级。
- 历史 trend 不再用 `speed_curve` 衰减作为 decoupling baseline。
- 前端展示能区分“改善 / 稳定 / 下滑”。

## 4. 实现摘要

- `_build_review_decoupling()` 改为 signed change 算法，新增 `change_pct / decline_pct / direction / basis / version`。
- `main.py::_fetch_historical_metrics_avg()` 不再读取 `speed_curve` 计算 decoupling baseline；缺同口径历史源时返回 `decoupling_pct=None`。
- `main.py` 给 decoupling trend 标注 `basis/version/baseline_basis/baseline_version`。
- `track.html` 新增 `_fatigueReviewDecouplingHeadline()` 与 `_fatigueReviewDecouplingEvidence()`，卡片和关键证据都使用后端方向字段。
- 测试同步废弃“后程改善也按绝对变化判坏”的旧契约。

## 5. 验证结果

通过：

```bash
.venv312/bin/python -m unittest discover -s tests -p 'test_v8_2_trend.py'
.venv312/bin/python -m pytest -q tests/test_fatigue_review_decoupling_resolver.py
.venv312/bin/python -m pytest -q tests/test_fatigue_review_e2e_contract.py tests/test_fatigue_review_snapshot_realignment.py
```

红线回归：

```bash
.venv312/bin/python -m unittest discover -s tests -p 'test_fatigue_review_core_audit_regression.py'
```

结果：8 个测试中，FR-Core-01 和 FR-Core-02 对应用例已转绿；剩余 5 个预期失败继续锚定后续任务。

## 6. 下一任务建议

按清单顺序，下一任务是 `FR-Core-03：不可用指标趋势门控与 AI 快照净化`。

建议执行边界：
- 只修 unavailable / partial 指标的 trend gate 和 AI compact snapshot 净化。
- 不同时修 durability 当前曲线源、空快照主值、运动类型路由或前端缺失文案。
