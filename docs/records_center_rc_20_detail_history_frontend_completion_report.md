# RC-20 纪录详情与演进视图完成报告

完成日期：2026-07-13

## 本轮目标

在记录中心当前纪录视图中提供轻量详情与演进入口，消费 RC-17 的 detail/history API。

## 实现范围

- `track.html`
  - 当前纪录区新增 `career-pb-detail-panel`。
  - 当前纪录卡新增 `查看演进` 按钮，携带 `data-record-id` 与 `data-pb-type`。
  - `normalizeCareerDetailLink()` 支持 `record_id/recordId`。
  - 新增 `renderCareerPbDetailPanel(detail, history)`。
  - 新增 `loadCareerPbDetail(recordId, pbType)`。
  - 新增 `openCareerRecordDetailFromElement(event, el)`。
  - 新增详情与历史节点 CSS。
- `tests/test_career_archives_frontend_render.py`
  - 覆盖 detail panel DOM。
  - 覆盖详情按钮 data contract。
  - 覆盖 `get_career_pb_detail` / `get_career_pb_history` 调用。
  - 覆盖演进列表容器与节点。

## 约束

- 当前纪录卡原本的 Activity 回跳能力保留。
- “查看演进”按钮使用 `stopPropagation()`，避免误触发 Activity 详情。
- 前端只展示后端 `record/value_display/improvement_display/history` 字段，不计算纪录事实。

## 验证

```bash
.venv312/bin/python -m pytest tests/test_career_archives_frontend_render.py -q
# 14 passed

.venv312/bin/python -m pytest tests/test_career_archives_frontend_render.py tests/test_career_phase8_frontend_readiness.py tests/test_career_record_maintenance_api.py tests/test_career_pb_api.py tests/test_career_record_lifecycle.py tests/test_career_record_rebuild.py tests/test_career_record_incremental_evaluation.py tests/test_career_record_state_migration.py tests/test_career_record_schema_migration.py tests/test_career_record_registry.py tests/test_career_pb_resolver.py tests/test_career_timeline_pb_nodes.py -q
# 85 passed, 13 subtests passed

.venv312/bin/python -m py_compile career_backend.py main.py
# passed
```

## 复核结论

RC-20 已完成纪录详情与演进视图基础。后续 RC-21 进入候选纪录确认与拒绝视图。

