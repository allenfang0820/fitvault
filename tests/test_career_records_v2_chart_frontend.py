from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACK_HTML = PROJECT_ROOT / "track.html"


def source() -> str:
    return TRACK_HTML.read_text(encoding="utf-8")


def extract_function_body(src: str, signature: str) -> str:
    start = src.find(signature)
    assert start >= 0, signature
    brace = src.find("{", start)
    assert brace >= 0, signature
    depth = 0
    for index in range(brace, len(src)):
        if src[index] == "{":
            depth += 1
        elif src[index] == "}":
            depth -= 1
            if depth == 0:
                return src[brace:index + 1]
    raise AssertionError(f"function not closed: {signature}")


def test_records_chart_panel_and_accessible_fallback_exist():
    src = source()

    assert 'id="career-record-analysis-panel"' in src
    assert "career-record-analysis-grid" in src
    assert "career-record-chart-canvas" in src
    assert "careerRecordSeriesFallbackHtml" in src
    assert "aria-label=\"可访问历史节点列表\"" not in src
    assert "aria-label=\"曲线锚点列表\"" not in src
    assert "aria-label=\"路线对比列表\"" not in src


def test_records_chart_engine_manages_echarts_instances():
    src = source()
    render_chart = extract_function_body(src, "function renderCareerRecordChart(containerId, option, fallbackHtml)")
    dispose = extract_function_body(src, "function disposeCareerRecordCharts()")
    resize = extract_function_body(src, "function resizeCareerRecordCharts()")

    assert "window.echarts" in render_chart
    assert "window.echarts.init" in render_chart
    assert "chart.setOption" in render_chart
    assert "__careerRecordClickHandler" in render_chart
    assert "chart.on('click', clickHandler)" in render_chart
    assert "careerRecordChartInstances[containerId]" in render_chart
    assert "setTimeout(function()" in render_chart
    assert "chart.resize()" in render_chart
    assert ".dispose()" in dispose
    assert ".resize()" in resize
    assert "window.addEventListener('resize', resizeCareerRecordCharts)" in src


def test_records_analysis_loads_only_backend_viewmodels():
    src = source()
    load_body = extract_function_body(src, "async function loadCareerRecordAnalysis(record)")

    assert "api.get_career_record_metric_series" in load_body
    assert "record_key: record.recordKey" in load_body
    assert "sport: record.sport || expectedSport || 'all'" in load_body
    assert "scope_hash: (record.scope && record.scope.scopeHash) || 'all'" in load_body
    assert "status: 'available'" in load_body
    assert "api.get_career_record_history" not in load_body
    assert "api.preview_career_records" not in load_body
    assert "api.rebuild_career_records" not in load_body
    assert "api.rebuild_career_pb_records" not in load_body
    assert "api.get_career_record_detail" in load_body
    assert "state.analysisRequestId = requestId" in load_body
    assert "String(state.selectedRecordKey || '') !== expectedRecordKey" in load_body
    assert "String(state.selectedSport || '') !== expectedSport" in load_body
    assert "api.get_career_record_curve" not in load_body
    assert "api.get_trail_route_comparison" not in load_body
    assert "normalizeCareerRecordMetricSeries" in load_body
    assert "metricSeries" in load_body
    assert "requireCareerApiData" in load_body
    forbidden = [
        "track_points",
        "raw_points",
        "points_json",
        "track_json",
        "fit_records",
        "raw_records",
    ]
    for token in forbidden:
        assert token not in load_body


