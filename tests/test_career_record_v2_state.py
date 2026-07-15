import sqlite3
import unittest

import career_backend


def _evidence(
    *,
    record_key="cycling_longest_distance",
    activity_id="activity-1",
    sport="cycling",
    source_mode="activity_total",
    metric_name="distance_m",
    metric_value=100000,
    metric_unit="meters",
    scope=None,
    range_data=None,
    quality=None,
):
    return career_backend.build_record_evidence(
        record_key=record_key,
        activity_id=activity_id,
        sport=sport,
        source_mode=source_mode,
        metric_name=metric_name,
        metric_value=metric_value,
        metric_unit=metric_unit,
        event_date="2026-07-14",
        scope=scope or {"sport_scope": "outdoor"},
        range_data=range_data or {},
        quality=quality or {"confidence": 0.98, "reason_codes": ["metric_quality_ok"]},
        resolver_version="records-v2-test",
    )


def _active_rows(conn: sqlite3.Connection):
    return conn.execute(
        """
        SELECT id, activity_id, record_key, source_mode, scope_key, scope_hash,
               metric_value_num, status, previous_record_id
        FROM career_pb_records
        WHERE status = 'active'
        ORDER BY record_key, source_mode, scope_key, metric_value_num
        """
    ).fetchall()


class CareerRecordV2StateTest(unittest.TestCase):
    def test_higher_is_better_same_scope_replaces_previous_active(self):
        conn = sqlite3.connect(":memory:")
        try:
            first = _evidence(activity_id="activity-1", metric_value=100000)
            better = _evidence(activity_id="activity-2", metric_value=105000)
            worse = _evidence(activity_id="activity-3", metric_value=90000)

            first_result = career_backend.apply_record_evidence_state(conn, first)
            better_result = career_backend.apply_record_evidence_state(conn, better)
            worse_result = career_backend.apply_record_evidence_state(conn, worse)

            self.assertEqual(first_result["action"], "activated")
            self.assertEqual(better_result["action"], "activated")
            self.assertEqual(worse_result["action"], "unchanged")
            active = _active_rows(conn)
            superseded = conn.execute("SELECT COUNT(*) FROM career_pb_records WHERE status = 'superseded'").fetchone()[0]
            self.assertEqual(len(active), 1)
            self.assertEqual(active[0][1], "activity-2")
            self.assertEqual(active[0][6], 105000)
            self.assertEqual(superseded, 1)
            self.assertEqual(better_result["comparison"]["improvement"], 5000)
        finally:
            conn.close()

    def test_different_scopes_do_not_replace_each_other(self):
        conn = sqlite3.connect(":memory:")
        try:
            outdoor = _evidence(
                record_key="cycling_power_5s",
                activity_id="outdoor",
                source_mode="best_effort_duration",
                metric_name="power_w",
                metric_value=600,
                metric_unit="watts",
                scope={"sport_scope": "outdoor"},
                range_data={"start_sec": 1, "end_sec": 6, "duration_sec": 5},
            )
            indoor = _evidence(
                record_key="cycling_power_5s",
                activity_id="indoor",
                source_mode="best_effort_duration",
                metric_name="power_w",
                metric_value=580,
                metric_unit="watts",
                scope={"sport_scope": "indoor", "indoor_scope": "trainer"},
                range_data={"start_sec": 2, "end_sec": 7, "duration_sec": 5},
            )

            career_backend.apply_record_evidence_state(conn, outdoor)
            career_backend.apply_record_evidence_state(conn, indoor)

            active = _active_rows(conn)
            self.assertEqual(len(active), 2)
            self.assertEqual({row[4] for row in active}, {"outdoor", "trainer"})
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM career_pb_records WHERE status = 'superseded'").fetchone()[0], 0)
        finally:
            conn.close()

    def test_lower_is_better_tie_and_slower_do_not_replace(self):
        conn = sqlite3.connect(":memory:")
        try:
            first = _evidence(
                record_key="running_5k",
                activity_id="run-1",
                sport="running",
                metric_name="elapsed_time_sec",
                metric_value=1500,
                metric_unit="seconds",
            )
            tie = _evidence(
                record_key="running_5k",
                activity_id="run-2",
                sport="running",
                metric_name="elapsed_time_sec",
                metric_value=1500,
                metric_unit="seconds",
            )
            slower = _evidence(
                record_key="running_5k",
                activity_id="run-3",
                sport="running",
                metric_name="elapsed_time_sec",
                metric_value=1600,
                metric_unit="seconds",
            )

            career_backend.apply_record_evidence_state(conn, first)
            tie_result = career_backend.apply_record_evidence_state(conn, tie)
            slower_result = career_backend.apply_record_evidence_state(conn, slower)

            self.assertEqual(tie_result["action"], "unchanged")
            self.assertTrue(tie_result["comparison"]["is_tie"])
            self.assertEqual(slower_result["action"], "unchanged")
            active = _active_rows(conn)
            self.assertEqual(len(active), 1)
            self.assertEqual(active[0][1], "run-1")
        finally:
            conn.close()

    def test_candidate_reject_is_idempotent_and_same_evidence_not_reprompted(self):
        conn = sqlite3.connect(":memory:")
        try:
            candidate_evidence = _evidence(
                record_key="cycling_power_5s",
                source_mode="best_effort_duration",
                metric_name="power_w",
                metric_value=600,
                metric_unit="watts",
                range_data={"start_sec": 1, "end_sec": 6, "duration_sec": 5},
                quality={"confidence": 0.8, "reason_codes": ["duration_semantics_unknown"]},
            )

            first = career_backend.apply_record_evidence_state(conn, candidate_evidence)
            career_backend.decide_career_record_v2_candidate(first["candidate_id"], "reject", conn=conn)
            second = career_backend.apply_record_evidence_state(conn, candidate_evidence)

            self.assertEqual(first["candidate_id"], second["candidate_id"])
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM career_event_candidates").fetchone()[0], 1)
            self.assertEqual(
                conn.execute("SELECT status FROM career_event_candidates WHERE id = ?", (first["candidate_id"],)).fetchone()[0],
                "rejected",
            )
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM career_pb_records").fetchone()[0], 0)
        finally:
            conn.close()

    def test_validation_required_registry_caps_high_confidence_to_candidate(self):
        conn = sqlite3.connect(":memory:")
        try:
            evidence = _evidence(
                record_key="cycling_max_work",
                activity_id="work-1",
                source_mode="activity_total",
                metric_name="work_kj",
                metric_value=2200,
                metric_unit="kilojoules",
                quality={"confidence": 0.99, "reason_codes": ["metric_quality_ok"]},
            )

            result = career_backend.apply_record_evidence_state(conn, evidence)

            self.assertEqual(result["action"], "candidate_created")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM career_pb_records").fetchone()[0], 0)
            candidate_payload = conn.execute(
                "SELECT evidence_json FROM career_event_candidates WHERE id = ?",
                (result["candidate_id"],),
            ).fetchone()[0]
            self.assertIn("validation_required_registry", candidate_payload)
        finally:
            conn.close()

    def test_confirmed_candidate_rejoins_scoped_comparison(self):
        conn = sqlite3.connect(":memory:")
        try:
            active = _evidence(
                record_key="cycling_power_5s",
                activity_id="active",
                source_mode="best_effort_duration",
                metric_name="power_w",
                metric_value=600,
                metric_unit="watts",
                range_data={"start_sec": 1, "end_sec": 6, "duration_sec": 5},
            )
            candidate = _evidence(
                record_key="cycling_power_5s",
                activity_id="candidate",
                source_mode="best_effort_duration",
                metric_name="power_w",
                metric_value=620,
                metric_unit="watts",
                range_data={"start_sec": 10, "end_sec": 15, "duration_sec": 5},
                quality={"confidence": 0.8, "reason_codes": ["duration_semantics_unknown"]},
            )
            career_backend.apply_record_evidence_state(conn, active)
            candidate_result = career_backend.apply_record_evidence_state(conn, candidate)

            confirm_result = career_backend.decide_career_record_v2_candidate(candidate_result["candidate_id"], "confirm", conn=conn)

            self.assertTrue(confirm_result["ok"])
            self.assertEqual(confirm_result["data"]["action"], "activated")
            active_rows = _active_rows(conn)
            self.assertEqual(len(active_rows), 1)
            self.assertEqual(active_rows[0][1], "candidate")
            self.assertEqual(active_rows[0][6], 620)
            self.assertEqual(
                conn.execute("SELECT status FROM career_event_candidates WHERE id = ?", (candidate_result["candidate_id"],)).fetchone()[0],
                "confirmed",
            )
        finally:
            conn.close()

    def test_v2_events_include_scope_and_safe_payload(self):
        conn = sqlite3.connect(":memory:")
        try:
            evidence = _evidence(activity_id="activity-safe", metric_value=100000)

            career_backend.apply_record_evidence_state(conn, evidence)

            event = conn.execute(
                """
                SELECT record_key, scope_hash, scope_key, decision, reason_codes_json, payload_json
                FROM career_record_events
                WHERE event_type = 'activated'
                LIMIT 1
                """
            ).fetchone()
            self.assertEqual(event[0], "cycling_longest_distance")
            self.assertTrue(event[1].startswith("scope:v2:sha256:"))
            self.assertEqual(event[2], "outdoor")
            self.assertEqual(event[3], "auto_confirm")
            payload_json = event[5]
            for forbidden in ("track_json", "power_stream", "file_path", "device_serial", "weight_history"):
                self.assertNotIn(forbidden, payload_json)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
