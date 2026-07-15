# RCV2-03 Registry、纪录族与 Scope 契约

完成时间：2026-07-14

本文冻结 Records Center V2 的 `RecordDefinition`、纪录族、`source_mode`、Scope 维度、静态 record keys、动态 route/segment scope 规则和 Catalog 可用性策略。后续 `RCV2-09` 代码化必须以本文为输入，不得在 Resolver、API 或前端重新发明单位、比较方向、运动边界或 Scope。

## 1. 契约原则

- Activity 是唯一事实源；Record Registry 只描述“什么可以成为纪录”，不直接读取数据库。
- Resolver/状态迁移服务是正式纪录唯一写入口。
- 前端只消费 Catalog/ViewModel，不拼 Scope、不计算纪录、不判断置信度、不决定比较方向。
- 跑步 V1 四项必须完全继承，不因 V2 改变 record key、距离容差、比较方向、单位或旧 API 兼容。
- 模型估计和分析曲线不注册为正式 active record，包括 eFTP、CP、W′、MAP、PMax、GAP、NGP、SWOLF 趋势。
- 未通过真实数据验收的运动或纪录不得在 Catalog 中标记为 `available`。
- 动态 route/segment 纪录使用稳定的 `record_key + scope_key` 表达实例，不把路线 ID、赛段 ID 拼进新的 record type。

## 2. V2 RecordDefinition 字段

代码化时建议继续使用不可变结构。V2 字段如下：

| 字段 | 类型 | 必填 | 冻结说明 |
| --- | --- | --- | --- |
| `key` | `str` | 是 | 静态纪录类型 key；发布后不可改变语义。动态路线/赛段仍使用静态 key。 |
| `sport` | `str` | 是 | 运动域，来自 sport 白名单。 |
| `family` | `str` | 是 | 纪录族，来自 family 白名单。替代 V1 `category` 的产品语义。 |
| `display_name` | `str` | 是 | 默认中文展示名；前端可展示但不能从文案反推规则。 |
| `metric` | `str` | 是 | 比较主值字段，来自 metric 白名单。 |
| `canonical_unit` | `str` | 是 | canonical 存储和比较单位，来自 unit 白名单。 |
| `comparison` | `str` | 是 | `lower_is_better` 或 `higher_is_better`。 |
| `source_mode` | `str` | 是 | evidence 来源模式，来自 source_mode 白名单。 |
| `scope_dimensions` | `tuple[str, ...]` | 是 | 该纪录实例必须携带的 Scope 维度；可为空 tuple。 |
| `minimum_data_requirements` | `tuple[str, ...]` | 是 | 生成 evidence 所需 Activity canonical facts。 |
| `quality_policy` | `str` | 是 | 质量策略 key，具体评分由 `RCV2-04` 冻结。 |
| `enabled_release` | `str` | 是 | 首次允许进入 Catalog 的发布标识。 |
| `rule_version` | `str` | 是 | 规则版本；V2 新定义统一从 `records-v2` 起。 |
| `priority` | `int` | 是 | Catalog 默认排序；同运动内越小越靠前。 |
| `availability_state` | `str` | 是 | Registry 级可用性默认状态，来自 availability 白名单。 |
| `availability_reason` | `str` | 否 | 不可用、候选或待验证的原因码。 |
| `standard_distance_m` | `float \| None` | 否 | 标准距离类纪录使用；非标准距离为 `None`。 |
| `standard_duration_sec` | `int \| None` | 否 | 功率持续时间锚点使用；非持续时间锚点为 `None`。 |
| `tolerance_ratio` | `float \| None` | 否 | 标准距离 activity-total 匹配使用；泳池 best effort 不使用容差。 |
| `dynamic_scope` | `bool` | 是 | route/segment 等动态实例为 `true`；普通静态纪录为 `false`。 |
| `legacy_category` | `str \| None` | 否 | 仅兼容 V1 或旧 API 时使用，不作为 V2 新逻辑判断依据。 |

字段兼容要求：

