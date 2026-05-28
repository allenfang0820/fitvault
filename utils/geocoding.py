"""
地理编码模块 — 根据 GPS 坐标获取城市/区域名

数据流: FIT GPS → resolve_activity_region → Nominatim API → activities.region

契约: FIELD_CONTRACT §2.1 "FIT 为唯一事实源"
"""
from __future__ import annotations

import time
import logging
import urllib.request
import urllib.parse
import json
from typing import Any

logger = logging.getLogger(__name__)

NOMINATIM_USER_AGENT = "MaiTuSports/1.0 (sports-tracker)"
NOMINATIM_BASE_URL = "https://nominatim.openstreetmap.org/reverse"
NOMINATIM_RATE_LIMIT_SEC = 1.0

_last_request_time: float = 0.0


def _rate_limited_request(url: str) -> dict[str, Any] | None:
    """遵守 Nominatim 频率限制的 HTTP GET"""
    global _last_request_time
    now = time.time()
    elapsed = now - _last_request_time
    if elapsed < NOMINATIM_RATE_LIMIT_SEC:
        time.sleep(NOMINATIM_RATE_LIMIT_SEC - elapsed)
    req = urllib.request.Request(url, headers={"User-Agent": NOMINATIM_USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            _last_request_time = time.time()
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.warning("Nominatim request failed: %s", e)
        return None


def reverse_geocode(lat: float, lon: float) -> dict[str, Any] | None:
    """
    逆地理编码：坐标 → 地址信息
    返回 {"city": "成都", "town": "高新区", "state": "四川省", "country": "中国"}
    """
    params = {
        "format": "json",
        "lat": str(lat),
        "lon": str(lon),
        "zoom": 10,
        "addressdetails": 1,
        "accept-language": "zh",
    }
    url = f"{NOMINATIM_BASE_URL}?{urllib.parse.urlencode(params)}"
    data = _rate_limited_request(url)
    if not data or "address" not in data:
        return None
    addr = data["address"]
    return {
        "city": addr.get("city") or addr.get("town") or addr.get("county") or "",
        "town": addr.get("town") or "",
        "state": addr.get("state") or "",
        "country": addr.get("country") or "",
    }


def format_region(geo: dict[str, Any] | None) -> str:
    """
    将逆地理编码结果格式化为 region 字符串
    优先级: city → town → county → state → province → ""
    """
    if not geo:
        return ""
    return (
        geo.get("city")
        or geo.get("town")
        or geo.get("county")
        or geo.get("state")
        or geo.get("province")
        or ""
    ).strip()
