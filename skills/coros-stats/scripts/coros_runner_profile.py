#!/usr/bin/env python3
"""
coros_runner_profile.py - COROS MCP-only runner profile aggregator.

Data source:
1. COROS MCP tools only.

Output: JSON array, each item is {"metric": "...", "value": ..., "note"?: "..."}.
Sync mode prints only the JSON array for FitVault ingestion.
"""
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


SKILL_DIR = Path(__file__).parent
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from subprocess_utils import run_hidden

KEEPALIVE = SKILL_DIR / "coros-mcp-keepalive.js"

FIELDS = [
    "username", "age", "gender", "height_cm", "weight_kg",
    "body_fat_percent", "body_water_percent", "bone_mass_kg", "muscle_mass_kg",
    "metabolic_age", "visceral_fat",
    "resting_heart_rate", "max_heart_rate", "hrv",
    "avg_sleep_hours", "avg_bedtime",
    "vo2_max", "lactate_threshold_hr", "lactate_threshold_pace",
    "ftp_watts",
    "1km_pb", "1mile_pb", "5km_pb", "10km_pb", "half_marathon_pb", "full_marathon_pb",
    "longest_run_km", "total_run_km",
    "race_predict_5k", "race_predict_10k", "race_predict_half", "race_predict_full",
    "longest_hike_km", "total_hike_km",
    "longest_ride_time", "cycling_40km_time", "cycling_80km_time",
    "longest_cycle_km", "total_cycle_km",
    "longest_swim_distance_m", "total_swim_km", "swimming_100m_pb",
]

UNAVAILABLE = {
    "body_fat_percent": "当前 COROS MCP 工具目录未确认返回体脂字段",
    "body_water_percent": "当前 COROS MCP 工具目录未确认返回体水分字段",
    "bone_mass_kg": "当前 COROS MCP 工具目录未确认返回骨量字段",
    "muscle_mass_kg": "当前 COROS MCP 工具目录未确认返回肌肉量字段",
    "metabolic_age": "当前 COROS MCP 工具目录未确认返回代谢年龄字段",
    "visceral_fat": "当前 COROS MCP 工具目录未确认返回内脏脂肪字段",
    "max_heart_rate": "当前 COROS MCP 工具 schema 未确认最大心率字段，需后续真实样本验证",
    "lactate_threshold_hr": "当前 COROS MCP 工具 schema 未确认乳酸阈值心率字段，需后续真实样本验证",
    "ftp_watts": "当前 COROS MCP 工具目录未确认返回 FTP 字段，需后续 FIT 样本验证",
    "1mile_pb": "当前 MCP 画像链路仅能按运动记录窗口兜底，全部历史 PB 留待 FIT 下载增强",
    "half_marathon_pb": "当前 MCP 画像链路仅能按运动记录窗口兜底，全部历史 PB 留待 FIT 下载增强",
    "full_marathon_pb": "当前 MCP 画像链路仅能按运动记录窗口兜底，全部历史 PB 留待 FIT 下载增强",
    "cycling_40km_time": "当前 COROS MCP 工具 schema 未确认骑行 40km 成绩字段，需后续 FIT 样本验证",
    "cycling_80km_time": "当前 COROS MCP 工具 schema 未确认骑行 80km 成绩字段，需后续 FIT 样本验证",
    "swimming_100m_pb": "当前 COROS MCP 工具 schema 未确认游泳 100m PB 字段，需后续 FIT 样本验证",
}

SPORT_RUN = {100, 101, 102, 103}
SPORT_HIKE = {104, 105, 106}
SPORT_CYCLE = {200, 201, 202, 203, 204, 205, 299}
SPORT_SWIM = {300, 301}


def _is_file(path):
    try:
        return Path(path).expanduser().is_file()
    except (OSError, TypeError, ValueError):
        return False


def _bundled_node_candidates():
    root = str(os.environ.get("MAITU_BUNDLED_NODE_DIR") or "").strip()
    if not root:
        return []
    base = Path(root).expanduser()
    return [
        base / "node.exe",
        base / "node",
        base / "bin" / "node.exe",
        base / "bin" / "node",
    ]


def resolve_node_binary():
    env_node = str(os.environ.get("QCLAW_CLI_NODE_BINARY") or "").strip()
    if env_node:
        return env_node
    for candidate in _bundled_node_candidates():
        if _is_file(candidate):
            return str(candidate)
    return shutil.which("node") or "node"


