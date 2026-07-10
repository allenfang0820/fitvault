import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import career_backend
import main
import profile_backend


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = PROJECT_ROOT / "docs" / "js_api_contract.json"
TRACK_HTML_PATH = PROJECT_ROOT / "track.html"

FORBIDDEN_RESPONSE_KEYS = {
    "points",
    "points_json",
    "track_json",
    "raw_records",
    "fit_records",
    "file_path",
    "advanced_metrics",
    "shadow_diff_json",
    "storage_ref",
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
    elif isinstance(value, str):
        testcase.assertNotIn("/Users/", value)
        testcase.assertNotIn("\\Users\\", value)
        testcase.assertNotIn("/tmp/", value)


def _create_activity_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY,
            start_time TEXT,
            start_time_utc TEXT,
            dist_km REAL,
            distance REAL,
            duration INTEGER,
            duration_sec INTEGER,
            sport_type TEXT,
            sub_sport_type TEXT,
            region_city TEXT,
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
        "start_time": "2026-01-01T08:00:00+08:00",
        "start_time_utc": "",
        "dist_km": 10.0,
        "distance": None,
        "duration": 3600,
        "duration_sec": None,
        "sport_type": "running",
        "sub_sport_type": "",
        "region_city": "北京",
        "deleted_at": None,
        "points_json": "[forbidden]",
        "track_json": "[forbidden]",
        "file_path": "/tmp/forbidden.fit",
    }
    data.update(overrides)
    columns = list(data)
    conn.execute(
        f"INSERT INTO activities ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
        [data[column] for column in columns],
    )


def _insert_race(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": "race:1",
        "activity_id": "1",
        "name": "2026 北京半程马拉松",
        "event_type": "half_marathon",
        "sport": "running",
        "event_date": "2026-05-01",
        "location_json": json.dumps({"city": "北京"}, ensure_ascii=False),
        "performance_summary_json": "{}",
        "achievement_ids_json": "[]",
        "confidence": 1.0,
        "source": "resolver",
        "status": "active",
        "display_metadata_json": "{}",
    }
    data.update(overrides)
    columns = list(data)
    conn.execute(
        f"INSERT INTO career_race_events ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
        [data[column] for column in columns],
    )


def _insert_pb(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": "pb:running_10k:1",
        "activity_id": "1",
        "sport": "running",
        "pb_type": "running_10k",
        "value": "3000",
        "value_unit": "seconds",
        "improvement": None,
        "event_date": "2026-05-01",
        "confidence": 1.0,
        "source": "resolver",
        "status": "active",
        "display_metadata_json": "{}",
    }
    data.update(overrides)
    columns = list(data)
    conn.execute(
        f"INSERT INTO career_pb_records ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
        [data[column] for column in columns],
    )


def _insert_achievement(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": "achievement:first_city:1",
        "activity_id": "4",
        "achievement_type": "first_city",
        "title": "首次点亮城市",
        "event_date": "2025-03-01",
        "score": 60,
        "icon": "map-pin",
        "description": "首次点亮城市：杭州",
        "confidence": 1.0,
        "source": "resolver",
        "status": "active",
        "display_metadata_json": "{}",
    }
    data.update(overrides)
    columns = list(data)
    conn.execute(
        f"INSERT INTO career_achievement_events ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
        [data[column] for column in columns],
    )


def _insert_memory(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": "memory:story:1",
        "race_id": "",
        "activity_id": "1",
        "memory_type": "story",
        "storage_ref": "",
        "story_text": "年度记忆",
        "metadata_json": "{}",
        "title": "年度记忆",
        "event_date": "2026-05-01",
        "status": "active",
    }
    data.update(overrides)
    columns = list(data)
    conn.execute(
        f"INSERT INTO career_memory_items ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
        [data[column] for column in columns],
    )


