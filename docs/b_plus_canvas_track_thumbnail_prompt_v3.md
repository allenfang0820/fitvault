# 任务：活动详情页轨迹缩略图 v3 升级 — 黑底白网格 + 视觉平滑（V9.x-LTTB 配套）

> 立项依据：用户反馈"轨迹背景太单一，轨迹仍不够平滑"
> 配合：V9.x-LTTB（已上线，弯道顶点保留）+ B+ Canvas v2（已上线，真实比例）
> 本次新增：v3 视觉升级（黑底 + 白网格）+ 轨迹平滑（贝塞尔曲线 + 反走样）
> 契约参考：fit-arch-contrac §2.1 字段全链路可追溯 / §V4.0 防腐层 / §九 目录 / §十 Non-Goals
> 工作量：≤ 0.5 个工作日 | 修改文件：1 个 (track.html `buildTrackThumbnailCanvas` v2 → v3)

---

## 一、用户反馈 + 根因

| # | 反馈 | 根因 | 修复方向 |
|---|---|---|---|
| 1 | **背景太单一** | v2 是无背景的纯色画布，视觉单调 | v3: **黑底 + 白色网格**（等比分布，模拟 Cesium 风格） |
| 2 | **轨迹仍不够平滑** | 48 个采样点 + 直线段连接 → 仍有"折角"感 | v3: **二次贝塞尔曲线平滑** + HiDPI 抗锯齿 + 加粗线宽 + 阴影发光 |

### 行业对照

| 产品 | 背景 | 平滑方式 |
|---|---|---|
| Garmin Connect 缩略图 | 浅灰底 + 浅色道路瓦片 | 服务端预渲染 + Mapbox 矢量瓦片抗锯齿 |
| Strava 缩略图 | 浅色 + 速度颜色梯度 | 客户端 Canvas + Catmull-Rom 样条 |
| COROS 缩略图 | 浅色 + 等高线 | 服务端预渲染 |
| ECharts 默认 line.smooth | 无背景 | 二次贝塞尔 |
| **脉图 v3 (本任务)** | **黑底 + 白网格** | **二次贝塞尔 + 抗锯齿** |

> **设计意图**：黑底白网格是数据可视化专业风格（如 Grafana / Datadog / GitHub Insights 暗色模式），脉图 v3 选择此风格契合"专业运动数据工具"定位。

---

## 二、目标

让 `buildTrackThumbnailCanvas` v3 在保留 v2 真实比例 + v9.x-LTTB 弯道特征基础上，**视觉升级为黑底白网格 + 平滑曲线**：

