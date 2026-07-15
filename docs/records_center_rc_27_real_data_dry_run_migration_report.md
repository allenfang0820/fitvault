# RC-27 真实数据 dry-run、迁移与人工复核报告

日期：2026-07-14

## 执行提示词摘要

目标：在不直接污染真实 active 结果的前提下，用当前真实库验证 Records Center 新规则、候选、历史迁移和回退路径，并准备人工复核材料与恢复方案。

本轮执行边界：

- 已备份真实数据库。
- 已在 staging 副本执行 dry-run 和 apply 验证。
- 未对真实库执行 rebuild/apply。
- 因任务明确要求人工复核，本任务暂不标记 Done。

## 数据库备份与校验

- 源库：`/Users/fanglei/.fitvault/user_profile.db`
- 源库大小：`428044288`
- 源库 sha256：`c76b6ce5d7bb736e8510e5b750b1fcf8f93285a122f582e050d57bbd2470108f`
- 备份库：[user_profile_rc27_backup_20260714_004536.db](/Users/fanglei/应用开发/AI%20track/docs/records_center_real_db_audit/user_profile_rc27_backup_20260714_004536.db)
- 备份 sha256：`c76b6ce5d7bb736e8510e5b750b1fcf8f93285a122f582e050d57bbd2470108f`
- staging 库：[user_profile_rc27_staging_20260714_004536.db](/Users/fanglei/应用开发/AI%20track/docs/records_center_real_db_audit/user_profile_rc27_staging_20260714_004536.db)
- staging sha256 初始值：`c76b6ce5d7bb736e8510e5b750b1fcf8f93285a122f582e050d57bbd2470108f`

## Staging dry-run 结果

dry-run 输出文件：[rc27_dry_run_plan.json](/Users/fanglei/应用开发/AI%20track/docs/records_center_real_db_audit/rc27_dry_run_plan.json)

- run_id：`records_rebuild:66f88b17a5e99c6e`
- resolver_version：`records-v1-rc27-dry-run`
- processed：`253`
- wall time：`37.406ms`
- metrics.elapsed_ms：`37.391ms`

dry-run 前后 staging 计数未变化：

| 指标 | dry-run 前 | dry-run 后 |
|---|---:|---:|
| career_pb_records | 3 | 3 |
| active_pb_records | 3 | 3 |
| career_event_candidates | 32 | 32 |

动作摘要：

| 动作 | 数量 |
|---|---:|
| new | 0 |
| replace | 0 |
| candidate | 13 |
| unchanged | 0 |
| ignored | 240 |

原因计数：

| reason_code | 数量 |
|---|---:|
| distance_from_dist_km | 244 |
| duration_from_total_timer_time | 253 |
| duration_semantics_unknown | 253 |
| record_definition_not_matched | 240 |
| distance_missing | 9 |

## Staging apply 验证

apply 输出文件：[rc27_staging_apply_result.json](/Users/fanglei/应用开发/AI%20track/docs/records_center_real_db_audit/rc27_staging_apply_result.json)

- run_id：`records_rebuild:5849c6fe7eb97bfa`
- resolver_version：`records-v1-rc27-staging-apply`
- processed：`253`
- applied_count：`253`
- wall time：`104.182ms`
- active PB 仍为 `3` 条。
- 候选从 `32` 增至 `45`，新增 `13` 条。
- record_events 从 `0` 增至 `506`。

staging apply 后当前 active PB：

| pb_type | record_id | activity_id | value | date |
|---|---|---:|---|---|
| running_10k | `pb:running_10k:108` | 108 | 40:06 | 2025-05-03 |
| running_half_marathon | `pb:running_half_marathon:239` | 239 | 2:07:22 | 2023-03-25 |
| running_5k | `pb:running_5k:167` | 167 | 27:08 | 2022-06-28 |

历史演进查询验证：

| pb_type | history length |
|---|---:|
| running_10k | 1 |
| running_half_marathon | 1 |
| running_5k | 1 |

## 候选清单

人工复核样本文件：[rc27_manual_review_samples.json](/Users/fanglei/应用开发/AI%20track/docs/records_center_real_db_audit/rc27_manual_review_samples.json)

