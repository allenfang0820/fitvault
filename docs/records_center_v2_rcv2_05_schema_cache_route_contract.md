# RCV2-05 Schema、Curve Cache、Route 数据与回滚契约

完成时间：2026-07-14

本文冻结 Records Center V2 的 schema 扩展、唯一性、Curve Cache、Route Signature、migration dry-run 和失败回滚方案。后续 `RCV2-10` 必须以本文为实现依据；不得创建与 `career_pb_records` 重叠的正式纪录事实表，不得把派生缓存当作 canonical record。

## 1. 当前 schema 可复用性审计

当前代码已具备并必须复用：

| 表/对象 | 当前用途 | V2 决策 |
| --- | --- | --- |
| `career_pb_records` | 正式纪录、历史纪录、候选状态字段所在表 | 继续作为唯一正式纪录事实表。 |
| `career_record_events` | append-only 纪录事件表 | 继续 append-only，V2 可扩展 payload 白名单。 |
| `career_event_candidates` | 候选事件/候选 PB 容器 | 继续复用，V2 候选 evidence 放入安全 JSON。 |
| `career_schema_meta` | schema version 记录 | 继续复用，V2 migration bump version。 |
| `ux_career_pb_records_active_scope` | V1 active 唯一约束：`pb_type/source_mode/sport_scope` | V2 迁移到 scope hash 唯一键前保留兼容。 |
| `ux_career_pb_records_evidence_version` | V1 evidence 幂等 | V2 扩展 evidence_key 规则，保留旧索引兼容。 |

当前 `career_pb_records` 已有 V1 扩展列：

```text
evidence_key
source_mode
sport_scope
previous_record_id
resolver_version
confirmed_at
rejected_at
invalidated_at
decision_source
decided_at
display_metadata_json
```

V2 不新建以下同义事实表：

```text
records
records_history
personal_records
career_records
career_record_history
```

## 2. `career_pb_records` V2 扩展字段

V2 在保留旧字段的前提下新增结构化 Scope 和范围字段。

| 字段 | 类型 | 默认 | 语义 |
| --- | --- | --- | --- |
| `record_key` | TEXT | null | V2 Registry key；迁移期与 `pb_type` 同步。 |
| `record_family` | TEXT | null | V2 family，如 `power_duration_pb`。 |
| `scope_json` | TEXT | `'{}'` | 后端解析后的结构化 Scope，只含白名单键。 |
| `scope_key` | TEXT | `'default'` | 动态 route/segment 实例 key；静态纪录为 `default`。 |
| `scope_hash` | TEXT | `''` | canonical scope JSON 的稳定 hash，用于唯一性。 |
| `range_json` | TEXT | `'{}'` | Activity 内范围，如功率窗口、泳段、爬升区间、赛段范围。 |
| `quality_json` | TEXT | `'{}'` | `QualityDecision` 安全摘要，不含 raw samples。 |
| `metric_value_num` | REAL | null | 比较主值的数值副本；保留 `value` 兼容旧 API。 |
| `metric_name` | TEXT | null | V2 metric，如 `power_w`、`elapsed_time_sec`。 |
| `catalog_state` | TEXT | null | 写入时的 Registry/Catalog 状态快照。 |
| `rule_version` | TEXT | null | V2 record definition 规则版本；不同于 resolver_version。 |

兼容规则：

- `pb_type` 继续作为旧 API 字段，V2 写入时必须等于 `record_key`。
- `sport_scope` 保留为 legacy 简化 scope；V2 不再只依赖它表达唯一性。
- `value`/`value_unit` 保留供旧 `get_career_pb*` 读取；V2 比较必须优先使用 `metric_value_num + value_unit + metric_name`。
- `display_metadata_json` 只放展示安全字段；技术质量摘要进 `quality_json`。

legacy row 迁移默认：

