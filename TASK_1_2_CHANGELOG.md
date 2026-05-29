# TASK_1_2_CHANGELOG

## 1. 修改文件列表

- `track.html`
- `TASK_1_2_CHANGELOG.md`

## 2. 新增治理项

| 项目 | 修改 | 原因 |
| -- | -- | -- |
| Cesium Look | 保持 `enableLook = false`，并新增 `lookEventTypes = []` | 显式禁止自由视角 FPS look 模式，避免非地图导航行为进入默认交互 |
| Rotate / Tilt | 保留 `RIGHT_DRAG => rotate/tilt`，并补充兼容态注释 | 当前仍需保留右键 Orbit 行为，同时标明这是 Orbit 重构前的临时兼容态 |
| Zoom 输入源 | 将 `zoomEventTypes` 从 `[MIDDLE_DRAG, WHEEL, PINCH]` 收口为 `[WHEEL, PINCH]` | 未发现业务依赖 `MIDDLE_DRAG`；MacBook 触控板不存在 middle mouse，缩放来源收敛到 wheel/pinch |
| Double click zoom | 对 `viewer.screenSpaceEventHandler` 移除 `LEFT_DOUBLE_CLICK` 默认动作 | 避免双击地图触发不可控默认缩放，缩放只保留 wheel/pinch |
| Canvas 右键菜单 | 仅在 `viewer.scene.canvas` 上监听 `contextmenu` 并 `preventDefault()` | 避免 macOS 双指点击时弹出浏览器右键菜单，不影响 document、输入框、AI 面板和调试 |

## 3. 保持不变的行为

- 左键拖拽仍映射为 `LEFT_DRAG => translate`，地图平移行为保持不变。
- 触控拖拽仍映射为 `TOUCH_DRAG => translate`，触控平移行为保持不变。
- 右键拖拽仍映射为 `RIGHT_DRAG => rotate/tilt`，当前 Orbit 兼容行为保持不变。
- `LEFT_CLICK` 打卡点逻辑未改动，`gestureHandler.setInputAction(... LEFT_CLICK)` 保持原样。
- 滑块 pitch 控制未改动，仍通过 `viewer.camera.lookAt(...)` 连续调整 pitch。
- 滑块释放链路未改动，仍通过 `viewer.camera.lookAtTransform(Cesium.Matrix4.IDENTITY)` 解锁。
- Compass 归北未改动，仍通过 `resetMapNorth()` 和 `flyToBoundingSphere(...)` 控制 heading。
- 自动旋转未改动，仍通过 `#btn-auto-rotate` 和 `setInterval(updateCamera)` 驱动。
- 轨迹加载后的 `flyTo` 未改动。
- UI/CSS/HTML 结构未改动。

## 4. 风险分析

- `RIGHT_DRAG` 当前仍同时承担 rotate 与 tilt，存在旋转/俯仰耦合；这是后续 Orbit Camera 重构前的兼容状态。
- `MIDDLE_DRAG` 已关闭；搜索结果显示没有业务代码依赖 middle drag zoom，但外接三键鼠标用户会失去中键拖拽缩放能力。
- `LEFT_DOUBLE_CLICK` 默认缩放已关闭；如果用户习惯双击缩放，需要未来通过明确的 zoom widget 或显式交互重新提供。
- `contextmenu` 仅在 Cesium canvas 层阻止，不影响页面其它区域；如果后续 canvas 上需要调试右键菜单，可临时回滚该监听。
- 滑块仍依赖 `lookAt` 与 `lookAtTransform(Matrix4.IDENTITY)` 解锁链路，本任务未改动该高敏感链路。

## 5. 回滚方法

如需撤销本次默认行为治理，可在 `track.html` 中执行以下反向修改：

- 删除 `cameraController.lookEventTypes = [];`。
- 将 `cameraController.zoomEventTypes` 恢复为 `[Cesium.CameraEventType.MIDDLE_DRAG, Cesium.CameraEventType.WHEEL, Cesium.CameraEventType.PINCH]`。
- 删除 `viewer.screenSpaceEventHandler.removeInputAction(Cesium.ScreenSpaceEventType.LEFT_DOUBLE_CLICK);` 相关代码块。
- 删除 `viewer.scene.canvas.addEventListener('contextmenu', function(e) { e.preventDefault(); });`。
- 可保留 `RIGHT_DRAG` 兼容态注释；该注释不影响运行行为。

## 6. 验收结论

- ✅ 左键平移映射保持不变。
- ✅ 左键点击打卡点逻辑保持不变。
- ✅ 右键 rotate/tilt 映射保持不变。
- ✅ 滑块 pitch 控制保持不变。
- ✅ Compass 归北保持不变。
- ✅ 自动旋转保持不变。
- ✅ Cesium canvas 不再触发浏览器默认右键菜单。
- ✅ 没有新增 UI。
- ✅ 没有重构地图系统。
- ✅ interaction 配置更显式、更可控。
