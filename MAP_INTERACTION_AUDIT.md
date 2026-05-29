# MAP_INTERACTION_AUDIT

## 1. 地图 SDK 信息

- 项目当前地图 SDK：CesiumJS。
- 本地 SDK 入口：`track.html` 通过 `lib/Cesium/Cesium.js` 加载。
- 本地资源基础路径：`window.CESIUM_BASE_URL = 'lib/Cesium/'`。
- CDN 回退版本：`cesium@1.105.1`，用于 `Widgets/widgets.css` 和 `Build/Cesium/Cesium.js`。
- 初始化入口文件：`track.html`。
- 初始化函数：`initCesiumViewer()`。
- 初始化调用链：`DOMContentLoaded` / `pywebviewready` → `bootstrapApplication()` → `initCesiumViewer()`。
- Viewer 初始化容器：`new Cesium.Viewer('cesiumContainer', ...)`。
- 底图来源：`Cesium.UrlTemplateImageryProvider`，URL 为 `https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png`。
- 地形来源：`Cesium.EllipsoidTerrainProvider()`。
- 当前没有发现 `mapboxgl.Map(...)` 初始化入口。

关键位置：
- `track.html:L9-L12`：Cesium base URL 与 CSS 本地优先/CDN 回退。
- `track.html:L2674-L2683`：Cesium JS 本地优先/CDN 回退。
- `track.html:L5184-L5221`：`initCesiumViewer()` 与 `new Cesium.Viewer(...)`。
- `track.html:L7046-L7057`：应用启动后调用 `initCesiumViewer()`。

## 2. 当前 Interaction 配置表

| Interaction | 当前状态 | 来源文件 | 来源位置 | 风险 |
|---|---:|---|---|---|
| interactive | Cesium Viewer 默认交互启用，未显式关闭 | `track.html` | `L5197-L5212` | 正常，Cesium 默认可交互 |
| dragPan / translate | 开启；显式映射为 `LEFT_DRAG`、`TOUCH_DRAG` | `track.html` | `L6576-L6585` | 与 macOS Maps 左键/单指平移一致 |
| dragRotate / rotate | 开启；显式映射为 `RIGHT_DRAG` | `track.html` | `L6576-L6585` | 与 macOS 触控板“双指按住拖拽旋转”目标一致，但右键浏览器菜单依赖 Cesium 是否拦截 |
| tilt / pitch | 开启；显式映射为 `RIGHT_DRAG` | `track.html` | `L6576-L6585` | 与 rotate 共用 `RIGHT_DRAG`，可能造成旋转/俯仰耦合 |
| scrollZoom / wheel zoom | 开启；显式映射为 `WHEEL` | `track.html` | `L6585` | 符合触控板双指滚动缩放，但实际平滑度依赖 Cesium 默认实现 |
| pinch zoom | 开启；显式映射为 `PINCH` | `track.html` | `L6585` | 正常，移动端/触控板兼容性依赖浏览器事件实现 |
| middle drag zoom | 开启；显式映射为 `MIDDLE_DRAG` | `track.html` | `L6585` | 桌面鼠标可用，macOS 触控板不常用 |
| boxZoom | 未发现显式配置 | `track.html` | 无 | Cesium 不等同 Mapbox `boxZoom`；当前未作为业务交互使用 |
| doubleClickZoom | 未发现显式配置 | `track.html` | 无 | Cesium 默认行为可能存在，未被当前代码显式治理 |
| keyboard | 未发现 Cesium keyboard 显式配置 | `track.html` | 无 | 页面存在非地图快捷键，地图键盘控制来源不清晰 |
| pitchWithRotate | Cesium 无同名配置；当前 pitch 与 rotate 同由 `RIGHT_DRAG` 控制 | `track.html` | `L6583-L6584` | 旋转与俯仰绑定在同一物理手势，存在误触可能 |
| touchPitch | 未发现独立显式配置 | `track.html` | 无 | 触控俯仰主要由 Cesium 默认触摸逻辑和当前事件映射共同决定 |
| enableLook | 关闭 | `track.html` | `L6581` | 正常，避免自由视角 look 与地图导航冲突 |
| inertiaSpin | `0.85` | `track.html` | `L6586` | 正常，提供旋转惯性 |
| inertiaTranslate | `0.85` | `track.html` | `L6587` | 正常，提供平移惯性 |
| minimumZoomDistance | `100` | `track.html` | `L6588` | 正常，限制过近缩放 |
| maximumZoomDistance | `20000000` | `track.html` | `L6589` | 正常，限制过远缩放 |

