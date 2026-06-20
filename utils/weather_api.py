from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import requests

OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
WEATHER_REQUEST_TIMEOUT_SEC = 5
RECENT_WEATHER_PAST_DAYS = 3
WEATHER_CODE_LABELS = {
    0: "晴",
    1: "少云",
    2: "多云",
    3: "阴",
    45: "雾",
    48: "冻雾",
    51: "毛毛雨",
    53: "小雨",
    55: "中雨",
    56: "冻雨",
    57: "强冻雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "冻雨",
    67: "强冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "雪粒",
    80: "阵雨",
    81: "强阵雨",
    82: "暴雨",
    85: "阵雪",
    86: "暴雪",
    95: "雷暴",
    96: "雷暴夹小冰雹",
    99: "强雷暴夹冰雹",
}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_activity_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _weather_code_values(hourly: dict[str, Any]) -> list[Any]:
    return hourly.get("weather_code") or hourly.get("weathercode") or []


def _activity_local_datetime(dt: datetime, payload: dict[str, Any]) -> datetime:
    offset = payload.get("utc_offset_seconds") if isinstance(payload, dict) else None
    try:
        offset_seconds = int(offset)
    except (TypeError, ValueError):
        offset_seconds = None
    if offset_seconds is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None) + timedelta(seconds=offset_seconds)
    return dt.astimezone(dt.tzinfo).replace(tzinfo=None)


def _select_hourly_weather(
    payload: dict[str, Any],
    activity_dt: datetime,
    source: str,
) -> dict[str, Any] | None:
    hourly = payload.get("hourly") if isinstance(payload, dict) else {}
    if not isinstance(hourly, dict):
        return None

    times = hourly.get("time") or []
    temperatures = hourly.get("temperature_2m") or []
    humidities = hourly.get("relative_humidity_2m") or []
    wind_speeds = hourly.get("wind_speed_10m") or []
    weather_codes = _weather_code_values(hourly)
    if not times:
        return None

    target_dt = _activity_local_datetime(activity_dt, payload)
    match_index = None
    match_delta = None
    for idx, time_str in enumerate(times):
        try:
            hourly_dt = datetime.fromisoformat(str(time_str))
        except ValueError:
            continue
        if hourly_dt.tzinfo is not None:
            hourly_dt = hourly_dt.replace(tzinfo=None)
        delta = abs((hourly_dt - target_dt).total_seconds())
        if match_index is None or match_delta is None or delta < match_delta:
            match_index = idx
            match_delta = delta
    if match_index is None:
        return None

    code = weather_codes[match_index] if match_index < len(weather_codes) else None
    matched_dt = datetime.fromisoformat(str(times[match_index]))
    weather = {
        "temperature_c": temperatures[match_index] if match_index < len(temperatures) else None,
        "humidity": humidities[match_index] if match_index < len(humidities) else None,
        "wind_speed_kmh": wind_speeds[match_index] if match_index < len(wind_speeds) else None,
        "weather_code": code,
        "weather_label": WEATHER_CODE_LABELS.get(int(code)) if code is not None else "",
        "observed_hour": matched_dt.hour,
        "observed_date": matched_dt.date().isoformat(),
        "source": source,
    }
    if not any(weather.get(key) is not None for key in ("temperature_c", "humidity", "wind_speed_kmh", "weather_code")):
        return None
    return weather


def _is_recent_weather_datetime(dt: datetime) -> bool:
    now = _now_utc()
    dt_utc = dt.astimezone(timezone.utc)
    age_days = (now.date() - dt_utc.date()).days
    return 0 <= age_days <= RECENT_WEATHER_PAST_DAYS


def fetch_historical_weather(lat: Any, lon: Any, start_time: Any) -> dict[str, Any] | None:
    dt = _parse_activity_datetime(start_time)
    try:
        lat_val = float(lat)
        lon_val = float(lon)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None

    date_text = dt.date().isoformat()
    end_date_text = (dt.date() + timedelta(days=1)).isoformat()
    try:
        if _is_recent_weather_datetime(dt):
            response = requests.get(
                OPEN_METEO_FORECAST_URL,
                params={
                    "latitude": lat_val,
                    "longitude": lon_val,
                    "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
                    "past_days": RECENT_WEATHER_PAST_DAYS,
                    "forecast_days": 1,
                    "timezone": "auto",
                },
                timeout=WEATHER_REQUEST_TIMEOUT_SEC,
            )
            response.raise_for_status()
            weather = _select_hourly_weather(response.json(), dt, "forecast")
            if weather:
                return weather

        response = requests.get(
            OPEN_METEO_ARCHIVE_URL,
            params={
                "latitude": lat_val,
                "longitude": lon_val,
                "start_date": date_text,
                "end_date": end_date_text,
                "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m,weathercode",
                "timezone": "auto",
            },
            timeout=WEATHER_REQUEST_TIMEOUT_SEC,
        )
        response.raise_for_status()
        return _select_hourly_weather(response.json(), dt, "archive")
    except Exception:
        return None
