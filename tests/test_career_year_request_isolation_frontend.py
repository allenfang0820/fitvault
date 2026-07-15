import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACK_HTML_PATH = PROJECT_ROOT / "track.html"


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


class TestCareerYearRequestIsolationFrontend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TRACK_HTML_PATH.read_text(encoding="utf-8")

    def test_year_load_uses_incrementing_request_id(self):
        body = extract_function_body(self.source, "async function loadCareerYearInsight(options)")

        self.assertIn("yearInsightRequestId", body)
        self.assertIn("const requestId", body)
        self.assertIn("appState.career.yearInsightRequestId = requestId", body)
        self.assertIn("const requestedYear", body)

    def test_late_response_checks_request_mode_and_year_before_writing(self):
        body = extract_function_body(self.source, "async function loadCareerYearInsight(options)")
        write_index = body.index("appState.career.yearInsight = data")
        guard_index = body.index("if (!stillCurrentRequest || !stillYearMode || !stillSameYear)")

        self.assertLess(guard_index, write_index)
        self.assertIn("appState.career.yearInsightRequestId === requestId", body)
        self.assertIn("appState.career.insightMode === 'year'", body)
        self.assertIn("responseYear === requestedYear", body)
        self.assertIn("stale_year_insight_response", body)

    def test_late_error_does_not_overwrite_current_page(self):
        body = extract_function_body(self.source, "async function loadCareerYearInsight(options)")
        error_index = body.index("stale_year_insight_error")
        render_error_index = body.index("renderCareerYearInsightError(message)")

        self.assertLess(error_index, render_error_index)
        self.assertIn("appState.career.yearInsightRequestId !== requestId", body)
        self.assertIn("appState.career.insightMode !== 'year'", body)

    def test_no_generation_or_llm_in_request_isolation(self):
        body = extract_function_body(self.source, "async function loadCareerYearInsight(options)")

        self.assertNotIn("generate_career_year_insight", body)
        self.assertNotIn("generate_career_insight", body)
        self.assertNotIn("call_llm", body)

    def test_generation_action_calls_year_generate_api_with_year_only(self):
        body = extract_function_body(self.source, "async function generateCareerYearInsight()")

        self.assertIn("window.pywebview.api.generate_career_year_insight", body)
        self.assertIn("generate_career_year_insight({ year: selectedYear })", body)
        self.assertIn("requireCareerApiData(res, '年度总结生成失败')", body)
        self.assertNotIn("prompt", body)
        self.assertNotIn("model", body)
        self.assertNotIn("force", body)
        self.assertNotIn("snapshot", body)
        self.assertNotIn("facts", body)
        self.assertNotIn("generate_career_insight", body)
        self.assertNotIn("call_llm", body)

    def test_generation_late_response_checks_request_mode_and_year_before_writing(self):
        body = extract_function_body(self.source, "async function generateCareerYearInsight()")
        write_index = body.index("appState.career.yearInsight = data")
        guard_index = body.index("if (!stillCurrentRequest || !stillYearMode || !stillSameYear)")

        self.assertLess(guard_index, write_index)
        self.assertIn("yearInsightGenerateRequestId", body)
        self.assertIn("appState.career.yearInsightGenerateRequestId === requestId", body)
        self.assertIn("appState.career.insightMode === 'year'", body)
        self.assertIn("responseYear === selectedYear", body)
        self.assertIn("appState.career.yearInsightSelectedYear === selectedYear", body)
        self.assertIn("stale_year_insight_generation_response", body)
        self.assertIn("stale_year_insight_generation_error", body)


if __name__ == "__main__":
    unittest.main()
