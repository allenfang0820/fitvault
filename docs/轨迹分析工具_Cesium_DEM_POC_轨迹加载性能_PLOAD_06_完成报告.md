# PLOAD-06 自动化性能合同与真实 UI 验收报告

> 日期：2026-08-03
> 开发状态：Completed
> 产品验收：User Manual Acceptance Pending

## 1. 最终实现

### 轨迹加载快照

`getLastTrackLoadPerformance()` 返回最近一次当前 revision 的只读副本：

- `bridgeAndDecodeMs`
- `statsAndMarkersMs`
- `boundsAndMetricsMs`
- `cesiumSceneMs`
- `profileCanvasMs`
- `cpListMs`
- `cameraLaunchMs`
- `synchronousApplyMs`
- `firstScreenReadyMs`
- `firstPostPaintMs`
- `deferredSettledMs`

canonical bridge 只调用一次 `load_activity_track()`，不为计时再次 stringify 完整 response。temporary import 使用 `frontend_only`，bridge 字段保持 `null`。

### 真实地形快照

`getLastTerrainLoadPerformance()` 返回 DEM session、provider metadata / assignment、首批 terrain tile、settle、hillshade setup、marker rebuild 和 total。标准路径不触发真实地形阶段。

## 2. 自动化结果

```text
轨迹专项：212 passed
全仓：3505 passed, 5 skipped, 262 subtests passed
JavaScript syntax: passed
docs/js_api_contract.json: valid
git diff --check: passed
```

全仓 warnings 为既有 `fitparse` / `ast.Str` deprecation，共 `93476` 条，不是本次失败；测试进程 exit code 为 `0`。

统一性能合同覆盖：

- 热循环无逐点 warning。
- canonical 已有距离不重复 fallback haversine。
- peak 检测不再调用 haversine，250m / 300m / 12m 和最高点语义由既有回归覆盖。
- canonical context 不携带 points，temporary context 仍携带 points。
- 首帧后队列受 render revision 保护，初始相机为可中断 `0.8s`。
- 不采用显示几何抽稀。
- 标准路径不等待 DEM，真实地形阶段计时与 listener 清理生效。
- CP、里程、最高点、进度和剖面合同保持。

## 3. 四条真实数据探针

| Activity | 点数 | stats / peak | warning | km / peak | context 缩减 |
| --- | ---: | ---: | ---: | --- | ---: |
| `127` 四姑娘山二峰登顶 | 26,052 | `169.300ms` | 0 | 10 / 1 | `99.992%` |
| `907` 长坪沟至二峰大本营 | 21,690 | `79.000ms` | 0 | 18 / 4 | `99.996%` |
| `1117` 城市跑 | 2,746 | `7.625ms` | 0 | 7 / 1 | `99.958%` |
| `1094` 骑行 | 2,916 | `7.473ms` | 0 | 23 / 2 | `99.960%` |

探针执行生产 `track.html` 当前算法，但不等价于 WebView / GPU / terrain 实测。

## 4. 打包 smoke

- 使用当前 `HikingTrackAnalyzer.spec` 构建成功。
- 构建路径：`/tmp/fitvault-pload06-final2-dist/脉图.app`。
- app 内 `track.html` 与工作区源码 `cmp` 一致。
- 当前最终构建已启动。
- activity `127` 实际看到地图、顶部 `8.34km / 7h14m / 896m / 5337m` 指标、路线、里程 marker 和底部剖面。

PyInstaller 的 Android platform、`pycparser`、`scipy.special._cdflib` hidden-import warning 未阻断 macOS arm64 构建。

## 5. 用户手动验收

用户已明确由其手动测试。以下项目未写成通过：

- activity `127` / `907`、城市跑、山地 / 越野跑、骑行的首屏体感与精确耗时。
- 标准 → 真实、真实 → 标准、失败回退和快速反向切换。
- 2D / 中间 / 3D 视角与相机手感。
- CP 展示 / 新增 / 编辑 / 删除，1 / 5 / 10km，最高点 / 坡顶开关。
- 进度切片、剖面点击定位、图钉清晰度。
- `firstScreenReadyMs` 相对原始 5 秒粗基线是否达到至少 `30%`。

手测时可在 Web Inspector 控制台读取：

```javascript
getLastTrackLoadPerformance()
getLastTerrainLoadPerformance()
```

在用户回填上述结果前，本报告结论为“实现与自动化完成，产品手动验收待完成”。
