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


class TestCareerGapP111FrontendDataLinkage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TRACK_HTML_PATH.read_text(encoding="utf-8")
        cls.career_panel = extract_between(
            cls.source,
            '<div id="panel-career" class="tab-panel">',
            '<!-- ========== 【轨迹分析工具】面板 ========== -->',
        )

    def test_career_loaders_consume_real_backend_apis(self):
        expectations = {
            "async function loadCareerOverview()": ("get_career_overview",),
            "async function loadCareerSeasons(filters)": ("get_career_seasons",),
            "async function loadCareerTimeline(filters)": ("get_career_timeline",),
            "async function loadCareerArchives()": ("get_career_races", "get_career_pb", "get_career_achievements"),
            "async function loadCareerMemory(filters)": ("get_career_memory_gallery",),
            "async function loadCareerInsight(options)": ("generate_career_insight",),
        }
        for signature, api_names in expectations.items():
            body = extract_function_body(self.source, signature)
            self.assertIn("requireCareerApiData", body)
            for api_name in api_names:
                self.assertIn(f".{api_name}", body)
            self.assertNotIn("mock", body.lower())

    def test_career_panel_is_not_overlay_or_legacy_honor_wall(self):
        panel_css = css_block(self.source, "#panel-career")
        shell_css = css_block(self.source, ".career-shell")

        self.assertIn("background: #020617", panel_css)
        self.assertIn("overflow: hidden", panel_css)
        self.assertIn("background: #020617", shell_css)
        self.assertNotIn("position: fixed", panel_css)
        for token in (
            "coming-soon-overlay",
            "honor-card",
            "honor-photo",
            "赛事照片占位",
            "半透明",
            "overlay",
        ):
            self.assertNotIn(token, self.career_panel)

    def test_timeline_flow_does_not_promote_plain_activity_or_candidate_lists(self):
        timeline_body = extract_function_body(self.source, "async function loadCareerTimeline(filters)")
        render_body = extract_function_body(self.source, "function renderCareerTimeline(viewModel)")

        self.assertIn("get_career_timeline", timeline_body)
        self.assertIn("careerTimelineYearHtml", render_body)
        for token in (
            "get_activity_list",
            "renderSportHubRecords",
            "set_activity_race_flag",
            "resolve_race_events",
            "get_career_event_candidates",
            "resolve_career_event_candidate",
            "candidatesCount",
            "careerCandidateListHtml",
            "career-timeline-candidates",
        ):
            self.assertNotIn(token, timeline_body + render_body)
            self.assertNotIn(token, self.career_panel)

    def test_archives_keep_fact_derivation_out_of_frontend(self):
        relevant = "\n".join(
            extract_function_body(self.source, signature)
            for signature in (
                "function normalizeCareerArchiveRace(item)",
                "function normalizeCareerArchivePb(item)",
                "function normalizeCareerArchiveAchievement(item)",
                "function normalizeCareerTimelineNode(item)",
                "function careerTimelineNodeMeta(node)",
                "function careerRaceArchiveCardHtml(item)",
                "function careerPbArchiveCardHtml(item)",
                "function careerAchievementArchiveCardHtml(item)",
            )
        )
        for forbidden in (
            "points",
            "points_json",
            "track_json",
            "file_path",
            "raw FIT",
            "SQLite",
            "is_race",
            "race_confidence",
            "finish_time_sec",
        ):
            self.assertNotIn(forbidden, relevant)
        for inference_token in ("马拉松", "半马", "10K", "5K"):
            self.assertNotIn(inference_token, relevant)

    def test_footprint_copy_uses_full_career_language_not_race_only_language(self):
        self.assertIn("生涯足迹", self.career_panel)
        self.assertIn("按 Activity 地理信息点亮行政区域", self.career_panel)
        self.assertNotIn("仅展示已绑定 Activity 的赛事起点", self.career_panel)
        self.assertIn("照片从赛事活动详情页绑定进入", self.career_panel)
        self.assertNotIn("career-memory-story-activity-id", self.career_panel)


if __name__ == "__main__":
    unittest.main()
