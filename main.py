#!/usr/bin/env python3
"""使用 pywebview 在桌面窗口中加载「脉图」单页 HTML。"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import sys
import threading
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import llm_backend  # noqa: F401 -- PyInstaller bundles LLM 模块
import track_backend  # noqa: F401 -- PyInstaller bundles track_backend
import profile_backend  # noqa: F401 -- PyInstaller bundles profile 模块
from fit_engine import FITCoreEngine
from garmin_fit_sdk import Decoder, Stream
from metrics_resolver import MetricsResolver

DEBUG_MODE = False
APP_VERSION = "v0.6.0"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)
if DEBUG_MODE:
    logger.setLevel(logging.DEBUG)
from utils.weather_api import fetch_historical_weather
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

HTML_FILENAME = "track.html"

# ─── Managed Workspace ───────────────────────────────────────────
CURRENT_SCHEMA_VERSION = 2
CURRENT_METRICS_VERSION = 3  # P1 核心资产：用于判定历史雷达算法是否需要强制清洗
WORKSPACE_ROOT = os.path.abspath(os.path.expanduser("~/.fitvault/workspace/"))
TRACKS_DIR = os.path.abspath(os.path.expanduser("~/.fitvault/workspace/tracks/"))
IMPORTS_DIR = os.path.abspath(os.path.expanduser("~/.fitvault/workspace/imports/"))

APP_CONFIG_PATH = os.path.expanduser("~/.trackapp_config.json")
DEFAULT_APP_CONFIG = {
    "workspace_track_path": TRACKS_DIR,
    "workspace_track_abs_path": TRACKS_DIR,
}
SPORT_HUB_PAGE_SIZES = [10, 20, 50]
APP_CONFIG_BACKUP_DIR = os.path.expanduser("~/.trackapp_config.backups")
APP_CONFIG_AUDIT_LOG = os.path.expanduser("~/.trackapp_config.audit.log")
SPORT_HUB_TYPE_ORDER = {
    "running": 1,
    "trail_running": 2,
    "cycling": 3,
    "road_cycling": 4,
    "mountain_biking": 5,
    "hiking": 6,
    "mountaineering": 7,
    "walking": 8,
    "swimming": 9,
    "stand_up_paddleboarding": 10,
    "driving": 11,
    "cardio": 12,
    "strength_training": 13,
    "yoga": 14,
    "pilates": 15,
    "hiit": 16,
    "breathing": 17,
    "flexibility_training": 18,
}

POWER_ELIGIBLE_TYPES: frozenset[str] = frozenset({
    "running", "trail_running", "treadmill_running",
    "cycling", "road_cycling", "mountain_biking",
})

OUTDOOR_LAND_GAIN_TYPES: frozenset[str] = frozenset({
    "running", "trail_running", "treadmill_running",
    "cycling", "road_cycling", "mountain_biking",
    "hiking", "mountaineering", "walking",
})

IRRELEVANT_LIST_METRICS: dict[str, frozenset[str]] = {
    "cardio": frozenset({"distance", "pace"}),
    "strength_training": frozenset({"distance", "pace"}),
    "yoga": frozenset({"distance", "pace"}),
    "pilates": frozenset({"distance", "pace"}),
    "hiit": frozenset({"distance", "pace"}),
    "breathing": frozenset({"distance", "pace"}),
    "flexibility_training": frozenset({"distance", "pace"}),
}

_ACTIVITY_SYNC_SCHEMA_LOCK = threading.Lock()
_ACTIVITY_SYNC_SCHEMA_READY_FOR: str | None = None
_APP_SHUTTING_DOWN = threading.Event()
FIT_WATCH_STABLE_SEC = 2.0
FIT_WATCH_POLL_INTERVAL_SEC = 1.5
ZIP_MAX_MEMBERS = 500
ZIP_MAX_MEMBER_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024
ZIP_COPY_CHUNK_BYTES = 1024 * 1024
ZIP_ALLOWED_SUFFIXES = frozenset({".fit"})


def app_base_dir() -> Path:
    """开发模式为脚本所在目录；PyInstaller 打包后为 _MEIPASS。"""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def html_file() -> Path:
    path = app_base_dir() / HTML_FILENAME
    if not path.is_file():
        raise FileNotFoundError(f"未找到页面文件: {path}")
    return path


def _default_application_config() -> dict:
    return dict(DEFAULT_APP_CONFIG)


def load_application_config() -> dict:
    config = _default_application_config()
    config_status = "loaded"
    try:
        with open(APP_CONFIG_PATH, "r", encoding="utf-8") as fh:
            loaded = json.load(fh)
        if not isinstance(loaded, dict):
            raise ValueError("配置文件根节点必须是对象")
        config.update(loaded)
    except FileNotFoundError:
        config_status = "missing"
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"[config] 读取配置失败，回退默认配置: {exc}")
        config_status = "recovered"

    config["workspace_track_path"] = TRACKS_DIR
    config["workspace_track_abs_path"] = TRACKS_DIR
    config["config_path"] = APP_CONFIG_PATH
    config["config_status"] = config_status
    return config


def persist_application_config(config: dict | None = None) -> dict:
    payload = _default_application_config()
    if isinstance(config, dict):
        payload.update(
            {
                key: value
                for key, value in config.items()
                if key
                not in {
                    "ok",
                    "error",
                    "workspace_track_path",
                    "workspace_track_abs_path",
                    "config_path",
                    "config_status",
                }
            }
        )
    payload["workspace_track_path"] = TRACKS_DIR
    payload["workspace_track_abs_path"] = TRACKS_DIR
    os.makedirs(TRACKS_DIR, exist_ok=True)
    with open(APP_CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    payload["config_path"] = APP_CONFIG_PATH
    payload["config_status"] = "saved"
    return payload


def backup_application_config(reason: str, config: dict | None = None) -> str | None:
    try:
        if not os.path.isfile(APP_CONFIG_PATH):
            return None
        os.makedirs(APP_CONFIG_BACKUP_DIR, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(APP_CONFIG_BACKUP_DIR, f"trackapp_config_{stamp}_{reason}.json")
        if config is None:
            with open(APP_CONFIG_PATH, "r", encoding="utf-8") as src:
                payload = json.load(src)
        else:
            payload = dict(config)
        with open(backup_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        return backup_path
    except Exception as exc:
        print(f"[config] 备份配置失败: {exc}")
        return None


def append_application_audit(event: str, payload: dict[str, Any]) -> None:
    try:
        line = {
            "time": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "event": event,
            "payload": payload,
        }
        with open(APP_CONFIG_AUDIT_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception as exc:
        print(f"[config] 写入审计日志失败: {exc}")


def init_application_config() -> dict:
    """初始化 Managed Workspace 目录结构，确保物理目录存在。"""
    os.makedirs(TRACKS_DIR, exist_ok=True)
    os.makedirs(IMPORTS_DIR, exist_ok=True)
    logger.info("工作区已初始化: TRACKS_DIR=%s, IMPORTS_DIR=%s", TRACKS_DIR, IMPORTS_DIR)
    try:
        file_exists = os.path.exists(APP_CONFIG_PATH)
        config = load_application_config()
        config_status = str(config.get("config_status") or "loaded")

        if (not file_exists) or config_status != "loaded":
            config = persist_application_config(config)
            config_status = "created" if not file_exists else "repaired"

        print(f"[config] config_path={APP_CONFIG_PATH}")
        print(f"[config] config_status={config_status}")
        print(f"[config] workspace_track_path={config.get('workspace_track_path')}")
        print(f"[config] workspace_track_abs_path={config.get('workspace_track_abs_path')}")
        return {"ok": True, **config, "config_status": config_status}
    except Exception as exc:
        fallback_path = DEFAULT_APP_CONFIG["workspace_track_path"]
        fallback_abs_path = os.path.abspath(os.path.expanduser(fallback_path))
        try:
            os.makedirs(fallback_abs_path, exist_ok=True)
        except Exception as mkdir_exc:
            print(f"[config] 兜底创建轨迹目录失败: {mkdir_exc}")

        print(f"[config] 初始化失败，已启用兜底目录: {exc}")
        print(f"[config] config_path={APP_CONFIG_PATH}")
        print(f"[config] workspace_track_abs_path={fallback_abs_path}")
        return {
            "ok": False,
            "error": str(exc),
            "config_path": APP_CONFIG_PATH,
            "workspace_track_path": fallback_path,
            "workspace_track_abs_path": fallback_abs_path,
            "config_status": "fallback",
        }


def _sqlite_table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    columns = set()
    for row in rows:
        if isinstance(row, sqlite3.Row):
            columns.add(str(row["name"]))
        else:
            columns.add(str(row[1]))
    return columns


def _normalize_activity_token(value: Any, fallback: str = "unknown") -> str:
    token = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if any(marker in token for marker in (".fit", ".gpx", ".kml", "/", "\\")):
        return fallback
    aliases = {
        "run": "running",
        "road_running": "running",
        "trail_run": "trail_running",
        "trail": "trail_running",
        "ride": "cycling",
        "bike": "cycling",
        "road_bike": "road_cycling",
        "road_biking": "road_cycling",
        "mountain_bike": "mountain_biking",
        "mtb": "mountain_biking",
        "walk": "walking",
        "hike": "hiking",
        "mountaineering": "mountaineering",
        "climb": "mountaineering",
        "drive": "driving",
        "car": "driving",
        "auto": "driving",
    }
    return aliases.get(token, token or fallback)


def _clean_fit_activity_title(file_name: Any, fallback: str = "") -> str:
    name = str(file_name or fallback or "").strip()
    if not name:
        return fallback or ""
    if name.lower().endswith(".fit"):
        name = name[:-4]
    base, _, tail = name.rpartition("_")
    if tail.isdigit() and base.strip():
        return base.strip()
    return name.strip()


def _resolve_display_sport_type(sport_type: Any, sub_sport_type: Any) -> str:
    sub_token = _normalize_activity_token(sub_sport_type, "")
    sport_token = _normalize_activity_token(sport_type)
    sub_display_map = {
        "trail_running": "trail_running",
        "road_cycling": "road_cycling",
        "mountain_biking": "mountain_biking",
        "treadmill_running": "treadmill_running",
        "cardio_training": "cardio",
        "cardio": "cardio",
        "strength_training": "strength_training",
        "yoga": "yoga",
        "pilates": "pilates",
        "hiit": "hiit",
        "breathing": "breathing",
        "flexibility_training": "flexibility_training",
    }
    if sub_token in sub_display_map:
        return sub_display_map[sub_token]
    if sport_token in sub_display_map:
        return sub_display_map[sport_token]
    return sport_token


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _safe_optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


API_CODE_OK = 0
API_CODE_VALIDATION = 1001
API_CODE_NOT_FOUND = 1004
API_CODE_AUTH_REQUIRED = 1401
API_CODE_UNSUPPORTED_FILE = 2001
API_CODE_EXTERNAL_SERVICE = 3001
API_CODE_FILE_IO = 4001
API_CODE_DB = 5001
API_CODE_INTERNAL = 9001


def _new_trace_id() -> str:
    return uuid.uuid4().hex[:12]


def _api_success(data: dict[str, Any] | None = None, msg: str = "ok", **legacy_fields: Any) -> dict[str, Any]:
    payload = dict(data or {})
    if legacy_fields:
        payload.update(legacy_fields)
    response = {"ok": True, "code": API_CODE_OK, "msg": msg, "data": payload, "traceId": _new_trace_id()}
    response.update(payload)
    return response


def _api_error(code: int, msg: str, data: dict[str, Any] | None = None, **legacy_fields: Any) -> dict[str, Any]:
    payload = dict(data or {})
    if legacy_fields:
        payload.update(legacy_fields)
    response = {"ok": False, "code": code, "msg": msg, "data": payload, "traceId": _new_trace_id(), "error": msg}
    response.update(payload)
    return response


def _delete_confirm_token(ids: list[int]) -> str:
    return f"DELETE:{len(ids)}"


def _is_path_under_dir(path: Path, base_dir: Path) -> bool:
    try:
        path.relative_to(base_dir)
        return True
    except ValueError:
        return False


def _decode_weather_json(value: Any) -> dict[str, Any] | None:
    if not value:
        return None
    if isinstance(value, dict):
        return value
    try:
        obj = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return obj if isinstance(obj, dict) else None


def _safe_json_list(value: Any) -> list | None:
    if not value:
        return None
    if isinstance(value, list):
        return value
    try:
        obj = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return obj if isinstance(obj, list) else None


def _infer_weather_from_track_data(data: dict[str, Any]) -> dict[str, Any] | None:
    weather = _decode_weather_json(data.get("weather_json")) or _decode_weather_json(data.get("weather"))
    if weather:
        return weather
    points = data.get("points") or []
    first_point = points[0] if points else {}
    start_time = (
        data.get("start_time")
        or data.get("start_time_utc")
        or first_point.get("time")
    )
    lat = data.get("start_lat")
    lon = data.get("start_lon")
    if lat is None:
        lat = first_point.get("lat")
    if lon is None:
        lon = first_point.get("lon")
    weather_result = fetch_historical_weather(lat, lon, start_time)
    if weather_result and isinstance(weather_result, dict):
        weather_result["source"] = "enrichment"
    return weather_result



def _activity_schema_cache_key() -> str:
    return str(Path(profile_backend.DB_PATH).expanduser().resolve())


def _safe_data_migrate(conn, sql: str) -> None:
    try:
        conn.execute(sql)
    except sqlite3.OperationalError as e:
        if "no such column" in str(e).lower():
            return
        raise


def ensure_activity_sync_schema() -> None:
    global _ACTIVITY_SYNC_SCHEMA_READY_FOR
    cache_key = _activity_schema_cache_key()
    if _ACTIVITY_SYNC_SCHEMA_READY_FOR == cache_key and Path(profile_backend.DB_PATH).exists():
        return

    with _ACTIVITY_SYNC_SCHEMA_LOCK:
        if _ACTIVITY_SYNC_SCHEMA_READY_FOR == cache_key and Path(profile_backend.DB_PATH).exists():
            return

        conn = profile_backend._conn()
        try:

            conn.execute(
                """
                UPDATE activities
                SET file_name = COALESCE(NULLIF(file_name, ''), filename)
                WHERE file_name IS NULL OR file_name = ''
                """
            )
            conn.execute(
                """
                UPDATE activities
                SET filename = COALESCE(NULLIF(filename, ''), file_name)
                WHERE filename IS NULL OR filename = ''
                """
            )
            _safe_data_migrate(
                conn,
                """
                UPDATE activities
                SET distance = COALESCE(distance, dist_km)
                WHERE distance IS NULL
                """
            )
            _safe_data_migrate(
                conn,
                """
                UPDATE activities
                SET duration = COALESCE(duration, duration_sec)
                WHERE duration IS NULL
                """
            )
            _safe_data_migrate(
                conn,
                """
                UPDATE activities
                SET track_json = COALESCE(NULLIF(track_json, ''), points_json)
                WHERE track_json IS NULL OR track_json = ''
                """
            )
            conn.execute(
                """
                UPDATE activities
                SET title = COALESCE(NULLIF(title, ''), filename, file_name)
                WHERE title IS NULL OR title = ''
                """
            )
            conn.execute(
                """
                UPDATE activities
                SET title_source = COALESCE(NULLIF(title_source, ''), 'legacy')
                WHERE title_source IS NULL OR title_source = ''
                """
            )
            _safe_data_migrate(
                conn,
                """
                UPDATE activities
                SET start_time_utc = COALESCE(NULLIF(start_time_utc, ''), CASE WHEN start_time LIKE '%Z' THEN start_time ELSE NULL END)
                WHERE start_time_utc IS NULL OR start_time_utc = ''
                """
            )
            _safe_data_migrate(
                conn,
                """
                UPDATE activities
                SET avg_pace = ROUND(COALESCE(duration, duration_sec) / COALESCE(distance, dist_km), 2)
                WHERE avg_pace IS NULL
                  AND COALESCE(duration, duration_sec, 0) > 0
                  AND COALESCE(distance, dist_km, 0) > 0
                """
            )
            _safe_data_migrate(
                conn,
                """
                UPDATE activities
                SET region_status = CASE
                        WHEN start_lat IS NULL OR start_lon IS NULL THEN 'none'
                        WHEN COALESCE(NULLIF(region, ''), NULLIF(region_display, '')) IS NOT NULL THEN 'success'
                        ELSE COALESCE(NULLIF(region_status, ''), 'pending')
                    END,
                    region_display = CASE
                        WHEN start_lat IS NULL OR start_lon IS NULL THEN COALESCE(NULLIF(region_display, ''), '室内运动')
                        ELSE COALESCE(NULLIF(region_display, ''), NULLIF(region, ''))
                    END,
                    region = CASE
                        WHEN start_lat IS NULL OR start_lon IS NULL THEN COALESCE(NULLIF(region, ''), '室内运动（无GPS）')
                        ELSE region
                    END,
                    region_attempt_count = COALESCE(region_attempt_count, 0)
                WHERE region_status IS NULL OR region_status = ''
                   OR region_display IS NULL OR region_display = ''
                """
            )

            dup_rows = conn.execute(
                """
                SELECT file_name, GROUP_CONCAT(id) AS ids
                FROM activities
                WHERE file_name IS NOT NULL AND file_name != ''
                GROUP BY file_name
                HAVING COUNT(*) > 1
                """
            ).fetchall()
            for row in dup_rows:
                ids = [int(item) for item in str(dict(row).get("ids") or "").split(",") if item]
                for dup_id in ids[1:]:
                    conn.execute(
                        "UPDATE activities SET file_name = file_name || '__dup_' || id WHERE id = ?",
                        (dup_id,),
                    )

            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_activities_file_name_unique ON activities(file_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_activities_start_time_desc ON activities(start_time DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_activities_sport_type ON activities(sport_type)")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS activity_placemarks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    activity_id INTEGER NOT NULL,
                    cp_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL DEFAULT 'custom',
                    icon TEXT NOT NULL DEFAULT '📍',
                    gpx_sym TEXT NOT NULL DEFAULT 'Waypoint',
                    lon REAL NOT NULL,
                    lat REAL NOT NULL,
                    alt REAL,
                    dist_km REAL,
                    source TEXT NOT NULL DEFAULT 'user',
                    created_at INTEGER,
                    updated_at INTEGER,
                    UNIQUE(activity_id, cp_id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_activity_placemarks_activity_dist ON activity_placemarks(activity_id, dist_km)"
            )
            conn.commit()
            _ACTIVITY_SYNC_SCHEMA_READY_FOR = cache_key
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


import track_backend
from utils.metrics_calc import AdvancedMetricsCalc, RadarScoreEngine


def _convert_track_to_algorithm_records(track_data: list[dict]) -> list[dict]:
    """将 FIT 引擎输出的标准轨迹点转换为 AdvancedMetricsCalc 需要的记录格式。"""
    if not track_data:
        return []
    from datetime import datetime
    records = []
    cumulative_dist = 0.0
    prev_lat, prev_lon = None, None
    for pt in track_data:
        ts = None
        raw_time = pt.get("time")
        if raw_time:
            try:
                ts = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass
        if ts is None:
            continue

        if "speed" not in pt and "enhanced_speed" in pt:
            pt["speed"] = pt["enhanced_speed"]
        if "altitude" not in pt and "enhanced_altitude" in pt:
            pt["altitude"] = pt["enhanced_altitude"]
        if "hr" not in pt and "heart_rate" in pt:
            pt["hr"] = pt["heart_rate"]

        lat = pt.get("lat")
        lon = pt.get("lon")
        dist_segment = 0.0
        if lat is not None and lon is not None and prev_lat is not None and prev_lon is not None:
            dist_segment = track_backend.haversine_m(prev_lat, prev_lon, lat, lon)
        cumulative_dist += dist_segment
        prev_lat, prev_lon = lat, lon

        raw_speed = pt.get("speed")
        pace = pt.get("pace")
        calc_speed = (1000.0 / pace) if pace and pace > 0 else 0.0
        final_speed = raw_speed if raw_speed is not None and raw_speed >= 0 else calc_speed

        records.append({
            "timestamp": ts,
            "heart_rate": pt.get("hr"),
            "speed": final_speed,
            "altitude": pt.get("altitude") or pt.get("alt"),
            "distance": cumulative_dist,
            "power": pt.get("power"),
        })
    return records


def _compute_advanced_metrics(track_data: list[dict]) -> dict:
    """从 user_profile 读取当前用户生理画像，对轨迹数据执行 6 维雷达算法。"""
    records = _convert_track_to_algorithm_records(track_data)
    if not records or len(records) < 2:
        return {}
    prof = profile_backend.get_profile()
    user_profile_dict = prof.to_dict() if prof else {}
    user_profile_dict = {k: v for k, v in user_profile_dict.items() if v is not None}
    calc = AdvancedMetricsCalc
    logger.debug("准备计算高级指标，总数据点数: %s", len(records))
    if records:
        mid_idx = len(records) // 2
        logger.debug("首条数据采样: %s", records[0])
        logger.debug("中段数据采样: %s", records[mid_idx])
    trimp = calc.calculate_trimp(records, user_profile_dict)
    hrv_score = calc.score_hrv_efficiency(
        None,  # 修复 Bug：当前单次运动中没有真实 HRV，直接传 None，避免 baseline vs baseline
        user_profile_dict.get("hrv_baseline"),
    )
    decoupling = calc.calculate_aerobic_decoupling(records)
    vam = calc.calculate_vam(records)
    threshold_hr = calc.calculate_threshold_hr(records)
    anaerobic_peak = calc.calculate_anaerobic_peak(records)
    result = {
        "trimp": trimp,
        "hrv": hrv_score,
        "decoupling": decoupling,
        "vam": vam,
        "threshold_hr": threshold_hr,
        "anaerobic_peak": anaerobic_peak,
        "metrics_version": CURRENT_METRICS_VERSION,
    }
    logger.debug("6维指标计算完成: %s", result)
    return result


def _rolling_aggregate_radar_metrics(sport_type: str | None = None) -> dict:
    """
    滚动极值与近期均值聚合（Rolling Aggregation）+ PMC 长期负荷衰减模型
    """
    import math

    now = datetime.now(timezone.utc)

    prof = profile_backend.get_profile()
    hrv_from_profile = prof.hrv_baseline if prof else None

    conn = profile_backend._conn()
    try:
        if sport_type:
            rows = conn.execute(
                """
                SELECT id, start_time_utc, start_time, advanced_metrics
                FROM activities
                WHERE deleted_at IS NULL
                  AND sport_type = ?
                  AND advanced_metrics IS NOT NULL
                  AND advanced_metrics != ''
                ORDER BY COALESCE(start_time_utc, start_time) ASC
                """,
                (sport_type,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, start_time_utc, start_time, advanced_metrics
                FROM activities
                WHERE deleted_at IS NULL
                  AND advanced_metrics IS NOT NULL
                  AND advanced_metrics != ''
                ORDER BY COALESCE(start_time_utc, start_time) ASC
                """
            ).fetchall()
    finally:
        conn.close()

    vam_values = []
    threshold_hr_values = []
    anaerobic_peak_values = []
    decoupling_values = []

    ctl = 0.0
    atl = 0.0
    last_date: datetime | None = None

    for row in rows:
        row = dict(row)
        try:
            time_str = row.get("start_time_utc") or row.get("start_time")
            if not time_str:
                continue
            dt = datetime.fromisoformat(str(time_str).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            age_days = (now - dt).total_seconds() / 86400.0

            if age_days > 90:
                continue

            metrics_str = row.get("advanced_metrics")
            if not metrics_str:
                continue
            metrics = json.loads(metrics_str)
            if not isinstance(metrics, dict):
                continue

            if "vam" in metrics and metrics["vam"] is not None:
                vam_values.append(float(metrics["vam"]))
            if "threshold_hr" in metrics and metrics["threshold_hr"] is not None:
                threshold_hr_values.append(float(metrics["threshold_hr"]))
            if "anaerobic_peak" in metrics and metrics["anaerobic_peak"] is not None:
                anaerobic_peak_values.append(float(metrics["anaerobic_peak"]))

            if "decoupling" in metrics and metrics["decoupling"] is not None:
                decoupling_values.append(float(metrics["decoupling"]))

            trimp = float(metrics.get("trimp") or 0.0)
            if trimp > 0:
                if last_date is None:
                    ctl = trimp / 42.0
                    atl = trimp / 7.0
                else:
                    delta_days = max((dt - last_date).total_seconds() / 86400.0, 0)
                    ctl = ctl * math.exp(-delta_days / 42.0) + trimp * (1 - math.exp(-1 / 42.0))
                    atl = atl * math.exp(-delta_days / 7.0) + trimp * (1 - math.exp(-1 / 7.0))
                last_date = dt

        except (ValueError, TypeError, json.JSONDecodeError):
            continue

    if last_date:
        delta_days_to_now = max((now - last_date).total_seconds() / 86400.0, 0)
        ctl = ctl * math.exp(-delta_days_to_now / 42.0)
        atl = atl * math.exp(-delta_days_to_now / 7.0)

    tsb = ctl - atl

    vam_max = max(vam_values) if vam_values else 0.0
    threshold_hr_max = max(threshold_hr_values) if threshold_hr_values else 0.0
    anaerobic_peak_max = max(anaerobic_peak_values) if anaerobic_peak_values else 0.0

    last_5_decoupling = decoupling_values[-5:] if decoupling_values else []
    decoupling_avg = sum(last_5_decoupling) / len(last_5_decoupling) if last_5_decoupling else 0.0

    hrv = float(hrv_from_profile) if hrv_from_profile is not None else 60.0

    max_hr = prof.max_hr if prof and prof.max_hr else 190
    radar_profile = RadarScoreEngine.build_radar_profile(sport_type or "running", {
        "trimp": ctl,
        "hrv": hrv,
        "decoupling": decoupling_avg,
        "vam": vam_max,
        "threshold_hr": threshold_hr_max,
        "anaerobic_peak": anaerobic_peak_max,
    }, {"max_hr": max_hr})

    return {
        "ctl": round(ctl, 1),
        "atl": round(atl, 1),
        "tsb": round(tsb, 1),
        "hrv": round(hrv, 1),
        "decoupling": round(decoupling_avg, 2),
        "vam": round(vam_max, 1),
        "threshold_hr": round(threshold_hr_max, 1),
        "anaerobic_peak": round(anaerobic_peak_max, 2),
        "radar": radar_profile,
    }


# ── Shadow Diff: 标准化误差分析层 (debug only, 不参与生产决策) ───

_SHADOW_TOLERANCE: dict[str, float] = {
    "pace": 0.5,
    "distance": 0.01,
    "duration": 1.0,
    "avg_hr": 2.0,
    "elevation_gain": 1.0,
    "calories": 2.0,
}

_SHADOW_ROUND: dict[str, int] = {
    "pace": 2,
    "distance": 2,
    "duration": 0,
    "avg_hr": 0,
    "elevation_gain": 1,
    "calories": 0,
}


def _norm(value: Any, decimals: int) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), decimals)
    except (TypeError, ValueError):
        return None


