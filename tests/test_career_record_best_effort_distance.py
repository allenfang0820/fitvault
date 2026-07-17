import unittest

import career_backend


def point(distance_m, elapsed_sec):
    return {"distance_m": distance_m, "t_sec": elapsed_sec}


class CareerRecordBestEffortDistanceTest(unittest.TestCase):
    def test_user_example_shorter_activity_internal_window_wins_5k(self):
        long_activity = [
            point(0, 0),
            point(5000, 1560),
            point(15000, 5200),
        ]
        shorter_activity = [
            point(0, 0),
            point(5000, 1440),
            point(5600, 1700),
        ]

        first = career_backend.best_effort_distance_window(long_activity, 5000)
        second = career_backend.best_effort_distance_window(shorter_activity, 5000)

        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertEqual(first["elapsed_time_sec"], 1560)
        self.assertEqual(second["elapsed_time_sec"], 1440)
        self.assertLess(second["elapsed_time_sec"], first["elapsed_time_sec"])
        self.assertEqual(second["range"]["start_distance_m"], 0)
        self.assertEqual(second["range"]["end_distance_m"], 5000)

    def test_shorter_than_target_is_unavailable(self):
        result = career_backend.best_effort_distance_window([
            point(0, 0),
            point(4999, 1500),
        ], 5000)

        self.assertFalse(result["ok"])
        self.assertIn("activity_shorter_than_target", result["reason_codes"])

    def test_exact_target_distance_outputs_full_activity_range(self):
        result = career_backend.best_effort_distance_window([
            point(0, 0),
            point(2500, 750),
            point(5000, 1500),
        ], 5000)

        self.assertTrue(result["ok"])
        self.assertEqual(result["elapsed_time_sec"], 1500)
        self.assertEqual(result["range"]["start_sec"], 0)
        self.assertEqual(result["range"]["end_sec"], 1500)
        self.assertEqual(result["range"]["distance_m"], 5000)

    def test_window_edges_are_linearly_interpolated(self):
        result = career_backend.best_effort_distance_window([
            point(0, 0),
            point(1000, 600),
            point(6000, 2100),
            point(7000, 2600),
        ], 5000)

        self.assertTrue(result["ok"])
        self.assertEqual(result["elapsed_time_sec"], 1500)
        self.assertEqual(result["range"]["start_distance_m"], 1000)
        self.assertEqual(result["range"]["end_distance_m"], 6000)
        self.assertEqual(result["range"]["start_sec"], 600)
        self.assertEqual(result["range"]["end_sec"], 2100)

    def test_time_gap_break_prevents_crossing_unknown_interval(self):
        result = career_backend.best_effort_distance_window([
            point(0, 0),
            point(2500, 1000),
            point(5000, 5000),
            point(7500, 6000),
        ], 5000)

        self.assertFalse(result["ok"])
        self.assertIn("time_gap_break", result["reason_codes"])

    def test_distance_rollback_splits_segments(self):
        result = career_backend.best_effort_distance_window([
            point(0, 0),
            point(4000, 1200),
            point(3000, 1300),
            point(7000, 2500),
        ], 5000)

        self.assertFalse(result["ok"])
        self.assertIn("distance_rollback", result["reason_codes"])

    def test_absurd_distance_jump_splits_segments(self):
        result = career_backend.best_effort_distance_window([
            point(0, 0),
            point(5000, 10),
            point(10000, 2000),
        ], 5000)

        self.assertFalse(result["ok"])
        self.assertIn("distance_jump_break", result["reason_codes"])

    def test_missing_stream_fallback_is_lower_confidence_and_blocks_active(self):
        result = career_backend.best_effort_distance_or_fallback(
            [],
            5000,
            activity={"id": "run-1", "sport_type": "running", "dist_km": 5.05, "duration_sec": 1500},
            fallback_tolerance_ratio=0.03,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "fallback_activity_total")
        self.assertEqual(result["source_mode"], "fallback_activity_total")
        self.assertEqual(result["quality"]["confidence_band"], "lower")
        self.assertEqual(result["quality"]["decision"], "validation_required")
        self.assertTrue(result["quality"]["blocks_active"])
        self.assertIn("legacy_distance_tolerance_match", result["quality"]["reason_codes"])
        self.assertEqual(result["range"]["start_sec"], 0.0)
        self.assertEqual(result["range"]["end_sec"], 1500)

    def test_missing_stream_outside_fallback_tolerance_does_not_extrapolate(self):
        result = career_backend.best_effort_distance_or_fallback(
            [],
            5000,
            activity={"id": "run-1", "sport_type": "running", "dist_km": 5.6, "duration_sec": 1500},
            fallback_tolerance_ratio=0.03,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "validation_required")
        self.assertIn("activity_total_outside_tolerance", result["reason_codes"])
        self.assertNotIn("elapsed_time_sec", result)


if __name__ == "__main__":
    unittest.main()
