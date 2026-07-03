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
import subprocess
import sys
from datetime import datetime
from pathlib import Path


SKILL_DIR = Path(__file__).parent
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


def call_keepalive(tool_name, args=None, retries=6):
    if args is None:
        args = {}
    cmd = ["node", str(KEEPALIVE), "call", tool_name, json.dumps(args, ensure_ascii=False)]
    for attempt in range(retries):
        try:
            result = subprocess.run(
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


def _unescape(text):
    if not text:
        return ""
    raw = str(text).strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, str):
            return parsed
        return json.dumps(parsed, ensure_ascii=False)
    except json.JSONDecodeError:
        return raw.replace("\\n", "\n").replace('\\"', '"').replace("\\t", "\t")


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
        try:
            birthday = datetime.strptime(m.group(1), "%Y-%m-%d").date()
            today = datetime.now().date()
            info["age"] = today.year - birthday.year - ((today.month, today.day) < (birthday.month, birthday.day))
        except ValueError:
            pass
    m = re.search(r"Gender:\s*(\S+)", text, re.I)
    if m:
        gender = m.group(1)
        info["gender"] = "男" if gender.lower() == "male" else "女" if gender.lower() == "female" else gender
    m = re.search(r"Nickname:\s*(.+)", text, re.I)
    if m:
        info["username"] = m.group(1).strip()
    return info


def parse_fitness_assessment(text):
    info = {}
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
    return info


def parse_single_metric(text, labels):
    clean = _unescape(text)
    if re.search(r"\bno\s+data\b|no .* found|无数据|未找到", clean, re.I):
        return None
    for label in labels:
        m = re.search(label + r"[^\n\r\d]*(\d+(?:\.\d+)?)", clean, re.I)
        if m:
            return float(m.group(1))
    return None


def parse_sleep(text):
    clean = _unescape(text)
    if re.search(r"\bno\s+sleep\s+data\b|no .* found|无睡眠|未找到", clean, re.I):
        return {"avg_sleep_hours": None, "avg_bedtime": None}
    return {
        "avg_sleep_hours": _parse_duration_hours(clean),
        "avg_bedtime": _parse_time_of_day(clean),
    }


def parse_sport_records(text):
    clean = _unescape(text)
    activities = []
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
    ])
    if resting is not None:
        result["resting_heart_rate"]["value"] = int(round(resting))
        result["resting_heart_rate"]["note"] = "COROS MCP queryRestingHeartRate"

    hrv = parse_single_metric(call_keepalive("querySleepHrv", {"days": 7, "timezone": "Asia/Shanghai"}), [
        r"average HRV",
        r"avgHrv",
        r"sleep HRV",
        r"HRV",
    ])
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
