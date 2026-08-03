# 轨迹分析工具 Cesium DEM POC 开发完成报告

> 日期：2026-07-30
> 任务：CDEM-09 POC 总验收与交付报告
> 范围：Cesium 1.143 升级、真实 DEM 地形图层、DEM 会话临时缓存、海拔墙退役、既有轨迹分析交互保留。

## 1. 总结论

本次 Cesium DEM POC 的自动化总验收通过。

已完成：

- Cesium 本地资源升级到 `cesium@1.143.0` 方向。
- Viewer 初始化兼容 Cesium 1.143，标准地形仍可无 DEM 运行。
- 新增独立 `图层 / 标准地形 / 真实地形` 控制，2D / 3D slider 继续只控制相机。
- 接入 ArcGIS World Elevation 作为在线真实地形 POC provider。
- DEM 不进入安装包，不默认下载；用户点击 `真实地形` 后才准备 session cache 并创建 provider。
- DEM session cache 使用会话临时目录，启动清理旧 session，退出清理当前 session。
- 海拔墙彻底退役，不保留用户入口、内部调试开关或隐藏兼容。
- CP、里程、最高点 / 坡顶、进度切片、底部剖面、2D / 3D、归北、自动旋转和活动详情缩略图跳转的自动化合同保持通过。
- 追加修复 macOS WebView / ANGLE / Metal 下 Cesium 大气散射 shader 链接失败：禁用 sky atmosphere、ground atmosphere、fog、sun lighting 路径，保留地图主体、轨迹和 DEM。

未完成 / 不包装为通过：

- 城市跑、山地 / 越野跑、骑行爬坡三类真实轨迹桌面 UI 手测尚未执行。
- 断网或阻断 ArcGIS 后的真实 UI 回退点检尚未执行。

交付判断：

- 自动化门禁与静态合同已满足进入真实 UI smoke 的条件。
- 正式发布前仍需完成三类真实轨迹和网络失败回退的人工点检。

## 2. CDEM-00 到 CDEM-08 汇总

| 任务 | 结果 | 关键产物 / 结论 |
| --- | --- | --- |
| CDEM-00 基线审计与合同冻结 | Completed | 冻结 Cesium、海拔墙、CP、里程、坡顶、进度、剖面和相机基线。 |
| CDEM-01 Cesium 1.143 本地资源升级 | Completed | `lib/Cesium` 升级为 `22M / 392 files`，fallback 统一到 `cesium@1.143.0`。 |
| CDEM-02 Viewer 初始化兼容 | Completed | Viewer 改用 `baseLayer: new Cesium.ImageryLayer(...)`，标准地形保持 `EllipsoidTerrainProvider`。 |
| CDEM-03 地形图层开关 | Completed | 新增独立标准地形 / 真实地形状态机，和 2D / 3D slider 解耦。 |
| CDEM-04 DEM 会话临时缓存 | Completed | 新增 `DemSessionCache`，用户动作后才写 `route-bbox.json`，退出清理。 |
| CDEM-05 真实地形轨迹贴合 | Completed | ArcGIS World Elevation provider、真实地形贴地轨迹、marker 高度策略完成。 |
| CDEM-06 海拔墙彻底退役 | Completed | `wallEntity`、wall heights、海拔墙文案和活跃 wall entity 删除。 |
| CDEM-07 既有分析交互回归 | Completed | 完整回归组 `161 passed`，CP / 里程 / 坡顶 / 进度 / 剖面 / 相机 / 缩略图跳转合同通过。 |
| CDEM-08 安装包、网络和存储验收 | Completed | Cesium 约 `+4M / +17 files`；ArcGIS metadata HTTP `200`；DEM 不默认下载、不长期缓存。 |

## 3. 最终自动化验证

最终回归组：

```bash
.venv312/bin/python -m pytest -q tests/test_track_cesium_dem_contract.py tests/test_track_dem_session_cache.py tests/test_track_html_sync_logic.py tests/test_track_thumbnail_canvas_v4.py tests/test_v9_0_detail_tab_review.py
# 165 passed
```

Whitespace：

```bash
git diff --check
# passed
```

海拔墙残留：

```bash
rg -n "wallEntity|elevation wall|海拔墙|海拔剖面堆积墙|wall\\.wall|Cesium\\.Wall" track.html tests/test_track_cesium_dem_contract.py tests/test_track_dem_session_cache.py tests/test_track_thumbnail_canvas_v4.py tests/test_track_html_sync_logic.py tests/test_v9_0_detail_tab_review.py
# no matches
```

## 4. 交互回归结论

自动化 / 静态合同通过：

