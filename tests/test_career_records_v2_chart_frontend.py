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
    assert "aria-label=\"可访问历史节点列表\"" in src
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
    assert "api.get_career_record_history" not in load_body
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
    assert "item.isCurrentBest" in render_body
    assert "item.isRecordBreaking" in render_body
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
    list_body = extract_function_body(src, "function careerRecordSeriesListHtml(metricSeries, record)")

    assert "data.points" in normalizer
    assert "data.current_best" in normalizer
    assert "data.record_progression" in normalizer
    assert "item.is_current_best" in normalizer
    assert "item.is_record_breaking" in normalizer
    assert "data.status" in normalizer
    assert "status.message" in empty_text
    assert "metricSeries.points" in list_body
    assert "当前最佳" in list_body
    assert "刷新记录" in list_body
    forbidden = ["points_json", "track_json", "raw_points", "best_effort_distance_window"]
    for token in forbidden:
        assert token not in normalizer
        assert token not in list_body


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
    assert "state.loading = true" in switch_sport
    assert "renderCareerRecordsCenter({ catalog: state.catalog })" in switch_sport


def test_records_sport_switch_keeps_catalog_picker_during_refresh():
    src = source()
    render_body = extract_function_body(src, "function renderCareerRecordsCenter(viewModel)")
    load_body = extract_function_body(src, "async function loadCareerRecordsCenter(options)")

    assert "const definitions = careerRecordCatalogDefinitions(catalog, selectedSport)" in render_body
    assert "if (state.loading)" in render_body
    loading_slice = render_body[render_body.find("if (state.loading)"):]
    assert "renderCareerRecordPicker(definitions, records, candidatesForGroup, state.selectedView)" in loading_slice
    assert "careerRecordViewFromDefinition(loadingDefinition)" in loading_slice
    assert "renderCareerRecordAnalysisPanel(loadingRecord, null)" in loading_slice
    history_slice = render_body[render_body.find("if (state.selectedView === 'history')"):]
    assert "loadCareerRecordAnalysis(historyFocus)" in history_slice
    assert "state.analysis && state.analysis.metricSeries ? state.analysis.metricSeries : null" in history_slice
    assert "api.preview_career_records" not in load_body


def test_records_center_initial_load_ignores_stale_requests():
    src = source()
    load_body = extract_function_body(src, "async function loadCareerRecordsCenter(options)")
    select_body = extract_function_body(src, "function selectCareerRecordKeyForAnalysis(recordKey)")

    assert "state.recordsRequestId = requestId" in load_body
    assert "if (state.recordsRequestId !== requestId)" in load_body
    assert "const selectedSport = state.selectedSport || (catalog.sports.length ? catalog.sports[0].sport : '')" in load_body
    assert "api.get_career_records({ sport: selectedSport || 'all' })" in load_body
    assert "state.analysis = null" in select_body
    assert "state.detail = null" in select_body
