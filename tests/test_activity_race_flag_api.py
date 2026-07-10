import sqlite3
import tempfile
import unittest
from pathlib import Path

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

    def _insert_activity(self) -> int:
        main.ensure_activity_sync_schema()
        conn = profile_backend._conn()
        try:
            cur = conn.execute(
                """
                INSERT INTO activities
                    (filename, file_name, title, title_source, sport_type, start_time, deleted_at,
                     is_race, race_source, race_confidence, race_override)
                VALUES
                    ('manual-race.fit', 'manual-race.fit', '测试活动', 'filename', 'running',
                     '2026-05-19T08:00:00+08:00', NULL, 0, NULL, NULL, 0)
                """
            )
            conn.commit()
            return int(cur.lastrowid)
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


if __name__ == "__main__":
    unittest.main()
