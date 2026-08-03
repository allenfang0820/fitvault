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
            distance_m REAL,
            distance REAL,
            dist_km REAL,
            duration_sec REAL,
            points_json TEXT,
            distance_source TEXT,
            deleted_at TEXT,
            is_mock INTEGER
        )
        """
    )
    career_backend.ensure_career_schema(conn)


def _open_water_stream(distance_m=10000, elapsed_sec=14400):
    return json.dumps([
        {"distance_m": round(distance_m * index / 8, 3), "t_sec": round(elapsed_sec * index / 8, 3)}
        for index in range(9)
    ])


class CareerRecordOpenWaterMetricSeriesTest(unittest.TestCase):
    def setUp(self):
        career_backend._clear_record_metric_series_cache()
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        _create_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def _insert_activity(self, activity_id, **overrides):
        activity = {
            "id": activity_id,
            "sport_type": "swimming",
            "sub_sport_type": "open_water",
            "start_time": "2026-07-20T08:00:00Z",
            "distance_m": 10000,
            "distance": None,
            "dist_km": None,
            "duration_sec": 14400,
            "points_json": _open_water_stream(),
            "distance_source": "device",
            "is_mock": 0,
        }
        activity.update(overrides)
        self.conn.execute(
            """
            INSERT INTO activities (
                id, sport_type, sub_sport_type, start_time, distance_m, distance,
                dist_km, duration_sec, points_json, distance_source, is_mock
            )
            VALUES (
                :id, :sport_type, :sub_sport_type, :start_time, :distance_m,
                :distance, :dist_km, :duration_sec, :points_json,
                :distance_source, :is_mock
            )
            """,
            activity,
        )

    def test_open_water_10k_materializes_and_returns_current_best(self):
        self._insert_activity("open-10k")
        row = self.conn.execute("SELECT * FROM activities WHERE id = 'open-10k'").fetchone()

        plan = career_backend.compute_record_metric_results_for_activity(
            row,
            record_keys=["open_water_swim_10k"],
            conn=self.conn,
        )
        self.assertEqual(plan["summary"]["would_upsert"], ["open_water_swim_10k"])
        career_backend.upsert_career_record_metric_results(
            self.conn, plan, dry_run=False
        )
        series = career_backend.get_career_record_metric_series(
            "open_water_swim_10k",
            {"sport": "open_water_swimming"},
            conn=self.conn,
        )

        self.assertEqual(series["status"]["state"], "ready")
        self.assertEqual(series["metrics"]["source"], "materialized")
        self.assertEqual(series["current_best"]["activity_id"], "open-10k")
        self.assertEqual(series["current_best"]["metric"]["value"], 14400.0)

    def test_legacy_distance_in_km_is_normalized_before_open_water_matching(self):
        self._insert_activity(
            "legacy-km-10k",
            distance_m=None,
            distance=10.0,
            points_json=_open_water_stream(),
        )
        row = self.conn.execute(
            "SELECT * FROM activities WHERE id = 'legacy-km-10k'"
        ).fetchone()

        facts = career_backend.build_activity_record_facts(dict(row))
        plan = career_backend.compute_record_metric_results_for_activity(
            row,
            record_keys=["open_water_swim_10k"],
            conn=self.conn,
        )

        self.assertEqual(facts["distance_m"], 10000.0)
        self.assertEqual(plan["summary"]["would_upsert"], ["open_water_swim_10k"])

    def test_manual_or_estimated_distance_is_materialized_as_ineligible_validation(self):
        self._insert_activity("manual-10k", distance_source="manual")
        row = self.conn.execute(
            "SELECT * FROM activities WHERE id = 'manual-10k'"
        ).fetchone()

        plan = career_backend.compute_record_metric_results_for_activity(
            row,
            record_keys=["open_water_swim_10k"],
            conn=self.conn,
        )
        result = plan["results"][0]

        self.assertEqual(result["status"], "validation_required")
        self.assertFalse(
            json.loads(result["eligibility_json"])["current_best"]
        )
        self.assertIn("open_water_gps_unreliable", result["quality_json"])

    def test_open_water_standard_key_is_supported_even_without_samples(self):
        series = career_backend.get_career_record_metric_series(
            "open_water_swim_10k",
            {"sport": "open_water_swimming"},
            conn=self.conn,
        )

        self.assertEqual(series["status"]["state"], "sample_missing")

    def test_open_water_standard_catalog_is_available(self):
        catalog = career_backend.get_career_record_catalog(
            {"sport": "open_water_swimming"}
        )
        records = [
            record
            for group in catalog["sports"][0]["groups"]
            for record in group["records"]
        ]
        standard = next(
            record
            for record in records
            if record["record_key"] == "open_water_swim_10k"
        )

        self.assertEqual(standard["availability_state"], "available")

    def test_open_water_aggregate_metric_results_remain_available(self):
        self._insert_activity("open-aggregate")
        row = self.conn.execute(
            "SELECT * FROM activities WHERE id = 'open-aggregate'"
        ).fetchone()

        plan = career_backend.compute_record_metric_results_for_activity(
            row,
            record_keys=[
                "open_water_swim_10k",
                "open_water_longest_distance",
                "open_water_longest_elapsed_time",
            ],
            conn=self.conn,
        )

        self.assertEqual(
            plan["summary"]["would_upsert"],
            [
                "open_water_longest_distance",
                "open_water_longest_elapsed_time",
                "open_water_swim_10k",
            ],
        )


if __name__ == "__main__":
    unittest.main()
