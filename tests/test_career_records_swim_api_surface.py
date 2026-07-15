import json
import sqlite3
from pathlib import Path
import unittest

import career_backend


FIXTURES = Path("tests/fixtures/records_center_v2/golden_manifest.json")
FORBIDDEN = ("track_json", "raw_fit", "clean_points", "file_path", "storage_ref", "/Users/", "weight_history")


def fixture_case(case_id: str) -> dict:
    manifest = json.loads(FIXTURES.read_text())
    for case in manifest["cases"]:
        if case["case_id"] == case_id:
            return case
    raise AssertionError(f"missing fixture case: {case_id}")


def assert_safe(testcase: unittest.TestCase, payload):
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    for forbidden in FORBIDDEN:
        testcase.assertNotIn(forbidden, text)


class CareerRecordsSwimApiSurfaceTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        pool = fixture_case("pool_swim_25m_freestyle_with_rest")
        open_water = fixture_case("open_water_750m_boundary_and_gps_jump")
        career_backend.apply_pool_swim_best_effort_records(
            self.conn,
            activity=pool["activity"],
            lengths=pool["input"]["lengths"],
            target_distances_m=(50, 100),
            dry_run=False,
        )
        career_backend.apply_open_water_records(
            self.conn,
            activity=open_water["activity"],
            track_points_xy=open_water["input"]["track_points_xy"],
            dry_run=False,
        )

    def tearDown(self):
        self.conn.close()

    def test_swim_catalog_separates_pool_and_open_water(self):
        pool_catalog = career_backend.get_career_record_catalog({"sport": "pool_swimming"})
        open_catalog = career_backend.get_career_record_catalog({"sport": "open_water_swimming"})

        pool_records = pool_catalog["sports"][0]["groups"][0]["records"]
        open_records = [record for group in open_catalog["sports"][0]["groups"] for record in group["records"]]
        self.assertTrue(all(record["availability_state"] == "validation_required" for record in pool_records))
        self.assertTrue(any(record["availability_state"] == "candidate_only" for record in open_records))
        assert_safe(self, pool_catalog)
        assert_safe(self, open_catalog)

    def test_swim_candidates_are_safe_and_no_active_records_are_created(self):
        pool_records = career_backend.get_career_records({"sport": "pool_swimming"}, conn=self.conn)
        open_records = career_backend.get_career_records({"sport": "open_water_swimming"}, conn=self.conn)
        candidates = career_backend.get_career_record_candidates({"status": "candidate"}, conn=self.conn)

        self.assertEqual(pool_records["records"], [])
        self.assertEqual(open_records["records"], [])
        candidate_keys = {candidate["record_key"] for candidate in candidates["candidates"]}
        self.assertIn("pool_swim_50m", candidate_keys)
        self.assertIn("open_water_swim_750m", candidate_keys)
        pool_candidate = next(candidate for candidate in candidates["candidates"] if candidate["record_key"] == "pool_swim_50m")
        self.assertEqual(pool_candidate["scope"]["dimensions"]["water_scope"], "pool_swimming")
        self.assertEqual(pool_candidate["scope"]["dimensions"]["pool_length_scope"], "scm_25m")
        assert_safe(self, candidates)


if __name__ == "__main__":
    unittest.main()
