from __future__ import annotations

import json
from pathlib import Path

from strength_fit_parser import normalize_strength_messages, probe_strength_messages


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "strength_fit_message_snapshots.json"


def _fixtures() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_probe_distinguishes_structured_and_unstructured_strength() -> None:
    fixtures = _fixtures()
    for name in (
        "structured_full_weight",
        "structured_partial_weight",
        "structured_bodyweight",
    ):
        report = probe_strength_messages(fixtures[name]["raw"])
        assert report["structured_strength"] is True
        assert report["sets"]["valid_active"] > 0

    report = probe_strength_messages(fixtures["unstructured_strength"]["raw"])
    assert report["structured_strength"] is False
    assert report["sets"]["valid_active"] == 0
    assert report["message_counts"]["set_mesgs"] == 0


def test_probe_classifies_weight_coverage_without_inventing_weight() -> None:
    fixtures = _fixtures()
    full = probe_strength_messages(fixtures["structured_full_weight"]["raw"])
    partial = probe_strength_messages(fixtures["structured_partial_weight"]["raw"])
    bodyweight = probe_strength_messages(fixtures["structured_bodyweight"]["raw"])

    assert full["sets"] == {
        "total": 3,
        "active": 2,
        "rest": 1,
        "valid_active": 2,
        "weighted_valid_active": 2,
        "weight_missing_valid_active": 0,
        "total_repetitions": 20,
    }
    assert partial["sets"]["valid_active"] == 3
    assert partial["sets"]["weighted_valid_active"] == 1
    assert partial["sets"]["weight_missing_valid_active"] == 2
    assert bodyweight["sets"]["weighted_valid_active"] == 0
    assert bodyweight["sets"]["weight_missing_valid_active"] == 2


def test_probe_joins_titles_by_exercise_pair_not_message_index() -> None:
    raw = _fixtures()["structured_full_weight"]["raw"]
    report = probe_strength_messages(raw)
    actions = report["exercise_resolution"]["unique_actions"]

    assert report["exercise_resolution"]["sources"] == {"exercise_title": 2}
    assert actions == [
        {
            "category": "squat",
            "exercise_name_code": 62,
            "fit_title": "负重深蹲",
            "resolution_source": "exercise_title",
            "workout_step_index": 0,
        }
    ]
    assert raw["exercise_title_mesgs"][0]["message_index"] == 7


def test_probe_reports_legacy_numeric_fields_without_promoting_them() -> None:
    raw = _fixtures()["structured_partial_weight"]["raw"]
    report = probe_strength_messages(raw)

    assert report["unknown_numeric_fields"]["set_mesgs"] == {"2": 3}
    assert report["exercise_resolution"]["sources"] == {"set_category": 3}
    assert all(
        action["fit_title"] is None
        for action in report["exercise_resolution"]["unique_actions"]
    )


def test_probe_output_is_json_serializable_and_excludes_sensitive_fields() -> None:
    report = probe_strength_messages(_fixtures()["structured_bodyweight"]["raw"])
    encoded = json.dumps(report, ensure_ascii=False)

    assert "2000-01-01T00:00:05Z" not in encoded
    assert "2000-01-01T00:00:00Z" not in encoded
    assert "file_path" not in encoded
    assert "serial_number" not in encoded
    assert "俯卧撑" in encoded


def test_normalizer_resolves_titles_and_excludes_warmup_from_summary() -> None:
    normalized = normalize_strength_messages(
        _fixtures()["structured_full_weight"]["raw"]
    )

    assert normalized["has_structured_sets"] is True
    assert [item["set_type"] for item in normalized["sets"]] == ["warmup", "working"]
    assert normalized["sets"][0]["exercise_key"] == "weighted_squat"
    assert normalized["sets"][0]["exercise_name"] == "负重深蹲"
    assert normalized["summary"] == {
        "schema_version": 1,
        "distinct_exercise_count": 1,
        "structured_set_count": 2,
        "working_set_count": 1,
        "total_reps": 8,
        "total_volume_kg": 480.0,
        "unmapped_set_count": None,
        "weight_missing_set_count": 0,
        "source": "fit_set_mesgs",
    }


def test_normalizer_keeps_partial_weight_and_broad_category_facts() -> None:
    normalized = normalize_strength_messages(
        _fixtures()["structured_partial_weight"]["raw"]
    )

    assert normalized["summary"]["working_set_count"] == 3
    assert normalized["summary"]["total_reps"] == 23
    assert normalized["summary"]["total_volume_kg"] == 400.0
    assert normalized["summary"]["weight_missing_set_count"] == 2
    assert normalized["sets"][0]["exercise_key"] == "pull_up"
    assert normalized["sets"][0]["exercise_name_source"] == "fit_category"
    assert normalized["sets"][0]["exercise_name_code"] is None
    assert normalized["sets"][0]["weight_kg"] is None

    bodyweight = normalize_strength_messages(
        _fixtures()["structured_bodyweight"]["raw"]
    )
    assert bodyweight["summary"]["total_volume_kg"] is None


def test_normalizer_returns_null_payload_for_unstructured_activity() -> None:
    normalized = normalize_strength_messages(
        _fixtures()["unstructured_strength"]["raw"]
    )

    assert normalized == {
        "has_structured_sets": False,
        "sets": None,
        "summary": None,
    }