```
v2 现状:   白底 + 渐变细线 + 折角
     ↓ v3
v3 目标:   黑底 + 白色网格 + 渐变粗线 + 阴影发光 + 贝塞尔平滑
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
✅ **不修改 `requirements.txt`**（无 Python 依赖变化）
✅ 贝塞尔平滑用原生 Canvas 2D API `quadraticCurveTo`（零依赖）

### 3.5 §十 Non-Goals

✅ 纯本地、零网络、零 SaaS
✅ 不向第三方发送任何数据

### 3.6 兼容性

✅ **保留 v2 测试用例**（34 测全部继续通过）
✅ 旧 SVG 函数 `buildTrackThumbnailSvg` 继续保留（不删除，作为对比/回滚备选）
✅ 容器尺寸契约不变（760×220 仍为默认）
✅ v9.x-LTTB 采样契约不变（60 点）

---

## 四、范围与边界

### 4.1 必须做

1. **改 `track.html` 中 `buildTrackThumbnailCanvas`**：
   - v2 → v3 视觉升级（黑底、白网格、贝塞尔平滑、抗锯齿、阴影发光、加粗线宽）
   - 保留所有 v2 Fix（Fix 1 居中、Fix 2 单点防御、Fix 3 动态线宽）
2. **追加测试** `tests/test_track_thumbnail_canvas_v3.py`：
   - 验证 v3 4 个新视觉特性（黑底、白网格、贝塞尔、抗锯齿）
3. **跑全量测试 + 视觉验证**

### 4.2 不许做

- ❌ 不改 `buildTrackThumbnailSvg`（SVG 备选保留）
- ❌ 不改 v2 既有 34 个测试用例（仅追加新测，不修改）
- ❌ 不改 `main.py` / `metrics_resolver.py` / 后端任何文件
- ❌ 不引入 JS 库（无 D3 / 无 ECharts / 无贝塞尔库）
- ❌ 不改 `docs/js_api_contract.json`（无新 API）
- ❌ 不加 hover / 旋转 / 动画等 V3.1+ 功能（保持职责单一）
- ❌ 不在 `track.html` 加外部 CSS / 字体 / 资源

### 4.3 边界与降级

| 情况 | 行为 |
|---|---|
| 点数 < 2 | 仍返回 `''`（v2 Fix 2 保留） |
| 高 DPI 屏 | 仍 `dpr` 缩放（v2 保留） |
| 极短轨迹 | 渐变 + 贝塞尔仍可工作 |
| 老浏览器（无 Canvas 2D） | 应 fallback，但本应用已是 Chromium 桌面端，无需考虑 |
| 用户系统暗色模式 | 黑底 v3 与暗色模式天然兼容（无需 media query） |

---

## 五、实施步骤

### Step 1：改 `buildTrackThumbnailCanvas` v2 → v3

**位置**：[track.html:6036-6136](file:///Users/fanglei/应用开发/AI track/track.html#L6036-L6136) 之间的 `buildTrackThumbnailCanvas` 函数

**改动原则**：
- **保留** v2 全部结构（Fix 1 居中 / Fix 2 单点防御 / Fix 3 动态线宽 / HiDPI / 真实比例 / 渐变 / 起终点）
- **新增** 4 个视觉层：
  1. **黑底填充**（v3 新增）
  2. **白色等比网格**（v3 新增，4×2 网格 + 边框）
  3. **贝塞尔平滑曲线**（v3 新增，`quadraticCurveTo`）
  4. **抗锯齿 + 阴影发光**（v3 新增，`ctx.imageSmoothingEnabled` + `shadowBlur`）

**完整 v3 实现**（**严格按此实现，不要自行"优化"**）：

```javascript
/**
 * 活动详情页轨迹缩略图（Canvas 2D 真实比例版 v3）
 * 产品定义：Geometric Activity Snapshot — Dark Mode Edition
 *
 * v3 升级（在 v2 基础上）:
 *   1. 黑底 (#0f172a slate-900) — 暗色模式专业风格
 *   2. 白色等比网格 4×2 — 模拟 Cesium / Grafana 暗色主题
 *   3. 二次贝塞尔曲线 (quadraticCurveTo) — 弯道视觉平滑
 *   4. 阴影发光 (shadowBlur) + 加粗线宽 — 视觉冲击力
 *   5. 抗锯齿 (imageSmoothingEnabled) — Retina 屏清晰
 *
 * 保留 v2 不变:
 *   - 真实物理宽高比自适应 (Fix 1 居中)
 *   - 单点防御 (Fix 2)
 *   - 动态线宽 (Fix 3)
 *   - HiDPI (devicePixelRatio)
 *   - 起终点标点
 *
 * 契约:
 *   - 入参 points: Array<{lat, lon}> 来自 record.thumbnail_points (V9.x-LTTB 采样后)
 *   - 返回: HTMLCanvasElement (HiDPI 感知) 或 ''
 *   - 投影: 等距矩形 + 真实物理宽高比自适应
 *   - 性能: 60 采样点, < 5ms 单次绘制
 *   - 零依赖, 零网络
 */
