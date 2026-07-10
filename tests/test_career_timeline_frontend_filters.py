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


def extract_between(source: str, start_marker: str, end_marker: str) -> str:
    start = source.find(start_marker)
    if start < 0:
        raise AssertionError(f"未找到起始标记: {start_marker}")
    end = source.find(end_marker, start + len(start_marker))
    if end < 0:
        raise AssertionError(f"未找到结束标记: {end_marker}")
    return source[start:end]


class TestCareerTimelineFrontendFilters(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TRACK_HTML_PATH.read_text(encoding="utf-8")

    def test_timeline_year_and_content_capsules_exist(self):
        panel = extract_between(
            self.source,
            '<div id="panel-career" class="tab-panel">',
            '<!-- ========== 【轨迹分析工具】面板 ========== -->',
        )
        self.assertIn('aria-label="运动生涯时间轴内容筛选"', panel)
        self.assertIn('id="career-timeline-year-capsules"', panel)
        self.assertIn('aria-label="运动生涯时间轴年份筛选"', panel)
        self.assertIn("setCareerTimelineTypeFilter('all')", panel)
        self.assertIn("setCareerTimelineTypeFilter('race')", panel)
        self.assertIn("setCareerTimelineTypeFilter('milestone')", panel)
        self.assertNotIn('id="career-timeline-year-filter"', panel)
        self.assertNotIn('id="career-timeline-sport-filter"', panel)

    def test_career_panel_does_not_inline_timeline_api_calls(self):
        panel = extract_between(
            self.source,
            '<div id="panel-career" class="tab-panel">',
            '<!-- ========== 【轨迹分析工具】面板 ========== -->',
        )
        self.assertNotIn("window.pywebview.api", panel)
        self.assertNotIn("get_career_timeline", panel)
        self.assertNotIn("get_career_overview", panel)

    def test_year_filter_handler_updates_year_and_reloads_timeline(self):
        body = extract_function_body(self.source, "function setCareerTimelineYearFilter(year)")
        self.assertIn("normalizeCareerTimelineFilters(appState.career.timelineFilters)", body)
        self.assertIn("nextYear", body)
        self.assertIn("year: Number.isFinite(nextYear) ? nextYear : null", body)
        self.assertIn("type: current.type", body)
        self.assertIn("loadCareerTimeline(appState.career.timelineFilters)", body)
        self.assertNotIn("window.pywebview.api", body)

    def test_year_capsules_are_derived_from_timeline_years(self):
        helper_body = extract_function_body(self.source, "function careerTimelineYearsFromTimeline(timeline)")
        load_body = extract_function_body(self.source, "async function loadCareerTimeline(filters)")
        render_filters_body = extract_function_body(self.source, "function renderCareerTimelineFilters(filters)")
        capsule_body = extract_function_body(self.source, "function careerTimelineYearCapsuleHtml(year, active)")
        self.assertIn("timeline.years", helper_body)
        self.assertIn("years.sort(function(a, b) { return b - a; })", helper_body)
        self.assertIn("careerTimelineYearsFromTimeline(timeline)", load_body)
        self.assertIn("timelineAvailableYears", load_body)
        self.assertIn("career-timeline-year-capsules", render_filters_body)
        self.assertIn("careerTimelineYearCapsuleHtml(null", render_filters_body)
        self.assertIn("yearCapsules.innerHTML", render_filters_body)
        self.assertIn("data-career-timeline-year", capsule_body)
        self.assertIn("setCareerTimelineYearFilter", capsule_body)

    def test_timeline_filters_do_not_render_sport_filter(self):
        panel = extract_between(
            self.source,
            '<div id="panel-career" class="tab-panel">',
            '<!-- ========== 【轨迹分析工具】面板 ========== -->',
        )
        render_filters_body = extract_function_body(self.source, "function renderCareerTimelineFilters(filters)")
        render_body = extract_function_body(self.source, "function renderCareerTimeline(viewModel)")
        self.assertNotIn("career-timeline-sport-filter", panel + render_filters_body)
        self.assertNotIn("career-timeline-sport-note", panel + render_filters_body)
        self.assertNotIn("careerTimelineSportLabel", render_filters_body)
        self.assertNotIn(".filter(", render_body)
        self.assertNotIn("node.sport", render_body)
        self.assertNotIn("achievement", render_body[render_body.find("yearsEl"):])

    def test_filter_functions_keep_data_boundary(self):
        relevant = "\n".join(
            extract_function_body(self.source, signature)
            for signature in (
                "function normalizeCareerTimelineFilters(filters)",
                "function careerTimelineYearsFromTimeline(timeline)",
                "function careerTimelineYearCapsuleHtml(year, active)",
                "function renderCareerTimelineFilters(filters)",
                "function setCareerTimelineTypeFilter(type)",
                "function setCareerTimelineYearFilter(year)",
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
