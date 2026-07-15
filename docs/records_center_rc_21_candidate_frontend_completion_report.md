# RC-21 候选纪录确认与拒绝视图完成报告

完成日期：2026-07-13

## 本轮目标

在记录中心前端展示待确认候选纪录，并提供 confirm/reject 操作入口。

## 实现范围

- `track.html`
  - 当前纪录区新增 `career-pb-candidate-panel`。
  - 新增 `normalizeCareerRecordCandidate(item)`。
  - 新增 `renderCareerPbCandidates(candidates)`。
  - 新增 `decideCareerPbCandidateFromElement(event, el)`。
  - `loadCareerArchives()` 增加 `api.get_career_event_candidates({ candidate_type: 'pb_record', status: 'candidate' })`。
  - confirm/reject 成功后调用 `loadCareerArchives()` 刷新 current/detail/history/candidates。
- `tests/test_career_archives_frontend_render.py`
  - 覆盖候选面板 DOM。
  - 覆盖候选 API 调用。
  - 覆盖 confirm/reject button data contract。
  - 覆盖 `decide_career_pb_candidate` 调用与刷新。

## 约束

- 前端只提交 candidate id 与 decision。
- 前端不得修改成绩、距离、时间、Activity 或 record key。
- 候选确认后的比较和状态迁移全部由后端完成。

## 验证

```bash
.venv312/bin/python -m pytest tests/test_career_archives_frontend_render.py -q
# 15 passed

.venv312/bin/python -m pytest tests/test_career_archives_frontend_render.py tests/test_career_phase8_frontend_readiness.py tests/test_career_record_maintenance_api.py tests/test_career_pb_api.py tests/test_career_record_lifecycle.py tests/test_career_record_rebuild.py tests/test_career_record_incremental_evaluation.py tests/test_career_record_state_migration.py tests/test_career_record_schema_migration.py tests/test_career_record_registry.py tests/test_career_pb_resolver.py tests/test_career_timeline_pb_nodes.py -q
# 86 passed, 13 subtests passed

.venv312/bin/python -m py_compile career_backend.py main.py
# passed
```

## 复核结论

RC-21 已完成候选纪录确认与拒绝视图。后续 RC-22 进入页面状态、响应式、无障碍与刷新反馈。

