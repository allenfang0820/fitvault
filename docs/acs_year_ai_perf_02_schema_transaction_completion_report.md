# ACS 年度 AI 总结性能修复任务 2 完成报告

## 任务

Schema Ensure、事务提交与 SQLite 锁竞争修复。

## 实现

- 增加当前 schema 只读快速路径，同时校验版本号和 11 张必需 ACS 表。
- 当前 schema 的嵌套仓储读取不再执行 DDL、backfill、UPDATE 或 SAVEPOINT。
- 缺表或版本不匹配仍进入完整 migration；失败继续 rollback。
- `generate_career_insight()` 在自有连接中提交 `save_career_snapshot()` 的写入，异常时回滚。
- 外部连接仍保持调用方 commit / rollback 所有权。

## 验证

```text
59 passed, 3 subtests passed
python -m py_compile career_backend.py main.py: passed
git diff --check: passed
```

真实库 query-only 验收：

- SQL 总数：119。
- SELECT：118。
- PRAGMA：1。
- CREATE / ALTER / INSERT / UPDATE / DELETE / SAVEPOINT：0。
- 年度报告状态正常返回 `stale`，未出现 `database is locked`。

跨连接持久化测试证明 `main.Api().generate_career_insight()` 返回后，重新连接仍能读取 `career_snapshot:latest`。
