import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import career_backend
import main
import profile_backend


def _create_activities_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY,
            start_time TEXT,
            start_time_utc TEXT,
            sport_type TEXT,
            dist_km REAL,
            duration_sec INTEGER,
            region_city TEXT,
            deleted_at TEXT,
            points_json TEXT,
            track_json TEXT,
            file_path TEXT
        )
        """
    )


def _seed_activity(conn: sqlite3.Connection, *, year: int = 2026) -> None:
    _create_activities_table(conn)
    career_backend.ensure_career_schema(conn)
    conn.execute(
        """
        INSERT INTO activities
            (id, start_time, start_time_utc, sport_type, dist_km, duration_sec,
             region_city, deleted_at, points_json, track_json, file_path)
        VALUES
            (1, ?, '', 'running', 10.0, 3600, '上海',
             NULL, '[forbidden]', '[forbidden]', '/tmp/forbidden.fit')
        """,
        (f"{year}-05-19T07:00:00+08:00",),
    )
    conn.commit()


def _assert_envelope(testcase, response, *, ok, code):
    testcase.assertIsInstance(response, dict)
    testcase.assertEqual(response.get("ok"), ok)
    testcase.assertEqual(response.get("code"), code)
    testcase.assertIsInstance(response.get("msg"), str)
    testcase.assertIsInstance(response.get("data"), dict)
    testcase.assertIsInstance(response.get("traceId"), str)
    testcase.assertTrue(response.get("traceId"))


def _assert_no_forbidden_text(testcase, value):
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    for token in ("/Users/", "\\Users\\", "/tmp/", "sqlite_schema", "Traceback", "points_json", "track_json"):
        testcase.assertNotIn(token, text)


class TestCareerYearInsightReadApi(unittest.TestCase):
    def test_get_career_year_insight_returns_unified_envelope(self):
        original_db_path = profile_backend.DB_PATH
        with tempfile.TemporaryDirectory(prefix="脉图 year insight ") as tmpdir:
            try:
                profile_backend.DB_PATH = Path(tmpdir) / "career.sqlite"
                conn = sqlite3.connect(str(profile_backend.DB_PATH))
                try:
                    _seed_activity(conn, year=2026)
                finally:
                    conn.close()

                response = main.Api().get_career_year_insight({"year": 2026})

                _assert_envelope(self, response, ok=True, code=main.API_CODE_OK)
                _assert_no_forbidden_text(self, response)
                data = response["data"]
                self.assertEqual(data["year"], 2026)
                self.assertEqual(data["report_state"], "not_generated")
                self.assertIn("facts", data)
                self.assertIsNone(data["report"])
                self.assertEqual(data["local_fallback"]["mode"], "local_fallback")
            finally:
                profile_backend.DB_PATH = original_db_path

    def test_get_career_year_insight_defaults_to_latest_activity_year(self):
        original_db_path = profile_backend.DB_PATH
        with tempfile.TemporaryDirectory(prefix="脉图 year insight default ") as tmpdir:
            try:
                profile_backend.DB_PATH = Path(tmpdir) / "career.sqlite"
                conn = sqlite3.connect(str(profile_backend.DB_PATH))
                try:
                    _seed_activity(conn, year=2025)
                    conn.execute(
                        """
                        INSERT INTO activities
                            (id, start_time, start_time_utc, sport_type, dist_km, duration_sec,
                             region_city, deleted_at, points_json, track_json, file_path)
                        VALUES
                            (2, '2026-05-19T07:00:00+08:00', '', 'running', 5.0, 1800,
                             '上海', NULL, '', '', '')
                        """
                    )
                    conn.commit()
                finally:
                    conn.close()

                response = main.Api().get_career_year_insight({})

                _assert_envelope(self, response, ok=True, code=main.API_CODE_OK)
                self.assertEqual(response["data"]["year"], 2026)
                self.assertEqual(response["data"]["available_years"], [2026, 2025])
            finally:
                profile_backend.DB_PATH = original_db_path

    def test_no_data_year_returns_business_state_not_error(self):
        original_db_path = profile_backend.DB_PATH
        with tempfile.TemporaryDirectory(prefix="脉图 year insight nodata ") as tmpdir:
            try:
                profile_backend.DB_PATH = Path(tmpdir) / "career.sqlite"
                conn = sqlite3.connect(str(profile_backend.DB_PATH))
                try:
                    career_backend.ensure_career_schema(conn)
                finally:
                    conn.close()

                response = main.Api().get_career_year_insight({"year": 2026})

                _assert_envelope(self, response, ok=True, code=main.API_CODE_OK)
                _assert_no_forbidden_text(self, response)
                self.assertEqual(response["data"]["report_state"], "no_data")
                self.assertFalse(response["data"]["status"]["data_ready"])
            finally:
                profile_backend.DB_PATH = original_db_path

    def test_unknown_or_invalid_parameters_return_validation_envelope(self):
        api = main.Api()
        responses = (
            api.get_career_year_insight({"year": 2026, "prompt": "bad"}),
            api.get_career_year_insight({"year": True}),
            api.get_career_year_insight({"year": "bad"}),
            api.get_career_year_insight({"year": 1800}),
        )
        for response in responses:
            _assert_envelope(self, response, ok=False, code=main.API_CODE_VALIDATION)
            _assert_no_forbidden_text(self, response)

    def test_js_api_contract_registers_get_career_year_insight(self):
        contract = json.loads(Path("docs/js_api_contract.json").read_text(encoding="utf-8"))
        methods = {entry["name"]: entry for entry in contract.get("methods", [])}

        self.assertIn("get_career_year_insight", methods)
        method = methods["get_career_year_insight"]
        self.assertTrue(method["readonly"])
        self.assertIn("year", method["returns"])
        self.assertIn("local_fallback", method["returns"])
        self.assertIn("不调用 LLM", method["description"])
        self.assertIn("未知字段拒绝", method["description"])

    def test_generate_career_insight_contract_is_not_replaced(self):
        api = main.Api()
        response = api.generate_career_insight({"prompt": "bad"})

        _assert_envelope(self, response, ok=False, code=main.API_CODE_VALIDATION)
        self.assertIn("refresh_snapshot", response["msg"])


if __name__ == "__main__":
    unittest.main()
