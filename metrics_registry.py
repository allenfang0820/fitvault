from __future__ import annotations

from typing import Any

METRICS_REGISTRY: dict[str, dict[str, dict[str, str]]] = {
    "canonical_core": {
        "duration_sec": {"source": "total_timer_time", "unit": "sec"},
        "distance_m":  {"source": "total_distance",    "unit": "m"},
        "avg_hr":      {"source": "avg_heart_rate",    "unit": "bpm"},
        "max_hr":      {"source": "max_heart_rate",    "unit": "bpm"},
        "calories":    {"source": "total_calories",    "unit": "kcal"},
        "gain_m":      {"source": "total_ascent",      "unit": "m"},
        "descent_m":   {"source": "total_descent",     "unit": "m"},
        "max_alt_m":   {"source": "max_altitude",      "unit": "m"},
        "min_alt_m":   {"source": "min_altitude",      "unit": "m"},
        "avg_speed":   {"source": "avg_speed",         "unit": "m/s"},
        "avg_cadence": {"source": "avg_cadence",       "unit": "rpm"},
        "avg_power":   {"source": "avg_power",         "unit": "watts"},
    },
    "session_meta": {
        "start_time":          {"source": "start_time"},
        "start_position_lat":  {"source": "start_position_lat"},
        "start_position_long": {"source": "start_position_long"},
        "sport":               {"source": "sport"},
        "sub_sport":           {"source": "sub_sport"},
    },
    "record_fields": {
        "heart_rate": {"source": "heart_rate", "unit": "bpm"},
        "speed":      {"source": "speed",      "unit": "m/s"},
        "altitude":   {"source": "altitude",   "unit": "m"},
        "distance":   {"source": "distance",   "unit": "m"},
        "cadence":    {"source": "cadence",    "unit": "rpm"},
        "power":      {"source": "power",      "unit": "watts"},
        "temperature":{"source": "temperature", "unit": "C"},
    },
    "lap_fields": {
        "start_time":       {"source": "start_time"},
        "total_timer_time": {"source": "total_timer_time", "unit": "sec"},
        "total_distance":   {"source": "total_distance",   "unit": "m"},
        "avg_heart_rate":   {"source": "avg_heart_rate",   "unit": "bpm"},
        "max_heart_rate":   {"source": "max_heart_rate",   "unit": "bpm"},
        "avg_speed":        {"source": "avg_speed",        "unit": "m/s"},
        "avg_cadence":      {"source": "avg_cadence",      "unit": "rpm"},
        "avg_power":        {"source": "avg_power",        "unit": "watts"},
    },
}

SPORT_ALIASES: dict[str, str] = {
    "run": "running",
    "road_running": "running",
    "trail_run": "trail_running",
    "trail": "trail_running",
    "treadmill": "treadmill_running",
    "indoor_run": "treadmill_running",
    "ride": "cycling",
    "bike": "cycling",
    "road_bike": "road_cycling",
    "road_biking": "road_cycling",
    "mountain_bike": "mountain_biking",
    "mtb": "mountain_biking",
    "indoor_bike": "indoor_cycling",
    "indoor_biking": "indoor_cycling",
    "stationary_bike": "indoor_cycling",
    "e_bike": "e_biking",
    "ebike": "e_biking",
    "electric_bike": "e_biking",
    "walk": "walking",
    "hike": "hiking",
    "mountaineering": "mountaineering",
    "climb": "mountaineering",
    "drive": "driving",
    "car": "driving",
    "auto": "driving",
    "swim": "swimming",
    "pool_swimming": "lap_swimming",
    "open_water_swimming": "open_water",
    "strength": "strength_training",
    "cardio_training": "cardio",
    "stair": "stair_climbing",
    "stairs": "stair_climbing",
    "sup": "stand_up_paddleboarding",
    "standup_paddleboarding": "stand_up_paddleboarding",
    "stand_up_paddle": "stand_up_paddleboarding",
    "paddleboarding": "stand_up_paddleboarding",
}

SPORT_CODE_ALIASES: dict[str, str] = {
    # Internal display ordering fallback. Unknown numeric FIT codes intentionally
    # remain unknown instead of defaulting to running.
    "1": "running",
    "2": "trail_running",
    "3": "cycling",
    "4": "road_cycling",
    "5": "mountain_biking",
    "6": "hiking",
    "7": "mountaineering",
    "8": "walking",
    "9": "swimming",
    "10": "stand_up_paddleboarding",
}

