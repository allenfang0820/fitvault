import sqlite3
import unittest

import career_backend


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


def insert_record_row(conn: sqlite3.Connection, values: dict):
    career_backend.ensure_career_schema(conn)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(career_pb_records)").fetchall()}
    payload = {
        "id": "record:model:1",
        "activity_id": "model-activity",
        "sport": "cycling",
        "pb_type": "cycling_model_estimate",
        "value": 320,
        "value_unit": "watts",
        "improvement": 0,
        "event_date": "2026-07-15",
        "confidence": 1.0,
        "source": "model",
        "status": "active",
        "record_key": "cycling_model_estimate",
        "record_family": "model_estimate",
        "source_mode": "activity_total",
        "sport_scope": "model",
        "scope_json": '{"sport_scope":"model"}',
        "scope_key": "model",
        "scope_hash": "scope:v2:model",
        "catalog_state": "model_only",
        "metric_value_num": 320,
        "metric_name": "power_w",
        "rule_version": "records-v2-test",
    }
    payload.update(values)
    filtered = {key: value for key, value in payload.items() if key in columns}
    placeholders = ", ".join("?" for _ in filtered)
    conn.execute(
        f"INSERT INTO career_pb_records ({', '.join(filtered.keys())}) VALUES ({placeholders})",
        tuple(filtered.values()),
    )


class CareerRecordsV2DownstreamIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

    def tearDown(self):
        self.conn.close()

    def test_overview_summary_counts_only_formal_active_and_superseded_records(self):
        career_backend.apply_record_evidence_state(self.conn, cycling_distance("activity-1", 100000, "2026-07-14"))
        career_backend.apply_record_evidence_state(self.conn, cycling_distance("activity-2", 105000, "2026-07-15"))
        career_backend.apply_record_evidence_state(self.conn, cycling_power_candidate())

        summary = career_backend.get_career_records_downstream_integration(self.conn)

        self.assertEqual(summary["overview"]["formal_record_count"], 2)
        self.assertEqual(summary["overview"]["by_sport"], {"cycling": 2})
        self.assertEqual(summary["overview"]["by_family"], {"activity_total_record": 2})
        self.assertEqual({record["status"] for record in summary["overview"]["records"]}, {"active", "superseded"})
        self.assertEqual(summary["excluded_sources"]["candidate_count"], 1)
        self.assertNotIn(
            "cycling_power_5s",
            {record["record_key"] for record in summary["overview"]["records"]},
        )

    def test_timeline_and_achievement_use_only_formal_record_events_idempotently(self):
        first = career_backend.apply_record_evidence_state(self.conn, cycling_distance("activity-1", 100000, "2026-07-14"))
        second = career_backend.apply_record_evidence_state(self.conn, cycling_distance("activity-2", 105000, "2026-07-15"))
        unchanged = career_backend.apply_record_evidence_state(self.conn, cycling_distance("activity-3", 90000, "2026-07-16"))
        candidate = career_backend.apply_record_evidence_state(self.conn, cycling_power_candidate())

        self.assertEqual(first["action"], "activated")
        self.assertEqual(second["action"], "activated")
        self.assertEqual(unchanged["action"], "unchanged")
        self.assertEqual(candidate["action"], "candidate_created")

        summary = career_backend.get_career_records_downstream_integration(self.conn)
        events = summary["timeline"]["events"]

        self.assertEqual(summary["timeline"]["formal_event_count"], 2)
        self.assertEqual(summary["achievement"]["formal_trigger_count"], 2)
        self.assertEqual(len({event["id"] for event in events}), 2)
        self.assertEqual({event["event_type"] for event in events}, {"activated"})
        self.assertNotIn("candidate_created", {event["event_type"] for event in events})
        self.assertNotIn("recalculated", {event["event_type"] for event in events})
        self.assertEqual(summary["timeline"]["idempotency_key"], "career_record_events.id")

    def test_race_archive_boundary_and_curve_model_exclusions_are_explicit(self):
        career_backend.apply_record_evidence_state(self.conn, cycling_distance("activity-1", 100000, "2026-07-14"))
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
        career_backend.save_career_record_curve_cache(
            activity_id="activity-1",
            sport="cycling",
            curve_type="cycling_power_duration_curve",
            source_mode="activity_total",
            scope={"sport_scope": "outdoor"},
            input_fingerprint=fingerprint,
            algorithm_version="curve:v1",
            curve={"anchors": [{"label": "1m", "value": 200}]},
            quality={"state": "ready", "reason_codes": []},
            conn=self.conn,
        )
        insert_record_row(self.conn, {"id": "record:model:1"})

        summary = career_backend.get_career_records_downstream_integration(self.conn)

        self.assertFalse(summary["race_archive"]["consumes_records"])
        self.assertEqual(summary["race_archive"]["record_derived_race_count"], 0)
        self.assertEqual(summary["achievement"]["cache_curve_triggers"], 0)
        self.assertEqual(summary["excluded_sources"]["curve_cache_count"], 1)
        self.assertEqual(summary["excluded_sources"]["model_and_analysis_records"], "excluded_by_family_and_catalog_state")
        self.assertNotIn(
            "cycling_model_estimate",
            {record["record_key"] for record in summary["overview"]["records"]},
        )

    def test_existing_timeline_keeps_candidates_out_of_formal_nodes(self):
        career_backend.apply_record_evidence_state(self.conn, cycling_power_candidate())

        timeline = career_backend.get_career_timeline({"type": "all"}, self.conn)

        self.assertEqual(timeline["candidates_count"], 1)
        self.assertEqual(timeline["years"], [])


if __name__ == "__main__":
    unittest.main()
