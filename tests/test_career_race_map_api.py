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

FORBIDDEN_SERIALIZED_TOKENS = (
    "points_json",
    "track_json",
    "file_path",
    "storage_ref",
    "raw FIT",
    "/Users/",
    "/tmp/",
    "SQLite",
)


def _create_activities_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY,
            title TEXT,
            start_time TEXT,
            sport_type TEXT,
            start_lat REAL,
            start_lon REAL,
            region TEXT,
            region_city TEXT,
            region_country TEXT,
            region_display TEXT,
            deleted_at TEXT,
            points_json TEXT,
            track_json TEXT,
            file_path TEXT,
            storage_ref TEXT
        )
        """
    )


def _insert_activity(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": 1,
        "title": "2026 苏州 10K",
        "start_time": "2026-05-19T07:30:00",
        "sport_type": "running",
        "start_lat": 31.2989,
        "start_lon": 120.5853,
        "region": "江苏 苏州",
        "region_city": "苏州",
        "region_country": "中国",
        "region_display": "江苏 苏州",
        "deleted_at": None,
        "points_json": "[forbidden]",
        "track_json": "[forbidden]",
        "file_path": "/Users/private/race.fit",
        "storage_ref": "/tmp/private.jpg",
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
        "name": "2026 苏州 10K",
        "event_type": "10k",
        "sport": "running",
        "event_date": "2026-05-19",
        "location_json": json.dumps({"city": "苏州"}, ensure_ascii=False),
        "performance_summary_json": "{}",
        "achievement_ids_json": "[]",
        "confidence": 1.0,
        "source": "user",
        "status": "active",
        "display_metadata_json": "{}",
    }
    data.update(overrides)
    columns = list(data)
    conn.execute(
        f"INSERT INTO career_race_events ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
        [data[column] for column in columns],
    )


def _assert_forbidden_tokens_absent(testcase: unittest.TestCase, value) -> None:
    serialized = json.dumps(value, ensure_ascii=False)
    for token in FORBIDDEN_SERIALIZED_TOKENS:
        testcase.assertNotIn(token, serialized)


class TestCareerRaceMapApi(unittest.TestCase):
    def test_backend_returns_safe_points_and_detail_links(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activities_table(conn)
            career_backend.ensure_career_schema(conn)
            _insert_activity(conn)
            _insert_race(conn)

            result = career_backend.get_career_race_map(conn=conn)

            self.assertEqual(result["summary"], {
                "total": 1,
                "with_coordinates": 1,
                "without_coordinates": 0,
                "city_count": 1,
                "country_count": 0,
            })
            self.assertEqual(len(result["locations"]), 1)
            point = result["locations"][0]
            self.assertEqual(point["id"], "race:1")
            self.assertEqual(point["activity_id"], "1")
            self.assertEqual(point["title"], "2026 苏州 10K")
            self.assertEqual(point["event_type_label"], "10K")
            self.assertEqual(point["sport_label"], "跑步")
            self.assertEqual(point["city"], "苏州")
            self.assertEqual(point["region_display"], "江苏 苏州")
            self.assertEqual(point["lat"], 31.2989)
            self.assertEqual(point["lon"], 120.5853)
            self.assertEqual(point["detail_link"], {"activity_id": "1", "source": "career"})
            self.assertEqual(result["without_coordinates"], [])
            self.assertTrue(result["status"]["data_ready"])
            _assert_forbidden_tokens_absent(self, result)
        finally:
            conn.close()

    def test_backend_splits_missing_and_invalid_coordinates(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activities_table(conn)
            career_backend.ensure_career_schema(conn)
            _insert_activity(conn, id=1, start_lat=None, start_lon=None, region_display="上海")
            _insert_activity(conn, id=2, start_lat=99.0, start_lon=181.0, region_display="杭州")
            _insert_race(conn, id="race:1", activity_id="1", name="上海半马", event_type="half_marathon", event_date="2026-04-01", location_json=json.dumps({"city": "上海"}, ensure_ascii=False))
            _insert_race(conn, id="race:2", activity_id="2", name="杭州骑行赛", sport="cycling", event_type="race", event_date="2026-04-02", location_json=json.dumps({"city": "杭州"}, ensure_ascii=False))

            result = career_backend.get_career_race_map(conn=conn)

            self.assertEqual(result["locations"], [])
            self.assertEqual(result["summary"]["total"], 2)
            self.assertEqual(result["summary"]["without_coordinates"], 2)
            reasons = {item["id"]: item["reason"] for item in result["without_coordinates"]}
            self.assertEqual(reasons["race:1"], "missing_start_coordinates")
            self.assertEqual(reasons["race:2"], "invalid_start_coordinates")
            self.assertEqual(result["without_coordinates"][0]["detail_link"]["source"], "career")
            _assert_forbidden_tokens_absent(self, result)
        finally:
            conn.close()

    def test_backend_filters_and_excludes_inactive_or_deleted(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activities_table(conn)
            career_backend.ensure_career_schema(conn)
            _insert_activity(conn, id=1, start_lat=31.2, start_lon=121.4)
            _insert_activity(conn, id=2, start_lat=30.2, start_lon=120.2)
            _insert_activity(conn, id=3, start_lat=39.9, start_lon=116.3, deleted_at="2026-01-01")
            _insert_race(conn, id="race:1", activity_id="1", sport="running", event_date="2026-05-19")
            _insert_race(conn, id="race:2", activity_id="2", sport="cycling", event_date="2025-05-19")
            _insert_race(conn, id="race:3", activity_id="3", sport="running", event_date="2026-06-19")
            _insert_race(conn, id="race:4", activity_id="4", sport="running", event_date="2026-07-19", status="inactive")

            result = career_backend.get_career_race_map({"sport": "running", "year": "2026"}, conn=conn)

            self.assertEqual(result["filters"], {"sport": "running", "year": 2026})
            self.assertEqual([item["id"] for item in result["locations"]], ["race:1"])
            self.assertEqual(result["summary"]["total"], 1)
            _assert_forbidden_tokens_absent(self, result)
        finally:
            conn.close()

    def test_empty_state_is_stable_without_activities_table(self):
        conn = sqlite3.connect(":memory:")
        try:
            result = career_backend.get_career_race_map(conn=conn)

            self.assertEqual(result["locations"], [])
            self.assertEqual(result["without_coordinates"], [])
            self.assertEqual(result["summary"]["total"], 0)
            self.assertEqual(result["filters"], {"sport": "all", "year": None})
            self.assertFalse(result["status"]["data_ready"])
        finally:
            conn.close()

    def test_main_api_get_career_race_map_returns_unified_envelope(self):
        original_db_path = profile_backend.DB_PATH
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                profile_backend.DB_PATH = Path(tmpdir) / "career-race-map.sqlite"
                conn = sqlite3.connect(str(profile_backend.DB_PATH))
                try:
                    _create_activities_table(conn)
                    career_backend.ensure_career_schema(conn)
                    _insert_activity(conn, id=10, start_lat=30.2741, start_lon=120.1551, region_display="浙江 杭州")
                    _insert_race(conn, id="race:10", activity_id="10", name="杭州 10K", event_type="10k")
                    conn.commit()
                finally:
                    conn.close()

                response = main.Api().get_career_race_map({"sport": "running"})

                self.assertTrue(response["ok"])
                self.assertEqual(response["code"], main.API_CODE_OK)
                self.assertEqual(response["msg"], "ok")
                self.assertEqual(response["data"]["summary"]["total"], 1)
                self.assertEqual(response["data"]["locations"][0]["activity_id"], "10")
                _assert_forbidden_tokens_absent(self, response["data"])
            finally:
                profile_backend.DB_PATH = original_db_path

    def test_js_api_contract_registers_get_career_race_map(self):
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        methods = {item["name"]: item for item in contract["methods"]}

        self.assertIn("get_career_race_map", methods)
        method = methods["get_career_race_map"]
        self.assertEqual(method["category"], "career")
        self.assertFalse(method["high_risk"])
        self.assertTrue(method["readonly"])
        self.assertIn("without_coordinates", method["returns"])


if __name__ == "__main__":
    unittest.main()