## 3. 当前事件监听器列表

| Event | 文件 | 监听对象 | 用途 | 风险 |
|---|---|---|---|---|
| `DOMContentLoaded` | `track.html:L7046` | `document` | 启动应用，准备调用地图初始化 | 正常 |
| `pywebviewready` | `track.html:L7050` | `window` | pywebview 环境准备后启动应用 | 正常 |
| `keydown` | `track.html:L3412` | `document` | AI 私教快捷键 `Meta/Ctrl + Shift + A` | 与地图键盘控制可能重叠，但当前不是地图控制 |
| `pointerdown` | `track.html:L3426` | AI 私教拖拽 handle | 拖动 AI 浮窗 | 非地图事件；若浮层覆盖地图，可能阻断地图拖拽 |
| `pointermove` | `track.html:L3431` | AI 私教拖拽 handle | 拖动 AI 浮窗 | 非地图事件；有移动状态管理 |
| `pointerup` | `track.html:L3442` | AI 私教拖拽 handle | 结束 AI 浮窗拖动 | 非地图事件 |
| `click` | `track.html:L4765` | 分页按钮 | 分页切换 | 非地图事件 |
| `click` | `track.html:L6565` | `#btn-auto-rotate` | 开启/停止自动旋转相机 | 地图相机控制来源之一 |
| `mousedown` | `track.html:L6613` | `#map-view-slider` | 记录滑块拖拽焦点、heading、range | 地图相机控制来源之一 |
| `touchstart` | `track.html:L6614` | `#map-view-slider` | 记录滑块触控拖拽焦点、heading、range | 地图相机控制来源之一 |
| `input` | `track.html:L6615` | `#map-view-slider` | 连续修改相机 pitch | 地图相机控制来源之一，高耦合 `lookAt` |
| `mouseup` | `track.html:L6620` | `window` | 结束滑块拖拽并释放 `lookAtTransform` | 必须保留，否则可能锁死平移 |
| `touchend` | `track.html:L6621` | `window` | 结束滑块触控拖拽并释放 `lookAtTransform` | 必须保留，否则可能锁死平移 |
| `touchcancel` | `track.html:L6622` | `window` | 异常结束触控拖拽并释放 `lookAtTransform` | 必须保留，否则可能锁死平移 |
| `camera.changed` | `track.html:L6625` | `viewer.camera` | 同步指南针旋转和滑块 value | 地图相机状态同步来源之一 |
| `click` | `track.html:L6637` | `#map-compass-btn` | 指南针一键归北 | 地图相机控制来源之一 |
| `keydown` | `track.html:L7090` | `#sport-records-page-jump` | 运动记录页码 Enter 跳转 | 非地图事件 |
| `keydown` | `track.html:L7096` | `#history-page-jump` | 历史页码 Enter 跳转 | 非地图事件 |
| `LEFT_CLICK` | `track.html:L7446-L7467` | `Cesium.ScreenSpaceEventHandler(viewer.scene.canvas)` | 点击地图编辑/新增打卡点 | 地图业务关键逻辑，不能轻易动 |
| `click` | `track.html:L7469` | `#profile-canvas` | 点击剖面图新增打卡点 | 与地图打卡点逻辑耦合 |

