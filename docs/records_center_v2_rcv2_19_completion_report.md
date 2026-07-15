# RCV2-19 骑行 Catalog、API、Curve ViewModel 与测试闭环完成报告

日期：2026-07-15

## 任务目标

交付骑行后端完整只读表面：Catalog 分组和能力状态、当前纪录、历史、详情、PDC 曲线、W/kg 不可用状态、安全 API 与回归测试闭环。

## 本次完成内容

- 新增 Catalog sport-level `capabilities`：
  - `power_duration_curve`：表达 PDC 可用、curve type、source mode、requires point power 和缺功率 reason code。
  - `activity_total_records`：表达整次活动纪录 key 和 validation-required 纪录。
  - `wkg`：表达 W/kg 当前 unavailable、需要活动日期体重、不会创建 record。
  - `model_estimates`：表达 eFTP/CP/W′/MAP/PMax 仅 model-only，不创建 record。
  - `scope_dimensions`：表达骑行 scope 维度。
- 更新 `docs/js_api_contract.json`：
  - `get_career_record_catalog` returns 增加 `capabilities`。
  - 描述中明确 Catalog 是运动能力状态唯一来源。
- 新增 `tests/test_career_records_cycling_api_surface.py`：
  - Catalog 分组与 capabilities。
  - Records 当前纪录。
  - Detail。
  - History。
  - Curve ViewModel。
  - Candidate。
  - 安全字段扫描。

## 契约保持

- 不新增写接口。
- 不返回 raw FIT、raw points、clean_points、power_points、本地路径、设备序列号或体重历史。
- 无逐点功率活动不得进入 PDC。
- model estimates 只作为 model-only 能力标签，不成为 active record。
- 不修改前端。
- 不打包。
- 不触碰真实库。

## 触碰文件

- `career_backend.py`
- `docs/js_api_contract.json`
- `tests/test_career_records_cycling_api_surface.py`
- `docs/records_center_v2_rcv2_19_execution_prompt.md`

## 验证结果

### RCV2-19 定向

```bash
.venv312/bin/python -m pytest tests/test_career_records_cycling_api_surface.py tests/test_career_record_cycling_activity_total.py tests/test_career_record_cycling_power_resolver.py -q
```

结果：

```text
12 passed in 0.26s
```

### Contract/API/PB/Evidence 兼容

```bash
.venv312/bin/python - <<'PY'
import json
from pathlib import Path
contract=json.loads(Path('docs/js_api_contract.json').read_text())
method=next(m for m in contract['methods'] if m['name']=='get_career_record_catalog')
print('catalog_contract_ok', 'capabilities' in method['returns'], method['readonly'], method['high_risk'])
PY
.venv312/bin/python -m pytest tests/test_career_records_v2_api.py tests/test_career_pb_api.py tests/test_career_record_evidence.py -q
.venv312/bin/python -m py_compile career_backend.py
```

结果：

```text
catalog_contract_ok True True False
22 passed, 5 subtests passed in 0.14s
```

### 加宽回归

```bash
.venv312/bin/python -m pytest tests/test_career_records_cycling_api_surface.py tests/test_career_record_cycling_activity_total.py tests/test_career_record_cycling_power_resolver.py tests/test_career_record_cycling_power_curve.py tests/test_career_record_cycling_power_stream.py tests/test_career_record_registry.py tests/test_career_record_schema_migration.py tests/test_career_record_evidence.py tests/test_career_record_v2_state.py tests/test_career_record_v2_rebuild.py tests/test_career_records_v2_api.py tests/test_records_center_v2_golden_fixtures.py tests/test_career_pb_api.py -q
```

结果：

```text
89 passed, 21 subtests passed in 0.45s
```

## 自适应差异复核

- 范围符合 RCV2-19：只读 Catalog/API/Curve ViewModel 和测试闭环。
- 未新增写接口。
- 未写真实库。
- 未改前端。
- 未打包。
- 未发现阻塞问题。

## 后续任务提示

下一任务为 `RCV2-20 徒步运动边界与 Activity-total Evidence`。重点是严格分离 hiking、walking、mountaineering、trail_running，并只从后端 Activity 安全事实生成徒步整次活动 evidence。
