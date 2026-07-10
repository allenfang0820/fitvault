import sqlite3
import unittest

import career_backend


def _create_activity_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY,
            title TEXT,
            title_source TEXT,
            sport_type TEXT,
            sub_sport_type TEXT,
            start_time TEXT,
            start_time_utc TEXT,
            dist_km REAL,
            distance REAL,
            duration INTEGER,
            duration_sec INTEGER,
            avg_pace REAL,
            total_ascent REAL,
            ascent REAL,
            elev_gain REAL,
            gain_m REAL,
            region_city TEXT,
            region TEXT,
            region_display TEXT,
            is_race INTEGER DEFAULT 0,
            race_source TEXT,
            race_confidence TEXT,
            race_override INTEGER DEFAULT 0,
            race_confirmed_at TEXT,
            deleted_at TEXT,
            updated_at TEXT
        )
        """
    )


def _insert_activity(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": 1,
        "title": "日常训练",
        "title_source": "sport_name",
        "sport_type": "running",
        "sub_sport_type": "generic",
        "start_time": "2026-05-19T08:00:00+08:00",
        "start_time_utc": "2026-05-19T00:00:00Z",
        "dist_km": 10.0,
        "distance": None,
        "duration": 3200,
        "duration_sec": 3200,
        "avg_pace": 320.0,
        "total_ascent": None,
        "ascent": None,
        "elev_gain": None,
        "gain_m": 120.0,
        "region_city": "成都",
        "region": "四川成都",
        "region_display": "成都",
        "is_race": 0,
        "race_source": None,
        "race_confidence": None,
        "race_override": 0,
        "race_confirmed_at": None,
        "deleted_at": None,
        "updated_at": "2026-05-19T08:00:00+08:00",
    }
    data.update(overrides)
    columns = list(data)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO activities ({', '.join(columns)}) VALUES ({placeholders})",
        [data[column] for column in columns],
    )


class TestCareerRefreshPipeline(unittest.TestCase):
    def test_refresh_uses_all_activities_for_career_basics_but_only_race_labels_for_races(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(conn, id=1, title="日常训练")

            result = career_backend.refresh_career_derived_events(conn)

            self.assertTrue(result["ok"])
            overview = career_backend.get_career_overview(conn)
            self.assertEqual(overview["summary"]["activity_count"], 1)
            self.assertEqual(overview["summary"]["total_distance_km"], 10.0)
            self.assertEqual(overview["summary"]["race_count"], 0)
            self.assertGreaterEqual(overview["summary"]["pb_count"], 1)
            self.assertGreaterEqual(overview["summary"]["achievement_count"], 1)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM career_race_events WHERE status = 'active'").fetchone()[0],
                0,
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM career_event_candidates WHERE status = 'candidate'").fetchone()[0],
                1,
            )
        finally:
            conn.close()

    def test_refresh_promotes_confirmed_race_label_to_race_archive(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(
                conn,
                id=2,
                title="2026 成都马拉松",
                dist_km=42.195,
                duration=15000,
                duration_sec=15000,
                is_race=1,
                race_source="user",
                race_confidence="high",
                race_override=1,
            )

            career_backend.refresh_career_derived_events(conn)

            overview = career_backend.get_career_overview(conn)
            self.assertEqual(overview["summary"]["activity_count"], 1)
            self.assertEqual(overview["summary"]["race_count"], 1)
            race = conn.execute(
                "SELECT activity_id, name, source, status FROM career_race_events WHERE id = 'race:2'"
            ).fetchone()
            self.assertEqual(race, ("2", "2026 成都马拉松", "user", "active"))
        finally:
            conn.close()

    def test_refresh_is_idempotent(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(conn, id=3, title="日常训练")

            career_backend.refresh_career_derived_events(conn)
            first_counts = {
                table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("career_race_events", "career_pb_records", "career_achievement_events")
            }
            career_backend.refresh_career_derived_events(conn)
            second_counts = {
                table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("career_race_events", "career_pb_records", "career_achievement_events")
            }

            self.assertEqual(second_counts, first_counts)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
