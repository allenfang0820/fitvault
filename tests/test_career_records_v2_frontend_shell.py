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


def test_records_v2_shell_uses_single_objective_records_view():
    src = source()

    assert 'id="career-records-v2-shell"' in src
    assert 'id="career-record-sport-tabs"' in src
    assert 'data-career-record-view=' not in src
    assert 'id="career-record-view-tabs"' not in src
    assert "setCareerRecordView" not in src
    assert 'class="career-record-dashboard-main"' in src
    assert 'id="career-record-dashboard-stats"' not in src
    assert "career-record-picker-card" in src
    assert "career-record-board-kicker" in src
    assert "多运动记录中心" in src
    assert "按运动类型查看当前最佳与历史成绩曲线。" in src


def test_records_v2_visual_reference_is_dashboard_not_plain_list():
    src = source()
    render_body = extract_function_body(src, "function renderCareerRecordsCenter(viewModel)")
    catalog_body = extract_function_body(src, "function careerRecordCatalogDefinitions(catalog, selectedSport)")
    picker_card_body = extract_function_body(src, "function careerRecordPickerCardHtml(definition, currentRecord, index)")
    picker_body = extract_function_body(src, "function renderCareerRecordPicker(definitions, records)")
    analysis_body = extract_function_body(src, "function renderCareerRecordAnalysisPanel(record, metricSeries)")

    assert "const definitions = careerRecordCatalogDefinitions(catalog, selectedSport)" in render_body
    assert "renderCareerRecordPicker(definitions, records)" in render_body
    assert 'id="career-record-current-list"' not in src
    assert "renderCareerRecordCandidatePanel" not in render_body
    assert "analysis_only" in catalog_body
    assert "candidate_only" not in catalog_body
    assert "validation_required" not in catalog_body
    assert "career-record-picker-card" in picker_card_body
    assert "careerRecordPickerCardHtml" in picker_body
    assert "careerRecordCandidatePickerCardHtml" not in picker_body
    assert "career-record-picker-value" in picker_card_body
    assert "career-record-picker-meta" in picker_card_body
    assert "currentRecord.metric.display" in picker_card_body
    assert "暂无记录" in picker_card_body
    assert "careerRecordAvailabilityBadge" not in picker_card_body
    assert "currentRecord.status" not in picker_card_body
    assert "career-record-dashboard-stats" not in src
    assert "renderCareerRecordDashboardStats" not in src
    assert "careerRecordStatCardHtml" not in src
    assert "焦点来源" not in src
    assert "career-record-analysis-head" in analysis_body
    assert "career-record-chart-box:first-child" in src
    assert "career-record-detail-card" not in src
    assert "careerRecordDetailPanelHtml" not in src
    assert "Personal Records" not in src
    assert "我的记录" in src
    assert "Record Families" not in src
    assert "career-record-group-card" not in src
    assert "Current Records" not in render_body


