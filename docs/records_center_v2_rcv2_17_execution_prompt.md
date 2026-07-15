# RCV2-17 工程级执行提示词：骑行固定功率锚点正式纪录 Resolver

## 目标

从 RCV2-16 Power Duration Curve anchors 生成六个固定骑行功率纪录 Evidence，并通过 V2 状态机完成 active/candidate/ignored/unchanged/superseded 的幂等处理。

## 输入摘要

- RCV2-12 已完成 scoped 状态迁移、候选和事件闭环。
- RCV2-16 已完成单活动 Power Duration Curve 与 cache。
- 本任务开始让骑行功率锚点进入正式记录中心事实链，但只通过 `RecordEvidence -> apply_record_evidence_state()`。

## 文件范围

- 允许修改：
  - `career_backend.py`
  - `tests/test_career_record_cycling_power_resolver.py`
  - `docs/records_center_v2_rcv2_17_completion_report.md`
  - `docs/records_center_v2_rolling_contract_summary.md`
  - `docs/运动生涯记录中心V2（多运动纪录）开发任务清单.md`
- 不允许修改：
  - 前端
  - 真实数据库
  - 打包脚本或发布产物
  - eFTP/CP/W′/W/kg 相关正式纪录定义

## 契约边界

- 只处理六个固定锚点：5s、30s、1m、5m、20m、60m。
- 不实现 1s。
- 不把 eFTP、CP、W′、MAP、PMax、W/kg 写为 PB。
- Evidence 必须带 activity-relative range。
- 质量不足只能 candidate 或 ignored。
- 默认入口必须 dry-run，避免误写真实库。

## 实施步骤

1. 新增 duration 到 record_key 的冻结映射。
2. 从 `resolve_cycling_power_duration_curve()` 输出 anchors。
3. 对可用 anchor 构造 `RecordEvidence`：
   - `source_mode=best_effort_duration`
   - `metric_name=power_w`
   - `metric_unit=watts`
   - `scope=sport_scope/indoor_scope/power_metric_scope`
   - `range_data=start_sec/end_sec/duration_sec`
4. 根据 anchor/stream quality 生成 confidence 与 decision。
5. 新增 dry-run plan/apply 入口。
6. 测试 active 建立、替代、tie unchanged、候选、e-bike ignored、重复导入幂等和删除回退。

## 验证

```bash
.venv312/bin/python -m pytest tests/test_career_record_cycling_power_resolver.py tests/test_career_record_cycling_power_curve.py tests/test_career_record_cycling_power_stream.py -q
.venv312/bin/python -m pytest tests/test_career_record_v2_state.py tests/test_career_record_v2_rebuild.py tests/test_career_record_evidence.py tests/test_career_pb_api.py -q
.venv312/bin/python -m py_compile career_backend.py
```

## 完成标准

- 六个固定锚点均可生成 Evidence 并进入状态机。
- 同 scope higher-is-better 替代正常。
- tie 和重复导入不重复 active。
- 质量不足进入候选或忽略。
- 删除 active activity 后可使用既有 fallback 机制恢复同 scope 次优纪录。
