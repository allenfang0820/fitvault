# TASK_1_6_CHANGELOG

## 1. 新增 Ownership 状态

- `activeCameraController`：当前持有 camera 主控制权的控制器。
- 允许值：`orbit`、`slider`、`autorotate`、`flyto`、`compass`、`null`。
- 当前实现为轻量状态变量，仍保留在 `track.html` 的 Cesium camera controller 初始化区域附近。

## 2. 新增 Ownership API

- `claimCameraOwnership(controllerName)`：申请 camera 控制权。
- `releaseCameraOwnership(controllerName)`：释放 camera 控制权。
- `hasCameraOwnership(controllerName)`：判断当前控制器是否持有 camera 控制权。
- `resetCameraTransformSafely()`：统一释放 Cesium `lookAtTransform(Matrix4.IDENTITY)`，避免 transform ownership 分散。

## 3. Ownership 优先级

```txt
orbit > slider > compass/flyto > autorotate
```

当前优先级映射：

| Controller | Priority |
| -- | -- |
| `orbit` | 4 |
| `slider` | 3 |
| `compass` | 2 |
| `flyto` | 2 |
| `autorotate` | 1 |

## 4. 被治理的 Camera 冲突

- Orbit vs autoRotate：`RIGHT_DOWN` 先停止 autoRotate，再申请 `orbit` ownership。
- Orbit vs Slider：Slider 必须申请 `slider` ownership；Orbit 持有时 slider 无法抢占。
- Orbit vs Compass：Compass 点击时如果 `activeCameraController !== null` 直接返回，不抢占 Orbit。
- Slider vs RAF：Orbit RAF 每帧检查 `hasCameraOwnership('orbit')`，ownership 丢失会立即停止写 camera。
- autoRotate vs 其它控制器：autoRotate 只有成功申请 `autorotate` ownership 才能启动，interval 每帧检查 ownership。
- lookAtTransform ownership：直接调用已收口到 `resetCameraTransformSafely()`。

## 5. RAF 生命周期治理

- Orbit RAF 每帧开头检查 `hasCameraOwnership('orbit')`。
- 如果 ownership 丢失，立即停止当前 RAF 链路：清空 `orbitAnimationFrame`、`orbitFocusPoint`、`orbitRange`、`orbitReleaseFocusWhenSettled`。
- Orbit 正常收敛完成后释放 `orbit` ownership。
- `RIGHT_UP` 时如果 RAF 已结束，则立即释放 `orbit` ownership；如果 RAF 仍在惯性收敛，则等收敛完成后释放。

## 6. Safe Transform Reset

- 新增 `resetCameraTransformSafely()` 作为唯一 transform reset 出口。
- 统一封装：`viewer.camera.lookAtTransform(Cesium.Matrix4.IDENTITY)`。
- 用途：避免 Orbit、Slider、autoRotate、轨迹加载等路径分散调用 transform reset，降低锁死和并发释放风险。

## 7. 风险分析

- `slider lookAt`：Slider 仍使用 `viewer.camera.lookAt(...)`，但 input 前必须持有 `slider` ownership；结束时统一释放 transform 和 ownership。
- `flyTo ownership`：轨迹加载 `flyTo` 尚未完整纳入 ownership，当前仅保留原行为并统一 transform reset；后续如果要治理导入/启动动画，需要对 `flyto` 做显式 claim/release。
- `Compass`：Compass reset 在非 idle 状态下直接忽略，避免 Orbit/Slider 期间硬抢 camera；用户可能需要在操作结束后再次点击 Compass。
- `autoRotate`：autoRotate 低优先级，无法抢占 Orbit/Slider/Compass；用户 Orbit 时会被停止。
- `setViewProfile()`：剖面按钮仍走 `updateCamera()`，当前没有单独 ownership 名称；后续如继续扩展相机系统，建议纳入 `flyto` 或新增 `profile` controller。

## 8. 回滚方法

如需恢复无 ownership 治理状态：

- 删除 `activeCameraController` 和 `cameraControllerPriority`。
- 删除 `claimCameraOwnership()`、`releaseCameraOwnership()`、`hasCameraOwnership()`。
- 删除 Orbit RAF 中的 `hasCameraOwnership('orbit')` 检查和 `releaseCameraOwnership('orbit')`。
- 删除 `RIGHT_DOWN`、Slider、Compass、autoRotate 中的 ownership claim/release 判断。
- 将 `resetCameraTransformSafely()` 调用恢复为直接 `viewer.camera.lookAtTransform(Cesium.Matrix4.IDENTITY)`。

## 9. 验收结论

- ✅ Orbit 时 Slider 不能抢 camera。
- ✅ Orbit 时 Compass 不抢 camera。
- ✅ autoRotate 不再与 Orbit 并发。
- ✅ Orbit RAF ownership 丢失后会停止。
- ✅ `lookAtTransform` 已统一到 `resetCameraTransformSafely()`。
- ✅ Slider 仍保留原 lookAt 控制链路。
- ✅ Compass 仍保留 idle 时归北能力。
- ✅ LEFT_CLICK 打卡点逻辑未改动。
- ✅ 左键平移配置未改动。
- ✅ 没有新增 UI。
- ✅ 没有重构地图系统。
