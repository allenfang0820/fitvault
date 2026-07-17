import json
import sqlite3
import unittest
from unittest import mock

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
        scope={"sport_scope": "outdoor"},
        range_data=range_data or {},
        quality=quality
        or {
            "confidence": 0.98,
            "confidence_band": "high",
            "decision": "auto_confirm",
            "reason_codes": [],
            "blocks_active": False,
        },
        resolver_version="records-v2-test",
    ).to_dict()


def _candidate_id(evidence):
    return "records_v2_candidate:test:" + evidence["record_key"] + ":" + evidence["activity_id"]


def _running_best_effort_evidence(record_key, activity_id, value):
    distance_m = 5000 if record_key == "running_5k" else 10000
    return career_backend.build_record_evidence(
        record_key=record_key,
        activity_id=activity_id,
        sport="running",
        source_mode="best_effort_distance",
        metric_name="elapsed_time_sec",
        metric_value=value,
        metric_unit="seconds",
        event_date="2026-07-15",
        scope={},
        range_data={
            "start_sec": 0,
            "end_sec": value,
            "duration_sec": value,
            "start_distance_m": 0,
            "end_distance_m": distance_m,
            "distance_m": distance_m,
        },
        quality={
            "confidence": 0.92,
            "confidence_band": "high",
            "decision": "preview",
            "reason_codes": ["best_effort_distance_window"],
            "blocks_active": False,
        },
        resolver_version="records-v2-test",
    ).to_dict()


