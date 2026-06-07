from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fitparse import FitFile, FitParseError

FIT_PARSE_LOG_PATH = Path(__file__).resolve().with_name("fit_parse.log")
SEMICIRCLE_SCALE = 180.0 / (1 << 31)

SPORT_TYPE_ALIASES = {
    "run": "running",
    "running": "running",
    "trail_running": "trail_running",
    "trail": "trail_running",
    "cycling": "cycling",
    "bike": "cycling",
    "road_cycling": "road_cycling",
    "mountain_biking": "mountain_biking",
    "hiking": "hiking",
    "hike": "hiking",
    "walking": "walking",
    "walk": "walking",
    "swimming": "swimming",
    "lap_swimming": "swimming",
    "open_water": "swimming",
    "treadmill_running": "treadmill_running",
    "cardio": "cardio",
    "cardio_training": "cardio",
    "strength_training": "strength_training",
    "yoga": "yoga",
    "pilates": "pilates",
    "hiit": "hiit",
    "breathing": "breathing",
    "flexibility_training": "flexibility_training",
    "training": "training",
}


def _assert_valid_fit_file(path: Path) -> None:
    """FIT 文件前置校验:拦截系统影子文件 + magic 验证。

    供 parse_fit_file / parse_fit_file_raw 两条入口共用,作为契约兜底。
    任一入口绕过都会污染下游(garmin_fit_sdk Decoder、fitparse 等),
    必须在这里统一拦截。

    Raises:
        ValueError: 文件名是系统影子文件 / 文件头 magic 不匹配
    """
    # 1) macOS AppleDouble 影子文件 (._xxx.fit) + Windows 临时文件 (~$xxx.fit)
    if path.name.startswith("._") or path.name.startswith("~$"):
        raise ValueError(f"系统影子文件,跳过: {path.name}")

    # 2) FIT 文件头 magic 验证。
    # 偏移 0: header_size (12 或 14)
    # 偏移 8-12: ".FIT" 4 字节 magic
    try:
        with open(path, "rb") as _f:
            _header = _f.read(14)
    except OSError as exc:
        raise ValueError(f"无法读取 FIT 文件: {exc}") from exc
    if len(_header) < 12 or _header[8:12] != b".FIT" or _header[0] not in (12, 14):
        raise ValueError(
            f"不是有效 FIT 文件(magic 不匹配,可能为压缩包/系统文件/损坏): {path.name}"
        )


