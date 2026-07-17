import json
import sqlite3
import unittest
from unittest import mock

import career_backend


FORBIDDEN = (
    "points_json",
    "track_json",
    "raw_fit",
    "file_path",
    "sqlite_master",
    "/Users/",
)


def assert_safe(testcase: unittest.TestCase, payload):
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    for forbidden in FORBIDDEN:
        testcase.assertNotIn(forbidden, text)


def create_activity_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE activities (
            id TEXT PRIMARY KEY,
            title TEXT,
            sport_type TEXT,
            sub_sport_type TEXT,
            start_time TEXT,
            start_time_utc TEXT,
            dist_km REAL,
            distance REAL,
            duration_sec REAL,
            duration REAL,
            gain_m REAL,
            ascent_m REAL,
            max_alt_m REAL,
            max_altitude_m REAL,
            avg_power REAL,
            max_power REAL,
            normalized_power REAL,
            power_points TEXT,
            points_json TEXT,
            track_json TEXT,
            laps_json TEXT,
            lengths_json TEXT,
            pool_length_m REAL,
            deleted_at TEXT,
            is_mock INTEGER
        )
        """
    )


def seed_first_batch_activities(conn: sqlite3.Connection) -> None:
    ride_points = json.dumps([
        {"distance_m": 0, "t_sec": 0, "power_w": 250},
        {"distance_m": 120000, "t_sec": 7200, "power_w": 250},
    ])
    ride_power = json.dumps([
        {"t": 0, "power_w": 250},
        {"t": 600, "power_w": 250},
        {"t": 1200, "power_w": 250},
        {"t": 7200, "power_w": 230},
    ])
    conn.executemany(
        """
        INSERT INTO activities (
            id, title, sport_type, start_time, dist_km, distance, duration_sec,
            gain_m, ascent_m, max_alt_m, max_altitude_m, avg_power, power_points,
            points_json, track_json, deleted_at, is_mock
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 0)
        """,
        [
            ("ride-best", "Long Ride", "cycling", "2026-07-11T08:00:00Z", 120.0, 120000, 7200, 1500, 1500, 1200, 1200, 250, ride_power, ride_points, ""),
            ("ride-short", "Short Ride", "cycling", "2026-07-01T08:00:00Z", 60.0, 60000, 4000, 600, 600, 900, 900, 220, ride_power, ride_points, ""),
            ("hike-best", "High Hike", "hiking", "2026-07-12T08:00:00Z", 22.0, 22000, 16000, 1200, 1200, 3500, 3500, None, "", "", ""),
        ],
    )


def seed_running_best_effort_activities(conn: sqlite3.Connection) -> None:
    run_points = json.dumps([
        {"distance_m": 0, "t_sec": 0},
        {"distance_m": 5000, "t_sec": 1500},
        {"distance_m": 10000, "t_sec": 3300},
        {"distance_m": 12000, "t_sec": 4000},
    ])
    conn.execute(
        """
        INSERT INTO activities (
            id, title, sport_type, start_time, dist_km, distance, duration_sec,
            gain_m, ascent_m, max_alt_m, max_altitude_m, avg_power, power_points,
            points_json, track_json, deleted_at, is_mock
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 0)
        """,
        (
            "run-best-effort",
            "Best Effort Run",
            "running",
            "2026-07-13T08:00:00Z",
            12.0,
            12000,
            4000,
            None,
            None,
            None,
            None,
            None,
            "",
            run_points,
            "",
        ),
    )


class CareerRecordsV2CandidateWriteTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        create_activity_schema(self.conn)
        seed_first_batch_activities(self.conn)
        career_backend.ensure_career_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def table_counts(self):
        return {
            table: int(self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("career_pb_records", "career_event_candidates", "career_record_events")
        }

    def test_candidate_write_dry_run_is_read_only_and_rejects_excluded_items(self):
        before = self.table_counts()

        plan = career_backend.apply_records_v2_candidate_write(
            {"dry_run": True, "sport": "all", "max_activities": 20},
            conn=self.conn,
        )

        self.assertTrue(plan["dry_run"])
        self.assertGreaterEqual(plan["summary"]["planned"], 7)
        self.assertEqual(self.table_counts(), before)
        rejected_keys = {item["record_key"] for item in plan["rejected"]}
        self.assertIn("cycling_max_work", rejected_keys)
        self.assertTrue(any("not_best_for_record_key" in item["reason_codes"] for item in plan["rejected"]))
        self.assertTrue(all(candidate["record_key"] in career_backend.RECORDS_V2_FIRST_BATCH_CANDIDATE_WRITE_KEYS for candidate in plan["candidates"]))
        assert_safe(self, plan)

    def test_running_5k_10k_best_effort_can_be_planned_as_candidates(self):
        seed_running_best_effort_activities(self.conn)
        before = self.table_counts()

        plan = career_backend.apply_records_v2_candidate_write(
            {
                "dry_run": True,
                "sport": "running",
                "record_keys": ["running_5k", "running_10k"],
                "max_activities": 20,
            },
            conn=self.conn,
        )

        self.assertTrue(plan["dry_run"])
        self.assertEqual(self.table_counts(), before)
        planned_by_key = {candidate["record_key"]: candidate for candidate in plan["candidates"]}
        self.assertEqual(set(planned_by_key), {"running_5k", "running_10k"})
        for candidate in planned_by_key.values():
            self.assertEqual(candidate["activity_id"], "run-best-effort")
            self.assertEqual(candidate["source_mode"], "best_effort_distance")
            self.assertGreaterEqual(candidate["confidence"], 0.92)
            evidence = candidate["evidence"]
            self.assertEqual(evidence["source_mode"], "best_effort_distance")
            self.assertTrue(evidence["range_json"])
            self.assertEqual((evidence.get("quality") or {}).get("decision"), "preview")
        assert_safe(self, plan)

    def test_running_5k_10k_candidate_apply_writes_only_candidate_table(self):
        seed_running_best_effort_activities(self.conn)
        before = self.table_counts()

        result = career_backend.apply_records_v2_candidate_write(
            {
                "dry_run": False,
                "sport": "running",
                "record_keys": ["running_5k", "running_10k"],
                "max_activities": 20,
            },
            conn=self.conn,
        )
        after = self.table_counts()

        self.assertFalse(result["dry_run"])
        self.assertEqual(result["summary"]["inserted"], 2)
        self.assertEqual(after["career_pb_records"], before["career_pb_records"])
        self.assertEqual(after["career_record_events"], before["career_record_events"])
        self.assertEqual(after["career_event_candidates"], before["career_event_candidates"] + 2)
        payloads = [
            json.loads(row[0])
            for row in self.conn.execute(
                "SELECT evidence_json FROM career_event_candidates WHERE candidate_type = 'pb_record'"
            ).fetchall()
        ]
        self.assertEqual({payload["record_evidence"]["record_key"] for payload in payloads}, {"running_5k", "running_10k"})
        self.assertTrue(all(payload["record_evidence"]["source_mode"] == "best_effort_distance" for payload in payloads))
        assert_safe(self, result)

    def test_validation_required_distance_keys_remain_rejected(self):
        item = {
            "record_key": "cycling_fastest_10k",
            "activity_id": "ride-best",
            "sport": "cycling",
            "status": "preview_candidate",
            "source_mode": "best_effort_distance",
            "range": {"start_sec": 0, "end_sec": 1200, "duration_sec": 1200, "distance_m": 10000},
            "quality": {
                "confidence": 0.92,
                "decision": "validation_required",
                "reason_codes": ["best_effort_distance_window", "validation_required"],
                "blocks_active": True,
            },
        }

        reasons = career_backend._records_v2_candidate_write_rejection_reasons(
            item,
            allowed_record_keys={"cycling_fastest_10k"},
        )

        self.assertIn("validation_required", reasons)
        self.assertIn("blocks_active", reasons)
        self.assertIn("decision_not_auto_confirm", reasons)

    def test_candidate_write_apply_only_writes_candidate_table(self):
        before = self.table_counts()

        result = career_backend.apply_records_v2_candidate_write(
            {"dry_run": False, "sport": "all", "max_activities": 20},
            conn=self.conn,
        )
        after = self.table_counts()

        self.assertFalse(result["dry_run"])
        self.assertEqual(result["summary"]["inserted"], result["summary"]["planned"])
        self.assertGreaterEqual(result["summary"]["inserted"], 7)
        self.assertEqual(after["career_pb_records"], before["career_pb_records"])
        self.assertEqual(after["career_record_events"], before["career_record_events"])
        self.assertEqual(after["career_event_candidates"], before["career_event_candidates"] + result["summary"]["inserted"])
        row = self.conn.execute(
            "SELECT evidence_json FROM career_event_candidates WHERE candidate_type = 'pb_record' LIMIT 1"
        ).fetchone()
        payload = json.loads(row[0])
        self.assertEqual(payload["candidate_write"]["write_scope"], "career_event_candidates_only")
        self.assertIn(payload["record_key"], career_backend.RECORDS_V2_FIRST_BATCH_CANDIDATE_WRITE_KEYS)
        assert_safe(self, result)

    def test_candidate_write_is_idempotent_for_same_plan(self):
        first = career_backend.apply_records_v2_candidate_write(
            {"dry_run": False, "sport": "all", "max_activities": 20},
            conn=self.conn,
        )
        second = career_backend.apply_records_v2_candidate_write(
            {"dry_run": False, "sport": "all", "max_activities": 20},
            conn=self.conn,
        )

        self.assertGreaterEqual(first["summary"]["inserted"], 7)
        self.assertEqual(second["summary"]["inserted"], 0)
        self.assertEqual(second["summary"]["skipped"], first["summary"]["inserted"])
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM career_pb_records").fetchone()[0],
            0,
        )
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM career_record_events").fetchone()[0],
            0,
        )

    def test_candidate_write_refuses_default_connection(self):
        result = career_backend.apply_records_v2_candidate_write({"dry_run": False}, conn=None)

        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "explicit_connection_required")

    def test_candidate_write_refuses_real_db_target_without_da12_authorization(self):
        with mock.patch.object(career_backend, "_records_v2_candidate_write_targets_default_real_db", return_value=True):
            result = career_backend.apply_records_v2_candidate_write({"dry_run": False}, conn=self.conn)

        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "real_db_write_not_authorized")
        self.assertEqual(self.table_counts(), {"career_pb_records": 0, "career_event_candidates": 0, "career_record_events": 0})


if __name__ == "__main__":
    unittest.main()