def call_keepalive(tool_name, args=None, retries=6):
    if args is None:
        args = {}
    node_binary = resolve_node_binary()
    cmd = [node_binary, str(KEEPALIVE), "call", tool_name, json.dumps(args, ensure_ascii=False)]
    for attempt in range(retries):
        try:
            result = run_hidden(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(SKILL_DIR),
                env=dict(os.environ),
            )
            if result.returncode != 0:
                if attempt < retries - 1:
                    import time
                    time.sleep(1.0 + attempt * 0.5)
                    continue
                return None
            out = result.stdout
            if "stackTrace" in out and "Session not found" in out:
                if attempt < retries - 1:
                    import time
                    time.sleep(1.5 + attempt * 0.5)
                    continue
                print(f"[warn] {tool_name}: COROS session 多次超时", file=sys.stderr)
                return None
            return out
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            if attempt < retries - 1:
                import time
                time.sleep(1.0 + attempt * 0.5)
                continue
            print(f"[warn] call {tool_name} failed: {exc}", file=sys.stderr)
            return None
    return None


def _decode_json_maybe(value):
    if not isinstance(value, str):
        return value
    raw = value.strip()
    if not raw:
        return ""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw.replace("\\n", "\n").replace('\\"', '"').replace("\\t", "\t")


def _unwrap_keepalive_envelope(payload):
    payload = _decode_json_maybe(payload)
    if not isinstance(payload, dict):
        return payload
    if payload.get("ok") is False:
        return payload.get("error") or payload.get("message") or payload.get("raw_summary") or payload
    if payload.get("ok") is True:
        if "data" in payload:
            return payload.get("data")
        if "text" in payload:
            return payload.get("text")
        if "content" in payload:
            return {"content": payload.get("content")}
    return payload


def _mcp_payload_to_text(payload):
    payload = _unwrap_keepalive_envelope(payload)
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        content = payload.get("content")
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("text") is not None:
                    parts.append(_mcp_payload_to_text(item.get("text")))
                elif item is not None:
                    parts.append(_mcp_payload_to_text(item))
            return "\n".join(part for part in parts if part)
        return json.dumps(payload, ensure_ascii=False)
    if isinstance(payload, list):
        return "\n".join(_mcp_payload_to_text(item) for item in payload if item is not None)
    return str(payload)


def _mcp_payload_to_dict(payload):
    payload = _unwrap_keepalive_envelope(payload)
    if isinstance(payload, dict):
        content = payload.get("content")
        if isinstance(content, list):
            merged = {}
            for item in content:
                if isinstance(item, dict) and item.get("text") is not None:
                    child = _mcp_payload_to_dict(item.get("text"))
                    if child:
                        merged.update(child)
                else:
                    child = _mcp_payload_to_dict(item)
                    if child:
                        merged.update(child)
            if merged:
                return merged
        return payload
    if isinstance(payload, list):
        merged = {}
        for item in payload:
            child = _mcp_payload_to_dict(item)
            if child:
                merged.update(child)
        return merged
    return {}


