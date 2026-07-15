# RCV2-22 徒步正式纪录、Catalog、API 与测试闭环完成报告

日期：2026-07-15

## 任务目标

完成徒步五项正式纪录、历史链、Catalog 和前端所需 ViewModel：最长距离、最大累计爬升、最长 elapsed、最高海拔、最大连续爬升。

## 本次完成内容

- 新增 `tests/test_career_records_hiking_api_surface.py`。
- 验证 Catalog：
  - 只展示 `hiking`。
  - 不展示 walking/mountaineering 占位。
  - `hiking_max_single_climb` 在 hiking group 中可见，但不作为 current active。
- 验证 Records API：
  - 四项 activity-total active 纪录可通过 `get_career_records({"sport": "hiking"})` 展示。
  - `hiking_max_single_climb` 只进入候选。
- 验证 Detail/History/Candidates：
  - detail_link 仍为 `source="career"`。
  - history axis 为 higher。
  - 候选列表包含 `hiking_max_single_climb`。
- 验证删除回退：
  - 删除 active activity 后同 scope superseded fallback 可恢复。

## 契约保持

- `hiking_max_single_climb` 仍为 candidate-only，不进入 current active。
- 不合并 walking/mountaineering/trail_running。
- 不实现通用最快 5K/10K 或 VAM。
- 不改前端。
- 不写真实库。
- 不打包。

## 验证结果

### RCV2-22 定向

```bash
.venv312/bin/python -m pytest tests/test_career_records_hiking_api_surface.py tests/test_career_record_hiking_elevation_climb.py tests/test_career_record_hiking_activity_total.py -q
```

结果：

```text
9 passed, 3 subtests passed in 0.13s
```

### 状态机/API/PB 兼容

```bash
.venv312/bin/python -m pytest tests/test_career_record_v2_state.py tests/test_career_records_v2_api.py tests/test_career_pb_api.py -q
.venv312/bin/python -m py_compile career_backend.py
```

结果：

```text
23 passed in 0.16s
```

### 加宽回归

```bash
.venv312/bin/python -m pytest tests/test_career_records_hiking_api_surface.py tests/test_career_record_hiking_elevation_climb.py tests/test_career_record_hiking_activity_total.py tests/test_career_records_cycling_api_surface.py tests/test_career_record_cycling_activity_total.py tests/test_career_record_cycling_power_resolver.py tests/test_career_record_cycling_power_curve.py tests/test_career_record_cycling_power_stream.py tests/test_career_record_registry.py tests/test_career_record_schema_migration.py tests/test_career_record_evidence.py tests/test_career_record_v2_state.py tests/test_career_record_v2_rebuild.py tests/test_career_records_v2_api.py tests/test_records_center_v2_golden_fixtures.py tests/test_career_pb_api.py -q
```

结果：

```text
98 passed, 24 subtests passed in 0.53s
```

## 自适应差异复核

- 范围符合 RCV2-22：徒步 Catalog/API/候选/回退闭环。
- 未写真实库。
- 未改前端。
- 未打包。
- 未发现阻塞问题。

## 后续任务提示

下一任务为 `RCV2-23 游泳 canonical facts、Pool Scope 与 schema 补齐`。必须补齐 pool length/water scope/stroke/length-lap canonical facts；不得默认 25m；无 pool length 不自动确认。
