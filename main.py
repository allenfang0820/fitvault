#!/usr/bin/env python3
"""使用 pywebview 在桌面窗口中加载「徒步轨迹AI分析仪」单页 HTML。"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import llm_backend  # noqa: F401 -- PyInstaller bundles LLM 模块
import track_backend  # noqa: F401 -- PyInstaller bundles track_backend
import profile_backend  # noqa: F401 -- PyInstaller bundles profile 模块
from fit_engine import FITCoreEngine

DEBUG_MODE = False

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
APP_CONFIG_PATH = os.path.expanduser("~/.trackapp_config.json")
DEFAULT_APP_CONFIG = {
    "workspace_track_path": "~/.qclaw/workspace/garmin_tracks/",
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
    "driving": 10,
}

_ACTIVITY_SYNC_SCHEMA_LOCK = threading.Lock()
_ACTIVITY_SYNC_SCHEMA_READY_FOR: str | None = None
_APP_SHUTTING_DOWN = threading.Event()
FIT_WATCH_DEBOUNCE_SEC = 1.2
FIT_WATCH_STABLE_WAIT_SEC = 0.5


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


def _resolve_workspace_track_path(config: dict | None = None) -> tuple[str, str]:
    raw_path = ""
    if isinstance(config, dict):
        raw_path = str(config.get("workspace_track_path") or "").strip()
    if not raw_path:
        raw_path = DEFAULT_APP_CONFIG["workspace_track_path"]
    abs_path = os.path.abspath(os.path.expanduser(raw_path))
    return raw_path, abs_path


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

    raw_path, abs_path = _resolve_workspace_track_path(config)
    if not str(config.get("workspace_track_path") or "").strip() and config_status == "loaded":
        config_status = "recovered"

    config["workspace_track_path"] = raw_path
    config["workspace_track_abs_path"] = abs_path
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
                    "workspace_track_abs_path",
                    "config_path",
                    "config_status",
                }
            }
        )

    raw_path, abs_path = _resolve_workspace_track_path(payload)
    payload["workspace_track_path"] = raw_path

    os.makedirs(abs_path, exist_ok=True)
    with open(APP_CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

    payload["workspace_track_abs_path"] = abs_path
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
    """初始化全局配置文件与轨迹目录，确保首次启动可自愈。"""
    try:
        file_exists = os.path.exists(APP_CONFIG_PATH)
        config = load_application_config()
        config_status = str(config.get("config_status") or "loaded")

        if (not file_exists) or config_status != "loaded":
            config = persist_application_config(config)
            config_status = "created" if not file_exists else "repaired"
        else:
            os.makedirs(str(config.get("workspace_track_abs_path") or ""), exist_ok=True)

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


def _resolve_display_sport_type(sport_type: Any, sub_sport_type: Any) -> str:
    sub_token = _normalize_activity_token(sub_sport_type, "")
    if sub_token in {"trail_running", "road_cycling", "mountain_biking"}:
        return sub_token
    sport_token = _normalize_activity_token(sport_type)
    if sport_token in {"trail_running", "road_cycling", "mountain_biking"}:
        return sport_token
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
    return fetch_historical_weather(lat, lon, start_time)


def _estimate_calories(distance_km: float, duration_sec: int, avg_hr: int | None = None) -> int:
    if distance_km <= 0 and duration_sec <= 0:
        return 0
    base = distance_km * 62.0 + duration_sec / 90.0
    if avg_hr:
        base *= min(1.35, max(0.85, avg_hr / 145.0))
    return max(1, int(round(base)))


def _activity_schema_cache_key() -> str:
    return str(Path(profile_backend.DB_PATH).expanduser().resolve())


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
            columns = _sqlite_table_columns(conn, "activities")
            required_columns = {
                "file_name": "TEXT",
                "title": "TEXT",
                "title_source": "TEXT",
                "distance": "REAL",
                "duration": "INTEGER",
                "avg_pace": "REAL",
                "calories": "INTEGER",
                "track_json": "TEXT",
                "start_time_utc": "TEXT",
                "start_lat": "REAL",
                "start_lon": "REAL",
                "region": "TEXT",
                "weather_json": "TEXT",
                "file_mtime": "REAL",
                "file_size": "INTEGER",
                "deleted_at": "TEXT",
                "advanced_metrics": "TEXT",
            }
            for col, dtype in required_columns.items():
                if col not in columns:
                    conn.execute(f"ALTER TABLE activities ADD COLUMN {col} {dtype}")

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
            conn.execute(
                """
                UPDATE activities
                SET distance = COALESCE(distance, dist_km)
                WHERE distance IS NULL
                """
            )
            conn.execute(
                """
                UPDATE activities
                SET duration = COALESCE(duration, duration_sec)
                WHERE duration IS NULL
                """
            )
            conn.execute(
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
            conn.execute(
                """
                UPDATE activities
                SET start_time_utc = COALESCE(NULLIF(start_time_utc, ''), CASE WHEN start_time LIKE '%Z' THEN start_time ELSE NULL END)
                WHERE start_time_utc IS NULL OR start_time_utc = ''
                """
            )
            conn.execute(
                """
                UPDATE activities
                SET avg_pace = ROUND(COALESCE(duration, duration_sec) / COALESCE(distance, dist_km), 2)
                WHERE avg_pace IS NULL
                  AND COALESCE(duration, duration_sec, 0) > 0
                  AND COALESCE(distance, dist_km, 0) > 0
                """
            )

            rows = conn.execute(
                """
                SELECT id, COALESCE(distance, dist_km, 0) AS distance_km,
                       COALESCE(duration, duration_sec, 0) AS duration_sec,
                       avg_hr, calories
                FROM activities
                WHERE calories IS NULL
                """
            ).fetchall()
            for row in rows:
                row_dict = dict(row)
                conn.execute(
                    "UPDATE activities SET calories = ? WHERE id = ?",
                    (
                        _estimate_calories(
                            _safe_float(row_dict.get("distance_km")),
                            _safe_int(row_dict.get("duration_sec")),
                            _safe_int(row_dict.get("avg_hr")) or None,
                        ),
                        row_dict["id"],
                    ),
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


def _parse_fit_activity_for_sync(file_path: Path) -> dict[str, Any]:
    resolved_path = str(file_path.expanduser().resolve())
    core = FITCoreEngine.parse_fit_file(resolved_path)
    basic = dict(core.get("basic_info") or {})
    track_data = [dict(point) for point in (core.get("track_data") or [])]
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
    distance_km = _safe_float(payload.get("dist_km"))
    duration_sec = _safe_int(payload.get("duration_sec"))
    avg_hr = _safe_int(payload.get("avg_hr")) or None
    avg_pace = round(duration_sec / distance_km, 2) if distance_km > 0 and duration_sec > 0 else None
    track_json = json.dumps(payload.get("points_json") or [], ensure_ascii=False)
    weather = fetch_historical_weather(
        payload.get("start_lat"),
        payload.get("start_lon"),
        payload.get("start_time") or payload.get("start_time_utc"),
    )
    stat = file_path.stat()
    advanced_metrics = _compute_advanced_metrics(track_data)
    return {
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
        "avg_hr": avg_hr,
        "max_hr": _safe_int(payload.get("max_hr")) or None,
        "calories": _safe_int(payload.get("calories")) or _estimate_calories(distance_km, duration_sec, avg_hr),
        "gain_m": _safe_float(payload.get("gain_m")),
        "max_alt_m": _safe_float(payload.get("max_alt_m")),
        "track_json": track_json,
        "points_json": track_json,
        "file_path": resolved_path,
        "start_lat": _safe_float(payload.get("start_lat")) or None,
        "start_lon": _safe_float(payload.get("start_lon")) or None,
        "region": str(payload.get("region") or "").strip(),
        "weather_json": json.dumps(weather, ensure_ascii=False) if weather else None,
        "file_mtime": float(stat.st_mtime),
        "file_size": int(stat.st_size),
        "advanced_metrics": json.dumps(advanced_metrics, ensure_ascii=False) if advanced_metrics else None,
    }


def _insert_activity_sync_row(conn: sqlite3.Connection, activity: dict[str, Any]) -> int:
    cur = conn.execute(
        """
        INSERT INTO activities
            (file_name, filename, title, title_source, start_time, start_time_utc, sport_type, sub_sport_type,
             distance, dist_km, duration, duration_sec, avg_pace, avg_hr, max_hr,
             calories, track_json, points_json, file_path, gain_m, max_alt_m, start_lat, start_lon, region,
             weather_json, file_mtime, file_size, advanced_metrics, deleted_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, datetime('now'))
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
            activity.get("weather_json"),
            activity.get("file_mtime"),
            activity.get("file_size"),
            activity.get("advanced_metrics"),
        ),
    )
    return int(cur.lastrowid)


