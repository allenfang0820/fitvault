import json
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACK_HTML_PATH = PROJECT_ROOT / "track.html"
CONTRACT_PATH = PROJECT_ROOT / "docs" / "js_api_contract.json"

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


class TestCareerOverviewFrontendIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TRACK_HTML_PATH.read_text(encoding="utf-8")

    def test_track_html_has_safe_career_overview_call_point(self):
        self.assertIn("async function loadCareerOverview()", self.source)
        self.assertIn("window.pywebview.api.get_career_overview()", self.source)
        self.assertIn("if (activePanel === 'career')", self.source)
        switch_body = extract_function_body(self.source, "function switchTab(tabBtn)")
        load_body = extract_function_body(self.source, "async function loadCareerData()")
        self.assertIn("loadCareerData().catch", switch_body)
        self.assertIn("refresh_career_derived_events", load_body)
        self.assertIn("loadCareerOverview().catch", load_body)

    def test_career_overview_normalizer_outputs_stable_view_model(self):
        body = extract_function_body(self.source, "function normalizeCareerOverview(payload)")
        self.assertIn("summary:", body)
        self.assertIn("identity:", body)
        self.assertIn("heroBanner:", body)
        self.assertIn("sportTotals:", body)
        self.assertIn("careerStats:", body)
        self.assertIn("bestPb:", body)
        self.assertIn("latestRace:", body)
        self.assertIn("latestPb:", body)
        self.assertIn("representativePbRecords:", body)
        self.assertIn("representativeAchievements:", body)
        self.assertIn("status:", body)
        self.assertIn("careerStartYear", body)
        self.assertIn("activityCount", body)
        self.assertIn("dataReady", body)
        self.assertIn("normalizeCareerIdentity(data.identity)", body)
        self.assertIn("normalizeCareerHeroBanner(data.hero_banner)", body)
        self.assertIn("normalizeCareerSportTotals(data.sport_totals)", body)
        self.assertIn("normalizeCareerStats(data.career_stats)", body)
        for token in FORBIDDEN_FRONTEND_TOKENS:
            self.assertNotIn(token, body)

    def test_career_overview_helpers_use_field_whitelists(self):
        helper_bodies = "\n".join(
            extract_function_body(self.source, signature)
            for signature in (
                "function normalizeCareerRace(item)",
                "function normalizeCareerPbRecord(item)",
                "function normalizeCareerAchievement(item)",
                "function normalizeCareerDetailLink(link)",
                "function normalizeCareerIdentity(identity)",
                "function normalizeCareerHeroBanner(hero)",
                "function normalizeCareerSportTotals(totals)",
                "function normalizeCareerStats(stats)",
            )
        )
        self.assertIn("detailLink", helper_bodies)
        self.assertIn("activity_id", helper_bodies)
        self.assertIn("maxAltitudeM", helper_bodies)
        self.assertNotIn("Object.assign", helper_bodies)
        self.assertNotIn("...item", helper_bodies)
        for token in FORBIDDEN_FRONTEND_TOKENS:
            self.assertNotIn(token, helper_bodies)

    def test_career_overview_load_handles_loading_error_and_empty_states(self):
        load_body = extract_function_body(self.source, "async function loadCareerOverview()")
        render_body = extract_function_body(self.source, "function renderCareerOverview(viewModel)")
        self.assertIn("overviewLoading = true", load_body)
        self.assertIn("overviewLoading = false", load_body)
        self.assertIn("overviewError", load_body)
        self.assertIn("try {", load_body)
        self.assertIn("catch (e)", load_body)
        self.assertIn("renderCareerOverviewLoading()", load_body)
        self.assertIn("renderCareerOverviewError(message)", load_body)
        self.assertIn("career-overview-empty", render_body)
        self.assertIn("dataReady", render_body)
        for token in FORBIDDEN_FRONTEND_TOKENS:
            self.assertNotIn(token, load_body + render_body)

    def test_career_shell_has_minimal_overview_targets_without_api_logic(self):
        career_panel = extract_between(
            self.source,
            '<div id="panel-career" class="tab-panel">',
            '<!-- ========== 【轨迹分析工具】面板 ========== -->',
        )
        self.assertIn('id="career-overview-status-text"', career_panel)
        self.assertIn('id="career-overview-hero-banner"', career_panel)
        self.assertIn('data-career-hero-field="title"', career_panel)
        self.assertIn('data-career-hero-field="distance"', career_panel)
        self.assertIn('id="career-overview-grid"', career_panel)
        self.assertIn('data-career-overview-field="runningDistanceKm"', career_panel)
        self.assertIn('data-career-overview-field="swimmingDistanceKm"', career_panel)
        self.assertIn('data-career-overview-field="strengthTotalWeightKg"', career_panel)
        self.assertIn('data-career-overview-field="maxAltitudeM"', career_panel)
        self.assertIn('data-career-overview-field="raceCount"', career_panel)
        self.assertIn('data-career-overview-field="locationFootprint"', career_panel)
        self.assertNotIn('career-command-row', career_panel)
        self.assertNotIn('career-sport-switch', career_panel)
        self.assertNotIn('data-career-sport-scope', career_panel)
        self.assertNotIn('career-overview-status-pill', career_panel)
        self.assertNotIn("window.pywebview.api", career_panel)
        self.assertNotIn("get_career_overview", career_panel)
        for token in FORBIDDEN_FRONTEND_TOKENS:
            self.assertNotIn(token, career_panel)

    def test_frontend_does_not_compute_career_facts(self):
        relevant = "\n".join(
            extract_function_body(self.source, signature)
            for signature in (
                "function normalizeCareerOverview(payload)",
                "function normalizeCareerIdentity(identity)",
                "function normalizeCareerHeroBanner(hero)",
                "function normalizeCareerSportTotals(totals)",
                "function normalizeCareerStats(stats)",
                "function renderCareerHeroBanner(hero)",
                "function renderCareerOverview(viewModel)",
                "async function loadCareerOverview()",
            )
        )
        for token in (
            "resolve_",
            "dist_km",
            "duration_sec",
            "avg_pace",
            "race_confidence",
            "sport_event",
            "career_race_events",
            "career_pb_records",
            "career_achievement_events",
        ):
            self.assertNotIn(token, relevant)

    def test_career_api_contract_methods_remain_registered(self):
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        methods = {item["name"]: item for item in contract["methods"]}
        for name in (
            "get_career_overview",
            "get_career_timeline",
            "get_career_races",
            "get_career_pb",
            "get_career_achievements",
        ):
            self.assertIn(name, methods)
            self.assertEqual(methods[name]["category"], "career")
            self.assertTrue(methods[name]["readonly"])


if __name__ == "__main__":
    unittest.main()
