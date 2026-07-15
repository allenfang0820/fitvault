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


class TestCareerYearCardNavigationFrontend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TRACK_HTML_PATH.read_text(encoding="utf-8")

    def test_season_card_is_native_button_with_accessible_year_summary_navigation(self):
        body = extract_function_body(self.source, "function careerSeasonCardHtml(season)")

        self.assertIn('<button type="button" class="career-season-card"', body)
        self.assertIn('aria-label="查看 ', body)
        self.assertIn(" 年度总结", body)
        self.assertIn('data-career-season-hint="查看年度总结"', body)
        self.assertIn("openCareerYearInsight", body)
        self.assertIn('class="career-season-year-number"', body)
        self.assertIn("reportUpdateAvailable", body)
        self.assertIn("career-season-new-badge", body)
        self.assertIn("年度报告可更新", body)
        self.assertIn("careerSeasonPillHtml('activities', '活动'", body)
        self.assertIn("careerSeasonPillHtml('distance', '里程'", body)
        self.assertIn("careerSeasonPillHtml('races', '赛事'", body)
        self.assertIn("careerSeasonPillHtml('pbs', 'PB'", body)
        self.assertIn("careerSeasonPillHtml('achievements', '成就'", body)
        self.assertNotIn("not_generated", body)
        self.assertNotIn("stale", body)
        self.assertNotIn("ready", body)
        self.assertNotIn("点击我试试", body)

    def test_year_card_click_switches_to_insight_and_loads_readonly_year_api(self):
        open_body = extract_function_body(self.source, "function openCareerYearInsight(year)")
        load_body = extract_function_body(self.source, "async function loadCareerYearInsight(options)")

        self.assertIn("appState.career.insightMode = 'year'", open_body)
        self.assertIn("yearInsightSelectedYear", open_body)
        self.assertIn("switchCareerPage('insight')", open_body)
        self.assertIn("loadCareerYearInsight({ year:", open_body)
        self.assertIn("window.pywebview.api.get_career_year_insight", load_body)
        self.assertIn("requireCareerApiData(res, '年度总结加载失败')", load_body)
        self.assertNotIn("generate_career_year_insight", open_body + load_body)
        self.assertNotIn("generate_career_insight", open_body + load_body)
        self.assertNotIn("call_llm", open_body + load_body)

    def test_season_card_focus_style_keeps_existing_hover_motion(self):
        self.assertIn(".career-season-card:hover,", self.source)
        self.assertIn(".career-season-card:focus-visible", self.source)
        self.assertIn("transform: translateY(-3px)", self.source)
        self.assertIn("cursor: pointer", self.source)

    def test_normalized_season_carries_report_update_badge_signal(self):
        body = extract_function_body(self.source, "function normalizeCareerSeason(item)")

        self.assertIn("reportUpdateAvailable", body)
        self.assertIn("report_update_available", body)
        self.assertIn(".career-season-new-badge", self.source)


if __name__ == "__main__":
    unittest.main()
