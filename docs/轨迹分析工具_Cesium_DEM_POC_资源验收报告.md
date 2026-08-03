# 轨迹分析工具 Cesium DEM POC 资源验收报告

> 日期：2026-07-30
> 任务：CDEM-08 安装包、网络和存储验收
> 范围：Cesium 1.143 本地资源、ArcGIS World Elevation 在线 DEM、DEM 会话临时缓存、失败回退。

## 1. 资源体积

本次测量：

```bash
du -sh lib/Cesium
# 22M	lib/Cesium

find lib/Cesium -type f | wc -l
# 392
```

与 CDEM-00 基线对比：

- CDEM-00：`18M / 375 files`
- CDEM-08：`22M / 392 files`
- 潜在安装包增量：约 `+4M / +17 files`

结论：

- Cesium 升级带来约 4M 本地第三方资源增量。
- DEM 数据本身未进入 `lib/Cesium`，也未作为本地地形包加入安装资源。
- `lib/Cesium` 中出现的 `Terrain` / `Heightmap` 命名文件属于 Cesium 运行时 worker / 内置 metadata，不是下载的 DEM tile 或离线地形包。

## 2. DEM 下载与网络

当前默认在线 provider：

```js
Cesium.ArcGISTiledElevationTerrainProvider.fromUrl(ARCGIS_WORLD_ELEVATION_TERRAIN_URL)
```

ArcGIS World Elevation endpoint 探测：

```bash
curl -L -sS --connect-timeout 5 --max-time 15 -o /tmp/arcgis_terrain_pjson.txt -w 'http_code=%{http_code}\ntime_total=%{time_total}\nremote_ip=%{remote_ip}\nsize=%{size_download}\n' 'https://elevation3d.arcgis.com/arcgis/rest/services/WorldElevation3D/Terrain3D/ImageServer?f=pjson'
# http_code=200
# time_total=0.896565
# remote_ip=184.24.16.46
# size=8074
```

结论：

- 当前机器网络下 ArcGIS World Elevation service metadata 可访问。
- 本轮 POC 不把 ArcGIS 可访问性视为标准地形的前置条件；真实地形失败时回退标准地形。
- 国内网络仍需后续真实用户环境观察；CDEM-08 只确认当前 provider 不需要 ion token，且失败不会阻断标准轨迹分析工具。

## 3. 首次启动与用户触发边界

静态合同：

- `initCesiumViewer()` 默认使用 `terrainProvider: new Cesium.EllipsoidTerrainProvider()`。
- 2D / 3D slider block 不包含 `selectTerrainLayer`、`applyStandardTerrainLayer` 或 `loadRealTerrainLayerForCurrentTrack`。
- 真实地形只在 `terrain-layer-real` 点击后执行 `selectTerrainLayer('real')`。
- `loadRealTerrainLayerForCurrentTrack()` 先调用 `prepare_dem_session_cache(JSON.stringify(appState.points))`，再创建 ArcGIS terrain provider。

结论：

- 首次启动不下载 DEM。
- 2D / 3D 切换不触发 DEM。
- 只有用户主动选择 `真实地形` 才进入 DEM 准备和 provider 创建路径。

## 4. 本地存储生命周期

当前缓存 root：

```text
~/.fitvault/cache/dem-session/
```

实现边界：

- `DemSessionCache.__init__()` 只清理旧 `session_*`，不创建当前 session 目录。
- `prepare_route_bbox()` 只在用户选择真实地形后创建当前 session 目录，并写入 `route-bbox.json`。
- `main()` 的 `finally` 调用 `api.cleanup_dem_session_cache()`。
- `cleanup_dem_session_cache()` 删除当前 session 目录。

自动化覆盖：

```bash
.venv312/bin/python -m pytest -q tests/test_track_dem_session_cache.py tests/test_track_cesium_dem_contract.py
# 19 passed
```

覆盖点：

- 启动清理旧 `session_*`，但不创建当前 session 目录。
- 用户动作后才创建当前 session，并按路线 bbox 写入元数据。
- 清理当前 session 不误删其他 session。
- `prepare_dem_session_cache()` 使用统一响应，且不写活动数据库路径。
- 无效路线不会创建 session 目录。
- pywebview 退出时调用 `cleanup_dem_session_cache()`。

结论：

- DEM 会话缓存不会随使用长期累积。
- 当前实现不写活动数据库、轨迹数据库或运动记录事实字段。
- 本轮仅写当前 session 的路线 bbox 元数据；实际 DEM tile 由 Cesium provider 在线请求，不落为长期离线地形包。

## 5. 失败回退

静态合同：

- `selectTerrainLayer('real')` 捕获 provider 创建失败。
- 失败时执行 `applyStandardTerrainLayer('真实地形暂不可用')`。
- `applyStandardTerrainLayer()` 恢复 `new Cesium.EllipsoidTerrainProvider()` 并刷新场景。

结论：

- ArcGIS 网络失败、Cesium provider 不可用或 DEM cache 预备失败，均不会阻断标准地形轨迹分析工具。
- 用户仍可继续使用轨迹、CP、里程点、最高点 / 坡顶、进度滑块、底部剖面图和 2D / 3D 相机。

## 6. 未自动化手测项

仍建议在桌面 UI 中使用真实活动点检：

- 首次打开轨迹分析工具，网络面板或日志确认没有 DEM 请求。
- 加载城市跑、山地 / 越野跑、骑行爬坡各一条轨迹后点击 `真实地形`。
- 断网或阻断 ArcGIS 后点击 `真实地形`，确认回退标准地形且轨迹分析仍可用。
- 退出程序后确认当前 `session_*` 目录被删除。

## 7. CDEM-08 结论

CDEM-08 验收通过：

- Cesium 升级资源增量有记录：约 `+4M / +17 files`。
- DEM 不进入安装包，不默认下载。
- DEM 只在用户选择真实地形后进入在线 provider 路径。
- DEM session cache 是会话临时缓存，退出清理、启动清理残留。
- 网络失败可回退标准地形，不阻断轨迹分析工具。
