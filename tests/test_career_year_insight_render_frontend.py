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


class TestCareerYearInsightRenderFrontend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TRACK_HTML_PATH.read_text(encoding="utf-8")

    def test_year_renderer_outputs_title_meta_data_through_partial_and_facts(self):
        body = extract_function_body(self.source, "function renderCareerYearInsight(viewModel)")
        facts_body = extract_function_body(self.source, "function careerYearFactsHtml(facts)")
        generated_at_body = extract_function_body(self.source, "function formatCareerGeneratedAt(value)")

        self.assertIn("年度总结", body)
        self.assertIn("vm.generated_at", body)
        self.assertIn("formatCareerGeneratedAt(vm.generated_at)", body)
        self.assertIn("toLocaleString", generated_at_body)
        self.assertIn("vm.data_through", body)
        self.assertIn("is_partial_year", body)
        self.assertIn("careerYearFactsHtml(facts)", body)
        for token in (
            "activity_count",
            "total_distance_km",
            "total_duration_seconds",
            "race_count",
            "pb_count",
            "achievement_count",
            "covered_city_count",
        ):
            self.assertIn(token, facts_body)

    def test_v2_year_report_renders_as_continuous_article_with_backend_evidence(self):
        body = extract_function_body(self.source, "function careerYearReportSectionsHtml(vm)")
        article_body = extract_function_body(self.source, "function careerYearV2ArticleHtml(report)")

        self.assertIn("const hasReport", body)
        self.assertIn("if (!hasReport) return careerYearLegacyReportHtml({}, fallback)", body)
        self.assertIn("acs.year.report.v2", body)
        self.assertIn("acs.year.report.v3", body)
        for token in ("content.title", "content.subtitle", "content.fact_leads", "content.fact_lead", "content.opening", "content.body_sections", "content.closing", "content.letter_to_next_year"):
            self.assertIn(token, article_body)
        self.assertIn("career-year-article", article_body)
        self.assertIn("safeHtml(paragraph)", article_body)
        self.assertNotIn("career-year-evidence-list", article_body)
        self.assertNotIn("openCareerActivityDetailFromElement", article_body)
        self.assertNotIn("onCareerActivityDetailKeydown", article_body)

    def test_v1_report_keeps_compatibility_view(self):
        body = extract_function_body(self.source, "function careerYearLegacyReportHtml(report, fallback)")
        list_body = extract_function_body(self.source, "function careerInsightListHtml(items, className, title)")
        item_body = extract_function_body(self.source, "function careerInsightListItemText(item)")
        expected_order = ["主线", "关键时刻", "运动节奏", "上一年比较", "下一年方向"]
        section_body = body[body.index("const sections"):]
        positions = [section_body.index(label) for label in expected_order]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("report.headline", body)
        self.assertIn("report.title", body)
        self.assertIn("report.mainline", body)
        self.assertIn("fallback.key_events", body)
        self.assertIn("career-year-section-list", list_body)
        self.assertIn("item.title", item_body)
        self.assertIn("item.description", item_body)
        self.assertIn("item.date", item_body)

    def test_all_year_report_states_have_independent_copy_and_actions(self):
        message_body = extract_function_body(self.source, "function careerYearStateMessage(state)")
        action_body = extract_function_body(self.source, "function careerYearActionHtml(state, vm)")

        for state in ("no_data", "not_generated", "ready", "stale", "generating", "failed", "ai_unavailable"):
            self.assertIn(state, message_body)
        self.assertIn("生成年度总结", action_body)
        self.assertIn("年度事实有更新，刷新年度总结", action_body)
        self.assertIn("重试年度总结", action_body)
        self.assertIn("升级年度故事", action_body)
        self.assertIn("format_upgrade_available", action_body)
        self.assertIn("disabled", action_body)
        self.assertIn("key === 'no_data'", action_body)
        self.assertIn("key === 'ready'", action_body)
        self.assertIn("key === 'ai_unavailable'", action_body)

    def test_loading_state_names_target_year(self):
        loading_body = extract_function_body(self.source, "function renderCareerYearInsightLoading(year)")

        self.assertIn("yearLabel", loading_body)
        self.assertIn("String(year) + ' 年度'", loading_body)
        self.assertIn("'正在读取 ' + yearLabel + '总结数据'", loading_body)
        self.assertIn("String(year) + ' 年度总结加载中'", loading_body)
        self.assertIn("const cardEl = document.getElementById('career-insight-card')", loading_body)
        self.assertIn("cardEl.innerHTML", loading_body)
        self.assertIn("career-year-skeleton", loading_body)
        self.assertIn("emptyEl.style.display = 'none'", loading_body)

    def test_error_state_replaces_loading_card_for_selected_year(self):
        error_body = extract_function_body(self.source, "function renderCareerYearInsightError(message)")

        self.assertIn("const cardEl = document.getElementById('career-insight-card')", error_body)
        self.assertIn("yearInsightSelectedYear", error_body)
        self.assertIn("const currentYear", error_body)
        self.assertIn("currentYear === selectedYear", error_body)
        self.assertIn("cardEl.innerHTML", error_body)
        self.assertIn("failed", error_body)
        self.assertIn("年度总结暂不可用", error_body)

    def test_not_generated_and_stale_states_keep_actions(self):
        action_body = extract_function_body(self.source, "function careerYearActionHtml(state, vm)")
        message_body = extract_function_body(self.source, "function careerYearStateMessage(state)")

        self.assertIn("年度事实已准备好，AI 年度总结尚未生成。", message_body)
        self.assertIn("有新的运动数据，当前保留旧年度报告。", message_body)
        self.assertIn("key === 'stale' ? '年度事实有更新，刷新年度总结'", action_body)
        self.assertIn("'生成年度总结'", action_body)
        self.assertNotIn("key === 'not_generated'", action_body[action_body.find("if (key === 'no_data'"):action_body.find("const label")])

    def test_year_render_keeps_fallback_non_ai_and_binds_generation_action_only(self):
        render_body = extract_function_body(self.source, "function renderCareerYearInsight(viewModel)")
        action_body = extract_function_body(self.source, "function careerYearActionHtml(state, vm)")

        self.assertIn("本地年度事实摘要", render_body)
        self.assertIn("不调用 AI", render_body)
        self.assertIn("try {", render_body)
        self.assertIn("renderCareerYearInsight card failed", render_body)
        self.assertIn("年度总结渲染失败，请稍后重试。", render_body)
        self.assertIn("data-career-year-generate-action", action_body)
        self.assertIn("generateCareerYearInsight()", action_body)
        self.assertNotIn("generate_career_year_insight", render_body + action_body)
        self.assertNotIn("generate_career_insight", render_body + action_body)
        self.assertNotIn("call_llm", render_body + action_body)

    def test_generating_state_has_story_progress_skeleton_and_reduced_motion(self):
        html_body = extract_function_body(self.source, "function careerYearGeneratingHtml(vm)")
        progress_body = extract_function_body(self.source, "function startCareerYearGeneratingProgress()")
        generating_body = extract_function_body(self.source, "function renderCareerYearInsightGenerating(year, tonePreset)")

        self.assertIn("正在整理你的", html_body)
        for step in ("正在读取年度活动数据", "正在整理比赛和 PB", "正在梳理这一年的运动节奏", "正在生成年度报告", "正在校验证据来源"):
            self.assertIn(step, html_body + progress_body)
        self.assertIn("career-year-skeleton", html_body)
        self.assertIn("role=\"status\"", html_body)
        self.assertIn("startCareerYearGeneratingProgress()", generating_body)
        self.assertIn("@media (prefers-reduced-motion: reduce)", self.source)

    def test_year_selector_renders_update_badges_from_backend_map(self):
        body = extract_function_body(self.source, "function renderCareerYearSelector(viewModel)")
        merge_body = extract_function_body(self.source, "function mergeCareerYearUpdateBadges(viewModel)")

        self.assertIn("year_update_badges", body)
        self.assertIn("mergeCareerYearUpdateBadges(vm)", body)
        self.assertIn("career-year-new-badge", body)
        self.assertIn("has-new", body)
        self.assertIn("年度报告可更新", body)
        self.assertIn("yearInsightUpdateBadgeMap", merge_body)
        self.assertIn("year_map", merge_body)
        self.assertIn("updateBadges.years", merge_body)
        self.assertIn("delete appState.career.yearInsightUpdateBadgeMap[String(responseYear)]", merge_body)


if __name__ == "__main__":
    unittest.main()