| activity_id | record_key | distance_m | elapsed_time_sec | confidence | title/date |
|---:|---|---:|---:|---:|---|
| 101 | running_5k | 5080 | 1867 | 0.86 | 秀英区 Track / 2026-02-04 |
| 102 | running_5k | 5090 | 2046 | 0.86 | 秀英区 Track / 2026-02-05 |
| 136 | running_10k | 10250 | 4122 | 0.86 | 北京市 跑步 / 2024-06-08 |
| 143 | running_5k | 5011 | 1732 | 0.86 | 北京市 跑步 / 2024-06-17 |
| 146 | running_10k | 10097 | 3467 | 0.86 | 北京市 跑步 / 2024-06-23 |
| 150 | running_10k | 10026 | 3278 | 0.86 | 北京市 跑步 / 2024-06-29 |
| 167 | running_5k | 5111 | 1628 | 0.86 | 北京市 跑步 / 2022-06-28 |
| 168 | running_5k | 5048 | 1851 | 0.86 | 北京市 跑步 / 2022-06-23 |
| 169 | running_5k | 5066 | 1727 | 0.86 | 北京市 跑步 / 2022-06-15 |
| 230 | running_half_marathon | 21435 | 7768 | 0.86 | 2023成都半程马拉松 / 2023-10-29 |
| 236 | running_10k | 10095 | 4329 | 0.86 | 北京市 跑步 / 2026-06-13 |
| 239 | running_half_marathon | 21457 | 7642 | 0.86 | 都江堰半程马拉松 / 2023-03-26 |
| 242 | running_10k | 10290 | 4135 | 0.86 | 北京市 跑步 / 2026-06-20 |

共同原因：

- `distance_from_dist_km`
- `duration_from_total_timer_time`
- `duration_semantics_unknown`

解释：这些结果落在标准距离 ±3% 内，但当前计时语义只能确认来自 timer time，无法证明是完全 elapsed time，因此按冻结规则进入 candidate，而不是自动确认。

## 人工复核样本覆盖

| 复核类型 | 样本数 | 结论 |
|---|---:|---|
| 边界距离 | 2 | 需要人工看是否 GPS 漂移或路线误差导致接近 ±3% 边界 |
| 自动暂停 / 计时语义 | 13 候选均涉及 | 无专用 auto-pause 字段；需基于活动详情确认 timer/elapsed 语义 |
| GPS 漂移 | 2 个边界距离样本优先 | Records dry-run 不读取轨迹点；建议人工打开 Activity Detail 查看轨迹 |
| 跑步机 | 0 | 当前库未抽到 treadmill 样本 |
| 重复导入 | 12 | 已抽取疑似同日/同距离/同用时样本，需人工确认是否重复 |
| 删除纪录 | 0 | 当前抽样未发现 deleted activity 样本 |
| 同日多成绩 | 0 | 当前候选未出现同日同 record_key 多候选 |
| 跨时区样本 | 12 | 需要确认 event_date 使用是否符合本地比赛/训练日期预期 |

## Activity Detail 回跳与历史演进

- staging 当前 active PB 均保留 `activity_id`。
- `get_career_pb_history()` 对 3 个 active 类型均可返回历史记录。
- 本轮未做真实 UI 点击验证；RC-28/RC-29 打包验收阶段应在真实界面打开记录中心并点击 Activity Detail 回跳。

## 恢复方案

如果后续真实库 rebuild/apply 结果不符合预期：

1. 关闭应用，避免 SQLite 写入竞争。
2. 将当前真实库另存为事故现场副本。
3. 用本次备份覆盖源库：
   ```bash
   cp "docs/records_center_real_db_audit/user_profile_rc27_backup_20260714_004536.db" "/Users/fanglei/.fitvault/user_profile.db"
   ```
4. 重新启动应用，并运行 Records/PB 只读 API 检查 active PB 和候选数量。
5. 如只需回退 Resolver 结果而不回滚整库，可在备份库中导出 `career_pb_records`、`career_event_candidates`、`career_record_events` 三表后定向恢复；该操作需要单独脚本和人工确认。

## 人工复核结论

用户决策：先全部保持候选，不写入真实库。

执行结论：

- 不对真实库执行 `rebuild_records(dry_run=False)`。
- 不批量确认 13 条候选。
- 不批量拒绝 13 条候选。
- 真实库当前 active PB 保持不变。
- 后续如需发布真实数据，可在记录中心候选视图逐条确认/拒绝，或重新发起一次带人工授权的真实库 rebuild。

## 阻塞项

RC-27 人工复核已完成；本轮明确选择“不写真实库，全部保持候选”。

后续如要改变该结论，需要重新确认：

- 13 条 candidate 中哪些应确认，哪些应拒绝。
- 是否允许在真实库执行 `rebuild_records(dry_run=False)`。
- 对已有 active PB（尤其 activity 167、239 已同时出现在候选清单中）是否按候选流程保留人工确认，而不是自动覆盖。
