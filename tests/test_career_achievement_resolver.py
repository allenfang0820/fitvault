import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import career_backend
import profile_backend


FORBIDDEN_FIELDS = {
    "points",
    "points_json",
    "track_json",
    "raw_records",
    "fit_records",
    "file_path",
    "advanced_metrics",
    "shadow_diff_json",
}


def _create_activity_table(conn: sqlite3.Connection, include_forbidden: bool = False) -> None:
    forbidden_sql = ""
    if include_forbidden:
        forbidden_sql = """
            points_json TEXT,
            track_json TEXT,
            raw_records TEXT,
            fit_records TEXT,
            file_path TEXT,
            advanced_metrics TEXT,
            shadow_diff_json TEXT,
        """
    conn.execute(
        f"""
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY,
            sport_type TEXT,
            sub_sport_type TEXT,
            start_time TEXT,
            start_time_utc TEXT,
            dist_km REAL,
            distance REAL,
            total_ascent REAL,
            ascent REAL,
            elev_gain REAL,
            gain_m REAL,
            region_city TEXT,
            region TEXT,
            region_display TEXT,
            deleted_at TEXT,
            {forbidden_sql}
            updated_at TEXT
        )
        """
    )


def _insert_activity(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": 1,
        "sport_type": "running",
        "sub_sport_type": "generic",
        "start_time": "2026-05-19T08:00:00+08:00",
        "start_time_utc": "2026-05-19T00:00:00Z",
        "dist_km": 5.0,
        "distance": None,
        "total_ascent": None,
        "ascent": None,
        "elev_gain": None,
        "gain_m": None,
        "region_city": "",
        "region": "",
        "region_display": "",
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


def _achievement_rows(conn: sqlite3.Connection):
    return conn.execute(
        """
        SELECT id, activity_id, achievement_type, title, event_date, score, icon,
               description, confidence, source, status, display_metadata_json
        FROM career_achievement_events
        ORDER BY achievement_type, status, event_date, id
        """
    ).fetchall()


class TestCareerAchievementResolver(unittest.TestCase):
    def test_running_first_distance_achievements_are_active(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(conn, id=1, dist_km=5.0, start_time="2026-01-01T08:00:00")
            _insert_activity(conn, id=2, dist_km=10.0, start_time="2026-02-01T08:00:00")
            _insert_activity(conn, id=3, dist_km=21.1, start_time="2026-03-01T08:00:00")
            _insert_activity(conn, id=4, dist_km=42.2, start_time="2026-04-01T08:00:00")

            result = career_backend.resolve_achievement_events(conn)

            self.assertTrue(result["ok"])
            active_types = {
                row[2]
                for row in _achievement_rows(conn)
                if row[10] == "active" and str(row[2]).startswith("first_running_")
            }
            self.assertEqual(
                active_types,
                {
                    "first_running_5k",
                    "first_running_10k",
                    "first_running_half_marathon",
                    "first_running_marathon",
                },
            )
            titles = {row[3] for row in _achievement_rows(conn)}
            self.assertIn("首次跑完 5K", titles)
            self.assertIn("首次完成全马", titles)
        finally:
            conn.close()

    def test_cycling_first_distance_achievements_are_active(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(conn, id=1, sport_type="cycling", dist_km=50.0, start_time="2026-01-01T08:00:00")
            _insert_activity(conn, id=2, sport_type="cycling", dist_km=100.0, start_time="2026-02-01T08:00:00")

            career_backend.resolve_achievement_events(conn)

            active_types = {
                row[2]
                for row in _achievement_rows(conn)
                if row[10] == "active" and str(row[2]).startswith("first_cycling_")
            }
            self.assertEqual(active_types, {"first_cycling_50k", "first_cycling_100k"})
        finally:
            conn.close()

    def test_record_achievements_keep_only_current_max_active(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(conn, id=1, sport_type="running", dist_km=8.0, total_ascent=100, start_time="2026-01-01T08:00:00")
            _insert_activity(conn, id=2, sport_type="running", dist_km=12.0, total_ascent=200, start_time="2026-02-01T08:00:00")
            _insert_activity(conn, id=3, sport_type="cycling", dist_km=60.0, total_ascent=300, start_time="2026-03-01T08:00:00")
            _insert_activity(conn, id=4, sport_type="cycling", dist_km=110.0, total_ascent=250, start_time="2026-04-01T08:00:00")
            _insert_activity(conn, id=5, sport_type="walking", dist_km=3.0, total_ascent=800, start_time="2026-05-01T08:00:00")

            career_backend.resolve_achievement_events(conn)

            active = {
                row[2]: row
                for row in _achievement_rows(conn)
                if row[10] == "active" and row[2] in {"longest_running", "longest_cycling", "max_ascent"}
            }
            self.assertEqual(active["longest_running"][1], "2")
            self.assertEqual(active["longest_cycling"][1], "4")
            self.assertEqual(active["max_ascent"][1], "5")
            metadata = json.loads(active["max_ascent"][11])
            self.assertEqual(metadata["ascent_m"], 800.0)
        finally:
            conn.close()

    def test_new_record_supersedes_old_active_record(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(conn, id=1, sport_type="running", dist_km=12.0, start_time="2026-01-01T08:00:00")
            career_backend.resolve_achievement_events(conn)

            _insert_activity(conn, id=2, sport_type="running", dist_km=15.0, start_time="2026-02-01T08:00:00")
            career_backend.resolve_achievement_events(conn)

            rows = conn.execute(
                """
                SELECT activity_id, status, display_metadata_json
                FROM career_achievement_events
                WHERE achievement_type = 'longest_running'
                ORDER BY activity_id
                """
            ).fetchall()
            by_activity = {row[0]: row for row in rows}
            self.assertEqual(by_activity["1"][1], "superseded")
            self.assertEqual(by_activity["2"][1], "active")
            metadata = json.loads(by_activity["2"][2])
            self.assertEqual(metadata["previous_activity_id"], "1")
            self.assertEqual(metadata["previous_value"], 12.0)
        finally:
            conn.close()

    def test_first_city_writes_one_active_achievement_per_first_city(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(conn, id=1, region_city="北京", start_time="2026-01-01T08:00:00")
            _insert_activity(conn, id=2, region_city="北京", start_time="2026-02-01T08:00:00")
            _insert_activity(conn, id=3, region_city="上海", start_time="2026-03-01T08:00:00")
            _insert_activity(conn, id=4, region_city="", region_display="", region="", start_time="2026-04-01T08:00:00")

            career_backend.resolve_achievement_events(conn)

            rows = [
                row for row in _achievement_rows(conn)
                if row[2] == "first_city" and row[10] == "active"
            ]
            self.assertEqual(len(rows), 2)
            by_city = {json.loads(row[11])["city"]: row for row in rows}
            self.assertEqual(by_city["北京"][1], "1")
            self.assertEqual(by_city["上海"][1], "3")
            self.assertTrue(all(row[3] == "首次点亮城市" for row in rows))
        finally:
            conn.close()

    def test_annual_milestone_is_created_from_safe_year_summary(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            for index in range(50):
                _insert_activity(
                    conn,
                    id=index + 1,
                    sport_type="walking",
                    dist_km=4.0,
                    start_time=f"2026-03-{(index % 28) + 1:02d}T08:00:00",
                    start_time_utc=f"2026-03-{(index % 28) + 1:02d}T00:00:00Z",
                )

            career_backend.resolve_achievement_events(conn)

            rows = [
                row for row in _achievement_rows(conn)
                if row[2] == "annual_milestone" and row[10] == "active"
            ]
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row[3], "2026 年度运动里程碑")
            metadata = json.loads(row[11])
            self.assertEqual(metadata["year"], 2026)
            self.assertEqual(metadata["activity_count"], 50)
            self.assertEqual(metadata["total_distance_km"], 200.0)
            self.assertNotIn("points_json", metadata)
        finally:
            conn.close()

    def test_annual_milestones_do_not_supersede_other_years(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            activity_id = 1
            for year in (2025, 2026):
                for index in range(50):
                    _insert_activity(
                        conn,
                        id=activity_id,
                        sport_type="walking",
                        dist_km=2.0,
                        start_time=f"{year}-04-{(index % 28) + 1:02d}T08:00:00",
                        start_time_utc=f"{year}-04-{(index % 28) + 1:02d}T00:00:00Z",
                    )
                    activity_id += 1

            career_backend.resolve_achievement_events(conn)

            active_years = {
                json.loads(row[11])["year"]
                for row in _achievement_rows(conn)
                if row[2] == "annual_milestone" and row[10] == "active"
            }
            self.assertEqual(active_years, {2025, 2026})
        finally:
            conn.close()

    def test_v1_achievement_types_have_titles_and_categories(self):
        expected_types = {
            "first_running_5k",
            "first_running_10k",
            "first_running_half_marathon",
            "first_running_marathon",
            "first_cycling_50k",
            "first_cycling_100k",
            "longest_running",
            "longest_cycling",
            "max_ascent",
            "first_city",
            "annual_milestone",
        }

        for achievement_type in expected_types:
            self.assertNotEqual(career_backend._achievement_type_label(achievement_type), achievement_type)
            self.assertIn(
                career_backend._achievement_category(achievement_type),
                {"first_distance", "record", "location", "annual"},
            )

    def test_resolver_is_idempotent(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(conn, id=1, sport_type="running", dist_km=5.0, region_city="北京")

            career_backend.resolve_achievement_events(conn)
            first_count = conn.execute("SELECT COUNT(*) FROM career_achievement_events").fetchone()[0]
            career_backend.resolve_achievement_events(conn)
            second_count = conn.execute("SELECT COUNT(*) FROM career_achievement_events").fetchone()[0]
            active_count = conn.execute(
                "SELECT COUNT(*) FROM career_achievement_events WHERE status = 'active'"
            ).fetchone()[0]

            self.assertEqual(first_count, second_count)
            self.assertEqual(active_count, second_count)
        finally:
            conn.close()

    def test_deleted_activity_is_skipped(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(conn, id=1, sport_type="running", dist_km=5.0, deleted_at="2026-01-02")

            result = career_backend.resolve_achievement_events(conn)

            self.assertEqual(result["processed"], 0)
            self.assertEqual(_achievement_rows(conn), [])
        finally:
            conn.close()

    def test_resolver_does_not_select_or_store_forbidden_raw_fields(self):
        conn = sqlite3.connect(":memory:")
        try:
            captured_sql = []
            _create_activity_table(conn, include_forbidden=True)
            conn.execute(
                """
                INSERT INTO activities
                    (id, sport_type, start_time, dist_km, total_ascent, region_city,
                     points_json, track_json, raw_records, fit_records, file_path,
                     advanced_metrics, shadow_diff_json)
                VALUES
                    (1, 'running', '2026-05-19T08:00:00', 5.0, 100, '北京',
                     '[1]', '[2]', '{}', '{}', '/tmp/a.fit', '{}', '{}')
                """
            )
            conn.set_trace_callback(captured_sql.append)

            career_backend.resolve_achievement_events(conn)

            select_sql = "\n".join(sql for sql in captured_sql if sql.lstrip().upper().startswith("SELECT"))
            for field in FORBIDDEN_FIELDS:
                self.assertNotIn(field, select_sql)
            stored_json = "\n".join(
                str(row[0])
                for row in conn.execute("SELECT display_metadata_json FROM career_achievement_events")
            )
            for field in FORBIDDEN_FIELDS:
                self.assertNotIn(field, stored_json)
        finally:
            conn.close()

    def test_default_connection_uses_temp_profile_db_path(self):
        original_db_path = profile_backend.DB_PATH
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                profile_backend.DB_PATH = Path(tmpdir) / "career-achievements.sqlite"
                conn = sqlite3.connect(str(profile_backend.DB_PATH))
                try:
                    _create_activity_table(conn)
                    _insert_activity(conn, id=1, sport_type="running", dist_km=21.1, region_city="成都")
                    conn.commit()
                finally:
                    conn.close()

                result = career_backend.resolve_achievement_events()

                self.assertTrue(result["ok"])
                check = sqlite3.connect(str(profile_backend.DB_PATH))
                try:
                    achievement_count = check.execute(
                        "SELECT COUNT(*) FROM career_achievement_events WHERE status = 'active'"
                    ).fetchone()[0]
                    self.assertGreaterEqual(achievement_count, 1)
                finally:
                    check.close()
            finally:
                profile_backend.DB_PATH = original_db_path


if __name__ == "__main__":
    unittest.main()
