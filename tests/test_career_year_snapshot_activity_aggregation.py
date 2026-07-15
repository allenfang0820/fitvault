import sqlite3
import unittest

import career_backend


def _create_activities_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY,
            title TEXT,
            start_time TEXT,
            start_time_utc TEXT,
            sport_type TEXT,
            sub_sport_type TEXT,
            sport TEXT,
            activity_type TEXT,
            dist_km REAL,
            distance REAL,
            duration INTEGER,
            duration_sec INTEGER,
            region_city TEXT,
            city TEXT,
            cityName TEXT,
            deleted_at TEXT,
            points_json TEXT,
            track_json TEXT,
            file_path TEXT
        )
        """
    )


def _insert_activity(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": 1,
        "title": "Should not enter snapshot",
        "start_time": "2026-01-02T07:00:00+08:00",
        "start_time_utc": "",
        "sport_type": "running",
        "sub_sport_type": "",
        "sport": "",
        "activity_type": "",
        "dist_km": 10.04,
        "distance": None,
        "duration": 3600,
        "duration_sec": None,
        "region_city": "北京",
        "city": "",
        "cityName": "",
        "deleted_at": None,
        "points_json": "[forbidden]",
        "track_json": "[forbidden]",
        "file_path": "/Users/example/private.fit",
    }
    data.update(overrides)
    columns = list(data)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO activities ({', '.join(columns)}) VALUES ({placeholders})",
        [data[column] for column in columns],
    )


class TestCareerYearSnapshotActivityAggregation(unittest.TestCase):
    def test_single_sport_year_aggregates_summary_breakdown_and_months(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activities_table(conn)
            _insert_activity(conn, id=1, dist_km=10.04, duration=3600, region_city="北京")
            _insert_activity(conn, id=2, start_time="2026-01-20T07:00:00+08:00", dist_km=5.05, duration=1800, region_city="上海")

            snapshot = career_backend.build_career_year_snapshot(2026, conn=conn, as_of_date="2026-07-13")

            self.assertEqual(snapshot["summary"]["activity_count"], 2)
            self.assertEqual(snapshot["summary"]["total_distance_km"], 15.1)
            self.assertEqual(snapshot["summary"]["total_duration_seconds"], 5400)
            self.assertEqual(snapshot["summary"]["covered_city_count"], 2)
            self.assertEqual([item["city"] for item in snapshot["city_moments"]], ["北京", "上海"])
            self.assertEqual(snapshot["city_moments"][0]["activity_count"], 1)
            self.assertEqual(snapshot["highlight_moments"][0]["type"], "longest_distance")
            self.assertEqual(snapshot["highlight_moments"][0]["activity_id"], "1")
            self.assertEqual(snapshot["sport_breakdown"], [
                {
                    "sport": "running",
                    "sport_label": "跑步",
                    "activity_count": 2,
                    "distance_km": 15.1,
                    "duration_seconds": 5400,
                }
            ])
            self.assertEqual(snapshot["month_digest"][0]["activity_count"], 2)
            self.assertEqual(snapshot["month_digest"][0]["distance_km"], 15.1)
            self.assertEqual(snapshot["month_digest"][0]["primary_sport"], "running")
            self.assertEqual(snapshot["month_digest"][1]["activity_count"], 0)
            self.assertEqual(snapshot["period"]["data_through"], "2026-01-20")
            self.assertEqual(snapshot["data_quality"]["status"], "limited")
            self.assertIn("partial_year", snapshot["data_quality"]["warnings"])
            self.assertTrue(career_backend.validate_career_year_snapshot_contract(snapshot))
        finally:
            conn.close()

    def test_multi_sport_year_outputs_stable_sport_and_month_sorting(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activities_table(conn)
            _insert_activity(conn, id=1, start_time="2026-03-01T07:00:00+08:00", sport_type="cycling", dist_km=40.0, duration=7200, region_city="北京")
            _insert_activity(conn, id=2, start_time="2026-03-02T07:00:00+08:00", sport_type="running", dist_km=8.0, duration=2400, region_city="北京")
            _insert_activity(conn, id=3, start_time="2026-03-03T07:00:00+08:00", sport_type="running", dist_km=6.0, duration=1800, region_city="北京")

            snapshot = career_backend.build_career_year_snapshot(2026, conn=conn, as_of_date="2026-07-13")

            self.assertEqual([item["sport"] for item in snapshot["sport_breakdown"]], ["cycling", "running"])
            self.assertEqual(snapshot["sport_breakdown"][0]["distance_km"], 40.0)
            self.assertEqual(snapshot["sport_breakdown"][1]["activity_count"], 2)
            self.assertEqual(snapshot["month_digest"][2]["primary_sport"], "running")
            self.assertEqual([item["month"] for item in snapshot["month_digest"]], list(range(1, 13)))
        finally:
            conn.close()

    def test_deleted_cross_year_and_invalid_date_activities_are_excluded(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activities_table(conn)
            _insert_activity(conn, id=1, start_time="2025-12-31T23:30:00+08:00", dist_km=99.0)
            _insert_activity(conn, id=2, start_time="2026-01-01T00:10:00+08:00", dist_km=10.0)
            _insert_activity(conn, id=3, start_time="2026-06-01T08:00:00+08:00", dist_km=20.0, deleted_at="2026-06-02")
            _insert_activity(conn, id=4, start_time="", start_time_utc="", dist_km=30.0)

            snapshot = career_backend.build_career_year_snapshot(2026, conn=conn, as_of_date="2026-07-13")

            self.assertEqual(snapshot["summary"]["activity_count"], 1)
            self.assertEqual(snapshot["summary"]["total_distance_km"], 10.0)
            self.assertEqual(snapshot["month_digest"][0]["activity_count"], 1)
            self.assertEqual(snapshot["month_digest"][5]["activity_count"], 0)
        finally:
            conn.close()

    def test_distance_and_duration_use_canonical_activity_columns_without_points(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activities_table(conn)
            _insert_activity(conn, id=1, dist_km=None, distance=12345.0, duration=None, duration_sec=3661)

            snapshot = career_backend.build_career_year_snapshot(2026, conn=conn, as_of_date="2026-07-13")

            self.assertEqual(snapshot["summary"]["total_distance_km"], 12.3)
            self.assertEqual(snapshot["summary"]["total_duration_seconds"], 3661)
            self.assertIn("longest_distance", {item["type"] for item in snapshot["highlight_moments"]})
            serialized = repr(snapshot)
            self.assertNotIn("points_json", serialized)
            self.assertNotIn("track_json", serialized)
            self.assertNotIn("/Users/example", serialized)
        finally:
            conn.close()

    def test_available_years_use_valid_non_deleted_activities_descending(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activities_table(conn)
            _insert_activity(conn, id=1, start_time="2024-05-01T07:00:00+08:00")
            _insert_activity(conn, id=2, start_time="2026-05-01T07:00:00+08:00")
            _insert_activity(conn, id=3, start_time="2026-06-01T07:00:00+08:00")
            _insert_activity(conn, id=4, start_time="2025-06-01T07:00:00+08:00", deleted_at="2025-06-02")
            _insert_activity(conn, id=5, start_time="", start_time_utc="")

            self.assertEqual(career_backend.get_career_year_snapshot_available_years(conn=conn), [2026, 2024])
        finally:
            conn.close()

    def test_preloaded_activity_rows_preserve_snapshot_and_fingerprint(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activities_table(conn)
            _insert_activity(conn, id=1, start_time="2026-05-01T07:00:00+08:00", dist_km=10.0)
            _insert_activity(conn, id=2, start_time="2025-05-01T07:00:00+08:00", dist_km=8.0)

            baseline = career_backend.build_career_year_snapshot(
                2026,
                conn=conn,
                as_of_date="2026-07-14",
            )
            preloaded_rows = career_backend._overview_activity_rows(conn)
            optimized = career_backend.build_career_year_snapshot(
                2026,
                conn=conn,
                as_of_date="2026-07-14",
                activity_rows=preloaded_rows,
            )

            self.assertEqual(optimized, baseline)
            self.assertEqual(optimized["source_fingerprint"], baseline["source_fingerprint"])
        finally:
            conn.close()

    def test_overview_activity_read_loads_activity_columns_once(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activities_table(conn)
            _insert_activity(conn, id=1)
            statements: list[str] = []
            conn.set_trace_callback(statements.append)

            rows = career_backend._overview_activity_rows(conn)

            activity_table_info = [
                statement
                for statement in statements
                if statement.strip().lower().startswith("pragma table_info(activities)")
            ]
            self.assertEqual(len(rows), 1)
            self.assertEqual(len(activity_table_info), 1)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
