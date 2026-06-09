# P1 运动复盘算法链路回正完成报告

## 1. 本次目标

- 正式执行 `docs/p1_fatigue_review_algorithm_realignment_prompt.md`。
- 废弃复盘主路径中基于 `hr_curve/speed_curve` 构造伪 records 的方案。
- 改用真实 FIT / DB canonical 数据：`activities` 标量 + `track_json/points_json` 轨迹点 + Resolver / GapCalculator 后端算法。
- 保持 P1 边界：不改前端草图、不接 AI 洞察、不做 DB schema 大迁移。

## 2. 数据来源调查矩阵

| 字段 | 来源 | 单位 | 可信级别 | 缺失策略 |
|---|---|---|---|---|
| `sport_type` | `activities.sport_type` | 枚举 | resolver truth | 缺失使用 `running` 兜底，后续可降级为 `unknown` |
| `calories` | `activities.calories` | kcal | fit_sdk canonical | 缺失为 0，bonk 不触发 |
| `total_distance_m` | 优先 `activities.dist_km * 1000`，其次 `activities.distance`，最后 records 末点距离 | m | fit_sdk canonical / backend derived | 全缺失时 0 |
| `duration_sec` | `activities.duration_sec`，其次 `activities.duration` | s | fit_sdk canonical | 缺失为 0 |
| `track_points` | `track_json` / `points_json` / `merged_track_json` | 点数组 | fit_sdk persisted points | 缺失时曲线空态 |
| `time_curve_sec` | 轨迹点 `time` 解析后的首点相对秒 | s | fit_sdk point truth | 无有效时间点则空数组 |
| `distance_curve_m` | `MetricsResolver._convert_track_to_algorithm_records()` 基于点序列后端累积 | m | backend derived from fit_sdk points | 无轨迹点则空数组，前端不得补算 |
| `altitude_curve_m` | 轨迹点 `alt/altitude/enhanced_altitude` | m | fit_sdk point truth | 缺失时 GAP/grade 降级为空或不可用 |
| `hr_curve` | 轨迹点 `hr/heart_rate`，兜底 `activities.hr_curve` | bpm | fit_sdk sampled curve | 缺失时效率/bonk 降级 |
| `speed_curve_mps` | 轨迹点 `speed/enhanced_speed` 或后端由 pace 转换 | m/s | fit_sdk / backend derived | 缺失时 GAP/efficiency 降级 |
| `grade_curve` | `GapCalculator.calculate(records)` | % | backend algorithm from fit_sdk | 输入不足返回空数组 |
| `gap_curve` | `GapCalculator.calculate(records)` | m/s | backend algorithm from fit_sdk | 输入不足返回空数组 |
| `efficiency_curve` | `GapCalculator.calculate(records)` | m/s/bpm | backend algorithm from fit_sdk | HR/GAP 不足返回 0 或空 |
| `fatigue_zones` | `MetricsResolver._calculate_fatigue_zones(distance_curve_m, efficiency_curve, sport_type)` | km range | backend algorithm from fit_sdk | 曲线不足返回空数组 |
| `collapse_events` | `MetricsResolver._detect_bonk_event(distance_curve_m, efficiency_curve, calories, sport_type)` | event | backend algorithm from fit_sdk | calories 或曲线不足返回空数组 |

## 3. 修改文件

- `main.py`
- `metrics_resolver.py`
- `tests/test_fatigue_review_resolver_realignment.py`

## 4. 算法链路变更

- 新增 `_build_fatigue_review_curve_bundle(row)`：从 `track_json / points_json / merged_track_json` 构造后端内部 canonical curve bundle。
- `_build_resolved_payload_v81()` 改为消费 bundle，不再从 `hr_curve/speed_curve` 构造伪 records。
- `_build_fatigue_review_snapshot(row)` 改为输出后端权威：
  - `curves.distance`：由 `distance_curve_m` 转 km。
  - `curves.time`：由 `time_curve_sec` 输出。
  - `curves.altitude`：由真实轨迹点海拔输出。
  - `curves.grade/gap/efficiency`：由 Resolver / GapCalculator 基于真实 records 输出。
- `MetricsResolver.resolve()` 显式向 `_detect_bonk_event()` 传入 `sport_type`。
- `MetricsResolver.resolve()` 将 `grade_curve` 放入 `final_data`，供复盘快照读取。

## 5. 废弃伪 records 说明

- 复盘主路径不再固定 `altitude=100.0`。
- 复盘主路径不再固定 `dt=1s` 冒充真实采样时间。
- 复盘主路径不再使用 `session_mesgs=[{}]` 导致 calories 缺失。
- 复盘主路径不再通过 `speed * dt` 构造 canonical 距离。
- records 仅作为后端内部算法适配结构，不进入 API data、不进入 AI snapshot、不写 DB。

## 6. 测试变更

- 新增 `tests/test_fatigue_review_resolver_realignment.py`，覆盖：
  - bundle 使用 `track_json` 真实轨迹点。
  - resolved payload 使用真实 distance/time/altitude/calories。
  - snapshot 输出后端权威距离、时间、海拔曲线。
  - 主路径源码不再包含固定 altitude、空 session、固定 dt。
  - Resolver bonk 调用显式传入 `sport_type`。

## 7. 验证结果

验证命令：

```bash
python -m pytest tests/test_fatigue_review_resolver_realignment.py tests/test_fatigue_review_contract_realignment.py tests/test_fatigue_review_e2e_contract.py tests/test_fatigue_review_envelope.py tests/test_fatigue_zones_resolver.py
```

验证结果：

```text
exit_code = 0
```

诊断结果：

- `main.py`：无新增诊断。
- `tests/test_fatigue_review_resolver_realignment.py`：无诊断。
- `metrics_resolver.py`：仅存在既有 hint 级提示，未出现错误级诊断。

## 8. 未处理事项

- P2：将 P1 输出进一步整理为稳定后端快照层，并补充缺失来源的空态策略。
- P3/P4：前端删除 `_distanceFromSpeedTime()` 事实推导并按草图消费后端权威曲线。
- P6：AI 洞察仍暂缓，待复盘功能跑通后接入。

## 9. 下一步建议

- 进入 P2 后端快照回正。
- P2 重点检查 `get_fatigue_review` 对不同数据形态的行为：有 GPS、有海拔、室内无 GPS、缺 calories、短轨迹。
- P2 完成后再处理前端展示，避免前端继续为缺失字段做事实推导。
