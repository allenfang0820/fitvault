"""B+ Canvas v4 严格网格规范测试 (纯黑底 + 实心白 1px 正方形网格)

契约:fit-arch-contrac §2.1 字段全链路可追溯 / §九 目录与依赖
覆盖: docs/b_plus_canvas_track_thumbnail_prompt_v4.md §四 测试场景
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
        self.assertNotIn("#0f172a", self.func, "v4: 不应再有 v3 的 #0f172a")
        self.assertRegex(self.func, r"fillStyle\s*=\s*['\"]#000000['\"]")
        self.assertRegex(self.func, r"fillRect\s*\(\s*0\s*,\s*0\s*,\s*maxW\s*,\s*maxH\s*\)")

    def test_no_alpha_blending(self):
        """v4: 背景必须无透明/渐变 (rgba/gradient/alpha 都不能用)"""
        m = re.search(r"fillStyle\s*=\s*['\"]#000000['\"]", self.func)
        self.assertIsNotNone(m)
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
        self.assertNotIn("rgba(148, 163, 184, 0.18)", self.func,
                         "v4: 不应再有 v3 的 18% 透明网格")

    def test_line_width_1px(self):
        """v4: 网格线宽 1px (用户规范)"""
        idx_stroke = self.func.find("strokeStyle = '#FFFFFF'")
        self.assertGreater(idx_stroke, 0, "v4: 缺少 strokeStyle = '#FFFFFF'")
        idx_linewidth = self.func.rfind("lineWidth = 1", 0, idx_stroke)
        self.assertGreater(idx_linewidth, 0, "v4: lineWidth = 1 必须在 strokeStyle 之前")

    def test_horizontal_grid_lines(self):
        """v4: 横向网格线 (从 cellSize 像素开始, 步长 cellSize)"""
        self.assertRegex(self.func, r"for\s*\(\s*let\s+x\s*=\s*CELL_SIZE\s*;\s*x\s*<\s*maxW")

    def test_vertical_grid_lines(self):
        """v4: 纵向网格线 (从 cellSize 像素开始, 步长 cellSize)"""
        self.assertRegex(self.func, r"for\s*\(\s*let\s+y\s*=\s*CELL_SIZE\s*;\s*y\s*<\s*maxH")


class TestV4SquareGrid(unittest.TestCase):
    """v4 升级: 正方形网格 (固定像素边长)"""

    @classmethod
    def setUpClass(cls):
        cls.src = _TRACK_HTML.read_text(encoding="utf-8")
        cls.func = _extract_function("buildTrackThumbnailCanvas", cls.src)

    def test_cell_size_constant(self):
        """v4: 网格单元固定 40px × 40px (正方形)"""
        self.assertRegex(self.func, r"const\s+CELL_SIZE\s*=\s*40",
                         "v4: 必须有 const CELL_SIZE = 40")

    def test_no_4x2_grid(self):
        """v4: 不应再有 v3 的 4 等分横线 / 2 等分纵线"""
        self.assertNotIn("i < 4", self.func, "v4: 不应再有 v3 的 4 等分循环")
        self.assertNotIn("i < 2", self.func, "v4: 不应再有 v3 的 2 等分循环")
        self.assertNotRegex(self.func, r"for\s*\(\s*let\s+i\s*=\s*1\s*;\s*i\s*<\s*[24]")

    def test_full_coverage(self):
        """v4: 网格覆盖全画布 (循环条件 x < maxW, y < maxH)"""
        self.assertRegex(self.func, r"x\s*<\s*maxW")
        self.assertRegex(self.func, r"y\s*<\s*maxH")
        self.assertRegex(self.func, r"x\s*\+=\s*CELL_SIZE")
        self.assertRegex(self.func, r"y\s*\+=\s*CELL_SIZE")

    def test_square_shape_math(self):
        """v4 升级: 横/纵网格步长相同 (正方形)"""
        # 验证 x 步长 == y 步长 == CELL_SIZE
        self.assertRegex(self.func, r"x\s*\+=\s*CELL_SIZE")
        self.assertRegex(self.func, r"y\s*\+=\s*CELL_SIZE")

    def test_subpixel_alignment(self):
        """v4: 1px 网格抗锯齿 (x+0.5 / y+0.5 像素对齐技巧)"""
        self.assertRegex(self.func, r"x\s*\+\s*0\.5")
        self.assertRegex(self.func, r"y\s*\+\s*0\.5")


class TestV4NoOuterBorder(unittest.TestCase):
    """v4 简化: 删除 v3 的 35% 半透明外边框"""

    @classmethod
    def setUpClass(cls):
        cls.src = _TRACK_HTML.read_text(encoding="utf-8")
        cls.func = _extract_function("buildTrackThumbnailCanvas", cls.src)

    def test_no_outer_border(self):
        """v4: 不再有 strokeRect 外边框 (白色 1px 网格已足够)"""
        self.assertNotIn("strokeRect", self.func, "v4: 不应再有 strokeRect 外边框")
        self.assertNotIn("rgba(148, 163, 184, 0.35)", self.func,
                         "v4: 不应再有 v3 的 35% 半透明外边框颜色")


# ══════════════════════════════════════════════════════════════════
# V1 不同分辨率设备验证 (用户要求 #1)
# ══════════════════════════════════════════════════════════════════

class TestV4MultiResolution(unittest.TestCase):
    """V1: 不同分辨率设备下网格不变形"""

    @classmethod
    def setUpClass(cls):
        cls.src = _TRACK_HTML.read_text(encoding="utf-8")
        cls.func = _extract_function("buildTrackThumbnailCanvas", cls.src)

    def test_cell_size_resolution_independent(self):
        """V1: 网格单元 40px 是固定值, 不受 maxW/maxH 影响"""
        # 关键: CELL_SIZE 必须是字面常量, 不能从 maxW/maxH 推算
        self.assertRegex(self.func, r"const\s+CELL_SIZE\s*=\s*40",
                         "V1: CELL_SIZE 必须硬编码 40, 不可依赖容器尺寸")
        # 确保 CELL_SIZE 没有参与 maxW/maxH 表达式
        self.assertNotRegex(self.func, r"CELL_SIZE\s*=\s*max[WH]")
        self.assertNotRegex(self.func, r"CELL_SIZE\s*=\s*Math\.(min|max)")

    def test_grid_pure_horizontal(self):
        """V1: 横线不依赖 maxH 比例 (避免随高度拉伸)"""
        # v3 是 y = (i/4) * maxH, v4 必须是 y = y + CELL_SIZE
        self.assertNotRegex(self.func, r"y\s*=\s*\(\s*i\s*/\s*\d+\s*\)\s*\*\s*maxH")
        self.assertRegex(self.func, r"y\s*\+=\s*CELL_SIZE")

    def test_grid_pure_vertical(self):
        """V1: 纵线不依赖 maxW 比例 (避免随宽度拉伸)"""
        self.assertNotRegex(self.func, r"x\s*=\s*\(\s*i\s*/\s*\d+\s*\)\s*\*\s*maxW")
        self.assertRegex(self.func, r"x\s*\+=\s*CELL_SIZE")


# ══════════════════════════════════════════════════════════════════
# V2 对比度验证 (用户要求 #2)
# ══════════════════════════════════════════════════════════════════

class TestV4Contrast(unittest.TestCase):
    """V2: 轨迹线条 vs 黑底白网格对比度"""

    @classmethod
    def setUpClass(cls):
        cls.src = _TRACK_HTML.read_text(encoding="utf-8")
        cls.func = _extract_function("buildTrackThumbnailCanvas", cls.src)

    def test_high_contrast_palette(self):
        """V2: 轨迹使用亮色 (emerald/cyan/sky) 在黑底上对比度高"""
        # 确认亮色渐变 (非暗色)
        self.assertIn("#34d399", self.func, "V2: 渐变起点 #34d399 (emerald-400)")
        self.assertIn("#22d3ee", self.func, "V2: 渐变中段 #22d3ee (cyan-400)")
        self.assertIn("#38bdf8", self.func, "V2: 渐变终点 #38bdf8 (sky-400)")

    def test_antialiasing_preserved(self):
        """V2: 抗锯齿保留 (Retina 屏轨迹清晰)"""
        self.assertIn("imageSmoothingQuality", self.func)
        self.assertIn("'high'", self.func)

    def test_shadow_glow_for_separation(self):
        """V2: 阴影发光增强轨迹 vs 网格的视觉分离"""
        self.assertIn("shadowBlur", self.func)
        # sky-400 阴影 (rgba(56, 189, 248, ...))
        self.assertIn("56, 189, 248", self.func)

    def test_thick_line_for_visibility(self):
        """V2: 轨迹线宽 3-5px (在 1px 网格上明显)"""
        # v3/v4 动态线宽 5/4/3
        self.assertRegex(self.func, r"diag\s*<\s*120\s*\?\s*5\s*:\s*diag\s*<\s*240\s*\?\s*4\s*:\s*3")

    def test_endpoint_markers_high_contrast(self):
        """V2: 起终点标点白/黄底在黑底上高对比"""
        self.assertIn("#f8fafc", self.func, "V2: 起点白底")
        self.assertIn("#fbbf24", self.func, "V2: 终点黄底")
        self.assertRegex(self.func, r"\.arc\s*\([^)]*,\s*6\s*,")


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
        self.assertIn("56, 189, 248", self.func)

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

    def test_v3_hidpi_preserved(self):
        """v3: HiDPI devicePixelRatio"""
        self.assertIn("devicePixelRatio", self.func)


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

    def test_no_zoom_pan_interaction(self):
        """决策 A: v4 不实现缩放/平移交互 (用户决策)"""
        # v4 保持静态缩略图职责
        for kw in ["onwheel", "addEventListener('wheel'", "onmousedown", "ondrag",
                   "requestAnimationFrame", "wheelDelta"]:
            self.assertNotIn(kw, self.func, f"v4 (决策 A) 不应实现 {kw} 交互")


if __name__ == "__main__":
    unittest.main()
