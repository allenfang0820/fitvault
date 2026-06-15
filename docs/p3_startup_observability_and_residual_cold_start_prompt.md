# P3 启动链路可观测性与剩余冷启动项复测提示词

> 任务类型：P3 启动性能可观测性 / 剩余瓶颈复测
> 前置条件：P0 活动列表查询轻量化、P1 活动列表数据库索引与排序优化、P1 scipy/numpy 延迟导入、P2 后台任务后移已完成
> 核心原则：先证明，后优化；没有证据不改性能逻辑

## 一、任务背景

前序任务已经处理了已确认的启动慢主因和首屏抢资源问题：

1. 活动列表不再读取/返回大字段：`hr_curve`、`speed_curve`、`shadow_diff_json`、`track_json`、`points_json`。
2. 活动列表查询增加排序、类型、地区、文件路径相关索引。
3. `gap_calculator.py` 已延迟导入 `numpy/scipy.signal`，`import main` 不应再加载 scipy/numpy。
4. 活动列表指标回填、地区补全、活动完整性检查、静默网关验证已后移到首屏之后。

外部报告 `/Users/fanglei/.qclaw/workspace-agent-823b6b76/脉图启动加载时间根因分析_20260615.md` 中还提到 `pandas` 可能占用 0.16-0.21s，但当前代码初步检查显示：

- `pandas` 只在 `llm_backend.points_to_dataframe_csv()` 函数内部导入；
- `main.py` 顶层导入 `llm_backend`，但不应在启动时触发 `points_to_dataframe_csv()`；
- 因此 P3 必须先复测 `pandas` 是否仍在实际启动导入链路，不得基于旧报告直接改代码。

## 二、任务目标

完成一轮低侵入启动性能复测与可观测性建设：

1. 建立可重复的启动/import 测量脚本或测试，覆盖 `import main`、关键重模块是否被加载、基础耗时统计。
2. 验证 `import main` 后 `sys.modules` 中不应出现 `numpy`、`scipy`、`scipy.signal`、`pandas`，除非有明确可解释的依赖链。
3. 复测 P0-P2 后的冷启动剩余耗时，输出新的瓶颈排序。
4. 若发现 `pandas` 或其他重依赖仍在启动链路，定位真实导入链路，并只做最小延迟导入或解耦。
5. 若未发现重依赖回潮，则不做生产代码性能改动，只补测量工具/测试和完成报告。
6. 固化防回归测试，防止未来把 `numpy/scipy/pandas` 重新带回 `import main` 冷启动路径。

## 三、强制契约约束

本任务必须遵守以下约束：

1. 不得修改 FIT 解析算法、GAP 算法、Resolver 输出语义、运动复盘算法、AI prompt 语义。
2. 不得修改数据库 schema、迁移、生产数据文件或用户本地数据库内容。
3. 不得把 P2 已后移的后台任务重新放回首屏同步路径。
4. 不得让活动列表接口重新读取或返回大字段：`hr_curve`、`speed_curve`、`shadow_diff_json`、`track_json`、`points_json`。
5. 不得让前端为性能绕过后端事实源，不得在 `track.html` 中新增事实推导。
6. 不得为了通过测试 mock 掉真实导入链路；测试应验证真实 `import main` 后的模块加载状态。
7. 不得引入新的重量级依赖、后台守护进程或网络调用。
8. 如需新增脚本，应放在 `scripts/` 或 `tests/` 中，且默认只读、可重复、不会写用户数据。
9. 若本任务只发现“无代码可改”，必须如实输出结论，不得制造无意义改动。

## 四、建议执行步骤

### Step 1：复核当前导入链路

执行前先检查：

- `main.py` 顶层 import 列表；
- `llm_backend.py` 中 `pandas` 的唯一使用点；
- `gap_calculator.py` 中 `_numeric_deps()` 懒加载是否仍存在；
- `metrics_resolver.py` 是否在 import 阶段实例化或调用 GAP 计算；
- P2 后台任务是否仍通过 timer 延迟触发。

需要记录：

- 顶层直接导入的本地模块；
- 可能间接导入重依赖的模块；
- 当前是否存在导入时执行 I/O、启动线程、启动 Timer 的代码。

### Step 2：建立冷启动测量命令

建议新增一个只读脚本，例如：

```text
scripts/measure_startup_imports.py
```

