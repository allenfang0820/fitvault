# P4 启动链路 fitparse / garmin_fit_sdk / watchdog 延迟导入评估提示词

> 任务类型：P4 启动冷路径依赖延迟导入评估
> 前置条件：P0 活动列表查询轻量化、P1 索引优化、P1 scipy/numpy 延迟导入、P2 后台任务后移、P3 启动链路可观测性已完成
> 核心原则：评估优先，收益明确再改；不得为了少量 import 时间牺牲 FIT 解析、文件监听、打包稳定性

## 一、任务背景

P3 已建立 `scripts/measure_startup_imports.py` 和 `tests/test_startup_import_contract.py`，当前 `import main` 约 0.23s，且 `numpy/scipy/pandas/webview` 不在冷启动路径。

P3 仍显示以下模块进入 `import main` 冷路径：

- `fitparse`
- `garmin_fit_sdk`

同时代码阅读显示：

- `main.py` 顶层导入 `from garmin_fit_sdk import Decoder, Stream`，实际主要用于 FIT 解析路径。
- `fit_engine.py` 顶层导入 `from fitparse import FitFile, FitParseError`，实际用于 `FITCoreEngine.parse_fit_file()`。
- `main.py` 顶层导入 `watchdog.events.FileSystemEventHandler` 和 `watchdog.observers.Observer`，实际用于 FIT 文件夹监听；其中 `FITFolderHandler` 当前直接继承 `FileSystemEventHandler`，延迟导入需要谨慎设计。
- `metrics_resolver.py` 顶层导入 `garmin_fit_sdk.profile as garmin_fit_profile`，可能用于枚举/字段 profile 解析，需先确认是否能安全延迟。

P4 的目标不是直接“把所有 import 都搬进函数”，而是评估这些模块是否值得、是否能够安全后移到具体功能调用点，并在收益清楚时做最小改动。

## 二、任务目标

完成 P4 评估并视证据决定是否实施最小改动：

1. 用 P3 测量脚本建立 P4 前基线，记录 `import main` 耗时和模块加载状态。
2. 分别测量 `fitparse`、`garmin_fit_sdk`、`watchdog` 单独 import 成本，给出收益排序。
3. 梳理三类依赖的实际调用点和架构风险。
4. 判断每个依赖是否适合延迟导入：
   - `fitparse`: 是否可从 `fit_engine.py` 顶层移动到 `parse_fit_file()` 内部，同时保留测试 patch 能力和异常类型处理。
   - `garmin_fit_sdk`: 是否可从 `main.py` 顶层移动到 `_sync_single_fit_file()` / FIT raw parse 调用点，同时确保 PyInstaller 打包仍能收集。
   - `watchdog`: 是否可延迟到 `FITWatchService.restart()`；如直接继承导致顶层必须导入，应评估是否值得引入动态基类或轻量适配层。
5. 若预计收益低、风险高，应只输出评估报告和测试，不做生产代码改动。
6. 若实施改动，必须同步更新 P3 测量脚本和启动导入契约测试，明确哪些模块不应再进入 `import main`。

## 三、强制契约约束

本任务必须遵守：

1. 不得改变 FIT 解析结果、字段名、单位、scale、异常语义和 canonical 数据来源。
2. 不得修改数据库 schema、迁移或用户本地数据。
3. 不得改变活动列表轻量查询契约，不得恢复大字段读取/返回。
4. 不得改变 P2 后台任务后移契约，不得在 `import main` 或首屏前启动 watchdog、Timer、线程、窗口或后台 worker。
5. 不得删除 `fitparse`、`garmin_fit_sdk`、`watchdog` 功能；只能评估或延迟导入。
6. 不得用 mock 或测试假象替代真实导入链路测量。
7. 不得引入新第三方依赖。
8. 不得为了减少 import 时间破坏 PyInstaller 打包；如改动可能影响打包收集，必须保留明确注释或显式 hidden-import 方案建议。
9. 不得大规模重构 `FITCoreEngine`、`MetricsResolver`、`FITWatchService`；P4 只允许小步、可回滚的启动路径改动。
10. 如果 `watchdog` 延迟导入需要改继承结构，必须先证明收益足够；否则保持不改。

## 四、建议执行步骤

### Step 1：建立 P4 前基线

运行：

```bash
python3 scripts/measure_startup_imports.py
python3 -m pytest tests/test_startup_import_contract.py
```

另用子进程分别测量：

```bash
python3 -X importtime -c "import fitparse" 2>&1
python3 -X importtime -c "import garmin_fit_sdk" 2>&1
python3 -X importtime -c "import watchdog.events; import watchdog.observers" 2>&1
```

或写临时子进程脚本输出简洁 JSON。不要把临时脚本提交，除非它有长期价值。

### Step 2：调用点矩阵

输出一张矩阵，至少包含：

| 依赖 | 当前顶层导入位置 | 实际调用点 | 可延迟性 | 风险 | 预估收益 |
|------|------------------|------------|----------|------|----------|

必须覆盖：

- `main.py`
- `fit_engine.py`
- `metrics_resolver.py`
- `test_fit_parser.py`
- `tests/test_laps_real_data.py`
- `test_watchdog_bridge.py`

