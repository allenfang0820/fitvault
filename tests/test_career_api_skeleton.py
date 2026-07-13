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

FORBIDDEN_RESPONSE_KEYS = {
    "points",
    "track_json",
    "raw_records",
    "fit_records",
    "file_path",
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


class TestCareerApiSkeleton(unittest.TestCase):
    def test_backend_overview_returns_stable_empty_state_and_creates_schema(self):
        conn = sqlite3.connect(":memory:")
        try:
            result = career_backend.get_career_overview(conn)

            self.assertEqual(
                result["summary"],
                {
                    "career_start_year": None,
                    "activity_count": 0,
                    "race_count": 0,
                    "pb_count": 0,
                    "achievement_count": 0,
                    "covered_city_count": 0,
                    "total_distance_km": None,
                },
            )
            self.assertIsNone(result["latest_race"])
            self.assertEqual(result["representative_achievements"], [])
            self.assertEqual(result["status"]["schema_ready"], True)
            self.assertEqual(result["status"]["data_ready"], False)
            self.assertIn("赛事、PB 与成就解析后生成", result["status"]["message"])

            table = conn.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name = 'career_schema_meta'
                """
            ).fetchone()
            self.assertIsNotNone(table)
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_backend_timeline_returns_stable_empty_state_and_normalized_filters(self):
        conn = sqlite3.connect(":memory:")
        try:
            result = career_backend.get_career_timeline(
                {"sport": "running", "year": "2026", "type": "pb"},
                conn,
            )

            self.assertEqual(result["filters"], {"year": 2026, "type": "pb"})
            self.assertEqual(result["years"], [])
            self.assertEqual(result["candidates_count"], 0)
            self.assertEqual(result["status"]["schema_ready"], True)
            self.assertEqual(result["status"]["data_ready"], False)
            self.assertIn("时间轴将在 ACS 派生事件生成后展示", result["status"]["message"])
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_backend_overview_uses_safe_activity_aggregates_only(self):
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute(
                """
                CREATE TABLE activities (
                    id INTEGER PRIMARY KEY,
                    start_time TEXT,
                    dist_km REAL,
                    region_city TEXT,
                    deleted_at TEXT,
                    file_path TEXT,
                    track_json TEXT
                )
                """
            )
            conn.execute(
                """
                INSERT INTO activities
                    (id, start_time, dist_km, region_city, deleted_at, file_path, track_json)
                VALUES
                    (1, '2024-03-01T08:00:00', 10.5, '北京', NULL, '/tmp/a.fit', '[1]'),
                    (2, '2025-04-01T08:00:00', 5.0, '上海', NULL, '/tmp/b.fit', '[2]'),
                    (3, '2023-01-01T08:00:00', 99.0, '杭州', '2025-01-01', '/tmp/c.fit', '[3]')
                """
            )

            result = career_backend.get_career_overview(conn)

            self.assertEqual(result["summary"]["career_start_year"], 2024)
            self.assertEqual(result["summary"]["activity_count"], 2)
            self.assertEqual(result["summary"]["covered_city_count"], 2)
            self.assertEqual(result["summary"]["total_distance_km"], 15.5)
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_main_api_career_methods_return_unified_envelope(self):
        original_db_path = profile_backend.DB_PATH
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                profile_backend.DB_PATH = Path(tmpdir) / "career_api.sqlite"
                api = main.Api()

                overview = api.get_career_overview()
                timeline = api.get_career_timeline({"sport": "all", "year": "", "type": "all"})

                for response in (overview, timeline):
                    self.assertTrue(response["ok"])
                    self.assertEqual(response["code"], 0)
                    self.assertEqual(response["msg"], "ok")
                    self.assertIsInstance(response["traceId"], str)
                    self.assertTrue(response["traceId"])
                    self.assertIsInstance(response["data"], dict)
                    _assert_forbidden_keys_absent(self, response["data"])

                self.assertIn("summary", overview["data"])
                self.assertEqual(timeline["data"]["filters"], {"year": None, "type": "all"})
            finally:
                profile_backend.DB_PATH = original_db_path

    def test_js_api_contract_registers_career_readonly_methods(self):
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        methods = {item["name"]: item for item in contract["methods"]}

        for name in ("get_career_overview", "get_career_timeline"):
            self.assertIn(name, methods)
            method = methods[name]
            self.assertEqual(method["category"], "career")
            self.assertFalse(method["high_risk"])
            self.assertTrue(method["readonly"])
            self.assertIn("{ ok, code, msg", method["returns"])

        refresh_method = methods["refresh_career_derived_events"]
        self.assertEqual(refresh_method["category"], "career")
        self.assertFalse(refresh_method["high_risk"])
        self.assertFalse(refresh_method["readonly"])
        self.assertIn("{ ok, code, msg", refresh_method["returns"])
        self.assertIn("派生事件索引", refresh_method["description"])


if __name__ == "__main__":
    unittest.main()
