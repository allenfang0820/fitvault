# 轨迹分析工具轨迹加载性能 PLOAD-00 基线报告

> 日期：2026-08-03
> 任务：CDEM-14 / PLOAD-00
> 状态：Completed
> 探针：`scripts/profile_track_load.py`

## 1. 结论摘要

PLOAD-00 已确认至少两个高优先级热点：

1. 当前 `track.html` 的 canonical stats / peak 路径在高密度轨迹上执行大量 `haversine()`，且每次调用都会执行 `console.warn()`。
2. canonical activity 加载完成后，`sync_track_context()` 仍会再次对完整 points 执行 JSON 序列化并跨 pywebview bridge 发送。

固定 `2.5s` `flyTo`、全量 Cartesian3 构建和真实 DEM 网络阶段已确认存在于当前链路，但本地探针不能代表 WebKit / Cesium GPU / 网络耗时，保留为后续分段测量项。

## 2. 样本结果

命令：

```bash
.venv312/bin/python scripts/profile_track_load.py --activity-id 127 --activity-id 907
```

| activity | 点数 | response bytes | backend load | Python JSON encode | frontend stats / peak | `haversine` warning calls | stringify |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `127` 四姑娘山二峰登顶 | `26,052` | `9,240,410` | `70.536ms` | `48.153ms` | `536.802ms` | `21,140,328` | `17.897ms` |
| `907` 长坪沟到二峰大本营 | `21,690` | `7,783,128` | `48.165ms` | `42.371ms` | `220.093ms` | `8,764,412` | `16.717ms` |

说明：Node 探针将 `console.warn` 替换为计数器，以避免基线运行本身被终端 I/O 淹没；实际 WebView 控制台输出可能更慢。`frontend stats / peak` 执行的是当前 `track.html` 函数源码，不是复制的替代算法。

## 3. 静态链路证据

- `applyDataAndRender()` 同步调用 stats、`updateScene()`、图表、报告和列表渲染。
- 当前存在固定 `duration: 2.5` 的 `camera.flyTo()`。
- 当前 `updateScene()` 对每个原始 point 创建 `Cesium.Cartesian3` 并填充 `appState.fullPositions`。
- 当前 canonical `sync_track_context` payload 包含 `points: appState.points`。
- 当前 `haversine()` 包含逐次 `console.warn('[DEPRECATED] ...')`。

## 4. DMG / 网络边界

- 已启动打包产物 `/Users/fanglei/应用开发/AI track/dist/v2.0-arm64/脉图.app`，进入轨迹分析工具页面成功。
- 用户已在打包 DMG 中观察到四姑娘山登顶活动加载约 5 秒以上；本报告将其作为真实 DMG 的粗粒度用户观测，不作为精确分段计时。
- 本轮未能在打包 UI 中定位并独立计时 activity `127` 的各阶段，因此 WebView bridge、Cesium GPU、首次 imagery、DEM provider、terrain tile settle 和 hillshade 请求仍标为待测。
- 标准地形不应等待 DEM；真实地形额外 provider / tile / hillshade 成本归 PLOAD-05。

## 5. PLOAD-01 输入与建议

- 第一优先级删除或一次性化 `haversine()` 热循环中的 `console.warn()`。
- canonical points 已有有效 `dist_km` 时跳过 fallback haversine 计算。
- 将峰顶检测改为线性 / 有界窗口，同时逐路线回归 marker 数量、最高点、普通坡顶位置和 300 米语义。
- 修复前后重复运行本探针，并补充 CDEM / marker 功能回归；只有测试全绿才能进入 PLOAD-02。

## 6. 未完成项

- pywebview bridge 往返精确耗时。
- WebKit / Cesium `updateScene()` 与首次绘制耗时。
- 标准 / 真实地形网络与 tile settle 分段耗时。
- Retina / 非 Retina 和不同窗口尺寸下的真实 UI 性能。
