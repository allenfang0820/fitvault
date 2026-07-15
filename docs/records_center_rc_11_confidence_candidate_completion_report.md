# RC-11 置信度、原因码与候选生成完成报告

完成日期：2026-07-13

## 本轮目标

实现记录中心 V1 的可解释置信度评分与候选决策纯逻辑，为后续 schema migration 和 PB 状态迁移提供稳定契约。

## 实现范围

- `career_backend.py`
  - 新增 `RECORD_CONFIDENCE_AUTO_THRESHOLD = 0.90`。
  - 新增 `RECORD_CONFIDENCE_CANDIDATE_THRESHOLD = 0.70`。
  - 新增 `score_record_confidence(summary, match)`。
  - 新增 `record_evidence_key(summary, match)`。
  - 新增 `build_record_candidate_decision(summary, match=None)`。
- `tests/test_career_record_registry.py`
  - 增加高置信自动确认测试。
  - 增加旧 timer/time semantics 降级 candidate 测试。
  - 增加缺距离、缺时间、距离不匹配 ignored 测试。
  - 增加 evidence key 幂等测试。

## 决策契约

- `confidence > 0.90`：`decision = auto_confirm`，`confidence_level = high`。
- `0.70 <= confidence <= 0.90`：`decision = candidate`，`confidence_level = medium`。
- `confidence < 0.70`：`decision = ignored`，`confidence_level = low`。
- V1 evidence key 格式：`activity_total:{activity_id}:{record_key}:{distance_m}:{elapsed_time_sec}`。
- 所有降级都输出稳定英文 `reason_codes`。

## 特别约束

- 本轮只新增纯函数与测试。
- 未接入当前 `resolve_pb_records()` 写入链路。
- 未修改真实数据库 schema。
- 未改变现有 active PB 结果。

## 验证

```bash
.venv312/bin/python -m pytest tests/test_career_record_registry.py tests/test_career_pb_resolver.py -q
# 25 passed, 13 subtests passed

.venv312/bin/python -m pytest tests/test_career_record_registry.py tests/test_career_pb_resolver.py tests/test_career_pb_api.py tests/test_career_timeline_pb_nodes.py -q
# 39 passed, 13 subtests passed

.venv312/bin/python -m py_compile career_backend.py
# passed
```

## 复核结论

RC-11 diff 只增加 Records 置信度/候选决策纯逻辑和解释性测试；没有写库、迁移或 UI/API 行为变化。工作区仍存在大量既有脏改，后续任务继续按任务边界定向复核。

