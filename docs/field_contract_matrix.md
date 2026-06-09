# 字段契约矩阵(全链路可追溯)

> 依据:`fit-arch-contrac.md` §2.1 "字段全链路可追溯" + `ARCHITECTURE.md` §6 "FIT → Resolver → DB → UI 字段契约必须长期维护"
> 版本:V9.4.4 / 2026-Q2
> 状态:核心字段已就位
> 配套文档:`docs/training_effect_v1_contract.md`(训练收益子集)、`docs/v9_2_overview_design.md` §7.1(概览页子集)

---

## 0. 目的

脉图要求**任何 UI 字段必须能追溯**：

```text
UI → DB → Resolver → FIT SDK
```

本文档是**单一登记处**,所有新字段 / 字段重命名 / 字段废弃必须在此登记。

---

## 1. Hero 字段矩阵(概览页主指标)

| UI 字段 | DB 列 | Resolver 输出路径 | FIT SDK 字段 | 备注 |
|---|---|---|---|---|
| `record.distance` | `activities.distance` (m) | `_build_record_from_row` | `session.total_distance / 100` | 单位米;前端 _formatHeroValue 转 km |
| `record.duration` | `activities.duration` (s) | 同上 | `session.total_timer_time` | 单位秒 |
| `record.avg_pace` | `activities.avg_pace` (s/km) | `_compute_avg_pace` | `session.total_timer_time / distance` | 后端 Resolver 派生 |
| `record.avg_hr` | `activities.avg_hr` | `_build_record_from_row` | `session.avg_heart_rate` | 直读 |
| `record.max_hr` | `activities.max_hr` | 同上 | `session.max_heart_rate` | 直读 |
| `record.calories` | `activities.calories` | 同上 | `session.total_calories` | 直读 |
| `record.ascent` | `activities.gain_m` (m) | 同上 | `session.total_ascent` | 命名转换:gain_m → ascent |
| `record.swolf` | `activities.swolf` | 同上 | `session.total_cycles / total_distance` | 游泳专用 |
| `record.avg_power` | `activities.avg_power` | 同上 | `session.avg_power` | 骑行/跑步 |
| `record.normalized_power` | `activities.normalized_power` | `_compute_normalized_power` | records → 30s 平均 → 4 次幂 | 后端 Resolver 派生(V7.x §指标 4) |
| `record.avg_cadence` | `activities.avg_cadence` | `_build_record_from_row` | `session.avg_running_cadence` / `session.avg_cadence` | 跑步/骑行 |
| `record.avg_speed` | (无 DB 列,Res 计算) | `_compute_avg_speed` | `session.enhanced_avg_speed` | 骑行专用 |

---

## 2. 圈速(Lap)字段矩阵(概览页/详情页圈速表)

> V9.4.4 新增完备:fit_engine → Resolver → DB → API → UI 全链路

### 2.1 圈速表 UI 列(V9.4.4 后端真理源驱动)

| UI 列 | 后端 `detail.lap_columns` 值 | DB 列 | Resolver 输出 | FIT SDK 字段 | 单位 | 启用 sport |
|---|---|---|---|---|---|---|
| `圈速` | (固定) | `activities.laps_json` | `_build_real_laps_from_row` | — | 编号 1,2,3... | 所有 |
| `配速` | `avg_pace` | 同上 | `pace_sec = round(elapsed / (dist_m/1000))` | `lap.total_timer_time / lap.total_distance` | sec/km | `LAP_PACE_TYPES` |
| `心率` | `avg_hr` | 同上 | `lap.hr` | `lap.avg_heart_rate` | bpm | `LAP_HR_TYPES` |
| `最大心率` | `max_hr` | 同上 | `lap.max_hr` | `lap.max_heart_rate` | bpm | `LAP_MAX_HR_TYPES` |
| `步频` | `cadence` | 同上 | `lap.cadence` | `lap.avg_cadence` | spm | `LAP_CADENCE_TYPES` |
| `GCT` | `gct` | 同上 | `lap.gct_ms` | `lap.avg_stance_time` | ms | `LAP_GCT_TYPES` |
| `功率` | `power` | 同上 | `lap.power_w` | `lap.avg_power` | W | `LAP_POWER_TYPES` |
| `累计爬升` | `ascent` | 同上 | `lap.ascent_m` | `lap.total_ascent` | m | `LAP_ASCENT_TYPES` |
| `累计下降` | `descent` | 同上 | `lap.descent_m` | `lap.total_descent` | m | `LAP_DESCENT_TYPES` |

