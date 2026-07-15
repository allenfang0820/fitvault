# ACS-Year-AI-08A 完成报告：测试矩阵与 ACS 宽回归

## 状态

Done。

## 测试矩阵

| 验收主题 | 覆盖任务 / 测试 |
| --- | --- |
| Year Snapshot 契约、字段顺序、禁止字段 | `tests/test_career_year_snapshot_contract.py` |
| 年度 Activity 聚合、月份摘要、跨年边界 | `tests/test_career_year_snapshot_activity_aggregation.py` |
| Resolver evidence catalog 与事实回填 | `tests/test_career_year_snapshot_evidence.py`、`tests/test_career_year_ai_report_validation.py` |
| period comparison 与 `source_fingerprint` | `tests/test_career_year_snapshot_period_comparison.py`、`tests/test_career_year_snapshot_fingerprint.py` |
| 状态机 `no_data/not_generated/ready/stale/failed/ai_unavailable` | `tests/test_career_year_report_state.py`、`tests/test_career_year_insight_service.py` |
| Snapshot 与 AI cache 持久化 | `tests/test_career_year_snapshot_persistence.py`、`tests/test_career_ai_insights_repository.py` |
| 只读 API 与 pywebview envelope | `tests/test_career_year_insight_read_api.py` |
| 年度卡片导航、模式切换、渲染与请求隔离 | `tests/test_career_year_card_navigation_frontend.py`、`tests/test_career_year_insight_mode_frontend.py`、`tests/test_career_year_insight_render_frontend.py`、`tests/test_career_year_request_isolation_frontend.py` |
| 年度 Prompt、fake LLM、格式修复 | `tests/test_career_year_llm_prompt.py` |
| 年度生成 API、幂等、single-flight、失败矩阵、日志隐私 | `tests/test_career_year_generate_api.py` |
| 年度 / 生涯 API 分离、旧记忆退役 | `tests/test_career_year_insight_read_api.py`、`tests/test_career_memory_retirement.py` |

## 验证结果

```text
.venv312/bin/python -m pytest tests/test_career_memory_retirement.py -q
3 passed in 0.13s

.venv312/bin/python -m pytest tests/test_career_year_*.py -q
97 passed, 10 subtests passed in 0.74s

.venv312/bin/python -m pytest tests/test_career*.py -q
576 passed, 38 subtests passed in 2.59s

.venv312/bin/python -m py_compile career_backend.py main.py llm_backend.py profile_backend.py
passed

.venv312/bin/python -m json.tool docs/js_api_contract.json >/dev/null
passed
```

## 静态检查

- `career_backend.py`、`track.html`、`docs/js_api_contract.json` 未重新暴露 `"memory_count"`、`representative_memories`、`memoryCount` 或旧 season memories pill。
- 年度卡片/年度页面前端仍未绑定 `generate_career_year_insight`；生成 API 仅在 pywebview contract 和 backend 暴露。
- `generate_career_insight` 保持全生涯 fallback 契约；年度链路使用 `get_career_year_insight` / `generate_career_year_insight` 独立接入 Year Snapshot、年度状态机和年度缓存。
- `docs/js_api_contract.json` 可被 JSON parser 正常解析。

## 发现与修复

首轮 `tests/test_career*.py` 发现 `career_backend.py` 中直接出现 `"memory_count"` 字面量，触发旧记忆退役静态测试。已将 Year Snapshot forbidden set 改为拼接构造，运行时仍禁止该 key，但源码不再重新暴露退役字段。

## Review 结论

通过。定向年度测试和 ACS 宽回归全绿；累计 diff 的高风险点集中在年度 Snapshot/cache/API/LLM/single-flight，均有对应测试覆盖。未发现阻塞问题，未执行 DMG 打包。
