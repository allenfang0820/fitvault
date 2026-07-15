import json
import shutil
import subprocess
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACK_HTML_PATH = PROJECT_ROOT / "track.html"

FORBIDDEN_ARCHIVE_TOKENS = (
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
    "display_metadata",
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


def extract_function_source(source: str, signature: str) -> str:
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
    return source[start:index]


def extract_between(source: str, start_marker: str, end_marker: str) -> str:
    start = source.find(start_marker)
    if start < 0:
        raise AssertionError(f"未找到起始标记: {start_marker}")
    end = source.find(end_marker, start + len(start_marker))
    if end < 0:
        raise AssertionError(f"未找到结束标记: {end_marker}")
    return source[start:end]


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


class TestCareerArchivesFrontendRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TRACK_HTML_PATH.read_text(encoding="utf-8")
        cls.section = extract_between(
            cls.source,
            '<section class="career-section" data-career-section="archives">',
            "</section>",
        )
        cls.relevant_js = "\n".join(
            extract_function_body(cls.source, signature)
            for signature in (
                "function normalizeCareerArchiveRace(item)",
                "function normalizeCareerArchivePb(item)",
                "function normalizeCareerArchiveAchievement(item)",
                "function normalizeCareerArchives(payload)",
                "function careerArchiveItemShell(item, title, meta)",
                "function careerArchiveRaceHtml(item)",
                "function careerRaceCardMedia(item)",
                "function careerRaceMetricsHtml(item)",
                "function careerRaceJudgementHtml(item)",
                "function careerRaceArchiveCardHtml(item)",
                "function careerArchivePbHtml(item)",
                "function careerPbArchiveCardHtml(item)",
                "function careerArchiveAchievementHtml(item)",
                "function careerAchievementArchiveCardHtml(item)",
                "function renderCareerArchiveGroup(name, items, emptyText, renderer)",
                "function getCareerRaceArchiveFilters()",
                "function syncCareerRaceArchiveFilters(filters, summary)",
                "function getCareerPbArchiveFilters()",
                "function syncCareerPbArchiveFilters(filters, summary)",
                "function renderCareerArchives(viewModel)",
                "function renderCareerArchivesLoading()",
                "function renderCareerArchivesError(message)",
                "function onCareerRaceArchiveFilterChange()",
                "function onCareerPbArchiveFilterChange()",
                "async function loadCareerArchives()",
            )
        )

    def test_archives_dom_targets_exist(self):
        self.assertIn('id="career-archives-status-text"', self.section)
        self.assertIn('id="career-race-archive-shell"', self.section)
        self.assertIn('id="career-race-summary"', self.section)
        self.assertIn('id="career-race-list"', self.section)
        self.assertIn('id="career-race-year-filter"', self.section)
        self.assertIn('id="career-race-sport-filter"', self.section)
        self.assertIn('id="career-race-type-filter"', self.section)
        self.assertIn('id="career-race-source-filter"', self.section)
        self.assertIn('data-career-archive-list="races"', self.section)
        self.assertIn('id="career-archives-empty"', self.section)
        for label in ("赛事档案", "全部年份", "全部类型", "用户确认", "设备标记", "规则识别"):
            self.assertIn(label, self.section)

    def test_pb_dom_targets_exist(self):
        pb_section = extract_between(
            self.source,
            '<section class="career-section" data-career-section="pb">',
            "</section>",
        )
        self.assertIn('id="career-pb-status-text"', pb_section)
        self.assertIn('id="career-pb-status-text" aria-live="polite"', pb_section)
        self.assertIn('id="career-pb-archive-shell"', pb_section)
        for token in (
            'id="career-records-v2-shell"',
            'id="career-record-current-list" aria-live="polite"',
            'id="career-record-analysis-panel" aria-live="polite"',
            'id="career-pb-summary" aria-live="polite"',
            'id="career-pb-list"',
            'id="career-pb-detail-panel" aria-live="polite"',
            'id="career-pb-candidate-panel" aria-live="polite"',
            'data-career-archive-list="pbs"',
        ):
            self.assertIn(token, self.source)
        self.assertNotIn('id="career-record-dashboard-stats"', self.source)
        for label in ("记录中心", "当前纪录", "演进", "候选"):
            self.assertIn(label, pb_section)

    def test_dedicated_achievement_archive_page_is_removed(self):
        self.assertNotIn('<section class="career-section" data-career-section="achievements">', self.source)
        self.assertNotIn('id="career-achievement-archive-shell"', self.source)
        self.assertNotIn('data-career-archive-list="achievements"', self.source)
        self.assertNotIn('function onCareerAchievementArchiveFilterChange()', self.source)

    def test_archives_use_single_column_right_rail_layout(self):
        bucket_list_css = css_block(self.source, ".career-bucket-list")
        bucket_css = css_block(self.source, ".career-bucket")

        self.assertIn("grid-template-columns: 1fr", bucket_list_css)
        self.assertIn("min-height: 0", bucket_css)
        self.assertNotIn("repeat(3", bucket_list_css)

    def test_switching_to_career_loads_archives(self):
        body = extract_function_body(self.source, "function switchTab(tabBtn)")
        load_body = extract_function_body(self.source, "async function loadCareerData()")
        self.assertIn("loadCareerData().catch", body)
        self.assertIn("loadCareerArchives().catch", load_body)
        self.assertIn("loadCareerOverview().catch", load_body)
        self.assertIn("loadCareerTimeline().catch", load_body)
        self.assertIn("loadCareerMemory().catch", load_body)

    def test_loader_calls_existing_readonly_apis_only(self):
        body = extract_function_body(self.source, "async function loadCareerArchives()")
        self.assertIn("api.get_career_races(raceFilters)", body)
        self.assertIn("api.get_career_pb(pbFilters)", body)
        self.assertIn("getCareerRaceArchiveFilters()", body)
        self.assertIn("getCareerPbArchiveFilters()", body)
        self.assertNotIn("api.get_career_achievements", body)
        self.assertNotIn("getCareerAchievementArchiveFilters()", body)
        self.assertIn("for (let attempt = 0; attempt < 2; attempt += 1)", body)
        self.assertIn("await waitCareerApiRetry(340)", body)
        self.assertNotIn("resolve_", body)
        self.assertNotIn("save_", body)
        self.assertNotIn("generate_career_insight", body)
        self.assertNotIn("call_llm", body)

    def test_normalizers_use_whitelisted_fields_without_metadata_passthrough(self):
        expected_tokens = (
            "activity_id",
            "event_type",
            "event_type_label",
            "event_date",
            "display_date",
            "location",
            "source_label",
            "confidence_label",
            "is_user_confirmed",
            "is_system_detected",
            "needs_user_judgement",
            "confidence_level",
            "pb_type",
            "pb_type_label",
            "pb_title",
            "value_unit",
            "value_display",
            "improvement_sec",
            "improvement_display",
            "achievement_type",
            "achievement_type_label",
            "achievement_title",
            "category",
            "category_label",
            "score_label",
            "description",
            "detail_link",
        )
        for token in expected_tokens:
            self.assertIn(token, self.relevant_js)
        self.assertNotIn("Object.assign", self.relevant_js)
        self.assertNotIn("...item", self.relevant_js)
        for token in FORBIDDEN_ARCHIVE_TOKENS:
            self.assertNotIn(token, self.relevant_js)

    def test_renderers_include_formal_race_archive_and_bucket_states(self):
        self.assertIn("renderCareerArchiveGroup('races'", self.relevant_js)
        self.assertIn("renderCareerArchiveGroup('pbs'", self.relevant_js)
        self.assertNotIn("renderCareerArchiveGroup('achievements'", self.relevant_js)
        self.assertIn("name === 'races' || name === 'pbs' ? source : source.slice(0, 5)", self.relevant_js)
        self.assertIn("careerRaceArchiveCardHtml", self.relevant_js)
        self.assertIn("careerPbArchiveCardHtml", self.relevant_js)
        self.assertNotIn("careerAchievementArchiveCardHtml", self.relevant_js)
        self.assertIn("career-race-card", self.source)
        self.assertIn("repeat(auto-fill, minmax(270px, 1fr))", self.source)
        self.assertIn("aspect-ratio: 4 / 5", self.source)
        self.assertIn("flex: 0 0 48%", self.source)
        self.assertIn("transform: scale(1.065)", self.source)
        self.assertIn("career-race-cover", self.source)
        self.assertIn("career-race-cover-art", self.source)
        self.assertIn("career-race-judgement", self.source)
        self.assertIn("career-race-judge-btn", self.source)
        self.assertIn("top: 50%", self.source)
        self.assertIn('data-race-cover-mode="', self.relevant_js)
        self.assertIn("normalizeCareerSafeImagePreview(media.imageRef || media.image_ref || '')", self.relevant_js)
        self.assertIn("cardMetrics", self.relevant_js)
        self.assertIn("linear-gradient(180deg, rgba(2, 6, 23, 0.08)", self.source)
        self.assertIn("career-race-badge", self.source)
        self.assertIn("career-pb-card", self.source)
        self.assertIn("career-pb-badge", self.source)
        self.assertIn("career-achievement-card", self.source)
        self.assertIn("career-achievement-badge", self.source)
        self.assertIn("暂无赛事", self.relevant_js)
        self.assertIn("暂无当前纪录", self.relevant_js)
        self.assertIn("待确认", self.relevant_js)
        self.assertIn("记录中心已接入", self.relevant_js)
        self.assertIn("正在加载赛事档案", self.relevant_js)
        self.assertIn("赛事档案暂不可用", self.relevant_js)
        self.assertIn("当前筛选下共", self.relevant_js)

    def test_archive_items_reuse_activity_detail_handler(self):
        body = extract_function_body(self.source, "function careerRaceArchiveCardHtml(item)")
        for token in (
            'role="button"',
            'tabindex="0"',
            'data-activity-id="',
            'data-career-source="',
            'onclick="openCareerActivityDetailFromElement(this)"',
            'onkeydown="onCareerActivityDetailKeydown(event, this)"',
        ):
            self.assertIn(token, body)
        self.assertIn("careerRaceMetricsHtml(item)", body)
        self.assertIn("careerRaceJudgementHtml(item)", body)
        self.assertIn("data-career-race-art-text", body)
        metrics_body = extract_function_body(self.source, "function careerRaceMetricsHtml(item)")
        self.assertIn("Array.isArray(item.cardMetrics)", metrics_body)
        self.assertNotIn("performanceSummary", metrics_body)
        self.assertNotIn("duration_text", metrics_body)
        self.assertNotIn("pace_text", metrics_body)
        self.assertNotIn("Activity Detail", body)
        self.assertNotIn("分段数据", body)
        self.assertNotIn("海拔曲线", body)
        self.assertNotIn("window.pywebview.api", body)

    def test_race_cards_offer_inline_judgement_and_manual_override(self):
        normalize_body = extract_function_body(self.source, "function normalizeCareerArchiveRace(item)")
        judgement_body = extract_function_body(self.source, "function careerRaceJudgementHtml(item)")
        handler_body = extract_function_body(self.source, "async function judgeCareerRaceFromCard(event, activityId, isRace)")

        self.assertIn("needsUserJudgement", normalize_body)
        self.assertIn("isSystemDetected", normalize_body)
        self.assertIn("item.needsUserJudgement", judgement_body)
        self.assertIn("item.isUserConfirmed", judgement_body)
        self.assertIn("取消赛事标记", judgement_body)
        self.assertIn("是赛事", judgement_body)
        self.assertIn("不是赛事", judgement_body)
        self.assertIn("judgeCareerRaceFromCard(event", judgement_body)
        self.assertIn("event.stopPropagation()", handler_body)
        self.assertIn("api.set_activity_race_flag(id, nextIsRace)", handler_body)
        self.assertIn("loadCareerArchives()", handler_body)
        self.assertIn("sportHubState.needsRefresh = true", handler_body)
        self.assertIn("appState.career.needsRefresh = true", handler_body)
        self.assertNotIn("showModal", judgement_body + handler_body)
        self.assertNotIn("confirm(", judgement_body + handler_body)

    def test_race_judgement_renderer_outputs_actions_for_each_race_state(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is required for JS semantic execution")

        function_source = extract_function_source(self.source, "function careerRaceJudgementHtml(item)")
        script = "\n".join(
            (
                "function safeHtml(value) { return String(value == null ? '' : value); }",
                function_source,
                "const output = {",
                "  missing: careerRaceJudgementHtml({ activityId: '' }),",
                "  resolver: careerRaceJudgementHtml({ activityId: '12', sourceLabel: '规则识别', needsUserJudgement: true, isUserConfirmed: false }),",
                "  user: careerRaceJudgementHtml({ activityId: '13', sourceLabel: '用户确认', needsUserJudgement: false, isUserConfirmed: true }),",
                "  fit: careerRaceJudgementHtml({ activityId: '14', sourceLabel: 'FIT 赛事标记', needsUserJudgement: false, isUserConfirmed: false })",
                "};",
                "process.stdout.write(JSON.stringify(output));",
            )
        )
        output = json.loads(subprocess.check_output([node, "-e", script], text=True))

        self.assertEqual(output["missing"], "")
        self.assertIn("是赛事", output["resolver"])
        self.assertIn("不是赛事", output["resolver"])
        self.assertIn("judgeCareerRaceFromCard(event, 12, true)", output["resolver"])
        self.assertIn("judgeCareerRaceFromCard(event, 12, false)", output["resolver"])
        self.assertIn("已由你确认这是赛事", output["user"])
        self.assertIn("取消赛事标记", output["user"])
        self.assertNotIn("judgeCareerRaceFromCard(event, 13, true)", output["user"])
        self.assertIn("judgeCareerRaceFromCard(event, 13, false)", output["user"])
        self.assertIn("FIT 赛事标记，可手动调整", output["fit"])
        self.assertIn("取消赛事标记", output["fit"])
        self.assertIn("judgeCareerRaceFromCard(event, 14, false)", output["fit"])

    def test_race_filters_reload_backend_view_model(self):
        body = extract_function_body(self.source, "function onCareerRaceArchiveFilterChange()")
        self.assertIn("getCareerRaceArchiveFilters()", body)
        self.assertIn("loadCareerArchives()", body)
        sync_body = extract_function_body(self.source, "function syncCareerRaceArchiveFilters(filters, summary)")
        self.assertIn("career-race-year-filter", sync_body)
        self.assertIn("raceByYear", sync_body)

    def test_pb_filters_reload_backend_view_model(self):
        body = extract_function_body(self.source, "function onCareerPbArchiveFilterChange()")
        self.assertIn("getCareerPbArchiveFilters()", body)
        self.assertIn("loadCareerArchives()", body)
        sync_body = extract_function_body(self.source, "function syncCareerPbArchiveFilters(filters, summary)")
        self.assertIn("career-pb-year-filter", sync_body)
        self.assertIn("pbByYear", sync_body)
        card_body = extract_function_body(self.source, "function careerPbArchiveCardHtml(item)")
        for token in (
            'role="button"',
            'data-activity-id="',
            'data-record-id="',
            'data-pb-type="',
            'openCareerRecordDetailFromElement(event, this)',
            'aria-label="查看纪录详情与演进"',
            'title="查看纪录详情与演进"',
            'career-pb-value',
            'career-pb-badge',
        ):
            self.assertIn(token, card_body)

    def test_pb_page_is_labeled_as_records_center(self):
        self.assertIn("pb: '记录中心'", self.source)
        self.assertIn("data-career-page-target=\"pb\" aria-pressed=\"false\" onclick=\"switchCareerPage('pb')\">记录</button>", self.source)

    def test_pb_detail_and_history_view_calls_backend_contract(self):
        for function_name in (
            "function renderCareerPbDetailPanel(detail, history)",
            "async function loadCareerPbDetail(recordId, pbType)",
            "function openCareerRecordDetailFromElement(event, el)",
        ):
            self.assertIn(function_name, self.source)
        load_body = extract_function_body(self.source, "async function loadCareerPbDetail(recordId, pbType)")
        self.assertIn("api.get_career_pb_detail(recordId)", load_body)
        self.assertIn("api.get_career_pb_history(pbType || 'all', {})", load_body)
        render_body = extract_function_body(self.source, "function renderCareerPbDetailPanel(detail, history)")
        self.assertIn("career-pb-history-list", render_body)
        self.assertIn("career-pb-history-node", render_body)
        self.assertIn("record.valueDisplay", render_body)

    def test_pb_candidate_view_calls_backend_contract(self):
        for function_name in (
            "function normalizeCareerRecordCandidate(item)",
            "function renderCareerPbCandidates(candidates)",
            "async function decideCareerPbCandidateFromElement(event, el)",
        ):
            self.assertIn(function_name, self.source)
        load_body = extract_function_body(self.source, "async function loadCareerArchives()")
        self.assertIn("api.get_career_event_candidates({ candidate_type: 'pb_record', status: 'candidate' })", load_body)
        self.assertIn("pbCandidates: archiveData[2] || {}", load_body)
        render_body = extract_function_body(self.source, "function renderCareerPbCandidates(candidates)")
        self.assertIn("data-career-record-candidate-id", render_body)
        self.assertIn("data-decision=\"confirm\"", render_body)
        self.assertIn("data-decision=\"reject\"", render_body)
        self.assertIn("aria-label=\"确认候选纪录\"", render_body)
        self.assertIn("aria-label=\"拒绝候选纪录\"", render_body)
        decide_body = extract_function_body(self.source, "async function decideCareerPbCandidateFromElement(event, el)")
        self.assertIn("el.disabled = true", decide_body)
        self.assertIn("确认中...", decide_body)
        self.assertIn("el.disabled = false", decide_body)
        self.assertIn("api.decide_career_pb_candidate({ candidate_id: candidateId, decision: decision })", decide_body)
        self.assertIn("await loadCareerArchives()", decide_body)

    def test_records_center_responsive_and_accessible_states_are_defined(self):
        self.assertIn(".career-pb-detail-action:disabled", self.source)
        self.assertIn(".career-pb-detail-panel", self.source)
        self.assertIn("@media (max-width: 980px)", self.source)
        self.assertIn(".career-pb-list", self.source)

    def test_achievement_archive_card_helper_has_no_dedicated_page_entry(self):
        self.assertNotIn("function onCareerAchievementArchiveFilterChange()", self.source)
        self.assertNotIn("function getCareerAchievementArchiveFilters()", self.source)
        self.assertNotIn("function syncCareerAchievementArchiveFilters(filters, summary)", self.source)
        card_body = extract_function_body(self.source, "function careerAchievementArchiveCardHtml(item)")
        for token in (
            'role="button"',
            'data-activity-id="',
            'career-achievement-score',
            'career-achievement-badge',
        ):
            self.assertIn(token, card_body)


if __name__ == "__main__":
    unittest.main()