class FITCoreEngine:
    @staticmethod
    def parse_fit_file_raw(file_path: str | Path) -> dict[str, Any]:
        from garmin_fit_sdk import Decoder, Stream

        path = Path(file_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")
        if not path.is_file():
            raise ValueError(f"路径不是文件: {path}")
        _assert_valid_fit_file(path)  # 契约兜底:与 parse_fit_file 共用

        path = str(path)
        stream = Stream.from_file(path)
        messages, meta = Decoder(stream).read()
        if "record_mesgs" in messages:
            messages["record_mesgs"] = FITCoreEngine._transform_record_format(messages["record_mesgs"])
        return {"raw": messages, "meta": meta, "source": "canonical"}

    @staticmethod
    def _transform_record_format(records: list) -> list:
        transformed = []
        for rec in records:
            if not isinstance(rec, dict):
                transformed.append(rec)
                continue
            geo = {}
            if "position_lat" in rec:
                geo["lat"] = rec["position_lat"]
            if "position_long" in rec:
                geo["lon"] = rec["position_long"]
            transformed.append({"raw": rec, "geo": geo})
        return transformed

    @staticmethod
    def parse_fit_file(file_path: str | Path) -> dict[str, Any]:
        path = Path(file_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")
        if not path.is_file():
            raise ValueError(f"路径不是文件: {path}")
        _assert_valid_fit_file(path)  # 契约兜底:与 parse_fit_file_raw 共用

        logger = FITCoreEngine._logger()
        try:
            fit = FitFile(str(path), check_crc=True)
        except FitParseError as exc:
            logger.exception("FIT 文件初始化失败: %s", path)
            err_str = str(exc).lower()
            if "header" in err_str or "signature" in err_str or "corrupt" in err_str:
                raise ValueError("FIT 文件损坏或已截断，无法解析。可能原因：文件传输不完整。") from exc
            if "version" in err_str or "protocol" in err_str:
                raise ValueError(f"FIT 文件版本不受支持: {exc}") from exc
            raise ValueError(f"FIT 文件解析失败: {exc}") from exc
        except OSError as exc:
            logger.exception("FIT 文件读取失败: %s", path)
            raise ValueError(f"无法读取 FIT 文件（权限或路径问题）: {exc}") from exc

        try:
            session_info = FITCoreEngine._read_session_info(fit)
            sport_info = FITCoreEngine._read_sport_info(fit)
            activity_info = FITCoreEngine._read_activity_info(fit)
            lap_data = FITCoreEngine._read_lap_data(fit)
            track_data = FITCoreEngine._read_track_data(fit)
            has_gps = bool(track_data)
            if not has_gps:
                logger.info("FIT 文件未包含 GPS 轨迹，跳过轨迹解析，保留室内运动基础字段: %s", path)

            avg_hr, max_hr = FITCoreEngine._heart_rate_stats(
                session_info.get("avg_heart_rate"),
                session_info.get("max_heart_rate"),
                track_data,
            )
            start_time, start_time_utc = FITCoreEngine._resolve_start_times(
                session_info.get("start_time"),
                activity_info.get("local_timestamp"),
                track_data,
            )
            title, title_source = FITCoreEngine._derive_title(
                path,
                sport_info.get("name"),
                session_info.get("session_label"),
            )

            sport_raw = session_info.get("sport") or sport_info.get("sport")
            sub_sport_raw = session_info.get("sub_sport") or sport_info.get("sub_sport")
            activity_type = FITCoreEngine._resolve_activity_type(sport_raw, sub_sport_raw)

            basic_info = {
                "file_name": path.name,
                "file_path": str(path),
                "title": title,
                "title_source": title_source,
                "sport": FITCoreEngine._token(sport_raw, "unknown"),
                "sub_sport": FITCoreEngine._token(sub_sport_raw, "unknown"),
                "activity_type": activity_type,
                "start_time": start_time,
                "start_time_utc": start_time_utc,
                "total_distance_m": FITCoreEngine._float_or_none(session_info.get("total_distance")),
                "total_distance_km": (FITCoreEngine._float_or_none(session_info.get("total_distance")) or 0.0) / 1000.0,
                "total_timer_time": FITCoreEngine._int_or_none(session_info.get("total_timer_time")),
                "total_calories": FITCoreEngine._int_or_none(session_info.get("total_calories")),
                "total_ascent": FITCoreEngine._float_or_none(session_info.get("total_ascent")),
                "total_descent": FITCoreEngine._float_or_none(session_info.get("total_descent")),
                "max_altitude": FITCoreEngine._float_or_none(session_info.get("max_altitude")),
                "avg_stroke_distance": FITCoreEngine._float_or_none(session_info.get("avg_stroke_distance")),
                "avg_hr": avg_hr,
                "max_hr": max_hr,
            }
            return {
                "basic_info": basic_info,
                "track_data": track_data,
                "lap_data": lap_data,
                "source": "canonical",
            }
        except ValueError:
            logger.exception("FIT 文件解析失败: %s", path)
            raise
        except Exception as exc:
            logger.exception("FIT 文件解析出现未预期异常: %s", path)
            raise ValueError(f"FIT 文件解析失败: {exc}") from exc

    @staticmethod
    def _logger() -> logging.Logger:
        logger = logging.getLogger("fit_engine.core")
        if logger.handlers:
            return logger
        handler = logging.FileHandler(FIT_PARSE_LOG_PATH, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        return logger

    @staticmethod
    def _message_fields_dict(msg: Any) -> dict[str, Any]:
        return {field.name: field.value for field in getattr(msg, "fields", [])}

    @staticmethod
    def _token(value: Any, fallback: str = "") -> str:
        token = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
        return token or fallback

    @staticmethod
    def _clean_text(value: Any) -> str:
        text = str(value or "").replace("\x00", "").strip()
        return re.sub(r"\s+", " ", text)

    @staticmethod
    def _clean_filename_title(path: Path) -> str:
        stem = re.sub(r"(?i)_activity(?:_\d+)?$", "", path.stem).strip("_- ")
        stem = re.sub(r"[_\s]+", " ", stem).strip()
        if not stem:
            return ""
        if re.fullmatch(r"[0-9a-fA-F]{8,}", stem):
            return ""
        if re.fullmatch(r"\d+", stem):
            return ""
        return stem

    @staticmethod
    def _fit_latlon_to_deg(lat: float, lon: float) -> tuple[float, float]:
        if abs(lat) <= 90 and abs(lon) <= 180:
            return lat, lon
        return lat * SEMICIRCLE_SCALE, lon * SEMICIRCLE_SCALE

    @staticmethod
    def _iso_utc(dt: Any) -> str | None:
        if dt is None:
            return None
        if isinstance(dt, datetime):
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        return str(dt)

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _int_or_none(value: Any) -> int | None:
        try:
            if value is None:
                return None
            return int(round(float(value)))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _resolve_activity_type(sport_raw: Any, sub_sport_raw: Any) -> str:
        sport = FITCoreEngine._token(sport_raw, "unknown")
        sub_sport = FITCoreEngine._token(sub_sport_raw, "unknown")
        if sub_sport in {"trail_running", "road_cycling", "mountain_biking"}:
            return sub_sport
        if sport in {"trail_running", "road_cycling", "mountain_biking"}:
            return sport
        if sub_sport in SPORT_TYPE_ALIASES:
            return SPORT_TYPE_ALIASES[sub_sport]
        if sport in SPORT_TYPE_ALIASES:
            return SPORT_TYPE_ALIASES[sport]
        return sport or "unknown"

    @staticmethod
    def _read_session_info(fit: FitFile) -> dict[str, Any]:
        info: dict[str, Any] = {}
        for msg in fit.get_messages("session"):
            fields = FITCoreEngine._message_fields_dict(msg)
            info = {
                "sport": msg.get_value("sport"),
                "sub_sport": msg.get_value("sub_sport"),
                "start_time": msg.get_value("start_time") or msg.get_value("timestamp"),
                "avg_heart_rate": msg.get_value("avg_heart_rate"),
                "max_heart_rate": msg.get_value("max_heart_rate"),
                "total_distance": msg.get_value("total_distance"),
                "total_timer_time": msg.get_value("total_timer_time") or msg.get_value("total_elapsed_time"),
                "total_calories": msg.get_value("total_calories"),
                "total_ascent": msg.get_value("total_ascent"),
                "total_descent": msg.get_value("total_descent"),
                "max_altitude": msg.get_value("max_altitude") or fields.get("enhanced_max_altitude"),
                "avg_stroke_distance": msg.get_value("avg_stroke_distance"),
                "session_label": fields.get("unknown_110"),
            }
            break
        return info

    @staticmethod
    def _read_sport_info(fit: FitFile) -> dict[str, Any]:
        info: dict[str, Any] = {}
        for msg in fit.get_messages("sport"):
            info = {
                "sport": msg.get_value("sport"),
                "sub_sport": msg.get_value("sub_sport"),
                "name": FITCoreEngine._clean_text(msg.get_value("name")),
            }
            break
        return info

    @staticmethod
    def _read_activity_info(fit: FitFile) -> dict[str, Any]:
        info: dict[str, Any] = {}
        for msg in fit.get_messages("activity"):
            info = {
                "local_timestamp": msg.get_value("local_timestamp"),
            }
            break
        return info

    @staticmethod
    def _read_lap_data(fit: FitFile) -> list[dict[str, Any]]:
        """提取 FIT lap_mesgs,字段命名与 MetricsResolver._normalize_laps 入参保持一致。

        返回结构:list[{total_distance, total_timer_time, avg_heart_rate,
                        max_heart_rate, avg_cadence, avg_power, total_calories,
                        lap_start_time, lap_index}]
        """
        laps: list[dict[str, Any]] = []
        for idx, msg in enumerate(fit.get_messages("lap")):
            values = FITCoreEngine._message_fields_dict(msg)
            lap_start = values.get("start_time") or values.get("timestamp")
            if isinstance(lap_start, datetime) and lap_start.tzinfo is None:
                lap_start = lap_start.replace(tzinfo=timezone.utc)
            laps.append({
                "lap_index": values.get("index") or values.get("lap_index") or idx,
                "total_distance": FITCoreEngine._float_or_none(values.get("total_distance")),
                "total_timer_time": FITCoreEngine._float_or_none(values.get("total_timer_time")),
                "avg_heart_rate": FITCoreEngine._int_or_none(values.get("avg_heart_rate")),
                "max_heart_rate": FITCoreEngine._int_or_none(values.get("max_heart_rate")),
                "avg_cadence": FITCoreEngine._int_or_none(values.get("avg_cadence")),
                "avg_power": FITCoreEngine._int_or_none(values.get("avg_power")),
                "total_calories": FITCoreEngine._int_or_none(values.get("total_calories")),
                "lap_start_time": FITCoreEngine._iso_utc(lap_start),
            })
        return laps

    @staticmethod
    def _read_track_data(fit: FitFile) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for msg in fit.get_messages("record"):
            values = FITCoreEngine._message_fields_dict(msg)
            lat = values.get("position_lat")
            lon = values.get("position_long")
            if lat is None or lon is None:
                continue
            try:
                latf, lonf = FITCoreEngine._fit_latlon_to_deg(float(lat), float(lon))
            except (TypeError, ValueError):
                continue
            ts = values.get("timestamp")
            if isinstance(ts, datetime) and ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            alt = values.get("enhanced_altitude")
            if alt is None:
                alt = values.get("altitude")
            hr = FITCoreEngine._int_or_none(values.get("heart_rate"))
            speed = FITCoreEngine._float_or_none(values.get("enhanced_speed"))
            if speed is None:
                speed = FITCoreEngine._float_or_none(values.get("speed"))
            pace = None
            if speed and speed > 0:
                pace = round(1000.0 / speed, 2)
            rows.append(
                {
                    "_ts": ts,
                    "lat": latf,
                    "lon": lonf,
                    "alt": FITCoreEngine._float_or_none(alt) or 0.0,
                    "time": FITCoreEngine._iso_utc(ts) if isinstance(ts, datetime) else None,
                    "hr": hr,
                    "pace": pace,
                }
            )
        rows.sort(key=lambda row: row["_ts"] or datetime.min.replace(tzinfo=timezone.utc))
        track_data: list[dict[str, Any]] = []
        for row in rows:
            if track_data:
                prev = track_data[-1]
                if abs(prev["lat"] - row["lat"]) < 1e-7 and abs(prev["lon"] - row["lon"]) < 1e-7 and prev.get("time") == row.get("time"):
                    continue
            track_data.append(
                {
                    "lat": row["lat"],
                    "lon": row["lon"],
                    "alt": row["alt"],
                    "time": row["time"],
                    "hr": row["hr"],
                    "pace": row["pace"],
                }
            )
        return track_data

    @staticmethod
    def _heart_rate_stats(session_avg_hr: Any, session_max_hr: Any, track_data: list[dict[str, Any]]) -> tuple[int | None, int | None]:
        hr_values = [int(point["hr"]) for point in track_data if point.get("hr") is not None]
        avg_hr = FITCoreEngine._int_or_none(session_avg_hr)
        max_hr = FITCoreEngine._int_or_none(session_max_hr)
        if avg_hr is None and hr_values:
            avg_hr = int(round(sum(hr_values) / len(hr_values)))
        if max_hr is None and hr_values:
            max_hr = max(hr_values)
        return avg_hr, max_hr

    @staticmethod
    def _resolve_start_times(start_time: datetime | None, local_timestamp: datetime | None, track_data: list[dict[str, Any]]) -> tuple[str | None, str | None]:
        start_time_utc = FITCoreEngine._iso_utc(start_time)
        if start_time is None and track_data:
            return track_data[0].get("time"), track_data[0].get("time")
        if start_time is None:
            if local_timestamp is None:
                return None, None
            if local_timestamp.tzinfo is None:
                local_timestamp = local_timestamp.replace(tzinfo=datetime.now().astimezone().tzinfo)
            return local_timestamp.isoformat(), None

        start_utc = start_time
        if start_utc.tzinfo is None:
            start_utc = start_utc.replace(tzinfo=timezone.utc)
        else:
            start_utc = start_utc.astimezone(timezone.utc)

        if local_timestamp is None:
            return start_utc.isoformat().replace("+00:00", "Z"), start_time_utc
        if local_timestamp.tzinfo is not None:
            return local_timestamp.isoformat(), start_time_utc

        delta = local_timestamp - start_utc.replace(tzinfo=None)
        if abs(delta) <= timedelta(hours=14) and (delta.total_seconds() % 60 == 0):
            local_tz = timezone(delta)
            return local_timestamp.replace(tzinfo=local_tz).isoformat(), start_time_utc
        return local_timestamp.isoformat(), start_time_utc

    @staticmethod
    def _derive_title(path: Path, sport_name: Any, session_label: Any) -> tuple[str, str]:
        file_title = FITCoreEngine._clean_filename_title(path)
        sport_title = FITCoreEngine._clean_text(sport_name)
        session_title = FITCoreEngine._clean_text(session_label)
        if sport_title:
            if file_title and sport_title in file_title and len(file_title) > len(sport_title):
                return file_title, "filename"
            return sport_title, "sport_name"
        if file_title:
            return file_title, "filename"
        if session_title:
            return session_title, "session_label"
        return path.name, "file_name"
