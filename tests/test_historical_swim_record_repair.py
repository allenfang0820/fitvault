import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import main


def _create_activity_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY,
            sport_type TEXT,
            sub_sport_type TEXT,
            start_time TEXT,
            start_time_utc TEXT,
            dist_km REAL,
            distance REAL,
            duration_sec INTEGER,
            duration INTEGER,
            gain_m REAL,
            max_alt_m REAL,
            avg_power REAL,
            max_power REAL,
            normalized_power REAL,
            points_json TEXT,
            track_json TEXT,
            laps_json TEXT,
            deleted_at TEXT,
            is_mock INTEGER DEFAULT 0
        )
        """
    )


class HistoricalSwimRecordRepairTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        _create_activity_table(self.conn)
        self.conn.execute(
            """
            INSERT INTO activities (
                id, sport_type, sub_sport_type, start_time, dist_km,
                duration_sec, duration, points_json, track_json, laps_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                "swimming",
                "open_water",
                "2026-07-01T08:00:00+08:00",
                0.8,
                600,
                600,
                json.dumps([
                    {"distance_m": 0, "elapsed_sec": 0},
                    {"distance_m": 800, "elapsed_sec": 600},
                ]),
                json.dumps([
                    {"distance_m": 0, "elapsed_sec": 0},
                    {"distance_m": 800, "elapsed_sec": 600},
                ]),
                "[]",
            ),
        )
        self.conn.execute(
            """
            INSERT INTO activities (
                id, sport_type, sub_sport_type, start_time, dist_km,
                duration_sec, duration, points_json, track_json, laps_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                2,
                "swimming",
                "lap_swimming",
                "2026-07-02T08:00:00+08:00",
                0.2,
                200,
                200,
                "[]",
                "[]",
                "[]",
            ),
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_dry_run_uses_activity_facts_and_keeps_pool_missing_controlled(self):
        result = main.repair_historical_swim_records({"dry_run": True}, conn=self.conn)

        self.assertTrue(result["ok"])
        self.assertTrue(result["dry_run"])
        self.assertFalse(result["summary"]["would_write"])
        pool_plan = next(item for item in result["plans"] if item["activity_id"] == "2")
        self.assertEqual(pool_plan["source"], "source_missing")
        self.assertIn("pool_length_missing", pool_plan["reason_codes"])
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM career_record_metric_results").fetchone()[0],
            0,
        )

    def test_apply_rebuilds_open_water_metric_results_and_events(self):
        result = main.repair_historical_swim_records({"dry_run": False}, conn=self.conn)

        self.assertTrue(result["ok"])
        self.assertFalse(result["dry_run"])
        row = self.conn.execute(
            """
            SELECT swim_water_scope, swim_pool_length_m
            FROM activities
            WHERE id = 1
            """
        ).fetchone()
        self.assertEqual(row, ("open_water_swimming", None))
        metric = self.conn.execute(
            """
            SELECT record_key, status
            FROM career_record_metric_results
            WHERE activity_id = '1'
            ORDER BY record_key
            """
        ).fetchall()
        self.assertIn(("open_water_swim_750m", "available"), metric)
        events = self.conn.execute(
            """
            SELECT event_type
            FROM career_record_events
            WHERE activity_id = '1'
              AND record_key = 'open_water_swim_750m'
            """
        ).fetchall()
        self.assertIn(("current_best",), events)

    def test_apply_is_idempotent_when_fit_lengths_differ_from_persisted_lengths(self):
        self.conn.execute(
            """
            CREATE TABLE activity_source_files (
                id INTEGER PRIMARY KEY,
                activity_id INTEGER,
                file_path TEXT,
                updated_at TEXT
            )
            """
        )
        self.conn.execute(
            """
            INSERT INTO activities (
                id, sport_type, sub_sport_type, start_time, dist_km,
                duration_sec, duration, points_json, track_json, laps_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                3,
                "swimming",
                "lap_swimming",
                "2026-07-03T08:00:00+08:00",
                0.2,
                200,
                200,
                "[]",
                "[]",
                json.dumps([{
                    "lap_index": 0,
                    "distance_m": 50,
                    "elapsed_sec": 60,
                    "length_distance_m": 25,
                    "swim_stroke": "freestyle",
                }]),
            ),
        )
        with tempfile.NamedTemporaryFile() as source:
            self.conn.execute(
                """
                INSERT INTO activity_source_files (activity_id, file_path, updated_at)
                VALUES (?, ?, ?)
                """,
                (3, source.name, "2026-08-02T00:00:00Z"),
            )
            self.conn.commit()
            parsed_fit = {
                "basic_info": {
                    "sport": "swimming",
                    "sub_sport": "lap_swimming",
                    "pool_length_m": 25,
                    "pool_length_unit": "m",
                    "swim_stroke": "freestyle",
                },
                "lap_data": [{
                    "lap_index": 0,
                    "total_distance": 100,
                    "total_timer_time": 120000,
                    "lengths": 4,
                    "swim_stroke": "freestyle",
                }],
            }
            with patch.object(main.FITCoreEngine, "parse_fit_file", return_value=parsed_fit):
                applied = main.repair_historical_swim_records(
                    {"dry_run": False, "activity_ids": [3]},
                    conn=self.conn,
                )
                self.assertFalse(applied["dry_run"])
                rerun = main.repair_historical_swim_records(
                    {"dry_run": True, "activity_ids": [3]},
                    conn=self.conn,
                )

        self.assertEqual(rerun["summary"]["planned_metric_upserts"], 0)
        self.assertEqual(rerun["summary"]["planned_metric_invalidations"], 0)
        self.assertEqual(rerun["summary"]["planned_lengths_updates"], 0)
        stored_lengths = self.conn.execute(
            "SELECT laps_json FROM activities WHERE id = 3"
        ).fetchone()[0]
        stored_length_rows = json.loads(stored_lengths)
        self.assertEqual(stored_length_rows[0]["distance_m"], 50)
        self.assertNotEqual(stored_length_rows[0]["distance_m"], 100)


if __name__ == "__main__":
    unittest.main()