> 真理源函数:`main.py::resolve_lap_columns(sport_type)`
> 列开关集合:`LAP_*_TYPES` (main.py,定义同 1 表)
> 前端列 label 真理源:`HERO_FIELD_LABELS` (track.html)
> 前端列格式化真理源:`_formatHeroValue` (track.html)

### 2.2 圈速 fit_engine → Resolver 字段归一化

| FIT 字段 (raw) | fit_engine 输出 | Resolver 归一化 | 详情 API 输出 |
|---|---|---|---|
| `lap.total_distance` | `total_distance` | `distance_m` | `distance_km` |
| `lap.total_timer_time` | `total_timer_time` | `elapsed_sec` | (Res 计算) `pace_sec` |
| `lap.avg_heart_rate` | `avg_heart_rate` | `avg_hr` | `hr` |
| `lap.max_heart_rate` | `max_heart_rate` | `max_hr` | `max_hr` |
| `lap.avg_running_cadence` / `avg_cadence` | `avg_cadence` | `avg_cadence` | `cadence` |
| `lap.avg_stance_time` | `avg_stance_time` | `stance_time_ms` | `gct_ms` |
| `lap.avg_power` | `avg_power` | `avg_power` | `power_w` |
| `lap.total_calories` | `total_calories` | (归一化外) | (未透传) |
| `lap.total_ascent` | `total_ascent` | `total_ascent` | `ascent_m` |
| `lap.total_descent` | `total_descent` | `total_descent` | `descent_m` |
| `lap.avg_vertical_oscillation` | `avg_vertical_oscillation` | `vertical_oscillation_cm` | (未透传) |
| `lap.avg_vertical_ratio` | `avg_vertical_ratio` | `vertical_ratio_pct` | (未透传) |
| `lap.avg_stance_time_balance` | `avg_stance_time_balance` | `stance_time_balance_pct` | (未透传) |
| `lap.avg_step_length` | `avg_step_length` | `stride_length_m` | (未透传) |
| `lap.avg_fractional_cadence` | `avg_fractional_cadence` | (未归一化) | (未透传) |

---

## 3. 训练收益(Training Effect)字段矩阵

> V9.4.4:纠正 V9.4.0 错误字段名 + 删除 V9.4.1 启发式估算
> 真理源:详契约 `docs/training_effect_v1_contract.md`

| UI 字段 | DB 列 | Resolver 路径 | FIT SDK 字段 | 备注 |
|---|---|---|---|---|
| `record.detail.training_effect.primary.score` | `activities.aerobic_training_effect` (REAL) | `MetricsResolver.build_training_effect` | `session.total_training_effect` (scale 0.1 → 0.0~5.0) | Garmin Firstbeat 私有算法 |
| `record.detail.training_effect.secondary.score` | `activities.anaerobic_training_effect` (REAL) | 同上 | `session.total_anaerobic_training_effect` | 同上 |
| `record.detail.training_effect.primary.label/summary` | (无,查表) | `SPORT_TE_MATRIX[sport][primary][idx]` | — | Resolver 查表 |
| `record.detail.training_effect.global_level` | (无) | `max([primary.level, secondary.level])` | — | Resolver 聚合 |
| `record.detail.training_effect.overall_summary` | (无) | 字符串拼接 | — | Resolver 拼接 |
| `record.detail.training_effect.data_source` | (无) | 硬编码 `'fit_sdk'` | — | V9.4.4 单一值 |

**禁用路径(V9.4.4 已删除)**:
- ~~`avg_hr / max_hr / duration_sec` 启发式估算~~ → V9.4.1~V9.4.3 违规,已删
- ~~`hr_zone_distribution` logistic 压缩~~ → 同一违规,已删

---

## 4. 地区 / 天气字段矩阵

| UI 字段 | DB 列 | 来源 | 异步? |
|---|---|---|---|
| `record.region_display` | `activities.region_display` | profile_backend 异步解析(OpenStreetMap) | 是 |
| `record.region` | `activities.region` | 同上(全路径) | 是 |
| `record.region_status` | `activities.region_status` | 同上 | 是 |
| `record.weather` | `activities.weather_json` | 后端 weather API 实时注入 | 是 |

---

## 5. 报告派生指标(复盘系统用,V9.x 新增)

> 下一阶段"运动复盘系统"主要消费字段,本节是扩展位

