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
import copy
import hashlib
import json
import logging
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import profile_backend

logger = logging.getLogger(__name__)

CAREER_SCHEMA_VERSION = "2026-07-14.records-v2.10"
CAREER_SCHEMA_ENSURE_LOCK = threading.RLock()
CAREER_DEFAULT_SCHEMA_READY = False
CAREER_DEFAULT_SCHEMA_READY_PATH = ""

CAREER_BUSINESS_TABLES = (
    "career_race_events",
    "career_pb_records",
    "career_achievement_events",
    "career_memory_items",
    "career_snapshots",
    "career_ai_insights",
    "career_event_candidates",
)

CAREER_EMPTY_STATUS_MESSAGE = "运动生涯数据将在赛事、PB 与成就解析后生成"
CAREER_TIMELINE_EMPTY_STATUS_MESSAGE = "时间轴将在 ACS 派生事件生成后展示"
CAREER_RACES_EMPTY_STATUS_MESSAGE = "赛事档案将在 Race Resolver 识别正式赛事后展示"
CAREER_RACES_READY_STATUS_MESSAGE = "赛事档案已生成"
CAREER_RACE_MAP_EMPTY_STATUS_MESSAGE = "赛事足迹将在有赛事与安全起点坐标后展示"
CAREER_RACE_MAP_READY_STATUS_MESSAGE = "赛事足迹已生成"
CAREER_FOOTPRINT_EMPTY_STATUS_MESSAGE = "生涯足迹将在有可靠地区信息后展示"
CAREER_FOOTPRINT_READY_STATUS_MESSAGE = "生涯足迹已生成"
CAREER_PB_EMPTY_STATUS_MESSAGE = "PB 记录将在 PB Resolver 识别后展示"
CAREER_PB_READY_STATUS_MESSAGE = "PB 记录已生成"
CAREER_ACHIEVEMENTS_EMPTY_STATUS_MESSAGE = "成就档案将在 Achievement Resolver 识别后展示"
CAREER_ACHIEVEMENTS_READY_STATUS_MESSAGE = "成就档案已生成"
CAREER_CANDIDATES_EMPTY_STATUS_MESSAGE = "暂无待确认候选事件"
CAREER_CANDIDATES_READY_STATUS_MESSAGE = "候选事件已生成"
CAREER_MEMORY_GALLERY_EMPTY_STATUS_MESSAGE = "赛事相册将在赛事活动生成后展示"
CAREER_MEMORY_GALLERY_READY_STATUS_MESSAGE = "赛事相册已生成"
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
CAREER_YEAR_SNAPSHOT_VERSION = "acs.year.v2"
CAREER_YEAR_SNAPSHOT_SCOPE = "year"
CAREER_YEAR_MIN = 1900
CAREER_YEAR_MAX = 2100
CAREER_YEAR_SNAPSHOT_TOP_LEVEL_FIELDS = (
    "snapshot_version",
    "scope",
    "year",
    "period",
    "summary",
    "sport_breakdown",
    "month_digest",
    "evidence_catalog",
    "highlight_moments",
    "city_moments",
    "comparison",
    "data_quality",
    "source_fingerprint",
)
CAREER_YEAR_SNAPSHOT_ACTIVITY_FIELDS = (
    "activity_id",
    "date",
    "sport",
    "sport_label",
    "distance_km",
    "duration_seconds",
    "city",
)
CAREER_YEAR_SNAPSHOT_RESOLVER_FIELDS = (
    "evidence_id",
    "activity_id",
    "type",
    "title",
    "date",
    "value",
)
CAREER_YEAR_SNAPSHOT_FORBIDDEN_KEYS = CAREER_SNAPSHOT_FORBIDDEN_KEYS | {
    "absolute_path",
    "access_token",
    "api_key",
    "authorization",
    "auth_token",
    "career_memory_items",
    "database",
    "derivatives",
    "fit_file",
    "llm_config",
    "media",
    "memory" + "_count",
    "memory_items",
    "metadata_json",
    "photo",
    "preview_url",
    "provider",
    "provider_token",
    "raw_fit",
    "representative" + "_memories",
    "sql",
    "story",
    "story_text",
    "token",
}
CAREER_AI_INSIGHT_CONTENT_FORBIDDEN_KEYS = CAREER_YEAR_SNAPSHOT_FORBIDDEN_KEYS - {"detail_link"}
CAREER_YEAR_SNAPSHOT_FIELD_SCHEMA = {
    "snapshot_version": {"type": "str", "value": CAREER_YEAR_SNAPSHOT_VERSION},
    "scope": {"type": "str", "value": CAREER_YEAR_SNAPSHOT_SCOPE},
    "year": {"type": "int", "range": [CAREER_YEAR_MIN, CAREER_YEAR_MAX]},
    "period": {
        "type": "object",
        "fields": ("start_date", "end_date", "as_of_date", "data_through", "is_partial_year", "latest_activity_date"),
        "nullable_fields": ("data_through", "latest_activity_date"),
    },
    "summary": {
        "type": "object",
        "fields": (
            "activity_count",
            "total_distance_km",
            "total_duration_seconds",
            "race_count",
            "pb_count",
            "achievement_count",
            "covered_city_count",
        ),
        "numeric_precision": {"km": 1, "seconds": 0, "counts": 0},
    },
    "sport_breakdown": {"type": "list", "sort": "sport asc", "numeric_precision": {"km": 1, "seconds": 0}},
    "month_digest": {"type": "list", "sort": "month asc", "months": [1, 12], "numeric_precision": {"km": 1, "seconds": 0}},
    "evidence_catalog": {"type": "list", "sort": "date asc + type asc + evidence_id asc"},
    "highlight_moments": {"type": "list", "sort": "rank asc + date asc + id asc"},
    "city_moments": {"type": "list", "sort": "activity_count desc + first_date asc + city asc"},
    "comparison": {
        "type": "object",
        "fields": (
            "status",
            "reason",
            "comparison_year",
            "period_mode",
            "activity_count_delta",
            "distance_km_delta",
            "duration_seconds_delta",
            "race_count_delta",
            "pb_count_delta",
        ),
        "nullable_fields": (
            "reason",
            "activity_count_delta",
            "distance_km_delta",
            "duration_seconds_delta",
            "race_count_delta",
            "pb_count_delta",
        ),
    },
    "data_quality": {"type": "object", "fields": ("status", "warnings")},
    "source_fingerprint": {"type": "str", "format": "sha256:{hex}"},
}
CAREER_YEAR_FINGERPRINT_EXCLUDED_KEYS = {
    "source_fingerprint",
    "generated_at",
    "as_of_date",
    "traceId",
    "trace_id",
    "status_message",
    "message",
    "log",
    "logs",
    "prompt_version",
    "model_version",
    "model_id",
    "ui_state",
}
CAREER_YEAR_REPORT_STATES = (
    "no_data",
    "not_generated",
    "ready",
    "stale",
    "generating",
    "failed",
    "ai_unavailable",
)
CAREER_YEAR_SNAPSHOT_TYPE = "career_year"
CAREER_AI_INSIGHT_SCOPE_YEAR = "career_year"
CAREER_AI_INSIGHT_STATUSES = (
    "candidate",
    "ready",
    "superseded",
    "failed",
)
CAREER_YEAR_AI_REPORT_SCHEMA_VERSION = "acs.year.report.v3"
CAREER_YEAR_AI_SECTION_ORDER = ("annual_story", "races", "progress", "footprints", "rhythm", "comparison")
CAREER_YEAR_AI_UNKNOWN_EVIDENCE_FAILURE_THRESHOLD = 2
CAREER_YEAR_GENERATION_FLIGHT_LOCK = threading.Lock()
CAREER_YEAR_GENERATION_FLIGHTS: dict[tuple[str, str, str, str], dict[str, Any]] = {}
CAREER_YEAR_CITY_CULTURE_HINTS = {
    "成都": "火锅",
    "成都市": "火锅",
    "神户": "和牛",
    "神户市": "和牛",
    "北京": "胡同和中轴线",
    "北京市": "胡同和中轴线",
    "上海": "江边和城市夜色",
    "上海市": "江边和城市夜色",
    "杭州": "西湖",
    "杭州市": "西湖",
}

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
    "road_cycling",
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

CAREER_FOOTPRINT_CHINA_COUNTRY_ALIASES = {
    "中国",
    "中华人民共和国",
    "中国大陆",
    "大陆",
    "china",
    "cn",
    "prc",
    "台湾",
    "台灣",
    "taiwan",
    "香港",
    "hong kong",
    "澳门",
    "澳門",
    "macau",
    "macao",
}

CAREER_FOOTPRINT_CHINA_REGION_SPECS = (
    ("CN-BJ", "北京", ("北京", "北京市", "beijing")),
    ("CN-TJ", "天津", ("天津", "天津市", "tianjin")),
    ("CN-HE", "河北", ("河北", "河北省", "hebei")),
    ("CN-SX", "山西", ("山西", "山西省", "shanxi")),
    ("CN-NM", "内蒙古", ("内蒙古", "内蒙古自治区", "neimenggu", "inner mongolia")),
    ("CN-LN", "辽宁", ("辽宁", "辽宁省", "liaoning")),
    ("CN-JL", "吉林", ("吉林", "吉林省", "jilin")),
    ("CN-HL", "黑龙江", ("黑龙江", "黑龙江省", "heilongjiang")),
    ("CN-SH", "上海", ("上海", "上海市", "shanghai")),
    ("CN-JS", "江苏", ("江苏", "江苏省", "jiangsu")),
    ("CN-ZJ", "浙江", ("浙江", "浙江省", "zhejiang")),
    ("CN-AH", "安徽", ("安徽", "安徽省", "anhui")),
    ("CN-FJ", "福建", ("福建", "福建省", "fujian")),
    ("CN-JX", "江西", ("江西", "江西省", "jiangxi")),
    ("CN-SD", "山东", ("山东", "山东省", "shandong")),
    ("CN-HA", "河南", ("河南", "河南省", "henan")),
    ("CN-HB", "湖北", ("湖北", "湖北省", "hubei")),
    ("CN-HN", "湖南", ("湖南", "湖南省", "hunan")),
    ("CN-GD", "广东", ("广东", "广东省", "guangdong")),
    ("CN-GX", "广西", ("广西", "广西壮族自治区", "guangxi")),
    ("CN-HI", "海南", ("海南", "海南省", "hainan")),
    ("CN-CQ", "重庆", ("重庆", "重庆市", "chongqing")),
    ("CN-SC", "四川", ("四川", "四川省", "sichuan")),
    ("CN-GZ", "贵州", ("贵州", "贵州省", "guizhou")),
    ("CN-YN", "云南", ("云南", "云南省", "yunnan")),
    ("CN-XZ", "西藏", ("西藏", "西藏自治区", "tibet", "xizang")),
    ("CN-SN", "陕西", ("陕西", "陕西省", "shaanxi")),
    ("CN-GS", "甘肃", ("甘肃", "甘肃省", "gansu")),
    ("CN-QH", "青海", ("青海", "青海省", "qinghai")),
    ("CN-NX", "宁夏", ("宁夏", "宁夏回族自治区", "ningxia")),
    ("CN-XJ", "新疆", ("新疆", "新疆维吾尔自治区", "xinjiang")),
    ("CN-TW", "台湾", ("台湾", "台灣", "台湾省", "台灣省", "taiwan", "taipei", "台北")),
    ("CN-HK", "香港", ("香港", "香港特别行政区", "hong kong")),
    ("CN-MO", "澳门", ("澳门", "澳門", "澳门特别行政区", "macau", "macao")),
)

CAREER_FOOTPRINT_CITY_REGION_HINTS = {
    "北京": ("CN-BJ", "北京"),
    "北京市": ("CN-BJ", "北京"),
    "上海": ("CN-SH", "上海"),
    "上海市": ("CN-SH", "上海"),
    "天津": ("CN-TJ", "天津"),
    "重庆": ("CN-CQ", "重庆"),
    "成都": ("CN-SC", "四川"),
    "成都市": ("CN-SC", "四川"),
    "都江堰": ("CN-SC", "四川"),
    "都江堰市": ("CN-SC", "四川"),
    "雅安": ("CN-SC", "四川"),
    "雅安市": ("CN-SC", "四川"),
    "名山": ("CN-SC", "四川"),
    "名山区": ("CN-SC", "四川"),
    "杭州": ("CN-ZJ", "浙江"),
    "杭州市": ("CN-ZJ", "浙江"),
    "苏州": ("CN-JS", "江苏"),
    "苏州市": ("CN-JS", "江苏"),
    "常州": ("CN-JS", "江苏"),
    "常州市": ("CN-JS", "江苏"),
    "广州": ("CN-GD", "广东"),
    "广州市": ("CN-GD", "广东"),
    "深圳": ("CN-GD", "广东"),
    "台北": ("CN-TW", "台湾"),
    "台北市": ("CN-TW", "台湾"),
    "臺北": ("CN-TW", "台湾"),
    "臺北市": ("CN-TW", "台湾"),
}

CAREER_FOOTPRINT_COUNTRY_SPECS = {
    "us": ("US", "美国"),
    "usa": ("US", "美国"),
    "united states": ("US", "美国"),
    "united states of america": ("US", "美国"),
    "美国": ("US", "美国"),
    "jp": ("JP", "日本"),
    "japan": ("JP", "日本"),
    "日本": ("JP", "日本"),
    "fr": ("FR", "法国"),
    "france": ("FR", "法国"),
    "法国": ("FR", "法国"),
    "gb": ("GB", "英国"),
    "uk": ("GB", "英国"),
    "united kingdom": ("GB", "英国"),
    "英国": ("GB", "英国"),
    "de": ("DE", "德国"),
    "germany": ("DE", "德国"),
    "德国": ("DE", "德国"),
    "au": ("AU", "澳大利亚"),
    "australia": ("AU", "澳大利亚"),
    "澳大利亚": ("AU", "澳大利亚"),
    "sg": ("SG", "新加坡"),
    "singapore": ("SG", "新加坡"),
    "新加坡": ("SG", "新加坡"),
    "it": ("IT", "意大利"),
    "italy": ("IT", "意大利"),
    "意大利": ("IT", "意大利"),
    "es": ("ES", "西班牙"),
    "spain": ("ES", "西班牙"),
    "西班牙": ("ES", "西班牙"),
    "nl": ("NL", "荷兰"),
    "netherlands": ("NL", "荷兰"),
    "holland": ("NL", "荷兰"),
    "荷兰": ("NL", "荷兰"),
    "gr": ("GR", "希腊"),
    "greece": ("GR", "希腊"),
    "希腊": ("GR", "希腊"),
    "ca": ("CA", "加拿大"),
    "canada": ("CA", "加拿大"),
    "加拿大": ("CA", "加拿大"),
    "za": ("ZA", "南非"),
    "south africa": ("ZA", "南非"),
    "南非": ("ZA", "南非"),
    "th": ("TH", "泰国"),
    "thailand": ("TH", "泰国"),
    "泰国": ("TH", "泰国"),
    "泰國": ("TH", "泰国"),
    "vn": ("VN", "越南"),
    "vietnam": ("VN", "越南"),
    "越南": ("VN", "越南"),
    "my": ("MY", "马来西亚"),
    "malaysia": ("MY", "马来西亚"),
    "马来西亚": ("MY", "马来西亚"),
    "馬來西亞": ("MY", "马来西亚"),
    "id": ("ID", "印度尼西亚"),
    "indonesia": ("ID", "印度尼西亚"),
    "印度尼西亚": ("ID", "印度尼西亚"),
    "印尼": ("ID", "印度尼西亚"),
    "ph": ("PH", "菲律宾"),
    "philippines": ("PH", "菲律宾"),
    "菲律宾": ("PH", "菲律宾"),
    "菲律賓": ("PH", "菲律宾"),
    "kh": ("KH", "柬埔寨"),
    "cambodia": ("KH", "柬埔寨"),
    "柬埔寨": ("KH", "柬埔寨"),
    "la": ("LA", "老挝"),
    "laos": ("LA", "老挝"),
    "老挝": ("LA", "老挝"),
    "mm": ("MM", "缅甸"),
    "myanmar": ("MM", "缅甸"),
    "burma": ("MM", "缅甸"),
    "缅甸": ("MM", "缅甸"),
    "bn": ("BN", "文莱"),
    "brunei": ("BN", "文莱"),
    "文莱": ("BN", "文莱"),
}

CAREER_FOOTPRINT_US_REGION_SPECS = (
    ("US-AK", "阿拉斯加州", ("阿拉斯加州", "阿拉斯加", "alaska")),
    ("US-AL", "亚拉巴马州", ("亚拉巴马州", "亚拉巴马", "alabama")),
    ("US-AR", "阿肯色州", ("阿肯色州", "阿肯色", "arkansas")),
    ("US-AZ", "亚利桑那州", ("亚利桑那州", "亚利桑那", "arizona")),
    ("US-CA", "加利福尼亚州", ("加利福尼亚州", "加利福尼亚", "california", "加州")),
    ("US-CO", "科罗拉多州", ("科罗拉多州", "科罗拉多", "colorado")),
    ("US-CT", "康涅狄格州", ("康涅狄格州", "康涅狄格", "connecticut")),
    ("US-DC", "华盛顿哥伦比亚特区", ("华盛顿哥伦比亚特区", "哥伦比亚特区", "district of columbia", "washington dc", "washington d.c.", "华盛顿特区")),
    ("US-DE", "特拉华州", ("特拉华州", "特拉华", "delaware")),
    ("US-FL", "佛罗里达州", ("佛罗里达州", "佛罗里达", "florida")),
    ("US-GA", "佐治亚州", ("佐治亚州", "佐治亚", "georgia")),
    ("US-HI", "夏威夷州", ("夏威夷州", "夏威夷", "hawaii")),
    ("US-IA", "艾奥瓦州", ("艾奥瓦州", "艾奥瓦", "iowa")),
    ("US-ID", "爱达荷州", ("爱达荷州", "爱达荷", "idaho")),
    ("US-IL", "伊利诺伊州", ("伊利诺伊州", "伊利诺伊", "illinois")),
    ("US-IN", "印第安纳州", ("印第安纳州", "印第安纳", "indiana")),
    ("US-KS", "堪萨斯州", ("堪萨斯州", "堪萨斯", "kansas")),
    ("US-KY", "肯塔基州", ("肯塔基州", "肯塔基", "kentucky")),
    ("US-LA", "路易斯安那州", ("路易斯安那州", "路易斯安那", "louisiana")),
    ("US-MA", "马萨诸塞州", ("马萨诸塞州", "马萨诸塞", "massachusetts")),
    ("US-MD", "马里兰州", ("马里兰州", "马里兰", "maryland")),
    ("US-ME", "缅因州", ("缅因州", "缅因", "maine")),
    ("US-MI", "密歇根州", ("密歇根州", "密歇根", "michigan")),
    ("US-MN", "明尼苏达州", ("明尼苏达州", "明尼苏达", "minnesota")),
    ("US-MO", "密苏里州", ("密苏里州", "密苏里", "missouri")),
    ("US-MS", "密西西比州", ("密西西比州", "密西西比", "mississippi")),
    ("US-MT", "蒙大拿州", ("蒙大拿州", "蒙大拿", "montana")),
    ("US-NC", "北卡罗来纳州", ("北卡罗来纳州", "北卡罗来纳", "north carolina")),
    ("US-ND", "北达科他州", ("北达科他州", "北达科他", "north dakota")),
    ("US-NE", "内布拉斯加州", ("内布拉斯加州", "内布拉斯加", "nebraska")),
    ("US-NH", "新罕布什尔州", ("新罕布什尔州", "新罕布什尔", "new hampshire")),
    ("US-NJ", "新泽西州", ("新泽西州", "新泽西", "new jersey")),
    ("US-NM", "新墨西哥州", ("新墨西哥州", "新墨西哥", "new mexico")),
    ("US-NV", "内华达州", ("内华达州", "内华达", "nevada")),
    ("US-NY", "纽约州", ("纽约州", "纽约", "new york")),
    ("US-OH", "俄亥俄州", ("俄亥俄州", "俄亥俄", "ohio")),
    ("US-OK", "俄克拉荷马州", ("俄克拉荷马州", "俄克拉荷马", "oklahoma")),
    ("US-OR", "俄勒冈州", ("俄勒冈州", "俄勒冈", "oregon")),
    ("US-PA", "宾夕法尼亚州", ("宾夕法尼亚州", "宾夕法尼亚", "pennsylvania")),
    ("US-RI", "罗得岛州", ("罗得岛州", "罗得岛", "rhode island")),
    ("US-SC", "南卡罗来纳州", ("南卡罗来纳州", "南卡罗来纳", "south carolina")),
    ("US-SD", "南达科他州", ("南达科他州", "南达科他", "south dakota")),
    ("US-TN", "田纳西州", ("田纳西州", "田纳西", "tennessee")),
    ("US-TX", "得克萨斯州", ("得克萨斯州", "得克萨斯", "texas")),
    ("US-UT", "犹他州", ("犹他州", "犹他", "utah")),
    ("US-VA", "弗吉尼亚州", ("弗吉尼亚州", "弗吉尼亚", "virginia")),
    ("US-VT", "佛蒙特州", ("佛蒙特州", "佛蒙特", "vermont")),
    ("US-WA", "华盛顿州", ("华盛顿州", "华盛顿", "washington")),
    ("US-WI", "威斯康星州", ("威斯康星州", "威斯康星", "wisconsin")),
    ("US-WV", "西弗吉尼亚州", ("西弗吉尼亚州", "西弗吉尼亚", "west virginia")),
    ("US-WY", "怀俄明州", ("怀俄明州", "怀俄明", "wyoming")),
)

CAREER_FOOTPRINT_US_POSTAL_REGION_MAP = {
    region_key.replace("US-", ""): (region_key, name)
    for region_key, name, _aliases in CAREER_FOOTPRINT_US_REGION_SPECS
}

CAREER_FOOTPRINT_US_CITY_REGION_HINTS = {
    "new york": ("US-NY", "纽约州"),
    "new york city": ("US-NY", "纽约州"),
    "nyc": ("US-NY", "纽约州"),
    "纽约": ("US-NY", "纽约州"),
    "纽约市": ("US-NY", "纽约州"),
    "boston": ("US-MA", "马萨诸塞州"),
    "波士顿": ("US-MA", "马萨诸塞州"),
    "chicago": ("US-IL", "伊利诺伊州"),
    "芝加哥": ("US-IL", "伊利诺伊州"),
    "los angeles": ("US-CA", "加利福尼亚州"),
    "san francisco": ("US-CA", "加利福尼亚州"),
    "san diego": ("US-CA", "加利福尼亚州"),
    "sacramento": ("US-CA", "加利福尼亚州"),
    "洛杉矶": ("US-CA", "加利福尼亚州"),
    "旧金山": ("US-CA", "加利福尼亚州"),
    "圣地亚哥": ("US-CA", "加利福尼亚州"),
    "seattle": ("US-WA", "华盛顿州"),
    "西雅图": ("US-WA", "华盛顿州"),
    "washington dc": ("US-DC", "华盛顿哥伦比亚特区"),
    "washington d.c.": ("US-DC", "华盛顿哥伦比亚特区"),
    "华盛顿特区": ("US-DC", "华盛顿哥伦比亚特区"),
    "miami": ("US-FL", "佛罗里达州"),
    "orlando": ("US-FL", "佛罗里达州"),
    "迈阿密": ("US-FL", "佛罗里达州"),
    "奥兰多": ("US-FL", "佛罗里达州"),
    "honolulu": ("US-HI", "夏威夷州"),
    "檀香山": ("US-HI", "夏威夷州"),
    "las vegas": ("US-NV", "内华达州"),
    "拉斯维加斯": ("US-NV", "内华达州"),
    "portland": ("US-OR", "俄勒冈州"),
    "费城": ("US-PA", "宾夕法尼亚州"),
    "philadelphia": ("US-PA", "宾夕法尼亚州"),
    "austin": ("US-TX", "得克萨斯州"),
    "houston": ("US-TX", "得克萨斯州"),
    "dallas": ("US-TX", "得克萨斯州"),
    "奥斯汀": ("US-TX", "得克萨斯州"),
    "休斯敦": ("US-TX", "得克萨斯州"),
    "达拉斯": ("US-TX", "得克萨斯州"),
    "atlanta": ("US-GA", "佐治亚州"),
    "亚特兰大": ("US-GA", "佐治亚州"),
    "denver": ("US-CO", "科罗拉多州"),
    "丹佛": ("US-CO", "科罗拉多州"),
}

CAREER_FOOTPRINT_JAPAN_REGION_SPECS = (
    ("JP-01", "北海道", ("北海道", "hokkaido")),
    ("JP-02", "青森", ("青森", "青森県", "aomori")),
    ("JP-03", "岩手", ("岩手", "岩手県", "iwate")),
    ("JP-04", "宫城", ("宫城", "宮城", "宮城県", "miyagi")),
    ("JP-05", "秋田", ("秋田", "秋田県", "akita")),
    ("JP-06", "山形", ("山形", "山形県", "yamagata")),
    ("JP-07", "福岛", ("福岛", "福島", "福島県", "fukushima")),
    ("JP-08", "茨城", ("茨城", "茨城県", "ibaraki")),
    ("JP-09", "栃木", ("栃木", "栃木県", "tochigi")),
    ("JP-10", "群马", ("群马", "群馬", "群馬県", "gunma")),
    ("JP-11", "埼玉", ("埼玉", "埼玉県", "saitama")),
    ("JP-12", "千叶", ("千叶", "千葉", "千葉県", "chiba")),
    ("JP-13", "东京", ("东京", "東京", "東京都", "tokyo")),
    ("JP-14", "神奈川", ("神奈川", "神奈川県", "kanagawa", "yokohama")),
    ("JP-15", "新潟", ("新潟", "新潟県", "niigata")),
    ("JP-16", "富山", ("富山", "富山県", "toyama")),
    ("JP-17", "石川", ("石川", "石川県", "ishikawa", "kanazawa")),
    ("JP-18", "福井", ("福井", "福井県", "fukui")),
    ("JP-19", "山梨", ("山梨", "山梨県", "yamanashi")),
    ("JP-20", "长野", ("长野", "長野", "長野県", "nagano")),
    ("JP-21", "岐阜", ("岐阜", "岐阜県", "gifu")),
    ("JP-22", "静冈", ("静冈", "静岡", "静岡県", "shizuoka")),
    ("JP-23", "爱知", ("爱知", "愛知", "愛知県", "aichi", "nagoya")),
    ("JP-24", "三重", ("三重", "三重県", "mie")),
    ("JP-25", "滋贺", ("滋贺", "滋賀", "滋賀県", "shiga")),
    ("JP-26", "京都", ("京都", "京都府", "kyoto")),
    ("JP-27", "大阪", ("大阪", "大阪府", "osaka")),
    ("JP-28", "兵库", ("兵库", "兵庫", "兵庫県", "神户", "神户市", "神戸", "神戸市", "hyogo", "kobe")),
    ("JP-29", "奈良", ("奈良", "奈良県", "nara")),
    ("JP-30", "和歌山", ("和歌山", "和歌山県", "wakayama")),
    ("JP-31", "鸟取", ("鸟取", "鳥取", "鳥取県", "tottori")),
    ("JP-32", "岛根", ("岛根", "島根", "島根県", "shimane")),
    ("JP-33", "冈山", ("冈山", "岡山", "岡山県", "okayama")),
    ("JP-34", "广岛", ("广岛", "広島", "広島県", "hiroshima")),
    ("JP-35", "山口", ("山口", "山口県", "yamaguchi")),
    ("JP-36", "德岛", ("德岛", "徳島", "徳島県", "tokushima")),
    ("JP-37", "香川", ("香川", "香川県", "kagawa")),
    ("JP-38", "爱媛", ("爱媛", "愛媛", "愛媛県", "ehime")),
    ("JP-39", "高知", ("高知", "高知県", "kochi")),
    ("JP-40", "福冈", ("福冈", "福岡", "福岡県", "fukuoka")),
    ("JP-41", "佐贺", ("佐贺", "佐賀", "佐賀県", "saga")),
    ("JP-42", "长崎", ("长崎", "長崎", "長崎県", "nagasaki")),
    ("JP-43", "熊本", ("熊本", "熊本県", "kumamoto")),
    ("JP-44", "大分", ("大分", "大分県", "oita")),
    ("JP-45", "宫崎", ("宫崎", "宮崎", "宮崎県", "miyazaki")),
    ("JP-46", "鹿儿岛", ("鹿儿岛", "鹿児島", "鹿児島県", "kagoshima")),
    ("JP-47", "冲绳", ("冲绳", "沖縄", "沖縄県", "okinawa")),
)

CAREER_OVERVIEW_STRENGTH_WEIGHT_COLUMNS = (
    "strength_total_weight_kg",
    "total_weight_kg",
    "total_volume_kg",
    "weight_volume_kg",
    "volume_kg",
)

@dataclass(frozen=True)
class RecordDefinition:
    key: str
    sport: str
    category: str
    display_name: str
    metric: str
    canonical_unit: str
    comparison: str
    source_mode: str
    standard_distance_m: float | None
    tolerance_ratio: float | None
    minimum_data_requirements: tuple[str, ...]
    enabled_release: str
    rule_version: str
    priority: int
    family: str = ""
    scope_dimensions: tuple[str, ...] = ()
    quality_policy: str = "default"
    availability_state: str = "available"
    availability_reason: str = ""
    standard_duration_sec: int | None = None
    dynamic_scope: bool = False
    legacy_category: str | None = None


RECORD_ALLOWED_SPORTS = {
    "running",
    "cycling",
    "hiking",
    "pool_swimming",
    "open_water_swimming",
    "trail_running",
}
RECORD_ALLOWED_FAMILIES = {
    "distance_time_pb",
    "power_duration_pb",
    "activity_total_record",
    "analysis_curve",
    "model_estimate",
}
RECORD_ALLOWED_UNITS = {
    "seconds",
    "meters",
    "meters_per_second",
    "watts",
    "kilojoules",
    "meters_ascent",
    "meters_altitude",
}
RECORD_ALLOWED_COMPARISONS = {"lower_is_better", "higher_is_better"}
RECORD_ALLOWED_SOURCE_MODES = {
    "activity_total",
    "best_effort_duration",
    "best_effort_distance",
}
RECORD_ALLOWED_SCOPE_DIMENSIONS = {
    "sport_scope",
    "indoor_scope",
    "distance_scope",
    "power_metric_scope",
    "pool_length_scope",
    "stroke_scope",
    "water_scope",
}
RECORD_ALLOWED_AVAILABILITY_STATES = {
    "available",
    "candidate_only",
    "validation_required",
    "unavailable",
    "analysis_only",
    "model_only",
}
RECORDS_V1_RULE_VERSION = "records-v1"
RECORDS_V2_RULE_VERSION = "records-v2"

RUNNING_RECORD_DEFINITIONS = (
    RecordDefinition(
        key="running_5k",
        sport="running",
        category="distance_time",
        display_name="5K",
        metric="elapsed_time_sec",
        canonical_unit="seconds",
        comparison="lower_is_better",
        source_mode="activity_total",
        standard_distance_m=5000.0,
        tolerance_ratio=0.03,
        minimum_data_requirements=("activity_id", "sport", "distance_m", "elapsed_time_sec", "event_date"),
        enabled_release="records-v1",
        rule_version=RECORDS_V1_RULE_VERSION,
        priority=0,
        family="distance_time_pb",
        quality_policy="running_distance_time_v1",
        legacy_category="distance_time",
    ),
    RecordDefinition(
        key="running_10k",
        sport="running",
        category="distance_time",
        display_name="10K",
        metric="elapsed_time_sec",
        canonical_unit="seconds",
        comparison="lower_is_better",
        source_mode="activity_total",
        standard_distance_m=10000.0,
        tolerance_ratio=0.03,
        minimum_data_requirements=("activity_id", "sport", "distance_m", "elapsed_time_sec", "event_date"),
        enabled_release="records-v1",
        rule_version=RECORDS_V1_RULE_VERSION,
        priority=1,
        family="distance_time_pb",
        quality_policy="running_distance_time_v1",
        legacy_category="distance_time",
    ),
    RecordDefinition(
        key="running_half_marathon",
        sport="running",
        category="distance_time",
        display_name="半程马拉松",
        metric="elapsed_time_sec",
        canonical_unit="seconds",
        comparison="lower_is_better",
        source_mode="activity_total",
        standard_distance_m=21097.5,
        tolerance_ratio=0.03,
        minimum_data_requirements=("activity_id", "sport", "distance_m", "elapsed_time_sec", "event_date"),
        enabled_release="records-v1",
        rule_version=RECORDS_V1_RULE_VERSION,
        priority=2,
        family="distance_time_pb",
        quality_policy="running_distance_time_v1",
        legacy_category="distance_time",
    ),
    RecordDefinition(
        key="running_marathon",
        sport="running",
        category="distance_time",
        display_name="马拉松",
        metric="elapsed_time_sec",
        canonical_unit="seconds",
        comparison="lower_is_better",
        source_mode="activity_total",
        standard_distance_m=42195.0,
        tolerance_ratio=0.03,
        minimum_data_requirements=("activity_id", "sport", "distance_m", "elapsed_time_sec", "event_date"),
        enabled_release="records-v1",
        rule_version=RECORDS_V1_RULE_VERSION,
        priority=3,
        family="distance_time_pb",
        quality_policy="running_distance_time_v1",
        legacy_category="distance_time",
    ),
)

CYCLING_POWER_RECORD_DEFINITIONS = (
    RecordDefinition("cycling_power_5s", "cycling", "power_duration", "5 秒最大功率", "power_w", "watts", "higher_is_better", "best_effort_duration", None, None, ("activity_id", "sport", "power_stream", "elapsed_time_sec", "event_date", "range_start", "range_end", "power_quality", "indoor_scope"), "records-v2", RECORDS_V2_RULE_VERSION, 100, family="power_duration_pb", scope_dimensions=("sport_scope", "indoor_scope", "power_metric_scope"), quality_policy="cycling_power_duration", standard_duration_sec=5),
    RecordDefinition("cycling_power_30s", "cycling", "power_duration", "30 秒最大功率", "power_w", "watts", "higher_is_better", "best_effort_duration", None, None, ("activity_id", "sport", "power_stream", "elapsed_time_sec", "event_date", "range_start", "range_end", "power_quality", "indoor_scope"), "records-v2", RECORDS_V2_RULE_VERSION, 101, family="power_duration_pb", scope_dimensions=("sport_scope", "indoor_scope", "power_metric_scope"), quality_policy="cycling_power_duration", standard_duration_sec=30),
    RecordDefinition("cycling_power_1m", "cycling", "power_duration", "1 分钟最大功率", "power_w", "watts", "higher_is_better", "best_effort_duration", None, None, ("activity_id", "sport", "power_stream", "elapsed_time_sec", "event_date", "range_start", "range_end", "power_quality", "indoor_scope"), "records-v2", RECORDS_V2_RULE_VERSION, 102, family="power_duration_pb", scope_dimensions=("sport_scope", "indoor_scope", "power_metric_scope"), quality_policy="cycling_power_duration", standard_duration_sec=60),
    RecordDefinition("cycling_power_5m", "cycling", "power_duration", "5 分钟最大功率", "power_w", "watts", "higher_is_better", "best_effort_duration", None, None, ("activity_id", "sport", "power_stream", "elapsed_time_sec", "event_date", "range_start", "range_end", "power_quality", "indoor_scope"), "records-v2", RECORDS_V2_RULE_VERSION, 103, family="power_duration_pb", scope_dimensions=("sport_scope", "indoor_scope", "power_metric_scope"), quality_policy="cycling_power_duration", standard_duration_sec=300),
    RecordDefinition("cycling_power_10m", "cycling", "power_duration", "10 分钟最大功率", "power_w", "watts", "higher_is_better", "best_effort_duration", None, None, ("activity_id", "sport", "power_stream", "elapsed_time_sec", "event_date", "range_start", "range_end", "power_quality", "indoor_scope"), "records-v2", RECORDS_V2_RULE_VERSION, 104, family="power_duration_pb", scope_dimensions=("sport_scope", "indoor_scope", "power_metric_scope"), quality_policy="cycling_power_duration", standard_duration_sec=600),
    RecordDefinition("cycling_power_20m", "cycling", "power_duration", "20 分钟最大功率", "power_w", "watts", "higher_is_better", "best_effort_duration", None, None, ("activity_id", "sport", "power_stream", "elapsed_time_sec", "event_date", "range_start", "range_end", "power_quality", "indoor_scope"), "records-v2", RECORDS_V2_RULE_VERSION, 105, family="power_duration_pb", scope_dimensions=("sport_scope", "indoor_scope", "power_metric_scope"), quality_policy="cycling_power_duration", standard_duration_sec=1200),
    RecordDefinition("cycling_power_30m", "cycling", "power_duration", "30 分钟最大功率", "power_w", "watts", "higher_is_better", "best_effort_duration", None, None, ("activity_id", "sport", "power_stream", "elapsed_time_sec", "event_date", "range_start", "range_end", "power_quality", "indoor_scope"), "records-v2", RECORDS_V2_RULE_VERSION, 106, family="power_duration_pb", scope_dimensions=("sport_scope", "indoor_scope", "power_metric_scope"), quality_policy="cycling_power_duration", standard_duration_sec=1800),
    RecordDefinition("cycling_power_60m", "cycling", "power_duration", "60 分钟最大功率", "power_w", "watts", "higher_is_better", "best_effort_duration", None, None, ("activity_id", "sport", "power_stream", "elapsed_time_sec", "event_date", "range_start", "range_end", "power_quality", "indoor_scope"), "records-v2", RECORDS_V2_RULE_VERSION, 107, family="power_duration_pb", scope_dimensions=("sport_scope", "indoor_scope", "power_metric_scope"), quality_policy="cycling_power_duration", standard_duration_sec=3600),
    RecordDefinition("cycling_power_2h", "cycling", "power_duration", "2 小时最大功率", "power_w", "watts", "higher_is_better", "best_effort_duration", None, None, ("activity_id", "sport", "power_stream", "elapsed_time_sec", "event_date", "range_start", "range_end", "power_quality", "indoor_scope"), "records-v2", RECORDS_V2_RULE_VERSION, 108, family="power_duration_pb", scope_dimensions=("sport_scope", "indoor_scope", "power_metric_scope"), quality_policy="cycling_power_duration", standard_duration_sec=7200),
)

CYCLING_STANDARD_DISTANCE_RECORD_DEFINITIONS = (
    RecordDefinition("cycling_fastest_10k", "cycling", "distance_time", "最快 10K", "elapsed_time_sec", "seconds", "lower_is_better", "best_effort_distance", 10000.0, None, ("activity_id", "sport", "distance_time_stream", "event_date", "range_start", "range_end", "distance_quality", "indoor_scope"), "records-v2", RECORDS_V2_RULE_VERSION, 90, family="distance_time_pb", scope_dimensions=("sport_scope", "indoor_scope", "distance_scope"), quality_policy="cycling_standard_distance_best_effort", availability_state="validation_required", availability_reason="distance_time_stream_contract_required"),
    RecordDefinition("cycling_fastest_20k", "cycling", "distance_time", "最快 20K", "elapsed_time_sec", "seconds", "lower_is_better", "best_effort_distance", 20000.0, None, ("activity_id", "sport", "distance_time_stream", "event_date", "range_start", "range_end", "distance_quality", "indoor_scope"), "records-v2", RECORDS_V2_RULE_VERSION, 91, family="distance_time_pb", scope_dimensions=("sport_scope", "indoor_scope", "distance_scope"), quality_policy="cycling_standard_distance_best_effort", availability_state="validation_required", availability_reason="distance_time_stream_contract_required"),
    RecordDefinition("cycling_fastest_40k", "cycling", "distance_time", "最快 40K", "elapsed_time_sec", "seconds", "lower_is_better", "best_effort_distance", 40000.0, None, ("activity_id", "sport", "distance_time_stream", "event_date", "range_start", "range_end", "distance_quality", "indoor_scope"), "records-v2", RECORDS_V2_RULE_VERSION, 92, family="distance_time_pb", scope_dimensions=("sport_scope", "indoor_scope", "distance_scope"), quality_policy="cycling_standard_distance_best_effort", availability_state="validation_required", availability_reason="distance_time_stream_contract_required"),
    RecordDefinition("cycling_fastest_50k", "cycling", "distance_time", "最快 50K", "elapsed_time_sec", "seconds", "lower_is_better", "best_effort_distance", 50000.0, None, ("activity_id", "sport", "distance_time_stream", "event_date", "range_start", "range_end", "distance_quality", "indoor_scope"), "records-v2", RECORDS_V2_RULE_VERSION, 93, family="distance_time_pb", scope_dimensions=("sport_scope", "indoor_scope", "distance_scope"), quality_policy="cycling_standard_distance_best_effort", availability_state="validation_required", availability_reason="distance_time_stream_contract_required"),
    RecordDefinition("cycling_fastest_100k", "cycling", "distance_time", "最快 100K", "elapsed_time_sec", "seconds", "lower_is_better", "best_effort_distance", 100000.0, None, ("activity_id", "sport", "distance_time_stream", "event_date", "range_start", "range_end", "distance_quality", "indoor_scope"), "records-v2", RECORDS_V2_RULE_VERSION, 94, family="distance_time_pb", scope_dimensions=("sport_scope", "indoor_scope", "distance_scope"), quality_policy="cycling_standard_distance_best_effort", availability_state="validation_required", availability_reason="distance_time_stream_contract_required"),
    RecordDefinition("cycling_fastest_180k", "cycling", "distance_time", "最快 180K", "elapsed_time_sec", "seconds", "lower_is_better", "best_effort_distance", 180000.0, None, ("activity_id", "sport", "distance_time_stream", "event_date", "range_start", "range_end", "distance_quality", "indoor_scope"), "records-v2", RECORDS_V2_RULE_VERSION, 95, family="distance_time_pb", scope_dimensions=("sport_scope", "indoor_scope", "distance_scope"), quality_policy="cycling_standard_distance_best_effort", availability_state="validation_required", availability_reason="distance_time_stream_contract_required"),
)

CYCLING_ACTIVITY_RECORD_DEFINITIONS = (
    RecordDefinition("cycling_longest_distance", "cycling", "activity_total", "最长骑行距离", "distance_m", "meters", "higher_is_better", "activity_total", None, None, ("activity_id", "sport", "distance_m", "event_date", "metric_quality"), "records-v2", RECORDS_V2_RULE_VERSION, 110, family="activity_total_record", scope_dimensions=("sport_scope", "indoor_scope"), quality_policy="cycling_activity_total"),
    RecordDefinition("cycling_max_ascent", "cycling", "activity_total", "单次最大爬升", "ascent_m", "meters_ascent", "higher_is_better", "activity_total", None, None, ("activity_id", "sport", "ascent_m", "event_date", "metric_quality"), "records-v2", RECORDS_V2_RULE_VERSION, 111, family="activity_total_record", scope_dimensions=("sport_scope", "indoor_scope"), quality_policy="cycling_activity_total"),
    RecordDefinition("cycling_longest_elapsed_time", "cycling", "activity_total", "最长骑行历时", "elapsed_time_sec", "seconds", "higher_is_better", "activity_total", None, None, ("activity_id", "sport", "elapsed_time_sec", "event_date", "time_quality"), "records-v2", RECORDS_V2_RULE_VERSION, 112, family="activity_total_record", scope_dimensions=("sport_scope", "indoor_scope"), quality_policy="cycling_activity_total"),
    RecordDefinition("cycling_max_work", "cycling", "activity_total", "单次最大机械功", "work_kj", "kilojoules", "higher_is_better", "activity_total", None, None, ("activity_id", "sport", "work_kj", "event_date", "power_quality"), "records-v2", RECORDS_V2_RULE_VERSION, 113, family="activity_total_record", scope_dimensions=("sport_scope", "indoor_scope", "power_metric_scope"), quality_policy="cycling_work_total", availability_state="validation_required", availability_reason="work_integration_quality_unknown"),
)

HIKING_RECORD_DEFINITIONS = (
    RecordDefinition("hiking_longest_distance", "hiking", "activity_total", "最长徒步距离", "distance_m", "meters", "higher_is_better", "activity_total", None, None, ("activity_id", "sport", "distance_m", "event_date", "metric_quality"), "records-v2", RECORDS_V2_RULE_VERSION, 200, family="activity_total_record", scope_dimensions=("sport_scope",), quality_policy="hiking_activity_total"),
    RecordDefinition("hiking_max_ascent", "hiking", "activity_total", "单次最大累计爬升", "ascent_m", "meters_ascent", "higher_is_better", "activity_total", None, None, ("activity_id", "sport", "ascent_m", "event_date", "metric_quality"), "records-v2", RECORDS_V2_RULE_VERSION, 201, family="activity_total_record", scope_dimensions=("sport_scope",), quality_policy="hiking_elevation"),
    RecordDefinition("hiking_longest_elapsed_time", "hiking", "activity_total", "最长徒步历时", "elapsed_time_sec", "seconds", "higher_is_better", "activity_total", None, None, ("activity_id", "sport", "elapsed_time_sec", "event_date", "time_quality"), "records-v2", RECORDS_V2_RULE_VERSION, 202, family="activity_total_record", scope_dimensions=("sport_scope",), quality_policy="hiking_activity_total"),
    RecordDefinition("hiking_max_altitude", "hiking", "activity_total", "最高海拔", "max_altitude_m", "meters_altitude", "higher_is_better", "activity_total", None, None, ("activity_id", "sport", "max_altitude_m", "event_date", "metric_quality"), "records-v2", RECORDS_V2_RULE_VERSION, 203, family="activity_total_record", scope_dimensions=("sport_scope",), quality_policy="hiking_elevation"),
    RecordDefinition("hiking_max_single_climb", "hiking", "activity_total", "最大连续爬升", "single_climb_m", "meters_ascent", "higher_is_better", "activity_total", None, None, ("activity_id", "sport", "single_climb_m", "event_date", "range_start", "range_end", "metric_quality"), "records-v2", RECORDS_V2_RULE_VERSION, 204, family="activity_total_record", scope_dimensions=("sport_scope",), quality_policy="hiking_single_climb", availability_state="candidate_only", availability_reason="single_climb_requires_review"),
)

POOL_SWIM_RECORD_DEFINITIONS = tuple(
    RecordDefinition(
        f"pool_swim_{label}",
        "pool_swimming",
        "distance_time",
        f"泳池 {display}",
        "elapsed_time_sec",
        "seconds",
        "lower_is_better",
        "best_effort_distance",
        float(distance_m),
        None,
        ("activity_id", "sport", "elapsed_time_sec", "event_date", "range_start", "range_end", "pool_length_scope", "stroke_scope", "time_quality"),
        "records-v2",
        RECORDS_V2_RULE_VERSION,
        300 + index,
        family="distance_time_pb",
        scope_dimensions=("water_scope", "pool_length_scope", "stroke_scope"),
        quality_policy="pool_swim_best_effort",
        availability_state="validation_required",
        availability_reason="pool_length_schema_required",
    )
    for index, (label, display, distance_m) in enumerate(
        (("50m", "50m", 50), ("100m", "100m", 100), ("200m", "200m", 200), ("400m", "400m", 400), ("800m", "800m", 800), ("1500m", "1500m", 1500))
    )
)

OPEN_WATER_RECORD_DEFINITIONS = (
    *tuple(
        RecordDefinition(
            f"open_water_swim_{label}",
            "open_water_swimming",
            "distance_time",
            f"公开水域 {display}",
            "elapsed_time_sec",
            "seconds",
            "lower_is_better",
            "activity_total",
            float(distance_m),
            0.05,
            ("activity_id", "sport", "distance_m", "elapsed_time_sec", "event_date", "distance_quality", "time_quality"),
            "records-v2",
            RECORDS_V2_RULE_VERSION,
            400 + index,
            family="distance_time_pb",
            scope_dimensions=("water_scope",),
            quality_policy="open_water_distance_time",
            availability_state="candidate_only",
            availability_reason="open_water_sample_limited",
        )
        for index, (label, display, distance_m) in enumerate(
            (("750m", "750m", 750), ("1500m", "1500m", 1500), ("1900m", "1900m", 1900), ("3800m", "3800m", 3800), ("5k", "5K", 5000), ("10k", "10K", 10000))
        )
    ),
    RecordDefinition("open_water_longest_distance", "open_water_swimming", "activity_total", "公开水域最长距离", "distance_m", "meters", "higher_is_better", "activity_total", None, None, ("activity_id", "sport", "distance_m", "event_date", "distance_quality"), "records-v2", RECORDS_V2_RULE_VERSION, 410, family="activity_total_record", scope_dimensions=("water_scope",), quality_policy="open_water_activity_total", availability_state="candidate_only", availability_reason="open_water_sample_limited"),
    RecordDefinition("open_water_longest_elapsed_time", "open_water_swimming", "activity_total", "公开水域最长历时", "elapsed_time_sec", "seconds", "higher_is_better", "activity_total", None, None, ("activity_id", "sport", "elapsed_time_sec", "event_date", "time_quality"), "records-v2", RECORDS_V2_RULE_VERSION, 411, family="activity_total_record", scope_dimensions=("water_scope",), quality_policy="open_water_activity_total", availability_state="candidate_only", availability_reason="open_water_sample_limited"),
)

TRAIL_RECORD_DEFINITIONS = (
    RecordDefinition("trail_longest_distance", "trail_running", "activity_total", "最长越野距离", "distance_m", "meters", "higher_is_better", "activity_total", None, None, ("activity_id", "sport", "distance_m", "event_date", "metric_quality"), "records-v2", RECORDS_V2_RULE_VERSION, 500, family="activity_total_record", scope_dimensions=("sport_scope",), quality_policy="trail_activity_total", availability_state="candidate_only", availability_reason="real_data_sample_missing"),
    RecordDefinition("trail_max_ascent", "trail_running", "activity_total", "越野最大累计爬升", "ascent_m", "meters_ascent", "higher_is_better", "activity_total", None, None, ("activity_id", "sport", "ascent_m", "event_date", "metric_quality"), "records-v2", RECORDS_V2_RULE_VERSION, 501, family="activity_total_record", scope_dimensions=("sport_scope",), quality_policy="trail_elevation", availability_state="candidate_only", availability_reason="real_data_sample_missing"),
    RecordDefinition("trail_longest_elapsed_time", "trail_running", "activity_total", "最长越野历时", "elapsed_time_sec", "seconds", "higher_is_better", "activity_total", None, None, ("activity_id", "sport", "elapsed_time_sec", "event_date", "time_quality"), "records-v2", RECORDS_V2_RULE_VERSION, 502, family="activity_total_record", scope_dimensions=("sport_scope",), quality_policy="trail_activity_total", availability_state="candidate_only", availability_reason="real_data_sample_missing"),
    RecordDefinition("trail_max_altitude", "trail_running", "activity_total", "越野最高海拔", "max_altitude_m", "meters_altitude", "higher_is_better", "activity_total", None, None, ("activity_id", "sport", "max_altitude_m", "event_date", "metric_quality"), "records-v2", RECORDS_V2_RULE_VERSION, 503, family="activity_total_record", scope_dimensions=("sport_scope",), quality_policy="trail_elevation", availability_state="candidate_only", availability_reason="real_data_sample_missing"),
    RecordDefinition("trail_max_single_climb", "trail_running", "activity_total", "越野最大连续爬升", "single_climb_m", "meters_ascent", "higher_is_better", "activity_total", None, None, ("activity_id", "sport", "single_climb_m", "event_date", "range_start", "range_end", "metric_quality"), "records-v2", RECORDS_V2_RULE_VERSION, 504, family="activity_total_record", scope_dimensions=("sport_scope",), quality_policy="trail_single_climb", availability_state="candidate_only", availability_reason="real_data_sample_missing"),
)

RECORD_DEFINITIONS = (
    *RUNNING_RECORD_DEFINITIONS,
    *CYCLING_STANDARD_DISTANCE_RECORD_DEFINITIONS,
    *CYCLING_POWER_RECORD_DEFINITIONS,
    *CYCLING_ACTIVITY_RECORD_DEFINITIONS,
    *HIKING_RECORD_DEFINITIONS,
    *POOL_SWIM_RECORD_DEFINITIONS,
    *OPEN_WATER_RECORD_DEFINITIONS,
    *TRAIL_RECORD_DEFINITIONS,
)
RECORD_DEFINITION_BY_KEY = {definition.key: definition for definition in RECORD_DEFINITIONS}


def _record_definition_range(definition: RecordDefinition) -> tuple[float, float]:
    if definition.standard_distance_m is None or definition.tolerance_ratio is None:
        raise ValueError(f"Record definition has no distance tolerance rule: {definition.key}")
    low = definition.standard_distance_m * (1.0 - definition.tolerance_ratio)
    high = definition.standard_distance_m * (1.0 + definition.tolerance_ratio)
    return low, high


def _record_definition_family(definition: RecordDefinition) -> str:
    return str(definition.family or definition.category or "").strip()


def validate_record_registry(definitions: tuple[RecordDefinition, ...] = RECORD_DEFINITIONS) -> None:
    seen_keys: set[str] = set()
    scoped_ranges: dict[tuple[str, str, str], list[tuple[float, float, str]]] = {}
    for definition in definitions:
        if definition.key in seen_keys:
            raise ValueError(f"Duplicate record definition key: {definition.key}")
        seen_keys.add(definition.key)
        if definition.sport not in RECORD_ALLOWED_SPORTS:
            raise ValueError(f"Unsupported record sport for {definition.key}: {definition.sport}")
        family = _record_definition_family(definition)
        if family not in RECORD_ALLOWED_FAMILIES:
            raise ValueError(f"Unsupported record family for {definition.key}: {family}")
        if definition.canonical_unit not in RECORD_ALLOWED_UNITS:
            raise ValueError(f"Unsupported record unit for {definition.key}: {definition.canonical_unit}")
        if definition.comparison not in RECORD_ALLOWED_COMPARISONS:
            raise ValueError(f"Unsupported record comparison for {definition.key}: {definition.comparison}")
        if definition.source_mode not in RECORD_ALLOWED_SOURCE_MODES:
            raise ValueError(f"Unsupported record source mode for {definition.key}: {definition.source_mode}")
        invalid_scope_dimensions = set(definition.scope_dimensions) - RECORD_ALLOWED_SCOPE_DIMENSIONS
        if invalid_scope_dimensions:
            raise ValueError(
                f"Unsupported record scope dimension for {definition.key}: "
                f"{sorted(invalid_scope_dimensions)}"
            )
        if definition.availability_state not in RECORD_ALLOWED_AVAILABILITY_STATES:
            raise ValueError(
                f"Unsupported record availability for {definition.key}: {definition.availability_state}"
            )
        has_distance_rule = definition.standard_distance_m is not None or definition.tolerance_ratio is not None
        if has_distance_rule:
            if definition.standard_distance_m is None or definition.standard_distance_m <= 0:
                raise ValueError(f"Invalid distance rule for {definition.key}")
            if definition.tolerance_ratio is not None and definition.tolerance_ratio <= 0:
                raise ValueError(f"Invalid distance rule for {definition.key}")
            if definition.tolerance_ratio is not None:
                scope = (definition.sport, definition.source_mode, family)
                scoped_ranges.setdefault(scope, []).append((*_record_definition_range(definition), definition.key))
        if definition.source_mode == "best_effort_duration" and not definition.standard_duration_sec:
            raise ValueError(f"Missing duration anchor for {definition.key}")
        if definition.dynamic_scope:
            raise ValueError(f"Dynamic scoped records are outside Records Center V2: {definition.key}")

    for ranges in scoped_ranges.values():
        ordered = sorted(ranges)
        for previous, current in zip(ordered, ordered[1:]):
            previous_low, previous_high, previous_key = previous
            current_low, current_high, current_key = current
            if current_low <= previous_high:
                raise ValueError(
                    f"Overlapping record definition ranges: {previous_key} "
                    f"({previous_low:g}-{previous_high:g}) and {current_key} "
                    f"({current_low:g}-{current_high:g})"
                )


validate_record_registry()


def get_record_definition(record_key: str) -> RecordDefinition | None:
    return RECORD_DEFINITION_BY_KEY.get(str(record_key or ""))


def iter_record_definitions(
    sport: str | None = None,
    source_mode: str | None = None,
    availability_state: str | None = None,
) -> tuple[RecordDefinition, ...]:
    return tuple(
        definition
        for definition in RECORD_DEFINITIONS
        if (sport is None or definition.sport == sport)
        and (source_mode is None or definition.source_mode == source_mode)
        and (availability_state is None or definition.availability_state == availability_state)
    )


RECORD_SPORT_ORDER = ("running", "cycling", "hiking", "pool_swimming", "open_water_swimming", "trail_running")
RECORD_SPORT_LABELS = {
    "running": "跑步",
    "cycling": "骑行",
    "hiking": "徒步",
    "pool_swimming": "泳池游泳",
    "open_water_swimming": "公开水域",
    "trail_running": "越野跑",
}
RECORD_SPORT_ICONS = {
    "running": "run",
    "cycling": "bike",
    "hiking": "hiking",
    "pool_swimming": "pool",
    "open_water_swimming": "waves",
    "trail_running": "trail",
}
RECORD_GROUP_LABELS = {
    "running_distance": "标准距离 PB",
    "cycling_standard_distance": "标准距离",
    "cycling_power": "功率纪录",
    "cycling_activity_total": "整次活动",
    "hiking_activity_total": "徒步纪录",
    "pool_swim_standard": "泳池标准距离",
    "open_water_standard": "公开水域标准距离",
    "open_water_activity_total": "公开水域整次活动",
    "trail_activity_total": "越野整次活动",
}
RECORD_AVAILABILITY_LABELS = {
    "available": "可用",
    "candidate_only": "仅候选",
    "validation_required": "待验证",
    "unavailable": "不可用",
    "analysis_only": "仅分析",
    "model_only": "模型估计",
}


def _record_axis_direction(definition: RecordDefinition) -> str:
    return "higher" if definition.comparison == "higher_is_better" else "lower"


def _record_group_key(definition: RecordDefinition) -> str:
    family = _record_definition_family(definition)
    if definition.sport == "running":
        return "running_distance"
    if definition.sport == "cycling" and family == "distance_time_pb":
        return "cycling_standard_distance"
    if definition.sport == "cycling" and family == "power_duration_pb":
        return "cycling_power"
    if definition.sport == "cycling":
        return "cycling_activity_total"
    if definition.sport == "hiking":
        return "hiking_activity_total"
    if definition.sport == "pool_swimming":
        return "pool_swim_standard"
    if definition.sport == "open_water_swimming" and family == "distance_time_pb":
        return "open_water_standard"
    if definition.sport == "open_water_swimming":
        return "open_water_activity_total"
    if definition.sport == "trail_running":
        return "trail_activity_total"
    return f"{definition.sport}_{family}"


def _record_catalog_item(definition: RecordDefinition) -> dict[str, Any]:
    state = definition.availability_state
    return {
        "record_key": definition.key,
        "display_name": definition.display_name,
        "sport": definition.sport,
        "sport_label": RECORD_SPORT_LABELS.get(definition.sport, definition.sport),
        "family": _record_definition_family(definition),
        "metric": definition.metric,
        "canonical_unit": definition.canonical_unit,
        "comparison": definition.comparison,
        "axis_direction": _record_axis_direction(definition),
        "source_mode": definition.source_mode,
        "scope_dimensions": list(definition.scope_dimensions),
        "availability_state": state,
        "availability_reason": definition.availability_reason or None,
        "availability_message_key": f"record_{state}",
        "priority": definition.priority,
        "supports_curve": definition.key.startswith("cycling_power_"),
        "supports_history": state not in {"analysis_only", "model_only"},
        "supports_candidates": state in {"available", "candidate_only"},
        "standard_distance_m": definition.standard_distance_m,
        "standard_duration_sec": definition.standard_duration_sec,
        "tolerance_ratio": definition.tolerance_ratio,
        "dynamic_scope": bool(definition.dynamic_scope),
    }


def _record_sport_capabilities(sport: str) -> dict[str, Any]:
    if sport == "cycling":
        return {
            "standard_distance_records": {
                "state": "validation_required",
                "source_mode": "best_effort_distance",
                "requires_distance_time_stream": True,
                "reason_codes": ["distance_time_stream_contract_required"],
                "record_keys": [
                    "cycling_fastest_10k",
                    "cycling_fastest_20k",
                    "cycling_fastest_40k",
                    "cycling_fastest_50k",
                    "cycling_fastest_100k",
                    "cycling_fastest_180k",
                ],
                "creates_active_record": False,
            },
            "power_duration_curve": {
                "state": "available",
                "curve_type": "cycling_power_duration_curve",
                "source_mode": "best_effort_duration",
                "requires_point_power": True,
                "missing_reason_codes": ["power_stream_missing"],
                "record_keys": [CYCLING_POWER_RECORD_KEY_BY_DURATION[duration] for duration in CYCLING_POWER_DURATION_WINDOWS_SEC],
            },
            "activity_total_records": {
                "state": "available",
                "record_keys": [
                    "cycling_longest_distance",
                    "cycling_max_ascent",
                    "cycling_longest_elapsed_time",
                    "cycling_max_work",
                ],
                "validation_required_record_keys": ["cycling_max_work"],
            },
            "wkg": {
                "state": "unavailable",
                "reason_codes": ["historical_weight_missing", "wkg_registry_not_enabled"],
                "requires_activity_date_weight": True,
                "creates_record": False,
            },
            "model_estimates": {
                "state": "model_only",
                "items": ["eftp", "cp", "w_prime", "map", "pmax"],
                "creates_record": False,
            },
            "scope_dimensions": ["sport_scope", "indoor_scope", "distance_scope", "power_metric_scope"],
        }
    if sport == "trail_running":
        return {
            "activity_total_records": {
                "state": "candidate_only",
                "record_keys": [
                    "trail_longest_distance",
                    "trail_max_ascent",
                    "trail_longest_elapsed_time",
                    "trail_max_altitude",
                    "trail_max_single_climb",
                ],
                "reason_codes": ["real_data_sample_missing"],
            },
            "scope_dimensions": ["sport_scope"],
        }
    return {}


def get_career_record_catalog(filters: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the V2 Records Catalog derived from the backend Registry only."""
    clean_filters = filters if isinstance(filters, dict) else {}
    sport_filter = str(clean_filters.get("sport") or "all").strip() or "all"
    include_unavailable = bool(clean_filters.get("include_unavailable", True))
    include_analysis = bool(clean_filters.get("include_analysis", True))
    excluded_states = set()
    if not include_unavailable:
        excluded_states.update({"unavailable", "validation_required"})
    if not include_analysis:
        excluded_states.update({"analysis_only", "model_only"})

    sports: list[dict[str, Any]] = []
    for sport in RECORD_SPORT_ORDER:
        if sport_filter not in {"all", sport}:
            continue
        definitions = [
            definition
            for definition in iter_record_definitions(sport=sport)
            if definition.availability_state not in excluded_states
        ]
        if not definitions and not include_unavailable:
            continue
        grouped: dict[str, list[RecordDefinition]] = {}
        for definition in definitions:
            grouped.setdefault(_record_group_key(definition), []).append(definition)
        groups = []
        for group_key, group_definitions in sorted(
            grouped.items(),
            key=lambda item: min(definition.priority for definition in item[1]),
        ):
            groups.append({
                "group_key": group_key,
                "group_label": RECORD_GROUP_LABELS.get(group_key, group_key),
                "family": _record_definition_family(sorted(group_definitions, key=lambda item: item.priority)[0]),
                "records": [_record_catalog_item(definition) for definition in sorted(group_definitions, key=lambda item: item.priority)],
            })
        record_count = sum(len(group["records"]) for group in groups)
        sport_states = {definition.availability_state for definition in definitions}
        sport_state = "available" if "available" in sport_states else (sorted(sport_states)[0] if sport_states else "unavailable")
        sports.append({
            "sport": sport,
            "sport_label": RECORD_SPORT_LABELS.get(sport, sport),
            "icon": RECORD_SPORT_ICONS.get(sport, "record"),
            "availability_state": sport_state,
            "state_label": RECORD_AVAILABILITY_LABELS.get(sport_state, sport_state),
            "record_count": record_count,
            "active_count": 0,
            "candidate_count": 0,
            "capabilities": _record_sport_capabilities(sport),
            "groups": groups,
        })
    return {
        "sports": sports,
        "filters": {
            "sport": sport_filter,
            "include_unavailable": include_unavailable,
            "include_analysis": include_analysis,
        },
        "status": {
            "schema_ready": True,
            "data_ready": bool(sports),
            "state": "ready" if sports else "empty",
            "message": "",
            "catalog_version": "records-center-v2-catalog",
        },
    }


def match_record_definition(
    summary: dict[str, Any],
    definitions: tuple[RecordDefinition, ...] = RUNNING_RECORD_DEFINITIONS,
) -> dict[str, Any] | None:
    sport = str(summary.get("sport") or "").strip()
    source_mode = str(summary.get("source_mode") or "activity_total").strip() or "activity_total"
    distance_m = _safe_float(summary.get("distance_m"))
    if distance_m is None or distance_m <= 0:
        return None
    matches: list[dict[str, Any]] = []
    for definition in definitions:
        if definition.sport != sport or definition.source_mode != source_mode:
            continue
        if definition.standard_distance_m is None or definition.tolerance_ratio is None:
            continue
        error_ratio = abs(distance_m - definition.standard_distance_m) / definition.standard_distance_m
        if error_ratio <= definition.tolerance_ratio:
            matches.append({
                "record_key": definition.key,
                "definition": definition,
                "source_mode": definition.source_mode,
                "standard_distance_m": definition.standard_distance_m,
                "actual_distance_m": int(round(distance_m)),
                "distance_error_ratio": error_ratio,
            })
    if not matches:
        return None
    if len(matches) > 1:
        keys = ", ".join(match["record_key"] for match in matches)
        raise ValueError(f"Record definition conflict for activity summary: {keys}")
    return matches[0]


def compare_record_performance(candidate_value: Any, current_value: Any | None) -> dict[str, Any]:
    candidate_sec = _safe_int(candidate_value)
    if candidate_sec <= 0:
        return {
            "is_valid": False,
            "is_new_record": False,
            "improvement_sec": None,
            "reason": "invalid_candidate_value",
        }
    if current_value in (None, ""):
        return {
            "is_valid": True,
            "is_new_record": True,
            "improvement_sec": None,
            "reason": "first_record",
        }
    current_sec = _safe_int(current_value)
    if current_sec <= 0:
        return {
            "is_valid": True,
            "is_new_record": True,
            "improvement_sec": None,
            "reason": "current_value_invalid",
        }
    if candidate_sec < current_sec:
        return {
            "is_valid": True,
            "is_new_record": True,
            "improvement_sec": current_sec - candidate_sec,
            "reason": "faster",
        }
    if candidate_sec == current_sec:
        return {
            "is_valid": True,
            "is_new_record": False,
            "improvement_sec": 0,
            "reason": "tie",
        }
    return {
        "is_valid": True,
        "is_new_record": False,
        "improvement_sec": None,
        "reason": "slower",
    }


def _career_year_report_needs_format_upgrade(cached_report: dict[str, Any] | None) -> bool:
    if not isinstance(cached_report, dict):
        return False
    content = cached_report.get("content") if isinstance(cached_report.get("content"), dict) else {}
    return str(content.get("schema_version") or "acs.year.report.v1") != CAREER_YEAR_AI_REPORT_SCHEMA_VERSION


def _career_year_report_update_available(
    year: int,
    *,
    conn: sqlite3.Connection,
    activity_rows: list[dict[str, Any]] | None = None,
) -> bool:
    cached_report = get_current_career_ai_insight(
        scope=CAREER_AI_INSIGHT_SCOPE_YEAR,
        scope_key=str(year),
        conn=conn,
    )
    if not cached_report or str(cached_report.get("status") or "") != "ready":
        return False
    snapshot = build_career_year_snapshot(year, conn=conn, activity_rows=activity_rows)
    return str(snapshot.get("source_fingerprint") or "") != str(cached_report.get("snapshot_fingerprint") or "")


def _career_year_update_badges(
    available_years: list[int],
    *,
    conn: sqlite3.Connection,
    activity_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    years: list[int] = []
    for year in available_years:
        try:
            clean_year = _validate_career_year(year)
            if _career_year_report_update_available(
                clean_year,
                conn=conn,
                activity_rows=activity_rows,
            ):
                years.append(clean_year)
        except Exception:
            continue
    return {
        "years": years,
        "year_map": {str(year): True for year in years},
    }


def _annotate_career_season_report_updates(
    seasons: list[dict[str, Any]],
    *,
    conn: sqlite3.Connection,
) -> list[dict[str, Any]]:
    """Attach report refresh eligibility to Season cards from Year Snapshot facts."""
    if not seasons:
        return seasons
    year_map: dict[int, bool] = {}
    for season in seasons:
        if not isinstance(season, dict):
            continue
        try:
            year = _validate_career_year(season.get("year"))
        except Exception:
            continue
        if year not in year_map:
            year_map[year] = _career_year_report_update_available(year, conn=conn)
        season["report_update_available"] = bool(year_map.get(year))
    return seasons


RECORD_CONFIDENCE_AUTO_THRESHOLD = 0.90
RECORD_CONFIDENCE_CANDIDATE_THRESHOLD = 0.70
_RECORDS_REBUILD_IN_PROGRESS = False


def _record_confidence_level(confidence: float) -> str:
    if confidence > RECORD_CONFIDENCE_AUTO_THRESHOLD:
        return "high"
    if confidence >= RECORD_CONFIDENCE_CANDIDATE_THRESHOLD:
        return "medium"
    return "low"


def _record_candidate_decision(confidence: float) -> str:
    if confidence > RECORD_CONFIDENCE_AUTO_THRESHOLD:
        return "auto_confirm"
    if confidence >= RECORD_CONFIDENCE_CANDIDATE_THRESHOLD:
        return "candidate"
    return "ignored"


CYCLING_POWER_STREAM_DEFAULT_CONFIG: dict[str, Any] = {
    "max_gap_sec": 5.0,
    "short_power_spike_ratio": 1.8,
    "min_high_coverage_ratio": 0.95,
    "min_candidate_coverage_ratio": 0.50,
    "min_valid_points": 2,
    "max_plausible_power_w": 2500.0,
}

CYCLING_EBIKE_SPORT_TYPES = {
    "e_bike",
    "e_biking",
    "ebike",
    "e_bike_fitness",
    "electric_bike",
    "electric_biking",
    "electric_mountain_bike",
    "e_mountain_biking",
}


def _finite_float(value: Any) -> float | None:
    parsed = _safe_float(value)
    if parsed is None or parsed != parsed or parsed in (float("inf"), float("-inf")):
        return None
    return parsed


def _cycling_power_stream_config(config: dict[str, Any] | None = None) -> dict[str, float]:
    merged = dict(CYCLING_POWER_STREAM_DEFAULT_CONFIG)
    if isinstance(config, dict):
        for key in merged:
            parsed = _finite_float(config.get(key))
            if parsed is not None and parsed > 0:
                merged[key] = parsed
    return {key: float(value) for key, value in merged.items()}


def _parse_record_timestamp_seconds(value: Any) -> float | None:
    if value is None:
        return None
    parsed = _finite_float(value)
    if parsed is not None:
        return parsed
    if isinstance(value, datetime):
        try:
            return float(value.timestamp())
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            return float(datetime.fromisoformat(normalized).timestamp())
        except ValueError:
            return None
    return None


def _extract_cycling_power_time(point: dict[str, Any]) -> float | None:
    for key in ("t", "time_sec", "elapsed_sec", "elapsed_time_sec", "timestamp", "time"):
        if key in point:
            parsed = _parse_record_timestamp_seconds(point.get(key))
            if parsed is not None:
                return parsed
    return None


def _extract_cycling_power_value(point: dict[str, Any]) -> tuple[float | None, bool]:
    for key in ("power_w", "power", "watts", "enhanced_power", "Power"):
        if key not in point:
            continue
        value = point.get(key)
        if value in (None, ""):
            return None, True
        parsed = _finite_float(value)
        if parsed is None:
            return None, True
        return parsed, False
    return None, True


def _normalise_cycling_scope_token(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def _is_ebike_activity(activity: dict[str, Any] | None) -> bool:
    if not isinstance(activity, dict):
        return False
    for key in ("sport_type", "sport", "activity_type", "sub_sport_type", "sub_sport"):
        if _normalise_cycling_scope_token(activity.get(key)) in CYCLING_EBIKE_SPORT_TYPES:
            return True
    return False


def _cycling_indoor_scope(activity: dict[str, Any] | None) -> str:
    if not isinstance(activity, dict):
        return "unknown"
    raw = _normalise_cycling_scope_token(
        activity.get("indoor_scope")
        or activity.get("trainer")
        or activity.get("location_scope")
        or activity.get("sub_sport_type")
        or activity.get("sub_sport")
    )
    if raw in {"indoor", "trainer", "virtual", "stationary", "indoor_cycling"}:
        return "trainer"
    if raw in {"outdoor", "road", "mountain", "gravel", "generic", "cycling"}:
        return "outdoor"
    return "unknown"


def _cycling_power_source_label(activity: dict[str, Any] | None) -> str:
    raw = str((activity or {}).get("power_source") or "raw_power_w").strip()
    if not raw:
        return "raw_power_w"
    lowered = raw.lower()
    forbidden = (
        "file_path",
        "storage_ref",
        "device_serial",
        "serial_number",
        "weight_history",
        "/users/",
        "\\users\\",
        "file://",
        "token",
        "password",
        "api_key",
    )
    if any(item in lowered for item in forbidden):
        return "raw_power_w"
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_.: -]", "", raw)[:64].strip()
    return cleaned or "raw_power_w"


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _round_optional(value: float | None, digits: int = 3) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _detect_cycling_power_spikes(
    points: list[dict[str, float]],
    *,
    spike_ratio: float,
    max_plausible_power_w: float,
) -> tuple[list[dict[str, float]], list[dict[str, Any]]]:
    if len(points) < 3:
        return points, []
    clean: list[dict[str, float]] = []
    spikes: list[dict[str, Any]] = []
    for index, point in enumerate(points):
        power = float(point["power_w"])
        is_spike = power > max_plausible_power_w
        if 0 < index < len(points) - 1:
            prev_power = float(points[index - 1]["power_w"])
            next_power = float(points[index + 1]["power_w"])
            local_baseline = max(prev_power, next_power, 1.0)
            is_spike = is_spike or (
                power > local_baseline * spike_ratio
                and power - max(prev_power, next_power) >= 100.0
            )
        if is_spike:
            spikes.append({"t_sec": round(float(point["t_sec"]), 3)})
            continue
        clean.append(point)
    return clean, spikes


def _cycling_power_interval_stats(
    points: list[dict[str, float]],
    *,
    max_gap_sec: float,
) -> dict[str, Any]:
    if len(points) < 2:
        return {
            "intervals_sec": [],
            "covered_duration_sec": 0.0,
            "weighted_power_seconds": 0.0,
            "gap_after_times_sec": [],
        }
    raw_intervals = [
        round(float(current["t_sec"]) - float(prev["t_sec"]), 6)
        for prev, current in zip(points, points[1:])
        if float(current["t_sec"]) - float(prev["t_sec"]) > 0
    ]
    median_interval = _median(raw_intervals)
    dynamic_gap_sec = max(max_gap_sec, (median_interval or 0.0) * 2.5)
    intervals: list[float] = []
    gap_after_times: list[float] = []
    covered = 0.0
    weighted = 0.0
    for prev, current in zip(points, points[1:]):
        delta = round(float(current["t_sec"]) - float(prev["t_sec"]), 6)
        if delta <= 0:
            continue
        intervals.append(delta)
        if delta > dynamic_gap_sec:
            gap_after_times.append(round(float(prev["t_sec"]), 3))
            continue
        covered += delta
        weighted += float(prev["power_w"]) * delta
    return {
        "intervals_sec": intervals,
        "gap_threshold_sec": dynamic_gap_sec,
        "covered_duration_sec": covered,
        "weighted_power_seconds": weighted,
        "gap_after_times_sec": gap_after_times,
    }


def normalize_cycling_power_stream_for_records(
    power_points: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    *,
    activity: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize cycling power stream for Records V2 best-effort duration logic.

    The returned ``clean_points`` are internal resolver input, not a public API
    payload. Use ``build_cycling_power_stream_quality_summary`` before exposing
    quality status to UI, logs, AI, or completion artifacts.
    """
    cfg = _cycling_power_stream_config(config)
    raw_points = list(power_points or [])
    scope = {
        "sport_scope": "cycling_regular",
        "indoor_scope": _cycling_indoor_scope(activity),
        "power_metric_scope": "raw_power_w",
    }
    if _is_ebike_activity(activity):
        return {
            "ok": False,
            "quality": "ignored",
            "confidence": 0.0,
            "confidence_band": "low",
            "candidate_only": False,
            "reason_codes": ["ebike_scope_excluded"],
            "scope": {**scope, "sport_scope": "ebike_excluded"},
            "clean_points": [],
            "quality_summary": {
                "state": "ignored",
                "confidence": 0.0,
                "reason_codes": ["ebike_scope_excluded"],
                "candidate_only": False,
                "scope": {**scope, "sport_scope": "ebike_excluded"},
                "points_count": len(raw_points),
                "valid_points_count": 0,
                "duration_sec": 0.0,
                "coverage_ratio": 0.0,
                "missing_power_count": 0,
                "zero_power_count": 0,
                "spike_count": 0,
                "gap_count": 0,
                "power_source": _cycling_power_source_label(activity),
            },
        }

    parsed_points: list[dict[str, float]] = []
    valid_times_in_input_order: list[float] = []
    missing_power_count = 0
    invalid_time_count = 0
    invalid_power_count = 0
    zero_power_count = 0
    for raw_point in raw_points:
        if not isinstance(raw_point, dict):
            invalid_time_count += 1
            continue
        t_raw = _extract_cycling_power_time(raw_point)
        if t_raw is None:
            invalid_time_count += 1
            continue
        valid_times_in_input_order.append(t_raw)
        power, missing = _extract_cycling_power_value(raw_point)
        if missing:
            missing_power_count += 1
            continue
        if power is None or power < 0:
            invalid_power_count += 1
            continue
        if power == 0:
            zero_power_count += 1
        parsed_points.append({"t_raw": float(t_raw), "power_w": float(power)})

    non_monotonic_count = sum(
        1
        for prev, current in zip(valid_times_in_input_order, valid_times_in_input_order[1:])
        if current <= prev
    )
    deduped: dict[float, dict[str, float]] = {}
    for point in sorted(parsed_points, key=lambda item: (item["t_raw"], item["power_w"])):
        deduped.setdefault(float(point["t_raw"]), point)
    ordered = list(deduped.values())
    if not ordered:
        reason_codes = ["power_stream_missing"]
        if invalid_time_count:
            reason_codes.append("duration_semantics_unknown")
        summary = {
            "state": "ignored",
            "confidence": 0.0,
            "reason_codes": sorted(dict.fromkeys(reason_codes)),
            "candidate_only": False,
            "scope": scope,
            "points_count": len(raw_points),
            "valid_points_count": 0,
            "duration_sec": 0.0,
            "coverage_ratio": 0.0,
            "missing_power_count": missing_power_count,
            "zero_power_count": zero_power_count,
            "spike_count": 0,
            "gap_count": 0,
            "invalid_time_count": invalid_time_count,
            "invalid_power_count": invalid_power_count,
        }
        return {
            "ok": False,
            "quality": "ignored",
            "confidence": 0.0,
            "confidence_band": "low",
            "candidate_only": False,
            "reason_codes": summary["reason_codes"],
            "scope": scope,
            "clean_points": [],
            "quality_summary": summary,
        }

    first_time = float(ordered[0]["t_raw"])
    normalized_points = [
        {"t_sec": round(float(point["t_raw"]) - first_time, 6), "power_w": round(float(point["power_w"]), 3)}
        for point in ordered
        if float(point["t_raw"]) >= first_time
    ]
    clean_points, spikes = _detect_cycling_power_spikes(
        normalized_points,
        spike_ratio=cfg["short_power_spike_ratio"],
        max_plausible_power_w=cfg["max_plausible_power_w"],
    )
    interval_stats = _cycling_power_interval_stats(clean_points, max_gap_sec=cfg["max_gap_sec"])
    intervals = interval_stats["intervals_sec"]
    span_duration = max(0.0, float(clean_points[-1]["t_sec"]) - float(clean_points[0]["t_sec"])) if len(clean_points) >= 2 else 0.0
    activity_duration = _finite_float((activity or {}).get("duration_sec") or (activity or {}).get("duration"))
    duration_sec = max(span_duration, activity_duration or 0.0)
    covered_duration = float(interval_stats["covered_duration_sec"])
    coverage_ratio = (covered_duration / duration_sec) if duration_sec > 0 else 0.0
    weighted_avg = (
        float(interval_stats["weighted_power_seconds"]) / covered_duration
        if covered_duration > 0
        else None
    )

    reason_codes: list[str] = []
    if missing_power_count:
        reason_codes.append("missing_power_stream_sample")
    if spikes:
        reason_codes.append("power_spike_detected")
    if interval_stats["gap_after_times_sec"]:
        reason_codes.append("power_stream_gap")
    if invalid_time_count or non_monotonic_count:
        reason_codes.append("duration_semantics_unknown")
    if invalid_power_count:
        reason_codes.append("plausibility_outlier")
    if len(clean_points) < int(cfg["min_valid_points"]):
        reason_codes.append("power_stream_missing")

    unique_reason_codes = sorted(dict.fromkeys(reason_codes))
    hard_block = "power_stream_missing" in unique_reason_codes
    if hard_block:
        quality = "ignored"
        confidence = 0.0
    elif coverage_ratio >= cfg["min_high_coverage_ratio"] and not unique_reason_codes:
        quality = "high"
        confidence = 0.98
    elif coverage_ratio >= cfg["min_candidate_coverage_ratio"] or clean_points:
        quality = "candidate"
        confidence = 0.80
    else:
        quality = "ignored"
        confidence = 0.0
        unique_reason_codes = sorted(dict.fromkeys([*unique_reason_codes, "power_stream_missing"]))

    sampling = {
        "median_interval_sec": _round_optional(_median(intervals)),
        "min_interval_sec": _round_optional(min(intervals) if intervals else None),
        "max_interval_sec": _round_optional(max(intervals) if intervals else None),
        "non_monotonic_count": non_monotonic_count,
    }
    summary = {
        "state": quality,
        "confidence": confidence,
        "confidence_band": _record_confidence_level(confidence),
        "reason_codes": unique_reason_codes,
        "candidate_only": quality == "candidate",
        "scope": scope,
        "points_count": len(raw_points),
        "valid_points_count": len(clean_points),
        "duration_sec": _round_optional(duration_sec),
        "covered_duration_sec": _round_optional(covered_duration),
        "coverage_ratio": _round_optional(coverage_ratio),
        "time_weighted_avg_power_w": _round_optional(weighted_avg, 2),
        "missing_power_count": missing_power_count,
        "zero_power_count": zero_power_count,
        "spike_count": len(spikes),
        "spike_times_sec": [item["t_sec"] for item in spikes],
        "gap_count": len(interval_stats["gap_after_times_sec"]),
        "gap_after_times_sec": interval_stats["gap_after_times_sec"],
        "gap_threshold_sec": _round_optional(interval_stats.get("gap_threshold_sec")),
        "invalid_time_count": invalid_time_count,
        "invalid_power_count": invalid_power_count,
        "sampling": sampling,
        "power_source": _cycling_power_source_label(activity),
    }
    return {
        "ok": quality != "ignored",
        "quality": quality,
        "confidence": confidence,
        "confidence_band": summary["confidence_band"],
        "candidate_only": quality == "candidate",
        "reason_codes": unique_reason_codes,
        "scope": scope,
        "clean_points": clean_points,
        "quality_summary": summary,
    }


def build_cycling_power_stream_quality_summary(normalized: dict[str, Any]) -> dict[str, Any]:
    """Return the safe public/loggable subset of a normalized power stream result."""
    if not isinstance(normalized, dict):
        return {
            "state": "ignored",
            "confidence": 0.0,
            "reason_codes": ["power_stream_missing"],
            "candidate_only": False,
        }
    summary = dict(normalized.get("quality_summary") or {})
    summary.pop("clean_points", None)
    summary.pop("normalized_points", None)
    summary.pop("power_points", None)
    return summary


CYCLING_POWER_DURATION_CURVE_ALGORITHM_VERSION = "cycling-power-duration-v1"
CYCLING_POWER_DURATION_WINDOWS_SEC = (5, 30, 60, 300, 600, 1200, 1800, 3600, 7200)
CYCLING_POWER_RECORD_KEY_BY_DURATION = {
    5: "cycling_power_5s",
    30: "cycling_power_30s",
    60: "cycling_power_1m",
    300: "cycling_power_5m",
    600: "cycling_power_10m",
    1200: "cycling_power_20m",
    1800: "cycling_power_30m",
    3600: "cycling_power_60m",
    7200: "cycling_power_2h",
}


def _cycling_power_stream_hash(normalized: dict[str, Any]) -> str:
    safe_payload = {
        "clean_points_hash": "sha256:" + hashlib.sha256(
            _json_dumps(normalized.get("clean_points") or []).encode("utf-8")
        ).hexdigest(),
        "quality_summary": build_cycling_power_stream_quality_summary(normalized),
        "scope": normalized.get("scope") or {},
    }
    return "sha256:" + hashlib.sha256(_json_dumps(safe_payload).encode("utf-8")).hexdigest()


def _cycling_power_intervals_from_clean_points(
    clean_points: list[dict[str, Any]],
    *,
    gap_threshold_sec: float,
) -> list[dict[str, float]]:
    intervals: list[dict[str, float]] = []
    for prev, current in zip(clean_points, clean_points[1:]):
        start = _finite_float(prev.get("t_sec"))
        end = _finite_float(current.get("t_sec"))
        power = _finite_float(prev.get("power_w"))
        if start is None or end is None or power is None:
            continue
        duration = end - start
        if duration <= 0 or duration > gap_threshold_sec:
            continue
        intervals.append({"start_sec": start, "end_sec": end, "power_w": power})
    return intervals


def _cycling_power_interval_groups(intervals: list[dict[str, float]]) -> list[list[dict[str, float]]]:
    groups: list[list[dict[str, float]]] = []
    current: list[dict[str, float]] = []
    previous_end: float | None = None
    for interval in intervals:
        start = float(interval["start_sec"])
        if previous_end is not None and abs(start - previous_end) > 1e-6:
            if current:
                groups.append(current)
            current = []
        current.append(interval)
        previous_end = float(interval["end_sec"])
    if current:
        groups.append(current)
    return groups


def _integrate_power_intervals(
    intervals: list[dict[str, float]],
    *,
    start_sec: float,
    end_sec: float,
) -> float | None:
    if end_sec <= start_sec:
        return None
    total = 0.0
    covered = 0.0
    for interval in intervals:
        overlap_start = max(start_sec, float(interval["start_sec"]))
        overlap_end = min(end_sec, float(interval["end_sec"]))
        if overlap_end <= overlap_start:
            continue
        duration = overlap_end - overlap_start
        covered += duration
        total += duration * float(interval["power_w"])
    if abs(covered - (end_sec - start_sec)) > 1e-6:
        return None
    return total


def _best_cycling_power_window(
    intervals: list[dict[str, float]],
    *,
    duration_sec: int,
) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    epsilon = 1e-9
    for group in _cycling_power_interval_groups(intervals):
        group_start = float(group[0]["start_sec"])
        group_end = float(group[-1]["end_sec"])
        if group_end - group_start + epsilon < duration_sec:
            continue
        candidate_starts = {group_start}
        for interval in group:
            start = float(interval["start_sec"])
            end = float(interval["end_sec"])
            if group_start <= start <= group_end - duration_sec + epsilon:
                candidate_starts.add(start)
            shifted = end - duration_sec
            if group_start <= shifted <= group_end - duration_sec + epsilon:
                candidate_starts.add(shifted)
        for candidate_start in sorted(candidate_starts):
            candidate_end = candidate_start + duration_sec
            if candidate_end > group_end + epsilon:
                continue
            total = _integrate_power_intervals(group, start_sec=candidate_start, end_sec=candidate_end)
            if total is None:
                continue
            average = total / duration_sec
            if best is None or average > best["value"] + epsilon or (
                abs(average - best["value"]) <= epsilon and candidate_start < best["range"]["start_sec"]
            ):
                best = {
                    "value": round(average, 3),
                    "duration_sec": int(duration_sec),
                    "unit": "watts",
                    "range": {
                        "start_sec": round(candidate_start, 3),
                        "end_sec": round(candidate_end, 3),
                    },
                }
    return best


def _cycling_power_anchor(duration_sec: int, best: dict[str, Any] | None, base_reason_codes: list[str]) -> dict[str, Any]:
    if best is None:
        return {
            "duration_sec": int(duration_sec),
            "value": None,
            "unit": "watts",
            "range": {},
            "quality": {
                "state": "unavailable",
                "reason_codes": sorted(dict.fromkeys([*base_reason_codes, "activity_shorter_than_window"])),
            },
        }
    return {
        "duration_sec": int(duration_sec),
        "value": best["value"],
        "unit": "watts",
        "range": best["range"],
        "quality": {
            "state": "ready" if not base_reason_codes else "candidate",
            "reason_codes": sorted(dict.fromkeys(base_reason_codes)),
        },
    }


def resolve_cycling_power_duration_curve(
    power_points: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    *,
    activity: dict[str, Any] | None = None,
    windows_sec: tuple[int, ...] | list[int] | None = None,
    algorithm_version: str = CYCLING_POWER_DURATION_CURVE_ALGORITHM_VERSION,
    conn: sqlite3.Connection | None = None,
    use_cache: bool = True,
    refresh: bool = False,
) -> dict[str, Any]:
    """Build or read a safe derived cycling power-duration curve cache."""
    start = time.perf_counter()
    normalized = normalize_cycling_power_stream_for_records(power_points, activity=activity)
    quality_summary = build_cycling_power_stream_quality_summary(normalized)
    scope = normalized.get("scope") or {}
    activity_id = str((activity or {}).get("activity_id") or (activity or {}).get("id") or "")
    windows = tuple(int(value) for value in (windows_sec or CYCLING_POWER_DURATION_WINDOWS_SEC) if int(value) > 0)
    stream_hash = _cycling_power_stream_hash(normalized)
    input_fingerprint = compute_career_record_curve_input_fingerprint(
        activity_id=activity_id or "activity:unknown",
        sport="cycling",
        source_mode="best_effort_duration",
        canonical_facts_version="records-v2.cycling-power-stream.v1",
        stream_summary_hash=stream_hash,
        algorithm_version=algorithm_version,
        rule_version=RECORDS_V2_RULE_VERSION,
        scope=scope,
    )
    if conn is not None and use_cache and not refresh and activity_id:
        cached = get_career_record_curve_cache(
            activity_id=activity_id,
            curve_type="cycling_power_duration_curve",
            source_mode="best_effort_duration",
            scope=scope,
            input_fingerprint=input_fingerprint,
            algorithm_version=algorithm_version,
            conn=conn,
        )
        if cached is not None:
            cached_curve = dict(cached.get("curve") or {})
            if "points" not in cached_curve and isinstance(cached_curve.get("anchors"), list):
                cached_curve["points"] = [
                    {
                        "x": anchor.get("duration_sec"),
                        "y": anchor.get("value"),
                        "quality_state": (anchor.get("quality") or {}).get("state") if isinstance(anchor, dict) else None,
                    }
                    for anchor in cached_curve["anchors"]
                    if isinstance(anchor, dict)
                ]
            return {
                "curve": cached_curve,
                "quality": cached.get("quality") or {},
                "cache": {
                    "hit": True,
                    "cache_id": cached.get("id"),
                    "input_fingerprint": input_fingerprint,
                    "algorithm_version": algorithm_version,
                },
                "metrics": {"elapsed_ms": _elapsed_ms(start), "window_count": len(windows)},
            }

    gap_threshold = _finite_float(quality_summary.get("gap_threshold_sec")) or CYCLING_POWER_STREAM_DEFAULT_CONFIG["max_gap_sec"]
    intervals = _cycling_power_intervals_from_clean_points(normalized.get("clean_points") or [], gap_threshold_sec=gap_threshold)
    base_reason_codes = list(normalized.get("reason_codes") or [])
    anchors: list[dict[str, Any]] = []
    for duration_sec in windows:
        best = _best_cycling_power_window(intervals, duration_sec=duration_sec)
        anchors.append(_cycling_power_anchor(duration_sec, best, base_reason_codes))
    points = [
        {
            "x": anchor["duration_sec"],
            "y": anchor["value"],
            "quality_state": (anchor.get("quality") or {}).get("state"),
        }
        for anchor in anchors
    ]
    available_anchors = [anchor for anchor in anchors if anchor.get("value") is not None]
    curve = {
        "curve_type": "cycling_power_duration_curve",
        "algorithm_version": algorithm_version,
        "unit": "watts",
        "source_mode": "best_effort_duration",
        "scope": scope,
        "anchors": anchors,
        "points": points,
        "axis": {
            "x": {"unit": "seconds", "scale": "duration"},
            "y": {"unit": "watts", "direction": "higher"},
        },
    }
    quality = {
        "state": "ready" if quality_summary.get("state") == "high" else quality_summary.get("state", "ignored"),
        "reason_codes": sorted(dict.fromkeys(base_reason_codes)),
        "stream_quality": quality_summary,
        "available_anchor_count": len(available_anchors),
        "missing_anchor_count": len(anchors) - len(available_anchors),
        "input_fingerprint": input_fingerprint,
        "algorithm_version": algorithm_version,
    }
    cache_info = {"hit": False, "cache_id": None, "input_fingerprint": input_fingerprint, "algorithm_version": algorithm_version}
    if conn is not None and use_cache and activity_id:
        cache_curve = dict(curve)
        cache_curve.pop("points", None)
        cached = save_career_record_curve_cache(
            activity_id=activity_id,
            sport="cycling",
            curve_type="cycling_power_duration_curve",
            source_mode="best_effort_duration",
            scope=scope,
            input_fingerprint=input_fingerprint,
            algorithm_version=algorithm_version,
            curve=cache_curve,
            quality=quality,
            conn=conn,
        )
        cache_info["cache_id"] = cached.get("id")
    return {
        "curve": curve,
        "quality": quality,
        "cache": cache_info,
        "metrics": {"elapsed_ms": _elapsed_ms(start), "window_count": len(windows)},
    }


def _cycling_power_event_date(activity: dict[str, Any] | None) -> str:
    if not isinstance(activity, dict):
        return ""
    for key in ("event_date", "start_time", "start_time_utc", "date"):
        value = str(activity.get(key) or "").strip()
        if value:
            return value[:10]
    return ""


def _cycling_power_anchor_confidence(anchor: dict[str, Any], stream_quality: dict[str, Any]) -> float:
    state = str((anchor.get("quality") or {}).get("state") or "")
    stream_state = str(stream_quality.get("state") or "")
    if state == "ready" and stream_state in {"high", "ready"}:
        return 0.98
    if state in {"candidate", "ready"} and stream_state not in {"ignored", "unavailable"}:
        return 0.80
    return 0.0


def _cycling_power_anchor_decision(confidence: float, reason_codes: list[str]) -> str:
    if confidence <= 0:
        return "ignored"
    if reason_codes:
        return "candidate"
    return _record_candidate_decision(confidence)


def build_cycling_power_record_evidences(
    power_points: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    *,
    activity: dict[str, Any] | None = None,
    windows_sec: tuple[int, ...] | list[int] | None = None,
    conn: sqlite3.Connection | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Build safe cycling power duration RecordEvidence objects from curve anchors."""
    curve_result = resolve_cycling_power_duration_curve(
        power_points,
        activity=activity,
        windows_sec=tuple(windows_sec or CYCLING_POWER_DURATION_WINDOWS_SEC),
        conn=conn,
        use_cache=use_cache,
    )
    curve = curve_result.get("curve") or {}
    stream_quality = ((curve_result.get("quality") or {}).get("stream_quality") or {})
    activity_id = str((activity or {}).get("activity_id") or (activity or {}).get("id") or "")
    event_date = _cycling_power_event_date(activity)
    evidences: list[RecordEvidence] = []
    skipped: list[dict[str, Any]] = []
    for anchor in curve.get("anchors") or []:
        if not isinstance(anchor, dict):
            continue
        duration_sec = _safe_int(anchor.get("duration_sec"))
        record_key = CYCLING_POWER_RECORD_KEY_BY_DURATION.get(duration_sec)
        if not record_key:
            skipped.append({"duration_sec": duration_sec, "reason": "unsupported_duration"})
            continue
        value = _finite_float(anchor.get("value"))
        range_data = anchor.get("range") if isinstance(anchor.get("range"), dict) else {}
        anchor_quality = anchor.get("quality") if isinstance(anchor.get("quality"), dict) else {}
        reason_codes = list(_dedupe_reason_codes(tuple(anchor_quality.get("reason_codes") or ())))
        if value is None or not range_data:
            skipped.append({
                "record_key": record_key,
                "duration_sec": duration_sec,
                "reason": "anchor_unavailable",
                "reason_codes": reason_codes or ["activity_shorter_than_window"],
            })
            continue
        confidence = _cycling_power_anchor_confidence(anchor, stream_quality)
        decision = _cycling_power_anchor_decision(confidence, reason_codes)
        quality = {
            "confidence": confidence,
            "confidence_band": _record_confidence_level(confidence),
            "decision": decision,
            "reason_codes": reason_codes,
            "source": "cycling_power_duration_curve",
            "quality_policy": "cycling_power_duration",
            "log_safety": "aggregate_only",
            "can_user_confirm": decision == "candidate",
            "blocks_active": decision != "auto_confirm",
        }
        evidence = build_record_evidence(
            record_key=record_key,
            activity_id=activity_id,
            sport="cycling",
            source_mode="best_effort_duration",
            metric_name="power_w",
            metric_value=value,
            metric_unit="watts",
            event_date=event_date,
            scope=curve.get("scope") or {},
            range_data={
                "start_sec": range_data.get("start_sec"),
                "end_sec": range_data.get("end_sec"),
                "duration_sec": duration_sec,
            },
            quality=quality,
            resolver_version=RECORDS_V2_RULE_VERSION,
            rule_version=RECORDS_V2_RULE_VERSION,
        )
        evidences.append(evidence)
    return {
        "curve": curve,
        "quality": curve_result.get("quality") or {},
        "cache": curve_result.get("cache") or {},
        "evidences": evidences,
        "skipped": skipped,
    }


def apply_cycling_power_duration_records(
    conn: sqlite3.Connection,
    power_points: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    *,
    activity: dict[str, Any] | None = None,
    windows_sec: tuple[int, ...] | list[int] | None = None,
    dry_run: bool = True,
    run_id: str = "",
    use_cache: bool = True,
) -> dict[str, Any]:
    """Plan or apply cycling power duration records through the V2 state machine."""
    ensure_career_schema(conn)
    plan = build_cycling_power_record_evidences(
        power_points,
        activity=activity,
        windows_sec=windows_sec,
        conn=conn,
        use_cache=use_cache,
    )
    evidence_payloads = [evidence.to_dict() for evidence in plan["evidences"]]
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "activity_id": str((activity or {}).get("activity_id") or (activity or {}).get("id") or ""),
            "planned_count": len(evidence_payloads),
            "evidences": evidence_payloads,
            "skipped": plan["skipped"],
            "cache": plan["cache"],
        }
    results: list[dict[str, Any]] = []
    summary: dict[str, int] = {}
    for evidence in plan["evidences"]:
        payload = evidence.to_dict()
        quality = payload.get("quality") if isinstance(payload.get("quality"), dict) else {}
        result = apply_record_evidence_state(
            conn,
            evidence,
            confidence=_safe_float(quality.get("confidence")),
            run_id=run_id,
            decision_source="cycling_power_resolver",
        )
        action = str(result.get("action") or "unknown")
        summary[action] = int(summary.get(action) or 0) + 1
        results.append({
            "record_key": payload.get("record_key"),
            "activity_id": payload.get("activity_id"),
            "action": action,
            "result": result,
        })
    return {
        "ok": True,
        "dry_run": False,
        "activity_id": str((activity or {}).get("activity_id") or (activity or {}).get("id") or ""),
        "applied_count": len(results),
        "summary": summary,
        "results": results,
        "skipped": plan["skipped"],
        "cache": plan["cache"],
    }


def _cycling_activity_metric_float(activity: dict[str, Any] | None, *keys: str) -> float | None:
    if not isinstance(activity, dict):
        return None
    for key in keys:
        value = _finite_float(activity.get(key))
        if value is not None and value > 0:
            return value
    return None


def _cycling_activity_is_indoor_without_metric(activity: dict[str, Any] | None, metric_value: float | None) -> bool:
    return _cycling_indoor_scope(activity) == "trainer" and (metric_value is None or metric_value <= 0)


def resolve_cycling_wkg_gate(
    activity: dict[str, Any] | None = None,
    *,
    weight_history: list[dict[str, Any]] | None = None,
    max_days_delta: int = 7,
) -> dict[str, Any]:
    """Resolve whether W/kg facts are allowed; never creates a record by itself."""
    event_date = _cycling_power_event_date(activity)
    if not event_date or not weight_history:
        return {
            "state": "unavailable",
            "evidence_created": False,
            "reason_codes": ["historical_weight_missing"],
        }
    try:
        event_dt = datetime.fromisoformat(event_date).date()
    except ValueError:
        return {
            "state": "unavailable",
            "evidence_created": False,
            "reason_codes": ["historical_weight_missing"],
        }
    best: tuple[int, float] | None = None
    for item in weight_history:
        if not isinstance(item, dict):
            continue
        weight = _finite_float(item.get("weight_kg") or item.get("weight"))
        date_text = str(item.get("date") or item.get("measured_at") or "").strip()[:10]
        if weight is None or not (25 <= weight <= 250) or not date_text:
            continue
        try:
            measured_dt = datetime.fromisoformat(date_text).date()
        except ValueError:
            continue
        delta = abs((event_dt - measured_dt).days)
        if delta <= int(max_days_delta) and (best is None or delta < best[0]):
            best = (delta, weight)
    if best is None:
        return {
            "state": "unavailable",
            "evidence_created": False,
            "reason_codes": ["historical_weight_missing"],
        }
    return {
        "state": "available",
        "evidence_created": False,
        "weight_kg": round(best[1], 3),
        "days_delta": best[0],
        "reason_codes": ["historical_weight_available", "wkg_registry_not_enabled"],
    }


def _cycling_activity_work_from_power(
    power_points: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    *,
    activity: dict[str, Any] | None,
) -> tuple[float | None, dict[str, Any]]:
    normalized = normalize_cycling_power_stream_for_records(power_points, activity=activity)
    summary = build_cycling_power_stream_quality_summary(normalized)
    avg_power = _finite_float(summary.get("time_weighted_avg_power_w"))
    covered = _finite_float(summary.get("covered_duration_sec"))
    if avg_power is None or covered is None or covered <= 0:
        return None, summary
    return round(avg_power * covered / 1000.0, 3), summary


def build_cycling_activity_total_record_evidences(
    *,
    activity: dict[str, Any] | None,
    power_points: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    weight_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build activity-total cycling record evidences without applying state."""
    activity = activity or {}
    activity_id = str(activity.get("activity_id") or activity.get("id") or "")
    event_date = _cycling_power_event_date(activity)
    scope_base = {
        "sport_scope": "cycling_regular",
        "indoor_scope": _cycling_indoor_scope(activity),
    }
    if _is_ebike_activity(activity):
        return {
            "evidences": [],
            "skipped": [{"record_key": "cycling_activity_total", "reason": "ebike_scope_excluded"}],
            "wkg_gate": resolve_cycling_wkg_gate(activity, weight_history=weight_history),
        }
    distance_m = _cycling_activity_metric_float(activity, "distance_m", "distance")
    ascent_m = _cycling_activity_metric_float(activity, "ascent_m", "total_ascent", "gain_m", "elevation_gain_m", "elevation_gain")
    elapsed_sec = _cycling_activity_metric_float(activity, "elapsed_time_sec", "duration_sec", "duration", "timer_time_sec")
    work_kj, power_quality = _cycling_activity_work_from_power(power_points, activity=activity)
    work_source = "power_stream" if work_kj is not None else ""
    if work_kj is None:
        work_kj = _cycling_activity_metric_float(activity, "work_kj", "total_work_kj", "mechanical_work_kj")
        work_source = "activity_summary" if work_kj is not None else ""

    specs = [
        ("cycling_longest_distance", distance_m, "distance_m", "meters", dict(scope_base), []),
        ("cycling_max_ascent", ascent_m, "ascent_m", "meters_ascent", dict(scope_base), []),
        ("cycling_longest_elapsed_time", elapsed_sec, "elapsed_time_sec", "seconds", dict(scope_base), []),
        ("cycling_max_work", work_kj, "work_kj", "kilojoules", {**scope_base, "power_metric_scope": "raw_power_w"}, ["work_integration_quality_unknown"] if work_source != "power_stream" else list(power_quality.get("reason_codes") or [])),
    ]
    evidences: list[RecordEvidence] = []
    skipped: list[dict[str, Any]] = []
    for record_key, value, metric_name, unit, scope, reason_codes in specs:
        if record_key in {"cycling_longest_distance", "cycling_max_ascent"} and _cycling_activity_is_indoor_without_metric(activity, value):
            skipped.append({"record_key": record_key, "reason": "not_applicable_indoor_metric_missing"})
            continue
        if value is None or value <= 0:
            skipped.append({"record_key": record_key, "reason": "metric_missing"})
            continue
        definition = get_record_definition(record_key)
        confidence = 0.98 if not reason_codes else 0.80
        decision = _record_candidate_decision(confidence) if not reason_codes else "candidate"
        quality = {
            "confidence": confidence,
            "confidence_band": _record_confidence_level(confidence),
            "decision": decision,
            "reason_codes": reason_codes,
            "source": work_source or "activity_total",
            "quality_policy": definition.quality_policy if definition else "cycling_activity_total",
            "log_safety": "aggregate_only",
            "can_user_confirm": decision == "candidate",
            "blocks_active": decision != "auto_confirm",
        }
        evidences.append(build_record_evidence(
            record_key=record_key,
            activity_id=activity_id,
            sport="cycling",
            source_mode="activity_total",
            metric_name=metric_name,
            metric_value=round(float(value), 3),
            metric_unit=unit,
            event_date=event_date,
            scope=scope,
            quality=quality,
            resolver_version=RECORDS_V2_RULE_VERSION,
            rule_version=RECORDS_V2_RULE_VERSION,
        ))
    return {
        "evidences": evidences,
        "skipped": skipped,
        "wkg_gate": resolve_cycling_wkg_gate(activity, weight_history=weight_history),
        "power_quality": power_quality,
    }


def apply_cycling_activity_total_records(
    conn: sqlite3.Connection,
    *,
    activity: dict[str, Any] | None,
    power_points: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    weight_history: list[dict[str, Any]] | None = None,
    dry_run: bool = True,
    run_id: str = "",
) -> dict[str, Any]:
    """Plan or apply cycling activity-total records through the V2 state machine."""
    ensure_career_schema(conn)
    plan = build_cycling_activity_total_record_evidences(
        activity=activity,
        power_points=power_points,
        weight_history=weight_history,
    )
    payloads = [evidence.to_dict() for evidence in plan["evidences"]]
    activity_id = str((activity or {}).get("activity_id") or (activity or {}).get("id") or "")
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "activity_id": activity_id,
            "planned_count": len(payloads),
            "evidences": payloads,
            "skipped": plan["skipped"],
            "wkg_gate": plan["wkg_gate"],
        }
    results: list[dict[str, Any]] = []
    summary: dict[str, int] = {}
    for evidence in plan["evidences"]:
        payload = evidence.to_dict()
        quality = payload.get("quality") if isinstance(payload.get("quality"), dict) else {}
        result = apply_record_evidence_state(
            conn,
            evidence,
            confidence=_safe_float(quality.get("confidence")),
            run_id=run_id,
            decision_source="cycling_activity_total_resolver",
        )
        action = str(result.get("action") or "unknown")
        summary[action] = int(summary.get(action) or 0) + 1
        results.append({"record_key": payload.get("record_key"), "action": action, "result": result})
    return {
        "ok": True,
        "dry_run": False,
        "activity_id": activity_id,
        "applied_count": len(results),
        "summary": summary,
        "results": results,
        "skipped": plan["skipped"],
        "wkg_gate": plan["wkg_gate"],
    }


def _hiking_activity_scope(activity: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(activity, dict):
        return {"accepted": False, "sport": "", "reason": "activity_id_missing"}
    tokens = [
        _normalise_cycling_scope_token(activity.get(key))
        for key in ("sport_type", "sport", "activity_type", "sub_sport_type", "sub_sport")
        if str(activity.get(key) or "").strip()
    ]
    if any(token in {"trail_running", "trail_run"} for token in tokens):
        return {"accepted": False, "sport": "trail_running", "reason": "record_definition_conflict"}
    if any(token in {"walking", "walk", "casual_walking", "indoor_walking"} for token in tokens):
        return {"accepted": False, "sport": "walking", "reason": "walking_scope_excluded"}
    if any(token in {"mountaineering", "mountain_climbing", "alpine_climbing"} for token in tokens):
        return {"accepted": False, "sport": "mountaineering", "reason": "mountaineering_scope_excluded"}
    if any(token in {"hiking", "hike", "trekking"} for token in tokens):
        return {"accepted": True, "sport": "hiking", "reason": "sport_hiking_scope"}
    return {"accepted": False, "sport": tokens[0] if tokens else "", "reason": "record_definition_conflict"}


def _hiking_activity_metric_float(activity: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _finite_float(activity.get(key))
        if value is not None and value > 0:
            return value
    return None


def build_hiking_activity_total_record_evidences(
    *,
    activity: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build hiking activity-total evidences without applying state."""
    activity = activity or {}
    scope = _hiking_activity_scope(activity)
    if not scope.get("accepted"):
        return {"evidences": [], "skipped": [{"record_key": "hiking_activity_total", "reason": scope.get("reason"), "sport": scope.get("sport")}]}
    activity_id = str(activity.get("activity_id") or activity.get("id") or "")
    event_date = _cycling_power_event_date(activity)
    distance_m = _hiking_activity_metric_float(activity, "distance_m", "distance")
    ascent_m = _hiking_activity_metric_float(activity, "ascent_m", "total_ascent", "gain_m", "elevation_gain_m", "elevation_gain")
    elapsed_sec = _hiking_activity_metric_float(activity, "elapsed_time_sec", "duration_sec", "timer_time_sec")
    elapsed_reason: list[str] = []
    if elapsed_sec is None:
        elapsed_sec = _hiking_activity_metric_float(activity, "duration")
        if elapsed_sec is not None:
            elapsed_reason.append("duration_semantics_unknown")
    max_altitude_m = _hiking_activity_metric_float(activity, "max_altitude_m", "max_alt_m", "max_altitude", "altitude_max")
    specs = [
        ("hiking_longest_distance", distance_m, "distance_m", "meters", []),
        ("hiking_max_ascent", ascent_m, "ascent_m", "meters_ascent", []),
        ("hiking_longest_elapsed_time", elapsed_sec, "elapsed_time_sec", "seconds", elapsed_reason),
        ("hiking_max_altitude", max_altitude_m, "max_altitude_m", "meters_altitude", []),
    ]
    evidences: list[RecordEvidence] = []
    skipped: list[dict[str, Any]] = []
    for record_key, value, metric_name, unit, reason_codes in specs:
        if value is None or value <= 0:
            skipped.append({"record_key": record_key, "reason": "metric_missing"})
            continue
        confidence = 0.98 if not reason_codes else 0.80
        decision = _record_candidate_decision(confidence) if not reason_codes else "candidate"
        definition = get_record_definition(record_key)
        quality = {
            "confidence": confidence,
            "confidence_band": _record_confidence_level(confidence),
            "decision": decision,
            "reason_codes": reason_codes,
            "source": "activity_total",
            "quality_policy": definition.quality_policy if definition else "hiking_activity_total",
            "log_safety": "aggregate_only",
            "can_user_confirm": decision == "candidate",
            "blocks_active": decision != "auto_confirm",
        }
        evidences.append(build_record_evidence(
            record_key=record_key,
            activity_id=activity_id,
            sport="hiking",
            source_mode="activity_total",
            metric_name=metric_name,
            metric_value=round(float(value), 3),
            metric_unit=unit,
            event_date=event_date,
            scope={"sport_scope": "hiking"},
            quality=quality,
            resolver_version=RECORDS_V2_RULE_VERSION,
            rule_version=RECORDS_V2_RULE_VERSION,
        ))
    return {"evidences": evidences, "skipped": skipped}


def apply_hiking_activity_total_records(
    conn: sqlite3.Connection,
    *,
    activity: dict[str, Any] | None,
    dry_run: bool = True,
    run_id: str = "",
) -> dict[str, Any]:
    """Plan or apply hiking activity-total records through the V2 state machine."""
    ensure_career_schema(conn)
    plan = build_hiking_activity_total_record_evidences(activity=activity)
    payloads = [evidence.to_dict() for evidence in plan["evidences"]]
    activity_id = str((activity or {}).get("activity_id") or (activity or {}).get("id") or "")
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "activity_id": activity_id,
            "planned_count": len(payloads),
            "evidences": payloads,
            "skipped": plan["skipped"],
        }
    results: list[dict[str, Any]] = []
    summary: dict[str, int] = {}
    for evidence in plan["evidences"]:
        payload = evidence.to_dict()
        quality = payload.get("quality") if isinstance(payload.get("quality"), dict) else {}
        result = apply_record_evidence_state(
            conn,
            evidence,
            confidence=_safe_float(quality.get("confidence")),
            run_id=run_id,
            decision_source="hiking_activity_total_resolver",
        )
        action = str(result.get("action") or "unknown")
        summary[action] = int(summary.get(action) or 0) + 1
        results.append({"record_key": payload.get("record_key"), "action": action, "result": result})
    return {
        "ok": True,
        "dry_run": False,
        "activity_id": activity_id,
        "applied_count": len(results),
        "summary": summary,
        "results": results,
        "skipped": plan["skipped"],
    }


HIKING_ELEVATION_DEFAULT_CONFIG = {
    "spike_threshold_m": 35.0,
    "flat_tolerance_m": 2.0,
    "min_climb_gain_m": 1.0,
}


def _hiking_track_point_value(point: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _finite_float(point.get(key))
        if value is not None:
            return value
    return None


def resolve_hiking_elevation_climb(
    track_points: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve safe hiking elevation quality and max continuous climb from track points."""
    cfg = dict(HIKING_ELEVATION_DEFAULT_CONFIG)
    if isinstance(config, dict):
        for key in cfg:
            parsed = _finite_float(config.get(key))
            if parsed is not None and parsed >= 0:
                cfg[key] = parsed
    raw_points = list(track_points or [])
    parsed: list[dict[str, Any]] = []
    for index, point in enumerate(raw_points):
        if not isinstance(point, dict):
            continue
        alt = _hiking_track_point_value(point, "alt_m", "altitude_m", "altitude", "alt")
        if alt is None:
            continue
        t_sec = _hiking_track_point_value(point, "t", "time_sec", "elapsed_sec")
        d_m = _hiking_track_point_value(point, "d", "distance_m", "distance")
        parsed.append({
            "index": index,
            "t_sec": t_sec,
            "distance_m": d_m,
            "alt_m": alt,
        })
    if len(parsed) < 2:
        return {
            "quality": "ignored",
            "reason_codes": ["elevation_missing"],
            "clean_points": [],
            "spike_point_indexes": [],
            "max_single_climb": None,
        }
    spikes: list[int] = []
    for i in range(1, len(parsed) - 1):
        if int(parsed[i - 1]["index"]) in set(spikes):
            continue
        prev_alt = float(parsed[i - 1]["alt_m"])
        current_alt = float(parsed[i]["alt_m"])
        next_alt = float(parsed[i + 1]["alt_m"])
        delta_prev = current_alt - prev_alt
        delta_next = next_alt - current_alt
        if (
            delta_prev * delta_next < 0
            and abs(delta_prev) > float(cfg["spike_threshold_m"])
            and abs(delta_next) > float(cfg["spike_threshold_m"])
        ):
            spikes.append(int(parsed[i]["index"]))
    clean_points = [point for point in parsed if int(point["index"]) not in set(spikes)]
    best: dict[str, Any] | None = None
    current_start = clean_points[0]
    current_gain = 0.0
    current_end = clean_points[0]
    for prev, current in zip(clean_points, clean_points[1:]):
        delta = float(current["alt_m"]) - float(prev["alt_m"])
        if delta >= -float(cfg["flat_tolerance_m"]):
            if delta > 0:
                current_gain += delta
                current_end = current
            continue
        if current_gain >= float(cfg["min_climb_gain_m"]) and (best is None or current_gain > best["gain_m"]):
            best = {"gain_m": round(current_gain, 3), "start": current_start, "end": current_end}
        current_start = current
        current_gain = 0.0
        current_end = current
    if current_gain >= float(cfg["min_climb_gain_m"]) and (best is None or current_gain > best["gain_m"]):
        best = {"gain_m": round(current_gain, 3), "start": current_start, "end": current_end}
    reason_codes = ["elevation_spike_detected"] if spikes else []
    quality = "candidate" if spikes else "high"
    return {
        "quality": quality,
        "reason_codes": reason_codes,
        "clean_points": clean_points,
        "spike_point_indexes": spikes,
        "max_single_climb": best,
    }


def build_hiking_single_climb_record_evidence(
    *,
    activity: dict[str, Any] | None,
    track_points: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
) -> dict[str, Any]:
    activity = activity or {}
    scope = _hiking_activity_scope(activity)
    if not scope.get("accepted"):
        return {"evidence": None, "skipped": [{"record_key": "hiking_max_single_climb", "reason": scope.get("reason")}], "climb": None}
    climb = resolve_hiking_elevation_climb(track_points)
    best = climb.get("max_single_climb") if isinstance(climb.get("max_single_climb"), dict) else None
    if not best:
        return {"evidence": None, "skipped": [{"record_key": "hiking_max_single_climb", "reason": "single_climb_range_missing"}], "climb": climb}
    start_point = best["start"]
    end_point = best["end"]
    reason_codes = list(climb.get("reason_codes") or [])
    confidence = 0.80 if reason_codes else 0.98
    quality = {
        "confidence": confidence,
        "confidence_band": _record_confidence_level(confidence),
        "decision": "candidate" if reason_codes else "auto_confirm",
        "reason_codes": reason_codes,
        "source": "elevation_track",
        "quality_policy": "hiking_single_climb",
        "log_safety": "aggregate_only",
        "can_user_confirm": True,
        "blocks_active": True,
    }
    evidence = build_record_evidence(
        record_key="hiking_max_single_climb",
        activity_id=str(activity.get("activity_id") or activity.get("id") or ""),
        sport="hiking",
        source_mode="activity_total",
        metric_name="single_climb_m",
        metric_value=best["gain_m"],
        metric_unit="meters_ascent",
        event_date=_cycling_power_event_date(activity),
        scope={"sport_scope": "hiking"},
        range_data={
            "start_sec": start_point.get("t_sec"),
            "end_sec": end_point.get("t_sec"),
            "start_distance_m": start_point.get("distance_m"),
            "end_distance_m": end_point.get("distance_m"),
        },
        quality=quality,
        resolver_version=RECORDS_V2_RULE_VERSION,
        rule_version=RECORDS_V2_RULE_VERSION,
    )
    return {"evidence": evidence, "skipped": [], "climb": climb}


def apply_hiking_single_climb_record(
    conn: sqlite3.Connection,
    *,
    activity: dict[str, Any] | None,
    track_points: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    dry_run: bool = True,
    run_id: str = "",
) -> dict[str, Any]:
    ensure_career_schema(conn)
    plan = build_hiking_single_climb_record_evidence(activity=activity, track_points=track_points)
    evidence = plan.get("evidence")
    activity_id = str((activity or {}).get("activity_id") or (activity or {}).get("id") or "")
    if dry_run or evidence is None:
        return {
            "ok": True,
            "dry_run": dry_run,
            "activity_id": activity_id,
            "planned_count": 1 if evidence else 0,
            "evidence": evidence.to_dict() if isinstance(evidence, RecordEvidence) else None,
            "skipped": plan.get("skipped") or [],
            "climb": {k: v for k, v in (plan.get("climb") or {}).items() if k != "clean_points"},
        }
    payload = evidence.to_dict()
    quality = payload.get("quality") if isinstance(payload.get("quality"), dict) else {}
    result = apply_record_evidence_state(
        conn,
        evidence,
        confidence=_safe_float(quality.get("confidence")),
        run_id=run_id,
        decision_source="hiking_single_climb_resolver",
    )
    return {
        "ok": True,
        "dry_run": False,
        "activity_id": activity_id,
        "applied_count": 1,
        "result": result,
        "skipped": [],
        "climb": {k: v for k, v in (plan.get("climb") or {}).items() if k != "clean_points"},
    }


SWIM_CANONICAL_ACTIVITY_COLUMNS = {
    "swim_water_scope": "TEXT",
    "swim_pool_length_m": "REAL",
    "swim_pool_length_scope": "TEXT",
    "swim_stroke_scope": "TEXT",
    "swim_facts_quality_json": "TEXT NOT NULL DEFAULT '{}'",
}


def plan_swim_canonical_facts_schema_migration(conn: sqlite3.Connection) -> dict[str, Any]:
    """Plan swim canonical fact columns without writing schema."""
    has_activities = _table_exists(conn, "activities")
    missing = []
    if has_activities:
        missing = [column for column in SWIM_CANONICAL_ACTIVITY_COLUMNS if not _column_exists(conn, "activities", column)]
    return {
        "ok": True,
        "dry_run": True,
        "table": "activities",
        "table_exists": has_activities,
        "missing_columns": missing,
        "column_sql": {column: SWIM_CANONICAL_ACTIVITY_COLUMNS[column] for column in missing},
    }


def apply_swim_canonical_facts_schema_migration(conn: sqlite3.Connection, *, dry_run: bool = True) -> dict[str, Any]:
    plan = plan_swim_canonical_facts_schema_migration(conn)
    if dry_run or not plan["table_exists"]:
        return plan
    added: list[str] = []
    for column in plan["missing_columns"]:
        _add_column_if_missing(conn, "activities", column, SWIM_CANONICAL_ACTIVITY_COLUMNS[column], added)
    return {**plan, "dry_run": False, "added_columns": added}


def _swim_scope_token(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def _normalize_swim_stroke(value: Any) -> str:
    token = _swim_scope_token(value)
    aliases = {
        "free": "freestyle",
        "front_crawl": "freestyle",
        "crawl": "freestyle",
        "back": "backstroke",
        "breast": "breaststroke",
        "fly": "butterfly",
    }
    token = aliases.get(token, token)
    if token in {"freestyle", "backstroke", "breaststroke", "butterfly", "mixed"}:
        return token
    return "unknown"


def _normalize_pool_length_scope(pool_length_m: float | None, unit: Any = "m") -> tuple[str, list[str]]:
    if pool_length_m is None or pool_length_m <= 0:
        return "", ["pool_length_missing"]
    unit_token = _swim_scope_token(unit or "m")
    if unit_token in {"yard", "yards", "yd", "y"}:
        return "", ["pool_length_yards_unsupported"]
    if abs(pool_length_m - 25.0) < 0.01:
        return "scm_25m", []
    if abs(pool_length_m - 50.0) < 0.01:
        return "scm_50m", []
    return f"scm_{pool_length_m:g}m", ["pool_length_non_standard"]


def normalize_swim_canonical_facts(
    *,
    activity: dict[str, Any] | None,
    lengths: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Normalize safe swim facts for later Records V2 swim resolvers."""
    activity = activity or {}
    sport_tokens = {
        _swim_scope_token(activity.get(key))
        for key in ("sport_type", "sport", "sub_sport_type", "sub_sport", "water_scope")
        if str(activity.get(key) or "").strip()
    }
    reason_codes: list[str] = []
    if sport_tokens & {"lap_swimming", "pool_swimming", "pool"}:
        water_scope = "pool_swimming"
    elif sport_tokens & {"open_water", "open_water_swimming", "openwater_swimming"}:
        water_scope = "open_water_swimming"
    elif "swimming" in sport_tokens:
        water_scope = "unknown"
        reason_codes.append("water_scope_unknown")
    else:
        water_scope = "not_swimming"
        reason_codes.append("record_definition_conflict")
    pool_length = _finite_float(activity.get("pool_length_m") or activity.get("pool_length"))
    pool_length_scope = ""
    if water_scope == "pool_swimming":
        pool_length_scope, pool_reasons = _normalize_pool_length_scope(pool_length, activity.get("pool_length_unit") or "m")
        reason_codes.extend(pool_reasons)
    stroke_scope = _normalize_swim_stroke(activity.get("stroke_scope") or activity.get("swim_stroke") or activity.get("stroke"))
    if stroke_scope == "unknown":
        reason_codes.append("swim_stroke_unknown")
    normalized_lengths: list[dict[str, Any]] = []
    if lengths and water_scope == "pool_swimming" and pool_length_scope:
        for index, item in enumerate(lengths):
            if not isinstance(item, dict):
                continue
            elapsed = _finite_float(item.get("elapsed_sec") or item.get("active_time_sec") or item.get("duration_sec"))
            if elapsed is None or elapsed <= 0:
                continue
            rest_after = _finite_float(item.get("rest_after_sec") or item.get("rest_sec")) or 0.0
            length_stroke = _normalize_swim_stroke(item.get("stroke") or item.get("swim_stroke") or stroke_scope)
            normalized_lengths.append({
                "index": int(item.get("index") if item.get("index") is not None else index),
                "distance_m": pool_length,
                "elapsed_sec": elapsed,
                "rest_after_sec": rest_after,
                "stroke_scope": length_stroke,
            })
    quality_state = "high" if not reason_codes else "candidate"
    if water_scope == "not_swimming" or "pool_length_missing" in reason_codes or "pool_length_yards_unsupported" in reason_codes:
        quality_state = "ignored"
    return {
        "water_scope": water_scope,
        "pool_length_m": pool_length if water_scope == "pool_swimming" else None,
        "pool_length_scope": pool_length_scope,
        "stroke_scope": stroke_scope,
        "lengths": normalized_lengths,
        "quality": {
            "state": quality_state,
            "reason_codes": list(_dedupe_reason_codes(tuple(reason_codes))),
            "candidate_only": quality_state == "candidate",
        },
    }


POOL_SWIM_RECORD_KEY_BY_DISTANCE = {
    50: "pool_swim_50m",
    100: "pool_swim_100m",
    200: "pool_swim_200m",
    400: "pool_swim_400m",
    800: "pool_swim_800m",
    1500: "pool_swim_1500m",
}


def build_pool_swim_best_effort_evidences(
    *,
    activity: dict[str, Any] | None,
    lengths: list[dict[str, Any]] | None,
    target_distances_m: tuple[int, ...] | list[int] | None = None,
) -> dict[str, Any]:
    facts = normalize_swim_canonical_facts(activity=activity, lengths=lengths)
    activity = activity or {}
    if facts["water_scope"] != "pool_swimming" or not facts.get("pool_length_scope"):
        return {"evidences": [], "skipped": [{"reason": "pool_length_missing", "record_key": "pool_swim"}], "facts": facts}
    canonical_lengths = facts.get("lengths") or []
    pool_length = _finite_float(facts.get("pool_length_m"))
    if pool_length is None or pool_length <= 0:
        return {"evidences": [], "skipped": [{"reason": "pool_length_missing", "record_key": "pool_swim"}], "facts": facts}
    targets = tuple(int(value) for value in (target_distances_m or tuple(POOL_SWIM_RECORD_KEY_BY_DISTANCE)) if int(value) > 0)
    evidences: list[RecordEvidence] = []
    skipped: list[dict[str, Any]] = []
    for distance_m in targets:
        record_key = POOL_SWIM_RECORD_KEY_BY_DISTANCE.get(distance_m)
        if not record_key:
            skipped.append({"record_key": "pool_swim", "distance_m": distance_m, "reason": "unsupported_distance"})
            continue
        length_count_float = distance_m / pool_length
        if abs(length_count_float - round(length_count_float)) > 1e-6:
            skipped.append({"record_key": record_key, "reason": "pool_length_distance_mismatch"})
            continue
        length_count = int(round(length_count_float))
        best: dict[str, Any] | None = None
        for start in range(0, max(0, len(canonical_lengths) - length_count + 1)):
            window = canonical_lengths[start:start + length_count]
            if len(window) < length_count:
                continue
            if any((_finite_float(item.get("rest_after_sec")) or 0.0) > 0 for item in window[:-1]):
                continue
            elapsed = sum(float(item["elapsed_sec"]) for item in window)
            strokes = {str(item.get("stroke_scope") or "unknown") for item in window}
            stroke_scope = strokes.pop() if len(strokes) == 1 else "mixed"
            candidate = {
                "elapsed_sec": round(elapsed, 3),
                "length_start": int(window[0]["index"]),
                "length_end": int(window[-1]["index"]),
                "stroke_scope": stroke_scope,
            }
            if best is None or candidate["elapsed_sec"] < best["elapsed_sec"]:
                best = candidate
        if best is None:
            skipped.append({"record_key": record_key, "reason": "pool_rest_break" if canonical_lengths else "range_missing"})
            continue
        reason_codes: list[str] = []
        if best["stroke_scope"] == "unknown":
            reason_codes.append("swim_stroke_unknown")
        elif best["stroke_scope"] != "freestyle":
            reason_codes.append("swim_stroke_unknown" if best["stroke_scope"] == "mixed" else "candidate_only_registry")
        confidence = 0.98 if not reason_codes else 0.80
        quality = {
            "confidence": confidence,
            "confidence_band": _record_confidence_level(confidence),
            "decision": _record_candidate_decision(confidence) if not reason_codes else "candidate",
            "reason_codes": reason_codes,
            "source": "pool_lengths",
            "quality_policy": "pool_swim_best_effort",
            "log_safety": "aggregate_only",
            "can_user_confirm": True,
            "blocks_active": True,
        }
        evidences.append(build_record_evidence(
            record_key=record_key,
            activity_id=str(activity.get("activity_id") or activity.get("id") or ""),
            sport="pool_swimming",
            source_mode="best_effort_distance",
            metric_name="elapsed_time_sec",
            metric_value=best["elapsed_sec"],
            metric_unit="seconds",
            event_date=_cycling_power_event_date(activity),
            scope={
                "water_scope": "pool_swimming",
                "pool_length_scope": facts["pool_length_scope"],
                "stroke_scope": best["stroke_scope"],
            },
            range_data={
                "length_start": best["length_start"],
                "length_end": best["length_end"],
                "lap_count": length_count,
                "distance_m": distance_m,
            },
            quality=quality,
            resolver_version=RECORDS_V2_RULE_VERSION,
            rule_version=RECORDS_V2_RULE_VERSION,
        ))
    return {"evidences": evidences, "skipped": skipped, "facts": facts}


def apply_pool_swim_best_effort_records(
    conn: sqlite3.Connection,
    *,
    activity: dict[str, Any] | None,
    lengths: list[dict[str, Any]] | None,
    target_distances_m: tuple[int, ...] | list[int] | None = None,
    dry_run: bool = True,
    run_id: str = "",
) -> dict[str, Any]:
    ensure_career_schema(conn)
    plan = build_pool_swim_best_effort_evidences(activity=activity, lengths=lengths, target_distances_m=target_distances_m)
    payloads = [evidence.to_dict() for evidence in plan["evidences"]]
    if dry_run:
        return {"ok": True, "dry_run": True, "planned_count": len(payloads), "evidences": payloads, "skipped": plan["skipped"]}
    results: list[dict[str, Any]] = []
    summary: dict[str, int] = {}
    for evidence in plan["evidences"]:
        payload = evidence.to_dict()
        quality = payload.get("quality") if isinstance(payload.get("quality"), dict) else {}
        result = apply_record_evidence_state(
            conn,
            evidence,
            confidence=_safe_float(quality.get("confidence")),
            run_id=run_id,
            decision_source="pool_swim_best_effort_resolver",
        )
        action = str(result.get("action") or "unknown")
        summary[action] = int(summary.get(action) or 0) + 1
        results.append({"record_key": payload.get("record_key"), "action": action, "result": result})
    return {"ok": True, "dry_run": False, "applied_count": len(results), "summary": summary, "results": results, "skipped": plan["skipped"]}


OPEN_WATER_RECORD_KEY_BY_DISTANCE = {
    750: "open_water_swim_750m",
    1500: "open_water_swim_1500m",
    1900: "open_water_swim_1900m",
    3800: "open_water_swim_3800m",
    5000: "open_water_swim_5k",
    10000: "open_water_swim_10k",
}


def _open_water_track_quality(track_points_xy: list[dict[str, Any]] | None) -> list[str]:
    if not track_points_xy:
        return []
    reasons: list[str] = []
    previous: dict[str, Any] | None = None
    for point in track_points_xy:
        if not isinstance(point, dict):
            continue
        if previous is not None:
            x1 = _finite_float(previous.get("x"))
            y1 = _finite_float(previous.get("y"))
            x2 = _finite_float(point.get("x"))
            y2 = _finite_float(point.get("y"))
            if None not in (x1, y1, x2, y2):
                segment = ((float(x2) - float(x1)) ** 2 + (float(y2) - float(y1)) ** 2) ** 0.5
                if segment > 500:
                    reasons.append("open_water_gps_unreliable")
                    break
        previous = point
    return list(_dedupe_reason_codes(tuple(reasons)))


def build_open_water_record_evidences(
    *,
    activity: dict[str, Any] | None,
    track_points_xy: list[dict[str, Any]] | None = None,
    tolerance_ratio: float = 0.05,
) -> dict[str, Any]:
    activity = activity or {}
    facts = normalize_swim_canonical_facts(activity=activity)
    if facts.get("water_scope") != "open_water_swimming":
        return {"evidences": [], "skipped": [{"record_key": "open_water", "reason": "pool_swim_scope"}], "facts": facts}
    distance_m = _finite_float(activity.get("distance_m") or activity.get("distance"))
    elapsed_sec = _finite_float(activity.get("elapsed_time_sec") or activity.get("duration_sec") or activity.get("duration"))
    if distance_m is None or distance_m <= 0:
        return {"evidences": [], "skipped": [{"record_key": "open_water", "reason": "distance_missing"}], "facts": facts}
    reason_codes = _open_water_track_quality(track_points_xy)
    if str(activity.get("distance_source") or "").lower() in {"manual", "estimated"}:
        reason_codes.append("open_water_gps_unreliable")
    reason_codes = list(_dedupe_reason_codes(tuple(reason_codes)))
    evidences: list[RecordEvidence] = []
    skipped: list[dict[str, Any]] = []
    event_date = _cycling_power_event_date(activity)
    activity_id = str(activity.get("activity_id") or activity.get("id") or "")
    for standard_distance, record_key in OPEN_WATER_RECORD_KEY_BY_DISTANCE.items():
        error_ratio = abs(distance_m - standard_distance) / float(standard_distance)
        if error_ratio > tolerance_ratio:
            skipped.append({"record_key": record_key, "reason": "distance_outside_5_percent", "distance_error_ratio": round(error_ratio, 6)})
            continue
        if elapsed_sec is None or elapsed_sec <= 0:
            skipped.append({"record_key": record_key, "reason": "elapsed_time_missing"})
            continue
        quality_reasons = list(reason_codes)
        if not quality_reasons:
            quality_reasons.append("distance_within_5_percent")
        confidence = 0.80 if reason_codes else 0.98
        quality = {
            "confidence": confidence,
            "confidence_band": _record_confidence_level(confidence),
            "decision": "candidate" if reason_codes else "auto_confirm",
            "reason_codes": quality_reasons,
            "source": "open_water_activity_total",
            "quality_policy": "open_water_activity_total",
            "log_safety": "aggregate_only",
            "can_user_confirm": True,
            "blocks_active": True,
        }
        evidences.append(build_record_evidence(
            record_key=record_key,
            activity_id=activity_id,
            sport="open_water_swimming",
            source_mode="activity_total",
            metric_name="elapsed_time_sec",
            metric_value=elapsed_sec,
            metric_unit="seconds",
            event_date=event_date,
            scope={"water_scope": "open_water_swimming"},
            quality=quality,
            resolver_version=RECORDS_V2_RULE_VERSION,
            rule_version=RECORDS_V2_RULE_VERSION,
        ))
    for record_key, metric_name, value, unit in (
        ("open_water_longest_distance", "distance_m", distance_m, "meters"),
        ("open_water_longest_elapsed_time", "elapsed_time_sec", elapsed_sec, "seconds"),
    ):
        if value is None or value <= 0:
            skipped.append({"record_key": record_key, "reason": "metric_missing"})
            continue
        confidence = 0.80 if reason_codes else 0.98
        quality = {
            "confidence": confidence,
            "confidence_band": _record_confidence_level(confidence),
            "decision": "candidate" if reason_codes else "auto_confirm",
            "reason_codes": reason_codes,
            "source": "open_water_activity_total",
            "quality_policy": "open_water_activity_total",
            "log_safety": "aggregate_only",
            "can_user_confirm": True,
            "blocks_active": True,
        }
        evidences.append(build_record_evidence(
            record_key=record_key,
            activity_id=activity_id,
            sport="open_water_swimming",
            source_mode="activity_total",
            metric_name=metric_name,
            metric_value=value,
            metric_unit=unit,
            event_date=event_date,
            scope={"water_scope": "open_water_swimming"},
            quality=quality,
            resolver_version=RECORDS_V2_RULE_VERSION,
            rule_version=RECORDS_V2_RULE_VERSION,
        ))
    return {"evidences": evidences, "skipped": skipped, "facts": facts, "reason_codes": reason_codes}


def apply_open_water_records(
    conn: sqlite3.Connection,
    *,
    activity: dict[str, Any] | None,
    track_points_xy: list[dict[str, Any]] | None = None,
    dry_run: bool = True,
    run_id: str = "",
) -> dict[str, Any]:
    ensure_career_schema(conn)
    plan = build_open_water_record_evidences(activity=activity, track_points_xy=track_points_xy)
    payloads = [evidence.to_dict() for evidence in plan["evidences"]]
    if dry_run:
        return {"ok": True, "dry_run": True, "planned_count": len(payloads), "evidences": payloads, "skipped": plan["skipped"]}
    results: list[dict[str, Any]] = []
    summary: dict[str, int] = {}
    for evidence in plan["evidences"]:
        payload = evidence.to_dict()
        quality = payload.get("quality") if isinstance(payload.get("quality"), dict) else {}
        result = apply_record_evidence_state(
            conn,
            evidence,
            confidence=_safe_float(quality.get("confidence")),
            run_id=run_id,
            decision_source="open_water_resolver",
        )
        action = str(result.get("action") or "unknown")
        summary[action] = int(summary.get(action) or 0) + 1
        results.append({"record_key": payload.get("record_key"), "action": action, "result": result})
    return {"ok": True, "dry_run": False, "applied_count": len(results), "summary": summary, "results": results, "skipped": plan["skipped"]}


def _trail_activity_scope(activity: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(activity, dict):
        return {"accepted": False, "sport": "", "reason": "activity_id_missing"}
    tokens = [
        _normalise_cycling_scope_token(activity.get(key))
        for key in ("sport_type", "sport", "activity_type", "sub_sport_type", "sub_sport")
        if str(activity.get(key) or "").strip()
    ]
    if any(token in {"trail_running", "trail_run"} for token in tokens):
        return {"accepted": True, "sport": "trail_running", "reason": "sport_trail_running_scope"}
    if any(token in {"running", "run", "road_running", "track_running"} for token in tokens):
        return {"accepted": False, "sport": "running", "reason": "road_running_scope_excluded"}
    if any(token in {"hiking", "hike", "trekking"} for token in tokens):
        return {"accepted": False, "sport": "hiking", "reason": "record_definition_conflict"}
    if any(token in {"mountaineering", "mountain_climbing", "alpine_climbing"} for token in tokens):
        return {"accepted": False, "sport": "mountaineering", "reason": "record_definition_conflict"}
    return {"accepted": False, "sport": tokens[0] if tokens else "", "reason": "record_definition_conflict"}


def build_trail_activity_total_record_evidences(
    *,
    activity: dict[str, Any] | None,
    track_points: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    activity = activity or {}
    scope = _trail_activity_scope(activity)
    if not scope.get("accepted"):
        return {"evidences": [], "skipped": [{"record_key": "trail_activity_total", "reason": scope.get("reason"), "sport": scope.get("sport")}]}
    activity_id = str(activity.get("activity_id") or activity.get("id") or "")
    event_date = _cycling_power_event_date(activity)
    distance_m = _hiking_activity_metric_float(activity, "distance_m", "distance")
    ascent_m = _hiking_activity_metric_float(activity, "ascent_m", "total_ascent", "gain_m", "elevation_gain_m", "elevation_gain")
    elapsed_sec = _hiking_activity_metric_float(activity, "elapsed_time_sec", "duration_sec", "timer_time_sec", "duration")
    max_altitude_m = _hiking_activity_metric_float(activity, "max_altitude_m", "max_alt_m", "max_altitude", "altitude_max")
    specs = [
        ("trail_longest_distance", distance_m, "distance_m", "meters", {}, []),
        ("trail_max_ascent", ascent_m, "ascent_m", "meters_ascent", {}, []),
        ("trail_longest_elapsed_time", elapsed_sec, "elapsed_time_sec", "seconds", {}, []),
        ("trail_max_altitude", max_altitude_m, "max_altitude_m", "meters_altitude", {}, []),
    ]
    evidences: list[RecordEvidence] = []
    skipped: list[dict[str, Any]] = []
    for record_key, value, metric_name, unit, range_data, reason_codes in specs:
        if value is None or value <= 0:
            skipped.append({"record_key": record_key, "reason": "metric_missing"})
            continue
        confidence = 0.98 if not reason_codes else 0.80
        definition = get_record_definition(record_key)
        quality = {
            "confidence": confidence,
            "confidence_band": _record_confidence_level(confidence),
            "decision": "auto_confirm" if not reason_codes else "candidate",
            "reason_codes": reason_codes,
            "source": "activity_total",
            "quality_policy": definition.quality_policy if definition else "trail_activity_total",
            "log_safety": "aggregate_only",
            "can_user_confirm": True,
            "blocks_active": True,
        }
        evidences.append(build_record_evidence(
            record_key=record_key,
            activity_id=activity_id,
            sport="trail_running",
            source_mode="activity_total",
            metric_name=metric_name,
            metric_value=round(float(value), 3),
            metric_unit=unit,
            event_date=event_date,
            scope={"sport_scope": "trail_running"},
            range_data=range_data,
            quality=quality,
            resolver_version=RECORDS_V2_RULE_VERSION,
            rule_version=RECORDS_V2_RULE_VERSION,
        ))
    climb = resolve_hiking_elevation_climb(track_points or [])
    best = climb.get("max_single_climb") if isinstance(climb.get("max_single_climb"), dict) else None
    if best:
        start_point = best["start"]
        end_point = best["end"]
        reasons = list(climb.get("reason_codes") or [])
        confidence = 0.80 if reasons else 0.98
        evidences.append(build_record_evidence(
            record_key="trail_max_single_climb",
            activity_id=activity_id,
            sport="trail_running",
            source_mode="activity_total",
            metric_name="single_climb_m",
            metric_value=best["gain_m"],
            metric_unit="meters_ascent",
            event_date=event_date,
            scope={"sport_scope": "trail_running"},
            range_data={
                "start_sec": start_point.get("t_sec"),
                "end_sec": end_point.get("t_sec"),
                "start_distance_m": start_point.get("distance_m"),
                "end_distance_m": end_point.get("distance_m"),
            },
            quality={
                "confidence": confidence,
                "confidence_band": _record_confidence_level(confidence),
                "decision": "auto_confirm" if not reasons else "candidate",
                "reason_codes": reasons,
                "source": "elevation_track",
                "quality_policy": "trail_single_climb",
                "log_safety": "aggregate_only",
                "can_user_confirm": True,
                "blocks_active": True,
            },
            resolver_version=RECORDS_V2_RULE_VERSION,
            rule_version=RECORDS_V2_RULE_VERSION,
        ))
    else:
        skipped.append({"record_key": "trail_max_single_climb", "reason": "single_climb_range_missing"})
    return {"evidences": evidences, "skipped": skipped}


def apply_trail_activity_total_records(
    conn: sqlite3.Connection,
    *,
    activity: dict[str, Any] | None,
    track_points: list[dict[str, Any]] | None = None,
    dry_run: bool = True,
    run_id: str = "",
) -> dict[str, Any]:
    ensure_career_schema(conn)
    plan = build_trail_activity_total_record_evidences(activity=activity, track_points=track_points)
    payloads = [evidence.to_dict() for evidence in plan["evidences"]]
    if dry_run:
        return {"ok": True, "dry_run": True, "planned_count": len(payloads), "evidences": payloads, "skipped": plan["skipped"]}
    summary: dict[str, int] = {}
    results: list[dict[str, Any]] = []
    for evidence in plan["evidences"]:
        payload = evidence.to_dict()
        quality = payload.get("quality") if isinstance(payload.get("quality"), dict) else {}
        result = apply_record_evidence_state(
            conn,
            evidence,
            confidence=_safe_float(quality.get("confidence")),
            run_id=run_id,
            decision_source="trail_activity_total_resolver",
        )
        action = str(result.get("action") or "unknown")
        summary[action] = int(summary.get(action) or 0) + 1
        results.append({"record_key": payload.get("record_key"), "action": action, "result": result})
    return {"ok": True, "dry_run": False, "applied_count": len(results), "summary": summary, "results": results, "skipped": plan["skipped"]}


TRAIL_ROUTE_SIGNATURE_VERSION = "trail-route-signature-v1"
TRAIL_ROUTE_MATCH_VERSION = "trail-route-match-v1"
TRAIL_ROUTE_MATCH_DEFAULT_CONFIG = {
    "start_end_tolerance_m": 100.0,
    "length_tolerance_ratio": 0.05,
    "min_track_coverage_ratio": 0.95,
    "min_corridor_overlap_ratio": 0.85,
    "corridor_tolerance_m": 100.0,
    "resample_step_m": 100.0,
    "max_time_gap_sec": 300.0,
    "max_gps_jump_distance_m": 2500.0,
}
TRAIL_ROUTE_SAFE_JSON_FORBIDDEN_KEYS = ACS_PUBLIC_METADATA_FORBIDDEN_KEYS | {
    "absolute_path",
    "account",
    "account_id",
    "api_key",
    "authorization",
    "device",
    "device_id",
    "device_identifier",
    "device_name",
    "device_serial",
    "fit_file",
    "full_track",
    "gps_points",
    "latitude",
    "longitude",
    "lat",
    "lon",
    "lng",
    "local_path",
    "path",
    "polyline",
    "encoded_polyline",
    "coordinates",
    "geometry",
    "points",
    "points_xy",
    "raw_fit",
    "raw_path",
    "raw_points",
    "real_lat",
    "real_lon",
    "samples",
    "serial_number",
    "storage_ref",
    "token",
    "track",
    "track_json",
    "track_points",
    "user_id",
    "weight",
    "weight_history",
}


def _assert_trail_route_safe_json(value: Any, *, path: str = "route") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            clean_key = str(key or "").strip()
            normalized_key = clean_key.lower()
            if normalized_key in TRAIL_ROUTE_SAFE_JSON_FORBIDDEN_KEYS:
                raise ValueError(f"{path}.{clean_key} is not allowed in route derived data")
            if isinstance(child, str) and _looks_like_local_path(child):
                raise ValueError(f"{path}.{clean_key} must not contain a local path")
            _assert_trail_route_safe_json(child, path=f"{path}.{clean_key}" if clean_key else path)
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _assert_trail_route_safe_json(child, path=f"{path}[{index}]")
        return
    if isinstance(value, str) and _looks_like_local_path(value):
        raise ValueError(f"{path} must not contain a local path")


def _trail_route_match_config(config: dict[str, Any] | None = None) -> dict[str, float]:
    merged = dict(TRAIL_ROUTE_MATCH_DEFAULT_CONFIG)
    if isinstance(config, dict):
        for key, value in config.items():
            if key not in merged:
                continue
            parsed = _safe_float(value)
            if parsed is not None and parsed > 0:
                merged[key] = float(parsed)
    return {key: float(value) for key, value in merged.items()}


def _extract_route_xy_point(point: Any, index: int) -> dict[str, float] | None:
    x_value = y_value = None
    if isinstance(point, (list, tuple)) and len(point) >= 2:
        x_value, y_value = point[0], point[1]
    elif isinstance(point, dict):
        x_value = point.get("x_m", point.get("x", point.get("easting_m")))
        y_value = point.get("y_m", point.get("y", point.get("northing_m")))
        if x_value is None or y_value is None:
            lat = _safe_float(point.get("lat", point.get("latitude")))
            lon = _safe_float(point.get("lon", point.get("lng", point.get("longitude"))))
            if lat is not None and lon is not None:
                # Internal-only coarse projection; never persisted or returned.
                x_value = lon * 111_320.0
                y_value = lat * 110_540.0
    else:
        return None
    x = _finite_float(x_value)
    y = _finite_float(y_value)
    if x is None or y is None:
        return None
    t_sec = None
    if isinstance(point, dict):
        t_sec = _parse_record_timestamp_seconds(point.get("t_sec", point.get("t", point.get("time_sec", point.get("elapsed_time_sec")))))
    return {"x": float(x), "y": float(y), "index": float(index), "t_sec": float(t_sec) if t_sec is not None else float(index)}


def _normalize_route_points(track_points: Any) -> list[dict[str, float]]:
    points: list[dict[str, float]] = []
    if not isinstance(track_points, (list, tuple)):
        return points
    for index, raw in enumerate(track_points):
        point = _extract_route_xy_point(raw, index)
        if point is None:
            continue
        points.append(point)
    return points


def _route_distance(a: dict[str, float], b: dict[str, float]) -> float:
    return ((float(a["x"]) - float(b["x"])) ** 2 + (float(a["y"]) - float(b["y"])) ** 2) ** 0.5


def _route_hash(prefix: str, value: Any) -> str:
    return f"{prefix}:sha256:" + hashlib.sha256(_json_dumps(value).encode("utf-8")).hexdigest()


def _route_cell(point: dict[str, float], grid_m: float) -> tuple[int, int]:
    grid = max(float(grid_m), 1.0)
    return (round(float(point["x"]) / grid), round(float(point["y"]) / grid))


def _route_cell_hash(cell: tuple[int, int], *, salt: str) -> str:
    return _route_hash("route-cell", {"salt": salt, "cell": [int(cell[0]), int(cell[1])]})


def _route_neighbor_cell_hashes(point: dict[str, float], *, grid_m: float, salt: str) -> list[str]:
    base_x, base_y = _route_cell(point, grid_m)
    hashes = [
        _route_cell_hash((base_x + dx, base_y + dy), salt=salt)
        for dx in (-1, 0, 1)
        for dy in (-1, 0, 1)
    ]
    return sorted(set(hashes))


def _resample_route_points(points: list[dict[str, float]], step_m: float) -> list[dict[str, float]]:
    if len(points) < 2:
        return list(points)
    step = max(float(step_m), 10.0)
    samples: list[dict[str, float]] = [dict(points[0])]
    next_mark = step
    travelled = 0.0
    for start, end in zip(points, points[1:]):
        segment_len = _route_distance(start, end)
        if segment_len <= 0:
            continue
        while next_mark <= travelled + segment_len:
            ratio = (next_mark - travelled) / segment_len
            samples.append({
                "x": float(start["x"]) + (float(end["x"]) - float(start["x"])) * ratio,
                "y": float(start["y"]) + (float(end["y"]) - float(start["y"])) * ratio,
                "t_sec": float(start.get("t_sec", 0.0)) + (float(end.get("t_sec", 0.0)) - float(start.get("t_sec", 0.0))) * ratio,
                "index": float(start.get("index", 0.0)) + (float(end.get("index", 0.0)) - float(start.get("index", 0.0))) * ratio,
            })
            next_mark += step
        travelled += segment_len
    if _route_distance(samples[-1], points[-1]) > 1.0:
        samples.append(dict(points[-1]))
    return samples


def _route_length_and_quality(points: list[dict[str, float]], config: dict[str, float]) -> dict[str, Any]:
    if len(points) < 2:
        return {
            "distance_m": 0.0,
            "track_coverage_ratio": 0.0,
            "bad_distance_m": 0.0,
            "reason_codes": ["route_signature_insufficient_points"],
        }
    total = 0.0
    bad = 0.0
    reason_codes: list[str] = []
    for start, end in zip(points, points[1:]):
        segment_len = _route_distance(start, end)
        total += segment_len
        dt = float(end.get("t_sec", 0.0)) - float(start.get("t_sec", 0.0))
        if dt > float(config["max_time_gap_sec"]):
            bad += segment_len
            reason_codes.append("route_gps_long_gap")
        if segment_len > float(config["max_gps_jump_distance_m"]):
            bad += segment_len
            reason_codes.append("route_gps_jump")
    coverage = 0.0 if total <= 0 else max(0.0, min(1.0, 1.0 - (bad / total)))
    return {
        "distance_m": round(total, 3),
        "track_coverage_ratio": round(coverage, 4),
        "bad_distance_m": round(bad, 3),
        "reason_codes": list(_dedupe_reason_codes(reason_codes)),
    }


def _safe_activity_route_distance(activity: dict[str, Any] | None, fallback_distance_m: float) -> float:
    if isinstance(activity, dict):
        parsed = _hiking_activity_metric_float(activity, "distance_m", "distance")
        if parsed is not None:
            return float(parsed)
    return float(fallback_distance_m)


def build_trail_route_signature(
    *,
    activity: dict[str, Any] | None,
    track_points: list[Any] | tuple[Any, ...] | None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a privacy-safe trail route signature from in-memory Activity track facts."""
    cfg = _trail_route_match_config(config)
    activity = activity or {}
    scope = _trail_activity_scope(activity)
    if not scope.get("accepted"):
        return {
            "ok": False,
            "status": "ignored",
            "reason_codes": [str(scope.get("reason") or "record_definition_conflict")],
            "signature": {},
            "quality": {},
        }
    points = _normalize_route_points(track_points or [])
    quality_base = _route_length_and_quality(points, cfg)
    if len(points) < 2 or quality_base["distance_m"] <= 0:
        return {
            "ok": False,
            "status": "ignored",
            "reason_codes": quality_base["reason_codes"],
            "signature": {},
            "quality": quality_base,
        }
    route_distance_m = _safe_activity_route_distance(activity, quality_base["distance_m"])
    step_m = float(cfg["resample_step_m"])
    samples = _resample_route_points(points, step_m)
    salt = f"{TRAIL_ROUTE_SIGNATURE_VERSION}:{round(float(cfg['corridor_tolerance_m']), 3)}:{round(step_m, 3)}"
    primary_cells = [_route_cell(sample, step_m) for sample in samples]
    primary_hashes = [_route_cell_hash(cell, salt=salt) for cell in primary_cells]
    corridor_hashes: set[str] = set()
    for sample in samples:
        corridor_hashes.update(_route_neighbor_cell_hashes(sample, grid_m=step_m, salt=salt))
    start = points[0]
    end = points[-1]
    start_anchor_hashes = _route_neighbor_cell_hashes(start, grid_m=float(cfg["start_end_tolerance_m"]), salt=salt)
    end_anchor_hashes = _route_neighbor_cell_hashes(end, grid_m=float(cfg["start_end_tolerance_m"]), salt=salt)
    start_primary_hash = _route_cell_hash(_route_cell(start, float(cfg["start_end_tolerance_m"])), salt=salt)
    end_primary_hash = _route_cell_hash(_route_cell(end, float(cfg["start_end_tolerance_m"])), salt=salt)
    shape_hash = _route_hash("route-shape", {
        "version": TRAIL_ROUTE_SIGNATURE_VERSION,
        "cells": primary_hashes,
        "distance_bucket_m": round(route_distance_m / 100.0) * 100,
    })
    reverse_shape_hash = _route_hash("route-shape", {
        "version": TRAIL_ROUTE_SIGNATURE_VERSION,
        "cells": list(reversed(primary_hashes)),
        "distance_bucket_m": round(route_distance_m / 100.0) * 100,
    })
    is_loop = bool(set(start_anchor_hashes) & set(end_anchor_hashes))
    endpoint_pair = sorted([start_primary_hash, end_primary_hash]) if is_loop else [start_primary_hash, end_primary_hash]
    route_key = _route_hash("route-key", {
        "version": TRAIL_ROUTE_SIGNATURE_VERSION,
        "sport": "trail_running",
        "endpoint_pair": sorted([start_primary_hash, end_primary_hash]),
        "shape_hash": min(shape_hash, reverse_shape_hash),
        "distance_bucket_m": round(route_distance_m / 100.0) * 100,
    })
    direction_key = _route_hash("route-direction", {
        "version": TRAIL_ROUTE_SIGNATURE_VERSION,
        "mode": "loop" if is_loop else "point_to_point",
        "endpoint_pair": endpoint_pair,
        "shape_hash": shape_hash,
    })
    signature = {
        "signature_version": TRAIL_ROUTE_SIGNATURE_VERSION,
        "route_key": route_key,
        "direction_key": direction_key,
        "sport": "trail_running",
        "distance_m": round(route_distance_m, 3),
        "computed_track_distance_m": quality_base["distance_m"],
        "start_anchor_hashes": start_anchor_hashes,
        "end_anchor_hashes": end_anchor_hashes,
        "shape_hash": shape_hash,
        "reverse_shape_hash": reverse_shape_hash,
        "route_sample_hashes": sorted(set(primary_hashes)),
        "corridor_hashes": sorted(corridor_hashes),
        "sample_count": len(samples),
        "source_point_count": len(points),
        "grid_step_m": step_m,
        "corridor_tolerance_m": float(cfg["corridor_tolerance_m"]),
        "is_loop_or_out_and_back": is_loop,
        "privacy": "hashed_derived_signature_only",
    }
    quality = {
        "track_coverage_ratio": quality_base["track_coverage_ratio"],
        "bad_distance_m": quality_base["bad_distance_m"],
        "reason_codes": list(quality_base["reason_codes"]),
        "log_safety": "hashed_route_signature_only",
        "candidate_only": True,
    }
    if quality["track_coverage_ratio"] < float(cfg["min_track_coverage_ratio"]):
        quality["reason_codes"] = list(_dedupe_reason_codes([*quality["reason_codes"], "route_track_low_coverage"]))
    _assert_trail_route_safe_json(signature, path="route_signature")
    _assert_trail_route_safe_json(quality, path="route_quality")
    return {
        "ok": True,
        "status": "candidate",
        "activity_id": str(activity.get("activity_id") or activity.get("id") or ""),
        "sport": "trail_running",
        "route_key": route_key,
        "direction_key": direction_key,
        "distance_m": round(route_distance_m, 3),
        "duration_sec": _safe_int(activity.get("elapsed_time_sec") or activity.get("duration_sec") or activity.get("duration"), 0),
        "ascent_m": _hiking_activity_metric_float(activity, "ascent_m", "total_ascent", "gain_m", "elevation_gain_m", "elevation_gain"),
        "signature": signature,
        "quality": quality,
        "config": {
            "start_end_tolerance_m": float(cfg["start_end_tolerance_m"]),
            "length_tolerance_ratio": float(cfg["length_tolerance_ratio"]),
            "min_track_coverage_ratio": float(cfg["min_track_coverage_ratio"]),
            "min_corridor_overlap_ratio": float(cfg["min_corridor_overlap_ratio"]),
        },
    }


def _signature_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and isinstance(value.get("signature"), dict):
        return value["signature"]
    return value if isinstance(value, dict) else {}


def _signature_hash_set(signature: dict[str, Any], key: str) -> set[str]:
    raw = signature.get(key)
    if not isinstance(raw, list):
        return set()
    return {str(item) for item in raw if str(item or "").strip()}


def _route_anchor_intersects(a: dict[str, Any], a_key: str, b: dict[str, Any], b_key: str) -> bool:
    return bool(_signature_hash_set(a, a_key) & _signature_hash_set(b, b_key))


def _route_signature_direction(target: dict[str, Any], comparison: dict[str, Any]) -> str:
    target_loop = bool(target.get("is_loop_or_out_and_back"))
    comparison_loop = bool(comparison.get("is_loop_or_out_and_back"))
    if target_loop and comparison_loop and _route_anchor_intersects(target, "start_anchor_hashes", comparison, "start_anchor_hashes"):
        return "loop"
    same = (
        _route_anchor_intersects(target, "start_anchor_hashes", comparison, "start_anchor_hashes")
        and _route_anchor_intersects(target, "end_anchor_hashes", comparison, "end_anchor_hashes")
    )
    reverse = (
        _route_anchor_intersects(target, "start_anchor_hashes", comparison, "end_anchor_hashes")
        and _route_anchor_intersects(target, "end_anchor_hashes", comparison, "start_anchor_hashes")
    )
    if same:
        return "same"
    if reverse:
        return "reverse"
    return "unknown"


def match_trail_route_signatures(
    target_signature: dict[str, Any],
    comparison_signature: dict[str, Any],
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare two safe trail route signatures without requiring raw track points."""
    cfg = _trail_route_match_config(config)
    target = _signature_dict(target_signature)
    comparison = _signature_dict(comparison_signature)
    reason_codes: list[str] = []
    target_samples = _signature_hash_set(target, "route_sample_hashes")
    comparison_samples = _signature_hash_set(comparison, "route_sample_hashes")
    target_corridor = _signature_hash_set(target, "corridor_hashes")
    comparison_corridor = _signature_hash_set(comparison, "corridor_hashes")
    target_distance = _safe_float(target.get("distance_m")) or 0.0
    comparison_distance = _safe_float(comparison.get("distance_m")) or 0.0
    length_error_ratio = 1.0
    if target_distance > 0 and comparison_distance > 0:
        length_error_ratio = abs(target_distance - comparison_distance) / max(target_distance, comparison_distance)
    target_coverage = len(target_samples & comparison_corridor) / len(target_samples) if target_samples else 0.0
    comparison_coverage = len(comparison_samples & target_corridor) / len(comparison_samples) if comparison_samples else 0.0
    coverage_ratio = min(target_coverage, comparison_coverage)
    overlap_ratio = (target_coverage + comparison_coverage) / 2.0
    direction = _route_signature_direction(target, comparison)
    target_quality = target_signature.get("quality") if isinstance(target_signature.get("quality"), dict) else {}
    comparison_quality = comparison_signature.get("quality") if isinstance(comparison_signature.get("quality"), dict) else {}
    track_coverage = min(
        _safe_float(target_quality.get("track_coverage_ratio")) or 0.0,
        _safe_float(comparison_quality.get("track_coverage_ratio")) or 0.0,
    )
    if direction == "reverse":
        reason_codes.append("route_direction_mismatch")
    elif direction == "unknown":
        reason_codes.append("route_endpoint_mismatch")
    if length_error_ratio > float(cfg["length_tolerance_ratio"]):
        reason_codes.append("route_length_mismatch")
    if track_coverage < float(cfg["min_track_coverage_ratio"]):
        reason_codes.append("route_track_low_coverage")
    if overlap_ratio < float(cfg["min_corridor_overlap_ratio"]):
        reason_codes.append("route_match_low_overlap")
    hard_blocked = any(
        code in set(reason_codes)
        for code in (
            "route_direction_mismatch",
            "route_endpoint_mismatch",
            "route_length_mismatch",
            "route_track_low_coverage",
            "route_match_low_overlap",
        )
    )
    if not hard_blocked:
        reason_codes.append("real_data_sample_missing")
    match_score = max(0.0, min(1.0, (overlap_ratio * 0.6) + (coverage_ratio * 0.25) + ((1.0 - min(length_error_ratio, 1.0)) * 0.15)))
    result = {
        "match_version": TRAIL_ROUTE_MATCH_VERSION,
        "route_key": str(target.get("route_key") or ""),
        "direction": direction,
        "match_score": round(match_score, 4),
        "coverage_ratio": round(coverage_ratio, 4),
        "overlap_ratio": round(overlap_ratio, 4),
        "length_error_ratio": round(length_error_ratio, 4),
        "decision": "ignored" if hard_blocked else "candidate",
        "candidate_only": True,
        "reason_codes": list(_dedupe_reason_codes(reason_codes)),
        "privacy": "hashed_route_signature_only",
    }
    _assert_trail_route_safe_json(result, path="route_match")
    return result


def build_trail_route_candidate_plan(
    *,
    activity: dict[str, Any] | None,
    track_points: list[Any] | tuple[Any, ...] | None,
    comparison_routes: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target = build_trail_route_signature(activity=activity, track_points=track_points, config=config)
    if not target.get("ok"):
        return {"ok": False, "signature": target, "matches": [], "candidate_count": 0, "skipped": target.get("reason_codes", [])}
    matches: list[dict[str, Any]] = []
    for item in comparison_routes or []:
        comparison = item.get("signature") if isinstance(item.get("signature"), dict) else None
        if comparison is None:
            comparison = build_trail_route_signature(
                activity=item.get("activity") if isinstance(item.get("activity"), dict) else {"activity_id": item.get("activity_id"), "sport_type": "trail_running"},
                track_points=item.get("track_points") or item.get("points_xy") or item.get("points"),
                config=config,
            )
        match = match_trail_route_signatures(target, comparison, config=config)
        match["activity_id"] = str(target.get("activity_id") or "")
        item_activity = item.get("activity") if isinstance(item.get("activity"), dict) else {}
        match["matched_activity_id"] = str(item.get("activity_id") or item_activity.get("activity_id") or comparison.get("activity_id") or "")
        matches.append(match)
    return {
        "ok": True,
        "signature": target,
        "matches": matches,
        "candidate_count": sum(1 for match in matches if match.get("decision") == "candidate"),
        "candidate_only": True,
    }


def _trail_elapsed_time_sec(activity: dict[str, Any] | None, *extra_values: Any) -> float | None:
    for value in extra_values:
        parsed = _finite_float(value)
        if parsed is not None and parsed > 0:
            return float(parsed)
    if isinstance(activity, dict):
        for key in ("elapsed_time_sec", "duration_sec", "timer_time_sec", "duration"):
            parsed = _finite_float(activity.get(key))
            if parsed is not None and parsed > 0:
                return float(parsed)
    return None


def _trail_segment_key(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("segment_key is required")
    return text


def _trail_segment_elapsed(segment: dict[str, Any]) -> float | None:
    elapsed = _trail_elapsed_time_sec(
        None,
        segment.get("elapsed_time_sec"),
        segment.get("duration_sec"),
        segment.get("timer_time_sec"),
        segment.get("duration"),
    )
    if elapsed is not None:
        return elapsed
    start = _safe_float(segment.get("start_sec"))
    end = _safe_float(segment.get("end_sec"))
    if start is not None and end is not None and end > start:
        return float(end - start)
    return None


def _trail_segment_range(segment: dict[str, Any]) -> dict[str, Any]:
    segment_key = _trail_segment_key(segment.get("segment_key") or segment.get("id") or segment.get("key"))
    start_sec = _safe_float(segment.get("start_sec"))
    end_sec = _safe_float(segment.get("end_sec"))
    duration_sec = _trail_segment_elapsed(segment)
    range_data: dict[str, Any] = {
        "segment_key": segment_key,
        "duration_sec": duration_sec,
    }
    for key in ("start_distance_m", "end_distance_m", "distance_m"):
        parsed = _safe_float(segment.get(key))
        if parsed is not None:
            range_data[key] = round(parsed, 3)
    if start_sec is not None:
        range_data["start_sec"] = round(start_sec, 3)
    if end_sec is not None:
        range_data["end_sec"] = round(end_sec, 3)
    if "start_sec" not in range_data or "end_sec" not in range_data:
        raise ValueError("segment evidence requires start_sec and end_sec")
    return {key: value for key, value in range_data.items() if value not in (None, "")}


def _trail_route_match_allows_evidence(match: dict[str, Any] | None) -> bool:
    if not isinstance(match, dict):
        return False
    return str(match.get("decision") or "") == "candidate" and str(match.get("direction") or "") in {"same", "loop"}


def build_trail_route_record_evidences(
    *,
    activity: dict[str, Any] | None,
    route_signature: dict[str, Any] | None,
    route_matches: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
) -> dict[str, Any]:
    """Build candidate-only route-total elapsed-time evidences from safe route matches."""
    activity = activity or {}
    scope = _trail_activity_scope(activity)
    if not scope.get("accepted"):
        return {"evidences": [], "skipped": [{"record_key": "trail_route_best_time", "reason": scope.get("reason"), "sport": scope.get("sport")}]}
    signature = route_signature if isinstance(route_signature, dict) else {}
    signature_body = _signature_dict(signature)
    route_key = str(signature.get("route_key") or signature_body.get("route_key") or "").strip()
    if not route_key:
        return {"evidences": [], "skipped": [{"record_key": "trail_route_best_time", "reason": "route_signature_missing"}]}
    elapsed_sec = _trail_elapsed_time_sec(activity)
    if elapsed_sec is None:
        return {"evidences": [], "skipped": [{"record_key": "trail_route_best_time", "reason": "elapsed_time_missing"}]}
    matches = [match for match in (route_matches or []) if _trail_route_match_allows_evidence(match)]
    if not matches:
        return {"evidences": [], "skipped": [{"record_key": "trail_route_best_time", "reason": "route_match_missing_or_blocked"}]}
    activity_id = str(activity.get("activity_id") or activity.get("id") or "")
    event_date = _cycling_power_event_date(activity)
    evidences: list[RecordEvidence] = []
    skipped: list[dict[str, Any]] = []
    for match in matches:
        direction = str(match.get("direction") or "same")
        reason_codes = list(_dedupe_reason_codes([*(match.get("reason_codes") or ()), "candidate_only_registry"]))
        quality = {
            "confidence": min(0.89, max(0.70, _safe_float(match.get("match_score")) or 0.80)),
            "confidence_band": "candidate",
            "decision": "candidate",
            "reason_codes": reason_codes,
            "source": "route_match",
            "quality_policy": "trail_route_match",
            "log_safety": "hashed_route_signature_only",
            "can_user_confirm": True,
            "blocks_active": True,
        }
        evidences.append(build_record_evidence(
            record_key="trail_route_best_time",
            activity_id=activity_id,
            sport="trail_running",
            source_mode="route_total",
            metric_name="elapsed_time_sec",
            metric_value=round(elapsed_sec, 3),
            metric_unit="seconds",
            event_date=event_date,
            scope={"sport_scope": "trail_running", "route_key": route_key},
            range_data={
                "route_key": route_key,
                "direction": direction,
                "start_sec": 0,
                "end_sec": round(elapsed_sec, 3),
                "duration_sec": round(elapsed_sec, 3),
                "distance_m": _safe_float(signature.get("distance_m") or signature_body.get("distance_m")),
            },
            quality=quality,
            resolver_version=TRAIL_ROUTE_MATCH_VERSION,
            rule_version=RECORDS_V2_RULE_VERSION,
        ))
    return {"evidences": _dedupe_best_elapsed_record_evidences(evidences), "skipped": skipped}


def _is_trail_climb_segment(segment: dict[str, Any]) -> bool:
    raw_type = _normalise_cycling_scope_token(segment.get("segment_type") or segment.get("type") or segment.get("kind"))
    return bool(segment.get("is_climb") is True or raw_type in {"climb", "climb_segment", "uphill", "ascent"})


def build_trail_segment_record_evidences(
    *,
    activity: dict[str, Any] | None,
    segments: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
) -> dict[str, Any]:
    """Build candidate-only trail segment and climb-segment elapsed-time evidences."""
    activity = activity or {}
    scope = _trail_activity_scope(activity)
    if not scope.get("accepted"):
        return {"evidences": [], "skipped": [{"record_key": "trail_segment_best_time", "reason": scope.get("reason"), "sport": scope.get("sport")}]}
    activity_id = str(activity.get("activity_id") or activity.get("id") or "")
    event_date = _cycling_power_event_date(activity)
    evidences: list[RecordEvidence] = []
    skipped: list[dict[str, Any]] = []
    for index, raw_segment in enumerate(segments or []):
        if not isinstance(raw_segment, dict):
            skipped.append({"record_key": "trail_segment_best_time", "reason": "segment_invalid", "index": index})
            continue
        try:
            range_data = _trail_segment_range(raw_segment)
            segment_key = str(range_data["segment_key"])
        except ValueError as exc:
            skipped.append({"record_key": "trail_segment_best_time", "reason": str(exc), "index": index})
            continue
        elapsed_sec = _trail_segment_elapsed(raw_segment)
        if elapsed_sec is None or elapsed_sec <= 0:
            skipped.append({"record_key": segment_key, "reason": "elapsed_time_missing", "index": index})
            continue
        record_key = "trail_climb_segment_best_time" if _is_trail_climb_segment(raw_segment) else "trail_segment_best_time"
        quality_policy = "trail_climb_segment" if record_key == "trail_climb_segment_best_time" else "trail_segment"
        reason_codes = list(_dedupe_reason_codes([*(raw_segment.get("reason_codes") or ()), "real_data_sample_missing", "candidate_only_registry"]))
        evidences.append(build_record_evidence(
            record_key=record_key,
            activity_id=activity_id,
            sport="trail_running",
            source_mode="segment",
            metric_name="elapsed_time_sec",
            metric_value=round(elapsed_sec, 3),
            metric_unit="seconds",
            event_date=event_date,
            scope={"sport_scope": "trail_running", "segment_key": segment_key},
            range_data=range_data,
            quality={
                "confidence": 0.80,
                "confidence_band": "candidate",
                "decision": "candidate",
                "reason_codes": reason_codes,
                "source": "trail_segment_resolver",
                "quality_policy": quality_policy,
                "log_safety": "aggregate_range_only",
                "can_user_confirm": True,
                "blocks_active": True,
            },
            resolver_version=RECORDS_V2_RULE_VERSION,
            rule_version=RECORDS_V2_RULE_VERSION,
        ))
    return {"evidences": _dedupe_best_elapsed_record_evidences(evidences), "skipped": skipped}


def _dedupe_best_elapsed_record_evidences(evidences: list[RecordEvidence]) -> list[RecordEvidence]:
    best_by_scope: dict[tuple[str, str, str], RecordEvidence] = {}
    for evidence in evidences:
        payload = evidence.to_dict()
        metric = payload.get("metric") if isinstance(payload.get("metric"), dict) else {}
        elapsed = _safe_float(metric.get("value"))
        if elapsed is None:
            continue
        key = (
            str(payload.get("record_key") or ""),
            str(payload.get("source_mode") or ""),
            str(payload.get("scope_hash") or ""),
        )
        current = best_by_scope.get(key)
        if current is None:
            best_by_scope[key] = evidence
            continue
        current_metric = current.to_dict().get("metric") or {}
        current_elapsed = _safe_float(current_metric.get("value"))
        if current_elapsed is None or elapsed < current_elapsed:
            best_by_scope[key] = evidence
    return list(best_by_scope.values())


def build_trail_route_segment_record_evidences(
    *,
    activity: dict[str, Any] | None,
    route_signature: dict[str, Any] | None = None,
    route_matches: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    segments: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
) -> dict[str, Any]:
    route_plan = build_trail_route_record_evidences(
        activity=activity,
        route_signature=route_signature,
        route_matches=route_matches,
    ) if route_signature is not None else {"evidences": [], "skipped": []}
    segment_plan = build_trail_segment_record_evidences(activity=activity, segments=segments) if segments is not None else {"evidences": [], "skipped": []}
    evidences = _dedupe_best_elapsed_record_evidences([*route_plan["evidences"], *segment_plan["evidences"]])
    return {"evidences": evidences, "skipped": [*route_plan["skipped"], *segment_plan["skipped"]]}


def apply_trail_route_segment_records(
    conn: sqlite3.Connection,
    *,
    activity: dict[str, Any] | None,
    route_signature: dict[str, Any] | None = None,
    route_matches: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    segments: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    dry_run: bool = True,
    run_id: str = "",
) -> dict[str, Any]:
    ensure_career_schema(conn)
    plan = build_trail_route_segment_record_evidences(
        activity=activity,
        route_signature=route_signature,
        route_matches=route_matches,
        segments=segments,
    )
    payloads = [evidence.to_dict() for evidence in plan["evidences"]]
    if dry_run:
        return {"ok": True, "dry_run": True, "planned_count": len(payloads), "evidences": payloads, "skipped": plan["skipped"]}
    summary: dict[str, int] = {}
    results: list[dict[str, Any]] = []
    for evidence in plan["evidences"]:
        payload = evidence.to_dict()
        quality = payload.get("quality") if isinstance(payload.get("quality"), dict) else {}
        result = apply_record_evidence_state(
            conn,
            evidence,
            confidence=_safe_float(quality.get("confidence")),
            run_id=run_id,
            decision_source="trail_route_segment_resolver",
        )
        action = str(result.get("action") or "unknown")
        summary[action] = int(summary.get(action) or 0) + 1
        results.append({"record_key": payload.get("record_key"), "scope_hash": payload.get("scope_hash"), "action": action, "result": result})
    return {"ok": True, "dry_run": False, "applied_count": len(results), "summary": summary, "results": results, "skipped": plan["skipped"]}


TRAIL_PACE_GAP_CURVE_ALGORITHM_VERSION = "trail-pace-gap-curve-v1"
TRAIL_PACE_GAP_ANCHOR_DISTANCES_M = (1000, 3000, 5000, 10000, 20000, 30000, 50000)


def _parse_record_date(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text[:10] + "T00:00:00+00:00")
    except ValueError:
        return None


def _trail_activity_date(activity: dict[str, Any] | None) -> datetime | None:
    if not isinstance(activity, dict):
        return None
    for key in ("event_date", "start_time", "start_time_utc", "date"):
        parsed = _parse_record_date(activity.get(key))
        if parsed is not None:
            return parsed
    return None


def _trail_curve_time_scope_accepts(activity: dict[str, Any], *, time_scope: str, as_of_date: Any = None) -> bool:
    scope = str(time_scope or "all").strip() or "all"
    if scope == "all":
        return True
    activity_date = _trail_activity_date(activity)
    if activity_date is None:
        return False
    as_of = _parse_record_date(as_of_date) or datetime.now(timezone.utc)
    if scope == "season":
        return activity_date.year == as_of.year
    if scope in {"last_42_days", "42_days", "last42"}:
        start = as_of - timedelta(days=41)
        return start.date() <= activity_date.date() <= as_of.date()
    raise ValueError(f"unsupported trail curve time_scope: {scope}")


def _normalize_trail_curve_points(track_points: Any) -> list[dict[str, float]]:
    raw_points = _normalize_route_points(track_points or [])
    if not raw_points:
        return []
    normalized: list[dict[str, float]] = []
    cumulative = 0.0
    previous_xy: dict[str, float] | None = None
    for index, raw in enumerate(track_points or []):
        xy = _extract_route_xy_point(raw, index)
        if xy is None:
            continue
        if isinstance(raw, dict):
            distance_m = _finite_float(raw.get("distance_m", raw.get("distance")))
            altitude_m = _finite_float(raw.get("altitude_m", raw.get("altitude", raw.get("enhanced_altitude"))))
        else:
            distance_m = None
            altitude_m = None
        if previous_xy is not None:
            cumulative += _route_distance(previous_xy, xy)
        previous_xy = xy
        normalized.append({
            "distance_m": float(distance_m) if distance_m is not None else round(cumulative, 3),
            "t_sec": float(xy.get("t_sec", index)),
            "altitude_m": float(altitude_m) if altitude_m is not None else 0.0,
        })
    normalized.sort(key=lambda item: (item["distance_m"], item["t_sec"]))
    deduped: list[dict[str, float]] = []
    for point in normalized:
        if deduped and point["distance_m"] <= deduped[-1]["distance_m"]:
            continue
        deduped.append(point)
    return deduped


def _trail_curve_track_summary(activity: dict[str, Any] | None, points: list[dict[str, float]]) -> dict[str, Any]:
    distance_m = _safe_activity_route_distance(activity, points[-1]["distance_m"] if points else 0.0)
    altitude_values = [point["altitude_m"] for point in points]
    return {
        "activity_id": str((activity or {}).get("activity_id") or (activity or {}).get("id") or ""),
        "point_count": len(points),
        "distance_m": round(distance_m, 3),
        "duration_sec": _trail_elapsed_time_sec(activity),
        "has_elevation": bool(altitude_values and any(abs(value) > 0 for value in altitude_values)),
        "altitude_range_m": round(max(altitude_values) - min(altitude_values), 3) if altitude_values else 0.0,
    }


def _trail_curve_window_anchor(points: list[dict[str, float]], target_distance_m: float) -> dict[str, Any]:
    if len(points) < 2:
        return {"status": "unavailable", "reason_codes": ["trail_curve_insufficient_points"]}
    total_distance = points[-1]["distance_m"] - points[0]["distance_m"]
    if total_distance + 1e-6 < target_distance_m:
        return {"status": "unavailable", "reason_codes": ["activity_shorter_than_window"]}
    best: dict[str, Any] | None = None
    end_index = 0
    for start_index, start in enumerate(points):
        while end_index < len(points) and points[end_index]["distance_m"] - start["distance_m"] < target_distance_m:
            end_index += 1
        if end_index >= len(points):
            break
        end = points[end_index]
        elapsed = end["t_sec"] - start["t_sec"]
        if elapsed <= 0:
            continue
        distance = end["distance_m"] - start["distance_m"]
        altitude_delta = end["altitude_m"] - start["altitude_m"]
        grade = altitude_delta / max(distance, 1.0)
        uphill_factor = max(0.0, grade) * 3.0
        downhill_factor = min(0.0, grade) * 1.0
        adjustment_factor = max(0.75, min(1.35, 1.0 + uphill_factor + downhill_factor))
        gap_elapsed = elapsed / adjustment_factor
        candidate = {
            "status": "available",
            "distance_m": float(target_distance_m),
            "elapsed_time_sec": round(float(elapsed), 3),
            "pace_sec_per_km": round(float(elapsed) / (target_distance_m / 1000.0), 3),
            "gap_sec_per_km": round(float(gap_elapsed) / (target_distance_m / 1000.0), 3),
            "grade": round(float(grade), 5),
            "range": {
                "start_sec": round(float(start["t_sec"]), 3),
                "end_sec": round(float(end["t_sec"]), 3),
                "duration_sec": round(float(elapsed), 3),
                "start_distance_m": round(float(start["distance_m"]), 3),
                "end_distance_m": round(float(end["distance_m"]), 3),
                "distance_m": float(target_distance_m),
            },
            "reason_codes": ["analysis_only"],
        }
        if best is None or candidate["elapsed_time_sec"] < best["elapsed_time_sec"]:
            best = candidate
    return best or {"status": "unavailable", "reason_codes": ["trail_curve_window_missing"]}


def resolve_trail_pace_gap_activity_curve(
    *,
    activity: dict[str, Any] | None,
    track_points: list[Any] | tuple[Any, ...] | None,
) -> dict[str, Any]:
    """Resolve analysis-only trail pace/GAP anchors for one Activity."""
    activity = activity or {}
    scope = _trail_activity_scope(activity)
    if not scope.get("accepted"):
        return {"ok": False, "status": "ignored", "reason_codes": [scope.get("reason")], "anchors": []}
    points = _normalize_trail_curve_points(track_points or [])
    summary = _trail_curve_track_summary(activity, points)
    anchors: list[dict[str, Any]] = []
    for distance_m in TRAIL_PACE_GAP_ANCHOR_DISTANCES_M:
        anchor = _trail_curve_window_anchor(points, float(distance_m))
        anchor["label"] = f"{int(distance_m / 1000)}K"
        anchor["distance_m"] = float(distance_m)
        if anchor.get("status") == "available":
            anchor["source"] = {
                "activity_id": summary["activity_id"],
                "range": anchor.pop("range"),
            }
        anchors.append(anchor)
    view_model = {
        "ok": True,
        "status": "analysis_only",
        "activity_id": summary["activity_id"],
        "sport": "trail_running",
        "curve_types": ["trail_pace_curve", "trail_gap_curve"],
        "algorithm_version": TRAIL_PACE_GAP_CURVE_ALGORITHM_VERSION,
        "gap_algorithm": {
            "version": TRAIL_PACE_GAP_CURVE_ALGORITHM_VERSION,
            "basis": "grade_adjusted_elapsed_time",
            "elevation_input": "available" if summary["has_elevation"] else "missing_or_flat",
            "limitations": [
                "analysis_only_not_record",
                "does_not_model_technical_terrain",
                "grade_adjustment_is_approximate",
            ],
        },
        "summary": summary,
        "anchors": anchors,
        "quality": {
            "reason_codes": ["analysis_only"],
            "log_safety": "aggregate_curve_anchors_only",
        },
    }
    _assert_record_curve_cache_safe_json({key: value for key, value in view_model.items() if key != "anchors"}, path="trail_curve_view_model")
    _assert_record_curve_cache_safe_json({"anchors": anchors}, path="trail_curve_anchors")
    return view_model


def build_trail_pace_gap_curve_viewmodel(
    *,
    activities: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    activity_tracks: dict[str, list[Any]] | None = None,
    time_scope: str = "all",
    as_of_date: Any = None,
) -> dict[str, Any]:
    """Aggregate Activity-level trail pace/GAP curves into a safe analysis ViewModel."""
    tracks = activity_tracks or {}
    scoped_activities = [
        activity
        for activity in activities
        if isinstance(activity, dict) and _trail_curve_time_scope_accepts(activity, time_scope=time_scope, as_of_date=as_of_date)
    ]
    resolved = [
        resolve_trail_pace_gap_activity_curve(
            activity=activity,
            track_points=tracks.get(str(activity.get("activity_id") or activity.get("id") or "")) or activity.get("track_points") or [],
        )
        for activity in scoped_activities
    ]
    best_by_distance: dict[float, dict[str, Any]] = {}
    for curve in resolved:
        if not curve.get("ok"):
            continue
        for anchor in curve.get("anchors") or []:
            if anchor.get("status") != "available":
                continue
            distance = float(anchor.get("distance_m") or 0.0)
            current = best_by_distance.get(distance)
            if current is None or float(anchor.get("pace_sec_per_km") or 999999) < float(current.get("pace_sec_per_km") or 999999):
                best_by_distance[distance] = copy.deepcopy(anchor)
    anchors: list[dict[str, Any]] = []
    for distance_m in TRAIL_PACE_GAP_ANCHOR_DISTANCES_M:
        anchor = best_by_distance.get(float(distance_m))
        if anchor is None:
            anchor = {
                "status": "unavailable",
                "label": f"{int(distance_m / 1000)}K",
                "distance_m": float(distance_m),
                "reason_codes": ["no_activity_in_time_scope" if not scoped_activities else "activity_shorter_than_window"],
            }
        anchors.append(anchor)
    view_model = {
        "ok": True,
        "status": "analysis_only",
        "sport": "trail_running",
        "time_scope": str(time_scope or "all"),
        "as_of_date": str(as_of_date or "")[:10],
        "activity_count": len(scoped_activities),
        "curve_types": ["trail_pace_curve", "trail_gap_curve"],
        "algorithm_version": TRAIL_PACE_GAP_CURVE_ALGORITHM_VERSION,
        "gap_algorithm": {
            "version": TRAIL_PACE_GAP_CURVE_ALGORITHM_VERSION,
            "basis": "grade_adjusted_elapsed_time",
            "elevation_input": "per_activity_summary",
            "limitations": [
                "analysis_only_not_record",
                "does_not_model_technical_terrain",
                "grade_adjustment_is_approximate",
            ],
        },
        "anchors": anchors,
        "quality": {"reason_codes": ["analysis_only"], "log_safety": "aggregate_curve_anchors_only"},
    }
    _assert_record_curve_cache_safe_json(view_model, path="trail_curve_view_model")
    return view_model


def save_trail_pace_gap_curve_cache(
    *,
    activity_id: Any,
    view_model: dict[str, Any],
    conn: sqlite3.Connection | None = None,
    scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist analysis-only trail pace/GAP anchors to safe curve cache rows."""
    if not isinstance(view_model, dict):
        raise ValueError("view_model must be a JSON object")
    anchors = view_model.get("anchors") if isinstance(view_model.get("anchors"), list) else []
    quality = view_model.get("quality") if isinstance(view_model.get("quality"), dict) else {"reason_codes": ["analysis_only"]}
    summary = view_model.get("summary") if isinstance(view_model.get("summary"), dict) else {}
    safe_curve = {
        "status": "analysis_only",
        "algorithm_version": TRAIL_PACE_GAP_CURVE_ALGORITHM_VERSION,
        "anchors": anchors,
        "gap_algorithm": view_model.get("gap_algorithm") if isinstance(view_model.get("gap_algorithm"), dict) else {},
        "summary": summary,
    }
    _assert_record_curve_cache_safe_json(safe_curve, path="trail_curve_cache")
    fingerprint = compute_career_record_curve_input_fingerprint(
        activity_id=activity_id,
        sport="trail_running",
        source_mode="activity_total",
        canonical_facts_version=RECORDS_V2_RULE_VERSION,
        stream_summary_hash=_route_hash("trail-curve-summary", {
            "activity_id": str(activity_id or ""),
            "summary": summary,
            "anchor_count": len(anchors),
            "algorithm_version": TRAIL_PACE_GAP_CURVE_ALGORITHM_VERSION,
        }),
        algorithm_version=TRAIL_PACE_GAP_CURVE_ALGORITHM_VERSION,
        rule_version=RECORDS_V2_RULE_VERSION,
        scope=scope or {"sport_scope": "trail_running"},
    )
    saved: dict[str, Any] = {}
    for curve_type in ("trail_pace_curve", "trail_gap_curve"):
        saved[curve_type] = save_career_record_curve_cache(
            activity_id=activity_id,
            sport="trail_running",
            curve_type=curve_type,
            source_mode="activity_total",
            scope=scope or {"sport_scope": "trail_running"},
            input_fingerprint=fingerprint,
            algorithm_version=TRAIL_PACE_GAP_CURVE_ALGORITHM_VERSION,
            curve=safe_curve,
            quality=quality,
            conn=conn,
        )
    return {"ok": True, "input_fingerprint": fingerprint, "saved": saved}


def _dedupe_reason_codes(reason_codes: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    return tuple(str(reason) for reason in dict.fromkeys(reason_codes) if str(reason or "").strip())


def score_record_confidence(summary: dict[str, Any], match: dict[str, Any] | None) -> dict[str, Any]:
    """Score an Activity-backed record candidate with explainable downgrade reasons."""
    reason_codes = list(summary.get("reason_codes") or ())
    score_breakdown: dict[str, float] = {
        "base": 1.0,
        "record_match": 0.0,
        "distance_quality": 0.0,
        "time_quality": 0.0,
        "required_fields": 0.0,
        "activity_context": 0.0,
    }

    if match is None:
        score_breakdown["record_match"] = -0.45
        reason_codes.append("record_definition_not_matched")
    else:
        distance_error_ratio = _safe_float(match.get("distance_error_ratio")) or 0.0
        tolerance_ratio = _safe_float(getattr(match.get("definition"), "tolerance_ratio", None))
        if tolerance_ratio and distance_error_ratio > tolerance_ratio:
            score_breakdown["record_match"] = -0.45
            reason_codes.append("record_distance_outside_tolerance")

    distance_quality = str(summary.get("distance_quality") or "").strip()
    if not summary.get("distance_m"):
        score_breakdown["distance_quality"] -= 0.45
        reason_codes.append("distance_missing")
    elif distance_quality == "distance_unit_ambiguous":
        score_breakdown["distance_quality"] -= 0.18
        reason_codes.append("distance_unit_ambiguous")
    elif distance_quality not in {"reliable_distance", "gps_distance", "measured_distance"}:
        score_breakdown["distance_quality"] -= 0.10
        reason_codes.append("distance_quality_unknown")

    time_quality = str(summary.get("time_quality") or "").strip()
    elapsed_time_sec = _safe_int(summary.get("elapsed_time_sec"))
    if elapsed_time_sec <= 0:
        score_breakdown["time_quality"] -= 0.45
        reason_codes.append("elapsed_time_missing")
    elif time_quality in {"semantics_unknown", "timer_time_only"}:
        score_breakdown["time_quality"] -= 0.14
        reason_codes.append("duration_semantics_unknown")
    elif time_quality not in {"reliable_elapsed", "reliable_elapsed_time", "elapsed_time"}:
        score_breakdown["time_quality"] -= 0.08
        reason_codes.append("elapsed_time_quality_unknown")

    if not str(summary.get("activity_id") or "").strip():
        score_breakdown["required_fields"] -= 0.10
        reason_codes.append("activity_id_missing")
    if not str(summary.get("event_date") or "").strip():
        score_breakdown["required_fields"] -= 0.05
        reason_codes.append("event_date_missing")

    sub_sport = str(summary.get("sub_sport_type") or summary.get("sub_sport") or "").strip().lower()
    if summary.get("is_treadmill") or "treadmill" in sub_sport or sub_sport in {"indoor_running", "indoor_run"}:
        score_breakdown["activity_context"] -= 0.12
        reason_codes.append("treadmill_distance_needs_confirmation")

    confidence = max(0.0, min(1.0, round(sum(score_breakdown.values()), 2)))
    return {
        "confidence": confidence,
        "confidence_level": _record_confidence_level(confidence),
        "reason_codes": _dedupe_reason_codes(reason_codes),
        "score_breakdown": score_breakdown,
    }


def record_evidence_key(summary: dict[str, Any], match: dict[str, Any] | None) -> str:
    record_key = str((match or {}).get("record_key") or "unmatched")
    source_mode = str((match or {}).get("source_mode") or summary.get("source_mode") or "activity_total")
    activity_id = str(summary.get("activity_id") or "")
    distance_m = _safe_int(summary.get("distance_m"))
    elapsed_time_sec = _safe_int(summary.get("elapsed_time_sec"))
    return f"{source_mode}:{activity_id}:{record_key}:{distance_m}:{elapsed_time_sec}"


def build_record_candidate_decision(
    summary: dict[str, Any],
    match: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the pure candidate decision consumed by the future Records write path."""
    resolved_match = match
    if resolved_match is None:
        resolved_match = match_record_definition(summary)
    score = score_record_confidence(summary, resolved_match)
    decision = _record_candidate_decision(float(score["confidence"]))
    return {
        "decision": decision,
        "record_key": (resolved_match or {}).get("record_key"),
        "source_mode": (resolved_match or {}).get("source_mode") or summary.get("source_mode") or "activity_total",
        "activity_id": str(summary.get("activity_id") or ""),
        "distance_m": summary.get("distance_m"),
        "elapsed_time_sec": summary.get("elapsed_time_sec"),
        "event_date": summary.get("event_date") or "",
        "evidence_key": record_evidence_key(summary, resolved_match),
        **score,
    }


# Legacy resolver ranges are retained until the write-path Resolver is migrated.
RUNNING_PB_DISTANCE_RANGES = (
    ("running_5k", 4.8, 5.3),
    ("running_10k", 9.5, 10.8),
    ("running_half_marathon", 20.5, 21.7),
    ("running_marathon", 41.0, 43.0),
)

PB_TIMELINE_TITLES = {
    definition.key: f"{definition.display_name} PB"
    for definition in RECORD_DEFINITIONS
}

PB_TYPE_LABELS = {
    **{definition.key: definition.display_name for definition in RECORD_DEFINITIONS},
    "cycling_distance": "最长骑行",
    "cycling_ascent": "最大爬升",
    "cycling_avg_speed": "最快均速",
}

PB_OVERVIEW_TYPE_PRIORITY = {
    definition.key: definition.priority
    for definition in RECORD_DEFINITIONS
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


def _career_year_display_time(value: Any, *, local_tz: Any = None) -> str:
    """Convert stored UTC/auditable timestamps to a local display timestamp."""
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        localized = parsed.astimezone(local_tz) if local_tz is not None else parsed.astimezone()
        return localized.replace(microsecond=0).isoformat()
    except (TypeError, ValueError, OverflowError):
        return text


def _connect_default() -> sqlite3.Connection:
    db_path = Path(profile_backend.DB_PATH).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=profile_backend.SQLITE_CONNECT_TIMEOUT_SEC)
    conn.execute(f"PRAGMA busy_timeout = {profile_backend.SQLITE_BUSY_TIMEOUT_MS}")
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


def _index_exists(conn: sqlite3.Connection, index_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'index' AND name = ?
        LIMIT 1
        """,
        (index_name,),
    ).fetchone()
    return row is not None


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


def _activity_select_alias(available_columns: set[str], column_name: str) -> str:
    if column_name in available_columns:
        return column_name
    return f"NULL AS {column_name}"


def _overview_activity_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    if not _table_exists(conn, "activities"):
        return []
    available_columns = {
        str(row[1])
        for row in conn.execute("PRAGMA table_info(activities)").fetchall()
        if len(row) > 1 and row[1]
    }
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
    select_sql = ", ".join(_activity_select_alias(available_columns, column) for column in columns)
    deleted_filter = "deleted_at IS NULL" if "deleted_at" in available_columns else "1=1"
    cursor = conn.execute(
        f"""
        SELECT {select_sql}
        FROM activities
        WHERE {deleted_filter}
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
    return f"运动活动 {activity_id}" if activity_id else "运动瞬间"


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


def _footprint_clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace("/", " ").replace(",", " ").split()).strip()


def _footprint_text_variants(value: Any) -> list[str]:
    """Return normalized location text variants from composite provider fields."""
    raw = str(value or "").strip()
    if not raw:
        return []
    normalized = raw
    for separator in ("；", ";", "、", "，", ",", "|", "\n", "\r", "\t"):
        normalized = normalized.replace(separator, "/")
    split_parts = normalized.split("/")
    parts = split_parts + [raw] if len(split_parts) > 1 else [raw]
    variants: list[str] = []
    seen: set[str] = set()
    for part in parts:
        cleaned = _footprint_clean_text(part)
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        variants.append(cleaned)
    return variants


def _footprint_text_candidates(row: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    values: list[str] = []
    for key in keys:
        values.extend(_footprint_text_variants(row.get(key)))
    return values


def _footprint_is_china_country(value: Any) -> bool:
    text = _footprint_clean_text(value).lower()
    if not text:
        return False
    return text in CAREER_FOOTPRINT_CHINA_COUNTRY_ALIASES or any(
        alias.lower() in text
        for alias in CAREER_FOOTPRINT_CHINA_COUNTRY_ALIASES
        if len(alias) > 1
    )


def _footprint_country_record(value: Any) -> dict[str, str] | None:
    variants = _footprint_text_variants(value)
    for text in variants:
        lowered = text.lower()
        if _footprint_is_china_country(text):
            return {"country": "中国", "country_code": "CN"}
        if lowered in CAREER_FOOTPRINT_COUNTRY_SPECS:
            code, name = CAREER_FOOTPRINT_COUNTRY_SPECS[lowered]
            return {"country": name, "country_code": code}
        if len(text) == 2 and text.isalpha():
            return {"country": text.upper(), "country_code": text.upper()}
    text = variants[0] if variants else _footprint_clean_text(value)
    lowered = text.lower()
    if not lowered:
        return None
    return {"country": text[:80], "country_code": lowered.upper()[:12]}


def _footprint_china_region_from_text(value: Any) -> tuple[str, str] | None:
    text = _footprint_clean_text(value)
    if not text:
        return None
    lowered = text.lower()
    for region_key, name, aliases in CAREER_FOOTPRINT_CHINA_REGION_SPECS:
        for alias in aliases:
            alias_text = str(alias).lower()
            if alias_text and alias_text in lowered:
                return region_key, name
    return None


def _footprint_china_region_from_city(value: Any) -> tuple[str, str] | None:
    text = _footprint_clean_text(value)
    if not text:
        return None
    if text in CAREER_FOOTPRINT_CITY_REGION_HINTS:
        return CAREER_FOOTPRINT_CITY_REGION_HINTS[text]
    compact = text.replace("市", "").replace("区", "").replace("县", "")
    for city, region in CAREER_FOOTPRINT_CITY_REGION_HINTS.items():
        if compact and compact == city.replace("市", "").replace("区", "").replace("县", ""):
            return region
    return None


def _footprint_japan_region_from_text(value: Any) -> tuple[str, str] | None:
    text = _footprint_clean_text(value)
    if not text:
        return None
    lowered = text.lower()
    for region_key, name, aliases in CAREER_FOOTPRINT_JAPAN_REGION_SPECS:
        for alias in aliases:
            alias_text = str(alias).lower()
            if alias_text and alias_text in lowered:
                return region_key, name
    return None


def _footprint_us_region_from_text(value: Any) -> tuple[str, str] | None:
    text = _footprint_clean_text(value)
    if not text:
        return None
    upper = text.upper()
    if upper.startswith("US-") and len(upper) == 5:
        return CAREER_FOOTPRINT_US_POSTAL_REGION_MAP.get(upper.replace("US-", ""))
    if len(upper) == 2 and upper in CAREER_FOOTPRINT_US_POSTAL_REGION_MAP:
        return CAREER_FOOTPRINT_US_POSTAL_REGION_MAP[upper]
    lowered = text.lower()
    for region_key, name, aliases in CAREER_FOOTPRINT_US_REGION_SPECS:
        for alias in aliases:
            alias_text = str(alias).lower()
            if len(alias_text) >= 3 and alias_text in lowered:
                return region_key, name
    return None


def _footprint_us_region_from_city(value: Any) -> tuple[str, str] | None:
    text = _footprint_clean_text(value)
    if not text:
        return None
    lowered = text.lower()
    if lowered in CAREER_FOOTPRINT_US_CITY_REGION_HINTS:
        return CAREER_FOOTPRINT_US_CITY_REGION_HINTS[lowered]
    compact = lowered.replace(".", "").replace("-", " ")
    compact = " ".join(compact.split())
    return CAREER_FOOTPRINT_US_CITY_REGION_HINTS.get(compact)


def _resolve_career_footprint_region(row: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve one Activity row into a safe map region without using title or track points."""
    country_values = _footprint_text_candidates(row, ("region_country", "country", "countryName"))
    region_values = _footprint_text_candidates(row, ("region", "region_display", "region_state", "state", "province"))
    city_values = _footprint_text_candidates(row, ("region_city", "city", "cityName"))
    all_location_text = country_values + region_values + city_values
    country = next((_footprint_country_record(value) for value in country_values if _footprint_country_record(value)), None)
    china_hint = bool(country and country.get("country_code") == "CN") or any(
        _footprint_is_china_country(value) for value in all_location_text
    )

    if china_hint or not country_values:
        for value in city_values + region_values + country_values:
            region = _footprint_china_region_from_text(value) or _footprint_china_region_from_city(value)
            if region:
                region_key, name = region
                return {
                    "region_key": region_key,
                    "name": name,
                    "country": "中国",
                    "country_code": "CN",
                    "level": "province",
                    "map_mode": "china",
                    "city": city_values[0][:80] if city_values else "",
                }

    japan_hint = bool(country and country.get("country_code") == "JP")
    if japan_hint:
        for value in region_values + city_values:
            region = _footprint_japan_region_from_text(value)
            if region:
                region_key, name = region
                return {
                    "region_key": region_key,
                    "name": name,
                    "country": "日本",
                    "country_code": "JP",
                    "level": "prefecture",
                    "map_mode": "japan",
                    "city": city_values[0][:80] if city_values else "",
                }

    us_hint = bool(country and country.get("country_code") == "US")
    if us_hint:
        for value in region_values:
            region = _footprint_us_region_from_text(value)
            if region:
                region_key, name = region
                return {
                    "region_key": region_key,
                    "name": name,
                    "country": "美国",
                    "country_code": "US",
                    "level": "state" if region_key != "US-DC" else "district",
                    "map_mode": "us",
                    "city": city_values[0][:80] if city_values else "",
                }
        for value in city_values:
            region = _footprint_us_region_from_city(value) or _footprint_us_region_from_text(value)
            if region:
                region_key, name = region
                return {
                    "region_key": region_key,
                    "name": name,
                    "country": "美国",
                    "country_code": "US",
                    "level": "state" if region_key != "US-DC" else "district",
                    "map_mode": "us",
                    "city": city_values[0][:80] if city_values else "",
                }

    if country and country.get("country_code") != "CN":
        return {
            "region_key": str(country["country_code"]),
            "name": str(country["country"]),
            "country": str(country["country"]),
            "country_code": str(country["country_code"]),
            "level": "country",
            "map_mode": "world",
            "city": city_values[0][:80] if city_values else "",
        }

    return None


def _career_footprint_missing_reason(row: dict[str, Any]) -> str:
    if _footprint_text_candidates(row, ("region_country", "country", "countryName", "region", "region_display", "region_city", "city", "cityName")):
        return "unmapped_region"
    return "missing_region"


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
        badges.append("运动瞬间")
    if pb:
        badges.append("PB")
    return [badge for badge in badges if badge][:3]


def _build_empty_hero_banner() -> dict[str, Any]:
    return {
        "mode": "empty",
        "activity_id": "",
        "race_id": "",
        "title": "等待第一个运动瞬间",
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


def _normalize_footprint_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    raw = filters if isinstance(filters, dict) else {}
    sport = str(raw.get("sport") or "all").strip().lower() or "all"
    if sport not in {"all", "running", "cycling", "swimming", "hiking", "walking", "strength"}:
        sport = "all"
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


def _json_loads_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _canonical_record_scope(scope: Any) -> dict[str, Any]:
    raw = scope if isinstance(scope, dict) else _json_loads_object(scope)
    clean: dict[str, Any] = {}
    for key in sorted(RECORD_ALLOWED_SCOPE_DIMENSIONS):
        value = raw.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, (str, int, float, bool)):
            clean[key] = value
    return clean


def _record_scope_hash(scope: Any) -> str:
    clean = _canonical_record_scope(scope)
    if not clean:
        return "scope:v2:sha256:empty"
    payload = _json_dumps(clean)
    return "scope:v2:sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _legacy_record_scope_json(sport_scope: Any) -> dict[str, Any]:
    clean_scope = str(sport_scope or "").strip()
    return {"sport_scope": clean_scope} if clean_scope else {}


RECORD_EVIDENCE_SCHEMA_VERSION = "records-evidence-v2"
RECORD_EVIDENCE_ALLOWED_RANGE_FIELDS = {
    "start_sec",
    "end_sec",
    "duration_sec",
    "start_distance_m",
    "end_distance_m",
    "distance_m",
    "start_index",
    "end_index",
    "lap_start",
    "lap_end",
    "lap_count",
    "length_start",
    "length_end",
    "segment_key",
    "route_key",
    "direction",
}
RECORD_EVIDENCE_ALLOWED_QUALITY_FIELDS = {
    "confidence",
    "confidence_band",
    "decision",
    "reason_codes",
    "source",
    "quality_policy",
    "user_message_key",
    "log_safety",
    "can_user_confirm",
    "blocks_active",
    "evidence_fingerprint",
}
RECORD_EVIDENCE_FORBIDDEN_KEYS = ACS_PUBLIC_METADATA_FORBIDDEN_KEYS | {
    "absolute_path",
    "account",
    "account_id",
    "api_key",
    "authorization",
    "device",
    "device_id",
    "device_identifier",
    "device_name",
    "device_serial",
    "fit_file",
    "full_track",
    "gps_points",
    "lat_lon",
    "local_path",
    "path",
    "power_stream",
    "raw_fit",
    "raw_path",
    "raw_points",
    "raw_power",
    "raw_samples",
    "real_lat",
    "real_lon",
    "samples",
    "serial_number",
    "storage_ref",
    "token",
    "track",
    "track_json",
    "user_id",
    "weight",
    "weight_history",
}


@dataclass(frozen=True)
class RecordEvidence:
    """Safe V2 record evidence payload; it is not a state transition."""

    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self.payload)

    @property
    def evidence_key(self) -> str:
        return str(self.payload.get("evidence_key") or "")

    @property
    def evidence_fingerprint(self) -> str:
        return str(self.payload.get("evidence_fingerprint") or "")


def _validate_record_source_mode(source_mode: Any) -> str:
    clean_source_mode = str(source_mode or "").strip() or "activity_total"
    if clean_source_mode not in RECORD_ALLOWED_SOURCE_MODES:
        raise ValueError(f"unsupported source_mode: {clean_source_mode}")
    return clean_source_mode


def _assert_record_evidence_safe_json(value: Any, *, path: str = "evidence") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            clean_key = str(key or "").strip()
            normalized_key = clean_key.lower()
            if normalized_key in RECORD_EVIDENCE_FORBIDDEN_KEYS:
                raise ValueError(f"{path}.{clean_key} is not allowed in record evidence")
            if isinstance(child, str) and _looks_like_local_path(child):
                raise ValueError(f"{path}.{clean_key} must not contain a local path")
            _assert_record_evidence_safe_json(child, path=f"{path}.{clean_key}" if clean_key else path)
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _assert_record_evidence_safe_json(child, path=f"{path}[{index}]")
        return
    if isinstance(value, str) and _looks_like_local_path(value):
        raise ValueError(f"{path} must not contain a local path")


def _primitive_record_value(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def canonicalize_record_range(range_data: Any) -> dict[str, Any]:
    raw = range_data if isinstance(range_data, dict) else _json_loads_object(range_data)
    _assert_record_evidence_safe_json(raw, path="range")
    clean: dict[str, Any] = {}
    for key in sorted(RECORD_EVIDENCE_ALLOWED_RANGE_FIELDS):
        if key not in raw:
            continue
        value = raw.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, list):
            clean[key] = [_primitive_record_value(item) for item in value if item not in (None, "")]
        elif isinstance(value, (str, int, float, bool)):
            clean[key] = _primitive_record_value(value)
        else:
            raise ValueError(f"range.{key} must be primitive or a primitive list")
    return clean


def canonicalize_record_quality(quality: Any) -> dict[str, Any]:
    raw = quality if isinstance(quality, dict) else _json_loads_object(quality)
    _assert_record_evidence_safe_json(raw, path="quality")
    clean: dict[str, Any] = {}
    for key in sorted(RECORD_EVIDENCE_ALLOWED_QUALITY_FIELDS):
        if key not in raw:
            continue
        value = raw.get(key)
        if value in (None, ""):
            continue
        if key == "reason_codes":
            reason_codes = value if isinstance(value, (list, tuple)) else [value]
            clean[key] = list(_dedupe_reason_codes(tuple(str(item).strip() for item in reason_codes)))
        elif key == "confidence":
            parsed = _safe_float(value)
            if parsed is not None:
                clean[key] = max(0.0, min(1.0, round(parsed, 4)))
        elif isinstance(value, (str, int, float, bool)):
            clean[key] = _primitive_record_value(value)
        else:
            raise ValueError(f"quality.{key} must be primitive or reason_codes")
    return clean


def _record_scope_key(scope: dict[str, Any]) -> str:
    if not scope:
        return "default"
    for key in ("route_key", "segment_key", "pool_length_scope", "stroke_scope", "water_scope", "indoor_scope", "sport_scope"):
        value = str(scope.get(key) or "").strip()
        if value:
            return value
    return hashlib.sha1(_json_dumps(scope).encode("utf-8")).hexdigest()[:12]


def _record_stable_hash(prefix: str, value: Any) -> str:
    return f"{prefix}:sha256:" + hashlib.sha256(_json_dumps(value).encode("utf-8")).hexdigest()


def _validate_record_evidence_source_requirements(
    *,
    source_mode: str,
    scope: dict[str, Any],
    range_json: dict[str, Any],
) -> None:
    if source_mode in {"best_effort_duration", "best_effort_distance", "segment"} and not range_json:
        raise ValueError(f"{source_mode} evidence requires an activity range")
    if source_mode == "route_total" and not str(scope.get("route_key") or "").strip():
        raise ValueError("route_total evidence requires scope.route_key")
    if source_mode == "segment" and not str(scope.get("segment_key") or range_json.get("segment_key") or "").strip():
        raise ValueError("segment evidence requires segment_key")


def build_record_evidence(
    *,
    record_key: Any,
    activity_id: Any,
    sport: Any,
    source_mode: Any,
    metric_name: Any = None,
    metric_value: Any = None,
    metric_unit: Any = None,
    event_date: Any = "",
    scope: Any = None,
    range_data: Any = None,
    quality: Any = None,
    resolver_version: Any = None,
    rule_version: Any = None,
) -> RecordEvidence:
    """Build safe, stable V2 evidence without applying record state changes."""
    clean_record_key = str(record_key or "").strip()
    if not clean_record_key:
        raise ValueError("record_key is required")
    definition = get_record_definition(clean_record_key)
    if definition is None:
        raise ValueError(f"unknown record_key: {clean_record_key}")
    clean_source_mode = _validate_record_source_mode(source_mode)
    if definition.source_mode != clean_source_mode:
        raise ValueError(f"source_mode mismatch for {clean_record_key}: expected {definition.source_mode}")
    clean_activity_id = str(activity_id or "").strip()
    if not clean_activity_id:
        raise ValueError("activity_id is required")
    clean_sport = str(sport or definition.sport).strip()
    if not clean_sport:
        raise ValueError("sport is required")
    if clean_sport != definition.sport:
        raise ValueError(f"sport mismatch for {clean_record_key}: expected {definition.sport}")
    scope_json = _canonical_record_scope(scope)
    range_json = canonicalize_record_range(range_data)
    _validate_record_evidence_source_requirements(
        source_mode=clean_source_mode,
        scope=scope_json,
        range_json=range_json,
    )
    quality_json = canonicalize_record_quality(quality)
    clean_metric_name = str(metric_name or definition.metric).strip()
    clean_metric_unit = str(metric_unit or definition.canonical_unit).strip()
    if clean_metric_name != definition.metric:
        raise ValueError(f"metric_name mismatch for {clean_record_key}: expected {definition.metric}")
    if clean_metric_unit != definition.canonical_unit:
        raise ValueError(f"metric_unit mismatch for {clean_record_key}: expected {definition.canonical_unit}")
    metric = {
        "name": clean_metric_name,
        "value": _primitive_record_value(metric_value),
        "unit": clean_metric_unit,
    }
    if not metric["name"]:
        raise ValueError("metric_name is required")
    if metric["value"] in (None, ""):
        raise ValueError("metric_value is required")
    if not metric["unit"]:
        raise ValueError("metric_unit is required")
    clean_rule_version = str(rule_version or definition.rule_version).strip()
    clean_resolver_version = str(resolver_version or clean_rule_version).strip()
    scope_hash = _record_scope_hash(scope_json)
    range_hash = _record_stable_hash("range", range_json)
    metric_hash = _record_stable_hash("metric", metric)
    evidence_key = (
        f"evidence:v2:{clean_record_key}:{clean_activity_id}:{clean_source_mode}:"
        f"{scope_hash}:{range_hash}:{metric_hash}:{clean_rule_version}"
    )
    payload = {
        "evidence_schema_version": RECORD_EVIDENCE_SCHEMA_VERSION,
        "record_key": clean_record_key,
        "record_family": _record_definition_family(definition),
        "activity_id": clean_activity_id,
        "sport": clean_sport,
        "source_mode": clean_source_mode,
        "scope_json": scope_json,
        "scope_key": _record_scope_key(scope_json),
        "scope_hash": scope_hash,
        "range_json": range_json,
        "range_hash": range_hash,
        "metric": metric,
        "metric_hash": metric_hash,
        "event_date": str(event_date or "").strip(),
        "quality": quality_json,
        "resolver_version": clean_resolver_version,
        "rule_version": clean_rule_version,
        "evidence_key": evidence_key,
    }
    payload["evidence_fingerprint"] = _record_stable_hash("evidence", {
        key: value
        for key, value in payload.items()
        if key != "evidence_fingerprint"
    })
    _assert_record_evidence_safe_json(payload, path="evidence")
    return RecordEvidence(payload)


def _sanitize_public_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _sanitize_public_metadata(child)
            for key, child in value.items()
            if str(key).strip().lower() not in ACS_PUBLIC_METADATA_FORBIDDEN_KEYS
        }
    if isinstance(value, list):
        return [_sanitize_public_metadata(child) for child in value]
    if isinstance(value, str) and _looks_like_local_path(value):
        return ""
    return value


def _looks_like_local_path(value: str) -> bool:
    text = str(value or "")
    lowered = text.lower()
    return (
        "/users/" in lowered
        or "\\users\\" in lowered
        or lowered.startswith("/tmp/")
        or lowered.startswith("file://")
        or ".fit" in lowered
    )


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000.0, 3)


def _record_reason_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
        for reason in decision.get("reason_codes") or ():
            key = str(reason or "unknown").strip() or "unknown"
            counts[key] = int(counts.get(key) or 0) + 1
    return counts


def _safe_record_log(event: str, **fields: Any) -> None:
    safe_fields = _sanitize_public_metadata({
        key: value
        for key, value in fields.items()
        if key not in {"items", "results", "decision", "payload", "evidence_json"}
    })
    try:
        logger.info("records_center.%s %s", event, _json_dumps(safe_fields))
    except Exception:
        logger.info("records_center.%s", event)


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


def _normalize_memory_gallery_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    raw = filters if isinstance(filters, dict) else {}
    sport = str(raw.get("sport") or "all").strip().lower() or "all"
    if sport not in {"all", "running", "cycling"}:
        sport = "all"
    year = _safe_activity_year(raw.get("year"))
    return {
        "sport": sport,
        "year": year,
    }


def _memory_gallery_cover_from_photos(photos: list[dict[str, Any]]) -> dict[str, Any]:
    if not photos:
        return {
            "has_photo": False,
            "image_ref": "",
            "photo_id": "",
        }
    first = photos[0]
    image_ref = str(first.get("thumbnail_url") or first.get("preview_url") or "")
    if not image_ref.startswith("data:image/"):
        image_ref = ""
    return {
        "has_photo": bool(image_ref),
        "image_ref": image_ref,
        "photo_id": str(first.get("id") or ""),
    }


def _empty_memory_gallery_footprint() -> dict[str, str]:
    return {
        "region_key": "",
        "country_code": "",
        "country": "",
        "name": "",
        "level": "",
        "map_mode": "",
    }


def _memory_gallery_footprint_record(region: dict[str, Any] | None) -> dict[str, str]:
    if not region:
        return _empty_memory_gallery_footprint()
    return {
        "region_key": str(region.get("region_key") or ""),
        "country_code": str(region.get("country_code") or ""),
        "country": str(region.get("country") or ""),
        "name": str(region.get("name") or ""),
        "level": str(region.get("level") or ""),
        "map_mode": str(region.get("map_mode") or ""),
    }


def _memory_gallery_activity_region_row(conn: sqlite3.Connection, activity_id: str) -> dict[str, Any]:
    if not activity_id or not _table_exists(conn, "activities"):
        return {}
    columns = (
        "region",
        "region_city",
        "region_country",
        "region_display",
        "region_state",
        "state",
        "province",
        "city",
        "cityName",
        "country",
        "countryName",
    )
    select_sql = ", ".join(
        f"{column} AS {column}" if _column_exists(conn, "activities", column) else f"NULL AS {column}"
        for column in columns
    )
    row = conn.execute(
        f"SELECT {select_sql} FROM activities WHERE id = ? LIMIT 1",
        (activity_id,),
    ).fetchone()
    return dict(row) if isinstance(row, sqlite3.Row) else (dict(zip(columns, row)) if row else {})


def _memory_gallery_album_footprint(conn: sqlite3.Connection, race: dict[str, Any]) -> dict[str, str]:
    activity_id = str(race.get("activity_id") or "").strip()
    row = _memory_gallery_activity_region_row(conn, activity_id)
    region = _resolve_career_footprint_region(row)
    if region:
        return _memory_gallery_footprint_record(region)

    location = race.get("location") if isinstance(race.get("location"), dict) else {}
    fallback_row = {
        "region_city": str(location.get("city") or race.get("city") or ""),
        "city": str(location.get("city") or race.get("city") or ""),
        "region_country": str(location.get("country") or race.get("country") or ""),
        "country": str(location.get("country") or race.get("country") or ""),
        "region": str(location.get("region") or location.get("state") or ""),
        "province": str(location.get("province") or location.get("state") or ""),
        "region_display": str(location.get("display") or ""),
    }
    return _memory_gallery_footprint_record(_resolve_career_footprint_region(fallback_row))


def _build_memory_gallery_album(race: dict[str, Any], photos: list[dict[str, Any]], footprint: dict[str, str] | None = None) -> dict[str, Any]:
    race_id = str(race.get("id") or "")
    activity_id = str(race.get("activity_id") or "")
    title = str(race.get("race_title") or race.get("name") or "未命名赛事")
    location = race.get("location") if isinstance(race.get("location"), dict) else {}
    display_location = str(location.get("display") or race.get("city") or "")
    return {
        "id": race_id or f"album:activity:{activity_id}",
        "race_id": race_id,
        "activity_id": activity_id,
        "title": title,
        "event_type": str(race.get("event_type") or ""),
        "event_type_label": str(race.get("event_type_label") or ""),
        "sport": str(race.get("sport") or ""),
        "sport_label": str(race.get("sport_label") or ""),
        "event_date": str(race.get("event_date") or ""),
        "display_date": str(race.get("display_date") or ""),
        "city": str(race.get("city") or ""),
        "location": {
            "city": str(location.get("city") or race.get("city") or ""),
            "display": display_location,
        },
        "cover": _memory_gallery_cover_from_photos(photos),
        "photos": photos,
        "photo_count": len(photos),
        "is_empty": not bool(photos),
        "footprint": footprint or _empty_memory_gallery_footprint(),
        "detail_link": {
            "activity_id": activity_id,
            "source": "career",
        } if activity_id else {"activity_id": "", "source": "career"},
    }


def _summarize_memory_gallery_albums(albums: list[dict[str, Any]]) -> dict[str, int]:
    photo_count = sum(int(album.get("photo_count") or 0) for album in albums)
    empty_album_count = sum(1 for album in albums if bool(album.get("is_empty")))
    cover_count = sum(
        1
        for album in albums
        if isinstance(album.get("cover"), dict) and bool(album["cover"].get("has_photo"))
    )
    return {
        "album_count": len(albums),
        "photo_count": photo_count,
        "empty_album_count": empty_album_count,
        "cover_count": cover_count,
    }


def get_career_memory_gallery(
    filters: dict[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Return race-based photo albums without exposing storage references."""
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        schema = ensure_career_schema(db)
        normalized_filters = _normalize_memory_gallery_filters(filters)
        race_payload = get_career_races(normalized_filters, conn=db)
        races = race_payload.get("races") if isinstance(race_payload, dict) else []
        albums: list[dict[str, Any]] = []
        for race in races if isinstance(races, list) else []:
            if not isinstance(race, dict):
                continue
            activity_id = str(race.get("activity_id") or "").strip()
            photos = _activity_race_photo_items(db, activity_id) if activity_id else []
            albums.append(_build_memory_gallery_album(race, photos, _memory_gallery_album_footprint(db, race)))
        summary = _summarize_memory_gallery_albums(albums)
        data_ready = bool(albums)
        return {
            "albums": albums,
            "summary": summary,
            "filters": normalized_filters,
            "status": {
                "schema_ready": bool(schema.get("ok")),
                "data_ready": data_ready,
                "message": CAREER_MEMORY_GALLERY_READY_STATUS_MESSAGE if data_ready else CAREER_MEMORY_GALLERY_EMPTY_STATUS_MESSAGE,
            },
        }
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


def _fetch_pb_resolver_activity_row(conn: sqlite3.Connection, activity_id: Any) -> dict[str, Any] | None:
    if not _table_exists(conn, "activities"):
        return None
    select_sql = ", ".join(
        _pb_activity_select_expr(conn, column_name)
        for column_name in PB_RESOLVER_ACTIVITY_COLUMNS
    )
    where_sql = f"CAST(id AS TEXT) = ? AND {_deleted_filter(conn)}"
    cursor = conn.execute(
        f"""
        SELECT {select_sql}
        FROM activities
        WHERE {where_sql}
        LIMIT 1
        """,
        (str(activity_id),),
    )
    rows = _rows_to_dicts(cursor)
    return rows[0] if rows else None


def evaluate_activity_record_increment(
    conn: sqlite3.Connection,
    activity_id: Any,
) -> dict[str, Any]:
    """Incrementally evaluate one Activity for Records Center PB state changes."""
    start = time.perf_counter()
    ensure_career_schema(conn)
    row = _fetch_pb_resolver_activity_row(conn, activity_id)
    if row is None:
        result = {
            "ok": True,
            "activity_id": str(activity_id),
            "action": "ignored",
            "reason": "activity_not_found_or_deleted",
            "metrics": {"elapsed_ms": _elapsed_ms(start)},
        }
        _safe_record_log(
            "increment",
            activity_id=str(activity_id),
            action="ignored",
            reason="activity_not_found_or_deleted",
            elapsed_ms=result["metrics"]["elapsed_ms"],
        )
        return result
    summary = _record_performance_summary(row)
    match = match_record_definition(summary)
    decision = build_record_candidate_decision(summary, match)
    decision["sport"] = summary.get("sport")
    result = apply_record_candidate_decision(conn, decision)
    response = {
        "ok": True,
        "activity_id": str(activity_id),
        "action": result.get("action"),
        "record_key": decision.get("record_key"),
        "confidence": decision.get("confidence"),
        "confidence_level": decision.get("confidence_level"),
        "decision": decision.get("decision"),
        "result": result,
        "metrics": {"elapsed_ms": _elapsed_ms(start)},
    }
    _safe_record_log(
        "increment",
        activity_id=str(activity_id),
        resolver_version=str(decision.get("resolver_version") or RECORDS_V1_RULE_VERSION),
        action=response["action"],
        record_key=response["record_key"],
        confidence_level=response["confidence_level"],
        elapsed_ms=response["metrics"]["elapsed_ms"],
    )
    return response


def evaluate_activity_record_increments(
    conn: sqlite3.Connection,
    activity_ids: list[Any] | tuple[Any, ...],
) -> dict[str, Any]:
    """Incrementally evaluate multiple Activities in a caller-owned transaction."""
    start = time.perf_counter()
    results = [evaluate_activity_record_increment(conn, activity_id) for activity_id in dict.fromkeys(activity_ids)]
    summary: dict[str, int] = {}
    for item in results:
        action = str(item.get("action") or "unknown")
        summary[action] = summary.get(action, 0) + 1
    response = {
        "ok": True,
        "processed": len(results),
        "summary": summary,
        "results": results,
        "metrics": {"elapsed_ms": _elapsed_ms(start), "processed": len(results)},
    }
    _safe_record_log(
        "increment_batch",
        processed=response["processed"],
        summary=summary,
        elapsed_ms=response["metrics"]["elapsed_ms"],
    )
    return response


def _plan_record_rebuild_item(conn: sqlite3.Connection, row: dict[str, Any], resolver_version: str) -> dict[str, Any]:
    summary = _record_performance_summary(row)
    match = match_record_definition(summary)
    decision = build_record_candidate_decision(summary, match)
    decision["sport"] = summary.get("sport")
    decision["resolver_version"] = resolver_version
    action = "ignored"
    comparison: dict[str, Any] | None = None
    if decision["decision"] == "candidate":
        action = "candidate"
    elif decision["decision"] == "auto_confirm" and decision.get("record_key"):
        current = _active_record_row(
            conn,
            str(decision.get("record_key")),
            str(decision.get("source_mode") or "activity_total"),
            str(decision.get("sport_scope") or "default"),
        )
        comparison = compare_record_performance(decision.get("elapsed_time_sec"), current.get("value") if current else None)
        if comparison.get("is_new_record"):
            action = "new" if current is None else "replace"
        else:
            action = "unchanged"
    return {
        "activity_id": decision.get("activity_id"),
        "record_key": decision.get("record_key"),
        "action": action,
        "decision": decision,
        "comparison": comparison,
    }


def plan_records_rebuild(
    conn: sqlite3.Connection,
    *,
    resolver_version: str = RECORDS_V1_RULE_VERSION,
) -> dict[str, Any]:
    """Build a no-write Records rebuild plan for audit and preview."""
    start = time.perf_counter()
    ensure_career_schema(conn)
    rows = _fetch_pb_resolver_activity_rows(conn)
    items = [_plan_record_rebuild_item(conn, row, resolver_version) for row in rows]
    summary = {key: 0 for key in ("new", "replace", "candidate", "unchanged", "ignored")}
    for item in items:
        action = str(item.get("action") or "ignored")
        summary[action] = summary.get(action, 0) + 1
    reason_counts = _record_reason_counts(items)
    seed = _json_dumps([
        resolver_version,
        [(item.get("activity_id"), item.get("record_key"), item.get("action")) for item in items],
    ])
    run_id = f"records_rebuild:{hashlib.sha1(seed.encode('utf-8')).hexdigest()[:16]}"
    metrics = {
        "elapsed_ms": _elapsed_ms(start),
        "processed": len(items),
        "reason_counts": reason_counts,
    }
    response = {
        "ok": True,
        "dry_run": True,
        "run_id": run_id,
        "resolver_version": resolver_version,
        "processed": len(items),
        "progress": {"processed": len(items), "total": len(items)},
        "summary": summary,
        "metrics": metrics,
        "items": items,
    }
    _safe_record_log(
        "rebuild_plan",
        run_id=run_id,
        resolver_version=resolver_version,
        processed=len(items),
        summary=summary,
        reason_counts=reason_counts,
        elapsed_ms=metrics["elapsed_ms"],
    )
    return response


def rebuild_records(
    conn: sqlite3.Connection,
    *,
    dry_run: bool = True,
    resolver_version: str = RECORDS_V1_RULE_VERSION,
) -> dict[str, Any]:
    """Dry-run or transactionally apply a full Records rebuild plan."""
    global _RECORDS_REBUILD_IN_PROGRESS
    start = time.perf_counter()
    if _RECORDS_REBUILD_IN_PROGRESS:
        return {
            "ok": False,
            "code": "records_rebuild_in_progress",
            "msg": "记录重建正在进行",
            "dry_run": dry_run,
            "metrics": {"elapsed_ms": _elapsed_ms(start)},
        }
    _RECORDS_REBUILD_IN_PROGRESS = True
    try:
        plan = plan_records_rebuild(conn, resolver_version=resolver_version)
        if dry_run:
            plan["metrics"]["elapsed_ms"] = _elapsed_ms(start)
            _safe_record_log(
                "rebuild_dry_run",
                run_id=plan.get("run_id"),
                resolver_version=resolver_version,
                processed=plan.get("processed"),
                summary=plan.get("summary"),
                reason_counts=(plan.get("metrics") or {}).get("reason_counts"),
                elapsed_ms=plan["metrics"]["elapsed_ms"],
            )
            return plan
        savepoint_name = "records_rebuild_apply"
        applied: list[dict[str, Any]] = []
        applied_summary: dict[str, int] = {}
        try:
            conn.execute(f"SAVEPOINT {savepoint_name}")
            for item in plan["items"]:
                decision = item["decision"]
                result = apply_record_candidate_decision(conn, decision)
                applied_action = str(result.get("action") or "unknown")
                applied_summary[applied_action] = int(applied_summary.get(applied_action) or 0) + 1
                applied.append({
                    "activity_id": item.get("activity_id"),
                    "planned_action": item.get("action"),
                    "applied_action": applied_action,
                    "result": result,
                })
            conn.execute(f"RELEASE SAVEPOINT {savepoint_name}")
        except Exception:
            try:
                conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
                conn.execute(f"RELEASE SAVEPOINT {savepoint_name}")
            except sqlite3.Error:
                pass
            raise
        metrics = {
            **dict(plan.get("metrics") or {}),
            "elapsed_ms": _elapsed_ms(start),
            "applied_summary": applied_summary,
        }
        response = {
            **plan,
            "dry_run": False,
            "applied": applied,
            "applied_count": len(applied),
            "metrics": metrics,
        }
        _safe_record_log(
            "rebuild_apply",
            run_id=response.get("run_id"),
            resolver_version=resolver_version,
            processed=response.get("processed"),
            applied_count=len(applied),
            summary=response.get("summary"),
            applied_summary=applied_summary,
            reason_counts=metrics.get("reason_counts"),
            elapsed_ms=metrics["elapsed_ms"],
        )
        return response
    finally:
        _RECORDS_REBUILD_IN_PROGRESS = False


def _current_record_decision_for_activity(conn: sqlite3.Connection, activity_id: Any) -> dict[str, Any] | None:
    row = _fetch_pb_resolver_activity_row(conn, activity_id)
    if row is None:
        return None
    summary = _record_performance_summary(row)
    match = match_record_definition(summary)
    decision = build_record_candidate_decision(summary, match)
    decision["sport"] = summary.get("sport")
    return decision


def _active_record_invalid_reason(conn: sqlite3.Connection, record: dict[str, Any]) -> str | None:
    activity_id = str(record.get("activity_id") or "")
    if not activity_id:
        return "activity_id_missing"
    current_decision = _current_record_decision_for_activity(conn, activity_id)
    if current_decision is None:
        return "activity_missing_or_deleted"
    if str(record.get("resolver_version") or "") == RECORDS_V1_RULE_VERSION:
        if current_decision.get("decision") == "ignored":
            return "activity_no_longer_matches_record"
        if str(current_decision.get("record_key") or "") != str(record.get("pb_type") or ""):
            return "activity_record_key_changed"
        if str(current_decision.get("evidence_key") or "") != str(record.get("evidence_key") or ""):
            return "activity_evidence_changed"
    return None


def _valid_fallback_record(
    conn: sqlite3.Connection,
    record_key: str,
    source_mode: str,
    sport_scope: str,
) -> dict[str, Any] | None:
    cursor = conn.execute(
        """
        SELECT id, activity_id, sport, pb_type, value, value_unit, improvement,
               event_date, confidence, source, status, evidence_key, source_mode,
               sport_scope, previous_record_id, resolver_version, display_metadata_json
        FROM career_pb_records
        WHERE pb_type = ?
          AND source_mode = ?
          AND sport_scope = ?
          AND status = 'superseded'
        ORDER BY CAST(value AS INTEGER) ASC, event_date ASC, id ASC
        """,
        (record_key, source_mode, sport_scope),
    )
    for row in _rows_to_dicts(cursor):
        if _active_record_invalid_reason(conn, row) is None:
            return row
    return None


def repair_record_lifecycle(
    conn: sqlite3.Connection,
    *,
    record_key: str | None = None,
) -> dict[str, Any]:
    """Invalidate stale active records and promote the best valid history fallback."""
    ensure_career_schema(conn)
    savepoint_name = "records_lifecycle_repair"
    invalidated: list[str] = []
    promoted: list[str] = []
    try:
        conn.execute(f"SAVEPOINT {savepoint_name}")
        params: list[Any] = []
        where_parts = ["status = 'active'"]
        if record_key:
            where_parts.append("pb_type = ?")
            params.append(record_key)
        active_rows = _rows_to_dicts(conn.execute(
            f"""
            SELECT id, activity_id, sport, pb_type, value, value_unit, improvement,
                   event_date, confidence, source, status, evidence_key, source_mode,
                   sport_scope, previous_record_id, resolver_version, display_metadata_json
            FROM career_pb_records
            WHERE {' AND '.join(where_parts)}
            ORDER BY pb_type, source_mode, sport_scope, id
            """,
            tuple(params),
        ))
        for active in active_rows:
            reason = _active_record_invalid_reason(conn, active)
            if reason is None:
                continue
            active_id = str(active.get("id") or "")
            decision = {
                "activity_id": str(active.get("activity_id") or ""),
                "record_key": str(active.get("pb_type") or ""),
                "evidence_key": str(active.get("evidence_key") or active_id),
                "resolver_version": str(active.get("resolver_version") or RECORDS_V1_RULE_VERSION),
                "decision_source": "resolver",
                "reason_codes": (reason,),
            }
            conn.execute(
                """
                UPDATE career_pb_records
                SET status = 'invalidated',
                    invalidated_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'active'
                """,
                (active_id,),
            )
            _insert_record_event(conn, "invalidated", decision, record_id=active_id, payload={
                "reason": reason,
                "record": active,
            })
            invalidated.append(active_id)
            fallback = _valid_fallback_record(
                conn,
                str(active.get("pb_type") or ""),
                str(active.get("source_mode") or "activity_total"),
                str(active.get("sport_scope") or "default"),
            )
            if fallback is None:
                continue
            fallback_id = str(fallback.get("id") or "")
            conn.execute(
                """
                UPDATE career_pb_records
                SET status = 'active',
                    decision_source = 'resolver',
                    decided_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'superseded'
                """,
                (fallback_id,),
            )
            fallback_decision = {
                "activity_id": str(fallback.get("activity_id") or ""),
                "record_key": str(fallback.get("pb_type") or ""),
                "evidence_key": str(fallback.get("evidence_key") or fallback_id),
                "resolver_version": str(fallback.get("resolver_version") or RECORDS_V1_RULE_VERSION),
                "decision_source": "resolver",
                "reason_codes": ("activated_from_invalidated_fallback",),
            }
            _insert_record_event(conn, "activated_from_rebuild", fallback_decision, record_id=fallback_id, payload={
                "invalidated_record_id": active_id,
                "record": fallback,
            })
            promoted.append(fallback_id)
        conn.execute(f"RELEASE SAVEPOINT {savepoint_name}")
    except Exception:
        try:
            conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
            conn.execute(f"RELEASE SAVEPOINT {savepoint_name}")
        except sqlite3.Error:
            pass
        raise
    return {
        "ok": True,
        "invalidated": invalidated,
        "promoted": promoted,
        "active_count": _count_rows(conn, "career_pb_records", "status = 'active'"),
    }


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


def _record_performance_summary(row: dict[str, Any]) -> dict[str, Any]:
    """Build the safe Activity performance summary used by Records Resolver."""
    sport = "running" if _is_running_activity(row) else str(row.get("sport_type") or "unknown").strip().lower()
    distance_km = _activity_distance_km(row)
    distance_m = int(round(distance_km * 1000.0)) if distance_km and distance_km > 0 else None
    timer_time_sec = _activity_duration_sec(row)
    reason_codes: list[str] = []

    raw_distance = _safe_float(row.get("distance"))
    if distance_m is None:
        distance_quality = "missing_distance"
        reason_codes.append("distance_missing")
    elif _safe_float(row.get("dist_km")) and _safe_float(row.get("dist_km")) > 0:
        distance_quality = "reliable_distance"
        reason_codes.append("distance_from_dist_km")
    elif raw_distance and raw_distance > 1000:
        distance_quality = "reliable_distance"
        reason_codes.append("distance_from_meter_field")
    else:
        distance_quality = "distance_unit_ambiguous"
        reason_codes.append("distance_unit_ambiguous")

    if timer_time_sec is None:
        elapsed_time_sec = None
        time_quality = "missing_time"
        reason_codes.append("elapsed_time_missing")
    else:
        # Current Activity rows store timer-time-compatible legacy duration fields.
        # RC-11 will decide candidate/active behavior from this quality flag.
        elapsed_time_sec = int(timer_time_sec)
        time_quality = "semantics_unknown"
        reason_codes.extend(["duration_from_total_timer_time", "duration_semantics_unknown"])

    return {
        "activity_id": str(row.get("id") or ""),
        "sport": sport,
        "event_date": _pb_event_date(row),
        "distance_m": distance_m,
        "distance_km": round(distance_km, 3) if distance_km is not None else None,
        "elapsed_time_sec": elapsed_time_sec,
        "timer_time_sec": timer_time_sec,
        "distance_quality": distance_quality,
        "time_quality": time_quality,
        "reason_codes": tuple(dict.fromkeys(reason_codes)),
    }


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
        summary = _record_performance_summary(row)
        if summary["sport"] != "running":
            continue
        duration_sec = summary.get("elapsed_time_sec")
        if duration_sec is None:
            continue
        distance_match = _match_running_pb_type(summary.get("distance_km"))
        if not distance_match:
            continue
        candidates.append({
            "activity_id": summary["activity_id"],
            "sport": summary["sport"],
            "pb_type": distance_match["pb_type"],
            "duration_sec": duration_sec,
            "event_date": summary["event_date"],
            "distance_km": distance_match["distance_km"],
            "matched_range_km": distance_match["matched_range_km"],
            "performance_summary": {
                "distance_m": summary["distance_m"],
                "elapsed_time_sec": summary["elapsed_time_sec"],
                "timer_time_sec": summary["timer_time_sec"],
                "distance_quality": summary["distance_quality"],
                "time_quality": summary["time_quality"],
                "reason_codes": list(summary["reason_codes"]),
            },
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


def _active_record_row(
    conn: sqlite3.Connection,
    record_key: str,
    source_mode: str = "activity_total",
    sport_scope: str = "default",
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, activity_id, value, previous_record_id, evidence_key, resolver_version
        FROM career_pb_records
        WHERE pb_type = ?
          AND source_mode = ?
          AND sport_scope = ?
          AND status = 'active'
        ORDER BY CAST(value AS INTEGER) ASC, event_date ASC, id ASC
        LIMIT 1
        """,
        (record_key, source_mode, sport_scope),
    ).fetchone()
    if row is None:
        return None
    if isinstance(row, sqlite3.Row):
        return dict(row)
    return {
        "id": row[0],
        "activity_id": row[1],
        "value": row[2],
        "previous_record_id": row[3],
        "evidence_key": row[4],
        "resolver_version": row[5],
    }


def _record_event_id(event_type: str, evidence_key: str, record_id: str = "") -> str:
    digest = hashlib.sha1(f"{event_type}|{record_id}|{evidence_key}".encode("utf-8")).hexdigest()[:16]
    return f"record_event:{event_type}:{digest}"


def _insert_record_event(
    conn: sqlite3.Connection,
    event_type: str,
    decision: dict[str, Any],
    *,
    record_id: str = "",
    payload: dict[str, Any] | None = None,
) -> None:
    evidence_key = str(decision.get("evidence_key") or "")
    event_id = _record_event_id(event_type, evidence_key, record_id)
    conn.execute(
        """
        INSERT OR IGNORE INTO career_record_events
            (id, record_id, activity_id, pb_type, event_type, evidence_key,
             resolver_version, source, payload_json)
        VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            record_id or None,
            str(decision.get("activity_id") or ""),
            str(decision.get("record_key") or ""),
            event_type,
            evidence_key,
            str(decision.get("resolver_version") or RECORDS_V1_RULE_VERSION),
            str(decision.get("decision_source") or "resolver"),
            _json_dumps(payload or decision),
        ),
    )


def _record_candidate_id(evidence_key: str) -> str:
    digest = hashlib.sha1(str(evidence_key or "").encode("utf-8")).hexdigest()[:16]
    return f"record_candidate:{digest}"


def _record_candidate_title(decision: dict[str, Any]) -> str:
    definition = get_record_definition(str(decision.get("record_key") or ""))
    display_name = definition.display_name if definition else str(decision.get("record_key") or "PB")
    return f"{display_name} 纪录候选"


def _upsert_record_candidate(conn: sqlite3.Connection, decision: dict[str, Any]) -> str:
    candidate_id = _record_candidate_id(str(decision.get("evidence_key") or ""))
    evidence = {
        "record_decision": decision,
        "record_key": decision.get("record_key"),
        "evidence_key": decision.get("evidence_key"),
        "reason_codes": list(decision.get("reason_codes") or ()),
        "confidence_level": decision.get("confidence_level"),
    }
    conn.execute(
        """
        INSERT INTO career_event_candidates
            (id, activity_id, candidate_type, title, evidence_json, confidence, status, updated_at)
        VALUES
            (?, ?, 'pb_record', ?, ?, ?, 'candidate', CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
            activity_id = excluded.activity_id,
            candidate_type = excluded.candidate_type,
            title = excluded.title,
            evidence_json = excluded.evidence_json,
            confidence = excluded.confidence,
            status = CASE
                WHEN career_event_candidates.status = 'rejected' THEN career_event_candidates.status
                ELSE 'candidate'
            END,
            updated_at = CASE
                WHEN career_event_candidates.status = 'rejected' THEN career_event_candidates.updated_at
                ELSE CURRENT_TIMESTAMP
            END
        """,
        (
            candidate_id,
            str(decision.get("activity_id") or ""),
            _record_candidate_title(decision),
            _json_dumps(evidence),
            float(decision.get("confidence") or 0.0),
        ),
    )
    _insert_record_event(conn, "candidate_created", decision, payload=evidence)
    return candidate_id


def _activate_record_decision(
    conn: sqlite3.Connection,
    decision: dict[str, Any],
    *,
    decision_source: str = "resolver",
) -> dict[str, Any]:
    record_key = str(decision.get("record_key") or "")
    source_mode = str(decision.get("source_mode") or "activity_total")
    sport_scope = str(decision.get("sport_scope") or "default")
    candidate_value = _safe_int(decision.get("elapsed_time_sec"))
    current = _active_record_row(conn, record_key, source_mode, sport_scope)
    comparison = compare_record_performance(candidate_value, current.get("value") if current else None)
    if not comparison["is_valid"] or not comparison["is_new_record"]:
        _insert_record_event(conn, "recalculated", decision, record_id=str((current or {}).get("id") or ""), payload={
            "record_decision": decision,
            "comparison": comparison,
        })
        return {"action": "unchanged", "comparison": comparison, "record_id": (current or {}).get("id")}

    improvement_sec = comparison.get("improvement_sec")
    record_id = f"pb:{record_key}:{decision.get('activity_id')}"
    previous_record_id = str((current or {}).get("id") or "") or None
    if previous_record_id == record_id:
        previous_record_id = None
    previous_value = _safe_int((current or {}).get("value")) if current else None
    metadata = {
        "resolver": "records_center",
        "pb_type": record_key,
        "confidence_level": decision.get("confidence_level"),
        "reason_codes": list(decision.get("reason_codes") or ()),
        "score_breakdown": decision.get("score_breakdown") or {},
        "evidence_key": decision.get("evidence_key"),
        "previous_record_id": previous_record_id,
        "previous_value": previous_value,
        "improvement_sec": improvement_sec,
    }
    if previous_record_id:
        conn.execute(
            """
            UPDATE career_pb_records
            SET status = 'superseded', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (previous_record_id,),
        )
        _insert_record_event(conn, "superseded", decision, record_id=previous_record_id, payload={
            "new_record_id": record_id,
            "record_decision": decision,
        })
    conn.execute(
        """
        INSERT INTO career_pb_records
            (id, activity_id, sport, pb_type, value, value_unit, improvement,
             event_date, confidence, source, status, evidence_key, source_mode,
             sport_scope, previous_record_id, resolver_version, confirmed_at,
             decision_source, decided_at, display_metadata_json, updated_at)
        VALUES
            (?, ?, ?, ?, ?, 'seconds', ?, ?, ?, 'resolver', 'active', ?, ?,
             ?, ?, ?, CURRENT_TIMESTAMP, ?, CURRENT_TIMESTAMP, ?, CURRENT_TIMESTAMP)
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
            evidence_key = excluded.evidence_key,
            source_mode = excluded.source_mode,
            sport_scope = excluded.sport_scope,
            previous_record_id = excluded.previous_record_id,
            resolver_version = excluded.resolver_version,
            confirmed_at = COALESCE(career_pb_records.confirmed_at, excluded.confirmed_at),
            decision_source = excluded.decision_source,
            decided_at = excluded.decided_at,
            display_metadata_json = excluded.display_metadata_json,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            record_id,
            str(decision.get("activity_id") or ""),
            str(decision.get("sport") or "running"),
            record_key,
            str(candidate_value),
            str(improvement_sec) if improvement_sec is not None else None,
            str(decision.get("event_date") or ""),
            float(decision.get("confidence") or 1.0),
            str(decision.get("evidence_key") or ""),
            source_mode,
            sport_scope,
            previous_record_id,
            str(decision.get("resolver_version") or RECORDS_V1_RULE_VERSION),
            decision_source,
            _json_dumps(metadata),
        ),
    )
    _insert_record_event(conn, "activated", decision, record_id=record_id, payload={
        "record_decision": decision,
        "comparison": comparison,
        "previous_record_id": previous_record_id,
    })
    return {"action": "activated", "comparison": comparison, "record_id": record_id}


def apply_record_candidate_decision(conn: sqlite3.Connection, decision: dict[str, Any]) -> dict[str, Any]:
    """Apply a Records Center candidate decision to PB records/candidates/events."""
    ensure_career_schema(conn)
    normalized = dict(decision)
    normalized.setdefault("resolver_version", RECORDS_V1_RULE_VERSION)
    normalized.setdefault("source_mode", "activity_total")
    normalized.setdefault("sport_scope", "default")
    _insert_record_event(conn, "detected", normalized)
    if normalized.get("decision") == "auto_confirm":
        return _activate_record_decision(conn, normalized, decision_source="resolver")
    if normalized.get("decision") == "candidate":
        candidate_id = _upsert_record_candidate(conn, normalized)
        return {"action": "candidate_created", "candidate_id": candidate_id}
    _insert_record_event(conn, "ignored", normalized)
    return {"action": "ignored"}


def decide_career_pb_candidate(
    candidate_id: str,
    decision: str,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Confirm or reject a PB record candidate without letting rejected items enter history."""
    start = time.perf_counter()
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        ensure_career_schema(db)
        row = db.execute(
            """
            SELECT id, evidence_json, status
            FROM career_event_candidates
            WHERE id = ? AND candidate_type = 'pb_record'
            LIMIT 1
            """,
            (candidate_id,),
        ).fetchone()
        if row is None:
            return {"ok": False, "code": "not_found", "msg": "候选纪录不存在", "data": None, "metrics": {"elapsed_ms": _elapsed_ms(start)}}
        status = row[2] if not isinstance(row, sqlite3.Row) else row["status"]
        evidence_json = row[1] if not isinstance(row, sqlite3.Row) else row["evidence_json"]
        evidence = _json_loads_object(evidence_json)
        record_decision = dict(evidence.get("record_decision") or {})
        if decision == "reject":
            db.execute(
                """
                UPDATE career_event_candidates
                SET status = 'rejected', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (candidate_id,),
            )
            _insert_record_event(db, "user_rejected", record_decision)
            result = {"action": "rejected", "candidate_id": candidate_id}
        elif decision == "confirm":
            if status == "rejected":
                return {"ok": False, "code": "already_rejected", "msg": "候选纪录已拒绝", "data": None, "metrics": {"elapsed_ms": _elapsed_ms(start)}}
            record_decision["decision"] = "auto_confirm"
            record_decision["decision_source"] = "user"
            result = _activate_record_decision(db, record_decision, decision_source="user")
            db.execute(
                """
                UPDATE career_event_candidates
                SET status = 'confirmed', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (candidate_id,),
            )
            _insert_record_event(db, "user_confirmed", record_decision, record_id=str(result.get("record_id") or ""))
        else:
            return {"ok": False, "code": "invalid_decision", "msg": "候选纪录操作无效", "data": None, "metrics": {"elapsed_ms": _elapsed_ms(start)}}
        if owns_conn:
            db.commit()
        metrics = {"elapsed_ms": _elapsed_ms(start)}
        _safe_record_log(
            "candidate_decision",
            candidate_id=candidate_id,
            action=result.get("action"),
            decision=decision,
            record_key=record_decision.get("record_key"),
            resolver_version=record_decision.get("resolver_version") or RECORDS_V1_RULE_VERSION,
            elapsed_ms=metrics["elapsed_ms"],
        )
        return {"ok": True, "code": "ok", "msg": "候选纪录已处理", "data": result, "metrics": metrics}
    except Exception:
        if owns_conn:
            db.rollback()
        raise
    finally:
        if owns_conn:
            db.close()


def _record_evidence_payload(evidence: RecordEvidence | dict[str, Any]) -> dict[str, Any]:
    if isinstance(evidence, RecordEvidence):
        payload = evidence.to_dict()
    elif isinstance(evidence, dict):
        payload = copy.deepcopy(evidence)
    else:
        raise ValueError("record evidence must be RecordEvidence or dict")
    _assert_record_evidence_safe_json(payload, path="evidence")
    if str(payload.get("evidence_schema_version") or "") != RECORD_EVIDENCE_SCHEMA_VERSION:
        raise ValueError("unsupported record evidence schema")
    for field in ("record_key", "activity_id", "sport", "source_mode", "scope_hash", "scope_key", "metric", "evidence_key"):
        if payload.get(field) in (None, "", {}):
            raise ValueError(f"record evidence missing {field}")
    definition = get_record_definition(str(payload.get("record_key") or ""))
    if definition is None:
        raise ValueError("record evidence has unknown record_key")
    if definition.family in {"analysis_curve", "model_estimate"} or definition.availability_state in {"analysis_only", "model_only", "unavailable"}:
        raise ValueError("record evidence is not eligible for state migration")
    return payload


def compare_record_metric(record_key: Any, candidate_value: Any, current_value: Any | None) -> dict[str, Any]:
    """Compare a V2 record metric using the Registry comparison direction."""
    definition = get_record_definition(str(record_key or ""))
    if definition is None:
        return {"is_valid": False, "is_new_record": False, "reason": "record_definition_not_matched"}
    candidate_num = _safe_float(candidate_value)
    if candidate_num is None:
        return {"is_valid": False, "is_new_record": False, "reason": "invalid_candidate_value"}
    current_num = _safe_float(current_value)
    if current_num is None:
        return {
            "is_valid": True,
            "is_new_record": True,
            "is_first_record": True,
            "comparison": definition.comparison,
            "improvement": None,
        }
    if candidate_num == current_num:
        return {
            "is_valid": True,
            "is_new_record": False,
            "is_tie": True,
            "comparison": definition.comparison,
            "improvement": 0,
            "reason": "tie",
        }
    if definition.comparison == "lower_is_better":
        is_new = candidate_num < current_num
        improvement = current_num - candidate_num if is_new else None
    elif definition.comparison == "higher_is_better":
        is_new = candidate_num > current_num
        improvement = candidate_num - current_num if is_new else None
    else:
        return {"is_valid": False, "is_new_record": False, "reason": "unsupported_comparison"}
    return {
        "is_valid": True,
        "is_new_record": bool(is_new),
        "is_tie": False,
        "comparison": definition.comparison,
        "improvement": improvement,
        "reason": "improved" if is_new else "not_improved",
    }


def _active_v2_record_row(
    conn: sqlite3.Connection,
    record_key: str,
    source_mode: str,
    scope_hash: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, activity_id, sport, pb_type, value, value_unit, improvement,
               event_date, confidence, source, status, evidence_key, source_mode,
               sport_scope, previous_record_id, resolver_version, record_key,
               scope_json, scope_key, scope_hash, range_json, quality_json,
               metric_value_num, metric_name, catalog_state, rule_version
        FROM career_pb_records
        WHERE record_key = ?
          AND source_mode = ?
          AND scope_hash = ?
          AND status = 'active'
        LIMIT 1
        """,
        (record_key, source_mode, scope_hash),
    ).fetchone()
    if row is None:
        return None
    columns = (
        "id", "activity_id", "sport", "pb_type", "value", "value_unit", "improvement",
        "event_date", "confidence", "source", "status", "evidence_key", "source_mode",
        "sport_scope", "previous_record_id", "resolver_version", "record_key",
        "scope_json", "scope_key", "scope_hash", "range_json", "quality_json",
        "metric_value_num", "metric_name", "catalog_state", "rule_version",
    )
    return dict(row) if isinstance(row, sqlite3.Row) else dict(zip(columns, row))


def _record_event_v2_id(event_type: str, evidence: dict[str, Any], *, record_id: str = "", new_status: str = "") -> str:
    stable = {
        "event_type": event_type,
        "record_id": record_id,
        "record_key": evidence.get("record_key"),
        "scope_hash": evidence.get("scope_hash"),
        "evidence_key": evidence.get("evidence_key"),
        "new_status": new_status,
    }
    digest = hashlib.sha1(_json_dumps(stable).encode("utf-8")).hexdigest()[:18]
    return f"record_event:v2:{event_type}:{digest}"


def _insert_record_event_v2(
    conn: sqlite3.Connection,
    event_type: str,
    evidence: dict[str, Any],
    *,
    record_id: str = "",
    decision: str = "",
    reason_codes: list[str] | tuple[str, ...] = (),
    payload: dict[str, Any] | None = None,
    run_id: str = "",
    source: str = "resolver",
    new_status: str = "",
) -> None:
    safe_payload = payload or {
        "record_key": evidence.get("record_key"),
        "source_mode": evidence.get("source_mode"),
        "scope_hash": evidence.get("scope_hash"),
        "scope_key": evidence.get("scope_key"),
        "metric": evidence.get("metric"),
        "range": evidence.get("range_json") or {},
        "quality": evidence.get("quality") or {},
    }
    _assert_record_evidence_safe_json(safe_payload, path="record_event_payload")
    clean_reason_codes = list(_dedupe_reason_codes(tuple(str(code).strip() for code in reason_codes)))
    conn.execute(
        """
        INSERT OR IGNORE INTO career_record_events
            (id, record_id, activity_id, pb_type, event_type, evidence_key,
             resolver_version, source, record_key, scope_hash, scope_key, run_id,
             decision, reason_codes_json, payload_json)
        VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _record_event_v2_id(event_type, evidence, record_id=record_id, new_status=new_status),
            record_id or None,
            str(evidence.get("activity_id") or ""),
            str(evidence.get("record_key") or ""),
            event_type,
            str(evidence.get("evidence_key") or ""),
            str(evidence.get("resolver_version") or RECORDS_V2_RULE_VERSION),
            source,
            str(evidence.get("record_key") or ""),
            str(evidence.get("scope_hash") or ""),
            str(evidence.get("scope_key") or "default"),
            str(run_id or ""),
            str(decision or ""),
            _json_dumps(clean_reason_codes),
            _json_dumps(safe_payload),
        ),
    )


def _record_v2_candidate_id(evidence_key: str) -> str:
    digest = hashlib.sha1(str(evidence_key or "").encode("utf-8")).hexdigest()[:18]
    return f"record_candidate:v2:{digest}"


def _record_v2_candidate_title(evidence: dict[str, Any]) -> str:
    definition = get_record_definition(str(evidence.get("record_key") or ""))
    display_name = definition.display_name if definition else str(evidence.get("record_key") or "纪录")
    return f"{display_name} 纪录候选"


def _candidate_payload_from_record_evidence(evidence: dict[str, Any], decision: str, reason_codes: list[str]) -> dict[str, Any]:
    payload = {
        "record_evidence": {
            "evidence_schema_version": evidence.get("evidence_schema_version"),
            "record_key": evidence.get("record_key"),
            "record_family": evidence.get("record_family"),
            "activity_id": evidence.get("activity_id"),
            "sport": evidence.get("sport"),
            "source_mode": evidence.get("source_mode"),
            "scope": evidence.get("scope_json") or {},
            "scope_key": evidence.get("scope_key"),
            "scope_hash": evidence.get("scope_hash"),
            "range": evidence.get("range_json") or {},
            "metric": evidence.get("metric") or {},
            "quality": evidence.get("quality") or {},
            "resolver_version": evidence.get("resolver_version"),
            "rule_version": evidence.get("rule_version"),
            "evidence_key": evidence.get("evidence_key"),
            "evidence_fingerprint": evidence.get("evidence_fingerprint"),
        },
        "record_key": evidence.get("record_key"),
        "source_mode": evidence.get("source_mode"),
        "scope_hash": evidence.get("scope_hash"),
        "decision": decision,
        "reason_codes": reason_codes,
    }
    _assert_record_evidence_safe_json(payload, path="record_candidate_payload")
    return payload


def _upsert_record_v2_candidate(
    conn: sqlite3.Connection,
    evidence: dict[str, Any],
    *,
    decision: str,
    reason_codes: list[str],
    confidence: float,
    run_id: str = "",
) -> str:
    candidate_id = _record_v2_candidate_id(str(evidence.get("evidence_key") or ""))
    payload = _candidate_payload_from_record_evidence(evidence, decision, reason_codes)
    conn.execute(
        """
        INSERT INTO career_event_candidates
            (id, activity_id, candidate_type, title, evidence_json, confidence, status, updated_at)
        VALUES
            (?, ?, 'pb_record', ?, ?, ?, 'candidate', CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
            activity_id = excluded.activity_id,
            title = excluded.title,
            evidence_json = CASE
                WHEN career_event_candidates.status = 'rejected' THEN career_event_candidates.evidence_json
                ELSE excluded.evidence_json
            END,
            confidence = CASE
                WHEN career_event_candidates.status = 'rejected' THEN career_event_candidates.confidence
                ELSE excluded.confidence
            END,
            status = CASE
                WHEN career_event_candidates.status = 'rejected' THEN career_event_candidates.status
                ELSE 'candidate'
            END,
            updated_at = CASE
                WHEN career_event_candidates.status = 'rejected' THEN career_event_candidates.updated_at
                ELSE CURRENT_TIMESTAMP
            END
        """,
        (
            candidate_id,
            str(evidence.get("activity_id") or ""),
            _record_v2_candidate_title(evidence),
            _json_dumps(payload),
            float(confidence),
        ),
    )
    _insert_record_event_v2(
        conn,
        "candidate_created",
        evidence,
        decision=decision,
        reason_codes=reason_codes,
        payload=payload,
        run_id=run_id,
        new_status="candidate",
    )
    return candidate_id


def _record_v2_decision_from_quality(evidence: dict[str, Any], decision: str | None, confidence: float) -> tuple[str, list[str]]:
    quality = evidence.get("quality") if isinstance(evidence.get("quality"), dict) else {}
    reason_codes = list(_dedupe_reason_codes(tuple(quality.get("reason_codes") or ())))
    resolved = str(decision or quality.get("decision") or "").strip()
    if not resolved:
        resolved = _record_candidate_decision(confidence)
    definition = get_record_definition(str(evidence.get("record_key") or ""))
    state = definition.availability_state if definition else "unavailable"
    if state in {"analysis_only", "model_only", "unavailable"}:
        reason_codes.append(f"{state}_registry")
        return "ignored", list(_dedupe_reason_codes(tuple(reason_codes)))
    if resolved == "auto_confirm" and state in {"candidate_only", "validation_required"}:
        reason_codes.append("candidate_only_registry" if state == "candidate_only" else "validation_required_registry")
        resolved = "candidate"
    return resolved, list(_dedupe_reason_codes(tuple(reason_codes)))


def apply_record_evidence_state(
    conn: sqlite3.Connection,
    evidence: RecordEvidence | dict[str, Any],
    *,
    decision: str | None = None,
    confidence: float | None = None,
    decision_source: str = "resolver",
    run_id: str = "",
) -> dict[str, Any]:
    """Apply one safe V2 evidence payload to scoped record state in the provided DB."""
    ensure_career_schema(conn)
    payload = _record_evidence_payload(evidence)
    metric = payload.get("metric") if isinstance(payload.get("metric"), dict) else {}
    metric_value = metric.get("value")
    quality = payload.get("quality") if isinstance(payload.get("quality"), dict) else {}
    resolved_confidence = confidence
    if resolved_confidence is None:
        resolved_confidence = _safe_float(quality.get("confidence"))
    if resolved_confidence is None:
        resolved_confidence = 1.0
    resolved_decision, reason_codes = _record_v2_decision_from_quality(payload, decision, float(resolved_confidence))
    _insert_record_event_v2(
        conn,
        "detected",
        payload,
        decision=resolved_decision,
        reason_codes=reason_codes,
        run_id=run_id,
        source=decision_source,
    )
    if resolved_decision == "candidate":
        candidate_id = _upsert_record_v2_candidate(
            conn,
            payload,
            decision=resolved_decision,
            reason_codes=reason_codes,
            confidence=float(resolved_confidence),
            run_id=run_id,
        )
        return {"action": "candidate_created", "candidate_id": candidate_id, "decision": resolved_decision}
    if resolved_decision != "auto_confirm":
        _insert_record_event_v2(
            conn,
            "ignored",
            payload,
            decision=resolved_decision,
            reason_codes=reason_codes,
            run_id=run_id,
            source=decision_source,
            new_status="ignored",
        )
        return {"action": "ignored", "decision": resolved_decision}

    record_key = str(payload.get("record_key") or "")
    source_mode = str(payload.get("source_mode") or "activity_total")
    scope_hash = str(payload.get("scope_hash") or "")
    current = _active_v2_record_row(conn, record_key, source_mode, scope_hash)
    comparison = compare_record_metric(record_key, metric_value, (current or {}).get("metric_value_num") or (current or {}).get("value"))
    if not comparison["is_valid"] or not comparison["is_new_record"]:
        _insert_record_event_v2(
            conn,
            "recalculated",
            payload,
            record_id=str((current or {}).get("id") or ""),
            decision=resolved_decision,
            reason_codes=reason_codes,
            payload={"record_evidence": payload, "comparison": comparison},
            run_id=run_id,
            source=decision_source,
            new_status="unchanged",
        )
        return {"action": "unchanged", "comparison": comparison, "record_id": (current or {}).get("id")}

    record_id = "record:v2:" + hashlib.sha1(str(payload.get("evidence_key") or "").encode("utf-8")).hexdigest()[:20]
    previous_record_id = str((current or {}).get("id") or "") or None
    if previous_record_id:
        conn.execute(
            """
            UPDATE career_pb_records
            SET status = 'superseded', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (previous_record_id,),
        )
        _insert_record_event_v2(
            conn,
            "superseded",
            payload,
            record_id=previous_record_id,
            decision=resolved_decision,
            reason_codes=reason_codes,
            payload={"new_record_id": record_id, "comparison": comparison},
            run_id=run_id,
            source=decision_source,
            new_status="superseded",
        )
    definition = get_record_definition(record_key)
    scope_key = str(payload.get("scope_key") or "default")
    improvement = comparison.get("improvement")
    conn.execute(
        """
        INSERT INTO career_pb_records (
            id, activity_id, sport, pb_type, value, value_unit, improvement,
            event_date, confidence, source, status, evidence_key, source_mode,
            sport_scope, previous_record_id, resolver_version, confirmed_at,
            decision_source, decided_at, display_metadata_json, record_key,
            record_family, scope_json, scope_key, scope_hash, range_json,
            quality_json, metric_value_num, metric_name, catalog_state,
            rule_version, updated_at
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, 'resolver', 'active', ?, ?,
            ?, ?, ?, CURRENT_TIMESTAMP, ?, CURRENT_TIMESTAMP, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP
        )
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
            evidence_key = excluded.evidence_key,
            source_mode = excluded.source_mode,
            sport_scope = excluded.sport_scope,
            previous_record_id = excluded.previous_record_id,
            resolver_version = excluded.resolver_version,
            decision_source = excluded.decision_source,
            decided_at = excluded.decided_at,
            display_metadata_json = excluded.display_metadata_json,
            record_key = excluded.record_key,
            record_family = excluded.record_family,
            scope_json = excluded.scope_json,
            scope_key = excluded.scope_key,
            scope_hash = excluded.scope_hash,
            range_json = excluded.range_json,
            quality_json = excluded.quality_json,
            metric_value_num = excluded.metric_value_num,
            metric_name = excluded.metric_name,
            catalog_state = excluded.catalog_state,
            rule_version = excluded.rule_version,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            record_id,
            str(payload.get("activity_id") or ""),
            str(payload.get("sport") or ""),
            record_key,
            str(metric_value),
            str((metric or {}).get("unit") or ""),
            str(improvement) if improvement is not None else None,
            str(payload.get("event_date") or ""),
            float(resolved_confidence),
            str(payload.get("evidence_key") or ""),
            source_mode,
            scope_key,
            previous_record_id,
            str(payload.get("resolver_version") or RECORDS_V2_RULE_VERSION),
            decision_source,
            _json_dumps({"record_evidence": payload, "comparison": comparison}),
            record_key,
            _record_definition_family(definition) if definition else str(payload.get("record_family") or ""),
            _json_dumps(payload.get("scope_json") or {}),
            scope_key,
            scope_hash,
            _json_dumps(payload.get("range_json") or {}),
            _json_dumps(payload.get("quality") or {}),
            _safe_float(metric_value),
            str((metric or {}).get("name") or ""),
            definition.availability_state if definition else "available",
            str(payload.get("rule_version") or RECORDS_V2_RULE_VERSION),
        ),
    )
    _insert_record_event_v2(
        conn,
        "activated",
        payload,
        record_id=record_id,
        decision=resolved_decision,
        reason_codes=reason_codes,
        payload={"record_evidence": payload, "comparison": comparison, "previous_record_id": previous_record_id},
        run_id=run_id,
        source=decision_source,
        new_status="active",
    )
    return {"action": "activated", "comparison": comparison, "record_id": record_id, "previous_record_id": previous_record_id}


def decide_career_record_v2_candidate(
    candidate_id: str,
    decision: str,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Confirm or reject a V2 record candidate without allowing value edits."""
    start = time.perf_counter()
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        ensure_career_schema(db)
        row = db.execute(
            """
            SELECT id, evidence_json, status
            FROM career_event_candidates
            WHERE id = ? AND candidate_type = 'pb_record'
            LIMIT 1
            """,
            (candidate_id,),
        ).fetchone()
        if row is None:
            return {"ok": False, "code": "not_found", "data": None}
        status = row[2] if not isinstance(row, sqlite3.Row) else row["status"]
        evidence_json = row[1] if not isinstance(row, sqlite3.Row) else row["evidence_json"]
        candidate_payload = _json_loads_object(evidence_json)
        record_evidence = candidate_payload.get("record_evidence")
        if not isinstance(record_evidence, dict):
            return {"ok": False, "code": "invalid_candidate", "data": None}
        if decision == "reject":
            if status == "rejected":
                result = {"action": "rejected", "candidate_id": candidate_id}
            else:
                db.execute(
                    """
                    UPDATE career_event_candidates
                    SET status = 'rejected', updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (candidate_id,),
                )
                _insert_record_event_v2(db, "user_rejected", record_evidence, decision="reject", new_status="rejected", source="user")
                result = {"action": "rejected", "candidate_id": candidate_id}
        elif decision == "confirm":
            if status == "rejected":
                return {"ok": False, "code": "already_rejected", "data": None}
            result = apply_record_evidence_state(
                db,
                record_evidence,
                decision="auto_confirm",
                confidence=_safe_float((record_evidence.get("quality") or {}).get("confidence")) or 1.0,
                decision_source="user",
            )
            db.execute(
                """
                UPDATE career_event_candidates
                SET status = 'confirmed', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (candidate_id,),
            )
            _insert_record_event_v2(
                db,
                "user_confirmed",
                record_evidence,
                record_id=str(result.get("record_id") or ""),
                decision="confirm",
                new_status="confirmed",
                source="user",
            )
        else:
            return {"ok": False, "code": "invalid_decision", "data": None}
        if owns_conn:
            db.commit()
        safe_result = dict(result)
        safe_result["metrics"] = {"elapsed_ms": _elapsed_ms(start)}
        safe_result["observability"] = records_v2_safe_observation(
            "records_v2_candidate_decision",
            candidate_id=candidate_id,
            decision=decision,
            action=str(result.get("action") or ""),
            record_id=str(result.get("record_id") or ""),
            elapsed_ms=safe_result["metrics"]["elapsed_ms"],
        )
        return {"ok": True, "code": "ok", "data": safe_result}
    except Exception:
        if owns_conn:
            db.rollback()
        raise
    finally:
        if owns_conn:
            db.close()


def _activity_sport_for_record_dispatch(row: dict[str, Any]) -> str:
    candidates = (
        row.get("sport_type"),
        row.get("sport"),
        row.get("activity_type"),
        row.get("sub_sport_type"),
        row.get("sub_sport"),
    )
    raw = next((str(value).strip().lower() for value in candidates if str(value or "").strip()), "")
    normalized = raw.replace(" ", "_").replace("-", "_")
    if normalized in {"trail_running", "trail_run"}:
        return "trail_running"
    if normalized in RUNNING_SPORT_TYPES or normalized in {"run"}:
        return "running"
    if normalized in {"cycling", "cycle", "biking", "bike", "road_biking", "mountain_biking"}:
        return "cycling"
    if normalized in {"hiking", "hike", "trekking"}:
        return "hiking"
    if normalized in {"walking", "walk", "casual_walking", "indoor_walking"}:
        return "walking"
    if normalized in {"mountaineering", "mountain_climbing", "alpine_climbing"}:
        return "mountaineering"
    if normalized in {"pool_swimming", "lap_swimming"}:
        return "pool_swimming"
    if normalized in {"open_water_swimming", "openwater_swimming"}:
        return "open_water_swimming"
    return normalized


def _fetch_record_dispatch_activity_rows(
    conn: sqlite3.Connection,
    *,
    activity_id: Any = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    if not _table_exists(conn, "activities"):
        return []
    select_parts = ["CAST(id AS TEXT) AS id"]
    for column in ("sport_type", "sport", "activity_type", "sub_sport_type", "sub_sport", "deleted_at", "updated_at"):
        if _column_exists(conn, "activities", column):
            select_parts.append(column)
        else:
            select_parts.append(f"NULL AS {column}")
    where_parts = []
    params: list[Any] = []
    if activity_id is not None:
        where_parts.append("CAST(id AS TEXT) = ?")
        params.append(str(activity_id))
    else:
        where_parts.append(_deleted_filter(conn))
    limit_sql = ""
    if limit is not None and int(limit) > 0:
        limit_sql = f" LIMIT {int(limit)}"
    cursor = conn.execute(
        f"""
        SELECT {', '.join(select_parts)}
        FROM activities
        WHERE {' AND '.join(where_parts) if where_parts else '1=1'}
        ORDER BY CAST(id AS TEXT)
        {limit_sql}
        """,
        tuple(params),
    )
    return _rows_to_dicts(cursor)


def _record_dispatch_definitions_for_sport(
    sport: str,
    *,
    include_non_available: bool = True,
) -> list[RecordDefinition]:
    definitions = [definition for definition in RECORD_DEFINITIONS if definition.sport == sport]
    if include_non_available:
        return [
            definition
            for definition in definitions
            if definition.availability_state not in {"analysis_only", "model_only", "unavailable"}
        ]
    return [definition for definition in definitions if definition.availability_state == "available"]


def plan_activity_record_v2_dispatch(
    conn: sqlite3.Connection,
    activity_id: Any,
    *,
    available_only: bool = True,
) -> dict[str, Any]:
    """Plan V2 resolver dispatch for one Activity without generating evidence or writing state."""
    ensure_career_schema(conn)
    rows = _fetch_record_dispatch_activity_rows(conn, activity_id=activity_id)
    if not rows:
        return {
            "activity_id": str(activity_id),
            "action": "ignored",
            "reason": "activity_not_found_or_deleted",
            "sport": "",
            "definitions": [],
        }
    row = rows[0]
    if str(row.get("deleted_at") or "").strip():
        return {
            "activity_id": str(activity_id),
            "action": "ignored",
            "reason": "activity_not_found_or_deleted",
            "sport": _activity_sport_for_record_dispatch(row),
            "definitions": [],
        }
    sport = _activity_sport_for_record_dispatch(row)
    definitions = _record_dispatch_definitions_for_sport(sport, include_non_available=not available_only)
    if available_only:
        definitions = [definition for definition in definitions if definition.availability_state == "available"]
    planned = [
        {
            "record_key": definition.key,
            "family": _record_definition_family(definition),
            "source_mode": definition.source_mode,
            "availability_state": definition.availability_state,
            "scope_dimensions": list(definition.scope_dimensions),
            "reason": "resolver_pending",
        }
        for definition in definitions
    ]
    return {
        "activity_id": str(activity_id),
        "action": "dispatch_planned" if planned else "ignored",
        "reason": "definitions_planned" if planned else "no_available_definitions",
        "sport": sport,
        "definitions": planned,
    }


def _record_v2_evidence_from_row(row: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "evidence_schema_version": RECORD_EVIDENCE_SCHEMA_VERSION,
        "record_key": str(row.get("record_key") or row.get("pb_type") or ""),
        "activity_id": str(row.get("activity_id") or ""),
        "sport": str(row.get("sport") or ""),
        "source_mode": str(row.get("source_mode") or "activity_total"),
        "scope_hash": str(row.get("scope_hash") or _record_scope_hash(_legacy_record_scope_json(row.get("sport_scope")))),
        "scope_key": str(row.get("scope_key") or row.get("sport_scope") or "default"),
        "metric": {
            "name": str(row.get("metric_name") or ""),
            "value": row.get("metric_value_num") if row.get("metric_value_num") is not None else row.get("value"),
            "unit": str(row.get("value_unit") or ""),
        },
        "quality": {"reason_codes": [reason]},
        "resolver_version": str(row.get("resolver_version") or RECORDS_V2_RULE_VERSION),
        "rule_version": str(row.get("rule_version") or RECORDS_V2_RULE_VERSION),
        "evidence_key": str(row.get("evidence_key") or row.get("id") or ""),
    }


def _superseded_v2_fallback_record(
    conn: sqlite3.Connection,
    active: dict[str, Any],
) -> dict[str, Any] | None:
    record_key = str(active.get("record_key") or active.get("pb_type") or "")
    source_mode = str(active.get("source_mode") or "activity_total")
    scope_hash = str(active.get("scope_hash") or "")
    definition = get_record_definition(record_key)
    if definition is None:
        return None
    order = "metric_value_num ASC, event_date ASC, id ASC" if definition.comparison == "lower_is_better" else "metric_value_num DESC, event_date ASC, id ASC"
    rows = _rows_to_dicts(conn.execute(
        f"""
        SELECT id, activity_id, sport, pb_type, value, value_unit, improvement,
               event_date, confidence, source, status, evidence_key, source_mode,
               sport_scope, previous_record_id, resolver_version, record_key,
               scope_json, scope_key, scope_hash, range_json, quality_json,
               metric_value_num, metric_name, catalog_state, rule_version
        FROM career_pb_records
        WHERE record_key = ?
          AND source_mode = ?
          AND scope_hash = ?
          AND status = 'superseded'
        ORDER BY {order}
        """,
        (record_key, source_mode, scope_hash),
    ))
    for row in rows:
        if _activity_exists_for_candidate(conn, str(row.get("activity_id") or "")):
            return row
    return None


def _invalidate_route_records_for_activity(conn: sqlite3.Connection, activity_id: str, invalidated_at: str) -> dict[str, int]:
    signatures = 0
    matches = 0
    if _table_exists(conn, "career_route_signatures"):
        result = conn.execute(
            """
            UPDATE career_route_signatures
            SET invalidated_at = ?, updated_at = CURRENT_TIMESTAMP
            WHERE activity_id = ? AND invalidated_at IS NULL
            """,
            (invalidated_at, activity_id),
        )
        signatures = int(result.rowcount or 0)
    if _table_exists(conn, "career_route_matches"):
        result = conn.execute(
            """
            UPDATE career_route_matches
            SET invalidated_at = ?
            WHERE (activity_id = ? OR matched_activity_id = ?)
              AND invalidated_at IS NULL
            """,
            (invalidated_at, activity_id, activity_id),
        )
        matches = int(result.rowcount or 0)
    return {"route_cache": signatures, "route_matches": matches}


def invalidate_career_record_state_for_activity(
    conn: sqlite3.Connection,
    activity_id: Any,
    *,
    reason: str = "activity_changed",
    dry_run: bool = True,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Invalidate V2 records/cache/route data for an Activity and optionally promote scoped fallback."""
    ensure_career_schema(conn)
    clean_activity_id = str(activity_id or "").strip()
    active_rows = _rows_to_dicts(conn.execute(
        """
        SELECT id, activity_id, sport, pb_type, value, value_unit, improvement,
               event_date, confidence, source, status, evidence_key, source_mode,
               sport_scope, previous_record_id, resolver_version, record_key,
               scope_json, scope_key, scope_hash, range_json, quality_json,
               metric_value_num, metric_name, catalog_state, rule_version
        FROM career_pb_records
        WHERE activity_id = ?
          AND status = 'active'
          AND record_key IS NOT NULL AND TRIM(record_key) != ''
        ORDER BY record_key, source_mode, scope_hash, id
        """,
        (clean_activity_id,),
    ))
    cache_count = 0
    if _table_exists(conn, "career_record_curve_cache"):
        cache_count = int(conn.execute(
            "SELECT COUNT(*) FROM career_record_curve_cache WHERE activity_id = ? AND invalidated_at IS NULL",
            (clean_activity_id,),
        ).fetchone()[0] or 0)
    route_cache_count = 0
    if _table_exists(conn, "career_route_signatures"):
        route_cache_count = int(conn.execute(
            "SELECT COUNT(*) FROM career_route_signatures WHERE activity_id = ? AND invalidated_at IS NULL",
            (clean_activity_id,),
        ).fetchone()[0] or 0)
    route_match_count = 0
    if _table_exists(conn, "career_route_matches"):
        route_match_count = int(conn.execute(
            """
            SELECT COUNT(*)
            FROM career_route_matches
            WHERE (activity_id = ? OR matched_activity_id = ?)
              AND invalidated_at IS NULL
            """,
            (clean_activity_id, clean_activity_id),
        ).fetchone()[0] or 0)
    if dry_run:
        would_promote = [
            fallback.get("id")
            for fallback in (
                _superseded_v2_fallback_record(conn, active)
                for active in active_rows
            )
            if fallback is not None
        ]
        return {
            "ok": True,
            "dry_run": True,
            "activity_id": clean_activity_id,
            "reason": reason,
            "would_invalidate_records": [row.get("id") for row in active_rows],
            "would_invalidate_cache": int(cache_count),
            "would_invalidate_route_cache": int(route_cache_count),
            "would_invalidate_route_matches": int(route_match_count),
            "would_promote": would_promote,
        }
    savepoint_name = "records_v2_activity_invalidation"
    invalidated: list[str] = []
    promoted: list[str] = []
    invalidated_at = _utc_now_iso()
    try:
        conn.execute(f"SAVEPOINT {savepoint_name}")
        for active in active_rows:
            active_id = str(active.get("id") or "")
            conn.execute(
                """
                UPDATE career_pb_records
                SET status = 'invalidated',
                    invalidated_at = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'active'
                """,
                (invalidated_at, active_id),
            )
            evidence = _record_v2_evidence_from_row(active, reason)
            _insert_record_event_v2(
                conn,
                "invalidated",
                evidence,
                record_id=active_id,
                decision="invalidated",
                reason_codes=[reason],
                payload={"reason": reason, "record_id": active_id},
                run_id=run_id or "",
                new_status="invalidated",
            )
            invalidated.append(active_id)
            fallback = _superseded_v2_fallback_record(conn, active)
            if fallback is None:
                continue
            fallback_id = str(fallback.get("id") or "")
            conn.execute(
                """
                UPDATE career_pb_records
                SET status = 'active',
                    decision_source = 'resolver',
                    decided_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'superseded'
                """,
                (fallback_id,),
            )
            _insert_record_event_v2(
                conn,
                "activated_from_rebuild",
                _record_v2_evidence_from_row(fallback, "activated_from_invalidated_fallback"),
                record_id=fallback_id,
                decision="auto_confirm",
                reason_codes=["activated_from_invalidated_fallback"],
                payload={"invalidated_record_id": active_id, "fallback_record_id": fallback_id},
                run_id=run_id or "",
                new_status="active",
            )
            promoted.append(fallback_id)
        invalidated_cache = invalidate_career_record_curve_cache(activity_id=clean_activity_id, conn=conn)
        route_counts = _invalidate_route_records_for_activity(conn, clean_activity_id, invalidated_at)
        conn.execute(f"RELEASE SAVEPOINT {savepoint_name}")
    except Exception:
        try:
            conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
            conn.execute(f"RELEASE SAVEPOINT {savepoint_name}")
        except sqlite3.Error:
            pass
        raise
    return {
        "ok": True,
        "dry_run": False,
        "activity_id": clean_activity_id,
        "reason": reason,
        "invalidated": invalidated,
        "promoted": promoted,
        "invalidated_cache": invalidated_cache,
        **route_counts,
    }


def plan_career_records_v2_rebuild(
    conn: sqlite3.Connection,
    *,
    resolver_version: str = RECORDS_V2_RULE_VERSION,
    batch_size: int = 500,
    max_activities: int | None = None,
    cancel_after: int | None = None,
) -> dict[str, Any]:
    """Build a V2 rebuild dispatch plan without writing records or generating evidence."""
    start = time.perf_counter()
    ensure_career_schema(conn)
    limit = max_activities if max_activities is not None else None
    rows = _fetch_record_dispatch_activity_rows(conn, limit=limit)
    items: list[dict[str, Any]] = []
    summary = {"dispatch_planned": 0, "ignored": 0, "cancelled": 0}
    by_sport: dict[str, int] = {}
    by_family: dict[str, int] = {}
    by_reason: dict[str, int] = {}
    cancelled = False
    for index, row in enumerate(rows):
        if cancel_after is not None and index >= int(cancel_after):
            cancelled = True
            break
        item = plan_activity_record_v2_dispatch(conn, row.get("id"), available_only=True)
        items.append(item)
        action = str(item.get("action") or "ignored")
        summary[action] = int(summary.get(action) or 0) + 1
        sport = str(item.get("sport") or "unknown")
        by_sport[sport] = int(by_sport.get(sport) or 0) + 1
        reason = str(item.get("reason") or "unknown")
        by_reason[reason] = int(by_reason.get(reason) or 0) + 1
        for definition in item.get("definitions") or []:
            family = str(definition.get("family") or "unknown")
            by_family[family] = int(by_family.get(family) or 0) + 1
    if cancelled:
        summary["cancelled"] = 1
    cache_route = _records_v2_cache_route_observability(conn)
    seed = _json_dumps({
        "resolver_version": resolver_version,
        "batch_size": int(batch_size),
        "items": [(item.get("activity_id"), item.get("sport"), item.get("reason")) for item in items],
        "cancelled": cancelled,
    })
    run_id = "records_v2_rebuild:" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
    return {
        "ok": True,
        "dry_run": True,
        "run_id": run_id,
        "resolver_version": resolver_version,
        "batch_size": int(batch_size),
        "processed": len(items),
        "cancelled": cancelled,
        "summary": summary,
        "by_sport": by_sport,
        "by_family": by_family,
        "by_reason": by_reason,
        "items": items,
        "metrics": {
            "elapsed_ms": _elapsed_ms(start),
            "processed": len(items),
            "performance_target_ms": RECORDS_V2_PERFORMANCE_TARGETS_MS["rebuild_plan"],
            **cache_route,
        },
        "observability": records_v2_safe_observation(
            "records_v2_rebuild_plan",
            run_id=run_id,
            dry_run=True,
            processed=len(items),
            by_sport=by_sport,
            by_family=by_family,
            by_reason=by_reason,
            **cache_route,
        ),
        "failure_recovery": {
            "transaction": "savepoint",
            "supports_cancel": True,
            "supports_batching": True,
            "raw_payload_logged": False,
        },
    }


def rebuild_career_records_v2(
    conn: sqlite3.Connection,
    *,
    dry_run: bool = True,
    resolver_version: str = RECORDS_V2_RULE_VERSION,
    batch_size: int = 500,
    max_activities: int | None = None,
    cancel_after: int | None = None,
) -> dict[str, Any]:
    """Run the V2 rebuild framework; current task plans dispatch only, without sport algorithms."""
    global _RECORDS_REBUILD_IN_PROGRESS
    if _RECORDS_REBUILD_IN_PROGRESS:
        return {"ok": False, "code": "records_rebuild_in_progress", "dry_run": dry_run}
    _RECORDS_REBUILD_IN_PROGRESS = True
    try:
        plan = plan_career_records_v2_rebuild(
            conn,
            resolver_version=resolver_version,
            batch_size=batch_size,
            max_activities=max_activities,
            cancel_after=cancel_after,
        )
        if dry_run:
            return plan
        savepoint_name = "records_v2_rebuild_apply"
        try:
            conn.execute(f"SAVEPOINT {savepoint_name}")
            # RCV2-13 wires the transactional shell only. Sport-specific resolver
            # evidence generation starts in RCV2-15+ and will append applied items.
            conn.execute(f"RELEASE SAVEPOINT {savepoint_name}")
        except Exception:
            try:
                conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
                conn.execute(f"RELEASE SAVEPOINT {savepoint_name}")
            except sqlite3.Error:
                pass
            raise
        return {
            **plan,
            "dry_run": False,
            "applied": [],
            "applied_count": 0,
            "observability": records_v2_safe_observation(
                "records_v2_rebuild_apply",
                run_id=str(plan.get("run_id") or ""),
                dry_run=False,
                processed=int(plan.get("processed") or 0),
                by_sport=plan.get("by_sport") if isinstance(plan.get("by_sport"), dict) else {},
                by_family=plan.get("by_family") if isinstance(plan.get("by_family"), dict) else {},
                by_reason=plan.get("by_reason") if isinstance(plan.get("by_reason"), dict) else {},
            ),
        }
    finally:
        _RECORDS_REBUILD_IN_PROGRESS = False


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
        "performance_summary": candidate.get("performance_summary") or {},
    }
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


def refresh_career_derived_events(
    conn: sqlite3.Connection | None = None,
    *,
    include_pb: bool = True,
) -> dict[str, Any]:
    """Refresh all Activity-backed ACS derived events in resolver ownership order."""
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        schema = ensure_career_schema(db)
        race_result = resolve_race_events(db)
        pb_result = resolve_pb_records(db) if include_pb else {
            "ok": True,
            "processed": 0,
            "pb_records_upserted": 0,
            "skipped": 0,
            "status": {
                "schema_ready": bool(schema.get("ok")),
                "resolver": "pb",
                "message": "PB 全量解析已由增量入口跳过",
            },
        }
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
            evidence_key TEXT NOT NULL DEFAULT '',
            source_mode TEXT NOT NULL DEFAULT 'activity_total',
            sport_scope TEXT NOT NULL DEFAULT 'default',
            previous_record_id TEXT,
            resolver_version TEXT NOT NULL DEFAULT 'legacy',
            confirmed_at TEXT,
            rejected_at TEXT,
            invalidated_at TEXT,
            decision_source TEXT NOT NULL DEFAULT 'resolver',
            decided_at TEXT,
            record_key TEXT,
            record_family TEXT,
            scope_json TEXT NOT NULL DEFAULT '{}',
            scope_key TEXT NOT NULL DEFAULT 'default',
            scope_hash TEXT NOT NULL DEFAULT '',
            range_json TEXT NOT NULL DEFAULT '{}',
            quality_json TEXT NOT NULL DEFAULT '{}',
            metric_value_num REAL,
            metric_name TEXT,
            catalog_state TEXT,
            rule_version TEXT,
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
        "career_ai_insights",
        """
        CREATE TABLE IF NOT EXISTS career_ai_insights (
            id TEXT PRIMARY KEY,
            scope TEXT NOT NULL,
            scope_key TEXT NOT NULL,
            snapshot_fingerprint TEXT NOT NULL,
            snapshot_version TEXT NOT NULL,
            prompt_version TEXT NOT NULL,
            model_id TEXT NOT NULL,
            content_json TEXT NOT NULL DEFAULT '{}',
            generated_at TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            status TEXT NOT NULL,
            UNIQUE(scope, scope_key, snapshot_fingerprint, prompt_version, model_id),
            CHECK(status IN ('candidate', 'ready', 'superseded', 'failed'))
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
    _create_table_if_missing(
        conn,
        "career_record_events",
        """
        CREATE TABLE IF NOT EXISTS career_record_events (
            id TEXT PRIMARY KEY,
            record_id TEXT,
            activity_id TEXT NOT NULL DEFAULT '',
            pb_type TEXT NOT NULL DEFAULT '',
            event_type TEXT NOT NULL,
            event_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            evidence_key TEXT NOT NULL DEFAULT '',
            resolver_version TEXT NOT NULL DEFAULT 'records-v1',
            source TEXT NOT NULL DEFAULT 'resolver',
            record_key TEXT,
            scope_hash TEXT NOT NULL DEFAULT '',
            scope_key TEXT NOT NULL DEFAULT 'default',
            run_id TEXT,
            decision TEXT,
            reason_codes_json TEXT NOT NULL DEFAULT '[]',
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        created,
    )
    _create_table_if_missing(
        conn,
        "career_record_curve_cache",
        """
        CREATE TABLE IF NOT EXISTS career_record_curve_cache (
            id TEXT PRIMARY KEY,
            activity_id TEXT NOT NULL,
            sport TEXT NOT NULL,
            curve_type TEXT NOT NULL,
            source_mode TEXT NOT NULL,
            scope_hash TEXT NOT NULL DEFAULT '',
            input_fingerprint TEXT NOT NULL,
            algorithm_version TEXT NOT NULL,
            curve_json TEXT NOT NULL DEFAULT '{}',
            quality_json TEXT NOT NULL DEFAULT '{}',
            generated_at TEXT NOT NULL,
            invalidated_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        created,
    )
    _create_table_if_missing(
        conn,
        "career_route_signatures",
        """
        CREATE TABLE IF NOT EXISTS career_route_signatures (
            id TEXT PRIMARY KEY,
            activity_id TEXT NOT NULL,
            sport TEXT NOT NULL,
            route_key TEXT NOT NULL,
            direction_key TEXT NOT NULL,
            distance_m REAL,
            ascent_m REAL,
            duration_sec INTEGER,
            signature_version TEXT NOT NULL,
            signature_json TEXT NOT NULL DEFAULT '{}',
            quality_json TEXT NOT NULL DEFAULT '{}',
            generated_at TEXT NOT NULL,
            invalidated_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        created,
    )
    _create_table_if_missing(
        conn,
        "career_route_matches",
        """
        CREATE TABLE IF NOT EXISTS career_route_matches (
            id TEXT PRIMARY KEY,
            route_key TEXT NOT NULL,
            activity_id TEXT NOT NULL,
            matched_activity_id TEXT NOT NULL,
            match_version TEXT NOT NULL,
            direction TEXT NOT NULL,
            match_score REAL NOT NULL,
            coverage_ratio REAL,
            overlap_ratio REAL,
            length_error_ratio REAL,
            decision TEXT NOT NULL,
            reason_codes_json TEXT NOT NULL DEFAULT '[]',
            generated_at TEXT NOT NULL,
            invalidated_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        created,
    )


def _ensure_career_light_memory_columns(conn: sqlite3.Connection, migrated: list[str]) -> None:
    _add_column_if_missing(conn, "career_memory_items", "title", "TEXT NOT NULL DEFAULT ''", migrated)
    _add_column_if_missing(conn, "career_memory_items", "event_date", "TEXT NOT NULL DEFAULT ''", migrated)
    _add_column_if_missing(conn, "career_memory_items", "status", "TEXT NOT NULL DEFAULT 'active'", migrated)


def _ensure_career_pb_record_columns(conn: sqlite3.Connection, migrated: list[str]) -> None:
    _add_column_if_missing(conn, "career_pb_records", "evidence_key", "TEXT NOT NULL DEFAULT ''", migrated)
    _add_column_if_missing(conn, "career_pb_records", "source_mode", "TEXT NOT NULL DEFAULT 'activity_total'", migrated)
    _add_column_if_missing(conn, "career_pb_records", "sport_scope", "TEXT NOT NULL DEFAULT 'default'", migrated)
    _add_column_if_missing(conn, "career_pb_records", "previous_record_id", "TEXT", migrated)
    _add_column_if_missing(conn, "career_pb_records", "resolver_version", "TEXT NOT NULL DEFAULT 'legacy'", migrated)
    _add_column_if_missing(conn, "career_pb_records", "confirmed_at", "TEXT", migrated)
    _add_column_if_missing(conn, "career_pb_records", "rejected_at", "TEXT", migrated)
    _add_column_if_missing(conn, "career_pb_records", "invalidated_at", "TEXT", migrated)
    _add_column_if_missing(conn, "career_pb_records", "decision_source", "TEXT NOT NULL DEFAULT 'resolver'", migrated)
    _add_column_if_missing(conn, "career_pb_records", "decided_at", "TEXT", migrated)
    _add_column_if_missing(conn, "career_pb_records", "record_key", "TEXT", migrated)
    _add_column_if_missing(conn, "career_pb_records", "record_family", "TEXT", migrated)
    _add_column_if_missing(conn, "career_pb_records", "scope_json", "TEXT NOT NULL DEFAULT '{}'", migrated)
    _add_column_if_missing(conn, "career_pb_records", "scope_key", "TEXT NOT NULL DEFAULT 'default'", migrated)
    _add_column_if_missing(conn, "career_pb_records", "scope_hash", "TEXT NOT NULL DEFAULT ''", migrated)
    _add_column_if_missing(conn, "career_pb_records", "range_json", "TEXT NOT NULL DEFAULT '{}'", migrated)
    _add_column_if_missing(conn, "career_pb_records", "quality_json", "TEXT NOT NULL DEFAULT '{}'", migrated)
    _add_column_if_missing(conn, "career_pb_records", "metric_value_num", "REAL", migrated)
    _add_column_if_missing(conn, "career_pb_records", "metric_name", "TEXT", migrated)
    _add_column_if_missing(conn, "career_pb_records", "catalog_state", "TEXT", migrated)
    _add_column_if_missing(conn, "career_pb_records", "rule_version", "TEXT", migrated)
    if _column_exists(conn, "career_pb_records", "evidence_key"):
        conn.execute(
            """
            UPDATE career_pb_records
            SET evidence_key = 'activity_total:' || activity_id || ':' || pb_type || ':' || value
            WHERE evidence_key IS NULL OR TRIM(evidence_key) = ''
            """
        )
    _backfill_career_pb_record_v2_columns(conn)


def _backfill_career_pb_record_v2_columns(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, "career_pb_records") or not _column_exists(conn, "career_pb_records", "scope_hash"):
        return
    rows = conn.execute(
        """
        SELECT id, sport, pb_type, value, value_unit, confidence, source, status,
               display_metadata_json, sport_scope, resolver_version, record_key,
               scope_json, scope_key, scope_hash, metric_value_num, metric_name,
               record_family, catalog_state, rule_version, quality_json
        FROM career_pb_records
        """
    ).fetchall()
    for row in rows:
        if isinstance(row, sqlite3.Row):
            record = dict(row)
        else:
            columns = (
                "id", "sport", "pb_type", "value", "value_unit", "confidence", "source", "status",
                "display_metadata_json", "sport_scope", "resolver_version", "record_key",
                "scope_json", "scope_key", "scope_hash", "metric_value_num", "metric_name",
                "record_family", "catalog_state", "rule_version", "quality_json",
            )
            record = dict(zip(columns, row))
        record_id = str(record.get("id") or "")
        pb_type = str(record.get("pb_type") or "")
        definition = get_record_definition(pb_type)
        scope_json = _json_loads_object(record.get("scope_json"))
        if not scope_json:
            scope_json = _legacy_record_scope_json(record.get("sport_scope"))
        scope_hash = str(record.get("scope_hash") or "").strip() or _record_scope_hash(scope_json)
        metric_value_num = record.get("metric_value_num")
        if metric_value_num is None:
            metric_value_num = _safe_float(record.get("value"))
        quality_json = _json_loads_object(record.get("quality_json"))
        if not quality_json:
            quality_json = {
                "confidence": _safe_float(record.get("confidence")),
                "source": str(record.get("source") or "resolver"),
                "legacy": True,
            }
        conn.execute(
            """
            UPDATE career_pb_records
            SET record_key = COALESCE(NULLIF(record_key, ''), ?),
                record_family = COALESCE(NULLIF(record_family, ''), ?),
                scope_json = ?,
                scope_key = COALESCE(NULLIF(scope_key, ''), ?),
                scope_hash = ?,
                range_json = COALESCE(NULLIF(range_json, ''), '{}'),
                quality_json = ?,
                metric_value_num = COALESCE(metric_value_num, ?),
                metric_name = COALESCE(NULLIF(metric_name, ''), ?),
                catalog_state = COALESCE(NULLIF(catalog_state, ''), ?),
                rule_version = COALESCE(NULLIF(rule_version, ''), ?)
            WHERE id = ?
            """,
            (
                pb_type,
                _record_definition_family(definition) if definition else "legacy",
                _json_dumps(scope_json),
                str(record.get("scope_key") or record.get("sport_scope") or "default"),
                scope_hash,
                _json_dumps(quality_json),
                metric_value_num,
                definition.metric if definition else ("elapsed_time_sec" if str(record.get("value_unit") or "") == "seconds" else None),
                definition.availability_state if definition else ("available" if str(record.get("status") or "") in {"active", "superseded"} else "candidate_only"),
                definition.rule_version if definition else str(record.get("resolver_version") or "legacy"),
                record_id,
            ),
        )


def _ensure_career_record_event_columns(conn: sqlite3.Connection, migrated: list[str]) -> None:
    _add_column_if_missing(conn, "career_record_events", "record_key", "TEXT", migrated)
    _add_column_if_missing(conn, "career_record_events", "scope_hash", "TEXT NOT NULL DEFAULT ''", migrated)
    _add_column_if_missing(conn, "career_record_events", "scope_key", "TEXT NOT NULL DEFAULT 'default'", migrated)
    _add_column_if_missing(conn, "career_record_events", "run_id", "TEXT", migrated)
    _add_column_if_missing(conn, "career_record_events", "decision", "TEXT", migrated)
    _add_column_if_missing(conn, "career_record_events", "reason_codes_json", "TEXT NOT NULL DEFAULT '[]'", migrated)


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
        CREATE UNIQUE INDEX IF NOT EXISTS ux_career_pb_records_active_scope
        ON career_pb_records(pb_type, source_mode, sport_scope)
        WHERE status = 'active'
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_career_pb_records_evidence_version
        ON career_pb_records(pb_type, activity_id, evidence_key, resolver_version)
        WHERE evidence_key IS NOT NULL AND TRIM(evidence_key) != ''
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_career_pb_records_record_scope_status
        ON career_pb_records(record_key, source_mode, scope_hash, status, event_date)
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_career_pb_records_active_v2_scope
        ON career_pb_records(record_key, source_mode, scope_hash)
        WHERE status = 'active'
          AND record_key IS NOT NULL AND TRIM(record_key) != ''
          AND scope_hash IS NOT NULL AND TRIM(scope_hash) != ''
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_career_pb_records_evidence_v2
        ON career_pb_records(record_key, activity_id, evidence_key, resolver_version)
        WHERE record_key IS NOT NULL AND TRIM(record_key) != ''
          AND evidence_key IS NOT NULL AND TRIM(evidence_key) != ''
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_career_pb_records_catalog_state
        ON career_pb_records(catalog_state, status, updated_at)
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
        CREATE INDEX IF NOT EXISTS idx_career_ai_insights_scope_key_status_generated
        ON career_ai_insights(scope, scope_key, status, generated_at)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_career_ai_insights_scope_status_generated
        ON career_ai_insights(scope, status, generated_at)
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
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_career_record_events_record
        ON career_record_events(record_id, event_at)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_career_record_events_activity_type
        ON career_record_events(activity_id, event_type, event_at)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_career_record_events_evidence
        ON career_record_events(pb_type, evidence_key, resolver_version)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_career_record_events_record_scope
        ON career_record_events(record_key, scope_hash, event_at)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_career_record_events_run_decision
        ON career_record_events(run_id, decision, event_at)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_career_event_candidates_type_status_updated
        ON career_event_candidates(candidate_type, status, updated_at)
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_career_record_curve_cache_current
        ON career_record_curve_cache(activity_id, curve_type, source_mode, scope_hash, input_fingerprint, algorithm_version)
        WHERE invalidated_at IS NULL
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_career_record_curve_cache_activity
        ON career_record_curve_cache(activity_id, curve_type, generated_at)
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_career_route_signatures_activity_version
        ON career_route_signatures(activity_id, signature_version)
        WHERE invalidated_at IS NULL
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_career_route_signatures_route_key
        ON career_route_signatures(route_key, sport, invalidated_at)
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_career_route_matches_pair_version
        ON career_route_matches(route_key, activity_id, matched_activity_id, match_version)
        WHERE invalidated_at IS NULL
        """
    )


CAREER_RECORDS_V2_PB_COLUMNS = {
    "record_key",
    "record_family",
    "scope_json",
    "scope_key",
    "scope_hash",
    "range_json",
    "quality_json",
    "metric_value_num",
    "metric_name",
    "catalog_state",
    "rule_version",
}
CAREER_RECORDS_V2_EVENT_COLUMNS = {
    "record_key",
    "scope_hash",
    "scope_key",
    "run_id",
    "decision",
    "reason_codes_json",
}
CAREER_RECORDS_V2_TABLES = {
    "career_record_curve_cache",
    "career_route_signatures",
    "career_route_matches",
}
CAREER_SCHEMA_REQUIRED_TABLES = {
    "career_schema_meta",
    *CAREER_BUSINESS_TABLES,
    "career_record_events",
    *CAREER_RECORDS_V2_TABLES,
}
CAREER_RECORDS_V2_INDEXES = {
    "idx_career_pb_records_record_scope_status",
    "ux_career_pb_records_active_v2_scope",
    "ux_career_pb_records_evidence_v2",
    "idx_career_pb_records_catalog_state",
    "idx_career_record_events_record_scope",
    "idx_career_record_events_run_decision",
    "idx_career_event_candidates_type_status_updated",
    "ux_career_record_curve_cache_current",
    "idx_career_record_curve_cache_activity",
    "ux_career_route_signatures_activity_version",
    "idx_career_route_signatures_route_key",
    "ux_career_route_matches_pair_version",
}
CAREER_RECORD_CURVE_TYPES = {
    "cycling_power_duration_curve",
    "trail_pace_curve",
    "trail_gap_curve",
    "pool_swim_pace_curve",
}
CAREER_RECORD_CURVE_CACHE_FORBIDDEN_KEYS = ACS_PUBLIC_METADATA_FORBIDDEN_KEYS | {
    "absolute_path",
    "file_path",
    "fit_file",
    "full_track",
    "gps_points",
    "lat_lon",
    "local_path",
    "path",
    "points_raw",
    "power_stream",
    "raw_fit",
    "raw_path",
    "raw_points",
    "raw_power",
    "raw_samples",
    "real_lat",
    "real_lon",
    "samples",
    "storage_ref",
    "track",
    "track_json",
    "weight_history",
}


def _normalize_record_curve_cache_text(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _validate_record_curve_cache_type(curve_type: Any) -> str:
    clean_curve_type = _normalize_record_curve_cache_text(curve_type, "curve_type")
    if clean_curve_type not in CAREER_RECORD_CURVE_TYPES:
        raise ValueError(f"unsupported curve_type: {clean_curve_type}")
    return clean_curve_type


def _validate_record_curve_source_mode(source_mode: Any) -> str:
    clean_source_mode = _normalize_record_curve_cache_text(source_mode, "source_mode")
    if clean_source_mode not in RECORD_ALLOWED_SOURCE_MODES:
        raise ValueError(f"unsupported source_mode: {clean_source_mode}")
    return clean_source_mode


def _assert_record_curve_cache_safe_json(value: Any, *, path: str = "curve_cache") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            clean_key = str(key or "").strip()
            normalized_key = clean_key.lower()
            if normalized_key in CAREER_RECORD_CURVE_CACHE_FORBIDDEN_KEYS:
                raise ValueError(f"{path}.{clean_key} is not allowed in curve cache")
            if isinstance(child, str) and _looks_like_local_path(child):
                raise ValueError(f"{path}.{clean_key} must not contain a local path")
            _assert_record_curve_cache_safe_json(child, path=f"{path}.{clean_key}" if clean_key else path)
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _assert_record_curve_cache_safe_json(child, path=f"{path}[{index}]")
        return
    if isinstance(value, str) and _looks_like_local_path(value):
        raise ValueError(f"{path} must not contain a local path")


def _career_record_curve_cache_row_to_dict(row: sqlite3.Row | tuple[Any, ...] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    if isinstance(row, sqlite3.Row):
        values = dict(row)
    else:
        columns = (
            "id",
            "activity_id",
            "sport",
            "curve_type",
            "source_mode",
            "scope_hash",
            "input_fingerprint",
            "algorithm_version",
            "curve_json",
            "quality_json",
            "generated_at",
            "invalidated_at",
            "created_at",
            "updated_at",
        )
        values = dict(zip(columns, row))
    values["curve"] = _json_loads_object(values.get("curve_json"))
    values["quality"] = _json_loads_object(values.get("quality_json"))
    return values


def compute_career_record_curve_input_fingerprint(
    *,
    activity_id: Any,
    sport: Any,
    source_mode: Any,
    canonical_facts_version: Any,
    stream_summary_hash: Any,
    algorithm_version: Any,
    rule_version: Any,
    scope: Any = None,
) -> str:
    """Compute a stable cache fingerprint from safe curve inputs only."""
    clean_source_mode = _validate_record_curve_source_mode(source_mode)
    payload = {
        "activity_id": _normalize_record_curve_cache_text(activity_id, "activity_id"),
        "sport": _normalize_record_curve_cache_text(sport, "sport"),
        "source_mode": clean_source_mode,
        "scope": _canonical_record_scope(scope),
        "canonical_facts_version": _normalize_record_curve_cache_text(canonical_facts_version, "canonical_facts_version"),
        "stream_summary_hash": _normalize_record_curve_cache_text(stream_summary_hash, "stream_summary_hash"),
        "algorithm_version": _normalize_record_curve_cache_text(algorithm_version, "algorithm_version"),
        "rule_version": _normalize_record_curve_cache_text(rule_version, "rule_version"),
    }
    _assert_record_curve_cache_safe_json(payload, path="curve_fingerprint")
    return "sha256:" + hashlib.sha256(_json_dumps(payload).encode("utf-8")).hexdigest()


def get_career_record_curve_cache(
    *,
    activity_id: Any,
    curve_type: Any,
    source_mode: Any,
    scope: Any = None,
    input_fingerprint: Any,
    algorithm_version: Any,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Return the current derived curve cache row for the exact safe cache key."""
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        ensure_career_schema(db)
        clean_activity_id = _normalize_record_curve_cache_text(activity_id, "activity_id")
        clean_curve_type = _validate_record_curve_cache_type(curve_type)
        clean_source_mode = _validate_record_curve_source_mode(source_mode)
        clean_scope_hash = _record_scope_hash(scope)
        clean_fingerprint = _normalize_record_curve_cache_text(input_fingerprint, "input_fingerprint")
        clean_algorithm_version = _normalize_record_curve_cache_text(algorithm_version, "algorithm_version")
        row = db.execute(
            """
            SELECT id, activity_id, sport, curve_type, source_mode, scope_hash,
                   input_fingerprint, algorithm_version, curve_json, quality_json,
                   generated_at, invalidated_at, created_at, updated_at
            FROM career_record_curve_cache
            WHERE activity_id = ?
              AND curve_type = ?
              AND source_mode = ?
              AND scope_hash = ?
              AND input_fingerprint = ?
              AND algorithm_version = ?
              AND invalidated_at IS NULL
            ORDER BY generated_at DESC, updated_at DESC
            LIMIT 1
            """,
            (
                clean_activity_id,
                clean_curve_type,
                clean_source_mode,
                clean_scope_hash,
                clean_fingerprint,
                clean_algorithm_version,
            ),
        ).fetchone()
        return _career_record_curve_cache_row_to_dict(row)
    finally:
        if owns_conn:
            db.close()


def save_career_record_curve_cache(
    *,
    activity_id: Any,
    sport: Any,
    curve_type: Any,
    source_mode: Any,
    scope: Any = None,
    input_fingerprint: Any,
    algorithm_version: Any,
    curve: dict[str, Any],
    quality: dict[str, Any] | None = None,
    generated_at: Any = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Insert or refresh a derived curve cache row without creating formal records."""
    if not isinstance(curve, dict):
        raise ValueError("curve must be a JSON object")
    if quality is not None and not isinstance(quality, dict):
        raise ValueError("quality must be a JSON object")
    _assert_record_curve_cache_safe_json(curve, path="curve")
    _assert_record_curve_cache_safe_json(quality or {}, path="quality")
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        ensure_career_schema(db)
        clean_activity_id = _normalize_record_curve_cache_text(activity_id, "activity_id")
        clean_sport = _normalize_record_curve_cache_text(sport, "sport")
        clean_curve_type = _validate_record_curve_cache_type(curve_type)
        clean_source_mode = _validate_record_curve_source_mode(source_mode)
        clean_scope_hash = _record_scope_hash(scope)
        clean_fingerprint = _normalize_record_curve_cache_text(input_fingerprint, "input_fingerprint")
        clean_algorithm_version = _normalize_record_curve_cache_text(algorithm_version, "algorithm_version")
        clean_generated_at = str(generated_at or _utc_now_iso())
        existing = db.execute(
            """
            SELECT id
            FROM career_record_curve_cache
            WHERE activity_id = ?
              AND curve_type = ?
              AND source_mode = ?
              AND scope_hash = ?
              AND input_fingerprint = ?
              AND algorithm_version = ?
              AND invalidated_at IS NULL
            ORDER BY generated_at DESC, updated_at DESC
            LIMIT 1
            """,
            (
                clean_activity_id,
                clean_curve_type,
                clean_source_mode,
                clean_scope_hash,
                clean_fingerprint,
                clean_algorithm_version,
            ),
        ).fetchone()
        curve_json = _json_dumps(curve)
        quality_json = _json_dumps(quality or {})
        if existing:
            cache_id = existing[0]
            db.execute(
                """
                UPDATE career_record_curve_cache
                SET sport = ?,
                    curve_json = ?,
                    quality_json = ?,
                    generated_at = ?,
                    invalidated_at = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (clean_sport, curve_json, quality_json, clean_generated_at, cache_id),
            )
        else:
            cache_payload = {
                "activity_id": clean_activity_id,
                "curve_type": clean_curve_type,
                "source_mode": clean_source_mode,
                "scope_hash": clean_scope_hash,
                "input_fingerprint": clean_fingerprint,
                "algorithm_version": clean_algorithm_version,
            }
            cache_id = "curve-cache:" + hashlib.sha256(_json_dumps(cache_payload).encode("utf-8")).hexdigest()
            db.execute(
                """
                INSERT INTO career_record_curve_cache (
                    id, activity_id, sport, curve_type, source_mode, scope_hash,
                    input_fingerprint, algorithm_version, curve_json, quality_json,
                    generated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cache_id,
                    clean_activity_id,
                    clean_sport,
                    clean_curve_type,
                    clean_source_mode,
                    clean_scope_hash,
                    clean_fingerprint,
                    clean_algorithm_version,
                    curve_json,
                    quality_json,
                    clean_generated_at,
                ),
            )
        if owns_conn:
            db.commit()
        cached = get_career_record_curve_cache(
            activity_id=clean_activity_id,
            curve_type=clean_curve_type,
            source_mode=clean_source_mode,
            scope=scope,
            input_fingerprint=clean_fingerprint,
            algorithm_version=clean_algorithm_version,
            conn=db,
        )
        if cached is None:
            raise RuntimeError("curve cache write did not produce a readable current row")
        return cached
    except Exception:
        if owns_conn:
            db.rollback()
        raise
    finally:
        if owns_conn:
            db.close()


def invalidate_career_record_curve_cache(
    *,
    activity_id: Any,
    curve_type: Any = None,
    source_mode: Any = None,
    scope: Any = None,
    conn: sqlite3.Connection | None = None,
) -> int:
    """Invalidate derived curve cache rows for an activity or narrower cache scope."""
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        ensure_career_schema(db)
        filters = ["activity_id = ?", "invalidated_at IS NULL"]
        params: list[Any] = [_normalize_record_curve_cache_text(activity_id, "activity_id")]
        if curve_type not in (None, ""):
            filters.append("curve_type = ?")
            params.append(_validate_record_curve_cache_type(curve_type))
        if source_mode not in (None, ""):
            filters.append("source_mode = ?")
            params.append(_validate_record_curve_source_mode(source_mode))
        if scope is not None:
            filters.append("scope_hash = ?")
            params.append(_record_scope_hash(scope))
        result = db.execute(
            f"""
            UPDATE career_record_curve_cache
            SET invalidated_at = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE {' AND '.join(filters)}
            """,
            [_utc_now_iso(), *params],
        )
        if owns_conn:
            db.commit()
        return int(result.rowcount or 0)
    except Exception:
        if owns_conn:
            db.rollback()
        raise
    finally:
        if owns_conn:
            db.close()


def _career_route_signature_row_to_dict(row: sqlite3.Row | tuple[Any, ...] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    values = dict(row) if isinstance(row, sqlite3.Row) else dict(zip((
        "id",
        "activity_id",
        "sport",
        "route_key",
        "direction_key",
        "distance_m",
        "ascent_m",
        "duration_sec",
        "signature_version",
        "signature_json",
        "quality_json",
        "generated_at",
        "invalidated_at",
        "created_at",
        "updated_at",
    ), row))
    values["signature"] = _json_loads_object(values.get("signature_json"))
    values["quality"] = _json_loads_object(values.get("quality_json"))
    return values


def _career_route_match_row_to_dict(row: sqlite3.Row | tuple[Any, ...] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    values = dict(row) if isinstance(row, sqlite3.Row) else dict(zip((
        "id",
        "route_key",
        "activity_id",
        "matched_activity_id",
        "match_version",
        "direction",
        "match_score",
        "coverage_ratio",
        "overlap_ratio",
        "length_error_ratio",
        "decision",
        "reason_codes_json",
        "generated_at",
        "invalidated_at",
        "created_at",
    ), row))
    values["reason_codes"] = [str(item) for item in _json_loads_list(values.get("reason_codes_json")) if str(item or "").strip()]
    return values


def save_career_route_signature(
    *,
    activity_id: Any,
    sport: Any,
    route_key: Any,
    direction_key: Any,
    signature: dict[str, Any],
    quality: dict[str, Any] | None = None,
    distance_m: Any = None,
    ascent_m: Any = None,
    duration_sec: Any = None,
    signature_version: Any = TRAIL_ROUTE_SIGNATURE_VERSION,
    generated_at: Any = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Insert or refresh a derived route signature row without storing raw track data."""
    if not isinstance(signature, dict):
        raise ValueError("signature must be a JSON object")
    if quality is not None and not isinstance(quality, dict):
        raise ValueError("quality must be a JSON object")
    _assert_trail_route_safe_json(signature, path="route_signature")
    _assert_trail_route_safe_json(quality or {}, path="route_quality")
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        ensure_career_schema(db)
        clean_activity_id = _normalize_record_curve_cache_text(activity_id, "activity_id")
        clean_sport = _normalize_record_curve_cache_text(sport, "sport")
        clean_route_key = _normalize_record_curve_cache_text(route_key, "route_key")
        clean_direction_key = _normalize_record_curve_cache_text(direction_key, "direction_key")
        clean_version = _normalize_record_curve_cache_text(signature_version, "signature_version")
        clean_generated_at = str(generated_at or _utc_now_iso())
        row = db.execute(
            """
            SELECT id
            FROM career_route_signatures
            WHERE activity_id = ?
              AND signature_version = ?
              AND invalidated_at IS NULL
            LIMIT 1
            """,
            (clean_activity_id, clean_version),
        ).fetchone()
        signature_json = _json_dumps(signature)
        quality_json = _json_dumps(quality or {})
        parsed_distance = _safe_float(distance_m)
        parsed_ascent = _safe_float(ascent_m)
        parsed_duration = _safe_int(duration_sec, 0) if duration_sec not in (None, "") else None
        if row:
            signature_id = row[0]
            db.execute(
                """
                UPDATE career_route_signatures
                SET sport = ?,
                    route_key = ?,
                    direction_key = ?,
                    distance_m = ?,
                    ascent_m = ?,
                    duration_sec = ?,
                    signature_json = ?,
                    quality_json = ?,
                    generated_at = ?,
                    invalidated_at = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    clean_sport,
                    clean_route_key,
                    clean_direction_key,
                    parsed_distance,
                    parsed_ascent,
                    parsed_duration,
                    signature_json,
                    quality_json,
                    clean_generated_at,
                    signature_id,
                ),
            )
        else:
            signature_id = "route-signature:" + hashlib.sha256(_json_dumps({
                "activity_id": clean_activity_id,
                "signature_version": clean_version,
            }).encode("utf-8")).hexdigest()
            db.execute(
                """
                INSERT INTO career_route_signatures (
                    id, activity_id, sport, route_key, direction_key, distance_m,
                    ascent_m, duration_sec, signature_version, signature_json,
                    quality_json, generated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signature_id,
                    clean_activity_id,
                    clean_sport,
                    clean_route_key,
                    clean_direction_key,
                    parsed_distance,
                    parsed_ascent,
                    parsed_duration,
                    clean_version,
                    signature_json,
                    quality_json,
                    clean_generated_at,
                ),
            )
        if owns_conn:
            db.commit()
        saved = get_career_route_signature(activity_id=clean_activity_id, signature_version=clean_version, conn=db)
        if saved is None:
            raise RuntimeError("route signature write did not produce a readable current row")
        return saved
    except Exception:
        if owns_conn:
            db.rollback()
        raise
    finally:
        if owns_conn:
            db.close()


def get_career_route_signature(
    *,
    activity_id: Any,
    signature_version: Any = TRAIL_ROUTE_SIGNATURE_VERSION,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        ensure_career_schema(db)
        row = db.execute(
            """
            SELECT id, activity_id, sport, route_key, direction_key, distance_m,
                   ascent_m, duration_sec, signature_version, signature_json,
                   quality_json, generated_at, invalidated_at, created_at, updated_at
            FROM career_route_signatures
            WHERE activity_id = ?
              AND signature_version = ?
              AND invalidated_at IS NULL
            ORDER BY generated_at DESC, updated_at DESC
            LIMIT 1
            """,
            (
                _normalize_record_curve_cache_text(activity_id, "activity_id"),
                _normalize_record_curve_cache_text(signature_version, "signature_version"),
            ),
        ).fetchone()
        return _career_route_signature_row_to_dict(row)
    finally:
        if owns_conn:
            db.close()


def save_career_route_match(
    *,
    route_key: Any,
    activity_id: Any,
    matched_activity_id: Any,
    match: dict[str, Any],
    match_version: Any = TRAIL_ROUTE_MATCH_VERSION,
    generated_at: Any = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Insert or refresh a derived route match row; never creates an active record."""
    if not isinstance(match, dict):
        raise ValueError("match must be a JSON object")
    _assert_trail_route_safe_json(match, path="route_match")
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        ensure_career_schema(db)
        clean_route_key = _normalize_record_curve_cache_text(route_key, "route_key")
        clean_activity_id = _normalize_record_curve_cache_text(activity_id, "activity_id")
        clean_matched_activity_id = _normalize_record_curve_cache_text(matched_activity_id, "matched_activity_id")
        clean_version = _normalize_record_curve_cache_text(match_version, "match_version")
        clean_generated_at = str(generated_at or _utc_now_iso())
        direction = str(match.get("direction") or "unknown").strip()
        decision = str(match.get("decision") or "ignored").strip()
        reason_codes = list(_dedupe_reason_codes(tuple(str(item) for item in match.get("reason_codes") or ())))
        _assert_trail_route_safe_json({"reason_codes": reason_codes}, path="route_match")
        row = db.execute(
            """
            SELECT id
            FROM career_route_matches
            WHERE route_key = ?
              AND activity_id = ?
              AND matched_activity_id = ?
              AND match_version = ?
              AND invalidated_at IS NULL
            LIMIT 1
            """,
            (clean_route_key, clean_activity_id, clean_matched_activity_id, clean_version),
        ).fetchone()
        if row:
            match_id = row[0]
            db.execute(
                """
                UPDATE career_route_matches
                SET direction = ?,
                    match_score = ?,
                    coverage_ratio = ?,
                    overlap_ratio = ?,
                    length_error_ratio = ?,
                    decision = ?,
                    reason_codes_json = ?,
                    generated_at = ?,
                    invalidated_at = NULL
                WHERE id = ?
                """,
                (
                    direction,
                    _safe_float(match.get("match_score")) or 0.0,
                    _safe_float(match.get("coverage_ratio")),
                    _safe_float(match.get("overlap_ratio")),
                    _safe_float(match.get("length_error_ratio")),
                    decision,
                    _json_dumps(reason_codes),
                    clean_generated_at,
                    match_id,
                ),
            )
        else:
            match_id = "route-match:" + hashlib.sha256(_json_dumps({
                "route_key": clean_route_key,
                "activity_id": clean_activity_id,
                "matched_activity_id": clean_matched_activity_id,
                "match_version": clean_version,
            }).encode("utf-8")).hexdigest()
            db.execute(
                """
                INSERT INTO career_route_matches (
                    id, route_key, activity_id, matched_activity_id, match_version,
                    direction, match_score, coverage_ratio, overlap_ratio,
                    length_error_ratio, decision, reason_codes_json, generated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    match_id,
                    clean_route_key,
                    clean_activity_id,
                    clean_matched_activity_id,
                    clean_version,
                    direction,
                    _safe_float(match.get("match_score")) or 0.0,
                    _safe_float(match.get("coverage_ratio")),
                    _safe_float(match.get("overlap_ratio")),
                    _safe_float(match.get("length_error_ratio")),
                    decision,
                    _json_dumps(reason_codes),
                    clean_generated_at,
                ),
            )
        if owns_conn:
            db.commit()
        saved = db.execute(
            """
            SELECT id, route_key, activity_id, matched_activity_id, match_version,
                   direction, match_score, coverage_ratio, overlap_ratio,
                   length_error_ratio, decision, reason_codes_json, generated_at,
                   invalidated_at, created_at
            FROM career_route_matches
            WHERE id = ?
            LIMIT 1
            """,
            (match_id,),
        ).fetchone()
        result = _career_route_match_row_to_dict(saved)
        if result is None:
            raise RuntimeError("route match write did not produce a readable current row")
        return result
    except Exception:
        if owns_conn:
            db.rollback()
        raise
    finally:
        if owns_conn:
            db.close()


def get_trail_route_comparison_viewmodel(
    payload: dict[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Return safe route match comparison rows without exposing route signatures."""
    start = time.perf_counter()
    raw = payload if isinstance(payload, dict) else {}
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        schema = ensure_career_schema(db)
        where_parts = ["invalidated_at IS NULL"]
        params: list[Any] = []
        for key in ("route_key", "activity_id", "matched_activity_id", "decision", "direction"):
            value = str(raw.get(key) or "").strip()
            if value:
                where_parts.append(f"{key} = ?")
                params.append(value)
        rows = db.execute(
            f"""
            SELECT id, route_key, activity_id, matched_activity_id, match_version,
                   direction, match_score, coverage_ratio, overlap_ratio,
                   length_error_ratio, decision, reason_codes_json, generated_at
            FROM career_route_matches
            WHERE {' AND '.join(where_parts)}
            ORDER BY generated_at DESC, route_key ASC, activity_id ASC, matched_activity_id ASC
            LIMIT 100
            """,
            tuple(params),
        ).fetchall()
        matches = []
        for row in rows:
            data = _career_route_match_row_to_dict(row)
            if not data:
                continue
            matches.append({
                "id": str(data.get("id") or ""),
                "route_key": str(data.get("route_key") or ""),
                "activity_id": str(data.get("activity_id") or ""),
                "matched_activity_id": str(data.get("matched_activity_id") or ""),
                "match_version": str(data.get("match_version") or ""),
                "direction": str(data.get("direction") or ""),
                "match_score": _safe_float(data.get("match_score")),
                "coverage_ratio": _safe_float(data.get("coverage_ratio")),
                "overlap_ratio": _safe_float(data.get("overlap_ratio")),
                "length_error_ratio": _safe_float(data.get("length_error_ratio")),
                "decision": str(data.get("decision") or ""),
                "reason_codes": list(data.get("reason_codes") or []),
                "candidate_only": str(data.get("decision") or "") == "candidate",
                "source_refs": {
                    "activity_id": str(data.get("activity_id") or ""),
                    "matched_activity_id": str(data.get("matched_activity_id") or ""),
                },
                "generated_at": str(data.get("generated_at") or ""),
            })
        response = {
            "matches": matches,
            "summary": {
                "returned_count": len(matches),
                "candidate_count": sum(1 for match in matches if match.get("decision") == "candidate"),
                "ignored_count": sum(1 for match in matches if match.get("decision") == "ignored"),
                "route_candidates": sum(1 for match in matches if match.get("decision") == "candidate"),
                "verified_real_data": False,
            },
            "filters": {
                "route_key": str(raw.get("route_key") or ""),
                "activity_id": str(raw.get("activity_id") or ""),
                "matched_activity_id": str(raw.get("matched_activity_id") or ""),
                "decision": str(raw.get("decision") or ""),
                "direction": str(raw.get("direction") or ""),
            },
            "metrics": {
                "elapsed_ms": _elapsed_ms(start),
                "returned_count": len(matches),
                "performance_target_ms": RECORDS_V2_PERFORMANCE_TARGETS_MS["route_comparison"],
                "cache_hit": bool(matches),
                "cache_miss": not bool(matches),
                "route_candidates": sum(1 for match in matches if match.get("decision") == "candidate"),
            },
            "status": _records_v2_status(
                schema,
                data_ready=bool(matches),
                state="ready" if matches else "empty",
                message="路线对比已生成" if matches else "暂无路线对比",
            ),
        }
        return _records_api_safe(response)
    finally:
        if owns_conn:
            db.close()


def cleanup_career_record_curve_cache_versions(
    *,
    curve_type: Any,
    keep_algorithm_versions: tuple[str, ...] | list[str] | set[str],
    conn: sqlite3.Connection | None = None,
) -> dict[str, int]:
    """Invalidate current curve cache rows whose algorithm_version is no longer kept."""
    clean_curve_type = _validate_record_curve_cache_type(curve_type)
    keep_versions = tuple(sorted(str(version).strip() for version in keep_algorithm_versions if str(version).strip()))
    if not keep_versions:
        raise ValueError("keep_algorithm_versions must not be empty")
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        ensure_career_schema(db)
        placeholders = ",".join("?" for _ in keep_versions)
        result = db.execute(
            f"""
            UPDATE career_record_curve_cache
            SET invalidated_at = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE curve_type = ?
              AND invalidated_at IS NULL
              AND algorithm_version NOT IN ({placeholders})
            """,
            [_utc_now_iso(), clean_curve_type, *keep_versions],
        )
        if owns_conn:
            db.commit()
        return {"invalidated": int(result.rowcount or 0)}
    except Exception:
        if owns_conn:
            db.rollback()
        raise
    finally:
        if owns_conn:
            db.close()


def plan_career_records_v2_schema_migration(conn: sqlite3.Connection) -> dict[str, Any]:
    """Return a read-only V2 schema migration plan without changing the database."""
    missing_tables = sorted(table for table in CAREER_RECORDS_V2_TABLES if not _table_exists(conn, table))
    pb_columns = set()
    if _table_exists(conn, "career_pb_records"):
        pb_columns = {row[1] for row in conn.execute("PRAGMA table_info(career_pb_records)").fetchall()}
    event_columns = set()
    if _table_exists(conn, "career_record_events"):
        event_columns = {row[1] for row in conn.execute("PRAGMA table_info(career_record_events)").fetchall()}
    missing_columns = [
        *(f"career_pb_records.{column}" for column in sorted(CAREER_RECORDS_V2_PB_COLUMNS - pb_columns)),
        *(f"career_record_events.{column}" for column in sorted(CAREER_RECORDS_V2_EVENT_COLUMNS - event_columns)),
    ]
    missing_indexes = sorted(index for index in CAREER_RECORDS_V2_INDEXES if not _index_exists(conn, index))
    legacy_rows_to_backfill = 0
    active_scope_conflicts: list[dict[str, Any]] = []
    if _table_exists(conn, "career_pb_records"):
        where_parts = []
        if "record_key" in pb_columns:
            where_parts.append("(record_key IS NULL OR TRIM(record_key) = '')")
        if "scope_hash" in pb_columns:
            where_parts.append("(scope_hash IS NULL OR TRIM(scope_hash) = '')")
        if "metric_value_num" in pb_columns:
            where_parts.append("metric_value_num IS NULL")
        legacy_where = " OR ".join(where_parts) if where_parts else "1=1"
        legacy_rows_to_backfill = _count_rows(conn, "career_pb_records", legacy_where)
        if {"record_key", "source_mode", "scope_hash", "status"}.issubset(pb_columns):
            rows = conn.execute(
                """
                SELECT record_key, source_mode, scope_hash, COUNT(*) AS count
                FROM career_pb_records
                WHERE status = 'active'
                  AND record_key IS NOT NULL AND TRIM(record_key) != ''
                  AND scope_hash IS NOT NULL AND TRIM(scope_hash) != ''
                GROUP BY record_key, source_mode, scope_hash
                HAVING COUNT(*) > 1
                """
            ).fetchall()
            for row in rows:
                active_scope_conflicts.append({
                    "record_key": row[0],
                    "source_mode": row[1],
                    "scope_hash": row[2],
                    "count": int(row[3] or 0),
                })
    return {
        "ok": not active_scope_conflicts,
        "dry_run": True,
        "would_create_tables": missing_tables,
        "would_add_columns": missing_columns,
        "would_create_indexes": missing_indexes,
        "legacy_rows_to_backfill": legacy_rows_to_backfill,
        "active_scope_conflicts": active_scope_conflicts,
        "blocked": bool(active_scope_conflicts),
        "status": {
            "schema_ready": _table_exists(conn, "career_pb_records"),
            "message": "V2 schema migration dry-run complete",
        },
    }


def _career_schema_is_current(conn: sqlite3.Connection) -> bool:
    placeholders = ",".join("?" for _ in CAREER_SCHEMA_REQUIRED_TABLES)
    table_count_row = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM sqlite_master
        WHERE type = 'table'
          AND name IN ({placeholders})
        """,
        tuple(sorted(CAREER_SCHEMA_REQUIRED_TABLES)),
    ).fetchone()
    if int(table_count_row[0] or 0) != len(CAREER_SCHEMA_REQUIRED_TABLES):
        return False
    version_row = conn.execute(
        "SELECT value FROM career_schema_meta WHERE key = 'schema_version'"
    ).fetchone()
    return bool(version_row and str(version_row[0] or "") == CAREER_SCHEMA_VERSION)


def ensure_career_schema(conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """Ensure the ACS schema baseline and derived-index tables exist."""
    global CAREER_DEFAULT_SCHEMA_READY, CAREER_DEFAULT_SCHEMA_READY_PATH
    owns_conn = conn is None
    default_db_path = str(Path(profile_backend.DB_PATH).expanduser()) if owns_conn else ""
    if owns_conn and CAREER_DEFAULT_SCHEMA_READY and CAREER_DEFAULT_SCHEMA_READY_PATH == default_db_path:
        return {
            "ok": True,
            "schema_version": CAREER_SCHEMA_VERSION,
            "created": [],
            "migrated": [],
            "cached": True,
        }
    db = conn or _connect_default()
    created: list[str] = []
    migrated: list[str] = []
    savepoint_name = "career_schema_migration"
    try:
        with CAREER_SCHEMA_ENSURE_LOCK:
            if owns_conn and CAREER_DEFAULT_SCHEMA_READY and CAREER_DEFAULT_SCHEMA_READY_PATH == default_db_path:
                return {
                    "ok": True,
                    "schema_version": CAREER_SCHEMA_VERSION,
                    "created": [],
                    "migrated": [],
                    "cached": True,
                }
            if _career_schema_is_current(db):
                if owns_conn:
                    CAREER_DEFAULT_SCHEMA_READY = True
                    CAREER_DEFAULT_SCHEMA_READY_PATH = default_db_path
                return {
                    "ok": True,
                    "schema_version": CAREER_SCHEMA_VERSION,
                    "created": [],
                    "migrated": [],
                    "cached": True,
                }
            db.execute(f"SAVEPOINT {savepoint_name}")
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
            _ensure_career_pb_record_columns(db, migrated)
            _ensure_career_record_event_columns(db, migrated)
            _ensure_career_light_memory_columns(db, migrated)
            _ensure_career_indexes(db)
            db.execute(f"RELEASE SAVEPOINT {savepoint_name}")

            if owns_conn:
                db.commit()
                CAREER_DEFAULT_SCHEMA_READY = True
                CAREER_DEFAULT_SCHEMA_READY_PATH = default_db_path
        return {
            "ok": True,
            "schema_version": CAREER_SCHEMA_VERSION,
            "created": created,
            "migrated": migrated,
            "cached": False,
        }
    except Exception:
        try:
            db.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
            db.execute(f"RELEASE SAVEPOINT {savepoint_name}")
        except sqlite3.Error:
            pass
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
        "is_system_detected": source == "resolver",
        "needs_user_judgement": source == "resolver",
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


def _career_footprint_activity_select_expr(conn: sqlite3.Connection, column_name: str) -> str:
    if column_name in ACS_FORBIDDEN_RESPONSE_KEYS:
        raise ValueError(f"Forbidden ACS footprint activity column: {column_name}")
    if _column_exists(conn, "activities", column_name):
        return f"{column_name} AS {column_name}"
    return f"NULL AS {column_name}"


def _career_footprint_activity_rows(conn: sqlite3.Connection, filters: dict[str, Any]) -> list[dict[str, Any]]:
    columns = (
        "id",
        "start_time",
        "start_time_utc",
        "sport_type",
        "sub_sport_type",
        "region",
        "region_city",
        "region_country",
        "region_display",
        "region_state",
        "state",
        "province",
        "city",
        "cityName",
        "country",
        "countryName",
        "deleted_at",
    )
    select_sql = ", ".join(_career_footprint_activity_select_expr(conn, column) for column in columns)
    cursor = conn.execute(
        f"""
        SELECT {select_sql}
        FROM activities
        WHERE {_deleted_filter(conn)}
        ORDER BY COALESCE(NULLIF(start_time, ''), NULLIF(start_time_utc, '')) DESC, id DESC
        """
    )
    rows: list[dict[str, Any]] = []
    for row in _rows_to_dicts(cursor):
        sport = _overview_activity_sport(row)
        if filters.get("sport") != "all" and sport != filters.get("sport"):
            continue
        event_date = _overview_activity_date(row)
        if filters.get("year") is not None and _safe_activity_year(event_date) != int(filters["year"]):
            continue
        row["_footprint_sport"] = sport
        row["_footprint_event_date"] = event_date
        rows.append(row)
    return rows


def _career_footprint_active_race_activity_ids(conn: sqlite3.Connection) -> set[str]:
    if not _table_exists(conn, "career_race_events"):
        return set()
    cursor = conn.execute("SELECT activity_id FROM career_race_events WHERE status = 'active'")
    return {str(row[0] or "").strip() for row in cursor.fetchall() if str(row[0] or "").strip()}


def _empty_career_footprint_region(region: dict[str, Any]) -> dict[str, Any]:
    return {
        "region_key": str(region.get("region_key") or ""),
        "name": str(region.get("name") or ""),
        "country": str(region.get("country") or ""),
        "country_code": str(region.get("country_code") or ""),
        "level": str(region.get("level") or ""),
        "map_mode": str(region.get("map_mode") or "china"),
        "activity_count": 0,
        "race_count": 0,
        "first_activity_date": "",
        "latest_activity_date": "",
        "representative_activity_id": "",
        "cities": set(),
    }


def _build_career_footprint_region_record(bucket: dict[str, Any]) -> dict[str, Any]:
    cities = sorted(str(city) for city in (bucket.get("cities") or set()) if str(city))
    representative_activity_id = str(bucket.get("representative_activity_id") or "")
    return {
        "region_key": str(bucket.get("region_key") or ""),
        "name": str(bucket.get("name") or ""),
        "country": str(bucket.get("country") or ""),
        "country_code": str(bucket.get("country_code") or ""),
        "level": str(bucket.get("level") or ""),
        "map_mode": str(bucket.get("map_mode") or "china"),
        "activity_count": int(bucket.get("activity_count") or 0),
        "race_count": int(bucket.get("race_count") or 0),
        "first_activity_date": str(bucket.get("first_activity_date") or ""),
        "latest_activity_date": str(bucket.get("latest_activity_date") or ""),
        "representative_activity_id": representative_activity_id,
        "city_count": len(cities),
        "cities": cities[:8],
        "detail_link": {
            "activity_id": representative_activity_id,
            "source": "career",
        } if representative_activity_id else {},
    }


def _career_footprint_without_region_item(row: dict[str, Any]) -> dict[str, Any]:
    activity_id = str(row.get("id") or "")
    return {
        "activity_id": activity_id,
        "event_date": str(row.get("_footprint_event_date") or ""),
        "sport": str(row.get("_footprint_sport") or "unknown"),
        "sport_label": _overview_sport_label(row.get("_footprint_sport") or "unknown"),
        "reason": _career_footprint_missing_reason(row),
        "detail_link": {
            "activity_id": activity_id,
            "source": "career",
        } if activity_id else {},
    }


def _summarize_career_footprint(
    rows: list[dict[str, Any]],
    regions: list[dict[str, Any]],
    without_region: list[dict[str, Any]],
) -> dict[str, int]:
    return {
        "activity_count": len(rows),
        "region_count": len(regions),
        "country_count": len({str(region.get("country_code") or region.get("country") or "") for region in regions if str(region.get("country_code") or region.get("country") or "")}),
        "china_region_count": sum(1 for region in regions if str(region.get("country_code") or "") == "CN"),
        "overseas_region_count": sum(1 for region in regions if str(region.get("country_code") or "") != "CN"),
        "without_region_count": len(without_region),
    }


def get_career_footprint(
    filters: dict[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Return Activity-backed career footprint regions without exposing track data."""
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        schema = ensure_career_schema(db)
        normalized_filters = _normalize_footprint_filters(filters)
        if not _table_exists(db, "activities"):
            return {
                "map_mode": "china",
                "regions": [],
                "without_region": [],
                "summary": _summarize_career_footprint([], [], []),
                "filters": normalized_filters,
                "status": {
                    "schema_ready": bool(schema.get("ok")),
                    "data_ready": False,
                    "message": CAREER_FOOTPRINT_EMPTY_STATUS_MESSAGE,
                },
            }

        rows = _career_footprint_activity_rows(db, normalized_filters)
        race_activity_ids = _career_footprint_active_race_activity_ids(db)
        buckets: dict[str, dict[str, Any]] = {}
        without_region: list[dict[str, Any]] = []
        for row in rows:
            region = _resolve_career_footprint_region(row)
            if not region:
                without_region.append(_career_footprint_without_region_item(row))
                continue
            region_key = str(region.get("region_key") or "")
            if not region_key:
                without_region.append(_career_footprint_without_region_item(row))
                continue
            bucket = buckets.setdefault(region_key, _empty_career_footprint_region(region))
            activity_id = str(row.get("id") or "")
            event_date = str(row.get("_footprint_event_date") or "")
            bucket["activity_count"] = int(bucket.get("activity_count") or 0) + 1
            if activity_id and activity_id in race_activity_ids:
                bucket["race_count"] = int(bucket.get("race_count") or 0) + 1
            if event_date:
                current_first = str(bucket.get("first_activity_date") or "")
                current_latest = str(bucket.get("latest_activity_date") or "")
                if not current_first or event_date < current_first:
                    bucket["first_activity_date"] = event_date
                if not current_latest or event_date > current_latest:
                    bucket["latest_activity_date"] = event_date
                    bucket["representative_activity_id"] = activity_id
            elif not bucket.get("representative_activity_id"):
                bucket["representative_activity_id"] = activity_id
            city = str(region.get("city") or "").strip()
            if city:
                bucket["cities"].add(city)

        regions = [
            _build_career_footprint_region_record(bucket)
            for bucket in buckets.values()
        ]
        regions.sort(key=lambda item: (-int(item.get("activity_count") or 0), str(item.get("country_code") or ""), str(item.get("name") or "")))
        map_mode = "world" if any(str(region.get("country_code") or "") != "CN" for region in regions) else "china"
        summary = _summarize_career_footprint(rows, regions, without_region)
        data_ready = bool(regions or without_region)
        return {
            "map_mode": map_mode,
            "regions": regions,
            "without_region": without_region,
            "summary": summary,
            "filters": normalized_filters,
            "status": {
                "schema_ready": bool(schema.get("ok")),
                "data_ready": data_ready,
                "message": CAREER_FOOTPRINT_READY_STATUS_MESSAGE if data_ready else CAREER_FOOTPRINT_EMPTY_STATUS_MESSAGE,
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


def _pb_source_mode_label(source_mode: Any) -> str:
    key = str(source_mode or "activity_total").strip().lower() or "activity_total"
    labels = {
        "activity_total": "整场活动",
        "best_effort_duration": "固定时长最佳努力",
        "best_effort_distance": "固定距离最佳努力",
        "route_total": "同路线",
        "segment": "赛段",
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
    source_mode = str(row.get("source_mode") or "activity_total")
    resolver_version = str(row.get("resolver_version") or "legacy")
    status = str(row.get("status") or "active")
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
        "source_mode": source_mode,
        "source_mode_label": _pb_source_mode_label(source_mode),
        "sport_scope": str(row.get("sport_scope") or "default"),
        "resolver_version": resolver_version,
        "status": status,
        "evidence_key": str(row.get("evidence_key") or ""),
        "previous_record_id": row.get("previous_record_id"),
        "confidence_label": _race_confidence_label(confidence_level, confidence),
        "display_metadata": display_metadata,
        "detail_link": {
            "activity_id": activity_id,
            "source": "career",
            "record_id": str(row.get("id") or ""),
        },
    }


RECORDS_API_FORBIDDEN_TEXT = (
    "points_json",
    "track_json",
    "raw_records",
    "fit_records",
    "raw_fit",
    "raw_stream",
    "power_stream",
    "gps_points",
    "route_signature",
    "file_path",
    "storage_ref",
    "sqlite_master",
    "sqlite_schema",
    "CREATE TABLE",
    "device_serial",
    "serial_number",
    "weight_history",
    "evidence_json",
    "/Users/",
    "\\Users\\",
    "file://",
)
RECORDS_V2_PERFORMANCE_TARGETS_MS = {
    "records_list": 200,
    "record_history": 250,
    "record_curve": 150,
    "record_candidates": 200,
    "route_comparison": 250,
    "rebuild_plan": 1000,
}
RECORDS_V2_OBSERVABILITY_ALLOWED_FIELDS = {
    "event",
    "run_id",
    "dry_run",
    "action",
    "decision",
    "candidate_id",
    "record_id",
    "record_key",
    "sport",
    "family",
    "reason",
    "status",
    "state",
    "processed",
    "returned_count",
    "candidate_count",
    "route_candidates",
    "cache_hit",
    "cache_miss",
    "curve_cache_count",
    "route_match_count",
    "route_cache_count",
    "elapsed_ms",
    "by_sport",
    "by_family",
    "by_reason",
}
RECORDS_V2_OBSERVABILITY_FORBIDDEN_FIELDS = {
    str(item).lower()
    for item in RECORDS_API_FORBIDDEN_TEXT
} | {
    "payload",
    "payload_json",
    "candidate_evidence",
    "record_decision",
    "curve_json",
    "quality_json",
    "input_fingerprint",
    "stream_summary_hash",
    "track",
    "path",
    "schema",
}


def records_v2_observability_contract() -> dict[str, Any]:
    """Return the Records V2 safety/performance/logging contract for tests and docs."""
    return {
        "performance_targets_ms": dict(RECORDS_V2_PERFORMANCE_TARGETS_MS),
        "allowed_log_fields": sorted(RECORDS_V2_OBSERVABILITY_ALLOWED_FIELDS),
        "forbidden_log_fields": sorted(RECORDS_V2_OBSERVABILITY_FORBIDDEN_FIELDS),
        "high_risk_operations": {
            "decide_career_record_candidate": {
                "requires": ["candidate_id", "decision"],
                "allowed_decisions": ["confirm", "reject"],
                "submits_candidate_values": False,
            },
            "rebuild_career_records": {
                "default_dry_run": True,
                "real_apply_requires": "apply_to_real_db=true",
                "supports": ["batch_size", "max_activities", "cancel_after", "savepoint_rollback"],
            },
        },
        "failure_policy": "diagnose_with_safe_counts_without_blocking_activity_detail",
    }


def records_v2_safe_observation(event: str, **fields: Any) -> dict[str, Any]:
    """Build a whitelisted observability payload without raw evidence or local paths."""
    observation: dict[str, Any] = {"event": str(event or "")}
    for key, value in fields.items():
        clean_key = str(key or "").strip()
        normalized_key = clean_key.lower()
        if not clean_key:
            continue
        if normalized_key in RECORDS_V2_OBSERVABILITY_FORBIDDEN_FIELDS:
            continue
        if clean_key not in RECORDS_V2_OBSERVABILITY_ALLOWED_FIELDS:
            continue
        if isinstance(value, dict):
            observation[clean_key] = {
                str(child_key): int(child_value or 0)
                for child_key, child_value in value.items()
                if str(child_key or "").strip().lower() not in RECORDS_V2_OBSERVABILITY_FORBIDDEN_FIELDS
            }
        elif isinstance(value, bool):
            observation[clean_key] = bool(value)
        elif isinstance(value, (int, float)):
            observation[clean_key] = round(float(value), 2) if isinstance(value, float) else int(value)
        elif value is None:
            observation[clean_key] = None
        else:
            text = str(value)
            lowered = text.lower()
            if any(token in lowered for token in ("/users/", "\\users\\", "file://", "sqlite_master", "create table")):
                continue
            observation[clean_key] = text[:120]
    return observation


def _records_v2_cache_route_observability(conn: sqlite3.Connection) -> dict[str, int]:
    curve_cache_count = _count_rows(conn, "career_record_curve_cache", "invalidated_at IS NULL")
    route_cache_count = _count_rows(conn, "career_route_signatures", "invalidated_at IS NULL")
    route_match_count = _count_rows(conn, "career_route_matches", "invalidated_at IS NULL")
    route_candidates = _count_rows(conn, "career_route_matches", "invalidated_at IS NULL AND decision = 'candidate'")
    return {
        "curve_cache_count": int(curve_cache_count),
        "route_cache_count": int(route_cache_count),
        "route_match_count": int(route_match_count),
        "route_candidates": int(route_candidates),
    }


def _records_v2_status(
    schema: dict[str, Any],
    *,
    data_ready: bool,
    state: str | None = None,
    message: str = "",
    candidate_count: int = 0,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    resolved_state = state or ("ready" if data_ready else "empty")
    return {
        "schema_ready": bool(schema.get("ok")),
        "data_ready": bool(data_ready),
        "state": resolved_state,
        "message": message,
        "records_version": "records-v2",
        "resolver_version": RECORDS_V2_RULE_VERSION,
        "catalog_version": "records-center-v2-catalog",
        "rebuilding": bool(_RECORDS_REBUILD_IN_PROGRESS),
        "partial": resolved_state == "partial",
        "validation_required": resolved_state == "validation_required",
        "candidate_count": int(candidate_count or 0),
        "last_rebuild_run_id": None,
        "last_rebuild_at": None,
        "warnings": warnings or [],
    }


def _normalize_records_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    raw = filters if isinstance(filters, dict) else {}
    year = None
    year_value = raw.get("year")
    if year_value not in (None, "", "all"):
        try:
            parsed_year = int(year_value)
            if 1900 <= parsed_year <= 3000:
                year = parsed_year
        except (TypeError, ValueError):
            year = None
    return {
        "sport": str(raw.get("sport") or "all").strip() or "all",
        "record_key": str(raw.get("record_key") or raw.get("pb_type") or "all").strip() or "all",
        "family": str(raw.get("family") or "all").strip() or "all",
        "scope_hash": str(raw.get("scope_hash") or "all").strip() or "all",
        "status": str(raw.get("status") or "active").strip() or "active",
        "year": year,
    }


def _record_metric_display(value: Any, unit: Any) -> str:
    unit_text = str(unit or "").strip().lower()
    if unit_text == "watts":
        parsed = _safe_float(value)
        return f"{parsed:g} W" if parsed is not None else ""
    if unit_text == "kilojoules":
        parsed = _safe_float(value)
        return f"{parsed:g} kJ" if parsed is not None else ""
    if unit_text in {"meters_ascent", "meters_altitude"}:
        parsed = _safe_float(value)
        return f"{parsed:g} m" if parsed is not None else ""
    return _pb_value_display(value, unit_text)


def _record_improvement_view(value: Any, unit: Any) -> dict[str, Any]:
    if value in (None, ""):
        return {"value": None, "unit": str(unit or ""), "display": "首次记录", "direction": "initial"}
    parsed = _safe_float(value)
    if parsed is None or parsed <= 0:
        return {"value": parsed, "unit": str(unit or ""), "display": "暂无提升记录", "direction": "none"}
    return {
        "value": parsed,
        "unit": str(unit or ""),
        "display": f"+{_record_metric_display(parsed, unit)}" if str(unit or "").lower() != "seconds" else f"提升 {_format_duration_seconds(parsed)}",
        "direction": "improved",
    }


def _scope_label(key: str, value: Any) -> str:
    clean = str(value or "").strip()
    labels = {
        "sport_scope": {"outdoor": "户外", "indoor": "室内", "default": "默认"},
        "indoor_scope": {"trainer": "骑行台", "outdoor": "户外"},
        "power_metric_scope": {"raw_power_w": "原始功率"},
        "water_scope": {"pool": "泳池", "open_water": "公开水域"},
    }
    return labels.get(key, {}).get(clean, clean)


def _record_scope_view(row: dict[str, Any]) -> dict[str, Any]:
    dimensions = _json_loads_object(row.get("scope_json"))
    if not dimensions:
        dimensions = _legacy_record_scope_json(row.get("sport_scope"))
    labels = [_scope_label(key, value) for key, value in sorted(dimensions.items()) if str(value or "").strip()]
    return {
        "scope_hash": str(row.get("scope_hash") or _record_scope_hash(dimensions)),
        "scope_key": str(row.get("scope_key") or row.get("sport_scope") or "default"),
        "labels": labels,
        "dimensions": dimensions,
    }


def _record_range_view(row: dict[str, Any]) -> dict[str, Any]:
    range_json = canonicalize_record_range(row.get("range_json"))
    if not range_json:
        return {}
    view = dict(range_json)
    start_sec = _safe_float(view.get("start_sec"))
    end_sec = _safe_float(view.get("end_sec"))
    if start_sec is not None and end_sec is not None:
        view.setdefault("type", "time_window")
        view["display"] = f"第 {_format_duration_seconds(start_sec)} - {_format_duration_seconds(end_sec)}"
    elif view.get("distance_m"):
        view.setdefault("type", "distance_window")
        view["display"] = _record_metric_display(view.get("distance_m"), "meters")
    return view


def _record_definition_for_row(row: dict[str, Any]) -> RecordDefinition | None:
    return get_record_definition(str(row.get("record_key") or row.get("pb_type") or ""))


def _build_career_record_view(row: dict[str, Any]) -> dict[str, Any]:
    definition = _record_definition_for_row(row)
    record_key = str(row.get("record_key") or row.get("pb_type") or "")
    sport = str(row.get("sport") or (definition.sport if definition else "unknown"))
    family = str(row.get("record_family") or (_record_definition_family(definition) if definition else "legacy"))
    metric_name = str(row.get("metric_name") or (definition.metric if definition else ""))
    metric_value = row.get("metric_value_num") if row.get("metric_value_num") is not None else row.get("value")
    metric_unit = str(row.get("value_unit") or (definition.canonical_unit if definition else ""))
    comparison = definition.comparison if definition else "lower_is_better"
    axis_direction = _record_axis_direction(definition) if definition else ("lower" if comparison == "lower_is_better" else "higher")
    quality = canonicalize_record_quality(row.get("quality_json"))
    if "confidence" not in quality:
        parsed_confidence = _safe_float(row.get("confidence"))
        if parsed_confidence is not None:
            quality["confidence"] = parsed_confidence
    quality.setdefault("reason_codes", [])
    quality.setdefault("message_key", "record_quality_high" if _safe_float(quality.get("confidence")) and float(quality["confidence"]) > 0.9 else "record_quality_review")
    event_date = str(row.get("event_date") or "")
    year, month, display_date = _race_display_date_parts(event_date)
    record_id = str(row.get("id") or "")
    activity_id = str(row.get("activity_id") or "")
    return {
        "id": record_id,
        "activity_id": activity_id,
        "record_key": record_key,
        "pb_type": str(row.get("pb_type") or record_key),
        "display_name": definition.display_name if definition else _pb_type_label(record_key),
        "sport": sport,
        "sport_label": RECORD_SPORT_LABELS.get(sport, _career_sport_label(sport)),
        "family": family,
        "metric": {
            "name": metric_name,
            "value": _safe_float(metric_value),
            "unit": metric_unit,
            "display": _record_metric_display(metric_value, metric_unit),
        },
        "comparison": comparison,
        "axis_direction": axis_direction,
        "improvement": _record_improvement_view(row.get("improvement"), metric_unit),
        "event_date": event_date,
        "display_date": display_date,
        "year": year,
        "month": month,
        "source_mode": str(row.get("source_mode") or "activity_total"),
        "source_mode_label": _pb_source_mode_label(row.get("source_mode")),
        "scope": _record_scope_view(row),
        "range": _record_range_view(row),
        "quality": quality,
        "status": str(row.get("status") or "active"),
        "catalog_state": str(row.get("catalog_state") or (definition.availability_state if definition else "available")),
        "resolver_version": str(row.get("resolver_version") or ""),
        "rule_version": str(row.get("rule_version") or ""),
        "detail_link": {
            "activity_id": activity_id,
            "source": "career",
            "record_id": record_id,
        },
    }


def _records_api_safe(data: Any) -> Any:
    forbidden_keys = {item.lower() for item in RECORDS_API_FORBIDDEN_TEXT if item and not any(sep in item for sep in ("/", "\\", "://")) and " " not in item}

    def _walk(value: Any, path: str = "records_api") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                clean_key = str(key or "").strip()
                normalized_key = clean_key.lower()
                if normalized_key in forbidden_keys:
                    raise ValueError(f"unsafe Records API payload key {path}.{clean_key}")
                _walk(child, f"{path}.{clean_key}" if clean_key else path)
            return
        if isinstance(value, list):
            for index, child in enumerate(value):
                _walk(child, f"{path}[{index}]")
            return
        if isinstance(value, str):
            lowered = value.lower()
            for forbidden in ("/users/", "\\users\\", "file://", "sqlite_master", "create table"):
                if forbidden in lowered:
                    raise ValueError(f"unsafe Records API payload value at {path}")

    _walk(data)
    return data


def _career_record_rows(conn: sqlite3.Connection, filters: dict[str, Any]) -> list[dict[str, Any]]:
    where_parts = []
    params: list[Any] = []
    status = filters.get("status")
    if status != "all":
        where_parts.append("status = ?")
        params.append(str(status or "active"))
    if filters.get("sport") != "all":
        where_parts.append("sport = ?")
        params.append(filters["sport"])
    if filters.get("record_key") != "all":
        where_parts.append("(record_key = ? OR pb_type = ?)")
        params.extend([filters["record_key"], filters["record_key"]])
    if filters.get("family") != "all":
        where_parts.append("record_family = ?")
        params.append(filters["family"])
    if filters.get("scope_hash") != "all":
        where_parts.append("scope_hash = ?")
        params.append(filters["scope_hash"])
    if filters.get("year") is not None:
        where_parts.append("substr(event_date, 1, 4) = ?")
        params.append(str(filters["year"]))
    cursor = conn.execute(
        f"""
        SELECT id, activity_id, sport, pb_type, value, value_unit, improvement,
               event_date, confidence, source, status, display_metadata_json,
               evidence_key, source_mode, sport_scope, previous_record_id,
               resolver_version, record_key, record_family, scope_json, scope_key,
               scope_hash, range_json, quality_json, metric_value_num, metric_name,
               catalog_state, rule_version
        FROM career_pb_records
        WHERE {' AND '.join(where_parts) if where_parts else '1=1'}
        ORDER BY event_date DESC, record_key ASC, scope_key ASC, id DESC
        """,
        tuple(params),
    )
    return _rows_to_dicts(cursor)


def _summarize_career_records(records: list[dict[str, Any]], candidate_count: int = 0) -> dict[str, Any]:
    by_sport: dict[str, int] = {}
    by_family: dict[str, int] = {}
    by_record_key: dict[str, int] = {}
    active_count = 0
    validation_required_count = 0
    for record in records:
        _increment_counter(by_sport, record.get("sport"))
        _increment_counter(by_family, record.get("family"))
        _increment_counter(by_record_key, record.get("record_key"))
        if record.get("status") == "active":
            active_count += 1
        if record.get("catalog_state") == "validation_required":
            validation_required_count += 1
    return {
        "total": len(records),
        "active_count": active_count,
        "candidate_count": candidate_count,
        "validation_required_count": validation_required_count,
        "by_sport": by_sport,
        "by_family": by_family,
        "by_record_key": by_record_key,
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
    card_metrics = race.get("card_metrics") if isinstance(race.get("card_metrics"), list) else []
    result_value = next(
        (
            str(metric.get("value") or "")
            for metric in card_metrics
            if isinstance(metric, dict)
            and str(metric.get("label") or "") in {"成绩", "时间"}
            and str(metric.get("value") or "")
        ),
        "",
    )
    return {
        "id": race["id"],
        "type": "race",
        "subtype": event_type,
        "activity_id": activity_id,
        "title": race["name"],
        "badge": event_type,
        "value": result_value,
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
        "pb_record": "纪录候选",
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


def _build_race_banner_photo_item(row: dict[str, Any]) -> dict[str, Any] | None:
    metadata = _sanitize_public_metadata(_json_loads_object(row.get("metadata_json")))
    activity_id = str(row.get("activity_id") or "").strip()
    race_id = str(row.get("race_id") or "").strip()
    if not activity_id and not race_id:
        return None
    title = str(
        row.get("title")
        or metadata.get("title")
        or CAREER_BANNER_PHOTO_TITLE
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
        "type": "photo",
        "title": title or CAREER_BANNER_PHOTO_TITLE,
        "date": event_date,
        "thumbnail_url": "",
        "has_media": bool(storage_ref),
    }
    if storage_ref:
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
    city_count = len(bucket.get("cities") or set())
    if activity_count:
        distance_text = f"，累计 {total_distance_km:.1f} km".replace(".0 km", " km") if total_distance_km else ""
        season_summary = (
            f"{year} 年共完成 {activity_count} 次活动{distance_text}，"
            f"沉淀 {race_count} 场赛事、{pb_count} 项 PB 和 {achievement_count} 项成就。"
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


def _sanitize_snapshot_record_refresh(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row.get("id") or ""),
        "record_id": str(row.get("record_id") or ""),
        "activity_id": str(row.get("activity_id") or ""),
        "pb_type": str(row.get("pb_type") or ""),
        "event_type": str(row.get("event_type") or ""),
        "event_at": str(row.get("event_at") or ""),
        "resolver_version": str(row.get("resolver_version") or ""),
        "source": str(row.get("source") or ""),
    }


RECORDS_SNAPSHOT_FORMAL_REFRESH_EVENT_TYPES = {"activated", "activated_from_rebuild", "user_confirmed"}
RECORDS_SNAPSHOT_CURVE_TYPES = (
    "cycling_power_duration_curve",
    "trail_pace_curve",
    "trail_gap_curve",
    "pool_swim_pace_curve",
)
RECORDS_SNAPSHOT_TREND_CURVE_TYPES = (
    "cycling_power_duration_curve",
    "trail_pace_curve",
    "trail_gap_curve",
)
RECORDS_SNAPSHOT_MODEL_ESTIMATES = ("eFTP", "CP", "W'", "MAP", "PMax", "GAP", "NGP")


def _records_snapshot_formal_record_item(record: dict[str, Any]) -> dict[str, Any]:
    metric = record.get("metric") if isinstance(record.get("metric"), dict) else {}
    scope = record.get("scope") if isinstance(record.get("scope"), dict) else {}
    return {
        "id": str(record.get("id") or ""),
        "activity_id": str(record.get("activity_id") or ""),
        "record_key": str(record.get("record_key") or record.get("pb_type") or ""),
        "sport": str(record.get("sport") or ""),
        "family": str(record.get("family") or ""),
        "status": str(record.get("status") or ""),
        "catalog_state": str(record.get("catalog_state") or ""),
        "source_mode": str(record.get("source_mode") or ""),
        "event_date": str(record.get("event_date") or ""),
        "metric": {
            "name": str(metric.get("name") or ""),
            "value": metric.get("value"),
            "unit": str(metric.get("unit") or ""),
            "display": str(metric.get("display") or ""),
        },
        "scope": {
            "scope_key": str(scope.get("scope_key") or ""),
            "scope_hash": str(scope.get("scope_hash") or ""),
            "labels": _records_snapshot_string_list(scope.get("labels"), limit=4),
        },
    }


def _records_snapshot_string_list(value: Any, *, limit: int = 4) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value[:limit]]
    if value in (None, ""):
        return []
    return [str(value)]


def _records_snapshot_legacy_current_records(current_records: list[dict[str, Any]], *, limit: int = 6) -> list[dict[str, Any]]:
    safe_records: list[dict[str, Any]] = []
    model_tokens = {"eftp", "cp", "wprime", "w_prime", "map", "pmax", "gap", "ngp", "model"}
    for record in current_records:
        if not isinstance(record, dict):
            continue
        record_key = str(record.get("record_key") or record.get("pb_type") or "").lower().replace("'", "")
        family = str(record.get("family") or record.get("record_family") or "").lower()
        catalog_state = str(record.get("catalog_state") or "").lower()
        source = str(record.get("source") or "").lower()
        if family in {"analysis_curve", "model_estimate"}:
            continue
        if catalog_state in {"analysis_only", "model_only", "unavailable"}:
            continue
        if source == "model":
            continue
        if any(token in record_key for token in model_tokens):
            continue
        safe_records.append(_sanitize_snapshot_pb(record))
        if len(safe_records) >= max(int(limit), 1):
            break
    return safe_records


def _records_snapshot_formal_records(conn: sqlite3.Connection, *, limit: int = 8) -> list[dict[str, Any]]:
    if not _table_exists(conn, "career_pb_records"):
        return []
    rows = _career_record_rows(
        conn,
        {
            "sport": "all",
            "record_key": "all",
            "family": "all",
            "scope_hash": "all",
            "status": "all",
            "year": None,
        },
    )
    records: list[dict[str, Any]] = []
    for row in rows:
        record = _build_career_record_view(row)
        status = str(record.get("status") or "")
        family = str(record.get("family") or "")
        catalog_state = str(record.get("catalog_state") or "")
        if status not in {"active", "superseded"}:
            continue
        if catalog_state in {"analysis_only", "model_only", "unavailable"}:
            continue
        if family in {"analysis_curve", "model_estimate"}:
            continue
        records.append(_records_snapshot_formal_record_item(record))
        if len(records) >= max(int(limit), 1):
            break
    return records


def _empty_records_snapshot_curve_item(curve_type: str) -> dict[str, Any]:
    return {
        "curve_type": curve_type,
        "sport": "",
        "source_mode": "",
        "state": "unavailable",
        "sample_count": 0,
        "algorithm_versions": [],
        "latest_generated_at": "",
        "source": "career_record_curve_cache",
        "kind": "analysis",
        "creates_formal_record": False,
    }


def _records_snapshot_curve_availability(conn: sqlite3.Connection) -> dict[str, Any]:
    by_curve_type = {
        curve_type: _empty_records_snapshot_curve_item(curve_type)
        for curve_type in RECORDS_SNAPSHOT_CURVE_TYPES
    }
    if _table_exists(conn, "career_record_curve_cache"):
        placeholders = ", ".join("?" for _ in RECORDS_SNAPSHOT_CURVE_TYPES)
        rows = _rows_to_dicts(
            conn.execute(
                f"""
                SELECT curve_type,
                       sport,
                       source_mode,
                       algorithm_version,
                       COUNT(*) AS sample_count,
                       MAX(generated_at) AS latest_generated_at
                FROM career_record_curve_cache
                WHERE invalidated_at IS NULL
                  AND curve_type IN ({placeholders})
                GROUP BY curve_type, sport, source_mode, algorithm_version
                ORDER BY curve_type ASC, latest_generated_at DESC
                """,
                tuple(RECORDS_SNAPSHOT_CURVE_TYPES),
            )
        )
        for row in rows:
            curve_type = str(row.get("curve_type") or "")
            if curve_type not in by_curve_type:
                continue
            item = by_curve_type[curve_type]
            count = int(row.get("sample_count") or 0)
            algorithm_version = str(row.get("algorithm_version") or "")
            item["sport"] = item["sport"] or str(row.get("sport") or "")
            item["source_mode"] = item["source_mode"] or str(row.get("source_mode") or "")
            item["sample_count"] = int(item.get("sample_count") or 0) + count
            if algorithm_version and algorithm_version not in item["algorithm_versions"]:
                item["algorithm_versions"].append(algorithm_version)
            latest = str(row.get("latest_generated_at") or "")
            if latest and latest > str(item.get("latest_generated_at") or ""):
                item["latest_generated_at"] = latest
    for item in by_curve_type.values():
        sample_count = int(item.get("sample_count") or 0)
        item["state"] = "available" if sample_count > 0 else "unavailable"
        item["algorithm_versions"] = sorted(str(version) for version in item.get("algorithm_versions") or [])
    available = [item for item in by_curve_type.values() if item["state"] == "available"]
    unavailable = [item["curve_type"] for item in by_curve_type.values() if item["state"] != "available"]
    return {
        "source": "career_record_curve_cache",
        "kind": "analysis",
        "available_count": len(available),
        "unavailable_count": len(unavailable),
        "by_curve_type": by_curve_type,
        "degraded_curve_types": unavailable,
        "boundary": "curve_cache_is_analysis_only_not_formal_record",
    }


def _records_snapshot_trend_curve_inputs(curve_availability: dict[str, Any]) -> list[dict[str, Any]]:
    by_curve_type = curve_availability.get("by_curve_type") if isinstance(curve_availability.get("by_curve_type"), dict) else {}
    inputs: list[dict[str, Any]] = []
    for curve_type in RECORDS_SNAPSHOT_TREND_CURVE_TYPES:
        item = by_curve_type.get(curve_type) if isinstance(by_curve_type.get(curve_type), dict) else _empty_records_snapshot_curve_item(curve_type)
        inputs.append(
            {
                "curve_type": curve_type,
                "sport": str(item.get("sport") or ""),
                "source": "career_record_curve_cache",
                "kind": "analysis",
                "state": str(item.get("state") or "unavailable"),
                "sample_count": int(item.get("sample_count") or 0),
                "algorithm_versions": [str(version) for version in (item.get("algorithm_versions") or [])],
                "creates_formal_record": False,
            }
        )
    return inputs


def _sanitize_records_snapshot_formal_record(item: dict[str, Any]) -> dict[str, Any]:
    metric = item.get("metric") if isinstance(item.get("metric"), dict) else {}
    scope = item.get("scope") if isinstance(item.get("scope"), dict) else {}
    return {
        "id": str(item.get("id") or ""),
        "activity_id": str(item.get("activity_id") or ""),
        "record_key": str(item.get("record_key") or ""),
        "sport": str(item.get("sport") or ""),
        "family": str(item.get("family") or ""),
        "status": str(item.get("status") or ""),
        "catalog_state": str(item.get("catalog_state") or ""),
        "source_mode": str(item.get("source_mode") or ""),
        "event_date": str(item.get("event_date") or ""),
        "metric": {
            "name": str(metric.get("name") or ""),
            "value": metric.get("value"),
            "unit": str(metric.get("unit") or ""),
            "display": str(metric.get("display") or ""),
        },
        "scope": {
            "scope_key": str(scope.get("scope_key") or ""),
            "scope_hash": str(scope.get("scope_hash") or ""),
            "labels": [str(label) for label in (scope.get("labels") or [])[:4]],
        },
    }


def _sanitize_records_snapshot_curve_item(item: dict[str, Any], *, curve_type: str = "") -> dict[str, Any]:
    clean_curve_type = str(item.get("curve_type") or curve_type or "")
    state = str(item.get("state") or "unavailable")
    if state not in {"available", "unavailable", "insufficient_sample"}:
        state = "unavailable"
    return {
        "curve_type": clean_curve_type,
        "sport": str(item.get("sport") or ""),
        "source_mode": str(item.get("source_mode") or ""),
        "state": state,
        "sample_count": int(item.get("sample_count") or 0),
        "algorithm_versions": _records_snapshot_string_list(item.get("algorithm_versions"), limit=4),
        "latest_generated_at": str(item.get("latest_generated_at") or ""),
        "source": "career_record_curve_cache",
        "kind": "analysis",
        "creates_formal_record": False,
    }


def _sanitize_records_snapshot_curve_availability(value: dict[str, Any] | None) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    raw_by_curve = raw.get("by_curve_type") if isinstance(raw.get("by_curve_type"), dict) else {}
    by_curve_type = {}
    for curve_type in RECORDS_SNAPSHOT_CURVE_TYPES:
        item = raw_by_curve.get(curve_type) if isinstance(raw_by_curve.get(curve_type), dict) else {}
        by_curve_type[curve_type] = _sanitize_records_snapshot_curve_item(item, curve_type=curve_type)
    available_count = sum(1 for item in by_curve_type.values() if item["state"] == "available")
    unavailable = [curve_type for curve_type, item in by_curve_type.items() if item["state"] != "available"]
    return {
        "source": "career_record_curve_cache",
        "kind": "analysis",
        "available_count": int(available_count),
        "unavailable_count": len(unavailable),
        "by_curve_type": by_curve_type,
        "degraded_curve_types": unavailable,
        "boundary": "curve_cache_is_analysis_only_not_formal_record",
    }


def _build_records_snapshot_summary(
    conn: sqlite3.Connection,
    current_records: list[dict[str, Any]],
    *,
    recent_limit: int = 8,
) -> dict[str, Any]:
    candidate_count = _count_rows(
        conn,
        "career_event_candidates",
        "candidate_type = 'pb_record' AND status = 'candidate'",
    )
    event_rows: list[dict[str, Any]] = []
    refresh_event_types = RECORDS_SNAPSHOT_FORMAL_REFRESH_EVENT_TYPES
    if _table_exists(conn, "career_record_events"):
        refresh_placeholders = ", ".join("?" for _ in refresh_event_types)
        event_rows = _rows_to_dicts(
            conn.execute(
                f"""
                SELECT id, record_id, activity_id, pb_type, event_type, event_at,
                       resolver_version, source
                FROM career_record_events
                WHERE event_type IN ({refresh_placeholders})
                ORDER BY event_at DESC, created_at DESC, id DESC
                LIMIT ?
                """,
                (*sorted(refresh_event_types), max(int(recent_limit), 1)),
            )
        )
        count_rows = _rows_to_dicts(
            conn.execute(
                """
                SELECT event_type, pb_type, COUNT(*) AS count
                FROM career_record_events
                GROUP BY event_type, pb_type
                """
            )
        )
    else:
        count_rows = []

    by_event_type: dict[str, int] = {}
    by_pb_type: dict[str, int] = {}
    total_events = 0
    for row in count_rows:
        count = int(row.get("count") or 0)
        total_events += count
        event_type_key = str(row.get("event_type") or "unknown").strip() or "unknown"
        pb_type_key = str(row.get("pb_type") or "unknown").strip() or "unknown"
        by_event_type[event_type_key] = int(by_event_type.get(event_type_key) or 0) + count
        by_pb_type[pb_type_key] = int(by_pb_type.get(pb_type_key) or 0) + count

    refresh_event_count = sum(
        int(row.get("count") or 0)
        for row in count_rows
        if str(row.get("event_type") or "") in refresh_event_types
    )
    latest_event_at = str(event_rows[0].get("event_at") or "") if event_rows else ""
    formal_records = _records_snapshot_formal_records(conn)
    curve_availability = _records_snapshot_curve_availability(conn)
    return {
        "current_records": _records_snapshot_legacy_current_records(current_records, limit=6),
        "formal_records": formal_records,
        "recent_refreshes": [_sanitize_snapshot_record_refresh(row) for row in event_rows],
        "candidate_count": int(candidate_count),
        "evolution_summary": {
            "total_event_count": int(total_events),
            "refresh_event_count": int(refresh_event_count),
            "by_event_type": by_event_type,
            "by_pb_type": by_pb_type,
            "latest_event_at": latest_event_at,
        },
        "curve_availability": curve_availability,
        "trend_inputs": {
            "basis": "career_record_events",
            "refresh_frequency_count": int(refresh_event_count),
            "evolution_event_count": int(total_events),
            "interpretation": "frequency_and_curve_availability_only",
            "curve_inputs": _records_snapshot_trend_curve_inputs(curve_availability),
            "model_boundary": {
                "model_estimates_create_records": False,
                "candidate_evidence_exposed": False,
                "formal_record_refresh_event_types": sorted(refresh_event_types),
                "excluded_estimates": list(RECORDS_SNAPSHOT_MODEL_ESTIMATES),
                "boundary": "analysis_and_model_outputs_do_not_refresh_formal_records",
            },
        },
    }


def _sanitize_snapshot_records_summary(value: dict[str, Any] | None) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    evolution = raw.get("evolution_summary") if isinstance(raw.get("evolution_summary"), dict) else {}
    trend_inputs = raw.get("trend_inputs") if isinstance(raw.get("trend_inputs"), dict) else {}
    return {
        "current_records": [
            _sanitize_snapshot_pb(item)
            for item in (raw.get("current_records") or [])
            if isinstance(item, dict)
        ][:6],
        "formal_records": [
            _sanitize_records_snapshot_formal_record(item)
            for item in (raw.get("formal_records") or [])
            if isinstance(item, dict)
        ][:8],
        "recent_refreshes": [
            _sanitize_snapshot_record_refresh(item)
            for item in (raw.get("recent_refreshes") or [])
            if isinstance(item, dict)
        ][:8],
        "candidate_count": int(raw.get("candidate_count") or 0),
        "evolution_summary": {
            "total_event_count": int(evolution.get("total_event_count") or 0),
            "refresh_event_count": int(evolution.get("refresh_event_count") or 0),
            "by_event_type": {
                str(key): int(value or 0)
                for key, value in dict(evolution.get("by_event_type") or {}).items()
            },
            "by_pb_type": {
                str(key): int(value or 0)
                for key, value in dict(evolution.get("by_pb_type") or {}).items()
            },
            "latest_event_at": str(evolution.get("latest_event_at") or ""),
        },
        "curve_availability": _sanitize_records_snapshot_curve_availability(
            raw.get("curve_availability") if isinstance(raw.get("curve_availability"), dict) else None
        ),
        "trend_inputs": {
            "basis": str(trend_inputs.get("basis") or "career_record_events"),
            "refresh_frequency_count": int(trend_inputs.get("refresh_frequency_count") or 0),
            "evolution_event_count": int(trend_inputs.get("evolution_event_count") or 0),
            "interpretation": "frequency_and_curve_availability_only",
            "curve_inputs": _records_snapshot_trend_curve_inputs(
                _sanitize_records_snapshot_curve_availability(
                    raw.get("curve_availability") if isinstance(raw.get("curve_availability"), dict) else None
                )
            ),
            "model_boundary": {
                "model_estimates_create_records": False,
                "candidate_evidence_exposed": False,
                "formal_record_refresh_event_types": sorted(RECORDS_SNAPSHOT_FORMAL_REFRESH_EVENT_TYPES),
                "excluded_estimates": list(RECORDS_SNAPSHOT_MODEL_ESTIMATES),
                "boundary": "analysis_and_model_outputs_do_not_refresh_formal_records",
            },
        },
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


def _career_year_snapshot_has_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).strip().lower() in CAREER_YEAR_SNAPSHOT_FORBIDDEN_KEYS:
                return True
            if _career_year_snapshot_has_forbidden_key(child):
                return True
    elif isinstance(value, list):
        return any(_career_year_snapshot_has_forbidden_key(child) for child in value)
    elif isinstance(value, str):
        lowered = value.lower()
        if "/users/" in lowered or "\\users\\" in lowered or "file://" in lowered:
            return True
    return False


def _career_ai_insight_content_has_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).strip().lower() in CAREER_AI_INSIGHT_CONTENT_FORBIDDEN_KEYS:
                return True
            if _career_ai_insight_content_has_forbidden_key(child):
                return True
    elif isinstance(value, list):
        return any(_career_ai_insight_content_has_forbidden_key(child) for child in value)
    elif isinstance(value, str):
        lowered = value.lower()
        if "/users/" in lowered or "\\users\\" in lowered or "file://" in lowered:
            return True
    return False


def _validate_career_year(year: Any) -> int:
    try:
        clean_year = int(year)
    except (TypeError, ValueError):
        raise ValueError("年度必须是有效整数") from None
    if clean_year < CAREER_YEAR_MIN or clean_year > CAREER_YEAR_MAX:
        raise ValueError(f"年度必须在 {CAREER_YEAR_MIN}-{CAREER_YEAR_MAX} 之间")
    return clean_year


def _career_year_as_of_date(as_of_date: Any = None) -> str:
    if as_of_date is None or as_of_date == "":
        return datetime.now(timezone.utc).date().isoformat()
    clean = str(as_of_date).strip()
    try:
        return datetime.fromisoformat(clean[:10]).date().isoformat()
    except ValueError:
        raise ValueError("as_of_date 必须是 YYYY-MM-DD 日期") from None


def _career_year_period(year: int, as_of_date: Any = None, data_through: Any = None) -> dict[str, Any]:
    as_of = _career_year_as_of_date(as_of_date)
    start_date = f"{year:04d}-01-01"
    end_date = f"{year:04d}-12-31"
    latest_activity_date = str(data_through or "").strip() or None
    return {
        "start_date": start_date,
        "end_date": end_date,
        "as_of_date": as_of,
        "data_through": latest_activity_date,
        "is_partial_year": start_date <= as_of <= end_date and as_of < end_date,
        "latest_activity_date": latest_activity_date,
    }


def _empty_career_year_summary() -> dict[str, Any]:
    return {
        "activity_count": 0,
        "total_distance_km": 0.0,
        "total_duration_seconds": 0,
        "race_count": 0,
        "pb_count": 0,
        "achievement_count": 0,
        "covered_city_count": 0,
    }


def _empty_career_year_month_digest() -> list[dict[str, Any]]:
    return [
        {
            "month": month,
            "activity_count": 0,
            "distance_km": 0.0,
            "duration_seconds": 0,
            "primary_sport": "",
        }
        for month in range(1, 13)
    ]


def _empty_career_year_comparison(year: int) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "reason": "not_computed",
        "comparison_year": year - 1,
        "period_mode": "none",
        "activity_count_delta": None,
        "distance_km_delta": None,
        "duration_seconds_delta": None,
        "race_count_delta": None,
        "pb_count_delta": None,
    }


def _career_year_snapshot_activity_rows(
    conn: sqlite3.Connection,
    year: int,
    end_date: str | None = None,
    activity_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    source_rows = activity_rows if activity_rows is not None else _overview_activity_rows(conn)
    for row in source_rows:
        activity_date = _overview_activity_date(row)
        if _safe_activity_year(activity_date) == year:
            if end_date and activity_date[:10] > end_date:
                continue
            rows.append(row)
    rows.sort(key=lambda item: (str(_overview_activity_date(item)), str(item.get("id") or "")))
    return rows


def _career_year_primary_sport(bucket: dict[str, dict[str, Any]]) -> str:
    candidates = [
        (
            str(sport),
            int(values.get("activity_count") or 0),
            float(values.get("distance_km") or 0.0),
        )
        for sport, values in bucket.items()
        if int(values.get("activity_count") or 0) > 0
    ]
    if not candidates:
        return ""
    candidates.sort(key=lambda item: (-item[1], -item[2], item[0]))
    return candidates[0][0]


def _career_year_ascent_m(row: dict[str, Any]) -> float | None:
    for key in ("total_ascent", "ascent", "elev_gain", "gain_m"):
        value = _safe_float(row.get(key))
        if value is not None and value > 0:
            return value
    return None


def _career_year_max_altitude_m(row: dict[str, Any]) -> float | None:
    value = _safe_float(row.get("max_alt_m"))
    return value if value is not None and value > 0 else None


def _career_year_city_culture_hint(city: Any) -> str:
    clean = " ".join(str(city or "").split()).strip()
    if not clean:
        return ""
    if clean in CAREER_YEAR_CITY_CULTURE_HINTS:
        return CAREER_YEAR_CITY_CULTURE_HINTS[clean]
    compact = clean.replace("市", "")
    return CAREER_YEAR_CITY_CULTURE_HINTS.get(compact, "")


def _career_year_safe_moment_text(value: Any, max_len: int = 80) -> str:
    return " ".join(str(value or "").split())[:max_len]


def _build_career_year_activity_facts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary = _empty_career_year_summary()
    sport_buckets: dict[str, dict[str, Any]] = {}
    month_buckets: dict[int, dict[str, Any]] = {
        month: {
            "activity_count": 0,
            "distance_km": 0.0,
            "duration_seconds": 0,
            "sports": {},
        }
        for month in range(1, 13)
    }
    cities: set[str] = set()
    city_buckets: dict[str, dict[str, Any]] = {}
    activity_candidates: list[dict[str, Any]] = []
    total_ascent_m = 0.0
    latest_activity_date: str | None = None

    for row in rows:
        activity_date = _overview_activity_date(row)
        if len(activity_date) < 10:
            continue
        try:
            month = int(activity_date[5:7])
        except ValueError:
            continue
        if month < 1 or month > 12:
            continue

        sport = _overview_activity_sport(row)
        distance_km = _activity_distance_km(row) or 0.0
        duration_seconds = _activity_duration_sec(row) or 0
        city = _overview_activity_city(row)
        ascent_m = _career_year_ascent_m(row) or 0.0
        max_altitude_m = _career_year_max_altitude_m(row)
        activity_id = str(row.get("id") or "").strip()

        summary["activity_count"] = int(summary["activity_count"]) + 1
        summary["total_distance_km"] = float(summary["total_distance_km"]) + float(distance_km)
        summary["total_duration_seconds"] = int(summary["total_duration_seconds"]) + int(duration_seconds)
        total_ascent_m += float(ascent_m)
        if city:
            cities.add(city)
            city_bucket = city_buckets.setdefault(
                city,
                {
                    "city": city,
                    "activity_count": 0,
                    "first_date": activity_date,
                    "latest_date": activity_date,
                    "representative_activity_id": activity_id,
                    "culture_hint": _career_year_city_culture_hint(city),
                },
            )
            city_bucket["activity_count"] = int(city_bucket["activity_count"]) + 1
            city_bucket["first_date"] = min(str(city_bucket["first_date"]), activity_date)
            city_bucket["latest_date"] = max(str(city_bucket["latest_date"]), activity_date)
            if float(distance_km) > float(city_bucket.get("representative_distance_km") or -1):
                city_bucket["representative_activity_id"] = activity_id
                city_bucket["representative_distance_km"] = round(float(distance_km), 1)
        latest_activity_date = max(latest_activity_date or activity_date, activity_date)
        if activity_id:
            activity_candidates.append({
                "activity_id": activity_id,
                "date": activity_date,
                "sport": sport,
                "sport_label": _overview_sport_label(sport),
                "distance_km": round(float(distance_km), 1),
                "duration_seconds": int(duration_seconds),
                "ascent_m": round(float(ascent_m), 1) if ascent_m > 0 else None,
                "max_altitude_m": round(float(max_altitude_m), 1) if max_altitude_m else None,
                "city": city,
            })

        sport_bucket = sport_buckets.setdefault(
            sport,
            {
                "sport": sport,
                "sport_label": _overview_sport_label(sport),
                "activity_count": 0,
                "distance_km": 0.0,
                "duration_seconds": 0,
            },
        )
        sport_bucket["activity_count"] = int(sport_bucket["activity_count"]) + 1
        sport_bucket["distance_km"] = float(sport_bucket["distance_km"]) + float(distance_km)
        sport_bucket["duration_seconds"] = int(sport_bucket["duration_seconds"]) + int(duration_seconds)

        month_bucket = month_buckets[month]
        month_bucket["activity_count"] = int(month_bucket["activity_count"]) + 1
        month_bucket["distance_km"] = float(month_bucket["distance_km"]) + float(distance_km)
        month_bucket["duration_seconds"] = int(month_bucket["duration_seconds"]) + int(duration_seconds)
        month_sports = month_bucket["sports"]
        month_sport_bucket = month_sports.setdefault(sport, {"activity_count": 0, "distance_km": 0.0})
        month_sport_bucket["activity_count"] = int(month_sport_bucket["activity_count"]) + 1
        month_sport_bucket["distance_km"] = float(month_sport_bucket["distance_km"]) + float(distance_km)

    summary["total_distance_km"] = round(float(summary["total_distance_km"]), 1)
    summary["total_duration_seconds"] = int(summary["total_duration_seconds"])
    summary["covered_city_count"] = len(cities)

    sport_breakdown = []
    for sport in sorted(sport_buckets):
        bucket = sport_buckets[sport]
        sport_breakdown.append({
            "sport": str(bucket["sport"]),
            "sport_label": str(bucket["sport_label"]),
            "activity_count": int(bucket["activity_count"]),
            "distance_km": round(float(bucket["distance_km"]), 1),
            "duration_seconds": int(bucket["duration_seconds"]),
        })

    month_digest = []
    for month in range(1, 13):
        bucket = month_buckets[month]
        month_digest.append({
            "month": month,
            "activity_count": int(bucket["activity_count"]),
            "distance_km": round(float(bucket["distance_km"]), 1),
            "duration_seconds": int(bucket["duration_seconds"]),
            "primary_sport": _career_year_primary_sport(bucket["sports"]),
        })

    city_moments = [
        {
            "city": str(bucket["city"]),
            "activity_count": int(bucket["activity_count"]),
            "first_date": str(bucket["first_date"]),
            "latest_date": str(bucket["latest_date"]),
            "representative_activity_id": str(bucket.get("representative_activity_id") or ""),
            "culture_hint": str(bucket.get("culture_hint") or ""),
        }
        for bucket in sorted(
            city_buckets.values(),
            key=lambda item: (-int(item.get("activity_count") or 0), str(item.get("first_date") or ""), str(item.get("city") or "")),
        )
    ][:5]

    highlight_moments = _career_year_activity_highlight_moments(activity_candidates, total_ascent_m)

    return {
        "summary": summary,
        "sport_breakdown": sport_breakdown,
        "month_digest": month_digest,
        "highlight_moments": highlight_moments,
        "city_moments": city_moments,
        "latest_activity_date": latest_activity_date,
    }


def _career_year_activity_highlight_moments(
    activity_candidates: list[dict[str, Any]],
    total_ascent_m: float,
) -> list[dict[str, Any]]:
    moments: list[dict[str, Any]] = []

    def add(kind: str, title: str, item: dict[str, Any], value: str, rank: int) -> None:
        activity_id = str(item.get("activity_id") or "")
        if not activity_id:
            return
        moments.append({
            "id": f"{kind}:{activity_id}",
            "activity_id": activity_id,
            "type": kind,
            "title": title,
            "date": str(item.get("date") or ""),
            "value": value,
            "rank": rank,
        })

    if activity_candidates:
        longest = sorted(
            activity_candidates,
            key=lambda item: (-float(item.get("distance_km") or 0.0), str(item.get("date") or ""), str(item.get("activity_id") or "")),
        )[0]
        if float(longest.get("distance_km") or 0.0) > 0:
            add("longest_distance", "年度最长距离", longest, f"{float(longest.get('distance_km') or 0.0):g} km", 30)

        longest_duration = sorted(
            activity_candidates,
            key=lambda item: (-int(item.get("duration_seconds") or 0), str(item.get("date") or ""), str(item.get("activity_id") or "")),
        )[0]
        if int(longest_duration.get("duration_seconds") or 0) > 0:
            add("longest_duration", "年度最长运动时间", longest_duration, f"{int(longest_duration.get('duration_seconds') or 0)} 秒", 40)

        altitude_items = [item for item in activity_candidates if item.get("max_altitude_m") is not None]
        if altitude_items:
            highest = sorted(
                altitude_items,
                key=lambda item: (-float(item.get("max_altitude_m") or 0.0), str(item.get("date") or ""), str(item.get("activity_id") or "")),
            )[0]
            altitude = float(highest.get("max_altitude_m") or 0.0)
            if altitude >= 5000:
                add("max_altitude_5000m", "单次活动海拔突破 5000 米", highest, f"{altitude:g} m", 20)
            elif altitude > 0:
                add("max_altitude", "年度最高海拔活动", highest, f"{altitude:g} m", 45)

        if total_ascent_m >= 5000:
            threshold = 50000 if total_ascent_m >= 50000 else 20000 if total_ascent_m >= 20000 else 10000 if total_ascent_m >= 10000 else 5000
            latest = sorted(activity_candidates, key=lambda item: (str(item.get("date") or ""), str(item.get("activity_id") or "")))[-1]
            add("annual_ascent_milestone", f"年度累计爬升突破 {threshold} 米", latest, f"{round(total_ascent_m):g} m", 35)

    unique: dict[str, dict[str, Any]] = {}
    for moment in moments:
        unique.setdefault(str(moment.get("id") or ""), moment)
    return sorted(
        unique.values(),
        key=lambda item: (int(item.get("rank") or 99), str(item.get("date") or ""), str(item.get("id") or "")),
    )[:5]


def _career_year_evidence_id(kind: str, raw_id: Any) -> str:
    clean = str(raw_id or "").strip()
    if clean.startswith(f"{kind}:"):
        return clean
    return f"{kind}:{clean}" if clean else ""


def _career_year_safe_evidence_value(*values: Any) -> str:
    parts = [" ".join(str(value or "").split()) for value in values]
    return " ".join(part for part in parts if part)[:80]


def _career_year_resolver_evidence(
    conn: sqlite3.Connection,
    year: int,
    valid_activity_ids: set[str],
) -> list[dict[str, Any]]:
    evidence_by_id: dict[str, dict[str, Any]] = {}

    def add(item: dict[str, Any]) -> None:
        activity_id = str(item.get("activity_id") or "").strip()
        evidence_id = str(item.get("evidence_id") or "").strip()
        event_date = str(item.get("date") or "").strip()[:10]
        if not evidence_id or not activity_id or activity_id not in valid_activity_ids:
            return
        if _safe_activity_year(event_date) != year:
            return
        evidence_by_id[evidence_id] = {
            "evidence_id": evidence_id,
            "activity_id": activity_id,
            "type": str(item.get("type") or "").strip(),
            "title": " ".join(str(item.get("title") or "").split())[:80],
            "date": event_date,
            "value": _career_year_safe_evidence_value(item.get("value")),
        }

    if _table_exists(conn, "career_race_events"):
        cursor = conn.execute(
            """
            SELECT id, activity_id, name, event_type, event_date, status
            FROM career_race_events
            WHERE status = 'active'
            """
        )
        for row in _rows_to_dicts(cursor):
            add({
                "evidence_id": _career_year_evidence_id("race", row.get("id")),
                "activity_id": row.get("activity_id"),
                "type": "race",
                "title": row.get("name") or row.get("event_type") or "赛事",
                "date": row.get("event_date"),
                "value": row.get("event_type"),
            })

    if _table_exists(conn, "career_pb_records"):
        cursor = conn.execute(
            """
            SELECT id, activity_id, sport, pb_type, value, value_unit, event_date, status
            FROM career_pb_records
            WHERE status = 'active'
            """
        )
        for row in _rows_to_dicts(cursor):
            add({
                "evidence_id": _career_year_evidence_id("pb", row.get("id")),
                "activity_id": row.get("activity_id"),
                "type": "pb",
                "title": _pb_type_label(row.get("pb_type")),
                "date": row.get("event_date"),
                "value": _career_year_safe_evidence_value(row.get("value"), row.get("value_unit")),
            })

    if _table_exists(conn, "career_achievement_events"):
        cursor = conn.execute(
            """
            SELECT id, activity_id, achievement_type, title, event_date, score, status
            FROM career_achievement_events
            WHERE status = 'active'
            """
        )
        for row in _rows_to_dicts(cursor):
            add({
                "evidence_id": _career_year_evidence_id("achievement", row.get("id")),
                "activity_id": row.get("activity_id"),
                "type": "achievement",
                "title": row.get("title") or _achievement_type_label(row.get("achievement_type")),
                "date": row.get("event_date"),
                "value": row.get("score"),
            })

    return sorted(
        evidence_by_id.values(),
        key=lambda item: (
            str(item.get("date") or ""),
            str(item.get("type") or ""),
            str(item.get("evidence_id") or ""),
        ),
    )


def _career_year_latest_fact_date(activity_latest: Any, evidence_catalog: list[dict[str, Any]]) -> str | None:
    dates = [str(activity_latest or "").strip()]
    dates.extend(str(item.get("date") or "").strip()[:10] for item in evidence_catalog)
    valid_dates = [date for date in dates if len(date) >= 10 and _safe_activity_year(date) is not None]
    return max(valid_dates) if valid_dates else None


def _career_year_comparison_end_date(comparison_year: int, data_through: str) -> str:
    month_day = str(data_through or "")[5:10]
    if month_day == "02-29" and not calendar.isleap(comparison_year):
        month_day = "02-28"
    return f"{comparison_year:04d}-{month_day}"


def _career_year_evidence_counts(evidence_catalog: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "race_count": sum(1 for item in evidence_catalog if item.get("type") == "race"),
        "pb_count": sum(1 for item in evidence_catalog if item.get("type") == "pb"),
        "achievement_count": sum(1 for item in evidence_catalog if item.get("type") == "achievement"),
    }


def _career_year_highlight_moments(
    activity_highlights: list[dict[str, Any]],
    evidence_catalog: list[dict[str, Any]],
    city_moments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    moments: list[dict[str, Any]] = []
    evidence_rank = {"race": 10, "pb": 15, "achievement": 25, "milestone": 25}
    for item in evidence_catalog:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "")
        if item_type not in evidence_rank:
            continue
        moments.append({
            "id": str(item.get("evidence_id") or ""),
            "activity_id": str(item.get("activity_id") or ""),
            "type": item_type,
            "title": _career_year_safe_moment_text(item.get("title")),
            "date": str(item.get("date") or ""),
            "value": _career_year_safe_moment_text(item.get("value")),
            "rank": evidence_rank[item_type],
        })
    for item in activity_highlights:
        if isinstance(item, dict):
            moments.append(dict(item))
    for city in city_moments[:2]:
        if not isinstance(city, dict):
            continue
        city_name = _career_year_safe_moment_text(city.get("city"), 40)
        activity_id = str(city.get("representative_activity_id") or "")
        if not city_name or not activity_id:
            continue
        value = f"{int(city.get('activity_count') or 0)} 次活动"
        culture_hint = _career_year_safe_moment_text(city.get("culture_hint"), 40)
        if culture_hint:
            value += f" · {culture_hint}"
        moments.append({
            "id": f"city:{city_name}:{activity_id}",
            "activity_id": activity_id,
            "type": "city",
            "title": f"在{city_name}留下运动坐标",
            "date": str(city.get("first_date") or ""),
            "value": value,
            "rank": 50,
        })
    unique: dict[str, dict[str, Any]] = {}
    for moment in moments:
        moment_id = str(moment.get("id") or "").strip()
        activity_id = str(moment.get("activity_id") or "").strip()
        if not moment_id or not activity_id:
            continue
        unique.setdefault(moment_id, {
            "id": moment_id,
            "activity_id": activity_id,
            "type": str(moment.get("type") or ""),
            "title": _career_year_safe_moment_text(moment.get("title")),
            "date": str(moment.get("date") or "")[:10],
            "value": _career_year_safe_moment_text(moment.get("value")),
            "rank": int(moment.get("rank") or 99),
        })
    return sorted(
        unique.values(),
        key=lambda item: (int(item.get("rank") or 99), str(item.get("date") or ""), str(item.get("id") or "")),
    )[:5]


def _career_year_available_comparison(
    current_summary: dict[str, Any],
    previous_summary: dict[str, Any],
    comparison_year: int,
    period_mode: str,
) -> dict[str, Any]:
    return {
        "status": "available",
        "reason": "",
        "comparison_year": comparison_year,
        "period_mode": period_mode,
        "activity_count_delta": int(current_summary.get("activity_count") or 0) - int(previous_summary.get("activity_count") or 0),
        "distance_km_delta": round(float(current_summary.get("total_distance_km") or 0.0) - float(previous_summary.get("total_distance_km") or 0.0), 1),
        "duration_seconds_delta": int(current_summary.get("total_duration_seconds") or 0) - int(previous_summary.get("total_duration_seconds") or 0),
        "race_count_delta": int(current_summary.get("race_count") or 0) - int(previous_summary.get("race_count") or 0),
        "pb_count_delta": int(current_summary.get("pb_count") or 0) - int(previous_summary.get("pb_count") or 0),
    }


def _career_year_unavailable_comparison(year: int, reason: str, period_mode: str = "none") -> dict[str, Any]:
    comparison = _empty_career_year_comparison(year)
    comparison["reason"] = reason
    comparison["period_mode"] = period_mode
    return comparison


def _build_career_year_comparison(
    conn: sqlite3.Connection,
    year: int,
    current_summary: dict[str, Any],
    current_period: dict[str, Any],
    activity_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if int(current_summary.get("activity_count") or 0) <= 0:
        return _career_year_unavailable_comparison(year, "no_current_year_data")

    comparison_year = year - 1
    data_through = str(current_period.get("data_through") or "").strip()
    if current_period.get("is_partial_year") and data_through:
        period_mode = "same_date_range"
        comparison_end_date = _career_year_comparison_end_date(comparison_year, data_through)
    else:
        period_mode = "full_year"
        comparison_end_date = f"{comparison_year:04d}-12-31"

    previous_rows = _career_year_snapshot_activity_rows(
        conn,
        comparison_year,
        end_date=comparison_end_date,
        activity_rows=activity_rows,
    )
    previous_facts = _build_career_year_activity_facts(previous_rows)
    if int(previous_facts["summary"].get("activity_count") or 0) <= 0:
        return _career_year_unavailable_comparison(year, "previous_year_no_data", period_mode=period_mode)

    previous_evidence = _career_year_resolver_evidence(
        conn,
        comparison_year,
        {str(row.get("id") or "").strip() for row in previous_rows if str(row.get("id") or "").strip()},
    )
    previous_summary = dict(previous_facts["summary"])
    previous_summary.update(_career_year_evidence_counts(previous_evidence))
    return _career_year_available_comparison(current_summary, previous_summary, comparison_year, period_mode)


def _career_year_data_quality(summary: dict[str, Any], period: dict[str, Any], comparison: dict[str, Any]) -> dict[str, Any]:
    if int(summary.get("activity_count") or 0) <= 0:
        return {"status": "no_data", "warnings": ["no_activity_data"]}
    warnings: list[str] = []
    if period.get("is_partial_year"):
        warnings.append("partial_year")
    if comparison.get("status") != "available":
        reason = str(comparison.get("reason") or "").strip()
        if reason:
            warnings.append(f"comparison_unavailable:{reason}")
    return {
        "status": "ready" if not warnings else "limited",
        "warnings": warnings,
    }


def _canonicalize_career_year_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _canonicalize_career_year_value(child)
            for key, child in sorted(value.items(), key=lambda item: str(item[0]))
            if str(key) not in CAREER_YEAR_FINGERPRINT_EXCLUDED_KEYS
        }
    if isinstance(value, list):
        return [_canonicalize_career_year_value(child) for child in value]
    if isinstance(value, float):
        rounded = round(value, 6)
        return int(rounded) if rounded.is_integer() else rounded
    return value


def career_year_snapshot_report_source_fields(snapshot: dict[str, Any]) -> dict[str, Any]:
    period = snapshot.get("period") if isinstance(snapshot.get("period"), dict) else {}
    comparison = snapshot.get("comparison") if isinstance(snapshot.get("comparison"), dict) else {}
    return {
        "snapshot_version": snapshot.get("snapshot_version"),
        "scope": snapshot.get("scope"),
        "year": snapshot.get("year"),
        "period": {
            "start_date": period.get("start_date"),
            "end_date": period.get("end_date"),
            "data_through": period.get("data_through"),
            "is_partial_year": period.get("is_partial_year"),
            "latest_activity_date": period.get("latest_activity_date"),
        },
        "summary": snapshot.get("summary") if isinstance(snapshot.get("summary"), dict) else {},
        "sport_breakdown": sorted(
            (snapshot.get("sport_breakdown") or []) if isinstance(snapshot.get("sport_breakdown"), list) else [],
            key=lambda item: str(item.get("sport") or "") if isinstance(item, dict) else "",
        ),
        "month_digest": sorted(
            (snapshot.get("month_digest") or []) if isinstance(snapshot.get("month_digest"), list) else [],
            key=lambda item: int(item.get("month") or 0) if isinstance(item, dict) else 0,
        ),
        "evidence_catalog": sorted(
            (snapshot.get("evidence_catalog") or []) if isinstance(snapshot.get("evidence_catalog"), list) else [],
            key=lambda item: (
                str(item.get("date") or ""),
                str(item.get("type") or ""),
                str(item.get("evidence_id") or ""),
            ) if isinstance(item, dict) else ("", "", ""),
        ),
        "comparison": {
            "status": comparison.get("status"),
            "reason": comparison.get("reason"),
            "comparison_year": comparison.get("comparison_year"),
            "period_mode": comparison.get("period_mode"),
            "activity_count_delta": comparison.get("activity_count_delta"),
            "distance_km_delta": comparison.get("distance_km_delta"),
            "duration_seconds_delta": comparison.get("duration_seconds_delta"),
            "race_count_delta": comparison.get("race_count_delta"),
            "pb_count_delta": comparison.get("pb_count_delta"),
        },
    }


def career_year_snapshot_canonical_json(value: Any) -> str:
    return json.dumps(
        _canonicalize_career_year_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def compute_career_year_source_fingerprint(snapshot: dict[str, Any]) -> str:
    canonical = career_year_snapshot_canonical_json(career_year_snapshot_report_source_fields(snapshot))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _successful_career_year_report(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(report, dict):
        return None
    status = str(report.get("status") or report.get("generation_status") or "success").strip().lower()
    if status not in {"success", "ready", "active"}:
        return None
    fingerprint = str(report.get("source_fingerprint") or "").strip()
    if not fingerprint:
        return None
    return report


def _career_year_snapshot_has_data(snapshot: dict[str, Any] | None) -> bool:
    if not isinstance(snapshot, dict):
        return False
    summary = snapshot.get("summary") if isinstance(snapshot.get("summary"), dict) else {}
    return int(summary.get("activity_count") or 0) > 0


def resolve_career_year_report_state(
    snapshot: dict[str, Any] | None,
    latest_successful_report: dict[str, Any] | None = None,
    runtime: dict[str, Any] | None = None,
    ai_available: bool = True,
) -> dict[str, Any]:
    """Resolve the annual report state from backend facts only."""
    runtime_state = str((runtime or {}).get("state") or "").strip().lower()
    current_fingerprint = str((snapshot or {}).get("source_fingerprint") or "").strip()
    report = _successful_career_year_report(latest_successful_report)
    report_fingerprint = str((report or {}).get("source_fingerprint") or "").strip()
    report_available = report is not None

    if not _career_year_snapshot_has_data(snapshot):
        base_status = "no_data"
    elif not report_available:
        base_status = "not_generated"
    elif report_fingerprint == current_fingerprint:
        base_status = "ready"
    else:
        base_status = "stale"

    status = base_status
    if base_status != "no_data":
        if runtime_state == "generating":
            status = "generating"
        elif runtime_state == "failed":
            status = "failed"
        elif not ai_available:
            status = "ai_unavailable"

    has_source_changes = base_status == "stale"
    can_generate = status == "not_generated"
    can_refresh = status == "stale"
    return {
        "status": status,
        "base_status": base_status,
        "can_generate": can_generate,
        "can_refresh": can_refresh,
        "has_source_changes": has_source_changes,
        "report_available": report_available,
        "display_report": report_available,
        "preserve_report": report_available and status in {"generating", "failed", "ai_unavailable", "stale", "ready"},
        "source_fingerprint": current_fingerprint,
        "report_fingerprint": report_fingerprint,
    }


def _career_year_snapshot_id(year: Any) -> str:
    return f"career_snapshot:year:{_validate_career_year(year)}"


def _strip_career_year_forbidden(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _strip_career_year_forbidden(child)
            for key, child in value.items()
            if str(key).strip().lower() not in CAREER_YEAR_SNAPSHOT_FORBIDDEN_KEYS
        }
    if isinstance(value, list):
        return [_strip_career_year_forbidden(child) for child in value]
    return value


def _sanitize_saved_career_year_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    stripped = _strip_career_year_forbidden(snapshot if isinstance(snapshot, dict) else {})
    cleaned = {
        key: stripped.get(key)
        for key in CAREER_YEAR_SNAPSHOT_TOP_LEVEL_FIELDS
        if key in stripped
    }
    if "source_fingerprint" in cleaned:
        cleaned["source_fingerprint"] = compute_career_year_source_fingerprint(cleaned)
    validate_career_year_snapshot_contract(cleaned)
    return cleaned


def _sanitize_career_year_ai_narrative_numbers(
    text: str,
    year: int,
    *,
    allow_year: bool = False,
    fallback: str = "",
) -> str:
    """Drop AI-authored sentences containing precise numbers; facts render elsewhere."""
    marker = "__CAREER_YEAR__"
    candidate = text.replace(str(year), marker) if allow_year else text
    if not re.search(r"\d", candidate):
        return text
    safe_sentences = [
        sentence
        for sentence in re.split(r"(?<=[。！？!?；;])", candidate)
        if sentence.strip() and not re.search(r"\d", sentence)
    ]
    cleaned = "".join(safe_sentences).replace(marker, str(year)).strip()
    return cleaned or fallback


def _career_year_complete_sentence(text: str, fallback: str = "") -> str:
    clean = str(text or "").strip()
    if not clean:
        return fallback
    if clean[-1] in "。！？.!?":
        return clean
    clean = clean.rstrip("，,、；;：:")
    return (clean or fallback).rstrip("，,、；;：:") + "。"


def save_career_year_snapshot(
    year: Any,
    conn: sqlite3.Connection | None = None,
    as_of_date: Any = None,
) -> dict[str, Any]:
    """Persist one rebuildable Year Snapshot without touching full-career snapshots."""
    clean_year = _validate_career_year(year)
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        ensure_career_schema(db)
        snapshot = build_career_year_snapshot(clean_year, conn=db, as_of_date=as_of_date)
        if _career_year_snapshot_has_forbidden_key(snapshot):
            raise ValueError("Year Snapshot 包含禁止字段")
        now = _utc_now_iso()
        snapshot_id = _career_year_snapshot_id(clean_year)
        db.execute(
            """
            INSERT INTO career_snapshots
                (id, snapshot_type, generated_at, content_json, source_version, created_at)
            VALUES
                (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                snapshot_type = excluded.snapshot_type,
                generated_at = excluded.generated_at,
                content_json = excluded.content_json,
                source_version = excluded.source_version,
                created_at = excluded.created_at
            """,
            (
                snapshot_id,
                CAREER_YEAR_SNAPSHOT_TYPE,
                now,
                _json_dumps(snapshot),
                CAREER_YEAR_SNAPSHOT_VERSION,
                now,
            ),
        )
        if owns_conn:
            db.commit()
        return {
            "snapshot_id": snapshot_id,
            "year": clean_year,
            "saved": True,
            "saved_at": now,
            "source_version": CAREER_YEAR_SNAPSHOT_VERSION,
            "source_fingerprint": snapshot["source_fingerprint"],
            "status": {
                "schema_ready": True,
                "data_ready": True,
                "message": "Year Snapshot 已保存",
            },
        }
    except Exception:
        if owns_conn:
            db.rollback()
        raise
    finally:
        if owns_conn:
            db.close()


def get_career_year_snapshot(
    year: Any,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Return one saved Year Snapshot for backend services without rebuilding it."""
    clean_year = _validate_career_year(year)
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        ensure_career_schema(db)
        row = db.execute(
            """
            SELECT id, generated_at, content_json, source_version, created_at
            FROM career_snapshots
            WHERE id = ?
              AND snapshot_type = ?
            LIMIT 1
            """,
            (_career_year_snapshot_id(clean_year), CAREER_YEAR_SNAPSHOT_TYPE),
        ).fetchone()
        if row is None:
            return {
                "snapshot": None,
                "year": clean_year,
                "status": {
                    "schema_ready": True,
                    "data_ready": False,
                    "message": "暂无 Year Snapshot",
                },
            }
        parsed = _json_loads_object(row[2])
        snapshot = _sanitize_saved_career_year_snapshot(parsed)
        return {
            "snapshot": snapshot,
            "snapshot_id": str(row[0] or _career_year_snapshot_id(clean_year)),
            "year": clean_year,
            "saved_at": str(row[4] or row[1] or ""),
            "source_version": str(row[3] or snapshot.get("snapshot_version") or CAREER_YEAR_SNAPSHOT_VERSION),
            "source_fingerprint": snapshot["source_fingerprint"],
            "status": {
                "schema_ready": True,
                "data_ready": True,
                "message": "Year Snapshot 已保存",
            },
        }
    finally:
        if owns_conn:
            db.close()


def _normalize_career_ai_insight_scope(scope: Any) -> str:
    clean = str(scope or "").strip()
    if not clean:
        raise ValueError("AI Insight scope 不能为空")
    return clean


def _normalize_career_ai_insight_scope_key(scope_key: Any) -> str:
    clean = str(scope_key or "").strip()
    if not clean:
        raise ValueError("AI Insight scope_key 不能为空")
    return clean


def _normalize_career_ai_insight_text(value: Any, field_name: str) -> str:
    clean = str(value or "").strip()
    if not clean:
        raise ValueError(f"{field_name} 不能为空")
    return clean


def _career_ai_insight_id(
    scope: Any,
    scope_key: Any,
    snapshot_fingerprint: Any,
    prompt_version: Any,
    model_id: Any,
) -> str:
    # Cache identity intentionally includes prompt/model. Do not reuse the
    # snapshot fingerprint canonicalizer, which excludes those runtime fields.
    key = json.dumps(
        {
            "scope": _normalize_career_ai_insight_scope(scope),
            "scope_key": _normalize_career_ai_insight_scope_key(scope_key),
            "snapshot_fingerprint": _normalize_career_ai_insight_text(snapshot_fingerprint, "snapshot_fingerprint"),
            "prompt_version": _normalize_career_ai_insight_text(prompt_version, "prompt_version"),
            "model_id": _normalize_career_ai_insight_text(model_id, "model_id"),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"career_ai_insight:{hashlib.sha256(key.encode('utf-8')).hexdigest()}"


def _validate_career_ai_insight_status(status: Any) -> str:
    clean = str(status or "").strip().lower()
    if clean not in CAREER_AI_INSIGHT_STATUSES:
        raise ValueError(f"AI Insight status 必须是 {', '.join(CAREER_AI_INSIGHT_STATUSES)} 之一")
    return clean


def _career_ai_insight_row(row: sqlite3.Row | tuple[Any, ...] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": str(row[0] or ""),
        "scope": str(row[1] or ""),
        "scope_key": str(row[2] or ""),
        "snapshot_fingerprint": str(row[3] or ""),
        "snapshot_version": str(row[4] or ""),
        "prompt_version": str(row[5] or ""),
        "model_id": str(row[6] or ""),
        "content": _json_loads_object(row[7]),
        "generated_at": str(row[8] or ""),
        "created_at": str(row[9] or ""),
        "updated_at": str(row[10] or ""),
        "status": str(row[11] or ""),
    }


def _select_career_ai_insight_columns() -> str:
    return """
        id, scope, scope_key, snapshot_fingerprint, snapshot_version,
        prompt_version, model_id, content_json, generated_at, created_at,
        updated_at, status
    """


def insert_career_ai_insight(
    *,
    scope: Any,
    scope_key: Any,
    snapshot_fingerprint: Any,
    snapshot_version: Any,
    prompt_version: Any,
    model_id: Any,
    content: dict[str, Any],
    status: str = "candidate",
    generated_at: Any = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Insert or update one audit cache row without making it current."""
    clean_scope = _normalize_career_ai_insight_scope(scope)
    clean_scope_key = _normalize_career_ai_insight_scope_key(scope_key)
    clean_fingerprint = _normalize_career_ai_insight_text(snapshot_fingerprint, "snapshot_fingerprint")
    clean_snapshot_version = _normalize_career_ai_insight_text(snapshot_version, "snapshot_version")
    clean_prompt_version = _normalize_career_ai_insight_text(prompt_version, "prompt_version")
    clean_model_id = _normalize_career_ai_insight_text(model_id, "model_id")
    clean_status = _validate_career_ai_insight_status(status)
    if clean_status == "ready":
        raise ValueError("ready AI Insight 必须通过 save_ready_career_ai_insight 或 activate_career_ai_insight 写入")
    if not isinstance(content, dict):
        raise ValueError("AI Insight content 必须是对象")
    if _career_ai_insight_content_has_forbidden_key(content):
        raise ValueError("AI Insight content 包含禁止字段")
    insight_id = _career_ai_insight_id(
        clean_scope,
        clean_scope_key,
        clean_fingerprint,
        clean_prompt_version,
        clean_model_id,
    )
    now = _utc_now_iso()
    generated = str(generated_at or now)
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        ensure_career_schema(db)
        db.execute(
            """
            INSERT INTO career_ai_insights
                (
                    id, scope, scope_key, snapshot_fingerprint, snapshot_version,
                    prompt_version, model_id, content_json, generated_at,
                    created_at, updated_at, status
                )
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(scope, scope_key, snapshot_fingerprint, prompt_version, model_id)
            DO UPDATE SET
                snapshot_version = excluded.snapshot_version,
                content_json = excluded.content_json,
                generated_at = excluded.generated_at,
                updated_at = excluded.updated_at,
                status = excluded.status
            """,
            (
                insight_id,
                clean_scope,
                clean_scope_key,
                clean_fingerprint,
                clean_snapshot_version,
                clean_prompt_version,
                clean_model_id,
                _json_dumps(content),
                generated,
                now,
                now,
                clean_status,
            ),
        )
        if owns_conn:
            db.commit()
        return get_career_ai_insight_by_cache_key(
            scope=clean_scope,
            scope_key=clean_scope_key,
            snapshot_fingerprint=clean_fingerprint,
            prompt_version=clean_prompt_version,
            model_id=clean_model_id,
            conn=db,
        ) or {"id": insight_id, "status": clean_status}
    except Exception:
        if owns_conn:
            db.rollback()
        raise
    finally:
        if owns_conn:
            db.close()


def activate_career_ai_insight(
    insight_id: Any,
    *,
    content_validated: bool,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Atomically make one validated insight current and supersede older current rows."""
    clean_id = _normalize_career_ai_insight_text(insight_id, "id")
    if not content_validated:
        raise ValueError("未经校验的 AI Insight 不能进入 ready")
    owns_conn = conn is None
    db = conn or _connect_default()
    savepoint_name = "career_ai_insight_activate"
    try:
        ensure_career_schema(db)
        db.execute(f"SAVEPOINT {savepoint_name}")
        row = db.execute(
            f"""
            SELECT {_select_career_ai_insight_columns()}
            FROM career_ai_insights
            WHERE id = ?
            LIMIT 1
            """,
            (clean_id,),
        ).fetchone()
        current = _career_ai_insight_row(row)
        if current is None:
            raise ValueError("AI Insight 不存在")
        if current["status"] == "failed":
            raise ValueError("failed AI Insight 不能切换为 ready")
        now = _utc_now_iso()
        db.execute(
            """
            UPDATE career_ai_insights
            SET status = 'superseded',
                updated_at = ?
            WHERE scope = ?
              AND scope_key = ?
              AND status = 'ready'
              AND id != ?
            """,
            (now, current["scope"], current["scope_key"], clean_id),
        )
        db.execute(
            """
            UPDATE career_ai_insights
            SET status = 'ready',
                updated_at = ?
            WHERE id = ?
            """,
            (now, clean_id),
        )
        db.execute(f"RELEASE SAVEPOINT {savepoint_name}")
        if owns_conn:
            db.commit()
        activated = get_career_ai_insight_by_id(clean_id, conn=db)
        return activated or {"id": clean_id, "status": "ready"}
    except Exception:
        try:
            db.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
            db.execute(f"RELEASE SAVEPOINT {savepoint_name}")
        except sqlite3.Error:
            pass
        if owns_conn:
            db.rollback()
        raise
    finally:
        if owns_conn:
            db.close()


def save_ready_career_ai_insight(
    *,
    scope: Any,
    scope_key: Any,
    snapshot_fingerprint: Any,
    snapshot_version: Any,
    prompt_version: Any,
    model_id: Any,
    content: dict[str, Any],
    content_validated: bool,
    generated_at: Any = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Insert a validated AI report and switch it to the current ready row."""
    if not content_validated:
        raise ValueError("未经校验的 AI Insight 不能进入 ready")
    owns_conn = conn is None
    db = conn or _connect_default()
    savepoint_name = "career_ai_insight_save_ready"
    try:
        ensure_career_schema(db)
        db.execute(f"SAVEPOINT {savepoint_name}")
        inserted = insert_career_ai_insight(
            scope=scope,
            scope_key=scope_key,
            snapshot_fingerprint=snapshot_fingerprint,
            snapshot_version=snapshot_version,
            prompt_version=prompt_version,
            model_id=model_id,
            content=content,
            status="candidate",
            generated_at=generated_at,
            conn=db,
        )
        activated = activate_career_ai_insight(
            inserted["id"],
            content_validated=True,
            conn=db,
        )
        db.execute(f"RELEASE SAVEPOINT {savepoint_name}")
        if owns_conn:
            db.commit()
        return activated
    except Exception:
        try:
            db.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
            db.execute(f"RELEASE SAVEPOINT {savepoint_name}")
        except sqlite3.Error:
            pass
        if owns_conn:
            db.rollback()
        raise
    finally:
        if owns_conn:
            db.close()


def get_career_ai_insight_by_id(
    insight_id: Any,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    clean_id = _normalize_career_ai_insight_text(insight_id, "id")
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        ensure_career_schema(db)
        row = db.execute(
            f"""
            SELECT {_select_career_ai_insight_columns()}
            FROM career_ai_insights
            WHERE id = ?
            LIMIT 1
            """,
            (clean_id,),
        ).fetchone()
        return _career_ai_insight_row(row)
    finally:
        if owns_conn:
            db.close()


def get_career_ai_insight_by_cache_key(
    *,
    scope: Any,
    scope_key: Any,
    snapshot_fingerprint: Any,
    prompt_version: Any,
    model_id: Any,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    clean_scope = _normalize_career_ai_insight_scope(scope)
    clean_scope_key = _normalize_career_ai_insight_scope_key(scope_key)
    clean_fingerprint = _normalize_career_ai_insight_text(snapshot_fingerprint, "snapshot_fingerprint")
    clean_prompt_version = _normalize_career_ai_insight_text(prompt_version, "prompt_version")
    clean_model_id = _normalize_career_ai_insight_text(model_id, "model_id")
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        ensure_career_schema(db)
        row = db.execute(
            f"""
            SELECT {_select_career_ai_insight_columns()}
            FROM career_ai_insights
            WHERE scope = ?
              AND scope_key = ?
              AND snapshot_fingerprint = ?
              AND prompt_version = ?
              AND model_id = ?
            LIMIT 1
            """,
            (
                clean_scope,
                clean_scope_key,
                clean_fingerprint,
                clean_prompt_version,
                clean_model_id,
            ),
        ).fetchone()
        return _career_ai_insight_row(row)
    finally:
        if owns_conn:
            db.close()


def get_current_career_ai_insight(
    *,
    scope: Any,
    scope_key: Any,
    prompt_version: Any = None,
    model_id: Any = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    clean_scope = _normalize_career_ai_insight_scope(scope)
    clean_scope_key = _normalize_career_ai_insight_scope_key(scope_key)
    filters = [clean_scope, clean_scope_key]
    optional_where = ""
    if prompt_version is not None:
        optional_where += " AND prompt_version = ?"
        filters.append(_normalize_career_ai_insight_text(prompt_version, "prompt_version"))
    if model_id is not None:
        optional_where += " AND model_id = ?"
        filters.append(_normalize_career_ai_insight_text(model_id, "model_id"))
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        ensure_career_schema(db)
        row = db.execute(
            f"""
            SELECT {_select_career_ai_insight_columns()}
            FROM career_ai_insights
            WHERE scope = ?
              AND scope_key = ?
              AND status = 'ready'
              {optional_where}
            ORDER BY generated_at DESC, updated_at DESC, id DESC
            LIMIT 1
            """,
            tuple(filters),
        ).fetchone()
        return _career_ai_insight_row(row)
    finally:
        if owns_conn:
            db.close()


def get_career_year_snapshot_available_years(
    conn: sqlite3.Connection | None = None,
    *,
    activity_rows: list[dict[str, Any]] | None = None,
) -> list[int]:
    """Return valid Activity years for annual AI selection, sorted newest first."""
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        source_rows = activity_rows if activity_rows is not None else _overview_activity_rows(db)
        years = {
            int(year)
            for year in (
                _safe_activity_year(_overview_activity_date(row))
                for row in source_rows
            )
            if year is not None and CAREER_YEAR_MIN <= int(year) <= CAREER_YEAR_MAX
        }
        return sorted(years, reverse=True)
    finally:
        if owns_conn:
            db.close()


def build_career_year_snapshot(
    year: Any,
    conn: sqlite3.Connection | None = None,
    as_of_date: Any = None,
    *,
    activity_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return the Year Snapshot Activity fact layer; resolver evidence is filled by later tasks."""
    clean_year = _validate_career_year(year)
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        year_activity_rows = _career_year_snapshot_activity_rows(
            db,
            clean_year,
            activity_rows=activity_rows,
        )
        activity_facts = _build_career_year_activity_facts(year_activity_rows)
        evidence_catalog = _career_year_resolver_evidence(
            db,
            clean_year,
            {
                str(row.get("id") or "").strip()
                for row in year_activity_rows
                if str(row.get("id") or "").strip()
            },
        )
        latest_fact_date = _career_year_latest_fact_date(activity_facts.get("latest_activity_date"), evidence_catalog)
        period = _career_year_period(clean_year, as_of_date=as_of_date, data_through=latest_fact_date)
        evidence_counts = _career_year_evidence_counts(evidence_catalog)
        summary = dict(activity_facts["summary"])
        summary.update(evidence_counts)
        city_moments = activity_facts["city_moments"]
        highlight_moments = _career_year_highlight_moments(
            activity_facts["highlight_moments"],
            evidence_catalog,
            city_moments,
        )
        comparison = _build_career_year_comparison(
            db,
            clean_year,
            summary,
            period,
            activity_rows=activity_rows,
        )
    finally:
        if owns_conn:
            db.close()
    snapshot = {
        "snapshot_version": CAREER_YEAR_SNAPSHOT_VERSION,
        "scope": CAREER_YEAR_SNAPSHOT_SCOPE,
        "year": clean_year,
        "period": period,
        "summary": summary,
        "sport_breakdown": activity_facts["sport_breakdown"],
        "month_digest": activity_facts["month_digest"],
        "evidence_catalog": evidence_catalog,
        "highlight_moments": highlight_moments,
        "city_moments": city_moments,
        "comparison": comparison,
        "data_quality": _career_year_data_quality(summary, period, comparison),
        "source_fingerprint": "",
    }
    snapshot["source_fingerprint"] = compute_career_year_source_fingerprint(snapshot)
    validate_career_year_snapshot_contract(snapshot)
    return snapshot


def validate_career_year_snapshot_contract(snapshot: dict[str, Any]) -> bool:
    """Validate the recursive Year Snapshot safety and shape contract."""
    if not isinstance(snapshot, dict):
        raise ValueError("Year Snapshot 必须是对象")
    if tuple(snapshot.keys()) != CAREER_YEAR_SNAPSHOT_TOP_LEVEL_FIELDS:
        raise ValueError("Year Snapshot 顶层字段或顺序不符合契约")
    if snapshot.get("snapshot_version") != CAREER_YEAR_SNAPSHOT_VERSION:
        raise ValueError("Year Snapshot version 无效")
    if snapshot.get("scope") != CAREER_YEAR_SNAPSHOT_SCOPE:
        raise ValueError("Year Snapshot scope 无效")
    year = _validate_career_year(snapshot.get("year"))
    if _career_year_snapshot_has_forbidden_key(snapshot):
        raise ValueError("Year Snapshot 包含禁止字段")

    period = snapshot.get("period")
    if not isinstance(period, dict):
        raise ValueError("period 必须是对象")
    for key in CAREER_YEAR_SNAPSHOT_FIELD_SCHEMA["period"]["fields"]:
        if key not in period:
            raise ValueError(f"period 缺少字段 {key}")
    if period.get("start_date") != f"{year:04d}-01-01" or period.get("end_date") != f"{year:04d}-12-31":
        raise ValueError("period 年份边界无效")
    if not isinstance(period.get("is_partial_year"), bool):
        raise ValueError("period.is_partial_year 必须是布尔值")

    summary = snapshot.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("summary 必须是对象")
    for key in CAREER_YEAR_SNAPSHOT_FIELD_SCHEMA["summary"]["fields"]:
        if key not in summary:
            raise ValueError(f"summary 缺少字段 {key}")
        if not isinstance(summary.get(key), (int, float)):
            raise ValueError(f"summary.{key} 必须是数字")

    sport_breakdown = snapshot.get("sport_breakdown")
    if not isinstance(sport_breakdown, list):
        raise ValueError("sport_breakdown 必须是列表")
    sport_keys = [str(item.get("sport") or "") for item in sport_breakdown if isinstance(item, dict)]
    if sport_keys != sorted(sport_keys):
        raise ValueError("sport_breakdown 必须按 sport 稳定排序")

    month_digest = snapshot.get("month_digest")
    if not isinstance(month_digest, list):
        raise ValueError("month_digest 必须是列表")
    months = [item.get("month") for item in month_digest if isinstance(item, dict)]
    if months != sorted(months) or any(not isinstance(month, int) or month < 1 or month > 12 for month in months):
        raise ValueError("month_digest 必须按 1-12 月稳定排序")

    evidence_catalog = snapshot.get("evidence_catalog")
    if not isinstance(evidence_catalog, list):
        raise ValueError("evidence_catalog 必须是列表")
    evidence_keys = [
        (str(item.get("date") or ""), str(item.get("type") or ""), str(item.get("evidence_id") or ""))
        for item in evidence_catalog
        if isinstance(item, dict)
    ]
    if evidence_keys != sorted(evidence_keys):
        raise ValueError("evidence_catalog 必须按 date + type + evidence_id 排序")

    highlight_moments = snapshot.get("highlight_moments")
    if not isinstance(highlight_moments, list):
        raise ValueError("highlight_moments 必须是列表")
    highlight_keys = [
        (int(item.get("rank") or 99), str(item.get("date") or ""), str(item.get("id") or ""))
        for item in highlight_moments
        if isinstance(item, dict)
    ]
    if highlight_keys != sorted(highlight_keys):
        raise ValueError("highlight_moments 必须按 rank + date + id 排序")

    city_moments = snapshot.get("city_moments")
    if not isinstance(city_moments, list):
        raise ValueError("city_moments 必须是列表")
    city_keys = [
        (-int(item.get("activity_count") or 0), str(item.get("first_date") or ""), str(item.get("city") or ""))
        for item in city_moments
        if isinstance(item, dict)
    ]
    if city_keys != sorted(city_keys):
        raise ValueError("city_moments 必须按 activity_count desc + first_date + city 排序")

    comparison = snapshot.get("comparison")
    if not isinstance(comparison, dict):
        raise ValueError("comparison 必须是对象")
    for key in CAREER_YEAR_SNAPSHOT_FIELD_SCHEMA["comparison"]["fields"]:
        if key not in comparison:
            raise ValueError(f"comparison 缺少字段 {key}")

    data_quality = snapshot.get("data_quality")
    if not isinstance(data_quality, dict) or not isinstance(data_quality.get("warnings"), list):
        raise ValueError("data_quality 必须包含 warnings 列表")
    if not isinstance(snapshot.get("source_fingerprint"), str):
        raise ValueError("source_fingerprint 必须是字符串")
    return True


def _career_year_key_events(snapshot: dict[str, Any], limit: int | None = None) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for item in snapshot.get("evidence_catalog") or []:
        if not isinstance(item, dict):
            continue
        events.append(
            {
                "evidence_id": str(item.get("evidence_id") or ""),
                "activity_id": str(item.get("activity_id") or ""),
                "type": str(item.get("type") or ""),
                "title": str(item.get("title") or ""),
                "date": str(item.get("date") or ""),
                "value": str(item.get("value") or ""),
            }
        )
    if limit is not None:
        return events[:limit]
    return events


def _career_year_highlight_events(snapshot: dict[str, Any], limit: int | None = None) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for item in snapshot.get("highlight_moments") or []:
        if not isinstance(item, dict):
            continue
        events.append({
            "id": str(item.get("id") or ""),
            "activity_id": str(item.get("activity_id") or ""),
            "type": str(item.get("type") or ""),
            "title": str(item.get("title") or ""),
            "date": str(item.get("date") or ""),
            "value": str(item.get("value") or ""),
            "rank": int(item.get("rank") or 99),
            "detail_link": {"activity_id": str(item.get("activity_id") or ""), "source": "activity"},
        })
    if limit is not None:
        return events[:limit]
    return events


def _career_year_facts_view(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    clean = snapshot if isinstance(snapshot, dict) else {}
    summary = clean.get("summary") if isinstance(clean.get("summary"), dict) else _empty_career_year_summary()
    period = clean.get("period") if isinstance(clean.get("period"), dict) else {}
    comparison = clean.get("comparison") if isinstance(clean.get("comparison"), dict) else _empty_career_year_comparison(
        int(clean.get("year") or 0) if str(clean.get("year") or "").isdigit() else 0
    )
    data_quality = clean.get("data_quality") if isinstance(clean.get("data_quality"), dict) else {
        "status": "no_data",
        "warnings": ["no_activity_data"],
    }
    return {
        "year": clean.get("year"),
        "period": {
            "start_date": str(period.get("start_date") or ""),
            "end_date": str(period.get("end_date") or ""),
            "data_through": period.get("data_through"),
            "is_partial_year": bool(period.get("is_partial_year")),
        },
        "summary": {
            "activity_count": int(summary.get("activity_count") or 0),
            "total_distance_km": round(float(summary.get("total_distance_km") or 0.0), 1),
            "total_duration_seconds": int(summary.get("total_duration_seconds") or 0),
            "total_duration_seconds": int(summary.get("total_duration_seconds") or 0),
            "race_count": int(summary.get("race_count") or 0),
            "pb_count": int(summary.get("pb_count") or 0),
            "achievement_count": int(summary.get("achievement_count") or 0),
            "covered_city_count": int(summary.get("covered_city_count") or 0),
        },
        "sport_breakdown": [
            {
                "sport": str(item.get("sport") or ""),
                "sport_label": str(item.get("sport_label") or ""),
                "activity_count": int(item.get("activity_count") or 0),
                "distance_km": round(float(item.get("distance_km") or 0.0), 1),
                "duration_seconds": int(item.get("duration_seconds") or 0),
            }
            for item in (clean.get("sport_breakdown") or [])
            if isinstance(item, dict)
        ],
        "month_digest": [
            {
                "month": int(item.get("month") or 0),
                "activity_count": int(item.get("activity_count") or 0),
                "distance_km": round(float(item.get("distance_km") or 0.0), 1),
                "duration_seconds": int(item.get("duration_seconds") or 0),
                "primary_sport": str(item.get("primary_sport") or ""),
            }
            for item in (clean.get("month_digest") or [])
            if isinstance(item, dict)
        ],
        "key_events": _career_year_key_events(clean),
        "highlight_moments": _career_year_highlight_events(clean),
        "city_moments": [
            {
                "city": str(item.get("city") or ""),
                "activity_count": int(item.get("activity_count") or 0),
                "first_date": str(item.get("first_date") or ""),
                "latest_date": str(item.get("latest_date") or ""),
                "representative_activity_id": str(item.get("representative_activity_id") or ""),
                "culture_hint": str(item.get("culture_hint") or ""),
                "detail_link": {"activity_id": str(item.get("representative_activity_id") or ""), "source": "activity"},
            }
            for item in (clean.get("city_moments") or [])
            if isinstance(item, dict)
        ],
        "comparison": {
            "status": str(comparison.get("status") or "unavailable"),
            "reason": comparison.get("reason"),
            "comparison_year": comparison.get("comparison_year"),
            "period_mode": str(comparison.get("period_mode") or "none"),
            "activity_count_delta": comparison.get("activity_count_delta"),
            "distance_km_delta": comparison.get("distance_km_delta"),
            "duration_seconds_delta": comparison.get("duration_seconds_delta"),
            "race_count_delta": comparison.get("race_count_delta"),
            "pb_count_delta": comparison.get("pb_count_delta"),
        },
        "data_quality": {
            "status": str(data_quality.get("status") or "no_data"),
            "warnings": [
                str(item)
                for item in (data_quality.get("warnings") or [])
            ],
        },
    }


def _career_year_local_fallback(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    facts = _career_year_facts_view(snapshot)
    summary = facts["summary"]
    month_digest = facts["month_digest"]
    active_months = [
        item for item in month_digest
        if int(item.get("activity_count") or 0) > 0
    ]
    top_month = None
    if active_months:
        top_month = sorted(
            active_months,
            key=lambda item: (
                -float(item.get("distance_km") or 0.0),
                -int(item.get("activity_count") or 0),
                int(item.get("month") or 0),
            ),
        )[0]
    highlights: list[str] = []
    if summary["activity_count"]:
        highlights.append(f"全年记录 {summary['activity_count']} 次活动")
    if summary["total_distance_km"]:
        highlights.append(f"累计距离 {summary['total_distance_km']:.1f} km")
    if summary["race_count"]:
        highlights.append(f"{summary['race_count']} 场赛事")
    if summary["pb_count"]:
        highlights.append(f"{summary['pb_count']} 项 PB")
    if summary["achievement_count"]:
        highlights.append(f"{summary['achievement_count']} 项成就")
    if not highlights:
        highlights.append("暂无足够年度活动事实")
    return {
        "mode": "local_fallback",
        "title": "年度事实摘要",
        "summary": "这是后端本地事实摘要，不是 AI 生成报告。",
        "highlights": highlights[:5],
        "key_events": facts["key_events"][:5],
        "month_rhythm": {
            "active_month_count": len(active_months),
            "top_month": top_month,
        },
        "comparison": facts["comparison"],
        "disclaimer": "本地 fallback 只展示已解析事实，不调用 AI，不生成叙事判断。",
    }


def _career_year_report_view(cached_report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(cached_report, dict):
        return None
    content = cached_report.get("content") if isinstance(cached_report.get("content"), dict) else {}
    return {
        "mode": "ai",
        "content": content,
        "schema_version": str(content.get("schema_version") or "acs.year.report.v1"),
        "snapshot_fingerprint": str(cached_report.get("snapshot_fingerprint") or ""),
        "snapshot_version": str(cached_report.get("snapshot_version") or ""),
        "prompt_version": str(cached_report.get("prompt_version") or ""),
        "model_id": str(cached_report.get("model_id") or ""),
        "generated_at": _career_year_display_time(cached_report.get("generated_at")),
    }


def get_career_year_insight(
    year: Any = None,
    *,
    ai_available: bool = True,
    runtime: dict[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Return the annual insight read model without calling LLM or writing AI cache."""
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        ensure_career_schema(db)
        activity_rows = _overview_activity_rows(db)
        available_years = get_career_year_snapshot_available_years(
            conn=db,
            activity_rows=activity_rows,
        )
        update_badges = _career_year_update_badges(
            available_years,
            conn=db,
            activity_rows=activity_rows,
        )
        if year is None or year == "":
            clean_year = available_years[0] if available_years else None
        else:
            clean_year = _validate_career_year(year)

        snapshot = (
            build_career_year_snapshot(clean_year, conn=db, activity_rows=activity_rows)
            if clean_year is not None
            else None
        )
        cached_report = (
            get_current_career_ai_insight(
                scope=CAREER_AI_INSIGHT_SCOPE_YEAR,
                scope_key=str(clean_year),
                conn=db,
            )
            if clean_year is not None
            else None
        )
        state_report = None
        if cached_report:
            state_report = {
                "status": cached_report.get("status"),
                "source_fingerprint": cached_report.get("snapshot_fingerprint"),
            }
        state = resolve_career_year_report_state(
            snapshot,
            state_report,
            runtime=runtime,
            ai_available=ai_available,
        )
        facts = _career_year_facts_view(snapshot)
        report = _career_year_report_view(cached_report) if state.get("report_available") else None
        format_upgrade_available = bool(
            state.get("status") == "ready"
            and ai_available
            and _career_year_report_needs_format_upgrade(cached_report)
        )
        period = snapshot.get("period") if isinstance(snapshot, dict) and isinstance(snapshot.get("period"), dict) else {}
        data_ready = _career_year_snapshot_has_data(snapshot)
        return {
            "available_years": available_years,
            "year_update_badges": update_badges,
            "year": clean_year,
            "report_state": state["status"],
            "can_generate": bool(state.get("can_generate")),
            "can_refresh": bool(state.get("can_refresh")),
            "has_source_changes": bool(state.get("has_source_changes")),
            "format_upgrade_available": format_upgrade_available,
            "can_upgrade_format": format_upgrade_available,
            "facts": facts,
            "report": report,
            "local_fallback": _career_year_local_fallback(snapshot),
            "generated_at": _career_year_display_time((cached_report or {}).get("generated_at")),
            "data_through": period.get("data_through"),
            "status": {
                "schema_ready": True,
                "data_ready": data_ready,
                "message": "年度报告只读数据已生成" if clean_year is not None else "暂无年度活动数据",
            },
        }
    finally:
        if owns_conn:
            db.close()


def _career_year_generation_view(
    year: Any,
    *,
    generation_status: str,
    message: str,
    ai_available: bool = True,
    runtime_state: str | None = None,
    insight: dict[str, Any] | None = None,
    conn: sqlite3.Connection,
) -> dict[str, Any]:
    runtime = {"state": runtime_state} if runtime_state else None
    view = get_career_year_insight(year, ai_available=ai_available, runtime=runtime, conn=conn)
    generation: dict[str, Any] = {
        "status": str(generation_status or ""),
        "message": str(message or ""),
    }
    if isinstance(insight, dict):
        generation.update({
            "insight_id": str(insight.get("id") or ""),
            "snapshot_fingerprint": str(insight.get("snapshot_fingerprint") or ""),
            "prompt_version": str(insight.get("prompt_version") or ""),
            "model_id": str(insight.get("model_id") or ""),
            "generated_at": _career_year_display_time(insight.get("generated_at")),
        })
    view["generation"] = generation
    return view


def _career_year_default_llm_context() -> tuple[Any, dict[str, Any], str, str, bool]:
    import llm_backend

    cfg = llm_backend.load_llm_config()
    transport = llm_backend._normalize_transport(cfg.get("transport"))
    cli_type = llm_backend._normalize_cli_type(cfg.get("cli_type"))
    model_id = str(cfg.get("model") or cfg.get("cli_model") or "").strip()
    if transport == "cli":
        available = bool(cli_type)
        if cli_type == "custom" and not str(cfg.get("cli_path") or "").strip():
            available = False
        if not model_id and cli_type:
            model_id = f"{cli_type}-default"
    else:
        available = bool(str(cfg.get("url") or "").strip() and model_id)
    return (
        llm_backend.generate_career_year_summary,
        cfg,
        llm_backend.CAREER_YEAR_SUMMARY_PROMPT_VERSION,
        model_id,
        available,
    )


def _call_career_year_generator(
    generator: Any,
    snapshot: dict[str, Any],
    *,
    config: dict[str, Any] | None,
) -> dict[str, Any]:
    if config is None:
        return generator(snapshot)
    return generator(snapshot, config=config)


def _career_year_generation_flight_start(
    key: tuple[str, str, str, str],
) -> tuple[bool, dict[str, Any]]:
    with CAREER_YEAR_GENERATION_FLIGHT_LOCK:
        existing = CAREER_YEAR_GENERATION_FLIGHTS.get(key)
        if existing is not None:
            return False, existing
        flight = {
            "condition": threading.Condition(CAREER_YEAR_GENERATION_FLIGHT_LOCK),
            "done": False,
            "result": None,
        }
        CAREER_YEAR_GENERATION_FLIGHTS[key] = flight
        return True, flight


def _career_year_generation_flight_wait(flight: dict[str, Any]) -> dict[str, Any]:
    condition = flight["condition"]
    with condition:
        while not flight.get("done"):
            condition.wait()
        result = flight.get("result")
    if isinstance(result, dict):
        return copy.deepcopy(result)
    raise RuntimeError("年度总结生成单飞未返回结果")


def _career_year_generation_flight_finish(
    key: tuple[str, str, str, str],
    flight: dict[str, Any],
    result: dict[str, Any],
) -> None:
    condition = flight["condition"]
    with condition:
        flight["result"] = copy.deepcopy(result)
        flight["done"] = True
        CAREER_YEAR_GENERATION_FLIGHTS.pop(key, None)
        condition.notify_all()


def _save_ready_career_ai_insight_with_retry(
    *,
    max_attempts: int = 3,
    **kwargs: Any,
) -> dict[str, Any]:
    last_exc: sqlite3.OperationalError | None = None
    for attempt in range(max(1, max_attempts)):
        try:
            return save_ready_career_ai_insight(**kwargs)
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt >= max_attempts - 1:
                raise
            last_exc = exc
            time.sleep(0.05 * (attempt + 1))
    raise last_exc or sqlite3.OperationalError("database is locked")


def _career_year_generation_failure_status(exc: BaseException, phase: str) -> tuple[str, str, bool, str | None]:
    if phase == "persistence":
        return "persistence_failed", "年度总结保存失败，已保留当前事实与历史报告", True, "failed"
    if isinstance(exc, TimeoutError):
        return "timeout", "AI 生成超时，已保留当前事实与历史报告", True, "failed"
    if phase == "validation":
        text = str(exc).lower()
        if "evidence" in text:
            return "evidence_failed", "AI 输出引用的证据未通过校验，已保留当前事实与历史报告", True, "failed"
        if "schema" in text or "year" in text:
            return "schema_failed", "AI 输出结构未通过校验，已保留当前事实与历史报告", True, "failed"
        return "format_failed", "AI 输出格式未通过校验，已保留当前事实与历史报告", True, "failed"
    if isinstance(exc, ValueError):
        return "format_failed", "AI 输出格式未通过校验，已保留当前事实与历史报告", True, "failed"
    return "network_failed", "AI 生成服务暂不可用，已保留当前事实与历史报告", True, "failed"


def generate_career_year_insight(
    year: Any,
    *,
    generator: Any = None,
    prompt_version: Any = None,
    model_id: Any = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Generate or refresh a year-scoped ACS AI report under backend state gates."""
    started = time.perf_counter()
    clean_year = _validate_career_year(year)
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        ensure_career_schema(db)
        snapshot = build_career_year_snapshot(clean_year, conn=db)
        cached_report = get_current_career_ai_insight(
            scope=CAREER_AI_INSIGHT_SCOPE_YEAR,
            scope_key=str(clean_year),
            conn=db,
        )
        state_report = None
        if cached_report:
            state_report = {
                "status": cached_report.get("status"),
                "source_fingerprint": cached_report.get("snapshot_fingerprint"),
            }
        state = resolve_career_year_report_state(snapshot, state_report)
        format_upgrade = bool(
            state["status"] == "ready"
            and _career_year_report_needs_format_upgrade(cached_report)
        )
        if state["status"] == "no_data":
            return _career_year_generation_view(
                clean_year,
                generation_status="not_allowed",
                message="该年度暂无可生成年度总结的活动数据",
                conn=db,
            )
        if state["status"] == "ready" and not format_upgrade:
            return _career_year_generation_view(
                clean_year,
                generation_status="already_ready",
                message="年度总结已是最新",
                insight=cached_report,
                conn=db,
            )
        if state["status"] not in {"not_generated", "stale"} and not format_upgrade:
            return _career_year_generation_view(
                clean_year,
                generation_status="not_allowed",
                message="当前状态不允许生成年度总结",
                conn=db,
            )

        llm_config: dict[str, Any] | None = None
        llm_available = True
        active_generator = generator
        clean_prompt_version = str(prompt_version or "").strip()
        clean_model_id = str(model_id or "").strip()
        if active_generator is None:
            active_generator, llm_config, default_prompt_version, default_model_id, llm_available = _career_year_default_llm_context()
            clean_prompt_version = clean_prompt_version or default_prompt_version
            clean_model_id = clean_model_id or default_model_id
        else:
            clean_prompt_version = clean_prompt_version or "acs.year.summary.zh-CN.v4"
            clean_model_id = clean_model_id or "test-model"

        if not llm_available or not clean_prompt_version or not clean_model_id:
            return _career_year_generation_view(
                clean_year,
                generation_status="ai_unavailable",
                message="AI 配置不可用，暂不能生成年度总结",
                ai_available=False,
                conn=db,
            )

        exact_cached = get_career_ai_insight_by_cache_key(
            scope=CAREER_AI_INSIGHT_SCOPE_YEAR,
            scope_key=str(clean_year),
            snapshot_fingerprint=snapshot["source_fingerprint"],
            prompt_version=clean_prompt_version,
            model_id=clean_model_id,
            conn=db,
        )
        if exact_cached and exact_cached.get("status") in {"ready", "superseded"}:
            ready = exact_cached
            if exact_cached.get("status") != "ready":
                ready = activate_career_ai_insight(
                    exact_cached["id"],
                    content_validated=True,
                    conn=db,
                )
                if owns_conn:
                    db.commit()
            return _career_year_generation_view(
                clean_year,
                generation_status="cache_hit",
                message="已复用年度总结缓存",
                insight=ready,
                conn=db,
            )

        flight_key = (
            str(clean_year),
            str(snapshot.get("source_fingerprint") or ""),
            clean_prompt_version,
            clean_model_id,
        )
        is_leader, flight = _career_year_generation_flight_start(flight_key)
        if not is_leader:
            return _career_year_generation_flight_wait(flight)

        result: dict[str, Any]
        try:
            exact_cached = get_career_ai_insight_by_cache_key(
                scope=CAREER_AI_INSIGHT_SCOPE_YEAR,
                scope_key=str(clean_year),
                snapshot_fingerprint=snapshot["source_fingerprint"],
                prompt_version=clean_prompt_version,
                model_id=clean_model_id,
                conn=db,
            )
            if exact_cached and exact_cached.get("status") in {"ready", "superseded"}:
                ready = exact_cached
                if exact_cached.get("status") != "ready":
                    ready = activate_career_ai_insight(
                        exact_cached["id"],
                        content_validated=True,
                        conn=db,
                    )
                    if owns_conn:
                        db.commit()
                result = _career_year_generation_view(
                    clean_year,
                    generation_status="cache_hit",
                    message="已复用年度总结缓存",
                    insight=ready,
                    conn=db,
                )
                return result

            phase = "llm"
            try:
                generated = _call_career_year_generator(
                    active_generator,
                    snapshot,
                    config=llm_config,
                )
                if not isinstance(generated, dict):
                    raise ValueError("年度 AI 生成结果必须是对象")
                latest_snapshot = build_career_year_snapshot(clean_year, conn=db)
                if latest_snapshot.get("source_fingerprint") != snapshot.get("source_fingerprint"):
                    result = _career_year_generation_view(
                        clean_year,
                        generation_status="source_changed",
                        message="年度事实已变化，本次生成结果已丢弃，请重新生成",
                        conn=db,
                    )
                    return result
                draft = generated.get("content") if isinstance(generated.get("content"), dict) else generated
                phase = "validation"
                validated = validate_career_year_ai_report(draft, snapshot)
                result_prompt_version = str(generated.get("prompt_version") or clean_prompt_version).strip()
                result_model_id = str(generated.get("model_id") or clean_model_id).strip()
                if not result_prompt_version or not result_model_id:
                    raise ValueError("年度 AI 生成结果缺少 prompt_version 或 model_id")
                phase = "persistence"
                saved = _save_ready_career_ai_insight_with_retry(
                    scope=CAREER_AI_INSIGHT_SCOPE_YEAR,
                    scope_key=str(clean_year),
                    snapshot_fingerprint=snapshot["source_fingerprint"],
                    snapshot_version=snapshot["snapshot_version"],
                    prompt_version=result_prompt_version,
                    model_id=result_model_id,
                    content=validated,
                    content_validated=True,
                    conn=db,
                )
                if owns_conn:
                    db.commit()
                result = _career_year_generation_view(
                    clean_year,
                    generation_status="generated",
                    message="年度总结已生成",
                    insight=saved,
                    conn=db,
                )
                return result
            except Exception as exc:
                if owns_conn:
                    db.rollback()
                failure_status, failure_message, failure_ai_available, failure_runtime = _career_year_generation_failure_status(exc, phase)
                elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
                logger.warning(
                    "generate_career_year_insight result year=%s fingerprint=%s prompt=%s model=%s phase=%s status=%s elapsed_ms=%s",
                    clean_year,
                    str(snapshot.get("source_fingerprint") or "")[:18],
                    clean_prompt_version,
                    clean_model_id,
                    phase,
                    failure_status,
                    elapsed_ms,
                )
                result = _career_year_generation_view(
                    clean_year,
                    generation_status=failure_status,
                    message=failure_message,
                    ai_available=failure_ai_available,
                    runtime_state=failure_runtime,
                    conn=db,
                )
                return result
        finally:
            _career_year_generation_flight_finish(flight_key, flight, locals().get("result", {
                "year": clean_year,
                "report_state": "ai_unavailable",
                "generation": {"status": "ai_unavailable", "message": "年度总结生成未完成"},
            }))
    finally:
        if owns_conn:
            db.close()


def _clean_career_year_ai_text(value: Any, max_len: int) -> str:
    text = str(value or "")
    text = re.sub(r"```(?:json)?|```", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<script\b[^>]*>.*?</script>", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)
    text = "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 32)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


def _clean_career_year_ai_list(value: Any, *, max_items: int, max_len: int) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    elif value:
        raw_items = [value]
    else:
        raw_items = []
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = _clean_career_year_ai_text(item, max_len)
        if not text or text in seen:
            continue
        cleaned.append(text)
        seen.add(text)
        if len(cleaned) >= max_items:
            break
    return cleaned


def _career_year_evidence_map(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    evidence: dict[str, dict[str, Any]] = {}
    for item in snapshot.get("evidence_catalog") or []:
        if not isinstance(item, dict):
            continue
        evidence_id = str(item.get("evidence_id") or "").strip()
        if not evidence_id:
            continue
        evidence[evidence_id] = {
            "evidence_id": evidence_id,
            "activity_id": str(item.get("activity_id") or ""),
            "type": str(item.get("type") or ""),
            "title": str(item.get("title") or ""),
            "date": str(item.get("date") or ""),
            "value": str(item.get("value") or ""),
            "detail_link": {
                "activity_id": str(item.get("activity_id") or ""),
                "source": "activity",
            },
        }
    return evidence


def _career_year_highlight_map(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    highlights: dict[str, dict[str, Any]] = {}
    for item in snapshot.get("highlight_moments") or []:
        if not isinstance(item, dict):
            continue
        highlight_id = str(item.get("id") or "").strip()
        if not highlight_id:
            continue
        highlights[highlight_id] = {
            "evidence_id": highlight_id,
            "id": highlight_id,
            "activity_id": str(item.get("activity_id") or ""),
            "type": str(item.get("type") or ""),
            "title": str(item.get("title") or ""),
            "date": str(item.get("date") or ""),
            "value": str(item.get("value") or ""),
            "detail_link": {
                "activity_id": str(item.get("activity_id") or ""),
                "source": "activity",
            },
        }
    return highlights


def _career_year_fact_leads(snapshot: dict[str, Any]) -> list[str]:
    summary = snapshot.get("summary") if isinstance(snapshot.get("summary"), dict) else {}
    period = snapshot.get("period") if isinstance(snapshot.get("period"), dict) else {}
    activity_count = int(summary.get("activity_count") or 0)
    distance_km = round(float(summary.get("total_distance_km") or 0.0), 1)
    duration_seconds = int(summary.get("total_duration_seconds") or 0)
    duration_hours = round(duration_seconds / 3600.0, 1) if duration_seconds > 0 else 0.0
    prefix = "这一年"
    if bool(period.get("is_partial_year")):
        data_through = str(period.get("data_through") or "").strip()
        prefix = f"截至 {data_through}" if data_through else "截至当前数据周期"
    leads: list[str] = []
    if activity_count > 0:
        leads.append(f"{prefix}，这些普通日子已经积累成了 {activity_count} 次运动。")
    if distance_km > 0:
        leads.append(f"这些活动带你走过了 {distance_km:g} 公里。它不只是一个总数，也记录了运动如何被慢慢留在生活里。")
    if duration_hours > 0:
        leads.append(f"时间也留下了痕迹：大约 {duration_hours:g} 小时，被一次次交给了路上、场地和训练。")
    achievements: list[str] = []
    race_count = int(summary.get("race_count") or 0)
    pb_count = int(summary.get("pb_count") or 0)
    achievement_count = int(summary.get("achievement_count") or 0)
    if race_count > 0:
        achievements.append(f"{race_count} 场比赛")
    if pb_count > 0:
        achievements.append(f"{pb_count} 项 PB")
    if achievement_count > 0:
        achievements.append(f"{achievement_count} 项成就或里程碑")
    if achievements:
        leads.append("其中真正发亮的部分，是 " + "、".join(achievements) + "，这些可以回跳到活动详情的节点。")
    city_count = int(summary.get("covered_city_count") or 0)
    if city_count > 0:
        leads.append(f"这一年的运动足迹也覆盖了 {city_count} 座城市。每一座城市，只记录你确实留下过的运动坐标。")
    if not leads:
        leads.append(f"{prefix}，年度事实还不多，但已经有了可以继续积累的起点。")
    return leads[:5]


def _career_year_fact_lead(snapshot: dict[str, Any]) -> str:
    return " ".join(_career_year_fact_leads(snapshot))


def validate_career_year_ai_report(
    draft: dict[str, Any],
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Validate an untrusted LLM annual report and return a cache-safe report."""
    if not isinstance(draft, dict):
        raise ValueError("年度 AI 报告必须是 JSON 对象")
    validate_career_year_snapshot_contract(snapshot)
    clean_year = _validate_career_year(snapshot.get("year"))
    if draft.get("schema_version") != CAREER_YEAR_AI_REPORT_SCHEMA_VERSION:
        raise ValueError("年度 AI 报告 schema_version 无效")
    if _validate_career_year(draft.get("year")) != clean_year:
        raise ValueError("年度 AI 报告 year 与 Snapshot 不一致")

    evidence_by_id = _career_year_evidence_map(snapshot)
    highlight_by_id = _career_year_highlight_map(snapshot)
    comparison = snapshot.get("comparison") if isinstance(snapshot.get("comparison"), dict) else {}
    summary = snapshot.get("summary") if isinstance(snapshot.get("summary"), dict) else {}
    allowed_evidence_types = {
        "races": {"race"},
        "progress": {
            "pb",
            "achievement",
            "milestone",
            "longest_distance",
            "longest_duration",
            "max_altitude",
            "max_altitude_5000m",
            "annual_ascent_milestone",
        },
        "footprints": {"city", "achievement", "milestone"},
    }
    section_defaults = {
        "annual_story": "这一年的主线",
        "races": "你完成的比赛",
        "progress": "看得见的进步",
        "footprints": "这一年的运动足迹",
        "rhythm": "这一年的节奏",
        "comparison": "和上一年相比",
    }
    raw_sections = draft.get("body_sections") if isinstance(draft.get("body_sections"), list) else []
    sections_by_type: dict[str, dict[str, Any]] = {}
    unknown_evidence = 0
    used_evidence: set[str] = set()
    moments: list[dict[str, Any]] = []
    for raw in raw_sections:
        if not isinstance(raw, dict):
            continue
        section_type = str(raw.get("type") or "").strip()
        if section_type not in CAREER_YEAR_AI_SECTION_ORDER or section_type in sections_by_type:
            continue
        if section_type == "races" and int(summary.get("race_count") or 0) <= 0:
            continue
        if section_type == "progress" and (
            int(summary.get("pb_count") or 0) <= 0
            and int(summary.get("achievement_count") or 0) <= 0
        ):
            continue
        if section_type == "comparison" and comparison.get("status") != "available":
            continue
        if section_type == "footprints" and not snapshot.get("city_moments"):
            continue
        paragraphs = _clean_career_year_ai_list(raw.get("paragraphs"), max_items=3, max_len=320)
        paragraphs = [
            cleaned
            for cleaned in (
                _sanitize_career_year_ai_narrative_numbers(text, clean_year)
                for text in paragraphs
            )
            if cleaned
        ]
        if not paragraphs and section_type == "annual_story":
            paragraphs = ["这一年留下的运动记录，来自一次次真实的出发与回来。"]
        if not paragraphs and section_type == "rhythm":
            paragraphs = ["从已经记录的活动中，可以看见这一年的运动节奏和持续积累。"]
        if not paragraphs:
            continue
        section_evidence: list[dict[str, Any]] = []
        raw_ids = raw.get("evidence_ids") if isinstance(raw.get("evidence_ids"), list) else []
        for raw_id in raw_ids:
            evidence_id = str(raw_id or "").strip()
            if not evidence_id or evidence_id in used_evidence:
                continue
            fact = evidence_by_id.get(evidence_id) or highlight_by_id.get(evidence_id)
            allowed_types = allowed_evidence_types.get(section_type)
            if fact is None or (allowed_types is not None and fact.get("type") not in allowed_types):
                unknown_evidence += 1
                continue
            if allowed_types is None:
                continue
            used_evidence.add(evidence_id)
            section_evidence.append(fact)
            moments.append(fact)
            if len(section_evidence) >= 5:
                break
        if section_type in allowed_evidence_types and not section_evidence:
            continue
        heading = _clean_career_year_ai_text(raw.get("heading"), 40) or section_defaults[section_type]
        sections_by_type[section_type] = {
            "type": section_type,
            "heading": _sanitize_career_year_ai_narrative_numbers(
                heading,
                clean_year,
                fallback=section_defaults[section_type],
            ),
            "paragraphs": paragraphs,
            "evidence": section_evidence,
        }
    if unknown_evidence >= CAREER_YEAR_AI_UNKNOWN_EVIDENCE_FAILURE_THRESHOLD:
        raise ValueError("年度 AI 报告引用了过多未知或类型不匹配的 evidence_id")
    if "annual_story" not in sections_by_type or "rhythm" not in sections_by_type:
        raise ValueError("年度 AI 报告缺少基础叙事章节")
    sections = [
        sections_by_type[section_type]
        for section_type in CAREER_YEAR_AI_SECTION_ORDER
        if section_type in sections_by_type
    ]
    title = _clean_career_year_ai_text(draft.get("title"), 60)
    subtitle = _clean_career_year_ai_text(draft.get("subtitle"), 80)
    opening = _clean_career_year_ai_text(draft.get("opening"), 320)
    closing = _clean_career_year_ai_text(draft.get("closing"), 320)
    letter = _clean_career_year_ai_text(draft.get("letter_to_next_year"), 260)
    if not title or not opening or not closing or not letter:
        raise ValueError("年度 AI 报告缺少必要长文内容")
    title = _sanitize_career_year_ai_narrative_numbers(
        title,
        clean_year,
        allow_year=True,
        fallback=f"{clean_year}，这一年的运动故事",
    )
    subtitle = _sanitize_career_year_ai_narrative_numbers(subtitle, clean_year)
    opening = _sanitize_career_year_ai_narrative_numbers(
        opening,
        clean_year,
        fallback="这些记录来自一个个普通日子里的出发、坚持和回来。",
    )
    closing = _sanitize_career_year_ai_narrative_numbers(
        closing,
        clean_year,
        fallback="这一年真正值得记住的，是持续为运动留下了真实痕迹。",
    )
    closing = _career_year_complete_sentence(
        closing,
        "这一年真正值得记住的，是持续为运动留下了真实痕迹。",
    )
    letter = _sanitize_career_year_ai_narrative_numbers(
        letter,
        clean_year,
        fallback="写给下一年的你：继续把运动留在生活里。",
    )
    letter = _career_year_complete_sentence(
        letter,
        "写给下一年的你：继续把运动留在生活里。",
    )
    share_caption = _sanitize_career_year_ai_narrative_numbers(
        _clean_career_year_ai_text(draft.get("share_caption"), 100),
        clean_year,
    )
    share_caption = share_caption.rstrip("，,、；;：:")
    annual_story = " ".join(sections_by_type["annual_story"]["paragraphs"])
    rhythm = " ".join(sections_by_type["rhythm"]["paragraphs"])
    comparison_text = ""
    if "comparison" in sections_by_type:
        comparison_text = " ".join(sections_by_type["comparison"]["paragraphs"])
    return {
        "schema_version": CAREER_YEAR_AI_REPORT_SCHEMA_VERSION,
        "year": clean_year,
        "title": title,
        "subtitle": subtitle,
        "fact_lead": _career_year_fact_lead(snapshot),
        "fact_leads": _career_year_fact_leads(snapshot),
        "opening": opening,
        "body_sections": sections,
        "closing": closing,
        "letter_to_next_year": letter,
        "share_caption": share_caption,
        "headline": title,
        "annual_thread": annual_story,
        "mainline": annual_story,
        "key_moments": moments,
        "rhythm_summary": rhythm,
        "rhythm": rhythm,
        "comparison_summary": comparison_text,
        "comparison": comparison_text,
        "directions": [letter],
        "next_year_direction": letter,
        "commentary": [],
        "caveats": _clean_career_year_ai_list(draft.get("caveats"), max_items=4, max_len=160),
        "disclaimer": "仅基于脉图年度事实生成，不构成医疗或训练处方。",
        "facts_summary": {
            "activity_count": int(summary.get("activity_count") or 0),
            "total_distance_km": round(float(summary.get("total_distance_km") or 0.0), 1),
            "race_count": int(summary.get("race_count") or 0),
            "pb_count": int(summary.get("pb_count") or 0),
            "achievement_count": int(summary.get("achievement_count") or 0),
        },
    }


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
    return {
        "snapshot_version": str(snapshot.get("snapshot_version") or "acs.v1"),
        "generated_at": str(snapshot.get("generated_at") or ""),
        "summary": {
            "career_start_year": raw_summary.get("career_start_year"),
            "activity_count": int(raw_summary.get("activity_count") or 0),
            "race_count": int(raw_summary.get("race_count") or 0),
            "pb_count": int(raw_summary.get("pb_count") or 0),
            "achievement_count": int(raw_summary.get("achievement_count") or 0),
            "covered_city_count": int(raw_summary.get("covered_city_count") or 0),
            "total_distance_km": raw_summary.get("total_distance_km"),
        },
        "primary_sport": {
            "sport": str(raw_primary_sport.get("sport") or ""),
            "activity_count": int(raw_primary_sport.get("activity_count") or 0),
            "confidence": str(raw_primary_sport.get("confidence") or "none"),
        },
        "pb_summary": pb_summary,
        "records_summary": _sanitize_snapshot_records_summary(
            snapshot.get("records_summary") if isinstance(snapshot.get("records_summary"), dict) else None
        ),
        "major_achievements": major_achievements,
        "timeline_digest": timeline_digest,
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
    start = time.perf_counter()
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
                   event_date, confidence, source, status, display_metadata_json,
                   evidence_key, source_mode, sport_scope, previous_record_id, resolver_version
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
            "metrics": {
                "elapsed_ms": _elapsed_ms(start),
                "returned_count": len(pb_records),
            },
            "status": {
                "schema_ready": bool(schema.get("ok")),
                "data_ready": data_ready,
                "resolver_version": RECORDS_V1_RULE_VERSION,
                "candidate_count": _count_rows(db, "career_event_candidates", "candidate_type = 'pb_record' AND status = 'candidate'"),
                "message": CAREER_PB_READY_STATUS_MESSAGE if data_ready else CAREER_PB_EMPTY_STATUS_MESSAGE,
            },
        }
    finally:
        if owns_conn:
            db.close()


def get_career_pb_detail(
    record_id: str,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Return one PB record detail without exposing Activity raw facts."""
    start = time.perf_counter()
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        schema = ensure_career_schema(db)
        cursor = db.execute(
            """
            SELECT id, activity_id, sport, pb_type, value, value_unit, improvement,
                   event_date, confidence, source, status, display_metadata_json,
                   evidence_key, source_mode, sport_scope, previous_record_id, resolver_version
            FROM career_pb_records
            WHERE id = ?
            LIMIT 1
            """,
            (str(record_id or ""),),
        )
        rows = [_build_pb_record(row) for row in _rows_to_dicts(cursor)]
        record = rows[0] if rows else None
        return {
            "record": record,
            "metrics": {
                "elapsed_ms": _elapsed_ms(start),
                "returned_count": 1 if record else 0,
            },
            "status": {
                "schema_ready": bool(schema.get("ok")),
                "data_ready": record is not None,
                "resolver_version": RECORDS_V1_RULE_VERSION,
                "message": "纪录详情已生成" if record else "未找到纪录详情",
            },
        }
    finally:
        if owns_conn:
            db.close()


def get_career_pb_history(
    pb_type: str,
    filters: dict[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Return a single PB type history in chronological order."""
    start = time.perf_counter()
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        schema = ensure_career_schema(db)
        raw = filters if isinstance(filters, dict) else {}
        source_mode = str(raw.get("source_mode") or "activity_total").strip() or "activity_total"
        sport_scope = str(raw.get("sport_scope") or "default").strip() or "default"
        cursor = db.execute(
            """
            SELECT id, activity_id, sport, pb_type, value, value_unit, improvement,
                   event_date, confidence, source, status, display_metadata_json,
                   evidence_key, source_mode, sport_scope, previous_record_id, resolver_version
            FROM career_pb_records
            WHERE pb_type = ?
              AND source_mode = ?
              AND sport_scope = ?
              AND status IN ('active', 'superseded', 'invalidated')
            ORDER BY event_date ASC, CAST(value AS INTEGER) DESC, id ASC
            """,
            (str(pb_type or ""), source_mode, sport_scope),
        )
        records = [_build_pb_record(row) for row in _rows_to_dicts(cursor)]
        return {
            "records": records,
            "filters": {
                "pb_type": str(pb_type or ""),
                "source_mode": source_mode,
                "sport_scope": sport_scope,
            },
            "metrics": {
                "elapsed_ms": _elapsed_ms(start),
                "returned_count": len(records),
            },
            "status": {
                "schema_ready": bool(schema.get("ok")),
                "data_ready": bool(records),
                "resolver_version": RECORDS_V1_RULE_VERSION,
                "message": "纪录历史已生成" if records else "暂无纪录历史",
            },
        }
    finally:
        if owns_conn:
            db.close()


def get_career_records(
    filters: dict[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Return V2 Records ViewModel rows without exposing internal evidence payloads."""
    start = time.perf_counter()
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        schema = ensure_career_schema(db)
        normalized_filters = _normalize_records_filters(filters)
        rows = _career_record_rows(db, normalized_filters)
        records = [_build_career_record_view(row) for row in rows]
        candidate_count = _count_rows(db, "career_event_candidates", "candidate_type = 'pb_record' AND status = 'candidate'")
        summary = _summarize_career_records(records, candidate_count=candidate_count)
        response = {
            "records": records,
            "summary": summary,
            "filters": normalized_filters,
            "metrics": {
                "elapsed_ms": _elapsed_ms(start),
                "returned_count": len(records),
                "performance_target_ms": RECORDS_V2_PERFORMANCE_TARGETS_MS["records_list"],
            },
            "status": _records_v2_status(
                schema,
                data_ready=bool(records),
                message="记录已生成" if records else "暂无记录",
                candidate_count=candidate_count,
            ),
        }
        return _records_api_safe(response)
    finally:
        if owns_conn:
            db.close()


def _career_record_activity_summary(conn: sqlite3.Connection, activity_id: str) -> dict[str, Any]:
    if not activity_id or not _table_exists(conn, "activities"):
        return {"activity_id": activity_id}
    select_parts = ["CAST(id AS TEXT) AS id"]
    for column in ("title", "name", "sport_type", "sport", "start_time", "start_time_utc", "distance", "dist_km", "duration", "duration_sec"):
        if _column_exists(conn, "activities", column):
            select_parts.append(column)
        else:
            select_parts.append(f"NULL AS {column}")
    row = conn.execute(
        f"SELECT {', '.join(select_parts)} FROM activities WHERE CAST(id AS TEXT) = ? LIMIT 1",
        (activity_id,),
    ).fetchone()
    if row is None:
        return {"activity_id": activity_id}
    data = dict(row) if isinstance(row, sqlite3.Row) else dict(zip([part.split(" AS ")[-1] for part in select_parts], row))
    distance_km = _safe_float(data.get("dist_km"))
    if distance_km is None:
        meters = _safe_float(data.get("distance"))
        distance_km = round(meters / 1000.0, 2) if meters is not None else None
    duration_sec = _safe_int(data.get("duration_sec"))
    if duration_sec <= 0:
        duration_sec = _safe_int(data.get("duration"))
    sport = _activity_sport_for_record_dispatch(data)
    return {
        "activity_id": activity_id,
        "title": str(data.get("title") or data.get("name") or ""),
        "sport": sport,
        "sport_label": RECORD_SPORT_LABELS.get(sport, _career_sport_label(sport)),
        "event_date": str(data.get("start_time") or data.get("start_time_utc") or "")[:10],
        "distance_display": f"{distance_km:g} km" if distance_km is not None else "",
        "duration_display": _format_duration_seconds(duration_sec) if duration_sec > 0 else "",
    }


def get_career_record_detail(
    payload: dict[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Return one V2 record detail ViewModel."""
    start = time.perf_counter()
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        schema = ensure_career_schema(db)
        raw = payload if isinstance(payload, dict) else {}
        record_id = str(raw.get("record_id") or raw.get("id") or "").strip()
        filters = {
            "sport": "all",
            "record_key": str(raw.get("record_key") or "all").strip() or "all",
            "family": "all",
            "scope_hash": str(raw.get("scope_hash") or "all").strip() or "all",
            "status": str(raw.get("status") or "all").strip() or "all",
            "year": None,
        }
        rows = _career_record_rows(db, filters)
        if record_id:
            rows = [row for row in rows if str(row.get("id") or "") == record_id]
        record = _build_career_record_view(rows[0]) if rows else None
        response = {
            "record": record,
            "activity_summary": _career_record_activity_summary(db, str((record or {}).get("activity_id") or "")) if record else {},
            "related": {
                "history_api": "get_career_record_history",
                "curve_api": "get_career_record_curve",
                "activity_link": {"activity_id": str((record or {}).get("activity_id") or ""), "source": "career"} if record else {},
            },
            "metrics": {"elapsed_ms": _elapsed_ms(start), "returned_count": 1 if record else 0},
            "status": _records_v2_status(
                schema,
                data_ready=record is not None,
                state="ready" if record else "error",
                message="纪录详情已生成" if record else "纪录不存在",
            ),
        }
        return _records_api_safe(response)
    finally:
        if owns_conn:
            db.close()


def get_career_record_history(
    filters: dict[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Return V2 history and backend-computed history summary."""
    start = time.perf_counter()
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        schema = ensure_career_schema(db)
        raw = filters if isinstance(filters, dict) else {}
        record_key = str(raw.get("record_key") or raw.get("pb_type") or "").strip()
        scope_hash = str(raw.get("scope_hash") or "all").strip() or "all"
        statuses = ["active", "superseded"]
        if bool(raw.get("include_invalidated")):
            statuses.append("invalidated")
        query_filters = {
            "sport": "all",
            "record_key": record_key or "all",
            "family": "all",
            "scope_hash": scope_hash,
            "status": "all",
            "year": None,
        }
        rows = [
            row
            for row in _career_record_rows(db, query_filters)
            if str(row.get("status") or "") in statuses
        ]
        rows.sort(key=lambda row: (str(row.get("event_date") or ""), str(row.get("id") or "")))
        records = [_build_career_record_view(row) for row in rows]
        definition = get_record_definition(record_key) if record_key else (_record_definition_for_row(rows[0]) if rows else None)
        comparison = definition.comparison if definition else "lower_is_better"
        axis_direction = _record_axis_direction(definition) if definition else ("lower" if comparison == "lower_is_better" else "higher")
        first = records[0]["metric"] if records else {"value": None, "unit": "", "display": ""}
        active_records = [record for record in records if record.get("status") == "active"]
        current = (active_records[-1] if active_records else (records[-1] if records else {})).get("metric", {"value": None, "unit": "", "display": ""})
        total_improvement_value = None
        if first.get("value") is not None and current.get("value") is not None:
            total_improvement_value = (
                float(first["value"]) - float(current["value"])
                if comparison == "lower_is_better"
                else float(current["value"]) - float(first["value"])
            )
        unit = str(current.get("unit") or first.get("unit") or "")
        history_summary = {
            "record_key": record_key,
            "scope_hash": scope_hash,
            "axis_direction": axis_direction,
            "comparison": comparison,
            "first_value": first,
            "current_value": current,
            "total_improvement": _record_improvement_view(total_improvement_value, unit),
            "record_count": len(records),
            "invalidated_count": sum(1 for record in records if record.get("status") == "invalidated"),
            "last_record_at": str((records[-1] if records else {}).get("event_date") or ""),
        }
        chart = {
            "x_axis": {"type": "time", "label": "日期"},
            "y_axis": {"unit": unit, "direction": axis_direction},
            "points": [
                {
                    "x": record.get("event_date"),
                    "y": (record.get("metric") or {}).get("value"),
                    "record_id": record.get("id"),
                    "status": record.get("status"),
                }
                for record in records
            ],
        }
        response = {
            "records": records,
            "history_summary": history_summary,
            "chart": chart,
            "filters": {"record_key": record_key, "scope_hash": scope_hash, "include_invalidated": bool(raw.get("include_invalidated"))},
            "metrics": {
                "elapsed_ms": _elapsed_ms(start),
                "returned_count": len(records),
                "performance_target_ms": RECORDS_V2_PERFORMANCE_TARGETS_MS["record_history"],
            },
            "status": _records_v2_status(schema, data_ready=bool(records), message="纪录历史已生成" if records else "暂无纪录历史"),
        }
        return _records_api_safe(response)
    finally:
        if owns_conn:
            db.close()


def get_career_record_curve(
    payload: dict[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Return safe derived curve cache ViewModel."""
    start = time.perf_counter()
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        schema = ensure_career_schema(db)
        raw = payload if isinstance(payload, dict) else {}
        where_parts = ["invalidated_at IS NULL"]
        params: list[Any] = []
        for key in ("activity_id", "curve_type", "scope_hash"):
            value = str(raw.get(key) or "").strip()
            if value:
                where_parts.append(f"{key} = ?")
                params.append(value)
        row = db.execute(
            f"""
            SELECT id, activity_id, sport, curve_type, source_mode, scope_hash,
                   input_fingerprint, algorithm_version, curve_json, quality_json,
                   generated_at
            FROM career_record_curve_cache
            WHERE {' AND '.join(where_parts)}
            ORDER BY generated_at DESC, updated_at DESC
            LIMIT 1
            """,
            tuple(params),
        ).fetchone()
        curve = None
        if row is not None:
            data = dict(row) if isinstance(row, sqlite3.Row) else dict(zip(
                ["id", "activity_id", "sport", "curve_type", "source_mode", "scope_hash", "input_fingerprint", "algorithm_version", "curve_json", "quality_json", "generated_at"],
                row,
            ))
            curve_json = _sanitize_public_metadata(_json_loads_object(data.get("curve_json")))
            quality_json = _sanitize_public_metadata(_json_loads_object(data.get("quality_json")))
            curve = {
                "id": str(data.get("id") or ""),
                "activity_id": str(data.get("activity_id") or ""),
                "curve_type": str(data.get("curve_type") or ""),
                "scope_hash": str(data.get("scope_hash") or ""),
                "algorithm_version": str(data.get("algorithm_version") or ""),
                "input_fingerprint": str(data.get("input_fingerprint") or ""),
                "source_mode": str(data.get("source_mode") or ""),
                "points": curve_json.get("points") if isinstance(curve_json.get("points"), list) else curve_json.get("anchors", []),
                "anchors": curve_json.get("anchors") if isinstance(curve_json.get("anchors"), list) else [],
                "quality": quality_json or {"state": "ready", "reason_codes": []},
                "generated_at": str(data.get("generated_at") or ""),
            }
        response = {
            "curve": curve,
            "metrics": {
                "elapsed_ms": _elapsed_ms(start),
                "returned_count": 1 if curve else 0,
                "performance_target_ms": RECORDS_V2_PERFORMANCE_TARGETS_MS["record_curve"],
                "cache_hit": bool(curve),
                "cache_miss": not bool(curve),
            },
            "status": _records_v2_status(schema, data_ready=curve is not None, state="ready" if curve else "empty", message="曲线已生成" if curve else "曲线尚未生成"),
        }
        return _records_api_safe(response)
    finally:
        if owns_conn:
            db.close()


def _build_record_candidate_view(row: dict[str, Any]) -> dict[str, Any]:
    evidence = _sanitize_public_metadata(_json_loads_object(row.get("evidence_json")))
    record_evidence = evidence.get("record_evidence") if isinstance(evidence.get("record_evidence"), dict) else {}
    record_key = str(evidence.get("record_key") or record_evidence.get("record_key") or "")
    definition = get_record_definition(record_key)
    metric = record_evidence.get("metric") if isinstance(record_evidence.get("metric"), dict) else {}
    scope = record_evidence.get("scope") if isinstance(record_evidence.get("scope"), dict) else {}
    quality = record_evidence.get("quality") if isinstance(record_evidence.get("quality"), dict) else {}
    confidence = _safe_float(row.get("confidence")) or _safe_float(quality.get("confidence")) or 0.0
    activity_id = str(row.get("activity_id") or record_evidence.get("activity_id") or "")
    return {
        "id": str(row.get("id") or ""),
        "activity_id": activity_id,
        "record_key": record_key,
        "display_name": definition.display_name if definition else str(row.get("title") or record_key),
        "sport": str(record_evidence.get("sport") or (definition.sport if definition else "")),
        "sport_label": RECORD_SPORT_LABELS.get(str(record_evidence.get("sport") or ""), _career_sport_label(record_evidence.get("sport"))),
        "metric": {
            "name": str(metric.get("name") or ""),
            "value": _safe_float(metric.get("value")),
            "unit": str(metric.get("unit") or ""),
            "display": _record_metric_display(metric.get("value"), metric.get("unit")),
        },
        "scope": {
            "scope_hash": str(record_evidence.get("scope_hash") or evidence.get("scope_hash") or ""),
            "scope_key": str(record_evidence.get("scope_key") or ""),
            "labels": [_scope_label(key, value) for key, value in sorted(scope.items())],
            "dimensions": scope,
        },
        "quality": {
            "confidence": confidence,
            "confidence_band": _record_confidence_level(confidence),
            "reason_codes": list(quality.get("reason_codes") or evidence.get("reason_codes") or []),
            "message_key": str(quality.get("message_key") or "record_quality_review"),
            "can_user_confirm": True,
        },
        "candidate_state": str(row.get("status") or "candidate"),
        "created_at": str(row.get("updated_at") or ""),
        "detail_link": {"activity_id": activity_id, "source": "career"},
    }


def get_career_record_candidates(
    filters: dict[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Return V2-safe record candidate ViewModels."""
    start = time.perf_counter()
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        schema = ensure_career_schema(db)
        raw = filters if isinstance(filters, dict) else {}
        status = str(raw.get("status") or "candidate").strip() or "candidate"
        record_key = str(raw.get("record_key") or "all").strip() or "all"
        sport = str(raw.get("sport") or "all").strip() or "all"
        where_parts = ["candidate_type = 'pb_record'"]
        params: list[Any] = []
        if status != "all":
            where_parts.append("status = ?")
            params.append(status)
        cursor = db.execute(
            f"""
            SELECT id, activity_id, candidate_type, title, evidence_json, confidence, status, updated_at
            FROM career_event_candidates
            WHERE {' AND '.join(where_parts)}
            ORDER BY updated_at DESC, confidence DESC, id DESC
            """,
            tuple(params),
        )
        candidates = [_build_record_candidate_view(row) for row in _rows_to_dicts(cursor)]
        if record_key != "all":
            candidates = [candidate for candidate in candidates if candidate.get("record_key") == record_key]
        if sport != "all":
            candidates = [candidate for candidate in candidates if candidate.get("sport") == sport]
        by_sport: dict[str, int] = {}
        by_reason_code: dict[str, int] = {}
        for candidate in candidates:
            _increment_counter(by_sport, candidate.get("sport"))
            for code in ((candidate.get("quality") or {}).get("reason_codes") or []):
                _increment_counter(by_reason_code, code)
        response = {
            "candidates": candidates,
            "summary": {"total": len(candidates), "by_sport": by_sport, "by_reason_code": by_reason_code},
            "filters": {"sport": sport, "record_key": record_key, "status": status},
            "metrics": {
                "elapsed_ms": _elapsed_ms(start),
                "returned_count": len(candidates),
                "performance_target_ms": RECORDS_V2_PERFORMANCE_TARGETS_MS["record_candidates"],
            },
            "status": _records_v2_status(schema, data_ready=bool(candidates), message="候选纪录已生成" if candidates else "暂无候选纪录", candidate_count=len(candidates)),
        }
        return _records_api_safe(response)
    finally:
        if owns_conn:
            db.close()


def decide_career_record_candidate(
    payload: dict[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Confirm/reject a V2 record candidate; fallback to V1 PB candidate handler for legacy payloads."""
    raw = payload if isinstance(payload, dict) else {}
    candidate_id = str(raw.get("candidate_id") or raw.get("id") or "").strip()
    action = str(raw.get("action") or raw.get("decision") or "").strip().lower()
    if not candidate_id:
        return {"ok": False, "code": "RECORD_CANDIDATE_NOT_FOUND", "msg": "候选不存在", "data": None}
    if action not in {"confirm", "reject"}:
        return {"ok": False, "code": "RECORD_CANDIDATE_HARD_BLOCKED", "msg": "候选操作无效", "data": None}
    result = decide_career_record_v2_candidate(candidate_id, action, conn=conn)
    if not result.get("ok") and result.get("code") == "invalid_candidate":
        result = decide_career_pb_candidate(candidate_id, action, conn=conn)
    return result


RECORDS_DOWNSTREAM_FORMAL_RECORD_STATUSES = {"active", "superseded"}
RECORDS_DOWNSTREAM_EXCLUDED_CATALOG_STATES = {"analysis_only", "model_only", "unavailable"}
RECORDS_DOWNSTREAM_FORMAL_EVENT_TYPES = {"activated", "activated_from_rebuild", "user_confirmed"}
RECORDS_DOWNSTREAM_EXCLUDED_EVENT_TYPES = {
    "candidate_created",
    "detected",
    "ignored",
    "recalculated",
    "user_rejected",
}


def _records_downstream_record_item(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(record.get("id") or ""),
        "activity_id": str(record.get("activity_id") or ""),
        "record_key": str(record.get("record_key") or record.get("pb_type") or ""),
        "sport": str(record.get("sport") or ""),
        "family": str(record.get("family") or ""),
        "status": str(record.get("status") or ""),
        "catalog_state": str(record.get("catalog_state") or ""),
        "event_date": str(record.get("event_date") or ""),
        "detail_link": {
            "activity_id": str(record.get("activity_id") or ""),
            "source": "career",
            "record_id": str(record.get("id") or ""),
        },
    }


def _records_downstream_formal_records(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = _career_record_rows(
        conn,
        {
            "sport": "all",
            "record_key": "all",
            "family": "all",
            "scope_hash": "all",
            "status": "all",
            "year": None,
        },
    )
    records: list[dict[str, Any]] = []
    for row in rows:
        record = _build_career_record_view(row)
        status = str(record.get("status") or "")
        family = str(record.get("family") or "")
        catalog_state = str(record.get("catalog_state") or "")
        if status not in RECORDS_DOWNSTREAM_FORMAL_RECORD_STATUSES:
            continue
        if catalog_state in RECORDS_DOWNSTREAM_EXCLUDED_CATALOG_STATES:
            continue
        if family in {"analysis_curve", "model_estimate"}:
            continue
        records.append(_records_downstream_record_item(record))
    return records


def _records_downstream_formal_events(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    if not _table_exists(conn, "career_record_events"):
        return []
    cursor = conn.execute(
        """
        SELECT id, record_id, activity_id, event_type, pb_type, record_key,
               scope_hash, decision, source, event_at
        FROM career_record_events
        ORDER BY event_at ASC, id ASC
        """
    )
    events: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for row in _rows_to_dicts(cursor):
        event_id = str(row.get("id") or "")
        if not event_id or event_id in seen_ids:
            continue
        seen_ids.add(event_id)
        event_type = str(row.get("event_type") or "")
        record_id = str(row.get("record_id") or "")
        if event_type not in RECORDS_DOWNSTREAM_FORMAL_EVENT_TYPES:
            continue
        if not record_id:
            continue
        record_key = str(row.get("record_key") or row.get("pb_type") or "")
        definition = get_record_definition(record_key)
        family = _record_definition_family(definition) if definition else ""
        if family in {"analysis_curve", "model_estimate"}:
            continue
        events.append(
            {
                "id": event_id,
                "record_id": record_id,
                "activity_id": str(row.get("activity_id") or ""),
                "event_type": event_type,
                "record_key": record_key,
                "sport": definition.sport if definition else "",
                "family": family,
                "scope_hash": str(row.get("scope_hash") or ""),
                "decision": str(row.get("decision") or ""),
                "source": str(row.get("source") or ""),
                "event_at": str(row.get("event_at") or ""),
                "detail_link": {
                    "activity_id": str(row.get("activity_id") or ""),
                    "source": "career",
                    "record_id": record_id,
                },
            }
        )
    return events


def _records_downstream_count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        _increment_counter(counts, item.get(key))
    return counts


def get_career_records_downstream_integration(
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Return a safe integration guard for ACS modules that consume formal records.

    This helper is intentionally a summary/contract surface. It does not promote
    candidates, does not read curve cache payloads, and does not infer races or
    achievements from raw record evidence.
    """
    start = time.perf_counter()
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        schema = ensure_career_schema(db)
        formal_records = _records_downstream_formal_records(db)
        formal_events = _records_downstream_formal_events(db)
        candidate_count = _count_rows(db, "career_event_candidates", "candidate_type = 'pb_record' AND status = 'candidate'")
        curve_cache_count = _count_rows(db, "career_record_curve_cache", "invalidated_at IS NULL")
        excluded_event_count = 0
        if _table_exists(db, "career_record_events"):
            placeholders = ", ".join("?" for _ in RECORDS_DOWNSTREAM_EXCLUDED_EVENT_TYPES)
            excluded_event_count = _safe_int(
                db.execute(
                    f"SELECT COUNT(*) FROM career_record_events WHERE event_type IN ({placeholders})",
                    tuple(sorted(RECORDS_DOWNSTREAM_EXCLUDED_EVENT_TYPES)),
                ).fetchone()[0]
            )
        response = {
            "overview": {
                "formal_record_count": len(formal_records),
                "eligible_statuses": sorted(RECORDS_DOWNSTREAM_FORMAL_RECORD_STATUSES),
                "by_sport": _records_downstream_count_by(formal_records, "sport"),
                "by_family": _records_downstream_count_by(formal_records, "family"),
                "records": formal_records,
            },
            "timeline": {
                "formal_event_count": len(formal_events),
                "formal_event_types": sorted(RECORDS_DOWNSTREAM_FORMAL_EVENT_TYPES),
                "events": formal_events,
                "idempotency_key": "career_record_events.id",
            },
            "race_archive": {
                "consumes_records": False,
                "record_derived_race_count": 0,
                "boundary": "race_archive_uses_race_resolver_only",
            },
            "achievement": {
                "formal_trigger_count": len(formal_events),
                "trigger_event_types": sorted(RECORDS_DOWNSTREAM_FORMAL_EVENT_TYPES),
                "candidate_triggers": 0,
                "cache_curve_triggers": 0,
            },
            "excluded_sources": {
                "candidate_count": candidate_count,
                "curve_cache_count": curve_cache_count,
                "excluded_event_count": excluded_event_count,
                "excluded_event_types": sorted(RECORDS_DOWNSTREAM_EXCLUDED_EVENT_TYPES),
                "excluded_catalog_states": sorted(RECORDS_DOWNSTREAM_EXCLUDED_CATALOG_STATES),
                "model_and_analysis_records": "excluded_by_family_and_catalog_state",
            },
            "metrics": {"elapsed_ms": _elapsed_ms(start)},
            "status": _records_v2_status(
                schema,
                data_ready=bool(formal_records or formal_events),
                message="Records downstream integration summary generated",
            ),
        }
        return _records_api_safe(response)
    finally:
        if owns_conn:
            db.close()


def rebuild_career_records(
    payload: dict[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """V2 rebuild wrapper; dry-run is the default safe behavior."""
    raw = payload if isinstance(payload, dict) else {}
    dry_run = bool(raw.get("dry_run", True))
    resolver_version = str(raw.get("resolver_version") or RECORDS_V2_RULE_VERSION)
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        result = rebuild_career_records_v2(
            db,
            dry_run=dry_run,
            resolver_version=resolver_version,
            batch_size=int(raw.get("batch_size") or 500),
            max_activities=raw.get("max_activities"),
            cancel_after=raw.get("cancel_after"),
        )
        if owns_conn and not dry_run:
            db.commit()
        return _records_api_safe(result)
    except Exception:
        if owns_conn:
            db.rollback()
        raise
    finally:
        if owns_conn:
            db.close()


def get_career_record_rebuild_status(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = payload if isinstance(payload, dict) else {}
    run_id = str(raw.get("run_id") or "").strip()
    return {
        "run_id": run_id,
        "state": "running" if _RECORDS_REBUILD_IN_PROGRESS else "idle",
        "dry_run": True,
        "started_at": None,
        "finished_at": None,
        "progress": {"scanned": 0, "total": 0},
        "summary": {},
        "status": {
            "schema_ready": True,
            "data_ready": False,
            "state": "rebuilding" if _RECORDS_REBUILD_IN_PROGRESS else "ready",
            "message": "重建中" if _RECORDS_REBUILD_IN_PROGRESS else "暂无运行中的重建",
        },
    }


def get_career_record_events(
    filters: dict[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Return append-only PB record events for idempotent frontend consumption."""
    start = time.perf_counter()
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        schema = ensure_career_schema(db)
        raw = filters if isinstance(filters, dict) else {}
        record_id = str(raw.get("record_id") or "").strip()
        pb_type = str(raw.get("pb_type") or raw.get("record_key") or "").strip()
        scope_hash = str(raw.get("scope_hash") or "").strip()
        run_id = str(raw.get("run_id") or "").strip()
        decision = str(raw.get("decision") or "").strip()
        event_type = str(raw.get("event_type") or "").strip()
        where_parts = ["1=1"]
        params: list[Any] = []
        if record_id:
            where_parts.append("record_id = ?")
            params.append(record_id)
        if pb_type:
            where_parts.append("pb_type = ?")
            params.append(pb_type)
        if scope_hash:
            where_parts.append("scope_hash = ?")
            params.append(scope_hash)
        if run_id:
            where_parts.append("run_id = ?")
            params.append(run_id)
        if decision:
            where_parts.append("decision = ?")
            params.append(decision)
        if event_type:
            where_parts.append("event_type = ?")
            params.append(event_type)
        cursor = db.execute(
            f"""
            SELECT id, record_id, activity_id, pb_type, event_type, event_at,
                   evidence_key, resolver_version, source, record_key, scope_hash,
                   scope_key, run_id, decision, reason_codes_json, payload_json,
                   created_at
            FROM career_record_events
            WHERE {' AND '.join(where_parts)}
            ORDER BY event_at ASC, id ASC
            """,
            tuple(params),
        )
        events = []
        for row in _rows_to_dicts(cursor):
            payload = _sanitize_public_metadata(_json_loads_object(row.get("payload_json")))
            events.append({
                "id": str(row.get("id") or ""),
                "record_id": str(row.get("record_id") or ""),
                "activity_id": str(row.get("activity_id") or ""),
                "pb_type": str(row.get("pb_type") or ""),
                "event_type": str(row.get("event_type") or ""),
                "event_at": str(row.get("event_at") or ""),
                "evidence_key": str(row.get("evidence_key") or ""),
                "resolver_version": str(row.get("resolver_version") or ""),
                "source": str(row.get("source") or ""),
                "record_key": str(row.get("record_key") or row.get("pb_type") or ""),
                "scope_hash": str(row.get("scope_hash") or ""),
                "scope_key": str(row.get("scope_key") or ""),
                "run_id": str(row.get("run_id") or ""),
                "decision": str(row.get("decision") or ""),
                "reason_codes": _json_loads_list(row.get("reason_codes_json")),
                "payload": payload,
                "created_at": str(row.get("created_at") or ""),
            })
        return {
            "events": events,
            "filters": {
                "record_id": record_id,
                "pb_type": pb_type,
                "scope_hash": scope_hash,
                "run_id": run_id,
                "decision": decision,
                "event_type": event_type,
            },
            "metrics": {
                "elapsed_ms": _elapsed_ms(start),
                "returned_count": len(events),
            },
            "status": {
                "schema_ready": bool(schema.get("ok")),
                "data_ready": bool(events),
                "message": "纪录事件已生成" if events else "暂无纪录事件",
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


def _normalize_memory_gallery_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    raw = filters if isinstance(filters, dict) else {}
    sport = str(raw.get("sport") or "all").strip().lower() or "all"
    if sport not in {"all", "running", "cycling"}:
        sport = "all"
    year = _safe_activity_year(raw.get("year"))
    return {
        "sport": sport,
        "year": year,
    }


def _memory_gallery_cover_from_photos(photos: list[dict[str, Any]]) -> dict[str, Any]:
    if not photos:
        return {
            "has_photo": False,
            "image_ref": "",
            "photo_id": "",
        }
    first = photos[0]
    image_ref = str(first.get("thumbnail_url") or first.get("preview_url") or "")
    if not image_ref.startswith("data:image/"):
        image_ref = ""
    return {
        "has_photo": bool(image_ref),
        "image_ref": image_ref,
        "photo_id": str(first.get("id") or ""),
    }


def _empty_memory_gallery_footprint() -> dict[str, str]:
    return {
        "region_key": "",
        "country_code": "",
        "country": "",
        "name": "",
        "level": "",
        "map_mode": "",
    }


def _memory_gallery_footprint_record(region: dict[str, Any] | None) -> dict[str, str]:
    if not region:
        return _empty_memory_gallery_footprint()
    return {
        "region_key": str(region.get("region_key") or ""),
        "country_code": str(region.get("country_code") or ""),
        "country": str(region.get("country") or ""),
        "name": str(region.get("name") or ""),
        "level": str(region.get("level") or ""),
        "map_mode": str(region.get("map_mode") or ""),
    }


def _memory_gallery_activity_region_row(conn: sqlite3.Connection, activity_id: str) -> dict[str, Any]:
    if not activity_id or not _table_exists(conn, "activities"):
        return {}
    columns = (
        "region",
        "region_city",
        "region_country",
        "region_display",
        "region_state",
        "state",
        "province",
        "city",
        "cityName",
        "country",
        "countryName",
    )
    select_sql = ", ".join(
        f"{column} AS {column}" if _column_exists(conn, "activities", column) else f"NULL AS {column}"
        for column in columns
    )
    row = conn.execute(
        f"SELECT {select_sql} FROM activities WHERE id = ? LIMIT 1",
        (activity_id,),
    ).fetchone()
    return dict(row) if isinstance(row, sqlite3.Row) else (dict(zip(columns, row)) if row else {})


def _memory_gallery_album_footprint(conn: sqlite3.Connection, race: dict[str, Any]) -> dict[str, str]:
    activity_id = str(race.get("activity_id") or "").strip()
    row = _memory_gallery_activity_region_row(conn, activity_id)
    region = _resolve_career_footprint_region(row)
    if region:
        return _memory_gallery_footprint_record(region)

    location = race.get("location") if isinstance(race.get("location"), dict) else {}
    fallback_row = {
        "region_city": str(location.get("city") or race.get("city") or ""),
        "city": str(location.get("city") or race.get("city") or ""),
        "region_country": str(location.get("country") or race.get("country") or ""),
        "country": str(location.get("country") or race.get("country") or ""),
        "region": str(location.get("region") or location.get("state") or ""),
        "province": str(location.get("province") or location.get("state") or ""),
        "region_display": str(location.get("display") or ""),
    }
    return _memory_gallery_footprint_record(_resolve_career_footprint_region(fallback_row))


def _build_memory_gallery_album(race: dict[str, Any], photos: list[dict[str, Any]], footprint: dict[str, str] | None = None) -> dict[str, Any]:
    race_id = str(race.get("id") or "")
    activity_id = str(race.get("activity_id") or "")
    title = str(race.get("race_title") or race.get("name") or "未命名赛事")
    location = race.get("location") if isinstance(race.get("location"), dict) else {}
    display_location = str(location.get("display") or race.get("city") or "")
    return {
        "id": race_id or f"album:activity:{activity_id}",
        "race_id": race_id,
        "activity_id": activity_id,
        "title": title,
        "event_type": str(race.get("event_type") or ""),
        "event_type_label": str(race.get("event_type_label") or ""),
        "sport": str(race.get("sport") or ""),
        "sport_label": str(race.get("sport_label") or ""),
        "event_date": str(race.get("event_date") or ""),
        "display_date": str(race.get("display_date") or ""),
        "city": str(race.get("city") or ""),
        "location": {
            "city": str(location.get("city") or race.get("city") or ""),
            "display": display_location,
        },
        "cover": _memory_gallery_cover_from_photos(photos),
        "photos": photos,
        "photo_count": len(photos),
        "is_empty": not bool(photos),
        "footprint": footprint or _empty_memory_gallery_footprint(),
        "detail_link": {
            "activity_id": activity_id,
            "source": "career",
        } if activity_id else {"activity_id": "", "source": "career"},
    }


def _summarize_memory_gallery_albums(albums: list[dict[str, Any]]) -> dict[str, int]:
    photo_count = sum(int(album.get("photo_count") or 0) for album in albums)
    empty_album_count = sum(1 for album in albums if bool(album.get("is_empty")))
    cover_count = sum(
        1
        for album in albums
        if isinstance(album.get("cover"), dict) and bool(album["cover"].get("has_photo"))
    )
    return {
        "album_count": len(albums),
        "photo_count": photo_count,
        "empty_album_count": empty_album_count,
        "cover_count": cover_count,
    }


def get_career_memory_gallery(
    filters: dict[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Return race-based photo albums without exposing storage references."""
    owns_conn = conn is None
    db = conn or _connect_default()
    try:
        schema = ensure_career_schema(db)
        normalized_filters = _normalize_memory_gallery_filters(filters)
        race_payload = get_career_races(normalized_filters, conn=db)
        races = race_payload.get("races") if isinstance(race_payload, dict) else []
        albums: list[dict[str, Any]] = []
        for race in races if isinstance(races, list) else []:
            if not isinstance(race, dict):
                continue
            activity_id = str(race.get("activity_id") or "").strip()
            photos = _activity_race_photo_items(db, activity_id) if activity_id else []
            albums.append(_build_memory_gallery_album(race, photos, _memory_gallery_album_footprint(db, race)))
        summary = _summarize_memory_gallery_albums(albums)
        data_ready = bool(albums)
        return {
            "albums": albums,
            "summary": summary,
            "filters": normalized_filters,
            "status": {
                "schema_ready": bool(schema.get("ok")),
                "data_ready": data_ready,
                "message": CAREER_MEMORY_GALLERY_READY_STATUS_MESSAGE if data_ready else CAREER_MEMORY_GALLERY_EMPTY_STATUS_MESSAGE,
            },
        }
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
                   storage_ref, metadata_json, created_at
            FROM career_memory_items
            WHERE id = ?
            """,
            (memory_id,),
        )
        row = cursor.fetchone()
        names = [column[0] for column in cursor.description or []]
        if owns_conn:
            db.commit()
        built_item = _build_race_banner_photo_item(dict(zip(names, row))) if row is not None else None
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
        _annotate_career_season_report_updates(seasons, conn=db)
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
        summary = {
            "career_start_year": activity_summary["career_start_year"],
            "activity_count": activity_summary["activity_count"],
            "race_count": race_count,
            "pb_count": pb_count,
            "achievement_count": achievement_count,
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
                    for key in ("activity_count", "race_count", "pb_count", "achievement_count")
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

        summary = overview.get("summary") if isinstance(overview.get("summary"), dict) else {}
        pb_summary = [
            _sanitize_snapshot_pb(record)
            for record in (pb_payload.get("pb_records") or [])[:6]
        ]
        records_summary = _build_records_snapshot_summary(db, pb_payload.get("pb_records") or [])
        major_achievements = [
            _sanitize_snapshot_achievement(item)
            for item in (achievement_payload.get("achievements") or [])[:8]
        ]
        timeline_digest = _flatten_timeline_digest(timeline_payload, limit=12)
        data_ready = any(
            bool(value)
            for value in (
                summary.get("activity_count"),
                summary.get("race_count"),
                summary.get("pb_count"),
                summary.get("achievement_count"),
                pb_summary,
                major_achievements,
                timeline_digest,
                records_summary.get("current_records"),
                records_summary.get("formal_records"),
                records_summary.get("recent_refreshes"),
                records_summary.get("candidate_count"),
                (records_summary.get("curve_availability") or {}).get("available_count"),
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
                "covered_city_count": int(summary.get("covered_city_count") or 0),
                "total_distance_km": summary.get("total_distance_km"),
            },
            "primary_sport": _build_primary_sport_summary(db),
            "pb_summary": pb_summary,
            "records_summary": records_summary,
            "major_achievements": major_achievements,
            "timeline_digest": timeline_digest,
            "status": {
                "schema_ready": bool(
                    (overview.get("status") or {}).get("schema_ready")
                    and (pb_payload.get("status") or {}).get("schema_ready")
                    and (achievement_payload.get("status") or {}).get("schema_ready")
                    and (timeline_payload.get("status") or {}).get("schema_ready")
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
    if covered_city_count:
        highlights.append(f"已覆盖城市 {covered_city_count} 个")
    if total_distance_km is not None:
        highlights.append(f"累计距离 {total_distance_km} km")
    return highlights[:6]


def _career_insight_record_highlights(records_summary: dict[str, Any]) -> list[str]:
    highlights: list[str] = []
    candidate_count = int(records_summary.get("candidate_count") or 0)
    current_records = records_summary.get("current_records") or []
    formal_records = records_summary.get("formal_records") or []
    recent_refreshes = records_summary.get("recent_refreshes") or []
    evolution = records_summary.get("evolution_summary") if isinstance(records_summary.get("evolution_summary"), dict) else {}
    curve_availability = records_summary.get("curve_availability") if isinstance(records_summary.get("curve_availability"), dict) else {}
    refresh_count = int(evolution.get("refresh_event_count") or 0)
    curve_available_count = int(curve_availability.get("available_count") or 0)
    if formal_records:
        highlights.append(f"当前纪录 {len(formal_records)} 项")
    elif current_records:
        highlights.append(f"当前纪录 {len(current_records)} 项")
    if candidate_count:
        highlights.append(f"待确认纪录候选 {candidate_count} 项")
    if recent_refreshes:
        highlights.append(f"最近纪录刷新 {len(recent_refreshes)} 条")
    if refresh_count:
        highlights.append(f"纪录刷新频率事实 {refresh_count} 次")
    if curve_available_count:
        highlights.append(f"分析曲线可用 {curve_available_count} 类，仅作趋势参考")
    return highlights[:3]


def _build_fallback_career_insight(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    clean_snapshot = snapshot if isinstance(snapshot, dict) else {}
    summary = clean_snapshot.get("summary") if isinstance(clean_snapshot.get("summary"), dict) else {}
    records_summary = clean_snapshot.get("records_summary") if isinstance(clean_snapshot.get("records_summary"), dict) else {}
    has_data = bool((clean_snapshot.get("status") or {}).get("data_ready"))
    highlights = _career_insight_highlights(summary)[:4]
    highlights.extend(_career_insight_record_highlights(records_summary))
    highlights = highlights[:6]
    if not highlights:
        highlights = ["暂无足够的运动生涯数据用于生成长期洞察"]
    return {
        "mode": "fallback",
        "title": "运动生涯洞察准备中",
        "summary": "已生成安全的运动生涯快照，AI 洞察将在后续版本开启。" if has_data else "暂无足够的运动生涯数据，后续会基于 Career Snapshot 生成长期总结。",
        "highlights": highlights,
        "next_steps": [
            "继续完善赛事、PB、成就与活动数据",
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
        result = {
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
        if owns_conn:
            db.commit()
        return result
    except Exception:
        if owns_conn:
            db.rollback()
        raise
    finally:
        if owns_conn:
            db.close()