- V1 代码中的 `category` 可在过渡期映射为 `family` 或 `legacy_category`，但新代码不得把 `category` 当成 V2 规则源。
- `availability_state` 是 Catalog 默认状态，不等于单个 evidence 的状态。单个 evidence 仍由 Resolver 质量评分和候选状态机决定。
- `scope_dimensions` 由后端输出；前端只能展示后端已解析的 scope labels。

## 3. 白名单

### 3.1 sport

| 值 | 说明 |
| --- | --- |
| `running` | 跑步 V1 继承；不包含越野跑。 |
| `cycling` | 普通骑行；排除 e-bike。 |
| `hiking` | 徒步；不混入 walking、mountaineering、trail_running。 |
| `pool_swimming` | 泳池游泳。 |
| `open_water_swimming` | 公开水域游泳。 |
| `trail_running` | 越野跑。 |

### 3.2 family

| 值 | 是否可注册为正式纪录 | 说明 |
| --- | --- | --- |
| `distance_time_pb` | 是 | 标准距离成绩，越低越好。 |
| `power_duration_pb` | 是 | 固定持续时间最佳功率，越高越好。 |
| `activity_total_record` | 是 | 整次活动总量或极值纪录。 |
| `route_pr` | 是，动态实例 | 同路线同方向 PR。真实样本缺失时 candidate-only。 |
| `segment_pr` | 是，动态实例 | 活动内赛段 PR。真实样本缺失时 candidate-only。 |
| `analysis_curve` | 否 | 只用于分析展示，不写正式纪录。 |
| `model_estimate` | 否 | 只用于模型估计或训练分析，不写正式纪录。 |

### 3.3 source_mode

| 值 | 说明 |
| --- | --- |
| `activity_total` | 整次 Activity 汇总 facts。 |
| `best_effort_duration` | Activity 内固定持续时间窗口，如骑行 20m 功率。 |
| `best_effort_distance` | Activity 内固定距离窗口，如泳池 100m。 |
| `route_total` | 由 Route Signature 匹配得到的整条路线实例。 |
| `segment` | Activity 内稳定赛段范围。 |

### 3.4 scope_dimensions

| 值 | 说明 | 生成方 |
| --- | --- | --- |
| `sport_scope` | 运动边界，如普通骑行排除 e-bike。 | 后端 |
| `indoor_scope` | `indoor` / `outdoor` / `unknown`。 | 后端 |
| `distance_scope` | 标准距离窗口口径，如 cycling 10K/40K/100K。 | 后端 |
| `power_metric_scope` | 功率口径，如 `raw_power_w`、未来可扩展 normalized/weighted。 | 后端 |
| `pool_length_scope` | 泳池长度，如 `scm_25m`、`scm_50m`、`scy_25y`。 | 后端 |
| `stroke_scope` | 泳姿，如 freestyle、backstroke、breaststroke、butterfly、mixed、unknown。 | 后端 |
| `water_scope` | `pool_swimming` 或 `open_water_swimming`。 | 后端 |
| `route_key` | 路线签名实例 key。 | 后端 |
| `segment_key` | 赛段实例 key。 | 后端 |

### 3.5 units、comparison、availability

| 类别 | 允许值 |
| --- | --- |
| `canonical_unit` | `seconds`、`meters`、`meters_per_second`、`watts`、`kilojoules`、`meters_ascent`、`meters_altitude` |
| `comparison` | `lower_is_better`、`higher_is_better` |
| `availability_state` | `available`、`candidate_only`、`validation_required`、`unavailable`、`analysis_only`、`model_only` |

状态解释：

- `available`：Catalog 可展示为可用正式纪录；单个 evidence 仍可因低质量进入候选或被忽略。
- `candidate_only`：可计算、可展示候选，但不自动确认，不写 active。
- `validation_required`：规则已冻结，但真实数据或 schema 尚不足，不对用户开放正式纪录。
- `unavailable`：V2 不开放，通常因事实源缺失或样本不存在。
- `analysis_only`：只用于曲线、趋势或辅助图表。
- `model_only`：只用于模型估计。