function buildTrackThumbnailCanvas(points, containerWidth, containerHeight) {
    const valid = (points || []).filter(p =>
        typeof p.lat === 'number' && typeof p.lon === 'number'
    );
    // 【v2 Fix 2】单点防御（v3 保留）
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

    // 【v3 新增】抗锯齿
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';

    // ---- 【v3 新增】4. 黑底填充 ----
    ctx.fillStyle = '#0f172a';  // slate-900
    ctx.fillRect(0, 0, maxW, maxH);

    // ---- 【v3 新增】5. 白色等比网格 4×2 + 边框 ----
    const gridColor = 'rgba(148, 163, 184, 0.18)';  // slate-400 半透明
    const borderColor = 'rgba(148, 163, 184, 0.35)';
    ctx.lineWidth = 1;
    ctx.strokeStyle = gridColor;
    // 横向 4 等分线 (5 条, 含上下边)
    for (let i = 1; i < 4; i++) {
        const y = (i / 4) * maxH;
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(maxW, y);
        ctx.stroke();
    }
    // 纵向 2 等分线 (3 条, 含左右边)
    for (let i = 1; i < 2; i++) {
        const x = (i / 2) * maxW;
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, maxH);
        ctx.stroke();
    }
    // 外边框
    ctx.strokeStyle = borderColor;
    ctx.strokeRect(0.5, 0.5, maxW - 1, maxH - 1);

    // ---- 6. 真实比例投影（v2 保留）----
    const lonRange = (maxLon - minLon) || 0.0001;
    const latRange = (maxLat - minLat) || 0.0001;
    const scaleX = (p) => offsetX + pad + ((p.lon - minLon) / lonRange) * viewW;
    const scaleY = (p) => offsetY + pad + ((maxLat - p.lat) / latRange) * viewH;

    // ---- 【v3 新增】7. 阴影发光（必须在 stroke 之前设置）----
    ctx.shadowColor = 'rgba(56, 189, 248, 0.45)';  // sky-400 半透明
    ctx.shadowBlur = 8;
    ctx.shadowOffsetX = 0;
    ctx.shadowOffsetY = 0;

    // ---- 【v3 新增】8. 渐变描边 ----
    const grad = ctx.createLinearGradient(0, 0, maxW, maxH);
    grad.addColorStop(0, '#34d399');  // emerald-400 (亮绿)
    grad.addColorStop(0.5, '#22d3ee'); // cyan-400 (中段青)
    grad.addColorStop(1, '#38bdf8');  // sky-400 (亮蓝)
    ctx.strokeStyle = grad;

    // ---- 【v3 新增】9. 二次贝塞尔曲线平滑 ----
    // 算法: 对每对相邻点 P[i], P[i+1] 计算中点 M,
    //       将 P[i+1] 作为控制点, M 作为终点, 形成贝塞尔段
    // 视觉: 相邻两段共享控制点 P[i+1], 整体 C¹ 连续
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    // 【v2 Fix 3 升级】动态线宽 + v3 加粗
    const diag = Math.sqrt(viewW * viewW + viewH * viewH);
    ctx.lineWidth = diag < 120 ? 5 : diag < 240 ? 4 : 3;

    if (valid.length === 2) {
        // 2 点: 退化为直线
        ctx.beginPath();
        ctx.moveTo(scaleX(valid[0]), scaleY(valid[0]));
        ctx.lineTo(scaleX(valid[1]), scaleY(valid[1]));
        ctx.stroke();
    } else {
        // ≥3 点: 贝塞尔平滑
        ctx.beginPath();
        ctx.moveTo(scaleX(valid[0]), scaleY(valid[0]));
        for (let i = 1; i < valid.length - 1; i++) {
            const mx = (scaleX(valid[i]) + scaleX(valid[i + 1])) / 2;
            const my = (scaleY(valid[i]) + scaleY(valid[i + 1])) / 2;
            // 二次贝塞尔: 当前点为控制点, 中点为终点
            ctx.quadraticCurveTo(scaleX(valid[i]), scaleY(valid[i]), mx, my);
        }
        // 最后一段: 终点直接连接到末点
        ctx.lineTo(scaleX(valid[valid.length - 1]), scaleY(valid[valid.length - 1]));
        ctx.stroke();
    }

    // ---- 【v3 新增】10. 重置阴影 (避免影响标点) ----
    ctx.shadowColor = 'transparent';
    ctx.shadowBlur = 0;

    // ---- 11. 起终点标点（v2 保留, v3 增强）----
    const startP = valid[0], endP = valid[valid.length - 1];
    const sx = scaleX(startP), sy = scaleY(startP);
    const ex = scaleX(endP), ey = scaleY(endP);
    // 起点：白底 + 深色描边
    ctx.fillStyle = '#f8fafc';
    ctx.strokeStyle = 'rgba(15, 23, 42, 0.9)';
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(sx, sy, 6, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    // 终点：黄色 + 深色描边
    ctx.fillStyle = '#fbbf24';
    ctx.beginPath(); ctx.arc(ex, ey, 6, 0, Math.PI * 2); ctx.fill(); ctx.stroke();

    return canvas;
}
```

---

### Step 2：保留 v2 SVG 函数（不修改）

`buildTrackThumbnailSvg` 函数（[track.html:6137+](file:///Users/fanglei/应用开发/AI track/track.html#L6137)）保持不变。SVG 版本作为：
- 调试对比用途
- 紧急回滚备选（1 行调用点切换）

---

### Step 3：调用点不变

[track.html:6225-6240](file:///Users/fanglei/应用开发/AI track/track.html#L6225-L6240) 调用点（v2 B+）保持不变，因为函数名 `buildTrackThumbnailCanvas` 不变，仅内部实现升级为 v3。**v2 测试用例继续通过**。

---

### Step 4：新增测试 `tests/test_track_thumbnail_canvas_v3.py`

**完整实现**（**严格按此实现**）：

```python
"""B+ Canvas v3 视觉升级测试 (黑底 + 白网格 + 贝塞尔平滑)

契约:fit-arch-contrac §2.1 字段全链路可追溯 / §九 目录与依赖
覆盖: docs/b_plus_canvas_track_thumbnail_prompt_v3.md §4.1.2 测试场景
"""

