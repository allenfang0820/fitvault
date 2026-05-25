"""
个人运动画像后端：SQLite 存储 + HRR 心率区间 + 有氧解耦 + MCP 联调同步。
"""

from __future__ import annotations

import json
import math
import os
import requests
import shutil
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import sys
if getattr(sys, "frozen", False):
    _BASE = Path.home() / ".fitvault"
else:
    _BASE = Path.home() / ".fitvault"

DB_PATH = _BASE / "user_profile.db"
TRACKS_DIR = _BASE / "workspace" / "tracks"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
SQLITE_POOL_SIZE = 6
SQLITE_POOL_ACQUIRE_TIMEOUT_SEC = 10.0
SQLITE_BUSY_TIMEOUT_MS = 15000
SQLITE_CONNECT_TIMEOUT_SEC = SQLITE_BUSY_TIMEOUT_MS / 1000.0
SQLITE_LOCK_RETRY_ATTEMPTS = 6
SQLITE_LOCK_RETRY_BASE_DELAY_SEC = 0.25
GEOCODE_REQUEST_TIMEOUT_SEC = 8
GEOCODE_LANG = "zh-CN"
GEOCODE_USER_AGENT = "FitVault/1.0"

_DB_CONN_SEMAPHORE = threading.BoundedSemaphore(SQLITE_POOL_SIZE)

SYNC_STATE_DIR = os.path.expanduser("~/.trackapp")
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
    from datetime import datetime
    now = datetime.now()
    write_sync_state({
        "last_sync_date": now.strftime("%Y-%m-%d"),
        "last_sync_time": now.isoformat(),
        "synced_today": True,
    })


def is_sync_needed_today() -> bool:
    if _TEST_BYPASS_DAILY_SYNC_LIMIT:
        return True
    from datetime import date
    state = read_sync_state()
    today = date.today().isoformat()
    return not (state.get("synced_today") and state.get("last_sync_date") == today)


# 内部测试开关：绕过单日同步次数限制，仅限开发调试使用
_TEST_BYPASS_DAILY_SYNC_LIMIT = False


def get_test_bypass_daily_sync_limit() -> bool:
    return _TEST_BYPASS_DAILY_SYNC_LIMIT


def set_test_bypass_daily_sync_limit(enabled: bool) -> None:
    global _TEST_BYPASS_DAILY_SYNC_LIMIT
    _TEST_BYPASS_DAILY_SYNC_LIMIT = bool(enabled)


# ─── 用户画像本地缓存文件（读/写/校验） ────────────────────────────────
PROFILE_CACHE_MAX_AGE_SEC = 7 * 24 * 3600  # 7 天


