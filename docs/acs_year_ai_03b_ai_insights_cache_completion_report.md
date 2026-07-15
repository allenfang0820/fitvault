# ACS-Year-AI-03B career_ai_insights schema 与缓存仓储完成报告

## 状态

Done。

## 交付内容

- 新增独立 AI 输出缓存表 `career_ai_insights`。
- 字段包含 `id`、`scope`、`scope_key`、`snapshot_fingerprint`、`snapshot_version`、`prompt_version`、`model_id`、`content_json`、`generated_at`、`created_at`、`updated_at`、`status`。
- 冻结唯一约束：`scope + scope_key + snapshot_fingerprint + prompt_version + model_id`。
- 新增查询索引：
  - `idx_career_ai_insights_scope_key_status_generated`
  - `idx_career_ai_insights_scope_status_generated`
- 新增仓储函数：
  - `insert_career_ai_insight`
  - `activate_career_ai_insight`
  - `save_ready_career_ai_insight`
  - `get_career_ai_insight_by_id`
  - `get_career_ai_insight_by_cache_key`
  - `get_current_career_ai_insight`

## 契约边界

- `ready` 只能通过 `content_validated=True` 的激活/保存路径写入。
- 新成功报告会在同一事务内把同一 `scope/scope_key` 下旧 `ready` 标记为 `superseded`。
- 多年份、多 fingerprint、多 Prompt 和多模型记录保留用于审计，但每个年度当前展示版本只保留一个 `ready`。
- 缓存表不写 Activity、Race、PB、Achievement、照片或全生涯 Snapshot 表。
- 本任务不调用 LLM、不新增 pywebview API、不改前端。

## 验证

```text
.venv312/bin/python -m pytest tests/test_career_ai_insights_repository.py tests/test_career_year_snapshot_persistence.py tests/test_career_year_report_state.py -q
20 passed, 4 subtests passed in 0.24s

.venv312/bin/python -m pytest tests/test_career_snapshot_persistence.py tests/test_career_snapshot_builder.py -q
16 passed in 0.23s

.venv312/bin/python -m py_compile career_backend.py
passed
```

## Review 结论

通过。03B diff 只触达年度 AI 缓存表、仓储函数、测试和文档；迁移在 `ensure_career_schema` savepoint 内可重复执行，失败会 rollback；旧 `career_snapshots` 数据在迁移失败测试中保持不丢失；未发现事实表写入或年度缓存覆盖全生涯 Snapshot 的路径。
