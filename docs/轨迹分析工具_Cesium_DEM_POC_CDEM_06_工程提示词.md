# CDEM-06 工程级提示词

> 任务：CDEM-06 海拔墙彻底退役
> 生成时间：2026-07-30
> 执行模式：task-loop-runner 门禁循环

## 0. 架构契约核对

执行前必须阅读并刷新：

- `README.md`
- `docs/archive/ARCHITECTURE.md`
- `docs/DIR_SPEC.md`
- `docs/field_contract_matrix.md`
- `docs/脉图运动复盘系统_开发团队交付手册_v1.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_开发交付手册.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_开发任务清单.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_契约摘要.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_基线审计报告.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_CDEM_05_工程提示词.md`
- `track.html` 的 `appState`、`setupViewerInteractions()`、`updateScene()`、`drawProfileChart()`、completed / remaining 轨迹、CP / 里程 / 最高点 marker
- `tests/test_track_cesium_dem_contract.py`

刷新摘要后确认：

- 海拔墙必须彻底退役，不保留入口、内部调试、隐藏兼容、活跃 entity 或注释性残留。
- 底部半透明海拔剖面图必须保留，继续消费 FIT / 手表海拔。
- DEM 和海拔墙职责已分离：真实地形由 ArcGIS provider 负责地图环境，FIT 海拔由底部剖面表达。
- `fullPositions` 必须保留给 completed / remaining 轨迹分段；`fullMaxHeights` / `fullMinHeights` 若仅服务 wall 可删除。
- CP、里程、最高点 / 坡顶、进度切片、2D / 3D 滑块、指南针 / 归北、ArcGIS provider 和 DEM session cache 不得丢失。
- dirty worktree 中存在大量无关改动，不得 stash、reset、覆盖、格式化或提交无关文件。

## 1. Goal

从产品和代码中彻底移除海拔墙，使底部半透明剖面图成为唯一海拔剖面表达，同时保持轨迹分段、标记、进度和真实地形能力稳定。

## 2. Scope

允许修改：

- `track.html` 中 `wallEntity`、`海拔剖面堆积墙` 点击命中、wall entity 创建 / 删除、`wallColor`、`fullMaxHeights` / `fullMinHeights` 等海拔墙专属状态
- `tests/test_track_cesium_dem_contract.py`
- `docs/轨迹分析工具_Cesium_DEM_POC_契约摘要.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_CDEM_06_工程提示词.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_开发任务清单.md`，仅在验证和 review 通过后更新状态
- `docs/轨迹分析工具_Cesium_DEM_POC_基线审计报告.md`，仅记录 CDEM-06 结果

禁止修改：

- `main.py`、`docs/js_api_contract.json`、DEM cache 生命周期和 pywebview API。
- ArcGIS provider、真实地形图层 UI、2D / 3D 滑块、completed / remaining 轨迹语义。
- FIT / GPX 解析、活动数据库、累计爬升、最高海拔、距离、配速、剖面图、复盘和 AI 事实。
- MapLibre / deck.gl、活动详情概览 / 复盘合同，以及并行 dirty worktree 文件。

## 3. Expected Work

- 从 `appState` 删除 `wallEntity`、`fullMaxHeights`、`fullMinHeights`。
- 从点击命中逻辑删除 `entityName === '海拔剖面堆积墙'`。
- 从 `updateScene()` 删除旧 wall entity remove / add、`wallColor`、`maximumHeights` / `minimumHeights` 维护。
- 保留 `appState.fullPositions`、completed / remaining polyline 和 `CallbackProperty` 进度切片。
- 更新测试：旧“海拔墙存在”断言改为“海拔墙不存在”，同时继续断言底部剖面图和轨迹分段存在。
- 运行 grep 验收，确认无 `wallEntity`、`海拔墙`、`海拔剖面堆积墙`、`wall:`、`Cesium.Wall` 活跃残留。

## 4. Validation

```bash
rg -n "wallEntity|elevation wall|海拔墙|海拔剖面堆积墙|wall\\.wall|Cesium\\.Wall" track.html tests
.venv312/bin/python -m pytest -q tests/test_track_cesium_dem_contract.py tests/test_track_dem_session_cache.py tests/test_track_thumbnail_canvas_v4.py
git diff --check
```

## 5. Completion Definition

- 用户界面和代码中无海拔墙活跃实现。
- 底部剖面图、进度切片、CP、里程、最高点 / 坡顶和真实地形 provider 均保留。
- 不改写任何活动事实、统计、复盘或 AI 输入。
- 聚焦测试、grep 验收和 `git diff --check` 通过。

## 6. Reread Triggers

出现以下任一情况，必须重新全文阅读相关文档或源码：

- 删除动作影响 `fullPositions`、completed / remaining polyline、progress slider 或 profile chart。
- 需要修改 FIT / 手表海拔、活动数据库、统计、剖面图、复盘或 AI 输入。
- 需要修改 ArcGIS provider、DEM session cache 或 2D / 3D 滑块语义。
- 测试失败指向既有轨迹交互、活动事实或 API 生命周期。