import re
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
# v3 视觉特性验证
# ══════════════════════════════════════════════════════════════════

class TestV3DarkBackground(unittest.TestCase):
    """v3 新增: 黑底填充"""

    @classmethod
    def setUpClass(cls):
        cls.src = _TRACK_HTML.read_text(encoding="utf-8")
        cls.func = _extract_function("buildTrackThumbnailCanvas", cls.src)

    def test_dark_fill_color(self):
        """v3: 暗色背景 #0f172a (slate-900)"""
        self.assertIn("#0f172a", self.func, "v3: 缺少暗色背景 #0f172a")
        self.assertRegex(self.func, r"fillStyle\s*=\s*['\"]#0f172a['\"]")
        self.assertRegex(self.func, r"fillRect\s*\(")


class TestV3Grid(unittest.TestCase):
    """v3 新增: 白色等比网格"""

    @classmethod
    def setUpClass(cls):
        cls.src = _TRACK_HTML.read_text(encoding="utf-8")
        cls.func = _extract_function("buildTrackThumbnailCanvas", cls.src)

    def test_grid_color(self):
        """v3: 网格颜色 rgba(148, 163, 184, ...)"""
        self.assertIn("148, 163, 184", self.func, "v3: 缺少网格颜色 slate-400")

    def test_grid_horizontal_lines(self):
        """v3: 横向 4 等分 (5 条线)"""
        # 循环 1..4, 生成 3 条中间线 + 上下边
        self.assertRegex(self.func, r"for\s*\(\s*let\s+i\s*=\s*1\s*;\s*i\s*<\s*4")

    def test_grid_vertical_lines(self):
        """v3: 纵向 2 等分 (1 条中间线)"""
        self.assertRegex(self.func, r"for\s*\(\s*let\s+i\s*=\s*1\s*;\s*i\s*<\s*2")

    def test_grid_outer_border(self):
        """v3: 外边框 strokeRect"""
        self.assertRegex(self.func, r"strokeRect\s*\(")


