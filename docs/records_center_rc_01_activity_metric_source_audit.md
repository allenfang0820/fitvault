# RC-01 Activity 距离与计时事实源审计

日期：2026-07-13

## 执行提示词

目标：确认跑步 PB 应读取的 canonical 距离与 elapsed time 字段，回答 `duration`、`duration_sec`、moving time、elapsed time 的真实语义和历史数据可用性。

范围：FIT 解析链路、Metrics Resolver、Activity schema、真实 SQLite 样本，以及跑步机、自动暂停和字段缺失样本。

约束：只读审计，不实现成绩比较，不改 schema，不扫描轨迹生成正式 PB，不写入正式 PB 表。

完成定义：形成字段来源链、真实库覆盖统计、数据质量分类和 RC-03 可使用的 canonical 字段建议。

## 1. FIT 到 Activity 字段来源链

当前 FIT 解析链路：

```text
FIT session message
  -> fit_engine.FITCoreEngine._read_session_info()
  -> fit_engine basic_info
  -> main._parse_fit_activity_for_sync()
  -> profile_backend.build_activity_payload()
  -> MetricsResolver shadow overwrite
  -> main._insert_activity_sync_row() / _update_activity_sync_row()
  -> activities
```

距离链路：

- `fit_engine._read_session_info()` 读取 `session.total_distance`。
- `FITCoreEngine.parse_fit_file()` 输出 `basic_info.total_distance_m` 和 `basic_info.total_distance_km`。
- `main._parse_fit_activity_for_sync()` 先把 `basic.total_distance_km` 传给 payload 的 `distance_km`。
- `MetricsResolver._build_storage_model()` 再从 raw session 的 `total_distance` 输出 `distance_m` 与 `distance_km`。
- resolver overwrite 区块将 `activities.distance = distance_km * 1000.0`、`activities.dist_km = distance_km`。

计时链路：

- `fit_engine._read_session_info()` 当前写法是 `total_timer_time = msg.get_value("total_timer_time") or msg.get_value("total_elapsed_time")`。
- `FITCoreEngine.parse_fit_file()` 输出 `basic_info.total_timer_time`。
- `main._parse_fit_activity_for_sync()` 将它作为 payload 的 `duration_sec`。
- `MetricsResolver._build_storage_model()` 从 `total_timer_time` 输出 `duration_sec`，并尝试从 `total_moving_time` 输出 `moving_time_sec`。
- resolver overwrite 区块将 `activities.duration = duration_sec`、`activities.duration_sec = duration_sec`。

结论：当前 `duration` 与 `duration_sec` 在导入后是同源字段，不能互为校验；其上游主要是 FIT `total_timer_time`，不等同于 PB 规则要求的 elapsed time。

## 2. Activity schema 与当前字段语义

Activity 表当前包含：

- 距离：`dist_km REAL`、`distance REAL`
- 时长：`duration_sec INTEGER`、`duration INTEGER`
- 轨迹：`points_json`、`track_json`
- 来源/质量辅助：`source_type`、`is_mock`、`processing_status`、`processing_error`、`sport_type`、`sub_sport_type`

代码中已有明确注释：resolver overwrite 后 `distance` 应为米，`dist_km` 应为公里。但真实库中仍存在历史行的 `distance == dist_km`，说明旧数据可能保留公里语义。PB 后续应优先使用 `dist_km`，不要直接信任 `distance`。

## 3. 真实 SQLite 只读统计

数据库：

```text
/Users/fanglei/.fitvault/user_profile.db
```

只读连接方式：

```python
sqlite3.connect("file:/Users/fanglei/.fitvault/user_profile.db?mode=ro", uri=True)
```

总体：

| 指标 | 数量 |
| --- | ---: |
| active Activity | 253 |
| active running Activity | 95 |
| running `duration > 0` | 95 |
| running `duration_sec > 0` | 95 |
| running `duration == duration_sec` | 95 |
| running `duration != duration_sec` | 0 |
| running `dist_km > 0` | 95 |
| running `distance > 0` | 95 |
| running `distance ~= dist_km * 1000` | 89 |
| running `distance ~= dist_km` | 6 |