未发现当前代码中存在以下手写地图 canvas 监听：
- `canvas.addEventListener('wheel', ...)`
- `canvas.addEventListener('contextmenu', ...)`
- `ScreenSpaceEventType.LEFT_DOWN`
- `ScreenSpaceEventType.LEFT_UP`
- `ScreenSpaceEventType.MOUSE_MOVE`

## 4. Camera 控制权分析

### 4.1 控制权总览

| Camera 属性 | 控制来源 | 文件位置 | 说明 | 风险 |
|---|---|---|---|---|
| `center` / 初始目标 | `viewer.camera.setView(...)` | `track.html:L5196-L5217` | 初始定位到中国附近高空 | 正常 |
| `center` / 轨迹目标 | `applyDataAndRender()` 内部 `viewer.camera.flyTo(...)` | `track.html:L6475-L6483` | 导入/加载轨迹后根据轨迹 bbox 计算中心 | 依赖轨迹点合法性 |
| `heading` | Cesium 原生手势 `RIGHT_DRAG` | `track.html:L6583` | 用户右键/触控板双指按住拖拽控制 | 与 tilt 共用手势，存在耦合 |
| `heading` | 自动旋转按钮 `setInterval(updateCamera)` | `track.html:L6565-L6574` | 每 30ms 增加 heading | **高风险：与用户手势、指南针归北、滑块同步并发控制** |
| `heading` | 指南针归北 `resetMapNorth()` | `track.html:L6559-L6561` | `flyToBoundingSphere(... heading=0.0 ...)` | 与自动旋转并发时可能互相抢控制权 |
| `heading` | 滑块拖动开始时锁定 `dragHeading` | `track.html:L6597-L6602` | 滑块调整 pitch 期间保持拖动开始时的 heading | 拖动期间其他 heading 变化不会进入滑块控制 |
| `pitch` | Cesium 原生手势 `RIGHT_DRAG` / `tiltEventTypes` | `track.html:L6584` | 用户右键/触控板双指按住拖拽控制 | 与 rotate 共用手势 |
| `pitch` | 剖面按钮 `setViewProfile()` | `track.html:L6530` | 设置 pitch 为 `0` | 与 2D/3D 滑块语义不同 |
| `pitch` | 滑块 `#map-view-slider input` | `track.html:L6615-L6619` | 连续设置 pitch 为 `-value` 度 | **高风险：使用 `lookAt`，依赖松手释放 transform** |
| `pitch` | 轨迹加载后 `flyTo` | `track.html:L6483` | 设置初始轨迹视角 pitch 为 `-85°` | 正常 |
| `zoom` / `range` | Cesium 原生 `WHEEL` / `PINCH` / `MIDDLE_DRAG` | `track.html:L6585` | 用户缩放 | 正常，平滑性由 Cesium 控制 |
| `zoom` / `range` | `currentRange` 与 `getCameraFocusRange()` | `track.html:L6542-L6546` | 归北/滑块使用当前相机到焦点距离 | 与真实 Cesium zoom 概念不完全等价 |
| `zoom` / `range` | 轨迹加载 `currentRange` | `track.html:L6476-L6483` | 根据轨迹范围计算初始高度 | 大范围/非法点可能异常 |
| `center` | `getCameraFocusPoint()` | `track.html:L6532-L6540` | 通过屏幕中心射线与 globe 求交 | 失败时 fallback 到 `appState.centerPosition` |

### 4.2 多来源控制风险

<span style="color:red">高风险：`heading` 当前至少由 Cesium 原生手势、自动旋转按钮、指南针归北、滑块拖动期间的锁定 heading 共同影响。</span>

<span style="color:red">高风险：`pitch` 当前至少由 Cesium 原生 tilt、剖面按钮、轨迹加载 flyTo、滑块 input 连续 lookAt 共同影响。</span>

<span style="color:red">高风险：`range/zoom` 当前由 Cesium 原生缩放、轨迹加载 currentRange、归北/滑块焦点 range 计算共同影响。</span>

