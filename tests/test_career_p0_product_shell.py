import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACK_HTML_PATH = PROJECT_ROOT / "track.html"


def extract_between(source: str, start_marker: str, end_marker: str) -> str:
    start = source.find(start_marker)
    if start < 0:
        raise AssertionError(f"未找到起始标记: {start_marker}")
    end = source.find(end_marker, start + len(start_marker))
    if end < 0:
        raise AssertionError(f"未找到结束标记: {end_marker}")
    return source[start:end]


def extract_function_body(source: str, signature: str) -> str:
    start = source.find(signature)
    if start < 0:
        raise AssertionError(f"未找到函数签名: {signature}")
    brace_start = source.find("{", start + len(signature))
    if brace_start < 0:
        raise AssertionError(f"未找到函数体起始: {signature}")
    depth = 1
    index = brace_start + 1
    while index < len(source) and depth > 0:
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        index += 1
    if depth != 0:
        raise AssertionError(f"函数体括号不闭合: {signature}")
    return source[brace_start + 1:index - 1]


def css_block(source: str, selector: str) -> str:
    start = source.find(selector + " {")
    if start < 0:
        raise AssertionError(f"未找到 CSS 选择器: {selector}")
    brace_start = source.find("{", start + len(selector))
    depth = 1
    index = brace_start + 1
    while index < len(source) and depth > 0:
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        index += 1
    if depth != 0:
        raise AssertionError(f"CSS 选择器主体括号不闭合: {selector}")
    return source[brace_start + 1:index - 1]


class TestCareerP0ProductShell(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TRACK_HTML_PATH.read_text(encoding="utf-8")
        cls.career_panel = extract_between(
            cls.source,
            '<div id="panel-career" class="tab-panel">',
            '<!-- ========== 【轨迹分析工具】面板 ========== -->',
        )

    def test_profile_panel_is_not_forced_visible_behind_career(self):
        profile_css = css_block(self.source, "#panel-profile")
        hidden_css = css_block(self.source, ".tab-panel:not(.active)")
        switch_body = extract_function_body(self.source, "function switchTab(tabBtn)")

        self.assertNotIn("display: flex", profile_css)
        self.assertIn("display: none !important", hidden_css)
        self.assertIn("visibility: hidden", hidden_css)
        self.assertIn("pointer-events: none", hidden_css)
        self.assertIn("document.querySelectorAll('.tab-panel').forEach", switch_body)
        self.assertIn("p.classList.remove('active')", switch_body)

    def test_career_shell_is_independent_opaque_product_page(self):
        shell_css = css_block(self.source, ".career-shell")
        section_css = css_block(self.source, ".career-section")

        self.assertIn("background: #020617", shell_css)
        self.assertIn("isolation: isolate", shell_css)
        self.assertIn("rgba(15, 23, 42, 0.92)", section_css)
        self.assertIn('data-acs-product-shell="v1"', self.career_panel)

    def test_career_top_secondary_navigation_matches_acs_modules(self):
        self.assertIn('aria-label="ACS 二级页面导航"', self.career_panel)
        expected = {
            "overview": "总览",
            "timeline": "时间轴",
            "races": "赛事档案",
            "pb": "PB",
            "achievements": "荣誉",
            "insight": "AI 总结",
            "footprint": "足迹",
        }
        for page, label in expected.items():
            self.assertIn(f'data-career-page-target="{page}"', self.career_panel)
            self.assertIn(f'data-career-page="{page}"', self.career_panel)
            self.assertIn(label, self.career_panel)

        switch_page_body = extract_function_body(self.source, "function switchCareerPage(page)")
        self.assertIn("validPages", switch_page_body)
        self.assertIn("career-page-title", switch_page_body)
        self.assertIn("data-career-page-target", switch_page_body)

    def test_career_panel_does_not_static_render_raw_or_local_fields(self):
        for forbidden in ("window.pywebview.api", "points", "track_json", "raw FIT", "file_path", "storage_ref"):
            self.assertNotIn(forbidden, self.career_panel)


if __name__ == "__main__":
    unittest.main()
