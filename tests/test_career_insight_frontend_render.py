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

    def test_career_insight_section_dom_exists_without_snapshot_json(self):
        section = extract_between(
            self.source,
            '<section class="career-section" data-career-section="insight">',
            '</section>',
        )
        self.assertIn("生涯洞察", section)
        self.assertIn('id="career-insight-status-text"', section)
        self.assertIn('id="career-insight-source"', section)
        self.assertIn('id="career-insight-refresh"', section)
        self.assertIn('id="career-insight-card"', section)
        self.assertIn('id="career-insight-empty"', section)
        self.assertIn("刷新本地洞察", section)
        self.assertIn("不会调用 AI", section)
        self.assertNotIn("<pre", section)
        self.assertNotIn("JSON.stringify", section)
        self.assertNotIn("get_latest_career_snapshot", section)

    def test_insight_state_is_in_app_state(self):
        state_slice = extract_between(
            self.source,
            "career: {",
            "}\n    };",
        )
        self.assertIn("insight: null", state_slice)
        self.assertIn("insightLoading", state_slice)
        self.assertIn("insightError", state_slice)
        self.assertIn("insightRefreshSaving", state_slice)

    def test_normalizer_uses_only_whitelisted_fields(self):
        body = extract_function_body(self.source, "function normalizeCareerInsight(payload)")
        for token in (
            "insight.mode",
            "insight.title",
            "insight.summary",
            "insight.highlights",
            "insight.next_steps",
            "insight.disclaimer",
            "snapshot_status",
            "snapshot_version",
            "status.data_ready",
            "status.message",
        ):
            self.assertIn(token, body)
        self.assertNotIn("Object.assign", body)
        self.assertNotIn("...payload", body)
        self.assertNotIn("...item", body)
        for token in FORBIDDEN_FRONTEND_TOKENS:
            self.assertNotIn(token, body)

    def test_render_career_insight_renders_fallback_sections(self):
        body = extract_function_body(self.source, "function renderCareerInsight(viewModel)")
        self.assertIn("career-insight-title", body)
        self.assertIn("career-insight-summary", body)
        self.assertIn("careerInsightListHtml(insight.highlights, 'highlights', '阶段亮点')", body)
        self.assertIn("careerInsightListHtml(insight.nextSteps, 'next-steps', '下一步建议')", body)
        self.assertIn("career-insight-disclaimer", body)
        self.assertNotIn("JSON.stringify", body)
        self.assertNotIn("<pre", body)

    def test_load_career_insight_calls_api_with_refresh_only_payload(self):
        body = extract_function_body(self.source, "async function loadCareerInsight(options)")
        self.assertIn("window.pywebview.api.generate_career_insight", body)
        self.assertIn("const payload = {", body)
        self.assertIn("refresh_snapshot: shouldRefresh", body)
        self.assertIn("requireCareerApiData(res, '生涯本地洞察生成失败')", body)
        self.assertIn("normalizeCareerInsight(requireCareerApiData", body)
        self.assertNotIn("call_llm", body)
        self.assertNotIn("get_latest_career_snapshot", body)
        payload_block = extract_between(body, "const payload = {", "};")
        self.assertIn("refresh_snapshot", payload_block)
        self.assertNotIn("title", payload_block)
        self.assertNotIn("summary", payload_block)
        self.assertNotIn("highlights", payload_block)

    def test_switching_to_career_loads_insight_without_blocking_others(self):
        body = extract_function_body(self.source, "function switchTab(tabBtn)")
        load_body = extract_function_body(self.source, "async function loadCareerData()")
        self.assertIn("loadCareerData().catch", body)
        self.assertIn("loadCareerOverview().catch", load_body)
        self.assertIn("loadCareerTimeline().catch", load_body)
        self.assertIn("loadCareerMemory().catch", load_body)
        self.assertIn("loadCareerInsight({ refresh_snapshot: false }).catch", load_body)

    def test_insight_frontend_keeps_data_boundary(self):
        relevant = "\n".join(
            extract_function_body(self.source, signature)
            for signature in (
                "function normalizeCareerInsight(payload)",
                "function careerInsightListHtml(items, className, label)",
                "function renderCareerInsight(viewModel)",
                "function renderCareerInsightLoading()",
                "function renderCareerInsightError(message)",
                "async function loadCareerInsight(options)",
            )
        )
        for token in FORBIDDEN_FRONTEND_TOKENS:
            self.assertNotIn(token, relevant)
        self.assertNotIn("call_llm", relevant)
        self.assertNotIn("get_latest_career_snapshot", relevant)
        self.assertNotIn("JSON.stringify", relevant)
        self.assertNotIn("Object.assign", relevant)
        self.assertNotIn("...payload", relevant)
        self.assertNotIn("...item", relevant)

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
