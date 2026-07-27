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


def extract_css_block(src: str, selector: str) -> str:
    start = src.find(selector)
    assert start >= 0, selector
    brace = src.find("{", start)
    assert brace >= 0, selector
    end = src.find("}", brace)
    assert end >= 0, selector
    return src[brace:end + 1]


def test_records_v2_does_not_restore_redundant_status_strip_cards():
    src = source()

    assert 'id="career-record-status-strip"' not in src
    assert "career-record-status-card" not in src
    assert "careerRecordStatusCardHtml" not in src
    assert "renderCareerRecordStatusStrip" not in src
    assert "renderCareerRecordPreviewPanel" not in src
    assert "careerRecordPreviewCardHtml" not in src
    assert "data-career-record-preview-id" not in src


def test_records_v2_responsive_breakpoints_and_no_hidden_overflow_mask():
    src = source()

    for breakpoint in (
        "@media (max-width: 1100px)",
        "@media (max-width: 980px)",
        "@media (max-width: 720px)",
        "@media (max-width: 520px)",
    ):
        assert breakpoint in src
    assert ".career-record-groups" in src
    assert ".career-record-preview-grid" not in src
    assert "overflow-x: auto" in src
    assert "scroll-snap-type: x proximity" in src
    assert ".career-record-analysis-grid" in src
    assert "grid-template-columns: 1fr" in src
    assert "overflow-wrap: anywhere" in src
    records_css = extract_css_block(src, ".career-records-v2-shell")
    assert "overflow: hidden" not in records_css
    assert ".career-pb-list" not in src


def test_records_v2_keyboard_focus_and_group_selection_accessibility():
    src = source()
    picker_card_body = extract_function_body(src, "function careerRecordPickerCardHtml(definition, currentRecord, index)")
    keydown_body = extract_function_body(src, "function onCareerRecordPickerKeydown(event, el)")
    select_body = extract_function_body(src, "function selectCareerRecordKeyForAnalysis(recordKey)")

    assert ":focus-visible" in src
    assert 'role="button"' in picker_card_body
    assert 'tabindex="0"' in picker_card_body
    assert 'aria-pressed="' in picker_card_body
    assert "data-career-record-key" in picker_card_body
    assert "onCareerRecordPickerKeydown(event, this)" in picker_card_body
    assert "event.preventDefault()" in keydown_body
    assert "selectCareerRecordKeyForAnalysis(recordKey)" in keydown_body
    assert "renderCareerRecordsCenter({ catalog: state.catalog })" in select_body


def test_records_v2_has_no_candidate_review_actions():
    src = source()

    assert "function careerRecordCurrentCardHtml" not in src
    assert "careerRecordCandidateCardHtml" not in src
    assert "decideCareerRecordCandidateFromElement" not in src
    assert "data-career-record-feedback" not in src
    assert "确认候选纪录" not in src
    assert "拒绝候选纪录" not in src


def test_records_v2_record_picker_uses_backend_records_not_catalog_group_cards():
    src = source()
    render_body = extract_function_body(src, "function renderCareerRecordsCenter(viewModel)")
    picker_body = extract_function_body(src, "function renderCareerRecordPicker(definitions, records)")
    catalog_body = extract_function_body(src, "function careerRecordCatalogDefinitions(catalog, selectedSport)")

    assert "item.sport === selectedSport" in render_body
    assert "careerRecordCatalogDefinitions(catalog, selectedSport)" in render_body
    assert "group.records" in catalog_body
    assert "item.record_key" in catalog_body
    assert "careerRecordPickerCardHtml" in picker_body
    assert "careerRecordCandidatePickerCardHtml" not in picker_body
    assert "career-record-group-card" not in src
    assert "Record Families" not in src
    assert "setCareerRecordGroup" not in src
    assert "onCareerRecordGroupKeydown" not in src
    forbidden = [
        "confidence =",
        "axisDirection =",
        "metric.value -",
        "metric.value +",
        "totalImprovement",
    ]
    for token in forbidden:
        assert token not in render_body


def test_records_v2_reduced_motion_and_accessible_fallback_lists_remain():
    src = source()

    assert "@media (prefers-reduced-motion: reduce)" in src
    assert "transition: none !important" in src
    assert "careerRecordSeriesFallbackHtml" in src
    assert 'aria-label="可访问历史节点列表"' not in src
    assert 'aria-label="曲线锚点列表"' not in src
    assert 'aria-label="路线对比列表"' not in src
