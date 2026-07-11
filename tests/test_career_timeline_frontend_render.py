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


class TestCareerTimelineFrontendRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TRACK_HTML_PATH.read_text(encoding="utf-8")

    def test_timeline_dom_targets_and_filters_exist(self):
        career_panel = extract_between(
            self.source,
            '<div id="panel-career" class="tab-panel">',
            '<!-- ========== 【轨迹分析工具】面板 ========== -->',
        )
        self.assertIn('data-career-section="timeline"', career_panel)
        self.assertIn('id="career-timeline-status-text"', career_panel)
        self.assertIn('id="career-timeline-filter-status"', career_panel)
        self.assertIn('id="career-timeline-years"', career_panel)
        self.assertIn('id="career-timeline-year-capsules"', career_panel)
        self.assertIn('id="career-timeline-empty"', career_panel)
        self.assertNotIn('id="career-timeline-candidates"', career_panel)
        self.assertNotIn("career-candidate", career_panel)
        for node_type in ("all", "race", "milestone"):
            self.assertIn(f'data-career-timeline-filter="{node_type}"', career_panel)
            self.assertIn(f"setCareerTimelineTypeFilter('{node_type}')", career_panel)
        self.assertNotIn('data-career-timeline-filter="pb"', career_panel)
        self.assertNotIn("setCareerTimelineTypeFilter('pb')", career_panel)
        self.assertNotIn('id="career-timeline-year-filter"', career_panel)
        self.assertNotIn('id="career-timeline-sport-filter"', career_panel)
        self.assertNotIn("window.pywebview.api", career_panel)
        self.assertNotIn("get_career_timeline", career_panel)

    def test_load_career_timeline_calls_api_and_handles_envelope(self):
        body = extract_function_body(self.source, "async function loadCareerTimeline(filters)")
        self.assertIn("window.pywebview.api.get_career_timeline", body)
        self.assertIn("appState.career.timelineFilters", body)
        self.assertIn("timelineLoading = true", body)
        self.assertIn("timelineLoading = false", body)
        self.assertIn("timelineError", body)
        self.assertIn("requireCareerApiData(res, '生涯时间轴加载失败')", body)
        self.assertIn("normalizeCareerTimeline(requireCareerApiData", body)
        self.assertIn("renderCareerTimelineLoading()", body)
        self.assertIn("renderCareerTimelineError(message)", body)
        self.assertNotIn("get_career_event_candidates", body)
        self.assertNotIn("候选事件加载失败", body)

    def test_normalizer_uses_whitelisted_timeline_fields(self):
        relevant = "\n".join(
            extract_function_body(self.source, signature)
            for signature in (
                "function normalizeCareerTimeline(payload)",
                "function normalizeCareerTimelineYear(item)",
                "function normalizeCareerTimelineMonth(item)",
                "function normalizeCareerTimelineNode(item)",
                "function normalizeCareerTimelineFilters(filters)",
            )
        )
        for token in (
            "years",
            "months",
            "nodes",
            "available_years",
            "activity_id",
            "detail_link",
            "subtype",
            "badge",
            "event_type",
            "pb_type",
            "pb_badge_scope",
            "achievement_type",
            "day",
            "track",
            "priority",
            "meta",
        ):
            self.assertIn(token, relevant)
        self.assertNotIn("season", relevant)
        self.assertNotIn("Object.assign", relevant)
        self.assertNotIn("...item", relevant)
        for token in FORBIDDEN_FRONTEND_TOKENS:
            self.assertNotIn(token, relevant)

    def test_renderers_include_loading_error_and_empty_states(self):
        render_body = extract_function_body(self.source, "function renderCareerTimeline(viewModel)")
        loading_body = extract_function_body(self.source, "function renderCareerTimelineLoading()")
        error_body = extract_function_body(self.source, "function renderCareerTimelineError(message)")
        self.assertIn("career-timeline-empty", render_body)
        self.assertIn("正在加载时间轴", loading_body)
        self.assertIn("时间轴暂不可用", error_body)
        self.assertIn("dataReady", render_body + error_body)
        self.assertNotIn("career-timeline-candidates", render_body)
        self.assertNotIn("candidatesCount", render_body)
        self.assertNotIn("候选事件待确认", render_body)
        self.assertNotIn("careerCandidateListHtml", render_body)

    def test_timeline_does_not_render_candidate_review_workflow(self):
        timeline_panel = extract_between(
            self.source,
            '<section class="career-section" data-career-section="timeline">',
            "</section>",
        )
        for token in (
            "data-career-candidate-id",
            "data-career-candidate-action",
            "confirm_race",
            "dismiss",
            "确认为赛事",
            "不是赛事",
            "careerCandidateCardHtml",
            "careerCandidateListHtml",
            "handleCareerCandidateAction",
            "get_career_event_candidates",
            "resolve_career_event_candidate",
        ):
            self.assertNotIn(token, self.source)
            self.assertNotIn(token, timeline_panel)

    def test_year_renderer_uses_month_band_without_backend_season_summary(self):
        year_body = extract_function_body(self.source, "function careerTimelineYearHtml(year)")
        month_body = extract_function_body(self.source, "function careerTimelineMonthHtml(month)")
        track_body = extract_function_body(self.source, "function careerTimelineTrackHtml(month, track)")
        position_body = extract_function_body(self.source, "function careerTimelineNodePositionStyle(node, month)")
        self.assertNotIn("careerTimelineSeasonSummaryHtml(year)", year_body)
        self.assertIn("career-timeline-year-title", year_body)
        self.assertIn("career-timeline-month-axis", month_body)
        self.assertIn("careerTimelineDayTicksHtml(month)", month_body)
        self.assertIn("careerTimelineTrackHtml(month, 'race', yearValue)", month_body)
        self.assertIn("careerTimelineTrackHtml(month, 'milestone', yearValue)", month_body)
        self.assertIn("data-career-timeline-track", track_body)
        self.assertIn("careerTimelineNodeLeftPercent(node, month)", position_body)
        for token in FORBIDDEN_FACT_TOKENS:
            self.assertNotIn(token, year_body + month_body + track_body + position_body)

    def test_race_pb_crown_is_rendered_from_backend_scope_only(self):
        normalize_body = extract_function_body(self.source, "function normalizeCareerTimelineNode(item)")
        crown_body = extract_function_body(self.source, "function careerTimelinePbCrownHtml(node)")
        node_body = extract_function_body(self.source, "function careerTimelineNodeHtml(node)")
        self.assertIn("pb_badge_scope", normalize_body)
        self.assertIn("pbBadgeScope", normalize_body)
        self.assertIn("scope !== 'career' && scope !== 'season'", crown_body)
        self.assertIn("人生 PB", crown_body)
        self.assertIn("当年 PB", crown_body)
        self.assertIn("aria-label", crown_body)
        self.assertIn("title", crown_body)
        self.assertIn("👑", crown_body)
        self.assertIn("careerTimelinePbCrownHtml(node)", node_body)
        for token in FORBIDDEN_FACT_TOKENS:
            self.assertNotIn(token, crown_body + node_body)

    def test_filter_switch_updates_type_and_reloads_timeline(self):
        body = extract_function_body(self.source, "function setCareerTimelineTypeFilter(type)")
        self.assertIn("type: String(type || 'all')", body)
        self.assertIn("year: current.year", body)
        self.assertIn("loadCareerTimeline(appState.career.timelineFilters)", body)
        filter_body = extract_function_body(self.source, "function renderCareerTimelineFilters(filters)")
        self.assertIn("data-career-timeline-filter", filter_body)
        self.assertIn("careerTimelineYearCapsuleHtml", filter_body)
        self.assertIn("is-active", filter_body)
        self.assertIn("aria-pressed", filter_body)

    def test_timeline_nodes_reuse_activity_detail_link_handler(self):
        body = extract_function_body(self.source, "function careerTimelineNodeHtml(node)")
        self.assertIn("node.detailLink.activityId", body)
        self.assertIn("node.activityId", body)
        self.assertIn('data-activity-id="', body)
        self.assertIn('data-career-source="', body)
        self.assertIn('role="button"', body)
        self.assertIn('tabindex="0"', body)
        self.assertIn('onclick="openCareerActivityDetailFromElement(this)"', body)
        self.assertIn('onkeydown="onCareerActivityDetailKeydown(event, this)"', body)
        self.assertIn("safeHtml", body)

    def test_timeline_render_layer_does_not_compute_facts_or_use_raw_fields(self):
        relevant = "\n".join(
            extract_function_body(self.source, signature)
            for signature in (
                "function normalizeCareerTimeline(payload)",
                "function normalizeCareerTimelineNode(item)",
                "function renderCareerTimeline(viewModel)",
                "function careerTimelineNodeHtml(node)",
                "function careerTimelineNodeMeta(node)",
                "function loadCareerTimeline(filters)",
            )
        )
        for token in FORBIDDEN_FRONTEND_TOKENS:
            self.assertNotIn(token, relevant)
        for token in FORBIDDEN_FACT_TOKENS:
            self.assertNotIn(token, relevant)
        self.assertNotIn("resolve_", relevant)

    def test_switching_to_career_loads_timeline_without_breaking_overview(self):
        body = extract_function_body(self.source, "function switchTab(tabBtn)")
        load_body = extract_function_body(self.source, "async function loadCareerData()")
        self.assertIn("loadCareerData().catch", body)
        self.assertIn("loadCareerOverview().catch", load_body)
        self.assertIn("loadCareerTimeline().catch", load_body)


if __name__ == "__main__":
    unittest.main()
