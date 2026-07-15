# RCV2-01 多运动 Activity 事实源与真实数据审计

审计时间：2026-07-14

数据库：`/Users/fanglei/.fitvault/user_profile.db`

审计方式：SQLite `mode=ro` 只读连接。审计前后数据库修改时间均为 `1784001529`，确认未写入真实库。

## 1. 结论摘要

- 当前 `activities` 表已经具备 V2 所需的大部分 Activity canonical 输入：距离、时间、爬升、海拔、轨迹、Lap、功率汇总、功率点、泳姿字段、SWOLF/划水距离。
- 当前时间字段来自 FIT session `total_timer_time`，仅在缺失时 fallback 到 `total_elapsed_time`。因此字段名称上不能直接证明是完整 elapsed time；正式纪录任务必须继续保留 `timer_semantics_unknown` 或等价质量原因，直到按运动完成语义校验。
- 普通骑行真实样本为 94 条，另有 2 条 `e_biking`，必须从普通骑行功率纪录中排除。普通骑行中 67 条有正的汇总功率/NP 和逐点功率流，27 条无可用功率流。
- 徒步 7 条、步行 38 条、登山 5 条均有距离、时间、轨迹、海拔和 Lap；但徒步、步行、登山必须保持独立 Scope。
- 游泳真实样本为 2 条，均为公开水域；没有真实泳池样本。泳池功能必须依赖 fixture，Catalog 不得标记真实数据 Verified。
- 越野跑真实样本为 0；越野 Route/Segment 只能 fixture 开发和 candidate-only，不得真实开放。
- `user_profile_snapshots` 有同步日期级体重快照，但没有活动日期级、来源质量明确的历史体重表。W/kg 不能用当前 `user_profile.weight` 回填历史活动，需后续定义严格关联门禁。

## 2. FIT/GPX/provider 到 Activity 的事实链路

| 事实 | 当前来源链 | Activity 字段 | V2 可用性 |
| --- | --- | --- | --- |
| 运动类型 | FIT session/sport `sport`、`sub_sport` -> `FITCoreEngine._resolve_activity_type` -> sync | `sport_type`、`sub_sport_type` | 可用，但标题/文件名只能辅助，不能单独提升置信度 |
| 距离 | FIT session `total_distance` -> km/m 双字段；GPX fallback 可由轨迹汇总 | `dist_km`、`distance` | `dist_km` 为当前主要 km 字段；`distance` 当前按米写入 |
| 时间 | FIT session `total_timer_time`，缺失时 fallback `total_elapsed_time` | `duration_sec`、`duration` | 可作 timer 输入；正式 elapsed 语义需质量标记 |
| 爬升/下降 | FIT session/lap `total_ascent/total_descent`，GPX 可 fallback | `gain_m`、`total_descent_m` | 可用于整次纪录；质量/来源需后续评分 |
| 最高/最低海拔 | FIT session `max_altitude/enhanced_max_altitude` + 轨迹 | `max_alt_m`、`min_alt_m` | 可用于整次纪录；GPS 尖峰需质量检测 |
| 轨迹 | FIT record messages 或 GPX points | `track_json`、`points_json` | 可用；API/ViewModel 不得返回 raw points |
| 功率汇总 | FIT session/lap `avg_power/max_power/normalized_power` | `avg_power`、`max_power`、`normalized_power` | 可作上下文；不能替代持续时间功率曲线 |
| 功率流 | FIT record `power` -> track points | `track_json/points_json` 内 `power` | 可用于 67 条骑行 PDC；需断点/尖峰/采样质量检测 |
| Lap | FIT lap messages -> normalized laps | `laps_json` | 可用；泳池仍缺真实样本和 pool length |
| 泳姿 | FIT lap `swim_stroke` | `laps_json[].swim_stroke` | 字段存在；真实库只有公开水域，泳池泳姿需 fixture 验证 |
| pool length | `MetricsResolver` 当前在 lap_swimming 中 fallback 25m | 未见独立 Activity 字段 | V2 正式纪录不可使用默认 25m，需新增/冻结 canonical 字段 |
| 体重 | 用户画像快照同步 | `user_profile.weight`、`user_profile_snapshots.normalized_json.weight` | 当前只适合候选级关联，不足以直接生成正式历史 W/kg |

## 3. 当前真实数据覆盖

按未删除 Activity 统计：

| 运动/范围 | 数量 | 距离/时间 | 轨迹 | Lap | 功率流 | 海拔轨迹 | V2 含义 |
| --- | ---: | --- | ---: | ---: | ---: | ---: | --- |
| 普通骑行 | 94 | 94/94 | 94 | 94 | 67 | 94 | 可开发 PDC；27 条无功率流仅可参与整次纪录 |
| 电助力骑行 | 2 | 2/2 | 2 | 2 | 0 | 2 | 排除普通骑行功率纪录 |
| 徒步 | 7 | 7/7 | 7 | 7 | 0 | 7 | 可验证整次活动纪录与海拔质量 |
| 登山 | 5 | 5/5 | 5 | 5 | 0 | 5 | 独立 Scope，不与徒步混排 |
| 步行 | 38 | 38/38 | 38 | 38 | 0 | 38 | 独立 Scope，不进入徒步纪录 |
| 游泳 | 2 | 2/2 | 2 | 2 | 0 | 2 | 均为公开水域，无泳池真实样本 |
| 越野跑 | 0 | 0 | 0 | 0 | 0 | 0 | 只能 fixture/candidate-only |

