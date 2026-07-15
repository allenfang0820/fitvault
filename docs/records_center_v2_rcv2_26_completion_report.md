# RCV2-26 游泳正式纪录、Catalog、API 与测试闭环完成报告

日期：2026-07-15

## 任务目标

交付泳池/公开水域独立的正式纪录状态机和安全 ViewModel。

## 本次完成内容

- 新增 `tests/test_career_records_swim_api_surface.py`。
- 验证 Catalog：
  - `pool_swimming` 与 `open_water_swimming` 独立展示。
  - pool records 保持 `validation_required`。
  - open-water records 保持 `candidate_only`。
- 验证 Records API：
  - pool/open-water 不产生 active current records。
  - 候选列表展示 pool/open-water candidates。
  - scope 中包含 water/pool length/stroke。
- 验证安全字段扫描。

## 契约保持

- SWOLF 不成为正式纪录。
- 未知泳姿不自动进入 freestyle PB。
- pool validation-required，不进入 active。
- open-water candidate-only，不进入 active。
- 不写真实库。
- 不改前端。
- 不打包。

## 验证结果

### RCV2-26 定向

```bash
.venv312/bin/python -m pytest tests/test_career_records_swim_api_surface.py tests/test_career_record_pool_swim_best_effort.py tests/test_career_record_open_water_resolver.py -q
```

结果：

```text
8 passed in 0.10s
```

### Contract/API/PB/Evidence 兼容

```bash
.venv312/bin/python - <<'PY'
import json
from pathlib import Path
json.loads(Path('docs/js_api_contract.json').read_text())
print('contract_json_ok True')
PY
.venv312/bin/python -m pytest tests/test_career_records_v2_api.py tests/test_career_pb_api.py tests/test_career_record_evidence.py -q
.venv312/bin/python -m py_compile career_backend.py
```

结果：

```text
contract_json_ok True
22 passed, 5 subtests passed in 0.14s
```

### 加宽回归

```bash
.venv312/bin/python -m pytest tests/test_career_records_swim_api_surface.py tests/test_career_record_open_water_resolver.py tests/test_career_record_pool_swim_best_effort.py tests/test_career_record_swim_canonical_facts.py tests/test_career_records_hiking_api_surface.py tests/test_career_record_hiking_elevation_climb.py tests/test_career_record_hiking_activity_total.py tests/test_career_records_cycling_api_surface.py tests/test_career_record_cycling_activity_total.py tests/test_career_record_cycling_power_resolver.py tests/test_career_record_cycling_power_curve.py tests/test_career_record_cycling_power_stream.py tests/test_career_record_registry.py tests/test_career_record_schema_migration.py tests/test_career_record_evidence.py tests/test_career_record_v2_state.py tests/test_career_record_v2_rebuild.py tests/test_career_records_v2_api.py tests/test_records_center_v2_golden_fixtures.py tests/test_career_pb_api.py -q
```

结果：

```text
110 passed, 24 subtests passed in 0.59s
```

## 自适应差异复核

- 范围符合 RCV2-26：游泳 Catalog/API surface。
- 未写真实库。
- 未改前端。
- 未打包。
- 未发现阻塞问题。

## 后续任务提示

下一任务为 `RCV2-27 越野跑分类与整次活动纪录 Evidence`。重点是 trail_running 严格分类，不混入 road running/hiking/mountaineering。
