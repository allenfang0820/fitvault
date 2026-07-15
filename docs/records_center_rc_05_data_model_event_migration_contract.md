# RC-05 数据模型、审计事件与迁移回滚冻结

日期：2026-07-13

## 执行提示词

目标：在兼容现有 `career_pb_records` 的前提下，冻结历史链、审计事件、唯一性、索引、migration 和失败回滚方案。

范围：`career_pb_records` 字段语义与新增字段、`career_record_events` append-only 表、唯一性/索引、migration 幂等、失败回滚、删除/重算保留策略。

约束：不新建与 `career_pb_records` 含义重叠的 `records` 表；不实现 migration 代码；不写真实数据库。

完成定义：RC-12 可直接按冻结 schema 实现，不再临时改变表意图。

## 1. 兼容原则

继续使用：

```text
career_pb_records
```

禁止新建同义事实表：

```text
records
records_history
personal_records
```

允许新增：

- `career_pb_records` 结构化字段。
- `career_record_events` append-only 审计表。
- 必要索引和唯一性约束。

旧版 `get_career_pb()` 必须继续读取 active 记录；迁移后旧字段仍存在，不能依赖一次性破坏性重建。

## 2. `career_pb_records` 字段冻结

现有字段继续保留：

| 字段 | 语义 |
| --- | --- |
| `id` | 稳定纪录实例 ID |
| `activity_id` | 来源 Activity，必填 |
| `sport` | 规范化运动类型 |
| `pb_type` | Registry `record_key` |
| `value` | 规范化比较值，跑步为整数秒；当前 TEXT |
| `value_unit` | 规范化单位，跑步为 `seconds` |
| `improvement` | 相对前一条正式纪录的提升值；首条为 null |
| `event_date` | Activity 本地运动日期 |
| `confidence` | Resolver 置信度 |
| `source` | `resolver` / `user_confirmed` / `migration` |
| `status` | `candidate` / `active` / `superseded` / `rejected` / `invalidated` |
| `display_metadata_json` | 白名单解释字段 |
| `created_at` | 创建时间 |
| `updated_at` | 更新时间 |

新增字段冻结：

| 字段 | 类型 | 默认 | 语义 |
| --- | --- | --- | --- |
| `evidence_key` | TEXT | `''` | 同一 Activity 内证据去重 |
| `source_mode` | TEXT | `'activity_total'` | `activity_total` / future `best_effort_segment` |
| `sport_scope` | TEXT | `'default'` | 同一 sport/source 下的范围，用于未来公路/越野拆分 |
| `previous_record_id` | TEXT | null | 上一条正式纪录 ID |
| `resolver_version` | TEXT | `'legacy'` for old rows, `records-v1` for new rows |
| `confirmed_at` | TEXT | null | 用户确认候选时间 |
| `rejected_at` | TEXT | null | 用户拒绝候选时间 |
| `invalidated_at` | TEXT | null | 失效时间 |
| `decision_source` | TEXT | null | `user` / `resolver` / `migration` |
| `decided_at` | TEXT | null | 最近一次候选决策时间 |

迁移旧行默认：

- `source_mode = 'activity_total'`
- `sport_scope = 'default'`
- `resolver_version = 'legacy'`
- `evidence_key = 'activity_total:' || activity_id || ':' || pb_type || ':' || value`

## 3. `value` 数值比较策略

当前 `value` 为 TEXT，不允许字符串排序。

跑步 V1：

```text
numeric_value = CAST(value AS INTEGER)
value_unit = 'seconds'
```

代码化要求：

- Resolver 内部使用整数 `elapsed_time_sec`。
- 写表前转为字符串保存到 `value`，直到 NUMERIC migration 单独实施。
- 查询和重建比较必须按 `value_unit` 转换。
- 非数字、NaN、无穷、空字符串不得进入 active。

未来迁移策略：

- 可新增 `numeric_value REAL`，但不能在 RC-12 前改变 V1 兼容读取。
- 若新增 numeric 字段，必须提供从 `value/value_unit` 回填和回滚验证。

## 4. `career_record_events` append-only schema

新增表：

```sql
CREATE TABLE IF NOT EXISTS career_record_events (
    id TEXT PRIMARY KEY,
    pb_record_id TEXT NOT NULL,
    pb_type TEXT NOT NULL,
    activity_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    old_status TEXT,
    new_status TEXT,
    previous_record_id TEXT,
    resolver_version TEXT NOT NULL DEFAULT 'records-v1',
    run_id TEXT,
    evidence_key TEXT NOT NULL DEFAULT '',
    reason_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

允许的 `event_type`：

- `detected`
- `candidate_created`
- `user_confirmed`
- `user_rejected`
- `activated`
- `superseded`
- `invalidated`
- `recalculated`
- `migration_backfilled`
- `activated_from_rebuild`

不可变约束：

- 事件只追加，不 update，不 delete。
- 若需要纠错，追加 `recalculated` 或新事件，不改旧事件。
- `reason_json` 只保存白名单摘要，不保存 raw FIT、轨迹、本地路径、SQLite schema。

事件 ID 建议：

```text
record_event:{event_type}:{pb_record_id}:{resolver_version}:{stable_hash}
```

`stable_hash` 可由 `activity_id/evidence_key/old_status/new_status/run_id` 组成，用于幂等。

## 5. 唯一性与索引

必须保证同一范围最多一条 active：

```sql
CREATE UNIQUE INDEX IF NOT EXISTS ux_career_pb_active_scope
ON career_pb_records(pb_type, source_mode, sport_scope)
WHERE status = 'active';
```

同一证据幂等：

```sql
CREATE UNIQUE INDEX IF NOT EXISTS ux_career_pb_evidence
ON career_pb_records(pb_type, activity_id, evidence_key, resolver_version);
```

查询索引：

```sql
CREATE INDEX IF NOT EXISTS idx_career_pb_status_type_date
ON career_pb_records(status, sport, pb_type, event_date);

