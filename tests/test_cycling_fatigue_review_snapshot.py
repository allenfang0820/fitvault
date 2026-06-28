from __future__ import annotations

import os
import sys
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


class TestCyclingFatigueReviewSnapshot(unittest.TestCase):
    def test_power_and_cadence_curves_are_distance_aligned(self):
        import main

        bundle = {
            "distance_curve_m": [0.0, 1000.0, 2000.0, 3000.0],
            "time_curve_sec": [0.0, 180.0, 360.0, 540.0],
            "hr_curve": [130, 135, 140, 142],
            "speed_curve_mps": [5.5, 5.6, 5.4, 5.5],
            "altitude_curve_m": [20, 22, 25, 24],
            "power_curve": [180, 190, 200, 195],
            "cadence_curve": [82, 84, 86, 85],
            "total_distance_m": 3000.0,
        }
        curves = main._build_fatigue_review_curves_snapshot(bundle, {})

        self.assertEqual(curves["distance"], [0.0, 1.0, 2.0, 3.0])
        self.assertEqual(curves["power"], [180.0, 190.0, 200.0, 195.0])
        self.assertEqual(curves["cadence"], [82.0, 84.0, 86.0, 85.0])

    def test_summary_marks_available_when_samples_are_valid(self):
        import main

        row = {
            "avg_power": 210,
            "max_power": 480,
            "normalized_power": 230,
            "avg_cadence": 86,
        }
        curves = {
            "distance": [i / 10 for i in range(25)],
            "power": [200 + i for i in range(25)],
            "cadence": [80 + (i % 5) for i in range(25)],
        }
        summary = main._build_fatigue_review_summary(row, {}, curves)

        self.assertTrue(summary["power_available"])
        self.assertTrue(summary["cadence_available"])
        self.assertEqual(summary["power_points_count"], 25)
        self.assertEqual(summary["cadence_points_count"], 25)
        self.assertEqual(summary["power_data_quality"], "available")
        self.assertEqual(summary["cadence_data_quality"], "available")
        self.assertEqual(summary["normalized_power"], 230.0)

    def test_summary_marks_missing_without_power(self):
        import main

        curves = {
            "distance": [0, 1, 2, 3],
            "power": [],
            "cadence": [80, 81, 82, 83],
        }
        summary = main._build_fatigue_review_summary({}, {}, curves)

        self.assertFalse(summary["power_available"])
        self.assertEqual(summary["power_points_count"], 0)
        self.assertEqual(summary["power_data_quality"], "missing")

    def test_summary_marks_insufficient_points(self):
        import main

        curves = {
            "distance": [i for i in range(10)],
            "power": [180 + i for i in range(10)],
            "cadence": [80 + i for i in range(10)],
        }
        summary = main._build_fatigue_review_summary({}, {}, curves)

        self.assertFalse(summary["power_available"])
        self.assertEqual(summary["power_points_count"], 10)
        self.assertEqual(summary["power_data_quality"], "insufficient_points")

    def test_summary_marks_invalid_values_when_anomaly_ratio_is_high(self):
        import main

        curves = {
            "distance": [i for i in range(25)],
            "power": [3000] * 10 + [200] * 15,
            "cadence": [300] * 10 + [85] * 15,
        }
        summary = main._build_fatigue_review_summary({}, {}, curves)

        self.assertFalse(summary["power_available"])
        self.assertFalse(summary["cadence_available"])
        self.assertEqual(summary["power_data_quality"], "invalid_values")
        self.assertEqual(summary["cadence_data_quality"], "invalid_values")

    def test_summary_marks_length_mismatch(self):
        import main

        curves = {
            "distance": [0, 1, 2, 3, 4],
            "power": [180, 190, 200],
            "cadence": [80, 81, 82],
        }
        summary = main._build_fatigue_review_summary({}, {}, curves)

        self.assertFalse(summary["power_available"])
        self.assertFalse(summary["cadence_available"])
        self.assertEqual(summary["power_data_quality"], "length_mismatch")
        self.assertEqual(summary["cadence_data_quality"], "length_mismatch")

    def test_ai_curve_summary_uses_counts_not_full_curves(self):
        from main import Api

        curves = {
            "distance": [0, 1, 2],
            "time": [0, 60, 120],
            "power": [180, 190, 200],
            "cadence": [80, 82, 84],
        }
        summary = Api._summarize_fatigue_review_curves_for_ai(curves)

        self.assertTrue(summary["has_power"])
        self.assertTrue(summary["has_cadence"])
        self.assertEqual(summary["power_points_count"], 3)
        self.assertEqual(summary["cadence_points_count"], 3)
        self.assertNotIn("power", summary)
        self.assertNotIn("cadence", summary)

    def test_curve_bundle_uses_track_json_cadence_when_db_curve_missing(self):
        import json
        import main

        points = []
        for idx in range(30):
            points.append({
                "time": f"2026-06-26T00:00:{idx:02d}Z",
                "distance": idx * 10.0,
                "hr": 120 + (idx % 5),
                "pace": 180.0,
                "alt": 100.0,
                "cadence": 80 + (idx % 4),
                "power": 180 + idx,
            })
        row = {
            "track_json": json.dumps(points),
            "points_json": json.dumps(points),
            "cadence_curve": "",
            "dist_km": 0.29,
            "duration_sec": 30,
            "sport_type": "cycling",
        }

        bundle = main._build_fatigue_review_curve_bundle(row)

        self.assertEqual(len(bundle["cadence_curve"]), 30)
        self.assertEqual(bundle["cadence_curve"][:4], [80, 81, 82, 83])

    def test_algorithm_record_conversion_preserves_cadence(self):
        from metrics_resolver import MetricsResolver

        records = MetricsResolver._convert_track_to_algorithm_records([
            {
                "time": "2026-06-26T00:00:00Z",
                "distance": 0.0,
                "hr": 120,
                "pace": 180.0,
                "alt": 100.0,
                "cadence": 82,
                "power": 180,
            },
            {
                "time": "2026-06-26T00:00:01Z",
                "distance": 5.0,
                "hr": 121,
                "pace": 180.0,
                "alt": 100.0,
                "cadence": 83,
                "power": 181,
            },
        ])

        self.assertEqual([r.get("cadence") for r in records], [82, 83])


if __name__ == "__main__":
    unittest.main()
