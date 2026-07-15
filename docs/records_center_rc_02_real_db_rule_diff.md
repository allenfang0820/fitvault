# RC-02 真实数据库与 ±3% 迁移影响审计

日期：2026-07-13

## 执行提示词

目标：用只读方式评估从当前硬编码距离区间切换到统一 `±3%` 后，真实用户 PB 会新增、移除或替换哪些结果。

范围：真实 SQLite 中 active running Activity、当前硬编码范围、新 `±3%` 范围、当前 active PB 表、计时口径风险标记。

约束：不写正式 PB 表，不执行 migration，不要求用户确认迁移，不读取或保存 raw FIT、本地路径或完整轨迹。

完成定义：输出每个 `pb_type` 的共同项、新增项、移除项、active 变化、边界样本和可复跑只读脚本。

## 1. 可复跑脚本

脚本：

```text
scripts/records_center_rc_02_rule_diff.py
```

运行：

```bash
.venv312/bin/python scripts/records_center_rc_02_rule_diff.py --db /Users/fanglei/.fitvault/user_profile.db
```

脚本使用 SQLite `mode=ro` 只读连接，不写任何表。

## 2. 规则对照

| pb_type | 当前硬编码范围 | 新 `±3%` 范围 |
| --- | ---: | ---: |
| `running_5k` | 4.8-5.3 km | 4.85-5.15 km |
| `running_10k` | 9.5-10.8 km | 9.7-10.3 km |
| `running_half_marathon` | 20.5-21.7 km | 20.46458-21.73043 km |
| `running_marathon` | 41.0-43.0 km | 40.92915-43.46085 km |

数据集：

- DB：`/Users/fanglei/.fitvault/user_profile.db`
- active running Activity：95
- 距离来源：`dist_km`
- 时间值：当前表内 `duration_sec/duration`
- 时间质量：沿用 RC-01 轨迹 elapsed 只读交叉校验

## 3. 总体差异

| pb_type | 当前候选 | 新规则候选 | 共同项 | 新增 | 移除 | active 是否变化 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `running_5k` | 8 | 6 | 6 | 0 | 2 | 不变 |
| `running_10k` | 8 | 5 | 5 | 0 | 3 | 变化 |
| `running_half_marathon` | 2 | 2 | 2 | 0 | 0 | 不变 |
| `running_marathon` | 0 | 0 | 0 | 0 | 0 | 不变 |

结论：

- 新 `±3%` 规则不会新增候选。
- 新规则会移除偏长 5K 2 条、偏短/偏长 10K 3 条。
- 10K 当前 active 会变化：当前规则的最快 10K 是活动 `108`，新规则下被排除，最佳变为活动 `150`。

## 4. 每项纪录影响

### running_5k

当前 best 与新规则 best 都是：

| activity_id | 日期 | 距离 | 用时 | 时间质量 | 误差 |
| --- | --- | ---: | ---: | --- | ---: |
| 167 | 2022-06-28 | 5.11123 km | 1628s | reliable_elapsed | 2.225% |

移除项：

| activity_id | 日期 | 距离 | 用时 | 时间质量 | 误差 | 原因 |
| --- | --- | ---: | ---: | --- | ---: | --- |
| 153 | 2025-01-05 | 5.29086 km | 1926s | reliable_elapsed | 5.817% | 超出 `±3%` |
| 100 | 2026-02-03 | 5.30000 km | 1990s | reliable_elapsed | 6.000% | 超出 `±3%` |

影响：active 不变，但历史候选集合收窄。

### running_10k

当前规则 best：

| activity_id | 日期 | 距离 | 用时 | 时间质量 | 轨迹 elapsed | diff | 误差 |
| --- | --- | ---: | ---: | --- | ---: | ---: | ---: |
| 108 | 2025-05-03 | 9.53095 km | 2406s | timer_time_only | 2450s | +44s | 4.690% |

新 `±3%` best：

| activity_id | 日期 | 距离 | 用时 | 时间质量 | 轨迹 elapsed | diff | 误差 |
| --- | --- | ---: | ---: | --- | ---: | ---: | ---: |
| 150 | 2024-06-29 | 10.02619 km | 3278s | reliable_elapsed | 3278s | 0s | 0.262% |

