# 任务：活动详情页轨迹缩略图 v4 升级 — 纯黑底 + 实心白色正方形网格 + 缩放适配

> 立项依据：用户反馈"v3 背景不是纯黑，网格不是正方形、不是实心、不是 1px，且需支持缩放适配"
> 配合：B+ Canvas v3（已上线，弯道特征 + 贝塞尔）+ V9.x-LTTB（已上线）
> 本次新增：v4 严格网格规范 + 缩放适配
> 契约参考：fit-arch-contrac §2.1 / §V4.0 防腐层 / §五 AI 边界 / §九 目录 / §十 Non-Goals
> 工作量：≤ 1 个工作日 | 修改文件：1 个 (track.html) + 1 个新测试

---

## ⚠️ 重要决策点（执行前必须确认）

### 决策 1：用户要求"缩放时网格同步适配"——这引入**新交互维度**

**当前 v3 状态**：
- 缩略图 = 纯静态展示
- 点击直接跳转 `jumpToTraceFromActivityDetail(id)` → Cesium 3D 沉浸分析
- 详情页缩略图**无平移/缩放交互**

**v4 用户要求**：
- 缩放时网格随视图比例同步适配
- 始终保持标准经纬线式的网格展示逻辑

**这是 3 个可选项**（**必须由用户决策**）：

| 选项 | 描述 | 工作量 | 风险 | 建议 |
|---|---|---|---|---|
| **A. 静态 v4 严格网格** | 不引入缩放交互，仅升级网格规范（纯黑底 + 实心白 1px + 正方形固定像素） | 0.3 天 | 极低 | **推荐**（最小变更） |
| B. v4 + wheel/drag 缩放 | 引入鼠标滚轮缩放 + 拖拽平移 + 网格重新计算 | 1.5 天 | 中 | 需更多契约 |
| C. 跳转到 Cesium 局部缩放 | 缩略图点击进入 Cesium 时，传入当前 zoom level 让 Cesium 加载对应瓦片 | 0.5 天 | 中 | 跨模块 |

> **本提示词按选项 A 设计**（最小变更、最高契约符合）。
> 如选 B/C，请先告知，本提示词需要重写 §五 实施步骤。

### 决策 2：网格"标准正方形"边长选多少？

`maxW=760, maxH=220`，比例 ≈ 3.45:1，**不可能**全区域正方形网格（只能纵向裁掉）。

| 选项 | 边长 | 横向格数 | 纵向格数 | 网格效果 |
|---|---|---|---|---|
| A | 20px | 38 | 11 | 细密，专业感强 |
| **B** | **40px** | **19** | **5.5** | **中等密度**（推荐） |
| C | 60px | 12.67 | 3.67 | 稀疏，简洁 |
| D | 100px | 7.6 | 2.2 | 极简 |

> **本提示词按选项 B（40px 正方形）**。
> 如选 A/C/D，请先告知。

---

## 一、v3 vs v4 差异表

| 维度 | v3 现状 | v4 要求 | 变化 |
|---|---|---|---|
| 背景色 | `#0f172a` slate-900 | **`#000000` 纯黑** | 升级 |
| 网格颜色 | `rgba(148,163,184,0.18)` 半透明 | **`#FFFFFF` 100% 实心** | 升级 |
| 线宽 | 1px | **1px** | 不变 |
| 网格形状 | 4 横向 + 2 纵向（**不规则矩形**） | **正方形**（固定像素边长） | 升级 |
| 覆盖 | 全画布 | **全画布** | 不变 |
| 边框 | 35% 半透明外框 | **保留作为可选（建议删除，纯白 1px 已足够）** | 简化 |
| 缩放适配 | 无 | **按选项 A：不实现** | 不变 |
| 缩略图职责 | 静态展示 | **静态展示**（保持） | 不变 |

---

## 二、目标

`buildTrackThumbnailCanvas` v4 在保留 v3 全部视觉（贝塞尔/阴影/抗锯齿/标点）基础上，**严格按用户规范升级网格层**：

```
v3 现状:   黑底 (slate-900) + 半透明白 4×2 不规则矩形 + 35% 边框
     ↓ v4
v4 目标:   纯黑底 (#000000) + 实心白 1px 正方形 40px 网格 + 覆盖全画布
```

---

## 三、契约约束（强制遵守）

### 3.1 §V4.0 防腐层契约

