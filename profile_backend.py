"""
个人运动画像后端：SQLite 存储 + HRR 心率区间 + 有氧解耦 + MCP 联调同步。
"""

from __future__ import annotations

import json
import logging
import math
import os
import random
import re
import requests
import shutil
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import llm_backend
import garmin_sync
import coros_sync
from utils.geocoding import reverse_geocode
import sys
if getattr(sys, "frozen", False):
    _BASE = Path.home() / ".fitvault"
else:
    _BASE = Path.home() / ".fitvault"

DB_PATH = _BASE / "user_profile.db"
TRACKS_DIR = _BASE / "workspace" / "tracks"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)


def _fitvault_log_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if sys.platform.startswith("win") and local_app_data:
        return Path(local_app_data).expanduser() / "FitVault" / "logs"
    return Path.home() / ".fitvault" / "logs"


def _fitvault_log_path(filename: str) -> Path:
    return _fitvault_log_dir() / filename


def _safe_file_logger(name: str, filename: str) -> logging.Logger:
    log = logging.getLogger(name)
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    log.propagate = False
    try:
        log_path = _fitvault_log_path(filename)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_path, encoding="utf-8")
    except Exception:
        log.addHandler(logging.NullHandler())
        return log
    fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    log.addHandler(fh)
    return log


def _duplicate_check_logger() -> logging.Logger:
    return _safe_file_logger("duplicate_check", "duplicate_check.log")

SQLITE_POOL_SIZE = 6
SQLITE_POOL_ACQUIRE_TIMEOUT_SEC = 10.0
SQLITE_BUSY_TIMEOUT_MS = 15000
SQLITE_CONNECT_TIMEOUT_SEC = SQLITE_BUSY_TIMEOUT_MS / 1000.0
SQLITE_LOCK_RETRY_ATTEMPTS = 6
SQLITE_LOCK_RETRY_BASE_DELAY_SEC = 0.25
PROFILE_SYNC_RETRY_COOLDOWN_SEC = 30 * 60
REGION_CACHE_PRECISION = 2
REGION_ENRICH_LIMIT = 20
REGION_ENRICH_MAX_REQUESTS = 50
REGION_ENRICH_RETRY_COOLDOWN_MINUTES = 30
GEOCODE_REQUEST_INTERVAL_MIN_SEC = 1.1
GEOCODE_REQUEST_INTERVAL_MAX_SEC = 1.6
REGION_PROVIDER_COOLDOWN_MINUTES = 24 * 60
GEOCODE_REQUEST_TIMEOUT_SEC = 8
GEOCODE_LANG = "zh-CN"
GEOCODE_USER_AGENT = "FitVault/1.0"
GPX_FALLBACK_GAIN_THRESHOLD_M = 0.1
_REGION_CACHE_LOCK = threading.Lock()
_REGION_CACHE: dict[tuple[float, float], str] = {}
_REGION_ENRICH_LOCK = threading.Lock()
REGION_ENRICH_PROVIDER_COOLDOWN_UNTIL: datetime | None = None

_DB_CONN_SEMAPHORE = threading.BoundedSemaphore(SQLITE_POOL_SIZE)
_PROFILE_SYNC_LOCK = threading.Lock()

PROFILE_CANONICAL_FIELDS: tuple[str, ...] = (
    "name", "gender", "age", "weight", "resting_hr", "max_hr",
    "recent_resting_hr", "resting_hr_7d_avg",
    "hrv_baseline", "recent_hrv", "hrv_7d_avg",
    "vo2max", "avg_bedtime", "avg_sleep_hours", "bmi",
    "body_fat_pct", "body_water_pct", "bone_mass", "muscle_mass",
    "longest_hike_km", "height_cm", "pb_5km", "pb_10km",
    "pb_half_marathon", "pb_full_marathon", "lactate_threshold_hr",
    "ftp", "ftp_watts", "lactate_threshold_pace", "pb_1km",
    "longest_run_km", "longest_ride_time", "cycling_40km_time",
    "cycling_80km_time", "longest_cycle_km", "longest_swim_distance_m",
    "swimming_100m_pb", "total_run_km", "total_hike_km",
    "total_cycle_km", "total_swim_km",
)

PROFILE_ANALYSIS_REQUIRED_FIELDS: tuple[str, ...] = (
    "resting_hr", "max_hr", "weight", "vo2max", "lactate_threshold_hr",
)
PROFILE_ANALYSIS_OPTIONAL_FIELDS: tuple[str, ...] = (
    "hrv_baseline", "recent_hrv", "hrv_7d_avg",
    "recent_resting_hr", "resting_hr_7d_avg",
    "avg_sleep_hours", "avg_bedtime", "body_fat_pct",
    "body_water_pct", "bone_mass", "muscle_mass", "ftp", "ftp_watts",
)
PROFILE_DISPLAY_ONLY_FIELDS: tuple[str, ...] = (
    "bmi", "pb_1km", "pb_5km", "pb_10km", "pb_half_marathon",
    "pb_full_marathon", "longest_hike_km", "total_hike_km",
    "longest_run_km", "total_run_km", "longest_ride_time",
    "cycling_40km_time", "cycling_80km_time", "longest_cycle_km",
    "total_cycle_km", "longest_swim_distance_m", "total_swim_km",
    "swimming_100m_pb",
)

PROFILE_FIELD_LABELS: dict[str, str] = {
    "name": "姓名", "gender": "性别", "age": "年龄", "height_cm": "身高",
    "weight": "体重", "resting_hr": "静息心率", "max_hr": "最大心率",
    "hrv_baseline": "HRV 基准", "vo2max": "最大摄氧量",
    "avg_bedtime": "平均入睡时间", "avg_sleep_hours": "平均睡眠",
    "bmi": "BMI", "body_fat_pct": "体脂率", "body_water_pct": "体水分",
    "bone_mass": "骨量", "muscle_mass": "肌肉量",
    "lactate_threshold_hr": "乳酸阈值心率",
    "lactate_threshold_pace": "乳酸阈值配速",
    "ftp": "FTP", "ftp_watts": "FTP",
    "pb_1km": "1km PB", "pb_5km": "5km PB", "pb_10km": "10km PB",
    "pb_half_marathon": "半马 PB", "pb_full_marathon": "全马 PB",
    "longest_hike_km": "最长徒步", "total_hike_km": "徒步累计",
    "longest_run_km": "最长跑步", "total_run_km": "跑步累计",
    "longest_ride_time": "最长骑行时长", "cycling_40km_time": "40km 骑行",
    "cycling_80km_time": "80km 骑行", "longest_cycle_km": "最长骑行",
    "total_cycle_km": "骑行累计", "longest_swim_distance_m": "最长游泳",
    "total_swim_km": "游泳累计", "swimming_100m_pb": "100m 游泳",
}

ACTIVITY_LIST_INDEX_SQL: tuple[tuple[str, str], ...] = (
    (
        "idx_activities_list_sort_expr",
        """
        CREATE INDEX IF NOT EXISTS idx_activities_list_sort_expr
        ON activities(
            COALESCE(source_type, 'fit_sdk'),
            COALESCE(is_mock, 0),
            deleted_at,
            COALESCE(start_time, updated_at) DESC,
            id DESC
        )
        """,
    ),
    (
        "idx_activities_list_type",
        """
        CREATE INDEX IF NOT EXISTS idx_activities_list_type
        ON activities(
            COALESCE(source_type, 'fit_sdk'),
            COALESCE(is_mock, 0),
            deleted_at,
            sport_type,
            sub_sport_type
        )
        """,
    ),
    (
        "idx_activities_location_display",
        """
        CREATE INDEX IF NOT EXISTS idx_activities_location_display
        ON activities(
            COALESCE(source_type, 'fit_sdk'),
            COALESCE(is_mock, 0),
            deleted_at,
            region_display,
            region,
            region_city
        )
        """,
    ),
    (
        "idx_activities_file_path",
        "CREATE INDEX IF NOT EXISTS idx_activities_file_path ON activities(file_path)",
    ),
    (
        "idx_activities_dedupe_lookup",
        """
        CREATE INDEX IF NOT EXISTS idx_activities_dedupe_lookup
        ON activities(
            deleted_at,
            start_time_utc,
            start_time,
            sport_type,
            sub_sport_type,
            dist_km,
            duration_sec
        )
        """,
    ),
)


def _ensure_activity_list_indexes(conn: sqlite3.Connection) -> None:
    for _name, sql in ACTIVITY_LIST_INDEX_SQL:
        conn.execute(sql)


def _dedupe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        num = float(value)
        if not math.isfinite(num):
            return None
        return num
    except (TypeError, ValueError):
        return None


def _dedupe_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _activity_list_semantic_identity(row: dict[str, Any]) -> str:
    """Return a stable UI-list identity for the same imported activity.

    The database may contain duplicate rows from earlier imports.  We only use
    the semantic key when start time, distance, and duration are present enough
    to be meaningful; otherwise we fall back to file identity.
    """
    start_time = str(row.get("start_time_utc") or row.get("start_time") or "").strip()
    dist_km = _dedupe_float(
        row.get("dist_km")
        if row.get("dist_km") is not None
        else row.get("distance_km_clean")
    )
    duration_sec = _dedupe_int(
        row.get("duration_sec")
        if row.get("duration_sec") is not None
        else row.get("duration")
    )
    has_track = bool(row.get("has_track"))
    if start_time and dist_km is not None and dist_km > 0 and duration_sec and duration_sec > 0:
        if not has_track:
            filename = str(row.get("filename") or row.get("file_name") or "").strip()
            if filename:
                return f"file:{filename}"
            file_path = str(row.get("file_path") or "").strip()
            if file_path:
                return f"file:{os.path.basename(file_path)}"
        sport_type = str(row.get("sub_sport_type") or row.get("sport_type") or "unknown").strip() or "unknown"
        return f"semantic:{sport_type}:{start_time}:{round(dist_km, 3):.3f}:{duration_sec}"

    filename = str(row.get("filename") or row.get("file_name") or "").strip()
    if filename:
        return f"file:{filename}"
    file_path = str(row.get("file_path") or "").strip()
    if file_path:
        return f"file:{os.path.basename(file_path)}"
    return f"id:{row.get('id')}"


def _dedupe_activity_list_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        identity = _activity_list_semantic_identity(row)
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(row)
    return deduped


def _canonical_dedupe_sport(data: dict[str, Any]) -> str:
    sub_sport = str(data.get("sub_sport_type") or "").strip()
    if sub_sport and sub_sport.lower() != "unknown":
        return sub_sport
    sport = str(data.get("sport_type") or "").strip()
    return sport or "unknown"


def build_activity_dedupe_key(data: dict[str, Any]) -> str:
    """Build a strict duplicate key for identical FIT activities.

    Empty means required fields are missing and the caller must not use strict
    key dedupe for this row.
    """
    start_time = str(data.get("start_time_utc") or data.get("start_time") or "").strip()
    dist_km = _dedupe_float(
        data.get("dist_km")
        if data.get("dist_km") is not None
        else data.get("distance_km_clean")
    )
    duration_sec = _dedupe_int(
        data.get("duration_sec")
        if data.get("duration_sec") is not None
        else data.get("duration")
    )
    if not start_time or dist_km is None or dist_km <= 0 or not duration_sec or duration_sec <= 0:
        return ""
    key = f"{_canonical_dedupe_sport(data)}|{start_time}|{round(dist_km, 3):.3f}|{duration_sec}"
    file_identity = str(data.get("file_name") or data.get("filename") or data.get("file_path") or "").strip()
    if file_identity:
        key = f"{key}|{file_identity}"
    return key


def find_activity_by_dedupe_key(conn: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any] | None:
    key = build_activity_dedupe_key(data)
    if not key:
        return None
    start_time = str(data.get("start_time_utc") or data.get("start_time") or "").strip()
    rows = conn.execute(
        """
        SELECT id, file_name, filename, file_path, start_time, start_time_utc,
               sport_type, sub_sport_type, dist_km, duration_sec, updated_at, deleted_at
        FROM activities
        WHERE deleted_at IS NULL
          AND (start_time_utc = ? OR start_time = ?)
        ORDER BY id ASC
        """,
        (start_time, start_time),
    ).fetchall()
    for row in rows:
        row_dict = dict(row)
        if build_activity_dedupe_key(row_dict) == key:
            return row_dict
    return None


