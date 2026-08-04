import json
import sqlite3
import unittest
from unittest import mock

import career_backend
import main
import profile_backend


def _distance_points(items):
    return json.dumps([{"distance_m": distance, "t_sec": elapsed} for distance, elapsed in items])


def _create_activity_schema(conn):
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
            points_json TEXT,
            track_json TEXT,
            power_points TEXT,
            laps_json TEXT,
            lengths_json TEXT,
            pool_length_m REAL,
            pool_length REAL,
            advanced_metrics TEXT,
            strength_sets_json TEXT,
            strength_summary_json TEXT,
            muscle_heatmap_json TEXT,
            strength_materialization_version INTEGER DEFAULT 0,
            strength_materialization_status TEXT,
            region_status TEXT,
            region_admin1 TEXT,
            region_admin1_code TEXT,
            start_lat REAL,
            start_lon REAL,
            list_metric_backfill_version INTEGER DEFAULT 0,
            deleted_at TEXT,
            is_mock INTEGER,
            file_path TEXT
        )
        """
    )
    career_backend.ensure_career_schema(conn)


def _insert_cycling(conn, activity_id, date, distance_km):
    distance_m = distance_km * 1000
    duration = 7200
    steps = max(4, int(distance_km // 5))
    points = [
        (round(distance_m * index / steps, 3), round(duration * index / steps, 3))
        for index in range(steps + 1)
    ]
    conn.execute(
        """
        INSERT INTO activities (
            id, sport_type, start_time, dist_km, distance, duration_sec,
            gain_m, points_json, track_json, advanced_metrics, is_mock
        )
        VALUES (?, 'cycling', ?, ?, ?, ?, 600, ?, ?, ?, 0)
        """,
        (
            activity_id,
            f"{date}T08:00:00Z",
            distance_km,
            distance_m,
            duration,
            _distance_points(points),
            _distance_points(points),
            json.dumps({"metrics_version": 1, "vam": 100}),
        ),
    )


class V204DerivedMetricsUpgradeTest(unittest.TestCase):
    def setUp(self):
        career_backend._clear_record_metric_series_cache()

    def test_audit_uses_column_introspection_for_old_activity_schema(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(
                """
                CREATE TABLE activities (
                    id TEXT PRIMARY KEY,
                    sport_type TEXT,
                    start_time TEXT,
                    track_json TEXT,
                    points_json TEXT,
                    advanced_metrics TEXT,
                    deleted_at TEXT
                )
                """
            )
            career_backend.ensure_career_schema(conn)

            audit = main.audit_derived_metrics_upgrade_dependencies(conn)

            self.assertTrue(audit["ok"])
            self.assertTrue(audit["schema_compatibility"]["uses_column_introspection"])
            self.assertIn("sport_type", audit["schema_compatibility"]["activity_columns_checked"])
            self.assertNotIn("sport", audit["schema_compatibility"]["activity_columns_checked"])
            self.assertEqual(audit["strength_materialization"]["classification"], "on_demand_backend_repair")
        finally:
            conn.close()

    def test_upgrade_rebuilds_half_materialized_cycling_and_marks_done(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            _create_activity_schema(conn)
            _insert_cycling(conn, "ride-52k", "2026-06-01", 52.0)
            _insert_cycling(conn, "ride-short-1", "2026-07-01", 5.24)
            _insert_cycling(conn, "ride-short-2", "2026-07-02", 4.8)
            career_backend.rebuild_career_record_metric_results(
                conn,
                sport="cycling",
                record_keys=["cycling_longest_distance"],
                dry_run=False,
            )
            conn.execute(
                """
                UPDATE career_record_metric_results
                SET status = 'invalidated'
                WHERE activity_id = 'ride-52k'
                  AND record_key = 'cycling_longest_distance'
                """
            )
            career_backend._clear_record_metric_series_cache()

            with mock.patch.object(
                main,
                "_compute_advanced_metrics",
                return_value={"metrics_version": main.CURRENT_METRICS_VERSION, "vam": 120},
            ):
                result = main.run_derived_metrics_upgrade(conn, force=True, run_strength_audit=False)

            self.assertTrue(result["ok"], result)
            self.assertTrue(result["status"]["migration_done"])
            self.assertTrue(profile_backend.app_migration_done(conn, main.DERIVED_METRICS_UPGRADE_KEY))
            series = career_backend.get_career_record_metric_series(
                "cycling_longest_distance",
                {"sport": "cycling"},
                conn=conn,
            )
            fastest_20k = career_backend.get_career_record_metric_series(
                "cycling_fastest_20k",
                {"sport": "cycling"},
                conn=conn,
            )
            self.assertEqual(series["metrics"]["source"], "materialized")
            self.assertEqual(series["current_best"]["activity_id"], "ride-52k")
            self.assertEqual(fastest_20k["metrics"]["source"], "materialized")
            self.assertEqual(fastest_20k["current_best"]["activity_id"], "ride-52k")
            row = conn.execute(
                "SELECT advanced_metrics FROM activities WHERE id = 'ride-52k'"
            ).fetchone()
            self.assertEqual(json.loads(row["advanced_metrics"])["metrics_version"], main.CURRENT_METRICS_VERSION)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
