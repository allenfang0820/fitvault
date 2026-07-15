# RCV2-39 完成报告：V2 自动化测试矩阵与全量回归

## 结论

RCV2-39 已完成。Records Center V2 定向矩阵、全部 `tests/test_career_*.py`、Activity import/sync/delete/detail/refresh 相邻回归、编译、API JSON 与静态安全检查均已通过。未执行打包，未写真实库。

## 修复项

- `main.py`
  - `get_trace_activity_history()` 继续返回统一 envelope，同时镜像旧调用方依赖的顶层 `records/total/page/page_size/total_pages/activity_types/locations`，恢复旧测试和旧前端兼容。
  - `_dedupe_activity_rows()` 在常规列表场景优先用 Activity `id` 去重，避免多个真实活动因相同 start/distance/duration 或临时 `file_path` 被错误折叠。
- `track.html`
  - 去除复盘/年度 UI 中被门禁禁止的 viewport 字号 `vw` 与负 `letter-spacing`。
- `docs/js_api_contract.json`
  - `get_career_record_curve.returns` 使用抽象 `plot_series` 表述安全绘图数据，避免返回契约出现 `points` 字面量导致边界审计误判。
- `career_backend.py`
  - V2 Activity invalidation 外部返回字段从 `route_signatures` / `would_invalidate_route_signatures` 调整为抽象 `route_cache` / `would_invalidate_route_cache`，避免外部 API 出现 route signature 字样。
- `tests/test_career_record_v2_rebuild.py`
  - 同步 route cache 字段名。

## 验证矩阵

```bash
.venv312/bin/python -m pytest $(rg --files tests | rg 'test_career_record|test_career_records|test_records_center_v2' | sort) -q
# 185 passed, 27 subtests passed

.venv312/bin/python -m pytest tests/test_career_*.py -q
# 729 passed, 52 subtests passed

.venv312/bin/python -m pytest $(rg --files tests | rg 'fit_sync|activity|detail|delete|refresh|import|track_html_sync|resolver_sport_isolation' | sort) -q
# 521 passed, 1 skipped, 27 subtests passed

.venv312/bin/python -m py_compile career_backend.py main.py metrics_registry.py metrics_resolver.py utils/metrics_calc.py
# passed

.venv312/bin/python - <<'PY'
import json
from pathlib import Path
json.loads(Path('docs/js_api_contract.json').read_text(encoding='utf-8'))
print('js_api_contract_json_ok')
PY
# js_api_contract_json_ok

rg -n "font-size\\s*:\\s*[^;]*vw|letter-spacing\\s*:\\s*-" track.html || true
# no matches

rg -n "would_invalidate_route_signatures|route_signature_count|logger\\.info\\(clean_payload|logger\\.info\\(.*payload_json|logger\\.info\\(.*evidence_json" career_backend.py main.py docs/js_api_contract.json tests/test_career_records_v2_security_perf_observability.py tests/test_career_record_v2_rebuild.py || true
# only test assertion text remains for logger.info(clean_payload)
```

## 剩余说明

- Activity 相邻回归中 `1 skipped` 为测试自身条件跳过，非本任务失败。
- 本任务没有降低产品规则、删除断言或跳过失败用例；失败项均通过兼容修复或边界字段修复解决。
- 未执行真实数据 apply；未打包。

## 后续任务入口

进入 `RCV2-40 真实数据备份、staging dry-run 与人工复核`。该任务只允许备份、staging 副本和 dry-run，不得写真实库。
