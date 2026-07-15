# FR-Core-01 历史窗口与活动时点修复完成报告

日期：2026-07-13  
任务源：`docs/fatigue_review_core_audit_fix_task_list.md`  
状态：已完成

## 1. 交付手册摘要刷新

- `Activity/FIT` 是单次活动事实源，Resolver / 复盘后端是算法结论唯一事实源。
- `get_fatigue_review(activity_id)` 是复盘页唯一权威数据源；前端不补算复盘指标。
- 历史 baseline 必须以被复盘活动的 `start_time_utc / start_time` 归一化时间作为 `as_of_time`。
- 当前值与 baseline 必须处于同一时间语义、同一过滤规则和同一指标口径。
- `datetime.now()` 不得作为历史活动复盘的窗口终点；活动 ID 大小不得替代时间先后。

## 2. FR-Core-01 任务契约摘要

- 21d baseline 使用 `[as_of_time - 21d, as_of_time)`。
- 7d / 42d 训练负荷窗口分别使用 `[as_of_time - 7d, as_of_time)` 和 `[as_of_time - 42d, as_of_time)`。
- 历史查询必须排除当前活动和当前活动之后的未来活动。
- 时间字符串必须兼容 `Z`、带时区和无时区格式；权威比较使用 UTC datetime，不依赖 SQLite 文本字典序。
- 旧库缺少 `start_time_utc` 时必须降级使用 `start_time`，不能直接让复盘趋势失效。

## 3. 工程级提示词

目标：修复 FR-Core-01，让复盘历史 baseline 和 7d/42d 负荷窗口都站在被复盘活动发生时点计算。

范围：
- 允许修改 `main.py` 中复盘历史 trend / load ratio 查询逻辑。
- 允许修改 `metrics_resolver.py` 中 efficiency baseline 的时间锚点参数。
- 允许新增或更新 FR-Core-01 相关测试。
- 允许更新任务清单和本完成报告。

边界：
- 不修改解耦方向算法。
- 不修改 unavailable 指标趋势门控。
- 不修改 running durability 当前曲线权威源。
- 不修改前端缺失文案。
- 不顺手修改 ACS、OpenClaw、同步、标题、打包或无关 UI。

验收：
- 复盘历史活动时，baseline 不得读取活动之后的数据。
- 21d 窗口只包含活动前 21 天内样本。
- 7d / 42d 负荷窗口以活动时点结算，并排除未来样本。
- 冻结电脑当前日期不应改变同一历史活动的复盘结果。

## 4. 实现摘要

- 在 `main.py` 新增 `_parse_activity_datetime()`、`_activity_as_of_time()`、`_activity_table_time_sql()`、`_activity_time_in_window()`。
- 将 `_fetch_efficiency_trend()`、`_fetch_durability_trend()`、`_fetch_cadence_stability_trend()`、`_fetch_training_load_trend()`、`_fetch_load_ratio_7d_42d()` 改为以活动 `as_of_time` 过滤历史样本。
- 将 `metrics_resolver._fetch_efficiency_baseline()` 增加可选 `as_of_time`，并在复盘 efficiency 注入路径传入当前活动时间。
- 新增 `tests/test_fatigue_review_time_window_contract.py` 覆盖 21d 与 7d/42d 行为。
- 刷新过期测试断言：不再要求 SQL 字符串 `start_time >= ?` 作为时间契约；改为检查解析后的活动时点窗口过滤。

## 5. 验证结果

通过：

```bash
.venv312/bin/python -m pytest -q tests/test_fatigue_review_trends.py
.venv312/bin/python -m unittest discover -s tests -p 'test_fatigue_review_time_window_contract.py'
.venv312/bin/python -m unittest discover -s tests -p 'test_v8_5_trend.py'
jq empty docs/js_api_contract.json
git diff --check
```

红线回归：

```bash
.venv312/bin/python -m unittest discover -s tests -p 'test_fatigue_review_core_audit_regression.py'
```

结果：8 个测试中，历史窗口用例已转绿；剩余 6 个预期失败继续锚定后续任务。

## 6. 下一任务建议

按清单顺序，下一任务是 `FR-Core-02：后程效率变化方向与同口径趋势修复`。

建议执行边界：
- 只修 signed decoupling、`direction`、`change_pct / decline_pct` 和 current/baseline 同口径。
- 不同时修 unavailable trend gate、AI 快照净化、durability 曲线源或前端缺失文案。
