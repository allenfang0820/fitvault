import sqlite3
import unittest

import career_backend


def trail_activity(activity_id: str, **overrides):
    base = {
        "activity_id": activity_id,
        "sport_type": "trail_running",
        "distance_m": 30000,
        "ascent_m": 1800,
        "duration_sec": 18000,
        "max_altitude_m": 2600,
        "event_date": f"2026-07-{int(activity_id):02d}",
    }
    base.update(overrides)
    return base


TRACK = [
    {"d": 0, "t": 0, "alt_m": 100},
    {"d": 1000, "t": 900, "alt_m": 200},
    {"d": 3000, "t": 2700, "alt_m": 450},
    {"d": 5000, "t": 4500, "alt_m": 430},
]


class CareerRecordTrailActivityTotalTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")

    def tearDown(self):
        self.conn.close()

    def test_trail_activity_builds_five_candidate_only_evidences(self):
        plan = career_backend.apply_trail_activity_total_records(
            self.conn,
            activity=trail_activity("1"),
            track_points=TRACK,
            dry_run=True,
        )

        self.assertEqual(plan["planned_count"], 5)
        keys = {item["record_key"] for item in plan["evidences"]}
        self.assertEqual(
            keys,
            {
                "trail_longest_distance",
                "trail_max_ascent",
                "trail_longest_elapsed_time",
                "trail_max_altitude",
                "trail_max_single_climb",
            },
        )

    def test_road_running_hiking_and_mountaineering_are_excluded_even_with_trail_title(self):
        for sport in ("running", "hiking", "mountaineering"):
            with self.subTest(sport=sport):
                plan = career_backend.apply_trail_activity_total_records(
                    self.conn,
                    activity=trail_activity("1", sport_type=sport, title="trail day"),
                    track_points=TRACK,
                    dry_run=True,
                )
                self.assertEqual(plan["planned_count"], 0)

    def test_trail_records_apply_as_candidates_not_active(self):
        result = career_backend.apply_trail_activity_total_records(
            self.conn,
            activity=trail_activity("1"),
            track_points=TRACK,
            dry_run=False,
            run_id="trail",
        )

        self.assertEqual(result["summary"], {"candidate_created": 5})
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM career_pb_records WHERE status = 'active'").fetchone()[0],
            0,
        )


if __name__ == "__main__":
    unittest.main()