最敏感链路：
- `#map-view-slider input` → `viewer.camera.lookAt(...)` → `mouseup/touchend/touchcancel` → `viewer.camera.lookAtTransform(Cesium.Matrix4.IDENTITY)`。
- 如果结束事件未触发或被浮层/浏览器行为吞掉，Cesium 原生平移可能被 transform 锁住。

## 5. 右键行为分析

- 当前代码未发现手写 `contextmenu` 监听器。
- 当前 Cesium 控制器将 `rotateEventTypes` 和 `tiltEventTypes` 都绑定到 `Cesium.CameraEventType.RIGHT_DRAG`。
- 右键单击是否弹出浏览器菜单，取决于 Cesium 内部对 canvas 右键/拖拽事件的处理；项目代码没有额外屏蔽浏览器右键菜单。
- 当前右键拖拽被用于地图旋转和倾斜，属于地图交互核心输入。
- 风险：如果 macOS 触控板“双指点按”被浏览器解释为 context menu，而不是右键拖拽，用户可能看到菜单或无法稳定触发旋转。

## 6. 滚轮缩放行为分析

- 当前缩放由 Cesium 原生控制器接管。
- 显式配置：`zoomEventTypes = [MIDDLE_DRAG, WHEEL, PINCH]`。
- 未发现自定义 `wheel` 拦截、节流、缩放 step 或 deltaMode 解析。
- 当前缩放体验应表现为 Cesium 默认连续缩放，是否具备惯性取决于 Cesium 内部实现和浏览器/触控板事件。
- 当前只设置了 `inertiaSpin` 与 `inertiaTranslate`，未发现显式设置 zoom inertia 参数。
- 风险：macOS 触控板双指滚动会直接进入 Cesium `WHEEL`，但其自然程度与 macOS Maps 的橡皮筋/惯性不一定一致。

## 7. 当前 UI 控件来源

| 控件 | 来源 | 文件位置 | 说明 | 风险 |
|---|---|---|---|---|
| Cesium 默认 baseLayerPicker | SDK 默认控件但显式关闭 | `track.html:L5203` | `baseLayerPicker: false` | 无 |
| Cesium 默认 geocoder | SDK 默认控件但显式关闭 | `track.html:L5204` | `geocoder: false` | 无 |
| Cesium 默认 homeButton | SDK 默认控件但显式关闭 | `track.html:L5205` | `homeButton: false` | 无 |
| Cesium 默认 navigationHelpButton | SDK 默认控件但显式关闭 | `track.html:L5207` | `navigationHelpButton: false` | 无 |
| Cesium 默认 sceneModePicker | SDK 默认控件但显式关闭 | `track.html:L5208` | `sceneModePicker: false` | 无 |
| Cesium timeline / animation | SDK 默认控件但显式关闭 | `track.html:L5209-L5210` | `timeline: false`, `animation: false` | 无 |
| Cesium fullscreenButton | SDK 默认控件但显式关闭 | `track.html:L5211` | `fullscreenButton: false` | 无 |
| 右侧滑块 | 自定义控件 | `track.html:L2285-L2293` | `#map-view-slider` 控制 pitch | 与相机 lookAt 强耦合 |
| Compass | 自定义控件 | `track.html:L2291-L2293`, `L6637` | `#map-compass-btn` 点击归北，`#compass-pointer` 实时旋转 | 与相机 changed 事件耦合 |
| 自动旋转 | 自定义控件 | `track.html:L2310`, `L6565-L6574` | 点击后 setInterval 驱动 heading | 与用户手势抢控制权 |
| 剖面视角 | 自定义控件 | `track.html:L2309`, `L6530` | 设置 pitch 为 0 | 与滑块 pitch 语义冲突 |
| 放大/缩小按钮 | 未发现当前自定义地图 zoom 按钮 | 无 | 当前没有 SDK NavigationControl | 无 |

## 8. 与 macOS 原生体验冲突项