def test_records_analysis_respects_backend_axis_and_analysis_labels():
    src = source()
    render_body = extract_function_body(src, "function renderCareerRecordAnalysisPanel(record, metricSeries)")
    visual_body = extract_function_body(src, "function careerRecordPointVisual(point, currentBestId, progressionIds)")
    title_body = extract_function_body(src, "function careerRecordChartTitle(record, axisDirection)")
    subtitle_body = extract_function_body(src, "function careerRecordAnalysisSubtitle(record)")

    assert "record.axisDirection" in render_body
    assert "series.axisDirection" in render_body
    assert "inverse: axisDirection === 'lower'" in render_body
    assert "careerRecordChartTitle(record, axisDirection)" in render_body
    assert "careerRecordAnalysisSubtitle(record)" in render_body
    assert "series.points" in render_body
    assert "series.currentBest" in render_body
    assert "series.recordProgression" in render_body
    assert "safePoint.isCurrentBest" in visual_body
    assert "safePoint.isRecordBreaking" in visual_body
    assert "careerRecordPointVisual(point, currentBestId, progressionIds)" in render_body
    assert "currentBestId" in render_body
    assert "progressionIds" in render_body
    assert "markPoint" in render_body
    assert "progressionMarkers.length ? { data: progressionMarkers } : undefined" in render_body
    assert "step: 'end'" not in render_body
    assert "history.records" not in render_body
    assert "历年纪录成绩" in title_body
    assert "自活动记录以来的历年相关纪录成绩" in subtitle_body
    assert "Pace/GAP 分析曲线" not in render_body
    assert "showCurvePanel" not in render_body
    assert "showRoutePanel" not in render_body
    assert "路线 PR 对比" not in render_body
    assert "曲线空态" not in render_body
    assert "越野路线对比" not in render_body
    assert "刷新越野 10K 正式纪录" not in render_body


def test_records_series_normalizer_and_empty_state_use_backend_viewmodel():
    src = source()
    normalizer = extract_function_body(src, "function normalizeCareerRecordMetricSeries(payload)")
    empty_text = extract_function_body(src, "function careerRecordSeriesEmptyText(record, metricSeries)")
    fallback_body = extract_function_body(src, "function careerRecordSeriesFallbackHtml(metricSeries, record)")
    visual_body = extract_function_body(src, "function careerRecordPointVisual(point, currentBestId, progressionIds)")
    fallback_point_body = extract_function_body(src, "function careerRecordSeriesFallbackPointHtml(point, visual)")

    assert "data.points" in normalizer
    assert "data.current_best" in normalizer
    assert "data.record_progression" in normalizer
    assert "data.summary" in normalizer
    assert "data.filters" in normalizer
    assert "item.is_current_best" in normalizer
    assert "item.is_record_breaking" in normalizer
    assert "data.status" in normalizer
    assert "status.message" in empty_text
    assert "metricSeries.points" in fallback_body
    assert "careerRecordPointVisual(point, currentBestId, progressionIds)" in fallback_body
    assert "careerRecordSeriesFallbackPointHtml(point, visual)" in fallback_body
    assert "当前最佳" in visual_body
    assert "刷新记录" in visual_body
    assert "活动成绩" in visual_body
    assert "visual.label" in fallback_point_body
    forbidden = ["points_json", "track_json", "raw_points", "best_effort_distance_window"]
    for token in forbidden:
        assert token not in normalizer
        assert token not in fallback_body


def test_records_chart_red_and_yellow_points_open_activity_detail_only_when_real_activity_exists():
    src = source()
    render_body = extract_function_body(src, "function renderCareerRecordAnalysisPanel(record, metricSeries)")
    activity_body = extract_function_body(src, "function careerRecordPointActivityId(point)")
    can_open_body = extract_function_body(src, "function careerRecordPointCanOpenActivity(point, visual)")
    open_data_body = extract_function_body(src, "function openCareerRecordPointActivityData(data)")
    fallback_point_body = extract_function_body(src, "function careerRecordSeriesFallbackPointHtml(point, visual)")
    keydown_body = extract_function_body(src, "function onCareerRecordPointActivityKeydown(event, el)")

    assert "detailLink.activityId || safePoint.activityId" in activity_body
    assert "kind === 'record_breaking' || kind === 'current_best'" in can_open_body
    assert "raw.canOpenActivity !== true || !raw.activityId" in open_data_body
    assert "openCareerActivityDetailFromElement(proxy)" in open_data_body
    assert "__careerRecordClickHandler" in render_body
    assert "openCareerRecordPointActivityData(params && params.data)" in render_body
    assert "activityId: activityId" in render_body
    assert "pointKind: entry.visual.kind" in render_body
    assert "canOpenActivity: canOpenActivity" in render_body
    assert "careerRecordPointCanOpenActivity(entry.point, entry.visual)" in render_body
    assert "role=\"button\"" in fallback_point_body
    assert "tabindex=\"0\"" in fallback_point_body
    assert "openCareerRecordPointActivityFromElement(this)" in fallback_point_body
    assert "onCareerRecordPointActivityKeydown(event, this)" in fallback_point_body
    assert "onCareerActivityDetailKeydown(event, el)" in keydown_body


