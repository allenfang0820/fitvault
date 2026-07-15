# RCV2-04 质量评分、置信度与原因码契约

完成时间：2026-07-14

本文冻结 Records Center V2 的质量评分、置信度阈值、reason codes、用户文案映射、日志安全等级和候选决策优先级。后续 Resolver、重建、增量评估、API 和前端必须共享同一套决策输出；不得在不同路径中各自解释 evidence。

## 1. 核心原则

- 质量评分只由后端 Resolver 或其下游状态迁移服务生成。
- 前端只展示后端 ViewModel 中的 `decision`、`confidence_band`、`reason_codes` 和安全文案，不解析技术 evidence。
- 用户确认只确认“这条候选证据可用于比较”，不能修改成绩值、距离、时间、功率、海拔、范围、Activity、record key 或 scope。
- Registry 的 `candidate_only`、`validation_required`、`analysis_only`、`model_only` 优先于单条 evidence 的高置信分。
- 同一 evidence 在增量、重建和维护 API 中必须得到相同 `decision`、`confidence`、`reason_codes` 和幂等 key。
- reason code 是稳定英文枚举；用户文案和日志映射可以迭代，但不得改变 code 语义。
- 日志和 API 不得包含 raw FIT、完整轨迹、真实 GPS 点、文件路径、设备序列号、账号、token、SQLite schema 或体重历史。

## 2. QualityDecision 输出

后续代码化建议使用不可变对象：

```python
QualityDecision(
    decision: str,
    confidence: float,
    confidence_band: str,
    reason_codes: tuple[str, ...],
    user_message_key: str,
    log_safety: str,
    can_user_confirm: bool,
    blocks_active: bool,
    evidence_fingerprint: str,
)
```

字段说明：

| 字段 | 允许值/要求 |
| --- | --- |
| `decision` | `auto_confirm`、`candidate`、`ignored`、`analysis_only`、`model_only`、`no_op` |
| `confidence` | `0.0` 到 `1.0`，必须 clamp，不能为 NaN |
| `confidence_band` | `high`、`candidate`、`low`、`not_applicable` |
| `reason_codes` | 稳定英文枚举，至少一个；无降级时也应有正向 reason |
| `user_message_key` | 安全文案 key，前端按 key 展示 |
| `log_safety` | `safe`、`aggregate_only`、`redacted` |
| `can_user_confirm` | 只有候选且事实未 hard-block 时为 true |
| `blocks_active` | true 表示不允许写 active |
| `evidence_fingerprint` | 不含敏感原始数据的幂等摘要 |

## 3. 阈值与优先级

### 3.1 置信度阈值

| confidence | confidence_band | 默认处理 |
| ---: | --- | --- |
| `> 0.90` | `high` | 可进入正式比较 |
| `0.70 <= confidence <= 0.90` | `candidate` | 生成候选，不替换 current |
| `< 0.70` | `low` | 忽略，不生成用户候选 |

边界冻结：

- `0.90` 属于 candidate。
- `0.70` 属于 candidate。
- `0.69` 属于 ignored。
- 只有 `>0.90` 且未被 Registry 状态或 hard-block 拦截，才允许 `auto_confirm`。

### 3.2 决策优先级

按以下顺序短路：

1. `analysis_only` 或 `model_only`：返回对应 decision，不进入候选/active 状态机。
2. hard-block reason 存在：`ignored`，`can_user_confirm=false`。
3. Registry `unavailable` 或 `validation_required`：`ignored` 或内部 `candidate`，不对用户开放 active；具体由任务实现阶段决定，但不得 auto-confirm。
4. Registry `candidate_only`：最高只能 `candidate`，即使 confidence `>0.90`。
5. confidence 阈值：按 3.1 得到 `auto_confirm`、`candidate` 或 `ignored`。

示例：

```text
trail_route_best_time confidence=0.97 + registry candidate_only
=> decision=candidate, can_user_confirm=true, blocks_active=true
```

