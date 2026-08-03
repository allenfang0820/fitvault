from __future__ import annotations

from strength_muscle_map_v1 import MUSCLE_REGIONS, STRENGTH_MUSCLE_MAP_V1
from strength_muscle_resolver import resolve_strength_muscle_heatmap


def _set(
    exercise_key: str | None,
    reps: int,
    weight_kg: float | None,
    *,
    category: str | None = None,
    set_type: str = "working",
) -> dict:
    return {
        "exercise_key": exercise_key,
        "exercise_category": category,
        "set_type": set_type,
        "reps": reps,
        "weight_kg": weight_kg,
    }


def test_mapping_references_only_frozen_regions_and_valid_weights() -> None:
    for mapping in STRENGTH_MUSCLE_MAP_V1.values():
        assert set(mapping) == {"primary", "secondary"}
        assert not (set(mapping["primary"]) & set(mapping["secondary"]))
        for role in ("primary", "secondary"):
            for muscle_id, weight in mapping[role].items():
                assert muscle_id in MUSCLE_REGIONS
                assert 0 < weight <= 1.0


def test_weighted_and_bodyweight_sets_use_separate_base_score_rules() -> None:
    heatmap = resolve_strength_muscle_heatmap(
        [
            _set("weighted_squat", 10, 50.0),
            _set("push_up", 20, None),
        ]
    )
    regions = {region["id"]: region for region in heatmap["regions"]}

    assert heatmap["coverage"] == {
        "working_sets": 2,
        "mapped_working_sets": 2,
        "unmapped_working_sets": 0,
        "mapped_volume_share_pct": 100.0,
    }
    assert regions["quadriceps"]["raw_score"] == 500.0
    assert regions["quadriceps"]["working_set_count"] == 1
    assert regions["chest"]["raw_score"] == 20.0
    assert regions["quadriceps"]["level"] == "high"
    assert regions["chest"]["level"] == "low"


def test_warmup_and_unknown_actions_do_not_pollute_regions() -> None:
    heatmap = resolve_strength_muscle_heatmap(
        [
            _set("bench_press", 10, 60.0, set_type="warmup"),
            _set("custom_unknown", 12, 20.0),
            _set("pull_up", 8, None),
        ]
    )
    exercise_keys = {
        key
        for region in heatmap["regions"]
        for key in region["exercise_keys"]
    }

    assert heatmap["coverage"]["working_sets"] == 2
    assert heatmap["coverage"]["mapped_working_sets"] == 1
    assert heatmap["coverage"]["unmapped_working_sets"] == 1
    assert heatmap["coverage"]["mapped_volume_share_pct"] == 3.2
    assert exercise_keys == {"pull_up"}


def test_broad_category_fallback_is_controlled_and_traceable() -> None:
    heatmap = resolve_strength_muscle_heatmap(
        [_set("unresolved_row_code", 10, 40.0, category="row")]
    )

    assert heatmap["coverage"]["mapped_working_sets"] == 1
    upper_back = next(region for region in heatmap["regions"] if region["id"] == "upper_back")
    assert upper_back["primary_exercise_keys"] == ["unresolved_row_code"]


def test_all_unmapped_sets_return_computed_empty_heatmap_contract() -> None:
    heatmap = resolve_strength_muscle_heatmap(
        [_set("unknown_one", 10, None), _set(None, 8, None)]
    )

    assert heatmap["coverage"] == {
        "working_sets": 2,
        "mapped_working_sets": 0,
        "unmapped_working_sets": 2,
        "mapped_volume_share_pct": 0.0,
    }
    assert heatmap["regions"] == []