def test_records_chart_ui_keeps_main_plot_clean_and_readable():
    src = source()
    render_body = extract_function_body(src, "function renderCareerRecordAnalysisPanel(record, metricSeries)")
    axis_body = extract_function_body(src, "function careerRecordChartAxisLabel(value)")
    legend_body = extract_function_body(src, "function careerRecordChartLegendHtml(points)")
    visual_body = extract_function_body(src, "function careerRecordPointVisual(point, currentBestId, progressionIds)")

    assert "careerRecordChartLegendHtml(points)" in render_body
    assert "careerRecordChartAxisLabel" in render_body
    assert "axisLabel: { color: '#94a3b8', formatter: careerRecordChartAxisLabel }" in render_body
    assert "careerRecordSeriesFallbackHtml(series, record)" in render_body
    assert "formatDuration(seconds)" in axis_body
    assert "活动成绩" in legend_body
    assert "刷新记录" in legend_body
    assert "当前最佳" in legend_body
    assert "#60a5fa" in visual_body
    assert "#f43f5e" in visual_body
    assert "#facc15" in visual_body
    assert "showSymbol: true" in render_body
    assert "visiblePoints.map" in render_body
    assert "symbol: 'circle'" in render_body
    assert "label: { show: false }" in render_body
    assert "symbol: 'pin'" not in render_body
    assert "career-record-node-list" not in src
    assert "careerRecordSeriesListHtml" not in src


def test_records_card_switch_renders_immediately_and_reuses_analysis_cache():
    src = source()
    state_body = extract_function_body(src, "function careerRecordState()")
    load_body = extract_function_body(src, "async function loadCareerRecordAnalysis(record)")
    select_body = extract_function_body(src, "function selectCareerRecordKeyForAnalysis(recordKey)")

    assert "analysisCache" in state_body
    assert "const cachedAnalysis = state.analysisCache" in load_body
    assert "renderCareerRecordAnalysisPanel(record, cachedAnalysis.metricSeries || null)" in load_body
    assert "renderCareerRecordAnalysisPanel(record, null)" in load_body
    assert "state.analysisCache[cacheKey] = state.analysis" in load_body
    assert "state.analysis = state.analysisCache && state.analysisCache[cacheKey]" in select_body


def test_records_card_selection_loads_analysis_and_disposes_on_sport_switch():
    src = source()
    card = extract_function_body(src, "function careerRecordPickerCardHtml(definition, currentRecord, index)")
    render_body = extract_function_body(src, "function renderCareerRecordsCenter(viewModel)")
    select = extract_function_body(src, "function selectCareerRecordKeyForAnalysis(recordKey)")
    switch_sport = extract_function_body(src, "function setCareerRecordSport(sport)")

    assert "selectCareerRecordKeyForAnalysis" in card
    assert "onCareerRecordPickerKeydown" in card
    assert "data-career-record-key" in card
    assert "renderCareerRecordsCenter({ catalog: state.catalog })" in select
    assert "loadCareerRecordAnalysis(selectedRecord)" in render_body
    assert "disposeCareerRecordCharts()" in switch_sport
    assert "state.selectedRecordKey = ''" in switch_sport
    assert "state.analysis = null" in switch_sport
    assert "state.analysisRequestId = Number(state.analysisRequestId || 0) + 1" in switch_sport
    assert "state.loading = false" in switch_sport
    assert "renderCareerRecordsCenter({ catalog: state.catalog })" in switch_sport
    assert "loadCareerRecordsCenter()" in switch_sport
    assert "loadCareerRecordsCenter({ refresh: true })" not in switch_sport


