# CDEM-00 基线审计报告

> 日期：2026-07-30
> 范围：轨迹分析工具 Cesium / DEM POC 执行前基线。
> 结论：当前任务只冻结基线，不修改生产行为。

## 1. 审计依据

- `README.md`
- `docs/archive/ARCHITECTURE.md`
- `docs/DIR_SPEC.md`
- `docs/field_contract_matrix.md`
- `docs/js_api_contract.json`
- `docs/脉图运动复盘系统_开发团队交付手册_v1.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_开发交付手册.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_开发任务清单.md`
- `track.html`
- `lib/Cesium`

## 2. 资源基线

```text
du -sh lib/Cesium
18M     lib/Cesium

find lib/Cesium -type f | wc -l
375
```

当前 `lib/Cesium` 顶层结构：

```text
Assets/
ThirdParty/
Widgets/
Workers/
Cesium.js
index.cjs
index.js
```

## 3. Cesium 初始化基线

CDEM-00 升级前 `track.html` 锚点：

- `window.CESIUM_BASE_URL = 'lib/Cesium/'`
- `lib/Cesium/Widgets/widgets.css`
- CSS fallback 指向 `https://cdn.jsdelivr.net/npm/cesium@1.105.1/Build/Cesium/Widgets/widgets.css`
- 脚本 fallback 指向 `https://cdn.jsdelivr.net/npm/cesium@1.105.1/Build/Cesium/Cesium.js`
- `initCesiumViewer()`
- `new Cesium.Viewer('cesiumContainer', ...)`
- `new Cesium.UrlTemplateImageryProvider(...)` 使用 CARTO Voyager 栅格底图。
- `new Cesium.EllipsoidTerrainProvider()` 作为当前标准地形。
- `viewer.scene.globe.depthTestAgainstTerrain = true`
- `setupViewerInteractions()`

后续 CDEM-01 / CDEM-02 风险：

- 本地 Cesium 升级后，CSS / script fallback 不得继续混用旧版 `1.105.1`。
- 必须确认 `Assets`、`Widgets`、`Workers` 和 `ThirdParty/Workers` 路径仍被 `window.CESIUM_BASE_URL` 正确解析。
- viewer 初始化参数必须在 Cesium 1.143 下兼容。

CDEM-01 升级后记录：

```text
npm package: cesium@1.143.0
source: official npm package Build/Cesium
package Build/Cesium size: 22M
package Build/Cesium files: 392

before lib/Cesium size: 18M
before lib/Cesium files: 375
after lib/Cesium size: 22M
after lib/Cesium files: 392
estimated local resource delta: +4M, +17 files
```

`track.html` 的 CSS / script CDN fallback 已统一更新到 `cesium@1.143.0`，不再混用旧版 `1.105.1`。

官方 Cesium 构建产物包含嵌入式二进制 / shader 文本片段，会触发 `git diff --check` 的 whitespace 噪声。CDEM-01 新增 `.gitattributes`：

```text
lib/Cesium/** -whitespace
```

该设置仅作用于第三方 Cesium 构建资源，不影响业务源码 whitespace 检查。

CDEM-01 验证已执行并通过：

```text
du -sh lib/Cesium
22M     lib/Cesium

find lib/Cesium -type f | wc -l
392

.venv312/bin/python -m pytest -q tests/test_track_cesium_dem_contract.py
11 passed in 0.04s

git diff --check
passed
```

CDEM-01 差异审查结论：

- `lib/Cesium/**` 已替换为官方 `cesium@1.143.0` 的 `Build/Cesium` 产物，并保留本地 `Cesium.js`、`index.cjs`、`index.js`、`Assets/`、`Widgets/`、`Workers/`。
- `track.html` 中 CDEM-01 仅将 Cesium CSS / script fallback 更新到 `1.143.0`；文件内其它既有 dirty diff 属于并行工作，未在本任务回退或整理。
- `.gitattributes` 仅为 `lib/Cesium/**` 设置 `-whitespace`，用于第三方构建产物门禁，业务源码仍保持默认 whitespace 检查。
- 本任务未接入 DEM provider，未修改 viewer 初始化语义，未删除海拔墙，未修改轨迹渲染和活动事实。