def _build_diff_entry(legacy: Any, resolved: Any, field: str) -> dict[str, Any]:
    decimals = _SHADOW_ROUND.get(field, 2)
    tolerance = _SHADOW_TOLERANCE.get(field, 0)
    l = _norm(legacy, decimals)
    r = _norm(resolved, decimals)
    if l is None and r is None:
        return {"legacy": None, "resolved": None, "delta": None, "delta_percent": None, "match": True, "status": "both_missing"}
    if l is None:
        return {"legacy": None, "resolved": r, "delta": None, "delta_percent": None, "match": False, "status": "legacy_missing"}
    if r is None:
        return {"legacy": l, "resolved": None, "delta": None, "delta_percent": None, "match": False, "status": "resolved_missing"}
    delta = round(l - r, max(decimals, 2))
    delta_pct = round(abs(delta) / max(abs(l), 1e-9) * 100, 2) if abs(l) > 1e-9 else None
    match = abs(delta) <= tolerance
    if l == 0 and r == 0:
        match = True
        delta_pct = None
    return {
        "legacy": l,
        "resolved": r,
        "delta": delta,
        "delta_percent": delta_pct,
        "match": match,
    }


def _build_standard_diff(
    legacy_pace: Any,
    legacy_dist: Any,
    legacy_dur: Any,
    legacy_hr: Any,
    legacy_gain: Any,
    legacy_cal: Any,
    legacy_pace_display: Any = None,
    legacy_pace_unit: Any = None,
    legacy_distance_display: Any = None,
    resolved_sm: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sm = resolved_sm or {}
    return {
        "pace": _build_diff_entry(legacy_pace, sm.get("avg_pace"), "pace"),
        "distance": _build_diff_entry(legacy_dist, sm.get("distance_km"), "distance"),
        "duration": _build_diff_entry(legacy_dur, sm.get("duration_sec"), "duration"),
        "avg_hr": _build_diff_entry(legacy_hr, sm.get("avg_hr"), "avg_hr"),
        "elevation_gain": _build_diff_entry(legacy_gain, sm.get("elevation_gain_m"), "elevation_gain"),
        "calories": _build_diff_entry(legacy_cal, sm.get("calories"), "calories"),
        "avg_pace_display": {
            "legacy": legacy_pace_display,
            "resolved": sm.get("avg_pace_display"),
            "match": legacy_pace_display == sm.get("avg_pace_display"),
            "status": "display_string",
        },
        "pace_unit": {
            "legacy": legacy_pace_unit,
            "resolved": sm.get("pace_unit"),
            "match": legacy_pace_unit == sm.get("pace_unit"),
            "status": "display_string",
        },
        "distance_display": {
            "legacy": legacy_distance_display,
            "resolved": sm.get("distance_display"),
            "match": legacy_distance_display == sm.get("distance_display"),
            "status": "display_string",
        },
        "_meta": {
            "tolerances": _SHADOW_TOLERANCE,
            "generated_by": "MetricsResolver Shadow Layer",
            "trusted": False,
            "note": "debug-only comparison; not used for production decisions",
        },
    }


def _parse_fit_activity_for_sync(file_path: Path) -> dict[str, Any]:
    resolved_path = str(file_path.expanduser().resolve())
    core = FITCoreEngine.parse_fit_file(resolved_path)
    basic = dict(core.get("basic_info") or {})
    track_data = [dict(point) for point in (core.get("track_data") or [])]
    has_track_points = bool(track_data)
    has_gps = any((pt.get("lat") is not None and pt.get("lon") is not None) for pt in track_data)
    data = track_backend.enrich_sport_metadata(
        {
            "points": track_data,
            "track_data": track_data,
            "placemarks": [],
            "basic_info": basic,
            "title": basic.get("title"),
            "fit_title": basic.get("title"),
            "title_source": basic.get("title_source"),
            "start_time": basic.get("start_time"),
            "start_time_utc": basic.get("start_time_utc"),
            "avg_hr": basic.get("avg_hr"),
            "max_hr": basic.get("max_hr"),
            "distance_km": basic.get("total_distance_km"),
            "duration_sec": basic.get("total_timer_time"),
            "calories": basic.get("total_calories"),
            "gain_m": basic.get("total_ascent"),
            "max_alt_m": basic.get("max_altitude"),
        },
        basic.get("sport"),
        basic.get("sub_sport"),
    )
    payload = profile_backend.build_activity_payload(file_path.name, data, resolved_path)
    # RESOLVER FIRST (Phase 2 Migration) — legacy 保留为 fallback
    distance_km = _safe_float(payload.get("dist_km"))
    duration_sec = _safe_int(payload.get("duration_sec"))
    avg_hr = _safe_int(payload.get("avg_hr")) or None
    # LEGACY DISPLAY LOGIC — DO NOT EXTEND
    # resolver-first migration in progress (Phase 2.3)
    # swimming legacy known-broken (sec/km); resolver provides correct sport-aware pace
    avg_pace = round(duration_sec / distance_km, 2) if distance_km > 0 and duration_sec > 0 else None
    # LEGACY DISPLAY LOGIC — DO NOT EXTEND
    # resolver-first migration in progress (Phase 2.3)
    sub_sport = str(payload.get("sub_sport_type") or "unknown")
    # LEGACY SWIMMING BRANCH — DO NOT FIX
    # resolver-first migration in progress; known sec/km bug on swimming, resolver provides /100m
    pace_unit = "/100m" if sub_sport in ("lap_swimming", "open_water") else "/km"
    pace_sec = avg_pace if avg_pace else 0
    if pace_sec and pace_sec > 0:
        pm, ps = int(pace_sec // 60), int(round(pace_sec % 60))
        avg_pace_display = f"{pm}'{ps:02d}''{pace_unit}"
    else:
        avg_pace_display = f"-- {pace_unit}"
    # LEGACY DISPLAY LOGIC — DO NOT EXTEND
    # resolver-first migration in progress (Phase 2.3)
    distance_m = (distance_km or 0) * 1000
    if distance_m <= 5000:
        distance_display = f"{int(distance_m)}m"
    else:
        distance_display = f"{round(distance_km, 2):.2f}km" if distance_km else "-- km"
    track_json = json.dumps(payload.get("points_json") or [], ensure_ascii=False)
    weather = None
    if has_gps:
        weather = fetch_historical_weather(
            payload.get("start_lat"),
            payload.get("start_lon"),
            payload.get("start_time") or payload.get("start_time_utc"),
        )

    stat = file_path.stat()
    advanced_metrics = _compute_advanced_metrics(track_data)
    result = {
        "points": track_data,
        "file_name": file_path.name,
        "filename": payload.get("filename") or file_path.name,
        "title": str(payload.get("title") or payload.get("filename") or file_path.name),
        "title_source": str(payload.get("title_source") or "fit"),
        "start_time": payload.get("start_time"),
        "start_time_utc": payload.get("start_time_utc"),
        "sport_type": payload.get("sport_type") or "unknown",
        "sub_sport_type": payload.get("sub_sport_type") or "unknown",
        "distance": distance_km,
        "dist_km": distance_km,
        "duration": duration_sec,
        "duration_sec": duration_sec,
        "avg_pace": avg_pace,
        "avg_pace_display": avg_pace_display,
        "distance_display": distance_display,
        "avg_hr": avg_hr,
        "max_hr": _safe_int(payload.get("max_hr")) or None,
        "calories": _safe_int(payload.get("calories")),
        "gain_m": _safe_float(payload.get("gain_m")),
        "max_alt_m": _safe_float(payload.get("max_alt_m")),
        "swolf": None,
        "normalized_power": None,
        "avg_stroke_distance": _safe_float(payload.get("avg_stroke_distance")),
        "hr_curve": None,
        "speed_curve": None,
        "track_json": track_json,
        "points_json": track_json,
        "file_path": resolved_path,
        "start_lat": _safe_float(payload.get("start_lat")) or None,
        "start_lon": _safe_float(payload.get("start_lon")) or None,
        "region": str(payload.get("region") or "").strip(),
        "region_city": payload.get("region_city"),
        "region_country": payload.get("region_country"),
        "region_display": payload.get("region_display"),
        "region_status": payload.get("region_status"),
        "region_error": payload.get("region_error"),
        "region_updated_at": payload.get("region_updated_at"),
        "region_attempt_count": payload.get("region_attempt_count", 0),
        "weather_json": json.dumps(weather, ensure_ascii=False) if weather else None,
        "file_mtime": float(stat.st_mtime),
        "file_size": int(stat.st_size),
        "advanced_metrics": json.dumps(advanced_metrics, ensure_ascii=False) if advanced_metrics else None,
        # source 标记：canonical（FIT）+ enrichment（weather/region）
        "source": {
            "fit": "canonical",
            "weather": "enrichment" if weather else "none",
            "region": "pending" if has_gps else "indoor",
        },
    }

    # 从 FIT 文件解析设备型号
    try:
        fit_stream = Stream.from_file(resolved_path)
        fit_msgs, _ = Decoder(fit_stream).read()
        raw_for_device = {"file_id_mesgs": list(fit_msgs.get("file_id_mesgs", []))}
        device_name = MetricsResolver._resolve_device_name(raw_for_device, {})
    except Exception:
        device_name = ""
    result["device_name"] = device_name

    # ── MetricsResolver Shadow Layer (对比验证用，不参与生产决策) ───
    # LEGACY SNAPSHOT — freeze before resolver overwrite
    legacy_avg_pace = avg_pace
    legacy_avg_pace_display = avg_pace_display
    legacy_pace_unit = pace_unit
    legacy_distance_display = distance_display
    try:
        raw_archive = FITCoreEngine.parse_fit_file_raw(resolved_path)
        resolver = MetricsResolver()
        resolved = resolver.resolve(
            raw_archive.get("raw") or {},
            raw_archive.get("meta") or {},
        )
        sm = resolved.get("storage_model") or {}
        result["resolved"] = sm
        result["diff"] = _build_standard_diff(
            legacy_pace=legacy_avg_pace,
            legacy_dist=distance_km,
            legacy_dur=duration_sec,
            legacy_hr=avg_hr,
            legacy_gain=payload.get("gain_m"),
            legacy_cal=payload.get("calories"),
            legacy_pace_display=legacy_avg_pace_display,
            legacy_pace_unit=legacy_pace_unit,
            legacy_distance_display=legacy_distance_display,
            resolved_sm=sm,
        )
        result["shadow_diff_json"] = json.dumps(result.get("diff") or {}, ensure_ascii=False, default=str)
        # Shadow Layer diff 持久化日志（不阻塞生产路径）
        try:
            import json as _json
            _shadow = logging.getLogger("metrics_resolver.shadow")
            _shadow.info(
                "[shadow] diff=%s | activity=%s",
                _json.dumps(result.get("diff"), ensure_ascii=False, default=str),
                resolved_path,
            )
        except Exception:
            pass  # 日志失败不阻塞同步流程

        # ═══════════════════════════════════════════════
        # RESOLVER FIRST OVERWRITE BLOCK
        # Task 2.1-2.3: single overwrite region, no second block
        # ═══════════════════════════════════════════════
        # Phase 2.1 — distance / duration (validated 44/44)
        distance_km = sm.get("distance_km", distance_km)
        duration_sec = sm.get("duration_sec", duration_sec)
        result["distance"] = distance_km
        result["dist_km"] = distance_km
        result["duration"] = duration_sec
        result["duration_sec"] = duration_sec
        # Phase 2.2 — avg_hr / calories / elevation_gain / elevation_loss (validated 44/44)
        avg_hr = sm.get("avg_hr", avg_hr)
        calories = sm.get("calories", _safe_int(payload.get("calories")))
        elevation_gain = sm.get("elevation_gain_m", _safe_float(payload.get("gain_m")))
        elevation_loss = sm.get("elevation_loss_m", _safe_float(payload.get("total_descent_m", 0)))
        result["avg_hr"] = avg_hr
        result["calories"] = calories
        result["gain_m"] = elevation_gain
        result["total_descent_m"] = elevation_loss
        # Phase 2.3 — pace / display (validated 44/44 non-swim; swimming resolver > legacy)
        avg_pace = sm.get("avg_pace", avg_pace)
        avg_pace_display = sm.get("avg_pace_display", avg_pace_display)
        pace_unit = sm.get("pace_unit", pace_unit)
        distance_display = sm.get("distance_display", distance_display)
        result["avg_pace"] = avg_pace
        result["avg_pace_display"] = avg_pace_display
        result["pace_unit"] = pace_unit
        result["distance_display"] = distance_display
        # Phase 2.4 — swolf: promote resolver-computed value for pool swimming;
        # for open water / SUP use avg_stroke_distance from FIT session;
        # non-water sports keep swolf=None (resolver fallback 0 is invalid for land sports)
        sub_sport_token = _normalize_activity_token(payload.get("sub_sport_type") or "", "")
        sport_token = _normalize_activity_token(payload.get("sport_type") or "", "")
        if sub_sport_token == "lap_swimming":
            result["swolf"] = sm.get("swolf")
        elif sub_sport_token in ("open_water", "open_water_swimming") or sport_token == "stand_up_paddleboarding":
            result["swolf"] = result["avg_stroke_distance"]
        # Phase 2.5 — normalized_power: promote resolver-computed value from storage_model
        result["normalized_power"] = sm.get("normalized_power_w")
        ap = resolved.get("analysis_pack") or {}
        if ap.get("hr_curve"):
            result["hr_curve"] = json.dumps(ap["hr_curve"], ensure_ascii=False)
        if ap.get("speed_curve"):
            result["speed_curve"] = json.dumps(ap["speed_curve"], ensure_ascii=False)
    except Exception as exc:
        logger.exception("MetricsResolver 解析失败，将使用 legacy 值兜底: %s, error=%s", resolved_path, exc)

    return result


def _insert_activity_sync_row(conn: sqlite3.Connection, activity: dict[str, Any]) -> int:
    try:
        cur = conn.execute(
            """
            INSERT INTO activities
                (file_name, filename, title, title_source, start_time, start_time_utc, sport_type, sub_sport_type,
                 distance, dist_km, duration, duration_sec, avg_pace, avg_hr, max_hr,
                 calories, track_json, points_json, file_path, gain_m, max_alt_m, start_lat, start_lon, region,
                 region_city, region_country, region_display, region_status, region_error, region_updated_at, region_attempt_count,
                 weather_json, file_mtime, file_size, advanced_metrics, normalized_power, swolf, device_name,
                 shadow_diff_json, source_type, is_mock, deleted_at, updated_at, hr_curve, speed_curve,
                 min_alt_m, total_descent_m, up_count, down_count, max_single_climb_m, difficulty_score, report_metrics_version,
                 avg_grade_pct, max_slope_pct, min_slope_pct, uphill_pct, downhill_pct)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, 'fit_sdk', 0, NULL, datetime('now'), ?, ?,
                    ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?)
            """,
            (
                activity.get("file_name"),
                activity.get("filename"),
                activity.get("title"),
                activity.get("title_source"),
                activity.get("start_time"),
                activity.get("start_time_utc"),
                activity.get("sport_type"),
                activity.get("sub_sport_type"),
                activity.get("distance"),
                activity.get("dist_km"),
                activity.get("duration"),
                activity.get("duration_sec"),
                activity.get("avg_pace"),
                activity.get("avg_hr"),
                activity.get("max_hr"),
                activity.get("calories"),
                activity.get("track_json"),
                activity.get("points_json"),
                activity.get("file_path"),
                activity.get("gain_m"),
                activity.get("max_alt_m"),
                activity.get("start_lat"),
                activity.get("start_lon"),
                activity.get("region"),
                activity.get("region_city"),
                activity.get("region_country"),
                activity.get("region_display"),
                activity.get("region_status"),
                activity.get("region_error"),
                activity.get("region_updated_at"),
                activity.get("region_attempt_count", 0),
                activity.get("weather_json"),
                activity.get("file_mtime"),
                activity.get("file_size"),
                activity.get("advanced_metrics"),
                activity.get("normalized_power"),
                activity.get("swolf"),
                activity.get("device_name") or "Unknown Device",
                activity.get("shadow_diff_json"),
                activity.get("hr_curve"),
                activity.get("speed_curve"),
                activity.get("min_alt_m"),
                activity.get("total_descent_m"),
                activity.get("up_count"),
                activity.get("down_count"),
                activity.get("max_single_climb_m"),
                activity.get("difficulty_score"),
                activity.get("report_metrics_version"),
                activity.get("avg_grade_pct"),
                activity.get("max_slope_pct"),
                activity.get("min_slope_pct"),
                activity.get("uphill_pct"),
                activity.get("downhill_pct"),
            ),
        )
        return int(cur.lastrowid)
    except sqlite3.IntegrityError:
        file_name = activity.get("file_name") or ""
        file_path = activity.get("file_path") or ""
        existing = _find_activity_by_file_path(conn, file_path, include_deleted=True) if file_path else None
        if not existing and file_name:
            existing = _find_activity_by_file_name(conn, file_name, include_deleted=True)
        if not existing:
            raise
        _update_activity_sync_row(conn, int(existing["id"]), activity)
        return int(existing["id"])


def _update_activity_sync_row(conn: sqlite3.Connection, activity_id: int, activity: dict[str, Any]) -> None:
    conn.execute(
        """
        UPDATE activities
        SET file_name = ?, filename = ?, title = ?, title_source = ?, start_time = ?, start_time_utc = ?,
            sport_type = ?, sub_sport_type = ?, distance = ?, dist_km = ?, duration = ?, duration_sec = ?,
            avg_pace = ?, avg_hr = ?, max_hr = ?, calories = ?, track_json = ?, points_json = ?,
            file_path = ?, gain_m = ?, max_alt_m = ?, start_lat = ?, start_lon = ?, region = ?,
            region_city = ?, region_country = ?, region_display = ?, region_status = ?, region_error = ?,
            region_updated_at = ?, region_attempt_count = ?,
            weather_json = ?, file_mtime = ?, file_size = ?, advanced_metrics = ?,
            normalized_power = ?, swolf = ?, device_name = ?, shadow_diff_json = ?, hr_curve = ?, speed_curve = ?,
            min_alt_m = ?, total_descent_m = ?, up_count = ?, down_count = ?, max_single_climb_m = ?, difficulty_score = ?, report_metrics_version = ?,
            avg_grade_pct = ?, max_slope_pct = ?, min_slope_pct = ?, uphill_pct = ?, downhill_pct = ?,
            source_type = 'fit_sdk', is_mock = 0, deleted_at = NULL, updated_at = datetime('now')
        WHERE id = ?
        """,
        (
            activity.get("file_name"),
            activity.get("filename"),
            activity.get("title"),
            activity.get("title_source"),
            activity.get("start_time"),
            activity.get("start_time_utc"),
            activity.get("sport_type"),
            activity.get("sub_sport_type"),
            activity.get("distance"),
            activity.get("dist_km"),
            activity.get("duration"),
            activity.get("duration_sec"),
            activity.get("avg_pace"),
            activity.get("avg_hr"),
            activity.get("max_hr"),
            activity.get("calories"),
            activity.get("track_json"),
            activity.get("points_json"),
            activity.get("file_path"),
            activity.get("gain_m"),
            activity.get("max_alt_m"),
            activity.get("start_lat"),
            activity.get("start_lon"),
            activity.get("region"),
            activity.get("region_city"),
            activity.get("region_country"),
            activity.get("region_display"),
            activity.get("region_status"),
            activity.get("region_error"),
            activity.get("region_updated_at"),
            activity.get("region_attempt_count", 0),
            activity.get("weather_json"),
            activity.get("file_mtime"),
            activity.get("file_size"),
            activity.get("advanced_metrics"),
            activity.get("normalized_power"),
            activity.get("swolf"),
            activity.get("device_name") or "Unknown Device",
            activity.get("shadow_diff_json"),
            activity.get("hr_curve"),
            activity.get("speed_curve"),
            activity.get("min_alt_m"),
            activity.get("total_descent_m"),
            activity.get("up_count"),
            activity.get("down_count"),
            activity.get("max_single_climb_m"),
            activity.get("difficulty_score"),
            activity.get("report_metrics_version"),
            activity.get("avg_grade_pct"),
            activity.get("max_slope_pct"),
            activity.get("min_slope_pct"),
            activity.get("uphill_pct"),
            activity.get("downhill_pct"),
            activity_id,
        ),
    )


def _activity_display_sql() -> str:
    return (
        "CASE "
        "WHEN COALESCE(NULLIF(sub_sport_type, ''), 'unknown') IN ('trail_running', 'road_cycling', 'mountain_biking') THEN sub_sport_type "
        "WHEN COALESCE(NULLIF(sport_type, ''), 'unknown') IN ('trail_running', 'road_cycling', 'mountain_biking') THEN sport_type "
        "ELSE COALESCE(NULLIF(sport_type, ''), 'unknown') "
        "END"
    )


def _cleanup_invalid_activity_types(conn: sqlite3.Connection) -> None:
    invalid_patterns = ("%.fit%", "%.gpx%", "%.kml%", "%/%", "%\\%")
    conn.execute(
        """
        UPDATE activities
        SET sport_type = 'unknown',
            updated_at = datetime('now')
        WHERE deleted_at IS NULL
          AND COALESCE(sport_type, '') != ''
          AND (
              lower(sport_type) LIKE ? OR
              lower(sport_type) LIKE ? OR
              lower(sport_type) LIKE ? OR
              sport_type LIKE ? OR
              sport_type LIKE ?
          )
        """,
        invalid_patterns,
    )
    conn.execute(
        """
        UPDATE activities
        SET sub_sport_type = 'unknown',
            updated_at = datetime('now')
        WHERE deleted_at IS NULL
          AND COALESCE(sub_sport_type, '') != ''
          AND (
              lower(sub_sport_type) LIKE ? OR
              lower(sub_sport_type) LIKE ? OR
              lower(sub_sport_type) LIKE ? OR
              sub_sport_type LIKE ? OR
              sub_sport_type LIKE ?
          )
        """,
        invalid_patterns,
    )


def _walk_fit_files(base: Path) -> list[Path]:
    fit_files: list[Path] = []
    for root, _dirs, files in os.walk(str(base)):
        for name in files:
            if name.lower().endswith(".fit"):
                fit_files.append(Path(root) / name)
    fit_files.sort(key=lambda item: (str(item.parent).lower(), item.name.lower()))
    abs_path = str(base.resolve()) if base.exists() else str(base)
    logger.info("FIT 扫描目录: %s, 发现文件数: %s", abs_path, len(fit_files))
    if len(fit_files) == 0:
        logger.warning("FIT 文件数为 0，请确认路径是否正确: %s", abs_path)
    return fit_files


def _inspect_directory_access(path: str) -> dict[str, Any]:
    base = Path(path).expanduser()
    exists = base.exists()
    is_dir = base.is_dir()
    abs_path = str(base.resolve()) if exists else str(base)
    readable = exists and os.access(str(base), os.R_OK | os.X_OK)
    writable = exists and os.access(str(base), os.W_OK | os.X_OK)
    fit_count = len(_walk_fit_files(base)) if exists and is_dir and readable else 0
    return {
        "path": abs_path,
        "exists": bool(exists),
        "is_dir": bool(is_dir),
        "readable": bool(readable),
        "writable": bool(writable),
        "fit_count": fit_count,
    }


def resolve_workspace_track_dir(auto_recover: bool = True) -> dict[str, Any]:
    """受控工作区：始终返回 TRACKS_DIR 的状态，不做路径猜测。"""
    config = load_application_config()
    status = _inspect_directory_access(TRACKS_DIR)
    config["workspace_track_path"] = TRACKS_DIR
    config["workspace_track_abs_path"] = TRACKS_DIR
    config["workspace_track_status"] = status
    config["workspace_track_recovered"] = None
    config["ok"] = True
    return config


def _source_scope_filter_clause(source_dir: str) -> tuple[str, list[Any]]:
    normalized = (str(source_dir) or "").strip()
    if not normalized:
        return "", []
    prefix = normalized.rstrip("/\\") + os.sep
    return "WHERE file_path LIKE ? AND deleted_at IS NULL", [prefix + "%"]


def _activity_row_identity(row: dict[str, Any]) -> str:
    filename = str(row.get("filename") or row.get("file_name") or "").strip()
    if filename:
        return filename
    file_path = str(row.get("file_path") or "").strip()
    if file_path:
        return os.path.basename(file_path)
    return f"id:{row.get('id')}"


def _dedupe_activity_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        identity = _activity_row_identity(row)
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(row)
    return deduped


def check_activity_data_integrity() -> dict[str, Any]:
    config = resolve_workspace_track_dir(auto_recover=True)
    source_dir = str(config.get("workspace_track_abs_path") or "")
    source_status = dict(config.get("workspace_track_status") or {})
    fit_files = _walk_fit_files(Path(source_dir)) if source_status.get("exists") and source_status.get("is_dir") else []
    source_names = sorted({path.name for path in fit_files})

    ensure_activity_sync_schema()
    conn = profile_backend._conn()
    try:
        where_clause, params = _source_scope_filter_clause(source_dir)
        db_rows = conn.execute(
            f"""
            SELECT id, COALESCE(file_name, filename) AS key_name, filename, file_path, start_time
            FROM activities
            {where_clause}
            ORDER BY COALESCE(start_time, updated_at) DESC, id DESC
            """,
            tuple(params),
        ).fetchall()
    finally:
        conn.close()

    db_records = [dict(row) for row in db_rows]
    db_names = sorted({str(row.get("filename") or row.get("key_name") or "").strip() for row in db_records if str(row.get("filename") or row.get("key_name") or "").strip().lower().endswith(".fit")})
    source_only = sorted(set(source_names) - set(db_names))
    db_only = sorted(set(db_names) - set(source_names))

    return {
        "ok": True,
        "source_dir": source_dir,
        "source_status": source_status,
        "db_record_total": len(db_records),
        "source_fit_total": len(source_names),
        "db_fit_total": len(db_names),
        "missing_in_db": source_only,
        "missing_on_disk": db_only,
        "has_diff": bool(source_only or db_only),
        "recovered": config.get("workspace_track_recovered"),
    }


def _format_sync_error_message(exc: Exception) -> str:
    raw = str(exc or "").strip() or exc.__class__.__name__
    if isinstance(exc, TimeoutError):
        return f"{raw}。请稍后重试，或关闭其他正在访问运动记录的窗口后再试。"
    if isinstance(exc, sqlite3.OperationalError) and "locked" in raw.lower():
        return "数据库当前正被其他任务占用，系统已自动等待并重试多次，但仍未完成同步。请稍后重试，或关闭其他正在加载运动记录的窗口后再试。"
    return raw


def _emit_sync_progress(progress_callback, **payload: Any) -> None:
    if progress_callback is None:
        return
    progress_callback(dict(payload))


def _find_activity_by_file_name(conn: sqlite3.Connection, file_name: str, include_deleted: bool = False) -> dict[str, Any] | None:
    deleted_clause = "" if include_deleted else "AND deleted_at IS NULL"
    row = conn.execute(
        f"""
        SELECT id, file_name, filename, file_path, deleted_at
        FROM activities
        WHERE COALESCE(file_name, filename) = ? {deleted_clause}
        ORDER BY id DESC
        LIMIT 1
        """,
        (file_name,),
    ).fetchone()
    return dict(row) if row else None


def _find_activity_by_file_path(conn: sqlite3.Connection, file_path: str, include_deleted: bool = False) -> dict[str, Any] | None:
    deleted_clause = "" if include_deleted else "AND deleted_at IS NULL"
    row = conn.execute(
        f"""
        SELECT id, file_name, filename, file_path, title, sport_type, sub_sport_type, start_time, updated_at, file_mtime, file_size, deleted_at
        FROM activities
        WHERE file_path = ? {deleted_clause}
        ORDER BY id DESC
        LIMIT 1
        """,
        (file_path,),
    ).fetchone()
    return dict(row) if row else None


def _load_existing_file_index(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """快速加载 DB 中所有已入库文件的 file_path → {file_mtime, file_size, id} 索引。
    用于在解析 FIT 文件前预判是否需要入库，避免无效解析。
    """
    rows = conn.execute(
        """
        SELECT id, file_path, file_mtime, file_size, device_name
        FROM activities
        WHERE deleted_at IS NULL
          AND COALESCE(file_path, '') != ''
        """
    ).fetchall()
    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        path = str(row["file_path"] or "").strip()
        if not path:
            continue
        resolved = str(Path(path).expanduser().resolve())
        existing = index.get(resolved)
        if existing is None or int(row["id"] or 0) > int(existing.get("id") or 0):
            index[resolved] = {
                "id": int(row["id"] or 0),
                "file_mtime": row["file_mtime"],
                "file_size": row["file_size"],
                "device_name": row["device_name"] or "",
            }
    return index


def _is_file_unchanged(disk_path: Path, existing: dict[str, Any]) -> bool:
    """判断磁盘文件与 DB 记录是否一致（mtime 和 size 均匹配）。"""
    existing_mtime = existing.get("file_mtime")
    existing_size = existing.get("file_size")
    if existing_mtime is None or existing_size is None:
        return False
    try:
        stat = disk_path.stat()
        disk_mtime = stat.st_mtime
        disk_size = stat.st_size
    except OSError:
        return False
    return (
        abs(float(existing_mtime) - disk_mtime) < 0.001
        and int(existing_size) == disk_size
    )


def _persist_sync_activity(activity: dict[str, Any]) -> dict[str, Any]:
    file_name = str(activity.get("file_name") or activity.get("filename") or "").strip()
    file_path = str(activity.get("file_path") or "").strip()
    activity["sport_type"] = _normalize_activity_token(activity.get("sport_type"))
    activity["sub_sport_type"] = _normalize_activity_token(activity.get("sub_sport_type"))

    # CONTRACT §2.1 / §6: 在持久化前计算报告 canonical 派生指标
    _points_raw = activity.get("points")
    if _points_raw and isinstance(_points_raw, list) and len(_points_raw) >= 2:
        try:
            _dist = _safe_float(activity.get("dist_km", 0))
            _gain = _safe_float(activity.get("gain_m", 0))
            _report = compute_report_metrics(_points_raw, _dist, _gain)
            activity.update(_report)
        except Exception as exc:
            logger.exception("[METRICS] compute_report_metrics failed for %s: %s", activity.get("file_name"), exc)

    def _write() -> dict[str, Any]:
        conn = profile_backend._conn()
        try:
            existing = _find_activity_by_file_path(conn, file_path, include_deleted=True) if file_path else None
            if existing and not existing.get("deleted_at"):
                file_mtime = activity.get("file_mtime")
                file_size = activity.get("file_size")
                existing_device = str(existing.get("device_name") or "").strip().lower()
                needs_device_refresh = (
                    not existing_device
                    or existing_device == "unknown"
                    or existing_device == "unknown device"
                    or existing_device.isdigit()
                )
                if (
                    not needs_device_refresh
                    and file_mtime is not None
                    and file_size is not None
                    and existing.get("file_mtime") is not None
                    and existing.get("file_size") is not None
                    and abs(float(existing.get("file_mtime") or 0) - float(file_mtime)) < 0.001
                    and int(existing.get("file_size") or 0) == int(file_size)
                ):
                    return {"op": "skipped", "id": int(existing["id"])}
            if not existing and file_name:
                existing = _find_activity_by_file_name(conn, file_name, include_deleted=True)
            if existing:
                _update_activity_sync_row(conn, int(existing["id"]), activity)
                op = "updated"
                activity_id = int(existing["id"])
            else:
                activity_id = _insert_activity_sync_row(conn, activity)
                op = "inserted"
            conn.commit()
            return {"op": op, "id": activity_id}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    return profile_backend.run_with_db_retry(_write)


def _sync_single_fit_file(file_path: str | Path) -> dict[str, Any]:
    ensure_activity_sync_schema()
    target = Path(file_path).expanduser().resolve()
    if not target.is_file():
        raise FileNotFoundError(f"未找到 FIT 文件: {target}")
    if target.suffix.lower() != ".fit":
        raise ValueError(f"仅支持监控 FIT 文件: {target}")
    activity = _parse_fit_activity_for_sync(target)
    write_res = _persist_sync_activity(activity)
    activity_id = int(write_res.get("id") or 0)

    conn = profile_backend._conn()
    try:
        row = _find_activity_by_file_path(conn, str(target))
    finally:
        conn.close()

    return {
        "ok": True,
        "activity_id": activity_id or int((row or {}).get("id") or 0),
        "file_path": str(target),
        "filename": target.name,
        "op": write_res.get("op"),
        "activity": row or {},
        "resolved": activity.get("resolved"),
        "diff": activity.get("diff"),
    }


class FITFolderHandler(FileSystemEventHandler):
    def __init__(self, schedule_callback) -> None:
        super().__init__()
        self._schedule_callback = schedule_callback

    def _is_valid_fit(self, file_path: str) -> bool:
        return file_path.lower().endswith(".fit")

    def on_created(self, event) -> None:
        if getattr(event, "is_directory", False):
            return
        file_path = str(getattr(event, "src_path", "") or "").strip()
        if not self._is_valid_fit(file_path):
            return
        logger.debug("FITFolderHandler.on_created: %s", file_path)
        self._schedule_callback(file_path)

    def on_moved(self, event) -> None:
        """处理文件移动/重命名事件（macOS Finder 拖拽/浏览器下载/原子写入等）。"""
        if getattr(event, "is_directory", False):
            return
        dest_path = str(getattr(event, "dest_path", "") or "").strip()
        if not self._is_valid_fit(dest_path):
            return
        logger.debug("FITFolderHandler.on_moved -> dest: %s", dest_path)
        self._schedule_callback(dest_path)


class FITFolderWatchService:
    """受控工作区 FIT 目录监听服务，带文件稳定性检测（Stable Check）。"""

    def __init__(self, api: "Api") -> None:
        self._api = api
        self._observer: Observer | None = None
        self._handler: FITFolderHandler | None = None
        self._watch_path = ""
        self._lock = threading.Lock()
        # 暂存队列：{file_path: StagingEntry}
        self._staging_queue: dict[str, dict[str, Any]] = {}
        self._synced_signatures: dict[str, tuple[int, int]] = {}
        self._staging_poll_active = False
        self._staging_poll_thread: threading.Thread | None = None

        # 【新增：P1 工业级加固资产】
        self._recently_enqueued: dict[str, float] = {}  # 存放 file_path -> timestamp
        self.suspended = False                          # 状态挂起锁

    def _staging_loop(self) -> None:
        """后台轮询线程：保持常驻，每隔 poll_interval 检查暂存队列。"""
        logger.info("[STAGING] 轮询线程已启动")
        consecutive_errors = 0
        while not _APP_SHUTTING_DOWN.is_set():
            try:
                ready: list[str] = []
                with self._lock:
                    if self._staging_queue:
                        now = time.time()
                        for file_path, entry in list(self._staging_queue.items()):
                            try:
                                if not os.path.exists(file_path):
                                    logger.debug("FIT staging 文件已消失，移除: %s", file_path)
                                    self._staging_queue.pop(file_path, None)
                                    continue
                                current_size = os.path.getsize(file_path)
                            except OSError:
                                self._staging_queue.pop(file_path, None)
                                continue

                            if entry.get("last_size") is not None and entry["last_size"] == current_size:
                                stable_since = entry.get("stable_since") or now
                                if entry.get("stable_since") is None:
                                    entry["stable_since"] = now
                                elapsed = now - stable_since
                                if elapsed >= FIT_WATCH_STABLE_SEC:
                                    logger.debug("FIT staging 文件稳定: %s (size=%s, stable=%.1fs)", file_path, current_size, elapsed)
                                    ready.append(file_path)
                            else:
                                entry["last_size"] = current_size
                                entry["stable_since"] = now
                                logger.debug("FIT staging 文件变化: %s (size=%s)", file_path, current_size)

                        for fp in ready:
                            self._staging_queue.pop(fp, None)

                # 在锁外安全地同步和解析文件
                for fp in ready:
                    self._process_stable_file(fp)

                consecutive_errors = 0
            except Exception as exc:
                consecutive_errors += 1
                logger.exception("[STAGING] 轮询异常 (连续 %d 次): %s", consecutive_errors, exc)
                if consecutive_errors > 10:
                    logger.error("[STAGING] 连续异常超过 10 次，线程退出")
                    break

            time.sleep(FIT_WATCH_POLL_INTERVAL_SEC)

        logger.info("[STAGING] 轮询线程已退出")

    def _ensure_polling_locked(self) -> None:
        if _APP_SHUTTING_DOWN.is_set():
            return
        # 线程健康自愈：如果线程已死但标记为活动，重置标记后重新启动
        if self._staging_poll_active:
            if self._staging_poll_thread and not self._staging_poll_thread.is_alive():
                logger.warning("FIT staging 线程已意外终止，正在自愈重启...")
                self._staging_poll_active = False
            else:
                return
        self._staging_poll_active = True
        self._staging_poll_thread = threading.Thread(target=self._staging_loop, daemon=True, name="fit-staging-poll")
        self._staging_poll_thread.start()
        logger.debug("FIT staging 轮询线程已启动")

    def _enqueue_created_file(self, file_path: str) -> None:
        if self.suspended:
            logger.debug("FIT enqueue 跳过（已挂起）: %s", file_path)
            return
        normalized = str(Path(file_path).expanduser().resolve())
        now = time.time()

        with self._lock:
            # 5秒内同一个路径禁止重复入队，彻底干掉 Mac Finder 的多事件轰炸
            last_time = self._recently_enqueued.get(normalized, 0.0)
            if now - last_time < 5.0:
                logger.debug("FIT enqueue 5秒去重跳过: %s (last=%.1fs ago)", normalized, now - last_time)
                return
            self._recently_enqueued[normalized] = now

            if normalized in self._staging_queue:
                logger.debug("FIT enqueue 已在队列中: %s", normalized)
                return
            self._staging_queue[normalized] = {"last_size": None, "stable_since": None}
            logger.info("FIT enqueue 入队等待稳定: %s", normalized)
            self._ensure_polling_locked()

    def _process_stable_file(self, file_path: str) -> None:
        """文件大小已稳定 2 秒，执行静默解析并通知前端。"""
        logger.info("[STAGING] 开始处理稳定文件: %s", file_path)
        try:
            signature = self._file_signature(file_path)
            if signature is None:
                logger.warning("[STAGING] 无法获取文件签名: %s", file_path)
                return
            logger.info("[STAGING] 文件签名: %s -> %s", file_path, signature)
            with self._lock:
                existing_sig = self._synced_signatures.get(file_path)
                if existing_sig == signature:
                    logger.info("[STAGING] 签名匹配，跳过已处理文件: %s (sig=%s)", file_path, signature)
                    return
            logger.info("[STAGING] 开始解析 FIT: %s", file_path)
            result = _sync_single_fit_file(file_path)
            logger.info("[STAGING] 解析结果: ok=%s, activity_id=%s, op=%s", result.get("ok"), result.get("activity_id"), result.get("op"))
            if result and result.get("ok"):
                activity_id = int(result.get("activity_id") or 0)
                with self._lock:
                    if signature:
                        self._synced_signatures[file_path] = signature
                if activity_id:
                    logger.info("[STAGING] 通知前端: file=%s, activity_id=%s", file_path, activity_id)
                    self._api.notify_new_track_detected(file_path, activity_id)
                    self._api._schedule_region_enrichment()
                else:
                    logger.warning("[STAGING] 解析成功但 activity_id 为 0: %s", file_path)
            else:
                logger.error("[STAGING] 解析失败: %s, result=%s", file_path, result)
        except Exception as exc:
            logger.exception("[STAGING] 处理文件异常: %s, error=%s", file_path, exc)

    def start(self) -> dict[str, Any]:
        return self.restart(TRACKS_DIR)

    def restart(self, target_dir: str | None = None) -> dict[str, Any]:
        with self._lock:
            self._stop_locked()
            self._staging_queue.clear()
            self._synced_signatures.clear()
            base = Path(TRACKS_DIR)
            os.makedirs(str(base), exist_ok=True)
            if not base.is_dir():
                logger.error("FIT 监听目录无效: %s", base)
                return {"ok": False, "error": f"监听目录无效: {base}"}
            observer = Observer()
            handler = FITFolderHandler(self._enqueue_created_file)
            observer.schedule(handler, str(base), recursive=True)
            observer.start()
            self._observer = observer
            self._handler = handler
            self._watch_path = str(base)
            logger.info("Watchdog 已启动: path=%s, observer=%s", self._watch_path, type(observer).__name__)
            return {"ok": True, "watching": True, "path": self._watch_path}

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    def _stop_locked(self) -> None:
        observer = self._observer
        self._observer = None
        self._handler = None
        old_path = self._watch_path
        self._watch_path = ""
        if observer is None:
            return
        try:
            observer.stop()
            observer.join(timeout=3.0)
            print(f"[watchdog] 已停止监听 FIT 目录: {old_path}")
        except Exception as exc:
            print(f"[watchdog] 停止监听失败: {exc}")

    def _file_signature(self, file_path: str) -> tuple[int, int] | None:
        try:
            stat = Path(file_path).stat()
        except OSError:
            return None
        return (int(stat.st_size), int(stat.st_mtime_ns))


class FitSyncJobManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._active_job_id: str | None = None
        self._latest_job_id: str | None = None

    def _snapshot(self, status: dict[str, Any] | None) -> dict[str, Any]:
        if not status:
            return {"ok": False, "error": "未找到同步任务"}
        return {
            key: value
            for key, value in status.items()
            if key not in {"_thread"}
        }

    def _finish(self, job_id: str, result: dict[str, Any]) -> None:
        with self._lock:
            status = self._jobs.get(job_id)
            if not status:
                return
            ok = bool(result.get("ok"))
            total = _safe_int(status.get("total"))
            current = _safe_int(status.get("current"))
            if total > 0:
                status["current"] = min(total, max(current, 0 if not ok else total))
                status["progress"] = round((status["current"] / total) * 100, 1)
            else:
                status["progress"] = 100.0 if ok else float(status.get("progress") or 0.0)
            status["state"] = "done"
            status["stage"] = "completed" if ok else "error"
            status["ok"] = ok
            status["result"] = result
            status["error"] = str(result.get("error") or "")
            status["message"] = str(
                result.get("message")
                or status.get("message")
                or ("同步完成" if ok else status["error"] or "同步失败")
            )
            status["finished_at"] = datetime.now(timezone.utc).isoformat()
            status["updated_at"] = status["finished_at"]
            if self._active_job_id == job_id:
                self._active_job_id = None

    def update(self, job_id: str, payload: dict[str, Any]) -> None:
        with self._lock:
            status = self._jobs.get(job_id)
            if not status:
                return
            status.update(payload)
            total = _safe_int(status.get("total"))
            current = _safe_int(status.get("current"))
            if total > 0:
                status["current"] = min(total, max(current, 0))
                status["progress"] = round((status["current"] / total) * 100, 1)
            status["updated_at"] = datetime.now(timezone.utc).isoformat()

    def start(self, worker) -> dict[str, Any]:
        with self._lock:
            if self._active_job_id:
                running = self._jobs.get(self._active_job_id)
                if running and running.get("state") in {"queued", "running"}:
                    return {
                        "ok": True,
                        "job_id": self._active_job_id,
                        "already_running": True,
                        "status": self._snapshot(running),
                    }

            job_id = uuid.uuid4().hex
            now = datetime.now(timezone.utc).isoformat()
            status = {
                "job_id": job_id,
                "state": "queued",
                "stage": "queued",
                "ok": None,
                "message": "同步任务已创建，正在准备扫描目录...",
                "current": 0,
                "total": 0,
                "progress": 0.0,
                "current_file": "",
                "inserted": 0,
                "updated": 0,
                "skipped": 0,
                "errors": [],
                "result": None,
                "error": "",
                "started_at": now,
                "updated_at": now,
                "finished_at": None,
            }
            self._jobs[job_id] = status
            self._active_job_id = job_id
            self._latest_job_id = job_id

            thread = threading.Thread(
                target=self._run_worker,
                args=(job_id, worker),
                daemon=True,
                name=f"fit-sync-{job_id[:8]}",
            )
            status["_thread"] = thread
            thread.start()

        return {
            "ok": True,
            "job_id": job_id,
            "already_running": False,
            "status": self.get_status(job_id),
        }

    def _run_worker(self, job_id: str, worker) -> None:
        self.update(job_id, {"state": "running", "stage": "preparing"})
        try:
            result = worker(lambda payload: self.update(job_id, payload))
            if not isinstance(result, dict):
                result = {"ok": False, "error": "同步任务返回了无效结果"}
        except Exception as exc:
            result = {"ok": False, "error": _format_sync_error_message(exc)}
        self._finish(job_id, result)

    def get_status(self, job_id: str = "") -> dict[str, Any]:
        with self._lock:
            target = job_id or self._active_job_id or self._latest_job_id
            return self._snapshot(self._jobs.get(target) if target else None)


FIT_SYNC_JOB_MANAGER = FitSyncJobManager()


# ── Per-Point Distance Attachment (UI Marker Rendering) ──

def _attach_per_point_distance(points: list[dict[str, Any]]) -> None:
    """为轨迹点附加累计距离字段 (dist_km)，仅用于前端 km marker 渲染，不参与 AI 输入。"""
    if not points or len(points) < 2:
        if points:
            points[0]["dist_km"] = 0.0
        return
    import track_backend as _tb
    accum = 0.0
    points[0]["dist_km"] = 0.0
    for i in range(1, len(points)):
        p0, p1 = points[i - 1], points[i]
        try:
            accum += _tb.haversine_m(
                float(p0.get("lat") or 0), float(p0.get("lon") or 0),
                float(p1.get("lat") or 0), float(p1.get("lon") or 0),
            ) / 1000.0
        except (TypeError, ValueError):
            pass
        points[i]["dist_km"] = accum


# ═══════════════════════════════════════════════════════
# AI Snapshot Contract — PURE FACT LAYER (Finalized)
#
# Task 3.4: 不可计算 / 不可扩展 / 不引入推理结构
#
# AI Snapshot 三不原则:
#   1. No reasoning fields
#   2. No derived analytics
#   3. No frontend computed values
#
# 仅允许 DB / resolver 字段。禁止:
#   - track.html calculateStats() 输出
#   - slope_pct / per-point distance / slope
#   - frontend fallback metrics
#   - AI 推理链 / training_load / fatigue model
# ═══════════════════════════════════════════════════════

FORBIDDEN_SNAPSHOT_FIELDS: set[str] = {
    "slope_pct", "pace_calc", "frontend_distance", "ui_only_metric",
    "reasoning_chain", "fatigue_model", "per_point_slope", "derived_grade",
}

_MAX_SNAPSHOT_KEYS = 35  # 增加报告 canonical 字段后从 28 调整


def get_snapshot_field_whitelist() -> set[str]:
    """AI Snapshot 允许字段白名单。任何不在此集合中的字段不得进入 snapshot。"""
    return {
        "activity_id", "sport_type", "sub_sport_type",
        "distance_km", "distance_display",
        "duration_sec", "duration",
        "avg_pace", "avg_pace_display", "pace_unit",
        "avg_hr", "max_hr",
        "calories",
        "elevation_gain_m", "gain_m",
        "max_alt_m",
        "avg_cadence",
        "normalized_power",
        "swolf",
        "tss",
        "start_time", "start_time_utc",
        "start_lat", "start_lon",
        "region",
        "file_path", "filename",
        "source",
        # 以下为可选字段（可能为 None）
        "resting_hr", "hrv_baseline", "vo2max",
        "weight", "height_cm",
        "pb_5km", "pb_10km", "pb_half_marathon", "pb_full_marathon",
        "lactate_threshold_hr", "lactate_threshold_pace",
        "ftp_watts",
        "avg_sleep_hours",
        "longest_hike_km", "longest_run_km", "longest_cycle_km",
        "swimming_100m_pb", "longest_swim_distance_m",
        "race_predict_5k", "race_predict_10k", "race_predict_half", "race_predict_full",
        # v2 新增：运动生理 / 曲线 / 设备上下文
        "hr_decoupling", "hr_curve", "speed_curve", "device_name",
        # v3 新增：报告 canonical 派生指标 (CONTRACT §6)
        "min_alt_m", "total_descent_m", "up_count", "down_count",
        "max_single_climb_m", "difficulty_score", "report_metrics_version",
        # v4 新增：报告坡度 v2 指标
        "avg_grade_pct", "max_slope_pct", "min_slope_pct", "uphill_pct", "downhill_pct",
    }


def validate_ai_snapshot(snapshot: dict[str, Any]) -> None:
    """AI Snapshot Contract Guard — 防污染护栏。
    确保 snapshot 不含任何前端计算字段或推理结构。"""
    for f in FORBIDDEN_SNAPSHOT_FIELDS:
        assert f not in snapshot, f"AI Snapshot pollution detected: {f}"
    assert len(snapshot.keys()) <= _MAX_SNAPSHOT_KEYS, (
        f"AI Snapshot keys exceeded: {len(snapshot.keys())} > {_MAX_SNAPSHOT_KEYS}"
    )
    # 白名单校验 — 防止未知字段进入 AI 输入
    allowed = get_snapshot_field_whitelist()
    for k in snapshot.keys():
        if k not in allowed:
            raise AssertionError(f"AI Snapshot unauthorized field: {k}")
    # 报告 canonical 字段范围校验 (CONTRACT §6)
    _td = snapshot.get("total_descent_m")
    if _td is not None:
        assert _td >= 0, f"total_descent_m must be >= 0, got {_td}"
    _ds = snapshot.get("difficulty_score")
    if _ds is not None:
        assert 0 <= _ds <= 10, f"difficulty_score out of range [0,10]: {_ds}"


def debug_ai_snapshot(snapshot: dict[str, Any]) -> None:
    """开发模式：输出 snapshot 结构校验。确保 keys ≤ {_MAX_SNAPSHOT_KEYS}、无数组、无嵌套。"""
    import sys
    keys = list(snapshot.keys())
    nested = [k for k, v in snapshot.items() if isinstance(v, (list, dict))]
    print(f"[AI SNAPSHOT CONTRACT] keys={keys} count={len(keys)} nested={nested or 'none'}",
          file=sys.stderr, flush=True)


def compute_report_metrics(
    points: list[dict[str, Any]],
    dist_km: float,
    gain_m: float,
) -> dict[str, Any]:
    """报告 canonical 派生指标计算器。
    CONTRACT §2.1 / §6: 所有输出字段来自 FIT records 遍历，存入 DB activities 表。
    前端仅读取 activityMetrics 展示，不得重复计算。
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
        if dalt < -1.5:
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
    result = {
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
    return result


def _compute_grade_metrics(
    points: list[dict[str, Any]],
    dist_km: float,
    gain_m: float,
) -> dict[str, Any]:
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
    if not has_alt:
        return result

    if not has_dist and dist_km and dist_km > 0 and len(points) >= 2:
        n = len(points)
        _enriched = []
        for i, p in enumerate(points):
            _p = dict(p)
            _p["dist_km"] = (dist_km * i) / (n - 1)
            _enriched.append(_p)
        return _compute_grade_metrics(_enriched, dist_km, gain_m)

    if not has_dist:
        return result

    if dist_km > 0 and gain_m is not None:
        avg = (gain_m / (dist_km * 1000.0)) * 100.0
        result["avg_grade_pct"] = round(max(0.0, min(avg, 100.0)), 1)

    window_slopes = []
    window_distances = []
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
        smoothed = []
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


def _decode_points_json_simple(raw: str | None) -> list:
    if not raw or not str(raw).strip():
        return []
    import json
    try:
        data = json.loads(str(raw))
        if isinstance(data, list):
            return data
        return []
    except Exception:
        return []


def rebuild_report_metrics_for_all_activities(dry_run: bool = False) -> dict:
    import sqlite3
    from profile_backend import DB_PATH

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, filename, dist_km, gain_m, track_json, points_json "
            "FROM activities "
            "WHERE deleted_at IS NULL "
            "  AND (track_json IS NOT NULL OR points_json IS NOT NULL) "
            "  AND (min_alt_m IS NULL OR report_metrics_version IS NULL OR report_metrics_version < 2 "
            "       OR avg_grade_pct IS NULL)"
        ).fetchall()

        rebuilt = 0
        skipped_no_points = 0
        errors = 0
        error_details = []

        for row in rows:
            points = _decode_points_json_simple(row["track_json"] or row["points_json"])
            if not points or len(points) < 2:
                skipped_no_points += 1
                continue
            try:
                _dist = float(row["dist_km"] or 0)
                _gain = float(row["gain_m"] or 0)
                _report = compute_report_metrics(points, _dist, _gain)
                if dry_run:
                    rebuilt += 1
                else:
                    conn.execute(
                        "UPDATE activities SET min_alt_m=?, total_descent_m=?, up_count=?, "
                        "down_count=?, max_single_climb_m=?, difficulty_score=?, report_metrics_version=?, "
                        "avg_grade_pct=?, max_slope_pct=?, min_slope_pct=?, uphill_pct=?, downhill_pct=? "
                        "WHERE id=?",
                        (
                            _report.get("min_alt_m"),
                            _report.get("total_descent_m"),
                            _report.get("up_count"),
                            _report.get("down_count"),
                            _report.get("max_single_climb_m"),
                            _report.get("difficulty_score"),
                            _report.get("report_metrics_version"),
                            _report.get("avg_grade_pct"),
                            _report.get("max_slope_pct"),
                            _report.get("min_slope_pct"),
                            _report.get("uphill_pct"),
                            _report.get("downhill_pct"),
                            row["id"],
                        ),
                    )
                    rebuilt += 1
            except Exception as exc:
                errors += 1
                error_details.append(f"id={row['id']} {row['filename']}: {exc}")

        if not dry_run:
            conn.commit()

        return {
            "ok": True,
            "total_candidates": len(rows),
            "rebuilt": rebuilt,
            "skipped_no_points": skipped_no_points,
            "errors": errors,
            "error_details": error_details if errors else None,
            "dry_run": dry_run,
        }
    finally:
        conn.close()


# ── AI Snapshot Builder (唯一合法 AI 输入源) ──
def _build_ai_snapshot(activity_id: int) -> dict[str, Any] | None:
    """AI 语义快照构建器 — 唯一合法 AI 输入源。
    PURE FACT CONTRACT: 所有字段来自 DB/resolver truth。
    禁止前端计算数据、推理结构、per-point 指标进入。"""
    if not activity_id:
        return None
    try:
        conn = sqlite3.connect(profile_backend._DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT sport_type, sub_sport_type, dist_km, duration_sec, avg_hr, max_hr,"
            " gain_m, max_alt_m, avg_pace, distance, duration,"
            " calories, avg_cadence, normalized_power, swolf,"
            " tss, start_time, start_lat, start_lon, region, file_path, filename,"
            " hr_decoupling, hr_curve, speed_curve, device_name,"
            " min_alt_m, total_descent_m, up_count, down_count, max_single_climb_m, difficulty_score, report_metrics_version,"
            " avg_grade_pct, max_slope_pct, min_slope_pct, uphill_pct, downhill_pct"
            " FROM activities WHERE id = ? AND deleted_at IS NULL",
            (activity_id,),
        ).fetchone()
        conn.close()
        if not row:
            return None
        d = dict(row)

        sub_sport = str(d.get("sub_sport_type") or "").lower()
        pace_unit = "/100m" if sub_sport in ("lap_swimming", "open_water") else "/km"

        # ── Display Fields (纯格式化，不重新计算) ──
        raw_dist_km = d.get("dist_km")
        if raw_dist_km is not None:
            dist_km = _safe_float(raw_dist_km)
        else:
            raw_dist_m = d.get("distance")
            dist_km = round(_safe_float(raw_dist_m) / 1000.0, 2) if raw_dist_m is not None else None

        if dist_km is not None and dist_km > 0:
            if dist_km < 0.1:
                distance_display = f"{int(dist_km * 1000)}m"
            else:
                distance_display = f"{round(dist_km, 2):.2f}km"
        else:
            distance_display = "-- km"

        raw_avg_pace = d.get("avg_pace")
        avg_pace = _safe_float(raw_avg_pace) if raw_avg_pace is not None else None
        if avg_pace is not None and avg_pace > 0:
            pm = int(avg_pace // 60)
            ps = int(avg_pace % 60)
            avg_pace_display = f"{pm}'{ps:02d}''{pace_unit}"
        else:
            avg_pace_display = f"-- {pace_unit}"

        snapshot = {
            "activity_id": activity_id,
            "sport_type": d.get("sport_type"),
            "sub_sport_type": d.get("sub_sport_type"),
            "distance_km": dist_km,
            "distance_display": distance_display,
            "duration_sec": d.get("duration_sec") or d.get("duration"),
            "avg_pace": avg_pace,
            "avg_pace_display": avg_pace_display,
            "pace_unit": pace_unit,
            "avg_hr": d.get("avg_hr"),
            "max_hr": d.get("max_hr"),
            "calories": d.get("calories"),
            "elevation_gain_m": d.get("gain_m"),
            "max_alt_m": d.get("max_alt_m"),
            "avg_cadence": d.get("avg_cadence"),
            "normalized_power": d.get("normalized_power"),
            "swolf": d.get("swolf"),
            "tss": d.get("tss"),
            "start_time": d.get("start_time"),
            "start_lat": d.get("start_lat"),
            "start_lon": d.get("start_lon"),
            "region": d.get("region"),
            "source": "DB Canonical / Resolver Truth",
            "hr_decoupling": d.get("hr_decoupling"),
            "hr_curve": d.get("hr_curve"),
            "speed_curve": d.get("speed_curve"),
            "device_name": d.get("device_name"),
            "min_alt_m": d.get("min_alt_m"),
            "total_descent_m": d.get("total_descent_m"),
            "up_count": d.get("up_count"),
            "down_count": d.get("down_count"),
            "max_single_climb_m": d.get("max_single_climb_m"),
            "difficulty_score": d.get("difficulty_score"),
            "report_metrics_version": d.get("report_metrics_version"),
            "avg_grade_pct": d.get("avg_grade_pct"),
            "max_slope_pct": d.get("max_slope_pct"),
            "min_slope_pct": d.get("min_slope_pct"),
            "uphill_pct": d.get("uphill_pct"),
            "downhill_pct": d.get("downhill_pct"),
        }

        validate_ai_snapshot(snapshot)
        debug_ai_snapshot(snapshot)
        return snapshot
    except Exception:
        return None


def _build_ai_snapshot_block(snapshot: dict[str, Any] | None) -> str:
    """将 AI snapshot 格式化为 LLM system prompt 可嵌入的文本块。"""
    if not snapshot:
        return ""
    lines = [
        "【运动语义快照 — 系统真值（非前端计算）】",
        f"- 运动类型: {snapshot.get('sport_type') or '-'} / {snapshot.get('sub_sport_type') or '-'}",
        f"- 距离: {snapshot.get('distance_display') or '-'} ({snapshot.get('distance_km')} km)",
        f"- 用时: {snapshot.get('duration_sec')} 秒",
        f"- 配速: {snapshot.get('avg_pace_display') or '-'} ({snapshot.get('pace_unit') or '-'})",
        f"- 平均心率: {snapshot.get('avg_hr')} bpm / 最大: {snapshot.get('max_hr')} bpm",
        f"- 卡路里: {snapshot.get('calories')}",
        f"- 累计爬升: {snapshot.get('elevation_gain_m')} m / 最高海拔: {snapshot.get('max_alt_m')} m",
    ]
    if snapshot.get("normalized_power") is not None:
        lines.append(f"- NP: {snapshot.get('normalized_power')} W")
    if snapshot.get("swolf") is not None:
        lines.append(f"- SWOLF: {snapshot.get('swolf')}")
    if snapshot.get("avg_cadence") is not None:
        lines.append(f"- 平均步频/踏频: {snapshot.get('avg_cadence')}")
    if snapshot.get("tss") is not None:
        lines.append(f"- TSS: {snapshot.get('tss')}")
    if snapshot.get("region"):
        lines.append(f"- 区域: {snapshot.get('region')}")
    lines.append("")
    lines.append("【重要】以上数值来自系统数据库（唯一真值），优先于轨迹明细表中的任何前端推算值。")
    return "\n".join(lines)


def _build_risk_assessment_messages(snapshot: dict[str, Any], weather_context: dict[str, Any] | None) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": llm_backend.build_risk_assessment_system_prompt(snapshot, weather_context),
        },
        {
            "role": "user",
            "content": llm_backend.build_risk_assessment_user_prompt(),
        },
    ]


# ═══════════════════════════════════════════════════════
# Insight Engine — Insight Builder + History Window
# Task 3.3: Schema-Driven AI Sports Insight
# ═══════════════════════════════════════════════════════

def _get_history_window(activity_id: int, sport_type: str, limit: int = 10) -> list[dict[str, Any]]:
    """获取同类型运动最近 N 条历史记录摘要，用于趋势对比。"""
    try:
        con_status = f"id != {activity_id} AND deleted_at IS NULL"
        conn = sqlite3.connect(profile_backend._DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""SELECT id, sport_type, sub_sport_type, dist_km, duration_sec,
                avg_hr, max_hr, avg_pace, gain_m, start_time
            FROM activities
            WHERE {con_status}
              AND sport_type = ?
            ORDER BY start_time DESC
            LIMIT ?""",
            (sport_type, limit),
        ).fetchall()
        conn.close()
        history = []
        for r in rows:
            d = dict(r)
            dur_sec = d.get("duration_sec") or 0
            dur_min = int(dur_sec // 60) if dur_sec else 0
            dist = d.get("dist_km") or 0
            avg_pace = d.get("avg_pace")
            pace_str = ""
            if avg_pace and avg_pace > 0:
                pm = int(avg_pace // 60)
                ps = int(avg_pace % 60)
                pace_str = f"{pm}'{ps:02d}\"/km"
            history.append({
                "id": d.get("id"),
                "dist_km": round(float(dist), 2) if dist else 0,
                "duration_min": dur_min,
                "avg_hr": d.get("avg_hr"),
                "max_hr": d.get("max_hr"),
                "avg_pace_display": pace_str or "--",
                "gain_m": round(float(d.get("gain_m") or 0)),
                "start_time": str(d.get("start_time") or ""),
            })
        return history
    except Exception:
        return []


def _build_history_block(history: list[dict[str, Any]]) -> str:
    """将历史记录格式化为 prompt 可嵌入文本。
       HISTORY IS CONTEXT REFERENCE ONLY — 非分析数据源。AI 不得基于历史做趋势建模。"""
    if not history:
        return ""
    lines = ["【历史同类运动 — 背景参考（context reference only，非分析数据源）】"]
    for i, h in enumerate(history[:8]):
        lines.append(
            f"  #{i + 1}: {h.get('dist_km')}km / {h.get('duration_min')}min / "
            f"配速 {h.get('avg_pace_display')} / HR {h.get('avg_hr')}-{h.get('max_hr')} / "
            f"爬升 {h.get('gain_m')}m ({h.get('start_time')})"
        )
    lines.append("  以上为背景信息，仅用于理解运动习惯，不得用于建模或趋势推导。")
    return "\n".join(lines)


def _build_ai_insight(activity_id: int) -> dict[str, Any]:
    """AI 运动洞察构建器。
    链路: DB → Snapshot → Prompt → LLM → normalize → UI
    """
    snapshot = _build_ai_snapshot(activity_id)
    if not snapshot:
        return llm_backend._empty_insight("未找到活动记录")

    sport_type = str(snapshot.get("sport_type") or "unknown")
    mode = llm_backend._insight_mode_sport(sport_type)

    # 历史对比窗口
    history = _get_history_window(activity_id, sport_type, limit=10)
    history_block = _build_history_block(history)

    # 构建 prompt
    system_prompt = llm_backend._build_insight_system_prompt(snapshot, mode, history_block)
    user_prompt = llm_backend._build_insight_user_prompt()

    return {
        "snapshot": snapshot,
        "mode": mode,
        "history": history,
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
    }


class Api:
    """pywebview js_api：轨迹文件、导出、大模型（OpenAI 兼容）等。"""

    SYSTEM_INSTRUCTION = "__SYSTEM_INSTRUCTION__"
    REPORT_TERRAIN = "__REPORT_TERRAIN__"
    REPORT_PERSONALIZED = "__REPORT_PERSONALIZED__"
    REPORT_INSIGHT = "__REPORT_INSIGHT__"
    REPORT_RISK_ASSESSMENT = "__REPORT_RISK_ASSESSMENT__"

    def __init__(self) -> None:
        self._track_points: list | None = None
        self._track_placemarks: list | None = None
        self._track_filename: str = ""
        self._track_weather: dict[str, Any] | None = None
        self._chat_messages: list[dict[str, str]] = []
        self._session_id = "session_" + uuid.uuid4().hex[:16]
        self._window = None
        self._frontend_ready = False
        self._pending_track_notifications: list[tuple[str, int]] = []
        self._notification_lock = threading.Lock()
        self._watch_service: FITFolderWatchService | None = None
        self._ai_snapshot: dict[str, Any] | None = None
        self._profile_startup_sync_scheduled = False
        self._region_enrichment_timer: threading.Timer | None = None
        self._region_enrichment_active = False

    def on_loaded(self) -> None:
        """页面加载完成后显示窗口，解决白屏感。"""
        import webview
        if webview.windows:
            webview.windows[0].show()

    def bind_window(self, window) -> None:
        self._window = window

    def set_watch_service(self, watch_service: FITFolderWatchService) -> None:
        self._watch_service = watch_service

    def _restart_watch_service(self) -> None:
        if self._watch_service is None:
            return
        self._watch_service.restart()

    def notify_frontend_ready(self) -> dict:
        self._frontend_ready = True
        self._flush_pending_track_notifications()
        self._schedule_profile_startup_sync()
        self._schedule_region_enrichment()
        return {"ok": True}

    def _schedule_region_enrichment(self) -> None:
        if self._region_enrichment_active:
            return
        if self._region_enrichment_timer is not None:
            self._region_enrichment_timer.cancel()
        self._region_enrichment_active = True

        def _on_complete(result: dict) -> None:
            self._region_enrichment_active = False
            self._region_enrichment_timer = None
            if result.get("processed", 0) > 0:
                self._dispatch_region_enrichment_complete(result)

        def _start():
            profile_backend.start_region_enrichment_background(on_complete=_on_complete)

        timer = threading.Timer(3, _start)
        timer.daemon = True
        self._region_enrichment_timer = timer
        timer.start()

    def _dispatch_region_enrichment_complete(self, result: dict) -> None:
        if not self._window:
            return
        payload = {
            "success": result.get("success", 0),
            "failed": result.get("failed", 0),
            "cache_hits": result.get("cache_hits", 0),
        }
        js_code = f"window.onRegionEnrichmentComplete && window.onRegionEnrichmentComplete({json.dumps(payload)})"
        try:
            self._window.evaluate_js(js_code)
            logger.info("[REGION] 地区补全完成通知已发送: success=%d, failed=%d", payload["success"], payload["failed"])
        except Exception as exc:
            logger.exception("[REGION] 地区补全完成通知失败: %s", exc)

    def _schedule_profile_startup_sync(self) -> None:
        if self._profile_startup_sync_scheduled:
            return
        self._profile_startup_sync_scheduled = True
        timer = threading.Timer(5, self.startup_sync_check)
        timer.daemon = True
        timer.start()

    def _dispatch_profile_sync_event(self, event_name: str, payload: dict) -> None:
        if not self._window:
            return
        js_code = f"window.onProfileSyncEvent && window.onProfileSyncEvent({json.dumps(event_name)}, {json.dumps(payload, ensure_ascii=False, default=str)})"
        try:
            self._window.evaluate_js(js_code)
        except Exception as exc:
            logger.exception("画像同步通知发送失败: %s", exc)

    def startup_sync_check(self) -> dict:
        try:
            conn = profile_backend.check_garmin_connection()
            if not conn.get("connected"):
                message = str(conn.get("message") or "Garmin 连接未配置")
                profile_backend.mark_profile_sync_blocked(message)
                result = {"ok": False, "blocked": True, "message": message, **profile_backend.get_profile_sync_metadata()}
                self._dispatch_profile_sync_event("profile_sync_blocked", result)
                return result
            if not profile_backend.is_sync_needed_today():
                result = {"ok": True, "already_synced": True, "message": "今天已同步", **profile_backend.get_profile_sync_metadata()}
                self._dispatch_profile_sync_event("profile_sync_complete", result)
                return result
            if profile_backend.should_skip_profile_sync_for_cooldown():
                result = {"ok": False, "cooldown": True, "message": "上次同步失败，冷却中", **profile_backend.get_profile_sync_metadata()}
                self._dispatch_profile_sync_event("profile_sync_complete", result)
                return result
            result = profile_backend.fetch_mcp_persona("garmin", trigger_type="startup", check_connection=False)
            if result.get("ok"):
                prof = profile_backend.get_profile()
                result.update({"profile": prof.to_dict(), **profile_backend.get_profile_sync_metadata()})
            else:
                result.update(profile_backend.get_profile_sync_metadata())
            self._dispatch_profile_sync_event("profile_sync_complete", result)
            return result
        except Exception as e:
            logger.exception("启动画像同步检查失败")
            message = str(e)
            profile_backend.mark_profile_sync_failed(message)
            result = {"ok": False, "error": message, **profile_backend.get_profile_sync_metadata()}
            self._dispatch_profile_sync_event("profile_sync_complete", result)
            return result

    def diagnose_watch_service(self) -> dict:
        """诊断文件监听服务状态，便于排查自动同步问题。"""
        ws = self._watch_service
        if not ws:
            return {"ok": False, "error": "Watch service 未初始化"}
        return {
            "ok": True,
            "watch_path": ws._watch_path,
            "observer_alive": ws._observer.is_alive() if ws._observer else False,
            "staging_thread_alive": ws._staging_poll_thread.is_alive() if ws._staging_poll_thread else False,
            "staging_queue_size": len(ws._staging_queue),
            "staging_queue": list(ws._staging_queue.keys()),
            "synced_signatures_count": len(ws._synced_signatures),
            "frontend_ready": self._frontend_ready,
            "window_bound": self._window is not None,
            "pending_notifications": len(self._pending_track_notifications),
        }

    def _flush_pending_track_notifications(self) -> None:
        with self._notification_lock:
            pending = list(self._pending_track_notifications)
            self._pending_track_notifications.clear()
        if pending:
            logger.info("[NOTIFY] 刷新 %d 条挂起通知", len(pending))
        for file_path, activity_id in pending:
            self._dispatch_new_track_notification(file_path, activity_id)

    def _dispatch_new_track_notification(self, file_path: str, activity_id: int = 0) -> None:
        if not self._window:
            logger.warning("[NOTIFY] _window 为 None，无法发送 JS 通知")
            return
        js_code = f"window.onNewTrackDetected({json.dumps(file_path)}, {int(activity_id or 0)})"
        try:
            self._window.evaluate_js(js_code)
            logger.info("[NOTIFY] JS 通知已发送: file=%s, activity_id=%s", file_path, activity_id)
        except Exception as exc:
            logger.exception("[NOTIFY] JS 通知发送失败: %s, error=%s", file_path, exc)

    def notify_new_track_detected(self, file_path: str, activity_id: int = 0) -> None:
        normalized = str(Path(file_path).expanduser().resolve())
        with self._notification_lock:
            if not self._frontend_ready or self._window is None:
                logger.info("[NOTIFY] 前端未就绪，通知挂起: %s (ready=%s, window=%s)", normalized, self._frontend_ready, self._window is not None)
                self._pending_track_notifications.append((normalized, int(activity_id or 0)))
                return
        logger.info("[NOTIFY] 通知前端: file=%s, activity_id=%s", normalized, activity_id)
        self._dispatch_new_track_notification(normalized, int(activity_id or 0))

    def _new_session_id(self) -> None:
        self._session_id = "session_" + uuid.uuid4().hex[:16]

    def sync_track_context(self, payload_json: str) -> dict:
        """前端完成渲染后同步轨迹上下文。
           AI Input Governance (Task 3.4 finalized):
           - 仅 activity_id 进入 AI snapshot，前端 points/placemarks 仅用于轨迹详情表
           - snapshot 由 _build_ai_snapshot() 从 DB 构建，不依赖任何前端计算值
           - 前端 track.html 角色: Visualization Layer ONLY"""
        try:
            obj = json.loads(payload_json)
        except json.JSONDecodeError:
            return _api_error(API_CODE_VALIDATION, "JSON 无效")
        self._track_points = obj.get("points") or []       # 仅用于轨迹详情表，不进入 AI
        self._track_placemarks = obj.get("placemarks") or []  # 仅用于轨迹详情表，不进入 AI
        self._track_filename = str(obj.get("filename") or "轨迹")
        self._track_weather = obj.get("weather") if isinstance(obj.get("weather"), dict) else None
        self._chat_messages = []
        self._new_session_id()
        # AI Input Governance: 从 DB 构建语义快照，取代前端计算数据
        # CONTRACT: _ai_snapshot 是 call_llm 中 AI 相关请求的唯一合法数据源
        activity_id = obj.get("activity_id") or obj.get("activityId")
        if activity_id:
            self._ai_snapshot = _build_ai_snapshot(int(activity_id))
        else:
            self._ai_snapshot = None
        return _api_success()

    def reset_llm_session(self) -> dict:
        self._chat_messages = []
        self._new_session_id()
        return _api_success()

    def get_llm_config(self) -> dict:
        cfg = llm_backend.redact_llm_config(llm_backend.load_llm_config())
        cfg["local_dir"] = TRACKS_DIR
        cfg["workspace_track_path"] = TRACKS_DIR
        cfg["workspace_track_abs_path"] = TRACKS_DIR
        return _api_success(cfg)

    def save_llm_config(self, provider: str, url: str, model: str, api_key: str, agent_id: str = "", watch_brand: str = "", local_dir: str = "") -> dict:
        """【防御加锁】拒绝外部越权直调。核心持久化已全面收拢至 test_llm_config 网关中。"""
        print("[API 警告] 外部代码尝试越权直接保存配置，已被安全网关拦截并重定向。")
        return _api_error(API_CODE_AUTH_REQUIRED, "Deprecated: 前端保存已被废弃，请直接使用唯一验证测试通道 test_llm_config")

    def get_config(self) -> dict:
        """安全读取全局配置文件，供前端配置页使用。"""
        try:
            config = resolve_workspace_track_dir(auto_recover=True)
            if not config.get("ok"):
                return _api_error(API_CODE_FILE_IO, str(config.get("error") or "工作区配置不可用"), config)
            return _api_success({
                "config_path": config.get("config_path"),
                "workspace_track_path": config.get("workspace_track_path"),
                "workspace_track_abs_path": config.get("workspace_track_abs_path"),
            })
        except Exception:
            logger.exception("get_config failed")
            return _api_error(API_CODE_INTERNAL, "读取配置失败")

    def save_config(self, new_config_dict: dict) -> dict:
        """保存全局配置。workspace_track_path 由受控工作区锁定，不可变更。"""
        try:
            current = load_application_config()
            payload = dict(current)
            if isinstance(new_config_dict, dict):
                payload.update(new_config_dict)
            payload["workspace_track_path"] = TRACKS_DIR
            payload["workspace_track_abs_path"] = TRACKS_DIR
            backup_path = backup_application_config("save_config", current)
            config = persist_application_config(payload)
            append_application_audit("save_config", {"backup_path": backup_path})
            return _api_success({
                "config_path": config.get("config_path"),
                "workspace_track_path": config.get("workspace_track_path"),
                "workspace_track_abs_path": config.get("workspace_track_abs_path"),
            })
        except Exception:
            logger.exception("save_config failed")
            return _api_error(API_CODE_FILE_IO, "保存配置失败")

    def test_llm_config(self, provider: str, url: str, model: str, api_key: str, agent_id: str = "") -> dict:
        """【测试即保存网关-稳定性加固版】严格实行先测试、后持久化策略，保障状态机最终一致性。"""
        try:
            # 1. 先发起真实的接口网络活性探测（防污染核心）
            text = llm_backend.test_llm_connection(
                provider=provider,
                url=url,
                model=model,
                api_key=api_key,
                agent_id=agent_id,
            )

            # 2. 只有网络探测 100% 成功通车，才执行无感持久化落盘，硬锁隐藏轨迹工作区
            llm_backend.save_llm_config(
                provider=provider,
                url=url,
                model=model,
                api_key=api_key,
                agent_id=agent_id,
                watch_brand="",
                local_dir=TRACKS_DIR
            )
            print(f"[Config 治理] 验证成功，大模型存储规范已安全固化对齐: {TRACKS_DIR}")

            # 3. 健全状态机：丰富持久化配置中的活性追踪字典
            config = load_application_config()
            config["llm_check_passed"] = True
            config["last_gateway_ok"] = True
            config["last_success_time"] = time.time()
            persist_application_config(config)

            return _api_success({"message": text})
        except Exception as e:
            # 连通失败：不破坏原有旧配置，但将当前网关可用状态即时标记为假（失效回滚）
            try:
                config = load_application_config()
                config["last_gateway_ok"] = False
                persist_application_config(config)
            except Exception:
                pass
            logger.warning("test_llm_config failed: %s", e)
            return _api_error(API_CODE_EXTERNAL_SERVICE, "大模型网关连通失败")

    def call_llm(self, prompt: str, sport_type: str = "hiking") -> dict:
        """对话或路书。AI 数据边界 (Task 3.4):
           - AI 输入: _ai_snapshot (DB truth) → ai_block (system prompt)
           - 轨迹详情表: _track_points (仅作为 CSV table 供参考，不参与 AI 分析)
           - 禁止: 前端 calculateStats 输出、per-point slope、request.get_json() metrics"""
        cfg = llm_backend.load_llm_config()
        url = (cfg.get("url") or "").strip()
        if not url:
            return {"ok": False, "error": "API 接口地址为空，请在设置中配置"}

        provider = str(cfg.get("provider") or "local_mcp")
        model = str(cfg.get("model") or "openclaw").strip()
        api_key = str(cfg.get("api_key") or "")
        agent_id = str(cfg.get("agent_id") or "")
        sid = self._session_id

        # AI 数据边界（契约总纲 §2.4）：
        #   AI 输入仅来自 _ai_snapshot (DB truth)
        #   _track_points / _track_placemarks 仅用于 UI 可视化，不进入 AI
        ai_block = _build_ai_snapshot_block(self._ai_snapshot)
        fn = self._track_filename or "轨迹"

        try:
            if prompt == self.REPORT_TERRAIN:
                sys_b = llm_backend.build_base_system_block(
                    sport_type=sport_type,
                    provider=provider,
                    track_filename=fn,
                    points=[],          # 契约束定: AI 不消费前端 points
                    placemarks=[],      # 契约束定: AI 不消费前端 placemarks
                    weather_context=None,  # 契约束定: 气象数据由 snapshot 提供
                    ai_snapshot_block=ai_block,
                )
                usr = llm_backend.build_report_user_prompt_terrain(sport_type)
                messages = [{"role": "system", "content": sys_b}, {"role": "user", "content": usr}]
                text = llm_backend.chat_completions(
                    url=url,
                    api_key=api_key,
                    model=model,
                    messages=messages,
                    session_id=sid,
                    agent_id=agent_id,
                )
                self._chat_messages = []
                self._new_session_id()
                return {"ok": True, "content": text}

            if prompt == self.REPORT_PERSONALIZED:
                sys_b = llm_backend.build_base_system_block(
                    sport_type=sport_type,
                    provider=provider,
                    track_filename=fn,
                    points=[],          # 契约束定: AI 不消费前端 points
                    placemarks=[],      # 契约束定: AI 不消费前端 placemarks
                    weather_context=None,  # 契约束定: 气象数据由 snapshot 提供
                    ai_snapshot_block=ai_block,
                )
                usr = llm_backend.build_report_user_prompt_personalized(sport_type, provider)
                messages = [{"role": "system", "content": sys_b}, {"role": "user", "content": usr}]
                text = llm_backend.chat_completions(
                    url=url,
                    api_key=api_key,
                    model=model,
                    messages=messages,
                    session_id=sid,
                    agent_id=agent_id,
                )
                self._chat_messages = []
                self._new_session_id()
                return {"ok": True, "content": text}

            if prompt == self.REPORT_INSIGHT:
                if not self._ai_snapshot:
                    return {"ok": True, "insight": llm_backend._empty_insight("请先加载活动轨迹")}
                insight_data = _build_ai_insight(self._ai_snapshot.get("activity_id"))
                sys_b = insight_data["system_prompt"]
                usr = insight_data["user_prompt"]
                messages = [{"role": "system", "content": sys_b}, {"role": "user", "content": usr}]
                text = llm_backend.chat_completions(
                    url=url,
                    api_key=api_key,
                    model=model,
                    messages=messages,
                    session_id=sid,
                    agent_id=agent_id,
                )
                self._chat_messages = []
                self._new_session_id()
                insight = llm_backend.normalize_insight_json(text)
                return {
                    "ok": True,
                    "insight": insight,
                    "history": insight_data.get("history") or [],
                    "snapshot": insight_data.get("snapshot") or {},
                }

            if prompt == self.REPORT_RISK_ASSESSMENT:
                if not self._ai_snapshot:
                    return {"ok": True, "risk_assessment": llm_backend.empty_risk_assessment("请先加载活动轨迹")}
                messages = _build_risk_assessment_messages(self._ai_snapshot, self._track_weather)
                text = llm_backend.chat_completions(
                    url=url,
                    api_key=api_key,
                    model=model,
                    messages=messages,
                    session_id=sid,
                    agent_id=agent_id,
                )
                self._chat_messages = []
                self._new_session_id()
                risk_assessment = llm_backend.normalize_risk_assessment_json(text)
                return {"ok": True, "risk_assessment": risk_assessment}

            if prompt == self.SYSTEM_INSTRUCTION:
                storage_rule = (
                    "从现在开始，所有从佳明(Garmin)下载的FIT文件，必须严格遵守以下规范：\n\n"
                    "FIT文件存放路径规范\n"
                    "下载后得到的是ZIP文件，必须解压\n"
                    "解压后得到的FIT文件必须放到以下目录：\n"
                    f"{TRACKS_DIR}\n"
                    "文件名由 Garmin-stats skill 的 download_fit.py 自动命名为 {活动标题}_{活动ID}.fit\n"
                    "解压并移动完成后，删除原始ZIP文件\n"
                    "如果目标目录不存在，先创建它\n"
                    "切勿擅自改变路径或跳过解压步骤\n"
                    "请记住这条规范，并将它写入你的长期记忆，标题为「FIT文件存放路径规范」。\n"
                    "以后每次下载FIT文件都严格按照这个路径存放，不要擅自改变路径或跳过解压步骤。\n"
                    "确认后，仅回复OK"
                )
                text = llm_backend.chat_completions(
                    url=url,
                    api_key=api_key,
                    model=model,
                    messages=[
                        {"role": "system", "content": storage_rule},
                        {"role": "user", "content": "确认收到以上指令，仅回复OK。"},
                    ],
                    session_id=sid,
                    agent_id=agent_id,
                )
                return {"ok": True, "content": text}

            user_text = prompt
            if not self._chat_messages:
                sys_c = llm_backend.build_chat_system_block(
                    sport_type=sport_type,
                    provider=provider,
                    track_filename=fn,
                    # CONTRACT §4.5: 通用对话路径 AI 仅消费 snapshot，禁止注入全量 points/placemarks
                    points=[],
                    placemarks=[],
                    weather_context=self._track_weather,
                    ai_snapshot_block=ai_block,
                )
                self._chat_messages = [{"role": "system", "content": sys_c}]
            self._chat_messages.append({"role": "user", "content": user_text})
            try:
                text = llm_backend.chat_completions(
                    url=url,
                    api_key=api_key,
                    model=model,
                    messages=list(self._chat_messages),
                    session_id=sid,
                    agent_id=agent_id,
                )
            except Exception:
                if self._chat_messages and self._chat_messages[-1].get("role") == "user":
                    self._chat_messages.pop()
                raise
            self._chat_messages.append({"role": "assistant", "content": text})
            return {"ok": True, "content": text}

        except Exception as e:
            return {"ok": False, "error": str(e)}

    def debug_snapshot(self, activity_id: int) -> dict:
        """Task 4.1: Snapshot Viewer Debug API。
           返回 AI 实际消费的唯一数据源 —— 与 _build_ai_snapshot() 完全一致。
           禁止额外计算、禁止修改 MetricsResolver、禁止返回前端计算字段。"""
        try:
            snapshot = _build_ai_snapshot(int(activity_id))
            if not snapshot:
                return {"ok": False, "error": "未找到活动记录"}
            return {
                "ok": True,
                "snapshot": snapshot,
                "meta": {
                    "version": "1.0",
                    "source": "_build_ai_snapshot (resolver truth + DB canonical)",
                    "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                },
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def pick_and_parse_track(self) -> dict:
        import webview
        from webview import FileDialog

        from track_backend import parse_track_file

        if not webview.windows:
            return {"ok": False, "error": "窗口未就绪"}

        paths = webview.windows[0].create_file_dialog(
            FileDialog.OPEN,
            file_types=("Track files (*.fit;*.gpx;*.kml)",),
        )
        if not paths:
            return {"ok": False, "cancelled": True}

        src = paths[0] if isinstance(paths, (list, tuple)) else paths
        try:
            data = parse_track_file(src)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        data["weather"] = _infer_weather_from_track_data(data)
        result = {"ok": True, "filename": Path(src).name, "data": data, "_src_path": src}
        return result

    def parse_track_at_path(self, file_path: str) -> dict:
        from track_backend import parse_track_file

        try:
            data = parse_track_file(file_path)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        data["weather"] = _infer_weather_from_track_data(data)
        return {"ok": True, "filename": Path(file_path).name, "data": data}

    def select_directory(self) -> dict:
        import webview
        from webview import FileDialog

        if not webview.windows:
            return {"ok": False, "error": "窗口未就绪"}

        try:
            paths = webview.windows[0].create_file_dialog(FileDialog.FOLDER)
        except OSError as e:
            return {"ok": False, "error": str(e)}

        if not paths:
            return {"ok": False, "cancelled": True}

        path = paths[0] if isinstance(paths, (list, tuple)) else paths
        return {"ok": True, "path": str(path)}

    def save_text_file(self, suggested_filename: str, content: str) -> dict:
        import webview
        from webview import FileDialog

        if not webview.windows:
            return {"ok": False, "error": "窗口未就绪"}

        win = webview.windows[0]
        suffix = Path(suggested_filename).suffix.lower()
        if suffix == ".gpx":
            file_types = ("GPX (*.gpx)",)
        elif suffix == ".kml":
            file_types = ("KML (*.kml)",)
        else:
            file_types = ("所有文件 (*.*)",)

        try:
            paths = win.create_file_dialog(
                FileDialog.SAVE,
                save_filename=suggested_filename,
                file_types=file_types,
            )
        except OSError as e:
            return {"ok": False, "error": str(e)}

        if not paths:
            return {"ok": False, "cancelled": True}

        dest = paths[0] if isinstance(paths, (list, tuple)) else paths
        try:
            Path(dest).write_text(content, encoding="utf-8")
        except OSError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "path": str(dest)}

    def get_user_profile(self) -> dict:
        prof = profile_backend.get_profile()
        zones = profile_backend.compute_hrr_zones(
            prof.resting_hr or 60, prof.max_hr or 190
        )
        cached = profile_backend.read_local_profile()
        metadata = profile_backend.get_profile_sync_metadata()
        return {
            "ok": True,
            "profile": prof.to_dict(),
            "hrr_zones": zones,
            **metadata,
            "cache_info": {
                "has_cached": cached is not None,
            },
        }

    def get_rolling_radar_metrics(self, sport_type: str = "running") -> dict:
        """滚动聚合雷达指标：90天极值 + 最近5次均值 + 42天累积 + HRV基线 + RadarScoreEngine 评分。"""
        try:
            metrics = _rolling_aggregate_radar_metrics(sport_type)
            return {"ok": True, "metrics": metrics}
        except Exception as e:
            logger.exception("滚动聚合雷达指标失败")
            return {
                "ok": False,
                "error": str(e),
                "metrics": {
                    "ctl": 0,
                    "hrv": 60,
                    "decoupling": 0,
                    "vam": 0,
                    "threshold_hr": 0,
                    "anaerobic_peak": 0,
                    "radar": {"type": sport_type, "dimensions": []},
                },
            }

    def save_user_profile(self, data: dict) -> dict:
        try:
            profile_backend.upsert_profile(data)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True}

    def fetch_mcp_persona(self, platform: str) -> dict:
        result = profile_backend.fetch_mcp_persona(platform, trigger_type="manual")
        if result.get("ok"):
            prof = profile_backend.get_profile()
            zones = profile_backend.compute_hrr_zones(
                prof.resting_hr or 60, prof.max_hr or 190
            )
            return {"ok": True, "profile": prof.to_dict(), "hrr_zones": zones, **profile_backend.get_profile_sync_metadata()}
        return result

    def get_activity_history(self) -> dict:
        """返回按时间倒序的历史运动记录列表。"""
        try:
            history = profile_backend.get_activity_history(limit=50)
            return {"ok": True, "history": history}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_test_bypass_daily_sync_limit(self) -> dict:
        return {"ok": True, "enabled": profile_backend.get_test_bypass_daily_sync_limit()}

    def set_test_bypass_daily_sync_limit(self, enabled: bool) -> dict:
        profile_backend.set_test_bypass_daily_sync_limit(enabled)
        return {"ok": True, "enabled": profile_backend.get_test_bypass_daily_sync_limit()}

    def check_daily_sync_status(self) -> dict:
        needs = profile_backend.is_sync_needed_today()
        state = profile_backend.read_sync_state()
        return {
            "ok": True,
            "needs_sync": needs,
            "last_sync_date": state.get("last_sync_date"),
            "last_sync_time": state.get("last_sync_time"),
            **profile_backend.get_profile_sync_metadata(),
        }

    def silent_fetch_mcp_persona(self, platform: str) -> dict:
        needs = profile_backend.is_sync_needed_today()
        if not needs:
            cached = profile_backend.read_local_profile()
            return {"ok": True, "already_synced": True, "has_cached": cached is not None, **profile_backend.get_profile_sync_metadata()}
        result = profile_backend.fetch_mcp_persona(platform, trigger_type="background")
        if result.get("ok"):
            prof = profile_backend.get_profile()
            return {"ok": True, "already_synced": False, "profile": prof.to_dict(), "has_cached": True, **profile_backend.get_profile_sync_metadata()}
        return {"ok": True, "already_synced": False, "error": result.get("error"), "has_cached": False, **profile_backend.get_profile_sync_metadata()}

    def _workspace_track_dir(self) -> str:
        config = init_application_config()
        return str(config.get("workspace_track_abs_path") or "").strip()

    def _build_activity_list_item(self, row: dict) -> dict:
        display_type = _resolve_display_sport_type(row.get("sport_type"), row.get("sub_sport_type"))
        distance_km = _safe_float(row.get("distance") if row.get("distance") is not None else row.get("dist_km"))
        duration_sec = _safe_int(row.get("duration") if row.get("duration") is not None else row.get("duration_sec"))
        # LEGACY (DO NOT EXTEND)
        # 未来将迁移至 MetricsResolver
        avg_pace = row.get("avg_pace")
        if avg_pace is None and distance_km > 0 and duration_sec > 0:
            avg_pace = round(duration_sec / distance_km, 2)
        # LEGACY (DO NOT EXTEND)
        # 未来将迁移至 MetricsResolver
        avg_pace_sec = _safe_int(avg_pace) if avg_pace is not None else None
        sub_sport = str(row.get("sub_sport_type") or "").strip()
        pace_unit = "/100m" if sub_sport in ("lap_swimming", "open_water") else "/km"
        if avg_pace_sec and avg_pace_sec > 0:
            m, s = int(avg_pace_sec // 60), int(round(avg_pace_sec % 60))
            avg_pace_display = f"{m}'{s:02d}''{pace_unit}"
        else:
            avg_pace_display = f"-- {pace_unit}"
        # LEGACY (DO NOT EXTEND)
        # 未来将迁移至 MetricsResolver
        raw_distance_m = distance_km * 1000
        if raw_distance_m <= 5000:
            distance_display = f"{int(raw_distance_m)}m"
        else:
            distance_display = f"{round(distance_km, 2):.2f}km"
        avg_hr = _safe_int(row.get("avg_hr")) or None
        max_hr = _safe_int(row.get("max_hr")) or None
        calories = row.get("calories")
        normalized_power = row.get("normalized_power")
        swolf_raw = row.get("swolf")
        swolf = None
        swolf_subtitle = None
        if display_type == "swimming" or display_type == "stand_up_paddleboarding":
            if sub_sport == "lap_swimming":
                swolf = swolf_raw
                swolf_subtitle = "平均SWOLF"
            else:
                swolf = swolf_raw
                swolf_subtitle = "平均划水距离"
        display_filename = str(row.get("filename") or row.get("file_name") or "")
        title = _clean_fit_activity_title(row.get("file_name") or row.get("filename"), display_filename)
        region_status = str(row.get("region_status") or "").strip()
        region_raw = str(row.get("region_display") or row.get("region") or "").strip()
        if not region_raw:
            if region_status == "pending":
                region_raw = "待补全"
            elif region_status == "none":
                region_raw = "室内运动"
            elif region_status == "failed":
                region_raw = "未知地点"
        if region_raw and region_raw.startswith("台湾"):
            region_raw = "台湾地区"
        timestamp = row.get("start_time") or row.get("start_time_utc") or row.get("updated_at")
        try:
            dt = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")) if timestamp else None
            date_label = dt.strftime("%Y-%m-%d") if dt else "--"
        except Exception:
            date_label = str(timestamp or "--")

        suppress = IRRELEVANT_LIST_METRICS.get(display_type, frozenset())
        if "distance" in suppress:
            distance_km = None
            distance_display = "/"
        if "pace" in suppress:
            avg_pace_sec = None
            avg_pace_display = "/"

        return {
            "id": int(row.get("id") or 0),
            "file_name": display_filename,
            "filename": display_filename,
            "title": title,
            "title_source": str(row.get("title_source") or ""),
            "start_time": row.get("start_time"),
            "start_time_utc": row.get("start_time_utc"),
            "date_label": date_label,
            "sport_type": str(row.get("sport_type") or "unknown"),
            "sub_sport_type": str(row.get("sub_sport_type") or "unknown"),
            "display_sport_type": display_type,
            "distance_km": round(distance_km, 2) if distance_km is not None else None,
            "duration_sec": duration_sec,
            "avg_pace_sec": avg_pace_sec,
            "avg_pace_display": avg_pace_display,
            "distance_display": distance_display,
            "avg_hr": avg_hr,
            "max_hr": max_hr,
            "calories": _safe_int(calories),
            "gain_m": round(_safe_float(row.get("gain_m")), 1),
            "normalized_power": _safe_float(normalized_power) if normalized_power is not None else None,
            "swolf": round(_safe_float(swolf), 1) if swolf is not None else None,
            "swolf_subtitle": swolf_subtitle,
            "file_path": str(row.get("file_path") or ""),
            "region": region_raw,
            "region_display": region_raw,
            "region_status": region_status,
            "device_name": str(row.get("device_name") or "").strip(),
            "start_lat": _safe_float(row.get("start_lat")) or None,
            "start_lon": _safe_float(row.get("start_lon")) or None,
            "weather": _decode_weather_json(row.get("weather_json")),
            "hr_curve": _safe_json_list(row.get("hr_curve")),
            "speed_curve": _safe_json_list(row.get("speed_curve")),
            "shadow_diff": _decode_weather_json(row.get("shadow_diff_json")) if row.get("shadow_diff_json") else {},
            "has_track": bool(row.get("has_track")),
            "has_local_file": bool(str(row.get("file_path") or "").strip() and os.path.exists(str(row.get("file_path") or "").strip())),
        }

    def _fetch_activity_row(self, activity_id: int) -> dict | None:
        ensure_activity_sync_schema()
        conn = profile_backend._conn()
        try:
            row = conn.execute(
                """
                SELECT *,
                       COALESCE(track_json, points_json) AS merged_track_json
                FROM activities
                WHERE id = ? AND deleted_at IS NULL
                """,
                (activity_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def _load_activity_placemarks(self, activity_id: int) -> list[dict[str, Any]]:
        ensure_activity_sync_schema()
        if not _safe_int(activity_id):
            return []
        conn = profile_backend._conn()
        try:
            rows = conn.execute(
                """
                SELECT cp_id, name, type, icon, gpx_sym, lon, lat, alt, dist_km, source, created_at, updated_at
                FROM activity_placemarks
                WHERE activity_id = ?
                ORDER BY COALESCE(dist_km, 999999999), id
                """,
                (_safe_int(activity_id),),
            ).fetchall()
            return [
                {
                    "id": str(row["cp_id"] or ""),
                    "cp_id": str(row["cp_id"] or ""),
                    "name": str(row["name"] or ""),
                    "type": str(row["type"] or "custom"),
                    "icon": str(row["icon"] or "📍"),
                    "gpx_sym": str(row["gpx_sym"] or "Waypoint"),
                    "lon": _safe_float(row["lon"]),
                    "lat": _safe_float(row["lat"]),
                    "alt": _safe_float(row["alt"]),
                    "dist": _safe_float(row["dist_km"]),
                    "dist_km": _safe_float(row["dist_km"]),
                    "source": str(row["source"] or "user"),
                    "created_at": _safe_int(row["created_at"]),
                    "updated_at": _safe_int(row["updated_at"]),
                }
                for row in rows
            ]
        finally:
            conn.close()

    def get_activity_placemarks(self, activity_id: int) -> dict:
        row = self._fetch_activity_row(_safe_int(activity_id))
        if not row:
            return _api_error(API_CODE_NOT_FOUND, "未找到该活动记录", {"placemarks": []})
        placemarks = self._load_activity_placemarks(_safe_int(activity_id))
        return _api_success({"placemarks": placemarks, "count": len(placemarks)})

    def sync_activity_placemarks(self, activity_id: int, placemarks: list[dict] | str | None = None) -> dict:
        activity_id = _safe_int(activity_id)
        if not activity_id:
            return _api_error(API_CODE_VALIDATION, "activity_id 无效", {"count": 0})
        if not self._fetch_activity_row(activity_id):
            return _api_error(API_CODE_NOT_FOUND, "未找到该活动记录", {"count": 0})
        if isinstance(placemarks, str):
            try:
                placemark_items = json.loads(placemarks)
            except json.JSONDecodeError:
                return _api_error(API_CODE_VALIDATION, "CP 点数据不是有效 JSON", {"count": 0})
        else:
            placemark_items = placemarks or []
        if not isinstance(placemark_items, list):
            return _api_error(API_CODE_VALIDATION, "CP 点数据必须是数组", {"count": 0})

        now_ms = int(time.time() * 1000)
        clean_items: list[dict[str, Any]] = []
        for item in placemark_items:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source") or "user")
            if source != "user":
                continue
            cp_id = str(item.get("id") or item.get("cp_id") or "").strip()
            name = str(item.get("name") or "").strip()
            lon = item.get("lon")
            lat = item.get("lat")
            if not cp_id or not name or lon is None or lat is None:
                continue
            clean_items.append(
                {
                    "cp_id": cp_id[:128],
                    "name": name[:120],
                    "type": str(item.get("type") or "custom")[:32],
                    "icon": str(item.get("icon") or "📍")[:16],
                    "gpx_sym": str(item.get("gpx_sym") or "Waypoint")[:64],
                    "lon": _safe_float(lon),
                    "lat": _safe_float(lat),
                    "alt": _safe_float(item.get("alt")),
                    "dist_km": _safe_float(item.get("dist_km") if item.get("dist_km") is not None else item.get("dist")),
                    "source": "user",
                    "created_at": _safe_int(item.get("created_at")) or now_ms,
                    "updated_at": now_ms,
                }
            )

        conn = profile_backend._conn()
        try:
            conn.execute("DELETE FROM activity_placemarks WHERE activity_id = ? AND source = 'user'", (activity_id,))
            conn.executemany(
                """
                INSERT INTO activity_placemarks
                    (activity_id, cp_id, name, type, icon, gpx_sym, lon, lat, alt, dist_km, source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        activity_id,
                        item["cp_id"],
                        item["name"],
                        item["type"],
                        item["icon"],
                        item["gpx_sym"],
                        item["lon"],
                        item["lat"],
                        item["alt"],
                        item["dist_km"],
                        item["source"],
                        item["created_at"],
                        item["updated_at"],
                    )
                    for item in clean_items
                ],
            )
            conn.commit()
            return _api_success({"count": len(clean_items), "placemarks": self._load_activity_placemarks(activity_id)})
        except Exception:
            conn.rollback()
            logger.exception("sync_activity_placemarks failed activity_id=%s", activity_id)
            return _api_error(API_CODE_DB, "CP 点同步失败", {"count": 0})
        finally:
            conn.close()

    def _sync_local_fit_files_impl(self, progress_callback=None) -> dict:
        """按配置文件中的工作目录增量同步 FIT 文件到 activities 表。"""
        try:
            ensure_activity_sync_schema()
            config = resolve_workspace_track_dir(auto_recover=True)
            source_dir = str(config.get("workspace_track_abs_path") or "")
            source_status = dict(config.get("workspace_track_status") or {})
            base = Path(source_dir) if source_status.get("exists") and source_status.get("is_dir") else Path(TRACKS_DIR)
            os.makedirs(str(base), exist_ok=True)
            started_at = time.perf_counter()
            fit_files = _walk_fit_files(base)
            disk_paths = {str(path.expanduser().resolve()) for path in fit_files}
            total = len(fit_files)
            logger.info("FIT 同步开始: base=%s, 有效文件数=%s", str(base), total)

            # 预加载 DB 中已入库文件索引，用于快速跳过未变更文件
            conn = profile_backend._conn()
            try:
                existing_index = _load_existing_file_index(conn)
            finally:
                conn.close()

            # 提前过滤出真正需要处理的新增/变更文件
            pending_files: list[Path] = []
            pre_skipped = 0
            for fit_path in fit_files:
                resolved = str(fit_path.expanduser().resolve())
                existing = existing_index.get(resolved)
                if existing and _is_file_unchanged(fit_path, existing):
                    pre_skipped += 1
                else:
                    pending_files.append(fit_path)

            inserted = 0
            updated = 0
            skipped = 0
            errors: list[dict[str, str]] = []

            _emit_sync_progress(
                progress_callback,
                stage="scanning",
                current=0,
                total=total,
                inserted=inserted,
                updated=updated,
                skipped=pre_skipped,
                current_file="",
                message=f"已找到 {total} 个 FIT 文件，其中 {len(pending_files)} 个需要同步...",
                errors=[],
            )

            for index, fit_path in enumerate(pending_files, start=1):
                file_name = fit_path.name
                _emit_sync_progress(
                    progress_callback,
                    stage="parsing",
                    current=index,
                    total=len(pending_files),
                    inserted=inserted,
                    updated=updated,
                    skipped=skipped + pre_skipped,
                    current_file=file_name,
                    message=f"正在解析 {index}/{len(pending_files)}: {file_name}",
                    errors=errors[-5:],
                )
                try:
                    activity = _parse_fit_activity_for_sync(fit_path)
                    _emit_sync_progress(
                        progress_callback,
                        stage="writing",
                        current=index,
                        total=len(pending_files),
                        inserted=inserted,
                        updated=updated,
                        skipped=skipped + pre_skipped,
                        current_file=file_name,
                        message=f"正在写入数据库 {index}/{len(pending_files)}: {file_name}",
                        errors=errors[-5:],
                    )
                    write_res = _persist_sync_activity(activity)
                    if write_res.get("op") == "updated":
                        updated += 1
                    elif write_res.get("op") == "skipped":
                        skipped += 1
                    else:
                        inserted += 1
                except Exception as exc:
                    logger.exception("解析/写入 FIT 文件异常: %s", file_name)
                    skipped += 1
                    errors.append(
                        {
                            "file_name": file_name,
                            "error": _format_sync_error_message(exc),
                        }
                    )

                _emit_sync_progress(
                    progress_callback,
                    stage="running",
                    current=index,
                    total=len(pending_files),
                    inserted=inserted,
                    updated=updated,
                    skipped=skipped + pre_skipped,
                    current_file=file_name,
                    message=f"已处理 {index}/{len(pending_files)} 个 FIT 文件",
                    errors=errors[-5:],
                )

            elapsed_sec = round(time.perf_counter() - started_at, 2)
            removed = self._mark_missing_activity_files_deleted(str(base), disk_paths)
            result = {
                "ok": True,
                "source_dir": str(base),
                "source_status": source_status,
                "recovered": config.get("workspace_track_recovered"),
                "scanned": total,
                "inserted": inserted,
                "updated": updated,
                "skipped": skipped + pre_skipped,
                "removed": removed,
                "errors": errors,
                "elapsed_sec": elapsed_sec,
                "message": f"同步完成：扫描 {total} 个 FIT 文件（跳过 {pre_skipped} 个未变更），新增 {inserted} 条，更新 {updated} 条，跳过 {skipped} 条，标记删除 {removed} 条，用时 {elapsed_sec:.2f} 秒。",
            }
            _emit_sync_progress(
                progress_callback,
                stage="completed",
                current=total,
                total=total,
                inserted=inserted,
                updated=updated,
                skipped=skipped + pre_skipped,
                current_file="",
                message=result["message"],
                errors=errors[-5:],
            )
            return result
        except Exception as exc:
            friendly_error = _format_sync_error_message(exc)
            logger.exception("FIT 同步失败: %s", friendly_error)
            _emit_sync_progress(
                progress_callback,
                stage="error",
                current=0,
                total=0,
                inserted=0,
                updated=0,
                skipped=0,
                current_file="",
                message=friendly_error,
                errors=[{"file_name": "", "error": friendly_error}],
            )
            return {"ok": False, "error": friendly_error, "message": friendly_error}

    def sync_local_fit_files(self) -> dict:
        return self._sync_local_fit_files_impl()

    def _mark_missing_activity_files_deleted(self, source_dir: str, disk_paths: set[str]) -> int:
        source_dir = str(source_dir or "").rstrip("/\\")
        if not source_dir:
            return 0
        ensure_activity_sync_schema()
        conn = profile_backend._conn()
        try:
            rows = conn.execute(
                """
                SELECT id, file_path
                FROM activities
                WHERE deleted_at IS NULL
                  AND COALESCE(file_path, '') != ''
                  AND file_path LIKE ?
                """,
                (source_dir + os.sep + "%",),
            ).fetchall()
            missing_ids = [int(row["id"]) for row in rows if str(row["file_path"] or "") not in disk_paths]
            if not missing_ids:
                return 0
            placeholders = ",".join("?" * len(missing_ids))
            conn.execute(
                f"UPDATE activities SET deleted_at = datetime('now'), updated_at = datetime('now') WHERE id IN ({placeholders})",
                missing_ids,
            )
            conn.commit()
            return len(missing_ids)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def delete_activities(self, activity_ids: list[int] | None = None, confirm_token: str = "") -> dict:
        """批量硬删除：强制确保 FIT 文件与数据库同步。"""
        ensure_activity_sync_schema()
        raw_ids = [int(item) for item in (activity_ids or []) if _safe_int(item)]
        if not raw_ids:
            return _api_error(
                API_CODE_VALIDATION,
                "未选择记录",
                {"missing_ids": [], "file_errors": [], "skipped_unsafe_paths": []},
            )
        ids = sorted(set(raw_ids))
        expected_token = _delete_confirm_token(ids)
        audit_id = uuid.uuid4().hex[:12]
        if str(confirm_token or "") != expected_token:
            logger.warning("delete_activities rejected audit_id=%s reason=invalid_confirm ids=%s", audit_id, ids)
            return _api_error(
                API_CODE_AUTH_REQUIRED,
                "删除确认参数无效",
                {
                    "audit_id": audit_id,
                    "expected_confirm_token": expected_token,
                    "missing_ids": [],
                    "file_errors": [],
                    "skipped_unsafe_paths": [],
                },
            )
        conn = profile_backend._conn()
        file_deleted = 0
        file_errors: list[dict[str, str]] = []
        skipped_unsafe_paths: list[dict[str, str]] = []
        missing_file_paths: list[dict[str, str]] = []
        try:
            rows = conn.execute(
                "SELECT id, file_path FROM activities WHERE id IN ({})".format(",".join("?" * len(ids))),
                ids,
            ).fetchall()
            if not rows:
                return _api_error(
                    API_CODE_NOT_FOUND,
                    "未找到记录",
                    {"audit_id": audit_id, "missing_ids": ids, "file_errors": [], "skipped_unsafe_paths": []},
                )

            existing_ids = [int(row["id"]) for row in rows]
            missing_ids = sorted(set(ids) - set(existing_ids))
            controlled_dir = Path(TRACKS_DIR).expanduser().resolve()
            deletable_ids: list[int] = []
            for row in rows:
                row_id = int(row["id"])
                fp = str(row["file_path"] or "").strip()
                if not fp:
                    deletable_ids.append(row_id)
                    continue
                try:
                    path = Path(fp).expanduser().resolve()
                    if not _is_path_under_dir(path, controlled_dir):
                        skipped_unsafe_paths.append({"id": str(row_id), "file_path": fp, "reason": "outside_tracks_dir"})
                        continue
                    if not path.exists():
                        missing_file_paths.append({"id": str(row_id), "file_path": fp})
                        deletable_ids.append(row_id)
                        continue
                    if not path.is_file():
                        skipped_unsafe_paths.append({"id": str(row_id), "file_path": fp, "reason": "not_file"})
                        continue
                    path.unlink()
                    file_deleted += 1
                    deletable_ids.append(row_id)
                except Exception as exc:
                    file_errors.append({"id": str(row_id), "file_path": fp, "error": str(exc)})

            if deletable_ids:
                conn.execute(
                    "DELETE FROM activity_placemarks WHERE activity_id IN ({})".format(",".join("?" * len(deletable_ids))),
                    deletable_ids,
                )
                conn.execute(
                    "DELETE FROM activities WHERE id IN ({})".format(",".join("?" * len(deletable_ids))),
                    deletable_ids,
                )
            conn.commit()
            logger.info(
                "delete_activities audit_id=%s requested=%s deleted=%s files_deleted=%s missing=%s unsafe=%s file_errors=%s",
                audit_id,
                ids,
                deletable_ids,
                file_deleted,
                missing_ids,
                skipped_unsafe_paths,
                file_errors,
            )
            result = {
                "audit_id": audit_id,
                "deleted": len(deletable_ids),
                "files_deleted": file_deleted,
                "missing_ids": missing_ids,
                "missing_file_paths": missing_file_paths,
                "file_errors": file_errors,
                "skipped_unsafe_paths": skipped_unsafe_paths,
            }
            if missing_ids:
                result["missing_ids"] = missing_ids
            return _api_success(result)
        except Exception:
            conn.rollback()
            logger.exception("delete_activities failed audit_id=%s ids=%s", audit_id, ids)
            return _api_error(
                API_CODE_DB,
                "删除活动失败",
                {
                    "audit_id": audit_id,
                    "files_deleted": file_deleted,
                    "file_errors": file_errors,
                    "skipped_unsafe_paths": skipped_unsafe_paths,
                },
            )
        finally:
            conn.close()

    def safe_extract_zip(self, zf, target_dir, password=None):
        target_root = Path(target_dir).expanduser().resolve()
        members = zf.infolist()
        report = {"extracted": [], "skipped": [], "errors": [], "total_uncompressed": 0}
        if len(members) > ZIP_MAX_MEMBERS:
            report["errors"].append({"error": "ZIP 成员数量超过上限", "code": API_CODE_VALIDATION, "limit": ZIP_MAX_MEMBERS, "actual": len(members)})
            return report
        for member in members:
            entry_name = member.filename
            resolved = Path(target_root / entry_name).resolve()
            if not _is_path_under_dir(resolved, target_root):
                logging.getLogger("track_import").warning(f"拒绝路径穿越: {entry_name}")
                report["errors"].append({"file": entry_name, "error": "拒绝路径穿越", "code": API_CODE_VALIDATION})
                continue
            if member.is_dir():
                resolved.mkdir(parents=True, exist_ok=True)
                continue
            if Path(entry_name).suffix.lower() not in ZIP_ALLOWED_SUFFIXES:
                report["skipped"].append({"file": entry_name, "reason": "unsupported_extension"})
                continue
            if member.file_size > ZIP_MAX_MEMBER_UNCOMPRESSED_BYTES:
                report["errors"].append({"file": entry_name, "error": "ZIP 成员解压大小超过上限", "code": API_CODE_VALIDATION, "limit": ZIP_MAX_MEMBER_UNCOMPRESSED_BYTES, "actual": member.file_size})
                continue
            if int(report["total_uncompressed"]) + member.file_size > ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES:
                report["errors"].append({"file": entry_name, "error": "ZIP 总解压大小超过上限", "code": API_CODE_VALIDATION, "limit": ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES})
                break
            resolved.parent.mkdir(parents=True, exist_ok=True)
            pwd = password.encode("utf-8") if isinstance(password, str) else password
            written = 0
            with zf.open(member, pwd=pwd) as src, open(resolved, "wb") as dst:
                while True:
                    chunk = src.read(ZIP_COPY_CHUNK_BYTES)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > ZIP_MAX_MEMBER_UNCOMPRESSED_BYTES:
                        dst.close()
                        resolved.unlink(missing_ok=True)
                        report["errors"].append({"file": entry_name, "error": "ZIP 成员流式读取超过上限", "code": API_CODE_VALIDATION, "limit": ZIP_MAX_MEMBER_UNCOMPRESSED_BYTES})
                        break
                    dst.write(chunk)
            if written > ZIP_MAX_MEMBER_UNCOMPRESSED_BYTES:
                continue
            os.chmod(str(resolved), member.external_attr >> 16 if member.external_attr else 0o644)
            report["total_uncompressed"] = int(report["total_uncompressed"]) + written
            report["extracted"].append(str(resolved))
        return report


    def unique_fit_path(self, target_dir, name):
        safe_name = os.path.basename(name)
        if not safe_name:
            safe_name = "untitled.fit"
        candidate = os.path.join(target_dir, safe_name)
        if not os.path.exists(candidate):
            return candidate
        base, ext = os.path.splitext(safe_name)
        counter = 1
        while True:
            candidate = os.path.join(target_dir, f"{base}-{counter}{ext}")
            if not os.path.exists(candidate):
                return candidate
            counter += 1


    def batch_import_tracks(self, file_paths: list[str]) -> dict:
        """多模态批量导入：FIT 直接复制，ZIP 解压到 IMPORTS_DIR 后归集到 TRACKS_DIR。"""
        if not file_paths:
            return _api_error(API_CODE_VALIDATION, "未提供文件路径", {"imported": [], "errors": []})

        # 临时挂起自动监听服务，防止引发双重导入灾难
        if self._watch_service:
            self._watch_service.suspended = True

        imported: list[str] = []
        errors: list[dict] = []

        try:
            for fp in file_paths:
                try:
                    src = Path(fp).expanduser().resolve()
                    if not src.is_file():
                        errors.append({"file": fp, "error": "文件不存在"})
                        continue

                    if src.suffix.lower() == ".fit":
                        dst = Path(self.unique_fit_path(TRACKS_DIR, src.name))
                        shutil.copy2(str(src), str(dst))
                        # 手动调用单入口同步解析
                        res = _sync_single_fit_file(dst)
                        if res.get("ok"):
                            imported.append(str(dst))

                    elif src.suffix.lower() == ".zip":
                        with zipfile.ZipFile(str(src), "r") as zf:
                            extract_report = self.safe_extract_zip(zf, IMPORTS_DIR)
                        for err in extract_report.get("errors") or []:
                            errors.append({"file": fp, **err})
                        for skipped in extract_report.get("skipped") or []:
                            errors.append({"file": fp, **skipped})
                        for fit_path in extract_report.get("extracted") or []:
                            fit = Path(fit_path).expanduser().resolve()
                            if fit.suffix.lower() not in ZIP_ALLOWED_SUFFIXES or not _is_path_under_dir(fit, Path(IMPORTS_DIR).expanduser().resolve()):
                                errors.append({"file": str(fit), "error": "ZIP 解压结果不在受控导入目录或不是 FIT 文件", "code": API_CODE_VALIDATION})
                                continue
                            dst = Path(self.unique_fit_path(TRACKS_DIR, fit.name))
                            shutil.move(str(fit), str(dst))
                            res = _sync_single_fit_file(dst)
                            if res.get("ok"):
                                imported.append(str(dst))
                    else:
                        errors.append({"file": fp, "error": "不支持的文件格式，仅支持 .fit 和 .zip", "code": API_CODE_UNSUPPORTED_FILE})
                except Exception as exc:
                    errors.append({"file": fp, "error": str(exc)})

            return _api_success({"imported": imported, "errors": errors if errors else None})

        finally:
            # 无论批量导入成功与否，无条件解除挂起锁，恢复 Watchdog 的日常静默监听
            if self._watch_service:
                self._watch_service.suspended = False

    def api_force_rebuild_radar_data(self) -> dict:
        """【P1 异步清洗网关】允许用户手动一键强刷全库雷达指标，安全更新至 METRICS_VERSION 3。"""
        try:
            def _async_run():
                print("[API] 收到全量数据清洗指令，正在后台启动清洗 worker...")
                res = force_rebuild_all_records()
                print(f"[API] 后台全量清洗完成: {res}")
                try:
                    _report_result = rebuild_report_metrics_for_all_activities(dry_run=False)
                    print(f"[API] 报告指标回填完成: {_report_result}")
                except Exception:
                    pass

            threading.Thread(target=_async_run, daemon=True, name="metrics-rebuild-worker").start()
            return _api_success({"message": "全量雷达指标重建任务已在后台异步启动，请稍后刷新页面查看成果。"})
        except Exception:
            logger.exception("api_force_rebuild_radar_data failed")
            return _api_error(API_CODE_INTERNAL, "全量雷达指标重建启动失败")

    def check_first_run_status(self) -> dict:
        """判定首次运行状态与网关实时活性健康状态。"""
        try:
            config = load_application_config()

            # 首次运行强锁判定：从未成功调通过本地大模型，则属于绝对首次使用
            is_first_run = not bool(config.get("llm_check_passed", False))

            # 实时可用性判定（供前端右上角/顶部轻提示渲染，不强锁系统）
            last_gateway_ok = bool(config.get("last_gateway_ok", False))
            last_success_time = config.get("last_success_time", 0)

            return _api_success({
                "is_first_run": is_first_run,
                "last_gateway_ok": last_gateway_ok,
                "last_success_time": last_success_time,
                "default_tracks_dir": TRACKS_DIR
            })
        except Exception:
            logger.exception("check_first_run_status failed")
            return _api_error(API_CODE_INTERNAL, "首次运行状态检查失败", {"is_first_run": True, "last_gateway_ok": False})

    def start_sync_local_fit_files(self) -> dict:
        return FIT_SYNC_JOB_MANAGER.start(
            lambda progress_callback: self._sync_local_fit_files_impl(progress_callback=progress_callback)
        )

    def get_sync_local_fit_files_status(self, job_id: str = "") -> dict:
        return FIT_SYNC_JOB_MANAGER.get_status(job_id)

    def _query_activity_list_records(self, sport_filter: str = "all") -> tuple[str, list[dict[str, Any]], list[str]]:
        try:
            ensure_activity_sync_schema()
            config = resolve_workspace_track_dir(auto_recover=True)
            source_dir = str(config.get("workspace_track_abs_path") or "")
            sport_filter = str(sport_filter or "all").strip() or "all"

            display_sql = _activity_display_sql()
            where_parts: list[str] = []
            params: list[Any] = []
            source_where, source_params = _source_scope_filter_clause(source_dir)
            if source_where:
                where_parts.append(source_where.replace("WHERE ", "", 1))
                params.extend(source_params)
            if sport_filter != "all":
                where_parts.append(f"{display_sql} = ?")
                params.append(sport_filter)
            where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

            conn = profile_backend._conn()
            try:
                _cleanup_invalid_activity_types(conn)
                conn.commit()
                all_rows = conn.execute(
                    f"""
                    SELECT id,
                           COALESCE(file_name, filename) AS file_name,
                           filename,
                           title,
                           title_source,
                           start_time,
                           start_time_utc,
                           sport_type,
                           sub_sport_type,
                           COALESCE(distance, dist_km) AS distance,
                           COALESCE(duration, duration_sec) AS duration,
                           avg_pace,
                           avg_hr,
                           max_hr,
                           calories,
                           gain_m,
                           normalized_power,
                           swolf,
                           device_name,
                           file_path,
                           start_lat,
                           start_lon,
                           region,
                           region_city,
                           region_country,
                           region_display,
                           region_status,
                           region_error,
                           region_updated_at,
                           region_attempt_count,
                           weather_json,
                           updated_at,
                           hr_curve,
                           speed_curve,
                           shadow_diff_json,
                           CASE WHEN COALESCE(track_json, points_json, '') != '' THEN 1 ELSE 0 END AS has_track
                    FROM activities
                    {where_sql}
                    ORDER BY COALESCE(start_time, updated_at) DESC, id DESC
                    """,
                    tuple(params),
                ).fetchall()

                type_rows = conn.execute(
                    """
                    SELECT sport_type, sub_sport_type
                    FROM activities
                    WHERE COALESCE(sport_type, '') != '' AND deleted_at IS NULL
                    """
                ).fetchall()
            finally:
                conn.close()

            deduped_rows = _dedupe_activity_rows([dict(row) for row in all_rows])
            records = [self._build_activity_list_item(row) for row in deduped_rows]
            activity_types = sorted(
                {
                    _resolve_display_sport_type(row["sport_type"], row["sub_sport_type"])
                    for row in type_rows
                    if _resolve_display_sport_type(row["sport_type"], row["sub_sport_type"]) != "unknown"
                },
                key=lambda item: (SPORT_HUB_TYPE_ORDER.get(item, 99), item),
            )
            return source_dir, records, activity_types
        except Exception as e:
            raise RuntimeError(str(e)) from e

    def get_activity_list_snapshot(self, sport_filter: str = "all") -> dict:
        """返回完整活动记录快照，供前端本地分页与筛选使用。"""
        try:
            source_dir, records, activity_types = self._query_activity_list_records(sport_filter)
            gain_eligible = OUTDOOR_LAND_GAIN_TYPES - {"treadmill_running"}
            swim_types = {"swimming", "stand_up_paddleboarding"}
            power_types = POWER_ELIGIBLE_TYPES
            has_gain = False
            has_swim = False
            has_power = False
            for r in records:
                st = r.get("display_sport_type") or r.get("sport_type") or ""
                if not has_gain and st in gain_eligible:
                    has_gain = True
                if not has_swim and st in swim_types:
                    has_swim = True
                if not has_power and st in power_types:
                    has_power = True
                if has_gain and has_swim and has_power:
                    break
            dynamic_columns = []
            if has_gain:
                dynamic_columns.append("gain")
            if has_swim:
                dynamic_columns.append("swolf")
            if has_power:
                dynamic_columns.append("np")
            return _api_success({
                "source_dir": source_dir,
                "total": len(records),
                "activity_types": activity_types,
                "page_sizes": SPORT_HUB_PAGE_SIZES,
                "records": records,
                "dynamic_columns": dynamic_columns,
            })
        except Exception:
            logger.exception("get_activity_list_snapshot failed")
            return _api_error(API_CODE_DB, "活动列表快照查询失败")

    def get_activity_list(self, page: int = 1, page_size: int = 20, sport_filter: str = "all") -> dict:
        """后端分页返回活动记录基础字段。"""
        try:
            page = max(1, _safe_int(page, 1))
            requested_page_size = _safe_int(page_size, 20)
            page_size = requested_page_size if requested_page_size in SPORT_HUB_PAGE_SIZES else 20
            offset = (page - 1) * page_size
            db_rows, total_count = profile_backend.get_activity_list_filtered(offset, page_size, sport_filter)
            deduped_rows = _dedupe_activity_rows(db_rows)
            records = [self._build_activity_list_item(row) for row in deduped_rows]
            total_pages = max(1, (total_count + page_size - 1) // page_size)
            page = min(page, total_pages)

            conn = profile_backend._conn()
            try:
                type_rows = conn.execute(
                    """
                    SELECT sport_type, sub_sport_type
                    FROM activities
                    WHERE COALESCE(sport_type, '') != ''
                      AND deleted_at IS NULL
                      AND COALESCE(source_type, 'fit_sdk') = 'fit_sdk'
                      AND COALESCE(is_mock, 0) = 0
                    """
                ).fetchall()
            finally:
                conn.close()
            activity_types = sorted(
                {
                    _resolve_display_sport_type(row["sport_type"], row["sub_sport_type"])
                    for row in type_rows
                    if _resolve_display_sport_type(row["sport_type"], row["sub_sport_type"]) != "unknown"
                },
                key=lambda item: (SPORT_HUB_TYPE_ORDER.get(item, 99), item),
            )

            return _api_success({
                "page": page,
                "page_size": page_size,
                "total": total_count,
                "total_pages": total_pages,
                "activity_types": activity_types,
                "page_sizes": SPORT_HUB_PAGE_SIZES,
                "records": records,
            })
        except Exception:
            logger.exception("get_activity_list failed")
            return _api_error(API_CODE_DB, "活动列表查询失败")

    def get_sport_hub_activity_page(self, page: int = 1, page_size: int = 10, sport_filter: str = "all") -> dict:
        """个人运动数据 - 后端分页活动记录。"""
        try:
            page = max(1, _safe_int(page, 1))
            requested_page_size = _safe_int(page_size, 10)
            page_size = requested_page_size if requested_page_size in SPORT_HUB_PAGE_SIZES else 10
            offset = (page - 1) * page_size
            db_rows, total_count = profile_backend.get_activity_list_filtered(offset, page_size, sport_filter)
            deduped_rows = _dedupe_activity_rows(db_rows)
            records = [self._build_activity_list_item(row) for row in deduped_rows]
            total_pages = max(1, (total_count + page_size - 1) // page_size)
            page = min(page, total_pages)

            conn = profile_backend._conn()
            try:
                type_rows = conn.execute(
                    """
                    SELECT sport_type, sub_sport_type
                    FROM activities
                    WHERE COALESCE(sport_type, '') != ''
                      AND deleted_at IS NULL
                      AND COALESCE(source_type, 'fit_sdk') = 'fit_sdk'
                      AND COALESCE(is_mock, 0) = 0
                    """
                ).fetchall()
            finally:
                conn.close()
            activity_types = sorted(
                {
                    _resolve_display_sport_type(row["sport_type"], row["sub_sport_type"])
                    for row in type_rows
                    if _resolve_display_sport_type(row["sport_type"], row["sub_sport_type"]) != "unknown"
                },
                key=lambda item: (SPORT_HUB_TYPE_ORDER.get(item, 99), item),
            )

            return _api_success({
                "page": page,
                "page_size": page_size,
                "total": total_count,
                "total_pages": total_pages,
                "activity_types": activity_types,
                "page_sizes": SPORT_HUB_PAGE_SIZES,
                "records": records,
            })
        except Exception:
            logger.exception("get_sport_hub_activity_page failed")
            return _api_error(API_CODE_DB, "个人运动数据分页查询失败")

    def get_activity_detail(self, activity_id: int) -> dict:
        """返回单条活动的详情数据，包含缩略图与统计信息。"""
        try:
            row = self._fetch_activity_row(_safe_int(activity_id))
            if not row:
                return _api_error(API_CODE_NOT_FOUND, "未找到该活动记录")
            record = _build_record_from_row(self, row, 0)
            return _api_success({"record": record})
        except Exception:
            logger.exception("get_activity_detail failed activity_id=%s", activity_id)
            return _api_error(API_CODE_DB, "活动详情查询失败")

    def load_activity_track(self, activity_id: int) -> dict:
        """优先从 SQLite 的 track_json 读取轨迹，支持源文件已删除时复盘。
           Task 3.2: 同时返回权威 metrics，前端不再计算 distance/pace/elevation。"""
        try:
            row = self._fetch_activity_row(_safe_int(activity_id))
            if not row:
                return {"ok": False, "error": "未找到该活动记录"}

            def _build_activity_canonical(r: dict) -> dict:
                sub_sport = str(r.get("sub_sport_type") or "").lower()
                pace_unit = "/100m" if sub_sport in ("lap_swimming", "open_water") else "/km"
                dist_km = _safe_float(r.get("dist_km"))
                if dist_km == 0.0:
                    dist_m = _safe_float(r.get("distance"))
                    if dist_m and dist_m > 0:
                        dist_km = round(dist_m / 1000.0, 2)
                duration_sec = _safe_int(r.get("duration_sec") or r.get("duration"))
                gain_m = _safe_float(r.get("gain_m"))
                avg_hr = _safe_int(r.get("avg_hr")) or None
                max_hr = _safe_int(r.get("max_hr")) or None
                calories = _safe_int(r.get("calories")) or None
                avg_pace = _safe_float(r.get("avg_pace")) or None

                if dist_km and dist_km > 0:
                    if dist_km < 0.1:
                        distance_display = f"{int(dist_km * 1000)}m"
                    else:
                        distance_display = f"{round(dist_km, 2):.2f}km"
                else:
                    distance_display = "-- km"

                if avg_pace and avg_pace > 0:
                    pm = int(avg_pace // 60)
                    ps = int(avg_pace % 60)
                    avg_pace_display = f"{pm}'{ps:02d}''{pace_unit}"
                else:
                    avg_pace_display = f"-- {pace_unit}"

                return {
                    "id": _safe_int(r.get("id")),
                    "sport_type": str(r.get("sport_type") or "unknown"),
                    "sub_sport_type": str(r.get("sub_sport_type") or "unknown"),
                    "region": str(r.get("region") or "").strip(),
                    "weather": _decode_weather_json(r.get("weather_json")),
                    "dist_km": dist_km,
                    "distance_display": distance_display,
                    "duration_sec": duration_sec,
                    "gain_m": gain_m,
                    "max_alt_m": _safe_float(r.get("max_alt_m")),
                    "avg_hr": avg_hr,
                    "max_hr": max_hr,
                    "calories": calories,
                    "avg_pace": avg_pace,
                    "avg_pace_display": avg_pace_display,
                    "pace_unit": pace_unit,
                    "start_time": str(r.get("start_time") or ""),
                    "min_alt_m": _safe_float(r.get("min_alt_m")),
                    "total_descent_m": _safe_float(r.get("total_descent_m")),
                    "up_count": _safe_int(r.get("up_count")),
                    "down_count": _safe_int(r.get("down_count")),
                    "max_single_climb_m": _safe_float(r.get("max_single_climb_m")),
                    "difficulty_score": _safe_int(r.get("difficulty_score")),
                    "avg_grade_pct": _safe_optional_float(r.get("avg_grade_pct")),
                    "max_slope_pct": _safe_optional_float(r.get("max_slope_pct")),
                    "min_slope_pct": _safe_optional_float(r.get("min_slope_pct")),
                    "uphill_pct": _safe_optional_float(r.get("uphill_pct")),
                    "downhill_pct": _safe_optional_float(r.get("downhill_pct")),
                    "report_metrics_version": _safe_int(r.get("report_metrics_version")),
                }

            points = self._decode_points_json(row.get("track_json") or row.get("points_json") or row.get("merged_track_json"))
            if points:
                filename = str(row.get("filename") or row.get("file_name") or "历史轨迹")
                weather = _decode_weather_json(row.get("weather_json"))
                raw_metrics = row.get("advanced_metrics")
                advanced_metrics = _decode_weather_json(raw_metrics) if isinstance(raw_metrics, str) else (raw_metrics or {})
                _attach_per_point_distance(points)
                placemarks = self._load_activity_placemarks(_safe_int(row.get("id")))
                return {
                    "ok": True,
                    "filename": filename,
                    "advanced_metrics": advanced_metrics,
                    "activity": _build_activity_canonical(row),
                    "data": {
                        "points": points,
                        "placemarks": placemarks,
                        "region": str(row.get("region") or "").strip(),
                        "weather": weather,
                        "advanced_metrics": advanced_metrics,
                    },
                }

            file_path = str(row.get("file_path") or "").strip()
            if file_path and os.path.isfile(file_path):
                loaded = profile_backend.load_local_track(file_path)
                if loaded.get("ok"):
                    data = dict(loaded.get("data") or {})
                    if not data.get("weather"):
                        data["weather"] = _infer_weather_from_track_data(data)
                    loaded["data"] = data
                    points_in_data = data.get("points") or []
                    if points_in_data:
                        _attach_per_point_distance(points_in_data)
                return loaded

            return {"ok": False, "error": "当前活动没有可复盘的轨迹数据"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_trace_activity_history(self, page: int = 1, page_size: int = 30, sport_filter: str = "all") -> dict:
        """返回轨迹分析工具使用的分页活动记录列表，后端驱动分页。"""
        try:
            page = max(1, _safe_int(page, 1))
            page_size = max(1, min(_safe_int(page_size, 30), 100))
            offset = (page - 1) * page_size
            db_rows, total_count = profile_backend.get_activity_list_filtered(offset, page_size, sport_filter, gps_only=True)
            deduped_rows = _dedupe_activity_rows(db_rows)
            records = [self._build_activity_list_item(row) for row in deduped_rows]

            for rec in records:
                rec["dist_km"] = rec.pop("distance_km", rec.get("distance_km_clean", 0))
                rec["valid"] = bool(rec.get("has_track"))
                rec["cityName"] = (rec.get("region") or "").strip() or "未知地点"
                rec["has_local_file"] = bool(str(rec.get("file_path") or "").strip())

            total_pages = max(1, (total_count + page_size - 1) // page_size)
            page = min(page, total_pages)

            conn = profile_backend._conn()
            try:
                type_rows = conn.execute(
                    """
                    SELECT sport_type, sub_sport_type
                    FROM activities
                    WHERE COALESCE(sport_type, '') != ''
                      AND deleted_at IS NULL
                      AND COALESCE(source_type, 'fit_sdk') = 'fit_sdk'
                      AND COALESCE(is_mock, 0) = 0
                      AND start_lat IS NOT NULL
                      AND start_lon IS NOT NULL
                      AND COALESCE(track_json, points_json, '') != ''
                      AND (
                          CASE
                              WHEN COALESCE(NULLIF(sub_sport_type, ''), 'unknown') IN ('trail_running', 'road_cycling', 'mountain_biking') THEN sub_sport_type
                              WHEN COALESCE(NULLIF(sport_type, ''), 'unknown') IN ('trail_running', 'road_cycling', 'mountain_biking') THEN sport_type
                              ELSE COALESCE(NULLIF(sport_type, ''), 'unknown')
                          END IN (
                              'running', 'hiking', 'mountaineering', 'cycling', 'walking',
                              'trail_running', 'road_cycling', 'mountain_biking'
                          )
                      )
                    """
                ).fetchall()
            finally:
                conn.close()
            activity_types = sorted(
                {
                    _resolve_display_sport_type(row["sport_type"], row["sub_sport_type"])
                    for row in type_rows
                    if _resolve_display_sport_type(row["sport_type"], row["sub_sport_type"]) != "unknown"
                },
                key=lambda item: (SPORT_HUB_TYPE_ORDER.get(item, 99), item),
            )

            return {
                "ok": True,
                "records": records,
                "total": total_count,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "activity_types": activity_types,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def check_activity_data_integrity(self) -> dict:
        try:
            return check_activity_data_integrity()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _decode_points_json(self, points_json: str | None) -> list[dict]:
        if not points_json:
            return []
        try:
            obj = json.loads(points_json)
            return obj if isinstance(obj, list) else []
        except Exception:
            return []

    def _sample_thumbnail_points(self, points: list[dict], limit: int = 48) -> list[dict]:
        if not points:
            return []
        step = max(1, len(points) // limit)
        sampled = []
        for p in points[::step]:
            lat = p.get("lat")
            lon = p.get("lon")
            if lat is None or lon is None:
                continue
            sampled.append({"lat": float(lat), "lon": float(lon)})
        return sampled[:limit]

    def _build_lap_rows(self, dist_km: float, duration_sec: int, avg_hr: int | None, base_power: int) -> list[dict]:
        import math

        if dist_km <= 0 or duration_sec <= 0:
            return []
        lap_count = max(1, min(20, int(round(dist_km))))
        lap_distance = dist_km / lap_count
        avg_pace_sec = duration_sec / max(dist_km, 0.001)
        rows: list[dict] = []
        for idx in range(lap_count):
            drift = math.sin((idx + 1) / max(lap_count, 1) * math.pi) * 8
            rows.append({
                "lap_no": idx + 1,
                "distance_km": round(lap_distance, 2),
                "pace_sec": int(avg_pace_sec + drift + (idx % 3) * 2),
                "hr": int((avg_hr or 148) + min(idx, 8)),
                "cadence": 176 + (idx % 4),
                "gct_ms": 228 + (idx % 5) * 3,
                "power_w": base_power + (idx % 6) * 6,
            })
        return rows


class SemanticSportsEngine:
    METRICS = {
        "distance": {"label": "距离", "unit": "km"},
        "duration": {"label": "时长", "unit": ""},
        "avg_pace": {"label": "平均配速", "unit": "/km"},
        "avg_speed": {"label": "平均速度", "unit": "km/h"},
        "avg_hr": {"label": "平均心率", "unit": "bpm"},
        "max_hr": {"label": "最大心率", "unit": "bpm"},
        "elevation": {"label": "总爬升", "unit": "m"},
        "calories": {"label": "热量", "unit": "Kcal"}
    }

    SPORT_PROFILES = {
        "running": {
            "summary_keys": ["distance", "avg_pace", "duration", "avg_hr"],
            "cards": [{"type": "summary_grid"}, {"type": "pace_hr_chart"}, {"type": "elevation_chart"}]
        },
        "trail_running": {
            "summary_keys": ["distance", "elevation", "duration", "avg_pace"],
            "cards": [{"type": "summary_grid"}, {"type": "elevation_chart"}, {"type": "pace_hr_chart"}]
        },
        "cycling": {
            "summary_keys": ["distance", "avg_speed", "duration", "avg_hr"],
            "cards": [{"type": "summary_grid"}, {"type": "speed_hr_power_chart"}, {"type": "elevation_chart"}]
        },
        "swimming": {
            "summary_keys": ["distance", "avg_pace", "duration", "avg_hr"],
            "cards": [{"type": "summary_grid"}, {"type": "pace_hr_chart"}]
        },
        "strength": {
            "summary_keys": ["duration", "calories", "avg_hr", "max_hr"],
            "cards": [{"type": "summary_grid"}, {"type": "hr_zones_chart"}]
        },
        "hiking": {
            "summary_keys": ["distance", "duration", "elevation", "avg_hr"],
            "cards": [{"type": "summary_grid"}, {"type": "elevation_chart"}]
        }
    }

    @staticmethod
    def format_duration(seconds):
        if not seconds or seconds < 0:
            return "--"
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    @staticmethod
    def format_pace(pace_sec):
        if not pace_sec or pace_sec <= 0:
            return "--"
        return f"{pace_sec // 60}'{pace_sec % 60:02d}\""

    @classmethod
    def build_display_metrics(cls, sport_type, raw_data):
        profile = cls.SPORT_PROFILES.get(sport_type, cls.SPORT_PROFILES["running"])
        display_list = []
        for key in profile["summary_keys"]:
            meta = cls.METRICS.get(key, {"label": key, "unit": ""})
            val_str = "--"
            if key == "distance":
                val_str = f"{raw_data.get('distance_km', 0):.2f}"
            elif key == "duration":
                val_str = cls.format_duration(raw_data.get('duration_sec', 0))
            elif key == "avg_pace":
                val_str = cls.format_pace(raw_data.get('avg_pace_sec', 0))
            elif key == "avg_speed":
                dist = raw_data.get('distance_km', 0)
                sec = raw_data.get('duration_sec', 0)
                val_str = f"{(dist / sec * 3600):.1f}" if sec > 0 else "--"
            elif key in ("avg_hr", "max_hr", "calories", "elevation"):
                val = raw_data.get(key)
                val_str = str(val) if val else "--"
            display_list.append({
                "key": key,
                "label": meta["label"],
                "value": val_str,
                "unit": meta["unit"]
            })
        return display_list

    @classmethod
    def get_layout(cls, sport_type: str) -> dict:
        return {"cards": cls.SPORT_PROFILES.get(sport_type, cls.SPORT_PROFILES["running"])["cards"]}


def _build_record_from_row(api_self, row: dict, idx: int) -> dict:
    points = api_self._decode_points_json(row.get("track_json") or row.get("points_json") or row.get("merged_track_json"))
    dist_km = _safe_float(row.get("distance") if row.get("distance") is not None else row.get("dist_km"))
    duration_sec = _safe_int(row.get("duration") if row.get("duration") is not None else row.get("duration_sec"))
    avg_hr = _safe_int(row.get("avg_hr")) or None
    max_hr = _safe_int(row.get("max_hr"))
    avg_pace = row.get("avg_pace")
    pace_sec = _safe_int(avg_pace) if avg_pace is not None else None
    sub_sport_record = str(row.get("sub_sport_type") or "").strip()
    pace_unit_record = "/100m" if sub_sport_record in ("lap_swimming", "open_water") else "/km"
    if pace_sec and pace_sec > 0:
        pm, ps = int(pace_sec // 60), int(round(pace_sec % 60))
        pace_display_detail = f"{pm}'{ps:02d}''{pace_unit_record}"
    else:
        pace_display_detail = f"-- {pace_unit_record}"
    raw_distance_m_detail = dist_km * 1000
    if raw_distance_m_detail <= 5000:
        distance_display_detail = f"{int(raw_distance_m_detail)}m"
    else:
        distance_display_detail = f"{round(dist_km, 2):.2f}km"
    calories = _safe_int(row.get("calories"))
    display_type = _resolve_display_sport_type(row.get("sport_type"), row.get("sub_sport_type"))
    title = str(row.get("title") or "").strip()
    base_power = 245 + (idx % 5) * 8
    timestamp = row.get("start_time") or row.get("updated_at")

    try:
        dt = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")) if timestamp else None
        month_key = dt.strftime("%Y-%m") if dt else "--"
        date_label = dt.strftime("%Y-%m-%d %H:%M") if dt else "--"
    except Exception:
        month_key = "--"
        date_label = str(timestamp or "--")

    import json

    raw_metrics_json = row.get("advanced_metrics")
    adv_metrics = {}

    if raw_metrics_json and isinstance(raw_metrics_json, str):
        try:
            adv_metrics = json.loads(raw_metrics_json) or {}
        except (json.JSONDecodeError, ValueError):
            adv_metrics = {}
    elif isinstance(raw_metrics_json, dict):
        adv_metrics = raw_metrics_json

    # 3. 【能力感知雷达网关 (Capability-Aware Radar Gateway)】
    if display_type in ("running", "trail_running"):
        radar_data = {
            "type": display_type,
            "labels": ["耐力水平", "乳酸阈值", "有氧效率", "无氧爆发", "恢复得分"],
            "scores": [
                min(100, max(20, int(_safe_float(adv_metrics.get("trimp")) / 1.5))) if adv_metrics.get("trimp") else 60,
                min(100, max(20, int(_safe_float(adv_metrics.get("threshold_hr")) / 1.8))) if adv_metrics.get("threshold_hr") else 65,
                min(100, max(20, int(100 - _safe_float(adv_metrics.get("decoupling", 0)) * 200))) if adv_metrics.get("decoupling") is not None else 70,
                min(100, max(20, int(_safe_float(adv_metrics.get("anaerobic_peak")) * 10))) if adv_metrics.get("anaerobic_peak") else 55,
                min(100, max(20, int(_safe_float(adv_metrics.get("hrv", 60)))))
            ]
        }
    elif display_type in ("cycling", "road_cycling", "mountain_biking"):
        radar_data = {
            "type": display_type,
            "labels": ["巡航输出", "有氧耐力", "心率响应", "爬升攀登", "恢复基线"],
            "scores": [
                min(100, max(20, int(_safe_float(adv_metrics.get("anaerobic_peak")) * 8))) if adv_metrics.get("anaerobic_peak") else 60,
                min(100, max(20, int(_safe_float(adv_metrics.get("trimp")) / 2.0))) if adv_metrics.get("trimp") else 55,
                min(100, max(20, int(100 - _safe_float(adv_metrics.get("decoupling", 0)) * 150))) if adv_metrics.get("decoupling") is not None else 65,
                min(100, max(20, int(_safe_float(adv_metrics.get("vam")) / 10.0))) if adv_metrics.get("vam") else 50,
                min(100, max(20, int(_safe_float(adv_metrics.get("hrv", 60)))))
            ]
        }
    elif display_type in ("hiking", "mountaineering"):
        radar_data = {
            "type": display_type,
            "labels": ["爬升效率", "长时耐力", "海拔适应", "体能负荷", "心脏恢复"],
            "scores": [
                min(100, max(20, int(_safe_float(adv_metrics.get("vam")) / 8.0))) if adv_metrics.get("vam") else 65,
                min(100, max(20, int(_safe_float(adv_metrics.get("trimp")) / 1.2))) if adv_metrics.get("trimp") else 70,
                min(100, max(20, int(_safe_float(row.get("max_alt_m", 0)) / 50.0))) if row.get("max_alt_m") else 50,
                min(100, max(20, int(_safe_float(adv_metrics.get("trimp")) / 2.5))) if adv_metrics.get("trimp") else 60,
                min(100, max(20, int(_safe_float(adv_metrics.get("hrv", 60)))))
            ]
        }
    else:
        radar_data = {
            "type": display_type,
            "labels": ["运动时长", "卡路里消耗", "心率控制", "训练负荷", "恢复指数"],
            "scores": [
                min(100, max(20, int(duration_sec / 60.0))) if duration_sec else 50,
                min(100, max(20, int(calories / 10.0))) if calories else 45,
                min(100, max(20, int((avg_hr or 120) / 1.8))),
                min(100, max(20, int(_safe_float(adv_metrics.get("trimp", 30))))),
                min(100, max(20, int(_safe_float(adv_metrics.get("hrv", 60)))))
            ]
        }

    raw_for_engine = {
        "distance_km": dist_km,
        "duration_sec": duration_sec,
        "avg_pace_sec": pace_sec,
        "avg_pace_display": pace_display_detail,
        "distance_display": distance_display_detail,
        "avg_hr": avg_hr,
        "max_hr": max_hr,
        "calories": calories,
        "elevation": int(row.get("gain_m") or 0),
    }

    capabilities = {
        "has_gps": bool(points),
        "has_hr": bool(avg_hr),
        "has_elevation": bool(row.get("gain_m") and float(row.get("gain_m")) > 0),
        "has_power": False,
    }

    detail = {
        "display_metrics": SemanticSportsEngine.build_display_metrics(display_type, raw_for_engine),
        "layout": SemanticSportsEngine.get_layout(display_type),
        "capabilities": capabilities,
        "radar": radar_data,
        "summary": raw_for_engine,
        "laps": api_self._build_lap_rows(dist_km, duration_sec, avg_hr, base_power),
        "thumbnail_points": api_self._sample_thumbnail_points(points),
    }

    region_status = str(row.get("region_status") or "").strip()
    region_display = str(row.get("region_display") or row.get("region") or "").strip()
    if not region_display:
        if region_status == "pending":
            region_display = "待补全"
        elif region_status == "none":
            region_display = "室内运动"
        elif region_status == "failed":
            region_display = "未知地点"

    return {
        "id": int(row.get("id") or idx + 1),
        "sport_type": str(row.get("sport_type") or "running"),
        "sub_sport_type": str(row.get("sub_sport_type") or "unknown"),
        "display_sport_type": display_type,
        "title": title,
        "title_source": str(row.get("title_source") or ""),
        "file_name": row.get("filename") or row.get("file_name") or title,
        "filename": row.get("filename") or row.get("file_name") or title,
        "start_time": row.get("start_time"),
        "start_time_utc": row.get("start_time_utc"),
        "date_label": date_label,
        "month_key": month_key,
        "distance_km": round(dist_km, 2),
        "duration_sec": duration_sec,
        "avg_pace_sec": pace_sec,
        "avg_hr": avg_hr,
        "max_hr": max_hr,
        "calories": calories,
        "gain_m": int(row.get("gain_m") or 0),
        "region": region_display,
        "region_display": region_display,
        "region_status": region_status,
        "device_name": str(row.get("device_name") or "").strip(),
        "start_lat": _safe_float(row.get("start_lat")) or None,
        "start_lon": _safe_float(row.get("start_lon")) or None,
        "weather": _decode_weather_json(row.get("weather_json")),
        "file_path": row.get("file_path") or "",
        "has_track": bool(points),
        "has_local_file": bool(str(row.get("file_path") or "").strip() and os.path.isfile(str(row.get("file_path") or "").strip())),
        "shadow_diff": _decode_weather_json(row.get("shadow_diff_json")) if row.get("shadow_diff_json") else {},
        "thumbnail_points": detail["thumbnail_points"],
        "detail": detail,
    }


def _api_build_results_payload(self, records: list[dict]) -> dict:
    result_entries = []
    for rec in records:
        dist = rec.get("distance_km") or 0.0
        if 20.5 <= dist <= 21.7:
            result_entries.append({
                "activity_id": rec["id"],
                "month": rec["month_key"],
                "title": rec["title"],
                "category": "half_marathon",
                "finish_time_sec": rec["duration_sec"],
                "avg_hr": rec.get("avg_hr") or 0,
            })
        elif 41.0 <= dist <= 43.0:
            result_entries.append({
                "activity_id": rec["id"],
                "month": rec["month_key"],
                "title": rec["title"],
                "category": "full_marathon",
                "finish_time_sec": rec["duration_sec"],
                "avg_hr": rec.get("avg_hr") or 0,
            })
    result_entries.sort(key=lambda item: item["month"])
    return {"entries": result_entries}


def _api_build_honors_payload(self, records: list[dict]) -> list[dict]:
    honor_items = []
    for rec in records:
        dist = rec.get("distance_km") or 0
        if dist < 20:
            continue
        month = rec.get("month_key") or "--"
        year = month.split("-")[0] if "-" in month else "未知"
        month_no = month.split("-")[1] if "-" in month else "--"
        honor_items.append({
            "year": year,
            "month": month_no,
            "activity_id": rec["id"],
            "title": rec["title"],
            "subtitle": f'{dist:.1f} km · {rec.get("sport_type", "running")}',
            "photo_label": "赛事照片占位",
        })
    grouped: dict[str, dict[str, list[dict]]] = {}
    for item in honor_items:
        grouped.setdefault(item["year"], {}).setdefault(item["month"], []).append(item)
    years = []
    for year in sorted(grouped.keys(), reverse=True):
        months = []
        for month in sorted(grouped[year].keys(), reverse=True):
            months.append({"month": month, "cards": grouped[year][month]})
        years.append({"year": year, "months": months})
    return years


def _api_get_person_sport_hub_data(self) -> dict:
    try:
        ensure_activity_sync_schema()
        config = resolve_workspace_track_dir(auto_recover=True)
        source_dir = str(config.get("workspace_track_abs_path") or "")
        where_sql, params = _source_scope_filter_clause(source_dir)
        conn = profile_backend._conn()
        try:
            _cleanup_invalid_activity_types(conn)
            conn.commit()
            rows = conn.execute(
                f"""
                SELECT id, COALESCE(file_name, filename) AS file_name, filename,
                       title, title_source, start_time_utc,
                       sport_type, sub_sport_type, COALESCE(distance, dist_km) AS distance,
                       COALESCE(duration, duration_sec) AS duration, gain_m, max_alt_m,
                       avg_pace, avg_hr, max_hr, calories,
                       COALESCE(track_json, points_json) AS track_json,
                       file_path, start_time, updated_at
                FROM activities
                {where_sql}
                ORDER BY COALESCE(start_time, updated_at) DESC, id DESC
                LIMIT 200
                """,
                tuple(params),
            ).fetchall()
        finally:
            conn.close()
        deduped_rows = _dedupe_activity_rows([dict(row) for row in rows])
        records = [_build_record_from_row(self, row, idx) for idx, row in enumerate(deduped_rows)]
        activity_types = sorted(
            {rec.get("display_sport_type") for rec in records if rec.get("display_sport_type")},
            key=lambda item: (SPORT_HUB_TYPE_ORDER.get(item, 99), item),
        )
        return {
            "ok": True,
            "activity_types": activity_types,
            "page_sizes": SPORT_HUB_PAGE_SIZES,
            "records": records,
            "results": self._build_results_payload(records),
            "honors": self._build_honors_payload(records),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _api_load_local_track(self, file_path: str) -> dict:
    try:
        return profile_backend.load_local_track(file_path)
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _api_get_activity_by_file_path(self, file_path: str) -> dict:
    try:
        resolved = str(Path(file_path).expanduser().resolve())
        ensure_activity_sync_schema()
        conn = profile_backend._conn()
        try:
            row = _find_activity_by_file_path(conn, resolved)
        finally:
            conn.close()
        if not row:
            return {"ok": False, "error": "未找到对应活动记录"}
        return {"ok": True, "activity": row}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _api_load_activity_track_by_file_path(self, file_path: str) -> dict:
    try:
        resolved = str(Path(file_path).expanduser().resolve())
        lookup = self.get_activity_by_file_path(resolved)
        if lookup.get("ok") and lookup.get("activity"):
            activity_id = _safe_int(dict(lookup["activity"]).get("id"))
            if activity_id:
                return self.load_activity_track(activity_id)
        return self.load_local_track(resolved)
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _api_import_track(self, file_path: str = "", duplicate_action: str = "", new_filename: str = "") -> dict:
    import webview
    from webview import FileDialog

    target_path = (file_path or "").strip()
    if not target_path:
        if not webview.windows:
            return {"ok": False, "error": "窗口未就绪"}
        paths = webview.windows[0].create_file_dialog(
            FileDialog.OPEN,
            file_types=("GPX files (*.gpx)",),
        )
        if not paths:
            return {"ok": False, "cancelled": True}
        target_path = paths[0] if isinstance(paths, (list, tuple)) else paths
    if Path(target_path).suffix.lower() != ".gpx":
        return {"ok": False, "error": "仅支持导入 GPX 文件，请选择 .gpx 格式的轨迹文件"}
    try:
        return profile_backend.ingest_activity_file(
            target_path,
            duplicate_action=duplicate_action,
            new_filename=new_filename or None,
        )
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _api_update_activity_sport_type(self, activity_id: int, sport_type: str) -> dict:
    try:
        profile_backend.update_activity_sport_type(activity_id, sport_type)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _api_validate_fit_directory(self, local_dir: str) -> dict:
    try:
        raw = str(local_dir or "").strip()
        if not raw:
            return {"ok": False, "error": "目录不能为空"}
        path = os.path.abspath(os.path.expanduser(raw))
        if not os.path.isdir(path):
            return {"ok": False, "error": f"目录不存在: {path}"}
        if not os.access(path, os.R_OK):
            return {"ok": False, "error": "目录不可读"}
        if not os.access(path, os.W_OK):
            return {"ok": False, "error": "目录不可写"}
        return {"ok": True, "path": path}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _api_scan_fit_directory(self, local_dir: str = "") -> dict:
    try:
        app_cfg = resolve_workspace_track_dir(auto_recover=True)
        target_dir = str(app_cfg.get("workspace_track_abs_path") or "").strip()
        if not target_dir and str(local_dir or "").strip():
            target_dir = os.path.abspath(os.path.expanduser(str(local_dir).strip()))
        if not target_dir:
            return {"ok": True, "files": [], "total": 0, "valid": 0, "skipped": 0}
        import profile_backend as pb
        res = pb.scan_fit_directory(target_dir)
        if isinstance(res, dict):
            res["source_dir"] = target_dir
            res["integrity"] = check_activity_data_integrity()
        return res
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _api_check_duplicate_track(self, act_data: dict) -> dict:
    try:
        res = profile_backend.check_duplicate_activity(
            start_time=act_data.get("start_time"),
            dist_km=act_data.get("dist_km", 0.0),
            duration_sec=act_data.get("duration_sec", 0),
            points_json=act_data.get("points_json", []),
            start_time_utc=act_data.get("start_time_utc"),
        )
        return {"ok": True, **res}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _api_save_activity(self, data: dict) -> dict:
    try:
        dup_action = data.get("_duplicate_action")
        if dup_action == "skip":
            return {"ok": True, "skipped": True}
        src = data.get("_src_path")
        new_filename = data.get("_new_filename")
        if src:
            data["file_path"] = profile_backend.copy_track_to_local(src, new_filename)
        else:
            data["file_path"] = None
        if data.get("points_json") and len(data["points_json"]) > 0:
            data["start_time"] = data["points_json"][0].get("time")
        profile_backend.save_activity(data)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


Api._build_results_payload = _api_build_results_payload
Api._build_honors_payload = _api_build_honors_payload
Api.get_person_sport_hub_data = _api_get_person_sport_hub_data
Api.load_local_track = _api_load_local_track
Api.get_activity_by_file_path = _api_get_activity_by_file_path
Api.load_activity_track_by_file_path = _api_load_activity_track_by_file_path
Api.import_track = _api_import_track
Api.update_activity_sport_type = _api_update_activity_sport_type
Api.validate_fit_directory = _api_validate_fit_directory
Api.scan_fit_directory = _api_scan_fit_directory
Api.check_duplicate_track = _api_check_duplicate_track
Api.save_activity = _api_save_activity


def _get_schema_version() -> int:
    """从数据库中读取当前 schema 版本号。"""
    conn = profile_backend._conn()
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS _schema_meta (key TEXT PRIMARY KEY, value TEXT)")
        row = conn.execute("SELECT value FROM _schema_meta WHERE key = 'schema_version'").fetchone()
        if row:
            return int(dict(row).get("value", 0))
        return 0
    except Exception:
        return 0
    finally:
        conn.close()


def _set_schema_version(version: int) -> None:
    """将 schema 版本号写入数据库。"""
    conn = profile_backend._conn()
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS _schema_meta (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute(
            "INSERT OR REPLACE INTO _schema_meta (key, value) VALUES ('schema_version', ?)",
            (str(version),),
        )
        conn.commit()
    except Exception as exc:
        logger.warning("写入 schema_version 失败: %s", exc)
    finally:
        conn.close()


def force_rebuild_all_records() -> dict[str, Any]:
    """强制重建所有活动记录的 advanced_metrics。"""
    ensure_activity_sync_schema()
    conn = profile_backend._conn()
    try:
        rows = conn.execute(
            """
            SELECT id, track_json, points_json
            FROM activities
            WHERE deleted_at IS NULL
              AND (track_json IS NOT NULL AND track_json != '')
            ORDER BY id ASC
            """
        ).fetchall()
        if not rows:
            logger.info("全量重建: 无活动记录需要处理")
            _set_schema_version(CURRENT_SCHEMA_VERSION)
            return {"ok": True, "migrated": 0}

        logger.info("全量重建: 开始处理 %s 条记录...", len(rows))
        migrated = 0
        for row in rows:
            try:
                row = dict(row)
                track_json = row.get("track_json") or row.get("points_json")
                if not track_json:
                    continue
                track_data = json.loads(track_json) if isinstance(track_json, str) else track_json
                if not isinstance(track_data, list) or len(track_data) < 2:
                    continue
                advanced = _compute_advanced_metrics(track_data)
                if advanced:
                    advanced["metrics_version"] = CURRENT_METRICS_VERSION
                    advanced_json = json.dumps(advanced, ensure_ascii=False)
                    conn.execute(
                        "UPDATE activities SET advanced_metrics = ?, updated_at = datetime('now') WHERE id = ?",
                        (advanced_json, int(row["id"])),
                    )
                    migrated += 1
                    if migrated % 10 == 0:
                        conn.commit()
            except Exception as exc:
                logger.warning("全量重建: 记录 id=%s 计算失败: %s", row.get("id"), exc)
                continue
        conn.commit()
        logger.info("全量重建完成: 成功重建 %s / %s 条记录", migrated, len(rows))
        _set_schema_version(CURRENT_SCHEMA_VERSION)
        return {"ok": True, "migrated": migrated, "total": len(rows)}
    except Exception as e:
        conn.rollback()
        logger.exception("全量重建失败: %s", e)
        return {"ok": False, "error": str(e), "migrated": 0}
    finally:
        conn.close()


def main() -> None:
    import webview

    local_version = _get_schema_version()
    if local_version < CURRENT_SCHEMA_VERSION:
        logger.info("Schema 版本升级: %s -> %s，触发增量数据清洗", local_version, CURRENT_SCHEMA_VERSION)
        force_rebuild_all_records()
    else:
        logger.info("Schema 版本一致 (v=%s)，跳过数据清洗", local_version)
    url = str(html_file().resolve())
    api = Api()
    window = webview.create_window(
        "脉图 - fit vault",
        url=url,
        js_api=api,
        width=1280,
        height=800,
        min_size=(800, 600),
        background_color='#0f172a',  # 匹配 HTML 背景色，消除白色闪烁
    )
    api.bind_window(window)
    watch_service = FITFolderWatchService(api)
    api.set_watch_service(watch_service)
    watch_service.start()
    try:
        webview.start(debug=False)
    finally:
        _APP_SHUTTING_DOWN.set()
        watch_service.stop()


if __name__ == "__main__":
    init_application_config()
    main()
