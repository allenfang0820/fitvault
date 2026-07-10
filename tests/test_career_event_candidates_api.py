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
    "points_json",
    "track_json",
    "raw_records",
    "fit_records",
    "file_path",
    "advanced_metrics",
    "shadow_diff_json",
    "sqlite_schema",
    "schema",
    "evidence_json",
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
        "title": "晨跑",
        "title_source": "sport_name",
        "sport_type": "running",
        "sub_sport_type": "generic",
        "start_time": "2026-05-19T08:00:00+08:00",
        "start_time_utc": "2026-05-19T00:00:00Z",
        "dist_km": 21.1,
        "distance": None,
        "duration": 7200,
        "duration_sec": 7200,
        "avg_pace": 341,
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


def _insert_candidate(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": "race_candidate:1",
        "activity_id": "1",
        "candidate_type": "race",
        "title": "晨跑",
        "evidence_json": json.dumps(
            {
                "resolver": "race",
                "decision": "candidate",
                "event_type": "half_marathon",
                "confidence_level": "low",
                "signals": [
                    {
                        "type": "standard_distance",
                        "level": "low",
                        "category": "half_marathon",
                        "distance_km": 21.1,
                        "file_path": "/tmp/leak.fit",
                    }
                ],
                "track_json": "[forbidden]",
            },
            ensure_ascii=False,
        ),
        "confidence": 0.35,
        "status": "candidate",
    }
    data.update(overrides)
    columns = list(data)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO career_event_candidates ({', '.join(columns)}) VALUES ({placeholders})",
        [data[column] for column in columns],
    )


class TestCareerEventCandidatesApi(unittest.TestCase):
    def test_backend_empty_state_returns_stable_shape(self):
        conn = sqlite3.connect(":memory:")
        try:
            result = career_backend.get_career_event_candidates(conn=conn)

            self.assertEqual(result["candidates"], [])
            self.assertEqual(result["summary"], {
                "total": 0,
                "by_type": {},
                "by_status": {},
                "max_confidence": None,
            })
            self.assertEqual(result["filters"], {
                "candidate_type": "all",
                "status": "candidate",
                "min_confidence": None,
            })
            self.assertTrue(result["status"]["schema_ready"])
            self.assertFalse(result["status"]["data_ready"])
        finally:
            conn.close()

    def test_backend_returns_safe_candidate_view_model(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_candidate(conn)

            result = career_backend.get_career_event_candidates(conn=conn)

            self.assertEqual(result["summary"]["total"], 1)
            item = result["candidates"][0]
            self.assertEqual(item["id"], "race_candidate:1")
            self.assertEqual(item["candidate_type_label"], "赛事候选")
            self.assertEqual(item["event_type_label"], "半程马拉松")
            self.assertEqual(item["confidence_label"], "低置信度")
            self.assertEqual(item["status_label"], "待确认")
            self.assertEqual(item["detail_link"], {"activity_id": "1", "source": "career"})
            self.assertIn("标准距离匹配", item["evidence_summary"][0])
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_confirm_race_candidate_promotes_to_race_event(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(conn)
            career_backend.ensure_career_schema(conn)
            _insert_candidate(conn)

            result = career_backend.resolve_career_event_candidate(
                {"id": "race_candidate:1", "decision": "confirm_race"},
                conn=conn,
            )

            self.assertTrue(result["changed"])
            self.assertEqual(result["candidate"]["status"], "resolved")
            race = conn.execute(
                "SELECT activity_id, confidence, source, status FROM career_race_events WHERE id = 'race:1'"
            ).fetchone()
            self.assertEqual(race, ("1", 1.0, "user", "active"))
            activity = conn.execute(
                "SELECT is_race, race_source, race_confidence, race_override FROM activities WHERE id = 1"
            ).fetchone()
            self.assertEqual(activity, (1, "user", "high", 1))
        finally:
            conn.close()

    def test_dismiss_candidate_persists_user_cancel_and_does_not_reactivate(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(conn)
            career_backend.resolve_race_events(conn)

            result = career_backend.resolve_career_event_candidate(
                {"id": "race_candidate:1", "decision": "dismiss"},
                conn=conn,
            )
            career_backend.resolve_race_events(conn)

            self.assertTrue(result["changed"])
            candidate_status = conn.execute(
                "SELECT status FROM career_event_candidates WHERE id = 'race_candidate:1'"
            ).fetchone()[0]
            self.assertEqual(candidate_status, "dismissed")
            race_count = conn.execute(
                "SELECT COUNT(*) FROM career_race_events WHERE status = 'active'"
            ).fetchone()[0]
            self.assertEqual(race_count, 0)
            activity = conn.execute(
                "SELECT is_race, race_source, race_override FROM activities WHERE id = 1"
            ).fetchone()
            self.assertEqual(activity, (0, "user", 1))
        finally:
            conn.close()

    def test_main_api_candidate_workflow_returns_unified_envelope(self):
        original_db_path = profile_backend.DB_PATH
        original_profile_schema = profile_backend._SCHEMA_READY_FOR
        original_main_schema = main._ACTIVITY_SYNC_SCHEMA_READY_FOR
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                profile_backend.DB_PATH = Path(tmpdir) / "career-candidates.sqlite"
                profile_backend._SCHEMA_READY_FOR = None
                main._ACTIVITY_SYNC_SCHEMA_READY_FOR = None
                main.ensure_activity_sync_schema()
                conn = profile_backend._conn()
                try:
                    conn.execute(
                        """
                        INSERT INTO activities
                            (filename, file_name, title, title_source, sport_type, start_time,
                             dist_km, is_race, race_override, deleted_at)
                        VALUES
                            ('candidate.fit', 'candidate.fit', '晨跑', 'sport_name', 'running',
                             '2026-05-19T08:00:00+08:00', 21.1, 0, 0, NULL)
                        """
                    )
                    conn.commit()
                    career_backend.resolve_race_events(conn)
                    conn.commit()
                finally:
                    conn.close()

                api = main.Api()
                listed = api.get_career_event_candidates()
                self.assertTrue(listed["ok"])
                self.assertEqual(listed["code"], main.API_CODE_OK)
                self.assertEqual(listed["data"]["summary"]["total"], 1)

                resolved = api.resolve_career_event_candidate(
                    {"id": listed["data"]["candidates"][0]["id"], "decision": "confirm_race"}
                )
                self.assertTrue(resolved["ok"])
                self.assertEqual(resolved["data"]["candidate"]["status"], "resolved")
                self.assertIn("traceId", resolved)
                _assert_forbidden_keys_absent(self, resolved["data"])
            finally:
                profile_backend.DB_PATH = original_db_path
                profile_backend._SCHEMA_READY_FOR = original_profile_schema
                main._ACTIVITY_SYNC_SCHEMA_READY_FOR = original_main_schema

    def test_js_api_contract_registers_candidate_methods(self):
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        methods = {item["name"]: item for item in contract["methods"]}

        self.assertIn("get_career_event_candidates", methods)
        self.assertIn("resolve_career_event_candidate", methods)
        self.assertTrue(methods["get_career_event_candidates"]["readonly"])
        self.assertFalse(methods["resolve_career_event_candidate"]["readonly"])


if __name__ == "__main__":
    unittest.main()
