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
    assert ".dispose()" in dispose
    assert ".resize()" in resize
    assert "window.addEventListener('resize', resizeCareerRecordCharts)" in src


def test_records_analysis_loads_only_backend_viewmodels():
    src = source()
    load_body = extract_function_body(src, "async function loadCareerRecordAnalysis(record)")

    assert "api.get_career_record_history" in load_body
    assert "api.get_career_record_detail" in load_body
    assert "api.get_career_record_curve" not in load_body
    assert "api.get_trail_route_comparison" not in load_body
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
    render_body = extract_function_body(src, "function renderCareerRecordAnalysisPanel(record, history)")
    title_body = extract_function_body(src, "function careerRecordChartTitle(record, axisDirection)")
    subtitle_body = extract_function_body(src, "function careerRecordAnalysisSubtitle(record)")

    assert "record.axisDirection" in render_body
    assert "inverse: axisDirection === 'lower'" in render_body
    assert "careerRecordChartTitle(record, axisDirection)" in render_body
    assert "careerRecordAnalysisSubtitle(record)" in render_body
    assert "历年纪录成绩" in title_body
    assert "自活动记录以来的历年相关纪录成绩" in subtitle_body
    assert "Pace/GAP 分析曲线" not in render_body
    assert "showCurvePanel" not in render_body
    assert "showRoutePanel" not in render_body
    assert "路线 PR 对比" not in render_body
    assert "曲线空态" not in render_body
    assert "越野路线对比" not in render_body
    assert "刷新越野 10K 正式纪录" not in render_body


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
