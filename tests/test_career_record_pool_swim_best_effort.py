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


class CareerRecordPoolSwimBestEffortTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")

    def tearDown(self):
        self.conn.close()

    def test_pool_25m_freestyle_best_50m_and_rest_breaks_100m(self):
        case = fixture_case("pool_swim_25m_freestyle_with_rest")

        plan = career_backend.apply_pool_swim_best_effort_records(
            self.conn,
            activity=case["activity"],
            lengths=case["input"]["lengths"],
            target_distances_m=(50, 100),
            dry_run=True,
        )

        self.assertEqual(plan["planned_count"], 1)
        evidence = plan["evidences"][0]
        self.assertEqual(evidence["record_key"], "pool_swim_50m")
        self.assertEqual(evidence["metric"]["value"], 63)
        self.assertEqual(evidence["scope_json"]["pool_length_scope"], "scm_25m")
        self.assertEqual(evidence["scope_json"]["stroke_scope"], "freestyle")
        self.assertEqual(evidence["range_json"]["length_start"], 0)
        self.assertEqual(evidence["range_json"]["length_end"], 1)
        self.assertTrue(any(item["record_key"] == "pool_swim_100m" and item["reason"] == "pool_rest_break" for item in plan["skipped"]))

    def test_validation_required_pool_evidence_becomes_candidate_not_active(self):
        case = fixture_case("pool_swim_25m_freestyle_with_rest")

        result = career_backend.apply_pool_swim_best_effort_records(
            self.conn,
            activity=case["activity"],
            lengths=case["input"]["lengths"],
            target_distances_m=(50,),
            dry_run=False,
            run_id="pool:50m",
        )

        self.assertEqual(result["summary"], {"candidate_created": 1})
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM career_pb_records WHERE status = 'active'").fetchone()[0],
            0,
        )

    def test_missing_pool_length_creates_no_best_effort_evidence(self):
        case = fixture_case("pool_swim_missing_pool_length_unknown_stroke")

        plan = career_backend.apply_pool_swim_best_effort_records(
            self.conn,
            activity=case["activity"],
            lengths=case["input"]["lengths"],
            target_distances_m=(50,),
            dry_run=True,
        )

        self.assertEqual(plan["planned_count"], 0)
        self.assertEqual(plan["skipped"][0]["reason"], "pool_length_missing")


if __name__ == "__main__":
    unittest.main()
