import inspect
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
    "storage_ref",
    "path",
    "thumbnail_url",
    "detail_link",
}


def _assert_forbidden_absent(testcase, value):
    if isinstance(value, dict):
        for key, child in value.items():
            testcase.assertNotIn(str(key).lower(), FORBIDDEN_RESPONSE_KEYS)
            _assert_forbidden_absent(testcase, child)
    elif isinstance(value, list):
        for child in value:
            _assert_forbidden_absent(testcase, child)
    elif isinstance(value, str):
        testcase.assertNotIn("/Users/", value)
        testcase.assertNotIn("\\Users\\", value)
        testcase.assertNotIn("/tmp/", value)


def _create_activities_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY,
            start_time TEXT,
            start_time_utc TEXT,
            sport_type TEXT,
            dist_km REAL,
            distance REAL,
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
        "start_time": "2026-05-19T07:00:00+08:00",
        "start_time_utc": "",
        "sport_type": "running",
        "dist_km": 10.0,
        "distance": None,
        "region_city": "北京",
        "deleted_at": None,
        "points_json": "[forbidden]",
        "track_json": "[forbidden]",
        "file_path": "/tmp/forbidden.fit",
    }
    data.update(overrides)
    columns = list(data)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO activities ({', '.join(columns)}) VALUES ({placeholders})",
        [data[column] for column in columns],
    )