## 4. 静态 Record Definitions

### 4.1 跑步，V1 继承

| key | display_name | family | metric | unit | comparison | source_mode | standard_distance_m | tolerance_ratio | scope_dimensions | availability |
| --- | --- | --- | --- | --- | --- | --- | ---: | ---: | --- | --- |
| `running_5k` | 5K | `distance_time_pb` | `elapsed_time_sec` | `seconds` | `lower_is_better` | `activity_total` | 5000 | 0.03 | `()` | `available` |
| `running_10k` | 10K | `distance_time_pb` | `elapsed_time_sec` | `seconds` | `lower_is_better` | `activity_total` | 10000 | 0.03 | `()` | `available` |
| `running_half_marathon` | 半程马拉松 | `distance_time_pb` | `elapsed_time_sec` | `seconds` | `lower_is_better` | `activity_total` | 21097.5 | 0.03 | `()` | `available` |
| `running_marathon` | 马拉松 | `distance_time_pb` | `elapsed_time_sec` | `seconds` | `lower_is_better` | `activity_total` | 42195 | 0.03 | `()` | `available` |

继承约束：

- 匹配公式仍为 `abs(actual_distance_m - standard_distance_m) / standard_distance_m <= 0.03`，边界包含。
- `source_mode` 仍为 `activity_total`，V2 不从长距离跑步中截取最快 5K/10K。
- 比较主值仍为整数秒 `elapsed_time_sec`，相同秒数不刷新。

### 4.2 骑行功率持续时间锚点

| key | display_name | family | metric | unit | comparison | source_mode | standard_duration_sec | scope_dimensions | availability | reason |
| --- | --- | --- | --- | --- | --- | --- | ---: | --- | --- | --- |
| `cycling_power_5s` | 5 秒最大功率 | `power_duration_pb` | `power_w` | `watts` | `higher_is_better` | `best_effort_duration` | 5 | `sport_scope, indoor_scope, power_metric_scope` | `available` | 真实库有普通骑行功率流覆盖 |
| `cycling_power_30s` | 30 秒最大功率 | `power_duration_pb` | `power_w` | `watts` | `higher_is_better` | `best_effort_duration` | 30 | `sport_scope, indoor_scope, power_metric_scope` | `available` | 同上 |
| `cycling_power_1m` | 1 分钟最大功率 | `power_duration_pb` | `power_w` | `watts` | `higher_is_better` | `best_effort_duration` | 60 | `sport_scope, indoor_scope, power_metric_scope` | `available` | 同上 |
| `cycling_power_5m` | 5 分钟最大功率 | `power_duration_pb` | `power_w` | `watts` | `higher_is_better` | `best_effort_duration` | 300 | `sport_scope, indoor_scope, power_metric_scope` | `available` | 同上 |
| `cycling_power_10m` | 10 分钟最大功率 | `power_duration_pb` | `power_w` | `watts` | `higher_is_better` | `best_effort_duration` | 600 | `sport_scope, indoor_scope, power_metric_scope` | `available` | 同上 |
| `cycling_power_20m` | 20 分钟最大功率 | `power_duration_pb` | `power_w` | `watts` | `higher_is_better` | `best_effort_duration` | 1200 | `sport_scope, indoor_scope, power_metric_scope` | `available` | 同上 |
| `cycling_power_30m` | 30 分钟最大功率 | `power_duration_pb` | `power_w` | `watts` | `higher_is_better` | `best_effort_duration` | 1800 | `sport_scope, indoor_scope, power_metric_scope` | `available` | 同上 |
| `cycling_power_60m` | 60 分钟最大功率 | `power_duration_pb` | `power_w` | `watts` | `higher_is_better` | `best_effort_duration` | 3600 | `sport_scope, indoor_scope, power_metric_scope` | `available` | 同上 |
| `cycling_power_2h` | 2 小时最大功率 | `power_duration_pb` | `power_w` | `watts` | `higher_is_better` | `best_effort_duration` | 7200 | `sport_scope, indoor_scope, power_metric_scope` | `available` | 同上 |