def load_activity_dedupe_index(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, file_name, filename, file_path, start_time, start_time_utc,
               sport_type, sub_sport_type, dist_km, duration_sec, updated_at, deleted_at
        FROM activities
        WHERE deleted_at IS NULL
        ORDER BY id ASC
        """
    ).fetchall()
    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        row_dict = dict(row)
        key = build_activity_dedupe_key(row_dict)
        if key and key not in index:
            index[key] = row_dict
    return index


def _activity_track_payload_size(row: dict[str, Any]) -> int:
    total = 0
    for key in ("track_json", "points_json"):
        raw = row.get(key)
        if not raw:
            continue
        try:
            obj = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            continue
        if isinstance(obj, dict):
            obj = obj.get("points") or obj.get("track_data") or []
        if isinstance(obj, list):
            total += len(obj)
    return total


def _cleanup_keep_rank(row: dict[str, Any]) -> tuple[int, int, float, int]:
    file_path = str(row.get("file_path") or "").strip()
    file_exists = 1 if file_path and Path(file_path).expanduser().exists() else 0
    track_size = _activity_track_payload_size(row)
    updated_raw = str(row.get("updated_at") or "").strip()
    try:
        updated_ts = datetime.fromisoformat(updated_raw.replace("Z", "+00:00")).timestamp() if updated_raw else 0.0
    except Exception:
        updated_ts = 0.0
    # Higher is better except id, where lower is better.
    return (file_exists, track_size, updated_ts, -int(row.get("id") or 0))


def _path_under_dir(path: Path, base_dir: Path) -> bool:
    try:
        path.relative_to(base_dir)
        return True
    except ValueError:
        return False


def cleanup_duplicate_activities(dry_run: bool = True) -> dict[str, Any]:
    """Clean strict duplicate activities.

    Default dry-run mode reports duplicate groups without mutating DB or files.
    """
    def _run() -> dict[str, Any]:
        conn = _conn()
        groups: dict[str, list[dict[str, Any]]] = {}
        try:
            _init_schema(conn)
            rows = conn.execute(
                """
                SELECT id, file_name, filename, file_path, start_time, start_time_utc,
                       sport_type, sub_sport_type, dist_km, duration_sec,
                       points_json, track_json, updated_at, deleted_at
                FROM activities
                WHERE deleted_at IS NULL
                ORDER BY id ASC
                """
            ).fetchall()
            for row in rows:
                row_dict = dict(row)
                key = build_activity_dedupe_key(row_dict)
                if not key:
                    continue
                groups.setdefault(key, []).append(row_dict)

            duplicate_groups = {key: items for key, items in groups.items() if len(items) > 1}
            kept_ids: list[int] = []
            deleted_ids: list[int] = []
            files_deleted = 0
            skipped_unsafe_paths: list[dict[str, str]] = []
            file_errors: list[dict[str, str]] = []
            report_groups: list[dict[str, Any]] = []
            controlled_dir = Path(TRACKS_DIR).expanduser().resolve()

            for key, items in duplicate_groups.items():
                ordered = sorted(items, key=_cleanup_keep_rank, reverse=True)
                keep = ordered[0]
                delete_items = ordered[1:]
                keep_id = int(keep["id"])
                group_deleted_ids = [int(item["id"]) for item in delete_items]
                kept_ids.append(keep_id)
                deleted_ids.extend(group_deleted_ids)
                report_groups.append({
                    "dedupe_key": key,
                    "kept_id": keep_id,
                    "deleted_ids": group_deleted_ids,
                })

                if dry_run:
                    continue

                for item in delete_items:
                    item_id = int(item["id"])
                    fp = str(item.get("file_path") or "").strip()
                    if not fp:
                        continue
                    try:
                        path = Path(fp).expanduser().resolve()
                        if not _path_under_dir(path, controlled_dir):
                            skipped_unsafe_paths.append({"id": str(item_id), "file_path": fp, "reason": "outside_tracks_dir"})
                            continue
                        if path.exists() and path.is_file():
                            path.unlink()
                            files_deleted += 1
                    except Exception as exc:
                        file_errors.append({"id": str(item_id), "file_path": fp, "error": str(exc)})

            rows_deleted = 0
            if not dry_run and deleted_ids:
                placeholders = ",".join("?" * len(deleted_ids))
                placemark_table = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='activity_placemarks'"
                ).fetchone()
                if placemark_table:
                    conn.execute(
                        f"DELETE FROM activity_placemarks WHERE activity_id IN ({placeholders})",
                        deleted_ids,
                    )
                cur = conn.execute(
                    f"DELETE FROM activities WHERE id IN ({placeholders})",
                    deleted_ids,
                )
                rows_deleted = int(cur.rowcount or 0)
                conn.commit()
            else:
                conn.rollback()

            return {
                "ok": True,
                "dry_run": bool(dry_run),
                "groups_found": len(duplicate_groups),
                "rows_deleted": 0 if dry_run else rows_deleted,
                "files_deleted": 0 if dry_run else files_deleted,
                "kept_ids": kept_ids,
                "deleted_ids": deleted_ids,
                "groups": report_groups,
                "skipped_unsafe_paths": skipped_unsafe_paths,
                "file_errors": file_errors,
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    return run_with_db_retry(_run)

SYNC_STATE_DIR = str(_BASE / "sync_state")
SYNC_STATE_PATH = os.path.join(SYNC_STATE_DIR, "sync_state.json")
PROFILE_CACHE_PATH = os.path.join(SYNC_STATE_DIR, "user_profile_cache.json")


def _ensure_sync_state_dir() -> None:
    os.makedirs(SYNC_STATE_DIR, exist_ok=True)


def read_sync_state() -> dict:
    _ensure_sync_state_dir()
    try:
        with open(SYNC_STATE_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def write_sync_state(state: dict) -> None:
    _ensure_sync_state_dir()
    with open(SYNC_STATE_PATH, "w") as f:
        json.dump(state, f)


def mark_sync_done() -> None:
    now = datetime.now()
    state = read_sync_state()
    state.update({
        "last_sync_date": now.strftime("%Y-%m-%d"),
        "last_sync_time": now.isoformat(),
        "last_attempt_at": now.isoformat(),
        "last_attempt_status": "success",
        "last_error": None,
        "active_job_id": None,
        "connection_status": "connected",
        "synced_today": True,
    })
    write_sync_state(state)


def is_sync_needed_today() -> bool:
    state = read_sync_state()
    today = date.today().isoformat()
    return not (state.get("synced_today") and state.get("last_sync_date") == today)


def _format_last_sync_ago(last_sync_time: str | None) -> str | None:
    if not last_sync_time:
        return None
    try:
        synced_at = datetime.fromisoformat(str(last_sync_time).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    delta_days = (date.today() - synced_at.date()).days
    time_part = synced_at.strftime("%H:%M")
    if delta_days == 0:
        return f"今天 {time_part}"
    if delta_days == 1:
        return f"昨天 {time_part}"
    if 1 < delta_days <= 3:
        return f"{delta_days} 天前 {time_part}"
    return synced_at.strftime("%Y-%m-%d %H:%M")


def _assert_gpx_not_persisted(data: dict[str, Any]) -> None:
    """GPX/KML 用后即抛契约: 写库入口拒绝 .gpx/.kml 源数据。

    §二 §八：FIT 是唯一可信数据源。filename 推断比 source_type 字段更可靠
    （source_type 在 INSERT/UPDATE 中是 SQL 字面量,容易被静默覆盖）。

    Args:
        data: 即将入库的 activity dict,需含 file_name / filename / file_path 至少一个

    Raises:
        ValueError: 当任何字段以 .gpx 或 .kml 结尾时,直接拒绝写库
    """
    for key in ("file_name", "filename", "file_path"):
        v = str(data.get(key) or "").strip().lower()
        if v.endswith((".gpx", ".kml")):
            raise ValueError(
                f"GPX/KML 是用后即抛型文件,禁止入库 ({key}={v!r})"
            )


def find_gpx_pollution() -> dict[str, Any]:
    """审计 GPX/KML 残留污染。

    Returns:
        {
            "type_a_contradiction": [list of {id, file_name, file_path, source_type}],
                # source_type='fit_sdk' 但 file 是 .gpx/.kml — 已被静默覆盖的污染
            "type_b_explicit_gpx": [list of {id, file_name, file_path, source_type}],
                # file 是 .gpx/.kml — 任何 source_type 都算污染
            "total_count": int,  # = len(type_b_explicit_gpx) 超集口径
        }
    """
    conn = _conn()
    try:
        rows = conn.execute(
            """
            SELECT id, file_name, file_path, source_type
            FROM activities
            WHERE (file_name LIKE '%.gpx' OR file_name LIKE '%.kml'
                OR file_path LIKE '%.gpx' OR file_path LIKE '%.kml')
              AND COALESCE(deleted_at, '') = ''
            ORDER BY id
            """
        ).fetchall()
    finally:
        conn.close()

    type_a = [
        {
            "id": r["id"],
            "file_name": r["file_name"],
            "file_path": r["file_path"],
            "source_type": r["source_type"],
        }
        for r in rows
        if r["source_type"] == "fit_sdk"
    ]
    type_b = [
        {
            "id": r["id"],
            "file_name": r["file_name"],
            "file_path": r["file_path"],
            "source_type": r["source_type"],
        }
        for r in rows
    ]
    return {
        "type_a_contradiction": type_a,
        "type_b_explicit_gpx": type_b,
        "total_count": len(type_b),
    }


def get_profile_sync_metadata() -> dict[str, Any]:
    state = read_sync_state()
    last_sync_time = state.get("last_sync_time")
    last_sync_date = state.get("last_sync_date")
    if not last_sync_time:
        prof = get_profile()
        if prof.last_updated:
            last_sync_time = prof.last_updated
            try:
                last_sync_date = datetime.fromisoformat(str(prof.last_updated)).date().isoformat()
            except (ValueError, TypeError):
                pass
    sync_status = state.get("last_attempt_status") or "idle"
    if state.get("active_job_id"):
        sync_status = "syncing"
    elif state.get("last_sync_date") == date.today().isoformat():
        sync_status = "success_today"
    return {
        "last_sync_time": last_sync_time,
        "last_sync_date": last_sync_date,
        "last_sync_ago": _format_last_sync_ago(last_sync_time) or "从未同步",
        "connection_status": state.get("connection_status") or "unknown",
        "sync_status": sync_status,
        "last_error": state.get("last_error"),
        "current_profile_source_platform": state.get("last_profile_source_platform"),
        "data_quality": state.get("last_profile_data_quality"),
        "missing_fields": state.get("last_profile_missing_fields") or [],
        "updated_fields": state.get("last_profile_updated_fields") or [],
        "preserved_fields": state.get("last_profile_preserved_fields") or [],
        "display_only_missing_fields": state.get("last_profile_display_only_missing_fields") or [],
        "analysis_required_fields": list(PROFILE_ANALYSIS_REQUIRED_FIELDS),
        "analysis_optional_fields": list(PROFILE_ANALYSIS_OPTIONAL_FIELDS),
    }


def check_llm_gateway_connection() -> dict[str, Any]:
    cfg = llm_backend.load_llm_config()
    url = str(cfg.get("url") or "").strip()
    model = str(cfg.get("model") or "").strip()
    if not url:
        return {"connected": False, "message": "LLM 网关未配置，请前往设置检测连接"}
    if not model:
        return {"connected": False, "message": "模型名未配置，请前往设置检测连接"}
    try:
        llm_backend.test_llm_connection(
            provider=str(cfg.get("provider") or "local_mcp"),
            url=url,
            model=model,
            api_key=str(cfg.get("api_key") or ""),
            agent_id=str(cfg.get("agent_id") or ""),
        )
    except Exception as exc:
        return {"connected": False, "message": f"LLM 网关检测失败：{exc}"}
    return {"connected": True, "message": "LLM 网关已就绪"}


def should_skip_profile_sync_for_cooldown() -> bool:
    state = read_sync_state()
    if state.get("last_attempt_status") != "failed_retryable":
        return False
    last_attempt_at = state.get("last_attempt_at")
    if not last_attempt_at:
        return False
    try:
        last_attempt = datetime.fromisoformat(str(last_attempt_at).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return False
    return datetime.now(last_attempt.tzinfo) - last_attempt < timedelta(seconds=PROFILE_SYNC_RETRY_COOLDOWN_SEC)


def mark_profile_sync_blocked(message: str) -> None:
    state = read_sync_state()
    state.update({
        "connection_status": "disconnected",
        "last_attempt_at": datetime.now().isoformat(),
        "last_attempt_status": "blocked",
        "last_error": message,
        "active_job_id": None,
    })
    write_sync_state(state)


def mark_profile_sync_auth_required(message: str) -> None:
    state = read_sync_state()
    state.update({
        "connection_status": "disconnected",
        "last_attempt_at": datetime.now().isoformat(),
        "last_attempt_status": "auth_required",
        "last_error": message,
        "active_job_id": None,
    })
    write_sync_state(state)


def mark_profile_sync_auth_available(platform: str) -> None:
    state = read_sync_state()
    status = str(state.get("last_attempt_status") or "")
    if status not in {"auth_required", "blocked"}:
        return
    state.update({
        "connection_status": "connected",
        "last_attempt_status": "idle",
        "last_error": None,
        "active_job_id": None,
        "last_profile_source_platform": str(platform or "").strip().lower() or state.get("last_profile_source_platform"),
    })
    write_sync_state(state)


def mark_profile_sync_failed(message: str) -> None:
    state = read_sync_state()
    state.update({
        "last_attempt_at": datetime.now().isoformat(),
        "last_attempt_status": "failed_retryable",
        "last_error": message,
        "active_job_id": None,
    })
    write_sync_state(state)


def _profile_sync_blocked_code(code: str) -> bool:
    return code in {
        "garmin_skill_not_found",
        "coros_skill_not_found",
        "invalid_garmin_region",
        "invalid_coros_region",
    }


# ─── 用户画像本地缓存文件（读/写/校验） ────────────────────────────────
PROFILE_CACHE_MAX_AGE_SEC = 7 * 24 * 3600  # 7 天


def write_local_profile(data: dict) -> None:
    """将用户画像数据写入本地缓存文件，含时间戳。"""
    _ensure_sync_state_dir()
    payload = {
        "cached_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "data": {k: v for k, v in data.items() if v is not None},
    }
    try:
        with open(PROFILE_CACHE_PATH, "w") as f:
            json.dump(payload, f, ensure_ascii=False, default=str)
    except Exception:
        pass


def _is_profile_data_valid(data: dict) -> bool:
    """校验用户画像数据是否具备最基本的有效字段。"""
    required_keys = {"name", "gender", "age", "weight", "resting_hr", "max_hr"}
    return any(k in data and data[k] is not None for k in required_keys)


def _is_user_profile_effective(data: dict[str, Any]) -> bool:
    keys = {
        "name", "gender", "age", "weight", "resting_hr", "hrv_baseline", "vo2max",
        "avg_sleep_hours", "bmi", "body_fat_pct", "body_water_pct", "bone_mass",
        "muscle_mass", "height_cm", "longest_hike_km", "pb_5km", "pb_10km",
        "pb_half_marathon", "pb_full_marathon", "lactate_threshold_hr", "ftp",
        "ftp_watts", "lactate_threshold_pace", "pb_1km", "longest_run_km",
        "longest_ride_time", "cycling_40km_time", "cycling_80km_time",
        "longest_cycle_km", "longest_swim_distance_m", "swimming_100m_pb",
        "total_run_km", "total_hike_km", "total_cycle_km", "total_swim_km",
    }
    return any(data.get(k) is not None for k in keys)


def read_local_profile() -> dict | None:
    """读取本地缓存文件，校验时效性和数据完整性，返回 data 字典或 None。"""
    try:
        with open(PROFILE_CACHE_PATH, "r") as f:
            payload = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return None
    cached_at = payload.get("cached_at")
    if not cached_at:
        return None
    try:
        cached_ts = datetime.fromisoformat(cached_at.replace("Z", "+00:00"))
        age_sec = (datetime.now(timezone.utc).replace(tzinfo=None) - cached_ts.replace(tzinfo=None)).total_seconds()
        if age_sec > PROFILE_CACHE_MAX_AGE_SEC:
            return None
    except (ValueError, TypeError):
        return None
    data = payload.get("data") or {}
    if not _is_profile_data_valid(data):
        return None
    return data


def read_latest_profile_snapshot() -> dict | None:
    conn = _conn()
    try:
        row = conn.execute(
            """
            SELECT normalized_json, synced_at
            FROM user_profile_snapshots
            WHERE status = 'success'
            ORDER BY synced_at DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    try:
        data = json.loads(row["normalized_json"] or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not _is_user_profile_effective(data):
        return None
    data.setdefault("last_updated", row["synced_at"])
    return data
_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY_FOR: str | None = None


class ManagedConnection(sqlite3.Connection):
    """在连接关闭时自动归还连接槽位。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._slot_released = False

    def _release_slot(self) -> None:
        if self._slot_released:
            return
        self._slot_released = True
        _DB_CONN_SEMAPHORE.release()

    def close(self) -> None:
        try:
            super().close()
        finally:
            self._release_slot()


def tracks_dir() -> Path:
    """返回本地轨迹存储目录（启动时自动创建）。"""
    TRACKS_DIR.mkdir(parents=True, exist_ok=True)
    return TRACKS_DIR


def _db_path_str() -> str:
    return str(Path(DB_PATH).expanduser().resolve())


def _acquire_connection_slot() -> None:
    acquired = _DB_CONN_SEMAPHORE.acquire(timeout=SQLITE_POOL_ACQUIRE_TIMEOUT_SEC)
    if not acquired:
        raise TimeoutError(
            f"数据库连接池繁忙，请稍后重试（>{SQLITE_POOL_ACQUIRE_TIMEOUT_SEC:.0f}s 未获取到连接）"
        )


def _configure_connection(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")


def _raw_connect() -> sqlite3.Connection:
    _acquire_connection_slot()
    try:
        conn = sqlite3.connect(
            str(DB_PATH),
            timeout=SQLITE_CONNECT_TIMEOUT_SEC,
            factory=ManagedConnection,
        )
    except Exception:
        _DB_CONN_SEMAPHORE.release()
        raise
    _configure_connection(conn)
    return conn


def _ensure_schema_initialized() -> None:
    global _SCHEMA_READY_FOR
    db_path = _db_path_str()
    if _SCHEMA_READY_FOR == db_path and Path(db_path).exists():
        return

    with _SCHEMA_LOCK:
        if _SCHEMA_READY_FOR == db_path and Path(db_path).exists():
            return

        conn = _raw_connect()
        try:
            _init_schema(conn)
        finally:
            conn.close()
        _SCHEMA_READY_FOR = db_path


def _conn() -> sqlite3.Connection:
    _ensure_schema_initialized()
    return _raw_connect()


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_profile (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT,
            gender      TEXT,
            age         INTEGER,
            weight      REAL,
            resting_hr  INTEGER,
            recent_resting_hr INTEGER,
            resting_hr_7d_avg INTEGER,
            max_hr      INTEGER,
            hrv_baseline REAL,
            recent_hrv REAL,
            hrv_7d_avg REAL,
            vo2max      REAL,
            avg_sleep_hours REAL,
            longest_hike_km REAL,
            updated_at  TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_profile_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_platform TEXT NOT NULL,
            trigger_type TEXT NOT NULL,
            status TEXT NOT NULL,
            synced_at TEXT NOT NULL,
            sync_date TEXT NOT NULL,
            raw_payload_json TEXT,
            normalized_json TEXT,
            name TEXT,
            gender TEXT,
            age INTEGER,
            weight REAL,
            resting_hr INTEGER,
            max_hr INTEGER,
            hrv_baseline REAL,
            vo2max REAL,
            avg_sleep_hours REAL,
            data_quality TEXT,
            missing_fields TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS geocode_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cache_key TEXT UNIQUE,
            lat_round REAL,
            lon_round REAL,
            city TEXT,
            country TEXT,
            display TEXT,
            provider TEXT,
            status TEXT,
            error TEXT,
            created_at TEXT,
            updated_at TEXT,
            last_used_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS activities (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            filename       TEXT,
            title          TEXT,
            title_source   TEXT,
            sport_type     TEXT,
            sub_sport_type TEXT DEFAULT 'unknown',
            dist_km        REAL,
            duration_sec   INTEGER,
            gain_m         REAL,
            max_alt_m      REAL,
            avg_hr         INTEGER,
            max_hr         INTEGER,
            avg_cadence    REAL,
            hr_decoupling  REAL,
            tss            REAL,
            points_json    TEXT,
            file_path      TEXT,
            start_time     TEXT,
            start_time_utc TEXT,
            start_lat      REAL,
            start_lon      REAL,
            region         TEXT,
            weather_json   TEXT,
            weather_status TEXT DEFAULT 'pending',
            weather_updated_at TEXT,
            weather_attempt_count INTEGER DEFAULT 0,
            weather_error  TEXT,
            file_mtime     REAL,
            file_size      INTEGER,
            deleted_at     TEXT,
            updated_at     TEXT DEFAULT (datetime('now')),
            avg_pace REAL,
            calories INTEGER,
            avg_power REAL,
            max_power REAL,
            normalized_power REAL,
            avg_stroke_distance REAL,
            swolf REAL,
            list_metric_backfill_version INTEGER DEFAULT 0,
            device_name TEXT,
            shadow_diff_json TEXT
        )
    """)

    activity_columns = (
        "filename",     "dist_km",     "duration_sec","avg_hr",
        "file_name",    "distance",    "duration",    "track_json",
        "advanced_metrics",
        "file_path",    "start_time",  "title",       "title_source",
        "start_time_utc","start_lat",  "start_lon",   "region",
        "region_city",  "region_country","region_display",
        "region_status","region_error","region_updated_at","region_attempt_count",
        "region_source","region_confidence",
        "weather_json", "weather_status", "weather_updated_at", "weather_attempt_count", "weather_error",
        "file_mtime",  "file_size",   "deleted_at",
        "avg_pace",     "calories",    "avg_power",   "max_power",
        "normalized_power","avg_stroke_distance","swolf","list_metric_backfill_version",
        "device_name",  "source_type", "is_mock",     "shadow_diff_json",
        "hr_curve",     "speed_curve",
        "gain_m",       "max_alt_m",   "max_hr",      "avg_cadence",
        "hr_decoupling","tss",         "points_json", "updated_at",
        "sport_type",   "sub_sport_type",
        "processing_status", "processing_error",
        "race_source",  "race_confirmed_at", "race_confidence", "race_override",
    )
    activity_dtypes = (
        "TEXT", "REAL", "INTEGER", "INTEGER",
        "TEXT", "REAL", "INTEGER", "TEXT",
        "TEXT",
        "TEXT", "TEXT", "TEXT", "TEXT",
        "TEXT", "REAL", "REAL", "TEXT",
        "TEXT", "TEXT", "TEXT",
        "TEXT DEFAULT 'pending'", "TEXT", "TEXT", "INTEGER DEFAULT 0",
        "TEXT", "TEXT",
        "TEXT", "TEXT DEFAULT 'pending'", "TEXT", "INTEGER DEFAULT 0", "TEXT",
        "REAL", "INTEGER", "TEXT",
        "REAL", "INTEGER", "REAL", "REAL",
        "REAL", "REAL", "REAL", "INTEGER DEFAULT 0",
        "TEXT", "TEXT", "INTEGER", "TEXT",
        "TEXT", "TEXT",
        "REAL", "REAL", "INTEGER", "REAL",
        "REAL", "REAL", "TEXT", "TEXT DEFAULT (datetime('now'))",
        "TEXT", "TEXT DEFAULT 'unknown'",
        "TEXT DEFAULT 'ready'", "TEXT",
        "TEXT", "TEXT", "TEXT", "INTEGER DEFAULT 0",
    )
    assert len(activity_columns) == len(activity_dtypes), "activity_columns/dtypes mismatch"
    for col, dtype in zip(activity_columns, activity_dtypes):
        try:
            conn.execute(f"ALTER TABLE activities ADD COLUMN {col} {dtype}")
        except Exception:
            pass

    for col, dtype in [
        ("processing_status", "TEXT DEFAULT 'ready'"),
        ("processing_error", "TEXT"),
        ("weather_status", "TEXT DEFAULT 'pending'"),
        ("weather_updated_at", "TEXT"),
        ("weather_attempt_count", "INTEGER DEFAULT 0"),
        ("weather_error", "TEXT"),
    ]:
        try:
            conn.execute(f"ALTER TABLE activities ADD COLUMN {col} {dtype}")
        except Exception:
            pass

    # CONTRACT §2.1 / §5: 报告 canonical 派生指标 — 幂等 migration
    _report_columns = [
        ("min_alt_m", "REAL"),
        ("total_descent_m", "REAL"),
        ("up_count", "INTEGER"),
        ("down_count", "INTEGER"),
        ("max_single_climb_m", "REAL"),
        ("difficulty_score", "INTEGER"),
        ("report_metrics_version", "INTEGER"),
        ("avg_grade_pct", "REAL"),
        ("max_slope_pct", "REAL"),
        ("min_slope_pct", "REAL"),
        ("uphill_pct", "REAL"),
        ("downhill_pct", "REAL"),
    ]
    for col, dtype in _report_columns:
        try:
            conn.execute(f"ALTER TABLE activities ADD COLUMN {col} {dtype}")
        except Exception:
            pass

    for col, dtype in [
        ("sub_sport_type", "TEXT"),
        ("file_path", "TEXT"),
        ("start_time", "TEXT"),
        ("title", "TEXT"),
        ("title_source", "TEXT"),
        ("start_time_utc", "TEXT"),
        ("start_lat", "REAL"),
        ("start_lon", "REAL"),
        ("region", "TEXT"),
        ("region_city", "TEXT"),
        ("region_country", "TEXT"),
        ("region_display", "TEXT"),
        ("region_status", "TEXT DEFAULT 'pending'"),
        ("region_error", "TEXT"),
        ("region_updated_at", "TEXT"),
        ("region_attempt_count", "INTEGER DEFAULT 0"),
        ("region_source", "TEXT"),
        ("region_confidence", "TEXT"),
        ("weather_json", "TEXT"),
        ("weather_status", "TEXT DEFAULT 'pending'"),
        ("weather_updated_at", "TEXT"),
        ("weather_attempt_count", "INTEGER DEFAULT 0"),
        ("weather_error", "TEXT"),
        ("file_mtime", "REAL"),
        ("file_size", "INTEGER"),
        ("deleted_at", "TEXT"),
        ("avg_pace", "REAL"),
        ("calories", "INTEGER"),
        ("avg_power", "REAL"),
        ("max_power", "REAL"),
        ("normalized_power", "REAL"),
        ("avg_stroke_distance", "REAL"),
        ("swolf", "REAL"),
        ("list_metric_backfill_version", "INTEGER DEFAULT 0"),
        ("device_name", "TEXT"),
        ("source_type", "TEXT"),
        ("is_mock", "INTEGER"),
        ("shadow_diff_json", "TEXT"),
    ]:
        try:
            conn.execute(f"ALTER TABLE activities ADD COLUMN {col} {dtype}")
        except Exception:
            pass

    for col, dtype in [
        ("hr_curve", "TEXT"),
        ("speed_curve", "TEXT"),
    ]:
        try:
            conn.execute(f"ALTER TABLE activities ADD COLUMN {col} {dtype}")
        except Exception:
            pass

    # === V8.0: V7.11-V7.13 新指标所需的 5 个数据列 ===
    # 依据 fit-arch-contrac §2.1 全链路可追溯,5 列的最终来源必须是 FIT 解析
    # (source_type=fit_sdk),不允许 frontend_fallback / mock / synthetic 标记
    # 写入入口在 V8.2/V8.3 阶段实现 (sync_local_fit_files / batch_import_tracks)
    # 列类型选择:
    #   - cadence_curve / hr_zone_distribution: TEXT (JSON 序列化的数组)
    #   - is_race / is_event / is_intermittent: INTEGER DEFAULT 0 (布尔型 SQLite 习惯)
    # 全部 nullable,不强制 NOT NULL,旧活动记录补列不会失败
    for col, dtype in [
        ("cadence_curve", "TEXT"),
        ("hr_zone_distribution", "TEXT"),
        ("is_race", "INTEGER DEFAULT 0"),
        ("race_source", "TEXT"),
        ("race_confirmed_at", "TEXT"),
        ("race_confidence", "TEXT"),
        ("race_override", "INTEGER DEFAULT 0"),
        ("is_event", "INTEGER DEFAULT 0"),
        ("is_intermittent", "INTEGER DEFAULT 0"),
        ("laps_json", "TEXT"),  # 真实圈速数据 (FIT lap_mesgs 归一化)
    ]:
        try:
            conn.execute(f"ALTER TABLE activities ADD COLUMN {col} {dtype}")
        except Exception:
            pass

    # === V9.4.0:Training Effect 数据列(FIT 219/218 直读,见 training_effect_v1_contract §6.5) ===
    # aerobic_training_effect: 有氧 TE(0.0~5.0,REAL)
    # anaerobic_training_effect: 无氧 TE(0.0~5.0,REAL)
    # 来源:FIT session message 直读;幂等 ALTER TABLE,旧记录补列后为 NULL(走 V9.2.2 占位)
    for col, dtype in [
        ("aerobic_training_effect", "REAL"),
        ("anaerobic_training_effect", "REAL"),
    ]:
        try:
            conn.execute(f"ALTER TABLE activities ADD COLUMN {col} {dtype}")
        except Exception:
            pass

    for col, dtype in [
        ("recent_resting_hr", "INTEGER"),
        ("resting_hr_7d_avg", "INTEGER"),
        ("recent_hrv", "REAL"),
        ("hrv_7d_avg", "REAL"),
        ("avg_bedtime", "TEXT"),
        ("avg_sleep_hours", "REAL"),
        ("bmi", "REAL"),
        ("body_fat_pct", "REAL"),
        ("body_water_pct", "REAL"),
        ("bone_mass", "REAL"),
        ("muscle_mass", "REAL"),
        ("longest_hike_km", "REAL"),
        ("height_cm", "REAL"),
        ("pb_5km", "TEXT"),
        ("pb_10km", "TEXT"),
        ("pb_half_marathon", "TEXT"),
        ("pb_full_marathon", "TEXT"),
        ("lactate_threshold_hr", "INTEGER"),
        ("ftp", "INTEGER"),
        ("ftp_watts", "INTEGER"),
        ("lactate_threshold_pace", "TEXT"),
        ("pb_1km", "TEXT"),
        ("longest_run_km", "REAL"),
        ("longest_ride_time", "TEXT"),
        ("cycling_40km_time", "TEXT"),
        ("cycling_80km_time", "TEXT"),
        ("longest_cycle_km", "REAL"),
        ("longest_swim_distance_m", "REAL"),
        ("swimming_100m_pb", "TEXT"),
        ("total_run_km", "REAL"),
        ("total_hike_km", "REAL"),
        ("total_cycle_km", "REAL"),
        ("total_swim_km", "REAL"),
    ]:
        try:
            conn.execute(f"ALTER TABLE user_profile ADD COLUMN {col} {dtype}")
        except Exception:
            pass
    _ensure_activity_list_indexes(conn)
    conn.commit()


def _is_locked_error(exc: Exception) -> bool:
    return isinstance(exc, sqlite3.OperationalError) and "locked" in str(exc).lower()


def run_with_db_retry(func, retries: int = SQLITE_LOCK_RETRY_ATTEMPTS):
    """对 SQLite 锁冲突做指数退避重试。"""
    last_exc = None
    for attempt in range(retries):
        try:
            return func()
        except sqlite3.OperationalError as exc:
            last_exc = exc
            if not _is_locked_error(exc) or attempt >= retries - 1:
                raise
            time.sleep(SQLITE_LOCK_RETRY_BASE_DELAY_SEC * (2**attempt))
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("数据库重试流程异常结束")


@dataclass
class UserProfile:
    name: str | None
    gender: str | None
    age: int | None
    weight: float | None
    resting_hr: int | None
    max_hr: int | None
    hrv_baseline: float | None
    vo2max: float | None
    avg_sleep_hours: float | None
    longest_hike_km: float | None
    recent_resting_hr: int | None = None
    resting_hr_7d_avg: int | None = None
    recent_hrv: float | None = None
    hrv_7d_avg: float | None = None
    avg_bedtime: str | None = None
    bmi: float | None = None
    body_fat_pct: float | None = None
    body_water_pct: float | None = None
    bone_mass: float | None = None
    muscle_mass: float | None = None
    height_cm: float | None = None
    pb_5km: str | None = None
    pb_10km: str | None = None
    pb_half_marathon: str | None = None
    pb_full_marathon: str | None = None
    lactate_threshold_hr: int | None = None
    ftp: int | None = None
    ftp_watts: int | None = None
    lactate_threshold_pace: str | None = None
    pb_1km: str | None = None
    longest_run_km: float | None = None
    longest_ride_time: str | None = None
    cycling_40km_time: str | None = None
    cycling_80km_time: str | None = None
    longest_cycle_km: float | None = None
    longest_swim_distance_m: float | None = None
    swimming_100m_pb: str | None = None
    total_run_km: float | None = None
    total_hike_km: float | None = None
    total_cycle_km: float | None = None
    total_swim_km: float | None = None
    last_updated: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "username": self.name,
            "gender": self.gender,
            "age": self.age,
            "weight": self.weight,
            "weight_kg": self.weight,
            "resting_hr": self.resting_hr,
            "resting_heart_rate": self.resting_hr,
            "recent_resting_hr": self.recent_resting_hr,
            "resting_hr_7d_avg": self.resting_hr_7d_avg,
            "max_hr": self.max_hr,
            "hrv_baseline": self.hrv_baseline,
            "hrv": self.hrv_baseline,
            "recent_hrv": self.recent_hrv,
            "hrv_7d_avg": self.hrv_7d_avg,
            "vo2max": self.vo2max,
            "vo2_max": self.vo2max,
            "avg_bedtime": self.avg_bedtime,
            "avg_sleep_hours": self.avg_sleep_hours,
            "bmi": self.bmi,
            "body_fat_pct": self.body_fat_pct,
            "body_water_pct": self.body_water_pct,
            "bone_mass": self.bone_mass,
            "muscle_mass": self.muscle_mass,
            "longest_hike_km": self.longest_hike_km,
            "height_cm": self.height_cm,
            "pb_5km": self.pb_5km,
            "pb_10km": self.pb_10km,
            "pb_half_marathon": self.pb_half_marathon,
            "pb_full_marathon": self.pb_full_marathon,
            "lactate_threshold_hr": self.lactate_threshold_hr,
            "ftp": self.ftp,
            "ftp_watts": self.ftp_watts,
            "lactate_threshold_pace": self.lactate_threshold_pace,
            "pb_1km": self.pb_1km,
            "longest_run_km": self.longest_run_km,
            "longest_ride_time": self.longest_ride_time,
            "cycling_40km_time": self.cycling_40km_time,
            "cycling_80km_time": self.cycling_80km_time,
            "longest_cycle_km": self.longest_cycle_km,
            "longest_swim_distance_m": self.longest_swim_distance_m,
            "swimming_100m_pb": self.swimming_100m_pb,
            "total_run_km": self.total_run_km,
            "total_hike_km": self.total_hike_km,
            "total_cycle_km": self.total_cycle_km,
            "total_swim_km": self.total_swim_km,
            "last_updated": self.last_updated,
        }


