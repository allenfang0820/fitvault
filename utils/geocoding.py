"""
地理编码模块 — 根据 GPS 坐标获取城市/区域名

数据流: activities 待补全地区 → Nominatim API → activities.region_display

契约: FIELD_CONTRACT §2.1 "FIT 为唯一事实源"
"""
from __future__ import annotations

import time
import logging
import urllib.request
import urllib.parse
import json
import random
from typing import Any

logger = logging.getLogger(__name__)

NOMINATIM_USER_AGENT = "FitVault/1.0 (sports-tracker)"
NOMINATIM_BASE_URL = "https://nominatim.openstreetmap.org/reverse"
NOMINATIM_RATE_LIMIT_MIN_SEC = 1.5
NOMINATIM_RATE_LIMIT_MAX_SEC = 5.0

_last_request_time: float = 0.0


def _rate_limited_request(url: str) -> dict[str, Any] | None:
    """遵守 Nominatim 频率限制的 HTTP GET（带随机抖动）"""
    global _last_request_time
    now = time.time()
    elapsed = now - _last_request_time
    jitter = random.uniform(NOMINATIM_RATE_LIMIT_MIN_SEC, NOMINATIM_RATE_LIMIT_MAX_SEC)
    required = max(0, jitter - elapsed)
    if required > 0:
        time.sleep(required)
    req = urllib.request.Request(url, headers={"User-Agent": NOMINATIM_USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            _last_request_time = time.time()
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.warning("Nominatim request failed: %s", e)
        return None


def _request_geo(lat: float, lon: float, zoom: int) -> dict[str, Any] | None:
    params = {
        "format": "json",
        "lat": str(lat),
        "lon": str(lon),
        "zoom": zoom,
        "addressdetails": 1,
        "accept-language": "zh",
    }
    url = f"{NOMINATIM_BASE_URL}?{urllib.parse.urlencode(params)}"
    data = _rate_limited_request(url)
    if not data or "address" not in data:
        return None
    addr = data["address"]
    return {
        "city": addr.get("city") or "",
        "town": addr.get("town") or "",
        "village": addr.get("village") or "",
        "hamlet": addr.get("hamlet") or "",
        "municipality": addr.get("municipality") or "",
        "county": addr.get("county") or "",
        "district": addr.get("district") or "",
        "state": addr.get("state") or "",
        "province": addr.get("province") or "",
        "region": addr.get("region") or "",
        "suburb": addr.get("suburb") or "",
        "neighbourhood": addr.get("neighbourhood") or "",
        "locality": addr.get("locality") or "",
        "protected_area": addr.get("protected_area") or "",
        "nature_reserve": addr.get("nature_reserve") or "",
        "park": addr.get("park") or "",
        "mountain": addr.get("mountain") or "",
        "peak": addr.get("peak") or "",
        "tourism": addr.get("tourism") or "",
        "name": data.get("name") or "",
        "display_name": data.get("display_name") or "",
        "country": addr.get("country") or "",
    }


def _is_administrative_district(name: str) -> bool:
    return bool(name and (name.endswith("区") and len(name) > 2))


def _is_province_level(name: str) -> bool:
    return bool(name and (name.endswith("省") or name.endswith("自治区") or name.endswith("特别行政区")))


def reverse_geocode(lat: float, lon: float, zoom: int = 10) -> dict[str, Any] | None:
    """
    逆地理编码：坐标 → 地址信息。
    当 zoom=10 返回的是行政区（区）或省份名时，自动降 zoom=6 获取城市级名称。
    若 zoom=6 也无法提供城市名，但 zoom=10 有有效 county（如"小金县"），
    则回退到 zoom=10 的 county，作为最接近城市级的名称。
    返回 {"city": "成都", "town": "", "county": "", "state": "四川省", "country": "中国"}
    """
    result = _request_geo(lat, lon, zoom)
    if not result:
        return None
    raw_city = (result.get("city") or result.get("town") or result.get("municipality") or "").strip()
    raw_state = (result.get("state") or "").strip()
    fallback_county = (result.get("county") or "").strip()
    if not raw_city or _is_administrative_district(raw_city) or _is_province_level(raw_city) or _is_province_level(raw_state):
        city_result = _request_geo(lat, lon, 6)
        if city_result:
            city_name = (city_result.get("city") or city_result.get("county") or "").strip()
            if city_name and not _is_province_level(city_name):
                result["city"] = city_name
            elif fallback_county:
                result["city"] = fallback_county
            elif not result.get("city"):
                result["city"] = (city_result.get("state") or result.get("state") or "").strip()
        elif fallback_county:
            result["city"] = fallback_county
    return result


def format_region(geo: dict[str, Any] | None) -> str:
    if not geo:
        return ""
    return (
        geo.get("city")
        or geo.get("county")
        or geo.get("town")
        or geo.get("municipality")
        or geo.get("state")
        or ""
    ).strip()
