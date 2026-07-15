# RCV2-29 工程级提示词：越野赛段 PR 与 Scope 状态闭环

## 目标

把 RCV2-28 的 route signature/match 和越野 segment 输入转成安全 `RecordEvidence`，覆盖 `trail_route_best_time`、`trail_segment_best_time`、`trail_climb_segment_best_time` 三类个人 PR，并接入现有 Scope 感知状态机。

## 范围

- 在 `career_backend.py` 中新增 Trail Route/Segment Record Resolver。
- 只使用 elapsed time，暂停计入成绩；不使用 moving time。
- route total 必须携带 `scope.route_key`；segment/climb segment 必须携带 `scope.segment_key` 与 Activity 内 range。
- 同一批 resolver 输出中，同 Scope 只保留 elapsed time 最小的 evidence。
- 新增状态与契约测试。
- 写完成报告，更新任务清单与滚动摘要。

## 约束

- Activity 是唯一事实源；resolver 不读取 raw FIT 文件。
- route/segment PR 在真实越野样本验收前保持 candidate-only，不自动激活正式纪录。
- 不实现公开 CR/KOM/QOM，不创建公开路线库或排行榜。
- 不使用 moving time、GAP 或分析曲线作为正式 PR。
- 不保存完整轨迹、GPS 点、polyline、路径、设备/账号/体重等敏感字段。
- 不写真实库；测试使用内存 SQLite。
- 不打包。

## 预期实现契约

- `build_trail_route_record_evidences(...)`：
  - 输入 Activity、route signature、route match。
  - 仅 `decision="candidate"` 且方向 `same/loop` 的 match 产生 route_total evidence。
- `build_trail_segment_record_evidences(...)`：
  - 输入 Activity 与 segment candidates。
  - 普通 segment 生成 `trail_segment_best_time`；climb segment 生成 `trail_climb_segment_best_time`。
- `apply_trail_route_segment_records(..., dry_run=True)`：
  - 默认只返回 planned evidences。
  - `dry_run=False` 时只调用现有 `apply_record_evidence_state()`，由于 registry 是 candidate_only，因此只进入候选，不写 active record。

## 验证命令

```bash
.venv312/bin/python -m pytest tests/test_career_record_trail_route_segment_resolver.py tests/test_career_record_trail_route_signature.py tests/test_career_record_v2_state.py -q
.venv312/bin/python -m pytest tests/test_career_record_v2_rebuild.py tests/test_career_records_v2_api.py tests/test_career_record_evidence.py tests/test_career_pb_api.py -q
.venv312/bin/python -m py_compile career_backend.py
```

## 完成定义

- route total、segment、climb segment 三类 evidence 可生成且安全。
- 相同 Scope 批内只保留最快 elapsed evidence。
- 方向不同的 route match 不产生 route PR evidence。
- apply 后保持 candidate-only，不自动写 active。
- 既有状态机、API、PB 兼容测试通过。
