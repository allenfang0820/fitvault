# 任务：活动详情页轨迹缩略图升级为 Canvas 2D 真实比例渲染（方案 B+）

> 立项依据：docs/activity_detail_track_snapshot_feasibility.md 调研结论
> 契约参考：fit-arch-contrac §2.1 / §五 AI 边界 / §九 目录与依赖 / §十 Non-Goals
> 工作量：0.5 个工作日 | 后端改动：0 | 新增依赖：0

---

## 一、目标

将活动详情页（`activity-detail-overlay`）主视觉区的轨迹缩略图，从**固定 760×180 画布的 SVG 简单投影**，升级为**保持真实物理比例的 Canvas 2D 自适应渲染**。

### 现状（要废弃的行为）

- 画布固定 760×180
- 等距矩形投影 + 画布比例 4.22:1
- 经抽样 8 个真实活动，**长宽比失真 72%~93%**（跑步南北向轨迹被横向拉伸 8-15 倍；圆形操场环被压成线段）

### 目标行为

- 画布**按真实物理比例自适应**（最大 760×220，留 14px 边距）
- HiDPI/Retina 屏清晰（`devicePixelRatio` 感知）
- 渐变描边 + 起终点标点
- 点击跳转 3D 沉浸分析（行为保持不变）
- 100% 本地，零网络，零新依赖

---

## 二、范围与边界

### 2.1 必须做

