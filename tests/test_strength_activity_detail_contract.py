from __future__ import annotations

import json
from unittest import mock

import main
from metrics_registry import METRICS_REGISTRY


def _structured_row() -> dict:
    sets = [
        {
            "set_index": 1,
            "exercise_key": "weighted_squat",
            "exercise_name": "负重深蹲",
            "exercise_name_source": "fit_title",
            "exercise_category": "squat",
            "set_type": "warmup",
            "reps": 10,
            "weight_kg": 30.0,
            "duration_sec": 30.0,
        },
        {
            "set_index": 2,
            "exercise_key": "weighted_squat",
            "exercise_name": "负重深蹲",
            "exercise_name_source": "fit_title",
            "exercise_category": "squat",
            "set_type": "working",
            "reps": 8,
            "weight_kg": 50.0,
            "duration_sec": 28.0,
        },
        {
            "set_index": 3,
            "exercise_key": "push_up",
            "exercise_name": "俯卧撑",
            "exercise_name_source": "fit_title",
            "exercise_category": "push_up",
            "set_type": "working",
            "reps": 10,
            "weight_kg": None,
            "duration_sec": 20.0,
        },
        {
            "set_index": 4,
            "exercise_key": "push_up",
            "exercise_name": "俯卧撑",
            "exercise_name_source": "fit_title",
            "exercise_category": "push_up",
            "set_type": "working",
            "reps": 7,
            "weight_kg": None,
            "duration_sec": 18.0,
        },
    ]
    summary = {
        "schema_version": 1,
        "distinct_exercise_count": 2,
        "structured_set_count": 4,
        "working_set_count": 3,
        "total_reps": 25,
        "total_volume_kg": 400.0,
        "unmapped_set_count": 0,
        "weight_missing_set_count": 2,
        "source": "fit_set_mesgs",
    }
    heatmap = {
        "schema_version": 1,
        "mapping_version": "strength_muscle_map_v1",
        "coverage": {
            "working_sets": 3,
            "mapped_working_sets": 3,
            "unmapped_working_sets": 0,
            "mapped_volume_share_pct": 100.0,
        },
        "regions": [
            {
                "id": "quadriceps",
                "label": "股四头肌",
                "side": "front",
                "score": 1.0,
                "level": "high",
                "share_pct": 75.0,
                "working_set_count": 1,
                "exercise_keys": ["weighted_squat"],
                "primary_exercise_keys": ["weighted_squat"],
                "secondary_exercise_keys": [],
            },
            {
                "id": "chest",
                "label": "胸部",
                "side": "front",
                "score": 0.2,
                "level": "low",
                "share_pct": 15.0,
                "working_set_count": 2,
                "exercise_keys": ["push_up"],
                "primary_exercise_keys": ["push_up"],
                "secondary_exercise_keys": [],
            },
            {
                "id": "triceps",
                "label": "肱三头肌",
                "side": "back",
                "score": 0.1,
                "level": "low",
                "share_pct": 10.0,
                "working_set_count": 2,
                "exercise_keys": ["push_up"],
                "primary_exercise_keys": [],
                "secondary_exercise_keys": ["push_up"],
            },
        ],
    }
    return {
        "id": 42,
        "filename": "strength.fit",
        "file_name": "strength.fit",
        "title": "力量训练",
        "title_source": "fit",
        "sport_type": "strength_training",
        "sub_sport_type": "strength_training",
        "duration_sec": 1800,
        "avg_hr": 120,
        "calories": 260,
        "strength_sets_json": json.dumps(sets, ensure_ascii=False),
        "strength_summary_json": json.dumps(summary, ensure_ascii=False),
        "muscle_heatmap_json": json.dumps(heatmap, ensure_ascii=False),
        "processing_status": "ready",
    }


def test_structured_strength_switches_overview_contract() -> None:
    record = main._build_activity_detail_summary_from_row(_structured_row())
    detail = record["detail"]

    assert detail["detail_surface_mode"] == "strength"
    assert detail["primary_visual"] == "strength_muscle_map"
    assert detail["split_section"] == "strength_sets"
    assert detail["overview_capabilities"]["has_structured_sets"] is True
    assert [item["field"] for item in detail["overview_metrics"]] == [
        "duration_sec",
        "strength_exercise_count",
        "strength_working_set_count",
        "strength_total_reps",
        "strength_total_volume_kg",
        "avg_hr",
    ]


def test_strength_payload_groups_sets_and_keeps_missing_weight_null() -> None:
    strength = main._build_activity_detail_summary_from_row(_structured_row())["detail"][
        "strength"
    ]
    squat, push_up = strength["exercises"]

    assert squat["working_set_count"] == 1
    assert squat["volume_kg"] == 400.0
    assert squat["primary_muscles"] == ["股四头肌"]
    assert push_up["working_set_count"] == 2
    assert push_up["volume_kg"] is None
    assert push_up["primary_muscles"] == ["胸部"]
    assert push_up["secondary_muscles"] == ["肱三头肌"]
    assert [item["weight_kg"] for item in push_up["sets"]] == [None, None]


