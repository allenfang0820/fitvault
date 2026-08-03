# PLOAD-05 真实 DEM 加载性能隔离完成报告

> 日期：2026-08-03
> 状态：Completed

## 1. 标准路径

用户未选择真实地形时，轨迹加载继续使用 `EllipsoidTerrainProvider`，不调用：

- `prepare_dem_session_cache()`
- `ArcGISTiledElevationTerrainProvider.fromUrl()`
- `waitForRealTerrainTiles()`
- `applyRealTerrainVisualMode()` / hillshade overlay

用户切回标准地形时只记录标准 scene / marker 重建和总耗时，不等待 DEM 网络。

## 2. 真实地形阶段记录

最近一次完成记录保存在 `appState.lastTerrainLoadPerformance`，并可通过 `getLastTerrainLoadPerformance()` 获取副本。字段包括：

| 字段 | 含义 |
| --- | --- |
| `demSessionPrepareMs` | 当前路线 bbox 会话准备及 bridge 往返 |
| `providerMetadataMs` | ArcGIS terrain provider metadata 创建 |
| `providerAssignMs` | provider 赋值到 Cesium scene |
| `observedPendingTerrainTiles` | 是否观察到 pending terrain tile |
| `firstTerrainTileMs` | 观察到 pending 后首次归零；未观察到则为 `null` |
| `tilesSettled` / `tilesSettledMs` | `tilesLoaded` 连续稳定帧结果与耗时 |
| `hillshadeSetupMs` | hillshade provider / imagery layer 同步建立时间 |
| `markerRebuildMs` | terrain-sensitive route / marker entity 重建 |
| `totalMs` | 用户动作到 ready / failed 的总耗时 |
| `stage` / `error` | 完成或失败阶段与错误 |

记录只在单次切换结束时保存，不在 tile、postRender、points 或 marker 热循环内输出 console。

## 3. 有界等待

`waitForRealTerrainTiles()` 同时监听 `tileLoadProgressEvent` 和 `postRender`：

- 成功稳定后释放两个 listener 并清理 timeout。
- 到达 `1200ms` 上限时也释放 listener。
- 未出现 pending tile 时不会伪造 `firstTerrainTileMs`。
- Node 运行测试验证 pending `4 → 0`、三帧稳定后得到首批 tile `80ms`、settle `110ms`，且两个 listener 均释放。

## 4. 网络探针

2026-08-03 当前开发网络：

```text
terrain metadata: HTTP 200, 0.649852s, 8074 bytes
hillshade z0 tile: HTTP 200, 1.224852s, 18588 bytes
```

这些结果只证明当前网络可达。`hillshadeSetupMs` 是同步 layer 建立时间，不等价于 hillshade tile 网络完成；真实 Cesium / WebView tile 与视觉 settle 留到 PLOAD-06。

## 5. 回归与审查

```text
32 passed
node --check: passed
activity 127 / 907 probe: passed
git diff --check: passed
```

首轮测试因旧函数签名断言失败，已仅更新直接相关静态合同后通过。完整 diff 审查确认 provider URL、DEM cache 生命周期、相机、vertical exaggeration、hillshade 参数、marker 视觉和活动事实未改变。
