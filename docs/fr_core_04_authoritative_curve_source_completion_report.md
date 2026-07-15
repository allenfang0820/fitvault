# FR-Core-04 当前指标曲线权威源统一完成报告

日期：2026-07-13  
任务源：`docs/fatigue_review_core_audit_fix_task_list.md`  
状态：已完成

## 1. 交付手册摘要刷新

- 当前活动指标必须来自同一份权威复盘快照。
- 图表、HR drift、骑行解释和 running durability 不得混用不同曲线来源。
- 数据库派生列可以作为兜底输入，但不能优先于本次解析出的 `curves_snapshot`。

## 2. FR-Core-04 任务契约摘要

- running durability 的当前速度输入使用 `curves_snapshot.speed`。
- 当 `row.speed_curve` 为空但权威 snapshot speed 有足够样本时，不得返回 `points<20`。
- 保持统一 startup review window，不为 durability 单独开窗口。

## 3. 工程级提示词

目标：统一当前复盘指标曲线权威源，修复 running durability 误读空 `row.speed_curve` 的问题。

范围：
- 允许修改 `main.py` 中 `_build_fatigue_review_snapshot()` 的 `review_speed_curve` 构造。
- 允许更新 snapshot realignment 和核心红线测试。

边界：
- 不修改 durability 算法公式。
- 不修改空快照 unavailable 主值。
- 不修改前端缺失文案。
- 不修改历史 trend、AI prompt 或骑行专项算法。

验收：
- `row.speed_curve=""` 但 `curves_snapshot.speed` 有足够样本时，durability 接收有效 `speed_stream`。
- decoupling、durability、cadence 继续共享同一个 startup review window。
- 既有 snapshot realignment 测试通过。

## 4. 实现摘要

- `review_speed_curve` 改为从 `curves_snapshot.get("speed")` 构造。
- 仅在 snapshot speed 缺失时使用已解析的 `speed_curve` 变量兜底。
- 更新测试，使其验证 authoritative snapshot speed，而非旧的 `row.speed_curve` 直读行为。

## 5. 验证结果

通过：

```bash
.venv312/bin/python -m pytest -q tests/test_fatigue_review_snapshot_realignment.py
```

结果：32 passed。

红线回归：

```bash
.venv312/bin/python -m unittest discover -s tests -p 'test_fatigue_review_core_audit_regression.py'
```

结果：FR-Core-04 对应用例已转绿；剩余 2 个预期失败继续锚定 FR-Core-05、FR-Core-07。

## 6. 下一任务建议

按清单顺序，下一任务是 `FR-Core-05：空态与 unavailable 主值修复`。

建议执行边界：
- 只修 empty snapshot / unavailable metrics 的主值、status 和 trend 形状。
- 不同时修前端跑步/骑行文案或运动类型路由。
