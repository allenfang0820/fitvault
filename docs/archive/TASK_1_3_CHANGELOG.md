# TASK_1_3_CHANGELOG

## 1. 修改文件列表

- `track.html`
- `TASK_1_3_CHANGELOG.md`

## 2. 新增 Orbit 输入链路

| 输入 | 行为 |
| -- | -- |
| `RIGHT_DOWN` | 进入自定义 Orbit 状态，记录起始鼠标位置、`startHeading`、`startPitch`，并停止自动旋转 |
| `MOUSE_MOVE` | Orbit 激活期间根据 `deltaX` 只计算 `heading`，根据 `deltaY` 只计算 `pitch` |
| `RIGHT_UP` | 退出自定义 Orbit 状态，清空起始鼠标位置 |

## 3. 被关闭的 Cesium 默认行为

- `cameraController.enableRotate = false`：关闭 Cesium 默认 rotate，避免与自定义 Orbit 同时改写 heading。
- `cameraController.enableTilt = false`：关闭 Cesium 默认 tilt，避免与自定义 Orbit 同时改写 pitch。
- `cameraController.rotateEventTypes = []`：清空 Cesium 默认 rotate 输入来源。
- `cameraController.tiltEventTypes = []`：清空 Cesium 默认 tilt 输入来源。

## 4. 与旧行为的差异

- 旧行为：`RIGHT_DRAG` 同时交给 Cesium 默认 `rotateEventTypes` 和 `tiltEventTypes`，水平/垂直输入可能混杂。
- 新行为：`RIGHT_DOWN + MOUSE_MOVE + RIGHT_UP` 由自定义 Orbit handler 接管。
- 新行为：水平拖动只影响 `heading = startHeading - deltaX * rotateSpeed`。
- 新行为：垂直拖动只影响 `pitch = startPitch - deltaY * pitchSpeed`。
- 新行为：`pitch` 使用 `Cesium.Math.clamp()` 限制在 `-90° ~ -20°`。
- 新行为：Orbit 过程中使用 `viewer.camera.setView({ orientation })` 实时更新，不使用 `flyTo()`。
- 新行为：Orbit 不重新计算 destination、center 或 `currentRange`。

## 5. 风险分析

- `slider lookAt`：滑块 pitch 控制仍保留原 `viewer.camera.lookAt(...)` 和 `lookAtTransform(Cesium.Matrix4.IDENTITY)` 解锁链路；本任务未改动该高敏感路径。
- `Compass`：指南针仍通过 `viewer.camera.changed` 同步 heading，并通过 `resetMapNorth()` 归北；自定义 Orbit 改变 heading 后会继续触发同步。
- `autoRotate`：用户 `RIGHT_DOWN` 主动 Orbit 时会清除 `rotateInterval` 并同步按钮 UI，避免自动旋转与手势 Orbit 抢 camera 控制权。
- `LEFT_CLICK`：打卡点仍复用同一个 `gestureHandler` 的 `LEFT_CLICK` 监听；本任务没有重写或删除该业务逻辑。
- `LEFT_DRAG`：左键平移仍由 Cesium `translateEventTypes = [LEFT_DRAG, TOUCH_DRAG]` 接管；本任务未接管左键拖拽。
- `setView orientation`：本任务按要求不改 destination/center/range，因此不会引入 flyTo 动画卡顿；实际体感仍需在触控板上验证旋转中心是否符合预期。

## 6. 回滚方法

如需恢复 Cesium 默认 Orbit：

- 将 `cameraController.enableRotate = false` 恢复为 `true`。
- 将 `cameraController.enableTilt = false` 恢复为 `true`。
- 将 `cameraController.rotateEventTypes = []` 恢复为 `[Cesium.CameraEventType.RIGHT_DRAG]`。
- 将 `cameraController.tiltEventTypes = []` 恢复为 `[Cesium.CameraEventType.RIGHT_DRAG]`。
- 删除自定义 Orbit 相关变量：`isOrbitingCamera`、`orbitStartPosition`、`orbitStartHeading`、`orbitStartPitch`、`orbitRotateSpeed`、`orbitPitchSpeed`。
- 删除 `RIGHT_DOWN`、`MOUSE_MOVE`、`RIGHT_UP` 三个自定义 `gestureHandler.setInputAction(...)`。
- 可保留 `stopAutoRotateForOrbit()`，但如果没有自定义 Orbit 调用它，该函数不会影响运行行为。

## 7. 验收结论

- ✅ 左键平移仍由 Cesium `LEFT_DRAG => translate` 控制。
- ✅ `LEFT_CLICK` 打卡点逻辑保持存在。
- ✅ 右键左右拖动只计算 heading。
- ✅ 右键上下拖动只计算 pitch。
- ✅ pitch 被限制在 `-90° ~ -20°`。
- ✅ Orbit 过程不调用 `flyTo()`。
- ✅ 用户 Orbit 时自动停止自动旋转。
- ✅ Compass 同步链路保持不变。
- ✅ 滑块 pitch 控制保持不变。
- ✅ 没有新增 UI。
- ✅ 没有重构地图系统。