SPORT_DISPLAY_NAMES: dict[str, str] = {
    "running": "Running",
    "trail_running": "Trail Running",
    "treadmill_running": "Treadmill Running",
    "cycling": "Cycling",
    "road_cycling": "Road Cycling",
    "mountain_biking": "Mountain Biking",
    "indoor_cycling": "Indoor Cycling",
    "e_biking": "E-Biking",
    "hiking": "Hiking",
    "mountaineering": "Mountaineering",
    "walking": "Walking",
    "swimming": "Swimming",
    "lap_swimming": "Lap Swimming",
    "open_water": "Open Water Swimming",
    "strength_training": "Strength Training",
    "cardio": "Cardio",
    "breathing": "Breathing",
    "stair_climbing": "Stair Climbing",
    "stand_up_paddleboarding": "Stand Up Paddleboarding",
    "driving": "Driving",
    "generic": "Generic",
    "unknown": "Unknown",
}


REVIEW_MODE_SPORTS: dict[str, frozenset[str]] = {
    "running": frozenset({"running", "trail_running", "treadmill_running"}),
    "cycling": frozenset({
        "cycling",
        "road_cycling",
        "mountain_biking",
        "indoor_cycling",
        "e_biking",
    }),
    "swimming": frozenset({"swimming", "lap_swimming", "open_water"}),
    "general": frozenset({
        "hiking",
        "mountaineering",
        "walking",
        "stand_up_paddleboarding",
    }),
    "not_applicable": frozenset({
        "cardio",
        "training",
        "strength_training",
        "breathing",
        "yoga",
        "pilates",
        "hiit",
        "flexibility_training",
        "stair_climbing",
        "driving",
        "generic",
        "unknown",
    }),
}


def _base_review_capabilities(review_mode: str) -> dict[str, Any]:
    if review_mode == "running":
        return {
            "review_mode": "running",
            "uses_altitude": True,
            "uses_heat": True,
            "uses_power": False,
            "uses_swolf": False,
            "uses_cadence": True,
            "uses_running_durability": True,
            "uses_cycling_power": False,
            "is_applicable": True,
        }
    if review_mode == "cycling":
        return {
            "review_mode": "cycling",
            "uses_altitude": True,
            "uses_heat": True,
            "uses_power": True,
            "uses_swolf": False,
            "uses_cadence": True,
            "uses_running_durability": False,
            "uses_cycling_power": True,
            "is_applicable": True,
        }
    if review_mode == "swimming":
        return {
            "review_mode": "swimming",
            "uses_altitude": False,
            "uses_heat": False,
            "uses_power": False,
            "uses_swolf": True,
            "uses_cadence": False,
            "uses_running_durability": False,
            "uses_cycling_power": False,
            "is_applicable": True,
        }
    if review_mode == "general":
        return {
            "review_mode": "general",
            "uses_altitude": True,
            "uses_heat": True,
            "uses_power": False,
            "uses_swolf": False,
            "uses_cadence": False,
            "uses_running_durability": False,
            "uses_cycling_power": False,
            "is_applicable": True,
        }
    return {
        "review_mode": "not_applicable",
        "uses_altitude": False,
        "uses_heat": False,
        "uses_power": False,
        "uses_swolf": False,
        "uses_cadence": False,
        "uses_running_durability": False,
        "uses_cycling_power": False,
        "is_applicable": False,
    }


def normalize_review_sport_type(value: Any, fallback: str = "unknown") -> str:
    token = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not token:
        return fallback
    if token.isdigit():
        return SPORT_CODE_ALIASES.get(token, fallback)
    return SPORT_ALIASES.get(token, token)


def get_review_mode(sport_type: Any) -> str:
    sport = normalize_review_sport_type(sport_type)
    for mode, sports in REVIEW_MODE_SPORTS.items():
        if sport in sports:
            return mode
    return "not_applicable"


def get_review_capabilities(sport_type: Any) -> dict[str, Any]:
    sport = normalize_review_sport_type(sport_type)
    mode = get_review_mode(sport)
    capabilities = _base_review_capabilities(mode)
    capabilities["sport_type"] = sport
    if sport == "mountain_biking":
        capabilities["uses_altitude"] = True
    if sport == "indoor_cycling":
        capabilities["uses_altitude"] = False
        capabilities["uses_heat"] = False
    return dict(capabilities)


REVIEW_SPORT_CAPABILITY_REGISTRY: dict[str, dict[str, Any]] = {
    sport: get_review_capabilities(sport)
    for sports in REVIEW_MODE_SPORTS.values()
    for sport in sports
}
