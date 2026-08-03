from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from strength_muscle_map_v1 import (
    MUSCLE_MAP_VERSION,
    MUSCLE_REGIONS,
    STRENGTH_MUSCLE_MAP_V1,
)


def _positive_number(value: Any) -> float | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def _mapping_for_set(item: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    exercise_key = str(item.get("exercise_key") or "").strip()
    if exercise_key in STRENGTH_MUSCLE_MAP_V1:
        return exercise_key, STRENGTH_MUSCLE_MAP_V1[exercise_key]
    category = str(item.get("exercise_category") or "").strip()
    if category in STRENGTH_MUSCLE_MAP_V1:
        return category, STRENGTH_MUSCLE_MAP_V1[category]
    return None, None


def _level(score: float) -> str:
    if score >= 0.66:
        return "high"
    if score >= 0.33:
        return "medium"
    return "low"


def resolve_strength_muscle_heatmap(normalized_sets: Any) -> dict[str, Any]:
    sets = [item for item in normalized_sets if isinstance(item, dict)] if isinstance(normalized_sets, list) else []
    working_sets = [item for item in sets if item.get("set_type") == "working"]
    muscle_scores: dict[str, float] = defaultdict(float)
    muscle_exercises: dict[str, set[str]] = defaultdict(set)
    muscle_working_sets: dict[str, int] = defaultdict(int)
    primary_exercises: dict[str, set[str]] = defaultdict(set)
    secondary_exercises: dict[str, set[str]] = defaultdict(set)
    mapped_working_sets = 0
    all_base_score = 0.0
    mapped_base_score = 0.0

    for item in working_sets:
        reps = _positive_number(item.get("reps"))
        if reps is None:
            continue
        weight = _positive_number(item.get("weight_kg"))
        base_score = reps * weight if weight is not None else reps
        all_base_score += base_score
        mapped_key, mapping = _mapping_for_set(item)
        if mapping is None or mapped_key is None:
            continue
        mapped_working_sets += 1
        mapped_base_score += base_score
        exercise_key = str(item.get("exercise_key") or mapped_key)
        for role in ("primary", "secondary"):
            weights = mapping.get(role) if isinstance(mapping, dict) else None
            if not isinstance(weights, dict):
                continue
            for muscle_id, coefficient in weights.items():
                if muscle_id not in MUSCLE_REGIONS:
                    continue
                coefficient_value = _positive_number(coefficient)
                if coefficient_value is None:
                    continue
                muscle_scores[muscle_id] += base_score * coefficient_value
                muscle_working_sets[muscle_id] += 1
                muscle_exercises[muscle_id].add(exercise_key)
                if role == "primary":
                    primary_exercises[muscle_id].add(exercise_key)
                else:
                    secondary_exercises[muscle_id].add(exercise_key)

    max_score = max(muscle_scores.values(), default=0.0)
    total_muscle_score = sum(muscle_scores.values())
    regions: list[dict[str, Any]] = []
    for muscle_id, meta in MUSCLE_REGIONS.items():
        raw_score = muscle_scores.get(muscle_id, 0.0)
        if raw_score <= 0 or max_score <= 0 or total_muscle_score <= 0:
            continue
        score = raw_score / max_score
        regions.append(
            {
                "id": muscle_id,
                "label": meta["label"],
                "side": meta["side"],
                "raw_score": round(raw_score, 3),
                "score": round(score, 4),
                "level": _level(score),
                "share_pct": round((raw_score / total_muscle_score) * 100.0, 1),
                "working_set_count": muscle_working_sets[muscle_id],
                "exercise_keys": sorted(muscle_exercises[muscle_id]),
                "primary_exercise_keys": sorted(primary_exercises[muscle_id]),
                "secondary_exercise_keys": sorted(secondary_exercises[muscle_id]),
            }
        )

    unmapped_working_sets = len(working_sets) - mapped_working_sets
    mapped_share = (
        round((mapped_base_score / all_base_score) * 100.0, 1)
        if all_base_score > 0
        else None
    )
    return {
        "schema_version": 1,
        "mapping_version": MUSCLE_MAP_VERSION,
        "source": f"fit_set_mesgs + {MUSCLE_MAP_VERSION}",
        "coverage": {
            "working_sets": len(working_sets),
            "mapped_working_sets": mapped_working_sets,
            "unmapped_working_sets": unmapped_working_sets,
            "mapped_volume_share_pct": mapped_share,
        },
        "regions": regions,
    }