```text
pool_swim_50m confidence=0.96 + pool_length_missing
=> decision=ignored, can_user_confirm=false, blocks_active=true
```

## 4. reason code 总表

### 4.1 通用正向 reason codes

| code | 用户文案 key | 日志安全 | 说明 |
| --- | --- | --- | --- |
| `activity_fact_ready` | `record_reason_activity_ready` | `safe` | Activity 事实可用于纪录评估。 |
| `activity_total_source` | `record_reason_activity_total` | `safe` | 使用整次活动事实。 |
| `best_effort_range_found` | `record_reason_best_effort_found` | `safe` | 找到活动内最佳努力范围。 |
| `range_attached` | `record_reason_range_attached` | `safe` | Evidence 已绑定活动内范围。 |
| `elapsed_time_reliable` | `record_reason_time_reliable` | `safe` | 时间事实可靠。 |
| `distance_reliable` | `record_reason_distance_reliable` | `safe` | 距离事实可靠。 |
| `scope_resolved` | `record_reason_scope_resolved` | `safe` | Scope 已由后端解析。 |
| `plausibility_passed` | `record_reason_plausibility_passed` | `safe` | 基础合理性检查通过。 |

### 4.2 通用降级与阻断 reason codes

| code | 默认严重度 | 用户是否可确认 | 用户文案 key | 日志安全 |
| --- | --- | --- | --- | --- |
| `activity_deleted` | hard_block | 否 | `record_reason_activity_deleted` | `safe` |
| `activity_processing_error` | hard_block | 否 | `record_reason_activity_processing_error` | `safe` |
| `activity_mock_or_test` | hard_block | 否 | `record_reason_activity_mock_or_test` | `safe` |
| `activity_id_missing` | hard_block | 否 | `record_reason_activity_missing` | `safe` |
| `record_definition_conflict` | hard_block | 否 | `record_reason_definition_conflict` | `safe` |
| `duplicate_evidence` | no_op | 否 | `record_reason_duplicate_evidence` | `safe` |
| `scope_missing` | hard_block | 否 | `record_reason_scope_missing` | `safe` |
| `metric_missing` | hard_block | 否 | `record_reason_metric_missing` | `safe` |
| `range_missing` | hard_block | 否 | `record_reason_range_missing` | `safe` |
| `duration_semantics_unknown` | degrade | 是 | `record_reason_time_needs_confirmation` | `safe` |
| `elapsed_time_missing` | hard_block | 否 | `record_reason_time_missing` | `safe` |
| `distance_missing` | hard_block | 否 | `record_reason_distance_missing` | `safe` |
| `plausibility_outlier` | degrade | 是 | `record_reason_plausibility_outlier` | `aggregate_only` |
| `validation_required_registry` | hard_block | 否 | `record_reason_validation_required` | `safe` |
| `candidate_only_registry` | candidate_cap | 是 | `record_reason_candidate_only` | `safe` |

### 4.3 骑行 reason codes

| code | 默认严重度 | 用户是否可确认 | 用户文案 key | 说明 |
| --- | --- | --- | --- | --- |
| `cycling_regular_scope` | positive | 不适用 | `record_reason_cycling_regular` | 普通骑行。 |
| `ebike_scope_excluded` | hard_block | 否 | `record_reason_ebike_excluded` | 电助力不进入普通骑行纪录。 |
| `power_stream_present` | positive | 不适用 | `record_reason_power_stream_present` | 有功率流。 |
| `power_stream_missing` | hard_block | 否 | `record_reason_power_stream_missing` | 功率锚点缺少功率流。 |
| `missing_power_stream_sample` | degrade | 是 | `record_reason_power_missing_sample` | 功率流存在缺失点。 |
| `power_stream_gap` | degrade | 是 | `record_reason_power_gap` | 存在不可跨越的功率断点。 |
| `power_spike_detected` | degrade | 是 | `record_reason_power_spike` | 检测到短时异常尖峰。 |
| `zero_watts_valid` | positive | 不适用 | `record_reason_zero_watts_valid` | 0W 按滑行有效值处理。 |
| `activity_shorter_than_window` | hard_block | 否 | `record_reason_activity_shorter_than_window` | 活动短于锚点窗口。 |
| `work_integration_quality_unknown` | degrade | 是 | `record_reason_work_quality_unknown` | 机械功积分质量待验证。 |
| `historical_weight_missing` | hard_block | 否 | `record_reason_historical_weight_missing` | W/kg 缺活动日期历史体重。 |

