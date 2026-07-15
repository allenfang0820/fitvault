# RCV2-23 游泳 canonical facts、Pool Scope 与 schema 补齐完成报告

日期：2026-07-15

## 任务目标

补齐游泳正式纪录所需 canonical facts：water scope、pool length、pool length scope、stroke scope、Length/Lap active time、rest 与距离事实；提供 schema dry-run plan。

## 本次完成内容

- 新增 `SWIM_CANONICAL_ACTIVITY_COLUMNS`：
  - `swim_water_scope`
  - `swim_pool_length_m`
  - `swim_pool_length_scope`
  - `swim_stroke_scope`
  - `swim_facts_quality_json`
- 新增 `plan_swim_canonical_facts_schema_migration()` dry-run。
- 新增 `apply_swim_canonical_facts_schema_migration(dry_run=True)`，默认不写 schema。
- 新增 `normalize_swim_canonical_facts()`：
  - 区分 `pool_swimming` / `open_water_swimming`。
  - 规范化 25m/50m pool length scope。
  - 规范化 stroke scope。
  - 规范化 Length/Lap elapsed、rest、distance、stroke。
  - 缺 pool length 不默认 25m。
  - 码制泳池返回 unsupported。
- 新增 `tests/test_career_record_swim_canonical_facts.py`。

## 契约保持

- 不生成游泳正式纪录。
- 不默认 25m。
- 无 pool length 不自动确认。
- SWOLF 不成为正式纪录。
- 码制泳池不在首发。
- 不写真实库。
- 不改前端。
- 不打包。

## 验证结果

### RCV2-23 定向

```bash
.venv312/bin/python -m pytest tests/test_career_record_swim_canonical_facts.py tests/test_records_center_v2_golden_fixtures.py -q
```

结果：

```text
8 passed in 0.16s
```

### Schema/Registry/API/PB 兼容

```bash
.venv312/bin/python -m pytest tests/test_career_record_schema_migration.py tests/test_career_record_registry.py tests/test_career_records_v2_api.py tests/test_career_pb_api.py -q
.venv312/bin/python -m py_compile career_backend.py
```

结果：

```text
47 passed, 16 subtests passed in 0.20s
```

### 加宽回归

```bash
.venv312/bin/python -m pytest tests/test_career_record_swim_canonical_facts.py tests/test_career_records_hiking_api_surface.py tests/test_career_record_hiking_elevation_climb.py tests/test_career_record_hiking_activity_total.py tests/test_career_records_cycling_api_surface.py tests/test_career_record_cycling_activity_total.py tests/test_career_record_cycling_power_resolver.py tests/test_career_record_cycling_power_curve.py tests/test_career_record_cycling_power_stream.py tests/test_career_record_registry.py tests/test_career_record_schema_migration.py tests/test_career_record_evidence.py tests/test_career_record_v2_state.py tests/test_career_record_v2_rebuild.py tests/test_career_records_v2_api.py tests/test_records_center_v2_golden_fixtures.py tests/test_career_pb_api.py -q
```

结果：

```text
102 passed, 24 subtests passed in 0.53s
```

## 自适应差异复核

- 范围符合 RCV2-23：canonical swim facts、Pool Scope 和 schema dry-run。
- 未生成正式游泳纪录。
- 未写真实库。
- 未改前端。
- 未打包。
- 未发现阻塞问题。

## 后续任务提示

下一任务为 `RCV2-24 泳池 Length/Lap 最佳努力 Resolver`。必须使用 canonical lengths，按 pool length 精确组合距离，休息中断窗口，不能用活动汇总时间替代泳段。
