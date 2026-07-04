#!/usr/bin/env python3
"""获取佳明用户画像 JSON 数组。

策略：
- 每次运行实时获取日更字段：睡眠、HRV、静息心率、体重、VO2max、阈值等。
- 活动历史字段从缓存读取：累计里程、最长距离等。
- 缓存不存在或超过 7 天时自动生成；显式 --refresh 时强制刷新活动缓存。
"""
import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

hermes_libs = os.path.expanduser("~/Library/Application Support/QClaw/hermes/libs")
if hermes_libs in sys.path:
    sys.path.remove(hermes_libs)

WORKSPACE_DIR = Path(
    os.environ.get("QCLAW_WORKSPACE_DIR", str(Path.home() / ".qclaw" / "workspace"))
).expanduser()
CACHE_DIR = Path(
    os.environ.get("GARMIN_STATS_CACHE_DIR", str(WORKSPACE_DIR / "garmin_data"))
).expanduser()
CACHE_FILE = CACHE_DIR / "all_activities.json"
CACHE_META_FILE = CACHE_DIR / "all_activities.meta.json"
DEFAULT_CACHE_TTL_DAYS = 7

from garmin_auth import GarminStatsAuthError, build_client, default_tokenstore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="获取佳明用户画像 JSON 数组")
    parser.add_argument("mode", nargs="?", default="", help="可传 sync 或 同步用户画像")
    parser.add_argument("--refresh", action="store_true", help="强制刷新活动缓存后再输出画像")
    parser.add_argument("--no-cache-refresh", action="store_true", help="缓存不存在时也不自动生成")
    parser.add_argument("--cache-ttl-days", type=int, default=DEFAULT_CACHE_TTL_DAYS, help="活动缓存自动刷新间隔天数，默认 7 天")
    parser.add_argument("--region", choices=["cn", "global"], default=os.environ.get("GARMIN_REGION", "cn"))
    parser.add_argument("--tokenstore", default=None, help="Garmin token 目录；默认按区域读取")
    parser.add_argument("--auth-file", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--debug", action="store_true", help="向 stderr 输出调试信息")
    return parser.parse_args()


def debug(msg: str, enabled: bool) -> None:
    if enabled:
        print(f"[garmin-stats] {msg}", file=sys.stderr)


def format_time(seconds):
    if seconds is None or seconds <= 0:
        return None
    s = int(round(seconds))
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    if h > 0:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m:02d}:{sec:02d}"


def safe_get(client, endpoint: str, debug_enabled: bool = False):
    try:
        return client.garth.connectapi(endpoint)
    except Exception as exc:
        debug(f"API 失败 {endpoint}: {exc}", debug_enabled)
        return None


def fetch_all_activities(client, debug_enabled: bool = False) -> List[Dict]:
    activities = []
    start = 0
    limit = 100
    while True:
        batch = safe_get(
            client,
            f"/activitylist-service/activities/search/activities?start={start}&limit={limit}",
            debug_enabled,
        )
        if not batch:
            break
        activities.extend(batch)
        if len(batch) < limit:
            break
        start += limit
    return activities


