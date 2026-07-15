# RCV2-15 骑行功率流规范化与质量检测完成报告

日期：2026-07-15

## 任务目标

实现 Records Center V2 专用的骑行功率流规范化与质量检测，把不同设备和采样频率的功率点转换为后续 Power Duration Curve 可消费的稳定内部结构，并输出安全质量摘要与 reason codes。

## 本次完成内容

- 新增 `normalize_cycling_power_stream_for_records()`：
  - 支持 `t/time_sec/elapsed_sec/elapsed_time_sec/timestamp/time` 时间字段。
  - 支持 `power_w/power/watts/enhanced_power/Power` 功率字段。
  - 将绝对时间或相对时间归一为 Activity-relative `t_sec`。
  - 保留 `0W` 作为有效滑行功率。
  - 将缺失、负值、非数值与无效时间戳从 clean stream 中排除，并记录质量原因。
  - 支持非 1Hz 采样的 time-weighted average。
  - 使用配置阈值和采样中位间隔共同识别不可跨越 gap，避免把干净非 1Hz 流误判为断点。
  - 检测短时功率尖峰并从 `clean_points` 中剔除。
  - 排除 e-bike scope。
- 新增 `build_cycling_power_stream_quality_summary()`：
  - 只返回安全质量摘要，不返回 raw points、power stream 或 FIT 内容。
  - 输出 `quality/confidence/reason_codes/candidate_only/scope/coverage/sampling` 等安全字段。
- 新增功率来源标签清洗：
  - 保留安全 `power_source` 标签。
  - 遇到路径、storage、设备序列号、token、体重历史等敏感内容时降级为 `raw_power_w`。
- 新增 `tests/test_career_record_cycling_power_stream.py`：
  - 覆盖 clean 非 1Hz、0W、缺失、断点、尖峰、e-bike 排除、字段别名和确定性输出。

## 契约保持

- 不写真实库。
- 不生成 active record。
- 不创建候选。
- 不接入 `apply_record_evidence_state()`。
- 不把汇总 `avg/max/NP` 替代逐点功率流。
- 不把 W/kg、NP、eFTP、CP、W′、MAP、PMax 注册为正式纪录。
- 不把 raw stream 返回前端。

## 触碰文件

- `career_backend.py`
- `tests/test_career_record_cycling_power_stream.py`
- `docs/records_center_v2_rcv2_15_execution_prompt.md`

## 验证结果

### RCV2-15 定向与 fixture

```bash
.venv312/bin/python -m pytest tests/test_career_record_cycling_power_stream.py tests/test_records_center_v2_golden_fixtures.py -q
```

结果：

```text
8 passed in 0.23s
```

### 兼容 API/Evidence/PB 与编译

```bash
.venv312/bin/python -m pytest tests/test_career_record_evidence.py tests/test_career_records_v2_api.py tests/test_career_pb_api.py -q
.venv312/bin/python -m py_compile career_backend.py
```

结果：

```text
22 passed, 5 subtests passed in 0.23s
```

### 加宽回归

```bash
.venv312/bin/python -m pytest tests/test_career_record_cycling_power_stream.py tests/test_career_record_registry.py tests/test_career_record_v2_state.py tests/test_career_record_v2_rebuild.py tests/test_career_records_v2_api.py tests/test_career_record_evidence.py tests/test_records_center_v2_golden_fixtures.py tests/test_career_pb_api.py -q
```

结果：

```text
61 passed, 18 subtests passed in 0.28s
```

## 自适应差异复核

- 范围符合 RCV2-15：新增纯计算 adapter、质量摘要和单测。
- 未修改前端。
- 未修改真实数据库。
- 未接入正式纪录状态迁移。
- 未打包。
- 未发现阻塞问题。

## 后续任务提示

下一任务为 `RCV2-16 单活动功率持续时间曲线与缓存`。它应复用本任务的 `clean_points`，计算 5s、30s、1m、5m、20m、60m 等固定窗口与可扩展曲线锚点，并写入 `career_record_curve_cache` 派生缓存。仍不得切换 active record，且不得向前端返回 raw stream。
