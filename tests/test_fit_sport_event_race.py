import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import main
import profile_backend


class TestFitSportEventRace(unittest.TestCase):
    def setUp(self):
        self.temp_dir_obj = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self.temp_dir_obj.name)
        self.original_db_path = profile_backend.DB_PATH
        self.original_profile_schema = profile_backend._SCHEMA_READY_FOR
        self.original_main_schema = main._ACTIVITY_SYNC_SCHEMA_READY_FOR

        profile_backend.DB_PATH = self.temp_dir / "user_profile.db"
        profile_backend._SCHEMA_READY_FOR = None
        main._ACTIVITY_SYNC_SCHEMA_READY_FOR = None

    def tearDown(self):
        profile_backend.DB_PATH = self.original_db_path
        profile_backend._SCHEMA_READY_FOR = self.original_profile_schema
        main._ACTIVITY_SYNC_SCHEMA_READY_FOR = self.original_main_schema
        self.temp_dir_obj.cleanup()

    def _fake_core(self, sport_event=None):
        basic = {
            "title": "测试跑步",
            "title_source": "sport_name",
            "sport": "running",
            "sub_sport": "generic",
            "start_time": "2026-05-19T08:00:00+08:00",
            "start_time_utc": "2026-05-19T00:00:00Z",
            "total_distance_km": 10.0,
            "total_timer_time": 3600,
            "total_calories": 600,
            "avg_hr": 150,
            "max_hr": 175,
        }
        if sport_event is not None:
            basic["sport_event"] = sport_event
        return {
            "basic_info": basic,
            "track_data": [
                {"time": "2026-05-19T00:00:00Z", "hr": 140},
                {"time": "2026-05-19T00:05:00Z", "hr": 150},
            ],
            "lap_data": [],
        }

    def _parse_activity(self, sport_event=None):
        fit_path = self.temp_dir / "race.fit"
        fit_path.write_bytes(b"fit")
        with mock.patch.object(main.FITCoreEngine, "parse_fit_file", return_value=self._fake_core(sport_event)), \
             mock.patch.object(main.FITCoreEngine, "parse_fit_file_raw", return_value={"raw": {}, "meta": {}}), \
             mock.patch.object(main.MetricsResolver, "resolve", return_value={}):
            return main._parse_fit_activity_for_sync(fit_path)

    def _connect(self):
        main.ensure_activity_sync_schema()
        conn = profile_backend._conn()
        conn.row_factory = sqlite3.Row
        return conn

    def test_string_race_sport_event_sets_is_race(self):
        activity = self._parse_activity("race")

        self.assertEqual(activity["sport_event"], "race")
        self.assertEqual(activity["is_race"], 1)

    def test_numeric_race_sport_event_sets_is_race(self):
        activity = self._parse_activity(4)

        self.assertEqual(activity["sport_event"], 4)
        self.assertEqual(activity["is_race"], 1)

    def test_missing_or_other_sport_event_is_not_race(self):
        missing = self._parse_activity(None)
        training = self._parse_activity("training")

        self.assertNotIn("raw_records", missing)
        self.assertNotIn("fit_records", missing)
        self.assertEqual(missing["is_race"], 0)
        self.assertEqual(training["sport_event"], "training")
        self.assertEqual(training["is_race"], 0)

    def test_insert_and_update_activity_sync_row_persist_is_race_source(self):
        activity = self._parse_activity("training")
        conn = self._connect()
        try:
            activity_id = main._insert_activity_sync_row(conn, activity)
            row = conn.execute(
                "SELECT is_race, race_source, race_confidence, race_override FROM activities WHERE id = ?",
                (activity_id,),
            ).fetchone()
            self.assertEqual(row["is_race"], 0)
            self.assertIsNone(row["race_source"])
            self.assertIsNone(row["race_confidence"])
            self.assertEqual(row["race_override"], 0)

            race_activity = dict(activity)
            race_activity["sport_event"] = "race"
            race_activity["is_race"] = 1
            main._update_activity_sync_row(conn, activity_id, race_activity)

            row = conn.execute(
                "SELECT is_race, race_source, race_confidence, race_override, race_confirmed_at FROM activities WHERE id = ?",
                (activity_id,),
            ).fetchone()
            self.assertEqual(row["is_race"], 1)
            self.assertEqual(row["race_source"], "fit_sport_event")
            self.assertEqual(row["race_confidence"], "high")
            self.assertEqual(row["race_override"], 0)
            self.assertTrue(row["race_confirmed_at"])
        finally:
            conn.close()

    def test_fit_sync_does_not_overwrite_user_confirmed_race(self):
        activity = self._parse_activity("training")
        conn = self._connect()
        try:
            activity_id = main._insert_activity_sync_row(conn, activity)
            conn.execute(
                """
                UPDATE activities
                SET is_race = 1,
                    race_source = 'user',
                    race_confidence = 'high',
                    race_override = 1,
                    race_confirmed_at = datetime('now')
                WHERE id = ?
                """,
                (activity_id,),
            )

            main._update_activity_sync_row(conn, activity_id, activity)

            row = conn.execute(
                "SELECT is_race, race_source, race_confidence, race_override FROM activities WHERE id = ?",
                (activity_id,),
            ).fetchone()
            self.assertEqual(row["is_race"], 1)
            self.assertEqual(row["race_source"], "user")
            self.assertEqual(row["race_confidence"], "high")
            self.assertEqual(row["race_override"], 1)
        finally:
            conn.close()

    def test_fit_sync_does_not_overwrite_user_cancelled_race(self):
        activity = self._parse_activity("race")
        conn = self._connect()
        try:
            activity_id = main._insert_activity_sync_row(conn, activity)
            conn.execute(
                """
                UPDATE activities
                SET is_race = 0,
                    race_source = 'user',
                    race_confidence = 'high',
                    race_override = 1,
                    race_confirmed_at = datetime('now')
                WHERE id = ?
                """,
                (activity_id,),
            )

            main._update_activity_sync_row(conn, activity_id, activity)

            row = conn.execute(
                "SELECT is_race, race_source, race_confidence, race_override FROM activities WHERE id = ?",
                (activity_id,),
            ).fetchone()
            self.assertEqual(row["is_race"], 0)
            self.assertEqual(row["race_source"], "user")
            self.assertEqual(row["race_confidence"], "high")
            self.assertEqual(row["race_override"], 1)
        finally:
            conn.close()

    def test_schema_migration_keeps_is_race_idempotent(self):
        for _ in range(3):
            main.ensure_activity_sync_schema()

        conn = profile_backend._conn()
        try:
            rows = conn.execute("PRAGMA table_info(activities)").fetchall()
            column_names = [row[1] for row in rows]
            for column in ("is_race", "race_source", "race_confirmed_at", "race_confidence", "race_override"):
                self.assertEqual(column_names.count(column), 1)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