1. 新增函数 `buildTrackThumbnailCanvas(points, containerWidth, containerHeight)` 返回 `<canvas>` DOM 元素
2. 替换 [track.html:6086](file:///Users/fanglei/应用开发/AI track/track.html#L6086) 的调用点（`renderActivityDetail` 内）
3. 保留 `<div class="detail-track-thumb" onclick="jumpToTraceFromActivityDetail(id)">` 包装层与点击行为
4. 保留 "点击进入 3D 沉浸分析" 提示文案
5. 空态降级（无 GPS / `thumbnail_points` 为空）保持现有分支（[track.html:6087-6088](file:///Users/fanglei/应用开发/AI track/track.html#L6087-L6088)）

### 2.2 不许做

- ❌ **不许**引入任何新 JS 库（无 D3 / 无 ECharts / 无 Mapbox / 无 Leaflet）
- ❌ **不许**改后端（`main.py` / `profile_backend.py` 零改动）
- ❌ **不许**改 DB schema
- ❌ **不许**改 `get_activity_detail` API 返回结构（`thumbnail_points` 字段已存在且正确）
- ❌ **不许**触碰 Cesium 容器
- ❌ **不许**写 `activities` 表 / `ai_snapshots` 表
- ❌ **不许**把 `shadow_diff` 引入渲染管线
- ❌ **不许**新增任何 Python 文件或前端文件（仅修改 `track.html`）
- ❌ **不许**修改 [buildTrackThumbnailSvg](file:///Users/fanglei/应用开发/AI track/track.html#L5997-L6024)（保留 SVG 路径作为备选/对比，但默认调用改 Canvas）

### 2.3 §五 AI 边界契约

- 本任务**纯前端绘制**，**不进入 AI 链路**
- 渲染前不构造任何 `_ai_snapshot` 输入
- 完成后**不刷新 AI 会话**

---

## 三、实施步骤

### Step 1：实现 `buildTrackThumbnailCanvas`

在 `track.html` 中 **`buildTrackThumbnailSvg` 函数紧邻位置**（约 [track.html:5997](file:///Users/fanglei/应用开发/AI track/track.html#L5997) 上方或下方）新增函数。

**完整代码**（**严格按此实现，不要自行"优化"**）：

```javascript
/**
 * 活动详情页轨迹缩略图（Canvas 2D 真实比例版）
 *
 * 契约：
 *   - 入参 points: Array<{lat: number, lon: number}> 来自 record.thumbnail_points
 *   - 返回: HTMLCanvasElement（HiDPI 感知） 或 空字符串（无数据时）
 *   - 投影: 等距矩形 + 真实物理宽高比自适应
 *   - 性能: 48 采样点, < 3ms 单次绘制
 *   - 零依赖, 零网络
 */
function buildTrackThumbnailCanvas(points, containerWidth, containerHeight) {
    const valid = (points || []).filter(p =>
        typeof p.lat === 'number' && typeof p.lon === 'number'
    );
    if (!valid.length) return '';

    // ---- 1. 真实物理范围（球面距离近似，缩略图尺度可接受）----
    const lats = valid.map(p => p.lat);
    const lons = valid.map(p => p.lon);
    const minLat = Math.min(...lats), maxLat = Math.max(...lats);
    const minLon = Math.min(...lons), maxLon = Math.max(...lons);
    const midLat = (minLat + maxLat) / 2;
    // 1° 纬度 ≈ 110.54 km; 1° 经度 ≈ 111.32 km × cos(lat)
    const latSpanM = (maxLat - minLat) * 110540;
    const lonSpanM = (maxLon - minLon) * 111320 * Math.cos(midLat * Math.PI / 180);
    const realRatio = (latSpanM > 0 && lonSpanM > 0) ? (lonSpanM / latSpanM) : 1;

    // ---- 2. 自适应 viewBox（保持真实比例 + 14px 边距）----
    const pad = 14;
    const maxW = containerWidth || 760;
    const maxH = containerHeight || 220;
    let viewW = maxW - pad * 2;
    let viewH = maxH - pad * 2;
    if (realRatio > viewW / viewH) {
        // 经度方向更长 → 以宽为约束, 高度收缩
        viewH = viewW / realRatio;
    } else {
        // 纬度方向更长或正方形 → 以高为约束, 宽度收缩
        viewW = viewH * realRatio;
    }

    // ---- 3. HiDPI 清晰 ----
    const dpr = window.devicePixelRatio || 1;
    const canvas = document.createElement('canvas');
    canvas.width = maxW * dpr;
    canvas.height = maxH * dpr;
    canvas.style.width = maxW + 'px';
    canvas.style.height = maxH + 'px';
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);

    // ---- 4. 真实比例投影 ----
    const lonRange = (maxLon - minLon) || 0.0001;
    const latRange = (maxLat - minLat) || 0.0001;
    const scaleX = (p) => pad + ((p.lon - minLon) / lonRange) * viewW;
    const scaleY = (p) => pad + ((maxLat - p.lat) / latRange) * viewH;

    // ---- 5. 渐变描边 ----
    const grad = ctx.createLinearGradient(0, 0, maxW, maxH);
    grad.addColorStop(0, '#34d399');
    grad.addColorStop(1, '#38bdf8');

    // ---- 6. 绘制轨迹 polyline ----
    ctx.beginPath();
    ctx.lineWidth = 3;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.strokeStyle = grad;
    valid.forEach((p, i) => {
        const x = scaleX(p), y = scaleY(p);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // ---- 7. 起终点标点 ----
    const startP = valid[0], endP = valid[valid.length - 1];
    const sx = scaleX(startP), sy = scaleY(startP);
    const ex = scaleX(endP), ey = scaleY(endP);
    // 起点：白底
    ctx.fillStyle = '#f8fafc';
    ctx.strokeStyle = 'rgba(15, 23, 42, 0.6)';
    ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.arc(sx, sy, 5, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    // 终点：黄色
    ctx.fillStyle = '#fbbf24';
    ctx.beginPath(); ctx.arc(ex, ey, 5, 0, Math.PI * 2); ctx.fill(); ctx.stroke();

    return canvas;
}
```

### Step 2：替换调用点

**文件位置**：[track.html:6086](file:///Users/fanglei/应用开发/AI track/track.html#L6086) 附近的 `renderActivityDetail` 函数内。

**原代码**：
```javascript
trackContainer.innerHTML = '<div class="detail-track-thumb" onclick="jumpToTraceFromActivityDetail(' + record.id + ')">' + buildTrackThumbnailSvg(record.thumbnail_points) + '<div class="detail-track-tip">点击进入 3D 沉浸分析(轨迹分析工具)</div></div>';
```

**新代码**（**严格替换，不要添加额外逻辑**）：
```javascript
// B+ Canvas 真实比例版（替代 SVG 固定比例）
const _canvas = buildTrackThumbnailCanvas(record.thumbnail_points, 760, 220);
if (_canvas) {
    const _wrap = document.createElement('div');
    _wrap.className = 'detail-track-thumb';
    _wrap.onclick = function() { jumpToTraceFromActivityDetail(record.id); };
    const _tip = document.createElement('div');
    _tip.className = 'detail-track-tip';
    _tip.innerText = '点击进入 3D 沉浸分析(轨迹分析工具)';
    _wrap.appendChild(_canvas);
    _wrap.appendChild(_tip);
    trackContainer.innerHTML = '';
    trackContainer.appendChild(_wrap);
} else {
    trackContainer.innerHTML = '<div class="detail-track-tip" style="color:#94a3b8;">当前活动无可用轨迹文件,无法生成轨迹地图。</div>';
}
```

**注意**：
- 外层 `<div class="detail-track-thumb">` 保留（CSS 已写好 [track.html:1426-1440](file:///Users/fanglei/应用开发/AI track/track.html#L1426-L1440)）
- onclick 跳转行为保持一致
- 提示文案"点击进入 3D 沉浸分析(轨迹分析工具)"保留
- 空态文案保留原样

### Step 3：CSS 微调（仅当需要时）

如果新 canvas 在 `.detail-track-thumb` 内显示异常（边距 / 高度 / 居中），按需在 [track.html:2869-2884](file:///Users/fanglei/应用开发/AI track/track.html#L2869-L2884) 区段微调。

**推荐增量**（**先看效果再决定是否加**）：
```css
.overview-main-visual .detail-track-thumb canvas {
    display: block;
    margin: 0 auto;
    max-width: 100%;
    height: auto;
}
```

### Step 4：保留 SVG 函数作为参考

**不要删除** `buildTrackThumbnailSvg`（[track.html:5997-6024](file:///Users/fanglei/应用开发/AI track/track.html#L5997-L6024)）。它仍在以下场景被消费：
- 任何依赖 SVG 节点的旧代码（grep 确认无新调用即可）
- 调试/对比用途

---

## 四、验收标准

### 4.1 视觉验收（手工）

| # | 场景 | 期望 |
|---|---|---|
| V1 | 跑团环线（约 1km 圈） | 视觉上是**接近圆形**的椭圆，不是横向拉长的椭圆 |
| V2 | 南北向长跑 10km | 视觉上是**纵向长条**（高>宽），不是横向拉伸 |
| V3 | 东西向城市骑行 20km | 视觉上是**横向长条**（宽>高） |
| V4 | 高 DPI 屏（Retina）截图 | 边缘清晰无锯齿 |
| V5 | 深色模式 | 渐变绿→蓝在深色背景下清晰可见 |
| V6 | 点击缩略图 | 正常跳转到 3D 沉浸分析（`jumpToTraceFromActivityDetail`） |
| V7 | 无 GPS 活动（室内） | 显示"当前活动无可用轨迹文件..."（空态分支不进入 Canvas） |
| V8 | `thumbnail_points` 为空数组 | 同上（空态降级） |

### 4.2 性能验收

- 单次绘制 < 3ms（48 采样点，DevTools Performance 实测）
- 详情页打开到缩略图可见 < 50ms
- 内存：每次开/关详情页无累积（canvas 节点随旧 DOM 一起释放）

### 4.3 契约验收

- [ ] `main.py` / `profile_backend.py` **零改动**（`git diff` 验证）
- [ ] 无新依赖加入 `requirements.txt` / `track.html` script 标签
- [ ] `docs/js_api_contract.json` **不需更新**（无新 API）
- [ ] AI 链路（`_ai_snapshot` / `_chat_messages`）**零影响**
- [ ] `shadow_diff` **零引用**
- [ ] `get_activity_detail` 返回结构**不变**

### 4.4 测试验收

新增单元测试文件 `tests/test_track_thumbnail_canvas.py`：

| # | 用例 | 断言 |
|---|---|---|
| T1 | 48 点矩形轨迹 | 真实物理宽高比下不超出 viewBox |
| T2 | 0 点 / null | 返回 `''` |
| T3 | 单点 | 返回 `''`（退化） |
| T4 | 极扁轨迹（lat_span ≈ 0） | 高度自适应收缩，不超 viewBox |
| T5 | 极高轨迹（lon_span ≈ 0） | 宽度自适应收缩，不超 viewBox |
| T6 | 南北向跑（lon/lat 比 = 0.3） | 生成的 canvas height > width |
| T7 | 东西向骑（lon/lat 比 = 5） | 生成的 canvas width > height |
| T8 | 起终点标点 | 起点白色 r=5，终点黄色 r=5 |

**实现提示**：JSDOM + `node-canvas` mock，断言 `canvas.width` / `canvas.height` / 不抛异常。

### 4.5 lint 验收

- [ ] 既有 `tests/` 全绿
- [ ] 无新增 TypeError / ReferenceError
- [ ] track.html 无新增 lint 错误

---

## 五、回滚预案

如发现 Canvas 渲染在某些边界情况异常：

**回滚 1 行**（将 Step 2 的新代码换回原 SVG 路径）：
```javascript
trackContainer.innerHTML = '<div class="detail-track-thumb" onclick="jumpToTraceFromActivityDetail(' + record.id + ')">' + buildTrackThumbnailSvg(record.thumbnail_points) + '<div class="detail-track-tip">点击进入 3D 沉浸分析(轨迹分析工具)</div></div>';
```

`buildTrackThumbnailCanvas` 函数可保留供未来再次启用。

---

## 六、交付物清单

| # | 文件 | 类型 | 状态 |
|---|---|---|---|
| 1 | `track.html` | 修改（新增 1 函数 + 替换 1 段） | ⏳ |
| 2 | `track.html` CSS | 视情况微调 | ⏳ 可选 |
| 3 | `tests/test_track_thumbnail_canvas.py` | 新增 | ⏳ |
| 4 | `docs/activity_detail_track_snapshot_feasibility.md` | 文档更新（方案 B+ 为推荐） | ⏳ |
| 5 | `docs/js_api_contract.json` | **不更新**（无新 API） | ✅ |
| 6 | `main.py` / `profile_backend.py` | **不更新** | ✅ |

---

## 七、禁止事项（再次强调）

> §十 Non-Goals 红线

- ❌ **不**允许加地图底图（违反 Non-Goals「不做 SaaS / 不上云」）
- ❌ **不**允许引第三方地图库（违反 §9.3 lib/ 本地加载）
- ❌ **不**允许走 Cesium（用户明确"不需要底图" + 静态快照 vs 3D 球职责分离）
- ❌ **不**允许做轨迹动画/转场（避免过早工程化，先解决核心比例问题）
- ❌ **不**允许做 hover 交互（当前 V9.2 §E11 职责明确：仅展示+跳转）
- ❌ **不**允许触碰 §5.5 轨迹报告 v3 边界（不在本任务范围）

---

## 八、执行确认

执行完成后需向用户报告：

1. 修改了哪些行（行号 + 简要 diff）
2. 4.1 视觉验收 V1~V8 是否通过（截图或文字描述）
3. 4.2 性能验收数字
4. 4.4 测试通过数
5. 是否有任何"意外发现"（比如某些活动的 `thumbnail_points` 异常）

> **本提示词为最终交付物，提交后进入"执行 → 验收 → 文档更新"三步流程。**
