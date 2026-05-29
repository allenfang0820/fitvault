from __future__ import annotations

import math
from typing import Any

from garmin_fit_sdk import profile as garmin_fit_profile
from metrics_registry import METRICS_REGISTRY, SPORT_ALIASES, SPORT_DISPLAY_NAMES

SEMICIRCLE_SCALE = 180.0 / (1 << 31)
MAX_CURVE_POINTS = 200

try:
    _RAW_GARMIN_PRODUCT = garmin_fit_profile.Profile['types']['garmin_product']
except (KeyError, TypeError):
    _RAW_GARMIN_PRODUCT = {}
GARMIN_DEVICE_NAME_DICT: dict[int, str] = {int(k): str(v) for k, v in _RAW_GARMIN_PRODUCT.items()}

_DEVICE_DISPLAY_OVERLAY: dict[int, str] = {
    3910: "Fenix 7X (APAC)",
    4536: "Fenix 8",
    4759: "Instinct 3 Solar 50mm",
    4775: "Tactix 8 AMOLED",
}


class MetricsResolver:
    """Metrics Runtime v1.1 语义计算大脑 —— 四路严格解耦分发"""

    def resolve(self, raw: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
        session = self._first(raw.get("session_mesgs"))
        laps = raw.get("lap_mesgs") or []
        records = raw.get("record_mesgs") or []

        sm = self._build_storage_model(session, laps, raw, meta)
        vm = self._build_view_model(sm, session, meta)
        ap = self._build_analysis_pack(laps, records)
        ac = self._build_ai_context(sm, session, records)

        return {
            "storage_model": sm,
            "view_model": vm,
            "analysis_pack": ap,
            "ai_context": ac,
            "source": "resolver",
        }

    # ── storage_model ──────────────────────────────────────────

    def _build_storage_model(
        self, session: dict[str, Any], laps: list[dict[str, Any]],
        raw: dict[str, Any], meta: dict[str, Any],
    ) -> dict[str, Any]:
        sm_meta = METRICS_REGISTRY["session_meta"]
        sport_raw = self._extract(session, sm_meta["sport"]["source"]) or "Workout"
        sport_type = self._normalize_sport(sport_raw)

        sm: dict[str, Any] = {
            "title": SPORT_DISPLAY_NAMES.get(sport_type, sport_raw or "Workout"),
            "sport": sport_type,
            "device_name": self._resolve_device_name(raw, meta),
            "distance_m": int(self._num(self._extract(session, "total_distance"))),
            "distance_km": round(self._num(self._extract(session, "total_distance")) / 1000.0, 2),
            "duration_sec": int(self._num(self._extract(session, "total_timer_time"))),
            "moving_time_sec": int(self._num(self._extract(session, "total_moving_time"))),
            "avg_hr": int(self._num(self._extract(session, "avg_heart_rate"))),
            "max_hr": int(self._num(self._extract(session, "max_heart_rate"))),
            "calories": int(self._num(self._extract(session, "total_calories"))),
            "elevation_gain_m": int(self._num(self._extract(session, "total_ascent"))),
            "elevation_loss_m": int(self._num(self._extract(session, "total_descent"))),
            "max_altitude_m": int(self._num(self._extract(session, "max_altitude"))),
            "avg_power_w": int(self._num(self._extract(session, "avg_power"))),
            "normalized_power_w": int(self._num(self._extract(session, "normalized_power"))),
            "max_power_w": int(self._num(self._extract(session, "max_power"))),
            "training_load": int(self._num(self._extract(session, "training_load"))),
            "avg_speed_mps": round(self._num(self._extract(session, "avg_speed")), 2),
            "start_time": self._extract(session, sm_meta["start_time"]["source"]),
            "start_lat": self._semicircle_to_deg(
                self._extract(session, sm_meta["start_position_lat"]["source"])
            ),
            "start_lon": self._semicircle_to_deg(
                self._extract(session, sm_meta["start_position_long"]["source"])
            ),
            "sport_type": sport_type,
            "sub_sport_type": self._normalize_sport(
                self._extract(session, sm_meta["sub_sport"]["source"])
            ),
            "avg_pace_sec": 0,
            "avg_pace": 0,
            "date_label": "",
            "gain_m": int(self._num(self._extract(session, "total_ascent"))),
            "max_alt_m": int(self._num(self._extract(session, "max_altitude"))),
            "total_ascent": int(self._num(self._extract(session, "total_ascent"))),
        }

        raw_start = sm["start_time"]
        sm["date_label"] = self._fmt_date_label(raw_start)

        distance_m = sm["distance_m"]
        if distance_m <= 5000:
            sm["distance_display"] = f"{int(distance_m)}m"
        else:
            sm["distance_display"] = f"{round(distance_m / 1000.0, 2):.2f}km"

        sm["region"] = ""

        avg_speed = sm["avg_speed_mps"]
        sub_sport = sm["sub_sport_type"]
        dur_sec = sm["duration_sec"]

        if sub_sport == "lap_swimming":
            num_lengths = self._num(self._extract(session, "num_lengths"))
            pool_length = self._num(self._extract(session, "pool_length")) or 25.0
            swim_distance_m = num_lengths * pool_length if num_lengths > 0 else 0.0
            sec_per_100m = (dur_sec / swim_distance_m * 100.0) if swim_distance_m > 0 and dur_sec > 0 else 0.0
            sm["avg_pace_sec"] = round(sec_per_100m, 1)
        elif sub_sport == "open_water":
            enhanced_speed = self._num(self._extract(session, "enhanced_avg_speed"))
            sec_per_100m = (1000.0 / enhanced_speed / 10.0) if enhanced_speed and enhanced_speed > 0 else 0.0
            sm["avg_pace_sec"] = round(sec_per_100m, 1)
        else:
            sm["avg_pace_sec"] = round(1000.0 / avg_speed) if avg_speed > 0 else 0

        sm["avg_pace"] = sm["avg_pace_sec"]

        dist_km = sm["distance_km"]
        if sub_sport not in ("lap_swimming", "open_water"):
            sm["avg_pace"] = round(dur_sec / dist_km, 2) if dist_km > 0 and dur_sec > 0 else 0

        pace_unit = "/km"
        if sub_sport in ("lap_swimming", "open_water"):
            pace_unit = "/100m"
        sm["avg_pace_display"] = self._fmt_pace(sm["avg_pace_sec"], pace_unit)

        # SWOLF: 平均泳池效率指数
        # Tier 1 — session 层 avg_swolf 字符串键
        raw_swolf = self._extract(session, "avg_swolf")
        # Tier 2 — Garmin SDK 会将 avg_swolf 存储为 session 层数值键 80
        if raw_swolf is None:
            raw_swolf = session.get(80)
        if raw_swolf is not None and float(raw_swolf) > 0:
            sm["swolf"] = int(round(float(raw_swolf)))
        else:
            # Tier 3 — 从各趟 lap 逐趟计算 SWOLF 后取均值（天然排除休息时段）
            swolf_values = []
            for lap in laps:
                lap_len = self._num(lap.get("num_lengths"))
                lap_strokes = self._num(
                    lap.get("total_strokes") or lap.get("total_cycles")
                )
                lap_timer = self._num(lap.get("total_timer_time"))
                if lap_len > 0 and lap_strokes > 0:
                    # total_timer_time 单位兼容（秒或毫秒）
                    lap_dur = lap_timer / 1000.0 if lap_timer > 86400 else lap_timer
                    lap_swolf = int(round(lap_strokes / lap_len + lap_dur / lap_len))
                    swolf_values.append(lap_swolf)
            if swolf_values:
                sm["swolf"] = int(round(sum(swolf_values) / len(swolf_values)))
            else:
                # Tier 4 — session 层聚合兜底（含休息时段的失真值，仅作最后回退）
                num_lengths = self._num(self._extract(session, "num_lengths"))
                total_strokes = self._num(
                    self._extract(session, "total_strokes")
                    or self._extract(session, "total_cycles")
                )
                total_timer = self._num(self._extract(session, "total_timer_time"))
                dur_sec = total_timer / 1000.0 if total_timer > 86400 else total_timer
                if num_lengths > 0:
                    sm["swolf"] = int(round(total_strokes / num_lengths + dur_sec / num_lengths))
                else:
                    sm["swolf"] = 0

        sm["source"] = "resolver"
        return sm

    # ── view_model ─────────────────────────────────────────────

    def _build_view_model(
        self, sm: dict[str, Any], session: dict[str, Any], meta: dict[str, Any]
    ) -> dict[str, str]:
        device_name = (meta.get("device") or {}).get("name") or "Unknown"
        sport_display = SPORT_DISPLAY_NAMES.get(
            sm.get("sport_type") or "unknown", "Unknown"
        )
        return {
            "distance_display": sm.get("distance_display") or self._fmt_distance(sm.get("distance_km")),
            "duration_display": self._fmt_duration(sm.get("duration_sec")),
            "avg_pace_display": sm.get("avg_pace_display") or self._fmt_pace(sm.get("avg_pace")),
            "avg_hr_display": f"{sm.get('avg_hr') or '--'} bpm",
            "max_hr_display": f"{sm.get('max_hr') or '--'} bpm",
            "gain_display": self._fmt_elevation(sm.get("elevation_gain_m")),
            "max_alt_display": self._fmt_elevation(sm.get("max_altitude_m")),
            "calories_display": f"{sm.get('calories') or '--'} kcal",
            "sport_display": sport_display,
            "device": device_name,
            "title": sm.get("title", "Workout"),
        }

    # ── analysis_pack ─────────────────────────────────────────

    def _build_analysis_pack(
        self, laps: list[dict[str, Any]], records: list[dict[str, Any]]
    ) -> dict[str, Any]:
        pack: dict[str, Any] = {
            "source": "resolver",
            "laps": self._normalize_laps(laps),
            "hr_curve": [],
            "pace_curve": [],
            "altitude_curve": [],
            "speed_curve": [],
            "distance_curve": [],
            "lat_curve": [],
            "lon_curve": [],
        }
        if not records:
            return pack

        step = max(1, len(records) // MAX_CURVE_POINTS)
        sampled = records[::step] if step > 1 else records

        for rec in sampled:
            hr = self._num(self._record_value(rec, "heart_rate", "hr"))
            speed = self._num(self._record_value(rec, "speed"))
            alt = self._num(self._record_value(rec, "altitude", "alt"))
            dist = self._num(self._record_value(rec, "distance", "dist"))
            lat = self._num(self._record_value(rec, "lat", "position_lat"))
            lon = self._num(self._record_value(rec, "lon", "position_long"))

            pack["hr_curve"].append(hr if hr else None)
            pack["speed_curve"].append(round(speed, 2) if speed else None)
            pack["altitude_curve"].append(round(alt, 1) if alt else None)
            pack["distance_curve"].append(round(dist, 1) if dist else None)
            pack["lat_curve"].append(round(lat, 6) if lat else None)
            pack["lon_curve"].append(round(lon, 6) if lon else None)

            if speed and speed > 0.1:
                pace_min_per_km = 16.6667 / speed
                pack["pace_curve"].append(round(pace_min_per_km, 2))
            else:
                pack["pace_curve"].append(None)

        return pack

    # ── ai_context ─────────────────────────────────────────────

    def _build_ai_context(
        self, sm: dict[str, Any], session: dict[str, Any], records: list[dict[str, Any]]
    ) -> dict[str, Any]:
        structured = dict(sm)
        structured.pop("start_time", None)
        structured["avg_hr_bpm"] = structured.pop("avg_hr", None)
        structured["max_hr_bpm"] = structured.pop("max_hr", None)
        structured["avg_pace_sec_per_km"] = structured.pop("avg_pace", None)

        pace_values = []
        hr_values = []
        for rec in records:
            spd = self._num(self._record_value(rec, "speed"))
            hr = self._num(self._record_value(rec, "heart_rate", "hr"))
            if spd and spd > 0.1:
                pace_values.append(16.6667 / spd)
            if hr:
                hr_values.append(hr)

        pace_variance = round(float(self._stddev(pace_values)), 2) if len(pace_values) >= 2 else None
        structured["pace_variance"] = pace_variance

        semantic = {
            "cardio_load": self._classify_cardio_load(
                sm.get("avg_hr"), sm.get("max_hr")
            ),
            "pace_stability": self._classify_pace_stability(pace_values),
            "elevation_profile": self._classify_elevation(sm.get("elevation_gain_m"), sm.get("distance_km")),
        }

        return {
            "source": "resolver",
            "structured_metrics": structured,
            "semantic_signals": semantic,
        }

    # ── helpers ────────────────────────────────────────────────

    @staticmethod
    def _first(messages: Any) -> dict[str, Any]:
        if isinstance(messages, list) and messages:
            first = messages[0]
            return dict(first) if isinstance(first, dict) else {}
        return {}

    @staticmethod
    def _extract(session: dict[str, Any], key: str) -> Any:
        value = session.get(key)
        if isinstance(value, str):
            return value.replace("\x00", "").strip()
        return value

    @staticmethod
    def _num(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _record_value(record: Any, *keys: str) -> Any:
        if not isinstance(record, dict):
            return None
        raw = record.get("raw")
        geo = record.get("geo")
        sources = [record]
        if isinstance(raw, dict):
            sources.append(raw)
        if isinstance(geo, dict):
            sources.append(geo)
        for key in keys:
            for source in sources:
                value = source.get(key)
                if value is not None:
                    return value
        return None

    @staticmethod
    def _safe_int_none(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _semicircle_to_deg(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value) * SEMICIRCLE_SCALE
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_sport(value: Any) -> str:
        if value is None:
            return "unknown"
        token = str(value).strip().lower().replace("-", "_").replace(" ", "_")
        if any(m in token for m in (".fit", ".gpx", ".kml", "/", "\\")):
            return "unknown"
        return SPORT_ALIASES.get(token, token or "unknown")

    @staticmethod
    def _fmt_date_label(value: Any) -> str:
        if value is None:
            return ""
        from datetime import datetime, timedelta, timezone
        try:
            if isinstance(value, datetime):
                dt = value
            else:
                s = str(value).replace("\x00", "").strip()
                if s.endswith("Z"):
                    s = s[:-1] + "+00:00"
                dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            bj_tz = timezone(timedelta(hours=8))
            dt_local = dt.astimezone(bj_tz)
            return dt_local.strftime("%Y-%m-%d")
        except (ValueError, TypeError, OverflowError):
            return ""

    @staticmethod
    def _fmt_distance(km: Any) -> str:
        try:
            d = float(km)
        except (TypeError, ValueError):
            return "-- km"
        if d >= 1.0:
            return f"{d:.2f} km"
        return f"{int(d * 1000)} m"

    @staticmethod
    def _fmt_duration(sec: Any) -> str:
        try:
            s = int(float(sec))
        except (TypeError, ValueError):
            return "--:--"
        h, m = divmod(s, 3600)
        m, s = divmod(m, 60)
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    @staticmethod
    def _fmt_pace(pace_sec: Any, unit: str = "/km") -> str:
        try:
            p = float(pace_sec)
        except (TypeError, ValueError):
            return f"-- {unit}"
        if p <= 0:
            return f"-- {unit}"
        minutes = int(p // 60)
        seconds = int(round(p % 60))
        return f"{minutes}'{seconds:02d}''{unit}"

    @staticmethod
    def _fmt_elevation(m: Any) -> str:
        try:
            v = float(m)
        except (TypeError, ValueError):
            return "-- m"
        return f"{int(v)} m"

    @staticmethod
    def _fmt_device_display_name(product_code: str) -> str:
        """snake_case 产品代号 → 人类可读产品名称"""
        display = str(product_code or "").strip()
        if not display or display.lower() in ("unknown", "unknown_device", "none"):
            return "Unknown Device"
        parts = display.split("_")
        title_parts = []
        for p in parts:
            p_upper = p.upper()
            if p in ("apac", "twn", "jpn", "chn", "kor", "sea"):
                title_parts.append(f"({p_upper})")
            else:
                title_parts.append(p[0].upper() + p[1:] if p else p)
        return " ".join(title_parts)

    @staticmethod
    def _resolve_device_name(raw: dict[str, Any], meta: dict[str, Any]) -> str:
        """从 raw['file_id_mesgs'] 提取 product_id，通过 SDK profile 翻译为产品型号"""
        fid = raw.get("file_id_mesgs")
        file_id = fid[0] if isinstance(fid, list) and fid else {}

        garmin_product = file_id.get("garmin_product") if isinstance(file_id, dict) else None
        product = file_id.get("product") if isinstance(file_id, dict) else None

        if garmin_product:
            product_code = str(garmin_product).strip()
        elif product is not None:
            pid_int = int(float(product)) if product else 0
            display = _DEVICE_DISPLAY_OVERLAY.get(pid_int)
            if display:
                product_code = display
            else:
                product_code = GARMIN_DEVICE_NAME_DICT.get(pid_int, f"Garmin Product {pid_int}")
        else:
            product_code = (meta.get("device") or {}).get("name") or ""

        if not product_code or str(product_code).isdigit():
            return "Unknown Device"

        return MetricsResolver._fmt_device_display_name(product_code)

    @staticmethod
    def _classify_cardio_load(avg_hr: Any, max_hr: Any) -> str:
        if avg_hr is None or max_hr is None:
            return "unknown"
        try:
            ratio = float(avg_hr) / float(max_hr)
        except (TypeError, ValueError, ZeroDivisionError):
            return "unknown"
        if ratio < 0.55:
            return "very_low"
        if ratio < 0.70:
            return "low"
        if ratio < 0.80:
            return "moderate"
        if ratio < 0.90:
            return "high"
        return "extreme"

    @staticmethod
    def _classify_pace_stability(pace_values: list[float]) -> str:
        if len(pace_values) < 2:
            return "unknown"
        stddev = MetricsResolver._stddev(pace_values)
        avg = sum(pace_values) / len(pace_values)
        cv = (stddev / avg * 100) if avg > 0 else 0
        if cv < 3:
            return "stable"
        if cv < 8:
            return "moderate"
        return "variable"

    @staticmethod
    def _classify_elevation(gain_m: Any, distance_km: Any) -> str:
        try:
            g = float(gain_m or 0)
        except (TypeError, ValueError):
            g = 0.0
        try:
            d = float(distance_km or 0)
        except (TypeError, ValueError):
            d = 0.0
        if d == 0:
            return "unknown"
        ratio = g / d
        if ratio < 10:
            return "flat"
        if ratio < 30:
            return "rolling_hills"
        return "mountainous"

    @staticmethod
    def _stddev(values: list[float]) -> float:
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
        return math.sqrt(variance)

    # ── lap normalization ─────────────────────────────────────

    @staticmethod
    def _normalize_laps(laps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for i, lap in enumerate(laps):
            if not isinstance(lap, dict):
                continue
            dist = MetricsResolver._num(lap.get("total_distance"))
            elapsed = MetricsResolver._num(lap.get("total_timer_time"))
            avg_hr = MetricsResolver._num(lap.get("avg_heart_rate"))
            avg_power = MetricsResolver._num(lap.get("avg_power"))
            avg_cadence = MetricsResolver._num(lap.get("avg_cadence"))
            if dist == 0 and elapsed == 0:
                continue
            result.append({
                "lap_index": lap.get("lap_index", i),
                "distance_m": dist,
                "elapsed_sec": elapsed,
                "avg_hr": avg_hr if avg_hr else None,
                "avg_power": avg_power if avg_power else None,
                "avg_cadence": avg_cadence if avg_cadence else None,
            })
        return result
