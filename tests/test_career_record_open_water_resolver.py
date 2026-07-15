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


class CareerRecordOpenWaterResolverTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")

    def tearDown(self):
        self.conn.close()

    def test_open_water_750m_boundary_is_inclusive_and_gps_jump_candidate(self):
        case = fixture_case("open_water_750m_boundary_and_gps_jump")

        plan = career_backend.apply_open_water_records(
            self.conn,
            activity=case["activity"],
            track_points_xy=case["input"]["track_points_xy"],
            dry_run=True,
        )

        keys = {evidence["record_key"] for evidence in plan["evidences"]}
        self.assertIn("open_water_swim_750m", keys)
        evidence = next(item for item in plan["evidences"] if item["record_key"] == "open_water_swim_750m")
        self.assertEqual(evidence["metric"]["value"], 1500)
        self.assertIn("open_water_gps_unreliable", evidence["quality"]["reason_codes"])
        self.assertEqual(evidence["scope_json"], {"water_scope": "open_water_swimming"})
        self.assertTrue(any(item["record_key"] == "open_water_swim_1500m" for item in plan["skipped"]))

    def test_open_water_records_are_candidate_only_not_active(self):
        case = fixture_case("open_water_750m_boundary_and_gps_jump")

        result = career_backend.apply_open_water_records(
            self.conn,
            activity=case["activity"],
            track_points_xy=case["input"]["track_points_xy"],
            dry_run=False,
            run_id="open-water",
        )

        self.assertEqual(result["summary"], {"candidate_created": 3})
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM career_pb_records WHERE status = 'active'").fetchone()[0],
            0,
        )

    def test_pool_swim_does_not_mix_into_open_water(self):
        result = career_backend.apply_open_water_records(
            self.conn,
            activity={"activity_id": "pool", "sport_type": "swimming", "sub_sport_type": "lap_swimming", "pool_length_m": 25},
            dry_run=True,
        )

        self.assertEqual(result["planned_count"], 0)
        self.assertEqual(result["skipped"][0]["reason"], "pool_swim_scope")


if __name__ == "__main__":
    unittest.main()
