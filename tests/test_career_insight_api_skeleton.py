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
            testcase.assertNotIn(str(key), FORBIDDEN_RESPONSE_KEYS)
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


def _insert_race(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT INTO career_race_events
            (id, activity_id, name, event_type, sport, event_date, location_json,
             performance_summary_json, achievement_ids_json, confidence, source, status, display_metadata_json)
        VALUES
            ('race:1', '1', '2026 北京半程马拉松', 'half_marathon', 'running', '2026-05-19',
             '{"city":"北京"}', '{}', '[]', 1.0, 'resolver', 'active', '{"track_json":"forbidden"}')
        """
    )


def _insert_pb(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT INTO career_pb_records
            (id, activity_id, sport, pb_type, value, value_unit, improvement,
             event_date, confidence, source, status, display_metadata_json)
        VALUES
            ('pb:1', '1', 'running', 'running_5k', '1500', 'seconds', NULL,
             '2026-05-19', 1.0, 'resolver', 'active', '{"file_path":"/tmp/hidden.fit"}')
        """
    )


def _insert_achievement(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT INTO career_achievement_events
            (id, activity_id, achievement_type, title, event_date, score, icon,
             description, confidence, source, status, display_metadata_json)
        VALUES
            ('achievement:1', '1', 'first_running_5k', '首次跑完 5K', '2026-05-19',
             70, 'flag', '首次跑完 5K', 1.0, 'resolver', 'active', '{"points_json":"forbidden"}')
        """
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


def _seed_career_data(conn: sqlite3.Connection) -> None:
    _create_activities_table(conn)
    career_backend.ensure_career_schema(conn)
    _insert_activity(conn)
    _insert_race(conn)
    _insert_pb(conn)
    _insert_achievement(conn)
    _insert_memory(conn)


def _canonical_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        "races": conn.execute("SELECT COUNT(*) FROM career_race_events").fetchone()[0],
        "pb": conn.execute("SELECT COUNT(*) FROM career_pb_records").fetchone()[0],
        "achievements": conn.execute("SELECT COUNT(*) FROM career_achievement_events").fetchone()[0],
        "memories": conn.execute("SELECT COUNT(*) FROM career_memory_items").fetchone()[0],
    }


class TestCareerInsightApiSkeleton(unittest.TestCase):
    def test_generates_and_saves_snapshot_when_missing(self):
        conn = sqlite3.connect(":memory:")
        try:
            _seed_career_data(conn)

            result = career_backend.generate_career_insight(conn=conn)
            snapshot_count = conn.execute("SELECT COUNT(*) FROM career_snapshots").fetchone()[0]

            self.assertEqual(snapshot_count, 1)
            self.assertEqual(result["insight"]["mode"], "fallback")
            self.assertEqual(result["snapshot_status"]["source"], "generated")
            self.assertEqual(result["snapshot_status"]["snapshot_version"], "acs.v1")
            self.assertTrue(result["snapshot_status"]["available"])
            self.assertTrue(result["status"]["data_ready"])
            _assert_forbidden_absent(self, result)
        finally:
            conn.close()

    def test_uses_saved_snapshot_without_growing_rows_when_refresh_false(self):
        conn = sqlite3.connect(":memory:")
        try:
            _seed_career_data(conn)
            career_backend.save_career_snapshot(conn=conn)

            result = career_backend.generate_career_insight({"refresh_snapshot": False}, conn=conn)
            snapshot_count = conn.execute("SELECT COUNT(*) FROM career_snapshots").fetchone()[0]

            self.assertEqual(snapshot_count, 1)
            self.assertEqual(result["snapshot_status"]["source"], "saved")
            self.assertTrue(result["status"]["data_ready"])
            _assert_forbidden_absent(self, result)
        finally:
            conn.close()

    def test_refresh_snapshot_updates_latest_without_creating_extra_rows(self):
        conn = sqlite3.connect(":memory:")
        try:
            _seed_career_data(conn)
            career_backend.save_career_snapshot(conn=conn)
            conn.execute(
                """
                UPDATE career_snapshots
                SET content_json = ?
                WHERE id = 'career_snapshot:latest'
                """,
                (json.dumps({"snapshot_version": "old", "summary": {"activity_count": 0}}, ensure_ascii=False),),
            )

            result = career_backend.generate_career_insight({"refresh_snapshot": True}, conn=conn)
            snapshot_count = conn.execute("SELECT COUNT(*) FROM career_snapshots").fetchone()[0]
            saved = career_backend.get_latest_career_snapshot(conn=conn)

            self.assertEqual(snapshot_count, 1)
            self.assertEqual(result["snapshot_status"]["source"], "refreshed")
            self.assertEqual(saved["snapshot"]["snapshot_version"], "acs.v1")
            self.assertEqual(saved["snapshot"]["summary"]["activity_count"], 1)
            _assert_forbidden_absent(self, result)
        finally:
            conn.close()

    def test_fallback_insight_shape_and_highlights_use_summary_only(self):
        conn = sqlite3.connect(":memory:")
        try:
            _seed_career_data(conn)

            result = career_backend.generate_career_insight(conn=conn)
            insight = result["insight"]

            self.assertEqual(set(insight), {"mode", "title", "summary", "highlights", "next_steps", "disclaimer"})
            self.assertEqual(insight["mode"], "fallback")
            self.assertIn("不调用 AI", insight["disclaimer"])
            self.assertIn("累计活动 1 次", insight["highlights"])
            self.assertIn("已记录赛事 1 场", insight["highlights"])
            self.assertIn("已沉淀 PB 1 项", insight["highlights"])
            self.assertIn("已获得成就 1 项", insight["highlights"])
            self.assertIn("已沉淀记忆 1 条", insight["highlights"])
            self.assertNotIn("最后三公里", " ".join(insight["highlights"]))
            _assert_forbidden_absent(self, result)
        finally:
            conn.close()

    def test_empty_database_returns_stable_low_data_fallback(self):
        conn = sqlite3.connect(":memory:")
        try:
            result = career_backend.generate_career_insight(conn=conn)

            self.assertEqual(result["insight"]["mode"], "fallback")
            self.assertFalse(result["status"]["data_ready"])
            self.assertEqual(result["snapshot_status"]["source"], "generated")
            self.assertIn("暂无足够", result["insight"]["highlights"][0])
            _assert_forbidden_absent(self, result)
        finally:
            conn.close()

    def test_rejects_unknown_payload_keys(self):
        conn = sqlite3.connect(":memory:")
        try:
            with self.assertRaisesRegex(ValueError, "仅支持 refresh_snapshot"):
                career_backend.generate_career_insight({"prompt": "bad"}, conn=conn)
        finally:
            conn.close()

    def test_does_not_call_llm_or_llm_backend(self):
        source = inspect.getsource(career_backend.generate_career_insight)
        self.assertNotIn("call_llm", source)
        self.assertNotIn("llm_backend", source)
        self.assertNotIn("main.", source)

    def test_does_not_write_canonical_fact_tables(self):
        conn = sqlite3.connect(":memory:")
        try:
            _seed_career_data(conn)
            before = _canonical_counts(conn)

            career_backend.generate_career_insight(conn=conn)
            after = _canonical_counts(conn)

            self.assertEqual(after, before)
        finally:
            conn.close()

    def test_main_api_generate_career_insight_returns_unified_envelope(self):
        original_db_path = profile_backend.DB_PATH
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                profile_backend.DB_PATH = Path(tmpdir) / "career-insight-api.sqlite"
                conn = sqlite3.connect(str(profile_backend.DB_PATH))
                try:
                    _seed_career_data(conn)
                    conn.commit()
                finally:
                    conn.close()

                response = main.Api().generate_career_insight({"refresh_snapshot": False})

                self.assertTrue(response["ok"])
                self.assertEqual(response["code"], main.API_CODE_OK)
                self.assertEqual(response["msg"], "ok")
                self.assertEqual(response["data"]["insight"]["mode"], "fallback")
                self.assertTrue(response["data"]["snapshot_status"]["available"])
                _assert_forbidden_absent(self, response["data"])
            finally:
                profile_backend.DB_PATH = original_db_path

    def test_main_validation_error_for_unknown_payload(self):
        response = main.Api().generate_career_insight({"prompt": "bad"})

        self.assertFalse(response["ok"])
        self.assertEqual(response["code"], main.API_CODE_VALIDATION)

    def test_js_api_contract_registers_generate_career_insight(self):
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        methods = {item["name"]: item for item in contract["methods"]}

        self.assertIn("generate_career_insight", methods)
        method = methods["generate_career_insight"]
        self.assertEqual(method["category"], "career")
        self.assertFalse(method["high_risk"])
        self.assertFalse(method["readonly"])
        self.assertIn("fallback", method["description"])
        self.assertIn("不调用 LLM", method["description"])
        self.assertIn("Career Snapshot", method["description"])
        self.assertIn("career_snapshots", method["description"])
        self.assertIn("canonical", method["description"])


if __name__ == "__main__":
    unittest.main()