### 4.4 徒步与海拔 reason codes

| code | 默认严重度 | 用户是否可确认 | 用户文案 key | 说明 |
| --- | --- | --- | --- | --- |
| `sport_hiking_scope` | positive | 不适用 | `record_reason_hiking_scope` | 运动被解析为徒步。 |
| `walking_scope_excluded` | hard_block | 否 | `record_reason_walking_excluded` | 步行不混入徒步。 |
| `mountaineering_scope_excluded` | hard_block | 否 | `record_reason_mountaineering_excluded` | 登山不混入徒步。 |
| `elevation_stream_present` | positive | 不适用 | `record_reason_elevation_present` | 有海拔轨迹或可靠汇总。 |
| `elevation_missing` | hard_block | 否 | `record_reason_elevation_missing` | 对海拔类纪录缺事实源。 |
| `elevation_spike_detected` | degrade | 是 | `record_reason_elevation_spike` | 检测到海拔尖峰。 |
| `elevation_gain_unreliable` | degrade | 是 | `record_reason_elevation_unreliable` | 累计爬升质量不足。 |
| `single_climb_range_missing` | hard_block | 否 | `record_reason_single_climb_range_missing` | 连续爬升缺范围。 |
| `single_climb_requires_review` | candidate_cap | 是 | `record_reason_single_climb_review` | 连续爬升需候选复核。 |

### 4.5 游泳 reason codes

| code | 默认严重度 | 用户是否可确认 | 用户文案 key | 说明 |
| --- | --- | --- | --- | --- |
| `pool_swim_scope` | positive | 不适用 | `record_reason_pool_swim_scope` | 泳池游泳。 |
| `open_water_scope` | positive | 不适用 | `record_reason_open_water_scope` | 公开水域游泳。 |
| `pool_length_present` | positive | 不适用 | `record_reason_pool_length_present` | pool length 已确认。 |
| `pool_length_missing` | hard_block | 否 | `record_reason_pool_length_missing` | 不得默认 25m。 |
| `pool_length_fallback_detected` | hard_block | 否 | `record_reason_pool_length_fallback` | 检测到旧 fallback，不能写正式纪录。 |
| `swim_stroke_resolved` | positive | 不适用 | `record_reason_stroke_resolved` | 泳姿可解析。 |
| `swim_stroke_unknown` | degrade | 是 | `record_reason_stroke_unknown` | 泳姿未知，只能候选或待验证。 |
| `pool_rest_break` | hard_block | 否 | `record_reason_pool_rest_break` | 休息中断该 best-effort 窗口。 |
| `open_water_gps_reliable` | positive | 不适用 | `record_reason_open_water_gps_reliable` | 公开水域 GPS 质量可接受。 |
| `open_water_gps_unreliable` | degrade | 是 | `record_reason_open_water_gps_unreliable` | GPS 跳点或漂移。 |
| `distance_outside_5_percent` | hard_block | 否 | `record_reason_distance_outside_5_percent` | 公开水域标准距离不匹配。 |
| `distance_within_5_percent` | positive | 不适用 | `record_reason_distance_within_5_percent` | 公开水域标准距离命中。 |

### 4.6 越野路线/赛段 reason codes