- CP 点展示、新增、编辑、删除和侧栏列表。
- 里程点展示和开关。
- 最高点 / 坡顶标记展示和开关。
- 进度滑块与 completed / remaining 轨迹切片。
- 底部半透明海拔剖面图和点击新增 CP 联动。
- 2D / 3D slider、`lookAtTransform(Cesium.Matrix4.IDENTITY)` 释放链路。
- 指南针 / 归北和自动旋转入口。
- 活动详情页轨迹缩略图跳转轨迹分析工具。
- macOS WebView shader 兼容层：`createCesiumWebviewCompatibleGlobe()` 在首帧前关闭 Globe 大气 / 光照 / 阴影 / 水面路径，Viewer 构造时关闭 OIT、阴影、MSAA 和 render-loop error modal，`applyCesiumWebviewShaderCompatibility()` 在初始化后再次关闭 HDR、sunBloom、FXAA/post-process、大气、fog、sun/moon 和 shadowMap 路径，避免 `_computeAtmosphereScattering` 链接失败。
- 真实地形 marker 可读性修复：CP 在真实地形下不再 point + billboard 双重绘制，CP / 最高点 / 坡顶使用运行时 canvas 生成的 retina PNG billboard，不再使用 SVG text / SVG filter / emoji 贴图；里程点按距离分层显示，最高点优先于普通坡顶显示，所有 marker 使用有限 depth-test 穿透距离降低远景堆叠。
- 真实地形 3D 观感增强：真实地形切换后等待 terrain tiles 稳定，并应用只作用于 Cesium scene 的 vertical exaggeration 和 ArcGIS `World_Shaded_Relief` 半透明 hillshade imagery overlay；图层切换保持用户当前相机与 2D / 3D slider 状态，不自动重新 framing；该增强不恢复动态光照 / 阴影 shader，不改变 FIT / 手表海拔事实、统计、底部剖面、复盘、AI 或 DB。

真实 UI 待手测：

- 城市跑：标准地形 / 真实地形、CP、里程、最高点、进度、剖面、相机。
- 山地 / 越野跑：真实地形贴合、坡顶 / 最高点、剖面与地图视觉分层。
- 骑行爬坡：长距离 / 爬升线路下真实地形加载、进度拖动、marker 可读性。
- 真实地形 marker smoke：远景 CP 标签不糊成文字带，1km / 5km / 10km 里程层级随距离变化，最高点在远景仍可识别，普通坡顶近景可用。
- hillshade smoke：真实地形打开后山体明暗层次可见，ArcGIS shaded relief 网络不可用时不阻断 DEM 和标准地形回退。

## 5. 海拔与地形事实边界

保持不变：

- FIT / 手表海拔继续是活动事实源。
- 底部剖面图继续使用记录海拔。
- 累计爬升、最高海拔、复盘和 AI 输入未改为 DEM 高程。
- DEM 只作为地图环境显示，不写数据库，不修正轨迹事实。

海拔墙：

- 已退役。
- 无用户入口。
- 无内部调试开关。
- 无活跃 wall entity。
- 底部剖面图是唯一海拔剖面表达。

## 6. 资源、网络和存储

资源：

- CDEM-00 基线：`18M / 375 files`
- CDEM-08 当前：`22M / 392 files`
- 潜在安装包增量：约 `+4M / +17 files`

网络：

- ArcGIS World Elevation metadata 当前探测：HTTP `200`，耗时约 `0.896565s`，下载 `8074` bytes。
- 本轮 provider 不需要 Cesium ion token。
- 国内真实用户网络仍需继续观察。

存储：

- DEM 不进入安装包。
- 首次启动不下载 DEM。
- 2D / 3D slider 不下载 DEM。
- 只有用户点击 `真实地形` 才准备 DEM session cache 和创建 online provider。
- session cache 位于 `~/.fitvault/cache/dem-session/session_*`。
- 当前任务只写当前路线 `route-bbox.json` 元数据。
- 程序退出清理当前 session，启动清理旧 session 残留。

失败回退：

- 真实地形失败时回退 `EllipsoidTerrainProvider`。
- 标准地形轨迹分析工具不依赖 ArcGIS 成功。

## 7. 剩余风险

- ArcGIS World Elevation 在不同地区、网络运营商或企业网络下可用性可能波动。
- Cesium terrain tile 的真实加载体验需要桌面 UI 和真实路线验证；metadata HTTP 200 只能证明服务入口当前可达。
- 真实地形下 CP / 里程 / 最高点的视觉高度虽然有合同保护，仍需在山地路线中观察可读性。
- 当前真实地形观感增强使用 Cesium `verticalExaggeration` 和 ArcGIS hillshade imagery overlay，虽不进入活动事实，但仍需在 macOS WebView 下确认不会引发新的 terrain shader 或网络体验问题。
- 当前 DEM cache 主要是会话元数据边界；实际 terrain tile 缓存行为由 Cesium runtime / 浏览器缓存决定，需在打包环境继续观察。
- 大气渲染已为 macOS WebView 兼容性关闭；这会减少天空 / 地表大气视觉效果，但优先保证轨迹分析工具可渲染。

## 8. 后续建议

发布前必须补齐：

- 城市跑、山地 / 越野跑、骑行爬坡三条真实轨迹桌面 UI 点检。
- ArcGIS 可用和不可用两种网络状态下真实地形按钮行为。
- 退出程序后 `~/.fitvault/cache/dem-session/session_*` 当前目录清理确认。

可进入后续正式开发的条件：

- 上述真实 UI smoke 通过。
- 不出现活动事实被 DEM 改写的问题。
- 不出现 DEM cache 长期累积。
- 不出现真实地形失败阻断标准轨迹分析工具。

中期仍独立处理：

- MapLibre + deck.gl `路线诊断` 不属于本 POC。
- 长期 DEM 缓存、离线包、自托管或服务商终局选型不属于本 POC。
