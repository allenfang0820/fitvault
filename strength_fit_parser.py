from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any


STRENGTH_MESSAGE_KEYS = (
    "set_mesgs",
    "exercise_title_mesgs",
    "workout_step_mesgs",
)


def _as_messages(value: Any) -> list[dict[Any, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _clean_token(value: Any) -> str | None:
    if value is None:
        return None
    token = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    token = re.sub(r"[^a-z0-9_]+", "", token)
    return token or None


def _clean_title(value: Any) -> str | None:
    candidates = value[:1] if isinstance(value, list) else [value]
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        text = re.sub(r"[\x00-\x1f\x7f]", "", candidate)
        text = re.sub(r"\s+", " ", text).strip()
        if text and len(text) <= 80 and re.search(r"[A-Za-z0-9\u3400-\u9fff]", text):
            return text
    return None


def _first_value(value: Any) -> Any:
    if isinstance(value, list):
        for item in value:
            if item is not None and item != "":
                return item
        return None
    return value


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _number_or_none(value: Any) -> float | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _is_valid_active_set(message: dict[Any, Any]) -> bool:
    set_type = _clean_token(message.get("set_type"))
    repetitions = _int_or_none(message.get("repetitions"))
    return set_type == "active" and repetitions is not None and repetitions > 0


def _field_availability(messages: list[dict[Any, Any]]) -> dict[str, dict[str, float | int]]:
    counts: Counter[str] = Counter()
    total = len(messages)
    for message in messages:
        for key, value in message.items():
            if not isinstance(key, str) or key.isdigit() or value is None:
                continue
            counts[key] += 1
    return {
        key: {
            "count": count,
            "pct": round((count / total) * 100.0, 1) if total else 0.0,
        }
        for key, count in sorted(counts.items())
    }


def _unknown_numeric_field_counts(messages: list[dict[Any, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for message in messages:
        for key, value in message.items():
            key_text = str(key)
            if key_text.isdigit() and value is not None:
                counts[key_text] += 1
    return dict(sorted(counts.items(), key=lambda item: int(item[0])))


def _exercise_pair(message: dict[Any, Any]) -> tuple[str | None, int | None]:
    category = _clean_token(_first_value(message.get("exercise_category")))
    exercise_name = _int_or_none(_first_value(message.get("exercise_name")))
    return category, exercise_name


def _set_exercise_pair(message: dict[Any, Any]) -> tuple[str | None, int | None]:
    raw_categories = message.get("category")
    categories = raw_categories if isinstance(raw_categories, list) else [raw_categories]
    subtype_value = message.get("category_subtype")
    if subtype_value is None:
        subtype_value = message.get(2, message.get("2"))
    subtypes = subtype_value if isinstance(subtype_value, list) else [subtype_value]
    for index, raw_category in enumerate(categories):
        category = _clean_token(raw_category)
        if not category or category == "unknown":
            continue
        subtype = subtypes[index] if index < len(subtypes) else None
        return category, _int_or_none(subtype)
    return None, None


def _title_index(
    title_messages: list[dict[Any, Any]],
) -> dict[tuple[str, int], str]:
    titles: dict[tuple[str, int], str] = {}
    for message in title_messages:
        category, exercise_name = _exercise_pair(message)
        title = _clean_title(message.get("wkt_step_name"))
        if category and exercise_name is not None and title:
            titles[(category, exercise_name)] = title
    return titles


def _step_index(
    step_messages: list[dict[Any, Any]],
) -> dict[int, dict[Any, Any]]:
    steps: dict[int, dict[Any, Any]] = {}
    for message in step_messages:
        message_index = _int_or_none(message.get("message_index"))
        if message_index is not None:
            steps[message_index] = message
    return steps


def _action_ref(
    message: dict[Any, Any],
    steps: dict[int, dict[Any, Any]],
    titles: dict[tuple[str, int], str],
) -> dict[str, Any]:
    workout_step_index = _int_or_none(message.get("wkt_step_index"))
    step = steps.get(workout_step_index) if workout_step_index is not None else None
    if step is not None:
        category, exercise_name = _exercise_pair(step)
        pair = (category, exercise_name)
        title = titles.get(pair) if category and exercise_name is not None else None
        source = "exercise_title" if title else "workout_step"
    else:
        category, exercise_name = _set_exercise_pair(message)
        title = None
        source = "set_category" if category else "unknown"
    return {
        "category": category,
        "exercise_name_code": exercise_name,
        "fit_title": title,
        "resolution_source": source,
        "workout_step_index": workout_step_index,
    }


def _profile_exercise_key(category: str | None, exercise_name: int | None) -> str | None:
    if not category or exercise_name is None:
        return None
    try:
        from garmin_fit_sdk.profile import Profile

        exercise_types = Profile.get("types", {}).get(f"{category}_exercise_name", {})
        return _clean_token(exercise_types.get(exercise_name))
    except (ImportError, AttributeError, TypeError):
        return None


def _display_name(token: str | None) -> str:
    if not token:
        return "未识别动作"
    return token.replace("_", " ").title()


def _normalized_action(
    message: dict[Any, Any],
    steps: dict[int, dict[Any, Any]],
    titles: dict[tuple[str, int], str],
) -> dict[str, Any]:
    ref = _action_ref(message, steps, titles)
    category = ref.get("category")
    exercise_name_code = ref.get("exercise_name_code")
    if (
        ref.get("resolution_source") == "set_category"
        and message.get("category_subtype") is None
    ):
        exercise_name_code = None
    profile_key = _profile_exercise_key(category, exercise_name_code)
    exercise_key = profile_key or category
    fit_title = ref.get("fit_title")
    if fit_title:
        exercise_name = fit_title
        name_source = "fit_title"
    elif profile_key:
        exercise_name = _display_name(profile_key)
        name_source = "fit_profile"
    elif category:
        exercise_name = _display_name(category)
        name_source = "fit_category"
    else:
        exercise_name = "未识别动作"
        name_source = "unknown"
    return {
        "exercise_key": exercise_key,
        "exercise_name": exercise_name,
        "exercise_name_source": name_source,
        "exercise_category": category,
        "exercise_name_code": exercise_name_code,
        "workout_step_index": ref.get("workout_step_index"),
    }


def _normalized_set_type(
    message: dict[Any, Any],
    steps: dict[int, dict[Any, Any]],
) -> str:
    workout_step_index = _int_or_none(message.get("wkt_step_index"))
    step = steps.get(workout_step_index) if workout_step_index is not None else None
    intensity = _clean_token(step.get("intensity")) if step else None
    if intensity in {"warmup", "warm_up"}:
        return "warmup"
    if intensity in {"cooldown", "cool_down"}:
        return "cooldown"
    if intensity in {"recovery", "rest"}:
        return "recovery"
    return "working"


def normalize_strength_messages(raw_messages: Any) -> dict[str, Any]:
    """Normalize persisted strength facts from decoded Garmin FIT messages."""

    raw = raw_messages if isinstance(raw_messages, dict) else {}
    set_messages = _as_messages(raw.get("set_mesgs"))
    title_messages = _as_messages(raw.get("exercise_title_mesgs"))
    step_messages = _as_messages(raw.get("workout_step_mesgs"))
    valid_sets = [message for message in set_messages if _is_valid_active_set(message)]
    if not valid_sets:
        return {
            "has_structured_sets": False,
            "sets": None,
            "summary": None,
        }

    steps = _step_index(step_messages)
    titles = _title_index(title_messages)
    normalized_sets: list[dict[str, Any]] = []
    for display_index, message in enumerate(valid_sets, start=1):
        action = _normalized_action(message, steps, titles)
        weight = _number_or_none(message.get("weight"))
        weight_kg = weight if weight is not None and weight > 0 else None
        normalized_sets.append(
            {
                "set_index": display_index,
                "source_set_index": _int_or_none(message.get("message_index")),
                **action,
                "set_type": _normalized_set_type(message, steps),
                "reps": _int_or_none(message.get("repetitions")),
                "weight_kg": weight_kg,
                "duration_sec": _number_or_none(message.get("duration")),
                "source": "fit_set_mesgs",
            }
        )

    working_sets = [item for item in normalized_sets if item["set_type"] == "working"]
    distinct_actions = {
        item.get("exercise_key") or "unknown"
        for item in working_sets
    }
    total_reps = sum(item.get("reps") or 0 for item in working_sets)
    weighted_working_sets = [
        item for item in working_sets if item.get("weight_kg") is not None
    ]
    total_volume_kg = sum(
        (item.get("reps") or 0) * item["weight_kg"]
        for item in weighted_working_sets
    )
    summary = {
        "schema_version": 1,
        "distinct_exercise_count": len(distinct_actions),
        "structured_set_count": len(normalized_sets),
        "working_set_count": len(working_sets),
        "total_reps": total_reps,
        "total_volume_kg": round(total_volume_kg, 3) if weighted_working_sets else None,
        "unmapped_set_count": None,
        "weight_missing_set_count": sum(
            1 for item in working_sets if item.get("weight_kg") is None
        ),
        "source": "fit_set_mesgs",
    }
    return {
        "has_structured_sets": True,
        "sets": normalized_sets,
        "summary": summary,
    }


def probe_strength_messages(raw_messages: Any) -> dict[str, Any]:
    """Return a sanitized structural report for Garmin strength FIT messages.

    The report intentionally excludes timestamps, file paths, device identifiers,
    unknown field payloads, and raw message bodies. It is a discovery contract,
    not the production strength normalizer.
    """

    raw = raw_messages if isinstance(raw_messages, dict) else {}
    sets = _as_messages(raw.get("set_mesgs"))
    titles = _as_messages(raw.get("exercise_title_mesgs"))
    steps = _as_messages(raw.get("workout_step_mesgs"))
    valid_sets = [message for message in sets if _is_valid_active_set(message)]

    weighted_count = 0
    total_repetitions = 0
    for message in valid_sets:
        total_repetitions += _int_or_none(message.get("repetitions")) or 0
        weight = _number_or_none(message.get("weight"))
        if weight is not None and weight > 0:
            weighted_count += 1

    step_lookup = _step_index(steps)
    title_lookup = _title_index(titles)
    action_refs = [
        _action_ref(message, step_lookup, title_lookup)
        for message in valid_sets
    ]
    resolution_counts = Counter(ref["resolution_source"] for ref in action_refs)

    unique_action_refs: list[dict[str, Any]] = []
    seen_actions: set[tuple[Any, ...]] = set()
    for ref in action_refs:
        identity = (
            ref.get("category"),
            ref.get("exercise_name_code"),
            ref.get("fit_title"),
            ref.get("resolution_source"),
        )
        if identity in seen_actions:
            continue
        seen_actions.add(identity)
        unique_action_refs.append(ref)

    message_groups = {
        "set_mesgs": sets,
        "exercise_title_mesgs": titles,
        "workout_step_mesgs": steps,
    }
    return {
        "probe_version": 1,
        "message_counts": {
            key: len(message_groups[key])
            for key in STRENGTH_MESSAGE_KEYS
        },
        "structured_strength": bool(valid_sets),
        "sets": {
            "total": len(sets),
            "active": sum(
                1 for message in sets if _clean_token(message.get("set_type")) == "active"
            ),
            "rest": sum(
                1 for message in sets if _clean_token(message.get("set_type")) == "rest"
            ),
            "valid_active": len(valid_sets),
            "weighted_valid_active": weighted_count,
            "weight_missing_valid_active": len(valid_sets) - weighted_count,
            "total_repetitions": total_repetitions,
        },
        "field_availability": {
            key: _field_availability(message_groups[key])
            for key in STRENGTH_MESSAGE_KEYS
        },
        "unknown_numeric_fields": {
            key: _unknown_numeric_field_counts(message_groups[key])
            for key in STRENGTH_MESSAGE_KEYS
        },
        "exercise_resolution": {
            "title_pair_count": len(title_lookup),
            "sources": dict(sorted(resolution_counts.items())),
            "unique_actions": unique_action_refs,
        },
    }
