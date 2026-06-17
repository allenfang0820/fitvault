# TASK_1_5_CHANGELOG

## 1. 新增 Orbit 空间状态

- `orbitFocusPoint`：`RIGHT_DOWN` 时捕获的屏幕中心地表空间锚点。
- `orbitRange`：相机到 `orbitFocusPoint` 的距离，Orbit 期间保持不变。
- `orbitReleaseFocusWhenSettled`：右键释放后，如果 RAF 仍在收敛，则延迟释放焦点，避免惯性尾韵阶段失去空间锚点。

## 2. Focus Point 获取链路

| 阶段 | 行为 |
| -- | -- |
| screen center | 使用 `viewer.scene.canvas.clientWidth / 2` 与 `clientHeight / 2` 取得屏幕中心 |
| getPickRay | 使用 `viewer.camera.getPickRay(screenCenter)` 从屏幕中心生成射线 |
| globe.pick | 使用 `viewer.scene.globe.pick(ray, viewer.scene)` 获取地表交点 |
| orbitFocusPoint | 将地表交点缓存在 `orbitFocusPoint`，仅在 `RIGHT_DOWN` 捕获一次 |
| orbitRange | 使用 `Cesium.Cartesian3.distance(camera.position, orbitFocusPoint)` 记录当前距离 |

## 3. Orbit 输出链路变化

| 版本 | 输出方式 | 行为 |
| -- | -- | -- |
| Task 1.4 | `camera.setView({ orientation })` | 只更新 heading/pitch，属于 orientation-only Orbit |
| Task 1.5 | `camera.lookAt(orbitFocusPoint, HeadingPitchRange)` | 围绕固定空间锚点更新 heading/pitch/range，减少低空 3D 漂移感 |

当前 RAF 链路为：

```txt
RIGHT_DOWN pick focus once
→ MOUSE_MOVE 更新 targetHeading / targetPitch
→ requestAnimationFrame
→ currentHeading / currentPitch lerp target
→ lookAt(orbitFocusPoint, HeadingPitchRange)
```

## 4. Fallback 行为

- 如果 `globe.pick(...)` 返回 `null`，`orbitFocusPoint` 不成立。
- 如果 `orbitRange <= 0`，固定锚点 Orbit 不成立。
- 上述场景会退化为 Task 1.4 的 `camera.setView({ orientation })`。
- fallback 不抛错、不阻断 Orbit 输入，也不影响 LEFT_CLICK、Slider、Compass。

## 5. 性能治理

- `globe.pick(...)` 只在 `RIGHT_DOWN` 执行一次。
- RAF 每帧不重新 pick，避免 CPU 飙升、focus jitter 和中心点漂移。
- `orbitFocusPoint` 在 `RIGHT_UP` 后释放；如果 RAF 惯性尾韵尚未结束，则等收敛后释放。
- RAF 收敛停止条件仍沿用 `orbitSettleThreshold = 0.0001`。

## 6. 风险分析

- `slider lookAt`：滑块仍使用自己的 `viewer.camera.lookAt(...)` 链路；本任务没有修改滑块。如果滑块在 Orbit RAF 收敛期间被操作，下一次 Orbit 会重新捕获新的屏幕中心焦点。
- `camera.lookAtTransform`：固定锚点 Orbit 每帧 `lookAt(...)` 后调用 `lookAtTransform(Cesium.Matrix4.IDENTITY)`，避免 lookAt transform 锁死后续 Cesium 平移。
- `Compass camera.changed`：Orbit 每帧仍触发 camera changed，指南针会持续同步 heading，这是预期行为。
- `autoRotate`：仍在用户 `RIGHT_DOWN` 时停止，避免自动旋转与空间锚点 Orbit 竞争。
- `focus fallback`：太空视角或地球边缘 pick 失败时会退化为 orientation-only Orbit，空间锚点效果会降低，但交互不会崩溃。

## 7. 回滚方法

如需恢复 Task 1.4 的 orientation-only Orbit：

- 删除 `orbitFocusPoint`、`orbitRange`、`orbitReleaseFocusWhenSettled`。
- 删除 `pickOrbitFocusPoint()`。
- 删除 `applyOrbitCamera()` 中的 `lookAt(orbitFocusPoint, HeadingPitchRange)` 分支。
- 在 `orbitAnimationLoop()` 中恢复直接 `viewer.camera.setView({ orientation })`。
- 删除 `RIGHT_DOWN` 中捕获 `orbitFocusPoint` 和计算 `orbitRange` 的代码。
- 删除 `RIGHT_UP` 中延迟释放 focus 的代码。

## 8. 验收结论

- ✅ RAF smoothing 继续保留。
- ✅ Orbit 输出已从 orientation-only `setView` 升级为固定空间锚点 `lookAt`。
- ✅ `orbitFocusPoint` 只在 `RIGHT_DOWN` 捕获一次。
- ✅ `orbitRange` 在 Orbit 期间保持不变。
- ✅ pick 失败时有 `setView` fallback。
- ✅ `lookAtTransform(Cesium.Matrix4.IDENTITY)` 已用于释放 transform。
- ✅ Compass 链路保持不变。
- ✅ Slider 链路保持不变。
- ✅ LEFT_CLICK 打卡点逻辑保持不变。
- ✅ 左键平移配置保持不变。
- ✅ 没有新增 UI。
- ✅ 没有重构地图系统。