def test_records_sport_switch_keeps_catalog_picker_during_refresh():
    src = source()
    render_body = extract_function_body(src, "function renderCareerRecordsCenter(viewModel)")
    load_body = extract_function_body(src, "async function loadCareerRecordsCenter(options)")

    assert "const definitions = careerRecordCatalogDefinitions(catalog, selectedSport)" in render_body
    assert "if (state.loading)" in render_body
    loading_slice = render_body[render_body.find("if (state.loading)"):]
    assert "renderCareerRecordPicker(definitions, records)" in loading_slice
    assert "careerRecordViewFromDefinition(loadingDefinition)" in loading_slice
    assert "renderCareerRecordAnalysisPanel(loadingRecord, null)" in loading_slice
    assert "selectedView" not in render_body
    assert "loadCareerRecordAnalysis(selectedRecord)" in render_body
    assert "state.analysis && state.analysis.metricSeries ? state.analysis.metricSeries : null" in render_body
    assert "api.preview_career_records" not in load_body


def test_records_center_initial_load_ignores_stale_requests():
    src = source()
    load_body = extract_function_body(src, "async function loadCareerRecordsCenter(options)")
    select_body = extract_function_body(src, "function selectCareerRecordKeyForAnalysis(recordKey)")

    assert "const opts = options && typeof options === 'object' ? options : {}" in load_body
    assert "state.recordsRequestId = requestId" in load_body
    assert "if (state.recordsRequestId !== requestId)" in load_body
    assert "const selectedSport = state.selectedSport || (catalog.sports.length ? catalog.sports[0].sport : '')" in load_body
    assert "api.get_career_records({ sport: selectedSport || 'all' })" in load_body
    assert "state.analysisCache[cacheKey]" in select_body
    assert "state.detail = null" in select_body


def test_records_center_reuses_cached_viewmodel_when_source_is_unchanged():
    src = source()
    state_body = extract_function_body(src, "function careerRecordState()")
    load_body = extract_function_body(src, "async function loadCareerRecordsCenter(options)")

    assert "loaded: false" in state_body
    assert "recordsBySport: {}" in state_body
    assert "loadedSport: ''" in state_body
    assert "loadedSourceVersion: null" in state_body
    assert "!opts.refresh" in load_body
    assert "const cachedSport = state.recordsBySport" in load_body
    assert "Number(cachedSport.sourceVersion || 0) === currentSourceVersion" in load_body
    assert "state.records = Array.isArray(cachedSport.records) ? cachedSport.records : []" in load_body
    assert "cachedSport.candidates" not in load_body
    assert "return state" in load_body
    assert "state.loaded = true" in load_body
    assert "state.loadedSport = selectedSport || 'all'" in load_body
    assert "state.loadedSourceVersion = currentSourceVersion" in load_body
    assert "state.recordsBySport[state.loadedSport]" in load_body


def test_records_center_renders_catalog_before_slow_records_request():
    src = source()
    load_body = extract_function_body(src, "async function loadCareerRecordsCenter(options)")
    catalog_index = load_body.find("state.catalog = catalog")
    render_index = load_body.find("renderCareerRecordsCenter({ catalog: state.catalog })", catalog_index)
    records_index = load_body.find("api.get_career_records({ sport: selectedSport || 'all' })")

    assert catalog_index >= 0
    assert render_index > catalog_index
    assert records_index > render_index
    assert "const recordsRes = await api.get_career_records" in load_body
    assert "Promise.all" not in load_body


def test_records_center_keeps_compat_paths_out_of_main_chart_source():
    src = source()
    center_body = extract_function_body(src, "async function loadCareerRecordsCenter(options)")
    analysis_body = extract_function_body(src, "async function loadCareerRecordAnalysis(record)")

    assert "api.get_career_record_catalog" in center_body
    assert "api.get_career_records" in center_body
    assert "api.get_career_record_candidates" not in center_body
    assert "api.decide_career_record_candidate" not in src

    for compat_token in (
        "api.get_career_records",
        "api.get_career_record_candidates",
        "api.decide_career_record_candidate",
    ):
        assert compat_token not in analysis_body

    for legacy_source in (
        "api.get_career_record_history",
        "api.preview_career_records",
        "api.rebuild_career_records",
        "api.rebuild_career_pb_records",
    ):
        assert legacy_source not in analysis_body
