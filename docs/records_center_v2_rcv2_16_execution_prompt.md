# RCV2-16 工程级执行提示词：单活动功率持续时间曲线与缓存

## 目标

基于 RCV2-15 的骑行功率流规范化结果，实现单活动 Power Duration Curve resolver，计算固定持续时间窗口的时间加权最佳功率锚点，并接入 `career_record_curve_cache` 派生缓存。

## 输入摘要

- RCV2-15 已提供 `normalize_cycling_power_stream_for_records()` 与安全 `quality_summary`。
- Curve Cache 表与 helper 已由 RCV2-10 完成：
  - `compute_career_record_curve_input_fingerprint()`
  - `save_career_record_curve_cache()`
  - `get_career_record_curve_cache()`
  - `invalidate_career_record_curve_cache()`
- Curve 是派生缓存，不是正式纪录事实源。
- 前端只能消费安全 anchors/points/ViewModel，不能读取 raw stream。

## 文件范围

- 允许修改：
  - `career_backend.py`
  - `tests/test_career_record_cycling_power_curve.py`
  - `docs/records_center_v2_rcv2_16_completion_report.md`
  - `docs/records_center_v2_rolling_contract_summary.md`
  - `docs/运动生涯记录中心V2（多运动纪录）开发任务清单.md`
- 不允许修改：
  - 前端
  - 真实数据库
  - 打包脚本或发布产物
  - 与记录中心 V2 无关模块

## 契约边界

- 不写 active record。
- 不创建候选。
- 不调用 `apply_record_evidence_state()`。
- 不返回 raw FIT、完整 points、clean_points、power_stream、本地路径或设备标识。
- 缓存只保存派生 anchors/points/quality 与 fingerprint。

## 实施步骤

1. 新增 Power Duration Curve 算法版本和默认窗口：5s、30s、60s、300s、1200s、3600s。
2. 基于 `clean_points` 构造不可跨 gap 的 step intervals。
3. 使用精确积分计算每个固定窗口的最佳平均功率。
4. tie 选择更早 activity-relative range。
5. 活动短于窗口时输出 unavailable anchor，reason code 为 `activity_shorter_than_window`。
6. 每个 anchor 包含 `value/duration_sec/unit/range/quality`。
7. 生成安全 `curve`：
   - `curve_type`
   - `algorithm_version`
   - `anchors`
   - `points`
   - `axis`
8. 生成安全 `quality`。
9. 用 safe hash 作为 stream summary hash，计算 cache fingerprint。
10. 接入 cache read/write，记录 hit/miss/elapsed_ms。

## 验证

```bash
.venv312/bin/python -m pytest tests/test_career_record_cycling_power_curve.py tests/test_career_record_cycling_power_stream.py -q
.venv312/bin/python -m pytest tests/test_career_record_schema_migration.py tests/test_career_records_v2_api.py tests/test_career_record_v2_rebuild.py -q
.venv312/bin/python -m py_compile career_backend.py
```

必要时加宽到 Registry/Evidence/PB。

## 完成标准

- 5s 至 60m anchor 结构稳定。
- 0W、缺失、暂停、非 1Hz、短活动和 tie 均有测试。
- cache hit/miss 可验证。
- cache 中不保存 raw stream。
- V2 API、schema/cache 和 V1 PB 无回归。
