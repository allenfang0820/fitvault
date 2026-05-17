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

EARTH_R = 6371000.0
SEMICIRCLE_SCALE = 180.0 / (1 << 31)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return EARTH_R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _fit_latlon_to_deg(lat: float, lon: float) -> tuple[float, float]:
    """FIT 中 position_lat/position_long 通常为 semicircle；若已是度则原样返回。"""
    if abs(lat) <= 90 and abs(lon) <= 180:
        return lat, lon
    return lat * SEMICIRCLE_SCALE, lon * SEMICIRCLE_SCALE


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


def attach_slopes(points: list[dict[str, Any]]) -> None:
    """为每个点写入 slope_pct：自上一轨迹点至当前点的坡度（%，水平距离 >5m 时与前端统计口径一致）。"""
    if not points:
        return
    points[0]["slope_pct"] = None
    for i in range(1, len(points)):
        p0, p1 = points[i - 1], points[i]
        dist_m = haversine_m(p0["lat"], p0["lon"], p1["lat"], p1["lon"])
        d_alt = float(p1["alt"]) - float(p0["alt"])
        if dist_m > 5:
            p1["slope_pct"] = (d_alt / dist_m) * 100.0
        else:
            p1["slope_pct"] = None


def parse_gpx_file(path: Path) -> dict[str, Any]:
    import gpxpy

    with open(path, "rb") as f:
        gpx = gpxpy.parse(f)

    points: list[dict[str, Any]] = []
    for track in gpx.tracks:
        for seg in track.segments:
            for p in seg.points:
                if p.latitude is None or p.longitude is None:
                    continue
                points.append(
                    {
                        "lat": float(p.latitude),
                        "lon": float(p.longitude),
                        "alt": float(p.elevation) if p.elevation is not None else 0.0,
                        "time": _iso(p.time),
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

    return {"points": points, "placemarks": placemarks}


def parse_fit_file(path: Path) -> dict[str, Any]:
    """解析 FIT 文件，提取位置/海拔/心率/速度/里程等核心字段，与 GPX 输出结构完全兼容。"""
    from fitparse import FitFile

    fit = FitFile(str(path))
    fit.check_crc = True

    rows: list[dict[str, Any]] = []
    for msg in fit.get_messages("record"):
        vals = {d.name: d.value for d in msg.fields}
        lat = vals.get("position_lat")
        lon = vals.get("position_long")
        if lat is None or lon is None:
            continue

        latf, lonf = _fit_latlon_to_deg(float(lat), float(lon))

        ts = vals.get("timestamp")
        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            tiso = _iso(ts)
        else:
            tiso = None

        alt_raw = vals.get("enhanced_altitude") or vals.get("altitude")
        altf = float(alt_raw) if alt_raw is not None else 0.0

        hr_val = vals.get("heart_rate")
        hr = int(hr_val) if hr_val is not None else None

        dist_raw = vals.get("distance")
        dist_m = float(dist_raw) if dist_raw is not None else None

        spd_raw = vals.get("speed")
        spd_ms = float(spd_raw) if spd_raw is not None else None

        pwr_raw = vals.get("power")
        pwr = int(pwr_raw) if pwr_raw is not None else None

        cad_raw = vals.get("cadence")
        cad = int(cad_raw) if cad_raw is not None else None

        temp_raw = vals.get("temperature")
        temp = float(temp_raw) if temp_raw is not None else None

        rows.append({
            "_ts": ts,
            "lat": latf,
            "lon": lonf,
            "alt": altf,
            "time": tiso,
            "hr": hr,
            "dist_m": dist_m,
            "speed_ms": spd_ms,
            "power": pwr,
            "cadence": cad,
            "temperature": temp,
        })

    rows.sort(key=lambda r: r["_ts"] or datetime.min.replace(tzinfo=timezone.utc))

    min_dt = datetime.min.replace(tzinfo=timezone.utc)
    points: list[dict[str, Any]] = []
    for row in rows:
        la, lo = row["lat"], row["lon"]
        tiso = row["time"]
        if points:
            q = points[-1]
            if abs(q["lat"] - la) < 1e-7 and abs(q["lon"] - lo) < 1e-7 and q.get("time") == tiso:
                continue
        points.append({
            "lat": la,
            "lon": lo,
            "alt": row["alt"],
            "time": tiso,
            "hr": row["hr"],
        })

    return {"points": points, "placemarks": []}


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
    return {"points": points, "placemarks": []}


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
            data = _parse_fit_with_error_handling(p)
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


def _parse_fit_with_error_handling(path: Path) -> dict[str, Any]:
    """解析 FIT 文件，带完整异常处理。"""
    from fitparse import FitFile, FitParseError

    try:
        fit = FitFile(str(path), check_crc=True)
    except FitParseError as e:
        err_str = str(e).lower()
        if "header" in err_str or "signature" in err_str or "corrupt" in err_str:
            raise ValueError(
                f"FIT 文件损坏或已截断，无法解析。可能原因：文件传输不完整。"
            ) from e
        if "version" in err_str or "protocol" in err_str:
            raise ValueError(
                f"FIT 文件版本不受支持: {e}"
            ) from e
        raise ValueError(f"FIT 文件解析失败: {e}") from e
    except OSError as e:
        raise ValueError(f"无法读取 FIT 文件（权限或路径问题）: {e}") from e

    rows: list[dict[str, Any]] = []
    file_version: str | None = None
    fit_sport: str | None = None
    fit_sub_sport: str | None = None

    for msg in fit.get_messages("file_id"):
        if file_version is None:
            for field in msg.fields:
                if field.name == "type":
                    file_version = str(field.value)
                    break

    for msg in fit.get_messages("session"):
        if fit_sport is None or fit_sub_sport is None:
            sport_rec = msg.get_value("sport")
            sub_sport_rec = msg.get_value("sub_sport")
            if sport_rec is not None:
                fit_sport = str(sport_rec).strip().lower()
            if sub_sport_rec is not None:
                fit_sub_sport = str(sub_sport_rec).strip().lower()
            break

    if fit_sport is None:
        for msg in fit.get_messages("sport"):
            sport_rec = msg.get_value("sport")
            if sport_rec is not None:
                fit_sport = str(sport_rec).strip().lower()
                break

    for msg in fit.get_messages("record"):
        vals = {d.name: d.value for d in msg.fields}
        lat = vals.get("position_lat")
        lon = vals.get("position_long")
        if lat is None or lon is None:
            continue

        try:
            latf, lonf = _fit_latlon_to_deg(float(lat), float(lon))
        except (ValueError, TypeError):
            continue

        ts = vals.get("timestamp")
        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            tiso = _iso(ts)
        else:
            tiso = None

        alt_raw = vals.get("enhanced_altitude") or vals.get("altitude")
        altf = float(alt_raw) if alt_raw is not None else 0.0

        hr_val = vals.get("heart_rate")
        hr = int(hr_val) if hr_val is not None else None

        rows.append({
            "_ts": ts,
            "lat": latf,
            "lon": lonf,
            "alt": altf,
            "time": tiso,
            "hr": hr,
        })

    if not rows:
        raise ValueError(
            "FIT 文件中未找到有效的轨迹记录（position_lat/position_long 字段为空）。"
            "可能原因：文件不包含 GPS 数据（如仅含健身房训练记录）。"
        )

    rows.sort(key=lambda r: r["_ts"] or datetime.min.replace(tzinfo=timezone.utc))

    points: list[dict[str, Any]] = []
    for row in rows:
        la, lo, tiso = row["lat"], row["lon"], row["time"]
        if points:
            q = points[-1]
            if abs(q["lat"] - la) < 1e-7 and abs(q["lon"] - lo) < 1e-7 and q.get("time") == tiso:
                continue
        points.append({
            "lat": la,
            "lon": lo,
            "alt": row["alt"],
            "time": tiso,
            "hr": row["hr"],
        })

    return {"points": points, "placemarks": []}
