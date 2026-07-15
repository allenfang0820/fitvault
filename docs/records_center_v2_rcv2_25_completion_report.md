# RCV2-25 公开水域标准距离与整次活动纪录 Resolver 完成报告

日期：2026-07-15

## 任务目标

实现公开水域标准距离和最长距离/历时纪录，并处理 GPS 误差和质量。

## 本次完成内容

- 新增 `OPEN_WATER_RECORD_KEY_BY_DISTANCE`。
- 新增 `_open_water_track_quality()`：
  - 对合成 XY 轨迹识别明显 GPS 跳点。
  - 输出 `open_water_gps_unreliable`。
- 新增 `build_open_water_record_evidences()`：
  - 750m、1500m、1900m、3800m、5K、10K 标准距离。
  - 使用整次活动距离，容差 `±5%`，边界包含。
  - 比较主值为 elapsed time。
  - 生成 `open_water_longest_distance` 与 `open_water_longest_elapsed_time`。
  - 与泳池严格分离。
- 新增 `apply_open_water_records()`，默认 dry-run。
- 新增 `tests/test_career_record_open_water_resolver.py`。

## 契约保持

- 不做公开水域活动内 best-effort 分段。
- 不与泳池混排。
- 水流/天气不进入事实判断。
- candidate-only，不强写真实样本。
- 不写真实库。
- 不改前端。
- 不打包。

## 验证结果

### RCV2-25 定向

```bash
.venv312/bin/python -m pytest tests/test_career_record_open_water_resolver.py tests/test_career_record_swim_canonical_facts.py -q
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
22 passed, 5 subtests passed in 0.14s
```

### 加宽回归

```bash
.venv312/bin/python -m pytest tests/test_career_record_open_water_resolver.py tests/test_career_record_pool_swim_best_effort.py tests/test_career_record_swim_canonical_facts.py tests/test_career_records_hiking_api_surface.py tests/test_career_record_hiking_elevation_climb.py tests/test_career_record_hiking_activity_total.py tests/test_career_records_cycling_api_surface.py tests/test_career_record_cycling_activity_total.py tests/test_career_record_cycling_power_resolver.py tests/test_career_record_cycling_power_curve.py tests/test_career_record_cycling_power_stream.py tests/test_career_record_registry.py tests/test_career_record_schema_migration.py tests/test_career_record_evidence.py tests/test_career_record_v2_state.py tests/test_career_record_v2_rebuild.py tests/test_career_records_v2_api.py tests/test_records_center_v2_golden_fixtures.py tests/test_career_pb_api.py -q
```

结果：

```text
108 passed, 24 subtests passed in 0.58s
```

## 自适应差异复核

- 范围符合 RCV2-25：公开水域整次活动 resolver。
- 未写真实库。
- 未改前端。
- 未打包。
- 未发现阻塞问题。

## 后续任务提示

下一任务为 `RCV2-26 游泳正式纪录、Catalog、API 与测试闭环`。重点是 pool/open-water 独立 scope、candidate/active 状态、Catalog validation 状态和安全 ViewModel。