CDEM-02 Viewer 初始化兼容记录：

- Cesium 1.143 `Viewer` 源码核对确认：`options.imageryProvider` 仍被读取，但只用于关闭默认底图，不会自动加入 `scene.imageryLayers`。
- `track.html::initCesiumViewer()` 已改为先创建 `standardBaseLayer = new Cesium.ImageryLayer(new Cesium.UrlTemplateImageryProvider(...))`，再传入 `baseLayer: standardBaseLayer`。
- `terrainProvider: new Cesium.EllipsoidTerrainProvider()` 保持不变，标准地形仍是无 DEM fallback。
- `setupViewerInteractions()`、相机 `changed` 监听、指南针同步、`requestSceneRender()`、2D / 3D 滑块 `lookAtTransform(Cesium.Matrix4.IDENTITY)` 释放链路保持不变。
- 本任务未接入 DEM provider，未删除海拔墙，未修改轨迹 entity、CP、里程、坡顶、进度切片、底部剖面图和活动事实。
- CDEM-02 验证已执行并通过：

```text
node -e "const Cesium=require('./lib/Cesium/index.cjs'); ..."
VERSION: 1.143.0
Viewer: function
ImageryLayer: function
UrlTemplateImageryProvider: function
EllipsoidTerrainProvider: function
Matrix4Identity: true

.venv312/bin/python -m pytest -q tests/test_track_cesium_dem_contract.py
11 passed in 0.07s

git diff --check
passed
```

CDEM-03 地形图层控制记录：

- `track.html` 顶栏新增 `图层` 控件，包含 `标准地形` 和 `真实地形`。
- `appState` 新增 `terrainLayerMode`、`terrainLayerStatus` 和 `terrainLayerMessage`；默认值为 `standard / idle`。
- `applyStandardTerrainLayer()` 只将 `viewer.scene.terrainProvider` 设为 `new Cesium.EllipsoidTerrainProvider()`。
- `selectTerrainLayer('real')` 先进入 loading；CDEM-04 尚未接入 provider 时，`loadRealTerrainLayerForCurrentTrack()` 受控失败并回退标准地形。
- 图层控件与 2D / 3D 滑块事件独立，测试锁定滑块不会调用地形图层函数。
- 本任务没有 `CesiumTerrainProvider`、`sampleTerrain`、DEM 下载、缓存、后端 API、数据库写入或活动事实改写。
- CDEM-03 验证已执行并通过：

```text
.venv312/bin/python -m pytest -q tests/test_track_cesium_dem_contract.py
12 passed in 0.06s

git diff --check
passed
```

CDEM-04 DEM 会话临时缓存记录：

- `main.py` 新增 `DemSessionCache`，会话根目录为 `~/.fitvault/cache/dem-session/`，不使用活动数据库、`workspace/tracks` 或安装包目录。
- 应用创建 `Api` 时仅扫除旧 `session_*` 残留，若不存在缓存根目录则不创建；当前 session 目录只在 `prepare_dem_session_cache(points_json)` 成功验证当前路线 GPS bbox 后创建。
- bbox 以当前有效 GPS 经纬度为边界并固定外扩 `1500m`，当前任务只写入 `route-bbox.json` 预备元数据，不下载 DEM、不接入 Cesium terrain provider。
- `Api._session_id` 会因轨迹 / AI 流程刷新，因此 DEM 使用独立进程级 session id；`main()` 退出 `finally` 调用 `cleanup_dem_session_cache()` 删除当前目录。
- `track.html::loadRealTerrainLayerForCurrentTrack()` 只在用户点击真实地形后调用该桥接；缓存预备成功后仍受控回退标准地形，provider / 贴地轨迹留给 CDEM-05。
- 新增 `tests/test_track_dem_session_cache.py`，覆盖旧 session 清扫、无用户操作不创建当前目录、bbox 缓冲、当前 session 清理、统一 API 信封和主程序退出清理。

CDEM-04 验证已执行并通过：

```text
.venv312/bin/python -m pytest -q tests/test_track_dem_session_cache.py tests/test_track_cesium_dem_contract.py
18 passed in 0.14s

jq empty docs/js_api_contract.json
passed

git diff --check
passed
```