运动分布前几项：

| sport_type | sub_sport_type | active 数 |
| --- | --- | ---: |
| running | generic | 92 |
| cycling | generic | 91 |
| walking | generic | 38 |
| hiking | generic | 6 |
| mountaineering | generic | 5 |
| running | track | 3 |

跑步机/室内：

- 当前 active running 样本中未发现 `sport_type/sub_sport_type/title` 明确包含 treadmill/跑步机。
- 当前 running 样本均有 GPS 起点或未命中室内条件；跑步机可信度规则需要在后续任务中保留，但本库没有可用于验证的跑步机样本。

## 4. 轨迹 elapsed 对 `duration_sec` 的交叉校验

审计方法：对 active running 的 `points_json/track_json` 取首尾时间差，比较 `duration_sec`。

样本量：95 条 running Activity。

| 分类 | 数量 | 含义 |
| --- | ---: | --- |
| `abs(points_elapsed - duration_sec) <= 5s` | 84 | `duration_sec` 与轨迹首尾 elapsed 基本一致 |
| `points_elapsed - duration_sec > 5s` | 8 | 轨迹 elapsed 明显大于 `duration_sec`，疑似自动暂停或 timer time |
| `duration_sec - points_elapsed > 5s` | 3 | 存在轻微不一致或轨迹采样首尾缺口 |
| 无时间点或解析失败 | 0 | 本次 running 样本均可解析 |

标准距离样本表现：

| bucket | 样本 | match | timer 小于 elapsed | duration 大于 points |
| --- | ---: | ---: | ---: | ---: |
| running_5k | 6 | 6 | 0 | 0 |
| running_10k | 5 | 5 | 0 | 0 |
| running_half_marathon | 2 | 2 | 0 | 0 |
| running_marathon | 0 | 0 | 0 | 0 |
| other | 82 | 71 | 8 | 3 |

样例：

| activity_id | dist_km | duration_sec | points_elapsed | diff |
| --- | ---: | ---: | ---: | ---: |
| 169 | 5.0659 | 1727 | 1730 | +3 |
| 168 | 5.04768 | 1851 | 1851 | 0 |
| 108 | 9.53095 | 2406 | 2450 | +44 |
| 166 | 5.81972 | 2193 | 2389 | +196 |
| 154 | 3.74423 | 1420 | 2009 | +589 |

结论：真实库中标准距离样本目前没有发现明显自动暂停差异，但字段层面仍不能保证 elapsed；非标准跑步样本已证明 `duration_sec` 可能短于轨迹 elapsed。

## 5. 数据质量分类规则建议

为 RC-03/RC-04 提供的临时分类：

| 分类 | 判定 | PB 处理建议 |
| --- | --- | --- |
| `reliable_elapsed` | 有明确 `elapsed_time_sec` 字段，或 Performance Summary 已用轨迹首尾/elapsed 字段验证 `duration_sec` 与 elapsed 差异不超过 5 秒 | 可参与自动确认的基础条件 |
| `timer_time_only` | 只有 `total_timer_time/duration_sec`，且轨迹 elapsed 明显更长，或存在自动暂停证据 | 最高进入候选 |
| `semantics_unknown` | 只有 `duration/duration_sec`，无 elapsed 交叉证据 | 最高进入候选 |
| `missing_time` | 无正数时长 | 忽略正式 PB |
| `reliable_distance` | `dist_km > 0`，或 `distance` 明确为米且可转换为米 | 可参与距离匹配 |
| `distance_unit_ambiguous` | `distance` 与 `dist_km` 语义冲突，且无 `dist_km` | 候选或忽略 |
| `missing_distance` | 无正数距离 | 忽略正式 PB |

