# P5 启动端到端时间线可观测性完成报告

## 1. 任务目标

按 P4 后续建议，建立真实启动阶段的端到端时间线，覆盖：

- Python 进程进入 `main()`
- API 对象创建
- pywebview window 创建
- watchdog 启动
- 前端 DOMContentLoaded
- `bootstrapApplication()` 开始
- `check_first_run_status`
- `get_llm_config`
- loading 隐藏
- startup route 恢复
- 首次活动列表 API 往返
- 活动列表渲染完成
- `notify_frontend_ready`
- P2 后移任务触发前的前端 ready 时刻

本轮只做可观测性，不改变启动流程、不写数据库、不启动新的后台任务。

## 2. 后端改动

`main.py` 新增内存时间线：

- `_PROCESS_START_PERF`
- `_STARTUP_TIMELINE`
- `_record_startup_event(name, **fields)`
- `_startup_timeline_snapshot()`
- `Api.get_startup_timeline()`

活动列表 API 增加只读诊断字段：

```json
"startup_trace": {
  "api_elapsed_ms": 0,
  "process_elapsed_ms": 0
}
```

该字段只用于性能诊断，不改变活动列表记录、分页、筛选、回填调度语义。

## 3. 前端改动

`track.html` 新增：

- `window.__STARTUP_TRACE__`
- `markStartupPhase(name, extra)`
- `reportStartupTimeline(reason)`

关键节点会打印到浏览器控制台：

```text
[STARTUP] {...}
[STARTUP_TIMELINE] { frontend: [...], backend: {...} }
```

活动列表加载会记录：

- `activity_list_load_start`
- `activity_list_api_done`
- `activity_list_load_error`
- `activity_list_render_done`

其中 `activity_list_api_done` 会同时包含前端 roundtrip 和后端 `startup_trace.api_elapsed_ms`。

## 4. 如何查看

启动桌面端后，打开开发者控制台，查看：

```text
[STARTUP_TIMELINE]
```

也可以从前端调用：

```javascript
reportStartupTimeline('manual')
```

或从 pywebview API 调用：

```javascript
pywebview.api.get_startup_timeline()
```

## 5. 验证结果

已执行：

```bash
python3 -m pytest tests/test_startup_timeline_contract.py tests/test_sport_hub_pagination.py -k 'StartupTimelineInstrumentation or StartupBackgroundDeferral or StartupTimelineContract'
python3 -m pytest test_fit_sync.py -k 'activity_list_schedules_metric_backfill_without_immediate_worker or activity_list or shadow_diff_json_persists_updates_and_detail_returns'
python3 -m pytest test_watchdog_bridge.py -k 'notify_frontend_ready_only_schedules_background_tasks or new_track_notification_is_queued'
python3 -m pytest test_fit_parser.py tests/test_laps_real_data.py
python3 -m pytest tests/test_startup_import_contract.py tests/test_gap_calculator_lazy_import.py tests/test_detail_api_columns.py
PYTHONPYCACHEPREFIX=/private/tmp/aitrack_pycache python3 -m py_compile main.py fit_engine.py metrics_resolver.py profile_backend.py gap_calculator.py scripts/measure_startup_imports.py
python3 scripts/measure_startup_imports.py
```

结果均通过。

说明：曾误把 `track.html` 放入 `py_compile`，该命令失败是因为 HTML 不是 Python 文件，不代表前端语法检查失败；前端本轮通过静态契约测试覆盖。

## 6. 下一步建议

用真实桌面端启动一次，采集 `[STARTUP_TIMELINE]` 输出后，再判断是否需要继续优化：

- 如果 `check_first_run_status` 或 `get_llm_config` 慢，优化配置读取路径。
- 如果首次活动列表 API 慢，继续看 SQL / DB I/O。
- 如果 `restoreStartupRoute` 后首屏渲染慢，再拆前端初始化任务。
- 如果 P2 后移任务仍挤压首屏，继续调整延迟或触发条件。

