#!/usr/bin/env python3
"""
coros_runner_profile.py - 跑者档案 42 字段聚合器

数据来源（按优先级）：
1. Training Hub URL（t.coros.com/admin/views/dash-board 及其 Training Hub 接口）
2. COROS MCP（queryUserInfo / queryFitnessAssessmentOverview / querySportRecords）

输出：标准 JSON 数组，每项 {"metric": "...", "value": ..., "note"?: "..."}。
- "同步用户画像" 触发时：仅输出 JSON 数组，不加任何解释
- 其他触发：JSON 数组 + 字段说明

字段获取不到的，统一用 null + note 说明。不得使用本地手动覆盖或公式估算。
"""
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

# 路径
SKILL_DIR = Path(__file__).parent
KEEPALIVE = SKILL_DIR / "coros-mcp-keepalive.js"
URL_FETCH = SKILL_DIR / "coros-url-fetch.js"  # URL 通道抓取器
TRAININGHUB_TOKEN_PATH = Path.home() / ".qclaw" / "coros-traininghub-token.json"

# 42 字段清单（41 原字段 + max_heart_rate）
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

# 不可获取的字段（URL+MCP 都不提供时标注）
UNAVAILABLE = {
    # 体成分（手表硬件不测）
    "body_fat_percent": "COROS 手表不测体成分；需第三方体脂秤（Withings/小米）",
    "body_water_percent": "COROS 手表不测体成分",
    "bone_mass_kg": "COROS 手表不测体成分",
    "muscle_mass_kg": "COROS 手表不测体成分",
    "metabolic_age": "COROS 手表不测体成分",
    "visceral_fat": "COROS 手表不测体成分",
    # HRV/睡眠（URL 面板空 + MCP NPE 或返回空）
    "hrv": "URL 面板存在但显示「近 7 日无数据」；MCP queryHrvAssessment 服务器 NPE",
    "avg_sleep_hours": "MCP querySleepData 返回「No sleep data found」；URL 无睡眠面板",
    "avg_bedtime": "MCP querySleepData 返回「No sleep data found」；URL 无睡眠面板",
    # 功率
    "ftp_watts": "COROS 不支持功率训练生态；无该字段",
    # 跑步 PBs（URL 个人跑步纪录只到 10km；MCP 7 天窗口内一般无全马/半马）
    "1mile_pb": "URL 个人跑步纪录无 1 英里项目；MCP 7 天窗口内无 1.6km 记录",
    "half_marathon_pb": "URL 个人跑步纪录只到 10km（无半马项目）；MCP 7 天窗口内无 21km 记录",
    "full_marathon_pb": "URL 个人跑步纪录只到 10km（无全马项目）；MCP 7 天窗口内无 42km 记录",
    # 总里程（两个通道都不暴露）
    "total_run_km": "URL 不暴露总跑量；MCP 仅能返回近期窗口合计（非 all-time）",
    "total_cycle_km": "URL 不暴露总骑行；MCP 7 天窗口内无骑行",
    # 徒步（URL 无面板 + MCP 7 天内通常无）
    "longest_hike_km": "URL 无徒步面板；MCP 7 天窗口内无徒步记录",
    "total_hike_km": "URL 无徒步面板；MCP 7 天窗口内无徒步记录",
    # 骑行细节（URL 面板只有距离+爬升，无时间列）
    "longest_ride_time": "URL 骑行纪录只有距离+爬升（无时间列）；MCP 7 天窗口无",
    "cycling_40km_time": "URL 骑行纪录无 40km 成绩；MCP 7 天窗口无",
    "cycling_80km_time": "URL 骑行纪录无 80km 成绩；MCP 7 天窗口无",
    # 游泳（URL 无面板 + MCP 7 天内通常无）
    "longest_swim_distance_m": "URL 无游泳面板；MCP 7 天窗口内无游泳",
    "total_swim_km": "URL 无游泳面板；MCP 7 天窗口内无游泳",
    "swimming_100m_pb": "URL 无游泳面板；MCP 7 天窗口内无 100m 游泳",
}

