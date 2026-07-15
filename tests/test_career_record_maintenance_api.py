import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import career_backend
import main
import profile_backend


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = PROJECT_ROOT / "docs" / "js_api_contract.json"


def _decision(activity_id: str = "1") -> dict:
    summary = {
        "activity_id": activity_id,
        "sport": "running",
        "source_mode": "activity_total",
        "event_date": "2026-07-01",
        "distance_m": 5000,
        "elapsed_time_sec": 1500,
        "distance_quality": "reliable_distance",
        "time_quality": "semantics_unknown",
        "reason_codes": ("duration_semantics_unknown",),
    }
    match = career_backend.match_record_definition(summary)
    return career_backend.build_record_candidate_decision(summary, match)


class CareerRecordMaintenanceApiTest(unittest.TestCase):
    def test_pb_candidate_decision_wrapper_confirms_and_rejects(self):
        original_db_path = profile_backend.DB_PATH
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                profile_backend.DB_PATH = Path(tmpdir) / "records-api.sqlite"
                conn = sqlite3.connect(str(profile_backend.DB_PATH))
                try:
                    candidate = career_backend.apply_record_candidate_decision(conn, _decision("1"))
                    rejected = career_backend.apply_record_candidate_decision(conn, _decision("2"))
                    conn.commit()
                finally:
                    conn.close()

                api = main.Api()
                confirm = api.decide_career_pb_candidate({"candidate_id": candidate["candidate_id"], "decision": "confirm"})
                reject = api.decide_career_pb_candidate({"candidate_id": rejected["candidate_id"], "decision": "reject"})
                invalid = api.decide_career_pb_candidate({"candidate_id": rejected["candidate_id"], "decision": "confirm"})

                self.assertTrue(confirm["ok"])
                self.assertEqual(confirm["data"]["action"], "activated")
                self.assertIn("elapsed_ms", confirm["data"]["metrics"])
                self.assertTrue(reject["ok"])
                self.assertEqual(reject["data"]["action"], "rejected")
                self.assertIn("elapsed_ms", reject["data"]["metrics"])
                self.assertFalse(invalid["ok"])
                self.assertEqual(invalid["code"], main.API_CODE_VALIDATION)
            finally:
                profile_backend.DB_PATH = original_db_path

    def test_rebuild_and_record_events_wrappers(self):
        original_db_path = profile_backend.DB_PATH
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                profile_backend.DB_PATH = Path(tmpdir) / "records-api.sqlite"
                conn = sqlite3.connect(str(profile_backend.DB_PATH))
                try:
                    career_backend.ensure_career_schema(conn)
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
                    conn.execute(
                        """
                        INSERT INTO activities
                            (id, sport_type, sub_sport_type, start_time, start_time_utc,
                             dist_km, distance, duration, duration_sec, deleted_at, updated_at)
                        VALUES
                            (1, 'running', 'generic', '2026-07-01T08:00:00+08:00',
                             '2026-07-01T00:00:00Z', 5.0, 5000.0, 1500, 1500, NULL,
                             '2026-07-01T08:00:00+08:00')
                        """
                    )
                    conn.commit()
                finally:
                    conn.close()

                api = main.Api()
                dry_run = api.rebuild_career_pb_records({"dry_run": True, "resolver_version": "records-v1-api"})
                apply = api.rebuild_career_pb_records({"dry_run": False, "resolver_version": "records-v1-api"})
                events = api.get_career_record_events({"pb_type": "running_5k"})

                self.assertTrue(dry_run["ok"])
                self.assertTrue(dry_run["data"]["dry_run"])
                self.assertEqual(dry_run["data"]["resolver_version"], "records-v1-api")
                self.assertIn("elapsed_ms", dry_run["data"]["metrics"])
                self.assertIn("reason_counts", dry_run["data"]["metrics"])
                self.assertTrue(apply["ok"])
                self.assertFalse(apply["data"]["dry_run"])
                self.assertIn("elapsed_ms", apply["data"]["metrics"])
                self.assertTrue(events["ok"])
                self.assertGreaterEqual(len(events["data"]["events"]), 1)
                self.assertIn("elapsed_ms", events["data"]["metrics"])
            finally:
                profile_backend.DB_PATH = original_db_path

    def test_js_api_contract_registers_record_maintenance_methods(self):
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        methods = {item["name"]: item for item in contract["methods"]}

        self.assertFalse(methods["decide_career_pb_candidate"]["readonly"])
        self.assertTrue(methods["decide_career_pb_candidate"]["high_risk"])
        self.assertFalse(methods["rebuild_career_pb_records"]["readonly"])
        self.assertTrue(methods["rebuild_career_pb_records"]["high_risk"])
        self.assertTrue(methods["get_career_record_events"]["readonly"])
        self.assertFalse(methods["get_career_record_events"]["high_risk"])
        self.assertIn("metrics", methods["rebuild_career_pb_records"]["returns"])
        self.assertIn("metrics", methods["get_career_record_events"]["returns"])


if __name__ == "__main__":
    unittest.main()
