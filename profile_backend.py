"""
个人运动画像后端：SQLite 存储 + HRR 心率区间 + 有氧解耦 + MCP 联调同步。
"""

from __future__ import annotations

import json
import math
import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import sys
if getattr(sys, "frozen", False):
    _BASE = Path.home() / ".hiking_track_ai"
else:
    _BASE = Path(__file__).resolve().parent

DB_PATH = _BASE / "user_profile.db"
TRACKS_DIR = _BASE / "local_tracks"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def tracks_dir() -> Path:
    """返回本地轨迹存储目录（启动时自动创建）。"""
    TRACKS_DIR.mkdir(parents=True, exist_ok=True)
    return TRACKS_DIR


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    _init_schema(conn)
    return conn


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
            updated_at     TEXT DEFAULT (datetime('now'))
        )
    """)

    for col, dtype in [("sub_sport_type", "TEXT"), ("file_path", "TEXT")]:
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
    ]:
        try:
            conn.execute(f"ALTER TABLE user_profile ADD COLUMN {col} {dtype}")
        except Exception:
            pass
    conn.commit()


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "gender": self.gender,
            "age": self.age,
            "weight": self.weight,
            "resting_hr": self.resting_hr,
            "max_hr": self.max_hr,
            "hrv_baseline": self.hrv_baseline,
            "vo2max": self.vo2max,
            "avg_sleep_hours": self.avg_sleep_hours,
            "longest_hike_km": self.longest_hike_km,
            "height_cm": self.height_cm,
            "pb_5km": self.pb_5km,
            "pb_10km": self.pb_10km,
            "pb_half_marathon": self.pb_half_marathon,
            "pb_full_marathon": self.pb_full_marathon,
            "lactate_threshold_hr": self.lactate_threshold_hr,
            "ftp_watts": self.ftp_watts,
        }


def get_profile() -> UserProfile:
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
    )


def upsert_profile(data: dict[str, Any]) -> UserProfile:
    conn = _conn()
    conn.execute("DELETE FROM user_profile")
    conn.execute(
        """
        INSERT INTO user_profile
            (name, gender, age, weight, resting_hr, max_hr, hrv_baseline, vo2max,
             avg_sleep_hours, longest_hike_km, height_cm, pb_5km, pb_10km, pb_half_marathon,
             pb_full_marathon, lactate_threshold_hr, ftp_watts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        ),
    )
    conn.commit()
    conn.close()
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
    )


def save_activity(data: dict[str, Any]) -> int:
    conn = _conn()
    cur = conn.execute(
        """
        INSERT INTO activities
            (filename, sport_type, sub_sport_type, dist_km, duration_sec, gain_m, max_alt_m,
             avg_hr, max_hr, avg_cadence, hr_decoupling, tss, points_json, file_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data.get("filename"),
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
        ),
    )
    conn.commit()
    aid = cur.lastrowid
    conn.close()
    return aid


def get_activity_history(limit: int = 50) -> list[dict[str, Any]]:
    """按时间倒序返回所有历史运动记录（包含 file_path）。"""
    conn = _conn()
    rows = conn.execute(
        """
        SELECT id, filename, sport_type, sub_sport_type, dist_km, duration_sec, gain_m,
               max_alt_m, avg_hr, max_hr, file_path, updated_at
        FROM activities ORDER BY id DESC LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def load_local_track(file_path: str) -> dict[str, Any]:
    """根据本地路径读取并解析轨迹文件，返回与 parse_track_file 一致的结构。"""
    import track_backend
    p = Path(file_path)
    if not p.is_file():
        return {"ok": False, "error": f"文件不存在: {file_path}"}
    try:
        data = track_backend.parse_track_file(str(p))
        return {"ok": True, "filename": p.name, "data": data}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def copy_track_to_local(src_path: str) -> str:
    """将源轨迹文件复制到 local_tracks 目录，以 filename 为基础生成唯一文件名，返回本地路径。"""
    src = Path(src_path)
    dest_dir = tracks_dir()
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
            "【输出格式】输出一个完整 JSON，绝对不输出任何其他文字：\n"
            "{\n"
            '  "longest_hike_km": 浮点数或null,\n'
            '  "name": "字符串或null",\n'
            '  "age": 整数或null,\n'
            '  "gender": "字符串或null",\n'
            '  "weight": 浮点数或null,\n'
            '  "vo2max": 浮点数或null,\n'
            '  "avg_sleep_hours": 浮点数或null\n'
            "}"
        )
        messages = [
            {"role": "system", "content": step1_prompt},
            {"role": "user", "content": "请立即执行上述两步数据提取和计算任务。"},
        ]
    else:
        messages = [
            {"role": "user", "content": "运行get_garmin_stats.py，并直接输出其返回的完整JSON数组。请勿输出任何其他文字，只输出JSON数组。"}
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
            }

        upsert_profile(profile_data)
        return {"ok": True, "persona": profile_data}

    except json.JSONDecodeError as e:
        return {"ok": False, "error": f"JSON 解析失败: {e}\n原始返回: {text[:500] if 'text' in dir() else 'N/A'}"}
    except Exception as e:
        return {"ok": False, "error": f"MCP 同步失败: {e}"}