当前真实库跑步分类：

| 分类 | 数量 |
| --- | ---: |
| `reliable_distance` by `dist_km` | 95 |
| `distance_unit_ambiguous` if relying only on `distance` | 6 |
| `reliable_elapsed` by point-time cross-check | 84 |
| `timer_time_only` by point elapsed > duration | 8 |
| `semantics_unknown` by field name alone | 95 |
| `missing_time` | 0 |
| `missing_distance` | 0 |

说明：`semantics_unknown` 是字段本身的判断；`reliable_elapsed` 是本次审计通过轨迹时间额外建立的证据。后续正式 Resolver 不应直接读取 raw track，而应由 Performance Summary 产出白名单质量字段。

## 6. Canonical 字段建议

距离：

```text
distance_m = round(dist_km * 1000)
```

优先级：

1. `dist_km > 0`：作为当前库最可靠来源。
2. `distance > 1000`：视为米，作为兜底。
3. `distance <= 1000` 且无 `dist_km`：单位不确定，不自动确认。

计时：

```text
elapsed_time_sec
```

当前 Activity 表没有可直接信任的 canonical `elapsed_time_sec`。建议 RC-09 的 Performance Summary 输出：

```json
{
  "elapsed_time_sec": 1730,
  "timer_time_sec": 1727,
  "elapsed_source": "fit_total_elapsed_time|track_time_span|timer_time_cross_checked|unknown",
  "time_quality": "reliable_elapsed|timer_time_only|semantics_unknown|missing_time",
  "reason_codes": ["duration_from_total_timer_time", "track_elapsed_matches_timer_time"]
}
```

来源优先级：

1. 新导入时若 FIT session 存在 `total_elapsed_time`，应单独保存或进入 Performance Summary。
2. 若无 `total_elapsed_time`，可由 Performance Resolver 用轨迹首尾时间生成 `track_elapsed_sec`，但只输出摘要，不向 PB Resolver 暴露轨迹。
3. `duration_sec` 当前应视为 `timer_time_sec` 或兼容旧字段；只有经过 elapsed 交叉校验后，才能作为 `elapsed_time_sec` 使用。

## 7. 对 RC-03 的冻结输入

- 距离单位应冻结为米，当前库以 `dist_km * 1000` 作为 canonical 迁移来源。
- 比较主值必须是 `elapsed_time_sec` 整数秒。
- 旧数据如果只有 `duration/duration_sec` 且没有 elapsed 质量证据，不得自动成为正式纪录。
- 当前真实标准距离样本可作为 `±3%` dry-run 的优先复核对象：5K 17 条、10K 9 条、半马 2 条、马拉松 0 条。
- 跑步机样本当前缺失，候选策略必须由契约先冻结，再等待真实样本验证。

## 8. 只读审计 SQL / 脚本摘要

本次使用的核心只读查询：

```sql
SELECT COUNT(*) FROM activities WHERE deleted_at IS NULL;

SELECT sport_type, sub_sport_type, COUNT(*)
FROM activities
WHERE deleted_at IS NULL
GROUP BY sport_type, sub_sport_type;

SELECT
  COUNT(*) n,
  SUM(duration > 0) duration_pos,
  SUM(duration_sec > 0) duration_sec_pos,
  SUM(duration = duration_sec) duration_equal,
  SUM(distance > 0) distance_pos,
  SUM(dist_km > 0) dist_km_pos,
  SUM(ABS(distance - dist_km * 1000.0) <= 1) distance_m_matches,
  SUM(ABS(distance - dist_km) <= 0.001) distance_km_matches
FROM activities
WHERE deleted_at IS NULL
  AND lower(COALESCE(sport_type, '')) IN ('running', 'run', 'trail_running', 'track_running', 'road_running', 'treadmill_running');
```

轨迹 elapsed 校验使用 Python 只读解析 `points_json/track_json` 的 `time` 字段，不写数据库。