| UI 字段 | DB 列 | Resolver 路径 | FIT SDK 字段 | 备注 |
|---|---|---|---|---|
| `record.up_count` | `activities.up_count` | `compute_report_metrics()` | records 海拔差分 | 爬升次数 |
| `record.down_count` | `activities.down_count` | 同上 | 同上 | 下降次数 |
| `record.max_single_climb_m` | `activities.max_single_climb_m` | 同上 | 同上 | 单段最大爬升 |
| `record.difficulty_score` | `activities.difficulty_score` | 同上 | 综合评分 | 0~100 |
| `record.avg_grade_pct` | `activities.avg_grade_pct` | 同上 | records 坡度 | 平均坡度 |
| `record.max_slope_pct` | `activities.max_slope_pct` | 同上 | 同上 | 最大坡度 |
| `record.min_slope_pct` | `activities.min_slope_pct` | 同上 | 同上 | 最小坡度 |
| `record.uphill_pct` | `activities.uphill_pct` | 同上 | 同上 | 上坡占比 |
| `record.downhill_pct` | `activities.downhill_pct` | 同上 | 同上 | 下坡占比 |
| `record.report_metrics_version` | `activities.report_metrics_version` | 同上 | — | 派生指标 schema 版本 |

---

## 6. 运动类型标准化矩阵

> Resolver §4.3 "活动类型标准化"职责

| UI 字段值 | DB 值 | 含义 |
|---|---|---|
| `running` | `running` | 跑步(硬路面) |
| `trail_running` | `trail_running` | 越野跑 |
| `treadmill_running` | `treadmill_running` | 跑步机 |
| `hiking` | `hiking` | 徒步 |
| `mountaineering` | `mountaineering` | 登山 |
| `walking` | `walking` | 步行 |
| `cycling` | `cycling` | 骑行(默认) |
| `road_cycling` | `road_cycling` | 公路车 |
| `mountain_biking` | `mountain_biking` | 山地车 |
| `indoor_cycling` | `indoor_cycling` | 室内骑行 |
| `swimming` | `swimming` | 泳池游泳 |
| `open_water_swimming` | `open_water_swimming` | 开放水域 |
| `strength` | `strength_training` | 力量训练 |
| `hiit` | `hiit` | HIIT |
| `yoga` | `yoga` | 瑜伽 |
| `pilates` | `pilates` | 普拉提 |

> 真理源:`SPORT_TYPE_CN` (前端) / 后端 sport_type 列

---

## 7. 已废弃字段(V9.4.4 审计)

| 旧名 | 新名 | 废弃时间 | 原因 |
|---|---|---|---|
| `ascent` | `gain_m` | V8.x | 命名歧义:ascent 可能指"爬升"或"上行程" |
| `sub_sport` | `sub_sport_type` | V8.x | 与 activity_type 易混 |
| ~~`training_effect_aerobic`~~ (FIT 219) | `total_training_effect` (FIT 7) | V9.4.4 | V9.4.0 误用字段名,fitparse 静默 None |
| ~~`anaerobic_training_effect` 启发式估算~~ | `total_anaerobic_training_effect` (FIT 13) | V9.4.4 | V9.4.1 启发式违规,删除 |

---

## 8. 字段版本化(§11.3)

| 阶段 | 字段 | 当前 | 未来 |
|---|---|---|---|
| M0 | `field_contract_version` | 未实施 | V10.x 引入 |
| M0 | `report_metrics_version` | 已列 | V9.x 已实施 |
| M0 | `schema_version` | 未实施 | V10.x 引入 |

---

## 9. 真理源索引(快速跳转)

| 维度 | 真理源 | 文件 |
|---|---|---|
| 字段中文 label | `HERO_FIELD_LABELS` | track.html |
| 字段图标 | `HERO_FIELD_ICONS` | track.html |
| 字段格式化(单位/精度) | `_formatHeroValue` | track.html |
| 运动类型 → 6 字段 Hero | `HERO_FIELD_REGISTRY` | track.html |
| 运动类型中文 label | `SPORT_TYPE_CN` | track.html |
| 圈速列启用(后端) | `LAP_*_TYPES` / `resolve_lap_columns` | main.py |
| 圈速列启用(后端功率/爬升) | `POWER_ELIGIBLE_TYPES` / `OUTDOOR_LAND_GAIN_TYPES` | main.py |
| 圈速列 label(前端) | `HERO_FIELD_LABELS` | track.html |
| 训练收益矩阵 | `SPORT_TE_MATRIX` / `TE_LEVELS_BY_INDEX` | metrics_resolver.py |
| 训练收益卡 label 真理源 | `record.detail.training_effect.{primary,secondary}.label` | metrics_resolver.py |
| 标题解析 | `_resolveDisplayTitle` / `_cleanDisplayTitle` | track.html |
| 标题派生 | `_derive_title` | fit_engine.py |
| 地区显示 | `sportHubRegionDisplay` | track.html |