class TestV3BezierSmooth(unittest.TestCase):
    """v3 新增: 二次贝塞尔曲线平滑"""

    @classmethod
    def setUpClass(cls):
        cls.src = _TRACK_HTML.read_text(encoding="utf-8")
        cls.func = _extract_function("buildTrackThumbnailCanvas", cls.src)

    def test_uses_quadratic_curve(self):
        """v3: 使用 quadraticCurveTo 二次贝塞尔"""
        self.assertIn("quadraticCurveTo", self.func, "v3: 缺少 quadraticCurveTo")

    def test_two_point_fallback(self):
        """v3: 2 点退化为直线 (贝塞尔无法 1 段)"""
        self.assertRegex(self.func, r"valid\.length\s*===\s*2")
        # 应有 lineTo 直线分支
        self.assertRegex(self.func, r"ctx\.lineTo")

    def test_midpoint_calculation(self):
        """v3: 计算相邻点中点 (贝塞尔终点)"""
        self.assertRegex(self.func, r"\(\s*scaleX\s*\(\s*valid\[i\]\s*\)\s*\+\s*scaleX\s*\(\s*valid\[i\s*\+\s*1\]\s*\)\s*\)\s*/\s*2")


class TestV3Antialiasing(unittest.TestCase):
    """v3 新增: 抗锯齿 + 阴影发光"""

    @classmethod
    def setUpClass(cls):
        cls.src = _TRACK_HTML.read_text(encoding="utf-8")
        cls.func = _extract_function("buildTrackThumbnailCanvas", cls.src)

    def test_image_smoothing_enabled(self):
        """v3: 抗锯齿开启"""
        self.assertIn("imageSmoothingEnabled", self.func)
        self.assertIn("imageSmoothingQuality", self.func)
        self.assertIn("'high'", self.func)

    def test_shadow_blur(self):
        """v3: 阴影发光 shadowBlur"""
        self.assertIn("shadowColor", self.func)
        self.assertIn("shadowBlur", self.func)

    def test_shadow_reset_before_markers(self):
        """v3: 阴影在标点前重置 (避免影响白底/黄底)"""
        # 顺序: shadowColor='transparent' + shadowBlur=0 必须在 ctx.arc 之前
        # 用位置索引验证
        idx_shadow_reset = self.func.find("shadowBlur = 0")
        idx_arc = self.func.find("ctx.arc")
        self.assertGreater(idx_shadow_reset, 0)
        self.assertGreater(idx_arc, 0)
        self.assertLess(idx_shadow_reset, idx_arc, "shadowBlur=0 必须在 ctx.arc 之前")


# ══════════════════════════════════════════════════════════════════
# v2 兼容性验证 (v3 不应破坏 v2 测试契约)
# ══════════════════════════════════════════════════════════════════

class TestV2BackwardCompat(unittest.TestCase):
    """v3 必须保留 v2 全部 Fix"""

    @classmethod
    def setUpClass(cls):
        cls.src = _TRACK_HTML.read_text(encoding="utf-8")
        cls.func = _extract_function("buildTrackThumbnailCanvas", cls.src)

    def test_v2_fix1_centering(self):
        """v2 Fix 1: offsetX/offsetY 居中"""
        self.assertIn("offsetX", self.func)
        self.assertIn("offsetY", self.func)

    def test_v2_fix2_single_point_defense(self):
        """v2 Fix 2: valid.length < 2"""
        self.assertRegex(self.func, r"valid\.length\s*<\s*2")

    def test_v2_fix3_dynamic_line_width(self):
        """v2 Fix 3: 动态线宽 (v3 加粗, 但保留分支)"""
        # v3: 5 / 4 / 3 (v2: 4 / 3 / 2, 加粗 +1)
        self.assertRegex(self.func, r"diag\s*<\s*120\s*\?\s*5\s*:\s*diag\s*<\s*240\s*\?\s*4\s*:\s*3")

    def test_hidpi_preserved(self):
        """v2: HiDPI devicePixelRatio"""
        self.assertIn("devicePixelRatio", self.func)
        self.assertRegex(self.func, r"canvas\.width\s*=\s*maxW\s*\*\s*dpr")

    def test_real_ratio_preserved(self):
        """v2: 真实物理宽高比"""
        self.assertIn("110540", self.func)
        self.assertIn("111320", self.func)
        self.assertRegex(self.func, r"Math\.cos\s*\(\s*midLat")

    def test_endpoints_preserved(self):
        """v2: 起终点标点保留 (v3 半径 6 升级)"""
        self.assertRegex(self.func, r"\.arc\s*\([^)]*,\s*6\s*,")
        # 起点白色 + 终点黄色
        self.assertIn("#f8fafc", self.func)
        self.assertIn("#fbbf24", self.func)


