import sqlite3
import unittest

import career_backend


class CareerRecordSourceVersionTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            """
            CREATE TABLE activities (
                id INTEGER PRIMARY KEY,
                sport_type TEXT,
                start_time TEXT,
                dist_km REAL,
                duration_sec INTEGER
            )
            """
        )

    def tearDown(self):
        self.conn.close()

    def test_refresh_returns_stable_content_version_for_idempotent_refresh(self):
        self.conn.execute(
            "INSERT INTO activities (id, sport_type, start_time, dist_km, duration_sec) VALUES (?, ?, ?, ?, ?)",
            (1, "running", "2026-07-01T08:00:00+08:00", 5.0, 1500),
        )
        first = career_backend.refresh_career_derived_events(self.conn)
        second = career_backend.refresh_career_derived_events(self.conn)

        self.assertIn("record_source_version", first)
        self.assertIsInstance(first["record_source_version"], int)
        self.assertEqual(first["record_source_version"], second["record_source_version"])
        records = career_backend.get_career_records({"sport": "running"}, conn=self.conn)
        self.assertEqual(records["source_version"], first["record_source_version"])

    def test_record_content_change_changes_version_without_timestamp_dependency(self):
        career_backend.ensure_career_schema(self.conn)
        first = career_backend._career_record_source_version(self.conn)
        self.conn.execute(
            """
            INSERT INTO career_record_metric_results (
                id, activity_id, record_key, sport, event_date, metric_name,
                metric_value_num, metric_unit, display_value, source_mode,
                record_family, comparison, scope_json, scope_hash, range_json,
                quality_json, eligibility_json, resolver_version, rule_version,
                input_fingerprint, result_fingerprint, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "metric:test",
                "activity-1",
                "open_water_swim_10k",
                "open_water_swimming",
                "2026-07-01",
                "elapsed_time_sec",
                3600.0,
                "seconds",
                "1:00:00",
                "distance_time_pb",
                "distance_time_pb",
                "min",
                "{}",
                "scope:test",
                "{}",
                "{}",
                "{}",
                career_backend.RECORD_METRIC_SERIES_RESOLVER_VERSION,
                "records-v3-series",
                "input-a",
                "result-a",
                "available",
            ),
        )
        self.conn.commit()
        second = career_backend._career_record_source_version(self.conn)
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
