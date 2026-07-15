# RCV2-38 工程级执行提示词：安全、性能、日志与可观测性闭环

## 任务目标

验证 Records Center V2 的列表、history、curve、candidate、rebuild、route 和 UI 相关路径具备安全、性能、日志与可观测性闭环：失败可诊断，但不泄露敏感数据；记录中心故障不得阻塞 Activity 主功能。

## 输入摘要

- 当前任务：`RCV2-38 安全、性能、日志与可观测性闭环`。
- 已完成前置：`RCV2-13` rebuild/删除回退，`RCV2-14` Records API，`RCV2-37` Snapshot/AI/Trends 安全摘要。
- 当前 API 多数已返回 `metrics.elapsed_ms` 和 `returned_count`；rebuild plan 已有 `by_sport/by_family/by_reason` 和 `metrics`。
- 当前 rebuild 默认 `dry_run=true`，main.py contract 已声明真实 apply 需要 `apply_to_real_db` 门禁。

## 冻结契约

- 不写真实库、不打包。
- 高风险 confirm/reject/apply 必须有输入边界、幂等或门禁。
- API/log/docs/UI 不得泄露 raw FIT、raw streams、points、track、route signature、path、schema、设备标识、体重详情、candidate evidence。
- Curve/Route 只可命中派生缓存或安全摘要，不允许列表路径扫描 raw points。
- 输出必须包含足够诊断信息：by sport/family/reason、cache hit/miss、route candidates、elapsed metrics。

## 文件范围

- `career_backend.py`
- `main.py`
- `docs/js_api_contract.json`
- 新增 `tests/test_career_records_v2_security_perf_observability.py`
- 新增 `docs/records_center_v2_rcv2_38_completion_report.md`
- 更新任务清单与滚动摘要

## 非目标

- 不重写 sport resolver。
- 不新增真实 DB apply 或全量真实数据 dry-run。
- 不调整前端视觉。
- 不执行打包、签名、公证或发布包替换。

## 实施步骤

1. 增加 Records V2 观测契约常量：性能目标、敏感字段黑名单、高风险操作日志白名单。
2. 增加安全日志/指标 helper，用于输出不含 payload/evidence/path/schema 的 run/candidate/rebuild 观测摘要。
3. 为 rebuild plan/apply 增加 cache/route 观测摘要、failure recovery 说明和安全 metrics。
4. 确认 `rebuild_career_records()` 默认 dry-run；如请求 `dry_run=false` 但没有 `apply_to_real_db=true`，main.py bridge 必须拒绝。
5. 为 Records API 查询、curve cache、route candidate、candidate decision 和 rebuild 增加安全/性能/可观测性测试。
6. 更新 JS API contract 的 rebuild/observability 描述。

## 验证命令

```bash
.venv312/bin/python -m pytest tests/test_career_records_v2_security_perf_observability.py tests/test_career_records_v2_api.py tests/test_career_record_v2_rebuild.py -q
.venv312/bin/python -m pytest tests/test_career_records_v2_snapshot_ai_trends.py tests/test_career_records_v2_downstream_integration.py -q
.venv312/bin/python -m py_compile career_backend.py main.py
```

## 差异复核

- 确认新增观测输出只含白名单字段。
- 确认安全测试覆盖 raw/points/track/path/schema/evidence 泄露。
- 确认 rebuild dry-run/apply 门禁不扩大真实写权限。
- 确认性能指标为诊断性守卫，不引入 flakey 绝对耗时断言。

## 完成定义

- 定向测试和 py_compile 通过。
- 完成报告写入。
- 任务清单标记 `RCV2-38 Done`、`RCV2-39 In Progress`。
- 滚动摘要刷新到 RCV2-39。
