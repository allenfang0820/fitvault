"""
轨迹文件解析（GPX / FIT / KML）与坡度计算，供 pywebview js_api 调用。
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fit_engine import FITCoreEngine, FIT_PARSE_LOG_PATH
from utils.weather_api import fetch_historical_weather

EARTH_R = 6371000.0

SUPPORTED_SPORT_TYPES = {
    "running",
    "hiking",
    "mountaineering",
    "cycling",
    "swimming",
    "walking",
    "driving",
    "trail_running",
    "treadmill_running",
    "road_cycling",
    "mountain_biking",
    "stair_climbing",
    "indoor_climbing",
    "rock_climbing",
    "elliptical",
    "rowing",
    "gravel_cycling",
    "e_biking",
    "e_mountain_biking",
    "cross_country_skiing",
    "alpine_skiing",
    "snowboarding",
    "snowshoeing",
}

SPORT_TYPE_ALIASES = {
    "run": "running",
    "running": "running",
    "jogging": "running",
    "runner": "running",
    "跑步": "running",
    "慢跑": "running",
    "trail_run": "trail_running",
    "trail_running": "trail_running",
    "trail running": "trail_running",
    "trailrun": "trail_running",
    "越野跑": "trail_running",
    "treadmill": "treadmill_running",
    "treadmill_running": "treadmill_running",
    "treadmill running": "treadmill_running",
    "indoor_running": "treadmill_running",
    "indoor run": "treadmill_running",
    "室内跑步": "treadmill_running",
    "bike": "cycling",
    "biking": "cycling",
    "cycling": "cycling",
    "cycle": "cycling",
    "骑行": "cycling",
    "自行车": "cycling",
    "road_biking": "road_cycling",
    "road_bike": "road_cycling",
    "road_cycling": "road_cycling",
    "road": "road_cycling",
    "road cycling": "road_cycling",
    "公路骑行": "road_cycling",
    "mountain_biking": "mountain_biking",
    "mountain_bike": "mountain_biking",
    "mountain": "mountain_biking",
    "mountain biking": "mountain_biking",
    "mtb": "mountain_biking",
    "山地骑行": "mountain_biking",
    "gravel_cycling": "gravel_cycling",
    "gravel": "gravel_cycling",
    "track_cycling": "track_cycling",
    "hand_cycling": "hand_cycling",
    "e_biking": "e_biking",
    "e_bike_fitness": "e_biking",
    "e_bike_mountain": "e_mountain_biking",
    "e_bike_enduro": "e_mountain_biking",
    "swim": "swimming",
    "swimming": "swimming",
    "open_water_swimming": "swimming",
    "lap_swimming": "swimming",
    "游泳": "swimming",
    "hike": "hiking",
    "hiking": "hiking",
    "mountaineering": "mountaineering",
    "alpine": "mountaineering",
    "floor_climbing": "stair_climbing",
    "stair_climbing": "stair_climbing",
    "stair climbing": "stair_climbing",
    "stairs": "stair_climbing",
    "floor climbing": "stair_climbing",
    "爬楼": "stair_climbing",
    "爬楼梯": "stair_climbing",
    "楼梯": "stair_climbing",
    "indoor_climbing": "indoor_climbing",
    "rock_climbing": "rock_climbing",
    "climbing": "climbing",
    "登山": "mountaineering",
    "高山": "mountaineering",
    "登山运动": "mountaineering",
    "徒步": "hiking",
    "爬山": "hiking",
    "walking": "walking",
    "walk": "walking",
    "indoor_walking": "indoor_walking",
    "casual_walking": "walking",
    "speed_walking": "walking",
    "步行": "walking",
    "健走": "walking",
    "elliptical": "elliptical",
    "椭圆机": "elliptical",
    "rowing": "rowing",
    "indoor_rowing": "rowing",
    "划船": "rowing",
    "cross_country_skiing": "cross_country_skiing",
    "skate_skiing": "cross_country_skiing",
    "alpine_skiing": "alpine_skiing",
    "indoor_skiing": "skiing",
    "snowboarding": "snowboarding",
    "snowshoeing": "snowshoeing",
    "cardio": "cardio",
    "cardio_training": "cardio",
    "fitness_equipment": "cardio",
    "fitness equipment": "cardio",
    "indoor_cardio": "cardio",
    "drive": "driving",
    "driving": "driving",
    "驾车": "driving",
    "开车": "driving",
}

SPORT_TYPE_NUMERIC_ALIASES = {
    "1": "running",
    "2": "cycling",
    "3": "hiking",
    "4": "swimming",
    "10": "walking",
    "14": "treadmill_running",
    "22": "trail_running",
    "24": "mountain_biking",
    "53": "road_cycling",
    "57": "driving",
}

SPORT_TYPE_KEYWORDS = (
    ("stair_climbing", ("stair", "stairs", "floor_climbing", "floor climbing", "爬楼", "爬楼梯", "楼梯")),
    ("rock_climbing", ("rock_climbing", "rock climbing", "攀岩")),
    ("indoor_climbing", ("indoor_climbing", "indoor climbing")),
    ("treadmill_running", ("treadmill", "indoor_run", "indoor running", "室内跑")),
    ("trail_running", ("trail", "cross_country_running", "越野跑")),
    ("gravel_cycling", ("gravel", "砾石")),
    ("road_cycling", ("road", "公路")),
    ("mountain_biking", ("mountain", "mtb", "山地")),
    ("swimming", ("swim", "游泳")),
    ("cycling", ("bike", "bik", "cycl", "骑行", "自行车")),
    ("elliptical", ("elliptical", "椭圆机")),
    ("rowing", ("rowing", "row", "划船")),
    ("cross_country_skiing", ("cross_country_skiing", "skate_skiing", "越野滑雪")),
    ("alpine_skiing", ("alpine_skiing", "高山滑雪")),
    ("snowboarding", ("snowboarding", "单板滑雪")),
    ("snowshoeing", ("snowshoeing", "雪鞋")),
    ("cardio", ("cardio", "aerobic", "fitness_equipment", "有氧")),
    ("mountaineering", ("mountaineering", "alpine", "high_mountain", "高山", "登山运动")),
    ("hiking", ("hike", "hiking", "trek", "徒步", "爬山")),
    ("walking", ("walk", "步行", "健走")),
    # § 修子串误判:driving 放在最末位,精确词 driv/drive/driving/驾车/开车,严禁"car"/"auto"
    ("driving", ("driv", "驾车", "开车")),
    ("running", ("run", "jog", "跑")),
)

FIT_SUB_SPORT_TO_SPORT_TYPE = {
    "trail": "trail_running",
    "track_running": "running",
    "street": "running",
    "treadmill": "treadmill_running",
    "indoor_running": "treadmill_running",
    "road": "road_cycling",
    "mountain": "mountain_biking",
    "downhill": "mountain_biking",
    "indoor_cycling": "cycling",
    "spin": "cycling",
    "gravel_cycling": "gravel_cycling",
    "track_cycling": "track_cycling",
    "hand_cycling": "hand_cycling",
    "e_bike_fitness": "e_biking",
    "e_bike_mountain": "e_mountain_biking",
    "e_bike_enduro": "e_mountain_biking",
    "lap_swimming": "swimming",
    "open_water": "swimming",
    "stair_climbing": "stair_climbing",
    "indoor_climbing": "indoor_climbing",
    "floor_climbing": "stair_climbing",
    "indoor_walking": "indoor_walking",
    "casual_walking": "walking",
    "speed_walking": "walking",
    "elliptical": "elliptical",
    "indoor_rowing": "rowing",
    "indoor_skiing": "skiing",
    "skate_skiing": "cross_country_skiing",
    "yoga": "yoga",
    "pilates": "pilates",
    "strength_training": "strength_training",
    "cardio_training": "cardio",
    "breathing": "breathing",
    "hiit": "hiit",
}

GPX_TYPE_TAGS = {"type", "sport", "activity", "activitytype", "activity_type", "category"}


def _sport_text(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _looks_like_invalid_sport_token(value: str) -> bool:
    token = str(value or "").strip().lower()
    return any(marker in token for marker in (".fit", ".gpx", ".kml", "/", "\\"))


def normalize_sport_type(value: Any, sub_value: Any = None) -> str | None:
    raw = _sport_text(value)
    sub_raw = _sport_text(sub_value)
    if _looks_like_invalid_sport_token(raw):
        raw = ""
    if _looks_like_invalid_sport_token(sub_raw):
        sub_raw = ""
    if sub_raw in FIT_SUB_SPORT_TO_SPORT_TYPE:
        return FIT_SUB_SPORT_TO_SPORT_TYPE[sub_raw]
    for candidate in (sub_raw, raw, f"{raw}_{sub_raw}".strip("_"), f"{raw} {sub_raw}".strip()):
        if not candidate or candidate in {"unknown", "none", "null"}:
            continue
        if candidate in SPORT_TYPE_NUMERIC_ALIASES:
            return SPORT_TYPE_NUMERIC_ALIASES[candidate]
        if candidate in SPORT_TYPE_ALIASES:
            return SPORT_TYPE_ALIASES[candidate]
    combined = " ".join(part for part in (raw, sub_raw) if part)
    for sport_type, keywords in SPORT_TYPE_KEYWORDS:
        if any(keyword in combined for keyword in keywords):
            return sport_type
            
    # Preserve the original unmapped type if it exists, rather than forcing None
    if raw and raw not in {"unknown", "none", "null"}:
        return raw
        
    return None


def infer_sport_type_from_points(points: list[dict[str, Any]]) -> str | None:
    if len(points) < 2:
        return None
    dist_m = 0.0
    gain_m = 0.0
    for i in range(1, len(points)):
        p0, p1 = points[i - 1], points[i]
        dist_m += haversine_m(p0["lat"], p0["lon"], p1["lat"], p1["lon"])
        alt_gain = float(p1.get("alt") or 0) - float(p0.get("alt") or 0)
        if alt_gain > 0:
            gain_m += alt_gain
    timed_points = [p for p in points if p.get("time")]
    duration_sec = 0.0
    if len(timed_points) >= 2:
        try:
            first = datetime.fromisoformat(str(timed_points[0]["time"]).replace("Z", "+00:00"))
            last = datetime.fromisoformat(str(timed_points[-1]["time"]).replace("Z", "+00:00"))
            duration_sec = max((last - first).total_seconds(), 0.0)
        except ValueError:
            duration_sec = 0.0
    if duration_sec <= 0 or dist_m <= 0:
        return "hiking" if gain_m >= 500 else None
    speed_kmh = dist_m / duration_sec * 3.6
    gain_per_km = gain_m / max(dist_m / 1000.0, 0.001)
    if speed_kmh >= 35:
        return "driving"
    if speed_kmh >= 18:
        return "cycling"
    if speed_kmh >= 8:
        return "trail_running" if gain_per_km >= 80 else "running"
    if speed_kmh >= 5.5:
        return "hiking" if gain_per_km >= 80 else "running"
    if gain_per_km >= 180:
        return "mountaineering"
    if gain_per_km >= 80:
        return "hiking"
    return "walking"


def enrich_sport_metadata(data: dict[str, Any], sport_raw: Any = None, sub_sport_raw: Any = None) -> dict[str, Any]:
    points = data.get("points") or []
    activity_type = normalize_sport_type(sport_raw, sub_sport_raw)
    if activity_type is None:
        activity_type = infer_sport_type_from_points(points)
    data["activity_type"] = activity_type or "unknown"
    data["sport_type"] = data["activity_type"]
    data["fit_sport"] = sport_raw if sport_raw is not None else data["activity_type"]
    data["fit_sub_sport"] = sub_sport_raw if sub_sport_raw is not None else "unknown"
    return data


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return EARTH_R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _iso(dt: Any) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return str(dt)


def _gpx_hr_from_extensions(extensions: list[Any]) -> int | None:
    for el in extensions or []:
        tag = getattr(el, "tag", "") or ""
        local = tag.split("}")[-1].lower()
        if local == "hr":
            try:
                return int(float(el.text))
            except (TypeError, ValueError):
                continue
        if hasattr(el, "iter"):
            for child in el.iter():
                ct = (getattr(child, "tag", "") or "").split("}")[-1].lower()
                if ct == "hr" and child.text:
                    try:
                        return int(float(child.text))
                    except (TypeError, ValueError):
                        continue
    return None


def _local_name(tag: Any) -> str:
    return (str(tag or "").split("}")[-1] or "").strip().lower().replace("-", "_")


def _gpx_type_from_extensions(extensions: list[Any]) -> str | None:
    for el in extensions or []:
        nodes = list(el.iter()) if hasattr(el, "iter") else [el]
        for node in nodes:
            local = _local_name(getattr(node, "tag", ""))
            text = str(getattr(node, "text", "") or "").strip()
            if local in GPX_TYPE_TAGS and text:
                sport_type = normalize_sport_type(text)
                if sport_type:
                    return sport_type
            for attr_value in getattr(node, "attrib", {}).values():
                sport_type = normalize_sport_type(attr_value)
                if sport_type:
                    return sport_type
    return None


def _extract_gpx_sport_type(gpx: Any) -> str | None:
    candidates: list[Any] = []
    for attr in ("type", "sport", "activity", "category"):
        value = getattr(gpx, attr, None)
        if value:
            candidates.append(value)
    for track in getattr(gpx, "tracks", []) or []:
        for attr in ("type", "name", "description"):
            value = getattr(track, attr, None)
            if value:
                candidates.append(value)
        sport_type = _gpx_type_from_extensions(getattr(track, "extensions", []) or [])
        if sport_type:
            return sport_type
    for route in getattr(gpx, "routes", []) or []:
        for attr in ("type", "name", "description"):
            value = getattr(route, attr, None)
            if value:
                candidates.append(value)
        sport_type = _gpx_type_from_extensions(getattr(route, "extensions", []) or [])
        if sport_type:
            return sport_type
    sport_type = _gpx_type_from_extensions(getattr(gpx, "extensions", []) or [])
    if sport_type:
        return sport_type
    for candidate in candidates:
        sport_type = normalize_sport_type(candidate)
        if sport_type:
            return sport_type
    return None


def attach_slopes(points: list[dict[str, Any]]) -> None:
    """为每个点写入 slope_pct：自上一轨迹点至当前点的坡度（%，水平距离 >5m 时与前端统计口径一致）。"""
    if not points:
        return
    points[0]["slope_pct"] = None
    if points[0].get("dist_km") is None:
        points[0]["dist_km"] = 0.0
    if points[0].get("dist") is None:
        points[0]["dist"] = 0.0
    cumulative_km = float(points[0].get("dist_km") or points[0].get("dist") or 0.0)
    for i in range(1, len(points)):
        p0, p1 = points[i - 1], points[i]
        dist_m = haversine_m(p0["lat"], p0["lon"], p1["lat"], p1["lon"])
        if p1.get("dist_km") is None and p1.get("dist") is None:
            cumulative_km += dist_m / 1000.0
            p1["dist_km"] = cumulative_km
            p1["dist"] = cumulative_km
        else:
            cumulative_km = float(p1.get("dist_km") if p1.get("dist_km") is not None else p1.get("dist") or cumulative_km)
            if p1.get("dist_km") is None:
                p1["dist_km"] = cumulative_km
            if p1.get("dist") is None:
                p1["dist"] = cumulative_km
        d_alt = float(p1["alt"]) - float(p0["alt"])
        if dist_m > 5:
            p1["slope_pct"] = (d_alt / dist_m) * 100.0
        else:
            p1["slope_pct"] = None


def parse_gpx_file(path: Path) -> dict[str, Any]:
    import gpxpy

    try:
        with open(path, "rb") as f:
            gpx = gpxpy.parse(f)
    except Exception as exc:
        raise ValueError(f"GPX 文件解析失败，可能格式损坏或不是合法的 GPX 文件: {exc}")

    points: list[dict[str, Any]] = []
    for track in gpx.tracks:
        for seg in track.segments:
            for p in seg.points:
                if p.latitude is None or p.longitude is None:
                    continue
                try:
                    time_str = _iso(p.time)
                except Exception as exc:
                    raise ValueError(f"GPX 轨迹点时间解析异常: {exc}")
                
                points.append(
                    {
                        "lat": float(p.latitude),
                        "lon": float(p.longitude),
                        "alt": float(p.elevation) if p.elevation is not None else 0.0,
                        "time": time_str,
                        "hr": _gpx_hr_from_extensions(getattr(p, "extensions", []) or []),
                    }
                )

    placemarks: list[dict[str, Any]] = []
    for i, w in enumerate(gpx.waypoints):
        if w.latitude is None or w.longitude is None:
            continue
        name = (w.name or "").strip() or f"打卡点 {i + 1}"
        placemarks.append(
            {
                "id": f"cp_gpx_{i}",
                "name": name,
                "lat": float(w.latitude),
                "lon": float(w.longitude),
                "alt": float(w.elevation) if w.elevation is not None else 0.0,
            }
        )

    return enrich_sport_metadata({"points": points, "placemarks": placemarks}, _extract_gpx_sport_type(gpx))


def parse_fit_file(path: Path) -> dict[str, Any]:
    """通过中央 FIT 解析引擎返回标准化后的 APP 轨迹结构。"""
    core = FITCoreEngine.parse_fit_file(path)
    basic = dict(core.get("basic_info") or {})
    track_data = [dict(point) for point in (core.get("track_data") or [])]
    data = enrich_sport_metadata(
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
    data["fit_sport"] = basic.get("sport")
    data["fit_sub_sport"] = basic.get("sub_sport")
    first_point = track_data[0] if track_data else {}
    data["weather"] = fetch_historical_weather(
        first_point.get("lat"),
        first_point.get("lon"),
        basic.get("start_time") or basic.get("start_time_utc") or first_point.get("time"),
    )
    return data


def _parse_kml_coord_tokens(tag_local: str, text: str) -> list[dict[str, float]]:
    pts: list[dict[str, float]] = []
    text = (text or "").strip()
    if not text:
        return pts

    if tag_local == "coord":
        for line in text.splitlines():
            for chunk in line.split():
                parts = chunk.replace(",", " ").split()
                if len(parts) >= 2:
                    try:
                        lon, lat = float(parts[0]), float(parts[1])
                        alt = float(parts[2]) if len(parts) > 2 else 0.0
                        pts.append({"lon": lon, "lat": lat, "alt": alt})
                    except (ValueError, IndexError):
                        continue
        return pts

    for triple in re.split(r"\s+", text.replace("\n", " ").replace("\r", " ").strip()):
        if not triple:
            continue
        parts = triple.split(",")
        if len(parts) >= 2:
            try:
                lon, lat = float(parts[0]), float(parts[1])
                alt = float(parts[2]) if len(parts) > 2 else 0.0
                pts.append({"lon": lon, "lat": lat, "alt": alt})
            except (ValueError, IndexError):
                continue
    return pts


def parse_kml_file(path: Path) -> dict[str, Any]:
    tree = ET.parse(path)
    root = tree.getroot()
    best: tuple[int, str, str] = (0, "", "")
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag not in ("coordinates", "coord"):
            continue
        txt = (el.text or "").strip()
        if len(txt) > best[0]:
            best = (len(txt), tag, txt)

    if best[0] == 0:
        return {"points": [], "placemarks": []}

    _, tag_local, text = best
    raw_pts = _parse_kml_coord_tokens(tag_local, text)
    points = [
        {"lat": p["lat"], "lon": p["lon"], "alt": p["alt"], "time": None, "hr": None} for p in raw_pts
    ]
    return enrich_sport_metadata({"points": points, "placemarks": []})


def parse_track_file(path: str | Path) -> dict[str, Any]:
    p = Path(path).expanduser().resolve()
    ext = p.suffix.lower()
    if ext not in (".gpx", ".fit", ".kml"):
        raise ValueError(
            f"不支持的格式: {ext}（仅支持 .gpx / .fit / .kml）。"
        )
    if not p.exists():
        raise FileNotFoundError(f"文件不存在: {p}")
    if not p.is_file():
        raise ValueError(f"路径不是文件: {p}")

    try:
        if ext == ".gpx":
            data = parse_gpx_file(p)
        elif ext == ".fit":
            data = parse_fit_file(p)
        else:
            data = parse_kml_file(p)
    except FileNotFoundError:
        raise
    except ValueError:
        raise
    except Exception as exc:
        raise RuntimeError(f"解析失败 [{ext}]: {exc}") from exc

    if not data.get("points"):
        raise ValueError("文件中未解析到有效轨迹点（需含经纬度）。")

    attach_slopes(data["points"])
    return data
