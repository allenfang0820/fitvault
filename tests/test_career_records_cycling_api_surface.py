import json
import sqlite3
import unittest

import career_backend


FORBIDDEN = (
    "clean_points",
    "power_points",
    "raw_fit",
    "fit_records",
    "track_json",
    "file_path",
    "storage_ref",
    "device_serial",
    "serial_number",
    "weight_history",
    "/Users/",
    "file://",
)


def assert_safe(testcase: unittest.TestCase, payload):
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    for forbidden in FORBIDDEN:
        testcase.assertNotIn(forbidden, text)


class CareerRecordsCyclingApiSurfaceTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.activity = {
            "activity_id": "1",
            "sport_type": "cycling",
            "indoor_scope": "outdoor",
            "distance_m": 120000,
            "ascent_m": 1500,
            "duration_sec": 7200,
            "event_date": "2026-07-01",
        }
        self.points = [{"t": 0, "power_w": 250}, {"t": 7200, "power_w": 250}]
        career_backend.apply_cycling_power_duration_records(
            self.conn,
            self.points,
            activity=self.activity,
            dry_run=False,
            run_id="api:power",
        )
        career_backend.apply_cycling_activity_total_records(
            self.conn,
            activity=self.activity,
            power_points=self.points,
            dry_run=False,
            run_id="api:total",
        )

    def tearDown(self):
        self.conn.close()

    def test_cycling_catalog_groups_and_capabilities_are_backend_driven(self):
        catalog = career_backend.get_career_record_catalog({"sport": "cycling"})
        sport = catalog["sports"][0]
        groups = {group["group_key"]: group for group in sport["groups"]}

        self.assertIn("cycling_standard_distance", groups)
        self.assertIn("cycling_power", groups)
        self.assertIn("cycling_activity_total", groups)
        standard_keys = {record["record_key"] for record in groups["cycling_standard_distance"]["records"]}
        self.assertEqual(
            standard_keys,
            {
                "cycling_fastest_10k",
                "cycling_fastest_20k",
                "cycling_fastest_40k",
                "cycling_fastest_50k",
                "cycling_fastest_100k",
                "cycling_fastest_180k",
            },
        )
        self.assertTrue(all(record["availability_state"] == "validation_required" for record in groups["cycling_standard_distance"]["records"]))
        self.assertEqual(sport["capabilities"]["standard_distance_records"]["state"], "validation_required")
        self.assertTrue(sport["capabilities"]["standard_distance_records"]["requires_distance_time_stream"])
        self.assertFalse(sport["capabilities"]["standard_distance_records"]["creates_active_record"])
        self.assertEqual(sport["capabilities"]["power_duration_curve"]["state"], "available")
        self.assertTrue(sport["capabilities"]["power_duration_curve"]["requires_point_power"])
        self.assertIn("cycling_power_2h", sport["capabilities"]["power_duration_curve"]["record_keys"])
        self.assertEqual(sport["capabilities"]["wkg"]["state"], "unavailable")
        self.assertFalse(sport["capabilities"]["wkg"]["creates_record"])
        self.assertIn("cycling_max_work", sport["capabilities"]["activity_total_records"]["validation_required_record_keys"])
        assert_safe(self, catalog)

    def test_records_detail_history_curve_and_candidates_are_safe_for_cycling(self):
        records = career_backend.get_career_records({"sport": "cycling"}, conn=self.conn)
        power_records = [record for record in records["records"] if record["family"] == "power_duration_pb"]
        standard_records = [record for record in records["records"] if record["record_key"].startswith("cycling_fastest_")]
        total_records = [record for record in records["records"] if record["family"] == "activity_total_record"]
        self.assertEqual(len(power_records), 9)
        self.assertEqual(len(standard_records), 0)
        self.assertEqual(len(total_records), 3)
        self.assertTrue(all(record["detail_link"]["source"] == "career" for record in records["records"]))

        record = next(item for item in power_records if item["record_key"] == "cycling_power_5s")
        detail = career_backend.get_career_record_detail({"record_id": record["id"]}, conn=self.conn)
        history = career_backend.get_career_record_history(
            {"record_key": "cycling_power_5s", "scope_hash": record["scope"]["scope_hash"]},
            conn=self.conn,
        )
        curve = career_backend.get_career_record_curve(
            {"activity_id": "1", "curve_type": "cycling_power_duration_curve", "scope_hash": record["scope"]["scope_hash"]},
            conn=self.conn,
        )
        candidates = career_backend.get_career_record_candidates({"status": "candidate"}, conn=self.conn)

        self.assertEqual(detail["record"]["record_key"], "cycling_power_5s")
        self.assertEqual(history["history_summary"]["axis_direction"], "higher")
        self.assertEqual(curve["curve"]["anchors"][0]["unit"], "watts")
        self.assertTrue(any(candidate["record_key"] == "cycling_max_work" for candidate in candidates["candidates"]))
        assert_safe(self, records)
        assert_safe(self, detail)
        assert_safe(self, history)
        assert_safe(self, curve)
        assert_safe(self, candidates)


if __name__ == "__main__":
    unittest.main()
