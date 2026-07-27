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


def test_records_v2_analysis_still_uses_backend_record_viewmodels():
    src = source()
    load_body = extract_function_body(src, "async function loadCareerRecordAnalysis(record)")

    assert "api.get_career_record_detail" in load_body
    assert "record_id: record.id" in load_body
    assert "api.get_career_record_metric_series" in load_body
    assert "normalizeCareerRecordMetricSeries" in load_body
    assert "api.get_career_record_candidates" not in load_body
    assert "api.decide_career_record_candidate" not in load_body


def test_records_v2_removes_candidate_review_surface():
    src = source()

    for forbidden in (
        "normalizeCareerRecordCandidateV2",
        "careerRecordCandidatePickerCardHtml",
        "careerRecordCandidateCardHtml",
        "renderCareerRecordCandidatePanel",
        "setCareerRecordCandidateFeedback",
        "decideCareerRecordCandidateFromElement",
        "data-career-record-candidate-id",
        "data-career-record-feedback",
        "data-decision=\"confirm\"",
        "data-decision=\"reject\"",
    ):
        assert forbidden not in src


def test_records_v2_loads_without_candidate_api_dependency():
    src = source()
    load_body = extract_function_body(src, "async function loadCareerRecordsCenter(options)")

    assert "typeof api.get_career_record_catalog !== 'function'" in load_body
    assert "typeof api.get_career_records !== 'function'" in load_body
    assert "get_career_record_candidates" not in load_body
    assert "decide_career_record_candidate" not in load_body
    assert "await api.get_career_records({ sport: selectedSport || 'all' })" in load_body
    assert "state.records = Array.isArray(recordData.records)" in load_body


def test_records_v2_keeps_current_record_picker_and_history_analysis():
    src = source()
    render_body = extract_function_body(src, "function renderCareerRecordsCenter(viewModel)")
    picker_body = extract_function_body(src, "function renderCareerRecordPicker(definitions, records)")

    assert "renderCareerRecordPicker(definitions, records)" in render_body
    assert "careerRecordPickerCardHtml" in picker_body
    assert "loadCareerRecordAnalysis(selectedRecord)" in render_body
    assert "renderCareerRecordAnalysisPanel(selectedRecord" in render_body
    assert "selectedView" not in render_body
