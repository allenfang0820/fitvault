#!/usr/bin/env python3
"""生成或刷新佳明活动缓存。

活动缓存用于 PB、最长距离、累计里程等历史活动字段。睡眠、HRV、静息心率、
体重、VO2max 等日更字段由 get_garmin_stats.py 每次实时获取，不依赖本缓存。
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

hermes_libs = os.path.expanduser("~/Library/Application Support/QClaw/hermes/libs")
if hermes_libs in sys.path:
    sys.path.remove(hermes_libs)

AUTH_FILE = Path.home() / ".qclaw" / "workspace" / "garmin_auth.json"
CACHE_DIR = Path.home() / ".qclaw" / "workspace" / "garmin_data"
CACHE_FILE = CACHE_DIR / "all_activities.json"
CACHE_META_FILE = CACHE_DIR / "all_activities.meta.json"


def patch_garth_ssl_consumer() -> None:
    import garth

    try:
        result = subprocess.run(
            [
                "curl",
                "-s",
                "--max-time",
                "10",
                "https://thegarth.s3.amazonaws.com/oauth_consumer.json",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip().startswith("{"):
            garth.sso.OAUTH_CONSUMER = json.loads(result.stdout.strip())
    except Exception:
        pass


def build_client(region: str, auth_file: Path):
    try:
        import garminconnect
        import garth
    except ModuleNotFoundError as exc:
        raise SystemExit(
            f"缺少依赖 {exc.name}。请先运行: pip3 install -r ~/.qclaw/skills/garmin-stats/requirements.txt"
        )

    patch_garth_ssl_consumer()
    garth_client = garth.Client()
    garth_client.load(str(auth_file.expanduser()))
    client = garminconnect.Garmin(is_cn=(region == "cn"))
    client.garth = garth_client
    return client, garth_client


def fetch_all_activities(client, limit: int, verbose: bool = True) -> list[dict]:
    activities: list[dict] = []
    start = 0
    while True:
        batch = client.garth.connectapi(
            f"/activitylist-service/activities/search/activities"
            f"?start={start}&limit={limit}"
        )
        if not batch:
            break
        activities.extend(batch)
        if verbose:
            print(f"  已获取 {len(activities)} 个活动...")
        if len(batch) < limit:
            break
        start += limit
    return activities


def write_cache(activities: list[dict], region: str, display_name: str | None) -> None:
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


def main() -> None:
    parser = argparse.ArgumentParser(description="生成佳明活动缓存")
    parser.add_argument("--region", choices=["cn", "global"], default=os.environ.get("GARMIN_REGION", "cn"))
    parser.add_argument("--auth-file", default=str(AUTH_FILE))
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    print("正在连接佳明账户...")
    client, garth_client = build_client(args.region, Path(args.auth_file))
    display_name = garth_client.profile.get("displayName")

    print("正在获取活动列表（活动多时可能需要几分钟）...")
    activities = fetch_all_activities(client, args.limit)
    write_cache(activities, args.region, display_name)

    print(f"共获取 {len(activities)} 个活动")
    print(f"缓存已保存: {CACHE_FILE}")
    print(f"缓存元数据已保存: {CACHE_META_FILE}")


if __name__ == "__main__":
    main()