def write_local_profile(data: dict) -> None:
    """将用户画像数据写入本地缓存文件，含时间戳。"""
    _ensure_sync_state_dir()
    payload = {
        "cached_at": datetime.utcnow().isoformat() + "Z",
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
        age_sec = (datetime.utcnow().replace(tzinfo=None) - cached_ts.replace(tzinfo=None)).total_seconds()
        if age_sec > PROFILE_CACHE_MAX_AGE_SEC:
            return None
    except (ValueError, TypeError):
        return None
    data = payload.get("data") or {}
    if not _is_profile_data_valid(data):
        return None
    return data
_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY_FOR: str | None = None
_REGION_CACHE_LOCK = threading.Lock()
_REGION_CACHE: dict[tuple[float, float], str] = {}


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
            max_hr      INTEGER,
            hrv_baseline REAL,
            vo2max      REAL,
            avg_sleep_hours REAL,
            longest_hike_km REAL,
            updated_at  TEXT DEFAULT (datetime('now'))
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
            file_mtime     REAL,
            file_size      INTEGER,
            deleted_at     TEXT,
            updated_at     TEXT DEFAULT (datetime('now'))
        )
    """)

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
        ("weather_json", "TEXT"),
        ("file_mtime", "REAL"),
        ("file_size", "INTEGER"),
        ("deleted_at", "TEXT"),
    ]:
        try:
            conn.execute(f"ALTER TABLE activities ADD COLUMN {col} {dtype}")
        except Exception:
            pass
            
    for col, dtype in [
        ("avg_sleep_hours", "REAL"),
        ("longest_hike_km", "REAL"),
        ("height_cm", "REAL"),
        ("pb_5km", "TEXT"),
        ("pb_10km", "TEXT"),
        ("pb_half_marathon", "TEXT"),
        ("pb_full_marathon", "TEXT"),
        ("lactate_threshold_hr", "INTEGER"),
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
    ]:
        try:
            conn.execute(f"ALTER TABLE user_profile ADD COLUMN {col} {dtype}")
        except Exception:
            pass
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
    height_cm: float | None = None
    pb_5km: str | None = None
    pb_10km: str | None = None
    pb_half_marathon: str | None = None
    pb_full_marathon: str | None = None
    lactate_threshold_hr: int | None = None
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
            "max_hr": self.max_hr,
            "hrv_baseline": self.hrv_baseline,
            "hrv": self.hrv_baseline,
            "vo2max": self.vo2max,
            "vo2_max": self.vo2max,
            "avg_sleep_hours": self.avg_sleep_hours,
            "longest_hike_km": self.longest_hike_km,
            "height_cm": self.height_cm,
            "pb_5km": self.pb_5km,
            "pb_10km": self.pb_10km,
            "pb_half_marathon": self.pb_half_marathon,
            "pb_full_marathon": self.pb_full_marathon,
            "lactate_threshold_hr": self.lactate_threshold_hr,
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
            "last_updated": self.last_updated,
        }


def get_profile() -> UserProfile:
    conn = _conn()
    row = conn.execute("SELECT * FROM user_profile ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    if row is None:
        cached = read_local_profile()
        if cached:
            upsert_profile(cached)
            conn = _conn()
            row = conn.execute("SELECT * FROM user_profile ORDER BY id DESC LIMIT 1").fetchone()
            conn.close()
    if row is None:
        return UserProfile(None, None, None, None, None, None, None, None, None, None)
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
        height_cm=row["height_cm"] if "height_cm" in row.keys() else None,
        pb_5km=row["pb_5km"] if "pb_5km" in row.keys() else None,
        pb_10km=row["pb_10km"] if "pb_10km" in row.keys() else None,
        pb_half_marathon=row["pb_half_marathon"] if "pb_half_marathon" in row.keys() else None,
        pb_full_marathon=row["pb_full_marathon"] if "pb_full_marathon" in row.keys() else None,
        lactate_threshold_hr=row["lactate_threshold_hr"] if "lactate_threshold_hr" in row.keys() else None,
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
        last_updated=row["updated_at"] if "updated_at" in row.keys() else None,
    )


def upsert_profile(data: dict[str, Any]) -> UserProfile:
    conn = _conn()
    conn.execute("DELETE FROM user_profile")
    conn.execute(
        """
        INSERT INTO user_profile
            (name, gender, age, weight, resting_hr, max_hr, hrv_baseline, vo2max,
             avg_sleep_hours, longest_hike_km, height_cm, pb_5km, pb_10km, pb_half_marathon,
             pb_full_marathon, lactate_threshold_hr, ftp_watts,
             lactate_threshold_pace, pb_1km, longest_run_km,
             longest_ride_time, cycling_40km_time, cycling_80km_time, longest_cycle_km,
             longest_swim_distance_m, swimming_100m_pb)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data.get("name"),
            data.get("gender"),
            data.get("age"),
            data.get("weight"),
            data.get("resting_hr"),
            data.get("max_hr"),
            data.get("hrv_baseline"),
            data.get("vo2max"),
            data.get("avg_sleep_hours"),
            data.get("longest_hike_km"),
            data.get("height_cm"),
            data.get("pb_5km"),
            data.get("pb_10km"),
            data.get("pb_half_marathon"),
            data.get("pb_full_marathon"),
            data.get("lactate_threshold_hr"),
            data.get("ftp_watts"),
            data.get("lactate_threshold_pace"),
            data.get("pb_1km"),
            data.get("longest_run_km"),
            data.get("longest_ride_time"),
            data.get("cycling_40km_time"),
            data.get("cycling_80km_time"),
            data.get("longest_cycle_km"),
            data.get("longest_swim_distance_m"),
            data.get("swimming_100m_pb"),
        ),
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
        avg_sleep_hours=data.get("avg_sleep_hours"),
        longest_hike_km=data.get("longest_hike_km"),
        height_cm=data.get("height_cm"),
        pb_5km=data.get("pb_5km"),
        pb_10km=data.get("pb_10km"),
        pb_half_marathon=data.get("pb_half_marathon"),
        pb_full_marathon=data.get("pb_full_marathon"),
        lactate_threshold_hr=data.get("lactate_threshold_hr"),
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
        last_updated=last_updated["updated_at"] if last_updated else None,
    )