# ══════════════════════════════════════════════════════════════════
# 契约符合性验证
# ══════════════════════════════════════════════════════════════════

class TestV3ContractCompliance(unittest.TestCase):
    """v3 必须满足 §V4.0 / §九 / §十"""

    @classmethod
    def setUpClass(cls):
        cls.src = _TRACK_HTML.read_text(encoding="utf-8")
        cls.func = _extract_function("buildTrackThumbnailCanvas", cls.src)

    def test_no_new_libs(self):
        """§九: 不引入新 JS 库"""
        # 不应新增 <script> 标签
        # 检查函数内不引用外部库
        for lib in ["d3", "echarts", "mapbox", "leaflet", "turf"]:
            self.assertNotIn(lib, self.func.lower(),
                             f"v3 禁止引入外部库: {lib}")

    def test_no_cesium_usage(self):
        """v3 函数不触碰 Cesium"""
        self.assertNotIn("Cesium", self.func)
        self.assertNotIn("viewer", self.func)

    def test_no_shadow_diff(self):
        """v3 函数不引用 shadow_diff"""
        self.assertNotIn("shadow_diff", self.func)

    def test_no_ai_snapshot(self):
        """v3 函数不构造 AI 输入"""
        self.assertNotIn("_ai_snapshot", self.func)
        self.assertNotIn("_chat_messages", self.func)

    def test_pure_function_no_io(self):
        """v3 纯函数,无 fetch / http / DB"""
        for kw in ["fetch(", "XMLHttpRequest", "$.ajax", "pywebview.api"]:
            self.assertNotIn(kw, self.func)


if __name__ == "__main__":
    unittest.main()
```

---

### Step 5：跑测试

按顺序执行：

```bash
# 5.1 跑 v3 新增测试
cd "/Users/fanglei/应用开发/AI track" && python3 -m pytest tests/test_track_thumbnail_canvas_v3.py -v

# 5.2 跑 v2 测试 (确保 v3 不破坏 v2 契约)
cd "/Users/fanglei/应用开发/AI track" && python3 -m pytest tests/test_track_thumbnail_canvas.py -v

# 5.3 跑 V9.x-LTTB 测试
cd "/Users/fanglei/应用开发/AI track" && python3 -m pytest tests/test_lttb_sampling.py -v

# 5.4 跑全量 (必须 845+ tests 全绿)
cd "/Users/fanglei/应用开发/AI track" && python3 -m pytest tests/ --ignore=tests/test_laps_real_data.py -q --tb=short
```

---

## 六、验收标准

### 6.1 视觉验收

| # | 场景 | 期望 |
|---|---|---|
| V1 | 打开活动详情页（任意活动） | 缩略图**黑底 + 白色 4×2 网格 + 外边框**清晰可见 |
| V2 | 短跑/长跑/骑行/徒步 | 轨迹呈现**贝塞尔平滑曲线**，无折角 |
| V3 | 急弯活动 | 弯道视觉平滑（V9.x-LTTB 已保留顶点 + v3 贝塞尔让曲线更顺） |
| V4 | 高 DPI 屏 | 边缘清晰无锯齿（`imageSmoothingQuality='high'`） |
| V5 | 终点标点 | 黄色圆点 + 深色描边，明显区别于起点 |
| V6 | 起点标点 | 白色圆点 + 深色描边，视觉清晰 |
| V7 | 暗色模式 | 黑底 v3 与系统暗色模式天然兼容 |
| V8 | 颜色对比 | 亮绿→青→亮蓝渐变在黑底上对比度高 |

### 6.2 契约验收

- [ ] `main.py` / `metrics_resolver.py` **零业务逻辑改动**（仅 v2 已实现 v9.x-LTTB）
- [ ] `buildTrackThumbnailSvg` 函数保留（不删除）
- [ ] v2 既有 34 个测试**仍通过**
- [ ] v3 新增 16 个测试全绿
- [ ] 全量测试 845+ 全绿
- [ ] 无新 JS 库（无 D3 / ECharts Canvas / 任何 npm 包）
- [ ] `docs/js_api_contract.json` 不更新
- [ ] `requirements.txt` 不更新

### 6.3 性能验收

- 单次绘制 < 5ms（48~60 采样点 + 贝塞尔 + 阴影 + 网格）
- 详情页打开时间无明显变化
- 内存：canvas 节点随旧 DOM 一起释放

### 6.4 §2.1 全链路可追溯验证

```
FIT SDK gps_lat / gps_long
  ↓
