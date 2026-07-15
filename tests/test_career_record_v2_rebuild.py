import sqlite3
import unittest
from unittest import mock

import career_backend


def _create_activities(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY,
            sport_type TEXT,
            sub_sport_type TEXT,
            deleted_at TEXT,
            updated_at TEXT
        )
        """
    )


def _insert_activity(conn: sqlite3.Connection, activity_id: int, sport: str, *, deleted_at: str | None = None) -> None:
    conn.execute(
        """
        INSERT INTO activities (id, sport_type, sub_sport_type, deleted_at, updated_at)
        VALUES (?, ?, '', ?, '2026-07-14T00:00:00Z')
        """,
        (activity_id, sport, deleted_at),
    )


def _cycling_distance_evidence(activity_id: int, distance_m: int):
    return career_backend.build_record_evidence(
        record_key="cycling_longest_distance",
        activity_id=str(activity_id),
        sport="cycling",
        source_mode="activity_total",
        metric_name="distance_m",
        metric_value=distance_m,
        metric_unit="meters",
        event_date="2026-07-14",
        scope={"sport_scope": "outdoor"},
        quality={"confidence": 0.99, "reason_codes": ["metric_quality_ok"]},
        resolver_version="records-v2-test",
    )


class CareerRecordV2RebuildTest(unittest.TestCase):
    def test_dispatch_plan_uses_available_definitions_only(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activities(conn)
            _insert_activity(conn, 1, "cycling")
            _insert_activity(conn, 2, "trail_running")
            _insert_activity(conn, 3, "cycling", deleted_at="2026-07-14T01:00:00Z")

            cycling = career_backend.plan_activity_record_v2_dispatch(conn, 1)
            trail = career_backend.plan_activity_record_v2_dispatch(conn, 2)
            deleted = career_backend.plan_activity_record_v2_dispatch(conn, 3)

            self.assertEqual(cycling["action"], "dispatch_planned")
            keys = {item["record_key"] for item in cycling["definitions"]}
            self.assertIn("cycling_longest_distance", keys)
            self.assertNotIn("cycling_max_work", keys)
            self.assertEqual(trail["action"], "ignored")
            self.assertEqual(trail["reason"], "no_available_definitions")
            self.assertEqual(deleted["reason"], "activity_not_found_or_deleted")
        finally:
            conn.close()

    def test_v2_rebuild_dry_run_is_read_only_and_summarized(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activities(conn)
            _insert_activity(conn, 1, "cycling")
            _insert_activity(conn, 2, "hiking")
            career_backend.ensure_career_schema(conn)
            before_records = conn.execute("SELECT COUNT(*) FROM career_pb_records").fetchone()[0]
            before_events = conn.execute("SELECT COUNT(*) FROM career_record_events").fetchone()[0]

            plan = career_backend.rebuild_career_records_v2(conn, dry_run=True)

            self.assertTrue(plan["dry_run"])
            self.assertTrue(plan["run_id"].startswith("records_v2_rebuild:"))
            self.assertEqual(plan["processed"], 2)
            self.assertGreater(plan["by_sport"]["cycling"], 0)
            self.assertIn("activity_total_record", plan["by_family"])
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM career_pb_records").fetchone()[0], before_records)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM career_record_events").fetchone()[0], before_events)
        finally:
            conn.close()

    def test_v2_rebuild_batch_cancel_and_apply_shell(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activities(conn)
            for activity_id in range(1, 6):
                _insert_activity(conn, activity_id, "cycling")

            cancelled = career_backend.plan_career_records_v2_rebuild(conn, batch_size=2, cancel_after=3)
            applied = career_backend.rebuild_career_records_v2(conn, dry_run=False, max_activities=2)

            self.assertTrue(cancelled["cancelled"])
            self.assertEqual(cancelled["processed"], 3)
            self.assertFalse(applied["dry_run"])
            self.assertEqual(applied["applied_count"], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM career_pb_records").fetchone()[0], 0)
        finally:
            conn.close()

    def test_activity_invalidation_updates_record_cache_and_promotes_fallback(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activities(conn)
            _insert_activity(conn, 1, "cycling")
            _insert_activity(conn, 2, "cycling")
            career_backend.apply_record_evidence_state(conn, _cycling_distance_evidence(1, 100000))
            career_backend.apply_record_evidence_state(conn, _cycling_distance_evidence(2, 105000))
            fingerprint = career_backend.compute_career_record_curve_input_fingerprint(
                activity_id="2",
                sport="cycling",
                source_mode="activity_total",
                canonical_facts_version="facts:v1",
                stream_summary_hash="summary:v1",
                algorithm_version="curve:v1",
                rule_version="records-v2",
                scope={"sport_scope": "outdoor"},
            )
            career_backend.save_career_record_curve_cache(
                activity_id="2",
                sport="cycling",
                curve_type="cycling_power_duration_curve",
                source_mode="activity_total",
                scope={"sport_scope": "outdoor"},
                input_fingerprint=fingerprint,
                algorithm_version="curve:v1",
                curve={"anchors": [{"duration_sec": 60, "value": 200}]},
                conn=conn,
            )
            dry = career_backend.invalidate_career_record_state_for_activity(conn, 2, reason="activity_deleted", dry_run=True)
            applied = career_backend.invalidate_career_record_state_for_activity(conn, 2, reason="activity_deleted", dry_run=False)

            self.assertEqual(dry["would_invalidate_records"], [applied["invalidated"][0]])
            self.assertEqual(len(dry["would_promote"]), 1)
            self.assertEqual(dry["would_invalidate_cache"], 1)
            active = conn.execute("SELECT activity_id, status FROM career_pb_records WHERE status = 'active'").fetchall()
            invalidated = conn.execute("SELECT activity_id, status FROM career_pb_records WHERE status = 'invalidated'").fetchall()
            self.assertEqual(active, [("1", "active")])
            self.assertEqual(invalidated, [("2", "invalidated")])
            self.assertEqual(applied["invalidated_cache"], 1)
            self.assertNotIn("route_cache", applied)
            self.assertNotIn("route_matches", applied)
        finally:
            conn.close()

    def test_activity_invalidation_rolls_back_on_failure(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activities(conn)
            _insert_activity(conn, 1, "cycling")
            career_backend.apply_record_evidence_state(conn, _cycling_distance_evidence(1, 100000))

            with mock.patch.object(career_backend, "invalidate_career_record_curve_cache", side_effect=RuntimeError("boom")):
                with self.assertRaisesRegex(RuntimeError, "boom"):
                    career_backend.invalidate_career_record_state_for_activity(conn, 1, dry_run=False)

            self.assertEqual(
                conn.execute("SELECT activity_id, status FROM career_pb_records").fetchall(),
                [("1", "active")],
            )
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM career_record_events WHERE event_type = 'invalidated'").fetchone()[0], 0)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