def _insert_da12_candidate(conn, evidence, *, status="candidate", confidence=0.98):
    candidate_id = _candidate_id(evidence)
    payload = career_backend._candidate_payload_from_record_evidence(evidence, "candidate", [])
    payload["candidate_write"] = {
        "version": "records-v2-g11-candidate-write-v1",
        "run_id": "records_v2_preview:test",
        "idempotency_key": "records_v2_candidate:test:" + candidate_id,
        "write_scope": "career_event_candidates_only",
    }
    conn.execute(
        """
        INSERT INTO career_event_candidates
            (id, activity_id, candidate_type, title, evidence_json, confidence, status, updated_at)
        VALUES
            (?, ?, 'pb_record', ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            candidate_id,
            evidence["activity_id"],
            evidence["record_key"] + " candidate",
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            confidence,
            status,
        ),
    )
    return candidate_id


class CareerRecordsV2ActiveWriteGateTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        career_backend.ensure_career_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def counts(self):
        return {
            table: int(self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("career_pb_records", "career_event_candidates", "career_record_events")
        }

    def test_active_write_dry_run_is_read_only(self):
        candidate_id = _insert_da12_candidate(self.conn, _evidence(metric_value=100000))
        before = self.counts()

        result = career_backend.apply_records_v2_active_write(
            {"candidate_ids": [candidate_id], "dry_run": True},
            conn=self.conn,
        )

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["summary"]["would_activate"], 1)
        self.assertEqual(self.counts(), before)

    def test_active_write_activates_candidate_and_events_in_memory(self):
        candidate_id = _insert_da12_candidate(self.conn, _evidence(metric_value=100000))

        result = career_backend.apply_records_v2_active_write(
            {"candidate_ids": [candidate_id], "dry_run": False},
            conn=self.conn,
        )

        self.assertFalse(result["dry_run"])
        self.assertEqual(result["summary"]["activated"], 1)
        self.assertEqual(result["summary"]["rejected"], 0)
        self.assertEqual(
            self.conn.execute("SELECT status FROM career_event_candidates WHERE id = ?", (candidate_id,)).fetchone()[0],
            "confirmed",
        )
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM career_pb_records WHERE status = 'active'").fetchone()[0], 1)
        event_types = {row[0] for row in self.conn.execute("SELECT event_type FROM career_record_events").fetchall()}
        self.assertIn("activated", event_types)
        self.assertIn("user_confirmed", event_types)

    def test_active_write_supersedes_previous_active(self):
        first_id = _insert_da12_candidate(self.conn, _evidence(activity_id="activity-1", metric_value=100000))
        second_id = _insert_da12_candidate(self.conn, _evidence(activity_id="activity-2", metric_value=105000))

        career_backend.apply_records_v2_active_write({"candidate_ids": [first_id], "dry_run": False}, conn=self.conn)
        result = career_backend.apply_records_v2_active_write({"candidate_ids": [second_id], "dry_run": False}, conn=self.conn)

        self.assertEqual(result["summary"]["activated"], 1)
        self.assertEqual(result["summary"]["superseded"], 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM career_pb_records WHERE status = 'active'").fetchone()[0], 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM career_pb_records WHERE status = 'superseded'").fetchone()[0], 1)

    def test_active_write_unchanged_candidate_does_not_create_new_active(self):
        first_id = _insert_da12_candidate(self.conn, _evidence(activity_id="activity-1", metric_value=100000))
        worse_id = _insert_da12_candidate(self.conn, _evidence(activity_id="activity-2", metric_value=90000))

        career_backend.apply_records_v2_active_write({"candidate_ids": [first_id], "dry_run": False}, conn=self.conn)
        result = career_backend.apply_records_v2_active_write({"candidate_ids": [worse_id], "dry_run": False}, conn=self.conn)

        self.assertEqual(result["summary"]["unchanged"], 1)
        self.assertEqual(result["summary"]["activated"], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM career_pb_records WHERE status = 'active'").fetchone()[0], 1)

    def test_running_best_effort_active_plan_compares_against_legacy_active(self):
        career_backend.apply_record_evidence_state(
            self.conn,
            _evidence(
                record_key="running_5k",
                activity_id="legacy-5k",
                sport="running",
                metric_name="elapsed_time_sec",
                metric_value=1628,
                metric_unit="seconds",
            ),
        )
        career_backend.apply_record_evidence_state(
            self.conn,
            _evidence(
                record_key="running_10k",
                activity_id="legacy-10k",
                sport="running",
                metric_name="elapsed_time_sec",
                metric_value=2406,
                metric_unit="seconds",
            ),
        )
        five_k_id = _insert_da12_candidate(
            self.conn,
            _running_best_effort_evidence("running_5k", "best-5k", 1212.156),
            confidence=0.92,
        )
        ten_k_id = _insert_da12_candidate(
            self.conn,
            _running_best_effort_evidence("running_10k", "slower-10k", 3268.262),
            confidence=0.92,
        )

        result = career_backend.apply_records_v2_active_write(
            {
                "candidate_ids": [five_k_id, ten_k_id],
                "dry_run": True,
                "strict_da12_batch": False,
            },
            conn=self.conn,
        )

        by_key = {item["record_key"]: item for item in result["items"]}
        self.assertEqual(by_key["running_5k"]["action"], "would_activate")
        self.assertTrue(by_key["running_5k"]["will_supersede"])
        self.assertTrue(by_key["running_5k"]["current_record_id"].startswith("record:v2:"))
        self.assertEqual(by_key["running_10k"]["action"], "unchanged")
        self.assertFalse(by_key["running_10k"]["will_supersede"])
        self.assertEqual(by_key["running_10k"]["comparison"]["reason"], "not_improved")
        self.assertEqual(result["summary"]["would_activate"], 1)
        self.assertEqual(result["summary"]["unchanged"], 1)

    def test_running_best_effort_active_apply_does_not_activate_slower_10k(self):
        career_backend.apply_record_evidence_state(
            self.conn,
            _evidence(
                record_key="running_5k",
                activity_id="legacy-5k",
                sport="running",
                metric_name="elapsed_time_sec",
                metric_value=1628,
                metric_unit="seconds",
            ),
        )
        career_backend.apply_record_evidence_state(
            self.conn,
            _evidence(
                record_key="running_10k",
                activity_id="legacy-10k",
                sport="running",
                metric_name="elapsed_time_sec",
                metric_value=2406,
                metric_unit="seconds",
            ),
        )
        five_k_id = _insert_da12_candidate(
            self.conn,
            _running_best_effort_evidence("running_5k", "best-5k", 1212.156),
            confidence=0.92,
        )
        ten_k_id = _insert_da12_candidate(
            self.conn,
            _running_best_effort_evidence("running_10k", "slower-10k", 3268.262),
            confidence=0.92,
        )

        result = career_backend.apply_records_v2_active_write(
            {
                "candidate_ids": [five_k_id, ten_k_id],
                "dry_run": False,
                "strict_da12_batch": False,
            },
            conn=self.conn,
        )

        self.assertEqual(result["summary"]["activated"], 1)
        self.assertEqual(result["summary"]["superseded"], 1)
        self.assertEqual(result["summary"]["unchanged"], 1)
        five_k_rows = self.conn.execute(
            "SELECT status, value FROM career_pb_records WHERE record_key = 'running_5k' ORDER BY status"
        ).fetchall()
        self.assertEqual(len(five_k_rows), 2)
        self.assertEqual(
            self.conn.execute("SELECT value FROM career_pb_records WHERE record_key = 'running_5k' AND status = 'active'").fetchone()[0],
            "1212.156",
        )
        self.assertEqual(
            self.conn.execute("SELECT event_date FROM career_pb_records WHERE record_key = 'running_5k' AND status = 'active'").fetchone()[0],
            "2026-07-15",
        )
        self.assertNotEqual(
            self.conn.execute("SELECT range_json FROM career_pb_records WHERE record_key = 'running_5k' AND status = 'active'").fetchone()[0],
            "{}",
        )
        active_scope_hash = self.conn.execute(
            "SELECT scope_hash FROM career_pb_records WHERE record_key = 'running_5k' AND status = 'active'"
        ).fetchone()[0]
        history = career_backend.get_career_record_history(
            {"record_key": "running_5k", "scope_hash": active_scope_hash, "include_invalidated": True},
            conn=self.conn,
        )
        self.assertEqual(history["metrics"]["returned_count"], 2)
        self.assertEqual(
            [record["status"] for record in history["records"]],
            ["superseded", "active"],
        )
        self.assertEqual(
            [point["status"] for point in history["chart"]["points"]],
            ["superseded", "active"],
        )
        ten_k_active_rows = self.conn.execute(
            "SELECT value FROM career_pb_records WHERE record_key = 'running_10k' AND status = 'active'"
        ).fetchall()
        self.assertEqual([row[0] for row in ten_k_active_rows], ["2406"])

    def test_confirmed_candidate_repairs_existing_superseded_record(self):
        career_backend.apply_record_evidence_state(
            self.conn,
            _evidence(
                record_key="running_5k",
                activity_id="legacy-5k",
                sport="running",
                metric_name="elapsed_time_sec",
                metric_value=1628,
                metric_unit="seconds",
            ),
        )
        evidence = _running_best_effort_evidence("running_5k", "best-5k", 1212.156)
        candidate_id = _insert_da12_candidate(self.conn, evidence, confidence=0.92)

        first = career_backend.apply_records_v2_active_write(
            {
                "candidate_ids": [candidate_id],
                "dry_run": False,
                "strict_da12_batch": False,
            },
            conn=self.conn,
        )
        self.assertEqual(first["summary"]["activated"], 1)
        record_id = first["apply"]["activated"][0]["record_id"]
        legacy_record_id = self.conn.execute(
            "SELECT id FROM career_pb_records WHERE record_key = 'running_5k' AND id != ?",
            (record_id,),
        ).fetchone()[0]

        self.conn.execute("UPDATE career_pb_records SET status = 'active' WHERE id = ?", (legacy_record_id,))
        self.conn.execute("UPDATE career_pb_records SET status = 'superseded' WHERE id = ?", (record_id,))

        plan = career_backend.plan_records_v2_active_write(
            self.conn,
            {
                "candidate_ids": [candidate_id],
                "strict_da12_batch": False,
            },
        )
        self.assertEqual(plan["items"][0]["action"], "would_activate")

        repaired = career_backend.apply_records_v2_active_write(
            {
                "candidate_ids": [candidate_id],
                "dry_run": False,
                "strict_da12_batch": False,
            },
            conn=self.conn,
        )

        self.assertEqual(repaired["summary"]["activated"], 1)
        self.assertEqual(
            self.conn.execute("SELECT status FROM career_pb_records WHERE id = ?", (record_id,)).fetchone()[0],
            "active",
        )
        self.assertEqual(
            self.conn.execute("SELECT status FROM career_pb_records WHERE id = ?", (legacy_record_id,)).fetchone()[0],
            "superseded",
        )

    def test_active_write_is_idempotent_for_confirmed_candidate(self):
        candidate_id = _insert_da12_candidate(self.conn, _evidence(metric_value=100000))

        first = career_backend.apply_records_v2_active_write({"candidate_ids": [candidate_id], "dry_run": False}, conn=self.conn)
        second = career_backend.apply_records_v2_active_write({"candidate_ids": [candidate_id], "dry_run": False}, conn=self.conn)

        self.assertEqual(first["summary"]["activated"], 1)
        self.assertEqual(second["summary"]["skipped"], 1)
        self.assertEqual(second["apply"]["skipped"][0]["action"], "skipped_existing_active")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM career_pb_records").fetchone()[0], 1)
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM career_record_events WHERE event_type = 'activated'").fetchone()[0],
            1,
        )

    def test_active_write_rejects_rejected_candidate(self):
        candidate_id = _insert_da12_candidate(self.conn, _evidence(metric_value=100000), status="rejected")

        result = career_backend.apply_records_v2_active_write(
            {"candidate_ids": [candidate_id], "dry_run": False},
            conn=self.conn,
        )

        self.assertEqual(result["summary"]["rejected"], 1)
        self.assertIn("candidate_rejected", result["apply"]["rejected"][0]["reason_codes"])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM career_pb_records").fetchone()[0], 0)

    def test_active_write_rejects_validation_required_and_candidate_only(self):
        validation_required = _evidence(
            record_key="cycling_max_work",
            activity_id="work",
            metric_name="work_kj",
            metric_value=2000,
            metric_unit="kilojoules",
        )
        candidate_only = _evidence(
            record_key="hiking_max_single_climb",
            activity_id="climb",
            sport="hiking",
            source_mode="activity_total",
            metric_name="single_climb_m",
            metric_value=800,
            metric_unit="meters_ascent",
        )
        first_id = _insert_da12_candidate(self.conn, validation_required)
        second_id = _insert_da12_candidate(self.conn, candidate_only)

        result = career_backend.apply_records_v2_active_write(
            {"candidate_ids": [first_id, second_id], "dry_run": False, "strict_da12_batch": False},
            conn=self.conn,
        )

        reasons = {code for item in result["apply"]["rejected"] for code in item["reason_codes"]}
        self.assertIn("validation_required_registry", reasons)
        self.assertIn("candidate_only_registry", reasons)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM career_pb_records").fetchone()[0], 0)

    def test_candidate_decision_confirm_reports_gate_rejection(self):
        validation_required = _evidence(
            record_key="cycling_max_work",
            activity_id="work",
            metric_name="work_kj",
            metric_value=2000,
            metric_unit="kilojoules",
        )
        candidate_id = _insert_da12_candidate(self.conn, validation_required)

        result = career_backend.decide_career_record_candidate(
            {"candidate_id": candidate_id, "action": "confirm"},
            conn=self.conn,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "active_write_rejected")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM career_pb_records").fetchone()[0], 0)
        self.assertEqual(
            self.conn.execute("SELECT status FROM career_event_candidates WHERE id = ?", (candidate_id,)).fetchone()[0],
            "candidate",
        )

    def test_active_write_refuses_default_real_db_without_da15_authorization(self):
        candidate_id = _insert_da12_candidate(self.conn, _evidence(metric_value=100000))
        with mock.patch.object(career_backend, "_records_v2_candidate_write_targets_default_real_db", return_value=True):
            result = career_backend.apply_records_v2_active_write(
                {"candidate_ids": [candidate_id], "dry_run": False},
                conn=self.conn,
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "real_db_active_write_not_authorized")
        self.assertEqual(self.counts(), {"career_pb_records": 0, "career_event_candidates": 1, "career_record_events": 0})


if __name__ == "__main__":
    unittest.main()
