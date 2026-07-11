import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACK_HTML_PATH = PROJECT_ROOT / "track.html"

FORBIDDEN_FRONTEND_TOKENS = (
    "points",
    "points_json",
    "track_json",
    "raw_records",
    "fit_records",
    "file_path",
    "advanced_metrics",
    "shadow_diff_json",
    "sqlite_schema",
    "schema",
)

FORBIDDEN_FACT_TOKENS = (
    "sport_event",
    "race_confidence",
    "dist_km",
    "duration_sec",
    "avg_pace",
    "career_race_events",
    "career_pb_records",
    "career_achievement_events",
)


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
    start = source.find(selector)
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


class TestCareerTimelineFrontendLargeRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TRACK_HTML_PATH.read_text(encoding="utf-8")

    def test_month_level_progressive_rendering_contract_exists(self):
        self.assertIn("const CAREER_TIMELINE_TRACK_INITIAL_LIMIT = 3", self.source)
        self.assertIn("const CAREER_TIMELINE_NODE_MIN_GAP_PERCENT = 19", self.source)
        self.assertIn("const CAREER_TIMELINE_LANE_HEIGHT = 54", self.source)
        self.assertIn("timelineExpandedMonths", self.source)
        self.assertIn("function careerTimelineMonthKey(yearValue, monthValue)", self.source)
        self.assertIn("function careerTimelineTrackKey(yearValue, monthValue, track)", self.source)
        self.assertIn("function resetCareerTimelineExpansion()", self.source)
        self.assertIn("function expandCareerTimelineTrack(buttonEl)", self.source)

    def test_initial_track_render_limits_nodes_and_shows_more_entry(self):
        track_body = extract_function_body(self.source, "function careerTimelineTrackHtml(month, track)")
        visible_body = extract_function_body(self.source, "function careerTimelineTrackVisibleNodes(nodes, expanded)")
        hidden_body = extract_function_body(self.source, "function careerTimelineTrackHiddenNodes(nodes, expanded)")
        self.assertIn("sorted.slice(0, CAREER_TIMELINE_TRACK_INITIAL_LIMIT)", visible_body)
        self.assertIn("slice(CAREER_TIMELINE_TRACK_INITIAL_LIMIT)", hidden_body)
        self.assertIn("careerTimelineLayoutTrackNodes(visibleNodes, month)", track_body)
        self.assertIn("layout.map", track_body)
        self.assertIn("hiddenNodes.length", track_body)
        self.assertIn("更多", track_body)
        self.assertIn("career-timeline-track-more", track_body)
        self.assertIn("data-career-timeline-track-key", track_body)
        self.assertNotIn("nodes.map(careerTimelineNodeHtml)", track_body)

    def test_expand_more_only_marks_the_selected_month_key(self):
        body = extract_function_body(self.source, "function expandCareerTimelineTrack(buttonEl)")
        self.assertIn("data-career-timeline-track-key", body)
        self.assertIn("timelineExpandedMonths[key] = true", body)
        self.assertIn("renderCareerTimeline(appState.career.timeline)", body)
        self.assertNotIn("window.pywebview.api", body)
        self.assertNotIn("loadCareerTimeline", body)

    def test_filter_reload_resets_progressive_render_state(self):
        load_body = extract_function_body(self.source, "async function loadCareerTimeline(filters)")
        type_body = extract_function_body(self.source, "function setCareerTimelineTypeFilter(type)")
        year_body = extract_function_body(self.source, "function setCareerTimelineYearFilter(year)")
        self.assertIn("resetCareerTimelineExpansion()", load_body)
        self.assertIn("loadCareerTimeline(appState.career.timelineFilters)", type_body)
        self.assertIn("loadCareerTimeline(appState.career.timelineFilters)", year_body)

    def test_activity_detail_link_rendering_is_still_reused(self):
        node_body = extract_function_body(self.source, "function careerTimelineNodeHtml(node)")
        track_body = extract_function_body(self.source, "function careerTimelineTrackHtml(month, track)")
        for token in (
            'role="button"',
            'tabindex="0"',
            'data-activity-id="',
            'data-career-source="',
            'onclick="openCareerActivityDetailFromElement(this)"',
            'onkeydown="onCareerActivityDetailKeydown(event, this)"',
        ):
            self.assertIn(token, node_body)
        self.assertIn("careerTimelineNodeHtml", track_body)

    def test_more_button_css_is_stable_for_narrow_windows(self):
        button_css = css_block(self.source, ".career-timeline-track-more,\n        .career-timeline-expand-btn")
        focus_css = css_block(self.source, ".career-timeline-track-more:hover,\n        .career-timeline-track-more:focus,\n        .career-timeline-expand-btn:hover,\n        .career-timeline-expand-btn:focus")
        self.assertIn("width: 100%", button_css)
        self.assertIn("min-height: 30px", button_css)
        self.assertIn("overflow", button_css + focus_css)
        self.assertIn("outline: none", focus_css)

    def test_track_positioning_uses_collision_aware_lane_offsets(self):
        position_body = extract_function_body(self.source, "function careerTimelineNodePositionStyle(node, month)")
        layout_body = extract_function_body(self.source, "function careerTimelineLayoutTrackNodes(nodes, month)")
        track_body = extract_function_body(self.source, "function careerTimelineTrackHtml(month, track)")
        self.assertIn("CAREER_TIMELINE_NODE_MIN_GAP_PERCENT", layout_body)
        self.assertIn("Math.abs(existing - center)", layout_body)
        self.assertIn("CAREER_TIMELINE_LANE_HEIGHT", position_body)
        self.assertIn("topOffset", position_body)
        self.assertIn("data-career-timeline-lane", position_body)
        self.assertIn("careerTimelineLayoutTrackNodes(visibleNodes, month)", track_body)
        self.assertIn("--career-timeline-lane-count", track_body)

    def test_large_render_functions_keep_data_boundary(self):
        relevant = "\n".join(
            extract_function_body(self.source, signature)
            for signature in (
                "function careerTimelineMonthKey(yearValue, monthValue)",
                "function careerTimelineTrackKey(yearValue, monthValue, track)",
                "function resetCareerTimelineExpansion()",
                "function isCareerTimelineMonthExpanded(key)",
                "function careerTimelineSortTrackNodes(nodes)",
                "function careerTimelineTrackVisibleNodes(nodes, expanded)",
                "function careerTimelineTrackHiddenNodes(nodes, expanded)",
                "function careerTimelineNodeLeftPercent(node, month)",
                "function careerTimelineLayoutTrackNodes(nodes, month)",
                "function careerTimelineNodePositionStyle(node, month)",
                "function careerTimelineTrackHtml(month, track)",
                "function careerTimelineMonthHtml(month)",
                "function careerTimelineYearHtml(year)",
                "function expandCareerTimelineTrack(buttonEl)",
            )
        )
        for token in FORBIDDEN_FRONTEND_TOKENS:
            self.assertNotIn(token, relevant)
        for token in FORBIDDEN_FACT_TOKENS:
            self.assertNotIn(token, relevant)
        self.assertNotIn("resolve_", relevant)
        self.assertNotIn("Object.assign", relevant)
        self.assertNotIn("...item", relevant)


if __name__ == "__main__":
    unittest.main()
