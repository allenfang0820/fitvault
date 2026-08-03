# CDEM-14 工程级提示词

> 任务：轨迹分析工具高密度轨迹加载性能分析与优化规划
> 生成时间：2026-08-03
> 执行模式：task-loop-runner 门禁循环

## 0. 契约核对

执行前必须刷新并阅读：

- `docs/轨迹分析工具_Cesium_DEM_POC_开发交付手册.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_开发任务清单.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_契约摘要.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_开发完成报告.md`
- `docs/轨迹分析工具_真实地形标记清晰度修复任务清单.md`
- 当前 `track.html`、`main.py` 和直接相关测试

本轮只完成性能根因分析、工程提示词和任务清单落盘，不修改生产行为。dirty worktree 中无关修改必须保留。

## 1. Goal

解决高密度运动轨迹加载感知等待超过 5 秒的问题，优先处理“四姑娘山二峰登顶”等大轨迹，同时保持活动事实、地图交互和现有 CDEM-12 相机体验。

## 2. Confirmed Evidence

- activity `127`：`26,052` 点，track JSON 约 `9.3 MB`。
- activity `907`：`21,690` 点，track JSON 约 `7.9 MB`。
- 本地直接调用 `Api.load_activity_track()` 约 `0.05–0.07s`，当前证据更指向 WebView bridge、前端主线程和 Cesium 首屏渲染，而不是 SQLite 查询本身。
- `applyDataAndRender()` 同步执行 `_buildStatsFromCanonical()`、`updateScene()`、图表、报告、列表和全量 `sync_track_context()`；相机 `flyTo()` 固定 `2.5s`。
- canonical points 已带 `dist_km` 时，当前仍无条件计算相邻 `haversine()` fallback。
- `haversine()` 每次调用都会执行 `console.warn()`；高密度 canonical 距离循环和峰顶邻域扫描会产生大量重复日志，应作为第一优先级热路径修复。
- `_detectPeakMarkers()` 对每个点扫描前后 300 米邻域，重复计算 haversine。
- `syncCurrentTrackContextForActivityAdvice()` 再次对完整 points 执行 `JSON.stringify` 并发送给 Python。
- 真实地形还会增加 ArcGIS provider、terrain tile settle 和 hillshade imagery 的网络 / 渲染成本。

## 3. Required Task Decomposition

按收益和风险顺序执行：加载分段基线；热循环 / 逐次日志 / 峰顶算法；canonical bridge 重复序列化；相机与非关键任务调度；中期复测；必要时才做 Cesium 显示几何 POC；最后做 DEM 性能隔离和真实 DMG 验收。

PLOAD-01 至 PLOAD-03 后必须设置复杂度门禁：若首屏目标已达到，PLOAD-04 记录“不采用显示抽稀”并完成，不得强行引入双轨迹结构。

## 4. Frozen Constraints

- FIT / 手表记录和后端 canonical metrics 是事实源；不得用显示抽稀结果改写事实。
- 必须保留 CP 展示 / 新增 / 编辑 / 删除、里程 1/5/10km 层级、最高点优先级、进度切片、底部剖面联动。
- 2D / 3D slider 只控制相机；标准 / 真实地形按钮只控制 terrain provider。
- 不恢复海拔墙，不引入 MapLibre + deck.gl，不引入长期 DEM 缓存。
- 不在未完成基线和 POC 前直接改 `flyTo`、抽稀比例、peak 算法、全局 resolution 或 provider。
- 任何触及 API、AI route facts、DB 或活动生命周期的改动，必须重新全文阅读相关文档和测试。
- 保留所有无关 dirty 修改，不得 stash、reset 或覆盖。

## 5. Validation

每个子任务必须运行任务清单规定的聚焦测试、JS 语法检查和 `git diff --check`；完成前必须覆盖真实 DMG 的四姑娘山高密度轨迹、城市跑、山地 / 越野跑和骑行轨迹，并记录首屏可交互时间与完整 settle 时间。

## 6. Completion Definition

- 至少确认两个主要耗时瓶颈并有分段数据。
- 优化后高密度轨迹首屏交互等待较基线下降至少 `30%`，同时功能合同全绿。
- 未执行的设备、网络或真实 UI 场景不得写成通过。
- 只有 PLOAD-00 至 PLOAD-06 均完成后，才能将 CDEM-14 标记 `Completed`。
