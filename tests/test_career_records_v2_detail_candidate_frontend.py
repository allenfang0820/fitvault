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


def test_records_v2_detail_panel_uses_backend_detail_viewmodel():
    src = source()
    load_body = extract_function_body(src, "async function loadCareerRecordAnalysis(record)")
    detail_body = extract_function_body(src, "function careerRecordDetailPanelHtml(record, detail)")

    assert "api.get_career_record_detail" in load_body
    assert "record_id: record.id" in load_body
    assert "rawDetail.record" in detail_body
    assert "activity_summary" in detail_body
    assert "detailRecord.improvement" in detail_body
    assert "detailRecord.scope.labels" in detail_body
    assert "detailRecord.sourceModeLabel" in detail_body
    assert "careerRecordRangeSummary(detailRecord.range)" in detail_body
    assert "careerRecordActivityActionHtml(detailRecord.detailLink" in detail_body


def test_records_v2_activity_jump_uses_career_detail_link_contract():
    src = source()
    card_body = extract_function_body(src, "function careerRecordCurrentCardHtml(record, index)")
    action_body = extract_function_body(src, "function careerRecordActivityActionHtml(detailLink, label)")
    jump_body = extract_function_body(src, "function openCareerRecordActivityFromElement(event, el)")
    shared_jump = extract_function_body(src, "function openCareerActivityDetailFromElement(el)")

    assert "record.detailLink.activityId" in card_body
    assert "record.detailLink.source || 'career'" in card_body
    assert "normalizeCareerDetailLink(detailLink)" in action_body
    assert 'data-career-source="' in action_body
    assert "openCareerActivityDetailFromElement(el)" in jump_body
    assert "source !== 'career'" in shared_jump
    assert "openActivityDetailModal(activityId)" in shared_jump


def test_records_v2_candidate_cards_show_backend_reason_confidence_and_actions():
    src = source()
    normalize_body = extract_function_body(src, "function normalizeCareerRecordCandidateV2(item)")
    card_body = extract_function_body(src, "function careerRecordCandidateCardHtml(candidate)")

    assert "quality.reason_codes" in normalize_body
    assert "quality.confidence" in normalize_body
    assert "quality.confidence_band" in normalize_body
    assert "quality.can_user_confirm !== false" in normalize_body
    assert "normalizeCareerDetailLink(item.detail_link)" in normalize_body
    assert "candidate.reasonCodes" in card_body
    assert "candidate.confidence" in card_body
    assert "data-decision=\"confirm\"" in card_body
    assert "data-decision=\"reject\"" in card_body
    assert "data-career-record-feedback" in card_body


def test_records_v2_candidate_decision_uses_v2_api_and_fixed_payload_only():
    src = source()
    decide_body = extract_function_body(src, "async function decideCareerRecordCandidateFromElement(event, el)")

    assert "api.decide_career_record_candidate" in decide_body
    assert "api.decide_career_pb_candidate" not in decide_body
    assert "{ candidate_id: candidateId, decision: decision }" in decide_body
    assert "btn.disabled = true" in decide_body
    assert "setAttribute('aria-busy', 'true')" in decide_body
    assert "loadCareerRecordsCenter({ refresh: true })" in decide_body

    forbidden_mutable_fields = [
        "metric:",
        "value:",
        "distance",
        "elapsed",
        "power",
        "scope:",
        "range:",
        "reason",
        "evidence",
        "activity_id:",
        "record_key:",
    ]
    payload_slice = decide_body[decide_body.find("api.decide_career_record_candidate"):]
    for token in forbidden_mutable_fields:
        assert token not in payload_slice


def test_records_v2_range_summary_is_whitelisted_and_has_no_raw_tokens():
    src = source()
    range_body = extract_function_body(src, "function careerRecordRangeSummary(range)")

    assert "const allowed =" in range_body
    assert "start_sec" in range_body
    assert "end_sec" in range_body
    assert "segment_key" in range_body
    for token in ("track", "raw", "gps", "polyline", "power_stream", "file_path", "sqlite"):
        assert token not in range_body.lower()