def _insert_memory(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT INTO career_memory_items
            (id, race_id, activity_id, memory_type, title, event_date,
             storage_ref, story_text, metadata_json, status)
        VALUES
            ('memory:1', '', '1', 'story', '第一次半马记忆', '2026-05-19',
             '/Users/example/private.jpg', '最后三公里很难，但撑住了。',
             '{"path":"/tmp/private.jpg"}', 'active')
        """
    )


def _seed_snapshot_source(conn: sqlite3.Connection) -> None:
    _create_activities_table(conn)
    career_backend.ensure_career_schema(conn)
    _insert_activity(conn)
    _insert_memory(conn)


class TestCareerSnapshotPersistence(unittest.TestCase):
    def test_save_career_snapshot_creates_latest_row_with_white_listed_content(self):
        conn = sqlite3.connect(":memory:")
        try:
            _seed_snapshot_source(conn)

            result = career_backend.save_career_snapshot(conn=conn)
            row = conn.execute(
                """
                SELECT id, snapshot_type, content_json, source_version
                FROM career_snapshots
                WHERE id = 'career_snapshot:latest'
                """
            ).fetchone()
            content = json.loads(row[2])

            self.assertTrue(result["saved"])
            self.assertEqual(row[0], "career_snapshot:latest")
            self.assertEqual(row[1], "career")
            self.assertEqual(row[3], "acs.v1")
            self.assertEqual(content["snapshot_version"], "acs.v1")
            self.assertEqual(content["summary"]["activity_count"], 1)
            self.assertNotIn("memory_count", content["summary"])
            self.assertNotIn("representative_memories", content)
            _assert_forbidden_absent(self, result)
            _assert_forbidden_absent(self, content)
        finally:
            conn.close()

    def test_save_career_snapshot_upserts_latest_without_growing_rows(self):
        conn = sqlite3.connect(":memory:")
        try:
            _seed_snapshot_source(conn)

            first = career_backend.save_career_snapshot(conn=conn)
            second = career_backend.save_career_snapshot(conn=conn)
            count = conn.execute("SELECT COUNT(*) FROM career_snapshots").fetchone()[0]

            self.assertEqual(count, 1)
            self.assertEqual(first["source_version"], "acs.v1")
            self.assertEqual(second["source_version"], "acs.v1")
            _assert_forbidden_absent(self, second)
        finally:
            conn.close()

    def test_get_latest_career_snapshot_empty_state_does_not_auto_generate(self):
        conn = sqlite3.connect(":memory:")
        try:
            _seed_snapshot_source(conn)

            result = career_backend.get_latest_career_snapshot(conn=conn)
            count = conn.execute("SELECT COUNT(*) FROM career_snapshots").fetchone()[0]

            self.assertIsNone(result["snapshot"])
            self.assertEqual(result["status"]["message"], "暂无 Career Snapshot")
            self.assertFalse(result["status"]["data_ready"])
            self.assertEqual(count, 0)
            _assert_forbidden_absent(self, result)
        finally:
            conn.close()

    def test_get_latest_career_snapshot_returns_saved_snapshot(self):
        conn = sqlite3.connect(":memory:")
        try:
            _seed_snapshot_source(conn)
            saved = career_backend.save_career_snapshot(conn=conn)

            result = career_backend.get_latest_career_snapshot(conn=conn)

            self.assertEqual(result["snapshot"]["snapshot_version"], "acs.v1")
            self.assertEqual(result["source_version"], "acs.v1")
            self.assertEqual(result["snapshot"]["summary"], saved["snapshot"]["summary"])
            self.assertTrue(result["status"]["data_ready"])
            self.assertEqual(result["status"]["message"], "Career Snapshot 已保存")
            _assert_forbidden_absent(self, result)
        finally:
            conn.close()

    def test_get_latest_career_snapshot_sanitizes_historical_dirty_content(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            dirty_snapshot = {
                "snapshot_version": "acs.v1",
                "generated_at": "2026-07-08T00:00:00+00:00",
                "summary": {"activity_count": 1, "storage_ref": "/Users/example/private.jpg"},
                "primary_sport": {"sport": "running", "activity_count": 1, "path": "/tmp/private"},
                "pb_summary": [{"id": "pb:1", "activity_id": "1", "sport": "running", "pb_type": "running_5k", "value": 1500, "value_unit": "seconds", "event_date": "2026-05-19", "points": [1]}],
                "records_summary": {
                    "current_records": [{"id": "pb:1", "activity_id": "1", "sport": "running", "pb_type": "running_5k", "value": 1500, "value_unit": "seconds", "event_date": "2026-05-19", "detail_link": {"activity_id": "1"}}],
                    "recent_refreshes": [{"id": "event:1", "record_id": "pb:1", "activity_id": "1", "pb_type": "running_5k", "event_type": "activated", "event_at": "2026-05-19", "resolver_version": "records-v1", "source": "resolver", "payload": {"path": "/tmp/private.fit"}}],
                    "candidate_count": 2,
                    "evolution_summary": {"total_event_count": 1, "refresh_event_count": 1, "by_event_type": {"activated": 1}, "by_pb_type": {"running_5k": 1}, "latest_event_at": "2026-05-19"},
                    "trend_inputs": {"basis": "career_record_events", "refresh_frequency_count": 1, "evolution_event_count": 1, "interpretation": "ability_improved"},
                },
                "major_achievements": [{"id": "achievement:1", "activity_id": "1", "achievement_type": "first_running_5k", "title": "首次跑完 5K", "event_date": "2026-05-19", "score": 70, "track_json": "[forbidden]"}],
                "timeline_digest": [{"id": "race:1", "activity_id": "1", "type": "race", "title": "比赛", "date": "2026-05-19", "detail_link": {"activity_id": "1"}, "File_Path": "/Users/example/private.fit"}],
                "representative_memories": [{"id": "memory:1", "activity_id": "1", "race_id": "", "type": "photo", "title": "照片", "story": "", "date": "2026-05-19", "has_media": True, "storage_ref": "/Users/example/private.jpg", "Storage_Ref": "/Users/example/private-case.jpg", "thumbnail_url": "/tmp/private.jpg", "detail_link": {"activity_id": "1"}}],
                "status": {"schema_ready": True, "data_ready": True, "message": "dirty", "sqlite_schema": "forbidden", "SQLite_Schema": "forbidden"},
            }
            conn.execute(
                """
                INSERT INTO career_snapshots
                    (id, snapshot_type, generated_at, content_json, source_version)
                VALUES
                    ('career_snapshot:latest', 'career', '2026-07-08T00:00:00+00:00', ?, 'acs.v1')
                """,
                (json.dumps(dirty_snapshot, ensure_ascii=False),),
            )

            result = career_backend.get_latest_career_snapshot(conn=conn)

            self.assertEqual(result["snapshot"]["summary"]["activity_count"], 1)
            self.assertEqual(result["snapshot"]["records_summary"]["candidate_count"], 2)
            self.assertEqual(
                result["snapshot"]["records_summary"]["trend_inputs"]["interpretation"],
                "frequency_and_curve_availability_only",
            )
            self.assertNotIn("payload", result["snapshot"]["records_summary"]["recent_refreshes"][0])
            self.assertNotIn("representative_memories", result["snapshot"])
            self.assertNotIn("memory_count", result["snapshot"]["summary"])
            _assert_forbidden_absent(self, result)
        finally:
            conn.close()

    def test_snapshot_forbidden_key_guard_is_case_insensitive(self):
        self.assertTrue(
            career_backend._snapshot_has_forbidden_key(
                {
                    "summary": {
                        "File_Path": "/Users/example/private.fit",
                    }
                }
            )
        )
        self.assertTrue(
            career_backend._snapshot_has_forbidden_key(
                {
                    "status": {
                        "SQLite_Schema": "CREATE TABLE secret",
                    }
                }
            )
        )
        self.assertFalse(
            career_backend._snapshot_has_forbidden_key(
                {
                    "summary": {
                        "activity_count": 1,
                    }
                }
            )
        )

    def test_backend_persistence_functions_do_not_call_llm(self):
        for fn in (career_backend.save_career_snapshot, career_backend.get_latest_career_snapshot):
            source = inspect.getsource(fn)
            self.assertNotIn("call_llm", source)
            self.assertNotIn("main.", source)

    def test_main_exposes_only_readonly_snapshot_api(self):
        api = main.Api()
        self.assertTrue(hasattr(api, "get_latest_career_snapshot"))
        self.assertFalse(hasattr(api, "save_career_snapshot"))
        self.assertNotIn("def save_career_snapshot", inspect.getsource(main.Api))

    def test_main_get_latest_career_snapshot_returns_unified_envelope(self):
        original_db_path = profile_backend.DB_PATH
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                profile_backend.DB_PATH = Path(tmpdir) / "career-snapshot-api.sqlite"
                conn = sqlite3.connect(str(profile_backend.DB_PATH))
                try:
                    _seed_snapshot_source(conn)
                    career_backend.save_career_snapshot(conn=conn)
                    conn.commit()
                finally:
                    conn.close()

                response = main.Api().get_latest_career_snapshot()

                self.assertTrue(response["ok"])
                self.assertEqual(response["code"], main.API_CODE_OK)
                self.assertEqual(response["msg"], "ok")
                self.assertIsInstance(response["traceId"], str)
                self.assertEqual(response["data"]["snapshot"]["snapshot_version"], "acs.v1")
                _assert_forbidden_absent(self, response["data"])
            finally:
                profile_backend.DB_PATH = original_db_path

    def test_main_generate_career_insight_commits_snapshot_across_connections(self):
        original_db_path = profile_backend.DB_PATH
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                profile_backend.DB_PATH = Path(tmpdir) / "career-insight-api.sqlite"
                conn = sqlite3.connect(str(profile_backend.DB_PATH))
                try:
                    _seed_snapshot_source(conn)
                    conn.commit()
                finally:
                    conn.close()

                response = main.Api().generate_career_insight({"refresh_snapshot": False})

                self.assertTrue(response["ok"])
                verify = sqlite3.connect(str(profile_backend.DB_PATH))
                try:
                    row = verify.execute(
                        "SELECT snapshot_type FROM career_snapshots WHERE id = 'career_snapshot:latest'"
                    ).fetchone()
                finally:
                    verify.close()
                self.assertEqual(row, ("career",))
            finally:
                profile_backend.DB_PATH = original_db_path

    def test_js_api_contract_registers_readonly_snapshot_api_only(self):
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        methods = {item["name"]: item for item in contract["methods"]}

        self.assertIn("get_latest_career_snapshot", methods)
        self.assertNotIn("save_career_snapshot", methods)
        method = methods["get_latest_career_snapshot"]
        self.assertEqual(method["category"], "career")
        self.assertFalse(method["high_risk"])
        self.assertTrue(method["readonly"])
        self.assertIn("不自动生成", method["description"])
        self.assertIn("不调用 LLM", method["description"])
        self.assertIn("storage_ref", method["description"])


if __name__ == "__main__":
    unittest.main()