# 跑步 SportType（按 COROS 编号）
SPORT_RUN = {100, 101, 102, 103}  # Outdoor / Indoor / Track / Trail
SPORT_HIKE = {104, 105}
SPORT_SWIM = {113, 114, 115, 116, 117, 118}  # 各类游泳
SPORT_CYCLE = {0, 1, 2, 3, 4}  # 骑行类（实际编号待 querySportRecords 验证）


def call_keepalive(tool_name, args=None, retries=6):
    """调用 COROS MCP 工具，返回原始 stdout。失败返回 None。

    COROS MCP 服务器会话不稳定（首调经常 Session not found），
    重试 6 次，指数退避 1s / 2s / 3s / 4s / 5s。
    """
    if args is None:
        args = {}
    cmd = ["node", str(KEEPALIVE), "call", tool_name, json.dumps(args)]
    for attempt in range(retries):
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30, cwd=str(SKILL_DIR)
            )
            if result.returncode != 0:
                if attempt < retries - 1:
                    import time
                    time.sleep(1.0 + attempt * 0.5)
                    continue
                return None
            out = result.stdout
            # 检测 COROS 会话丢失错误：包含 "Session not found" 或 stackTrace
            if "stackTrace" in out and "Session not found" in out:
                if attempt < retries - 1:
                    import time
                    time.sleep(1.5 + attempt * 0.5)
                    continue
                print(f"[warn] {tool_name}: COROS session 多次超时 (重试 {retries} 次)", file=sys.stderr)
                return None
            return out
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            if attempt < retries - 1:
                import time
                time.sleep(1.0 + attempt * 0.5)
                continue
            print(f"[warn] call {tool_name} failed: {e}", file=sys.stderr)
            return None
    return None


def _unescape(text):
    """COROS MCP 输出是 JSON 字符串，含 \\n / \\" 等转义，先还原。"""
    if not text:
        return text
    text = text.strip()
    # COROS MCP 输出的成功格式是 JSON 字符串以 " 包裹："text content"
    # 失败格式是 JSON 对象：{"stackTrace": ...}
    # 这里只处理成功格式
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1]
    # 用 JSON 解析做规范反转义（最可靠）
    try:
        # 把 text 当成 JSON 字符串字面量解析
        parsed = json.loads('"' + text.replace('"', '\\"') + '"')
        return parsed
    except json.JSONDecodeError:
        pass
    # 兜底：手动反转义
    return text.replace("\\n", "\n").replace('\\"', '"').replace("\\t", "\t").replace("\\\\", "\\")


def parse_user_info(text):
    """解析 queryUserInfo 文本，提取 nickname / age / gender / height / weight。"""
    info = {}
    if not text:
        return info
    text = _unescape(text)
    # Height: 170.0 cm
    m = re.search(r"Height:\s*([\d.]+)\s*cm", text)
    if m:
        info["height_cm"] = float(m.group(1))
    # Weight: 73.8 kg
    m = re.search(r"Weight:\s*([\d.]+)\s*kg", text)
    if m:
        info["weight_kg"] = float(m.group(1))
    # Birthday: 1979-08-20 (Age: 46)
    m = re.search(r"Age:\s*(\d+)", text)
    if m:
        info["age"] = int(m.group(1))
    # Gender: Male
    m = re.search(r"Gender:\s*(\S+)", text)
    if m:
        g = m.group(1)
        info["gender"] = "男" if g.lower() == "male" else "女" if g.lower() == "female" else g
    # Nickname: 用户昵称
    m = re.search(r"Nickname:\s*(.+)", text)
    if m:
        info["username"] = m.group(1).strip()
    return info


def parse_fitness_assessment(text):
    """解析 queryFitnessAssessmentOverview 文本。"""
    info = {}
    if not text:
        return info
    text = _unescape(text)
    # VO2max: 45
    m = re.search(r"VO2max:\s*(\d+)", text)
    if m:
        info["vo2_max"] = int(m.group(1))
    # Threshold Pace: 5:12 /km
    m = re.search(r"Threshold Pace:\s*([\d:]+)", text)
    if m:
        info["lactate_threshold_pace"] = m.group(1) + " /km"
    # 5 km Prediction: 24:59
    for label, key in [
        (r"5 km Prediction:\s*([\d:]+)", "race_predict_5k"),
        (r"10 km Prediction:\s*([\d:]+)", "race_predict_10k"),
        (r"Half Marathon Prediction:\s*([\d:]+)", "race_predict_half"),
        (r"(?<!Half )Marathon Prediction:\s*([\d:]+)", "race_predict_full"),
    ]:
        m = re.search(label, text)
        if m:
            info[key] = m.group(1)
    return info