def test_strength_payload_localizes_known_english_fit_titles() -> None:
    row = _structured_row()
    sets = json.loads(row["strength_sets_json"])
    sets[0]["exercise_key"] = "curl"
    sets[0]["exercise_name"] = "Curl"
    sets[0]["exercise_category"] = "curl"
    sets[0]["set_type"] = "working"
    sets[1]["exercise_key"] = "sit_up"
    sets[1]["exercise_name"] = "Sit Up"
    sets[1]["exercise_category"] = "sit_up"
    row["strength_sets_json"] = json.dumps(sets, ensure_ascii=False)
    row["muscle_heatmap_json"] = json.dumps(
        {
            "schema_version": 1,
            "mapping_version": "strength_muscle_map_v1",
            "coverage": {
                "working_sets": 4,
                "mapped_working_sets": 2,
                "unmapped_working_sets": 2,
                "mapped_volume_share_pct": 100.0,
            },
            "regions": [],
        },
        ensure_ascii=False,
    )

    exercises = main._build_activity_detail_summary_from_row(row)["detail"]["strength"]["exercises"]

    assert [item["exercise_name"] for item in exercises[:2]] == ["弯举", "仰卧起坐"]
    assert [item["exercise_raw_name"] for item in exercises[:2]] == ["Curl", "Sit Up"]


def test_summary_and_full_detail_share_structured_strength_state() -> None:
    row = _structured_row()
    summary = main._build_activity_detail_summary_from_row(row)["detail"]
    full = main._build_record_from_row(main.Api(), row, 0)["detail"]

    for key in (
        "primary_visual",
        "split_section",
        "overview_capabilities",
        "strength",
        "strength_materialization",
    ):
        assert full[key] == summary[key]
    assert full["laps"] == []
    assert full["lap_columns"] == []


def test_missing_or_malformed_materialized_data_keeps_limited_contract() -> None:
    for row in (
        {"sport_type": "strength_training", "duration_sec": 1200},
        {
            "sport_type": "strength_training",
            "duration_sec": 1200,
            "strength_sets_json": "not-json",
            "strength_summary_json": "{}",
        },
    ):
        detail = main._build_activity_detail_summary_from_row(row)["detail"]
        assert detail["primary_visual"] == "strength_limited"
        assert detail["split_section"] == "strength_unavailable"
        assert detail["overview_capabilities"]["has_structured_sets"] is False
        assert "strength" not in detail


def test_strength_materialization_five_state_contract_is_normalized_and_sanitized() -> None:
    structured = _structured_row()
    assert main._build_activity_detail_summary_from_row(structured)["detail"][
        "strength_materialization"
    ] == {
        "version": 1,
        "status": "materialized",
        "can_retry": False,
        "message_code": "strength_materialization_ready",
    }

    cases = (
        ({}, "pending", False, "strength_materialization_pending"),
        (
            {"strength_materialization_version": 1, "strength_materialization_status": "unstructured"},
            "unstructured",
            False,
            "strength_sets_not_recorded",
        ),
        (
            {"strength_materialization_version": 1, "strength_materialization_status": "source_missing"},
            "source_missing",
            True,
            "strength_source_unavailable",
        ),
        (
            {
                "strength_materialization_version": 1,
                "strength_materialization_status": "failed",
                "strength_materialization_error": "/private/user/path.fit: decoder traceback",
            },
            "failed",
            True,
            "strength_materialization_failed",
        ),
        (
            {"strength_materialization_version": 0, "strength_materialization_status": "failed"},
            "pending",
            False,
            "strength_materialization_pending",
        ),
    )
    for extra, status, can_retry, message_code in cases:
        row = {"sport_type": "strength_training", "duration_sec": 1200, **extra}
        materialization = main._build_activity_detail_summary_from_row(row)["detail"][
            "strength_materialization"
        ]
        assert materialization == {
            "version": 1,
            "status": status,
            "can_retry": can_retry,
            "message_code": message_code,
        }
        assert "private" not in json.dumps(materialization)


def test_non_strength_detail_does_not_expose_strength_materialization() -> None:
    detail = main._build_activity_detail_summary_from_row(
        {
            "sport_type": "running",
            "duration_sec": 1200,
            "strength_materialization_version": 1,
            "strength_materialization_status": "failed",
            "strength_materialization_error": "internal",
        }
    )["detail"]
    assert "strength_materialization" not in detail


def test_detail_contract_never_reads_fit_raw() -> None:
    with mock.patch.object(
        main.FITCoreEngine,
        "parse_fit_file_raw",
        side_effect=AssertionError("detail view must use materialized JSON"),
    ):
        detail = main._build_activity_detail_summary_from_row(_structured_row())["detail"]
    assert detail["strength"]["summary"]["working_set_count"] == 3


def test_strength_metric_fields_are_registered() -> None:
    assert set(METRICS_REGISTRY["strength_fields"]) == {
        "strength_exercise_count",
        "strength_working_set_count",
        "strength_total_reps",
        "strength_total_volume_kg",
    }
