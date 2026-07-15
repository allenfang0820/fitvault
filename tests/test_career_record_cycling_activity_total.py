import sqlite3
import unittest

import career_backend


def cycling_activity(activity_id: str, **overrides):
    base = {
        "activity_id": activity_id,
        "sport_type": "cycling",
        "indoor_scope": "outdoor",
        "distance_m": 100000,
        "ascent_m": 1200,
        "duration_sec": 7200,
        "event_date": f"2026-07-{int(activity_id):02d}",
    }
    base.update(overrides)
    return base


class CareerRecordCyclingActivityTotalTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")

    def tearDown(self):
        self.conn.close()

    def test_dry_run_builds_activity_total_evidences_and_blocks_wkg_without_history(self):
        activity = cycling_activity("1")
        points = [{"t": 0, "power_w": 200}, {"t": 7200, "power_w": 200}]

        plan = career_backend.apply_cycling_activity_total_records(
            self.conn,
            activity=activity,
            power_points=points,
            dry_run=True,
        )

        self.assertTrue(plan["dry_run"])
        self.assertEqual(plan["planned_count"], 4)
        self.assertEqual(plan["wkg_gate"]["state"], "unavailable")
        self.assertFalse(plan["wkg_gate"]["evidence_created"])
        keys = {item["record_key"] for item in plan["evidences"]}
        self.assertEqual(
            keys,
            {
                "cycling_longest_distance",
                "cycling_max_ascent",
                "cycling_longest_elapsed_time",
                "cycling_max_work",
            },
        )
        work = next(item for item in plan["evidences"] if item["record_key"] == "cycling_max_work")
        self.assertEqual(work["metric"]["value"], 1440.0)

    def test_activity_total_records_apply_and_work_stays_candidate(self):
        first = cycling_activity("1", distance_m=100000, ascent_m=1200, duration_sec=7200)
        second = cycling_activity("2", distance_m=120000, ascent_m=1500, duration_sec=8000)

        first_result = career_backend.apply_cycling_activity_total_records(
            self.conn,
            activity=first,
            power_points=[{"t": 0, "power_w": 200}, {"t": 7200, "power_w": 200}],
            dry_run=False,
            run_id="test:first",
        )
        second_result = career_backend.apply_cycling_activity_total_records(
            self.conn,
            activity=second,
            power_points=[{"t": 0, "power_w": 210}, {"t": 8000, "power_w": 210}],
            dry_run=False,
            run_id="test:second",
        )

        self.assertEqual(first_result["summary"], {"activated": 3, "candidate_created": 1})
        self.assertEqual(second_result["summary"], {"activated": 3, "candidate_created": 1})
        records = career_backend.get_career_records({"sport": "cycling"}, conn=self.conn)["records"]
        active_keys = {record["record_key"] for record in records}
        self.assertEqual(
            active_keys,
            {"cycling_longest_distance", "cycling_max_ascent", "cycling_longest_elapsed_time"},
        )
        self.assertTrue(all(record["activity_id"] == "2" for record in records))
        candidates = career_backend.get_career_record_candidates({"status": "candidate"}, conn=self.conn)["candidates"]
        self.assertTrue(any(candidate["record_key"] == "cycling_max_work" for candidate in candidates))

    def test_indoor_missing_distance_and_ascent_are_not_zero_records(self):
        activity = cycling_activity(
            "1",
            indoor_scope="trainer",
            distance_m=None,
            distance=None,
            ascent_m=None,
            total_ascent=None,
            duration_sec=3600,
        )

        plan = career_backend.apply_cycling_activity_total_records(
            self.conn,
            activity=activity,
            power_points=[{"t": 0, "power_w": 180}, {"t": 3600, "power_w": 180}],
            dry_run=True,
        )

        keys = {item["record_key"] for item in plan["evidences"]}
        self.assertNotIn("cycling_longest_distance", keys)
        self.assertNotIn("cycling_max_ascent", keys)
        skipped = {item["record_key"]: item["reason"] for item in plan["skipped"]}
        self.assertEqual(skipped["cycling_longest_distance"], "not_applicable_indoor_metric_missing")
        self.assertEqual(skipped["cycling_max_ascent"], "not_applicable_indoor_metric_missing")

    def test_wkg_gate_requires_activity_date_nearby_historical_weight(self):
        missing = career_backend.resolve_cycling_wkg_gate(cycling_activity("1"))
        available = career_backend.resolve_cycling_wkg_gate(
            cycling_activity("1"),
            weight_history=[{"date": "2026-07-02", "weight_kg": 70}],
        )

        self.assertEqual(missing["state"], "unavailable")
        self.assertEqual(missing["reason_codes"], ["historical_weight_missing"])
        self.assertEqual(available["state"], "available")
        self.assertFalse(available["evidence_created"])
        self.assertIn("wkg_registry_not_enabled", available["reason_codes"])

    def test_ebike_activity_total_is_excluded(self):
        plan = career_backend.apply_cycling_activity_total_records(
            self.conn,
            activity=cycling_activity("1", sport_type="e_biking"),
            power_points=[{"t": 0, "power_w": 180}, {"t": 3600, "power_w": 180}],
            dry_run=True,
        )

        self.assertEqual(plan["planned_count"], 0)
        self.assertEqual(plan["skipped"][0]["reason"], "ebike_scope_excluded")


if __name__ == "__main__":
    unittest.main()
