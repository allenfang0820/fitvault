import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "tests" / "fixtures" / "records_center_v2" / "golden_manifest.json"


def load_records_center_v2_golden_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_records_center_v2_golden_manifest_schema_is_stable():
    manifest = load_records_center_v2_golden_manifest()
    assert manifest["manifest_version"].startswith("records-center-v2-golden-fixtures-")
    assert manifest["privacy_contract"]["synthetic_only"] is True
    assert manifest["privacy_contract"]["contains_real_user_data"] is False
    assert manifest["privacy_contract"]["coordinate_system"] == "synthetic_xy_meters"
    assert isinstance(manifest["cases"], list)
    assert len(manifest["cases"]) >= 8

    required_case_fields = {"case_id", "sport", "source_mode", "purpose", "activity", "input", "expected"}
    case_ids = set()
    for case in manifest["cases"]:
        assert required_case_fields <= set(case), case
        assert case["case_id"] not in case_ids
        case_ids.add(case["case_id"])
        assert str(case["activity"]["activity_id"]).startswith("fixture:")
        assert isinstance(case["expected"], dict)


def test_records_center_v2_golden_manifest_covers_required_edge_cases():
    manifest = load_records_center_v2_golden_manifest()
    serialized = json.dumps(manifest, ensure_ascii=False)

    required_tokens = [
        "zero_watts_are_valid",
        "missing_power_stream_sample",
        "power_spike_detected",
        "power_stream_gap",
        "ebike_scope_excluded",
        "elevation_spike_detected",
        "pool_rest_break",
        "pool_length_missing",
        "swim_stroke_unknown",
        "open_water_gps_unreliable",
        "trail_activity_total_candidate_only",
        "trail_max_single_climb",
        "trail_route_best_time",
        "route_segment_pr",
        "pace_gap_curve",
        "real_data_sample_missing",
    ]
    for token in required_tokens:
        assert token in serialized

    sports = {case["sport"] for case in manifest["cases"]}
    assert {"cycling", "hiking", "swimming", "trail_running"} <= sports


def test_records_center_v2_golden_manifest_has_no_sensitive_fields_or_real_paths():
    manifest = load_records_center_v2_golden_manifest()
    serialized = json.dumps(manifest["cases"], ensure_ascii=False).lower()

    forbidden_fragments = [
        "/users/",
        "file://",
        ".fitvault",
        "user_profile.db",
        "storage_ref",
        "device_serial",
        "serial_number",
        "email",
        "password",
        "api_key",
        "token",
        "real_lat",
        "real_lon",
    ]
    for fragment in forbidden_fragments:
        assert fragment not in serialized


def test_records_center_v2_golden_manifest_documents_candidate_only_limits():
    manifest = load_records_center_v2_golden_manifest()
    by_id = {case["case_id"]: case for case in manifest["cases"]}

    assert by_id["pool_swim_missing_pool_length_unknown_stroke"]["expected"]["candidate_only"] is True
    assert by_id["trail_activity_total_candidate_only"]["expected"]["candidate_only"] is True
    assert by_id["trail_activity_total_candidate_only"]["expected"]["route_segment_pr"] is False
    assert by_id["trail_activity_total_candidate_only"]["expected"]["pace_gap_curve"] is False
    assert "must_not_default_pool_length_m" in by_id["pool_swim_missing_pool_length_unknown_stroke"]["expected"]
    assert by_id["open_water_750m_boundary_and_gps_jump"]["expected"]["boundary_is_inclusive"] is True
