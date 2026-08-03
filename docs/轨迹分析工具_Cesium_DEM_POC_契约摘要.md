# 轨迹分析工具 Cesium DEM POC 契约摘要

> 刷新时间：2026-08-03
> 当前任务：CDEM-14 / PLOAD-06 自动化性能合同与真实 UI 验收
> 来源：项目总契约、开发交付手册、开发任务清单、基线审计报告、CDEM-07 / CDEM-08 完成记录、`main.py` / `track.html` 当前实现。

## 1. 总体工程契约

- 脉图是本地优先的单用户运动数据工具，不能引入会破坏本地优先、轻量化和可解释性的重型平台化架构。
- FIT / 手表记录是活动事实源。前端、AI、地图底图、DEM 均不能改写原始活动事实、数据库事实字段或后端权威快照。
- UI 展示字段必须能追溯到后端 / DB / Resolver / FIT SDK；本次地图显示改造不得绕过后端事实源重算活动统计。
- 前端可以做展示层交互，但不得把 DOM、Cesium entity、剖面图、轨迹点或 DEM 高程推导为复盘、AI、累计爬升、最高海拔等事实。
- 工作区可能存在并行改动；执行任务时不得 stash、reset、覆盖或格式化无关文件。

## 2. 本轮 POC 产品边界

- 短期目标是 Cesium 升级、真实 DEM 地形图层 POC、DEM 会话临时缓存、海拔墙彻底退役。
- MapLibre + deck.gl 2D 路线诊断是中期目标，本轮不做。
- 现有 2D / 3D 滑块只控制相机视角，不触发 DEM 下载，不切换 terrain provider。
- 真实 DEM 是独立图层，由用户主动选择；默认标准地形，不弹确认框。
- DEM 不进入安装包，不默认下载，不写入活动数据库；本轮只做会话临时缓存，退出清理，启动清理异常残留。
- 海拔墙已在 CDEM-06 彻底退役，不保留用户入口、内部调试开关、隐藏兼容或活跃 entity。

## 3. 海拔与地形分层

- FIT / 手表海拔继续用于底部半透明海拔剖面图、累计爬升、最高海拔、复盘和 AI 事实输入。
- DEM 高程只用于地图环境显示。
- 本轮不做 DEM 与 FIT 高程差异诊断，不用 DEM 修正活动轨迹点。
- 海拔墙原用于模拟山地地形；引入 DEM 后其表达职责被真实地形替代，继续保留会混淆“记录海拔”和“地形海拔”，因此当前已退役。

## 4. 必须保留的既有轨迹分析能力

- CP 点展示、新增、编辑、删除和侧栏列表。
- 里程点展示与开关。
- 最高点 / 坡顶标记展示与开关。
- 进度滑块、已完成 / 未完成轨迹切片。
- 底部半透明海拔剖面图和点击定位 / 新增 CP 联动。
- 活动详情页轨迹缩略图跳转轨迹分析工具。
- 2D / 3D 视角滑块、指南针 / 归北。
- 自动旋转入口如当前产品仍保留。
- GPX / FIT 导入后加载轨迹并定位。

## 5. 当前基线事实

- `lib/Cesium` CDEM-00 基线体积为 `18M`，文件数为 `375`。
- CDEM-01 已将本地 Cesium 资源替换为官方 `cesium@1.143.0` 的 `Build/Cesium` 产物；当前体积为 `22M`，文件数为 `392`。
- CDEM-00 已完成，基线审计报告和静态契约测试已落盘。
- `track.html` 使用 `window.CESIUM_BASE_URL = 'lib/Cesium/'`。
- Cesium CSS 和脚本 CDN fallback 已统一到 `cesium@1.143.0`，不得重新混用旧版 `1.105.1`。
- 当前 viewer 使用 CARTO Voyager 栅格底图和 `new Cesium.EllipsoidTerrainProvider()`。
- CDEM-06 已完成海拔墙彻底退役；当前代码不应再存在 `wallEntity`、`海拔剖面堆积墙`、`wall.wall` 或 `Cesium.Wall` 等活跃实现。
- 当前轨迹主体使用 `remainingTrackEntity` / `completedTrackEntity` 和 `Cesium.CallbackProperty` 维护进度切片。
- 当前 CP、里程、坡顶、进度、剖面图和相机控制均集中在 `track.html`。

## 6. CDEM-09 执行约束

