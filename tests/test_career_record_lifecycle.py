import sqlite3
import unittest
from unittest import mock

import career_backend


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


def _insert_activity(conn: sqlite3.Connection, activity_id: int, dist_km: float, duration: int) -> None:
    conn.execute(
        """
        INSERT INTO activities
            (id, sport_type, sub_sport_type, start_time, start_time_utc, dist_km,
             distance, duration, duration_sec, deleted_at, updated_at)
        VALUES
            (?, 'running', 'generic', '2026-07-01T08:00:00+08:00',
             '2026-07-01T00:00:00Z', ?, ?, ?, ?, NULL, '2026-07-01T08:00:00+08:00')
        """,
        (activity_id, dist_km, dist_km * 1000, duration, duration),
    )


def _record_decision(conn: sqlite3.Connection, activity_id: int, elapsed_time_sec: int) -> dict:
    row = career_backend._fetch_pb_resolver_activity_row(conn, activity_id)
    summary = career_backend._record_performance_summary(row)
    summary["time_quality"] = "reliable_elapsed"
    summary["elapsed_time_sec"] = elapsed_time_sec
    match = career_backend.match_record_definition(summary)
    return career_backend.build_record_candidate_decision(summary, match)


class CareerRecordLifecycleTest(unittest.TestCase):
    def test_deleted_active_activity_invalidates_and_promotes_best_valid_fallback(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(conn, 1, 5.0, 1500)
            _insert_activity(conn, 2, 5.0, 1450)
            career_backend.apply_record_candidate_decision(conn, _record_decision(conn, 1, 1500))
            career_backend.apply_record_candidate_decision(conn, _record_decision(conn, 2, 1450))
            conn.execute("UPDATE activities SET deleted_at = '2026-07-02T00:00:00Z' WHERE id = 2")

            result = career_backend.repair_record_lifecycle(conn)

            self.assertEqual(len(result["invalidated"]), 1)
            self.assertEqual(len(result["promoted"]), 1)
            rows = conn.execute(
                "SELECT activity_id, status FROM career_pb_records ORDER BY activity_id"
            ).fetchall()
            self.assertEqual(rows, [("1", "active"), ("2", "invalidated")])
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM career_pb_records WHERE status = 'active'").fetchone()[0],
                1,
            )
            self.assertIn(
                "activated_from_rebuild",
                [row[0] for row in conn.execute("SELECT event_type FROM career_record_events").fetchall()],
            )
        finally:
            conn.close()

    def test_activity_evidence_change_invalidates_without_false_new_record(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(conn, 1, 5.0, 1500)
            career_backend.apply_record_candidate_decision(conn, _record_decision(conn, 1, 1500))
            conn.execute("UPDATE activities SET dist_km = 8.0, distance = 8000.0 WHERE id = 1")

            result = career_backend.repair_record_lifecycle(conn)

            self.assertEqual(len(result["invalidated"]), 1)
            self.assertEqual(result["promoted"], [])
            self.assertEqual(
                conn.execute("SELECT status FROM career_pb_records WHERE activity_id = '1'").fetchone()[0],
                "invalidated",
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM career_record_events WHERE event_type = 'activated'").fetchone()[0],
                1,
            )
        finally:
            conn.close()

    def test_lifecycle_repair_is_idempotent_for_same_invalidated_record(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(conn, 1, 5.0, 1500)
            career_backend.apply_record_candidate_decision(conn, _record_decision(conn, 1, 1500))
            conn.execute("UPDATE activities SET deleted_at = '2026-07-02T00:00:00Z' WHERE id = 1")

            career_backend.repair_record_lifecycle(conn)
            career_backend.repair_record_lifecycle(conn)

            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM career_record_events WHERE event_type = 'invalidated'").fetchone()[0],
                1,
            )
        finally:
            conn.close()

    def test_lifecycle_repair_failure_rolls_back_active_status(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(conn, 1, 5.0, 1500)
            career_backend.apply_record_candidate_decision(conn, _record_decision(conn, 1, 1500))
            conn.execute("UPDATE activities SET deleted_at = '2026-07-02T00:00:00Z' WHERE id = 1")

            with mock.patch.object(career_backend, "_insert_record_event", side_effect=RuntimeError("boom")):
                with self.assertRaisesRegex(RuntimeError, "boom"):
                    career_backend.repair_record_lifecycle(conn)

            self.assertEqual(
                conn.execute("SELECT status FROM career_pb_records WHERE activity_id = '1'").fetchone()[0],
                "active",
            )
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()

