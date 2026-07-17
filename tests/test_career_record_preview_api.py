import json
import sqlite3
import unittest
from unittest import mock

import career_backend
import main


def _create_preview_schema(conn: sqlite3.Connection) -> None:
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
            max_alt_m REAL,
            avg_power REAL,
            max_power REAL,
            normalized_power REAL,
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


def _counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        for table in ("career_pb_records", "career_event_candidates", "career_record_curve_cache", "career_record_events")
    }


class CareerRecordPreviewApiTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        _create_preview_schema(self.conn)
        points = json.dumps([{"distance_m": 0, "t_sec": 0}, {"distance_m": 10000, "t_sec": 1800}])
        self.conn.executemany(
            """
            INSERT INTO activities (
                id, sport_type, sub_sport_type, start_time, dist_km, duration_sec,
                gain_m, max_alt_m, avg_power, points_json, laps_json, deleted_at, is_mock
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("run-1", "running", "", "2026-07-16T08:00:00Z", 10.0, 1800, None, None, None, points, "", None, 0),
                ("ride-1", "cycling", "", "2026-07-15T08:00:00Z", 40.0, 5400, 500, 1200, 210, points, "", None, 0),
                ("ebike-1", "e_biking", "", "2026-07-14T08:00:00Z", 20.0, 3600, 200, 500, 120, points, "", None, 0),
                ("mock-1", "running", "", "2026-07-13T08:00:00Z", 5.0, 1500, None, None, None, points, "", None, 1),
                ("deleted-1", "running", "", "2026-07-12T08:00:00Z", 5.0, 1500, None, None, None, points, "", "2026-07-13T00:00:00Z", 0),
            ],
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_preview_defaults_to_readonly_dry_run_and_preserves_counts(self):
        before = _counts(self.conn)
        result = career_backend.preview_career_records({"max_activities": 10}, conn=self.conn)
        after = _counts(self.conn)

        self.assertTrue(result["ok"])
        self.assertTrue(result["dry_run"])
        self.assertTrue(result["readonly"])
        self.assertEqual(before, after)
        self.assertEqual(result["summary"]["mode"], "multi_sport_dry_run_materialized")
        self.assertTrue(result["summary"]["resolver_connected"])
        self.assertGreaterEqual(len(result["preview_records"]), 1)
        self.assertGreaterEqual(len(result["preview_candidates"]), 1)
        self.assertIn("running_5k", result["by_record_key"])
        self.assertIn("cycling_fastest_10k", result["by_record_key"])
        self.assertIn("running", result["by_sport"])
        self.assertIn("cycling", result["by_sport"])

    def test_preview_respects_max_activities_and_sport_filter(self):
        limited = career_backend.preview_career_records({"max_activities": 2}, conn=self.conn)
        cycling = career_backend.preview_career_records({"sport": "cycling", "max_activities": 10}, conn=self.conn)

        self.assertLessEqual(limited["summary"]["returned"], 2)
        self.assertEqual(cycling["by_sport"], {"cycling": 1})
        self.assertEqual(cycling["summary"]["adapter_ready"], 1)

    def test_preview_collects_ignored_reasons(self):
        result = career_backend.preview_career_records({"max_activities": 10}, conn=self.conn)

        self.assertIn("ebike_scope_excluded", result["by_reason"])
        self.assertIn("mock_activity_excluded", result["by_reason"])
        self.assertIn("activity_deleted", result["by_reason"])
        self.assertGreaterEqual(len(result["ignored"]), 3)

    def test_preview_payload_is_safe(self):
        result = career_backend.preview_career_records({"max_activities": 10}, conn=self.conn)
        payload = json.dumps(result, ensure_ascii=False, sort_keys=True)

        self.assertNotIn("points_json", payload)
        self.assertNotIn("track_json", payload)
        self.assertNotIn('"power_stream"', payload)
        self.assertNotIn("laps_json", payload)
        self.assertNotIn("file_path", payload)
        self.assertNotIn("device_serial", payload)
        self.assertIn("power_stream_missing", result["by_reason"])

    def test_pywebview_bridge_returns_success_envelope(self):
        fake = {
            "ok": True,
            "dry_run": True,
            "readonly": True,
            "run_id": "records_v2_preview:test",
            "summary": {"mode": "adapter_dispatch_only"},
            "metrics": {"processed": 1, "returned_count": 1},
            "by_sport": {"running": 1},
            "by_reason": {},
        }
        with mock.patch("career_backend.preview_career_records", return_value=fake):
            response = main.Api().preview_career_records({"sport": "running"})

        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["run_id"], "records_v2_preview:test")

    def test_pywebview_bridge_rejects_apply_payload(self):
        response = main.Api().preview_career_records({"dry_run": False, "apply_to_real_db": True})

        self.assertFalse(response["ok"])
        self.assertIn("dry-run", response["msg"])


if __name__ == "__main__":
    unittest.main()