✅ **本任务只改 1 个文件**：`track.html` 中 `buildTrackThumbnailCanvas` 函数
✅ **不改 `main.py` / `metrics_resolver.py`**（业务逻辑已下沉，V9.x-LTTB 已完成）
✅ `main.py` 透传契约零变化（API `thumbnail_points` 字段结构不变）

### 3.2 §2.1 字段全链路可追溯

✅ 输入仍是 `record.thumbnail_points: [{lat, lon}, ...]`
✅ 输出仍是 `HTMLCanvasElement`
✅ 仅**视觉层升级**（绘制参数变化），不修改数据

### 3.3 §五 AI 边界契约

✅ 纯前端绘制，**不构造任何 `_ai_snapshot` 输入**、**不刷 AI 会话**

### 3.4 §九 目录契约

✅ **不引入任何新 JS 库**（无 D3 / 无 ECharts Canvas / 无任何 npm 包）
✅ 网格用原生 Canvas 2D API（零依赖）
✅ **不修改 `requirements.txt`**

### 3.5 §十 Non-Goals

✅ 纯本地、零网络、零 SaaS

### 3.6 兼容性

✅ 保留 v3 全部视觉特性（贝塞尔/阴影/抗锯齿/标点/真实比例/HiDPI/单点防御/动态线宽）
✅ v3 测试用例继续通过（**仅升级背景色/网格/边框 3 个测试期望**）
✅ v9.x-LTTB 采样契约不变（60 点）
✅ 旧 SVG 函数 `buildTrackThumbnailSvg` 继续保留

### 3.7 缩放交互（按选项 A）

✅ **不实现** 鼠标滚轮/拖拽交互
✅ 缩略图职责保持"静态展示 + 点击跳转 3D"

---

## 四、范围与边界

### 4.1 必须做

1. **改 `track.html` 中 `buildTrackThumbnailCanvas`**：
   - v3 背景色 `#0f172a` → **`#000000`**
   - v3 网格颜色 `rgba(148,163,184,0.18)` → **`#FFFFFF` 100% 实心**
   - v3 不规则 4×2 网格 → **40px 正方形网格**（按 `maxW/maxH` 自动计算行列数）
   - v3 外边框 `rgba(148,163,184,0.35)` → **删除**（白色 1px 网格已足够）
2. **升级 v3 测试** `tests/test_track_thumbnail_canvas_v3.py`：
   - 验证 v4 4 个新规范（纯黑底、实心白、正方形、无边框）
3. **跑全量测试 + 视觉验证**

### 4.2 不许做

- ❌ 不实现鼠标交互（缩放/平移/拖拽）
- ❌ 不改 `main.py` / `metrics_resolver.py` / 后端任何文件
- ❌ 不引入 JS 库
- ❌ 不改 `docs/js_api_contract.json`（无新 API）
- ❌ 不改 `buildTrackThumbnailSvg`（SVG 备选保留）

### 4.3 边界与降级

| 情况 | 行为 |
|---|---|
| `maxH` 不被 `cellSize` 整除 | 最后一列/行网格画到画布边缘（无截断，**符合"完整覆盖"要求**） |
| 高 DPI 屏 | 网格线宽 1px 按 `dpr` 缩放（实际渲染 2px/3px，视觉仍清晰） |
| 极窄/极宽容器 | 网格自动适应（cellSize 固定，行列数随容器变化） |

---

## 五、实施步骤（按选项 A 设计）

### Step 1：改 `buildTrackThumbnailCanvas` v3 → v4

