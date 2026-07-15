import json
import sqlite3
from pathlib import Path
import unittest

import career_backend


FIXTURES = Path("tests/fixtures/records_center_v2/golden_manifest.json")


def fixture_case(case_id: str) -> dict:
    manifest = json.loads(FIXTURES.read_text())
    for case in manifest["cases"]:
        if case["case_id"] == case_id:
            return case
    raise AssertionError(f"missing fixture case: {case_id}")


class CareerRecordHikingElevationClimbTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")

    def tearDown(self):
        self.conn.close()

    def test_elevation_spike_is_removed_and_single_climb_range_is_returned(self):
        case = fixture_case("hiking_elevation_spike_single_climb")

        result = career_backend.resolve_hiking_elevation_climb(case["input"]["track_points"])

        self.assertEqual(result["quality"], "candidate")
        self.assertEqual(result["spike_point_indexes"], [3])
        self.assertIn("elevation_spike_detected", result["reason_codes"])
        climb = result["max_single_climb"]
        self.assertEqual(climb["gain_m"], 400)
        self.assertEqual(climb["start"]["t_sec"], 0)
        self.assertEqual(climb["end"]["t_sec"], 5700)

    def test_single_climb_evidence_is_candidate_only_and_safe(self):
        case = fixture_case("hiking_elevation_spike_single_climb")

        plan = career_backend.apply_hiking_single_climb_record(
            self.conn,
            activity=case["activity"],
            track_points=case["input"]["track_points"],
            dry_run=True,
        )
        applied = career_backend.apply_hiking_single_climb_record(
            self.conn,
            activity=case["activity"],
            track_points=case["input"]["track_points"],
            dry_run=False,
            run_id="hiking:climb",
        )

        self.assertEqual(plan["planned_count"], 1)
        evidence = plan["evidence"]
        self.assertEqual(evidence["record_key"], "hiking_max_single_climb")
        self.assertEqual(evidence["metric"]["value"], 400)
        self.assertIn("start_sec", evidence["range_json"])
        self.assertEqual(applied["result"]["action"], "candidate_created")
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM career_pb_records WHERE status = 'active'").fetchone()[0],
            0,
        )
        self.assertNotIn("clean_points", json.dumps(plan, ensure_ascii=False))

    def test_missing_track_does_not_use_total_ascent_as_single_climb(self):
        activity = {
            "activity_id": "fixture:hiking:no_track",
            "sport_type": "hiking",
            "ascent_m": 900,
            "event_date": "2026-07-01",
        }

        plan = career_backend.apply_hiking_single_climb_record(
            self.conn,
            activity=activity,
            track_points=[],
            dry_run=True,
        )

        self.assertEqual(plan["planned_count"], 0)
        self.assertEqual(plan["skipped"][0]["reason"], "single_climb_range_missing")


if __name__ == "__main__":
    unittest.main()