| 字段 | 默认值 |
| --- | --- |
| `record_key` | `pb_type` |
| `record_family` | `distance_time_pb` for running V1；无法识别时 `legacy` |
| `scope_json` | `{"sport_scope": sport_scope}` 或 `{}` |
| `scope_key` | `sport_scope` 非空时使用 `sport_scope`，否则 `default` |
| `scope_hash` | canonical scope JSON hash；空 scope 为固定 hash |
| `range_json` | `{}` |
| `quality_json` | 从 `confidence/source/display_metadata_json` 生成安全摘要 |
| `metric_value_num` | 按 `value_unit` 解析 `value`；失败则 null 且不得 active |
| `metric_name` | 跑步 V1 为 `elapsed_time_sec` |
| `catalog_state` | `available` for V1 active/superseded，候选保留原状态 |
| `rule_version` | `records-v1` 或 `legacy` |

## 3. Scope canonicalization 与唯一性

### 3.1 Scope JSON 白名单

`scope_json` 只允许以下键：

```text
sport_scope
indoor_scope
power_metric_scope
pool_length_scope
stroke_scope
water_scope
route_key
segment_key
```

禁止：

- raw GPS points。
- 文件路径、设备序列号、账号、token。
- 体重历史或原始传感器流。
- 前端生成的临时 label。

### 3.2 canonical scope hash

生成规则：

```text
scope_canonical_json = JSON.stringify(scope_json, sort_keys=True, separators=(',', ':'))
scope_hash = 'scope:v2:sha256:' + sha256(scope_canonical_json).hexdigest()
```

空 scope 固定为：

```text
scope:v2:sha256:empty
```

动态实例身份：

```text
record_identity = record_key + "::" + scope_hash
```

route/segment 展示可使用 `scope_key`，但唯一性必须使用 `scope_hash`，避免 label 或 route name 变化破坏历史链。

### 3.3 active 唯一键

V2 目标唯一约束：

```sql
CREATE UNIQUE INDEX IF NOT EXISTS ux_career_pb_records_active_v2_scope
ON career_pb_records(record_key, source_mode, scope_hash)
WHERE status = 'active';
```

迁移期兼容：

- 保留旧 `ux_career_pb_records_active_scope(pb_type, source_mode, sport_scope)`，直到所有 active legacy 行都有 `record_key/scope_hash` 且 V1 API 通过兼容测试。
- 旧索引可能无法表达多维 Scope；V2 写入前必须设置 `sport_scope` 为兼容摘要，例如 `cycling_regular|outdoor|raw_power_w`，但不能让前端依赖该字符串。

active 冲突处理：

- migration dry-run 先检查同一 `record_key/source_mode/scope_hash` 下是否有多个 active。
- 有冲突时不得自动删除或覆盖，生成冲突报告并停止 apply。
- 冲突需由 rebuild 或用户决策处理后再创建 V2 unique index。

### 3.4 evidence 幂等键

V2 evidence key 格式：

```text
evidence:v2:{record_key}:{activity_id}:{source_mode}:{scope_hash}:{range_hash}:{metric_hash}:{rule_version}
```

其中：

- `range_hash` 来自安全 `range_json`。
- `metric_hash` 只包含 canonical metric 数值、单位和必要容差信息，不含 raw stream。
- 同一 evidence 在增量和重建中必须生成相同 key。

目标唯一约束：

```sql
CREATE UNIQUE INDEX IF NOT EXISTS ux_career_pb_records_evidence_v2
ON career_pb_records(record_key, activity_id, evidence_key, resolver_version);
```

保留旧 evidence index，确保旧 PB API 与旧候选不丢失。

## 4. `career_record_events` V2 扩展

保持 append-only，不 update、不 delete。

建议新增字段：