骑行功率边界：

- 普通骑行 `sport_scope=cycling_regular`；e-bike 必须排除，原因码 `ebike_scope_excluded`。
- 0W 是有效滑行值；缺失功率不是 0W。
- 窗口不得跨长暂停、长断点或缺失流段。
- `power_metric_scope` V2 默认 `raw_power_w`；normalized power 可做分析，不作为正式功率锚点。
- W/kg 不在上述 key 中注册为 active；缺少活动日期级历史体重契约前，只能作为 `model_only` 或 `validation_required` 的派生视图。

### 4.3 骑行标准距离最快成绩

| key | display_name | family | metric | unit | comparison | source_mode | standard_distance_m | scope_dimensions | availability | reason |
| --- | --- | --- | --- | --- | --- | --- | ---: | --- | --- | --- |
| `cycling_fastest_10k` | 最快 10K | `distance_time_pb` | `elapsed_time_sec` | `seconds` | `lower_is_better` | `best_effort_distance` | 10000 | `sport_scope, indoor_scope, distance_scope` | `validation_required` | 需要距离-时间流契约 |
| `cycling_fastest_20k` | 最快 20K | `distance_time_pb` | `elapsed_time_sec` | `seconds` | `lower_is_better` | `best_effort_distance` | 20000 | `sport_scope, indoor_scope, distance_scope` | `validation_required` | 同上 |
| `cycling_fastest_40k` | 最快 40K | `distance_time_pb` | `elapsed_time_sec` | `seconds` | `lower_is_better` | `best_effort_distance` | 40000 | `sport_scope, indoor_scope, distance_scope` | `validation_required` | 同上 |
| `cycling_fastest_50k` | 最快 50K | `distance_time_pb` | `elapsed_time_sec` | `seconds` | `lower_is_better` | `best_effort_distance` | 50000 | `sport_scope, indoor_scope, distance_scope` | `validation_required` | 同上 |
| `cycling_fastest_100k` | 最快 100K | `distance_time_pb` | `elapsed_time_sec` | `seconds` | `lower_is_better` | `best_effort_distance` | 100000 | `sport_scope, indoor_scope, distance_scope` | `validation_required` | 同上 |
| `cycling_fastest_180k` | 最快 180K | `distance_time_pb` | `elapsed_time_sec` | `seconds` | `lower_is_better` | `best_effort_distance` | 180000 | `sport_scope, indoor_scope, distance_scope` | `validation_required` | 同上 |

骑行标准距离边界：

- 普通骑行 `sport_scope=cycling_regular`；e-bike 必须排除。
- 必须使用 Activity 内距离-时间流的固定距离窗口，不得用整次活动均速或整次活动 elapsed time 替代。
- 距离-时间流、暂停语义、室内外里程来源和异常 GPS/速度跳点规则冻结前，不生成 active record。

### 4.4 骑行整次活动纪录

| key | display_name | family | metric | unit | comparison | source_mode | scope_dimensions | availability | reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `cycling_longest_distance` | 最长骑行距离 | `activity_total_record` | `distance_m` | `meters` | `higher_is_better` | `activity_total` | `sport_scope, indoor_scope` | `available` | 普通骑行样本充足 |
| `cycling_max_ascent` | 单次最大爬升 | `activity_total_record` | `ascent_m` | `meters_ascent` | `higher_is_better` | `activity_total` | `sport_scope, indoor_scope` | `available` | 需质量评分过滤异常海拔 |
| `cycling_longest_elapsed_time` | 最长骑行历时 | `activity_total_record` | `elapsed_time_sec` | `seconds` | `higher_is_better` | `activity_total` | `sport_scope, indoor_scope` | `available` | 使用后端 canonical elapsed |
| `cycling_max_work` | 单次最大机械功 | `activity_total_record` | `work_kj` | `kilojoules` | `higher_is_better` | `activity_total` | `sport_scope, indoor_scope, power_metric_scope` | `validation_required` | 需要功率积分质量契约 |

