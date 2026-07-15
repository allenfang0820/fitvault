# RCV2-28 工程级提示词：Route Signature 与同路线匹配 candidate-only

## 目标

实现越野跑个人路线 PR 的前置 Route Resolver：从 Activity 派生隐私安全 route signature，并判断两条路线是否为同路线、同方向，为后续 `trail_route_best_time` evidence 提供 candidate-only 依据。

## 范围

- 在 `career_backend.py` 中新增路线签名、路线匹配、派生表保存/读取 helper。
- 新增 `tests/test_career_record_trail_route_signature.py`，覆盖同向、反向、折返、低重合、部分覆盖、GPS 长缺口/跳点、配置化阈值与持久化隐私安全。
- 使用 `tests/fixtures/records_center_v2/golden_manifest.json` 中 `trail_route_same_reverse_low_overlap` 作为合约样例。
- 写完成报告并更新滚动摘要与任务清单。

## 约束

- Activity 仍是唯一事实源；route signature/match 只是派生缓存，不是正式纪录。
- 初始阈值必须配置化：起终点 100m、长度误差 5%、轨迹覆盖率 95%、走廊重合 85%。
- 必须处理反向、折返、部分重合、GPS 长缺口和跳点。
- 不保存 full track、GPS 点数组、真实经纬度、可还原 polyline、原始路径、设备/账号/体重等敏感信息。
- 不创建公开路线库或排行榜。
- 不自动确认 route PR；所有 route PR 结果必须 candidate-only。
- 不写真实库；测试只能使用内存库或临时库。
- 不打包。

## 预期实现契约

- `build_trail_route_signature(...)` 返回 `route_key`、`direction_key`、安全 `signature`、`quality`、`status`。
- `match_trail_route_signatures(...)` 返回 `direction`、`coverage_ratio`、`overlap_ratio`、`length_error_ratio`、`match_score`、`decision`、`reason_codes`。
- `save_career_route_signature(...)` 与 `save_career_route_match(...)` 只保存派生签名/匹配摘要。
- 同向同路线返回 `decision="candidate"`，理由包含 `real_data_sample_missing`。
- 反向返回 `decision="ignored"` 且包含 `route_direction_mismatch`。
- 低重合或低覆盖返回 `decision="ignored"` 且包含对应 reason。

## 验证命令

```bash
.venv312/bin/python -m pytest tests/test_career_record_trail_route_signature.py tests/test_career_record_trail_activity_total.py -q
.venv312/bin/python -m pytest tests/test_career_record_schema_migration.py tests/test_career_record_v2_rebuild.py tests/test_career_records_v2_api.py tests/test_career_pb_api.py -q
.venv312/bin/python -m py_compile career_backend.py
```

## 完成定义

- 同向、反向、低重合/部分覆盖样本得到可解释不同结果。
- 持久化 JSON 隐私安全测试通过。
- 任务清单标记 RCV2-28 Done，滚动摘要刷新到 RCV2-28。
