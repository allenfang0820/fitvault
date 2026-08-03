# CDEM-02 工程级提示词

> 任务：CDEM-02 Viewer 初始化兼容
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
- `tests/test_track_cesium_dem_contract.py`
- `track.html` 的 `initCesiumViewer()`、`setupViewerInteractions()`、相机控制、2D / 3D 滑块、指南针和 `requestSceneRender()` 相关代码

刷新摘要后确认：

- FIT / 手表海拔仍是活动事实源，Viewer 兼容改造不得改变活动事实。
- 本任务只处理 Cesium 1.143 下 Viewer 初始化、标准底图、椭球地形和相机交互兼容。
- Cesium 1.143 的 `Viewer` 应使用 `baseLayer` 接入标准底图；不能继续依赖旧 `imageryProvider` 选项。
- `terrainProvider` 仍使用 `new Cesium.EllipsoidTerrainProvider()`，不接入 DEM provider。
- 2D / 3D 滑块只控制相机视角，不触发 DEM 下载，不切换 terrain provider。
- CP、里程、坡顶、进度、底部剖面图、海拔墙删除目标和活动详情跳转能力都不得丢失。
- dirty worktree 中存在大量无关改动，不得 stash、reset、覆盖或格式化。

## 1. Goal

确认并修复 Cesium `1.143` 下轨迹分析工具 Viewer 初始化兼容性，使标准 CARTO 底图、椭球地形、相机事件、指南针同步、`requestSceneRender()` 和 2D / 3D 视角滑块释放链路继续可用。

## 2. Scope

允许修改：

- `track.html`，仅限 `initCesiumViewer()` 和 Viewer 初始化直接兼容点
- `tests/test_track_cesium_dem_contract.py`
- `docs/轨迹分析工具_Cesium_DEM_POC_契约摘要.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_CDEM_02_工程提示词.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_开发任务清单.md`，仅在验证通过后更新状态
- 可新增或更新浏览器 / pywebview 手测记录文档

禁止修改：

- DEM provider、DEM 下载、DEM 缓存、长期离线地形包。
- 海拔墙删除逻辑；海拔墙仍留到 CDEM-06。
- 轨迹渲染语义、CP 点、里程点、坡顶 / 最高点、进度切片、底部剖面图。
- FIT / GPX 解析、活动数据库、累计爬升、最高海拔、距离、配速等事实口径。
- 活动详情页概览 / 复盘合同、疲劳复盘算法、AI prompt、MapLibre / deck.gl。
- 与本任务无关的并行 dirty worktree 文件。

## 3. Expected Work

- 核对 Cesium 1.143 的 Viewer 构造参数。
- 确认 `options.imageryProvider` 不再作为 Viewer 标准底图接入方式。
- 将标准 CARTO 底图改为 `baseLayer: new Cesium.ImageryLayer(new Cesium.UrlTemplateImageryProvider(...))`。
- 保持 `terrainProvider: new Cesium.EllipsoidTerrainProvider()`。
- 保持 `setupViewerInteractions()`、camera `changed` 监听、指南针同步、`requestSceneRender()` 和滑块 `lookAtTransform(Cesium.Matrix4.IDENTITY)` 释放链路。
- 用静态契约测试锁定兼容行为。

## 4. Validation

```bash
node -e "const Cesium=require('./lib/Cesium/index.cjs'); console.log(Cesium.VERSION, typeof Cesium.Viewer, typeof Cesium.ImageryLayer, typeof Cesium.UrlTemplateImageryProvider)"
.venv312/bin/python -m pytest -q tests/test_track_cesium_dem_contract.py
git diff --check
```

## 5. Completion Definition

- `initCesiumViewer()` 在 Cesium 1.143 下不再依赖旧 `imageryProvider` Viewer option。
- 标准 CARTO 底图通过 `baseLayer` 明确进入 Viewer。
- 标准地形仍为椭球地形，无 DEM 情况下轨迹分析页保持可运行。
- 相机交互链路、指南针和 2D / 3D 滑块释放链路仍有测试覆盖。
- 聚焦契约测试和 `git diff --check` 通过。

## 6. Reread Triggers

出现以下任一情况，必须重新全文阅读相关文档或源码：

- 需要改动 `setupViewerInteractions()` 之外的大范围相机事件。
- 需要接入 DEM provider 或 terrain 切换。
- 需要删除海拔墙、改轨迹 entity、改 CP / 里程 / 坡顶 / 进度 / 剖面图逻辑。
- 测试失败指向活动事实、活动详情或复盘合同。
- 发现 Cesium 1.143 的底图或地形 API 与本提示词假设不一致。