| code | 默认严重度 | 用户是否可确认 | 用户文案 key | 说明 |
| --- | --- | --- | --- | --- |
| `sport_trail_running_scope` | positive | 不适用 | `record_reason_trail_scope` | 越野跑。 |
| `road_running_scope_excluded` | hard_block | 否 | `record_reason_road_running_excluded` | 公路跑不混入越野。 |
| `route_signature_present` | positive | 不适用 | `record_reason_route_signature_present` | 路线签名可用。 |
| `route_signature_missing` | hard_block | 否 | `record_reason_route_signature_missing` | 缺路线签名。 |
| `route_match_passed` | positive | 不适用 | `record_reason_route_match_passed` | 同路线匹配通过。 |
| `route_direction_mismatch` | hard_block | 否 | `record_reason_route_direction_mismatch` | 反向路线拒绝。 |
| `route_match_low_overlap` | hard_block | 否 | `record_reason_route_low_overlap` | 重合度不足。 |
| `real_data_sample_missing` | candidate_cap | 是 | `record_reason_real_sample_missing` | 缺真实样本，保持候选。 |
| `segment_key_missing` | hard_block | 否 | `record_reason_segment_key_missing` | 赛段 key 缺失。 |
| `segment_range_missing` | hard_block | 否 | `record_reason_segment_range_missing` | 赛段活动内范围缺失。 |
| `climb_segment_grade_unverified` | degrade | 是 | `record_reason_climb_segment_unverified` | 爬坡赛段坡度/范围待验证。 |

### 4.7 跑步 V1 reason codes

| code | 默认严重度 | 用户是否可确认 | 用户文案 key | 说明 |
| --- | --- | --- | --- | --- |
| `sport_running` | positive | 不适用 | `record_reason_running_scope` | 跑步 V1 继承。 |
| `distance_within_3_percent` | positive | 不适用 | `record_reason_distance_within_3_percent` | 标准距离命中。 |
| `distance_outside_3_percent` | hard_block | 否 | `record_reason_distance_outside_3_percent` | 标准距离不匹配。 |
| `sport_trail_running_excluded_v1` | hard_block | 否 | `record_reason_trail_excluded_v1` | V1 跑步不含越野跑。 |
| `sport_treadmill_requires_confirmation` | degrade | 是 | `record_reason_treadmill_confirmation` | 跑步机需要确认。 |

## 5. 运动质量评分矩阵

分数计算可在实现时调整权重，但输出等级和 reason code 必须保持稳定。

### 5.1 通用基础项

| 维度 | 通过条件 | 失败/降级 |
| --- | --- | --- |
| activity integrity | Activity 存在、非 mock/test、解析完成 | hard-block：`activity_deleted`、`activity_processing_error`、`activity_mock_or_test` |
| metric presence | 目标 metric 和单位存在 | hard-block：`metric_missing` |
| scope | 后端可解析全部必需 scope | hard-block：`scope_missing` |
| range | 需要活动内范围的纪录已绑定范围 | hard-block：`range_missing` |
| plausibility | 速度、功率、海拔、距离在合理范围 | degrade：`plausibility_outlier`；严重异常可 hard-block |

### 5.2 骑行功率

| 质量项 | high | candidate/degrade | ignored |
| --- | --- | --- | --- |
| sport_scope | 普通骑行 | unknown cycling subtype | e-bike：`ebike_scope_excluded` |
| power stream | 有足够覆盖，0W 保留 | 少量缺失或短 gap：candidate | 无功率流：`power_stream_missing` |
| spike | 无明显尖峰 | 短尖峰被剔除：`power_spike_detected` | 尖峰导致窗口无法可信 |
| duration window | 窗口完整且不跨 gap | 质量低但有范围 | 活动短于窗口 |
| work_kj | 积分覆盖完整 | 质量未知则 candidate/validation_required | 无功率流 |

### 5.3 徒步与海拔

