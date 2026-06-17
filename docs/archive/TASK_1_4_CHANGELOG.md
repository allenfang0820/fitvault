# TASK_1_4_CHANGELOG

## 1. 新增 Orbit 动画状态

- `targetHeading`：Orbit 输入产生的目标 heading。
- `targetPitch`：Orbit 输入产生的目标 pitch，已在输入阶段 clamp 到 `-90° ~ -20°`。
- `currentHeading`：逐帧逼近目标的当前 heading。
- `currentPitch`：逐帧逼近目标的当前 pitch。
- `orbitAnimationFrame`：`requestAnimationFrame` 动画句柄，用于避免重复启动循环并在收敛后停止。

## 2. Orbit Smoothing 参数

| 参数 | 当前值 | 作用 |
| -- | -- | -- |
| `orbitSmoothing` | `0.15` | 每帧插值比例，让当前角度渐进逼近目标角度 |
| `orbitMinDeltaThreshold` | `0.5` | 过滤触控板微小抖动输入 |
| `orbitRotateSpeed` | `0.004` | 横向拖动到 heading 的灵敏度 |
| `orbitPitchSpeed` | `0.003` | 纵向拖动到 pitch 的灵敏度 |
| `orbitSettleThreshold` | `0.0001` | target 与 current 足够接近时停止 RAF 循环 |

## 3. 新增动画链路

| 阶段 | 行为 |
| -- | -- |
| `RIGHT_DOWN` | 停止自动旋转，记录起始鼠标位置，并同步 `currentHeading/currentPitch` 与 `targetHeading/targetPitch` |
| `MOUSE_MOVE` | 只更新 `targetHeading` 与 `targetPitch`，不直接 `setView()` |
| `requestAnimationFrame` | 启动 `orbitAnimationLoop()` |
| `lerp` | `currentHeading/currentPitch` 按 `orbitSmoothing` 逐帧逼近 target |
| `setView` | 每帧通过 `viewer.camera.setView({ orientation })` 更新实时 Orbit |
| `RIGHT_UP` | 结束输入状态，但 RAF 继续收敛到 target，形成轻微惯性尾韵 |

## 4. 性能治理

- `MOUSE_MOVE` 不再直接更新 camera，只更新 target 并调度 RAF。
- `scheduleOrbitAnimation()` 会检查 `orbitAnimationFrame !== null`，避免重复创建动画循环。
- `orbitAnimationLoop()` 在 heading 与 pitch 误差都小于 `0.0001` 时停止继续调度 RAF。
- 动画收敛时会将 `currentHeading/currentPitch` 对齐到 `targetHeading/targetPitch`，避免无限微抖。
- 未引入 `setTimeout`、CSS transition、第三方 easing/tween 库。

## 5. 风险分析

- `slider lookAt`：滑块仍使用 `viewer.camera.lookAt(...)` 与 `lookAtTransform(Cesium.Matrix4.IDENTITY)`，本任务没有改变该链路；如果滑块操作发生在 RAF 尚未完全收敛后，下一次 Orbit 会从当前 camera 姿态重新同步状态。
- `Compass camera.changed`：Orbit RAF 每帧 `setView()` 会触发 `viewer.camera.changed`，指南针会持续同步 heading，这是预期行为。
- `autoRotate`：仍在 `RIGHT_DOWN` 时停止自动旋转，避免 RAF Orbit 与自动旋转同时控制 camera。
- `LEFT_CLICK`：打卡点逻辑仍保留在原 `gestureHandler` 上，本任务未改动。
- `LEFT_DRAG`：左键平移仍由 Cesium translate 控制，本任务未接管左键输入。

## 6. 回滚方法

如需恢复 Task 1.3 的“即时 Orbit”：

- 删除 `currentHeading`、`currentPitch`、`targetHeading`、`targetPitch`、`orbitAnimationFrame`、`orbitSmoothing`、`orbitMinDeltaThreshold`、`orbitSettleThreshold`。
- 删除 `shortestHeadingDelta()`、`orbitAnimationLoop()`、`scheduleOrbitAnimation()`。
- 在 `MOUSE_MOVE` 中恢复直接计算 `heading` / `pitch` 并立即调用 `viewer.camera.setView({ orientation })`。
- 保留 `RIGHT_DOWN` 记录 `orbitStartPosition`、`orbitStartHeading`、`orbitStartPitch`。
- 保留 `RIGHT_UP` 退出 Orbit 状态。

## 7. 验收结论

- ✅ Orbit 输入已从即时 `setView()` 改为 `target → RAF → lerp → setView()`。
- ✅ heading/pitch 继续解耦。
- ✅ pitch clamp 继续作用于 `targetPitch`。
- ✅ deadzone 已用于过滤触控板微小抖动。
- ✅ 动画循环可在收敛后自动停止。
- ✅ 停止拖动后 RAF 会继续轻微收敛，形成惯性尾韵。
- ✅ Compass 同步链路保持不变。
- ✅ Slider 链路保持不变。
- ✅ autoRotate 仍会在用户 Orbit 时停止。
- ✅ 没有新增 UI。
- ✅ 没有重构地图系统。
