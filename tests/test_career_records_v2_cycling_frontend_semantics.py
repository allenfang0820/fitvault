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


def test_cycling_catalog_cards_use_standard_distance_power_duration_then_endurance_order():
    src = source()
    standard_order = extract_function_body(src, "const careerRecordCyclingStandardDistanceOrder =")
    power_order = extract_function_body(src, "const careerRecordCyclingPowerOrder =")
    endurance_order = extract_function_body(src, "const careerRecordCyclingEnduranceOrder =")
    sort_body = extract_function_body(src, "function careerRecordDefinitionDisplayOrder(definition)")
    catalog_body = extract_function_body(src, "function careerRecordCatalogDefinitions(catalog, selectedSport)")

    expected_standard = [
        "cycling_fastest_10k",
        "cycling_fastest_20k",
        "cycling_fastest_40k",
        "cycling_fastest_50k",
        "cycling_fastest_100k",
        "cycling_fastest_180k",
    ]
    standard_positions = [standard_order.index(key) for key in expected_standard]
    assert standard_positions == sorted(standard_positions)

    expected_power = [
        "cycling_power_5s",
        "cycling_power_30s",
        "cycling_power_1m",
        "cycling_power_5m",
        "cycling_power_10m",
        "cycling_power_20m",
        "cycling_power_30m",
        "cycling_power_60m",
        "cycling_power_2h",
    ]
    positions = [power_order.index(key) for key in expected_power]
    assert positions == sorted(positions)

    expected_endurance = [
        "cycling_longest_distance",
        "cycling_max_ascent",
        "cycling_longest_elapsed_time",
        "cycling_max_work",
    ]
    endurance_positions = [endurance_order.index(key) for key in expected_endurance]
    assert endurance_positions == sorted(endurance_positions)

    assert "definition.sport === 'cycling'" in sort_body
    assert "careerRecordCyclingDisplayOrder(definition)" in sort_body
    assert "careerRecordCyclingStandardDistanceOrder" in sort_body or "careerRecordCyclingDisplayOrder" in sort_body
    assert "careerRecordDefinitionDisplayOrder(a)" in catalog_body
    assert "groupKey" in catalog_body
    assert "groupLabel" in catalog_body
    assert "candidate_only" not in catalog_body
    assert "validation_required" not in catalog_body


def test_cycling_left_picker_stays_title_only_but_uses_catalog_keys():
    src = source()
    picker = extract_function_body(src, "function careerRecordPickerCardHtml(definition, currentRecord, index)")
    render_picker = extract_function_body(src, "function renderCareerRecordPicker(definitions, records, candidates, selectedView)")
    section_label = extract_function_body(src, "function careerRecordPickerSectionLabel(definition)")

    assert "data-career-record-key" in picker
    assert "definition.displayName" in picker
    assert "selectCareerRecordKeyForAnalysis" in picker
    assert "career-record-picker-section" in render_picker
    assert "标准距离" in section_label
    assert "功率时长" in section_label
    assert "整次活动" in section_label
    assert "career-record-picker-value" not in src
    assert "career-record-picker-meta" not in src
    assert "careerRecordAvailabilityBadge" not in picker


def test_cycling_chart_titles_and_empty_states_match_platform_semantics():
    src = source()
    title_body = extract_function_body(src, "function careerRecordChartTitle(record, axisDirection)")
    subtitle_body = extract_function_body(src, "function careerRecordAnalysisSubtitle(record)")
    empty_body = extract_function_body(src, "function careerRecordHistoryEmptyText(record)")
    render_body = extract_function_body(src, "function renderCareerRecordAnalysisPanel(record, history)")

    assert "careerRecordIsCyclingStandardDistanceRecord(record)" in title_body
    assert "历年最快成绩 · 越低越好" in title_body
    assert "careerRecordIsCyclingPowerRecord(record)" in title_body
    assert "历年最佳功率 · 越高越好" in title_body
    assert "历年骑行纪录 · 越高越好" in title_body
    assert "该标准距离的历年最快成绩" in subtitle_body
    assert "该时长的历年最佳平均功率" in subtitle_body
    assert "该骑行纪录的历年最佳成绩" in subtitle_body
    assert "暂无正式标准距离纪录" in empty_body
    assert "距离-时间流契约仍待真实数据验收" in empty_body
    assert "暂无正式功率纪录" in empty_body
    assert "缺少功率计数据" in empty_body
    assert "暂无正式骑行纪录" in empty_body
    assert "careerRecordChartTitle(record, axisDirection)" in render_body
    assert "careerRecordHistoryListHtml(history, record)" in render_body


def test_cycling_records_center_main_view_does_not_restore_curve_or_route_modules():
    src = source()
    load_body = extract_function_body(src, "async function loadCareerRecordAnalysis(record)")

    forbidden = [
        "api.get_career_record_curve",
        "api.get_trail_route_comparison",
        "Pace/GAP 分析曲线",
        "路线 PR 对比",
        "越野路线对比",
        "曲线空态",
        "曲线锚点列表",
        "路线对比列表",
    ]
    for token in forbidden:
        assert token not in src
        assert token not in load_body
