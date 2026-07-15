import sqlite3
import unittest

import career_backend


def hiking_activity(activity_id: str, **overrides):
    base = {
        "activity_id": activity_id,
        "sport_type": "hiking",
        "distance_m": 18000,
        "ascent_m": 900,
        "duration_sec": 14400,
        "max_altitude_m": 3200,
        "event_date": f"2026-07-{int(activity_id):02d}",
    }
    base.update(overrides)
    return base


class CareerRecordHikingActivityTotalTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")

    def tearDown(self):
        self.conn.close()

    def test_hiking_activity_builds_four_activity_total_evidences(self):
        plan = career_backend.apply_hiking_activity_total_records(
            self.conn,
            activity=hiking_activity("1"),
            dry_run=True,
        )

        self.assertTrue(plan["dry_run"])
        self.assertEqual(plan["planned_count"], 4)
        keys = {item["record_key"] for item in plan["evidences"]}
        self.assertEqual(
            keys,
            {
                "hiking_longest_distance",
                "hiking_max_ascent",
                "hiking_longest_elapsed_time",
                "hiking_max_altitude",
            },
        )
        self.assertTrue(all(item["scope_json"] == {"sport_scope": "hiking"} for item in plan["evidences"]))

    def test_walking_mountaineering_and_trail_are_excluded_even_when_title_mentions_hiking(self):
        cases = [
            ("walking", "walking_scope_excluded"),
            ("mountaineering", "mountaineering_scope_excluded"),
            ("trail_running", "record_definition_conflict"),
        ]
        for sport, reason in cases:
            with self.subTest(sport=sport):
                plan = career_backend.apply_hiking_activity_total_records(
                    self.conn,
                    activity=hiking_activity("1", sport_type=sport, title="周末 hiking"),
                    dry_run=True,
                )
                self.assertEqual(plan["planned_count"], 0)
                self.assertEqual(plan["skipped"][0]["reason"], reason)

    def test_duration_fallback_is_candidate_when_time_semantics_unknown(self):
        activity = hiking_activity("1")
        activity.pop("duration_sec")
        activity["duration"] = 14400

        plan = career_backend.apply_hiking_activity_total_records(
            self.conn,
            activity=activity,
            dry_run=True,
        )

        elapsed = next(item for item in plan["evidences"] if item["record_key"] == "hiking_longest_elapsed_time")
        self.assertEqual(elapsed["quality"]["decision"], "candidate")
        self.assertIn("duration_semantics_unknown", elapsed["quality"]["reason_codes"])

    def test_apply_hiking_records_replace_higher_totals(self):
        first = hiking_activity("1", distance_m=18000, ascent_m=900, duration_sec=14400, max_altitude_m=3200)
        second = hiking_activity("2", distance_m=22000, ascent_m=1200, duration_sec=16000, max_altitude_m=3500)

        first_result = career_backend.apply_hiking_activity_total_records(
            self.conn,
            activity=first,
            dry_run=False,
            run_id="hiking:first",
        )
        second_result = career_backend.apply_hiking_activity_total_records(
            self.conn,
            activity=second,
            dry_run=False,
            run_id="hiking:second",
        )

        self.assertEqual(first_result["summary"], {"activated": 4})
        self.assertEqual(second_result["summary"], {"activated": 4})
        records = career_backend.get_career_records({"sport": "hiking"}, conn=self.conn)["records"]
        self.assertEqual(len(records), 4)
        self.assertTrue(all(record["activity_id"] == "2" for record in records))


if __name__ == "__main__":
    unittest.main()