def save_activity(data: dict[str, Any]) -> int:
    def _write() -> int:
        conn = _conn()
        try:
            cur = conn.execute(
                """
                INSERT INTO activities
                    (filename, title, title_source, sport_type, sub_sport_type, dist_km, duration_sec, gain_m, max_alt_m,
                     avg_hr, max_hr, avg_cadence, hr_decoupling, tss, points_json, file_path, start_time, start_time_utc,
                     start_lat, start_lon, region, weather_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    data.get("weather_json"),
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
    return [dict(r) for r in rows]


def get_activity_list_filtered(offset: int, limit: int, sport_filter: str) -> tuple[list[dict[str, Any]], int]:
    display_sql = (
        "CASE "
        "WHEN COALESCE(NULLIF(sub_sport_type, ''), 'unknown') IN ('trail_running', 'road_cycling', 'mountain_biking') THEN sub_sport_type "
        "WHEN COALESCE(NULLIF(sport_type, ''), 'unknown') IN ('trail_running', 'road_cycling', 'mountain_biking') THEN sport_type "
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
        "weather_json, "
        "source_type, "
        "is_mock, "
        "updated_at, "
        "CASE WHEN COALESCE(track_json, points_json, '') != '' THEN 1 ELSE 0 END AS has_track"
    )

    conn = _conn()
    try:
        count_row = conn.execute(
            f"SELECT COUNT(*) FROM activities {where_sql}",
            tuple(params),
        ).fetchone()
        total_count = int(count_row[0]) if count_row else 0

        rows = conn.execute(
            f"""
            SELECT {select_fields}
            FROM activities
            {where_sql}
            ORDER BY COALESCE(start_time, updated_at) DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            tuple(params + [limit, offset]),
        ).fetchall()
    finally:
        conn.close()

    return [dict(r) for r in rows], total_count


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
            SELECT id, sport_type, sub_sport_type
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
    title = str(data.get("title") or data.get("fit_title") or filename).strip()
    title_source = str(data.get("title_source") or ("fit_title" if data.get("title") or data.get("fit_title") else "filename")).strip()
    avg_hr = data.get("avg_hr")
    max_hr = data.get("max_hr")
    start_lat, start_lon = _extract_start_coordinates(points)
    region = resolve_activity_region(
        data.get("start_lat", start_lat),
        data.get("start_lon", start_lon),
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
        "start_lat": start_lat,
        "start_lon": start_lon,
        "region": region,
        "weather_json": data.get("weather_json"),
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


def resolve_activity_region(lat: Any, lon: Any) -> str:
    try:
        lat_val = round(float(lat), 4)
        lon_val = round(float(lon), 4)
    except (TypeError, ValueError):
        return ""

    cache_key = (lat_val, lon_val)
    with _REGION_CACHE_LOCK:
        cached = _REGION_CACHE.get(cache_key)
    if cached is not None:
        return cached

    region = ""
    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={
                "format": "json",
                "lat": lat_val,
                "lon": lon_val,
                "zoom": 10,
                "accept-language": GEOCODE_LANG,
            },
            headers={"User-Agent": GEOCODE_USER_AGENT},
            timeout=GEOCODE_REQUEST_TIMEOUT_SEC,
        )
        response.raise_for_status()
        payload = response.json() if callable(getattr(response, "json", None)) else {}
        address = payload.get("address") if isinstance(payload, dict) else {}
        if isinstance(address, dict):
            region = str(
                address.get("city")
                or address.get("town")
                or address.get("county")
                or address.get("state")
                or address.get("province")
                or payload.get("name")
                or ""
            ).strip()
    except Exception:
        region = ""

    with _REGION_CACHE_LOCK:
        _REGION_CACHE[cache_key] = region
    return region