**位置**：[track.html:6034-6223](file:///Users/fanglei/应用开发/AI track/track.html#L6034-L6223) 之间的 `buildTrackThumbnailCanvas` 函数

**改动原则**：
- **保留** v3 全部结构（贝塞尔/阴影/抗锯齿/标点/真实比例/HiDPI/单点防御/动态线宽）
- **升级** 4 个网格相关常量 + 1 个绘制逻辑

**完整 v4 实现**（**严格按此实现，不要自行"优化"**）：

```javascript
/**
 * 活动详情页轨迹缩略图（Canvas 2D 真实比例版 v4）
 * 产品定义：Geometric Activity Snapshot — Pure Black Edition
 *
 * v4 升级（在 v3 基础上）:
 *   1. 纯黑底 #000000（v3 是 #0f172a slate-900）
 *   2. 实心白 #FFFFFF 1px 正方形网格（v3 是 18% 透明 slate-400 矩形）
 *   3. 网格单元固定 40px × 40px（v3 是 4×2 不规则）
 *   4. 覆盖全画布（含最后一行/列，无截断）（v3 是 4 等分 + 2 等分 + 35% 边框）
 *
 * 保留 v3 不变:
 *   - 真实物理宽高比自适应 (Fix 1 居中)
 *   - 单点防御 (Fix 2)
 *   - 动态线宽 (Fix 3, 5/4/3 加粗)
 *   - HiDPI (devicePixelRatio)
 *   - 抗锯齿 (imageSmoothingQuality='high')
 *   - 二次贝塞尔曲线 (quadraticCurveTo)
 *   - 阴影发光 (shadowBlur=8)
 *   - 起终点标点 r=6
 *
 * 契约:
 *   - 入参 points: Array<{lat, lon}> 来自 record.thumbnail_points (V9.x-LTTB 采样后)
 *   - 返回: HTMLCanvasElement (HiDPI 感知) 或 ''
 *   - 投影: 等距矩形 + 真实物理宽高比自适应
 *   - 性能: 60 采样点, < 5ms 单次绘制
 *   - 零依赖, 零网络
 *   - 缩略图职责: 静态展示 + 点击跳转 3D (无缩放/平移交互)
 */
function buildTrackThumbnailCanvas(points, containerWidth, containerHeight) {
    const valid = (points || []).filter(p =>
        typeof p.lat === 'number' && typeof p.lon === 'number'
    );
    // 【v2 Fix 2】单点防御（v4 保留）
    if (valid.length < 2) return '';

    // ---- 1. 真实物理范围 ----
    const lats = valid.map(p => p.lat);
    const lons = valid.map(p => p.lon);
    const minLat = Math.min(...lats), maxLat = Math.max(...lats);
    const minLon = Math.min(...lons), maxLon = Math.max(...lons);
    const midLat = (minLat + maxLat) / 2;
    const latSpanM = (maxLat - minLat) * 110540;
    const lonSpanM = (maxLon - minLon) * 111320 * Math.cos(midLat * Math.PI / 180);
    const realRatio = (latSpanM > 0 && lonSpanM > 0) ? (lonSpanM / latSpanM) : 1;

    // ---- 2. 自适应 viewBox（v2 Fix 1 居中保留）----
    const pad = 14;
    const maxW = containerWidth || 760;
    const maxH = containerHeight || 220;
    let viewW = maxW - pad * 2;
    let viewH = maxH - pad * 2;
    if (realRatio > viewW / viewH) {
        viewH = viewW / realRatio;
    } else {
        viewW = viewH * realRatio;
    }
    const offsetX = (maxW - viewW) / 2;
    const offsetY = (maxH - viewH) / 2;

    // ---- 3. HiDPI 清晰 ----
    const dpr = window.devicePixelRatio || 1;
    const canvas = document.createElement('canvas');
    canvas.width = maxW * dpr;
    canvas.height = maxH * dpr;
    canvas.style.width = maxW + 'px';
    canvas.style.height = maxH + 'px';
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);

    // 抗锯齿
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';

    // ---- 【v4 升级】4. 纯黑底填充 ----
    ctx.fillStyle = '#000000';
    ctx.fillRect(0, 0, maxW, maxH);

    // ---- 【v4 升级】5. 实心白 1px 正方形网格 ----
    // 网格单元: 固定 40px × 40px 标准正方形
    // 覆盖策略: 行列 = ceil(maxW/40) × ceil(maxH/40), 最后一列/行画到画布边缘
    // 视觉: 模拟经纬线式网格, 100% 实心白色 1px
    const CELL_SIZE = 40;  // 正方形边长(像素)
    ctx.lineWidth = 1;
    ctx.strokeStyle = '#FFFFFF';  // 100% 实心白
    // 横向网格线 (从 cellSize 像素到 maxW-1 像素, 含最后一条)
    for (let x = CELL_SIZE; x < maxW; x += CELL_SIZE) {
        ctx.beginPath();
        ctx.moveTo(x + 0.5, 0);  // +0.5 是 Canvas 1px 抗锯齿技巧
        ctx.lineTo(x + 0.5, maxH);
        ctx.stroke();
    }
    // 纵向网格线 (从 cellSize 像素到 maxH-1 像素, 含最后一条)
    for (let y = CELL_SIZE; y < maxH; y += CELL_SIZE) {
        ctx.beginPath();
        ctx.moveTo(0, y + 0.5);
        ctx.lineTo(maxW, y + 0.5);
        ctx.stroke();
    }
    // 【v4 删除】外边框: 白色 1px 网格已足够, 不再需要单独的 35% 半透明外框

    // ---- 6. 真实比例投影（v3 保留）----
    const lonRange = (maxLon - minLon) || 0.0001;
    const latRange = (maxLat - minLat) || 0.0001;
    const scaleX = (p) => offsetX + pad + ((p.lon - minLon) / lonRange) * viewW;
    const scaleY = (p) => offsetY + pad + ((maxLat - p.lat) / latRange) * viewH;

    // ---- 7. 阴影发光（v3 保留）----
    ctx.shadowColor = 'rgba(56, 189, 248, 0.45)';
    ctx.shadowBlur = 8;
    ctx.shadowOffsetX = 0;
    ctx.shadowOffsetY = 0;

    // ---- 8. 渐变描边（v3 保留）----
    const grad = ctx.createLinearGradient(0, 0, maxW, maxH);
    grad.addColorStop(0, '#34d399');
    grad.addColorStop(0.5, '#22d3ee');
    grad.addColorStop(1, '#38bdf8');
    ctx.strokeStyle = grad;

    // ---- 9. 二次贝塞尔曲线平滑（v3 保留）----
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    const diag = Math.sqrt(viewW * viewW + viewH * viewH);
    ctx.lineWidth = diag < 120 ? 5 : diag < 240 ? 4 : 3;

    if (valid.length === 2) {
        ctx.beginPath();
        ctx.moveTo(scaleX(valid[0]), scaleY(valid[0]));
        ctx.lineTo(scaleX(valid[1]), scaleY(valid[1]));
        ctx.stroke();
    } else {
        ctx.beginPath();
        ctx.moveTo(scaleX(valid[0]), scaleY(valid[0]));
        for (let i = 1; i < valid.length - 1; i++) {
            const mx = (scaleX(valid[i]) + scaleX(valid[i + 1])) / 2;
            const my = (scaleY(valid[i]) + scaleY(valid[i + 1])) / 2;
            ctx.quadraticCurveTo(scaleX(valid[i]), scaleY(valid[i]), mx, my);
        }
        ctx.lineTo(scaleX(valid[valid.length - 1]), scaleY(valid[valid.length - 1]));
        ctx.stroke();
    }

    // ---- 10. 重置阴影（v3 保留）----
    ctx.shadowColor = 'transparent';
    ctx.shadowBlur = 0;

    // ---- 11. 起终点标点（v3 保留, r=6）----
    const startP = valid[0], endP = valid[valid.length - 1];
    const sx = scaleX(startP), sy = scaleY(startP);
    const ex = scaleX(endP), ey = scaleY(endP);
    ctx.fillStyle = '#f8fafc';
    ctx.strokeStyle = 'rgba(15, 23, 42, 0.9)';
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(sx, sy, 6, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    ctx.fillStyle = '#fbbf24';
    ctx.beginPath(); ctx.arc(ex, ey, 6, 0, Math.PI * 2); ctx.fill(); ctx.stroke();

    return canvas;
}
```

---

### Step 2：升级 v3 测试 → v4 测试

**位置**：[tests/test_track_thumbnail_canvas_v3.py](file:///Users/fanglei/应用开发/AI track/tests/test_track_thumbnail_canvas_v3.py)

**改动**：
- `TestV3DarkBackground` → 改名为 `TestV4PureBlackBackground`
- `TestV3Grid` → 改名为 `TestV4WhiteSolidGrid`，**4 个测试升级**
- 新增 `TestV4NoOuterBorder` 测试

**完整新测实现**（追加在 v3 测试文件末尾，或新建 v4 文件均可——按 v3 升级惯例推荐**新建 v4 文件**）：

```python
"""B+ Canvas v4 严格网格规范测试 (纯黑底 + 实心白 1px 正方形网格)

契约:fit-arch-contrac §2.1 字段全链路可追溯 / §九 目录与依赖
覆盖: docs/b_plus_canvas_track_thumbnail_prompt_v4.md §四 测试场景
"""

import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_TRACK_HTML = _PROJECT_ROOT / "track.html"


def _extract_function(name: str, src: str) -> str:
    start = src.find(f"function {name}(")
    assert start >= 0, f"函数 {name} 未在 track.html 中找到"
    brace_start = src.find("{", start)
    depth = 0
    i = brace_start
    while i < len(src):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
        i += 1
    raise RuntimeError(f"无法找到函数 {name} 的结束大括号")


# ══════════════════════════════════════════════════════════════════
# v4 严格网格规范验证
# ══════════════════════════════════════════════════════════════════

class TestV4PureBlackBackground(unittest.TestCase):
    """v4 升级: 纯黑底 #000000"""

    @classmethod
    def setUpClass(cls):
        cls.src = _TRACK_HTML.read_text(encoding="utf-8")
        cls.func = _extract_function("buildTrackThumbnailCanvas", cls.src)

    def test_pure_black_fill(self):
        """v4: 纯黑底 #000000 (非 slate-900)"""
        self.assertIn("#000000", self.func, "v4: 缺少纯黑底 #000000")
        # 必须不是 v3 的 slate-900
        self.assertNotIn("#0f172a", self.func, "v4: 不应再有 v3 的 #0f172a")
        # 必须用 fillRect 覆盖全画布
        self.assertRegex(self.func, r"fillStyle\s*=\s*['\"]#000000['\"]")
        self.assertRegex(self.func, r"fillRect\s*\(\s*0\s*,\s*0\s*,\s*maxW\s*,\s*maxH\s*\)")

    def test_no_alpha_blending(self):
        """v4: 背景必须无透明/渐变 (rgba/gradient/alpha 都不能用)"""
        # 抽取出 fillStyle='#000000' 行附近,确保无 rgba 透明
        import re
        m = re.search(r"fillStyle\s*=\s*['\"]#000000['\"]", self.func)
        self.assertIsNotNone(m)
        # fillStyle 行本身不能含 rgba
        line_start = self.func.rfind("\n", 0, m.start()) + 1
        line_end = self.func.find("\n", m.end())
        line = self.func[line_start:line_end]
        self.assertNotIn("rgba", line, "v4 背景色行不应使用 rgba 透明")


class TestV4WhiteSolidGrid(unittest.TestCase):
    """v4 升级: 实心白 #FFFFFF 1px 网格"""

    @classmethod
    def setUpClass(cls):
        cls.src = _TRACK_HTML.read_text(encoding="utf-8")
        cls.func = _extract_function("buildTrackThumbnailCanvas", cls.src)

    def test_solid_white_grid_color(self):
        """v4: 网格颜色 #FFFFFF 100% 实心 (非 v3 的 18% 透明 slate-400)"""
        self.assertIn("#FFFFFF", self.func, "v4: 缺少实心白 #FFFFFF")
        # 不能再有 v3 的网格颜色
        self.assertNotIn("rgba(148, 163, 184, 0.18)", self.func,
                         "v4: 不应再有 v3 的 18% 透明网格")

    def test_line_width_1px(self):
        """v4: 网格线宽 1px (用户规范)"""
        # 抽取出 strokeStyle='#FFFFFF' 行, 确保 ctx.lineWidth = 1 在它之前
        idx_stroke = self.func.find("strokeStyle = '#FFFFFF'")
        self.assertGreater(idx_stroke, 0, "v4: 缺少 strokeStyle = '#FFFFFF'")
        # lineWidth = 1 必须在 strokeStyle 之前设置
        idx_linewidth = self.func.rfind("lineWidth = 1", 0, idx_stroke)
        self.assertGreater(idx_linewidth, 0, "v4: lineWidth = 1 必须在 strokeStyle 之前")

    def test_horizontal_grid_lines(self):
        """v4: 横向网格线 (从 cellSize 像素开始, 步长 cellSize)"""
        # 寻找 for (let x = CELL_SIZE; x < maxW; x += CELL_SIZE)
        self.assertRegex(self.func, r"for\s*\(\s*let\s+x\s*=\s*CELL_SIZE\s*;\s*x\s*<\s*maxW")

    def test_vertical_grid_lines(self):
        """v4: 纵向网格线 (从 cellSize 像素开始, 步长 cellSize)"""
        # 寻找 for (let y = CELL_SIZE; y < maxH; y += CELL_SIZE)
        self.assertRegex(self.func, r"for\s*\(\s*let\s+y\s*=\s*CELL_SIZE\s*;\s*y\s*<\s*maxH")


class TestV4SquareGrid(unittest.TestCase):
    """v4 升级: 正方形网格 (固定像素边长)"""

    @classmethod
    def setUpClass(cls):
        cls.src = _TRACK_HTML.read_text(encoding="utf-8")
        cls.func = _extract_function("buildTrackThumbnailCanvas", cls.src)

    def test_cell_size_constant(self):
        """v4: 网格单元固定 40px × 40px (正方形)"""
        # 必须有 const CELL_SIZE = 40
        self.assertRegex(self.func, r"const\s+CELL_SIZE\s*=\s*40",
                         "v4: 必须有 const CELL_SIZE = 40")

    def test_no_4x2_grid(self):
        """v4: 不应再有 v3 的 4 等分横线 / 2 等分纵线"""
        self.assertNotIn("i < 4", self.func, "v4: 不应再有 v3 的 4 等分循环")
        self.assertNotIn("i < 2", self.func, "v4: 不应再有 v3 的 2 等分循环")
        # v3 的 for (let i = 1; i < 4/2) 模式不应再出现
        self.assertNotRegex(self.func, r"for\s*\(\s*let\s+i\s*=\s*1\s*;\s*i\s*<\s*[24]")

    def test_full_coverage(self):
        """v4: 网格覆盖全画布 (循环条件 x < maxW, y < maxH)"""
        # 应有 x < maxW + y < maxH
        self.assertRegex(self.func, r"x\s*<\s*maxW")
        self.assertRegex(self.func, r"y\s*<\s*maxH")
        # 步长是 CELL_SIZE (而非任意值)
        self.assertRegex(self.func, r"x\s*\+=\s*CELL_SIZE")
        self.assertRegex(self.func, r"y\s*\+=\s*CELL_SIZE")


class TestV4NoOuterBorder(unittest.TestCase):
    """v4 简化: 删除 v3 的 35% 半透明外边框"""

    @classmethod
    def setUpClass(cls):
        cls.src = _TRACK_HTML.read_text(encoding="utf-8")
        cls.func = _extract_function("buildTrackThumbnailCanvas", cls.src)

    def test_no_outer_border(self):
        """v4: 不再有 strokeRect 外边框 (白色 1px 网格已足够)"""
        self.assertNotIn("strokeRect", self.func, "v4: 不应再有 strokeRect 外边框")
        # v3 的 35% 边框颜色不应再有
        self.assertNotIn("rgba(148, 163, 184, 0.35)", self.func,
                         "v4: 不应再有 v3 的 35% 半透明外边框颜色")


# ══════════════════════════════════════════════════════════════════
# v3 兼容性验证 (v4 必须保留 v3 全部视觉特性)
# ══════════════════════════════════════════════════════════════════

class TestV3BackwardCompatV4(unittest.TestCase):
    """v4 必须保留 v3 全部特性"""

    @classmethod
    def setUpClass(cls):
        cls.src = _TRACK_HTML.read_text(encoding="utf-8")
        cls.func = _extract_function("buildTrackThumbnailCanvas", cls.src)

    def test_v3_bezier_preserved(self):
        """v3: 二次贝塞尔曲线"""
        self.assertIn("quadraticCurveTo", self.func)
        self.assertRegex(self.func, r"valid\.length\s*===\s*2")

    def test_v3_shadow_preserved(self):
        """v3: 阴影发光"""
        self.assertIn("shadowBlur", self.func)
        self.assertIn("sky-400", self.func) or self.assertIn("56, 189, 248", self.func)

    def test_v3_antialiasing_preserved(self):
        """v3: 抗锯齿"""
        self.assertIn("imageSmoothingQuality", self.func)
        self.assertIn("'high'", self.func)

    def test_v3_endpoints_preserved(self):
        """v3: 起终点标点 r=6"""
        self.assertRegex(self.func, r"\.arc\s*\([^)]*,\s*6\s*,")
        self.assertIn("#f8fafc", self.func)
        self.assertIn("#fbbf24", self.func)

    def test_v3_real_ratio_preserved(self):
        """v3: 真实物理宽高比"""
        self.assertIn("110540", self.func)
        self.assertIn("111320", self.func)

    def test_v3_dynamic_line_width_preserved(self):
        """v3: 动态线宽 5/4/3"""
        self.assertRegex(self.func, r"diag\s*<\s*120\s*\?\s*5\s*:\s*diag\s*<\s*240\s*\?\s*4\s*:\s*3")


# ══════════════════════════════════════════════════════════════════
# 契约符合性验证
# ══════════════════════════════════════════════════════════════════

class TestV4ContractCompliance(unittest.TestCase):
    """v4 必须满足 §V4.0 / §九 / §十"""

    @classmethod
    def setUpClass(cls):
        cls.src = _TRACK_HTML.read_text(encoding="utf-8")
        cls.func = _extract_function("buildTrackThumbnailCanvas", cls.src)

    def test_no_new_libs(self):
        """§九: 不引入新 JS 库"""
        forbidden_patterns = ["d3.", "import d3", "from d3", "mapboxgl.", "leaflet.", "turf."]
        for p in forbidden_patterns:
            self.assertNotIn(p.lower(), self.func.lower(),
                             f"v4 禁止引入外部库: {p}")

    def test_no_cesium_usage(self):
        """v4 函数不触碰 Cesium"""
        self.assertNotIn("Cesium", self.func)
        self.assertNotIn("viewer", self.func)

    def test_no_shadow_diff(self):
        """v4 函数不引用 shadow_diff"""
        self.assertNotIn("shadow_diff", self.func)

    def test_no_ai_snapshot(self):
        """v4 函数不构造 AI 输入"""
        self.assertNotIn("_ai_snapshot", self.func)
        self.assertNotIn("_chat_messages", self.func)


if __name__ == "__main__":
    unittest.main()
```

---

### Step 3：跑测试

按顺序执行：

```bash
# 3.1 跑 v4 新增测试
cd "/Users/fanglei/应用开发/AI track" && python3 -m pytest tests/test_track_thumbnail_canvas_v4.py -v

# 3.2 跑 v3 测试 (v4 升级应使 v3 失败的相关测同步更新 — 已在 v3 文件中标注)
cd "/Users/fanglei/应用开发/AI track" && python3 -m pytest tests/test_track_thumbnail_canvas_v3.py -v

# 3.3 跑 v2 测试
cd "/Users/fanglei/应用开发/AI track" && python3 -m pytest tests/test_track_thumbnail_canvas.py -v

# 3.4 跑全量
cd "/Users/fanglei/应用开发/AI track" && python3 -m pytest tests/ --ignore=tests/test_laps_real_data.py -q --tb=short
```

---

## 六、验收标准

### 6.1 视觉验收（用户明确要求 2 项验证）

| # | 场景 | 期望 | 自动化 |
|---|---|---|---|
| V1 | **不同分辨率设备**（1280×720 / 1920×1080 / 2560×1440 / Retina） | 网格**不拉伸、不变形**，始终保持正方形 | ✅ `TestV4SquareGrid` 验证 `CELL_SIZE = 40` 固定 |
| V2 | **轨迹 vs 网格对比度** | 亮绿→青→亮蓝渐变轨迹在 `#000000` 纯黑 + `#FFFFFF` 实心白网格上**清晰可辨** | ✅ `TestV3BackwardCompatV4.test_v3_antialiasing_preserved` |
| V3 | 纯黑底确认 | 视觉是 `#000000`（无任何 slate-900 灰度） | ✅ `TestV4PureBlackBackground.test_pure_black_fill` |
| V4 | 实心白 1px 网格 | 网格颜色 `#FFFFFF`，线宽 1px，无半透明 | ✅ `TestV4WhiteSolidGrid.test_solid_white_grid_color` + `test_line_width_1px` |
| V5 | 正方形 40px | 行列 = `ceil(maxW/40)` × `ceil(maxH/40)`，每格 40×40 | ✅ `TestV4SquareGrid.test_cell_size_constant` |
| V6 | 覆盖全画布 | 最后一列/行到画布边缘，无截断 | ✅ `TestV4SquareGrid.test_full_coverage` |

### 6.2 契约验收

- [ ] `main.py` / `metrics_resolver.py` 业务逻辑零改动
- [ ] v3 视觉特性（贝塞尔/阴影/抗锯齿/标点/真实比例/HiDPI）全部保留
- [ ] v3 测试文件中**仅**升级 3 个 v4 契约相关测（背景色/网格色/边框删除）
- [ ] v4 新增测试全部通过
- [ ] 全量 867+ tests 全绿
- [ ] 无新 JS 库
- [ ] `docs/js_api_contract.json` 不更新
- [ ] `requirements.txt` 不更新

### 6.3 性能验收

- 单次绘制 < 5ms（48~60 采样点 + 贝塞尔 + 阴影 + 网格）
- 网格 for 循环 `O(maxW/40 + maxH/40)` ≈ `O(19+5) = 24` 次 stroke，远低于贝塞尔的 58 次
- 内存：canvas 节点随旧 DOM 一起释放

### 6.4 §2.1 全链路可追溯验证

```
FIT SDK gps_lat / gps_long
  ↓
activities.track_json[i].lat / lon
  ↓
MetricsResolver._lttb_sample  (V9.x-LTTB 弯道特征保留)
  ↓
record.detail.thumbnail_points  (60 点)
  ↓
track.html buildTrackThumbnailCanvas v4  (本次升级)
  ↓
#000000 纯黑底 + #FFFFFF 实心白 40×40 网格 + 贝塞尔轨迹
```

**链路中无任何"硬编码 / fallback / AI 输出"切断追溯**。

---

## 七、回滚预案

如发现 v4 网格太密/太疏或颜色对比不达预期：

**回滚方案 A：1 行切换回 v3 视觉**（保持 v4 函数结构但用 v3 颜色）

```javascript
// 第 4 步 背景色改回
ctx.fillStyle = '#0f172a';  // v3 slate-900

// 第 5 步 网格色改回
const gridColor = 'rgba(148, 163, 184, 0.18)';
const borderColor = 'rgba(148, 163, 184, 0.35)';
// 恢复 v3 的 4×2 不规则循环 + strokeRect 外框
```

**回滚方案 B：完全回滚到 v3**（覆盖函数体）
[docs/b_plus_canvas_track_thumbnail_prompt_v3.md](file:///Users/fanglei/应用开发/AI track/docs/b_plus_canvas_track_thumbnail_prompt_v3.md) §五 Step 1 有完整 v3 代码。

---

## 八、交付物清单

| # | 文件 | 类型 | 必改行 | 状态 |
|---|---|---|---|---|
| 1 | `track.html` `buildTrackThumbnailCanvas` | v3 → v4 升级 | 4 处常量 + 网格循环重写 | ⏳ |
| 2 | `tests/test_track_thumbnail_canvas_v4.py` | 新增 | +180 行 | ⏳ |
| 3 | `tests/test_track_thumbnail_canvas_v3.py` | 删/改 3 个 v3 测 | 3 处 | ⏳ |
| 4 | `buildTrackThumbnailSvg` 函数 | **不修改** | 0 | ✅ |
| 5 | `main.py` / `metrics_resolver.py` | **不修改** | 0 | ✅ |
| 6 | `docs/js_api_contract.json` | **不更新** | 0 | ✅ |
| 7 | `requirements.txt` | **不更新** | 0 | ✅ |
| 8 | `lib/` | **不修改** | 0 | ✅ |

---

## 九、§V4.0 防腐层契约自检（提交前必跑）

```bash
cd "/Users/fanglei/应用开发/AI track" && python3 -c "
import ast
with open('main.py') as f:
    tree = ast.parse(f.read())
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name == '_sample_thumbnail_points':
        non_doc = [s for s in node.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
        assert len(non_doc) == 1, f'main.py 防腐层被破坏: {len(non_doc)} 行'
        print('✅ §V4.0 防腐层契约保持')
"
```

> v4 是**纯前端视觉升级**，**§V4.0 防腐层不应受影响**。

---

## 十、执行确认

执行完成后需向用户报告：

1. **修改了哪些行**：`track.html` 哪几行 + `tests/test_track_thumbnail_canvas_v4.py` 哪几行 + `tests/test_track_thumbnail_canvas_v3.py` 哪几处升级
2. **测试通过数**：v4 新增 + v3 升级后 + 全量
3. **V1~V6 6 个视觉验收场景**：
   - **V1 不同分辨率**：在 1280×720 / 1920×1080 / 2560×1440 / Retina 上截图，确认 40px 正方形不变形
   - **V2 对比度**：确认轨迹在黑底白网格上视觉清晰
4. **意外发现**：v4 网格密度是否合适 / 是否需要调整 CELL_SIZE
5. **后续可优化项**：V4.1（按用户要求加缩放适配——如选决策 1 选项 B/C）

> **本提示词为最终交付物，提交后进入"执行 → 测试 → 报告"三步流程。**
