import sqlite3
import tempfile
import unittest
from pathlib import Path

import career_backend
import main
import profile_backend


class TestActivityRaceFlagApi(unittest.TestCase):
    def setUp(self):
        self.temp_dir_obj = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self.temp_dir_obj.name)
        self.original_db_path = profile_backend.DB_PATH
        self.original_profile_schema = profile_backend._SCHEMA_READY_FOR
        self.original_main_schema = main._ACTIVITY_SYNC_SCHEMA_READY_FOR

        profile_backend.DB_PATH = self.temp_dir / "user_profile.db"
        profile_backend._SCHEMA_READY_FOR = None
        main._ACTIVITY_SYNC_SCHEMA_READY_FOR = None
        self.api = main.Api()

    def tearDown(self):
        profile_backend.DB_PATH = self.original_db_path
        profile_backend._SCHEMA_READY_FOR = self.original_profile_schema
        main._ACTIVITY_SYNC_SCHEMA_READY_FOR = self.original_main_schema
        self.temp_dir_obj.cleanup()

    def _insert_activity(self, **overrides) -> int:
        main.ensure_activity_sync_schema()
        conn = profile_backend._conn()
        try:
            data = {
                "filename": "manual-race.fit",
                "file_name": "manual-race.fit",
                "title": "测试活动",
                "title_source": "filename",
                "sport_type": "running",
                "start_time": "2026-05-19T08:00:00+08:00",
                "deleted_at": None,
                "is_race": 0,
                "race_source": None,
                "race_confidence": None,
                "race_override": 0,
            }
            data.update(overrides)
            columns = list(data)
            placeholders = ", ".join("?" for _ in columns)
            cur = conn.execute(
                f"INSERT INTO activities ({', '.join(columns)}) VALUES ({placeholders})",
                [data[column] for column in columns],
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def _insert_active_career_race(self, activity_id: int, source: str = "resolver") -> None:
        conn = profile_backend._conn()
        try:
            career_backend.ensure_career_schema(conn)
            conn.execute(
                """
                INSERT INTO career_race_events
                    (id, activity_id, name, event_type, sport, event_date, location_json,
                     performance_summary_json, achievement_ids_json, confidence, source, status,
                     display_metadata_json, updated_at)
                VALUES
                    (?, ?, '系统识别赛事', 'race', 'running', '2026-05-19', '{}',
                     '{}', '[]', 0.82, ?, 'active',
                     '{"confidence_level":"medium"}', datetime('now'))
                """,
                (f"race:auto:{activity_id}", str(activity_id), source),
            )
            conn.commit()
        finally:
            conn.close()

    def _race_row(self, activity_id: int) -> sqlite3.Row:
        conn = profile_backend._conn()
        try:
            conn.row_factory = sqlite3.Row
            return conn.execute(
                """
                SELECT is_race, race_source, race_confidence, race_override, race_confirmed_at
                FROM activities
                WHERE id = ?
                """,
                (activity_id,),
            ).fetchone()
        finally:
            conn.close()

    def test_manual_mark_race_success(self):
        activity_id = self._insert_activity()

        res = self.api.set_activity_race_flag(activity_id, True)

        self.assertTrue(res["ok"])
        self.assertEqual(res["code"], main.API_CODE_OK)
        self.assertIn("traceId", res)
        data = res["data"]
        self.assertEqual(data["activity_id"], activity_id)
        self.assertTrue(data["is_race"])
        self.assertEqual(data["race_source"], "user")
        self.assertEqual(data["race_confidence"], "high")
        self.assertEqual(data["race_override"], 1)
        self.assertTrue(data["race_confirmed_at"])
        self.assertIn("career_refresh", data)
        self.assertNotIn("record", data)

        row = self._race_row(activity_id)
        self.assertEqual(row["is_race"], 1)
        self.assertEqual(row["race_source"], "user")
        self.assertEqual(row["race_confidence"], "high")
        self.assertEqual(row["race_override"], 1)

    def test_manual_cancel_race_success(self):
        activity_id = self._insert_activity()

        res = self.api.set_activity_race_flag(activity_id, "false")

        self.assertTrue(res["ok"])
        data = res["data"]
        self.assertFalse(data["is_race"])
        self.assertEqual(data["race_source"], "user")
        self.assertEqual(data["race_confidence"], "high")
        self.assertEqual(data["race_override"], 1)

        row = self._race_row(activity_id)
        self.assertEqual(row["is_race"], 0)
        self.assertEqual(row["race_source"], "user")
        self.assertEqual(row["race_override"], 1)

    def test_nonexistent_activity_returns_not_found(self):
        main.ensure_activity_sync_schema()

        res = self.api.set_activity_race_flag(999999, True)

        self.assertFalse(res["ok"])
        self.assertEqual(res["code"], main.API_CODE_NOT_FOUND)
        self.assertIn("traceId", res)

    def test_invalid_activity_id_returns_validation_error(self):
        res = self.api.set_activity_race_flag("bad-id", True)

        self.assertFalse(res["ok"])
        self.assertEqual(res["code"], main.API_CODE_VALIDATION)
        self.assertIn("traceId", res)

    def test_invalid_is_race_returns_validation_error(self):
        activity_id = self._insert_activity()

        res = self.api.set_activity_race_flag(activity_id, "maybe")

        self.assertFalse(res["ok"])
        self.assertEqual(res["code"], main.API_CODE_VALIDATION)
        self.assertIn("traceId", res)

    def test_external_source_is_rejected(self):
        activity_id = self._insert_activity()

        res = self.api.set_activity_race_flag(activity_id, True, source="fit_sport_event")

        self.assertFalse(res["ok"])
        self.assertEqual(res["code"], main.API_CODE_VALIDATION)

    def test_response_does_not_expose_forbidden_fields(self):
        activity_id = self._insert_activity()

        res = self.api.set_activity_race_flag(activity_id, 1)

        self.assertTrue(res["ok"])
        data = res["data"]
        for field in ("points", "track_json", "raw_records", "fit_records", "file_path"):
            self.assertNotIn(field, data)

    def test_activity_list_lights_medal_for_active_system_detected_race(self):
        activity_id = self._insert_activity()
        self._insert_active_career_race(activity_id, source="resolver")

        res = self.api.get_activity_list(page=1, page_size=20)

        self.assertTrue(res["ok"])
        record = next(item for item in res["data"]["records"] if item["id"] == activity_id)
        self.assertTrue(record["is_race"])
        self.assertEqual(record["race_source"], "resolver")
        self.assertTrue(record["career_race_is_active"])
        self.assertEqual(record["career_race_source"], "resolver")

    def test_activity_list_respects_user_cancelled_race_over_active_race_event(self):
        activity_id = self._insert_activity(
            is_race=0,
            race_source="user",
            race_confidence="high",
            race_override=1,
        )
        self._insert_active_career_race(activity_id, source="resolver")

        res = self.api.get_activity_list(page=1, page_size=20)

        self.assertTrue(res["ok"])
        record = next(item for item in res["data"]["records"] if item["id"] == activity_id)
        self.assertFalse(record["is_race"])
        self.assertEqual(record["race_source"], "user")
        self.assertTrue(record["career_race_is_active"])


if __name__ == "__main__":
    unittest.main()
