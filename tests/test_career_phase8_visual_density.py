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
    if brace_start < 0:
        raise AssertionError(f"未找到 CSS 选择器主体: {selector}")
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


class TestCareerPhase8VisualDensity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TRACK_HTML_PATH.read_text(encoding="utf-8")
        cls.career_panel = extract_between(
            cls.source,
            '<div id="panel-career" class="tab-panel">',
            '<!-- ========== 【轨迹分析工具】面板 ========== -->',
        )
        cls.mobile_css = extract_between(
            cls.source,
            "@media (max-width: 980px)",
            "/* V1.0:三个预留 tab",
        )

    def test_header_copy_is_compact_and_not_placeholder_copy(self):
        subtitle_match = re.search(r'<p class="career-subtitle">([^<]+)</p>', self.career_panel)
        self.assertIsNotNone(subtitle_match)
        subtitle = subtitle_match.group(1)

        self.assertLessEqual(len(subtitle), 55)
        self.assertNotIn("当前仅建立页面入口", subtitle)
        self.assertNotIn("结构壳", subtitle)
        self.assertNotIn("coming soon", subtitle.lower())

        header_css = css_block(self.source, ".career-header")
        subtitle_css = css_block(self.source, ".career-subtitle")
        self.assertIn("padding: 12px 14px", header_css)
        self.assertIn("font-size: 0.72rem", subtitle_css)
        self.assertIn("line-height: 1.42", subtitle_css)
        self.assertIn("max-width: 620px", subtitle_css)

    def test_cards_keep_compact_professional_dimensions(self):
        metric_css = css_block(self.source, ".career-metric-placeholder")
        section_css = css_block(self.source, ".career-section")
        bucket_list_css = css_block(self.source, ".career-bucket-list")
        bucket_css = css_block(self.source, ".career-bucket")
        timeline_node_css = css_block(self.source, ".career-timeline-node")
        memory_item_css = css_block(self.source, ".career-memory-item")
        insight_card_css = css_block(self.source, ".career-insight-card")

        self.assertIn("padding: 12px", section_css)
        self.assertIn("min-height: 70px", metric_css)
        self.assertIn("border-radius: 8px", metric_css)
        self.assertIn("grid-template-columns: 1fr", bucket_list_css)
        self.assertIn("min-height: 0", bucket_css)
        self.assertIn("padding: 5px 8px", timeline_node_css)
        self.assertIn("display: block", timeline_node_css)
        self.assertIn("min-height: 32px", timeline_node_css)
        self.assertIn("width: clamp(112px, 18%, 156px)", timeline_node_css)
        self.assertIn("padding: 10px", memory_item_css)
        self.assertIn("padding: 10px", insight_card_css)

    def test_timeline_large_scroll_uses_month_progressive_expansion(self):
        track_body = extract_function_body(self.source, "function careerTimelineTrackHtml(month, track)")
        visible_body = extract_function_body(self.source, "function careerTimelineTrackVisibleNodes(nodes, expanded)")
        expand_body = extract_function_body(self.source, "function expandCareerTimelineTrack(buttonEl)")

        self.assertIn("const CAREER_TIMELINE_TRACK_INITIAL_LIMIT = 3", self.source)
        self.assertIn("sorted.slice(0, CAREER_TIMELINE_TRACK_INITIAL_LIMIT)", visible_body)
        self.assertIn("更多", track_body)
        self.assertIn("career-timeline-track-more", track_body)
        self.assertNotIn("nodes.map(careerTimelineNodeHtml)", track_body)
        self.assertIn("timelineExpandedMonths[key] = true", expand_body)
        self.assertIn("renderCareerTimeline(appState.career.timeline)", expand_body)

    def test_no_legacy_honor_wall_or_hero_shape_in_career_panel(self):
        for token in (
            "coming-soon-overlay",
            "honor-photo",
            "honor-card",
            "赛事照片占位",
            "overview-hero-area",
            "profile-hero",
            "marketing",
        ):
            self.assertNotIn(token, self.career_panel)

    def test_mobile_and_long_text_constraints_prevent_horizontal_overflow(self):
        self.assertIn(".career-layout", self.mobile_css)
        self.assertIn(".career-overview-grid", self.mobile_css)
        self.assertIn(".career-bucket-list", self.mobile_css)
        self.assertIn(".career-spotlight", self.mobile_css)
        self.assertIn("grid-template-columns: 1fr", self.mobile_css)
        self.assertIn("flex-wrap: wrap", self.mobile_css)

        for selector in (
            ".career-timeline-node-title",
            ".career-timeline-node-meta",
            ".career-memory-title",
            ".career-insight-status",
        ):
            self.assertIn("overflow-wrap: anywhere", css_block(self.source, selector))


if __name__ == "__main__":
    unittest.main()
