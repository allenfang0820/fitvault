# RCV2-16 单活动功率持续时间曲线与缓存完成报告

日期：2026-07-15

## 任务目标

基于 RCV2-15 的骑行功率流规范化结果，实现单活动 Power Duration Curve resolver，计算固定持续时间窗口的时间加权最佳功率锚点，并接入 `career_record_curve_cache` 派生缓存。

## 本次完成内容

- 新增 `resolve_cycling_power_duration_curve()`：
  - 复用 `normalize_cycling_power_stream_for_records()` 的 `clean_points/quality_summary`。
  - 默认窗口：5s、30s、60s、300s、1200s、3600s。
  - 基于 step intervals 做精确时间加权积分。
  - 不跨 RCV2-15 识别出的 gap。
  - tie 选择更早的 activity-relative range。
  - 活动短于窗口时输出 unavailable anchor，reason code 为 `activity_shorter_than_window`。
- 新增 Power Curve helper：
  - `_cycling_power_stream_hash()`
  - `_cycling_power_intervals_from_clean_points()`
  - `_cycling_power_interval_groups()`
  - `_integrate_power_intervals()`
  - `_best_cycling_power_window()`
  - `_cycling_power_anchor()`
- 接入 Curve Cache：
  - 使用 `compute_career_record_curve_input_fingerprint()` 计算输入指纹。
  - 使用 `get_career_record_curve_cache()` 读取命中。
  - 使用 `save_career_record_curve_cache()` 写入 miss 结果。
  - cache 只保存安全 anchors/quality，不保存 `clean_points`、`power_points`、raw FIT 或原始功率流。
  - 由于 cache 安全规则禁止 `points` 键，缓存落库时只存 anchors；resolver 命中缓存时从 anchors 派生展示 points。
- 新增 `tests/test_career_record_cycling_power_curve.py`：
  - clean 非 1Hz time-weighted anchor。
  - gap/missing/spike 不跨断点。
  - cache miss/hit。
  - tie 选择更早 range。

## 契约保持

- 不写 active record。
- 不创建候选。
- 不调用 `apply_record_evidence_state()`。
- 曲线是派生缓存，不反向成为正式纪录事实。
- 不把 1s、eFTP、CP、W′、MAP、PMax 或 W/kg 写成 PB。
- 不把 raw stream 返回前端。

## 触碰文件

- `career_backend.py`
- `tests/test_career_record_cycling_power_curve.py`
- `docs/records_center_v2_rcv2_16_execution_prompt.md`

## 验证结果

### Power Curve + Power Stream 定向测试

```bash
.venv312/bin/python -m pytest tests/test_career_record_cycling_power_curve.py tests/test_career_record_cycling_power_stream.py -q
```

结果：

```text
8 passed in 0.10s
```

### Schema/Cache + API + Rebuild 兼容

```bash
.venv312/bin/python -m pytest tests/test_career_record_schema_migration.py tests/test_career_records_v2_api.py tests/test_career_record_v2_rebuild.py -q
.venv312/bin/python -m py_compile career_backend.py
```

结果：

```text
23 passed, 3 subtests passed in 0.20s
```

### 加宽回归

```bash
.venv312/bin/python -m pytest tests/test_career_record_cycling_power_curve.py tests/test_career_record_cycling_power_stream.py tests/test_career_record_registry.py tests/test_career_record_evidence.py tests/test_career_records_v2_api.py tests/test_career_record_v2_state.py tests/test_career_record_v2_rebuild.py tests/test_records_center_v2_golden_fixtures.py tests/test_career_pb_api.py -q
```

结果：

```text
65 passed, 18 subtests passed in 0.33s
```

## 自适应差异复核

- 范围符合 RCV2-16：新增曲线 resolver、cache integration 和测试。
- 未修改前端。
- 未写真实库。
- 未创建正式纪录或候选。
- 未打包。
- 未发现阻塞问题。

## 后续任务提示

下一任务为 `RCV2-17 骑行固定功率锚点正式纪录 Resolver`。它应从 `resolve_cycling_power_duration_curve()` 的 anchors 生成 `RecordEvidence`，并通过 `apply_record_evidence_state()` 接入 V2 状态机；必须保留 activity-relative range、Scope 和质量原因，质量不足只进入候选或忽略。