CDEM-05 真实地形轨迹贴合记录：

- `track.html` 新增 ArcGIS World Elevation provider URL：`https://elevation3d.arcgis.com/arcgis/rest/services/WorldElevation3D/Terrain3D/ImageServer`。
- `loadRealTerrainLayerForCurrentTrack()` 只在用户点击真实地形后执行，先调用 `prepare_dem_session_cache(JSON.stringify(appState.points))`，再使用 `Cesium.ArcGISTiledElevationTerrainProvider.fromUrl(...)` 创建 provider。
- `applyStandardTerrainLayer()` 和真实地形 ready 后均调用 `refreshTerrainSensitiveScene()`，确保 provider 切换后轨迹和 marker 高度策略同步。
- `updateScene()` 在真实地形 ready 时对 completed / remaining polyline 设置 `clampToGround: useRealTerrain`，同时保留 `CallbackProperty` 与 `appState.progress` 切片。
- CP、里程点、最高点 / 坡顶在真实地形下使用 `Cesium.HeightReference.RELATIVE_TO_GROUND` 和小高度偏移；标准地形下仍使用 FIT 海拔夸张高度。
- 海拔墙未删除，但真实地形 ready 时不显示；CDEM-06 仍负责彻底退役 wall entity、状态和测试断言。
- 未改写 FIT 海拔、活动数据库、累计爬升、最高海拔、底部剖面图、复盘或 AI 输入。

CDEM-05 验证已执行并通过：

```text
.venv312/bin/python -m pytest -q tests/test_track_cesium_dem_contract.py tests/test_track_dem_session_cache.py
19 passed in 0.18s

.venv312/bin/python -m pytest -q tests/test_track_thumbnail_canvas_v4.py
32 passed in 0.06s

git diff --check
passed
```

CDEM-06 海拔墙退役记录：

- `track.html` 已删除海拔墙活跃实现：`wallEntity` 状态、点击命中、旧 entity remove / add、`wallColor`、`fullMaxHeights`、`fullMinHeights`、`maximumHeights` / `minimumHeights`。
- `appState.fullPositions` 保留，completed / remaining 轨迹仍使用 `Cesium.CallbackProperty` 和 `appState.progress` 维护进度切片。
- 底部半透明剖面图继续通过 `drawProfileChart()` 消费 FIT / 手表记录海拔；`profile-canvas` 点击新增 CP 联动保留。
- CP、里程点、最高点 / 坡顶、2D / 3D 滑块、ArcGIS Elevation provider 和 DEM session cache 保持存在。
- CDEM-06 grep 验收无 `wallEntity`、`elevation wall`、`海拔墙`、`海拔剖面堆积墙`、`wall.wall`、`Cesium.Wall` 残留。

CDEM-06 验证已执行并通过：

```text
rg -n "wallEntity|elevation wall|海拔墙|海拔剖面堆积墙|wall\\.wall|Cesium\\.Wall" track.html tests
no matches

.venv312/bin/python -m pytest -q tests/test_track_cesium_dem_contract.py tests/test_track_dem_session_cache.py tests/test_track_thumbnail_canvas_v4.py
51 passed in 0.21s

git diff --check
passed
```

## 4. 海拔墙当前实现与删除目标

当前活跃实现位于 `track.html`：

- `appState.wallEntity`
- 点击识别里将 `entityName === '海拔剖面堆积墙'` 作为轨迹命中。
- `updateScene()` 中删除旧 `wallEntity`。
- `TRACK_VISUAL_STYLE.wallColor`
- `viewer.entities.add({ name: '海拔剖面堆积墙', wall: ... })`
- wall 使用 `appState.fullPositions`、`appState.fullMaxHeights`、`appState.fullMinHeights` 和 `Cesium.CallbackProperty`。

后续 CDEM-06 删除目标：

- 删除 `appState.wallEntity` 状态。
- 删除点击识别中的 `海拔剖面堆积墙`。
- 删除 `updateScene()` 中 wall entity 的 remove / add 逻辑。
- 删除 `TRACK_VISUAL_STYLE.wallColor`。
- 保留 `fullPositions`，因为 remaining / completed track 仍使用它。
- 删除或重构 `fullMaxHeights` / `fullMinHeights` 前必须确认没有影响进度切片和底部剖面图。

