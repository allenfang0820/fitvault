import json
import sqlite3
import unittest

import career_backend


FORBIDDEN = (
    "track_points",
    "points_xy",
    "raw_points",
    "gps_points",
    "track_json",
    "polyline",
    "file_path",
    "storage_ref",
    "device_serial",
    "serial_number",
    "weight_history",
    "route_signature",
    "/Users/",
    "file://",
)


def assert_safe(testcase: unittest.TestCase, payload):
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    for forbidden in FORBIDDEN:
        testcase.assertNotIn(forbidden, text)


def _activity(activity_id: str, elapsed=5400):
    return {
        "activity_id": activity_id,
        "sport_type": "trail_running",
        "distance_m": 10_000,
        "ascent_m": 720,
        "duration_sec": elapsed,
        "max_altitude_m": 1800,
        "event_date": "2026-07-14",
    }


class CareerRecordsTrailApiSurfaceTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.activity = _activity("trail-api-target")
        career_backend.apply_trail_activity_total_records(
            self.conn,
            activity=self.activity,
            track_points=[
                {"distance_m": 0, "altitude_m": 1000, "t_sec": 0},
                {"distance_m": 5000, "altitude_m": 1300, "t_sec": 2500},
                {"distance_m": 10000, "altitude_m": 1200, "t_sec": 5400},
            ],
            dry_run=False,
            run_id="trail:activity",
        )

    def tearDown(self):
        self.conn.close()

    def test_trail_catalog_only_exposes_non_route_records(self):
        catalog = career_backend.get_career_record_catalog({"sport": "trail_running", "include_unavailable": True})
        sport = catalog["sports"][0]
        groups = {group["group_key"]: group for group in sport["groups"]}

        self.assertIn("trail_activity_total", groups)
        self.assertNotIn("trail_route_segment", groups)
        self.assertEqual(sport["capabilities"]["activity_total_records"]["state"], "candidate_only")
        self.assertNotIn("route_segment_pr", sport["capabilities"])
        self.assertNotIn("pace_gap_curve", sport["capabilities"])
        record_keys = {
            record["record_key"]
            for group in sport["groups"]
            for record in group["records"]
        }
        self.assertEqual(
            record_keys,
            {
                "trail_longest_distance",
                "trail_max_ascent",
                "trail_longest_elapsed_time",
                "trail_max_altitude",
                "trail_max_single_climb",
            },
        )
        assert_safe(self, catalog)

    def test_trail_candidates_only_include_activity_total_records(self):
        records = career_backend.get_career_records({"sport": "trail_running"}, conn=self.conn)
        candidates = career_backend.get_career_record_candidates({"sport": "trail_running"}, conn=self.conn)

        self.assertEqual(records["records"], [])
        self.assertGreaterEqual(len(candidates["candidates"]), 5)
        candidate_keys = {candidate["record_key"] for candidate in candidates["candidates"]}
        self.assertIn("trail_longest_distance", candidate_keys)
        self.assertNotIn("trail_route_best_time", candidate_keys)
        self.assertNotIn("trail_segment_best_time", candidate_keys)
        self.assertNotIn("trail_climb_segment_best_time", candidate_keys)
        assert_safe(self, records)
        assert_safe(self, candidates)

    def test_contract_excludes_trail_route_comparison_api(self):
        contract = json.loads(open("docs/js_api_contract.json", encoding="utf-8").read())
        methods = {item["name"]: item for item in contract["methods"]}

        self.assertNotIn("get_trail_route_comparison", methods)
        self.assertIn("不属于当前记录中心", methods["get_career_record_catalog"]["description"])
        self.assertNotIn("Pace/GAP analysis-only", methods["get_career_record_catalog"]["description"])


if __name__ == "__main__":
    unittest.main()