### Step 3：决策门槛

只有满足以下条件之一，才允许改生产代码：

1. 某依赖单独 import 成本明显，且可以用局部 import 无语义风险地移出 `import main`。
2. 改动后 P3 测量脚本可稳定显示该依赖不再进入冷路径。
3. 相关功能测试可以覆盖 FIT 解析、同步、watchdog 通知或 resolver 使用点。

如果收益小于风险，应明确“不改”。

### Step 4：允许的最小改动模式

#### fitparse

可考虑：

- 将 `FitFile` / `FitParseError` 从 `fit_engine.py` 顶层移入 `parse_fit_file()`；
- 如测试需要 patch，提供模块级轻量 helper，例如 `_fitparse_deps()`，但不得在 import 时加载 fitparse；
- 保持 `FitParseError` 捕获语义一致。

必须验证：

```bash
python3 -m pytest test_fit_parser.py tests/test_laps_real_data.py
```

#### garmin_fit_sdk

可考虑：

- 移除 `main.py` 顶层 `Decoder, Stream`，在实际 FIT raw 解析位置局部导入；
- 检查 `fit_engine.py.parse_fit_file_raw()` 已经局部导入，可作为参考；
- `metrics_resolver.py` 的 `garmin_fit_sdk.profile` 若仅用于少数函数，可评估 helper 延迟导入；若大量常量依赖顶层 profile，则先不改。

必须验证：

```bash
python3 -m pytest test_fit_sync.py -k 'parse_fit_activity_for_sync or activity_list or shadow_diff_json_persists_updates_and_detail_returns'
python3 -m pytest tests/test_gap_calculator_lazy_import.py tests/test_detail_api_columns.py
```

#### watchdog

可考虑：

- 保持 `FITFolderHandler` 行为不变，仅评估是否能把 `Observer` 局部导入到 `FITWatchService.restart()`；
- `FileSystemEventHandler` 因基类需要，如延迟会导致结构变复杂，优先不改；
- 不得为了延迟导入破坏现有 test patch、通知队列或 stop/restart 行为。

必须验证：

```bash
python3 -m pytest test_watchdog_bridge.py
```

注意：完整 `test_watchdog_bridge.py` 若存在历史无关失败，应记录具体失败并至少运行 P2 相关窄口径用例。

### Step 5：更新测量与报告

如果改动生产代码：

- 更新 `scripts/measure_startup_imports.py` 的观察模块状态。
- 更新 `tests/test_startup_import_contract.py` 的断言。
- 重新记录 `import main` 耗时。

无论是否改动，都新增完成报告：

```text
docs/p4_startup_lazy_fitparse_garmin_watchdog_completion_report.md
```

报告必须包含：

1. P4 前后 `import main` 耗时。
2. 三个依赖的单独 import 成本。
3. 调用点矩阵。
4. 每个依赖的决策：改 / 不改 / 延后。
5. 若改动，列出生产代码改动和防回归测试。
6. 若不改，说明收益/风险判断。
7. PyInstaller 打包风险说明。
8. 下一任务建议。

## 五、验收标准

P4 完成时必须满足：

1. 有明确证据说明 `fitparse`、`garmin_fit_sdk`、`watchdog` 是否值得延迟导入。
2. 若实施改动，`scripts/measure_startup_imports.py` 能证明冷路径模块状态变化。
3. 若不实施改动，有完成报告说明原因，不留下半成品代码。
4. 相关回归测试通过。
5. P0/P1/P2/P3 既有启动性能契约不回退。

建议基础验证命令：

```bash
python3 scripts/measure_startup_imports.py
python3 -m pytest tests/test_startup_import_contract.py
python3 -m pytest tests/test_gap_calculator_lazy_import.py tests/test_detail_api_columns.py
python3 -m pytest test_fit_sync.py -k 'activity_list_schedules_metric_backfill_without_immediate_worker or activity_list or shadow_diff_json_persists_updates_and_detail_returns'
python3 -m pytest test_watchdog_bridge.py -k 'notify_frontend_ready_only_schedules_background_tasks or new_track_notification_is_queued'
python3 -m pytest tests/test_sport_hub_pagination.py -k 'StartupBackgroundDeferral'
PYTHONPYCACHEPREFIX=/private/tmp/aitrack_pycache python3 -m py_compile main.py fit_engine.py metrics_resolver.py profile_backend.py gap_calculator.py scripts/measure_startup_imports.py
```

若改了 `fit_engine.py`，追加：

```bash
python3 -m pytest test_fit_parser.py tests/test_laps_real_data.py
```

若改了 watchdog 相关结构，追加：

```bash
python3 -m pytest test_watchdog_bridge.py
```

## 六、执行前再思考检查单

执行 P4 前必须逐项确认：

- 是否已经用 P3 脚本拿到当前基线？
- 是否区分了“顶层导入成本”和“实际功能调用成本”？
- 是否会破坏 FIT 解析字段追溯和异常语义？
- 是否会破坏 PyInstaller 对依赖的收集？
- 是否会让 watchdog 或后台任务在首屏前启动？
- 是否真的需要改 `watchdog` 的继承结构？
- 如果收益很小，是否愿意只写评估报告而不改生产代码？

