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


def _distance_points(items):
    return json.dumps([{"distance_m": distance, "t_sec": elapsed} for distance, elapsed in items])


class RunningCyclingPreviewMaterializerTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        _create_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_running_5k_best_effort_uses_internal_window_not_whole_activity_average(self):
        self.conn.executemany(
            """
            INSERT INTO activities (
                id, sport_type, start_time, dist_km, duration_sec, points_json, is_mock
            )
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            [
                ("run-15k", "running", "2026-07-16T08:00:00Z", 15.0, 5200, _distance_points([(0, 0), (5000, 1560), (15000, 5200)])),
                ("run-5-6k", "running", "2026-07-15T08:00:00Z", 5.6, 1700, _distance_points([(0, 0), (5000, 1440), (5600, 1700)])),
            ],
        )
        before = _counts(self.conn)

        result = career_backend.preview_career_records({"sport": "running", "max_activities": 10}, conn=self.conn)
        after = _counts(self.conn)

        best_5k = next(item for item in result["preview_records"] if item["record_key"] == "running_5k")
        self.assertEqual(best_5k["activity_id"], "run-5-6k")
        self.assertEqual(best_5k["metric"]["value"], 1440)
        self.assertEqual(best_5k["source_mode"], "best_effort_distance")
        self.assertEqual(best_5k["range"]["start_distance_m"], 0)
        self.assertEqual(best_5k["range"]["end_distance_m"], 5000)
        self.assertEqual(before, after)

    def test_cycling_preview_materializes_distance_totals_and_power_missing_reasons(self):
        self.conn.execute(
            """
            INSERT INTO activities (
                id, sport_type, start_time, dist_km, duration_sec, gain_m, points_json, is_mock
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                "ride-40k",
                "cycling",
                "2026-07-16T08:00:00Z",
                40.0,
                5400,
                600,
                _distance_points([(0, 0), (10000, 1500), (20000, 2800), (40000, 5400)]),
            ),
        )
        before = _counts(self.conn)

        result = career_backend.preview_career_records({"sport": "cycling", "max_activities": 10}, conn=self.conn)
        after = _counts(self.conn)

        record_keys = {item["record_key"] for item in result["preview_records"]}
        candidate_keys = {item["record_key"] for item in result["preview_candidates"]}
        self.assertIn("cycling_longest_distance", record_keys)
        self.assertIn("cycling_max_ascent", record_keys)
        self.assertIn("cycling_longest_elapsed_time", record_keys)
        self.assertIn("cycling_fastest_10k", candidate_keys)
        self.assertIn("power_stream_missing", result["by_reason"])
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