def ingest_activity_file(
    src_path: str,
    duplicate_action: str = "",
    new_filename: str | None = None,
) -> dict[str, Any]:
    import track_backend
    import logging

    logger = logging.getLogger("duplicate_check")
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


def _summarize_track_points(points: list[dict[str, Any]], track_backend_module: Any) -> tuple[float, int, int]:
    dist_m = 0.0
    gain_m = 0.0
    for idx in range(1, len(points)):
        p0, p1 = points[idx - 1], points[idx]
        if p0.get("lat") is None or p0.get("lon") is None or p1.get("lat") is None or p1.get("lon") is None:
            continue
        dist_m += track_backend_module.haversine_m(p0["lat"], p0["lon"], p1["lat"], p1["lon"])
        if p0.get("alt") is not None and p1.get("alt") is not None:
            alt_gain = float(p1.get("alt") or 0.0) - float(p0.get("alt") or 0.0)
            if alt_gain > 0:
                gain_m += alt_gain

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
) -> dict[str, Any]:
    """
    检查是否有重复的活动记录。
    判断标准：
    1. 时间窗口粗筛：开始时间相差 <= 5分钟，且时长差异 <= 10%。
    2. 轨迹点空间匹配：如果提供了 points_json，计算经纬度重合度（距离<50米），阈值 90%。
    3. 核心运动数据匹配：距离差异 < 10%。
    """
    import track_backend
    import logging
    import json
    from datetime import datetime
    import os

    # 设置独立的查重日志记录
    logger = logging.getLogger("duplicate_check")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        fh = logging.FileHandler("duplicate_check.log", encoding="utf-8")
        fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(fh)

    conn = _conn()
    rows = conn.execute(
        "SELECT id, filename, file_path, start_time, start_time_utc, dist_km, duration_sec, points_json, updated_at FROM activities"
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

    logger.info(f"--- 开始查重 --- 目标: start={start_time}, utc={start_time_utc}, dist={dist_km}km, dur={duration_sec}s, points={len(points_json) if points_json else 0}")

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

        logger.info(f"[{r_dict['filename']}] 查重得分: {score} (时间差: {time_diff_sec if time_diff_sec is not None else 'N/A'}s, 里程差: {dist_diff_ratio*100:.1f}%, 时长差: {dur_diff_ratio*100 if duration_sec>0 and db_dur>0 else 'N/A'}%, 重合度: {overlap_ratio*100:.1f}%)")

        if score > max_score:
            max_score = score
            best_match = r_dict

    # 设置阈值 80 为重复
    if max_score >= 80.0 and best_match:
        logger.info(f"--- 查重结果: 发现重复 --- 匹配记录: {best_match['filename']}, 分数: {max_score}")
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
    return None


def fetch_mcp_persona(platform: str) -> dict[str, Any]:
    """
    获取用户运动画像：通过 MCP 工具拉取生理数据 + 徒步历史。
    """
    if platform not in ("garmin", "coros"):
        return {"ok": False, "error": "不支持的平台，仅支持 garmin / coros"}

    import llm_backend

    cfg = llm_backend.load_llm_config()
    url = (cfg.get("url") or "").strip() or "http://localhost:3000/v1/chat/completions"
    model = (cfg.get("model") or "openclaw").strip()
    api_key = str(cfg.get("api_key") or "")

    if platform == "coros":
        step1_prompt = (
            "你是一个数据分析助手，严格按顺序调用以下工具来构建用户完整画像。\n\n"
            "【第一步】获取最长徒步距离：\n"
            "调用 querySportRecords 工具，参数固定为：\n"
            '{ "startDate": "20100101", "sportTypeCodes": [104, 105], "limit": 20 }\n'
            "取返回记录中 distance 最大值（单位km，保留两位小数）作为 longest_hike_km。若无记录设为 null。\n\n"
            "【第二步】获取体能评估：\n"
            "调用 queryFitnessAssessmentOverview 工具，取 vo2max 字段。若无数据则设为 null。\n\n"
            "【第三步】获取基础生理数据：\n"
            "- 调用 queryUserInfo，取 nickname 作为 name、age 作为 age、gender 作为 gender、weight 作为 weight（kg）\n"
            "- 调用 querySleepData，取最近一次记录的 sleepMainDuration（小时），再取多次平均值作为 avg_sleep_hours\n\n"
            "【第四步】获取跑步记录：\n"
            "调用 querySportRecords 工具，参数为：\n"
            '{ "startDate": "20100101", "sportTypeCodes": [101, 102, 103], "limit": 20 }\n'
            "取返回记录中 distance 最大值（单位km，保留两位小数）作为 longest_run_km。若无记录设为 null。\n"
            "此外，若返回记录中包含跑步时长信息，取最大值作为 longest_running_duration（格式 mm:ss 或 h:mm:ss）。若无则设为 null。\n\n"
            "【第五步】获取骑行记录：\n"
            "调用 querySportRecords 工具，参数为：\n"
            '{ "startDate": "20100101", "sportTypeCodes": [201, 202], "limit": 20 }\n'
            "取返回记录中 distance 最大值（单位km，保留两位小数）作为 longest_cycle_km。若无记录设为 null。\n"
            "取返回记录中时长最大值（格式 h:mm:ss）作为 longest_ride_time。若无则设为 null。\n\n"
            "【第六步】获取游泳记录：\n"
            "调用 querySportRecords 工具，参数为：\n"
            '{ "startDate": "20100101", "sportTypeCodes": [301, 302], "limit": 20 }\n'
            "取返回记录中 distance 最大值（单位m）作为 longest_swim_distance_m。若无记录设为 null。\n"
            "若存在 100m 游泳记录，取其用时（格式 mm:ss）作为 swimming_100m_pb。若无则设为 null。\n\n"
            "【输出格式】输出一个完整 JSON，绝对不输出任何其他文字：\n"
            "{\n"
            '  "longest_hike_km": 浮点数或null,\n'
            '  "name": "字符串或null",\n'
            '  "age": 整数或null,\n'
            '  "gender": "字符串或null",\n'
            '  "weight": 浮点数或null,\n'
            '  "vo2max": 浮点数或null,\n'
            '  "avg_sleep_hours": 浮点数或null,\n'
            '  "lactate_threshold_pace": "字符串或null",\n'
            '  "longest_run_km": 浮点数或null,\n'
            '  "pb_1km": "字符串或null",\n'
            '  "longest_ride_time": "字符串或null",\n'
            '  "longest_cycle_km": 浮点数或null,\n'
            '  "swimming_100m_pb": "字符串或null",\n'
            '  "longest_swim_distance_m": 整数或null\n'
            "}"
        )
        messages = [
            {"role": "system", "content": step1_prompt},
            {"role": "user", "content": "请立即执行上述两步数据提取和计算任务。"},
        ]
    else:
        messages = [
            {"role": "user", "content": "同步用户画像"}
        ]

    try:
        text = llm_backend.chat_completions(
            url=url,
            api_key=api_key,
            model=model,
            messages=messages,
            session_id="mcp_persona_" + platform,
            timeout=300,
        )

        json_str = text.strip()
        if json_str.startswith("```"):
            lines = json_str.split("\n")
            json_str = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

        parsed_json = json.loads(json_str)

        if platform == "garmin":
            if not isinstance(parsed_json, list):
                return {"ok": False, "error": "Garmin 数据同步失败，返回的不是 JSON 数组。"}
            
            # Map array to dict
            data_map = {}
            for item in parsed_json:
                if isinstance(item, dict) and "metric" in item and "value" in item:
                    data_map[item["metric"]] = item["value"]
            
            profile_data = {
                "name": str(data_map.get("username")) if data_map.get("username") is not None else None,
                "gender": str(data_map.get("gender")) if data_map.get("gender") is not None else None,
                "age": _validate_int(data_map.get("age")),
                "weight": _validate_number(data_map.get("weight_kg")),
                "resting_hr": _validate_int(data_map.get("resting_heart_rate")),
                "max_hr": None,
                "hrv_baseline": _validate_number(data_map.get("hrv")),
                "vo2max": _validate_number(data_map.get("vo2_max")),
                "avg_sleep_hours": _validate_number(data_map.get("avg_sleep_hours")),
                "longest_hike_km": _validate_number(data_map.get("longest_hike_km")),
                "height_cm": _validate_number(data_map.get("height_cm")),
                "pb_5km": _validate_time_format(data_map.get("5km_pb")),
                "pb_10km": _validate_time_format(data_map.get("10km_pb")),
                "pb_half_marathon": _validate_time_format(data_map.get("half_marathon_pb")),
                "pb_full_marathon": _validate_time_format(data_map.get("full_marathon_pb")),
                "lactate_threshold_hr": _validate_int(data_map.get("lactate_threshold_hr")),
                "ftp_watts": _validate_int(data_map.get("ftp_watts")),
                "lactate_threshold_pace": _validate_time_format(data_map.get("lactate_threshold_pace")),
                "longest_run_km": _validate_number(data_map.get("longest_run_km")),
                "pb_1km": _validate_time_format(data_map.get("1km_pb")),
                "longest_ride_time": _validate_time_format(data_map.get("longest_ride_time")),
                "longest_cycle_km": _validate_number(data_map.get("longest_cycle_km")),
                "swimming_100m_pb": _validate_time_format(data_map.get("swimming_100m_pb")),
                "longest_swim_distance_m": _validate_number(data_map.get("longest_swim_distance_m")),
            }
        else:
            persona = parsed_json
            profile_data = {
                "name": persona.get("name"),
                "gender": persona.get("gender"),
                "age": _validate_int(persona.get("age")),
                "weight": _validate_number(persona.get("weight")),
                "resting_hr": _validate_int(persona.get("resting_hr")),
                "max_hr": None,
                "hrv_baseline": _validate_number(persona.get("hrv_baseline")),
                "vo2max": _validate_number(persona.get("vo2max")),
                "avg_sleep_hours": _validate_number(persona.get("avg_sleep_hours")),
                "longest_hike_km": _validate_number(persona.get("longest_hike_km")),
                "height_cm": None,
                "pb_5km": None,
                "pb_10km": None,
                "pb_half_marathon": None,
                "pb_full_marathon": None,
                "lactate_threshold_hr": None,
                "ftp_watts": None,
                "lactate_threshold_pace": _validate_time_format(persona.get("lactate_threshold_pace")),
                "longest_run_km": _validate_number(persona.get("longest_run_km")),
                "pb_1km": _validate_time_format(persona.get("pb_1km")),
                "longest_ride_time": _validate_time_format(persona.get("longest_ride_time")),
                "longest_cycle_km": _validate_number(persona.get("longest_cycle_km")),
                "swimming_100m_pb": _validate_time_format(persona.get("swimming_100m_pb")),
                "longest_swim_distance_m": _validate_number(persona.get("longest_swim_distance_m")),
            }

        upsert_profile(profile_data)
        mark_sync_done()
        return {"ok": True, "persona": profile_data}

    except json.JSONDecodeError as e:
        return {"ok": False, "error": f"JSON 解析失败: {e}\n原始返回: {text[:500] if 'text' in dir() else 'N/A'}"}
    except Exception as e:
        return {"ok": False, "error": f"MCP 同步失败: {e}"}