- CDEM-09 是总验收与交付报告任务，默认不新增产品能力。
- 必须汇总 CDEM-00 到 CDEM-08 的实际执行结果、自动化证据、未自动化手测项和风险。
- 必须明确城市跑、山地 / 越野跑、骑行爬坡三类真实轨迹 UI 点检状态；未实际执行的手测项不得写成通过。
- 必须汇总 CP、里程、最高点 / 坡顶、进度、剖面、相机、活动详情缩略图跳转的回归结论。
- 必须汇总海拔墙退役、安装包资源、DEM 下载触发、临时缓存清理和失败回退结论。
- 必须运行最终自动化回归组和 `git diff --check`。
- 若自动化不绿，不得标记 CDEM-09 完成。
- 若仅真实 UI 手测未执行，可标记为“自动化验收通过 / 真实场景手测待执行”，并给出是否可进入后续正式开发的条件化建议。
- 海拔墙已经 CDEM-06 退役，CDEM-09 不得恢复任何海拔墙实现。
- 不写活动数据库，不改 FIT / 手表海拔，不改累计爬升、最高海拔、底部剖面图或复盘事实。
- 不引入 MapLibre / deck.gl，不改活动详情概览 / 复盘合同。
- dirty worktree 中存在大量无关改动，不得 stash、reset、覆盖或格式化。

## 7. CDEM-07 完成状态

- CDEM 聚焦回归通过：`tests/test_track_cesium_dem_contract.py`、`tests/test_track_dem_session_cache.py`、`tests/test_track_thumbnail_canvas_v4.py` 共 `51 passed`。
- 海拔墙残留 grep 通过：`wallEntity|elevation wall|海拔墙|海拔剖面堆积墙|wall.wall|Cesium.Wall` 未命中 CDEM 回归范围文件。
- `git diff --check` 通过。
- 任务清单完整回归组已通过：`tests/test_track_cesium_dem_contract.py`、`tests/test_track_html_sync_logic.py`、`tests/test_track_thumbnail_canvas_v4.py`、`tests/test_v9_0_detail_tab_review.py`、`tests/test_track_dem_session_cache.py` 共 `161 passed`。
- 前次 ACS 生涯面板与多运动详情概览静态合同失败已用合同锚点和空态 hidden 语义修复，未改变 Cesium / DEM / 海拔墙退役逻辑。
- CDEM-07 门禁已解除。

## 8. CDEM-08 当前检查点

- 当前默认 provider 为 ArcGIS World Elevation：`Cesium.ArcGISTiledElevationTerrainProvider.fromUrl(ARCGIS_WORLD_ELEVATION_TERRAIN_URL)`。
- 真实地形入口只在 `selectTerrainLayer('real')` 后进入 `loadRealTerrainLayerForCurrentTrack()`；2D / 3D slider block 不含 `selectTerrainLayer`、`applyStandardTerrainLayer` 或 `loadRealTerrainLayerForCurrentTrack`。
- 标准地形路径为 `new Cesium.EllipsoidTerrainProvider()`，真实地形失败时 `applyStandardTerrainLayer('真实地形暂不可用')` 回退。
- DEM 会话缓存 root 为 `~/.fitvault/cache/dem-session/`，当前实现只写 `route-bbox.json` 作为当前路线 bbox 元数据。
- `DemSessionCache.__init__()` 只清理旧 `session_*`，不创建当前目录；`prepare_route_bbox()` 仅在用户动作后创建当前 session 目录。
- `main()` 的 `finally` 调用 `api.cleanup_dem_session_cache()`，清理当前 session 目录。
- CDEM-08 资源验收完成：`lib/Cesium` 当前 `22M / 392 files`，相对 CDEM-00 基线约 `+4M / +17 files`。
- ArcGIS World Elevation service metadata 当前探测结果：HTTP `200`，耗时约 `0.896565s`，下载 `8074` bytes。
- CDEM-08 聚焦测试通过：`tests/test_track_dem_session_cache.py tests/test_track_cesium_dem_contract.py` 共 `19 passed`；`git diff --check` 通过。

## 9. CDEM-09 当前检查点

