# P6A 3D 轨迹视觉基线与改造边界确认报告

> 日期: 2026-06-17
> 范围: 轨迹页 3D 地图视图、轨迹主体、海拔墙、顶部工具栏、底部海拔剖面图、标签系统、报告入口等视觉层。
> 结论: P6 后续可以主要在 `track.html` 内完成视觉改造,但必须隔离数据/AI/导入链路。

## 1. 当前视觉元素盘点

| 模块 | 当前实现位置 | 当前问题 | 后续任务 |
|---|---|---|---|
| 主轨迹线 | `track.html` `updateScene()` 中 `remainingTrackEntity` / `completedTrackEntity` | 已完成轨迹为高饱和绿色 + 黑色描边,未完成轨迹为蓝色半透明,整体偏工程调试态 | P6B |
| 海拔墙 | `track.html` `updateScene()` 中 `wallEntity` | 绿色墙面透明度偏重,缺少渐隐和空气感,容易像 GIS 围挡 | P6C |
| 起点/终点/最高点 | 当前主要依赖里程/坡顶/CP entity 间接表达,最高点在 `peakMarkers` 中强调 | 重点标记体系不统一,最高点与普通坡顶同一套强描边标签 | P6B / P6D |
| 里程标签 | `track.html` `updateScene()` 中 `kmEntities` | 黄色点 + 黑描边 + 高密度标签,与地图道路黄色抢视觉 | P6D |
| CP 点 | `track.html` `renderCpMapLayer()` | 点、billboard、label 同时存在,尺寸和描边较重,标签显示距离较远 | P6D |
| 坡顶标签 | `track.html` `updateScene()` 中 `peakEntities` | 红/金 + 黑描边,视觉冲击强;普通坡顶和最高点层级差不够精致 | P6D |
| 顶部工具栏 | `track.html` `#top-bar` / `.panel-inner` / `.ctrl-btn` | 深色后台栏,按钮样式偏密集,分隔符较硬 | P6E |
| 统计胶囊 | `track.html` `.mini-stat` 和 `#val-dist/#val-time/#val-gain/#val-max` | 目前是文本 + 分隔线,不是 Apple-like compact capsule | P6E |
| 2D/3D 滑杆 | `track.html` `.topbar-slider-wrapper` / `#map-view-slider` | 当前滑杆背景偏浅灰,拇指偏重,和顶栏玻璃风格不统一 | P6E / P6H |
| 进度滑杆 | `track.html` `#progress-slider` + `bindTopBarToggles()` | 控件较小,视觉权重和主工具栏不统一 | P6E / P6H |
| 底部海拔剖面图 | `track.html` `#profile-container` + `drawProfileChart()` | 面板贴底且灰色填充较重,网格/红点/CP 标记仍偏工具化 | P6F |
| 报告侧栏入口 | `track.html` `#ai-sidebar-btn` / `#ai-sidebar-body` | 紫蓝渐变侧拉按钮存在感强,与主地图视觉体系略割裂 | P6G / P6H |
| 隐私按钮 | 当前运行界面可见,代码中未作为独立 P6 入口定位到稳定选择器 | 视觉上为高饱和紫色浮标,后续应确认来源后纳入统一浮层体系 | P6A-补查 / P6G |
| 地图底图 | `initCesiumViewer()` 使用 CARTO Voyager raster tiles | 底图道路黄、地块绿与轨迹绿互相争抢;底图样式受瓦片源限制 | P6G |

## 2. 可改范围

P6 后续允许优先修改以下区域:

- `track.html` CSS:
  - `#top-bar`
  - `.panel-inner`
  - `.mini-stat`
  - `.ctrl-btn`
  - `.toggle-label`
  - `.topbar-view-controls`
  - `.topbar-slider-wrapper`
  - `#map-view-slider`
  - `#profile-container`
  - `#profile-canvas`
  - `#ai-sidebar-btn`
  - `#ai-sidebar-body`