def _update_activity_sync_row(conn: sqlite3.Connection, activity_id: int, activity: dict[str, Any]) -> None:
    conn.execute(
        """
        UPDATE activities
        SET file_name = ?, filename = ?, title = ?, title_source = ?, start_time = ?, start_time_utc = ?,
            sport_type = ?, sub_sport_type = ?, distance = ?, dist_km = ?, duration = ?, duration_sec = ?,
            avg_pace = ?, avg_hr = ?, max_hr = ?, calories = ?, track_json = ?, points_json = ?,
            file_path = ?, gain_m = ?, max_alt_m = ?, start_lat = ?, start_lon = ?, region = ?,
            weather_json = ?, file_mtime = ?, file_size = ?, advanced_metrics = ?, deleted_at = NULL, updated_at = datetime('now')
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
            activity.get("weather_json"),
            activity.get("file_mtime"),
            activity.get("file_size"),
            activity.get("advanced_metrics"),
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


def _infer_activity_source_dir() -> dict[str, Any] | None:
    ensure_activity_sync_schema()
    conn = profile_backend._conn()
    try:
        rows = conn.execute(
            """
            SELECT file_path, COUNT(*) AS record_count
            FROM activities
            WHERE COALESCE(file_path, '') != ''
            GROUP BY file_path
            """
        ).fetchall()
    finally:
        conn.close()

    counter: dict[str, int] = {}
    sample_file = None
    for row in rows:
        file_path = str(dict(row).get("file_path") or "").strip()
        if not file_path:
            continue
        parent = str(Path(file_path).expanduser().resolve().parent)
        if not os.path.isdir(parent):
            continue
        counter[parent] = counter.get(parent, 0) + _safe_int(dict(row).get("record_count"), 1)
        sample_file = file_path

    if not counter:
        return None

    best_dir = sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]
    return {
        "path": best_dir,
        "record_count": counter[best_dir],
        "sample_file": sample_file or "",
    }


def resolve_workspace_track_dir(auto_recover: bool = True) -> dict[str, Any]:
    config = load_application_config()
    configured_abs = str(config.get("workspace_track_abs_path") or "")
    configured_raw = str(config.get("workspace_track_path") or DEFAULT_APP_CONFIG["workspace_track_path"])
    status = _inspect_directory_access(configured_abs) if configured_abs else {
        "path": configured_abs,
        "exists": False,
        "is_dir": False,
        "readable": False,
        "writable": False,
        "fit_count": 0,
    }
    recovered = None

    should_recover = auto_recover and (
        not status["exists"]
        or not status["is_dir"]
        or not status["readable"]
        or status["fit_count"] == 0
    )
    if should_recover:
        inferred = _infer_activity_source_dir()
        if inferred:
            inferred_status = _inspect_directory_access(inferred["path"])
            if inferred_status["exists"] and inferred_status["is_dir"] and inferred_status["fit_count"] > 0:
                if os.path.abspath(inferred["path"]) != os.path.abspath(configured_abs or inferred["path"]):
                    previous = {
                        "workspace_track_path": configured_raw,
                        "workspace_track_abs_path": configured_abs,
                    }
                    backup_path = backup_application_config("auto_recover_source", config)
                    persist_application_config({"workspace_track_path": inferred["path"]})
                    append_application_audit(
                        "auto_recover_workspace_track_path",
                        {
                            "previous": previous,
                            "recovered": inferred,
                            "backup_path": backup_path,
                        },
                    )
                    config = load_application_config()
                    status = _inspect_directory_access(str(config.get("workspace_track_abs_path") or ""))
                    recovered = {
                        "previous_path": configured_abs,
                        "recovered_path": inferred["path"],
                        "backup_path": backup_path,
                    }

    config["workspace_track_status"] = status
    config["workspace_track_recovered"] = recovered
    config["ok"] = True
    return config


def _source_scope_filter_clause(source_dir: str) -> tuple[str, list[Any]]:
    normalized = str(source_dir or "").strip()
    if not normalized:
        return "", []
    return "WHERE file_path LIKE ? AND deleted_at IS NULL", [normalized.rstrip("/\\") + os.sep + "%"]


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


def _find_activity_by_file_name(conn: sqlite3.Connection, file_name: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, file_name, filename, file_path
        FROM activities
        WHERE COALESCE(file_name, filename) = ? AND deleted_at IS NULL
        ORDER BY id DESC
        LIMIT 1
        """,
        (file_name,),
    ).fetchone()
    return dict(row) if row else None