- CDEM-09 需要产出 `docs/轨迹分析工具_Cesium_DEM_POC_开发完成报告.md`。
- 最终自动化验证命令为：`tests/test_track_cesium_dem_contract.py tests/test_track_dem_session_cache.py tests/test_track_html_sync_logic.py tests/test_track_thumbnail_canvas_v4.py tests/test_v9_0_detail_tab_review.py`。
- 真实城市跑、山地 / 越野跑、骑行爬坡 UI 点检当前尚未在桌面界面执行，报告中必须列为待手测。
- CDEM-09 最终自动化验证通过：完整回归组 `161 passed`，`git diff --check` 通过，海拔墙残留 grep 无命中。
- 开发完成报告已落盘，交付结论为“自动化总验收通过，正式发布前需补真实 UI smoke”。
- macOS WebView / ANGLE / Metal shader 兼容修复已追加：Viewer 禁用 `skyAtmosphere` / `skyBox` / OIT / shadows / terrain shadows / MSAA / render-loop error modal，通过 `createCesiumWebviewCompatibleGlobe()` 在首帧前关闭 `showGroundAtmosphere`、`enableLighting`、`dynamicAtmosphereLighting`、`dynamicAtmosphereLightingFromSun`、Globe shadows 和 water effect，并在初始化后再次关闭 HDR、sunBloom、FXAA/post-process、skyAtmosphere、sun/moon、fog、shadowMap 和 Globe 大气 / 光照路径；当前最终完整回归组更新为 `165 passed`。
- 真实地形 marker 可读性修复已追加：CP 在真实地形下不再 point + billboard 双重绘制，CP / 最高点 / 坡顶图钉改为运行时 canvas 生成的 retina PNG billboard，不再使用 SVG text / SVG filter / emoji 贴图；所有 marker 使用有限 depth-test 穿透距离和标签距离分层；里程点按 1km / 5km / 10km 距离分层显示；最高点优先于普通坡顶显示；真实地形地图标签去掉前置 emoji，降低 WebGL 纹理栅格化黑边风险。
- 真实地形 3D 观感修复已追加：用户切换真实地形后等待 `scene.globe.tilesLoaded` 稳定若干帧，再应用地图显示专用 `verticalExaggeration` 和 ArcGIS `World_Shaded_Relief` 半透明 hillshade imagery overlay。图层切换不得自动 `flyToBoundingSphere`、不得改写 2D / 3D slider、不得重置用户当前相机视角；该增强仅作用于 Cesium scene 显示，不恢复动态光照 / 阴影 shader，不改写 `appState.points`、FIT / 手表海拔、统计、底部剖面、复盘、AI 或 DB。
- 本轮修复后的 CDEM 聚焦回归更新为 `23 passed`，完整轨迹详情回归组更新为 `165 passed`；真实桌面 UI 下的 marker 清晰度、三类轨迹地形观感、hillshade 国内网络可用性和 shader 兼容仍需人工 smoke，不得写成已通过。

## 10. 每任务执行前提示词必须包含

- 刷新后的本契约摘要。
- 参考文档：开发交付手册、开发任务清单、基线审计报告，以及当前任务涉及的源码 / 测试。
- 本任务目标、范围、允许文件、禁止文件、验收命令和完成定义。
- dirty worktree 保护声明。
- 任务偏离时的重新全文阅读触发条件。

## 11. CDEM-10 顶部工具栏响应式契约

- 本任务只修复 `track.html` 轨迹分析工具顶栏在不同窗口宽度下的布局和可达性；不改变任何轨迹、地图、DEM、缓存或活动事实逻辑。
- 根因是 `.panel-inner` 强制单行 `flex-wrap: nowrap`、隐藏横向滚动条和固定宽度/不可收缩子项叠加，导致中等宽度窗口右侧控制实际溢出且不可发现。
- 顶栏必须按语义组织为：运动统计、视角控制、地形图层、主动作、次级动作、标记显隐和轨迹进度。宽屏完整单行；中等宽度允许逻辑换行并压缩统计/次级动作；窄屏必须提供真实、可键盘操作的次级动作菜单，不能仅把控件 `display:none` 或留在不可见横向滚动区。
- 必须保留既有入口和 ID：`map-compass-btn`、`map-view-slider`、`terrain-layer-standard`、`terrain-layer-real`、`btn-auto-rotate`、`toggle-cp`、`toggle-km`、`toggle-peak`、`progress-slider`、导入、剖面和导出动作。既有事件绑定、2D / 3D slider 与 terrain provider 的解耦不得改变。
- 保留 `topbar-terrain-control` 的标准/真实地形状态机和原有无确认弹窗语义；不得在本任务重新引入海拔墙、MapLibre / deck.gl、阴影 shader、DEM 长期缓存或任何后端变更。
- 允许修改：`track.html`、`tests/test_track_cesium_dem_contract.py`、本摘要、CDEM-10 工程提示词与任务清单。禁止修改 FIT / GPX 解析、数据库、`main.py` DEM cache、Cesium provider、活动详情 / 复盘合同和无关 dirty 文件。
- 验收：静态合同覆盖所有工具入口与响应式规则；`node --check`、CDEM 聚焦 pytest、`git diff --check` 通过。手测覆盖约 1440px、1180px、960px 宽的桌面窗口，确认顶栏无被裁切且菜单项目可点击。
- 偏离触发：如需修改控件行为、事件绑定、terrain provider、相机控制、数据字段或缩略图跳转，必须重新全文阅读交付手册、任务清单、本摘要和直接相关源码/测试后再继续。

