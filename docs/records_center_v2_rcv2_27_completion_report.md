# RCV2-27 越野跑分类与整次活动纪录 Evidence 完成报告

日期：2026-07-15

## 任务目标

严格识别 `trail_running`，并生成距离、爬升、历时、海拔和连续爬升 evidence。

## 本次完成内容

- 新增 `build_trail_activity_total_record_evidences()`：
  - `trail_longest_distance`
  - `trail_max_ascent`
  - `trail_longest_elapsed_time`
  - `trail_max_altitude`
  - `trail_max_single_climb`
- 新增 `apply_trail_activity_total_records()`，默认 dry-run。
- 新增 `_trail_activity_scope()`：
  - 接收 `trail_running/trail_run`。
  - 排除 road running、hiking、mountaineering。
  - 标题不提升类型。
- 复用 RCV2-21 海拔/连续爬升服务。
- 新增 `tests/test_career_record_trail_activity_total.py`。

## 契约保持

- 越野不进入公路跑 PB。
- 不生成跨路线最快标准距离正式纪录。
- 不生成 route PR 或 segment PR；留给后续任务。
- 无真实 trail 样本时保持 candidate-only。
- 不写真实库。
- 不改前端。
- 不打包。

## 验证结果

### RCV2-27 定向

```bash
.venv312/bin/python -m pytest tests/test_career_record_trail_activity_total.py tests/test_career_record_hiking_activity_total.py tests/test_career_record_v2_rebuild.py -q
```

结果：

```text
12 passed, 6 subtests passed in 0.23s
```

### Evidence/API/PB 兼容

```bash
.venv312/bin/python -m pytest tests/test_career_record_evidence.py tests/test_career_records_v2_api.py tests/test_career_pb_api.py -q
.venv312/bin/python -m py_compile career_backend.py
```

结果：

```text
22 passed, 5 subtests passed in 0.16s
```

### 加宽回归

```bash
.venv312/bin/python -m pytest tests/test_career_record_trail_activity_total.py tests/test_career_records_swim_api_surface.py tests/test_career_record_open_water_resolver.py tests/test_career_record_pool_swim_best_effort.py tests/test_career_record_swim_canonical_facts.py tests/test_career_records_hiking_api_surface.py tests/test_career_record_hiking_elevation_climb.py tests/test_career_record_hiking_activity_total.py tests/test_career_records_cycling_api_surface.py tests/test_career_record_cycling_activity_total.py tests/test_career_record_cycling_power_resolver.py tests/test_career_record_cycling_power_curve.py tests/test_career_record_cycling_power_stream.py tests/test_career_record_registry.py tests/test_career_record_schema_migration.py tests/test_career_record_evidence.py tests/test_career_record_v2_state.py tests/test_career_record_v2_rebuild.py tests/test_career_records_v2_api.py tests/test_records_center_v2_golden_fixtures.py tests/test_career_pb_api.py -q
```

结果：

```text
113 passed, 27 subtests passed in 0.62s
```

## 自适应差异复核

- 范围符合 RCV2-27：越野分类与整次 activity-total evidence。
- 未写真实库。
- 未改前端。
- 未打包。
- 未发现阻塞问题。

## 后续任务提示

下一任务为 `RCV2-28 Route Signature 与同路线匹配 candidate-only`。它涉及路线隐私与派生签名，必须只保存不可还原的摘要/匹配指标，不复制完整轨迹。
