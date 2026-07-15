#!/usr/bin/env python3
"""Read-only Records Center RC-02 PB range diff audit.

This script compares the current hard-coded running PB distance ranges with the
Records Center V1 +/-3% rule. It never writes to SQLite.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


RUNNING_TYPES = {
    "running",
    "run",
    "trail_running",
    "track_running",
    "road_running",
    "treadmill_running",
}

CURRENT_RANGES = {
    "running_5k": (4.8, 5.3, 5.0),
    "running_10k": (9.5, 10.8, 10.0),
    "running_half_marathon": (20.5, 21.7, 21.0975),
    "running_marathon": (41.0, 43.0, 42.195),
}

PERCENT_RANGES = {
    key: (standard * 0.97, standard * 1.03, standard)
    for key, (_, _, standard) in CURRENT_RANGES.items()
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        default=str(Path.home() / ".fitvault" / "user_profile.db"),
        help="SQLite database path. Default: ~/.fitvault/user_profile.db",
    )
    return parser.parse_args()


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _point_elapsed(row: sqlite3.Row) -> int | None:
    raw = row["points_json"] or row["track_json"]
    if not raw:
        return None
    try:
        points = json.loads(raw)
    except Exception:
        return None
    if not isinstance(points, list):
        return None
    times = [
        parsed
        for point in points
        if isinstance(point, dict)
        for parsed in [_parse_time(point.get("time"))]
        if parsed is not None
    ]
    if len(times) < 2:
        return None
    return int(round((max(times) - min(times)).total_seconds()))


def _time_quality(row: sqlite3.Row) -> tuple[str, int | None, int | None]:
    duration = int(row["duration_sec"] or row["duration"] or 0)
    elapsed = _point_elapsed(row)
    if duration <= 0:
        return "missing_time", elapsed, None
    if elapsed is None:
        return "semantics_unknown", elapsed, None
    diff = elapsed - duration
    if abs(diff) <= 5:
        return "reliable_elapsed", elapsed, diff
    if diff > 5:
        return "timer_time_only", elapsed, diff
    return "points_shorter_than_duration", elapsed, diff


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path.expanduser().resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _load_running_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    placeholders = ",".join("?" for _ in RUNNING_TYPES)
    params = tuple(RUNNING_TYPES) + tuple(RUNNING_TYPES)
    return conn.execute(
        f"""
        SELECT id, title, sport_type, sub_sport_type, start_time, dist_km, distance,
               duration_sec, duration, points_json, track_json
        FROM activities
        WHERE deleted_at IS NULL
          AND (
            lower(COALESCE(sport_type, '')) IN ({placeholders})
            OR lower(COALESCE(sub_sport_type, '')) IN ({placeholders})
          )
        ORDER BY id
        """,
        params,
    ).fetchall()


def _build_candidates(
    rows: list[sqlite3.Row],
    ranges: dict[str, tuple[float, float, float]],
) -> dict[str, list[dict[str, Any]]]:
    candidates: dict[str, list[dict[str, Any]]] = {key: [] for key in ranges}
    for row in rows:
        dist_km = row["dist_km"]
        duration = row["duration_sec"] or row["duration"]
        if dist_km is None or dist_km <= 0 or duration is None or duration <= 0:
            continue
        quality, point_elapsed, elapsed_diff = _time_quality(row)
        for key, (low, high, standard) in ranges.items():
            if low <= float(dist_km) <= high:
                candidates[key].append({
                    "activity_id": str(row["id"]),
                    "title": row["title"] or "",
                    "event_date": str(row["start_time"] or "")[:10],
                    "dist_km": round(float(dist_km), 5),
                    "duration_sec": int(duration),
                    "time_quality": quality,
                    "points_elapsed": point_elapsed,
                    "elapsed_diff": elapsed_diff,
                    "distance_error_pct": round(abs(float(dist_km) - standard) / standard * 100, 3),
                })
    for values in candidates.values():
        values.sort(key=lambda item: (item["duration_sec"], item["event_date"], item["activity_id"]))
    return candidates


def _active_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'career_pb_records'"
    ).fetchone()
    if not exists:
        return []
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT id, activity_id, pb_type, value, event_date, status
            FROM career_pb_records
            WHERE status = 'active'
            ORDER BY pb_type
            """
        )
    ]


def run_audit(db_path: Path) -> dict[str, Any]:
    with _connect_readonly(db_path) as conn:
        rows = _load_running_rows(conn)
        current = _build_candidates(rows, CURRENT_RANGES)
        percent = _build_candidates(rows, PERCENT_RANGES)
        by_type: dict[str, Any] = {}
        for key in CURRENT_RANGES:
            current_ids = {item["activity_id"] for item in current[key]}
            percent_ids = {item["activity_id"] for item in percent[key]}
            by_type[key] = {
                "current_count": len(current_ids),
                "percent_count": len(percent_ids),
                "common_count": len(current_ids & percent_ids),
                "added": [item for item in percent[key] if item["activity_id"] in percent_ids - current_ids],
                "removed": [item for item in current[key] if item["activity_id"] in current_ids - percent_ids],
                "current_best": current[key][0] if current[key] else None,
                "percent_best": percent[key][0] if percent[key] else None,
                "active_changes": (
                    current[key][0]["activity_id"] if current[key] else None,
                    percent[key][0]["activity_id"] if percent[key] else None,
                ),
            }
        return {
            "db": str(db_path.expanduser().resolve()),
            "running_activity_count": len(rows),
            "ranges": {
                "current": CURRENT_RANGES,
                "percent_3": PERCENT_RANGES,
            },
            "by_type": by_type,
            "current_table_active": _active_rows(conn),
        }


def main() -> None:
    args = _parse_args()
    result = run_audit(Path(args.db))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