### CDEM-10 完成记录

- 顶栏已改为统计、视角、地形、主动作、次级动作、标记显隐和进度七个语义组；`.panel-inner` 不再使用单行隐藏横向滚动。
- 约 `1440px` 宽窗口为完整单行；约 `1180px` 与 `960px` 宽窗口按语义组自动换行，实测 `scrollWidth === clientWidth`，不存在横向裁切。
- `900px` 以下，剖面、漫游和导出进入带 `aria-expanded` / `aria-controls` 的“更多轨迹工具”菜单；菜单可点击打开、Esc 关闭，次级动作执行后自动收起。归北、2D / 3D、地形、导入、CP / 里程 / 坡顶和进度均保留原 ID / handler。
- 窄屏统计保留里程和耗时，爬升与最高值仅作视觉压缩；地图标记开关保留可访问文本并补充悬停说明。
- 自动验证通过：`166 passed`（CDEM / DEM cache / sync / thumbnail / detail 回归组）、`node --check /tmp/fitvault_track_inline.js`、`git diff --check`。浏览器实测覆盖 1440px、1180px、960px 与 880px 宽度；真实数据轨迹与真实 DEM 场景手测仍沿用 CDEM-09 发布前 smoke 门禁。

## 12. CDEM-11 顶栏防重叠契约

- 本任务只修复真实统计值加载后，路线统计组与归北 / 2D / 3D 视角组在临界窗口宽度下发生视觉重叠的问题。
- 根因是 `.topbar-stats` 同时允许 `flex-shrink` 且继承 `min-width: 0`，但内部 `.mini-stat` 均不可收缩；真实里程、耗时、爬升、最高值变长后，子项可从缩水后的统计组边界溢出，右侧视角组仍按错误边界排版。
- 修复必须让统计组宽度不小于自身内容宽度，并在空间不足时让整个后续语义组换行；禁止通过绝对定位、负 margin、遮挡、隐藏归北或隐藏 2D / 3D slider 规避。
- 保留 CDEM-10 的七个语义组、900px 以下更多菜单、全部既有 ID / handler、地形与视角解耦、海拔墙退役和 DEM / FIT 事实边界。
- 允许修改：`track.html` 顶栏 CSS、`tests/test_track_cesium_dem_contract.py`、本摘要、CDEM-11 工程提示词和任务清单。禁止修改相机 / terrain provider / entity / backend / FIT / GPX / DB / DEM cache。
- 验收必须加入“长统计值”场景，断言统计组内容不越界且与 `.topbar-view-controls` 矩形不相交；覆盖临界宽度扫描，并继续通过 CDEM 完整回归、JS 语法和 diff 检查。
- 本轮未发现产品或架构偏离，不触发重读全部业务合同；若需要隐藏视角控制、修改统计语义或改变相机行为，立即重新全文阅读相关合同后再继续。

### CDEM-11 完成记录

- `.topbar-stats` 已由可收缩的 `flex: 1 1 280px` 改为 `flex: 1 0 auto; min-width: max-content`，统计组不会再缩到四个不可收缩统计胶囊的内容宽度以下。
- 空间不足时仍由 `.panel-inner { flex-wrap: wrap; }` 负责整组换行；归北按钮和 2D / 3D slider 未隐藏、未缩放、未改事件。
- 使用 `123.45 km / 12:34:56 / 12345 m / 8848 m` 长值夹具在 1440、1180、1040、960px 扫描：各宽度 `stats.scrollWidth === stats.clientWidth`、顶栏无横向溢出、统计组与视角组矩形均不相交。
- 自动验证通过：完整 CDEM 回归 `166 passed`、`node --check /tmp/fitvault_track_inline.js`、`git diff --check`。临时浏览器夹具已清理。