def _mcp_payload_to_records(payload):
    payload = _unwrap_keepalive_envelope(payload)
    if isinstance(payload, dict) and isinstance(payload.get("content"), list):
        records = []
        for item in payload.get("content") or []:
            records.extend(_mcp_payload_to_records(item.get("text") if isinstance(item, dict) else item))
        return records
    if isinstance(payload, dict):
        for key in ("records", "data", "activities", "items", "list"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _unescape(text):
    return _mcp_payload_to_text(text)


def _first_present(data, *keys):
    if not isinstance(data, dict):
        return None
    lower_map = {str(k).lower(): v for k, v in data.items()}
    for key in keys:
        if key in data and data.get(key) is not None:
            return data.get(key)
        lowered = str(key).lower()
        if lowered in lower_map and lower_map[lowered] is not None:
            return lower_map[lowered]
    return None


def _number_value(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    values = _numbers(value)
    return values[0] if values else None


def _normalize_gender(value):
    clean = str(value or "").strip()
    lower = clean.lower()
    if lower in {"male", "m", "man", "男"}:
        return "男"
    if lower in {"female", "f", "woman", "女"}:
        return "女"
    return clean or None


def _age_from_birthday(value):
    if not value:
        return None
    try:
        birthday = datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
        today = datetime.now().date()
        return today.year - birthday.year - ((today.month, today.day) < (birthday.month, birthday.day))
    except ValueError:
        return None


def _numbers(text):
    return [float(value) for value in re.findall(r"(?<!\d)(\d+(?:\.\d+)?)(?!\d)", str(text or ""))]


def _first_int(text):
    values = _numbers(text)
    return int(round(values[0])) if values else None


def _parse_duration_hours(text):
    clean = str(text or "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:h|hr|hour|hours|小时)", clean, re.I)
    if m:
        return round(float(m.group(1)), 2)
    m = re.search(r"(\d+):(\d{2})(?::(\d{2}))?", clean)
    if m:
        first = int(m.group(1))
        second = int(m.group(2))
        third = int(m.group(3) or 0)
        if m.group(3):
            return round(first + second / 60 + third / 3600, 2)
        return round(first / 60 + second / 3600, 2)
    m = re.search(r"(\d+)\s*(?:min|minute|minutes|分钟)", clean, re.I)
    if m:
        return round(int(m.group(1)) / 60, 2)
    return None


def _parse_time_of_day(text):
    clean = str(text or "")
    for pattern in (
        r"(?:bedtime|sleep start|main sleep window|入睡|开始)[^\d]*(\d{1,2}:\d{2})",
        r"(\d{1,2}:\d{2})\s*(?:-|~|至)",
    ):
        m = re.search(pattern, clean, re.I)
        if m:
            return m.group(1)
    return None


def parse_user_info(text):
    info = {}
    data = _mcp_payload_to_dict(text)
    text = _unescape(text)
    m = re.search(r"Height:\s*([\d.]+)\s*cm", text, re.I)
    if m:
        info["height_cm"] = float(m.group(1))
    m = re.search(r"Weight:\s*([\d.]+)\s*kg", text, re.I)
    if m:
        info["weight_kg"] = float(m.group(1))
    m = re.search(r"Age:\s*(\d+)", text, re.I)
    if m:
        info["age"] = int(m.group(1))
    m = re.search(r"Birthday:\s*(\d{4}-\d{2}-\d{2})", text, re.I)
    if m and "age" not in info:
        age = _age_from_birthday(m.group(1))
        if age is not None:
            info["age"] = age
    m = re.search(r"Gender:\s*(\S+)", text, re.I)
    if m:
        info["gender"] = _normalize_gender(m.group(1))
    m = re.search(r"Nickname:\s*(.+)", text, re.I)
    if m:
        info["username"] = m.group(1).strip()

    height = _number_value(_first_present(data, "height_cm", "heightCm", "height", "stature"))
    if height is not None:
        info["height_cm"] = round(height * 100, 1) if 1.0 <= height <= 3.0 else height
    weight = _number_value(_first_present(data, "weight_kg", "weightKg", "weight"))
    if weight is not None:
        info["weight_kg"] = weight
    age = _number_value(_first_present(data, "age"))
    if age is not None:
        info["age"] = int(round(age))
    elif "age" not in info:
        birthday = _first_present(data, "birthday", "birthdate", "birth_date", "birthDate")
        parsed_age = _age_from_birthday(birthday)
        if parsed_age is not None:
            info["age"] = parsed_age
    gender = _first_present(data, "gender", "sex")
    if gender is not None:
        info["gender"] = _normalize_gender(gender)
    username = _first_present(data, "username", "nickname", "name")
    if username is not None:
        info["username"] = str(username).strip()
    return info


def parse_fitness_assessment(text):
    info = {}
    data = _mcp_payload_to_dict(text)
    text = _unescape(text)
    m = re.search(r"VO2\s*max|VO2max", text, re.I)
    if m:
        tail = text[m.end():m.end() + 80]
        value = _first_int(tail)
        if value is not None:
            info["vo2_max"] = value
    m = re.search(r"Threshold Pace:\s*([\d:]+)", text, re.I)
    if m:
        info["lactate_threshold_pace"] = m.group(1) + " /km"
    for label, key in [
        (r"5\s*km Prediction:\s*([\d:]+)", "race_predict_5k"),
        (r"10\s*km Prediction:\s*([\d:]+)", "race_predict_10k"),
        (r"Half Marathon Prediction:\s*([\d:]+)", "race_predict_half"),
        (r"(?<!Half )Marathon Prediction:\s*([\d:]+)", "race_predict_full"),
    ]:
        m = re.search(label, text, re.I)
        if m:
            info[key] = m.group(1)

    vo2 = _number_value(_first_present(data, "vo2_max", "vo2max", "vdot"))
    if vo2 is not None:
        info["vo2_max"] = int(round(vo2))
    threshold_pace = _first_present(data, "lactate_threshold_pace", "threshold_pace", "thresholdPace")
    if threshold_pace is not None:
        pace = str(threshold_pace).strip()
        info["lactate_threshold_pace"] = pace if "/km" in pace else pace + " /km"
    for key, candidates in {
        "race_predict_5k": ("race_predict_5k", "predict_5k", "five_k_prediction", "fiveKPrediction"),
        "race_predict_10k": ("race_predict_10k", "predict_10k", "ten_k_prediction", "tenKPrediction"),
        "race_predict_half": ("race_predict_half", "predict_half", "half_marathon_prediction", "halfMarathonPrediction"),
        "race_predict_full": ("race_predict_full", "predict_full", "marathon_prediction", "marathonPrediction"),
    }.items():
        value = _first_present(data, *candidates)
        if value is not None:
            info[key] = str(value).strip()
    return info


def parse_single_metric(text, labels, json_keys=None):
    data = _mcp_payload_to_dict(text)
    for key in json_keys or []:
        value = _number_value(_first_present(data, key))
        if value is not None:
            return value
    clean = _unescape(text)
    if re.search(r"\bno\s+data\b|no .* found|无数据|未找到", clean, re.I):
        return None
    for label in labels:
        m = re.search(label + r"[^\n\r\d]*(\d+(?:\.\d+)?)", clean, re.I)
        if m:
            return float(m.group(1))
    return None


def parse_sleep(text):
    data = _mcp_payload_to_dict(text)
    clean = _unescape(text)
    if re.search(r"\bno\s+sleep\s+data\b|no .* found|无睡眠|未找到", clean, re.I):
        return {"avg_sleep_hours": None, "avg_bedtime": None}
    sleep_hours = _number_value(_first_present(data, "avg_sleep_hours", "sleep_hours", "total_sleep_hours", "sleepHours", "totalSleepHours"))
    bedtime = _first_present(data, "avg_bedtime", "bedtime", "sleep_start", "sleepStart")
    return {
        "avg_sleep_hours": round(sleep_hours, 2) if sleep_hours is not None else _parse_duration_hours(clean),
        "avg_bedtime": str(bedtime).strip() if bedtime is not None else _parse_time_of_day(clean),
    }


def _activity_from_record(record):
    item = {"raw": record}
    sport_type = _number_value(_first_present(record, "sport_type", "sportType", "sportTypeCode"))
    if sport_type is not None:
        item["sport_type"] = int(round(sport_type))
    distance = _number_value(_first_present(record, "distance_km", "distanceKm", "distance", "totalDistance", "distanceMeters"))
    if distance is not None:
        item["distance_km"] = round(distance / 1000, 3) if distance > 1000 else distance
    duration = _first_present(record, "duration", "duration_sec", "durationSeconds", "totalTime")
    if duration is not None:
        if isinstance(duration, (int, float)):
            seconds = int(round(float(duration)))
            item["duration"] = f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"
        else:
            item["duration"] = str(duration).strip()
    pace = _first_present(record, "avg_pace", "average_pace", "avgPace", "pace")
    if pace is not None:
        item["avg_pace"] = str(pace).strip()
    return item if "distance_km" in item else None


def parse_sport_records(text):
    activities = []
    for record in _mcp_payload_to_records(text):
        item = _activity_from_record(record)
        if item:
            activities.append(item)
    if activities:
        return activities

    clean = _unescape(text)
    blocks = re.split(r"\n(?=\d+\.\s)", clean)
    for block in blocks:
        if not re.match(r"\d+\.\s", block):
            continue
        item = {"raw": block}
        m = re.search(r"SportType:\s*(\d+)", block, re.I)
        if m:
            item["sport_type"] = int(m.group(1))
        m = re.search(r"Distance:\s*([\d.]+)\s*km", block, re.I)
        if m:
            item["distance_km"] = float(m.group(1))
        m = re.search(r"Duration:\s*([\d:]+)", block, re.I)
        if m:
            item["duration"] = m.group(1)
        m = re.search(r"Average Pace:\s*([\d:]+)", block, re.I)
        if m:
            item["avg_pace"] = m.group(1)
        if "distance_km" in item:
            activities.append(item)
    return activities


def _pace_seconds(value):
    parts = [int(part) for part in str(value).split(":") if part.isdigit()]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return 10**9


def find_pb(activities, sport_types, low, high):
    candidates = [
        item for item in activities
        if item.get("sport_type") in sport_types
        and low <= float(item.get("distance_km") or 0) <= high
        and item.get("avg_pace")
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda item: _pace_seconds(item.get("avg_pace")))["avg_pace"]


def aggregate_distance(activities, sport_types):
    selected = [
        item for item in activities
        if item.get("sport_type") in sport_types and item.get("distance_km") is not None
    ]
    if not selected:
        return None, None
    total = round(sum(float(item["distance_km"]) for item in selected), 2)
    longest = round(max(float(item["distance_km"]) for item in selected), 2)
    return total, longest


def build_profile():
    result = {field: {"metric": field, "value": None} for field in FIELDS}

    user_info = parse_user_info(call_keepalive("queryUserInfo"))
    for key, value in user_info.items():
        if key in result:
            result[key]["value"] = value
            result[key]["note"] = "COROS MCP queryUserInfo"

    fitness = parse_fitness_assessment(call_keepalive("queryFitnessAssessmentOverview"))
    for key, value in fitness.items():
        if key in result:
            result[key]["value"] = value
            result[key]["note"] = "COROS MCP queryFitnessAssessmentOverview"

    resting = parse_single_metric(call_keepalive("queryRestingHeartRate", {"days": 7, "timezone": "Asia/Shanghai"}), [
        r"resting heart rate",
        r"restingHeartRate",
        r"静息心率",
    ], json_keys=["resting_heart_rate", "restingHeartRate", "avg_resting_hr", "resting_hr"])
    if resting is not None:
        result["resting_heart_rate"]["value"] = int(round(resting))
        result["resting_heart_rate"]["note"] = "COROS MCP queryRestingHeartRate"

    hrv = parse_single_metric(call_keepalive("querySleepHrv", {"days": 7, "timezone": "Asia/Shanghai"}), [
        r"average HRV",
        r"avgHrv",
        r"sleep HRV",
        r"HRV",
    ], json_keys=["hrv", "avgHrv", "average_hrv", "sleep_hrv"])
    if hrv is not None:
        result["hrv"]["value"] = round(hrv, 1)
        result["hrv"]["note"] = "COROS MCP querySleepHrv"

    sleep = parse_sleep(call_keepalive("querySleepData", {"days": 7, "timezone": "Asia/Shanghai"}))
    for key in ("avg_sleep_hours", "avg_bedtime"):
        if sleep.get(key) is not None:
            result[key]["value"] = sleep[key]
            result[key]["note"] = "COROS MCP querySleepData"

    activities = parse_sport_records(call_keepalive("querySportRecords", {
        "sportTypeCodes": [65535],
        "limit": 20,
        "timezone": "Asia/Shanghai",
    }))
    if activities:
        for key, low, high in [
            ("1km_pb", 0.95, 1.15),
            ("1mile_pb", 1.55, 1.75),
            ("5km_pb", 4.8, 5.2),
            ("10km_pb", 9.8, 10.2),
            ("half_marathon_pb", 20.8, 21.6),
            ("full_marathon_pb", 41.5, 42.5),
        ]:
            value = find_pb(activities, SPORT_RUN, low, high)
            if value is not None:
                result[key]["value"] = value
                result[key]["note"] = "COROS MCP querySportRecords 当前窗口最佳（非 all-time PB）"
        for total_key, longest_key, sport_types, note in [
            ("total_run_km", "longest_run_km", SPORT_RUN, "跑步"),
            ("total_hike_km", "longest_hike_km", SPORT_HIKE, "徒步/登山"),
            ("total_cycle_km", "longest_cycle_km", SPORT_CYCLE, "骑行"),
            ("total_swim_km", "longest_swim_distance_m", SPORT_SWIM, "游泳"),
        ]:
            total, longest = aggregate_distance(activities, sport_types)
            if total is not None:
                result[total_key]["value"] = total
                result[total_key]["note"] = f"COROS MCP querySportRecords 当前窗口{note}合计（非 all-time）"
            if longest is not None:
                result[longest_key]["value"] = round(longest * 1000, 1) if longest_key == "longest_swim_distance_m" else longest
                result[longest_key]["note"] = f"COROS MCP querySportRecords 当前窗口最长{note}（非 all-time）"

    for key, reason in UNAVAILABLE.items():
        if result[key]["value"] is None:
            result[key]["note"] = reason
    for key in FIELDS:
        if result[key]["value"] is None and "note" not in result[key]:
            result[key]["note"] = "当前 COROS MCP 返回中未解析到该字段，需后续真实样本验证"
    return [result[field] for field in FIELDS]


def main():
    args = sys.argv[1:]
    sync_mode = "sync" in args or "同步用户画像" in args
    profile = build_profile()
    print(json.dumps(profile, ensure_ascii=False, indent=2))
    if not sync_mode:
        obtained = sum(1 for item in profile if item.get("value") is not None)
        print(f"\n=== 字段可获取性 ===\n已获取: {obtained}/{len(profile)}", file=sys.stderr)


if __name__ == "__main__":
    main()