V2 不开放 `cycling_fastest_average_speed`：均速高度依赖路线、风、红绿灯和暂停语义，先保留为分析指标或后续版本候选。

### 4.5 徒步整次活动纪录

| key | display_name | family | metric | unit | comparison | source_mode | scope_dimensions | availability | reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `hiking_longest_distance` | 最长徒步距离 | `activity_total_record` | `distance_m` | `meters` | `higher_is_better` | `activity_total` | `sport_scope` | `available` | 真实库有 hiking 样本 |
| `hiking_max_ascent` | 单次最大累计爬升 | `activity_total_record` | `ascent_m` | `meters_ascent` | `higher_is_better` | `activity_total` | `sport_scope` | `available` | 需海拔质量过滤 |
| `hiking_longest_elapsed_time` | 最长徒步历时 | `activity_total_record` | `elapsed_time_sec` | `seconds` | `higher_is_better` | `activity_total` | `sport_scope` | `available` | 使用后端 canonical elapsed |
| `hiking_max_altitude` | 最高海拔 | `activity_total_record` | `max_altitude_m` | `meters_altitude` | `higher_is_better` | `activity_total` | `sport_scope` | `available` | 需异常点过滤 |
| `hiking_max_single_climb` | 最大连续爬升 | `activity_total_record` | `single_climb_m` | `meters_ascent` | `higher_is_better` | `activity_total` | `sport_scope` | `candidate_only` | 必须带 Activity 内范围，真实样本需人工复核 |

徒步边界：

- 只接收 canonical `hiking`。
- `walking`、`mountaineering`、`trail_running` 不得混入徒步纪录。
- `hiking_max_single_climb` 不得用整次累计爬升冒充，Evidence 必须包含起止点范围。

### 4.5 泳池游泳标准距离

| key | display_name | family | metric | unit | comparison | source_mode | standard_distance_m | scope_dimensions | availability | reason |
| --- | --- | --- | --- | --- | --- | --- | ---: | --- | --- | --- |
| `pool_swim_50m` | 泳池 50m | `distance_time_pb` | `elapsed_time_sec` | `seconds` | `lower_is_better` | `best_effort_distance` | 50 | `water_scope, pool_length_scope, stroke_scope` | `validation_required` | 真实库无泳池样本，pool length schema 待补齐 |
| `pool_swim_100m` | 泳池 100m | `distance_time_pb` | `elapsed_time_sec` | `seconds` | `lower_is_better` | `best_effort_distance` | 100 | `water_scope, pool_length_scope, stroke_scope` | `validation_required` | 同上 |
| `pool_swim_200m` | 泳池 200m | `distance_time_pb` | `elapsed_time_sec` | `seconds` | `lower_is_better` | `best_effort_distance` | 200 | `water_scope, pool_length_scope, stroke_scope` | `validation_required` | 同上 |
| `pool_swim_400m` | 泳池 400m | `distance_time_pb` | `elapsed_time_sec` | `seconds` | `lower_is_better` | `best_effort_distance` | 400 | `water_scope, pool_length_scope, stroke_scope` | `validation_required` | 同上 |
| `pool_swim_800m` | 泳池 800m | `distance_time_pb` | `elapsed_time_sec` | `seconds` | `lower_is_better` | `best_effort_distance` | 800 | `water_scope, pool_length_scope, stroke_scope` | `validation_required` | 同上 |
| `pool_swim_1500m` | 泳池 1500m | `distance_time_pb` | `elapsed_time_sec` | `seconds` | `lower_is_better` | `best_effort_distance` | 1500 | `water_scope, pool_length_scope, stroke_scope` | `validation_required` | 同上 |

泳池边界：

- 不使用距离容差；距离来自连续 Length/Lap 数量乘以已确认 pool length。
- 缺少 `pool_length_scope` 不得默认 25m。
- `stroke_scope=unknown` 时不得自动确认。
- 休息或非游泳段会中断 best-effort 窗口。