def test_records_v2_user_visible_copy_hides_engineering_terms():
    src = source()
    shell_start = src.find('<div class="career-records-v2-shell"')
    assert shell_start >= 0
    shell_end = src.find('<div class="career-page" data-career-page="insight"', shell_start)
    assert shell_end >= 0
    shell_html = src[shell_start:shell_end]
    sport_tabs_body = extract_function_body(src, "function renderCareerRecordSportTabs(catalog, selectedSport)")
    picker_body = extract_function_body(src, "function careerRecordPickerCardHtml(definition, currentRecord, index)")
    picker_render_body = extract_function_body(src, "function renderCareerRecordPicker(definitions, records)")
    empty_body = extract_function_body(src, "function careerRecordSeriesEmptyText(record, metricSeries)")
    analysis_body = extract_function_body(src, "function renderCareerRecordAnalysisPanel(record, metricSeries)")
    load_body = extract_function_body(src, "async function loadCareerRecordsCenter(options)")
    visible_copy = "\n".join([
        shell_html,
        sport_tabs_body,
        picker_body,
        picker_render_body,
        empty_body,
        analysis_body,
        load_body,
    ])

    for forbidden in (
        "Catalog 暂无运动项",
        "正在读取 Catalog",
        "记录中心 V2 接口",
        "记录中心 V2 已接入",
        "V2 已接入",
        "由后端 Catalog 驱动",
        "已接入 Catalog",
        "已接入",
        "距离-时间流契约",
        "真实数据验收",
        "演进",
        "候选",
    ):
        assert forbidden not in visible_copy
    assert "运动记录" in shell_html
    assert "暂无可展示记录" in visible_copy
    assert "记录中心暂不可用" in load_body
    assert "careerRecordAvailabilityBadge" not in analysis_body


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
    assert "api.get_career_record_candidates" not in load_body
    assert "api.preview_career_records" not in load_body
    assert "max_activities: 300" not in load_body
    assert "normalizeCareerRecordCatalog" in load_body
    assert "normalizeCareerRecordPreviewV2" not in src
    assert "renderCareerRecordSportTabs(catalog, selectedSport)" in render_body
    assert "renderCareerRecordCandidatePanel" not in render_body
    assert "careerRecordViewFromDefinition(selectedDefinition)" in render_body


def test_records_v2_swimming_sport_labels_are_distinct():
    src = source()
    label_body = extract_function_body(src, "function careerRecordSportLabel(sport)")
    tabs_body = extract_function_body(src, "function renderCareerRecordSportTabs(catalog, selectedSport)")

    assert "pool_swimming: '泳池游泳'" in label_body
    assert "open_water_swimming: '公开水域游泳'" in label_body
    assert "if (key === 'pool_swimming' || key === 'open_water_swimming') return '游泳'" not in label_body
    assert "sport.sportLabel || sport.sport_label || careerRecordSportLabel(sport.sport)" in tabs_body


def test_records_v2_preview_does_not_render_main_area_cards():
    src = source()
    render_body = extract_function_body(src, "function renderCareerRecordsCenter(viewModel)")
    analysis_body = extract_function_body(src, "async function loadCareerRecordAnalysis(record)")

    assert "function careerRecordPreviewCardHtml" not in src
    assert "function renderCareerRecordPreviewPanel" not in src
    assert "function careerRecordPreviewMetricDisplay" not in src
    assert "function normalizeCareerRecordPreviewV2" not in src
    assert "career-record-preview-grid" not in src
    assert "data-career-record-preview-id" not in src
    assert "preview_career_records" not in src
    assert "renderCareerRecordPreviewPanel" not in render_body
    assert "previewForGroup" not in render_body
    assert "records.map(careerRecordCurrentCardHtml)" not in render_body
    assert "career-record-current-list" not in src
    assert "career-record-current-card" not in src
    assert "renderCareerRecordCandidatePanel" not in render_body
    assert "careerRecordViewFromDefinition(selectedDefinition)" in render_body
    assert "loadCareerRecordAnalysis(selectedRecord)" in render_body
    assert "preview" not in analysis_body.lower()


def test_records_v2_current_card_garbage_code_is_removed_without_frontend_recomputing():
    src = source()
    normalize_body = extract_function_body(src, "function normalizeCareerRecordV2(item)")
    render_body = extract_function_body(src, "function renderCareerRecordsCenter(viewModel)")

    assert "function careerRecordCurrentCardHtml" not in src
    assert "data-career-record-id" not in src
    assert "openCareerRecordDetailFromElementV2" not in src
    assert "selectCareerRecordForAnalysis" not in src
    assert "onCareerRecordAnalysisKeydown" not in src
    assert "metric.display" in normalize_body
    assert "scope.labels" in normalize_body
    assert "item.improvement" in normalize_body
    forbidden_frontend_calculations = [
        "totalImprovement +=",
        "axisDirection =",
        "confidence =",
        "metric.value -",
        "metric.value +",
    ]
    combined = normalize_body + render_body
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
