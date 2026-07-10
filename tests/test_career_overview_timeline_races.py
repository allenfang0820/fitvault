import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import career_backend
import profile_backend


FORBIDDEN_RESPONSE_KEYS = {
    "points",
    "points_json",
    "track_json",
    "raw_records",
    "fit_records",
    "file_path",
    "advanced_metrics",
    "shadow_diff_json",
    "sqlite_schema",
    "schema",
}


def _assert_forbidden_keys_absent(testcase, value):
    if isinstance(value, dict):
        for key, child in value.items():
            testcase.assertNotIn(str(key), FORBIDDEN_RESPONSE_KEYS)
            _assert_forbidden_keys_absent(testcase, child)
    elif isinstance(value, list):
        for child in value:
            _assert_forbidden_keys_absent(testcase, child)


def _insert_race(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": "race:1",
        "activity_id": "1",
        "name": "2026 成都半程马拉松",
        "event_type": "half_marathon",
        "sport": "running",
        "event_date": "2026-05-19",
        "location_json": json.dumps({"city": "成都"}, ensure_ascii=False),
        "performance_summary_json": "{}",
        "achievement_ids_json": "[]",
        "confidence": 1.0,
        "source": "user",
        "status": "active",
        "display_metadata_json": json.dumps({"confidence_level": "high"}, ensure_ascii=False),
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
        "id": "pb:running_5k:1",
        "activity_id": "1",
        "sport": "running",
        "pb_type": "running_5k",
        "value": "1500",
        "value_unit": "seconds",
        "improvement": None,
        "event_date": "2026-05-19",
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


class TestCareerOverviewTimelineRaces(unittest.TestCase):
    def test_overview_empty_state_latest_race_is_none(self):
        conn = sqlite3.connect(":memory:")
        try:
            result = career_backend.get_career_overview(conn)

            self.assertIsNone(result["latest_race"])
            self.assertEqual(result["summary"]["race_count"], 0)
            self.assertFalse(result["status"]["data_ready"])
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_overview_returns_latest_race_and_data_ready(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_race(conn, id="race:1", activity_id="1", name="2025 北京马拉松", event_date="2025-10-01")
            _insert_race(conn, id="race:2", activity_id="2", name="2026 成都半程马拉松", event_date="2026-05-19")

            result = career_backend.get_career_overview(conn)

            self.assertEqual(result["summary"]["race_count"], 2)
            self.assertTrue(result["status"]["data_ready"])
            self.assertEqual(result["latest_race"]["id"], "race:2")
            self.assertEqual(result["latest_race"]["detail_link"], {"activity_id": "2", "source": "career"})
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_timeline_empty_state_is_stable(self):
        conn = sqlite3.connect(":memory:")
        try:
            result = career_backend.get_career_timeline({"sport": "all", "year": "", "type": "all"}, conn)

            self.assertEqual(result["filters"], {"year": None, "type": "all"})
            self.assertEqual(result["available_years"], [])
            self.assertEqual(result["years"], [])
            self.assertFalse(result["status"]["data_ready"])
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_timeline_groups_race_nodes_by_year_and_month(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_race(conn, id="race:1", activity_id="1", name="2025 北京马拉松", event_date="2025-10-01")
            _insert_race(conn, id="race:2", activity_id="2", name="2026 成都半程马拉松", event_date="2026-05-19")
            _insert_race(conn, id="race:3", activity_id="3", name="2026 上海10K比赛", event_type="10k", event_date="2026-05-28")

            result = career_backend.get_career_timeline({"type": "race"}, conn)

            self.assertTrue(result["status"]["data_ready"])
            self.assertEqual(result["available_years"], [2026, 2025])
            self.assertEqual([year["year"] for year in result["years"]], [2026, 2025])
            self.assertNotIn("season", result["years"][0])
            self.assertEqual(result["years"][0]["months"][0]["month"], 5)
            self.assertEqual(result["years"][0]["months"][0]["year"], 2026)
            self.assertEqual(result["years"][0]["months"][0]["days_in_month"], 31)
            nodes = result["years"][0]["months"][0]["nodes"]
            self.assertEqual([node["id"] for node in nodes], ["race:3", "race:2"])
            self.assertEqual(nodes[0]["type"], "race")
            self.assertEqual(nodes[0]["track"], "race")
            self.assertEqual(nodes[0]["day"], 28)
            self.assertEqual(nodes[0]["detail_link"], {"activity_id": "3", "source": "career"})
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_timeline_sport_filter_is_ignored_in_06b_view_model(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_race(conn, id="race:1", activity_id="1", sport="running", event_date="2026-05-19")
            _insert_race(conn, id="race:2", activity_id="2", sport="cycling", event_date="2026-06-01")

            result = career_backend.get_career_timeline({"sport": "cycling", "type": "race"}, conn)

            self.assertEqual(result["filters"], {"year": None, "type": "race"})
            nodes = [node for year in result["years"] for month in year["months"] for node in month["nodes"]]
            self.assertEqual({node["sport"] for node in nodes}, {"running", "cycling"})
        finally:
            conn.close()

    def test_timeline_year_filter(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_race(conn, id="race:1", activity_id="1", event_date="2025-10-01")
            _insert_race(conn, id="race:2", activity_id="2", event_date="2026-05-19")

            result = career_backend.get_career_timeline({"year": "2025", "type": "race"}, conn)

            self.assertEqual(result["available_years"], [2026, 2025])
            self.assertEqual([year["year"] for year in result["years"]], [2025])
            self.assertEqual(result["years"][0]["months"][0]["nodes"][0]["id"], "race:1")
        finally:
            conn.close()

    def test_timeline_race_nodes_include_backend_pb_badge_scope(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_race(conn, id="race:career", activity_id="10", event_date="2026-05-03")
            _insert_race(conn, id="race:season", activity_id="11", event_date="2026-05-02")
            _insert_race(conn, id="race:none", activity_id="12", event_date="2026-05-01")
            _insert_pb(conn, id="pb:career", activity_id="10", status="active", event_date="2026-05-03")
            _insert_pb(conn, id="pb:season", activity_id="11", status="superseded", event_date="2026-05-02")

            result = career_backend.get_career_timeline({"type": "race"}, conn)

            nodes = [node for year in result["years"] for month in year["months"] for node in month["nodes"]]
            scope_by_id = {node["id"]: node["pb_badge_scope"] for node in nodes}
            self.assertEqual(scope_by_id["race:career"], "career")
            self.assertEqual(scope_by_id["race:season"], "season")
            self.assertEqual(scope_by_id["race:none"], "none")
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_timeline_type_pb_returns_empty_years(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_race(conn, id="race:1", activity_id="1")

            result = career_backend.get_career_timeline({"type": "pb"}, conn)

            self.assertEqual(result["years"], [])
            self.assertFalse(result["status"]["data_ready"])
        finally:
            conn.close()

    def test_low_candidate_does_not_enter_timeline(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            conn.execute(
                """
                INSERT INTO career_event_candidates
                    (id, activity_id, candidate_type, title, evidence_json, confidence, status)
                VALUES
                    ('race_candidate:10', '10', 'race', '21K晨跑', '{}', 0.35, 'candidate')
                """
            )

            result = career_backend.get_career_timeline({"type": "race"}, conn)

            self.assertEqual(result["years"], [])
            self.assertEqual(result["candidates_count"], 1)
            self.assertFalse(result["status"]["data_ready"])
        finally:
            conn.close()

    def test_default_connection_uses_temp_profile_db_path(self):
        original_db_path = profile_backend.DB_PATH
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                profile_backend.DB_PATH = Path(tmpdir) / "career-overview-timeline.sqlite"
                conn = sqlite3.connect(str(profile_backend.DB_PATH))
                try:
                    career_backend.ensure_career_schema(conn)
                    _insert_race(conn, id="race:20", activity_id="20", event_date="2026-07-01")
                    conn.commit()
                finally:
                    conn.close()

                overview = career_backend.get_career_overview()
                timeline = career_backend.get_career_timeline()

                self.assertEqual(overview["latest_race"]["id"], "race:20")
                self.assertEqual(timeline["years"][0]["year"], 2026)
                self.assertEqual(timeline["available_years"], [2026])
            finally:
                profile_backend.DB_PATH = original_db_path


if __name__ == "__main__":
    unittest.main()
