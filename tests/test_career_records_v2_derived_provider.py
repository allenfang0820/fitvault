import json
import sqlite3
import unittest

import career_backend


FORBIDDEN = (
    "points_json",
    "track_json",
    "power_stream",
    "raw_fit",
    "file_path",
    "sqlite_master",
    "/Users/",
)


def assert_safe(testcase: unittest.TestCase, payload):
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    for forbidden in FORBIDDEN:
        testcase.assertNotIn(forbidden, text)


def create_activity_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE activities (
            id TEXT PRIMARY KEY,
            title TEXT,
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
            deleted_at TEXT,
            is_mock INTEGER
        )
        """
    )


class CareerRecordsV2DerivedProviderTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        create_activity_schema(self.conn)
        run_points = json.dumps([{"distance_m": 0, "t_sec": 0}, {"distance_m": 10000, "t_sec": 1800}])
        ride_points = json.dumps([{"distance_m": 0, "t_sec": 0, "power_w": 250}, {"distance_m": 120000, "t_sec": 7200, "power_w": 250}])
        ride_power = json.dumps([{"t": 0, "power_w": 250}, {"t": 1200, "power_w": 250}, {"t": 7200, "power_w": 230}])
        self.conn.executemany(
            """
            INSERT INTO activities (
                id, title, sport_type, start_time, dist_km, distance, duration_sec,
                gain_m, ascent_m, max_alt_m, max_altitude_m, avg_power, power_points,
                points_json, track_json, deleted_at, is_mock
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 0)
            """,
            [
                ("run-1", "Best 10K", "running", "2026-07-10T08:00:00Z", 10.0, 10000, 1800, None, None, None, None, None, "", run_points, ""),
                ("ride-1", "Long Ride", "cycling", "2026-07-11T08:00:00Z", 120.0, 120000, 7200, 1500, 1500, 1200, 1200, 250, ride_power, ride_points, ""),
                ("ride-2", "Short Ride", "cycling", "2026-07-01T08:00:00Z", 60.0, 60000, 4000, 600, 600, 900, 900, 220, ride_power, ride_points, ""),
                ("hike-1", "High Hike", "hiking", "2026-07-12T08:00:00Z", 22.0, 22000, 16000, 1200, 1200, 3500, 3500, None, "", "", ""),
            ],
        )
        self.conn.commit()

    def tearDown(self):
        career_backend._RECORDS_V2_DERIVED_CACHE.clear()
        career_backend._RECORDS_V2_ACTIVITY_FINGERPRINT_CACHE.clear()
        self.conn.close()

    def test_records_api_returns_v3_series_rows_without_writing_state(self):
        before = {
            table: int(self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("career_pb_records", "career_event_candidates", "career_record_events")
            if career_backend._table_exists(self.conn, table)
        }
        records = career_backend.get_career_records({"sport": "cycling"}, conn=self.conn)
        after = {
            table: int(self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("career_pb_records", "career_event_candidates", "career_record_events")
        }

        self.assertEqual(before, {key: 0 for key in before})
        self.assertEqual(after, {"career_pb_records": 0, "career_event_candidates": 0, "career_record_events": 0})
        self.assertGreaterEqual(records["summary"]["active_count"], 1)
        distance = next(record for record in records["records"] if record["record_key"] == "cycling_longest_distance")
        self.assertEqual(distance["id"], "catalog:cycling_longest_distance")
        self.assertEqual(distance["status"], "active")
        self.assertEqual(distance["source_mode"], "activity_total")
        self.assertEqual(distance["metric"]["display"], "120000 m")
        assert_safe(self, records)

    def test_chart_source_uses_metric_series_viewmodel_for_activity_total_records(self):
        records = career_backend.get_career_records({"sport": "cycling"}, conn=self.conn)["records"]
        distance = next(record for record in records if record["record_key"] == "cycling_longest_distance")

        series = career_backend.get_career_record_metric_series(
            {
                "record_key": "cycling_longest_distance",
                "sport": "cycling",
                "scope_hash": distance["scope"]["scope_hash"],
                "status": "available",
            },
            conn=self.conn,
        )

        self.assertEqual(series["record_key"], distance["record_key"])
        self.assertEqual(series["current_best"]["activity_id"], distance["activity_id"])
        self.assertEqual(series["current_best"]["metric"]["value"], distance["metric"]["value"])
        self.assertGreaterEqual(len(series["points"]), 1)
        self.assertTrue(all(point["status"] == "available" for point in series["points"]))
        assert_safe(self, series)

    def test_activity_total_history_uses_summary_only_fast_provider(self):
        career_backend._RECORDS_V2_DERIVED_CACHE.clear()
        career_backend._RECORDS_V2_ACTIVITY_FINGERPRINT_CACHE.clear()
        original = career_backend._preview_career_record_activity_rows

        def fail_if_heavy_preview_reader_is_used(*_args, **_kwargs):
            raise AssertionError("activity total derived history must not read heavy preview columns")

        career_backend._preview_career_record_activity_rows = fail_if_heavy_preview_reader_is_used
        try:
            history = career_backend.get_career_record_history(
                {"record_key": "cycling_longest_distance"},
                conn=self.conn,
            )
        finally:
            career_backend._preview_career_record_activity_rows = original
            career_backend._RECORDS_V2_DERIVED_CACHE.clear()
            career_backend._RECORDS_V2_ACTIVITY_FINGERPRINT_CACHE.clear()

        self.assertGreaterEqual(len(history["chart"]["points"]), 1)
        self.assertTrue(all(record["record_key"] == "cycling_longest_distance" for record in history["records"]))
        assert_safe(self, history)

    def test_candidate_api_appends_disabled_first_batch_derived_candidates(self):
        candidates = career_backend.get_career_record_candidates({"sport": "cycling", "include_derived": True}, conn=self.conn)

        self.assertTrue(any(candidate["record_key"] == "cycling_longest_distance" for candidate in candidates["candidates"]))
        derived = next(candidate for candidate in candidates["candidates"] if candidate["record_key"] == "cycling_longest_distance")
        self.assertEqual(derived["candidate_state"], "derived_candidate")
        self.assertFalse(derived["quality"]["can_user_confirm"])
        self.assertIn("not_written_to_candidate_store", derived["quality"]["reason_codes"])
        assert_safe(self, candidates)


if __name__ == "__main__":
    unittest.main()
