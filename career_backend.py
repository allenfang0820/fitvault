"""Athlete Career System (ACS) backend boundary.

ACS is the derived career-organization layer for FitVault. It may organize
Activity-backed semantic events, but it must not become a second fact store.

Hard boundaries:
- Activity remains the only source of truth.
- Resolver code owns semantic recognition; ACS owns long-term organization.
- ACS tables store derived indexes and display metadata only.
- ACS must not read raw FIT files, raw track points, or full activity records.
- AI-facing ACS features must consume a compact Career Snapshot, never local
  file paths, SQLite schema, raw FIT records, points, or track_json.
"""

from __future__ import annotations

import base64
import calendar
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import profile_backend

CAREER_SCHEMA_VERSION = "2026-07-08.phase6.01"

CAREER_BUSINESS_TABLES = (
    "career_race_events",
    "career_pb_records",
    "career_achievement_events",
    "career_memory_items",
    "career_snapshots",
    "career_event_candidates",
)

CAREER_EMPTY_STATUS_MESSAGE = "运动生涯数据将在赛事、PB 与成就解析后生成"
CAREER_TIMELINE_EMPTY_STATUS_MESSAGE = "时间轴将在 ACS 派生事件生成后展示"
CAREER_RACES_EMPTY_STATUS_MESSAGE = "赛事档案将在 Race Resolver 识别正式赛事后展示"
CAREER_RACES_READY_STATUS_MESSAGE = "赛事档案已生成"
CAREER_RACE_MAP_EMPTY_STATUS_MESSAGE = "赛事足迹将在有赛事与安全起点坐标后展示"
CAREER_RACE_MAP_READY_STATUS_MESSAGE = "赛事足迹已生成"
CAREER_PB_EMPTY_STATUS_MESSAGE = "PB 记录将在 PB Resolver 识别后展示"
CAREER_PB_READY_STATUS_MESSAGE = "PB 记录已生成"
CAREER_ACHIEVEMENTS_EMPTY_STATUS_MESSAGE = "成就档案将在 Achievement Resolver 识别后展示"
CAREER_ACHIEVEMENTS_READY_STATUS_MESSAGE = "成就档案已生成"
CAREER_CANDIDATES_EMPTY_STATUS_MESSAGE = "暂无待确认候选事件"
CAREER_CANDIDATES_READY_STATUS_MESSAGE = "候选事件已生成"
CAREER_MEMORY_EMPTY_STATUS_MESSAGE = "暂无生涯记忆"
CAREER_MEMORY_READY_STATUS_MESSAGE = "生涯记忆已生成"
CAREER_SEASONS_EMPTY_STATUS_MESSAGE = "年度生涯将在活动记录与派生事件生成后展示"
CAREER_SEASONS_READY_STATUS_MESSAGE = "年度生涯已生成"
CAREER_BANNER_MEDIA_ROLE = "overview_banner"
CAREER_RACE_GALLERY_MEDIA_ROLE = "race_gallery"
CAREER_BANNER_PHOTO_TITLE = "赛事 Banner 照片"
CAREER_CONTROLLED_MEDIA_DIRNAME = "career_media"
CAREER_ACTIVITY_RACE_PHOTO_PREVIEW_DIRNAME = "activity_race_photo_preview"
CAREER_ACTIVITY_RACE_PHOTO_THUMB_DIRNAME = "activity_race_photo_thumb"
CAREER_BANNER_PHOTO_MAX_BYTES = 15 * 1024 * 1024
CAREER_RACE_ARCHIVE_COVER_MAX_BYTES = CAREER_BANNER_PHOTO_MAX_BYTES
CAREER_OVERVIEW_HERO_SLIDE_MAX_COUNT = 5
CAREER_ACTIVITY_RACE_PHOTO_MAX_COUNT = 5
CAREER_BANNER_IMAGE_MIME_BY_SUFFIX = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
CAREER_TIMELINE_MILESTONE_TYPES = {"milestone"}
CAREER_TIMELINE_MILESTONE_ALIASES = {"achievement", "achievements"}
CAREER_MEMORY_TYPES = {"photo", "story", "track"}

RACE_RESOLVER_ACTIVITY_COLUMNS = (
    "id",
    "title",
    "title_source",
    "sport_type",
    "sub_sport_type",
    "start_time",
    "start_time_utc",
    "dist_km",
    "distance",
    "duration",
    "duration_sec",
    "avg_pace",
    "avg_hr",
    "gain_m",
    "calories",
    "avg_power",
    "region_city",
    "region",
    "region_display",
    "is_race",
    "race_source",
    "race_confidence",
    "race_override",
    "race_confirmed_at",
    "deleted_at",
)

RACE_FORBIDDEN_ACTIVITY_COLUMNS = {
    "points",
    "points_json",
    "track_json",
    "raw_records",
    "fit_records",
    "file_path",
    "advanced_metrics",
    "shadow_diff_json",
}

RACE_STANDARD_DISTANCE_RANGES = (
    ("5k", "5K", 4.8, 5.3),
    ("10k", "10K", 9.5, 10.8),
    ("half_marathon", "半程马拉松", 20.5, 21.7),
    ("marathon", "马拉松", 41.0, 43.0),
)

RACE_STRONG_KEYWORDS = (
    ("half_marathon", "半程马拉松"),
    ("half_marathon", "半马"),
    ("marathon", "全马"),
    ("marathon", "马拉松"),
    ("10k", "10k"),
    ("5k", "5k"),
    ("trail_race", "越野赛"),
    ("triathlon", "铁人三项"),
    ("race", "比赛"),
    ("race", "race"),
    ("marathon", "marathon"),
    ("trail_race", "trail race"),
)

RACE_WEAK_KEYWORDS = ("活动", "event", "run")

PB_RESOLVER_ACTIVITY_COLUMNS = (
    "id",
    "sport_type",
    "sub_sport_type",
    "start_time",
    "start_time_utc",
    "dist_km",
    "distance",
    "duration",
    "duration_sec",
    "deleted_at",
)

ACHIEVEMENT_RESOLVER_ACTIVITY_COLUMNS = (
    "id",
    "sport_type",
    "sub_sport_type",
    "start_time",
    "start_time_utc",
    "dist_km",
    "distance",
    "total_ascent",
    "ascent",
    "elev_gain",
    "gain_m",
    "region_city",
    "region",
    "region_display",
    "deleted_at",
)

PB_FORBIDDEN_ACTIVITY_COLUMNS = {
    "points",
    "points_json",
    "track_json",
    "raw_records",
    "fit_records",
    "file_path",
    "advanced_metrics",
    "shadow_diff_json",
}

ACHIEVEMENT_FORBIDDEN_ACTIVITY_COLUMNS = {
    "points",
    "points_json",
    "track_json",
    "raw_records",
    "fit_records",
    "file_path",
    "advanced_metrics",
    "shadow_diff_json",
}

ACS_FORBIDDEN_RESPONSE_KEYS = {
    "points",
    "points_json",
    "track_json",
    "raw_records",
    "fit_records",
    "file_path",
    "advanced_metrics",
    "shadow_diff_json",
    "sqlite_schema",
    "schema",
}
ACS_PUBLIC_METADATA_FORBIDDEN_KEYS = ACS_FORBIDDEN_RESPONSE_KEYS | {
    "storage_ref",
    "path",
    "thumbnail_url",
    "detail_link",
}
CAREER_SNAPSHOT_FORBIDDEN_KEYS = ACS_PUBLIC_METADATA_FORBIDDEN_KEYS

RUNNING_SPORT_TYPES = {
    "running",
    "run",
    "trail_running",
    "track_running",
    "road_running",
}

CYCLING_SPORT_TYPES = {
    "cycling",
    "cycling_sport",
    "road_biking",
    "mountain_biking",
    "gravel_cycling",
    "indoor_cycling",
    "bike",
    "biking",
}

WALKING_SPORT_TYPES = {
    "walking",
    "walk",
    "casual_walking",
}

HIKING_SPORT_TYPES = {
    "hiking",
    "hike",
    "mountaineering",
    "trekking",
}

SWIMMING_SPORT_TYPES = {
    "swimming",
    "lap_swimming",
    "open_water",
    "open_water_swimming",
}

STRENGTH_SPORT_TYPES = {
    "strength",
    "strength_training",
    "weight_training",
    "gym",
}

CAREER_OVERVIEW_STRENGTH_WEIGHT_COLUMNS = (
    "strength_total_weight_kg",
    "total_weight_kg",
    "total_volume_kg",
    "weight_volume_kg",
    "volume_kg",
)

RUNNING_PB_DISTANCE_RANGES = (
    ("running_5k", 4.8, 5.3),
    ("running_10k", 9.5, 10.8),
    ("running_half_marathon", 20.5, 21.7),
    ("running_marathon", 41.0, 43.0),
)

PB_TIMELINE_TITLES = {
    "running_5k": "5K PB",
    "running_10k": "10K PB",
    "running_half_marathon": "半马 PB",
    "running_marathon": "全马 PB",
}

PB_TYPE_LABELS = {
    "running_5k": "5K",
    "running_10k": "10K",
    "running_half_marathon": "半程马拉松",
    "running_marathon": "马拉松",
    "cycling_distance": "最长骑行",
    "cycling_ascent": "最大爬升",
    "cycling_avg_speed": "最快均速",
}

PB_OVERVIEW_TYPE_PRIORITY = {
    "running_5k": 0,
    "running_10k": 1,
    "running_half_marathon": 2,
    "running_marathon": 3,
}

ACHIEVEMENT_FIRST_DISTANCE_RULES = (
    ("first_running_5k", "首次跑完 5K", "running", 4.8, 5.3, 70, "flag"),
    ("first_running_10k", "首次跑完 10K", "running", 9.5, 10.8, 75, "flag"),
    ("first_running_half_marathon", "首次完成半马", "running", 20.5, 21.7, 85, "flag"),
    ("first_running_marathon", "首次完成全马", "running", 41.0, 43.0, 95, "flag"),
    ("first_cycling_50k", "首次骑行 50K", "cycling", 49.0, 55.0, 70, "bike"),
    ("first_cycling_100k", "首次骑行 100K", "cycling", 98.0, 110.0, 85, "bike"),
)

ACHIEVEMENT_TITLES = {
    **{rule[0]: rule[1] for rule in ACHIEVEMENT_FIRST_DISTANCE_RULES},
    "longest_running": "最长跑步距离",
    "longest_cycling": "最长骑行距离",
    "max_ascent": "最大累计爬升",
    "first_city": "首次点亮城市",
    "annual_milestone": "年度运动里程碑",
}

ACHIEVEMENT_CATEGORY_LABELS = {
    "first_distance": "首次突破",
    "record": "个人纪录",
    "location": "地点点亮",
    "annual": "年度里程碑",
    "general": "综合成就",
}

TIMELINE_06B_ACHIEVEMENT_MILESTONE_TYPES = {
    "first_running_5k",
    "first_running_10k",
    "first_running_half_marathon",
    "first_running_marathon",
    "first_cycling_50k",
    "first_cycling_100k",
    "first_cycling_200k",
    "regular_training_4_weeks",
    "regular_training_8_weeks",
    "regular_training_12_weeks",
    "high_frequency_training_month",
    "single_elevation_gain_1000m",
    "single_elevation_gain_2000m",
    "first_max_altitude_3000m",
    "first_max_altitude_5000m",
    "multi_sport_2_types",
    "multi_sport_3_types",
    "multi_sport_5_types",
    "year_activity_100",
    "year_running_distance_1000km",
    "year_cycling_distance_3000km",
    "year_elevation_gain_50000m",
}

TIMELINE_06B_MILESTONE_TITLES = {
    "first_activity": "第一次运动记录",
    "first_sport_activity": "第一次{sport_label}",
    "first_race": "第一场正式赛事",
    "first_running_5k": "第一次 5K",
    "first_running_10k": "第一次 10K",
    "first_running_half_marathon": "第一次半马",
    "first_running_marathon": "第一次全马",
    "first_cycling_50k": "第一次 50K 骑行",
    "first_cycling_100k": "第一次 100K 骑行",
    "first_cycling_200k": "第一次 200K 骑行",
    "single_elevation_gain_1000m": "千米爬升挑战",
    "single_elevation_gain_2000m": "双千米爬升挑战",
    "first_max_altitude_3000m": "首次踏上海拔 3000m+",
    "first_max_altitude_5000m": "首次踏上海拔 5000m+",
    "multi_sport_2_types": "双栖运动者",
    "multi_sport_3_types": "多项运动者",
    "multi_sport_5_types": "全能探索者",
    "year_activity_100": "年度 100 次运动",
    "year_running_distance_1000km": "年度跑步 1000 km",
    "year_cycling_distance_3000km": "年度骑行 3000 km",
    "year_elevation_gain_50000m": "年度爬升 50000 m",
    "total_activity_count_milestone": "累计活动 {threshold} 次",
    "total_distance_milestone": "累计运动 {threshold} km",
    "running_distance_milestone": "累计跑步 {threshold} km",
    "cycling_distance_milestone": "累计骑行 {threshold} km",
    "total_elevation_gain_milestone": "累计爬升 {threshold} m",
    "total_duration_hours_milestone": "累计运动 {threshold} 小时",
}

