# RCV2-20 徒步运动边界与 Activity-total Evidence 完成报告

日期：2026-07-15

## 任务目标

实现 hiking 与 walking/mountaineering/trail_running 的严格分离，并生成徒步整次活动 evidence：最长距离、累计爬升、最长 elapsed time、最高海拔。

## 本次完成内容

- 收紧 `_activity_sport_for_record_dispatch()`：
  - `hiking/hike/trekking` 归为 `hiking`。
  - `walking/walk/casual_walking/indoor_walking` 保持 `walking`。
  - `mountaineering/mountain_climbing/alpine_climbing` 保持 `mountaineering`。
  - `trail_running` 继续保持越野跑。
- 新增 `build_hiking_activity_total_record_evidences()`：
  - `hiking_longest_distance`
  - `hiking_max_ascent`
  - `hiking_longest_elapsed_time`
  - `hiking_max_altitude`
- 新增 `apply_hiking_activity_total_records()`，默认 `dry_run=True`。
- 标题不参与类型提升；即使 title 包含 hiking，`walking/mountaineering/trail_running` 仍被排除。
- `duration` fallback 会降级为 candidate，reason code 为 `duration_semantics_unknown`。
- 新增 `tests/test_career_record_hiking_activity_total.py`。

## 契约保持

- 不实现最大连续爬升；留给 RCV2-21。
- 不合并 walking/mountaineering/trail_running。
- 不设置跨路线最快配速。
- 不修改前端。
- 不写真实库。
- 不打包。

## 验证结果

### RCV2-20 定向

```bash
.venv312/bin/python -m pytest tests/test_career_record_hiking_activity_total.py tests/test_career_record_v2_rebuild.py -q
```

结果：

```text
9 passed, 3 subtests passed in 0.21s
```

### Evidence/API/PB 兼容

```bash
.venv312/bin/python -m pytest tests/test_career_record_evidence.py tests/test_career_records_v2_api.py tests/test_career_pb_api.py -q
.venv312/bin/python -m py_compile career_backend.py
```

结果：

```text
22 passed, 5 subtests passed in 0.14s
```

### 加宽回归

```bash
.venv312/bin/python -m pytest tests/test_career_record_hiking_activity_total.py tests/test_career_records_cycling_api_surface.py tests/test_career_record_cycling_activity_total.py tests/test_career_record_cycling_power_resolver.py tests/test_career_record_cycling_power_curve.py tests/test_career_record_cycling_power_stream.py tests/test_career_record_registry.py tests/test_career_record_schema_migration.py tests/test_career_record_evidence.py tests/test_career_record_v2_state.py tests/test_career_record_v2_rebuild.py tests/test_career_records_v2_api.py tests/test_records_center_v2_golden_fixtures.py tests/test_career_pb_api.py -q
```

结果：

```text
93 passed, 24 subtests passed in 0.47s
```

## 自适应差异复核

- 范围符合 RCV2-20：徒步运动边界和 activity-total evidence。
- 默认 dry-run。
- 未写真实库。
- 未改前端。
- 未打包。
- 未发现阻塞问题。

## 后续任务提示

下一任务为 `RCV2-21 海拔质量与最大连续爬升 Resolver`。必须注意：不能用整次累计爬升冒充最大连续爬升；最大连续爬升必须来自可回溯的 Activity 内 range。