## 13. CDEM-12 地形切换相机一致性契约

- 保留现有产品分工：2D / 3D slider 只控制相机视角；标准 / 真实地形按钮只切换 terrain provider 和对应显示层。禁止让 slider 触发 DEM 下载或 provider 切换。
- 标准地形在 slider 位于 3D 端时允许呈现三维透视，这是正常行为，不改成固定平面地图。
- 当前缺陷不是 `selectTerrainLayer()` 直接调用 `flyTo`，而是 terrain provider、地表高度、`verticalExaggeration`、贴地轨迹和 marker 高度基准变化后，没有按同一地理焦点恢复相机与新地表的相对关系。
- 修复目标是保持“同一用户视图”，不是机械保持相机 ECEF 世界坐标：切换前捕获屏幕中心地理锚点、heading、pitch、roll、焦点距离和 slider 值；目标地形稳定后，按同一经纬度锚点和新地表高度恢复相同姿态与近似相同屏幕尺度。
- 地形切换不得调用路线重新 framing，不得使用 `flyToBoundingSphere` 自动适配路线，不得改写 `appState.centerPosition`、`currentRange` 的业务语义或 `map-view-slider` 值。
- 保留真实地形 `verticalExaggeration = 1.6`、hillshade、轨迹 `clampToGround`、marker `RELATIVE_TO_GROUND` 与标准地形现有渲染策略；如需改变这些产品参数，必须单独确认，不可借相机修复顺手调整。
- 切换必须具有事务 / 版本语义：快速连续点击时最后一次用户意图生效，过期的异步 DEM provider 结果不得覆盖新选择；失败回退标准地形时也要恢复切换前视图。
- 不改 FIT / GPX、活动数据库、累计爬升、最高海拔、底部剖面、复盘、AI、DEM session cache 和 provider 选型。
- 自动与桌面 UI 验收必须覆盖标准→真实、真实→标准、失败回退、快速反向切换，以及 2D、中间角度、3D 三种 slider 状态；未实际执行的真实 UI 场景不得写成通过。
- 2026-08-03 DMG 实测补充：用户反馈打包后切换标准 / 真实地形时相机视角变化不大，当前体验可接受；该结果仅作为局部真实打包环境 smoke 证据，不替代完整 CTCAM-00 至 CTCAM-07 验收，也不改变 CDEM-12 的 `Planned` 状态。

## 14. CDEM-13 真实地形标记清晰度契约

- 当前 CP / 最高点 canvas 图钉源图固定为逻辑 `64×84`、backing `128×168`，但 Cesium 显示尺寸分别为 CP `32×42`、最高点 `30×40`、普通坡顶 `24×32`；非整数长宽缩放和不同目标尺寸会产生纹理重采样。
- CP 与最高点还分别使用 `scaleByDistance = 1.14→0.72`、`1.05→0.68`，相机会在连续距离区间生成大量非整数显示尺寸，进一步造成边缘和中心图形模糊。
- pin cache key 当前只包含颜色 / 类型，不包含 `devicePixelRatio`、backing scale 或目标尺寸；窗口显示比例变化后无法主动重建更匹配的纹理。
- 里程点并未使用 canvas billboard，而是 `PointGraphics + LabelGraphics`；真实地形标签字体仅 `12px`，清晰度依赖 Cesium glyph atlas、drawing buffer 和 WebView 缩放，不能用“已有 retina 图钉”覆盖其验收。
- Viewer 当前为 WebView shader 兼容关闭 `FXAA`、`MSAA=1`，且没有专门量化 `drawingBufferWidth / canvas.clientWidth / devicePixelRatio / resolutionScale`。这些是可能的全局放大因素，但不得在未测量性能和 shader 风险前直接提高分辨率。
- `RELATIVE_TO_GROUND`、depth test 和 terrain offset 主要影响遮挡 / 裁切 / 抖动，不是纹理模糊的直接根因；清晰度任务仍需同时验证图钉没有因地形交叉而产生“像模糊”的半遮挡。
- 修复不得恢复 SVG text / filter / emoji 纹理，不得丢失 CP 编辑、里程层级、最高点优先级、distance declutter 和真实地形高度策略。
- 本问题作为独立 CDEM-13 任务处理，不混入 CDEM-12 相机修复的生产实现；两个任务在最终真实 UI smoke 中合并验收。

