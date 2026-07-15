# RCV2-24 泳池 Length/Lap 最佳努力 Resolver 完成报告

日期：2026-07-15

## 任务目标

从连续有效 Length/Lap 中生成 50m、100m、200m、400m、800m、1500m 最佳用时 evidence。

## 本次完成内容

- 新增 `POOL_SWIM_RECORD_KEY_BY_DISTANCE`。
- 新增 `build_pool_swim_best_effort_evidences()`：
  - 使用 RCV2-23 canonical lengths。
  - 按 pool length 精确组合目标距离。
  - 不使用距离容差。
  - 休息中断窗口。
  - 记录 `length_start/length_end/lap_count/distance_m`。
  - 分离 `water_scope/pool_length_scope/stroke_scope`。
- 新增 `apply_pool_swim_best_effort_records()`，默认 dry-run。
- 新增 `tests/test_career_record_pool_swim_best_effort.py`。

## 契约保持

- 无 pool length 不生成 evidence，不默认 25m。
- 活动汇总时间不替代泳段。
- validation-required 只进入候选，不进入 active。
- 无真实泳池样本时只使用 fixture 验证。
- 不改前端。
- 不写真实库。
- 不打包。

## 验证结果

### RCV2-24 定向

```bash
.venv312/bin/python -m pytest tests/test_career_record_pool_swim_best_effort.py tests/test_career_record_swim_canonical_facts.py -q
```

结果：

```text
7 passed in 0.17s
```

### Evidence/API/PB 兼容

```bash
.venv312/bin/python -m pytest tests/test_career_record_evidence.py tests/test_career_records_v2_api.py tests/test_career_pb_api.py -q
.venv312/bin/python -m py_compile career_backend.py
```

结果：

```text
22 passed, 5 subtests passed in 0.17s
```

### 加宽回归

```bash
.venv312/bin/python -m pytest tests/test_career_record_pool_swim_best_effort.py tests/test_career_record_swim_canonical_facts.py tests/test_career_records_hiking_api_surface.py tests/test_career_record_hiking_elevation_climb.py tests/test_career_record_hiking_activity_total.py tests/test_career_records_cycling_api_surface.py tests/test_career_record_cycling_activity_total.py tests/test_career_record_cycling_power_resolver.py tests/test_career_record_cycling_power_curve.py tests/test_career_record_cycling_power_stream.py tests/test_career_record_registry.py tests/test_career_record_schema_migration.py tests/test_career_record_evidence.py tests/test_career_record_v2_state.py tests/test_career_record_v2_rebuild.py tests/test_career_records_v2_api.py tests/test_records_center_v2_golden_fixtures.py tests/test_career_pb_api.py -q
```

结果：

```text
105 passed, 24 subtests passed in 0.58s
```

## 自适应差异复核

- 范围符合 RCV2-24：泳池 best-effort evidence。
- 未写真实库。
- 未改前端。
- 未打包。
- 未发现阻塞问题。

## 后续任务提示

下一任务为 `RCV2-25 公开水域标准距离与整次活动纪录 Resolver`。必须使用整次活动匹配 `±5%`，candidate-only，不与泳池混排。
