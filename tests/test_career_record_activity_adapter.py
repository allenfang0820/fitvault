import json
import unittest

import career_backend


def _base_activity(**overrides):
    data = {
        "id": "activity-1",
        "sport_type": "running",
        "sub_sport_type": "",
        "start_time": "2026-07-16T08:00:00Z",
        "dist_km": 10.0,
        "duration_sec": 3600,
        "points_json": json.dumps([{"distance_m": 0, "t_sec": 0}, {"distance_m": 10000, "t_sec": 3600}]),
    }
    data.update(overrides)
    return data


class ActivityRecordFactsAdapterTest(unittest.TestCase):
    def test_running_activity_maps_to_running_with_distance_stream(self):
        facts = career_backend.build_activity_record_facts(_base_activity())

        self.assertEqual(facts["sport"], "running")
        self.assertEqual(facts["activity_id"], "activity-1")
        self.assertEqual(facts["distance_m"], 10000.0)
        self.assertTrue(facts["distance_time_stream_available"])
        self.assertNotIn("distance_time_stream_missing", facts["reason_codes"])

    def test_cycling_activity_maps_to_cycling_and_detects_power(self):
        facts = career_backend.build_activity_record_facts(_base_activity(
            sport_type="cycling",
            avg_power=220,
        ))

        self.assertEqual(facts["sport"], "cycling")
        self.assertTrue(facts["power_stream_available"])
        self.assertNotIn("power_stream_missing", facts["reason_codes"])

    def test_ebike_is_excluded_from_regular_cycling(self):
        facts = career_backend.build_activity_record_facts(_base_activity(
            sport_type="e_biking",
            avg_power=180,
        ))

        self.assertEqual(facts["sport"], "unsupported")
        self.assertTrue(facts["is_ebike"])
        self.assertIn("ebike_scope_excluded", facts["reason_codes"])

    def test_hiking_does_not_mix_walking_or_mountaineering(self):
        hiking = career_backend.build_activity_record_facts(_base_activity(
            sport_type="hiking",
            gain_m=500,
            max_alt_m=1200,
        ))
        walking = career_backend.build_activity_record_facts(_base_activity(sport_type="walking"))
        mountaineering = career_backend.build_activity_record_facts(_base_activity(sport_type="mountaineering"))

        self.assertEqual(hiking["sport"], "hiking")
        self.assertEqual(walking["sport"], "unsupported")
        self.assertEqual(mountaineering["sport"], "unsupported")
        self.assertIn("unsupported_sport", walking["reason_codes"])
        self.assertIn("unsupported_sport", mountaineering["reason_codes"])

    def test_open_water_swim_maps_from_swimming_subsport(self):
        facts = career_backend.build_activity_record_facts(_base_activity(
            sport_type="swimming",
            sub_sport_type="open_water",
        ))

        self.assertEqual(facts["sport"], "open_water_swimming")
        self.assertEqual(facts["water_scope"], "open_water")

    def test_pool_swim_does_not_default_pool_length(self):
        facts = career_backend.build_activity_record_facts(_base_activity(
            sport_type="swimming",
            sub_sport_type="pool",
            points_json="",
            laps_json=json.dumps([{"elapsed_time_sec": 30, "distance_m": 50}]),
        ))

        self.assertEqual(facts["sport"], "pool_swimming")
        self.assertTrue(facts["lap_length_stream_available"])
        self.assertIn("pool_length_missing", facts["reason_codes"])

    def test_deleted_and_mock_are_excluded(self):
        deleted = career_backend.build_activity_record_facts(_base_activity(deleted_at="2026-07-16T09:00:00Z"))
        mock = career_backend.build_activity_record_facts(_base_activity(is_mock=1))

        self.assertEqual(deleted["sport"], "unsupported")
        self.assertIn("activity_deleted", deleted["reason_codes"])
        self.assertEqual(mock["sport"], "unsupported")
        self.assertIn("mock_activity_excluded", mock["reason_codes"])

    def test_missing_streams_emit_reasons(self):
        cycling = career_backend.build_activity_record_facts(_base_activity(
            sport_type="cycling",
            points_json="",
            avg_power=None,
            max_power=None,
            normalized_power=None,
        ))
        pool = career_backend.build_activity_record_facts(_base_activity(
            sport_type="pool_swimming",
            points_json="",
            laps_json="",
        ))

        self.assertIn("distance_time_stream_missing", cycling["reason_codes"])
        self.assertIn("power_stream_missing", cycling["reason_codes"])
        self.assertIn("lap_length_stream_missing", pool["reason_codes"])

    def test_safe_summary_filters_raw_streams_and_sensitive_keys(self):
        facts = career_backend.build_activity_record_facts(_base_activity(
            points_json=json.dumps([{"distance_m": 0, "t_sec": 0, "lat": 1.0}]),
            file_path="/Users/example/private.fit",
            device_serial="secret",
            power_points=[{"t": 1, "power": 200}],
        ))
        payload = json.dumps(facts, ensure_ascii=False, sort_keys=True)

        self.assertNotIn("points_json", payload)
        self.assertNotIn("power_points", payload)
        self.assertNotIn("file_path", payload)
        self.assertNotIn("device_serial", payload)
        self.assertNotIn("/Users/example", payload)


if __name__ == "__main__":
    unittest.main()