| 质量项 | high | candidate/degrade | ignored |
| --- | --- | --- | --- |
| sport_scope | `hiking` | unknown outdoor walk-like | walking/mountaineering/trail_running |
| distance/time | canonical facts 可靠 | duration semantics unknown | 缺失 |
| ascent/max altitude | 海拔流或汇总可信 | 海拔尖峰可修正：candidate | 海拔事实缺失 |
| single climb | 有去噪轨迹和范围 | 需要人工复核：candidate | 范围缺失或用累计爬升冒充 |

### 5.4 泳池游泳

| 质量项 | high | candidate/degrade | ignored |
| --- | --- | --- | --- |
| water_scope | pool_swimming | unknown water scope | 非泳池 |
| pool length | 明确 pool length/scope | 无 | 缺失或 fallback |
| stroke | 泳姿解析 | unknown stroke candidate | 无可解析且 record 需要 stroke scope |
| length/lap range | 连续且无休息 | 泳姿混合 candidate | 休息中断目标窗口 |
| real data | 真实样本验收后可用 | 当前 V2 默认 validation_required | 无真实样本不得 active |

### 5.5 公开水域游泳

| 质量项 | high | candidate/degrade | ignored |
| --- | --- | --- | --- |
| water_scope | open_water_swimming | unknown swim subtype | 非公开水域 |
| standard distance | `±5%` 内，边界包含 | 距离接近边界且 GPS 轻微异常 | 超出 `±5%` |
| GPS quality | 轨迹连续、无跳点 | GPS 跳点/漂移 candidate | 严重跳点导致距离不可信 |
| sample sufficiency | 用户 dry-run 后放行 | 当前默认 candidate_only | 无真实验收不得 active |

### 5.6 越野路线/赛段

| 质量项 | high | candidate/degrade | ignored |
| --- | --- | --- | --- |
| sport_scope | trail_running | unknown off-road run | road running/hiking/mountaineering |
| route signature | 有稳定 route_key | 低样本 candidate | 缺 route signature |
| route match | 同向、长度误差和重合度通过 | 真实样本缺失 candidate | 反向或低重合 |
| segment | segment_key 和范围完整 | 爬坡赛段坡度待验证 | 缺 key 或范围 |
| sample sufficiency | 真实样本验收后可放行 | 当前默认 candidate_only | 无真实验收不得 active |

## 6. 用户确认边界

用户可确认：

- `duration_semantics_unknown`。
- `plausibility_outlier` 且未触发 hard-block。
- `missing_power_stream_sample`、`power_stream_gap`、`power_spike_detected` 造成的低置信候选。
- `elevation_spike_detected`、`elevation_gain_unreliable`、`single_climb_requires_review`。
- `swim_stroke_unknown`，但只有 pool length 已确认且 Registry 状态允许时才可能进入比较。
- `open_water_gps_unreliable`。
- `real_data_sample_missing`、`climb_segment_grade_unverified`。

用户不可确认：

- Activity 删除、解析失败、mock/test。
- record definition 冲突。
- 缺 Activity ID、缺 metric、缺必需 scope、缺必需范围。
- 距离超出标准容差。
- e-bike 混入普通骑行。
- 缺功率流却要生成功率锚点。
- 缺 pool length 或检测到旧 fallback。
- 路线反向、低重合或缺 route signature。
- 缺活动日期级历史体重却要生成 W/kg。

确认后仍必须重新比较：

- 用户确认不会直接改写 active。
- 候选确认后如果没有优于 current，则不得替换 current。
- `candidate_only_registry` 或 `validation_required_registry` 未被后续真实数据/用户发布决策解除前，即使用户确认也不得写 active。

## 7. 样本不足和 Catalog 状态规则

