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
    """v3 → v4 升级: 纯黑底填充"""

    @classmethod
    def setUpClass(cls):
        cls.src = _TRACK_HTML.read_text(encoding="utf-8")
        cls.func = _extract_function("buildTrackThumbnailCanvas", cls.src)

    def test_dark_fill_color(self):
        """v4 升级: 纯黑底 #000000 (v3 是 #0f172a, v4 升级到纯黑)"""
        self.assertIn("#000000", self.func, "v4: 缺少纯黑底 #000000")
        self.assertRegex(self.func, r"fillStyle\s*=\s*['\"]#000000['\"]")
        self.assertRegex(self.func, r"fillRect\s*\(")
        # v4 不应再有 v3 的 slate-900
        self.assertNotIn("#0f172a", self.func, "v4: 不应再有 v3 的 #0f172a")


class TestV3Grid(unittest.TestCase):
    """v3 → v4 升级: 实心白 1px 正方形网格"""

    @classmethod
    def setUpClass(cls):
        cls.src = _TRACK_HTML.read_text(encoding="utf-8")
        cls.func = _extract_function("buildTrackThumbnailCanvas", cls.src)

    def test_grid_color(self):
        """v4 升级: 实心白 #FFFFFF (v3 是 rgba 18% 透明 slate-400)"""
        self.assertIn("#FFFFFF", self.func, "v4: 缺少实心白 #FFFFFF")
        # v4 不应再有 v3 的半透明网格颜色
        self.assertNotIn("rgba(148, 163, 184, 0.18)", self.func,
                         "v4: 不应再有 v3 的 18% 透明网格")

    def test_grid_horizontal_lines(self):
        """v4: 横向网格线 (cellSize 步长, 从 CELL_SIZE 开始)"""
        # v4 新模式: for (let x = CELL_SIZE; x < maxW; x += CELL_SIZE)
        self.assertRegex(self.func, r"for\s*\(\s*let\s+x\s*=\s*CELL_SIZE\s*;\s*x\s*<\s*maxW")

    def test_grid_vertical_lines(self):
        """v4: 纵向网格线 (cellSize 步长, 从 CELL_SIZE 开始)"""
        # v4 新模式: for (let y = CELL_SIZE; y < maxH; y += CELL_SIZE)
        self.assertRegex(self.func, r"for\s*\(\s*let\s+y\s*=\s*CELL_SIZE\s*;\s*y\s*<\s*maxH")

    def test_grid_outer_border(self):
        """v4 升级: 删除外边框 (白色 1px 网格已足够)"""
        # v4 不应再有 strokeRect
        self.assertNotIn("strokeRect", self.func, "v4: 不应再有 strokeRect 外边框")
        # v4 不应再有 v3 的 35% 半透明外框颜色
        self.assertNotIn("rgba(148, 163, 184, 0.35)", self.func,
                         "v4: 不应再有 v3 的 35% 半透明外边框颜色")


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
        # 关键字搜索: 必须不是作为变量名/字符串子串
        # 排除 "echarts" 的合法引用 (imageSmoothingEnabled 等)
        forbidden_libs = {
            "d3": ["d3.", "import d3", "from d3", "require('d3", "d3.min"],
            "mapbox": ["mapboxgl.", "mapbox-gl", "new mapbox"],
            "leaflet": ["leaflet.", "l.map(", "l.tile"],
            "turf": ["turf.", "@turf/"],
        }
        for lib, patterns in forbidden_libs.items():
            for p in patterns:
                self.assertNotIn(p.lower(), self.func.lower(),
                                 f"v3 禁止引入外部库: {lib} (匹配: {p})")

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