### 4.6 公开水域游泳

| key | display_name | family | metric | unit | comparison | source_mode | standard_distance_m | tolerance_ratio | scope_dimensions | availability | reason |
| --- | --- | --- | --- | --- | --- | --- | ---: | ---: | --- | --- | --- |
| `open_water_swim_750m` | 公开水域 750m | `distance_time_pb` | `elapsed_time_sec` | `seconds` | `lower_is_better` | `activity_total` | 750 | 0.05 | `water_scope` | `candidate_only` | 真实样本少，GPS 质量需 dry-run |
| `open_water_swim_1500m` | 公开水域 1500m | `distance_time_pb` | `elapsed_time_sec` | `seconds` | `lower_is_better` | `activity_total` | 1500 | 0.05 | `water_scope` | `candidate_only` | 同上 |
| `open_water_swim_1900m` | 公开水域 1900m | `distance_time_pb` | `elapsed_time_sec` | `seconds` | `lower_is_better` | `activity_total` | 1900 | 0.05 | `water_scope` | `candidate_only` | 同上 |
| `open_water_swim_3800m` | 公开水域 3800m | `distance_time_pb` | `elapsed_time_sec` | `seconds` | `lower_is_better` | `activity_total` | 3800 | 0.05 | `water_scope` | `candidate_only` | 同上 |
| `open_water_swim_5k` | 公开水域 5K | `distance_time_pb` | `elapsed_time_sec` | `seconds` | `lower_is_better` | `activity_total` | 5000 | 0.05 | `water_scope` | `candidate_only` | 同上 |
| `open_water_swim_10k` | 公开水域 10K | `distance_time_pb` | `elapsed_time_sec` | `seconds` | `lower_is_better` | `activity_total` | 10000 | 0.05 | `water_scope` | `candidate_only` | 同上 |
| `open_water_longest_distance` | 公开水域最长距离 | `activity_total_record` | `distance_m` | `meters` | `higher_is_better` | `activity_total` |  |  | `water_scope` | `candidate_only` | 真实样本少，GPS 质量需 dry-run |
| `open_water_longest_elapsed_time` | 公开水域最长历时 | `activity_total_record` | `elapsed_time_sec` | `seconds` | `higher_is_better` | `activity_total` |  |  | `water_scope` | `candidate_only` | 同上 |

公开水域边界：

- 标准距离匹配使用 `±5%`，边界包含。
- 必须通过 GPS 和计时质量门禁；GPS 跳点、明显漂移或距离异常进入候选或忽略。
- V2 只使用整次活动标准距离，不做公开水域活动内 fastest 750m 截取。

### 4.7 越野跑整次活动纪录

| key | display_name | family | metric | unit | comparison | source_mode | scope_dimensions | availability | reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `trail_longest_distance` | 最长越野距离 | `activity_total_record` | `distance_m` | `meters` | `higher_is_better` | `activity_total` | `sport_scope` | `candidate_only` | 真实库越野样本为 0 |
| `trail_max_ascent` | 越野最大累计爬升 | `activity_total_record` | `ascent_m` | `meters_ascent` | `higher_is_better` | `activity_total` | `sport_scope` | `candidate_only` | 同上 |
| `trail_longest_elapsed_time` | 最长越野历时 | `activity_total_record` | `elapsed_time_sec` | `seconds` | `higher_is_better` | `activity_total` | `sport_scope` | `candidate_only` | 同上 |
| `trail_max_altitude` | 越野最高海拔 | `activity_total_record` | `max_altitude_m` | `meters_altitude` | `higher_is_better` | `activity_total` | `sport_scope` | `candidate_only` | 同上 |
| `trail_max_single_climb` | 越野最大连续爬升 | `activity_total_record` | `single_climb_m` | `meters_ascent` | `higher_is_better` | `activity_total` | `sport_scope` | `candidate_only` | 必须带范围，真实库越野样本为 0 |

越野跑边界：

