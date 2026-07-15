# ACS-Year-AI-03A 年度 Snapshot 持久化与读取完成报告

## 状态

Done。

## 交付内容

- 复用 `career_snapshots` 表保存可重建的年度 Year Snapshot。
- 年度 Snapshot 使用稳定 ID `career_snapshot:year:{year}`。
- 年度 Snapshot 使用 `snapshot_type=career_year` 与 `source_version=acs.year.v1`。
- 新增内部保存函数 `save_career_year_snapshot()`，返回保存时间、版本与 `source_fingerprint`，不返回完整 Snapshot 给普通前端展示。
- 新增内部读取函数 `get_career_year_snapshot()`，读取历史内容时会二次裁剪禁止字段并重新校验年度 Snapshot 契约。
- 保持全生涯 `career_snapshot:latest`、`save_career_snapshot()` 与 `get_latest_career_snapshot()` 隔离。
- 未新增 pywebview 前端任意写 Snapshot API。

## 契约边界

- 年度 Snapshot 仍是派生数据，可由 Activity 与 Resolver facts 重建，不成为 canonical 事实源。
- 保存前执行年度禁止字段递归检查；读取历史脏数据时执行裁剪、fingerprint 重算与契约校验。
- 连接由函数创建时负责 commit / rollback / close；调用方传入连接时保持调用方事务所有权。
- 本任务不调用 LLM、不改前端、不修改全生涯洞察 fallback。

## 验证

```text
.venv312/bin/python -m pytest tests/test_career_year_snapshot_persistence.py tests/test_career_year_report_state.py tests/test_career_year_snapshot_fingerprint.py -q
20 passed, 4 subtests passed in 0.20s

.venv312/bin/python -m pytest tests/test_career_snapshot_persistence.py tests/test_career_snapshot_builder.py -q
16 passed in 0.22s

.venv312/bin/python -m py_compile career_backend.py
passed
```

## Review 结论

通过。diff 触达范围符合 03A：年度 Snapshot 内部持久化、对应测试与任务文档；未发现全生涯 Snapshot 覆盖、pywebview 写接口暴露、普通前端完整 Snapshot 展示或 canonical 事实表写入。