| Registry 状态 | Evidence 高分时的最高决策 | 用户可见 |
| --- | --- | --- |
| `available` | `auto_confirm` | 可展示正式纪录 |
| `candidate_only` | `candidate` | 展示待确认/待验收候选 |
| `validation_required` | `ignored` 或内部候选 | 展示灰态说明，不展示正式纪录 |
| `unavailable` | `ignored` | 不开放或灰态 |
| `analysis_only` | `analysis_only` | 仅分析区 |
| `model_only` | `model_only` | 仅模型估计区 |

样本不足冻结：

- 泳池：真实库无泳池样本，且 pool length schema 待补齐，默认 `validation_required`。
- 公开水域：只有 2 条真实样本，标准距离和整次活动纪录默认 `candidate_only`。
- 越野：真实样本为 0，整次活动、路线和赛段默认 `candidate_only`。
- 徒步最大连续爬升：即使有 hiking 样本，因需要范围和海拔去噪，默认 `candidate_only`。
- 骑行 W/kg：历史体重事实源缺失，不进入正式纪录。

## 8. 日志与文案安全

API/ViewModel 可以返回：

- reason code。
- 文案 key。
- 聚合质量标签。
- 经过裁剪的活动内范围索引或时间偏移。
- 不含原始数据的 evidence fingerprint。

禁止返回或记录：

- 本地文件路径、FIT 文件名中的路径信息。
- raw FIT 内容、完整轨迹点、真实经纬度数组。
- 设备序列号、账号、邮箱、token、API key。
- SQLite schema dump。
- 用户体重历史明细。

`aggregate_only` 日志只允许输出计数、等级和 code，不输出原始采样值。`redacted` 日志必须经过显式脱敏。

## 9. 边界测试表

| 编号 | 场景 | 预期 |
| --- | --- | --- |
| CONF-001 | confidence `0.91` + available + 无 hard-block | `auto_confirm` |
| CONF-002 | confidence `0.90` | `candidate` |
| CONF-003 | confidence `0.70` | `candidate` |
| CONF-004 | confidence `0.69` | `ignored` |
| CONF-005 | confidence NaN | validation fail 或 clamp 后 hard-block |
| CONF-006 | confidence `>0.90` + `candidate_only_registry` | `candidate` |
| CONF-007 | confidence `>0.90` + `validation_required_registry` | 不得 active |
| REASON-001 | 降级但无 reason code | validation fail |
| REASON-002 | fixture 中 reason code 不在白名单 | validation fail |
| REASON-003 | reason payload 含路径/token/real GPS | validation fail |
| CYCLING-001 | 0W 功率点 | 有效，不当作缺失 |
| CYCLING-002 | e-bike | `ignored`，`ebike_scope_excluded` |
| CYCLING-003 | 活动短于 60m anchor | `ignored`，`activity_shorter_than_window` |
| HIKING-001 | 海拔尖峰 | candidate，`elevation_spike_detected` |
| HIKING-002 | 最大连续爬升缺范围 | ignored |
| SWIM-001 | pool length 缺失 | ignored，用户不可确认 |
| SWIM-002 | open water 距离误差正好 5% | 匹配，但 GPS 质量仍可降级 |
| TRAIL-001 | route reverse direction | ignored |
| TRAIL-002 | same route but no real sample | candidate-only |
| USER-001 | 用户确认 candidate | 不改事实值，重新参与比较 |
| USER-002 | 用户确认 hard-block | 拒绝操作，不改状态 |

## 10. 后续实现测试计划

`RCV2-12` 状态迁移和后续 Resolver 任务至少需要覆盖：

- 阈值边界：`0.69`、`0.70`、`0.90`、`0.91`。
- reason code 白名单和用户文案 key 完整性。
- Registry candidate-only/validation-required 优先级。
- 每个 hard-block reason 不允许用户确认。
- 同一 evidence 在增量与重建中 decision 幂等。
- fixture reason codes 全部落在白名单中。
- 敏感字段扫描：路径、token、real GPS、设备序列号、体重历史不得进入 reason payload。
- V1 跑步候选/active/rejected/invalidated 状态机不回归。