- 不混入 road running、hiking 或 mountaineering。
- 整次活动纪录可先以 candidate-only 进入内部 dry-run，真实数据验证前不得 auto-confirm。
- `trail_pace_curve`、`trail_gap_curve` 是 `analysis_only`，不写 active record。

## 5. 动态 Route/Segment 定义

动态定义不产生无限 record keys。Registry 只注册以下静态 key，实例由后端生成 `scope_key`。

| key | display_name | family | metric | unit | comparison | source_mode | scope_dimensions | availability | reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `trail_route_best_time` | 越野同路线最佳时间 | `route_pr` | `elapsed_time_sec` | `seconds` | `lower_is_better` | `route_total` | `sport_scope, route_key` | `candidate_only` | 真实越野样本缺失，路线匹配需人工验收 |
| `trail_segment_best_time` | 越野赛段最佳时间 | `segment_pr` | `elapsed_time_sec` | `seconds` | `lower_is_better` | `segment` | `sport_scope, segment_key` | `candidate_only` | 赛段来源和范围需后续冻结 |
| `trail_climb_segment_best_time` | 越野爬坡赛段最佳时间 | `segment_pr` | `elapsed_time_sec` | `seconds` | `lower_is_better` | `segment` | `sport_scope, segment_key` | `candidate_only` | 爬坡赛段定义需后续冻结 |

动态实例标识：

```text
record_identity = record_key + "::" + scope_key
```

示例：

```json
{
  "record_key": "trail_route_best_time",
  "scope_key": "route:v1:sha256:...",
  "scope": {
    "sport_scope": "trail_running",
    "route_key": "route:v1:sha256:...",
    "route_direction": "same_direction"
  }
}
```

Route Signature V2 默认匹配阈值来自 golden manifest：

- 起终点容差 `100m`。
- 长度误差 `<= 5%`。
- 轨迹覆盖率 `>= 0.95`。
- corridor overlap `>= 0.85`。
- 反向路线必须拒绝，原因码 `route_direction_mismatch`。
- 低重合路线必须拒绝，原因码 `route_match_low_overlap`。

后续 `RCV2-28` 可以细化算法，但不得放宽“无真实越野样本前 candidate-only”的发布状态。

## 6. 分析曲线与模型估计边界

以下项目可以出现在 API ViewModel 或 Snapshot 的分析区，但不得进入 `career_pb_records` active/candidate 事实：

| key | 类型 | 边界 |
| --- | --- | --- |
| `cycling_power_duration_curve` | `analysis_curve` | 可由曲线缓存生成，用于展示和锚点辅助，不是纪录类型。 |
| `trail_pace_curve` | `analysis_curve` | 仅分析，不比较用户历史 PR。 |
| `trail_gap_curve` | `analysis_curve` | 仅分析，不作为正式成绩。 |
| `estimated_ftp` / `eftp` | `model_estimate` | 可显示为训练估计，不是纪录。 |
| `critical_power` / `w_prime` | `model_estimate` | 可用于分析，不是纪录。 |
| `map` / `pmax` | `model_estimate` | 可用于分析，不是纪录。 |
| `swolf_trend` | `analysis_curve` | 游泳效率分析，不是正式纪录。 |

## 7. Catalog 发布策略

Catalog 必须区分三层状态：

1. Registry 定义状态：本文的 `availability_state`。
2. 真实数据验收状态：`RCV2-40`、`RCV2-41` dry-run 和用户决策。
3. 单条 evidence 状态：质量评分、置信度和候选状态机。

默认发布矩阵：

