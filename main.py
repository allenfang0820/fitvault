#!/usr/bin/env python3
"""使用 pywebview 在桌面窗口中加载「脉图」单页 HTML。"""

from __future__ import annotations

import json
import logging
import os
import re
import runpy
import shutil
import socket
import sqlite3
import sys
import threading
import time
import uuid
import zipfile
from urllib.parse import urlparse
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

import llm_backend  # noqa: F401 -- PyInstaller bundles LLM 模块
import garmin_sync  # noqa: F401 -- PyInstaller bundles Garmin sync provider
import coros_sync  # noqa: F401 -- PyInstaller bundles COROS sync provider
import track_backend  # noqa: F401 -- PyInstaller bundles track_backend
import profile_backend  # noqa: F401 -- PyInstaller bundles profile 模块
from fit_engine import FITCoreEngine
from metrics_resolver import MetricsResolver, SemanticSportsEngine, build_training_effect, _build_environment_challenge_block  # V9.4.0 修复 NameError:build_training_effect 已在 metrics_resolver.py:2760 定义, 此处补 import;V_ENV.1.16:补 _build_environment_challenge_block

DEBUG_MODE = False
APP_VERSION = "V1.2.0"

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

HTML_FILENAME = "track.html"
APP_ICON_FILENAME = "assets/app_icon.icns"

# ─── Managed Workspace ───────────────────────────────────────────
CURRENT_SCHEMA_VERSION = 2
CURRENT_METRICS_VERSION = 6  # v6: P1-P4 雷达解释字段与评分上下文升级
# v3 → v4 变更要点(2026-Q2):
# 1) calculate_vam 重写为"有效爬坡段"算法(rolling median + 段级过滤),
#    消除 1m/5s 海拔噪声被算成 720 m/h 的根因。
# 2) _rolling_aggregate_radar_metrics 增加 _is_valid_vam_activity 过滤
#    (cycling/road/mtb/running ≥ 20m@1km, trail_running ≥ 30m, hiking ≥ 50m),
#    避免 gain_m=0/4/5m 的通勤旧 VAM 污染雷达图。
# v4 → v5 变更要点(2026-Q2):
# 1) 骑行无氧优先使用 5/15/30/60s 功率与 W/kg。
# 2) 无功率时速度 fallback 只做低可信度样本,雷达评分封顶。
# v5 → v6 变更要点(2026-Q2):
# 1) endurance detail / confidence / source / sample_count 参与雷达解释。
# 2) radar.dimensions 透传 confidence/source/sample_count/reason 元信息。
# 3) stability/climbing/threshold/anaerobic 的 source/confidence 参与聚合解释。
# 触发条件:历史 advanced_metrics.metrics_version < 6 → 由
# api_force_rebuild_radar_data / rebuild_advanced_metrics_for_all_activities 强制清洗重建。
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
_PROCESS_START_PERF = time.perf_counter()
_STARTUP_TIMELINE_LOCK = threading.Lock()
_STARTUP_TIMELINE: list[dict[str, Any]] = []
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
    "lap_swimming": 9,
    "open_water": 9,
    "open_water_swimming": 9,
    "stand_up_paddleboarding": 10,
    "paddling": 10,
    "driving": 11,
    "cardio": 12,
    "strength_training": 13,
    "yoga": 14,
    "pilates": 15,
    "hiit": 16,
    "breathing": 17,
    "flexibility_training": 18,
}


# ══════════════════════════════════════════════════════════════════
# MTDI 轨迹难度计算 — Canonical 层
# 契约 §2.1 / §2.2 / §2.4: 难度为唯一可信计算，禁止前端复算
# 输入: dist_km / gain_m / max_alt_m / max_single_climb_m / sport_type
# 输出: mtdi_score (0-∞) + mtdi_level (1-8) + mtdi_level_name
# ══════════════════════════════════════════════════════════════════

MTDI_LEVEL_THRESHOLDS: tuple[float, ...] = (8, 16, 29, 46, 76, 111, 181)


def calculate_track_difficulty(
    dist_km: float,
    gain_m: float,
    max_alt_m: float,
    max_single_climb_m: float,
    sport_type: str = "running",
) -> dict[str, Any]:
    """V4.0 治理:已下沉至 MetricsResolver._calculate_track_difficulty,此函数为过渡期透传兼容层。

    严禁修改此函数体添加任何额外逻辑(透传代码模板约束)。
    完整实现见 metrics_resolver.py:MetricsResolver._calculate_track_difficulty
    """
    return MetricsResolver._calculate_track_difficulty(
        dist_km, gain_m, max_alt_m, max_single_climb_m, sport_type
    )


POWER_ELIGIBLE_TYPES: frozenset[str] = frozenset({
    "running", "trail_running", "treadmill_running",
    "cycling", "road_cycling", "mountain_biking",
})

OUTDOOR_LAND_GAIN_TYPES: frozenset[str] = frozenset({
    "running", "trail_running", "treadmill_running",
    "cycling", "road_cycling", "mountain_biking",
    "hiking", "mountaineering", "walking",
})

# 活动列表字段展示规则：仅这些类型显示累计爬升
# 范围：跑步、骑行、徒步、登山
LIST_GAIN_ELIGIBLE_TYPES: frozenset[str] = frozenset({
    "running", "trail_running", "treadmill_running",
    "cycling", "road_cycling", "mountain_biking",
    "hiking", "mountaineering", "walking",
})

# 活动列表字段展示规则：仅这些类型显示标准化功率
# 范围：跑步、骑行
LIST_POWER_ELIGIBLE_TYPES: frozenset[str] = frozenset({
    "running", "trail_running", "treadmill_running",
    "cycling", "road_cycling", "mountain_biking", "indoor_cycling",
})

CYCLING_REVIEW_TYPES: frozenset[str] = frozenset({
    "cycling", "road_cycling", "mountain_biking", "indoor_cycling",
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

# V9.4.5:圈速表列规则真理源(后端决定,前端只消费 detail.lap_columns)
# V10.0 P1-1:骑行类活动圈表升级为 9 列,字段对齐自动切圈 P0-1 输出
#   圈号 + 圈距离 + 圈用时 + 平均速度 + 平均心率 + 平均功率 + 最大功率 + NP + 累计爬升
#   跑步圈表保持基础列,左右平衡按数据存在性在 detail 构建阶段追加。
LAP_COLUMN_PRESETS: dict[str, list[str]] = {
    "running": ["avg_pace", "avg_hr", "cadence", "gct", "power"],
    "treadmill_running": ["avg_pace", "avg_hr", "cadence", "gct", "power"],
    "trail_running": ["avg_pace", "avg_hr", "max_hr", "ascent", "descent"],
    "hiking": ["avg_pace", "avg_hr", "max_hr", "ascent", "descent"],
    "mountaineering": ["avg_pace", "avg_hr", "max_hr", "ascent", "descent"],
    "walking": ["avg_pace", "avg_hr", "max_hr", "ascent", "descent"],
    # V10.0 P1-1:户外骑行升级为 9 列
    "cycling": ["lap_no", "lap_distance_km", "elapsed_sec", "avg_speed_kmh", "avg_hr", "avg_power", "max_power", "normalized_power", "total_ascent"],
    "road_cycling": ["lap_no", "lap_distance_km", "elapsed_sec", "avg_speed_kmh", "avg_hr", "avg_power", "max_power", "normalized_power", "total_ascent"],
    "mountain_biking": ["lap_no", "lap_distance_km", "elapsed_sec", "avg_speed_kmh", "avg_hr", "avg_power", "max_power", "normalized_power", "total_ascent"],
    "indoor_cycling": ["avg_pace", "avg_hr", "power"],
    "swimming": ["avg_hr", "swolf", "stroke_style", "length_distance"],
    "lap_swimming": ["avg_hr", "swolf", "stroke_style", "length_distance"],
    "open_water": ["avg_hr", "stroke_distance"],
    "open_water_swimming": ["avg_hr", "stroke_distance"],
    "cardio": ["avg_hr", "power", "calories"],
    "cardio_training": ["avg_hr", "power", "calories"],
}


def resolve_lap_columns(sport_type: str) -> list[str]:
    """V9.4.5:详情页圈速表列真理源(后端计算,前端消费)。"""
    sport = (sport_type or "").lower()
    return list(LAP_COLUMN_PRESETS.get(sport, []))


def resolve_detail_lap_columns(sport_type: str, laps: list[dict[str, Any]] | None = None) -> list[str]:
    """Return visible detail lap columns; optional columns only appear when data exists."""
    columns = resolve_lap_columns(sport_type)
    sport = (sport_type or "").lower()
    if sport in ("running", "treadmill_running"):
        has_balance = any(
            isinstance(lap, dict) and lap.get("stance_time_balance_pct") is not None
            for lap in (laps or [])
        )
        if has_balance and "stance_balance" not in columns:
            insert_at = columns.index("gct") + 1 if "gct" in columns else len(columns)
            columns.insert(insert_at, "stance_balance")
    return columns


WATER_METRIC_DISPLAY_TYPES = {
    "swimming",
    "lap_swimming",
    "open_water",
    "open_water_swimming",
    "stand_up_paddleboarding",
    "paddling",
}


def _resolve_activity_list_dynamic_columns(activity_types: list[str]) -> list[str]:
    types = set(activity_types or [])
    dynamic_columns: list[str] = []
    if types & LIST_GAIN_ELIGIBLE_TYPES:
        dynamic_columns.append("gain")
    if types & WATER_METRIC_DISPLAY_TYPES:
        dynamic_columns.append("swolf")
    if types & LIST_POWER_ELIGIBLE_TYPES:
        dynamic_columns.append("np")
    return dynamic_columns


def _resolve_activity_list_dynamic_columns_for_rows(rows: list[dict[str, Any]]) -> list[str]:
    visible_types = [
        _resolve_display_sport_type(row.get("sport_type"), row.get("sub_sport_type"))
        for row in (rows or [])
    ]
    return _resolve_activity_list_dynamic_columns(visible_types)

_ACTIVITY_SYNC_SCHEMA_LOCK = threading.Lock()
_ACTIVITY_SYNC_SCHEMA_READY_FOR: str | None = None
_APP_SHUTTING_DOWN = threading.Event()
PROFILE_SYNC_INTERVAL_SEC = 5 * 60
PROFILE_STARTUP_SYNC_DELAY_SEC = PROFILE_SYNC_INTERVAL_SEC
REGION_ENRICH_STARTUP_DELAY_SEC = 20.0
LIST_METRIC_BACKFILL_DELAY_SEC = 15.0
WEATHER_BACKFILL_STARTUP_DELAY_SEC = 18.0
FIT_WATCH_STABLE_SEC = 2.0
FIT_WATCH_POLL_INTERVAL_SEC = 1.5
ZIP_MAX_MEMBERS = 500
ZIP_MAX_MEMBER_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024
ZIP_COPY_CHUNK_BYTES = 1024 * 1024

# V10.1 误导入健康数据防护(契约 §2.2 fit_sdk 严格语义:仅运动数据入库)
# 误导入阈值,命中任一即跳过(走 skipped 通道,不算 error,不动 AI Snapshot)
# - MIN_FIT_FILE_SIZE_KB: 健康监测/HRV/压力监测等 FIT 通常 < 5 KB
# - MIN_FIT_DISTANCE_M: 实际运动通常 ≥ 100m,健康数据 distance=0
# - MIN_FIT_RECORD_COUNT: 运动 record ≥ 30 条(约 30 秒以上)
MIN_FIT_FILE_SIZE_KB = 5.0
MIN_FIT_DISTANCE_M = 100.0
MIN_FIT_RECORD_COUNT = 30
ZIP_ALLOWED_SUFFIXES = frozenset({".fit"})
WEATHER_BACKFILL_BATCH_LIMIT = 30
WEATHER_BACKFILL_RETRY_COOLDOWN_SEC = 6 * 60 * 60
WEATHER_BACKFILL_MAX_ATTEMPTS = 5


def app_base_dir() -> Path:
    """开发模式为脚本所在目录；PyInstaller 打包后为 _MEIPASS。"""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        meipass = Path(sys._MEIPASS)
        candidates = [
            meipass.parent / "Resources",
            Path(sys.executable).resolve().parent.parent / "Resources",
            meipass,
        ]
        for candidate in candidates:
            if (candidate / HTML_FILENAME).is_file():
                return candidate
        return meipass
    return Path(__file__).resolve().parent


def html_file() -> Path:
    path = app_base_dir() / HTML_FILENAME
    if not path.is_file():
        raise FileNotFoundError(f"未找到页面文件: {path}")
    return path


def app_icon_file() -> Path:
    return app_base_dir() / APP_ICON_FILENAME


def help_markdown_file() -> Path:
    return app_base_dir() / "docs" / "脉图帮助说明.md"


def load_help_markdown() -> str:
    path = help_markdown_file()
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FileNotFoundError(f"未找到帮助说明文档: {path}") from exc


def set_runtime_app_icon() -> None:
    """Best-effort Dock icon setup for direct Python runs on macOS."""
    try:
        icon_path = app_icon_file()
        if not icon_path.is_file():
            return
        from AppKit import NSApplication, NSImage

        image = NSImage.alloc().initWithContentsOfFile_(str(icon_path))
        if image:
            NSApplication.sharedApplication().setApplicationIconImage_(image)
    except Exception as exc:
        logger.debug("设置运行时图标失败: %s", exc)


def apply_macos_native_window_chrome(window: Any) -> bool:
    """Use a transparent macOS titlebar while keeping native traffic-light buttons."""
    if sys.platform != "darwin":
        return False
    try:
        native_window = getattr(window, "native", None)
        if native_window is None:
            return False

        def _apply() -> None:
            import AppKit

            full_size_mask = getattr(
                AppKit,
                "NSWindowStyleMaskFullSizeContentView",
                getattr(AppKit, "NSFullSizeContentViewWindowMask", 1 << 15),
            )
            title_hidden = getattr(AppKit, "NSWindowTitleHidden", 1)
            native_window.setStyleMask_(native_window.styleMask() | full_size_mask)
            native_window.setTitlebarAppearsTransparent_(True)
            native_window.setTitleVisibility_(title_hidden)
            native_window.setMovableByWindowBackground_(False)
            native_window.standardWindowButton_(AppKit.NSWindowCloseButton).setHidden_(False)
            native_window.standardWindowButton_(AppKit.NSWindowMiniaturizeButton).setHidden_(False)
            native_window.standardWindowButton_(AppKit.NSWindowZoomButton).setHidden_(False)

        from PyObjCTools import AppHelper

        AppHelper.callAfter(_apply)
        return True
    except Exception as exc:
        logger.debug("应用 macOS 原生窗口样式失败: %s", exc)
        return False


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
        "sup": "stand_up_paddleboarding",
        "standup_paddleboarding": "stand_up_paddleboarding",
        "stand_up_paddle": "stand_up_paddleboarding",
        "paddleboarding": "stand_up_paddleboarding",
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
        "lap_swimming": "lap_swimming",
        "open_water": "open_water",
        "open_water_swimming": "open_water_swimming",
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


def _resolve_water_metric(
    display_type: Any,
    sub_sport_type: Any,
    swolf_raw: Any,
) -> tuple[float | None, str | None, str | None]:
    """Return display value/label/kind for water sports using the legacy swolf column."""
    display_token = _normalize_activity_token(display_type, "")
    sub_token = _normalize_activity_token(sub_sport_type, "")
    value = _safe_float(swolf_raw, None)
    if value is None or display_token not in WATER_METRIC_DISPLAY_TYPES:
        return None, None, None
    if sub_token == "lap_swimming" or display_token in ("swimming", "lap_swimming"):
        return value, "平均SWOLF", "swolf"
    return value, "平均划水距离", "stroke_distance"


_FIT_WATER_METRIC_CACHE: dict[str, dict[str, float | None]] = {}


def _read_water_metrics_from_fit(file_path: Any) -> dict[str, float | None]:
    path_text = str(file_path or "").strip()
    if not path_text:
        return {"swolf": None, "stroke_distance": None}
    if path_text in _FIT_WATER_METRIC_CACHE:
        return _FIT_WATER_METRIC_CACHE[path_text]

    metrics = {"swolf": None, "stroke_distance": None}
    try:
        path = Path(path_text).expanduser()
        if not path.is_file():
            _FIT_WATER_METRIC_CACHE[path_text] = metrics
            return metrics

        parsed = FITCoreEngine.parse_fit_file(path)
        basic = parsed.get("basic_info") or {}
        stroke_value = _safe_float(
            parsed.get("avg_stroke_distance") or basic.get("avg_stroke_distance"),
            None,
        )
        if stroke_value and stroke_value > 0:
            metrics["stroke_distance"] = stroke_value

        from fitparse import FitFile

        fit = FitFile(str(path))
        lap_swolf_values: list[float] = []
        for msg in fit.get_messages("lap"):
            vals = {field.name: field.value for field in msg}
            raw_swolf = _safe_float(vals.get("avg_swolf"), None)
            if raw_swolf and raw_swolf > 0:
                lap_swolf_values.append(raw_swolf)
                continue
            lengths = _safe_float(vals.get("num_lengths"), 0.0) or 0.0
            cycles = _safe_float(vals.get("total_strokes") or vals.get("total_cycles"), 0.0) or 0.0
            timer = _safe_float(vals.get("total_timer_time"), 0.0) or 0.0
            if lengths > 0 and cycles > 0 and timer > 0:
                lap_swolf_values.append((cycles / lengths) + (timer / lengths))
        if lap_swolf_values:
            metrics["swolf"] = round(sum(lap_swolf_values) / len(lap_swolf_values))
    except Exception:
        pass
    _FIT_WATER_METRIC_CACHE[path_text] = metrics
    return metrics


def _resolve_water_metric_for_row(
    display_type: Any,
    sub_sport_type: Any,
    swolf_raw: Any,
    file_path: Any = None,
) -> tuple[float | None, str | None, str | None]:
    value, label, kind = _resolve_water_metric(display_type, sub_sport_type, swolf_raw)
    return value, label, kind


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


# 任务 2: 详情 API 必需列白名单
# 维护规则:
#   1. 本白名单由 _fetch_activity_row 全部调用点(详情/复盘/轨迹加载/地标)实际消费的 row 字段驱动
#   2. 任何向这些调用方引入新字段的改动,必须同步更新本白名单
#   3. 反之,向本白名单添加新列前必须先确认有调用方实际消费
#   4. 严禁添加仅用于 AI/审计/调试的字段(如 shadow_diff_json 的扩展、debug 标记)
#   5. 大体积字段(advanced_metrics/track_json)必须在所有调用方都确认必要时才纳入
DETAIL_API_REQUIRED_COLUMNS: tuple[str, ...] = (
    # 基础标识
    "id",
    "filename",
    "file_name",
    "title",
    "title_source",
    # 运动类型
    "sport_type",
    "sub_sport_type",
    # 时间
    "start_time",
    "start_time_utc",
    "updated_at",
    # 距离/时长
    "dist_km",
    "distance",
    "duration",
    "duration_sec",
    "avg_pace",
    # 心率
    "avg_hr",
    "max_hr",
    # 热量
    "calories",
    # 列表/详情共用展示指标
    "avg_power",
    "max_power",
    "normalized_power",
    "avg_stroke_distance",
    "swolf",
    # 海拔/爬升
    "gain_m",
    "max_alt_m",
    "min_alt_m",
    "total_descent_m",
    "up_count",
    "down_count",
    "max_single_climb_m",
    "difficulty_score",
    "report_metrics_version",
    "avg_grade_pct",
    "max_slope_pct",
    "min_slope_pct",
    "uphill_pct",
    "downhill_pct",
    # 地理
    "start_lat",
    "start_lon",
    "region",
    "region_status",
    "region_display",
    "weather_json",
    "weather_status",
    "weather_updated_at",
    "weather_attempt_count",
    "weather_error",
    # 文件/设备
    "file_path",
    "device_name",
    # 审计(保留 shadow_diff 但前端不展示,符合 §六)
    "shadow_diff_json",
    # 圈速(任务 1 引入)
    "laps_json",
    # 曲线(复盘模块消费)
    "hr_curve",
    "speed_curve",
    "cadence_curve",
    "hr_zone_distribution",
    # V9.4.4:Training Effect 训练收益(Firstbeat 私有字段)
    "aerobic_training_effect",
    "anaerobic_training_effect",
    "is_race",
    "is_event",
    "is_intermittent",
    "processing_status",
    "processing_error",
    # 轨迹(仅用于缩略图采样 + 轨迹加载)
    "track_json",
    "points_json",
    # WHERE 子句使用
    "deleted_at",
)
API_CODE_EXTERNAL_SERVICE = 3001
API_CODE_FILE_IO = 4001
API_CODE_DB = 5001
API_CODE_INTERNAL = 9001


def _new_trace_id() -> str:
    return uuid.uuid4().hex[:12]


def _startup_elapsed_ms() -> float:
    return round((time.perf_counter() - _PROCESS_START_PERF) * 1000.0, 2)


def _record_startup_event(name: str, **fields: Any) -> None:
    event = {
        "name": str(name),
        "elapsed_ms": _startup_elapsed_ms(),
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    if fields:
        event.update(fields)
    with _STARTUP_TIMELINE_LOCK:
        _STARTUP_TIMELINE.append(event)
        if len(_STARTUP_TIMELINE) > 200:
            del _STARTUP_TIMELINE[:-200]


def _startup_timeline_snapshot() -> list[dict[str, Any]]:
    with _STARTUP_TIMELINE_LOCK:
        return [dict(item) for item in _STARTUP_TIMELINE]


def _api_success(data: dict[str, Any] | None = None, msg: str = "ok", **legacy_fields: Any) -> dict[str, Any]:
    # 任务 3 (P1-3):严格遵守 fit-arch-contrac §三 统一响应结构 {code, msg, data, traceId}
    # 移除 response.update(payload) 双重包装,所有 payload 字段仅通过 res.data.xxx 访问
    payload = dict(data or {})
    if legacy_fields:
        payload.update(legacy_fields)
    return {
        "ok": True,
        "code": API_CODE_OK,
        "msg": msg,
        "data": payload,
        "traceId": _new_trace_id(),
    }


def _api_error(code: int, msg: str, data: dict[str, Any] | None = None, **legacy_fields: Any) -> dict[str, Any]:
    # 任务 3 (P1-3):严格遵守 fit-arch-contrac §三 统一响应结构
    # 保留 error 顶层字段(契约 §3.1 过渡期兼容),移除 payload 派生
    payload = dict(data or {})
    if legacy_fields:
        payload.update(legacy_fields)
    return {
        "ok": False,
        "code": code,
        "msg": msg,
        "error": msg,  # 过渡期兼容:error 字段保留在顶层
        "data": payload,
        "traceId": _new_trace_id(),
    }


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


def _fatigue_review_weather_float(value: Any) -> float | None:
    num = _safe_optional_float(value)
    return num if num is not None else None


def _fatigue_review_temperature(value: Any) -> float | None:
    temp = _fatigue_review_weather_float(value)
    if temp is None:
        return None
    return temp if -60.0 <= temp <= 70.0 else None


def _build_fatigue_review_environment_context(
    weather: dict[str, Any] | None = None,
    avg_temperature: Any = None,
    context_tags: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build review AI environmental facts without turning neutral weather into risk tags."""
    weather = weather if isinstance(weather, dict) else {}
    context_tags = context_tags if isinstance(context_tags, dict) else {}
    temp = _fatigue_review_temperature(avg_temperature)
    if temp is None:
        temp = _fatigue_review_temperature(
            weather.get("temperature_c")
            if weather.get("temperature_c") is not None
            else weather.get("temperature")
            if weather.get("temperature") is not None
            else weather.get("avg_temperature")
        )
    humidity = _fatigue_review_weather_float(weather.get("humidity"))
    if humidity is not None and not (0.0 <= humidity <= 100.0):
        humidity = None
    wind = _fatigue_review_weather_float(weather.get("wind_speed_kmh"))
    if wind is not None and wind < 0:
        wind = None
    label = str(weather.get("weather_label") or "").strip()
    observed_date = str(weather.get("observed_date") or "").strip()
    observed_hour = _safe_int(weather.get("observed_hour"), -1)
    has_weather = any(value is not None and value != "" for value in (temp, humidity, wind, label, observed_date))

    encoded_tags = json.dumps(context_tags, ensure_ascii=False)
    if "Extreme" in encoded_tags or "极端" in encoded_tags or "High (高" in encoded_tags or "高海拔" in encoded_tags:
        pressure_level = "high"
    elif context_tags:
        pressure_level = "moderate"
    elif temp is not None and temp >= 25.0:
        pressure_level = "moderate"
    elif temp is not None and temp >= 20.0:
        pressure_level = "mild"
    else:
        pressure_level = "none"

    parts: list[str] = []
    if label:
        parts.append(f"天气{label}")
    if temp is not None:
        parts.append(f"{temp:.1f}°C")
    if humidity is not None:
        parts.append(f"湿度{humidity:.0f}%")
    if wind is not None:
        parts.append(f"风速{wind:.1f}km/h")
    if not parts:
        summary = "本次未携带可用天气快照，外部环境只能按压力标签和轨迹背景解释。"
    elif context_tags:
        summary = "，".join(parts) + "；同时识别到外部影响标签，需结合压力标签解释本次表现。"
    else:
        summary = "，".join(parts) + "；未识别到明显外部环境压力。"

    return {
        "has_weather": bool(has_weather),
        "weather_label": label,
        "temperature_c": round(temp, 1) if temp is not None else None,
        "humidity": round(humidity, 1) if humidity is not None else None,
        "wind_speed_kmh": round(wind, 1) if wind is not None else None,
        "observed_date": observed_date,
        "observed_hour": observed_hour if observed_hour >= 0 else None,
        "pressure_level": pressure_level,
        "summary": summary,
    }


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


def _sanitize_distance_curve_m(values: list) -> list[float]:
    clean: list[float] = []
    last = 0.0
    for value in values or []:
        num = _safe_float(value)
        if num is None or num < 0:
            num = last
        if num < last:
            num = last
        clean.append(float(num))
        last = float(num)
    return clean


def _resample_curve_to_distance_axis(
    source_distance_m: Any,
    source_curve: Any,
    target_distance_m: Any,
) -> list:
    """Map a record-level curve onto the authoritative review distance axis."""
    if not (
        isinstance(source_distance_m, list)
        and isinstance(source_curve, list)
        and isinstance(target_distance_m, list)
    ):
        return []
    if not source_distance_m or len(source_distance_m) != len(source_curve) or not target_distance_m:
        return []

    source_pairs: list[tuple[float, Any]] = []
    for distance, value in zip(source_distance_m, source_curve):
        dist = _safe_float(distance)
        if dist is None:
            continue
        source_pairs.append((float(dist), value))
    if not source_pairs:
        return []

    sampled: list[Any] = []
    idx = 0
    last_idx = len(source_pairs) - 1
    for target in target_distance_m:
        target_dist = _safe_float(target)
        if target_dist is None:
            sampled.append(None)
            continue
        while idx < last_idx and source_pairs[idx + 1][0] <= float(target_dist):
            idx += 1
        nearest_idx = idx
        if idx < last_idx:
            left_gap = abs(float(target_dist) - source_pairs[idx][0])
            right_gap = abs(source_pairs[idx + 1][0] - float(target_dist))
            if right_gap < left_gap:
                nearest_idx = idx + 1
        sampled.append(source_pairs[nearest_idx][1])
    return sampled


def _build_fatigue_review_curve_bundle(row: dict[str, Any]) -> dict[str, Any]:
    track_points = _safe_json_list(
        row.get("track_json") or row.get("points_json") or row.get("merged_track_json")
    ) or []
    records = MetricsResolver._convert_track_to_algorithm_records(track_points)
    dist_km_field = _safe_float(row.get("dist_km"))
    dist_m_field = _safe_float(row.get("distance"))
    total_distance_m = 0.0
    if dist_km_field and dist_km_field > 0:
        total_distance_m = dist_km_field * 1000.0
    elif dist_m_field and dist_m_field > 0:
        total_distance_m = dist_m_field
    elif records:
        total_distance_m = float(records[-1].get("distance") or 0.0)
    start_ts = records[0].get("timestamp") if records else None
    time_curve_sec: list[float] = []
    for record in records:
        ts = record.get("timestamp")
        if start_ts is not None and ts is not None:
            time_curve_sec.append(round((ts - start_ts).total_seconds(), 3))
    bundle = {
        "records": records,
        "distance_curve_m": _sanitize_distance_curve_m([r.get("distance") for r in records]),
        "time_curve_sec": time_curve_sec,
        "hr_curve": [r.get("heart_rate") for r in records],
        "speed_curve_mps": [float(r.get("speed") or 0.0) for r in records],
        "altitude_curve_m": [r.get("altitude") for r in records],
        "cadence_curve": [r.get("cadence") for r in records] or _safe_json_list(row.get("cadence_curve")) or [],
        "power_curve": [r.get("power") for r in records],
        "calories": _safe_float(row.get("calories")) or 0.0,
        "duration_sec": _safe_int(row.get("duration_sec") or row.get("duration")) or 0,
        "total_distance_m": total_distance_m,
        "sport_type": str(row.get("sport_type") or "running"),
        "source": "track_json" if track_points else "canonical_db",
        "avg_heart_rate": _safe_float(row.get("avg_hr") or row.get("avg_heart_rate")),
        "max_heart_rate": _safe_float(row.get("max_hr") or row.get("max_heart_rate")),
        "total_ascent": _safe_float(row.get("gain_m") or row.get("total_ascent")),
        "max_altitude": _safe_float(row.get("max_alt_m") or row.get("max_altitude")),
        "avg_power": _safe_float(row.get("avg_power")),
        "normalized_power": _safe_float(row.get("normalized_power")),
        "avg_temperature": _fatigue_review_temperature(row.get("avg_temperature")),
        "weather_json": row.get("weather_json"),
    }
    try:
        prof = profile_backend.get_profile()
        bundle["profile_max_hr"] = _safe_float(prof.max_hr) if prof and prof.max_hr else None
        bundle["profile_resting_hr"] = _safe_float(prof.resting_hr) if prof and prof.resting_hr else None
        bundle["profile_weight_kg"] = _safe_float(prof.weight) if prof and prof.weight else None
        bundle["profile_vo2max"] = _safe_float(prof.vo2max) if prof and prof.vo2max else None
        bundle["lactate_threshold_hr"] = _safe_float(prof.lactate_threshold_hr) if prof and prof.lactate_threshold_hr else None
        bundle["profile_ftp_watts"] = _safe_float(
            (prof.ftp_watts if prof and prof.ftp_watts else None)
            or (prof.ftp if prof and prof.ftp else None)
        )
    except Exception:
        bundle["profile_max_hr"] = None
        bundle["profile_resting_hr"] = None
        bundle["profile_weight_kg"] = None
        bundle["profile_vo2max"] = None
        bundle["lactate_threshold_hr"] = None
        bundle["profile_ftp_watts"] = None
    return bundle


def _build_resolved_payload_v81(
    bundle: dict[str, Any],
    sport_type: str,
) -> dict[str, Any]:
    empty = {
        "distance_curve": [],
        "time_curve": [],
        "altitude_curve": [],
        "hr_curve": [],
        "speed_curve": [],
        "power_curve": [],
        "cadence_curve": [],
        "gap_curve": [],
        "grade_curve": [],
        "efficiency_curve": [],
        "insight_events": [],
        "fatigue_zones": [],
        "context_tags": {},
    }
    records = bundle.get("records") or []
    distance_curve = bundle.get("distance_curve_m") or []
    fallback = dict(empty)
    fallback.update({
        "distance_curve": distance_curve,
        "time_curve": bundle.get("time_curve_sec") or [],
        "altitude_curve": bundle.get("altitude_curve_m") or [],
    })
    if not records or len(records) < 2 or not distance_curve:
        return fallback
    try:
        weather = _decode_weather_json(bundle.get("weather_json")) or {}
        weather_temp = (
            weather.get("temperature_c")
            or weather.get("temperature")
            or weather.get("avg_temperature")
        )
        avg_temperature = (
            bundle.get("avg_temperature")
            if bundle.get("avg_temperature") is not None
            else _fatigue_review_temperature(weather_temp)
        )
        raw = {
            "record_mesgs": records,
            "session_mesgs": [{
                "sport": sport_type,
                "total_distance": bundle.get("total_distance_m") or 0.0,
                "total_timer_time": bundle.get("duration_sec") or 0,
                "total_calories": bundle.get("calories") or 0.0,
                "avg_heart_rate": bundle.get("avg_heart_rate"),
                "max_heart_rate": bundle.get("max_heart_rate"),
                "total_ascent": bundle.get("total_ascent"),
                "max_altitude": bundle.get("max_altitude"),
                "avg_power": bundle.get("avg_power"),
                "normalized_power": bundle.get("normalized_power"),
                "avg_temperature": avg_temperature,
            }],
            "lap_mesgs": [],
            "weather_json": bundle.get("weather_json"),
        }
        meta = {
            "sport_type": sport_type,
            "weather": weather,
            "profile_max_hr": bundle.get("profile_max_hr"),
            "profile_resting_hr": bundle.get("profile_resting_hr"),
            "profile_weight_kg": bundle.get("profile_weight_kg"),
            "profile_vo2max": bundle.get("profile_vo2max"),
            "lactate_threshold_hr": bundle.get("lactate_threshold_hr"),
        }

        resolved = MetricsResolver().resolve(raw, meta)
        if not isinstance(resolved, dict):
            return empty

        # §6 shadow_diff 隔离:出口白名单过滤
        for forbidden in ("shadow_diff", "shadow_diff_json", "diff"):
            resolved.pop(forbidden, None)

        resolver_distance_curve = resolved.get("distance_curve") or distance_curve
        efficiency_curve = resolved.get("efficiency_curve") or []
        resolver_time_curve = resolved.get("time_curve") or bundle.get("time_curve_sec") or []
        resolver_hr_curve = resolved.get("hr_curve") or bundle.get("hr_curve") or []
        resolver_speed_curve = resolved.get("speed_curve") or bundle.get("speed_curve_mps") or []
        resolver_cadence_curve = resolved.get("cadence_curve") or bundle.get("cadence_curve") or []
        if efficiency_curve and len(resolver_distance_curve) != len(efficiency_curve):
            resolver_distance_curve = distance_curve[:len(efficiency_curve)]
        resolver_altitude_curve = resolved.get("altitude_curve") or bundle.get("altitude_curve_m") or []
        resolver_power_curve = bundle.get("power_curve") or []
        if len(resolver_distance_curve) != len(distance_curve):
            if len(resolver_altitude_curve) != len(resolver_distance_curve):
                resolver_altitude_curve = _resample_curve_to_distance_axis(
                    source_distance_m=distance_curve,
                    source_curve=bundle.get("altitude_curve_m") or [],
                    target_distance_m=resolver_distance_curve,
                ) or resolver_altitude_curve
            if len(resolver_power_curve) != len(resolver_distance_curve):
                resolver_power_curve = _resample_curve_to_distance_axis(
                    source_distance_m=distance_curve,
                    source_curve=bundle.get("power_curve") or [],
                    target_distance_m=resolver_distance_curve,
                ) or resolver_power_curve
            if len(resolver_hr_curve) != len(resolver_distance_curve):
                resolver_hr_curve = _resample_curve_to_distance_axis(
                    source_distance_m=distance_curve,
                    source_curve=bundle.get("hr_curve") or [],
                    target_distance_m=resolver_distance_curve,
                ) or resolver_hr_curve
            if len(resolver_speed_curve) != len(resolver_distance_curve):
                resolver_speed_curve = _resample_curve_to_distance_axis(
                    source_distance_m=distance_curve,
                    source_curve=bundle.get("speed_curve_mps") or [],
                    target_distance_m=resolver_distance_curve,
                ) or resolver_speed_curve
            if len(resolver_cadence_curve) != len(resolver_distance_curve):
                resolver_cadence_curve = _resample_curve_to_distance_axis(
                    source_distance_m=distance_curve,
                    source_curve=bundle.get("cadence_curve") or [],
                    target_distance_m=resolver_distance_curve,
                ) or resolver_cadence_curve
        if len(resolver_time_curve) != len(resolver_distance_curve):
            resolver_time_curve = []
        if len(resolver_hr_curve) != len(resolver_distance_curve):
            resolver_hr_curve = []
        if len(resolver_speed_curve) != len(resolver_distance_curve):
            resolver_speed_curve = []
        if len(resolver_cadence_curve) != len(resolver_distance_curve):
            resolver_cadence_curve = []
        if len(resolver_altitude_curve) != len(resolver_distance_curve):
            resolver_altitude_curve = []
        if len(resolver_power_curve) != len(resolver_distance_curve):
            resolver_power_curve = []
        fatigue_zones = MetricsResolver._calculate_fatigue_zones(
            distance_curve=resolver_distance_curve,
            ei_curve=efficiency_curve,
            sport_type=sport_type,
            avg_hr=bundle.get("avg_heart_rate"),
            profile_max_hr=bundle.get("profile_max_hr"),
            profile_resting_hr=bundle.get("profile_resting_hr"),
        )
        insight_events = MetricsResolver._detect_bonk_event(
            distance_curve=resolver_distance_curve,
            ei_curve=efficiency_curve,
            total_calories=bundle.get("calories") or 0.0,
            sport_type=sport_type,
            time_curve=resolver_time_curve,
            hr_curve=resolver_hr_curve,
            speed_curve=resolver_speed_curve,
            cadence_curve=resolver_cadence_curve,
            power_curve=resolver_power_curve,
            weight_kg=bundle.get("profile_weight_kg"),
            avg_hr=bundle.get("avg_heart_rate"),
            profile_max_hr=bundle.get("profile_max_hr"),
            profile_resting_hr=bundle.get("profile_resting_hr"),
            lactate_threshold_hr=bundle.get("lactate_threshold_hr"),
            vo2max=bundle.get("profile_vo2max"),
        )

        return {
            "distance_curve": resolver_distance_curve,
            "time_curve": resolver_time_curve,
            "altitude_curve": resolver_altitude_curve,
            "hr_curve": resolver_hr_curve,
            "speed_curve": resolver_speed_curve,
            "power_curve": resolver_power_curve,
            "cadence_curve": resolver_cadence_curve,
            "gap_curve": resolved.get("gap_curve") or [],
            "grade_curve": resolved.get("grade_curve") or [],
            "efficiency_curve": efficiency_curve,
            "insight_events": insight_events,
            "fatigue_zones": fatigue_zones,
            "context_tags": resolved.get("context_tags") or {},
        }
    except Exception:
        logger.exception("_build_resolved_payload_v81 Resolver 调用失败,降级空 dict")
        try:
            fallback["fatigue_zones"] = MetricsResolver._calculate_fatigue_zones(
                distance_curve=distance_curve,
                ei_curve=[],
                sport_type=sport_type,
            )
        except Exception:
            fallback["fatigue_zones"] = []
        return fallback


_FATIGUE_REVIEW_FORBIDDEN_KEYS = {
    "records",
    "points",
    "raw_records",
    "track_points",
    "fit_records",
    "gpx_points",
    "shadow_diff",
    "shadow_diff_json",
    "diff",
}

_FATIGUE_REVIEW_STARTUP_EVENT_MIN_KM = 0.1
_FATIGUE_REVIEW_TURNING_POINT_MIN_KM_BY_SPORT = {
    "running": 1.0,
    "trail_running": 1.0,
    "treadmill_running": 1.0,
    "hiking": 1.0,
    "walking": 0.8,
    "mountaineering": 1.0,
    "cycling": 3.0,
    "road_cycling": 3.0,
    "mountain_biking": 2.0,
}
_FATIGUE_REVIEW_TURNING_POINT_MIN_DISTANCE_RATIO = 0.15
_FATIGUE_REVIEW_TURNING_POINT_MIN_ZONE_KM_BY_SPORT = {
    "running": 0.5,
    "trail_running": 0.5,
    "treadmill_running": 0.5,
    "hiking": 0.8,
    "walking": 0.5,
    "mountaineering": 0.8,
    "cycling": 1.5,
    "road_cycling": 1.5,
    "mountain_biking": 1.0,
}
_FATIGUE_REVIEW_TURNING_POINT_MIN_ZONE_RATIO = 0.08
_FATIGUE_REVIEW_STARTUP_GUARD_KM_BY_SPORT = {
    "running": 0.3,
    "trail_running": 0.3,
    "treadmill_running": 0.3,
    "hiking": 0.5,
    "walking": 0.5,
    "mountaineering": 0.5,
    "cycling": 1.0,
    "road_cycling": 1.0,
    "mountain_biking": 1.0,
}
_FATIGUE_REVIEW_DEFAULT_STARTUP_GUARD_KM = 0.3


def _fatigue_review_total_km(total_distance_m: Any = None) -> float:
    return (_safe_float(total_distance_m, None) or 0.0) / 1000.0


def _fatigue_review_turning_point_min_km(
    sport_type: str,
    total_distance_m: Any = None,
) -> float:
    sport = str(sport_type or "").strip().lower()
    total_km = _fatigue_review_total_km(total_distance_m)
    base = _FATIGUE_REVIEW_TURNING_POINT_MIN_KM_BY_SPORT.get(sport, 1.0)
    if total_km > 0:
        base = min(base, max(0.0, total_km * 0.35))
        base = max(base, total_km * _FATIGUE_REVIEW_TURNING_POINT_MIN_DISTANCE_RATIO)
    return round(max(_FATIGUE_REVIEW_STARTUP_EVENT_MIN_KM, base), 2)


def _fatigue_review_turning_point_min_zone_km(
    sport_type: str,
    total_distance_m: Any = None,
) -> float:
    sport = str(sport_type or "").strip().lower()
    total_km = _fatigue_review_total_km(total_distance_m)
    base = _FATIGUE_REVIEW_TURNING_POINT_MIN_ZONE_KM_BY_SPORT.get(sport, 0.5)
    if total_km > 0:
        base = min(base, max(0.15, total_km * 0.25))
        base = max(base, total_km * _FATIGUE_REVIEW_TURNING_POINT_MIN_ZONE_RATIO)
    return round(max(0.1, base), 2)


def _fatigue_review_zone_trigger_km(zone: dict[str, Any]) -> float:
    start = _safe_float(zone.get("start_km")) or 0.0
    end = _safe_float(zone.get("end_km")) or start
    return start if start >= 0.05 else round((start + end) / 2.0, 2)


def _is_fatigue_review_trusted_pressure_zone(
    zone: dict[str, Any],
    sport_type: str,
    total_distance_m: Any = None,
) -> bool:
    if not isinstance(zone, dict) or zone.get("startup_trimmed"):
        return False
    start = _safe_float(zone.get("start_km"), None)
    end = _safe_float(zone.get("end_km"), None)
    if start is None or end is None or end <= start:
        return False
    if end - start < _fatigue_review_turning_point_min_zone_km(sport_type, total_distance_m):
        return False
    return _fatigue_review_zone_trigger_km(zone) >= _fatigue_review_turning_point_min_km(
        sport_type,
        total_distance_m,
    )


def _is_cycling_review_sport(sport_type: Any) -> bool:
    return str(sport_type or "").strip().lower() in CYCLING_REVIEW_TYPES


def _normalize_cycling_fatigue_zone_contract(zone: dict[str, Any]) -> dict[str, Any]:
    """Keep cycling zones as review references, not fatigue-collapse claims."""
    item = dict(zone)
    item["semantic"] = str(item.get("semantic") or "state_change_reference")
    item["interpretation"] = str(item.get("interpretation") or "reference_only")
    item["confidence"] = str(item.get("confidence") or "partial")
    item["description"] = str(
        item.get("description")
        or item.get("reason")
        or "参考区间：这段状态变化较明显，需结合功率、踏频、心率和地形判断。"
    )
    return item


def _cycling_signal_status(signals: Any, key: str) -> str:
    if not isinstance(signals, dict):
        return "unavailable"
    signal = signals.get(key)
    if not isinstance(signal, dict):
        return "unavailable"
    status = str(signal.get("status") or "unavailable").strip().lower()
    return status if status in {"available", "partial", "unavailable"} else "unavailable"


def _cycling_zone_indices(zone: dict[str, Any], distance_curve_km: Any) -> list[int]:
    if not isinstance(distance_curve_km, list) or not distance_curve_km:
        return []
    start = _safe_float(zone.get("start_km"), None)
    end = _safe_float(zone.get("end_km"), None)
    if start is None or end is None or end <= start:
        return []
    indices: list[int] = []
    for idx, value in enumerate(distance_curve_km):
        dist = _safe_float(value, None)
        if dist is not None and start <= dist <= end:
            indices.append(idx)
    return indices


def _cycling_zone_segment_stats(curves_snapshot: Any, indices: list[int]) -> dict[str, Any]:
    curves = curves_snapshot if isinstance(curves_snapshot, dict) else {}

    def values(name: str) -> list[Any]:
        series = curves.get(name)
        if not isinstance(series, list):
            return []
        out: list[float | None] = []
        for idx in indices:
            if 0 <= idx < len(series):
                out.append(_safe_float(series[idx], None))
        return out

    powers = values("power")
    speeds = values("speed")
    grades = values("grade")
    cadences = values("cadence")
    hrs = values("hr")

    total = max(len(indices), 1)
    power_observed = [v for v in powers if v is not None]
    speed_observed = [v for v in speeds if v is not None]
    grade_observed = [v for v in grades if v is not None]
    cadence_observed = [v for v in cadences if v is not None]
    hr_observed = [v for v in hrs if v is not None]

    low_power_count = sum(1 for v in power_observed if v <= 20)
    stopped_count = sum(1 for v in speed_observed if v <= 0.8)
    downhill_count = sum(1 for v in grade_observed if v <= -1.5)
    zero_cadence_count = sum(1 for v in cadence_observed if v <= 0)

    return {
        "points_count": len(indices),
        "power_points_count": len([v for v in power_observed if 0 < v <= 2500]),
        "hr_points_count": len([v for v in hr_observed if v > 30]),
        "cadence_points_count": len([v for v in cadence_observed if 0 < v <= 250]),
        "low_power_ratio": low_power_count / max(len(power_observed), 1) if power_observed else 0.0,
        "stopped_ratio": stopped_count / max(len(speed_observed), 1) if speed_observed else 0.0,
        "downhill_ratio": downhill_count / max(len(grade_observed), 1) if grade_observed else 0.0,
        "zero_cadence_ratio": zero_cadence_count / max(len(cadence_observed), 1) if cadence_observed else 0.0,
        "coverage_ratio": len(indices) / total,
    }


def _calibrate_cycling_fatigue_zones_for_review(
    zones: Any,
    summary: Any,
    curves_snapshot: Any,
    cycling_explanation_signals: Any,
) -> list[dict[str, Any]]:
    """P14: reduce cycling fatigue-zone overclaims before UI exposure.

    The resolver still emits generic EI-drop windows. For cycling, review zones
    remain reference intervals unless supported by dedicated explanation signals;
    coasting, stopping, and downhill-dominant windows are not shown as fatigue.
    """
    if not isinstance(zones, list):
        return []
    summary = summary if isinstance(summary, dict) else {}
    curves = curves_snapshot if isinstance(curves_snapshot, dict) else {}
    distance = curves.get("distance") if isinstance(curves.get("distance"), list) else []

    power_quality = str(summary.get("power_data_quality") or "missing")
    cadence_quality = str(summary.get("cadence_data_quality") or "missing")
    has_power = bool(summary.get("power_available")) and power_quality == "available"
    has_cadence = bool(summary.get("cadence_available")) and cadence_quality == "available"
    has_hr = bool(curves.get("hr"))

    power_status = _cycling_signal_status(cycling_explanation_signals, "power_retention_signal")
    aerobic_status = _cycling_signal_status(cycling_explanation_signals, "aerobic_drift_signal")
    cadence_status = _cycling_signal_status(cycling_explanation_signals, "cadence_signal")

    calibrated: list[dict[str, Any]] = []
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        item = _normalize_cycling_fatigue_zone_contract(zone)
        indices = _cycling_zone_indices(item, distance)
        stats = _cycling_zone_segment_stats(curves, indices)

        if (
            stats["stopped_ratio"] >= 0.45
            or (stats["downhill_ratio"] >= 0.45 and stats["low_power_ratio"] >= 0.45)
            or (stats["downhill_ratio"] >= 0.25 and stats["zero_cadence_ratio"] >= 0.55)
        ):
            continue

        reasons: list[str] = []
        descriptions: list[str] = []
        if not has_power or power_status != "available":
            reasons.append(f"power_signal_{power_status}")
            descriptions.append("功率数据或有效踩踏证据不足，不能判断功率回落。")
        else:
            reasons.append("power_signal_available")
        if not has_hr or aerobic_status != "available":
            reasons.append(f"aerobic_signal_{aerobic_status}")
            descriptions.append("心率或功率-心率证据不足，不能判断有氧漂移或心率压力。")
        else:
            reasons.append("aerobic_signal_available")
        if not has_cadence or cadence_status != "available":
            reasons.append(f"cadence_signal_{cadence_status}")
            descriptions.append("踏频证据不足时，不判断踩踏组织中断。")
        else:
            reasons.append("cadence_signal_available")

        item["semantic"] = "state_change_reference"
        item["interpretation"] = "reference_only"
        item["confidence"] = "partial"
        item["calibration"] = "p14_cycling_reference_zone"
        item["reasons"] = list(dict.fromkeys((item.get("reasons") or []) + reasons)) if isinstance(item.get("reasons"), list) else reasons
        item["description"] = (
            "参考区间：这段状态变化较明显，需结合功率、踏频、心率和地形判断。"
            + (" " + " ".join(descriptions) if descriptions else " 专项解释以可用的骑行解释信号为准。")
        )
        calibrated.append(item)

    return calibrated


def _filter_trusted_fatigue_zones_for_review(
    zones: Any,
    sport_type: str,
    total_distance_m: Any = None,
) -> list[dict[str, Any]]:
    """Keep only user-visible, credible pressure zones for review surfaces."""
    if not isinstance(zones, list):
        return []
    trusted: list[dict[str, Any]] = []
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        if not _is_fatigue_review_trusted_pressure_zone(zone, sport_type, total_distance_m):
            continue
        item = dict(zone)
        if _is_cycling_review_sport(sport_type):
            item = _normalize_cycling_fatigue_zone_contract(item)
        trusted.append(item)
    return trusted


def _build_fatigue_review_collapse_events(
    bonk_events: Optional[list[dict[str, Any]]],
    fatigue_zones: Optional[list[dict[str, Any]]],
    sport_type: str = "running",
    total_distance_m: Any = None,
) -> list[dict[str, Any]]:
    """Build backend-authoritative event anchors for the review chart.

    Bonk events stay first-class. When Bonk is absent, we expose a small,
    deduplicated set of fatigue transition anchors from backend fatigue_zones.
    """
    raw_events: list[dict[str, Any]] = []

    def add_event(
        event_type: str,
        trigger_km: Any,
        title: str,
        description: str,
        value_y: Any = None,
        extra: Optional[dict[str, Any]] = None,
    ) -> None:
        trigger = _safe_float(trigger_km)
        if trigger is None or trigger < 0:
            return
        for existing in raw_events:
            existing_km = _safe_float(existing.get("trigger_km"))
            if existing_km is not None and abs(existing_km - trigger) < 0.05:
                return
        event = {
            "type": event_type,
            "title": title,
            "label": title,
            "trigger_km": round(trigger, 2),
            "trigger_time_sec": None,
            "value_y": value_y,
            "description": description,
        }
        if isinstance(extra, dict):
            for key in ("risk_start_km", "risk_end_km", "confidence", "evidence", "risk_level"):
                if key in extra:
                    event[key] = extra.get(key)
        raw_events.append(event)

    for ev in bonk_events or []:
        if not isinstance(ev, dict):
            continue
        add_event(
            event_type=str(ev.get("type") or "BONK_WARNING"),
            trigger_km=ev.get("trigger_km"),
            title=str(ev.get("title") or ev.get("label") or "能量断档风险线索"),
            description=str(ev.get("description") or "后端识别到能量断档风险窗口线索"),
            value_y=ev.get("value_y"),
            extra=ev,
        )

    zones: list[dict[str, Any]] = []
    for zone in fatigue_zones or []:
        if not isinstance(zone, dict):
            continue
        start = _safe_float(zone.get("start_km"), None)
        end = _safe_float(zone.get("end_km"), None)
        if start is None or end is None or end <= start:
            continue
        normalized = dict(zone)
        normalized["start_km"] = start
        normalized["end_km"] = end
        zones.append(normalized)
    zones.sort(key=lambda item: (item["start_km"], item["end_km"]))

    def is_review_fatigue_event_zone(zone: dict[str, Any]) -> bool:
        return _is_fatigue_review_trusted_pressure_zone(
            zone,
            sport_type=sport_type,
            total_distance_m=total_distance_m,
        )

    def zone_desc(zone: dict[str, Any], fallback: str) -> str:
        start = _safe_float(zone.get("start_km")) or 0.0
        end = _safe_float(zone.get("end_km")) or start
        level = str(zone.get("level") or "fatigue")
        return str(
            zone.get("reason")
            or zone.get("description")
            or f"{fallback}: 识别到 {level} 压力区间 {start:.1f}-{end:.1f} km"
        )

    event_zones = [zone for zone in zones if is_review_fatigue_event_zone(zone)]
    if _is_cycling_review_sport(sport_type):
        event_zones = [
            zone for zone in event_zones
            if str(zone.get("event_semantic") or "").strip().lower() in {
                "power_drop",
                "cadence_interruption",
                "hr_power_decoupling",
                "non_fitness_event",
                "data_insufficient",
            }
        ]
    if event_zones:
        first = event_zones[0]
        first_type = str(first.get("event_semantic") or "FATIGUE_PRESSURE_START")
        first_title = str(first.get("event_title") or "状态压力开始")
        first_fallback = (
            "状态变化参考: 需结合功率、踏频、心率和地形判断"
            if _is_cycling_review_sport(sport_type)
            else "状态压力开始: 强度和效率变化都达到转折点门槛"
        )
        add_event(
            first_type,
            _fatigue_review_zone_trigger_km(first),
            first_title,
            zone_desc(first, first_fallback),
        )

        high_levels = {"high", "collapse", "critical", "severe"}
        high_zones = [
            zone for zone in event_zones
            if str(zone.get("level") or "").lower() in high_levels
        ]
        if high_zones:
            first_high = high_zones[0]
            add_event(
                "EFFICIENCY_DROP",
                _fatigue_review_zone_trigger_km(first_high),
                "效率下降",
                zone_desc(first_high, "效率下降"),
            )

            last_high = high_zones[-1]
            add_event(
                "SUSTAINED_FATIGUE",
                _fatigue_review_zone_trigger_km(last_high),
                "疲劳加深",
                zone_desc(last_high, "后段疲劳加深"),
            )

    collapse_events: list[dict[str, Any]] = []
    for idx, ev in enumerate(raw_events[:4]):
        title = str(ev.get("title") or ev.get("label") or ev.get("type") or "关键事件")
        item = {
            "event_id": f"ce_{idx:02d}",
            "type": str(ev.get("type") or "FATIGUE_EVENT"),
            "title": title,
            "label": str(ev.get("label") or title),
            "trigger_km": ev.get("trigger_km"),
            "trigger_time_sec": ev.get("trigger_time_sec"),
            "value_y": ev.get("value_y"),
            "description": str(ev.get("description") or ""),
        }
        for key in ("risk_start_km", "risk_end_km", "confidence", "evidence", "risk_level"):
            if key in ev:
                item[key] = ev.get(key)
        collapse_events.append(item)
    return collapse_events


def _fatigue_review_startup_guard_km(
    sport_type: str,
    total_distance_m: Any = None,
) -> float:
    """Display-layer warmup guard for review fatigue zones."""
    sport = str(sport_type or "").strip().lower()
    guard_km = _FATIGUE_REVIEW_STARTUP_GUARD_KM_BY_SPORT.get(
        sport,
        _FATIGUE_REVIEW_DEFAULT_STARTUP_GUARD_KM,
    )
    total_m = _safe_float(total_distance_m, None)
    if total_m is not None and total_m > 0:
        # Keep the guard bounded for very short activities.
        guard_km = min(guard_km, max(0.0, (total_m / 1000.0) * 0.1))
    return round(max(0.0, guard_km), 2)


def _filter_fatigue_zones_after_startup(
    zones: Any,
    sport_type: str,
    total_distance_m: Any = None,
) -> list[dict[str, Any]]:
    """Drop or trim startup/warmup fatigue zones before review display."""
    if not isinstance(zones, list):
        return []

    guard_km = _fatigue_review_startup_guard_km(sport_type, total_distance_m)
    if guard_km <= 0:
        return [dict(zone) for zone in zones if isinstance(zone, dict)]

    filtered: list[dict[str, Any]] = []
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        start = _safe_float(zone.get("start_km"), None)
        end = _safe_float(zone.get("end_km"), None)
        if start is None or end is None or end <= start:
            continue
        if end <= guard_km:
            continue
        item = dict(zone)
        if start < guard_km:
            item["start_km"] = guard_km
            item["startup_trimmed"] = True
        filtered.append(item)
    return filtered


def _fatigue_review_startup_index(
    distance_curve_km: Any,
    sport_type: str,
    total_distance_m: Any = None,
) -> int:
    """Return the first distance-axis index outside the review startup guard."""
    return int(_build_review_input_window(
        distance_curve_km,
        sport_type,
        total_distance_m,
    ).get("start_idx", 0))


def _build_review_input_window(
    distance_curve_km: Any,
    sport_type: str,
    total_distance_m: Any = None,
) -> dict[str, Any]:
    """Build a review-only startup guard window shared by fatigue metrics."""
    guard_km = _fatigue_review_startup_guard_km(sport_type, total_distance_m)
    has_aligned_axis = isinstance(distance_curve_km, list) and bool(distance_curve_km)
    if not has_aligned_axis or guard_km <= 0:
        return {
            "start_idx": 0,
            "guard_km": guard_km,
            "has_aligned_axis": has_aligned_axis,
        }

    start_idx = len(distance_curve_km)
    for idx, value in enumerate(distance_curve_km):
        dist_km = _safe_float(value, None)
        if dist_km is not None and dist_km >= guard_km:
            start_idx = idx
            break

    return {
        "start_idx": start_idx,
        "guard_km": guard_km,
        "has_aligned_axis": has_aligned_axis,
    }


def _trim_review_series_by_window(series: Any, window: Any, distance_curve_km: Any = None) -> list:
    """Trim a review metric input by the shared startup window."""
    if not isinstance(series, list):
        return []
    if not isinstance(window, dict) or not window.get("has_aligned_axis"):
        return series
    if distance_curve_km is not None and (
        not isinstance(distance_curve_km, list) or len(distance_curve_km) != len(series)
    ):
        return series
    start_idx = _safe_int(window.get("start_idx"))
    return series[start_idx:]


def _trim_review_series_after_startup(
    series: Any,
    distance_curve_km: Any,
    sport_type: str,
    total_distance_m: Any = None,
) -> list:
    """Trim review metric inputs only; raw chart curves remain intact."""
    window = _build_review_input_window(distance_curve_km, sport_type, total_distance_m)
    return _trim_review_series_by_window(series, window, distance_curve_km)


def _build_review_hr_drift_records(
    hr_curve: Any,
    speed_curve: Any,
    distance_curve_km: Any,
    sport_type: str,
    total_distance_m: Any = None,
    window: Any = None,
) -> list[dict[str, Any]]:
    """Build review-only HR drift records from real HR and speed streams."""
    if not (
        isinstance(hr_curve, list)
        and isinstance(speed_curve, list)
        and isinstance(distance_curve_km, list)
    ):
        return []
    if not (len(hr_curve) == len(speed_curve) == len(distance_curve_km)):
        return []

    review_window = (
        window
        if isinstance(window, dict)
        else _build_review_input_window(distance_curve_km, sport_type, total_distance_m)
    )
    if not review_window.get("has_aligned_axis"):
        return []
    start_idx = _safe_int(review_window.get("start_idx"))
    records: list[dict[str, Any]] = []
    for idx in range(start_idx, len(hr_curve)):
        hr = _safe_float(hr_curve[idx], None)
        speed = _safe_float(speed_curve[idx], None)
        if hr is None or hr <= 30 or speed is None or speed <= 0:
            continue
        records.append({
            "raw": {
                "heart_rate": hr,
                "speed": speed,
                "timestamp": idx,
            }
        })
    return records


def _review_metric_reasons(metric_key: str, **kwargs: Any) -> list[str]:
    duration_sec = _safe_int(kwargs.get("duration_sec")) or 0
    sport_type = str(kwargs.get("sport_type") or "")
    reasons: list[str] = []
    if metric_key == "efficiency":
        if sport_type in ("swimming",):
            reasons.append("unsupported_sport_swim")
        if duration_sec < 15 * 60:
            reasons.append("duration<15min")
        if not _safe_float(kwargs.get("avg_hr")):
            reasons.append("missing_hr")
        if not _safe_float(kwargs.get("avg_pace")):
            reasons.append("missing_pace")
    elif metric_key == "durability":
        if sport_type in ("swimming",):
            reasons.append("unsupported_sport_swim")
        if duration_sec < 45 * 60:
            reasons.append("duration<45min")
        if _safe_int(kwargs.get("speed_points")) < 20:
            reasons.append("points<20")
    elif metric_key == "cadence_stability":
        if sport_type not in ("running", "trail_running"):
            reasons.append("unsupported_sport")
        if duration_sec < 20 * 60:
            reasons.append("duration<20min")
        if _safe_int(kwargs.get("cadence_points")) < 20:
            reasons.append("points<20")
    elif metric_key == "training_load":
        if duration_sec < 5 * 60:
            reasons.append("duration<5min")
        if not _safe_float(kwargs.get("avg_hr")):
            reasons.append("missing_hr")
        if not kwargs.get("has_zone_distribution"):
            if not _safe_float(kwargs.get("profile_max_hr")):
                reasons.append("missing_profile_max_hr")
            if not _safe_float(kwargs.get("profile_resting_hr")):
                reasons.append("missing_resting_hr")
    return reasons


def _merge_fatigue_zones_for_review(
    zones: Any,
    merge_gap_km: float = 0.05,
) -> list[dict[str, Any]]:
    """Normalize review fatigue zones for consistent UI consumption.

    Resolver may emit short adjacent windows for interval sessions. The review
    snapshot exposes user-facing zones, so contiguous same-level windows are
    merged before they drive chart bands, stage overview, side cards, and event
    anchors.
    """
    if not isinstance(zones, list):
        return []

    normalized: list[dict[str, Any]] = []
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        start = _safe_float(zone.get("start_km"), None)
        end = _safe_float(zone.get("end_km"), None)
        if start is None or end is None or end <= start:
            continue
        level = str(zone.get("level") or "unknown").strip().lower() or "unknown"
        item = {
            "start_km": round(start, 2),
            "end_km": round(end, 2),
            "level": level,
        }
        for optional_key in ("reason", "description", "semantic", "interpretation", "confidence"):
            if zone.get(optional_key):
                item[optional_key] = str(zone.get(optional_key))
        normalized.append(item)

    normalized.sort(key=lambda item: (item["start_km"], item["end_km"], item["level"]))

    merged: list[dict[str, Any]] = []
    gap = max(0.0, _safe_float(merge_gap_km) or 0.0)
    for zone in normalized:
        if not merged:
            merged.append(dict(zone))
            continue
        previous = merged[-1]
        same_level = previous.get("level") == zone.get("level")
        touches = zone["start_km"] <= (previous["end_km"] + gap)
        if same_level and touches:
            previous["end_km"] = round(max(previous["end_km"], zone["end_km"]), 2)
            if not previous.get("reason") and zone.get("reason"):
                previous["reason"] = zone["reason"]
            if not previous.get("description") and zone.get("description"):
                previous["description"] = zone["description"]
            for optional_key in ("semantic", "interpretation", "confidence"):
                if not previous.get(optional_key) and zone.get(optional_key):
                    previous[optional_key] = zone[optional_key]
            continue
        merged.append(dict(zone))

    return merged


def _fatigue_review_axis_len(distance_curve_m: list) -> int:
    if not isinstance(distance_curve_m, list) or not distance_curve_m:
        return 0
    numeric = [_safe_float(v) for v in distance_curve_m]
    return len(numeric) if any(v is not None for v in numeric) else 0


def _fatigue_review_numeric_curve(
    values: Any,
    axis_len: int,
    decimals: int | None = None,
) -> list:
    """Normalize a drawable curve to the authoritative distance-axis length."""
    if axis_len <= 0 or not isinstance(values, list) or len(values) != axis_len:
        return []
    normalized: list[Any] = []
    has_value = False
    for value in values:
        num = _safe_float(value)
        if num is None:
            normalized.append(None)
            continue
        has_value = True
        normalized.append(round(num, decimals) if decimals is not None else num)
    return normalized if has_value else []


def _build_fatigue_review_terrain_load_curve(
    grade_curve: Any,
    speed_curve: Any,
    time_curve: Any,
    axis_len: int,
) -> list:
    """Build backend-authoritative Terrain Load from grade, speed, and duration."""
    if axis_len <= 0:
        return []
    if not (
        isinstance(grade_curve, list)
        and isinstance(speed_curve, list)
        and isinstance(time_curve, list)
    ):
        return []
    if len(grade_curve) != axis_len or len(speed_curve) != axis_len or len(time_curve) != axis_len:
        return []

    terrain_load: list[float] = []
    has_source_value = False
    previous_time: float | None = None
    for i in range(axis_len):
        grade_pct = _safe_float(grade_curve[i], None)
        speed_mps = _safe_float(speed_curve[i], None)
        current_time = _safe_float(time_curve[i], None)
        if grade_pct is None or speed_mps is None or current_time is None:
            terrain_load.append(0.0)
            previous_time = current_time if current_time is not None else previous_time
            continue

        if previous_time is None:
            dt_sec = 0.0
        else:
            dt_sec = max(0.0, current_time - previous_time)
        previous_time = current_time

        grade_ratio = abs(grade_pct) / 100.0
        load = grade_ratio * max(0.0, speed_mps) * dt_sec
        if load > 0:
            has_source_value = True
        terrain_load.append(round(load, 4))

    return terrain_load if has_source_value else []


_FATIGUE_REVIEW_PACE_DISPLAY_CAP_SEC = 15 * 60


def _build_fatigue_review_pace_display_curve(
    speed_curve: Any,
    axis_len: int,
    cap_sec_per_km: float = _FATIGUE_REVIEW_PACE_DISPLAY_CAP_SEC,
) -> dict[str, list]:
    """Build display-only pace curves from backend speed m/s.

    `raw` preserves the truthful sec/km value for tooltip use, while `chart`
    caps very slow/stopped points so Garmin-style pace lanes stay readable.
    """
    if axis_len <= 0 or not isinstance(speed_curve, list) or len(speed_curve) != axis_len:
        return {"chart": [], "raw": [], "capped": []}

    chart: list[Any] = []
    raw: list[Any] = []
    capped: list[bool] = []
    has_value = False
    cap = float(cap_sec_per_km)
    for value in speed_curve:
        speed_mps = _safe_float(value, None)
        if speed_mps is None or speed_mps <= 0:
            raw.append(None)
            chart.append(None)
            capped.append(False)
            continue
        pace_sec = 1000.0 / speed_mps
        pace_rounded = round(pace_sec, 1)
        is_capped = pace_rounded > cap
        raw.append(pace_rounded)
        chart.append(cap if is_capped else pace_rounded)
        capped.append(is_capped)
        has_value = True

    if not has_value:
        return {"chart": [], "raw": [], "capped": []}
    return {"chart": chart, "raw": raw, "capped": capped}


def _build_fatigue_review_display_curves(
    speed_curve: Any,
    gap_curve: Any,
    axis_len: int,
) -> dict[str, Any]:
    pace = _build_fatigue_review_pace_display_curve(speed_curve, axis_len)
    gap_pace = _build_fatigue_review_pace_display_curve(gap_curve, axis_len)
    return {
        "pace_sec_per_km": pace["chart"],
        "pace_raw_sec_per_km": pace["raw"],
        "pace_capped": pace["capped"],
        "gap_pace_sec_per_km": gap_pace["chart"],
        "gap_pace_raw_sec_per_km": gap_pace["raw"],
        "gap_pace_capped": gap_pace["capped"],
    }


def _build_fatigue_review_display_meta() -> dict[str, Any]:
    return {
        "pace_display_cap_sec_per_km": _FATIGUE_REVIEW_PACE_DISPLAY_CAP_SEC,
        "pace_display_cap_label": "15'00''/km",
        "pace_cap_strategy": "cap_slow_points_for_chart_only",
    }


def _fatigue_review_data_quality(
    values: Any,
    min_points: int = 20,
    axis_len: int | None = None,
    valid_min: float = 0.0,
    valid_max: float | None = None,
    invalid_ratio_threshold: float = 0.2,
    ignore_below_or_equal_min_for_invalid_ratio: bool = False,
) -> tuple[bool, int, str]:
    if not isinstance(values, list) or not values:
        return False, 0, "missing"
    if axis_len is not None and axis_len > 0 and len(values) != axis_len:
        return False, 0, "length_mismatch"
    count = 0
    invalid_count = 0
    observed_count = 0
    for value in values:
        num = _safe_float(value, None)
        if num is None:
            continue
        observed_count += 1
        if num <= valid_min or (valid_max is not None and num > valid_max):
            if not (ignore_below_or_equal_min_for_invalid_ratio and num <= valid_min):
                invalid_count += 1
            continue
        if num > valid_min:
            count += 1
    if observed_count > 0 and invalid_count / observed_count > invalid_ratio_threshold:
        return False, count, "invalid_values"
    if count <= 0:
        return False, 0, "missing"
    if count < min_points:
        return False, count, "insufficient_points"
    return True, count, "available"


def _build_fatigue_review_summary(
    row: dict[str, Any],
    bundle: dict[str, Any],
    curves_snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Activity-level review summary used by cycling contracts and AI preflight."""
    power_curve = curves_snapshot.get("power") or bundle.get("power_curve") or []
    cadence_curve = curves_snapshot.get("cadence") or bundle.get("cadence_curve") or []
    axis_len = len(curves_snapshot.get("distance") or [])
    power_available, power_count, power_quality = _fatigue_review_data_quality(
        power_curve,
        axis_len=axis_len,
        valid_min=0.0,
        valid_max=2500.0,
    )
    cadence_available, cadence_count, cadence_quality = _fatigue_review_data_quality(
        cadence_curve,
        axis_len=axis_len,
        valid_min=0.0,
        valid_max=250.0,
        ignore_below_or_equal_min_for_invalid_ratio=True,
    )
    return {
        "avg_power": _safe_float(row.get("avg_power"), None),
        "max_power": _safe_float(row.get("max_power"), None),
        "normalized_power": _safe_float(row.get("normalized_power"), None),
        "avg_cadence": _safe_float(row.get("avg_cadence"), None),
        "duration_sec": _safe_int(row.get("duration_sec") or row.get("duration") or bundle.get("duration_sec") or 0),
        "power_available": power_available,
        "cadence_available": cadence_available,
        "power_points_count": power_count,
        "cadence_points_count": cadence_count,
        "power_data_quality": power_quality,
        "cadence_data_quality": cadence_quality,
    }


def _cycling_power_variability_unavailable(
    summary: dict[str, Any] | None = None,
    reason: str = "power data unavailable",
    confidence: str = "unavailable",
) -> dict[str, Any]:
    summary = summary or {}
    return {
        "vi": None,
        "level": "unknown",
        "confidence": confidence,
        "avg_power": _safe_float(summary.get("avg_power"), None),
        "normalized_power": _safe_float(summary.get("normalized_power"), None),
        "power_points_count": _safe_int(summary.get("power_points_count") or 0),
        "power_data_quality": str(summary.get("power_data_quality") or "missing"),
        "reasons": [reason],
    }


def _cycling_pedaling_stability_unavailable(
    summary: dict[str, Any] | None = None,
    reason: str = "cadence data unavailable",
    confidence: str = "unavailable",
) -> dict[str, Any]:
    summary = summary or {}
    return {
        "score": None,
        "level": "unknown",
        "confidence": confidence,
        "cv": None,
        "decay_pct": None,
        "avg_cadence": _safe_float(summary.get("avg_cadence"), None),
        "cadence_points_count": _safe_int(summary.get("cadence_points_count") or 0),
        "cadence_data_quality": str(summary.get("cadence_data_quality") or "missing"),
        "reasons": [reason],
    }


def _cycling_metric_confidence(points_count: int) -> str:
    if points_count >= 120:
        return "high"
    if points_count >= 20:
        return "medium"
    if points_count > 0:
        return "low"
    return "unavailable"


def _build_cycling_power_variability_metric(summary: dict[str, Any]) -> dict[str, Any]:
    """P3 cycling metric: VI = normalized_power / avg_power, never recompute NP."""
    summary = summary or {}
    quality = str(summary.get("power_data_quality") or "missing")
    points_count = _safe_int(summary.get("power_points_count") or 0)
    if quality != "available":
        return _cycling_power_variability_unavailable(
            summary,
            reason=f"power data unavailable: {quality}",
        )

    avg_power = _safe_float(summary.get("avg_power"), None)
    normalized_power = _safe_float(summary.get("normalized_power"), None)
    if avg_power is None or avg_power <= 0:
        return _cycling_power_variability_unavailable(
            summary,
            reason="missing avg_power",
            confidence="low" if points_count > 0 else "unavailable",
        )
    if normalized_power is None or normalized_power <= 0:
        return _cycling_power_variability_unavailable(
            summary,
            reason="missing normalized_power",
            confidence="low" if points_count > 0 else "unavailable",
        )

    vi = round(normalized_power / avg_power, 2)
    if vi < 1.05:
        level = "good"
    elif vi < 1.15:
        level = "moderate"
    elif vi < 1.30:
        level = "variable"
    else:
        level = "surging"

    return {
        "vi": vi,
        "level": level,
        "confidence": _cycling_metric_confidence(points_count),
        "avg_power": avg_power,
        "normalized_power": normalized_power,
        "power_points_count": points_count,
        "power_data_quality": quality,
        "reasons": [],
    }


def _build_cycling_pedaling_stability_metric(
    summary: dict[str, Any],
    cadence_curve: list[Any],
) -> dict[str, Any]:
    """P3 cycling metric: conservative cadence stability from same-axis cadence curve."""
    summary = summary or {}
    quality = str(summary.get("cadence_data_quality") or "missing")
    points_count = _safe_int(summary.get("cadence_points_count") or 0)
    if quality != "available":
        return _cycling_pedaling_stability_unavailable(
            summary,
            reason=f"cadence data unavailable: {quality}",
        )
    if not isinstance(cadence_curve, list):
        return _cycling_pedaling_stability_unavailable(
            summary,
            reason="cadence curve unavailable",
        )

    values = []
    for value in cadence_curve:
        num = _safe_float(value, None)
        if num is not None and 0 < num <= 250:
            values.append(num)
    if len(values) < 20:
        return _cycling_pedaling_stability_unavailable(
            summary,
            reason="cadence data unavailable: insufficient_points",
            confidence="low" if values else "unavailable",
        )

    mean_value = sum(values) / len(values)
    if mean_value <= 0:
        return _cycling_pedaling_stability_unavailable(
            summary,
            reason="cadence mean unavailable",
        )
    variance = sum((value - mean_value) ** 2 for value in values) / len(values)
    cv = variance ** 0.5 / mean_value

    midpoint = len(values) // 2
    head_values = values[:midpoint]
    tail_values = values[midpoint:]
    head_avg = sum(head_values) / len(head_values) if head_values else 0.0
    tail_avg = sum(tail_values) / len(tail_values) if tail_values else 0.0
    decay_pct = ((tail_avg - head_avg) / head_avg * 100.0) if head_avg > 0 else 0.0

    cv_penalty = min(45.0, cv * 300.0)
    decay_penalty = min(35.0, abs(decay_pct) * 1.5)
    score = round(max(0.0, min(100.0, 100.0 - cv_penalty - decay_penalty)), 1)
    if score >= 80:
        level = "good"
    elif score >= 60:
        level = "moderate"
    elif score >= 40:
        level = "unstable"
    else:
        level = "poor"

    return {
        "score": score,
        "level": level,
        "confidence": _cycling_metric_confidence(points_count),
        "cv": round(cv, 3),
        "decay_pct": round(decay_pct, 1),
        "avg_cadence": _safe_float(summary.get("avg_cadence"), None),
        "cadence_points_count": points_count,
        "cadence_data_quality": quality,
        "reasons": [],
    }


def _cycling_power_efficiency_unavailable(
    summary: dict[str, Any] | None = None,
    avg_hr: Any = None,
    reason: str = "cycling power efficiency unavailable",
    confidence: str = "unavailable",
) -> dict[str, Any]:
    summary = summary or {}
    return {
        "score": None,
        "level": "unknown",
        "confidence": confidence,
        "delta_pct": None,
        "sample_size": 0,
        "basis": "power_hr",
        "power_per_hr": None,
        "avg_power": _safe_float(summary.get("avg_power"), None),
        "avg_hr": _safe_float(avg_hr, None),
        "power_data_quality": str(summary.get("power_data_quality") or "missing"),
        "reasons": [reason],
    }


def _build_cycling_power_efficiency_metric(
    summary: dict[str, Any],
    avg_hr: Any,
) -> dict[str, Any]:
    """P3b cycling metric: conservative power-per-heart-rate efficiency."""
    summary = summary or {}
    quality = str(summary.get("power_data_quality") or "missing")
    if quality != "available":
        return _cycling_power_efficiency_unavailable(
            summary,
            avg_hr=avg_hr,
            reason=f"power data unavailable: {quality}",
        )

    avg_power = _safe_float(summary.get("avg_power"), None)
    avg_hr_value = _safe_float(avg_hr, None)
    if avg_power is None or avg_power <= 0:
        return _cycling_power_efficiency_unavailable(
            summary,
            avg_hr=avg_hr,
            reason="missing avg_power",
            confidence="low",
        )
    if avg_hr_value is None or avg_hr_value <= 0:
        return _cycling_power_efficiency_unavailable(
            summary,
            avg_hr=avg_hr,
            reason="missing avg_hr",
            confidence="low",
        )

    power_per_hr = round(avg_power / avg_hr_value, 3)
    if power_per_hr < 1.2:
        score, level = 45, "low"
    elif power_per_hr < 1.8:
        score, level = 65, "moderate"
    elif power_per_hr < 2.5:
        score, level = 80, "good"
    else:
        score, level = 90, "good"

    return {
        "score": score,
        "level": level,
        "confidence": _cycling_metric_confidence(_safe_int(summary.get("power_points_count") or 0)),
        "delta_pct": None,
        "sample_size": 0,
        "basis": "power_hr",
        "power_per_hr": power_per_hr,
        "avg_power": avg_power,
        "avg_hr": avg_hr_value,
        "power_data_quality": quality,
        "reasons": [],
    }


def _cycling_power_durability_unavailable(
    summary: dict[str, Any] | None = None,
    reason: str = "cycling power durability unavailable",
    confidence: str = "unavailable",
) -> dict[str, Any]:
    summary = summary or {}
    return {
        "score": None,
        "level": "unknown",
        "confidence": confidence,
        "head_speed": None,
        "tail_speed": None,
        "basis": "power_retention",
        "head_power": None,
        "tail_power": None,
        "power_retention_pct": None,
        "power_points_count": _safe_int(summary.get("power_points_count") or 0),
        "power_data_quality": str(summary.get("power_data_quality") or "missing"),
        "reasons": [reason],
    }


def _build_cycling_power_durability_metric(
    summary: dict[str, Any],
    power_curve: list[Any],
) -> dict[str, Any]:
    """P3b cycling metric: late-ride power retention from same-axis power curve."""
    summary = summary or {}
    quality = str(summary.get("power_data_quality") or "missing")
    if quality != "available":
        return _cycling_power_durability_unavailable(
            summary,
            reason=f"power data unavailable: {quality}",
        )
    if not isinstance(power_curve, list):
        return _cycling_power_durability_unavailable(
            summary,
            reason="power curve unavailable",
        )

    values = []
    for value in power_curve:
        num = _safe_float(value, None)
        if num is not None and 0 < num <= 2500:
            values.append(num)
    if len(values) < 20:
        return _cycling_power_durability_unavailable(
            summary,
            reason="power data unavailable: insufficient_points",
            confidence="low" if values else "unavailable",
        )

    midpoint = len(values) // 2
    head_values = values[:midpoint]
    tail_values = values[midpoint:]
    head_power = sum(head_values) / len(head_values) if head_values else 0.0
    tail_power = sum(tail_values) / len(tail_values) if tail_values else 0.0
    if head_power <= 0 or tail_power <= 0:
        return _cycling_power_durability_unavailable(
            summary,
            reason="power retention unavailable",
        )

    retention = round(tail_power / head_power * 100.0, 1)
    if retention >= 95:
        score, level = 90, "good"
    elif retention >= 90:
        score, level = 78, "moderate"
    elif retention >= 80:
        score, level = 62, "dropping"
    else:
        score, level = 45, "dropping"

    points_count = _safe_int(summary.get("power_points_count") or len(values))
    return {
        "score": score,
        "level": level,
        "confidence": _cycling_metric_confidence(points_count),
        "head_speed": None,
        "tail_speed": None,
        "basis": "power_retention",
        "head_power": round(head_power, 1),
        "tail_power": round(tail_power, 1),
        "power_retention_pct": retention,
        "power_points_count": points_count,
        "power_data_quality": quality,
        "reasons": [],
    }


def _build_unavailable_cycling_metrics(summary: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    return {
        "power_variability": _cycling_power_variability_unavailable(
            summary,
            reason="cycling power metric unavailable for this sport",
        ),
        "pedaling_stability": _cycling_pedaling_stability_unavailable(
            summary,
            reason="cycling cadence metric unavailable for this sport",
        ),
    }


def _build_cycling_review_metrics(
    sport_type: str | None,
    summary: dict[str, Any],
    curves_snapshot: dict[str, Any],
    avg_hr: Any = None,
) -> dict[str, dict[str, Any]]:
    if sport_type not in _CYCLING_SPORT_TYPES:
        return _build_unavailable_cycling_metrics(summary)
    return {
        "efficiency": _build_cycling_power_efficiency_metric(summary, avg_hr),
        "durability": _build_cycling_power_durability_metric(
            summary,
            curves_snapshot.get("power") if isinstance(curves_snapshot, dict) else [],
        ),
        "power_variability": _build_cycling_power_variability_metric(summary),
        "pedaling_stability": _build_cycling_pedaling_stability_metric(
            summary,
            curves_snapshot.get("cadence") if isinstance(curves_snapshot, dict) else [],
        ),
    }


def _cycling_format_watts(value: Any) -> str:
    num = _safe_float(value, None)
    if num is None:
        return ""
    return f"{int(round(num))}W"


def _cycling_format_pct(value: Any, digits: int = 1) -> str:
    num = _safe_float(value, None)
    if num is None:
        return ""
    return f"{num:.{digits}f}%"


def _cycling_evidence_display_fields(item: dict[str, Any]) -> dict[str, Any]:
    item_type = str(item.get("type") or "")
    hidden = {
        "power_data_quality",
        "aerobic_drift_data_quality",
        "cadence_data_quality",
        "cycling_pacing_data_quality",
        "hr_drift_reference",
        "review_decoupling_reference",
        "power_retention_metric_reference",
        "pedaling_stability_metric_reference",
    }
    base = {
        "visibility": "hidden" if item_type in hidden else "visible",
        "source": "review_snapshot",
    }

    def fields(label: str, display_value: str, description: str, unit: str = "") -> dict[str, Any]:
        return {
            **base,
            "label": label,
            "display_value": display_value,
            "unit": unit,
            "description": description,
        }

    if item_type in hidden:
        return fields("参考依据", "", "该证据仅用于内部解释权重，不直接展示给用户。")

    if item_type == "ride_power_summary":
        parts = []
        avg_power = _cycling_format_watts(item.get("avg_power"))
        normalized_power = _cycling_format_watts(item.get("normalized_power"))
        max_power = _cycling_format_watts(item.get("max_power"))
        if avg_power:
            parts.append(f"平均功率 {avg_power}")
        if normalized_power:
            parts.append(f"标准化功率 {normalized_power}")
        if max_power:
            parts.append(f"最高功率 {max_power}")
        return fields("本次功率", " / ".join(parts), "用于判断本次输出强度的功率摘要。", "W")

    if item_type == "personal_ftp":
        parts = []
        ftp_watts = _cycling_format_watts(item.get("ftp_watts"))
        if ftp_watts:
            parts.append(f"个人 FTP {ftp_watts}")
        ratio = _safe_float(item.get("normalized_power_to_ftp"), None)
        if ratio is None:
            ratio = _safe_float(item.get("avg_power_to_ftp"), None)
        if ratio is not None:
            parts.append(f"相对个人阈值约 {int(round(ratio * 100))}%")
        display = " / ".join(parts)
        result = fields("相对个人阈值", display, "用个人 FTP 和本次功率摘要判断这次对你来说强不强。", "%")
        result["source"] = "user_profile"
        return result

    if item_type == "cycling_aerobic_drift":
        parts = []
        decoupling = _cycling_format_pct(item.get("decoupling_pct"), 1)
        if decoupling:
            parts.append(f"后半程效率变化 {decoupling}")
        head_power = _cycling_format_watts(item.get("head_power"))
        tail_power = _cycling_format_watts(item.get("tail_power"))
        if head_power and tail_power:
            parts.append(f"前段 {head_power} / 后段 {tail_power}")
        head_hr = _safe_float(item.get("head_hr"), None)
        tail_hr = _safe_float(item.get("tail_hr"), None)
        if head_hr is not None and tail_hr is not None:
            parts.append(f"前段心率 {int(round(head_hr))} / 后段 {int(round(tail_hr))} bpm")
        return fields("功率心率关系", " / ".join(parts), "比较前后段功率和心率关系，判断后半程是否更吃力。")

    if item_type == "effective_pedaling_power_retention":
        parts = []
        head_power = _cycling_format_watts(item.get("head_effective_power"))
        tail_power = _cycling_format_watts(item.get("tail_effective_power"))
        if head_power and tail_power:
            parts.append(f"有效踩踏前半 {head_power} / 后半 {tail_power}")
        retention = _cycling_format_pct(item.get("power_retention_pct"), 1)
        if retention:
            parts.append(f"后程保持 {retention}")
        if not parts and _safe_int(item.get("filtered_points_count") or 0) > 0:
            parts.append("已排除滑行和停顿影响")
        return fields("有效踩踏后程", " / ".join(parts), "先排除滑行、停顿和异常片段，再比较前后段功率。")

    if item_type == "cycling_pacing_reference":
        parts = []
        head_power = _cycling_format_watts(item.get("head_power"))
        tail_power = _cycling_format_watts(item.get("tail_power"))
        if head_power and tail_power:
            parts.append(f"前半 {head_power} / 后半 {tail_power}")
        early_delta = _safe_float(item.get("early_to_mid_delta_pct"), None)
        if early_delta is not None and abs(early_delta) >= 8:
            parts.append(f"开局相对中段变化 {early_delta:.1f}%")
        power_cv = _safe_float(item.get("power_cv"), None)
        if power_cv is not None:
            parts.append(f"功率波动约 {power_cv * 100:.1f}%")
        return fields("功率节奏", " / ".join(parts), "观察前段是否过冲、后段是否回落，以及输出是否忽高忽低。")

    if item_type == "cycling_cadence_rhythm":
        parts = []
        avg_cadence = _safe_float(item.get("avg_cadence"), None)
        if avg_cadence is not None:
            parts.append(f"平均踏频 {avg_cadence:.0f} rpm")
        cadence_cv = _safe_float(item.get("cadence_cv"), None)
        if cadence_cv is not None:
            parts.append(f"踏频波动 {cadence_cv * 100:.1f}%")
        cadence_drop = _cycling_format_pct(item.get("cadence_drop_pct"), 1)
        if cadence_drop:
            parts.append(f"后段踏频变化 {cadence_drop}")
        zero_ratio = _safe_float(item.get("zero_cadence_ratio"), None)
        if zero_ratio is not None and zero_ratio >= 0.05:
            parts.append(f"零踏频占比约 {zero_ratio * 100:.1f}%")
        return fields("踏频节奏", " / ".join(parts), "观察踩踏是否连续、是否波动大，以及后段节奏是否变散。", "rpm")

    return fields("参考依据", "", "该证据暂不直接展示。")


def _decorate_cycling_evidence(evidence: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    decorated: list[dict[str, Any]] = []
    for item in evidence or []:
        if not isinstance(item, dict):
            continue
        merged = dict(item)
        display_fields = _cycling_evidence_display_fields(merged)
        for key, value in display_fields.items():
            merged.setdefault(key, value)
        if merged.get("visibility") == "hidden":
            merged["display_value"] = ""
        if not str(merged.get("display_value") or "").strip() and merged.get("visibility") == "visible":
            merged["visibility"] = "hidden"
        decorated.append(merged)
    return decorated


def _cycling_explanation_signal(
    status: str,
    summary: str,
    reasons: list[str] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    level: str = "unknown",
) -> dict[str, Any]:
    return {
        "status": status,
        "level": level,
        "summary": summary,
        "evidence": _decorate_cycling_evidence(evidence),
        "reasons": reasons or [],
    }


def _build_cycling_intensity_signal(
    summary: dict[str, Any],
    profile_ftp_watts: Any = None,
    profile_weight_kg: Any = None,
) -> dict[str, Any]:
    power_quality = str(summary.get("power_data_quality") or "missing")
    has_power = bool(summary.get("power_available"))
    avg_power = _safe_float(summary.get("avg_power"), None)
    normalized_power = _safe_float(summary.get("normalized_power"), None)
    max_power = _safe_float(summary.get("max_power"), None)
    points_count = _safe_int(summary.get("power_points_count") or 0)
    duration_sec = _safe_int(summary.get("duration_sec") or 0)
    ftp_watts = _safe_float(profile_ftp_watts, None)
    weight_kg = _safe_float(profile_weight_kg, None)

    evidence: list[dict[str, Any]] = [{
        "type": "power_data_quality",
        "power_available": has_power,
        "power_data_quality": power_quality,
        "power_points_count": points_count,
    }]
    if duration_sec > 0:
        evidence[0]["duration_sec"] = duration_sec
    power_facts: dict[str, Any] = {"type": "ride_power_summary"}
    if avg_power is not None:
        power_facts["avg_power"] = avg_power
    if normalized_power is not None:
        power_facts["normalized_power"] = normalized_power
    if max_power is not None:
        power_facts["max_power"] = max_power
    if len(power_facts) > 1:
        if not has_power or power_quality != "available":
            power_facts["visibility"] = "hidden"
        evidence.append(power_facts)

    if not has_power:
        reasons = [f"power_data_unavailable:{power_quality}"]
        if ftp_watts is None or ftp_watts <= 0:
            reasons.append("missing_ftp")
        return _cycling_explanation_signal(
            "unavailable",
            "缺少可用功率数据，暂不判断本次骑行的个人强度。",
            reasons,
        evidence,
    )

    if power_quality != "available":
        return _cycling_explanation_signal(
            "unavailable",
            "功率数据质量不足，暂不判断本次骑行的个人强度。",
            [f"power_data_unavailable:{power_quality}"],
            evidence,
        )

    if points_count < 60:
        return _cycling_explanation_signal(
            "unavailable",
            "可用功率样本太少，暂不判断本次骑行的个人强度。",
            ["insufficient_power_points"],
            evidence,
        )

    if ftp_watts is None or ftp_watts <= 0:
        return _cycling_explanation_signal(
            "unavailable",
            "缺少个人 FTP，暂不判断本次骑行相对强度。",
            ["missing_ftp"],
            evidence,
        )

    ftp_evidence: dict[str, Any] = {
        "type": "personal_ftp",
        "ftp_watts": round(ftp_watts, 1),
        "source": "user_profile",
    }
    if weight_kg is not None and weight_kg > 0:
        ftp_evidence["weight_kg"] = round(weight_kg, 1)
    if avg_power is not None and avg_power > 0:
        ftp_evidence["avg_power_to_ftp"] = round(avg_power / ftp_watts, 3)
    if normalized_power is not None and normalized_power > 0:
        ftp_evidence["normalized_power_to_ftp"] = round(normalized_power / ftp_watts, 3)

    reference_power = normalized_power if normalized_power is not None and normalized_power > 0 else avg_power
    reference_source = "normalized_power" if normalized_power is not None and normalized_power > 0 else "avg_power"
    if reference_power is None or reference_power <= 0:
        evidence.append(ftp_evidence)
        return _cycling_explanation_signal(
            "unavailable",
            "缺少可用功率摘要，暂不判断本次骑行的个人强度。",
            ["missing_power_summary"],
            evidence,
        )

    intensity_ratio = reference_power / ftp_watts
    ftp_evidence["intensity_ratio"] = round(intensity_ratio, 3)
    ftp_evidence["intensity_basis"] = reference_source
    evidence.append(ftp_evidence)

    if intensity_ratio < 0.55:
        level = "recovery"
        summary_text = "这次骑行相对强度偏恢复，主要是轻刺激。"
    elif intensity_ratio < 0.75:
        level = "endurance"
        summary_text = "这次骑行主要是耐力强度，整体刺激可控。"
    elif intensity_ratio < 0.90:
        level = "tempo"
        summary_text = "这次骑行进入节奏强度，对你来说已经不是轻松骑。"
    elif intensity_ratio <= 1.05:
        level = "threshold"
        summary_text = "这次骑行相对强度接近阈值，对你来说负荷不轻。"
    else:
        level = "high_intensity"
        summary_text = "这次骑行相对强度高于阈值，属于高压力输出。"

    reasons = ["personal_ftp_available", f"intensity_basis:{reference_source}"]
    return _cycling_explanation_signal("available", summary_text, reasons, evidence, level=level)


def _build_cycling_aerobic_drift_signal(
    summary: dict[str, Any],
    curves_snapshot: dict[str, Any],
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    def _unavailable_result(reason: str, evidence_item: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "unavailable",
            "level": "unknown",
            "reasons": [reason],
            "evidence": evidence_item,
        }

    power_quality = str(summary.get("power_data_quality") or "missing")
    has_power = bool(summary.get("power_available"))
    power_points_count = _safe_int(summary.get("power_points_count") or 0)
    hr_curve = curves_snapshot.get("hr") if isinstance(curves_snapshot.get("hr"), list) else []
    power_curve = curves_snapshot.get("power") if isinstance(curves_snapshot.get("power"), list) else []
    has_hr = bool(hr_curve)
    metrics = metrics if isinstance(metrics, dict) else {}

    evidence: list[dict[str, Any]] = [{
        "type": "aerobic_drift_data_quality",
        "has_hr": has_hr,
        "power_available": has_power,
        "power_data_quality": power_quality,
        "power_points_count": power_points_count,
    }]

    hr_drift = metrics.get("hr_drift") if isinstance(metrics.get("hr_drift"), dict) else {}
    if hr_drift:
        item: dict[str, Any] = {"type": "hr_drift_reference"}
        for key in ("pct", "level", "confidence"):
            if key in hr_drift:
                item[key] = hr_drift.get(key)
        reasons = hr_drift.get("reasons")
        if isinstance(reasons, list) and reasons:
            item["reasons"] = [str(reason) for reason in reasons[:3]]
        if len(item) > 1:
            evidence.append(item)

    decoupling = metrics.get("decoupling") if isinstance(metrics.get("decoupling"), dict) else {}
    if decoupling:
        item = {"type": "review_decoupling_reference"}
        for key in ("pct", "level", "confidence"):
            if key in decoupling:
                item[key] = decoupling.get(key)
        if len(item) > 1:
            evidence.append(item)

    if not has_power:
        return _cycling_explanation_signal(
            "unavailable",
            "缺少可用功率数据，暂不判断本次骑行有氧漂移。",
            [f"power_data_unavailable:{power_quality}"],
            evidence,
        )

    if power_quality != "available":
        return _cycling_explanation_signal(
            "unavailable",
            "功率数据质量不足，暂不判断本次骑行有氧漂移。",
            [f"power_data_unavailable:{power_quality}"],
            evidence,
        )

    if not has_hr:
        return _cycling_explanation_signal(
            "unavailable",
            "缺少心率曲线，暂不判断本次骑行有氧漂移。",
            ["missing_hr"],
            evidence,
        )

    if not power_curve:
        return _cycling_explanation_signal(
            "unavailable",
            "缺少功率曲线，暂不判断本次骑行有氧漂移。",
            ["missing_power_curve"],
            evidence,
        )

    axis_len = min(len(power_curve), len(hr_curve))
    if axis_len < 40:
        drift_result = _unavailable_result(
            "insufficient_power_hr_points",
            {
                "type": "cycling_aerobic_drift",
                "basis": "effective_power_hr_decoupling",
                "power_data_quality": power_quality,
                "power_points_count": power_points_count,
                "effective_points_count": 0,
                "filtered_points_count": axis_len,
                "filter_reasons": ["insufficient_points"],
            },
        )
        evidence.append(drift_result["evidence"])
        return _cycling_explanation_signal(
            "unavailable",
            "功率与心率有效样本不足，暂不判断本次骑行有氧漂移。",
            drift_result["reasons"],
            evidence,
        )

    if len(power_curve) != len(hr_curve):
        length_evidence = {
            "type": "cycling_aerobic_drift",
            "basis": "effective_power_hr_decoupling",
            "power_data_quality": power_quality,
            "power_points_count": power_points_count,
            "effective_points_count": 0,
            "filtered_points_count": max(len(power_curve), len(hr_curve)),
            "filter_reasons": ["curve_length_mismatch"],
        }
        evidence.append(length_evidence)
        return _cycling_explanation_signal(
            "unavailable",
            "功率与心率曲线无法稳定对齐，暂不判断本次骑行有氧漂移。",
            ["curve_length_mismatch"],
            evidence,
        )

    speed_curve = curves_snapshot.get("speed") if isinstance(curves_snapshot.get("speed"), list) else []
    if len(speed_curve) != axis_len:
        speed_curve = []
    time_curve = curves_snapshot.get("time") if isinstance(curves_snapshot.get("time"), list) else []
    if len(time_curve) != axis_len:
        time_curve = []

    avg_power = _safe_float(summary.get("avg_power"), None)
    power_threshold = max(30.0, (avg_power * 0.2) if avg_power and avg_power > 0 else 30.0)
    midpoint = axis_len // 2
    head_power_values: list[float] = []
    head_hr_values: list[float] = []
    tail_power_values: list[float] = []
    tail_hr_values: list[float] = []
    filtered_points_count = 0
    filter_reasons: list[str] = []
    prev_time: float | None = None

    for idx in range(axis_len):
        current_time = _safe_float(time_curve[idx], None) if time_curve else None
        reason = None
        power = _safe_float(power_curve[idx], None)
        hr = _safe_float(hr_curve[idx], None)
        if power is None:
            reason = "invalid_power"
        elif power > 2500:
            reason = "abnormal_power"
        elif power <= power_threshold:
            reason = "coasting"
        elif hr is None:
            reason = "invalid_hr"
        elif hr < 35 or hr > 230:
            reason = "abnormal_hr"

        if reason is None and speed_curve:
            speed = _safe_float(speed_curve[idx], None)
            if speed is not None and speed <= 1.0:
                reason = "stopped"

        if reason is None and time_curve:
            if current_time is None:
                reason = "time_gap"
            elif prev_time is not None:
                delta = current_time - prev_time
                if delta <= 0 or delta > 30:
                    reason = "time_gap"

        if current_time is not None:
            prev_time = current_time

        if reason is not None:
            filtered_points_count += 1
            if reason not in filter_reasons:
                filter_reasons.append(reason)
            continue

        if idx < midpoint:
            head_power_values.append(float(power))
            head_hr_values.append(float(hr))
        else:
            tail_power_values.append(float(power))
            tail_hr_values.append(float(hr))

    effective_count = len(head_power_values) + len(tail_power_values)
    if len(head_power_values) < 20 or len(tail_power_values) < 20:
        evidence.append({
            "type": "cycling_aerobic_drift",
            "basis": "effective_power_hr_decoupling",
            "power_data_quality": power_quality,
            "power_points_count": power_points_count,
            "effective_points_count": effective_count,
            "head_effective_points_count": len(head_power_values),
            "tail_effective_points_count": len(tail_power_values),
            "filtered_points_count": filtered_points_count,
            "filter_reasons": filter_reasons or ["insufficient_points"],
            "power_threshold_watts": round(power_threshold, 1),
        })
        return _cycling_explanation_signal(
            "unavailable",
            "功率与心率有效样本不足，暂不判断本次骑行有氧漂移。",
            ["insufficient_power_hr_points"],
            evidence,
        )

    head_power = sum(head_power_values) / len(head_power_values)
    tail_power = sum(tail_power_values) / len(tail_power_values)
    head_hr = sum(head_hr_values) / len(head_hr_values)
    tail_hr = sum(tail_hr_values) / len(tail_hr_values)
    if head_power <= 0 or tail_power <= 0 or head_hr <= 0 or tail_hr <= 0:
        evidence.append({
            "type": "cycling_aerobic_drift",
            "basis": "effective_power_hr_decoupling",
            "power_data_quality": power_quality,
            "power_points_count": power_points_count,
            "effective_points_count": effective_count,
            "filtered_points_count": filtered_points_count,
            "filter_reasons": filter_reasons,
        })
        return _cycling_explanation_signal(
            "unavailable",
            "功率与心率关系无法稳定计算，暂不判断本次骑行有氧漂移。",
            ["power_hr_ratio_unavailable"],
            evidence,
        )

    head_power_per_hr = head_power / head_hr
    tail_power_per_hr = tail_power / tail_hr
    decoupling_pct = (head_power_per_hr - tail_power_per_hr) / head_power_per_hr * 100.0
    decoupling_pct = round(decoupling_pct, 1)
    if decoupling_pct <= 5.0:
        level = "stable"
        summary_text = "后半程功率与心率关系保持稳定，暂未看到明显有氧漂移。"
    elif decoupling_pct <= 10.0:
        level = "mild_drift"
        summary_text = "后半程同等心率下的功率略有下降，出现轻微有氧漂移。"
    else:
        level = "significant_drift"
        summary_text = "后半程功率与心率关系明显分离，有氧漂移较明显。"

    confidence = "high" if effective_count >= 180 else "medium" if effective_count >= 80 else "low"
    evidence.append({
        "type": "cycling_aerobic_drift",
        "basis": "effective_power_hr_decoupling",
        "head_power": round(head_power, 1),
        "tail_power": round(tail_power, 1),
        "head_hr": round(head_hr, 1),
        "tail_hr": round(tail_hr, 1),
        "head_power_per_hr": round(head_power_per_hr, 3),
        "tail_power_per_hr": round(tail_power_per_hr, 3),
        "decoupling_pct": decoupling_pct,
        "effective_points_count": effective_count,
        "head_effective_points_count": len(head_power_values),
        "tail_effective_points_count": len(tail_power_values),
        "filtered_points_count": filtered_points_count,
        "filter_reasons": filter_reasons,
        "power_threshold_watts": round(power_threshold, 1),
        "power_data_quality": power_quality,
        "confidence": confidence,
    })
    return _cycling_explanation_signal(
        "available" if confidence != "low" else "partial",
        summary_text,
        ["effective_power_hr_decoupling"],
        evidence,
        level=level,
    )


def _build_effective_pedaling_power_retention(
    summary: dict[str, Any],
    curves_snapshot: dict[str, Any],
) -> dict[str, Any]:
    """P3: compare front/back power after filtering coasting, stops, and time gaps."""
    summary = summary if isinstance(summary, dict) else {}
    curves_snapshot = curves_snapshot if isinstance(curves_snapshot, dict) else {}
    quality = str(summary.get("power_data_quality") or "missing")
    has_power = bool(summary.get("power_available"))
    points_count = _safe_int(summary.get("power_points_count") or 0)

    if not has_power or quality != "available":
        return {
            "status": "unavailable",
            "level": "unknown",
            "reasons": [f"power_data_unavailable:{quality}"],
            "evidence": {
                "type": "effective_pedaling_power_retention",
                "basis": "effective_pedaling_power",
                "power_data_quality": quality,
                "power_points_count": points_count,
                "effective_power_points_count": 0,
                "filtered_points_count": 0,
                "filter_reasons": [],
            },
        }

    power_curve = curves_snapshot.get("power") if isinstance(curves_snapshot.get("power"), list) else []
    axis_len = len(power_curve)
    if axis_len < 20:
        return {
            "status": "unavailable",
            "level": "unknown",
            "reasons": ["insufficient_effective_pedaling_points"],
            "evidence": {
                "type": "effective_pedaling_power_retention",
                "basis": "effective_pedaling_power",
                "power_data_quality": quality,
                "power_points_count": points_count,
                "effective_power_points_count": 0,
                "filtered_points_count": axis_len,
                "filter_reasons": ["insufficient_points"],
            },
        }

    speed_curve = curves_snapshot.get("speed") if isinstance(curves_snapshot.get("speed"), list) else []
    if len(speed_curve) != axis_len:
        speed_curve = []
    time_curve = curves_snapshot.get("time") if isinstance(curves_snapshot.get("time"), list) else []
    if len(time_curve) != axis_len:
        time_curve = []

    avg_power = _safe_float(summary.get("avg_power"), None)
    power_threshold = max(30.0, (avg_power * 0.2) if avg_power and avg_power > 0 else 30.0)
    midpoint = axis_len // 2
    head_values: list[float] = []
    tail_values: list[float] = []
    filtered_points_count = 0
    filter_reasons: list[str] = []
    prev_time: float | None = None

    for idx, raw_power in enumerate(power_curve):
        current_time = _safe_float(time_curve[idx], None) if time_curve else None
        reason = None
        power = _safe_float(raw_power, None)
        if power is None:
            reason = "invalid_power"
        elif power > 2500:
            reason = "abnormal_power"
        elif power <= power_threshold:
            reason = "coasting"

        if reason is None and speed_curve:
            speed = _safe_float(speed_curve[idx], None)
            if speed is not None and speed <= 1.0:
                reason = "stopped"

        if reason is None and time_curve:
            if current_time is None:
                reason = "time_gap"
            elif prev_time is not None:
                delta = current_time - prev_time
                if delta <= 0 or delta > 30:
                    reason = "time_gap"

        if current_time is not None:
            prev_time = current_time

        if reason is not None:
            filtered_points_count += 1
            if reason not in filter_reasons:
                filter_reasons.append(reason)
            continue

        if idx < midpoint:
            head_values.append(float(power))
        else:
            tail_values.append(float(power))

    effective_count = len(head_values) + len(tail_values)
    if len(head_values) < 10 or len(tail_values) < 10:
        return {
            "status": "unavailable",
            "level": "unknown",
            "reasons": ["insufficient_effective_pedaling_points"],
            "evidence": {
                "type": "effective_pedaling_power_retention",
                "basis": "effective_pedaling_power",
                "power_data_quality": quality,
                "power_points_count": points_count,
                "effective_power_points_count": effective_count,
                "head_effective_points_count": len(head_values),
                "tail_effective_points_count": len(tail_values),
                "filtered_points_count": filtered_points_count,
                "filter_reasons": filter_reasons or ["insufficient_points"],
            },
        }

    head_power = sum(head_values) / len(head_values)
    tail_power = sum(tail_values) / len(tail_values)
    if head_power <= 0 or tail_power <= 0:
        return {
            "status": "unavailable",
            "level": "unknown",
            "reasons": ["effective_power_retention_unavailable"],
            "evidence": {
                "type": "effective_pedaling_power_retention",
                "basis": "effective_pedaling_power",
                "power_data_quality": quality,
                "power_points_count": points_count,
                "effective_power_points_count": effective_count,
                "filtered_points_count": filtered_points_count,
                "filter_reasons": filter_reasons,
            },
        }

    retention = round(tail_power / head_power * 100.0, 1)
    if retention >= 95.0:
        level = "held"
    elif retention >= 85.0:
        level = "slight_drop"
    else:
        level = "clear_drop"

    confidence = "high" if effective_count >= 120 else "medium" if effective_count >= 40 else "low"
    return {
        "status": "available" if confidence != "low" else "partial",
        "level": level,
        "reasons": [],
        "evidence": {
            "type": "effective_pedaling_power_retention",
            "basis": "effective_pedaling_power",
            "head_effective_power": round(head_power, 1),
            "tail_effective_power": round(tail_power, 1),
            "power_retention_pct": retention,
            "effective_power_points_count": effective_count,
            "head_effective_points_count": len(head_values),
            "tail_effective_points_count": len(tail_values),
            "filtered_points_count": filtered_points_count,
            "filter_reasons": filter_reasons,
            "power_threshold_watts": round(power_threshold, 1),
            "power_data_quality": quality,
            "confidence": confidence,
        },
    }


def _build_cycling_power_retention_signal(
    summary: dict[str, Any],
    curves_snapshot: dict[str, Any],
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metrics = metrics if isinstance(metrics, dict) else {}
    result = _build_effective_pedaling_power_retention(summary, curves_snapshot)
    evidence: list[dict[str, Any]] = []
    result_evidence = result.get("evidence")
    if isinstance(result_evidence, dict):
        evidence.append(result_evidence)

    durability = metrics.get("durability") if isinstance(metrics.get("durability"), dict) else {}
    if durability.get("basis") == "power_retention":
        reference: dict[str, Any] = {"type": "power_retention_metric_reference"}
        for key in (
            "basis",
            "head_power",
            "tail_power",
            "power_retention_pct",
            "power_points_count",
            "power_data_quality",
        ):
            if key in durability:
                reference[key] = durability.get(key)
        if len(reference) > 1:
            evidence.append(reference)

    status = str(result.get("status") or "unavailable")
    level = str(result.get("level") or "unknown")
    reasons = [str(reason) for reason in (result.get("reasons") or [])]

    if status == "available" or status == "partial":
        if level == "held":
            summary_text = "有效踩踏段后半程功率保持稳定。"
        elif level == "slight_drop":
            summary_text = "有效踩踏段后半程功率有小幅回落。"
        elif level == "clear_drop":
            summary_text = "有效踩踏段后半程功率明显回落。"
        else:
            summary_text = "已生成有效踩踏段后程保持参考证据。"
        return _cycling_explanation_signal(status, summary_text, reasons, evidence, level=level)

    if reasons and reasons[0].startswith("power_data_unavailable:"):
        summary_text = "缺少可用功率曲线，暂不判断有效踩踏段后程保持。"
    else:
        summary_text = "有效踩踏段样本不足，暂不判断后程功率保持。"
    return _cycling_explanation_signal("unavailable", summary_text, reasons, evidence, level="unknown")


def _build_cycling_pacing_signal(
    summary: dict[str, Any],
    curves_snapshot: dict[str, Any],
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = summary if isinstance(summary, dict) else {}
    curves_snapshot = curves_snapshot if isinstance(curves_snapshot, dict) else {}
    metrics = metrics if isinstance(metrics, dict) else {}

    quality = str(summary.get("power_data_quality") or "missing")
    has_power = bool(summary.get("power_available"))
    points_count = _safe_int(summary.get("power_points_count") or 0)

    variability = metrics.get("power_variability") if isinstance(metrics.get("power_variability"), dict) else {}
    durability = metrics.get("durability") if isinstance(metrics.get("durability"), dict) else {}

    evidence: list[dict[str, Any]] = [{
        "type": "cycling_pacing_data_quality",
        "power_available": has_power,
        "power_data_quality": quality,
        "power_points_count": points_count,
    }]

    if not has_power or quality != "available":
        return _cycling_explanation_signal(
            "unavailable",
            "缺少可用功率曲线，暂不判断骑行功率节奏。",
            [f"power_data_unavailable:{quality}"],
            evidence,
        )

    power_curve = curves_snapshot.get("power") if isinstance(curves_snapshot.get("power"), list) else []
    values: list[float] = []
    for value in power_curve:
        power = _safe_float(value, None)
        if power is not None and 0 < power <= 2500:
            values.append(power)

    if len(values) < 20:
        return _cycling_explanation_signal(
            "unavailable",
            "功率样本不足，暂不判断骑行功率节奏。",
            ["insufficient_power_points"],
            evidence,
        )

    midpoint = len(values) // 2
    quarter = max(1, len(values) // 4)
    head_values = values[:midpoint]
    tail_values = values[midpoint:]
    early_values = values[:quarter]
    mid_values = values[quarter:midpoint] or head_values
    avg_power = sum(values) / len(values)
    head_power = sum(head_values) / len(head_values)
    tail_power = sum(tail_values) / len(tail_values)
    early_power = sum(early_values) / len(early_values)
    mid_power = sum(mid_values) / len(mid_values)
    variance = sum((value - avg_power) ** 2 for value in values) / len(values)
    power_cv = (variance ** 0.5 / avg_power) if avg_power > 0 else 0.0
    front_to_tail_delta_pct = ((tail_power - head_power) / head_power * 100.0) if head_power > 0 else 0.0
    early_to_mid_delta_pct = ((early_power - mid_power) / mid_power * 100.0) if mid_power > 0 else 0.0

    vi = _safe_float(variability.get("vi"), None)
    power_variability_level = str(variability.get("level") or "unknown")
    pacing_evidence: dict[str, Any] = {
        "type": "cycling_pacing_reference",
        "basis": "power_curve_and_vi",
        "head_power": round(head_power, 1),
        "tail_power": round(tail_power, 1),
        "early_power": round(early_power, 1),
        "mid_power": round(mid_power, 1),
        "front_to_tail_delta_pct": round(front_to_tail_delta_pct, 1),
        "early_to_mid_delta_pct": round(early_to_mid_delta_pct, 1),
        "power_cv": round(power_cv, 3),
        "power_points_count": points_count or len(values),
    }
    if vi is not None:
        pacing_evidence["vi"] = round(vi, 2)
    if power_variability_level:
        pacing_evidence["power_variability_level"] = power_variability_level
    if durability.get("power_retention_pct") is not None:
        pacing_evidence["power_retention_pct"] = durability.get("power_retention_pct")
    evidence.append(pacing_evidence)

    variable_by_vi = vi is not None and vi >= 1.15
    variable_by_cv = power_cv >= 0.25
    front_loaded = early_to_mid_delta_pct >= 10.0 and front_to_tail_delta_pct <= -10.0
    late_fade = front_to_tail_delta_pct <= -12.0
    steady = (
        (vi is None or vi <= 1.08)
        and power_cv <= 0.15
        and abs(front_to_tail_delta_pct) <= 8.0
        and early_to_mid_delta_pct < 10.0
    )

    if variable_by_vi or variable_by_cv:
        level = "variable"
        summary_text = "本次骑行功率输出波动较大。"
    elif front_loaded:
        level = "front_loaded"
        summary_text = "本次骑行前段输出偏高，可能增加后程回落压力。"
    elif late_fade:
        level = "late_fade"
        summary_text = "本次骑行后段功率出现回落。"
    elif steady:
        level = "steady"
        summary_text = "本次骑行功率输出较平稳，未看到明显前段过冲。"
    else:
        level = "variable"
        summary_text = "本次骑行功率节奏有一定波动。"

    return _cycling_explanation_signal("available", summary_text, [], evidence, level=level)


def _build_cycling_cadence_signal(
    summary: dict[str, Any],
    curves_snapshot: dict[str, Any],
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = summary if isinstance(summary, dict) else {}
    curves_snapshot = curves_snapshot if isinstance(curves_snapshot, dict) else {}
    metrics = metrics if isinstance(metrics, dict) else {}

    quality = str(summary.get("cadence_data_quality") or "missing")
    has_cadence = bool(summary.get("cadence_available"))
    points_count = _safe_int(summary.get("cadence_points_count") or 0)
    avg_cadence_summary = _safe_float(summary.get("avg_cadence"), None)

    evidence: list[dict[str, Any]] = [{
        "type": "cadence_data_quality",
        "cadence_available": has_cadence,
        "cadence_data_quality": quality,
        "cadence_points_count": points_count,
    }]
    if avg_cadence_summary is not None and avg_cadence_summary > 0:
        evidence[0]["avg_cadence"] = round(avg_cadence_summary, 1)

    if not has_cadence or quality != "available":
        return _cycling_explanation_signal(
            "unavailable",
            "缺少可用踏频曲线，暂不判断踩踏节奏。",
            [f"cadence_data_unavailable:{quality}"],
            evidence,
        )

    cadence_curve = curves_snapshot.get("cadence") if isinstance(curves_snapshot.get("cadence"), list) else []
    axis_len = len(cadence_curve)
    if axis_len < 20:
        evidence.append({
            "type": "cycling_cadence_rhythm",
            "basis": "effective_cadence_curve",
            "cadence_data_quality": quality,
            "cadence_points_count": points_count,
            "effective_cadence_points_count": 0,
            "filtered_points_count": axis_len,
            "filter_reasons": ["insufficient_points"],
        })
        return _cycling_explanation_signal(
            "unavailable",
            "踏频有效样本不足，暂不判断踩踏节奏。",
            ["insufficient_cadence_points"],
            evidence,
        )

    speed_curve = curves_snapshot.get("speed") if isinstance(curves_snapshot.get("speed"), list) else []
    if speed_curve and len(speed_curve) != axis_len:
        evidence.append({
            "type": "cycling_cadence_rhythm",
            "basis": "effective_cadence_curve",
            "cadence_data_quality": quality,
            "cadence_points_count": points_count,
            "effective_cadence_points_count": 0,
            "filtered_points_count": max(axis_len, len(speed_curve)),
            "filter_reasons": ["curve_length_mismatch"],
        })
        return _cycling_explanation_signal(
            "unavailable",
            "踏频与速度曲线无法稳定对齐，暂不判断踩踏节奏。",
            ["curve_length_mismatch"],
            evidence,
        )

    power_curve = curves_snapshot.get("power") if isinstance(curves_snapshot.get("power"), list) else []
    if power_curve and len(power_curve) != axis_len:
        evidence.append({
            "type": "cycling_cadence_rhythm",
            "basis": "effective_cadence_curve",
            "cadence_data_quality": quality,
            "cadence_points_count": points_count,
            "effective_cadence_points_count": 0,
            "filtered_points_count": max(axis_len, len(power_curve)),
            "filter_reasons": ["curve_length_mismatch"],
        })
        return _cycling_explanation_signal(
            "unavailable",
            "踏频与功率曲线无法稳定对齐，暂不判断踩踏节奏。",
            ["curve_length_mismatch"],
            evidence,
        )

    time_curve = curves_snapshot.get("time") if isinstance(curves_snapshot.get("time"), list) else []
    if time_curve and len(time_curve) != axis_len:
        evidence.append({
            "type": "cycling_cadence_rhythm",
            "basis": "effective_cadence_curve",
            "cadence_data_quality": quality,
            "cadence_points_count": points_count,
            "effective_cadence_points_count": 0,
            "filtered_points_count": max(axis_len, len(time_curve)),
            "filter_reasons": ["curve_length_mismatch"],
        })
        return _cycling_explanation_signal(
            "unavailable",
            "踏频与时间曲线无法稳定对齐，暂不判断踩踏节奏。",
            ["curve_length_mismatch"],
            evidence,
        )

    midpoint = axis_len // 2
    effective_values: list[float] = []
    head_values: list[float] = []
    tail_values: list[float] = []
    zero_cadence_count = 0
    filtered_points_count = 0
    filter_reasons: list[str] = []
    prev_time: float | None = None

    for idx, raw_cadence in enumerate(cadence_curve):
        current_time = _safe_float(time_curve[idx], None) if time_curve else None
        reason = None
        cadence = _safe_float(raw_cadence, None)
        if cadence is None:
            reason = "invalid_cadence"
        elif cadence <= 0:
            reason = "zero_cadence"
            zero_cadence_count += 1
        elif cadence > 250:
            reason = "abnormal_cadence"

        if reason is None and speed_curve:
            speed = _safe_float(speed_curve[idx], None)
            if speed is not None and speed <= 1.0:
                reason = "stopped"

        if reason is None and power_curve:
            power = _safe_float(power_curve[idx], None)
            if power is not None and power <= 5.0:
                reason = "coasting"
        elif reason == "zero_cadence" and power_curve:
            power = _safe_float(power_curve[idx], None)
            if power is not None and power <= 5.0 and "coasting" not in filter_reasons:
                filter_reasons.append("coasting")

        if reason is None and time_curve:
            if current_time is None:
                reason = "time_gap"
            elif prev_time is not None:
                delta = current_time - prev_time
                if delta <= 0 or delta > 30:
                    reason = "time_gap"

        if current_time is not None:
            prev_time = current_time

        if reason is not None:
            filtered_points_count += 1
            if reason not in filter_reasons:
                filter_reasons.append(reason)
            continue

        effective_values.append(float(cadence))
        if idx < midpoint:
            head_values.append(float(cadence))
        else:
            tail_values.append(float(cadence))

    effective_count = len(effective_values)
    zero_cadence_ratio = zero_cadence_count / axis_len if axis_len > 0 else 0.0
    if effective_count < 20 or len(head_values) < 10 or len(tail_values) < 10:
        evidence.append({
            "type": "cycling_cadence_rhythm",
            "basis": "effective_cadence_curve",
            "cadence_data_quality": quality,
            "cadence_points_count": points_count,
            "effective_cadence_points_count": effective_count,
            "head_effective_points_count": len(head_values),
            "tail_effective_points_count": len(tail_values),
            "filtered_points_count": filtered_points_count,
            "filter_reasons": filter_reasons or ["insufficient_points"],
            "zero_cadence_ratio": round(zero_cadence_ratio, 3),
        })
        return _cycling_explanation_signal(
            "unavailable",
            "踏频有效样本不足，暂不判断踩踏节奏。",
            ["insufficient_cadence_points"],
            evidence,
        )

    avg_cadence = sum(effective_values) / effective_count
    head_cadence = sum(head_values) / len(head_values)
    tail_cadence = sum(tail_values) / len(tail_values)
    variance = sum((value - avg_cadence) ** 2 for value in effective_values) / effective_count
    cadence_std = variance ** 0.5
    cadence_cv = cadence_std / avg_cadence if avg_cadence > 0 else 0.0
    cadence_drop_pct = ((tail_cadence - head_cadence) / head_cadence * 100.0) if head_cadence > 0 else 0.0
    low_cadence_count = sum(1 for value in effective_values if value < 70.0)
    low_cadence_ratio = low_cadence_count / effective_count if effective_count else 0.0

    pedaling = metrics.get("pedaling_stability") if isinstance(metrics.get("pedaling_stability"), dict) else {}
    pedaling_reference: dict[str, Any] = {"type": "pedaling_stability_metric_reference"}
    for key in ("score", "level", "confidence", "cv", "decay_pct", "avg_cadence", "cadence_points_count", "cadence_data_quality"):
        if key in pedaling:
            pedaling_reference[key] = pedaling.get(key)
    if len(pedaling_reference) > 1:
        evidence.append(pedaling_reference)

    confidence = "high" if effective_count >= 180 else "medium" if effective_count >= 80 else "low"
    cadence_evidence = {
        "type": "cycling_cadence_rhythm",
        "basis": "effective_cadence_curve",
        "avg_cadence": round(avg_cadence, 1),
        "head_cadence": round(head_cadence, 1),
        "tail_cadence": round(tail_cadence, 1),
        "cadence_cv": round(cadence_cv, 3),
        "cadence_std": round(cadence_std, 1),
        "cadence_drop_pct": round(cadence_drop_pct, 1),
        "low_cadence_ratio": round(low_cadence_ratio, 3),
        "zero_cadence_ratio": round(zero_cadence_ratio, 3),
        "effective_cadence_points_count": effective_count,
        "head_effective_points_count": len(head_values),
        "tail_effective_points_count": len(tail_values),
        "filtered_points_count": filtered_points_count,
        "filter_reasons": filter_reasons,
        "cadence_data_quality": quality,
        "confidence": confidence,
    }
    evidence.append(cadence_evidence)

    if zero_cadence_ratio >= 0.20 or "coasting" in filter_reasons and filtered_points_count / axis_len >= 0.25:
        level = "interrupted"
        summary_text = "本次踩踏中断较多，节奏连续性一般。"
    elif cadence_cv >= 0.12 or cadence_std >= 10.0:
        level = "variable"
        summary_text = "本次骑行踏频波动较大，踩踏节奏不够连续。"
    elif avg_cadence < 72.0 or low_cadence_ratio >= 0.45:
        level = "low_cadence_bias"
        summary_text = "本次骑行踏频整体偏低，更像偏力量型输出。"
    elif cadence_drop_pct <= -10.0:
        level = "cadence_drop"
        summary_text = "后半程踏频有所下降，踩踏节奏后段变得不够利落。"
    else:
        level = "steady"
        summary_text = "本次骑行踏频节奏比较稳定，踩踏组织没有明显散掉。"

    return _cycling_explanation_signal(
        "available" if confidence != "low" else "partial",
        summary_text,
        ["effective_cadence_rhythm"],
        evidence,
        level=level,
    )


def _build_cycling_explanation_signals(
    sport_type: str | None,
    summary: dict[str, Any] | None = None,
    curves_snapshot: dict[str, Any] | None = None,
    profile_ftp_watts: Any = None,
    profile_weight_kg: Any = None,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Cycling explanation contract; each task only advances its named signal."""
    summary = summary if isinstance(summary, dict) else {}
    curves_snapshot = curves_snapshot if isinstance(curves_snapshot, dict) else {}
    metrics = metrics if isinstance(metrics, dict) else {}
    if sport_type not in _CYCLING_SPORT_TYPES:
        unavailable = ["not_cycling_activity"]
        return {
            "status": "unavailable",
            "intensity_signal": _cycling_explanation_signal(
                "unavailable",
                "非骑行活动不生成骑行解释信号。",
                unavailable,
            ),
            "aerobic_drift_signal": _cycling_explanation_signal(
                "unavailable",
                "非骑行活动不判断骑行有氧漂移。",
                unavailable,
            ),
            "power_retention_signal": _cycling_explanation_signal(
                "unavailable",
                "非骑行活动不判断骑行后程功率保持。",
                unavailable,
            ),
            "pacing_signal": _cycling_explanation_signal(
                "unavailable",
                "非骑行活动不判断骑行功率节奏。",
                unavailable,
            ),
            "cadence_signal": _cycling_explanation_signal(
                "unavailable",
                "非骑行活动不判断骑行踏频解释。",
                unavailable,
            ),
            "evidence": [],
            "unavailable_reasons": unavailable,
        }

    power_quality = str(summary.get("power_data_quality") or "missing")
    cadence_quality = str(summary.get("cadence_data_quality") or "missing")
    has_power = bool(summary.get("power_available"))
    has_cadence = bool(summary.get("cadence_available"))
    has_hr = bool(curves_snapshot.get("hr"))
    ftp_watts = _safe_float(profile_ftp_watts, None)

    unavailable_reasons: list[str] = []
    if ftp_watts is None or ftp_watts <= 0:
        unavailable_reasons.append("missing_ftp")
    if not has_power:
        unavailable_reasons.append(f"power_data_unavailable:{power_quality}")
    if not has_hr:
        unavailable_reasons.append("missing_hr")
    if not has_cadence:
        unavailable_reasons.append(f"cadence_data_unavailable:{cadence_quality}")

    return {
        "status": "partial",
        "intensity_signal": _build_cycling_intensity_signal(
            summary,
            profile_ftp_watts=ftp_watts,
            profile_weight_kg=profile_weight_kg,
        ),
        "aerobic_drift_signal": _build_cycling_aerobic_drift_signal(
            summary,
            curves_snapshot,
            metrics=metrics,
        ),
        "power_retention_signal": _build_cycling_power_retention_signal(
            summary,
            curves_snapshot,
            metrics=metrics,
        ),
        "pacing_signal": _build_cycling_pacing_signal(
            summary,
            curves_snapshot,
            metrics=metrics,
        ),
        "cadence_signal": _build_cycling_cadence_signal(
            summary,
            curves_snapshot,
            metrics=metrics,
        ),
        "evidence": [],
        "unavailable_reasons": list(dict.fromkeys(unavailable_reasons)),
    }


def _build_fatigue_review_curves_snapshot(
    bundle: dict[str, Any],
    resolved: dict[str, Any],
) -> dict[str, Any]:
    """Build the P2 authoritative curve snapshot consumed by the frontend.

    P2 rule: use the backend distance axis as truth. Curves with mismatched
    length are omitted instead of asking the frontend to infer or pad facts.
    """
    distance_curve_m = resolved.get("distance_curve") or bundle.get("distance_curve_m") or []
    axis_len = _fatigue_review_axis_len(distance_curve_m)
    total_distance_m = _safe_float(bundle.get("total_distance_m")) or 0.0

    if axis_len <= 0:
        return {
            "distance": [],
            "time": [],
            "efficiency": [],
            "gap": [],
            "grade": [],
            "terrain_load": [],
            "hr": [],
            "altitude": [],
            "speed": [],
            "power": [],
            "cadence": [],
            "total_distance_m": total_distance_m,
        }

    distance = [
        round(float(_safe_float(value) or 0.0) / 1000.0, 3)
        for value in distance_curve_m
    ]
    time_curve = _fatigue_review_numeric_curve(
        resolved.get("time_curve") or bundle.get("time_curve_sec") or [],
        axis_len,
        3,
    )
    grade_curve = _fatigue_review_numeric_curve(
        resolved.get("grade_curve") or [],
        axis_len,
    )
    speed_curve = _fatigue_review_numeric_curve(
        resolved.get("speed_curve") or bundle.get("speed_curve_mps") or [],
        axis_len,
    )
    return {
        "distance": distance,
        "time": time_curve,
        "efficiency": _fatigue_review_numeric_curve(
            resolved.get("efficiency_curve") or [],
            axis_len,
        ),
        "gap": _fatigue_review_numeric_curve(
            resolved.get("gap_curve") or [],
            axis_len,
        ),
        "grade": grade_curve,
        "terrain_load": _build_fatigue_review_terrain_load_curve(
            grade_curve=grade_curve,
            speed_curve=speed_curve,
            time_curve=time_curve,
            axis_len=axis_len,
        ),
        "hr": _fatigue_review_numeric_curve(
            resolved.get("hr_curve") or bundle.get("hr_curve") or [],
            axis_len,
        ),
        "altitude": _fatigue_review_numeric_curve(
            resolved.get("altitude_curve") or bundle.get("altitude_curve_m") or [],
            axis_len,
        ),
        "speed": speed_curve,
        "power": _fatigue_review_numeric_curve(
            resolved.get("power_curve") or bundle.get("power_curve") or [],
            axis_len,
        ),
        "cadence": _fatigue_review_numeric_curve(
            resolved.get("cadence_curve") or bundle.get("cadence_curve") or [],
            axis_len,
        ),
        "total_distance_m": total_distance_m,
    }


def _strip_fatigue_review_forbidden_keys(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_fatigue_review_forbidden_keys(item)
            for key, item in value.items()
            if key not in _FATIGUE_REVIEW_FORBIDDEN_KEYS
        }
    if isinstance(value, list):
        return [_strip_fatigue_review_forbidden_keys(item) for item in value]
    return value


def _compute_hr_drift_from_curve(hr_curve: list) -> float | None:
    """V8.2: 从 hr_curve 计算心率漂移百分比。

    定义: (后20%均值 - 前20%均值) / 前20%均值 × 100
    > 0 表示心率随时间上升(热漂/脱水/疲劳)
    < 0 表示心率下降(冷却/恢复)
    见 docs/physiology_reference.md §指标 6

    Args:
        hr_curve: 心率逐点序列

    Returns:
        float | None: 漂移百分比,样本不足时返回 None
    """
    valid = [h for h in hr_curve if h and h > 0]
    if len(valid) < 20:
        return None
    n = len(valid)
    split = max(1, n // 5)
    first_mean = sum(valid[:split]) / split
    last_mean = sum(valid[-split:]) / split
    if first_mean <= 0:
        return None
    return round((last_mean - first_mean) / first_mean * 100.0, 2)


def _compute_speed_decay_from_curve(speed_curve: list) -> float | None:
    """V8.2: 从 speed_curve 计算速度衰减百分比。

    定义: (前20%均值 - 后20%均值) / 前20%均值 × 100
    > 0 表示后程降速(疲劳)
    < 0 表示后程加速(负配速)

    Args:
        speed_curve: 速度逐点序列

    Returns:
        float | None: 衰减百分比,样本不足时返回 None
    """
    valid = [s for s in speed_curve if s and s > 0]
    if len(valid) < 20:
        return None
    n = len(valid)
    split = max(1, n // 5)
    first_mean = sum(valid[:split]) / split
    last_mean = sum(valid[-split:]) / split
    if first_mean <= 0:
        return None
    return round((first_mean - last_mean) / first_mean * 100.0, 2)


def _compute_hr_zone_distribution(
    hr_curve: list,
    max_hr: float | None,
) -> str | None:
    """V8.4: 从 hr_curve 和 max_hr 计算 Z1-Z5 心率区间分布,序列化为 JSON。

    区间定义(Banister 模型,基于 max_hr 百分比):
    - Z1: < 60% max_hr(恢复区)
    - Z2: 60-70% max_hr(有氧基础)
    - Z3: 70-80% max_hr(有氧)
    - Z4: 80-90% max_hr(阈值)
    - Z5: ≥ 90% max_hr(无氧)

    假设 hr_curve 采样间隔 1s(V8.4 简化;V8.x 可加 sample_interval_sec 参数)。

    契约:
    - §2.1 全链路可追溯:hr_zone 来源 = hr_curve + 个人最大心率
    - §8 canonical 写入:此函数输出仅供 INSERT/UPDATE 流程
    - §2.2 数据可信分层:max_hr 缺失时拒写(None),不写入假数据

    Args:
        hr_curve: 心率逐点序列
        max_hr: 个人最大心率(bpm),无则返回 None

    Returns:
        str: JSON 字典 '{"Z1": sec, "Z2": sec, ...}' (单位:秒)
        None: hr_curve 空 / max_hr 无效(< 30 视为设备无 HR 数据)
    """
    if not hr_curve or not max_hr or max_hr < 30:
        return None

    z1 = z2 = z3 = z4 = z5 = 0
    for h in hr_curve:
        if h is None or h <= 0:
            continue
        ratio = float(h) / float(max_hr)
        if ratio < 0.6:
            z1 += 1
        elif ratio < 0.7:
            z2 += 1
        elif ratio < 0.8:
            z3 += 1
        elif ratio < 0.9:
            z4 += 1
        else:
            z5 += 1

    return json.dumps(
        {"Z1": z1, "Z2": z2, "Z3": z3, "Z4": z4, "Z5": z5},
        ensure_ascii=False,
    )


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
            try:
                profile_backend.backfill_auto_activity_titles(conn)
            except Exception as exc:
                logger.warning("自动活动标题回填失败，已跳过: %s", exc)

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
            _safe_data_migrate(
                conn,
                """
                UPDATE activities
                SET processing_status = CASE
                        WHEN COALESCE(NULLIF(track_json, ''), NULLIF(points_json, '')) IS NOT NULL THEN 'ready'
                        ELSE COALESCE(NULLIF(processing_status, ''), 'ready')
                    END
                WHERE processing_status IS NULL OR processing_status = ''
                """
            )
            _safe_data_migrate(
                conn,
                """
                UPDATE activities
                SET weather_status = CASE
                        WHEN weather_json IS NOT NULL AND weather_json != '' THEN 'success'
                        WHEN start_lat IS NULL OR start_lon IS NULL THEN 'none'
                        ELSE COALESCE(NULLIF(weather_status, ''), 'pending')
                    END,
                    weather_attempt_count = COALESCE(weather_attempt_count, 0)
                WHERE weather_status IS NULL OR weather_status = ''
                   OR weather_attempt_count IS NULL
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_activities_processing_status ON activities(processing_status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_activities_weather_status ON activities(weather_status)")
            profile_backend._ensure_activity_list_indexes(conn)
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
from utils.metrics_calc import AdvancedMetricsCalc, RadarScoreEngine, _CYCLING_SPORT_TYPES


def _convert_track_to_algorithm_records(track_data: list[dict]) -> list[dict]:
    """V4.0 治理: 业务逻辑已下沉至 MetricsResolver。
    完整实现见 metrics_resolver.py: MetricsResolver._convert_track_to_algorithm_records
    """
    return MetricsResolver._convert_track_to_algorithm_records(track_data)


def _compute_advanced_metrics(track_data: list[dict], sport_type: str | None = None) -> dict:
    """V4.0 治理: IO 隔离，纯计算下沉至 MetricsResolver。

    IO 层留在 main.py(profile_backend.get_profile()),
    纯计算见 metrics_resolver.py: MetricsResolver._compute_advanced_metrics
    """
    records = MetricsResolver._convert_track_to_algorithm_records(track_data)
    if not records or len(records) < 2:
        return {}
    prof = profile_backend.get_profile()
    user_profile_dict = prof.to_dict() if prof else {}
    result = MetricsResolver._compute_advanced_metrics(records, user_profile_dict, sport_type)
    if result:
        result["metrics_version"] = CURRENT_METRICS_VERSION
    return result


def needs_advanced_metrics_rebuild(metrics: dict | str | None) -> bool:
    """Return True when stored advanced_metrics is missing, invalid, or stale."""
    if not metrics:
        return True
    try:
        if isinstance(metrics, str):
            parsed = json.loads(metrics)
        else:
            parsed = metrics
        if not isinstance(parsed, dict):
            return True
        version = parsed.get("metrics_version")
        if version is None:
            return True
        return int(float(version)) < CURRENT_METRICS_VERSION
    except (TypeError, ValueError, json.JSONDecodeError):
        return True


def _resolve_normalized_power_for_sync(
    basic: dict[str, Any],
    raw_laps: list,
    track_data: list[dict],
    resolver_sm: dict[str, Any] | None = None,
) -> int | None:
    """Resolve NP from FIT canonical fields without depending on Resolver output shape."""
    for value in (
        basic.get("normalized_power"),
        (resolver_sm or {}).get("normalized_power_w"),
    ):
        np_value = _safe_float(value, None)
        if np_value and np_value > 0:
            return int(round(np_value))

    lap_values: list[float] = []
    for lap in raw_laps or []:
        if not isinstance(lap, dict):
            continue
        value = _safe_float(lap.get("normalized_power"), None)
        duration = _safe_float(lap.get("total_timer_time"), None)
        if value and value > 0:
            if duration and duration > 0:
                lap_values.extend([value] * max(1, int(round(duration))))
            else:
                lap_values.append(value)
    if lap_values:
        fourth_mean = sum(v ** 4 for v in lap_values) / len(lap_values)
        return int(round(fourth_mean ** 0.25))

    power_values = [
        float(power)
        for point in (track_data or [])
        for power in [_safe_float(point.get("power"), None)]
        if power is not None and power > 0
    ]
    if len(power_values) >= 30:
        fourth_mean = sum(v ** 4 for v in power_values) / len(power_values)
        return int(round(fourth_mean ** 0.25))
    return None


_NP_BACKFILL_LOCK = threading.Lock()
_NP_BACKFILL_STATUS: dict[str, Any] = {
    "running": False,
    "total": 0,
    "processed": 0,
    "updated": 0,
    "limited": False,
    "np_total": 0,
    "np_updated": 0,
    "power_total": 0,
    "power_updated": 0,
    "water_total": 0,
    "water_updated": 0,
    "started_at": 0.0,
    "finished_at": 0.0,
    "error": "",
}
_NP_BACKFILL_THREAD: threading.Thread | None = None
_NP_BACKFILL_TIMER: threading.Timer | None = None
LIST_METRIC_BACKFILL_BATCH_LIMIT = 200
LIST_METRIC_BACKFILL_VERSION = 1
_WEATHER_BACKFILL_LOCK = threading.Lock()
_WEATHER_BACKFILL_STATUS: dict[str, Any] = {
    "running": False,
    "scheduled": False,
    "total": 0,
    "processed": 0,
    "updated": 0,
    "failed": 0,
    "limited": False,
    "started_at": 0.0,
    "finished_at": 0.0,
    "error": "",
}
_WEATHER_BACKFILL_THREAD: threading.Thread | None = None
_WEATHER_BACKFILL_TIMER: threading.Timer | None = None


def _normalized_power_backfill_status() -> dict[str, Any]:
    with _NP_BACKFILL_LOCK:
        return dict(_NP_BACKFILL_STATUS)


def _weather_backfill_status() -> dict[str, Any]:
    with _WEATHER_BACKFILL_LOCK:
        return dict(_WEATHER_BACKFILL_STATUS)


def _read_normalized_power_fast_from_fit(file_path: Any) -> int | None:
    path_text = str(file_path or "").strip()
    if not path_text:
        return None
    path = Path(path_text).expanduser()
    if not path.is_file():
        return None
    try:
        from fitparse import FitFile

        fit = FitFile(str(path))
        for msg in fit.get_messages("session"):
            value = _safe_float(msg.get_value("normalized_power"), None)
            if value and value > 0:
                return int(round(value))

        weighted_fourth_sum = 0.0
        total_weight = 0.0
        for msg in fit.get_messages("lap"):
            value = _safe_float(msg.get_value("normalized_power"), None)
            if not value or value <= 0:
                continue
            weight = _safe_float(msg.get_value("total_timer_time"), 1.0) or 1.0
            weight = max(1.0, min(weight, 24 * 3600.0))
            weighted_fourth_sum += (value ** 4) * weight
            total_weight += weight
        if total_weight > 0:
            return int(round((weighted_fourth_sum / total_weight) ** 0.25))

        record_fourth_sum = 0.0
        record_count = 0
        for msg in fit.get_messages("record"):
            value = _safe_float(msg.get_value("power"), None)
            if value and value > 0:
                record_fourth_sum += value ** 4
                record_count += 1
        if record_count >= 30:
            return int(round((record_fourth_sum / record_count) ** 0.25))
    except Exception:
        return None
    return None


def _read_activity_metrics_fast_from_fit(file_path: Any) -> dict[str, float | int | None]:
    metrics: dict[str, float | int | None] = {
        "avg_power": None,
        "max_power": None,
        "normalized_power": None,
        "avg_stroke_distance": None,
        "swolf": None,
    }
    path_text = str(file_path or "").strip()
    if not path_text:
        return metrics
    path = Path(path_text).expanduser()
    if not path.is_file():
        return metrics

    try:
        from fitparse import FitFile

        fit = FitFile(str(path))
        weighted_np_fourth_sum = 0.0
        weighted_np_total = 0.0
        lap_swolf_values: list[float] = []

        for msg in fit.get_messages("session"):
            avg_power = _safe_float(msg.get_value("avg_power"), None)
            if avg_power and avg_power > 0:
                metrics["avg_power"] = int(round(avg_power))
            max_power = _safe_float(msg.get_value("max_power"), None)
            if max_power and max_power > 0:
                metrics["max_power"] = int(round(max_power))
            normalized_power = _safe_float(msg.get_value("normalized_power"), None)
            if normalized_power and normalized_power > 0:
                metrics["normalized_power"] = int(round(normalized_power))
            stroke_distance = _safe_float(msg.get_value("avg_stroke_distance"), None)
            if stroke_distance and stroke_distance > 0:
                metrics["avg_stroke_distance"] = float(stroke_distance)
            raw_swolf = _safe_float(msg.get_value("avg_swolf"), None)
            if raw_swolf and raw_swolf > 0:
                metrics["swolf"] = int(round(raw_swolf))

        for msg in fit.get_messages("lap"):
            if not metrics.get("normalized_power"):
                value = _safe_float(msg.get_value("normalized_power"), None)
                if value and value > 0:
                    weight = _safe_float(msg.get_value("total_timer_time"), 1.0) or 1.0
                    weight = max(1.0, min(weight, 24 * 3600.0))
                    weighted_np_fourth_sum += (value ** 4) * weight
                    weighted_np_total += weight
            if not metrics.get("swolf"):
                raw_swolf = _safe_float(msg.get_value("avg_swolf"), None)
                if raw_swolf and raw_swolf > 0:
                    lap_swolf_values.append(raw_swolf)
                    continue
                lengths = _safe_float(msg.get_value("num_lengths"), 0.0) or 0.0
                cycles = _safe_float(msg.get_value("total_strokes") or msg.get_value("total_cycles"), 0.0) or 0.0
                timer = _safe_float(msg.get_value("total_timer_time"), 0.0) or 0.0
                if lengths > 0 and cycles > 0 and timer > 0:
                    lap_swolf_values.append((cycles / lengths) + (timer / lengths))
            if not metrics.get("avg_stroke_distance"):
                stroke_distance = _safe_float(msg.get_value("avg_stroke_distance"), None)
                if stroke_distance and stroke_distance > 0:
                    metrics["avg_stroke_distance"] = float(stroke_distance)

        if not metrics.get("normalized_power") and weighted_np_total > 0:
            metrics["normalized_power"] = int(round((weighted_np_fourth_sum / weighted_np_total) ** 0.25))
        if not metrics.get("swolf") and lap_swolf_values:
            metrics["swolf"] = int(round(sum(lap_swolf_values) / len(lap_swolf_values)))

        if not metrics.get("normalized_power"):
            record_fourth_sum = 0.0
            record_count = 0
            for msg in fit.get_messages("record"):
                value = _safe_float(msg.get_value("power"), None)
                if value and value > 0:
                    record_fourth_sum += value ** 4
                    record_count += 1
            if record_count >= 30:
                metrics["normalized_power"] = int(round((record_fourth_sum / record_count) ** 0.25))
    except Exception:
        return metrics
    return metrics


def _resolve_water_metric_value_for_backfill(
    sport_type: Any,
    sub_sport_type: Any,
    metrics: dict[str, float | None],
) -> float | None:
    display_type = _resolve_display_sport_type(sport_type, sub_sport_type)
    display_token = _normalize_activity_token(display_type, "")
    sub_token = _normalize_activity_token(sub_sport_type, "")
    if sub_token == "lap_swimming" or display_token in ("swimming", "lap_swimming"):
        return _safe_float(metrics.get("swolf"), None)
    if display_token in WATER_METRIC_DISPLAY_TYPES:
        return _safe_float(metrics.get("avg_stroke_distance") or metrics.get("stroke_distance"), None)
    return None


def _run_normalized_power_backfill_worker(db_path: str) -> None:
    started = time.time()
    processed = 0
    updated = 0
    np_updated = 0
    power_updated = 0
    water_updated = 0
    total = 0
    limited = False
    error = ""
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(db_path, timeout=profile_backend.SQLITE_CONNECT_TIMEOUT_SEC)
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout = {profile_backend.SQLITE_BUSY_TIMEOUT_MS}")
        limit = LIST_METRIC_BACKFILL_BATCH_LIMIT
        power_rows = conn.execute(
            """
            SELECT id, file_path
            FROM activities
            WHERE deleted_at IS NULL
              AND (avg_power IS NULL OR max_power IS NULL OR normalized_power IS NULL)
              AND COALESCE(list_metric_backfill_version, 0) < ?
              AND COALESCE(file_path, '') != ''
              AND lower(COALESCE(sport_type, '')) IN (
                  'running', 'trail_running', 'treadmill_running',
                  'cycling', 'road_cycling', 'mountain_biking'
              )
            ORDER BY id DESC
            LIMIT ?
            """,
            (LIST_METRIC_BACKFILL_VERSION, limit),
        ).fetchall()
        remaining_power = conn.execute(
            """
            SELECT COUNT(*)
            FROM activities
            WHERE deleted_at IS NULL
              AND (avg_power IS NULL OR max_power IS NULL OR normalized_power IS NULL)
              AND COALESCE(list_metric_backfill_version, 0) < ?
              AND COALESCE(file_path, '') != ''
              AND lower(COALESCE(sport_type, '')) IN (
                  'running', 'trail_running', 'treadmill_running',
                  'cycling', 'road_cycling', 'mountain_biking'
              )
            """
            ,
            (LIST_METRIC_BACKFILL_VERSION,),
        ).fetchall()
        remaining_power_count = int(remaining_power[0][0] if remaining_power else 0)
        water_limit = max(0, limit - len(power_rows))
        water_rows = conn.execute(
            """
            SELECT id, file_path, sport_type, sub_sport_type
            FROM activities
            WHERE deleted_at IS NULL
              AND (swolf IS NULL OR avg_stroke_distance IS NULL)
              AND COALESCE(list_metric_backfill_version, 0) < ?
              AND COALESCE(file_path, '') != ''
              AND (
                  lower(COALESCE(sport_type, '')) IN (
                      'swimming', 'lap_swimming', 'open_water',
                      'open_water_swimming', 'stand_up_paddleboarding', 'paddling'
                  )
                  OR lower(COALESCE(sub_sport_type, '')) IN (
                      'lap_swimming', 'open_water', 'open_water_swimming',
                      'stand_up_paddleboarding', 'paddling'
                  )
              )
            ORDER BY id DESC
            LIMIT ?
            """
            ,
            (LIST_METRIC_BACKFILL_VERSION, water_limit),
        ).fetchall()
        remaining_water = conn.execute(
            """
            SELECT COUNT(*)
            FROM activities
            WHERE deleted_at IS NULL
              AND (swolf IS NULL OR avg_stroke_distance IS NULL)
              AND COALESCE(list_metric_backfill_version, 0) < ?
              AND COALESCE(file_path, '') != ''
              AND (
                  lower(COALESCE(sport_type, '')) IN (
                      'swimming', 'lap_swimming', 'open_water',
                      'open_water_swimming', 'stand_up_paddleboarding', 'paddling'
                  )
                  OR lower(COALESCE(sub_sport_type, '')) IN (
                      'lap_swimming', 'open_water', 'open_water_swimming',
                      'stand_up_paddleboarding', 'paddling'
                  )
              )
            """
            ,
            (LIST_METRIC_BACKFILL_VERSION,),
        ).fetchall()
        remaining_water_count = int(remaining_water[0][0] if remaining_water else 0)
        total = len(power_rows) + len(water_rows)
        limited = (remaining_power_count + remaining_water_count) > total
        with _NP_BACKFILL_LOCK:
            _NP_BACKFILL_STATUS.update({
                "total": total,
                "processed": 0,
                "updated": 0,
                "limited": limited,
                "np_total": len(power_rows),
                "np_updated": 0,
                "power_total": len(power_rows),
                "power_updated": 0,
                "water_total": len(water_rows),
                "water_updated": 0,
                "error": "",
            })
        for row in power_rows:
            processed += 1
            metrics = _read_activity_metrics_fast_from_fit(row["file_path"])
            avg_power = _safe_float(metrics.get("avg_power"), None)
            max_power = _safe_float(metrics.get("max_power"), None)
            normalized_power = _safe_float(metrics.get("normalized_power"), None)
            if any(value and value > 0 for value in (avg_power, max_power, normalized_power)):
                conn.execute(
                    """
                    UPDATE activities
                    SET avg_power = COALESCE(avg_power, ?),
                        max_power = COALESCE(max_power, ?),
                        normalized_power = COALESCE(normalized_power, ?),
                        list_metric_backfill_version = ?,
                        updated_at = COALESCE(updated_at, datetime('now'))
                    WHERE id = ?
                    """,
                    (
                        int(round(avg_power)) if avg_power and avg_power > 0 else None,
                        int(round(max_power)) if max_power and max_power > 0 else None,
                        int(round(normalized_power)) if normalized_power and normalized_power > 0 else None,
                        LIST_METRIC_BACKFILL_VERSION,
                        int(row["id"]),
                    ),
                )
                updated += 1
                np_updated += 1
                power_updated += 1
            else:
                conn.execute(
                    """
                    UPDATE activities
                    SET list_metric_backfill_version = ?,
                        updated_at = COALESCE(updated_at, datetime('now'))
                    WHERE id = ?
                    """,
                    (LIST_METRIC_BACKFILL_VERSION, int(row["id"])),
                )
            if processed % 25 == 0:
                conn.commit()
                with _NP_BACKFILL_LOCK:
                    _NP_BACKFILL_STATUS.update({
                        "processed": processed,
                        "updated": updated,
                        "np_updated": np_updated,
                        "power_updated": power_updated,
                        "water_updated": water_updated,
                    })
        for row in water_rows:
            processed += 1
            metrics = _read_activity_metrics_fast_from_fit(row["file_path"])
            value = _resolve_water_metric_value_for_backfill(
                row["sport_type"],
                row["sub_sport_type"],
                metrics,
            )
            stroke_distance = _safe_float(metrics.get("avg_stroke_distance"), None)
            if any(metric_value and metric_value > 0 for metric_value in (value, stroke_distance)):
                conn.execute(
                    """
                    UPDATE activities
                    SET swolf = COALESCE(swolf, ?),
                        avg_stroke_distance = COALESCE(avg_stroke_distance, ?),
                        list_metric_backfill_version = ?,
                        updated_at = COALESCE(updated_at, datetime('now'))
                    WHERE id = ?
                    """,
                    (
                        float(value) if value and value > 0 else None,
                        float(stroke_distance) if stroke_distance and stroke_distance > 0 else None,
                        LIST_METRIC_BACKFILL_VERSION,
                        int(row["id"]),
                    ),
                )
                updated += 1
                water_updated += 1
            else:
                conn.execute(
                    """
                    UPDATE activities
                    SET list_metric_backfill_version = ?,
                        updated_at = COALESCE(updated_at, datetime('now'))
                    WHERE id = ?
                    """,
                    (LIST_METRIC_BACKFILL_VERSION, int(row["id"])),
                )
            if processed % 25 == 0:
                conn.commit()
                with _NP_BACKFILL_LOCK:
                    _NP_BACKFILL_STATUS.update({
                        "processed": processed,
                        "updated": updated,
                        "np_updated": np_updated,
                        "power_updated": power_updated,
                        "water_updated": water_updated,
                    })
        conn.commit()
    except Exception as exc:
        error = str(exc)
        logger.exception("normalized_power backfill failed")
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
    finally:
        if conn:
            conn.close()
        with _NP_BACKFILL_LOCK:
            _NP_BACKFILL_STATUS.update({
                "running": False,
                "total": total,
                "processed": processed,
                "updated": updated,
                "limited": limited,
                "np_updated": np_updated,
                "power_updated": power_updated,
                "water_updated": water_updated,
                "started_at": started,
                "finished_at": time.time(),
                "error": error,
            })


def _start_normalized_power_backfill_if_needed() -> dict[str, Any]:
    global _NP_BACKFILL_THREAD
    with _NP_BACKFILL_LOCK:
        if _NP_BACKFILL_STATUS.get("running"):
            return dict(_NP_BACKFILL_STATUS)
        finished_at = float(_NP_BACKFILL_STATUS.get("finished_at") or 0)
        if finished_at and time.time() - finished_at < 60:
            return dict(_NP_BACKFILL_STATUS)

    db_path = _activity_schema_cache_key()
    try:
        conn = sqlite3.connect(db_path, timeout=profile_backend.SQLITE_CONNECT_TIMEOUT_SEC)
        try:
            missing_power = conn.execute(
                """
                SELECT COUNT(*)
                FROM activities
                WHERE deleted_at IS NULL
                  AND (avg_power IS NULL OR max_power IS NULL OR normalized_power IS NULL)
                  AND COALESCE(list_metric_backfill_version, 0) < ?
                  AND COALESCE(file_path, '') != ''
                  AND lower(COALESCE(sport_type, '')) IN (
                      'running', 'trail_running', 'treadmill_running',
                      'cycling', 'road_cycling', 'mountain_biking'
                  )
                """
                ,
                (LIST_METRIC_BACKFILL_VERSION,),
            ).fetchone()[0]
            missing_water = conn.execute(
                """
                SELECT COUNT(*)
                FROM activities
                WHERE deleted_at IS NULL
                  AND (swolf IS NULL OR avg_stroke_distance IS NULL)
                  AND COALESCE(list_metric_backfill_version, 0) < ?
                  AND COALESCE(file_path, '') != ''
                  AND (
                      lower(COALESCE(sport_type, '')) IN (
                          'swimming', 'lap_swimming', 'open_water',
                          'open_water_swimming', 'stand_up_paddleboarding', 'paddling'
                      )
                      OR lower(COALESCE(sub_sport_type, '')) IN (
                          'lap_swimming', 'open_water', 'open_water_swimming',
                          'stand_up_paddleboarding', 'paddling'
                      )
                  )
                """
                ,
                (LIST_METRIC_BACKFILL_VERSION,),
            ).fetchone()[0]
        finally:
            conn.close()
    except Exception as exc:
        with _NP_BACKFILL_LOCK:
            _NP_BACKFILL_STATUS.update({"error": str(exc), "running": False})
            return dict(_NP_BACKFILL_STATUS)
    missing = int(missing_power or 0) + int(missing_water or 0)
    scheduled = min(missing, LIST_METRIC_BACKFILL_BATCH_LIMIT)
    if not missing:
        with _NP_BACKFILL_LOCK:
            _NP_BACKFILL_STATUS.update({
                "total": 0,
                "processed": 0,
                "updated": 0,
                "limited": False,
                "np_total": 0,
                "np_updated": 0,
                "power_total": 0,
                "power_updated": 0,
                "water_total": 0,
                "water_updated": 0,
                "scheduled": False,
                "error": "",
            })
            return dict(_NP_BACKFILL_STATUS)

    with _NP_BACKFILL_LOCK:
        if _NP_BACKFILL_STATUS.get("running"):
            return dict(_NP_BACKFILL_STATUS)
        _NP_BACKFILL_STATUS.update({
            "running": True,
            "total": scheduled,
            "processed": 0,
            "updated": 0,
            "limited": missing > scheduled,
            "np_total": min(int(missing_power or 0), scheduled),
            "np_updated": 0,
            "power_total": min(int(missing_power or 0), scheduled),
            "power_updated": 0,
            "water_total": max(0, scheduled - min(int(missing_power or 0), scheduled)),
            "water_updated": 0,
            "scheduled": False,
            "started_at": time.time(),
            "finished_at": 0.0,
            "error": "",
        })
    _NP_BACKFILL_THREAD = threading.Thread(
        target=_run_normalized_power_backfill_worker,
        args=(db_path,),
        daemon=True,
        name="normalized-power-backfill",
    )
    _NP_BACKFILL_THREAD.start()
    return _normalized_power_backfill_status()


def _schedule_normalized_power_backfill_if_needed(delay_sec: float = LIST_METRIC_BACKFILL_DELAY_SEC) -> dict[str, Any]:
    global _NP_BACKFILL_TIMER
    with _NP_BACKFILL_LOCK:
        if _NP_BACKFILL_STATUS.get("running"):
            return dict(_NP_BACKFILL_STATUS)
        if _NP_BACKFILL_TIMER is not None and _NP_BACKFILL_TIMER.is_alive():
            status = dict(_NP_BACKFILL_STATUS)
            status["scheduled"] = True
            return status
        finished_at = float(_NP_BACKFILL_STATUS.get("finished_at") or 0)
        if finished_at and time.time() - finished_at < 60:
            return dict(_NP_BACKFILL_STATUS)

        _NP_BACKFILL_STATUS.update({
            "scheduled": True,
            "scheduled_at": time.time(),
            "scheduled_delay_sec": float(delay_sec),
            "error": "",
        })

    def _start_scheduled() -> None:
        global _NP_BACKFILL_TIMER
        try:
            _start_normalized_power_backfill_if_needed()
        finally:
            with _NP_BACKFILL_LOCK:
                _NP_BACKFILL_TIMER = None
                if not _NP_BACKFILL_STATUS.get("running"):
                    _NP_BACKFILL_STATUS["scheduled"] = False

    timer = threading.Timer(max(0.0, float(delay_sec)), _start_scheduled)
    timer.daemon = True
    with _NP_BACKFILL_LOCK:
        if _NP_BACKFILL_TIMER is not None and _NP_BACKFILL_TIMER.is_alive():
            status = dict(_NP_BACKFILL_STATUS)
            status["scheduled"] = True
            return status
        _NP_BACKFILL_TIMER = timer
        status = dict(_NP_BACKFILL_STATUS)
    timer.start()
    return status


def _weather_backfill_candidate_where(force: bool = False, include_cooldown: bool = True) -> tuple[str, list[Any]]:
    where = """
              deleted_at IS NULL
              AND (weather_json IS NULL OR weather_json = '')
              AND start_lat IS NOT NULL
              AND start_lon IS NOT NULL
              AND COALESCE(NULLIF(start_time, ''), NULLIF(start_time_utc, '')) IS NOT NULL
              AND COALESCE(weather_status, 'pending') != 'none'
    """
    params: list[Any] = []
    if not force:
        where += """
              AND COALESCE(weather_status, 'pending') != 'unavailable'
              AND COALESCE(weather_attempt_count, 0) < ?
        """
        params.append(WEATHER_BACKFILL_MAX_ATTEMPTS)
    if include_cooldown and not force:
        cutoff = datetime.fromtimestamp(time.time() - WEATHER_BACKFILL_RETRY_COOLDOWN_SEC).isoformat()
        where += """
              AND (
                    weather_updated_at IS NULL
                    OR weather_updated_at = ''
                    OR weather_updated_at <= ?
                  )
        """
        params.append(cutoff)
    return where, params


def _run_weather_backfill_worker(db_path: str, limit: int = WEATHER_BACKFILL_BATCH_LIMIT, force: bool = False) -> None:
    started = time.time()
    processed = 0
    updated = 0
    failed = 0
    total = 0
    limited = False
    error = ""
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(db_path, timeout=profile_backend.SQLITE_CONNECT_TIMEOUT_SEC)
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout = {profile_backend.SQLITE_BUSY_TIMEOUT_MS}")
        candidate_where, candidate_params = _weather_backfill_candidate_where(force=force, include_cooldown=True)
        rows = conn.execute(
            f"""
            SELECT id, start_lat, start_lon, start_time, start_time_utc, weather_attempt_count
            FROM activities
            WHERE {candidate_where}
            ORDER BY COALESCE(start_time, start_time_utc) DESC, id DESC
            LIMIT ?
            """,
            (*candidate_params, max(1, int(limit))),
        ).fetchall()
        remaining_where, remaining_params = _weather_backfill_candidate_where(force=force, include_cooldown=False)
        remaining = conn.execute(
            f"""
            SELECT COUNT(*)
            FROM activities
            WHERE {remaining_where}
            """,
            tuple(remaining_params),
        ).fetchone()[0]
        total = len(rows)
        limited = int(remaining or 0) > total
        with _WEATHER_BACKFILL_LOCK:
            _WEATHER_BACKFILL_STATUS.update({
                "running": True,
                "scheduled": False,
                "total": total,
                "processed": 0,
                "updated": 0,
                "failed": 0,
                "limited": limited,
                "started_at": started,
                "finished_at": 0.0,
                "error": "",
            })

        for row in rows:
            processed += 1
            start_time = row["start_time"] or row["start_time_utc"]
            weather = fetch_historical_weather(row["start_lat"], row["start_lon"], start_time)
            now_text = datetime.now().isoformat()
            attempt_count = int(row["weather_attempt_count"] or 0) + 1
            if weather:
                conn.execute(
                    """
                    UPDATE activities
                    SET weather_json = ?,
                        weather_status = 'success',
                        weather_updated_at = ?,
                        weather_attempt_count = ?,
                        weather_error = NULL,
                        updated_at = COALESCE(updated_at, datetime('now'))
                    WHERE id = ?
                    """,
                    (json.dumps(weather, ensure_ascii=False), now_text, attempt_count, int(row["id"])),
                )
                updated += 1
            else:
                failed_status = "unavailable" if attempt_count >= WEATHER_BACKFILL_MAX_ATTEMPTS and not force else "failed"
                conn.execute(
                    """
                    UPDATE activities
                    SET weather_status = ?,
                        weather_updated_at = ?,
                        weather_attempt_count = ?,
                        weather_error = ?,
                        updated_at = COALESCE(updated_at, datetime('now'))
                    WHERE id = ?
                    """,
                    (failed_status, now_text, attempt_count, "weather unavailable", int(row["id"])),
                )
                failed += 1
            if processed % 10 == 0:
                conn.commit()
                with _WEATHER_BACKFILL_LOCK:
                    _WEATHER_BACKFILL_STATUS.update({
                        "processed": processed,
                        "updated": updated,
                        "failed": failed,
                    })
        conn.commit()
    except Exception as exc:
        error = str(exc)
        logger.exception("weather backfill failed")
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
    finally:
        if conn:
            conn.close()
        with _WEATHER_BACKFILL_LOCK:
            _WEATHER_BACKFILL_STATUS.update({
                "running": False,
                "scheduled": False,
                "total": total,
                "processed": processed,
                "updated": updated,
                "failed": failed,
                "limited": limited,
                "started_at": started,
                "finished_at": time.time(),
                "error": error,
            })


def _backfill_activity_weather_once(activity_id: int, force: bool = False) -> dict[str, Any]:
    ensure_activity_sync_schema()
    aid = _safe_int(activity_id)
    if not aid or aid <= 0:
        return {"ok": False, "code": API_CODE_VALIDATION, "msg": "activity_id 必须为正整数"}
    conn = sqlite3.connect(_activity_schema_cache_key(), timeout=profile_backend.SQLITE_CONNECT_TIMEOUT_SEC)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {profile_backend.SQLITE_BUSY_TIMEOUT_MS}")
    try:
        row = conn.execute(
            """
            SELECT id, start_lat, start_lon, start_time, start_time_utc, weather_json,
                   weather_status, weather_attempt_count
            FROM activities
            WHERE id = ? AND deleted_at IS NULL
            """,
            (aid,),
        ).fetchone()
        if not row:
            return {"ok": False, "code": API_CODE_NOT_FOUND, "msg": "未找到该活动记录"}
        if row["weather_json"] and not force:
            return {
                "ok": True,
                "status": "success",
                "weather": _decode_weather_json(row["weather_json"]),
                "updated": False,
            }
        if row["start_lat"] is None or row["start_lon"] is None:
            conn.execute(
                """
                UPDATE activities
                SET weather_status = 'none',
                    weather_error = NULL,
                    weather_attempt_count = COALESCE(weather_attempt_count, 0),
                    weather_updated_at = ?
                WHERE id = ?
                """,
                (datetime.now().isoformat(), aid),
            )
            conn.commit()
            return {"ok": False, "code": API_CODE_VALIDATION, "msg": "当前活动没有 GPS 坐标，无法补全天气"}
        start_time = row["start_time"] or row["start_time_utc"]
        if not start_time:
            return {"ok": False, "code": API_CODE_VALIDATION, "msg": "当前活动缺少开始时间，无法补全天气"}
        attempt_count = int(row["weather_attempt_count"] or 0) + 1
        weather = fetch_historical_weather(row["start_lat"], row["start_lon"], start_time)
        now_text = datetime.now().isoformat()
        if weather:
            conn.execute(
                """
                UPDATE activities
                SET weather_json = ?,
                    weather_status = 'success',
                    weather_updated_at = ?,
                    weather_attempt_count = ?,
                    weather_error = NULL,
                    updated_at = COALESCE(updated_at, datetime('now'))
                WHERE id = ?
                """,
                (json.dumps(weather, ensure_ascii=False), now_text, attempt_count, aid),
            )
            conn.commit()
            return {"ok": True, "status": "success", "weather": weather, "updated": True}
        failed_status = "unavailable" if attempt_count >= WEATHER_BACKFILL_MAX_ATTEMPTS and not force else "failed"
        conn.execute(
            """
            UPDATE activities
            SET weather_status = ?,
                weather_updated_at = ?,
                weather_attempt_count = ?,
                weather_error = ?,
                updated_at = COALESCE(updated_at, datetime('now'))
            WHERE id = ?
            """,
            (failed_status, now_text, attempt_count, "weather unavailable", aid),
        )
        conn.commit()
        return {
            "ok": False,
            "code": API_CODE_EXTERNAL_SERVICE,
            "msg": "暂未获取到当前活动天气",
            "status": failed_status,
            "updated": False,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _start_weather_backfill_if_needed(limit: int = WEATHER_BACKFILL_BATCH_LIMIT, force: bool = False) -> dict[str, Any]:
    global _WEATHER_BACKFILL_THREAD
    ensure_activity_sync_schema()
    with _WEATHER_BACKFILL_LOCK:
        if _WEATHER_BACKFILL_STATUS.get("running"):
            return dict(_WEATHER_BACKFILL_STATUS)
        finished_at = float(_WEATHER_BACKFILL_STATUS.get("finished_at") or 0)
        if not force and finished_at and time.time() - finished_at < 60:
            return dict(_WEATHER_BACKFILL_STATUS)

    db_path = _activity_schema_cache_key()
    try:
        conn = sqlite3.connect(db_path, timeout=profile_backend.SQLITE_CONNECT_TIMEOUT_SEC)
        try:
            candidate_where, candidate_params = _weather_backfill_candidate_where(force=force, include_cooldown=False)
            missing = int(conn.execute(
                f"""
                SELECT COUNT(*)
                FROM activities
                WHERE {candidate_where}
                """,
                tuple(candidate_params),
            ).fetchone()[0] or 0)
        finally:
            conn.close()
    except Exception as exc:
        with _WEATHER_BACKFILL_LOCK:
            _WEATHER_BACKFILL_STATUS.update({"error": str(exc), "running": False, "scheduled": False})
            return dict(_WEATHER_BACKFILL_STATUS)

    scheduled = min(missing, max(1, int(limit)))
    if not missing:
        with _WEATHER_BACKFILL_LOCK:
            _WEATHER_BACKFILL_STATUS.update({
                "running": False,
                "scheduled": False,
                "total": 0,
                "processed": 0,
                "updated": 0,
                "failed": 0,
                "limited": False,
                "error": "",
            })
            return dict(_WEATHER_BACKFILL_STATUS)

    with _WEATHER_BACKFILL_LOCK:
        if _WEATHER_BACKFILL_STATUS.get("running"):
            return dict(_WEATHER_BACKFILL_STATUS)
        _WEATHER_BACKFILL_STATUS.update({
            "running": True,
            "scheduled": False,
            "total": scheduled,
            "processed": 0,
            "updated": 0,
            "failed": 0,
            "limited": missing > scheduled,
            "started_at": time.time(),
            "finished_at": 0.0,
            "error": "",
        })
    _WEATHER_BACKFILL_THREAD = threading.Thread(
        target=_run_weather_backfill_worker,
        args=(db_path, scheduled, force),
        daemon=True,
        name="weather-backfill",
    )
    _WEATHER_BACKFILL_THREAD.start()
    return _weather_backfill_status()


def _schedule_weather_backfill_if_needed(delay_sec: float = WEATHER_BACKFILL_STARTUP_DELAY_SEC) -> dict[str, Any]:
    global _WEATHER_BACKFILL_TIMER
    try:
        db_path = _activity_schema_cache_key()
        conn = sqlite3.connect(db_path, timeout=profile_backend.SQLITE_CONNECT_TIMEOUT_SEC)
        try:
            candidate_where, candidate_params = _weather_backfill_candidate_where(force=False, include_cooldown=True)
            missing = int(conn.execute(
                f"SELECT COUNT(*) FROM activities WHERE {candidate_where}",
                tuple(candidate_params),
            ).fetchone()[0] or 0)
        finally:
            conn.close()
        if not missing:
            with _WEATHER_BACKFILL_LOCK:
                _WEATHER_BACKFILL_STATUS.update({"scheduled": False, "total": 0, "error": ""})
                return dict(_WEATHER_BACKFILL_STATUS)
    except Exception as exc:
        with _WEATHER_BACKFILL_LOCK:
            _WEATHER_BACKFILL_STATUS.update({"scheduled": False, "error": str(exc)})
            return dict(_WEATHER_BACKFILL_STATUS)

    with _WEATHER_BACKFILL_LOCK:
        if _WEATHER_BACKFILL_STATUS.get("running"):
            return dict(_WEATHER_BACKFILL_STATUS)
        if _WEATHER_BACKFILL_TIMER is not None and _WEATHER_BACKFILL_TIMER.is_alive():
            status = dict(_WEATHER_BACKFILL_STATUS)
            status["scheduled"] = True
            return status
        finished_at = float(_WEATHER_BACKFILL_STATUS.get("finished_at") or 0)
        if finished_at and time.time() - finished_at < 60:
            return dict(_WEATHER_BACKFILL_STATUS)
        _WEATHER_BACKFILL_STATUS.update({
            "scheduled": True,
            "scheduled_at": time.time(),
            "scheduled_delay_sec": float(delay_sec),
            "error": "",
        })

    def _start_scheduled() -> None:
        global _WEATHER_BACKFILL_TIMER
        try:
            _start_weather_backfill_if_needed(force=False)
        finally:
            with _WEATHER_BACKFILL_LOCK:
                _WEATHER_BACKFILL_TIMER = None
                if not _WEATHER_BACKFILL_STATUS.get("running"):
                    _WEATHER_BACKFILL_STATUS["scheduled"] = False

    timer = threading.Timer(max(0.0, float(delay_sec)), _start_scheduled)
    timer.daemon = True
    with _WEATHER_BACKFILL_LOCK:
        if _WEATHER_BACKFILL_TIMER is not None and _WEATHER_BACKFILL_TIMER.is_alive():
            status = dict(_WEATHER_BACKFILL_STATUS)
            status["scheduled"] = True
            return status
        _WEATHER_BACKFILL_TIMER = timer
        status = dict(_WEATHER_BACKFILL_STATUS)
    timer.start()
    return status


def _p90(values: list[float]) -> float:
    """90 分位数聚合策略,用于雷达 3 个维度(VAM/Threshold HR/Anaerobic Peak)的滚动聚合。

    设计意图:消除 max() 聚合下"单次极端活动永久主导得分"的系统性问题。
    详见审计报告 §8 / §9.1 修复建议 P0。

    样本量门控:
    - N = 0:返回 0.0(无数据兜底,与原 max() 行为一致)
    - N < 4:退化为算术平均(max 在小样本下退化为该值本身,无统计意义)
    - N >= 4:用线性插值计算 90 分位数(同 numpy.percentile 默认 method)
    """
    if not values:
        return 0.0
    if len(values) < 4:
        return sum(values) / len(values)

    sorted_vals = sorted(values)
    # 线性插值 p90(0-based index 0.9 * (n-1)),与 numpy.percentile 默认 linear 一致
    rank = 0.9 * (len(sorted_vals) - 1)
    lower_idx = int(rank)
    upper_idx = min(lower_idx + 1, len(sorted_vals) - 1)
    fraction = rank - lower_idx
    return sorted_vals[lower_idx] * (1 - fraction) + sorted_vals[upper_idx] * fraction


_ANAEROBIC_SOURCE_PRIORITY: dict[str, int] = {
    "power_wkg": 4,
    "power_w": 3,
    "speed": 2,
    "speed_fallback": 1,
    "legacy": 0,
}


_THRESHOLD_SOURCE_PRIORITY: dict[str, int] = {
    "ftp_wkg": 3,
    "ftp_w": 2,
    "threshold_hr": 1,
    "legacy": 0,
}


def _normalize_anaerobic_source(source: Any, sport_type: str | None) -> str:
    token = str(source or "").strip().lower()
    if token in _ANAEROBIC_SOURCE_PRIORITY:
        return token
    if sport_type in _CYCLING_SPORT_TYPES:
        return "legacy"
    if sport_type in ("running", "trail_running"):
        return "speed"
    return "legacy"


def _normalize_threshold_source(source: Any, sport_type: str | None) -> str:
    token = str(source or "").strip().lower()
    if token in _THRESHOLD_SOURCE_PRIORITY:
        return token
    if sport_type in _CYCLING_SPORT_TYPES:
        return "legacy"
    return "threshold_hr"


def _climbing_confidence(sample_count: int) -> str:
    if sample_count >= 6:
        return "high"
    if sample_count >= 3:
        return "medium"
    return "low"


_STABILITY_SPORT_TYPES: frozenset[str] = frozenset({
    "running",
    "trail_running",
    "treadmill_running",
    "cycling",
    "road_cycling",
    "mountain_biking",
    "hiking",
    "walking",
    "mountaineering",
})


def _stability_confidence(sample_count: int) -> str:
    if sample_count >= 5:
        return "high"
    if sample_count >= 3:
        return "medium"
    return "low"


def _is_truthy_metric(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return False


def _is_valid_stability_activity(row: dict, sport_type: str | None, metrics: dict) -> bool:
    """Pa:Hr stability only trusts steady aerobic samples."""
    sport = str(sport_type or "").strip().lower()
    if sport not in _STABILITY_SPORT_TYPES:
        return False

    decoupling = _safe_float(metrics.get("decoupling"), None)
    if decoupling is None or decoupling < -20 or decoupling > 50:
        return False

    duration_sec = _safe_float(row.get("duration_sec"), 0.0)
    if duration_sec <= 0:
        duration_sec = _safe_float(row.get("duration"), 0.0)
    min_duration = 3600.0 if sport in {"hiking", "walking", "mountaineering"} else 2400.0
    if duration_sec < min_duration:
        return False

    if _is_truthy_metric(row.get("is_intermittent")) or _is_truthy_metric(metrics.get("is_intermittent")):
        return False
    workout_type = str(metrics.get("workout_type") or row.get("workout_type") or "").strip().lower()
    if any(token in workout_type for token in ("interval", "intervals", "hiit", "fartlek")):
        return False
    if _is_truthy_metric(metrics.get("intervals")):
        return False

    paused_time = _safe_float(metrics.get("paused_time"), None)
    elapsed_time = _safe_float(metrics.get("elapsed_time"), None)
    moving_time = _safe_float(metrics.get("moving_time"), None)
    if paused_time is None and elapsed_time is not None and moving_time is not None:
        paused_time = max(elapsed_time - moving_time, 0.0)
    if elapsed_time is None:
        elapsed_time = duration_sec
    if paused_time is not None and elapsed_time and elapsed_time > 0:
        if paused_time / elapsed_time > 0.15:
            return False

    dist_km = _safe_float(row.get("dist_km"), 0.0)
    if dist_km <= 0:
        dist_m = _safe_float(row.get("distance"), 0.0)
        if dist_m > 0:
            dist_km = dist_m / 1000.0
    gain_m = _safe_float(row.get("gain_m"), 0.0)
    if dist_km > 0 and gain_m > 0:
        climb_density = gain_m / dist_km
        max_density = 80.0 if sport in {"hiking", "walking", "mountaineering"} else 25.0
        if climb_density > max_density:
            return False

    return True


# 雷达 90 天聚合 VAM 可信度阈值
# (最小总爬升 m, 最小距离 km)
# 设计意图:即使单次 calculate_vam 已修复,历史 advanced_metrics 中
# 可能残留 gain_m=0/4/5m 的通勤骑行旧 VAM,直接聚合会污染雷达图。
# 只有"真实爬坡活动"才允许 VAM 进入聚合。
_VAM_CREDIBILITY_THRESHOLDS: dict[str, tuple[float, float]] = {
    "cycling": (20.0, 1.0),
    "road_cycling": (20.0, 1.0),
    "mountain_biking": (20.0, 1.0),
    "running": (20.0, 1.0),
    "trail_running": (30.0, 1.0),
    "hiking": (50.0, 1.0),
}


def _is_valid_vam_activity(row: dict, sport_type: str | None) -> bool:
    """VAM 可信度过滤:只有真实爬坡活动才允许 VAM 进入 90 天聚合。

    阈值表见 _VAM_CREDIBILITY_THRESHOLDS。
    - gain_m 缺失按 0 处理(不通过)
    - dist_km 缺失时回退 distance/1000.0
    - sport_type 不在表中(游泳等无 climbing 维度)默认不纳入
    """
    if not sport_type:
        return False
    threshold = _VAM_CREDIBILITY_THRESHOLDS.get(sport_type)
    if threshold is None:
        return False
    min_gain_m, min_dist_km = threshold
    gain_m = _safe_float(row.get("gain_m"), 0.0)
    dist_km = _safe_float(row.get("dist_km"), 0.0)
    if dist_km <= 0:
        # V8.x 修复: distance 字段已对齐米单位(语义正确)
        dist_m = _safe_float(row.get("distance"), 0.0)
        if dist_m > 0:
            dist_km = dist_m / 1000.0
    return gain_m >= min_gain_m and dist_km >= min_dist_km


def _rolling_aggregate_radar_metrics(sport_type: str | None = None) -> dict:
    """
    滚动极值与近期均值聚合（Rolling Aggregation）+ PMC 长期负荷衰减模型
    """
    import math

    now = datetime.now(timezone.utc)

    prof = profile_backend.get_profile()
    hrv_from_profile = prof.hrv_baseline if prof else None
    profile_dict = prof.to_dict() if prof else {}

    conn = profile_backend._conn()
    try:
        if sport_type:
            # §5 雷达数据源:骑行变体(cycling/road_cycling/mountain_biking)统一查询,
            # 对齐 _CYCLING_SPORT_TYPES 集合意图,确保 road/mtb 骑行者雷达数据不空洞。
            # 任务 2 修复:额外取出 gain_m/dist_km/distance/duration_sec/duration/sport_type
            # 用于 VAM 可信度过滤(避免 gain_m=0/4/5m 的通勤旧 VAM 污染雷达图)。
            if sport_type in _CYCLING_SPORT_TYPES:
                cycling_types = sorted(_CYCLING_SPORT_TYPES)
                placeholders = ",".join(["?"] * len(cycling_types))
                rows = conn.execute(
                    f"""
                    SELECT id, start_time_utc, start_time, advanced_metrics,
                           sport_type, gain_m, dist_km, distance, duration_sec, duration, is_intermittent
                    FROM activities
                    WHERE deleted_at IS NULL
                      AND sport_type IN ({placeholders})
                      AND COALESCE(NULLIF(processing_status, ''), 'ready') = 'ready'
                      AND advanced_metrics IS NOT NULL
                      AND advanced_metrics != ''
                    ORDER BY COALESCE(start_time_utc, start_time) ASC
                    """,
                    tuple(cycling_types),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, start_time_utc, start_time, advanced_metrics,
                           sport_type, gain_m, dist_km, distance, duration_sec, duration, is_intermittent
                    FROM activities
                    WHERE deleted_at IS NULL
                      AND sport_type = ?
                      AND COALESCE(NULLIF(processing_status, ''), 'ready') = 'ready'
                      AND advanced_metrics IS NOT NULL
                      AND advanced_metrics != ''
                    ORDER BY COALESCE(start_time_utc, start_time) ASC
                    """,
                    (sport_type,),
                ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, start_time_utc, start_time, advanced_metrics,
                       sport_type, gain_m, dist_km, distance, duration_sec, duration, is_intermittent
                FROM activities
                WHERE deleted_at IS NULL
                  AND advanced_metrics IS NOT NULL
                  AND COALESCE(NULLIF(processing_status, ''), 'ready') = 'ready'
                  AND advanced_metrics != ''
                ORDER BY COALESCE(start_time_utc, start_time) ASC
                """
            ).fetchall()
    finally:
        conn.close()

    vam_values = []
    climbing_gain_values = []
    climbing_distance_values = []
    climbing_duration_values = []
    climbing_power_available_count = 0
    climbing_elevation_activity_count = 0
    threshold_values_by_source: dict[str, list[float]] = {}
    anaerobic_peak_values_by_source: dict[str, list[float]] = {}
    decoupling_values = []

    ctl = 0.0
    atl = 0.0
    last_date: datetime | None = None
    valid_sample_count = 0
    latest_metrics_version = 0
    stale_metrics_count = 0
    endurance_sample_count = 0
    endurance_training_dates_28d: set[date] = set()

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
                stale_metrics_count += 1
                continue
            valid_sample_count += 1
            if needs_advanced_metrics_rebuild(metrics):
                stale_metrics_count += 1
            try:
                latest_metrics_version = max(latest_metrics_version, int(float(metrics.get("metrics_version") or 0)))
            except (TypeError, ValueError):
                pass

            row_sport_type = row.get("sport_type") or sport_type
            valid_climb_activity = _is_valid_vam_activity(row, row_sport_type)
            if valid_climb_activity:
                climbing_elevation_activity_count += 1

            # §任务 2 VAM 可信度过滤:仅真实爬升/距离达标的活动允许 VAM 入聚合
            if "vam" in metrics and metrics["vam"] is not None:
                vam_value = float(metrics["vam"])
                if vam_value > 0 and valid_climb_activity:
                    vam_values.append(vam_value)
                    gain_m = _safe_float(row.get("gain_m"), 0.0)
                    dist_km = _safe_float(row.get("dist_km"), 0.0)
                    if dist_km <= 0:
                        dist_m = _safe_float(row.get("distance"), 0.0)
                        if dist_m > 0:
                            dist_km = dist_m / 1000.0
                    duration_sec = _safe_float(row.get("duration_sec") or row.get("duration"), 0.0)
                    if gain_m > 0:
                        climbing_gain_values.append(gain_m)
                    if dist_km > 0:
                        climbing_distance_values.append(dist_km)
                    if duration_sec > 0:
                        climbing_duration_values.append(duration_sec)
                    if row_sport_type in _CYCLING_SPORT_TYPES and any(
                        _safe_float(metrics.get(key), 0.0) > 0
                        for key in ("climbing_power_wkg", "climbing_power", "threshold_wkg", "avg_power", "normalized_power", "max_power")
                    ):
                        climbing_power_available_count += 1
            if any(metrics.get(key) is not None for key in ("threshold_hr", "threshold_power", "threshold_wkg")):
                row_sport_type = row.get("sport_type") or sport_type
                source = _normalize_threshold_source(metrics.get("threshold_source"), row_sport_type)
                threshold_value = None
                if source == "ftp_wkg":
                    threshold_value = metrics.get("threshold_wkg")
                elif source == "ftp_w":
                    threshold_value = metrics.get("threshold_power")
                else:
                    threshold_value = metrics.get("threshold_hr")
                    source = "threshold_hr" if source == "legacy" and row_sport_type not in _CYCLING_SPORT_TYPES else source
                if threshold_value is not None:
                    threshold_values_by_source.setdefault(source, []).append(float(threshold_value))
            if "anaerobic_peak" in metrics and metrics["anaerobic_peak"] is not None:
                row_sport_type = row.get("sport_type") or sport_type
                source = _normalize_anaerobic_source(metrics.get("anaerobic_peak_source"), row_sport_type)
                anaerobic_peak_values_by_source.setdefault(source, []).append(float(metrics["anaerobic_peak"]))

            if "decoupling" in metrics and metrics["decoupling"] is not None:
                row_sport_type = row.get("sport_type") or sport_type
                if _is_valid_stability_activity(row, row_sport_type, metrics):
                    decoupling_values.append(float(metrics["decoupling"]))

            trimp = float(metrics.get("trimp") or 0.0)
            if trimp > 0:
                endurance_sample_count += 1
                duration_sec = _safe_float(row.get("duration_sec") or row.get("duration"))
                if age_days <= 28 and duration_sec >= 600:
                    endurance_training_dates_28d.add(dt.astimezone().date())
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

    if valid_sample_count == 0:
        recovery_detail = RadarScoreEngine.score_recovery_detail(
            profile_dict,
            {"ctl": 0.0, "atl": 0.0, "tsb": 0.0},
        )
        return {
            "ctl": 0.0,
            "atl": 0.0,
            "tsb": 0.0,
            "metrics_version": latest_metrics_version or None,
            "expected_metrics_version": CURRENT_METRICS_VERSION,
            "needs_rebuild": stale_metrics_count > 0,
            "stale_metrics_count": stale_metrics_count,
            "hrv": round(float(hrv_from_profile), 1) if hrv_from_profile is not None else None,
            "endurance_score": 0,
            "endurance_ctl_score": 0,
            "endurance_consistency_score": 0,
            "endurance_training_days_28d": 0,
            "endurance_sample_count": 0,
            "endurance_confidence": "low",
            "endurance_source": "no_valid_trimp",
            "recovery_score": recovery_detail.get("score"),
            "recovery_source": recovery_detail.get("source"),
            "recovery_confidence": recovery_detail.get("confidence"),
            "recovery_reasons": recovery_detail.get("reasons"),
            "decoupling": 0.0,
            "stability_sample_count": 0,
            "stability_confidence": "low",
            "vam": 0.0,
            "climbing_activity_count_90d": valid_sample_count,
            "climbing_elevation_activity_count_90d": climbing_elevation_activity_count,
            "climbing_sample_count": 0,
            "climbing_confidence": "low",
            "threshold_hr": 0.0,
            "threshold_source": None,
            "threshold_confidence": "low",
            "threshold_sample_count": 0,
            "threshold_power": None,
            "threshold_wkg": None,
            "anaerobic_peak": 0.0,
            "anaerobic_peak_source": None,
            "anaerobic_peak_confidence": "low",
            "anaerobic_sample_count": 0,
            "radar": {"type": sport_type or "running", "dimensions": []},
        }

    if last_date:
        delta_days_to_now = max((now - last_date).total_seconds() / 86400.0, 0)
        ctl = ctl * math.exp(-delta_days_to_now / 42.0)
        atl = atl * math.exp(-delta_days_to_now / 7.0)

    tsb = ctl - atl

    # §5 雷达聚合:p90 替代 max 消除异常值主导(审计 §8 / §9.1 P0)
    vam_max = _p90(vam_values)
    climbing_sample_count = len(vam_values)
    climbing_confidence = _climbing_confidence(climbing_sample_count)
    climbing_gain_p90 = _p90(climbing_gain_values)
    climbing_distance_p90 = _p90(climbing_distance_values)
    climbing_duration_p90 = _p90(climbing_duration_values)
    selected_threshold_source = None
    selected_threshold_values: list[float] = []
    for source, _priority in sorted(_THRESHOLD_SOURCE_PRIORITY.items(), key=lambda item: item[1], reverse=True):
        values = threshold_values_by_source.get(source) or []
        if values:
            selected_threshold_source = source
            selected_threshold_values = values
            break
    threshold_max = _p90(selected_threshold_values)
    threshold_hr_max = threshold_max if selected_threshold_source in ("threshold_hr", "legacy") else 0.0
    threshold_power_max = threshold_max if selected_threshold_source == "ftp_w" else None
    threshold_wkg_max = threshold_max if selected_threshold_source == "ftp_wkg" else None
    threshold_confidence = "low"
    if selected_threshold_source == "ftp_wkg":
        threshold_confidence = "high"
    elif selected_threshold_source == "ftp_w":
        threshold_confidence = "medium"
    elif selected_threshold_source == "threshold_hr":
        threshold_confidence = "medium" if sport_type not in _CYCLING_SPORT_TYPES else "low"
    selected_anaerobic_source = None
    selected_anaerobic_values: list[float] = []
    for source, _priority in sorted(_ANAEROBIC_SOURCE_PRIORITY.items(), key=lambda item: item[1], reverse=True):
        values = anaerobic_peak_values_by_source.get(source) or []
        if values:
            selected_anaerobic_source = source
            selected_anaerobic_values = values
            break
    anaerobic_peak_max = _p90(selected_anaerobic_values)
    anaerobic_confidence = "low"
    if selected_anaerobic_source == "power_wkg":
        anaerobic_confidence = "high"
    elif selected_anaerobic_source == "power_w":
        anaerobic_confidence = "medium"
    elif selected_anaerobic_source == "speed":
        anaerobic_confidence = "medium"

    last_5_decoupling = decoupling_values[-5:] if decoupling_values else []
    decoupling_avg = sum(last_5_decoupling) / len(last_5_decoupling) if last_5_decoupling else 0.0
    stability_sample_count = len(decoupling_values)
    stability_confidence = _stability_confidence(stability_sample_count)

    hrv = float(hrv_from_profile) if hrv_from_profile is not None else 60.0
    endurance_detail = RadarScoreEngine.score_endurance_detail(
        ctl,
        sport_type,
        len(endurance_training_dates_28d),
        endurance_sample_count,
    )
    recovery_detail = RadarScoreEngine.score_recovery_detail(
        profile_dict,
        {"ctl": ctl, "atl": atl, "tsb": tsb},
    )

    max_hr = prof.max_hr if prof and prof.max_hr else 190
    radar_input = {
        "trimp": ctl,
        "endurance_score": endurance_detail.get("score"),
        "endurance_ctl_score": endurance_detail.get("ctl_score"),
        "endurance_consistency_score": endurance_detail.get("consistency_score"),
        "endurance_training_days_28d": endurance_detail.get("training_days_28d"),
        "endurance_sample_count": endurance_detail.get("sample_count"),
        "endurance_confidence": endurance_detail.get("confidence"),
        "endurance_source": endurance_detail.get("source"),
        "hrv": hrv,
        "recovery_score": recovery_detail.get("score"),
        "recovery_source": recovery_detail.get("source"),
        "recovery_confidence": recovery_detail.get("confidence"),
        "decoupling": decoupling_avg,
        "stability_sample_count": stability_sample_count,
        "stability_confidence": stability_confidence,
        "vam": vam_max,
        "climbing_vam_p90": vam_max,
        "climbing_activity_count_90d": valid_sample_count,
        "climbing_elevation_activity_count_90d": climbing_elevation_activity_count,
        "climbing_sample_count": climbing_sample_count,
        "climbing_confidence": climbing_confidence,
        "climbing_gain_p90": climbing_gain_p90,
        "climbing_distance_p90": climbing_distance_p90,
        "climbing_duration_p90": climbing_duration_p90,
        "climbing_power_available_count": climbing_power_available_count,
        "threshold_hr": threshold_hr_max,
        "threshold_source": selected_threshold_source,
        "threshold_confidence": threshold_confidence,
        "threshold_power": threshold_power_max,
        "threshold_wkg": threshold_wkg_max,
        "anaerobic_peak": anaerobic_peak_max,
        "anaerobic_peak_source": selected_anaerobic_source,
        "anaerobic_peak_confidence": anaerobic_confidence,
    }
    radar_profile = RadarScoreEngine.build_radar_profile(sport_type or "running", radar_input, {"max_hr": max_hr})
    climbing_dimension = next(
        (dim for dim in radar_profile.get("dimensions", []) if dim.get("key") == "climbing"),
        {},
    )

    return {
        "ctl": round(ctl, 1),
        "atl": round(atl, 1),
        "tsb": round(tsb, 1),
        "metrics_version": latest_metrics_version or None,
        "expected_metrics_version": CURRENT_METRICS_VERSION,
        "needs_rebuild": stale_metrics_count > 0,
        "stale_metrics_count": stale_metrics_count,
        "hrv": round(hrv, 1),
        "endurance_score": endurance_detail.get("score"),
        "endurance_ctl_score": endurance_detail.get("ctl_score"),
        "endurance_consistency_score": endurance_detail.get("consistency_score"),
        "endurance_training_days_28d": endurance_detail.get("training_days_28d"),
        "endurance_sample_count": endurance_detail.get("sample_count"),
        "endurance_confidence": endurance_detail.get("confidence"),
        "endurance_source": endurance_detail.get("source"),
        "recovery_score": recovery_detail.get("score"),
        "recovery_source": recovery_detail.get("source"),
        "recovery_confidence": recovery_detail.get("confidence"),
        "recovery_reasons": recovery_detail.get("reasons"),
        "decoupling": round(decoupling_avg, 2),
        "stability_sample_count": stability_sample_count,
        "stability_confidence": stability_confidence,
        "vam": round(vam_max, 1),
        "climbing_vam_p90": round(vam_max, 1),
        "climbing_activity_count_90d": valid_sample_count,
        "climbing_elevation_activity_count_90d": climbing_elevation_activity_count,
        "climbing_sample_count": climbing_sample_count,
        "climbing_confidence": climbing_confidence,
        "climbing_gain_p90": round(climbing_gain_p90, 1),
        "climbing_distance_p90": round(climbing_distance_p90, 2),
        "climbing_duration_p90": round(climbing_duration_p90, 1),
        "climbing_power_available_count": climbing_power_available_count,
        "climbing_score_cap": climbing_dimension.get("score_cap"),
        "climbing_score_components": climbing_dimension.get("score_components"),
        "climbing_reason": climbing_dimension.get("reason"),
        "climbing_source": climbing_dimension.get("source"),
        "threshold_hr": round(threshold_hr_max, 1),
        "threshold_source": selected_threshold_source,
        "threshold_confidence": threshold_confidence,
        "threshold_sample_count": len(selected_threshold_values),
        "threshold_power": round(threshold_power_max, 1) if threshold_power_max is not None else None,
        "threshold_wkg": round(threshold_wkg_max, 2) if threshold_wkg_max is not None else None,
        "anaerobic_peak": round(anaerobic_peak_max, 2),
        "anaerobic_peak_source": selected_anaerobic_source,
        "anaerobic_peak_confidence": anaerobic_confidence,
        "anaerobic_sample_count": len(selected_anaerobic_values),
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
    raw_laps = list(core.get("lap_data") or [])
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
            # V9.4.4:Training Effect 透传(Firstbeat 私有字段)
            "aerobic_training_effect": basic.get("aerobic_training_effect"),
            "anaerobic_training_effect": basic.get("anaerobic_training_effect"),
            "total_descent_m": basic.get("total_descent"),
            "avg_power": basic.get("avg_power"),
            "max_power": basic.get("max_power"),
            "normalized_power": basic.get("normalized_power"),
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
    weather_status = "none" if not has_gps else "pending"
    weather_error = None
    if has_gps:
        weather = fetch_historical_weather(
            payload.get("start_lat"),
            payload.get("start_lon"),
            payload.get("start_time") or payload.get("start_time_utc"),
        )
        weather_status = "success" if weather else "pending"
        weather_error = None if weather else "weather unavailable"

    stat = file_path.stat()
    advanced_metrics = _compute_advanced_metrics(track_data, payload.get("sport_type") or basic.get("sport"))
    # 规范化 lap 数据:复用 MetricsResolver._normalize_laps 保持字段语义一致
    normalized_laps = MetricsResolver._normalize_laps(raw_laps) if raw_laps else []
    laps_json = json.dumps(normalized_laps, ensure_ascii=False) if normalized_laps else None
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
        "avg_power": _safe_float(basic.get("avg_power")),
        "max_power": _safe_float(basic.get("max_power")),
        "swolf": None,
        "normalized_power": None,
        "avg_stroke_distance": _safe_float(payload.get("avg_stroke_distance")),
        "hr_curve": None,
        "speed_curve": None,
        "cadence_curve": None,  # V8.3
        "laps_json": laps_json,  # 真实圈速数据 (FIT lap_mesgs 归一化)
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
        "weather_status": weather_status,
        "weather_updated_at": datetime.now().isoformat() if weather else None,
        "weather_attempt_count": 1 if has_gps else 0,
        "weather_error": weather_error,
        "file_mtime": float(stat.st_mtime),
        "file_size": int(stat.st_size),
        "advanced_metrics": json.dumps(advanced_metrics, ensure_ascii=False) if advanced_metrics else None,
        # source 标记：canonical（FIT）+ enrichment（weather/region）
        "source": {
            "fit": "canonical",
            "weather": "enrichment" if weather else "none",
            "region": "pending" if has_gps else "indoor",
        },
        # V9.4.4:Training Effect(Firstbeat 私有字段,从 fit_engine 透传)
        "aerobic_training_effect": _safe_float(basic.get("aerobic_training_effect")),
        "anaerobic_training_effect": _safe_float(basic.get("anaerobic_training_effect")),
        "processing_status": "ready",
        "processing_error": None,
    }

    # 从 FIT 文件解析设备型号
    try:
        from garmin_fit_sdk import Decoder, Stream

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
        # V8.x 修复 distance 字段单位歧义:distance = 米(语义对齐),dist_km = 公里
        # §2.1 字段全链路可追溯:严禁双字段语义重叠
        _km = distance_km if distance_km is not None else 0
        result["distance"] = _km * 1000.0  # 真存米
        result["dist_km"] = _km             # 真存公里
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
        result["total_descent_m_device"] = payload.get("total_descent_m_device")  # 设备值,不受 resolver 覆写
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
        elif sub_sport_token in ("open_water", "open_water_swimming") or sport_token in ("stand_up_paddleboarding", "paddling"):
            result["swolf"] = result["avg_stroke_distance"]
        # Phase 2.5 — normalized_power: FIT canonical first; Resolver output shape is not stable here.
        result["normalized_power"] = _resolve_normalized_power_for_sync(
            basic,
            raw_laps,
            track_data,
            sm,
        )
        # V8.3: 直接从 resolved 顶层取曲线(Resolver 已放 final_data)
        # 旧逻辑 ap = resolved.get("analysis_pack") 永远为空(V7.1 Resolver 未把 analysis_pack 放入 final_data)
        # 这是 V8.3 修复的副作用:hr/speed/cadence 三条曲线终于能进 DB
        if resolved.get("hr_curve"):
            result["hr_curve"] = json.dumps(resolved["hr_curve"], ensure_ascii=False)
        if resolved.get("speed_curve"):
            result["speed_curve"] = json.dumps(resolved["speed_curve"], ensure_ascii=False)
        # V8.3: cadence_curve 持久化(V7.12 步频稳定性依赖)
        if resolved.get("cadence_curve"):
            # 过滤 None(设备未采样),保留非零值(步频>0 是真值)
            cad_vals = [c for c in resolved["cadence_curve"] if c is not None and c > 0]
            if cad_vals:
                result["cadence_curve"] = json.dumps(cad_vals, ensure_ascii=False)
        # V8.4: hr_zone_distribution 持久化(V7.13 训练负荷依赖)
        # result["hr_curve"] 已是 JSON 字符串,需反解
        hr_curve_for_zones = _safe_json_list(result.get("hr_curve")) or []
        profile_max_hr_for_zones = 0
        try:
            prof_for_zones = profile_backend.get_profile()
            profile_max_hr_for_zones = _safe_int(prof_for_zones.max_hr) if prof_for_zones and prof_for_zones.max_hr else 0
        except Exception:
            profile_max_hr_for_zones = 0
        max_hr_for_zones = profile_max_hr_for_zones or (_safe_int(result.get("max_hr")) or 0)
        hr_zone_json = _compute_hr_zone_distribution(hr_curve_for_zones, max_hr_for_zones)
        if hr_zone_json:
            result["hr_zone_distribution"] = hr_zone_json
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
                 weather_json, weather_status, weather_updated_at, weather_attempt_count, weather_error,
                 file_mtime, file_size, advanced_metrics, avg_power, max_power, normalized_power, avg_stroke_distance, swolf, device_name,
                 shadow_diff_json, source_type, is_mock, deleted_at, updated_at, hr_curve, speed_curve, cadence_curve, hr_zone_distribution, laps_json,
                 min_alt_m, total_descent_m, up_count, down_count, max_single_climb_m, difficulty_score, report_metrics_version,
                 avg_grade_pct, max_slope_pct, min_slope_pct, uphill_pct, downhill_pct,
                 aerobic_training_effect, anaerobic_training_effect, processing_status, processing_error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, 'fit_sdk', 0, NULL, datetime('now'), ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                activity.get("weather_status"),
                activity.get("weather_updated_at"),
                activity.get("weather_attempt_count", 0),
                activity.get("weather_error"),
                activity.get("file_mtime"),
                activity.get("file_size"),
                activity.get("advanced_metrics"),
                activity.get("avg_power"),
                activity.get("max_power"),
                activity.get("normalized_power"),
                activity.get("avg_stroke_distance"),
                activity.get("swolf"),
                activity.get("device_name") or "Unknown Device",
                activity.get("shadow_diff_json"),
                activity.get("hr_curve"),
                activity.get("speed_curve"),
                activity.get("cadence_curve"),  # V8.3
                activity.get("hr_zone_distribution"),  # V8.4
                activity.get("laps_json"),  # 真实圈速数据
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
                # V9.4.0:Training Effect(FIT 219/218 直读)
                activity.get("aerobic_training_effect"),
                activity.get("anaerobic_training_effect"),
                activity.get("processing_status") or "ready",
                activity.get("processing_error"),
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
            weather_json = ?, weather_status = ?, weather_updated_at = ?, weather_attempt_count = ?, weather_error = ?,
            file_mtime = ?, file_size = ?, advanced_metrics = ?,
            avg_power = ?, max_power = ?, normalized_power = ?, avg_stroke_distance = ?, swolf = ?,
            device_name = ?, shadow_diff_json = ?, hr_curve = ?, speed_curve = ?,
            laps_json = ?,
            min_alt_m = ?, total_descent_m = ?, up_count = ?, down_count = ?, max_single_climb_m = ?, difficulty_score = ?, report_metrics_version = ?,
            avg_grade_pct = ?, max_slope_pct = ?, min_slope_pct = ?, uphill_pct = ?, downhill_pct = ?,
            processing_status = ?, processing_error = ?,
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
            activity.get("weather_status"),
            activity.get("weather_updated_at"),
            activity.get("weather_attempt_count", 0),
            activity.get("weather_error"),
            activity.get("file_mtime"),
            activity.get("file_size"),
            activity.get("advanced_metrics"),
            activity.get("avg_power"),
            activity.get("max_power"),
            activity.get("normalized_power"),
            activity.get("avg_stroke_distance"),
            activity.get("swolf"),
            activity.get("device_name") or "Unknown Device",
            activity.get("shadow_diff_json"),
            activity.get("hr_curve"),
            activity.get("speed_curve"),
            activity.get("laps_json"),
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
            activity.get("processing_status") or "ready",
            activity.get("processing_error"),
            activity_id,
        ),
    )


def _upsert_processing_activity_placeholder(dst: Path, source_name: str | None = None) -> int:
    ensure_activity_sync_schema()
    resolved_path = str(dst.expanduser().resolve())
    stat = dst.stat()
    title = Path(source_name or dst.name).stem or dst.stem

    def _write() -> int:
        conn = profile_backend._conn()
        try:
            existing = _find_activity_by_file_path(conn, resolved_path, include_deleted=True)
            if existing:
                activity_id = int(existing["id"])
                conn.execute(
                    """
                    UPDATE activities
                    SET file_name = ?, filename = ?, title = COALESCE(NULLIF(title, ''), ?),
                        title_source = COALESCE(NULLIF(title_source, ''), 'filename'),
                        file_path = ?, file_mtime = ?, file_size = ?,
                        source_type = 'fit_sdk', is_mock = 0, deleted_at = NULL,
                        processing_status = 'processing', processing_error = NULL,
                        updated_at = datetime('now')
                    WHERE id = ?
                    """,
                    (dst.name, dst.name, title, resolved_path, float(stat.st_mtime), int(stat.st_size), activity_id),
                )
            else:
                cur = conn.execute(
                    """
                    INSERT INTO activities
                        (file_name, filename, title, title_source, file_path, file_mtime, file_size,
                         source_type, is_mock, deleted_at, updated_at, processing_status, processing_error)
                    VALUES (?, ?, ?, 'filename', ?, ?, ?, 'fit_sdk', 0, NULL, datetime('now'), 'processing', NULL)
                    """,
                    (dst.name, dst.name, title, resolved_path, float(stat.st_mtime), int(stat.st_size)),
                )
                activity_id = int(cur.lastrowid)
            conn.commit()
            return activity_id
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    return profile_backend.run_with_db_retry(_write)


def _mark_activity_processing_failed(file_path: str | Path, error: str) -> None:
    try:
        resolved_path = str(Path(file_path).expanduser().resolve())
    except Exception:
        resolved_path = str(file_path)
    conn = profile_backend._conn()
    try:
        conn.execute(
            """
            UPDATE activities
            SET processing_status = 'failed',
                processing_error = ?,
                updated_at = datetime('now')
            WHERE file_path = ?
            """,
            (str(error)[:500], resolved_path),
        )
        conn.commit()
    finally:
        conn.close()


def _delete_processing_activity_placeholder(conn: sqlite3.Connection, file_path: str, keep_id: int = 0) -> int:
    if not file_path:
        return 0
    path_values = {str(file_path)}
    try:
        path_values.add(str(Path(file_path).expanduser().resolve()))
    except Exception:
        pass
    placeholders = ",".join("?" * len(path_values))
    cur = conn.execute(
        f"""
        DELETE FROM activities
        WHERE file_path IN ({placeholders})
          AND id != ?
          AND COALESCE(NULLIF(processing_status, ''), 'ready') IN ('processing', 'pending')
        """,
        tuple(path_values) + (int(keep_id or 0),),
    )
    return int(cur.rowcount or 0)


def _activity_display_sql() -> str:
    return (
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
    skipped_system: list[str] = []
    for root, _dirs, files in os.walk(str(base)):
        for name in files:
            # 过滤 macOS AppleDouble 影子文件(._xxx.fit) + Windows 隐藏/系统文件
            # 这些是文件系统元数据,不是真正的 FIT,会让 fitparse 报错刷 ERROR 日志
            if name.startswith("._") or name in (".DS_Store", "Thumbs.db", "desktop.ini") or name.startswith("~$"):
                skipped_system.append(name)
                continue
            if name.lower().endswith(".fit"):
                fit_files.append(Path(root) / name)
    fit_files.sort(key=lambda item: (str(item.parent).lower(), item.name.lower()))
    abs_path = str(base.resolve()) if base.exists() else str(base)
    logger.info("FIT 扫描目录: %s, 发现文件数: %s", abs_path, len(fit_files))
    if skipped_system:
        logger.info("FIT 扫描跳过 %d 个系统/影子文件(.DS_Store / ._* / Thumbs.db 等)", len(skipped_system))
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
    start_time = str(row.get("start_time_utc") or row.get("start_time") or "").strip()
    dist_km = _safe_float(
        row.get("dist_km")
        if row.get("dist_km") is not None
        else row.get("distance_km_clean"),
        0.0,
    )
    duration_sec = _safe_int(
        row.get("duration_sec")
        if row.get("duration_sec") is not None
        else row.get("duration"),
        0,
    )
    if start_time and dist_km > 0 and duration_sec > 0:
        sport_type = str(row.get("sub_sport_type") or row.get("sport_type") or "unknown").strip() or "unknown"
        return f"semantic:{sport_type}:{start_time}:{round(dist_km, 3):.3f}:{duration_sec}"

    filename = str(row.get("filename") or row.get("file_name") or "").strip()
    if filename:
        return f"file:{filename}"
    file_path = str(row.get("file_path") or "").strip()
    if file_path:
        return f"file:{os.path.basename(file_path)}"
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


def _expand_activity_ids_to_duplicate_groups(conn: sqlite3.Connection, ids: list[int]) -> tuple[list[dict[str, Any]], list[int]]:
    """Expand visible activity ids to hidden semantic duplicates for hard delete."""
    if not ids:
        return [], []
    select_fields = """
        id,
        COALESCE(file_name, filename) AS file_name,
        filename,
        file_path,
        start_time,
        start_time_utc,
        sport_type,
        sub_sport_type,
        dist_km,
        COALESCE(duration, duration_sec) AS duration,
        duration_sec
    """
    selected_rows = conn.execute(
        f"SELECT {select_fields} FROM activities WHERE id IN ({','.join('?' * len(ids))})",
        ids,
    ).fetchall()
    selected_dicts = [dict(row) for row in selected_rows]
    existing_ids = {int(row["id"]) for row in selected_dicts}
    missing_ids = sorted(set(ids) - existing_ids)
    semantic_identities = {
        _activity_row_identity(row)
        for row in selected_dicts
        if _activity_row_identity(row).startswith("semantic:")
    }
    if not semantic_identities:
        return selected_dicts, missing_ids

    candidate_rows = conn.execute(
        f"""
        SELECT {select_fields}
        FROM activities
        WHERE deleted_at IS NULL
        ORDER BY id ASC
        """
    ).fetchall()
    expanded: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for row in [dict(item) for item in candidate_rows]:
        row_id = int(row["id"])
        if row_id in existing_ids or _activity_row_identity(row) in semantic_identities:
            if row_id in seen_ids:
                continue
            seen_ids.add(row_id)
            expanded.append(row)
    return expanded, missing_ids


def _activity_points_for_duplicate_check(activity: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("points", "points_json", "track_json"):
        raw = activity.get(key)
        if not raw:
            continue
        try:
            obj = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            continue
        if isinstance(obj, dict):
            obj = obj.get("points") or obj.get("track_data") or []
        if isinstance(obj, list):
            return [dict(p) for p in obj if isinstance(p, dict)]
    return []


def _find_semantic_duplicate_activity(activity: dict[str, Any]) -> dict[str, Any] | None:
    dist_km = _safe_float(activity.get("dist_km"))
    duration_sec = _safe_int(activity.get("duration_sec") if activity.get("duration_sec") is not None else activity.get("duration"))
    start_time = activity.get("start_time")
    start_time_utc = activity.get("start_time_utc")
    if not (dist_km and dist_km > 0 and duration_sec and duration_sec > 0 and (start_time or start_time_utc)):
        return None
    points = _activity_points_for_duplicate_check(activity)
    if not points:
        return None
    try:
        dup_res = profile_backend.check_duplicate_activity(
            start_time=start_time,
            dist_km=float(dist_km),
            duration_sec=int(duration_sec),
            points_json=points,
            start_time_utc=start_time_utc,
        )
    except Exception as exc:
        logger.warning("[dedup] semantic duplicate check skipped for %s: %s", activity.get("file_name") or activity.get("filename"), exc)
        return None
    if not dup_res.get("is_duplicate"):
        return None
    duplicate = dup_res.get("duplicate_record") or {}
    duplicate_id = _safe_int(duplicate.get("id"))
    if not duplicate_id:
        return None
    duplicate["duplicate_score"] = dup_res.get("score")
    return duplicate


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
        SELECT id, file_name, filename, file_path, deleted_at, processing_status
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
        SELECT id, file_name, filename, file_path, title, sport_type, sub_sport_type, start_time, updated_at,
               file_mtime, file_size, deleted_at, processing_status
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


def _persist_sync_activity(
    activity: dict[str, Any],
    dedupe_index: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    profile_backend._assert_gpx_not_persisted(activity)  # §二 §八: GPX/KML 用后即抛
    file_name = str(activity.get("file_name") or activity.get("filename") or "").strip()
    file_path = str(activity.get("file_path") or "").strip()
    activity["sport_type"] = _normalize_activity_token(activity.get("sport_type"))
    activity["sub_sport_type"] = _normalize_activity_token(activity.get("sub_sport_type"))

    # CONTRACT §2.1 / §6: 在持久化前计算报告 canonical 派生指标
    # 保存设备报告的 total_descent (§2.1 数据可信分层: fit_sdk > points 计算值)
    _device_descent = _safe_float(activity.get("total_descent_m_device"))
    _points_raw = activity.get("points")
    if _points_raw and isinstance(_points_raw, list) and len(_points_raw) >= 2:
        try:
            _dist = _safe_float(activity.get("dist_km", 0))
            _gain = _safe_float(activity.get("gain_m", 0))
            _report = profile_backend.compute_report_metrics(_points_raw, _dist, _gain)
            activity.update(_report)
            # 设备报告的 total_descent 优先于 points 计算值
            if _device_descent is not None and _device_descent > 0:
                activity["total_descent_m"] = _device_descent
        except Exception as exc:
            logger.exception("[METRICS] compute_report_metrics failed for %s: %s", activity.get("file_name"), exc)
            # 降级路径也保留设备值
            if _device_descent is not None and _device_descent > 0:
                activity["total_descent_m"] = _device_descent

    def _write() -> dict[str, Any]:
        conn = profile_backend._conn()
        try:
            existing = _find_activity_by_file_path(conn, file_path, include_deleted=True) if file_path else None
            if existing and str(existing.get("processing_status") or "").strip().lower() in {"processing", "pending"}:
                existing = None
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
                if existing and str(existing.get("processing_status") or "").strip().lower() in {"processing", "pending"}:
                    existing = None
            strict_dedupe_key = profile_backend.build_activity_dedupe_key(activity)
            if not existing and strict_dedupe_key:
                if dedupe_index is not None:
                    indexed = dedupe_index.get(strict_dedupe_key)
                    if indexed:
                        row = conn.execute(
                            """
                            SELECT id, file_name, filename, file_path, deleted_at
                            FROM activities
                            WHERE id = ? AND deleted_at IS NULL
                            """,
                            (int(indexed.get("id") or 0),),
                        ).fetchone()
                        existing = dict(row) if row else None
                else:
                    existing = profile_backend.find_activity_by_dedupe_key(conn, activity)
                if existing:
                    existing_path = str(existing.get("file_path") or "").strip()
                    current_path = str(activity.get("file_path") or "").strip()
                    if current_path and existing_path != current_path:
                        _delete_processing_activity_placeholder(conn, current_path, keep_id=int(existing["id"]))
                        conn.commit()
                        if dedupe_index is not None:
                            dedupe_index[strict_dedupe_key] = {"id": int(existing["id"])}
                        return {
                            "op": "skipped",
                            "id": int(existing["id"]),
                            "dedupe": "strict_key",
                            "duplicate": True,
                        }
            semantic_duplicate = None
            if not existing:
                semantic_duplicate = _find_semantic_duplicate_activity(activity)
                duplicate_id = _safe_int((semantic_duplicate or {}).get("id"))
                if duplicate_id:
                    row = conn.execute(
                        """
                        SELECT id, file_name, filename, file_path, deleted_at
                        FROM activities
                        WHERE id = ?
                          AND deleted_at IS NULL
                          AND COALESCE(source_type, 'fit_sdk') = 'fit_sdk'
                          AND COALESCE(is_mock, 0) = 0
                        """,
                        (duplicate_id,),
                    ).fetchone()
                    existing = dict(row) if row else None
            if existing:
                _update_activity_sync_row(conn, int(existing["id"]), activity)
                op = "updated"
                activity_id = int(existing["id"])
                dedupe = "semantic" if semantic_duplicate else ("strict_key" if strict_dedupe_key else None)
            else:
                activity_id = _insert_activity_sync_row(conn, activity)
                op = "inserted"
                dedupe = None
            conn.commit()
            if dedupe_index is not None and strict_dedupe_key:
                dedupe_index[strict_dedupe_key] = {"id": activity_id}
            res = {"op": op, "id": activity_id}
            if dedupe:
                res["dedupe"] = dedupe
                res["duplicate_score"] = semantic_duplicate.get("duplicate_score") if semantic_duplicate else None
            return res
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    return profile_backend.run_with_db_retry(_write)


def _fit_file_size_kb(target: Path) -> float:
    try:
        return target.stat().st_size / 1024
    except OSError:
        return 0.0


def _fit_health_skip_result(
    target: Path,
    *,
    filter_reasons: list[str],
    file_size_kb: float,
    total_distance_m: float | None = None,
    record_count: int | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": True,
        "op": "skipped",
        "reason": "filtered_as_health_data",
        "filter_reasons": filter_reasons,
        "file_size_kb": round(file_size_kb, 2),
        "file_path": str(target),
        "filename": target.name,
        "activity_id": 0,
    }
    if total_distance_m is not None:
        result["total_distance_m"] = round(total_distance_m, 1)
    if record_count is not None:
        result["record_count"] = record_count
    return result


def _filter_fit_file_before_parse(target: Path) -> dict[str, Any] | None:
    """Fast health-data filter for tiny FIT files before expensive parsing."""
    file_size_kb = _fit_file_size_kb(target)
    if file_size_kb < MIN_FIT_FILE_SIZE_KB:
        logger.info(
            "[V10.1 filter] skip %s: file_size_kb=%.2f < %.2f (疑似健康监测数据)",
            target.name, file_size_kb, MIN_FIT_FILE_SIZE_KB,
        )
        return _fit_health_skip_result(
            target,
            filter_reasons=["file_too_small"],
            file_size_kb=file_size_kb,
        )
    return None


def _fit_activity_record_count(activity: dict[str, Any]) -> int:
    for key in ("points", "points_json", "track_json"):
        raw = activity.get(key)
        if not raw:
            continue
        try:
            obj = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(obj, list):
            return len(obj)
    return 0


def _filter_fit_activity_after_parse(activity: dict[str, Any], target: Path, file_size_kb: float | None = None) -> dict[str, Any] | None:
    """Filter parsed FIT payloads that are health snapshots rather than workouts."""
    filter_reasons: list[str] = []
    try:
        dist_km_val = _safe_float(activity.get("dist_km"))
    except Exception:
        dist_km_val = 0.0
    total_distance_m = (dist_km_val or 0.0) * 1000.0
    if total_distance_m < MIN_FIT_DISTANCE_M:
        filter_reasons.append("distance_too_short")

    record_count = _fit_activity_record_count(activity)
    if record_count < MIN_FIT_RECORD_COUNT:
        filter_reasons.append("record_count_too_low")

    if not filter_reasons:
        return None
    if file_size_kb is None:
        file_size_kb = _fit_file_size_kb(target)
    logger.info(
        "[V10.1 filter] skip %s: reasons=%s, file_size_kb=%.2f, total_distance_m=%.1f, record_count=%d",
        target.name, filter_reasons, file_size_kb, total_distance_m, record_count,
    )
    return _fit_health_skip_result(
        target,
        filter_reasons=filter_reasons,
        file_size_kb=file_size_kb,
        total_distance_m=total_distance_m,
        record_count=record_count,
    )


def _sync_single_fit_file(file_path: str | Path) -> dict[str, Any]:
    ensure_activity_sync_schema()
    target = Path(file_path).expanduser().resolve()
    if not target.is_file():
        raise FileNotFoundError(f"未找到 FIT 文件: {target}")
    if target.suffix.lower() != ".fit":
        raise ValueError(f"仅支持监控 FIT 文件: {target}")

    # V10.1 健康数据过滤(契约 §2.2 fit_sdk 严格语义)
    # 在解析前先做文件大小检查,避免对明显是健康监测的小文件做无谓解析
    pre_filter = _filter_fit_file_before_parse(target)
    if pre_filter:
        return pre_filter

    activity = _parse_fit_activity_for_sync(target)

    # V10.1 解析后过滤:距离和记录数(契约 §2.1 全链路可追溯:过滤逻辑在后端边界层)
    post_filter = _filter_fit_activity_after_parse(activity, target)
    if post_filter:
        return post_filter

    write_res = _persist_sync_activity(activity)
    activity_id = int(write_res.get("id") or 0)

    if write_res.get("op") == "skipped" and write_res.get("dedupe") == "strict_key":
        try:
            if target.exists() and target.is_file() and _is_path_under_dir(target, Path(TRACKS_DIR).expanduser().resolve()):
                target.unlink()
        except OSError:
            logger.warning("[dedup] duplicate FIT file cleanup failed: %s", target)

    conn = profile_backend._conn()
    try:
        if activity_id:
            fetched = conn.execute(
                "SELECT * FROM activities WHERE id = ? AND deleted_at IS NULL",
                (activity_id,),
            ).fetchone()
            row = dict(fetched) if fetched else None
        else:
            row = _find_activity_by_file_path(conn, str(target))
    finally:
        conn.close()

    return {
        "ok": True,
        "activity_id": activity_id or int((row or {}).get("id") or 0),
        "file_path": str(target),
        "filename": target.name,
        "op": write_res.get("op"),
        "dedupe": write_res.get("dedupe"),
        "duplicate": bool(write_res.get("duplicate")),
        "activity": row or {},
        "resolved": activity.get("resolved"),
        "diff": activity.get("diff"),
        # T-IMPORT-FIT-DEDUP: 暴露 points 给 80 分查重用 (不污染契约 §三 响应结构,仅扩展)
        "points": activity.get("points") or [],
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
            from watchdog.observers import Observer

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
                or result.get("msg")
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
FIT_IMPORT_JOB_MANAGER = FitSyncJobManager()


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

# V4.0 治理: AI Snapshot 契约层全部下沉至 metrics_resolver.py
# 删除: FORBIDDEN_SNAPSHOT_FIELDS / _MAX_SNAPSHOT_KEYS / get_snapshot_field_whitelist
#       validate_ai_snapshot / debug_ai_snapshot
# 完整实现见 metrics_resolver.py: MetricsResolver._AI_SNAPSHOT_* / _validate_ai_snapshot /
#                                   _debug_ai_snapshot / _build_ai_snapshot_block /
#                                   _build_ai_snapshot_text_block


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
                _report = profile_backend.compute_report_metrics(points, _dist, _gain)
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


# ── AI Snapshot Builder (V4.0 治理: IO 隔离 + 1 行透传至 Resolver) ──


def _build_ai_snapshot(activity_id: int) -> dict[str, Any] | None:
    """AI 语义快照构建器 (V4.0 治理: IO 隔离拆分)

    V4.0 治理: 本函数仅做 IO 查询 (SQLite) + 1 行透传至 Resolver 纯计算
    所有 dict 转换/格式化/校验逻辑已下沉至 MetricsResolver._build_ai_snapshot_block
    严禁在本函数中重新添加业务计算(透传代码模板约束)
    """
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
            " avg_grade_pct, max_slope_pct, min_slope_pct, uphill_pct, downhill_pct,"
            " aerobic_training_effect, anaerobic_training_effect"
            " FROM activities WHERE id = ? AND deleted_at IS NULL",
            (activity_id,),
        ).fetchone()
        conn.close()
        if not row:
            return None
        # 1 行透传至 Resolver 纯计算(V4.0 治理)
        return MetricsResolver._build_ai_snapshot_block(dict(row))
    except Exception:
        return None


def _build_ai_snapshot_block(snapshot: dict[str, Any] | None) -> str:
    """V4.0 治理: 已下沉至 MetricsResolver._build_ai_snapshot_text_block, 此函数为 1 行透传兼容层"""
    return MetricsResolver._build_ai_snapshot_text_block(snapshot)


def _parse_activity_advice_context(raw_context: Any) -> dict[str, str]:
    """Parse user-provided planning context; never infer from track history."""
    data: dict[str, Any] = {}
    if isinstance(raw_context, dict):
        data = raw_context
    elif isinstance(raw_context, str):
        text = raw_context.strip()
        if text:
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    data = parsed
                else:
                    data = {"user_activity_type": text}
            except json.JSONDecodeError:
                data = {"user_activity_type": text}

    user_activity_type = str(data.get("user_activity_type") or data.get("activity_type") or "").strip()
    planned_start_time = str(data.get("planned_start_time") or data.get("planned_time") or "").strip()
    return {
        "user_activity_type": user_activity_type,
        "planned_start_time": planned_start_time,
        "activity_type_source": "user_input" if user_activity_type else "missing",
        "planned_time_source": "user_input" if planned_start_time else "missing",
    }


_ACTIVITY_ADVICE_SNAPSHOT_KEYS: tuple[str, ...] = (
    "activity_id", "distance_km", "distance_display", "duration_sec",
    "elevation_gain_m", "total_descent_m", "max_alt_m", "min_alt_m",
    "avg_grade_pct", "max_slope_pct", "min_slope_pct", "uphill_pct",
    "downhill_pct", "up_count", "down_count", "max_single_climb_m",
    "difficulty_score", "region", "start_lat", "start_lon", "source",
)


def _activity_advice_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _activity_advice_format_distance(distance_km: float | None) -> str | None:
    if distance_km is None or distance_km <= 0:
        return None
    if distance_km < 0.1:
        return f"{int(round(distance_km * 1000))}m"
    return f"{distance_km:.2f}km"


def _build_activity_advice_snapshot_from_ai_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    """Build the activity-advice-only route facts snapshot from DB truth."""
    if not isinstance(snapshot, dict):
        return None
    advice_snapshot = {key: snapshot.get(key) for key in _ACTIVITY_ADVICE_SNAPSHOT_KEYS if key in snapshot}
    if not advice_snapshot.get("source"):
        advice_snapshot["source"] = "DB Canonical / Resolver Truth"
    return advice_snapshot or None


def _build_activity_advice_snapshot_from_overview_route_facts(obj: dict[str, Any]) -> dict[str, Any] | None:
    """Build activity advice route facts from the same aggregate facts shown in the overview."""
    raw_facts = obj.get("activityAdviceRouteFacts") if isinstance(obj, dict) else None
    if not isinstance(raw_facts, dict):
        raw_facts = obj.get("activity_advice_route_facts") if isinstance(obj, dict) else None
    if not isinstance(raw_facts, dict):
        return None

    advice_snapshot: dict[str, Any] = {}
    for key in _ACTIVITY_ADVICE_SNAPSHOT_KEYS:
        if key in raw_facts and raw_facts.get(key) is not None:
            advice_snapshot[key] = raw_facts.get(key)

    if not advice_snapshot.get("distance_display"):
        advice_snapshot["distance_display"] = _activity_advice_format_distance(
            _activity_advice_float(advice_snapshot.get("distance_km"))
        )
    if not advice_snapshot.get("source"):
        advice_snapshot["source"] = "overview_route_facts"
    return {key: value for key, value in advice_snapshot.items() if value is not None}


def _build_activity_advice_snapshot_from_track_context(obj: dict[str, Any]) -> dict[str, Any] | None:
    """Aggregate temporary route facts from synced track context without retaining raw points."""
    raw_points = obj.get("points") if isinstance(obj, dict) else None
    if not isinstance(raw_points, list) or len(raw_points) < 2:
        return None

    distance_m = 0.0
    elevation_gain_m = 0.0
    total_descent_m = 0.0
    altitudes: list[float] = []
    first_lat: float | None = None
    first_lon: float | None = None
    previous: tuple[float, float, float | None] | None = None

    for point in raw_points:
        if not isinstance(point, dict):
            continue
        lat = _activity_advice_float(point.get("lat"))
        lon = _activity_advice_float(point.get("lon"))
        if lat is None or lon is None:
            continue
        alt = _activity_advice_float(point.get("alt"))
        if alt is not None:
            altitudes.append(alt)
        if first_lat is None or first_lon is None:
            first_lat = lat
            first_lon = lon
        if previous is not None:
            prev_lat, prev_lon, prev_alt = previous
            try:
                distance_m += track_backend.haversine_m(prev_lat, prev_lon, lat, lon)
            except Exception:
                pass
            if alt is not None and prev_alt is not None:
                delta = alt - prev_alt
                if delta > 0:
                    elevation_gain_m += delta
                elif delta < 0:
                    total_descent_m += abs(delta)
        previous = (lat, lon, alt)

    if first_lat is None or first_lon is None or distance_m <= 0:
        return None

    distance_km = round(distance_m / 1000.0, 2)
    snapshot: dict[str, Any] = {
        "distance_km": distance_km,
        "distance_display": _activity_advice_format_distance(distance_km),
        "elevation_gain_m": round(elevation_gain_m) if altitudes else None,
        "total_descent_m": round(total_descent_m) if altitudes else None,
        "max_alt_m": round(max(altitudes)) if altitudes else None,
        "min_alt_m": round(min(altitudes)) if altitudes else None,
        "start_lat": round(first_lat, 6),
        "start_lon": round(first_lon, 6),
        "source": "temporary_track_context",
    }
    return {key: value for key, value in snapshot.items() if value is not None}


def _build_activity_advice_messages(
    snapshot: dict[str, Any] | None,
    planning_context: dict[str, Any] | None,
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": llm_backend.build_activity_advice_system_prompt(snapshot, planning_context),
        },
        {
            "role": "user",
            "content": llm_backend.build_activity_advice_user_prompt(),
        },
    ]






def _build_radar_insight_snapshot(sport_type: str) -> dict[str, Any]:
    """雷达图 AI 洞察专用 snapshot 构建器(§5.4 规则 3)。
    数据源:_rolling_aggregate_radar_metrics(雷达后端引擎) + profile_backend
    白名单:仅暴露雷达相关字段,严禁 shadow_diff / debug-only 字段。
    """
    if not sport_type:
        return {}

    metrics = _rolling_aggregate_radar_metrics(sport_type)
    prof = profile_backend.get_profile()

    ALLOWED_METRIC_KEYS = (
        "ctl", "atl", "tsb", "hrv",
        "endurance_score", "endurance_ctl_score", "endurance_consistency_score",
        "endurance_training_days_28d", "endurance_sample_count",
        "endurance_confidence", "endurance_source",
        "recovery_score", "recovery_source", "recovery_confidence", "recovery_reasons",
        "decoupling", "vam", "threshold_hr", "anaerobic_peak",
        "stability_sample_count", "stability_confidence",
        "climbing_activity_count_90d", "climbing_elevation_activity_count_90d",
        "climbing_sample_count", "climbing_confidence", "climbing_reason",
        "climbing_vam_p90", "climbing_score_cap", "climbing_score_components",
        "threshold_source", "threshold_confidence", "threshold_sample_count", "threshold_power", "threshold_wkg",
        "anaerobic_peak_source", "anaerobic_peak_confidence", "anaerobic_sample_count",
        "radar",
    )
    safe_metrics = {k: metrics.get(k) for k in ALLOWED_METRIC_KEYS if k in metrics}

    safe_user_profile = {}
    if prof is not None:
        for k in (
            "age", "gender", "resting_hr", "recent_resting_hr", "resting_hr_7d_avg",
            "max_hr", "hrv_baseline", "recent_hrv", "hrv_7d_avg",
        ):
            v = getattr(prof, k, None)
            if v is not None:
                safe_user_profile[k] = v

    return {
        "source": "DB Canonical / 雷达后端引擎 / Resolver Truth",
        "sport_type": sport_type,
        "aggregation_window_days": 90,
        "metrics": safe_metrics,
        "user_profile": safe_user_profile,
    }


def _build_radar_insight_messages(
    snapshot: dict[str, Any],
    sport_type: str,
) -> list[dict[str, str]]:
    """组装 [system_msg, user_msg] 用于 LLM 调用。"""
    system_prompt = llm_backend.build_radar_insight_system_prompt(snapshot, sport_type)
    user_prompt = llm_backend.build_radar_insight_user_prompt(sport_type)
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


class Api:
    """pywebview js_api：轨迹文件、导出、大模型（OpenAI 兼容）等。"""

    SYSTEM_INSTRUCTION = "__SYSTEM_INSTRUCTION__"
    REPORT_ACTIVITY_ADVICE = "__REPORT_ACTIVITY_ADVICE__"
    RADAR_INSIGHT = "__RADAR_INSIGHT__"
    FATIGUE_REVIEW_INSIGHT = "__FATIGUE_REVIEW_INSIGHT__"

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
        self._activity_advice_snapshot: dict[str, Any] | None = None
        self._fatigue_review_activity_id: int = 0
        self._profile_startup_sync_scheduled = False
        self._profile_sync_timer: threading.Timer | None = None
        self._region_enrichment_timer: threading.Timer | None = None
        self._region_enrichment_active = False
        self._window_shown = False

    def on_loaded(self, *args) -> dict:
        """页面加载完成后显示窗口，解决原生窗口先白屏的问题。"""
        try:
            if self._window_shown:
                return {"ok": True, "already_shown": True}
            target = self._window
            if target is not None:
                apply_macos_native_window_chrome(target)
                target.show()
                self._window_shown = True
                _record_startup_event("window_show")
                return {"ok": True}
        except Exception as exc:
            logger.debug("显示主窗口失败: %s", exc)
        return {"ok": False}

    def bind_window(self, window) -> None:
        self._window = window

    def set_watch_service(self, watch_service: FITFolderWatchService) -> None:
        self._watch_service = watch_service

    def _restart_watch_service(self) -> None:
        if self._watch_service is None:
            return
        self._watch_service.restart()

    def notify_frontend_ready(self) -> dict:
        _record_startup_event("frontend_ready", pending_notifications=len(self._pending_track_notifications))
        self._frontend_ready = True
        self._flush_pending_track_notifications()
        self._schedule_profile_startup_sync()
        self._schedule_region_enrichment()
        return {"ok": True}

    def get_startup_timeline(self) -> dict:
        return _api_success({
            "process_elapsed_ms": _startup_elapsed_ms(),
            "events": _startup_timeline_snapshot(),
        })

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

        timer = threading.Timer(REGION_ENRICH_STARTUP_DELAY_SEC, _start)
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
        self._schedule_next_profile_sync(PROFILE_STARTUP_SYNC_DELAY_SEC)

    def _schedule_next_profile_sync(self, delay_sec: float) -> None:
        if _APP_SHUTTING_DOWN.is_set():
            return
        timer = threading.Timer(delay_sec, self._run_profile_sync_tick)
        timer.daemon = True
        timer.start()
        self._profile_sync_timer = timer

    def _run_profile_sync_tick(self) -> None:
        try:
            self.startup_sync_check()
        except Exception:
            logger.exception("画像同步 tick 异常")
        finally:
            if not _APP_SHUTTING_DOWN.is_set():
                self._schedule_next_profile_sync(PROFILE_SYNC_INTERVAL_SEC)

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
            needed = profile_backend.is_sync_needed_today()
            if not needed:
                result = {"ok": True, "already_synced": True, "message": "今天已同步", **profile_backend.get_profile_sync_metadata()}
                self._dispatch_profile_sync_event("profile_sync_complete", result)
                return result
            cooldown = profile_backend.should_skip_profile_sync_for_cooldown()
            if cooldown:
                result = {"ok": False, "cooldown": True, "message": "上次同步失败，冷却中", **profile_backend.get_profile_sync_metadata()}
                self._dispatch_profile_sync_event("profile_sync_complete", result)
                return result
            self._dispatch_profile_sync_event("profile_sync_started", {
                **profile_backend.get_profile_sync_metadata(),
                "sync_status": "syncing",
                "last_sync_ago": "正在同步",
            })
            cfg = llm_backend.load_llm_config()
            watch_brand = str(cfg.get("watch_brand") or "garmin").strip().lower() or "garmin"
            result = profile_backend.fetch_mcp_persona(watch_brand, trigger_type="startup")
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
           AI Input Governance:
           - 通用 AI snapshot 仍仅来自 activity_id / DB truth
           - 活动建议使用后端白名单 route facts,临时轨迹只保留聚合事实
           - 前端 track.html 角色: Visualization Layer + current track sync"""
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
        # 通用 AI 仍使用 DB truth；活动建议优先使用概览同源 route facts。
        activity_id = obj.get("activity_id") or obj.get("activityId")
        if activity_id:
            self._ai_snapshot = _build_ai_snapshot(int(activity_id))
            if isinstance(self._ai_snapshot, dict):
                self._ai_snapshot["activity_id"] = int(activity_id)
        else:
            self._ai_snapshot = None
        self._activity_advice_snapshot = (
            _build_activity_advice_snapshot_from_overview_route_facts(obj)
            or _build_activity_advice_snapshot_from_track_context(obj)
            or _build_activity_advice_snapshot_from_ai_snapshot(self._ai_snapshot)
        )
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
        cfg["ai_notified"] = bool(llm_backend.load_llm_config().get("ai_notified", False))
        return _api_success(cfg)

    def get_app_info(self) -> dict:
        return _api_success({
            "name": "脉图 FitVault",
            "version": APP_VERSION,
        })

    def get_help_markdown(self) -> dict:
        try:
            return _api_success({
                "markdown": load_help_markdown(),
                "source": "docs/脉图帮助说明.md",
            })
        except FileNotFoundError as exc:
            return _api_error(API_CODE_NOT_FOUND, str(exc))

    def set_ai_notified(self, value: bool) -> dict:
        """独立写入 ai_notified 标志，不触发网络测试。"""
        try:
            current = llm_backend.load_llm_config()
            llm_backend.save_llm_config(
                provider=current.get("provider", ""),
                url=current.get("url", ""),
                model=current.get("model", ""),
                api_key=current.get("api_key", ""),
                agent_id=current.get("agent_id", ""),
                watch_brand=current.get("watch_brand", ""),
                local_dir=current.get("local_dir", ""),
                ai_notified=bool(value),
                ai_notified_hash=str(current.get("ai_notified_hash", "")),
                transport=current.get("transport", "http"),
                cli_type=current.get("cli_type", ""),
                cli_path=current.get("cli_path", ""),
                cli_args=current.get("cli_args", ""),
                cli_model=current.get("cli_model", ""),
                cli_timeout_sec=current.get("cli_timeout_sec", 300),
                garmin_region=current.get("garmin_region", ""),
                coros_region=current.get("coros_region", ""),
            )
            return _api_success({"ai_notified": bool(value)})
        except Exception:
            logger.exception("set_ai_notified failed")
            return _api_error(API_CODE_INTERNAL, "写入 ai_notified 失败")

    def set_watch_brand(self, value: str) -> dict:
        """独立写入 watch_brand，不触发网络测试，选择即持久化。"""
        try:
            current = llm_backend.load_llm_config()
            llm_backend.save_llm_config(
                provider=current.get("provider", ""),
                url=current.get("url", ""),
                model=current.get("model", ""),
                api_key=current.get("api_key", ""),
                agent_id=current.get("agent_id", ""),
                watch_brand=str(value or ""),
                local_dir=current.get("local_dir", ""),
                ai_notified=bool(current.get("ai_notified", False)),
                ai_notified_hash=str(current.get("ai_notified_hash", "")),
                transport=current.get("transport", "http"),
                cli_type=current.get("cli_type", ""),
                cli_path=current.get("cli_path", ""),
                cli_args=current.get("cli_args", ""),
                cli_model=current.get("cli_model", ""),
                cli_timeout_sec=current.get("cli_timeout_sec", 300),
                garmin_region=current.get("garmin_region", ""),
                coros_region=current.get("coros_region", ""),
            )
            return _api_success({"watch_brand": str(value or "")})
        except Exception:
            logger.exception("set_watch_brand failed")
            return _api_error(API_CODE_INTERNAL, "写入 watch_brand 失败")

    def set_garmin_region(self, value: str = "") -> dict:
        """Persist Garmin account region without testing LLM connectivity."""
        try:
            region = garmin_sync.resolve_garmin_region(value)
            current = llm_backend.load_llm_config()
            llm_backend.save_llm_config(
                provider=current.get("provider", ""),
                url=current.get("url", ""),
                model=current.get("model", ""),
                api_key=current.get("api_key", ""),
                agent_id=current.get("agent_id", ""),
                watch_brand=current.get("watch_brand", ""),
                local_dir=current.get("local_dir", ""),
                ai_notified=bool(current.get("ai_notified", False)),
                ai_notified_hash=str(current.get("ai_notified_hash", "")),
                transport=current.get("transport", "http"),
                cli_type=current.get("cli_type", ""),
                cli_path=current.get("cli_path", ""),
                cli_args=current.get("cli_args", ""),
                cli_model=current.get("cli_model", ""),
                cli_timeout_sec=current.get("cli_timeout_sec", 300),
                garmin_region=region,
                coros_region=current.get("coros_region", ""),
            )
            return _api_success({"garmin_region": region})
        except garmin_sync.GarminSyncError as exc:
            return _api_error(API_CODE_VALIDATION, str(exc), {"garmin_region": str(value or "")})
        except Exception:
            logger.exception("set_garmin_region failed")
            return _api_error(API_CODE_INTERNAL, "写入 Garmin 区域失败")

    def set_coros_region(self, value: str = "") -> dict:
        """Persist COROS account region without testing LLM connectivity."""
        try:
            region = coros_sync.resolve_coros_region(value)
            current = llm_backend.load_llm_config()
            llm_backend.save_llm_config(
                provider=current.get("provider", ""),
                url=current.get("url", ""),
                model=current.get("model", ""),
                api_key=current.get("api_key", ""),
                agent_id=current.get("agent_id", ""),
                watch_brand=current.get("watch_brand", ""),
                local_dir=current.get("local_dir", ""),
                ai_notified=bool(current.get("ai_notified", False)),
                ai_notified_hash=str(current.get("ai_notified_hash", "")),
                transport=current.get("transport", "http"),
                cli_type=current.get("cli_type", ""),
                cli_path=current.get("cli_path", ""),
                cli_args=current.get("cli_args", ""),
                cli_model=current.get("cli_model", ""),
                cli_timeout_sec=current.get("cli_timeout_sec", 300),
                garmin_region=current.get("garmin_region", ""),
                coros_region=region,
            )
            return _api_success({"coros_region": region})
        except coros_sync.CorosSyncError as exc:
            return _api_error(API_CODE_VALIDATION, str(exc), {"coros_region": str(value or "")})
        except Exception:
            logger.exception("set_coros_region failed")
            return _api_error(API_CODE_INTERNAL, "写入 COROS 区域失败")

    @staticmethod
    def _garmin_region_from_config(region: str = "") -> str:
        explicit = str(region or "").strip()
        if explicit:
            return explicit
        cfg = llm_backend.load_llm_config()
        return str(cfg.get("garmin_region") or "").strip()

    def check_garmin_auth_status(self, region: str = "") -> dict:
        """Check local Garmin token presence without contacting Garmin."""
        try:
            resolved_region = self._garmin_region_from_config(region)
            status = garmin_sync.check_auth_status(region=resolved_region or None)
            payload = {
                "region": status.region,
                "status": status.status,
                "token_path": status.token_path,
                "message": status.message,
                "login_command": status.login_command,
                "authorized": bool(status.ok),
            }
            if status.ok:
                return _api_success(payload, msg=status.message)
            return _api_error(API_CODE_EXTERNAL_SERVICE, status.message, payload)
        except Exception:
            logger.exception("check_garmin_auth_status failed")
            return _api_error(API_CODE_INTERNAL, "Garmin 授权状态检查失败")

    def start_garmin_login(self, region: str = "") -> dict:
        """Start the bundled Garmin login script; intended for explicit user action."""
        try:
            resolved_region = self._garmin_region_from_config(region)
            result = garmin_sync.start_login(region=resolved_region or None)
            payload = {
                "region": result.region,
                "status": result.status,
                "message": result.message,
                "command": result.command,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
            if result.ok:
                return _api_success(payload, msg=result.message)
            return _api_error(API_CODE_EXTERNAL_SERVICE, result.message, payload)
        except Exception:
            logger.exception("start_garmin_login failed")
            return _api_error(API_CODE_INTERNAL, "Garmin 登录授权启动失败")

    @staticmethod
    def _coros_region_from_config(region: str = "") -> str:
        explicit = str(region or "").strip()
        if explicit:
            return explicit
        cfg = llm_backend.load_llm_config()
        return str(cfg.get("coros_region") or "").strip()

    def check_coros_auth_status(self, region: str = "") -> dict:
        """Check local COROS MCP token presence without reading token contents."""
        try:
            resolved_region = self._coros_region_from_config(region)
            status = coros_sync.check_auth_status(region=resolved_region or None)
            payload = {
                "region": status.region,
                "status": status.status,
                "token_path": status.token_path,
                "message": status.message,
                "login_command": status.login_command,
                "authorized": bool(status.ok),
                "mcp_authorized": bool(status.mcp_authorized),
                "node_available": bool(status.node_available),
                "skill_available": bool(status.skill_available),
                "node_path": status.node_path,
                "openclaw_node_binary": status.openclaw_node_binary,
                "openclaw_mjs": status.openclaw_mjs,
                "keepalive_region": status.keepalive_region,
                "keepalive_mcp_url": status.keepalive_mcp_url,
                "keepalive_token_path": status.keepalive_token_path,
                "diagnostics": status.diagnostics or [],
            }
            if status.ok:
                return _api_success(payload, msg=status.message)
            return _api_error(API_CODE_EXTERNAL_SERVICE, status.message, payload)
        except Exception:
            logger.exception("check_coros_auth_status failed")
            return _api_error(API_CODE_INTERNAL, "COROS 授权状态检查失败")

    def start_coros_login(self, region: str = "") -> dict:
        """Start the bundled COROS MCP login script; intended for explicit user action."""
        try:
            resolved_region = self._coros_region_from_config(region)
            result = coros_sync.start_login(region=resolved_region or None)
            payload = {
                "region": result.region,
                "status": result.status,
                "message": result.message,
                "command": result.command,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
            if result.ok:
                return _api_success(payload, msg=result.message)
            return _api_error(API_CODE_EXTERNAL_SERVICE, result.message, payload)
        except Exception:
            logger.exception("start_coros_login failed")
            return _api_error(API_CODE_INTERNAL, "COROS 授权启动失败")

    def set_ai_notified_hash(self, value: str) -> dict:
        """持久化通知时的目录哈希，用于重启后路径变更检测。"""
        try:
            current = llm_backend.load_llm_config()
            llm_backend.save_llm_config(
                provider=current.get("provider", ""),
                url=current.get("url", ""),
                model=current.get("model", ""),
                api_key=current.get("api_key", ""),
                agent_id=current.get("agent_id", ""),
                watch_brand=current.get("watch_brand", ""),
                local_dir=current.get("local_dir", ""),
                ai_notified=bool(current.get("ai_notified", False)),
                ai_notified_hash=str(value or ""),
                transport=current.get("transport", "http"),
                cli_type=current.get("cli_type", ""),
                cli_path=current.get("cli_path", ""),
                cli_args=current.get("cli_args", ""),
                cli_model=current.get("cli_model", ""),
                cli_timeout_sec=current.get("cli_timeout_sec", 300),
                garmin_region=current.get("garmin_region", ""),
                coros_region=current.get("coros_region", ""),
            )
            return _api_success({"ai_notified_hash": str(value or "")})
        except Exception:
            logger.exception("set_ai_notified_hash failed")
            return _api_error(API_CODE_INTERNAL, "写入 ai_notified_hash 失败")

    def ping_llm_gateway(self) -> dict:
        """TCP 存活探测：仅检测网关端口可达，不发送 LLM 消息，不创建会话。"""
        try:
            cfg = llm_backend.load_llm_config()
            url = str(cfg.get("url", "")).strip()
            if not url:
                return _api_error(API_CODE_VALIDATION, "网关地址未配置")
            parsed = urlparse(url)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            sock = socket.create_connection((host, port), timeout=3)
            sock.close()
            return _api_success({"reachable": True, "host": host, "port": port})
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            return _api_success({"reachable": False, "error": str(e)})
        except Exception:
            logger.exception("ping_llm_gateway failed")
            return _api_error(API_CODE_INTERNAL, "网关探测异常")

    def save_llm_config(
        self,
        provider: str,
        url: str,
        model: str,
        api_key: str,
        agent_id: str = "",
        watch_brand: str = "",
        local_dir: str = "",
        transport: str = "http",
        cli_type: str = "",
        cli_path: str = "",
        cli_args: str = "",
        cli_model: str = "",
        cli_timeout_sec: int = 300,
        garmin_region: str = "",
        coros_region: str = "",
    ) -> dict:
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

    def test_llm_config(
        self,
        provider: str,
        url: str,
        model: str,
        api_key: str,
        agent_id: str = "",
        watch_brand: str = "",
        transport: str = "http",
        cli_type: str = "",
        cli_path: str = "",
        cli_args: str = "",
        cli_model: str = "",
        cli_timeout_sec: int = 300,
        garmin_region: str = "",
        coros_region: str = "",
    ) -> dict:
        """【测试即保存配置-稳定性加固版】严格实行先测试、后持久化策略，保障状态机最终一致性。"""
        try:
            transport_mode = llm_backend._normalize_transport(transport)
            current = llm_backend.load_llm_config()
            effective_key = api_key or (current.get("api_key") or "").strip()

            if transport_mode == "cli":
                cli_type_clean = llm_backend._normalize_cli_type(cli_type)
                if not cli_type_clean:
                    return _api_error(API_CODE_VALIDATION, "请选择 CLI 类型后再测试连接")
                if cli_type_clean == "custom" and not str(cli_path or "").strip():
                    return _api_error(API_CODE_VALIDATION, "请先填写自定义 CLI 路径")
                messages = [
                    {"role": "system", "content": "你只需要用中文回复：连接成功。"},
                    {"role": "user", "content": "请回复连接成功"},
                ]
                if cli_type_clean == "openclaw":
                    messages = [{"role": "user", "content": "请只回复这四个字：连接成功"}]
                text = llm_backend.generate_text(
                    config={
                        "transport": "cli",
                        "provider": provider,
                        "model": model,
                        "agent_id": agent_id,
                        "cli_type": cli_type_clean,
                        "cli_path": cli_path,
                        "cli_args": cli_args,
                        "cli_model": cli_model,
                        "cli_timeout_sec": cli_timeout_sec,
                    },
                    messages=messages,
                    session_id=f"llm_config_test_{int(time.time() * 1000)}",
                    timeout=30,
                )
            else:
                # CONTRACT §2.1 / §7.2: 显式校验必填参数 url / model，禁止静默用 DEFAULT_URL 走 localhost。
                url_stripped = (url or "").strip()
                model_stripped = (model or "").strip()
                if not url_stripped or not model_stripped:
                    return _api_error(API_CODE_VALIDATION, "请先填写 API 接口地址和模型名，再点击测试连接")

                # 当 api_key 为空时，复用已存储的密钥（前端不会持有明文 key，这是安全设计）
                # 1. 先发起真实的接口网络活性探测（防污染核心）
                text = llm_backend.test_llm_connection(
                    provider=provider,
                    url=url,
                    model=model,
                    api_key=effective_key,
                    agent_id=agent_id,
                )

            # 2. 只有连接探测 100% 成功通车，才执行无感持久化落盘，硬锁隐藏轨迹工作区
            llm_backend.save_llm_config(
                provider=provider,
                url=url,
                model=model,
                api_key=effective_key,
                agent_id=agent_id,
                watch_brand=watch_brand,
                local_dir=TRACKS_DIR,
                ai_notified=bool(current.get("ai_notified", False)),
                ai_notified_hash=str(current.get("ai_notified_hash", "")),
                transport=transport_mode,
                cli_type=cli_type,
                cli_path=cli_path,
                cli_args=cli_args,
                cli_model=cli_model,
                cli_timeout_sec=cli_timeout_sec,
                garmin_region=garmin_region or current.get("garmin_region", ""),
                coros_region=coros_region or current.get("coros_region", ""),
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
            # 连通失败：不破坏原有旧配置，但将当前大模型连接可用状态即时标记为假（失效回滚）
            try:
                config = load_application_config()
                config["last_gateway_ok"] = False
                persist_application_config(config)
            except Exception:
                pass
            logger.warning("test_llm_config failed: %s", e)
            if llm_backend._normalize_transport(transport) == "cli":
                failure_detail = llm_backend._error_snippet(str(e))
                detail = ""
                if llm_backend._normalize_cli_type(cli_type) == "openclaw":
                    try:
                        detail = llm_backend.diagnose_openclaw_cli({
                            "transport": "cli",
                            "cli_type": cli_type,
                            "cli_path": cli_path,
                            "cli_args": cli_args,
                            "cli_model": cli_model,
                            "cli_timeout_sec": cli_timeout_sec,
                            "agent_id": agent_id,
                        })
                    except Exception:
                        detail = ""
                msg = "大模型 CLI 连接测试失败"
                if failure_detail:
                    msg += "：" + failure_detail
                if detail:
                    if failure_detail:
                        msg += "；" + detail
                    else:
                        msg += "：" + detail
                return _api_error(API_CODE_EXTERNAL_SERVICE, msg)
            return _api_error(API_CODE_EXTERNAL_SERVICE, "大模型网关连通失败")

    @staticmethod
    def _is_garmin_watch_brand(value: Any) -> bool:
        brand = str(value or "").strip().lower()
        return brand in {"garmin", "佳明"}

    def _garmin_sync_error_payload(
        self,
        *,
        provider_error_code: str,
        message: str,
        start_date: str,
        end_date: str,
        download: dict[str, Any] | None = None,
        import_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        action_hints = {
            "invalid_garmin_region": "请检查 GARMIN_REGION 配置，仅支持 cn 或 global。",
            "garmin_auth_required": "Garmin 授权不可用或已失效，请重新启动对应区域的 Garmin 授权后再同步。",
            "garmin_skill_not_found": "未找到 Garmin skill 脚本，请确认 garmin-stats 已随应用正确安装。",
            "garmin_script_failed": "请确认已完成 Garmin 授权、网络可用且 Garmin 服务未限流，然后重试。",
            "garmin_json_parse_error": "Garmin 下载脚本返回格式异常，请更新 garmin-stats skill 后重试。",
            "garmin_import_failed": "FIT 文件已下载到本地目录，但导入活动库失败，请稍后重试或使用本地导入。",
            "unknown": "Garmin 同步出现未知异常，请稍后重试。",
        }
        return {
            "provider": "garmin",
            "provider_error_code": provider_error_code,
            "action_hint": action_hints.get(provider_error_code, action_hints["unknown"]),
            "message": str(message or ""),
            "start_date": start_date,
            "end_date": end_date,
            "target_dir": TRACKS_DIR,
            "download": download,
            "import": import_result,
        }

    def _coros_sync_error_payload(
        self,
        *,
        provider_error_code: str,
        message: str,
        start_date: str,
        end_date: str,
        download: dict[str, Any] | None = None,
        import_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        action_hints = {
            "invalid_coros_region": "请检查 COROS 区域配置，仅支持 cn、us 或 eu。",
            "coros_auth_required": "COROS MCP 授权不可用或已失效，请回配置页完成 COROS 授权后再同步。",
            "coros_skill_not_found": "未找到 COROS skill 脚本，请确认 coros-stats 已随应用正确安装。",
            "coros_fit_download_failed": "COROS MCP FIT 下载失败，请确认网络可用、授权有效，并尝试缩小日期范围。",
            "coros_fit_download_limit": "COROS MCP 单次最多下载 10 个 FIT 文件，请缩小日期范围后分批同步。",
            "coros_sync_partial": "COROS FIT 部分下载或导入失败，请查看失败列表并分批重试。",
            "coros_node_missing": "未检测到 Node.js 或 coros-mcp CLI，请先完成 COROS MCP 授权环境准备。",
            "coros_import_failed": "FIT 文件已下载到本地目录，但导入活动库失败，请稍后重试或使用本地导入。",
            "unknown": "COROS 同步出现未知异常，请稍后重试。",
        }
        return {
            "provider": "coros",
            "provider_error_code": provider_error_code,
            "action_hint": action_hints.get(provider_error_code, action_hints["unknown"]),
            "message": str(message or ""),
            "start_date": start_date,
            "end_date": end_date,
            "target_dir": TRACKS_DIR,
            "download": download,
            "import": import_result,
        }

    @staticmethod
    def _llm_config_ready_error(cfg: dict) -> str | None:
        transport = llm_backend._normalize_transport((cfg or {}).get("transport"))
        if transport == "cli":
            cli_type = llm_backend._normalize_cli_type((cfg or {}).get("cli_type"))
            if not cli_type:
                return "CLI 类型未配置，请在系统配置页填写后重试"
            if cli_type == "custom" and not str((cfg or {}).get("cli_path") or "").strip():
                return "自定义 CLI 路径未配置，请在系统配置页填写后重试"
            return None
        if not str((cfg or {}).get("url") or "").strip():
            return "API 接口地址未配置，请在系统配置页填写后重试"
        if not str((cfg or {}).get("model") or "").strip():
            return "模型名未配置，请在系统配置页填写后重试"
        return None

    @staticmethod
    def _generate_llm_text(cfg: dict, messages: list[dict[str, str]], session_id: str, timeout: int = 300) -> str:
        return llm_backend.generate_text(
            config=cfg,
            messages=messages,
            session_id=session_id,
            timeout=timeout,
        )

    def call_llm(self, prompt: str, sport_type: str = "hiking") -> dict:
        """对话或路书。AI 数据边界:
           - 普通 AI 输入: _ai_snapshot (DB truth) → ai_block (system prompt)
           - 活动建议输入: _activity_advice_snapshot + 用户显式 planning context
           - 禁止: 前端 calculateStats 输出、per-point slope、request.get_json() metrics"""
        if prompt == self.FATIGUE_REVIEW_INSIGHT:
            # §5.6.2 规则 4:入口处先清空 + 刷新,所有 happy / fallback 分支前执行
            # §5.6.2 规则 6:严禁写 DB,AI 洞察只存前端内存
            self._chat_messages = []
            self._new_session_id()

            def _fr_empty(message: str, resolved_sport_type: str | None = None) -> dict:
                return _api_success({
                    "fatigue_review_insight": llm_backend.empty_fatigue_review_insight(message),
                    "sport_type": resolved_sport_type or sport_type,
                })

            activity_id = (
                _safe_int(getattr(self, "_fatigue_review_activity_id", 0))
                or self._extract_fatigue_review_activity_id(self._ai_snapshot)
            )
            if not activity_id:
                return _fr_empty("请先加载活动轨迹")

            try:
                fr_snapshot = self._build_fatigue_review_insight_snapshot(activity_id, sport_type)
                if not fr_snapshot:
                    return _fr_empty("未找到该活动记录")
                if not fr_snapshot.get("metrics"):
                    return _fr_empty("当前活动数据不足,无法生成洞察", fr_snapshot.get("sport_type"))

                cfg = llm_backend.load_llm_config()
                cfg_error = self._llm_config_ready_error(cfg)
                if cfg_error:
                    return _fr_empty(cfg_error)

                sid = self._session_id
                authoritative_sport_type = str(fr_snapshot.get("sport_type") or sport_type or "running")
                sport_cn = {
                    "running": "跑步", "trail_running": "越野跑", "treadmill_running": "跑步机",
                    "hiking": "徒步", "mountaineering": "登山",
                    "cycling": "骑行", "road_cycling": "公路骑行", "mountain_biking": "山地车",
                    "swimming": "游泳", "lap_swimming": "泳池游泳", "open_water": "公开水域游泳",
                }.get(authoritative_sport_type, authoritative_sport_type or "该运动")
                messages = llm_backend.build_fatigue_review_messages(fr_snapshot, authoritative_sport_type, sport_cn)
                text = self._generate_llm_text(
                    cfg,
                    messages=messages,
                    session_id=sid,
                )
                return _api_success({
                    "fatigue_review_insight": llm_backend.normalize_fatigue_review_json(text),
                    "sport_type": authoritative_sport_type,
                })
            except Exception as e:
                logger.warning("fatigue_review_insight failed: %s", e)
                return _fr_empty(str(e))

        if prompt == self.REPORT_ACTIVITY_ADVICE:
            # 活动建议是一次性计划上下文,必须在任何 happy / fallback 分支前隔离普通 AI 教练会话。
            self._chat_messages = []
            self._new_session_id()

            def _activity_advice_empty(message: str) -> dict:
                return {
                    "ok": True,
                    "activity_advice": llm_backend.empty_activity_advice(message),
                }

            planning_context = _parse_activity_advice_context(sport_type)
            snapshot = self._activity_advice_snapshot
            if not snapshot:
                return _activity_advice_empty("请先加载活动轨迹")

            cfg = llm_backend.load_llm_config()
            cfg_error = self._llm_config_ready_error(cfg)
            if cfg_error:
                return _activity_advice_empty(cfg_error)

            sid = self._session_id
            messages = _build_activity_advice_messages(snapshot, planning_context)
            try:
                text = self._generate_llm_text(
                    cfg,
                    messages=messages,
                    session_id=sid,
                )
            except Exception as exc:
                return _activity_advice_empty(f"LLM 调用失败: {exc}")
            return {
                "ok": True,
                "activity_advice": llm_backend.normalize_activity_advice_json(text),
            }

        cfg = llm_backend.load_llm_config()
        cfg_error = self._llm_config_ready_error(cfg)
        if cfg_error:
            return {"ok": False, "error": cfg_error}
        provider = str(cfg.get("provider") or "local_mcp")
        sid = self._session_id

        # AI 数据边界（契约总纲 §2.4）：
        #   AI 输入仅来自 _ai_snapshot (DB truth)
        #   _track_points / _track_placemarks 仅用于 UI 可视化，不进入 AI
        ai_block = _build_ai_snapshot_block(self._ai_snapshot)
        fn = self._track_filename or "轨迹"

        try:
            if prompt == self.RADAR_INSIGHT:
                # §5.4 规则 5:洞察调用后清空 + 刷新 session,避免污染 AI 教练会话
                # 必须在所有分支(happy / 降级)前执行,否则降级路径会留下旧 session
                self._chat_messages = []
                self._new_session_id()

                if not sport_type:
                    return {
                        "ok": True,
                        "radar_insight": llm_backend.empty_radar_insight("请先选择运动类型"),
                    }
                snapshot = _build_radar_insight_snapshot(sport_type)
                if not snapshot.get("metrics") or not (snapshot["metrics"].get("radar") or {}).get("dimensions"):
                    return {
                        "ok": True,
                        "radar_insight": llm_backend.empty_radar_insight("当前运动类型暂无 90 天数据"),
                    }
                messages = _build_radar_insight_messages(snapshot, sport_type)
                text = self._generate_llm_text(
                    cfg,
                    messages=messages,
                    session_id=sid,
                )
                return {
                    "ok": True,
                    "radar_insight": llm_backend.normalize_radar_insight_json(text),
                    "sport_type": sport_type,
                }

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
                text = self._generate_llm_text(
                    cfg,
                    messages=[
                        {"role": "system", "content": storage_rule},
                        {"role": "user", "content": "确认收到以上指令，仅回复OK。"},
                    ],
                    session_id=sid,
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
                text = self._generate_llm_text(
                    cfg,
                    messages=list(self._chat_messages),
                    session_id=sid,
                )
            except Exception:
                if self._chat_messages and self._chat_messages[-1].get("role") == "user":
                    self._chat_messages.pop()
                raise
            self._chat_messages.append({"role": "assistant", "content": text})
            return {"ok": True, "content": text}

        except Exception as e:
            return {"ok": False, "error": str(e)}

    def sync_remote_fit_activities(self, start_date: str = "", end_date: str = "") -> dict:
        """Download provider FIT files for a date range, then import local FIT data."""
        start_raw = str(start_date or "").strip()
        end_raw = str(end_date or "").strip()
        try:
            start_day = date.fromisoformat(start_raw)
            end_day = date.fromisoformat(end_raw)
        except ValueError:
            return _api_error(API_CODE_VALIDATION, "请选择有效的开始和结束日期")
        if start_day > end_day:
            return _api_error(API_CODE_VALIDATION, "开始日期不能晚于结束日期")

        cfg = llm_backend.load_llm_config()
        brand = str(cfg.get("watch_brand") or "").strip().lower()
        if brand not in {"garmin", "coros"}:
            return _api_error(
                API_CODE_VALIDATION,
                "当前手表品牌暂不支持按时间同步活动，请在配置页面选择佳明或高驰后重试，或使用导入本地 FIT 文件。",
            )

        def _download_has_import_candidates(summary: dict[str, Any]) -> bool:
            return int(summary.get("downloaded") or 0) > 0 or int(summary.get("skipped") or 0) > 0

        def _remote_import_skipped_result(provider_label: str) -> dict[str, Any]:
            return {
                "ok": True,
                "source_dir": str(TRACKS_DIR),
                "scanned": 0,
                "inserted": 0,
                "updated": 0,
                "skipped": 0,
                "removed": 0,
                "errors": [],
                "elapsed_sec": 0,
                "remote_import_skipped": True,
                "message": f"{provider_label} 未返回可下载的 FIT 文件，已跳过本地全目录扫描。",
            }

        if brand == "coros":
            try:
                download_summary = coros_sync.download_fit_json(
                    start_date=start_day.isoformat(),
                    end_date=end_day.isoformat(),
                    output_dir=TRACKS_DIR,
                    region=cfg.get("coros_region") or None,
                    limit=10,
                )
                logger.info(
                    "COROS remote FIT sync completed range=%s..%s dir=%s downloaded=%s skipped=%s failed=%s",
                    start_day.isoformat(),
                    end_day.isoformat(),
                    TRACKS_DIR,
                    download_summary.get("downloaded"),
                    download_summary.get("skipped"),
                    download_summary.get("failed"),
                )
                if not download_summary.get("ok", True) and int(download_summary.get("searched") or 0) > 0:
                    payload = self._coros_sync_error_payload(
                        provider_error_code="coros_fit_download_failed",
                        message="COROS 已找到活动记录，但 FIT 文件下载失败。",
                        start_date=start_day.isoformat(),
                        end_date=end_day.isoformat(),
                        download=download_summary,
                    )
                    return _api_error(API_CODE_EXTERNAL_SERVICE, payload["message"], payload)
                if not _download_has_import_candidates(download_summary):
                    import_result = _remote_import_skipped_result("COROS")
                    return _api_success({
                        "download": download_summary,
                        "import": import_result,
                        "start_date": start_day.isoformat(),
                        "end_date": end_day.isoformat(),
                        "target_dir": TRACKS_DIR,
                    })
                import_result = self.sync_local_fit_files()
                if not (isinstance(import_result, dict) and import_result.get("ok")):
                    msg = str((import_result or {}).get("error") or (import_result or {}).get("msg") or "COROS FIT 已下载，但本地导入失败")
                    payload = self._coros_sync_error_payload(
                        provider_error_code="coros_import_failed",
                        message=msg,
                        start_date=start_day.isoformat(),
                        end_date=end_day.isoformat(),
                        download=download_summary,
                        import_result=import_result if isinstance(import_result, dict) else {"ok": False, "error": msg},
                    )
                    logger.warning("COROS remote FIT sync import failed: %s", msg)
                    return _api_error(API_CODE_EXTERNAL_SERVICE, "COROS FIT 已下载，但本地导入失败", payload)
                return _api_success({
                    "download": download_summary,
                    "import": import_result,
                    "start_date": start_day.isoformat(),
                    "end_date": end_day.isoformat(),
                    "target_dir": TRACKS_DIR,
                })
            except coros_sync.CorosSyncError as e:
                payload = self._coros_sync_error_payload(
                    provider_error_code=getattr(e, "code", "coros_sync_error") or "coros_sync_error",
                    message=str(e),
                    start_date=start_day.isoformat(),
                    end_date=end_day.isoformat(),
                )
                logger.warning("sync_remote_fit_activities COROS provider failed: %s", e)
                return _api_error(API_CODE_EXTERNAL_SERVICE, str(e), payload)
            except Exception as e:
                logger.warning("sync_remote_fit_activities COROS failed: %s", e)
                payload = self._coros_sync_error_payload(
                    provider_error_code="unknown",
                    message=str(e),
                    start_date=start_day.isoformat(),
                    end_date=end_day.isoformat(),
                )
                return _api_error(API_CODE_EXTERNAL_SERVICE, str(e), payload)

        try:
            download_summary = garmin_sync.download_fit_json(
                start_date=start_day.isoformat(),
                end_date=end_day.isoformat(),
                output_dir=TRACKS_DIR,
                region=cfg.get("garmin_region") or None,
            )
            logger.info(
                "Garmin remote FIT sync completed range=%s..%s dir=%s downloaded=%s skipped=%s failed=%s",
                start_day.isoformat(),
                end_day.isoformat(),
                TRACKS_DIR,
                download_summary.get("downloaded"),
                download_summary.get("skipped"),
                download_summary.get("failed"),
            )
            if not _download_has_import_candidates(download_summary):
                import_result = _remote_import_skipped_result("Garmin")
                return _api_success({
                    "download": download_summary,
                    "import": import_result,
                    "start_date": start_day.isoformat(),
                    "end_date": end_day.isoformat(),
                    "target_dir": TRACKS_DIR,
                })
            import_result = self.sync_local_fit_files()
            if not (isinstance(import_result, dict) and import_result.get("ok")):
                msg = str((import_result or {}).get("error") or (import_result or {}).get("msg") or "Garmin FIT 已下载，但本地导入失败")
                payload = self._garmin_sync_error_payload(
                    provider_error_code="garmin_import_failed",
                    message=msg,
                    start_date=start_day.isoformat(),
                    end_date=end_day.isoformat(),
                    download=download_summary,
                    import_result=import_result if isinstance(import_result, dict) else {"ok": False, "error": msg},
                )
                logger.warning("Garmin remote FIT sync import failed: %s", msg)
                return _api_error(API_CODE_EXTERNAL_SERVICE, "Garmin FIT 已下载，但本地导入失败", payload)
            return _api_success({
                "download": download_summary,
                "import": import_result,
                "start_date": start_day.isoformat(),
                "end_date": end_day.isoformat(),
                "target_dir": TRACKS_DIR,
            })
        except garmin_sync.GarminSyncError as e:
            payload = self._garmin_sync_error_payload(
                provider_error_code=getattr(e, "code", "garmin_sync_error") or "garmin_sync_error",
                message=str(e),
                start_date=start_day.isoformat(),
                end_date=end_day.isoformat(),
            )
            logger.warning("sync_remote_fit_activities Garmin provider failed: %s", e)
            return _api_error(API_CODE_EXTERNAL_SERVICE, str(e), payload)
        except Exception as e:
            logger.warning("sync_remote_fit_activities failed: %s", e)
            payload = self._garmin_sync_error_payload(
                provider_error_code="unknown",
                message=str(e),
                start_date=start_day.isoformat(),
                end_date=end_day.isoformat(),
            )
            return _api_error(API_CODE_EXTERNAL_SERVICE, str(e), payload)

    def pick_and_import_fit_files(self) -> dict:
        """Open a local file picker and start a background FIT / ZIP import job."""
        import webview
        from webview import FileDialog

        if not webview.windows:
            return _api_error(API_CODE_INTERNAL, "窗口未就绪", {"imported": [], "errors": []})
        try:
            paths = webview.windows[0].create_file_dialog(
                FileDialog.OPEN,
                allow_multiple=True,
                file_types=("FIT or ZIP files (*.fit;*.zip)",),
            )
        except TypeError:
            paths = webview.windows[0].create_file_dialog(
                FileDialog.OPEN,
                file_types=("FIT or ZIP files (*.fit;*.zip)",),
            )
        if not paths:
            return _api_success({"cancelled": True, "imported": [], "errors": []})
        file_paths = list(paths) if isinstance(paths, (list, tuple)) else [paths]
        start_res = self.start_import_fit_files(file_paths)
        if not start_res.get("ok"):
            return start_res
        return _api_success({
            "job_id": start_res.get("job_id"),
            "already_running": bool(start_res.get("already_running")),
            "status": start_res.get("status") or {},
        })

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

    def save_skill_zip(self, skill_name: str) -> dict:
        import webview
        from webview import FileDialog

        allowed = {
            "garmin-stats": "garmin-stats.zip",
            "coros-stats": "coros-stats.zip",
        }
        filename = allowed.get(str(skill_name or "").strip())
        if not filename:
            return {"ok": False, "error": "未知的 skill 下载项"}
        src = app_base_dir() / "skills" / filename
        if not src.is_file():
            return {"ok": False, "error": f"未找到安装包：{filename}"}
        if not webview.windows:
            return {"ok": False, "error": "窗口未就绪"}

        win = webview.windows[0]
        try:
            paths = win.create_file_dialog(
                FileDialog.SAVE,
                save_filename=filename,
                file_types=("ZIP (*.zip)",),
            )
        except OSError as e:
            return {"ok": False, "error": str(e)}

        if not paths:
            return {"ok": False, "cancelled": True}

        dest = Path(paths[0] if isinstance(paths, (list, tuple)) else paths)
        if dest.suffix.lower() != ".zip":
            dest = dest.with_suffix(".zip")
        try:
            shutil.copyfile(src, dest)
        except OSError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "path": str(dest)}

    def get_user_profile(self) -> dict:
        prof = profile_backend.get_profile()
        zones = (
            profile_backend.compute_hrr_zones(prof.resting_hr, prof.max_hr)
            if prof.resting_hr and prof.max_hr
            else []
        )
        cached = profile_backend.read_local_profile()
        metadata = profile_backend.get_profile_sync_metadata()
        cfg = llm_backend.load_llm_config()
        watch_brand = str(cfg.get("watch_brand") or "").strip().lower()
        profile_summary = profile_backend.build_profile_status_summary(watch_brand)
        return {
            "ok": True,
            "profile": prof.to_dict(),
            "hrr_zones": zones,
            **metadata,
            **profile_summary,
            "profile_sync_summary": profile_summary,
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
                    "metrics_version": None,
                    "expected_metrics_version": CURRENT_METRICS_VERSION,
                    "needs_rebuild": False,
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
            existing = profile_backend.get_profile().to_dict()
            existing.update(data or {})
            profile_backend.upsert_profile(existing)
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
            profile_summary = profile_backend.build_profile_status_summary(platform)
            return {
                "ok": True,
                "profile": prof.to_dict(),
                "hrr_zones": zones,
                **profile_backend.get_profile_sync_metadata(),
                **profile_summary,
                "profile_sync_summary": result.get("profile_sync_summary") or profile_summary,
            }
        if isinstance(result, dict):
            profile_summary = profile_backend.build_profile_status_summary(platform)
            return {
                **result,
                **profile_backend.get_profile_sync_metadata(),
                "profile_sync_summary": result.get("profile_sync_summary") or profile_summary,
            }
        return result

    def get_activity_history(self) -> dict:
        """返回按时间倒序的历史运动记录列表。"""
        try:
            history = profile_backend.get_activity_history(limit=50)
            return {"ok": True, "history": history}
        except Exception as e:
            return {"ok": False, "error": str(e)}

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

    def _workspace_track_dir(self) -> str:
        config = init_application_config()
        return str(config.get("workspace_track_abs_path") or "").strip()

    def _build_activity_list_item(self, row: dict) -> dict:
        display_type = _resolve_display_sport_type(row.get("sport_type"), row.get("sub_sport_type"))
        # V8.x 修复: distance 字段已对齐米单位, dist_km 是真公里值
        # §2.1 字段全链路可追溯: 优先 dist_km(已知正确), distance 仅做兜底
        dist_km_field = _safe_float(row.get("dist_km"))
        dist_m_field = _safe_float(row.get("distance"))
        if dist_km_field and dist_km_field > 0:
            distance_km = dist_km_field
        elif dist_m_field and dist_m_field > 0:
            distance_km = dist_m_field / 1000.0
        else:
            distance_km = 0.0
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
        water_metric_value, water_metric_label, water_metric_kind = _resolve_water_metric_for_row(
            display_type,
            sub_sport,
            swolf_raw,
            row.get("file_path"),
        )
        swolf = water_metric_value
        swolf_subtitle = water_metric_label
        display_filename = str(row.get("filename") or row.get("file_name") or "")
        row_title = str(row.get("title") or "").strip()
        title = row_title or _clean_fit_activity_title(row.get("file_name") or row.get("filename"), display_filename)
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

        gain_raw_value = _safe_float(row.get("gain_m"))
        power_raw_value = _safe_float(normalized_power) if normalized_power is not None else None
        if display_type in LIST_GAIN_ELIGIBLE_TYPES:
            gain_field_value = round(gain_raw_value, 1) if gain_raw_value is not None else None
            gain_field_display = f"{int(round(gain_field_value))} m" if gain_field_value is not None else "/"
        else:
            gain_field_value = None
            gain_field_display = "/"
        if display_type in LIST_POWER_ELIGIBLE_TYPES:
            power_field_value = round(power_raw_value, 1) if power_raw_value is not None else None
            power_field_display = f"{int(round(power_field_value))} W" if power_field_value is not None else "/"
        else:
            power_field_value = None
            power_field_display = "/"

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
            "sport_type_cn": profile_backend.translate_sport_type(display_type),
            "distance_km": round(distance_km, 2) if distance_km is not None else None,
            "duration_sec": duration_sec,
            "avg_pace_sec": avg_pace_sec,
            "avg_pace_display": avg_pace_display,
            "distance_display": distance_display,
            "avg_hr": avg_hr,
            "max_hr": max_hr,
            "calories": _safe_int(calories),
            "gain_m": gain_field_value,
            "gain_display": gain_field_display,
            "normalized_power": power_field_value,
            "normalized_power_display": power_field_display,
            "swolf": round(_safe_float(swolf), 1) if swolf is not None else None,
            "swolf_subtitle": swolf_subtitle,
            "water_metric_value": round(_safe_float(water_metric_value), 1) if water_metric_value is not None else None,
            "water_metric_label": water_metric_label,
            "water_metric_kind": water_metric_kind,
            "stroke_distance": (
                round(_safe_float(water_metric_value), 1)
                if water_metric_kind == "stroke_distance" and water_metric_value is not None
                else None
            ),
            "file_path": str(row.get("file_path") or ""),
            "region": region_raw,
            "region_display": region_raw,
            "region_status": region_status,
            "device_name": str(row.get("device_name") or "").strip(),
            "start_lat": _safe_float(row.get("start_lat")) or None,
            "start_lon": _safe_float(row.get("start_lon")) or None,
            "weather": _decode_weather_json(row.get("weather_json")),
            "weather_status": str(row.get("weather_status") or ""),
            "weather_updated_at": str(row.get("weather_updated_at") or ""),
            "weather_attempt_count": _safe_int(row.get("weather_attempt_count")),
            "weather_error": str(row.get("weather_error") or ""),
            "has_track": bool(row.get("has_track")),
            "has_local_file": bool(str(row.get("file_path") or "").strip() and os.path.exists(str(row.get("file_path") or "").strip())),
            "processing_status": str(row.get("processing_status") or "ready"),
            "processing_error": str(row.get("processing_error") or ""),
        }

    def _fetch_activity_row(self, activity_id: int) -> dict | None:
        ensure_activity_sync_schema()
        conn = profile_backend._conn()
        try:
            # 任务 2: 详情 API 按需查询,仅 SELECT 白名单列(见 DETAIL_API_REQUIRED_COLUMNS)
            # 避免 SELECT * 拉取 advanced_metrics/未消费派生列等大字段
            columns_str = ", ".join(DETAIL_API_REQUIRED_COLUMNS)
            row = conn.execute(
                f"""
                SELECT {columns_str},
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
                dedupe_index = profile_backend.load_activity_dedupe_index(conn)
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
                resolved_fit = fit_path.expanduser().resolve()
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
                    pre_filter = _filter_fit_file_before_parse(resolved_fit)
                    if pre_filter:
                        skipped += 1
                        _emit_sync_progress(
                            progress_callback,
                            stage="running",
                            current=index,
                            total=len(pending_files),
                            inserted=inserted,
                            updated=updated,
                            skipped=skipped + pre_skipped,
                            current_file=file_name,
                            message=f"已过滤健康数据 FIT {index}/{len(pending_files)}: {file_name}",
                            errors=errors[-5:],
                        )
                        continue

                    activity = _parse_fit_activity_for_sync(resolved_fit)
                    post_filter = _filter_fit_activity_after_parse(activity, resolved_fit)
                    if post_filter:
                        skipped += 1
                        _emit_sync_progress(
                            progress_callback,
                            stage="running",
                            current=index,
                            total=len(pending_files),
                            inserted=inserted,
                            updated=updated,
                            skipped=skipped + pre_skipped,
                            current_file=file_name,
                            message=f"已过滤健康数据 FIT {index}/{len(pending_files)}: {file_name}",
                            errors=errors[-5:],
                        )
                        continue

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
                    write_res = _persist_sync_activity(activity, dedupe_index=dedupe_index)
                    if write_res.get("op") == "updated":
                        updated += 1
                    elif write_res.get("op") == "skipped":
                        if write_res.get("dedupe") == "strict_key":
                            try:
                                if resolved_fit.exists() and resolved_fit.is_file() and _is_path_under_dir(resolved_fit, Path(TRACKS_DIR).expanduser().resolve()):
                                    resolved_fit.unlink()
                            except OSError:
                                logger.warning("[dedup] duplicate FIT file cleanup failed: %s", fit_path)
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
            expanded_rows, missing_ids = _expand_activity_ids_to_duplicate_groups(conn, ids)
            rows = expanded_rows
            if not rows:
                return _api_error(
                    API_CODE_NOT_FOUND,
                    "未找到记录",
                    {"audit_id": audit_id, "missing_ids": ids, "file_errors": [], "skipped_unsafe_paths": []},
                )

            expanded_ids = sorted({int(row["id"]) for row in rows})
            duplicate_expanded_ids = sorted(set(expanded_ids) - set(ids))
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
                "expanded_duplicate_ids": duplicate_expanded_ids,
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
            # 一次性导入过多 FIT 文件会导致:
            #   1. 进程长时间阻塞(fitparse 每文件 1-3 秒,3617 个 ≈ 1-3 小时)
            #   2. 内存溢出风险
            #   3. UI 进度回调失去响应
            # 建议拆分后分批上传,或使用 sync_local_fit_files 增量扫描
            report["errors"].append({
                "error": "ZIP 成员数量超过单次上传上限",
                "code": API_CODE_VALIDATION,
                "limit": ZIP_MAX_MEMBERS,
                "actual": len(members),
                "hint": (
                    f"当前 ZIP 包含 {len(members)} 个文件,超过单次上传上限 {ZIP_MAX_MEMBERS} 个。"
                    f"建议:\n"
                    f"  1. 在文件管理器中将 ZIP 拆分为多个(每个不超过 {ZIP_MAX_MEMBERS} 个 FIT 文件),分批上传;\n"
                    f"  2. 或将 FIT 文件直接放入 TRACKS_DIR(默认 ~/.fitvault/workspace/tracks/),然后使用「扫描本地目录」功能增量导入。"
                ),
            })
            return report
        for member in members:
            entry_name = member.filename
            # T-IMPORT-FIT-DEDUP Issue B: ZIP 文件名编码兜底
            # 当 UTF-8 flag (bit 11, 0x800) 未设置 且文件名含非 ASCII 字符时,
            # 说明 Python zipfile 已按 CP437 默认解码,需要还原回原始字节并重新尝试解码。
            # 常见场景:
            #   - macOS Archive Utility: UTF-8 字节但未设 flag
            #   - Windows 资源管理器: GBK 字节,未设 flag
            #   - 7-Zip 等: 偶有不设 flag
            # 优先级: UTF-8 > GBK > Big5 > Shift_JIS (按现代系统使用率)
            if not (member.flag_bits & 0x800) and any(ord(c) > 127 for c in entry_name):
                try:
                    raw_bytes = entry_name.encode('cp437')
                except UnicodeEncodeError:
                    raw_bytes = None
                if raw_bytes is not None:
                    for _enc in ('utf-8', 'gbk', 'big5', 'shift_jis'):
                        try:
                            entry_name = raw_bytes.decode(_enc)
                            break  # 找到第一个能成功解码的编码
                        except (UnicodeDecodeError, UnicodeEncodeError):
                            continue
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


    def batch_import_tracks(self, file_paths: list[str], progress_callback=None) -> dict:
        """多模态批量导入：FIT 直接复制，ZIP 解压到 IMPORTS_DIR 后归集到 TRACKS_DIR。"""
        if not file_paths:
            return _api_error(API_CODE_VALIDATION, "未提供文件路径", {"imported": [], "errors": []})

        # 临时挂起自动监听服务，防止引发双重导入灾难
        if self._watch_service:
            self._watch_service.suspended = True

        imported: list[str] = []
        skipped: list[dict] = []
        errors: list[dict] = []
        # V10.1 健康数据过滤累计(契约 §2.2 fit_sdk 严格语义)
        health_filtered: list[dict] = []
        total = len(file_paths)
        current = 0

        def emit_progress(message: str, current_file: str = "", stage: str = "running") -> None:
            _emit_sync_progress(
                progress_callback,
                state="running",
                stage=stage,
                message=message,
                current=current,
                total=total,
                current_file=current_file,
                inserted=len(imported),
                updated=0,
                skipped=len(skipped),
                errors=errors,
            )

        try:
            emit_progress("导入任务已启动，正在准备文件...", stage="preparing")
            for fp in file_paths:
                current_dst: Path | None = None
                try:
                    src = Path(fp).expanduser().resolve()
                    if not src.is_file():
                        errors.append({"file": fp, "error": "文件不存在"})
                        current += 1
                        emit_progress(f"已跳过不存在的文件：{Path(fp).name}", Path(fp).name)
                        continue

                    if src.suffix.lower() == ".fit":
                        emit_progress(f"正在导入 {min(current + 1, total)}/{total}：{src.name}", src.name)
                        dst = Path(self.unique_fit_path(TRACKS_DIR, src.name))
                        current_dst = dst
                        shutil.copy2(str(src), str(dst))
                        emit_progress(f"正在解析 {min(current + 1, total)}/{total}：{src.name}", src.name)
                        # 手动调用单入口同步解析
                        res = _sync_single_fit_file(dst)
                        if res.get("ok"):
                            if res.get("op") == "skipped":
                                # V10.1 健康数据过滤跳过(契约 §2.2)
                                if res.get("reason") == "filtered_as_health_data":
                                    health_filtered.append({
                                        "file": str(fp),
                                        "file_size_kb": res.get("file_size_kb"),
                                        "filter_reasons": res.get("filter_reasons"),
                                    })
                                    current += 1
                                    emit_progress(f"已跳过疑似健康数据 {current}/{total}：{src.name}", src.name)
                                    continue
                                if res.get("dedupe") == "strict_key":
                                    skipped.append({
                                        "file": str(fp),
                                        "duplicate_of": res.get("activity_id"),
                                        "dedupe": "strict_key",
                                    })
                                    current += 1
                                    emit_progress(f"已跳过重复活动 {current}/{total}：{src.name}", src.name)
                                    continue
                            # T-IMPORT-FIT-DEDUP (二次扩展): FIT 分支同样用文件名 stem 覆盖 title
                            # 防止 FIT 内部 title 字段(如 GBK 误读)导致活动列表显示乱码
                            self._apply_title_override(res.get("activity_id"), dst)
                            skip_entry = self._rollback_if_semantic_duplicate(res, dst, fp)
                            if skip_entry is not None:
                                skipped.append(skip_entry)
                            else:
                                imported.append(str(dst))
                        else:
                            err_msg = str(res.get("error") or "FIT 解析失败")
                            _mark_activity_processing_failed(dst, err_msg)
                            errors.append({"file": fp, "error": err_msg})
                        current += 1
                        emit_progress(f"已处理 {current}/{total}：{src.name}", src.name)

                    elif src.suffix.lower() == ".zip":
                        emit_progress(f"正在解压 {src.name}", src.name)
                        with zipfile.ZipFile(str(src), "r") as zf:
                            extract_report = self.safe_extract_zip(zf, IMPORTS_DIR)
                        for err in extract_report.get("errors") or []:
                            errors.append({"file": fp, **err})
                        for skipped_item in extract_report.get("skipped") or []:
                            errors.append({"file": fp, **skipped_item})
                        extracted_fits = extract_report.get("extracted") or []
                        total += max(len(extracted_fits) - 1, 0)
                        emit_progress(f"已解压 {src.name}，发现 {len(extracted_fits)} 个 FIT 文件", src.name)
                        if not extracted_fits:
                            current += 1
                            emit_progress(f"已处理 {current}/{total}：{src.name}", src.name)
                        for fit_path in extracted_fits:
                            fit = Path(fit_path).expanduser().resolve()
                            if fit.suffix.lower() not in ZIP_ALLOWED_SUFFIXES or not _is_path_under_dir(fit, Path(IMPORTS_DIR).expanduser().resolve()):
                                errors.append({"file": str(fit), "error": "ZIP 解压结果不在受控导入目录或不是 FIT 文件", "code": API_CODE_VALIDATION})
                                current += 1
                                emit_progress(f"已跳过 {current}/{total}：{fit.name}", fit.name)
                                continue
                            emit_progress(f"正在导入 {min(current + 1, total)}/{total}：{fit.name}", fit.name)
                            dst = Path(self.unique_fit_path(TRACKS_DIR, fit.name))
                            current_dst = dst
                            shutil.move(str(fit), str(dst))
                            emit_progress(f"正在解析 {min(current + 1, total)}/{total}：{fit.name}", fit.name)
                            res = _sync_single_fit_file(dst)
                            if res.get("ok"):
                                if res.get("op") == "skipped":
                                    # V10.1 健康数据过滤跳过(契约 §2.2)
                                    if res.get("reason") == "filtered_as_health_data":
                                        health_filtered.append({
                                            "file": str(fit),
                                            "file_size_kb": res.get("file_size_kb"),
                                            "filter_reasons": res.get("filter_reasons"),
                                        })
                                        current += 1
                                        emit_progress(f"已跳过疑似健康数据 {current}/{total}：{fit.name}", fit.name)
                                        continue
                                    if res.get("dedupe") == "strict_key":
                                        skipped.append({
                                            "file": str(fit),
                                            "duplicate_of": res.get("activity_id"),
                                            "dedupe": "strict_key",
                                        })
                                        current += 1
                                        emit_progress(f"已跳过重复活动 {current}/{total}：{fit.name}", fit.name)
                                        continue
                                # T-IMPORT-FIT-DEDUP (二次): ZIP 分支同样覆盖 title
                                self._apply_title_override(res.get("activity_id"), dst)
                                skip_entry = self._rollback_if_semantic_duplicate(res, dst, fp)
                                if skip_entry is not None:
                                    skipped.append(skip_entry)
                                else:
                                    imported.append(str(dst))
                            else:
                                err_msg = str(res.get("error") or "FIT 解析失败")
                                _mark_activity_processing_failed(dst, err_msg)
                                errors.append({"file": str(fit), "error": err_msg})
                            current += 1
                            emit_progress(f"已处理 {current}/{total}：{fit.name}", fit.name)
                    else:
                        errors.append({"file": fp, "error": "不支持的文件格式，仅支持 .fit 和 .zip", "code": API_CODE_UNSUPPORTED_FILE})
                        current += 1
                        emit_progress(f"已跳过不支持的文件：{src.name}", src.name)
                except Exception as exc:
                    try:
                        if current_dst is not None:
                            _mark_activity_processing_failed(current_dst, str(exc))
                    except Exception:
                        pass
                    errors.append({"file": fp, "error": str(exc)})
                    current += 1
                    emit_progress(f"导入异常：{Path(fp).name}", Path(fp).name)

            return _api_success({
                "imported": imported,
                "skipped": skipped,
                # V10.1 健康数据过滤累计(契约 §2.2)
                "health_filtered": health_filtered,
                "errors": errors if errors else None,
            }, msg=f"导入完成：新增 {len(imported)} 条，跳过 {len(skipped)} 条，异常 {len(errors)} 条")

        finally:
            # 无论批量导入成功与否，无条件解除挂起锁，恢复 Watchdog 的日常静默监听
            if self._watch_service:
                self._watch_service.suspended = False

    def _apply_title_override(self, new_id: int | None, dst: Path) -> None:
        """T-IMPORT-FIT-DEDUP (二次): 用文件名 stem 覆盖 activities.title。

        防止 FIT 内部 ``basic_info.title`` 字段被 GBK 误读后写入 activities.title,
        导致活动列表显示乱码。FIT/ZIP 两条分支统一调用。

        Args:
            new_id: ``_sync_single_fit_file`` 返回的 ``activity_id``
            dst: 已归集到 TRACKS_DIR 的 FIT 文件路径
        """
        if not (new_id and dst.stem):
            return
        try:
            _conn = profile_backend._conn()
            try:
                _conn.execute(
                    "UPDATE activities SET title = ? WHERE id = ?",
                    (dst.stem, new_id),
                )
                _conn.commit()
            finally:
                _conn.close()
        except Exception as _exc:
            logging.getLogger("track_import").warning(
                "[title-override] UPDATE failed for id=%s: %s", new_id, _exc,
            )

    def _rollback_if_semantic_duplicate(self, sync_res: dict, dst: Path, src_path: str) -> dict | None:
        """T-IMPORT-FIT-DEDUP: 80 分语义查重钩子。

        在 ``_sync_single_fit_file`` 成功插入后,比对已存在的活动;
        若与某条既有记录 ``is_duplicate=True`` 且 score >= 80,则回滚
        (删除刚插入的 row 与文件),并返回 ``skipped`` 描述供上层展示。

        Args:
            sync_res: ``_sync_single_fit_file`` 的返回值,含 ``activity_id``/``activity``/``resolved``
            dst: 已复制到 TRACKS_DIR 的目标文件
            src_path: 原始文件路径(用于错误描述)

        Returns:
            命中重复时返回 ``skipped`` 字典;未命中返回 None。
        """
        new_id = sync_res.get("activity_id")
        parsed = sync_res.get("resolved") or {}
        activity_row = sync_res.get("activity") or {}
        start_time = activity_row.get("start_time") or parsed.get("start_time")
        # dist_km/duration_sec 不在 activities 行,resolved 字段名为 distance_km/duration_sec
        dist_km = parsed.get("distance_km")
        if dist_km is None:
            dist_km = parsed.get("dist_km")
        duration_sec = parsed.get("duration_sec")
        # points 由 _sync_single_fit_file 显式暴露 (T-IMPORT-FIT-DEDUP)
        points = sync_res.get("points") or []
        if not (start_time and dist_km is not None and duration_sec is not None):
            return None  # 必要字段不全,跳过查重(契约:不污染 canonical)
        try:
            dup_check = profile_backend.check_duplicate_activity(
                start_time=start_time,
                dist_km=float(dist_km),
                duration_sec=int(duration_sec),
                points_json=points,
                start_time_utc=activity_row.get("start_time_utc") or parsed.get("start_time_utc"),
            )
        except Exception as exc:
            # 查重异常不应阻塞导入(契约 §7 边界)
            logging.getLogger("track_import").warning(
                "[dedup] check_duplicate_activity raised for id=%s: %s", new_id, exc,
            )
            return None
        existing = dup_check.get("duplicate_record") or {}
        existing_id = existing.get("id")
        if not (dup_check.get("is_duplicate") and existing_id):
            return None
        if existing_id == new_id:
            # 命中的是刚插入的自己(API 无 exclude_id,只能事后过滤)
            return None
        # 命中:回滚(删除刚插入的 row + 文件)
        conn = profile_backend._conn()
        try:
            conn.execute("DELETE FROM activities WHERE id = ?", (new_id,))
            conn.commit()
        except Exception as exc:
            logging.getLogger("track_import").warning(
                "[dedup] rollback DELETE failed for id=%s: %s", new_id, exc,
            )
        finally:
            try:
                conn.close()
            except Exception:
                pass
        try:
            os.remove(str(dst))
        except OSError:
            pass
        return {
            "file": str(src_path),
            "duplicate_of": existing_id,
            "score": dup_check.get("score"),
        }

    def api_force_rebuild_radar_data(self) -> dict:
        """手动强刷 derived advanced_metrics,不触碰原始轨迹或 canonical 活动字段。"""
        try:
            res = force_rebuild_all_records(force=True)
            return _api_success({
                "message": "雷达 derived 指标重建完成，请刷新页面查看成果。",
                "rebuilt_count": int(res.get("rebuilt_count") or res.get("migrated") or 0),
                "skipped_count": int(res.get("skipped_count") or 0),
                "failed_count": int(res.get("failed_count") or 0),
                "metrics_version": CURRENT_METRICS_VERSION,
                "raw": res,
            })
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

    def start_import_fit_files(self, file_paths: list[str]) -> dict:
        paths = [str(p) for p in (file_paths or []) if str(p or "").strip()]
        if not paths:
            return _api_error(API_CODE_VALIDATION, "未提供文件路径", {"imported": [], "errors": []})
        return FIT_IMPORT_JOB_MANAGER.start(
            lambda progress_callback: self.batch_import_tracks(paths, progress_callback=progress_callback)
        )

    def get_import_fit_files_status(self, job_id: str = "") -> dict:
        return FIT_IMPORT_JOB_MANAGER.get_status(job_id)

    def _query_activity_list_records(self, sport_filter: str = "all", title_keyword: str = "") -> tuple[str, list[dict[str, Any]], list[str]]:
        try:
            ensure_activity_sync_schema()
            config = resolve_workspace_track_dir(auto_recover=True)
            source_dir = str(config.get("workspace_track_abs_path") or "")
            sport_filter = str(sport_filter or "all").strip() or "all"
            title_keyword = str(title_keyword or "").strip()[:64]

            display_sql = _activity_display_sql()
            where_parts: list[str] = []
            params: list[Any] = []
            source_where, source_params = _source_scope_filter_clause(source_dir)
            if source_where:
                where_parts.append(source_where.replace("WHERE ", "", 1))
                params.extend(source_params)
            where_parts.append("COALESCE(NULLIF(processing_status, ''), 'ready') NOT IN ('processing', 'pending')")
            if sport_filter != "all":
                where_parts.append(f"{display_sql} = ?")
                params.append(sport_filter)
            if title_keyword:
                where_parts.append("COALESCE(title, '') LIKE ? ESCAPE '\\'")
                params.append("%" + re.sub(r"([%_\\])", r"\\\1", title_keyword) + "%")
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
                           dist_km,
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
                           COALESCE(NULLIF(processing_status, ''), 'ready') AS processing_status,
                           processing_error,
                           CASE
                               WHEN TRIM(COALESCE(NULLIF(track_json, ''), NULLIF(points_json, ''), '')) NOT IN ('', '[]', '{{}}') THEN 1
                               ELSE 0
                           END AS has_track
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

    def get_activity_list_snapshot(self, sport_filter: str = "all", title_keyword: str = "") -> dict:
        """返回完整活动记录快照，供前端本地分页与筛选使用。"""
        started = time.perf_counter()
        try:
            source_dir, records, activity_types = self._query_activity_list_records(sport_filter, title_keyword)
            np_backfill = _schedule_normalized_power_backfill_if_needed()
            dynamic_columns = _resolve_activity_list_dynamic_columns_for_rows(records)
            elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
            _record_startup_event(
                "activity_list_snapshot_api",
                elapsed_ms_api=elapsed_ms,
                total=len(records),
                sport_filter=str(sport_filter or "all"),
            )
            return _api_success({
                "source_dir": source_dir,
                "total": len(records),
                "activity_types": activity_types,
                "activity_type_labels": {t: profile_backend.translate_sport_type(t) for t in activity_types},
                "page_sizes": SPORT_HUB_PAGE_SIZES,
                "records": records,
                "dynamic_columns": dynamic_columns,
                "normalized_power_backfill": np_backfill,
                "list_metric_backfill": np_backfill,
                "startup_trace": {
                    "api_elapsed_ms": elapsed_ms,
                    "process_elapsed_ms": _startup_elapsed_ms(),
                },
            })
        except Exception:
            logger.exception("get_activity_list_snapshot failed")
            return _api_error(API_CODE_DB, "活动列表快照查询失败")

    def get_activity_list(self, page: int = 1, page_size: int = 20, sport_filter: str = "all", title_keyword: str = "") -> dict:
        """后端分页返回活动记录基础字段。"""
        started = time.perf_counter()
        try:
            page = max(1, _safe_int(page, 1))
            requested_page_size = _safe_int(page_size, 20)
            page_size = requested_page_size if requested_page_size in SPORT_HUB_PAGE_SIZES else 20
            offset = (page - 1) * page_size
            db_rows, total_count = profile_backend.get_activity_list_filtered(offset, page_size, sport_filter, title_keyword=title_keyword)
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

            metric_backfill = _schedule_normalized_power_backfill_if_needed()
            elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
            _record_startup_event(
                "activity_list_api",
                elapsed_ms_api=elapsed_ms,
                page=page,
                page_size=page_size,
                total=total_count,
                sport_filter=str(sport_filter or "all"),
            )
            return _api_success({
                "page": page,
                "page_size": page_size,
                "total": total_count,
                "total_pages": total_pages,
                "activity_types": activity_types,
                "activity_type_labels": {t: profile_backend.translate_sport_type(t) for t in activity_types},
                "page_sizes": SPORT_HUB_PAGE_SIZES,
                "records": records,
                "dynamic_columns": _resolve_activity_list_dynamic_columns_for_rows(records),
                "normalized_power_backfill": metric_backfill,
                "list_metric_backfill": metric_backfill,
                "startup_trace": {
                    "api_elapsed_ms": elapsed_ms,
                    "process_elapsed_ms": _startup_elapsed_ms(),
                },
            })
        except Exception:
            logger.exception("get_activity_list failed")
            return _api_error(API_CODE_DB, "活动列表查询失败")

    def backfill_missing_weather(self, limit: int = WEATHER_BACKFILL_BATCH_LIMIT) -> dict:
        """手动触发缺失天气回填。"""
        try:
            status = _start_weather_backfill_if_needed(max(1, _safe_int(limit, WEATHER_BACKFILL_BATCH_LIMIT)), force=True)
            return _api_success({"weather_backfill": status})
        except Exception:
            logger.exception("backfill_missing_weather failed")
            return _api_error(API_CODE_DB, "天气回填启动失败")

    def get_weather_backfill_status(self) -> dict:
        try:
            return _api_success({"weather_backfill": _weather_backfill_status()})
        except Exception:
            return _api_error(API_CODE_DB, "天气回填状态查询失败")

    def get_sport_hub_activity_page(self, page: int = 1, page_size: int = 10, sport_filter: str = "all", title_keyword: str = "") -> dict:
        """个人运动数据 - 后端分页活动记录。"""
        try:
            page = max(1, _safe_int(page, 1))
            requested_page_size = _safe_int(page_size, 10)
            page_size = requested_page_size if requested_page_size in SPORT_HUB_PAGE_SIZES else 10
            offset = (page - 1) * page_size
            db_rows, total_count = profile_backend.get_activity_list_filtered(offset, page_size, sport_filter, title_keyword=title_keyword)
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

    def backfill_activity_weather(self, activity_id: int) -> dict:
        """仅为当前活动补全一次天气快照。"""
        try:
            result = _backfill_activity_weather_once(_safe_int(activity_id), force=True)
            if not result.get("ok"):
                return _api_error(
                    _safe_int(result.get("code"), API_CODE_DB),
                    str(result.get("msg") or "当前活动天气补全失败"),
                    {"status": result.get("status"), "updated": result.get("updated", False)},
                )
            row = self._fetch_activity_row(_safe_int(activity_id))
            record = _build_record_from_row(self, row, 0) if row else None
            return _api_success({
                "weather": result.get("weather"),
                "updated": result.get("updated", False),
                "status": result.get("status"),
                "record": record,
            })
        except Exception:
            logger.exception("backfill_activity_weather failed activity_id=%s", activity_id)
            return _api_error(API_CODE_DB, "当前活动天气补全失败")

    def get_fatigue_review(self, activity_id: int) -> dict:
        """V6.3 运动复盘覆盖层数据源。

        契约:fit-arch-contrac §3 响应结构 / §六 shadow_diff 隔离 / §8 只读。
        data 字段白名单(7 段):metrics / collapse_events / curves / context_tags /
        ai_insight / advice / disclaimer。前端禁止拼接 prompt,AI 洞察由
        call_llm('__FATIGUE_REVIEW_INSIGHT__', sport_type) 独立 sentinel 走专用通道。
        """
        try:
            aid = _safe_int(activity_id)
            if aid is None or aid <= 0:
                return _api_error(API_CODE_VALIDATION, "activity_id 必须为正整数")

            row = self._fetch_activity_row(aid)
            if not row:
                return _api_error(API_CODE_NOT_FOUND, "未找到该活动记录")
            processing_status = str(row.get("processing_status") or "ready").strip().lower()
            if processing_status in {"pending", "processing"}:
                return _api_error(API_CODE_VALIDATION, "复盘数据正在后台准备中，请稍后再试", {
                    "processing_status": processing_status,
                    "activity_id": aid,
                })
            if processing_status == "failed":
                return _api_error(API_CODE_VALIDATION, "该活动详细数据处理失败，暂不可复盘", {
                    "processing_status": processing_status,
                    "activity_id": aid,
                    "processing_error": str(row.get("processing_error") or ""),
                })

            # §六 shadow_diff 隔离:严禁从 _build_standard_diff 路径拉取 shadow_diff
            fr_snapshot = self._build_fatigue_review_snapshot(row)
            self._fatigue_review_activity_id = aid
            return _api_success(fr_snapshot)
        except Exception:
            logger.exception("get_fatigue_review failed activity_id=%s", activity_id)
            return _api_error(API_CODE_DB, "复盘数据查询失败")

    def _fetch_historical_metrics_avg(self, sport_type: str, current_activity_id: int, limit: int = 5) -> dict:
        """V8.2: 从 hr_curve / speed_curve 列直接计算同运动类型历史基线。

        替代 V7.6 的 storage_model 方案(V4.0 防腐层从未写入该列,V8.0 决策不补)。
        V8.2 改为读 activities 表已有列(hr_curve / speed_curve),直接用曲线统计量
        计算心率漂移和速度衰减的历史均值,作为 trend baseline。

        契约:
        - §2.1 全链路可追溯:trend 来源 = hr_curve + speed_curve(FIT 解析 → fit_sdk)
        - §8 canonical 只读:仅 SELECT,严禁 INSERT/UPDATE
        - §7.2 安全:activity_id 走 _safe_int,DB 异常降级返回 sample_size=0
        - bonk_count 暂不可计算(需 Records → Resolver→ insight_events,V8.x 扩展)
        """
        try:
            aid = _safe_int(current_activity_id) or 0
            compare_limit = _safe_int(limit) or 5
            conn = profile_backend._conn()
            try:
                rows = conn.execute(
                    """
                    SELECT id, hr_curve, speed_curve
                    FROM activities
                    WHERE sport_type = ?
                      AND (? = 0 OR id < ?)
                      AND deleted_at IS NULL
                      AND hr_curve IS NOT NULL
                      AND hr_curve != ''
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (sport_type, aid, aid, compare_limit),
                ).fetchall()
            finally:
                conn.close()

            if not rows:
                return {"hr_drift_pct": None, "decoupling_pct": None, "bonk_count": 0, "sample_size": 0}

            hr_drift_vals: list[float] = []
            decoupling_vals: list[float] = []

            for r in rows:
                hr_curve = _safe_json_list(r["hr_curve"]) or []
                speed_curve = _safe_json_list(r["speed_curve"]) or []

                # V8.2: 直接从曲线计算,不依赖 Resolver(reduce coupling)
                hr_drift = _compute_hr_drift_from_curve(hr_curve)
                if hr_drift is not None:
                    hr_drift_vals.append(hr_drift)

                speed_decay = _compute_speed_decay_from_curve(speed_curve)
                if speed_decay is not None:
                    decoupling_vals.append(speed_decay)

            return {
                "hr_drift_pct": (sum(hr_drift_vals) / len(hr_drift_vals)) if hr_drift_vals else None,
                "decoupling_pct": (sum(decoupling_vals) / len(decoupling_vals)) if decoupling_vals else None,
                "bonk_count": 0,  # V8.2: 无法从曲线列计算(V8.x 扩展)
                "sample_size": len(rows),
            }
        except Exception:
            logger.exception("_fetch_historical_metrics_avg failed")
            return {"hr_drift_pct": None, "decoupling_pct": None, "bonk_count": 0, "sample_size": 0}


    # === V7.14:21d Baseline 真实查询 + 跨周期负荷比 ===
    # 见 docs/physiology_reference.md §指标 5/7/9 + §五未来指标入源流程
    # §8 严禁写 activities 表;只读 SQL
    # §6 SQL 严禁 SELECT shadow_diff_json

    def _fetch_efficiency_trend(self, row: dict) -> dict:
        """V7.14:21d 中位数 efficiency_ratio baseline 查询。

        见 docs/physiology_reference.md §五未来指标入源流程
        返回:{"baseline_ratio": float|None, "compared_count": int, "level": str}
        """
        try:
            from profile_backend import DB_PATH
            import sqlite3
            from datetime import datetime, timedelta, timezone
            sport_type = str(row.get("sport_type") or "running")
            current_id = _safe_int(row.get("id")) or 0
            avg_hr = _safe_float(row.get("avg_hr"))
            avg_pace = _safe_float(row.get("avg_pace") or row.get("avg_pace_sec"))
            duration_sec = _safe_int(row.get("duration_sec") or row.get("duration")) or 0

            if not avg_hr or not avg_pace or duration_sec < 15 * 60:
                return {"baseline_ratio": None, "compared_count": 0, "level": "flat"}

            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()
            cutoff_ts = (datetime.now(timezone.utc) - timedelta(days=21)).isoformat()
            cursor.execute(
                """
                SELECT avg_hr, avg_pace, duration_sec
                FROM activities
                WHERE sport_type = ?
                  AND id != ?
                  AND start_time >= ?
                  AND avg_hr IS NOT NULL
                  AND avg_pace IS NOT NULL
                  AND duration_sec > ?
                ORDER BY start_time DESC
                """,
                (sport_type, current_id, cutoff_ts, 15 * 60),
            )
            rows = cursor.fetchall()
            conn.close()
        except Exception:
            return {"baseline_ratio": None, "compared_count": 0, "level": "flat"}

        ratios = []
        for h, p, _d in rows:
            if p and float(p) > 0 and h and float(h) > 0:
                speed_mps = 1000.0 / float(p)
                ratios.append(speed_mps / float(h))
        if len(ratios) < 3:  # V7.9 MIN_HISTORY = 3
            return {"baseline_ratio": None, "compared_count": len(ratios), "level": "flat"}

        ratios.sort()
        n = len(ratios)
        median = ratios[n // 2] if n % 2 == 1 else (ratios[n // 2 - 1] + ratios[n // 2]) / 2
        return {
            "baseline_ratio": round(median, 6),
            "compared_count": len(ratios),
            "level": "computed",
        }

    def _fetch_durability_trend(self, row: dict) -> dict:
        """V7.14:21d 中位数 head/tail 速度比 baseline。

        见 docs/physiology_reference.md §五未来指标入源流程
        返回:{"baseline_ratio": float|None, "compared_count": int, "level": str}
        """
        try:
            from profile_backend import DB_PATH
            import sqlite3
            import json as _json_v714
            from datetime import datetime, timedelta, timezone
            sport_type = str(row.get("sport_type") or "running")
            current_id = _safe_int(row.get("id")) or 0

            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()
            cutoff_ts = (datetime.now(timezone.utc) - timedelta(days=21)).isoformat()
            cursor.execute(
                """
                SELECT speed_curve
                FROM activities
                WHERE sport_type = ?
                  AND id != ?
                  AND start_time >= ?
                  AND speed_curve IS NOT NULL
                  AND duration_sec > ?
                ORDER BY start_time DESC
                """,
                (sport_type, current_id, cutoff_ts, 45 * 60),
            )
            rows = cursor.fetchall()
            conn.close()
        except Exception:
            return {"baseline_ratio": None, "compared_count": 0, "level": "flat"}

        ratios = []
        for (speed_curve_json,) in rows:
            try:
                speed_curve = _json_v714.loads(speed_curve_json)
            except (TypeError, ValueError):
                continue
            valid = [s for s in speed_curve if s and s > 0]
            if len(valid) < 20:
                continue
            n = len(valid)
            head_idx = max(1, int(n * 0.30))
            tail_idx = max(1, int(n * 0.30))
            head_speed = sum(valid[:head_idx]) / head_idx
            tail_speed = sum(valid[-tail_idx:]) / tail_idx
            if head_speed > 0:
                ratios.append(tail_speed / head_speed)
        if len(ratios) < 3:
            return {"baseline_ratio": None, "compared_count": len(ratios), "level": "flat"}

        ratios.sort()
        n = len(ratios)
        median = ratios[n // 2] if n % 2 == 1 else (ratios[n // 2 - 1] + ratios[n // 2]) / 2
        return {
            "baseline_ratio": round(median, 6),
            "compared_count": len(ratios),
            "level": "computed",
        }

    def _fetch_cadence_stability_trend(self, row: dict) -> dict:
        """V8.5:21d 中位数 cadence CV baseline 查询。

        算法:
          1. 查询同 sport_type 的最近 21d 活动(限 running / trail_running)
          2. 对每条活动,解析 cadence_curve → 计算 CV (std/avg * 100)
          3. 取中位数作为 baseline
          4. 返回 baseline_cv + compared_count + level

        复用 V7.9 21d baseline 模式(见 _fetch_efficiency_trend)。
        见 docs/physiology_reference.md §指标 8。

        契约:
        - §2.1 全链路可追溯:trend baseline 来源 = 21d cadence_curve
        - §8 canonical 只读:仅 SELECT
        - §6 SQL 严禁 SELECT shadow_diff_json
        """
        try:
            from profile_backend import DB_PATH
            import sqlite3
            import json as _json_v85
            from datetime import datetime, timedelta, timezone
            sport_type = str(row.get("sport_type") or "running")
            current_id = _safe_int(row.get("id")) or 0

            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()
            cutoff_ts = (datetime.now(timezone.utc) - timedelta(days=21)).isoformat()
            cursor.execute(
                """
                SELECT cadence_curve
                FROM activities
                WHERE sport_type = ?
                  AND id != ?
                  AND start_time >= ?
                  AND cadence_curve IS NOT NULL
                  AND cadence_curve != ''
                  AND duration_sec > ?
                ORDER BY start_time DESC
                """,
                (sport_type, current_id, cutoff_ts, 20 * 60),
            )
            rows = cursor.fetchall()
            conn.close()
        except Exception:
            return {"baseline_cv": None, "compared_count": 0, "level": "flat"}

        cvs: list[float] = []
        for (cadence_json,) in rows:
            try:
                cadence_stream = _json_v85.loads(cadence_json)
            except (TypeError, ValueError):
                continue
            # 复刻 V7.12 CV 计算:过滤 > 30 spm 的有效点
            valid = [c for c in cadence_stream if c and c > 30]
            if len(valid) < 20:
                continue
            avg = sum(valid) / len(valid)
            if avg <= 0:
                continue
            # stddev 简单实现(与 Resolver._stddev 一致)
            variance = sum((x - avg) ** 2 for x in valid) / len(valid)
            stddev = variance ** 0.5
            cv = (stddev / avg) * 100.0
            cvs.append(round(cv, 2))

        if len(cvs) < 3:  # V7.9 MIN_HISTORY = 3
            return {"baseline_cv": None, "compared_count": len(cvs), "level": "flat"}

        cvs.sort()
        n = len(cvs)
        median = cvs[n // 2] if n % 2 == 1 else (cvs[n // 2 - 1] + cvs[n // 2]) / 2
        return {
            "baseline_cv": round(median, 2),
            "compared_count": len(cvs),
            "level": "computed",
        }

    def _fetch_training_load_trend(self, row: dict) -> dict:
        """V8.5:21d 中位数 daily load baseline 查询。

        算法:
          1. 查询同 sport_type 的最近 21d 活动
          2. 对每条活动,解析 hr_zone_distribution → 调 _compute_training_load
          3. 失败时降级:用 avg_hr + 用户画像 HRR 推算主要 zone weight
          4. 取中位数 load 作为 baseline

        复用 V7.9 21d baseline 模式 + V7.13 训练负荷降级路径。
        见 docs/physiology_reference.md §指标 9。

        契约:
        - §2.1 全链路可追溯:trend baseline 来源 = 21d hr_zone_distribution / avg_hr + profile HRR
        - §8 canonical 只读:仅 SELECT
        - §6 SQL 严禁 SELECT shadow_diff_json
        """
        try:
            from profile_backend import DB_PATH
            import sqlite3
            import json as _json_v85
            from datetime import datetime, timedelta, timezone
            from metrics_resolver import MetricsResolver as _MR_v85
            sport_type = str(row.get("sport_type") or "running")
            current_id = _safe_int(row.get("id")) or 0
            try:
                profile = profile_backend.get_profile()
                profile_max_hr = _safe_float(profile.max_hr) if profile and profile.max_hr else None
                profile_resting_hr = _safe_float(profile.resting_hr) if profile and profile.resting_hr else None
            except Exception:
                profile_max_hr = _safe_float(row.get("max_hr") or row.get("max_heart_rate"))
                profile_resting_hr = 60.0 if profile_max_hr else None

            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()
            cutoff_ts = (datetime.now(timezone.utc) - timedelta(days=21)).isoformat()
            cursor.execute(
                """
                SELECT hr_zone_distribution, avg_hr, duration_sec
                FROM activities
                WHERE sport_type = ?
                  AND id != ?
                  AND start_time >= ?
                  AND duration_sec > ?
                  AND avg_hr IS NOT NULL
                ORDER BY start_time DESC
                """,
                (sport_type, current_id, cutoff_ts, 5 * 60),
            )
            rows = cursor.fetchall()
            conn.close()
        except Exception:
            return {"baseline_load": None, "compared_count": 0, "level": "flat"}

        loads: list[float] = []
        for zone_json, avg_hr, dur in rows:
            hr_zone_dist = None
            if zone_json:
                try:
                    hr_zone_dist = _json_v85.loads(zone_json)
                except (TypeError, ValueError):
                    hr_zone_dist = None
            load_result = _MR_v85._compute_training_load(
                hr_zone_distribution=hr_zone_dist,
                avg_hr=float(avg_hr) if avg_hr else None,
                profile_max_hr=profile_max_hr,
                profile_resting_hr=profile_resting_hr,
                duration_sec=float(dur) if dur else 0.0,
                sport_type=sport_type,
            )
            load = load_result.get("load")
            if load is not None:
                loads.append(float(load))

        if len(loads) < 3:  # V7.9 MIN_HISTORY = 3
            return {"baseline_load": None, "compared_count": len(loads), "level": "flat"}

        loads.sort()
        n = len(loads)
        median = loads[n // 2] if n % 2 == 1 else (loads[n // 2 - 1] + loads[n // 2]) / 2
        return {
            "baseline_load": round(median, 1),
            "compared_count": len(loads),
            "level": "computed",
        }

    def _fetch_load_ratio_7d_42d(self, row: dict) -> dict:
        """V7.14:7d/42d acute/chronic training load ratio。

        行业惯例参考 Gabbett 2016 训练负荷管理:
          ratio = acute_7d / (chronic_42d / 6)
          < 0.8   → under_training
          0.8-1.3 → balanced
          1.3-1.5 → caution
          > 1.5   → danger(过度训练风险)

        见 docs/physiology_reference.md §指标 9
        返回:{"ratio": float|None, "acute_7d": float|None, "chronic_42d": float|None,
              "compared_count": int, "level": str}
        """
        try:
            from profile_backend import DB_PATH
            import sqlite3
            from datetime import datetime, timedelta, timezone
            from metrics_resolver import MetricsResolver as _MR_v714
            sport_type = str(row.get("sport_type") or "running")
            current_id = _safe_int(row.get("id")) or 0
            try:
                profile = profile_backend.get_profile()
                profile_max_hr = _safe_float(profile.max_hr) if profile and profile.max_hr else None
                profile_resting_hr = _safe_float(profile.resting_hr) if profile and profile.resting_hr else None
            except Exception:
                profile_max_hr = _safe_float(row.get("max_hr") or row.get("max_heart_rate"))
                profile_resting_hr = 60.0 if profile_max_hr else None

            # 当前活动的 load(已在 V7.13 算过,直接用;失败时 fallback 重算)
            hr_zone_dist = None
            if row.get("hr_zone_distribution"):
                try:
                    import json
                    hr_zone_dist = json.loads(row.get("hr_zone_distribution"))
                except (TypeError, ValueError):
                    hr_zone_dist = None
            duration_sec = _safe_int(row.get("duration_sec") or row.get("duration")) or 0
            current_load_result = _MR_v714._compute_training_load(
                hr_zone_distribution=hr_zone_dist,
                avg_hr=_safe_float(row.get("avg_hr")),
                profile_max_hr=profile_max_hr,
                profile_resting_hr=profile_resting_hr,
                duration_sec=float(duration_sec),
                sport_type=sport_type,
            )
            current_load = current_load_result.get("load") or 0.0

            # 7d 与 42d 历史累积 load
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()
            now = datetime.now(timezone.utc)
            cutoff_7d = (now - timedelta(days=7)).isoformat()
            cutoff_42d = (now - timedelta(days=42)).isoformat()

            def _query_period_load(cutoff_ts):
                cursor.execute(
                    """
                    SELECT avg_hr, duration_sec
                    FROM activities
                    WHERE sport_type = ?
                      AND id != ?
                      AND start_time <= ?
                      AND start_time >= ?
                      AND avg_hr IS NOT NULL
                      AND duration_sec > ?
                    """,
                    (sport_type, current_id, now.isoformat(), cutoff_ts, 5 * 60),
                )
                period_rows = cursor.fetchall()
                total = 0.0
                count = 0
                for h, d in period_rows:
                    load = _MR_v714._compute_training_load(
                        avg_hr=float(h),
                        profile_max_hr=profile_max_hr,
                        profile_resting_hr=profile_resting_hr,
                        duration_sec=float(d),
                        sport_type=sport_type,
                    )
                    if load.get("load") is not None:
                        total += load["load"]
                        count += 1
                return total, count

            chronic_42d, count_42d = _query_period_load(cutoff_42d)
            acute_7d, count_7d = _query_period_load(cutoff_7d)
            conn.close()

            # 加上当前活动 load
            total_chronic = chronic_42d + current_load
            total_acute = acute_7d + current_load

            if total_chronic <= 0 or count_42d < 3:
                return {
                    "ratio": None, "acute_7d": round(total_acute, 1),
                    "chronic_42d": round(total_chronic, 1),
                    "compared_count": count_42d, "level": "insufficient_data",
                }
            # 行业标准:chronic_avg_week = chronic_42d / 6
            # ratio = acute_7d / chronic_avg_week
            ratio = total_acute / (total_chronic / 6.0)
            ratio = round(ratio, 2)

            if ratio < 0.8:
                level = "under_training"
            elif ratio <= 1.3:
                level = "balanced"
            elif ratio <= 1.5:
                level = "caution"
            else:
                level = "danger"

            return {
                "ratio": ratio,
                "acute_7d": round(total_acute, 1),
                "chronic_42d": round(total_chronic, 1),
                "compared_count": count_42d,
                "level": level,
            }
        except Exception:
            return {
                "ratio": None, "acute_7d": None, "chronic_42d": None,
                "compared_count": 0, "level": "error",
            }

    def _empty_fatigue_review_snapshot(
        sport_type: str = "running",
        advice_text: str = "复盘快照构建失败,数据不足",
    ) -> dict:
        """V8.x 统一复盘空态兜底模板(§3 9 段白名单 + 8 维 metrics 完整)。

        修复 V4 Bug #1 / #2: 旧版 except 兜底 dict 缺 fatigue_zones / total_distance_m /
        4 个 V7.x 新指标,前端 ECharts 在降级场景下读不到完整契约。
        本函数保证: 任何降级路径(无 hr_curve / Resolver 异常 / AI 失败)
        返回结构与正常路径完全一致,前端零特殊处理。
        """
        return {
            "sport_type": sport_type,
            "metrics": {
                "hr_drift": {
                    "pct": None, "level": "unknown", "confidence": "unavailable",
                    "reasons": ["review snapshot unavailable"],
                    "trend": {"level": "flat", "compared_count": 0, "delta_pct": None, "is_improving": None, "source": "historical_avg"},
                },
                "decoupling": {
                    "pct": 0.0, "level": "unknown",
                    "trend": {"level": "flat", "compared_count": 0, "delta_pct": None, "is_improving": None, "source": "historical_avg"},
                },
                "bonk_risk": {
                    "is_at_risk": False, "confidence": "unavailable",
                    "trend": {"is_increasing": False, "compared_count": 0, "level": "flat", "source": "historical_avg"},
                },
                "events": {
                    "count": 0,
                    "trend": {"delta_count": 0, "level": "flat", "compared_count": 0, "source": "historical_avg"},
                },
                # V7.9 - V7.13 4 个新指标完整兜底
                "efficiency": {
                    "score": None, "level": "unknown", "confidence": "unavailable",
                    "delta_pct": None, "sample_size": 0,
                    **({
                        "basis": "power_hr",
                        "power_per_hr": None,
                        "avg_power": None,
                        "avg_hr": None,
                        "power_data_quality": "missing",
                    } if sport_type in _CYCLING_SPORT_TYPES else {}),
                    "reasons": ["power data unavailable: missing"] if sport_type in _CYCLING_SPORT_TYPES else ["review snapshot unavailable"],
                    "trend": {"level": "flat", "compared_count": 0, "baseline_ratio": None, "source": "v7_14_error"},
                },
                "durability": {
                    "score": None, "level": "unknown", "confidence": "unavailable",
                    "head_speed": None, "tail_speed": None,
                    **({
                        "basis": "power_retention",
                        "head_power": None,
                        "tail_power": None,
                        "power_retention_pct": None,
                        "power_points_count": 0,
                        "power_data_quality": "missing",
                    } if sport_type in _CYCLING_SPORT_TYPES else {}),
                    "reasons": ["power data unavailable: missing"] if sport_type in _CYCLING_SPORT_TYPES else ["review snapshot unavailable"],
                    "trend": {"level": "flat", "compared_count": 0, "baseline_ratio": None, "source": "v7_14_error"},
                },
                "cadence_stability": {
                    "score": None, "level": "unknown", "confidence": "unavailable",
                    "cv": None, "decay_pct": None, "is_intermittent": False, "reasons": ["review snapshot unavailable"],
                    "trend": {"level": "flat", "compared_count": 0, "is_improving": None, "baseline_cv": None, "source": "v8_5_error"},
                },
                "training_load": {
                    "load": None, "level": "unknown", "zone_used": None, "confidence": "unavailable",
                    "load_ratio": None, "ratio_7d_42d": "v7_14_error", "reasons": ["review snapshot unavailable"],
                    "trend": {"level": "flat", "compared_count": 0, "is_improving": None, "baseline_load": None, "source": "v8_5_error"},
                },
                "power_variability": {
                    "vi": None, "level": "unknown", "confidence": "unavailable",
                    "avg_power": None, "normalized_power": None,
                    "power_points_count": 0, "power_data_quality": "missing",
                    "reasons": ["power data unavailable: missing"],
                },
                "pedaling_stability": {
                    "score": None, "level": "unknown", "confidence": "unavailable",
                    "cv": None, "decay_pct": None, "avg_cadence": None,
                    "cadence_points_count": 0, "cadence_data_quality": "missing",
                    "reasons": ["cadence data unavailable: missing"],
                },
            },
            "collapse_events": [],
            "fatigue_zones": [],
            "curves": {
                "distance": [],
                "time": [],
                "efficiency": [],
                "gap": [],
                "grade": [],
                "terrain_load": [],
                "hr": [],
                "altitude": [],
                "speed": [],
                "power": [],
                "cadence": [],
                "total_distance_m": 0.0,
            },
            "summary": {
                "avg_power": None,
                "max_power": None,
                "normalized_power": None,
                "avg_cadence": None,
                "power_available": False,
                "cadence_available": False,
                "power_points_count": 0,
                "cadence_points_count": 0,
                "power_data_quality": "missing",
                "cadence_data_quality": "missing",
            },
            "display_curves": {
                "pace_sec_per_km": [],
                "pace_raw_sec_per_km": [],
                "pace_capped": [],
                "gap_pace_sec_per_km": [],
                "gap_pace_raw_sec_per_km": [],
                "gap_pace_capped": [],
            },
            "display_meta": _build_fatigue_review_display_meta(),
            "context_tags": {},
            "environment_context": _build_fatigue_review_environment_context(),
            "cycling_explanation_signals": _build_cycling_explanation_signals(
                sport_type=sport_type,
                summary={
                    "power_available": False,
                    "cadence_available": False,
                    "power_data_quality": "missing",
                    "cadence_data_quality": "missing",
                },
                curves_snapshot={},
            ),
            "ai_insight": None,
            "advice": advice_text,
            "disclaimer": "AI 生成仅供参考 · 数据来源：FIT 解析 + 后端算法",
        }

    @staticmethod
    def _extract_fatigue_review_activity_id(snapshot: dict[str, Any] | None) -> int:
        if not isinstance(snapshot, dict):
            return 0
        for key in ("activity_id", "activityId", "id"):
            aid = _safe_int(snapshot.get(key))
            if aid:
                return aid
        for key in ("activity", "record"):
            nested = snapshot.get(key)
            if isinstance(nested, dict):
                aid = _safe_int(nested.get("activity_id") or nested.get("activityId") or nested.get("id"))
                if aid:
                    return aid
        return 0

    @staticmethod
    def _summarize_fatigue_review_curves_for_ai(curves: dict[str, Any]) -> dict[str, Any]:
        curves = curves if isinstance(curves, dict) else {}
        distance = curves.get("distance") if isinstance(curves.get("distance"), list) else []
        time_curve = curves.get("time") if isinstance(curves.get("time"), list) else []
        return {
            "distance_points_count": len(distance),
            "time_points_count": len(time_curve),
            "has_hr": bool(curves.get("hr")),
            "has_speed": bool(curves.get("speed")),
            "has_altitude": bool(curves.get("altitude")),
            "has_grade": bool(curves.get("grade")),
            "has_gap": bool(curves.get("gap")),
            "has_efficiency": bool(curves.get("efficiency")),
            "has_power": bool(curves.get("power")),
            "has_cadence": bool(curves.get("cadence")),
            "power_points_count": len(curves.get("power")) if isinstance(curves.get("power"), list) else 0,
            "cadence_points_count": len(curves.get("cadence")) if isinstance(curves.get("cadence"), list) else 0,
            "total_distance_m": _safe_float(curves.get("total_distance_m")) or 0.0,
        }

    def _build_fatigue_review_insight_snapshot(
        self,
        activity_id: int,
        sport_type: str | None = None,
    ) -> dict[str, Any]:
        """Build a compact AI-only snapshot from the authoritative review snapshot."""
        aid = _safe_int(activity_id)
        if not aid:
            return {}
        row = self._fetch_activity_row(aid)
        if not row:
            return {}
        review_snapshot = self._build_fatigue_review_snapshot(row)
        compact = {
            "activity_id": aid,
            "sport_type": review_snapshot.get("sport_type") or row.get("sport_type") or sport_type or "running",
            "metrics": review_snapshot.get("metrics") or {},
            "summary": review_snapshot.get("summary") or {},
            "fatigue_zones": review_snapshot.get("fatigue_zones") or [],
            "collapse_events": review_snapshot.get("collapse_events") or [],
            "curves_summary": self._summarize_fatigue_review_curves_for_ai(
                review_snapshot.get("curves") or {}
            ),
            "context_tags": review_snapshot.get("context_tags") or {},
            "environment_context": review_snapshot.get("environment_context") or {},
            "cycling_explanation_signals": review_snapshot.get("cycling_explanation_signals") or {},
            "advice": review_snapshot.get("advice") or "",
            "disclaimer": review_snapshot.get("disclaimer") or "",
        }
        return _strip_fatigue_review_forbidden_keys(compact)

    def _build_fatigue_review_snapshot(self, row: dict) -> dict:
        """V6.3 复盘覆盖层白名单快照(§六 shadow_diff 隔离)。

        严禁携带:shadow_diff / shadow_diff_json / diff / records 原始数据。
        7 段白名单:metrics / collapse_events / curves / context_tags / ai_insight /
        advice / disclaimer。
        """
        try:
            # V4 Bug #1 修复: 安全初始化所有可能在内部 try 块失败的变量,
            # 防止最末 return 引用未赋值变量导致 UnboundLocalError
            fatigue_zones: list = []
            gap_curve: list = []
            grade_curve: list = []
            efficiency_curve: list = []
            bonk_events: list = []
            context_tags: dict = {}
            hr_curve: list = []
            speed_curve: list = []

            # 1. 基础标量
            total_calories = _safe_float(row.get("calories")) or 0.0
            # V8.x 修复: distance 字段已对齐米单位, dist_km 是真公里值
            # §2.1 字段全链路可追溯: 优先用 dist_km * 1000(已知正确), distance 仅做兜底
            dist_km_field = _safe_float(row.get("dist_km"))
            dist_m_field = _safe_float(row.get("distance"))
            if dist_km_field and dist_km_field > 0:
                total_distance_m = dist_km_field * 1000.0
            elif dist_m_field and dist_m_field > 0:
                total_distance_m = dist_m_field
            else:
                total_distance_m = 0.0
            sport_type = str(row.get("sport_type") or "running")

            bundle = _build_fatigue_review_curve_bundle(row)
            total_distance_m = bundle.get("total_distance_m") or total_distance_m
            distance_curve_m = bundle.get("distance_curve_m") or []
            time_curve = bundle.get("time_curve_sec") or []
            altitude_curve = bundle.get("altitude_curve_m") or []
            hr_curve = bundle.get("hr_curve") or _safe_json_list(row.get("hr_curve")) or []
            speed_curve = bundle.get("speed_curve_mps") or _safe_json_list(row.get("speed_curve")) or []

            resolved_v81: dict[str, Any] = {}
            gap_curve: list[float] = []
            grade_curve: list[float] = []
            efficiency_curve: list[float] = []
            bonk_events: list[dict[str, Any]] = []
            context_tags: dict[str, str] = {}

            if bundle.get("records"):
                try:
                    resolved_v81 = _build_resolved_payload_v81(
                        bundle=bundle,
                        sport_type=sport_type,
                    )
                    distance_curve_m = resolved_v81.get("distance_curve") or distance_curve_m
                    time_curve = resolved_v81.get("time_curve") or time_curve
                    altitude_curve = resolved_v81.get("altitude_curve") or altitude_curve
                    gap_curve = resolved_v81.get("gap_curve") or []
                    grade_curve = resolved_v81.get("grade_curve") or []
                    efficiency_curve = resolved_v81.get("efficiency_curve") or []
                    bonk_events = resolved_v81.get("insight_events") or []
                    fatigue_zones = resolved_v81.get("fatigue_zones") or []  # V4.0: 从 Resolver 契约层透传
                    fatigue_zones = _filter_fatigue_zones_after_startup(
                        fatigue_zones,
                        sport_type=sport_type,
                        total_distance_m=total_distance_m,
                    )
                    fatigue_zones = _filter_trusted_fatigue_zones_for_review(
                        fatigue_zones,
                        sport_type=sport_type,
                        total_distance_m=total_distance_m,
                    )
                    fatigue_zones = _merge_fatigue_zones_for_review(fatigue_zones)
                    context_tags = resolved_v81.get("context_tags") or {}
                except Exception:
                    logger.exception(
                        "_build_fatigue_review_snapshot V8.1 Resolver 调用失败,降级空数组"
                    )

            curves_snapshot = _build_fatigue_review_curves_snapshot(
                bundle=bundle,
                resolved=resolved_v81,
            )
            axis_len = len(curves_snapshot.get("distance") or [])
            display_curves = _build_fatigue_review_display_curves(
                speed_curve=curves_snapshot.get("speed") or [],
                gap_curve=curves_snapshot.get("gap") or [],
                axis_len=axis_len,
            )
            display_meta = _build_fatigue_review_display_meta()
            distance_curve_km = curves_snapshot.get("distance") or []
            review_input_window = _build_review_input_window(
                distance_curve_km,
                sport_type=sport_type,
                total_distance_m=total_distance_m,
            )
            review_efficiency_curve = _trim_review_series_by_window(
                efficiency_curve,
                review_input_window,
                distance_curve_km,
            )
            review_speed_curve = _trim_review_series_by_window(
                _safe_json_list(row.get("speed_curve")) or [],
                review_input_window,
                distance_curve_km,
            )
            review_cadence_curve = _trim_review_series_by_window(
                _safe_json_list(row.get("cadence_curve")) or [],
                review_input_window,
                distance_curve_km,
            )

            # 4. metrics 白名单:四个核心指标
            decoupling = MetricsResolver._build_review_decoupling(review_efficiency_curve)
            decoupling_pct = _safe_float(decoupling.get("pct")) or 0.0

            bonk_risk = MetricsResolver._build_bonk_risk(
                total_calories=total_calories,
                sport_type=sport_type,
                bonk_events=bonk_events,
            )
            bonk_at_risk = bool(bonk_risk.get("is_at_risk"))

            # === V7.10 指标 6:HR Drift 真实算法(替代 V7.6 decoupling_pct 代理) ===
            # 见 docs/physiology_reference.md §指标 6
            # 注:decoupling 字段继续使用 efficiency_curve 计算的 decoupling_pct
            # hr_drift 字段改为从 hr_curve 提取 records 后用 _compute_hr_drift 计算
            try:
                from metrics_resolver import MetricsResolver as _MR_v710
                _records_v710 = _build_review_hr_drift_records(
                    hr_curve=curves_snapshot.get("hr") or [],
                    speed_curve=curves_snapshot.get("speed") or [],
                    distance_curve_km=distance_curve_km,
                    sport_type=sport_type,
                    total_distance_m=total_distance_m,
                    window=review_input_window,
                )
                _duration_v710 = _safe_int(row.get("duration_sec") or row.get("duration")) or 0
                _drift_result = _MR_v710._compute_hr_drift(
                    records=_records_v710,
                    duration_sec=float(_duration_v710),
                )
                _drift_pct = _drift_result.get("drift_pct")
                _drift_level = _drift_result.get("level", "unknown")
                _drift_confidence = _drift_result.get("confidence", "unavailable")
                _drift_reasons = _drift_result.get("reasons") or []
            except Exception:
                _drift_pct = None
                _drift_level = "unknown"
                _drift_confidence = "unavailable"
                _drift_reasons = ["hr drift calculation failed"]

            metrics = {
                "hr_drift": {
                    "pct": _drift_pct,
                    "level": _drift_level,
                    "confidence": _drift_confidence,  # V7.10 新增 confidence
                    "reasons": _drift_reasons,
                },
                "decoupling": decoupling,
                "bonk_risk": bonk_risk,
                "power_variability": {
                    "vi": None,
                    "level": "unknown",
                    "confidence": "unavailable",
                    "reasons": ["cycling power metric pending implementation"],
                },
                "pedaling_stability": {
                    "score": None,
                    "level": "unknown",
                    "confidence": "unavailable",
                    "cv": None,
                    "decay_pct": None,
                    "reasons": ["cycling cadence metric pending implementation"],
                },
            }

            # V7.6 trend 派生:挂在 metrics 子字段,不扩展 V6.3 顶级 7 段白名单
            _TREND_COMPARE_COUNT = 5
            historical_avg = self._fetch_historical_metrics_avg(
                sport_type=sport_type,
                current_activity_id=int(row.get("id", 0)) or 0,
                limit=_TREND_COMPARE_COUNT,
            )
            sample_size = historical_avg.get("sample_size", 0)

            def _trend_of(current_val, baseline_val, reverse_polarity: bool = False) -> dict:
                if sample_size < 3 or baseline_val is None or current_val is None:
                    return {"delta_pct": None, "level": "unknown", "compared_count": sample_size, "is_improving": None, "source": "historical_avg"}
                if baseline_val == 0:
                    return {"delta_pct": None, "level": "unknown", "compared_count": sample_size, "is_improving": None, "source": "historical_avg"}
                delta_pct = round((current_val - baseline_val) / baseline_val * 100.0, 2)
                if abs(delta_pct) <= 2.0:
                    level = "flat"
                elif delta_pct > 0:
                    level = "up"
                else:
                    level = "down"
                is_improving = delta_pct < 0 if reverse_polarity else delta_pct <= 0
                return {"delta_pct": delta_pct, "level": level, "compared_count": sample_size, "is_improving": is_improving, "source": "historical_avg"}

            metrics["hr_drift"]["trend"] = _trend_of(
                _drift_pct if _drift_pct is not None else 0.0,
                historical_avg.get("hr_drift_pct"),
            )
            metrics["decoupling"]["trend"] = _trend_of(decoupling_pct, historical_avg.get("decoupling_pct"), reverse_polarity=True)
            metrics["bonk_risk"]["trend"] = {
                "is_increasing": bool(bonk_at_risk) and historical_avg.get("bonk_count", 0) == 0,
                "compared_count": sample_size,
                "level": "up" if (bonk_at_risk and historical_avg.get("bonk_count", 0) == 0) else "flat",
                "source": "historical_avg",
            }
            # V7.9 指标 5:Efficiency Score(注入 metrics 子字段,不扩展 7 段顶级白名单)
            # 见 docs/physiology_reference.md §指标 5
            try:
                from metrics_resolver import (
                    MetricsResolver as _MR_efficiency,
                    evaluate_efficiency,
                )
                _eff_avg_hr = _safe_float(row.get("avg_hr"))
                _eff_avg_pace = _safe_float(row.get("avg_pace") or row.get("avg_pace_sec"))
                _eff_dur = _safe_int(row.get("duration_sec") or row.get("duration")) or 0
                # baseline 查询(用 profile_backend.DB_PATH,与项目其他读取一致)
                try:
                    from profile_backend import DB_PATH
                    _eff_baseline = _MR_efficiency._fetch_efficiency_baseline(
                        db_path=str(DB_PATH),
                        sport_type=sport_type,
                        current_activity_id=_safe_int(row.get("id")) or 0,
                    )
                except Exception:
                    _eff_baseline = {"baseline_ratio": None, "sample_size": 0}
                _eff_result = evaluate_efficiency(
                    avg_hr=_eff_avg_hr,
                    avg_pace_sec_per_km=_eff_avg_pace,
                    sport_type=sport_type,
                    duration_sec=float(_eff_dur),
                    baseline_ratio=_eff_baseline.get("baseline_ratio"),
                    sample_size=_eff_baseline.get("sample_size", 0),
                    avg_temp_c=None,
                    max_alt_m=_safe_float(row.get("max_altitude_m") or row.get("max_alt_m")),
                    hr_source="chest_strap",
                )
                metrics["efficiency"] = {
                    "score": _eff_result.get("score"),
                    "level": _eff_result.get("level"),
                    "confidence": _eff_result.get("confidence"),
                    "delta_pct": _eff_result.get("delta_pct"),
                    "sample_size": _eff_result.get("sample_size"),
                    "reasons": _review_metric_reasons(
                        "efficiency",
                        duration_sec=_safe_int(row.get("duration_sec") or row.get("duration")) or 0,
                        sport_type=sport_type,
                        avg_hr=row.get("avg_hr"),
                        avg_pace=row.get("avg_pace") or row.get("avg_pace_sec"),
                    ) if _eff_result.get("confidence") == "unavailable" else [],
                }
            except Exception:
                # V7.9:efficiency 注入失败不影响其他 metric,降级为 unavailable
                metrics["efficiency"] = {
                    "score": None,
                    "level": "unknown",
                    "confidence": "unavailable",
                    "delta_pct": None,
                    "sample_size": 0,
                    "reasons": ["efficiency calculation failed"],
                }

            # V7.14:efficiency trend 真实查询(21d baseline)
            # 见 docs/physiology_reference.md §指标 5 + §五未来指标入源流程
            try:
                _eff_trend = self._fetch_efficiency_trend(row)
                metrics["efficiency"]["trend"] = {
                    "level": _eff_trend.get("level", "flat"),
                    "compared_count": _eff_trend.get("compared_count", 0),
                    "baseline_ratio": _eff_trend.get("baseline_ratio"),
                    "source": "v7_14_baseline",
                }
            except Exception:
                metrics["efficiency"]["trend"] = {
                    "level": "flat",
                    "compared_count": 0,
                    "source": "v7_14_error",
                }

            # V7.11 指标 7:Durability Index(耐久指数)
            # 见 docs/physiology_reference.md §指标 7
            try:
                from metrics_resolver import MetricsResolver as _MR_v711
                _duration_v711 = _safe_int(row.get("duration_sec") or row.get("duration")) or 0
                # race 标志:row 可能不含,默认 False
                _is_race_v711 = bool(row.get("is_race") or row.get("is_event") or False)
                _durability_result = _MR_v711._compute_durability_index(
                    speed_stream=review_speed_curve,
                    duration_sec=float(_duration_v711),
                    sport_type=sport_type,
                    is_race=_is_race_v711,
                )
                metrics["durability"] = {
                    "score": _durability_result.get("score"),
                    "level": _durability_result.get("level"),
                    "confidence": _durability_result.get("confidence"),
                    "head_speed": _durability_result.get("head_speed"),
                    "tail_speed": _durability_result.get("tail_speed"),
                    "reasons": _review_metric_reasons(
                        "durability",
                        duration_sec=_duration_v711,
                        sport_type=sport_type,
                        speed_points=len(review_speed_curve),
                    ) if _durability_result.get("confidence") == "unavailable" else [],
                }
                # V7.14:durability trend 真实查询(21d baseline)
                # 见 docs/physiology_reference.md §指标 7 + §五未来指标入源流程
                try:
                    _dur_trend = self._fetch_durability_trend(row)
                    metrics["durability"]["trend"] = {
                        "level": _dur_trend.get("level", "flat"),
                        "compared_count": _dur_trend.get("compared_count", 0),
                        "baseline_ratio": _dur_trend.get("baseline_ratio"),
                        "source": "v7_14_baseline",
                    }
                except Exception:
                    metrics["durability"]["trend"] = {
                        "level": "flat",
                        "compared_count": 0,
                        "source": "v7_14_error",
                    }
            except Exception:
                # V7.11:durability 注入失败不影响其他 metric,降级为 unavailable
                metrics["durability"] = {
                    "score": None,
                    "level": "unknown",
                    "confidence": "unavailable",
                    "head_speed": None,
                    "tail_speed": None,
                    "reasons": ["durability calculation failed"],
                }

            # V7.12 指标 8:Cadence Stability(步频稳定性)
            # 见 docs/physiology_reference.md §指标 8
            try:
                from metrics_resolver import MetricsResolver as _MR_v712
                _duration_v712 = _safe_int(row.get("duration_sec") or row.get("duration")) or 0
                _is_intermittent_v712 = bool(row.get("is_intermittent") or False)
                _cadence_result = _MR_v712._compute_cadence_stability(
                    cadence_stream=review_cadence_curve,
                    duration_sec=float(_duration_v712),
                    sport_type=sport_type,
                    is_intermittent=_is_intermittent_v712,
                )
                metrics["cadence_stability"] = {
                    "score": _cadence_result.get("score"),
                    "level": _cadence_result.get("level"),
                    "confidence": _cadence_result.get("confidence"),
                    "cv": _cadence_result.get("cv"),
                    "decay_pct": _cadence_result.get("decay_pct"),
                    "is_intermittent": _cadence_result.get("is_intermittent"),
                    "reasons": _review_metric_reasons(
                        "cadence_stability",
                        duration_sec=_duration_v712,
                        sport_type=sport_type,
                        cadence_points=len(review_cadence_curve),
                    ) if _cadence_result.get("confidence") == "unavailable" else [],
                }
                # V8.5:21d 中位数 cadence CV baseline trend
                # 语义与 4 个老指标不同:CV 越小越稳(is_improving 方向反转)
                # 见 docs/physiology_reference.md §指标 8
                try:
                    _cad_trend = self._fetch_cadence_stability_trend(row)
                    _baseline_cv = _cad_trend.get("baseline_cv")
                    _current_cv = _cadence_result.get("cv")
                    if _baseline_cv is not None and _current_cv is not None and _baseline_cv > 0:
                        _delta_pct = round((_baseline_cv - _current_cv) / _baseline_cv * 100.0, 2)
                        # CV 下降 = 步频更稳 = improving
                        if _delta_pct > 5:
                            _cad_level, _cad_improving = "up", True
                        elif _delta_pct < -5:
                            _cad_level, _cad_improving = "down", False
                        else:
                            _cad_level, _cad_improving = "flat", None
                    else:
                        _delta_pct, _cad_level, _cad_improving = None, _cad_trend.get("level", "flat"), None
                    metrics["cadence_stability"]["trend"] = {
                        "delta_pct": _delta_pct,
                        "level": _cad_level,
                        "compared_count": _cad_trend.get("compared_count", 0),
                        "is_improving": _cad_improving,
                        "baseline_cv": _baseline_cv,
                        "source": "v8_5_21d_median_cadence_cv",
                    }
                except Exception:
                    metrics["cadence_stability"]["trend"] = {
                        "delta_pct": None,
                        "level": "flat",
                        "compared_count": 0,
                        "is_improving": None,
                        "source": "v8_5_error",
                    }
            except Exception:
                # V7.12:cadence_stability 注入失败不影响其他 metric,降级为 unavailable
                metrics["cadence_stability"] = {
                    "score": None,
                    "level": "unknown",
                    "confidence": "unavailable",
                    "cv": None,
                    "decay_pct": None,
                    "is_intermittent": False,
                    "reasons": ["cadence stability calculation failed"],
                }

            # V7.13 指标 9:Training Load(TRIMP 简化版)
            # 见 docs/physiology_reference.md §指标 9
            # §6 误用 2:跨 sport 不可比;前端显示需 sport_type 显式标注
            try:
                from metrics_resolver import MetricsResolver as _MR_v713
                # HR zone 分布(可选,row 字段 JSON 字符串;parse 失败则降级为 avg_hr 推算)
                _hr_zone_dist = None
                if row.get("hr_zone_distribution"):
                    try:
                        _hr_zone_dist = json.loads(row.get("hr_zone_distribution"))
                    except (TypeError, ValueError):
                        _hr_zone_dist = None
                _duration_v713 = _safe_int(row.get("duration_sec") or row.get("duration")) or 0
                _load_result = _MR_v713._compute_training_load(
                    hr_zone_distribution=_hr_zone_dist,
                    avg_hr=_safe_float(row.get("avg_hr")),
                    profile_max_hr=bundle.get("profile_max_hr"),
                    profile_resting_hr=bundle.get("profile_resting_hr"),
                    duration_sec=float(_duration_v713),
                    sport_type=sport_type,
                    hr_source="chest_strap",  # 简化:假设胸带
                )
                _load_reasons = []
                if _load_result.get("confidence") == "unavailable":
                    _load_reasons = _review_metric_reasons(
                        "training_load",
                        duration_sec=_duration_v713,
                        avg_hr=row.get("avg_hr"),
                        profile_max_hr=bundle.get("profile_max_hr"),
                        profile_resting_hr=bundle.get("profile_resting_hr"),
                        has_zone_distribution=bool(_hr_zone_dist),
                    ) or _load_result.get("reasons") or []
                metrics["training_load"] = {
                    "load": _load_result.get("load"),
                    "level": _load_result.get("level"),
                    "zone_used": _load_result.get("zone_used"),
                    "confidence": _load_result.get("confidence"),
                    "reasons": _load_reasons,
                    # V7.14:load_ratio = 7d/42d 真实计算(Gabbett 2016 行业惯例)
                    "load_ratio": None,
                    "ratio_7d_42d": "pending_v7_14_compute",
                }
                # V7.14:7d/42d acute/chronic 真实计算
                try:
                    _load_ratio = self._fetch_load_ratio_7d_42d(row)
                    metrics["training_load"]["load_ratio"] = _load_ratio.get("ratio")
                    metrics["training_load"]["ratio_7d_42d"] = _load_ratio.get("level")
                    metrics["training_load"]["acute_7d"] = _load_ratio.get("acute_7d")
                    metrics["training_load"]["chronic_42d"] = _load_ratio.get("chronic_42d")
                    metrics["training_load"]["ratio_compared_count"] = _load_ratio.get("compared_count")
                except Exception:
                    metrics["training_load"]["load_ratio"] = None
                    metrics["training_load"]["ratio_7d_42d"] = "v7_14_error"
                # V8.5:21d 中位数 daily load baseline trend
                # 训练负荷无统一改善方向(高/低因训练阶段而异),is_improving 留 None
                # 见 docs/physiology_reference.md §指标 9
                try:
                    _load_trend = self._fetch_training_load_trend(row)
                    _baseline_load = _load_trend.get("baseline_load")
                    _current_load = _load_result.get("load")
                    if _baseline_load is not None and _current_load is not None and _baseline_load > 0:
                        _load_delta_pct = round((_current_load - _baseline_load) / _baseline_load * 100.0, 2)
                        if _load_delta_pct > 10:
                            _load_level = "up"
                        elif _load_delta_pct < -10:
                            _load_level = "down"
                        else:
                            _load_level = "flat"
                    else:
                        _load_delta_pct, _load_level = None, _load_trend.get("level", "flat")
                    metrics["training_load"]["trend"] = {
                        "delta_pct": _load_delta_pct,
                        "level": _load_level,
                        "compared_count": _load_trend.get("compared_count", 0),
                        "is_improving": None,  # 训练负荷无统一改善方向
                        "baseline_load": _baseline_load,
                        "source": "v8_5_21d_median_daily_load",
                    }
                except Exception:
                    metrics["training_load"]["trend"] = {
                        "delta_pct": None,
                        "level": "flat",
                        "compared_count": 0,
                        "is_improving": None,
                        "source": "v8_5_error",
                    }
            except Exception:
                # V7.13:training_load 注入失败不影响其他 metric,降级为 unavailable
                metrics["training_load"] = {
                    "load": None,
                    "level": "unknown",
                    "zone_used": None,
                    "confidence": "unavailable",
                    "reasons": ["training load calculation failed"],
                    "load_ratio": None,
                    "ratio_7d_42d": "v7_14_error",
                }

            # === V4.0 防腐层:fatigue_zones 已下沉至 MetricsResolver._calculate_fatigue_zones ===
            # 旧版 V8.11 滑窗算法已删除(含 for 循环 bug 修复 + 真实 distance_curve)
            # main.py 仅作为路由网关,从 resolved_v81.get("fatigue_zones") 透传
            # 周边 metrics 白名单(decoupling / bonk_risk / events / historical_avg)完全保留

            # 6. 7 段白名单
            weather = _decode_weather_json(row.get("weather_json"))
            environment_context = _build_fatigue_review_environment_context(
                weather=weather,
                avg_temperature=bundle.get("avg_temperature"),
                context_tags=context_tags,
            )
            summary = _build_fatigue_review_summary(
                row=row,
                bundle=bundle,
                curves_snapshot=curves_snapshot,
            )
            metrics.update(_build_cycling_review_metrics(
                sport_type=sport_type,
                summary=summary,
                curves_snapshot=curves_snapshot,
                avg_hr=row.get("avg_hr"),
            ))
            cycling_explanation_signals = _build_cycling_explanation_signals(
                sport_type=sport_type,
                summary=summary,
                curves_snapshot=curves_snapshot,
                profile_ftp_watts=bundle.get("profile_ftp_watts"),
                profile_weight_kg=bundle.get("profile_weight_kg"),
                metrics=metrics,
            )
            if _is_cycling_review_sport(sport_type):
                fatigue_zones = _calibrate_cycling_fatigue_zones_for_review(
                    fatigue_zones,
                    summary=summary,
                    curves_snapshot=curves_snapshot,
                    cycling_explanation_signals=cycling_explanation_signals,
                )
            # 5. collapse_events 白名单(每条带 event_id 联动标识)
            collapse_events = _build_fatigue_review_collapse_events(
                bonk_events=bonk_events,
                fatigue_zones=fatigue_zones,
                sport_type=sport_type,
                total_distance_m=total_distance_m,
            )
            historical_bonk_count = historical_avg.get("bonk_count", 0)
            event_delta = len(collapse_events) - historical_bonk_count
            metrics["events"] = {
                "count": len(collapse_events),
                "trend": {
                    "delta_count": event_delta,
                    "level": "up" if event_delta > 0 else ("down" if event_delta < 0 else "flat"),
                    "compared_count": sample_size,
                    "source": "historical_avg",
                },
            }
            snapshot = {
                "sport_type": sport_type,
                "metrics": metrics,
                "summary": summary,
                "collapse_events": collapse_events,
                "fatigue_zones": fatigue_zones,  # V8.11: Layer 2 疲劳背景带
                "curves": curves_snapshot,
                "display_curves": display_curves,
                "display_meta": display_meta,
                "context_tags": context_tags,
                "environment_context": environment_context,
                "cycling_explanation_signals": cycling_explanation_signals,
                "ai_insight": None,
                "advice": "暂未生成",
                "disclaimer": "AI 生成仅供参考 · 数据来源：FIT 解析 + 后端算法",
            }
            return _strip_fatigue_review_forbidden_keys(snapshot)
        except Exception as e:
            logger.exception("_build_fatigue_review_snapshot failed: %s", e)
            # V4 Bug #1 / #2 修复: 统一空态兜底模板, 9 段白名单 + 8 维 metrics 完整
            # 防止前端 ECharts 在降级场景下读不到 fatigue_zones / total_distance_m / 4 个新指标
            safe_sport = "running"
            if isinstance(row, dict):
                safe_sport = row.get("sport_type") or "running"
            return self._empty_fatigue_review_snapshot(
                sport_type=safe_sport,
                advice_text=f"复盘快照构建失败,内部错误: {str(e)[:50]}",
            )

    def load_activity_track(self, activity_id: int) -> dict:
        """优先从 SQLite 的 track_json 读取轨迹，支持源文件已删除时复盘。
           Task 3.2: 同时返回权威 metrics，前端不再计算 distance/pace/elevation。"""
        try:
            row = self._fetch_activity_row(_safe_int(activity_id))
            if not row:
                return {"ok": False, "error": "未找到该活动记录"}

            # V4.0 治理: _build_activity_canonical 已下沉至 MetricsResolver
            # 完整实现见 metrics_resolver.py: MetricsResolver._build_activity_canonical
            activity_canonical = MetricsResolver._build_activity_canonical(row)

            mtdi = calculate_track_difficulty(
                dist_km=activity_canonical.get("dist_km"),
                gain_m=activity_canonical.get("gain_m"),
                max_alt_m=activity_canonical.get("max_alt_m"),
                max_single_climb_m=activity_canonical.get("max_single_climb_m"),
                sport_type=activity_canonical.get("sport_type") or "running",
            )
            activity_canonical["mtdi_score"] = mtdi["score"]
            activity_canonical["mtdi_level"] = mtdi["level"]
            activity_canonical["mtdi_level_name"] = mtdi["level_name"]

            points = self._decode_points_json(row.get("track_json") or row.get("points_json") or row.get("merged_track_json"))
            if points:
                filename = str(row.get("filename") or row.get("file_name") or "历史轨迹")
                weather = _decode_weather_json(row.get("weather_json"))
                _attach_per_point_distance(points)
                placemarks = self._load_activity_placemarks(_safe_int(row.get("id")))
                return {
                    "ok": True,
                    "filename": filename,
                    "activity": activity_canonical,
                    "data": {
                        "points": points,
                        "placemarks": placemarks,
                        "region": str(row.get("region") or "").strip(),
                        "weather": weather,
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

    def get_trace_activity_history(
        self,
        page: int = 1,
        page_size: int = 30,
        sport_filter: str = "all",
        time_filter: str = "all",
        location_filter: str = "all",
    ) -> dict:
        """返回轨迹分析工具使用的分页活动记录列表，后端驱动分页。

        §任务 3:扩展 time_filter / location_filter 后端参数(透传到 SQL),
        返回中新增 locations(地区选项,与 sport_filter 联动,与 time/location filter 独立)。
        """
        try:
            page = max(1, _safe_int(page, 1))
            page_size = max(1, min(_safe_int(page_size, 30), 100))
            offset = (page - 1) * page_size
            db_rows, total_count = profile_backend.get_activity_list_filtered(
                offset, page_size, sport_filter, gps_only=True,
                time_filter=time_filter, location_filter=location_filter,
            )
            deduped_rows = _dedupe_activity_rows(db_rows)
            records = [self._build_activity_list_item(row) for row in deduped_rows]

            for rec in records:
                rec["dist_km"] = rec.pop("distance_km", rec.get("distance_km_clean", 0))
                rec["valid"] = bool(rec.get("has_track"))
                rec["cityName"] = (rec.get("region") or "").strip() or "未知地点"
                rec["has_local_file"] = bool(str(rec.get("file_path") or "").strip())

            # total / total_pages 来自 get_activity_list_filtered 的 COUNT(*),
            # 该 COUNT(*) 与分页查询使用同一套 WHERE,严格反映筛选后总数
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

            # §任务 3:地区选项(独立于 time/location filter,与 sport_filter 联动)
            # 选址下拉是"我有活动的城市",不应随时间窗口变化而变化
            location_options = profile_backend.get_activity_location_options(
                sport_filter=sport_filter, gps_only=True,
            )

            return _api_success({
                "records": records,
                "total": total_count,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "activity_types": activity_types,
                "locations": location_options,
            })
        except Exception as e:
            logger.exception("get_trace_activity_history failed")
            return _api_error(API_CODE_DB, str(e))

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

    def _sample_thumbnail_points(self, points: list[dict], limit: int = 60) -> list[dict]:
        """活动轨迹缩略图采样(V9.x-LTTB 升级)。

        契约:fit-arch-contrac §V4.0 防腐层 / §2.1 字段全链路可追溯
        业务逻辑已下沉至 MetricsResolver._lttb_sample, 本函数仅做 1 行透传
        采样阈值从 48 提升至 60 以适配 B+ Canvas v2 真实比例渲染
        """
        return MetricsResolver._lttb_sample(points, limit)

    def _build_lap_rows(self, dist_km: float, duration_sec: int, avg_hr: int | None, base_power: int) -> list[dict]:
        """V4.0 mock 圈速数据生成器(V10.0 R-3:添加 source_type 标记)。

        ⚠️ 契约警告:fit-arch-contrac §2.2
            本函数输出 source_type="mock",**严禁进入生产 UI**。
            前端 P1-1 渲染时必须过滤掉 source_type="mock" 的圈数据。
        """
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
                "source_type": "mock",  # V10.0 R-3:对齐契约 §2.2 层级命名
            })
        return rows


def _build_real_laps_from_row(row: dict, dist_km: float = 0, duration_sec: int = 0, avg_hr = None, base_power: int = 0) -> list[dict[str, Any]]:
    """V4.0 治理: 业务逻辑已下沉至 MetricsResolver。
    完整实现见 metrics_resolver.py: MetricsResolver._build_real_laps_from_row

    V10.0 R-4 配套:为 FIT 真实圈打 source_type="fit_sdk" 标记,与契约 §2.2 层级命名对齐
    """
    return MetricsResolver._build_real_laps_from_row(row)


FULL_ACTIVITY_LAP_FALLBACK_DISPLAY_TYPES = frozenset({"hiking", "mountaineering", "walking"})

# V10.0 任务 2:户外骑行类自动切圈适用范围
# 仅 cycling / road_cycling / mountain_biking,室内骑行由智能骑行台自带切圈,
# 跑步/徒步/游泳等其他运动类型严禁进入此分支。
_AUTO_LAP_ELIGIBLE_DISPLAY_TYPES = frozenset({"cycling", "road_cycling", "mountain_biking"})
_AUTO_LAP_BUCKET_M: float = 5000.0
_AUTO_LAP_MIN_DISTANCE_KM: float = 5.0


def _build_detail_laps(api_self, row: dict, display_type: str, dist_km: float, duration_sec: int, avg_hr = None, base_power: int = 0) -> list[dict[str, Any]]:
    """详情页圈速数据契约(V10.0 升级:户外骑行支持按 5km 自动切圈)。

    优先级(V10.0 调整后):
      1. FIT 真实圈(laps_json)>= 2 圈 → 直接返回(保留 FIT 真实数据)
      2. FIT 真实圈 == 1 圈 + 非骑行类(徒步等)→ 直接返回(V4.0 既有行为)
      3. FIT 真实圈 == 1 圈 + 户外骑行类 + 距离 >= 5km + 有 points → 调用 P0-1 自动切圈
      4. FIT 真实圈 == 1 圈 + 户外骑行类 + 其他情况 → 直接返回 FIT 1 圈
      5. FIT 真实圈 == 0 圈 + 户外骑行类 + 距离 >= 5km + 有 points → 调用 P0-1 自动切圈
      6. FIT 真实圈 == 0 圈 + 徒步类 → 返回全程 1 圈汇总
      7. 其他情况(跑步、室内骑行等)→ mock fallback

    契约:fit-arch-contrac §2.1 / §2.2 / §八 8.3
      - 自动切圈结果 source_type="frontend_fallback"(V10.0 R-1 修订)
      - FIT 真实圈 source_type="fit_sdk"(V10.0 R-4)
      - mock 数据 source_type="mock"(V10.0 R-3)
      - 严禁写回 laps_json,严禁进 ai_snapshots
      - indoor_cycling 不进入自动切圈(智能骑行台自带切圈,保留原状)
      - 非骑行类的 1 圈 FIT 圈保持原 V4.0 行为直接返回(不进入自动切圈逻辑)
    """
    normalized_type = (display_type or "").strip().lower()
    real_laps = _build_real_laps_from_row(row, dist_km, duration_sec, avg_hr, base_power)

    # 多圈 FIT 真实数据:始终优先返回
    if real_laps and len(real_laps) >= 2:
        return real_laps

    # 单圈 FIT 真实数据:仅骑行类会考虑替换为自动切圈,其他运动保持原状
    if real_laps and len(real_laps) == 1:
        if normalized_type in _AUTO_LAP_ELIGIBLE_DISPLAY_TYPES and dist_km >= _AUTO_LAP_MIN_DISTANCE_KM:
            points = api_self._decode_points_json(
                row.get("track_json") or row.get("points_json") or row.get("merged_track_json")
            )
            if points and len(points) >= 2:
                synthetic = MetricsResolver._build_synthetic_laps_from_points(
                    points, normalized_type, _AUTO_LAP_BUCKET_M
                )
                if synthetic and len(synthetic) >= 1:
                    import logging
                    logging.getLogger("fitvault.laps").info(
                        "[V10.0] auto-lap cycling %s: %.2fkm → %d segments (replaced 1 FIT lap)",
                        normalized_type, dist_km, len(synthetic),
                    )
                    return synthetic
        # 非骑行类或骑行类但无 points 数据:保持 V4.0 行为
        return real_laps

    # 无 FIT 圈:骑行类尝试自动切圈
    if (
        normalized_type in _AUTO_LAP_ELIGIBLE_DISPLAY_TYPES
        and dist_km >= _AUTO_LAP_MIN_DISTANCE_KM
    ):
        points = api_self._decode_points_json(
            row.get("track_json") or row.get("points_json") or row.get("merged_track_json")
        )
        if points and len(points) >= 2:
            synthetic = MetricsResolver._build_synthetic_laps_from_points(
                points, normalized_type, _AUTO_LAP_BUCKET_M
            )
            if synthetic and len(synthetic) >= 1:
                import logging
                logging.getLogger("fitvault.laps").info(
                    "[V10.0] auto-lap cycling %s: %.2fkm → %d segments (no FIT lap)",
                    normalized_type, dist_km, len(synthetic),
                )
                return synthetic

    # 现有 fallback:徒步类返回全程 1 圈
    if normalized_type in FULL_ACTIVITY_LAP_FALLBACK_DISPLAY_TYPES:
        if dist_km <= 0 or duration_sec <= 0:
            return []
        pace_sec = _safe_int(row.get("avg_pace")) or int(round(duration_sec / max(dist_km, 0.001)))
        return [{
            "lap_no": 1,
            "distance_km": round(dist_km, 2),
            "pace_sec": pace_sec,
            "hr": avg_hr,
            "max_hr": _safe_int(row.get("max_hr")) or None,
            "ascent_m": _safe_int(row.get("gain_m")) if row.get("gain_m") is not None else None,
            "descent_m": _safe_int(row.get("total_descent_m")) if row.get("total_descent_m") is not None else None,
            "source_type": "fit_sdk",  # V10.0 R-4:徒步整段汇总也打 fit_sdk 标记
        }]

    # 现有 fallback:其他情况返回 mock(仅用于跑步、室内骑行等)
    return api_self._build_lap_rows(dist_km, duration_sec, avg_hr, base_power)


def _build_record_from_row(api_self, row: dict, idx: int) -> dict:
    points = api_self._decode_points_json(row.get("track_json") or row.get("points_json") or row.get("merged_track_json"))
    # V8.x 修复: distance 已对齐米单位, dist_km 是真公里值
    dist_km_field = _safe_float(row.get("dist_km"))
    dist_m_field = _safe_float(row.get("distance"))
    if dist_km_field and dist_km_field > 0:
        dist_km = dist_km_field
    elif dist_m_field and dist_m_field > 0:
        dist_km = dist_m_field / 1000.0
    else:
        dist_km = 0.0
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
    water_metric_value, water_metric_label, water_metric_kind = _resolve_water_metric_for_row(
        display_type,
        row.get("sub_sport_type"),
        row.get("swolf"),
        row.get("file_path"),
    )
    title = str(row.get("title") or "").strip()
    base_power = 245 + (idx % 5) * 8
    timestamp = row.get("start_time") or row.get("updated_at")

    try:
        dt = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")) if timestamp else None
        month_key = dt.strftime("%Y-%m") if dt else "--"
        date_label = dt.strftime("%Y-%m-%d") if dt else "--"
    except Exception:
        month_key = "--"
        date_label = str(timestamp or "--")

    raw_for_engine = {
        "distance_km": dist_km,
        "duration_sec": duration_sec,
        "avg_speed": (dist_km * 1000.0 / duration_sec) if dist_km > 0 and duration_sec > 0 else None,
        "avg_pace_sec": pace_sec,
        "avg_pace_display": pace_display_detail,
        "distance_display": distance_display_detail,
        "avg_hr": avg_hr,
        "max_hr": max_hr,
        "calories": calories,
        "elevation": int(row.get("gain_m") or 0),
    }

    # 任务 5 (P2-1): 能力字段判据统一——存在性而非值域
    # 原 has_elevation: bool(row.get("gain_m") and float(row.get("gain_m")) > 0)
    # 问题: gain_m=0 的平坦路段被误判为「无海拔数据」,与 has_gps/has_hr 风格不一致
    # 修复: 任一海拔字段非空即认为「有海拔数据」(4 字段交叉验证)
    # 原 has_power: 硬编码 False,所有有功率数据的活动都被错误地隐藏功率 section
    # 修复: 任一功率字段非空即认为「有功率数据」
    capabilities = {
        "has_gps": bool(points),
        "has_hr": bool(avg_hr),
        "has_elevation": any(
            row.get(field) is not None
            for field in ("gain_m", "max_alt_m", "min_alt_m", "total_descent_m")
        ),
        "has_power": bool(row.get("avg_power") or row.get("normalized_power")),
    }

    detail_laps = _build_detail_laps(api_self, row, display_type, dist_km, duration_sec, avg_hr, base_power)

    detail = {
        "display_metrics": SemanticSportsEngine.build_display_metrics(display_type, raw_for_engine),
        "layout": SemanticSportsEngine.get_layout(display_type),
        "capabilities": capabilities,
        "summary": raw_for_engine,
        "laps": detail_laps,
        # V9.4.4:圈速表列真理源(后端决定,前端不再硬编码 if/else)
        "lap_columns": resolve_detail_lap_columns(display_type, detail_laps),
        "thumbnail_points": api_self._sample_thumbnail_points(points),
        # V9.4.4:Training Effect 派生(契约 §2.2 路径 record.detail.training_effect)
        # 真理源:FIT session.total_training_effect / total_anaerobic_training_effect
        #   (Garmin Firstbeat 私有算法,fitparse 已应用 scale 0.1 → 0.0~5.0)
        # 双字段都 None → 走概览页占位卡(不重算 Firstbeat 私有算法)
        "training_effect": build_training_effect(
            {
                "aerobic_training_effect": row.get("aerobic_training_effect"),
                "anaerobic_training_effect": row.get("anaerobic_training_effect"),
            },
            display_type,
        ),
        # V_ENV.1.16:环境挑战派生(契约 docs/environment_challenge_v1_contract §1.1)
        # 数据源:DB row.gain_m / max_alt_m / avg_temperature / weather_json
        # 真理源:_build_environment_challenge_block(metrics_resolver L3212)
        # §五 5.3:不进 AI snapshot;§六 审计字段隔离:本块不读 shadow_diff_json
        "environment_challenge": _build_environment_challenge_block(
            sm={
                "total_ascent": _safe_float(row.get("gain_m")),
                "distance_km": dist_km,
                "max_altitude_m": _safe_float(row.get("max_alt_m")),
            },
            sport_type=display_type,
            avg_temp=_safe_float(row.get("avg_temperature")) or None,
            raw={"weather": _decode_weather_json(row.get("weather_json")) or {}},
            meta={},
        ),
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
        "sport_type_cn": profile_backend.translate_sport_type(display_type),
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
        "swolf": round(_safe_float(water_metric_value), 1) if water_metric_value is not None else None,
        "swolf_subtitle": water_metric_label,
        "water_metric_value": round(_safe_float(water_metric_value), 1) if water_metric_value is not None else None,
        "water_metric_label": water_metric_label,
        "water_metric_kind": water_metric_kind,
        "stroke_distance": (
            round(_safe_float(water_metric_value), 1)
            if water_metric_kind == "stroke_distance" and water_metric_value is not None
            else None
        ),
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
        "processing_status": str(row.get("processing_status") or "ready"),
        "processing_error": str(row.get("processing_error") or ""),
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
                       sport_type, sub_sport_type, COALESCE(distance, dist_km) AS distance, dist_km,
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


def _api_find_gpx_pollution(self) -> dict:
    """审计接口: 返回当前 DB 中 GPX/KML 残留污染。"""
    try:
        return profile_backend.find_gpx_pollution()
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _api_import_track(self, file_path: str = "", duplicate_action: str = "", new_filename: str = "") -> dict:
    """GPX/KML 临时轨迹导入入口。

    契约 §二 §八：GPX/KML 是用后即抛型文件，不进 canonical DB。
    本接口仅解析并返回内存数据，不写 activities 表，不拷贝文件到 TRACKS_DIR。
    duplicate_action / new_filename 保留参数签名兼容，实际不持久化无意义。
    """
    import webview
    from webview import FileDialog

    target_path = (file_path or "").strip()
    if not target_path:
        if not webview.windows:
            return {"ok": False, "error": "窗口未就绪"}
        paths = webview.windows[0].create_file_dialog(
            FileDialog.OPEN,
            file_types=("Track files (*.gpx;*.kml)",),
        )
        if not paths:
            return {"ok": False, "cancelled": True}
        target_path = paths[0] if isinstance(paths, (list, tuple)) else paths
    if Path(target_path).suffix.lower() not in (".gpx", ".kml"):
        return {"ok": False, "error": "仅支持导入 GPX/KML 轨迹文件，请选择 .gpx 或 .kml 格式的轨迹文件"}
    try:
        # §二 §八：GPX/KML 只解析不持久化 — 不写 activities 表，不拷贝文件
        return profile_backend.parse_route_for_preview(target_path, resolve_region=False)
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _api_resolve_preview_region(self, lat, lon) -> dict:
    """临时轨迹地区查询入口：只读写 geocode_cache，不写 activities。"""
    try:
        fields = profile_backend.resolve_preview_region(lat, lon)
        return {"ok": True, "region": fields}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _api_choose_gpx_track_file(self) -> dict:
    """仅打开 GPX/KML 文件选择器，不做解析，避免文件选择阶段显示任务加载层。"""
    import webview
    from webview import FileDialog

    try:
        if not webview.windows:
            return {"ok": False, "error": "窗口未就绪"}
        paths = webview.windows[0].create_file_dialog(
            FileDialog.OPEN,
            file_types=("Track files (*.gpx;*.kml)",),
        )
        if not paths:
            return {"ok": False, "cancelled": True}
        target_path = paths[0] if isinstance(paths, (list, tuple)) else paths
        if Path(target_path).suffix.lower() not in (".gpx", ".kml"):
            return {"ok": False, "error": "仅支持导入 GPX/KML 轨迹文件，请选择 .gpx 或 .kml 格式的轨迹文件"}
        return {"ok": True, "file_path": str(target_path)}
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
        profile_backend._assert_gpx_not_persisted(data)  # §二 §八: API 入口拒绝 GPX/KML
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


def _api_cleanup_duplicate_activities(self, dry_run: bool = True) -> dict:
    try:
        return _api_success(profile_backend.cleanup_duplicate_activities(dry_run=bool(dry_run)))
    except Exception as e:
        logger.exception("cleanup_duplicate_activities failed")
        return _api_error(API_CODE_DB, "清理重复活动失败", {"error": str(e)})


Api._build_results_payload = _api_build_results_payload
Api._build_honors_payload = _api_build_honors_payload
Api.get_person_sport_hub_data = _api_get_person_sport_hub_data
Api.load_local_track = _api_load_local_track
Api.get_activity_by_file_path = _api_get_activity_by_file_path
Api.load_activity_track_by_file_path = _api_load_activity_track_by_file_path
Api.choose_gpx_track_file = _api_choose_gpx_track_file
Api.import_track = _api_import_track
Api.resolve_preview_region = _api_resolve_preview_region
Api.find_gpx_pollution = _api_find_gpx_pollution
Api.update_activity_sport_type = _api_update_activity_sport_type
Api.validate_fit_directory = _api_validate_fit_directory
Api.scan_fit_directory = _api_scan_fit_directory
Api.check_duplicate_track = _api_check_duplicate_track
Api.save_activity = _api_save_activity
Api.cleanup_duplicate_activities = _api_cleanup_duplicate_activities


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


def force_rebuild_all_records(force: bool = True) -> dict[str, Any]:
    """Safely rebuild derived advanced_metrics without touching canonical activity data."""
    ensure_activity_sync_schema()
    conn = profile_backend._conn()
    try:
        rows = conn.execute(
            """
            SELECT id, track_json, points_json, sport_type, advanced_metrics
            FROM activities
            WHERE deleted_at IS NULL
              AND (track_json IS NOT NULL AND track_json != '')
            ORDER BY id ASC
            """
        ).fetchall()
        if not rows:
            logger.info("全量重建: 无活动记录需要处理")
            _set_schema_version(CURRENT_SCHEMA_VERSION)
            return {
                "ok": True,
                "rebuilt_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
                "metrics_version": CURRENT_METRICS_VERSION,
                "migrated": 0,
                "total": 0,
            }

        logger.info("全量重建: 开始处理 %s 条记录...", len(rows))
        rebuilt_count = 0
        skipped_count = 0
        failed_count = 0
        for row in rows:
            row = dict(row)
            try:
                if not force and not needs_advanced_metrics_rebuild(row.get("advanced_metrics")):
                    skipped_count += 1
                    continue
                track_json = row.get("track_json") or row.get("points_json")
                if not track_json:
                    skipped_count += 1
                    continue
                track_data = json.loads(track_json) if isinstance(track_json, str) else track_json
                if not isinstance(track_data, list) or len(track_data) < 2:
                    skipped_count += 1
                    continue
                advanced = _compute_advanced_metrics(track_data, row.get("sport_type"))
                if advanced:
                    advanced_json = json.dumps(advanced, ensure_ascii=False)
                    conn.execute(
                        "UPDATE activities SET advanced_metrics = ?, updated_at = datetime('now') WHERE id = ?",
                        (advanced_json, int(row["id"])),
                    )
                    rebuilt_count += 1
                    if rebuilt_count % 10 == 0:
                        conn.commit()
                else:
                    skipped_count += 1
            except Exception as exc:
                logger.warning("全量重建: 记录 id=%s 计算失败: %s", row.get("id"), exc)
                failed_count += 1
                continue
        conn.commit()
        logger.info("全量重建完成: 成功重建 %s / %s 条记录", rebuilt_count, len(rows))
        _set_schema_version(CURRENT_SCHEMA_VERSION)
        return {
            "ok": True,
            "rebuilt_count": rebuilt_count,
            "skipped_count": skipped_count,
            "failed_count": failed_count,
            "metrics_version": CURRENT_METRICS_VERSION,
            "migrated": rebuilt_count,
            "total": len(rows),
        }
    except Exception as e:
        conn.rollback()
        logger.exception("全量重建失败: %s", e)
        return {
            "ok": False,
            "error": str(e),
            "rebuilt_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "metrics_version": CURRENT_METRICS_VERSION,
            "migrated": 0,
        }
    finally:
        conn.close()


def main() -> None:
    import webview

    _record_startup_event("main_enter")
    set_runtime_app_icon()
    local_version = _get_schema_version()
    if local_version < CURRENT_SCHEMA_VERSION:
        logger.info("Schema 版本升级: %s -> %s，触发增量数据清洗", local_version, CURRENT_SCHEMA_VERSION)
        force_rebuild_all_records()
    else:
        logger.info("Schema 版本一致 (v=%s)，跳过数据清洗", local_version)
    url = str(html_file().resolve())
    api = Api()
    _record_startup_event("api_created")
    window = webview.create_window(
        f"脉图 - FitVault {APP_VERSION}",
        url=url,
        js_api=api,
        width=1280,
        height=800,
        min_size=(800, 600),
        hidden=True,
        frameless=(sys.platform == "darwin"),
        easy_drag=False,
        draggable=True,
        background_color='#061626',  # 匹配启动图主背景色，降低原生窗口预绘制闪烁
    )
    _record_startup_event("window_created")
    api.bind_window(window)
    try:
        window.events.loaded += api.on_loaded
    except Exception as exc:
        logger.debug("绑定窗口 loaded 事件失败: %s", exc)
    watch_service = FITFolderWatchService(api)
    api.set_watch_service(watch_service)
    watch_service.start()
    _record_startup_event("watch_service_started")
    try:
        _record_startup_event("webview_start_enter")
        webview.start(debug=False)
    finally:
        _APP_SHUTTING_DOWN.set()
        watch_service.stop()


def run_garmin_login_cli(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] != "--garmin-login":
        return 1
    login_script = app_base_dir() / "skills" / "garmin-stats" / "scripts" / "login.py"
    if not login_script.is_file():
        print(f"未找到 Garmin 登录脚本: {login_script}", file=sys.stderr)
        return 2
    old_argv = sys.argv[:]
    scripts_dir = str(login_script.parent)
    inserted_path = False
    try:
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
            inserted_path = True
        sys.argv = [str(login_script), *args[1:]]
        runpy.run_path(str(login_script), run_name="__main__")
        return 0
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        print(str(code), file=sys.stderr)
        return 1
    finally:
        sys.argv = old_argv
        if inserted_path:
            try:
                sys.path.remove(scripts_dir)
            except ValueError:
                pass


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--garmin-login":
        raise SystemExit(run_garmin_login_cli(sys.argv[1:]))
    init_application_config()
    main()