脚本职责：

- 在全新 Python 进程中执行 `import main`；
- 记录总耗时；
- 输出关键模块是否已加载：`numpy`、`scipy`、`scipy.signal`、`pandas`、`fitparse`、`garmin_fit_sdk`、`webview`；
- 可选输出前 N 个慢导入项，但不得依赖网络或第三方新增依赖；
- 不启动 pywebview 窗口；
- 不调用 `main.main()` 或任何会启动 UI/后台任务的入口。

如果不新增脚本，也可以新增 pytest，但必须保证测量和断言在子进程中完成，避免当前 pytest 进程已导入模块污染结果。

### Step 3：新增防回归测试

建议新增：

```text
tests/test_startup_import_contract.py
```

至少覆盖：

1. 子进程 `import main` 成功。
2. `import main` 后 `numpy`、`scipy`、`scipy.signal` 不在 `sys.modules`。
3. `import main` 后 `pandas` 不在 `sys.modules`，除非 Step 1 证明有不可避免的架构原因；如不可避免，必须在完成报告中说明。
4. 测试不得要求具体耗时阈值过严，避免 CI/本机抖动；如设置阈值，只能是宽松的防灾阈值。
5. 输出中应包含 import 耗时，便于人工比较 P0-P2 前后效果。

### Step 4：必要时做最小代码改动

只有当 Step 1-3 证明存在真实启动回潮时，才允许改生产代码。

允许的改动：

- 将重依赖从模块顶层移入实际使用函数；
- 将仅为 PyInstaller 收集而存在的顶层 import 改为更轻的收集方式或加注释说明；
- 将启动阶段不需要的初始化改为调用时初始化。

禁止的改动：

- 替换算法实现；
- 删除功能；
- 改 API 返回结构；
- 改数据库字段；
- 改用户可见 UI 流程；
- 为了测量而启动真实桌面窗口。

### Step 5：完成报告

新增完成报告：

```text
docs/p3_startup_observability_and_residual_cold_start_completion_report.md
```

报告必须包含：

- 本轮复测环境与命令；
- `import main` 耗时；
- `numpy/scipy/scipy.signal/pandas` 是否进入 `sys.modules`；
- 与外部报告结论的交叉验证结果；
- 是否做了生产代码改动；
- 若未改代码，说明原因；
- 已新增/更新的测试；
- 剩余风险和下一任务建议。

## 五、验收标准

本任务完成时必须满足：

1. 有可重复命令能测量 `import main` 冷启动耗时和关键模块加载状态。
2. 有自动化测试防止 `numpy/scipy/scipy.signal/pandas` 回到 `import main` 冷启动路径。
3. 如果发现回潮，已用最小改动修复，并验证不影响相关业务功能。
4. 如果未发现回潮，没有生产代码噪音改动。
5. P0/P1/P2 已建立的契约测试仍通过：

```bash
python3 -m pytest tests/test_gap_calculator_lazy_import.py tests/test_detail_api_columns.py
python3 -m pytest test_fit_sync.py -k 'activity_list_schedules_metric_backfill_without_immediate_worker or activity_list or shadow_diff_json_persists_updates_and_detail_returns'
python3 -m pytest test_watchdog_bridge.py -k 'notify_frontend_ready_only_schedules_background_tasks or new_track_notification_is_queued'
python3 -m pytest tests/test_sport_hub_pagination.py -k 'StartupBackgroundDeferral'
```

6. 新增的 P3 启动导入契约测试通过。

## 六、输出格式

完成后请输出：

```text
P3 启动链路可观测性与剩余冷启动项复测完成报告

1. 复测结论
2. pandas / numpy / scipy 导入状态
3. 代码改动清单
4. 测试结果
5. 是否需要更新后续任务清单
6. 下一任务建议
```

## 七、执行前再思考检查单

执行本提示词前必须逐项确认：

- 当前任务是不是测量优先，而不是直接改性能逻辑？
- 是否会误触发 pywebview、Watchdog、后台同步、地区补全或指标回填？
- 新增测试是否在子进程里检查干净 import 状态？
- 是否保护了 P0 活动列表轻量查询契约？
- 是否保护了 P1 scipy/numpy 懒加载契约？
- 是否保护了 P2 后台任务后移契约？
- 如果 `pandas` 没有进入启动链路，是否愿意不改生产代码？

