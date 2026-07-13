import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACK_HTML_PATH = PROJECT_ROOT / "track.html"

FORBIDDEN_CAREER_TOKENS = (
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
    "storage_ref",
    "display_metadata",
)


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


class TestCareerPhase8CrossPlatformVisualContract(unittest.TestCase):
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

    def test_global_font_and_career_scroll_container_are_cross_platform_safe(self):
        body_css = css_block(self.source, "body")
        shell_css = css_block(self.source, ".career-shell")
        layout_css = css_block(self.source, ".career-layout")
        column_css = css_block(self.source, ".career-column")

        self.assertIn("-apple-system", body_css)
        self.assertIn("BlinkMacSystemFont", body_css)
        self.assertIn('"Segoe UI"', body_css)
        self.assertIn("Roboto", body_css)
        self.assertIn("sans-serif", body_css)

        self.assertIn("height: 100%", shell_css)
        self.assertIn("min-height: 0", shell_css)
        self.assertIn("overflow: auto", shell_css)
        self.assertIn("overflow-x: hidden", shell_css)
        self.assertIn("min-height: 0", layout_css)
        self.assertIn("min-width: 0", column_css)
        self.assertIn("min-height: 0", column_css)

    def test_mobile_css_covers_all_career_regions(self):
        for selector in (
            ".career-layout",
            ".career-overview-grid",
            ".career-bucket-list",
            ".career-spotlight",
            ".career-timeline-month",
            ".career-memory-list",
            ".career-insight-toolbar",
        ):
            self.assertIn(selector, self.mobile_css)
        self.assertIn("grid-template-columns: 1fr", self.mobile_css)
        self.assertIn("flex-direction: column", self.mobile_css)

    def test_career_loaders_have_local_pywebview_error_states(self):
        loader_specs = (
            ("async function loadCareerOverview()", "生涯总览接口暂不可用", "renderCareerOverviewError(message)"),
            ("async function loadCareerTimeline(filters)", "生涯时间轴接口暂不可用", "renderCareerTimelineError(message)"),
            ("async function loadCareerArchives()", "生涯分区接口暂不可用", "renderCareerArchivesError(message)"),
            ("async function loadCareerMemory(filters)", "赛事相册接口暂不可用", "renderCareerMemoryError(message)"),
            ("async function loadCareerInsight(options)", "生涯本地洞察接口暂不可用", "renderCareerInsightError(message)"),
        )
        for signature, unavailable_text, error_renderer in loader_specs:
            body = extract_function_body(self.source, signature)
            self.assertIn("try {", body)
            self.assertIn("catch (e)", body)
            self.assertIn("window.pywebview", body)
            self.assertIn(unavailable_text, body)
            self.assertIn(error_renderer, body)

    def test_switching_to_career_loads_modules_independently(self):
        body = extract_function_body(self.source, "function switchTab(tabBtn)")
        load_body = extract_function_body(self.source, "async function loadCareerData()")
        self.assertIn("loadCareerData().catch", body)
        self.assertIn("refresh_career_derived_events", load_body)
        for token in (
            "loadCareerOverview().catch",
            "loadCareerTimeline().catch",
            "loadCareerArchives().catch",
            "loadCareerMemory().catch",
            "loadCareerInsight({ refresh_snapshot: false }).catch",
        ):
            self.assertIn(token, load_body)

    def test_long_text_constraints_cover_interactive_career_items(self):
        for selector in (
            ".career-spotlight-item .title",
            ".career-spotlight-item .meta",
            ".career-timeline-node-title",
            ".career-timeline-node-meta",
            ".career-archive-title",
            ".career-archive-meta",
            ".career-memory-album-title",
            ".career-memory-album-meta",
            ".career-insight-status",
            ".career-insight-list li",
        ):
            self.assertIn("overflow-wrap: anywhere", css_block(self.source, selector))

    def test_timeline_06b_layout_is_cross_platform_safe(self):
        self.assertIn('id="career-timeline-year-capsules"', self.career_panel)
        self.assertNotIn('id="career-timeline-year-filter"', self.career_panel)
        self.assertNotIn('id="career-timeline-sport-filter"', self.career_panel)
        month_body = extract_function_body(self.source, "function careerTimelineMonthHtml(month)")
        track_body = extract_function_body(self.source, "function careerTimelineTrackHtml(month, track)")
        position_body = extract_function_body(self.source, "function careerTimelineNodePositionStyle(node, month)")
        self.assertIn("career-timeline-month-axis", month_body)
        self.assertIn("career-timeline-track-lane", track_body)
        self.assertIn("career-timeline-track-more", track_body)
        self.assertIn("data-career-timeline-lane", position_body)
        self.assertIn(".career-timeline-track-lane .career-timeline-node", self.mobile_css)
        self.assertIn("left: auto !important", self.mobile_css)
        self.assertIn("transform: none", self.mobile_css)

    def test_career_visual_slice_keeps_security_boundary_and_not_legacy_wall(self):
        relevant = "\n".join(
            extract_function_body(self.source, signature)
            for signature in (
                "function normalizeCareerOverview(payload)",
                "function normalizeCareerTimeline(payload)",
                "function normalizeCareerArchives(payload)",
                "function normalizeCareerMemory(payload)",
                "function normalizeCareerInsight(payload)",
                "function renderCareerArchives(viewModel)",
                "function renderCareerTimeline(viewModel)",
                "function renderCareerMemory(viewModel)",
                "function renderCareerInsight(viewModel)",
            )
        )
        for token in FORBIDDEN_CAREER_TOKENS:
            self.assertNotIn(token, relevant)
        self.assertNotIn("Object.assign", relevant)
        self.assertNotIn("...item", relevant)

        for token in ("coming-soon-overlay", "honor-photo", "honor-card", "赛事照片占位"):
            self.assertNotIn(token, self.career_panel)


if __name__ == "__main__":
    unittest.main()
