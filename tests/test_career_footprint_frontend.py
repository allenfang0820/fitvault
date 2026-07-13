import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACK_HTML_PATH = PROJECT_ROOT / "track.html"

FORBIDDEN_FOOTPRINT_TOKENS = (
    "points_json",
    "track_json",
    "raw_records",
    "fit_records",
    "file_path",
    "advanced_metrics",
    "shadow_diff_json",
    "sqlite_schema",
    "storage_ref",
    "file://",
    "/Users/",
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


class TestCareerFootprintFrontend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TRACK_HTML_PATH.read_text(encoding="utf-8")

    def test_footprint_page_contains_dark_map_targets_without_manual_inputs(self):
        section = extract_between(
            self.source,
            '<section class="career-section" data-career-section="footprint">',
            '</section>',
        )
        for token in (
            'id="career-footprint-status-text"',
            'id="career-footprint-year-filter"',
            'id="career-footprint-sport-filter"',
            'id="career-footprint-map"',
            'id="career-footprint-hover-card"',
            'id="career-footprint-detail-panel"',
            'id="career-footprint-missing-list"',
            'id="career-footprint-empty"',
            "生涯足迹",
        ):
            self.assertIn(token, section)
        self.assertIn('data-map-mode="china"', section)
        self.assertNotIn("career-race-map-locations", section)
        self.assertNotIn("career-memory-story-activity-id", section)
        self.assertNotIn("placeholder=\"活动 ID\"", section)
        self.assertNotIn("添加故事", section)

    def test_load_career_footprint_calls_api_and_handles_envelope(self):
        body = extract_function_body(self.source, "async function loadCareerFootprint(filters)")
        self.assertIn("window.pywebview", body)
        self.assertIn("api.get_career_footprint(nextFilters)", body)
        self.assertIn("requireCareerApiData(res, '生涯足迹加载失败')", body)
        self.assertIn("normalizeCareerFootprint(requireCareerApiData", body)
        self.assertIn("renderCareerFootprintLoading()", body)
        self.assertIn("renderCareerFootprintError(message)", body)
        self.assertIn("for (let attempt = 0; attempt < 2; attempt += 1)", body)
        self.assertIn("await waitCareerApiRetry(320)", body)

    def test_footprint_normalizers_use_whitelisted_fields(self):
        relevant = "\n".join(
            extract_function_body(self.source, signature)
            for signature in (
                "function normalizeCareerFootprintRegion(item)",
                "function normalizeCareerFootprintMissing(item)",
                "function normalizeCareerFootprint(payload)",
            )
        )
        for token in (
            "map_mode",
            "region_key",
            "country_code",
            "activity_count",
            "race_count",
            "first_activity_date",
            "latest_activity_date",
            "representative_activity_id",
            "without_region",
            "summary",
            "status",
            "detail_link",
        ):
            self.assertIn(token, relevant)
        self.assertNotIn("Object.assign", relevant)
        self.assertNotIn("...item", relevant)
        for token in FORBIDDEN_FOOTPRINT_TOKENS:
            self.assertNotIn(token, relevant)

    def test_footprint_map_uses_backend_mode_and_echarts_geojson_resource(self):
        render_body = extract_function_body(self.source, "function renderCareerFootprint(viewModel, options)")
        register_body = extract_function_body(self.source, "function ensureCareerFootprintEchartsMap(mapMode)")
        option_body = extract_function_body(self.source, "function buildCareerFootprintChartOption(mapMode, litByKey)")
        asset_body = extract_function_body(self.source, "function buildCareerFootprintAssetRegionMap(mapMode)")
        self.assertIn("vm.mapMode === 'world' ? 'world' : 'china'", render_body)
        self.assertIn("getCareerFootprintMapConfig(mapMode)", render_body)
        self.assertIn("ensureCareerFootprintEchartsMap(mapMode)", render_body)
        self.assertIn("buildCareerFootprintChartOption(mapMode, litByKey)", render_body)
        self.assertIn("buildCareerFootprintMapRegions(vm, mapMode)", render_body)
        self.assertIn("window.FITVAULT_CAREER_FOOTPRINT_MAPS", self.source)
        self.assertIn("assets/career_footprint_maps.js", self.source)
        self.assertIn("echarts.registerMap(config.mapName, geoJson)", register_body)
        self.assertIn("nameProperty: config.keyProperty", option_body)
        self.assertIn("layoutCenter: config.layoutCenter", option_body)
        self.assertIn("layoutSize: config.layoutSize", option_body)
        self.assertIn("regions: buildCareerFootprintStaticChartRegions(mapMode)", option_body)
        self.assertIn("roam: false", option_body)
        self.assertIn("label: {\n                    show: false", option_body)
        self.assertIn("normalizeCareerFootprintAssetRegion(feature, mapMode)", asset_body)
        self.assertIn("region_key", self.source)

    def test_footprint_map_is_static_region_lighting_not_tile_service(self):
        option_body = extract_function_body(self.source, "function buildCareerFootprintChartOption(mapMode, litByKey)")
        css = extract_between(self.source, ".career-footprint-map {", ".career-footprint-static-map-layer {")
        self.assertIn("type: 'map'", option_body)
        self.assertIn("areaColor", option_body)
        self.assertIn("本地 GeoJSON · ECharts", self.source)
        self.assertIn("min-height: 420px", css)
        self.assertIn(".career-footprint-map-back", self.source)
        self.assertNotIn("FITVAULT_CAREER_MAP_PROVIDER", self.source)
        self.assertNotIn("tianditu", self.source.lower())
        self.assertNotIn("openstreetmap", self.source.lower())
        self.assertNotIn("Leaflet", self.source)
        self.assertNotIn("mapbox", self.source.lower())
        self.assertNotIn("tileLayer", self.source)

    def test_footprint_map_uses_real_local_geojson_and_world_china_aggregation(self):
        aggregate_body = extract_function_body(self.source, "function buildCareerFootprintMapRegions(viewModel, mapMode)")
        country_body = extract_function_body(self.source, "function buildCareerFootprintCountryRegion(regions, countryCode)")
        config = extract_between(
            self.source,
            "const CAREER_FOOTPRINT_MAP_CONFIG = {",
            "    const careerFootprintRegisteredMaps = {};",
        )
        self.assertIn("FitVaultCareerFootprintWorld", config)
        self.assertIn("FitVaultCareerFootprintChina", config)
        self.assertIn("FitVaultCareerFootprintJapan", config)
        self.assertIn("FitVaultCareerFootprintUS", config)
        self.assertIn("keyProperty: 'region_key'", config)
        self.assertIn("supportedDrilldowns: { CN: 'china', TW: 'china', JP: 'japan', US: 'us' }", config)
        self.assertIn("script: 'assets/career_footprint_us.js'", config)
        self.assertIn("layoutSize: '150%'", config)
        self.assertIn("layoutSize: '106%'", config)
        self.assertIn("countryCode === countryCode", aggregate_body)
        self.assertIn("regionKey: countryCode", self.source)
        self.assertIn("regionKey: 'TW'", aggregate_body)
        self.assertIn("countryCode === 'CN'", aggregate_body)
        self.assertIn("activityCount", country_body)
        self.assertIn("CN-TW", self.source)
        self.assertIn("function hasCareerFootprintDrilldownRegions(viewModel, regionKey, drilldown)", self.source)
        self.assertIn("String(region.regionKey || '') !== countryCode", self.source)
        self.assertIn("String(region.mapMode || '') === drilldown", self.source)

    def test_footprint_region_interaction_shows_summary_and_detail_panel(self):
        render_preview_body = extract_function_body(self.source, "function renderCareerFootprintPreview(regionKey)")
        ensure_chart_body = extract_function_body(self.source, "function ensureCareerFootprintChart(mapEl)")
        detail_body = extract_function_body(self.source, "function renderCareerFootprintDetail(regionKey)")
        select_body = extract_function_body(self.source, "function selectCareerFootprintRegion(regionKey)")
        state_body = extract_function_body(self.source, "function getCareerFootprintRegionState(regionKey)")
        combined = "\n".join([render_preview_body, ensure_chart_body, detail_body, select_body, state_body])

        self.assertIn("footprintChart.on('mouseover'", ensure_chart_body)
        self.assertIn("footprintChart.on('click'", ensure_chart_body)
        self.assertIn("const drilldown = getCareerFootprintMapConfig(currentMode).supportedDrilldowns[key]", ensure_chart_body)
        self.assertIn("drilldown && hasCareerFootprintDrilldownRegions", ensure_chart_body)
        self.assertIn("renderCareerFootprint(appState.career.footprint || normalizeCareerFootprint({}), { mapMode: drilldown", ensure_chart_body)
        self.assertIn("loadCareerFootprintMapScript(mapMode", self.source)
        self.assertIn("正在加载本地地图资源", self.source)
        self.assertNotIn("drilldown && key === 'CN'", ensure_chart_body)
        self.assertIn("returnCareerFootprintWorldMap", self.source)
        self.assertIn("career-footprint-map-back", self.source)
        self.assertIn("career-footprint-hover-card", combined)
        self.assertIn("career-footprint-detail-panel", combined)
        self.assertIn("footprintRegionByKey", combined)
        self.assertIn("footprintAssetRegionByKey", combined)
        self.assertIn("openCareerActivityDetailFromElement(this)", detail_body)
        self.assertIn('data-activity-id="', detail_body)
        self.assertIn("representativeActivityId", detail_body)
        self.assertNotIn("item.title", combined)
        self.assertNotIn("region_display", combined)

    def test_missing_region_activities_are_not_rendered_as_activity_cards(self):
        render_body = extract_function_body(self.source, "function renderCareerFootprint(viewModel, options)")
        css = extract_between(self.source, ".career-footprint-missing-list {", ".career-footprint-missing-card {")
        self.assertIn("display: none", css)
        self.assertIn("missingEl.innerHTML = ''", render_body)
        self.assertNotIn("careerFootprintMissingHtml", self.source)
        self.assertNotIn("Activity #", self.source)

    def test_load_career_data_includes_footprint_not_legacy_race_map(self):
        body = extract_function_body(self.source, "async function loadCareerData()")
        self.assertIn("loadCareerFootprint().catch", body)
        self.assertNotIn("loadCareerRaceMap().catch", body)

    def test_switching_to_footprint_refreshes_hidden_echarts_map(self):
        body = extract_function_body(self.source, "function switchCareerPage(page)")
        refresh_body = extract_function_body(self.source, "function refreshCareerFootprintMapWhenVisible()")

        self.assertIn("if (nextPage === 'footprint') refreshCareerFootprintMapWhenVisible()", body)
        self.assertIn("setTimeout(function()", refresh_body)
        self.assertIn("renderCareerFootprint(appState.career.footprint", refresh_body)
        self.assertIn("footprintChart.resize()", refresh_body)


if __name__ == "__main__":
    unittest.main()
