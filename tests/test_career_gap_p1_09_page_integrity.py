import re
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


class TestCareerGapP109PageIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TRACK_HTML_PATH.read_text(encoding="utf-8")
        cls.career_panel = extract_between(
            cls.source,
            '<div id="panel-career" class="tab-panel">',
            '<!-- ========== 【轨迹分析工具】面板 ========== -->',
        )

    def test_career_panel_is_opaque_first_level_product_page(self):
        panel_css = css_block(self.source, "#panel-career")
        shell_css = css_block(self.source, ".career-shell")
        hidden_css = css_block(self.source, ".tab-panel:not(.active)")

        self.assertIn("background: #020617", panel_css)
        self.assertIn("padding: 0", panel_css)
        self.assertIn("overflow: hidden", panel_css)
        self.assertIn("isolation: isolate", panel_css)
        self.assertIn("background: #020617", shell_css)
        self.assertIn("overflow: auto", shell_css)
        self.assertIn("display: none !important", hidden_css)
        self.assertIn("visibility: hidden", hidden_css)

    def test_secondary_pages_have_mutual_exclusion_state(self):
        pages = ("overview", "timeline", "races", "pb", "achievements", "insight", "footprint")
        self.assertIn('data-acs-active-page="overview"', self.career_panel)
        self.assertEqual(self.career_panel.count('class="career-page is-active"'), 1)
        for page in pages:
            self.assertIn(f'data-career-page="{page}"', self.career_panel)
        self.assertIn('data-career-page="overview" aria-hidden="false"', self.career_panel)
        for page in pages[1:]:
            self.assertIn(f'data-career-page="{page}" aria-hidden="true"', self.career_panel)

        switch_body = extract_function_body(self.source, "function switchCareerPage(page)")
        self.assertIn("section.setAttribute('aria-hidden'", switch_body)
        self.assertIn("data-acs-active-page", switch_body)
        self.assertIn("data-career-page-target", switch_body)
        self.assertIn("aria-pressed", switch_body)

    def test_achievement_wall_is_formal_archive_not_placeholder(self):
        achievement_section = extract_between(
            self.source,
            '<section class="career-section" data-career-section="achievements">',
            "</section>",
        )
        for token in (
            'id="career-achievement-archive-shell"',
            'id="career-achievement-year-filter"',
            'id="career-achievement-category-filter"',
            'id="career-achievement-type-filter"',
            'id="career-achievement-source-filter"',
            'id="career-achievement-score-filter"',
            'class="career-achievement-list"',
            'data-career-archive-list="achievements"',
        ):
            self.assertIn(token, achievement_section)
        self.assertIn("function careerAchievementArchiveCardHtml(item)", self.source)
        self.assertIn("career-achievement-card", self.source)
        self.assertIn("career-achievement-badge", self.source)
        self.assertNotIn("coming-soon-overlay", achievement_section)
        self.assertNotIn("首版", achievement_section)
        self.assertNotIn("占位", achievement_section)

    def test_each_secondary_page_has_stable_state_targets(self):
        required_targets = (
            "career-overview-status-text",
            "career-overview-empty",
            "career-timeline-status-text",
            "career-timeline-empty",
            "career-archives-status-text",
            "career-archives-empty",
            "career-pb-status-text",
            "career-pb-empty",
            "career-achievement-status-text",
            "career-achievement-empty",
            "career-insight-status-text",
            "career-insight-empty",
            "career-memory-status-text",
            "career-memory-empty",
        )
        for target in required_targets:
            self.assertIn(f'id="{target}"', self.career_panel)

        for signature in (
            "function renderCareerArchivesLoading()",
            "function renderCareerArchivesError(message)",
            "function renderCareerTimelineLoading()",
            "function renderCareerTimelineError(message)",
            "function renderCareerMemoryLoading()",
            "function renderCareerMemoryError(message)",
            "function renderCareerInsightLoading()",
            "function renderCareerInsightError(message)",
        ):
            extract_function_body(self.source, signature)

    def test_no_early_stage_or_overlay_copy_inside_career_panel(self):
        lowered = self.career_panel.lower()
        for token in (
            "coming soon",
            "coming-soon-overlay",
            "代码疯狂产生中",
            "首版先保留",
            "当前仅建立页面入口",
            "结构壳",
            "半透明",
            "overlay",
            "honor-card",
            "honor-photo",
            "赛事照片占位",
        ):
            self.assertNotIn(token.lower(), lowered)
        self.assertIsNone(re.search(r"position\\s*:\\s*fixed", css_block(self.source, "#panel-career")))


if __name__ == "__main__":
    unittest.main()
