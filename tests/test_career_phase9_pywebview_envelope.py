import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import career_backend
import main
import profile_backend


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACK_HTML_PATH = PROJECT_ROOT / "track.html"


def _create_activities_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY,
            start_time TEXT,
            start_time_utc TEXT,
            sport_type TEXT,
            dist_km REAL,
            region_city TEXT,
            deleted_at TEXT,
            points_json TEXT,
            track_json TEXT,
            file_path TEXT
        )
        """
    )


def _seed_activity(conn: sqlite3.Connection) -> None:
    _create_activities_table(conn)
    career_backend.ensure_career_schema(conn)
    conn.execute(
        """
        INSERT INTO activities
            (id, start_time, start_time_utc, sport_type, dist_km, region_city,
             deleted_at, points_json, track_json, file_path)
        VALUES
            (1, '2026-05-19T07:00:00+08:00', '', 'running', 10.0, '上海',
             NULL, '[forbidden]', '[forbidden]', '/tmp/forbidden.fit')
        """
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
    for token in ("/Users/", "\\Users\\", "/tmp/", "sqlite_schema", "Traceback"):
        testcase.assertNotIn(token, text)


def _extract_function_body(source: str, signature: str) -> str:
    start = source.find(signature)
    if start < 0:
        raise AssertionError(f"未找到函数签名: {signature}")
    brace_start = source.find("{", start + len(signature))
    if brace_start < 0:
        raise AssertionError(f"未找到函数体起始: {signature}")
    depth = 1
    index = brace_start + 1
    while index < len(source) and depth > 0:
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        index += 1
    if depth != 0:
        raise AssertionError(f"函数体括号不闭合: {signature}")
    return source[brace_start + 1:index - 1]


class TestCareerPhase9PywebviewEnvelope(unittest.TestCase):
    def test_career_pywebview_methods_return_unified_envelope(self):
        original_db_path = profile_backend.DB_PATH
        with tempfile.TemporaryDirectory(prefix="脉图 ACS envelope ") as tmpdir:
            try:
                profile_backend.DB_PATH = Path(tmpdir) / "含 空格" / "career.sqlite"
                profile_backend.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(str(profile_backend.DB_PATH))
                try:
                    _seed_activity(conn)
                finally:
                    conn.close()

                api = main.Api()
                calls = (
                    api.get_career_overview,
                    lambda: api.get_career_timeline({"type": "all"}),
                    lambda: api.get_career_races({}),
                    lambda: api.get_career_pb({}),
                    lambda: api.get_career_achievements({}),
                    lambda: api.get_career_memory_gallery({}),
                    api.get_latest_career_snapshot,
                    lambda: api.generate_career_insight({"refresh_snapshot": False}),
                )
                for call in calls:
                    response = call()
                    _assert_envelope(self, response, ok=True, code=main.API_CODE_OK)
                    _assert_no_forbidden_text(self, response)
            finally:
                profile_backend.DB_PATH = original_db_path

    def test_career_validation_errors_keep_envelope_and_do_not_echo_paths(self):
        api = main.Api()
        responses = (
            api.generate_career_insight({"prompt": "bad"}),
        )
        for response in responses:
            _assert_envelope(self, response, ok=False, code=main.API_CODE_VALIDATION)
            _assert_no_forbidden_text(self, response)

    def test_career_frontend_requires_valid_envelope_data(self):
        source = TRACK_HTML_PATH.read_text(encoding="utf-8")
        helper = _extract_function_body(source, "function requireCareerApiData(res, fallback)")

        self.assertIn("typeof res !== 'object'", helper)
        self.assertIn("res.ok === false", helper)
        self.assertIn("Number(res.code) !== 0", helper)
        self.assertIn("!res.data || typeof res.data !== 'object'", helper)

        for signature in (
            "async function loadCareerOverview()",
            "async function loadCareerMemory(filters)",
        ):
            body = _extract_function_body(source, signature)
            self.assertIn("requireCareerApiData", body, signature)


if __name__ == "__main__":
    unittest.main()
