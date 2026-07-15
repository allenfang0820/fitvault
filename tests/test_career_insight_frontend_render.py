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
    "storage_ref",
    "path",
    "thumbnail_url",
    "detail_link",
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


class TestCareerInsightFrontendRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TRACK_HTML_PATH.read_text(encoding="utf-8")

    def test_insight_section_is_annual_only_without_full_career_controls(self):
        section = extract_between(
            self.source,
            '<section class="career-section" data-career-section="insight">',
            '</section>',
        )
        self.assertIn("年度 AI 总结", section)
        self.assertIn('id="career-insight-status-text"', section)
        self.assertIn('id="career-insight-source"', section)
        self.assertIn('id="career-year-selector"', section)
        self.assertIn('id="career-insight-card"', section)
        self.assertIn('id="career-insight-empty"', section)
        self.assertNotIn("生涯总结", section)
        self.assertNotIn("刷新本地洞察", section)
        self.assertNotIn("career-insight-mode", section)
        self.assertNotIn("career-insight-refresh", section)
        self.assertNotIn("<pre", section)
        self.assertNotIn("JSON.stringify", section)
        self.assertNotIn("get_latest_career_snapshot", section)

    def test_app_state_keeps_only_year_insight_viewmodels(self):
        state_slice = extract_between(
            self.source,
            "career: {",
            "}\n    };",
        )
        self.assertIn("yearInsight: null", state_slice)
        self.assertIn("yearInsightByYear", state_slice)
        self.assertNotIn("insight: null", state_slice)
        self.assertNotIn("insightLoading", state_slice)
        self.assertNotIn("insightRefreshSaving", state_slice)

    def test_annual_loader_is_the_only_insight_frontend_api(self):
        load_body = extract_function_body(self.source, "async function loadCareerYearInsight(options)")
        generate_body = extract_function_body(self.source, "async function generateCareerYearInsight()")
        self.assertIn("window.pywebview.api.get_career_year_insight", load_body)
        self.assertIn("window.pywebview.api.generate_career_year_insight", generate_body)
        self.assertNotIn("generate_career_insight", load_body + generate_body)
        self.assertNotIn("get_latest_career_snapshot", load_body + generate_body)
        self.assertNotIn("call_llm", load_body + generate_body)

    def test_switching_to_career_loads_modules_but_keeps_insight_lazy(self):
        body = extract_function_body(self.source, "function switchTab(tabBtn)")
        load_body = extract_function_body(self.source, "async function loadCareerData()")
        self.assertIn("loadCareerData().catch", body)
        self.assertIn("loadCareerOverview().catch", load_body)
        self.assertIn("loadCareerTimeline().catch", load_body)
        self.assertIn("loadCareerMemory().catch", load_body)
        self.assertNotIn("loadCareerInsight", load_body)

    def test_full_career_frontend_functions_are_removed(self):
        for token in (
            "function normalizeCareerInsight(",
            "function renderCareerInsight(",
            "function setCareerInsightMode(",
            "async function loadCareerInsight(",
            "window.pywebview.api.generate_career_insight",
        ):
            self.assertNotIn(token, self.source)

    def test_mobile_style_keeps_insight_toolbar_single_column(self):
        mobile_css = extract_between(
            self.source,
            "@media (max-width: 980px)",
            "/* V1.0:三个预留 tab",
        )
        self.assertIn(".career-insight-toolbar", mobile_css)
        self.assertIn("flex-direction: column", mobile_css)
        self.assertIn("align-items: flex-start", mobile_css)


if __name__ == "__main__":
    unittest.main()
