#!/usr/bin/env python3
"""生成或刷新佳明活动缓存。

活动缓存用于 PB、最长距离、累计里程等历史活动字段。睡眠、HRV、静息心率、
体重、VO2max 等日更字段由 get_garmin_stats.py 每次实时获取，不依赖本缓存。
"""
import argparse
import json
import os
import sys
from datetime import datetime
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

from garmin_auth import GarminStatsAuthError, build_client, default_tokenstore


def fetch_all_activities(client, limit: int, verbose: bool = True) -> List[Dict]:
    activities = []
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


def write_cache(activities: List[Dict], region: str, display_name: Optional[str]) -> None:
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
    parser.add_argument("--tokenstore", default=None, help="Garmin token 目录；默认按区域读取")
    parser.add_argument("--auth-file", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    print("正在连接佳明账户...")
    tokenstore = args.tokenstore or args.auth_file or str(default_tokenstore(args.region))
    try:
        client, garth_client, token_path = build_client(args.region, tokenstore)
    except GarminStatsAuthError as exc:
        raise SystemExit(str(exc))
    display_name = garth_client.profile.get("displayName")
    print(f"使用 token: {token_path}")

    print("正在获取活动列表（活动多时可能需要几分钟）...")
    activities = fetch_all_activities(client, args.limit)
    write_cache(activities, args.region, display_name)

    print(f"共获取 {len(activities)} 个活动")
    print(f"缓存已保存: {CACHE_FILE}")
    print(f"缓存元数据已保存: {CACHE_META_FILE}")


if __name__ == "__main__":
    main()
