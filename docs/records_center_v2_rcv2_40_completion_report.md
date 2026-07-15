# RCV2-40 完成报告：真实数据备份、staging dry-run 与人工复核

## 结论

RCV2-40 已完成。已对真实库执行只读审计，生成 backup 与 staging 副本，并仅在 staging 副本上执行 schema ensure 与 Records V2 rebuild dry-run。真实库前后 hash、mtime 和关键计数均未变化；未对真实库 apply，未确认或拒绝任何候选，未打包。

## 产物

- 脱敏 dry-run 摘要：`docs/records_center_v2_real_data/rcv2_40/rcv2_40_staging_dry_run_summary.json`
- 备份副本：`docs/records_center_v2_real_data/rcv2_40/user_profile_rcv2_40_backup.db`
- staging 副本：`docs/records_center_v2_real_data/rcv2_40/user_profile_rcv2_40_staging.db`

## 源库未变化证明

- 源库前后 SHA-256：一致。
- 源库前后 mtime_ns：一致。
- 源库前后关键表计数：一致。
- backup 初始 hash 与源库一致：是。
- staging 初始 hash 与源库一致：是。

## 源库关键计数

- `activities`：981
- `career_pb_records`：3，其中 active 3
- `career_record_events`：0
- `career_event_candidates`：129，其中 candidate 125
- `career_record_curve_cache`：0
- `career_route_cache`：0
- `career_route_matches`：0
- `career_snapshots`：0
- `career_ai_insights`：14

候选类型补充：

- `race / candidate`：125
- `race / resolved`：4
- V2 `pb_record` candidate：0

## 真实样本复核

- 骑行：368 条；其中 66 条具备功率摘要字段。
- 徒步：33 条；33 条具备海拔/爬升摘要字段。
- 公开水域游泳：7 条。
- 泳池游泳：0 条；pool length 可验证样本 0。
- 越野跑：0 条。

## staging dry-run 摘要

- staging schema：`2026-07-14.records-v2.10`，schema ensure 成功。
- rebuild dry-run：成功。
- processed：981
- dispatch planned：854
- ignored：127
- by_sport 主要项：
  - running：453
  - cycling：368
  - walking：82
  - hiking：33
  - swimming：7
  - mountaineering：11
  - e_biking：10
- by_family：
  - distance_time_pb：1812
  - power_duration_pb：2208
  - activity_total_record：1236
- by_reason：
  - definitions_planned：854
  - no_available_definitions：127
- cache/route：curve cache 0，route cache 0，route match 0，route candidates 0。

说明：staging rebuild plan 耗时约 1897 ms，高于 RCV2-38 的小样本诊断目标 1000 ms。该结果来自 981 条真实活动的 staging dry-run，不阻塞 RCV2-40，但应在后续性能优化或真实 apply 前继续观察。

## Catalog 与用户决策建议

基于当前真实样本和既有冻结规则，建议进入 RCV2-41 时采用：

- 跑步：保持 V1 已有正式纪录兼容。
- 骑行：真实样本足够支撑继续展示骑行 Catalog；功率纪录仍必须按功率流质量、断点和候选规则判定；未授权前不写真实库。
- 徒步：真实样本足够支撑徒步 Catalog；最大连续爬升等质量敏感项继续 candidate-only/人工复核。
- 公开水域游泳：有样本，但 V2 仍保持 candidate-only，需人工复核 GPS/计时质量。
- 泳池游泳：无真实泳池和 pool length 样本，保持 validation-required。
- 越野跑：无真实样本，整次/路线/赛段继续 candidate-only，Pace/GAP 仅 analysis-only。
- 所有新 V2 真实数据结果：按用户既有要求先保持候选，不写真实库。

## 验证命令

```bash
.venv312/bin/python -m py_compile career_backend.py main.py
# passed

# RCV2-40 read-only source audit + staging dry-run script
# source_unchanged: hash=true, mtime_ns=true, counts=true
# copy_verification: backup=true, staging=true
```

## 安全复核

- dry-run 摘要已脱敏，不包含本地绝对路径、raw FIT、raw streams、功率流、轨迹、candidate evidence、record_decision 或 route signature。
- staging 副本允许 schema ensure；真实库未执行 schema apply/rebuild apply。
- 未执行打包。

## 后续任务入口

进入 `RCV2-41 用户数据决策与 Catalog 可用性最终冻结`。依据用户已给出的“全部保持候选，不写入真实库”原则，下一步应记录 no-apply 决策并冻结 Catalog 可用性状态。
