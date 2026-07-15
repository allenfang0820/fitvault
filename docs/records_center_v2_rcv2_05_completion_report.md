# RCV2-05 完成报告：Schema、Curve Cache、Route 数据与回滚冻结

完成时间：2026-07-14

## 任务目标

冻结 Records Center V2 的数据结构、唯一性、Curve Cache、Route Signature、migration dry-run 和失败回滚方案，并确保不创建与 `career_pb_records` 重叠的正式纪录事实表。

## 交付物

- `docs/records_center_v2_rcv2_05_execution_prompt.md`
- `docs/records_center_v2_rcv2_05_schema_cache_route_contract.md`
- `docs/records_center_v2_rcv2_05_completion_report.md`
- `docs/records_center_v2_rolling_contract_summary.md`
- `docs/运动生涯记录中心V2（多运动纪录）开发任务清单.md`

## 冻结结论

- 继续复用 `career_pb_records` 作为唯一正式纪录事实表，不新建 `records`、`personal_records` 等同义表。
- 继续复用 `career_record_events` append-only 事件表和 `career_event_candidates` 候选容器。
- V2 在 `career_pb_records` 上新增结构化字段：`record_key`、`record_family`、`scope_json`、`scope_key`、`scope_hash`、`range_json`、`quality_json`、`metric_value_num`、`metric_name`、`catalog_state`、`rule_version`。
- 冻结 scope canonicalization：白名单 scope JSON 排序序列化后生成 `scope:v2:sha256:*`；动态纪录身份为 `record_key + "::" + scope_hash`。
- 冻结 V2 active 唯一键：`record_key/source_mode/scope_hash WHERE status='active'`，迁移期保留 V1 active scope 索引。
- 冻结 Curve Cache 表 `career_record_curve_cache`，明确它是派生缓存，不是 canonical record。
- 冻结 Route Signature/Route Match 派生表，禁止保存完整轨迹、真实 GPS 点或可还原路线的高精度 polyline。
- 冻结 migration 顺序、`dry_run=True` 不写库、冲突停止、失败回滚和真实库安全策略。

## 验证结果

```bash
.venv312/bin/python - <<'PY'
# 检查现有表复用、V2 scope/unique/cache/route/dry-run/rollback/安全边界术语
PY
```

结果：`schema_contract_check_ok`

```bash
.venv312/bin/python -m pytest tests/test_records_center_v2_golden_fixtures.py -q
```

结果：`4 passed in 0.02s`

## Diff 复核

- 本任务只新增/更新 RCV2 文档、滚动摘要和任务状态。
- 未修改业务代码、schema migration、API contract、前端、真实库或打包产物。
- Contract 明确 `RCV2-40` 前不得对真实库 apply V2 migration。
- Curve/Route 数据被定义为派生缓存，不会替代 Activity 或正式纪录事实。

## 下一任务

`RCV2-06 通用 Records API、Catalog 与 ViewModel 冻结`。

下一任务应在 Registry、质量和 schema 契约基础上冻结通用 API、Catalog、Records、Detail、History、Curve、Candidate ViewModel 与 V1 PB API 兼容包装关系。
