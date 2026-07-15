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


def test_records_v2_shell_dom_and_tabs_exist():
    src = source()

    assert 'id="career-records-v2-shell"' in src
    assert 'id="career-record-sport-tabs"' in src
    assert 'data-career-record-view="current"' in src
    assert 'data-career-record-view="history"' in src
    assert 'data-career-record-view="candidates"' in src
    assert 'class="career-record-dashboard-main"' in src
    assert 'id="career-record-dashboard-stats"' not in src
    assert "career-record-picker-card" in src
    assert "career-record-board-kicker" in src
    assert "多运动记录中心" in src
    assert "当前纪录、候选与分析曲线保持边界" in src


def test_records_v2_visual_reference_is_dashboard_not_plain_list():
    src = source()
    render_body = extract_function_body(src, "function renderCareerRecordsCenter(viewModel)")
    catalog_body = extract_function_body(src, "function careerRecordCatalogDefinitions(catalog, selectedSport)")
    picker_card_body = extract_function_body(src, "function careerRecordPickerCardHtml(definition, currentRecord, index)")
    picker_body = extract_function_body(src, "function renderCareerRecordPicker(definitions, records, candidates, selectedView)")
    analysis_body = extract_function_body(src, "function renderCareerRecordAnalysisPanel(record, history)")

    assert "const definitions = careerRecordCatalogDefinitions(catalog, selectedSport)" in render_body
    assert "renderCareerRecordPicker(definitions, records, candidatesForGroup, state.selectedView)" in render_body
    assert "listEl.innerHTML = ''" in render_body
    assert "analysis_only" in catalog_body
    assert "candidate_only" not in catalog_body
    assert "validation_required" not in catalog_body
    assert "career-record-picker-card" in picker_card_body
    assert "careerRecordPickerCardHtml" in picker_body
    assert "career-record-picker-value" not in src
    assert "career-record-picker-meta" not in src
    assert "careerRecordAvailabilityBadge" not in picker_card_body
    assert "career-record-dashboard-stats" not in src
    assert "renderCareerRecordDashboardStats" not in src
    assert "careerRecordStatCardHtml" not in src
    assert "焦点来源" not in src
    assert "career-record-analysis-head" in analysis_body
    assert "career-record-chart-box:first-child" in src
    assert "Personal Records" in src
    assert "Record Families" not in src
    assert "career-record-group-card" not in src
    assert "Current Records" not in render_body


def test_records_v2_visual_reference_does_not_import_mock_runtime_or_fake_index():
    src = source()

    for forbidden in (
        "表现指数",
        "基准值为100",
        "modao.cc",
        "iconify-icon",
        "tailwindcss.js",
    ):
        assert forbidden not in src


def test_records_v2_frontend_consumes_catalog_and_viewmodels():
    src = source()
    load_body = extract_function_body(src, "async function loadCareerRecordsCenter(options)")
    render_body = extract_function_body(src, "function renderCareerRecordsCenter(viewModel)")

    assert "api.get_career_record_catalog" in load_body
    assert "api.get_career_records" in load_body
    assert "api.get_career_record_candidates" in load_body
    assert "normalizeCareerRecordCatalog" in load_body
    assert "renderCareerRecordSportTabs(catalog, selectedSport)" in render_body
    assert "候选纪录不会被渲染为当前纪录" in render_body


def test_records_v2_cards_render_backend_fields_without_recomputing():
    src = source()
    normalize_body = extract_function_body(src, "function normalizeCareerRecordV2(item)")
    card_body = extract_function_body(src, "function careerRecordCurrentCardHtml(record, index)")

    assert "metric.display" in normalize_body
    assert "scope.labels" in normalize_body
    assert "item.improvement" in normalize_body
    assert "record.metric.display" in card_body
    assert "record.scope.labels" in card_body
    assert "record.improvement.display" in card_body
    forbidden_frontend_calculations = [
        "totalImprovement +=",
        "axisDirection =",
        "confidence =",
        "metric.value -",
        "metric.value +",
    ]
    combined = normalize_body + card_body
    for token in forbidden_frontend_calculations:
        assert token not in combined


def test_records_v2_no_unimplemented_cycling_avg_speed_placeholder():
    src = source()

    assert "cycling_avg_speed" not in src
    assert "最快均速" not in src


def test_records_v2_loads_with_career_data_and_page_switch():
    src = source()
    load_data = extract_function_body(src, "async function loadCareerData()")
    switch_page = extract_function_body(src, "function switchCareerPage(page)")

    assert "loadCareerRecordsCenter().catch" in load_data
    assert "nextPage === 'pb'" in switch_page
    assert "loadCareerRecordsCenter().catch" in switch_page
