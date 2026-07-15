# RCV2-21 海拔质量与最大连续爬升 Resolver 完成报告

日期：2026-07-15

## 任务目标

可靠生成徒步海拔质量与最大连续爬升证据，防止 GPS 高度尖峰污染纪录，并保证最大连续爬升结果可回溯 Activity 内 range。

## 本次完成内容

- 新增 `resolve_hiking_elevation_climb()`：
  - 读取 `alt_m/altitude_m/altitude/alt`。
  - 支持 `t/time_sec/elapsed_sec` 与 `d/distance_m/distance`。
  - 识别孤立高度尖峰/谷值。
  - 剔除尖峰后计算最大连续爬升。
  - 输出 `spike_point_indexes`、`reason_codes`、`max_single_climb`。
- 新增 `build_hiking_single_climb_record_evidence()`：
  - 生成 `hiking_max_single_climb` evidence。
  - metric 为 `single_climb_m` / `meters_ascent`。
  - range 包含 `start_sec/end_sec/start_distance_m/end_distance_m`。
- 新增 `apply_hiking_single_climb_record()`：
  - 默认 dry-run。
  - 显式 apply 时通过 V2 状态机创建候选。
  - 因 Registry `candidate_only`，不进入 active。
- 新增 `tests/test_career_record_hiking_elevation_climb.py`：
  - 使用 golden fixture 验证海拔尖峰。
  - 验证最大连续爬升 range。
  - 验证无轨迹不会使用整次累计爬升冒充。

## 契约保持

- 不用整次累计爬升冒充最大连续爬升。
- 无轨迹不生成 `hiking_max_single_climb`。
- 异常高度只进入 candidate/ignored。
- 不写路线速度纪录。
- 不改前端。
- 不写真实库。
- 不打包。

## 验证结果

### RCV2-21 定向

```bash
.venv312/bin/python -m pytest tests/test_career_record_hiking_elevation_climb.py tests/test_career_record_hiking_activity_total.py -q
```

结果：

```text
7 passed, 3 subtests passed in 0.18s
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
.venv312/bin/python -m pytest tests/test_career_record_hiking_elevation_climb.py tests/test_career_record_hiking_activity_total.py tests/test_career_records_cycling_api_surface.py tests/test_career_record_cycling_activity_total.py tests/test_career_record_cycling_power_resolver.py tests/test_career_record_cycling_power_curve.py tests/test_career_record_cycling_power_stream.py tests/test_career_record_registry.py tests/test_career_record_schema_migration.py tests/test_career_record_evidence.py tests/test_career_record_v2_state.py tests/test_career_record_v2_rebuild.py tests/test_career_records_v2_api.py tests/test_records_center_v2_golden_fixtures.py tests/test_career_pb_api.py -q
```

结果：

```text
96 passed, 24 subtests passed in 0.49s
```

## 自适应差异复核

- 范围符合 RCV2-21：海拔质量和最大连续爬升。
- 默认 dry-run。
- 未写真实库。
- 未改前端。
- 未打包。
- 未发现阻塞问题。

## 后续任务提示

下一任务为 `RCV2-22 徒步正式纪录、Catalog、API 与测试闭环`。重点是把 RCV2-20/21 的五项徒步纪录接入只读表面、候选/事件/回退测试和 Catalog 验收。
