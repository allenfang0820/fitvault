# RC-26 自动化测试矩阵与宽回归报告

日期：2026-07-14

## 执行提示词摘要

目标：把记录中心从 Registry 到前端、跨模块、Snapshot/AI、安全性能和活动导入刷新链路的自动化测试整理成可交付矩阵，并运行最宽可行回归，确认 Milestone D 无未解释的相关失败。

边界：

- 以 Records Center / PB / ACS Career 相关测试为主。
- 活动导入回归选择与 ACS 派生刷新、Race 标记、FIT 导入相关的本地测试。
- 不把外部 Garmin/COROS 账号同步、真实网络或真机打包验收纳入 RC-26。

## 测试矩阵

| 覆盖域 | 代表测试 | 覆盖结论 |
|---|---|---|
| Registry、边界距离、比较规则 | `tests/test_career_record_registry.py`、`tests/test_career_pb_resolver.py` | 记录定义、±3% 标准距离、比较方向、legacy timer 兼容、置信度输入稳定 |
| Performance Summary 与计时事实 | `tests/test_career_pb_resolver.py` | `elapsed_time_sec`、`duration/duration_sec` legacy fallback 与 reason code 覆盖 |
| Schema / migration / active 唯一 | `tests/test_career_record_schema_migration.py`、`tests/test_career_backend_schema.py` | schema 可迁移；默认 DB path 缓存不跨 profile DB 误用；active scope 唯一索引稳定 |
| 状态迁移、历史链、候选、删除回退、幂等 | `tests/test_career_record_state_migration.py`、`tests/test_career_record_lifecycle.py`、`tests/test_career_record_rebuild.py` | active/superseded/invalidated/rejected、fallback、dry-run/apply、并发保护和幂等事件覆盖 |
| 增量评估与活动导入刷新 | `tests/test_career_record_incremental_evaluation.py`、`tests/test_career_activity_change_refresh.py`、`tests/test_fit_sync.py` | 单 Activity 增量评估、导入后跳过 legacy PB 全量刷新并走增量 Records 契约 |
| API envelope / 筛选 / 错误码 / 安全边界 | `tests/test_career_record_maintenance_api.py`、`tests/test_career_pb_api.py`、`tests/test_career_phase9_pywebview_envelope.py`、`tests/test_career_phase9_data_boundary_audit.py` | main API 统一 envelope、高风险接口标记、事件 payload 递归清洗、禁止字段边界覆盖 |
| 前端当前/详情/演进/候选/状态/响应式/A11y | `tests/test_career_archives_frontend_render.py`、`tests/test_career_phase8_frontend_readiness.py` | “记录中心”页面、当前纪录、演进、候选确认/拒绝、aria-live、移动端状态覆盖 |
| Overview / Timeline / Race / Achievement 联动 | `tests/test_career_overview_pb_summary.py`、`tests/test_career_overview_api_closure.py`、`tests/test_career_timeline_pb_nodes.py`、`tests/test_career_timeline_engine_closure.py` | 候选不进正式 Overview/Timeline，PB badge 聚合，Timeline 不返回 PB 独立节点，Race/Achievement 不越权计算 PB |
| Snapshot / AI / Trends 边界 | `tests/test_career_snapshot_builder.py`、`tests/test_career_snapshot_persistence.py`、`tests/test_career_insight_api_skeleton.py` | `records_summary` 白名单、候选只计数、AI fallback 不调用 LLM、不重算 PB、trend_inputs 仅 frequency_only |
| 性能、日志、可观测性 | `tests/test_career_record_rebuild.py` | 10,000 条合成 Activity dry-run 性能门、metrics、reason_counts、安全结构化日志 |
| JSON contract / Python 编译 | `docs/js_api_contract.json`、`career_backend.py`、`main.py` | JSON 可解析；核心后端入口可编译 |

## 本轮补齐/修正

- `tests/test_career_timeline_engine_closure.py`
  - 将旧测试中同一 active PB scope 的重复插入改为不同 PB 类型，符合 `ux_career_pb_records_active_scope`。
- `tests/test_fit_sync.py`
  - 单 FIT 导入后的 Career refresh 断言更新为 `refresh_career_derived_events(include_pb=False)`，符合增量 Records 契约。
- `career_backend.ensure_career_schema()`
  - schema ready cache 增加默认 DB path 维度，避免测试或运行时切换 `profile_backend.DB_PATH` 后跳过新库初始化。

## 验证结果

全部 Career 测试：

```bash
.venv312/bin/python -m pytest tests/test_career_*.py -q
```

结果：`468 passed, 24 subtests passed`

活动导入/刷新相关回归：

```bash
.venv312/bin/python -m pytest \
  tests/test_career_activity_change_refresh.py \
  tests/test_activity_race_flag_api.py \
  tests/test_fit_sport_event_race.py \
  tests/test_fit_sync.py \
  tests/test_import.py \
  tests/test_startup_import_contract.py \
  tests/test_track_html_sync_logic.py \
  -q
```

结果：`168 passed`

静态检查：

```bash
.venv312/bin/python -m py_compile career_backend.py main.py
.venv312/bin/python -m json.tool docs/js_api_contract.json >/dev/null
```

结果：通过。

## 已知残余风险

- 本任务未运行外部账号同步、网络下载、macOS/Windows 打包与真机验收；这些属于 RC-27 至 RC-30。
- 当前工作区存在大量本轮外的未提交改动，RC-26 只解释并修正与 Records/Career 回归相关的失败。
- 10k 性能测试使用合成/脱敏数据，不替代 RC-27 的真实库 dry-run 与人工复核。

## 结论

Milestone D 自动化测试矩阵已建立。Records Center 相关宽回归无未解释失败。