1. 右键/双指按住拖拽同时承担旋转与俯仰：符合当前重映射目标，但在实际触控板上可能出现旋转和 tilt 混杂。
2. 右键 context menu 未被项目层显式处理：可能与 macOS 双指点按/右键菜单冲突。
3. 页面 `<body>` 设置 `touch-action: none` 和 `overscroll-behavior: none`：有利于阻止页面滚动，但可能影响浏览器默认触控行为与可访问性。
4. `#map-view-slider` 使用 `lookAt` 连续控制 pitch：如果松手解锁链路失效，会与原生平移冲突。
5. 自动旋转按钮通过 `setInterval` 高频改写 heading：用户手势操作期间可能抢占相机控制权，不符合原生地图“用户输入优先”的体验。
6. 剖面按钮 `setViewProfile()` 设置 pitch 为 `0`：与当前滑块 3D/2D 的 `30°-90°` 俯仰范围语义不一致。
7. Cesium 默认双击缩放、键盘导航等行为未显式审计/关闭：可能与 macOS Maps 预期存在差异。
8. Compass、滑块、自动旋转、轨迹加载 flyTo 都能改变相机：控制权分散，不符合 macOS 原生交互通常的单一手势优先模型。

## 9. 后续重构风险分析

### 9.1 不能轻易动的逻辑

- `gestureHandler.setInputAction(... LEFT_CLICK ...)`：负责点击地图编辑/新增打卡点，是地图业务关键链路。
- `profile-canvas` click：负责剖面图点击新增打卡点，与地图打卡点行为共享 `openAddModal()`。
- `getCameraFocusPoint()`：归北和滑块都依赖屏幕中心射线求交，改变后会影响“原地运镜”。
- `viewer.camera.lookAtTransform(Cesium.Matrix4.IDENTITY)`：滑块交互结束后必须释放 transform，不能删除。
- `applyDataAndRender()` 内轨迹 bbox 和 `flyTo`：导入轨迹后首屏定位依赖该逻辑。

### 9.2 耦合严重的文件/区域

- `track.html` 单文件同时包含 HTML、CSS、Cesium 初始化、地图交互、轨迹渲染、AI 面板、历史抽屉、配置和导入逻辑。
- `track.html:L6521-L6637` 是相机控制集中区，但 `LEFT_CLICK` 打卡点逻辑位于 `L7443-L7467`，同一个 `gestureHandler` 跨越较远代码区域使用。
- 顶部工具条通过内联 `onclick` 调用相机函数，事件生命周期不集中。
- 后端 `main.py` 负责 pywebview 注入、轨迹导入和新轨迹通知，虽不直接控制相机，但会触发前端加载轨迹后重置 camera。

### 9.3 可能导致回归 bug 的行为

- 移除或重建 `gestureHandler` 可能导致地图点击新增打卡点失效。
- 调整 `RIGHT_DRAG` 映射可能改变当前旋转/倾斜入口。
- 调整 `TOUCH_DRAG` 可能影响移动端/触控板平移。
- 调整 `lookAt` / `lookAtTransform` 时机可能导致地图松手后无法平移。
- 改动 `currentRange` 计算可能导致归北、滑块、轨迹加载后的距离不一致。
- 修改 `body touch-action` 可能引入页面滚动、浏览器缩放或触控板事件分发变化。
- 自动旋转未统一停止时，后续新增手势重构可能出现“相机自己动”的误判。

## 10. 验收结论

- ✅ 本次审计没有修改任何地图交互逻辑。
- ✅ 本次审计没有新增任何地图功能。
- ✅ 本次审计没有调整 UI。
- ✅ 已明确当前地图 SDK、初始化入口和资源加载方式。
- ✅ 已明确当前 interaction 配置来源。
- ✅ 已明确 camera 控制链路和多来源控制风险。
- ✅ 已列出与 macOS 原生体验的主要冲突项。
- ✅ 已列出后续重构时不能轻易动的逻辑和高风险耦合点。
