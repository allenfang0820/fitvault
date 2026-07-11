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


def css_block(source: str, selector: str) -> str:
    start = source.find(selector)
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


class TestCareerTimelineFrontendVisualContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TRACK_HTML_PATH.read_text(encoding="utf-8")

    def test_timeline_dom_has_stable_year_month_node_targets(self):
        panel = extract_between(
            self.source,
            '<div id="panel-career" class="tab-panel">',
            '<!-- ========== 【轨迹分析工具】面板 ========== -->',
        )
        for token in (
            'id="career-timeline-years"',
            'class="career-timeline-status"',
            'class="career-timeline-placeholder"',
        ):
            self.assertIn(token, panel)
        self.assertNotIn('class="career-timeline-candidates"', panel)
        self.assertNotIn("career-candidate", panel)

        renderers = "\n".join(
            extract_function_body(self.source, signature)
            for signature in (
                "function careerTimelineNodeHtml(node)",
                "function careerTimelineMonthHtml(month)",
                "function careerTimelineTrackHtml(month, track)",
                "function careerTimelineYearHtml(year)",
            )
        )
        for token in (
            "career-timeline-year",
            "career-timeline-year-title",
            "career-timeline-month",
            "career-timeline-month-label",
            "career-timeline-month-axis",
            "career-timeline-track",
            "career-timeline-track-lane",
            "career-timeline-node",
        ):
            self.assertIn(token, renderers)
        self.assertNotIn("careerTimelineSeasonSummaryHtml(year)", renderers)

    def test_timeline_nodes_keep_visible_content_to_title_and_date(self):
        type_body = extract_function_body(self.source, "function careerTimelineTypeLabel(type)")
        node_body = extract_function_body(self.source, "function careerTimelineNodeHtml(node)")
        self.assertIn("return '赛事'", type_body)
        self.assertIn("return '里程碑'", type_body)
        self.assertNotIn("return 'PB'", type_body)
        self.assertIn("careerTimelineNodeDateLabel(node)", node_body)
        self.assertIn("careerTimelineNodeAriaLabel(node)", node_body)
        self.assertIn("data-career-timeline-tone", node_body)
        self.assertNotIn("careerTimelineTypeLabel(type)", node_body)
        self.assertNotIn("career-timeline-node-tag", node_body)
        self.assertNotIn("career-timeline-node-desc", node_body)
        self.assertIn("careerTimelinePbCrownHtml(node)", node_body)

    def test_pb_crown_styles_are_accessible_and_distinct(self):
        crown_css = css_block(self.source, ".career-timeline-pb-crown")
        career_css = css_block(self.source, ".career-timeline-pb-crown.career")
        season_css = css_block(self.source, ".career-timeline-pb-crown.season")
        crown_body = extract_function_body(self.source, "function careerTimelinePbCrownHtml(node)")
        self.assertIn("position: absolute", crown_css)
        self.assertIn("font-size", crown_css)
        self.assertIn("top: -10px", crown_css)
        self.assertIn("right: -7px", crown_css)
        self.assertIn("color: #facc15", career_css)
        self.assertIn("color: #e2e8f0", season_css)
        self.assertIn("aria-label", crown_body)
        self.assertIn("title", crown_body)
        self.assertIn("人生 PB", crown_body)
        self.assertIn("当年 PB", crown_body)

    def test_long_text_and_narrow_layout_css_is_stable(self):
        title_css = css_block(self.source, ".career-timeline-node-title")
        meta_css = css_block(self.source, ".career-timeline-node-meta")
        body_css = css_block(self.source, ".career-timeline-node-body")
        month_css = css_block(self.source, ".career-timeline-month")
        track_lane_css = css_block(self.source, ".career-timeline-track-lane")
        node_lane_css = css_block(self.source, ".career-timeline-track-lane .career-timeline-node")
        mobile_css = extract_between(
            self.source,
            "@media (max-width: 980px)",
            "/* V1.0:三个预留 tab",
        )
        self.assertIn("overflow-wrap: anywhere", title_css)
        self.assertIn("overflow-wrap: anywhere", meta_css)
        self.assertIn("-webkit-line-clamp: 1", title_css)
        self.assertIn("display: -webkit-box", meta_css)
        self.assertIn("-webkit-line-clamp: 1", meta_css)
        self.assertIn("min-width: 0", body_css)
        self.assertIn("grid-template-columns: 64px minmax(0, 1fr)", month_css)
        self.assertIn("position: relative", track_lane_css)
        self.assertIn("position: absolute", node_lane_css)
        self.assertIn("transform: none", node_lane_css)
        self.assertIn(".career-timeline-month", mobile_css)
        self.assertIn("grid-template-columns: 1fr", mobile_css)
        self.assertIn(".career-timeline-track-lane .career-timeline-node", mobile_css)
        self.assertIn("position: relative", mobile_css)
        self.assertIn("top: auto !important", mobile_css)
        self.assertIn("left: auto !important", mobile_css)

    def test_year_label_and_month_connector_match_timeline_reference(self):
        year_css = css_block(self.source, ".career-timeline-year-title")
        month_number_css = css_block(self.source, ".career-timeline-month-label strong")
        connector_css = css_block(self.source, ".career-timeline-month-label::after")
        mobile_css = extract_between(
            self.source,
            "@media (max-width: 980px)",
            "/* V1.0:三个预留 tab",
        )

        self.assertIn('font-family: "DIN Next", "DIN NEXT"', year_css)
        self.assertIn("font-size: 1.38rem", year_css)
        self.assertIn("font-size: 1.05rem", month_number_css)
        self.assertIn("linear-gradient(180deg", connector_css)
        self.assertIn("rgba(59, 130, 246, 0) 100%", connector_css)
        self.assertIn("bottom: -10px", connector_css)
        self.assertIn(".career-timeline-month-label::after", mobile_css)
        self.assertIn("display: none", mobile_css)

    def test_timeline_compact_nodes_use_type_tones_without_inner_type_labels(self):
        node_css = css_block(self.source, ".career-timeline-node")
        position_body = extract_function_body(self.source, "function careerTimelineNodePositionStyle(node, month)")
        node_body = extract_function_body(self.source, "function careerTimelineNodeHtml(node)")
        tone_body = extract_function_body(self.source, "function careerTimelineNodeTone(node)")

        self.assertIn("min-height: 32px", node_css)
        self.assertIn("padding: 5px 8px", node_css)
        self.assertIn("box-sizing: border-box", node_css)
        self.assertIn("width: clamp(112px, 18%, 156px)", node_css)
        self.assertIn("display: block", node_css)
        self.assertIn("tone-race", self.source)
        self.assertIn("tone-first", self.source)
        self.assertIn("tone-cumulative", self.source)
        self.assertIn("tone-annual", self.source)
        self.assertIn("tone-achievement", self.source)
        self.assertIn("badge.indexOf('首次')", tone_body)
        self.assertIn("badge.indexOf('累计')", tone_body)
        self.assertIn("badge.indexOf('年度')", tone_body)
        self.assertIn("careerTimelineNodeLeftPercent(node, month)", position_body)
        self.assertIn("lane * CAREER_TIMELINE_LANE_HEIGHT", position_body)
        self.assertIn("careerTimelineNodeAriaLabel(node)", node_body)

    def test_date_points_and_card_left_edges_share_one_anchor(self):
        anchor_body = extract_function_body(self.source, "function careerTimelineDayAnchorPercent(dayValue, daysInMonthValue)")
        left_body = extract_function_body(self.source, "function careerTimelineNodeLeftPercent(node, month)")
        ticks_body = extract_function_body(self.source, "function careerTimelineDayTicksHtml(month)")
        date_ticks_css = css_block(self.source, ".career-timeline-date-ticks")
        lane_css = css_block(self.source, ".career-timeline-track-lane")
        node_lane_css = css_block(self.source, ".career-timeline-track-lane .career-timeline-node")

        self.assertIn("(Math.min(day, daysInMonth) - 1)", anchor_body)
        self.assertIn("careerTimelineDayAnchorPercent", left_body)
        self.assertIn("careerTimelineDayAnchorPercent(day, daysInMonth)", ticks_body)
        self.assertIn("--career-timeline-card-reserve", date_ticks_css)
        self.assertIn("--career-timeline-card-reserve", lane_css)
        self.assertIn("--career-timeline-card-reserve: 184px", self.source)
        self.assertIn("transform: none", node_lane_css)
        self.assertNotIn("translateX(-50%)", node_lane_css)

    def test_timeline_day_axis_lights_event_dates(self):
        month_body = extract_function_body(self.source, "function careerTimelineMonthHtml(month)")
        ticks_body = extract_function_body(self.source, "function careerTimelineDayTicksHtml(month)")
        tick_css = css_block(self.source, ".career-timeline-day-tick")
        active_css = css_block(self.source, ".career-timeline-day-tick.is-active")
        active_dot_css = css_block(self.source, ".career-timeline-day-tick.is-active::after")

        self.assertIn("careerTimelineDayTicksHtml(month)", month_body)
        self.assertIn("day <= daysInMonth", ticks_body)
        self.assertIn("activeDays.has(day)", ticks_body)
        self.assertIn("day % 5 === 0", ticks_body)
        self.assertIn("is-major", ticks_body)
        self.assertIn("data-career-timeline-day", ticks_body)
        self.assertIn("日有事件", ticks_body)
        self.assertIn("position: absolute", tick_css)
        self.assertIn("color: #d1fae5", active_css)
        self.assertIn("background: #4ade80", active_dot_css)
        self.assertIn("box-shadow", active_dot_css)
        mobile_css = extract_between(
            self.source,
            "@media (max-width: 980px)",
            "/* V1.0:三个预留 tab",
        )
        self.assertIn(".career-timeline-day-tick.is-major", mobile_css)
        self.assertIn("color: transparent", mobile_css)

    def test_nearby_timeline_nodes_use_collision_aware_lanes(self):
        layout_body = extract_function_body(self.source, "function careerTimelineLayoutTrackNodes(nodes, month)")
        track_body = extract_function_body(self.source, "function careerTimelineTrackHtml(month, track)")
        lane_css = css_block(self.source, ".career-timeline-track-lane")

        self.assertIn("CAREER_TIMELINE_NODE_MIN_GAP_PERCENT", layout_body)
        self.assertIn("Math.abs(existing - anchor)", layout_body)
        self.assertIn("laneAnchors[lane]", layout_body)
        self.assertNotIn("% CAREER_TIMELINE_TRACK_LANES", layout_body)
        self.assertIn("careerTimelineLayoutTrackNodes(visibleNodes, month)", track_body)
        self.assertIn("--career-timeline-lane-count", track_body)
        self.assertIn("--career-timeline-lane-count", lane_css)

    def test_milestone_tones_share_fill_and_use_distinct_borders(self):
        node_css = css_block(self.source, ".career-timeline-node")
        for selector in (
            ".career-timeline-node.tone-first",
            ".career-timeline-node.tone-cumulative",
            ".career-timeline-node.tone-annual",
            ".career-timeline-node.tone-achievement",
            ".career-timeline-node.tone-milestone",
        ):
            tone_css = css_block(self.source, selector)
            self.assertIn("border-color", tone_css)
            self.assertNotIn("background:", tone_css)
        self.assertIn("background: rgba(15, 23, 42, 0.88)", node_css)

    def test_race_cards_use_neutral_gray_border(self):
        race_css = css_block(self.source, ".career-timeline-node.tone-race")
        self.assertIn("border-color: rgba(148, 163, 184, 0.72)", race_css)
        self.assertIn("rgba(148, 163, 184, 0.14)", race_css)
        for blue in ("56, 189, 248", "59, 130, 246", "34, 211, 238"):
            self.assertNotIn(blue, race_css)

    def test_race_node_shows_result_without_rank_fields(self):
        node_body = extract_function_body(self.source, "function careerTimelineNodeHtml(node)")
        aria_body = extract_function_body(self.source, "function careerTimelineNodeAriaLabel(node)")
        result_css = css_block(self.source, ".career-timeline-node-result")
        self.assertIn("formatCareerTimelineNodeValue(node)", node_body)
        self.assertIn("career-timeline-node-result", node_body)
        self.assertIn("formatCareerTimelineNodeValue(node)", aria_body)
        self.assertIn("font-weight: 900", result_css)
        for token in ("rank", "placement", "名次", "排名"):
            self.assertNotIn(token, node_body.lower())

    def test_filter_active_state_and_accessibility_are_clear(self):
        panel = extract_between(
            self.source,
            '<div id="panel-career" class="tab-panel">',
            '<!-- ========== 【轨迹分析工具】面板 ========== -->',
        )
        self.assertIn('role="group"', panel)
        self.assertIn('aria-label="运动生涯时间轴内容筛选"', panel)
        self.assertIn('aria-label="运动生涯时间轴年份筛选"', panel)
        self.assertIn('aria-pressed="true"', panel)
        self.assertIn('aria-pressed="false"', panel)
        self.assertNotIn('data-career-timeline-filter="pb"', panel)
        active_css = css_block(self.source, ".career-filter-chip:hover,\n        .career-filter-chip.is-active")
        self.assertIn("border-color", active_css)
        self.assertIn("background", active_css)
        filter_body = extract_function_body(self.source, "function renderCareerTimelineFilters(filters)")
        self.assertIn("classList.toggle('is-active'", filter_body)
        self.assertIn("aria-pressed", filter_body)
        self.assertIn("careerTimelineYearCapsuleHtml", filter_body)

    def test_loading_empty_and_error_messages_are_distinct(self):
        render_body = extract_function_body(self.source, "function renderCareerTimeline(viewModel)")
        loading_body = extract_function_body(self.source, "function renderCareerTimelineLoading()")
        error_body = extract_function_body(self.source, "function renderCareerTimelineError(message)")
        placeholder_css = css_block(self.source, ".career-timeline-placeholder")
        self.assertIn("暂无时间轴节点", render_body)
        self.assertIn("正在加载时间轴", loading_body)
        self.assertIn("时间轴暂不可用", error_body)
        self.assertIn("min-height: 180px", placeholder_css)
        self.assertNotIn("career-timeline-candidates", render_body)
        self.assertNotIn("候选事件待确认", render_body)
        self.assertNotIn(".career-timeline-candidates", self.source)
        self.assertNotIn(".career-candidate", self.source)

    def test_timeline_nodes_reuse_activity_detail_handler(self):
        body = extract_function_body(self.source, "function careerTimelineNodeHtml(node)")
        for token in (
            'role="button"',
            'tabindex="0"',
            'data-activity-id="',
            'data-career-source="',
            'onclick="openCareerActivityDetailFromElement(this)"',
            'onkeydown="onCareerActivityDetailKeydown(event, this)"',
        ):
            self.assertIn(token, body)
        self.assertNotIn("window.pywebview.api", body)
        self.assertNotIn("get_activity_detail", body)

    def test_timeline_frontend_keeps_data_boundary(self):
        relevant = "\n".join(
            extract_function_body(self.source, signature)
            for signature in (
                "function normalizeCareerTimeline(payload)",
                "function normalizeCareerTimelineNode(item)",
                "function careerTimelineNodePositionStyle(node, month)",
                "function careerTimelineNodeMeta(node)",
                "function careerTimelineNodeHtml(node)",
                "function careerTimelineMonthHtml(month)",
                "function careerTimelineTrackHtml(month, track)",
                "function renderCareerTimeline(viewModel)",
                "async function loadCareerTimeline(filters)",
            )
        )
        for token in FORBIDDEN_FRONTEND_TOKENS:
            self.assertNotIn(token, relevant)
        for token in FORBIDDEN_FACT_TOKENS:
            self.assertNotIn(token, relevant)
        self.assertNotIn("resolve_", relevant)
        self.assertNotIn("Object.assign", relevant)
        self.assertNotIn("...item", relevant)

    def test_career_panel_does_not_inline_api_calls(self):
        panel = extract_between(
            self.source,
            '<div id="panel-career" class="tab-panel">',
            '<!-- ========== 【轨迹分析工具】面板 ========== -->',
        )
        self.assertNotIn("window.pywebview.api", panel)
        self.assertNotIn("get_career_timeline", panel)
        self.assertNotIn("get_career_overview", panel)


if __name__ == "__main__":
    unittest.main()
