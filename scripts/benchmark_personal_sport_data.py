#!/usr/bin/env python3
"""Read-only microbenchmarks for personal sport data APIs.

Measures cold-ish first call and warm repeated calls for the activity list,
activity detail, and fatigue review paths. The script does not write to the
database; it only calls existing read APIs and reports elapsed time plus JSON
payload size.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main
import profile_backend


def _payload_bytes(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000.0, 2)


def _select_activity_ids() -> tuple[int | None, int | None]:
    db_path = Path(profile_backend.DB_PATH)
    if not db_path.exists():
        return None, None
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        recent = conn.execute(
            """
            SELECT id
            FROM activities
            WHERE deleted_at IS NULL
              AND COALESCE(source_type, 'fit_sdk') = 'fit_sdk'
              AND COALESCE(is_mock, 0) = 0
            ORDER BY COALESCE(start_time, updated_at) DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
        long_track = conn.execute(
            """
            SELECT id
            FROM activities
            WHERE deleted_at IS NULL
              AND COALESCE(source_type, 'fit_sdk') = 'fit_sdk'
              AND COALESCE(is_mock, 0) = 0
            ORDER BY LENGTH(COALESCE(track_json, points_json, '')) DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
        return (
            int(recent["id"]) if recent else None,
            int(long_track["id"]) if long_track else None,
        )
    finally:
        conn.close()


def _measure(label: str, fn: Callable[[], dict[str, Any]], repeats: int) -> dict[str, Any]:
    samples: list[dict[str, Any]] = []
    for index in range(max(1, repeats)):
        started = time.perf_counter()
        response = fn()
        elapsed = _elapsed_ms(started)
        data = response.get("data") if isinstance(response, dict) else None
        samples.append(
            {
                "run": index + 1,
                "elapsed_ms": elapsed,
                "ok": bool(response.get("ok")) if isinstance(response, dict) else False,
                "code": response.get("code") if isinstance(response, dict) else None,
                "api_elapsed_ms": data.get("api_elapsed_ms") if isinstance(data, dict) else None,
                "startup_api_elapsed_ms": (
                    data.get("startup_trace", {}).get("api_elapsed_ms")
                    if isinstance(data, dict) and isinstance(data.get("startup_trace"), dict)
                    else None
                ),
                "payload_bytes": _payload_bytes(response),
            }
        )
    elapsed_values = [sample["elapsed_ms"] for sample in samples]
    return {
        "label": label,
        "runs": samples,
        "min_ms": min(elapsed_values),
        "max_ms": max(elapsed_values),
        "mean_ms": round(statistics.mean(elapsed_values), 2),
    }


def main_cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warm-runs", type=int, default=3, help="number of calls per benchmark")
    parser.add_argument("--activity-id", type=int, default=0, help="activity id for detail/review")
    parser.add_argument("--long-activity-id", type=int, default=0, help="long activity id for review")
    args = parser.parse_args()

    recent_id, long_id = _select_activity_ids()
    activity_id = args.activity_id or recent_id
    long_activity_id = args.long_activity_id or long_id or activity_id

    api = main.Api()
    benchmarks: list[tuple[str, Callable[[], dict[str, Any]]]] = [
        ("get_sport_hub_activity_page(1,10,'all','')", lambda: api.get_sport_hub_activity_page(1, 10, "all", "")),
        ("get_activity_list(1,20,'all','')", lambda: api.get_activity_list(1, 20, "all", "")),
    ]
    if activity_id:
        benchmarks.append((f"get_activity_detail({activity_id})", lambda: api.get_activity_detail(int(activity_id))))
    if long_activity_id:
        benchmarks.append((f"get_fatigue_review({long_activity_id})", lambda: api.get_fatigue_review(int(long_activity_id))))

    report = {
        "db_path": str(Path(profile_backend.DB_PATH).expanduser()),
        "recent_activity_id": activity_id,
        "long_activity_id": long_activity_id,
        "warm_runs": max(1, args.warm_runs),
        "benchmarks": [_measure(label, fn, max(1, args.warm_runs)) for label, fn in benchmarks],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