| 字段 | 类型 | 默认 | 语义 |
| --- | --- | --- | --- |
| `record_key` | TEXT | null | V2 record key；与 `pb_type` 兼容。 |
| `scope_hash` | TEXT | `''` | 事件对应 scope。 |
| `scope_key` | TEXT | `'default'` | 动态实例 key。 |
| `run_id` | TEXT | null | 增量、重建或 dry-run 批次 ID。 |
| `decision` | TEXT | null | `QualityDecision.decision` 快照。 |
| `reason_codes_json` | TEXT | `'[]'` | 稳定 reason code 数组。 |

`payload_json` 白名单：

- status 变化摘要。
- old/new metric 安全值。
- quality summary。
- migration/dry-run summary。
- compact range summary。

禁止：

- raw FIT、完整轨迹、真实 GPS 点。
- 文件路径、设备序列号、账号、token。
- SQLite schema dump。
- 体重历史明细。

事件 ID 建议：

```text
record_event:v2:{event_type}:{record_id}:{run_id}:{stable_hash}
```

`stable_hash` 来自 `record_key/scope_hash/evidence_key/old_status/new_status`。

## 5. 候选表扩展策略

继续复用：

```text
career_event_candidates
```

候选 evidence 进入 `evidence_json`，但必须安全裁剪。

V2 candidate JSON 建议结构：

```json
{
  "record_key": "cycling_power_20m",
  "source_mode": "best_effort_duration",
  "scope_hash": "scope:v2:sha256:...",
  "scope": {
    "sport_scope": "cycling_regular",
    "indoor_scope": "outdoor",
    "power_metric_scope": "raw_power_w"
  },
  "metric": {
    "name": "power_w",
    "value": 248,
    "unit": "watts"
  },
  "range": {
    "type": "time_window",
    "start_offset_sec": 1220,
    "end_offset_sec": 2420
  },
  "quality": {
    "decision": "candidate",
    "confidence": 0.84,
    "reason_codes": ["power_stream_gap"]
  }
}
```

候选 JSON 不得包含 raw stream 或完整采样数组。

建议新增候选索引：

```sql
CREATE INDEX IF NOT EXISTS idx_career_event_candidates_type_status_updated
ON career_event_candidates(candidate_type, status, updated_at);
```

若未来需要强幂等，可新增 `candidate_key` 字段；`RCV2-05` 不要求立即新增，避免破坏 V1 候选。

## 6. Curve Cache

Curve Cache 是派生缓存，不是正式纪录事实源。删除或重算 cache 不得改变已经确认的 record，除非 Resolver 明确以相同 Activity facts 重新生成 evidence 并经过状态机。

### 6.1 表结构

建议新增：

