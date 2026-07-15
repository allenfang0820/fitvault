import sqlite3
import unittest

import career_backend


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY,
            start_time TEXT,
            start_time_utc TEXT,
            sport_type TEXT,
            dist_km REAL,
            duration INTEGER,
            region_city TEXT,
            deleted_at TEXT
        )
        """
    )
    career_backend.ensure_career_schema(conn)


def _insert_activity(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": 1,
        "start_time": "2026-07-11T07:00:00+08:00",
        "start_time_utc": "",
        "sport_type": "running",
        "dist_km": 10.0,
        "duration": 3600,
        "region_city": "北京",
        "deleted_at": None,
    }
    data.update(overrides)
    columns = list(data)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO activities ({', '.join(columns)}) VALUES ({placeholders})",
        [data[column] for column in columns],
    )


def _insert_race(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": "race:1",
        "activity_id": "1",
        "name": "测试赛事",
        "event_type": "race",
        "sport": "running",
        "event_date": "2026-07-11",
        "location_json": "{}",
        "performance_summary_json": "{}",
        "achievement_ids_json": "[]",
        "confidence": 1.0,
        "source": "resolver",
        "status": "active",
        "display_metadata_json": "{}",
    }
    data.update(overrides)
    columns = list(data)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO career_race_events ({', '.join(columns)}) VALUES ({placeholders})",
        [data[column] for column in columns],
    )


def _insert_pb(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": "pb:1",
        "activity_id": "1",
        "sport": "running",
        "pb_type": "running_5k",
        "value": "1200",
        "value_unit": "seconds",
        "improvement": None,
        "event_date": "2026-07-11",
        "confidence": 1.0,
        "source": "resolver",
        "status": "active",
        "display_metadata_json": "{}",
    }
    data.update(overrides)
    columns = list(data)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO career_pb_records ({', '.join(columns)}) VALUES ({placeholders})",
        [data[column] for column in columns],
    )


class TestCareerYearSnapshotPeriodComparison(unittest.TestCase):
    def test_current_year_uses_data_through_not_view_date_for_same_range_comparison(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_tables(conn)
            _insert_activity(conn, id=1, start_time="2026-07-11T07:00:00+08:00", dist_km=10.0, duration=3600)
            _insert_activity(conn, id=2, start_time="2025-07-11T07:00:00+08:00", dist_km=6.0, duration=2000)
            _insert_activity(conn, id=3, start_time="2025-07-12T07:00:00+08:00", dist_km=999.0, duration=999)
            _insert_race(conn, id="race:2026", activity_id="1", event_date="2026-07-11")
            _insert_pb(conn, id="pb:2026", activity_id="1", event_date="2026-07-11")
            _insert_race(conn, id="race:2025", activity_id="2", event_date="2025-07-11")

            snapshot = career_backend.build_career_year_snapshot(2026, conn=conn, as_of_date="2026-07-14")

            self.assertTrue(snapshot["period"]["is_partial_year"])
            self.assertEqual(snapshot["period"]["data_through"], "2026-07-11")
            self.assertEqual(snapshot["comparison"]["status"], "available")
            self.assertEqual(snapshot["comparison"]["period_mode"], "same_date_range")
            self.assertEqual(snapshot["comparison"]["activity_count_delta"], 0)
            self.assertEqual(snapshot["comparison"]["distance_km_delta"], 4.0)
            self.assertEqual(snapshot["comparison"]["duration_seconds_delta"], 1600)
            self.assertEqual(snapshot["comparison"]["race_count_delta"], 0)
            self.assertEqual(snapshot["comparison"]["pb_count_delta"], 1)
        finally:
            conn.close()

    def test_historical_year_uses_full_year_comparison(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_tables(conn)
            _insert_activity(conn, id=1, start_time="2025-12-31T07:00:00+08:00", dist_km=10.0, duration=3600)
            _insert_activity(conn, id=2, start_time="2024-12-31T07:00:00+08:00", dist_km=8.0, duration=3000)

            snapshot = career_backend.build_career_year_snapshot(2025, conn=conn, as_of_date="2026-07-14")

            self.assertFalse(snapshot["period"]["is_partial_year"])
            self.assertEqual(snapshot["comparison"]["status"], "available")
            self.assertEqual(snapshot["comparison"]["period_mode"], "full_year")
            self.assertEqual(snapshot["comparison"]["distance_km_delta"], 2.0)
        finally:
            conn.close()

    def test_previous_year_without_data_returns_unavailable_reason_and_null_deltas(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_tables(conn)
            _insert_activity(conn, id=1, start_time="2026-01-02T07:00:00+08:00", dist_km=10.0, duration=3600)

            snapshot = career_backend.build_career_year_snapshot(2026, conn=conn, as_of_date="2026-01-03")

            self.assertEqual(snapshot["comparison"]["status"], "unavailable")
            self.assertEqual(snapshot["comparison"]["reason"], "previous_year_no_data")
            self.assertIsNone(snapshot["comparison"]["activity_count_delta"])
            self.assertIn("comparison_unavailable:previous_year_no_data", snapshot["data_quality"]["warnings"])
        finally:
            conn.close()

    def test_no_current_data_returns_no_data_quality_and_no_current_reason(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_tables(conn)

            snapshot = career_backend.build_career_year_snapshot(2026, conn=conn, as_of_date="2026-07-14")

            self.assertEqual(snapshot["comparison"]["status"], "unavailable")
            self.assertEqual(snapshot["comparison"]["reason"], "no_current_year_data")
            self.assertEqual(snapshot["data_quality"], {"status": "no_data", "warnings": ["no_activity_data"]})
        finally:
            conn.close()

    def test_leap_day_comparison_caps_to_feb_28_when_previous_year_is_not_leap(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_tables(conn)
            _insert_activity(conn, id=1, start_time="2024-02-29T07:00:00+08:00", dist_km=10.0, duration=3600)
            _insert_activity(conn, id=2, start_time="2023-02-28T07:00:00+08:00", dist_km=8.0, duration=3000)
            _insert_activity(conn, id=3, start_time="2023-03-01T07:00:00+08:00", dist_km=999.0, duration=999)

            snapshot = career_backend.build_career_year_snapshot(2024, conn=conn, as_of_date="2024-03-01")

            self.assertEqual(snapshot["comparison"]["status"], "available")
            self.assertEqual(snapshot["comparison"]["period_mode"], "same_date_range")
            self.assertEqual(snapshot["comparison"]["distance_km_delta"], 2.0)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
