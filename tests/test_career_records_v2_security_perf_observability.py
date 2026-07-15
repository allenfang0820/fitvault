import inspect
import json
import sqlite3
import unittest

import career_backend
import main


FORBIDDEN = (
    "raw_fit",
    "raw_stream",
    "power_stream",
    "track_json",
    "file_path",
    "storage_ref",
    "sqlite_master",
    "sqlite_schema",
    "route_signature",
    "evidence_json",
    "record_decision",
    "/Users/",
    "/tmp/",
)


def assert_no_sensitive_text(testcase: unittest.TestCase, payload) -> None:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    for forbidden in FORBIDDEN:
        testcase.assertNotIn(forbidden, text)


def create_activities(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE activities (
            id TEXT PRIMARY KEY,
            sport_type TEXT,
            deleted_at TEXT,
            updated_at TEXT,
            points_json TEXT,
            track_json TEXT,
            file_path TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO activities (id, sport_type, deleted_at, updated_at, points_json, track_json, file_path)
        VALUES
            ('activity-1', 'cycling', NULL, '2026-07-15T00:00:00+00:00', '[hidden]', '[hidden]', '/tmp/hidden.fit'),
            ('activity-2', 'trail_running', NULL, '2026-07-15T00:00:00+00:00', '[hidden]', '[hidden]', '/tmp/hidden.fit')
        """
    )


def cycling_distance(activity_id: str, value: float, date: str = "2026-07-14"):
    return career_backend.build_record_evidence(
        record_key="cycling_longest_distance",
        activity_id=activity_id,
        sport="cycling",
        source_mode="activity_total",
        metric_name="distance_m",
        metric_value=value,
        metric_unit="meters",
        event_date=date,
        scope={"sport_scope": "outdoor"},
        quality={"confidence": 0.98, "reason_codes": ["metric_quality_ok"]},
        resolver_version="records-v2-test",
    )


def cycling_power_candidate():
    return career_backend.build_record_evidence(
        record_key="cycling_power_5s",
        activity_id="candidate-activity",
        sport="cycling",
        source_mode="best_effort_duration",
        metric_name="power_w",
        metric_value=600,
        metric_unit="watts",
        event_date="2026-07-15",
        scope={"sport_scope": "outdoor"},
        range_data={"start_sec": 10, "end_sec": 15, "duration_sec": 5},
        quality={"confidence": 0.8, "reason_codes": ["duration_semantics_unknown"]},
        resolver_version="records-v2-test",
    )


class CareerRecordsV2SecurityPerfObservabilityTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        career_backend.ensure_career_schema(self.conn)
        create_activities(self.conn)

    def tearDown(self):
        self.conn.close()

    def _save_curve(self):
        fingerprint = career_backend.compute_career_record_curve_input_fingerprint(
            activity_id="activity-1",
            sport="cycling",
            source_mode="activity_total",
            canonical_facts_version="facts:v1",
            stream_summary_hash="summary:v1",
            algorithm_version="curve:v1",
            rule_version="records-v2",
            scope={"sport_scope": "outdoor"},
        )
        return career_backend.save_career_record_curve_cache(
            activity_id="activity-1",
            sport="cycling",
            curve_type="cycling_power_duration_curve",
            source_mode="activity_total",
            scope={"sport_scope": "outdoor"},
            input_fingerprint=fingerprint,
            algorithm_version="curve:v1",
            curve={"anchors": [{"x": 60, "y": 250, "label": "1m"}]},
            quality={"state": "ready", "reason_codes": []},
            conn=self.conn,
        )

    def _save_route_candidate(self):
        return career_backend.save_career_route_match(
            route_key="route:test",
            activity_id="activity-2",
            matched_activity_id="activity-1",
            match={
                "direction": "same",
                "match_score": 0.94,
                "coverage_ratio": 0.91,
                "overlap_ratio": 0.93,
                "length_error_ratio": 0.02,
                "decision": "candidate",
                "reason_codes": ["same_route_candidate"],
            },
            conn=self.conn,
        )

    def test_observability_contract_and_safe_observation_drop_sensitive_fields(self):
        contract = career_backend.records_v2_observability_contract()
        observation = career_backend.records_v2_safe_observation(
            "records_v2_rebuild",
            run_id="records_v2_rebuild:test",
            dry_run=True,
            processed=2,
            by_sport={"cycling": 1},
            payload_json={"raw_fit": "hidden"},
            evidence_json={"record_decision": {"elapsed_time_sec": 1}},
            file_path="/tmp/hidden.fit",
            route_signature="hidden",
        )

        self.assertIn("records_list", contract["performance_targets_ms"])
        self.assertIn("rebuild_career_records", contract["high_risk_operations"])
        self.assertTrue(contract["high_risk_operations"]["rebuild_career_records"]["default_dry_run"])
        self.assertEqual(observation["run_id"], "records_v2_rebuild:test")
        self.assertEqual(observation["by_sport"], {"cycling": 1})
        assert_no_sensitive_text(self, observation)

    def test_records_queries_expose_diagnostic_metrics_without_sensitive_payloads(self):
        career_backend.apply_record_evidence_state(self.conn, cycling_distance("activity-1", 100000))
        career_backend.apply_record_evidence_state(self.conn, cycling_power_candidate())
        record = career_backend.get_career_records({"sport": "cycling"}, conn=self.conn)["records"][0]

        records = career_backend.get_career_records({"sport": "cycling"}, conn=self.conn)
        history = career_backend.get_career_record_history(
            {"record_key": record["record_key"], "scope_hash": record["scope"]["scope_hash"]},
            conn=self.conn,
        )
        candidates = career_backend.get_career_record_candidates({"status": "candidate"}, conn=self.conn)

        self.assertEqual(records["metrics"]["performance_target_ms"], career_backend.RECORDS_V2_PERFORMANCE_TARGETS_MS["records_list"])
        self.assertEqual(history["metrics"]["performance_target_ms"], career_backend.RECORDS_V2_PERFORMANCE_TARGETS_MS["record_history"])
        self.assertEqual(candidates["metrics"]["performance_target_ms"], career_backend.RECORDS_V2_PERFORMANCE_TARGETS_MS["record_candidates"])
        self.assertGreaterEqual(records["metrics"]["elapsed_ms"], 0)
        self.assertEqual(candidates["summary"]["total"], 1)
        assert_no_sensitive_text(self, records)
        assert_no_sensitive_text(self, candidates)

    def test_curve_and_route_views_report_cache_hit_miss_and_route_candidates(self):
        self._save_curve()
        self._save_route_candidate()

        curve_hit = career_backend.get_career_record_curve(
            {"activity_id": "activity-1", "curve_type": "cycling_power_duration_curve"},
            conn=self.conn,
        )
        curve_miss = career_backend.get_career_record_curve(
            {"activity_id": "missing", "curve_type": "cycling_power_duration_curve"},
            conn=self.conn,
        )
        route = career_backend.get_trail_route_comparison_viewmodel({"route_key": "route:test"}, conn=self.conn)

        self.assertTrue(curve_hit["metrics"]["cache_hit"])
        self.assertFalse(curve_hit["metrics"]["cache_miss"])
        self.assertFalse(curve_miss["metrics"]["cache_hit"])
        self.assertTrue(curve_miss["metrics"]["cache_miss"])
        self.assertTrue(route["metrics"]["cache_hit"])
        self.assertEqual(route["summary"]["route_candidates"], 1)
        self.assertEqual(route["metrics"]["route_candidates"], 1)
        assert_no_sensitive_text(self, route)

    def test_rebuild_plan_reports_counts_cache_route_metrics_and_failure_recovery(self):
        self._save_curve()
        self._save_route_candidate()

        plan = career_backend.rebuild_career_records({"dry_run": True, "batch_size": 1, "cancel_after": 1}, conn=self.conn)

        self.assertTrue(plan["dry_run"])
        self.assertTrue(plan["cancelled"])
        self.assertIn("by_sport", plan)
        self.assertIn("by_family", plan)
        self.assertIn("by_reason", plan)
        self.assertEqual(plan["metrics"]["curve_cache_count"], 1)
        self.assertEqual(plan["metrics"]["route_cache_count"], 0)
        self.assertEqual(plan["metrics"]["route_match_count"], 1)
        self.assertEqual(plan["metrics"]["route_candidates"], 1)
        self.assertTrue(plan["failure_recovery"]["supports_batching"])
        self.assertTrue(plan["failure_recovery"]["supports_cancel"])
        self.assertFalse(plan["failure_recovery"]["raw_payload_logged"])
        self.assertEqual(plan["observability"]["event"], "records_v2_rebuild_plan")
        assert_no_sensitive_text(self, plan["observability"])

    def test_candidate_decision_is_bounded_idempotent_and_observable(self):
        candidate = career_backend.apply_record_evidence_state(self.conn, cycling_power_candidate())

        first = career_backend.decide_career_record_candidate(
            {"candidate_id": candidate["candidate_id"], "decision": "reject"},
            conn=self.conn,
        )
        second = career_backend.decide_career_record_candidate(
            {"candidate_id": candidate["candidate_id"], "decision": "reject"},
            conn=self.conn,
        )

        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertEqual(first["data"]["action"], "rejected")
        self.assertEqual(second["data"]["action"], "rejected")
        self.assertIn("metrics", first["data"])
        self.assertEqual(first["data"]["observability"]["event"], "records_v2_candidate_decision")
        assert_no_sensitive_text(self, first["data"]["observability"])

    def test_main_rebuild_apply_is_gated_before_backend_write_and_logs_safely(self):
        response = main.Api().rebuild_career_records({"dry_run": False})
        source = inspect.getsource(main.Api.rebuild_career_records)

        self.assertFalse(response["ok"])
        self.assertIn("dry-run", response["msg"])
        self.assertIn("apply_to_real_db", source)
        self.assertIn("records_v2_safe_observation", source)
        self.assertNotIn("logger.info(clean_payload", source)


if __name__ == "__main__":
    unittest.main()