def parse_sport_records(text):
    """解析 querySportRecords 文本，返回活动列表。"""
    if not text:
        return []
    text = _unescape(text)
    activities = []
    # 按编号块切分
    blocks = re.split(r"\n(?=\d+\.\s)", text)
    for block in blocks:
        if not re.match(r"\d+\.\s", block):
            continue
        a = {"raw": block}
        # SportType
        m = re.search(r"SportType:\s*(\d+)", block)
        if m:
            a["sport_type"] = int(m.group(1))
        # Distance: 5.57 km
        m = re.search(r"Distance:\s*([\d.]+)\s*km", block)
        if m:
            a["distance_km"] = float(m.group(1))
        # Duration: 38:43
        m = re.search(r"Duration:\s*([\d:]+)", block)
        if m:
            a["duration"] = m.group(1)
        # Average Pace: 6:57 /km
        m = re.search(r"Average Pace:\s*([\d:]+)", block)
        if m:
            a["avg_pace"] = m.group(1)
        # Avg HR: 125 bpm
        m = re.search(r"Avg HR:\s*(\d+)\s*bpm", block)
        if m:
            a["avg_hr"] = int(m.group(1))
        # 名称推断
        m = re.match(r"\d+\.\s*(.+?)\s*—", block)
        if m:
            a["name"] = m.group(1).strip()
        if "distance_km" in a and "duration" in a:
            activities.append(a)
    return activities


# ============== URL 数据源（t.coros.com/admin/views/dash-board）==============

def fetch_url_data(retries=2):
    """调用 coros-url-fetch.js 拿 dashboard 完整数据。

    依赖：Chrome 进程带 --remote-debugging-port=9222 启动，
    且在 t.coros.com/admin/views/dash-board 页面有登录 session。
    失败时返回空 dict。
    """
    if not URL_FETCH.exists():
        print(f"[warn] URL fetch script not found: {URL_FETCH}", file=sys.stderr)
        return {}
    for attempt in range(retries):
        try:
            r = subprocess.run(
                ["node", str(URL_FETCH)],
                capture_output=True, text=True, timeout=60, cwd=str(SKILL_DIR)
            )
            if r.returncode != 0:
                if attempt < retries - 1:
                    import time; time.sleep(1.0); continue
                print(f"[warn] URL fetch failed (exit {r.returncode}): {r.stderr[:200]}", file=sys.stderr)
                return {}
            # 最后一行 stdout 是 JSON（之前是 [info] 提示）
            out = r.stdout.strip()
            # 提取最后一块 JSON {...}
            brace_start = out.rfind('\n{')
            if brace_start == -1:
                brace_start = out.find('{')
            if brace_start == -1:
                print(f"[warn] No JSON in URL output: {out[:200]}", file=sys.stderr)
                return {}
            data = json.loads(out[brace_start:].strip())
            return data
        except subprocess.TimeoutExpired:
            if attempt < retries - 1:
                import time; time.sleep(1.0); continue
            print("[warn] URL fetch timeout", file=sys.stderr)
            return {}
        except json.JSONDecodeError as e:
            print(f"[warn] URL JSON parse failed: {e}", file=sys.stderr)
            return {}
    return {}


def find_pb(activities, sport_types, distance_low, distance_high, value_key="avg_pace"):
    """在指定运动类型 + 距离区间内找最佳（最快配速）记录。"""
    candidates = [
        a for a in activities
        if a.get("sport_type") in sport_types
        and "distance_km" in a
        and distance_low <= a["distance_km"] <= distance_high
    ]
    if not candidates:
        return None
    if value_key == "avg_pace":
        # 配速越小越好（mm:ss → 秒）
        def to_sec(p):
            m, s = p.split(":")
            return int(m) * 60 + int(s)
        candidates.sort(key=lambda a: to_sec(a["avg_pace"]))
        return candidates[0]["avg_pace"]
    return None


