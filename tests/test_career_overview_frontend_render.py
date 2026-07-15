import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACK_HTML_PATH = PROJECT_ROOT / "track.html"

FORBIDDEN_RENDER_TOKENS = (
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


class TestCareerOverviewFrontendRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TRACK_HTML_PATH.read_text(encoding="utf-8")

    def test_summary_metric_dom_targets_exist(self):
        career_panel = extract_between(
            self.source,
            '<div id="panel-career" class="tab-panel">',
            '<!-- ========== 【轨迹分析工具】面板 ========== -->',
        )
        for field in (
            "runningDistanceKm",
            "cyclingDistanceKm",
            "walkingHikingDistanceKm",
            "swimmingDistanceKm",
            "strengthTotalWeightKg",
            "maxAltitudeM",
            "locationFootprint",
            "activityCount",
            "totalDistanceKm",
            "totalDuration",
            "raceCount",
            "longestActivityDistanceKm",
            "maxElevationGainM",
            "activeYearCount",
        ):
            self.assertIn(f'data-career-overview-field="{field}"', career_panel)
        self.assertNotIn('data-career-overview-field="bestPb"', career_panel)

    def test_summary_metric_cards_have_semantic_icons_and_color_tones(self):
        career_panel = extract_between(
            self.source,
            '<div id="panel-career" class="tab-panel">',
            '<!-- ========== 【轨迹分析工具】面板 ========== -->',
        )
        metric_names = (
            "running",
            "cycling",
            "walking",
            "swimming",
            "strength",
            "altitude",
            "location",
            "activities",
            "duration",
            "races",
            "longest",
            "elevation",
            "years",
            "distance",
        )
        for metric_name in metric_names:
            self.assertIn(f'data-career-metric="{metric_name}"', career_panel)
            self.assertIn(f'href="#career-icon-{metric_name}"', career_panel)

        self.assertEqual(career_panel.count('class="career-metric-icon"'), len(metric_names))
        self.assertIn(".career-metric-placeholder .label {", self.source)
        self.assertIn("color: var(--career-metric-accent)", self.source)
        self.assertIn(".career-metric-placeholder .value {", self.source)
        self.assertIn("color: #f1f5f9", self.source)

    def test_overview_season_cards_use_din_year_and_typed_pills(self):
        count_body = extract_function_body(self.source, "function careerSeasonCountText(value, unit)")
        pill_body = extract_function_body(self.source, "function careerSeasonPillHtml(type, label, value)")
        card_body = extract_function_body(self.source, "function careerSeasonCardHtml(season)")
        render_body = extract_function_body(self.source, "function renderCareerSeasons(viewModel)")
        card_css = extract_between(self.source, ".career-season-card {", ".career-season-head {")

        self.assertIn("Math.round(count)", count_body)
        self.assertIn('class="career-season-pill', pill_body)
        self.assertIn('data-career-season-pill', pill_body)
        self.assertIn("parseFloat", pill_body)
        self.assertIn("is-zero", pill_body)
        self.assertNotIn("const yearSuffix", card_body)
        self.assertIn('class="career-season-year-number"', card_body)
        self.assertNotIn('class="career-season-year-suffix"', card_body)
        self.assertIn("seasonSummary", card_body)
        self.assertIn("formatCareerDistanceKm(season && season.totalDistanceKm)", card_body)
        self.assertIn("careerSeasonPillHtml('activities', '活动'", card_body)
        self.assertIn("careerSeasonPillHtml('distance', '里程'", card_body)
        self.assertIn("careerSeasonPillHtml('races', '赛事'", card_body)
        self.assertIn("careerSeasonPillHtml('pbs', 'PB'", card_body)
        self.assertIn("careerSeasonPillHtml('achievements', '成就'", card_body)
        self.assertNotIn("careerSeasonPillHtml('memories', '记忆'", card_body)
        self.assertIn("careerSeasonPillHtml('cities', '城市'", card_body)
        self.assertIn('class="career-season-pills"', card_body)
        self.assertNotIn("highlights", card_body)
        self.assertNotIn('class="career-season-icon"', card_body)
        self.assertNotIn("seasonTitle", card_body)
        self.assertNotIn("seasonStage", card_body)
        self.assertNotIn("career-season-stage", card_body)
        self.assertNotIn("等待年度高光", card_body)
        self.assertIn("seasons.map(careerSeasonCardHtml)", render_body)
        self.assertNotIn("seasons.slice(0, 3)", render_body)
        self.assertNotIn(".career-season-stage {", self.source)
        self.assertIn("background: rgba(2, 6, 23, 0.28)", card_css)
        self.assertNotIn("linear-gradient", card_css)
        self.assertIn("transition: transform 160ms ease", card_css)
        self.assertIn("cursor: pointer", card_css)
        self.assertIn(".career-season-card:hover", card_css)
        self.assertIn(".career-season-card:focus-visible", self.source)
        self.assertIn("transform: translateY(-3px)", card_css)
        self.assertIn("content: attr(data-career-season-hint)", card_css)
        self.assertIn('<button type="button" class="career-season-card"', card_body)
        self.assertIn('aria-label="查看 ', card_body)
        self.assertIn("查看年度总结", card_body)
        self.assertIn("openCareerYearInsight", card_body)
        self.assertNotIn("点击我试试", card_body)
        self.assertNotIn(".career-season-card:nth-child", self.source)
        self.assertNotIn(".career-season-icon", self.source)
        self.assertIn(".career-season-year-number {", self.source)
        self.assertIn('font-family: "DIN Next", "DIN NEXT"', self.source)
        self.assertIn("font-size: 2.2rem", self.source)
        self.assertIn("color: #f8fafc", self.source)
        self.assertIn("color: #a7b3c6", self.source)
        self.assertIn(".career-season-pill[data-career-season-pill=\"activities\"]", self.source)
        self.assertIn(".career-season-pill[data-career-season-pill=\"distance\"]", self.source)
        self.assertIn(".career-season-pill[data-career-season-pill=\"races\"]", self.source)
        self.assertIn(".career-season-pill[data-career-season-pill=\"pbs\"]", self.source)
        self.assertIn(".career-season-pill[data-career-season-pill=\"achievements\"]", self.source)
        pill_css = extract_between(self.source, ".career-season-pill {", ".career-season-pill-label {")
        label_css = extract_between(self.source, ".career-season-pill-label {", ".career-season-pill-value {")
        value_css = extract_between(self.source, ".career-season-pill-value {", ".career-season-pill.is-zero {")
        race_css = extract_between(
            self.source,
            '.career-season-pill[data-career-season-pill="races"] {',
            '.career-season-pill[data-career-season-pill="pbs"] {',
        )
        pb_css = extract_between(
            self.source,
            '.career-season-pill[data-career-season-pill="pbs"] {',
            '.career-season-pill[data-career-season-pill="achievements"] {',
        )
        self.assertIn("background: rgba(15, 23, 42, 0.82)", pill_css)
        self.assertIn("border: 1px solid var(--career-season-pill-border)", pill_css)
        self.assertNotIn("rgba(var(--career-season-pill-rgb)", pill_css)
        self.assertIn("color: #94a3b8", label_css)
        self.assertIn("color: #e2e8f0", value_css)
        self.assertIn("148, 163, 184", race_css)
        self.assertIn("203, 213, 225", pb_css)
        self.assertNotIn("background:", race_css + pb_css)
        self.assertNotIn(".career-season-highlight:not(:first-child)::before", self.source)

    def test_memory_banner_replaces_three_question_cards(self):
        career_panel = extract_between(
            self.source,
            '<div id="panel-career" class="tab-panel">',
            '<!-- ========== 【轨迹分析工具】面板 ========== -->',
        )
        self.assertIn('id="career-overview-hero-banner"', career_panel)
        self.assertIn('data-career-hero-mode="empty"', career_panel)
        self.assertIn('id="career-banner-photo-img"', career_panel)
        self.assertIn('id="career-banner-photo-img-alt"', career_panel)
        self.assertIn('class="career-banner-art"', career_panel)
        self.assertIn('data-career-hero-field="title"', career_panel)
        self.assertIn('data-career-hero-field="distance"', career_panel)
        self.assertIn('id="career-banner-badges"', career_panel)
        self.assertNotIn('id="career-banner-photo-btn"', career_panel)
        self.assertNotIn('id="career-banner-photo-status"', career_panel)
        self.assertNotIn('onclick="pickCareerRacePhoto(event)"', career_panel)
        self.assertNotIn('设置照片', career_panel)
        for label in ("我是谁", "我走了多久", "我经历过什么"):
            self.assertNotIn(label, career_panel)

    def test_render_career_overview_renders_summary_and_spotlight(self):
        body = extract_function_body(self.source, "function renderCareerOverview(viewModel)")
        for field in (
            "runningDistanceKm",
            "cyclingDistanceKm",
            "walkingHikingDistanceKm",
            "swimmingDistanceKm",
            "strengthTotalWeightKg",
            "maxAltitudeM",
            "locationFootprint",
            "activityCount",
            "totalDistanceKm",
            "raceCount",
            "longestActivityDistanceKm",
            "maxElevationGainM",
            "activeYearCount",
        ):
            self.assertIn(field, body)
        self.assertIn("renderCareerHeroBanner(vm.heroBanner)", body)
        self.assertIn("career-overview-empty", body)
        self.assertIn("dataReady", body)

    def test_banner_renderers_use_safe_html_and_data_hooks(self):
        bodies = "\n".join(
            extract_function_body(self.source, signature)
            for signature in (
                "function normalizeCareerHeroBanner(hero)",
                "function renderCareerHeroBanner(hero)",
            )
        )
        self.assertIn("safeHtml", bodies)
        self.assertIn("data-activity-id", bodies)
        self.assertIn("data-career-source", bodies)
        self.assertIn("imageRef", bodies)
        self.assertIn("slides", bodies)
        self.assertIn("resolveCareerHeroActiveSlide(vm)", bodies)
        self.assertIn("metallic_gradient", bodies)
        self.assertNotIn("career-banner-photo-btn", bodies)
        self.assertNotIn("racePhotoError", bodies)

    def test_banner_carousel_uses_backend_safe_slides(self):
        normalize_body = extract_function_body(self.source, "function normalizeCareerHeroBanner(hero)")
        render_body = extract_function_body(self.source, "function renderCareerHeroBanner(hero)")
        sync_body = extract_function_body(self.source, "function syncCareerHeroCarousel(slides)")
        resolve_body = extract_function_body(self.source, "function resolveCareerHeroActiveSlide(vm)")
        self.assertIn("raw.slides", normalize_body)
        self.assertIn("media.image_ref || media.imageRef", normalize_body)
        self.assertIn("raw.activity_id == null ? raw.activityId", normalize_body)
        self.assertIn("raw.detail_link || raw.detailLink", normalize_body)
        self.assertIn("slice(0, 5)", normalize_body)
        self.assertIn("setInterval", sync_body)
        self.assertIn("heroCarouselIndex", sync_body + resolve_body)
        self.assertIn("activeHero.media.imageRef", render_body)
        self.assertIn("setCareerHeroPhoto(activeHero.media.imageRef", render_body)
        self.assertIn("resetCareerHeroPhotoLayers()", render_body)
        self.assertIn("activeHero.detailLink.activityId", render_body)

    def test_banner_carousel_crossfades_photo_layers(self):
        layers_body = extract_function_body(self.source, "function getCareerHeroPhotoLayers()")
        photo_body = extract_function_body(self.source, "function setCareerHeroPhoto(imageRef, title)")
        reset_body = extract_function_body(self.source, "function resetCareerHeroPhotoLayers()")
        self.assertIn("career-banner-photo-img", layers_body)
        self.assertIn("career-banner-photo-img-alt", layers_body)
        self.assertIn("heroPhotoLayerIndex", photo_body)
        self.assertIn("requestAnimationFrame", photo_body)
        self.assertIn("classList.toggle('is-active'", photo_body)
        self.assertIn("aria-hidden", photo_body)
        self.assertIn("removeAttribute('src')", reset_body)

    def test_identity_renderers_use_backend_fields_without_fact_math(self):
        normalize_body = extract_function_body(self.source, "function normalizeCareerIdentity(identity)")
        render_body = extract_function_body(self.source, "function renderCareerIdentity(identity)")
        tag_body = extract_function_body(self.source, "function renderCareerIdentityTags(tags)")
        self.assertIn("primarySport", normalize_body)
        self.assertIn("identityTitle", normalize_body)
        self.assertIn("questionAnswers", normalize_body)
        self.assertIn("setCareerIdentityField('identityTitle'", render_body)
        self.assertIn("setCareerIdentityField('identitySummary'", render_body)
        self.assertIn("safeHtml(tag)", tag_body)
        for token in FORBIDDEN_FACT_TOKENS:
            self.assertNotIn(token, normalize_body + render_body + tag_body)

    def test_render_layer_does_not_reference_forbidden_raw_fields(self):
        relevant = "\n".join(
            extract_function_body(self.source, signature)
            for signature in (
                "function renderCareerOverview(viewModel)",
                "function normalizeCareerHeroBanner(hero)",
                "function renderCareerHeroBanner(hero)",
                "function normalizeCareerIdentity(identity)",
                "function renderCareerIdentity(identity)",
                "function renderCareerIdentityTags(tags)",
                "function careerSpotlightItemHtml(item, title, meta)",
                "function renderCareerLatestRace(race)",
                "function renderCareerLatestPb(pb)",
                "function renderCareerAchievementList(items)",
                "function renderCareerOverviewLoading()",
                "function renderCareerOverviewError(message)",
            )
        )
        for token in FORBIDDEN_RENDER_TOKENS:
            self.assertNotIn(token, relevant)

    def test_render_layer_does_not_compute_career_facts(self):
        relevant = "\n".join(
            extract_function_body(self.source, signature)
            for signature in (
                "function renderCareerOverview(viewModel)",
                "function normalizeCareerHeroBanner(hero)",
                "function renderCareerHeroBanner(hero)",
                "function normalizeCareerIdentity(identity)",
                "function renderCareerIdentity(identity)",
                "function renderCareerLatestRace(race)",
                "function renderCareerLatestPb(pb)",
                "function renderCareerAchievementList(items)",
            )
        )
        for token in FORBIDDEN_FACT_TOKENS:
            self.assertNotIn(token, relevant)

    def test_loading_and_error_renderers_are_present(self):
        loading_body = extract_function_body(self.source, "function renderCareerOverviewLoading()")
        error_body = extract_function_body(self.source, "function renderCareerOverviewError(message)")
        self.assertIn("正在加载生涯总览", loading_body)
        self.assertIn("生涯总览暂不可用", error_body)


if __name__ == "__main__":
    unittest.main()