## 15. CDEM-14 轨迹加载性能契约

- 当前性能问题以高密度轨迹为重点：activity `127` 为 `26,052` 点、约 `9.3 MB` track JSON；activity `907` 为 `21,690` 点、约 `7.9 MB` track JSON。
- 本地 `Api.load_activity_track()` 探针约 `0.05–0.07s`，暂不能把 5 秒等待归因于 SQLite；必须在真实 DMG 中拆出 bridge、JSON、前端算法、Cesium、相机和 DEM 网络阶段。
- 当前 `applyDataAndRender()` 是同步首屏路径，包含 canonical stats、峰顶检测、bounds、全量 Cartesian3、轨迹 entity 重建、图表、固定 `2.5s` `flyTo`、报告、列表和全量 `sync_track_context()`。
- canonical points 已带有效 `dist_km` 时，不应为了 fallback 无条件重复计算相邻 haversine；当前 `haversine()` 还会在每次调用时执行 `console.warn()`，必须优先消除热循环内的逐次日志。峰顶检测的前后 300 米扫描作为同一优先级热点测量和优化。
- canonical activity 的完整 points 不应在 `load_activity_track` 返回后又通过 `sync_track_context` 重复序列化 / 传输；若改变该 bridge 合同，必须保留临时导入路径并同步 AI activity advice 测试和白名单边界。
- 允许对 Cesium 显示 polyline 做受控显示几何预算或渐进渲染，但原始 points 必须保留，CP / 里程 / 最高点 / 坡顶、剖面、进度和活动事实不得丢失或改写。
- 标准地形加载不得等待 DEM、hillshade 或 terrain settle；真实地形额外网络耗时必须单独记录，失败不得阻断标准轨迹分析工具。
- 修复顺序固定为：PLOAD-00 测量，PLOAD-01 热循环 / 日志，PLOAD-02 canonical 重复传输，PLOAD-03 相机 / 非关键调度；完成后立即复测。只有仍未达标时才实施 PLOAD-04 Cesium 显示几何，达标时以“不采用”结论完成该 POC。
- CDEM-14 详细清单为 `docs/轨迹分析工具_轨迹加载性能优化任务清单.md`，当前状态为 `Planning`，不得因单个活动改善或主观感受提前标记完成。

### PLOAD-00 当前执行契约

- 本任务只建立基线，不修改 `track.html`、`main.py` 或生产行为。
- 只读探针必须使用 activity `127`、`907` 的真实本地数据库数据，并执行 `track.html` 当前 `haversine()`、`_detectPeakMarkers()`、`_buildStatsFromCanonical()` 源码；不得复制替代算法充当生产基线。
- 必须分别记录 Python load、Python JSON encode、payload bytes、前端 stats / peak、`console.warn` 调用数和重复 `JSON.stringify`；静态记录全量 Cartesian3、固定 `2.5s` `flyTo` 与 canonical 全量 `sync_track_context` 路径。
- 本地脚本不能证明 pywebview bridge、WebKit/Cesium GPU、真实 DEM tile 或 hillshade 时延；未执行部分必须保留为 DMG 待测，不能包装为通过。
- 允许文件为诊断脚本、脚本测试、PLOAD-00 基线报告、工程提示词、契约摘要和任务状态；不得触碰业务数据库内容或无关 dirty 文件。
- PLOAD-00 已完成：`20 passed`，基线报告为 `docs/轨迹分析工具_Cesium_DEM_POC_轨迹加载性能_PLOAD_00_基线报告.md`；下一项进入 PLOAD-01，先处理热循环逐次日志、冗余 haversine 和峰顶检测。

### PLOAD-01 当前执行契约

- 只允许修改 `track.html` 的显示层距离 / 峰顶辅助逻辑、性能探针、聚焦测试和任务文档；不得修改后端事实、DB、FIT / GPX、DEM、相机、复盘或 AI。
- `haversine()` 不得在热循环内逐次记录 console；canonical point 有有效 `dist_km` / `dist` 时不得计算 fallback haversine。
- 峰顶检测保留 250m 去重、300m 邻域、12m prominence、连续扫描停止和最高点 300m 升级语义；允许预计算球面单位向量并使用等价弦长阈值消除每次三角函数。
- activity `127`、`907` 修复前后 marker 数量、经纬度、海拔与最高点标志必须一致；warning count 必须降为 `0`。
- 必须重跑真实数据探针、CDEM 聚焦测试、JS 语法和 `git diff --check`，再执行 adaptive review。
- PLOAD-01 已完成：activity `127` / `907` stats / peak 探针分别下降约 `68.3%` / `61.5%`，warning count 归零；activity `1117` / `1094` 和四条路线 marker 合同保持一致；`22 passed`、JS 语法和 diff review 通过。