- `track.html` Cesium 视觉属性:
  - `updateScene()` 中 `remainingTrackEntity.polyline`
  - `updateScene()` 中 `completedTrackEntity.polyline`
  - `updateScene()` 中 `wallEntity.wall`
  - `updateScene()` 中 `kmEntities` 的 point / label 样式
  - `updateScene()` 中 `peakEntities` 的 point / label 样式
  - `renderCpMapLayer()` 中 CP point / billboard / label 样式
- `track.html` canvas 绘制样式:
  - `drawProfileChart()` 中网格、填充、线条、当前点、CP 标记的颜色和透明度
- 视觉辅助:
  - 可增加纯视觉 CSS 变量或 helper 函数,用于统一颜色、透明度、字体、label 参数
  - 可参考 `docs/visual_mockups/apple_like_3d_track_mockup.html` 和 PNG 方向稿

## 3. 禁改范围

P6 不得修改以下数据、AI、导入和业务链路:

- 数据计算:
  - `_buildStatsFromCanonical(...)`
  - `_previewStatsOnly(...)`
  - `calculateStats(...)`
  - `appState.points`
  - `appState.activityMetrics`
  - `dist` / `dist_km`
  - 距离、累计爬升、最高/最低海拔、坡度、CP 距离、里程点、坡顶检测逻辑
- 活动建议和 AI:
  - `buildActivityAdviceRouteFactsFromOverview(...)`
  - `requestActivityAdvice()`
  - `sync_track_context(...)`
  - `call_llm(...)`
  - `_activity_advice_snapshot`
  - `_ai_snapshot`
  - 所有 prompt / normalizer / LLM payload
- 导入解析:
  - `triggerTrackImport()`
  - `load_activity_track`
  - `load_local_track`
  - `import_track`
  - `parseGPX`
  - `parseKML`
- 交互行为:
  - 2D/3D 视角切换
  - 进度滑杆
  - CP/里程/坡顶显示开关
  - 剖面、旋转、导出、导入 GPX 按钮
  - 地图拖拽、缩放、旋转

## 4. 推荐执行顺序

1. P6B 轨迹主体视觉降噪
2. P6C 海拔墙轻量化
3. P6E 顶部工具栏 glass 改造
4. P6F 底部海拔剖面图重绘
5. P6D 标签系统层级改造
6. P6G 地图底图与整体色彩调和
7. P6H 响应式与交互状态检查
8. P6I 视觉回归验收

建议先做 P6B/P6C/P6E/P6F,因为这四项能最快改善质感,且最容易保持数据逻辑不变。P6D 标签系统涉及默认显示密度和用户预期,应在主体视觉稳定后处理。

## 5. 风险点

- Cesium entity 使用 `CallbackProperty` 按进度切片,视觉参数不能破坏 completed / remaining / wall 的动态更新。
- 标签密度调整可能改变用户对里程、坡顶、CP 信息可见性的预期,默认开关行为必须保持不变。
- CARTO Voyager 底图本身不可完全控色,若不更换瓦片源,只能通过轨迹/墙/标签/overlay 进行调和。
- `drawProfileChart()` 是 canvas 命令式绘制,改视觉时容易误碰 `getX/getY/maxDist/altRange` 等数据映射,后续必须只改颜色、线宽、透明度和装饰。
- `renderCpMapLayer()` 同时使用 point、billboard、label,降噪时需确认点击/编辑 CP 的拾取行为不受影响。
- 当前工作区可能出现打包产物或并行会话改动,每次提交前必须按文件/patch 精确 staged,避免混提交。

## 6. 后续验收基线

每个后续 P6 任务至少手动覆盖:

- 打开真实 FIT/DB 轨迹。
- 导入 GPX 轨迹。
- 切换 2D / 3D 滑杆。
- 拖动进度滑杆。
- 开关 CP 点、里程、坡顶。
- 打开/关闭报告侧栏。
- 查看底部剖面图点击定位。
- 截图对比改造前后。

## 7. P6B 入口建议

P6B 应只处理 `updateScene()` 内主轨迹线:

- 统一主轨迹色为克制青绿/苹果绿。
- 降低黑色描边强度。
- 加轻微白色高光或柔和 glow。
- 保持 `CallbackProperty` 切片逻辑不变。
- 不改 `appState.fullPositions/fullMaxHeights/fullMinHeights`。