def _find_activity_by_file_path(conn: sqlite3.Connection, file_path: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, file_name, filename, file_path, title, sport_type, sub_sport_type, start_time, updated_at, file_mtime, file_size
        FROM activities
        WHERE file_path = ? AND deleted_at IS NULL
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
        SELECT id, file_path, file_mtime, file_size
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

    def _write() -> dict[str, Any]:
        conn = profile_backend._conn()
        try:
            existing = _find_activity_by_file_path(conn, file_path) if file_path else None
            if existing:
                file_mtime = activity.get("file_mtime")
                file_size = activity.get("file_size")
                if (
                    file_mtime is not None
                    and file_size is not None
                    and existing.get("file_mtime") is not None
                    and existing.get("file_size") is not None
                    and abs(float(existing.get("file_mtime") or 0) - float(file_mtime)) < 0.001
                    and int(existing.get("file_size") or 0) == int(file_size)
                ):
                    return {"op": "skipped", "id": int(existing["id"])}
            if not existing and file_name:
                existing = _find_activity_by_file_name(conn, file_name)
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
    }


class FITFolderHandler(FileSystemEventHandler):
    def __init__(self, schedule_callback) -> None:
        super().__init__()
        self._schedule_callback = schedule_callback

    def on_created(self, event) -> None:
        if getattr(event, "is_directory", False):
            return
        file_path = str(getattr(event, "src_path", "") or "").strip()
        if not file_path.lower().endswith(".fit"):
            return
        self._schedule_callback(file_path)


class FITFolderWatchService:
    def __init__(
        self,
        api: "Api",
        debounce_sec: float = FIT_WATCH_DEBOUNCE_SEC,
        stable_wait_sec: float = FIT_WATCH_STABLE_WAIT_SEC,
    ) -> None:
        self._api = api
        self._observer: Observer | None = None
        self._handler: FITFolderHandler | None = None
        self._watch_path = ""
        self._lock = threading.Lock()
        self._debounce_sec = max(float(debounce_sec), float(stable_wait_sec), 0.1)
        self._stable_wait_sec = max(float(stable_wait_sec), 0.1)
        self._pending_files: set[str] = set()
        self._synced_signatures: dict[str, tuple[int, int]] = {}
        self._debounce_timer: threading.Timer | None = None
        self._batch_running = False

    def start(self) -> dict[str, Any]:
        config = resolve_workspace_track_dir(auto_recover=True)
        target_dir = str(config.get("workspace_track_abs_path") or "").strip()
        return self.restart(target_dir)

    def restart(self, target_dir: str) -> dict[str, Any]:
        target_dir = str(target_dir or "").strip()
        with self._lock:
            self._stop_locked()
            self._pending_files.clear()
            self._synced_signatures.clear()
            self._batch_running = False
            if not target_dir:
                self._watch_path = ""
                return {"ok": True, "watching": False, "path": ""}
            base = Path(target_dir).expanduser().resolve()
            os.makedirs(str(base), exist_ok=True)
            if not base.is_dir():
                return {"ok": False, "error": f"监听目录无效: {base}"}

            observer = Observer()
            handler = FITFolderHandler(self._enqueue_created_file)
            observer.schedule(handler, str(base), recursive=True)
            observer.start()
            self._observer = observer
            self._handler = handler
            self._watch_path = str(base)
            print(f"[watchdog] 开始监听 FIT 目录: {self._watch_path}")
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
        timer = self._debounce_timer
        self._debounce_timer = None
        if timer is not None:
            timer.cancel()
        if observer is None:
            return
        try:
            observer.stop()
            observer.join(timeout=3.0)
            print(f"[watchdog] 已停止监听 FIT 目录: {old_path}")
        except Exception as exc:
            print(f"[watchdog] 停止监听失败: {exc}")

    def _enqueue_created_file(self, file_path: str) -> None:
        normalized = str(Path(file_path).expanduser().resolve())
        with self._lock:
            self._pending_files.add(normalized)
            self._arm_debounce_timer_locked()

    def _arm_debounce_timer_locked(self) -> None:
        if _APP_SHUTTING_DOWN.is_set():
            return
        if self._debounce_timer is not None:
            self._debounce_timer.cancel()
        self._debounce_timer = threading.Timer(self._debounce_sec, self._flush_pending_files)
        self._debounce_timer.daemon = True
        self._debounce_timer.start()

    def _flush_pending_files(self) -> None:
        with self._lock:
            self._debounce_timer = None
            if self._batch_running or not self._pending_files or _APP_SHUTTING_DOWN.is_set():
                return
            batch_paths = sorted(self._pending_files)
            self._pending_files.clear()
            self._batch_running = True

        worker = threading.Thread(
            target=self._run_sync_batch,
            args=(batch_paths,),
            daemon=True,
            name="fit-watch-batch-sync",
        )
        worker.start()

    def _run_sync_batch(self, batch_paths: list[str]) -> None:
        try:
            time.sleep(self._stable_wait_sec)
            candidates = self._collect_sync_candidates(batch_paths)
            if not candidates or _APP_SHUTTING_DOWN.is_set():
                return

            start_res = self._api.start_sync_local_fit_files()
            if not start_res or not start_res.get("ok"):
                raise RuntimeError((start_res or {}).get("error") or "监听增量同步启动失败")

            job_id = str(start_res.get("job_id") or "")
            status = self._wait_for_sync_job(job_id)
            result = dict(status.get("result") or {})
            if not status.get("ok") or not result.get("ok"):
                raise RuntimeError(status.get("error") or result.get("error") or status.get("message") or "监听增量同步失败")

            for file_path, signature in candidates.items():
                activity_id = self._lookup_activity_id(file_path)
                if activity_id:
                    self._api.notify_new_track_detected(file_path, activity_id)
                with self._lock:
                    self._synced_signatures[file_path] = signature
        except Exception as exc:
            print(f"[watchdog] 新 FIT 文件批处理同步失败: {exc}")
        finally:
            with self._lock:
                self._batch_running = False
                if self._pending_files and not _APP_SHUTTING_DOWN.is_set():
                    self._arm_debounce_timer_locked()

    def _collect_sync_candidates(self, batch_paths: list[str]) -> dict[str, tuple[int, int]]:
        candidates: dict[str, tuple[int, int]] = {}
        for file_path in batch_paths:
            signature = self._file_signature(file_path)
            if signature is None:
                continue
            with self._lock:
                if self._synced_signatures.get(file_path) == signature:
                    continue
            candidates[file_path] = signature
        return candidates

    def _file_signature(self, file_path: str) -> tuple[int, int] | None:
        try:
            stat = Path(file_path).stat()
        except OSError:
            return None
        return (int(stat.st_size), int(stat.st_mtime_ns))

    def _wait_for_sync_job(self, job_id: str) -> dict[str, Any]:
        while not _APP_SHUTTING_DOWN.is_set():
            status = self._api.get_sync_local_fit_files_status(job_id)
            if not status:
                raise RuntimeError("监听增量同步状态为空")
            if status.get("state") == "done":
                return status
            time.sleep(0.2)
        return {"ok": False, "error": "应用正在退出，监听同步已中止"}

    def _lookup_activity_id(self, file_path: str) -> int:
        lookup = self._api.get_activity_by_file_path(file_path)
        if not lookup or not lookup.get("ok"):
            return 0
        activity = dict(lookup.get("activity") or {})
        return _safe_int(activity.get("id"))


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