def write_activity_cache(activities: List[Dict], region: str, display_name: Optional[str]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with CACHE_FILE.open("w", encoding="utf-8") as f:
        json.dump(activities, f, ensure_ascii=False, indent=2)
    meta = {
        "updated_at": datetime.now().isoformat(),
        "count": len(activities),
        "region": region,
        "display_name": display_name,
    }
    with CACHE_META_FILE.open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def load_activity_cache() -> Optional[List[Dict]]:
    if not CACHE_FILE.exists():
        return None
    try:
        with CACHE_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else None
    except Exception:
        return None


def cache_note() -> Optional[str]:
    if not CACHE_META_FILE.exists():
        return None
    try:
        with CACHE_META_FILE.open("r", encoding="utf-8") as f:
            meta = json.load(f)
        updated_at = meta.get("updated_at")
        count = meta.get("count")
        if updated_at:
            return f"活动缓存更新于 {updated_at[:19]}，共 {count} 条"
    except Exception:
        return None
    return None


def cache_age_days() -> Optional[float]:
    if not CACHE_META_FILE.exists():
        return None
    try:
        with CACHE_META_FILE.open("r", encoding="utf-8") as f:
            meta = json.load(f)
        updated_at = meta.get("updated_at")
        if not updated_at:
            return None
        dt = datetime.fromisoformat(updated_at)
        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        return (now - dt).total_seconds() / 86400
    except Exception:
        return None


def cache_region() -> Optional[str]:
    if not CACHE_META_FILE.exists():
        return None
    try:
        with CACHE_META_FILE.open("r", encoding="utf-8") as f:
            meta = json.load(f)
        region = meta.get("region")
        return str(region) if region else None
    except Exception:
        return None


def cache_is_fresh(ttl_days: int) -> bool:
    if ttl_days <= 0:
        return False
    age = cache_age_days()
    return age is not None and age <= ttl_days


def ensure_activity_cache(client, region: str, display_name: Optional[str], args: argparse.Namespace) -> List[Dict]:
    activities = None if args.refresh else load_activity_cache()
    cached_region = cache_region()
    region_matches = cached_region in (None, region)
    if activities is not None and region_matches and cache_is_fresh(args.cache_ttl_days):
        age = cache_age_days()
        age_text = f"{age:.1f} 天" if age is not None else "未知"
        debug(f"使用活动缓存: {len(activities)} 条，缓存年龄 {age_text}", args.debug)
        return activities
    if args.no_cache_refresh:
        if activities is not None:
            if not region_matches:
                debug(
                    f"活动缓存 region={cached_region} 与当前 region={region} 不一致；"
                    "--no-cache-refresh 已启用，继续使用旧缓存",
                    args.debug,
                )
            else:
                debug("活动缓存已过期，但 --no-cache-refresh 已启用，继续使用旧缓存", args.debug)
            return activities
        debug("活动缓存不存在且 --no-cache-refresh 已启用", args.debug)
        return []
    if activities is None:
        debug("活动缓存不存在，自动生成", args.debug)
    elif args.refresh:
        debug("收到 --refresh，强制刷新活动缓存", args.debug)
    elif not region_matches:
        debug(f"活动缓存 region={cached_region} 与当前 region={region} 不一致，自动刷新", args.debug)
    else:
        age = cache_age_days()
        age_text = f"{age:.1f} 天" if age is not None else "未知"
        debug(f"活动缓存超过 {args.cache_ttl_days} 天或元数据缺失，自动刷新；当前年龄 {age_text}", args.debug)
    activities = fetch_all_activities(client, args.debug)
    write_activity_cache(activities, region, display_name)
    return activities


def activity_type(activity: dict) -> str:
    return str(activity.get("activityType", {}).get("typeKey") or "")


def distance_m(activity: dict) -> float:
    try:
        return float(activity.get("distance") or 0)
    except Exception:
        return 0.0


def build_profile(args: argparse.Namespace) -> List[Dict]:
    try:
        import pytz
    except ModuleNotFoundError:
        raise RuntimeError("缺少依赖 pytz。请先在 skill 目录运行: python -m pip install -r requirements.txt")

    tokenstore = args.tokenstore or args.auth_file or str(default_tokenstore(args.region))
    client, garth_client, token_path = build_client(args.region, tokenstore)
    debug(f"使用 Garmin token: {token_path}", args.debug)
    display_name = garth_client.profile["displayName"]

    today = date.today()

    # 1. 用户基础信息（实时）
    personal_data = safe_get(
        client,
        f"/userprofile-service/userprofile/personal-information/{display_name}",
        args.debug,
    )

    username = None
    age = None
    gender = None
    vo2_max = None
    height = None
    weight = None

    if personal_data:
        username = (
            personal_data.get("userInfo", {}).get("fullName")
            or personal_data.get("fullName")
            or garth_client.profile.get("fullName")
        )
        age = personal_data.get("userInfo", {}).get("age") or personal_data.get("age")
        gender = personal_data.get("userInfo", {}).get("genderType") or personal_data.get("gender")
        if gender == "MALE":
            gender = "男"
        elif gender == "FEMALE":
            gender = "女"
        vo2_max = personal_data.get("biometricProfile", {}).get("vo2Max")
        if vo2_max:
            vo2_max = round(float(vo2_max), 1)
        height = personal_data.get("biometricProfile", {}).get("height")
        if height:
            height = round(float(height), 1)
        weight = personal_data.get("biometricProfile", {}).get("weight")
        if weight:
            weight = round(float(weight) / 1000, 1)

    if not vo2_max:
        settings_data = safe_get(
            client,
            f"/userprofile-service/userprofile/user-settings/{display_name}",
            args.debug,
        )
        if settings_data:
            vo2_max = settings_data.get("userSettings", {}).get("vo2MaxRunning")
            if vo2_max:
                vo2_max = round(float(vo2_max), 1)

    # 2. 静息心率、HRV、睡眠、平均入睡时间（实时，近 7 天）
    rhr_list, hrv_list, sleep_list = [], [], []
    bedtime_minutes = []
    local_tz = pytz.timezone("Asia/Shanghai")

    for i in range(1, 8):
        d = (today - timedelta(days=i)).isoformat()
        data = safe_get(
            client,
            f"/wellness-service/wellness/dailySleepData/{display_name}?date={d}",
            args.debug,
        )
        if not data:
            continue
        if data.get("restingHeartRate"):
            rhr_list.append(data["restingHeartRate"])
        if data.get("avgOvernightHrv"):
            hrv_list.append(float(data["avgOvernightHrv"]))
        dto = data.get("dailySleepDTO", {})
        sec = dto.get("sleepTimeSeconds", 0)
        if sec and sec > 0:
            sleep_list.append(sec / 3600)
        sleep_start_gmt = dto.get("sleepStartTimestampGMT")
        if sleep_start_gmt:
            dt_gmt = datetime.fromtimestamp(sleep_start_gmt / 1000, tz=timezone.utc)
            dt_local = dt_gmt.astimezone(local_tz)
            minutes = dt_local.hour * 60 + dt_local.minute
            if minutes < 12 * 60:
                minutes += 24 * 60
            bedtime_minutes.append(minutes)

    resting_hr = round(sum(rhr_list) / len(rhr_list)) if rhr_list else None
    hrv = round(sum(hrv_list) / len(hrv_list), 1) if hrv_list else None
    sleep_hours = round(sum(sleep_list) / len(sleep_list), 1) if sleep_list else None
    avg_bedtime = None
    if bedtime_minutes:
        avg_min = sum(bedtime_minutes) / len(bedtime_minutes)
        avg_bedtime = f"{int(avg_min // 60) % 24:02d}:{int(avg_min % 60):02d}"

    # 3. FTP 和乳酸阈值（实时）
    bio_data = safe_get(client, "/biometric-service/biometric/current", args.debug)
    ftp = None
    lthr = None
    lthr_pace = None
    if bio_data:
        if bio_data.get("functionalThresholdPower") and bio_data["functionalThresholdPower"].get("value"):
            ftp = bio_data["functionalThresholdPower"]["value"]
        if bio_data.get("lactateThresholdHeartRate") and bio_data["lactateThresholdHeartRate"].get("value"):
            lthr = bio_data["lactateThresholdHeartRate"]["value"]
        if bio_data.get("lactateThresholdSpeed") and bio_data["lactateThresholdSpeed"].get("value"):
            speed_ms = bio_data["lactateThresholdSpeed"]["value"] * 10
            pace_min_per_km = 1000 / speed_ms / 60
            minutes = int(pace_min_per_km)
            seconds = int((pace_min_per_km - minutes) * 60)
            lthr_pace = f"{minutes}:{seconds:02d}"

    # 4. 官方个人纪录和比赛预测（实时）
    prs = safe_get(client, f"/personalrecord-service/personalrecord/prs/{display_name}", args.debug)
    running_type_map = {1: "1km", 2: "1mile", 3: "5km", 4: "10km", 5: "half", 6: "full"}
    cycling_type_map = {8: "ride_time"}
    swimming_type_map = {17: "swim_distance", 18: "swim_100m"}
    running_pb, cycling_pr, swimming_pr = {}, {}, {}

    if prs:
        for pr in prs:
            at = pr.get("activityType")
            tid = pr.get("typeId")
            val = pr.get("value")
            if val is None:
                continue
            if at == "running" and tid in running_type_map:
                running_pb[running_type_map[tid]] = val
            elif at == "cycling" and tid in cycling_type_map:
                cycling_pr[cycling_type_map[tid]] = val
            elif at == "lap_swimming" and tid in swimming_type_map:
                swimming_pr[swimming_type_map[tid]] = int(round(val))

    pb_1k = format_time(running_pb.get("1km"))
    pb_1mile = format_time(running_pb.get("1mile"))
    pb_5k = format_time(running_pb.get("5km"))
    pb_10k = format_time(running_pb.get("10km"))
    pb_half = format_time(running_pb.get("half"))
    pb_full = format_time(running_pb.get("full"))
    pb_ride_time = format_time(cycling_pr.get("ride_time"))

    rp_5k = rp_10k = rp_half = rp_full = None
    try:
        rp = client.get_race_predictions()
        if rp:
            rp_5k = format_time(rp.get("time5K"))
            rp_10k = format_time(rp.get("time10K"))
            rp_half = format_time(rp.get("timeHalfMarathon"))
            rp_full = format_time(rp.get("timeMarathon"))
    except Exception as exc:
        debug(f"比赛预测获取失败: {exc}", args.debug)

    # 5. 活动历史字段（缓存；必要时刷新）
    all_activities = ensure_activity_cache(client, args.region, display_name, args)
    runs = [a for a in all_activities if activity_type(a) == "running"]
    hikes = [a for a in all_activities if activity_type(a) in {"hiking", "walking", "trekking"}]
    cycles = [a for a in all_activities if activity_type(a) == "cycling"]
    swims = [a for a in all_activities if activity_type(a) in {"swimming", "lap_swimming"}]

    longest_run_km = round(max((distance_m(a) for a in runs), default=0) / 1000, 2) if runs else None
    total_run_km = round(sum(distance_m(a) for a in runs) / 1000, 1) if runs else None
    longest_hike_km = round(max((distance_m(a) for a in hikes), default=0) / 1000, 1) if hikes else None
    total_hike_km = round(sum(distance_m(a) for a in hikes) / 1000, 1) if hikes else None
    longest_cycle_km = round(max((distance_m(a) for a in cycles), default=0) / 1000, 1) if cycles else None
    total_cycle_km = round(sum(distance_m(a) for a in cycles) / 1000, 1) if cycles else None
    total_swim_km = round(sum(distance_m(a) for a in swims) / 1000, 1) if swims else None

    # 6. 身体成分（实时，最近 7 天，来自智能秤）
    body_composition = {}
    try:
        comp_data = client.get_body_composition((today - timedelta(days=7)).isoformat(), today.isoformat())
        if comp_data and comp_data.get("dateWeightList"):
            with_fat = [r for r in comp_data["dateWeightList"] if r.get("bodyFat") and r["bodyFat"] > 0]
            latest_comp = max(with_fat, key=lambda x: x["calendarDate"]) if with_fat else max(comp_data["dateWeightList"], key=lambda x: x["calendarDate"])
            body_composition["bmi"] = round(latest_comp.get("bmi"), 1) if latest_comp.get("bmi") else None
            body_composition["body_fat_percent"] = latest_comp.get("bodyFat") if latest_comp.get("bodyFat", 0) > 0 else None
            body_composition["body_water_percent"] = latest_comp.get("bodyWater") if latest_comp.get("bodyWater", 0) > 0 else None
            if latest_comp.get("boneMass") and latest_comp["boneMass"] > 0:
                body_composition["bone_mass_kg"] = round(latest_comp["boneMass"] / 1000, 2)
            if latest_comp.get("muscleMass") and latest_comp["muscleMass"] > 0:
                body_composition["muscle_mass_kg"] = round(latest_comp["muscleMass"] / 1000, 2)
            body_composition["metabolic_age"] = latest_comp.get("metabolicAge")
            body_composition["visceral_fat"] = latest_comp.get("visceralFat")
    except Exception as exc:
        debug(f"身体成分获取失败: {exc}", args.debug)

    output = [
        {"metric": "username", "value": username},
        {"metric": "age", "value": age},
        {"metric": "gender", "value": gender},
        {"metric": "resting_heart_rate", "value": resting_hr},
        {"metric": "hrv", "value": hrv},
        {"metric": "avg_sleep_hours", "value": sleep_hours},
        {"metric": "avg_bedtime", "value": avg_bedtime},
        {"metric": "vo2_max", "value": vo2_max},
        {"metric": "1km_pb", "value": pb_1k},
        {"metric": "1mile_pb", "value": pb_1mile},
        {"metric": "5km_pb", "value": pb_5k},
        {"metric": "10km_pb", "value": pb_10k},
        {"metric": "half_marathon_pb", "value": pb_half},
        {"metric": "full_marathon_pb", "value": pb_full},
        {"metric": "race_predict_5k", "value": rp_5k},
        {"metric": "race_predict_10k", "value": rp_10k},
        {"metric": "race_predict_half", "value": rp_half},
        {"metric": "race_predict_full", "value": rp_full},
        {"metric": "longest_run_km", "value": longest_run_km, "note": cache_note()},
        {"metric": "total_run_km", "value": total_run_km, "note": cache_note()},
        {"metric": "longest_hike_km", "value": longest_hike_km, "note": cache_note()},
        {"metric": "total_hike_km", "value": total_hike_km, "note": cache_note()},
        {"metric": "longest_ride_time", "value": pb_ride_time},
        {"metric": "cycling_40km_time", "value": None},
        {"metric": "cycling_80km_time", "value": None},
        {"metric": "longest_cycle_km", "value": longest_cycle_km, "note": cache_note()},
        {"metric": "total_cycle_km", "value": total_cycle_km, "note": cache_note()},
        {"metric": "longest_swim_distance_m", "value": swimming_pr.get("swim_distance")},
        {"metric": "total_swim_km", "value": total_swim_km, "note": cache_note()},
        {"metric": "swimming_100m_pb", "value": format_time(swimming_pr.get("swim_100m"))},
        {"metric": "lactate_threshold_hr", "value": lthr},
        {"metric": "lactate_threshold_pace", "value": lthr_pace},
        {"metric": "ftp_watts", "value": ftp},
        {"metric": "height_cm", "value": height},
        {"metric": "weight_kg", "value": weight},
        {"metric": "bmi", "value": body_composition.get("bmi")},
        {"metric": "body_fat_percent", "value": body_composition.get("body_fat_percent")},
        {"metric": "body_water_percent", "value": body_composition.get("body_water_percent")},
        {"metric": "bone_mass_kg", "value": body_composition.get("bone_mass_kg")},
        {"metric": "muscle_mass_kg", "value": body_composition.get("muscle_mass_kg")},
        {"metric": "metabolic_age", "value": body_composition.get("metabolic_age")},
        {"metric": "visceral_fat", "value": body_composition.get("visceral_fat")},
    ]

    return output


def main() -> None:
    args = parse_args()
    try:
        output = build_profile(args)
    except GarminStatsAuthError as exc:
        raise SystemExit(str(exc))
    except RuntimeError as exc:
        raise SystemExit(str(exc))
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