## 5. 必须保留的交互锚点

### 5.1 顶部工具栏

- `#map-compass-btn`：归北 / 指南针入口。
- `#map-view-slider`：2D / 3D 视角滑块。
- `#btn-auto-rotate`：地图漫游入口。
- `triggerTrackImport()`：导入轨迹。
- `setViewProfile()`：剖面视角。
- `exportGPX()`：导出轨迹。
- `#toggle-cp`：CP 点开关。
- `#toggle-km`：里程点开关。
- `#toggle-peak`：坡顶 / 最高点开关。
- `#progress-slider`：轨迹进度滑块。

### 5.2 底部剖面图

- `#profile-container`
- `#profile-canvas`
- `drawProfileChart()`
- `profile-canvas` click 通过距离轴寻找 nearest point 并调用 `openAddModal(...)`。

### 5.3 CP 点能力

- `renderCpMapLayer(exaggeration)`
- `refreshCpViews()`
- `openEditModal(id, currentName)`
- `openAddModal(lon, lat, alt)`
- `saveCp()`
- `deleteCp()`
- `deleteCpFromList(cpId)`
- `syncPlacemarksToBackend()`
- CP entity id 使用 `cp_` 前缀时点击进入编辑。

### 5.4 轨迹语义分段

- `appState.remainingTrackEntity`
- `appState.completedTrackEntity`
- `name: '未完成轨迹'`
- `name: '已完成轨迹'`
- 两段 polyline 均使用 `Cesium.CallbackProperty` 基于 `appState.progress` 切片。

### 5.5 里程与坡顶 / 最高点

- `appState.kmMarkers`
- `appState.peakMarkers`
- `appState.kmEntities`
- `appState.peakEntities`
- `showKM`
- `showPeak`
- `peak.isHighest`

### 5.6 相机控制

- `updateCamera(headingDeg, pitchDeg)`
- `setViewProfile()`
- `getCameraFocusPoint()`
- `resetMapNorth()`
- `claimCameraOwnership()` / `releaseCameraOwnership()`
- `resetCameraTransformSafely()`
- `viewer.camera.lookAtTransform(Cesium.Matrix4.IDENTITY)`
- `beginMapViewSliderDrag(event)` / `endMapViewSliderDrag()`
- `map-view-slider` input 使用 `viewer.camera.lookAt(...)`，结束时释放 transform。

## 6. 本轮明确非目标

- 不做 MapLibre + deck.gl 2D 路线诊断页。
- 不在 CDEM-00 升级 Cesium。
- 不在 CDEM-00 新增 DEM provider。
- 不在 CDEM-00 删除海拔墙。
- 不修改 FIT / GPX 解析语义。
- 不修改活动详情页概览 / 复盘合同。
- 不修改疲劳复盘算法、AI prompt 或数据库事实字段。

## 7. CDEM-00 验证结论

本报告配套 `tests/test_track_cesium_dem_contract.py`。该测试在 CDEM-00 阶段确认当前基线存在；后续任务应按任务目标更新测试断言，例如：

- CDEM-01：更新 Cesium 版本与 fallback 断言。
- CDEM-03：新增地形图层状态机断言。
- CDEM-04：新增 DEM session cache API / 生命周期断言。
- CDEM-06：将海拔墙存在断言改为不存在断言。

本任务已执行并通过：

```text
du -sh lib/Cesium
18M     lib/Cesium

find lib/Cesium -type f | wc -l
375

.venv312/bin/python -m pytest -q tests/test_track_cesium_dem_contract.py
10 passed in 0.04s

git diff --check
passed
```

轻量 diff 审查结论：

- 本任务未修改 `track.html` 生产行为。
- 本任务未修改 `lib/Cesium/**`。
- 本任务未触碰 FIT / GPX 解析、活动数据库、复盘算法、AI prompt 或 MapLibre / deck.gl 实现。
- 新增静态测试只冻结当前轨迹分析页基线，后续任务可按交付目标更新断言。
