# P1 骑行复盘快照入源与数据质量完成报告

## 1. 本次目标

- 按 `docs/p1_cycling_fatigue_review_snapshot_prompt.md` 执行 P1-cycling。
- 让骑行复盘快照稳定输出同轴 `curves.power / curves.cadence`。
- 完善 `summary.power_data_quality / cadence_data_quality`，区分 missing、insufficient_points、invalid_values、length_mismatch、available。
- 确保 AI compact snapshot 只保留 power/cadence 摘要和计数，不携带全量曲线。
- 不实现骑行评分算法，不改前端 ECharts，不改 LLM 输出，不改 DB schema。

## 2. 数据来源调查

### activities 字段

当前 `_fetch_activity_row()` 使用 `DETAIL_API_REQUIRED_COLUMNS` 白名单读取活动详情，已覆盖复盘需要的字段：

- `avg_power`
- `max_power`
- `normalized_power`
- `avg_cadence`
- `cadence_curve`
- `track_json`
- `points_json`
- `merged_track_json`
- `sport_type`
- `duration / duration_sec`
- `dist_km / distance`

### track_json 点结构

`_build_fatigue_review_curve_bundle(row)` 通过 `MetricsResolver._convert_track_to_algorithm_records(track_points)` 将点转换成内部 records。

当前可用情况：

- `power_curve` 来源：track records 中的 `power`。
- `cadence_curve` 来源：activities 表中的 `cadence_curve` JSON。
- `distance_curve_m` 来源：records 中的累计 `distance`。
- `time_curve_sec` 来源：records timestamp 与起点 timestamp 的差值。

`MetricsResolver._convert_track_to_algorithm_records()` 当前会透传：

- `timestamp`
- `heart_rate`
- `speed`
- `altitude`
- `distance`
- `power`

### bundle / snapshot 当前行为

- `_build_fatigue_review_curve_bundle(row)` 已输出 `power_curve / cadence_curve`。
- `_build_resolved_payload_v81(bundle, sport_type)` 已对 resolver 距离轴变化场景做 power/cadence 重采样。
- 本次补齐 `_build_resolved_payload_v81()` 返回 `power_curve`，让后续 `curves_snapshot` 能消费同轴结果。
- `_build_fatigue_review_curves_snapshot(bundle, resolved)` 输出 `curves.power / curves.cadence`，长度必须与 `curves.distance` 同轴。
- `_summarize_fatigue_review_curves_for_ai(curves)` 只输出 `has_power / has_cadence / power_points_count / cadence_points_count`，不输出全量曲线。

## 3. 实现内容

### curves.power

- 在 `_build_resolved_payload_v81()` 返回值中加入 `power_curve`。
- `_build_fatigue_review_curves_snapshot()` 优先读取 `resolved.power_curve`，兜底读取 `bundle.power_curve`。
- 输出前仍走 `_fatigue_review_numeric_curve(...)`，长度不匹配时返回空数组。

### curves.cadence

- 继续复用现有 `resolved.cadence_curve / bundle.cadence_curve`。
- 输出前走 `_fatigue_review_numeric_curve(...)`，长度不匹配时返回空数组。

### summary

- 升级 `_fatigue_review_data_quality(...)`，支持：
  - `missing`
  - `insufficient_points`
  - `invalid_values`
  - `length_mismatch`
  - `available`
- 功率有效值范围：`0 < power <= 2500`。
- 踏频有效值范围：`0 < cadence <= 250`。
- 默认有效样本阈值：20 点。
- `_build_fatigue_review_summary(...)` 现在按 `curves.distance` 长度判断 power/cadence 是否同轴。

### AI compact snapshot

- 已保留 P0 的 `summary` 输出。
- 已保留 `curves_summary.has_power / has_cadence / power_points_count / cadence_points_count`。
- 新增测试确认 compact summary 不包含全量 `power` / `cadence` 曲线。

## 4. 明确不做

- 未实现 `power_variability` 真实算法。
- 未实现 `pedaling_stability` 真实算法。
- 未把骑行 `efficiency` 改为 `power/hr`。
- 未把骑行 `durability` 改为功率耐久。
- 未修改 `track.html` 主图区 ECharts。
- 未修改 `llm_backend.py`。
- 未修改 DB schema。

## 5. 验证

运行命令：

```bash
python3 -m pytest tests/test_cycling_fatigue_review_snapshot.py
python3 -m pytest tests/test_fatigue_review_contract_realignment.py tests/test_fatigue_review_e2e_contract.py tests/test_fatigue_review_ai_insight_p6.py tests/test_fatigue_review_prompts.py
```

结果：

- `tests/test_cycling_fatigue_review_snapshot.py`：7 passed。
- 复盘契约与 AI 相关测试：90 passed。
- 测试过程中仅出现 urllib3 / LibreSSL 环境警告，与本次变更无关。

## 6. 剩余风险

- 0W 滑行与缺失 0W 尚未区分，P1 只把 `power <= 0` 视为无效样本。
- 踏频单位在现有字段中未完全显式标注，当前契约按 rpm 或设备原始踏频单位处理。
- `cadence_curve` 目前主要来自 DB JSON，若未来 track records 也稳定包含 cadence，可考虑统一来源优先级。
- `indoor_cycling / gravel_cycling / e_biking` 尚未进入完整专项验收。

## 7. 下一步

- P2：AI 骑行提示词专项化，明确有功率/无功率时的解释边界。
- P3：骑行专项指标实现，包括 `power_variability / pedaling_stability / power-based efficiency / power durability`。
- P4：前端主图骑行模式，默认显示 `power + hr + altitude` 并加入踏频图层。
