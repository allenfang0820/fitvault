"""B+ Canvas 轨迹缩略图 v2 单元测试

契约:fit-arch-contrac §2.1 字段全链路可追溯 / §九 目录与依赖
覆盖: docs/b_plus_canvas_track_thumbnail_prompt_v2.md §4.4 T1~T10

测试策略:由于环境无 Node.js,采用 Python 端:
  1. 静态抽取 track.html 中的 buildTrackThumbnailCanvas 函数
  2. 验证函数结构 (Fix 1/2/3 存在性, API 调用, 返回值类型)
  3. 验证调用点替换 (renderActivityDetail 不再调 buildTrackThumbnailSvg)
  4. 验证 SVG 备选函数保留
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_TRACK_HTML = _PROJECT_ROOT / "track.html"


def _extract_function(name: str, src: str) -> str:
    """从 track.html 提取指定函数的源码"""
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
# 静态结构测试 — 验证 v2 升级 3 个 Fix 的源码存在性
# ══════════════════════════════════════════════════════════════════

class TestCanvasFunctionStructure(unittest.TestCase):
    """buildTrackThumbnailCanvas v2 函数结构验证"""

    @classmethod
    def setUpClass(cls):
        cls.src = _TRACK_HTML.read_text(encoding="utf-8")
        cls.func = _extract_function("buildTrackThumbnailCanvas", cls.src)

    # ---- T9 部分: Fix 1 居中 ----
    def test_fix1_offsetX_exists(self):
        self.assertIn("offsetX", self.func, "Fix 1: 缺少 offsetX 居中变量")

    def test_fix1_offsetY_exists(self):
        self.assertIn("offsetY", self.func, "Fix 1: 缺少 offsetY 居中变量")

    def test_fix1_offsets_applied_to_scale(self):
        """Fix 1: offsetX/Y 必须应用到 scaleX/scaleY"""
        # 应有: scaleX = (p) => offsetX + pad + ...
        self.assertRegex(self.func, r"offsetX\s*\+\s*pad")
        self.assertRegex(self.func, r"offsetY\s*\+\s*pad")

    # ---- T2/T3 部分: Fix 2 单点防御 ----
    def test_fix2_single_point_defense(self):
        """Fix 2: valid.length < 2 防御"""
        self.assertRegex(self.func, r"valid\.length\s*<\s*2",
                         "Fix 2: 缺少单点防御 valid.length < 2")
        # 必须返回空字符串(支持单行 if `if (x<2) return '';` 或块 if)
        self.assertRegex(self.func, r"valid\.length\s*<\s*2[^;{]*return\s+''",
                         "Fix 2: 单点防御未返回空字符串")

    # ---- T10 部分: Fix 3 动态线宽 ----
    def test_fix3_dynamic_line_width_branches(self):
        """Fix 3: 动态线宽 (diag < 120 / diag < 240)"""
        self.assertIn("diag", self.func, "Fix 3: 缺少 diag 变量")
        self.assertRegex(self.func, r"diag\s*<\s*120", "Fix 3: 缺少短距离分支 (4px)")
        self.assertRegex(self.func, r"diag\s*<\s*240", "Fix 3: 缺少中距离分支 (3px)")

    def test_fix3_three_width_values(self):
        """Fix 3: 线宽必须是三档 (v3 升级: 5:4:3, v2 旧: 4:3:2)
        契约:动态线宽, v3 加粗 +1 适配贝塞尔平滑视觉"""
        # v3: 5 / 4 / 3 (v2 旧: 4 / 3 / 2, v3 加粗 +1)
        self.assertRegex(self.func, r"lineWidth\s*=\s*diag\s*<\s*120\s*\?\s*5\s*:\s*diag\s*<\s*240\s*\?\s*4\s*:\s*3",
                         "Fix 3: 线宽表达式不符合 v3 5:4:3 三档契约")

    # ---- T1/T4/T5/T6/T7: 真实比例自适应 ----
    def test_real_ratio_calculation(self):
        """真实物理比:1° lat=110540m, 1° lon=111320m × cos(lat)"""
        self.assertIn("110540", self.func, "缺少 lat 度→米常数")
        self.assertIn("111320", self.func, "缺少 lon 度→米常数")
        self.assertRegex(self.func, r"Math\.cos\s*\(\s*midLat", "缺少 cos(midLat) 修正")

    def test_adaptive_viewbox(self):
        """viewBox 自适应:经度方向长 → 高收缩;反之亦然"""
        # 必须有 if (realRatio > viewW / viewH) { viewH = viewW / realRatio; }
        self.assertRegex(self.func, r"realRatio\s*>\s*viewW\s*/\s*viewH")
        self.assertRegex(self.func, r"viewH\s*=\s*viewW\s*/\s*realRatio")
        self.assertRegex(self.func, r"viewW\s*=\s*viewH\s*\*\s*realRatio")

    # ---- HiDPI ----
    def test_dpr_aware(self):
        """HiDPI:devicePixelRatio 感知"""
        self.assertIn("devicePixelRatio", self.func)
        self.assertIn("dpr", self.func)
        # canvas.width 应乘以 dpr
        self.assertRegex(self.func, r"canvas\.width\s*=\s*maxW\s*\*\s*dpr")
        self.assertRegex(self.func, r"canvas\.height\s*=\s*maxH\s*\*\s*dpr")
        # style.width 不乘 dpr
        self.assertRegex(self.func, r"canvas\.style\.width\s*=\s*maxW\s*\+\s*'px'")

    # ---- 渐变描边 ----
    def test_gradient_stroke(self):
        """绿→蓝渐变描边"""
        self.assertIn("createLinearGradient", self.func)
        self.assertIn("#34d399", self.func, "缺少渐变起点绿色")
        self.assertIn("#38bdf8", self.func, "缺少渐变终点蓝色")

    # ---- 起终点标点 ----
    def test_start_end_markers(self):
        """起终点标点:白底 r=6 (v3 升级),黄底 r=6 (v3 升级)
        契约:v3 标点半径 5→6 加粗,适配阴影发光背景"""
        # arc(x, y, 6, 0, 2π) - v3 升级
        self.assertRegex(self.func, r"\.arc\s*\(\s*\w+\s*,\s*\w+\s*,\s*6\s*,")
        # 起点白色 + 终点黄色
        self.assertIn("#f8fafc", self.func, "缺少起点白色 #f8fafc")
        self.assertIn("#fbbf24", self.func, "缺少终点黄色 #fbbf24")

    # ---- 真实比例投影 (lat/lon → 像素) ----
    def test_projection_formula(self):
        """scaleX/scaleY 真实比例投影公式"""
        # scaleX 应包含: (p.lon - minLon) / lonRange
        self.assertRegex(self.func, r"\(p\.lon\s*-\s*minLon\)\s*/\s*lonRange")
        # scaleY 应包含: (maxLat - p.lat) / latRange (Y 翻转)
        self.assertRegex(self.func, r"\(maxLat\s*-\s*p\.lat\)\s*/\s*latRange")

    # ---- 返回值类型 ----
    def test_returns_canvas_element(self):
        """返回 HTMLCanvasElement,不是 SVG 字符串"""
        self.assertIn("document.createElement('canvas')", self.func)
        self.assertIn("return canvas;", self.func)


# ══════════════════════════════════════════════════════════════════
# 调用点验证 — 验证 renderActivityDetail 改用了 Canvas
# ══════════════════════════════════════════════════════════════════

class TestCallSiteReplacement(unittest.TestCase):
    """验证 v2 替换:renderActivityDetail 调用 buildTrackThumbnailCanvas"""

    @classmethod
    def setUpClass(cls):
        cls.src = _TRACK_HTML.read_text(encoding="utf-8")

    def test_calls_canvas_function(self):
        """renderActivityDetail 必须调 buildTrackThumbnailCanvas"""
        # V6: 调用点直接传 record.thumbnail_points + SIZE 常量
        self.assertIn("buildTrackThumbnailCanvas(record.thumbnail_points, SIZE, SIZE)",
                      self.src, "V6 调用点应传 record.thumbnail_points + SIZE 常量")

    def test_old_svg_call_replaced(self):
        """原 buildTrackThumbnailSvg 调用应被替换"""
        # 找到 renderActivityDetail 中处理 trackContainer 的代码段
        # 不应再有内联 buildTrackThumbnailSvg 调用
        # 但 SVG 函数本身保留,只是不再被此调用点消费
        # 检查条件:renderActivityDetail 内,不在 buildTrackThumbnailSvg 函数定义中
        func_start = self.src.find("function renderActivityDetail")
        func_end = self.src.find("\n    function ", func_start + 1)
        if func_end == -1:
            func_end = len(self.src)
        render_fn = self.src[func_start:func_end]
        # renderActivityDetail 内不再调 SVG
        self.assertNotIn("buildTrackThumbnailSvg(record.thumbnail_points)",
                         render_fn, "renderActivityDetail 仍调旧 SVG 函数,未替换")

    def test_uses_fixed_260_size(self):
        """V6:调用点使用固定 260×260 尺寸(与 CSS .overview-track-area 固定 260 对齐)"""
        # 应包含 buildTrackThumbnailCanvas(record.thumbnail_points, SIZE, SIZE)
        self.assertRegex(self.src,
                         r"buildTrackThumbnailCanvas\(\s*record\.thumbnail_points\s*,\s*SIZE\s*,\s*SIZE\s*\)",
                         "V6 调用点应使用固定 SIZE=260")
        # 验证 SIZE 常量定义
        self.assertIn("var SIZE = 260", self.src, "V6 应定义 SIZE = 260 常量")
        # V6 已移除 ResizeObserver（整个文件层面验证,无残留）
        self.assertNotIn("ResizeObserver", self.src,
                         "V6 已移除 ResizeObserver 动态重绘")
        # V6: track 渲染块内不再有 rAF 动态测量(仅检查局部范围,其他模块可继续用 rAF)
        func_start = self.src.find("function renderActivityDetail")
        func_end = self.src.find("\n    function ", func_start + 1)
        if func_end == -1:
            func_end = len(self.src)
        render_fn = self.src[func_start:func_end]
        # 在 track 渲染块(if caps.has_gps && record.thumbnail_points ...)前后 200 字符内
        track_idx = render_fn.find("if (caps.has_gps && record.thumbnail_points")
        if track_idx > 0:
            track_block = render_fn[track_idx:track_idx + 600]
            self.assertNotIn("requestAnimationFrame", track_block,
                             "V6 轨迹快照渲染块不应再用 rAF 动态测量")
            self.assertNotIn("ResizeObserver", track_block,
                             "V6 轨迹快照渲染块不应再有 ResizeObserver")

    def test_empty_state_preserved(self):
        """空态降级文案保留"""
        self.assertIn("当前活动无可用轨迹文件", self.src)

    def test_keeps_svg_as_reference(self):
        """SVG 函数保留作为参考(不删除)"""
        # 函数定义仍存在
        self.assertRegex(self.src, r"function\s+buildTrackThumbnailSvg\s*\(",
                         "buildTrackThumbnailSvg 应保留(作为参考/对比)")

    def test_jump_to_3d_preserved(self):
        """点击跳转 3D 沉浸分析行为保留"""
        self.assertIn("jumpToTraceFromActivityDetail(record.id)", self.src,
                      "点击跳转 3D 行为应保留")

    def test_tip_text_preserved(self):
        """提示文案保留"""
        self.assertIn("点击进入 3D 沉浸分析", self.src)


# ══════════════════════════════════════════════════════════════════
# 契约符合性验证 — §V4.0 防腐层 / §九 目录
# ══════════════════════════════════════════════════════════════════

class TestContractCompliance(unittest.TestCase):
    """§V4.0 防腐层 / §九 目录契约"""

    @classmethod
    def setUpClass(cls):
        cls.src = _TRACK_HTML.read_text(encoding="utf-8")

    def test_no_new_external_libs(self):
        """不引入新 JS 库(无 D3 / 新 ECharts / Mapbox / Leaflet)"""
        # 检查没有新增 <script src="..."> 引用外部库
        script_tags = re.findall(r'<script\s+[^>]*src\s*=\s*["\']([^"\']+)["\']', self.src)
        # 已知允许的库(ECharts 是既有合法依赖,用于复盘图表)
        allowed = {
            "lib/Cesium/Cesium.js",
            "https://cdn.jsdelivr.net/npm/cesium@1.105.1/Build/Cesium/Cesium.js",
            "https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js",
        }
        for s in script_tags:
            self.assertIn(s, allowed, f"新增外部脚本 {s},违反 §九 目录契约")

    def test_no_cesium_usage_in_canvas_func(self):
        """Canvas 函数不触碰 Cesium"""
        func = _extract_function("buildTrackThumbnailCanvas", self.src)
        self.assertNotIn("Cesium", func)
        self.assertNotIn("viewer", func)

    def test_no_shadow_diff_in_canvas_func(self):
        """Canvas 函数不引用 shadow_diff"""
        func = _extract_function("buildTrackThumbnailCanvas", self.src)
        self.assertNotIn("shadow_diff", func)

    def test_pure_function_no_io(self):
        """Canvas 函数是纯函数,无 fetch / http / DB 调用"""
        func = _extract_function("buildTrackThumbnailCanvas", self.src)
        self.assertNotIn("fetch(", func)
        self.assertNotIn("XMLHttpRequest", func)
        self.assertNotIn("$.ajax", func)
        self.assertNotIn("pywebview.api", func)


# ══════════════════════════════════════════════════════════════════
# T1~T10 行为契约 — 通过静态分析 + 几何参数推导
# ══════════════════════════════════════════════════════════════════

class TestBehaviorContract(unittest.TestCase):
    """T1~T10 行为契约的几何/参数级验证"""

    @classmethod
    def setUpClass(cls):
        cls.src = _TRACK_HTML.read_text(encoding="utf-8")
        cls.func = _extract_function("buildTrackThumbnailCanvas", cls.src)

    # ---- T1: 48 点矩形轨迹 ----
    def test_t1_iterates_all_points(self):
        """T1: ≥3 点应被迭代绘制 (v3 升级 for 循环 + 贝塞尔,v2 旧 forEach + 折线)"""
        # v3: 用 for 循环 + 贝塞尔 (quadraticCurveTo)
        self.assertIn("for (let i = 1; i < valid.length - 1", self.func,
                      "v3: 缺少贝塞尔 for 循环")
        # v3: 必须有 quadraticCurveTo (贝塞尔平滑)
        self.assertIn("quadraticCurveTo", self.func, "v3: 缺少 quadraticCurveTo")
        # 起点 moveTo + 末点 lineTo
        self.assertRegex(self.func, r"ctx\.moveTo\s*\(\s*scaleX\s*\(\s*valid\[0\]\s*\)")
        self.assertRegex(self.func, r"ctx\.lineTo\s*\(\s*scaleX\s*\(\s*valid\[valid\.length\s*-\s*1\]\s*\)")

    # ---- T2: 0 点 / null 返回空 ----
    def test_t2_empty_returns_empty(self):
        """T2: 0 点 / null 防御"""
        # 已有 valid.length < 2 防御
        self.assertRegex(self.func, r"valid\.length\s*<\s*2")

    # ---- T3: 单点防御 (Fix 2) ----
    def test_t3_single_point_defense(self):
        """T3: 单点 → 空字符串"""
        self.assertRegex(self.func, r"valid\.length\s*<\s*2[^;{]*return\s+''")

    # ---- T4: 极扁轨迹 ----
    def test_t4_flat_trajectory_handled(self):
        """T4: lat_span=0 不抛除零(用 || 0.0001 兜底)"""
        self.assertRegex(self.func, r"latRange\s*=\s*\(maxLat\s*-\s*minLat\)\s*\|\|\s*0\.0001")

    # ---- T5: 极高轨迹 ----
    def test_t5_tall_trajectory_handled(self):
        """T5: lon_span=0 不抛除零"""
        self.assertRegex(self.func, r"lonRange\s*=\s*\(maxLon\s*-\s*minLon\)\s*\|\|\s*0\.0001")

    # ---- T6: 南北向跑 ----
    def test_t6_north_south_aspect(self):
        """T6: 南北向 → viewW = viewH * realRatio 收缩"""
        self.assertRegex(self.func, r"viewW\s*=\s*viewH\s*\*\s*realRatio")

    # ---- T7: 东西向骑 ----
    def test_t7_east_west_aspect(self):
        """T7: 东西向 → viewH = viewW / realRatio 收缩"""
        self.assertRegex(self.func, r"viewH\s*=\s*viewW\s*/\s*realRatio")

    # ---- T8: 起终点标点 ----
    def test_t8_markers_use_radius_6(self):
        """T8 (v3 升级): 标点半径 = 6 (v2 旧为 5, v3 加粗适配阴影背景)"""
        # arc(x, y, 6, 0, 2π) - v3 升级
        self.assertRegex(self.func, r"\.arc\s*\([^)]*,\s*6\s*,")
        # 起点白色 + 终点黄色
        self.assertIn("#f8fafc", self.func)
        self.assertIn("#fbbf24", self.func)

    # ---- T9: 等比例居中 (Fix 1) ----
    def test_t9_centering_offset(self):
        """T9: 居中偏移 offsetX/offsetY"""
        self.assertRegex(self.func, r"offsetX\s*=\s*\(maxW\s*-\s*viewW\)\s*/\s*2")
        self.assertRegex(self.func, r"offsetY\s*=\s*\(maxH\s*-\s*viewH\)\s*/\s*2")

    # ---- T10: 动态线宽 (Fix 3) ----
    def test_t10_dynamic_width_full(self):
        """T10 (v3 升级): 完整 5:4:3 三档线宽 (v2 旧 4:3:2)"""
        self.assertRegex(self.func,
                         r"lineWidth\s*=\s*diag\s*<\s*120\s*\?\s*5\s*:\s*diag\s*<\s*240\s*\?\s*4\s*:\s*3")


if __name__ == "__main__":
    unittest.main()