class Api:
    """pywebview js_api：轨迹文件、导出、大模型（OpenAI 兼容）等。"""

    REPORT_TERRAIN = "__REPORT_TERRAIN__"
    REPORT_PERSONALIZED = "__REPORT_PERSONALIZED__"

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

    def on_loaded(self) -> None:
        """页面加载完成后显示窗口，解决白屏感。"""
        import webview
        if webview.windows:
            webview.windows[0].show()

    def bind_window(self, window) -> None:
        self._window = window

    def set_watch_service(self, watch_service: FITFolderWatchService) -> None:
        self._watch_service = watch_service

    def _restart_watch_service(self, target_dir: str) -> None:
        if self._watch_service is None:
            return
        self._watch_service.restart(target_dir)

    def notify_frontend_ready(self) -> dict:
        self._frontend_ready = True
        self._flush_pending_track_notifications()
        return {"ok": True}

    def _flush_pending_track_notifications(self) -> None:
        with self._notification_lock:
            pending = list(self._pending_track_notifications)
            self._pending_track_notifications.clear()
        for file_path, activity_id in pending:
            self._dispatch_new_track_notification(file_path, activity_id)

    def _dispatch_new_track_notification(self, file_path: str, activity_id: int = 0) -> None:
        if not self._window:
            return
        js_code = f"window.onNewTrackDetected({json.dumps(file_path)}, {int(activity_id or 0)})"
        try:
            self._window.evaluate_js(js_code)
        except Exception as exc:
            print(f"[watchdog] 前端通知失败: {exc}")

    def notify_new_track_detected(self, file_path: str, activity_id: int = 0) -> None:
        normalized = str(Path(file_path).expanduser().resolve())
        with self._notification_lock:
            if not self._frontend_ready or self._window is None:
                self._pending_track_notifications.append((normalized, int(activity_id or 0)))
                return
        self._dispatch_new_track_notification(normalized, int(activity_id or 0))

    def _new_session_id(self) -> None:
        self._session_id = "session_" + uuid.uuid4().hex[:16]

    def sync_track_context(self, payload_json: str) -> dict:
        """前端完成渲染与 calculateStats 后同步轨迹（含 dist 等），供 call_llm 拼表。"""
        try:
            obj = json.loads(payload_json)
        except json.JSONDecodeError as e:
            return {"ok": False, "error": f"JSON 无效: {e}"}
        self._track_points = obj.get("points") or []
        self._track_placemarks = obj.get("placemarks") or []
        self._track_filename = str(obj.get("filename") or "轨迹")
        self._track_weather = obj.get("weather") if isinstance(obj.get("weather"), dict) else None
        self._chat_messages = []
        self._new_session_id()
        return {"ok": True}

    def reset_llm_session(self) -> dict:
        self._chat_messages = []
        self._new_session_id()
        return {"ok": True}

    def get_llm_config(self) -> dict:
        cfg = llm_backend.load_llm_config()
        app_cfg = resolve_workspace_track_dir(auto_recover=True)
        cfg["local_dir"] = str(app_cfg.get("workspace_track_path") or "")
        cfg["workspace_track_path"] = str(app_cfg.get("workspace_track_path") or "")
        cfg["workspace_track_abs_path"] = str(app_cfg.get("workspace_track_abs_path") or "")
        return {"ok": True, **cfg}

    def save_llm_config(self, provider: str, url: str, model: str, api_key: str, agent_id: str = "", watch_brand: str = "", local_dir: str = "") -> dict:
        try:
            llm_backend.save_llm_config(provider, url, model, api_key, agent_id, watch_brand, local_dir)
            if str(local_dir or "").strip():
                current = load_application_config()
                backup_path = backup_application_config("save_llm_config", current)
                config = persist_application_config({"workspace_track_path": local_dir})
                append_application_audit(
                    "save_llm_config_workspace_track_path",
                    {
                        "previous_path": current.get("workspace_track_abs_path"),
                        "new_path": config.get("workspace_track_abs_path"),
                        "backup_path": backup_path,
                    },
                )
                self._restart_watch_service(str(config.get("workspace_track_abs_path") or ""))
        except OSError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True}

    def get_config(self) -> dict:
        """安全读取全局配置文件，供前端配置页使用。"""
        try:
            config = resolve_workspace_track_dir(auto_recover=True)
            if not config.get("ok"):
                return config
            return {
                "ok": True,
                "config_path": config.get("config_path"),
                "workspace_track_path": config.get("workspace_track_path"),
                "workspace_track_abs_path": config.get("workspace_track_abs_path"),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def save_config(self, new_config_dict: dict) -> dict:
        """保存全局配置，并确保轨迹目录在物理硬盘上存在。"""
        try:
            current = load_application_config()
            payload = dict(current)
            if isinstance(new_config_dict, dict):
                payload.update(new_config_dict)
            if str(payload.get("local_dir") or "").strip() and not str(payload.get("workspace_track_path") or "").strip():
                payload["workspace_track_path"] = payload["local_dir"]
            backup_path = backup_application_config("save_config", current)
            config = persist_application_config(payload)
            status = _inspect_directory_access(str(config.get("workspace_track_abs_path") or ""))
            if not status.get("readable"):
                return {"ok": False, "error": "配置目录不可读取，请检查权限"}
            append_application_audit(
                "save_config",
                {
                    "previous_path": current.get("workspace_track_abs_path"),
                    "new_path": config.get("workspace_track_abs_path"),
                    "backup_path": backup_path,
                },
            )
            return {
                "ok": True,
                "config_path": config.get("config_path"),
                "workspace_track_path": config.get("workspace_track_path"),
                "workspace_track_abs_path": config.get("workspace_track_abs_path"),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}
        finally:
            if 'config' in locals():
                self._restart_watch_service(str(config.get("workspace_track_abs_path") or ""))

    def test_llm_config(self, provider: str, url: str, model: str, api_key: str, agent_id: str = "") -> dict:
        try:
            text = llm_backend.test_llm_connection(
                provider=provider,
                url=url,
                model=model,
                api_key=api_key,
                agent_id=agent_id,
            )
            return {"ok": True, "message": text}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def call_llm(self, prompt: str, sport_type: str = "hiking") -> dict:
        """对话或路书：prompt 为普通用户文本，或魔法串 __REPORT_TERRAIN__ / __REPORT_PERSONALIZED__。"""
        cfg = llm_backend.load_llm_config()
        url = (cfg.get("url") or "").strip()
        if not url:
            return {"ok": False, "error": "API 接口地址为空，请在设置中配置"}

        provider = str(cfg.get("provider") or "local_mcp")
        model = str(cfg.get("model") or "openclaw").strip()
        api_key = str(cfg.get("api_key") or "")
        agent_id = str(cfg.get("agent_id") or "")
        sid = self._session_id

        pts = self._track_points or []
        pms = self._track_placemarks or []
        fn = self._track_filename or "轨迹"
        weather = self._track_weather

        try:
            if prompt == self.REPORT_TERRAIN:
                sys_b = llm_backend.build_base_system_block(
                    sport_type=sport_type,
                    provider=provider,
                    track_filename=fn,
                    points=pts,
                    placemarks=pms,
                    weather_context=weather,
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
                    points=pts,
                    placemarks=pms,
                    weather_context=weather,
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

            user_text = prompt
            if not self._chat_messages:
                sys_c = llm_backend.build_chat_system_block(
                    sport_type=sport_type,
                    provider=provider,
                    track_filename=fn,
                    points=pts,
                    placemarks=pms,
                    weather_context=weather,
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
        return {
            "ok": True,
            "profile": prof.to_dict(),
            "hrr_zones": zones,
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
        result = profile_backend.fetch_mcp_persona(platform)
        if result.get("ok"):
            prof = profile_backend.get_profile()
            zones = profile_backend.compute_hrr_zones(
                prof.resting_hr or 60, prof.max_hr or 190
            )
            return {"ok": True, "profile": prof.to_dict(), "hrr_zones": zones}
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
        }

    def silent_fetch_mcp_persona(self, platform: str) -> dict:
        needs = profile_backend.is_sync_needed_today()
        if not needs:
            cached = profile_backend.read_local_profile()
            return {"ok": True, "already_synced": True, "has_cached": cached is not None}
        result = profile_backend.fetch_mcp_persona(platform)
        if result.get("ok"):
            prof = profile_backend.get_profile()
            return {"ok": True, "already_synced": False, "profile": prof.to_dict(), "has_cached": True}
        return {"ok": True, "already_synced": False, "error": result.get("error"), "has_cached": False}

    def _workspace_track_dir(self) -> str:
        config = init_application_config()
        return str(config.get("workspace_track_abs_path") or "").strip()

    def _build_activity_list_item(self, row: dict) -> dict:
        display_type = _resolve_display_sport_type(row.get("sport_type"), row.get("sub_sport_type"))
        distance_km = _safe_float(row.get("distance") if row.get("distance") is not None else row.get("dist_km"))
        duration_sec = _safe_int(row.get("duration") if row.get("duration") is not None else row.get("duration_sec"))
        avg_pace = row.get("avg_pace")
        if avg_pace is None and distance_km > 0 and duration_sec > 0:
            avg_pace = round(duration_sec / distance_km, 2)
        avg_pace_sec = _safe_int(avg_pace) if avg_pace is not None else None
        avg_hr = _safe_int(row.get("avg_hr")) or None
        calories = row.get("calories")
        if calories is None:
            calories = _estimate_calories(distance_km, duration_sec, avg_hr)
        display_filename = str(row.get("filename") or row.get("file_name") or "")
        title = str(row.get("title") or "").strip() or display_filename or self._guess_record_title(display_type, distance_km, row.get("start_time"), int(row.get("id") or 0))
        timestamp = row.get("start_time") or row.get("updated_at")
        try:
            dt = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")) if timestamp else None
            date_label = dt.strftime("%Y-%m-%d %H:%M") if dt else "--"
        except Exception:
            date_label = str(timestamp or "--")

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
            "distance_km": round(distance_km, 2),
            "duration_sec": duration_sec,
            "avg_pace_sec": avg_pace_sec,
            "avg_hr": avg_hr,
            "calories": _safe_int(calories),
            "gain_m": round(_safe_float(row.get("gain_m")), 1),
            "file_path": str(row.get("file_path") or ""),
            "region": str(row.get("region") or "").strip(),
            "start_lat": _safe_float(row.get("start_lat")) or None,
            "start_lon": _safe_float(row.get("start_lon")) or None,
            "weather": _decode_weather_json(row.get("weather_json")),
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

    def _sync_local_fit_files_impl(self, progress_callback=None) -> dict:
        """按配置文件中的工作目录增量同步 FIT 文件到 activities 表。"""
        try:
            ensure_activity_sync_schema()
            config = resolve_workspace_track_dir(auto_recover=True)
            target_dir = os.path.abspath(os.path.expanduser(str(config.get("workspace_track_abs_path") or "").strip()))
            source_status = dict(config.get("workspace_track_status") or {})
            if not target_dir or not source_status.get("exists") or not source_status.get("is_dir"):
                logger.warning("FIT 同步跳过：目录无效或不存在, target_dir=%s", target_dir)
                result = {
                    "ok": True,
                    "source_dir": "",
                    "scanned": 0,
                    "inserted": 0,
                    "updated": 0,
                    "skipped": 0,
                    "errors": [],
                    "message": "未检测到有效的 FIT 数据目录，请先在配置页选择目录。",
                }
                _emit_sync_progress(progress_callback, stage="completed", current=0, total=0, **result)
                return result

            base = Path(target_dir)
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

    def delete_activities(self, activity_ids: list[int] | None = None) -> dict:
        """批量硬删除：强制确保 FIT 文件与数据库同步。"""
        ensure_activity_sync_schema()
        raw_ids = [int(item) for item in (activity_ids or []) if _safe_int(item)]
        if not raw_ids:
            return {"ok": False, "error": "未选择记录"}
        ids = list(set(raw_ids))
        conn = profile_backend._conn()
        try:
            rows = conn.execute(
                "SELECT id, file_path FROM activities WHERE id IN ({})".format(",".join("?" * len(ids))),
                ids,
            ).fetchall()
            if not rows:
                return {"ok": False, "error": "未找到记录"}

            for row in rows:
                fp = row.get("file_path")
                if fp and os.path.exists(fp):
                    os.remove(fp)

            conn.execute(
                "DELETE FROM activities WHERE id IN ({})".format(",".join("?" * len(ids))),
                ids,
            )
            conn.commit()
            return {"ok": True, "deleted": len(ids)}
        except Exception as e:
            conn.rollback()
            return {"ok": False, "error": str(e)}
        finally:
            conn.close()

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
                           calories,
                           gain_m,
                           file_path,
                           start_lat,
                           start_lon,
                           region,
                           weather_json,
                           updated_at,
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
            return {
                "ok": True,
                "source_dir": source_dir,
                "total": len(records),
                "activity_types": activity_types,
                "page_sizes": SPORT_HUB_PAGE_SIZES,
                "records": records,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_activity_list(self, page: int = 1, page_size: int = 20, sport_filter: str = "all") -> dict:
        """分页返回活动记录基础字段，不返回 track_json 以提升列表响应速度。"""
        try:
            page = max(1, _safe_int(page, 1))
            requested_page_size = _safe_int(page_size, 20)
            page_size = requested_page_size if requested_page_size in SPORT_HUB_PAGE_SIZES else 20
            source_dir, all_records, activity_types = self._query_activity_list_records(sport_filter)
            total = len(all_records)
            total_pages = max(1, (total + page_size - 1) // page_size)
            page = min(page, total_pages)
            offset = (page - 1) * page_size
            records = all_records[offset: offset + page_size]
            return {
                "ok": True,
                "source_dir": source_dir,
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
                "activity_types": activity_types,
                "page_sizes": SPORT_HUB_PAGE_SIZES,
                "records": records,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_activity_detail(self, activity_id: int) -> dict:
        """返回单条活动的详情数据，包含缩略图与统计信息。"""
        try:
            row = self._fetch_activity_row(_safe_int(activity_id))
            if not row:
                return {"ok": False, "error": "未找到该活动记录"}
            record = _build_record_from_row(self, row, 0)
            return {"ok": True, "record": record}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def load_activity_track(self, activity_id: int) -> dict:
        """优先从 SQLite 的 track_json 读取轨迹，支持源文件已删除时复盘。"""
        try:
            row = self._fetch_activity_row(_safe_int(activity_id))
            if not row:
                return {"ok": False, "error": "未找到该活动记录"}

            points = self._decode_points_json(row.get("track_json") or row.get("points_json") or row.get("merged_track_json"))
            if points:
                filename = str(row.get("filename") or row.get("file_name") or "历史轨迹")
                weather = _decode_weather_json(row.get("weather_json"))
                raw_metrics = row.get("advanced_metrics")
                advanced_metrics = _decode_weather_json(raw_metrics) if isinstance(raw_metrics, str) else (raw_metrics or {})
                return {
                    "ok": True,
                    "filename": filename,
                    "advanced_metrics": advanced_metrics,
                    "activity": {
                        "id": _safe_int(row.get("id")),
                        "sport_type": str(row.get("sport_type") or "unknown"),
                        "sub_sport_type": str(row.get("sub_sport_type") or "unknown"),
                        "region": str(row.get("region") or "").strip(),
                        "weather": weather,
                    },
                    "data": {
                        "points": points,
                        "placemarks": [],
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
                return loaded

            return {"ok": False, "error": "当前活动没有可复盘的轨迹数据"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_trace_activity_history(self) -> dict:
        """返回轨迹分析工具使用的活动记录列表，与个人运动数据页保持同源一致。
        与 get_activity_list_snapshot 共用 SQLite 数据源，不触发 FIT 同步。
        """
        try:
            source_dir, records, _ = self._query_activity_list_records("all")

            for rec in records:
                rec["dist_km"] = rec.pop("distance_km", rec.get("dist_km"))
                rec["valid"] = bool(rec.get("has_track"))
                rec["cityName"] = (rec.get("region") or "").strip() or "未知地点"
                rec["has_local_file"] = bool(str(rec.get("file_path") or "").strip())

            return {
                "ok": True,
                "source_dir": source_dir,
                "records": records,
                "total": len(records),
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

    def _guess_record_title(self, sport_type: str, dist_km: float, _start_time: str | None, idx: int) -> str:
        race_names = [
            "都江堰双遗半程马拉松",
            "成都马拉松",
            "青城山越野挑战赛",
            "天府绿道晨跑",
            "龙泉山长距离拉练",
            "都江堰山径耐力课",
        ]
        if 20.5 <= dist_km <= 21.7:
            return "都江堰双遗半程马拉松"
        if 41.0 <= dist_km <= 43.0:
            return "成都马拉松"
        sport_map = {
            "running": "城市路跑训练",
            "trail_running": "山地越野训练",
            "hiking": "耐力徒步穿越",
            "mountaineering": "高海拔登山训练",
            "cycling": "长距离骑行训练",
            "road_cycling": "公路耐力骑行",
            "mountain_biking": "山地骑行路线",
            "walking": "恢复步行记录",
            "swimming": "游泳专项训练",
            "driving": "自驾路线记录",
        }
        return race_names[idx % len(race_names)] if idx < len(race_names) else sport_map.get(sport_type, "综合训练记录")


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
    max_hr = _safe_int(row.get("max_hr")) or (avg_hr + 12 if avg_hr else None)
    avg_pace = row.get("avg_pace")
    pace_sec = _safe_int(avg_pace) if avg_pace is not None else (int(duration_sec / dist_km) if dist_km > 0 and duration_sec > 0 else None)
    calories = _safe_int(row.get("calories")) or _estimate_calories(dist_km, duration_sec, avg_hr)
    display_type = _resolve_display_sport_type(row.get("sport_type"), row.get("sub_sport_type"))
    title = str(row.get("title") or "").strip() or api_self._guess_record_title(display_type, dist_km, row.get("start_time"), idx)
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
    if raw_metrics_json and isinstance(raw_metrics_json, str):
        try:
            adv_metrics = json.loads(raw_metrics_json)
        except (json.JSONDecodeError, ValueError):
            adv_metrics = {}
    else:
        adv_metrics = {}

    radar_data = RadarScoreEngine.build_radar_profile(display_type, adv_metrics, {"max_hr": max_hr or 190})

    raw_for_engine = {
        "distance_km": dist_km,
        "duration_sec": duration_sec,
        "avg_pace_sec": pace_sec,
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
        "region": str(row.get("region") or "").strip(),
        "start_lat": _safe_float(row.get("start_lat")) or None,
        "start_lon": _safe_float(row.get("start_lon")) or None,
        "weather": _decode_weather_json(row.get("weather_json")),
        "file_path": row.get("file_path") or "",
        "has_track": bool(points),
        "has_local_file": bool(str(row.get("file_path") or "").strip() and os.path.isfile(str(row.get("file_path") or "").strip())),
        "thumbnail_points": detail["thumbnail_points"],
        "detail": detail,
    }


    def _mock_person_records(self) -> list[dict]:
        mock_rows = [
            {"id": 9001, "filename": "dujiangyan_hm.fit", "sport_type": "running", "dist_km": 21.1, "duration_sec": 6420, "gain_m": 82, "avg_hr": 158, "max_hr": 176, "file_path": "", "start_time": "2026-03-22T07:30:00Z", "points_json": json.dumps([{"lat": 30.991 + i * 0.001, "lon": 103.65 + i * 0.0012} for i in range(24)])},
            {"id": 9002, "filename": "chengdu_marathon.fit", "sport_type": "running", "dist_km": 42.2, "duration_sec": 13920, "gain_m": 126, "avg_hr": 162, "max_hr": 181, "file_path": "", "start_time": "2025-10-27T07:00:00Z", "points_json": json.dumps([{"lat": 30.67 + i * 0.0008, "lon": 104.06 + i * 0.0006} for i in range(36)])},
            {"id": 9003, "filename": "qingcheng_trail.fit", "sport_type": "trail_running", "dist_km": 18.4, "duration_sec": 8100, "gain_m": 968, "avg_hr": 154, "max_hr": 172, "file_path": "", "start_time": "2026-01-12T06:45:00Z", "points_json": json.dumps([{"lat": 30.90 + i * 0.0009, "lon": 103.55 + i * 0.001} for i in range(28)])},
            {"id": 9004, "filename": "long_ride.fit", "sport_type": "cycling", "dist_km": 86.5, "duration_sec": 11340, "gain_m": 540, "avg_hr": 146, "max_hr": 168, "file_path": "", "start_time": "2025-12-08T08:10:00Z", "points_json": json.dumps([{"lat": 30.58 + i * 0.0006, "lon": 104.18 + i * 0.0009} for i in range(32)])},
        ]
        return [_build_record_from_row(self, row, idx) for idx, row in enumerate(mock_rows)]


    def _build_results_payload(self, records: list[dict]) -> dict:
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

        if not result_entries:
            result_entries = [
                {"activity_id": 9001, "month": "2025-03", "title": "都江堰双遗半程马拉松", "category": "half_marathon", "finish_time_sec": 6580, "avg_hr": 156},
                {"activity_id": 9002, "month": "2025-10", "title": "成都马拉松", "category": "full_marathon", "finish_time_sec": 14280, "avg_hr": 163},
                {"activity_id": 9005, "month": "2026-03", "title": "都江堰双遗半程马拉松", "category": "half_marathon", "finish_time_sec": 6420, "avg_hr": 158},
                {"activity_id": 9006, "month": "2026-10", "title": "成都马拉松", "category": "full_marathon", "finish_time_sec": 13920, "avg_hr": 162},
            ]

        result_entries.sort(key=lambda item: item["month"])
        return {"entries": result_entries}

    def _build_honors_payload(self, records: list[dict]) -> list[dict]:
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

        if not honor_items:
            honor_items = [
                {"year": "2026", "month": "03", "activity_id": 9001, "title": "都江堰双遗半程马拉松", "subtitle": "半程马拉松 PB", "photo_label": "赛事照片占位"},
                {"year": "2025", "month": "10", "activity_id": 9002, "title": "成都马拉松", "subtitle": "全马完赛", "photo_label": "赛事照片占位"},
            ]

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

    def get_person_sport_hub_data(self) -> dict:
        """返回个人运动数据面板下半区所需的结构化 JSON。"""
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
            if not records:
                records = self._mock_person_records()

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

    def load_local_track(self, file_path: str) -> dict:
        """根据本地路径读取并解析轨迹文件，返回与 parse_track_file 一致的结构。"""
        try:
            return profile_backend.load_local_track(file_path)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_activity_by_file_path(self, file_path: str) -> dict:
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

    def load_activity_track_by_file_path(self, file_path: str) -> dict:
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

    def import_track(self, file_path: str = "", duplicate_action: str = "", new_filename: str = "") -> dict:
        """统一导入并入库轨迹文件，由 Python 后端完成解析和持久化。"""
        import webview
        from webview import FileDialog

        target_path = (file_path or "").strip()
        if not target_path:
            if not webview.windows:
                return {"ok": False, "error": "窗口未就绪"}
            paths = webview.windows[0].create_file_dialog(
                FileDialog.OPEN,
                file_types=("Track files (*.fit;*.gpx;*.kml)",),
            )
            if not paths:
                return {"ok": False, "cancelled": True}
            target_path = paths[0] if isinstance(paths, (list, tuple)) else paths

        try:
            return profile_backend.ingest_activity_file(
                target_path,
                duplicate_action=duplicate_action,
                new_filename=new_filename or None,
            )
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def update_activity_sport_type(self, activity_id: int, sport_type: str) -> dict:
        try:
            profile_backend.update_activity_sport_type(activity_id, sport_type)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def validate_fit_directory(self, local_dir: str) -> dict:
        """验证本地 FIT 目录的有效性（存在、可读写），不扫描文件内容。"""
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

    def scan_fit_directory(self, local_dir: str = "") -> dict:
        """从配置文件夹扫描所有 fit 文件，解析后返回带 GPS 有效性标记的轨迹列表。"""
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

    def check_duplicate_track(self, act_data: dict) -> dict:
        """检查轨迹是否重复"""
        try:
            start_time = act_data.get("start_time")
            start_time_utc = act_data.get("start_time_utc")
            
            res = profile_backend.check_duplicate_activity(
                start_time=start_time,
                dist_km=act_data.get("dist_km", 0.0),
                duration_sec=act_data.get("duration_sec", 0),
                points_json=act_data.get("points_json", []),
                start_time_utc=start_time_utc
            )
            return {"ok": True, **res}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def save_activity(self, data: dict) -> dict:
        """保存运动记录，自动将源文件复制到 local_tracks 目录。"""
        try:
            # Check for duplicate action
            dup_action = data.get("_duplicate_action")
            if dup_action == "skip":
                return {"ok": True, "skipped": True}

            src = data.get("_src_path")
            new_filename = data.get("_new_filename")
            
            if src:
                local_path = profile_backend.copy_track_to_local(src, new_filename)
                data["file_path"] = local_path
            else:
                data["file_path"] = None
                
            if data.get("points_json") and len(data["points_json"]) > 0:
                data["start_time"] = data["points_json"][0].get("time")
                
            profile_backend.save_activity(data)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True}


def _migrate_advanced_metrics() -> dict[str, Any]:
    """启动迁移：为所有缺少 advanced_metrics 的活动记录重新计算并填充。"""
    ensure_activity_sync_schema()
    conn = profile_backend._conn()
    try:
        rows = conn.execute(
            """
            SELECT id, track_json, points_json, sport_type
            FROM activities
            WHERE deleted_at IS NULL
              AND (advanced_metrics IS NULL OR advanced_metrics = '')
              AND (track_json IS NOT NULL AND track_json != '')
            ORDER BY id ASC
            """
        ).fetchall()
        if not rows:
            logger.info("数据迁移: 所有记录均已包含 advanced_metrics，无需迁移")
            return {"ok": True, "migrated": 0}

        logger.info("数据迁移: 发现 %s 条记录缺少 advanced_metrics，开始重新计算...", len(rows))
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
                    advanced_json = json.dumps(advanced, ensure_ascii=False)
                    conn.execute(
                        "UPDATE activities SET advanced_metrics = ?, updated_at = datetime('now') WHERE id = ?",
                        (advanced_json, int(row["id"])),
                    )
                    migrated += 1
                    if migrated % 10 == 0:
                        conn.commit()
            except Exception as exc:
                logger.warning("数据迁移: 记录 id=%s 计算失败: %s", row.get("id"), exc)
                continue
        conn.commit()
        logger.info("数据迁移完成: 成功迁移 %s / %s 条记录", migrated, len(rows))
        return {"ok": True, "migrated": migrated, "total": len(rows)}
    except Exception as e:
        conn.rollback()
        logger.exception("数据迁移失败: %s", e)
        return {"ok": False, "error": str(e), "migrated": 0}
    finally:
        conn.close()


def main() -> None:
    import webview

    _migrate_advanced_metrics()
    url = str(html_file().resolve())
    api = Api()
    window = webview.create_window(
        "3D 轨迹分析仪 - AI 增强版",
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