移除项：

| activity_id | 日期 | 距离 | 用时 | 时间质量 | 误差 | 原因 |
| --- | --- | ---: | ---: | --- | ---: | --- |
| 108 | 2025-05-03 | 9.53095 km | 2406s | timer_time_only | 4.690% | 低于 9.7km，且 timer time 短于 elapsed |
| 360 | 2026-07-11 | 10.34986 km | 4201s | reliable_elapsed | 3.499% | 高于 10.3km |
| 336 | 2026-06-27 | 10.49500 km | 4424s | reliable_elapsed | 4.950% | 高于 10.3km |

影响：当前 active 10K 需要在迁移时替换。由于旧 active `108` 同时存在距离误差和 timer-time 风险，新规则替换方向与交付手册“公平与 elapsed time”目标一致。

### running_half_marathon

当前 best 与新规则 best 都是：

| activity_id | 日期 | 距离 | 用时 | 时间质量 | 误差 |
| --- | --- | ---: | ---: | --- | ---: |
| 239 | 2023-03-26 | 21.45749 km | 7642s | reliable_elapsed | 1.706% |

影响：候选集合和 active 均不变。

### running_marathon

当前规则与新规则都没有候选。无迁移影响。

## 5. 5K / 10K 边界审计

重点样本：

| activity_id | 日期 | 距离 | 用时 | 新规则结果 | 时间质量 |
| --- | --- | ---: | ---: | --- | --- |
| 169 | 2022-06-15 | 5.06590 | 1727s | 保留 | reliable_elapsed |
| 168 | 2022-06-23 | 5.04768 | 1851s | 保留 | reliable_elapsed |
| 167 | 2022-06-28 | 5.11123 | 1628s | 保留 | reliable_elapsed |
| 153 | 2025-01-05 | 5.29086 | 1926s | 移除 | reliable_elapsed |
| 100 | 2026-02-03 | 5.30000 | 1990s | 移除 | reliable_elapsed |
| 108 | 2025-05-03 | 9.53095 | 2406s | 移除 | timer_time_only |
| 150 | 2024-06-29 | 10.02619 | 3278s | 保留，成为新 10K best | reliable_elapsed |
| 360 | 2026-07-11 | 10.34986 | 4201s | 移除 | reliable_elapsed |
| 336 | 2026-06-27 | 10.49500 | 4424s | 移除 | reliable_elapsed |

## 6. 当前 `career_pb_records` active 对照

当前正式表 active：

| pb_type | activity_id | value | event_date |
| --- | --- | ---: | --- |
| `running_5k` | 167 | 1628 | 2022-06-28 |
| `running_10k` | 108 | 2406 | 2025-05-03 |
| `running_half_marathon` | 239 | 7642 | 2023-03-25 |

与新 `±3%` dry-run 对照：

- `running_5k` 一致。
- `running_10k` 不一致，需要迁移替换为活动 `150`。
- `running_half_marathon` 一致；日期显示存在来源时区差异，dry-run 使用 `start_time` 日期为 2023-03-26，表内 active 为 2023-03-25，后续日期口径需要继续保持 Activity 本地日期规则。

## 7. 受计时口径不确定影响的 Activity

在当前标准距离候选中：

- `running_10k` 活动 `108` 是当前 active，但质量为 `timer_time_only`：`duration_sec=2406`，轨迹首尾 elapsed 为 `2450`，差异 +44 秒。
- 新 `±3%` 规则会排除活动 `108`，因此迁移后 active 变化同时解决一个计时口径风险。
- 其他保留的 5K、10K、半马候选本次审计未发现 points elapsed 明显大于 `duration_sec`。

## 8. RC-03 输入

- 统一 `±3%` 规则对真实数据有实际 active 影响，不能静默迁移；RC-15/RC-27 必须保留 dry-run 与人工复核流程。
- `running_10k` 的旧 active 应作为迁移说明中的重点案例。
- `event_date` 与 `start_time/start_time_utc` 的本地日期口径需要在 RC-03/RC-06 明确，避免迁移时半马日期前后不一致。
- 新规则没有新增候选，因此首轮迁移风险主要是“移除/替换”，不是扩容。
