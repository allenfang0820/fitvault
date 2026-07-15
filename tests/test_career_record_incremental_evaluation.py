import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import career_backend
import main
import profile_backend


def _create_activity_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY,
            sport_type TEXT,
            sub_sport_type TEXT,
            start_time TEXT,
            start_time_utc TEXT,
            dist_km REAL,
            distance REAL,
            duration INTEGER,
            duration_sec INTEGER,
            deleted_at TEXT,
            updated_at TEXT
        )
        """
    )


def _insert_activity(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": 1,
        "sport_type": "running",
        "sub_sport_type": "generic",
        "start_time": "2026-07-01T08:00:00+08:00",
        "start_time_utc": "2026-07-01T00:00:00Z",
        "dist_km": 5.0,
        "distance": 5000.0,
        "duration": 1500,
        "duration_sec": 1500,
        "deleted_at": None,
        "updated_at": "2026-07-01T08:00:00+08:00",
    }
    data.update(overrides)
    columns = list(data)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO activities ({', '.join(columns)}) VALUES ({placeholders})",
        [data[column] for column in columns],
    )


class CareerRecordIncrementalEvaluationTest(unittest.TestCase):
    def test_activity_increment_creates_idempotent_candidate_from_current_timer_semantics(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(conn, id=1)

            first = career_backend.evaluate_activity_record_increment(conn, 1)
            second = career_backend.evaluate_activity_record_increment(conn, 1)

            self.assertEqual(first["action"], "candidate_created")
            self.assertEqual(second["action"], "candidate_created")
            self.assertEqual(first["record_key"], "running_5k")
            self.assertIn("elapsed_ms", first["metrics"])
            self.assertIn("elapsed_ms", second["metrics"])
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM career_event_candidates").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM career_pb_records").fetchone()[0], 0)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM career_record_events WHERE event_type = 'candidate_created'").fetchone()[0],
                1,
            )
        finally:
            conn.close()

    def test_activity_increment_ignores_missing_or_deleted_activity(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(conn, id=1, deleted_at="2026-07-02T00:00:00Z")

            result = career_backend.evaluate_activity_record_increment(conn, 1)

            self.assertEqual(result["action"], "ignored")
            self.assertEqual(result["reason"], "activity_not_found_or_deleted")
            self.assertIn("elapsed_ms", result["metrics"])
        finally:
            conn.close()

    def test_import_refresh_uses_incremental_record_evaluation_and_skips_legacy_pb_full_refresh(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "profile.db")
            with mock.patch.object(profile_backend, "DB_PATH", db_path), \
                    mock.patch.object(main.profile_backend, "DB_PATH", db_path), \
                    mock.patch.object(career_backend, "evaluate_activity_record_increment", return_value={
                        "ok": True,
                        "activity_id": "42",
                        "action": "candidate_created",
                    }) as incremental, \
                    mock.patch.object(career_backend, "refresh_career_derived_events", return_value={
                        "ok": True,
                        "status": {"message": "ok"},
                    }) as refresh:

                result = main._refresh_career_derived_events_safe("single_fit_sync", activity_id=42)

            self.assertTrue(result["ok"])
            self.assertEqual(result["record_increment"]["activity_id"], "42")
            incremental.assert_called_once()
            refresh.assert_called_once_with(include_pb=False)


if __name__ == "__main__":
    unittest.main()
