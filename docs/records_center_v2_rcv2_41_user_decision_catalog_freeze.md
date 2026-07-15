# RCV2-41 用户决策与 Catalog 可用性冻结记录

## 用户决策

记录时间：2026-07-15

用户已明确要求：

> 先全部保持候选，不写入真实库。

据此，本轮 RCV2-41 决策冻结为：

- 不对真实库执行 Records V2 apply。
- 不确认或拒绝任何真实候选。
- 新 V2 真实数据结果保持候选、validation-required 或 analysis-only 状态。
- 后续如需真实写入，必须在已有备份/回滚方案基础上获得新的明确授权。

## RCV2-40 真实数据依据

- 源库未变化：hash、mtime_ns、关键计数前后一致。
- staging dry-run：processed 981，dispatch planned 854，ignored 127。
- 真实样本：
  - 骑行：368 条，其中 66 条具备功率摘要。
  - 徒步：33 条，33 条具备海拔/爬升摘要。
  - 公开水域游泳：7 条。
  - 泳池游泳：0 条。
  - 越野跑：0 条。
- 源库已有候选均为 race candidate/resolved；V2 `pb_record` candidate 为 0。

## Catalog 最终冻结状态

| Sport | 当前 Catalog 状态 | RCV2-41 冻结结论 | 理由 |
| --- | --- | --- | --- |
| running | available 4 | 保持 available | V1 跑步 PB 兼容基线已通过全量回归 |
| cycling | available 9, validation_required 1 | 保持现状；真实写入需后续授权 | 有真实骑行样本，功率/W/kg 等仍受质量和体重门禁约束 |
| hiking | available 4, candidate_only 1 | 保持现状；连续爬升候选复核 | 有真实徒步样本，海拔/连续爬升仍需质量门禁 |
| pool_swimming | validation_required 6 | 保持 validation_required | 无真实泳池样本，且无可验证 pool length 样本 |
| open_water_swimming | candidate_only 8 | 保持 candidate_only | 有公开水域样本，但 GPS/计时质量需人工复核 |
| trail_running | candidate_only 8 | 保持 candidate_only / analysis-only | 无真实越野样本，路线/赛段/曲线不得标 Verified |

## 不写真实库声明

本任务未执行：

- `rebuild_career_records(dry_run=false)`
- `decide_career_record_candidate(confirm/reject)` 真实候选操作
- 真实库 schema apply
- 任何打包、签名、公证或发布包替换

## 后续条件

进入 RCV2-42/43 平台验收前，Catalog 展示可按当前状态运行；进入真实写入前，必须另行获得用户明确授权，并重新核对 backup/staging/hash/rollback。