CREATE INDEX IF NOT EXISTS idx_career_pb_activity
ON career_pb_records(activity_id);

CREATE INDEX IF NOT EXISTS idx_career_record_events_record
ON career_record_events(pb_record_id, created_at);

CREATE INDEX IF NOT EXISTS idx_career_record_events_run
ON career_record_events(run_id, event_type);

CREATE INDEX IF NOT EXISTS idx_career_record_events_activity
ON career_record_events(activity_id, pb_type);
```

SQLite 兼容策略：

- 优先使用 partial unique index。
- 若目标平台 SQLite 版本不支持或迁移失败，必须在事务内执行 active scope 检查，并用测试覆盖。
- RC-29 Windows 验收必须验证 partial index 或 fallback 行为。

## 6. Migration 顺序

RC-12 实现时按以下顺序：

1. 开启事务。
2. 确认 `career_pb_records` 存在；不存在则创建完整新 schema。
3. 对缺失字段逐一 `ALTER TABLE ADD COLUMN`。
4. 回填旧行默认字段。
5. 创建 `career_record_events`。
6. 创建普通索引。
7. 检查 active scope 是否已有冲突。
8. 若无冲突，创建 active partial unique index。
9. 写入 migration audit event 或 schema migration 记录。
10. 提交事务。

active 冲突处理：

- 不得静默删除或覆盖。
- 若旧库已有多个 active，migration 应停止在应用计划前，输出冲突报告。
- 用户确认或 rebuild 任务解决冲突后再创建唯一约束。

## 7. 失败回滚

事务失败：

- rollback 后旧 `career_pb_records` 必须仍可由 `get_career_pb()` 读取。
- 不得先清空 active 再重建。
- 不得留下部分新增字段依赖的业务状态。

迁移脚本要求：

- 每一步幂等，可重复执行。
- 对已存在字段/索引/表不报错。
- 对字段回填只填空值，不覆盖已有结构化值。
- 失败时返回明确错误和建议，不触发 Resolver 正式重算。

## 8. 删除、软删除与重算保留策略

Activity 软删除：

- 来源 active/superseded/candidate 标记为 `invalidated`。
- 写 `invalidated` event。
- 不物理删除 PB 记录。

Activity 重新导入：

- 若 Activity ID 复用且关键证据变化，旧 evidence invalidated，新 evidence 重新检测。
- 若新 Activity ID 表示同一文件/语义重复，导入层先去重，PB 层再用 evidence key 幂等。

Resolver 版本变化：

- 保留旧记录和事件。
- 新规则应用时写 `recalculated` / `migration_backfilled`。
- 规则变化导致 active 替换，不发送庆祝通知。

用户拒绝：

- `rejected` 保留，不删除。
- 同一 evidence 同版本不得重复出现。

## 9. 旧版本兼容

旧 API：

- `get_career_pb()` 继续查询 `status='active'`。
- 旧字段 `value/improvement/display_metadata_json` 继续可读。
- 新字段缺失时后端应使用兼容默认值。

旧测试：

- 现有 `tests/test_career_pb_resolver.py`
- 现有 `tests/test_career_pb_api.py`
- 现有 `tests/test_career_timeline_pb_nodes.py`

迁移实现后必须继续通过。

## 10. 测试计划

| 编号 | 场景 | 预期 |
| --- | --- | --- |
| DB-001 | 空库 ensure schema | 创建 `career_pb_records` 和 `career_record_events` |
| DB-002 | 旧 schema 缺新增字段 | 幂等添加字段 |
| DB-003 | 重复 migration | 无副作用 |
| DB-004 | 旧 active 行回填 | `source_mode/activity_total`、`resolver_version/legacy` |
| DB-005 | active 唯一约束 | 同 scope 第二条 active 失败或事务检查拒绝 |
| DB-006 | 同 evidence 重复写入 | 不生成重复 PB |
| DB-007 | 事件 append-only | 不 update/delete 旧事件 |
| DB-008 | migration 中途失败 | rollback 后旧 active 可读 |
| DB-009 | `value` TEXT 数值比较 | `"100"` 优于 `"99"` 不因字符串排序误判 |
| DB-010 | soft delete active 来源 | active invalidated 并准备回退 |
| DB-011 | Windows SQLite | partial index 或 fallback 验证通过 |

## 11. RC-12 实现输入

RC-12 需要实现：

- schema migration helper。
- 新字段回填。
- `career_record_events` 创建。
- active scope 唯一性保护。
- evidence 唯一性保护。
- migration 幂等测试。
- rollback/失败保护测试。
