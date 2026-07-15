# RCV2-10 工程级执行提示词

任务：Scope schema migration 与 Curve Cache 基础设施

目标：实现 V2 结构化 Scope、V2 active/evidence 索引、Curve Cache、Route Signature/Match 派生表和只读 dry-run 计划能力，同时保持 V1 `career_pb_records`、事件、候选和旧 PB API 兼容。

输入摘要：

- `RCV2-05` 已冻结 schema/cache/route 契约。
- `RCV2-09` 已代码化 V2 Registry/Catalog。
- 当前 schema 已有 V1 扩展字段和事件表；本任务补 V2 字段、派生表、索引和测试。

前置依赖：`RCV2-05`、`RCV2-09`。

文件范围：

- 可写：`career_backend.py`、schema migration 测试、本文、完成报告、滚动摘要、任务清单。
- 禁止：真实库 apply、前端、API contract JSON、打包产物。

冻结契约：

- 继续复用 `career_pb_records`，不新建重叠事实表。
- Curve Cache、Route Signature、Route Match 是派生数据，不是 canonical record。
- 不存 raw path、完整 track、raw power stream、真实 GPS 点或体重历史。
- migration 必须幂等；失败回滚不丢 V1 历史。
- dry-run 只读，不写表。

实施步骤：

1. 新增 scope canonicalization helper。
2. 扩展 `career_pb_records` 创建 schema 与补列逻辑。
3. 回填 legacy rows 的 V2 字段。
4. 扩展 `career_record_events` 创建 schema 与补列逻辑。
5. 新建 curve cache、route signatures、route matches 表。
6. 新增 V2 索引。
7. 新增只读 dry-run 计划函数。
8. 扩展 schema migration 测试：空库、legacy、幂等、dry-run、回滚、索引、表结构、安全字段。
9. 运行定向测试和 py_compile。

非目标：

- 不实现 curve 计算。
- 不实现 route matching 算法。
- 不接 V2 API bridge。
- 不写真实库。

验证：

- `.venv312/bin/python -m pytest tests/test_career_record_schema_migration.py tests/test_career_record_registry.py -q`
- `.venv312/bin/python -m pytest tests/test_career_pb_api.py tests/test_records_center_v2_golden_fixtures.py -q`
- `.venv312/bin/python -m py_compile career_backend.py`

完成定义：

- 空库/V1 legacy 库重复初始化一致，V1 查询无回归，V2 scope/cache/route 表和索引存在，dry-run 不写库。
