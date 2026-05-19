from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
WEATHER_REQUEST_TIMEOUT_SEC = 5
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
    hour_index = int(dt.astimezone(dt.tzinfo).hour)
    try:
        response = requests.get(
            OPEN_METEO_ARCHIVE_URL,
            params={
                "latitude": lat_val,
                "longitude": lon_val,
                "start_date": date_text,
                "end_date": date_text,
                "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m,weathercode",
                "timezone": "auto",
            },
            timeout=WEATHER_REQUEST_TIMEOUT_SEC,
        )
        response.raise_for_status()
        payload = response.json()
        hourly = payload.get("hourly") if isinstance(payload, dict) else {}
        if not isinstance(hourly, dict):
            return None

        times = hourly.get("time") or []
        temperatures = hourly.get("temperature_2m") or []
        humidities = hourly.get("relative_humidity_2m") or []
        wind_speeds = hourly.get("wind_speed_10m") or []
        weather_codes = hourly.get("weathercode") or []
        if not times:
            return None

        match_index = None
        for idx, time_str in enumerate(times):
            try:
                hourly_dt = datetime.fromisoformat(str(time_str))
            except ValueError:
                continue
            if hourly_dt.hour == hour_index:
                match_index = idx
                break
        if match_index is None:
            match_index = min(hour_index, len(times) - 1)

        code = weather_codes[match_index] if match_index < len(weather_codes) else None
        weather = {
            "temperature_c": temperatures[match_index] if match_index < len(temperatures) else None,
            "humidity": humidities[match_index] if match_index < len(humidities) else None,
            "wind_speed_kmh": wind_speeds[match_index] if match_index < len(wind_speeds) else None,
            "weather_code": code,
            "weather_label": WEATHER_CODE_LABELS.get(int(code)) if code is not None else "",
            "observed_hour": hour_index,
            "observed_date": date_text,
        }
        if not any(weather.get(key) is not None for key in ("temperature_c", "humidity", "wind_speed_kmh", "weather_code")):
            return None
        return weather
    except Exception:
        return None