| 运动/族 | 默认 Catalog 状态 | 原因 |
| --- | --- | --- |
| 跑步 V1 四项 | `available` | V1 已完成并有回归保护。 |
| 骑行功率锚点 | `available` | 普通骑行功率流覆盖 67 条；异常质量仍按候选处理。 |
| 骑行整次活动距离/爬升/历时 | `available` | 普通骑行样本充足，e-bike 排除。 |
| 骑行最大机械功 | `validation_required` | 功率积分和异常功率质量需后续闭环。 |
| 徒步整次活动距离/累计爬升/历时/最高海拔 | `available` | hiking 样本存在，但海拔质量仍需评分。 |
| 徒步最大连续爬升 | `candidate_only` | 必须带范围并人工复核。 |
| 泳池游泳 | `validation_required` | 无真实泳池样本，pool length schema 缺失。 |
| 公开水域游泳 | `candidate_only` | 只有 2 条真实样本，GPS 质量需 dry-run。 |
| 越野跑整次活动 | `candidate_only` | 真实库越野样本为 0。 |
| 越野路线/赛段 PR | `candidate_only` | 只有 fixture，缺真实验收。 |
| 分析曲线 | `analysis_only` | 不写正式纪录。 |
| 模型估计 | `model_only` | 不写正式纪录。 |

`available=false` 的 ViewModel 不代表完全隐藏。前端可以展示灰态、说明和“等待数据/待验证”，但不得制造假纪录或用 fixture 数据填充。

## 8. 最小数据要求

| family | minimum_data_requirements |
| --- | --- |
| `distance_time_pb` + `activity_total` | `activity_id, sport, distance_m, elapsed_time_sec, event_date, distance_quality, time_quality` |
| `distance_time_pb` + `best_effort_distance` | `activity_id, sport, elapsed_time_sec, event_date, range_start, range_end, pool_length_scope, stroke_scope, time_quality` |
| `power_duration_pb` | `activity_id, sport, power_stream, elapsed_time_sec, event_date, range_start, range_end, power_quality, indoor_scope` |
| `activity_total_record` | `activity_id, sport, metric_value, event_date, metric_quality` |
| `route_pr` | `activity_id, sport, route_signature, route_key, elapsed_time_sec, event_date, route_match_quality` |
| `segment_pr` | `activity_id, sport, segment_key, range_start, range_end, elapsed_time_sec, event_date, segment_quality` |

Activity 内范围要求：

- 骑行功率锚点：必须保存窗口起止时间或采样索引。
- 泳池 best-effort：必须保存连续 Length/Lap 范围。
- 最大连续爬升：必须保存起止距离/时间/海拔范围。
- route/segment PR：必须保存 route/segment scope 和活动内范围。

## 9. 冲突矩阵

| 冲突 | 决策 |
| --- | --- |
| 同一 `sport + family + source_mode + scope_dimensions` 下两个标准距离容差区间重叠 | Registry validation 失败；不得运行时静默选择。 |
| 同一 Activity 同时匹配多个 record definitions | 写审计原因 `record_definition_conflict`，不写 active，不生成候选。 |
| `available` 定义缺少必要 canonical fact | Evidence 进入 candidate 或 ignored，由 `RCV2-04` reason code 决定。 |
| `validation_required` 定义有高质量 fixture 通过 | 仍不得标记真实可用；fixture 不是真实数据验收。 |
| 前端请求不存在的 record key | API 返回受控空态或错误，不由前端 fallback 到硬编码。 |
| route/segment scope_key 缺失 | 不生成动态纪录实例。 |
| 模型估计值优于历史成绩 | 不写正式纪录，只进入分析区。 |
| W/kg 缺少活动日期历史体重 | 不注册 active W/kg 纪录，不用当前体重回填历史。 |

## 10. 后续测试计划

`RCV2-09` 代码化 Registry 时至少新增：

- record keys 唯一性测试。
- field whitelist 测试：family、unit、comparison、source_mode、availability。
- 跑步 V1 兼容测试：四项 key、容差、source_mode 和旧 API 不变。
- 动态 route/segment 不拼接新 record type 测试。
- model/analysis key 不进入 active record definitions 测试。
- Catalog 状态测试：泳池 `validation_required`、越野 `candidate_only`、W/kg 不 active。
- scope_dimensions 由后端返回，前端不计算 Scope 的契约测试。

`RCV2-15` 至 `RCV2-31` Resolver 任务必须复用 `tests/fixtures/records_center_v2/golden_manifest.json`，不得把 fixture 通过解释为真实数据 Verified。
