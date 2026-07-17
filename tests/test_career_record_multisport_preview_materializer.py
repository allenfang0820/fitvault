import json
import sqlite3
import unittest

import career_backend


def _create_schema(conn):
    conn.execute(
        """
        CREATE TABLE activities (
            id TEXT PRIMARY KEY,
            sport_type TEXT,
            sub_sport_type TEXT,
            start_time TEXT,
            start_time_utc TEXT,
            dist_km REAL,
            distance REAL,
            duration_sec REAL,
            duration REAL,
            gain_m REAL,
            ascent_m REAL,
            max_alt_m REAL,
            max_altitude_m REAL,
            avg_power REAL,
            max_power REAL,
            normalized_power REAL,
            power_points TEXT,
            points_json TEXT,
            track_json TEXT,
            laps_json TEXT,
            lengths_json TEXT,
            pool_length_m REAL,
            pool_length REAL,
            stroke_scope TEXT,
            swim_stroke TEXT,
            advanced_metrics TEXT,
            deleted_at TEXT,
            is_mock INTEGER
        )
        """
    )
    for table in ("career_pb_records", "career_event_candidates", "career_record_curve_cache", "career_record_events"):
        conn.execute(f"CREATE TABLE {table} (id TEXT)")


def _counts(conn):
    return {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("career_pb_records", "career_event_candidates", "career_record_curve_cache", "career_record_events")
    }


class MultiSportPreviewMaterializerTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        _create_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_hiking_open_water_pool_and_trail_preview_are_materialized_readonly(self):
        hiking_track = json.dumps([
            {"d": 0, "t": 0, "alt_m": 1000},
            {"d": 2000, "t": 1800, "alt_m": 1300},
            {"d": 5000, "t": 4500, "alt_m": 1250},
        ])
        open_water_points = json.dumps([
            {"distance_m": 0, "t_sec": 0},
            {"distance_m": 750, "t_sec": 900},
            {"distance_m": 1500, "t_sec": 1800},
        ])
        pool_lengths = json.dumps([
            {"index": 0, "elapsed_sec": 31, "stroke": "freestyle", "rest_after_sec": 0},
            {"index": 1, "elapsed_sec": 32, "stroke": "freestyle", "rest_after_sec": 0},
            {"index": 2, "elapsed_sec": 34, "stroke": "freestyle", "rest_after_sec": 60},
        ])
        trail_track = json.dumps([
            {"d": 0, "t": 0, "alt_m": 100},
            {"d": 1000, "t": 900, "alt_m": 220},
            {"d": 3000, "t": 2700, "alt_m": 480},
            {"d": 5000, "t": 4500, "alt_m": 430},
        ])
        self.conn.executemany(
            """
            INSERT INTO activities (
                id, sport_type, sub_sport_type, start_time, dist_km, duration_sec,
                gain_m, max_alt_m, points_json, lengths_json, pool_length_m, stroke_scope, is_mock
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            [
                ("hike-1", "hiking", "", "2026-07-16T08:00:00Z", 18.0, 14400, 900, 3200, hiking_track, "", None, "",),
                ("ow-1", "swimming", "open_water", "2026-07-15T08:00:00Z", 1.5, 1800, None, None, open_water_points, "", None, "",),
                ("pool-1", "swimming", "pool", "2026-07-14T08:00:00Z", None, 100, None, None, "", pool_lengths, 25, "freestyle",),
                ("trail-1", "trail_running", "", "2026-07-13T08:00:00Z", 30.0, 18000, 1800, 2600, trail_track, "", None, "",),
            ],
        )
        before = _counts(self.conn)

        result = career_backend.preview_career_records({"max_activities": 10}, conn=self.conn)
        after = _counts(self.conn)

        keys = {item["record_key"] for item in [*result["preview_records"], *result["preview_candidates"]]}
        self.assertIn("hiking_longest_distance", keys)
        self.assertIn("hiking_max_single_climb", keys)
        self.assertIn("open_water_swim_1500m", keys)
        self.assertIn("open_water_longest_distance", keys)
        self.assertIn("pool_swim_50m", keys)
        self.assertIn("trail_longest_distance", keys)
        self.assertIn("trail_max_single_climb", keys)
        self.assertIn("trail_sample_missing", result["by_reason"])
        self.assertEqual(result["summary"]["mode"], "multi_sport_dry_run_materialized")
        self.assertEqual(before, after)

    def test_pool_missing_length_stays_ignored_without_defaulting_25m(self):
        self.conn.execute(
            """
            INSERT INTO activities (
                id, sport_type, sub_sport_type, start_time, duration_sec, lengths_json, stroke_scope, is_mock
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                "pool-missing",
                "swimming",
                "pool",
                "2026-07-16T08:00:00Z",
                60,
                json.dumps([{"index": 0, "elapsed_sec": 30}]),
                "freestyle",
            ),
        )

        result = career_backend.preview_career_records({"sport": "pool_swimming", "max_activities": 10}, conn=self.conn)

        keys = {item["record_key"] for item in result["preview_records"]}
        ignored_reasons = {reason for item in result["ignored"] for reason in item.get("reason_codes", [])}
        self.assertNotIn("pool_swim_50m", keys)
        self.assertIn("pool_length_missing", ignored_reasons)


if __name__ == "__main__":
    unittest.main()