activities.track_json[i].lat / lon
  ↓
MetricsResolver._lttb_sample  (V9.x-LTTB 弯道特征保留)
  ↓
record.detail.thumbnail_points  (60 点, 起点/终点强制保留, 弯道顶点保留)
  ↓
track.html buildTrackThumbnailCanvas v3  (本次升级)
  ↓
黑底 + 白网格 + 贝塞尔平滑 + 阴影发光 + 起终点标点
```

链路中**无任何"硬编码 / fallback / AI 输出"切断追溯**。

---

## 七、回滚预案

如发现 v3 视觉/性能问题：

**回滚方案 A：临时回滚到 v2**（1 行调用点切换）

```javascript
// track.html:6225-6240 调用点改为
trackContainer.innerHTML = '<div class="detail-track-thumb" onclick="jumpToTraceFromActivityDetail(' + record.id + ')">' + buildTrackThumbnailSvg(record.thumbnail_points) + '<div class="detail-track-tip">点击进入 3D 沉浸分析(轨迹分析工具)</div></div>';
```

**回滚方案 B：完全回滚到 v2 函数**（覆盖 `buildTrackThumbnailCanvas` 函数体）

[docs/b_plus_canvas_track_thumbnail_prompt_v2.md](file:///Users/fanglei/应用开发/AI track/docs/b_plus_canvas_track_thumbnail_prompt_v2.md) 5.1 节有完整 v2 代码。

---

## 八、交付物清单

| # | 文件 | 类型 | 必改行 | 状态 |
|---|---|---|---|---|
| 1 | `track.html` `buildTrackThumbnailCanvas` | v2 → v3 升级 | ~100 行重写 | ⏳ |
| 2 | `tests/test_track_thumbnail_canvas_v3.py` | 新增 | +180 行 | ⏳ |
| 3 | `buildTrackThumbnailSvg` 函数 | **不修改** | 0 | ✅ |
| 4 | `main.py` / `metrics_resolver.py` | **不修改** | 0 | ✅ |
| 5 | `docs/js_api_contract.json` | **不更新** | 0 | ✅ |
| 6 | `requirements.txt` | **不更新** | 0 | ✅ |
| 7 | `lib/` | **不修改** | 0 | ✅ |

---

## 九、§V4.0 防腐层契约自检（提交前必跑）

```bash
# 确认 main.py._sample_thumbnail_points 仍为 1 行透传
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

> v3 是**纯前端视觉升级**，**§V4.0 防腐层不应受影响**（V9.x-LTTB 已确保 main.py 透传）。

---

## 十、执行确认

执行完成后需向用户报告：

1. **修改了哪些行**：`track.html` `buildTrackThumbnailCanvas` 哪几行 + `tests/test_track_thumbnail_canvas_v3.py` 哪几行
2. **测试通过数**：v3 新增 16 测 + v2 既有 34 测 + 全量 845+ 全绿
3. **V1~V8 8 个视觉验收场景**：截图或文字描述
4. **意外发现**：v3 视觉层叠加是否影响性能 / 暗色模式是否兼容
5. **后续可优化项**：V3.1（hover 高亮采样点）/ V3.2（按 alt 高程着色）等

> **本提示词为最终交付物，提交后进入"执行 → 测试 → 报告"三步流程。**
