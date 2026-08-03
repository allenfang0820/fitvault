from __future__ import annotations

from typing import Final


MUSCLE_MAP_VERSION: Final[str] = "strength_muscle_map_v1"

MUSCLE_REGIONS: Final[dict[str, dict[str, str]]] = {
    "chest": {"label": "胸部", "side": "front"},
    "lats": {"label": "背阔肌", "side": "back"},
    "upper_back": {"label": "上背", "side": "back"},
    "anterior_deltoids": {"label": "前三角肌", "side": "front"},
    "lateral_rear_deltoids": {"label": "侧/后束三角肌", "side": "both"},
    "biceps": {"label": "肱二头肌", "side": "front"},
    "triceps": {"label": "肱三头肌", "side": "back"},
    "core": {"label": "核心", "side": "front"},
    "glutes": {"label": "臀部", "side": "back"},
    "quadriceps": {"label": "股四头肌", "side": "front"},
    "hamstrings": {"label": "腘绳肌", "side": "back"},
    "calves": {"label": "小腿", "side": "back"},
}

STRENGTH_EXERCISE_LABELS_ZH: Final[dict[str, str]] = {
    "curl": "弯举",
    "bench_press": "卧推",
    "lateral_raise": "侧平举",
    "row": "划船",
    "seated_cable_row": "坐姿绳索划船",
    "pull_up": "引体向上",
    "sit_up": "仰卧起坐",
    "squat": "深蹲",
    "weighted_squat": "负重深蹲",
    "dumbbell_kickback": "哑铃臂屈伸",
    "push_up": "俯卧撑",
    "barbell_deadlift": "杠铃硬拉",
    "deadlift": "硬拉",
    "triceps_extension": "肱三头肌伸展",
    "dumbbell_flye": "哑铃飞鸟",
    "flye": "飞鸟",
    "burpee": "波比跳",
    "cable_crossover": "绳索夹胸",
    "jumping_jacks": "开合跳",
    "mountain_climber": "登山跑",
    "shoulder_press": "肩推",
    "jump_rope": "跳绳",
}


STRENGTH_MUSCLE_MAP_V1: Final[dict[str, dict[str, dict[str, float]]]] = {
    "curl": {
        "primary": {"biceps": 1.0},
        "secondary": {},
    },
    "bench_press": {
        "primary": {"chest": 1.0},
        "secondary": {"triceps": 0.45, "anterior_deltoids": 0.35},
    },
    "lateral_raise": {
        "primary": {"lateral_rear_deltoids": 1.0},
        "secondary": {"anterior_deltoids": 0.2},
    },
    "row": {
        "primary": {"upper_back": 1.0, "lats": 0.7},
        "secondary": {"biceps": 0.4, "lateral_rear_deltoids": 0.25},
    },
    "seated_cable_row": {
        "primary": {"upper_back": 1.0, "lats": 0.7},
        "secondary": {"biceps": 0.4, "lateral_rear_deltoids": 0.25},
    },
    "pull_up": {
        "primary": {"lats": 1.0},
        "secondary": {"upper_back": 0.45, "biceps": 0.5, "core": 0.15},
    },
    "sit_up": {
        "primary": {"core": 1.0},
        "secondary": {},
    },
    "squat": {
        "primary": {"quadriceps": 1.0, "glutes": 0.7},
        "secondary": {"hamstrings": 0.35, "core": 0.2},
    },
    "weighted_squat": {
        "primary": {"quadriceps": 1.0, "glutes": 0.7},
        "secondary": {"hamstrings": 0.35, "core": 0.2},
    },
    "dumbbell_kickback": {
        "primary": {"triceps": 1.0},
        "secondary": {},
    },
    "push_up": {
        "primary": {"chest": 1.0},
        "secondary": {"triceps": 0.45, "anterior_deltoids": 0.3, "core": 0.2},
    },
    "barbell_deadlift": {
        "primary": {"hamstrings": 1.0, "glutes": 0.8},
        "secondary": {"upper_back": 0.35, "core": 0.3},
    },
    "deadlift": {
        "primary": {"hamstrings": 1.0, "glutes": 0.8},
        "secondary": {"upper_back": 0.35, "core": 0.3},
    },
    "triceps_extension": {
        "primary": {"triceps": 1.0},
        "secondary": {},
    },
    "dumbbell_flye": {
        "primary": {"chest": 1.0},
        "secondary": {"anterior_deltoids": 0.25},
    },
    "flye": {
        "primary": {"chest": 1.0},
        "secondary": {"anterior_deltoids": 0.25},
    },
    "burpee": {
        "primary": {"quadriceps": 0.65, "core": 0.3},
        "secondary": {"glutes": 0.4, "chest": 0.25, "calves": 0.2, "triceps": 0.15},
    },
    "cable_crossover": {
        "primary": {"chest": 1.0},
        "secondary": {"anterior_deltoids": 0.2},
    },
    "jumping_jacks": {
        "primary": {"calves": 0.45, "lateral_rear_deltoids": 0.35},
        "secondary": {"quadriceps": 0.2},
    },
    "mountain_climber": {
        "primary": {"core": 1.0},
        "secondary": {"quadriceps": 0.35, "anterior_deltoids": 0.2},
    },
    "shoulder_press": {
        "primary": {"anterior_deltoids": 1.0, "lateral_rear_deltoids": 0.65},
        "secondary": {"triceps": 0.45, "upper_back": 0.15},
    },
    "jump_rope": {
        "primary": {"calves": 1.0},
        "secondary": {"quadriceps": 0.2},
    },
}
