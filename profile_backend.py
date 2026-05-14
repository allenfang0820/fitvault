"""
个人运动画像后端：SQLite 存储 + HRR 心率区间 + 有氧解耦 + MCP 联调同步。
"""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import sys
if getattr(sys, "frozen", False):
    DB_PATH = Path.home() / ".hiking_track_ai" / "user_profile.db"
else:
    DB_PATH = Path(__file__).resolve().parent / "user_profile.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


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
            updated_at  TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS activities (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            filename       TEXT,
            sport_type     TEXT,
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
            updated_at     TEXT DEFAULT (datetime('now'))
        )
    """)
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
        }


def get_profile() -> UserProfile:
    conn = _conn()
    row = conn.execute("SELECT * FROM user_profile ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    if row is None:
        return UserProfile(None, None, None, None, None, None, None, None)
    return UserProfile(
        name=row["name"],
        gender=row["gender"],
        age=row["age"],
        weight=row["weight"],
        resting_hr=row["resting_hr"],
        max_hr=row["max_hr"],
        hrv_baseline=row["hrv_baseline"],
        vo2max=row["vo2max"],
    )


def upsert_profile(data: dict[str, Any]) -> UserProfile:
    conn = _conn()
    conn.execute("DELETE FROM user_profile")
    conn.execute(
        """
        INSERT INTO user_profile
            (name, gender, age, weight, resting_hr, max_hr, hrv_baseline, vo2max)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
    )


def save_activity(data: dict[str, Any]) -> int:
    conn = _conn()
    cur = conn.execute(
        """
        INSERT INTO activities
            (filename, sport_type, dist_km, duration_sec, gain_m, max_alt_m,
             avg_hr, max_hr, avg_cadence, hr_decoupling, tss, points_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data.get("filename"),
            data.get("sport_type"),
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
        ),
    )
    conn.commit()
    aid = cur.lastrowid
    conn.close()
    return aid


def get_activities(limit: int = 20) -> list[dict[str, Any]]:
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM activities ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


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


def fetch_mcp_persona(platform: str) -> dict[str, Any]:
    """
    通过普通 /v1/chat/completions 接口，让大模型作为数据提取助手
    依次调用高驰/佳明 MCP 工具，获取生理档案并更新本地数据库。
    platform: 'garmin' | 'coros'
    """
    if platform not in ("garmin", "coros"):
        return {"ok": False, "error": "不支持的平台，仅支持 garmin / coros"}

    import llm_backend

    cfg = llm_backend.load_llm_config()
    url = (cfg.get("url") or "").strip() or "http://localhost:3000/v1/chat/completions"
    model = (cfg.get("model") or "openclaw").strip()
    api_key = str(cfg.get("api_key") or "")

    if platform == "coros":
        system_prompt = (
            "你是一个严格的数据提取助手。请依次调用挂载的高驰 COROS MCP 工具："
            "queryUserInfo、queryRestingHeartRate、queryHrvAssessment、queryFitnessAssessmentOverview。 "
            "获取用户的年龄(age)、性别(gender)、静息心率(restingHeartRate)、最新 HRV 评估数值(hrv_baseline)以及 VO2max。 "
            "绝对不要输出任何解释性文字，只严格输出一个纯 JSON 字符串，格式如下："
            '{"age":整数,"gender":"男或女","resting_hr":整数,"hrv_baseline":浮点数,"vo2max":浮点数}'
        )
    else:
        system_prompt = (
            "你是一个严格的数据提取助手。请依次调用挂载的佳明 Garmin MCP 工具："
            "queryUserInfo、queryRestingHeartRate、queryHrvAssessment、queryFitnessAssessmentOverview。 "
            "获取用户的年龄(age)、性别(gender)、静息心率(restingHeartRate)、最新 HRV 评估数值(hrv_baseline)以及 VO2max。 "
            "绝对不要输出任何解释性文字，只严格输出一个纯 JSON 字符串，格式如下："
            '{"age":整数,"gender":"男或女","resting_hr":整数,"hrv_baseline":浮点数,"vo2max":浮点数}'
        )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "请提取我的最新生理数据"},
    ]

    try:
        text = llm_backend.chat_completions(
            url=url,
            api_key=api_key,
            model=model,
            messages=messages,
            session_id="mcp_persona_" + platform,
            timeout=120,
        )

        json_str = text.strip()
        if json_str.startswith("```"):
            lines = json_str.split("\n")
            json_str = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

        persona = json.loads(json_str)

        profile_data = {
            "name": persona.get("name"),
            "gender": persona.get("gender"),
            "age": persona.get("age"),
            "weight": persona.get("weight"),
            "resting_hr": persona.get("resting_hr"),
            "max_hr": persona.get("max_hr"),
            "hrv_baseline": persona.get("hrv_baseline"),
            "vo2max": persona.get("vo2max"),
        }
        upsert_profile(profile_data)
        return {"ok": True, "persona": profile_data}

    except json.JSONDecodeError as e:
        return {"ok": False, "error": f"JSON 解析失败: {e}\n原始返回: {text[:500] if 'text' in dir() else 'N/A'}"}
    except Exception as e:
        return {"ok": False, "error": f"MCP 同步失败: {e}"}