class TestCareerSeasonsApi(unittest.TestCase):
    def test_backend_groups_activity_and_derived_counts_by_year(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            career_backend.ensure_career_schema(conn)
            _insert_activity(conn, id=1, start_time="2026-01-01T08:00:00+08:00", dist_km=10.0, duration=3600, sport_type="running", region_city="北京")
            _insert_activity(conn, id=2, start_time="2026-02-01T08:00:00+08:00", dist_km=5.0, duration=1800, sport_type="running", region_city="北京")
            _insert_activity(conn, id=3, start_time="2026-03-01T08:00:00+08:00", dist_km=None, distance=20000, duration=None, duration_sec=4000, sport_type="cycling", region_city="上海")
            _insert_activity(conn, id=4, start_time="2025-03-01T08:00:00+08:00", dist_km=50.0, duration=7200, sport_type="cycling", region_city="杭州")
            _insert_activity(conn, id=5, start_time="2024-03-01T08:00:00+08:00", dist_km=99.0, sport_type="running", region_city="广州", deleted_at="2026-01-01")
            _insert_race(conn)
            _insert_pb(conn)
            _insert_achievement(conn)
            _insert_memory(conn)
            _insert_memory(conn, id="memory:story:2025", activity_id="4", event_date="2025-03-01")

            result = career_backend.get_career_seasons(conn=conn)

            self.assertEqual([season["year"] for season in result["seasons"]], [2026, 2025])
            season_2026 = result["seasons"][0]
            self.assertEqual(season_2026["activity_count"], 3)
            self.assertEqual(season_2026["total_distance_km"], 35.0)
            self.assertEqual(season_2026["total_duration_seconds"], 9400)
            self.assertEqual(season_2026["race_count"], 1)
            self.assertEqual(season_2026["pb_count"], 1)
            self.assertEqual(season_2026["achievement_count"], 0)
            self.assertEqual(season_2026["memory_count"], 1)
            self.assertEqual(season_2026["city_count"], 2)
            self.assertEqual(season_2026["primary_sport"], "running")
            self.assertEqual(season_2026["primary_sport_label"], "跑步")
            self.assertEqual(season_2026["season_stage"], "高光年")
            self.assertIn("3 次活动", " ".join(season_2026["highlights"]))
            self.assertIn("1 场赛事", " ".join(season_2026["highlights"]))
            self.assertEqual(result["summary"]["total_seasons"], 2)
            self.assertEqual(result["summary"]["total_activity_count"], 4)
            self.assertEqual(result["summary"]["total_distance_km"], 85.0)
            self.assertTrue(result["status"]["data_ready"])
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_backend_filters_year_and_sport_without_frontend_fact_calculation(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            career_backend.ensure_career_schema(conn)
            _insert_activity(conn, id=1, start_time="2026-01-01T08:00:00+08:00", sport_type="running", dist_km=10.0)
            _insert_activity(conn, id=2, start_time="2026-02-01T08:00:00+08:00", sport_type="cycling", dist_km=40.0)
            _insert_activity(conn, id=3, start_time="2025-01-01T08:00:00+08:00", sport_type="running", dist_km=5.0)
            _insert_race(conn)

            result = career_backend.get_career_seasons({"year": "2026", "sport": "running"}, conn=conn)

            self.assertEqual(result["filters"], {"year": 2026, "sport": "running"})
            self.assertEqual(len(result["seasons"]), 1)
            self.assertEqual(result["seasons"][0]["year"], 2026)
            self.assertEqual(result["seasons"][0]["activity_count"], 1)
            self.assertEqual(result["seasons"][0]["total_distance_km"], 10.0)
            self.assertEqual(result["seasons"][0]["race_count"], 1)
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_backend_empty_state_is_stable(self):
        conn = sqlite3.connect(":memory:")
        try:
            result = career_backend.get_career_seasons(conn=conn)

            self.assertEqual(result["seasons"], [])
            self.assertEqual(result["summary"]["total_seasons"], 0)
            self.assertIsNone(result["summary"]["latest_year"])
            self.assertIsNone(result["summary"]["total_distance_km"])
            self.assertFalse(result["status"]["data_ready"])
            self.assertIn("年度生涯", result["status"]["message"])
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_overview_includes_representative_seasons(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(conn, id=1, start_time="2026-01-01T08:00:00+08:00")

            result = career_backend.get_career_overview(conn)

            self.assertEqual(len(result["representative_seasons"]), 1)
            self.assertEqual(result["representative_seasons"][0]["year"], 2026)
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_main_api_and_js_contract_register_get_career_seasons(self):
        original_db_path = profile_backend.DB_PATH
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                profile_backend.DB_PATH = Path(tmpdir) / "career.sqlite"
                response = main.Api().get_career_seasons({})

                self.assertTrue(response["ok"])
                self.assertEqual(response["code"], 0)
                self.assertEqual(response["msg"], "ok")
                self.assertIsInstance(response["traceId"], str)
                self.assertIn("seasons", response["data"])
                _assert_forbidden_keys_absent(self, response["data"])
            finally:
                profile_backend.DB_PATH = original_db_path

        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        methods = {item["name"]: item for item in contract["methods"]}
        self.assertIn("get_career_seasons", methods)
        self.assertEqual(methods["get_career_seasons"]["category"], "career")
        self.assertTrue(methods["get_career_seasons"]["readonly"])
        self.assertFalse(methods["get_career_seasons"]["high_risk"])

    def test_frontend_renders_backend_season_view_model(self):
        source = TRACK_HTML_PATH.read_text(encoding="utf-8")

        self.assertIn("window.pywebview.api.get_career_seasons", source)
        self.assertIn("function normalizeCareerSeasons", source)
        self.assertIn("function renderCareerSeasons", source)
        self.assertIn('id="career-season-strip"', source)
        self.assertIn("data-career-season-year", source)
        self.assertIn("requireCareerApiData(res, '年度结构加载失败')", source)


if __name__ == "__main__":
    unittest.main()