def get_profile() -> UserProfile:
    conn = _conn()
    row = conn.execute("SELECT * FROM user_profile ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    row_data = dict(row) if row is not None else None
    if row_data is None or not _is_user_profile_effective(row_data):
        cached = read_local_profile()
        snapshot = None if cached else read_latest_profile_snapshot()
        restored = cached or snapshot
        if restored:
            upsert_profile(restored)
            conn = _conn()
            row = conn.execute("SELECT * FROM user_profile ORDER BY id DESC LIMIT 1").fetchone()
            conn.close()
            row_data = dict(row) if row is not None else None
    if row is None:
        return UserProfile(None, None, None, None, None, None, None, None, None, None)
    if row_data is not None:
        row = row_data
    return UserProfile(
        name=row["name"],
        gender=row["gender"],
        age=row["age"],
        weight=row["weight"],
        resting_hr=row["resting_hr"],
        max_hr=row["max_hr"],
        hrv_baseline=row["hrv_baseline"],
        vo2max=row["vo2max"] if "vo2max" in row.keys() else None,
        avg_sleep_hours=row["avg_sleep_hours"] if "avg_sleep_hours" in row.keys() else None,
        longest_hike_km=row["longest_hike_km"] if "longest_hike_km" in row.keys() else None,
        recent_resting_hr=row["recent_resting_hr"] if "recent_resting_hr" in row.keys() else None,
        resting_hr_7d_avg=row["resting_hr_7d_avg"] if "resting_hr_7d_avg" in row.keys() else None,
        recent_hrv=row["recent_hrv"] if "recent_hrv" in row.keys() else None,
        hrv_7d_avg=row["hrv_7d_avg"] if "hrv_7d_avg" in row.keys() else None,
        avg_bedtime=row["avg_bedtime"] if "avg_bedtime" in row.keys() else None,
        bmi=row["bmi"] if "bmi" in row.keys() else None,
        body_fat_pct=row["body_fat_pct"] if "body_fat_pct" in row.keys() else None,
        body_water_pct=row["body_water_pct"] if "body_water_pct" in row.keys() else None,
        bone_mass=row["bone_mass"] if "bone_mass" in row.keys() else None,
        muscle_mass=row["muscle_mass"] if "muscle_mass" in row.keys() else None,
        height_cm=row["height_cm"] if "height_cm" in row.keys() else None,
        pb_5km=row["pb_5km"] if "pb_5km" in row.keys() else None,
        pb_10km=row["pb_10km"] if "pb_10km" in row.keys() else None,
        pb_half_marathon=row["pb_half_marathon"] if "pb_half_marathon" in row.keys() else None,
        pb_full_marathon=row["pb_full_marathon"] if "pb_full_marathon" in row.keys() else None,
        lactate_threshold_hr=row["lactate_threshold_hr"] if "lactate_threshold_hr" in row.keys() else None,
        ftp=row["ftp"] if "ftp" in row.keys() else None,
        ftp_watts=row["ftp_watts"] if "ftp_watts" in row.keys() else None,
        lactate_threshold_pace=row["lactate_threshold_pace"] if "lactate_threshold_pace" in row.keys() else None,
        pb_1km=row["pb_1km"] if "pb_1km" in row.keys() else None,
        longest_run_km=row["longest_run_km"] if "longest_run_km" in row.keys() else None,
        longest_ride_time=row["longest_ride_time"] if "longest_ride_time" in row.keys() else None,
        cycling_40km_time=row["cycling_40km_time"] if "cycling_40km_time" in row.keys() else None,
        cycling_80km_time=row["cycling_80km_time"] if "cycling_80km_time" in row.keys() else None,
        longest_cycle_km=row["longest_cycle_km"] if "longest_cycle_km" in row.keys() else None,
        longest_swim_distance_m=row["longest_swim_distance_m"] if "longest_swim_distance_m" in row.keys() else None,
        swimming_100m_pb=row["swimming_100m_pb"] if "swimming_100m_pb" in row.keys() else None,
        total_run_km=row["total_run_km"] if "total_run_km" in row.keys() else None,
        total_hike_km=row["total_hike_km"] if "total_hike_km" in row.keys() else None,
        total_cycle_km=row["total_cycle_km"] if "total_cycle_km" in row.keys() else None,
        total_swim_km=row["total_swim_km"] if "total_swim_km" in row.keys() else None,
        last_updated=row["updated_at"] if "updated_at" in row.keys() else None,
    )


def upsert_profile(data: dict[str, Any]) -> UserProfile:
    conn = _conn()
    conn.execute("DELETE FROM user_profile")
    fields = (
        "name", "gender", "age", "weight", "resting_hr",
        "recent_resting_hr", "resting_hr_7d_avg",
        "max_hr", "hrv_baseline", "recent_hrv", "hrv_7d_avg", "vo2max",
        "avg_bedtime", "avg_sleep_hours", "bmi", "body_fat_pct", "body_water_pct", "bone_mass",
        "muscle_mass", "longest_hike_km", "height_cm", "pb_5km", "pb_10km", "pb_half_marathon",
        "pb_full_marathon", "lactate_threshold_hr", "ftp", "ftp_watts",
        "lactate_threshold_pace", "pb_1km", "longest_run_km",
        "longest_ride_time", "cycling_40km_time", "cycling_80km_time", "longest_cycle_km",
        "longest_swim_distance_m", "swimming_100m_pb",
        "total_run_km", "total_hike_km", "total_cycle_km", "total_swim_km",
    )
    placeholders = ", ".join(["?"] * len(fields))
    conn.execute(
        f"INSERT INTO user_profile ({', '.join(fields)}) VALUES ({placeholders})",
        tuple(data.get(field) for field in fields),
    )
    conn.commit()
    last_updated = conn.execute("SELECT updated_at FROM user_profile ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    write_local_profile(data)
    return UserProfile(
        name=data.get("name"),
        gender=data.get("gender"),
        age=data.get("age"),
        weight=data.get("weight"),
        resting_hr=data.get("resting_hr"),
        max_hr=data.get("max_hr"),
        hrv_baseline=data.get("hrv_baseline"),
        vo2max=data.get("vo2max"),
        avg_bedtime=data.get("avg_bedtime"),
        avg_sleep_hours=data.get("avg_sleep_hours"),
        bmi=data.get("bmi"),
        recent_resting_hr=data.get("recent_resting_hr"),
        resting_hr_7d_avg=data.get("resting_hr_7d_avg"),
        recent_hrv=data.get("recent_hrv"),
        hrv_7d_avg=data.get("hrv_7d_avg"),
        body_fat_pct=data.get("body_fat_pct"),
        body_water_pct=data.get("body_water_pct"),
        bone_mass=data.get("bone_mass"),
        muscle_mass=data.get("muscle_mass"),
        longest_hike_km=data.get("longest_hike_km"),
        height_cm=data.get("height_cm"),
        pb_5km=data.get("pb_5km"),
        pb_10km=data.get("pb_10km"),
        pb_half_marathon=data.get("pb_half_marathon"),
        pb_full_marathon=data.get("pb_full_marathon"),
        lactate_threshold_hr=data.get("lactate_threshold_hr"),
        ftp=data.get("ftp"),
        ftp_watts=data.get("ftp_watts"),
        lactate_threshold_pace=data.get("lactate_threshold_pace"),
        pb_1km=data.get("pb_1km"),
        longest_run_km=data.get("longest_run_km"),
        longest_ride_time=data.get("longest_ride_time"),
        cycling_40km_time=data.get("cycling_40km_time"),
        cycling_80km_time=data.get("cycling_80km_time"),
        longest_cycle_km=data.get("longest_cycle_km"),
        longest_swim_distance_m=data.get("longest_swim_distance_m"),
        swimming_100m_pb=data.get("swimming_100m_pb"),
        total_run_km=data.get("total_run_km"),
        total_hike_km=data.get("total_hike_km"),
        total_cycle_km=data.get("total_cycle_km"),
        total_swim_km=data.get("total_swim_km"),
        last_updated=last_updated["updated_at"] if last_updated else None,
    )


def save_activity(data: dict[str, Any]) -> int:
    _assert_gpx_not_persisted(data)  # §二 §八: GPX/KML 用后即抛
    def _write() -> int:
        conn = _conn()
        try:
            _init_schema(conn)
            existing = find_activity_by_dedupe_key(conn, data)
            if existing:
                return int(existing["id"])
            cur = conn.execute(
                """
                INSERT INTO activities
                    (filename, title, title_source, sport_type, sub_sport_type, dist_km, duration_sec, gain_m, max_alt_m,
                     avg_hr, max_hr, avg_cadence, hr_decoupling, tss, points_json, file_path, start_time, start_time_utc,
                     start_lat, start_lon, region, region_city, region_country, region_display, region_status, region_error,
                     region_updated_at, region_attempt_count, weather_json, weather_status, weather_updated_at,
                     weather_attempt_count, weather_error, avg_pace, calories, avg_power, max_power,
                     normalized_power, avg_stroke_distance, swolf, shadow_diff_json,
                     min_alt_m, total_descent_m, up_count, down_count, max_single_climb_m, difficulty_score, report_metrics_version,
                     avg_grade_pct, max_slope_pct, min_slope_pct, uphill_pct, downhill_pct)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?)
                """,
                (
                    data.get("filename"),
                    data.get("title"),
                    data.get("title_source"),
                    data.get("sport_type"),
                    data.get("sub_sport_type", "unknown"),
                    data.get("dist_km"),
                    data.get("duration_sec"),
                    data.get("gain_m"),
                    data.get("max_alt_m"),
                    data.get("avg_hr"),
                    data.get("max_hr"),
                    data.get("avg_cadence"),
                    data.get("hr_decoupling"),
                    data.get("tss"),
                    json.dumps(data.get("points_json", [])),
                    data.get("file_path"),
                    data.get("start_time"),
                    data.get("start_time_utc"),
                    data.get("start_lat"),
                    data.get("start_lon"),
                    data.get("region"),
                    data.get("region_city"),
                    data.get("region_country"),
                    data.get("region_display"),
                    data.get("region_status"),
                    data.get("region_error"),
                    data.get("region_updated_at"),
                    data.get("region_attempt_count", 0),
                    data.get("weather_json"),
                    data.get("weather_status"),
                    data.get("weather_updated_at"),
                    data.get("weather_attempt_count", 0),
                    data.get("weather_error"),
                    data.get("avg_pace"),
                    data.get("calories"),
                    data.get("avg_power"),
                    data.get("max_power"),
                    data.get("normalized_power"),
                    data.get("avg_stroke_distance"),
                    data.get("swolf"),
                    data.get("shadow_diff_json"),
                    data.get("min_alt_m"),
                    data.get("total_descent_m"),
                    data.get("up_count"),
                    data.get("down_count"),
                    data.get("max_single_climb_m"),
                    data.get("difficulty_score"),
                    data.get("report_metrics_version"),
                    data.get("avg_grade_pct"),
                    data.get("max_slope_pct"),
                    data.get("min_slope_pct"),
                    data.get("uphill_pct"),
                    data.get("downhill_pct"),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    return run_with_db_retry(_write)


def update_activity_sport_type(activity_id: int, sport_type: str) -> None:
    def _write() -> None:
        conn = _conn()
        try:
            conn.execute(
                """
                UPDATE activities
                SET sport_type = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (sport_type, activity_id),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    run_with_db_retry(_write)


def get_activity_history(limit: int = 50) -> list[dict[str, Any]]:
    """按时间倒序返回所有历史运动记录（包含 file_path）。"""
    conn = _conn()
    rows = conn.execute(
        """
        SELECT id, filename, sport_type, sub_sport_type, dist_km, duration_sec, gain_m,
               max_alt_m, avg_hr, max_hr, file_path, start_time, updated_at
        FROM activities ORDER BY id DESC LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    rows_dicts = [dict(r) for r in rows]
    for _row in rows_dicts:
        # §契约 §二/§五: 使用解析后的显示类型翻译，sub_sport_type 可覆盖主类型
        _resolved = (str(_row.get("sub_sport_type") or "").strip() or _row.get("sport_type"))
        _row["sport_type_cn"] = translate_sport_type(_resolved)
    return rows_dicts


# §契约 §二/§五:Resolver 是唯一语义翻译层
# FIT SDK 运动类型英文常量 → 中文显示名映射 (单一可信来源)
SPORT_TYPE_CN_MAP: dict[str, str] = {
    "running": "跑步",
    "trail_running": "越野跑",
    "treadmill_running": "跑步机",
    "hiking": "徒步",
    "mountaineering": "登山",
    "walking": "步行",
    "cycling": "骑行",
    "road_cycling": "公路骑行",
    "mountain_biking": "山地骑行",
    "e_biking": "电助力骑行",
    "e_mountain_biking": "电助力山地骑行",
    "gravel_cycling": "砾石骑行",
    "track_cycling": "场地骑行",
    "hand_cycling": "手摇车",
    "swimming": "游泳",
    "lap_swimming": "泳池游泳",
    "open_water": "公开水域",
    "horseback_riding": "骑马",
    "equestrian": "骑马",
    "golf": "高尔夫",
    "tennis": "网球",
    "soccer": "足球",
    "basketball": "篮球",
    "skiing": "滑雪",
    "alpine_skiing": "高山滑雪",
    "cross_country_skiing": "越野滑雪",
    "snowboarding": "单板滑雪",
    "snowshoeing": "雪鞋行走",
    "rowing": "划船",
    "paddling": "桨板",
    "stand_up_paddleboarding": "立式桨板",
    "training": "训练",
    "sailing": "帆船",
    "surfing": "冲浪",
    "fishing": "钓鱼",
    "hunting": "狩猎",
    "inline_skating": "轮滑",
    "rock_climbing": "攀岩",
    "indoor_climbing": "室内攀爬",
    "stair_climbing": "爬楼",
    "floor_climbing": "爬楼",
    "elliptical": "椭圆机",
    "indoor_walking": "室内步行",
    "wheelchair_walk": "轮椅步行",
    "wheelchair_run": "轮椅竞速",
    "kayaking": "皮划艇",
    "rafting": "漂流",
    "diving": "潜水",
    "yoga": "瑜伽",
    "pilates": "普拉提",
    "strength_training": "力量训练",
    "hiit": "高强度间歇",
    "breath_training": "呼吸训练",
    "flexibility_training": "柔韧训练",
    "cardio": "有氧运动",
    "driving": "驾车",
    "fitness_equipment": "有氧运动",
    "indoor_cardio": "室内有氧",
    "flying": "飞行",
    "motorcycling": "摩托",
    "transition": "换项",
    "multisport": "多项",
    "other": "其他",
}


def translate_sport_type(sport_type: str | None) -> str:
    """Resolver 层:FIT SDK sport_type → 中文显示名。

    - 命中映射表 → 返回中文标签
    - 未命中 → 返回 PascalCase 化后的原值(如 ``horseback_riding`` → ``Horseback riding``)
    - 空值 → 返回 ``"综合运动"`` 兜底
    """
    if not sport_type:
        return "综合运动"
    raw = str(sport_type).strip().lower()
    if raw in SPORT_TYPE_CN_MAP:
        return SPORT_TYPE_CN_MAP[raw]
    # 兜底:PascalCase + 空格化下划线
    return raw.replace("_", " ").title() if raw else "综合运动"


_AUTO_ACTIVITY_TITLE_SOURCES = {"auto", "auto_sport", "auto_region_sport", "garmin_auto", "coros_auto", "region_auto"}
_PROTECTED_ACTIVITY_TITLE_SOURCES = {"manual", "user", "edited"}
_GENERIC_SUB_SPORT_TYPES = {"", "unknown", "generic", "other"}
_TECHNICAL_ACTIVITY_TITLE_RE = re.compile(
    r"^(?:coros[\s_-]*)?(?:activity[\s_-]*fit[\s_-]*files?|activity)(?:[\s_-]+[0-9a-f]{8,})?$",
    re.IGNORECASE,
)
_ACTIVITY_FILE_ID_SUFFIX_RE = re.compile(r"^(?P<title>.+?)[_\s]+\d{6,}(?:[-_]\d+)*$")


def clean_activity_filename_title(value: Any) -> str:
    """Remove provider activity ids and local collision suffixes from filename titles."""
    text = str(value or "").strip()
    if not text:
        return ""
    stem = Path(text).stem if text.lower().endswith(".fit") else text
    match = _ACTIVITY_FILE_ID_SUFFIX_RE.fullmatch(stem.strip())
    if match:
        cleaned = str(match.group("title") or "").strip(" _-")
        if cleaned:
            return cleaned
    return stem.strip()


def _is_technical_activity_title(title: Any) -> bool:
    text = str(title or "").strip()
    if not text:
        return True
    stem = Path(text).stem if text.lower().endswith(".fit") else text
    normalized = re.sub(r"[_\s]+", " ", stem).strip().lower()
    if "activity-fit-files" in stem.lower() or "activity fit files" in normalized:
        return True
    if _TECHNICAL_ACTIVITY_TITLE_RE.match(normalized.replace(" ", "-")):
        return True
    return bool(re.fullmatch(r"[0-9a-f]{16,}", normalized))


def _title_region_prefix(region_display: Any) -> str:
    text = str(region_display or "").strip()
    if not text or text in {"待补全", "室内运动", "未知地点", "室内运动（无GPS）"}:
        return ""
    for sep in ("/", "，", ","):
        if sep in text:
            text = text.split(sep, 1)[0].strip()
            break
    return "" if text in {"中国", "中华人民共和国"} else text


def build_activity_display_title(
    *,
    current_title: Any = "",
    title_source: Any = "",
    sport_type: Any = "",
    sub_sport_type: Any = "",
    region_display: Any = "",
) -> tuple[str, str]:
    """Build a user-facing activity title without exposing provider temp filenames."""
    source = str(title_source or "").strip()
    title = str(current_title or "").strip()
    if title and source in _PROTECTED_ACTIVITY_TITLE_SOURCES:
        return title, source
    if title and source == "filename":
        cleaned_filename_title = clean_activity_filename_title(title)
        if cleaned_filename_title != title and not _is_technical_activity_title(cleaned_filename_title):
            return cleaned_filename_title, source
        title = cleaned_filename_title
    should_replace = not title or source in _AUTO_ACTIVITY_TITLE_SOURCES or _is_technical_activity_title(title)
    if not should_replace:
        return title, source or "fit"

    sub = str(sub_sport_type or "").strip().lower()
    sport_key = sub if sub not in _GENERIC_SUB_SPORT_TYPES else str(sport_type or "").strip().lower()
    sport_cn = translate_sport_type(sport_key or "unknown")
    region_prefix = _title_region_prefix(region_display)
    if region_prefix:
        return f"{region_prefix} {sport_cn}", "auto_region_sport"
    return sport_cn, "auto_sport"


def _can_region_update_activity_title(title_source: Any, current_title: Any = "") -> bool:
    source = str(title_source or "").strip()
    if source in _PROTECTED_ACTIVITY_TITLE_SOURCES:
        return False
    if source in _AUTO_ACTIVITY_TITLE_SOURCES:
        return True
    if source == "filename" and _is_technical_activity_title(current_title):
        return True
    return False


def backfill_auto_activity_titles(conn: sqlite3.Connection | None = None, limit: int = 500) -> int:
    """Upgrade legacy technical titles to display titles; preserve real/manual titles."""
    owns_conn = conn is None
    db = conn or _conn()
    updated = 0
    try:
        rows = db.execute(
            """
            SELECT id, title, title_source, sport_type, sub_sport_type, region_display, region
            FROM activities
            WHERE COALESCE(deleted_at, '') = ''
              AND (
                COALESCE(title_source, '') IN ('auto_sport', 'auto_region_sport')
                OR TRIM(COALESCE(title, '')) = ''
                OR (
                  COALESCE(title_source, '') = 'filename'
                  AND (
                    COALESCE(title, '') GLOB '*_[0-9][0-9][0-9][0-9][0-9][0-9]*'
                    OR COALESCE(title, '') GLOB '* [0-9][0-9][0-9][0-9][0-9][0-9]*'
                  )
                )
                OR lower(COALESCE(title, '')) LIKE '%activity-fit-files%'
                OR (
                  length(TRIM(COALESCE(title, ''))) >= 16
                  AND lower(TRIM(COALESCE(title, ''))) NOT GLOB '*[^0-9a-f]*'
                )
                OR lower(COALESCE(filename, '')) LIKE 'coros___activity-fit-files%'
                OR lower(COALESCE(file_name, '')) LIKE 'coros___activity-fit-files%'
              )
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        for row in rows:
            current_title = row["title"]
            current_source = row["title_source"]
            title, title_source = build_activity_display_title(
                current_title=current_title,
                title_source=current_source,
                sport_type=row["sport_type"],
                sub_sport_type=row["sub_sport_type"],
                region_display=row["region_display"] or row["region"] or "",
            )
            if title == (current_title or "") and title_source == (current_source or ""):
                continue
            db.execute(
                """
                UPDATE activities
                SET title = ?, title_source = ?, updated_at = updated_at
                WHERE id = ?
                """,
                (title, title_source, int(row["id"])),
            )
            updated += 1
        if owns_conn:
            db.commit()
        return updated
    except sqlite3.OperationalError:
        if owns_conn:
            db.rollback()
        return 0
    finally:
        if owns_conn:
            db.close()


def get_activity_list_filtered(
    offset: int,
    limit: int,
    sport_filter: str,
    gps_only: bool = False,
    time_filter: str = "all",
    location_filter: str = "all",
    title_keyword: str = "",
) -> tuple[list[dict[str, Any]], int]:
    display_sql = (
        "CASE "
        "WHEN COALESCE(NULLIF(sub_sport_type, ''), 'unknown') IN ("
        "'lap_swimming', 'open_water', 'open_water_swimming', "
        "'trail_running', 'road_cycling', 'mountain_biking', 'treadmill_running'"
        ") THEN sub_sport_type "
        "WHEN COALESCE(NULLIF(sport_type, ''), 'unknown') IN ("
        "'lap_swimming', 'open_water', 'open_water_swimming', "
        "'trail_running', 'road_cycling', 'mountain_biking', 'treadmill_running'"
        ") THEN sport_type "
        "ELSE COALESCE(NULLIF(sport_type, ''), 'unknown') "
        "END"
    )

    where_parts = [
        "COALESCE(source_type, 'fit_sdk') = 'fit_sdk'",
        "COALESCE(is_mock, 0) = 0",
        "deleted_at IS NULL",
        "COALESCE(NULLIF(processing_status, ''), 'ready') NOT IN ('processing', 'pending')",
    ]
    params: list[Any] = []

    if sport_filter and sport_filter != "all":
        where_parts.append(f"{display_sql} = ?")
        params.append(sport_filter)

    # §任务 1:时间过滤(time_filter)——所有分支使用 ? 参数绑定,COUNT(*) 与分页共用同一套 WHERE
    if time_filter == "7d":
        where_parts.append("start_time IS NOT NULL AND start_time >= datetime('now', '-7 days')")
    elif time_filter == "30d":
        where_parts.append("start_time IS NOT NULL AND start_time >= datetime('now', '-30 days')")
    elif time_filter == "90d":
        where_parts.append("start_time IS NOT NULL AND start_time >= datetime('now', '-90 days')")
    elif time_filter == "this_year":
        where_parts.append(
            "strftime('%Y', start_time) = strftime('%Y', 'now')"
        )
    elif time_filter == "last_year":
        where_parts.append(
            "strftime('%Y', start_time) = strftime('%Y', 'now', '-1 year')"
        )
    # 'all' 或未知值 → 不加过滤

    # §任务 1:地区过滤(location_filter)——同时匹配 region_display / region / region_city,使用参数绑定防注入
    if location_filter and location_filter != "all":
        where_parts.append(
            "(COALESCE(NULLIF(region_display, ''), '') = ? "
            "OR COALESCE(NULLIF(region, ''), '') = ? "
            "OR COALESCE(NULLIF(region_city, ''), '') = ?)"
        )
        params.extend([location_filter, location_filter, location_filter])

    # title 模糊搜索——参数化绑定,转义 % _ \ 防止通配符注入
    title_keyword = str(title_keyword or "").strip()[:64]
    if title_keyword:
        where_parts.append("COALESCE(title, '') LIKE ? ESCAPE '\\'")
        params.append("%" + re.sub(r"([%_\\])", r"\\\1", title_keyword) + "%")

    if gps_only:
        where_parts.append(
            f"{display_sql} IN ("
            "'running','hiking','mountaineering','cycling','walking',"
            "'trail_running','road_cycling','mountain_biking'"
            ")"
        )
        where_parts.append("start_lat IS NOT NULL")
        where_parts.append("start_lon IS NOT NULL")

    where_sql = "WHERE " + " AND ".join(where_parts)

    select_fields = (
        "id, "
        "COALESCE(file_name, filename) AS file_name, "
        "filename, "
        "title, "
        "title_source, "
        "start_time, "
        "start_time_utc, "
        "sport_type, "
        "sub_sport_type, "
        "distance, "
        "dist_km, "
        "COALESCE(dist_km, ROUND(distance / 1000.0, 2)) AS distance_km_clean, "
        "COALESCE(duration, duration_sec) AS duration, "
        "avg_pace, "
        "avg_hr, "
        "max_hr, "
        "calories, "
        "gain_m, "
        "normalized_power, "
        "swolf, "
        "device_name, "
        "file_path, "
        "start_lat, "
        "start_lon, "
        "region, "
        "region_city, "
        "region_country, "
        "region_display, "
        "region_status, "
        "region_error, "
        "region_updated_at, "
        "region_attempt_count, "
        "weather_json, "
        "source_type, "
        "is_mock, "
        "is_race, "
        "race_source, "
        "race_confirmed_at, "
        "race_confidence, "
        "race_override, "
        "updated_at, "
        "CASE WHEN TRIM(COALESCE(NULLIF(track_json, ''), NULLIF(points_json, ''), '')) NOT IN ('', '[]', '{}') THEN 1 ELSE 0 END AS has_track"
    )

    conn = _conn()
    try:
        rows = conn.execute(
            f"""
            SELECT {select_fields}
            FROM activities
            {where_sql}
            ORDER BY COALESCE(start_time, updated_at) DESC, id DESC
            """,
            tuple(params),
        ).fetchall()
    finally:
        conn.close()

    all_rows_dicts = [dict(r) for r in rows]
    deduped_all_rows = _dedupe_activity_list_rows(all_rows_dicts)
    total_count = len(deduped_all_rows)
    safe_offset = max(0, int(offset or 0))
    safe_limit = max(0, int(limit or 0))
    rows_dicts = deduped_all_rows[safe_offset:safe_offset + safe_limit] if safe_limit else []
    # §契约 §二/§五:Resolver 层在响应中注入 sport_type_cn,前端不再做翻译
    for _row in rows_dicts:
        _resolved = (str(_row.get("sub_sport_type") or "").strip() or _row.get("sport_type"))
        _row["sport_type_cn"] = translate_sport_type(_resolved)
    return rows_dicts, total_count


# 别名保持向后兼容(老代码可能引用)
get_sport_hub_activity_page = get_activity_list_filtered


# §任务 2:地区选项排除集合(与 §任务 1 抽取逻辑保持一致)
_LOCATION_OPTION_EXCLUDE = ("待补全", "室内运动", "未知地点")


def get_activity_location_options(
    sport_filter: str = "all",
    gps_only: bool = True,
) -> list[dict[str, Any]]:
    """从全量符合条件的活动中生成地区选项。

    地区值优先级: region_display -> region -> region_city。
    排除空值、待补全、室内运动、未知地点。
    返回 [{value, label, count}],按 count DESC 再按 label 中文 ASC。

    复用 get_activity_list_filtered 的 sport_filter / gps_only 过滤语义,
    保证选项与列表页查询口径一致(同一批活动)。
    """
    display_sql = (
        "CASE "
        "WHEN COALESCE(NULLIF(sub_sport_type, ''), 'unknown') IN ("
        "'lap_swimming', 'open_water', 'open_water_swimming', "
        "'trail_running', 'road_cycling', 'mountain_biking', 'treadmill_running'"
        ") THEN sub_sport_type "
        "WHEN COALESCE(NULLIF(sport_type, ''), 'unknown') IN ("
        "'lap_swimming', 'open_water', 'open_water_swimming', "
        "'trail_running', 'road_cycling', 'mountain_biking', 'treadmill_running'"
        ") THEN sport_type "
        "ELSE COALESCE(NULLIF(sport_type, ''), 'unknown') "
        "END"
    )

    where_parts = [
        "COALESCE(source_type, 'fit_sdk') = 'fit_sdk'",
        "COALESCE(is_mock, 0) = 0",
        "deleted_at IS NULL",
    ]
    params: list[Any] = []

    if sport_filter and sport_filter != "all":
        where_parts.append(f"{display_sql} = ?")
        params.append(sport_filter)

    if gps_only:
        where_parts.append(
            f"{display_sql} IN ("
            "'running','hiking','mountaineering','cycling','walking',"
            "'trail_running','road_cycling','mountain_biking'"
            ")"
        )
        where_parts.append("start_lat IS NOT NULL")
        where_parts.append("start_lon IS NOT NULL")

    where_sql = "WHERE " + " AND ".join(where_parts)

    # 地区优先级解析:display -> region -> city
    # NULLIF 把空串转 NULL,COALESCE 取首个非 NULL
    region_expr = (
        "COALESCE(NULLIF(region_display, ''), "
        "NULLIF(region, ''), "
        "NULLIF(region_city, ''))"
    )

    # 排除列表展开为 IN(?, ?, ?)
    placeholders = ",".join(["?"] * len(_LOCATION_OPTION_EXCLUDE))
    exclude_params: list[str] = list(_LOCATION_OPTION_EXCLUDE)

    conn = _conn()
    try:
        rows = conn.execute(
            f"""
            SELECT {region_expr} AS region_value, COUNT(*) AS cnt
            FROM activities
            {where_sql}
              AND {region_expr} IS NOT NULL
              AND {region_expr} NOT IN ({placeholders})
            GROUP BY {region_expr}
            ORDER BY cnt DESC, region_value ASC
            """,
            tuple(params + exclude_params),
        ).fetchall()
    finally:
        conn.close()

    return [
        {"value": r[0], "label": r[0], "count": int(r[1])}
        for r in rows
        if r[0]  # 二次防御:过滤空字符串
    ]


def load_local_track(file_path: str) -> dict[str, Any]:
    """根据本地路径读取并解析轨迹文件，返回与 parse_track_file 一致的结构。"""
    import track_backend
    p = Path(file_path)
    if not p.is_file():
        return {"ok": False, "error": f"文件不存在: {file_path}"}
    try:
        data = track_backend.parse_track_file(str(p))
        conn = _conn()
        row = conn.execute(
            """
            SELECT id, sport_type, sub_sport_type, region, region_display,
                   dist_km, gain_m, max_alt_m, min_alt_m, total_descent_m,
                   up_count, down_count, max_single_climb_m, difficulty_score,
                   avg_grade_pct, max_slope_pct, min_slope_pct, uphill_pct, downhill_pct,
                   report_metrics_version, mtdi_score, mtdi_level, mtdi_level_name,
                   avg_pace, avg_hr, max_hr, calories, start_time, duration_sec
            FROM activities
            WHERE file_path = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (str(p),),
        ).fetchone()
        conn.close()
        activity = dict(row) if row else None
        return {"ok": True, "filename": p.name, "data": data, "activity": activity}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def build_activity_payload(filename: str, data: dict[str, Any], src_path: str | None = None) -> dict[str, Any]:
    import track_backend

    points = data.get("points") or []
    dist_km, duration_sec, gain_m = _summarize_track_points(points, track_backend)
    dist_km = float(data.get("distance_km") or dist_km or 0.0)
    duration_sec = int(data.get("duration_sec") or duration_sec or 0)
    gain_m = float(data.get("gain_m") or gain_m or 0.0)

    hr_values = [int(p["hr"]) for p in points if p.get("hr") is not None]
    alt_values = [float(p.get("alt") or 0.0) for p in points if p.get("alt") is not None]
    raw_title = str(data.get("title") or data.get("fit_title") or filename).strip()
    explicit_title_source = str(data.get("title_source") or "").strip()
    filename_stem = Path(str(filename or "")).stem.strip()
    if explicit_title_source:
        raw_title_source = explicit_title_source
    elif raw_title in {str(filename or "").strip(), filename_stem}:
        raw_title_source = "filename"
    else:
        raw_title_source = "fit_title" if data.get("title") or data.get("fit_title") else "filename"
    avg_hr = data.get("avg_hr")
    max_hr = data.get("max_hr")
    start_lat, start_lon = _extract_start_coordinates(points)
    resolved_start_lat = data.get("start_lat") if data.get("start_lat") is not None else start_lat
    resolved_start_lon = data.get("start_lon") if data.get("start_lon") is not None else start_lon
    region_fields = build_initial_region_fields(resolved_start_lat, resolved_start_lon)
    title, title_source = build_activity_display_title(
        current_title=raw_title,
        title_source=raw_title_source,
        sport_type=data.get("sport_type", "unknown"),
        sub_sport_type=data.get("fit_sub_sport") or data.get("sub_sport_type") or "unknown",
        region_display=region_fields.get("region_display") or region_fields.get("region") or "",
    )
    raw_weather_json = data.get("weather_json")
    weather_json = raw_weather_json
    if not weather_json and isinstance(data.get("weather"), dict) and data.get("weather"):
        weather_json = json.dumps(data.get("weather"), ensure_ascii=False)
    elif isinstance(weather_json, dict):
        weather_json = json.dumps(weather_json, ensure_ascii=False)
    has_gps = resolved_start_lat is not None and resolved_start_lon is not None
    has_weather = bool(weather_json)

    avg_stroke_distance = float(
        data.get("avg_stroke_distance")
        or (data.get("basic_info") or {}).get("avg_stroke_distance")
        or 0.0
    )

    return {
        "filename": filename,
        "title": title,
        "title_source": title_source,
        "sport_type": data.get("sport_type", "unknown"),
        "sub_sport_type": data.get("fit_sub_sport") or data.get("sub_sport_type") or "unknown",
        "dist_km": dist_km,
        "duration_sec": duration_sec,
        "gain_m": gain_m,
        "total_descent_m": float(data.get("total_descent_m") or 0),
        "total_descent_m_device": float(data.get("total_descent_m") or 0),  # FIT 设备值,不受 resolver/计算器覆写
        "max_alt_m": float(data.get("max_alt_m") or (max(alt_values) if alt_values else 0.0)),
        "avg_hr": int(avg_hr) if avg_hr is not None else (int(round(sum(hr_values) / len(hr_values))) if hr_values else None),
        "max_hr": int(max_hr) if max_hr is not None else (max(hr_values) if hr_values else None),
        "avg_cadence": None,
        "hr_decoupling": None,
        "tss": None,
        "points_json": points,
        "file_path": src_path,
        "start_time": data.get("start_time") or (points[0].get("time") if points else None),
        "start_time_utc": data.get("start_time_utc"),
        "start_lat": resolved_start_lat,
        "start_lon": resolved_start_lon,
        **region_fields,
        "weather_json": weather_json,
        "weather_status": "success" if has_weather else ("pending" if has_gps else "none"),
        "weather_updated_at": datetime.now().isoformat() if has_weather else None,
        "weather_attempt_count": 1 if has_gps else 0,
        "weather_error": None if has_weather or not has_gps else "weather unavailable",
        "device_name": data.get("device_name") or "",
        "avg_pace": round(duration_sec / dist_km, 2) if dist_km > 0 and duration_sec > 0 else None,
        "calories": data.get("calories"),
        "avg_power": data.get("avg_power") or (data.get("basic_info") or {}).get("avg_power"),
        "max_power": data.get("max_power") or (data.get("basic_info") or {}).get("max_power"),
        "normalized_power": data.get("normalized_power") or (data.get("basic_info") or {}).get("normalized_power"),
        "swolf": None,
        "avg_stroke_distance": avg_stroke_distance,
        "hr_curve": None,
        "speed_curve": None,
        "source_type": "fit_sdk",
        "is_mock": 0,
        # V9.4.4:Training Effect(Firstbeat 私有字段,从 fit_engine 透传)
        "aerobic_training_effect": data.get("aerobic_training_effect"),
        "anaerobic_training_effect": data.get("anaerobic_training_effect"),
    }


def _extract_start_coordinates(points: list[dict[str, Any]]) -> tuple[float | None, float | None]:
    for point in points:
        try:
            lat = point.get("lat")
            lon = point.get("lon")
            if lat is None or lon is None:
                continue
            return float(lat), float(lon)
        except (TypeError, ValueError):
            continue
    return None, None


def _coerce_lat_lon(lat: Any, lon: Any) -> tuple[float, float] | None:
    try:
        lat_val = float(lat)
        lon_val = float(lon)
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat_val <= 90 and -180 <= lon_val <= 180):
        return None
    return lat_val, lon_val


def build_initial_region_fields(lat: Any, lon: Any) -> dict[str, Any]:
    coord = _coerce_lat_lon(lat, lon)
    if coord is None:
        return {
            "region": "室内运动（无GPS）",
            "region_city": None,
            "region_country": None,
            "region_display": "室内运动",
            "region_status": "none",
            "region_error": None,
            "region_updated_at": datetime.now().isoformat(),
            "region_attempt_count": 0,
        }
    return {
        "region": "",
        "region_city": None,
        "region_country": None,
        "region_display": None,
        "region_status": "pending",
        "region_error": None,
        "region_updated_at": None,
        "region_attempt_count": 0,
    }


def _region_cache_key(lat: Any, lon: Any) -> tuple[str, float, float] | None:
    coord = _coerce_lat_lon(lat, lon)
    if coord is None:
        return None
    lat_round = round(coord[0], REGION_CACHE_PRECISION)
    lon_round = round(coord[1], REGION_CACHE_PRECISION)
    return f"{lat_round:.2f},{lon_round:.2f}", lat_round, lon_round


def _format_city_country(city: str | None, country: str | None) -> str:
    city_text = str(city or "").strip()
    country_text = str(country or "").strip()
    if city_text and country_text:
        return f"{city_text}/{country_text}"
    return city_text or country_text


def _first_geo_text(geo: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = str(geo.get(key) or "").strip()
        if value:
            return value
    return None


def _display_name_fallback(display_name: str, country: str | None) -> str | None:
    parts = [part.strip() for part in str(display_name or "").split(",") if part.strip()]
    if not parts:
        return None
    country_text = str(country or "").strip()
    for part in parts:
        if country_text and part == country_text:
            continue
        if any(ch.isdigit() for ch in part) and len(part) <= 8:
            continue
        return part
    return parts[0]


def _extract_city_country(geo: dict[str, Any] | None) -> tuple[str | None, str | None, str]:
    if not geo:
        return None, None, ""
    city = _first_geo_text(
        geo,
        (
            "city",
            "county",
            "town",
            "municipality",
            "village",
            "hamlet",
            "district",
            "state",
            "province",
            "region",
            "suburb",
            "neighbourhood",
            "locality",
            "protected_area",
            "nature_reserve",
            "park",
            "mountain",
            "peak",
            "tourism",
            "name",
        ),
    )
    country = str(geo.get("country") or "").strip() or None
    if not city:
        city = _display_name_fallback(str(geo.get("display_name") or ""), country)
    return city, country, _format_city_country(city, country)


def resolve_activity_region(lat: Any, lon: Any) -> str:
    cache_info = _region_cache_key(lat, lon)
    if cache_info is None:
        return "室内运动（无GPS）"
    cache_key, lat_round, lon_round = cache_info
    with _REGION_CACHE_LOCK:
        cached = _REGION_CACHE.get((lat_round, lon_round))
    if cached is not None:
        return cached
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT display FROM geocode_cache WHERE cache_key = ? AND status = 'success' LIMIT 1",
            (cache_key,),
        ).fetchone()
        if row:
            display = str(row["display"] or "").strip()
            conn.execute("UPDATE geocode_cache SET last_used_at = ? WHERE cache_key = ?", (datetime.now().isoformat(), cache_key))
            conn.commit()
            with _REGION_CACHE_LOCK:
                _REGION_CACHE[(lat_round, lon_round)] = display
            return display
    finally:
        conn.close()
    return ""


def resolve_preview_region(lat: Any, lon: Any) -> dict[str, Any]:
    """Resolve region for temporary GPX previews.

    This path may read/write geocode_cache, but must never touch activities.
    """
    base = build_initial_region_fields(lat, lon)
    cache_info = _region_cache_key(lat, lon)
    if cache_info is None:
        return base

    cache_key, lat_round, lon_round = cache_info
    now = datetime.now().isoformat()

    with _REGION_CACHE_LOCK:
        memory_display = _REGION_CACHE.get((lat_round, lon_round))
    if memory_display:
        return {
            **base,
            "region": memory_display,
            "region_display": memory_display,
            "region_status": "success",
            "region_error": None,
            "region_updated_at": now,
        }

    try:
        conn = _conn()
        try:
            row = conn.execute(
                "SELECT city, country, display FROM geocode_cache WHERE cache_key = ? AND status = 'success' LIMIT 1",
                (cache_key,),
            ).fetchone()
            if row:
                display = str(row["display"] or "").strip()
                if display:
                    conn.execute("UPDATE geocode_cache SET last_used_at = ? WHERE cache_key = ?", (now, cache_key))
                    conn.commit()
                    with _REGION_CACHE_LOCK:
                        _REGION_CACHE[(lat_round, lon_round)] = display
                    return {
                        **base,
                        "region": display,
                        "region_city": row["city"],
                        "region_country": row["country"],
                        "region_display": display,
                        "region_status": "success",
                        "region_error": None,
                        "region_updated_at": now,
                    }
        finally:
            conn.close()
    except Exception as cache_exc:
        logger.warning("GPX preview geocode cache read failed: %s", cache_exc)

    try:
        geo = reverse_geocode(lat_round, lon_round)
        city, country, display = _extract_city_country(geo)
        if not display:
            raise RuntimeError("未返回城市/国家")

        try:
            conn = _conn()
            try:
                _write_geocode_cache(conn, cache_key, lat_round, lon_round, city, country, display, "success", None)
                conn.commit()
            finally:
                conn.close()
        except Exception as cache_exc:
            logger.warning("GPX preview geocode cache write failed: %s", cache_exc)
        with _REGION_CACHE_LOCK:
            _REGION_CACHE[(lat_round, lon_round)] = display
        return {
            **base,
            "region": display,
            "region_city": city,
            "region_country": country,
            "region_display": display,
            "region_status": "success",
            "region_error": None,
            "region_updated_at": datetime.now().isoformat(),
        }
    except Exception as exc:
        message = str(exc)
        try:
            conn = _conn()
            try:
                _write_geocode_cache(conn, cache_key, lat_round, lon_round, None, None, "", "failed", message)
                conn.commit()
            finally:
                conn.close()
        except Exception as cache_exc:
            logger.warning("GPX preview geocode cache write failed: %s", cache_exc)
        return {
            **base,
            "region": "",
            "region_city": None,
            "region_country": None,
            "region_display": "",
            "region_status": "failed",
            "region_error": message,
            "region_updated_at": datetime.now().isoformat(),
            "region_attempt_count": 1,
        }


def _write_geocode_cache(conn: sqlite3.Connection, cache_key: str, lat_round: float, lon_round: float, city: str | None, country: str | None, display: str, status: str, error: str | None) -> None:
    now = datetime.now().isoformat()
    conn.execute(
        """
        INSERT INTO geocode_cache (cache_key, lat_round, lon_round, city, country, display, provider, status, error, created_at, updated_at, last_used_at)
        VALUES (?, ?, ?, ?, ?, ?, 'nominatim', ?, ?, ?, ?, ?)
        ON CONFLICT(cache_key) DO UPDATE SET
            city = excluded.city,
            country = excluded.country,
            display = excluded.display,
            provider = excluded.provider,
            status = excluded.status,
            error = excluded.error,
            updated_at = excluded.updated_at,
            last_used_at = excluded.last_used_at
        """,
        (cache_key, lat_round, lon_round, city, country, display, status, error, now, now, now),
    )


def _region_enrich_can_call_provider() -> bool:
    if REGION_ENRICH_PROVIDER_COOLDOWN_UNTIL is None:
        return True
    return datetime.now(timezone.utc) >= REGION_ENRICH_PROVIDER_COOLDOWN_UNTIL


def _region_enrich_provider_cooldown(reason: str) -> str:
    global REGION_ENRICH_PROVIDER_COOLDOWN_UNTIL
    REGION_ENRICH_PROVIDER_COOLDOWN_UNTIL = datetime.now(timezone.utc) + timedelta(minutes=REGION_PROVIDER_COOLDOWN_MINUTES)
    logger.warning("Nominatim 地区补全进入 cooldown: reason=%s until=%s", reason, REGION_ENRICH_PROVIDER_COOLDOWN_UNTIL.isoformat())
    return REGION_ENRICH_PROVIDER_COOLDOWN_UNTIL.isoformat()


def _region_enrich_activity_update_sql(*, include_title: bool, inferred: bool = False) -> str:
    title_sql = "title = ?, title_source = ?," if include_title else ""
    source_sql = "region_source = 'offline_geocoder', region_confidence = 'medium'," if inferred else "region_source = 'nominatim', region_confidence = 'high',"
    status = "inferred" if inferred else "success"
    return f"""
        UPDATE activities
        SET {title_sql}
            region_city = ?, region_country = ?, region_display = ?, region = ?,
            region_status = '{status}', region_error = NULL, {source_sql}
            region_updated_at = ?, updated_at = updated_at
        WHERE id = ?
    """


def _region_enrich_apply_to_matching_activities(
    *,
    cache_key: str,
    lat_round: float,
    lon_round: float,
    city: Any,
    country: Any,
    display: Any,
    source: str = "nominatim",
) -> dict[str, int]:
    display_text = str(display or "").strip()
    if not display_text:
        return {"updated": 0, "title_updated": 0, "title_protected": 0}
    inferred = source == "offline_geocoder"
    conn = _conn()
    try:
        rows = conn.execute(
            """
            SELECT id, start_lat, start_lon, title, title_source, sport_type, sub_sport_type
            FROM activities
            WHERE COALESCE(deleted_at, '') = ''
              AND region_status IN ('pending', 'failed', 'inferred')
              AND start_lat IS NOT NULL
              AND start_lon IS NOT NULL
              AND printf('%.2f,%.2f', round(start_lat, 2), round(start_lon, 2)) = ?
            ORDER BY id ASC
            """,
            (cache_key,),
        ).fetchall()
        updated = 0
        title_updated = 0
        title_protected = 0
        now = datetime.now().isoformat()
        for row in rows:
            allow_title_update = (not inferred) and _can_region_update_activity_title(row["title_source"], row["title"])
            if allow_title_update:
                title, title_source = build_activity_display_title(
                    current_title=row["title"],
                    title_source=row["title_source"],
                    sport_type=row["sport_type"],
                    sub_sport_type=row["sub_sport_type"],
                    region_display=display_text,
                )
                params = (title, title_source, city, country, display_text, display_text, now, int(row["id"]))
                title_updated += 1
            else:
                params = (city, country, display_text, display_text, now, int(row["id"]))
                if str(row["title"] or "").strip():
                    title_protected += 1
            conn.execute(_region_enrich_activity_update_sql(include_title=allow_title_update, inferred=inferred), params)
            updated += 1
        if updated:
            conn.execute("UPDATE geocode_cache SET last_used_at = ? WHERE cache_key = ?", (now, cache_key))
        conn.commit()
        return {"updated": updated, "title_updated": title_updated, "title_protected": title_protected}
    finally:
        conn.close()


def _region_pending_rows(limit: int) -> list[sqlite3.Row]:
    conn = _conn()
    try:
        return conn.execute(
            """
            SELECT id, start_lat, start_lon, region_attempt_count,
                   title, title_source, sport_type, sub_sport_type, region_status, region_updated_at
            FROM activities
            WHERE COALESCE(deleted_at, '') = ''
              AND region_status IN ('pending', 'failed', 'inferred')
              AND start_lat IS NOT NULL
              AND start_lon IS NOT NULL
              AND (
                region_status = 'inferred'
                OR COALESCE(region_attempt_count, 0) < 3
                OR region_updated_at IS NULL
                OR region_updated_at < datetime('now', ?)
              )
            ORDER BY
              CASE
                WHEN region_status = 'inferred' THEN 0
                WHEN region_updated_at IS NULL THEN 1
                ELSE 2
              END ASC,
              COALESCE(start_time, updated_at) ASC,
              id ASC
            LIMIT ?
            """,
            (f"-{REGION_ENRICH_RETRY_COOLDOWN_MINUTES} minutes", int(limit)),
        ).fetchall()
    finally:
        conn.close()


def region_enrichment_dry_run(years: list[int] | None = None, conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    owns_conn = conn is None
    db = conn or _conn()
    try:
        year_filter = ""
        params: list[Any] = []
        if years:
            clean_years = [str(int(year)) for year in years]
            placeholders = ",".join("?" for _ in clean_years)
            year_filter = f"AND substr(COALESCE(a.start_time, ''), 1, 4) IN ({placeholders})"
            params.extend(clean_years)
        rows = db.execute(
            f"""
            SELECT substr(COALESCE(a.start_time, ''), 1, 4) AS year,
                   COUNT(*) AS pending_gps,
                   SUM(CASE WHEN g.status = 'success' THEN 1 ELSE 0 END) AS cache_hit,
                   COUNT(DISTINCT printf('%.2f,%.2f', round(a.start_lat, 2), round(a.start_lon, 2))) AS unique_coords,
                   SUM(CASE WHEN COALESCE(a.title_source, '') IN ('auto','auto_sport','auto_region_sport','garmin_auto','coros_auto','region_auto')
                         OR (COALESCE(a.title_source, '') = 'filename' AND COALESCE(a.title, '') LIKE '%activity%')
                         THEN 1 ELSE 0 END) AS auto_title_candidates
            FROM activities a
            LEFT JOIN geocode_cache g
              ON g.cache_key = printf('%.2f,%.2f', round(a.start_lat, 2), round(a.start_lon, 2))
            WHERE COALESCE(a.deleted_at, '') = ''
              AND a.region_status IN ('pending', 'failed', 'inferred')
              AND a.start_lat IS NOT NULL
              AND a.start_lon IS NOT NULL
              {year_filter}
            GROUP BY year
            ORDER BY year
            """,
            tuple(params),
        ).fetchall()
        by_year = []
        for row in rows:
            pending = int(row["pending_gps"] or 0)
            cache_hit = int(row["cache_hit"] or 0)
            unique_coords = int(row["unique_coords"] or 0)
            auto_titles = int(row["auto_title_candidates"] or 0)
            by_year.append({
                "year": int(row["year"]) if str(row["year"] or "").isdigit() else None,
                "pending_gps_activity_count": pending,
                "cache_hit_activity_count": cache_hit,
                "nominatim_unique_coord_count": max(0, unique_coords),
                "auto_title_update_candidate_count": auto_titles,
                "protected_title_count": max(0, pending - auto_titles),
            })
        return {"ok": True, "years": by_year}
    finally:
        if owns_conn:
            db.close()


def run_region_enrichment_once(limit: int = REGION_ENRICH_LIMIT, max_requests: int = REGION_ENRICH_MAX_REQUESTS, offline_resolver: Any | None = None) -> dict[str, Any]:
    if not _REGION_ENRICH_LOCK.acquire(blocking=False):
        return {"ok": True, "skipped": True, "reason": "running"}
    processed = 0
    success = 0
    failed = 0
    cache_hits = 0
    requests_count = 0
    consecutive_failures = 0
    title_updated = 0
    title_protected = 0
    inferred = 0
    stopped_reason = ""
    provider_cooldown_until = ""
    try:
        rows = _region_pending_rows(limit)
        requested_keys: set[str] = set()
        for row in rows:
            if consecutive_failures >= 3:
                stopped_reason = "consecutive_failures"
                break
            processed += 1
            activity_id = int(row["id"])
            cache_info = _region_cache_key(row["start_lat"], row["start_lon"])
            if cache_info is None:
                continue
            cache_key, lat_round, lon_round = cache_info
            conn = _conn()
            try:
                cached = conn.execute(
                    "SELECT city, country, display FROM geocode_cache WHERE cache_key = ? AND status = 'success' LIMIT 1",
                    (cache_key,),
                ).fetchone()
                if cached:
                    result = _region_enrich_apply_to_matching_activities(
                        cache_key=cache_key,
                        lat_round=lat_round,
                        lon_round=lon_round,
                        city=cached["city"],
                        country=cached["country"],
                        display=cached["display"],
                    )
                    cache_hits += int(result["updated"])
                    success += int(result["updated"])
                    title_updated += int(result["title_updated"])
                    title_protected += int(result["title_protected"])
                    continue
            finally:
                conn.close()

            if cache_key in requested_keys:
                continue
            requested_keys.add(cache_key)
            if requests_count >= max_requests:
                stopped_reason = "request_budget_exhausted"
                if offline_resolver:
                    offline = offline_resolver(lat_round, lon_round)
                    city, country, display = _extract_city_country(offline)
                    result = _region_enrich_apply_to_matching_activities(
                        cache_key=cache_key,
                        lat_round=lat_round,
                        lon_round=lon_round,
                        city=city,
                        country=country,
                        display=display,
                        source="offline_geocoder",
                    )
                    inferred += int(result["updated"])
                    title_protected += int(result["title_protected"])
                continue
            if not _region_enrich_can_call_provider():
                stopped_reason = "provider_cooldown"
                break
            if requests_count > 0:
                time.sleep(random.uniform(GEOCODE_REQUEST_INTERVAL_MIN_SEC, GEOCODE_REQUEST_INTERVAL_MAX_SEC))
            requests_count += 1
            try:
                geo = reverse_geocode(lat_round, lon_round)
                city, country, display = _extract_city_country(geo)
                if not display:
                    raise RuntimeError("未返回城市/国家")
                conn = _conn()
                try:
                    _write_geocode_cache(conn, cache_key, lat_round, lon_round, city, country, display, "success", None)
                    conn.commit()
                finally:
                    conn.close()
                result = _region_enrich_apply_to_matching_activities(
                    cache_key=cache_key,
                    lat_round=lat_round,
                    lon_round=lon_round,
                    city=city,
                    country=country,
                    display=display,
                )
                with _REGION_CACHE_LOCK:
                    _REGION_CACHE[(lat_round, lon_round)] = display
                success += int(result["updated"])
                title_updated += int(result["title_updated"])
                title_protected += int(result["title_protected"])
                consecutive_failures = 0
            except Exception as exc:
                message = str(exc)
                if "429" in message or "too many requests" in message.lower():
                    provider_cooldown_until = _region_enrich_provider_cooldown("rate_limited")
                    stopped_reason = "provider_rate_limited"
                conn = _conn()
                try:
                    _write_geocode_cache(conn, cache_key, lat_round, lon_round, None, None, "", "failed", message)
                    conn.execute(
                        """
                        UPDATE activities
                        SET region_status = 'failed', region_error = ?, region_attempt_count = COALESCE(region_attempt_count, 0) + 1, region_updated_at = ?, updated_at = updated_at
                        WHERE id = ?
                        """,
                        (message, datetime.now().isoformat(), activity_id),
                    )
                    conn.commit()
                finally:
                    conn.close()
                failed += 1
                consecutive_failures += 1
                if offline_resolver:
                    offline = offline_resolver(lat_round, lon_round)
                    city, country, display = _extract_city_country(offline)
                    result = _region_enrich_apply_to_matching_activities(
                        cache_key=cache_key,
                        lat_round=lat_round,
                        lon_round=lon_round,
                        city=city,
                        country=country,
                        display=display,
                        source="offline_geocoder",
                    )
                    inferred += int(result["updated"])
                    title_protected += int(result["title_protected"])
                if stopped_reason == "provider_rate_limited":
                    break
        return {
            "ok": True,
            "processed": processed,
            "success": success,
            "failed": failed,
            "cache_hits": cache_hits,
            "requests": requests_count,
            "inferred": inferred,
            "title_updated": title_updated,
            "title_protected": title_protected,
            "stopped_reason": stopped_reason,
            "provider_cooldown_until": provider_cooldown_until or (REGION_ENRICH_PROVIDER_COOLDOWN_UNTIL.isoformat() if REGION_ENRICH_PROVIDER_COOLDOWN_UNTIL else ""),
        }
    finally:
        _REGION_ENRICH_LOCK.release()


def refresh_activity_region(activity_id: int) -> dict[str, Any]:
    """Manually re-run reverse geocoding for one activity."""
    aid = int(activity_id or 0)
    if aid <= 0:
        return {"ok": False, "error": "无效活动 ID"}

    conn = _conn()
    try:
        row = conn.execute(
            """
            SELECT id, start_lat, start_lon, title, title_source, sport_type, sub_sport_type
            FROM activities
            WHERE id = ? AND COALESCE(deleted_at, '') = ''
            LIMIT 1
            """,
            (aid,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return {"ok": False, "error": "未找到活动记录"}

    cache_info = _region_cache_key(row["start_lat"], row["start_lon"])
    if cache_info is None:
        title, title_source = build_activity_display_title(
            current_title=row["title"],
            title_source=row["title_source"],
            sport_type=row["sport_type"],
            sub_sport_type=row["sub_sport_type"],
            region_display="室内运动",
        )
        conn = _conn()
        try:
            conn.execute(
                """
                UPDATE activities
                SET title = ?, title_source = ?,
                    region_status = 'none',
                    region_source = 'none',
                    region_confidence = 'none',
                    region_display = '室内运动',
                    region = '室内运动（无GPS）',
                    region_error = NULL,
                    region_updated_at = ?,
                    updated_at = updated_at
                WHERE id = ?
                """,
                (title, title_source, datetime.now().isoformat(), aid),
            )
            conn.commit()
        finally:
            conn.close()
        return {
            "ok": True,
            "region": "室内运动（无GPS）",
            "region_display": "室内运动",
            "region_status": "none",
        }

    cache_key, lat_round, lon_round = cache_info
    now = datetime.now().isoformat()

    conn = _conn()
    try:
        cached = conn.execute(
            "SELECT city, country, display FROM geocode_cache WHERE cache_key = ? AND status = 'success' LIMIT 1",
            (cache_key,),
        ).fetchone()
        if cached and str(cached["display"] or "").strip():
            display = str(cached["display"] or "").strip()
            title, title_source = build_activity_display_title(
                current_title=row["title"],
                title_source=row["title_source"],
                sport_type=row["sport_type"],
                sub_sport_type=row["sub_sport_type"],
                region_display=display,
            )
            conn.execute(
                """
                UPDATE activities
                SET title = ?, title_source = ?,
                    region_city = ?, region_country = ?, region_display = ?, region = ?,
                    region_status = 'success',
                    region_source = 'nominatim',
                    region_confidence = 'high',
                    region_error = NULL, region_updated_at = ?,
                    updated_at = updated_at
                WHERE id = ?
                """,
                (title, title_source, cached["city"], cached["country"], display, display, now, aid),
            )
            conn.execute("UPDATE geocode_cache SET last_used_at = ? WHERE cache_key = ?", (now, cache_key))
            conn.commit()
            with _REGION_CACHE_LOCK:
                _REGION_CACHE[(lat_round, lon_round)] = display
            return {
                "ok": True,
                "region": display,
                "region_city": cached["city"],
                "region_country": cached["country"],
                "region_display": display,
                "region_status": "success",
                "cache_hit": True,
            }
    finally:
        conn.close()

    try:
        geo = reverse_geocode(lat_round, lon_round)
        city, country, display = _extract_city_country(geo)
        if not display:
            raise RuntimeError("未返回城市/国家")
        title, title_source = build_activity_display_title(
            current_title=row["title"],
            title_source=row["title_source"],
            sport_type=row["sport_type"],
            sub_sport_type=row["sub_sport_type"],
            region_display=display,
        )
        conn = _conn()
        try:
            _write_geocode_cache(conn, cache_key, lat_round, lon_round, city, country, display, "success", None)
            conn.execute(
                """
                UPDATE activities
                SET title = ?, title_source = ?,
                    region_city = ?, region_country = ?, region_display = ?, region = ?,
                    region_status = 'success',
                    region_source = 'nominatim',
                    region_confidence = 'high',
                    region_error = NULL, region_updated_at = ?,
                    updated_at = updated_at
                WHERE id = ?
                """,
                (title, title_source, city, country, display, display, datetime.now().isoformat(), aid),
            )
            conn.commit()
        finally:
            conn.close()
        with _REGION_CACHE_LOCK:
            _REGION_CACHE[(lat_round, lon_round)] = display
        return {
            "ok": True,
            "region": display,
            "region_city": city,
            "region_country": country,
            "region_display": display,
            "region_status": "success",
            "cache_hit": False,
        }
    except Exception as exc:
        message = str(exc)
        conn = _conn()
        try:
            _write_geocode_cache(conn, cache_key, lat_round, lon_round, None, None, "", "failed", message)
            conn.execute(
                """
                UPDATE activities
                SET region_status = 'failed',
                    region_source = 'nominatim',
                    region_confidence = 'none',
                    region_error = ?,
                    region_attempt_count = COALESCE(region_attempt_count, 0) + 1,
                    region_updated_at = ?,
                    updated_at = updated_at
                WHERE id = ?
                """,
                (message, datetime.now().isoformat(), aid),
            )
            conn.commit()
        finally:
            conn.close()
        return {"ok": False, "error": message, "region_status": "failed"}


def start_region_enrichment_background(limit: int = REGION_ENRICH_LIMIT, on_complete = None) -> None:
    def _run():
        result = run_region_enrichment_once(limit=limit)
        if callable(on_complete):
            try:
                on_complete(result)
            except Exception:
                pass
    thread = threading.Thread(target=_run, daemon=True)
    thread.start()


def ingest_activity_file(
    src_path: str,
    duplicate_action: str = "",
    new_filename: str | None = None,
) -> dict[str, Any]:
    import track_backend

    logger = _duplicate_check_logger()
    p = Path(src_path).expanduser().resolve()
    if not p.is_file():
        return {"ok": False, "error": f"文件不存在: {src_path}"}

    data = track_backend.parse_track_file(str(p))
    activity = build_activity_payload(p.name, data, str(p))

    if duplicate_action:
        logger.info(f"--- 用户查重操作 --- 文件: {p.name}, 选择操作: {duplicate_action}, 新文件名: {new_filename}")

    dup_res = check_duplicate_activity(
        start_time=activity.get("start_time"),
        dist_km=activity.get("dist_km", 0.0),
        duration_sec=activity.get("duration_sec", 0),
        points_json=activity.get("points_json", []),
        start_time_utc=activity.get("start_time_utc")
    )

    if dup_res.get("is_duplicate") and duplicate_action not in ("force", "merge"):
        return {
            "ok": True,
            "duplicate": True,
            "score": dup_res.get("score"),
            "duplicate_record": dup_res.get("duplicate_record"),
            "file_path": str(p),
            "filename": p.name,
        }

    # 如果是覆盖 (merge)，删除旧记录和旧文件
    if duplicate_action == "merge" and dup_res.get("duplicate_record"):
        old_record = dup_res.get("duplicate_record")
        old_id = old_record.get("id")
        old_file_path = old_record.get("file_path")
        if old_id:
            def _delete_old_record() -> None:
                conn = _conn()
                try:
                    conn.execute("DELETE FROM activities WHERE id = ?", (old_id,))
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
                finally:
                    conn.close()

            run_with_db_retry(_delete_old_record)
        if old_file_path and Path(old_file_path).exists():
            try:
                Path(old_file_path).unlink()
            except Exception:
                pass

    local_path = copy_track_to_local(str(p), new_filename if duplicate_action == "force" else None)
    activity["file_path"] = local_path
    activity["filename"] = Path(local_path).name
    activity_id = save_activity(activity)

    return {
        "ok": True,
        "filename": activity["filename"],
        "data": data,
        "activity": {
            "id": activity_id,
            "filename": activity["filename"],
            "sport_type": activity["sport_type"],
            "sub_sport_type": activity["sub_sport_type"],
            "dist_km": activity["dist_km"],
            "duration_sec": activity["duration_sec"],
            "gain_m": activity["gain_m"],
            "max_alt_m": activity["max_alt_m"],
            "file_path": local_path,
            "start_time": activity["start_time"],
        },
    }


def parse_route_for_preview(src_path: str, resolve_region: bool = True) -> dict[str, Any]:
    """解析 GPX/KML 临时轨迹，仅返回内存数据（不持久化，不写 DB，不拷贝文件）。
    
    契约依据：
    - §二 FIT 文件为唯一可信运动数据源，GPX/KML 是用后即抛型文件
    - §八 canonical DB 只存 fit_sdk 数据，不含 GPX/KML
    - Region 仅允许读写 geocode_cache，不触发 activities 写入
    """
    import track_backend

    p = Path(src_path).expanduser().resolve()
    if not p.is_file():
        return {"ok": False, "error": f"文件不存在: {src_path}"}
    if p.suffix.lower() not in (".gpx", ".kml"):
        return {"ok": False, "error": "仅支持导入 GPX/KML 轨迹文件"}

    data = track_backend.parse_track_file(str(p))
    points = data.get("points") or []

    # 复用 build_activity_payload 的计算逻辑（距离/时间/心率等）
    activity = build_activity_payload(p.name, data, str(p))
    activity["gain_m"] = float(_compute_gpx_fallback_gain_m(points))

    # ====== Region 解析（仅 geocode_cache；不写 activities，不触发 enrichment 线程）======
    start_lat = activity.get("start_lat")
    start_lon = activity.get("start_lon")
    region_fields = resolve_preview_region(start_lat, start_lon) if resolve_region else build_initial_region_fields(start_lat, start_lon)

    # 前端轨迹报告需要的衍生指标 — 统一算法：FIT 和临时轨迹共用 compute_report_metrics
    dist_km_val = float(activity.get("dist_km") or 0.0)
    gain_m_val = float(activity.get("gain_m") or 0.0)
    report = compute_report_metrics(points, dist_km_val, gain_m_val)
    _attach_gpx_preview_mtdi(activity, report)

    return {
        "ok": True,
        "filename": p.name,
        "data": {
            "points": points,
            "placemarks": data.get("placemarks") or [],
            "weather": data.get("weather") or {},
        },
        "activity": {
            "id": None,  # ← 关键：无 DB id，前端自动切换 temporary_session
            "filename": p.name,
            "sport_type": activity["sport_type"],
            "sub_sport_type": activity["sub_sport_type"],
            "dist_km": activity["dist_km"],
            "duration_sec": activity["duration_sec"],
            "gain_m": activity["gain_m"],
            "max_alt_m": activity["max_alt_m"],
            "min_alt_m": report.get("min_alt_m"),
            "total_descent_m": report.get("total_descent_m"),
            "avg_grade_pct": report.get("avg_grade_pct"),
            "max_slope_pct": report.get("max_slope_pct"),
            "min_slope_pct": report.get("min_slope_pct"),
            "uphill_pct": report.get("uphill_pct"),
            "downhill_pct": report.get("downhill_pct"),
            "up_count": report.get("up_count"),
            "down_count": report.get("down_count"),
            "max_single_climb_m": report.get("max_single_climb_m"),
            "difficulty_score": report.get("difficulty_score"),
            "mtdi_score": activity.get("mtdi_score"),
            "mtdi_level": activity.get("mtdi_level"),
            "mtdi_level_name": activity.get("mtdi_level_name"),
            "avg_hr": activity["avg_hr"],
            "max_hr": activity["max_hr"],
            "calories": activity["calories"],
            "avg_pace": activity["avg_pace"],
            "start_time": activity["start_time"],
            "start_lat": start_lat,
            "start_lon": start_lon,
            "region": region_fields.get("region") or "",
            "region_city": region_fields.get("region_city"),
            "region_country": region_fields.get("region_country"),
            "region_status": region_fields.get("region_status"),
            "region_error": region_fields.get("region_error"),
            "region_display": region_fields.get("region_display") or region_fields.get("region") or "",
            "weather": data.get("weather") or {},
        },
    }


def parse_gpx_for_preview(src_path: str) -> dict[str, Any]:
    """兼容旧 API：解析 GPX/KML 临时轨迹，不持久化。"""
    return parse_route_for_preview(src_path)


def compute_report_metrics(
    points: list[dict[str, Any]],
    dist_km: float,
    gain_m: float,
) -> dict[str, Any]:
    """报告 canonical 派生指标计算器（FIT 和 GPX 共用一组算法）。

    CONTRACT §2.1 / §五 / §5.5:
    - 所有输出字段来自 points 遍历，可算就算，不可算才 None
    - avg_grade_pct 由后端统一计算（前端不得推导）
    - 前端仅读取 activityMetrics 展示，不得重复计算
    """
    if not points or len(points) < 2:
        return {}

    min_alt = points[0].get("alt", 0)
    total_descent = 0.0
    last_alt = min_alt
    for p in points[1:]:
        alt = p.get("alt", 0)
        if alt < min_alt:
            min_alt = alt
        dalt = alt - last_alt
        # 阈值 0.1m 适配 1 秒采样 FIT 数据 (设备值优先,此处为 fallback)
        if dalt < -0.1:
            total_descent += abs(dalt)
        last_alt = alt

    up_count = 0
    down_count = 0
    max_single_climb = 0.0
    hill_state = 0
    hill_ref_alt = points[0].get("alt", 0)
    hill_peak = hill_ref_alt
    hill_valley = hill_ref_alt
    HILL_THRESHOLD = 15

    for p in points[1:]:
        alt = p.get("alt", 0)
        if hill_state == 1:
            if alt > hill_peak:
                hill_peak = alt
            elif hill_peak - alt >= HILL_THRESHOLD:
                climb = hill_peak - hill_valley
                if climb >= HILL_THRESHOLD:
                    up_count += 1
                    if climb > max_single_climb:
                        max_single_climb = climb
                hill_state = -1
                hill_valley = alt
        elif hill_state == -1:
            if alt < hill_valley:
                hill_valley = alt
            elif alt - hill_valley >= HILL_THRESHOLD:
                if hill_peak - hill_valley >= HILL_THRESHOLD:
                    down_count += 1
                hill_state = 1
                hill_peak = alt
        else:
            if alt - hill_ref_alt >= HILL_THRESHOLD:
                hill_state = 1
                hill_valley = hill_ref_alt
                hill_peak = alt
            elif hill_ref_alt - alt >= HILL_THRESHOLD:
                hill_state = -1
                hill_peak = hill_ref_alt
                hill_valley = alt

    if hill_state == 1:
        climb = hill_peak - hill_valley
        if climb >= HILL_THRESHOLD:
            up_count += 1
            if climb > max_single_climb:
                max_single_climb = climb
    elif hill_state == -1:
        if hill_peak - hill_valley >= HILL_THRESHOLD:
            down_count += 1

    diff_score = 0
    if dist_km > 5:
        diff_score += 1
    if dist_km > 10:
        diff_score += 1
    if dist_km > 15:
        diff_score += 1
    if gain_m > 200:
        diff_score += 1
    if gain_m > 500:
        diff_score += 1
    if gain_m > 800:
        diff_score += 1
    if max_single_climb > 100:
        diff_score += 1
    if max_single_climb > 300:
        diff_score += 1
    if up_count > 3:
        diff_score += 1
    if up_count > 8:
        diff_score += 1

    _grade = _compute_grade_metrics(points, dist_km, gain_m)
    return {
        "min_alt_m": round(float(min_alt), 1),
        "total_descent_m": round(float(total_descent), 1),
        "up_count": up_count,
        "down_count": down_count,
        "max_single_climb_m": round(float(max_single_climb), 1),
        "difficulty_score": diff_score,
        "avg_grade_pct": _grade.get("avg_grade_pct"),
        "max_slope_pct": _grade.get("max_slope_pct"),
        "min_slope_pct": _grade.get("min_slope_pct"),
        "uphill_pct": _grade.get("uphill_pct"),
        "downhill_pct": _grade.get("downhill_pct"),
        "report_metrics_version": 2,
    }


def _compute_grade_metrics(
    points: list[dict[str, Any]],
    dist_km: float,
    gain_m: float,
) -> dict[str, Any]:
    """轨迹报告坡度指标计算器（FIT 和 GPX 共用）。
    
    CONTRACT §5.5: 每个字段独立判定数据可用性。
    滑窗计算 max_slope / min_slope / uphill_pct / downhill_pct。
    """
    WINDOW_DISTANCE_M = 100.0
    MIN_WINDOW_DISTANCE_M = 60.0
    UPHILL_THRESHOLD = 3.0
    DOWNHILL_THRESHOLD = -3.0
    MAX_ABS_SLOPE = 45.0
    NOISE_ALT_THRESHOLD_M = 1.5

    result: dict[str, Any] = {
        "avg_grade_pct": None,
        "max_slope_pct": None,
        "min_slope_pct": None,
        "uphill_pct": None,
        "downhill_pct": None,
    }

    if not points or len(points) < 2:
        return result

    has_dist = any(p.get("dist_km") is not None for p in points)
    has_alt = any(p.get("alt") is not None for p in points)

    # 距离回退: 轨迹无 dist_km 但总距可用,按时间均匀插值后递归
    if not has_dist and dist_km and dist_km > 0 and len(points) >= 2:
        n = len(points)
        _enriched = []
        for i, p in enumerate(points):
            _p = dict(p)
            _p["dist_km"] = (dist_km * i) / (n - 1)
            _enriched.append(_p)
        return _compute_grade_metrics(_enriched, dist_km, gain_m)

    if not has_dist and not has_alt:
        return result

    # avg_grade_pct 独立计算
    if has_dist and dist_km and dist_km > 0 and gain_m is not None:
        avg = (gain_m / (dist_km * 1000.0)) * 100.0
        result["avg_grade_pct"] = round(max(0.0, min(avg, 100.0)), 1)

    if not has_alt:
        return result

    # 滑窗计算 max/min/uphill/downhill
    window_slopes: list[float] = []
    window_distances: list[float] = []
    n = len(points)
    for i in range(n):
        base_dist = points[i].get("dist_km")
        base_alt = points[i].get("alt")
        if base_dist is None or base_alt is None:
            continue
        for j in range(i + 1, n):
            cur_dist = points[j].get("dist_km")
            cur_alt = points[j].get("alt")
            if cur_dist is None or cur_alt is None:
                continue
            if cur_dist <= base_dist:
                continue
            distance_m = (cur_dist - base_dist) * 1000.0
            if distance_m < MIN_WINDOW_DISTANCE_M:
                continue
            if distance_m > WINDOW_DISTANCE_M * 1.5:
                break
            alt_delta = cur_alt - base_alt
            slope = (alt_delta / distance_m) * 100.0
            if abs(slope) > MAX_ABS_SLOPE:
                continue
            if abs(alt_delta) < NOISE_ALT_THRESHOLD_M:
                slope = 0.0
            window_slopes.append(slope)
            window_distances.append(distance_m)
            break

    if len(window_slopes) >= 3:
        smoothed: list[float] = []
        for k in range(len(window_slopes)):
            lo = max(0, k - 1)
            hi = min(len(window_slopes), k + 2)
            neighbor = sorted(window_slopes[lo:hi])
            smoothed.append(neighbor[len(neighbor) // 2])
        window_slopes = smoothed

    if window_slopes:
        result["max_slope_pct"] = round(max(window_slopes), 1)
        result["min_slope_pct"] = round(min(window_slopes), 1)

        uphill_m = 0.0
        downhill_m = 0.0
        valid_m = 0.0
        for k, s in enumerate(window_slopes):
            wd = window_distances[k] if k < len(window_distances) else WINDOW_DISTANCE_M
            valid_m += wd
            if s >= UPHILL_THRESHOLD:
                uphill_m += wd
            elif s <= DOWNHILL_THRESHOLD:
                downhill_m += wd

        if valid_m > 0:
            result["uphill_pct"] = round((uphill_m / valid_m) * 100.0, 1)
            result["downhill_pct"] = round((downhill_m / valid_m) * 100.0, 1)

    return result


def _compute_gpx_fallback_gain_m(points: list[dict[str, Any]]) -> int:
    """GPX preview-only cumulative gain for dense, disposable track data."""
    gain_m = 0.0
    for idx in range(1, len(points)):
        p0, p1 = points[idx - 1], points[idx]
        if p0.get("alt") is None or p1.get("alt") is None:
            continue
        dalt = float(p1.get("alt") or 0.0) - float(p0.get("alt") or 0.0)
        if dalt > GPX_FALLBACK_GAIN_THRESHOLD_M:
            gain_m += dalt
    return int(round(gain_m))


def _resolve_gpx_preview_sport_type(activity: dict[str, Any], report: dict[str, Any]) -> str:
    """Correct disposable GPX sport semantics when device metadata is too generic."""
    sport_type = str(activity.get("sport_type") or "unknown")
    dist_km = float(activity.get("dist_km") or 0.0)
    duration_sec = float(activity.get("duration_sec") or 0.0)
    gain_m = float(activity.get("gain_m") or 0.0)
    max_alt_m = float(activity.get("max_alt_m") or 0.0)
    max_single_climb_m = float(report.get("max_single_climb_m") or 0.0)
    speed_kmh = (dist_km / (duration_sec / 3600.0)) if duration_sec > 0 else 0.0

    generic_running = sport_type in {"running", "trail_running", "walking", "unknown"}
    long_high_climb = (
        duration_sec >= 2 * 3600
        and speed_kmh > 0
        and speed_kmh <= 5.5
        and gain_m >= 500
        and max_alt_m >= 2500
        and max_single_climb_m >= 100
    )
    if generic_running and long_high_climb:
        return "hiking"
    return sport_type


def _attach_gpx_preview_mtdi(activity: dict[str, Any], report: dict[str, Any]) -> None:
    """Attach MTDI fields for GPX preview so frontend narrative does not fall back to LV1."""
    from metrics_resolver import MetricsResolver

    sport_type = _resolve_gpx_preview_sport_type(activity, report)
    activity["sport_type"] = sport_type
    mtdi = MetricsResolver._calculate_track_difficulty(
        dist_km=activity.get("dist_km"),
        gain_m=activity.get("gain_m"),
        max_alt_m=activity.get("max_alt_m"),
        max_single_climb_m=report.get("max_single_climb_m"),
        sport_type=sport_type,
    )
    activity["mtdi_score"] = mtdi["score"]
    activity["mtdi_level"] = mtdi["level"]
    activity["mtdi_level_name"] = mtdi["level_name"]


def _summarize_track_points(points: list[dict[str, Any]], track_backend_module: Any) -> tuple[float, int, int]:
    dist_m = 0.0
    gain_m = 0.0
    for idx in range(1, len(points)):
        p0, p1 = points[idx - 1], points[idx]
        if p0.get("lat") is None or p0.get("lon") is None or p1.get("lat") is None or p1.get("lon") is None:
            continue
        dist_m += track_backend_module.haversine_m(p0["lat"], p0["lon"], p1["lat"], p1["lon"])
        if p0.get("alt") is not None and p1.get("alt") is not None:
            dalt = float(p1.get("alt") or 0.0) - float(p0.get("alt") or 0.0)
            # CONTRACT §5.5: 1.5m 噪声阈值 — 与 compute_report_metrics 一致
            if dalt > 1.5:
                gain_m += dalt

    duration_sec = 0
    timed_points = [p for p in points if p.get("time")]
    if len(timed_points) >= 2:
        try:
            start = datetime.fromisoformat(str(timed_points[0]["time"]).replace("Z", "+00:00"))
            end = datetime.fromisoformat(str(timed_points[-1]["time"]).replace("Z", "+00:00"))
            duration_sec = max(int((end - start).total_seconds()), 0)
        except ValueError:
            duration_sec = 0

    return round(dist_m / 1000.0, 2), duration_sec, int(round(gain_m))


def scan_fit_directory(local_dir: str) -> dict[str, Any]:
    """扫描配置文件夹中的所有 fit 文件，解析并过滤无 GPS 数据文件。"""
    import track_backend
    if not str(local_dir or "").strip():
        return {"ok": False, "error": "未配置 FIT 文件目录"}
    base = Path(local_dir).expanduser().resolve()
    if not base.is_dir():
        return {"ok": False, "error": f"目录不存在或不是有效文件夹: {local_dir}"}

    files = []
    valid = 0
    skipped = 0

    try:
        fit_files = []
        for root, _dirs, files_in_dir in os.walk(str(base)):
            for name in files_in_dir:
                if name.lower().endswith(".fit"):
                    fit_files.append(Path(root) / name)
        fit_files.sort(key=lambda p: (str(p.parent).lower(), p.name.lower()))
    except PermissionError:
        return {"ok": False, "error": "无读取权限"}

    for p in fit_files:
        try:
            data = track_backend.parse_track_file(str(p))
            points = data.get("points") or []
            dist_km, duration_sec, gain_m = _summarize_track_points(points, track_backend)
            
            start_lat = points[0].get("lat") if points else None
            start_lon = points[0].get("lon") if points else None
            
            has_gps = any(
                pt.get("lat") is not None and pt.get("lon") is not None
                for pt in points
            )
            if not has_gps:
                skipped += 1
                files.append({
                    "file_path": str(p),
                    "filename": p.name,
                    "valid": False,
                    "reason": "无GPS坐标数据",
                    "sport_type": data.get("sport_type", "unknown"),
                    "dist_km": dist_km,
                    "duration_sec": duration_sec,
                    "start_time": (points[0].get("time") if points else None),
                })
                continue
            valid += 1
            start_time = None
            if points and points[0].get("time"):
                start_time = points[0]["time"]
            files.append({
                "file_path": str(p),
                "filename": p.name,
                "valid": True,
                "sport_type": data.get("sport_type", "unknown"),
                "dist_km": dist_km,
                "duration_sec": duration_sec,
                "gain_m": gain_m,
                "start_time": start_time,
                "start_lat": start_lat,
                "start_lon": start_lon,
            })
        except Exception as exc:
            skipped += 1
            files.append({
                "file_path": str(p),
                "filename": p.name,
                "valid": False,
                "reason": "解析失败",
            })

    return {
        "ok": True,
        "files": files,
        "total": len(fit_files),
        "valid": valid,
        "skipped": skipped,
    }


def check_duplicate_activity(
    start_time: str | None,
    dist_km: float,
    duration_sec: int,
    points_json: list[dict[str, Any]] | None = None,
    start_time_utc: str | None = None,
    include_deleted: bool = False,
) -> dict[str, Any]:
    """
    检查是否有重复的活动记录。
    判断标准：
    1. 时间窗口粗筛：开始时间相差 <= 5分钟，且时长差异 <= 10%。
    2. 轨迹点空间匹配：如果提供了 points_json，计算经纬度重合度（距离<50米），阈值 90%。
    3. 核心运动数据匹配：距离差异 < 10%。
    """
    import track_backend
    import json
    from datetime import datetime

    logger = _duplicate_check_logger()

    deleted_clause = "" if include_deleted else "WHERE deleted_at IS NULL"
    conn = _conn()
    rows = conn.execute(
        f"""
        SELECT id, filename, file_path, start_time, start_time_utc, dist_km,
               duration_sec, points_json, updated_at, deleted_at
        FROM activities
        {deleted_clause}
        """
    ).fetchall()
    conn.close()

    def _parse_time(time_str: str | None) -> datetime | None:
        if not time_str: return None
        try:
            from datetime import timezone
            dt = datetime.fromisoformat(str(time_str).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            return None

    def _safe_time_diff_sec(dt1: datetime | None, dt2: datetime | None) -> float | None:
        if dt1 is None or dt2 is None:
            return None
        if (dt1.tzinfo is None) == (dt2.tzinfo is None):
            return abs((dt1 - dt2).total_seconds())
        # 兜底：如果一个是 aware，一个是 naive，去掉时区强制比较字面时间，避免报错
        return abs((dt1.replace(tzinfo=None) - dt2.replace(tzinfo=None)).total_seconds())

    best_match = None
    max_score = 0.0
    
    target_local = _parse_time(start_time)
    target_utc = _parse_time(start_time_utc)
    if not target_utc and points_json and len(points_json) > 0:
        target_utc = _parse_time(points_json[0].get("time"))

    scope = "active+deleted" if include_deleted else "active"
    logger.info(f"--- 开始查重 --- scope={scope}, 目标: start={start_time}, utc={start_time_utc}, dist={dist_km}km, dur={duration_sec}s, points={len(points_json) if points_json else 0}")

    for r in rows:
        r_dict = dict(r)
        score = 0.0
        
        db_local = _parse_time(r_dict.get("start_time"))
        db_utc = _parse_time(r_dict.get("start_time_utc"))
        
        if not db_utc and r_dict.get("points_json"):
            try:
                db_pts = json.loads(r_dict["points_json"])
                if db_pts and isinstance(db_pts, list) and len(db_pts) > 0:
                    db_utc = _parse_time(db_pts[0].get("time"))
            except Exception:
                pass
                
        # 1. 时间窗口粗筛 (优先比较 UTC，如果没有则比较 Local)
        time_diff_sec = None
        if target_utc and db_utc:
            time_diff_sec = _safe_time_diff_sec(target_utc, db_utc)
        elif target_local and db_local:
            time_diff_sec = _safe_time_diff_sec(target_local, db_local)
        # 如果连 local 和 utc 都交叉了，做最后兜底
        elif target_utc and db_local:
            time_diff_sec = _safe_time_diff_sec(target_utc, db_local)
        elif target_local and db_utc:
            time_diff_sec = _safe_time_diff_sec(target_local, db_utc)
            
        if time_diff_sec is not None:
            if time_diff_sec > 300: # 5分钟
                logger.info(f"[{r_dict['filename']}] 排除: 开始时间相差 {time_diff_sec}s > 300s")
                continue
        else:
            # 两个都没有时间，或者无法比较，扣分但不断然排除
            pass

        # 时长差异 <= 10%
        db_dur = r_dict.get("duration_sec") or 0
        if duration_sec > 0 and db_dur > 0:
            dur_diff_ratio = abs(db_dur - duration_sec) / max(duration_sec, 1)
            if dur_diff_ratio > 0.1:
                logger.info(f"[{r_dict['filename']}] 排除: 时长差异 {dur_diff_ratio*100:.1f}% > 10%")
                continue

        # 里程差异
        db_dist = r_dict.get("dist_km") or 0.0
        dist_diff_ratio = abs(db_dist - dist_km) / max(dist_km, 0.1) if dist_km > 0 else 0
        if dist_diff_ratio > 0.15: # 放宽一点到15%作为粗筛
             logger.info(f"[{r_dict['filename']}] 排除: 里程差异 {dist_diff_ratio*100:.1f}% > 15%")
             continue

        # 2. 空间匹配
        overlap_ratio = 0.0
        if points_json and r_dict.get("points_json"):
            try:
                db_points = json.loads(r_dict["points_json"])
                if db_points and isinstance(db_points, list) and len(db_points) > 0 and len(points_json) > 0:
                    # 降采样，最多取 100 个点进行比对，提高效率
                    step1 = max(1, len(points_json) // 100)
                    step2 = max(1, len(db_points) // 100)
                    sample1 = points_json[::step1]
                    sample2 = db_points[::step2]
                    
                    match_count = 0
                    for p1 in sample1:
                        if "lat" not in p1 or "lon" not in p1:
                            continue
                        # 寻找 sample2 中是否有距离 < 50m 的点
                        min_dist = float('inf')
                        for p2 in sample2:
                            if "lat" not in p2 or "lon" not in p2:
                                continue
                            d = track_backend.haversine_m(p1["lat"], p1["lon"], p2["lat"], p2["lon"])
                            if d < min_dist:
                                min_dist = d
                                if min_dist < 50: # 提前跳出
                                    break
                        if min_dist < 50:
                            match_count += 1
                            
                    overlap_ratio = match_count / len(sample1) if sample1 else 0.0
            except Exception as e:
                logger.warning(f"[{r_dict['filename']}] 空间匹配异常: {e}")

        # 计算综合分数
        score = 0.0
        if time_diff_sec is not None:
            if time_diff_sec <= 60:
                score += 30.0
            elif time_diff_sec <= 300:
                score += 15.0
                
        if dist_diff_ratio <= 0.05:
            score += 20.0
        elif dist_diff_ratio <= 0.1:
            score += 10.0
            
        if duration_sec > 0 and db_dur > 0:
            if abs(db_dur - duration_sec) / duration_sec <= 0.05:
                score += 20.0
            elif abs(db_dur - duration_sec) / duration_sec <= 0.1:
                score += 10.0

        if overlap_ratio >= 0.9:
            score += 30.0
        elif overlap_ratio >= 0.7:
            score += 15.0

        # 没有可比对轨迹点时,同一开始时间 + 几乎相同距离/时长本身就是强重复信号。
        # 旧评分在这种场景最高只有 70 分,会漏掉 Garmin/FIT 重复导入的同一活动。
        if (
            time_diff_sec is not None
            and time_diff_sec <= 60
            and dist_km > 0
            and duration_sec > 0
            and db_dur > 0
            and dist_diff_ratio <= 0.01
            and abs(db_dur - duration_sec) / max(duration_sec, 1) <= 0.01
        ):
            score = max(score, 85.0)

        record_status = "history/deleted" if r_dict.get("deleted_at") else "active"
        logger.info(f"[{r_dict['filename']}] 查重得分: {score} ({record_status}, 时间差: {time_diff_sec if time_diff_sec is not None else 'N/A'}s, 里程差: {dist_diff_ratio*100:.1f}%, 时长差: {dur_diff_ratio*100 if duration_sec>0 and db_dur>0 else 'N/A'}%, 重合度: {overlap_ratio*100:.1f}%)")

        if score > max_score:
            max_score = score
            best_match = r_dict

    # 设置阈值 80 为重复
    if max_score >= 80.0 and best_match:
        match_status = "history/deleted" if best_match.get("deleted_at") else "active"
        logger.info(f"--- 查重结果: 发现重复 --- 匹配记录: {best_match['filename']}, 状态: {match_status}, 分数: {max_score}")
        # 不返回完整的 points_json 以免日志过大
        best_match.pop("points_json", None)
        return {
            "is_duplicate": True,
            "score": max_score,
            "duplicate_record": best_match
        }
        
    logger.info(f"--- 查重结果: 无重复 --- 最高分: {max_score}")
    if best_match:
        best_match.pop("points_json", None)
    return {
        "is_duplicate": False,
        "score": max_score,
        "duplicate_record": best_match if max_score > 0 else None
    }


def copy_track_to_local(src_path: str, new_filename: str = None) -> str:
    """将源轨迹文件复制到 local_tracks 目录，以 filename 为基础生成唯一文件名，返回本地路径。"""
    src = Path(src_path)
    dest_dir = tracks_dir()
    
    if new_filename:
        stem = Path(new_filename).stem
        suffix = Path(new_filename).suffix or src.suffix
    else:
        stem = src.stem
        suffix = src.suffix
        
    dest = dest_dir / f"{stem}{suffix}"
    n = 1
    while dest.exists():
        dest = dest_dir / f"{stem}_{n}{suffix}"
        n += 1
    shutil.copy2(src, dest)
    return str(dest)


def compute_hrr_zones(resting_hr: int, max_hr: int) -> list[dict[str, Any]]:
    if not (resting_hr and max_hr and max_hr > resting_hr):
        return []
    hrr = max_hr - resting_hr
    zones = [
        ("Z1 轻松", 0.50, 0.60),
        ("Z2 有氧耐力", 0.60, 0.70),
        ("Z3 节奏", 0.70, 0.80),
        ("Z4 阈值", 0.80, 0.90),
        ("Z5 无氧爆发", 0.90, 1.00),
    ]
    return [
        {
            "zone": name,
            "pct_low": round(pct_low * 100),
            "pct_high": round(pct_high * 100),
            "hr_low": round(resting_hr + hrr * pct_low),
            "hr_high": round(resting_hr + hrr * pct_high),
        }
        for name, pct_low, pct_high in zones
    ]


def compute_hr_decoupling(
    first_half_points: list[dict[str, Any]],
    second_half_points: list[dict[str, Any]],
) -> float | None:
    """
    有氧解耦率：对比运动前半程与后半程的「配速/心率」比值变化。
    计算公式：
        Ratio_1 = (dist_first / time_first) / avg_hr_first
        Ratio_2 = (dist_second / time_second) / avg_hr_second
        Decoupling% = (1 - Ratio_2 / Ratio_1) * 100
    值越接近 0 表示有氧能力越稳定；正值（心率↑ 配速↓）提示耐力不足。
    """
    def _ratio(pts: list[dict[str, Any]]) -> float | None:
        if len(pts) < 2:
            return None
        total_dist = 0.0
        total_time_s = 0.0
        total_hr = 0.0
        valid = 0
        for i in range(1, len(pts)):
            p0, p1 = pts[i - 1], pts[i]
            t0 = _ts(p0)
            t1 = _ts(p1)
            if t0 is None or t1 is None or t1 <= t0:
                continue
            dist = _haversine(p0["lat"], p0["lon"], p1["lat"], p1["lon"])
            total_dist += dist
            total_time_s += (t1 - t0).total_seconds()
            if p0.get("hr") and p1.get("hr"):
                total_hr += (p0["hr"] + p1["hr"]) / 2.0
                valid += 1
        if total_time_s <= 0 or valid == 0:
            return None
        return (total_dist / total_time_s) / (total_hr / valid)

    r1 = _ratio(first_half_points)
    r2 = _ratio(second_half_points)
    if r1 is None or r2 is None or r1 == 0:
        return None
    return round((1 - r2 / r1) * 100, 2)


def compute_tss(
    duration_sec: int,
    normalized_power: float | None,
    coggan_if: float | None,
    resting_hr: int | None,
    max_hr: int | None,
) -> float:
    """
    训练压力评分（TSS）：
        - 已知 Coggan IF：TSS = (IF² × 训练时长 h) × 100
        - 已知 NP：TSS ≈ NP × 训练时长(h) × IF  （IF = NP / FTP）
        - 均不知时：用平均心率占比 × 时长估算
    """
    if coggan_if is not None and 0 < coggan_if <= 1.2:
        h = duration_sec / 3600.0
        return round((coggan_if ** 2) * h * 100, 1)

    if normalized_power is not None and resting_hr and max_hr:
        ftp = _hr_to_power_estimate(normalized_power, resting_hr, max_hr)
        if ftp > 0:
            np_ratio = normalized_power / ftp
            h = duration_sec / 3600.0
            return round((np_ratio ** 2) * h * 100, 1)

    if resting_hr and max_hr:
        avg_hr_est = (resting_hr + max_hr) * 0.65
        ratio = (avg_hr_est - resting_hr) / (max_hr - resting_hr)
        h = duration_sec / 3600.0
        return round((max(ratio, 0.1) ** 2) * h * 100, 1)

    return 0.0


def _hr_to_power_estimate(np: float, resting_hr: int, max_hr: int) -> float:
    hrr = max_hr - resting_hr
    if hrr <= 0:
        return 0.0
    est_if = ((np / 150.0) - 0.4) / 0.6
    return max(100.0, resting_hr + est_if * hrr)


def _ts(pt: dict[str, Any]) -> datetime | None:
    t = pt.get("time")
    if t is None:
        return None
    if isinstance(t, datetime):
        return t
    try:
        return datetime.fromisoformat(str(t).replace("Z", "+00:00"))
    except Exception:
        return None


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _parse_time_to_sec(value: Any) -> int | None:
    """将时间值转换为秒数。支持：整数秒、"HH:MM:SS"字符串、"MM:SS"字符串。"""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        s = value.strip()
        parts = s.split(":")
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 1 and s:
            return int(float(parts[0]))
    return None


import re

def _validate_number(val: Any) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return f if not math.isnan(f) else None
    except (ValueError, TypeError):
        return None

def _validate_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        f = float(val)
        if math.isnan(f):
            return None
        return int(f)
    except (ValueError, TypeError):
        return None

def _validate_time_format(val: Any) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() == "null":
        return None
    if re.match(r"^(\d{1,2}:)?\d{1,2}:\d{2}$", s):
        return s
    if re.match(r"^\d{1,2}'\d{2}\"?$", s):
        return s
    return None


def _merge_pb_predict(pb_value: Any, predict_value: Any) -> str | None:
    pb = str(pb_value).strip() if pb_value and str(pb_value).strip().lower() != "null" else None
    predict = str(predict_value).strip() if predict_value and str(predict_value).strip().lower() != "null" else None
    parts = []
    if pb:
        parts.append(f"🏆 {pb}")
    if predict:
        parts.append(f"📈 {predict}")
    return "｜".join(parts) if parts else None


def _first_present(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        if isinstance(value, str) and value.strip().lower() in {"", "null", "none"}:
            continue
        return value
    return None


def _is_meaningful_profile_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and value.strip().lower() in {"", "null", "none"}:
        return False
    return True


def _profile_field_labels(fields: list[str] | tuple[str, ...]) -> list[dict[str, str]]:
    return [{"field": field, "label": PROFILE_FIELD_LABELS.get(field, field)} for field in fields]


def build_profile_sync_field_summary(
    platform: str,
    incoming: dict[str, Any],
    merged: dict[str, Any],
    existing: dict[str, Any] | None,
) -> dict[str, Any]:
    existing = existing or {}
    updated_fields: list[str] = []
    preserved_fields: list[str] = []
    for key in PROFILE_CANONICAL_FIELDS:
        new_value = (incoming or {}).get(key)
        old_value = existing.get(key)
        if _is_meaningful_profile_value(new_value):
            if not _is_meaningful_profile_value(old_value) or old_value != new_value:
                updated_fields.append(key)
            continue
        if _is_meaningful_profile_value(old_value) and merged.get(key) == old_value:
            preserved_fields.append(key)

    quality, analysis_missing = _profile_data_quality(merged)
    display_only_missing = [
        field for field in PROFILE_DISPLAY_ONLY_FIELDS
        if not _is_meaningful_profile_value(merged.get(field))
    ]
    supports_remote = str(platform or "").strip().lower() == "garmin"
    return {
        "source_platform": str(platform or "").strip().lower(),
        "data_quality": quality,
        "missing_fields": analysis_missing,
        "updated_fields": updated_fields,
        "preserved_fields": preserved_fields,
        "display_only_missing_fields": display_only_missing,
        "analysis_required_fields": list(PROFILE_ANALYSIS_REQUIRED_FIELDS),
        "analysis_optional_fields": list(PROFILE_ANALYSIS_OPTIONAL_FIELDS),
        "updated_field_labels": _profile_field_labels(updated_fields),
        "preserved_field_labels": _profile_field_labels(preserved_fields),
        "missing_field_labels": _profile_field_labels(analysis_missing),
        "display_only_missing_field_labels": _profile_field_labels(display_only_missing),
        "analysis_required_field_labels": _profile_field_labels(PROFILE_ANALYSIS_REQUIRED_FIELDS),
        "analysis_optional_field_labels": _profile_field_labels(PROFILE_ANALYSIS_OPTIONAL_FIELDS),
        "supports_remote_activity_sync": supports_remote,
        "activity_sync_hint": (
            "可按日期范围直接同步 Garmin 活动 FIT 文件。"
            if supports_remote else
            "COROS 暂不支持远程活动同步；请使用本地 FIT、ZIP 或目录监听导入活动。"
        ),
    }


def write_profile_sync_field_summary(summary: dict[str, Any]) -> None:
    state = read_sync_state()
    source_platform = summary.get("source_platform")
    if source_platform:
        state["last_profile_source_platform"] = source_platform
    state["last_profile_data_quality"] = summary.get("data_quality")
    state["last_profile_missing_fields"] = summary.get("missing_fields") or []
    state["last_profile_updated_fields"] = summary.get("updated_fields") or []
    state["last_profile_preserved_fields"] = summary.get("preserved_fields") or []
    state["last_profile_display_only_missing_fields"] = summary.get("display_only_missing_fields") or []
    write_sync_state(state)


def build_profile_status_summary(current_watch_brand: str = "") -> dict[str, Any]:
    metadata = get_profile_sync_metadata()
    brand = str(current_watch_brand or "").strip().lower()
    source_platform = str(metadata.get("current_profile_source_platform") or "").strip().lower() or None
    if not source_platform and brand in {"garmin", "coros"}:
        source_platform = brand
    supports_remote = brand == "garmin"
    data_quality = metadata.get("data_quality")
    missing_fields = list(metadata.get("missing_fields") or [])
    updated_fields = list(metadata.get("updated_fields") or [])
    preserved_fields = list(metadata.get("preserved_fields") or [])
    display_only_missing = list(metadata.get("display_only_missing_fields") or [])
    return {
        "current_watch_brand": brand,
        "current_profile_source_platform": source_platform,
        "last_profile_sync_at": metadata.get("last_sync_time"),
        "last_profile_sync_status": metadata.get("sync_status"),
        "data_quality": data_quality,
        "missing_fields": missing_fields,
        "updated_fields": updated_fields,
        "preserved_fields": preserved_fields,
        "display_only_missing_fields": display_only_missing,
        "analysis_required_fields": list(PROFILE_ANALYSIS_REQUIRED_FIELDS),
        "analysis_optional_fields": list(PROFILE_ANALYSIS_OPTIONAL_FIELDS),
        "missing_field_labels": _profile_field_labels(missing_fields),
        "updated_field_labels": _profile_field_labels(updated_fields),
        "preserved_field_labels": _profile_field_labels(preserved_fields),
        "display_only_missing_field_labels": _profile_field_labels(display_only_missing),
        "analysis_required_field_labels": _profile_field_labels(PROFILE_ANALYSIS_REQUIRED_FIELDS),
        "analysis_optional_field_labels": _profile_field_labels(PROFILE_ANALYSIS_OPTIONAL_FIELDS),
        "supports_remote_activity_sync": supports_remote,
        "activity_sync_hint": (
            "可按日期范围直接同步 Garmin 活动 FIT 文件。"
            if supports_remote else
            "COROS 暂不支持远程活动同步；请使用本地 FIT、ZIP 或目录监听导入活动。"
        ),
    }


def merge_profile_with_existing(incoming: dict[str, Any], existing: dict[str, Any] | None) -> dict[str, Any]:
    """Merge sync payload into the single runtime profile without brand namespaces."""
    merged = dict(incoming or {})
    existing = existing or {}
    for key in PROFILE_CANONICAL_FIELDS:
        if _is_meaningful_profile_value(merged.get(key)):
            continue
        old_value = existing.get(key)
        if _is_meaningful_profile_value(old_value):
            merged[key] = old_value
    return merged


def _profile_data_quality(profile_data: dict[str, Any]) -> tuple[str, list[str]]:
    analysis_fields = ["resting_hr", "max_hr", "weight", "vo2max", "lactate_threshold_hr"]
    missing = [field for field in analysis_fields if profile_data.get(field) is None]
    has_rest_and_max = profile_data.get("resting_hr") is not None and profile_data.get("max_hr") is not None
    optional_present = sum(1 for field in ("weight", "vo2max", "lactate_threshold_hr") if profile_data.get(field) is not None)
    if has_rest_and_max and optional_present >= 2:
        return "complete_for_analysis", missing
    if any(profile_data.get(field) is not None for field in analysis_fields):
        return "partial_for_analysis", missing
    display_fields = ("name", "gender", "age", "height_cm")
    if any(profile_data.get(field) is not None for field in display_fields):
        return "display_only", missing
    return "invalid", missing


def _insert_profile_snapshot(platform: str, trigger_type: str, raw_payload: Any, profile_data: dict[str, Any]) -> None:
    quality, missing = _profile_data_quality(profile_data)
    synced_at = datetime.now().isoformat()
    conn = _conn()
    try:
        conn.execute(
            """
            INSERT INTO user_profile_snapshots (
                source_platform, trigger_type, status, synced_at, sync_date,
                raw_payload_json, normalized_json, name, gender, age, weight,
                resting_hr, max_hr, hrv_baseline, vo2max, avg_sleep_hours,
                data_quality, missing_fields
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                platform,
                trigger_type,
                "success",
                synced_at,
                synced_at[:10],
                json.dumps(raw_payload, ensure_ascii=False, default=str),
                json.dumps(profile_data, ensure_ascii=False, default=str),
                profile_data.get("name"),
                profile_data.get("gender"),
                profile_data.get("age"),
                profile_data.get("weight"),
                profile_data.get("resting_hr"),
                profile_data.get("max_hr"),
                profile_data.get("hrv_baseline"),
                profile_data.get("vo2max"),
                profile_data.get("avg_sleep_hours"),
                quality,
                json.dumps(missing, ensure_ascii=False),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _extract_json_substring(text: str) -> str:
    left = text.find("[")
    right = text.rfind("]")
    if left != -1 and right != -1 and right > left:
        return text[left:right + 1]
    left = text.find("{")
    right = text.rfind("}")
    if left != -1 and right != -1 and right > left:
        return text[left:right + 1]
    return text


def _configured_garmin_region() -> str:
    cfg = llm_backend.load_llm_config()
    return str(cfg.get("garmin_region") or "").strip()


def _configured_coros_region() -> str:
    cfg = llm_backend.load_llm_config()
    return str(cfg.get("coros_region") or "").strip()


def _profile_metric_array_to_map(parsed_json: Any) -> dict[str, Any]:
    data_map: dict[str, Any] = {}
    if not isinstance(parsed_json, list):
        return data_map
    for item in parsed_json:
        if not isinstance(item, dict):
            continue
        metric = item.get("metric")
        if metric is None:
            metric = item.get("name")
        if metric is None or "value" not in item:
            continue
        data_map[str(metric)] = item.get("value")
    return data_map


def _profile_data_from_metric_map(data_map: dict[str, Any]) -> dict[str, Any]:
    ftp = _validate_int(_first_present(data_map, "ftp_watts", "ftp"))
    synced_max_hr = (
        _validate_int(_first_present(data_map, "max_hr", "max_heart_rate", "maximum_heart_rate"))
    )
    return {
        "name": str(_first_present(data_map, "username", "name", "nickname")) if _first_present(data_map, "username", "name", "nickname") is not None else None,
        "gender": str(_first_present(data_map, "gender")) if _first_present(data_map, "gender") is not None else None,
        "age": _validate_int(_first_present(data_map, "age")),
        "weight": _validate_number(_first_present(data_map, "weight_kg", "weight")),
        "resting_hr": _validate_int(_first_present(data_map, "resting_heart_rate", "resting_hr")),
        "recent_resting_hr": _validate_int(_first_present(data_map, "recent_resting_hr", "resting_hr_7d_avg", "resting_heart_rate", "resting_hr")),
        "resting_hr_7d_avg": _validate_int(_first_present(data_map, "resting_hr_7d_avg", "recent_resting_hr", "resting_heart_rate", "resting_hr")),
        "max_hr": synced_max_hr,
        "hrv_baseline": _validate_number(_first_present(data_map, "hrv", "hrv_baseline")),
        "recent_hrv": _validate_number(_first_present(data_map, "recent_hrv", "hrv_7d_avg", "hrv", "hrv_baseline")),
        "hrv_7d_avg": _validate_number(_first_present(data_map, "hrv_7d_avg", "recent_hrv", "hrv", "hrv_baseline")),
        "vo2max": _validate_number(_first_present(data_map, "vo2_max", "vo2max")),
        "avg_bedtime": str(_first_present(data_map, "avg_bedtime")).strip() if _first_present(data_map, "avg_bedtime") is not None else None,
        "avg_sleep_hours": _validate_number(_first_present(data_map, "avg_sleep_hours")),
        "bmi": _validate_number(_first_present(data_map, "bmi")),
        "body_fat_pct": _validate_number(_first_present(data_map, "body_fat_percent", "body_fat_pct")),
        "body_water_pct": _validate_number(_first_present(data_map, "body_water_percent", "body_water_pct")),
        "bone_mass": _validate_number(_first_present(data_map, "bone_mass_kg", "bone_mass")),
        "muscle_mass": _validate_number(_first_present(data_map, "muscle_mass_kg", "muscle_mass")),
        "longest_hike_km": _validate_number(_first_present(data_map, "longest_hike_km")),
        "height_cm": _validate_number(_first_present(data_map, "height_cm")),
        "pb_5km": _merge_pb_predict(_first_present(data_map, "5km_pb", "pb_5km"), _first_present(data_map, "race_predict_5k")),
        "pb_10km": _merge_pb_predict(_first_present(data_map, "10km_pb", "pb_10km"), _first_present(data_map, "race_predict_10k")),
        "pb_half_marathon": _merge_pb_predict(_first_present(data_map, "half_marathon_pb", "pb_half_marathon"), _first_present(data_map, "race_predict_half")),
        "pb_full_marathon": _merge_pb_predict(_first_present(data_map, "full_marathon_pb", "pb_full_marathon"), _first_present(data_map, "race_predict_full")),
        "lactate_threshold_hr": _validate_int(_first_present(data_map, "lactate_threshold_hr")),
        "ftp": ftp,
        "ftp_watts": ftp,
        "lactate_threshold_pace": _validate_time_format(_first_present(data_map, "lactate_threshold_pace")),
        "longest_run_km": _validate_number(_first_present(data_map, "longest_run_km")),
        "pb_1km": _validate_time_format(_first_present(data_map, "1km_pb", "pb_1km")),
        "longest_ride_time": _validate_time_format(_first_present(data_map, "longest_ride_time")),
        "cycling_40km_time": _validate_time_format(_first_present(data_map, "cycling_40km_time")),
        "cycling_80km_time": _validate_time_format(_first_present(data_map, "cycling_80km_time")),
        "longest_cycle_km": _validate_number(_first_present(data_map, "longest_cycle_km")),
        "swimming_100m_pb": _validate_time_format(_first_present(data_map, "swimming_100m_pb")),
        "longest_swim_distance_m": _validate_number(_first_present(data_map, "longest_swim_distance_m")),
        "total_run_km": _validate_number(_first_present(data_map, "total_run_km")),
        "total_hike_km": _validate_number(_first_present(data_map, "total_hike_km")),
        "total_cycle_km": _validate_number(_first_present(data_map, "total_cycle_km")),
        "total_swim_km": _validate_number(_first_present(data_map, "total_swim_km")),
    }


def _provider_failure_payload(platform: str, exc: Exception, message: str | None = None) -> dict[str, Any]:
    provider = str(platform or "").strip().lower()
    if provider == "coros":
        normalized = coros_sync.normalize_coros_error(
            exc,
            {"operation": "fetch_mcp_persona", "region": _configured_coros_region() or ""},
        )
        code = str(normalized.get("provider_error_code") or "coros_profile_sync_failed")
        return {
            "ok": False,
            "error": str(normalized.get("message") or message or "COROS 画像同步失败。"),
            "provider": provider,
            "provider_error_code": code,
            "action_hint": str(normalized.get("action_hint") or coros_sync.COROS_ACTION_HINTS.get(code, coros_sync.COROS_ACTION_HINTS["unknown"])),
            "diagnostics": normalized.get("diagnostics") or {"provider": "coros"},
            "profile_sync_summary": build_profile_status_summary(provider),
        }
    code = str(getattr(exc, "code", "") or f"{provider}_sync_error").strip()
    text = str(message if message is not None else exc)
    action_hints = {
        "coros_auth_required": "请到配置页选择正确 COROS 区域，点击检查状态并完成 MCP 授权。",
        "coros_node_missing": "未检测到 COROS 同步所需 Node.js，请确认安装包完整或回配置页重新检查账号连接。",
        "coros_skill_not_found": "未找到 coros-stats skill 脚本，请确认应用内 COROS skill 安装完整。",
        "coros_keepalive_invalid": "COROS keepalive 配置不可用，请回配置页检查账号连接状态并重新连接。",
        "coros_script_failed": "请确认 COROS 授权、Node.js 与 coros-stats skill 可用后重试。",
        "coros_json_parse_error": "COROS 画像脚本返回格式异常，请更新 coros-stats skill 后重试。",
        "invalid_coros_region": "请检查 COROS 区域配置，仅支持 cn / us / eu。",
        "garmin_sync_error": "Garmin 数据同步失败，请检查 Garmin 授权和本地 skill 状态。",
    }
    return {
        "ok": False,
        "error": text,
        "provider": provider,
        "provider_error_code": code,
        "action_hint": action_hints.get(code, f"{provider.upper()} 同步失败，请检查配置页授权状态后重试。"),
        "profile_sync_summary": build_profile_status_summary(provider),
    }


def fetch_mcp_persona(platform: str, trigger_type: str = "manual") -> dict[str, Any]:
    """
    获取用户运动画像：通过 MCP 工具拉取生理数据 + 徒步历史。
    """
    if platform not in ("garmin", "coros"):
        return {"ok": False, "error": "不支持的平台，仅支持 garmin / coros"}

    state = read_sync_state()
    if state.get("active_job_id"):
        last_attempt_at = state.get("last_attempt_at")
        stale = False
        if not last_attempt_at:
            stale = True
        else:
            try:
                last_at = datetime.fromisoformat(str(last_attempt_at).replace("Z", "+00:00"))
                age = datetime.now(last_at.tzinfo) - last_at
                if age > timedelta(minutes=5):
                    stale = True
            except (ValueError, TypeError):
                stale = True
        if stale:
            state["active_job_id"] = None
            write_sync_state(state)
        else:
            return {"ok": False, "error": "正在同步中"}

    job_id = os.urandom(8).hex()
    state.update({
        "active_job_id": job_id,
        "last_attempt_at": datetime.now().isoformat(),
        "last_attempt_trigger": trigger_type,
        "last_attempt_status": "syncing",
        "last_error": None,
        "connection_status": "connected" if platform == "garmin" else state.get("connection_status", "unknown"),
    })
    write_sync_state(state)

    existing_profile = get_profile()
    existing_profile_data = existing_profile.to_dict() if existing_profile else {}

    try:
        if platform == "garmin":
            parsed_json = garmin_sync.sync_profile_json(region=_configured_garmin_region() or None)
        else:
            parsed_json = coros_sync.sync_profile_json(region=_configured_coros_region() or None)

        if not isinstance(parsed_json, list):
            label = "Garmin" if platform == "garmin" else "COROS"
            error = f"{label} 数据同步失败，返回的不是 JSON 数组。"
            mark_profile_sync_failed(error)
            return {"ok": False, "error": error}

        profile_data = _profile_data_from_metric_map(_profile_metric_array_to_map(parsed_json))

        incoming_profile_data = dict(profile_data)
        valid_fields = [
            key for key, value in incoming_profile_data.items()
            if _is_meaningful_profile_value(value)
        ]
        if not valid_fields:
            label = "Garmin" if platform == "garmin" else "COROS"
            error = f"{label} 画像同步未解析到任何有效字段，请检查账号授权状态、网络连接或 provider 返回格式。"
            logger.warning(
                "%s profile sync returned no meaningful fields trigger=%s raw_count=%s",
                platform,
                trigger_type,
                len(parsed_json) if isinstance(parsed_json, list) else "n/a",
            )
            mark_profile_sync_failed(error)
            exc = (
                garmin_sync.GarminJsonParseError(error)
                if platform == "garmin" else
                coros_sync.CorosJsonParseError(error)
            )
            return _provider_failure_payload(platform, exc, error)
        profile_data = merge_profile_with_existing(incoming_profile_data, existing_profile_data)
        field_summary = build_profile_sync_field_summary(
            platform,
            incoming_profile_data,
            profile_data,
            existing_profile_data,
        )
        write_profile_sync_field_summary(field_summary)
        upsert_profile(profile_data)
        _insert_profile_snapshot(platform, trigger_type, parsed_json, profile_data)
        mark_sync_done()
        return {"ok": True, "persona": profile_data, "profile_sync_summary": field_summary}

    except json.JSONDecodeError as e:
        error = f"JSON 解析失败: {e}\n原始返回: {text[:500] if 'text' in dir() else 'N/A'}"
        mark_profile_sync_failed(error)
        return {"ok": False, "error": error}
    except coros_sync.CorosAuthRequiredError as e:
        normalized = coros_sync.normalize_coros_error(
            e,
            {"operation": "fetch_mcp_persona", "region": _configured_coros_region() or ""},
        )
        error = str(normalized.get("message") or "COROS 授权不可用或已失效。")
        mark_profile_sync_auth_required(error)
        return _provider_failure_payload(platform, e, error)
    except coros_sync.CorosSyncError as e:
        normalized = coros_sync.normalize_coros_error(
            e,
            {"operation": "fetch_mcp_persona", "region": _configured_coros_region() or ""},
        )
        error = str(normalized.get("message") or "COROS 数据同步失败。")
        if _profile_sync_blocked_code(str(getattr(e, "code", ""))):
            mark_profile_sync_blocked(error)
        else:
            mark_profile_sync_failed(error)
        return _provider_failure_payload(platform, e, error)
    except garmin_sync.GarminAuthRequiredError as e:
        error = "Garmin 授权不可用或已失效，请到配置页完成授权。"
        detail = str(e).strip()
        if detail and detail != error:
            error = f"{error} {detail}"
        mark_profile_sync_auth_required(error)
        return _provider_failure_payload(platform, e, error)
    except garmin_sync.GarminSyncError as e:
        error = f"Garmin 数据同步失败: {e}"
        if _profile_sync_blocked_code(str(getattr(e, "code", ""))):
            mark_profile_sync_blocked(error)
        else:
            mark_profile_sync_failed(error)
        return _provider_failure_payload(platform, e, error)
    except Exception as e:
        if platform == "coros":
            normalized = coros_sync.normalize_coros_error(
                e,
                {"operation": "fetch_mcp_persona", "region": _configured_coros_region() or ""},
            )
            error = str(normalized.get("message") or "COROS 画像同步失败。")
            mark_profile_sync_failed(error)
            return _provider_failure_payload(platform, e, error)
        error = f"MCP 同步失败: {e}"
        mark_profile_sync_failed(error)
        return {"ok": False, "error": error}
