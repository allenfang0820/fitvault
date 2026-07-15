import json
import sqlite3
import unittest

import career_backend


FORBIDDEN = (
    "track_json",
    "power_stream",
    "file_path",
    "storage_ref",
    "sqlite_master",
    "CREATE TABLE",
    "device_serial",
    "weight_history",
    "/Users/",
)


def assert_safe_payload(testcase: unittest.TestCase, payload):
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    for forbidden in FORBIDDEN:
        testcase.assertNotIn(forbidden, text)


def create_activities(conn: sqlite3.Connection):
    conn.execute(
        """
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY,
            title TEXT,
            sport_type TEXT,
            start_time TEXT,
            distance REAL,
            duration_sec INTEGER,
            deleted_at TEXT
        )
        """
    )
    conn.executemany(
        """
        INSERT INTO activities (id, title, sport_type, start_time, distance, duration_sec, deleted_at)
        VALUES (?, ?, ?, ?, ?, ?, NULL)
        """,
        [
            (1, "晨间骑行", "cycling", "2026-07-01T08:00:00Z", 100000, 7200),
            (2, "更长骑行", "cycling", "2026-07-08T08:00:00Z", 105000, 7600),
            (3, "五秒功率", "cycling", "2026-07-10T08:00:00Z", 30000, 3600),
        ],
    )


def cycling_distance(activity_id: int, distance_m: int):
    return career_backend.build_record_evidence(
        record_key="cycling_longest_distance",
        activity_id=str(activity_id),
        sport="cycling",
        source_mode="activity_total",
        metric_name="distance_m",
        metric_value=distance_m,
        metric_unit="meters",
        event_date=f"2026-07-{activity_id:02d}",
        scope={"sport_scope": "outdoor"},
        quality={"confidence": 0.99, "reason_codes": ["metric_quality_ok"]},
        resolver_version="records-v2-test",
    )


def cycling_power_candidate():
    return career_backend.build_record_evidence(
        record_key="cycling_power_5s",
        activity_id="3",
        sport="cycling",
        source_mode="best_effort_duration",
        metric_name="power_w",
        metric_value=600,
        metric_unit="watts",
        event_date="2026-07-10",
        scope={"sport_scope": "outdoor"},
        range_data={"start_sec": 10, "end_sec": 15, "duration_sec": 5},
        quality={"confidence": 0.8, "reason_codes": ["duration_semantics_unknown"]},
        resolver_version="records-v2-test",
    )


class CareerRecordsV2ApiTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        create_activities(self.conn)
        career_backend.apply_record_evidence_state(self.conn, cycling_distance(1, 100000))
        career_backend.apply_record_evidence_state(self.conn, cycling_distance(2, 105000))

    def tearDown(self):
        self.conn.close()

    def test_catalog_and_records_api_return_safe_viewmodel(self):
        catalog = career_backend.get_career_record_catalog({"sport": "cycling"})
        records = career_backend.get_career_records({"sport": "cycling"}, conn=self.conn)

        self.assertTrue(catalog["sports"])
        self.assertEqual(records["summary"]["active_count"], 1)
        record = records["records"][0]
        self.assertEqual(record["record_key"], "cycling_longest_distance")
        self.assertEqual(record["metric"]["display"], "105000 m")
        self.assertEqual(record["improvement"]["value"], 5000)
        self.assertEqual(record["detail_link"]["source"], "career")
        self.assertEqual(records["status"]["records_version"], "records-v2")
        assert_safe_payload(self, records)

    def test_detail_and_history_api_compute_summary_backend_side(self):
        records = career_backend.get_career_records({"sport": "cycling"}, conn=self.conn)["records"]
        record_id = records[0]["id"]

        detail = career_backend.get_career_record_detail({"record_id": record_id}, conn=self.conn)
        history = career_backend.get_career_record_history(
            {"record_key": "cycling_longest_distance", "scope_hash": records[0]["scope"]["scope_hash"]},
            conn=self.conn,
        )

        self.assertEqual(detail["record"]["id"], record_id)
        self.assertEqual(detail["activity_summary"]["title"], "更长骑行")
        self.assertEqual(history["history_summary"]["axis_direction"], "higher")
        self.assertEqual(history["history_summary"]["total_improvement"]["value"], 5000)
        self.assertEqual(len(history["chart"]["points"]), 2)
        assert_safe_payload(self, detail)
        assert_safe_payload(self, history)

    def test_curve_api_returns_safe_cache_only(self):
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
            curve={"anchors": [{"x": 60, "y": 200, "label": "1m"}]},
            quality={"state": "ready", "reason_codes": []},
            conn=self.conn,
        )

        curve = career_backend.get_career_record_curve(
            {"activity_id": "2", "curve_type": "cycling_power_duration_curve"},
            conn=self.conn,
        )

        self.assertEqual(curve["curve"]["anchors"][0]["label"], "1m")
        self.assertEqual(curve["status"]["state"], "ready")
        assert_safe_payload(self, curve)

    def test_candidate_api_and_decision_wrapper(self):
        candidate = career_backend.apply_record_evidence_state(self.conn, cycling_power_candidate())

        candidates = career_backend.get_career_record_candidates({"status": "candidate"}, conn=self.conn)
        decision = career_backend.decide_career_record_candidate(
            {"candidate_id": candidate["candidate_id"], "action": "reject"},
            conn=self.conn,
        )

        self.assertEqual(candidates["summary"]["total"], 1)
        self.assertEqual(candidates["candidates"][0]["record_key"], "cycling_power_5s")
        self.assertTrue(decision["ok"])
        self.assertEqual(decision["data"]["action"], "rejected")
        assert_safe_payload(self, candidates)

    def test_rebuild_records_defaults_to_dry_run(self):
        result = career_backend.rebuild_career_records({"dry_run": True}, conn=self.conn)

        self.assertTrue(result["dry_run"])
        self.assertTrue(result["run_id"].startswith("records_v2_rebuild:"))
        self.assertIn("cycling", result["by_sport"])
        assert_safe_payload(self, result)

    def test_record_events_support_v2_scope_and_decision_filters(self):
        record = career_backend.get_career_records({"sport": "cycling"}, conn=self.conn)["records"][0]

        events = career_backend.get_career_record_events(
            {"record_key": "cycling_longest_distance", "scope_hash": record["scope"]["scope_hash"], "decision": "auto_confirm"},
            conn=self.conn,
        )

        self.assertGreaterEqual(len(events["events"]), 1)
        self.assertEqual(events["filters"]["scope_hash"], record["scope"]["scope_hash"])
        self.assertTrue(all(event["record_key"] == "cycling_longest_distance" for event in events["events"]))
        self.assertTrue(all(event["decision"] == "auto_confirm" for event in events["events"]))
        assert_safe_payload(self, events)


if __name__ == "__main__":
    unittest.main()