TIMELINE_06B_FIRST_DISTANCE_RULES = (
    ("first_running_5k", "running", 4.8, 5.3, "5 km", 76),
    ("first_running_10k", "running", 9.5, 10.8, "10 km", 78),
    ("first_running_half_marathon", "running", 20.5, 21.7, "21.1 km", 84),
    ("first_running_marathon", "running", 41.0, 43.0, "42.2 km", 90),
    ("first_cycling_50k", "cycling", 49.0, 55.0, "50 km", 76),
    ("first_cycling_100k", "cycling", 98.0, 110.0, "100 km", 84),
    ("first_cycling_200k", "cycling", 198.0, 220.0, "200 km", 92),
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _connect_default() -> sqlite3.Connection:
    db_path = Path(profile_backend.DB_PATH).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    if not _table_exists(conn, table_name):
        return False
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(row[1] == column_name for row in rows)


def _count_rows(conn: sqlite3.Connection, table_name: str, where_sql: str = "") -> int:
    if not _table_exists(conn, table_name):
        return 0
    sql = f"SELECT COUNT(*) FROM {table_name}"
    if where_sql:
        sql += f" WHERE {where_sql}"
    row = conn.execute(sql).fetchone()
    return int(row[0] or 0) if row else 0


def _add_column_if_missing(
    conn: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_sql: str,
    migrated: list[str],
) -> None:
    if not _table_exists(conn, table_name):
        return
    if _column_exists(conn, table_name, column_name):
        return
    conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")
    migrated.append(f"{table_name}.{column_name}")


def _deleted_filter(conn: sqlite3.Connection) -> str:
    return "deleted_at IS NULL" if _column_exists(conn, "activities", "deleted_at") else "1=1"


def _activity_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    if not _table_exists(conn, "activities"):
        return {
            "career_start_year": None,
            "activity_count": 0,
            "covered_city_count": 0,
            "total_distance_km": None,
        }

    where_sql = _deleted_filter(conn)
    activity_count = _count_rows(conn, "activities", where_sql)

    start_year = None
    start_time_expr = None
    has_start_time = _column_exists(conn, "activities", "start_time")
    has_start_time_utc = _column_exists(conn, "activities", "start_time_utc")
    if has_start_time and has_start_time_utc:
        start_time_expr = "COALESCE(NULLIF(start_time, ''), NULLIF(start_time_utc, ''))"
    elif has_start_time:
        start_time_expr = "start_time"
    elif has_start_time_utc:
        start_time_expr = "start_time_utc"
    if start_time_expr:
        row = conn.execute(
            f"""
            SELECT MIN(substr({start_time_expr}, 1, 4))
            FROM activities
            WHERE {where_sql}
              AND COALESCE({start_time_expr}, '') != ''
            """
        ).fetchone()
        raw_year = row[0] if row else None
        if raw_year and str(raw_year).isdigit():
            start_year = int(raw_year)

    covered_city_count = 0
    city_expr = None
    for column_name in ("region_city", "city", "cityName"):
        if _column_exists(conn, "activities", column_name):
            city_expr = column_name
            break
    if city_expr:
        row = conn.execute(
            f"""
            SELECT COUNT(DISTINCT TRIM({city_expr}))
            FROM activities
            WHERE {where_sql}
              AND TRIM(COALESCE({city_expr}, '')) != ''
            """
        ).fetchone()
        covered_city_count = int(row[0] or 0) if row else 0

    total_distance_km = None
    distance_expr = None
    has_dist_km = _column_exists(conn, "activities", "dist_km")
    has_distance = _column_exists(conn, "activities", "distance")
    if has_dist_km and has_distance:
        distance_expr = "COALESCE(dist_km, distance / 1000.0)"
    elif has_dist_km:
        distance_expr = "dist_km"
    elif has_distance:
        distance_expr = "distance / 1000.0"
    if distance_expr:
        row = conn.execute(
            f"""
            SELECT SUM({distance_expr})
            FROM activities
            WHERE {where_sql}
            """
        ).fetchone()
        if row and row[0] is not None:
            total_distance_km = round(float(row[0]), 2)

    return {
        "career_start_year": start_year,
        "activity_count": activity_count,
        "covered_city_count": covered_city_count,
        "total_distance_km": total_distance_km,
    }


def _activity_select_alias(conn: sqlite3.Connection, table_name: str, column_name: str) -> str:
    if _column_exists(conn, table_name, column_name):
        return column_name
    return f"NULL AS {column_name}"


def _overview_activity_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    if not _table_exists(conn, "activities"):
        return []
    columns = (
        "id",
        "title",
        "name",
        "file_name",
        "filename",
        "sport_type",
        "sub_sport_type",
        "sport",
        "activity_type",
        "start_time",
        "start_time_utc",
        "dist_km",
        "distance",
        "duration",
        "duration_sec",
        "total_ascent",
        "ascent",
        "elev_gain",
        "gain_m",
        "max_alt_m",
        "region_city",
        "city",
        "cityName",
        "region_country",
        "country",
        "countryName",
    ) + CAREER_OVERVIEW_STRENGTH_WEIGHT_COLUMNS
    select_sql = ", ".join(_activity_select_alias(conn, "activities", column) for column in columns)
    cursor = conn.execute(
        f"""
        SELECT {select_sql}
        FROM activities
        WHERE {_deleted_filter(conn)}
        ORDER BY COALESCE(NULLIF(start_time, ''), NULLIF(start_time_utc, '')) DESC, id DESC
        """
    )
    return _rows_to_dicts(cursor)


def _overview_activity_title(row: dict[str, Any]) -> str:
    for key in ("title", "name", "file_name", "filename"):
        value = " ".join(str(row.get(key) or "").split())
        if value:
            return value[:80]
    activity_id = str(row.get("id") or "").strip()
    return f"运动活动 {activity_id}" if activity_id else "运动记忆"


def _overview_activity_sport(row: dict[str, Any]) -> str:
    values = " ".join(
        str(row.get(key) or "").strip().lower()
        for key in ("sport_type", "sub_sport_type", "sport", "activity_type")
    )
    if not values.strip():
        return "unknown"
    tokens = set(values.replace("-", "_").split())
    if tokens & RUNNING_SPORT_TYPES or any(token in values for token in ("running", "跑步", "trail_running")):
        return "running"
    if tokens & CYCLING_SPORT_TYPES or any(token in values for token in ("cycling", "bike", "骑行")):
        return "cycling"
    if tokens & SWIMMING_SPORT_TYPES or any(token in values for token in ("swimming", "游泳", "open_water")):
        return "swimming"
    if tokens & HIKING_SPORT_TYPES or any(token in values for token in ("hiking", "徒步", "trekking")):
        return "hiking"
    if tokens & WALKING_SPORT_TYPES or any(token in values for token in ("walking", "步行", "walk")):
        return "walking"
    if tokens & STRENGTH_SPORT_TYPES or any(token in values for token in ("strength", "力量", "weight_training")):
        return "strength"
    return "unknown"


def _overview_sport_label(sport: Any) -> str:
    labels = {
        "running": "跑步",
        "cycling": "骑行",
        "swimming": "游泳",
        "hiking": "徒步",
        "walking": "步行",
        "strength": "力量训练",
        "unknown": "运动",
    }
    return labels.get(str(sport or "unknown"), "运动")


def _overview_activity_date(row: dict[str, Any]) -> str:
    return str(row.get("start_time") or row.get("start_time_utc") or "").strip()[:10]


def _overview_activity_city(row: dict[str, Any]) -> str:
    for key in ("region_city", "city", "cityName"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _overview_activity_country(row: dict[str, Any]) -> str:
    for key in ("region_country", "country", "countryName"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _distance_display(value: Any) -> str:
    parsed = _safe_float(value)
    if parsed is None or parsed <= 0:
        return ""
    return f"{parsed:.1f} km".replace(".0 km", " km")


def _weight_display_kg(value: Any) -> str:
    parsed = _safe_float(value)
    if parsed is None or parsed <= 0:
        return "待生成"
    if parsed >= 1000:
        return f"{parsed / 1000.0:.1f} t".replace(".0 t", " t")
    return f"{parsed:.0f} kg"


def _duration_display(value: Any) -> str:
    seconds = _safe_int(value, default=0)
    if seconds <= 0:
        return ""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours:
        return f"{hours}小时{minutes:02d}分"
    return f"{minutes}分钟"


def _build_sport_totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    totals = {
        "running_distance_km": 0.0,
        "cycling_distance_km": 0.0,
        "walking_distance_km": 0.0,
        "hiking_distance_km": 0.0,
        "walking_hiking_distance_km": 0.0,
        "swimming_distance_km": 0.0,
        "strength_total_weight_kg": None,
        "strength_total_weight_status": "unavailable",
    }
    strength_columns = [column for column in CAREER_OVERVIEW_STRENGTH_WEIGHT_COLUMNS if any(row.get(column) not in (None, "") for row in rows)]
    strength_sum = 0.0
    strength_seen = False
    for row in rows:
        sport = _overview_activity_sport(row)
        distance_km = _activity_distance_km(row) or 0.0
        if sport == "running":
            totals["running_distance_km"] += distance_km
        elif sport == "cycling":
            totals["cycling_distance_km"] += distance_km
        elif sport == "walking":
            totals["walking_distance_km"] += distance_km
            totals["walking_hiking_distance_km"] += distance_km
        elif sport == "hiking":
            totals["hiking_distance_km"] += distance_km
            totals["walking_hiking_distance_km"] += distance_km
        elif sport == "swimming":
            totals["swimming_distance_km"] += distance_km
        if sport == "strength" and strength_columns:
            for column in strength_columns:
                value = _safe_float(row.get(column))
                if value is not None and value > 0:
                    strength_sum += value
                    strength_seen = True
                    break
    for key in ("running_distance_km", "cycling_distance_km", "walking_distance_km", "hiking_distance_km", "walking_hiking_distance_km", "swimming_distance_km"):
        totals[key] = round(float(totals[key]), 2)
    if strength_columns:
        totals["strength_total_weight_kg"] = round(strength_sum, 1) if strength_seen else None
        totals["strength_total_weight_status"] = "available" if strength_seen else "partial"
    return totals


def _build_career_stats(
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
    race_count: int,
    pb_count: int,
    achievement_count: int,
) -> dict[str, Any]:
    countries = {_overview_activity_country(row).strip() for row in rows if _overview_activity_country(row).strip()}
    years = {
        int(_overview_activity_date(row)[:4])
        for row in rows
        if _overview_activity_date(row)[:4].isdigit()
    }
    total_duration = 0
    longest_distance = 0.0
    max_gain = 0.0
    max_altitude: float | None = None
    for row in rows:
        duration = _activity_duration_sec(row)
        if duration is not None:
            total_duration += int(duration)
        distance = _activity_distance_km(row)
        if distance is not None:
            longest_distance = max(longest_distance, float(distance))
        ascent = _achievement_ascent_m(row)
        if ascent is not None:
            max_gain = max(max_gain, float(ascent))
        altitude = _safe_float(row.get("max_alt_m"))
        if altitude is not None:
            max_altitude = altitude if max_altitude is None else max(max_altitude, altitude)
    return {
        "activity_count": _safe_int(summary.get("activity_count")),
        "race_count": race_count,
        "pb_count": pb_count,
        "achievement_count": achievement_count,
        "total_duration_seconds": total_duration,
        "covered_city_count": _safe_int(summary.get("covered_city_count")),
        "covered_country_count": len(countries),
        "active_year_count": len(years),
        "longest_activity_distance_km": round(longest_distance, 2) if longest_distance > 0 else None,
        "max_elevation_gain_m": round(max_gain, 1) if max_gain > 0 else None,
        "max_altitude_m": round(max_altitude, 1) if max_altitude is not None else None,
    }


def _best_pb_summary(pb_records: list[dict[str, Any]]) -> dict[str, Any] | None:
    representative = _representative_pb_records(pb_records, limit=1)
    if not representative:
        return None
    pb = representative[0]
    return {
        "title": str(pb.get("pb_title") or pb.get("pb_type_label") or "PB"),
        "value_display": str(pb.get("value_display") or ""),
        "event_date": str(pb.get("event_date") or ""),
        "detail_link": pb.get("detail_link") if isinstance(pb.get("detail_link"), dict) else {"activity_id": "", "source": "career"},
    }


def _find_activity_row_by_id(rows: list[dict[str, Any]], activity_id: Any) -> dict[str, Any] | None:
    target = str(activity_id or "").strip()
    if not target:
        return None
    for row in rows:
        if str(row.get("id") or "").strip() == target:
            return row
    return None


def _hero_badges(source_type: str, race: dict[str, Any] | None, pb: dict[str, Any] | None) -> list[str]:
    badges: list[str] = []
    if race:
        label = str(race.get("event_type_label") or "").strip()
        badges.append(label or "赛事")
    elif source_type == "activity":
        badges.append("运动记忆")
    if pb:
        badges.append("PB")
    return [badge for badge in badges if badge][:3]


def _build_empty_hero_banner() -> dict[str, Any]:
    return {
        "mode": "empty",
        "activity_id": "",
        "race_id": "",
        "title": "等待第一段运动记忆",
        "subtitle": "导入活动后，脉图会在这里展示你的代表瞬间",
        "sport": "unknown",
        "sport_label": "运动",
        "event_date": "",
        "city": "",
        "country": "",
        "distance_display": "",
        "duration_display": "",
        "badges": ["等待活动"],
        "media": {"has_photo": False, "image_ref": ""},
        "slides": [],
        "art": {"text": "运动生涯", "tone": "steel_blue", "style": "metallic_gradient"},
        "detail_link": {"activity_id": "", "source": "career"},
    }


def _hero_photo_media(activity_id: Any, hero_photo_refs: dict[str, str] | None) -> dict[str, Any]:
    clean_id = str(activity_id or "").strip()
    image_ref = str((hero_photo_refs or {}).get(clean_id) or "").strip()
    return {
        "has_photo": bool(image_ref),
        "image_ref": image_ref,
    }


def _race_display_title_from_activity(race: dict[str, Any], activity_row: dict[str, Any] | None) -> str:
    row = activity_row or {}
    activity_title = ""
    for key in ("title", "name", "file_name", "filename"):
        value = " ".join(str(row.get(key) or "").split())
        if value:
            activity_title = value[:80]
            break
    return activity_title or str(race.get("race_title") or race.get("name") or "").strip()


def _controlled_media_root() -> Path:
    return Path(profile_backend.TRACKS_DIR).expanduser().resolve().parent / CAREER_CONTROLLED_MEDIA_DIRNAME


def _is_path_under_dir(path: Path, base_dir: Path) -> bool:
    try:
        path.relative_to(base_dir)
        return True
    except ValueError:
        return False


def _is_controlled_career_media_ref(media_ref: Any) -> bool:
    try:
        _normalize_memory_media_ref(media_ref)
        return True
    except ValueError:
        return False


def _career_media_ref_to_data_url(media_ref: Any, max_bytes: int | None = None) -> str:
    clean_ref = _normalize_memory_media_ref(media_ref)
    if not clean_ref.startswith("memory/photo/"):
        return ""
    relative_part = clean_ref[len("memory/photo/") :]
    media_root = _controlled_media_root()
    target = (media_root / relative_part).resolve()
    if not _is_path_under_dir(target, media_root):
        return ""
    suffix = target.suffix.lower()
    mime = CAREER_BANNER_IMAGE_MIME_BY_SUFFIX.get(suffix)
    if not mime or not target.exists() or not target.is_file():
        return ""
    try:
        byte_limit = max_bytes if max_bytes is not None else CAREER_BANNER_PHOTO_MAX_BYTES
        if target.stat().st_size > byte_limit:
            return ""
        encoded = base64.b64encode(target.read_bytes()).decode("ascii")
    except OSError:
        return ""
    return f"data:{mime};base64,{encoded}"


def _sanitize_career_media_preview(value: Any) -> str:
    preview = str(value or "").strip()
    return preview if preview.startswith("data:image/") else ""


def _career_media_ref_to_safe_preview(media_ref: Any, max_bytes: int | None = None) -> str:
    if not _is_controlled_career_media_ref(media_ref):
        return ""
    return _sanitize_career_media_preview(_career_media_ref_to_data_url(media_ref, max_bytes=max_bytes))


def _renderable_image_ref(media_ref: str, max_bytes: int | None = None) -> str:
    return _career_media_ref_to_safe_preview(media_ref, max_bytes=max_bytes)


def _safe_activity_race_derivative_ref(value: Any, dirname: str) -> str:
    try:
        clean_ref = _normalize_memory_media_ref(value)
    except ValueError:
        return ""
    prefix = f"memory/photo/{dirname}/"
    return clean_ref if clean_ref.startswith(prefix) else ""


def _activity_race_derivatives_from_metadata(metadata: dict[str, Any]) -> dict[str, str]:
    raw = metadata.get("derivatives") if isinstance(metadata.get("derivatives"), dict) else {}
    return {
        "preview_ref": _safe_activity_race_derivative_ref(
            raw.get("preview_ref"),
            CAREER_ACTIVITY_RACE_PHOTO_PREVIEW_DIRNAME,
        ),
        "thumbnail_ref": _safe_activity_race_derivative_ref(
            raw.get("thumbnail_ref"),
            CAREER_ACTIVITY_RACE_PHOTO_THUMB_DIRNAME,
        ),
    }


def _render_activity_race_photo_image(
    row: dict[str, Any],
    preferred: str = "preview",
    max_bytes: int | None = None,
) -> str:
    metadata = _json_loads_object(row.get("metadata_json"))
    derivatives = _activity_race_derivatives_from_metadata(metadata)
    order = (
        ("thumbnail_ref", "preview_ref")
        if preferred == "thumbnail"
        else ("preview_ref", "thumbnail_ref")
    )
    for key in order:
        ref = derivatives.get(key) or ""
        if not ref:
            continue
        try:
            image_ref = _renderable_image_ref(ref, max_bytes=max_bytes)
        except ValueError:
            image_ref = ""
        if image_ref.startswith("data:image/"):
            return image_ref
    storage_ref = str(row.get("storage_ref") or "").strip()
    if storage_ref:
        try:
            image_ref = _renderable_image_ref(storage_ref, max_bytes=max_bytes)
        except ValueError:
            image_ref = ""
        if image_ref.startswith("data:image/"):
            return image_ref
    return ""


def _load_hero_photo_refs(conn: sqlite3.Connection) -> dict[str, str]:
    if not _table_exists(conn, "career_memory_items"):
        return {}
    rows = _rows_to_dicts(conn.execute(
        """
        SELECT activity_id, storage_ref, metadata_json
        FROM career_memory_items
        WHERE status = 'active'
          AND memory_type = 'photo'
          AND COALESCE(activity_id, '') <> ''
          AND COALESCE(storage_ref, '') <> ''
        ORDER BY updated_at DESC, created_at DESC
        """
    ))
    refs: dict[str, str] = {}
    for row in rows:
        clean_id = str(row.get("activity_id") or "").strip()
        if not clean_id or clean_id in refs:
            continue
        metadata = _json_loads_object(row.get("metadata_json"))
        if str(metadata.get("role") or "").strip() != CAREER_BANNER_MEDIA_ROLE:
            continue
        image_ref = _render_activity_race_photo_image(row, preferred="preview")
        if not image_ref:
            continue
        refs[clean_id] = image_ref
    return refs


def _build_hero_banner(
    rows: list[dict[str, Any]],
    latest_race: dict[str, Any] | None,
    latest_pb: dict[str, Any] | None,
    hero_photo_refs: dict[str, str] | None = None,
) -> dict[str, Any]:
    if latest_race:
        activity_row = _find_activity_row_by_id(rows, latest_race.get("activity_id")) or {}
        sport = str(latest_race.get("sport") or _overview_activity_sport(activity_row) or "unknown")
        title = _race_display_title_from_activity(latest_race, activity_row)
        event_date = str(latest_race.get("event_date") or _overview_activity_date(activity_row))
        city = str(latest_race.get("city") or _overview_activity_city(activity_row))
        country = _overview_activity_country(activity_row)
        activity_id = str(latest_race.get("activity_id") or activity_row.get("id") or "")
        media = _hero_photo_media(activity_id, hero_photo_refs)
        return {
            "mode": "photo" if media["has_photo"] else "title_art",
            "activity_id": activity_id,
            "race_id": str(latest_race.get("id") or ""),
            "title": title,
            "subtitle": " · ".join(part for part in (event_date, city or country, _overview_sport_label(sport)) if part),
            "sport": sport,
            "sport_label": _overview_sport_label(sport),
            "event_date": event_date,
            "city": city,
            "country": country,
            "distance_display": _distance_display(_activity_distance_km(activity_row)),
            "duration_display": _duration_display(_activity_duration_sec(activity_row)),
            "badges": _hero_badges("race", latest_race, latest_pb if latest_pb and str(latest_pb.get("activity_id")) == activity_id else None),
            "media": media,
            "slides": [],
            "art": {"text": title, "tone": "steel_blue", "style": "metallic_gradient"},
            "detail_link": {"activity_id": activity_id, "source": "career"},
        }

    if rows:
        sorted_rows = sorted(
            rows,
            key=lambda row: (
                _activity_distance_km(row) or 0.0,
                _overview_activity_date(row),
                str(row.get("id") or ""),
            ),
            reverse=True,
        )
        row = sorted_rows[0]
        sport = _overview_activity_sport(row)
        title = _overview_activity_title(row)
        event_date = _overview_activity_date(row)
        city = _overview_activity_city(row)
        country = _overview_activity_country(row)
        activity_id = str(row.get("id") or "")
        return {
            "mode": "title_art",
            "activity_id": activity_id,
            "race_id": "",
            "title": title,
            "subtitle": " · ".join(part for part in (event_date, city or country, _overview_sport_label(sport)) if part),
            "sport": sport,
            "sport_label": _overview_sport_label(sport),
            "event_date": event_date,
            "city": city,
            "country": country,
            "distance_display": _distance_display(_activity_distance_km(row)),
            "duration_display": _duration_display(_activity_duration_sec(row)),
            "badges": _hero_badges("activity", None, latest_pb if latest_pb and str(latest_pb.get("activity_id")) == activity_id else None),
            "media": {"has_photo": False, "image_ref": ""},
            "slides": [],
            "art": {"text": title, "tone": "steel_blue", "style": "metallic_gradient"},
            "detail_link": {"activity_id": activity_id, "source": "career"},
        }

    return _build_empty_hero_banner()


def _build_hero_banner_slides(
    races: list[dict[str, Any]],
    activity_rows: list[dict[str, Any]],
    latest_pb: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    slides: list[dict[str, Any]] = []
    seen_activity_ids: set[str] = set()
    for race in races:
        activity_id = str(race.get("activity_id") or "").strip()
        if not activity_id or activity_id in seen_activity_ids:
            continue
        media = race.get("media") if isinstance(race.get("media"), dict) else {}
        image_ref = _sanitize_career_media_preview(media.get("image_ref") if isinstance(media, dict) else "")
        if not image_ref:
            continue
        activity_row = _find_activity_row_by_id(activity_rows, activity_id) or {}
        sport = str(race.get("sport") or _overview_activity_sport(activity_row) or "unknown")
        title = _race_display_title_from_activity(race, activity_row)
        event_date = str(race.get("event_date") or _overview_activity_date(activity_row))
        city = str(race.get("city") or _overview_activity_city(activity_row))
        country = _overview_activity_country(activity_row)
        slides.append({
            "mode": "photo",
            "activity_id": activity_id,
            "race_id": str(race.get("id") or ""),
            "title": title,
            "subtitle": " · ".join(part for part in (event_date, city or country, _overview_sport_label(sport)) if part),
            "sport": sport,
            "sport_label": _overview_sport_label(sport),
            "event_date": event_date,
            "city": city,
            "country": country,
            "distance_display": _distance_display(_activity_distance_km(activity_row)),
            "duration_display": _duration_display(_activity_duration_sec(activity_row)),
            "badges": _hero_badges("race", race, latest_pb if latest_pb and str(latest_pb.get("activity_id")) == activity_id else None),
            "media": {"has_photo": True, "image_ref": image_ref},
            "art": {"text": title, "tone": "steel_blue", "style": "metallic_gradient"},
            "detail_link": {"activity_id": activity_id, "source": "career"},
        })
        seen_activity_ids.add(activity_id)
        if len(slides) >= CAREER_OVERVIEW_HERO_SLIDE_MAX_COUNT:
            break
    return slides


def _fetch_memory_activity_binding(conn: sqlite3.Connection, activity_id: str) -> dict[str, Any] | None:
    clean_id = str(activity_id or "").strip()
    if not clean_id:
        return None
    if not _table_exists(conn, "activities"):
        return {"id": clean_id, "event_date": ""}
    where_parts = ["CAST(id AS TEXT) = ?"]
    select_parts = ["id"]
    if _column_exists(conn, "activities", "start_time"):
        select_parts.append("start_time")
    else:
        select_parts.append("NULL AS start_time")
    if _column_exists(conn, "activities", "start_time_utc"):
        select_parts.append("start_time_utc")
    else:
        select_parts.append("NULL AS start_time_utc")
    if _column_exists(conn, "activities", "deleted_at"):
        select_parts.append("deleted_at")
    else:
        select_parts.append("NULL AS deleted_at")
    row = conn.execute(
        f"""
        SELECT {', '.join(select_parts)}
        FROM activities
        WHERE {' AND '.join(where_parts)}
        LIMIT 1
        """,
        (clean_id,),
    ).fetchone()
    if row is None:
        raise ValueError("绑定的活动不存在")
    data = dict(zip([item.split(" AS ")[-1].strip() for item in select_parts], row))
    if str(data.get("deleted_at") or "").strip():
        raise ValueError("绑定的活动已删除")
    raw_date = str(data.get("start_time") or data.get("start_time_utc") or "").strip()
    return {
        "id": str(data.get("id") or clean_id),
        "event_date": raw_date[:10] if raw_date else "",
    }


def _fetch_banner_race_activity_binding(conn: sqlite3.Connection, activity_id: str) -> dict[str, Any]:
    clean_id = str(activity_id or "").strip()
    if not clean_id:
        raise ValueError("赛事照片必须绑定活动")
    binding = _fetch_memory_activity_binding(conn, clean_id)
    activity_id_value = str((binding or {}).get("id") or clean_id)
    is_activity_race = False
    if _table_exists(conn, "activities"):
        select_parts = ["id"]
        if _column_exists(conn, "activities", "is_race"):
            select_parts.append("is_race")
        else:
            select_parts.append("0 AS is_race")
        row = conn.execute(
            f"""
            SELECT {', '.join(select_parts)}
            FROM activities
            WHERE CAST(id AS TEXT) = ?
            LIMIT 1
            """,
            (activity_id_value,),
        ).fetchone()
        if row is not None:
            names = [item.split(" AS ")[-1].strip() for item in select_parts]
            data = dict(zip(names, row))
            is_activity_race = _safe_int(data.get("is_race")) == 1
    race_row = None
    if _table_exists(conn, "career_race_events"):
        race_row = conn.execute(
            """
            SELECT id
            FROM career_race_events
            WHERE CAST(activity_id AS TEXT) = ?
              AND status = 'active'
            ORDER BY event_date DESC, updated_at DESC
            LIMIT 1
            """,
            (activity_id_value,),
        ).fetchone()
    if not is_activity_race and race_row is None:
        raise ValueError("赛事照片只能绑定已确认赛事活动")
    return {
        "id": activity_id_value,
        "event_date": str((binding or {}).get("event_date") or ""),
        "race_id": str(race_row[0] if race_row else ""),
    }


def _default_memory_event_date() -> str:
    return _utc_now_iso()[:10]


def _normalize_memory_media_ref(value: Any) -> str:
    media_ref = str(value or "").strip()
    if not media_ref:
        raise ValueError("媒体引用不能为空")
    decoded_ref = media_ref
    for _ in range(2):
        next_decoded = unquote(decoded_ref)
        if next_decoded == decoded_ref:
            break
        decoded_ref = next_decoded
    invalid_markers = (
        "/users/",
        "/tmp/",
        "\\",
        "\x00",
    )
    for candidate in (media_ref, decoded_ref):
        lowered = candidate.lower()
        segments = candidate.replace("\\", "/").split("/")
        if (
            candidate.startswith("/")
            or candidate.startswith("~")
            or any(segment == ".." or segment.endswith(":..") for segment in segments)
            or lowered.startswith("file:")
            or (len(candidate) >= 2 and candidate[1] == ":")
            or any(marker in lowered for marker in invalid_markers)
        ):
            raise ValueError("媒体引用必须是应用受控目录内的安全引用")
    if ":" in media_ref and not media_ref.startswith("asset:memory:"):
        raise ValueError("媒体引用必须是应用受控目录内的安全引用")
    if not (media_ref.startswith("memory/") or media_ref.startswith("asset:memory:")):
        raise ValueError("媒体引用必须是应用受控目录内的安全引用")
    return media_ref


def _normalize_timeline_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    raw = filters if isinstance(filters, dict) else {}
    node_type = (str(raw.get("type") or "all").strip() or "all").lower()
    if node_type in CAREER_TIMELINE_MILESTONE_ALIASES:
        node_type = "milestone"
    year_value = raw.get("year")
    year = None
    if year_value not in (None, "", "all"):
        try:
            parsed_year = int(year_value)
            if 1900 <= parsed_year <= 3000:
                year = parsed_year
        except (TypeError, ValueError):
            year = None
    return {
        "year": year,
        "type": node_type,
    }


def _normalize_race_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    raw = filters if isinstance(filters, dict) else {}
    sport = str(raw.get("sport") or "all").strip() or "all"
    event_type = str(raw.get("event_type") or raw.get("type") or "all").strip() or "all"
    source = str(raw.get("source") or "all").strip() or "all"
    year_value = raw.get("year")
    year = None
    if year_value not in (None, "", "all"):
        try:
            parsed_year = int(year_value)
            if 1900 <= parsed_year <= 3000:
                year = parsed_year
        except (TypeError, ValueError):
            year = None
    return {
        "sport": sport,
        "year": year,
        "event_type": event_type,
        "source": source,
    }


def _normalize_pb_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    raw = filters if isinstance(filters, dict) else {}
    sport = str(raw.get("sport") or "all").strip() or "all"
    pb_type = str(raw.get("pb_type") or raw.get("type") or "all").strip() or "all"
    source = str(raw.get("source") or "all").strip() or "all"
    year_value = raw.get("year")
    year = None
    if year_value not in (None, "", "all"):
        try:
            parsed_year = int(year_value)
            if 1900 <= parsed_year <= 3000:
                year = parsed_year
        except (TypeError, ValueError):
            year = None
    return {
        "sport": sport,
        "year": year,
        "pb_type": pb_type,
        "source": source,
    }


def _normalize_achievement_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    raw = filters if isinstance(filters, dict) else {}
    achievement_type = str(raw.get("achievement_type") or raw.get("type") or "all").strip() or "all"
    category = str(raw.get("category") or "all").strip() or "all"
    source = str(raw.get("source") or "all").strip() or "all"
    year_value = raw.get("year")
    year = None
    if year_value not in (None, "", "all"):
        try:
            parsed_year = int(year_value)
            if 1900 <= parsed_year <= 3000:
                year = parsed_year
        except (TypeError, ValueError):
            year = None
    min_score_value = raw.get("min_score")
    min_score = None
    if min_score_value not in (None, "", "all"):
        try:
            parsed_score = int(float(min_score_value))
            if parsed_score >= 0:
                min_score = parsed_score
        except (TypeError, ValueError):
            min_score = None
    return {
        "achievement_type": achievement_type,
        "category": category,
        "year": year,
        "source": source,
        "min_score": min_score,
    }


def _normalize_season_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    raw = filters if isinstance(filters, dict) else {}
    year_value = raw.get("year")
    year = None
    if year_value not in (None, "", "all"):
        try:
            parsed_year = int(year_value)
            if 1900 <= parsed_year <= 3000:
                year = parsed_year
        except (TypeError, ValueError):
            year = None
    sport = str(raw.get("sport") or "all").strip() or "all"
    if sport not in {"all", "running", "cycling"}:
        sport = "all"
    return {
        "year": year,
        "sport": sport,
    }


def _normalize_candidate_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    raw = filters if isinstance(filters, dict) else {}
    candidate_type = str(raw.get("candidate_type") or raw.get("type") or "all").strip().lower() or "all"
    status = str(raw.get("status") or "candidate").strip().lower() or "candidate"
    min_confidence_value = raw.get("min_confidence")
    min_confidence = None
    if min_confidence_value not in (None, "", "all"):
        try:
            parsed_confidence = float(min_confidence_value)
            if parsed_confidence >= 0:
                min_confidence = min(parsed_confidence, 1.0)
        except (TypeError, ValueError):
            min_confidence = None
    return {
        "candidate_type": candidate_type,
        "status": status,
        "min_confidence": min_confidence,
    }


def _json_dumps(value: dict[str, Any] | list[Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_loads_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _sanitize_public_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _sanitize_public_metadata(child)
            for key, child in value.items()
            if str(key).strip().lower() not in ACS_PUBLIC_METADATA_FORBIDDEN_KEYS
        }
    if isinstance(value, list):
        return [_sanitize_public_metadata(child) for child in value]
    return value


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _rows_to_dicts(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    names = [item[0] for item in cursor.description or []]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _activity_select_expr(conn: sqlite3.Connection, column_name: str) -> str:
    if column_name in RACE_FORBIDDEN_ACTIVITY_COLUMNS:
        raise ValueError(f"Forbidden ACS activity column: {column_name}")
    if _column_exists(conn, "activities", column_name):
        return column_name
    return f"NULL AS {column_name}"


def _fetch_race_resolver_activity_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    if not _table_exists(conn, "activities"):
        return []
    select_sql = ", ".join(
        _activity_select_expr(conn, column_name)
        for column_name in RACE_RESOLVER_ACTIVITY_COLUMNS
    )
    where_sql = _deleted_filter(conn)
    cursor = conn.execute(
        f"""
        SELECT {select_sql}
        FROM activities
        WHERE {where_sql}
        ORDER BY id ASC
        """
    )
    return _rows_to_dicts(cursor)


def _activity_distance_km(row: dict[str, Any]) -> float | None:
    dist_km = _safe_float(row.get("dist_km"))
    if dist_km and dist_km > 0:
        return dist_km
    raw_distance = _safe_float(row.get("distance"))
    if raw_distance is None or raw_distance <= 0:
        return None
    return raw_distance / 1000.0 if raw_distance > 1000 else raw_distance


def _match_standard_distance(distance_km: float | None) -> dict[str, Any] | None:
    if distance_km is None:
        return None
    for event_type, label, low, high in RACE_STANDARD_DISTANCE_RANGES:
        if low <= distance_km <= high:
            return {
                "event_type": event_type,
                "label": label,
                "distance_km": round(distance_km, 3),
                "range_km": [low, high],
            }
    return None


def _match_strong_title_keyword(title: str) -> dict[str, str] | None:
    normalized = title.strip().lower()
    if not normalized:
        return None
    for event_type, keyword in RACE_STRONG_KEYWORDS:
        if keyword.lower() in normalized:
            return {"event_type": event_type, "keyword": keyword}
    return None


def _match_weak_title_keyword(title: str) -> dict[str, str] | None:
    normalized = title.strip().lower()
    if not normalized:
        return None
    for keyword in RACE_WEAK_KEYWORDS:
        if keyword.lower() in normalized:
            return {"event_type": "race", "keyword": keyword}
    return None


def _race_display_date(row: dict[str, Any]) -> str:
    value = str(row.get("start_time_utc") or row.get("start_time") or "").strip()
    return value[:10] if value else ""


def _race_display_city(row: dict[str, Any]) -> str:
    for key in ("region_city", "region_display", "region"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _race_fallback_name(row: dict[str, Any], event_type: str) -> str:
    year = _race_display_date(row)[:4]
    city = _race_display_city(row)
    label = {
        "5k": "5K",
        "10k": "10K",
        "half_marathon": "半程马拉松",
        "marathon": "马拉松",
        "trail_race": "越野赛",
        "triathlon": "铁人三项",
    }.get(event_type, "赛事")
    parts = [part for part in (year, city, label) if part]
    return "".join(parts) if parts else label


def _race_event_name(row: dict[str, Any], event_type: str) -> str:
    title = str(row.get("title") or "").strip()
    if title:
        return title
    return _race_fallback_name(row, event_type)


def _race_source_for_decision(row: dict[str, Any], confidence_level: str) -> str:
    source = str(row.get("race_source") or "").strip().lower()
    if confidence_level == "high" and source in {"user", "fit_sport_event"}:
        return source
    return "resolver"


def _build_race_decision(row: dict[str, Any]) -> dict[str, Any]:
    title = str(row.get("title") or "")
    is_race = _safe_int(row.get("is_race")) == 1
    race_override = _safe_int(row.get("race_override")) == 1
    race_source = str(row.get("race_source") or "").strip().lower()
    race_confidence = str(row.get("race_confidence") or "").strip().lower()
    title_match = _match_strong_title_keyword(title)
    weak_title_match = _match_weak_title_keyword(title)
    distance_match = _match_standard_distance(_activity_distance_km(row))
    signals: list[dict[str, Any]] = []

    if race_source == "user" and not is_race:
        return {
            "decision": "skip_user_cancelled",
            "confidence_level": "none",
            "confidence_score": 0.0,
            "event_type": "race",
            "signals": [
                {"type": "user_cancellation", "level": "high", "matched": True},
            ],
        }

    if race_source == "user" and is_race:
        signals.append({"type": "user_confirmation", "level": "high", "matched": True})
    if race_override and is_race:
        signals.append({"type": "user_override", "level": "high", "matched": True})
    if race_source == "fit_sport_event" and is_race:
        signals.append({"type": "fit_sport_event", "level": "high", "matched": True})
    if is_race and race_confidence == "high":
        signals.append({"type": "activity_race_confidence", "level": "high", "matched": True})

    if signals:
        event_type = (
            (title_match or {}).get("event_type")
            or (distance_match or {}).get("event_type")
            or "race"
        )
        return {
            "decision": "race_event",
            "confidence_level": "high",
            "confidence_score": 1.0,
            "event_type": event_type,
            "signals": signals,
        }

    if title_match:
        signals.append({
            "type": "title_keyword",
            "level": "medium",
            "matched": True,
            "keyword": title_match["keyword"],
        })
    if distance_match:
        signals.append({
            "type": "standard_distance",
            "level": "low",
            "matched": True,
            "category": distance_match["event_type"],
            "distance_km": distance_match["distance_km"],
        })

    if title_match and distance_match:
        return {
            "decision": "race_event",
            "confidence_level": "medium",
            "confidence_score": 0.75,
            "event_type": title_match.get("event_type") or distance_match["event_type"],
            "signals": signals,
        }

    if distance_match or weak_title_match:
        if weak_title_match:
            signals.append({
                "type": "weak_title_keyword",
                "level": "low",
                "matched": True,
                "keyword": weak_title_match["keyword"],
            })
        return {
            "decision": "candidate",
            "confidence_level": "low",
            "confidence_score": 0.35 if distance_match else 0.25,
            "event_type": (distance_match or weak_title_match or {}).get("event_type", "race"),
            "signals": signals,
        }

    return {
        "decision": "skip",
        "confidence_level": "none",
        "confidence_score": 0.0,
        "event_type": "race",
        "signals": signals,
    }


def _race_evidence(row: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "resolver": "race",
        "activity_id": str(row.get("id") or ""),
        "signals": decision.get("signals", []),
        "confidence_level": decision.get("confidence_level"),
        "confidence_score": decision.get("confidence_score"),
        "decision": decision.get("decision"),
        "event_type": decision.get("event_type"),
    }


def _upsert_race_event(conn: sqlite3.Connection, row: dict[str, Any], decision: dict[str, Any]) -> None:
    activity_id = str(row.get("id"))
    event_id = f"race:{activity_id}"
    event_type = str(decision.get("event_type") or "race")
    evidence = _race_evidence(row, decision)
    metadata = {
        "resolver": "race",
        "confidence_level": decision.get("confidence_level"),
        "evidence": evidence,
    }
    conn.execute(
        """
        INSERT INTO career_race_events
            (id, activity_id, name, event_type, sport, event_date, location_json,
             performance_summary_json, achievement_ids_json, confidence, source, status,
             display_metadata_json, updated_at)
        VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, '[]', ?, ?, 'active', ?, CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
            activity_id = excluded.activity_id,
            name = excluded.name,
            event_type = excluded.event_type,
            sport = excluded.sport,
            event_date = excluded.event_date,
            location_json = excluded.location_json,
            performance_summary_json = excluded.performance_summary_json,
            confidence = excluded.confidence,
            source = excluded.source,
            status = 'active',
            display_metadata_json = excluded.display_metadata_json,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            event_id,
            activity_id,
            _race_event_name(row, event_type),
            event_type,
            str(row.get("sport_type") or "unknown"),
            _race_display_date(row),
            _json_dumps({"city": _race_display_city(row)}),
            _json_dumps({"event_type": event_type}),
            float(decision.get("confidence_score") or 0.0),
            _race_source_for_decision(row, str(decision.get("confidence_level") or "")),
            _json_dumps(metadata),
        ),
    )
    conn.execute(
        """
        UPDATE career_event_candidates
        SET status = 'resolved', updated_at = CURRENT_TIMESTAMP
        WHERE id = ? OR activity_id = ?
        """,
        (f"race_candidate:{activity_id}", activity_id),
    )


def _upsert_race_candidate(conn: sqlite3.Connection, row: dict[str, Any], decision: dict[str, Any]) -> None:
    activity_id = str(row.get("id"))
    candidate_id = f"race_candidate:{activity_id}"
    evidence = _race_evidence(row, decision)
    conn.execute(
        """
        INSERT INTO career_event_candidates
            (id, activity_id, candidate_type, title, evidence_json, confidence, status, updated_at)
        VALUES
            (?, ?, 'race', ?, ?, ?, 'candidate', CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
            activity_id = excluded.activity_id,
            candidate_type = excluded.candidate_type,
            title = excluded.title,
            evidence_json = excluded.evidence_json,
            confidence = excluded.confidence,
            status = 'candidate',
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            candidate_id,
            activity_id,
            _race_event_name(row, str(decision.get("event_type") or "race")),
            _json_dumps(evidence),
            float(decision.get("confidence_score") or 0.0),
        ),
    )
    conn.execute(
        """
        UPDATE career_race_events
        SET status = 'inactive', updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (f"race:{activity_id}",),
    )


def _close_race_artifacts(conn: sqlite3.Connection, activity_id: str) -> None:
    conn.execute(
        """
        UPDATE career_race_events
        SET status = 'inactive', updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (f"race:{activity_id}",),
    )
    conn.execute(
        """
        UPDATE career_event_candidates
        SET status = 'dismissed', updated_at = CURRENT_TIMESTAMP
        WHERE id = ? OR activity_id = ?
        """,
        (f"race_candidate:{activity_id}", activity_id),
    )


def _activity_exists_for_candidate(conn: sqlite3.Connection, activity_id: str) -> bool:
    if not _table_exists(conn, "activities"):
        return False
    where_sql = f"CAST(id AS TEXT) = ? AND {_deleted_filter(conn)}"
    row = conn.execute(
        f"SELECT 1 FROM activities WHERE {where_sql} LIMIT 1",
        (str(activity_id),),
    ).fetchone()
    return row is not None


def _set_activity_user_race_flag(conn: sqlite3.Connection, activity_id: str, is_race: bool) -> None:
    if not _activity_exists_for_candidate(conn, activity_id):
        raise ValueError("候选绑定的活动不存在")
    required_columns = ("is_race", "race_source", "race_confidence", "race_override", "race_confirmed_at")
    missing = [column for column in required_columns if not _column_exists(conn, "activities", column)]
    if missing:
        raise ValueError("活动表缺少赛事确认字段")
    updated_at_sql = ", updated_at = CURRENT_TIMESTAMP" if _column_exists(conn, "activities", "updated_at") else ""
    conn.execute(
        f"""
        UPDATE activities
        SET is_race = ?,
            race_source = 'user',
            race_confidence = 'high',
            race_override = 1,
            race_confirmed_at = CURRENT_TIMESTAMP
            {updated_at_sql}
        WHERE CAST(id AS TEXT) = ?
        """,
        (1 if is_race else 0, str(activity_id)),
    )


def resolve_race_events(conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """Resolve Activity-backed race events and low-confidence candidates."""
    owns_conn = conn is None
    db = conn or _connect_default()
    processed = 0
    race_events_upserted = 0
    candidates_upserted = 0
    skipped = 0
    try:
        schema = ensure_career_schema(db)
        rows = _fetch_race_resolver_activity_rows(db)
        for row in rows:
            processed += 1
            activity_id = str(row.get("id"))
            decision = _build_race_decision(row)
            if decision["decision"] == "race_event":
                _upsert_race_event(db, row, decision)
                race_events_upserted += 1
            elif decision["decision"] == "candidate":
                _upsert_race_candidate(db, row, decision)
                candidates_upserted += 1
            elif decision["decision"] == "skip_user_cancelled":
                _close_race_artifacts(db, activity_id)
                skipped += 1
            else:
                skipped += 1

        if owns_conn:
            db.commit()
        return {
            "ok": True,
            "processed": processed,
            "race_events_upserted": race_events_upserted,
            "candidates_upserted": candidates_upserted,
            "skipped": skipped,
            "status": {
                "schema_ready": bool(schema.get("ok")),
                "resolver": "race",
                "message": "赛事解析完成",
            },
        }
    except Exception:
        if owns_conn:
            db.rollback()
        raise
    finally:
        if owns_conn:
            db.close()


def _pb_activity_select_expr(conn: sqlite3.Connection, column_name: str) -> str:
    if column_name in PB_FORBIDDEN_ACTIVITY_COLUMNS:
        raise ValueError(f"Forbidden ACS PB activity column: {column_name}")
    if _column_exists(conn, "activities", column_name):
        return column_name
    return f"NULL AS {column_name}"


def _fetch_pb_resolver_activity_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    if not _table_exists(conn, "activities"):
        return []
    select_sql = ", ".join(
        _pb_activity_select_expr(conn, column_name)
        for column_name in PB_RESOLVER_ACTIVITY_COLUMNS
    )
    where_sql = _deleted_filter(conn)
    cursor = conn.execute(
        f"""
        SELECT {select_sql}
        FROM activities
        WHERE {where_sql}
        ORDER BY id ASC
        """
    )
    return _rows_to_dicts(cursor)


def _is_running_activity(row: dict[str, Any]) -> bool:
    sport = str(row.get("sport_type") or "").strip().lower()
    sub_sport = str(row.get("sub_sport_type") or "").strip().lower()
    return sport in RUNNING_SPORT_TYPES or sub_sport in RUNNING_SPORT_TYPES


def _activity_duration_sec(row: dict[str, Any]) -> int | None:
    duration = _safe_int(row.get("duration"))
    if duration > 0:
        return duration
    duration_sec = _safe_int(row.get("duration_sec"))
    return duration_sec if duration_sec > 0 else None


def _match_running_pb_type(distance_km: float | None) -> dict[str, Any] | None:
    if distance_km is None:
        return None
    for pb_type, low, high in RUNNING_PB_DISTANCE_RANGES:
        if low <= distance_km <= high:
            return {
                "pb_type": pb_type,
                "distance_km": round(distance_km, 3),
                "matched_range_km": [low, high],
            }
    return None


def _pb_event_date(row: dict[str, Any]) -> str:
    value = str(row.get("start_time_utc") or row.get("start_time") or "").strip()
    return value[:10] if value else ""


def _build_pb_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in rows:
        if not _is_running_activity(row):
            continue
        duration_sec = _activity_duration_sec(row)
        if duration_sec is None:
            continue
        distance_match = _match_running_pb_type(_activity_distance_km(row))
        if not distance_match:
            continue
        candidates.append({
            "activity_id": str(row.get("id") or ""),
            "sport": "running",
            "pb_type": distance_match["pb_type"],
            "duration_sec": duration_sec,
            "event_date": _pb_event_date(row),
            "distance_km": distance_match["distance_km"],
            "matched_range_km": distance_match["matched_range_km"],
        })
    return candidates


def _best_pb_by_type(candidates: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        pb_type = str(candidate["pb_type"])
        current = best.get(pb_type)
        if current is None:
            best[pb_type] = candidate
            continue
        current_key = (int(current["duration_sec"]), str(current.get("event_date") or ""), str(current.get("activity_id") or ""))
        candidate_key = (int(candidate["duration_sec"]), str(candidate.get("event_date") or ""), str(candidate.get("activity_id") or ""))
        if candidate_key < current_key:
            best[pb_type] = candidate
    return best


def _active_pb_row(conn: sqlite3.Connection, pb_type: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, activity_id, value
        FROM career_pb_records
        WHERE pb_type = ? AND status = 'active'
        ORDER BY CAST(value AS INTEGER) ASC, event_date ASC, id ASC
        LIMIT 1
        """,
        (pb_type,),
    ).fetchone()
    if row is None:
        return None
    if isinstance(row, sqlite3.Row):
        return dict(row)
    return {"id": row[0], "activity_id": row[1], "value": row[2]}


def _upsert_active_pb_record(
    conn: sqlite3.Connection,
    candidate: dict[str, Any],
    previous: dict[str, Any] | None,
) -> None:
    pb_type = str(candidate["pb_type"])
    activity_id = str(candidate["activity_id"])
    previous_activity_id = str(previous.get("activity_id") or "") if previous else None
    previous_value = _safe_int(previous.get("value")) if previous else None
    improvement_sec = None
    if previous_value and previous_value > int(candidate["duration_sec"]):
        improvement_sec = previous_value - int(candidate["duration_sec"])
    metadata = {
        "resolver": "pb",
        "pb_type": pb_type,
        "distance_km": candidate["distance_km"],
        "matched_range_km": candidate["matched_range_km"],
        "previous_activity_id": previous_activity_id,
        "previous_value": previous_value,
        "improvement_sec": improvement_sec,
    }
    conn.execute(
        """
        INSERT INTO career_pb_records
            (id, activity_id, sport, pb_type, value, value_unit, improvement,
             event_date, confidence, source, status, display_metadata_json, updated_at)
        VALUES
            (?, ?, ?, ?, ?, 'seconds', ?, ?, 1.0, 'resolver', 'active', ?, CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
            activity_id = excluded.activity_id,
            sport = excluded.sport,
            pb_type = excluded.pb_type,
            value = excluded.value,
            value_unit = excluded.value_unit,
            improvement = excluded.improvement,
            event_date = excluded.event_date,
            confidence = excluded.confidence,
            source = excluded.source,
            status = 'active',
            display_metadata_json = excluded.display_metadata_json,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            f"pb:{pb_type}:{activity_id}",
            activity_id,
            candidate["sport"],
            pb_type,
            str(int(candidate["duration_sec"])),
            str(improvement_sec) if improvement_sec is not None else None,
            candidate["event_date"],
            _json_dumps(metadata),
        ),
    )
    conn.execute(
        """
        UPDATE career_pb_records
        SET status = 'superseded', updated_at = CURRENT_TIMESTAMP
        WHERE pb_type = ?
          AND status = 'active'
          AND activity_id != ?
        """,
        (pb_type, activity_id),
    )


def resolve_pb_records(conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """Resolve running PB records from Activity-backed safe summaries."""
    owns_conn = conn is None
    db = conn or _connect_default()
    processed = 0
    pb_records_upserted = 0
    skipped = 0
    try:
        schema = ensure_career_schema(db)
        rows = _fetch_pb_resolver_activity_rows(db)
        processed = len(rows)
        candidates = _build_pb_candidates(rows)
        best_by_type = _best_pb_by_type(candidates)
        for pb_type, candidate in best_by_type.items():
            previous = _active_pb_row(db, pb_type)
            if previous and str(previous.get("activity_id") or "") == str(candidate.get("activity_id") or ""):
                previous = None
            _upsert_active_pb_record(db, candidate, previous)
            pb_records_upserted += 1
        skipped = processed - len(candidates)

        if owns_conn:
            db.commit()
        return {
            "ok": True,
            "processed": processed,
            "pb_records_upserted": pb_records_upserted,
            "skipped": skipped,
            "status": {
                "schema_ready": bool(schema.get("ok")),
                "resolver": "pb",
                "message": "PB 解析完成",
            },
        }
    except Exception:
        if owns_conn:
            db.rollback()
        raise
    finally:
        if owns_conn:
            db.close()


def _achievement_activity_select_expr(conn: sqlite3.Connection, column_name: str) -> str:
    if column_name in ACHIEVEMENT_FORBIDDEN_ACTIVITY_COLUMNS:
        raise ValueError(f"Forbidden ACS Achievement activity column: {column_name}")
    if _column_exists(conn, "activities", column_name):
        return column_name
    return f"NULL AS {column_name}"


def _fetch_achievement_resolver_activity_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    if not _table_exists(conn, "activities"):
        return []
    select_sql = ", ".join(
        _achievement_activity_select_expr(conn, column_name)
        for column_name in ACHIEVEMENT_RESOLVER_ACTIVITY_COLUMNS
    )
    where_sql = _deleted_filter(conn)
    cursor = conn.execute(
        f"""
        SELECT {select_sql}
        FROM activities
        WHERE {where_sql}
        ORDER BY id ASC
        """
    )
    return _rows_to_dicts(cursor)


def _is_cycling_activity(row: dict[str, Any]) -> bool:
    sport = str(row.get("sport_type") or "").strip().lower()
    sub_sport = str(row.get("sub_sport_type") or "").strip().lower()
    return sport in CYCLING_SPORT_TYPES or sub_sport in CYCLING_SPORT_TYPES


def _achievement_event_date(row: dict[str, Any]) -> str:
    value = str(row.get("start_time_utc") or row.get("start_time") or "").strip()
    return value[:10] if value else ""


def _achievement_ascent_m(row: dict[str, Any]) -> float | None:
    for key in ("total_ascent", "ascent", "elev_gain", "gain_m"):
        value = _safe_float(row.get(key))
        if value is not None and value > 0:
            return value
    return None


def _achievement_city(row: dict[str, Any]) -> str:
    for key in ("region_city", "region_display", "region"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _achievement_city_key(city: str) -> str:
    normalized = "_".join(city.strip().lower().split())
    safe = "".join(ch if ch.isalnum() else "_" for ch in normalized)
    return "_".join(part for part in safe.split("_") if part) or "unknown"


def _achievement_sport_matches(row: dict[str, Any], sport_family: str) -> bool:
    if sport_family == "running":
        return _is_running_activity(row)
    if sport_family == "cycling":
        return _is_cycling_activity(row)
    return False


def _achievement_sort_key(row: dict[str, Any]) -> tuple[str, str]:
    return (_achievement_event_date(row), str(row.get("id") or ""))


def _first_distance_achievement_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for achievement_type, title, sport_family, low, high, score, icon in ACHIEVEMENT_FIRST_DISTANCE_RULES:
        matched: list[dict[str, Any]] = []
        for row in rows:
            if not _achievement_sport_matches(row, sport_family):
                continue
            distance_km = _activity_distance_km(row)
            if distance_km is None or not (low <= distance_km <= high):
                continue
            matched.append({
                "row": row,
                "achievement_type": achievement_type,
                "title": title,
                "score": score,
                "icon": icon,
                "sport": sport_family,
                "distance_km": round(distance_km, 3),
                "matched_range_km": [low, high],
            })
        if matched:
            candidates.append(sorted(matched, key=lambda item: _achievement_sort_key(item["row"]))[0])
    return candidates


def _record_achievement_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    running_rows: list[tuple[dict[str, Any], float]] = []
    cycling_rows: list[tuple[dict[str, Any], float]] = []
    ascent_rows: list[tuple[dict[str, Any], float]] = []
    for row in rows:
        distance_km = _activity_distance_km(row)
        if distance_km is not None and distance_km > 0:
            if _is_running_activity(row):
                running_rows.append((row, distance_km))
            if _is_cycling_activity(row):
                cycling_rows.append((row, distance_km))
        ascent_m = _achievement_ascent_m(row)
        if ascent_m is not None and ascent_m > 0:
            ascent_rows.append((row, ascent_m))

    record_specs = (
        ("longest_running", running_rows, "distance_km", 90, "route"),
        ("longest_cycling", cycling_rows, "distance_km", 90, "bike"),
        ("max_ascent", ascent_rows, "ascent_m", 85, "mountain"),
    )
    for achievement_type, values, metadata_key, score, icon in record_specs:
        if not values:
            continue
        row, value = sorted(
            values,
            key=lambda item: (float(item[1]), _achievement_event_date(item[0]), str(item[0].get("id") or "")),
            reverse=True,
        )[0]
        candidates.append({
            "row": row,
            "achievement_type": achievement_type,
            "title": ACHIEVEMENT_TITLES[achievement_type],
            "score": score,
            "icon": icon,
            "sport": "cycling" if achievement_type == "longest_cycling" else ("running" if achievement_type == "longest_running" else "all"),
            metadata_key: round(float(value), 3),
            "record_value": round(float(value), 3),
            "record_unit": "m" if metadata_key == "ascent_m" else "km",
        })
    return candidates


def _first_city_achievement_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_city: dict[str, dict[str, Any]] = {}
    for row in rows:
        city = _achievement_city(row)
        if not city:
            continue
        city_key = _achievement_city_key(city)
        candidate = {
            "row": row,
            "achievement_type": "first_city",
            "title": ACHIEVEMENT_TITLES["first_city"],
            "score": 60,
            "icon": "map-pin",
            "sport": "all",
            "city": city,
            "city_key": city_key,
        }
        current = by_city.get(city_key)
        if current is None or _achievement_sort_key(row) < _achievement_sort_key(current["row"]):
            by_city[city_key] = candidate
    return list(by_city.values())


def _annual_milestone_achievement_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_year: dict[int, dict[str, Any]] = {}
    for row in rows:
        event_date = _achievement_event_date(row)
        if len(event_date) < 4 or not event_date[:4].isdigit():
            continue
        year = int(event_date[:4])
        bucket = by_year.setdefault(
            year,
            {
                "year": year,
                "activity_count": 0,
                "total_distance_km": 0.0,
                "activity_days": set(),
                "latest_row": row,
            },
        )
        bucket["activity_count"] = int(bucket["activity_count"]) + 1
        distance_km = _activity_distance_km(row)
        if distance_km is not None and distance_km > 0:
            bucket["total_distance_km"] = float(bucket["total_distance_km"]) + float(distance_km)
        if len(event_date) >= 10:
            bucket["activity_days"].add(event_date[:10])
        if _achievement_sort_key(row) >= _achievement_sort_key(bucket["latest_row"]):
            bucket["latest_row"] = row

    candidates: list[dict[str, Any]] = []
    for year, bucket in sorted(by_year.items()):
        activity_count = int(bucket["activity_count"])
        total_distance_km = round(float(bucket["total_distance_km"]), 3)
        if activity_count < 50 and total_distance_km < 500:
            continue
        candidates.append({
            "row": bucket["latest_row"],
            "achievement_type": "annual_milestone",
            "title": f"{year} 年度运动里程碑",
            "score": 80 if activity_count < 100 and total_distance_km < 1000 else 90,
            "icon": "calendar-check",
            "sport": "all",
            "year": year,
            "activity_count": activity_count,
            "total_distance_km": total_distance_km,
            "activity_days": len(bucket["activity_days"]),
        })
    return candidates


def _achievement_description(candidate: dict[str, Any]) -> str:
    achievement_type = str(candidate.get("achievement_type") or "")
    if achievement_type == "annual_milestone":
        return (
            f"{candidate.get('year')} 年累计 "
            f"{candidate.get('activity_count')} 次运动，"
            f"{candidate.get('total_distance_km')} km"
        )
    if achievement_type == "first_city":
        return f"首次在{candidate.get('city')}留下运动记录"
    if "distance_km" in candidate:
        return f"{candidate.get('title')}：{candidate.get('distance_km')} km"
    if "ascent_m" in candidate:
        return f"{candidate.get('title')}：{candidate.get('ascent_m')} m"
    return str(candidate.get("title") or "")


def _active_achievement_row(conn: sqlite3.Connection, achievement_type: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, activity_id, display_metadata_json
        FROM career_achievement_events
        WHERE achievement_type = ? AND status = 'active'
        ORDER BY event_date DESC, id DESC
        LIMIT 1
        """,
        (achievement_type,),
    ).fetchone()
    if row is None:
        return None
    if isinstance(row, sqlite3.Row):
        return dict(row)
    return {"id": row[0], "activity_id": row[1], "display_metadata_json": row[2]}


def _achievement_candidate_id(candidate: dict[str, Any]) -> str:
    achievement_type = str(candidate["achievement_type"])
    activity_id = str(candidate["row"].get("id") or "")
    if achievement_type == "annual_milestone":
        return f"achievement:annual_milestone:{candidate.get('year')}:{activity_id}"
    if achievement_type == "first_city":
        return f"achievement:first_city:{candidate.get('city_key')}:{activity_id}"
    return f"achievement:{achievement_type}:{activity_id}"


def _upsert_achievement_event(
    conn: sqlite3.Connection,
    candidate: dict[str, Any],
    previous: dict[str, Any] | None = None,
) -> None:
    row = candidate["row"]
    achievement_type = str(candidate["achievement_type"])
    activity_id = str(row.get("id") or "")
    previous_metadata = _json_loads_object((previous or {}).get("display_metadata_json"))
    metadata: dict[str, Any] = {
        "resolver": "achievement",
        "achievement_type": achievement_type,
    }
    for key in (
        "sport",
        "distance_km",
        "ascent_m",
        "city",
        "matched_range_km",
        "record_value",
        "record_unit",
        "year",
        "activity_count",
        "total_distance_km",
        "activity_days",
    ):
        if key in candidate:
            metadata[key] = candidate[key]
    if achievement_type in {"longest_running", "longest_cycling", "max_ascent"} and previous and str(previous.get("activity_id") or "") != activity_id:
        metadata["previous_activity_id"] = str(previous.get("activity_id") or "")
        for key in ("distance_km", "ascent_m", "record_value"):
            if key in previous_metadata:
                metadata["previous_value"] = previous_metadata[key]
                break
    conn.execute(
        """
        INSERT INTO career_achievement_events
            (id, activity_id, achievement_type, title, event_date, score, icon, description,
             confidence, source, status, display_metadata_json, updated_at)
        VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, 1.0, 'resolver', 'active', ?, CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
            activity_id = excluded.activity_id,
            achievement_type = excluded.achievement_type,
            title = excluded.title,
            event_date = excluded.event_date,
            score = excluded.score,
            icon = excluded.icon,
            description = excluded.description,
            confidence = excluded.confidence,
            source = excluded.source,
            status = 'active',
            display_metadata_json = excluded.display_metadata_json,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            _achievement_candidate_id(candidate),
            activity_id,
            achievement_type,
            str(candidate["title"]),
            _achievement_event_date(row),
            int(candidate["score"]),
            str(candidate["icon"]),
            _achievement_description(candidate),
            _json_dumps(metadata),
        ),
    )


def _supersede_other_achievements(conn: sqlite3.Connection, candidate: dict[str, Any]) -> None:
    achievement_type = str(candidate["achievement_type"])
    activity_id = str(candidate["row"].get("id") or "")
    if achievement_type == "first_city":
        pattern = f"achievement:first_city:{candidate.get('city_key')}:%"
        conn.execute(
            """
            UPDATE career_achievement_events
            SET status = 'superseded', updated_at = CURRENT_TIMESTAMP
            WHERE achievement_type = 'first_city'
              AND id LIKE ?
              AND activity_id != ?
              AND status = 'active'
            """,
            (pattern, activity_id),
        )
        return
    if achievement_type == "annual_milestone":
        pattern = f"achievement:annual_milestone:{candidate.get('year')}:%"
        conn.execute(
            """
            UPDATE career_achievement_events
            SET status = 'superseded', updated_at = CURRENT_TIMESTAMP
            WHERE achievement_type = 'annual_milestone'
              AND id LIKE ?
              AND activity_id != ?
              AND status = 'active'
            """,
            (pattern, activity_id),
        )
        return
    conn.execute(
        """
        UPDATE career_achievement_events
        SET status = 'superseded', updated_at = CURRENT_TIMESTAMP
        WHERE achievement_type = ?
          AND activity_id != ?
          AND status = 'active'
        """,
        (achievement_type, activity_id),
    )


def _achievement_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return (
        _first_distance_achievement_candidates(rows)
        + _record_achievement_candidates(rows)
        + _first_city_achievement_candidates(rows)
        + _annual_milestone_achievement_candidates(rows)
    )


def resolve_achievement_events(conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """Resolve Activity-backed achievement events from safe summaries."""
    owns_conn = conn is None
    db = conn or _connect_default()
    processed = 0
    achievement_events_upserted = 0
    skipped = 0
    try:
        schema = ensure_career_schema(db)
        rows = _fetch_achievement_resolver_activity_rows(db)
        processed = len(rows)
        candidates = _achievement_candidates(rows)
        touched_activity_ids = {str(candidate["row"].get("id") or "") for candidate in candidates}
        for candidate in candidates:
            achievement_type = str(candidate["achievement_type"])
            previous = _active_achievement_row(db, achievement_type)
            if achievement_type in {"first_city", "annual_milestone"} or achievement_type.startswith("first_"):
                previous = None
            if previous and str(previous.get("activity_id") or "") == str(candidate["row"].get("id") or ""):
                previous = None
            _upsert_achievement_event(db, candidate, previous)
            _supersede_other_achievements(db, candidate)
            achievement_events_upserted += 1
        skipped = max(0, processed - len(touched_activity_ids))

        if owns_conn:
            db.commit()
        return {
            "ok": True,
            "processed": processed,
            "achievement_events_upserted": achievement_events_upserted,
            "skipped": skipped,
            "status": {
                "schema_ready": bool(schema.get("ok")),
                "resolver": "achievement",
                "message": "成就解析完成",
            },
        }
    except Exception:
        if owns_conn:
            db.rollback()
        raise
    finally:
        if owns_conn:
            db.close()


def refresh_career_derived_events(conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """Refresh all Activity-backed ACS derived events in resolver ownership order."""
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        schema = ensure_career_schema(db)
        race_result = resolve_race_events(db)
        pb_result = resolve_pb_records(db)
        achievement_result = resolve_achievement_events(db)
        if owns_conn:
            db.commit()
        return {
            "ok": True,
            "race": race_result,
            "pb": pb_result,
            "achievement": achievement_result,
            "status": {
                "schema_ready": bool(schema.get("ok")),
                "message": "运动生涯派生事件已刷新",
            },
        }
    except Exception:
        if owns_conn:
            db.rollback()
        raise
    finally:
        if owns_conn:
            db.close()


def _create_table_if_missing(
    conn: sqlite3.Connection,
    table_name: str,
    create_sql: str,
    created: list[str],
) -> None:
    if not _table_exists(conn, table_name):
        created.append(table_name)
    conn.execute(create_sql)


def _ensure_career_business_tables(conn: sqlite3.Connection, created: list[str]) -> None:
    """Create ACS derived-index tables without copying Activity raw facts."""
    _create_table_if_missing(
        conn,
        "career_race_events",
        """
        CREATE TABLE IF NOT EXISTS career_race_events (
            id TEXT PRIMARY KEY,
            activity_id TEXT NOT NULL,
            name TEXT NOT NULL,
            event_type TEXT NOT NULL,
            sport TEXT NOT NULL,
            event_date TEXT NOT NULL,
            location_json TEXT NOT NULL DEFAULT '{}',
            performance_summary_json TEXT NOT NULL DEFAULT '{}',
            achievement_ids_json TEXT NOT NULL DEFAULT '[]',
            confidence REAL NOT NULL DEFAULT 0.0 CHECK (confidence >= 0.0 AND confidence <= 1.0),
            source TEXT NOT NULL DEFAULT 'resolver',
            status TEXT NOT NULL DEFAULT 'active',
            display_metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        created,
    )
    _create_table_if_missing(
        conn,
        "career_pb_records",
        """
        CREATE TABLE IF NOT EXISTS career_pb_records (
            id TEXT PRIMARY KEY,
            activity_id TEXT NOT NULL,
            sport TEXT NOT NULL,
            pb_type TEXT NOT NULL,
            value TEXT NOT NULL,
            value_unit TEXT NOT NULL DEFAULT '',
            improvement TEXT,
            event_date TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 1.0 CHECK (confidence >= 0.0 AND confidence <= 1.0),
            source TEXT NOT NULL DEFAULT 'resolver',
            status TEXT NOT NULL DEFAULT 'active',
            display_metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        created,
    )
    _create_table_if_missing(
        conn,
        "career_achievement_events",
        """
        CREATE TABLE IF NOT EXISTS career_achievement_events (
            id TEXT PRIMARY KEY,
            activity_id TEXT NOT NULL,
            achievement_type TEXT NOT NULL,
            title TEXT NOT NULL,
            event_date TEXT NOT NULL,
            score INTEGER NOT NULL DEFAULT 0,
            icon TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            confidence REAL NOT NULL DEFAULT 1.0 CHECK (confidence >= 0.0 AND confidence <= 1.0),
            source TEXT NOT NULL DEFAULT 'resolver',
            status TEXT NOT NULL DEFAULT 'active',
            display_metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        created,
    )
    _create_table_if_missing(
        conn,
        "career_memory_items",
        """
        CREATE TABLE IF NOT EXISTS career_memory_items (
            id TEXT PRIMARY KEY,
            race_id TEXT,
            activity_id TEXT NOT NULL,
            memory_type TEXT NOT NULL,
            storage_ref TEXT NOT NULL DEFAULT '',
            story_text TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        created,
    )
    _create_table_if_missing(
        conn,
        "career_snapshots",
        """
        CREATE TABLE IF NOT EXISTS career_snapshots (
            id TEXT PRIMARY KEY,
            snapshot_type TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            content_json TEXT NOT NULL DEFAULT '{}',
            source_version TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        created,
    )
    _create_table_if_missing(
        conn,
        "career_event_candidates",
        """
        CREATE TABLE IF NOT EXISTS career_event_candidates (
            id TEXT PRIMARY KEY,
            activity_id TEXT NOT NULL,
            candidate_type TEXT NOT NULL,
            title TEXT NOT NULL,
            evidence_json TEXT NOT NULL DEFAULT '{}',
            confidence REAL NOT NULL DEFAULT 0.0 CHECK (confidence >= 0.0 AND confidence <= 1.0),
            status TEXT NOT NULL DEFAULT 'candidate',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        created,
    )


def _ensure_career_light_memory_columns(conn: sqlite3.Connection, migrated: list[str]) -> None:
    _add_column_if_missing(conn, "career_memory_items", "title", "TEXT NOT NULL DEFAULT ''", migrated)
    _add_column_if_missing(conn, "career_memory_items", "event_date", "TEXT NOT NULL DEFAULT ''", migrated)
    _add_column_if_missing(conn, "career_memory_items", "status", "TEXT NOT NULL DEFAULT 'active'", migrated)


def _ensure_career_indexes(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_career_race_events_activity
        ON career_race_events(activity_id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_career_race_events_date_status
        ON career_race_events(event_date, status)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_career_pb_records_activity
        ON career_pb_records(activity_id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_career_pb_records_sport_type_date
        ON career_pb_records(sport, pb_type, event_date)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_career_achievement_events_activity
        ON career_achievement_events(activity_id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_career_achievement_events_date_score
        ON career_achievement_events(event_date, score)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_career_memory_items_activity
        ON career_memory_items(activity_id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_career_memory_items_race
        ON career_memory_items(race_id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_career_memory_items_status_date
        ON career_memory_items(status, event_date)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_career_snapshots_type_generated
        ON career_snapshots(snapshot_type, generated_at)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_career_event_candidates_activity
        ON career_event_candidates(activity_id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_career_event_candidates_status
        ON career_event_candidates(status, confidence)
        """
    )


def ensure_career_schema(conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """Ensure the ACS schema baseline and derived-index tables exist."""
    owns_conn = conn is None
    db = conn or _connect_default()
    created: list[str] = []
    migrated: list[str] = []
    try:
        if not _table_exists(db, "career_schema_meta"):
            created.append("career_schema_meta")
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS career_schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        existing = db.execute(
            "SELECT value FROM career_schema_meta WHERE key = 'schema_version'"
        ).fetchone()
        existing_value = existing[0] if existing is not None else None
        if existing_value != CAREER_SCHEMA_VERSION:
            migrated.append("schema_version")
        db.execute(
            """
            INSERT INTO career_schema_meta (key, value, updated_at)
            VALUES ('schema_version', ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (CAREER_SCHEMA_VERSION, _utc_now_iso()),
        )
        _ensure_career_business_tables(db, created)
        _ensure_career_light_memory_columns(db, migrated)
        _ensure_career_indexes(db)

        if owns_conn:
            db.commit()
        return {
            "ok": True,
            "schema_version": CAREER_SCHEMA_VERSION,
            "created": created,
            "migrated": migrated,
        }
    except Exception:
        if owns_conn:
            db.rollback()
        raise
    finally:
        if owns_conn:
            db.close()


def _increment_counter(target: dict[str, int], key: str) -> None:
    clean_key = str(key or "unknown").strip() or "unknown"
    target[clean_key] = target.get(clean_key, 0) + 1


def _race_event_type_label(event_type: Any) -> str:
    key = str(event_type or "race").strip().lower() or "race"
    labels = {
        "5k": "5K",
        "10k": "10K",
        "half_marathon": "半程马拉松",
        "marathon": "马拉松",
        "trail_race": "越野赛",
        "triathlon": "铁人三项",
        "race": "赛事",
    }
    return labels.get(key, key)


def _career_sport_label(sport: Any) -> str:
    key = str(sport or "").strip().lower()
    family = _career_identity_sport_family(key)
    if family == "running":
        return "跑步"
    if family == "cycling":
        return "骑行"
    return "未知运动"


def _race_source_label(source: Any) -> str:
    key = str(source or "resolver").strip().lower() or "resolver"
    labels = {
        "user": "用户确认",
        "fit_sport_event": "设备赛事标记",
        "resolver": "规则识别",
        "title_distance": "规则识别",
        "activity_race_confidence": "规则识别",
    }
    return labels.get(key, key)


def _race_confidence_label(confidence_level: Any, confidence: Any) -> str:
    key = str(confidence_level or "").strip().lower()
    if key == "high":
        return "高置信度"
    if key == "medium":
        return "中置信度"
    if key == "low":
        return "低置信度"
    try:
        score = float(confidence)
    except (TypeError, ValueError):
        score = 0.0
    if score >= 0.85:
        return "高置信度"
    if score >= 0.6:
        return "中置信度"
    if score > 0:
        return "低置信度"
    return "置信度未知"


def _race_display_date_parts(event_date: Any) -> tuple[int | None, int | None, str]:
    text = str(event_date or "").strip()
    year = None
    month = None
    if len(text) >= 4 and text[:4].isdigit():
        year = int(text[:4])
    if len(text) >= 7 and text[5:7].isdigit():
        month = int(text[5:7])
    return year, month, text[:10] if text else ""


def _race_metric(label: str, value: Any) -> dict[str, str] | None:
    clean_value = str(value or "").strip()
    if not clean_value:
        return None
    return {"label": label, "value": clean_value}


def _race_compact_duration_display(value: Any) -> str:
    seconds = _safe_int(value, default=0)
    if seconds <= 0:
        return ""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _race_pace_display(seconds_per_km: Any) -> str:
    seconds = _safe_int(seconds_per_km, default=0)
    if seconds <= 0:
        return ""
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes}'{secs:02d}\"/km"


def _race_speed_display(distance_km: float | None, duration_sec: int | None) -> str:
    if distance_km is None or distance_km <= 0 or duration_sec is None or duration_sec <= 0:
        return ""
    speed = distance_km / (duration_sec / 3600.0)
    return f"{speed:.1f} km/h"


def _race_elevation_display(value: Any) -> str:
    gain = _safe_float(value)
    if gain is None or gain <= 0:
        return ""
    return f"{int(round(gain))} m"


def _race_card_metrics_from_activity(race: dict[str, Any], activity_row: dict[str, Any] | None) -> list[dict[str, str]]:
    row = activity_row or {}
    summary = race.get("performance_summary") if isinstance(race.get("performance_summary"), dict) else {}
    sport = str(race.get("sport") or row.get("sport_type") or "").lower()
    event_type = str(race.get("event_type") or "").lower()
    distance_km = _activity_distance_km(row)
    duration_sec = _activity_duration_sec(row)
    pace = row.get("avg_pace")
    if pace is None and distance_km and duration_sec:
        pace = round(duration_sec / distance_km)
    duration_text = (
        summary.get("duration_text")
        or summary.get("result_text")
        or _race_compact_duration_display(duration_sec)
    )
    distance_text = _distance_display(distance_km)
    pace_text = summary.get("pace_text") or _race_pace_display(pace)
    speed_text = summary.get("speed_text") or _race_speed_display(distance_km, duration_sec)
    hr_value = _safe_int(row.get("avg_hr"), default=0)
    hr_text = summary.get("avg_hr_text") or summary.get("avg_heart_rate_text") or (f"{hr_value} bpm" if hr_value > 0 else "")
    elevation_text = summary.get("elevation_gain_text") or _race_elevation_display(row.get("gain_m"))
    power_value = _safe_int(row.get("avg_power"), default=0)
    power_text = summary.get("avg_power_text") or (f"{power_value} W" if power_value > 0 else "")
    calories_value = _safe_int(row.get("calories"), default=0)
    calories_text = summary.get("calories_text") or (f"{calories_value} kcal" if calories_value > 0 else "")
    rank_text = summary.get("rank_text")

    if sport in {"cycling", "road_cycling", "mountain_biking", "indoor_cycling"}:
        candidates = [
            _race_metric("时间", duration_text),
            _race_metric("距离", distance_text),
            _race_metric("均速", speed_text),
            _race_metric("爬升", elevation_text),
            _race_metric("功率", power_text),
            _race_metric("心率", hr_text),
        ]
    elif sport in {"trail_running", "hiking", "mountaineering"} or "trail" in event_type:
        candidates = [
            _race_metric("成绩", duration_text),
            _race_metric("距离", distance_text),
            _race_metric("爬升", elevation_text),
            _race_metric("心率", hr_text),
            _race_metric("配速", pace_text),
            _race_metric("排名", rank_text),
        ]
    else:
        candidates = [
            _race_metric("成绩", duration_text),
            _race_metric("距离", distance_text),
            _race_metric("配速", pace_text),
            _race_metric("心率", hr_text),
            _race_metric("排名", rank_text),
            _race_metric("热量", calories_text),
        ]
    return [item for item in candidates if item][:4]


def _build_race_record(row: dict[str, Any]) -> dict[str, Any]:
    location = _json_loads_object(row.get("location_json"))
    performance_summary = _sanitize_public_metadata(_json_loads_object(row.get("performance_summary_json")))
    display_metadata = _sanitize_public_metadata(_json_loads_object(row.get("display_metadata_json")))
    evidence = _json_loads_object(display_metadata.get("evidence"))
    confidence_level = str(
        display_metadata.get("confidence_level")
        or evidence.get("confidence_level")
        or ""
    ).strip()
    activity_id = str(row.get("activity_id") or "")
    event_type = str(row.get("event_type") or "race")
    sport = str(row.get("sport") or "unknown")
    event_date = str(row.get("event_date") or "")
    source = str(row.get("source") or "resolver")
    confidence = float(row.get("confidence") or 0.0)
    year, month, display_date = _race_display_date_parts(event_date)
    city = str(location.get("city") or "")
    return {
        "id": str(row.get("id") or ""),
        "activity_id": activity_id,
        "name": str(row.get("name") or ""),
        "race_title": str(row.get("name") or ""),
        "event_type": event_type,
        "event_type_label": _race_event_type_label(event_type),
        "sport": sport,
        "sport_label": _career_sport_label(sport),
        "event_date": event_date,
        "year": year,
        "month": month,
        "display_date": display_date,
        "city": city,
        "location": {
            "city": city,
            "display": city,
        },
        "performance_summary": performance_summary,
        "confidence": confidence,
        "source": source,
        "source_label": _race_source_label(source),
        "confidence_level": confidence_level or "unknown",
        "confidence_label": _race_confidence_label(confidence_level, confidence),
        "is_user_confirmed": source == "user",
        "display_metadata": display_metadata,
        "detail_link": {
            "activity_id": activity_id,
            "source": "career",
        },
    }


def _race_map_activity_select_expr(conn: sqlite3.Connection, column_name: str) -> str:
    if column_name in RACE_FORBIDDEN_ACTIVITY_COLUMNS:
        raise ValueError(f"Forbidden ACS activity column: {column_name}")
    if _column_exists(conn, "activities", column_name):
        return f"a.{column_name} AS {column_name}"
    return f"NULL AS {column_name}"


def _valid_coordinate(lat: float | None, lon: float | None) -> bool:
    if lat is None or lon is None:
        return False
    return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0


def _race_map_region_display(row: dict[str, Any], location: dict[str, Any]) -> str:
    for key in ("region_display", "region", "region_city"):
        value = " ".join(str(row.get(key) or "").split())
        if value:
            return value[:80]
    city = " ".join(str(location.get("city") or "").split())
    return city[:80]


def _build_race_map_record(row: dict[str, Any], *, with_coordinates: bool, reason: str = "") -> dict[str, Any]:
    location = _json_loads_object(row.get("location_json"))
    activity_id = str(row.get("activity_id") or "")
    event_type = str(row.get("event_type") or "race")
    sport = str(row.get("sport") or "unknown")
    source = str(row.get("source") or "resolver")
    city = str(location.get("city") or row.get("region_city") or "").strip()
    region_display = _race_map_region_display(row, location)
    record = {
        "id": str(row.get("id") or ""),
        "activity_id": activity_id,
        "title": str(row.get("name") or ""),
        "sport": sport,
        "sport_label": _career_sport_label(sport),
        "event_type": event_type,
        "event_type_label": _race_event_type_label(event_type),
        "event_date": str(row.get("event_date") or ""),
        "city": city[:80],
        "region_display": region_display,
        "confidence": float(row.get("confidence") or 0.0),
        "source": source,
        "source_label": _race_source_label(source),
        "detail_link": {
            "activity_id": activity_id,
            "source": "career",
        },
    }
    if with_coordinates:
        record["lat"] = round(float(row.get("start_lat")), 6)
        record["lon"] = round(float(row.get("start_lon")), 6)
    else:
        record["reason"] = reason or "missing_start_coordinates"
    return record


def _summarize_race_map(locations: list[dict[str, Any]], without_coordinates: list[dict[str, Any]]) -> dict[str, int]:
    all_items = locations + without_coordinates
    cities = {
        str(item.get("city") or item.get("region_display") or "").strip()
        for item in all_items
        if str(item.get("city") or item.get("region_display") or "").strip()
    }
    countries = {
        str(item.get("country") or "").strip()
        for item in all_items
        if str(item.get("country") or "").strip()
    }
    return {
        "total": len(all_items),
        "with_coordinates": len(locations),
        "without_coordinates": len(without_coordinates),
        "city_count": len(cities),
        "country_count": len(countries),
    }


def get_career_race_map(
    filters: dict[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Return safe ACS Race Map points from Activity start coordinates only."""
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        schema = ensure_career_schema(db)
        normalized_filters = _normalize_race_filters(filters)
        map_filters = {
            "sport": normalized_filters["sport"],
            "year": normalized_filters["year"],
        }
        if not _table_exists(db, "activities"):
            return {
                "locations": [],
                "without_coordinates": [],
                "summary": _summarize_race_map([], []),
                "filters": map_filters,
                "status": {
                    "schema_ready": bool(schema.get("ok")),
                    "data_ready": False,
                    "message": CAREER_RACE_MAP_EMPTY_STATUS_MESSAGE,
                },
            }

        where_parts = ["r.status = 'active'"]
        params: list[Any] = []
        if normalized_filters["sport"] != "all":
            where_parts.append("r.sport = ?")
            params.append(normalized_filters["sport"])
        if normalized_filters["year"] is not None:
            where_parts.append("substr(r.event_date, 1, 4) = ?")
            params.append(str(normalized_filters["year"]))
        if _column_exists(db, "activities", "deleted_at"):
            where_parts.append("(a.deleted_at IS NULL OR TRIM(COALESCE(a.deleted_at, '')) = '')")

        activity_columns = (
            "start_lat",
            "start_lon",
            "region",
            "region_city",
            "region_country",
            "region_display",
        )
        select_activity = ",\n                   ".join(
            _race_map_activity_select_expr(db, column_name)
            for column_name in activity_columns
        )
        cursor = db.execute(
            f"""
            SELECT r.id, r.activity_id, r.name, r.event_type, r.sport, r.event_date,
                   r.location_json, r.confidence, r.source,
                   {select_activity}
            FROM career_race_events r
            INNER JOIN activities a ON CAST(a.id AS TEXT) = CAST(r.activity_id AS TEXT)
            WHERE {' AND '.join(where_parts)}
            ORDER BY r.event_date DESC, r.id DESC
            """,
            tuple(params),
        )
        locations: list[dict[str, Any]] = []
        without_coordinates: list[dict[str, Any]] = []
        for row in _rows_to_dicts(cursor):
            lat = _safe_float(row.get("start_lat"))
            lon = _safe_float(row.get("start_lon"))
            if _valid_coordinate(lat, lon):
                row["start_lat"] = lat
                row["start_lon"] = lon
                locations.append(_build_race_map_record(row, with_coordinates=True))
            else:
                reason = "missing_start_coordinates" if lat is None or lon is None else "invalid_start_coordinates"
                without_coordinates.append(_build_race_map_record(row, with_coordinates=False, reason=reason))

        summary = _summarize_race_map(locations, without_coordinates)
        data_ready = bool(locations or without_coordinates)
        return {
            "locations": locations,
            "without_coordinates": without_coordinates,
            "summary": summary,
            "filters": map_filters,
            "status": {
                "schema_ready": bool(schema.get("ok")),
                "data_ready": data_ready,
                "message": CAREER_RACE_MAP_READY_STATUS_MESSAGE if data_ready else CAREER_RACE_MAP_EMPTY_STATUS_MESSAGE,
            },
        }
    finally:
        if owns_conn:
            db.close()


def _pb_type_label(pb_type: Any) -> str:
    key = str(pb_type or "").strip()
    return PB_TYPE_LABELS.get(key, key or "PB")


def _format_duration_seconds(value: Any) -> str:
    seconds = _safe_int(value, default=0)
    if seconds <= 0:
        return ""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    sec = seconds % 60
    if hours:
        return f"{hours}:{minutes:02d}:{sec:02d}"
    return f"{minutes}:{sec:02d}"


def _pb_value_display(value: Any, unit: Any) -> str:
    unit_text = str(unit or "").strip().lower()
    if unit_text == "seconds":
        return _format_duration_seconds(value)
    parsed = _safe_float(value)
    if parsed is None:
        return ""
    if unit_text in {"km", "kilometer", "kilometers"}:
        return f"{parsed:.1f} km".replace(".0 km", " km")
    if unit_text in {"m", "meter", "meters"}:
        return f"{parsed:.0f} m"
    if unit_text in {"km/h", "kph"}:
        return f"{parsed:.1f} km/h".replace(".0 km/h", " km/h")
    return f"{parsed:g} {unit_text}".strip()


def _pb_improvement_display(value: Any, unit: Any) -> str:
    if value in (None, ""):
        return "首次记录"
    unit_text = str(unit or "").strip().lower()
    if unit_text == "seconds":
        formatted = _format_duration_seconds(value)
        return f"提升 {formatted}" if formatted else "暂无提升记录"
    parsed = _safe_float(value)
    if parsed is None or parsed <= 0:
        return "暂无提升记录"
    return f"提升 {parsed:g}"


def _pb_source_label(source: Any) -> str:
    key = str(source or "resolver").strip().lower() or "resolver"
    labels = {
        "resolver": "规则识别",
        "user": "用户确认",
        "manual": "手动导入",
    }
    return labels.get(key, key)


def _achievement_type_label(achievement_type: Any) -> str:
    key = str(achievement_type or "").strip()
    return ACHIEVEMENT_TITLES.get(key, key or "荣誉里程碑")


def _achievement_category(achievement_type: Any) -> str:
    key = str(achievement_type or "").strip()
    if key.startswith("first_running_") or key.startswith("first_cycling_"):
        return "first_distance"
    if key in {"longest_running", "longest_cycling", "max_ascent"}:
        return "record"
    if key == "first_city":
        return "location"
    if key == "annual_milestone":
        return "annual"
    return "general"


def _achievement_category_label(category: Any) -> str:
    key = str(category or "").strip()
    return ACHIEVEMENT_CATEGORY_LABELS.get(key, key or "综合成就")


def _achievement_sport(achievement_type: Any, display_metadata: dict[str, Any]) -> str:
    metadata_sport = str(display_metadata.get("sport") or "").strip().lower()
    if metadata_sport:
        return metadata_sport
    key = str(achievement_type or "").strip()
    if "_running_" in key or key == "longest_running":
        return "running"
    if "_cycling_" in key or key == "longest_cycling":
        return "cycling"
    return "all"


def _achievement_sport_label(sport: Any) -> str:
    key = str(sport or "").strip().lower()
    if key == "all":
        return "综合"
    return _career_sport_label(key)


def _achievement_source_label(source: Any) -> str:
    return _pb_source_label(source)


def _achievement_score_label(score: Any) -> str:
    value = _safe_int(score, default=0)
    return f"{value} 分" if value > 0 else "未评分"


def _build_pb_record(row: dict[str, Any]) -> dict[str, Any]:
    display_metadata = _sanitize_public_metadata(_json_loads_object(row.get("display_metadata_json")))
    confidence_level = str(display_metadata.get("confidence_level") or "").strip()
    activity_id = str(row.get("activity_id") or "")
    improvement_sec = _safe_int(row.get("improvement"), default=0) if row.get("improvement") not in (None, "") else None
    pb_type = str(row.get("pb_type") or "")
    sport = str(row.get("sport") or "unknown")
    event_date = str(row.get("event_date") or "")
    year, month, display_date = _race_display_date_parts(event_date)
    value = _safe_int(row.get("value"), default=0)
    value_unit = str(row.get("value_unit") or "")
    source = str(row.get("source") or "resolver")
    confidence = float(row.get("confidence") or 0.0)
    return {
        "id": str(row.get("id") or ""),
        "activity_id": activity_id,
        "sport": sport,
        "sport_label": _career_sport_label(sport),
        "pb_type": pb_type,
        "pb_type_label": _pb_type_label(pb_type),
        "pb_title": f"{_pb_type_label(pb_type)} PB" if pb_type else "PB",
        "value": value,
        "value_unit": value_unit,
        "value_display": _pb_value_display(value, value_unit),
        "improvement_sec": improvement_sec,
        "improvement_display": _pb_improvement_display(improvement_sec, value_unit),
        "event_date": event_date,
        "year": year,
        "month": month,
        "display_date": display_date,
        "confidence": confidence,
        "source": source,
        "source_label": _pb_source_label(source),
        "confidence_label": _race_confidence_label(confidence_level, confidence),
        "display_metadata": display_metadata,
        "detail_link": {
            "activity_id": activity_id,
            "source": "career",
        },
    }


def _build_achievement_record(row: dict[str, Any]) -> dict[str, Any]:
    display_metadata = _sanitize_public_metadata(_json_loads_object(row.get("display_metadata_json")))
    activity_id = str(row.get("activity_id") or "")
    achievement_type = str(row.get("achievement_type") or "")
    event_date = str(row.get("event_date") or "")
    year, month, display_date = _race_display_date_parts(event_date)
    score = _safe_int(row.get("score"), default=0)
    confidence = float(row.get("confidence") or 0.0)
    source = str(row.get("source") or "resolver")
    category = _achievement_category(achievement_type)
    sport = _achievement_sport(achievement_type, display_metadata)
    return {
        "id": str(row.get("id") or ""),
        "activity_id": activity_id,
        "achievement_type": achievement_type,
        "achievement_type_label": _achievement_type_label(achievement_type),
        "achievement_title": str(row.get("title") or "") or _achievement_type_label(achievement_type),
        "category": category,
        "category_label": _achievement_category_label(category),
        "sport": sport,
        "sport_label": _achievement_sport_label(sport),
        "title": str(row.get("title") or ""),
        "event_date": event_date,
        "year": year,
        "month": month,
        "display_date": display_date,
        "score": score,
        "score_label": _achievement_score_label(score),
        "icon": str(row.get("icon") or ""),
        "description": str(row.get("description") or ""),
        "confidence": confidence,
        "source": source,
        "source_label": _achievement_source_label(source),
        "confidence_label": _race_confidence_label("", confidence),
        "display_metadata": display_metadata,
        "detail_link": {
            "activity_id": activity_id,
            "source": "career",
        },
    }


def _build_timeline_race_node(
    race: dict[str, Any],
    pb_scope_by_activity: dict[str, str] | None = None,
) -> dict[str, Any]:
    year, month, day = _timeline_date_parts(race.get("event_date"))
    event_type = str(race.get("event_type") or "")
    city = str(race.get("city") or "")
    sport = str(race.get("sport") or "")
    activity_id = str(race.get("activity_id") or "")
    pb_badge_scope = (pb_scope_by_activity or {}).get(activity_id, "none")
    return {
        "id": race["id"],
        "type": "race",
        "subtype": event_type,
        "activity_id": activity_id,
        "title": race["name"],
        "badge": event_type,
        "value": "",
        "meta": " · ".join(part for part in (city, _career_sport_label(sport)) if part),
        "event_type": event_type,
        "sport": sport,
        "date": race["event_date"],
        "year": year,
        "month": month,
        "day": day,
        "track": "race",
        "priority": 90,
        "pb_badge_scope": pb_badge_scope if pb_badge_scope in {"career", "season"} else "none",
        "city": city,
        "confidence": race["confidence"],
        "source": race["source"],
        "detail_link": race["detail_link"],
    }


def _pb_timeline_title(pb_type: Any) -> str:
    return PB_TIMELINE_TITLES.get(str(pb_type or ""), "PB")


def _build_timeline_pb_node(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record["id"],
        "type": "pb",
        "activity_id": record["activity_id"],
        "title": _pb_timeline_title(record.get("pb_type")),
        "pb_type": record["pb_type"],
        "sport": record["sport"],
        "date": record["event_date"],
        "value": record["value"],
        "value_unit": record["value_unit"],
        "improvement_sec": record["improvement_sec"],
        "confidence": record["confidence"],
        "source": record["source"],
        "detail_link": record["detail_link"],
    }


def _build_timeline_achievement_node(achievement: dict[str, Any]) -> dict[str, Any]:
    year, month, day = _timeline_date_parts(achievement.get("event_date"))
    achievement_type = str(achievement.get("achievement_type") or "")
    score = achievement["score"]
    return {
        "id": achievement["id"],
        "type": "milestone",
        "subtype": achievement_type,
        "activity_id": achievement["activity_id"],
        "title": achievement["title"],
        "badge": _achievement_type_label(achievement_type),
        "value": str(score) if score not in (None, "") else "",
        "meta": achievement["description"],
        "achievement_type": achievement_type,
        "date": achievement["event_date"],
        "year": year,
        "month": month,
        "day": day,
        "track": "milestone",
        "priority": 60,
        "score": score,
        "icon": achievement["icon"],
        "description": achievement["description"],
        "confidence": achievement["confidence"],
        "source": achievement["source"],
        "detail_link": achievement["detail_link"],
    }


def _timeline_milestone_title(subtype: str, threshold: Any = None, sport: Any = None) -> str:
    template = TIMELINE_06B_MILESTONE_TITLES.get(subtype, subtype or "里程碑")
    if "{sport_label}" in template:
        return template.format(sport_label=_overview_sport_label(sport))
    if "{threshold}" in template:
        return template.format(threshold=threshold)
    return template


def _timeline_format_km(value: Any) -> str:
    parsed = _safe_float(value)
    if parsed is None:
        return ""
    return f"{parsed:.1f} km".replace(".0 km", " km")


def _timeline_format_m(value: Any) -> str:
    parsed = _safe_float(value)
    if parsed is None:
        return ""
    return f"{parsed:.0f} m"


def _timeline_milestone_node(candidate: dict[str, Any]) -> dict[str, Any] | None:
    activity_id = str(candidate.get("activity_id") or "").strip()
    event_date = str(candidate.get("date") or "").strip()[:10]
    if not activity_id or not event_date:
        return None
    year, month, day = _timeline_date_parts(event_date)
    if year is None or month is None or day is None:
        return None
    subtype = str(candidate.get("subtype") or "")
    return {
        "id": str(candidate.get("id") or f"timeline:milestone:{subtype}:{activity_id}"),
        "type": "milestone",
        "subtype": subtype,
        "activity_id": activity_id,
        "title": str(candidate.get("title") or _timeline_milestone_title(subtype, candidate.get("threshold"), candidate.get("sport"))),
        "badge": str(candidate.get("badge") or "里程碑"),
        "value": str(candidate.get("value") or ""),
        "meta": str(candidate.get("meta") or ""),
        "achievement_type": subtype,
        "date": event_date,
        "year": year,
        "month": month,
        "day": day,
        "track": "milestone",
        "priority": int(candidate.get("priority") or 60),
        "score": int(candidate.get("score") or candidate.get("priority") or 60),
        "icon": str(candidate.get("icon") or "sparkles"),
        "description": str(candidate.get("description") or candidate.get("meta") or ""),
        "confidence": float(candidate.get("confidence") or 1.0),
        "source": str(candidate.get("source") or "timeline_milestone"),
        "detail_link": {
            "activity_id": activity_id,
            "source": "career",
        },
    }


def _timeline_active_achievement_milestone_candidates(db: sqlite3.Connection) -> list[dict[str, Any]]:
    achievements = get_career_achievements(
        {
            "achievement_type": "all",
            "year": None,
            "source": "all",
            "min_score": None,
        },
        conn=db,
    ).get("achievements", [])
    candidates: list[dict[str, Any]] = []
    for achievement in achievements:
        subtype = str(achievement.get("achievement_type") or "")
        if subtype not in TIMELINE_06B_ACHIEVEMENT_MILESTONE_TYPES:
            continue
        candidates.append({
            "id": achievement.get("id"),
            "subtype": subtype,
            "activity_id": achievement.get("activity_id"),
            "date": achievement.get("event_date"),
            "title": achievement.get("title") or _timeline_milestone_title(subtype),
            "badge": _timeline_milestone_badge(subtype),
            "value": str(achievement.get("score") or ""),
            "meta": achievement.get("description"),
            "priority": max(60, int(achievement.get("score") or 60)),
            "score": achievement.get("score"),
            "icon": achievement.get("icon") or "sparkles",
            "description": achievement.get("description"),
            "confidence": achievement.get("confidence"),
            "source": achievement.get("source") or "achievement",
        })
    return candidates


def _timeline_activity_rows(db: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = _overview_activity_rows(db)
    return sorted(rows, key=lambda row: (_achievement_event_date(row), str(row.get("id") or "")))


def _timeline_activity_id(row: dict[str, Any]) -> str:
    return str(row.get("id") or "").strip()


def _timeline_activity_date(row: dict[str, Any]) -> str:
    return _achievement_event_date(row)


def _timeline_activity_ascent_m(row: dict[str, Any]) -> float:
    return float(_achievement_ascent_m(row) or 0.0)


def _timeline_activity_max_alt_m(row: dict[str, Any]) -> float:
    return float(_safe_float(row.get("max_alt_m")) or 0.0)


def _timeline_milestone_badge(subtype: str) -> str:
    if subtype.startswith("first_"):
        return "首次"
    if subtype.startswith("total_") or subtype in {"running_distance_milestone", "cycling_distance_milestone"}:
        return "累计"
    if subtype.startswith("year_"):
        return "年度坚持"
    return "成就"


def _timeline_activity_meta(row: dict[str, Any]) -> str:
    title = _overview_activity_title(row)
    sport = _career_sport_label(_overview_activity_sport(row))
    parts = [part for part in (title, sport) if part]
    return " · ".join(parts[:2])


def _timeline_first_activity_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    valid_rows = [row for row in rows if _timeline_activity_id(row) and _timeline_activity_date(row)]
    if not valid_rows:
        return candidates
    first = valid_rows[0]
    candidates.append({
        "subtype": "first_activity",
        "activity_id": _timeline_activity_id(first),
        "date": _timeline_activity_date(first),
        "badge": "首次",
        "value": _overview_sport_label(_overview_activity_sport(first)),
        "meta": _timeline_activity_meta(first),
        "priority": 88,
        "icon": "flag",
    })
    seen_sports: set[str] = set()
    for row in valid_rows:
        sport = _overview_activity_sport(row)
        if sport not in {"running", "cycling", "swimming", "hiking", "walking", "strength"} or sport in seen_sports:
            continue
        seen_sports.add(sport)
        candidates.append({
            "id": f"timeline:milestone:first_sport_activity:{sport}:{_timeline_activity_id(row)}",
            "subtype": "first_sport_activity",
            "activity_id": _timeline_activity_id(row),
            "date": _timeline_activity_date(row),
            "title": _timeline_milestone_title("first_sport_activity", sport=sport),
            "badge": "首次",
            "value": _overview_sport_label(sport),
            "meta": _timeline_activity_meta(row),
            "priority": 80,
            "icon": "flag",
            "sport": sport,
        })
    return candidates


def _timeline_first_race_candidates(db: sqlite3.Connection) -> list[dict[str, Any]]:
    races = get_career_races({"sport": "all", "year": None, "event_type": "all", "source": "all"}, conn=db).get("races", [])
    valid_races = [
        race for race in races
        if str(race.get("activity_id") or "").strip() and str(race.get("event_date") or "").strip()
    ]
    if not valid_races:
        return []
    race = sorted(valid_races, key=lambda item: (str(item.get("event_date") or ""), str(item.get("id") or "")))[0]
    return [{
        "id": f"timeline:milestone:first_race:{race.get('activity_id')}",
        "subtype": "first_race",
        "activity_id": race.get("activity_id"),
        "date": race.get("event_date"),
        "badge": "首次",
        "value": _race_event_type_label(race.get("event_type")),
        "meta": str(race.get("name") or "正式赛事"),
        "priority": 92,
        "icon": "trophy",
        "source": "race_resolver",
    }]


def _timeline_first_distance_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for subtype, sport, low, high, value, priority in TIMELINE_06B_FIRST_DISTANCE_RULES:
        for row in rows:
            if _overview_activity_sport(row) != sport:
                continue
            distance_km = _activity_distance_km(row)
            if distance_km is None or not (low <= distance_km <= high):
                continue
            candidates.append({
                "subtype": subtype,
                "activity_id": _timeline_activity_id(row),
                "date": _timeline_activity_date(row),
                "badge": "首次",
                "value": value,
                "meta": _timeline_activity_meta(row),
                "priority": priority,
                "icon": "flag" if sport == "running" else "bike",
                "sport": sport,
            })
            break
    return candidates


def _timeline_elevation_challenge_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    first_1000 = next((row for row in rows if _timeline_activity_ascent_m(row) >= 1000), None)
    first_2000 = next((row for row in rows if _timeline_activity_ascent_m(row) >= 2000), None)
    if first_2000 is not None:
        candidates.append({
            "subtype": "single_elevation_gain_2000m",
            "activity_id": _timeline_activity_id(first_2000),
            "date": _timeline_activity_date(first_2000),
            "badge": "成就",
            "value": _timeline_format_m(_timeline_activity_ascent_m(first_2000)),
            "meta": _timeline_activity_meta(first_2000),
            "priority": 88,
            "icon": "mountain",
        })
    if first_1000 is not None and _timeline_activity_id(first_1000) != _timeline_activity_id(first_2000 or {}):
        candidates.append({
            "subtype": "single_elevation_gain_1000m",
            "activity_id": _timeline_activity_id(first_1000),
            "date": _timeline_activity_date(first_1000),
            "badge": "成就",
            "value": _timeline_format_m(_timeline_activity_ascent_m(first_1000)),
            "meta": _timeline_activity_meta(first_1000),
            "priority": 82,
            "icon": "mountain",
        })
    return candidates


def _timeline_altitude_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    first_3000 = next((row for row in rows if _timeline_activity_max_alt_m(row) >= 3000), None)
    first_5000 = next((row for row in rows if _timeline_activity_max_alt_m(row) >= 5000), None)
    candidates: list[dict[str, Any]] = []
    if first_5000 is not None:
        candidates.append({
            "subtype": "first_max_altitude_5000m",
            "activity_id": _timeline_activity_id(first_5000),
            "date": _timeline_activity_date(first_5000),
            "badge": "成就",
            "value": _timeline_format_m(_timeline_activity_max_alt_m(first_5000)),
            "meta": _timeline_activity_meta(first_5000),
            "priority": 90,
            "icon": "mountain-snow",
        })
    if first_3000 is not None and _timeline_activity_id(first_3000) != _timeline_activity_id(first_5000 or {}):
        candidates.append({
            "subtype": "first_max_altitude_3000m",
            "activity_id": _timeline_activity_id(first_3000),
            "date": _timeline_activity_date(first_3000),
            "badge": "成就",
            "value": _timeline_format_m(_timeline_activity_max_alt_m(first_3000)),
            "meta": _timeline_activity_meta(first_3000),
            "priority": 84,
            "icon": "mountain-snow",
        })
    return candidates


def _timeline_multi_sport_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    valid_sports = {"running", "cycling", "swimming", "hiking", "walking", "strength"}
    seen: set[str] = set()
    candidates: list[dict[str, Any]] = []
    thresholds = {2: "multi_sport_2_types", 3: "multi_sport_3_types", 5: "multi_sport_5_types"}
    for row in rows:
        sport = _overview_activity_sport(row)
        if sport not in valid_sports or sport in seen:
            continue
        seen.add(sport)
        subtype = thresholds.get(len(seen))
        if not subtype:
            continue
        candidates.append({
            "subtype": subtype,
            "activity_id": _timeline_activity_id(row),
            "date": _timeline_activity_date(row),
            "badge": "成就",
            "value": f"{len(seen)} 类运动",
            "meta": _timeline_activity_meta(row),
            "priority": 78 + len(seen),
            "icon": "sparkles",
        })
    return candidates


def _timeline_yearly_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[int, dict[str, Any]] = {}
    candidates: list[dict[str, Any]] = []
    for row in rows:
        event_date = _timeline_activity_date(row)
        if len(event_date) < 4 or not event_date[:4].isdigit():
            continue
        year = int(event_date[:4])
        bucket = buckets.setdefault(year, {
            "count": 0,
            "running_km": 0.0,
            "cycling_km": 0.0,
            "ascent_m": 0.0,
            "emitted": set(),
        })
        bucket["count"] += 1
        sport = _overview_activity_sport(row)
        distance_km = _activity_distance_km(row) or 0.0
        if sport == "running":
            bucket["running_km"] += distance_km
        if sport == "cycling":
            bucket["cycling_km"] += distance_km
        bucket["ascent_m"] += _timeline_activity_ascent_m(row)

        checks = (
            ("year_activity_100", bucket["count"], 100, "100 次", 82),
            ("year_running_distance_1000km", bucket["running_km"], 1000, "1000 km", 84),
            ("year_cycling_distance_3000km", bucket["cycling_km"], 3000, "3000 km", 84),
            ("year_elevation_gain_50000m", bucket["ascent_m"], 50000, "50000 m", 84),
        )
        for subtype, current, threshold, value, priority in checks:
            if current >= threshold and subtype not in bucket["emitted"]:
                bucket["emitted"].add(subtype)
                candidates.append({
                    "id": f"timeline:milestone:{subtype}:{year}:{_timeline_activity_id(row)}",
                    "subtype": subtype,
                    "activity_id": _timeline_activity_id(row),
                    "date": event_date,
                    "badge": "年度坚持",
                    "value": value,
                    "meta": f"{year} 年由这次活动达成",
                    "priority": priority,
                    "icon": "calendar-check",
                })
    return candidates


def _timeline_add_cumulative_candidate(
    candidates: list[dict[str, Any]],
    emitted: set[tuple[str, int]],
    subtype: str,
    current: float,
    thresholds: tuple[int, ...],
    value_suffix: str,
    row: dict[str, Any],
    priority: int,
) -> None:
    crossed = [threshold for threshold in thresholds if current >= threshold and (subtype, threshold) not in emitted]
    if not crossed:
        return
    threshold = max(crossed)
    for item in crossed:
        emitted.add((subtype, item))
    candidates.append({
        "id": f"timeline:milestone:{subtype}:{threshold}:{_timeline_activity_id(row)}",
        "subtype": subtype,
        "activity_id": _timeline_activity_id(row),
        "date": _timeline_activity_date(row),
        "badge": "累计",
        "value": f"{threshold} {value_suffix}".strip(),
        "threshold": threshold,
        "meta": "由这次活动跨越累计节点",
        "priority": priority,
        "icon": "milestone",
    })


def _timeline_cumulative_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    emitted: set[tuple[str, int]] = set()
    total_count = 0
    total_distance = 0.0
    running_distance = 0.0
    cycling_distance = 0.0
    total_ascent = 0.0
    total_duration_hours = 0.0
    for row in rows:
        if not _timeline_activity_id(row) or not _timeline_activity_date(row):
            continue
        total_count += 1
        distance_km = _activity_distance_km(row) or 0.0
        total_distance += distance_km
        sport = _overview_activity_sport(row)
        if sport == "running":
            running_distance += distance_km
        if sport == "cycling":
            cycling_distance += distance_km
        total_ascent += _timeline_activity_ascent_m(row)
        duration_sec = _activity_duration_sec(row) or 0
        total_duration_hours += duration_sec / 3600.0
        _timeline_add_cumulative_candidate(candidates, emitted, "total_activity_count_milestone", total_count, (100, 200, 300, 500, 1000), "次", row, 76)
        _timeline_add_cumulative_candidate(candidates, emitted, "total_distance_milestone", total_distance, (500, 1000, 2000, 5000, 10000), "km", row, 78)
        _timeline_add_cumulative_candidate(candidates, emitted, "running_distance_milestone", running_distance, (500, 1000, 2000, 5000), "km", row, 80)
        _timeline_add_cumulative_candidate(candidates, emitted, "cycling_distance_milestone", cycling_distance, (1000, 3000, 5000, 10000), "km", row, 80)
        _timeline_add_cumulative_candidate(candidates, emitted, "total_elevation_gain_milestone", total_ascent, (10000, 50000, 100000), "m", row, 80)
        _timeline_add_cumulative_candidate(candidates, emitted, "total_duration_hours_milestone", total_duration_hours, (100, 300, 500, 1000), "小时", row, 78)
    return candidates


def _timeline_activity_milestone_candidates(db: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = _timeline_activity_rows(db)
    return (
        _timeline_first_activity_candidates(rows)
        + _timeline_first_distance_candidates(rows)
        + _timeline_elevation_challenge_candidates(rows)
        + _timeline_altitude_candidates(rows)
        + _timeline_multi_sport_candidates(rows)
        + _timeline_yearly_candidates(rows)
        + _timeline_cumulative_candidates(rows)
        + _timeline_first_race_candidates(db)
    )


def _dedupe_timeline_milestone_nodes(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    seen_subtypes: set[str] = set()
    seen_ids: set[str] = set()
    for candidate in sorted(
        candidates,
        key=lambda item: (
            str(item.get("date") or ""),
            int(item.get("priority") or 0),
            str(item.get("subtype") or ""),
        ),
    ):
        subtype = str(candidate.get("subtype") or "")
        if subtype in TIMELINE_06B_ACHIEVEMENT_MILESTONE_TYPES or (
            subtype.startswith("first_") and subtype != "first_sport_activity"
        ):
            if subtype in seen_subtypes:
                continue
            seen_subtypes.add(subtype)
        node = _timeline_milestone_node(candidate)
        if not node or node["id"] in seen_ids:
            continue
        seen_ids.add(node["id"])
        nodes.append(node)
    return nodes


def _timeline_milestone_nodes(db: sqlite3.Connection, year: int | None = None) -> list[dict[str, Any]]:
    candidates = _timeline_active_achievement_milestone_candidates(db) + _timeline_activity_milestone_candidates(db)
    nodes = _dedupe_timeline_milestone_nodes(candidates)
    if year is not None:
        nodes = [node for node in nodes if node.get("year") == year]
    return nodes


def _timeline_date_parts(event_date: Any) -> tuple[int | None, int | None, int | None]:
    text = str(event_date or "").strip()[:10]
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d")
        return parsed.year, parsed.month, parsed.day
    except (TypeError, ValueError):
        return None, None, None


def _timeline_days_in_month(year: Any, month: Any) -> int:
    try:
        parsed_year = int(year)
        parsed_month = int(month)
        if 1 <= parsed_month <= 12:
            return calendar.monthrange(parsed_year, parsed_month)[1]
    except (TypeError, ValueError):
        pass
    return 31


def _group_timeline_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, dict[int, list[dict[str, Any]]]] = {}
    for node in nodes:
        year = node.get("year")
        month = node.get("month")
        if not isinstance(year, int) or not isinstance(month, int):
            continue
        grouped.setdefault(year, {}).setdefault(month, []).append(node)

    years: list[dict[str, Any]] = []
    for year in sorted(grouped.keys(), reverse=True):
        months: list[dict[str, Any]] = []
        for month in sorted(grouped[year].keys(), reverse=True):
            nodes = sorted(
                grouped[year][month],
                key=lambda item: (
                    str(item.get("date") or ""),
                    str(item.get("type") or ""),
                    str(item.get("id") or ""),
                ),
                reverse=True,
            )
            months.append({
                "year": year,
                "month": month,
                "days_in_month": _timeline_days_in_month(year, month),
                "nodes": nodes,
            })
        years.append({"year": year, "months": months})
    return years


def _attach_timeline_seasons(
    years: list[dict[str, Any]],
    seasons: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    season_by_year = {int(season.get("year") or 0): season for season in seasons}
    enriched: list[dict[str, Any]] = []
    for year_item in years:
        year = int(year_item.get("year") or 0)
        item = dict(year_item)
        season = season_by_year.get(year)
        if season:
            item["season"] = season
        else:
            item["season"] = _build_season_record(_empty_season_bucket(year))
        enriched.append(item)
    return enriched


def _group_timeline_races(races: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _group_timeline_nodes([_build_timeline_race_node(race) for race in races])


def _timeline_pb_badge_scope_by_activity(db: sqlite3.Connection) -> dict[str, str]:
    if not _table_exists(db, "career_pb_records"):
        return {}
    scope_by_activity: dict[str, str] = {}
    rows = db.execute(
        """
        SELECT activity_id, status
        FROM career_pb_records
        WHERE activity_id IS NOT NULL
          AND TRIM(CAST(activity_id AS TEXT)) != ''
        """
    ).fetchall()
    for row in rows:
        activity_id = str(row[0] or "")
        status = str(row[1] or "")
        if not activity_id:
            continue
        if status == "active":
            scope_by_activity[activity_id] = "career"
        elif status == "superseded" and scope_by_activity.get(activity_id) != "career":
            scope_by_activity[activity_id] = "season"
    return scope_by_activity


def _build_timeline_nodes_for_type(
    db: sqlite3.Connection,
    node_type: str,
    year: int | None = None,
) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    if node_type in ("all", "race"):
        pb_scope_by_activity = _timeline_pb_badge_scope_by_activity(db)
        race_filters: dict[str, Any] = {
            "sport": "all",
            "year": year,
            "event_type": "all",
            "source": "all",
        }
        races = get_career_races(race_filters, conn=db).get("races", [])
        nodes.extend(_build_timeline_race_node(race, pb_scope_by_activity) for race in races)
    if node_type == "all" or node_type in CAREER_TIMELINE_MILESTONE_TYPES:
        nodes.extend(_timeline_milestone_nodes(db, year=year))
    return nodes


def _timeline_available_years(nodes: list[dict[str, Any]]) -> list[int]:
    years = {
        int(node["year"])
        for node in nodes
        if isinstance(node.get("year"), int)
    }
    return sorted(years, reverse=True)


def _summarize_races(races: list[dict[str, Any]]) -> dict[str, Any]:
    by_event_type: dict[str, int] = {}
    by_sport: dict[str, int] = {}
    by_year: dict[str, int] = {}
    for race in races:
        _increment_counter(by_event_type, race.get("event_type"))
        _increment_counter(by_sport, race.get("sport"))
        year = str(race.get("event_date") or "")[:4]
        if year.isdigit():
            _increment_counter(by_year, year)
    return {
        "total": len(races),
        "by_event_type": by_event_type,
        "by_sport": by_sport,
        "by_year": by_year,
    }


def _summarize_pb_records(pb_records: list[dict[str, Any]]) -> dict[str, Any]:
    by_pb_type: dict[str, int] = {}
    by_sport: dict[str, int] = {}
    by_year: dict[str, int] = {}
    for record in pb_records:
        _increment_counter(by_pb_type, record.get("pb_type"))
        _increment_counter(by_sport, record.get("sport"))
        year = str(record.get("event_date") or "")[:4]
        if year.isdigit():
            _increment_counter(by_year, year)
    return {
        "total": len(pb_records),
        "by_pb_type": by_pb_type,
        "by_sport": by_sport,
        "by_year": by_year,
    }


def _summarize_achievements(achievements: list[dict[str, Any]]) -> dict[str, Any]:
    by_type: dict[str, int] = {}
    by_category: dict[str, int] = {}
    by_year: dict[str, int] = {}
    by_source: dict[str, int] = {}
    max_score = None
    for achievement in achievements:
        _increment_counter(by_type, achievement.get("achievement_type"))
        _increment_counter(by_category, achievement.get("category"))
        _increment_counter(by_source, achievement.get("source"))
        year = str(achievement.get("event_date") or "")[:4]
        if year.isdigit():
            _increment_counter(by_year, year)
        score = _safe_int(achievement.get("score"), default=0)
        max_score = score if max_score is None else max(max_score, score)
    return {
        "total": len(achievements),
        "by_type": by_type,
        "by_category": by_category,
        "by_year": by_year,
        "by_source": by_source,
        "max_score": max_score,
    }


def _candidate_type_label(candidate_type: Any) -> str:
    key = str(candidate_type or "").strip().lower()
    labels = {
        "race": "赛事候选",
        "achievement": "成就候选",
    }
    return labels.get(key, key or "候选事件")


def _candidate_status_label(status: Any) -> str:
    key = str(status or "").strip().lower()
    labels = {
        "candidate": "待确认",
        "resolved": "已确认",
        "dismissed": "已拒绝",
    }
    return labels.get(key, key or "未知状态")


def _candidate_signal_label(signal: dict[str, Any]) -> str:
    signal_type = str(signal.get("type") or "").strip()
    labels = {
        "standard_distance": "标准距离匹配",
        "weak_title_keyword": "弱标题关键词",
        "title_keyword": "标题关键词",
        "user_confirmation": "用户确认",
        "user_override": "用户覆盖",
        "fit_sport_event": "设备赛事标记",
        "activity_race_confidence": "活动赛事置信度",
        "user_cancellation": "用户取消",
    }
    label = labels.get(signal_type, signal_type or "候选证据")
    detail_parts: list[str] = []
    if signal.get("keyword"):
        detail_parts.append(str(signal.get("keyword")))
    if signal.get("category"):
        detail_parts.append(_race_event_type_label(signal.get("category")))
    distance_km = _safe_float(signal.get("distance_km"))
    if distance_km is not None:
        detail_parts.append(f"{distance_km:g} km")
    return f"{label}（{' · '.join(detail_parts)}）" if detail_parts else label


def _candidate_evidence_summary(evidence: dict[str, Any]) -> list[str]:
    signals = evidence.get("signals")
    if not isinstance(signals, list):
        return []
    summary: list[str] = []
    for signal in signals:
        if isinstance(signal, dict):
            summary.append(_candidate_signal_label(_sanitize_public_metadata(signal)))
    return summary[:5]


def _build_candidate_record(row: dict[str, Any]) -> dict[str, Any]:
    evidence = _sanitize_public_metadata(_json_loads_object(row.get("evidence_json")))
    confidence = float(row.get("confidence") or 0.0)
    candidate_type = str(row.get("candidate_type") or "")
    status = str(row.get("status") or "candidate")
    activity_id = str(row.get("activity_id") or "")
    return {
        "id": str(row.get("id") or ""),
        "activity_id": activity_id,
        "candidate_type": candidate_type,
        "candidate_type_label": _candidate_type_label(candidate_type),
        "title": str(row.get("title") or ""),
        "event_type": str(evidence.get("event_type") or candidate_type or "candidate"),
        "event_type_label": _race_event_type_label(evidence.get("event_type") or candidate_type),
        "confidence": confidence,
        "confidence_label": _race_confidence_label(evidence.get("confidence_level"), confidence),
        "status": status,
        "status_label": _candidate_status_label(status),
        "evidence_summary": _candidate_evidence_summary(evidence),
        "updated_at": str(row.get("updated_at") or ""),
        "detail_link": {
            "activity_id": activity_id,
            "source": "career",
        },
    }


def _summarize_candidates(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    max_confidence = None
    for candidate in candidates:
        _increment_counter(by_type, candidate.get("candidate_type"))
        _increment_counter(by_status, candidate.get("status"))
        confidence = _safe_float(candidate.get("confidence"))
        if confidence is not None:
            max_confidence = confidence if max_confidence is None else max(max_confidence, confidence)
    return {
        "total": len(candidates),
        "by_type": by_type,
        "by_status": by_status,
        "max_confidence": max_confidence,
    }


def _memory_type_label(memory_type: Any) -> str:
    key = str(memory_type or "story").strip().lower() or "story"
    if key == "photo":
        return "照片记忆"
    if key == "track":
        return "轨迹记忆"
    return "故事记忆"


def _build_memory_item(row: dict[str, Any]) -> dict[str, Any] | None:
    metadata = _sanitize_public_metadata(_json_loads_object(row.get("metadata_json")))
    memory_type = str(row.get("memory_type") or "story").strip().lower() or "story"
    if memory_type not in CAREER_MEMORY_TYPES:
        memory_type = "story"
    activity_id = str(row.get("activity_id") or "").strip()
    race_id = str(row.get("race_id") or "").strip()
    if not activity_id and not race_id:
        return None
    title = str(
        row.get("title")
        or metadata.get("title")
        or _memory_type_label(memory_type)
    ).strip()
    event_date = str(
        row.get("event_date")
        or metadata.get("event_date")
        or metadata.get("date")
        or row.get("created_at")
        or ""
    ).strip()[:10]
    storage_ref = str(row.get("storage_ref") or "").strip()
    item = {
        "id": str(row.get("id") or ""),
        "activity_id": activity_id,
        "race_id": race_id,
        "type": memory_type,
        "title": title or _memory_type_label(memory_type),
        "story": str(row.get("story_text") or metadata.get("story") or "").strip(),
        "date": event_date,
        "thumbnail_url": "",
        "has_media": bool(storage_ref and memory_type in {"photo", "track"}),
    }
    if memory_type == "photo" and storage_ref:
        try:
            image_ref = _renderable_image_ref(storage_ref)
        except ValueError:
            image_ref = ""
        if image_ref.startswith("data:image/"):
            item["thumbnail_url"] = image_ref
    if activity_id:
        item["detail_link"] = {
            "activity_id": activity_id,
            "source": "career",
        }
    else:
        item["detail_link"] = {
            "activity_id": "",
            "source": "career",
        }
    return item


def _fetch_memory_row(conn: sqlite3.Connection, memory_id: str) -> dict[str, Any] | None:
    clean_id = str(memory_id or "").strip()
    if not clean_id or not _table_exists(conn, "career_memory_items"):
        return None
    cursor = conn.execute(
        """
        SELECT id, race_id, activity_id, memory_type, title, event_date,
               storage_ref, story_text, metadata_json, status, created_at, updated_at
        FROM career_memory_items
        WHERE id = ?
        LIMIT 1
        """,
        (clean_id,),
    )
    rows = _rows_to_dicts(cursor)
    return rows[0] if rows else None


def _summarize_memory_items(items: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "total": len(items),
        "photo_count": 0,
        "story_count": 0,
        "track_count": 0,
    }
    for item in items:
        memory_type = str(item.get("type") or "story")
        if memory_type == "photo":
            summary["photo_count"] += 1
        elif memory_type == "track":
            summary["track_count"] += 1
        else:
            summary["story_count"] += 1
    return summary


def _safe_activity_year(value: Any) -> int | None:
    text = str(value or "").strip()
    year_text = text[:4]
    if not year_text.isdigit():
        return None
    year = int(year_text)
    if 1900 <= year <= 3000:
        return year
    return None


def _season_activity_rows(conn: sqlite3.Connection, filters: dict[str, Any]) -> list[dict[str, Any]]:
    if not _table_exists(conn, "activities"):
        return []
    columns = {
        "id": "id",
        "start_time": "start_time",
        "start_time_utc": "start_time_utc",
        "dist_km": "dist_km",
        "distance": "distance",
        "duration": "duration",
        "duration_sec": "duration_sec",
        "sport_type": "sport_type",
        "sub_sport_type": "sub_sport_type",
        "sport": "sport",
        "activity_type": "activity_type",
        "region_city": "region_city",
        "city": "city",
        "cityName": "cityName",
    }
    select_parts = [
        f"{column} AS {alias}" if _column_exists(conn, "activities", column) else f"NULL AS {alias}"
        for alias, column in columns.items()
    ]
    where_parts = [_deleted_filter(conn)]
    if filters.get("year") is not None:
        if _column_exists(conn, "activities", "start_time") and _column_exists(conn, "activities", "start_time_utc"):
            date_expr = "COALESCE(NULLIF(start_time, ''), NULLIF(start_time_utc, ''))"
        elif _column_exists(conn, "activities", "start_time"):
            date_expr = "start_time"
        elif _column_exists(conn, "activities", "start_time_utc"):
            date_expr = "start_time_utc"
        else:
            date_expr = "''"
        where_parts.append(f"substr({date_expr}, 1, 4) = '{int(filters['year'])}'")

    cursor = conn.execute(
        f"""
        SELECT {', '.join(select_parts)}
        FROM activities
        WHERE {' AND '.join(where_parts)}
        """
    )
    rows = _rows_to_dicts(cursor)
    sport_filter = str(filters.get("sport") or "all")
    if sport_filter == "all":
        return rows
    filtered: list[dict[str, Any]] = []
    for row in rows:
        sport = _season_activity_sport(row)
        if sport == sport_filter:
            filtered.append(row)
    return filtered


def _season_activity_date(row: dict[str, Any]) -> str:
    return str(row.get("start_time") or row.get("start_time_utc") or "").strip()


def _season_activity_sport(row: dict[str, Any]) -> str:
    for key in ("sport_type", "sub_sport_type", "sport", "activity_type"):
        family = _career_identity_sport_family(row.get(key))
        if family in {"running", "cycling"}:
            return family
    return "unknown"


def _season_activity_city(row: dict[str, Any]) -> str:
    for key in ("region_city", "city", "cityName"):
        city = str(row.get(key) or "").strip()
        if city:
            return city
    return ""


def _empty_season_bucket(year: int) -> dict[str, Any]:
    return {
        "year": year,
        "activity_count": 0,
        "total_distance_km": 0.0,
        "total_duration_seconds": 0,
        "race_count": 0,
        "pb_count": 0,
        "achievement_count": 0,
        "memory_count": 0,
        "cities": set(),
        "sport_counts": {},
    }


def _increment_year_counter(
    buckets: dict[int, dict[str, Any]],
    year: int | None,
    field: str,
    filters: dict[str, Any],
) -> None:
    if year is None:
        return
    if filters.get("year") is not None and int(filters["year"]) != year:
        return
    bucket = buckets.setdefault(year, _empty_season_bucket(year))
    bucket[field] = int(bucket.get(field) or 0) + 1


def _add_season_activity_buckets(
    buckets: dict[int, dict[str, Any]],
    rows: list[dict[str, Any]],
    filters: dict[str, Any],
) -> None:
    for row in rows:
        year = _safe_activity_year(_season_activity_date(row))
        if year is None:
            continue
        if filters.get("year") is not None and int(filters["year"]) != year:
            continue
        bucket = buckets.setdefault(year, _empty_season_bucket(year))
        bucket["activity_count"] = int(bucket.get("activity_count") or 0) + 1
        distance_km = _activity_distance_km(row)
        if distance_km is not None:
            bucket["total_distance_km"] = float(bucket.get("total_distance_km") or 0.0) + float(distance_km)
        duration_sec = _activity_duration_sec(row)
        if duration_sec is not None:
            bucket["total_duration_seconds"] = int(bucket.get("total_duration_seconds") or 0) + int(duration_sec)
        city = _season_activity_city(row)
        if city:
            bucket["cities"].add(city)
        sport = _season_activity_sport(row)
        sport_counts = bucket["sport_counts"]
        sport_counts[sport] = int(sport_counts.get(sport) or 0) + 1


def _season_primary_sport(bucket: dict[str, Any]) -> str:
    counts = {
        key: int(value)
        for key, value in dict(bucket.get("sport_counts") or {}).items()
        if key in {"running", "cycling"} and int(value) > 0
    }
    if not counts:
        return "unknown"
    total = sum(counts.values())
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    top_sport, top_count = ordered[0]
    if len(ordered) > 1 and top_count / max(total, 1) < 0.6:
        return "mixed"
    return top_sport


def _season_stage(bucket: dict[str, Any]) -> str:
    if int(bucket.get("achievement_count") or 0) > 0 or int(bucket.get("pb_count") or 0) > 0:
        return "高光年"
    if int(bucket.get("race_count") or 0) > 0:
        return "赛事年"
    if int(bucket.get("activity_count") or 0) > 0:
        return "记录年"
    return "空白年"


def _season_highlights(bucket: dict[str, Any]) -> list[str]:
    highlights: list[str] = []
    activity_count = int(bucket.get("activity_count") or 0)
    distance_km = round(float(bucket.get("total_distance_km") or 0.0), 2)
    race_count = int(bucket.get("race_count") or 0)
    pb_count = int(bucket.get("pb_count") or 0)
    achievement_count = int(bucket.get("achievement_count") or 0)
    memory_count = int(bucket.get("memory_count") or 0)
    city_count = len(bucket.get("cities") or set())
    if activity_count:
        highlights.append(f"完成 {activity_count} 次活动")
    if distance_km > 0:
        distance_text = f"{distance_km:.1f}".replace(".0", "")
        highlights.append(f"累计 {distance_text} km")
    if race_count:
        highlights.append(f"{race_count} 场赛事")
    if pb_count:
        highlights.append(f"{pb_count} 项 PB")
    if achievement_count:
        highlights.append(f"{achievement_count} 项成就")
    if memory_count:
        highlights.append(f"{memory_count} 条记忆")
    if city_count:
        highlights.append(f"覆盖 {city_count} 城")
    return highlights[:5]


def _build_season_record(bucket: dict[str, Any]) -> dict[str, Any]:
    year = int(bucket.get("year") or 0)
    primary_sport = _season_primary_sport(bucket)
    primary_sport_label = _career_identity_sport_label(primary_sport)
    stage = _season_stage(bucket)
    total_distance_km = round(float(bucket.get("total_distance_km") or 0.0), 2)
    activity_count = int(bucket.get("activity_count") or 0)
    race_count = int(bucket.get("race_count") or 0)
    pb_count = int(bucket.get("pb_count") or 0)
    achievement_count = int(bucket.get("achievement_count") or 0)
    memory_count = int(bucket.get("memory_count") or 0)
    city_count = len(bucket.get("cities") or set())
    if activity_count:
        distance_text = f"，累计 {total_distance_km:.1f} km".replace(".0 km", " km") if total_distance_km else ""
        season_summary = (
            f"{year} 年共完成 {activity_count} 次活动{distance_text}，"
            f"沉淀 {race_count} 场赛事、{pb_count} 项 PB、{achievement_count} 项成就和 {memory_count} 条记忆。"
        )
    else:
        season_summary = f"{year} 年暂无普通活动摘要，仅保留已确认的生涯派生事件。"
    return {
        "year": year,
        "activity_count": activity_count,
        "total_distance_km": total_distance_km,
        "total_duration_seconds": int(bucket.get("total_duration_seconds") or 0),
        "race_count": race_count,
        "pb_count": pb_count,
        "achievement_count": achievement_count,
        "memory_count": memory_count,
        "city_count": city_count,
        "primary_sport": primary_sport,
        "primary_sport_label": primary_sport_label,
        "season_stage": stage,
        "season_title": f"{year} {stage}",
        "season_summary": season_summary,
        "highlights": _season_highlights(bucket),
    }


def _add_derived_season_counts(conn: sqlite3.Connection, buckets: dict[int, dict[str, Any]], filters: dict[str, Any]) -> None:
    if _table_exists(conn, "career_race_events"):
        race_where = ["status = 'active'"]
        race_params: list[Any] = []
        if filters.get("sport") in {"running", "cycling"}:
            race_where.append("sport = ?")
            race_params.append(str(filters["sport"]))
        for row in conn.execute(
            f"SELECT event_date FROM career_race_events WHERE {' AND '.join(race_where)}",
            tuple(race_params),
        ).fetchall():
            _increment_year_counter(buckets, _safe_activity_year(row[0]), "race_count", filters)
    if _table_exists(conn, "career_pb_records"):
        pb_where = ["status = 'active'"]
        pb_params: list[Any] = []
        if filters.get("sport") in {"running", "cycling"}:
            pb_where.append("sport = ?")
            pb_params.append(str(filters["sport"]))
        for row in conn.execute(
            f"SELECT event_date FROM career_pb_records WHERE {' AND '.join(pb_where)}",
            tuple(pb_params),
        ).fetchall():
            _increment_year_counter(buckets, _safe_activity_year(row[0]), "pb_count", filters)
    if _table_exists(conn, "career_achievement_events"):
        for row in conn.execute("SELECT event_date FROM career_achievement_events WHERE status = 'active'").fetchall():
            _increment_year_counter(buckets, _safe_activity_year(row[0]), "achievement_count", filters)
    if _table_exists(conn, "career_memory_items"):
        for row in conn.execute("SELECT event_date FROM career_memory_items WHERE status = 'active'").fetchall():
            _increment_year_counter(buckets, _safe_activity_year(row[0]), "memory_count", filters)


def _build_career_seasons(conn: sqlite3.Connection, filters: dict[str, Any]) -> list[dict[str, Any]]:
    buckets: dict[int, dict[str, Any]] = {}
    _add_season_activity_buckets(buckets, _season_activity_rows(conn, filters), filters)
    _add_derived_season_counts(conn, buckets, filters)
    return [
        _build_season_record(buckets[year])
        for year in sorted(buckets.keys(), reverse=True)
    ]


def _summarize_seasons(seasons: list[dict[str, Any]]) -> dict[str, Any]:
    total_distance = sum(float(season.get("total_distance_km") or 0.0) for season in seasons)
    return {
        "total_seasons": len(seasons),
        "latest_year": int(seasons[0]["year"]) if seasons else None,
        "total_activity_count": sum(int(season.get("activity_count") or 0) for season in seasons),
        "total_distance_km": round(total_distance, 2) if seasons else None,
        "total_race_count": sum(int(season.get("race_count") or 0) for season in seasons),
        "total_pb_count": sum(int(season.get("pb_count") or 0) for season in seasons),
        "total_achievement_count": sum(int(season.get("achievement_count") or 0) for season in seasons),
        "total_memory_count": sum(int(season.get("memory_count") or 0) for season in seasons),
    }


def _date_desc_sort_value(value: Any) -> int:
    digits = "".join(ch for ch in str(value or "")[:10] if ch.isdigit())
    try:
        return -int(digits[:8]) if digits else 0
    except ValueError:
        return 0


def _representative_pb_records(pb_records: list[dict[str, Any]], limit: int = 4) -> list[dict[str, Any]]:
    return sorted(
        pb_records,
        key=lambda record: (
            PB_OVERVIEW_TYPE_PRIORITY.get(str(record.get("pb_type") or ""), 999),
            _date_desc_sort_value(record.get("event_date")),
            str(record.get("id") or ""),
        ),
    )[:limit]


def _representative_achievements(achievements: list[dict[str, Any]], limit: int = 4) -> list[dict[str, Any]]:
    return sorted(
        achievements,
        key=lambda achievement: (
            _safe_int(achievement.get("score"), default=0),
            str(achievement.get("event_date") or ""),
            str(achievement.get("id") or ""),
        ),
        reverse=True,
    )[:limit]


def _latest_pb_record(pb_records: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not pb_records:
        return None
    return sorted(
        pb_records,
        key=lambda record: (
            str(record.get("event_date") or ""),
            str(record.get("id") or ""),
        ),
        reverse=True,
    )[0]


def _build_primary_sport_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    if not _table_exists(conn, "activities"):
        return {"sport": "", "activity_count": 0, "confidence": "none"}
    sport_column = None
    for candidate in ("sport_type", "sport", "activity_type"):
        if _column_exists(conn, "activities", candidate):
            sport_column = candidate
            break
    if not sport_column:
        return {"sport": "", "activity_count": 0, "confidence": "none"}
    where_parts = [f"TRIM(COALESCE({sport_column}, '')) != ''"]
    if _column_exists(conn, "activities", "deleted_at"):
        where_parts.append("(deleted_at IS NULL OR TRIM(COALESCE(deleted_at, '')) = '')")
    row = conn.execute(
        f"""
        SELECT {sport_column} AS sport, COUNT(*) AS activity_count
        FROM activities
        WHERE {' AND '.join(where_parts)}
        GROUP BY {sport_column}
        ORDER BY activity_count DESC, sport ASC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        return {"sport": "", "activity_count": 0, "confidence": "none"}
    return {
        "sport": str(row[0] or ""),
        "activity_count": int(row[1] or 0),
        "confidence": "derived",
    }


def _career_identity_sport_family(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if any(token in text for token in ("running", "run", "跑步", "路跑", "越野跑", "trail")):
        return "running"
    if any(token in text for token in ("cycling", "cycle", "bike", "biking", "ride", "骑行", "公路车", "自行车")):
        return "cycling"
    return "other"


def _career_identity_sport_label(sport: str) -> str:
    key = str(sport or "")
    if key == "running":
        return "跑步"
    if key == "cycling":
        return "骑行"
    if key == "mixed":
        return "多运动"
    return "未知"


def _career_identity_primary_sport(conn: sqlite3.Connection) -> dict[str, Any]:
    if not _table_exists(conn, "activities"):
        return {"primary_sport": "unknown", "primary_sport_label": "未知"}
    sport_column = None
    for candidate in ("sport_type", "sport", "activity_type"):
        if _column_exists(conn, "activities", candidate):
            sport_column = candidate
            break
    if not sport_column:
        return {"primary_sport": "unknown", "primary_sport_label": "未知"}
    where_parts = [f"TRIM(COALESCE({sport_column}, '')) != ''"]
    if _column_exists(conn, "activities", "deleted_at"):
        where_parts.append("(deleted_at IS NULL OR TRIM(COALESCE(deleted_at, '')) = '')")
    rows = conn.execute(
        f"""
        SELECT {sport_column} AS sport, COUNT(*) AS activity_count
        FROM activities
        WHERE {' AND '.join(where_parts)}
        GROUP BY {sport_column}
        """
    ).fetchall()
    counts: dict[str, int] = {}
    for raw_sport, raw_count in rows:
        family = _career_identity_sport_family(raw_sport)
        if not family:
            continue
        counts[family] = counts.get(family, 0) + int(raw_count or 0)
    known_counts = {key: value for key, value in counts.items() if key in ("running", "cycling") and value > 0}
    if not known_counts:
        return {"primary_sport": "unknown", "primary_sport_label": "未知"}
    total_known = sum(known_counts.values())
    ordered = sorted(known_counts.items(), key=lambda item: (-item[1], item[0]))
    top_sport, top_count = ordered[0]
    if len(ordered) > 1 and top_count / max(total_known, 1) < 0.6:
        primary_sport = "mixed"
    else:
        primary_sport = top_sport
    return {
        "primary_sport": primary_sport,
        "primary_sport_label": _career_identity_sport_label(primary_sport),
    }


def _career_identity_stage(activity_count: int, career_years: int) -> str:
    if activity_count <= 0:
        return "等待开启"
    if career_years <= 1:
        return "起步期"
    if career_years <= 3:
        return "积累期"
    return "成熟期"


def _build_career_identity(conn: sqlite3.Connection, summary: dict[str, Any]) -> dict[str, Any]:
    activity_count = _safe_int(summary.get("activity_count"), default=0)
    start_year = summary.get("career_start_year")
    current_year = datetime.now(timezone.utc).year
    if start_year and activity_count > 0:
        career_years = max(1, current_year - int(start_year) + 1)
    else:
        career_years = 0
    stage = _career_identity_stage(activity_count, career_years)
    sport_info = _career_identity_primary_sport(conn)
    primary_sport = sport_info["primary_sport"] if activity_count > 0 else "unknown"
    primary_sport_label = _career_identity_sport_label(primary_sport)
    race_count = _safe_int(summary.get("race_count"), default=0)
    pb_count = _safe_int(summary.get("pb_count"), default=0)
    achievement_count = _safe_int(summary.get("achievement_count"), default=0)
    city_count = _safe_int(summary.get("covered_city_count"), default=0)
    total_distance_km = summary.get("total_distance_km")

    if activity_count <= 0:
        title = "等待开启运动生涯"
        summary_text = "导入运动记录后，脉图会在这里生成你的运动生涯身份、累计足迹和代表经历。"
        tags = ["等待首条运动记录"]
        who_answer = "你的运动生涯身份将在活动导入后生成。"
        journey_answer = "暂无累计足迹。"
        experience_answer = "暂无赛事、PB 或荣誉经历。"
    else:
        title_prefix = primary_sport_label if primary_sport != "unknown" else ""
        title = f"{title_prefix}{stage}运动者" if title_prefix else f"{stage}运动者"
        start_text = f"从 {int(start_year)} 年开始" if start_year else "从已导入记录开始"
        distance_text = ""
        if total_distance_km is not None:
            distance_text = f"，累计 {float(total_distance_km):.1f} 公里".replace(".0 公里", " 公里")
        city_text = f"，覆盖 {city_count} 个城市" if city_count > 0 else ""
        summary_text = f"你已经{start_text}沉淀运动记录，累计完成 {activity_count} 次活动{distance_text}{city_text}。"
        tags = [primary_sport_label if primary_sport != "unknown" else "运动记录"]
        tags.append(f"{activity_count} 次活动")
        if race_count:
            tags.append(f"{race_count} 场赛事")
        if pb_count:
            tags.append(f"{pb_count} 项 PB")
        if city_count:
            tags.append(f"{city_count} 城足迹")
        if achievement_count:
            tags.append(f"{achievement_count} 项成就")
        who_answer = f"你是一名{title}，当前主运动识别为{primary_sport_label}。"
        journey_answer = f"{start_text}，你已累计完成 {activity_count} 次活动{distance_text}{city_text}。"
        experience_parts = []
        if race_count:
            experience_parts.append(f"{race_count} 场赛事")
        if pb_count:
            experience_parts.append(f"{pb_count} 项 PB")
        if achievement_count:
            experience_parts.append(f"{achievement_count} 项成就")
        experience_answer = "、".join(experience_parts) + "已沉淀为代表经历。" if experience_parts else "赛事、PB 与荣誉会在解析后沉淀为代表经历。"

    return {
        "primary_sport": primary_sport,
        "primary_sport_label": primary_sport_label,
        "career_years": career_years,
        "career_stage": stage,
        "identity_title": title,
        "identity_summary": summary_text,
        "identity_tags": tags[:6],
        "question_answers": {
            "who": who_answer,
            "journey": journey_answer,
            "experience": experience_answer,
        },
    }


def _sanitize_snapshot_pb(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(record.get("id") or ""),
        "activity_id": str(record.get("activity_id") or ""),
        "sport": str(record.get("sport") or ""),
        "pb_type": str(record.get("pb_type") or ""),
        "value": record.get("value"),
        "value_unit": str(record.get("value_unit") or ""),
        "event_date": str(record.get("event_date") or ""),
    }


def _sanitize_snapshot_achievement(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id") or ""),
        "activity_id": str(item.get("activity_id") or ""),
        "achievement_type": str(item.get("achievement_type") or ""),
        "title": str(item.get("title") or ""),
        "event_date": str(item.get("event_date") or ""),
        "score": _safe_int(item.get("score"), default=0),
    }


def _sanitize_snapshot_timeline_node(node: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(node.get("id") or ""),
        "activity_id": str(node.get("activity_id") or ""),
        "type": str(node.get("type") or ""),
        "title": str(node.get("title") or ""),
        "date": str(node.get("date") or ""),
    }


def _sanitize_snapshot_memory(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id") or ""),
        "activity_id": str(item.get("activity_id") or ""),
        "race_id": str(item.get("race_id") or ""),
        "type": str(item.get("type") or ""),
        "title": str(item.get("title") or ""),
        "story": str(item.get("story") or ""),
        "date": str(item.get("date") or ""),
        "has_media": bool(item.get("has_media")),
    }


def _flatten_timeline_digest(timeline: dict[str, Any], limit: int = 12) -> list[dict[str, Any]]:
    digest: list[dict[str, Any]] = []
    for year in timeline.get("years") or []:
        for month in year.get("months") or []:
            for node in month.get("nodes") or []:
                digest.append(_sanitize_snapshot_timeline_node(node))
                if len(digest) >= limit:
                    return digest
    return digest


def _snapshot_has_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).strip().lower() in CAREER_SNAPSHOT_FORBIDDEN_KEYS or _snapshot_has_forbidden_key(child):
                return True
    elif isinstance(value, list):
        return any(_snapshot_has_forbidden_key(child) for child in value)
    return False


def _sanitize_saved_career_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    raw_summary = snapshot.get("summary") if isinstance(snapshot.get("summary"), dict) else {}
    raw_primary_sport = snapshot.get("primary_sport") if isinstance(snapshot.get("primary_sport"), dict) else {}
    raw_status = snapshot.get("status") if isinstance(snapshot.get("status"), dict) else {}
    pb_summary = [
        _sanitize_snapshot_pb(item)
        for item in (snapshot.get("pb_summary") or [])
        if isinstance(item, dict)
    ][:6]
    major_achievements = [
        _sanitize_snapshot_achievement(item)
        for item in (snapshot.get("major_achievements") or [])
        if isinstance(item, dict)
    ][:8]
    timeline_digest = [
        _sanitize_snapshot_timeline_node(item)
        for item in (snapshot.get("timeline_digest") or [])
        if isinstance(item, dict)
    ][:12]
    representative_memories = [
        _sanitize_snapshot_memory(item)
        for item in (snapshot.get("representative_memories") or [])
        if isinstance(item, dict)
    ][:6]
    return {
        "snapshot_version": str(snapshot.get("snapshot_version") or "acs.v1"),
        "generated_at": str(snapshot.get("generated_at") or ""),
        "summary": {
            "career_start_year": raw_summary.get("career_start_year"),
            "activity_count": int(raw_summary.get("activity_count") or 0),
            "race_count": int(raw_summary.get("race_count") or 0),
            "pb_count": int(raw_summary.get("pb_count") or 0),
            "achievement_count": int(raw_summary.get("achievement_count") or 0),
            "memory_count": int(raw_summary.get("memory_count") or 0),
            "covered_city_count": int(raw_summary.get("covered_city_count") or 0),
            "total_distance_km": raw_summary.get("total_distance_km"),
        },
        "primary_sport": {
            "sport": str(raw_primary_sport.get("sport") or ""),
            "activity_count": int(raw_primary_sport.get("activity_count") or 0),
            "confidence": str(raw_primary_sport.get("confidence") or "none"),
        },
        "pb_summary": pb_summary,
        "major_achievements": major_achievements,
        "timeline_digest": timeline_digest,
        "representative_memories": representative_memories,
        "status": {
            "schema_ready": bool(raw_status.get("schema_ready", True)),
            "data_ready": bool(raw_status.get("data_ready")),
            "message": str(raw_status.get("message") or ""),
        },
    }


def get_career_races(
    filters: dict[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Return active ACS race archive entries without exposing Activity raw facts."""
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        schema = ensure_career_schema(db)
        normalized_filters = _normalize_race_filters(filters)
        where_parts = ["status = 'active'"]
        params: list[Any] = []
        if normalized_filters["sport"] != "all":
            where_parts.append("sport = ?")
            params.append(normalized_filters["sport"])
        if normalized_filters["event_type"] != "all":
            where_parts.append("event_type = ?")
            params.append(normalized_filters["event_type"])
        if normalized_filters["source"] != "all":
            where_parts.append("source = ?")
            params.append(normalized_filters["source"])
        if normalized_filters["year"] is not None:
            where_parts.append("substr(event_date, 1, 4) = ?")
            params.append(str(normalized_filters["year"]))

        cursor = db.execute(
            f"""
            SELECT id, activity_id, name, event_type, sport, event_date,
                   location_json, performance_summary_json, confidence, source, display_metadata_json
            FROM career_race_events
            WHERE {' AND '.join(where_parts)}
            ORDER BY event_date DESC, id DESC
            """,
            tuple(params),
        )
        races = [_build_race_record(row) for row in _rows_to_dicts(cursor)]
        activity_rows_by_id: dict[str, dict[str, Any]] = {}
        activity_ids = [str(race.get("activity_id") or "").strip() for race in races if str(race.get("activity_id") or "").strip()]
        if activity_ids and _table_exists(db, "activities"):
            select_sql = ", ".join(
                _activity_select_expr(db, column_name)
                for column_name in RACE_RESOLVER_ACTIVITY_COLUMNS
            )
            placeholders = ", ".join("?" for _ in activity_ids)
            activity_cursor = db.execute(
                f"""
                SELECT {select_sql}
                FROM activities
                WHERE CAST(id AS TEXT) IN ({placeholders})
                """,
                tuple(activity_ids),
            )
            activity_rows_by_id = {
                str(row.get("id") or ""): row
                for row in _rows_to_dicts(activity_cursor)
            }
        for race in races:
            activity_row = activity_rows_by_id.get(str(race.get("activity_id") or ""))
            display_title = _race_display_title_from_activity(race, activity_row)
            if display_title:
                race["name"] = display_title
                race["race_title"] = display_title
            race["card_metrics"] = _race_card_metrics_from_activity(race, activity_row)
            race["media"] = _activity_race_hero_banner_media(
                db,
                race.get("activity_id"),
                max_bytes=CAREER_RACE_ARCHIVE_COVER_MAX_BYTES,
                preferred="thumbnail",
            )
        summary = _summarize_races(races)
        data_ready = bool(races)
        return {
            "races": races,
            "summary": summary,
            "filters": normalized_filters,
            "status": {
                "schema_ready": bool(schema.get("ok")),
                "data_ready": data_ready,
                "message": CAREER_RACES_READY_STATUS_MESSAGE if data_ready else CAREER_RACES_EMPTY_STATUS_MESSAGE,
            },
        }
    finally:
        if owns_conn:
            db.close()


def get_career_pb(
    filters: dict[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Return active ACS PB records without exposing Activity raw facts."""
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        schema = ensure_career_schema(db)
        normalized_filters = _normalize_pb_filters(filters)
        where_parts = ["status = 'active'"]
        params: list[Any] = []
        if normalized_filters["sport"] != "all":
            where_parts.append("sport = ?")
            params.append(normalized_filters["sport"])
        if normalized_filters["pb_type"] != "all":
            where_parts.append("pb_type = ?")
            params.append(normalized_filters["pb_type"])
        if normalized_filters["source"] != "all":
            where_parts.append("source = ?")
            params.append(normalized_filters["source"])
        if normalized_filters["year"] is not None:
            where_parts.append("substr(event_date, 1, 4) = ?")
            params.append(str(normalized_filters["year"]))

        cursor = db.execute(
            f"""
            SELECT id, activity_id, sport, pb_type, value, value_unit, improvement,
                   event_date, confidence, source, display_metadata_json
            FROM career_pb_records
            WHERE {' AND '.join(where_parts)}
            ORDER BY event_date DESC, pb_type ASC, id DESC
            """,
            tuple(params),
        )
        pb_records = [_build_pb_record(row) for row in _rows_to_dicts(cursor)]
        summary = _summarize_pb_records(pb_records)
        data_ready = bool(pb_records)
        return {
            "pb_records": pb_records,
            "summary": summary,
            "filters": normalized_filters,
            "status": {
                "schema_ready": bool(schema.get("ok")),
                "data_ready": data_ready,
                "message": CAREER_PB_READY_STATUS_MESSAGE if data_ready else CAREER_PB_EMPTY_STATUS_MESSAGE,
            },
        }
    finally:
        if owns_conn:
            db.close()


def get_career_achievements(
    filters: dict[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Return active ACS achievement entries without exposing Activity raw facts."""
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        schema = ensure_career_schema(db)
        normalized_filters = _normalize_achievement_filters(filters)
        where_parts = ["status = 'active'"]
        params: list[Any] = []
        if normalized_filters["achievement_type"] != "all":
            where_parts.append("achievement_type = ?")
            params.append(normalized_filters["achievement_type"])
        if normalized_filters["source"] != "all":
            where_parts.append("source = ?")
            params.append(normalized_filters["source"])
        if normalized_filters["year"] is not None:
            where_parts.append("substr(event_date, 1, 4) = ?")
            params.append(str(normalized_filters["year"]))
        if normalized_filters["min_score"] is not None:
            where_parts.append("score >= ?")
            params.append(int(normalized_filters["min_score"]))

        cursor = db.execute(
            f"""
            SELECT id, activity_id, achievement_type, title, event_date, score, icon,
                   description, confidence, source, display_metadata_json
            FROM career_achievement_events
            WHERE {' AND '.join(where_parts)}
            ORDER BY score DESC, event_date DESC, id DESC
            """,
            tuple(params),
        )
        achievements = [_build_achievement_record(row) for row in _rows_to_dicts(cursor)]
        if normalized_filters["category"] != "all":
            achievements = [
                achievement
                for achievement in achievements
                if achievement.get("category") == normalized_filters["category"]
            ]
        summary = _summarize_achievements(achievements)
        data_ready = bool(achievements)
        return {
            "achievements": achievements,
            "summary": summary,
            "filters": normalized_filters,
            "status": {
                "schema_ready": bool(schema.get("ok")),
                "data_ready": data_ready,
                "message": CAREER_ACHIEVEMENTS_READY_STATUS_MESSAGE if data_ready else CAREER_ACHIEVEMENTS_EMPTY_STATUS_MESSAGE,
            },
        }
    finally:
        if owns_conn:
            db.close()


def get_career_event_candidates(
    filters: dict[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Return low-confidence ACS event candidates without promoting them."""
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        schema = ensure_career_schema(db)
        normalized_filters = _normalize_candidate_filters(filters)
        where_parts = ["1=1"]
        params: list[Any] = []
        if normalized_filters["candidate_type"] != "all":
            where_parts.append("candidate_type = ?")
            params.append(normalized_filters["candidate_type"])
        if normalized_filters["status"] != "all":
            where_parts.append("status = ?")
            params.append(normalized_filters["status"])
        if normalized_filters["min_confidence"] is not None:
            where_parts.append("confidence >= ?")
            params.append(float(normalized_filters["min_confidence"]))
        cursor = db.execute(
            f"""
            SELECT id, activity_id, candidate_type, title, evidence_json,
                   confidence, status, updated_at
            FROM career_event_candidates
            WHERE {' AND '.join(where_parts)}
            ORDER BY confidence DESC, updated_at DESC, id DESC
            """,
            tuple(params),
        )
        candidates = [_build_candidate_record(row) for row in _rows_to_dicts(cursor)]
        summary = _summarize_candidates(candidates)
        data_ready = bool(candidates)
        return {
            "candidates": candidates,
            "summary": summary,
            "filters": normalized_filters,
            "status": {
                "schema_ready": bool(schema.get("ok")),
                "data_ready": data_ready,
                "message": CAREER_CANDIDATES_READY_STATUS_MESSAGE if data_ready else CAREER_CANDIDATES_EMPTY_STATUS_MESSAGE,
            },
        }
    finally:
        if owns_conn:
            db.close()


def resolve_career_event_candidate(
    payload: dict[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Confirm or dismiss a low-confidence candidate through user intent."""
    raw = payload if isinstance(payload, dict) else {}
    candidate_id = str(raw.get("id") or raw.get("candidate_id") or "").strip()
    decision = str(raw.get("decision") or raw.get("action") or "").strip().lower()
    if not candidate_id:
        raise ValueError("候选事件 id 不能为空")
    if decision not in {"confirm_race", "dismiss", "reject_race"}:
        raise ValueError("候选事件处理动作无效")

    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        schema = ensure_career_schema(db)
        row = db.execute(
            """
            SELECT id, activity_id, candidate_type, title, evidence_json, confidence, status, updated_at
            FROM career_event_candidates
            WHERE id = ?
            LIMIT 1
            """,
            (candidate_id,),
        ).fetchone()
        if row is None:
            raise ValueError("候选事件不存在")
        candidate = _build_candidate_record(dict(row) if isinstance(row, sqlite3.Row) else dict(zip(
            ["id", "activity_id", "candidate_type", "title", "evidence_json", "confidence", "status", "updated_at"],
            row,
        )))
        if candidate["status"] != "candidate":
            result = {
                "candidate": candidate,
                "decision": decision,
                "changed": False,
                "status": {
                    "schema_ready": bool(schema.get("ok")),
                    "data_ready": True,
                    "message": "候选事件已处理",
                },
            }
            if owns_conn:
                db.commit()
            return result
        if candidate["candidate_type"] != "race":
            raise ValueError("当前仅支持处理赛事候选")

        activity_id = candidate["activity_id"]
        if decision == "confirm_race":
            _set_activity_user_race_flag(db, activity_id, True)
            resolve_race_events(db)
            final_status = "resolved"
            message = "候选事件已确认为赛事"
        else:
            _set_activity_user_race_flag(db, activity_id, False)
            _close_race_artifacts(db, activity_id)
            final_status = "dismissed"
            message = "候选事件已拒绝"

        refreshed = db.execute(
            """
            SELECT id, activity_id, candidate_type, title, evidence_json, confidence, status, updated_at
            FROM career_event_candidates
            WHERE id = ?
            LIMIT 1
            """,
            (candidate_id,),
        ).fetchone()
        updated_candidate = _build_candidate_record(dict(refreshed) if isinstance(refreshed, sqlite3.Row) else dict(zip(
            ["id", "activity_id", "candidate_type", "title", "evidence_json", "confidence", "status", "updated_at"],
            refreshed,
        ))) if refreshed is not None else {**candidate, "status": final_status, "status_label": _candidate_status_label(final_status)}

        if owns_conn:
            db.commit()
        return {
            "candidate": updated_candidate,
            "decision": decision,
            "changed": True,
            "status": {
                "schema_ready": bool(schema.get("ok")),
                "data_ready": True,
                "message": message,
            },
        }
    except Exception:
        if owns_conn:
            db.rollback()
        raise
    finally:
        if owns_conn:
            db.close()


def get_career_memory(
    filters: dict[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Return lightweight ACS memory items without exposing storage references."""
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        schema = ensure_career_schema(db)
        raw_filters = filters if isinstance(filters, dict) else {}
        memory_type = str(raw_filters.get("type") or raw_filters.get("memory_type") or "all").strip().lower() or "all"
        if memory_type not in CAREER_MEMORY_TYPES:
            memory_type = "all"
        where_parts = ["status = 'active'"]
        params: list[Any] = []
        if memory_type != "all":
            where_parts.append("memory_type = ?")
            params.append(memory_type)
        cursor = db.execute(
            f"""
            SELECT id, race_id, activity_id, memory_type, title, event_date,
                   storage_ref, story_text, metadata_json, created_at
            FROM career_memory_items
            WHERE {' AND '.join(where_parts)}
            ORDER BY COALESCE(NULLIF(event_date, ''), created_at) DESC, id DESC
            """,
            tuple(params),
        )
        items = [
            item
            for item in (_build_memory_item(row) for row in _rows_to_dicts(cursor))
            if item is not None
        ]
        summary = _summarize_memory_items(items)
        data_ready = bool(items)
        return {
            "items": items,
            "summary": summary,
            "filters": {
                "type": memory_type,
            },
            "status": {
                "schema_ready": bool(schema.get("ok")),
                "data_ready": data_ready,
                "message": CAREER_MEMORY_READY_STATUS_MESSAGE if data_ready else CAREER_MEMORY_EMPTY_STATUS_MESSAGE,
            },
        }
    finally:
        if owns_conn:
            db.close()


def save_career_memory_story(
    payload: dict[str, Any],
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Create or update a story MemoryItem bound to an Activity or Race."""
    if not isinstance(payload, dict):
        raise ValueError("记忆故事参数无效")
    activity_id = str(payload.get("activity_id") or "").strip()
    race_id = str(payload.get("race_id") or "").strip()
    title = " ".join(str(payload.get("title") or "").split())
    story = str(payload.get("story") or "").strip()
    if not activity_id and not race_id:
        raise ValueError("记忆故事必须绑定活动或赛事")
    if not title:
        raise ValueError("记忆标题不能为空")
    if not story:
        raise ValueError("记忆故事不能为空")
    if len(title) > 80:
        raise ValueError("记忆标题不能超过 80 个字符")
    if len(story) > 500:
        raise ValueError("记忆故事不能超过 500 个字符")

    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        ensure_career_schema(db)
        activity_binding = _fetch_memory_activity_binding(db, activity_id) if activity_id else None
        clean_activity_id = str((activity_binding or {}).get("id") or activity_id).strip()
        event_date = str((activity_binding or {}).get("event_date") or "").strip() or _default_memory_event_date()
        target_key = clean_activity_id or race_id
        digest = hashlib.sha1(f"{target_key}|{title}|{story}".encode("utf-8")).hexdigest()[:12]
        target_prefix = f"activity:{clean_activity_id}" if clean_activity_id else f"race:{race_id}"
        memory_id = f"memory:story:{target_prefix}:{digest}"
        metadata = {
            "source": "user",
            "binding": {
                "activity_id": clean_activity_id,
                "race_id": race_id,
            },
        }
        now = _utc_now_iso()
        db.execute(
            """
            INSERT INTO career_memory_items
                (id, race_id, activity_id, memory_type, storage_ref, story_text,
                 metadata_json, title, event_date, status, created_at, updated_at)
            VALUES
                (?, ?, ?, 'story', '', ?, ?, ?, ?, 'active', ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                race_id = excluded.race_id,
                activity_id = excluded.activity_id,
                memory_type = 'story',
                storage_ref = '',
                story_text = excluded.story_text,
                metadata_json = excluded.metadata_json,
                title = excluded.title,
                event_date = excluded.event_date,
                status = 'active',
                updated_at = excluded.updated_at
            """,
            (
                memory_id,
                race_id,
                clean_activity_id,
                story,
                _json_dumps(metadata),
                title,
                event_date,
                now,
                now,
            ),
        )
        cursor = db.execute(
            """
            SELECT id, race_id, activity_id, memory_type, title, event_date,
                   storage_ref, story_text, metadata_json, created_at
            FROM career_memory_items
            WHERE id = ?
            """,
            (memory_id,),
        )
        row = cursor.fetchone()
        names = [column[0] for column in cursor.description or []]
        if owns_conn:
            db.commit()
        built_item = _build_memory_item(dict(zip(names, row))) if row is not None else None
        return {
            "item": built_item,
            "status": {
                "schema_ready": True,
                "data_ready": bool(built_item),
                "message": "记忆故事已保存",
            },
        }
    except Exception:
        if owns_conn:
            db.rollback()
        raise
    finally:
        if owns_conn:
            db.close()


def save_career_memory_media(
    payload: dict[str, Any],
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Create or update a photo/track MemoryItem with a safe media reference."""
    if not isinstance(payload, dict):
        raise ValueError("记忆媒体参数无效")
    activity_id = str(payload.get("activity_id") or "").strip()
    race_id = str(payload.get("race_id") or "").strip()
    memory_type = str(payload.get("memory_type") or payload.get("type") or "").strip().lower()
    title = " ".join(str(payload.get("title") or "").split())
    media_ref = _normalize_memory_media_ref(payload.get("media_ref"))
    if not activity_id and not race_id:
        raise ValueError("记忆媒体必须绑定活动或赛事")
    if memory_type not in {"photo", "track"}:
        raise ValueError("记忆媒体类型仅支持 photo 或 track")
    if not title:
        raise ValueError("记忆标题不能为空")
    if len(title) > 80:
        raise ValueError("记忆标题不能超过 80 个字符")

    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        ensure_career_schema(db)
        activity_binding = _fetch_memory_activity_binding(db, activity_id) if activity_id else None
        clean_activity_id = str((activity_binding or {}).get("id") or activity_id).strip()
        event_date = str((activity_binding or {}).get("event_date") or "").strip() or _default_memory_event_date()
        target_key = clean_activity_id or race_id
        digest = hashlib.sha1(f"{target_key}|{memory_type}|{media_ref}".encode("utf-8")).hexdigest()[:12]
        target_prefix = f"activity:{clean_activity_id}" if clean_activity_id else f"race:{race_id}"
        memory_id = f"memory:{memory_type}:{target_prefix}:{digest}"
        metadata = {
            "source": "user",
            "binding": {
                "activity_id": clean_activity_id,
                "race_id": race_id,
            },
            "media_kind": memory_type,
        }
        now = _utc_now_iso()
        db.execute(
            """
            INSERT INTO career_memory_items
                (id, race_id, activity_id, memory_type, storage_ref, story_text,
                 metadata_json, title, event_date, status, created_at, updated_at)
            VALUES
                (?, ?, ?, ?, ?, '', ?, ?, ?, 'active', ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                race_id = excluded.race_id,
                activity_id = excluded.activity_id,
                memory_type = excluded.memory_type,
                storage_ref = excluded.storage_ref,
                story_text = '',
                metadata_json = excluded.metadata_json,
                title = excluded.title,
                event_date = excluded.event_date,
                status = 'active',
                updated_at = excluded.updated_at
            """,
            (
                memory_id,
                race_id,
                clean_activity_id,
                memory_type,
                media_ref,
                _json_dumps(metadata),
                title,
                event_date,
                now,
                now,
            ),
        )
        cursor = db.execute(
            """
            SELECT id, race_id, activity_id, memory_type, title, event_date,
                   storage_ref, story_text, metadata_json, created_at
            FROM career_memory_items
            WHERE id = ?
            """,
            (memory_id,),
        )
        row = cursor.fetchone()
        names = [column[0] for column in cursor.description or []]
        if owns_conn:
            db.commit()
        built_item = _build_memory_item(dict(zip(names, row))) if row is not None else None
        return {
            "item": built_item,
            "status": {
                "schema_ready": True,
                "data_ready": bool(built_item),
                "message": "记忆媒体已保存",
            },
        }
    except Exception:
        if owns_conn:
            db.rollback()
        raise
    finally:
        if owns_conn:
            db.close()


def _fetch_activity_race_photo_rows(conn: sqlite3.Connection, activity_id: str) -> list[dict[str, Any]]:
    clean_activity_id = str(activity_id or "").strip()
    if not clean_activity_id or not _table_exists(conn, "career_memory_items"):
        return []
    cursor = conn.execute(
        """
        SELECT id, race_id, activity_id, memory_type, title, event_date,
               storage_ref, story_text, metadata_json, created_at, updated_at
        FROM career_memory_items
        WHERE status = 'active'
          AND memory_type = 'photo'
          AND CAST(activity_id AS TEXT) = ?
          AND COALESCE(storage_ref, '') <> ''
        """,
        (clean_activity_id,),
    )
    rows: list[dict[str, Any]] = []
    for row in _rows_to_dicts(cursor):
        metadata = _json_loads_object(row.get("metadata_json"))
        role = str(metadata.get("role") or "").strip()
        if role in {CAREER_BANNER_MEDIA_ROLE, CAREER_RACE_GALLERY_MEDIA_ROLE}:
            rows.append(row)

    def sort_key(item: dict[str, Any]) -> tuple[int, str, str]:
        metadata = _json_loads_object(item.get("metadata_json"))
        order_raw = metadata.get("order_index")
        try:
            order_index = int(order_raw)
        except (TypeError, ValueError):
            order_index = 0 if str(metadata.get("role") or "") == CAREER_BANNER_MEDIA_ROLE else 999
        return (order_index, str(item.get("created_at") or ""), str(item.get("id") or ""))

    return sorted(rows, key=sort_key)


def _build_activity_race_photo_item(row: dict[str, Any], fallback_order: int) -> dict[str, Any]:
    metadata = _json_loads_object(row.get("metadata_json"))
    try:
        order_index = int(metadata.get("order_index"))
    except (TypeError, ValueError):
        order_index = fallback_order
    thumbnail_url = _render_activity_race_photo_image(row, preferred="thumbnail")
    preview_url = _render_activity_race_photo_image(row, preferred="preview")
    return {
        "id": str(row.get("id") or ""),
        "activity_id": str(row.get("activity_id") or ""),
        "race_id": str(row.get("race_id") or ""),
        "title": str(row.get("title") or CAREER_BANNER_PHOTO_TITLE),
        "order_index": order_index,
        "thumbnail_url": thumbnail_url,
        "preview_url": preview_url or thumbnail_url,
        "is_banner": order_index == 0 or str(metadata.get("role") or "") == CAREER_BANNER_MEDIA_ROLE,
    }


def _activity_race_photo_items(conn: sqlite3.Connection, activity_id: str) -> list[dict[str, Any]]:
    rows = _fetch_activity_race_photo_rows(conn, activity_id)
    items = [_build_activity_race_photo_item(row, index) for index, row in enumerate(rows)]
    items.sort(key=lambda item: (int(item.get("order_index") or 0), str(item.get("id") or "")))
    for index, item in enumerate(items):
        item["order_index"] = index
        item["is_banner"] = index == 0
    return items


def _activity_race_hero_banner_media(
    conn: sqlite3.Connection,
    activity_id: str,
    max_bytes: int | None = None,
    preferred: str = "preview",
) -> dict[str, Any]:
    rows = _fetch_activity_race_photo_rows(conn, activity_id)
    if not rows:
        return {"has_photo": False, "image_ref": ""}
    image_ref = _render_activity_race_photo_image(rows[0], preferred=preferred, max_bytes=max_bytes)
    return {"has_photo": bool(image_ref), "image_ref": image_ref}


def _build_activity_race_photo_response(
    conn: sqlite3.Connection,
    activity_id: str,
    race_id: str = "",
    event_date: str = "",
    can_manage: bool = True,
    message: str = "赛事照片已生成",
) -> dict[str, Any]:
    clean_activity_id = str(activity_id or "").strip()
    photos = _activity_race_photo_items(conn, clean_activity_id)
    return {
        "activity_id": clean_activity_id,
        "race_id": str(race_id or ""),
        "event_date": str(event_date or ""),
        "photos": photos,
        "summary": {
            "total": len(photos),
            "max": CAREER_ACTIVITY_RACE_PHOTO_MAX_COUNT,
            "remaining": max(CAREER_ACTIVITY_RACE_PHOTO_MAX_COUNT - len(photos), 0),
            "can_manage": bool(can_manage),
        },
        "hero_banner_media": _activity_race_hero_banner_media(conn, clean_activity_id),
        "status": {
            "schema_ready": True,
            "data_ready": bool(photos),
            "message": message or ("赛事照片已生成" if photos else "暂无赛事照片"),
        },
    }


def _update_activity_race_photo_order(
    conn: sqlite3.Connection,
    activity_id: str,
    ordered_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    rows = _fetch_activity_race_photo_rows(conn, activity_id)
    if ordered_ids is not None:
        normalized_ids = [str(item or "").strip() for item in ordered_ids if str(item or "").strip()]
        row_by_id = {str(row.get("id") or ""): row for row in rows}
        if len(normalized_ids) != len(rows) or set(normalized_ids) != set(row_by_id):
            raise ValueError("照片排序必须包含当前活动的全部照片")
        rows = [row_by_id[item_id] for item_id in normalized_ids]
    now = _utc_now_iso()
    for index, row in enumerate(rows):
        metadata = _json_loads_object(row.get("metadata_json"))
        metadata["source"] = metadata.get("source") or "user"
        metadata["role"] = CAREER_BANNER_MEDIA_ROLE if index == 0 else CAREER_RACE_GALLERY_MEDIA_ROLE
        metadata["media_kind"] = "photo"
        metadata["order_index"] = index
        binding = metadata.get("binding") if isinstance(metadata.get("binding"), dict) else {}
        binding["activity_id"] = str(activity_id or "")
        if row.get("race_id"):
            binding["race_id"] = str(row.get("race_id") or "")
        metadata["binding"] = binding
        conn.execute(
            """
            UPDATE career_memory_items
            SET metadata_json = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (_json_dumps(metadata), now, str(row.get("id") or "")),
        )
    return _activity_race_photo_items(conn, activity_id)


def get_activity_race_photos(
    activity_id: Any,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Return safe race photo gallery items for one Activity Detail context."""
    clean_activity_id = str(activity_id or "").strip()
    if not clean_activity_id:
        raise ValueError("activity_id 无效")
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        ensure_career_schema(db)
        try:
            binding = _fetch_banner_race_activity_binding(db, clean_activity_id)
            can_manage = True
            race_id = str(binding.get("race_id") or "").strip()
            event_date = str(binding.get("event_date") or "").strip()
        except ValueError:
            can_manage = False
            race_id = ""
            event_date = ""
        return _build_activity_race_photo_response(
            db,
            clean_activity_id,
            race_id=race_id,
            event_date=event_date,
            can_manage=can_manage,
        )
    finally:
        if owns_conn:
            db.close()


def _normalize_activity_race_photo_payload_items(payload: dict[str, Any]) -> list[dict[str, str]]:
    raw_items = payload.get("media_items")
    items: list[dict[str, str]] = []
    if isinstance(raw_items, list):
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            try:
                media_ref = _normalize_memory_media_ref(raw.get("media_ref"))
            except ValueError:
                continue
            item = {
                "media_ref": media_ref,
                "preview_ref": _safe_activity_race_derivative_ref(
                    raw.get("preview_ref"),
                    CAREER_ACTIVITY_RACE_PHOTO_PREVIEW_DIRNAME,
                ),
                "thumbnail_ref": _safe_activity_race_derivative_ref(
                    raw.get("thumbnail_ref"),
                    CAREER_ACTIVITY_RACE_PHOTO_THUMB_DIRNAME,
                ),
            }
            items.append(item)
    if items:
        return items

    media_refs = payload.get("media_refs")
    if isinstance(media_refs, str):
        refs = [media_refs]
    elif isinstance(media_refs, list):
        refs = [str(item or "").strip() for item in media_refs]
    else:
        refs = []
    derivative_map = payload.get("media_derivatives") if isinstance(payload.get("media_derivatives"), dict) else {}
    for ref in refs:
        if not ref:
            continue
        media_ref = _normalize_memory_media_ref(ref)
        raw_derivatives = derivative_map.get(media_ref) if isinstance(derivative_map.get(media_ref), dict) else {}
        items.append({
            "media_ref": media_ref,
            "preview_ref": _safe_activity_race_derivative_ref(
                raw_derivatives.get("preview_ref"),
                CAREER_ACTIVITY_RACE_PHOTO_PREVIEW_DIRNAME,
            ),
            "thumbnail_ref": _safe_activity_race_derivative_ref(
                raw_derivatives.get("thumbnail_ref"),
                CAREER_ACTIVITY_RACE_PHOTO_THUMB_DIRNAME,
            ),
        })
    return items


def add_activity_race_photos(
    payload: dict[str, Any],
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Save safe photo references for the current race Activity Detail context."""
    if not isinstance(payload, dict):
        raise ValueError("赛事照片参数无效")
    activity_id = str(payload.get("activity_id") or "").strip()
    title = " ".join(str(payload.get("title") or CAREER_BANNER_PHOTO_TITLE).split()) or CAREER_BANNER_PHOTO_TITLE
    media_items = _normalize_activity_race_photo_payload_items(payload)
    if not activity_id:
        raise ValueError("activity_id 无效")
    if not media_items:
        raise ValueError("请选择有效的图片文件")
    if len(title) > 80:
        raise ValueError("赛事照片标题不能超过 80 个字符")

    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        ensure_career_schema(db)
        binding = _fetch_banner_race_activity_binding(db, activity_id)
        clean_activity_id = str(binding.get("id") or activity_id).strip()
        race_id = str(binding.get("race_id") or payload.get("race_id") or "").strip()
        event_date = str(binding.get("event_date") or "").strip() or _default_memory_event_date()
        existing = _fetch_activity_race_photo_rows(db, clean_activity_id)
        remaining = CAREER_ACTIVITY_RACE_PHOTO_MAX_COUNT - len(existing)
        if remaining <= 0:
            raise ValueError("每个赛事活动最多保存 5 张照片")
        if len(media_items) > remaining:
            raise ValueError(f"本次最多还能添加 {remaining} 张照片")

        start_index = len(existing)
        now = _utc_now_iso()
        for offset, media_item in enumerate(media_items):
            media_ref = media_item["media_ref"]
            order_index = start_index + offset
            digest = hashlib.sha1(f"{clean_activity_id}|race_photo|{media_ref}".encode("utf-8")).hexdigest()[:12]
            memory_id = f"memory:photo:activity:{clean_activity_id}:race-photo:{digest}"
            derivatives = {
                key: value
                for key, value in {
                    "preview_ref": media_item.get("preview_ref", ""),
                    "thumbnail_ref": media_item.get("thumbnail_ref", ""),
                }.items()
                if value
            }
            metadata = {
                "source": "user",
                "role": CAREER_BANNER_MEDIA_ROLE if order_index == 0 else CAREER_RACE_GALLERY_MEDIA_ROLE,
                "binding": {
                    "activity_id": clean_activity_id,
                    "race_id": race_id,
                },
                "media_kind": "photo",
                "order_index": order_index,
            }
            if derivatives:
                metadata["derivatives"] = derivatives
            db.execute(
                """
                INSERT INTO career_memory_items
                    (id, race_id, activity_id, memory_type, storage_ref, story_text,
                     metadata_json, title, event_date, status, created_at, updated_at)
                VALUES
                    (?, ?, ?, 'photo', ?, '', ?, ?, ?, 'active', ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    race_id = excluded.race_id,
                    activity_id = excluded.activity_id,
                    memory_type = 'photo',
                    storage_ref = excluded.storage_ref,
                    story_text = '',
                    metadata_json = excluded.metadata_json,
                    title = excluded.title,
                    event_date = excluded.event_date,
                    status = 'active',
                    updated_at = excluded.updated_at
                """,
                (
                    memory_id,
                    race_id,
                    clean_activity_id,
                    media_ref,
                    _json_dumps(metadata),
                    title,
                    event_date,
                    now,
                    now,
                ),
            )
        _update_activity_race_photo_order(db, clean_activity_id)
        if owns_conn:
            db.commit()
        return _build_activity_race_photo_response(
            db,
            clean_activity_id,
            race_id=race_id,
            event_date=event_date,
            can_manage=True,
            message="赛事照片已保存",
        )
    except Exception:
        if owns_conn:
            db.rollback()
        raise
    finally:
        if owns_conn:
            db.close()


def reorder_activity_race_photos(
    payload: dict[str, Any],
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Persist user-defined race photo order; first photo becomes Banner."""
    if not isinstance(payload, dict):
        raise ValueError("赛事照片排序参数无效")
    activity_id = str(payload.get("activity_id") or "").strip()
    ordered_ids = payload.get("ordered_ids")
    if not activity_id:
        raise ValueError("activity_id 无效")
    if not isinstance(ordered_ids, list) or not ordered_ids:
        raise ValueError("照片排序不能为空")

    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        ensure_career_schema(db)
        binding = _fetch_banner_race_activity_binding(db, activity_id)
        clean_activity_id = str(binding.get("id") or activity_id).strip()
        _update_activity_race_photo_order(db, clean_activity_id, ordered_ids)
        if owns_conn:
            db.commit()
        return _build_activity_race_photo_response(
            db,
            clean_activity_id,
            race_id=str(binding.get("race_id") or ""),
            event_date=str(binding.get("event_date") or ""),
            can_manage=True,
            message="赛事照片顺序已更新",
        )
    except Exception:
        if owns_conn:
            db.rollback()
        raise
    finally:
        if owns_conn:
            db.close()


def deactivate_activity_race_photo(
    payload: dict[str, Any],
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Soft-delete one race photo and normalize the remaining Banner order."""
    if not isinstance(payload, dict):
        raise ValueError("赛事照片删除参数无效")
    activity_id = str(payload.get("activity_id") or "").strip()
    photo_id = str(payload.get("photo_id") or payload.get("id") or "").strip()
    if not activity_id:
        raise ValueError("activity_id 无效")
    if not photo_id:
        raise ValueError("photo_id 无效")

    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        ensure_career_schema(db)
        binding = _fetch_banner_race_activity_binding(db, activity_id)
        clean_activity_id = str(binding.get("id") or activity_id).strip()
        rows = _fetch_activity_race_photo_rows(db, clean_activity_id)
        target = next((row for row in rows if str(row.get("id") or "") == photo_id), None)
        if target is None:
            raise ValueError("照片不属于当前赛事活动或已删除")
        now = _utc_now_iso()
        db.execute(
            """
            UPDATE career_memory_items
            SET status = 'inactive',
                updated_at = ?
            WHERE id = ?
              AND CAST(activity_id AS TEXT) = ?
              AND memory_type = 'photo'
              AND status = 'active'
            """,
            (now, photo_id, clean_activity_id),
        )
        _update_activity_race_photo_order(db, clean_activity_id)
        if owns_conn:
            db.commit()
        return _build_activity_race_photo_response(
            db,
            clean_activity_id,
            race_id=str(binding.get("race_id") or ""),
            event_date=str(binding.get("event_date") or ""),
            can_manage=True,
            message="赛事照片已删除",
        )
    except Exception:
        if owns_conn:
            db.rollback()
        raise
    finally:
        if owns_conn:
            db.close()


def save_career_race_photo(
    payload: dict[str, Any],
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Bind one safe photo reference as the Overview Banner for a race activity."""
    if not isinstance(payload, dict):
        raise ValueError("赛事照片参数无效")
    activity_id = str(payload.get("activity_id") or "").strip()
    media_ref = _normalize_memory_media_ref(payload.get("media_ref"))
    title = " ".join(str(payload.get("title") or CAREER_BANNER_PHOTO_TITLE).split()) or CAREER_BANNER_PHOTO_TITLE
    if len(title) > 80:
        raise ValueError("赛事照片标题不能超过 80 个字符")

    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        ensure_career_schema(db)
        binding = _fetch_banner_race_activity_binding(db, activity_id)
        clean_activity_id = str(binding.get("id") or activity_id).strip()
        race_id = str(binding.get("race_id") or "").strip()
        event_date = str(binding.get("event_date") or "").strip() or _default_memory_event_date()
        memory_id = f"memory:photo:activity:{clean_activity_id}:overview-banner"
        metadata = {
            "source": "user",
            "role": CAREER_BANNER_MEDIA_ROLE,
            "binding": {
                "activity_id": clean_activity_id,
                "race_id": race_id,
            },
            "media_kind": "photo",
        }
        now = _utc_now_iso()
        db.execute(
            """
            INSERT INTO career_memory_items
                (id, race_id, activity_id, memory_type, storage_ref, story_text,
                 metadata_json, title, event_date, status, created_at, updated_at)
            VALUES
                (?, ?, ?, 'photo', ?, '', ?, ?, ?, 'active', ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                race_id = excluded.race_id,
                activity_id = excluded.activity_id,
                memory_type = 'photo',
                storage_ref = excluded.storage_ref,
                story_text = '',
                metadata_json = excluded.metadata_json,
                title = excluded.title,
                event_date = excluded.event_date,
                status = 'active',
                updated_at = excluded.updated_at
            """,
            (
                memory_id,
                race_id,
                clean_activity_id,
                media_ref,
                _json_dumps(metadata),
                title,
                event_date,
                now,
                now,
            ),
        )
        cursor = db.execute(
            """
            SELECT id, race_id, activity_id, memory_type, title, event_date,
                   storage_ref, story_text, metadata_json, created_at
            FROM career_memory_items
            WHERE id = ?
            """,
            (memory_id,),
        )
        row = cursor.fetchone()
        names = [column[0] for column in cursor.description or []]
        if owns_conn:
            db.commit()
        built_item = _build_memory_item(dict(zip(names, row))) if row is not None else None
        hero_banner_media = _activity_race_hero_banner_media(db, clean_activity_id)
        return {
            "item": built_item,
            "hero_banner_media": hero_banner_media,
            "status": {
                "schema_ready": True,
                "data_ready": True,
                "message": "赛事 Banner 照片已保存",
            },
        }
    except Exception:
        if owns_conn:
            db.rollback()
        raise
    finally:
        if owns_conn:
            db.close()


def update_career_memory_story(
    payload: dict[str, Any],
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Update title and story text for an active story MemoryItem."""
    if not isinstance(payload, dict):
        raise ValueError("记忆故事参数无效")
    memory_id = str(payload.get("id") or "").strip()
    title = " ".join(str(payload.get("title") or "").split())
    story = str(payload.get("story") or "").strip()
    if not memory_id:
        raise ValueError("记忆 ID 不能为空")
    if not title:
        raise ValueError("记忆标题不能为空")
    if not story:
        raise ValueError("记忆故事不能为空")
    if len(title) > 80:
        raise ValueError("记忆标题不能超过 80 个字符")
    if len(story) > 500:
        raise ValueError("记忆故事不能超过 500 个字符")

    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        ensure_career_schema(db)
        existing = _fetch_memory_row(db, memory_id)
        if existing is None:
            raise ValueError("记忆不存在")
        if str(existing.get("status") or "") != "active":
            raise ValueError("只能编辑 active 记忆")
        if str(existing.get("memory_type") or "") != "story":
            raise ValueError("只能编辑故事型记忆")
        metadata = _json_loads_object(existing.get("metadata_json"))
        metadata["updated_by"] = "user"
        metadata["story_updated_at"] = _utc_now_iso()
        db.execute(
            """
            UPDATE career_memory_items
            SET title = ?,
                story_text = ?,
                metadata_json = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (title, story, _json_dumps(metadata), _utc_now_iso(), memory_id),
        )
        updated = _fetch_memory_row(db, memory_id)
        if owns_conn:
            db.commit()
        return {
            "item": _build_memory_item(updated or {}),
            "status": {
                "schema_ready": True,
                "data_ready": updated is not None,
                "message": "记忆故事已更新",
            },
        }
    except Exception:
        if owns_conn:
            db.rollback()
        raise
    finally:
        if owns_conn:
            db.close()


def deactivate_career_memory_item(
    payload: dict[str, Any],
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Mark a MemoryItem inactive without physically deleting it."""
    if not isinstance(payload, dict):
        raise ValueError("记忆停用参数无效")
    memory_id = str(payload.get("id") or "").strip()
    if not memory_id:
        raise ValueError("记忆 ID 不能为空")

    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        ensure_career_schema(db)
        existing = _fetch_memory_row(db, memory_id)
        if existing is None:
            raise ValueError("记忆不存在")
        db.execute(
            """
            UPDATE career_memory_items
            SET status = 'inactive',
                updated_at = ?
            WHERE id = ?
            """,
            (_utc_now_iso(), memory_id),
        )
        if owns_conn:
            db.commit()
        return {
            "id": memory_id,
            "status": "inactive",
        }
    except Exception:
        if owns_conn:
            db.rollback()
        raise
    finally:
        if owns_conn:
            db.close()


def get_career_seasons(
    filters: dict[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Return annual ACS Season view models from safe Activity summaries and derived events."""
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        schema = ensure_career_schema(db)
        normalized_filters = _normalize_season_filters(filters)
        seasons = _build_career_seasons(db, normalized_filters)
        summary = _summarize_seasons(seasons)
        data_ready = bool(seasons)
        return {
            "seasons": seasons,
            "summary": summary,
            "filters": normalized_filters,
            "status": {
                "schema_ready": bool(schema.get("ok")),
                "data_ready": data_ready,
                "message": CAREER_SEASONS_READY_STATUS_MESSAGE if data_ready else CAREER_SEASONS_EMPTY_STATUS_MESSAGE,
            },
        }
    finally:
        if owns_conn:
            db.close()


def get_career_overview(conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """Return a stable ACS overview skeleton backed by safe aggregate counts."""
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        schema = ensure_career_schema(db)
        activity_summary = _activity_summary(db)
        activity_rows = _overview_activity_rows(db)
        race_count = _count_rows(db, "career_race_events", "status = 'active'")
        pb_count = _count_rows(db, "career_pb_records", "status = 'active'")
        achievement_count = _count_rows(db, "career_achievement_events", "status = 'active'")
        memory_count = _count_rows(db, "career_memory_items", "status = 'active'")
        summary = {
            "career_start_year": activity_summary["career_start_year"],
            "activity_count": activity_summary["activity_count"],
            "race_count": race_count,
            "pb_count": pb_count,
            "achievement_count": achievement_count,
            "memory_count": memory_count,
            "covered_city_count": activity_summary["covered_city_count"],
            "total_distance_km": activity_summary["total_distance_km"],
        }
        identity = _build_career_identity(db, summary)
        race_payload = get_career_races(conn=db)
        latest_race = race_payload["races"][0] if race_payload.get("races") else None
        pb_payload = get_career_pb(conn=db)
        pb_records = pb_payload.get("pb_records", [])
        achievement_payload = get_career_achievements(conn=db)
        achievements = achievement_payload.get("achievements", [])
        season_payload = get_career_seasons(conn=db)
        seasons = season_payload.get("seasons", [])
        latest_pb = _latest_pb_record(pb_records)
        hero_photo_refs = _load_hero_photo_refs(db)
        hero_banner = _build_hero_banner(activity_rows, latest_race, latest_pb, hero_photo_refs)
        hero_slides = _build_hero_banner_slides(race_payload.get("races", []), activity_rows, latest_pb)
        if hero_slides:
            hero_banner["slides"] = hero_slides
            if not hero_banner.get("media", {}).get("has_photo"):
                hero_banner["mode"] = "photo"
        return {
            "summary": summary,
            "identity": identity,
            "hero_banner": hero_banner,
            "sport_totals": _build_sport_totals(activity_rows),
            "career_stats": _build_career_stats(activity_rows, summary, race_count, pb_count, achievement_count),
            "best_pb": _best_pb_summary(pb_records),
            "representative_seasons": seasons[:3],
            "latest_race": latest_race,
            "latest_pb": latest_pb,
            "representative_pb_records": _representative_pb_records(pb_records),
            "representative_achievements": _representative_achievements(achievements),
            "status": {
                "schema_ready": bool(schema.get("ok")),
                "data_ready": any(
                    summary[key]
                    for key in ("activity_count", "race_count", "pb_count", "achievement_count", "memory_count")
                ),
                "message": CAREER_EMPTY_STATUS_MESSAGE,
            },
        }
    finally:
        if owns_conn:
            db.close()


def get_career_timeline(
    filters: dict[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Return the ACS 06B timeline view model from safe resolver-backed facts."""
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        schema = ensure_career_schema(db)
        normalized_filters = _normalize_timeline_filters(filters)
        candidates_count = _count_rows(db, "career_event_candidates", "status = 'candidate'")
        available_nodes = _build_timeline_nodes_for_type(db, normalized_filters["type"], year=None)
        available_years = _timeline_available_years(available_nodes)
        nodes = _build_timeline_nodes_for_type(db, normalized_filters["type"], year=normalized_filters["year"])
        years = _group_timeline_nodes(nodes)
        data_ready = bool(years)
        return {
            "filters": normalized_filters,
            "available_years": available_years,
            "years": years,
            "candidates_count": candidates_count,
            "status": {
                "schema_ready": bool(schema.get("ok")),
                "data_ready": data_ready,
                "message": "运动生涯时间轴已生成" if data_ready else CAREER_TIMELINE_EMPTY_STATUS_MESSAGE,
            },
        }
    finally:
        if owns_conn:
            db.close()


def build_career_snapshot(conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """Build a compact ACS snapshot for future AI use without persisting it."""
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        overview = get_career_overview(conn=db)
        pb_payload = get_career_pb(conn=db)
        achievement_payload = get_career_achievements(conn=db)
        timeline_payload = get_career_timeline({"type": "all"}, conn=db)
        memory_payload = get_career_memory(conn=db)

        summary = overview.get("summary") if isinstance(overview.get("summary"), dict) else {}
        pb_summary = [
            _sanitize_snapshot_pb(record)
            for record in (pb_payload.get("pb_records") or [])[:6]
        ]
        major_achievements = [
            _sanitize_snapshot_achievement(item)
            for item in (achievement_payload.get("achievements") or [])[:8]
        ]
        timeline_digest = _flatten_timeline_digest(timeline_payload, limit=12)
        representative_memories = [
            _sanitize_snapshot_memory(item)
            for item in (memory_payload.get("items") or [])[:6]
        ]
        data_ready = any(
            bool(value)
            for value in (
                summary.get("activity_count"),
                summary.get("race_count"),
                summary.get("pb_count"),
                summary.get("achievement_count"),
                summary.get("memory_count"),
                pb_summary,
                major_achievements,
                timeline_digest,
                representative_memories,
            )
        )
        return {
            "snapshot_version": "acs.v1",
            "generated_at": _utc_now_iso(),
            "summary": {
                "career_start_year": summary.get("career_start_year"),
                "activity_count": int(summary.get("activity_count") or 0),
                "race_count": int(summary.get("race_count") or 0),
                "pb_count": int(summary.get("pb_count") or 0),
                "achievement_count": int(summary.get("achievement_count") or 0),
                "memory_count": int(summary.get("memory_count") or 0),
                "covered_city_count": int(summary.get("covered_city_count") or 0),
                "total_distance_km": summary.get("total_distance_km"),
            },
            "primary_sport": _build_primary_sport_summary(db),
            "pb_summary": pb_summary,
            "major_achievements": major_achievements,
            "timeline_digest": timeline_digest,
            "representative_memories": representative_memories,
            "status": {
                "schema_ready": bool(
                    (overview.get("status") or {}).get("schema_ready")
                    and (pb_payload.get("status") or {}).get("schema_ready")
                    and (achievement_payload.get("status") or {}).get("schema_ready")
                    and (timeline_payload.get("status") or {}).get("schema_ready")
                    and (memory_payload.get("status") or {}).get("schema_ready")
                ),
                "data_ready": data_ready,
                "message": "Career Snapshot 已生成" if data_ready else "Career Snapshot 暂无可用生涯数据",
            },
        }
    finally:
        if owns_conn:
            db.close()


def save_career_snapshot(conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """Persist the latest white-listed Career Snapshot for later read-only access."""
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        ensure_career_schema(db)
        snapshot = build_career_snapshot(conn=db)
        if _snapshot_has_forbidden_key(snapshot):
            raise ValueError("Career Snapshot 包含禁止字段")
        generated_at = str(snapshot.get("generated_at") or _utc_now_iso())
        source_version = str(snapshot.get("snapshot_version") or "acs.v1")
        now = _utc_now_iso()
        db.execute(
            """
            INSERT INTO career_snapshots
                (id, snapshot_type, generated_at, content_json, source_version, created_at)
            VALUES
                ('career_snapshot:latest', 'career', ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                snapshot_type = excluded.snapshot_type,
                generated_at = excluded.generated_at,
                content_json = excluded.content_json,
                source_version = excluded.source_version,
                created_at = excluded.created_at
            """,
            (generated_at, _json_dumps(snapshot), source_version, now),
        )
        if owns_conn:
            db.commit()
        return {
            "snapshot": snapshot,
            "saved": True,
            "saved_at": now,
            "source_version": source_version,
            "status": {
                "schema_ready": True,
                "data_ready": True,
                "message": "Career Snapshot 已保存",
            },
        }
    except Exception:
        if owns_conn:
            db.rollback()
        raise
    finally:
        if owns_conn:
            db.close()


def get_latest_career_snapshot(conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """Return the latest persisted Career Snapshot without generating a new one."""
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        ensure_career_schema(db)
        cursor = db.execute(
            """
            SELECT generated_at, content_json, source_version, created_at
            FROM career_snapshots
            WHERE id = 'career_snapshot:latest'
              AND snapshot_type = 'career'
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        if row is None:
            return {
                "snapshot": None,
                "status": {
                    "schema_ready": True,
                    "data_ready": False,
                    "message": "暂无 Career Snapshot",
                },
            }
        parsed = _json_loads_object(row[1])
        snapshot = _sanitize_saved_career_snapshot(parsed)
        return {
            "snapshot": snapshot,
            "saved_at": str(row[3] or row[0] or ""),
            "source_version": str(row[2] or snapshot.get("snapshot_version") or "acs.v1"),
            "status": {
                "schema_ready": True,
                "data_ready": True,
                "message": "Career Snapshot 已保存",
            },
        }
    finally:
        if owns_conn:
            db.close()


def _career_insight_highlights(summary: dict[str, Any]) -> list[str]:
    highlights: list[str] = []
    activity_count = int(summary.get("activity_count") or 0)
    race_count = int(summary.get("race_count") or 0)
    pb_count = int(summary.get("pb_count") or 0)
    achievement_count = int(summary.get("achievement_count") or 0)
    memory_count = int(summary.get("memory_count") or 0)
    covered_city_count = int(summary.get("covered_city_count") or 0)
    total_distance_km = summary.get("total_distance_km")
    if activity_count:
        highlights.append(f"累计活动 {activity_count} 次")
    if race_count:
        highlights.append(f"已记录赛事 {race_count} 场")
    if pb_count:
        highlights.append(f"已沉淀 PB {pb_count} 项")
    if achievement_count:
        highlights.append(f"已获得成就 {achievement_count} 项")
    if memory_count:
        highlights.append(f"已沉淀记忆 {memory_count} 条")
    if covered_city_count:
        highlights.append(f"已覆盖城市 {covered_city_count} 个")
    if total_distance_km is not None:
        highlights.append(f"累计距离 {total_distance_km} km")
    return highlights[:6]


def _build_fallback_career_insight(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    clean_snapshot = snapshot if isinstance(snapshot, dict) else {}
    summary = clean_snapshot.get("summary") if isinstance(clean_snapshot.get("summary"), dict) else {}
    has_data = bool((clean_snapshot.get("status") or {}).get("data_ready"))
    highlights = _career_insight_highlights(summary)
    if not highlights:
        highlights = ["暂无足够的运动生涯数据用于生成长期洞察"]
    return {
        "mode": "fallback",
        "title": "运动生涯洞察准备中",
        "summary": "已生成安全的运动生涯快照，AI 洞察将在后续版本开启。" if has_data else "暂无足够的运动生涯数据，后续会基于 Career Snapshot 生成长期总结。",
        "highlights": highlights,
        "next_steps": [
            "继续完善赛事、PB、成就与记忆数据",
            "后续版本将基于 Career Snapshot 生成长期总结",
        ],
        "disclaimer": "当前为本地降级洞察，不调用 AI。",
    }


def generate_career_insight(
    payload: dict[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Return a stable fallback Career Insight based only on Career Snapshot."""
    raw_payload = payload if isinstance(payload, dict) else {}
    allowed_keys = {"refresh_snapshot"}
    unknown_keys = set(raw_payload) - allowed_keys
    if unknown_keys:
        raise ValueError("Career Insight 参数仅支持 refresh_snapshot")
    refresh_snapshot = bool(raw_payload.get("refresh_snapshot"))

    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        ensure_career_schema(db)
        snapshot_source = "saved"
        if refresh_snapshot:
            saved_payload = save_career_snapshot(conn=db)
            snapshot = saved_payload.get("snapshot")
            snapshot_source = "refreshed"
        else:
            latest_payload = get_latest_career_snapshot(conn=db)
            snapshot = latest_payload.get("snapshot")
            if not snapshot:
                saved_payload = save_career_snapshot(conn=db)
                snapshot = saved_payload.get("snapshot")
                snapshot_source = "generated"
        clean_snapshot = snapshot if isinstance(snapshot, dict) else {}
        snapshot_status = clean_snapshot.get("status") if isinstance(clean_snapshot.get("status"), dict) else {}
        data_ready = bool(snapshot_status.get("data_ready"))
        insight = _build_fallback_career_insight(clean_snapshot)
        return {
            "insight": insight,
            "snapshot_status": {
                "available": bool(clean_snapshot),
                "source": snapshot_source,
                "snapshot_version": str(clean_snapshot.get("snapshot_version") or ""),
            },
            "status": {
                "schema_ready": bool(snapshot_status.get("schema_ready", True)),
                "data_ready": data_ready,
                "message": "Career Insight 降级结果已生成" if data_ready else "Career Insight 暂无足够生涯数据",
            },
        }
    finally:
        if owns_conn:
            db.close()
