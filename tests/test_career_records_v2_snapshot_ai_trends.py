import json
import sqlite3
import unittest

import career_backend


FORBIDDEN_SNAPSHOT_TEXT = (
    "anchors",
    "input_fingerprint",
    "stream_summary_hash",
    "record_decision",
    "elapsed_time_sec",
    "route_signature",
    "detail_link",
    "file_path",
    "track_json",
    "points",
    "weight_history",
    "sqlite_schema",
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


def insert_model_only_record(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(career_pb_records)").fetchall()}
    payload = {
        "id": "record:model:eftp",
        "activity_id": "activity-model",
        "sport": "cycling",
        "pb_type": "cycling_eftp",
        "value": 300,
        "value_unit": "watts",
        "event_date": "2026-07-15",
        "confidence": 1.0,
        "source": "model",
        "status": "active",
        "record_key": "cycling_eftp",
        "record_family": "model_estimate",
        "source_mode": "activity_total",
        "sport_scope": "model",
        "scope_json": '{"sport_scope":"model"}',
        "scope_key": "model",
        "scope_hash": "scope:v2:model",
        "catalog_state": "model_only",
        "metric_value_num": 300,
        "metric_name": "power_w",
        "rule_version": "records-v2-test",
    }
    filtered = {key: value for key, value in payload.items() if key in columns}
    placeholders = ", ".join("?" for _ in filtered)
    conn.execute(
        f"INSERT INTO career_pb_records ({', '.join(filtered.keys())}) VALUES ({placeholders})",
        tuple(filtered.values()),
    )


class CareerRecordsV2SnapshotAiTrendsTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        career_backend.ensure_career_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def _save_cycling_curve(self):
        fingerprint = career_backend.compute_career_record_curve_input_fingerprint(
            activity_id="activity-2",
            sport="cycling",
            source_mode="activity_total",
            canonical_facts_version="facts:v1",
            stream_summary_hash="summary:v1",
            algorithm_version="curve:v1",
            rule_version="records-v2",
            scope={"sport_scope": "outdoor"},
        )
        return career_backend.save_career_record_curve_cache(
            activity_id="activity-2",
            sport="cycling",
            curve_type="cycling_power_duration_curve",
            source_mode="activity_total",
            scope={"sport_scope": "outdoor"},
            input_fingerprint=fingerprint,
            algorithm_version="curve:v1",
            curve={"anchors": [{"label": "1m", "value": 250}]},
            quality={"state": "ready", "reason_codes": []},
            conn=self.conn,
        )

    def test_snapshot_compresses_formal_records_candidates_and_curve_availability_safely(self):
        career_backend.apply_record_evidence_state(self.conn, cycling_distance("activity-1", 100000, "2026-07-14"))
        career_backend.apply_record_evidence_state(self.conn, cycling_distance("activity-2", 105000, "2026-07-15"))
        career_backend.apply_record_evidence_state(self.conn, cycling_power_candidate())
        self._save_cycling_curve()
        insert_model_only_record(self.conn)

        snapshot = career_backend.build_career_snapshot(conn=self.conn)
        records_summary = snapshot["records_summary"]
        trend_inputs = records_summary["trend_inputs"]
        curve_availability = records_summary["curve_availability"]
        payload_text = json.dumps(records_summary, ensure_ascii=False)

        self.assertEqual(records_summary["candidate_count"], 1)
        self.assertEqual(len(records_summary["formal_records"]), 2)
        self.assertEqual(
            {record["record_key"] for record in records_summary["formal_records"]},
            {"cycling_longest_distance"},
        )
        self.assertEqual({record["status"] for record in records_summary["formal_records"]}, {"active", "superseded"})
        self.assertNotIn("cycling_eftp", payload_text)

        pdc = curve_availability["by_curve_type"]["cycling_power_duration_curve"]
        self.assertEqual(pdc["state"], "available")
        self.assertEqual(pdc["sample_count"], 1)
        self.assertEqual(pdc["algorithm_versions"], ["curve:v1"])
        self.assertFalse(pdc["creates_formal_record"])
        self.assertEqual(curve_availability["by_curve_type"]["trail_pace_curve"]["state"], "unavailable")

        self.assertEqual(trend_inputs["interpretation"], "frequency_and_curve_availability_only")
        self.assertTrue(all(not item["creates_formal_record"] for item in trend_inputs["curve_inputs"]))
        self.assertFalse(trend_inputs["model_boundary"]["model_estimates_create_records"])
        self.assertFalse(trend_inputs["model_boundary"]["candidate_evidence_exposed"])
        self.assertIn("eFTP", trend_inputs["model_boundary"]["excluded_estimates"])

        for forbidden in FORBIDDEN_SNAPSHOT_TEXT:
            self.assertNotIn(forbidden, payload_text)

    def test_recalculated_events_count_as_evolution_but_not_formal_refreshes(self):
        career_backend.apply_record_evidence_state(self.conn, cycling_distance("activity-1", 100000, "2026-07-14"))
        career_backend.apply_record_evidence_state(self.conn, cycling_distance("activity-3", 90000, "2026-07-16"))

        snapshot = career_backend.build_career_snapshot(conn=self.conn)
        records_summary = snapshot["records_summary"]

        self.assertEqual(records_summary["evolution_summary"]["by_event_type"]["recalculated"], 1)
        self.assertEqual(records_summary["evolution_summary"]["refresh_event_count"], 1)
        self.assertNotIn(
            "recalculated",
            {item["event_type"] for item in records_summary["recent_refreshes"]},
        )
        self.assertEqual(
            records_summary["trend_inputs"]["model_boundary"]["formal_record_refresh_event_types"],
            ["activated", "activated_from_rebuild", "user_confirmed"],
        )

    def test_ai_record_highlights_label_curves_as_analysis_only(self):
        highlights = career_backend._career_insight_record_highlights(
            {
                "curve_availability": {"available_count": 2},
                "candidate_count": 0,
                "current_records": [],
                "formal_records": [],
                "recent_refreshes": [],
                "evolution_summary": {"refresh_event_count": 0},
            }
        )

        joined = " ".join(highlights)
        self.assertIn("分析曲线可用 2 类，仅作趋势参考", joined)
        self.assertNotIn("刷新正式纪录", joined)
        self.assertNotIn("确认候选", joined)

    def test_saved_snapshot_sanitizer_rebuilds_trend_contract_without_dirty_curve_payload(self):
        dirty = {
            "current_records": [],
            "formal_records": [
                {
                    "id": "record:1",
                    "activity_id": "activity-1",
                    "record_key": "cycling_longest_distance",
                    "sport": "cycling",
                    "family": "activity_total_record",
                    "status": "active",
                    "catalog_state": "available",
                    "source_mode": "activity_total",
                    "event_date": "2026-07-15",
                    "metric": {"name": "distance_m", "value": 100000, "unit": "meters", "display": "100 km"},
                    "scope": {"scope_key": "outdoor", "scope_hash": "scope:v2:1", "labels": ["户外"]},
                    "detail_link": {"activity_id": "activity-1"},
                    "quality": {"raw_stream": [1, 2, 3]},
                }
            ],
            "recent_refreshes": [],
            "candidate_count": 3,
            "evolution_summary": {"total_event_count": 1, "refresh_event_count": 1},
            "curve_availability": {
                "by_curve_type": {
                    "cycling_power_duration_curve": {
                        "curve_type": "cycling_power_duration_curve",
                        "sport": "cycling",
                        "source_mode": "activity_total",
                        "state": "available",
                        "sample_count": 1,
                        "algorithm_versions": ["curve:v1"],
                        "latest_generated_at": "2026-07-15T00:00:00+00:00",
                        "input_fingerprint": "sha256:hidden",
                        "anchors": [{"label": "1m"}],
                    }
                }
            },
            "trend_inputs": {"interpretation": "ability_improved", "candidate_evidence": {"record_decision": {}}},
        }

        sanitized = career_backend._sanitize_snapshot_records_summary(dirty)
        payload_text = json.dumps(sanitized, ensure_ascii=False)

        self.assertEqual(sanitized["candidate_count"], 3)
        self.assertEqual(sanitized["formal_records"][0]["record_key"], "cycling_longest_distance")
        self.assertEqual(sanitized["trend_inputs"]["interpretation"], "frequency_and_curve_availability_only")
        self.assertEqual(
            sanitized["curve_availability"]["by_curve_type"]["cycling_power_duration_curve"]["state"],
            "available",
        )
        for forbidden in FORBIDDEN_SNAPSHOT_TEXT:
            self.assertNotIn(forbidden, payload_text)


if __name__ == "__main__":
    unittest.main()
