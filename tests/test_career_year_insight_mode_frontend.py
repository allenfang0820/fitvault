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


def extract_between(source: str, start_marker: str, end_marker: str) -> str:
    start = source.find(start_marker)
    if start < 0:
        raise AssertionError(f"未找到起始标记: {start_marker}")
    end = source.find(end_marker, start + len(start_marker))
    if end < 0:
        raise AssertionError(f"未找到结束标记: {end_marker}")
    return source[start:end]


class TestCareerYearInsightModeFrontend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TRACK_HTML_PATH.read_text(encoding="utf-8")

    def test_insight_section_is_annual_only_with_year_selector(self):
        section = extract_between(
            self.source,
            '<section class="career-section" data-career-section="insight">',
            '</section>',
        )

        self.assertIn("年度 AI 总结", section)
        self.assertIn("年度总结", section)
        self.assertIn('id="career-year-selector"', section)
        self.assertIn('id="career-year-tone-select"', section)
        self.assertIn('value="warm"', section)
        self.assertIn('value="light"', section)
        self.assertIn('value="humorous"', section)
        self.assertIn("报告语气", section)
        self.assertNotIn("生涯总结", section)
        self.assertNotIn("career-insight-mode", section)
        self.assertNotIn("setCareerInsightMode", section)

    def test_state_keeps_only_year_viewmodels(self):
        state_slice = extract_between(self.source, "career: {", "}\n    };")

        for token in (
            "insightMode: 'year'",
            "yearInsight: null",
            "yearInsightByYear",
            "yearInsightNeedsRefresh",
            "careerSourceVersion",
            "yearInsightLoading",
            "yearInsightGenerating",
            "yearInsightError",
            "yearInsightSelectedYear",
            "yearInsightTonePreset: 'warm'",
            "yearInsightRequestId",
            "yearInsightGenerateRequestId",
        ):
            self.assertIn(token, state_slice)
        for token in ("insight: null", "insightLoading", "insightRefreshSaving"):
            self.assertNotIn(token, state_slice)

    def test_year_selector_uses_backend_available_years_only(self):
        body = extract_function_body(self.source, "function renderCareerYearSelector(viewModel)")

        self.assertIn("vm.available_years", body)
        self.assertIn("years.length ? years.map", body)
        self.assertIn("career-year-chip", body)
        self.assertIn("loadCareerYearInsight({ year:", body)
        self.assertLess(body.index("years.map"), body.index("loadCareerYearInsight({ year:"))
        self.assertNotIn("representativeSeasons", body)
        self.assertNotIn("querySelectorAll", body)
        self.assertNotIn("careerSeason", body)
        self.assertNotIn("new Date", body)

    def test_top_nav_to_insight_defaults_to_year_mode_and_backend_default_year(self):
        switch_body = extract_function_body(self.source, "function switchCareerPage(page)")
        enter_body = extract_function_body(self.source, "function enterCareerInsightFromTopNav()")

        self.assertIn("if (nextPage === 'insight') enterCareerInsightFromTopNav()", switch_body)
        self.assertIn("appState.career.insightMode = 'year'", enter_body)
        self.assertIn("loadCareerYearInsight({})", enter_body)
        self.assertNotIn("new Date", enter_body)
        self.assertNotIn("representativeSeasons", enter_body)

    def test_annual_page_calls_only_year_api(self):
        year_load_body = extract_function_body(self.source, "async function loadCareerYearInsight(options)")

        self.assertIn("window.pywebview.api.get_career_year_insight", year_load_body)
        self.assertNotIn("generate_career_insight", year_load_body)
        self.assertNotIn("call_llm", year_load_body)
        self.assertNotIn("function setCareerInsightMode", self.source)
        self.assertNotIn("async function loadCareerInsight", self.source)

    def test_year_load_uses_per_year_cache_unless_refresh_is_required(self):
        body = extract_function_body(self.source, "async function loadCareerYearInsight(options)")

        self.assertIn("yearInsightByYear[cacheKey]", body)
        self.assertIn("careerYearInsightCacheKey", body)
        self.assertIn("tone_preset: requestedTonePreset", body)
        self.assertIn("!appState.career.yearInsightNeedsRefresh[cacheKey]", body)
        self.assertIn("if (cached && !force", body)
        self.assertLess(body.index("if (cached && !force"), body.index("get_career_year_insight"))
        self.assertIn("yearInsightByYear[responseKey] = data", body)
        self.assertIn("sourceChangedDuringRequest", body)

    def test_year_load_updates_selector_before_waiting_for_backend(self):
        body = extract_function_body(self.source, "async function loadCareerYearInsight(options)")

        self.assertIn("renderCareerYearShell()", body)
        self.assertLess(body.index("renderCareerYearShell()"), body.index("renderCareerYearInsightLoading"))
        self.assertLess(body.index("renderCareerYearShell()"), body.index("get_career_year_insight"))

    def test_year_load_does_not_treat_new_badge_or_stale_state_as_cache_invalidation(self):
        body = extract_function_body(self.source, "async function loadCareerYearInsight(options)")

        self.assertIn("appState.career.yearInsightNeedsRefresh[responseKey] = !!sourceChangedDuringRequest", body)
        self.assertNotIn("data.has_source_changes", body)
        self.assertNotIn("data.report_state === 'stale'", body)
        self.assertNotIn("year_update_badges", body)
        self.assertNotIn("updateMap", body)

    def test_season_new_badges_do_not_invalidate_year_report_cache(self):
        body = extract_function_body(self.source, "async function loadCareerSeasons(filters)")

        self.assertIn("normalizeCareerSeasons", body)
        self.assertNotIn("yearInsightNeedsRefresh", body)
        self.assertNotIn("reportUpdateAvailable &&", body)

    def test_generation_result_cache_refresh_depends_on_source_version_only(self):
        body = extract_function_body(self.source, "async function generateCareerYearInsight()")

        self.assertIn("const cacheKey = careerYearInsightCacheKey(selectedYear, responseTone)", body)
        self.assertIn("appState.career.yearInsightNeedsRefresh[cacheKey] = !!sourceChangedDuringRequest", body)
        self.assertNotIn("data.has_source_changes", body)
        self.assertNotIn("data.report_state === 'stale'", body)

    def test_career_data_load_is_gated_and_does_not_preload_full_career_insight(self):
        body = extract_function_body(self.source, "async function loadCareerData()")

        self.assertIn("careerDataLoaded", body)
        self.assertIn("careerDataLoadingPromise", body)
        self.assertIn("careerDataNeedsRefresh", body)
        self.assertIn("sourceUnchanged", body)
        self.assertIn("coreLoadsReady", body)
        self.assertNotIn("loadCareerInsight", body)
        self.assertLess(body.index("loadCareerOverview"), body.index("loadCareerSeasons"))

    def test_year_card_navigation_suppresses_default_load_and_selects_card_year(self):
        body = extract_function_body(self.source, "function openCareerYearInsight(year)")

        self.assertIn("appState.career.suppressInsightAutoLoad = true", body)
        self.assertIn("yearInsightSelectedYear", body)
        self.assertIn("switchCareerPage('insight')", body)
        self.assertIn("return loadCareerYearInsight({", body)
        self.assertIn("year: appState.career.yearInsightSelectedYear", body)
        self.assertIn("tone_preset: appState.career.yearInsightTonePreset", body)


if __name__ == "__main__":
    unittest.main()