def aggregate_runs(activities, sport_types):
    """聚合跑步：总距离、最长距离。"""
    runs = [a for a in activities if a.get("sport_type") in sport_types and "distance_km" in a]
    if not runs:
        return None, None
    total = sum(a["distance_km"] for a in runs)
    longest = max(a["distance_km"] for a in runs)
    return round(total, 2), round(longest, 2)


def aggregate_swim(activities, sport_types):
    """聚合游泳：总距离（km）、最长距离（m）。"""
    swims = [a for a in activities if a.get("sport_type") in sport_types and "distance_km" in a]
    if not swims:
        return None, None
    total_km = round(sum(a["distance_km"] for a in swims), 2)
    longest_m = max(a["distance_km"] for a in swims) * 1000
    return total_km, longest_m


def load_traininghub_token():
    """读取 Training Hub cookie（如已登录）。"""
    if not TRAININGHUB_TOKEN_PATH.exists():
        return None
    try:
        with open(TRAININGHUB_TOKEN_PATH) as f:
            data = json.load(f)
        token = data.get("token")
        if not token:
            return None
        return token
    except (json.JSONDecodeError, OSError):
        return None


def _th_get(path, token, params=None):
    """COROS Training Hub API 调用。鉴权用 accessToken header（不是 Authorization）。

    实测根因：COROS 后端读 custom header `accessToken`，cookie 不参与鉴权。
    """
    import urllib.request
    if params:
        from urllib.parse import urlencode
        path = path + "?" + urlencode(params)
    url = "https://teamcnapi.coros.com" + path
    req = urllib.request.Request(
        url,
        headers={
            "accessToken": token,
            "Origin": "https://t.coros.com",
            "Referer": "https://t.coros.com/",
            "regionId": "2",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[warn] traininghub {path} failed: {e}", file=sys.stderr)
        return None


def fetch_traininghub_dashboard(token):
    """拿 dashboard/query 完整响应（含 summaryInfo.lthr/ltsp/lthrZone 等）。"""
    return _th_get("/dashboard/query", token, {"size": 30})


def fetch_traininghub_cycle(token):
    """拿 dashboard/queryCycleRecord（骑行 PR 列表）。"""
    return _th_get("/dashboard/queryCycleRecord", token)


def extract_traininghub_summary(dashboard_data):
    """从 dashboard/query 提取 summaryInfo。

    实测字段：
      lthr=166, ltsp=312(秒), fitnessMaxHr=187, cycleLevelHr=139
      aerobicEnduranceScore=73.3, anaerobicCapacityScore=71.8, ...
    """
    if not dashboard_data:
        return {}
    info = (dashboard_data.get("data") or {}).get("summaryInfo") or {}
    return info


def extract_cycle_prs(cycle_data):
    """从 dashboard/queryCycleRecord 提取骑行 PR。

    实测结构：
      data.allRecordList: [ { type, recordList: [{type, subMode, mode, sportType, record, happenDay, ...}] }, ... ]
      - type=101: 持续时间（秒）
      - type=102: 距离（km）
    返回: {longest_ride_time: max of type 101, longest_cycle_km: max of type 102}
    """
    if not cycle_data:
        return {}
    all_groups = (cycle_data.get("data") or {}).get("allRecordList") or []
    time_records = []   # type=101
    dist_records = []   # type=102
    for grp in all_groups:
        for r in grp.get("recordList", []):
            t = r.get("type")
            v = r.get("record")
            if t == 101 and v:
                time_records.append(v)
            elif t == 102 and v:
                dist_records.append(v)
    out = {}
    if time_records:
        out["longest_ride_time"] = max(time_records)  # 秒
    if dist_records:
        out["longest_cycle_km"] = max(dist_records)   # km
    return out


def build_profile():
    """构建 42 字段 JSON 数组。

    合并规则：先用 MCP 填兜底值，再用 Training Hub URL/API 覆盖同字段。
    数据只来自 Training Hub URL/API 和 COROS MCP。
    """
    result = {f: {"metric": f, "value": None} for f in FIELDS}

    # ---------- 来源 1：COROS MCP ----------
    # queryUserInfo
    text = call_keepalive("queryUserInfo")
    user_info = parse_user_info(text)
    for k in ("username", "age", "gender", "height_cm", "weight_kg"):
        if k in user_info:
            result[k]["value"] = user_info[k]

    # queryFitnessAssessmentOverview
    text = call_keepalive("queryFitnessAssessmentOverview")
    fitness = parse_fitness_assessment(text)
    for k in ("vo2_max", "lactate_threshold_pace", "race_predict_5k", "race_predict_10k",
              "race_predict_half", "race_predict_full"):
        if k in fitness:
            result[k]["value"] = fitness[k]

    # querySportRecords（7 天窗口）
    text = call_keepalive("querySportRecords")
    activities = parse_sport_records(text)
    if activities:
        # 跑步 PB（MCP 仅近 7 天；Training Hub URL 的 all-time PB 会在后面覆盖）
        for k, lo, hi in [
            ("1km_pb", 0.95, 1.15),
            ("1mile_pb", 1.55, 1.75),
            ("5km_pb", 4.8, 5.2),
            ("10km_pb", 9.8, 10.2),
            ("half_marathon_pb", 20.8, 21.6),
            ("full_marathon_pb", 41.5, 42.5),
        ]:
            v = find_pb(activities, SPORT_RUN, lo, hi)
            if v is not None:
                result[k]["value"] = v
                result[k]["note"] = "MCP querySportRecords 近 7 天最佳（非 all-time PB，仅兜底）"
        # 跑步聚合
        total_run, longest_run = aggregate_runs(activities, SPORT_RUN)
        if total_run is not None:
            result["total_run_km"]["value"] = total_run
            result["total_run_km"]["note"] = "MCP querySportRecords 近 7 天合计（非 all-time，仅兜底）"
        if longest_run is not None:
            result["longest_run_km"]["value"] = longest_run
            result["longest_run_km"]["note"] = "MCP querySportRecords 近 7 天最长（非 all-time，仅兜底）"
        # 徒步
        total_hike, longest_hike = aggregate_runs(activities, SPORT_HIKE)
        if total_hike is not None:
            result["total_hike_km"]["value"] = total_hike
            result["total_hike_km"]["note"] = "MCP querySportRecords 近 7 天合计（仅兜底）"
        if longest_hike is not None:
            result["longest_hike_km"]["value"] = longest_hike
            result["longest_hike_km"]["note"] = "MCP querySportRecords 近 7 天最长（仅兜底）"
        # 游泳
        total_swim_km, longest_swim_m = aggregate_swim(activities, SPORT_SWIM)
        if total_swim_km is not None:
            result["total_swim_km"]["value"] = total_swim_km
            result["total_swim_km"]["note"] = "MCP querySportRecords 近 7 天合计（仅兜底）"
        if longest_swim_m is not None:
            result["longest_swim_distance_m"]["value"] = longest_swim_m
            result["longest_swim_distance_m"]["note"] = "MCP querySportRecords 近 7 天最长（仅兜底）"
        # 100m 游泳 PB
        v = find_pb(activities, SPORT_SWIM, 0.08, 0.12)
        if v is not None:
            result["swimming_100m_pb"]["value"] = v
            result["swimming_100m_pb"]["note"] = "MCP querySportRecords 近 7 天最佳（仅兜底）"
        # 骑行（SportType 编号不确定，先尝试 0-50 减去已知项）
        cycle_types = set(range(0, 50)) - SPORT_RUN - SPORT_HIKE - SPORT_SWIM
        total_cycle, longest_cycle = aggregate_runs(activities, cycle_types)
        if total_cycle is not None:
            result["total_cycle_km"]["value"] = total_cycle
            result["total_cycle_km"]["note"] = "MCP querySportRecords 近 7 天合计（仅兜底）"
        if longest_cycle is not None:
            result["longest_cycle_km"]["value"] = longest_cycle
            result["longest_cycle_km"]["note"] = "MCP querySportRecords 近 7 天最长（仅兜底）"

    # 给未填上的 7 天窗口字段加默认 note
    for k in ("1km_pb", "1mile_pb", "5km_pb", "10km_pb", "half_marathon_pb", "full_marathon_pb",
              "longest_run_km", "total_run_km", "longest_hike_km", "total_hike_km",
              "longest_swim_distance_m", "total_swim_km"):
        if result[k]["value"] is None and k not in UNAVAILABLE:
            result[k]["note"] = "querySportRecords 7 天窗口内无符合记录（全部历史需导 FIT 解析）"

    # ---------- 来源 2：COROS URL（t.coros.com dashboard）----------
    # URL 抓取优先：个人跑步/骑行纪录有 all-time 数据，HR/配速/训练负荷 MCP NPE 时 URL 可补救
    url_data = fetch_url_data()
    if url_data:
        # 2.1 username (URL/MCP 双源一致)
        if url_data.get("username") and result["username"]["value"] is None:
            result["username"]["value"] = url_data["username"]
            result["username"]["note"] = "Training Hub URL.dashboard"

        # 2.2 max_heart_rate（URL 独有）
        if url_data.get("max_heart_rate"):
            result["max_heart_rate"]["value"] = url_data["max_heart_rate"]
            result["max_heart_rate"]["note"] = "Training Hub URL.dashboard (乳酸阈心率区间面板)"

        # 2.3 resting_heart_rate（URL 提供，MCP NPE）
        if url_data.get("resting_heart_rate"):
            result["resting_heart_rate"]["value"] = url_data["resting_heart_rate"]
            result["resting_heart_rate"]["note"] = "Training Hub URL.dashboard"

        # 2.4 lactate_threshold_hr（URL 优先）
        if url_data.get("lactate_threshold_hr"):
            result["lactate_threshold_hr"]["value"] = url_data["lactate_threshold_hr"]
            result["lactate_threshold_hr"]["note"] = "Training Hub URL.dashboard 实测"

        # 2.5 lactate_threshold_pace（URL 优先于 MCP）
        if url_data.get("lactate_threshold_pace"):
            result["lactate_threshold_pace"]["value"] = url_data["lactate_threshold_pace"]
            result["lactate_threshold_pace"]["note"] = "Training Hub URL.dashboard (乳酸阈配速区间面板)"

        # 2.6 PBs all-time（URL 个人跑步纪录“全部”窗口）
        pbs = url_data.get("pbs", {})
        for k in ("1km", "5km", "10km"):
            if pbs.get(k):
                f = f"{k}_pb"
                result[f]["value"] = pbs[k]
                result[f]["note"] = "Training Hub URL 个人跑步纪录（全部/all-time）"

        # 2.7 longest_run_km（URL all-time，优先于 MCP 7 天）
        if url_data.get("longest_run_km"):
            result["longest_run_km"]["value"] = url_data["longest_run_km"]
            result["longest_run_km"]["note"] = f"Training Hub URL 个人跑步纪录（全部/all-time） {url_data.get('longest_run_date', '')}".strip()

        # 2.8 longest_cycle_km（URL all-time，优先于 MCP 7 天 / Training Hub）
        if url_data.get("longest_cycle_km"):
            result["longest_cycle_km"]["value"] = url_data["longest_cycle_km"]
            result["longest_cycle_km"]["note"] = f"Training Hub URL 个人骑行纪录（全部/all-time） {url_data.get('longest_cycle_date', '')}".strip()

        # 2.8b longest_ride_time（URL 页面不提供，Training Hub API 可能补充）
        # 2.8c highest_climbing_gain_m（URL 个人跑步纪录，bonus）
        if url_data.get("highest_climb_m"):
            # bonus 字段，不在 42 字段中，存为 metadata
            pass

        # 2.9 race_predict_*（URL 与 MCP 一致但双源验证更可靠）
        for k in ("race_predict_5k", "race_predict_10k", "race_predict_half", "race_predict_full"):
            if url_data.get(k):
                result[k]["value"] = url_data[k]
                result[k]["note"] = "Training Hub URL 成绩预测面板"

    # ---------- 来源 3：Training Hub（可选） ----------
    th_token = load_traininghub_token()
    if th_token:
        # dashboard/query → summaryInfo（含 lthr/ltsp 实测）
        dash = fetch_traininghub_dashboard(th_token)
        info = extract_traininghub_summary(dash)
        if info.get("lthr") and result["lactate_threshold_hr"]["value"] is None:
            result["lactate_threshold_hr"]["value"] = info["lthr"]
            result["lactate_threshold_hr"]["note"] = "Training Hub dashboard/query 实测"
        elif result["lactate_threshold_hr"]["value"] is None:
            result["lactate_threshold_hr"]["note"] = "Training Hub URL/API 和 MCP 均未返回"
        if info.get("ltsp") and result["lactate_threshold_pace"]["value"] is None:
            secs = info["ltsp"]
            mm, ss = divmod(secs, 60)
            result["lactate_threshold_pace"]["value"] = f"{mm}:{ss:02d} /km"
            result["lactate_threshold_pace"]["note"] = f"Training Hub dashboard/query ltsp={secs}秒"
        # 额外 bonus：体能分（不在 41 字段内，但 useful）
        # 放在 metadata 里
        # queryCycleRecord → 骑行 PR
        cycle = fetch_traininghub_cycle(th_token)
        prs = extract_cycle_prs(cycle)
        if "longest_ride_time" in prs:
            secs = prs["longest_ride_time"]
            h, rem = divmod(secs, 3600)
            m, s = divmod(rem, 60)
            time_str = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
            result["longest_ride_time"]["value"] = time_str
            result["longest_ride_time"]["note"] = f"Training Hub queryCycleRecord 全部历史 type=101 最大值（{secs}秒）"
        if "longest_cycle_km" in prs and result["longest_cycle_km"]["value"] is None:
            result["longest_cycle_km"]["value"] = prs["longest_cycle_km"]
            result["longest_cycle_km"]["note"] = "Training Hub queryCycleRecord 全部历史 type=102 最大值"
    else:
        if result["lactate_threshold_hr"]["value"] is None:
            result["lactate_threshold_hr"]["note"] = "Training Hub URL/API 和 MCP 均未返回"

    # ---------- URL 最终覆盖（保证 Training Hub URL 优先级高于 MCP 和 API 补充）----------
    if url_data:
        pbs = url_data.get("pbs", {})
        for pb_key, field in (("1km", "1km_pb"), ("5km", "5km_pb"), ("10km", "10km_pb")):
            if pbs.get(pb_key):
                result[field]["value"] = pbs[pb_key]
                result[field]["note"] = "Training Hub URL 个人跑步纪录（全部/all-time）"
        for k in ("username", "longest_cycle_km", "lactate_threshold_hr", "lactate_threshold_pace",
                  "max_heart_rate", "resting_heart_rate", "longest_run_km",
                  "race_predict_5k", "race_predict_10k", "race_predict_half", "race_predict_full"):
            if k in url_data and url_data[k] not in (None, ""):
                result[k]["value"] = url_data[k]
                if k == "username":
                    result[k]["note"] = "Training Hub URL.dashboard"
                elif k in ("longest_cycle_km",):
                    date = url_data.get("longest_cycle_date", "")
                    result[k]["note"] = f"Training Hub URL 个人骑行纪录（全部/all-time） {date}".strip()
                elif k in ("longest_run_km",):
                    date = url_data.get("longest_run_date", "")
                    result[k]["note"] = f"Training Hub URL 个人跑步纪录（全部/all-time） {date}".strip()
                elif k.startswith("race_predict_"):
                    result[k]["note"] = "Training Hub URL 成绩预测面板"

    # ---------- 标注不可获取字段 ----------
    for k, reason in UNAVAILABLE.items():
        if result[k]["value"] is None:
            result[k]["note"] = reason

    # 输出
    return [result[f] for f in FIELDS]


def main():
    args = sys.argv[1:]
    sync_mode = "sync" in args or "同步用户画像" in args

    profile = build_profile()

    if sync_mode:
        # 严格只返回 JSON 数组
        print(json.dumps(profile, ensure_ascii=False, indent=2))
    else:
        # 普通模式：JSON + 简表
        print(json.dumps(profile, ensure_ascii=False, indent=2))
        # 简表
        print("\n=== 字段可获取性 ===", file=sys.stderr)
        obtained = sum(1 for f in profile if f["value"] is not None)
        print(f"已获取: {obtained}/{len(profile)}", file=sys.stderr)
        for f in profile:
            if f["value"] is None:
                print(f"  ✗ {f['metric']}: {f.get('note', '未知')}", file=sys.stderr)


if __name__ == "__main__":
    main()
