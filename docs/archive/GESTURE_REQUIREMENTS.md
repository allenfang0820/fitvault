# 地图应用手势操作需求文档

**版本**: v1.0  
**最后更新**: 2026-05-29  
**目标平台**: macOS (触摸板 + 鼠标)  
**技术栈**: CesiumJS 1.105 + 原生 DOM 事件 + ScreenSpaceEventHandler  

---

## 目录

1. [现有手势系统现状](#一现有手势系统现状)
2. [单指平移地图手势](#二单指平移地图手势)
3. [双指俯仰视角过渡手势](#三双指俯仰视角过渡手势)
4. [双指按住缩放手势](#四双指按住缩放手势)
5. [鼠标锚点捏合缩放手势](#五鼠标锚点捏合缩放手势)
6. [双指画圈旋转手势（Twist Gesture）](#六双指画圈旋转手势)
7. [多输入协同与 Camera Ownership 治理](#七多输入协同与-camera-ownership-治理)
8. [交互验收标准汇总](#八交互验收标准汇总)

---

## 一、现有手势系统现状

### 1.1 当前 Cesium 手势映射

| 手势 | Cesium 事件类型 | 当前行为 | 代码位置 |
|------|----------------|---------|---------|
| 左键拖拽 / 触摸拖拽 | `LEFT_DRAG` + `TOUCH_DRAG` | 平移地图（Cesium 原生） | L6639 |
| 右键 DOWN + MOVE + UP | 自定义 `ScreenSpaceEventHandler` | 自定义 Orbit (heading/pitch 解耦) | L6747-L6792 |
| 滚轮缩放 | `WHEEL` | 缩放（Cesium 原生） | L6643 |
| 触摸板捏合 | `PINCH` | 缩放（Cesium 原生） | L6643 |
| 左键单击 | 自定义 `LEFT_CLICK` | 场景拾取（打卡点 / 轨迹点） | L7652-L7673 |
| 左键双击 | 已移除 | 无操作 | L6649 |
| 滑块拖拽 | DOM `mousedown` / `touchstart` | pitch 角度过渡 (2D↔3D) | L6816-L6829 |
| 指南针按钮 | DOM `click` | 飞行至正北方向 | L6843 |

### 1.2 Camera Controller 配置

```javascript
cameraController.enableRotate   = false;   // Cesium 默认旋转已禁用
cameraController.enableTranslate = true;    // 平移启用
cameraController.enableZoom      = true;    // 缩放启用
cameraController.enableTilt      = false;   // 倾斜已禁用
cameraController.enableLook      = false;   // Look 已禁用

translateEventTypes: [LEFT_DRAG, TOUCH_DRAG]
zoomEventTypes:      [WHEEL, PINCH]
rotateEventTypes:    []   // 空——由自定义 Orbit 接管
tiltEventTypes:      []
lookEventTypes:      []

minimumZoomDistance: 100 (米)
maximumZoomDistance: 20000000 (米)
inertiaSpin:         0.85
inertiaTranslate:    0.85
```

### 1.3 Camera Ownership 优先级

所有相机操作必须先申请 ownership。优先级从低到高：

| 优先级 | Controller | 说明 |
|--------|-----------|------|
| 1 (最低) | `autorotate` | 自动旋转 |
| 2 | `compass` / `flyto` | 指南针归北 / flyTo 动画 |
| 3 | `slider` | 2D/3D 滑块 |
| 4 (最高) | `orbit` | 右键/双指 Orbit 操控 |

### 1.4 自定义 Orbit Camera 参数

| 参数 | 值 | 说明 |
|------|-----|------|
| `orbitSmoothing` | 0.15 | lerp 平滑系数 |
| `orbitRotateSpeed` | 0.004 | heading 灵敏度 |
| `orbitPitchSpeed` | 0.003 | pitch 灵敏度 |
| `orbitSettleThreshold` | 0.0001 | RAF 收敛停止阈值 |
| `orbitMinDeltaThreshold` | 0.5 px | deadzone 防抖 |
| pitch 范围 | -90° ~ -20° | 弧度制 |

---

## 二、单指平移地图手势

### 2.1 需求背景

当前平移功能由 Cesium 原生的 `LEFT_DRAG` 处理（L6639），缺少最小移动阈值和边缘阻尼。需增强两项行为以提升操作防误触和边界体验。

### 2.2 触发条件

| 项目 | 规格 |
|------|------|
| 输入设备 | 触摸板单指 / 鼠标左键 |
| 触发事件 | `LEFT_DRAG`（保留 Cesium `translateEventTypes` 映射） |
| 最小移动阈值 | **≥ 5px**（在 `MOUSE_MOVE` 回调中累计 delta 判断） |
| 无效操作过滤 | 仅在累计位移 ≥ 5px 后才开始更新 camera，之前的移动被丢弃 |

> **注意**: 如果在 `RIGHT_DOWN` 之后的 MOUSE_MOVE 中同时支持双指平移，需与 Orbit 互斥。Orbit 优先级更高（ownership = `"orbit"`），平移仅在 `activeCameraController === null` 时可执行。

### 2.3 交互效果

| 项目 | 规格 |
|------|------|
| 平移方向 | 手指移动方向与地图移动方向 1:1 线性对应（手指上移 → 地图内容向下移动，即摄像机向屏幕上方平移） |
| 比例关系 | 1:1（无加速度曲线），由 Cesium 的 `translateEventTypes` 原生行为保证 |
| 连续性 | 支持连续无缝平移，Cesium 内置惯性 (`inertiaTranslate = 0.85`) 保证松手后的惯性尾韵 |
| 帧率 | 不低于 60fps |

### 2.4 边界限制

| 项目 | 规格 |
|------|------|
| 边界行为 | 当地图平移至可视范围边缘时，添加**阻尼效果** |
| 阻尼实现 | 将平移增量乘以衰减因子 `Math.max(0, 1 - overshoot / maxOvershoot)`，产生渐进阻力感 |
| 禁止行为 | 禁止出现空白区域（禁止 camera 继续平移越过地球边缘） |
| 最大越界距离 | 建议 `maxOvershoot = 200px`（屏幕像素） |

> **实现考量**: 当前 Cesium 原生 `LEFT_DRAG` 不提供边缘阻尼。可通过监听 `camera.changed` 事件，在 moveEnd 时检测并回调 camera 位置实现。或通过自定义 `ScreenSpaceEventHandler` 接管 `LEFT_DRAG`。

### 2.5 验收标准

- [ ] 单指/左键移动 < 5px 时地图不响应
- [ ] 移动 ≥ 5px 后地图 1:1 跟随
- [ ] 松手后有惯性滑动
- [ ] 地图边缘松手后回弹，不出现空白
- [ ] Orbit 期间单指平移不执行（ownership 互斥）

---

## 三、双指俯仰视角过渡手势

### 3.1 需求背景

当前俯仰角度变化只能通过滑块（Slider）手动拖拽或 Orbit 右键拖拽实现。需新增触摸板双指轻扫操作，快速切换俯视/平视视角，提升浏览效率。

### 3.2 触发条件

| 项目 | 规格 |
|------|------|
| 输入设备 | 触摸板双指 |
| 手势类型 | **轻扫 (Swipe)**——双指不按下，仅在触摸板表面滑动 |
| 触发事件 | `wheel` 事件（macOS 中双指轻扫映射为 `wheel` 事件，`deltaY` 非零） |
| 与滚轮缩放区分 | 当 `event.ctrlKey === false` 且 `event.metaKey === false` 且无 `pinch` 检测时，`deltaY` 映射为 pitch 调整 |
| 方向判定 | `deltaY > 0`（向下轻扫）→ 平视转俯视（pitch 减小，更接近俯视）; `deltaY < 0`（向上轻扫）→ 俯视转平视（pitch 增大，更接近平视） |
| 速度阈值 | **≥ 100px/s**（对 `wheel` 事件的 `deltaY` 累积计算瞬时速度） |
| 无效操作过滤 | 速度 < 100px/s 的轻扫被忽略；单次 `wheel` 事件的 `|deltaY|` < 阈值也忽略 |

### 3.3 交互效果

| 项目 | 规格 |
|------|------|
| 过渡方式 | 从当前 pitch 到目标 pitch 的**平滑动画过渡** |
| 帧率 | **60fps**（使用 `requestAnimationFrame` 驱动） |
| 过渡时长 | 固定 **0.8 秒** |
| 缓动函数 | **缓入缓出贝塞尔曲线** `cubic-bezier(0.42, 0, 0.58, 1)` 或 Cesium `EasingFunction.SINE_IN_OUT` |
| 目标角度计算 | 每次轻扫触发后，以当前 pitch ± 固定步长 (建议 15°) 作为目标，而非基于 swipe 距离 |
| 动画不被打断 | 应保持当前动画到完成（或新 swipe 可中断并重新开始） |

### 3.4 角度限制

| 项目 | 规格 |
|------|------|
| 最小俯仰角 | **15°**（纯俯视，对应 Cesium pitch = -75°） |
| 最大俯仰角 | **90°**（纯平视，对应 Cesium pitch = 0°） |
| 边界行为 | 到达边界后动画立即终止于边界值，不越界 |
| Clamp 位置 | 在动画的目标值计算和每帧更新时均需 clamp |

> **注意**: Cesium 中 `camera.pitch` 为弧度制，负值表示向下看（俯视）。`-90° = -π/2` 为纯俯视（垂直向下），`0°` 为纯平视。用户侧角度定义为绝对值（15°~90°），内部需转换：`cesiumPitch = -Math.toRadians(userPitchDeg)`。

### 3.5 Ownership 治理

- `claimCameraOwnership("swipe-pitch")` 在动画开始时申请
- `releaseCameraOwnership("swipe-pitch")` 在动画结束时释放
- 优先级：低于 `orbit`(4)，高于 `autorotate`(1)，建议设为 2（与 compass 同级）
- 若 Orbit 正在运行，swipe-pitch 直接忽略

### 3.6 验收标准

- [ ] 双指向上轻扫 → 视角从俯视过渡到平视
- [ ] 双指向下轻扫 → 视角从平视过渡到俯视
- [ ] 慢速轻扫 (< 100px/s) 不触发
- [ ] 过渡动画流畅 (60fps)，0.8s 完成
- [ ] 角度锁定在 15°~90°，不越界
- [ ] Orbit 期间 swipe 不响应

---

## 四、双指按住缩放手势

### 4.1 需求背景

当前缩放由 Cesium 原生的 `PINCH`（捏合）事件处理。需新增一种备选缩放方式：双指按住后垂直拖拽缩放，提供更直观的缩放体验。

### 4.2 触发条件

| 项目 | 规格 |
|------|------|
| 输入设备 | 触摸板双指 |
| 手势类型 | **按住 + 垂直拖拽**——双指同时按下后，沿垂直方向同步移动 |
| 触发事件 | 自定义 `ScreenSpaceEventHandler` 的 `TOUCH_MOVE` 或 Pointer Events 序列检测 |
| 按下判定 | 两个触摸点同时 `pointerdown`，间隔 < 200ms，距离 > 10px |
| 方向判定 | 双指 **垂直移动**（Y 轴变化为主）：**下移 → Zoom Out**（缩小），**上移 → Zoom In**（放大） |
| 水平分量处理 | 若水平移动分量超过垂直分量的 50%，则判定为其他手势，不触发缩放 |

### 4.3 交互效果

| 项目 | 规格 |
|------|------|
| 缩放方式 | 地图比例尺随手指垂直移动距离**线性变化** |
| 缩放系数 | **0.1 倍 / 100px**（每垂直移动 100px，zoom level 变化 0.1 倍） |
| 画面稳定性 | 以屏幕中心为缩放锚点，缩放过程画面中心不动 |
| 连续性 | 手指移动过程中实时更新缩放级别 |
| 惯性 | 松手后可选惯性缩放，但在初始版本建议无惯性，松手即停 |

### 4.4 缩放限制

| 项目 | 规格 |
|------|------|
| 最小缩放距离 | `minimumZoomDistance = 100` 米（当前已配置于 L6646） |
| 最大缩放距离 | `maximumZoomDistance = 20000000` 米（当前已配置于 L6647） |
| 到边界行为 | 到达边界后 camera 停留在边界，手指可继续移动但不产生额外缩放；松手后再向反方向可正常缩放 |

### 4.5 Ownership 治理

- `claimCameraOwnership("two-finger-zoom")` 在双指按下且判定为垂直移动时申请
- `releaseCameraOwnership("two-finger-zoom")` 在双指抬起时释放
- 优先级：建议设为 3（与 slider 同级）
- Orbit 期间不触发此手势
- 与传统 PINCH 缩放的关系：两者共用 zoom 效果，但 PINCH 由 Cesium 原生处理且无 ownership；本手势需自定义实现

> **与 PINCH 捏合缩放的关系**: 两种缩放方式共存。PINCH（捏合）保留 Cesium 原生行为（以屏幕中心缩放），本手势提供垂直拖拽备选方案。当检测到双指按住垂直拖拽时，暂时阻止 Cesium 的 PINCH 事件触发。

### 4.6 验收标准

- [ ] 双指按住上移 → 地图放大
- [ ] 双指按住下移 → 地图缩小
- [ ] 每 100px 移动对应约 0.1x 缩放变化
- [ ] 缩放不超过预设最小/最大级别
- [ ] 缩放过程中画面中心稳定
- [ ] 双指水平移动 > 50% 垂直分量时不触发

---

## 五、鼠标锚点捏合缩放手势

### 5.1 需求背景

当前 Cesium 原生的 PINCH 缩放和 WHEEL 缩放均以屏幕中心为缩放锚点。需新增以鼠标光标位置为锚点的缩放行为，提供精确的目标导向缩放体验。

### 5.2 触发条件

| 项目 | 规格 |
|------|------|
| 输入设备 | 鼠标光标 + 触摸板捏合/张开 |
| 前置条件 | 鼠标光标停留在地图上的**任意目标位置** |
| 触发事件 | `PINCH` 事件（触摸板双指捏合/张开），且存在有效的鼠标光标位置 |
| 光标检测 | 通过 `mousemove` 事件跟踪最后一个 `{clientX, clientY}` 作为锚点 |
| 降级策略 | 若光标位置无效（光标在 canvas 外部），退回到 Cesium 默认的以屏幕中心缩放 |

### 5.3 交互效果

| 项目 | 规格 |
|------|------|
| 缩放锚点 | 鼠标光标停留的**地理坐标**（通过 `viewer.camera.getPickRay` + `globe.pick` 计算） |
| 锚点稳定性 | 缩放过程中，锚点始终保持在屏幕可视区域的**相同像素位置** |
| 实现方式 | 缩放前后调整 `camera.position` 的偏移量，使用 `camera.lookAt(anchorPoint, newRange)` |
| 动画帧率 | ≥ 60fps |

### 5.4 与 WHEEL 缩放的一致性

滚轮缩放 (`WHEEL`) 同样应支持鼠标锚点行为：当鼠标在地图上方时，滚轮缩放以鼠标位置为锚点。

### 5.5 Ownership 治理

- `claimCameraOwnership("pinch-zoom")` 在 pinch 开始时申请
- `releaseCameraOwnership("pinch-zoom")` 在 pinch 结束时释放
- 优先级：建议设为 3（与 slider 同级）
- Orbit 期间 pinch 仍可用（缩放不应被 Orbit 完全阻塞），但需通过 ownership 检查

### 5.6 验收标准

- [ ] 鼠标悬停在某地标上，双指捏合 → 以该地标为中心缩小
- [ ] 鼠标悬停在某地标上，双指张开 → 以该地标为中心放大
- [ ] 缩放过程中锚点屏幕位置不变
- [ ] 滚轮缩放同样以鼠标位置为锚点
- [ ] 鼠标在 canvas 外时退回到屏幕中心缩放
- [ ] 帧率 ≥ 60fps

---

## 六、双指画圈旋转手势（Twist Gesture）

### 6.1 需求背景

当前地图旋转仅能通过右键拖拽（Orbit Camera）或自动旋转按钮实现。需新增触摸板双指画圈旋转手势，提供更直觉的旋转操作。

### 6.2 触发条件

| 项目 | 规格 |
|------|------|
| 输入设备 | 触摸板双指 |
| 手势类型 | **画圈操作 (Twist)**——双指接触触摸板并做圆弧运动 |
| 方向判定 | **顺时针画圈 → 地图顺时针旋转**（heading 增大）; **逆时针画圈 → 地图逆时针旋转**（heading 减小） |
| 最小弧度阈值 | **≥ π/4 (45°)** 累计弧角变化才触发旋转 |
| 角度计算 | 以双指连线的中点为虚拟圆心，计算每帧连线角度变化，累加为 `accumulatedArc` |
| 无效操作过滤 | 累计弧角 < π/4 时的不触发旋转，但松手后重置 cumulative 状态 |

### 6.3 交互效果

| 项目 | 规格 |
|------|------|
| 旋转原点 | 屏幕的**几何中心**（`canvas.clientWidth/2`, `canvas.clientHeight/2`） |
| 角度映射 | 双指画圈的弧度与地图旋转角度 **1:1 匹配** |
| 旋转方式 | 修改 `camera.heading`，保持 pitch 和 range 不变 |
| 平滑度 | 使用 `requestAnimationFrame` 驱动更新，帧间无跳变 |
| 连续旋转 | 支持连续多圈旋转（heading 无上限，通过 `Cesium.Math.zeroToTwoPi` 规范化） |

### 6.4 旋转重置快捷操作

| 项目 | 规格 |
|------|------|
| 触发手势 | **双指连续点击触摸板两次**（Double Tap with two fingers） |
| 判定规则 | 两次 `pointerdown` 事件间隔 < 500ms，双指同时按下，且两次之间无明显移动 |
| 重置目标 | 地图旋转角度恢复至 **0°**（正北方向） |
| 过渡方式 | 0.4s 缓入缓出动画 (`Cesium.EasingFunction.SINE_IN_OUT`) |
| 与 Compass 的关系 | 复用 `resetMapNorth()` 逻辑，但 `claimCameraOwnership("twist-reset")` 代替 |

### 6.5 Ownership 治理

- `claimCameraOwnership("twist-rotate")` 在累计弧角 ≥ π/4 时申请
- `releaseCameraOwnership("twist-rotate")` 在双指抬起时释放
- 优先级：建议设为 4（与 orbit 同级，因为 twist 本质是旋转变体）
- `claimCameraOwnership("twist-reset")` 在双指双击检测到时申请
- Orbit 期间 twist 不响应

### 6.6 角度与方位感说明

| 用户视角 | heading 值 | 含义 |
|---------|-----------|------|
| 正北 | 0° | 地图上方为北 |
| 顺时针旋转 90° | 90° (π/2) | 地图上方为东 |
| 顺时针旋转 180° | 180° (π) | 地图上方为南 |
| 逆时针旋转 90° | 270° (3π/2) | 地图上方为西 |

### 6.7 验收标准

- [ ] 双指顺时针画圈 → 地图顺时针旋转
- [ ] 双指逆时针画圈 → 地图逆时针旋转
- [ ] 小弧度 (< 45°) 不触发旋转
- [ ] 旋转以屏幕中心为原点，画面稳定
- [ ] 双指双击 → 地图恢复 0° heading（正北）
- [ ] Orbit 期间 twist 不响应

---

## 七、多输入协同与 Camera Ownership 治理

### 7.1 手势互斥矩阵

以下矩阵描述同时发生两个手势时的处理规则：

| 手势 A ↓ / 手势 B → | 单指平移 | Orbit 旋转 | 俯仰轻扫 | 按住缩放 | 锚点捏合 | Twist 旋转 |
|---------------------|---------|-----------|---------|---------|---------|-----------|
| **单指平移** | — | Orbit 优先 | 平移优先 | N/A | N/A | N/A |
| **Orbit 旋转** | Orbit 优先 | — | Orbit 优先 | Orbit 优先 | 缩放允许 | Orbit 优先 |
| **俯仰轻扫** | 轻扫优先 | Orbit 优先 | — | 轻扫优先 | 缩放允许 | Twist 优先 |
| **按住缩放** | N/A | Orbit 优先 | 缩放优先 | — | 缩放优先 | Twist 优先 |
| **锚点捏合** | N/A | 缩放允许 | 缩放允许 | 缩放允许 | — | 缩放允许 |
| **Twist 旋转** | N/A | Orbit 优先 | Twist 优先 | Twist 优先 | 缩放允许 | — |

规则说明：
- "X 优先" = 手势 B 被忽略，仅执行手势 A
- "缩放允许" = 缩放可以与另一手势共存（camera range 独立于 rotation）
- "N/A" = 物理上不可同时发生（需要不同数量/类型的手指）

### 7.2 Ownership 优先级（完整）

| 优先级值 | Controller | 手势来源 | 说明 |
|---------|-----------|---------|------|
| 1 | `autorotate` | 自动旋转按钮 | 仅 idle 时运行 |
| 2 | `compass` | 指南针按钮 | 仅 idle 时运行 |
| 2 | `flyto` | flyTo 程序调用 | 导入轨迹后 |
| 2 | `swipe-pitch` | 双指轻扫 | 新增 |
| 2 | `twist-reset` | 双指双击 | 新增 |
| 3 | `slider` | 2D/3D 滑块 | 拖拽滑块 |
| 3 | `two-finger-zoom` | 双指按住缩放 | 新增 |
| 3 | `pinch-zoom` | 锚点捏合缩放 | 新增 |
| 4 | `orbit` | 右键/双指 Orbit | 最高优先级 |
| 4 | `twist-rotate` | 双指画圈旋转 | 新增，与 orbit 同级 |

### 7.3 通用规则

1. **所有手势的开始**必须调用 `claimCameraOwnership(controllerName)`，失败则直接 return
2. **所有手势的结束**必须调用 `releaseCameraOwnership(controllerName)`
3. **Orbit 开始时**强制停止 `autorotate`（调用 `stopAutoRotateForOrbit()`）
4. **RAF 每帧**检查 `hasCameraOwnership()`，ownership 丢失立即停止动画
5. **lookAtTransform 释放**统一走 `resetCameraTransformSafely()`，禁止各处直接调用

### 7.4 事件监听注册清单

当前 `gestureHandler` (`Cesium.ScreenSpaceEventHandler`) 已注册：

| 事件 | 用途 | 状态 |
|------|------|------|
| `RIGHT_DOWN` | Orbit 开始 | ✅ 已实现 |
| `MOUSE_MOVE` | Orbit 拖拽更新 | ✅ 已实现 |
| `RIGHT_UP` | Orbit 结束 | ✅ 已实现 |
| `LEFT_CLICK` | 场景拾取（打卡点） | ✅ 已实现 |

待注册的新事件：

| 事件 | 用途 | 处理方式 |
|------|------|---------|
| 双指 Swipe (wheel) | pitch 过渡 | 监听 `wheel` 事件于 `viewer.scene.canvas` |
| 双指按住 + 垂直拖拽 | 缩放 | 自定义 Pointer Events 序列 |
| 双指 Pinch + 鼠标锚点 | 锚点缩放 | 扩展 Cesium PINCH 行为 |
| 双指 Twist | 旋转 | 自定义 Pointer Events 序列 |
| 双指 Double Tap | 旋转重置 | 在 gestureHandler 中新增 |

---

## 八、交互验收标准汇总

### 8.1 功能完整性

- [ ] G1. 单指平移：5px deadzone + 边缘阻尼，不出现空白
- [ ] G2. 双指轻扫俯仰：swipe 触发，0.8s 贝塞尔过渡，角度 15°~90°
- [ ] G3. 双指按住缩放：垂直拖拽缩放，0.1x/100px 线性系数
- [ ] G4. 鼠标锚点缩放：PINCH/WHEEL 以鼠标位置为锚点
- [ ] G5. 双指旋转：弧角 ≥ π/4 触发，1:1 匹配
- [ ] G6. 双指双击：heading 重置为 0°（0.4s 动画）

### 8.2 性能指标

- [ ] P1. 所有动画帧率 ≥ 60fps
- [ ] P2. 手势响应延迟 < 16ms（从输入事件到首帧更新）
- [ ] P3. 无内存泄漏（RAF/callback 正确清理）

### 8.3 互斥与稳定性

- [ ] M1. Orbit 期间：平移、轻扫、旋转、按住缩放均不响应
- [ ] M2. 缩放与旋转可同时进行（不同 camera 属性）
- [ ] M3. 多个 gestureHandler 事件不会重复触发
- [ ] M4. Camera 不会出现抖动/漂移/锁死
- [ ] M5. ownership 状态在所有手势结束后正确恢复为 `null`

### 8.4 兼容性

- [ ] C1. LEFT_CLICK 打卡点功能不受影响
- [ ] C2. Slider 2D/3D 过渡滑块功能不受影响
- [ ] C3. Compass 指南针归北功能不受影响
- [ ] C4. autoRotate 自动旋转功能不受影响
- [ ] C5. 轨迹 flyTo 和 bbox 逻辑不受影响
- [ ] C6. 导入/导出/剖面图等功能不受影响
- [ ] C7. 不新增 UI 组件，不改变现有布局

### 8.5 边界与容错

- [ ] E1. 所有角度/距离参数有 clamp 保护
- [ ] E2. 手势识别失败时有降级策略（如锚点获取失败时回退到屏幕中心）
- [ ] E3. 异常情况下 ownership 不会永久锁定（超时自动释放）
- [ ] E4. 触摸板与鼠标输入可正常切换，不产生遗留状态