```sql
CREATE TABLE IF NOT EXISTS career_record_curve_cache (
    id TEXT PRIMARY KEY,
    activity_id TEXT NOT NULL,
    sport TEXT NOT NULL,
    curve_type TEXT NOT NULL,
    source_mode TEXT NOT NULL,
    scope_hash TEXT NOT NULL DEFAULT '',
    input_fingerprint TEXT NOT NULL,
    algorithm_version TEXT NOT NULL,
    curve_json TEXT NOT NULL DEFAULT '{}',
    quality_json TEXT NOT NULL DEFAULT '{}',
    generated_at TEXT NOT NULL,
    invalidated_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

允许的 `curve_type`：

- `cycling_power_duration_curve`
- `trail_pace_curve`
- `trail_gap_curve`
- `pool_swim_pace_curve`

### 6.2 唯一性与索引

```sql
CREATE UNIQUE INDEX IF NOT EXISTS ux_career_record_curve_cache_current
ON career_record_curve_cache(activity_id, curve_type, source_mode, scope_hash, input_fingerprint, algorithm_version)
WHERE invalidated_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_career_record_curve_cache_activity
ON career_record_curve_cache(activity_id, curve_type, generated_at);
```

### 6.3 fingerprint

`input_fingerprint` 必须只由安全摘要组成：

```text
activity_id
sport
source_mode
record-relevant canonical facts version
stream summary hash
algorithm_version
rule_version
```

`stream summary hash` 可以由采样数量、时间范围、缺失段摘要和数值 hash 生成，但不得存储原始采样值、完整功率流或 GPS 轨迹。

失效条件：

- Activity 相关 canonical facts 改变。
- power/elevation/lap/track derived summary 改变。
- algorithm_version 改变。
- rule_version 改变。
- Activity 删除或重新导入。

Cache miss 只能导致重新计算，不得用旧 cache 伪造 active record。

## 7. Route Signature 与 Route Match 派生数据

Route 数据是匹配派生物，不是 canonical record，也不是完整轨迹备份。

### 7.1 Route Signature 表

建议新增：

```sql
CREATE TABLE IF NOT EXISTS career_route_signatures (
    id TEXT PRIMARY KEY,
    activity_id TEXT NOT NULL,
    sport TEXT NOT NULL,
    route_key TEXT NOT NULL,
    direction_key TEXT NOT NULL,
    distance_m REAL,
    ascent_m REAL,
    duration_sec INTEGER,
    signature_version TEXT NOT NULL,
    signature_json TEXT NOT NULL DEFAULT '{}',
    quality_json TEXT NOT NULL DEFAULT '{}',
    generated_at TEXT NOT NULL,
    invalidated_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

`signature_json` 允许：

- 起终点网格摘要。
- 总距离/总爬升/方向摘要。
- 简化后的 shape hash。
- bounding box 粗粒度摘要。
- 采样数量与覆盖率摘要。

`signature_json` 禁止：

- 完整坐标点。
- 真实经纬度数组。
- 原始轨迹文件路径。
- 可还原用户路线的高精度 polyline。

唯一性：

```sql
CREATE UNIQUE INDEX IF NOT EXISTS ux_career_route_signatures_activity_version
ON career_route_signatures(activity_id, signature_version)
WHERE invalidated_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_career_route_signatures_route_key
ON career_route_signatures(route_key, sport, invalidated_at);
```

### 7.2 Route Match 表

建议新增：

```sql
CREATE TABLE IF NOT EXISTS career_route_matches (
    id TEXT PRIMARY KEY,
    route_key TEXT NOT NULL,
    activity_id TEXT NOT NULL,
    matched_activity_id TEXT NOT NULL,
    match_version TEXT NOT NULL,
    direction TEXT NOT NULL,
    match_score REAL NOT NULL,
    coverage_ratio REAL,
    overlap_ratio REAL,
    length_error_ratio REAL,
    decision TEXT NOT NULL,
    reason_codes_json TEXT NOT NULL DEFAULT '[]',
    generated_at TEXT NOT NULL,
    invalidated_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

唯一性：

```sql
CREATE UNIQUE INDEX IF NOT EXISTS ux_career_route_matches_pair_version
ON career_route_matches(route_key, activity_id, matched_activity_id, match_version)
WHERE invalidated_at IS NULL;
```

默认阈值来自 golden manifest：

- 起终点容差 `100m`。
- 长度误差 `<= 5%`。
- 轨迹覆盖率 `>= 0.95`。
- corridor overlap `>= 0.85`。
- 反向路线 hard-block：`route_direction_mismatch`。
- 低重合 hard-block：`route_match_low_overlap`。

## 8. Migration 顺序

`RCV2-10` 实现时必须支持 `dry_run=True`。

推荐 apply 顺序：

1. 开启事务或 savepoint。
2. 读取 `career_schema_meta`，记录旧 schema version。
3. 确认 V1 表存在；缺失时创建完整新 schema。
4. 对 `career_pb_records` 逐列 `ALTER TABLE ADD COLUMN`，不删除旧列。
5. 回填 legacy rows 的 `record_key/scope_json/scope_key/scope_hash/metric_value_num/metric_name/catalog_state/rule_version`。
6. 扫描 active scope 冲突，不通过则回滚并输出报告。
7. 扩展 `career_record_events` 缺失列。
8. 创建 curve cache、route signatures、route matches 表。
9. 创建普通索引。
10. 创建 V2 unique indexes。
11. 写 schema migration meta 和安全 migration event。
12. 提交事务。

`dry_run=True` 必须：

- 不写任何表。
- 输出将新增的表、列、索引、回填计数、冲突计数、阻塞项。
- 对真实库只允许只读连接或副本。

## 9. 失败回滚

失败回滚要求：

- 任一步失败必须回滚本次 schema 变更。
- 不得删除 V1 历史行。
- 不得清空候选表。
- 不得留下半创建唯一索引导致旧 API 不可用。
- 失败报告必须包含阶段、错误类别、是否已回滚、下一步建议。

冲突处理：

| 冲突 | 行为 |
| --- | --- |
| active scope 冲突 | dry-run 报告，apply 停止。 |
| legacy `value` 无法解析数值 | 保留行，`metric_value_num=null`，该行不得作为 V2 active 比较来源，报告待修复。 |
| scope_json 非法 | 回填安全默认 scope 并标记 reason，或停止 apply；不得猜测前端 scope。 |
| partial unique index 创建失败 | 回滚并使用事务内检查 fallback；Windows 验收必须覆盖。 |
| curve/route 表创建失败 | 回滚本次 migration；不得影响 V1 PB 读取。 |

## 10. 索引计划

必须保留：

```sql
idx_career_pb_records_activity
idx_career_pb_records_sport_type_date
ux_career_pb_records_active_scope
ux_career_pb_records_evidence_version
idx_career_record_events_record
idx_career_record_events_activity_type
idx_career_record_events_evidence
```

V2 目标新增：

```sql
idx_career_pb_records_record_scope_status
ux_career_pb_records_active_v2_scope
ux_career_pb_records_evidence_v2
idx_career_pb_records_catalog_state
idx_career_record_events_record_scope
idx_career_record_events_run_decision
idx_career_event_candidates_type_status_updated
ux_career_record_curve_cache_current
idx_career_record_curve_cache_activity
ux_career_route_signatures_activity_version
idx_career_route_signatures_route_key
ux_career_route_matches_pair_version
```

建议 SQL：

```sql
CREATE INDEX IF NOT EXISTS idx_career_pb_records_record_scope_status
ON career_pb_records(record_key, source_mode, scope_hash, status, event_date);

CREATE INDEX IF NOT EXISTS idx_career_pb_records_catalog_state
ON career_pb_records(catalog_state, status, updated_at);

CREATE INDEX IF NOT EXISTS idx_career_record_events_record_scope
ON career_record_events(record_key, scope_hash, event_at);

CREATE INDEX IF NOT EXISTS idx_career_record_events_run_decision
ON career_record_events(run_id, decision, event_at);
```

## 11. 真实库安全策略

- `RCV2-10` 到 `RCV2-39` 的 schema/Resolver 开发可以用临时库、fixture 或测试库。
- `RCV2-40` 前不得对真实库 apply V2 migration。
- `RCV2-40` 真实数据评估只能先备份和 staging dry-run。
- 没有用户明确批准，不得把 V2 candidate 或 active 写入真实库。
- 用户当前仍要求“不打包”，本 schema 任务不触发 packaging。

## 12. 后续测试计划

`RCV2-10` 至少实现：

- 空库 migration。
- V1 legacy 库 migration。
- 重复 migration 幂等。
- dry-run 不写库，数据库 mtime 不变。
- active scope 冲突报告。
- legacy value 解析失败不丢历史。
- partial unique index 或 fallback 检查。
- migration 中途失败回滚。
- curve cache fingerprint 变化导致 cache invalidation。
- route signature 不包含完整真实轨迹或高精度经纬度。
- 禁止字段扫描：`file_path/storage_ref/device_serial/serial_number/email/token/password/api_key/real_lat/real_lon/weight_history`。
- V1 `get_career_pb*` 在 migration 后兼容。