### PLOAD-02 当前执行契约

- canonical activity 已由 `load_activity_track()` 完整传入 WebView；`sync_track_context()` 只需 `activityId`、placemarks、filename、weather 和白名单 `activityAdviceRouteFacts`，不得重复携带完整 points。
- 临时 session 继续携带 points，后端继续通过 `_build_activity_advice_snapshot_from_track_context()` 聚合临时路线事实。
- 后端 DB AI snapshot 仍只由 `activityId` 构建，activity advice 仍优先消费 overview route facts；前端不得补算 canonical 事实。
- API 合同必须明确 points 为按 persistence mode 条件提供；测试必须同时覆盖 canonical 无 points 和 temporary 有 points。
- 不修改 marker、DEM、相机、DB、FIT / GPX、活动详情 / 复盘或 AI 输出语义。
- PLOAD-02 已完成：canonical activity 不再重复回传完整 points，activity `127` / `907` context payload 分别下降 `99.992%` / `99.996%`；temporary session 和 activity advice 事实合同保持；`52 passed`、API JSON、JS 语法和 diff review 通过。

### PLOAD-03 当前执行契约

- 首屏可用定义为 Cesium 地图主体、顶部权威统计、底部 Canvas 海拔剖面和 CP 列表已完成当前路线渲染；不得等待 ECharts、AI 报告、雷达、地区解析或轨迹上下文后台同步。
- `applyDataAndRender()` 每次有效路线加载必须生成单调递增的 render revision；首帧后任务执行前和每个任务之间都要校验 revision，快速切换路线时旧任务不得写回新路线 UI 或上下文。
- 首帧后任务优先使用 `requestAnimationFrame` 后的 `requestIdleCallback`，无该 API 时使用短 `setTimeout` 回退；调度失败不能阻断地图、统计、剖面、CP、里程、最高点或进度交互。
- 初始路线定位保留现有中心、range、heading、pitch 和 roll 语义，采用短动画而不是直接跳变；固定 `2.5s` 不再作为首屏等待。任何用户相机控制取得 ownership 时必须能取消初始飞行动画。
- 本任务不得修改标准 / 真实地形 provider、CDEM-12 地形切换视图恢复、2D / 3D slider 职责、DEM / hillshade、marker 高度 / 清晰度、FIT / GPX、DB 或活动事实。
- PLOAD-03 完成后立即复跑 activity `127`、`907` 性能探针和聚焦回归；根据低风险优化后的证据决定 PLOAD-04 是否需要显示几何抽稀，不能为完成清单强行引入双轨迹结构。
- PLOAD-03 已完成：首屏关键路径与首帧后 idle 队列已分层，render revision 可阻止旧路线后台任务写回；初始定位从固定 `2.5s` 改为可被用户接管的 `0.8s` 短动画。activity `127` / `907` 合同复测保持通过，聚焦门禁 `41 passed`、JS 语法和 diff review 全绿。
- PLOAD-04 决策输入：PLOAD-01 的 stats / peak 热点下降 `68.3%` / `61.5%`，PLOAD-02 canonical context 缩减 `99.992%` / `99.996%`，PLOAD-03 移除固定等待并延后非关键工作；当前没有证据证明全量 Cesium 显示几何仍是首屏主瓶颈，因此优先记录“不采用显示抽稀”，真实 DMG 精确首屏计时留到 PLOAD-06 验收。

### PLOAD-04 当前执行契约

- PLOAD-04 是复杂度门禁，不要求为了形式上的 POC 修改生产几何；当前证据不支持增加原始 / 显示双轨迹结构。
- 本任务以文档化“不采用显示抽稀”完成：保留 `appState.points`、`appState.fullPositions`、CP / 里程 / 最高点来源、进度切片和剖面联动现状。
- 不新增 Douglas-Peucker、点数阈值、渐进 entity、后台 Worker 或任何会改变路线视觉形状和 marker 映射的实现。
- 若 PLOAD-06 真实 DMG 分段后来证明 Cartesian3 / entity 是剩余主瓶颈，应作为新证据重新打开 PLOAD-04，而不是在本任务预埋未启用的双轨迹代码。
- 验收以 PLOAD-03 完成报告、activity `127` / `907` 探针、现有 marker 合同和无生产代码 diff 为准；未执行的 WebView GPU 时延仍明确列为待测。
- PLOAD-04 已完成并决定不采用显示抽稀；本任务无生产代码变更，聚焦回归 `24 passed`。若 PLOAD-06 没有新的真实 DMG 分段证据，不得重新引入双轨迹结构。

