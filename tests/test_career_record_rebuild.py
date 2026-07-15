import sqlite3
import time
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


class CareerRecordRebuildTest(unittest.TestCase):
    def test_dry_run_outputs_versioned_plan_without_writes(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(conn, id=1)
            _insert_activity(conn, id=2, dist_km=8.0, distance=8000.0)

            plan = career_backend.rebuild_records(conn, dry_run=True, resolver_version="records-v1-test")

            self.assertTrue(plan["ok"])
            self.assertTrue(plan["dry_run"])
            self.assertTrue(plan["run_id"].startswith("records_rebuild:"))
            self.assertEqual(plan["resolver_version"], "records-v1-test")
            self.assertEqual(plan["processed"], 2)
            self.assertEqual(plan["progress"], {"processed": 2, "total": 2})
            self.assertEqual(plan["summary"]["candidate"], 1)
            self.assertEqual(plan["summary"]["ignored"], 1)
            self.assertIn("elapsed_ms", plan["metrics"])
            self.assertIn("reason_counts", plan["metrics"])
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM career_pb_records").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM career_event_candidates").fetchone()[0], 0)
        finally:
            conn.close()

    def test_apply_rebuild_is_idempotent_for_same_evidence(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(conn, id=1)

            first = career_backend.rebuild_records(conn, dry_run=False)
            second = career_backend.rebuild_records(conn, dry_run=False)

            self.assertFalse(first["dry_run"])
            self.assertFalse(second["dry_run"])
            self.assertIn("elapsed_ms", first["metrics"])
            self.assertIn("applied_summary", first["metrics"])
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM career_event_candidates").fetchone()[0], 1)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM career_record_events WHERE event_type = 'candidate_created'").fetchone()[0],
                1,
            )
        finally:
            conn.close()

    def test_apply_failure_rolls_back_and_keeps_existing_active(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            conn.execute(
                """
                INSERT INTO career_pb_records
                    (id, activity_id, sport, pb_type, value, value_unit, event_date,
                     status, evidence_key, source_mode, sport_scope, resolver_version)
                VALUES
                    ('pb:running_5k:legacy', 'legacy', 'running', 'running_5k',
                     '1600', 'seconds', '2026-06-01', 'active',
                     'activity_total:legacy:running_5k:1600', 'activity_total',
                     'default', 'legacy')
                """
            )
            _create_activity_table(conn)
            _insert_activity(conn, id=1)

            with mock.patch.object(career_backend, "apply_record_candidate_decision", side_effect=RuntimeError("boom")):
                with self.assertRaisesRegex(RuntimeError, "boom"):
                    career_backend.rebuild_records(conn, dry_run=False)

            rows = conn.execute("SELECT id, status FROM career_pb_records").fetchall()
            self.assertEqual(rows, [("pb:running_5k:legacy", "active")])
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM career_event_candidates").fetchone()[0], 0)
        finally:
            conn.close()

    def test_rebuild_rejects_reentrant_run(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend._RECORDS_REBUILD_IN_PROGRESS = True

            result = career_backend.rebuild_records(conn, dry_run=True)

            self.assertFalse(result["ok"])
            self.assertEqual(result["code"], "records_rebuild_in_progress")
            self.assertIn("elapsed_ms", result["metrics"])
        finally:
            career_backend._RECORDS_REBUILD_IN_PROGRESS = False
            conn.close()

    def test_record_event_payload_is_recursively_sanitized(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            conn.execute(
                """
                INSERT INTO career_record_events
                    (id, record_id, activity_id, pb_type, event_type, event_at,
                     evidence_key, resolver_version, source, payload_json)
                VALUES
                    ('event:secure', 'pb:1', '1', 'running_5k', 'activated',
                     '2026-07-01T00:00:00+00:00', 'evidence:1', 'records-v1',
                     'resolver',
                     '{"nested":{"track_json":"forbidden","note":"/Users/private/raw.fit","safe":"kept"},"detail_link":{"activity_id":"1"}}')
                """
            )

            result = career_backend.get_career_record_events({"pb_type": "running_5k"}, conn=conn)
            payload = result["events"][0]["payload"]

            self.assertEqual(payload["nested"]["safe"], "kept")
            self.assertEqual(payload["nested"]["note"], "")
            self.assertNotIn("track_json", payload["nested"])
            self.assertNotIn("detail_link", payload)
            self.assertIn("elapsed_ms", result["metrics"])
        finally:
            conn.close()

    def test_rebuild_logs_safe_metrics_without_payload_or_paths(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(conn, id=1)

            with self.assertLogs("career_backend", level="INFO") as captured:
                result = career_backend.rebuild_records(conn, dry_run=True, resolver_version="records-v1-test")

            self.assertTrue(result["ok"])
            joined = "\n".join(captured.output)
            self.assertIn("records_center.rebuild_dry_run", joined)
            self.assertIn("records-v1-test", joined)
            self.assertNotIn("payload_json", joined)
            self.assertNotIn("/Users/", joined)
            self.assertNotIn(".fit", joined)
        finally:
            conn.close()

    def test_rebuild_dry_run_handles_ten_thousand_synthetic_activities(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            rows = [
                (
                    index,
                    "running",
                    "generic",
                    f"2026-07-{(index % 28) + 1:02d}T08:00:00+08:00",
                    f"2026-07-{(index % 28) + 1:02d}T00:00:00Z",
                    5.0 if index % 2 == 0 else 8.0,
                    5000.0 if index % 2 == 0 else 8000.0,
                    1500 + (index % 300),
                    1500 + (index % 300),
                    None,
                    f"2026-07-{(index % 28) + 1:02d}T08:00:00+08:00",
                )
                for index in range(1, 10001)
            ]
            conn.executemany(
                """
                INSERT INTO activities
                    (id, sport_type, sub_sport_type, start_time, start_time_utc,
                     dist_km, distance, duration, duration_sec, deleted_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

            started = time.perf_counter()
            result = career_backend.rebuild_records(conn, dry_run=True, resolver_version="records-v1-perf")
            wall_ms = (time.perf_counter() - started) * 1000.0

            self.assertTrue(result["ok"])
            self.assertEqual(result["processed"], 10000)
            self.assertEqual(result["summary"]["candidate"], 5000)
            self.assertEqual(result["summary"]["ignored"], 5000)
            self.assertLess(result["metrics"]["elapsed_ms"], 8000)
            self.assertLess(wall_ms, 10000)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
