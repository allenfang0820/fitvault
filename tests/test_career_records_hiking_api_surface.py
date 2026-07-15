import json
import sqlite3
import unittest

import career_backend


FORBIDDEN = ("track_json", "raw_fit", "clean_points", "file_path", "storage_ref", "/Users/", "weight_history")


def assert_safe(testcase: unittest.TestCase, payload):
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    for forbidden in FORBIDDEN:
        testcase.assertNotIn(forbidden, text)


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


class CareerRecordsHikingApiSurfaceTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            """
            CREATE TABLE activities (
                id INTEGER PRIMARY KEY,
                sport_type TEXT,
                start_time TEXT,
                deleted_at TEXT
            )
            """
        )
        self.conn.executemany(
            "INSERT INTO activities (id, sport_type, start_time, deleted_at) VALUES (?, 'hiking', ?, NULL)",
            [(1, "2026-07-01T00:00:00Z"), (2, "2026-07-02T00:00:00Z")],
        )
        self.first = hiking_activity("1", distance_m=18000, ascent_m=900, duration_sec=14400, max_altitude_m=3200)
        self.second = hiking_activity("2", distance_m=22000, ascent_m=1200, duration_sec=16000, max_altitude_m=3500)
        self.track = [
            {"d": 0, "t": 0, "alt_m": 120},
            {"d": 1000, "t": 1200, "alt_m": 200},
            {"d": 3000, "t": 3600, "alt_m": 420},
            {"d": 5000, "t": 6000, "alt_m": 400},
        ]
        career_backend.apply_hiking_activity_total_records(self.conn, activity=self.first, dry_run=False)
        career_backend.apply_hiking_activity_total_records(self.conn, activity=self.second, dry_run=False)
        career_backend.apply_hiking_single_climb_record(self.conn, activity=self.second, track_points=self.track, dry_run=False)

    def tearDown(self):
        self.conn.close()

    def test_hiking_catalog_has_hiking_group_without_walking_mountaineering_placeholders(self):
        catalog = career_backend.get_career_record_catalog({"sport": "hiking"})
        sport = catalog["sports"][0]

        self.assertEqual(sport["sport"], "hiking")
        self.assertEqual([group["group_key"] for group in sport["groups"]], ["hiking_activity_total"])
        keys = [record["record_key"] for record in sport["groups"][0]["records"]]
        self.assertIn("hiking_max_single_climb", keys)
        self.assertNotIn("walking", json.dumps(catalog, ensure_ascii=False))
        self.assertNotIn("mountaineering", json.dumps(catalog, ensure_ascii=False))
        assert_safe(self, catalog)

    def test_hiking_records_detail_history_candidates_and_fallback_are_safe(self):
        records = career_backend.get_career_records({"sport": "hiking"}, conn=self.conn)
        self.assertEqual(len(records["records"]), 4)
        self.assertTrue(all(record["activity_id"] == "2" for record in records["records"]))
        self.assertFalse(any(record["record_key"] == "hiking_max_single_climb" for record in records["records"]))

        distance = next(record for record in records["records"] if record["record_key"] == "hiking_longest_distance")
        detail = career_backend.get_career_record_detail({"record_id": distance["id"]}, conn=self.conn)
        history = career_backend.get_career_record_history(
            {"record_key": "hiking_longest_distance", "scope_hash": distance["scope"]["scope_hash"]},
            conn=self.conn,
        )
        candidates = career_backend.get_career_record_candidates({"sport": "hiking"}, conn=self.conn)
        self.assertEqual(detail["record"]["sport"], "hiking")
        self.assertEqual(history["history_summary"]["axis_direction"], "higher")
        self.assertTrue(any(candidate["record_key"] == "hiking_max_single_climb" for candidate in candidates["candidates"]))

        invalidated = career_backend.invalidate_career_record_state_for_activity(
            self.conn,
            "2",
            dry_run=False,
            reason="test_hiking_deleted",
        )
        self.assertEqual(len(invalidated["promoted"]), 4)
        fallback = career_backend.get_career_records({"sport": "hiking"}, conn=self.conn)
        self.assertTrue(all(record["activity_id"] == "1" for record in fallback["records"]))
        assert_safe(self, records)
        assert_safe(self, detail)
        assert_safe(self, history)
        assert_safe(self, candidates)


if __name__ == "__main__":
    unittest.main()
