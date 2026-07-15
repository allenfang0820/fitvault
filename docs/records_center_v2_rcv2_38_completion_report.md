# RCV2-38 完成报告：安全、性能、日志与可观测性闭环

## 结论

RCV2-38 已完成。Records Center V2 现在具备安全/性能/日志/可观测性的诊断闭环：查询路径返回可复验 metrics，高风险候选决策和 rebuild 输出白名单观测摘要，rebuild 继续默认 dry-run，真实 apply 仍由 main.py 的 `apply_to_real_db` 显式门禁阻断。

## 主要变更

- `career_backend.py`
  - 新增 `RECORDS_V2_PERFORMANCE_TARGETS_MS`，覆盖 records list、history、curve、candidate、route comparison、rebuild plan。
  - 新增 `records_v2_observability_contract()`，冻结性能目标、高风险操作和日志白名单/黑名单。
  - 新增 `records_v2_safe_observation()`，只输出白名单字段，自动丢弃 payload/evidence/path/schema/raw/route signature 等敏感字段。
  - `get_career_records()`、`get_career_record_history()`、`get_career_record_candidates()` 增加 `metrics.performance_target_ms`。
  - `get_career_record_curve()` 增加 `cache_hit/cache_miss/performance_target_ms`，保持既有安全曲线 ViewModel。
  - `get_trail_route_comparison_viewmodel()` 增加 route candidate 计数、cache hit/miss 和性能目标。
  - `rebuild_career_records_v2()` / plan 增加 cache/route 安全计数、`observability` 白名单摘要和 `failure_recovery` savepoint/batch/cancel 说明。
  - `decide_career_record_v2_candidate()` 返回安全 `metrics` 与 `observability`，confirm/reject 仍不接受用户提交成绩、距离、scope、range 或 reason。
- `main.py`
  - `decide_career_record_candidate()` 和 `rebuild_career_records()` 增加安全日志，只记录白名单观测字段。
  - `rebuild_career_records(dry_run=false)` 继续要求 `apply_to_real_db=true`，否则在进入后端写路径前拒绝。
- `docs/js_api_contract.json`
  - 更新 `rebuild_career_records` 返回契约，加入 metrics、observability 与 failure_recovery。
- `tests/test_career_records_v2_security_perf_observability.py`
  - 新增安全、性能、日志与可观测性闭环测试。

## 安全边界

- API/log/observability 不返回 raw FIT、raw streams、power stream、track_json、file_path、storage_ref、SQLite schema、设备标识、体重详情、candidate evidence、record_decision 或 route signature。
- Route 观测字段使用抽象 `route_cache_count` 和 `route_candidates`，不输出 route signature 本体或可还原路线内容。
- Curve API 保留 RCV2-14 约定的安全降采样曲线 ViewModel；RCV2-38 只补 cache hit/miss 与性能诊断，不回扫 Activity raw points。
- 未执行真实库 apply；未打包。

## 验证

```bash
.venv312/bin/python -m pytest tests/test_career_records_v2_security_perf_observability.py tests/test_career_records_v2_api.py tests/test_career_record_v2_rebuild.py -q
# 17 passed

.venv312/bin/python -m pytest tests/test_career_records_v2_snapshot_ai_trends.py tests/test_career_records_v2_downstream_integration.py -q
# 8 passed

.venv312/bin/python -m pytest tests/test_career_records_v2_security_perf_observability.py tests/test_career_records_v2_api.py tests/test_career_record_v2_rebuild.py tests/test_career_records_v2_snapshot_ai_trends.py tests/test_career_records_v2_downstream_integration.py -q
# 25 passed

.venv312/bin/python -m py_compile career_backend.py main.py
# passed

.venv312/bin/python - <<'PY'
import json
from pathlib import Path
json.loads(Path('docs/js_api_contract.json').read_text(encoding='utf-8'))
print('js_api_contract_json_ok')
PY
# js_api_contract_json_ok
```

## 自适应复核

- 本任务实际触碰范围符合 RCV2-38：安全/性能/日志/observability helper、rebuild/curve/route/candidate metrics、main.py 高风险入口安全日志、JS API contract 和定向测试。
- 没有新增真实库写授权；`dry_run=false` 仍被 main.py 门禁保护。
- 没有把 raw evidence、curve payload、route signature、path 或 schema 写入观测输出。
- 工作区仍有大量前序未提交改动，本轮未整理、回退或覆盖无关文件。

## 后续任务入口

进入 `RCV2-39 V2 自动化测试矩阵与全量回归`。重点运行并修复 V2 全测试矩阵，证明多运动扩展未破坏 V1 和相邻功能。