骑行明细：

- `cycling/generic`：91 条，其中 65 条有正的 `avg_power/normalized_power`。
- `road_cycling/road`：2 条，其中 1 条有正的 `avg_power/normalized_power`。
- `cycling/252`：1 条，有正的 `avg_power/normalized_power`，后续 Sport Resolver 需确认 sub_sport `252` 的语义。
- `e_biking/e_bike_fitness`：2 条，排除普通骑行纪录。

游泳明细：

- 活动 `122`、`123` 均为 `swimming/open_water`。
- 两条均有 `dist_km`、`duration_sec`、轨迹和 2 条 normalized lap。
- `laps_json` 中存在 `swim_stroke` 字段，但当前公开水域样本不能验证泳池 Length 组合、pool length、组间休息和泳姿 Scope。

## 4. 时间语义与兼容性

代码链路显示：

```text
FIT session total_timer_time
  -> basic_info.total_timer_time
  -> duration_sec / duration

fallback: total_elapsed_time only when total_timer_time missing
```

含义：

- 当前 `duration_sec` 不是从字段名即可判定的 elapsed time。
- 对跑步 V1 已有 `duration_semantics_unknown` 的候选机制；V2 多运动也应沿用或扩展该原因码。
- 徒步、越野路线/赛段和公开水域标准距离若要求 elapsed time，必须在后续质量评分任务冻结 timer/elapsed 口径。
- 删除/重建/候选确认均不得让前端选择 moving/timer/elapsed。

## 5. 历史体重审计

当前表：

- `user_profile`：1 行当前画像，含 `weight=73.4`。
- `user_profile_snapshots`：32 条同步快照，含 `sync_date/synced_at/normalized_json.weight`，示例体重 `73.2`。

结论：

- 有日期级画像快照，可作为后续 W/kg 关联候选输入。
- 还没有专门的、活动日期级的历史体重事实表和来源质量字段。
- W/kg 正式纪录不得用当前体重回填历史。
- `RCV2-18` 需要冻结活动日期附近窗口、来源优先级、质量等级和隐私 ViewModel；没有可靠匹配时不生成 W/kg 事实或候选。

## 6. 附录 B 相关问题回答

| 问题 | RCV2-01 回答 |
| --- | --- |
| 1. Activity 时间字段能否提供可靠 elapsed time？ | 当前字段主要是 `total_timer_time`，不能直接视为可靠 elapsed；需要质量标记，正式 elapsed 口径后续冻结。 |
| 2. 功率流采样间隔、断点和尖峰分布如何？ | 67 条普通骑行有功率流；本任务确认覆盖，采样间隔/断点/尖峰分布留给 `RCV2-15` 做算法级统计。 |
| 3. 历史体重是否具备活动日期级可追溯来源？ | 只有画像快照日期，不足以直接正式生成历史 W/kg；需后续 W/kg 门禁。 |
| 4. pool length 是否需要新增 canonical Activity 字段？ | 是。当前正式路径不得使用 `MetricsResolver` 的 25m fallback。 |
| 5. Length/Lap 休息和泳姿如何表达？ | `laps_json` 有 lap 时长、距离、`swim_stroke` 字段；无真实泳池样本，需 fixture 验证休息中断和泳姿 Scope。 |
| 6. 公开水域 `±5%` 是否适合真实样本？ | 当前只有 0.615km 和 0.786km 两条公开水域样本；可验证 750m 边界附近，但不足以冻结所有距离阈值。 |
| 7. 海拔来源能否区分气压计/校正/GPS？ | 当前 Activity 字段有海拔/爬升和轨迹高度，但未见可靠来源类型字段；需 `RCV2-04/21` 质量评分降级。 |
| 10. 无真实越野/泳池样本时哪些功能 candidate-only？ | 泳池正式纪录不可真实验收；越野 Route/Segment 不可真实开放，均需 fixture/candidate-only/validation required。 |

待后续任务回答：

- 连续爬升段定义：`RCV2-21`。
- 路线签名/方向/重合度版本化：`RCV2-28`。
- V2 通用 Records API 兼容包装：`RCV2-06/14`。
- Catalog 防硬编码暴露：`RCV2-06/09/32`。

## 7. 对后续任务的输入

- `RCV2-02` fixtures 必须覆盖：无真实泳池、无真实越野、骑行功率 0W/缺失/非 1Hz/断点/尖峰、海拔尖峰、路线反向/低重合。
- `RCV2-03` Registry 可把骑行功率锚点设为可实现，但 Catalog 是否 available 应等待算法和真实 dry-run；泳池和越野应默认 validation required。
- `RCV2-04` reason codes 至少需要覆盖：`timer_semantics_unknown`、`missing_power_stream`、`power_stream_gap`、`pool_length_missing`、`swim_stroke_unknown`、`elevation_source_unknown`、`trail_sport_ambiguous`、`real_data_sample_missing`。
- `RCV2-05` schema 需要考虑：pool length、stroke scope、duration/distance/range、route/segment scope、curve cache、quality source fields。
