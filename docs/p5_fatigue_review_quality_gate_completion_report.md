# P5 运动复盘测试与文档固化完成报告

## 1. 本次目标

- 正式执行 P5 测试门禁 / 文档固化。
- 将 P0-P4 已完成的数据契约、算法链路、后端快照、前端零推断和 UI 结构固化为长期回归门禁。
- 保持 P5 边界：不改复盘算法、不接 AI 洞察、不做 UI 大改、不做 DB schema 迁移。

## 2. 修改文件

- `tests/test_fatigue_review_quality_gate.py`
- `docs/fatigue_review_realignment_plan_v1.md`
- `docs/detail_tab_review_manual_test_checklist.md`
- `docs/p5_fatigue_review_quality_gate_completion_report.md`

## 3. 新增/强化测试

新增 `tests/test_fatigue_review_quality_gate.py`，集中覆盖 P0-P4 长期门禁：

- 前端零推断：
  - 禁止 `_distanceFromSpeedTime`。
  - 禁止 `speed / sum(speed)`。
  - 禁止 `speed * 1s`。
  - 禁止 `total_distance_m` 均分距离轴。
  - `openFatigueReview()` 的 `distance_curve` 只能来自 `curvesObj.distance`。
- 后端 snapshot 白名单：
  - 顶层字段严格等于 P0/P2 契约。
  - `curves` 字段严格等于 P2 契约。
  - 任意层级禁止 `shadow_diff / shadow_diff_json / diff / records / points / raw_records / track_points`。
- 曲线同源：
  - 非空可绘图曲线长度必须与 `curves.distance` 一致。
  - `fatigue_zones` 和 `collapse_events` 坐标为后端数字字段。
- P4 UI 结构：
  - 保留 `fr-review-layout / fr-status-strip / fr-core-metrics-section / fr-capacity-metrics-section / fr-context-panel / fr-events-panel / fr-advice-panel / fatigue-review-chart`。
  - 保留 8 个指标卡目标 id。
  - 复盘相关 id 不重复。
- AI 边界：
  - `__FATIGUE_REVIEW_INSIGHT__` sentinel 保留。
  - 前端 AI 调用只传 sentinel + sportType。
  - 前端不拼 prompt、不传 metrics / curves / points。
  - P5 不新增 AI DB 写入路径。

## 4. 文档更新

- `docs/fatigue_review_realignment_plan_v1.md`
  - 新增状态总览。
  - 标记 P0-P5 已完成。
  - 标记 P6 待执行。
  - 补充 P5 已固化门禁。
  - 补充 P6 AI 边界提醒。
- `docs/detail_tab_review_manual_test_checklist.md`
  - 新增 P5 质量门禁测试命令。
  - 新增 P5 门禁覆盖点：前端零推断、后端白名单、forbidden 隔离、曲线同源、P4 UI、AI 边界。

## 5. 验证结果

验证命令：

```bash
python3 -m pytest tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py tests/test_fatigue_review_e2e_contract.py tests/test_fatigue_review_snapshot_realignment.py tests/test_fatigue_review_resolver_realignment.py tests/test_fatigue_review_contract_realignment.py tests/test_fatigue_review_envelope.py
```

验证结果：

```text
100 passed, 1 warning
```

说明：

- warning 来自本机 urllib3 / LibreSSL 版本提示，与本次 P5 修改无关。
- 本机无 `python` 命令，继续使用 `python3` 完成验证。

## 6. 未处理事项

- P6：复盘 AI 洞察最后接入。
- P6 需要修复 `__FATIGUE_REVIEW_INSIGHT__` 分支，并确保 AI 只消费后端权威 snapshot，不读取前端 payload，不写 DB，不进入 `ai_snapshots`。

## 7. 下一步建议

- 进入 P6 AI 洞察接入前，先编写 P6 提示词。
- P6 应复用 P5 质量门禁，并额外增加 AI prompt / normalizer / sentinel / 错误空态测试。
