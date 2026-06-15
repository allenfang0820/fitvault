# P3 启动链路可观测性与剩余冷启动项复测完成报告

## 1. 复测结论

本轮按 `docs/p3_startup_observability_and_residual_cold_start_prompt.md` 执行，优先做子进程冷启动测量与导入链路复核。

当前 `import main` 不再加载 `numpy`、`scipy`、`scipy.signal`、`pandas` 或 `webview`。外部报告中提到的 `pandas` 次要冷启动风险，在当前代码形态下未复现；`pandas` 仅位于 `llm_backend.points_to_dataframe_csv()` 的函数内部，启动导入不会触发。

本轮未修改生产业务逻辑。

## 2. pandas / numpy / scipy 导入状态

实测命令：

```bash
python3 scripts/measure_startup_imports.py
```

代表性输出：

```json
{"elapsed_sec": 0.233953, "loaded": {"fitparse": true, "garmin_fit_sdk": true, "numpy": false, "pandas": false, "scipy": false, "scipy.signal": false, "webview": false}}
```

结论：

- `numpy`: 未进入 `import main` 冷启动路径。
- `scipy`: 未进入 `import main` 冷启动路径。
- `scipy.signal`: 未进入 `import main` 冷启动路径。
- `pandas`: 未进入 `import main` 冷启动路径。
- `webview`: 顶层未导入，只有实际启动桌面入口时才需要。
- `fitparse` / `garmin_fit_sdk`: P3 时仍在 `main.py` 顶层链路中加载；后续 P4 已单独评估并后移到 FIT 解析调用点。

## 3. 代码改动清单

新增只读测量脚本：

- `scripts/measure_startup_imports.py`

新增防回归测试：

- `tests/test_startup_import_contract.py`

未改动：

- `main.py`
- `llm_backend.py`
- `gap_calculator.py`
- `metrics_resolver.py`
- `profile_backend.py`
- `track.html`

## 4. 测试结果

本轮新增测试用于固化：

- 子进程 `import main` 成功；
- `numpy/scipy/scipy.signal/pandas` 不回到冷启动路径；
- 测量脚本输出稳定 JSON。

已执行：

```bash
python3 scripts/measure_startup_imports.py
python3 -m pytest tests/test_startup_import_contract.py
python3 -m pytest tests/test_gap_calculator_lazy_import.py tests/test_detail_api_columns.py
python3 -m pytest test_fit_sync.py -k 'activity_list_schedules_metric_backfill_without_immediate_worker or activity_list or shadow_diff_json_persists_updates_and_detail_returns'
python3 -m pytest test_watchdog_bridge.py -k 'notify_frontend_ready_only_schedules_background_tasks or new_track_notification_is_queued'
python3 -m pytest tests/test_sport_hub_pagination.py -k 'StartupBackgroundDeferral'
PYTHONPYCACHEPREFIX=/private/tmp/aitrack_pycache python3 -m py_compile main.py profile_backend.py gap_calculator.py scripts/measure_startup_imports.py
```

结果均通过。

## 5. 是否需要更新后续任务清单

需要轻微更新：原先基于外部报告的 `pandas` 优化项应降级为“已复测，无需改动”。下一步不建议继续围绕 pandas 做生产代码改造。

## 6. 下一任务建议

后续 P4 已完成：

- `fitparse`、`garmin_fit_sdk` 已移出 `import main` 冷路径；
- `watchdog.observers.Observer` 已后移到文件监听启动点；
- `FileSystemEventHandler` 因当前类继承结构保留顶层导入，避免为小收益引入结构风险。
