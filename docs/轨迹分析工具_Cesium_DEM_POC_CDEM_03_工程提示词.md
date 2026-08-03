# CDEM-03 工程级提示词

> 任务：CDEM-03 地形图层开关
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
- `docs/轨迹分析工具_Cesium_DEM_POC_CDEM_02_工程提示词.md`
- `tests/test_track_cesium_dem_contract.py`
- `track.html` 的顶栏、`appState`、`initCesiumViewer()`、2D / 3D 滑块和 terrain provider 相关代码

刷新摘要后确认：

- FIT / 手表海拔仍是活动事实源，地形图层只影响地图环境显示。
- CDEM-03 只新增独立地形图层入口和状态机，不实现 DEM 会话缓存。
- 默认标准地形；用户主动点 `真实地形` 才进入真实地形加载流程。
- 本任务中没有 CDEM-04 provider / cache 时，真实地形加载必须可回退标准地形，且不得下载 DEM。
- 2D / 3D 滑块只控制相机视角，不切换 terrain provider。
- CP、里程、坡顶、进度、底部剖面图、海拔墙删除目标和活动详情跳转能力都不得丢失。
- dirty worktree 中存在大量无关改动，不得 stash、reset、覆盖或格式化。

## 1. Goal

新增独立地形图层控制，让用户可以在 `标准地形` 与 `真实地形` 之间切换；该控制与现有 2D / 3D 视角滑块解耦，并为后续 CDEM-04 / CDEM-05 接入真实 DEM provider 留出清晰状态机。

## 2. Scope

允许修改：

- `track.html` 的顶栏图层 UI、地形图层状态、标准地形回退、真实地形加载占位函数
- `tests/test_track_cesium_dem_contract.py`
- `docs/轨迹分析工具_Cesium_DEM_POC_契约摘要.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_CDEM_03_工程提示词.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_开发任务清单.md`，仅在验证通过后更新状态
- `docs/轨迹分析工具_Cesium_DEM_POC_基线审计报告.md`，仅记录 CDEM-03 结果

禁止修改：

- DEM 会话缓存、下载目录、清理生命周期和后端 API。
- 真实 DEM provider 的正式接入、地形贴合、轨迹高度策略。
- 海拔墙删除逻辑；海拔墙仍留到 CDEM-06。
- 轨迹渲染语义、CP 点、里程点、坡顶 / 最高点、进度切片、底部剖面图。
- FIT / GPX 解析、活动数据库、累计爬升、最高海拔、距离、配速等事实口径。
- 活动详情页概览 / 复盘合同、疲劳复盘算法、AI prompt、MapLibre / deck.gl。
- 与本任务无关的并行 dirty worktree 文件。

## 3. Expected Work

- 在轨迹分析工具顶栏新增 `图层` 控件，提供 `标准地形` 与 `真实地形`。
- 在 `appState` 中新增地形图层状态，例如 mode/status/message。
- 默认标准地形，初始化时明确同步 UI。
- 新增标准地形回退函数，将 terrain provider 设为 `new Cesium.EllipsoidTerrainProvider()`。
- 新增真实地形加载占位函数；CDEM-03 阶段不得下载 DEM，不得写数据库。
- 点击真实地形后显示 loading 状态，加载失败时回退标准地形。
- 保证 `map-view-slider` 事件中不调用任何地形图层函数。
- 用静态契约测试锁定 UI 文案、状态机、滑块解耦和无默认 DEM 下载。

## 4. Validation

```bash
.venv312/bin/python -m pytest -q tests/test_track_cesium_dem_contract.py
git diff --check
```

## 5. Completion Definition

- 顶栏存在独立 `图层` 控件。
- 默认标准地形，不默认下载 DEM。
- 真实地形路径有 loading 和失败回退标准地形状态。
- 2D / 3D 滑块不触发地形 provider 切换。
- 聚焦契约测试和 `git diff --check` 通过。

## 6. Reread Triggers

出现以下任一情况，必须重新全文阅读相关文档或源码：

- 需要新增后端 DEM API、下载缓存或持久化目录。
- 需要改变轨迹高度、CP/里程/坡顶显示高度策略。
- 需要删除海拔墙或修改底部剖面图数据来源。
- 需要让 2D / 3D 滑块控制地形。
- 测试失败指向活动事实、活动详情或复盘合同。
