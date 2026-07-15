# FR-Core-05 缺失、零值、无风险与不可分析状态修复完成报告

日期：2026-07-13  
任务源：`docs/fatigue_review_core_audit_fix_task_list.md`  
状态：已完成

## 1. 交付手册摘要刷新

- `null + unavailable` 表示无法分析；真实计算为零时才允许返回 `0`。
- 前端不得仅凭数组为空或 count 为 0 推断“状态平稳”。
- unavailable 与 available-but-zero 必须通过后端字段显式区分。

## 2. FR-Core-05 任务契约摘要

- 空态 decoupling 主值必须为 `null`，不得是 `0.0`。
- 空态 decoupling 必须显式 `status=unavailable`、`confidence=unavailable`、`direction=unknown`。
- events 必须包含 `analysis_status`，只有 `available && count=0` 才能显示无事件/状态平稳。
- unavailable events 的 trend 保持事件计数形状，但 `delta_count=null`、`level=unknown`。

## 3. 工程级提示词

目标：修复空态和不可分析状态，避免缺失数据被展示成 0% 或状态平稳。

范围：
- 允许修改 `main.py` 中 empty snapshot 和 events metric 形状。
- 允许修改 `track.html` events 卡片显示逻辑。
- 允许更新相关测试与任务清单。

边界：
- 不修改前端 durability 缺失文案。
- 不修改运动类型路由。
- 不修改 durability / decoupling 算法公式。
- 不修改 AI prompt。

验收：
- `_empty_fatigue_review_snapshot().metrics.decoupling.pct is None`。
- unavailable decoupling trend 不携带强趋势。
- events unavailable 时前端不展示“状态平稳”。
- 既有趋势、契约、骑行空态测试通过。

## 4. 实现摘要

- `_empty_fatigue_review_snapshot()` 的 decoupling 改为 unavailable 空态。
- 正常 snapshot 的 events 增加 `analysis_status/confidence/reasons`。
- 前端 running/cycling events 卡片读取 `analysis_status`，unavailable 显示数据不足。
- trend gate 对 events 保留 `delta_count` 形状。

## 5. 验证结果

通过：

```bash
.venv312/bin/python -m pytest -q tests/test_fatigue_review_trends.py
.venv312/bin/python -m pytest -q tests/test_fatigue_review_contract_realignment.py tests/test_fatigue_review_e2e_contract.py tests/test_cycling_fatigue_review_metrics.py
```

红线回归：

```bash
.venv312/bin/python -m unittest discover -s tests -p 'test_fatigue_review_core_audit_regression.py'
```

结果：FR-Core-05 对应用例已转绿；剩余 1 个预期失败继续锚定 FR-Core-07。

## 6. 下一任务建议

按清单顺序，下一任务是 `FR-Core-06：运动类型能力注册表单一真理源`。

但当前红线中还剩 `FR-Core-07：指标卡、缺失原因与运动专项文案分流` 的 running durability 文案问题；若严格按清单，应先做 FR-Core-06 的能力注册表，再做 FR-Core-07。
