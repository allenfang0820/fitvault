# RCV2-05 工程级执行提示词

任务：Schema、Curve Cache、Route 数据与回滚冻结

目标：冻结 Records Center V2 的数据结构、唯一性、缓存语义、migration 顺序和失败回滚方案，并明确不创建与 `career_pb_records` 重叠的事实表。

输入摘要：

- `RCV2-03` 已冻结 Registry、record keys、source_mode、scope_dimensions 和 Catalog 可用性。
- `RCV2-04` 已冻结质量评分、阈值、reason codes、candidate-only/validation-required 优先级和日志安全边界。
- 当前代码已有 `career_pb_records`、`career_record_events`、`career_event_candidates`，并已有 V1 扩展列：`evidence_key/source_mode/sport_scope/previous_record_id/resolver_version/confirmed_at/rejected_at/invalidated_at/decision_source/decided_at`。
- 当前 active 唯一索引是 `pb_type, source_mode, sport_scope WHERE status='active'`；V2 需要扩展到结构化 Scope，但必须兼容 legacy。

前置依赖：`RCV2-03`、`RCV2-04`。

文件范围：

- 可写：本提示词、`docs/records_center_v2_rcv2_05_schema_cache_route_contract.md`、完成报告、滚动摘要、V2 任务清单。
- 禁止：业务代码、真实 schema migration、API contract、前端、真实库、打包产物。

冻结契约：

- 继续复用 `career_pb_records` 作为正式纪录事实表，不新建同义 `records`/`personal_records`。
- `career_record_events` 继续 append-only；候选继续复用 `career_event_candidates`。
- Curve Cache 和 Route Signature 都是派生数据，不是 canonical record，不得保存 raw FIT、完整轨迹、真实 GPS 点或路径。
- 第一次真实数据评估只允许副本 dry-run；没有用户批准不得 apply 真实库。
- Migration 必须幂等、可 dry-run、可失败回滚、可保留 V1 历史。

实施步骤：

1. 审计当前 V1 表、字段和索引可复用性。
2. 冻结 V2 `career_pb_records` 新增/兼容字段与 legacy row 迁移策略。
3. 冻结 active 唯一键、evidence 幂等键和 scope hash 策略。
4. 冻结 Curve Cache 表、fingerprint、失效和安全边界。
5. 冻结 Route Signature/Route Match 派生表与不复制完整轨迹原则。
6. 冻结 migration 顺序、dry-run 报告、失败回滚、真实库冲突处理。
7. 写索引计划和测试计划。
8. 更新滚动摘要和任务状态。

非目标：

- 不实现 migration 代码。
- 不创建或修改真实数据库。
- 不调整 API/前端。
- 不删除 V1 历史或旧字段。

验证：

- 文档检查：必须包含现有三张表复用、active scope 唯一性、curve/route 非 canonical、dry-run/rollback、安全禁止字段。
- 运行 golden fixture 测试，确保后续 cache/route 仍引用 privacy-safe fixtures。

完成定义：

- `RCV2-10` 可以直接按本文实现 schema migration、curve cache 和 route 派生数据，不需要临时决定列名、JSON 字段、唯一性或回滚语义。
