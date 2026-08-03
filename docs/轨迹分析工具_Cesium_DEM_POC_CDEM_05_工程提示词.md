# CDEM-05 工程级提示词

> 任务：CDEM-05 真实地形轨迹贴合与语义轨迹保留
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
- `docs/轨迹分析工具_Cesium_DEM_POC_CDEM_04_工程提示词.md`
- `track.html` 的 `loadRealTerrainLayerForCurrentTrack()`、`selectTerrainLayer()`、`updateScene()`、`renderCpMapLayer()`、CP / 里程 / 最高点 marker 和 2D / 3D 滑块绑定
- `tests/test_track_cesium_dem_contract.py`

刷新摘要后确认：

- FIT / 手表海拔仍是活动事实源；DEM 只用于地图环境显示。
- 用户已确认本轮不考虑自托管，CDEM-05 默认在线 provider 选 ArcGIS Elevation。
- 真实地形只由用户主动点击图层触发；启动、轨迹加载和 2D / 3D 滑块不得触发 provider 创建或 DEM 请求。
- CDEM-04 session cache 仍在真实地形点击路径中作为 bbox / 生命周期边界，但本任务不做自管 tile 下载、长期缓存或离线包。
- 标准地形必须保持既有椭球 + FIT 海拔夸张高度；真实地形下才使用贴地 / 近地显示。
- completed / remaining 轨迹分段、`CallbackProperty`、进度滑块、CP、里程、最高点 / 坡顶、底部剖面图和相机控制都不得丢失。
- 海拔墙不在本任务删除，仍留给 CDEM-06。
- dirty worktree 中存在大量无关改动，不得 stash、reset、覆盖、格式化或提交无关文件。

## 1. Goal

接入 ArcGIS World Elevation 作为默认在线 DEM provider，并在真实地形模式下让轨迹与标记贴近真实地形显示，同时保持标准地形和既有轨迹分析语义不变。

## 2. Scope

允许修改：

- `track.html` 中真实地形 provider 创建、provider 切换后的 scene 刷新、轨迹 polyline clamp 策略、CP / 里程 / 最高点 marker 高度策略
- `tests/test_track_cesium_dem_contract.py`
- `docs/轨迹分析工具_Cesium_DEM_POC_契约摘要.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_CDEM_05_工程提示词.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_开发任务清单.md`，仅在验证和 review 通过后更新状态
- `docs/轨迹分析工具_Cesium_DEM_POC_基线审计报告.md`，仅记录 CDEM-05 结果

禁止修改：

- `main.py`、`docs/js_api_contract.json`、DEM cache 生命周期和 pywebview API，除非发现 CDEM-04 直接阻塞。
- FIT / GPX 解析、活动数据库、累计爬升、最高海拔、距离、配速、剖面图、复盘和 AI 事实。
- 海拔墙删除逻辑；CDEM-06 再彻底退役。
- MapLibre / deck.gl、活动详情概览 / 复盘合同，以及并行 dirty worktree 文件。

## 3. Expected Work

- 新增 ArcGIS Elevation URL 常量，使用 `Cesium.ArcGISTiledElevationTerrainProvider.fromUrl()` 创建 provider。
- `loadRealTerrainLayerForCurrentTrack()` 保留 `prepare_dem_session_cache(JSON.stringify(appState.points))` 前置调用，再创建 ArcGIS provider。
- provider 创建失败时沿用标准地形回退，不弹确认框。
- 标准地形下 `updateScene()` 保持当前 FIT 海拔夸张高度。
- 真实地形 ready 下 completed / remaining 轨迹使用 `clampToGround` 或等价近地策略，并继续使用 `CallbackProperty` 做进度切片。
- CP、里程、最高点 / 坡顶在真实地形下使用 `HeightReference.RELATIVE_TO_GROUND` 和小高度偏移；标准地形下保持 `HeightReference.NONE`。
- 图层切换后刷新 scene entities，确保 provider 改变后轨迹和 marker 高度策略同步。
- 静态测试锁定 provider、用户触发路径、2D / 3D 解耦、轨迹分段和 marker 高度策略。

## 4. Validation

```bash
.venv312/bin/python -m pytest -q tests/test_track_cesium_dem_contract.py tests/test_track_dem_session_cache.py
test -f tests/test_track_thumbnail_canvas_v4.py && .venv312/bin/python -m pytest -q tests/test_track_thumbnail_canvas_v4.py || true
git diff --check
```

## 5. Completion Definition

- 用户点击真实地形后会先准备 DEM session cache，再创建 ArcGIS Elevation provider。
- 标准地形不变，真实地形失败回退标准地形。
- 真实地形下轨迹分段和 CP / 里程 / 最高点 marker 不丢失。
- 不用 DEM 改写任何活动事实、统计、剖面图、复盘或 AI 输入。
- 聚焦测试和 `git diff --check` 通过。

## 6. Reread Triggers

出现以下任一情况，必须重新全文阅读相关文档或源码：

- 需要新增后端下载器、代理服务、自托管 tile 服务、长期缓存、LRU 或离线包。
- 需要改变 FIT / 手表海拔、活动数据库、统计、剖面图、复盘或 AI 输入。
- 需要删除海拔墙或重写 completed / remaining 分段。
- 需要让 2D / 3D 滑块触发 provider 创建或 DEM 请求。
- 测试失败指向活动事实、API 契约、启动 / 退出生命周期或既有轨迹交互。
