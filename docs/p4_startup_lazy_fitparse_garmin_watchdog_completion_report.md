# P4 启动链路 fitparse / garmin_fit_sdk / watchdog 延迟导入评估完成报告

## 1. 复测结论

P4 已完成。结论是：`fitparse` 与 `garmin_fit_sdk` 适合从 `import main` 冷启动路径后移到实际 FIT 解析调用点；`watchdog.observers.Observer` 可以安全后移到文件监听启动点；`watchdog.events.FileSystemEventHandler` 因 `FITFolderHandler` 当前直接继承它，本轮保持顶层导入，避免为小收益改动继承结构。

P4 前代表性输出：

```json
{"elapsed_sec": 0.173019, "loaded": {"fitparse": true, "garmin_fit_sdk": true, "numpy": false, "pandas": false, "scipy": false, "scipy.signal": false, "webview": false}}
```

P4 后代表性输出：

```json
{"elapsed_sec": 0.224965, "loaded": {"fitparse": false, "garmin_fit_sdk": false, "numpy": false, "pandas": false, "scipy": false, "scipy.signal": false, "webview": false}}
```

单次耗时会受 Python 进程和系统状态抖动影响，本轮更重要的验收点是模块状态：`fitparse` 和 `garmin_fit_sdk` 已不再进入 `import main`。

## 2. 单独 import 成本

使用 `python3 -X importtime` 复测：

| 依赖 | 累计 import 成本 | 结论 |
|------|------------------|------|
| `fitparse` | 约 13.3 ms | 可延迟，收益明确，风险可控 |
| `garmin_fit_sdk` | 约 11.1 ms | 可延迟，需同时处理 `metrics_resolver` 的 profile 引用 |
| `watchdog.events + watchdog.observers` | 约 23.5 ms | `Observer` 可延迟；`FileSystemEventHandler` 暂不改继承结构 |

## 3. 调用点矩阵

| 依赖 | 当前顶层导入位置 | 实际调用点 | 决策 |
|------|------------------|------------|------|
| `fitparse` | `fit_engine.py` | `FITCoreEngine.parse_fit_file()` | 改为 `_fitparse_deps()` 懒加载 |
| `garmin_fit_sdk.Decoder/Stream` | `main.py` | `_sync_single_fit_file()` 设备名解析 | 改为局部导入 |
| `garmin_fit_sdk.profile` | `metrics_resolver.py` | `_resolve_device_name()` 产品型号翻译 | 改为 `_garmin_device_name_dict()` 懒加载 |
| `watchdog.observers.Observer` | `main.py` | `FITFolderWatchService.restart()` | 改为局部导入 |
| `watchdog.events.FileSystemEventHandler` | `main.py` | `FITFolderHandler` 基类 | 保持顶层导入 |

## 4. 代码改动清单

- `fit_engine.py`
  - 移除顶层 `fitparse` 导入。
  - 新增 `_fitparse_deps()`，仅在 `parse_fit_file()` 真正解析 FIT 时加载 `FitFile/FitParseError`。
  - 类型标注改为 `Any`，避免为了注解触发导入。

- `metrics_resolver.py`
  - 移除顶层 `garmin_fit_sdk.profile` 导入。
  - 新增 `_garmin_device_name_dict()`，仅在解析设备型号需要 SDK profile 时加载。

- `main.py`
  - 移除顶层 `garmin_fit_sdk.Decoder/Stream`。
  - 在 `_sync_single_fit_file()` 的设备名解析分支局部导入。
  - 将 `watchdog.observers.Observer` 局部导入到 `FITFolderWatchService.restart()`。

- `tests/test_startup_import_contract.py`
  - 将 `fitparse`、`garmin_fit_sdk` 加入冷启动禁止加载断言。

- `test_fit_parser.py` / `tests/test_laps_real_data.py`
  - 调整测试 patch 方式以适配 `_fitparse_deps()` 懒加载。
  - mock FIT 用例写入最小合法 FIT header，继续通过生产前置 magic 校验。

## 5. PyInstaller 风险说明

本轮未删除依赖使用，只把导入后移到实际调用点。`fitparse`、`garmin_fit_sdk`、`watchdog` 仍以普通 import 形式出现在源码中，静态收集通常仍可发现。

若后续打包环境发现 hidden import 缺失，应在打包配置中显式加入：

```text
fitparse
garmin_fit_sdk
watchdog.events
watchdog.observers
```

不要为打包收集重新把这些依赖放回 `main.py` 顶层。

## 6. 测试结果

已执行：

```bash
python3 scripts/measure_startup_imports.py
python3 -m pytest tests/test_startup_import_contract.py
python3 -m pytest test_fit_parser.py tests/test_laps_real_data.py
python3 -m pytest test_fit_sync.py -k 'parse_fit_activity_for_sync or activity_list or shadow_diff_json_persists_updates_and_detail_returns'
python3 -m pytest test_watchdog_bridge.py -k 'notify_frontend_ready_only_schedules_background_tasks or new_track_notification_is_queued'
python3 -m pytest tests/test_gap_calculator_lazy_import.py tests/test_detail_api_columns.py
PYTHONPYCACHEPREFIX=/private/tmp/aitrack_pycache python3 -m py_compile main.py fit_engine.py metrics_resolver.py profile_backend.py gap_calculator.py scripts/measure_startup_imports.py
```

结果均通过。

## 7. 下一任务建议

启动冷路径里主要重依赖已经基本移出。下一步建议不要继续做盲目 import 微优化，而是转向真实应用启动阶段的端到端时间线：

- pywebview 窗口创建到首屏隐藏 loading 的时间；
- 前端 `bootstrapApplication()` 各阶段耗时；
- 首次活动列表 API 耗时；
- 首屏后延迟任务是否按 P2 计划错峰执行。