### PLOAD-05 当前执行契约

- 标准轨迹加载仍以 `EllipsoidTerrainProvider` 首屏为默认路径，不调用 `prepare_dem_session_cache()`、ArcGIS terrain provider、terrain settle 或 hillshade；只有用户选择真实地形才产生这些额外成本。
- 真实地形一次用户动作需要记录：DEM session bbox 准备、provider metadata、provider assignment 后首批 terrain tile、`tilesLoaded` 稳定、hillshade overlay 建立、terrain-sensitive marker / entity 重建和总耗时。
- 计时使用单次阶段记录，不在 tile、点或帧热循环中输出 console；最近一次记录保存在前端只读诊断状态，供 PLOAD-06 真实 DMG 验收读取。
- `waitForRealTerrainTiles()` 必须有有界超时并清理事件监听器；未观察到 pending tile 时如实记录，不得伪造首 tile 完成时间。
- 真实地形失败仍调用标准地形回退，标准地图、轨迹、顶部统计、CP / 里程 / 最高点、进度和剖面保持可用；诊断失败本身不得阻断回退。
- 不改变 provider URL、DEM session cache 生命周期、vertical exaggeration、hillshade 视觉参数、CDEM-12 相机合同、marker 像素或活动事实。
- PLOAD-05 已完成：最近一次 terrain 性能快照可通过 `getLastTerrainLoadPerformance()` 读取；标准分支不触发 DEM，真实分支记录 cache、metadata、tile、settle、hillshade setup、marker rebuild 和 total。聚焦回归 `32 passed`，当前网络对 ArcGIS metadata / hillshade tile 可达；真实 WebView tile settle 未伪装为通过。

### PLOAD-06 当前执行契约

- 最终验收必须同时固化 PLOAD-01 逐点日志 / peak 合同、PLOAD-02 conditional context payload、PLOAD-03 revision / 首帧后队列 / 可中断短相机、PLOAD-04 不采用显示抽稀和 PLOAD-05 terrain 阶段隔离。
- canonical `load_activity_track()` 入口需要记录前端可观测的 bridge + decode 总耗时；不得为了估算 payload 再次 `JSON.stringify` 完整 response。后端 load / encode 继续由只读 Python 探针记录。
- `applyDataAndRender()` 最近一次性能快照记录 stats / marker、bounds、Cesium scene、Canvas profile、CP list、首屏同步完成、首帧后任务完成；记录本身不得输出逐点日志或改变任务顺序。
- 快速切换路线时旧 revision 不得覆盖当前性能快照；temporary import 没有 canonical bridge 时明确标记 `frontend_only`，不能伪造 bridge 数据。
- 真实 UI 必须优先尝试打包 `脉图.app`；能读取的实际场景如实记录，无法通过桌面可访问性或 WebView 调试读取的精确分段标为未验证，不得由 pytest / curl 替代。
- 最终自动化回归覆盖 CP 编辑合同、1/5/10km、最高点优先级、进度切片、剖面联动、相机和 DEM 失败回退；全绿并通过累计 diff review 后才完成 CDEM-14。
- PLOAD-06 实现与自动化已完成：最近一次 track / terrain 快照可读取，轨迹专项 `212 passed`，全仓 `3505 passed, 5 skipped, 262 subtests passed`，JS / API JSON / diff check 全绿；当前源码打包 app 启动成功。
- activity `127` 打包 WebView smoke 实际看到地图、8.34km / 7h14m / 896m / 5337m 顶部指标、路线、里程 marker 和底部剖面；未精确读取 WebView 内部分段。
- 用户明确由其手动完成真实 UI 验收。activity `907`、城市跑、骑行、真实地形切换、CP 编辑、图钉清晰度、相机手感和精确 `30%` 首屏指标仍为待回填；CDEM-14 状态为 `Implementation Complete / User Manual Acceptance Pending`，不得描述为最终产品验收通过。
